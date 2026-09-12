# -*- coding: utf-8 -*-
"""法寶神將玩法指南產生器 —— 產生 shenjiang.html, 跑完自己驗證一次。

用法:

    python tools/build_shenjiang.py

會覆寫 shenjiang.html。輸出是決定性的 —— 來源沒變的話重跑一次 git status
應該是乾淨的, 這也是最好的回歸測試。

--------------------------------------------------------------------------
來源 (全部在 2.開機擋)
--------------------------------------------------------------------------
  script/20.法寶神將/00.設定.txt   所有 $@SJ_* 表(神將名/階級/定位/靈氣/技能、
                                   養成成本、兌換比例、召喚池機率)
  script/20.法寶神將/02.附靈.txt   召喚期間給主人的加成(bonus 那一段)
  script/20.法寶神將/03.NPC.txt    NPC 座標
  conf/battle/blackgod.conf        sj_* 設定(基礎 ATK、召喚時長…)
  conf/battle/player.conf          max_res_mres_ignored(無視特性的全服上限)
  db/import/blackgod/item_shenjiang.yml  道具名稱
  db/import/item_cash.yml          神將轉蛋的商城定價

★★ 這一頁沒有任何手寫的數字 ★★
  每一個數值都是從上面那幾支解析出來的。玩法敘述可以手寫, 數字不行 ——
  手寫的數字會在改平衡時默默過期, 而網頁不會報錯。

★ 技能陣列的索引是「神將編號 * 4 + 技能位(0~3)」, 不是 (編號-1)*4。
  依據是 03.NPC.txt:96 的 `$@SJ_Sk$[.@g * 4 + .@i]`, 不是自己數出來的。

★ 召喚池機率是「累積切點」不是各自機率:
  $@SJ_PoolCut[i] 是第 i 段的上界, 分母 $@SJ_PoolDen。所以某一段的機率是
  (cut[i] - cut[i-1]) / den。直接把 cut 當機率印會得到一組完全錯誤的數字。

★ 「無視特性 RES/MRES」的上限 max_res_mres_ignored 在 conf/battle/player.conf,
  不在 blackgod.conf —— 而且那是全服共用總額, 頁面要講清楚免得玩家誤會
  成額外配額。
"""
import io, os, re, sys, html

HERE = os.path.dirname(os.path.abspath(__file__))
WEB  = os.path.dirname(HERE)
ROOT = r"H:\91.神域仙境"
SRV  = os.path.join(ROOT, "2.開機擋")
SJ   = os.path.join(SRV, r"script\20.法寶神將")

F_CONF  = os.path.join(SJ, "00.設定.txt")
F_AURA  = os.path.join(SJ, "02.附靈.txt")
F_NPC   = os.path.join(SJ, "03.NPC.txt")
F_GROW  = os.path.join(SJ, "04.養成.txt")
F_BATT  = os.path.join(SRV, r"conf\battle\blackgod.conf")
F_PLAY  = os.path.join(SRV, r"conf\battle\player.conf")
F_ITEM  = os.path.join(SRV, r"db\import\blackgod\item_shenjiang.yml")
F_CASH  = os.path.join(SRV, r"db\import\item_cash.yml")

STYLE_FROM = os.path.join(WEB, "potential.html")
DEST       = os.path.join(WEB, "shenjiang.html")

NG = 29          # 神將數量, 會對來源驗證


def die(msg):
    sys.exit("[build_shenjiang] " + msg)


def read(path):
    with io.open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def e(s):
    return html.escape(str(s), quote=False)


def comma(n):
    return "{:,}".format(int(n))


# ==========================================================================
#  來源解析
# ==========================================================================
def parse_scalars(src):
    """$@SJ_Xxx = 123;  ->  {'SJ_Xxx': 123}"""
    out = {}
    for m in re.finditer(r"^\s*\$@(SJ_[A-Za-z0-9_]+)\s*=\s*(-?\d+)\s*;", src, re.M):
        out[m.group(1)] = int(m.group(2))
    return out


def parse_setarray(src, name):
    """setarray $@<name>[start], a, b, c;  ->  dict{index: int}"""
    pat = r"setarray\s+\$@" + re.escape(name) + r"\[(\d+)\]\s*,([^;]*);"
    m = re.search(pat, src)
    if not m:
        return None
    start = int(m.group(1))
    vals = [v.strip() for v in m.group(2).split(",")]
    out = {}
    for i, v in enumerate(vals):
        if v == "":
            continue
        out[start + i] = int(v)
    return out


def parse_setarray_str(src, name):
    """setarray $@<name>$[start], "a", "b";  ->  dict{index: str}"""
    pat = r"setarray\s+\$@" + re.escape(name) + r"\$\[(\d+)\]\s*,([^;]*);"
    m = re.search(pat, src)
    if not m:
        return None
    start = int(m.group(1))
    vals = re.findall(r'"([^"]*)"', m.group(2))
    return {start + i: v for i, v in enumerate(vals)}


def parse_indexed_str(src, name):
    """$@<name>$[n] = "text";  ->  dict{n: str}"""
    out = {}
    pat = r"\$@" + re.escape(name) + r"\$\[(\d+)\]\s*=\s*\"([^\"]*)\"\s*;"
    for m in re.finditer(pat, src):
        out[int(m.group(1))] = m.group(2)
    return out


def parse_conf(src, prefix):
    """key: value  ->  {key: int}, 只收指定前綴且值是整數的"""
    out = {}
    for m in re.finditer(r"^\s*(" + prefix + r"[a-z0-9_]*)\s*:\s*(-?\d+)", src, re.M):
        out[m.group(1)] = int(m.group(2))
    return out


def parse_item_names(src):
    """item_shenjiang.yml -> {id: 中文名}"""
    out, cur = {}, None
    for line in src.split("\n"):
        m = re.match(r"\s*-\s*Id:\s*(\d+)", line)
        if m:
            cur = int(m.group(1))
            continue
        m = re.match(r"\s*Name:\s*(.+?)\s*$", line)
        if m and cur is not None:
            out[cur] = m.group(1)
            cur = None
    return out


def parse_cash_price(src, item_id):
    """item_cash.yml 裡某個道具的 Price"""
    pat = r"-\s*Item:\s*" + str(item_id) + r"\s*\n\s*Price:\s*(\d+)"
    m = re.search(pat, src)
    return int(m.group(1)) if m else None


# ==========================================================================
def main():
    S = read(F_CONF)
    A = read(F_AURA)
    N = read(F_NPC)
    B = read(F_BATT)
    P = read(F_PLAY)
    items = parse_item_names(read(F_ITEM))
    cash = read(F_CASH)

    sc = parse_scalars(S)
    cfg = parse_conf(B, "sj_")

    # ---- 神將本體 ----
    name = parse_indexed_str(S, "SJ_Name")
    role = parse_indexed_str(S, "SJ_Role")
    aura = parse_indexed_str(S, "SJ_Aura")
    skil = parse_indexed_str(S, "SJ_Sk")
    grade = parse_setarray(S, "SJ_Grade")
    for label, d in (("名稱", name), ("定位", role), ("靈氣", aura), ("階級", grade)):
        if sorted(d) != list(range(1, NG + 1)):
            die("%s 表不是 1~%d 連續(實際 %d 筆)" % (label, NG, len(d)))

    realm = parse_setarray_str(S, "SJ_RealmName")
    if sorted(realm) != list(range(12)):
        die("十二境名稱不是 0~11")

    # ---- 養成成本 ----
    lvcap = parse_setarray(S, "SJ_LvCap")
    tabs = {}
    for k in ("SJ_LvFrag", "SJ_LvPhantom", "SJ_LvZeny", "SJ_LvMatA", "SJ_LvMatB",
              "SJ_LvMatN", "SJ_StarFragN", "SJ_StarFragP", "SJ_StarPhantom",
              "SJ_StarZeny", "SJ_StarMatA", "SJ_StarMatB", "SJ_StarMatN"):
        t = parse_setarray(S, k)
        if t is None:
            die("找不到 $@%s" % k)
        tabs[k] = t
    seal_it = parse_setarray(S, "SJ_ItSeal")
    realm_it = parse_setarray(S, "SJ_ItRealm")
    rate = parse_setarray(S, "SJ_SealRate")
    fee = parse_setarray(S, "SJ_SealFee")

    # ---- 召喚池 ----
    cut = parse_setarray(S, "SJ_PoolCut")
    den = sc.get("SJ_PoolDen")
    if not cut or den is None:
        die("找不到召喚池機率表")
    if cut[max(cut)] != den:
        die("$@SJ_PoolCut 最後一段不等於分母, 機率表對不起來")

    # ---- 召喚期間的玩家加成 (02.附靈.txt) ----
    blk = re.search(r"if\s*\(\s*getsjinfo\(1\)\s*\)\s*\{(.*?)\n\t\}", A, re.S)
    if not blk:
        die("02.附靈.txt 找不到 getsjinfo(1) 的召喚加成區塊")
    blk = blk.group(1)

    def two(pat):
        m = re.search(pat, blk)
        if not m:
            die("召喚加成解析不到: " + pat)
        return int(m.group(1)), int(m.group(2))

    hp_p, hp_n = two(r"bonus\s+bMaxHPrate,\s*\(\.@prem\)\s*\?\s*(\d+)\s*:\s*(\d+)")
    sp_p, sp_n = two(r"bonus\s+bMaxSPrate,\s*\(\.@prem\)\s*\?\s*(\d+)\s*:\s*(\d+)")
    ig_p, ig_n = two(r"bIgnoreResRaceRate,\s*RC_ALL,\s*\(\.@prem\)\s*\?\s*(\d+)\s*:\s*(\d+)")
    tr_p, tr_n = two(r"\.@tr\s*=\s*\(\.@prem\)\s*\?\s*(\d+)\s*:\s*(\d+)")
    if (hp_p, hp_n) != (sp_p, sp_n):
        die("MHP 與 MSP 的百分比不一致, 頁面那一列不能合併")
    m = re.search(r"^\s*max_res_mres_ignored\s*:\s*(\d+)", P, re.M)
    if not m:
        die("player.conf 找不到 max_res_mres_ignored")
    ig_cap = int(m.group(1))

    # ---- 等級與星級的上限 (04.養成.txt, 一般與特級不同) ----
    #   ★ 這兩組數字以前是手寫在頁面上的, 但「一般 Lv.100 封頂」正是玩家
    #     看了成本表最會誤會的地方 —— 表上有 6 個階段, 後兩段其實只有特級
    #     開得了。一律從實作解析。
    G = read(F_GROW)
    m = re.search(r"\.@maxlv\s*=\s*\(\$@SJ_Grade\[\.@g\]\)\s*\?\s*(\d+)\s*:\s*(\d+)", G)
    if not m:
        die("04.養成.txt 解析不到等級上限 .@maxlv")
    lv_p, lv_n = int(m.group(1)), int(m.group(2))
    m = re.search(r"\.@maxs\s*=\s*\(\.@prem\)\s*\?\s*(\d+)\s*:\s*(\d+)", G)
    if not m:
        die("04.養成.txt 解析不到星級上限 .@maxs")
    st_p, st_n = int(m.group(1)), int(m.group(2))
    # 一般神將從第幾階段開始開不了
    m = re.search(r"if\s*\(\s*\.@step\s*>=\s*(\d+)\s*&&\s*!\$@SJ_Grade\[\.@g\]\s*\)", G)
    if not m:
        die("04.養成.txt 解析不到「一般神將止步於第幾階段」")
    step_lock = int(m.group(1))

    # ---- NPC 座標 ----
    m = re.search(r"^(\w+),(\d+),(\d+),\d+\s+script\s+", N, re.M)
    if not m:
        die("03.NPC.txt 找不到 NPC 的座標行")
    npc_map, npc_x, npc_y = m.group(1), int(m.group(2)), int(m.group(3))

    # ---- 轉蛋定價 ----
    tk = sc.get("SJ_ItTicket")
    price = parse_cash_price(cash, tk)
    if price is None:
        die("item_cash.yml 裡找不到轉蛋 %s 的定價" % tk)

    npre = sum(1 for g in range(1, NG + 1) if grade[g] == 1)
    nnor = NG - npre

    # ======================================================================
    #  表格
    # ======================================================================
    rows = []
    for g in range(1, NG + 1):
        prem = grade[g] == 1
        sk = [skil[g * 4 + i] for i in range(4) if skil.get(g * 4 + i)]
        rows.append(
            '<tr><td class="c">%d</td><td class="nm">%s%s</td><td class="c">%s</td>'
            '<td>%s</td><td>%s</td></tr>'
            % (g, e(name[g]),
               ' <span class="bn">特級</span>' if prem else "",
               e(role[g]), e(aura[g]),
               "<br>".join(e(x) for x in sk) if sk else
               '<span class="dim">—</span>'))
    tbl_gen = "\n".join(rows)

    # 召喚池
    pool_label = ["特級法寶", "一般法寶", "特級神將碎片", "一般神將碎片", "材料"]
    if len(cut) != len(pool_label):
        die("召喚池是 %d 段, 但這裡只準備了 %d 個標籤" % (len(cut), len(pool_label)))
    rows, prev = [], 0
    for i in sorted(cut):
        pct = (cut[i] - prev) * 100.0 / den
        rows.append('<tr><td>%s</td><td class="c">%s</td></tr>'
                    % (e(pool_label[i]), ("%.5f" % pct).rstrip("0").rstrip(".") + "%"))
        prev = cut[i]
    tbl_pool = "\n".join(rows)

    # 等級
    rows = []
    for s in sorted(tabs["SJ_LvFrag"]):
        rows.append('<tr><td class="c">%d</td><td class="c">Lv.%d</td><td class="c">%s</td>'
                    '<td class="c">%s</td><td class="c">%s</td><td class="c">%s</td></tr>'
                    % (s, lvcap[s], comma(tabs["SJ_LvFrag"][s]),
                       comma(tabs["SJ_LvPhantom"][s]), comma(tabs["SJ_LvMatN"][s]),
                       comma(tabs["SJ_LvZeny"][s])))
    tbl_lv = "\n".join(rows)

    # 升星
    rows = []
    for s in sorted(tabs["SJ_StarPhantom"]):
        fn = tabs["SJ_StarFragN"].get(s, 0)
        rows.append('<tr><td class="c">%d → %d</td><td class="c">%s</td><td class="c">%s</td>'
                    '<td class="c">%s</td><td class="c">%s</td><td class="c">%s</td></tr>'
                    % (s, s + 1,
                       comma(fn) if fn else '<span class="dim">上限</span>',
                       comma(tabs["SJ_StarFragP"][s]), comma(tabs["SJ_StarPhantom"][s]),
                       comma(tabs["SJ_StarMatN"][s]), comma(tabs["SJ_StarZeny"][s])))
    tbl_star = "\n".join(rows)

    # 十二境神將印
    rows = []
    for i in sorted(rate):
        rows.append('<tr><td class="c">%s境</td><td>%s</td><td>%s</td>'
                    '<td class="c">%s : 1</td><td class="c">%s</td></tr>'
                    % (e(realm[i]), e(items.get(realm_it[i], realm_it[i])),
                       e(items.get(seal_it[i], seal_it[i])),
                       comma(rate[i]), comma(fee[i]) + " Zeny"))
    tbl_seal = "\n".join(rows)

    hours = cfg["sj_summon_time"] / 3600000.0
    hour_s = ("%.1f" % hours).rstrip("0").rstrip(".")

    # ======================================================================
    #  HTML
    # ======================================================================
    style = re.search(r"<style>.*?</style>", read(STYLE_FROM), re.S)
    if not style:
        die("potential.html 裡找不到 <style> 區段")
    style = style.group(0)

    extra = """
<style>
.nm{font-weight:700}
h3.sub{font-family:"Noto Serif TC",serif; font-size:16px; margin:24px 0 0}
.steps{list-style:none; margin:0; padding:0; display:grid; gap:14px;
       grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.steps li{border:1px solid var(--rule); border-radius:10px; padding:14px 16px}
.steps b{display:block; font-family:"Noto Serif TC",serif; font-size:17px;
         margin-bottom:6px}
.steps i{font-style:normal; color:var(--cinnabar); font-weight:700;
         margin-right:.45em}
.steps p{margin:0; font-size:14px; color:var(--ink-soft); line-height:1.75}
.bn{display:inline-block; padding:1px 7px; margin-left:6px; border-radius:6px;
    font-size:.82em; white-space:nowrap; font-weight:700;
    background:#c6503022; color:#c65030}
.dim{color:var(--ink-soft); opacity:.7}
.c{text-align:center; white-space:nowrap}
.callout{border-left:3px solid var(--cinnabar); padding:2px 0 2px 14px;
         margin:18px 0 0; color:var(--ink-soft); font-size:14.5px;
         line-height:1.85; max-width:72ch}
.callout b{color:var(--ink)}
.two{display:grid; gap:24px; grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.two .note{max-width:none}
</style>"""

    doc = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>法寶神將玩法</title>
<meta name="description" content="神域仙境 法寶神將：29 名神將的靈氣與技能、召喚池機率、升級升星成本、十二境神將印兌換、召喚期間的加成。">
<meta name="color-scheme" content="light dark">
<meta property="og:type" content="website">
<meta property="og:site_name" content="神域仙境">
<meta property="og:title" content="法寶神將玩法">
<meta property="og:description" content="一件法寶、一名神將。裝備就有靈氣加成，召喚出來還會替你打。">
<meta property="og:image" content="https://drw-online.github.io/game/og.jpg">
<meta property="og:image:width" content="600">
<meta property="og:image:height" content="600">
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="#EFF1EC" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#121615" media="(prefers-color-scheme: dark)">
<link rel="icon" href="favicon.png" type="image/png">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Noto+Serif+TC:wght@600;700&display=swap">
__STYLE__
__EXTRA__
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <a class="home" href="index.html">
      <img src="logo.webp" width="440" height="440" alt="" decoding="async">
      <span>← 神域仙境 玩家工具</span>
    </a>
    <h1>法寶神將玩法</h1>
    <p class="lede">一件法寶對應一名神將。<b>裝備法寶</b>就有靈氣加成，<b>召喚出來</b>神將會上場替你打，而且召喚期間主人自己也會變強。全部功能都在崑崙的<b>【御寶天君‧雲虛】</b>（__MAP__ __X__,__Y__）。</p>
  </header>

  <section>
    <h2>三句話</h2>
    <ol class="steps">
      <li><b><i>一</i>拿到法寶</b><p>用<b>__TICKET__</b>抽，或蒐集<b>神將碎片</b>湊。共 __NG__ 名神將，其中 __NPRE__ 名是特級。</p></li>
      <li><b><i>二</i>裝備法寶</b><p>裝上去就有<b>靈氣</b>加成，不必召喚。同時只能裝一件 —— 換法寶會讓星級歸零。</p></li>
      <li><b><i>三</i>召喚神將</b><p>神將上場替你打，一次撐 <b>__HOURS__ 小時</b>。召喚期間主人另外拿到一整批加成。</p></li>
    </ol>
  </section>

  <section>
    <h2>召喚期間，主人拿到什麼</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>項目</th><th class="c">一般神將</th><th class="c">特級神將</th></tr></thead>
        <tbody>
          <tr><td>最大 HP／最大 SP</td><td class="c">+__HPN__%</td><td class="c">+__HPP__%</td></tr>
          <tr><td>無視特性 RES／MRES</td><td class="c">+__IGN__%</td><td class="c">+__IGP__%</td></tr>
          <tr><td>全特性素質（六項各）</td><td class="c">+__TRN__</td><td class="c">+__TRP__</td></tr>
        </tbody>
      </table>
    </div>
    <p class="note">這些<b>只在神將真的在場上時生效</b>，收回或時間到就沒了 —— 跟「裝備法寶就有」的靈氣是兩回事。</p>
    <div class="callout"><b>無視特性 RES／MRES 有一個共用上限。</b>全服總上限是 <b>__IGCAP__%</b>，而且是<b>與其他來源共用</b>的、不是額外配額 —— 你身上如果已經從別處吃滿了，神將這一份就疊不上去。</div>
  </section>

  <section>
    <h2>__NG__ 名神將</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th class="c">編號</th><th>名稱</th><th class="c">定位</th><th>靈氣（裝備就生效）</th><th>技能</th></tr></thead>
        <tbody>__TBLGEN__</tbody>
      </table>
    </div>
    <p class="note">一般神將 __NNOR__ 名、特級 __NPRE__ 名。等級上限一般 <b>Lv.__LVN__</b>、特級 <b>Lv.__LVP__</b>；星級上限一般 <b>__STN__ 星</b>、特級 <b>__STP__ 星</b>。</p>
  </section>

  <section>
    <h2>怎麼拿到</h2>
    <div class="two">
      <div>
        <h3 class="sub">召喚池機率</h3>
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>抽到什麼</th><th class="c">機率</th></tr></thead>
            <tbody>__TBLPOOL__</tbody>
          </table>
        </div>
        <p class="note">抽一次要一張<b>__TICKET__</b>，商城「新商品」頁上架，<b>__PRICE__ 點</b>。</p>
      </div>
      <div>
        <h3 class="sub">碎片也能湊</h3>
        <p class="note">抽到重複的法寶可以在天君那裡<b>分解</b>成該神將的碎片：一般 __DUPN__ 片、特級 __DUPP__ 片。碎片本身可以交易，湊齊了一樣能請出神將。</p>
        <p class="note">碎片與法寶也會從<b>天降福利</b>之類的活動流出來，不是只有商城一條路。</p>
      </div>
    </div>
  </section>

  <section>
    <h2>養成</h2>
    <h3 class="sub">提升等級</h3>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th class="c">階段</th><th class="c">可升到</th><th class="c">神將碎片</th><th class="c">幻影碎片</th><th class="c">神將印（兩種各）</th><th class="c">Zeny</th></tr></thead>
        <tbody>__TBLLV__</tbody>
      </table>
    </div>
    <div class="callout"><b>一般神將只開到第 __STEPMAX__ 階段（Lv.__LVN__）。</b>第 __STEPLOCK__ 階段以後只有特級神將能升，一路到 Lv.__LVP__ —— 表上有六個階段，但一般神將用不到後面兩個。</div>

    <h3 class="sub">升星</h3>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th class="c">星級</th><th class="c">碎片（一般）</th><th class="c">碎片（特級）</th><th class="c">幻影碎片</th><th class="c">神將印（兩種各）</th><th class="c">Zeny</th></tr></thead>
        <tbody>__TBLSTAR__</tbody>
      </table>
    </div>
    <p class="note">升星<b>固定成功，不會失敗</b>。Zeny 超過單筆上限的階段可以分次存入，存滿了再升。升星成功會發<b>全服公告</b>。</p>

    <h3 class="sub">十二境神將印怎麼換</h3>
    <p class="note">養成吃的是<b>神將印</b>不是原始材料 —— 原始材料要先在天君那裡兌換成<b>同境</b>的印，不能跨境、高境也不能向下替代。兌換<b>固定成功但不可還原</b>，神將印帳號綁定。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th class="c">境</th><th>原始材料</th><th>換成</th><th class="c">比例</th><th class="c">每枚手續費</th></tr></thead>
        <tbody>__TBLSEAL__</tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>天君還能做什麼</h2>
    <div class="two">
      <div>
        <p class="note"><b>設定戰鬥 AI</b> —— 跟隨、主動、守護、集火、輔助、停止六種，決定神將上場之後怎麼動。</p>
        <p class="note"><b>裝備法寶符印</b> —— 戰印／真印／靈印三種，分別加攻擊、血量與冷卻縮減。</p>
      </div>
      <div>
        <p class="note"><b>分解重複法寶</b> —— 重複的法寶換成該神將的碎片。</p>
        <p class="note"><b>法寶修復</b> —— 法寶碎片換回剩餘冷卻的一半，每天一次，所有品階共用。</p>
      </div>
    </div>
  </section>

  <footer class="foot">
    <p>資料直接取自伺服器設定檔，改動後重新產生即可。</p>
    <p><a href="index.html">← 回玩家工具首頁</a></p>
  </footer>
</div>
</body>
</html>
"""

    rep = {
        "__STYLE__": style,
        "__EXTRA__": extra,
        "__MAP__": e(npc_map),
        "__X__": str(npc_x),
        "__Y__": str(npc_y),
        "__NG__": str(NG),
        "__NPRE__": str(npre),
        "__NNOR__": str(nnor),
        "__HOURS__": hour_s,
        "__HPN__": str(hp_n), "__HPP__": str(hp_p),
        "__IGN__": str(ig_n), "__IGP__": str(ig_p),
        "__TRN__": str(tr_n), "__TRP__": str(tr_p),
        "__IGCAP__": str(ig_cap),
        "__LVN__": str(lv_n), "__LVP__": str(lv_p),
        "__STN__": str(st_n), "__STP__": str(st_p),
        "__STEPLOCK__": str(step_lock),
        "__STEPMAX__": str(step_lock - 1),
        "__TBLGEN__": tbl_gen,
        "__TBLPOOL__": tbl_pool,
        "__TBLLV__": tbl_lv,
        "__TBLSTAR__": tbl_star,
        "__TBLSEAL__": tbl_seal,
        "__TICKET__": e(items.get(tk, tk)),
        "__PRICE__": str(price),
        "__DUPN__": comma(sc["SJ_DupFragN"]),
        "__DUPP__": comma(sc["SJ_DupFragP"]),
    }
    for k, v in rep.items():
        doc = doc.replace(k, v)

    left = sorted(set(re.findall(r"__[A-Z0-9_]+__", doc)))
    if left:
        die("還有沒被替換的樣板欄位: %s" % left)

    with io.open(DEST, "w", encoding="utf-8", newline="\n") as f:
        f.write(doc)

    print("神將 %d 名(一般 %d / 特級 %d)" % (NG, nnor, npre))
    print("上限: 等級 一般 %d / 特級 %d, 星級 一般 %d / 特級 %d; 一般止步於第 %d 階段"
          % (lv_n, lv_p, st_n, st_p, step_lock - 1))
    print("召喚池 %d 段, 分母 %s" % (len(cut), comma(den)))
    print("召喚 %s 小時; MHP/MSP +%d%%/+%d%%, 無視特性 +%d%%/+%d%%(上限 %d%%), 特性素質 +%d/+%d"
          % (hour_s, hp_n, hp_p, ig_n, ig_p, ig_cap, tr_n, tr_p))
    print("基礎 ATK/MATK 一般 %s / 特級 %s"
          % (comma(cfg["sj_base_atk_normal"]), comma(cfg["sj_base_atk_premium"])))
    print("轉蛋 %s 商城 %d 點" % (items.get(tk, tk), price))
    print("已寫出 %s (%d bytes)" % (DEST, os.path.getsize(DEST)))


if __name__ == "__main__":
    main()

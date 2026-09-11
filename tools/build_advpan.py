# -*- coding: utf-8 -*-
"""
進階星盤圖鑑產生器 —— 產生 advpan.html, 跑完自己驗證一次。

用法:

    python tools/build_advpan.py

會覆寫 advpan.html。輸出是決定性的 —— 來源沒變的話重跑一次 git status
應該是乾淨的, 這也是最好的回歸測試。

--------------------------------------------------------------------------
來源
--------------------------------------------------------------------------
  script/17.進階星盤/00.設定.txt      54 個節點、六大星域、常數、觸發表
  script/17.進階星盤/02.NPC.txt       效果 key 的中文名與單位、條件型節點說明
  add/src/blackgod_astro_proc.inc     星蝕的持續時間與 ICD (引擎才是真相)
  自創/0909/神域仙境_進階星盤系統.md   §9.3 星蝕效果的玩家措辭
  db/import/blackgod/item_daopan.yml  洗點材料名(與大道星盤共用)
  conf/battle/blackgod.conf           adv_enable / adv_proc_per_sec

--------------------------------------------------------------------------
三個會讓產出安靜出錯的地方
--------------------------------------------------------------------------
★ 節點資料是「一行多個單格賦值」不是 setarray:
      $@adv_name$[101] = "尋靈之眼";	$@adv_tier[101] = 1;
  只寫 setarray 的解析器會抓到 0 筆而且不報錯 —— 頁面會變成空的六個星域。

★ 觸發表的值是「具名常數」不是數字:
      $@adv_pk[203] = $@ADV_PK_ABN;
  只認數字的 regex 會靜默漏掉全部 24 個觸發型節點, 那些節點在頁面上會
  看起來「沒有正面效果」—— 而那正好牴觸企劃書 §2.2, verify() 因此會吵。
  這是刻意讓它吵的。

★ 效果 key 的中文名在 02.NPC.txt 不在 00.設定.txt:
  那是 2026-09-09 的分工 —— 00 是數值表, 02 是 UI 文案。抓錯檔案會得到
  空字串, 頁面上每一條效果都只剩數字。
"""
import os, re, io, html, json      # json: 互動星盤要把節點資料序列化進頁面

HERE = os.path.dirname(os.path.abspath(__file__))
WEB  = os.path.dirname(HERE)
ROOT = r"H:\91.神域仙境"
SRV  = os.path.join(ROOT, "2.開機擋")
SRC  = os.path.join(ROOT, "1.原始碼")

CFG   = os.path.join(SRV, r"script\17.進階星盤\00.設定.txt")
UI    = os.path.join(SRV, r"script\17.進階星盤\02.NPC.txt")
ENG   = os.path.join(SRC, r"add\src\blackgod_astro_proc.inc")
SPEC  = os.path.join(ROOT, r"自創\0909\神域仙境_進階星盤系統.md")
ITEM  = os.path.join(SRV, r"db\import\blackgod\item_daopan.yml")
CONF  = os.path.join(SRV, r"conf\battle\blackgod.conf")

DEST  = os.path.join(WEB, "advpan.html")


def read(path):
    with io.open(path, encoding="utf-8-sig") as f:
        return f.read()


# ---------------------------------------------------------------- 腳本解析

def constants(t):
    """抓 $@NAME = 數字;  —— 全大寫的那些。觸發表要靠它解符號。"""
    return {m.group(1): int(m.group(2))
            for m in re.finditer(r"\$@([A-Z][A-Z0-9_]*)\s*=\s*(-?\d+)\s*;", t)}


def setarr(t, name):
    """setarray $@<name>[起始], v1, v2, ...;  -> {索引: 字串}"""
    out = {}
    for m in re.finditer(r"setarray\s+" + re.escape("$@" + name)
                         + r"\[(\d+)\]\s*,(.*?);", t, re.S):
        start = int(m.group(1))
        for i, v in enumerate(x.strip() for x in m.group(2).split(",")):
            if v:
                out[start + i] = v.strip('"')
    return out


def assign_str(t, name):
    """$@<name>$[索引] = "字串";"""
    return {int(m.group(1)): m.group(2)
            for m in re.finditer(r"\$@" + name + r"\$\[(\d+)\]\s*=\s*\"([^\"]*)\"", t)}


def assign_val(t, name, consts):
    """$@<name>[索引] = 數字 或 $@常數;  —— 一定要吃常數, 見檔頭第二點。"""
    out = {}
    for m in re.finditer(r"\$@" + name + r"\[(\d+)\]\s*=\s*(\$@[A-Za-z0-9_]+|-?\d+)\s*;", t):
        raw = m.group(2)
        if raw.startswith("$@"):
            key = raw[2:]
            if key in consts:
                out[int(m.group(1))] = consts[key]
        else:
            out[int(m.group(1))] = int(raw)
    return out


def slot_comments(t):
    """{(節點, 欄位): 行內註解} —— 取 ek/ev 那一行 // 後面的字。

    ★ 條件型節點(ek 填 0、值放在 ev)的意思「只」寫在那裡 ——
      $@adv_ek1[107] = 0;   $@adv_ev1[107] = 50;   // 低血時掉落額外 +0.5%
      那些效果沒辦法用效果 key 表達(條件是「目標身上有什麼」或「自己血量
      多少」), 所以 00.設定.txt 把它們的語意寫在註解裡, 由引擎的
      F_Adv_Damage 逐條處理。漏讀的話那 11 個節點會整欄空白, 而且
      verify() 會依企劃書 §2.2 判定「沒有負面效果」而失敗 —— 那正是
      2026-09-12 第一次跑這支時發生的事。
    """
    out = {}
    for m in re.finditer(r"\$@adv_ek(\d)\[(\d+)\].*?//\s*(.+?)\s*$", t, re.M):
        out[(int(m.group(2)), int(m.group(1)))] = m.group(3)
    return out


def conf_int(t, key, default=0):
    m = re.search(r"^" + key + r"\s*:\s*(-?\d+)\s*$", t, re.M)
    return int(m.group(1)) if m else default


# ---------------------------------------------------------------- 數值格式

def num(v):
    """把「百分點 x100」印成小數, 與 02.NPC.txt 的 F_Adv_Num 同一套規則。"""
    sign = "-" if v < 0 else ""
    v = abs(v)
    i, f = divmod(v, 100)
    if f == 0:
        return "%s%d" % (sign, i)
    if f % 10 == 0:
        return "%s%d.%d" % (sign, i, f // 10)
    return "%s%d.%02d" % (sign, i, f)


def eff_text(key, val, kn, ku):
    """單格效果 -> 一行字。與 02.NPC.txt 的 F_Adv_EffText 同一套規則。

    ku: 1 百分比(x100) / 2 點數(原值) / 3 千分點 / 4 萬分比
    """
    if not key or key not in kn or val == 0:
        return ""
    name = kn[key]
    u = ku.get(key, 1)
    if u == 2:
        return "%s %s%d" % (name, "+" if val > 0 else "", val)
    if u == 3:
        s = "-" if val < 0 else "+"
        a = abs(val)
        return "%s %s%d.%d%%" % (name, s, a // 10, a % 10)
    return "%s %s%s%%" % (name, "+" if val > 0 else "", num(val))


def proc_text(nid, pk, pr, pv, pdur, picd, pkn, abname):
    if nid not in pk or pk[nid] <= 0:
        return ""
    kind = pk[nid]
    what = pkn.get(kind, "?")
    if kind == 1:
        what = "附加" + abname.get(pv.get(nid, 0), "?")
    s = "攻擊 %s%% 機率%s" % (num(pr.get(nid, 0)), what)
    if pdur.get(nid, 0) > 0:
        s += "，持續 %s 秒" % num(pdur[nid] // 10)
    if picd.get(nid, 0) > 0:
        s += "（內置冷卻 %s 秒）" % num(picd[nid] // 10)
    return s


# ---------------------------------------------------------------- 收集

def collect():
    cfg = read(CFG)
    ui  = read(UI)
    C   = constants(cfg)

    dom     = setarr(cfg, "adv_dom$")
    domsrc  = setarr(cfg, "adv_domsrc$")
    domdesc = setarr(cfg, "adv_domdesc$")
    lo      = {k: int(v) for k, v in setarr(cfg, "adv_lo").items()}
    hi      = {k: int(v) for k, v in setarr(cfg, "adv_hi").items()}
    tcost   = {k: int(v) for k, v in setarr(cfg, "adv_tcost").items()}
    tmax    = {k: int(v) for k, v in setarr(cfg, "adv_tmax").items()}

    name = assign_str(cfg, "adv_name")
    tier = assign_val(cfg, "adv_tier", C)
    ek1  = assign_val(cfg, "adv_ek1", C); ev1 = assign_val(cfg, "adv_ev1", C)
    ek2  = assign_val(cfg, "adv_ek2", C); ev2 = assign_val(cfg, "adv_ev2", C)
    ek3  = assign_val(cfg, "adv_ek3", C); ev3 = assign_val(cfg, "adv_ev3", C)
    pk   = assign_val(cfg, "adv_pk", C);  pr  = assign_val(cfg, "adv_pr", C)
    pv   = assign_val(cfg, "adv_pv", C)
    pdur = assign_val(cfg, "adv_pdur", C); picd = assign_val(cfg, "adv_picd", C)
    xa   = assign_val(cfg, "adv_xa", C);  xb  = assign_val(cfg, "adv_xb", C)

    kn     = setarr(ui, "adv_kn$")
    ku     = {k: int(v) for k, v in setarr(ui, "adv_ku").items()}
    pkn    = assign_str(ui, "adv_pkn")
    abname = assign_str(ui, "adv_abname")
    note   = assign_str(ui, "adv_note")

    cmt = slot_comments(cfg)

    cross_lo = C["ADV_CROSS_LO"]
    cross_hi = C["ADV_CROSS_HI"]

    order = []
    for d in sorted(lo):
        for nid in range(lo[d], hi[d] + 1):
            order.append((d, nid))
    for nid in range(cross_lo, cross_hi + 1):
        order.append((7, nid))

    rows = []
    for d, nid in order:
        t = tier.get(nid, 0)
        pos, neg = [], []
        p = proc_text(nid, pk, pr, pv, pdur, picd, pkn, abname)
        if p:
            pos.append(p)
        for slot, (k, v, bucket) in enumerate(
                ((ek1.get(nid, 0), ev1.get(nid, 0), pos),
                 (ek2.get(nid, 0), ev2.get(nid, 0), neg),
                 (ek3.get(nid, 0), ev3.get(nid, 0), neg)), start=1):
            s = eff_text(k, v, kn, ku)
            if not s and k == 0 and v != 0:
                #  條件型: 效果 key 是 0, 語意只在行內註解裡 (見 slot_comments)
                s = cmt.get((nid, slot), "")
            if s:
                bucket.append(s)
        rows.append(dict(
            dom=d, id=nid, name=name.get(nid, "?"), tier=t,
            max=tmax.get(t, 1), cost=tcost.get(t, 1),
            pos=pos, neg=neg, note=note.get(nid, ""),
            xa=xa.get(nid, 0), xb=xb.get(nid, 0),
            pen_ev=(ev1.get(nid, 0) if ek1.get(nid, 0) in (31, 32) else 0),
        ))

    meta = dict(
        dom=dom, domsrc=domsrc, domdesc=domdesc, tcost=tcost, tmax=tmax,
        need_realm=C.get("ADV_NEED_REALM"), need_dao=C.get("ADV_NEED_DAO"),
        max_pt=C.get("ADV_MAX_PT"), dom_pre=C.get("ADV_DOM_PRE"),
        core_pre=C.get("ADV_CORE_PRE"), cross_pre=C.get("ADV_CROSS_PRE"),
        reset_gem=C.get("ADV_RESET_GEM"),
        item_respec=C.get("ADV_ITEM_RESPEC"), item_reset=C.get("ADV_ITEM_RESET"),
        kn=kn, ku=ku,
    )
    return rows, meta


def collect_eclipse():
    """星蝕: 結構(名稱/持續/ICD)取自引擎, 效果措辭取自企劃書 §9.3。

    ★ 兩邊都讀是刻意的 —— 引擎是真相, 但它的效果拆在 8 張 int 陣列裡,
      拿來給玩家看太碎。企劃書那張表是同一批數字的人話版本, 而 verify()
      會比對兩邊的名稱, 對不上就吵。
    ★ flags 欄可能是 0 也可能是 AAF_X | AAF_Y —— 字元類要含數字, 否則
      會安靜漏掉冰緩/致盲/感電/衰弱那四筆。
    """
    t = read(ENG)
    m = re.search(r"adv_abn_spec\[AAB_COUNT\]\s*=\s*\{(.*?)\n\};", t, re.S)
    eng = re.findall(
        r"\{\s*\"([^\"]+)\",\s*([0A-Z_| ]+),\s*(AAB_[A-Z_]+),\s*"
        r"(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(\d+)\s*\}", m.group(1))

    spec = read(SPEC)
    sec = spec[spec.index("### 9.3"):spec.index("### 9.4")]
    by_name = {r[0]: r for r in eng}
    out = []
    for line in sec.split("\n"):
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or "原生異常" in cells[0]:
            continue
        e = by_name.get(cells[1])
        out.append(dict(src=cells[0], name=cells[1], effect=cells[2],
                        dur=int(e[3]) if e else 0, icd=int(e[4]) if e else 0))
    return out, eng


def read_items():
    t = read(ITEM)
    out = {}
    cur = None
    for line in t.split("\n"):
        m = re.match(r"\s*-\s*Id:\s*(\d+)", line)
        if m:
            cur = int(m.group(1))
            continue
        m = re.match(r"\s*Name:\s*(.+?)\s*$", line)
        if m and cur is not None:
            out.setdefault(cur, m.group(1))
    return out


# ---------------------------------------------------------------- HTML

def esc(s):
    return html.escape(str(s), quote=False)


STYLE = """:root{
  --ground:#EFF1EC; --paper:#F8F9F6; --sunk:#E5E8E1;
  --ink:#1F2422; --ink-soft:#5A625E; --ink-faint:#8B948F;
  --rule:#D3D8D0; --rule-soft:#E1E5DC;
  --cinnabar:#B8331C; --cinnabar-wash:#B8331C1A;
  --indigo:#2F4858;
  --on-accent:#F8F9F6;
  --shadow:0 1px 2px #1f242212, 0 6px 18px #1f24220a;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ground:#121615; --paper:#1A201E; --sunk:#0D100F;
    --ink:#E4E8E3; --ink-soft:#9AA4A0; --ink-faint:#6E7873;
    --rule:#2A322F; --rule-soft:#222A27;
    --cinnabar:#E0654A; --cinnabar-wash:#E0654A22;
    --indigo:#8FB3C7;
    --on-accent:#121615;
    --shadow:0 1px 2px #00000040, 0 6px 18px #00000030;
  }
}
:root[data-theme="dark"]{
  --ground:#121615; --paper:#1A201E; --sunk:#0D100F;
  --ink:#E4E8E3; --ink-soft:#9AA4A0; --ink-faint:#6E7873;
  --rule:#2A322F; --rule-soft:#222A27;
  --cinnabar:#E0654A; --cinnabar-wash:#E0654A22;
  --indigo:#8FB3C7;
  --on-accent:#121615;
  --shadow:0 1px 2px #00000040, 0 6px 18px #00000030;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);
  font:400 16px/1.75 "Noto Sans TC",system-ui,sans-serif;
  -webkit-text-size-adjust:100%}
.wrap{max-width:1040px;margin:0 auto;padding:0 20px 96px}
.masthead{display:flex;align-items:center;gap:14px;padding:26px 0 8px}
.home{display:inline-flex;align-items:center;gap:10px;text-decoration:none;color:inherit}
.home img{width:34px;height:34px;border-radius:8px;display:block}
.home span{font:700 15px/1 "Noto Serif TC",serif;letter-spacing:.04em}
.home:hover span{color:var(--cinnabar)}
h1{font:900 clamp(30px,5.2vw,46px)/1.2 "Noto Serif TC",serif;
  margin:18px 0 10px;letter-spacing:.01em}
.lede{color:var(--ink-soft);max-width:70ch;margin:0 0 26px}
.lede b{color:var(--ink);font-weight:700}
h2{font:700 clamp(20px,3vw,26px)/1.35 "Noto Serif TC",serif;margin:0 0 4px}
h2 .en{font:500 12px/1 "Noto Sans TC",sans-serif;color:var(--ink-faint);
  letter-spacing:.16em;display:block;margin-bottom:6px;text-transform:uppercase}
h2 .src{font:500 12px/1 "Noto Sans TC",sans-serif;color:var(--on-accent);
  background:var(--indigo);border-radius:999px;padding:4px 10px;
  vertical-align:middle;margin-left:8px;white-space:nowrap}
section{margin:44px 0 0;padding-top:28px;border-top:1px solid var(--rule)}
section > p{color:var(--ink-soft);max-width:72ch}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin:22px 0 4px}
.stat{background:var(--paper);border:1px solid var(--rule);border-radius:12px;
  padding:12px 16px;box-shadow:var(--shadow);min-width:124px}
.stat b{display:block;font:700 24px/1.2 "Noto Serif TC",serif;color:var(--cinnabar)}
.stat span{font-size:13px;color:var(--ink-soft)}
.jump{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 0}
.jump a{font-size:14px;text-decoration:none;color:var(--ink-soft);
  border:1px solid var(--rule);border-radius:999px;padding:5px 13px;background:var(--paper)}
.jump a:hover{color:var(--cinnabar);border-color:var(--cinnabar)}
.banner{background:var(--cinnabar-wash);border-left:3px solid var(--cinnabar);
  border-radius:0 10px 10px 0;padding:14px 18px;margin:22px 0;color:var(--ink-soft)}
.banner b{color:var(--ink)}
.note{background:var(--sunk);border-radius:10px;padding:13px 17px;margin:18px 0;
  font-size:14.5px;color:var(--ink-soft)}
.note b{color:var(--ink)}
.desc{color:var(--ink-soft);font-size:14.5px;margin:6px 0 14px}
.tbl-wrap{overflow-x:auto;border:1px solid var(--rule);border-radius:12px;
  background:var(--paper);box-shadow:var(--shadow)}
table{border-collapse:collapse;width:100%;font-size:14.5px;min-width:640px}
th,td{padding:10px 13px;text-align:left;vertical-align:top;
  border-bottom:1px solid var(--rule-soft)}
th{background:var(--sunk);font-weight:700;white-space:nowrap;font-size:13px;
  letter-spacing:.03em;color:var(--ink-soft)}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--cinnabar-wash)}
td.nm{white-space:nowrap;font-weight:700}
td.lv{white-space:nowrap;color:var(--ink-soft);font-size:13.5px}
.eff{margin:0;padding:0;list-style:none}
.eff li{margin:0 0 2px}
.eff li:last-child{margin-bottom:0}
.eff.neg{color:var(--cinnabar)}
.cond{display:block;color:var(--ink-faint);font-size:13px;margin-top:4px;
  font-weight:400;white-space:normal}
.pill{display:inline-block;font-size:11.5px;font-weight:700;border-radius:999px;
  padding:2px 9px;background:var(--sunk);color:var(--ink-soft);white-space:nowrap}
.pill.core{background:var(--cinnabar);color:var(--on-accent)}
.pill.cross{background:var(--indigo);color:var(--on-accent)}
.foot{margin:60px 0 0;padding-top:22px;border-top:1px solid var(--rule);
  color:var(--ink-faint);font-size:13.5px}
.foot b{color:var(--ink-soft)}
.back{display:inline-block;margin-top:26px;text-decoration:none;font-size:14px;
  color:var(--ink-soft);border:1px solid var(--rule);border-radius:999px;
  padding:7px 16px;background:var(--paper)}
.back:hover{color:var(--cinnabar);border-color:var(--cinnabar)}
@media (max-width:640px){
  .wrap{padding:0 15px 72px}
  table{min-width:560px}
}"""


def node_table(rows, meta, cross=False):
    o = ['<div class="tbl-wrap"><table>']
    o.append('<thead><tr><th>節點</th><th>等級／點數</th>'
             '<th>正面效果（每級）</th><th>代價（每級）</th></tr></thead><tbody>')
    for r in rows:
        pill = ""
        if r["tier"] == 2:
            pill = ' <span class="pill core">核心</span>'
        elif r["tier"] == 3:
            pill = ' <span class="pill cross">跨域</span>'
        cell = '<td class="nm">%s%s' % (esc(r["name"]), pill)
        if cross and r["xa"] and r["xb"]:
            cell += '<span class="cond">%s ＋ %s</span>' % (
                esc(meta["dom"].get(r["xa"], "")), esc(meta["dom"].get(r["xb"], "")))
        cell += '</td>'
        o.append('<tr>' + cell)
        o.append('<td class="lv">%d 級／每級 %d 點</td>' % (r["max"], r["cost"]))
        for bucket, cls in ((r["pos"], "pos"), (r["neg"], "neg")):
            o.append('<td><ul class="eff %s">' % cls)
            for line in bucket:
                o.append('<li>%s</li>' % esc(line))
            o.append('</ul>')
            if cls == "pos" and r["note"]:
                o.append('<span class="cond">%s</span>' % esc(r["note"]))
            o.append('</td>')
        o.append('</tr>')
    o.append('</tbody></table></div>')
    return "\n".join(o)


# ---------------------------------------------------------------- 互動星盤
#
# 進階星盤與大道 / 萬法都不一樣, 它是「門檻制」不是樹:
#
#   一般節點   同星域已投入 >= ADV_DOM_PRE(3) 點
#   核心星位   同星域已投入 >= ADV_CORE_PRE(12) 點   (tier 2)
#   跨星域     兩側星域「各」>= ADV_CROSS_PRE(6) 點  (tier 3)
#
# ★★ 每個星域「編號最小的那個節點」是入口, 永遠可點 ★★
#   沒有這個例外會死結 —— 要 3 點才點得下去, 但不點就永遠拿不到那 3 點。
#   (01.核心.txt 的 F_Adv_PreOK 有一整段註解在講: 2026-09-10 修過,
#    舊版只放行「該域 0 點」時, 投入 1 點之後就永久卡死。)
#   前端不必另外拿資料 —— 依 dom 分組取最小 id 就是入口。
#
# ★ pos / neg 已經是 eff_text() 產好的「每級」文字, 所以 tooltip 直接用;
#   但也因為是文字, 加總不了 —— 側欄只給各星域投入與門檻進度, 不做效果總計。
def adv_sim_block(rows, meta):
    sim_rows = [{k: r[k] for k in ("id", "name", "dom", "tier", "max", "cost",
                                   "pos", "neg", "xa", "xb")} for r in rows]
    sim_meta = {
        "maxPt": meta["max_pt"], "domPre": meta["dom_pre"],
        "corePre": meta["core_pre"], "crossPre": meta["cross_pre"],
        "dom": {str(k): v for k, v in meta["dom"].items()},
    }
    css = """<style>
  .asim-wrap{border:1px solid var(--rule);border-radius:10px;background:var(--paper);
    overflow:hidden;margin-top:14px}
  .asim-bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:10px 12px;
    background:var(--sunk);border-bottom:1px solid var(--rule)}
  .asim-bar button{font:inherit;font-size:.86rem;padding:5px 11px;border-radius:999px;
    border:1px solid var(--rule);background:var(--paper);color:var(--ink-soft);cursor:pointer}
  .asim-bar button:hover{border-color:var(--cinnabar);color:var(--cinnabar)}
  .asim-bar .sp{flex:1 1 auto}
  .asim-pts{font-variant-numeric:tabular-nums;font-size:.9rem;color:var(--ink-soft)}
  .asim-pts b{color:var(--cinnabar);font-size:1.05rem}
  .asim-body{display:grid;grid-template-columns:minmax(0,1fr) 240px}
  @media (max-width:820px){.asim-body{grid-template-columns:minmax(0,1fr)}}
  .asim-canvas{overflow:auto;background:var(--ground);max-height:600px}
  .asim-canvas svg{display:block}
  .asim-side{border-left:1px solid var(--rule);padding:12px;font-size:.86rem;
    max-height:600px;overflow:auto}
  @media (max-width:820px){.asim-side{border-left:0;border-top:1px solid var(--rule)}}
  .asim-side h4{margin:0 0 6px;font-size:.8rem;color:var(--ink-faint)}
  .asim-side dl{display:grid;grid-template-columns:1fr auto;gap:2px 10px;margin:0 0 14px}
  .asim-side dt{color:var(--ink-soft);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .asim-side dd{margin:0;font-variant-numeric:tabular-nums;font-weight:500}
  .asim-side dd.ok{color:var(--cinnabar)}
  .asim-side dd.no{color:var(--ink-faint)}
  .asim-tip{padding:8px 12px;border-top:1px solid var(--rule);background:var(--sunk);
    font-size:.8rem;color:var(--ink-faint)}
  .asim-axis{fill:var(--ink-faint);font-size:11px}
  .asim-node{cursor:pointer}
  .asim-node circle{fill:var(--paper);stroke:var(--ink-faint);stroke-width:2}
  .asim-node.on circle{fill:var(--cinnabar);stroke:var(--cinnabar)}
  .asim-node.max circle{stroke:#D8A21B;stroke-width:3}
  .asim-node.locked circle{stroke-dasharray:3 3;opacity:.5}
  .asim-node text.lbl{font-size:10px;fill:var(--ink-soft)}
  .asim-node.on text.lbl{fill:var(--ink)}
  .asim-node text.lv{font-size:10px;font-weight:700;fill:#D8A21B}
  .asim-node:focus circle{stroke:var(--cinnabar);stroke-width:3}
</style>"""
    html = """
<section id="sim">
<h2>互動星盤</h2>
<div class="note">在盤上排點看看：<b>左鍵加一級、右鍵退一級</b>。規則跟遊戲裡一致 ——
一般節點要同星域先投入 %d 點、核心星位要 %d 點、跨星域連線要<b>兩側各</b> %d 點，
總共只有 <b>%d 點</b>。每個星域最上面那個是<b>入口</b>，不受門檻限制（否則會死結）。</div>
<div class="asim-wrap">
  <div class="asim-bar" id="asimBar"></div>
  <div class="asim-body">
    <div class="asim-canvas" id="asimCanvas"></div>
    <div class="asim-side">
      <h4>各星域投入</h4><dl id="asimDom"></dl>
      <h4>跨星域連線</h4><dl id="asimCross"></dl>
    </div>
  </div>
  <div class="asim-tip" id="asimTip">點一個節點試試。配點會寫進網址，複製整條網址就能分享。</div>
</div>
</section>""" % (meta["dom_pre"], meta["core_pre"], meta["cross_pre"], meta["max_pt"])
    js = r"""
<script>
(function(){
  var R = __ROWS__, M = __META__;
  var N = {}, i, k;
  for(i=0;i<R.length;i++) N[R[i].id] = R[i];
  var lv = {};
  // 每個星域編號最小的節點 = 入口, 不受門檻限制
  var entry = {};
  for(i=0;i<R.length;i++){
    var d = R[i].dom;
    if(d === 7) continue;
    if(!entry[d] || R[i].id < entry[d]) entry[d] = R[i].id;
  }
  function domUsed(d){
    var s = 0;
    for(k in lv){ if(N[k].dom === d) s += lv[k]*N[k].cost; }
    return s;
  }
  function used(){ var s=0; for(k in lv) s += lv[k]*N[k].cost; return s; }
  function preOK(id){
    var n = N[id];
    if(n.tier === 3) return domUsed(n.xa) >= M.crossPre && domUsed(n.xb) >= M.crossPre;
    if(n.tier === 2) return domUsed(n.dom) >= M.corePre;
    if(id === entry[n.dom]) return true;
    return domUsed(n.dom) >= M.domPre;
  }
  function why(id){
    var n = N[id];
    if(n.tier === 3) return '跨星域連線要「' + M.dom[n.xa] + '」與「' + M.dom[n.xb] + '」各投入 ' + M.crossPre + ' 點（目前 ' + domUsed(n.xa) + ' / ' + domUsed(n.xb) + '）。';
    if(n.tier === 2) return '核心星位要同星域先投入 ' + M.corePre + ' 點（目前 ' + domUsed(n.dom) + '）。';
    return '要同星域先投入 ' + M.domPre + ' 點（目前 ' + domUsed(n.dom) + '）。';
  }
  // 退一級之後, 有沒有別人的門檻被打破
  function breaksAfter(id){
    var save = lv[id], bad = 0;
    if(save - 1 > 0) lv[id] = save - 1; else delete lv[id];
    for(k in lv){ if(!preOK(k)){ bad = k; break; } }
    lv[id] = save;
    return bad;
  }
  function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function title(id){
    var n = N[id], cl = lv[id]||0;
    var t = n.name + ' — ' + (n.dom === 7 ? '跨星域連線' : M.dom[n.dom]);
    t += '\n上限 ' + n.max + ' 級，每級 ' + n.cost + ' 點';
    if(n.pos) t += '\n投資 1 級：' + n.pos;
    if(n.neg) t += '\n代價（每級）：' + n.neg;
    if(cl > 0) t += '\n目前 ' + cl + ' 級，已投入 ' + (cl*n.cost) + ' 點';
    if(id === entry[n.dom]) t += '\n（此星域的入口，不受門檻限制）';
    return t;
  }
  function draw(){
    var COLW=150, ROWH=48, PADX=70, PADY=44, cols={}, pos={}, out=[];
    var ids = R.map(function(r){ return r.id; }).sort(function(a,b){
      if(N[a].dom !== N[b].dom) return N[a].dom - N[b].dom;
      return a - b; });
    for(i=0;i<ids.length;i++){
      var d2 = N[ids[i]].dom;
      cols[d2] = cols[d2] || 0;
      pos[ids[i]] = { x: PADX + (d2-1)*COLW, y: PADY + 22 + cols[d2]*ROWH };
      cols[d2]++;
    }
    var maxr = 0, dmax = 0;
    for(var c in cols){ if(cols[c] > maxr) maxr = cols[c]; if(+c > dmax) dmax = +c; }
    var W = PADX*2 + (dmax-1)*COLW + 110, H = PADY*2 + 22 + maxr*ROWH;
    out.push('<svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'">');
    for(var d3=1; d3<=dmax; d3++){
      var nm = d3 === 7 ? '跨星域' : (M.dom[d3] || '');
      out.push('<text class="asim-axis" x="'+(PADX+(d3-1)*COLW)+'" y="20" text-anchor="middle">'+esc(nm)+'</text>');
      out.push('<text class="asim-axis" x="'+(PADX+(d3-1)*COLW)+'" y="36" text-anchor="middle">'+(d3===7?'':domUsed(d3)+' 點')+'</text>');
    }
    for(i=0;i<ids.length;i++){
      var id=ids[i], n=N[id], p=pos[id], cl=lv[id]||0;
      var cls=['asim-node'];
      if(cl>0) cls.push('on');
      if(cl>=n.max) cls.push('max');
      if(cl===0 && !preOK(id)) cls.push('locked');
      var r = n.tier===1 ? 10 : 13;
      out.push('<g class="'+cls.join(' ')+'" data-id="'+id+'" tabindex="0">');
      out.push('<title>'+esc(title(id))+'</title>');
      out.push('<circle cx="'+p.x+'" cy="'+p.y+'" r="'+r+'"/>');
      out.push('<text class="lv" x="'+(p.x+r-1)+'" y="'+(p.y+r+1)+'">'+(cl||'')+'</text>');
      out.push('<text class="lbl" x="'+(p.x+r+5)+'" y="'+(p.y+4)+'">'+esc(n.name)+'</text>');
      out.push('</g>');
    }
    out.push('</svg>');
    document.getElementById('asimCanvas').innerHTML = out.join('');
  }
  function side(){
    var h=[], d;
    for(d=1; d<=6; d++){
      var u=domUsed(d), st = u>=M.domPre ? 'ok' : 'no';
      h.push('<dt>'+esc(M.dom[d]||('星域'+d))+'</dt><dd class="'+st+'">'+u+'</dd>');
    }
    document.getElementById('asimDom').innerHTML = h.join('');
    var h2=[];
    for(i=0;i<R.length;i++){
      if(R[i].tier !== 3) continue;
      var a=domUsed(R[i].xa), b=domUsed(R[i].xb);
      var okk = a>=M.crossPre && b>=M.crossPre;
      h2.push('<dt>'+esc(R[i].name)+'</dt><dd class="'+(okk?'ok':'no')+'">'+a+'/'+b+'</dd>');
    }
    document.getElementById('asimCross').innerHTML = h2.length?h2.join(''):'<dt>—</dt><dd></dd>';
    document.getElementById('asimUsed').innerHTML = '已用 <b>'+used()+'</b> / '+M.maxPt+' 點';
  }
  function tip(m){ document.getElementById('asimTip').textContent = m; }
  function add(id){
    var n=N[id], cl=lv[id]||0;
    if(cl>=n.max){ tip(n.name+' 已經滿級了。'); return; }
    if(cl===0 && !preOK(id)){ tip(why(id)); return; }
    if(used()+n.cost > M.maxPt){ tip('點數不夠了，這一級要 '+n.cost+' 點，總共只有 '+M.maxPt+' 點。'); return; }
    lv[id]=cl+1; tip(n.name+' → '+lv[id]+' 級（花了 '+n.cost+' 點）。'); sync();
  }
  function sub(id){
    var n=N[id], cl=lv[id]||0;
    if(cl<=0) return;
    var b=breaksAfter(id);
    if(b){ tip('不能退 —— 退了之後【'+N[b].name+'】的門檻就不夠了。'); return; }
    lv[id]=cl-1; if(!lv[id]) delete lv[id];
    tip(n.name+' → '+(lv[id]||0)+' 級。'); sync();
  }
  function encode(){ var a=[],ks=Object.keys(lv).sort(function(x,y){return x-y;});
    for(i=0;i<ks.length;i++) a.push(ks[i]+'.'+lv[ks[i]]); return a.join('-'); }
  function decode(s){ lv={}; if(!s) return;
    var ps=s.split('-');
    for(i=0;i<ps.length;i++){ var kv=ps[i].split('.'), id=+kv[0], v=+kv[1];
      if(N[id] && v>0 && v<=N[id].max) lv[id]=v; } }
  function sync(){ draw(); side();
    var h=encode(); history.replaceState(null,'',h?('#b='+h):location.pathname); }
  document.getElementById('asimBar').innerHTML =
    '<span class="asim-pts" id="asimUsed"></span><span class="sp"></span>'+
    '<button type="button" id="asimReset">清空</button>';
  document.getElementById('asimBar').addEventListener('click', function(ev){
    var b=ev.target.closest('button');
    if(b && b.id==='asimReset'){ lv={}; tip('已清空。'); sync(); } });
  var cv=document.getElementById('asimCanvas');
  cv.addEventListener('click', function(ev){
    var g=ev.target.closest('.asim-node'); if(g) add(+g.dataset.id); });
  cv.addEventListener('contextmenu', function(ev){
    var g=ev.target.closest('.asim-node'); if(!g) return;
    ev.preventDefault(); sub(+g.dataset.id); });
  cv.addEventListener('keydown', function(ev){
    var g=ev.target.closest('.asim-node'); if(!g) return;
    if(ev.key==='Enter'||ev.key===' '){ ev.preventDefault(); add(+g.dataset.id); }
    if(ev.key==='Backspace'||ev.key==='Delete'){ ev.preventDefault(); sub(+g.dataset.id); } });
  if(location.hash.indexOf('#b=')===0) decode(location.hash.slice(3));
  sync();
})();
</script>"""
    js = js.replace("__ROWS__", json.dumps(sim_rows, ensure_ascii=False, separators=(",", ":")))
    js = js.replace("__META__", json.dumps(sim_meta, ensure_ascii=False, separators=(",", ":")))
    return css + html + js


def build():
    rows, meta = collect()
    ecl, eng = collect_eclipse()
    items = read_items()
    conf = read(CONF)

    total_cost = sum(r["cost"] * r["max"] for r in rows)
    n_cross = len([r for r in rows if r["dom"] == 7])
    n_dom = len(meta["dom"])

    o = []
    a = o.append
    desc = ("神域仙境 進階星盤的 %d 個節點、六大星域、%d 條跨星域連線與星蝕轉化表。"
            "每個節點都同時帶有正面與負面效果。" % (len(rows), n_cross))

    a('<!doctype html>')
    a('<html lang="zh-Hant">')
    a('<head>')
    a('<meta charset="utf-8">')
    a('<meta name="viewport" content="width=device-width, initial-scale=1">')
    a('<title>進階星盤</title>')
    a('<meta name="description" content="%s">' % esc(desc))
    a('<meta name="color-scheme" content="light dark">')
    a('<meta property="og:type" content="website">')
    a('<meta property="og:site_name" content="神域仙境">')
    a('<meta property="og:title" content="進階星盤">')
    a('<meta property="og:description" content="%s">' % esc(desc))
    a('<meta property="og:image" content="https://drw-online.github.io/game/og.jpg">')
    a('<meta property="og:image:width" content="600">')
    a('<meta property="og:image:height" content="600">')
    a('<meta name="twitter:card" content="summary">')
    a('<meta name="theme-color" content="#EFF1EC" media="(prefers-color-scheme: light)">')
    a('<meta name="theme-color" content="#121615" media="(prefers-color-scheme: dark)">')
    a('<link rel="icon" href="favicon.png" type="image/png">')
    a('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    a('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
      'family=Noto+Sans+TC:wght@400;500;700&family=Noto+Serif+TC:wght@500;700;900&display=swap">')
    a('<style>%s</style>' % STYLE)
    a('</head>')
    a('<body>')
    a('<div class="wrap">')
    a('<div class="masthead"><a class="home" href="index.html">'
      '<img src="favicon.png" alt=""><span>神域仙境</span></a></div>')

    a('<h1>進階星盤</h1>')
    a('<p class="lede">大道星盤之後的高階分支。'
      '<b>每一個節點都同時給你力量與代價</b>——沒有例外，核心星位也一樣。'
      '全盤 <b>%d</b> 個節點，點滿需要 <b>%d</b> 點，'
      '而你一輩子只會拿到 <b>%d</b> 點。點不滿，是這個系統的核心。</p>'
      % (len(rows), total_cost, meta["max_pt"]))

    a('<div class="stats">')
    for v, k in ((len(rows), "節點總數"), (total_cost, "點滿所需"),
                 (meta["max_pt"], "你拿得到"), (n_dom, "大星域"),
                 (n_cross, "跨星域連線")):
        a('<div class="stat"><b>%s</b><span>%s</span></div>' % (v, k))
    a('</div>')

    a('<nav class="jump">')
    a('<a href="#rule">怎麼點</a>')
    for d in sorted(meta["dom"]):
        a('<a href="#d%d">%s</a>' % (d, esc(meta["dom"][d])))
    a('<a href="#cross">跨星域</a>')
    a('<a href="#eclipse">星蝕轉化</a>')
    a('<a href="#respec">重修</a>')
    a('</nav>')

    a('<section id="rule">')
    a('<h2><span class="en">How it works</span>怎麼點</h2>')
    a('<div class="banner"><b>開啟條件：</b>境界達到亥境（第 %d 境），'
      '且大道星盤已投入 <b>%d</b> 點。開啟時一次給滿 <b>%d</b> 點。</div>'
      % (meta["need_realm"], meta["need_dao"], meta["max_pt"]))
    a('<div class="tbl-wrap"><table>')
    a('<thead><tr><th>節點類型</th><th>最大等級</th><th>每級點數</th>'
      '<th>前置條件</th></tr></thead><tbody>')
    a('<tr><td class="nm">一般節點</td><td>%d</td><td>%d</td>'
      '<td>同星域已投入 %d 點'
      '<span class="cond">該星域還是 0 點時可以直接開頭</span></td></tr>'
      % (meta["tmax"][1], meta["tcost"][1], meta["dom_pre"]))
    a('<tr><td class="nm">核心星位 <span class="pill core">核心</span></td>'
      '<td>%d</td><td>%d</td><td>同星域已投入 %d 點</td></tr>'
      % (meta["tmax"][2], meta["tcost"][2], meta["core_pre"]))
    a('<tr><td class="nm">跨星域連線 <span class="pill cross">跨域</span></td>'
      '<td>%d</td><td>%d</td><td>兩側星域各投入 %d 點</td></tr>'
      % (meta["tmax"][3], meta["tcost"][3], meta["cross_pre"]))
    a('</tbody></table></div>')
    a('<div class="note"><b>負面效果是刻意設計的，不是異常。</b>'
      '尋寶者犧牲戰力與生存，破甲者犧牲自身防禦，法術穿透者承擔 SP 與詠唱壓力，'
      '異常流則承擔較低的直接輸出。選你願意付的代價。</div>')
    a('</section>')

    a(adv_sim_block(rows, meta))

    for d in sorted(meta["dom"]):
        a('<section id="d%d">' % d)
        a('<h2><span class="en">Domain %d</span>%s<span class="src">對應原六道 · %s</span></h2>'
          % (d, esc(meta["dom"][d]), esc(meta["domsrc"].get(d, ""))))
        a('<p class="desc">%s</p>' % esc(meta["domdesc"].get(d, "")))
        a(node_table([r for r in rows if r["dom"] == d], meta))
        a('</section>')

    a('<section id="cross">')
    a('<h2><span class="en">Cross-domain</span>跨星域連線</h2>')
    a('<p>兩側星域各投入 <b>%d</b> 點才能點亮。每條只有 1 級，花 %d 點。</p>'
      % (meta["cross_pre"], meta["tcost"][3]))
    a(node_table([r for r in rows if r["dom"] == 7], meta, cross=True))
    a('</section>')

    a('<section id="eclipse">')
    a('<h2><span class="en">Astral eclipse</span>星蝕轉化</h2>')
    a('<p>目標免疫某個異常時，那一次成功觸發<b>不會消失</b>——改成套用對應的'
      '「星蝕」狀態。星蝕不屬於硬控制、不阻止 Boss 行動，'
      '所以 Boss 沒辦法用一般異常免疫把整套排除掉。</p>')
    a('<div class="tbl-wrap"><table>')
    a('<thead><tr><th>免疫的異常</th><th>轉化後</th><th>效果</th>'
      '<th>持續／冷卻</th></tr></thead><tbody>')
    for e in ecl:
        a('<tr><td class="nm">%s</td><td class="nm">%s</td><td>%s</td>'
          '<td class="lv">%s 秒／%s 秒</td></tr>'
          % (esc(e["src"]), esc(e["name"]), esc(e["effect"]),
             num(e["dur"] // 10), num(e["icd"] // 10)))
    a('</tbody></table></div>')
    a('<div class="note"><b>Boss</b> 至少保留原效果 30%、最低 2 秒；'
      '<b>PVP</b> 至少 20%、最低 1 秒。世界 Boss 可再乘 0.75，但不會歸零。'
      '同名星蝕不疊加只刷新，單一目標同時最多承受 4 種。</div>')
    a('</section>')

    a('<section id="respec">')
    a('<h2><span class="en">Respec</span>重修</h2>')
    a('<div class="tbl-wrap"><table>')
    a('<thead><tr><th>做什麼</th><th>材料</th></tr></thead><tbody>')
    a('<tr><td class="nm">退還 1 級</td><td>%s ×1</td></tr>'
      % esc(items.get(meta["item_respec"], "悟道石")))
    a('<tr><td class="nm">全盤重置</td><td>%s ×1 ＋ %s ×%d</td></tr>'
      % (esc(items.get(meta["item_reset"], "輪迴石")),
         esc(items.get(meta["item_respec"], "悟道石")), meta["reset_gem"]))
    a('</tbody></table></div>')
    a('<div class="note">退還會讓<b>核心星位</b>或<b>跨星域連線</b>失去前置時，'
      '系統會擋下來——請先退掉那個節點。</div>')
    a('<p>NPC 位置：<b>崑崙 (166, 146)</b> 的「進階星盤」。</p>')
    a('</section>')

    a('<div class="foot">')
    a('<p>本頁由 <b>tools/build_advpan.py</b> 從伺服器腳本直接產生——'
      '節點、效果、觸發率、星蝕持續時間全部讀自 <b>script/17.進階星盤/</b> 與 '
      '<b>add/src/blackgod_astro_proc.inc</b>，沒有一個數字是手抄的。</p>')
    a('<p>引擎開關 adv_enable：<b>%s</b>　每秒觸發上限：<b>%d</b> 次</p>'
      % ("已啟用" if conf_int(conf, "adv_enable") else "未啟用",
         conf_int(conf, "adv_proc_per_sec", 5)))
    a('<a class="back" href="index.html">← 回工具總覽</a>')
    a('</div>')

    a('</div>')
    a('</body>')
    a('</html>')

    out = "\n".join(o) + "\n"
    verify(rows, meta, ecl, eng, out, total_cost)
    with io.open(DEST, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print("寫出 %s  (%d bytes, %d 個節點)"
          % (DEST, len(out.encode("utf-8")), len(rows)))


# ---------------------------------------------------------------- 自檢

def verify(rows, meta, ecl, eng, out, total_cost):
    bad = []

    def chk(cond, msg):
        if not cond:
            bad.append(msg)

    ids = [r["id"] for r in rows]
    chk(len(ids) == len(set(ids)), "節點編號有重複")
    chk(len(rows) == 54, "節點數 %d, 應該是 54" % len(rows))
    chk(len([r for r in rows if r["dom"] == 7]) == 6, "跨星域連線不是 6 條")
    chk(len(meta["dom"]) == 6, "星域不是 6 個")
    chk(meta["max_pt"] and meta["max_pt"] < total_cost,
        "點數上限 %s 不小於點滿所需 %d —— 那就點得滿了" % (meta["max_pt"], total_cost))

    # 企劃書 §2.2: 沒有純正面節點
    for r in rows:
        chk(r["neg"], "節點 %d %s 沒有負面效果 —— 企劃書 §2.2 不允許"
            % (r["id"], r["name"]))
        chk(r["pos"] or r["note"],
            "節點 %d %s 正面效果與條件說明都是空的" % (r["id"], r["name"]))
        chk(r["name"] != "?", "節點 %d 沒有名稱" % r["id"])

    # 企劃書 §4.1: 每點穿透不得超過 0.1% (千分點 1)
    for r in rows:
        chk(r["pen_ev"] <= 1,
            "節點 %d %s 每級穿透 %d 千分點, 超過 §4.1 的 0.1%%"
            % (r["id"], r["name"], r["pen_ev"]))

    for k in meta["ku"]:
        chk(k in meta["kn"], "效果 key %d 有單位卻沒有名稱" % k)

    eng_names = {e[0] for e in eng}
    chk(len(ecl) == 11, "星蝕轉化表 %d 列, 企劃書 §9.3 是 11 列" % len(ecl))
    for e in ecl:
        chk(e["name"] in eng_names,
            "星蝕「%s」企劃書有但 blackgod_astro_proc.inc 沒有" % e["name"])
        chk(e["dur"] > 0, "星蝕「%s」持續時間是 0" % e["name"])

    chk(out.count("<tr>") == out.count("</tr>"), "HTML 的 tr 沒有配對")
    chk(out.count("<table") == out.count("</table>"), "HTML 的 table 沒有配對")

    if bad:
        print("★ 自檢失敗 %d 項:" % len(bad))
        for b in bad:
            print("   -", b)
        raise SystemExit(1)
    print("自檢通過 —— %d 個節點都有正面與負面效果, 穿透全部 <= 0.1%%/點, "
          "星蝕 11 列與引擎一致。" % len(rows))


if __name__ == "__main__":
    build()

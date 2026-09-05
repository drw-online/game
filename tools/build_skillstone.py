# -*- coding: utf-8 -*-
"""
技能石技能表產生器 —— 產生 skills/*.png 與 skillstone.html, 跑完自己驗證一次。

用法(需要 Pillow):

    python tools/build_skillstone.py

--------------------------------------------------------------------------
來源
--------------------------------------------------------------------------
  5.技能圖片/技能書對照表.csv          1095 本技能書 (物品ID / 階級 / 技能代號 / 上限 / 職業 / 圖示)
  5.技能圖片/技能圖示對應表.csv        中文名稱與英文名 (以技能代號 join)
  5.技能圖片/*.bmp                     24x24 技能圖示
  2.開機擋/db/import/blackgod/item_skillbook.yml   真正的物品 DB, 用來驗證 CSV 沒過期
  2.開機擋/script/04.系統/05.技能書.txt            $@SKB_* 號段表 = 伺服器實際的抽取池
  2.開機擋/conf/atcommands.yml                     @job 說明表 = 遊戲內的中文職業名
  1.原始碼/src/common/mmo.hpp                      enum e_job, 把 CSV 的英文職業接到職業編號

--------------------------------------------------------------------------
為什麼要對這麼多份來源
--------------------------------------------------------------------------
★ 階級一律以 技能書對照表 的「階級」欄為準, 不看「原始分類」也不用物品 ID
  前綴推 —— 2026-08-16 有 46 本二轉技能原本被歸在 1 轉(成因見
  05.技能書.txt 檔頭)。兩欄目前有 46 筆不一致, 那是正確的歷史痕跡。

★ 真正決定「哪一階開得到哪幾本」的是 05.技能書.txt OnInit 的 $@SKB_BASE /
  $@SKB_LEN 號段表, 不是 CSV。verify() 拿號段表反過來核對 CSV 的每一階
  —— 號段表改了而 CSV 沒重出的話, 這裡會當場失敗。

★ 圖示檔名用 技能書對照表 的「圖示」欄, 不用 技能圖示對應表 的「圖片檔名」。
  後者有兩筆是空的(BA_FROSTJOKER / CG_SPECIALSINGER), 前者已經填了借用的
  圖(ba_dissonance / cg_moonlit), 1095 支一個都不缺。

★ 中文名稱有兩支在 技能圖示對應表 是空的(BA_FROSTJOKER / LK_CONCENTRATION),
  退回用 技能書對照表 的物品名稱去掉「技能書」三個字。

★ 洋紅 (255,0,255) 是去背色, 1093 個圖示裡有 824 個用它。其餘 269 個本來
  就是不透明的深色底 —— 那是遊戲裡的原樣, 不要另外去背。
"""
import os, re, csv, io, html as H

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
WEB  = os.path.dirname(HERE)
ROOT = r"H:\91.神域仙境"

SKILLPIC = os.path.join(ROOT, r"5.技能圖片")
CSV_BOOK = os.path.join(SKILLPIC, "技能書對照表.csv")
CSV_ICON = os.path.join(SKILLPIC, "技能圖示對應表.csv")
YML_BOOK = os.path.join(ROOT, r"2.開機擋\db\import\blackgod\item_skillbook.yml")
TXT_BOOK = os.path.join(ROOT, r"2.開機擋\script\04.系統\05.技能書.txt")
YML_ATCM = os.path.join(ROOT, r"2.開機擋\conf\atcommands.yml")
HPP_JOB  = os.path.join(ROOT, r"1.原始碼\src\common\mmo.hpp")

PNG  = os.path.join(WEB, "skills")
DEST = os.path.join(WEB, "skillstone.html")

MAGENTA = (255, 0, 255)

# 技能書對照表寫 Supernovice, e_job 叫 JOB_SUPER_NOVICE。目前只有這一筆對不上。
JOB_ALIAS = {"Supernovice": "JOB_SUPER_NOVICE"}


def read(path, enc="utf-8"):
    with io.open(path, encoding=enc, errors="strict") as f:
        return f.read()


# ------------------------------------------------------------------ 來源
def load_books():
    """技能書對照表 -> 1095 筆, 保持 CSV 原順序(= 物品 ID 順序)。"""
    with io.open(CSV_BOOK, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_icons():
    """技能圖示對應表 -> {技能代號: 該列}。"""
    with io.open(CSV_ICON, encoding="utf-8-sig") as f:
        return {r["技能代號"]: r for r in csv.DictReader(f)}


def load_segments():
    """05.技能書.txt 的 $@SKB_* -> {階級: [(起始ID, 本數), ...]}。"""
    txt = read(TXT_BOOK)

    def arr(name):
        m = re.search(r"setarray\s+\$@%s\[0\],([^;]+);" % name, txt)
        if not m:
            raise SystemExit("05.技能書.txt 找不到 $@%s" % name)
        return [int(x) for x in re.findall(r"\d+", re.sub(r"//.*", "", m.group(1)))]

    tier, base, ln = arr("SKB_TIER"), arr("SKB_BASE"), arr("SKB_LEN")
    if not (len(tier) == len(base) == len(ln)):
        raise SystemExit("$@SKB_TIER / BASE / LEN 長度不一致")
    seg = {}
    for t, b, n in zip(tier, base, ln):
        seg.setdefault(t, []).append((b, n))
    return seg


def load_itemdb():
    """item_skillbook.yml -> {物品ID: (AegisName, Name)}。"""
    s = read(YML_BOOK)
    ids = [int(x) for x in re.findall(r"^\s*- Id:\s*(\d+)", s, re.M)]
    aegis = re.findall(r"^\s*AegisName:\s*(\S+)", s, re.M)
    names = re.findall(r'^\s*Name:\s*"(.*?)"', s, re.M)
    if not (len(ids) == len(aegis) == len(names)):
        raise SystemExit("item_skillbook.yml 的 Id / AegisName / Name 筆數不一致")
    return dict(zip(ids, zip(aegis, names)))


def load_jobnames():
    """回 (e_job 的 {JOB_XXX: 編號}, @job 說明表的 {編號: 中文名})。

    中文名一律照 conf/atcommands.yml —— 玩家 @help job 看到的就是這一份,
    52.造型師.txt 的選單也是照它抄的。用 jobname() 會回英文。
    """
    src = read(HPP_JOB)
    body = src[src.find("enum e_job"):]
    body = body[:body.find("};")]
    jid, nxt = {}, 0
    for line in body.splitlines()[1:]:
        line = line.split("//")[0].strip().rstrip(",")
        m = re.match(r"^(JOB_\w+)\s*(?:=\s*(\d+))?$", line)
        if not m:
            continue
        if m.group(2) is not None:
            nxt = int(m.group(2))
        jid[m.group(1)] = nxt
        nxt += 1

    t = read(YML_ATCM)
    k = t.find("Command: jobchange")
    seg = t[k:t.find("- Command:", k + 10)]
    cn = {int(a): b for a, b in re.findall(r"(\d+)\s+([^\s0-9]+)", seg)}
    return jid, cn


def job_cn(eng, jid, cn):
    key = JOB_ALIAS.get(eng, "JOB_" + eng.upper())
    if key not in jid or jid[key] not in cn:
        raise SystemExit("職業對不到中文名: %s (%s)" % (eng, key))
    return cn[jid[key]]


def parse_sources():
    books, icons, itemdb = load_books(), load_icons(), load_itemdb()
    jid, cn = load_jobnames()

    rows = []
    for b in books:
        code = b["技能代號"]
        ic = icons.get(code, {})
        name = (ic.get("中文名稱") or "").strip()
        if not name:
            # 圖示對應表沒中文名的兩支, 退回物品名稱(去掉「技能書」)
            name = re.sub(r"技能書$", "", b["物品名稱"])
        rows.append(dict(
            id=int(b["物品ID"]),
            tier=int(b["階級"][0]),
            code=code,
            name=name,
            en=(ic.get("技能說明") or "").strip(),
            job=b["職業"],
            jobcn=job_cn(b["職業"], jid, cn),
            maxlv=int(b["技能上限"]),
            icon=b["圖示"],
        ))
    return rows, itemdb, load_segments()


# ------------------------------------------------------------------ 圖示
def render_icons(rows):
    """洋紅去背轉 PNG。回 ({圖示名: (w, h)}, 有去背的張數)。"""
    os.makedirs(PNG, exist_ok=True)
    sizes, keyed = {}, 0
    for icon in sorted({r["icon"] for r in rows}):
        im = Image.open(os.path.join(SKILLPIC, icon + ".bmp")).convert("RGBA")
        px = im.load()
        hit = False
        for y in range(im.height):
            for x in range(im.width):
                if px[x, y][:3] == MAGENTA:
                    px[x, y] = (0, 0, 0, 0)
                    hit = True
        im.save(os.path.join(PNG, icon + ".png"), optimize=True)
        sizes[icon] = im.size
        keyed += hit
    return sizes, keyed


# ------------------------------------------------------------------ 頁面
PAGE = u"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>技能石技能表</title>
<meta name="description" content="神域仙境 1/2/3/4 轉技能石各自開得到哪些技能，共 __TOTAL__ 支，可依階級、職業與名稱查詢。">
<meta name="color-scheme" content="light dark">
<meta property="og:type" content="website">
<meta property="og:site_name" content="神域仙境">
<meta property="og:title" content="技能石技能表">
<meta property="og:description" content="神域仙境 1/2/3/4 轉技能石各自開得到哪些技能，共 __TOTAL__ 支，可依階級、職業與名稱查詢。">
<meta property="og:image" content="https://drw-online.github.io/game/og.jpg">
<meta property="og:image:width" content="600">
<meta property="og:image:height" content="600">
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="#EFF1EC" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#121615" media="(prefers-color-scheme: dark)">
<link rel="icon" href="favicon.png" type="image/png">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Noto+Serif+TC:wght@500;700;900&display=swap">
<style>
:root{
  --ground:#EFF1EC; --paper:#F8F9F6; --sunk:#E5E8E1;
  --ink:#1F2422; --ink-soft:#5A625E; --ink-faint:#8B948F;
  --rule:#D3D8D0; --rule-soft:#E1E5DC;
  --cinnabar:#B8331C; --cinnabar-wash:#B8331C1A;
  --on-accent:#F8F9F6; --focus:#B8331C;
  --shadow:0 1px 2px #1f242212, 0 6px 18px #1f24220a;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ground:#121615; --paper:#1A201E; --sunk:#0D100F;
    --ink:#E4E8E3; --ink-soft:#9AA4A0; --ink-faint:#6E7873;
    --rule:#2A322F; --rule-soft:#222A27;
    --cinnabar:#E0654A; --cinnabar-wash:#E0654A22;
    --on-accent:#121615; --focus:#E0654A;
    --shadow:0 1px 2px #00000040, 0 6px 18px #00000030;
  }
}
:root[data-theme="dark"]{
  --ground:#121615; --paper:#1A201E; --sunk:#0D100F;
  --ink:#E4E8E3; --ink-soft:#9AA4A0; --ink-faint:#6E7873;
  --rule:#2A322F; --rule-soft:#222A27;
  --cinnabar:#E0654A; --cinnabar-wash:#E0654A22;
  --on-accent:#121615; --focus:#E0654A;
  --shadow:0 1px 2px #00000040, 0 6px 18px #00000030;
}
*{box-sizing:border-box}
body{margin:0; background:var(--ground); color:var(--ink);
  font-family:"Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,sans-serif;
  font-size:15px; line-height:1.65; -webkit-font-smoothing:antialiased}
.wrap{max-width:1180px; margin:0 auto; padding:0 20px 76px}
.masthead{padding:44px 0 26px; border-bottom:1px solid var(--rule)}
.home{display:inline-flex; align-items:center; gap:11px; text-decoration:none; margin-bottom:12px}
.home img{width:46px; height:auto; flex:none; display:block}
.home span{font-size:12px; letter-spacing:.34em; color:var(--cinnabar); font-weight:700}
.home:hover span{text-decoration:underline; text-underline-offset:5px}
.home:focus-visible{outline:2px solid var(--focus); outline-offset:3px; border-radius:3px}
h1{margin:0; font-family:"Noto Serif TC",serif; font-weight:900;
  font-size:clamp(32px,6vw,48px); line-height:1.12; letter-spacing:.07em; text-wrap:balance}
.lede{margin:14px 0 0; max-width:62ch; color:var(--ink-soft)}
.lede b{color:var(--ink); font-weight:500}

.bar{margin-top:30px; display:flex; flex-wrap:wrap; align-items:center; gap:10px}
.chip{padding:5px 14px; background:var(--paper); color:var(--ink-soft); border:1px solid var(--rule);
  border-radius:100px; font:inherit; font-size:13px; letter-spacing:.06em; cursor:pointer;
  transition:background .12s ease, border-color .12s ease, color .12s ease}
.chip em{font-style:normal; font-variant-numeric:tabular-nums; opacity:.72; margin-left:3px}
.chip:hover{border-color:var(--ink-faint)}
.chip:focus-visible{outline:2px solid var(--focus); outline-offset:2px}
.chip[aria-pressed="true"]{background:var(--cinnabar); border-color:var(--cinnabar); color:var(--on-accent)}
.bar2{margin-top:12px; display:flex; flex-wrap:wrap; align-items:center; gap:12px}
.search{flex:1 1 260px; min-width:0}
.search input{width:100%; padding:11px 14px; font:inherit; font-size:14px; color:var(--ink);
  background:var(--paper); border:1px solid var(--rule); border-radius:6px}
.search input::placeholder{color:var(--ink-faint)}
.search input:focus-visible{outline:2px solid var(--focus); outline-offset:2px; border-color:var(--cinnabar)}
select{padding:11px 12px; font:inherit; font-size:14px; color:var(--ink);
  background:var(--paper); border:1px solid var(--rule); border-radius:6px; max-width:100%}
select:focus-visible{outline:2px solid var(--focus); outline-offset:2px; border-color:var(--cinnabar)}
.count{font-size:13px; color:var(--ink-faint); font-variant-numeric:tabular-nums; white-space:nowrap}
.count b{color:var(--cinnabar); font-weight:700}
.odds{margin:14px 0 0; font-size:13.5px; color:var(--ink-soft); font-variant-numeric:tabular-nums}

.grid{list-style:none; margin:18px 0 0; padding:0;
  display:grid; gap:10px; grid-template-columns:repeat(auto-fill,minmax(268px,1fr))}
.sk{display:grid; grid-template-columns:32px 1fr; gap:2px 12px; align-items:start;
  padding:12px 14px 11px; background:var(--paper);
  border:1px solid var(--rule-soft); border-radius:6px; box-shadow:var(--shadow)}
.sk[hidden]{display:none}
.sk img{grid-row:1 / span 3; width:32px; height:32px; image-rendering:pixelated;
  image-rendering:-moz-crisp-edges; image-rendering:crisp-edges; border-radius:3px}
.nm{font-size:14.5px; font-weight:500; line-height:1.35}
.tag{font-size:11px; letter-spacing:.06em; font-weight:700; color:var(--cinnabar);
  background:var(--cinnabar-wash); border-radius:100px; padding:1px 8px; margin-left:7px;
  vertical-align:1.5px; white-space:nowrap}
.en{font-size:12px; color:var(--ink-faint); line-height:1.4}
.meta{margin-top:5px; display:flex; flex-wrap:wrap; gap:4px 10px;
  font-size:11.5px; color:var(--ink-faint); letter-spacing:.03em}
.meta i{font-style:normal; color:var(--ink-soft)}
.meta code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:11px; color:var(--ink-soft)}
.meta em{font-style:normal; font-variant-numeric:tabular-nums}

.empty{margin:34px 0 0; color:var(--ink-faint); font-size:14px}
.empty[hidden]{display:none}

.foot{margin-top:48px; padding-top:20px; border-top:1px solid var(--rule);
  font-size:12.5px; line-height:1.85; color:var(--ink-faint); max-width:76ch}
.foot b{color:var(--ink-soft); font-weight:500}
.foot p{margin:0 0 10px}
.back{display:inline-block; margin-top:6px; color:var(--cinnabar); font-size:13px; letter-spacing:.06em; text-decoration:none}
.back:hover{text-decoration:underline; text-underline-offset:5px}
.back:focus-visible{outline:2px solid var(--focus); outline-offset:3px; border-radius:2px}
@media (max-width:640px){
  .masthead{padding:32px 0 22px}
  .grid{grid-template-columns:1fr}
}
@media (prefers-reduced-motion: reduce){ *{transition:none !important} }
</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <a class="home" href="index.html">
      <img src="logo.webp" width="440" height="440" alt="" decoding="async">
      <span>← 神域仙境 玩家工具</span>
    </a>
    <h1>技能石技能表</h1>
    <p class="lede">四種技能石各自開得到的技能，合計 <b>__TOTAL__ 支</b>。開石頭是<b>同階均勻隨機</b>一本 —— 同一階裡每一支被抽到的機率都一樣。</p>
  </header>

  <div class="bar" id="tiers">
    <button class="chip" data-t="" aria-pressed="true">全部</button>
__CHIPS__
  </div>

  <div class="bar2">
    <div class="search">
      <input id="q" type="search" placeholder="輸入技能名稱、英文名、技能代號或技能書編號…" autocomplete="off" aria-label="搜尋技能">
    </div>
    <label class="count" for="job">職業</label>
    <select id="job" aria-label="依職業篩選">
      <option value="">全部職業</option>
__JOBOPTS__
    </select>
    <div class="count"><b id="shown">__TOTAL__</b> / __TOTAL__ 支</div>
  </div>

  <p class="odds" id="odds"></p>

  <ul class="grid" id="grid">
__CARDS__
  </ul>
  <p class="empty" id="empty" hidden>沒有符合的技能。</p>

  <footer class="foot">
    <p><b>階級以伺服器實際的抽取號段為準。</b>有幾支技能「原本是幾轉」與這裡的階級不一樣 —— 以本表為準，那才是開該階石頭實際會抽到的池子。</p>
    <p><b>上限是那支技能自己的最高等級。</b>一本技能書加 1 級，加到上限為止。</p>
    <a class="back" href="index.html">← 回神域仙境玩家工具</a>
  </footer>
</div>
<script>
(function(){
  var q     = document.getElementById('q'),
      job   = document.getElementById('job'),
      shown = document.getElementById('shown'),
      empty = document.getElementById('empty'),
      odds  = document.getElementById('odds'),
      chips = [].slice.call(document.querySelectorAll('#tiers .chip')),
      cards = [].slice.call(document.querySelectorAll('.sk')),
      SIZE  = __SIZES__,
      tier  = '';
  function apply(){
    var s = q.value.trim().toLowerCase(), j = job.value, n = 0;
    for (var i = 0; i < cards.length; i++){
      var c = cards[i];
      var hit = (!tier || c.dataset.t === tier)
             && (!j || c.dataset.j === j)
             && (!s || c.dataset.k.indexOf(s) !== -1);
      c.hidden = !hit;
      if (hit) n++;
    }
    shown.textContent = n;
    empty.hidden = n !== 0;
    odds.textContent = tier
      ? tier + '轉技能石的池子共 ' + SIZE[tier] + ' 支，每一支開出來的機率是 '
        + (100 / SIZE[tier]).toFixed(2) + '%。'
      : '四階合計 ' + cards.length + ' 支。選一個階級可以看該階的抽中機率。';
  }
  chips.forEach(function(b){
    b.addEventListener('click', function(){
      tier = b.dataset.t;
      chips.forEach(function(o){ o.setAttribute('aria-pressed', o === b ? 'true' : 'false'); });
      apply();
    });
  });
  q.addEventListener('input', apply);
  job.addEventListener('change', apply);
  apply();
})();
</script>
</body>
</html>
"""

CARD = (u'<li class="sk" data-t="{tier}" data-j="{job}" data-k="{key}">'
        u'<img src="skills/{icon}.png" width="32" height="32" alt="" loading="lazy" decoding="async">'
        u'<span class="nm">{name}<span class="tag">{tier}轉</span></span>'
        u'<span class="en">{en}</span>'
        u'<span class="meta"><i>{jobcn}</i><em>上限 Lv{maxlv}</em>'
        u'<code>{code}</code><em>#{id}</em></span></li>')


def build_page(rows, tiers):
    total = len(rows)

    chips = "\n".join(
        '    <button class="chip" data-t="%d" aria-pressed="false">%d轉 <em>%d</em></button>'
        % (t, t, tiers[t]) for t in sorted(tiers))

    jobs = sorted({(r["jobcn"], r["job"]) for r in rows})
    jobopts = "\n".join('      <option value="%s">%s</option>' % (H.escape(e), H.escape(c))
                        for c, e in jobs)

    cards = []
    for r in rows:
        key = " ".join([r["name"], r["en"], r["code"], r["job"], r["jobcn"], str(r["id"])]).lower()
        cards.append("    " + CARD.format(
            tier=r["tier"], job=H.escape(r["job"]), key=H.escape(key),
            icon=r["icon"], name=H.escape(r["name"]), en=H.escape(r["en"]),
            jobcn=H.escape(r["jobcn"]), maxlv=r["maxlv"], code=r["code"], id=r["id"]))

    sizes = "{" + ",".join('"%d":%d' % (t, tiers[t]) for t in sorted(tiers)) + "}"

    out = (PAGE.replace("__CHIPS__", chips)
               .replace("__JOBOPTS__", jobopts)
               .replace("__CARDS__", "\n".join(cards))
               .replace("__SIZES__", sizes)
               .replace("__TOTAL__", str(total)))
    with io.open(DEST, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    return out


# ------------------------------------------------------------------ 驗證
def verify(rows, itemdb, seg, sizes, out):
    ok = True

    def chk(cond, msg):
        nonlocal ok
        ok = ok and bool(cond)
        print("  %s  %s" % ("ok  " if cond else "FAIL", msg))

    print("  ----  skillstone.html")

    # 1. CSV 與真正的物品 DB 必須一模一樣 —— CSV 過期的話這裡先爆
    ids = [r["id"] for r in rows]
    chk(len(ids) == len(set(ids)), "技能書編號唯一 (%d 本)" % len(ids))
    chk(set(ids) == set(itemdb), "與 item_skillbook.yml 的編號集合相同 (%d)" % len(itemdb))

    # 2. 每一階必須完全等於 05.技能書.txt 的號段 —— 這才是伺服器真正的抽取池
    for t in sorted(seg):
        want = set()
        for base, n in seg[t]:
            want |= set(range(base, base + n))
        got = {r["id"] for r in rows if r["tier"] == t}
        chk(got == want, "%d轉的池子與 $@SKB_* 號段相同 (%d 支)" % (t, len(want)))
    chk(set(seg) == {r["tier"] for r in rows}, "階級集合 = 號段表的階級集合 %s" % sorted(seg))

    # 3. 欄位完整性
    chk(all(r["name"] for r in rows), "每一支都有中文名稱")
    chk(all(r["jobcn"] for r in rows), "每一支都對到中文職業名")
    chk(all(r["maxlv"] >= 1 for r in rows), "技能上限都 >= 1")

    # 4. 圖示
    miss = [r["icon"] for r in rows if r["icon"] not in sizes]
    chk(not miss, "每一支都有圖示 (%d 個檔, 共用後 %d 支)" % (len(sizes), len(rows)))
    bad = [k for k, v in sizes.items() if v != (24, 24)]
    chk(not bad, "圖示都是 24x24" + ("" if not bad else " — 例外: %s" % bad[:5]))
    onfile = {f[:-4] for f in os.listdir(PNG) if f.endswith(".png")}
    chk(onfile == set(sizes), "skills/ 沒有多餘或缺少的 PNG (%d)" % len(onfile))

    # 5. 頁面
    chk(not re.search(r"__[A-Z]+__", out), "樣板佔位全部替換")
    chk(out.count('class="sk"') == len(rows), "卡片數 %d" % out.count('class="sk"'))
    for t in sorted(seg):
        n = out.count('data-t="%d"' % t)
        chk(n == len([r for r in rows if r["tier"] == t]) + 1,
            "%d轉: %d 張卡 + 1 個 chip" % (t, n - 1))

    print("  ----  %s   (%.0f KB)" % ("PASS" if ok else "FAIL", len(out.encode("utf-8")) / 1024))
    return ok


def main():
    rows, itemdb, seg = parse_sources()
    tiers = {}
    for r in rows:
        tiers[r["tier"]] = tiers.get(r["tier"], 0) + 1
    print("來源  %d 支技能  (%s)" % (
        len(rows), " / ".join("%d轉 %d" % (t, tiers[t]) for t in sorted(tiers))))

    sizes, keyed = render_icons(rows)
    print("圖示  %d 個 PNG, 其中 %d 個有洋紅去背" % (len(sizes), keyed))

    out = build_page(rows, tiers)
    print("頁面  skillstone.html %.1f KB" % (len(out.encode("utf-8")) / 1024))

    if not verify(rows, itemdb, seg, sizes, out):
        raise SystemExit(1)
    print("完成。來源沒變的話 git status 應該是乾淨的。")


if __name__ == "__main__":
    main()

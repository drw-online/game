# -*- coding: utf-8 -*-
"""
靈獸島魔物圖鑑產生器 —— 產生 mobs.html, 跑完自己驗證一次。

用法(需要 PyYAML):

    python tools/build_mobs.py

會覆寫 mobs.html。輸出是決定性的 —— 來源沒變的話重跑一次 git status
應該是乾淨的, 這也是最好的回歸測試。

--------------------------------------------------------------------------
來源
--------------------------------------------------------------------------
  script/05.魔物/13.靈獸島.txt                  生成清單(352 隻的權威名單)
  script/04.系統/56.靈獸島入口.txt              入場費
  db/import/blackgod/mob_bossnia.yml            190 隻專用 MVP 本體
  db/import/blackgod/mob_drwmob.yml             162 種神域魔物本體
  db/import/blackgod/mob_skillstone.yml         352 隻的 1轉技能石(附加)
  db/import/blackgod/mob_drwmob_mvpcoin.yml     162 種的 MVP硬幣(附加)
  db/import/map_drops.yml                       bossnia_01 的 2~4轉技能石
  db/re/item_db_*.yml + db/import/blackgod/item_*.yml   物品中文名

★ 掉落是四層疊加, 少讀一支就會漏 —— mob_db 的 Drops 是「附加」不是
  「取代」(mob.cpp:5186 的 drops.push_back()), 所以 mob_skillstone.yml 與
  mob_drwmob_mvpcoin.yml 那兩支只寫 Id + Drops 的附加檔也要一起算進來。

★ 兩邊的 Rate 分母不一樣:
      mob_db     10000    (Rate 5 = 0.05%)
      map_drops  看 Header 的 Version: 2=十萬分比 3=百萬分比 (本檔是 3)
  抄錯會讓機率差 100 倍。

★ conf/battle/drops.conf 的 item_rate_* 目前全部是 100(無加成),
  所以 db 裡的數字就是玩家實際看到的機率。倍率若改了, 本頁要跟著改。
"""
import os, re, json, html
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
WEB  = os.path.dirname(HERE)
ROOT = r"H:\91.神域仙境"
DB   = os.path.join(ROOT, r"2.開機擋\db")
BG   = os.path.join(DB, "import", "blackgod")
SPAWN = os.path.join(ROOT, r"2.開機擋\script\05.魔物\13.靈獸島.txt")
ENTRY = os.path.join(ROOT, r"2.開機擋\script\04.系統\56.靈獸島入口.txt")

MAP = "bossnia_01"

RACE = {"Formless": "無形", "Undead": "不死", "Brute": "動物", "Plant": "植物",
        "Insect": "昆蟲", "Fish": "魚貝", "Demon": "惡魔", "Demihuman": "人形",
        "Angel": "天使", "Dragon": "龍族"}
ELEM = {"Neutral": "無", "Water": "水", "Earth": "地", "Fire": "火", "Wind": "風",
        "Poison": "毒", "Holy": "聖", "Dark": "暗", "Ghost": "念", "Undead": "不死"}
SIZE = {"Small": "小型", "Medium": "中型", "Large": "大型"}


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        return yaml.safe_load(f)


def body(path):
    return (load(path) or {}).get("Body") or []


# ---------------------------------------------------------------- 來源解析

def read_spawn():
    """從生成腳本取出實際會生成的魔物 —— 資料表的權威名單。"""
    with open(SPAWN, encoding="utf-8-sig") as f:
        t = f.read()
    return [(int(a), int(b), int(c)) for a, b, c in re.findall(
        r'^%s,\d+,\d+,\d+,\d+\tmonster\t.+?\t(\d+),(\d+),(\d+)\s*$' % MAP, t, re.M)]


def read_entrance_fee():
    """入場費寫在入口 NPC 裡, 不要在本檔另外寫死一份。"""
    with open(ENTRY, encoding="utf-8-sig") as f:
        t = f.read()
    m = re.search(r'^\s*\$@BN_FEE\s*=\s*(\d+)\s*;', t, re.M)
    if not m:
        raise SystemExit("入口腳本裡找不到 $@BN_FEE")
    return int(m.group(1))


def read_items():
    """AegisName -> (Id, 中文名)。本服的 item_db 本身就是中文的。"""
    rels = ["re/item_db_equip.yml", "re/item_db_etc.yml", "re/item_db_usable.yml"]
    rels += ["import/blackgod/" + f for f in sorted(os.listdir(BG))
             if f.startswith("item_") and f.endswith(".yml")]
    names = {}
    for rel in rels:
        p = os.path.join(DB, rel.replace("/", os.sep))
        if not os.path.exists(p):
            continue
        for it in body(p):
            if it.get("AegisName") and it.get("Name"):
                names[it["AegisName"]] = (it["Id"], it["Name"])
    return names


def read_map_drops():
    """bossnia_01 的 GlobalDrops。分母看 Header 的 Version。"""
    d = load(os.path.join(DB, "import", "map_drops.yml"))
    denom = 1000000 if int(d["Header"]["Version"]) >= 3 else 100000
    for row in d["Body"]:
        if row.get("Map") == MAP:
            return [(g["Item"], g["Rate"] / denom * 100) for g in row.get("GlobalDrops") or []]
    return []


def collect():
    items = read_items()
    mvp = {m["Id"]: m for m in body(os.path.join(BG, "mob_bossnia.yml"))}
    drw = {m["Id"]: m for m in body(os.path.join(BG, "mob_drwmob.yml"))}

    extra = {}
    for fn in ("mob_skillstone.yml", "mob_drwmob_mvpcoin.yml"):
        for m in body(os.path.join(BG, fn)):
            extra.setdefault(m["Id"], []).extend(m.get("Drops") or [])

    def drops_of(mob, mid):
        out = []
        for src, mvp_only in ((mob.get("Drops") or [], 0),
                              (mob.get("MvpDrops") or [], 1),
                              (extra.get(mid) or [], 0)):
            for x in src:
                iid, name = items[x["Item"]]
                out.append([iid, name, round(x["Rate"] / 10000 * 100, 6), mvp_only])
        return out

    rows = []
    for mid, _amount, respawn in read_spawn():
        mob = mvp.get(mid) or drw.get(mid)
        if mob is None:
            raise SystemExit("生成清單有 %d 但兩支 mob_db 都查不到" % mid)
        rows.append({
            "id": mid,
            "k": "mvp" if mid in mvp else "drw",
            "n": mob.get("JapaneseName") or mob["Name"],
            "en": mob["Name"],
            "lv": mob["Level"],
            "hp": mob["Hp"],
            "atk": mob["Attack"],
            "matk": mob["Attack2"],
            "df": mob.get("Defense", 0),
            "mdf": mob.get("MagicDefense", 0),
            "sz": SIZE[mob["Size"]],
            "rc": RACE[mob["Race"]],
            "el": ELEM[mob["Element"]],
            "elv": mob["ElementLevel"],
            "rng": mob["AttackRange"],
            "exp": mob.get("BaseExp", 0),
            "jexp": mob.get("JobExp", 0),
            "mexp": mob.get("MvpExp", 0),
            "dt": mob.get("DamageTaken", 100),
            "res": mob.get("Resistance", 0),
            "mres": mob.get("MagicResistance", 0),
            "st": [mob.get(k, 0) for k in ("Str", "Agi", "Vit", "Int", "Dex", "Luk")],
            "rs": respawn,
            "d": drops_of(mob, mid),
        })

    gdrops = [[items[a][0], items[a][1], round(r, 6)] for a, r in read_map_drops()]
    return rows, gdrops


def common_drops(rows, gdrops):
    """352 隻全部都掉的那幾樣 —— 抽出來單獨講, 表格就不必重複 352 次。"""
    sets = [{x[0] for x in r["d"] if not x[3]} for r in rows]
    shared = set.intersection(*sets) if sets else set()
    ref = {x[0]: x for x in rows[0]["d"]}
    out = [(ref[i][1], ref[i][2], "352 隻全部") for i in sorted(shared)]
    out += [(n, r, "地圖掉落") for _, n, r in gdrops]
    return out, shared


# ---------------------------------------------------------------- HTML

def pct(v):
    s = ("%.4f" if v >= 1 else "%.6f") % v
    return (s.rstrip("0").rstrip(".") or "0") + "%"


def esc(s):
    return html.escape(str(s), quote=False)


TPL = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>靈獸島魔物圖鑑 · 神域仙境</title>
<meta name="description" content="靈獸島 352 隻魔物的完整數值與掉落：190 隻專用 MVP 與 162 種神域魔物。">
<meta name="color-scheme" content="light dark">
<meta property="og:type" content="website">
<meta property="og:site_name" content="神域仙境">
<meta property="og:title" content="靈獸島魔物圖鑑">
<meta property="og:description" content="靈獸島 352 隻魔物的完整數值與掉落。">
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
.wrap{max-width:1080px; margin:0 auto; padding:0 20px 76px}
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
h2{margin:0 0 14px; font-family:"Noto Serif TC",serif; font-size:20px; font-weight:700; letter-spacing:.1em}
section{margin-top:38px}
.tbl-wrap{overflow-x:auto; -webkit-overflow-scrolling:touch}
table{border-collapse:collapse; width:100%; font-size:14px; min-width:460px}
th,td{text-align:left; padding:9px 14px; border-bottom:1px solid var(--rule-soft)}
th{font-size:12px; letter-spacing:.14em; color:var(--ink-faint); font-weight:500; white-space:nowrap;
  border-bottom:1px solid var(--rule)}
td.num,th.num{text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap}
.foot{margin-top:48px; padding-top:20px; border-top:1px solid var(--rule);
  font-size:12.5px; line-height:1.85; color:var(--ink-faint); max-width:76ch}
.foot b{color:var(--ink-soft); font-weight:500}
.foot p{margin:0 0 10px}
.back{display:inline-block; margin-top:6px; color:var(--cinnabar); font-size:13px; letter-spacing:.06em; text-decoration:none}
.back:hover{text-decoration:underline; text-underline-offset:5px}
.back:focus-visible{outline:2px solid var(--focus); outline-offset:3px; border-radius:2px}
@media (max-width:640px){ .masthead{padding:32px 0 22px} }
@media (prefers-reduced-motion: reduce){ *{transition:none !important} }

.facts{list-style:none; margin:0; padding:0; display:grid; gap:12px;
  grid-template-columns:repeat(auto-fit,minmax(178px,1fr))}
.facts li{background:var(--paper); border:1px solid var(--rule-soft); border-radius:6px;
  padding:16px 18px; box-shadow:var(--shadow)}
.fk{display:block; font-size:12px; letter-spacing:.18em; color:var(--ink-faint)}
.fv{display:block; margin-top:5px; font-family:"Noto Serif TC",serif; font-size:23px;
  font-weight:700; letter-spacing:.04em; color:var(--cinnabar); font-variant-numeric:tabular-nums}
.fn{display:block; margin-top:3px; font-size:12.5px; color:var(--ink-soft); line-height:1.6}

.controls{position:sticky; top:0; z-index:5; background:var(--ground); padding:14px 0 12px;
  border-bottom:1px solid var(--rule); margin-bottom:18px}
.ctl-row{display:flex; flex-wrap:wrap; gap:9px 16px; align-items:center}
.ctl-row + .ctl-row{margin-top:10px}
.glab{font-size:12px; letter-spacing:.18em; color:var(--ink-faint); flex:none; width:34px}
.search{flex:1 1 240px; min-width:200px; padding:9px 13px; background:var(--paper); color:var(--ink);
  border:1px solid var(--rule); border-radius:4px; font:inherit; font-size:14px}
.search::placeholder{color:var(--ink-faint)}
.search:focus-visible{outline:2px solid var(--focus); outline-offset:1px; border-color:var(--focus)}
.chip{padding:5px 12px; background:var(--paper); color:var(--ink-soft); border:1px solid var(--rule);
  border-radius:100px; font:inherit; font-size:13px; cursor:pointer; white-space:nowrap;
  transition:background .12s ease,color .12s ease,border-color .12s ease}
.chip:hover{border-color:var(--ink-faint)}
.chip:focus-visible{outline:2px solid var(--focus); outline-offset:2px}
.chip[aria-pressed="true"]{background:var(--cinnabar); border-color:var(--cinnabar); color:var(--on-accent)}
.tally{margin:11px 0 0; font-size:13px; color:var(--ink-soft); font-variant-numeric:tabular-nums}
.tally b{color:var(--cinnabar); font-weight:700; font-size:15px}

#mobs{min-width:900px}
tr.mob{cursor:pointer}
tr.mob:hover{background:var(--sunk)}
tr.mob:focus-visible{outline:2px solid var(--focus); outline-offset:-2px}
td.oid{font-variant-numeric:tabular-nums; color:var(--ink-faint); width:1%; white-space:nowrap}
td.nm{white-space:nowrap}
td.nm b{font-weight:500}
.tag{display:inline-block; margin-right:7px; padding:1px 7px; border-radius:100px;
  font-size:11px; letter-spacing:.08em; vertical-align:1px}
.tag.mvp{background:var(--cinnabar); color:var(--on-accent)}
.tag.drw{background:var(--sunk); color:var(--ink-soft); border:1px solid var(--rule)}
td.el{white-space:nowrap; color:var(--ink-soft); font-size:13px}
td.dp{font-size:13px; color:var(--ink-soft); min-width:190px}
tr.detail > td{background:var(--sunk); padding:0}
.dwrap{padding:16px 18px 20px}
.grid{display:grid; gap:10px 26px; grid-template-columns:repeat(auto-fit,minmax(108px,1fr));
  margin:0 0 18px; padding:0; list-style:none}
.grid li{font-size:13px}
.grid b{display:block; font-size:11px; letter-spacing:.14em; color:var(--ink-faint); font-weight:500}
.grid span{font-variant-numeric:tabular-nums; color:var(--ink)}
.dt h3{margin:0 0 8px; font-size:12px; letter-spacing:.16em; color:var(--ink-faint); font-weight:500}
.dt table{min-width:0; font-size:13px; width:auto}
.dt th,.dt td{padding:6px 22px 6px 0; border-bottom:1px solid var(--rule-soft)}
.dt tr:last-child td{border-bottom:0}
td.rate{color:var(--cinnabar); font-weight:500; text-align:right; font-variant-numeric:tabular-nums}
.only{font-size:11px; color:var(--ink-faint); margin-left:7px}
.empty{padding:40px 0; text-align:center; color:var(--ink-faint)}
.note{margin:12px 0 0; font-size:13px; color:var(--ink-faint); max-width:66ch}
.note b{color:var(--ink-soft); font-weight:500}
</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <a class="home" href="index.html">
      <img src="logo.webp" width="440" height="440" alt="" decoding="async">
      <span>← 神域仙境 玩家工具</span>
    </a>
    <h1>靈獸島魔物圖鑑</h1>
    <p class="lede">靈獸島是<b>單一張圖</b>，__TOTAL__ 隻魔物同時擠在上面：__NMVP__ 隻專用 MVP 與 __NDRW__ 種神域魔物，每種各 1 隻、<b>死了 1 秒就重生</b>。下面是每一隻的完整數值與掉落。</p>
  </header>

  <section>
    <h2>進去之前</h2>
    <ul class="facts">
      <li><span class="fk">入場費</span><span class="fv">__FEE__ z</span><span class="fn">每次進場收取</span></li>
      <li><span class="fk">MVP 受到的傷害</span><span class="fv">10%</span><span class="fn">__NMVP__ 隻 MVP 全部減傷 90%；神域魔物無減傷</span></li>
      <li><span class="fk">重生</span><span class="fv">1 秒</span><span class="fn">引擎下限，寫更小也沒用</span></li>
      <li><span class="fk">魔物總數</span><span class="fv">__TOTAL__</span><span class="fn">__NMVP__ 隻 MVP ＋ __NDRW__ 種神域魔物</span></li>
    </ul>
    <p class="note">這裡的 MVP 是<b>靈獸島專用的複製品</b>（編號 __MVPFROM__～__MVPTO__），與野外那些同名的王是不同的魔物 —— 差別只在<b>只吃 10% 傷害</b>。牠們掉的卡片與素材則與本尊相同。</p>
  </section>

  <section>
    <h2>全圖共通掉落</h2>
    <p class="note" style="margin-top:0">不分魔物種類，圖上每一隻死掉都會擲的幾樣。個別魔物自己的掉落列在下面的表裡。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>物品</th><th class="num">機率</th><th>來源</th></tr></thead>
        <tbody>__COMMON__</tbody>
      </table>
    </div>
    <p class="note">MVP 硬幣是這張圖的主要產出。__TOTAL__ 隻全清一輪的期望值是 __TOTAL__ × __COINPCT__ ＝ <b>__COINEXP__ 枚</b>，也就是平均清 __COINROUNDS__ 輪出一枚。</p>
  </section>

  <section>
    <h2>魔物一覽</h2>
    <div class="controls">
      <div class="ctl-row">
        <input id="q" class="search" type="search" placeholder="搜尋名稱或編號…　例：巴風特、26001、神域魔物007" aria-label="搜尋魔物">
        <div id="kind" class="ctl-row" role="group" aria-label="類型"></div>
      </div>
      <div class="ctl-row">
        <span class="glab">種族</span>
        <div id="race" class="ctl-row" role="group" aria-label="種族"></div>
      </div>
      <div class="ctl-row">
        <span class="glab">屬性</span>
        <div id="elem" class="ctl-row" role="group" aria-label="屬性"></div>
      </div>
      <div class="ctl-row">
        <span class="glab">體型</span>
        <div id="size" class="ctl-row" role="group" aria-label="體型"></div>
      </div>
      <p class="tally" id="tally"></p>
    </div>
    <div class="tbl-wrap">
      <table id="mobs">
        <thead><tr>
          <th class="num">編號</th><th>名稱</th><th class="num">等級</th><th class="num">HP</th>
          <th>種族</th><th>屬性</th><th>體型</th>
          <th class="num">攻擊</th><th class="num">魔攻</th><th class="num">防禦</th>
          <th>專屬掉落</th>
        </tr></thead>
        <tbody id="rows"></tbody>
      </table>
    </div>
    <div class="empty" id="empty" hidden>沒有符合條件的魔物。</div>
    <p class="note">點任一列可展開完整數值與全部掉落。「專屬掉落」欄<b>不重複列出</b>上面那 __NSHARED__ 樣全圖共通的東西。</p>
  </section>

  <footer class="foot">
    <p><b>機率就是實際機率</b>　伺服器的掉率倍率目前全部是 100%（無加成），所以表上的數字不必再乘任何東西。倍率若日後調整，本頁會一併更新。</p>
    <p><b>攻擊與魔攻是兩個欄位</b>　更新版引擎把魔物的第二攻擊力當成魔法攻擊，不是攻擊力上限 —— 表上的「魔攻」就是牠的魔法攻擊。</p>
    <p><b>MVP 獎勵掉落另計</b>　展開後標了「MVP 獎勵」的那幾格只有搶到 MVP 的人拿得到，與一般掉落分開擲。</p>
    <p><b>同名不同隻</b>　MVP 清單裡有幾個名字重複，那是原廠本來就有多個版本的同名王，編號不同、數值也不同。</p>
    <p><b>神域魔物的外觀</b>　__NDRW__ 種神域魔物長什麼樣子、對應哪顆寵物蛋，看<a href="pets.html" style="color:var(--cinnabar)">神域寵物圖鑑</a>。</p>
    <a class="back" href="index.html">← 回神域仙境玩家工具</a>
  </footer>
</div>

<script>
const MOBS = __DATA__;
const SHARED = new Set(__SHAREDIDS__);

const F = {q:"", k:"", rc:"", el:"", sz:""};
const $ = s => document.querySelector(s);
const rowsEl = $("#rows"), emptyEl = $("#empty"), tallyEl = $("#tally");
const fmt = n => n.toLocaleString("en-US");

function chips(host, key, list, allLabel){
  const mk = (label, val) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "chip"; b.textContent = label;
    b.dataset.v = val;
    b.setAttribute("aria-pressed", String(F[key] === val));
    b.onclick = () => {
      F[key] = F[key] === val ? "" : val;
      host.querySelectorAll(".chip").forEach(c =>
        c.setAttribute("aria-pressed", String(c.dataset.v === F[key])));
      render();
    };
    return b;
  };
  host.appendChild(mk(allLabel, ""));
  list.forEach(([label, val]) => host.appendChild(mk(label, val)));
}

function detail(m){
  const tr = document.createElement("tr");
  tr.className = "detail";
  const td = document.createElement("td");
  td.colSpan = 11;

  const stats = [
    ["STR", m.st[0]], ["AGI", m.st[1]], ["VIT", m.st[2]],
    ["INT", m.st[3]], ["DEX", m.st[4]], ["LUK", m.st[5]],
    ["魔防", m.mdf], ["射程", m.rng], ["屬性", m.el + " Lv" + m.elv],
    ["受到傷害", m.dt + "%"], ["Base 經驗", fmt(m.exp)], ["Job 經驗", fmt(m.jexp)],
  ];
  if (m.mexp) stats.push(["MVP 經驗", fmt(m.mexp)]);
  if (m.res)  stats.push(["RES", m.res]);
  if (m.mres) stats.push(["MRES", m.mres]);

  const ul = document.createElement("ul");
  ul.className = "grid";
  for (const [k, v] of stats){
    const li = document.createElement("li");
    const b = document.createElement("b"); b.textContent = k;
    const s = document.createElement("span"); s.textContent = v;
    li.append(b, s); ul.appendChild(li);
  }

  const box = document.createElement("div");
  box.className = "dwrap";
  box.appendChild(ul);

  const dt = document.createElement("div");
  dt.className = "dt";
  const h3 = document.createElement("h3");
  h3.textContent = "全部掉落（" + m.d.length + " 格）";
  dt.appendChild(h3);

  const t = document.createElement("table");
  const tb = document.createElement("tbody");
  for (const d of m.d.slice().sort((a, b) => b[2] - a[2])){
    const r = document.createElement("tr");
    const c1 = document.createElement("td");
    c1.textContent = d[1];
    if (d[3]){
      const s = document.createElement("span");
      s.className = "only"; s.textContent = "MVP 獎勵";
      c1.appendChild(s);
    }
    const c2 = document.createElement("td");
    c2.className = "rate"; c2.textContent = d[2] + "%";
    const c3 = document.createElement("td");
    c3.className = "oid"; c3.textContent = "#" + d[0];
    r.append(c1, c2, c3); tb.appendChild(r);
  }
  t.appendChild(tb); dt.appendChild(t);
  box.appendChild(dt); td.appendChild(box); tr.appendChild(td);
  return tr;
}

function row(m){
  const tr = document.createElement("tr");
  tr.className = "mob";
  tr.tabIndex = 0;

  const own = m.d.filter(d => !SHARED.has(d[0]));
  const label = own.length
    ? own.slice(0, 2).map(d => d[1]).join("、") + (own.length > 2 ? " 等 " + own.length + " 樣" : "")
    : "—";

  const cells = [
    ["num oid", m.id], ["nm", null], ["num", m.lv], ["num", fmt(m.hp)],
    ["el", m.rc], ["el", m.el + " Lv" + m.elv], ["el", m.sz],
    ["num", fmt(m.atk)], ["num", fmt(m.matk)], ["num", fmt(m.df)],
    ["dp", label],
  ];
  cells.forEach(([cls, val], i) => {
    const td = document.createElement("td");
    td.className = cls;
    if (i === 1){
      const tag = document.createElement("span");
      tag.className = "tag " + m.k;
      tag.textContent = m.k === "mvp" ? "MVP" : "神域";
      const b = document.createElement("b");
      b.textContent = m.n;
      td.append(tag, b);
    } else {
      td.textContent = val;
    }
    tr.appendChild(td);
  });

  let open = null;
  const toggle = () => {
    if (open){ open.remove(); open = null; return; }
    open = detail(m);
    tr.after(open);
  };
  tr.onclick = toggle;
  tr.onkeydown = e => {
    if (e.key === "Enter" || e.key === " "){ e.preventDefault(); toggle(); }
  };
  return tr;
}

function render(){
  const q = F.q.trim().toLowerCase();
  const list = MOBS.filter(m =>
    (!F.k  || m.k  === F.k)  &&
    (!F.rc || m.rc === F.rc) &&
    (!F.el || m.el === F.el) &&
    (!F.sz || m.sz === F.sz) &&
    (!q || m.n.toLowerCase().includes(q) || m.en.toLowerCase().includes(q) || String(m.id).includes(q))
  );
  rowsEl.replaceChildren(...list.map(row));
  emptyEl.hidden = list.length > 0;
  const nm = list.filter(m => m.k === "mvp").length;
  tallyEl.innerHTML = "顯示 <b>" + list.length + "</b> 隻　（MVP " + nm
    + "　神域魔物 " + (list.length - nm) + "）";
}

chips($("#kind"), "k",  [["MVP", "mvp"], ["神域魔物", "drw"]], "全部");
chips($("#race"), "rc", __RACES__, "全部");
chips($("#elem"), "el", __ELEMS__, "全部");
chips($("#size"), "sz", __SIZES__, "全部");
$("#q").addEventListener("input", e => { F.q = e.target.value; render(); });
render();
</script>
</body>
</html>
"""


def build():
    rows, gdrops = collect()
    common, shared = common_drops(rows, gdrops)

    nmvp = sum(1 for r in rows if r["k"] == "mvp")
    mvp_ids = [r["id"] for r in rows if r["k"] == "mvp"]
    coin = next(r for n, r, _ in common if "硬幣" in n)
    exp_coin = len(rows) * coin / 100

    trs = "".join(
        '<tr><td>%s</td><td class="num rate">%s</td><td class="el">%s</td></tr>'
        % (esc(n), pct(r), esc(src)) for n, r, src in common)

    def pairs(key):
        return json.dumps([[v, v] for v in sorted({r[key] for r in rows})],
                          ensure_ascii=False)

    out = TPL
    for k, v in [
        ("__TOTAL__", str(len(rows))),
        ("__NMVP__", str(nmvp)),
        ("__NDRW__", str(len(rows) - nmvp)),
        ("__NSHARED__", str(len(shared))),
        ("__MVPFROM__", str(min(mvp_ids))),
        ("__MVPTO__", str(max(mvp_ids))),
        ("__FEE__", "{:,}".format(read_entrance_fee())),
        ("__COMMON__", trs),
        ("__COINPCT__", pct(coin)),
        ("__COINEXP__", ("%.3f" % exp_coin).rstrip("0").rstrip(".")),
        ("__COINROUNDS__", str(round(1 / exp_coin))),
        ("__SHAREDIDS__", json.dumps(sorted(shared))),
        ("__RACES__", pairs("rc")),
        ("__ELEMS__", pairs("el")),
        ("__SIZES__", pairs("sz")),
        ("__DATA__", json.dumps(rows, ensure_ascii=False, separators=(",", ":"))),
    ]:
        out = out.replace(k, v)

    dest = os.path.join(WEB, "mobs.html")
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    return dest, rows, common, out


# ---------------------------------------------------------------- 驗證

def verify(dest, rows, common, out):
    ok = True

    def chk(cond, msg):
        nonlocal ok
        print(("  ok    " if cond else "  FAIL  ") + msg)
        ok = ok and bool(cond)

    print("驗證 %s" % dest)
    chk(len(rows) == 352, "魔物 352 隻 (實得 %d)" % len(rows))
    chk(sum(1 for r in rows if r["k"] == "mvp") == 190, "MVP 190 隻")
    chk(sum(1 for r in rows if r["k"] == "drw") == 162, "神域魔物 162 種")
    chk(len({r["id"] for r in rows}) == len(rows), "編號不重複")
    chk(all(r["n"] for r in rows), "每隻都有顯示名")
    chk(all(not re.fullmatch(r'[A-Za-z0-9_]+', d[1]) for r in rows for d in r["d"]),
        "掉落物全部是中文名")
    chk(all(r["dt"] == 10 for r in rows if r["k"] == "mvp"), "MVP 減傷 90%")
    chk(all(r["rs"] == 1000 for r in rows), "重生 1 秒")
    chk(len(common) == 5, "全圖共通掉落 5 樣 (實得 %d)" % len(common))
    coin = [c for c in common if "硬幣" in c[0]]
    chk(len(coin) == 1 and abs(coin[0][1] - 0.05) < 1e-9, "MVP硬幣 0.05%")
    st = [c for c in common if c[0] == "1轉技能石"]
    chk(len(st) == 1 and abs(st[0][1] - 5) < 1e-9, "1轉技能石 5%")
    chk(all(len(r["d"]) >= 2 for r in rows), "掉落有疊加附加檔")
    chk(not re.search(r'__[A-Z]+__', out), "樣板佔位全部替換")
    print("  ----  %s   (%.0f KB)" % ("PASS" if ok else "FAIL",
                                      len(out.encode("utf-8")) / 1024))
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if verify(*build()) else 1)

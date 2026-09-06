# -*- coding: utf-8 -*-
"""
萬妖詞綴圖鑑產生器 —— 產生 mobaffix.html, 跑完自己驗證一次。

用法(需要 PyYAML):

    python tools/build_mobaffix.py

會覆寫 mobaffix.html。輸出是決定性的 —— 來源沒變的話重跑一次 git status
應該是乾淨的, 這也是最好的回歸測試。

--------------------------------------------------------------------------
來源
--------------------------------------------------------------------------
  db/import/mob_affix_db.yml       28 條詞綴 (名稱/最低階/最低境/權重/互斥組/數值)
  db/import/mob_affix_map_db.yml   13 張啟用地圖 (模式/境/上限)
  conf/battle/blackgod.conf        總開關 + 五階機率 + 五階掉落倍率

★ 十二境的「詞綴數上限」不在任何設定檔裡 —— 它寫死在 C++
  (add/src/blackgod_mob_affix.inc 的 mob_affix_realm_cap[])。這裡複製一份,
  verify() 會拿規格 §1.2 的 1,1,2,2,3,3,4,4,4,5,5,6 對一次。但改了 C++ 卻
  沒改這裡的話, 驗證抓不到 —— 那是這支唯一無法自動偵測的耦合。

★ 抽階級用的是「五者總和」當分母, 不強制等於 10000。所以百分比一律用實際
  總和算, 不要寫死除以 10000 —— 測試期間曾把 r_n 設成 0, 寫死的話比例會錯。

★ 詞綴的 Stats 全部選填。缺欄位代表 0 而不是繼承, 組效果字串時要跳過 0,
  否則會印出一堆「攻擊 +0%」。

★ 每一境實際抽得到幾條, 受 MinRank / MinRealm / 互斥組三者夾擊。
  verify() 逐境檢查「互斥後湊得出的條數 >= 該境上限」—— 湊不出來的話
  那一境的高階怪會默默少帶幾條, 而且不報錯。
"""
import os, re, json, html

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
WEB  = os.path.dirname(HERE)
ROOT = r"H:\91.神域仙境"
SRV  = os.path.join(ROOT, "2.開機擋")

AFFIX = os.path.join(SRV, r"db\import\mob_affix_db.yml")
MAPDB = os.path.join(SRV, r"db\import\mob_affix_map_db.yml")
CONF  = os.path.join(SRV, r"conf\battle\blackgod.conf")

# 規格 §1.2。索引 = 境(1~12)。與 mob_affix_realm_cap[] 必須一致。
REALM_CAP  = [0, 1, 1, 2, 2, 3, 3, 4, 4, 4, 5, 5, 6]
REALM_NAME = "子丑寅卯辰巳午未申酉戌亥"

# 規格 §1.1。詞綴數隨階級, 稀有與天命是區間。
RANK_NAME  = ["普通", "強化", "精英", "稀有", "天命"]
RANK_COUNT = ["0", "1", "2", "3～4", "5～6"]
RANK_KEY   = ["n", "e", "el", "r", "f"]

GROUP_NAME = {
    # 0831 規格(十二洞天)的互斥組
    "S":  "強生存",
    "D":  "高傷",
    "B":  "迴避",
    "MY": "神話",
    "":   "命中",
    # 0901 規格(共通 C 池)的互斥組。yml 只給英文代號沒給中文, 下面的譯名是
    # 照各組實際的 Stats 取的, 不是從來源讀來的:
    #   SURV_HARD  = MaxHPRate            -> 厚血
    #   SURV_ARMOR = Def/Mdef + Res/Mres  -> 護甲
    #   BURST      = Atk/Matk 或 Crit     -> 爆發
    #   SPEED      = HitRate              -> 敏捷
    #     (規格 C-D08 原本是 ASPD +10% + HIT +12%, 但 Stats 的 SpeedRate 是
    #      移動速度不是攻速, 實作只做得出 HIT —— 譯名跟著實作走而不是規格)
    "SURV_HARD":  "厚血",
    "SURV_ARMOR": "護甲",
    "BURST":      "爆發",
    "SPEED":      "敏捷",
}

# 0901 規格 §11 的危險值分段, 對應 mob_affix_danger_rate()
# (1.原始碼/add/src/blackgod_mob_affix.inc:1188)。
# ★ 這寫死在 C++, 與 REALM_CAP 同屬「改了 C++ 這裡不會自動跟上」的耦合,
#   verify() 偵測不到。
DANGER_BAND = [
    ("0",      1.00),
    ("1～5",   1.10),
    ("6～10",  1.25),
    ("11～15", 1.45),
    ("16～20", 1.70),
    ("21 以上", 2.00),
]

# Stats 欄位 -> (顯示名, 是不是百分比)。順序就是顯示順序。
STAT_LABEL = [
    ("MaxHPRate", "最大HP",   True),
    ("AtkRate",   "攻擊",     True),
    ("MatkRate",  "魔攻",     True),
    ("DefRate",   "防禦",     True),
    ("MdefRate",  "魔防",     True),
    ("ResAdd",    "RES",      False),
    ("MresAdd",   "MRES",     False),
    ("CritAdd",   "暴擊",     False),
    ("HitRate",   "命中",     True),
    ("FleeRate",  "迴避",     True),
    ("SpeedRate", "移動速度", True),
]


# ---------------------------------------------------------------- 讀取

def esc(s):
    return html.escape(str(s), quote=False)


def load_yaml(path):
    with open(path, encoding="utf-8-sig") as f:
        return (yaml.safe_load(f) or {}).get("Body") or []


def read_conf():
    with open(CONF, encoding="utf-8-sig") as f:
        t = f.read()

    def num(key):
        m = re.search(r"^%s:\s*(\d+)" % re.escape(key), t, re.M)
        if not m:
            raise SystemExit("conf 找不到 %s" % key)
        return int(m.group(1))

    return {
        "enable": num("mob_affix_enable"),
        "rate":   [num("mob_affix_r_" + k) for k in RANK_KEY],
        "drop":   [num("mob_affix_drop_" + k) for k in RANK_KEY],
    }


def stat_text(stats):
    """把 Stats 組成「最大HP +100% · RES +100」。0 與缺欄位都跳過。"""
    out = []
    for key, label, is_pct in STAT_LABEL:
        v = (stats or {}).get(key, 0)
        if not v:
            continue
        out.append("%s %+d%s" % (label, v, "%" if is_pct else ""))
    return " · ".join(out)


def collect():
    conf = read_conf()

    rows = []
    for e in load_yaml(AFFIX):
        g = (e.get("Group") or "").strip()
        rows.append({
            "id":    int(e["Id"]),
            "nm":    e["Name"],
            "g":     g,
            "gn":    GROUP_NAME.get(g, g or "其他"),
            "rank":  int(e.get("MinRank", 1)),
            "realm": int(e.get("MinRealm", 0)),
            "w":     int(e.get("Weight", 100)),
            "boss":  bool(e.get("BossAllowed", False)),
            "st":    stat_text(e.get("Stats")),
            # ★ 判別兩套規格用 Pool 的「有無」, 不要用 MinRealm 是不是 0。
            #   0901 那批根本沒有 MinRealm 欄位, 讀出來是 0, 若拿 0 當
            #   「不限境界」就會把它們算進每一境的池子 —— 子境會從 8 條
            #   變成 14 條, 而且完全不報錯。
            "pool":  (e.get("Pool") or "").strip(),
            "ds":    int(e.get("DangerScore", 0)),
        })
    rows.sort(key=lambda r: (r["pool"], r["realm"], r["rank"], -r["w"], r["id"]))

    maps = []
    for e in load_yaml(MAPDB):
        maps.append({
            "map":   e["Map"],
            "mode":  e.get("Mode", "OFF"),
            "realm": int(e.get("Realm", 0)),
            "cap":   int(e.get("MaxAffixes", 0)),
            "pools": list(e.get("Pools") or []),
            "dcaps": list(e.get("DangerCaps") or []),
            "deny":  list(e.get("MobDeny") or []),
            # 極道異種(0901 規格 §22)。十二洞天那 13 張也有 —— 一般怪照舊
            # 只抽 REALM 池, 極道另走 ExtremePools 的 C 池, 兩者互不影響。
            "ex_pools": list(e.get("ExtremePools") or []),
            "ex_rate":  int(e.get("ExtremeRate", 0)),
            "ex_cap":   int(e.get("ExtremeCap", 0)),
            "ex_cd":    int(e.get("ExtremeCooldown", 0)),
            "ex_cnt":   int(e.get("ExtremeCount", 0)),
            "ex_ds":    int(e.get("ExtremeDanger", 0)),
            "ex_hp":    int(e.get("ExtremeHP", 0)),
            "ex_atk":   int(e.get("ExtremeAtk", 0)),
        })
    maps.sort(key=lambda m: (m["realm"] == 0, m["realm"], m["map"]))

    return rows, maps, conf


def dt_rows(rows):
    """十二洞天(0831 規格)那 28 條 —— 用 MinRealm 分境。"""
    return [r for r in rows if not r["pool"]]


def pool_rows(rows, pool=None):
    """0901 規格的共通池。pool=None 取全部。"""
    return [r for r in rows if r["pool"] and (pool is None or r["pool"] == pool)]


def pool_size(rows, realm, rank=4):
    """該境該階, 扣掉互斥組之後最多能塞幾條。

    ★ 這裡的 "pool" 是「候選池大小」的意思, 與 0901 規格的 Pool 欄位無關 ——
      只算十二洞天那 28 條。C 池那批不分境, 混進來會讓每一境都虛胖 6 條。
    """
    ok = [r for r in dt_rows(rows) if r["rank"] <= rank and r["realm"] <= realm]
    grouped = {r["g"] for r in ok if r["g"]}
    free = len([r for r in ok if not r["g"]])
    return len(grouped) + free


def avail(rows, realm):
    return len([r for r in dt_rows(rows) if r["realm"] <= realm])


# ---------------------------------------------------------------- 樣板

TPL = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>萬妖詞綴 — 神域仙境</title>
<meta name="description" content="十二洞天的魔物有機率帶詞綴。五階機率、十二境上限、28 條詞綴的數值與取得條件。">
<meta name="color-scheme" content="light dark">
<meta property="og:type" content="website">
<meta property="og:site_name" content="神域仙境">
<meta property="og:title" content="萬妖詞綴">
<meta property="og:description" content="十二洞天的魔物有機率帶詞綴。五階機率、十二境上限、28 條詞綴的數值與取得條件。">
<meta property="og:image" content="https://drw-online.github.io/game/og.jpg">
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
  --cinnabar:#B8331C; --cinnabar-wash:#B8331C1A; --on-accent:#F8F9F6;
  --focus:#B8331C;
  --shadow:0 1px 2px #1f242212, 0 6px 18px #1f24220a;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ground:#121615; --paper:#1A201E; --sunk:#0D100F;
    --ink:#E4E8E3; --ink-soft:#9AA4A0; --ink-faint:#6E7873;
    --rule:#2A322F; --rule-soft:#222A27;
    --cinnabar:#E0654A; --cinnabar-wash:#E0654A22; --on-accent:#121615;
    --focus:#E0654A;
    --shadow:0 1px 2px #00000040, 0 6px 18px #00000030;
  }
}
:root[data-theme="dark"]{
  --ground:#121615; --paper:#1A201E; --sunk:#0D100F;
  --ink:#E4E8E3; --ink-soft:#9AA4A0; --ink-faint:#6E7873;
  --rule:#2A322F; --rule-soft:#222A27;
  --cinnabar:#E0654A; --cinnabar-wash:#E0654A22; --on-accent:#121615;
  --focus:#E0654A;
  --shadow:0 1px 2px #00000040, 0 6px 18px #00000030;
}
*{box-sizing:border-box}
body{margin:0; background:var(--ground); color:var(--ink);
  font-family:"Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,sans-serif;
  font-size:15px; line-height:1.65; -webkit-font-smoothing:antialiased}
.wrap{max-width:1080px; margin:0 auto; padding:0 20px 76px}
.masthead{padding:32px 0 22px; border-bottom:1px solid var(--rule)}
.home{display:inline-flex; align-items:center; gap:11px; text-decoration:none; margin-bottom:12px}
.home img{width:46px; height:auto; flex:none; display:block}
.home span{font-size:12px; letter-spacing:.34em; color:var(--cinnabar); font-weight:700}
.home:hover span{text-decoration:underline; text-underline-offset:5px}
.home:focus-visible{outline:2px solid var(--focus); outline-offset:3px; border-radius:3px}
h1{margin:0; font-family:"Noto Serif TC",serif; font-size:30px; font-weight:900; letter-spacing:.06em}
h2{margin:0 0 14px; font-family:"Noto Serif TC",serif; font-size:20px; font-weight:700; letter-spacing:.1em}
.lede{margin:14px 0 0; max-width:62ch; color:var(--ink-soft)}
.lede b{color:var(--ink); font-weight:500}
section{margin-top:42px}
.facts{list-style:none; margin:0; padding:0; display:grid; gap:12px;
  grid-template-columns:repeat(auto-fit,minmax(178px,1fr))}
.facts li{background:var(--paper); border:1px solid var(--rule-soft); border-radius:6px;
  padding:16px 18px; box-shadow:var(--shadow)}
.fk{display:block; font-size:12px; letter-spacing:.14em; color:var(--ink-faint)}
.fv{display:block; margin-top:5px; font-family:"Noto Serif TC",serif;
  font-size:23px; font-weight:700; color:var(--cinnabar); font-variant-numeric:tabular-nums}
.fn{display:block; margin-top:3px; font-size:12.5px; color:var(--ink-soft)}
.tbl-wrap{overflow-x:auto; -webkit-overflow-scrolling:touch}
table{border-collapse:collapse; width:100%; font-size:14px; min-width:460px}
th,td{text-align:left; padding:9px 14px; border-bottom:1px solid var(--rule-soft)}
th{font-size:12px; letter-spacing:.14em; color:var(--ink-faint); font-weight:500; white-space:nowrap;
  border-bottom:1px solid var(--rule)}
td.num,th.num{text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap}
td.nm{white-space:nowrap}
td.nm b{font-weight:500}
td.el{white-space:nowrap; color:var(--ink-soft); font-size:13px}
td.st{color:var(--ink-soft); font-size:13px}
td.rate{color:var(--cinnabar); font-weight:500; text-align:right;
  font-variant-numeric:tabular-nums; white-space:nowrap}
tr.off td{color:var(--ink-faint)}
.controls{display:flex; flex-wrap:wrap; gap:9px; align-items:center; margin:0 0 14px}
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
.note{margin:12px 0 0; font-size:13px; color:var(--ink-faint); max-width:66ch}
.note b{color:var(--ink-soft); font-weight:500}
.foot{margin-top:48px; padding-top:20px; border-top:1px solid var(--rule);
  font-size:12.5px; line-height:1.85; color:var(--ink-faint); max-width:76ch}
.foot b{color:var(--ink-soft); font-weight:500}
.foot p{margin:0 0 10px}
.back{display:inline-block; margin-top:6px; color:var(--cinnabar); font-size:13px;
  letter-spacing:.06em; text-decoration:none}
.back:hover{text-decoration:underline; text-underline-offset:5px}
.back:focus-visible{outline:2px solid var(--focus); outline-offset:3px; border-radius:2px}
@media (prefers-reduced-motion:reduce){*{transition:none !important}}
</style>
</head>
<body>
<div class="wrap">

  <header class="masthead">
    <a class="home" href="index.html">
      <img src="logo.webp" width="440" height="440" alt="" decoding="async">
      <span>← 神域仙境 玩家工具</span>
    </a>
    <h1>萬妖詞綴</h1>
    <p class="lede"><b>十二洞天</b>的魔物出生時有機率帶上<b>詞綴</b> —— 數值會變強，掉落也跟著變多。滑鼠移到怪身上，名字底下那行 <b>[巨靈,金剛]</b> 就是牠帶的詞綴。境界越高，一隻身上疊得越多。</p>
  </header>

  <section>
    <h2>一眼</h2>
    <ul class="facts">
      <li><span class="fk">詞綴總數</span><span class="fv">__NAFFIX__</span><span class="fn">洞天 __NDT__ 條＋共通 __NPOOL__ 條，同類互斥</span></li>
      <li><span class="fk">帶詞綴的機率</span><span class="fv">__PCTANY__%</span><span class="fn">其餘 __PCTNONE__% 是普通怪</span></li>
      <li><span class="fk">啟用地圖</span><span class="fv">__NMAP__</span><span class="fn">十二洞天 __NDTMAP__ 張＋靈獸島／鎖妖塔 __NPOOLMAP__ 張</span></li>
      <li><span class="fk">一隻最多帶</span><span class="fv">__MAXCAP__ 條</span><span class="fn">亥境；子境只有 1 條</span></li>
    </ul>
    <p class="note">__ENABLENOTE__</p>
  </section>

  <section>
    <h2>階級</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>階級</th><th class="num">出現率</th><th class="num">詞綴數</th><th class="num">掉落倍率</th></tr></thead>
        <tbody>__RANKROWS__</tbody>
      </table>
    </div>
    <p class="note"><b>詞綴數會被境界砍</b>　抽到天命本來有 5～6 條，但子境上限是 1 條，就只帶 1 條。掉落倍率不受影響，該是 ×3.00 就是 ×3.00。</p>
  </section>

  <section>
    <h2>十二境</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>境</th><th>地圖</th><th class="num">詞綴上限</th><th class="num">可抽詞綴</th></tr></thead>
        <tbody>__REALMROWS__</tbody>
      </table>
    </div>
    <p class="note"><b>可抽詞綴</b>是該境解鎖了幾條。低境抽不到高境的詞綴 —— 例如【萬妖之主】要到酉境以上才出得來。</p>
  </section>

  <section>
    <h2>極道異種</h2>
    <p class="note">十二洞天的怪除了照舊抽境界詞綴，還有一小部分會變成<b>極道異種</b> —— 血量與攻擊大幅提高，詞綴改抽下面的<b>共通池</b>，而且同一張圖同時存在的數量有上限。牠們跟一般帶詞綴的怪是兩套獨立機制，不會互相影響。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>境</th><th class="num">出現率</th><th class="num">同時上限</th><th class="num">詞綴數</th><th class="num">危險值上限</th><th class="num">血量</th><th class="num">攻擊</th></tr></thead>
        <tbody>__EXROWS__</tbody>
      </table>
    </div>
    <p class="note"><b>出現率</b>是該圖的怪變成極道的機率，<b>同時上限</b>是全圖同一時間最多幾隻 —— 打掉之後要等冷卻（洞天 10 分鐘、靈獸島 15 分鐘）才會再出。<b>血量／攻擊</b>是在原本數值上再加的百分比。</p>
  </section>

  <section>
    <h2>靈獸島與鎖妖塔</h2>
    <p class="note">這三張圖不吃境界制，改用<b>共通池</b>與<b>危險值</b>。差別在於：十二洞天是「境界決定解鎖到哪一條」，這裡是「抽幾條由危險值總分決定」—— 所以不會出現低階怪一次帶滿高強度詞綴的情況。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>地圖</th><th>內容</th><th class="num">詞綴上限</th><th>危險值上限（普通→天命）</th></tr></thead>
        <tbody>__POOLMAPROWS__</tbody>
      </table>
    </div>
    <p class="note"><b>詞綴上限</b>管「幾條」，<b>危險值上限</b>管「多凶」—— 兩道閘取先碰到的那一個。4 條危險值 1 的詞綴與 1 條危險值 5 的，條數差很多但凶險程度相近，只用條數擋不住後者。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>詞綴</th><th>類型</th><th class="num">最低階級</th><th class="num">危險值</th><th>效果</th></tr></thead>
        <tbody>__POOLROWS__</tbody>
      </table>
    </div>
    <p class="note">目前共通池只有這 __NPOOL__ 條。靈獸島與鎖妖塔各自的專屬池已經掛上去了但還是空的 —— 規格裡那些「生態、群獵、追跡、伏擊」不是單純加數值，要等事件與排程器做出來才加得進去。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th class="num">危險值總分</th><th class="num">掉落倍率</th></tr></thead>
        <tbody>__DANGERROWS__</tbody>
      </table>
    </div>
    <p class="note">這三張圖的掉落倍率<b>看危險值總分，不看階級</b>，跟十二洞天那張階級表是兩套。卡片、MVP 掉落與固定掉率的物品一樣不吃倍率。</p>
  </section>

  <section>
    <h2>詞綴一覽</h2>
    <div class="controls">
      <input id="q" class="search" type="search" placeholder="搜尋詞綴名稱或效果…" autocomplete="off">
      <button class="chip" data-g="" aria-pressed="true">全部</button>
      __GROUPCHIPS__
    </div>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>詞綴</th><th>類型</th><th class="num">最低階級</th><th class="num">出現於</th><th>效果</th></tr></thead>
        <tbody id="tb"></tbody>
      </table>
    </div>
    <p class="tally" id="tally"></p>
    <p class="note"><b>同一類只會有一條</b>　強生存、高傷、迴避、神話各自互斥 —— 不會出現「巨靈 + 金剛 + 厚土」這種純堆血的組合。命中類刻意不互斥，亥境要湊滿 6 條得靠它們。</p>
  </section>

  <footer class="foot">
    <p><b>怎麼看牠帶了什麼</b>　滑鼠移到怪身上，名字下面會列出詞綴，例如 <b>[巨靈,金剛][稀有]</b> —— 前面是詞綴，後面方括號是階級。怪物名字本身不會變。</p>
    <p><b>詞綴不是永久的</b>　每一隻怪出生時各自抽一次，死了重生會重抽。同一種怪，這隻是天命、下一隻可能是普通。</p>
    <p><b>掉落倍率只加原本會掉的</b>　卡片、MVP 掉落，以及固定掉率的物品都不吃詞綴倍率 —— 不會因為打到天命怪就掉出本來掉不到的東西。</p>
    <p><b>召喚物不帶詞綴</b>　怪召出來的小怪、分身一律不抽，也不會給額外掉落。</p>
    <p><b>Boss 另有規矩</b>　MVP 最多 1 條、Mini Boss 最多 2 條，而且只吃少數允許用在 Boss 身上的詞綴。</p>
    <a class="back" href="index.html">← 回神域仙境玩家工具</a>
  </footer>

</div>
<script>
const DATA = __DATA__;
const tb = document.getElementById("tb"), q = document.getElementById("q"),
      tally = document.getElementById("tally");
let gsel = "";

function draw(){
  const kw = q.value.trim().toLowerCase();
  const hit = DATA.filter(r =>
    (!gsel || r.g === gsel) &&
    (!kw || (r.nm + " " + r.st + " " + r.gn).toLowerCase().includes(kw)));
  tb.innerHTML = hit.map(r =>
    '<tr><td class="nm"><b>' + r.nm + '</b></td>' +
    '<td class="el">' + r.gn + '</td>' +
    '<td class="num">' + r.rankn + '</td>' +
    '<td class="num">' + r.where + '</td>' +
    '<td class="st">' + (r.st || '—') + '</td></tr>').join("")
    || '<tr><td colspan="5" class="st">沒有符合的詞綴。</td></tr>';
  tally.innerHTML = "顯示 <b>" + hit.length + "</b> / " + DATA.length + " 條";
}

document.querySelectorAll(".chip").forEach(b => b.addEventListener("click", () => {
  gsel = b.dataset.g;
  document.querySelectorAll(".chip").forEach(o =>
    o.setAttribute("aria-pressed", o === b ? "true" : "false"));
  draw();
}));
q.addEventListener("input", draw);
draw();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- 產生

def build():
    rows, maps, conf = collect()

    total = sum(conf["rate"]) or 1
    pct = [r * 100.0 / total for r in conf["rate"]]

    rank_rows = "".join(
        '<tr%s><td><b>%s</b></td><td class="num">%.2f%%</td>'
        '<td class="num">%s</td><td class="num rate">×%.2f</td></tr>'
        % (' class="off"' if i == 0 else "", esc(RANK_NAME[i]), pct[i],
           esc(RANK_COUNT[i]), conf["drop"][i] / 10000.0)
        for i in range(5))

    by_realm = {}
    for m in maps:
        by_realm.setdefault(m["realm"], []).append(m["map"])

    realm_rows = "".join(
        '<tr><td><b>%s</b> 境</td><td class="el">%s</td>'
        '<td class="num">%d 條</td><td class="num">%d 條</td></tr>'
        % (esc(REALM_NAME[r - 1]), esc("、".join(by_realm.get(r, ["—"]))),
           REALM_CAP[r], avail(rows, r))
        for r in range(1, 13))

    groups = []
    for r in rows:
        if r["g"] not in [g for g, _ in groups]:
            groups.append((r["g"], r["gn"]))
    group_chips = "".join(
        '<button class="chip" data-g="%s" aria-pressed="false">%s</button>'
        % (esc(g), esc(n)) for g, n in groups if g)

    data = [{
        "nm": r["nm"], "g": r["g"], "gn": r["gn"], "st": r["st"],
        "rankn": RANK_NAME[r["rank"]],
        "realm": r["realm"],
        "realmn": REALM_NAME[r["realm"] - 1] if r["realm"] else "",
        # ★ 共通池那批的 realm 是 0, 但那不等於「不限」—— 它們只出現在
        #   靈獸島/鎖妖塔, 以及十二洞天的極道異種身上。直接算好要顯示的字,
        #   不要讓前端用 realm 去猜。
        "where": (REALM_NAME[r["realm"] - 1] + " 境↑") if r["realm"]
                 else ("共通池 · 危險值 %d" % r["ds"]),
    } for r in rows]

    # 子境是 dongtian1_1 / dongtian1_2 兩張分流圖, 參數完全相同 ——
    # 逐圖列會變成兩列一模一樣的「子 境」。同境同參數的只留一列。
    ex_maps, _seen = [], set()
    for m in maps:
        if not m["ex_rate"]:
            continue
        key = (m["realm"], m["ex_rate"], m["ex_cap"], m["ex_cnt"],
               m["ex_ds"], m["ex_hp"], m["ex_atk"]) if m["realm"] else m["map"]
        if key in _seen:
            continue
        _seen.add(key)
        ex_maps.append(m)

    ex_rows = "".join(
        '<tr><td><b>%s</b></td><td class="num">%.4g%%</td><td class="num">%d 隻</td>'
        '<td class="num">%d 條</td><td class="num">%d</td>'
        '<td class="num rate">+%d%%</td><td class="num rate">+%d%%</td></tr>'
        % (esc(REALM_NAME[m["realm"] - 1] + " 境" if m["realm"]
                else {"bossnia_01": "靈獸島 MVP", "bossnia_02": "靈獸島魔物"}
                     .get(m["map"], m["map"])),
           m["ex_rate"] / 100.0, m["ex_cap"], m["ex_cnt"], m["ex_ds"],
           m["ex_hp"], m["ex_atk"])
        for m in ex_maps)

    MAP_DESC = {
        "bossnia_01": "靈獸島 · 190 隻 MVP",
        "bossnia_02": "靈獸島 · 162 種神域魔物",
        "suoyao01":   "鎖妖塔",
    }
    poolmap_rows = "".join(
        '<tr><td class="el">%s</td><td>%s</td><td class="num">%d 條</td>'
        '<td class="num">%s</td></tr>'
        % (esc(m["map"]), esc(MAP_DESC.get(m["map"], "—")), m["cap"],
           esc(" / ".join(str(c) for c in m["dcaps"]) or "—"))
        for m in maps if m["realm"] == 0)

    pool_list = pool_rows(rows)
    poolrows_html = "".join(
        '<tr><td class="nm"><b>%s</b></td><td class="el">%s</td>'
        '<td class="num">%s</td><td class="num">%d</td><td class="st">%s</td></tr>'
        % (esc(r["nm"]), esc(r["gn"]), esc(RANK_NAME[r["rank"]]), r["ds"],
           esc(r["st"] or "—"))
        for r in pool_list)

    danger_rows = "".join(
        '<tr><td class="num">%s</td><td class="num rate">×%.2f</td></tr>'
        % (esc(lo), mult) for lo, mult in DANGER_BAND)

    where = "十二洞天、靈獸島與鎖妖塔"
    if conf["enable"]:
        note = ("<b>目前已啟用。</b>只有%s的自然生成魔物會抽詞綴，"
                "主城、新手村、任務圖與 PVP／GVG 一律不掛。" % where)
    else:
        note = "<b>目前尚未啟用。</b>設定已就位，開啟後%s的魔物會抽詞綴。" % where

    out = TPL
    for k, v in [
        ("__NAFFIX__",     str(len(rows))),
        ("__NDT__",        str(len(dt_rows(rows)))),
        ("__NPOOL__",      str(len(pool_list))),
        ("__NGROUP__",     str(len(groups))),
        ("__NMAP__",       str(len(maps))),
        ("__NDTMAP__",     str(len([m for m in maps if m["realm"]]))),
        ("__NPOOLMAP__",   str(len([m for m in maps if not m["realm"]]))),
        ("__EXROWS__",       ex_rows),
        ("__POOLMAPROWS__",  poolmap_rows),
        ("__POOLROWS__",     poolrows_html),
        ("__DANGERROWS__",   danger_rows),
        ("__MAXCAP__",     str(max(REALM_CAP))),
        ("__PCTANY__",     "%g" % round(100.0 - pct[0], 2)),
        ("__PCTNONE__",    "%g" % round(pct[0], 2)),
        ("__ENABLENOTE__", note),
        ("__RANKROWS__",   rank_rows),
        ("__REALMROWS__",  realm_rows),
        ("__GROUPCHIPS__", group_chips),
        ("__DATA__",       json.dumps(data, ensure_ascii=False, separators=(",", ":"))),
    ]:
        out = out.replace(k, v)

    dest = os.path.join(WEB, "mobaffix.html")
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    return dest, rows, maps, conf, out


# ---------------------------------------------------------------- 驗證

def verify(dest, rows, maps, conf, out):
    ok = True

    def chk(cond, msg):
        nonlocal ok
        ok = ok and bool(cond)
        print("  %s  %s" % ("ok  " if cond else "FAIL", msg))

    print("  ----  %s" % os.path.basename(dest))

    ids = [r["id"] for r in rows]
    chk(len(ids) == len(set(ids)), "詞綴 Id 唯一 (%d 條)" % len(ids))
    chk(all(1 <= r["rank"] <= 4 for r in rows), "MinRank 都在 1~4")
    chk(all(0 <= r["realm"] <= 12 for r in rows), "MinRealm 都在 0~12")
    chk(all(r["st"] for r in rows), "每一條詞綴都有數值效果")

    chk(sum(conf["rate"]) == 10000,
        "五階機率合計 10000 (實際 %d)" % sum(conf["rate"]))
    chk(all(d >= 10000 for d in conf["drop"]), "掉落倍率都 >= x1.00")
    chk(conf["drop"] == sorted(conf["drop"]), "掉落倍率隨階級遞增")

    chk(REALM_CAP[1:] == [1, 1, 2, 2, 3, 3, 4, 4, 4, 5, 5, 6],
        "十二境上限與規格 §1.2 相同")

    chk(len(maps) == len({m["map"] for m in maps}), "地圖不重複 (%d 張)" % len(maps))
    # ★ 只拿境界制那批比對。0901 規格的三張圖 Realm 一律是 0, 混進來會讓
    #   集合變成 {0,1..12} 而永遠不等於 {1..12} —— 那不是資料錯。
    chk({m["realm"] for m in maps if m["realm"]} == set(range(1, 13)),
        "十二境都有地圖")
    chk(all(m["mode"] in ("OFF", "OPT_IN", "MAP_ALL") for m in maps), "地圖模式合法")

    short = [r for r in range(1, 13) if pool_size(rows, r) < REALM_CAP[r]]
    chk(not short,
        "每境的詞綴池湊得滿上限" + ("" if not short else " — 不足: %s" % short))

    # ---- 0901 規格(共通池 / 危險值 / 極道異種) ----
    pl = pool_rows(rows)
    dt = dt_rows(rows)
    chk(len(dt) + len(pl) == len(rows) and pl and dt,
        "兩套規格都解析到 (洞天 %d + 共通池 %d)" % (len(dt), len(pl)))
    chk(all(r["realm"] == 0 for r in pl),
        "共通池那批沒有 MinRealm (有的話代表兩套規格混用了)")
    chk(all(r["ds"] > 0 for r in pl), "共通池每一條都有 DangerScore")
    chk(all(r["ds"] == 0 for r in dt),
        "洞天那批沒有 DangerScore (它們走階級掉落表)")
    chk(all(GROUP_NAME.get(r["g"]) for r in pl),
        "共通池的互斥組都有中文譯名 (%s)"
        % "/".join(sorted({r["gn"] for r in pl})))

    pmaps = [m for m in maps if not m["realm"]]
    chk(len(pmaps) == 3 and all(m["pools"] and m["dcaps"] for m in pmaps),
        "0901 那 3 張圖都有 Pools 與 DangerCaps (實得 %d 張)" % len(pmaps))
    chk(all(len(m["dcaps"]) == 5 for m in pmaps),
        "DangerCaps 都是 5 格 (普通~天命)")
    chk(all(m["dcaps"] == sorted(m["dcaps"]) for m in pmaps),
        "DangerCaps 隨階級遞增")

    # 極道異種在十二洞天也有 —— 這條就是防止「以為只有新圖才有」而漏寫
    ex = [m for m in maps if m["ex_rate"]]
    chk(len(ex) == 15,
        "15 張圖有極道異種 (13 洞天 + 靈獸島 2, 實得 %d)" % len(ex))
    dt_ex = sorted((m["realm"], m["ex_rate"]) for m in ex if m["realm"])
    chk([r for _, r in dt_ex] == sorted(r for _, r in dt_ex),
        "洞天的極道出現率隨境遞增")
    chk(all(m["ex_hp"] and m["ex_atk"] and m["ex_cnt"] for m in ex),
        "極道的血量/攻擊/詞綴數都有填")

    chk(not re.search(r"__[A-Z]+__", out), "樣板佔位全部替換")
    chk("<script>" in out and "DATA" in out, "資料已嵌入")

    print("  ----  %s   (%.0f KB)" % ("PASS" if ok else "FAIL",
                                      len(out.encode("utf-8")) / 1024))
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if verify(*build()) else 1)

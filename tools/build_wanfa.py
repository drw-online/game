# -*- coding: utf-8 -*-
"""
萬法星盤圖鑑產生器 —— 產生 wanfa.html, 跑完自己驗證一次。

用法(需要 PyYAML):

    python tools/build_wanfa.py

會覆寫 wanfa.html。輸出是決定性的 —— 來源沒變的話重跑一次 git status
應該是乾淨的, 這也是最好的回歸測試。

--------------------------------------------------------------------------
來源
--------------------------------------------------------------------------
  script/04.系統/73.萬法星盤.txt      OnInit 的 13 張平行 setarray + 全部參數
  script/10.鎖妖塔/00.設定.txt        $@SY_MAXFLOOR (目前開放層數)
  db/re/skill_db.yml + db/import      技能中文名(Description)與 MaxLevel
  db/import/blackgod/item_daopan.yml  洗點材料名(與大道星盤共用)
  conf/battle/blackgod.conf           PvP 觸發率 / 傷害調整

★ 13 張表是「索引即節點編號」對齊填寫的, 少一格會讓該格之後全部錯位而且
  不報錯。verify() 逐表比對鍵集合, 就是在擋這件事。

★ 技能中文名要用 skill_db 的 Description 不是 Name —— Name 是
  AegisName(SM_BASH)。腳本裡用的是 getskillinfo(SKI_DESCRIPTION, id),
  上游的 getskillname 在本服不存在。

★ $@wf_slv + $@wf_sinc*(Lv-1) 不可超過該技能的 MaxLevel。超過不會報錯,
  技能資料會讀到範圍外 —— verify() 逐節點檢查滿級時的值。
"""
import os, re, json, html
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
WEB  = os.path.dirname(HERE)
ROOT = r"H:\91.神域仙境"
SRV  = os.path.join(ROOT, "2.開機擋")
WF    = os.path.join(SRV, r"script\04.系統\73.萬法星盤.txt")
TOWER = os.path.join(SRV, r"script\10.鎖妖塔\00.設定.txt")
CONF  = os.path.join(SRV, r"conf\battle\blackgod.conf")

# BF 遮罩常數 -> 玩家看得懂的觸發條件。定義就在 OnInit 開頭;
# 常數名若改了這裡會對到 None, verify() 抓得到。
BF_LABEL = {
    "$@WF_BF_PM":  "近戰普攻",
    "$@WF_BF_PMS": "近戰普攻 · 物理技能",
    "$@WF_BF_PR":  "遠程普攻",
    "$@WF_BF_PRS": "遠程普攻 · 物理技能",
    "$@WF_BF_MG":  "魔法技能",
    "$@WF_BF_ANY": "任何攻擊",
}

RING_DESC = {
    0: "路線入口，本身不觸發技能",
    1: "高頻小效果，一轉技能",
    2: "流派成形，二轉技能",
    3: "強力效果，三轉技能",
    4: "核心爆發，四轉技能",
    5: "不放技能，改為加成指定路線的觸發率",
}


def read(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


# ---------------------------------------------------------------- 腳本解析

def setarrays(t, name):
    """抓 setarray $@<name>[起始], v1, v2, ...; 回傳 {索引: 原始字串}。

    ★ 前面的 `setarray\\s+` 不能省 —— NPC 那段也在讀同一批陣列(例如
      $@WF_RING$[0]), 少了前綴會把「使用」當成「定義」抓進來, 而且不報錯,
      只是名稱欄變成一段程式碼碎片。
    """
    out = {}
    for m in re.finditer(r"setarray\s+" + re.escape("$@" + name)
                         + r"\[(\d+)\]\s*,(.*?);", t, re.S):
        start = int(m.group(1))
        for i, v in enumerate(x.strip() for x in m.group(2).split(",")):
            if v:
                out[start + i] = v
    return out


def scalar(t, name):
    m = re.search(re.escape("$@" + name) + r"\s*=\s*([^;]+);", t)
    if not m:
        raise SystemExit("找不到 $@%s" % name)
    return int(m.group(1).strip())


def parse_script():
    t = re.sub(r"//[^\n]*", "", read(WF))          # 去掉行註解再解析
    ints = lambda n: {k: int(v) for k, v in setarrays(t, n).items()}
    strs = lambda n: {k: v.strip('"') for k, v in setarrays(t, n).items()}

    node = {
        "nm":    strs("wf_name$"),
        "ring":  ints("wf_ring"),
        "route": ints("wf_route"),
        "pre":   ints("wf_pre"),
        "sk":    ints("wf_skill"),
        "bf":    setarrays(t, "wf_bf"),            # 常數名, 保持字串
        "icd":   ints("wf_icd"),
        "dmg":   ints("wf_dmg"),
        "flag":  ints("wf_flag"),
        "rate":  ints("wf_rate"),
        "rinc":  ints("wf_rinc"),
        "slv":   ints("wf_slv"),
        "sinc":  ints("wf_sinc"),
        "cr1":   ints("wf_cr1"),
        "cr2":   ints("wf_cr2"),
        "cbon":  ints("wf_cbon"),
    }
    meta = {
        "ver":       scalar(t, "WF_VER"),
        "pt_max":    scalar(t, "WF_PT_MAX"),
        "cost_base": scalar(t, "WF_COST_BASE"),
        "cost_core": scalar(t, "WF_COST_CORE"),
        "maxlv":     scalar(t, "WF_MAXLV"),
        "respec":    scalar(t, "WF_ITEM_RESPEC"),
        "reset":     scalar(t, "WF_ITEM_RESET"),
        "cum":       [int(v) for _, v in sorted(setarrays(t, "WF_CUM").items())],
        "ring$":     [v for _, v in sorted(strs("WF_RING$").items())],
        "route$":    strs("WF_ROUTE$"),
        "grant":     ints("wf_grant"),
        "syg":       ints("wf_syg"),
    }
    return node, meta


def read_tower_floors():
    return int(re.search(r"\$@SY_MAXFLOOR\s*=\s*(\d+)", read(TOWER)).group(1))


def read_pvp():
    t = read(CONF)
    g = lambda k: int(re.search(r"^%s:\s*(\d+)" % k, t, re.M).group(1))
    return g("astrolabe_pvp_proc_rate"), g("astrolabe_pvp_damage_rate")


def read_skills(ids):
    """技能中文名取 Description 不是 Name(那是 AegisName)。"""
    want, got = set(ids), {}
    for rel in ("db/re/skill_db.yml", "db/import/skill_db.yml"):
        p = os.path.join(SRV, rel.replace("/", os.sep))
        if not os.path.exists(p):
            continue
        for s in (yaml.safe_load(open(p, encoding="utf-8-sig")) or {}).get("Body") or []:
            if s.get("Id") in want:
                cur = got.setdefault(s["Id"], {})
                for k in ("Description", "MaxLevel"):
                    if k in s:
                        cur[k] = s[k]
    return got


def read_items(ids):
    out = {}
    d = os.path.join(SRV, "db", "import", "blackgod")
    for fn in sorted(os.listdir(d)):
        if not (fn.startswith("item_") and fn.endswith(".yml")):
            continue
        for it in (yaml.safe_load(open(os.path.join(d, fn), encoding="utf-8-sig")) or {}).get("Body") or []:
            if it.get("Id") in ids:
                out[it["Id"]] = it["Name"]
    return out


# ---------------------------------------------------------------- 組裝

def pct(milli):
    return ("%.1f" % (milli / 10)).rstrip("0").rstrip(".") + "%"


def sec(ms):
    return ("%.1f" % (ms / 1000)).rstrip("0").rstrip(".") + " 秒"


def esc(s):
    return html.escape(str(s), quote=False)


def collect():
    node, meta = parse_script()
    skills = read_skills([v for v in node["sk"].values() if v > 0])

    rows = []
    for nid in sorted(node["nm"]):
        ring = node["ring"][nid]
        sk = node["sk"][nid]
        lvmax = 1 if ring in (0, 5) else meta["maxlv"]
        rate, rinc = node["rate"][nid], node["rinc"][nid]
        slv, sinc = node["slv"][nid], node["sinc"][nid]
        icd = node["icd"][nid]

        r1 = min(rate, 1000)
        r5 = min(rate + rinc * (lvmax - 1), 1000)

        rows.append({
            "id": nid,
            "nm": node["nm"][nid],
            "ring": ring,
            "rings": meta["ring$"][ring],
            "route": node["route"][nid],
            "routes": meta["route$"][node["route"][nid]],
            "pre": node["pre"][nid],
            "pren": node["nm"].get(node["pre"][nid], ""),
            "sk": sk,
            "skn": skills.get(sk, {}).get("Description", ""),
            "skmax": skills.get(sk, {}).get("MaxLevel", 0),
            "bf": BF_LABEL.get(node["bf"][nid]),
            "icd": icd,
            "icds": sec(icd) if icd else "",
            "dmg": node["dmg"][nid],
            "flag": node["flag"][nid],
            "lvmax": lvmax,
            "cost": (meta["cost_base"] if ring == 0 else
                     meta["cost_core"] if ring == 5 else meta["cum"][lvmax]),
            "r1": r1, "r5": r5, "r1s": pct(r1), "r5s": pct(r5),
            "l1": slv, "l5": slv + sinc * (lvmax - 1),
            "rinc": rinc, "rincs": pct(rinc), "sinc": sinc,
            "cr1": meta["route$"].get(node["cr1"].get(nid, 0), ""),
            "cr2": meta["route$"].get(node["cr2"].get(nid, 0), ""),
            "cbon": node["cbon"].get(nid, 0),
        })

    items = read_items({meta["respec"], meta["reset"]})
    meta["floors"] = read_tower_floors()
    meta["pvp_rate"], meta["pvp_dmg"] = read_pvp()
    meta["respec$"] = items[meta["respec"]]
    meta["reset$"] = items[meta["reset"]]
    meta["realms"] = len(meta["grant"])
    meta["pt_realm"] = sum(meta["grant"].values())
    meta["pt_tower_all"] = sum(meta["syg"].values())
    meta["pt_tower_now"] = sum(v for k, v in meta["syg"].items() if k <= meta["floors"])
    meta["pt_now"] = min(meta["pt_realm"] + meta["pt_tower_now"], meta["pt_max"])
    return rows, meta


# ---------------------------------------------------------------- HTML

TPL = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>萬法星盤 · 神域仙境</title>
<meta name="description" content="萬法星君的萬法星盤：__NNODE__ 個節點，攻擊與受擊時自動觸發跨職業技能。">
<meta name="color-scheme" content="light dark">
<meta property="og:type" content="website">
<meta property="og:site_name" content="神域仙境">
<meta property="og:title" content="萬法星盤">
<meta property="og:description" content="__NNODE__ 個節點，攻擊與受擊時自動觸發跨職業技能。">
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

.steps{list-style:none; margin:0; padding:0; display:grid; gap:10px}
.steps li{background:var(--paper); border:1px solid var(--rule-soft); border-radius:6px;
  padding:14px 18px; font-size:14px; display:flex; gap:14px; align-items:baseline; flex-wrap:wrap}
.steps .rn{font-family:"Noto Serif TC",serif; font-size:15px; font-weight:700;
  color:var(--cinnabar); letter-spacing:.06em; flex:none; min-width:5.6em}
.steps .rd{color:var(--ink-soft); flex:1 1 260px}
.steps .rd b{color:var(--ink); font-weight:500}

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

#nodes{min-width:840px}
tr.node{cursor:pointer}
tr.node:hover{background:var(--sunk)}
tr.node:focus-visible{outline:2px solid var(--focus); outline-offset:-2px}
td.oid{font-variant-numeric:tabular-nums; color:var(--ink-faint); width:1%; white-space:nowrap}
td.nm{white-space:nowrap}
td.nm b{font-weight:500}
.tag{display:inline-block; margin-right:7px; padding:1px 7px; border-radius:100px;
  font-size:11px; letter-spacing:.08em; vertical-align:1px; white-space:nowrap}
.tag.r0{background:var(--sunk); color:var(--ink-soft); border:1px solid var(--rule)}
.tag.r5{background:var(--cinnabar); color:var(--on-accent)}
.tag.rn{background:var(--cinnabar-wash); color:var(--cinnabar); border:1px solid var(--cinnabar)}
td.sk{color:var(--ink-soft); font-size:13px}
td.sk b{color:var(--ink); font-weight:500}
td.sk .hit{color:var(--cinnabar); font-size:12px; margin-left:8px}
td.el{white-space:nowrap; color:var(--ink-soft); font-size:13px}
td.rate{color:var(--cinnabar); font-weight:500; text-align:right;
  font-variant-numeric:tabular-nums; white-space:nowrap}
tr.detail > td{background:var(--sunk); padding:0}
.dwrap{padding:16px 18px 20px}
.grid{display:grid; gap:10px 26px; grid-template-columns:repeat(auto-fit,minmax(132px,1fr));
  margin:0; padding:0; list-style:none}
.grid li{font-size:13px}
.grid b{display:block; font-size:11px; letter-spacing:.14em; color:var(--ink-faint); font-weight:500}
.grid span{color:var(--ink)}
.empty{padding:40px 0; text-align:center; color:var(--ink-faint)}
.note{margin:12px 0 0; font-size:13px; color:var(--ink-faint); max-width:66ch}
.note b{color:var(--ink-soft); font-weight:500}
.note a{color:var(--cinnabar)}
</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <a class="home" href="index.html">
      <img src="logo.webp" width="440" height="440" alt="" decoding="async">
      <span>← 神域仙境 玩家工具</span>
    </a>
    <h1>萬法星盤</h1>
    <p class="lede">在<b>普羅酒館</b>找<b>萬法星君</b>開啟。點亮星辰之後，你的<b>普攻、技能與受擊</b>都有機率自動放出別的職業的招式 —— 不必去學那個職業。全盤 __NNODE__ 個節點，但你一輩子只拿得到 __PTMAX__ 點。</p>
  </header>

  <section>
    <h2>先看這幾個數字</h2>
    <ul class="facts">
      <li><span class="fk">節點總數</span><span class="fv">__NNODE__</span><span class="fn">全部點滿要 __TOTALCOST__ 點</span></li>
      <li><span class="fk">點數上限</span><span class="fv">__PTMAX__</span><span class="fn">一條主修 ＋ 一條副修，是刻意的設計</span></li>
      <li><span class="fk">目前拿得到</span><span class="fv">__PTNOW__</span><span class="fn">境界 __PTREALM__ ＋ 鎖妖塔 __PTTOWER__</span></li>
      <li><span class="fk">開啟條件</span><span class="fv">免費</span><span class="fn">找萬法星君說一聲就開</span></li>
    </ul>
    <p class="note">星盤跟<a href="daopan.html">大道星盤</a>是<b>兩套完全分開</b>的東西 —— 點數、存檔、NPC 都不共用。大道給的是被動數值（ATK／血量／減傷），萬法給的是<b>主動觸發技能</b>。唯一共用的是洗點石頭。</p>
  </section>

  <section>
    <h2>點數哪裡來</h2>
    <ul class="steps">
      <li><span class="rn">境界突破</span><span class="rd">每突破一境給 <b>__GRANTEACH__ 點</b>，__NREALM__ 境全滿共 <b>__PTREALM__ 點</b></span></li>
      <li><span class="rn">鎖妖塔</span><span class="rd">每層<b>首次</b>通關給 <b>__SYGEACH__ 點</b>，設計 __NTOWER__ 層共 __PTTOWERALL__ 點；目前開放到<b>第 __FLOORS__ 層</b>，所以實際拿得到 <b>__PTTOWER__ 點</b></span></li>
    </ul>
    <p class="note">兩邊加起來 __PTALL__ 點，比上限 __PTMAX__ 點多 —— 這是<b>刻意</b>的，讓你不必兩條路都走滿。鎖妖塔開放更多層之後，那 __PTMAX__ 點才會真的用得完。點數是<b>算總額補差</b>，不會重複發，配點表調整也不會把你已經加的點洗掉。</p>
  </section>

  <section>
    <h2>星環與花費</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>星環</th><th class="num">節點</th><th class="num">最高等級</th><th class="num">點滿要</th><th>作用</th></tr></thead>
        <tbody>__RINGS__</tbody>
      </table>
    </div>
    <p class="note">一到四環升級的<b>累計</b>花費是 __CUM__ 點（Lv1~4 各 1 點，覺醒的 Lv5 要 2 點）。升級會同時提高<b>觸發機率</b>與<b>技能等級</b>。基礎星與主星都只有 1 級。</p>
  </section>

  <section>
    <h2>核心主星</h2>
    <p class="note" style="margin-top:0">主星自己不放技能，而是幫<b>指定路線</b>的所有節點加觸發率。<b>同時只能啟用一顆</b>，但可以各自投資、隨時換，換的時候不用花石頭。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>主星</th><th>受惠路線</th><th class="num">觸發率</th><th>前置節點</th></tr></thead>
        <tbody>__CORES__</tbody>
      </table>
    </div>
    <p class="note">單系主星只吃一條路線但倍率高，雙系共鳴吃兩條路線但倍率低 —— 專精還是兼顧，自己選。主星要<b>投資過</b>才算數，退點退掉的話加成會跟著消失。</p>
  </section>

  <section>
    <h2>全部節點</h2>
    <div class="controls">
      <div class="ctl-row">
        <input id="q" class="search" type="search" placeholder="搜尋節點或技能名…　例：火、狂擊、審判、302" aria-label="搜尋節點">
      </div>
      <div class="ctl-row">
        <span class="glab">星環</span>
        <div id="ring" class="ctl-row" role="group" aria-label="星環"></div>
      </div>
      <div class="ctl-row">
        <span class="glab">路線</span>
        <div id="route" class="ctl-row" role="group" aria-label="路線"></div>
      </div>
      <div class="ctl-row">
        <span class="glab">觸發</span>
        <div id="bf" class="ctl-row" role="group" aria-label="觸發條件"></div>
      </div>
      <p class="tally" id="tally"></p>
    </div>
    <div class="tbl-wrap">
      <table id="nodes">
        <thead><tr>
          <th class="num">編號</th><th>節點</th><th>路線</th>
          <th>觸發技能</th><th>觸發條件</th>
          <th class="num">Lv1</th><th class="num">滿級</th>
        </tr></thead>
        <tbody id="rows"></tbody>
      </table>
    </div>
    <div class="empty" id="empty" hidden>沒有符合條件的節點。</div>
    <p class="note">「Lv1／滿級」是<b>觸發機率</b>。點任一列可展開技能等級、冷卻、傷害倍率與前置節點。</p>
  </section>

  <section>
    <h2>洗點</h2>
    <ul class="steps">
      <li><span class="rn">__RESPEC__</span><span class="rd">x1 —— 指定節點<b>退 1 級</b>，退回的點數可以重點</span></li>
      <li><span class="rn">__RESET__</span><span class="rd">x1 —— <b>整盤重置</b>，所有節點歸零、主星取消，點數全部退回</span></li>
    </ul>
    <p class="note">這兩顆石頭與大道星盤共用 —— 你不必記兩套材料，而兩邊的點數本來就各自獨立，洗哪一邊都不會影響另一邊。</p>
  </section>

  <footer class="foot">
    <p><b>技能可以跨職業</b>　節點觸發的招式不需要你的職業學得會，也不吃你的 SP —— 每個節點有自己的冷卻，與你手動放技能的冷卻互不干擾。</p>
    <p><b>觸發條件要看清楚</b>　寫「近戰普攻」的節點只有普攻能觸發，要吃技能得看到「物理技能」四個字。魔法路線一律是魔法技能觸發。</p>
    <p><b>受擊型節點</b>　少數節點是<b>被打的時候</b>才觸發，表上會標出來 —— 有的是對自己（補血、防護），有的是反打對方。</p>
    <p><b>傷害會打折</b>　高環技能的傷害刻意調低（四環只剩 55~60%）—— 那些招的原始倍率不是設計給自動觸發用的。展開後沒特別標的就是不打折。</p>
    <p><b>PvP 另外算</b>　對玩家時觸發率只有 __PVPRATE__%、傷害只有 __PVPDMG__%。</p>
    <p><b>技能等級有上限</b>　每個節點的技能等級最高只到該技能本身的上限，升到滿級也不會超過。</p>
    <a class="back" href="index.html">← 回神域仙境玩家工具</a>
  </footer>
</div>

<script>
const NODES = __DATA__;

const F = {q:"", ring:"", route:"", bf:""};
const $ = s => document.querySelector(s);
const rowsEl = $("#rows"), emptyEl = $("#empty"), tallyEl = $("#tally");

function chips(host, key, list, allLabel){
  const mk = (label, val) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "chip"; b.textContent = label;
    b.dataset.v = String(val);
    b.setAttribute("aria-pressed", String(F[key] === val));
    b.onclick = () => {
      F[key] = F[key] === val ? "" : val;
      host.querySelectorAll(".chip").forEach(c =>
        c.setAttribute("aria-pressed", String(c.dataset.v === String(F[key]))));
      render();
    };
    return b;
  };
  host.appendChild(mk(allLabel, ""));
  list.forEach(([label, val]) => host.appendChild(mk(label, val)));
}

function detail(n){
  const tr = document.createElement("tr");
  tr.className = "detail";
  const td = document.createElement("td");
  td.colSpan = 7;

  const rows = [["前置節點", n.pre ? n.pren + "（#" + n.pre + "）" : "起點，沒有前置"]];
  if (n.sk){
    rows.push(
      ["技能等級", n.l1 === n.l5 ? "Lv" + n.l1 + "（升級不加等級）" : "Lv" + n.l1 + " → Lv" + n.l5],
      ["冷卻", n.icd ? n.icds : "無"],
      ["傷害倍率", n.dmg === 1000 ? "100%（不打折）" : (n.dmg / 10) + "%"],
      ["觸發時機", (n.flag & 8) ? "受擊時" : "攻擊時"],
      ["施放對象", (n.flag & 1) ? "對敵人" : "對自己"],
      ["每級提升", "機率 +" + n.rincs + (n.sinc ? "、技能等級 +" + n.sinc : "")],
    );
  } else if (n.ring === 5){
    rows.push(["共鳴效果",
      n.cr1 + (n.cr2 ? "、" + n.cr2 : "") + " 路線的觸發率 ×" + (n.cbon / 10) + "%"]);
  } else {
    rows.push(["效果", "路線入口，本身不觸發技能"]);
  }
  rows.push(["點滿花費",
    n.cost + " 點" + (n.lvmax > 1 ? "（Lv" + n.lvmax + "）" : "（只有 1 級）")]);

  const ul = document.createElement("ul");
  ul.className = "grid";
  for (const [k, v] of rows){
    const li = document.createElement("li");
    const b = document.createElement("b"); b.textContent = k;
    const s = document.createElement("span"); s.textContent = v;
    li.append(b, s); ul.appendChild(li);
  }

  const box = document.createElement("div");
  box.className = "dwrap";
  box.appendChild(ul);
  td.appendChild(box); tr.appendChild(td);
  return tr;
}

function row(n){
  const tr = document.createElement("tr");
  tr.className = "node";
  tr.tabIndex = 0;

  const cells = [
    ["num oid", n.id], ["nm", null], ["el", n.routes],
    ["sk", null], ["el", n.bf || "—"],
    ["rate", n.sk ? n.r1s : "—"], ["rate", n.sk ? n.r5s : "—"],
  ];
  cells.forEach(([cls, val], i) => {
    const td = document.createElement("td");
    td.className = cls;
    if (i === 1){
      const tag = document.createElement("span");
      tag.className = "tag " + (n.ring === 0 ? "r0" : n.ring === 5 ? "r5" : "rn");
      tag.textContent = n.rings;
      const b = document.createElement("b");
      b.textContent = n.nm;
      td.append(tag, b);
    } else if (i === 3){
      if (n.sk){
        const b = document.createElement("b");
        b.textContent = n.skn;
        td.append(b);
        if (n.flag & 8){
          const s = document.createElement("span");
          s.className = "hit";
          s.textContent = "受擊觸發";
          td.append(s);
        }
      } else {
        td.textContent = n.ring === 5 ? "共鳴加成" : "路線入口";
      }
    } else {
      td.textContent = val;
    }
    tr.appendChild(td);
  });

  let open = null;
  const toggle = () => {
    if (open){ open.remove(); open = null; return; }
    open = detail(n);
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
  const list = NODES.filter(n =>
    (F.ring === "" || n.ring === F.ring) &&
    (!F.route || n.routes === F.route) &&
    (!F.bf || n.bf === F.bf) &&
    (!q || n.nm.toLowerCase().includes(q) || (n.skn || "").toLowerCase().includes(q)
        || n.routes.includes(q) || String(n.id).includes(q))
  );
  rowsEl.replaceChildren(...list.map(row));
  emptyEl.hidden = list.length > 0;
  const cost = list.reduce((a, n) => a + n.cost, 0);
  tallyEl.innerHTML = "顯示 <b>" + list.length + "</b> 個節點　（全部點滿要 " + cost + " 點）";
}

chips($("#ring"),  "ring",  __RINGCHIPS__,  "全部");
chips($("#route"), "route", __ROUTECHIPS__, "全部");
chips($("#bf"),    "bf",    __BFCHIPS__,    "全部");
$("#q").addEventListener("input", e => { F.q = e.target.value; render(); });
render();
</script>
</body>
</html>
"""


def build():
    rows, meta = collect()

    by_ring = {}
    for n in rows:
        by_ring.setdefault(n["ring"], []).append(n)

    rings_html = "".join(
        '<tr><td>%s</td><td class="num">%d</td><td class="num">%d</td>'
        '<td class="num">%d</td><td class="el">%s</td></tr>'
        % (esc(meta["ring$"][r]), len(ns), ns[0]["lvmax"],
           sum(n["cost"] for n in ns), esc(RING_DESC[r]))
        for r, ns in sorted(by_ring.items()))

    cores_html = "".join(
        '<tr><td><b>%s</b></td><td class="el">%s</td>'
        '<td class="num rate">×%d%%</td><td class="el">%s</td></tr>'
        % (esc(n["nm"]), esc(n["cr1"] + ("、" + n["cr2"] if n["cr2"] else "")),
           n["cbon"] // 10, esc(n["pren"]))
        for n in rows if n["ring"] == 5)

    bfs = []
    for n in rows:
        if n["bf"] and n["bf"] not in bfs:
            bfs.append(n["bf"])

    out = TPL
    for k, v in [
        ("__NNODE__", str(len(rows))),
        ("__PTMAX__", str(meta["pt_max"])),
        ("__TOTALCOST__", str(sum(n["cost"] for n in rows))),
        ("__PTNOW__", str(meta["pt_now"])),
        ("__PTREALM__", str(meta["pt_realm"])),
        ("__PTTOWERALL__", str(meta["pt_tower_all"])),
        ("__PTTOWER__", str(meta["pt_tower_now"])),
        ("__PTALL__", str(meta["pt_realm"] + meta["pt_tower_all"])),
        ("__NREALM__", str(meta["realms"])),
        ("__NTOWER__", str(len(meta["syg"]))),
        ("__GRANTEACH__", str(sorted(set(meta["grant"].values()))[0])),
        ("__SYGEACH__", str(sorted(set(meta["syg"].values()))[0])),
        ("__FLOORS__", str(meta["floors"])),
        ("__CUM__", " / ".join(str(c) for c in meta["cum"][1:])),
        ("__RINGS__", rings_html),
        ("__CORES__", cores_html),
        ("__RESPEC__", esc(meta["respec$"])),
        ("__RESET__", esc(meta["reset$"])),
        ("__PVPRATE__", str(meta["pvp_rate"] // 10)),
        ("__PVPDMG__", str(meta["pvp_dmg"] // 10)),
        ("__RINGCHIPS__", json.dumps([[meta["ring$"][r], r] for r in sorted(by_ring)],
                                     ensure_ascii=False)),
        ("__ROUTECHIPS__", json.dumps([[v, v] for _, v in sorted(meta["route$"].items())],
                                      ensure_ascii=False)),
        ("__BFCHIPS__", json.dumps([[v, v] for v in bfs], ensure_ascii=False)),
        ("__DATA__", json.dumps(rows, ensure_ascii=False, separators=(",", ":"))),
    ]:
        out = out.replace(k, v)

    dest = os.path.join(WEB, "wanfa.html")
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    return dest, rows, meta, out


# ---------------------------------------------------------------- 驗證

def verify(dest, rows, meta, out):
    ok = True

    def chk(cond, msg):
        nonlocal ok
        print(("  ok    " if cond else "  FAIL  ") + msg)
        ok = ok and bool(cond)

    node, _ = parse_script()          # 重新解析一次來源, 獨立於 build 的結果
    print("驗證 %s" % dest)

    keys = set(node["nm"])
    chk(all(set(node[k]) == keys for k in
            ("ring", "route", "pre", "sk", "bf", "icd", "dmg",
             "flag", "rate", "rinc", "slv", "sinc")),
        "13 張表逐格對齊 (%d 個節點)" % len(keys))
    chk(len(rows) == 55, "節點 55 個 (實得 %d)" % len(rows))

    cnt = {}
    for n in rows:
        cnt[n["ring"]] = cnt.get(n["ring"], 0) + 1
    chk(cnt == {0: 3, 1: 13, 2: 12, 3: 10, 4: 9, 5: 8},
        "各環 3/13/12/10/9/8 (實得 %s)" % cnt)

    # 星環/路線名稱抓錯時是「一段程式碼碎片」不是空值, 所以要正面比對內容
    chk(meta["ring$"] == ["基礎星", "第一星環", "第二星環",
                          "第三星環", "第四星環", "核心主星"],
        "星環名稱正確 (%s)" % "/".join(meta["ring$"]))
    chk(len(meta["route$"]) == 9
        and all(re.fullmatch(r"[一-鿿]+", v) for v in meta["route$"].values()),
        "9 條路線名稱都是中文 (%s)" % "/".join(meta["route$"].values()))
    chk(all(n["bf"] for n in rows if n["sk"]), "BF 遮罩全部對到中文標籤")
    chk(all(n["skn"] for n in rows if n["sk"]), "觸發技能全部有中文名")
    over = [(n["id"], n["nm"], n["l5"], n["skmax"])
            for n in rows if n["sk"] and n["l5"] > n["skmax"]]
    chk(not over, "技能等級不超過 MaxLevel" + (" — 超出 %s" % over if over else ""))

    chk(all(n["r5"] <= 1000 for n in rows), "觸發率不超過 100%")
    chk(all(n["pre"] == 0 or n["pre"] in keys for n in rows), "前置節點都存在")
    roots = [n for n in rows if n["pre"] == 0]
    chk(len(roots) == 3 and all(n["ring"] == 0 for n in roots), "只有 3 個基礎星是起點")
    chk(all(n["sk"] == 0 for n in rows if n["ring"] in (0, 5)),
        "基礎星與主星不觸發技能")

    chk(meta["pt_realm"] == 26 and meta["pt_tower_all"] == 26,
        "配點 境界 %d + 鎖妖塔 %d" % (meta["pt_realm"], meta["pt_tower_all"]))
    chk(meta["pt_now"] == 34,
        "目前可得 %d 點 (境界 %d + 塔 %d 層 %d)"
        % (meta["pt_now"], meta["pt_realm"], meta["floors"], meta["pt_tower_now"]))
    chk(meta["respec$"] and meta["reset$"],
        "洗點材料 %s / %s" % (meta["respec$"], meta["reset$"]))
    chk(meta["pvp_rate"] == 700 and meta["pvp_dmg"] == 600,
        "PvP 觸發 %d / 傷害 %d" % (meta["pvp_rate"], meta["pvp_dmg"]))

    cores = [n for n in rows if n["ring"] == 5]
    chk(all(n["cr1"] and n["cbon"] for n in cores), "8 顆主星都有受惠路線與倍率")
    chk(not re.search(r"__[A-Z]+__", out), "樣板佔位全部替換")

    print("  ----  %s   (%.0f KB)" % ("PASS" if ok else "FAIL",
                                      len(out.encode("utf-8")) / 1024))
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if verify(*build()) else 1)

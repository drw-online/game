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


def assigns(t, name):
    """抓單格賦值 $@<name>[索引] = 值;  回傳 {索引: 原始字串}。

    ★ 延伸前置那一段(規格 §6)是稀疏的, 用單格賦值而不是 setarray ——
      只認 setarray 會把它們全部漏掉, 而且不報錯, 只是前置欄顯示舊值。
      例如 $@wf_pre[110] 在 setarray 裡是 11(法之基), 後面被改成 13(靈識)
      並補上 pre2/pre3 變成「靈識/附靈/靈光 三選一」。
    ★ 索引的左中括號負責錨定, 所以 $@wf_pre 不會誤抓到 $@wf_prelv。
    """
    out = {}
    for m in re.finditer(re.escape("$@" + name) + r"\[(\d+)\]\s*=\s*([^;]+);", t):
        out[int(m.group(1))] = m.group(2).strip()
    return out


def scalar(t, name):
    m = re.search(re.escape("$@" + name) + r"\s*=\s*([^;]+);", t)
    if not m:
        raise SystemExit("找不到 $@%s" % name)
    return int(m.group(1).strip())


def parse_script():
    t = re.sub(r"//[^\n]*", "", read(WF))          # 去掉行註解再解析
    def merged(n):
        """setarray 先鋪底, 單格賦值再覆寫 —— 順序不能反。"""
        d = setarrays(t, n)
        d.update(assigns(t, n))
        return d

    ints = lambda n: {k: int(v) for k, v in merged(n).items()}
    strs = lambda n: {k: v.strip('"') for k, v in merged(n).items()}

    node = {
        "nm":    strs("wf_name$"),
        "ring":  ints("wf_ring"),
        "route": ints("wf_route"),
        "pre":   ints("wf_pre"),
        "prelv":  ints("wf_prelv"),
        "pre2":   ints("wf_pre2"),
        "pre2lv": ints("wf_pre2lv"),
        "pre3":   ints("wf_pre3"),
        "pre3lv": ints("wf_pre3lv"),
        "pre4":   ints("wf_pre4"),
        "pre4lv": ints("wf_pre4lv"),
        "preor":  ints("wf_preor"),
        "sk":    ints("wf_skill"),
        "bf":    merged("wf_bf"),            # 常數名, 保持字串
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

        # 前置四槽(規格 §6)。$@wf_preNlv 沒填就是 1 = 「有點就行」,
        # 所以 Lv1 不印出來, 只有 >= 2 才標等級。
        slots = []
        for k, klv in (("pre", "prelv"), ("pre2", "pre2lv"),
                       ("pre3", "pre3lv"), ("pre4", "pre4lv")):
            p = node[k].get(nid, 0)
            if p > 0:
                slots.append((p, node["nm"].get(p, "#%d" % p),
                              max(1, node[klv].get(nid, 0))))
        if not slots:
            pretxt = "起點，沒有前置"
        else:
            parts = ["%s（#%d）%s" % (nm, p, "Lv%d↑" % lv if lv > 1 else "")
                     for p, nm, lv in slots]
            pretxt = ("／".join(parts) + "　任一即可"
                      if node["preor"].get(nid, 0) else "＋".join(parts))

        rows.append({
            "id": nid,
            "nm": node["nm"][nid],
            "ring": ring,
            "rings": meta["ring$"][ring],
            "route": node["route"][nid],
            "routes": meta["route$"][node["route"][nid]],
            "pre": node["pre"].get(nid, 0),
            "preids": [p for p, _, _ in slots],
            "pretxt": pretxt,
            # ---- 以下三項是給「互動星盤」用的結構化資料 ----
            # pretxt 是給人看的字串, 算不了規則; preids 又丟掉了「要幾級」。
            #   pres  = [[前置節點, 需要幾級], ...]
            #   preor = 0 全部都要(預設) / 1 任一即可
            #   rate / slv 是基礎值, 配上既有的 rinc / sinc 才推得出中間級數
            #   (rows 原本只有頭尾兩級的 r1/r5 與 l1/l5)。
            "pres": [[p, lvreq] for p, _, lvreq in slots],
            "preor": node["preor"].get(nid, 0),
            "rate": rate, "slv": slv,
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
/* [2026-09-07] 依指示：這一頁不要有左右滑的內容。
   原本是 .tbl-wrap{overflow-x:auto} + table{min-width:460px} + #nodes{min-width:840px},
   窄螢幕就變成橫向捲動。改成兩段式：
     寬螢幕  照常是表格, 但不再撐 min-width, 長文字改成換行
     窄螢幕  整個表拆成一列一張卡(見下面的 @media), 徹底沒有橫向捲動
   ★ overflow-x 保留 hidden 而不是拿掉 —— 萬一哪天有人加了撐寬的東西,
     寧可被裁掉也不要又冒出捲軸。 */
.tbl-wrap{overflow-x:hidden}
table{border-collapse:collapse; width:100%; font-size:14px; table-layout:auto}
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

/* #nodes 原本是 min-width:840px, 八欄硬撐出橫向捲動。拿掉之後靠
   下面的 td.el 換行與窄螢幕卡片版面自己收斂。 */
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
/* 前置那一欄放的是「靈刃星（#213）Lv3↑／破魂星（#214）Lv3↑　任一即可」
   這種長句, nowrap 等於直接把表格撐爆。改成允許換行, 並在全形頓號與
   斜線處也能斷。 */
td.el{white-space:normal; overflow-wrap:anywhere; line-height:1.6;
  color:var(--ink-soft); font-size:13px}
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

/* ---- 窄螢幕：表格改成一列一張卡 ---------------------------------------
   [2026-09-07] 依指示這一頁不要有左右滑的內容。八欄的節點表在手機上
   無論怎麼壓都塞不下, 所以窄螢幕直接放棄表格排版:
     thead 收起來, 每個 td 變成一行「欄位名 值」
   欄位名取自 td 的 data-label(由產生器與前端一起填), 沒填就只顯示值。
   ★ 斷點 780px 是算出來的不是猜的: .wrap 是 max-width:1080px 加左右各
     20px padding, 所以 780px 視窗的內容寬度是 740px; 而節點表在允許換行
     之後的自然最小寬度約 614px(節點欄的星環標籤+名稱約 163px 最寬,
     兩個機率欄各約 66px)。740 > 614 留了足夠餘裕。
   ★ 這個餘裕很重要 —— 上面的 .tbl-wrap 是 overflow-x:hidden, 塞不下會被
     「裁掉」而不是變成捲軸, 那比捲動更糟。斷點寧可訂寬一點。 */
@media (max-width:780px){
  .tbl-wrap table, .tbl-wrap thead, .tbl-wrap tbody,
  .tbl-wrap tr, .tbl-wrap th, .tbl-wrap td{display:block; width:auto}
  .tbl-wrap thead{position:absolute; width:1px; height:1px;
    overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap}
  .tbl-wrap tbody tr{padding:12px 0; border-bottom:1px solid var(--rule)}
  .tbl-wrap tbody td{border:0; padding:3px 0; text-align:left}
  .tbl-wrap td[data-label]::before{
    content:attr(data-label) "　"; color:var(--ink-faint);
    font-size:11px; letter-spacing:.14em}
  /* 數字欄在卡片裡靠左比較好讀, 覆蓋掉桌機的靠右 */
  .tbl-wrap td.num, .tbl-wrap td.rate{text-align:left; white-space:normal}
  td.oid{width:auto}
  td.nm{white-space:normal}
  /* 展開的明細本來就是整列一格, 不要被上面的 display:block 弄壞 */
  .tbl-wrap tr.detail{padding:0; border:0}
  .tbl-wrap tr.detail > td{padding:0}
  .tbl-wrap tr.detail > td::before{content:none}
}
__SIMCSS__
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

__SIM__

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
          <th>前置</th>
          <th>觸發技能</th><th>觸發條件</th>
          <th class="num">Lv1</th><th class="num">滿級</th>
        </tr></thead>
        <tbody id="rows"></tbody>
      </table>
    </div>
    <div class="empty" id="empty" hidden>沒有符合條件的節點。</div>
    <p class="note">「Lv1／滿級」是<b>觸發機率</b>。點任一列可展開技能等級、冷卻、傷害倍率與點滿花費。</p>
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
  td.colSpan = 8;

  const rows = [["前置節點", n.pretxt]];
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

  // 窄螢幕會把表格拆成一列一張卡, 那時 thead 是收起來的 ——
  // 欄位名改由每個 td 的 data-label 帶著走, 順序要跟 thead 一致。
  const LABEL = ["編號", "節點", "路線", "前置",
                 "觸發技能", "觸發條件", "Lv1 觸發率", "滿級觸發率"];

  const cells = [
    ["num oid", n.id], ["nm", null], ["el", n.routes],
    ["el", n.pretxt], ["sk", null], ["el", n.bf || "—"],
    ["rate", n.sk ? n.r1s : "—"], ["rate", n.sk ? n.r5s : "—"],
  ];
  cells.forEach(([cls, val], i) => {
    const td = document.createElement("td");
    td.className = cls;
    td.setAttribute("data-label", LABEL[i]);
    if (i === 1){
      const tag = document.createElement("span");
      tag.className = "tag " + (n.ring === 0 ? "r0" : n.ring === 5 ? "r5" : "rn");
      tag.textContent = n.rings;
      const b = document.createElement("b");
      b.textContent = n.nm;
      td.append(tag, b);
    } else if (i === 4){
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


# ---------------------------------------------------------------- 互動星盤
#
# 與 daopan.html 的互動盤同一套想法, 但規則不同, 抄過去之前先看這裡:
#
#   成本   ring 0 (基礎星) = WF_COST_BASE, 只有 1 級
#          ring 5 (核心主星) = WF_COST_CORE, 只有 1 級
#          其餘 = 累進 WF_CUM[lv] (不是每級固定!) ——
#          「再升一級要幾點」是 CUM[lv+1] - CUM[lv]
#   前置   最多四槽, 每槽各有「要幾級」; preor 決定是「全部都要」還是「任一即可」
#   佈局   X = 星環(0~5), Y 依路線分組。不分頁 —— 星盤的重點就是看整張圖
#
SIM_CSS = """
  .sim-wrap{border:1px solid var(--rule);border-radius:10px;background:var(--paper);
    box-shadow:var(--shadow);overflow:hidden;margin-top:14px}
  .sim-bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;
    padding:10px 12px;background:var(--sunk);border-bottom:1px solid var(--rule)}
  .sim-bar button{font:inherit;font-size:.86rem;padding:5px 11px;border-radius:999px;
    border:1px solid var(--rule);background:var(--paper);color:var(--ink-soft);cursor:pointer}
  .sim-bar button:hover{border-color:var(--cinnabar);color:var(--cinnabar)}
  .sim-bar .spacer{flex:1 1 auto}
  .sim-pts{font-variant-numeric:tabular-nums;font-size:.9rem;color:var(--ink-soft)}
  .sim-pts b{color:var(--cinnabar);font-size:1.05rem}
  .sim-body{display:grid;grid-template-columns:minmax(0,1fr) 250px}
  @media (max-width:820px){.sim-body{grid-template-columns:minmax(0,1fr)}}
  .sim-canvas{overflow:auto;background:var(--ground);max-height:620px}
  .sim-canvas svg{display:block}
  .sim-side{border-left:1px solid var(--rule);padding:12px;font-size:.86rem;
    max-height:620px;overflow:auto}
  @media (max-width:820px){.sim-side{border-left:0;border-top:1px solid var(--rule)}}
  .sim-side h4{margin:0 0 6px;font-size:.8rem;letter-spacing:.06em;color:var(--ink-faint)}
  .sim-side dl{display:grid;grid-template-columns:1fr auto;gap:2px 10px;margin:0 0 14px}
  .sim-side dt{color:var(--ink-soft);min-width:0;overflow:hidden;text-overflow:ellipsis;
    white-space:nowrap}
  .sim-side dd{margin:0;font-variant-numeric:tabular-nums;color:var(--cinnabar);font-weight:500}
  .sim-empty{color:var(--ink-faint)}
  .sim-tip{padding:8px 12px;border-top:1px solid var(--rule);background:var(--sunk);
    font-size:.8rem;color:var(--ink-faint)}
  .sim-axis{fill:var(--ink-faint);font-size:11px}
  .sim-rt{fill:var(--ink-faint);font-size:10px}
  .sim-link{stroke:var(--rule);stroke-width:1.6;fill:none}
  .sim-link.on{stroke:var(--cinnabar);stroke-width:2.4}
  .sim-link.alt{stroke-dasharray:4 3}
  .sim-node{cursor:pointer}
  .sim-node circle{fill:var(--paper);stroke:var(--ink-faint);stroke-width:2;
    transition:fill .12s,stroke .12s}
  .sim-node.on circle{fill:var(--cinnabar);stroke:var(--cinnabar)}
  .sim-node.max circle{stroke:#D8A21B;stroke-width:3}
  .sim-node.locked circle{stroke-dasharray:3 3;opacity:.5}
  .sim-node text.lbl{font-size:10px;fill:var(--ink-soft)}
  .sim-node.on text.lbl{fill:var(--ink)}
  .sim-node text.lv{font-size:10px;font-weight:700;fill:#D8A21B}
  .sim-node:focus{outline:none}
  .sim-node:focus circle{stroke:var(--focus);stroke-width:3}
"""

SIM_HTML = """
  <section id="sim">
    <h2>互動星盤</h2>
    <p class="note">直接在盤上排點看看：<b>左鍵加一級、右鍵退一級</b>。規則跟遊戲裡一致 —— 前置要先點到指定等級、總共只有 <b>__PTMAX__ 點</b>、升級費用是<b>累進</b>的（__CUM__）。橫軸是星環，同一欄由上而下依路線排。</p>
    <div class="sim-wrap">
      <div class="sim-bar" id="simTabs"></div>
      <div class="sim-body">
        <div class="sim-canvas" id="simCanvas"></div>
        <div class="sim-side">
          <h4>各路線投入</h4>
          <dl id="simPaths"></dl>
          <h4>已點的觸發</h4>
          <dl id="simEff"></dl>
        </div>
      </div>
      <div class="sim-tip" id="simTip">點一個節點試試。配點會寫進網址，複製整條網址就能分享。</div>
    </div>
  </section>
"""

SIM_JS = r"""
<script>
(function(){
  var R = __SIMDATA__, M = __SIMMETA__;
  var N = {}, i;
  for(i=0;i<R.length;i++){ N[R[i].id] = R[i]; }
  var COLW = 150, ROWH = 46, PADX = 62, PADY = 40;
  var lv = {};

  function maxlv(id){ return N[id].lvmax; }
  // ★ 累進: 從 cl 升到 cl+1 要幾點。ring 0/5 只有 1 級, 直接用固定價。
  function stepCost(id, cl){
    var r = N[id].ring;
    if(r === 0) return M.costBase;
    if(r === 5) return M.costCore;
    return M.cum[cl+1] - M.cum[cl];
  }
  function nodeSpent(id){
    var cl = lv[id]||0, r = N[id].ring;
    if(!cl) return 0;
    if(r === 0) return M.costBase;
    if(r === 5) return M.costCore;
    return M.cum[cl];
  }
  function used(){ var s=0; for(var k in lv){ s += nodeSpent(k); } return s; }
  function routeUsed(rt){ var s=0; for(var k in lv){ if(N[k].route === rt) s += nodeSpent(k); } return s; }

  function preOK(id){
    var ps = N[id].pres, j;
    if(!ps.length) return true;
    if(N[id].preor){
      for(j=0;j<ps.length;j++){ if((lv[ps[j][0]]||0) >= ps[j][1]) return true; }
      return false;
    }
    for(j=0;j<ps.length;j++){ if((lv[ps[j][0]]||0) < ps[j][1]) return false; }
    return true;
  }
  function preMissing(id){
    var ps = N[id].pres, j;
    for(j=0;j<ps.length;j++){
      if((lv[ps[j][0]]||0) < ps[j][1]){
        var nm = N[ps[j][0]] ? N[ps[j][0]].nm : ('#'+ps[j][0]);
        return nm + (ps[j][1] > 1 ? (' Lv.'+ps[j][1]) : '');
      }
    }
    return '';
  }
  // 退到某級之後, 還有沒有別人靠它撐著
  function breaks(id, after){
    for(var k in lv){
      if(k == id || (lv[k]||0) <= 0) continue;
      var ps = N[k].pres, j, okCnt = 0, need = 0;
      for(j=0;j<ps.length;j++){
        need++;
        var have = (ps[j][0] == id) ? after : (lv[ps[j][0]]||0);
        if(have >= ps[j][1]) okCnt++;
      }
      if(N[k].preor ? okCnt === 0 : okCnt < need) return k;
    }
    return 0;
  }

  function layout(){
    var byRing = {}, pos = {}, ids = [];
    for(i=0;i<R.length;i++) ids.push(R[i].id);
    ids.sort(function(a,b){
      if(N[a].ring !== N[b].ring) return N[a].ring - N[b].ring;
      if(N[a].route !== N[b].route) return N[a].route - N[b].route;
      return a - b;
    });
    for(i=0;i<ids.length;i++){
      var r = N[ids[i]].ring;
      byRing[r] = byRing[r] || 0;
      pos[ids[i]] = { x: PADX + r*COLW, y: PADY + 20 + byRing[r]*ROWH };
      byRing[r]++;
    }
    var maxr = 0;
    for(var rr in byRing){ if(byRing[rr] > maxr) maxr = byRing[rr]; }
    return { ids: ids, pos: pos, w: PADX*2 + 5*COLW + 100, h: PADY*2 + 20 + maxr*ROWH };
  }

  function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function pct(milli){ return (milli/10).toFixed(milli%10 ? 1 : 0) + '%'; }

  function nodeTitle(id){
    var n = N[id], cl = lv[id]||0;
    var t = n.nm + ' — ' + n.rings + '・' + n.routes;
    t += '\n上限 ' + n.lvmax + ' 級，點滿共 ' + n.cost + ' 點';
    if(cl < n.lvmax) t += '\n升到 ' + (cl+1) + ' 級要 ' + stepCost(id, cl) + ' 點';
    if(n.lvmax > 1){
      var pr = [];
      if(n.rinc) pr.push('觸發率 +' + pct(n.rinc));
      if(n.sinc) pr.push('技能等級 +' + n.sinc);
      if(pr.length) t += '\n投資 1 級：' + pr.join('、');
    }
    if(cl > 0){
      var now = [];
      now.push('觸發率 ' + pct(Math.min(n.rate + n.rinc*(cl-1), 1000)));
      if(n.skn) now.push('技能等級 ' + (n.slv + n.sinc*(cl-1)));
      t += '\n目前 ' + cl + ' 級：' + now.join('、');
    }
    if(n.skn) t += '\n技能：' + n.skn + (n.bf ? ('（' + n.bf + '）') : '');
    return t;
  }

  function draw(){
    var L = layout(), out = ['<svg width="'+L.w+'" height="'+L.h+'" viewBox="0 0 '+L.w+' '+L.h+'">'];
    for(i=0;i<=5;i++){
      out.push('<text class="sim-axis" x="'+(PADX + i*COLW)+'" y="20" text-anchor="middle">'+esc(M.rings[i])+'</text>');
    }
    for(i=0;i<L.ids.length;i++){
      var id = L.ids[i], a = L.pos[id], ps = N[id].pres, j;
      for(j=0;j<ps.length;j++){
        var s = L.pos[ps[j][0]];
        if(!s) continue;
        var on = ((lv[ps[j][0]]||0) >= ps[j][1] && (lv[id]||0) > 0) ? ' on' : '';
        var alt = N[id].preor ? ' alt' : '';
        out.push('<path class="sim-link'+alt+on+'" d="M'+s.x+' '+s.y+' L'+a.x+' '+a.y+'"/>');
      }
    }
    for(i=0;i<L.ids.length;i++){
      var id2 = L.ids[i], n = N[id2], p = L.pos[id2], cl = lv[id2]||0;
      var cls = ['sim-node'];
      if(cl > 0) cls.push('on');
      if(cl >= n.lvmax) cls.push('max');
      if(cl === 0 && !preOK(id2)) cls.push('locked');
      var r = n.ring === 5 ? 13 : 10;
      out.push('<g class="'+cls.join(' ')+'" data-id="'+id2+'" tabindex="0">');
      out.push('<title>'+esc(nodeTitle(id2))+'</title>');
      out.push('<circle cx="'+p.x+'" cy="'+p.y+'" r="'+r+'"/>');
      out.push('<text class="lv" x="'+(p.x+r-1)+'" y="'+(p.y+r+1)+'">'+(cl||'')+'</text>');
      out.push('<text class="lbl" x="'+(p.x+r+5)+'" y="'+(p.y+4)+'">'+esc(n.nm)+'</text>');
      out.push('</g>');
    }
    out.push('</svg>');
    document.getElementById('simCanvas').innerHTML = out.join('');
  }

  function side(){
    var h = [], k, seen = {};
    for(k in lv){ seen[N[k].route] = 1; }
    var rts = Object.keys(seen).sort(function(a,b){ return a-b; });
    if(!rts.length) h.push('<dt class="sim-empty">還沒點任何節點</dt><dd></dd>');
    for(i=0;i<rts.length;i++){
      h.push('<dt>'+esc(M.routes[rts[i]])+'</dt><dd>'+routeUsed(+rts[i])+'</dd>');
    }
    document.getElementById('simPaths').innerHTML = h.join('');

    var h2 = [], keys = Object.keys(lv).sort(function(a,b){ return a-b; });
    for(i=0;i<keys.length;i++){
      var n = N[keys[i]], cl = lv[keys[i]];
      if(!n.skn) continue;
      h2.push('<dt>'+esc(n.skn)+'</dt><dd>'+pct(Math.min(n.rate + n.rinc*(cl-1), 1000))+'</dd>');
    }
    document.getElementById('simEff').innerHTML =
      h2.length ? h2.join('') : '<dt class="sim-empty">還沒有會觸發的技能</dt><dd></dd>';
    document.getElementById('simUsed').innerHTML = '已用 <b>'+used()+'</b> / '+M.ptMax+' 點';
  }

  function tip(m){ document.getElementById('simTip').textContent = m; }

  function add(id){
    var n = N[id], cl = lv[id]||0;
    if(cl >= n.lvmax){ tip(n.nm + ' 已經滿級了。'); return; }
    if(cl === 0 && !preOK(id)){ tip('要先點亮前置：' + preMissing(id) + '。'); return; }
    var c = stepCost(id, cl);
    if(used() + c > M.ptMax){ tip('點數不夠了，升這一級要 ' + c + ' 點，你只有 ' + M.ptMax + ' 點。'); return; }
    lv[id] = cl + 1;
    tip(n.nm + ' → ' + lv[id] + ' 級（花了 ' + c + ' 點）。');
    sync();
  }
  function sub(id){
    var n = N[id], cl = lv[id]||0;
    if(cl <= 0) return;
    var b = breaks(id, cl - 1);
    if(b){ tip('不能退 —— 【' + N[b].nm + '】要靠它撐著。'); return; }
    lv[id] = cl - 1;
    if(!lv[id]) delete lv[id];
    tip(n.nm + ' → ' + (lv[id]||0) + ' 級。');
    sync();
  }

  function encode(){
    var a = [], ks = Object.keys(lv).sort(function(x,y){ return x-y; });
    for(i=0;i<ks.length;i++) a.push(ks[i] + '.' + lv[ks[i]]);
    return a.join('-');
  }
  function decode(s){
    lv = {};
    if(!s) return;
    var parts = s.split('-');
    for(i=0;i<parts.length;i++){
      var kv = parts[i].split('.'), id = +kv[0], v = +kv[1];
      if(N[id] && v > 0 && v <= N[id].lvmax) lv[id] = v;
    }
  }
  function sync(){
    draw(); side();
    var h = encode();
    history.replaceState(null, '', h ? ('#b=' + h) : location.pathname);
  }

  document.getElementById('simTabs').innerHTML =
    '<span class="sim-pts" id="simUsed"></span><span class="spacer"></span>' +
    '<button type="button" id="simReset">清空</button>';
  document.getElementById('simTabs').addEventListener('click', function(ev){
    var b = ev.target.closest('button');
    if(b && b.id === 'simReset'){ lv = {}; tip('已清空。'); sync(); }
  });
  var cv = document.getElementById('simCanvas');
  cv.addEventListener('click', function(ev){
    var g = ev.target.closest('.sim-node');
    if(g) add(+g.dataset.id);
  });
  cv.addEventListener('contextmenu', function(ev){
    var g = ev.target.closest('.sim-node');
    if(!g) return;
    ev.preventDefault();
    sub(+g.dataset.id);
  });
  cv.addEventListener('keydown', function(ev){
    var g = ev.target.closest('.sim-node');
    if(!g) return;
    if(ev.key === 'Enter' || ev.key === ' '){ ev.preventDefault(); add(+g.dataset.id); }
    if(ev.key === 'Backspace' || ev.key === 'Delete'){ ev.preventDefault(); sub(+g.dataset.id); }
  });

  if(location.hash.indexOf('#b=') === 0) decode(location.hash.slice(3));
  sync();
})();
</script>
"""


def build():
    rows, meta = collect()

    by_ring = {}
    for n in rows:
        by_ring.setdefault(n["ring"], []).append(n)

    # data-label 是給窄螢幕的卡片版面用的 —— 那時 thead 收起來, 欄位名
    # 由 td 自己帶。順序要跟上面 thead 的 th 一致。
    rings_html = "".join(
        '<tr><td data-label="星環">%s</td><td class="num" data-label="節點">%d</td>'
        '<td class="num" data-label="最高等級">%d</td>'
        '<td class="num" data-label="點滿要">%d</td>'
        '<td class="el" data-label="作用">%s</td></tr>'
        % (esc(meta["ring$"][r]), len(ns), ns[0]["lvmax"],
           sum(n["cost"] for n in ns), esc(RING_DESC[r]))
        for r, ns in sorted(by_ring.items()))

    cores_html = "".join(
        '<tr><td data-label="主星"><b>%s</b></td>'
        '<td class="el" data-label="受惠路線">%s</td>'
        '<td class="num rate" data-label="觸發率">×%d%%</td>'
        '<td class="el" data-label="前置節點">%s</td></tr>'
        % (esc(n["nm"]), esc(n["cr1"] + ("、" + n["cr2"] if n["cr2"] else "")),
           n["cbon"] // 10, esc(n["pretxt"]))
        for n in rows if n["ring"] == 5)

    bfs = []
    for n in rows:
        if n["bf"] and n["bf"] not in bfs:
            bfs.append(n["bf"])

    # 互動盤只要規則需要的欄位, 不要表格那些顯示字串(r1s / icds / pretxt …),
    # 否則等於在頁面裡塞第二份完整 rows。
    sim_rows = [{k: n[k] for k in ("id", "nm", "ring", "rings", "route", "routes",
                                   "pres", "preor", "lvmax", "cost",
                                   "rate", "rinc", "slv", "sinc", "skn", "bf")}
                for n in rows]
    sim_meta = {
        "ptMax": meta["pt_max"], "cum": meta["cum"],
        "costBase": meta["cost_base"], "costCore": meta["cost_core"],
        "rings": meta["ring$"],
        "routes": {str(k): v for k, v in meta["route$"].items()},
    }

    out = TPL
    for k, v in [
        # ★ 這三項一定要排在最前面 —— SIM_HTML 裡用了 __PTMAX__ / __CUM__,
        #   先把區塊插進頁面, 後面那些替換才吃得到它。順序反了不會報錯,
        #   只會在頁面上看到沒被取代的 __PTMAX__ 字樣。
        ("__SIMCSS__", SIM_CSS),
        ("__SIM__", SIM_HTML + SIM_JS),
        ("__SIMMETA__", json.dumps(sim_meta, ensure_ascii=False, separators=(",", ":"))),
        ("__SIMDATA__", json.dumps(sim_rows, ensure_ascii=False, separators=(",", ":"))),
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
    # ★ 下面幾個是「快照預期值」不是推導值 —— 星盤擴充時本來就會 FAIL,
    #   那正是它們的用途(擋住漏抓與多抓)。擴充後手動更新, 但更新前一定要先
    #   確認數字是真的長出來的, 不是解析器誤抓。
    #   [2026-09-06] 55 -> 72 個節點。查證過: 來源用額外的 setarray 補在稀疏
    #   索引(13/113/212/310…), 而 $@wf_name$ / $@wf_ring / $@wf_skill 的單格
    #   賦值都是 0 筆 —— 節點身分純由 setarray 決定, 沒有踩到本檔開頭寫的
    #   「把使用當成定義抓進來」那個坑。新增的是念靈路線那一批(返魂星/
    #   念爆星/靈刃星/破魂星/靈盾星/靈魂擴張/靈暴星/玄靈護體…)。
    chk(len(rows) == 72, "節點 72 個 (實得 %d)" % len(rows))

    cnt = {}
    for n in rows:
        cnt[n["ring"]] = cnt.get(n["ring"], 0) + 1
    chk(cnt == {0: 6, 1: 14, 2: 16, 3: 14, 4: 13, 5: 9},
        "各環 6/14/16/14/13/9 (實得 %s)" % cnt)

    # 星環/路線名稱抓錯時是「一段程式碼碎片」不是空值, 所以要正面比對內容
    chk(meta["ring$"] == ["基礎星", "第一星環", "第二星環",
                          "第三星環", "第四星環", "核心主星"],
        "星環名稱正確 (%s)" % "/".join(meta["ring$"]))
    # [2026-09-06] 9 -> 10 條: 新增「念靈」。名稱本身一直都是正常中文,
    #   先前 FAIL 純粹是條數對不上, 不是抓到程式碼碎片。
    chk(len(meta["route$"]) == 10
        and all(re.fullmatch(r"[一-鿿]+", v) for v in meta["route$"].values()),
        "10 條路線名稱都是中文 (%s)" % "/".join(meta["route$"].values()))
    chk(all(n["bf"] for n in rows if n["sk"]), "BF 遮罩全部對到中文標籤")
    chk(all(n["skn"] for n in rows if n["sk"]), "觸發技能全部有中文名")
    over = [(n["id"], n["nm"], n["l5"], n["skmax"])
            for n in rows if n["sk"] and n["l5"] > n["skmax"]]
    chk(not over, "技能等級不超過 MaxLevel" + (" — 超出 %s" % over if over else ""))

    chk(all(n["r5"] <= 1000 for n in rows), "觸發率不超過 100%")
    chk(all(all(p in keys for p in n["preids"]) for n in rows), "前置節點都存在")
    roots = [n for n in rows if n["pre"] == 0]
    chk(len(roots) == 3 and all(n["ring"] == 0 for n in roots), "只有 3 個基礎星是起點")
    chk(all(n["sk"] == 0 for n in rows if n["ring"] in (0, 5)),
        "基礎星與主星不觸發技能")

    chk(meta["pt_realm"] == 26 and meta["pt_tower_all"] == 26,
        "配點 境界 %d + 鎖妖塔 %d" % (meta["pt_realm"], meta["pt_tower_all"]))
    # [2026-09-06] 34 -> 50。鎖妖塔開放層數增加使 pt_tower_now 由 8 變 26,
    #   26 + 26 = 52 已經超過 $@WF_PT_MAX = 50, 所以 pt_now 被上限夾成 50 ——
    #   星盤到這裡開始「點數封頂」, 多出來的 2 點拿不到。這不是解析錯誤。
    chk(meta["pt_now"] == 50,
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

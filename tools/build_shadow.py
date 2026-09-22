# -*- coding: utf-8 -*-
"""
三流派影子裝備產生器 —— 產生 shadow.html, 跑完自己驗證一次。

用法:

    python tools/build_shadow.py

會覆寫 shadow.html。輸出是決定性的 —— 來源沒變的話重跑一次 git status
應該是乾淨的, 這也是最好的回歸測試。

--------------------------------------------------------------------------
來源 (全部在 2.開機擋)
--------------------------------------------------------------------------
  script/23.影子裝備/00.設定.txt        三系列的 ID 區段
  script/23.影子裝備/01.套裝.txt        單件能力(switch)、2/4/6 件門檻、PVP 停用
  db/import/blackgod/item_shadow_three.yml  18 件的名稱、部位、精煉與交易限制
  conf/battle/blackgod.conf             bg_star_* (追擊機率、內置冷卻、技能等級)
  db/re/skill_db.yml                    追擊用技能的中文名

★★ 道具 yml 裡「沒有」任何 Script ★★
  單件能力與九個套裝門檻全部在 01.套裝.txt 的 F_Shadow_Calc。
  想從 item_db 讀能力會讀到空的, 而且不會報錯。

★ 能力文字是從 bonus 指令翻出來的, 不是手打的。
  BONUS 表裡沒有的 bonus 會讓產生器「當場失敗」而不是印出空白 ——
  日後加了新詞條就會被擋下來, 逼人補翻譯。

★ bStarThunder 在 pc_bonus 是取最高值不是相加(規格 6.1), 所以穿滿六件
  是「第 2 階」不是「第 1+2 = 3 階」。頁面照這個語意寫。

★ 取得管道是「找出來」的不是寫死的 —— 兩條路都要掃, 找不到才標「尚未開放取得」:
    1. 全服腳本的 getitem / makeitem / rentitem 帶這 18 個 ID
    2. db/map_drops_increased.yml 的地圖掉落表(base 與 import 兩份)
  [2026-09-22] 影子裝走的是第 2 條(pvp_n_1-2 全魔物 0.01%), 之前只掃第 1 條,
  頁面因此一直誤標「尚未開放取得」—— 而且 rc=0 不報錯。
"""
import io, os, re, sys, html

try:
    import yaml
except ImportError:
    sys.exit("需要 PyYAML: pip install pyyaml")

HERE = os.path.dirname(os.path.abspath(__file__))
WEB  = os.path.dirname(HERE)
ROOT = r"H:\91.神域仙境"
SRV  = os.path.join(ROOT, "2.開機擋")

F_CONF = os.path.join(SRV, r"script\23.影子裝備\00.設定.txt")
F_SET  = os.path.join(SRV, r"script\23.影子裝備\01.套裝.txt")
F_ITEM = os.path.join(SRV, r"db\import\blackgod\item_shadow_three.yml")
F_BATT = os.path.join(SRV, r"conf\battle\blackgod.conf")

STYLE_FROM = os.path.join(WEB, "potential.html")
DEST       = os.path.join(WEB, "shadow.html")


def die(msg):
    sys.exit("build_shadow: " + msg)


def chk(cond, msg):
    if not cond:
        die(msg)


def read(path, enc="utf-8-sig"):
    with io.open(path, "r", encoding=enc) as f:
        return f.read()


def yload(path):
    with io.open(path, "r", encoding="utf-8-sig") as f:
        return (yaml.safe_load(f) or {}).get("Body") or []


# ==========================================================================
#  bonus -> 中文
# ==========================================================================
#  ★ 這張表是「白名單」。查不到的 bonus 會中止產生, 不會靜默略過。
RACE_CN  = {"RC_All": "所有種族"}
ELE_CN   = {"Ele_All": "所有屬性"}
CLASS_CN = {"Class_All": "一般、BOSS 與傭兵", "Class_Boss": "BOSS",
            "Class_Normal": "一般"}

BONUS1 = {
    "bAtkRate":        lambda v: "物理攻擊 +%d%%" % v,
    "bPatk":           lambda v: "物理攻擊力 P.ATK +%d" % v,
    "bMatkRate":       lambda v: "魔法攻擊 +%d%%" % v,
    "bSmatk":          lambda v: "魔法攻擊力 S.MATK +%d" % v,
    "bMaxHPrate":      lambda v: "最大生命 +%d%%" % v,
    "bMaxSPrate":      lambda v: "最大魔力 +%d%%" % v,
    "bRes":            lambda v: "物理抗性 RES +%d" % v,
    "bMres":           lambda v: "魔法抗性 MRES +%d" % v,
    "bPhysicalPen":    lambda v: "物理抗性穿透 +%d" % v,
    "bMagicalPen":     lambda v: "魔法抗性穿透 +%d" % v,
    "bAspd":           lambda v: "攻擊速度 +%d" % v,
    "bHit":            lambda v: "命中 +%d" % v,
    "bFlee":           lambda v: "迴避 +%d" % v,
    "bShortAtkRate":   lambda v: "近距離物理傷害 +%d%%" % v,
    "bLongAtkRate":    lambda v: "遠距離物理傷害 +%d%%" % v,
    "bDelayrate":      lambda v: "技能後延遲 %+d%%" % v,
    "bUseSPrate":      lambda v: "技能魔力消耗 %+d%%" % v,
    "bFixedCast":      lambda v: "固定詠唱 %+g 秒" % (v / 1000.0),
    "bNormalAtkRate":  lambda v: "普通攻擊傷害 +%d%%" % v,
    "bStarThunder":    lambda v: "星雷追擊 第 %d 階" % v,
    "bStarThunderDmg": lambda v: "星雷追擊傷害 +%d%%" % v,
}

BONUS2 = {
    "bIgnoreResRaceRate":  lambda a, v: "無視%s的物理抗性 %d%%" % (RACE_CN.get(a, a), v),
    "bIgnoreMResRaceRate": lambda a, v: "無視%s的魔法抗性 %d%%" % (RACE_CN.get(a, a), v),
    "bMagicAddEle":        lambda a, v: "對%s的魔法傷害 +%d%%" % (ELE_CN.get(a, a), v),
    "bAddClass":           lambda a, v: "對%s的物理傷害 +%d%%" % (CLASS_CN.get(a, a), v),
}


def eff_text(stmt):
    """把一句 bonus 指令翻成中文。翻不出來就中止。"""
    stmt = stmt.strip().rstrip(";").strip()

    m = re.match(r"^bonus2\s+(\w+)\s*,\s*(\w+)\s*,\s*(-?\d+)$", stmt)
    if m:
        fn = BONUS2.get(m.group(1))
        chk(fn, "BONUS2 表裡沒有 %s —— 補上翻譯再跑一次" % m.group(1))
        return fn(m.group(2), int(m.group(3)))

    m = re.match(r"^bonus\s+(\w+)\s*,\s*(-?\d+)$", stmt)
    if m:
        fn = BONUS1.get(m.group(1))
        chk(fn, "BONUS1 表裡沒有 %s —— 補上翻譯再跑一次" % m.group(1))
        return fn(int(m.group(2)))

    die("看不懂的 bonus 句子: %r" % stmt)


def eff_list(block):
    """一段程式碼裡所有的 bonus 句子 -> 中文清單(保持原順序)。"""
    block = re.sub(r"//.*$", "", block, flags=re.M)
    out = []
    for raw in block.split(";"):
        raw = raw.strip()
        if not raw:
            continue
        # 去掉條件前綴, 例如 if (!$@SHD_star_off) bonus bStarThunder,1;
        raw = re.sub(r"^if\s*\([^)]*\)\s*", "", raw).strip()
        if not raw.startswith("bonus"):
            continue
        out.append(eff_text(raw))
    return out


# ==========================================================================
#  來源解析
# ==========================================================================
def parse_conf():
    s = read(F_CONF)
    seg = {}
    for key in ("PHY", "MAG", "AUT"):
        lo = re.search(r"\$@SHD_%s_LO\s*=\s*(\d+)" % key, s)
        hi = re.search(r"\$@SHD_%s_HI\s*=\s*(\d+)" % key, s)
        chk(lo and hi, "00.設定.txt 找不到 $@SHD_%s_LO/HI" % key)
        seg[key] = (int(lo.group(1)), int(hi.group(1)))
    return seg


def brace_block(s, start):
    """從 s[start] 的 '{' 開始, 回傳到配對 '}' 為止的內容。"""
    chk(s[start] == "{", "brace_block 的起點不是 {")
    depth, i = 0, start
    while i < len(s):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return s[start + 1:i]
        i += 1
    die("找不到配對的 }")


def parse_setbonus():
    """單件能力(switch case) + 2/4/6 件門檻 + PVP 停用的旗標清單。"""
    s = read(F_SET)

    single = {}
    for m in re.finditer(r"case\s+(\d+)\s*:(.*?)break\s*;", s, re.S):
        single[int(m.group(1))] = eff_list(m.group(2))
    chk(single, "01.套裝.txt 一個 case 都沒解析到")

    # 門檻: if (.@phy >= 2) { ... }
    thr = {}
    for m in re.finditer(r"if\s*\(\s*\.@(phy|mag|aut)\s*>=\s*(\d+)\s*\)\s*", s):
        pos = s.find("{", m.end())
        chk(pos >= 0, "門檻 if 後面找不到 {")
        thr.setdefault(m.group(1), {})[int(m.group(2))] = eff_list(brace_block(s, pos))
    chk(len(thr) == 3, "門檻只解析到 %d 個系列, 應該是 3 個" % len(thr))

    # PVP 停用: 那一長串 getmapflag
    m = re.search(r"getmapflag\([^)]*?mf_\w+\)"
                  r"(?:\s*\|\|\s*getmapflag\([^)]*?mf_\w+\))+", s)
    chk(m, "01.套裝.txt 找不到 PVP 判斷")
    pvp_flags = re.findall(r"mf_(\w+)", m.group(0))

    return single, thr, pvp_flags


def parse_items():
    out = {}
    for it in yload(F_ITEM):
        locs = [k for k, v in (it.get("Locations") or {}).items() if v]
        chk(len(locs) == 1, "%s 的部位不是剛好一個: %s" % (it["Name"], locs))
        tr = it.get("Trade") or {}
        out[it["Id"]] = {
            "name": it["Name"],
            "aegis": it["AegisName"],
            "loc": locs[0],
            "refine": bool(it.get("Refineable")),
            "grade": bool(it.get("Gradable")),
            "notrade": bool(tr.get("NoTrade")),
            "nodrop": bool(tr.get("NoDrop")),
        }
    chk(out, "item_shadow_three.yml 沒有內容")
    return out


def parse_battleconf(keys):
    s = read(F_BATT, "utf-8")
    got = {}
    for k in keys:
        m = re.search(r"^%s\s*:\s*(-?\d+)" % re.escape(k), s, re.M)
        chk(m, "blackgod.conf 找不到 %s" % k)
        got[k] = int(m.group(1))
    return got


def skill_name(aegis):
    for rel in (r"db\re\skill_db.yml", r"db\import\skill_db.yml"):
        p = os.path.join(SRV, rel)
        if not os.path.exists(p):
            continue
        for sk in yload(p):
            if sk.get("Name") == aegis and sk.get("Description"):
                return sk["Description"]
    die("skill_db 找不到 %s" % aegis)


def find_map_drops(aegis):
    """地圖掉落表有沒有這些道具 —— 影子裝走的就是這條路, 不是 NPC 發的。

    ★ [2026-09-22] 只掃腳本 getitem 會整條漏掉, 頁面於是誤標「尚未開放取得」。
    ★ 分母看檔頭 Version: 2 = 十萬分比, 3 = 百萬分比。看錯就差 10 倍。
    ★ base 與 import 兩份都要看 —— import 是後蓋上去的那一份。
    """
    out = []
    for rel in (r"db\map_drops_increased.yml", r"db\import\map_drops_increased.yml"):
        p = os.path.join(SRV, rel)
        if not os.path.isfile(p):
            continue
        with io.open(p, "r", encoding="utf-8-sig") as f:
            doc = yaml.safe_load(f) or {}
        ver = ((doc.get("Header") or {}).get("Version")) or 0
        chk(ver in (2, 3), "%s 的 Header Version 是 %r, 分母不明" % (rel, ver))
        denom = 100000.0 if ver == 2 else 1000000.0
        for ent in (doc.get("Body") or []):
            rates = {d["Rate"] for d in (ent.get("GlobalDrops") or [])
                     if d.get("Item") in aegis}
            if not rates:
                continue
            chk(len(rates) == 1,
                "%s 在 %s 的掉落率不一致: %s" % (ent.get("Map"), rel, sorted(rates)))
            out.append("%s 全魔物掉落 %g%%"
                       % (ent.get("Map"), rates.pop() / denom * 100))
    return out


def find_source(ids, aegis):
    """全服腳本有沒有發放這些道具 —— 有才寫得出「怎麼拿」。"""
    hits = set()
    pat = re.compile(r"\b(?:getitem|getitem2|makeitem|rentitem)\s*[\( ]\s*(?:%s)\b"
                     % "|".join(str(i) for i in ids))
    for base in ("script", "npc"):
        root = os.path.join(SRV, base)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if not fn.endswith(".txt"):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    body = read(p, "utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for line in body.splitlines():
                    t = line.strip()
                    if t.startswith("//"):
                        continue
                    if pat.search(t):
                        hits.add(os.path.relpath(p, SRV))
    return find_map_drops(aegis) + sorted(hits)


# ==========================================================================
#  組頁面
# ==========================================================================
LOC_CN = {
    "Shadow_Weapon": "武器", "Shadow_Armor": "鎧甲", "Shadow_Shield": "盾牌",
    "Shadow_Shoes": "戰靴", "Shadow_Right_Accessory": "耳環",
    "Shadow_Left_Accessory": "墜子",
}
LOC_ORDER = ["Shadow_Weapon", "Shadow_Armor", "Shadow_Shield",
             "Shadow_Shoes", "Shadow_Right_Accessory", "Shadow_Left_Accessory"]

LINE = [
    ("PHY", "phy", "破軍誅仙", "物理", "把物理攻擊、爆發與抗性穿透堆到底。"),
    ("MAG", "mag", "太虛萬法", "法術", "魔法攻擊、屬性增傷與詠唱縮短。"),
    ("AUT", "aut", "星雷幻舞", "自詠普攻", "靠普通攻擊本體吃傷害，並自動引下雷擊。"),
]

PVP_CN = {
    "pvp": "PVP 地圖", "gvg": "攻城戰", "gvg_castle": "攻城城堡",
    "gvg_te": "TE 攻城戰", "gvg_te_castle": "TE 攻城城堡",
    "battleground": "戰場",
}


def main():
    seg   = parse_conf()
    single, thr, pvp_flags = parse_setbonus()
    items = parse_items()
    star  = parse_battleconf(["bg_star_chance_t1", "bg_star_chance_t2",
                              "bg_star_icd_t1", "bg_star_icd_t2",
                              "bg_star_skill_lv"])
    bolt  = skill_name("MG_LIGHTNINGBOLT")

    # ---- 驗證: 每件都要有單件能力, 而且落在自己的 ID 區段 ----
    for iid in items:
        chk(iid in single, "%s (%d) 在 01.套裝.txt 裡沒有單件能力"
            % (items[iid]["name"], iid))
    for iid in single:
        chk(iid in items, "01.套裝.txt 有 case %d 但 item_db 裡沒這件" % iid)

    by_line = {}
    for key, _var, _cn, _tag, _desc in LINE:
        lo, hi = seg[key]
        got = sorted(i for i in items if lo <= i <= hi)
        chk(got, "%s 系列一件都沒有" % key)
        locs = [items[i]["loc"] for i in got]
        chk(len(set(locs)) == len(got), "%s 系列有重複部位" % key)
        for l in locs:
            chk(l in LOC_CN, "沒見過的影裝部位 %s" % l)
        by_line[key] = got

    sizes = {len(v) for v in by_line.values()}
    chk(len(sizes) == 1, "三個系列的件數不一致: %s" % sizes)
    per_line = sizes.pop()

    covered = {i for g in by_line.values() for i in g}
    chk(covered == set(items), "有道具不在任何一個 ID 區段內: %s"
        % sorted(set(items) - covered))

    # 精煉/附魔/交易限制: 全部必須一致, 不然頁面不能寫成一句話
    for f in ("refine", "grade", "notrade", "nodrop"):
        vals = {items[i][f] for i in items}
        chk(len(vals) == 1, "欄位 %s 在各件之間不一致" % f)
    it0 = items[min(items)]

    # 門檻: 三個系列的門檻級距必須一樣
    steps = {tuple(sorted(v)) for v in thr.values()}
    chk(len(steps) == 1, "三個系列的套裝門檻不一致: %s" % steps)
    steps = sorted(steps.pop())
    chk(len(steps) >= 2, "門檻少於兩層, 頁面文案要重寫")
    chk(steps[-1] == per_line,
        "最高門檻 %d 件與每系列 %d 件對不上" % (steps[-1], per_line))

    # ---- 取得管道 ----
    sources = find_source(sorted(items), {v["aegis"] for v in items.values()})

    # ======================================================================
    #  HTML
    # ======================================================================
    style = re.search(r"<style>.*?</style>", read(STYLE_FROM, "utf-8"), re.S)
    chk(style, "potential.html 裡找不到 <style> 區塊")
    style = style.group(0)

    extra = """
<style>
h3.sub{font-family:"Noto Serif TC",serif; font-size:17px; margin:30px 0 4px;
       letter-spacing:.06em}
h3.sub .tag{font-family:"Noto Sans TC",sans-serif; font-size:12px; font-weight:500;
            letter-spacing:.14em; color:var(--cinnabar); margin-left:10px;
            padding:2px 8px; border:1px solid var(--cinnabar); border-radius:20px;
            vertical-align:3px}
.sub-desc{margin:0 0 12px; font-size:14px; color:var(--ink-soft)}
.eff{margin:0; padding:0; list-style:none}
.eff li{display:inline-block; padding:1px 8px; margin:2px 5px 2px 0;
        border-radius:6px; font-size:.9em; background:var(--sunk); color:var(--ink-soft)}
.eff li.up{background:var(--cinnabar-wash); color:var(--cinnabar); font-weight:700}
.thr{list-style:none; margin:0; padding:0; display:grid; gap:12px;
     grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.thr li{border:1px solid var(--rule); border-radius:10px; padding:13px 15px;
        background:var(--paper); box-shadow:var(--shadow)}
.thr b{display:block; font-family:"Noto Serif TC",serif; font-size:16px;
       margin-bottom:7px}
.callout{border-left:3px solid var(--cinnabar); padding:2px 0 2px 14px;
         margin:18px 0 0; color:var(--ink-soft); font-size:14.5px;
         line-height:1.85; max-width:72ch}
.callout b{color:var(--ink)}
.warn{border:1px solid var(--cinnabar); border-radius:10px; padding:14px 16px;
      margin:16px 0 0; font-size:14.5px; color:var(--ink-soft); line-height:1.85;
      background:var(--cinnabar-wash)}
.warn b{color:var(--ink)}
.rules{list-style:none; margin:0; padding:0; display:grid; gap:10px;
       grid-template-columns:repeat(auto-fit,minmax(250px,1fr))}
.rules li{border-left:3px solid var(--rule); padding:2px 0 2px 13px;
          font-size:14px; color:var(--ink-soft); line-height:1.8}
.rules li b{color:var(--ink); font-weight:700}
</style>
"""

    # ---- 三流派各自的 6 件 ----
    blocks = []
    for key, _var, cn, tag, desc in LINE:
        rows = []
        for iid in sorted(by_line[key], key=lambda i: LOC_ORDER.index(items[i]["loc"])):
            it = items[iid]
            effs = "".join("<li>%s</li>" % html.escape(e) for e in single[iid])
            rows.append('<tr><td>%s</td><td>%s</td><td class="num">%d</td>'
                        '<td><ul class="eff">%s</ul></td></tr>'
                        % (html.escape(it["name"]), LOC_CN[it["loc"]], iid, effs))
        lo, hi = seg[key]
        blocks.append(
            '<h3 class="sub">%s<span class="tag">%s</span></h3>'
            '<p class="sub-desc">%s　道具編號 %d ~ %d。</p>'
            '<div class="tbl-wrap"><table>'
            '<thead><tr><th>裝備</th><th>部位</th><th class="num">編號</th>'
            '<th>單件能力</th></tr></thead><tbody>%s</tbody></table></div>'
            % (html.escape(cn), html.escape(tag), html.escape(desc),
               lo, hi, "".join(rows)))
    line_blocks = "".join(blocks)

    # ---- 套裝門檻 ----
    thr_blocks = []
    for _key, var, cn, _tag, _desc in LINE:
        cards = []
        for n in steps:
            effs = "".join(
                '<li class="up">%s</li>' % html.escape(e) for e in thr[var][n])
            cards.append('<li><b>%d 件</b><ul class="eff">%s</ul></li>' % (n, effs))
        thr_blocks.append('<h3 class="sub">%s</h3><ul class="thr">%s</ul>'
                          % (html.escape(cn), "".join(cards)))
    thr_blocks = "".join(thr_blocks)

    # ---- 星雷追擊 ----
    star_rows = "".join([
        '<tr><td>第 1 階</td><td class="num">%d%%</td><td class="num">%g 秒</td>'
        '<td>%d 件套裝</td></tr>' % (star["bg_star_chance_t1"],
                                    star["bg_star_icd_t1"] / 1000.0, steps[-2]),
        '<tr><td>第 2 階</td><td class="num">%d%%</td><td class="num">%g 秒</td>'
        '<td>%d 件套裝</td></tr>' % (star["bg_star_chance_t2"],
                                    star["bg_star_icd_t2"] / 1000.0, steps[-1]),
    ])

    # ---- 取得管道 ----
    if sources:
        obtain = ('<p class="note">取得管道：%s</p>'
                  % html.escape("、".join(sources)))
    else:
        obtain = ('<div class="warn"><b>這 %d 件目前尚未開放取得。</b>'
                  '全服腳本裡找不到任何發放它們的地方 —— 沒有兌換、沒有掉落、'
                  '也沒有商城。下面列的是它們<b>開放之後</b>的能力，'
                  '取得方式等公告。</div>' % len(items))

    # ---- 規則 ----
    pvp_cn = "、".join(PVP_CN.get(f, f) for f in pvp_flags)
    rule_items = [
        "<li><b>玩家互打的場合一律不生效</b>　在%s裡，單件能力、所有套裝門檻"
        "與星雷追擊全部停用，只保留裝備欄占位。</li>" % pvp_cn,
    ]
    if not it0["refine"]:
        rule_items.append("<li><b>不能精煉</b>　本版沒有開放。</li>")
    if not it0["grade"]:
        rule_items.append("<li><b>不能附魔</b>　本版沒有開放。</li>")
    if it0["notrade"] or it0["nodrop"]:
        what = []
        if it0["notrade"]:
            what.append("交易")
        if it0["nodrop"]:
            what.append("丟棄")
        rule_items.append("<li><b>不能%s</b>　拿到就是自己的。</li>"
                          % "也不能".join(what))
    if len(steps) >= 2 and steps[-1] - steps[-2] > 1:
        rule_items.append(
            "<li><b>穿 %d 件 = 只拿到 %s 的效果</b>　"
            "門檻是「至少幾件」，中間的件數沒有額外特效。</li>"
            % (steps[-1] - 1, "、".join("%d 件" % n for n in steps[:-1])))
    rule_items.append("<li><b>只算同系列、不同部位</b>　"
                      "三個流派的件數各自獨立計算，混穿不會互相湊數。</li>")
    rules = "".join(rule_items)

    doc = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>三流派影子裝備</title>
<meta name="description" content="神域仙境 三流派影子裝備：破軍誅仙、太虛萬法、星雷幻舞各 __PER__ 件，套裝門檻與星雷追擊的完整數值。">
<meta name="color-scheme" content="light dark">
<meta property="og:type" content="website">
<meta property="og:site_name" content="神域仙境">
<meta property="og:title" content="三流派影子裝備">
<meta property="og:description" content="物理、法術、自詠普攻三條路線，各六件，穿越多越強。">
<meta property="og:image" content="https://drw-online.github.io/game/og.jpg">
<meta property="og:image:width" content="600">
<meta property="og:image:height" content="600">
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="#EFF1EC" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#121615" media="(prefers-color-scheme: dark)">
<link rel="icon" href="favicon.png" type="image/png">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Noto+Serif+TC:wght@500;700;900&display=swap">
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
    <h1>三流派影子裝備</h1>
    <p class="lede">三條路線各 <b>__PER__ 件</b>，穿在<b>影裝欄</b>、不佔一般裝備位。每一件自己就有能力，湊到 <b>__STEPS__ 件</b>還會再開一層。三個流派<b>各自算件數</b>，混穿不會互相湊數。</p>
  </header>

  <section>
    <h2>怎麼拿</h2>
    __OBTAIN__
  </section>

  <section>
    <h2>__TOTAL__ 件與各自的能力</h2>
    __LINES__
  </section>

  <section>
    <h2>套裝門檻</h2>
    <p class="note">下面是<b>額外</b>加上去的，單件能力照樣生效。穿滿 __PER__ 件就同時吃到 __STEPSTXT__ 這幾層。</p>
    __THRESHOLDS__
  </section>

  <section>
    <h2>星雷追擊</h2>
    <p class="note">星雷幻舞獨有。普通攻擊<b>造成實際傷害</b>時有機率自動放出一發<b>__BOLT__ Lv.__BOLTLV__</b>（風屬性魔法，__BOLTHIT__ 段）。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>階級</th><th class="num">發動率</th><th class="num">內置冷卻</th><th>來自</th></tr></thead>
        <tbody>__STAR__</tbody>
      </table>
    </div>
    <div class="callout">
      幾個容易誤會的地方：<b>一次普通攻擊只抽一次</b> —— 多段武器、雙持、二刀連擊都算同一次。
      <b>機率沒中不會進冷卻</b>，下一次普攻照樣抽。冷卻<b>不會被換裝、切圖或死亡重置</b>。
      追擊打出來的傷害<b>不會再觸發追擊</b>，也不吃吸血與吸魔。
      另外，<b>普通攻擊傷害加成不會加到追擊上</b> —— 那一條只認普攻本體。
    </div>
  </section>

  <section>
    <h2>規則</h2>
    <ul class="rules">__RULES__</ul>
  </section>

  <footer class="foot">
    資料以伺服器實際設定為準。若頁面內容與遊戲內不符，請以遊戲內為準並回報管理員。
  </footer>
</div>
</body>
</html>
"""

    rep = {
        "__STYLE__": style,
        "__EXTRA__": extra,
        "__PER__": str(per_line),
        "__TOTAL__": str(len(items)),
        "__STEPS__": "／".join(str(n) for n in steps),
        "__STEPSTXT__": "、".join("%d 件" % n for n in steps),
        "__OBTAIN__": obtain,
        "__LINES__": line_blocks,
        "__THRESHOLDS__": thr_blocks,
        "__BOLT__": html.escape(bolt),
        "__BOLTLV__": str(star["bg_star_skill_lv"]),
        "__BOLTHIT__": str(star["bg_star_skill_lv"]),
        "__STAR__": star_rows,
        "__RULES__": rules,
    }
    for k, v in rep.items():
        doc = doc.replace(k, v)

    left = sorted(set(re.findall(r"__[A-Z0-9_]+__", doc)))
    chk(not left, "有沒被替換掉的佔位符: %s" % left)

    with io.open(DEST, "w", encoding="utf-8", newline="\n") as f:
        f.write(doc)

    # ======================================================================
    #  反向驗證 —— 把寫出去的頁面重新解析回來跟來源對
    # ======================================================================
    out = read(DEST, "utf-8")
    back = re.findall(r"<tr><td>([^<]+)</td><td>([^<]+)</td>"
                      r'<td class="num">(\d+)</td>', out)
    chk(len(back) == len(items),
        "頁面只寫出 %d 件, 應該是 %d 件" % (len(back), len(items)))
    for nm, loc, iid in back:
        iid = int(iid)
        chk(iid in items, "頁面出現來源沒有的編號 %d" % iid)
        chk(nm == items[iid]["name"], "頁面的名稱 %s 與來源不符" % nm)
        chk(loc == LOC_CN[items[iid]["loc"]], "頁面的部位 %s 與來源不符" % loc)
    for iid, effs in single.items():
        for e in effs:
            chk(html.escape(e) in out, "單件能力「%s」沒出現在頁面上" % e)
    for var, tbl in thr.items():
        for n, effs in tbl.items():
            for e in effs:
                chk(html.escape(e) in out, "套裝能力「%s」沒出現在頁面上" % e)

    print("三流派 %d 件(每系列 %d) / 門檻 %s 件 / 單件能力 %d 條"
          % (len(items), per_line, "、".join(str(n) for n in steps),
             sum(len(v) for v in single.values())))
    print("星雷追擊 第1階 %d%% 冷卻 %gs / 第2階 %d%% 冷卻 %gs / %s Lv.%d"
          % (star["bg_star_chance_t1"], star["bg_star_icd_t1"] / 1000.0,
             star["bg_star_chance_t2"], star["bg_star_icd_t2"] / 1000.0,
             bolt, star["bg_star_skill_lv"]))
    print("PVP 停用範圍: %s" % "、".join(pvp_flags))
    if not sources:
        print("[!] 全服腳本找不到發放這些道具的地方, 頁面已標「尚未開放取得」")
    print("已寫出 %s (%d bytes)" % (DEST, os.path.getsize(DEST)))


if __name__ == "__main__":
    main()

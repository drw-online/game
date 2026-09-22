# -*- coding: utf-8 -*-
"""
手動打王區產生器 —— 產生 bossz.html, 跑完自己驗證一次。

用法:

    python tools/build_bossz.py

會覆寫 bossz.html。輸出是決定性的 —— 來源沒變的話重跑一次 git status
應該是乾淨的, 這也是最好的回歸測試。

--------------------------------------------------------------------------
來源 (全部在 2.開機擋)
--------------------------------------------------------------------------
  script/25.手動王區/00.設定.txt        地圖代號 $@BZ_MAP$ 與六面旗、地圖減傷
  script/05.魔物/16.手動王區_魔物.txt   常駐 spawn 清單(隻數/每種幾隻/重生秒數)
  db/import/blackgod/mob_bossz.yml      152 隻的數值與掉落
  db/import/blackgod/item_petegg_bossz.yml  152 顆寵物蛋
  db/import/blackgod/pet_bossz.yml      152 種寵物的捕捉/餵食參數
  db/import/mob_resist_db.yml           ResistProfile 100 的實際減傷
  db/import/mob_skill_db.txt            每一隻的技能組
  db/re/skill_db.yml + db/import        技能中文名(Description)

★ 這一頁沒有任何手寫的數值 —— 全部從上面那幾支解析。敘述可以手寫,
  數字不行: 手寫的數字會在改平衡時默默過期, 而網頁不會報錯。

★ 技能中文名要用 skill_db 的 Description 不是 Name —— Name 是 AegisName。
  (同 build_wanfa.py / build_spz.py)

★ 152 隻的數值「目前」完全一樣, 所以頁面把數值抽成一張共用表。
  verify 會檢查這個前提還成立 —— 哪天分級了就會當場失敗, 那時要改成逐隻列。

★ 技能分兩組:
    共通  152 隻都有的那幾招(反射盾 / 極限痛苦 / 魔法鏡 / 光之盾 / 治癒)
          —— 這幾招決定打法, 單獨拉一段講。
    各自  每隻各有幾招四轉攻擊技能, 放進可搜尋的對照表。
  兩組都是算出來的(取交集與差集), 不是寫死的名單。

★ 入場方式是「找出來」的不是寫死的 —— 掃全服腳本有沒有 warp 到這張圖。
  找不到就照實寫「還沒有入口 NPC」。
  [2026-09-22] 入口已經有了(萬境試煉使 -> script/25.手動王區/01.入口.txt)。
  它寫的是 `warp $@BZ_MAP$`, 所以 find_entrance 要先解地圖名變數 ——
  只比字面地圖名會誤報成「還沒有入口」。
"""
import io, os, re, sys, html, collections

try:
    import yaml
except ImportError:
    sys.exit("需要 PyYAML: pip install pyyaml")

HERE = os.path.dirname(os.path.abspath(__file__))
WEB  = os.path.dirname(HERE)
ROOT = r"H:\91.神域仙境"
SRV  = os.path.join(ROOT, "2.開機擋")
SRC  = os.path.join(ROOT, "1.原始碼")

F_CONF  = os.path.join(SRV, r"script\25.手動王區\00.設定.txt")
F_SPAWN = os.path.join(SRV, r"script\05.魔物\16.手動王區_魔物.txt")
F_MOB   = os.path.join(SRV, r"db\import\blackgod\mob_bossz.yml")
F_EGG   = os.path.join(SRV, r"db\import\blackgod\item_petegg_bossz.yml")
F_PET   = os.path.join(SRV, r"db\import\blackgod\pet_bossz.yml")
F_RES   = os.path.join(SRV, r"db\import\mob_resist_db.yml")
F_MSKL  = os.path.join(SRV, r"db\import\mob_skill_db.txt")
F_SHDEF = os.path.join(SRC, r"add\src\blackgod_boss_shield.inc")
F_SHENU = os.path.join(SRC, r"src\map\mob.hpp")
F_SHMAP = os.path.join(SRC, r"src\map\mob.cpp")

STYLE_FROM = os.path.join(WEB, "potential.html")
DEST       = os.path.join(WEB, "bossz.html")


def die(msg):
    sys.exit("build_bossz: " + msg)


def chk(cond, msg):
    if not cond:
        die(msg)


def read(path, enc="utf-8-sig"):
    with io.open(path, "r", encoding=enc) as f:
        return f.read()


def yload(path):
    with io.open(path, "r", encoding="utf-8-sig") as f:
        return (yaml.safe_load(f) or {}).get("Body") or []


def num(n):
    return "{:,}".format(int(n))


def rng(lo, hi):
    """數量不一致時寫成區間, 例如 4~6。"""
    return str(lo) if lo == hi else "%d~%d" % (lo, hi)


def cn_num(n):
    """大數字寫成中文量級, 例如 30000000000 -> 300 億。"""
    n = int(n)
    for unit, name in ((10 ** 8, "億"), (10 ** 4, "萬")):
        if n >= unit and n % unit == 0:
            return "%s %s" % (num(n // unit), name)
    return num(n)


# ==========================================================================
#  來源解析
# ==========================================================================
def parse_conf():
    """地圖代號、六面旗、地圖減傷。"""
    s = read(F_CONF)

    m = re.search(r'\$@BZ_MAP\$\s*=\s*"([^"]+)"', s)
    chk(m, "00.設定.txt 找不到 $@BZ_MAP$")
    mapname = m.group(1)

    flags, dmg = [], None
    for line in s.splitlines():
        line = line.strip()
        if line.startswith("//"):
            continue
        m = re.match(r"setmapflag\s+\$@BZ_MAP\$\s*,\s*(mf_\w+)\s*(?:,\s*(.+?))?\s*;", line)
        if not m:
            continue
        if m.group(1) == "mf_mobdmgrate":
            args = [a.strip() for a in (m.group(2) or "").split(",")]
            chk(len(args) == 2, "mf_mobdmgrate 必須有兩個參數(第 2 個沒給飄字會變 0)")
            dmg = (int(args[0]), int(args[1]))
        else:
            flags.append(m.group(1))

    chk(flags, "00.設定.txt 一面旗都沒解析到")
    chk(dmg, "00.設定.txt 找不到 mf_mobdmgrate")
    return mapname, flags, dmg


def parse_spawn(mapname):
    """常駐 spawn: 每種幾隻、重生毫秒。"""
    rows = []
    for line in read(F_SPAWN, "utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        m = re.match(r"^(\S+?),\d+,\d+,\d+,\d+\s+monster\s+(.+?)\s+(\d+),(\d+),(\d+)\s*$", line)
        if not m:
            continue
        chk(m.group(1) == mapname,
            "spawn 的地圖 %s 與 $@BZ_MAP$ %s 不一致" % (m.group(1), mapname))
        rows.append((int(m.group(3)), m.group(2), int(m.group(4)), int(m.group(5))))
    chk(rows, "16.手動王區_魔物.txt 一行 spawn 都沒解析到")
    return rows


def parse_mobs():
    out = {}
    for mb in yload(F_MOB):
        out[mb["Id"]] = mb
    chk(out, "mob_bossz.yml 沒有內容")
    return out


def parse_eggs():
    out = {}
    for it in yload(F_EGG):
        out[it["AegisName"]] = (it["Id"], it["Name"])
    return out


def parse_pets():
    out = {}
    for p in yload(F_PET):
        out[p["Mob"]] = p
    return out


def parse_resist(pid):
    for r in yload(F_RES):
        if r.get("Id") == pid:
            return r
    die("mob_resist_db.yml 找不到 ResistProfile %s" % pid)


def parse_mob_skills(ids):
    """mob_skill_db.txt 是 CSV: mobid,標籤@技能,狀態,技能id,等級,機率,...

    ★ 行首的 mobid 才是主鍵, 標籤欄(BG_BOSSZ001@XXX)只是給人看的。
    """
    want = set(ids)
    per = collections.defaultdict(list)
    with io.open(F_MSKL, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            c = line.split(",")
            if len(c) < 6 or not c[0].isdigit():
                continue
            mid = int(c[0])
            if mid not in want:
                continue
            per[mid].append((int(c[3]), int(c[4]), int(c[5])))
    return per


def read_skill_names(ids):
    want, got = set(ids), {}
    for rel in (r"db\re\skill_db.yml", r"db\import\skill_db.yml"):
        p = os.path.join(SRV, rel)
        if not os.path.exists(p):
            continue
        for s in yload(p):
            if s.get("Id") in want and s.get("Description"):
                got[s["Id"]] = s["Description"]
    return got


def parse_shields():
    """四大防禦的參數一律從原始碼取 —— 頁面不自己抄一份數字。

    ★ 這四招「不在 mob_skill_db 裡」。2026-09-22 起改成引擎實作
      (add/src/blackgod_boss_shield.inc), 所以掃技能表掃不到,
      舊版頁面那段寫死的文案整段過期了(還提到已經不存在的「魔法鏡」)。

    三個檔各取一段, 全部對得起來才算數:
      mob.hpp  enum e_bg_shield 的「順序」= bg_shield_def[] 的索引
      mob.cpp  ShieldOrder 的英文字串 -> BGS_*
      .inc     bg_shield_def[] 的參數與 BGS_* 常數
    """
    hpp = read(F_SHENU, "utf-8")
    m = re.search(r"enum\s+e_bg_shield\s*:\s*\w+\s*\{(.*?)\}", hpp, re.S)
    chk(m, "mob.hpp 找不到 enum e_bg_shield")
    order = re.findall(r"^\s*(BGS_\w+)", m.group(1), re.M)
    chk(order and order[0] == "BGS_NONE", "e_bg_shield 的第一項不是 BGS_NONE")
    chk(order[-1] == "BGS_MAX", "e_bg_shield 的最後一項不是哨兵 BGS_MAX")
    order = order[:-1]          # 去掉哨兵, 剩下 [NONE] + 實際的盾

    cpp = read(F_SHMAP, "utf-8")
    en = dict(re.findall(r'name\s*==\s*"(\w+)"\s*\)\s*sv\s*=\s*(BGS_\w+)', cpp))
    chk(len(en) == len(order) - 1,
        "mob.cpp 認得 %d 種 ShieldOrder 字串, 列舉有 %d 種" % (len(en), len(order) - 1))

    inc = read(F_SHDEF, "utf-8")
    m = re.search(r"bg_shield_def\[BGS_MAX\]\s*=\s*\{(.*?)\n\};", inc, re.S)
    chk(m, "blackgod_boss_shield.inc 找不到 bg_shield_def")
    rows = re.findall(r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,',
                      m.group(1))
    chk(len(rows) == len(order) - 1,
        "bg_shield_def 有 %d 列, 列舉有 %d 種盾" % (len(rows), len(order) - 1))

    # 階段 -> 血量百分比。從 bg_shield_phase() 的判斷式算, 不抄註解
    ph = {}
    for expr, p in re.findall(r"hp\s*<=\s*([^)]+?)\s*\)\s*return\s+(\d+);", inc):
        mm = re.fullmatch(r"mx\s*(?:\*\s*(\d+)\s*)?/\s*(\d+)", expr.strip())
        chk(mm, "bg_shield_phase 的判斷式看不懂: %r" % expr)
        ph[int(p)] = 100 * int(mm.group(1) or 1) // int(mm.group(2))
    chk(ph, "bg_shield_phase 一條判斷式都沒解析到")

    sh = {}
    for name, (cn, dur, cd, up, rate) in zip(order[1:], rows):
        up = int(up)
        chk(up in ph, "解鎖階段 %d 在 bg_shield_phase 裡沒有對應的血量" % up)
        sh[name] = {"cn": cn, "dur": int(dur), "cd": int(cd),
                    "hp": ph[up], "rate": int(rate)}

    k = {}
    for key in ("BGS_TELEGRAPH", "BGS_RF_WINDOW", "BGS_RF_CAP_PCT", "BGS_GAP_NORMAL"):
        mm = re.search(r"#define\s+%s\s+(\d+)" % key, inc)
        chk(mm, "blackgod_boss_shield.inc 找不到 %s" % key)
        k[key] = int(mm.group(1))

    return en, sh, k


def find_entrance(mapname):
    """全服腳本有沒有 warp 到這張圖 —— 有入口才寫得出「怎麼進去」。

    ★ 不能只比對字面地圖名。手動王區的入口寫的是 `warp $@BZ_MAP$, ...`,
      地圖名要到 25.手動王區/00.設定.txt 的 OnInit 才綁上去, 只比字面
      會誤報成「還沒有入口 NPC」。所以先掃一遍「哪些字串變數 = 這張圖」,
      再拿那些變數名一起比。
    """
    bodies = []
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
                    bodies.append((p, read(p, "utf-8")))
                except (UnicodeDecodeError, OSError):
                    continue

    # `$@BZ_MAP$ = "pvp_n_1-2"` 與 `set $@BZ_MAP$, "pvp_n_1-2"` 兩種寫法
    alias = set()
    pat = r'((?:\$@|\$|\.@|\.)\w+\$)\s*(?:=|,)\s*"%s"' % re.escape(mapname)
    for _p, body in bodies:
        if mapname not in body:
            continue
        for line in body.splitlines():
            t = line.strip()
            if t.startswith("//"):
                continue
            alias.update(re.findall(pat, t))

    hits = []
    for p, body in bodies:
        for line in body.splitlines():
            t = line.strip()
            if t.startswith("//"):
                continue
            if mapname not in t and not any(a in t for a in alias):
                continue
            if re.search(r"\bwarp\b|warpparty|warpguild|unitwarp", t):
                hits.append((os.path.relpath(p, SRV), t[:120]))
    return hits


# ==========================================================================
#  組頁面
# ==========================================================================
def main():
    mapname, flags, dmg = parse_conf()
    spawn   = parse_spawn(mapname)
    mobs    = parse_mobs()
    eggs    = parse_eggs()
    pets    = parse_pets()

    N = len(spawn)
    chk(len(mobs) == N, "spawn %d 隻 vs mob_bossz.yml %d 筆, 對不起來" % (N, len(mobs)))
    chk(len(pets) == N, "寵物 %d 筆 != 魔物 %d 隻" % (len(pets), N))

    ids = [r[0] for r in spawn]
    chk(len(set(ids)) == N, "spawn 有重複的魔物編號")
    chk(set(ids) == set(mobs), "spawn 的編號與 mob_bossz.yml 對不起來")

    amounts = {r[2] for r in spawn}
    delays  = {r[3] for r in spawn}
    chk(len(amounts) == 1 and len(delays) == 1,
        "spawn 的每種隻數/重生時間不一致: %s / %s" % (amounts, delays))
    amount, delay_ms = amounts.pop(), delays.pop()

    # ---- 數值: 152 隻必須完全一樣, 不然這一頁的抽法就不成立 ----
    FIELDS = ["Level", "Hp", "Attack", "Attack2", "Defense", "MagicDefense",
              "Resistance", "MagicResistance", "Dex", "AttackRange",
              "Size", "Race", "Element", "ElementLevel", "WalkSpeed",
              "AttackDelay", "BaseExp", "JobExp", "ResistProfile",
              "IgnoreDef", "IgnoreRes"]
    stat = {}
    for k in FIELDS:
        vals = {mb.get(k) for mb in mobs.values()}
        chk(len(vals) == 1,
            "欄位 %s 有 %d 種值 —— 152 隻不再共用同一組數值, "
            "這一頁要改成逐隻列數值" % (k, len(vals)))
        stat[k] = vals.pop()

    modes = {tuple(sorted((mb.get("Modes") or {}).items())) for mb in mobs.values()}
    chk(len(modes) == 1, "Modes 不一致")
    mode_set = dict(modes.pop())
    chk(mode_set.get("Mvp"), "這些魔物沒有 Mvp 旗標, 頁面不能寫成 MVP")

    # ---- 掉落: 把「自己的蛋」與「共通掉落」分開 ----
    own_egg, common = {}, None
    for mid, mb in mobs.items():
        mine, rest = None, []
        for d in mb.get("Drops") or []:
            if pets.get(mb["AegisName"], {}).get("EggItem") == d["Item"]:
                mine = (d["Item"], d["Rate"])
            else:
                rest.append((d["Item"], d["Rate"]))
        chk(mine, "%s 沒有掉自己的寵物蛋" % mb["AegisName"])
        own_egg[mid] = mine
        rest = tuple(sorted(rest))
        if common is None:
            common = rest
        chk(common == rest, "各隻的共通掉落不一致: %s vs %s" % (common, rest))

    egg_rates = {r for _, r in own_egg.values()}
    chk(len(egg_rates) == 1, "寵物蛋掉率不一致: %s" % egg_rates)
    egg_rate = egg_rates.pop()

    # 共通掉落的中文名
    item_name = {}
    d = os.path.join(SRV, "db", "import", "blackgod")
    want_items = {i for i, _ in common}
    for fn in sorted(os.listdir(d)):
        if fn.startswith("item_") and fn.endswith(".yml"):
            for it in yload(os.path.join(d, fn)):
                if it.get("AegisName") in want_items:
                    item_name[it["AegisName"]] = it["Name"]
    for i, _ in common:
        chk(i in item_name, "共通掉落 %s 查不到中文名" % i)

    # ---- 寵物參數 ----
    for k in ["FoodItem", "CaptureRate", "AllowAutoFeed"]:
        vals = {p.get(k) for p in pets.values()}
        chk(len(vals) == 1, "寵物欄位 %s 不一致" % k)
    capture_rate = list(pets.values())[0]["CaptureRate"]
    auto_feed    = list(pets.values())[0]["AllowAutoFeed"]
    for mid, mb in mobs.items():
        a = mb["AegisName"]
        chk(a in pets, "%s 沒有對應的寵物設定" % a)
        chk(pets[a]["EggItem"] in eggs, "%s 的蛋不在 item_petegg_bossz.yml" % a)

    # ---- 抗性模板 ----
    prof = parse_resist(stat["ResistProfile"])

    # ---- 技能 ----
    mskill = parse_mob_skills(ids)
    chk(len(mskill) == N, "只有 %d 隻有技能設定, 應該是 %d 隻" % (len(mskill), N))
    cnt = {len(v) for v in mskill.values()}
    per_lo, per_hi = min(cnt), max(cnt)

    sets = {mid: {s[0] for s in v} for mid, v in mskill.items()}
    shared = set.intersection(*sets.values())
    chk(shared, "152 隻沒有任何共通技能 —— 頁面的分組方式要重想")

    own_cnt = {mid: len(sets[mid] - shared) for mid in ids}
    own_lo, own_hi = min(own_cnt.values()), max(own_cnt.values())

    all_sk = {s[0] for v in mskill.values() for s in v}
    names = read_skill_names(all_sk)
    missing = sorted(all_sk - set(names))
    chk(not missing, "這些技能編號查不到中文名: %s" % missing[:10])

    # 共通技能的等級/機率(取第一隻的, 並驗證全服一致)
    shared_rows = []
    for sid, lv, rate in mskill[ids[0]]:
        if sid not in shared:
            continue
        for mid in ids:
            got = [x for x in mskill[mid] if x[0] == sid]
            chk(got and got[0] == (sid, lv, rate),
                "共通技能 %s 在各隻身上的等級/機率不一致" % names[sid])
        shared_rows.append((sid, lv, rate))

    # ---- 四大防禦 (引擎實作, 不在 mob_skill_db 裡) ----
    sh_en, sh_def, sh_k = parse_shields()
    mob_sh = {}
    for mid, mb in mobs.items():
        so = [e["Type"] for e in (mb.get("ShieldOrder") or [])]
        chk(so, "魔物 %d 沒有 ShieldOrder —— 牠不會放任何防禦" % mid)
        for t in so:
            chk(t in sh_en, "魔物 %d 的 ShieldOrder 有認不得的 %r" % (mid, t))
        mob_sh[mid] = [sh_en[t] for t in so]
    sh_used = collections.Counter(k for v in mob_sh.values() for k in v)
    chk(set(sh_used) == set(sh_def),
        "有盾沒被任何一隻用到(或用到沒定義的): %s"
        % (set(sh_def) ^ set(sh_used)))

    # ---- 入場方式 ----
    entrance = find_entrance(mapname)

    # ======================================================================
    #  HTML
    # ======================================================================
    style = re.search(r"<style>.*?</style>", read(STYLE_FROM, "utf-8"), re.S)
    chk(style, "potential.html 裡找不到 <style> 區塊")
    style = style.group(0)

    extra = """
<style>
.stats{list-style:none; margin:0; padding:0; display:grid; gap:12px;
       grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
.stats li{border:1px solid var(--rule); border-radius:10px; padding:12px 14px;
          background:var(--paper); box-shadow:var(--shadow)}
.stats b{display:block; font-size:12px; letter-spacing:.14em; color:var(--ink-faint);
         font-weight:500; margin-bottom:4px}
.stats span{font-family:"Noto Serif TC",serif; font-size:19px; font-weight:700}
.stats em{font-style:normal; font-size:13px; color:var(--ink-soft); display:block;
          margin-top:3px; letter-spacing:0}
.rules{list-style:none; margin:0; padding:0; display:grid; gap:10px;
       grid-template-columns:repeat(auto-fit,minmax(250px,1fr))}
.rules li{border-left:3px solid var(--rule); padding:2px 0 2px 13px;
          font-size:14px; color:var(--ink-soft); line-height:1.8}
.rules li b{color:var(--ink); font-weight:700}
.rules li.hot{border-left-color:var(--cinnabar)}
.callout{border-left:3px solid var(--cinnabar); padding:2px 0 2px 14px;
         margin:18px 0 0; color:var(--ink-soft); font-size:14.5px;
         line-height:1.85; max-width:72ch}
.callout b{color:var(--ink)}
h3.sub{font-family:"Noto Serif TC",serif; font-size:16px; margin:26px 0 10px;
       letter-spacing:.06em}
.sk{display:inline-block; padding:1px 8px; margin:2px 4px 2px 0; border-radius:6px;
    font-size:.86em; white-space:nowrap; background:var(--sunk); color:var(--ink-soft)}
td.skl{min-width:280px; line-height:2.1}
.warn{border:1px solid var(--cinnabar); border-radius:10px; padding:14px 16px;
      margin:16px 0 0; font-size:14px; color:var(--ink-soft); line-height:1.8;
      background:var(--cinnabar-wash)}
.warn b{color:var(--ink)}
</style>
"""

    ELE = {"Neutral": "無", "Water": "水", "Earth": "地", "Fire": "火",
           "Wind": "風", "Poison": "毒", "Holy": "聖", "Dark": "暗",
           "Ghost": "念", "Undead": "不死"}
    RACE = {"Formless": "無形", "Undead": "不死", "Brute": "動物", "Plant": "植物",
            "Insect": "昆蟲", "Fish": "魚貝", "Demon": "惡魔", "DemiHuman": "人形",
            "Angel": "天使", "Dragon": "龍"}
    SIZE = {"Small": "小型", "Medium": "中型", "Large": "大型"}

    hit = stat["Level"] + stat["Dex"] + 150      # status_calc_misc 重算
    cards = [
        ("等級", num(stat["Level"]), ""),
        ("生命", cn_num(stat["Hp"]), num(stat["Hp"])),
        ("攻擊", cn_num(stat["Attack"]), "物理與魔法同值"),
        ("命中", num(hit), "等級 + DEX + 150"),
        ("防禦", "%s / %s" % (num(stat["Defense"]), num(stat["MagicDefense"])),
         "物防 / 魔防"),
        ("抗性", "%s / %s" % (num(stat["Resistance"]), num(stat["MagicResistance"])),
         "RES / MRES"),
        ("屬性", "%s %d" % (ELE.get(stat["Element"], stat["Element"]),
                            stat["ElementLevel"]), ""),
        ("種族", RACE.get(stat["Race"], stat["Race"]),
         SIZE.get(stat["Size"], stat["Size"])),
        ("攻擊間隔", "%s 毫秒" % num(stat["AttackDelay"]),
         "攻擊距離 %d 格" % stat["AttackRange"]),
        ("經驗值", num(stat["BaseExp"]), "職業經驗 %s" % num(stat["JobExp"])),
        ("無視防禦", "%d%% / %d%%" % (stat["IgnoreDef"], stat["IgnoreRes"]),
         "你的 DEF / RES 只算得到一半"),
    ]
    stat_cards = "".join(
        "<li><b>%s</b><span>%s</span>%s</li>"
        % (html.escape(t), html.escape(v),
           "<em>%s</em>" % html.escape(e) if e else "")
        for t, v, e in cards)

    FLAG_CN = {
        "mf_noteleport": ("不能傳送", "蒼蠅翅膀與傳送類技能都用不了"),
        "mf_noreturn":   ("不能飛回城", "蝴蝶翅膀無效"),
        "mf_nomemo":     ("不能記錄傳送點", "這張圖不能當傳送目的地"),
        "mf_nosave":     ("死亡回存點", "死掉或斷線都不會留在圖上"),
        "mf_nobranch":   ("不能用枯枝", "召不出額外的怪"),
        "mf_loadevent":  ("進圖會觸發事件", "系統需要知道你進來了"),
    }
    take, show = dmg
    chk(show == 10000,
        "mf_mobdmgrate 的第 2 個參數是 %d 不是 10000 —— 飄字會與實際扣血不符" % show)
    rule_items = ['<li class="hot"><b>地圖減傷 %g%%</b>　魔物打到你的傷害只剩 '
                  '<b>%g%%</b>，飄字顯示的就是真正扣掉的血。</li>'
                  % (100 - take / 100.0, take / 100.0)]
    for f in flags:
        t, d = FLAG_CN.get(f, (f, ""))
        rule_items.append("<li><b>%s</b>　%s</li>" % (html.escape(t), html.escape(d)))
    rules = "".join(rule_items)

    pr = []
    for e in prof.get("Element") or []:
        pr.append(("所有屬性攻擊" if e["Type"] == "All"
                   else "%s屬性攻擊" % ELE.get(e["Type"], e["Type"]), e["Rate"]))
    RANGE_CN = {"Short": "近距離攻擊", "Long": "遠距離攻擊", "Magic": "魔法攻擊"}
    for r in prof.get("Range") or []:
        pr.append((RANGE_CN.get(r["Type"], r["Type"]), r["Rate"]))
    prof_rows = "".join(
        '<tr><td>%s</td><td class="num">%d%%</td><td>傷害只剩 %d%%</td></tr>'
        % (html.escape(t), v, 100 - v) for t, v in pr)

    # ---- 四大防禦表 ----
    #  ★ 白名單。多一種盾而沒補說法, 這裡會當場失敗而不是印出空白 ——
    #    與 FLAG_CN / RANGE_CN 同一個規矩。
    SHIELD_CN = {
        "BGS_REFLECT": "你打出的傷害 <b>%d%%</b> 反彈回自己身上",
        "BGS_PAIN":    "你打出的傷害 <b>%d%%</b> 反彈回自己身上",
        "BGS_MIRROR":  "你的<b>魔法</b>傷害只剩 <b>%d%%</b>",
        "BGS_LIGHT":   "你的<b>遠距離武器</b>傷害只剩 <b>%d%%</b>",
    }
    SHIELD_CUT = {"BGS_MIRROR", "BGS_LIGHT"}   # rate 是減傷, 不是反傷
    miss = sorted(set(sh_def) - set(SHIELD_CN))
    chk(not miss, "這幾種防禦還沒有中文說法: %s" % miss)

    shield_rows = "".join(
        '<tr><td>%s</td><td class="num">%g 秒</td><td class="num">%g 秒</td>'
        '<td class="num">%d%%</td><td>%s</td><td class="num">%d 隻</td></tr>'
        % (html.escape(sh_def[k]["cn"]), sh_def[k]["dur"] / 1000.0,
           sh_def[k]["cd"] / 1000.0, sh_def[k]["hp"],
           SHIELD_CN[k] % (100 - sh_def[k]["rate"] if k in SHIELD_CUT
                           else sh_def[k]["rate"]),
           sh_used[k])
        for k in sorted(sh_def, key=lambda k: -sh_used[k]))

    sh_rows = "".join(
        '<tr><td>%s</td><td class="num">Lv.%d</td><td class="num">%g%%</td></tr>'
        % (html.escape(names[sid]), lv, rate / 100.0)
        for sid, lv, rate in shared_rows)

    rows = []
    for mid in ids:
        mb = mobs[mid]
        eid, _ename = eggs[pets[mb["AegisName"]]["EggItem"]]
        own = sorted(s for s in sets[mid] if s not in shared)
        chips = "".join('<span class="sk">%s</span>' % html.escape(names[s]) for s in own)
        shn = [sh_def[k]["cn"] for k in mob_sh[mid]]
        shc = "".join('<span class="sk">%s</span>' % html.escape(n) for n in shn)
        key = "%s %d %d %s %s" % (mb["JapaneseName"], mid, eid,
                                  " ".join(shn), " ".join(names[s] for s in own))
        rows.append(
            '<tr data-k="%s"><td>%s</td><td class="num">%d</td>'
            '<td class="num">%d</td><td class="skl">%s</td>'
            '<td class="skl">%s</td></tr>'
            % (html.escape(key), html.escape(mb["JapaneseName"]), mid, eid,
               shc, chips))
    mob_rows = "".join(rows)

    drop_rows = ['<tr><td>自己的寵物蛋</td><td class="num">%g%%</td>'
                 '<td>每一隻掉自己那一顆，編號見下表</td></tr>'
                 % (egg_rate / 100.0)]
    for i, r in common:
        drop_rows.append('<tr><td>%s</td><td class="num">%g%%</td>'
                         '<td>%d 隻共通</td></tr>'
                         % (html.escape(item_name[i]), r / 100.0, N))
    drop_rows = "".join(drop_rows)

    if entrance:
        ent = ('<p class="note">入口在：%s</p>'
               % html.escape("、".join(sorted({h[0] for h in entrance}))))
    else:
        ent = ('<div class="warn"><b>目前還沒有入口 NPC。</b>'
               '全服腳本裡找不到任何通往這張圖的傳送點，所以這一區'
               '<b>還不能自己走進去</b>。開放方式等公告。</div>')

    pet_note = []
    if capture_rate == 0:
        pet_note.append("<b>不能用捕捉道具抓</b>，只能靠掉落的蛋")
    if auto_feed:
        pet_note.append("可以開自動餵食")
    pet_note = "、".join(pet_note) if pet_note else "詳見遊戲內"

    doc = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>手動打王區</title>
<meta name="description" content="神域仙境 手動打王區：__N__ 隻 MVP 同時在場、秒重生、地圖減傷 __CUT__%，每一隻都掉自己的寵物蛋。完整數值、技能與對照表。">
<meta name="color-scheme" content="light dark">
<meta property="og:type" content="website">
<meta property="og:site_name" content="神域仙境">
<meta property="og:title" content="手動打王區">
<meta property="og:description" content="一張圖上同時站著 __N__ 隻 MVP，死了一秒就回來。">
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
    <h1>手動打王區</h1>
    <p class="lede">一張圖上同時站著 <b>__N__ 隻 MVP</b>，每種各 __AMOUNT__ 隻，倒下 <b>__DELAY__ 秒</b>就回來。牠們<b>全部共用同一組數值</b>，差別只在各自會的攻擊技能，以及各自掉的那一顆寵物蛋。</p>
  </header>

  <section>
    <h2>這張圖的規則</h2>
    <ul class="rules">__RULES__</ul>
    __ENTRANCE__
    <p class="note">地圖代號 <b>__MAP__</b>。死亡不會掉裝備，也不是玩家互打的區域 —— 原本掛在這張圖上的死亡掉裝與 PVP 旗標都已經拿掉了。</p>
  </section>

  <section>
    <h2>魔物數值</h2>
    <ul class="stats">__STATS__</ul>
    <p class="note">__N__ 隻<b>完全一樣</b>，沒有強弱之分。全部帶 MVP 旗標，而且是偵測型 —— 躲隱形沒有用。</p>

    <h3 class="sub">額外抗性</h3>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>對什麼</th><th class="num">減傷</th><th>結果</th></tr></thead>
        <tbody>__PROF__</tbody>
      </table>
    </div>
    <p class="note">這一層疊在上面的 RES／MRES 之外。<b>遠距離比近距離更吃虧</b>，而且下面的防禦還會再砍一次。</p>
  </section>

  <section>
    <h2>四大防禦</h2>
    <p class="note">這四招<b>不是技能</b>，是系統排的，所以技能表裡看不到。開始前會先跳一行<b>紅字預警</b>，__TELE__ 秒後才真的生效 —— 看到字就停手。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>防禦</th><th class="num">持續</th><th class="num">冷卻</th><th class="num">血量門檻</th><th>對你的影響</th><th class="num">幾隻會</th></tr></thead>
        <tbody>__SHIELDS__</tbody>
      </table>
    </div>
    <div class="callout">
      <b>每一隻固定只會其中兩種</b>，輪流放 —— 誰會哪兩種見最下面那張表。
      血量門檻是「掉到那個百分比以下才會開始放」，所以開場不會有。
      反彈傷害有上限：每 __RFWIN__ 秒最多吃到自己 <b>__RFCAP__%</b> 的血，
      一次不會被秒殺，但站著硬打一樣會死。防禦結束後有 <b>__GAP__ 秒</b>的空窗，那才是輸出時間。
    </div>
  </section>

  <section>
    <h2>每一隻都會的 __SHN__ 招</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>技能</th><th class="num">等級</th><th class="num">發動率</th></tr></thead>
        <tbody>__SHARED__</tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>掉什麼</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>物品</th><th class="num">機率</th><th>說明</th></tr></thead>
        <tbody>__DROPS__</tbody>
      </table>
    </div>
    <p class="note">孵出來的寵物__PETNOTE__。</p>
  </section>

  <section>
    <h2>__N__ 隻對照表</h2>
    <div class="controls">
      <div class="ctl-row">
        <div class="search"><input id="q" type="search" placeholder="輸入魔物名、編號或技能名…" autocomplete="off" aria-label="搜尋魔物"></div>
        <div class="tally"><b id="shown">__N__</b> / __N__ 隻</div>
      </div>
    </div>
    <div class="tbl-wrap">
      <table id="tbl">
        <thead><tr><th>魔物</th><th class="num">魔物編號</th><th class="num">蛋編號</th><th>會的兩種防禦</th><th>各自的攻擊技能</th></tr></thead>
        <tbody>__ROWS__</tbody>
      </table>
    </div>
    <p class="note">每一隻各有 <b>__OWNN__ 招</b>自己的攻擊技能，加上上面那 __SHN__ 招共通的，合計 __PERN__ 招。</p>
  </section>

  <footer class="foot">
    資料以伺服器實際設定為準。若頁面內容與遊戲內不符，請以遊戲內為準並回報管理員。
  </footer>
</div>

<script>
(function(){
  var box = document.getElementById('q');
  var tb  = document.querySelector('#tbl tbody');
  var out = document.getElementById('shown');
  if(!box || !tb) return;
  var rows = Array.prototype.slice.call(tb.querySelectorAll('tr'));
  box.addEventListener('input', function(){
    var s = box.value.trim().toLowerCase(), n = 0;
    rows.forEach(function(tr){
      var hit = !s || tr.getAttribute('data-k').toLowerCase().indexOf(s) >= 0;
      tr.hidden = !hit;
      if(hit) n++;
    });
    if(out) out.textContent = n;
  });
})();
</script>
</body>
</html>
"""

    rep = {
        "__STYLE__": style,
        "__EXTRA__": extra,
        "__N__": str(N),
        "__AMOUNT__": str(amount),
        "__DELAY__": "%g" % (delay_ms / 1000.0),
        "__MAP__": html.escape(mapname),
        "__CUT__": "%g" % (100 - take / 100.0),
        "__RULES__": rules,
        "__ENTRANCE__": ent,
        "__STATS__": stat_cards,
        "__PROF__": prof_rows,
        "__SHN__": str(len(shared_rows)),
        "__SHIELDS__": shield_rows,
        "__TELE__": "%g" % (sh_k["BGS_TELEGRAPH"] / 1000.0),
        "__RFWIN__": "%g" % (sh_k["BGS_RF_WINDOW"] / 1000.0),
        "__RFCAP__": str(sh_k["BGS_RF_CAP_PCT"]),
        "__GAP__": "%g" % (sh_k["BGS_GAP_NORMAL"] / 1000.0),
        "__SHARED__": sh_rows,
        "__DROPS__": drop_rows,
        "__PETNOTE__": pet_note,
        "__ROWS__": mob_rows,
        "__OWNN__": rng(own_lo, own_hi),
        "__PERN__": rng(per_lo, per_hi),
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
    back = re.findall(r'<tr data-k="[^"]*"><td>([^<]+)</td><td class="num">(\d+)</td>'
                      r'<td class="num">(\d+)</td>', out)
    chk(len(back) == N, "頁面只寫出 %d 列, 應該是 %d 列" % (len(back), N))
    for (nm, mid, eid), want_id in zip(back, ids):
        mb = mobs[want_id]
        chk(int(mid) == want_id, "頁面的魔物編號 %s 與來源 %d 不符" % (mid, want_id))
        chk(nm == mb["JapaneseName"], "頁面的魔物名 %s 與來源不符" % nm)
        chk(int(eid) == eggs[pets[mb["AegisName"]]["EggItem"]][0],
            "頁面的蛋編號與來源不符 (魔物 %d)" % want_id)
    chk(out.count('class="sk"') == sum(own_cnt.values()) + 2 * N,
        "技能標籤總數對不上")
    for k, v in sh_def.items():
        chk(out.count(">%s<" % v["cn"]) + out.count(">%s</span>" % v["cn"]) > 0,
            "頁面沒寫出防禦 %s" % v["cn"])

    print("地圖 %s / %d 隻 MVP / 每種 %d 隻 / 重生 %g 秒"
          % (mapname, N, amount, delay_ms / 1000.0))
    print("旗標 %d 面 + 地圖減傷 %g%%" % (len(flags), 100 - take / 100.0))
    print("數值 Lv.%d HP %s ATK %s 命中 %s"
          % (stat["Level"], num(stat["Hp"]), num(stat["Attack"]), num(hit)))
    print("技能 每隻 %s 招 (共通 %d + 各自 %s), 技能中文名 %d 種"
          % (rng(per_lo, per_hi), len(shared_rows), rng(own_lo, own_hi), len(names)))
    print("防禦 %s (預警 %g 秒, 空窗 %g 秒, 反傷上限 每 %g 秒 %d%%)"
          % (" / ".join("%s %d隻" % (sh_def[k]["cn"], sh_used[k])
                        for k in sorted(sh_def, key=lambda k: -sh_used[k])),
             sh_k["BGS_TELEGRAPH"] / 1000.0, sh_k["BGS_GAP_NORMAL"] / 1000.0,
             sh_k["BGS_RF_WINDOW"] / 1000.0, sh_k["BGS_RF_CAP_PCT"]))
    if not entrance:
        print("[!] 找不到任何 warp 到 %s 的入口, 頁面已標註「還沒有入口 NPC」" % mapname)
    print("已寫出 %s (%d bytes)" % (DEST, os.path.getsize(DEST)))


if __name__ == "__main__":
    main()

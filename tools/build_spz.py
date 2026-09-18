# -*- coding: utf-8 -*-
"""
技能專精玩法指南產生器 —— 產生 spz.html, 跑完自己驗證一次。

用法:

    python tools/build_spz.py

會覆寫 spz.html。輸出是決定性的 —— 來源沒變的話重跑一次 git status
應該是乾淨的, 這也是最好的回歸測試。

--------------------------------------------------------------------------
來源 (全部在 2.開機擋)
--------------------------------------------------------------------------
  script/19.技能專精/00.設定.txt    全部 $@SPZ_* (唯一的數值來源)
  script/19.技能專精/01.對照表.txt  $@SPZ_LINE$ 十一職系
  script/19.技能專精/04.技能表.txt  白名單 $@SPZ_SKTY / SKLV / SKVC / SKDL / SKBK / SKLN
  script/21.專精換取/00.設定.txt    靈髓換取的配方數與四個技能書配方
  script/04.系統/12.境界突破.txt    $@realm_name$ (解鎖門檻那一境的名字)
  db/re/skill_db.yml + db/import/skill_db.yml   技能中文名取 Description

★★ 這一頁沒有任何手寫的數值 ★★
  敘述是手寫的, 數字全部解析而來。唯一例外是 verify 裡的預期值 ——
  那是刻意寫死來擋改動的。

★ 「練滿一支技能的期望成本」是算出來的, 不是抄註解 ——
  突破固定 5%、失敗掉到「目標級 - 1 - BREAK_DROP」, 所以失敗會往回走,
  期望值要解線性方程式(21 個狀態)而不是把每級相加。
  00.設定.txt 第七節的註解寫著「一個技能練滿期望吃 8,905 本一轉書、
  191 億 Zeny」, 驗證時拿算出來的值跟它對照, 差超過 2% 就中止 ——
  註解過期或模型寫錯都攔得下來。

★ 技能中文名取 skill_db 的 Description 不是 Name(Name 是 AegisName),
  與 wanfa.html 同一個做法。
"""
import io, json, os, re, sys, html

HERE = os.path.dirname(os.path.abspath(__file__))
WEB  = os.path.dirname(HERE)
ROOT = r"H:\91.神域仙境"
SRV  = os.path.join(ROOT, "2.開機擋")
SPZ  = os.path.join(SRV, r"script\19.技能專精")

F_CONF  = os.path.join(SPZ, "00.設定.txt")
F_TABLE = os.path.join(SPZ, "01.對照表.txt")
F_SKILL = os.path.join(SPZ, "04.技能表.txt")
F_EXCH  = os.path.join(SRV, r"script\21.專精換取\00.設定.txt")
F_REALM = os.path.join(SRV, r"script\04.系統\12.境界突破.txt")
F_SKDB  = [os.path.join(SRV, r"db\re\skill_db.yml"),
           os.path.join(SRV, r"db\import\skill_db.yml")]

STYLE_FROM = os.path.join(WEB, "potential.html")
DEST       = os.path.join(WEB, "spz.html")


def chk(cond, msg):
    if not cond:
        sys.exit("驗證失敗: " + msg)


# ==========================================================================
#  來源解析
# ==========================================================================
def read(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


def strip_comments(text):
    """去掉 // 之後的內容, 但不動字串裡的 //。"""
    out = []
    for line in text.split("\n"):
        buf, inq, i = [], False, 0
        while i < len(line):
            c = line[i]
            if c == '"':
                inq = not inq
            elif not inq and c == "/" and i + 1 < len(line) and line[i + 1] == "/":
                break
            buf.append(c)
            i += 1
        out.append("".join(buf))
    return "\n".join(out)


def split_vals(s):
    vals, cur, inq = [], "", False
    for c in s:
        if c == '"':
            inq = not inq
            cur += c
        elif c == "," and not inq:
            vals.append(cur.strip())
            cur = ""
        else:
            cur += c
    if cur.strip():
        vals.append(cur.strip())
    return vals


def conv(tok):
    if tok.startswith('"') and tok.endswith('"'):
        return tok[1:-1]
    try:
        return int(tok)
    except ValueError:
        return tok


ARR_RE = re.compile(r"setarray\s+(\$@\w+\$?)\s*\[\s*(\d+)\s*\]\s*,(.*?);", re.S)
#  ★ 純量「不能」綁行首 —— 00.設定.txt 有一行寫兩個賦值:
#      $@SPZ_BK_WD10 = 10;	$@SPZ_BK_B2_10 = 20;
#    綁了 ^ 的話第二個永遠抓不到, 而且只會在用到它的時候才 KeyError。
#    名字後面緊接 [ 的是陣列指派, 這個式子自然不會match(中間隔著 [)。
SCA_RE = re.compile(r"(\$@\w+\$?)\s*=\s*([^;]+);")


def parse(text):
    """回 (arrays, scalars); arrays[name] = {index: value}。"""
    text = strip_comments(text)
    arrays, scalars = {}, {}
    for m in ARR_RE.finditer(text):
        name, start = m.group(1), int(m.group(2))
        d = arrays.setdefault(name, {})
        for i, tok in enumerate(split_vals(m.group(3))):
            if tok != "":
                d[start + i] = conv(tok)
    for m in SCA_RE.finditer(text):
        name, val = m.group(1), m.group(2).strip()
        if name in arrays:
            continue
        scalars[name] = conv(val)
    return arrays, scalars


def seq(arr, lo, hi):
    """把 {index: value} 取成 lo..hi 的 list, 缺格一律中止。"""
    out = []
    for i in range(lo, hi + 1):
        chk(i in arr, f"陣列缺索引 {i} (需要 {lo}~{hi})")
        out.append(arr[i])
    return out


def skill_names():
    """技能數字 ID -> 中文名(Description)。import 覆蓋 base。"""
    name = {}
    for path in F_SKDB:
        if not os.path.exists(path):
            continue
        cur = None
        for line in io.open(path, "r", encoding="utf-8", errors="replace"):
            m = re.match(r"^  - Id:\s*(\d+)\s*$", line)
            if m:
                cur = int(m.group(1))
                continue
            if cur is None:
                continue
            m = re.match(r"^    Description:\s*(.+?)\s*$", line)
            if m:
                name[cur] = m.group(1).strip('"')
    return name


# ==========================================================================
#  期望成本 —— 突破失敗會往回走, 所以要解線性方程式
# ==========================================================================
def expected_cost(cost_tables, extra, breaks, rate, drop, maxlv):
    """
    cost_tables: {材料名: [第1級, ..., 第maxlv級]}
    extra:       {等級: {材料名: 數量}}  突破另計的材料
    回 ({材料名: 期望總量}, {突破等級: 期望嘗試次數})。

    狀態 = 目前等級 0..maxlv。想升到 T = L+1 時付一次 T 級的材料;
    T 不是突破點就必定成功(06.升級.txt「一般升級固定成功」);
    是突破點則 rate/10000 成功, 否則掉到 T - 1 - drop。
    失敗會回到更低的狀態, 所以先解「每一級的期望嘗試次數」。
    """
    n = maxlv + 1
    p = rate / 10000.0
    # 期望造訪次數 f: (I - P^T) f = e0
    A = [[0.0] * n for _ in range(n)]
    b = [0.0] * n
    b[0] = 1.0
    for L in range(n):
        A[L][L] += 1.0
    for L in range(maxlv):
        T = L + 1
        if T in breaks:
            A[T][L] -= p
            A[max(T - 1 - drop, 0)][L] -= (1.0 - p)
        else:
            A[T][L] -= 1.0
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(A[r][col]))
        chk(abs(A[piv][col]) > 1e-12, "期望成本: 轉移矩陣奇異, 解不出來")
        A[col], A[piv] = A[piv], A[col]
        b[col], b[piv] = b[piv], b[col]
        for r in range(n):
            if r == col:
                continue
            k = A[r][col] / A[col][col]
            if k == 0.0:
                continue
            for c in range(col, n):
                A[r][c] -= k * A[col][c]
            b[r] -= k * b[col]
    visits = [b[i] / A[i][i] for i in range(n)]

    tries = {L + 1: visits[L] for L in range(maxlv)}
    total = {}
    for mat, tbl in cost_tables.items():
        s = 0.0
        for T, t in tries.items():
            s += t * tbl[T - 1]
            if T in extra and mat in extra[T]:
                s += t * extra[T][mat]
        total[mat] = s
    return total, {bkl: tries[bkl] for bkl in sorted(breaks)}


# ==========================================================================
#  小工具
# ==========================================================================
def esc(s):
    return html.escape(str(s), quote=False)


def num(v):
    return f"{v:,}"


def zh_zeny(z):
    """Zeny 轉成「N 億」/「N 萬」的中文說法。"""
    if z >= 100000000 and z % 100000000 == 0:
        return f"{z // 100000000} 億"
    if z >= 100000000:
        return f"{z / 100000000:g} 億"
    if z >= 10000 and z % 10000 == 0:
        return f"{z // 10000} 萬"
    return num(z)


def main():
    conf_a, conf_s = parse(read(F_CONF))
    tbl_a,  tbl_s  = parse(read(F_TABLE))
    sk_a,   _      = parse(read(F_SKILL))
    ex_a,   ex_s   = parse(read(F_EXCH))
    realm_a, _     = parse(read(F_REALM))
    SKNAME = skill_names()

    MAXLV = conf_s["$@SPZ_MAXLV"]
    chk(MAXLV == 20, f"$@SPZ_MAXLV = {MAXLV}, 這一頁的版面是照 20 級排的")

    # ---- 每級消耗 (七張平行表) ----
    #  ★ B1~B4 的單位是「同職系同轉技能書幾本」不是殘頁 ——
    #    06.升級.txt 檔頭: 殘頁每 $@SPZ_DECOMP[階] 張抵 1 本。
    MATS = [("B1", "一轉書"), ("B2", "二轉書"), ("B3", "三轉書"),
            ("B4", "四轉書"), ("SL", "專精靈髓"), ("WD", "悟道石"),
            ("ZY", "Zeny(百萬)")]
    cost = {k: seq(conf_a[f"$@SPZ_{k}"], 1, MAXLV) for k, _ in MATS}

    # ---- 階段總量 (對帳用) ----
    st_lo = seq(conf_a["$@SPZ_ST_LO"], 1, 5)
    st_hi = seq(conf_a["$@SPZ_ST_HI"], 1, 5)
    st = {k: seq(conf_a[f"$@SPZ_ST_{k}"], 1, 5) for k, _ in MATS}

    # ---- 突破 ----
    breaks = sorted(seq(conf_a["$@SPZ_BREAK"], 0, conf_s["$@SPZ_BREAKN"] - 1))
    brate  = conf_s["$@SPZ_BREAK_RATE"]
    bdrop  = conf_s["$@SPZ_BREAK_DROP"]
    extra_cost = {
        breaks[0]: {"SL": conf_s["$@SPZ_BK_SOUL5"]},
        breaks[1]: {"WD": conf_s["$@SPZ_BK_WD10"]},
        breaks[2]: {},
        breaks[3]: {},
    }
    exp_total, exp_tries = expected_cost(cost, extra_cost, set(breaks),
                                        brate, bdrop, MAXLV)

    # ---- 效果曲線 ----
    W = seq(conf_a["$@SPZ_W"], 1, MAXLV)
    R = seq(conf_a["$@SPZ_R"], 1, MAXLV)
    DMGCAP = seq(conf_a["$@SPZ_DMGCAP"], 1, 4)
    RESCAP = seq(conf_a["$@SPZ_RESCAP"], 1, 3)
    up = lambda cap, w: (cap * w + 99) // 100      # 05.效果.txt 的無條件進位

    # ---- 類型 / 階段 / 路線 / 極意 ----
    TYPE  = seq(conf_a["$@SPZ_TYPE$"], 1, 8)
    TYPED = seq(conf_a["$@SPZ_TYPEDESC$"], 1, 8)
    TIER  = seq(conf_a["$@SPZ_TIER$"], 1, 4)
    TLO   = seq(conf_a["$@SPZ_TIER_LO"], 1, 4)
    THI   = seq(conf_a["$@SPZ_TIER_HI"], 1, 4)
    BR    = seq(conf_a["$@SPZ_BR$"], 1, 2)
    BRD   = seq(conf_a["$@SPZ_BRDESC$"], 1, 2)
    UL    = seq(conf_a["$@SPZ_UL$"], 1, 2)
    ULD   = seq(conf_a["$@SPZ_ULDESC$"], 1, 2)

    # ---- 職系與白名單 ----
    LINEN = tbl_s["$@SPZ_LINEN"]
    LINE  = seq(tbl_a["$@SPZ_LINE$"], 1, LINEN)
    ty, lvc, bk, ln = (sk_a["$@SPZ_SKTY"], sk_a["$@SPZ_SKLV"],
                       sk_a["$@SPZ_SKBK"], sk_a["$@SPZ_SKLN"])
    vc, dl = sk_a.get("$@SPZ_SKVC", {}), sk_a.get("$@SPZ_SKDL", {})

    skills = []
    for sid, t in sorted(ty.items()):
        if not t:
            continue
        chk(sid in lvc and sid in ln and sid in bk,
            f"技能 {sid} 在 SKTY 有值, 但 SKLV/SKLN/SKBK 缺一 —— 04.技能表.txt 對不齊")
        nm = SKNAME.get(sid)
        chk(bool(nm), f"技能 {sid} 在 skill_db 找不到 Description")
        skills.append({"id": sid, "n": nm, "t": t, "c": lvc[sid],
                       "l": ln[sid], "b": bk[sid],
                       "vc": vc.get(sid, 0), "dl": dl.get(sid, 0)})
    CLASSN = ["一般", "核心", "終極"]

    # ---- 解鎖 ----
    need_realm = conf_s["$@SPZ_NEED_REALM"]
    chk(need_realm in realm_a["$@realm_name$"],
        f"12.境界突破.txt 沒有第 {need_realm} 境的名字")
    realm_name = realm_a["$@realm_name$"][need_realm]
    open_zeny  = conf_s["$@SPZ_OPEN_ZENY"]
    open_book  = conf_s["$@SPZ_OPEN_BOOK"]
    need_job4  = conf_s["$@SPZ_NEED_JOB4"]

    # ---- 分解與投入 ----
    decomp = seq(conf_a["$@SPZ_DECOMP"], 1, 4)
    decomp_other = conf_s["$@SPZ_DECOMP_OTHER"]
    feed_line  = conf_s["$@SPZ_FEED_SAMELINE"]
    feed_skill = conf_s["$@SPZ_FEED_SAMESKILL"]

    # ---- 槽 ----
    slot_n, slot_c, slot_u, slot_t = (conf_s["$@SPZ_SLOT_NORMAL"],
                                      conf_s["$@SPZ_SLOT_CORE"],
                                      conf_s["$@SPZ_SLOT_ULT"],
                                      conf_s["$@SPZ_SLOT_TOTAL"])
    slot_clv, slot_ulv = conf_s["$@SPZ_SLOT_CORE_LV"], conf_s["$@SPZ_SLOT_ULT_LV"]
    slot_cd = conf_s["$@SPZ_SLOT_CD"]

    # ---- 重煉 / 重置 ----
    rf1_n, rf1_z = conf_s["$@SPZ_RF1_N"], conf_s["$@SPZ_RF1_ZENY"]
    rf2_n, rf2_s = conf_s["$@SPZ_RF2_N"], conf_s["$@SPZ_RF2_SOUL"]
    rf_box = seq(conf_a["$@SPZ_RF_BOX_N"], 1, 3)
    rs_lun, rs_zeny = conf_s["$@SPZ_RESET_LUNHUI"], conf_s["$@SPZ_RESET_ZENY"]
    rs_back, rs_bkback = conf_s["$@SPZ_RESET_BACK"], conf_s["$@SPZ_RESET_BKBACK"]
    sw_lun, sw_book, sw_cd = (conf_s["$@SPZ_SWITCH_LUNHUI"],
                              conf_s["$@SPZ_SWITCH_BOOK"],
                              conf_s["$@SPZ_SWITCH_CD"])

    # ---- 靈髓換取 (四個技能書配方 + 總配方數) ----
    ex_n = ex_s["$@SPZX_N"]
    book_rec = [{"name": ex_a["$@SPZX_Name$"][r], "tier": r + 1,
                 "qty": ex_a["$@SPZX_MQty"][r], "zeny": ex_a["$@SPZX_Zeny"][r],
                 "out": ex_a["$@SPZX_Out"][r], "same": ex_a["$@SPZX_SameN"][r]}
                for r in range(4)]

    # ======================================================================
    #  驗證 (產生之前)
    # ======================================================================
    for key, label in MATS:
        for i in range(5):
            s = sum(cost[key][lv - 1] for lv in range(st_lo[i], st_hi[i] + 1))
            chk(s == st[key][i],
                f"{label} 第 {i+1} 階段 (Lv.{st_lo[i]}~{st_hi[i]}) 每級合計 {s} "
                f"!= 階段表 {st[key][i]}")
    chk(len(breaks) == conf_s["$@SPZ_BREAKN"] == 4, "突破點不是 4 個")
    chk(breaks == [5, 10, 15, 20], f"突破點變成 {breaks}, 版面文案要跟著改")
    chk(THI == breaks, "階段終點與突破點對不上")
    chk(len(TYPE) == len(TYPED) == 8, "專精類型不是 8 種")
    chk(all(TYPE) and all(TYPED), "專精類型有空白")
    chk(W[MAXLV - 1] + conf_s["$@SPZ_BR_B_DMG"] + conf_s["$@SPZ_UL_B_DMG"] == 100,
        "Lv.20 + 激進 + 破界 的主效果權重不是 100, 上限就打不滿了")
    chk(R[MAXLV - 1] + conf_s["$@SPZ_BR_A_RES"] + conf_s["$@SPZ_UL_A_RES"] <= 100,
        "資源補正權重會超過 100")
    chk(slot_n + slot_c + slot_u == slot_t, "槽數加總與 $@SPZ_SLOT_TOTAL 不一致")
    chk(len(skills) > 100, f"白名單只有 {len(skills)} 支, 太少, 先確認 04.技能表.txt")
    chk(all(1 <= s["t"] <= 8 for s in skills), "有技能的專精類型超出 1~8")
    chk(all(1 <= s["c"] <= 3 for s in skills), "有技能的級別超出 1~3")
    chk(all(1 <= s["l"] <= LINEN for s in skills), "有技能的職系超出範圍")
    chk(ex_n == 38, f"靈髓換取的配方數變成 {ex_n}, 頁面文案要跟著改")
    chk(all(b["qty"] > 0 and b["zeny"] > 0 for b in book_rec),
        "技能書換靈髓的配方有 0")

    exp_book1 = exp_total["B1"]          # 單位就是「本」
    exp_zeny  = exp_total["ZY"] * 1000000
    chk(abs(exp_book1 - 8905) / 8905 < 0.02,
        f"算出來的一轉書期望 {exp_book1:.0f} 本與 00.設定.txt 註解的 8,905 本差超過 2% "
        f"—— 模型或註解有一個過期了")
    chk(abs(exp_zeny / 100000000 - 191) / 191 < 0.02,
        f"算出來的 Zeny 期望 {exp_zeny/100000000:.1f} 億與註解的 191 億差超過 2%")

    # ======================================================================
    #  表格
    # ======================================================================
    def tier_of(lv):
        for i in range(4):
            if TLO[i] <= lv <= THI[i]:
                return TIER[i]
        return ""

    rows = []
    for lv in range(1, MAXLV + 1):
        mark = ' <span class="bn">突破</span>' if lv in breaks else ""
        cells = "".join(
            f'<td class="num">{num(cost[k][lv-1]) if cost[k][lv-1] else "—"}</td>'
            for k, _ in MATS[:-1])
        rows.append(f'<tr><td class="num">Lv.{lv}{mark}</td><td>{esc(tier_of(lv))}</td>'
                    f'{cells}<td class="num">{num(cost["ZY"][lv-1])} 百萬</td></tr>')
    cost_rows = "\n".join(rows)

    rows = []
    for i in range(5):
        rng = f"Lv.{st_lo[i]}" if st_lo[i] == st_hi[i] else f"Lv.{st_lo[i]}~{st_hi[i]}"
        cells = "".join(f'<td class="num">{num(st[k][i]) if st[k][i] else "—"}</td>'
                        for k, _ in MATS)
        rows.append(f"<tr><td>{rng}</td>{cells}</tr>")
    stage_rows = "\n".join(rows)

    rows = []
    for lv in range(1, MAXLV + 1):
        mark = ' <span class="bn">突破</span>' if lv in breaks else ""
        main = "".join(f'<td class="num">+{up(DMGCAP[c], W[lv-1])}%</td>' for c in range(3))
        res = "".join(
            (f'<td class="num">−{up(RESCAP[c], R[lv-1])}%</td>' if R[lv - 1]
             else '<td class="num">—</td>') for c in range(3))
        rows.append(f'<tr><td class="num">Lv.{lv}{mark}</td>'
                    f'<td class="num">{W[lv-1]}</td>{main}'
                    f'<td class="num">{R[lv-1]}</td>{res}</tr>')
    eff_rows = "\n".join(rows)

    type_rows = "\n".join(
        f'<tr><td class="nm">{esc(TYPE[i])}</td><td>{esc(TYPED[i])}</td></tr>'
        for i in range(8))

    cap_rows = "\n".join(
        f'<tr><td>{CLASSN[c]}</td><td class="num">+{DMGCAP[c]}%</td>'
        f'<td class="num">−{RESCAP[c]}%</td>'
        f'<td class="num">{sum(1 for s in skills if s["c"] == c + 1)}</td></tr>'
        for c in range(3))

    exp_rows = "\n".join([
        f'<tr><td>一轉技能書</td><td class="num">{exp_total["B1"]:,.0f} 本</td>'
        f'<td class="num">{exp_total["B1"]*decomp[0]:,.0f} 張一階殘頁</td></tr>',
        f'<tr><td>二轉技能書</td><td class="num">{exp_total["B2"]:,.0f} 本</td>'
        f'<td class="num">{exp_total["B2"]*decomp[1]:,.0f} 張二階殘頁</td></tr>',
        f'<tr><td>三轉技能書</td><td class="num">{exp_total["B3"]:,.0f} 本</td>'
        f'<td class="num">{exp_total["B3"]*decomp[2]:,.0f} 張三階殘頁</td></tr>',
        f'<tr><td>四轉技能書</td><td class="num">{exp_total["B4"]:,.0f} 本</td>'
        f'<td class="num">{exp_total["B4"]*decomp[3]:,.0f} 張四階殘頁</td></tr>',
        f'<tr><td>專精靈髓</td><td class="num">{exp_total["SL"]:,.0f}</td>'
        f'<td class="num">—</td></tr>',
        f'<tr><td>悟道石</td><td class="num">{exp_total["WD"]:,.0f}</td>'
        f'<td class="num">—</td></tr>',
        f'<tr><td>Zeny</td><td class="num">{exp_zeny/100000000:,.0f} 億</td>'
        f'<td class="num">—</td></tr>',
    ])

    try_rows = "\n".join(
        f'<tr><td class="num">Lv.{b}</td><td class="num">{exp_tries[b]:.1f} 次</td>'
        f'<td class="num">{exp_tries[b]*brate/10000:.2f}</td></tr>' for b in breaks)

    book_rows = "\n".join(
        f'<tr><td class="nm">{esc(b["name"])}</td><td class="num">{b["tier"]} 轉</td>'
        f'<td class="num">{num(b["qty"])} 本</td>'
        f'<td class="num">{zh_zeny(b["zeny"])}</td>'
        f'<td class="num">{b["out"]}</td>'
        f'<td class="num">{num(b["same"])} 本</td></tr>' for b in book_rec)

    decomp_rows = "\n".join(
        f'<tr><td class="num">{i+1} 轉</td><td class="num">{decomp[i]} 張</td>'
        f'<td class="num">{decomp[i]*decomp_other//100} 張</td></tr>' for i in range(4))

    line_rows = "\n".join(
        f'<tr><td class="nm">{esc(LINE[i])}</td>'
        f'<td class="num">{sum(1 for s in skills if s["l"] == i + 1)}</td></tr>'
        for i in range(LINEN))

    # ======================================================================
    #  HTML
    # ======================================================================
    style = re.search(r"<style>.*?</style>", read(STYLE_FROM), re.S)
    chk(bool(style), "potential.html 裡找不到 <style> 區塊")
    style = style.group(0)

    extra_css = """
<style>
.nm{font-weight:700}
h3.sub{font-family:"Noto Serif TC",serif; font-size:16px; margin:24px 0 0}
.steps{list-style:none; margin:0; padding:0; display:grid; gap:14px;
       grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.steps li{border:1px solid var(--rule); border-radius:10px; padding:14px 16px}
.steps b{display:block; font-family:"Noto Serif TC",serif; font-size:17px; margin-bottom:6px}
.steps i{font-style:normal; color:var(--cinnabar); font-weight:700; margin-right:.45em}
.steps p{margin:0; font-size:14px; color:var(--ink-soft); line-height:1.75}
.bn{display:inline-block; padding:1px 7px; border-radius:6px; font-size:.82em;
    white-space:nowrap; font-weight:700; background:#c6503022; color:#c65030}
.callout{border-left:3px solid var(--cinnabar); padding:2px 0 2px 14px; margin:18px 0 0;
         color:var(--ink-soft); font-size:14.5px; line-height:1.85; max-width:72ch}
.callout b{color:var(--ink)}
.two{display:grid; gap:24px; grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.two .note{max-width:none}
.filters{display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:0 0 12px}
.filters select,.filters input{font:inherit; padding:6px 10px; border:1px solid var(--rule);
  border-radius:8px; background:transparent; color:inherit}
.filters .cnt{color:var(--ink-soft); font-size:14px}
.c1{color:#c65030}.c2{color:#3a8f5a}.c3{color:#7a5cc6}
</style>
"""

    doc = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>技能專精玩法</title>
<meta name="description" content="神域仙境 技能專精：重複的技能書變成養成材料，單一技能 Lv.1~20，四個突破點、八種專精類型、五個啟用槽與每一級的效果。">
<meta name="color-scheme" content="light dark">
<meta property="og:type" content="website">
<meta property="og:site_name" content="神域仙境">
<meta property="og:title" content="技能專精玩法">
<meta property="og:description" content="重複的技能書不再是垃圾 —— 拆成殘頁，把一支技能練到 Lv.20。">
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
    <h1>技能專精玩法</h1>
    <p class="lede">練滿之後多出來的技能書<b>不再是垃圾</b> —— 拆成殘頁，投進你最常用的那一支技能，把它從 Lv.1 推到 <b>Lv.__MAXLV__</b>。代價是 <b>__BREAKN__ 個突破點</b>，每一個的成功率都只有 <b>__BRATE__%</b>，失敗還會掉級。</p>
  </header>

  <section>
    <h2>三句話</h2>
    <ol class="steps">
      <li><b><i>一</i>解鎖</b><p>境界到 <b>__REALM__</b>，帶 <b>__OPENZENY__ Zeny</b> 與 <b>__OPENBOOK__ 本</b>技能書，找崑崙的<b>萬法宗師・玄策</b>（__NPCPOS__）。</p></li>
      <li><b><i>二</i>投材料</b><p>技能書可以<b>直接投</b>，也可以<b>拆成殘頁</b>。同職系算 __FEEDLINE__ 本，<b>同一支技能的書算 __FEEDSKILL__ 本</b>，別的職系只能拆。</p></li>
      <li><b><i>三</i>裝上去</b><p>練好的專精要<b>放進啟用槽</b>才有效果。共 __SLOTT__ 格：一般 __SLOTN__、核心 __SLOTC__、極意 __SLOTU__。</p></li>
    </ol>
  </section>

  <section>
    <h2>解鎖</h2>
    <div class="tbl-wrap">
      <table><tbody>
        <tr><th>境界</th><td>突破到第 __NEEDREALM__ 境【__REALM__】__JOB4__</td></tr>
        <tr><th>費用</th><td>__OPENZENY__ Zeny + 任意技能書 __OPENBOOK__ 本</td></tr>
        <tr><th>在哪裡</th><td>崑崙 <b>萬法宗師・玄策</b>（__NPCPOS__）</td></tr>
        <tr><th>綁定</th><td><b>專精進度綁角色</b>；殘頁與靈髓是<b>帳號共用</b>的存量，不佔背包、不能交易</td></tr>
      </tbody></table>
    </div>
  </section>

  <section>
    <h2>材料怎麼來</h2>
    <h3 class="sub">技能書拆成殘頁</h3>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>技能書</th><th class="num">同職系拆出</th><th class="num">別的職系拆出</th></tr></thead>
        <tbody>__DECOMPROWS__</tbody>
      </table>
    </div>
    <p class="note">殘頁反過來<b>每 N 張抵 1 本</b>，N 就是上表同職系那一欄 —— 所以拆或不拆的價值一樣，拆只是為了「先囤著」。別的職系的書<b>只能拆</b>，而且只有 __DECOMPOTHER__%。<b>同一支技能的書直接投進去算 __FEEDSKILL__ 本</b>，這個倍率只在直接投入時有，拆殘頁不會跟著變 __FEEDSKILL__ 倍。</p>

    <h3 class="sub">專精靈髓</h3>
    <p class="note">靈髓是第二種主材料，向<b>專精換取使</b>換。換取共有 <b>__EXN__ 個配方</b>（技能書、殘頁、幻影碎片、各境材料、副本材料），下面四個是直接用技能書換的：</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>配方</th><th class="num">技能書</th><th class="num">數量</th><th class="num">Zeny</th><th class="num">產出靈髓</th><th class="num">整批同一本書</th></tr></thead>
        <tbody>__BOOKROWS__</tbody>
      </table>
    </div>
    <p class="note">最後一欄是<b>同名優惠</b>：整批都交同一本技能書時，需求量降到那個數字，Zeny 不變。</p>

    <h3 class="sub">其他材料</h3>
    <p class="note"><b>悟道石</b>（Lv.__BK10LV__ 突破起要用）、<b>萬法核心</b>（Lv.__BK15LV__）、<b>極意天書</b>（Lv.__BK20LV__）、<b>輪迴石</b>（重置與換路線）。核心與天書是 Boss 掉落與活動產出的實體道具。</p>
  </section>

  <section>
    <h2>每一級要多少</h2>
    <p class="note">下表是<b>升到該級</b>所需的量。技能書那四欄的單位是<b>同職系同轉技能書的本數</b> —— 用殘頁付也可以，一階 __DECOMP1__ 張抵 1 本、二階 __DECOMP2__ 張、三階 __DECOMP3__ 張、四階 __DECOMP4__ 張。突破那四級的材料要<b>另外再加</b>，見下一節。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th class="num">等級</th><th>階段</th><th class="num">一轉書</th><th class="num">二轉書</th><th class="num">三轉書</th><th class="num">四轉書</th><th class="num">靈髓</th><th class="num">悟道石</th><th class="num">Zeny</th></tr></thead>
        <tbody>__COSTROWS__</tbody>
      </table>
    </div>
    <h3 class="sub">四個階段的小計</h3>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>階段</th><th class="num">一轉書</th><th class="num">二轉書</th><th class="num">三轉書</th><th class="num">四轉書</th><th class="num">靈髓</th><th class="num">悟道石</th><th class="num">Zeny(百萬)</th></tr></thead>
        <tbody>__STAGEROWS__</tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>突破：__BRATE__% 而且會掉級</h2>
    <div class="tbl-wrap">
      <table><tbody>
        <tr><th>突破點</th><td>Lv.__BREAKLIST__</td></tr>
        <tr><th>成功率</th><td><b>__BRATE__%</b>，固定值 —— 不吃 LUK、掉落率、VIP、稱號、星盤或任何加成，商城也不賣提高成功率的東西</td></tr>
        <tr><th>失敗</th><td>掉到<b>該突破點的兩級以下</b>（例：衝 Lv.20 失敗 → Lv.18），材料不返還</td></tr>
        <tr><th>額外材料</th><td>Lv.5 靈髓 __BKSOUL5__；Lv.10 悟道石 __BKWD10__ + 同職系二轉書 __BKB210__；Lv.15 萬法核心 __BKCORE15__ + 同職系三轉書 __BKB315__；Lv.20 極意天書 __BKTOME20__ + 同職系四轉書 __BKB420__</td></tr>
      </tbody></table>
    </div>
    <h3 class="sub">每個突破點平均要試幾次</h3>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th class="num">突破點</th><th class="num">平均嘗試</th><th class="num">其中成功</th></tr></thead>
        <tbody>__TRYROWS__</tbody>
      </table>
    </div>
    <p class="note">「平均嘗試」把<b>失敗掉級後重新爬回來</b>算進去了，所以不是單純的 1 ÷ __BRATE__%。</p>
  </section>

  <section>
    <h2>練滿一支要多少（期望值）</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>材料</th><th class="num">期望總量</th><th class="num">換算成殘頁</th></tr></thead>
        <tbody>__EXPROWS__</tbody>
      </table>
    </div>
    <div class="callout">
      這是<b>期望值</b>不是保底 —— 運氣好會少很多，運氣差會多很多。數字大的原因只有一個：<b>四個突破點各只有 __BRATE__%，失敗還會掉級</b>，掉下去的那幾級要重新付一次。<br>
      所以這是<b>長期目標</b>，不是這週練得完的東西。先挑一支你確定會一直用的技能。
    </div>
  </section>

  <section>
    <h2>每一級給什麼</h2>
    <p class="note">主效果依<b>專精類型</b>而不同：輔助型加的是該技能的<b>治療量</b>，防禦型加的是<b>受到技能傷害的減免</b>，其餘六型加的是<b>該技能傷害</b>。資源補正是 SP 消耗、詠唱與後延遲的降幅。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th class="num">等級</th><th class="num">主權重</th><th class="num">一般</th><th class="num">核心</th><th class="num">終極</th><th class="num">資源權重</th><th class="num">一般</th><th class="num">核心</th><th class="num">終極</th></tr></thead>
        <tbody>__EFFROWS__</tbody>
      </table>
    </div>
    <p class="note">「一般／核心／終極」是<b>技能自己的級別</b>，由教它的技能書轉數決定，不是專精等級。三種級別的上限不同但曲線相同 —— 所以每一種都在 Lv.__MAXLV__ 剛好打滿自己的上限。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>技能級別</th><th class="num">主效果上限</th><th class="num">資源補正上限</th><th class="num">白名單技能數</th></tr></thead>
        <tbody>__CAPROWS__</tbody>
      </table>
    </div>
    <p class="note">PVP 場景的主效果再乘 __DMGPVP__%。</p>
  </section>

  <section>
    <h2>八種專精類型</h2>
    <p class="note">每一支技能的類型是<b>固定的</b>，由系統指定，不能選。類型決定主效果加在哪裡，也決定代價。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>類型</th><th>給什麼／代價</th></tr></thead>
        <tbody>__TYPEROWS__</tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>Lv.10 路線與 Lv.20 極意</h2>
    <div class="two">
      <div>
        <h3 class="sub" style="margin-top:0">Lv.10：__BR1__ 或 __BR2__</h3>
        <p class="note"><b>__BR1__</b>：__BRD1__<br><b>__BR2__</b>：__BRD2__</p>
        <p class="note">選錯可以換：輪迴石 __SWLUN__ + 同職系技能書 __SWBOOK__ 本，同一支技能 __SWCD__ 小時內只能換一次。</p>
      </div>
      <div>
        <h3 class="sub" style="margin-top:0">Lv.20：__UL1__ 或 __UL2__</h3>
        <p class="note"><b>__UL1__</b>：__ULD1__<br><b>__UL2__</b>：__ULD2__</p>
        <p class="note">兩者都是「拿更多數值換更多代價」，沒有純好處的選項。</p>
      </div>
    </div>
  </section>

  <section>
    <h2>啟用槽</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>槽</th><th class="num">格數</th><th>放得進去的專精</th></tr></thead>
        <tbody>
          <tr><td>一般</td><td class="num">__SLOTN__</td><td>Lv.1 以上</td></tr>
          <tr><td>核心</td><td class="num">__SLOTC__</td><td>Lv.__SLOTCLV__ 以上</td></tr>
          <tr><td>極意</td><td class="num">__SLOTU__</td><td>Lv.__SLOTULV__</td></tr>
        </tbody>
      </table>
    </div>
    <p class="note">共 __SLOTT__ 格。<b>只有放進槽裡的專精才有效果</b>，練好但沒裝等於沒有。換槽要在城鎮，換完有 __SLOTCD__ 秒冷卻。</p>
  </section>

  <section>
    <h2>可以專精的技能</h2>
    <p class="note">白名單就是<b>技能書教得到的技能</b>，共 <b>__SKN__ 支</b>，再扣掉傳送、商店、製作與純系統那幾類。輸入關鍵字或切換下拉選單來找。</p>
    <div class="filters">
      <select id="fty"><option value="">全部類型</option>__TYOPTS__</select>
      <select id="fcl"><option value="">全部級別</option>__CLOPTS__</select>
      <select id="fln"><option value="">全部職系</option>__LNOPTS__</select>
      <input id="fkw" type="search" placeholder="技能名稱／編號" size="16">
      <span class="cnt" id="cnt"></span>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>技能</th><th class="num">編號</th><th>專精類型</th><th>級別</th><th>職系</th><th class="num">技能書</th></tr></thead>
        <tbody id="skrows"></tbody>
      </table>
    </div>
    <h3 class="sub">各職系有幾支</h3>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>職系</th><th class="num">技能數</th></tr></thead>
        <tbody>__LINEROWS__</tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>技能書重煉</h2>
    <p class="note">用不到的書可以換成同職系的其他書。<b>不能指定要換出哪一支</b>。</p>
    <div class="tbl-wrap">
      <table><tbody>
        <tr><th>同轉換一本</th><td>同轉技能書 __RF1N__ 本 + Zeny __RF1Z__ → 隨機同職系同轉技能書 1 本</td></tr>
        <tr><th>可選職系</th><td>同轉同職系 __RF2N__ 本 + 靈髓 __RF2S__ → 自選職系、隨機技能書 1 本</td></tr>
        <tr><th>升轉材料箱</th><td>一轉 __RFBOX1__ 本 → 二轉箱；二轉 __RFBOX2__ 本 → 三轉箱；三轉 __RFBOX3__ 本 → 四轉箱</td></tr>
      </tbody></table>
    </div>
  </section>

  <section>
    <h2>重置與換路線</h2>
    <div class="tbl-wrap">
      <table><tbody>
        <tr><th>單一技能重置</th><td>輪迴石 __RSLUN__ + Zeny __RSZENY__。返還已成功消耗的技能書／殘頁 <b>__RSBACK__%</b>、突破材料 <b>__RSBKBACK__%</b>，<b>Zeny 不返還</b></td></tr>
        <tr><th>換 Lv.10 路線</th><td>輪迴石 __SWLUN__ + 同職系技能書 __SWBOOK__ 本，同一支技能 __SWCD__ 小時冷卻</td></tr>
      </tbody></table>
    </div>
    <p class="note">返還是照「<b>實際交出去的量</b>」算，不是照等級表反推 —— 所以用同名書省下來的部分不會在重置時變成利潤。</p>
  </section>

  <footer class="foot">
    <a class="home" href="index.html">← 回 神域仙境 玩家工具</a>
    <p>資料由 <code>tools/build_spz.py</code> 從伺服器腳本解析產生。</p>
  </footer>
</div>

<script>
const SK = __SKJSON__;
const TY = __TYJSON__, CL = __CLJSON__, LN = __LNJSON__;
const rows = document.getElementById("skrows");
const cnt  = document.getElementById("cnt");
const fty = document.getElementById("fty"), fcl = document.getElementById("fcl");
const fln = document.getElementById("fln"), fkw = document.getElementById("fkw");
function render(){
  const t = fty.value, c = fcl.value, l = fln.value;
  const k = fkw.value.trim().toLowerCase();
  const out = [];
  let n = 0;
  for (const s of SK){
    if (t && String(s.t) !== t) continue;
    if (c && String(s.c) !== c) continue;
    if (l && String(s.l) !== l) continue;
    if (k && !(s.n.toLowerCase().includes(k) || String(s.id).includes(k))) continue;
    n++;
    out.push('<tr><td class="nm">' + s.n + '</td><td class="num">' + s.id +
             '</td><td>' + TY[s.t-1] + '</td><td class="c' + s.c + '">' + CL[s.c-1] +
             '</td><td>' + LN[s.l-1] + '</td><td class="num">' + s.b + '</td></tr>');
  }
  rows.innerHTML = out.join("");
  cnt.textContent = n + " / " + SK.length + " 支";
}
for (const el of [fty, fcl, fln]) el.addEventListener("change", render);
fkw.addEventListener("input", render);
render();
</script>
</body>
</html>
"""

    rep = {
        "__STYLE__": style,
        "__EXTRA__": extra_css,
        "__MAXLV__": str(MAXLV),
        "__BREAKN__": str(len(breaks)),
        "__BRATE__": f"{brate/100:g}",
        "__BREAKLIST__": " / Lv.".join(str(b) for b in breaks),
        "__REALM__": esc(realm_name),
        "__NEEDREALM__": str(need_realm),
        "__JOB4__": "（不需要四轉）" if not need_job4 else "，而且要完成四轉",
        "__OPENZENY__": zh_zeny(open_zeny),
        "__OPENBOOK__": str(open_book),
        "__NPCPOS__": "gonryun 173,131",
        "__DECOMPROWS__": decomp_rows,
        "__DECOMPOTHER__": str(decomp_other),
        "__DECOMP1__": str(decomp[0]), "__DECOMP2__": str(decomp[1]),
        "__DECOMP3__": str(decomp[2]), "__DECOMP4__": str(decomp[3]),
        "__FEEDLINE__": str(feed_line),
        "__FEEDSKILL__": str(feed_skill),
        "__EXN__": str(ex_n),
        "__BOOKROWS__": book_rows,
        "__BK10LV__": str(breaks[1]),
        "__BK15LV__": str(breaks[2]),
        "__BK20LV__": str(breaks[3]),
        "__COSTROWS__": cost_rows,
        "__STAGEROWS__": stage_rows,
        "__BKSOUL5__": str(conf_s["$@SPZ_BK_SOUL5"]),
        "__BKWD10__": str(conf_s["$@SPZ_BK_WD10"]),
        "__BKB210__": str(conf_s["$@SPZ_BK_B2_10"]),
        "__BKCORE15__": str(conf_s["$@SPZ_BK_CORE15"]),
        "__BKB315__": str(conf_s["$@SPZ_BK_B3_15"]),
        "__BKTOME20__": str(conf_s["$@SPZ_BK_TOME20"]),
        "__BKB420__": str(conf_s["$@SPZ_BK_B4_20"]),
        "__TRYROWS__": try_rows,
        "__EXPROWS__": exp_rows,
        "__EFFROWS__": eff_rows,
        "__CAPROWS__": cap_rows,
        "__DMGPVP__": str(conf_s["$@SPZ_DMGCAP_PVP"]),
        "__TYPEROWS__": type_rows,
        "__BR1__": esc(BR[0]), "__BR2__": esc(BR[1]),
        "__BRD1__": esc(BRD[0]), "__BRD2__": esc(BRD[1]),
        "__UL1__": esc(UL[0]), "__UL2__": esc(UL[1]),
        "__ULD1__": esc(ULD[0]), "__ULD2__": esc(ULD[1]),
        "__SLOTN__": str(slot_n), "__SLOTC__": str(slot_c),
        "__SLOTU__": str(slot_u), "__SLOTT__": str(slot_t),
        "__SLOTCLV__": str(slot_clv), "__SLOTULV__": str(slot_ulv),
        "__SLOTCD__": str(slot_cd),
        "__SKN__": str(len(skills)),
        "__TYOPTS__": "".join(f'<option value="{i+1}">{esc(TYPE[i])}</option>'
                              for i in range(8)),
        "__CLOPTS__": "".join(f'<option value="{i+1}">{CLASSN[i]}</option>'
                              for i in range(3)),
        "__LNOPTS__": "".join(f'<option value="{i+1}">{esc(LINE[i])}</option>'
                              for i in range(LINEN)),
        "__LINEROWS__": line_rows,
        "__RF1N__": str(rf1_n), "__RF1Z__": zh_zeny(rf1_z),
        "__RF2N__": str(rf2_n), "__RF2S__": str(rf2_s),
        "__RFBOX1__": str(rf_box[0]), "__RFBOX2__": str(rf_box[1]),
        "__RFBOX3__": str(rf_box[2]),
        "__RSLUN__": str(rs_lun), "__RSZENY__": zh_zeny(rs_zeny),
        "__RSBACK__": str(rs_back), "__RSBKBACK__": str(rs_bkback),
        "__SWLUN__": str(sw_lun), "__SWBOOK__": str(sw_book),
        "__SWCD__": str(sw_cd // 3600),
        "__SKJSON__": json.dumps(skills, ensure_ascii=False, separators=(",", ":")),
        "__TYJSON__": json.dumps(TYPE, ensure_ascii=False),
        "__CLJSON__": json.dumps(CLASSN, ensure_ascii=False),
        "__LNJSON__": json.dumps(LINE, ensure_ascii=False),
    }
    for k, v in rep.items():
        doc = doc.replace(k, v)

    left = re.findall(r"__[A-Z0-9]+__", doc)
    chk(not left, "還有沒被取代的佔位符: " + ", ".join(sorted(set(left))))

    with io.open(DEST, "w", encoding="utf-8", newline="\n") as f:
        f.write(doc)

    # ======================================================================
    #  產生之後: 把頁面解析回來跟來源對
    # ======================================================================
    back = read(DEST)
    m = re.search(r"const SK = (\[.*?\]);", back, re.S)
    chk(bool(m), "寫出來的頁面裡找不到 SK 資料")
    got = json.loads(m.group(1))
    chk(len(got) == len(skills), f"頁面的技能數 {len(got)} != 解析出的 {len(skills)}")
    for a, b in zip(got, skills):
        chk(a["id"] == b["id"] and a["n"] == b["n"] and a["t"] == b["t"]
            and a["c"] == b["c"] and a["l"] == b["l"] and a["b"] == b["b"],
            f"技能 {b['id']} 寫進頁面之後對不上")
    for lv in (1, MAXLV):
        chk(f"Lv.{lv}" in back, f"頁面沒有 Lv.{lv} 那一列")
    chk(back.count('<td class="num">') > 200, "表格看起來太空")
    chk(str(len(skills)) in back, "頁面沒有寫出技能總數")
    for t in TYPE:
        chk(t in back, f"頁面沒有專精類型「{t}」")

    print(f"spz.html 產生完成: {len(back):,} bytes")
    print(f"  白名單 {len(skills)} 支技能 / 職系 {LINEN} / 類型 8 / 等級 1~{MAXLV}")
    print(f"  期望練滿一支: 一轉書 {exp_book1:,.0f} 本、Zeny {exp_zeny/100000000:,.1f} 億、"
          f"靈髓 {exp_total['SL']:,.0f}、悟道石 {exp_total['WD']:,.0f}")
    print("  突破平均嘗試: " + " / ".join(f"Lv.{b} {exp_tries[b]:.1f} 次" for b in breaks))
    print("  各級別技能數: " + " / ".join(
        f"{CLASSN[c]} {sum(1 for s in skills if s['c'] == c+1)}" for c in range(3)))


if __name__ == "__main__":
    main()

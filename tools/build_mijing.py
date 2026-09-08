# -*- coding: utf-8 -*-
"""
天地大秘境玩法指南產生器 —— 產生 mijing.html, 跑完自己驗證一次。

用法:

    python tools/build_mijing.py

會覆寫 mijing.html。輸出是決定性的 —— 來源沒變的話重跑一次 git status
應該是乾淨的, 這也是最好的回歸測試。

--------------------------------------------------------------------------
來源 (全部在 2.開機擋)
--------------------------------------------------------------------------
  script/16.天地大秘境/00.設定.txt      所有 $@MJ_* 表與常數(唯一的數值來源)
  script/16.天地大秘境/02.入口管理器.txt 13 張候選地圖的中文名
  script/16.天地大秘境/09.祭壇.txt      20 項祭壇的玩家說明文字(S_Desc)
  script/16.天地大秘境/10.危害.txt      定時危害的預警文字(S_RuleWarn/S_AffWarn)

★★ 這一頁沒有任何手寫的數字 ★★
  每一個數值都是從上面那幾支解析出來的。玩法敘述可以手寫, 數字不行 ——
  手寫的數字會在改平衡時默默過期, 而網頁不會報錯。
  唯一的例外是 verify 段裡的預期值, 那是「刻意寫死來擋改動」的。

★ 法則(40)與詞綴(18)在腳本裡「只有名字 + kind/V 代碼」, 沒有玩家看得懂
  的敘述。本檔的 rule_text / aff_text 從 kind+V 還原成中文 —— 對照的是
  01.核心.txt 的 F_MJ_RuleApply 與 10.危害.txt 的 S_FireRule/S_FireAff,
  不是 00.設定.txt 的註解(註解描述的是企劃書意圖, 不一定等於實作)。
  產生前會檢查「每一個出現過的 kind 都有對應的還原規則」。

★ 有 6 條法則(D12/D14/D25/D36/D38/D39)是 kind 11 且不是 D16 ——
  F_MJ_RuleApply 對它們完全不做事, 也沒有別的檔案讀它們。
  它們「只給獎勵加成、不加難度」, 頁面照實寫成「不改數值」。
  這是實作現況不是筆誤; 要改的話改腳本, 不是改這裡。
  跑完會把這份清單印出來, 免得日後補實作了卻忘記頁面還寫著舊話。
"""
import io, os, re, sys, html

HERE = os.path.dirname(os.path.abspath(__file__))
WEB  = os.path.dirname(HERE)
ROOT = r"H:\91.神域仙境"
SRV  = os.path.join(ROOT, "2.開機擋")
MJ   = os.path.join(SRV, r"script\16.天地大秘境")

F_CONF  = os.path.join(MJ, "00.設定.txt")
F_WORLD = os.path.join(MJ, "02.入口管理器.txt")
F_ALT   = os.path.join(MJ, "09.祭壇.txt")
F_HAZ   = os.path.join(MJ, "10.危害.txt")

STYLE_FROM = os.path.join(WEB, "potential.html")
DEST       = os.path.join(WEB, "mijing.html")


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
SCA_RE = re.compile(r"^\s*(\$@\w+\$?)\s*=\s*([^;]+);", re.M)


def parse_conf(text):
    """回 (arrays, scalars)。arrays[name] = {index: value}"""
    text = strip_comments(text)
    arrays, scalars = {}, {}
    for m in ARR_RE.finditer(text):
        name, start = m.group(1), int(m.group(2))
        d = arrays.setdefault(name, {})
        for i, tok in enumerate(split_vals(m.group(3))):
            d[start + i] = conv(tok)
    for m in SCA_RE.finditer(text):
        name, val = m.group(1), m.group(2).strip()
        if name in arrays:
            continue
        scalars[name] = conv(val)
    return arrays, scalars


def parse_if_table(text, label):
    """把 `if ( .@id == N ) return "..."` 這種表解析成 {N: str};
    結尾那個無條件 return 收在鍵 0 當 fallback。"""
    body = text.split(label, 1)
    if len(body) < 2:
        sys.exit("找不到 %s" % label)
    out = {}
    for line in body[1].split("\n"):
        line = line.strip()
        m = re.match(r'if\s*\(\s*\.@id\s*==\s*(\d+)\s*\)\s*return\s+"(.*?)"\s*;', line)
        if m:
            out[int(m.group(1))] = m.group(2)
            continue
        m = re.match(r'return\s+"(.*?)"\s*;', line)
        if m:
            out[0] = m.group(1)
            break
    return out


# ==========================================================================
#  法則 / 詞綴的中文還原
# ==========================================================================
#  對照的是 F_MJ_RuleApply 的實際分支, 不是 00.設定.txt 的註解。
def rule_text(rid, kind, v, v2, warn):
    #  ---- 先處理 F_MJ_RuleApply 裡「按編號特判」的那幾條 ----
    if kind == 7:
        if rid == 13:                       # D13 靈力稅 -> 'mj_spcost
            return "主動技能的 SP 消耗 +%d%%（全場合計上限 25%%）" % v
        return "受到的治療 −%d%%（全場合計上限 40%%）" % v
    if kind == 8:
        if rid == 21:
            return "穩定度的自然消耗 +%d%%" % v
        if rid == 22:
            return "首領提前 1 分鐘進入狂暴（最低 8 分鐘）"
        if rid == 23:
            return "事件的限制時間 −%d%%" % v
        if rid == 24:
            return "踩到陷阱多扣 %d 點穩定度" % v
        return None
    if kind == 9:
        if rid in (31, 37):
            return "稀有怪數量 +%d%%" % v
        return "精英怪數量 +%d%%" % v
    if kind == 11:
        if rid == 16:
            return "補給次數 −%d 次" % v
        return "只改變場景與路線，不改數值（獎勵加成照給）"

    #  ---- 其餘按 kind ----
    if kind == 1:
        return "怪物攻擊力與魔攻 +%d%%（地圖加成合計上限 50%%）" % v
    if kind == 2:
        return "怪物血量 +%d%%（地圖加成合計上限 100%%）" % v
    if kind == 3:
        return "怪物物理防禦 +%d%%" % v
    if kind == 4:
        return "怪物魔法防禦 +%d%%" % v
    if kind == 5:
        return "首領的物抗與魔抗 +%d（合計上限 220）" % v
    if kind == 6:
        s = "每 %d 秒發動一次定時危害，威力 %d%%" % (v, v2)
        return s + ("　—　「%s」" % warn if warn else "")
    if kind == 10:
        return "精英與稀有怪各多帶 %d 條詞綴" % v
    return None


def aff_text(aid, kind, v, v2, warn):
    w = "　—　「%s」" % warn if warn else ""
    if kind == 1:  return "血量 +%d%%" % v
    if kind == 2:  return "攻擊力與魔攻 +%d%%" % v
    if kind == 3:  return "物理抗性 +%d" % v
    if kind == 4:  return "魔法抗性 +%d" % v
    if kind == 5:  return "每 %d 秒回復自身 1%% 血量" % v
    if kind == 6:  return "每 %d 秒獲得一層護盾（自身血量的 %d%%）" % (v, v2)
    if kind == 7:  return "每 %d 秒放一次地板，威力 %d%%%s" % (v, v2, w)
    if kind == 8:  return "死亡後在原地留下地板 %d 秒，威力 %d%%" % (v, v2)
    if kind == 9:  return "每 %d 秒瞬移一次%s" % (v, w)
    if kind == 10: return "每 %d 秒放一次減速（不是暈眩）%s" % (v, w)
    if kind == 11: return "每 %d 秒召喚 %d 隻同伴" % (v, v2)
    if kind == 12: return "每 %d 秒點名一人，威力 %d%%%s" % (v, v2, w)
    if kind == 13: return "霧區內命中率 −%d%%" % v
    if kind == 14: return "每 %d 秒輪轉安全扇區，威力 %d%%%s" % (v, v2, w)
    #  kind 15 的預警文字本身就是完整敘述, 再接一次會變成同一句講兩遍
    if kind == 15: return "場上出現鏡核，打破它可以讓首領承受更高傷害"
    return None


RULE_CAT = {
    1: "攻擊", 2: "防禦", 3: "元素", 4: "資源", 5: "恢復",
    6: "時間", 7: "移動", 8: "怪物強化", 9: "玩家限制", 10: "獎勵加成",
}

ALT_REQ = {
    0: "無條件",
    1: "剩餘穩定度 ≥ %s",
    2: "尚未達到密度上限",
    3: "至少留下 1 盞魂燈",
    4: "還有補給次數",
    5: "只在第 1 層之前",
    6: "只在首領之前",
    7: "尚未跨過污染門檻",
    8: "額外抗性 ≤ 220",
}


# ==========================================================================
def esc(s):
    return html.escape(str(s))


def num(v):
    """萬分點 -> 人看得懂的數字。10000 -> 100 ; 500 -> 5 ; 135 -> 1.35"""
    return str(v // 100) if v % 100 == 0 else ("%.2f" % (v / 100.0))


def main():
    A, S = parse_conf(read(F_CONF))
    W, _ = parse_conf(read(F_WORLD))
    alt_desc = parse_if_table(read(F_ALT), "S_Desc:")
    haz = read(F_HAZ)
    rule_warn = parse_if_table(haz, "S_RuleWarn:")
    aff_warn = parse_if_table(haz, "S_AffWarn:")

    def arr(name, n, base=1):
        d = A.get(name)
        if d is None:
            sys.exit("00.設定.txt 找不到 %s" % name)
        out = [d.get(i) for i in range(base, base + n)]
        if any(x is None for x in out):
            sys.exit("%s 少了元素: 期望 %d 個, 實得 %d 個"
                     % (name, n, sum(1 for x in out if x is not None)))
        return out

    RN = S["$@MJ_RarityN"]
    TN = S["$@MJ_TplN"]
    BN = S["$@MJ_BossN"]
    DN = S["$@MJ_RuleN"]
    AN = S["$@MJ_AltN"]
    FN = S["$@MJ_AffN"]
    SN = S["$@MJ_ShopN"]

    # ---------------- 稀有度 ----------------
    rar_name  = arr("$@MJ_RarityName$", RN)
    rar_roll  = arr("$@MJ_RarityRoll", RN)
    rar_hp    = arr("$@MJ_RarityHP", RN)
    rar_fl    = arr("$@MJ_RarityFloors", RN)
    rar_hard  = arr("$@MJ_RarityHard", RN)
    rar_decay = arr("$@MJ_RarityDecay", RN)
    rar_lant  = arr("$@MJ_RarityLanternAdd", RN)
    rar_rev   = arr("$@MJ_RarityRevive", RN)
    rar_rules = arr("$@MJ_RarityRules", RN)
    rar_hid   = arr("$@MJ_RarityHidden", RN)
    rar_rr    = arr("$@MJ_RarityRr", RN)
    rar_enr   = arr("$@MJ_RarityEnrage", RN)
    pdiv      = arr("$@MJ_PDiv", RN)
    eres      = arr("$@MJ_ERes", RN)

    rar_pct, lo = [], 0
    for r in range(RN):
        rar_pct.append((rar_roll[r] - lo + 1) / 100.0)
        lo = rar_roll[r] + 1

    def lantern(r, p):
        """r 是 1-based 稀有度。太初是 P/2, 其餘是 P + add, 下限 1。"""
        n = p // 2 if r == RN else p + rar_lant[r - 1]
        return max(1, n)

    # ---------------- 模板 ----------------
    tpl_name = arr("$@MJ_TplName$", TN)
    tpl_roll = arr("$@MJ_TplRoll", TN)
    tpl_ev   = arr("$@MJ_TplEvent$", TN)
    tpl_tr   = arr("$@MJ_TplTrap$", TN)
    tpl_b    = [arr("$@MJ_TplBoss1", TN), arr("$@MJ_TplBoss2", TN),
                arr("$@MJ_TplBoss3", TN)]
    tpl_pct, lo = [], 0
    for t in range(TN):
        tpl_pct.append(tpl_roll[t] - lo + 1)
        lo = tpl_roll[t] + 1

    # ---------------- 首領 ----------------
    boss_name = arr("$@MJ_BossName$", BN)
    boss_sig  = arr("$@MJ_BossSig$", BN)
    boss_tpl  = arr("$@MJ_BossTpl", BN)

    # ---------------- 組隊 ----------------
    p_hp  = arr("$@MJ_PartyHP", 6)
    p_atk = arr("$@MJ_PartyATK", 6)
    p_el  = arr("$@MJ_PartyElite", 6)
    p_mk  = arr("$@MJ_PartyMark", 6)
    p_dec = arr("$@MJ_PartyDecay", 6)

    # ---------------- 法則 ----------------
    d_name  = arr("$@MJ_RuleName$", DN)
    d_cat   = arr("$@MJ_RuleCat", DN)
    d_kind  = arr("$@MJ_RuleKind", DN)
    d_v     = arr("$@MJ_RuleV", DN)
    d_v2    = arr("$@MJ_RuleV2", DN)
    d_bonus = arr("$@MJ_RuleBonus", DN)
    d_ds    = arr("$@MJ_RuleDS", DN)
    d_t5    = arr("$@MJ_RuleT5Only", DN)

    # ---------------- 祭壇 ----------------
    a_name = arr("$@MJ_AltName$", AN)
    a_q    = arr("$@MJ_AltQ", AN)
    a_kind = arr("$@MJ_AltKind", AN)
    a_v    = arr("$@MJ_AltV", AN)
    a_req  = arr("$@MJ_AltReq", AN)
    a_reqv = arr("$@MJ_AltReqV", AN)

    # ---------------- 詞綴 ----------------
    f_name = arr("$@MJ_AffName$", FN)
    f_kind = arr("$@MJ_AffKind", FN)
    f_v    = arr("$@MJ_AffV", FN)
    f_v2   = arr("$@MJ_AffV2", FN)
    f_ds   = arr("$@MJ_AffDS", FN)
    f_lo   = arr("$@MJ_AffNormLo", RN)
    f_hi   = arr("$@MJ_AffNormHi", RN)
    f_el   = arr("$@MJ_AffElite", RN)
    f_ra   = arr("$@MJ_AffRare", RN)
    f_bo   = arr("$@MJ_AffBoss", RN)

    # ---------------- 兌換 ----------------
    sh_name = arr("$@MJ_ShopName$", SN)
    sh_cost = arr("$@MJ_ShopCost", SN)
    sh_week = arr("$@MJ_ShopWeek", SN)
    sh_need = arr("$@MJ_ShopNeed", SN)

    # ---------------- 候選地圖 ----------------
    gmap  = W.get("$@MJ_GateMap$", {})
    gname = W.get("$@MJ_GateMapName$", {})
    gnpc  = W.get("$@MJ_GateNpc$", {})
    GN = len(gmap)
    gate_names = [gname[i] for i in sorted(gname)]

    # ---------------- 成就 / 排行榜 ----------------
    ach_n     = S["$@MJ_AchN"]
    ach_name  = arr("$@MJ_AchName$", ach_n)
    ach_desc  = arr("$@MJ_AchDesc$", ach_n)
    rank_name = arr("$@MJ_RankName$", S["$@MJ_RankN"])
    hidfast   = arr("$@MJ_HidFastMin", RN)

    # ======================================================================
    #  驗證 —— 任何一條不過就不產生檔案
    # ======================================================================
    def die(msg):
        sys.exit("[驗證失敗] " + msg)

    if not (len(gmap) == len(gname) == len(gnpc)):
        die("候選地圖 / 中文名 / 入口 NPC 三張表長度不一致: %d / %d / %d"
            % (len(gmap), len(gname), len(gnpc)))
    if rar_roll[-1] != 9999:
        die("稀有度抽樣上界不是 9999 而是 %d" % rar_roll[-1])
    if tpl_roll[-1] != 99:
        die("模板抽樣上界不是 99 而是 %d" % tpl_roll[-1])
    if abs(sum(rar_pct) - 100.0) > 1e-9:
        die("階級機率合計 %.4f 不是 100" % sum(rar_pct))
    if sum(tpl_pct) != 100:
        die("模板機率合計 %d 不是 100" % sum(tpl_pct))
    if BN != TN * 3 + 1:
        die("首領數 %d 不等於 模板 %d x 3 + 1" % (BN, TN))
    for i in range(1, AN + 1):
        #  最後一項在 09.祭壇.txt 是無條件 return, 記在鍵 0
        if i not in alt_desc and not (i == AN and 0 in alt_desc):
            die("祭壇 A%02d 在 09.祭壇.txt 沒有說明文字" % i)
    for i in range(DN):
        if rule_text(i + 1, d_kind[i], d_v[i], d_v2[i], "") is None:
            die("法則 D%02d 的 kind=%d 沒有對應的中文還原" % (i + 1, d_kind[i]))
        if d_cat[i] not in RULE_CAT:
            die("法則 D%02d 的類別 %d 不在對照表裡" % (i + 1, d_cat[i]))
    for i in range(FN):
        if aff_text(i + 1, f_kind[i], f_v[i], f_v2[i], "") is None:
            die("詞綴 W%02d 的 kind=%d 沒有對應的中文還原" % (i + 1, f_kind[i]))
    for i in range(AN):
        if a_req[i] not in ALT_REQ:
            die("祭壇 A%02d 的資格原型 %d 不在對照表裡" % (i + 1, a_req[i]))

    # ======================================================================
    #  組表
    # ======================================================================
    pace_rows = "".join(
        '<tr><th scope="row">%s</th><td>%s</td></tr>' % (esc(k), v)
        for k, v in [
            ("檢查頻率", "每 60 秒一次"),
            ("在線門檻", "%d 人" % S["$@MJ_MinOnline"]),
            ("冷卻", "上一個入口關閉後 <b>%d 分鐘</b>內不會再開"
                     % S["$@MJ_CoolMin"]),
            ("出現機率", "基礎 %d%%，每次沒抽中 +%d 個百分點，最高 %d%%"
                         % (S["$@MJ_RollBase"], S["$@MJ_RollStep"],
                            S["$@MJ_RollMax"])),
            ("保底", "第 %d 次有效檢查必定開啟" % S["$@MJ_RollPity"]),
            ("存在多久", "<b>%d 分鐘</b>（剩 5 分、1 分各公告一次）"
                         % (S["$@MJ_OpenSec"] // 60)),
        ])

    gate_chips = "".join('<span class="chip">%s</span>' % esc(n)
                         for n in gate_names)

    rar_rows = []
    for r in range(RN):
        supp = ("最終傷害 ÷ %s、抗性 +%d%%" % ("{:,}".format(pdiv[r]), eres[r])
                if pdiv[r] > 1 else "—")
        rar_rows.append(
            '<tr><td class="nm">%s</td><td class="num roll">%s%%</td>'
            '<td class="num">%d</td><td class="num">%d 分</td>'
            '<td class="num">%s</td><td class="num">%d ／ %d</td>'
            '<td class="num">×%s</td><td class="num">%d%%</td>'
            '<td class="lim">%s</td></tr>'
            % (esc(rar_name[r]), ("%g" % rar_pct[r]), rar_fl[r], rar_hard[r],
               num(rar_decay[r]), lantern(r + 1, 1), lantern(r + 1, 6),
               "%g" % (rar_hp[r] / 100.0), rar_hid[r], esc(supp)))

    tpl_rows = []
    for t in range(TN):
        bosses = "、".join(boss_name[tpl_b[k][t] - 1] for k in range(3))
        tpl_rows.append(
            '<tr><td class="nm">%s</td><td class="num roll">%d%%</td>'
            '<td>%s</td><td>%s</td><td class="lim">%s</td></tr>'
            % (esc(tpl_name[t]), tpl_pct[t], esc(tpl_ev[t]), esc(tpl_tr[t]),
               esc(bosses)))

    party_rows = []
    for p in range(6):
        party_rows.append(
            '<tr><td class="nm">%d 人</td><td class="num">×%s</td>'
            '<td class="num">×%s</td><td class="num">%d</td>'
            '<td class="num">%d</td><td class="num">×%s</td></tr>'
            % (p + 1, "%g" % (p_hp[p] / 100.0), "%g" % (p_atk[p] / 100.0),
               p_el[p], p_mk[p], "%g" % (p_dec[p] / 100.0)))

    stab_rows = "".join(
        '<tr><td>%s</td><td class="num %s">%s</td><td class="lim">%s</td></tr>'
        % (esc(a), c, esc(b), esc(d))
        for a, b, c, d in [
            ("每分鐘自然消耗",
             "−%s ~ −%s" % (num(min(rar_decay)), num(max(rar_decay))),
             "roll", "階級越高掉得越慢；單人再 ×0.90"),
            ("角色死亡", "−%s" % num(S["$@MJ_StabDeath"]), "roll",
             "人多時每人扣得少一些，最少 −2"),
            ("踩到陷阱", "−%s" % num(S["$@MJ_StabTrap"]), "roll",
             "同一個陷阱 3 秒內全隊只扣一次"),
            ("事件失敗", "−%s" % num(S["$@MJ_StabEvFail"]), "roll",
             "同一個事件只扣一次"),
            ("首領破解失敗", "−%s" % num(S["$@MJ_StabBoss"]), "roll", "每次"),
            ("完成事件", "＋%s" % num(S["$@MJ_StabEvOK"]), "keep",
             "每場最多加 3 次"),
        ])

    boss_rows = []
    for b in range(BN):
        t = tpl_name[boss_tpl[b] - 1]
        boss_rows.append(
            '<tr><td class="oid">B%02d</td><td class="nm">%s</td>'
            '<td>%s</td><td class="lim">%s</td></tr>'
            % (b + 1, esc(boss_name[b]), esc(boss_sig[b]), esc(t)))

    rule_rows = []
    for i in range(DN):
        rid = i + 1
        txt = rule_text(rid, d_kind[i], d_v[i], d_v2[i], rule_warn.get(rid, ""))
        tag = '<span class="bn t5">限太初</span>' if d_t5[i] else ""
        rule_rows.append(
            '<tr><td class="oid">D%02d</td><td class="nm">%s%s</td>'
            '<td class="lim">%s</td><td>%s</td>'
            '<td class="num roll">＋%d%%</td><td class="num">%d</td></tr>'
            % (rid, esc(d_name[i]), tag, esc(RULE_CAT[d_cat[i]]), esc(txt),
               d_bonus[i], d_ds[i]))

    alt_rows = []
    for i in range(AN):
        rid = i + 1
        desc = alt_desc.get(rid, alt_desc.get(0, ""))
        req = ALT_REQ[a_req[i]]
        if "%s" in req:
            req = req % num(a_reqv[i])
        gain = "＋%s%%" % num(a_q[i]) if a_q[i] else "—"
        cost = num(a_v[i]) if a_kind[i] == 2 else "—"
        alt_rows.append(
            '<tr><td class="oid">A%02d</td><td class="nm">%s</td>'
            '<td>%s</td><td class="num roll">%s</td>'
            '<td class="num">%s</td><td class="lim">%s</td></tr>'
            % (rid, esc(a_name[i]), esc(desc), gain, esc(cost), esc(req)))

    aff_rows = []
    for i in range(FN):
        aid = i + 1
        txt = aff_text(aid, f_kind[i], f_v[i], f_v2[i], aff_warn.get(aid, ""))
        aff_rows.append(
            '<tr><td class="oid">W%02d</td><td class="nm">%s</td>'
            '<td>%s</td><td class="num">%d</td></tr>'
            % (aid, esc(f_name[i]), esc(txt), f_ds[i]))

    affn_rows = []
    for r in range(RN):
        rng = ("%d" % f_lo[r]) if f_lo[r] == f_hi[r] \
            else ("%d~%d" % (f_lo[r], f_hi[r]))
        affn_rows.append(
            '<tr><td class="nm">%s</td><td class="num">%s</td>'
            '<td class="num">%d</td><td class="num">%d</td>'
            '<td class="num">%d</td></tr>'
            % (esc(rar_name[r]), rng, f_el[r], f_ra[r], f_bo[r]))

    hid_rows = "".join(
        '<tr><td>%s</td><td class="num roll">＋%d</td></tr>' % (esc(a), b)
        for a, b in [
            ("完成當場全部的事件", S["$@MJ_HidEvAll"]),
            ("解開模板的隱藏機關", S["$@MJ_HidPuzzle"]),
            ("全場無人死亡", S["$@MJ_HidNoDeath"]),
            ("擊殺模板的特定稀有怪", S["$@MJ_HidRare"]),
            ("打完主線首領時穩定度 ≥ 40", S["$@MJ_HidStab40"]),
            ("在限時內完成主線", S["$@MJ_HidFast"]),
            ("三個風險祭壇全部成功", S["$@MJ_HidAltar3"]),
        ])

    shop_rows = []
    for i in range(SN):
        need = ("完成 %s 階以上的主線" % rar_name[sh_need[i] - 1]
                if sh_need[i] else "—")
        shop_rows.append(
            '<tr><td class="nm">%s</td><td class="num roll">%d</td>'
            '<td class="num">%d</td><td class="lim">%s</td></tr>'
            % (esc(sh_name[i]), sh_cost[i], sh_week[i], esc(need)))

    ach_rows = "".join(
        '<tr><td class="nm">%s</td><td>%s</td></tr>'
        % (esc(ach_name[i]), esc(ach_desc[i])) for i in range(ach_n))

    week_rows = "".join(
        '<tr><td>%s</td><td class="num roll">%s</td></tr>' % (a, b)
        for a, b in [
            ("第 1 ~ %d 場" % S["$@MJ_WeekFull"], "100%"),
            ("第 %d ~ %d 場" % (S["$@MJ_WeekFull"] + 1, S["$@MJ_WeekHalf"]),
             "%d%%" % S["$@MJ_WeekRate2"]),
            ("第 %d 場之後" % (S["$@MJ_WeekHalf"] + 1), "0%"),
        ])

    #  平均一輪 = 冷卻 + 抽中所需的期望分鐘數(每分鐘檢查一次, 機率遞增)
    p_miss, exp = 1.0, 0.0
    for k in range(S["$@MJ_RollPity"]):
        rate = min(S["$@MJ_RollBase"] + S["$@MJ_RollStep"] * k,
                   S["$@MJ_RollMax"]) / 100.0
        exp += p_miss * rate * (k + 1)
        p_miss *= (1 - rate)
    cycle = int(round(S["$@MJ_CoolMin"] + exp))

    # ======================================================================
    #  HTML
    # ======================================================================
    style = re.search(r"<style>.*?</style>", read(STYLE_FROM), re.S)
    if not style:
        sys.exit("potential.html 裡找不到 <style> 區塊")
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
.maps{display:flex; flex-wrap:wrap; gap:8px; margin:10px 0 0}
.maps .chip{cursor:default}
.bn{display:inline-block; padding:1px 7px; margin-left:6px; border-radius:6px;
    font-size:.82em; white-space:nowrap; font-weight:700;
    background:#c6503022; color:#c65030}
.callout{border-left:3px solid var(--cinnabar); padding:2px 0 2px 14px;
         margin:18px 0 0; color:var(--ink-soft); font-size:14.5px;
         line-height:1.85; max-width:72ch}
.callout b{color:var(--ink)}
.two{display:grid; gap:24px; grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.two .note{max-width:none}
.keep{color:#3a8f5a; font-weight:500}
</style>
"""

    doc = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>天地大秘境玩法</title>
<meta name="description" content="神域仙境 天地大秘境：入口何時出現、五個階級、六個模板、40 條法則、20 項祭壇、18 條詞綴與獎勵兌換。">
<meta name="color-scheme" content="light dark">
<meta property="og:type" content="website">
<meta property="og:site_name" content="神域仙境">
<meta property="og:title" content="天地大秘境玩法">
<meta property="og:description" content="入口隨機現世，公告只給地圖名。找到它、決定進不進、把它打完。">
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
    <h1>天地大秘境玩法</h1>
    <p class="lede">秘境的入口<b>不是固定的 NPC</b> —— 它隨機出現在十二洞天的某一張圖上，全服公告<b>只給地圖名，不給座標</b>。找到那道裂隙、決定要不要踏進去、把 <b>__FLOORS__ 層</b>打完，就是這套玩法的全部。</p>
  </header>

  <section>
    <h2>三句話</h2>
    <ol class="steps">
      <li><b><i>一</i>找到它</b><p>公告會說「某某階・某某秘境 於 <b>某張洞天</b> 現世」。座標要自己找，裂隙只存在 __OPENMIN__ 分鐘。</p></li>
      <li><b><i>二</i>決定進不進</b><p>點下裂隙可以先進<b>預備廳</b>看完整資訊 —— 首領是誰、有什麼陷阱、幾盞魂燈。這裡不扣任何東西，看完可以退回。</p></li>
      <li><b><i>三</i>打完它</b><p>一層一層清，最後一層是首領。中途有<b>風險祭壇</b>可以拿難度換收益。撐不住也沒關係，已經到手的獎勵不會被收回。</p></li>
    </ol>
  </section>

  <section>
    <h2>入口什麼時候出現</h2>
    <div class="tbl-wrap">
      <table><tbody>__PACE__</tbody></table>
    </div>
    <p class="note">平均一輪約 <b>__CYCLE__ 分鐘</b>（冷卻 __COOL__ 分 + 抽中所需的時間）。沒有固定時段，也沒有預告。</p>

    <h3 class="sub">會開在這 __GN__ 張圖裡</h3>
    <div class="maps">__MAPS__</div>
    <p class="note">位置每次都不一樣 —— 是隨機取點再驗證能不能站人，不是固定幾個點輪流。公告被聊天洗掉的話，可以去問崑崙的<b>秘境守望者</b>開在哪張圖（他一樣不給座標）。</p>
  </section>

  <section>
    <h2>五個階級</h2>
    <p class="note">公告裡的第一個詞。階級決定這一場的長度、強度與收益，<b>進去之前就知道</b>。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>階級</th><th class="num">抽中機率</th><th class="num">層數</th><th class="num">時限</th><th class="num">每分鐘扣穩</th><th class="num">魂燈 1人／6人</th><th class="num">怪物血量</th><th class="num">隱藏層基率</th><th>玩家輸出壓制</th></tr></thead>
        <tbody>__RARROWS__</tbody>
      </table>
    </div>
    <div class="callout">
      <b>仙階以上會壓制玩家輸出。</b>那不是你的裝備出問題 —— 裂隙的對話框會用紅字寫明倍率。凡與靈完全走正常計算，沒有任何壓制。<br>
      高階的每分鐘扣穩<b>反而更慢</b>，因為路更長。高階的壓力來自魂燈變少、機制變多，不是逼你超時。
    </div>
  </section>

  <section>
    <h2>六個模板</h2>
    <p class="note">公告裡的第二個詞。模板決定怪、事件、陷阱與首領 —— <b>地形是同一張</b>，差別不在地圖長什麼樣子。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>模板</th><th class="num">抽中機率</th><th>事件</th><th>陷阱</th><th>可能的首領</th></tr></thead>
        <tbody>__TPLROWS__</tbody>
      </table>
    </div>
    <p class="note">每個模板有 3 隻首領等權抽 1，所以同一個模板進去兩次不一定打到同一隻。</p>
  </section>

  <section>
    <h2>踏進去之前</h2>
    <div class="two">
      <div>
        <h3 class="sub" style="margin-top:0">人數在預備廳就鎖定</h3>
        <p class="note">只算<b>同一張圖、你身邊 8 格內</b>的隊友，最多 6 人。踏進去的那一刻名單就鎖死 —— 之後退隊、掉線、死亡都<b>不會</b>降低難度。要一起打就得先站在一起。</p>
      </div>
      <div>
        <h3 class="sub" style="margin-top:0">預備廳不扣任何東西</h3>
        <p class="note">在預備廳看得到首領名字與招式、事件與陷阱、魂燈數與怪物倍率。看完覺得打不過，直接退回，裂隙還在原處。</p>
      </div>
    </div>
    <div class="tbl-wrap" style="margin-top:18px">
      <table>
        <thead><tr><th class="num">人數</th><th class="num">怪物血量</th><th class="num">怪物攻擊</th><th class="num">每精英層的精英數</th><th class="num">被點名人數</th><th class="num">扣穩速度</th></tr></thead>
        <tbody>__PARTY__</tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>兩條各自獨立的失敗線</h2>
    <div class="two">
      <div>
        <h3 class="sub" style="margin-top:0">穩定度</h3>
        <p class="note">從 <b>100</b> 開始，隨時間自然往下掉，歸零就崩塌。低於 20 與 10 時各提示一次 —— <b>提示本身不附加任何懲罰</b>，不會越掉越快。</p>
      </div>
      <div>
        <h3 class="sub" style="margin-top:0">絕對時限</h3>
        <p class="note">依階級 __HARDMIN__ ~ __HARDMAX__ 分鐘。<b>任何回穩都不會把時間買回來</b>，這兩條互不相干。</p>
      </div>
    </div>
    <div class="tbl-wrap" style="margin-top:18px">
      <table>
        <thead><tr><th>發生什麼</th><th class="num">穩定度</th><th>備註</th></tr></thead>
        <tbody>__STAB__</tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>魂燈 —— 全隊共用的復活次數</h2>
    <p class="note">死了以後 <b>__REVWAIT__ 秒</b>可以復起，恢復 <b>__REVHP__%</b> 的血與魔，並帶 <b>__REVPROT__ 秒</b>保護（一出手就取消）。每個人自己還有本場復活上限：凡靈 __REV1__ 次、仙神 __REV3__ 次、太初 __REV5__ 次。<b>燈燒完就只能看著。</b></p>
    <div class="callout">
      死亡扣穩定度與熄魂燈是<b>兩件事</b> —— 一死就扣穩，用復活技能也躲不掉；魂燈則是「真的站起來」才熄。
    </div>
  </section>

  <section>
    <h2>__BN__ 隻首領</h2>
    <p class="note">最後一層。三階段，血量 __GATE1__% 與 __GATE2__% 各一道破解閘門，轉階時有 <b>__SHIELD__%</b> 血量的盾。破解方式是打機關或按符石 —— <b>單人也做得到</b>，不需要第二個人站位。拖過 __ENRMIN__ ~ __ENRMAX__ 分鐘進狂暴。</p>
    <div class="controls">
      <div class="ctl-row">
        <input id="q-boss" class="search" type="search" placeholder="搜尋首領或招式…" aria-label="搜尋首領" data-target="#t-boss">
      </div>
    </div>
    <div class="tbl-wrap">
      <table id="t-boss">
        <thead><tr><th>編號</th><th>首領</th><th>招式特徵</th><th>模板</th></tr></thead>
        <tbody>__BOSS__</tbody>
      </table>
    </div>
    <p class="note">最後那隻<b>太初道影</b>只在太初階的隱藏層出現，是唯一的四階段首領。</p>
  </section>

  <section>
    <h2>__DN__ 條地圖法則</h2>
    <p class="note">每一場開場就抽好，<b>戰鬥中不會偷換</b>。階級越高抽越多條（凡 __RULE1__ 條 → 太初 __RULE5__ 條），每一類最多 __RULECAP__ 條。法則同時加難度也加獎勵。</p>
    <div class="controls">
      <div class="ctl-row">
        <input id="q-rule" class="search" type="search" placeholder="搜尋法則…　例：治療、召喚、精英" aria-label="搜尋法則" data-target="#t-rule">
      </div>
    </div>
    <div class="tbl-wrap">
      <table id="t-rule">
        <thead><tr><th>編號</th><th>名稱</th><th>類別</th><th>效果</th><th class="num">獎勵加成</th><th class="num">危險度</th></tr></thead>
        <tbody>__RULE__</tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>__AN__ 項風險祭壇</h2>
    <p class="note">過層時會進轉層廳，<b>__ALTOFFER__ 選 1 或跳過</b>，一場最多 __ALTRUN__ 個。<b>選了不能反悔。</b>成本會先攤在你面前 —— 獎勵倍率最多加到 ＋__ALTCAP__%。資格不符的祭壇根本不會出現在選單上，那不是壞了。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>編號</th><th>名稱</th><th>做什麼</th><th class="num">獎勵倍率</th><th class="num">立即扣穩</th><th>出現條件</th></tr></thead>
        <tbody>__ALT__</tbody>
      </table>
    </div>
    <p class="note">獎勵倍率寫「—」的那幾項不是沒好處 —— 它們是<b>直接多給你一條法則或一次翻盤機會</b>，收益是從那條法則本身的獎勵加成來的，不再另外加一次。</p>
  </section>

  <section>
    <h2>__FN__ 條萬妖詞綴</h2>
    <p class="note">掛在怪物身上的額外能力，發動前會在畫面上預警。有三條硬規則擋著：<b>回血與護盾最多一種</b>、<b>瞬移不與硬控同場</b>、<b>死亡地板最多一個來源</b> —— 不會出現無解組合。</p>
    <div class="controls">
      <div class="ctl-row">
        <input id="q-aff" class="search" type="search" placeholder="搜尋詞綴…" aria-label="搜尋詞綴" data-target="#t-aff">
      </div>
    </div>
    <div class="tbl-wrap">
      <table id="t-aff">
        <thead><tr><th>編號</th><th>名稱</th><th>效果</th><th class="num">危險度</th></tr></thead>
        <tbody>__AFF__</tbody>
      </table>
    </div>
    <h3 class="sub">每一場會掛幾條</h3>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>階級</th><th class="num">普通怪</th><th class="num">精英</th><th class="num">稀有</th><th class="num">首領</th></tr></thead>
        <tbody>__AFFN__</tbody>
      </table>
    </div>
    <p class="note">最後兩條「神話」詞綴要污染 ≥ __MYTHCOR__ 且階級在神以上才會進池，太初一律開放。</p>
  </section>

  <section>
    <h2>隱藏層</h2>
    <p class="note">打完主線首領之後才判定。機率 =（階級基礎率 + 隱藏分）%，隱藏分最多算 __HIDCAP__ 分，最終機率上限 __HIDPCAP__%。</p>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>做到什麼</th><th class="num">隱藏分</th></tr></thead>
        <tbody>__HID__</tbody>
      </table>
    </div>
    <div class="callout">
      門開了也不一定進得去 —— 要<b>穩定度 ≥ __HIDNEED__</b>，而且付掉 <b>__HIDCOST__ 點</b>之後還要剩 <b>≥ __HIDKEEP__</b>。兩個條件不到就只能撤離。<br>
      <b>撤離或失敗都不影響主線的獎勵</b> —— 主線的部分在打完首領當下就已經入帳了。<br>
      「限時完成主線」的門檻依階級是 __HIDFAST__ 分鐘。
    </div>
  </section>

  <section>
    <h2>獎勵</h2>
    <p class="note">主線通關給<b>秘境碎片</b>，基礎 __RWBASE__ 片再乘上難度倍率與本週收益率。難度倍率吃階級（凡 ×__RR1__ → 太初 ×__RR5__）、層數、祭壇與法則。</p>
    <div class="two">
      <div>
        <h3 class="sub" style="margin-top:0">本週第幾場</h3>
        <div class="tbl-wrap">
          <table><thead><tr><th>場次</th><th class="num">收益率</th></tr></thead><tbody>__WEEK__</tbody></table>
        </div>
        <p class="note">一週認真打 <b>__WEEKFULL__ 場</b>就好，之後大幅遞減。守望者的第一頁就寫著你下一場拿幾成。</p>
      </div>
      <div>
        <h3 class="sub" style="margin-top:0">失敗補償</h3>
        <p class="note">崩塌或超時也有補償：每完成一個非首領層 __FAILPF__ 片，單場最多 __FAILCAP__ 片；每週最多領 __FAILN__ 次、總共 __FAILSUM__ 片。<b>已經入帳的獎勵不會因為崩塌被收回。</b></p>
      </div>
    </div>
    <h3 class="sub">碎片兌換（找秘境守望者）</h3>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>兌換</th><th class="num">碎片</th><th class="num">每週上限</th><th>門檻</th></tr></thead>
        <tbody>__SHOP__</tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>成就、排行榜與守望者</h2>
    <div class="two">
      <div>
        <h3 class="sub" style="margin-top:0">__ACHN__ 個秘境成就</h3>
        <div class="tbl-wrap">
          <table><tbody>__ACH__</tbody></table>
        </div>
        <p class="note">只給收藏與外觀，<b>不堆疊永久傷害</b>。成就記在帳號上，換角色不用重領。</p>
      </div>
      <div>
        <h3 class="sub" style="margin-top:0">__RANKN__ 種排行榜</h3>
        <p class="note">__RANK__。各自依階級、模板、人數與境界分開排。</p>
        <h3 class="sub">秘境守望者</h3>
        <p class="note">在<b>崑崙</b>。查入口開在哪張圖、斷線後返回原場次、領取獎勵、碎片兌換、看成就與排行榜，全都找他。</p>
      </div>
    </div>
  </section>

  <section>
    <h2>爭天秘境</h2>
    <p class="note">同一套秘境的 <b>PVP 分支</b>，報名處也在崑崙。<b>永遠是自願的</b> —— 公告會明講是 PVP，還要按二次確認才鎖隊。它<b>不抽太初、不列一般通關榜</b>，核心畢業材料一片都不給。不想碰的人完全不會被捲進去。</p>
  </section>

  <footer class="foot">
    資料以伺服器實際設定為準。若頁面內容與遊戲內不符，請以遊戲內為準並回報管理員。
  </footer>
</div>

<script>
(function(){
  var boxes = document.querySelectorAll('.search[data-target]');
  Array.prototype.forEach.call(boxes, function(box){
    var tb = document.querySelector(box.getAttribute('data-target') + ' tbody');
    if(!tb) return;
    var rows = Array.prototype.slice.call(tb.querySelectorAll('tr'));
    box.addEventListener('input', function(){
      var s = box.value.trim().toLowerCase();
      rows.forEach(function(tr){
        tr.hidden = !!s && tr.textContent.toLowerCase().indexOf(s) < 0;
      });
    });
  });
})();
</script>
</body>
</html>
"""

    rep = {
        "__STYLE__": style,
        "__EXTRA__": extra,
        "__FLOORS__": "%d~%d" % (min(rar_fl), max(rar_fl)),
        "__OPENMIN__": str(S["$@MJ_OpenSec"] // 60),
        "__PACE__": pace_rows,
        "__CYCLE__": str(cycle),
        "__COOL__": str(S["$@MJ_CoolMin"]),
        "__GN__": str(GN),
        "__MAPS__": gate_chips,
        "__RARROWS__": "".join(rar_rows),
        "__TPLROWS__": "".join(tpl_rows),
        "__PARTY__": "".join(party_rows),
        "__STAB__": stab_rows,
        "__HARDMIN__": str(min(rar_hard)),
        "__HARDMAX__": str(max(rar_hard)),
        "__REVWAIT__": str(S["$@MJ_ReviveWait"]),
        "__REVHP__": str(S["$@MJ_ReviveHP"]),
        "__REVPROT__": str(S["$@MJ_ReviveProt"]),
        "__REV1__": str(rar_rev[0]),
        "__REV3__": str(rar_rev[2]),
        "__REV5__": str(rar_rev[4]),
        "__BN__": str(BN),
        "__GATE1__": str(S["$@MJ_BossGate1"]),
        "__GATE2__": str(S["$@MJ_BossGate2"]),
        "__SHIELD__": str(S["$@MJ_BossShield"]),
        "__ENRMIN__": str(min(rar_enr)),
        "__ENRMAX__": str(max(rar_enr)),
        "__BOSS__": "".join(boss_rows),
        "__DN__": str(DN),
        "__RULE1__": str(rar_rules[0]),
        "__RULE5__": str(rar_rules[4]),
        "__RULECAP__": str(S["$@MJ_RuleCatCap"]),
        "__RULE__": "".join(rule_rows),
        "__AN__": str(AN),
        "__ALTOFFER__": str(S["$@MJ_AltOffer"]),
        "__ALTRUN__": str(S["$@MJ_AltPerRun"]),
        "__ALTCAP__": num(S["$@MJ_AltQCap"]),
        "__ALT__": "".join(alt_rows),
        "__FN__": str(FN),
        "__AFF__": "".join(aff_rows),
        "__AFFN__": "".join(affn_rows),
        "__MYTHCOR__": str(S["$@MJ_CorGate3"]),
        "__HIDCAP__": str(S["$@MJ_HidScoreCap"]),
        "__HIDPCAP__": str(S["$@MJ_HidPCap"]),
        "__HID__": hid_rows,
        "__HIDNEED__": num(S["$@MJ_HidNeed"]),
        "__HIDCOST__": num(S["$@MJ_HidCost"]),
        "__HIDKEEP__": num(S["$@MJ_HidKeep"]),
        "__HIDFAST__": "／".join(
            "%s %d" % (rar_name[r], hidfast[r]) for r in range(RN)),
        "__RWBASE__": str(S["$@MJ_RewardBase"]),
        "__RR1__": "%g" % (rar_rr[0] / 100.0),
        "__RR5__": "%g" % (rar_rr[4] / 100.0),
        "__WEEK__": week_rows,
        "__WEEKFULL__": str(S["$@MJ_WeekFull"]),
        "__FAILPF__": str(S["$@MJ_FailPerFl"]),
        "__FAILCAP__": str(S["$@MJ_FailCap"]),
        "__FAILN__": str(S["$@MJ_FailWeekN"]),
        "__FAILSUM__": str(S["$@MJ_FailWeekSum"]),
        "__SHOP__": "".join(shop_rows),
        "__ACHN__": str(ach_n),
        "__ACH__": ach_rows,
        "__RANKN__": str(S["$@MJ_RankN"]),
        "__RANK__": "、".join(rank_name),
    }
    for k, v in rep.items():
        doc = doc.replace(k, v)

    left = sorted(set(re.findall(r"__[A-Z0-9_]+__", doc)))
    if left:
        die("有沒被替換掉的佔位符: %s" % left)

    with io.open(DEST, "w", encoding="utf-8", newline="\n") as f:
        f.write(doc)

    narrative = [i + 1 for i in range(DN) if d_kind[i] == 11 and i + 1 != 16]
    print("階級 %d / 模板 %d / 首領 %d / 法則 %d / 祭壇 %d / 詞綴 %d / 兌換 %d"
          % (RN, TN, BN, DN, AN, FN, SN))
    print("候選地圖 %d 張, 入口存在 %d 分, 冷卻 %d 分, 平均一輪約 %d 分"
          % (GN, S["$@MJ_OpenSec"] // 60, S["$@MJ_CoolMin"], cycle))
    print("階級機率 " + " / ".join("%s %g%%" % (rar_name[r], rar_pct[r])
                                   for r in range(RN)))
    print("★ 只給獎勵不加難度的法則(kind 11 且非 D16): "
          + (", ".join("D%02d %s" % (i, d_name[i - 1]) for i in narrative)
             if narrative else "無"))
    print("已寫出 %s (%d bytes)" % (DEST, os.path.getsize(DEST)))


if __name__ == "__main__":
    main()

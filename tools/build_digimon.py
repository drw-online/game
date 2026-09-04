# -*- coding: utf-8 -*-
"""
數碼寶貝圖鑑產生器 —— 產生 digimon/*.png 與 digimon.html, 跑完自己驗證一次。

用法(需要 Pillow):

    python tools/build_digimon.py

--------------------------------------------------------------------------
來源
--------------------------------------------------------------------------
  2.開機擋/db/import/blackgod/pet_digimon.yml          33 筆的 Mob / EggItem
  2.開機擋/db/import/blackgod/mob_digimon.yml          魔物編號與 JapaneseName
  2.開機擋/db/import/blackgod/item_petegg_digimon.yml  寵物蛋編號
  外觀 (兩處, 逐名解析 —— 只看其中一處會少一批而且不會報錯):
    3.客戶端/data/sprite/跨蝶攪/         [2026-09-04] 新增的 22 隻
    3.客戶端/old/data_/sprite/跨蝶攪/    最早那 11 隻

--------------------------------------------------------------------------
與 build_pets.py 的關係
--------------------------------------------------------------------------
spr/act 解碼、渲染、頁面版型全部沿用 build_pets.py —— 它已經處理好
spr 2.0/2.1 與 act 2.3/2.5 的版本差異(細節見該檔檔頭)。本檔只換掉
資料來源、sprite 路徑與文案, 版面與其他頁保持一致。

sprite 檔名用 AegisName(Agumon / Greymon ...), 不是 build_pets 那種連號。
"""
import os, re, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
WEB  = os.path.dirname(HERE)
ROOT = r"H:\91.神域仙境"
DB   = os.path.join(ROOT, r"2.開機擋\db\import\blackgod")
SPR_DIRS = [
    os.path.join(ROOT, r"3.客戶端\data\sprite\跨蝶攪"),
    os.path.join(ROOT, r"3.客戶端\old\data_\sprite\跨蝶攪"),
]
PNG = os.path.join(WEB, "digimon")

_spec = importlib.util.spec_from_file_location("build_pets", os.path.join(HERE, "build_pets.py"))
bp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bp)          # 有 __main__ 保護, import 不會跑到 main()

from PIL import Image


def parse_sources():
    """三支 YAML 對出 33 筆 (編號, 中文名, 魔物編號, 蛋編號, sprite 檔名)。"""
    mob = bp.read_text(os.path.join(DB, "mob_digimon.yml"))
    pet = bp.read_text(os.path.join(DB, "pet_digimon.yml"))
    egg = bp.read_text(os.path.join(DB, "item_petegg_digimon.yml"))

    mi = {m[1]: dict(id=int(m[0]), jp=m[3].strip()) for m in re.findall(
        r'^  - Id: (\d+)\n    AegisName: (\S+)\n    Name: (.+)\n    JapaneseName: (.+)$', mob, re.M)}
    ei = {m[1]: dict(id=int(m[0]), name=m[2].strip()) for m in re.findall(
        r'^  - Id: (\d+)\n    AegisName: (\S+)\n    Name: (.+)$', egg, re.M)}
    pets = re.findall(r'^  - Mob: (\S+)\n    EggItem: (\S+)$', pet, re.M)

    rows = []
    for k, (mob_aegis, egg_aegis) in enumerate(pets, 1):
        if mob_aegis not in mi:
            raise SystemExit("mob_digimon.yml 缺 " + mob_aegis)
        if egg_aegis not in ei:
            raise SystemExit("item_petegg_digimon.yml 缺 " + egg_aegis)
        m, e = mi[mob_aegis], ei[egg_aegis]
        rows.append(dict(no=k, name=m['jp'], mob=m['id'], egg=e['id'], spr=mob_aegis))
    return rows


def find_spr_dir(name):
    """回傳 (目錄, 實際檔名)。找不到回 (None, None) 由呼叫端決定怎麼辦。

    檔名一律等於 AegisName。曾經有一筆例外(來源套件把神聖天使獸的圖
    叫 MagnaAngemon, mob_db 卻用 Anangeon), 已於 [2026-09-04] 直接把
    客戶端的 spr/act 更名為 Anangeon —— 客戶端 jobname.lub 也是拿
    AegisName 去找圖的, 留著別名只會讓遊戲裡看不到而網頁看得到。
    """
    for d in SPR_DIRS:
        if os.path.exists(os.path.join(d, name + ".spr")) \
           and os.path.exists(os.path.join(d, name + ".act")):
            return d, name
    return None, None


def render_all(rows):
    """回 (有圖的 rows, sizes, 各目錄張數, 沒圖的 rows)。

    ★ 沒圖的不是小問題 —— 客戶端 jobname.lub 指到不存在的 spr, 那隻在
      遊戲裡也不會有外觀。這裡只是把它擋在圖鑑外, 真正要修的是素材。
    """
    os.makedirs(PNG, exist_ok=True)
    sizes, used, ok, missing = {}, {}, [], []
    for r in rows:
        d, fn = find_spr_dir(r['spr'])
        if d is None:
            missing.append(r)
            continue
        bp.SPR = d                                  # bp.render 讀模組層級的 SPR
        sizes[r['spr']] = bp.render(fn, os.path.join(PNG, r['spr'] + ".png"))
        used[d] = used.get(d, 0) + 1
        ok.append(r)
    return ok, sizes, used, missing


# ------------------------------------------------------------------ 頁面
REPL = [
    ("靈獸島 162 種神域寵物的外觀對照，附魔物編號與寵物蛋編號。",
     "神域仙境 33 種數碼寶貝寵物的外觀對照，附魔物編號與寵物蛋編號。"),
    ("神域寵物圖鑑", "數碼寶貝圖鑑"),
    ('src="pets/', 'src="digimon/'),
    ("靈獸島的 <b>162 種神域寵物</b>", "全部 <b>33 種數碼寶貝寵物</b>"),
    ('<b id="shown">162</b> / 162 種', '<b id="shown">33</b> / 33 種'),
    ("162 種神域寵物", "33 種數碼寶貝"),
]
FOOT_OLD = ("<p><b>編號是連號的。</b>第 N 號寵物的魔物編號是 <b>24999 + N</b>、"
            "寵物蛋編號是 <b>4099999 + N</b> —— 001 對到 25000 與 4100000，"
            "162 對到 25161 與 4100161，中間沒有跳號。</p>")
FOOT_NEW = ("<p><b>編號是連號的。</b>第 N 號的魔物編號是 <b>30000 + N</b>、"
            "寵物蛋編號是 <b>4199999 + N</b> —— 001 對到 30001 與 4200000，"
            "033 對到 30033 與 4200032，中間沒有跳號。</p>"
            "<p><b>數碼寶貝孵出來就是 ★5 星 5 條</b>，升級點數也是三倍（每級 3 點），"
            '另外天生自帶一組固定能力。詳見<a href="petaffix.html">寵物詞條與星級</a>。</p>')


def build_page(rows, sizes):
    n = len(rows)
    cards = [bp.CARD.format(w=sizes[r['spr']][0], h=sizes[r['spr']][1], **r) for r in rows]
    html = bp.PAGE.replace('__CARDS__', '\n'.join('    ' + c for c in cards))
    for old, new in REPL:
        html = html.replace(old, new.replace("33", str(n)))
    if FOOT_OLD in html:
        html = html.replace(FOOT_OLD, FOOT_NEW)
    else:
        print("!! 頁尾連號說明沒換到(版型可能改過), 請人工確認")
    stale = [t for t in ("靈獸島", "神域寵物", "162", 'href="pets', 'src="pets/') if t in html]
    if stale:
        raise SystemExit("頁面殘留 pets 專用字樣: %s" % stale)
    with open(os.path.join(WEB, "digimon.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    return html


def verify(rows, sizes, html):
    """反向解析 —— 直接改 HTML 最容易「改了 A 忘了改 B」, 只有回頭解析才抓得到。"""
    err = []
    cards = re.findall(
        r'data-k="(\d+) (\S+) (\d+) (\d+)".*?src="digimon/(\S+?)\.png" width="(\d+)" height="(\d+)"',
        html)
    if len(cards) != len(rows):
        err.append("卡片數 %d != %d" % (len(cards), len(rows)))
    for (no, name, mob, egg, spr, w, h), r in zip(cards, rows):
        if (int(no), name, int(mob), int(egg), spr) != (r['no'], r['name'], r['mob'], r['egg'], r['spr']):
            err.append("欄位不符 #%s" % no)
        p = os.path.join(PNG, spr + ".png")
        if not os.path.exists(p):
            err.append("缺圖 " + spr)
        elif Image.open(p).size != (int(w), int(h)):
            err.append("尺寸 %s %s != %s" % (spr, Image.open(p).size, (w, h)))
    n = len(rows)
    for token in ["%d 種數碼寶貝" % n, '<b id="shown">%d</b> / %d 種' % (n, n), 'href="index.html"']:
        if token not in html:
            err.append("缺字串 " + token)
    return err


def main():
    allrows = parse_sources()
    print("來源  %d 筆 (魔物 %d~%d / 蛋 %d~%d)" % (
        len(allrows), allrows[0]['mob'], allrows[-1]['mob'], allrows[0]['egg'], allrows[-1]['egg']))
    rows, sizes, used, missing = render_all(allrows)
    for d, n in sorted(used.items()):
        print("外觀  %2d 張 <- %s" % (n, d))
    if missing:
        print("!! 沒有 sprite, 已排除在圖鑑外 (這幾隻在遊戲裡也不會有外觀):")
        for r in missing:
            print("     #%02d %s  魔物 %d  蛋 %d  (找不到 %s.spr/.act)"
                  % (r['no'], r['name'], r['mob'], r['egg'], r['spr']))
    html = build_page(rows, sizes)
    print("頁面  digimon.html %.1f KB" % (len(html.encode('utf-8')) / 1024))
    err = verify(rows, sizes, html)
    if err:
        print("驗證失敗:")
        for e in err:
            print("       ", e)
        raise SystemExit(1)
    print("完成。來源沒變的話 git status 應該是乾淨的。")


if __name__ == "__main__":
    main()

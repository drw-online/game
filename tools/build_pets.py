# -*- coding: utf-8 -*-
"""
神域寵物圖鑑產生器 —— 產生 pets/*.png 與 pets.html, 跑完自己驗證一次。

用法(需要 Pillow):

    python tools/build_pets.py

會覆寫 pets.html 與 pets/ 底下的 162 張 PNG。輸出是決定性的 ——
來源沒變的話重跑一次 git status 應該是乾淨的, 這也是最好的回歸測試。

--------------------------------------------------------------------------
來源
--------------------------------------------------------------------------
  2.開機擋/db/import/blackgod/pet_drwmob.yml          162 筆的 Mob / EggItem
  2.開機擋/db/import/blackgod/mob_drwmob.yml          魔物編號與 JapaneseName
  2.開機擋/db/import/blackgod/item_petegg_drwmob.yml  寵物蛋編號
  3.客戶端/old/data09/<몬스터>/drwmob001~162.spr|act  外觀

★ 完整的 162 隻只在 old/data09。3.客戶端/data/sprite 底下只有 129~162
  那批 34 隻, 前 128 隻早就打包進 drw02.grf —— 從那裡抓會只拿到五分之一,
  而且不會有任何錯誤訊息。

--------------------------------------------------------------------------
spr / act 格式
--------------------------------------------------------------------------
遊戲內顯示的名字是 mob_db 的 JapaneseName 不是 Name(override_mob_names: 2)。

外觀取 act 動作 0(站立朝南)第 0 格, 合成所有圖層後裁掉透明邊。

162 隻裡兩種 spr 版本混在一起, act 也是, 只實作其中一版會在中途炸掉,
而且錯誤訊息長得像檔案損毀:

  spr 2.1  索引格 RLE 壓縮      122 隻
  spr 2.0  索引格未壓縮          40 隻
  act 2.5                       157 隻
  act 2.3  少 scaleY 與 w/h 欄位  5 隻

RGBA 格是 ABGR 順序而且上下顛倒; 索引格則是正常方向、索引 0 當透明。

有一部分外觀把陰影畫進圖裡(alpha 255 的純黑塊, 不是解碼錯誤),
所以圖上腳邊會帶一塊黑影。pets.html 頁尾有對玩家說明這件事。
"""
import os, re, struct
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
WEB  = os.path.dirname(HERE)
ROOT = r"H:\91.神域仙境"
DB   = os.path.join(ROOT, r"2.開機擋\db\import\blackgod")
SPR  = os.path.join(ROOT, r"3.客戶端\old\data09\跨蝶攪")
PNG  = os.path.join(WEB, "pets")

MAX = 128  # 縮圖長邊上限


# ---------------------------------------------------------------- 來源解析

def read_text(path):
    d = open(path, 'rb').read()
    if d[:3] == b'\xef\xbb\xbf':
        d = d[3:]
    return d.decode('utf-8').replace('\r\n', '\n')


def parse_sources():
    """三支 YAML 對出 162 筆 (編號, 名稱, 魔物編號, 蛋編號, sprite 檔名)。"""
    mob = read_text(os.path.join(DB, "mob_drwmob.yml"))
    pet = read_text(os.path.join(DB, "pet_drwmob.yml"))
    egg = read_text(os.path.join(DB, "item_petegg_drwmob.yml"))

    mi = {m[1]: dict(id=int(m[0]), jp=m[3].strip()) for m in re.findall(
        r'^  - Id: (\d+)\n    AegisName: (\S+)\n    Name: (.+)\n    JapaneseName: (.+)$', mob, re.M)}
    ei = {m[1]: dict(id=int(m[0]), name=m[2].strip()) for m in re.findall(
        r'^  - Id: (\d+)\n    AegisName: (\S+)\n    Name: (.+)$', egg, re.M)}
    pets = re.findall(r'^  - Mob: (\S+)\n    EggItem: (\S+)$', pet, re.M)

    rows = []
    for k, (mob_aegis, egg_aegis) in enumerate(pets, 1):
        m, e = mi[mob_aegis], ei[egg_aegis]
        rows.append(dict(no=k, name=m['jp'], mob=m['id'], egg=e['id'], spr="drwmob%03d" % k))
    return rows


# ---------------------------------------------------------------- spr / act

def load_spr(path):
    d = open(path, 'rb').read()
    ver = struct.unpack_from('<H', d, 2)[0]
    n_idx, n_rgba = struct.unpack_from('<HH', d, 4)
    off = 8
    idx = []
    for _ in range(n_idx):
        if ver >= 0x201:                       # RLE: 0x00 後面接連續 0 的個數
            w, h, clen = struct.unpack_from('<HHH', d, off); off += 6
            comp = d[off:off + clen]; off += clen
            px = bytearray(); j = 0
            while j < len(comp):
                c = comp[j]; j += 1
                if c == 0:
                    if j >= len(comp):
                        break
                    px.extend(b'\x00' * comp[j]); j += 1
                else:
                    px.append(c)
        else:                                  # 2.0: 未壓縮
            w, h = struct.unpack_from('<HH', d, off); off += 4
            px = bytearray(d[off:off + w * h]); off += w * h
        idx.append((w, h, bytes(px[:w * h]).ljust(w * h, b'\x00')))
    rgba = []
    for _ in range(n_rgba):
        w, h = struct.unpack_from('<HH', d, off); off += 4
        rgba.append((w, h, d[off:off + w * h * 4])); off += w * h * 4
    pal = d[-1024:] if n_idx else None
    return idx, rgba, pal


def img_indexed(frame, pal):
    w, h, px = frame
    if not w or not h:
        return None
    im = Image.frombytes('P', (w, h), px)
    im.putpalette(b''.join(pal[c * 4:c * 4 + 3] for c in range(256)))
    im = im.convert('RGBA')
    a = im.load()
    for y in range(h):
        row = y * w
        for x in range(w):
            if px[row + x] == 0:               # 索引 0 = 透明
                a[x, y] = (0, 0, 0, 0)
    return im


def img_rgba(frame):
    w, h, raw = frame
    if not w or not h:
        return None
    r, g, b, a = Image.frombytes('RGBA', (w, h), raw).split()
    return Image.merge('RGBA', (a, b, g, r)).transpose(Image.FLIP_TOP_BOTTOM)


def act_idle_layers(path):
    """動作 0 第 0 格的圖層。"""
    d = open(path, 'rb').read()
    ver = struct.unpack_from('<H', d, 2)[0]
    off = 16                                   # magic2 + ver2 + actions2 + reserved10
    off += 4                                   # 動作 0 的 frame count
    off += 32                                  # frame reserved
    n = struct.unpack_from('<I', d, off)[0]; off += 4
    layers = []
    for _ in range(n):
        x, y, si, mirror = struct.unpack_from('<iiiI', d, off); off += 16
        off += 4                               # color rgba
        sx = struct.unpack_from('<f', d, off)[0]; off += 4
        if ver >= 0x204:
            sy = struct.unpack_from('<f', d, off)[0]; off += 4
        else:
            sy = sx
        rot, spr_type = struct.unpack_from('<ii', d, off); off += 8
        if ver >= 0x205:
            off += 8                           # width / height
        layers.append(dict(x=x, y=y, i=si, mirror=mirror, sx=sx, sy=sy, rot=rot, t=spr_type))
    return layers


def render(name, out_path):
    idx, rgba, pal = load_spr(os.path.join(SPR, name + ".spr"))
    canvas = Image.new('RGBA', (500, 500), (0, 0, 0, 0))
    for l in act_idle_layers(os.path.join(SPR, name + ".act")):
        src = rgba if l['t'] == 1 else idx
        if not 0 <= l['i'] < len(src):
            continue
        im = img_rgba(src[l['i']]) if l['t'] == 1 else img_indexed(src[l['i']], pal)
        if im is None:
            continue
        if l['mirror']:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if abs(l['sx'] - 1) > 1e-3 or abs(l['sy'] - 1) > 1e-3:
            im = im.resize((max(1, int(im.width * abs(l['sx']))),
                            max(1, int(im.height * abs(l['sy'])))), Image.NEAREST)
        if l['rot']:
            im = im.rotate(-l['rot'], expand=True, resample=Image.NEAREST)
        canvas.alpha_composite(im, (250 + l['x'] - im.width // 2, 250 + l['y'] - im.height // 2))
    box = canvas.getbbox()
    if not box:
        raise ValueError(name + " 渲染出空圖")
    out = canvas.crop(box)
    if out.width > MAX or out.height > MAX:
        out.thumbnail((MAX, MAX), Image.LANCZOS)
    out.save(out_path, optimize=True)
    return out.width, out.height


# ---------------------------------------------------------------- 頁面

PAGE = '''<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>神域寵物圖鑑</title>
<meta name="description" content="神域仙境 靈獸島 162 種神域寵物的外觀對照，附魔物編號與寵物蛋編號。">
<meta name="color-scheme" content="light dark">
<meta property="og:type" content="website">
<meta property="og:site_name" content="神域仙境">
<meta property="og:title" content="神域寵物圖鑑">
<meta property="og:description" content="神域仙境 靈獸島 162 種神域寵物的外觀對照，附魔物編號與寵物蛋編號。">
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
  --shadow-lift:0 2px 4px #1f242216, 0 14px 34px #1f242212;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ground:#121615; --paper:#1A201E; --sunk:#0D100F;
    --ink:#E4E8E3; --ink-soft:#9AA4A0; --ink-faint:#6E7873;
    --rule:#2A322F; --rule-soft:#222A27;
    --cinnabar:#E0654A; --cinnabar-wash:#E0654A22;
    --on-accent:#121615; --focus:#E0654A;
    --shadow:0 1px 2px #00000040, 0 6px 18px #00000030;
    --shadow-lift:0 2px 6px #00000055, 0 14px 34px #00000045;
  }
}
:root[data-theme="dark"]{
  --ground:#121615; --paper:#1A201E; --sunk:#0D100F;
  --ink:#E4E8E3; --ink-soft:#9AA4A0; --ink-faint:#6E7873;
  --rule:#2A322F; --rule-soft:#222A27;
  --cinnabar:#E0654A; --cinnabar-wash:#E0654A22;
  --on-accent:#121615; --focus:#E0654A;
  --shadow:0 1px 2px #00000040, 0 6px 18px #00000030;
  --shadow-lift:0 2px 6px #00000055, 0 14px 34px #00000045;
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

.bar{margin-top:30px; display:flex; flex-wrap:wrap; align-items:center; gap:14px}
.search{flex:1 1 260px; min-width:0}
.search input{
  width:100%; padding:11px 14px; font:inherit; font-size:14px; color:var(--ink);
  background:var(--paper); border:1px solid var(--rule); border-radius:6px;
}
.search input::placeholder{color:var(--ink-faint)}
.search input:focus-visible{outline:2px solid var(--focus); outline-offset:2px; border-color:var(--cinnabar)}
.count{font-size:13px; color:var(--ink-faint); font-variant-numeric:tabular-nums; white-space:nowrap}
.count b{color:var(--cinnabar); font-weight:700}

.grid{list-style:none; margin:22px 0 0; padding:0;
  display:grid; gap:14px; grid-template-columns:repeat(auto-fill,minmax(158px,1fr))}
.pet{
  display:flex; flex-direction:column; align-items:center; gap:2px;
  padding:14px 12px 16px; background:var(--paper);
  border:1px solid var(--rule-soft); border-radius:6px; box-shadow:var(--shadow);
  transition:transform .14s ease, box-shadow .14s ease, border-color .14s ease;
}
.pet:hover{transform:translateY(-3px); box-shadow:var(--shadow-lift); border-color:var(--cinnabar)}
.pet[hidden]{display:none}
.fig{height:136px; width:100%; display:flex; align-items:flex-end; justify-content:center;
  border-bottom:1px solid var(--rule-soft); margin-bottom:11px}
.fig img{max-width:100%; height:auto; image-rendering:pixelated;
  image-rendering:-moz-crisp-edges; image-rendering:crisp-edges}
.no{font-family:"Noto Serif TC",serif; font-size:23px; font-weight:900;
  letter-spacing:.08em; color:var(--cinnabar); font-variant-numeric:tabular-nums; line-height:1.2}
.nm{font-size:13px; color:var(--ink-soft)}
.ids{margin-top:7px; display:flex; flex-direction:column; align-items:center; gap:1px;
  font-size:11.5px; color:var(--ink-faint); letter-spacing:.04em}
.ids i{font-style:normal; font-variant-numeric:tabular-nums; color:var(--ink-soft)}

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
  .grid{grid-template-columns:repeat(auto-fill,minmax(136px,1fr)); gap:11px}
  .fig{height:112px}
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
    <h1>神域寵物圖鑑</h1>
    <p class="lede">靈獸島的 <b>162 種神域寵物</b>，編號與長相的對照表。每一筆附上牠的<b>魔物編號</b>與對應的<b>寵物蛋編號</b> —— 蛋的名稱、掉落與詞條查詢用的都是這組號碼。</p>
  </header>

  <div class="bar">
    <div class="search">
      <input id="q" type="search" placeholder="輸入編號、名稱、魔物編號或蛋編號…" autocomplete="off" aria-label="搜尋寵物">
    </div>
    <div class="count"><b id="shown">162</b> / 162 種</div>
  </div>

  <ul class="grid" id="grid">
__CARDS__
  </ul>
  <p class="empty" id="empty" hidden>沒有符合的寵物。</p>

  <footer class="foot">
    <p><b>編號是連號的。</b>第 N 號寵物的魔物編號是 <b>24999 + N</b>、寵物蛋編號是 <b>4099999 + N</b> —— 001 對到 25000 與 4100000，162 對到 25161 與 4100161，中間沒有跳號。</p>
    <p><b>圖是遊戲裡的實際外觀。</b>直接取自客戶端的圖檔，抓的是站立朝南的第一格；有些外觀本身就把陰影畫進圖裡，看起來腳邊帶一塊黑影，那是原圖就有的。</p>
    <p><b>名字是出廠名稱。</b>寵物孵出來之後可以改名，改過的名字不會反映在這裡。</p>
    <a class="back" href="index.html">← 回神域仙境玩家工具</a>
  </footer>
</div>
<script>
(function(){
  var q = document.getElementById('q');
  var pets = Array.prototype.slice.call(document.querySelectorAll('.pet'));
  var shown = document.getElementById('shown');
  var empty = document.getElementById('empty');
  function filter(){
    var s = q.value.trim().toLowerCase(), n = 0;
    for (var i = 0; i < pets.length; i++){
      var hit = !s || pets[i].dataset.k.toLowerCase().indexOf(s) !== -1;
      pets[i].hidden = !hit;
      if (hit) n++;
    }
    shown.textContent = n;
    empty.hidden = n !== 0;
  }
  q.addEventListener('input', filter);
  filter();
})();
</script>
</body>
</html>
'''

CARD = ('<li class="pet" data-k="{no} {name} {mob} {egg}">'
        '<span class="fig"><img src="pets/{spr}.png" width="{w}" height="{h}" alt="{name}" loading="lazy" decoding="async"></span>'
        '<b class="no">{no}</b>'
        '<span class="nm">{name}</span>'
        '<span class="ids"><span>魔物 <i>{mob}</i></span><span>蛋 <i>{egg}</i></span></span>'
        '</li>')


def write_page(rows):
    cards = [CARD.format(no="%03d" % r['no'], name=r['name'], mob=r['mob'],
                         egg=r['egg'], spr=r['spr'], w=r['w'], h=r['h']) for r in rows]
    html = PAGE.replace('__CARDS__', '\n'.join('    ' + c for c in cards))
    with open(os.path.join(WEB, "pets.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    return html


# ---------------------------------------------------------------- 驗證

CARD_RE = re.compile(
    r'<li class="pet" data-k="(\d{3}) (\S+) (\d+) (\d+)">'
    r'<span class="fig"><img src="pets/(\w+)\.png" width="(\d+)" height="(\d+)" alt="(\S+?)" loading="lazy" decoding="async"></span>'
    r'<b class="no">(\d{3})</b>'
    r'<span class="nm">(\S+?)</span>'
    r'<span class="ids"><span>魔物 <i>(\d+)</i></span><span>蛋 <i>(\d+)</i></span></span></li>')


def verify(rows):
    """把寫出去的頁面重新解析回來, 跟來源與實際 PNG 逐項對。

    直接改 HTML 最容易出的錯是「改了 A 忘了改 B」, 只有反過來解析才抓得到。
    """
    html = open(os.path.join(WEB, "pets.html"), encoding="utf-8").read()
    cards = CARD_RE.findall(html)
    err = []
    if len(cards) != len(rows):
        err.append("卡片數 %d != 來源 %d" % (len(cards), len(rows)))

    for c, s in zip(cards, rows):
        k_no, k_nm, k_mob, k_egg, img, w, h, alt, no, nm, mob, egg = c
        if int(no) != s['no']:   err.append(("編號", no, s['no']))
        if nm != s['name']:      err.append(("名稱", no, nm, s['name']))
        if int(mob) != s['mob']: err.append(("魔物編號", no, mob, s['mob']))
        if int(egg) != s['egg']: err.append(("蛋編號", no, egg, s['egg']))
        if img != s['spr']:      err.append(("圖檔", no, img, s['spr']))
        if alt != nm:            err.append(("alt", no, alt, nm))
        # data-k 與看得見的文字必須一致, 否則搜尋結果會對不上卡片內容
        if (k_no, k_nm, int(k_mob), int(k_egg)) != (no, nm, int(mob), int(egg)):
            err.append(("data-k 不一致", no))
        p = os.path.join(PNG, img + ".png")
        if not os.path.exists(p):
            err.append(("缺圖", p)); continue
        if Image.open(p).size != (int(w), int(h)):
            err.append(("尺寸", no, Image.open(p).size, (w, h)))

    # 編號 N -> 魔物 24999+N -> 蛋 4099999+N, 頁尾直接把這條規則寫給玩家看
    for s in rows:
        if s['mob'] != 24999 + s['no'] or s['egg'] != 4099999 + s['no']:
            err.append(("連號規則", s['no'], s['mob'], s['egg']))

    n_png = len([f for f in os.listdir(PNG) if f.endswith('.png')])
    if n_png != len(rows):
        err.append(("pets/ 內 PNG 數", n_png))
    for token in ['162 種神域寵物', '<b id="shown">162</b> / 162 種', 'href="index.html"']:
        if token not in html:
            err.append(("頁面文案缺", token))
    return err


# ---------------------------------------------------------------- 主流程

def main():
    rows = parse_sources()
    print("來源  pet/mob/egg 對出 %d 筆" % len(rows))

    os.makedirs(PNG, exist_ok=True)
    for r in rows:
        r['w'], r['h'] = render(r['spr'], os.path.join(PNG, r['spr'] + ".png"))
    total = sum(os.path.getsize(os.path.join(PNG, r['spr'] + ".png")) for r in rows)
    print("渲染  %d 張 PNG, 共 %.1f KB" % (len(rows), total / 1024))

    html = write_page(rows)
    print("頁面  pets.html %.1f KB" % (len(html.encode('utf-8')) / 1024))

    err = verify(rows)
    print("驗證  差異 %d" % len(err))
    for e in err[:12]:
        print("       ", e)
    if err:
        raise SystemExit(1)
    print("完成。來源沒變的話 git status 應該是乾淨的。")


if __name__ == "__main__":
    main()

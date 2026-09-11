# -*- coding: utf-8 -*-
"""build_daopan.py —— 產生 daopan.html 的「互動星盤」區塊。

用法:  python tools/build_daopan.py

★ 它只覆寫 daopan.html 裡
      <!-- DAOPAN-SIM:BEGIN -->  ...  <!-- DAOPAN-SIM:END -->
  之間的內容, 頁面其餘手寫的說明文字一個字都不動。
  第一次執行時若找不到標記, 會自動插在第一個 </section> 之後。

★ 資料唯一來源是 2.開機擋/script/04.系統/70.大道星盤.txt 的 OnInit。
  改了那邊的節點表就重跑這支, 不要手改 daopan.html 裡的節點資料 ——
  那是「改了來源、網頁不會自己跟上」的典型現場。

★ 網頁照的是「現行遊戲規則」: 前置(pre / pre2 為或關係) + 56 點上限 +
  核心天賦互斥。刻意沒有點數門檻 —— 伺服器端沒有那條規則, 網頁多做
  會讓玩家照著排卻在遊戲裡點不出來。
  橫軸用的是節點在 pre 樹上的深度, 那只是排版, 不是限制。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.dirname(HERE)
SRC = os.path.normpath(os.path.join(
    WEB, '..', '..', '2.開機擋', 'script', '04.系統', '70.大道星盤.txt'))
OUT = os.path.join(WEB, 'daopan.html')

BEGIN = '<!-- DAOPAN-SIM:BEGIN -->'
END = '<!-- DAOPAN-SIM:END -->'
PATHS = [(100, '武道'), (200, '仙道'), (300, '守道'),
         (400, '血道'), (500, '疾道'), (600, '天命')]


def read_source():
    with open(SRC, encoding='utf-8') as f:
        return f.read()


def arr(text, prefix, base, isstr=False):
    """抓一條 setarray。★ prefix 可能含 $ (例 dao_name$), 一定要 re.escape。"""
    pat = r'setarray \$@' + re.escape(prefix) + r'\[' + str(base) + r'\],(.*?);\n'
    m = re.search(pat, text, re.S)
    if not m:
        sys.exit('找不到 $@%s[%d] —— 節點表結構變了, 先看 %s' % (prefix, base, SRC))
    body = re.sub(r'//[^\n]*', '', m.group(1))
    if isstr:
        return re.findall(r'"([^"]*)"', body)
    return [int(x.strip()) for x in body.split(',')
            if x.strip().lstrip('-').isdigit()]


def build_data(text):
    kn = arr(text, 'dao_kn$', 1, True)
    ku = arr(text, 'dao_ku', 1)
    ks = arr(text, 'dao_ks', 1)
    tmax = arr(text, 'dao_tmax', 1)
    tcost = arr(text, 'dao_tcost', 1)
    tname = arr(text, 'dao_tname$', 1, True)
    pdesc = arr(text, 'dao_pathdesc$', 0, True)
    slot = arr(text, 'dao_slot', 0)

    nodes = {}
    for base, pname in PATHS:
        cols = dict(
            nm=arr(text, 'dao_name$', base, True), ti=arr(text, 'dao_tier', base),
            p1=arr(text, 'dao_pre', base), p2=arr(text, 'dao_pre2', base),
            ex=arr(text, 'dao_ex', base),
            k1=arr(text, 'dao_ek1', base), v1=arr(text, 'dao_ev1', base),
            k2=arr(text, 'dao_ek2', base), v2=arr(text, 'dao_ev2', base),
            k3=arr(text, 'dao_ek3', base), v3=arr(text, 'dao_ev3', base))
        lens = {k: len(v) for k, v in cols.items()}
        # ★ 八張表是「四個一組」人工對齊的, 少一格不會報錯只會整段錯位。
        #   這道檢查就是為了讓那種錯當場停下來。
        if len(set(lens.values())) != 1:
            sys.exit('%s 的節點表長度不一致, 有人少數了一格: %s' % (pname, lens))
        for i in range(lens['nm']):
            eff = [[cols['k1'][i], cols['v1'][i]],
                   [cols['k2'][i], cols['v2'][i]],
                   [cols['k3'][i], cols['v3'][i]]]
            nodes[base + i] = dict(
                n=cols['nm'][i], t=cols['ti'][i], p=cols['p1'][i],
                q=cols['p2'][i], x=cols['ex'][i],
                e=[a for a in eff if a[0] > 0])

    depth = {}

    def dep(nid, seen=frozenset()):
        if nid in depth:
            return depth[nid]
        if nid in seen:          # 資料若出現環, 當成根而不是無限遞迴
            return 0
        p = nodes[nid]['p']
        depth[nid] = 0 if p == 0 else dep(p, seen | {nid}) + 1
        return depth[nid]

    for nid in nodes:
        nodes[nid]['d'] = dep(nid)

    full = sum(tcost[nodes[i]['t'] - 1] * tmax[nodes[i]['t'] - 1] for i in nodes)
    return dict(
        paths=[{'b': b, 'n': n, 'desc': pdesc[i], 'slot': slot[i]}
               for i, (b, n) in enumerate(PATHS)],
        keyname=kn, keyunit=ku, keysign=ks,
        tiermax=tmax, tiercost=tcost, tiername=tname,
        cap=56, full=full,
        nodes={str(k): v for k, v in sorted(nodes.items())})


CSS = """
<style>
  .sim-wrap{border:1px solid var(--rule);border-radius:10px;background:var(--paper);
    box-shadow:var(--shadow);overflow:hidden;margin-top:14px}
  .sim-bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;
    padding:10px 12px;background:var(--sunk);border-bottom:1px solid var(--rule)}
  .sim-bar button{font:inherit;font-size:.86rem;padding:5px 11px;border-radius:999px;
    border:1px solid var(--rule);background:var(--paper);color:var(--ink-soft);cursor:pointer}
  .sim-bar button:hover{border-color:var(--cinnabar);color:var(--cinnabar)}
  .sim-bar button[aria-pressed="true"]{background:var(--cinnabar);border-color:var(--cinnabar);
    color:var(--on-accent)}
  .sim-bar .spacer{flex:1 1 auto}
  .sim-pts{font-variant-numeric:tabular-nums;font-size:.9rem;color:var(--ink-soft)}
  .sim-pts b{color:var(--cinnabar);font-size:1.05rem}
  .sim-body{display:grid;grid-template-columns:minmax(0,1fr) 250px}
  @media (max-width:820px){.sim-body{grid-template-columns:minmax(0,1fr)}}
  .sim-canvas{overflow:auto;background:var(--ground);max-height:560px}
  .sim-canvas svg{display:block}
  .sim-side{border-left:1px solid var(--rule);padding:12px;font-size:.86rem;
    max-height:560px;overflow:auto}
  @media (max-width:820px){.sim-side{border-left:0;border-top:1px solid var(--rule)}}
  .sim-side h4{margin:0 0 6px;font-size:.8rem;letter-spacing:.06em;color:var(--ink-faint);
    text-transform:uppercase}
  .sim-side dl{display:grid;grid-template-columns:1fr auto;gap:2px 10px;margin:0 0 14px}
  .sim-side dt{color:var(--ink-soft);min-width:0;overflow:hidden;text-overflow:ellipsis;
    white-space:nowrap}
  .sim-side dd{margin:0;font-variant-numeric:tabular-nums;color:var(--cinnabar);font-weight:500}
  .sim-empty{color:var(--ink-faint)}
  .sim-tip{padding:8px 12px;border-top:1px solid var(--rule);background:var(--sunk);
    font-size:.8rem;color:var(--ink-faint)}
  .sim-axis{fill:var(--ink-faint);font-size:11px}
  .sim-link{stroke:var(--rule);stroke-width:2;fill:none}
  .sim-link.on{stroke:var(--cinnabar);stroke-width:2.5}
  .sim-link.alt{stroke-dasharray:4 3}
  .sim-node{cursor:pointer}
  .sim-node circle{fill:var(--paper);stroke:var(--ink-faint);stroke-width:2;
    transition:fill .12s,stroke .12s}
  .sim-node.on circle{fill:var(--cinnabar);stroke:var(--cinnabar)}
  .sim-node.max circle{stroke:#D8A21B;stroke-width:3}
  .sim-node.locked circle{stroke-dasharray:3 3;opacity:.5}
  .sim-node text.lbl{font-size:11px;fill:var(--ink-soft)}
  .sim-node.on text.lbl{fill:var(--ink)}
  .sim-node text.lv{font-size:10px;font-weight:700;fill:#D8A21B}
  .sim-node.t4 circle{stroke-width:3}
  .sim-node:focus{outline:none}
  .sim-node:focus circle{stroke:var(--focus);stroke-width:3}
</style>
"""

HTML = """
<section id="sim">
  <h2>互動星盤</h2>
  <p class="note">直接在盤上排點看看：<b>左鍵加一級、右鍵退一級</b>。規則跟遊戲裡一致——要有前置節點才點得到、總共只有 <b>56 點</b>、同群組的核心天賦只能擇一。橫軸是節點的深度，越往右越深。</p>
  <div class="sim-wrap">
    <div class="sim-bar" id="simTabs"></div>
    <div class="sim-body">
      <div class="sim-canvas" id="simCanvas"></div>
      <div class="sim-side">
        <h4>各道投入</h4>
        <dl id="simPaths"></dl>
        <h4>加成總計</h4>
        <dl id="simEff"></dl>
      </div>
    </div>
    <div class="sim-tip" id="simTip">點一個節點試試。配點會寫進網址，複製整條網址就能分享。</div>
  </div>
</section>
"""

JS_TEMPLATE = """
<script>
(function(){
  var D = __DATA__;
  var N = D.nodes, CAP = D.cap;
  var COLW = 132, ROWH = 62, PADX = 54, PADY = 34;
  var lv = {}, cur = 0;

  function tmax(id){ return D.tiermax[N[id].t - 1]; }
  function tcost(id){ return D.tiercost[N[id].t - 1]; }
  function used(){ var s=0; for(var k in lv){ s += lv[k]*tcost(k); } return s; }
  function pathUsed(b){ var s=0; for(var k in lv){ if(Math.floor(k/100)*100 === b) s += lv[k]*tcost(k); } return s; }
  function has(id){ return (lv[id]||0) > 0; }

  function preOK(id){
    var d = N[id];
    if(d.p === 0) return true;
    if(has(d.p)) return true;
    if(d.q > 0 && has(d.q)) return true;
    return false;
  }
  function exConflict(id){
    var g = N[id].x;
    if(!g) return 0;
    for(var k in lv){ if(k != id && N[k] && N[k].x === g && lv[k] > 0) return k; }
    return 0;
  }
  // 退點會不會讓別人斷線: 只有退到 0 級才可能
  function breaks(id){
    for(var k in lv){
      if(k == id || lv[k] <= 0) continue;
      var d = N[k];
      if(d.p != id && d.q != id) continue;
      var other = (d.p == id) ? d.q : d.p;
      if(other > 0 && has(other)) continue;
      return k;
    }
    return 0;
  }

  function layout(b){
    var ids = [], i;
    for(var k in N){ if(Math.floor(k/100)*100 === b) ids.push(k); }
    ids.sort(function(a,c){ return a-c; });
    var rows = {}, pos = {};
    for(i=0;i<ids.length;i++){
      var d = N[ids[i]].d;
      rows[d] = rows[d] || 0;
      pos[ids[i]] = { x: PADX + d*COLW, y: PADY + 26 + rows[d]*ROWH };
      rows[d]++;
    }
    var maxd = 0, maxr = 0;
    for(var dd in rows){ if(+dd > maxd) maxd = +dd; if(rows[dd] > maxr) maxr = rows[dd]; }
    return { ids: ids, pos: pos, w: PADX*2 + maxd*COLW + 90, h: PADY*2 + 26 + maxr*ROWH };
  }

  function esc(s){
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function draw(){
    var b = D.paths[cur].b, L = layout(b), i;
    var out = ['<svg width="'+L.w+'" height="'+L.h+'" viewBox="0 0 '+L.w+' '+L.h+'">'];

    // 深度刻度
    var seen = {};
    for(i=0;i<L.ids.length;i++){
      var dv = N[L.ids[i]].d;
      if(seen[dv]) continue;
      seen[dv] = 1;
      out.push('<text class="sim-axis" x="'+(PADX + dv*COLW)+'" y="18" text-anchor="middle">'+dv+'</text>');
    }

    // 連線
    for(i=0;i<L.ids.length;i++){
      var id = L.ids[i], d = N[id], a = L.pos[id];
      [[d.p,''],[d.q,' alt']].forEach(function(pair){
        var pid = pair[0];
        if(!pid || !L.pos[pid]) return;
        var s = L.pos[pid];
        var on = (has(pid) && has(id)) ? ' on' : '';
        out.push('<path class="sim-link'+pair[1]+on+'" d="M'+s.x+' '+s.y+' L'+a.x+' '+a.y+'"/>');
      });
    }

    // 節點
    for(i=0;i<L.ids.length;i++){
      var id2 = L.ids[i], n = N[id2], p = L.pos[id2];
      var cls = ['sim-node','t'+n.t];
      var cl = lv[id2] || 0;
      if(cl > 0) cls.push('on');
      if(cl >= tmax(id2)) cls.push('max');
      if(cl === 0 && !preOK(id2)) cls.push('locked');
      var r = n.t >= 3 ? 17 : 14;
      out.push('<g class="'+cls.join(' ')+'" data-id="'+id2+'" tabindex="0">');
      out.push('<title>'+esc(n.n)+' — '+esc(D.tiername[n.t-1])+'（每級 '+tcost(id2)+' 點，上限 '+tmax(id2)+' 級）</title>');
      out.push('<circle cx="'+p.x+'" cy="'+p.y+'" r="'+r+'"/>');
      out.push('<text class="lv" x="'+(p.x+r-2)+'" y="'+(p.y+r+1)+'">'+(cl||'')+'</text>');
      out.push('<text class="lbl" x="'+p.x+'" y="'+(p.y+r+15)+'" text-anchor="middle">'+esc(n.n)+'</text>');
      out.push('</g>');
    }
    out.push('</svg>');
    document.getElementById('simCanvas').innerHTML = out.join('');
  }

  function fmt(k, v){
    var sign = D.keysign[k-1] < 0 ? '-' : '+';
    var unit = D.keyunit[k-1] === 1 ? '%' : (D.keyunit[k-1] === 2 ? ' 毫秒' : '');
    return sign + v + unit;
  }

  function side(){
    var i, html = [];
    for(i=0;i<D.paths.length;i++){
      var u = pathUsed(D.paths[i].b);
      html.push('<dt>'+esc(D.paths[i].n)+'</dt><dd>'+u+'</dd>');
    }
    document.getElementById('simPaths').innerHTML = html.join('');

    var sum = {};
    for(var k in lv){
      if(lv[k] <= 0) continue;
      var e = N[k].e;
      for(i=0;i<e.length;i++){ sum[e[i][0]] = (sum[e[i][0]]||0) + e[i][1]*lv[k]; }
    }
    var keys = Object.keys(sum).sort(function(a,c){ return a-c; });
    if(!keys.length){
      document.getElementById('simEff').innerHTML = '<dt class="sim-empty">還沒點任何節點</dt><dd></dd>';
    } else {
      var h2 = [];
      for(i=0;i<keys.length;i++){
        var kk = +keys[i];
        h2.push('<dt>'+esc(D.keyname[kk-1])+'</dt><dd>'+fmt(kk, sum[kk])+'</dd>');
      }
      document.getElementById('simEff').innerHTML = h2.join('');
    }

    var u2 = used();
    document.getElementById('simUsed').innerHTML = '已用 <b>'+u2+'</b> / '+CAP+' 點';
  }

  function tip(msg){ document.getElementById('simTip').textContent = msg; }

  function add(id){
    var cl = lv[id] || 0;
    if(cl >= tmax(id)){ tip(N[id].n + ' 已經滿級了。'); return; }
    if(cl === 0 && !preOK(id)){
      var need = N[id].p;
      tip('要先點亮前置節點：' + (N[need] ? N[need].n : '大道之心') + '。');
      return;
    }
    if(cl === 0){
      var c = exConflict(id);
      if(c){ tip('與【' + N[c].n + '】互斥，同群組的核心天賦只能擇一。'); return; }
    }
    if(used() + tcost(id) > CAP){ tip('點數不夠了，你只有 ' + CAP + ' 點。'); return; }
    lv[id] = cl + 1;
    tip(N[id].n + ' → ' + lv[id] + ' 級。');
    sync();
  }

  function sub(id){
    var cl = lv[id] || 0;
    if(cl <= 0) return;
    if(cl === 1){
      var b = breaks(id);
      if(b){ tip('不能退——【' + N[b].n + '】要靠它連著。'); return; }
    }
    lv[id] = cl - 1;
    if(lv[id] === 0) delete lv[id];
    tip(N[id].n + ' → ' + (lv[id]||0) + ' 級。');
    sync();
  }

  function encode(){
    var a = [];
    var ks = Object.keys(lv).sort(function(x,y){ return x-y; });
    for(var i=0;i<ks.length;i++){ a.push(ks[i] + '.' + lv[ks[i]]); }
    return a.join('-');
  }
  function decode(s){
    lv = {};
    if(!s) return;
    var parts = s.split('-');
    for(var i=0;i<parts.length;i++){
      var kv = parts[i].split('.');
      var id = +kv[0], v = +kv[1];
      if(N[id] && v > 0 && v <= tmax(id)) lv[id] = v;
    }
  }

  function sync(){
    draw(); side();
    var h = encode();
    history.replaceState(null, '', h ? ('#b=' + h) : location.pathname);
  }

  function tabs(){
    var h = [], i;
    for(i=0;i<D.paths.length;i++){
      h.push('<button type="button" data-i="'+i+'" aria-pressed="'+(i===cur)+'">'+esc(D.paths[i].n)+'</button>');
    }
    h.push('<span class="spacer"></span>');
    h.push('<span class="sim-pts" id="simUsed"></span>');
    h.push('<button type="button" id="simReset">清空</button>');
    document.getElementById('simTabs').innerHTML = h.join('');
  }

  document.getElementById('simTabs').addEventListener('click', function(ev){
    var b = ev.target.closest('button');
    if(!b) return;
    if(b.id === 'simReset'){ lv = {}; tip('已清空。'); sync(); return; }
    cur = +b.dataset.i;
    tabs(); sync();
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
  tabs(); sync();
})();
</script>
"""


def main():
    text = read_source()
    data = build_data(text)
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    block = BEGIN + CSS + HTML + JS_TEMPLATE.replace('__DATA__', payload) + END

    with open(OUT, encoding='utf-8') as f:
        page = f.read()

    if BEGIN in page and END in page:
        i = page.index(BEGIN)
        j = page.index(END) + len(END)
        page = page[:i] + block + page[j:]
        where = '覆寫既有區塊'
    else:
        anchor = '  </section>\n'
        if anchor not in page:
            sys.exit('找不到插入錨點, 請手動放上 %s / %s 標記' % (BEGIN, END))
        i = page.index(anchor) + len(anchor)
        page = page[:i] + '\n' + block + '\n' + page[i:]
        where = '首次插入'

    out = page.encode('utf-8')
    with open(OUT, 'wb') as f:
        f.write(out)

    print('節點 %d  點滿 %d 點  上限 %d 點' % (len(data['nodes']), data['full'], data['cap']))
    print('資料 %d bytes, 區塊 %d bytes' % (len(payload), len(block)))
    print('%s -> %s (%d bytes)' % (where, OUT, len(out)))


if __name__ == '__main__':
    main()

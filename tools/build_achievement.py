# -*- coding: utf-8 -*-
"""產生 achievement.html —— 天命成就稱號圖鑑。

資料來源是遊戲腳本本身, 不另外維護一份:
    2.開機擋/script/13.天命成就/00.設定.txt
取六個 setarray 陣列(各 150 筆, 索引 0~149):
    $@ACH_NAME$  稱號名        $@ACH_RAR   稀有度 1~7
    $@ACH_CATE$  分類          $@ACH_PTS   天命點
    $@ACH_COND$  取得條件      $@ACH_HIDE  是否隱藏成就
以及 $@ACH_RARNM$ / $@ACH_RARCL$ (索引 1~7) 的稀有度名稱與顏色。

★ 隱藏成就只公開「分類」與「稀有度」, 名稱與條件留白。
  遊戲內圖鑑的規則就是未解鎖前只顯示「？？？？？？」(企劃書 §5), 網頁沒有
  個別玩家狀態, 所以一律當成未解鎖處理 —— 這是與使用者確認過的方案 B。

★ CSS 直接取用 potential.html 的 <style> 區塊, 不再抄一份。
  站上其他頁是各自內嵌一份, 但那樣改樣式要改六個地方; 這裡改成引用,
  potential.html 一改這頁跟著一致。

用法: python tools/build_achievement.py
"""
import io
import os
import re
import sys
import html

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.dirname(HERE)
SRC = os.path.join(
    WEB, "..", "..", "2.開機擋", "script", "13.天命成就", "00.設定.txt")
STYLE_FROM = os.path.join(WEB, "potential.html")
DEST = os.path.join(WEB, "achievement.html")

N = 150


def read(path, enc="utf-8"):
    with io.open(path, encoding=enc) as f:
        return f.read()


def strip_comments(s):
    """去掉 // 行註解。這幾個陣列的字串裡沒有 //。"""
    return re.sub(r"//[^\n]*", "", s)


def parse_array(text, name, is_str):
    """setarray 是分段宣告的(NAME$ 38 段 / COND$ 50 段), 每段自帶起始索引。"""
    out = {}
    pat = re.compile(
        r"setarray\s+\S*@" + re.escape(name) + r"\[(\d+)\]\s*,(.*?);", re.S)
    for m in pat.finditer(text):
        base = int(m.group(1))
        body = strip_comments(m.group(2))
        if is_str:
            vals = re.findall(r'"([^"]*)"', body)
        else:
            vals = [int(x) for x in re.findall(r"-?\d+", body)]
        for k, v in enumerate(vals):
            out[base + k] = v
    return out


def main():
    text = read(SRC)

    name = parse_array(text, "ACH_NAME$", True)
    cate = parse_array(text, "ACH_CATE$", True)
    cond = parse_array(text, "ACH_COND$", True)
    rar = parse_array(text, "ACH_RAR", False)
    pts = parse_array(text, "ACH_PTS", False)
    hide = parse_array(text, "ACH_HIDE", False)
    rarnm = parse_array(text, "ACH_RARNM$", True)
    rarcl = parse_array(text, "ACH_RARCL$", True)

    for label, d in (("NAME$", name), ("CATE$", cate), ("COND$", cond),
                     ("RAR", rar), ("PTS", pts), ("HIDE", hide)):
        if len(d) != N or min(d) != 0 or max(d) != N - 1:
            sys.exit("$@ACH_%s 解析出 %d 筆 (索引 %s~%s), 應為 %d 筆 0~%d"
                     % (label, len(d), min(d) if d else "-",
                        max(d) if d else "-", N, N - 1))
    if len(rarnm) != 7 or len(rarcl) != 7:
        sys.exit("稀有度表解析異常: 名稱 %d 筆 / 顏色 %d 筆"
                 % (len(rarnm), len(rarcl)))

    hidden_n = sum(1 for i in range(N) if hide[i])
    cats = sorted({cate[i] for i in range(N)})
    rar_count = {r: sum(1 for i in range(N) if rar[i] == r) for r in range(1, 8)}

    rows = []
    for i in range(N):
        h = bool(hide[i])
        r = rar[i]
        nm = "？？？？？？" if h else name[i]
        cd = "" if h else cond[i]
        rows.append(
            '<tr data-r="%d" data-c="%s" data-h="%d">'
            '<td class="num">%03d</td>'
            '<td class="nm%s" style="color:#%s">%s</td>'
            '<td>%s</td>'
            '<td class="num"><span class="rar" style="background:#%s1F;color:#%s">%s</span></td>'
            '<td class="cond">%s</td>'
            '<td class="num">%s</td></tr>'
            % (r, html.escape(cate[i]), 1 if h else 0,
               i + 1,
               " masked" if h else "", rarcl[r], html.escape(nm),
               html.escape(cate[i]),
               rarcl[r], rarcl[r], html.escape(rarnm[r]),
               html.escape(cd) if cd
               else '<span class="masked">隱藏成就 · 條件不公開</span>',
               "{:,}".format(pts[i])))

    rar_btns = "".join(
        '<button type="button" data-r="%d" style="--c:#%s">%s<i>%d</i></button>'
        % (r, rarcl[r], html.escape(rarnm[r]), rar_count[r])
        for r in range(1, 8))
    cat_btns = "".join(
        '<button type="button" data-c="%s">%s</button>'
        % (html.escape(c), html.escape(c)) for c in cats)

    style = re.search(r"<style>.*?</style>", read(STYLE_FROM), re.S)
    if not style:
        sys.exit("potential.html 裡找不到 <style> 區塊")
    style = style.group(0)

    extra = """
<style>
.rar{display:inline-block;padding:1px 8px;border-radius:999px;font-weight:700;font-size:.86em;white-space:nowrap}
.nm{font-weight:700}
.masked{color:var(--ink-faint);font-weight:400}
.cond{font-size:.94em;color:var(--ink-soft)}
.ctl-row button i{font-style:normal;opacity:.6;margin-left:.4em;font-size:.85em}
.ctl-row button[data-r]{border-left:3px solid var(--c)}
</style>
"""

    rar_rows = "".join(
        '<tr><td><span class="rar" style="background:#%s1F;color:#%s">%s</span></td>'
        '<td class="num">%d</td><td>%s</td></tr>'
        % (rarcl[r], rarcl[r], html.escape(rarnm[r]), rar_count[r],
           "全服公告" if r >= 5 else ("周圍" if r == 4 else "只通知本人"))
        for r in range(1, 8))

    doc = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>天命成就稱號圖鑑</title>
<meta name="description" content="神域仙境 天命成就的 150 個稱號、分類、稀有度與取得條件。">
<meta name="color-scheme" content="light dark">
<meta property="og:type" content="website">
<meta property="og:site_name" content="神域仙境">
<meta property="og:title" content="天命成就稱號圖鑑">
<meta property="og:description" content="神域仙境 天命成就的 150 個稱號、分類、稀有度與取得條件。">
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
    <h1>天命成就稱號圖鑑</h1>
    <p class="lede">天命成就共 <b>150 個稱號</b>，分成 <b>__NCAT__ 類</b>、七個稀有度。達成條件後成就會「完成」，要到<b>成就視窗按下領取</b>才會拿到稱號 —— 領取之後就能在裝備面板的稱號下拉直接選用。</p>
  </header>

  <section>
    <h2>稀有度</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>稀有度</th><th class="num">數量</th><th>解鎖時的公告範圍</th></tr></thead>
        <tbody>__RARROWS__</tbody>
      </table>
    </div>
    <p class="note">白、綠、藍只通知本人；紫色會通知周圍的人；金色以上全服公告。</p>
  </section>

  <section>
    <h2>稱號一覽</h2>
    <div class="controls">
      <div class="ctl-row">
        <input id="q" class="search" type="search" placeholder="搜尋稱號或條件…　例：突破、擊殺、鎖妖塔" aria-label="搜尋稱號">
      </div>
      <div class="ctl-row">
        <span class="glab">稀有度</span>
        <div id="rar" class="ctl-row" role="group" aria-label="稀有度">__RARBTN__</div>
      </div>
      <div class="ctl-row">
        <span class="glab">分類</span>
        <div id="cat" class="ctl-row" role="group" aria-label="分類">__CATBTN__</div>
      </div>
      <p class="tally" id="tally"></p>
    </div>
    <div class="tbl-wrap">
      <table id="tbl">
        <thead><tr><th class="num">編號</th><th>稱號</th><th>分類</th><th class="num">稀有度</th><th>取得條件</th><th class="num">天命點</th></tr></thead>
        <tbody>__ROWS__</tbody>
      </table>
    </div>
    <p class="note">其中 <b>__NHIDE__ 個是隱藏成就</b>，名稱與條件不公開，只列出分類與稀有度 —— 與遊戲內圖鑑一致（未解鎖前顯示「？？？？？？」）。自己解鎖之後，遊戲裡就看得到完整內容。</p>
    <p class="note">「天命點」是累計用的分數，累積到門檻會解鎖里程碑加成 —— 里程碑一覽請在遊戲裡找<b>天命碑</b>（崑崙 151,131／斐揚 142,203，或直接打 <code>@ach</code>）。</p>
  </section>

  <footer class="foot">
    <p>資料直接取自伺服器腳本 <code>script/13.天命成就/00.設定.txt</code>，由 <code>tools/build_achievement.py</code> 產生。</p>
  </footer>
</div>

<script>
(function(){
  var tbl=document.getElementById('tbl'), q=document.getElementById('q'),
      tally=document.getElementById('tally'),
      rows=[].slice.call(tbl.tBodies[0].rows),
      selR=null, selC=null;

  function bind(box, key, get, set){
    box.addEventListener('click', function(e){
      var b=e.target.closest('button'); if(!b) return;
      var v=b.getAttribute(key);
      if(get()===v){ set(null); b.classList.remove('on'); }
      else{
        [].forEach.call(box.querySelectorAll('button'),function(x){x.classList.remove('on');});
        set(v); b.classList.add('on');
      }
      apply();
    });
  }
  bind(document.getElementById('rar'),'data-r',function(){return selR;},function(v){selR=v;});
  bind(document.getElementById('cat'),'data-c',function(){return selC;},function(v){selC=v;});

  function apply(){
    var s=q.value.trim().toLowerCase(), n=0;
    rows.forEach(function(tr){
      var ok=true;
      if(selR && tr.getAttribute('data-r')!==selR) ok=false;
      if(ok && selC && tr.getAttribute('data-c')!==selC) ok=false;
      if(ok && s && tr.textContent.toLowerCase().indexOf(s)<0) ok=false;
      tr.hidden=!ok; if(ok) n++;
    });
    tally.textContent='顯示 '+n+' / '+rows.length+' 個稱號';
  }
  q.addEventListener('input', apply);
  apply();
})();
</script>
</body>
</html>
"""

    doc = (doc.replace("__STYLE__", style)
              .replace("__EXTRA__", extra)
              .replace("__RARROWS__", rar_rows)
              .replace("__RARBTN__", rar_btns)
              .replace("__CATBTN__", cat_btns)
              .replace("__ROWS__", "".join(rows))
              .replace("__NCAT__", str(len(cats)))
              .replace("__NHIDE__", str(hidden_n)))

    with io.open(DEST, "w", encoding="utf-8", newline="\n") as f:
        f.write(doc)

    print("稱號 %d 個, 分類 %d 類, 隱藏 %d 個" % (N, len(cats), hidden_n))
    print("稀有度: " + ", ".join(
        "%s %d" % (rarnm[r], rar_count[r]) for r in range(1, 8)))
    print("已寫出 %s (%d bytes)" % (DEST, os.path.getsize(DEST)))


if __name__ == "__main__":
    main()

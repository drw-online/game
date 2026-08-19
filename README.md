# 神域仙境 玩家工具

給玩家查資料的靜態網站。純 HTML，沒有後端、沒有建置工具、沒有相依套件。

**網址**：https://drw-online.github.io/game/

| 頁面 | 內容 |
|---|---|
| `index.html` | 入口頁，列出所有工具 |
| `runewords.html` | 符文之語圖鑑 — 33 種符文、290 組組合 |
| `potential.html` | 裝備潛能詞條表 — 5 個部位池、190 條詞條 |
| `petaffix.html` | 寵物詞條與星級 — 40 種能力、★3→★9 升階表 |

---

## 結構慣例

**一頁一個 `.html`，全部平放在同一層，不開子資料夾。**

新增一頁 = 丟一支新的 `.html` 進來 + 在 `index.html` 的清單加一項。不用改結構，舊連結不會壞。

```
index.html          入口頁
runewords.html      ┐
potential.html      ├ 各工具頁，彼此獨立
petaffix.html       ┘
logo.webp           站台 logo（去背 440px，入口頁與各頁的回首頁鈕共用）
favicon.png         瀏覽器分頁圖示（64px）
og.jpg              貼 Discord / 社群時的連結預覽圖（600px，紙色底）
logo.jpg            原始 logo（1254px 白底），只是來源檔，頁面不引用
```

每一頁都是**自帶資料的單一檔案** — 資料以 JSON 直接內嵌在 `<script>` 裡，除了 Google Fonts 沒有任何外部請求。所以單獨開一支 `.html` 也能正常運作。

---

## 資料從哪來

**頁面內容不是手打的**，是從伺服器實際設定與規格書解析出來的。改了來源之後要重跑產生器，不要直接編輯 `.html` 裡的資料。

| 頁面 | 來源 |
|---|---|
| `runewords.html` | `2.開機擋/db/import/item_combos.yml`（290 組的符文與組合名）<br>`2.開機擋/db/import/blackgod/item_rune.yml`（33 種符文的 ID 與中文名）<br>`符文之語/*.xlsx`（適用裝備、定位、效果文字） |
| `potential.html` | `2.開機擋/script/04.系統/22.裝備潛能.txt` 的 `$@BGP_*` 五個詞條池與 `$@BGP_OptWeight*` |
| `petaffix.html` | `2.開機擋/script/04.系統/30.寵物詞條.txt` 的 `$@PETAB_*` 與 `$@PETUP_*` |

解析時踩過的坑，改產生器前先看一眼：

* **陣列最後一項的尾註會被吃掉。** 腳本的 `setarray` 最後一項以分號結尾，用非貪婪比對 `(.*?);` 會在那個分號截斷，把最後一條的 `// 說明` 切掉 —— 五個詞條池會各少一條，變成 185 而不是 190。要**逐行解析**並認 `[,;]` 分隔。
* **重複符文是合法資料。** 04冊的「神聖結界」是 `光+光+神+魂`、「冥界障壁」是 `闇+闇+魂+玄`，規格書原文就這樣寫，代表要插兩張同符文，不是轉錄錯誤。用 `set()` 去重會把洞數算錯。
* **名稱跨冊重複也是正常的。** 有 11 個組合名重複（「長生」出現 3 次），是規格書逐冊獨立設計的結果。

---

## 更新流程

改完來源資料、重跑產生器覆蓋 `.html` 之後：

```bash
cd "H:/91.神域仙境/符文之語/web"
git add -A
git commit -m "更新符文之語資料"
git push
```

推完之後 **GitHub Pages 會自動重新部署**，不必再做任何事。但要注意：

* 建置通常 1～3 分鐘，偶爾會拖到 5 分鐘以上。**推完立刻開網頁看到的是舊版是正常的**，不是失敗。
* 要確認新版真的上線，抓一個「新版才有的檔案或內容」來測，不要只看首頁回 200 —— 舊檔還在的話一樣回 200。

### 加一頁新的

1. 產生 `新頁面.html`，放進這個資料夾
2. 在 `index.html` 的 `<ul class="tools">` 裡照既有格式加一個 `<li class="tool">`
3. 新頁面記得加回首頁連結（頁首 logo + 頁尾各一個），照既有頁面複製
4. commit、push

---

## Git 帳號設定

這個 repo 用**專屬帳號** `drw-online`，與本機其他專案用的主帳號分開。兩件事讓它們不互相干擾：

**1. 憑證按 repo 路徑分開存**（全域設定，已設好，只需設一次）

```bash
git config --global credential.useHttpPath true
```

Windows 的 Git Credential Manager 預設**只按主機名**記憑證，也就是 `github.com` 只會記住一組帳號 —— 沒有這行的話，推這個 repo 會拿主帳號的憑證去認證，得到：

```
remote: Permission to drw-online/game.git denied to <主帳號>.
fatal: ... The requested URL returned error: 403
```

設定之後憑證鍵變成 `github.com/drw-online/game.git`，兩個帳號各記各的，主帳號的登入也不必刪掉。

**2. 身分只設在這個 repo，不要動全域**

```bash
git -C "H:/91.神域仙境/符文之語/web" config user.name  "..."
git -C "H:/91.神域仙境/符文之語/web" config user.email "..."
```

commit 顯示成誰，看的是 **email 不是帳號名** —— 拿主帳號的 email 提交到這裡，GitHub 會把那筆 commit 算在主帳號頭上。

### 換過用戶名要注意

GitHub 改用戶名之後，**repo 網址會自動轉址，但 Pages 網址不會**。而且 repo 的轉址只在「沒人搶註舊用戶名」的前提下有效。所以改名後要立刻：

```bash
git remote set-url origin https://github.com/<新名>/game.git
```

而且憑證鍵也跟著變了，**下一次 push 會重新問一次授權**，那是正常的，授權一次之後就記住。

---

## 授權時選錯帳號的話

GCM 跳出的授權視窗如果走瀏覽器，會直接沿用瀏覽器**當下的登入狀態** —— 主帳號登著就會用主帳號授權，再錯一次。兩個解法：

* 先開無痕視窗登入 `drw-online`，再執行 push
* 或改用 Personal Access Token（Settings → Developer settings → Fine-grained tokens，該 repo 的 **Contents: Read and write**），在對話框選 Token 那項貼上去，完全不經瀏覽器

---

## 其他

* repo 必須是 **public** —— 免費帳號的 GitHub Pages 只支援 public repo。
* 這裡沒有任何機敏資料：純靜態頁、沒有後端、沒有帳密、沒有伺服器位址，只有遊戲設定資料。
* Pages 設定：Settings → Pages → Source 選 `Deploy from a branch`，Branch `main` + `/ (root)`。

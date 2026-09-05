# 神域仙境 玩家工具

給玩家查資料的靜態網站。純 HTML，沒有後端、沒有建置工具、沒有相依套件。

**網址**：https://drw-online.github.io/game/

| 頁面 | 內容 |
|---|---|
| `index.html` | 入口頁，列出所有工具 |
| `runewords.html` | 符文之語圖鑑 — 33 種符文、290 組組合、掉落與煉化的取得方式 |
| `potential.html` | 裝備潛能詞條表 — 5 個部位池、193 條詞條、六支道具的差別 |
| `petaffix.html` | 寵物詞條與星級 — 41 種能力、★3→★9 升階表、升等與六維配點 |
| `daopan.html` | 大道星盤天賦樹 — 六大道 141 個節點、12 個核心天賦、56 點的配點上限 |
| `pets.html` | 神域寵物圖鑑 — 靈獸島 162 種寵物的編號、外觀、魔物編號與蛋編號 |
| `mobs.html` | 靈獸島魔物圖鑑 — 352 隻的數值與掉落（190 隻 MVP + 162 種神域魔物）、全圖共通掉落 |
| `wanfa.html` | 萬法星盤 — 55 個節點的觸發技能、機率、冷卻與傷害倍率，8 顆主星共鳴 |
| `skillstone.html` | 技能石技能表 — 1/2/3/4 轉技能石各自的抽取池，1095 支技能的圖示、中文名、職業與上限 |

---

## 結構慣例

**一頁一個 `.html`，全部平放在同一層。**

子資料夾只放兩類東西：**頁面沒辦法塞進單一檔案的圖**（`pets/` 神域寵物外觀、`digimon/` 數碼寶貝外觀、`skills/` 技能圖示），以及 `tools/`（產生器，不是頁面內容，發布出去也無害）。除此之外不要再開新的子資料夾。

新增一頁 = 丟一支新的 `.html` 進來 + 在 `index.html` 的清單加一項。不用改結構，舊連結不會壞。

```
index.html          入口頁
runewords.html      ┐
potential.html      │
petaffix.html       ├ 各工具頁，彼此獨立
daopan.html         │
pets.html           │
mobs.html           │
wanfa.html          │
skillstone.html     ┘
pets/               神域寵物圖鑑的 162 張外觀圖（drwmob001.png ~ drwmob162.png，共約 920 KB）
skills/             技能石技能表的 1093 個技能圖示（24x24 PNG，共約 830 KB）
tools/              產生器。build_pets.py（產 pets.html 與 pets/）、build_mobs.py（產 mobs.html）、
                    build_wanfa.py（產 wanfa.html）、build_skillstone.py（產 skillstone.html 與 skills/）
logo.webp           站台 logo（去背 440px，入口頁與各頁的回首頁鈕共用）
favicon.png         瀏覽器分頁圖示（64px）
og.jpg              貼 Discord / 社群時的連結預覽圖（600px，紙色底）
logo.jpg            原始 logo（1254px 白底），只是來源檔，頁面不引用
```

每一頁都是**自帶資料的單一檔案** — 資料以 JSON 直接內嵌在 `<script>` 裡，除了 Google Fonts 沒有任何外部請求。所以單獨開一支 `.html` 也能正常運作。

`pets.html` 是例外：資料直接寫成靜態的 `<li>`（不靠 JS 就看得到），但外觀圖要讀同層的 `pets/`，所以它必須跟那個資料夾放在一起才看得到圖。

---

## 資料從哪來

**頁面內容不是手打的**，是從伺服器實際設定與規格書解析出來的。改了來源之後要重新解析，不要憑印象改 `.html` 裡的數字。

| 頁面 | 來源 |
|---|---|
| `runewords.html` | `2.開機擋/db/import/item_combos.yml`（290 組的符文與組合名）<br>`2.開機擋/db/import/blackgod/item_rune.yml`（33 種符文的 ID、中文名與階級區段）<br>`2.開機擋/script/04.系統/42.符文掉落.txt`（開放的洞天與掉率）<br>`2.開機擋/script/04.系統/16.符文煉化.txt` 的 `$@RR_*`（四道工序與材料）<br>`符文之語_去重複版/*.xlsx`（定位、效果文字。**「適用裝備」欄不採用** —— item_combos.yml 的 290 組 `Combo` 只列符文、沒有任何裝備，`SameItem: true` 也只要求「同一件裝備湊齊」而不指定哪一件，實際上不限部位）——<br>2026-08-27 起以此為準，舊的 `符文之語/*.xlsx` 有 19 群配方撞號 |
| `potential.html` | `2.開機擋/script/04.系統/22.裝備潛能.txt` 的 `$@BGP_*` 五個詞條池與 `$@BGP_OptWeight*`；**效果文字取自同檔的 `$@BGP_OptFmt$`**（客戶端 tooltip 原文，NPC 也是印這張表）——<br>2026-08-27 之前誤用詞條池的開發註解，45 筆與遊戲內用字不符<br>同檔 `F_BGP_Enchant` 檔頭的六支道具與旗標；`db/import/blackgod/item_vipmat.yml` 是實際的呼叫端 |
| `petaffix.html` | `2.開機擋/script/04.系統/30.寵物詞條.txt` 的 `$@PETAB_*`、`$@PETUP_*`、`$@PET_DIGI_*`<br>`2.開機擋/conf/battle/blackgod.conf` 的 `pet_gain_exp_rate` / `pet_levelup_point` / `pet_max_level` / `pet_bonus_point_class_*`（升等與配點） |
| `pets.html` | `2.開機擋/db/import/blackgod/pet_drwmob.yml`（162 筆的 `Mob` 與 `EggItem`）<br>`2.開機擋/db/import/blackgod/mob_drwmob.yml`（魔物編號與 `JapaneseName`，遊戲內顯示的是這欄）<br>`2.開機擋/db/import/blackgod/item_petegg_drwmob.yml`（寵物蛋編號）<br>外觀圖來自客戶端 `3.客戶端/old/data09/<몬스터>/drwmob001~162.spr｜act`<br>**這一頁有產生器**：`python tools/build_pets.py` |
| `daopan.html` | `2.開機擋/script/04.系統/70.大道星盤.txt` 的 `OnInit` 八張節點表（`$@dao_name$` / `tier` / `pre` / `pre2` / `ex` / `ek1~3` / `ev1~3`）、分級表 `$@dao_tmax` `$@dao_tcost`、效果對照 `$@dao_kn$` `$@dao_ku` `$@dao_ks`、境界配點 `$@dao_grant`、常數 `$@DAO_*`<br>`2.開機擋/script/04.系統/12.境界突破.txt` 的 `$@realm_name$`（十三境的名字） |
| `mobs.html` | `2.開機擋/script/05.魔物/13.靈獸島.txt`（352 隻的生成清單，這是權威名單）<br>`2.開機擋/script/04.系統/56.靈獸島入口.txt` 的 `$@BN_FEE`（入場費）<br>`2.開機擋/db/import/blackgod/mob_bossnia.yml`（190 隻 MVP 本體）<br>`2.開機擋/db/import/blackgod/mob_drwmob.yml`（162 種神域魔物本體）<br>**掉落是四層疊加**：本體的 `Drops` + `mob_skillstone.yml`（1轉技能石）+ `mob_drwmob_mvpcoin.yml`（MVP硬幣）+ `db/import/map_drops.yml` 的 `bossnia_01`（2~4轉技能石）—— 少讀一支就會漏，`Drops` 是附加不是取代<br>物品中文名取自 `db/re/item_db_*.yml` 與 `db/import/blackgod/item_*.yml`（本服的 item_db 本身就是中文）<br>⚠ 兩邊 Rate 分母不同：mob_db 是 10000，map_drops 看 `Header.Version`（2=十萬 3=百萬）<br>**這一頁有產生器**：`python tools/build_mobs.py` |
| `wanfa.html` | `2.開機擋/script/04.系統/73.萬法星盤.txt` 的 `OnInit` —— 13 張平行 `setarray`（`$@wf_name$` / `ring` / `route` / `pre` / `skill` / `bf` / `icd` / `dmg` / `flag` / `rate` / `rinc` / `slv` / `sinc`），主星另有 `$@wf_cr1` `cr2` `cbon`；參數 `$@WF_PT_MAX` `COST_*` `CUM[]` `ITEM_*`；配點表 `$@wf_grant` `$@wf_syg`<br>`2.開機擋/script/10.鎖妖塔/00.設定.txt` 的 `$@SY_MAXFLOOR`（決定「目前實際拿得到幾點」）<br>技能中文名取 `skill_db.yml` 的 **`Description`**（`Name` 是 AegisName），同時比對 `MaxLevel`<br>`2.開機擋/conf/battle/blackgod.conf` 的 `astrolabe_pvp_proc_rate` / `astrolabe_pvp_damage_rate`<br>⚠ 抓 `setarray` 的 regex **必須帶 `setarray` 前綴** —— NPC 那段也在讀同一批陣列，少了前綴會把「使用」當「定義」抓進來且不報錯<br>**這一頁有產生器**：`python tools/build_wanfa.py` |
| `skillstone.html` | `5.技能圖片/技能書對照表.csv`（1095 本技能書的物品ID / **階級** / 技能代號 / 上限 / 職業 / 圖示檔名 —— 這是主幹）<br>`5.技能圖片/技能圖示對應表.csv`（中文名稱與英文名，以技能代號 join）<br>`5.技能圖片/*.bmp`（24x24 圖示，洋紅 `255,0,255` 是去背色；1093 個裡有 824 個用它，其餘本來就是不透明深色底）<br>`2.開機擋/db/import/blackgod/item_skillbook.yml`（真正的物品 DB，用來驗證 CSV 沒過期）<br>`2.開機擋/script/04.系統/05.技能書.txt` 的 `$@SKB_TIER` / `$@SKB_BASE` / `$@SKB_LEN`（**這才是伺服器真正的抽取池**，`F_SkillStone` 照它均勻隨機）<br>`2.開機擋/conf/atcommands.yml` 的 `@job` 說明表（中文職業名，玩家 `@help job` 看到的就是這份）+ `1.原始碼/src/common/mmo.hpp` 的 `enum e_job`（把 CSV 的英文職業接到職業編號）<br>⚠ **階級只認「階級」欄，不看「原始分類」也不用物品 ID 前綴推** —— 2026-08-16 有 46 本二轉技能原本被歸在 1 轉，兩欄至今仍有 46 筆不一致，那是正確的歷史痕跡<br>⚠ 圖示檔名用 `技能書對照表` 的「圖示」欄，不用 `技能圖示對應表` 的「圖片檔名」（後者有兩筆是空的）<br>**這一頁有產生器**：`python tools/build_skillstone.py` |

### ⚠ 產生器已經不在了（`pets.html` / `mobs.html` / `wanfa.html` / `skillstone.html` 除外）

**`pets.html` 有產生器**，在 `tools/build_pets.py`：解析三支 YAML → 把客戶端 sprite 轉成 PNG → 寫出 `pets.html` → **自己反向解析驗證一次**。輸出是決定性的，來源沒變的話重跑一次 `git status` 應該是乾淨的 —— 這同時就是它的回歸測試，改完務必跑一次確認。

**`mobs.html` 也有產生器**，在 `tools/build_mobs.py`（需要 PyYAML）：解析生成清單與四層掉落 → 寫出 `mobs.html` → 跑完自己驗證一次（352 隻、機率、掉落物是否全部對到中文名）。同樣是決定性輸出，改完重跑一次確認。

**`wanfa.html` 也有產生器**，在 `tools/build_wanfa.py`（需要 PyYAML）：解析 `OnInit` 的 13 張平行表 → 寫出 `wanfa.html` → 跑完自己驗證一次（表格逐格對齊、各環節點數、技能等級沒超過 `MaxLevel`、星環與路線名稱是中文而不是程式碼碎片）。同樣是決定性輸出。

**`skillstone.html` 也有產生器**，在 `tools/build_skillstone.py`（需要 Pillow）：兩支 CSV join → 把 1093 個 `.bmp` 圖示洋紅去背轉成 `skills/*.png` → 寫出 `skillstone.html` → 跑完自己驗證一次。驗證裡最重要的一項是**拿 `05.技能書.txt` 的 `$@SKB_*` 號段反過來核對每一階的池子** —— 號段表改了而 CSV 沒重出的話，這裡會當場失敗。同樣是決定性輸出（連 PNG 的位元組都一樣）。

其餘四頁沒有。README 原本寫「改完來源要重跑產生器」，但那支產生器**沒有留下來** —— repo 裡沒有，專案其他地方也沒有。
2026-08-25 這次更新是**逐頁寫一次性腳本、直接改 `.html`** 完成的：解析來源 → 覆寫內嵌 JSON 或表格 → 再反過來解析改完的 `.html` 與來源逐項比對。

下次更新照同樣的做法就好，但**一定要留下驗證那一步** —— 直接改 HTML 最容易出的錯是「改了 A 忘了改 B」（表格改了、lede 的數字沒改、`<title>` 沒改），只有把改完的頁面重新解析回來跟來源對，才抓得到。

解析時踩過的坑，改產生器前先看一眼：

* **陣列最後一項的尾註會被吃掉。** 腳本的 `setarray` 最後一項以分號結尾，用非貪婪比對 `(.*?);` 會在那個分號截斷，把最後一條的 `// 說明` 切掉 —— 五個詞條池會各少一條，變成 185 而不是 190。要**逐行解析**並認 `[,;]` 分隔。
* **重複符文的比對一律用計數（multiset），不要用 `set()`。**〔2026-08-27：資料面已消失 —— 去重複版把「神聖結界」改成 `光+日+神+魂`、「冥界障壁」改成 `闇+月+魂+玄`，現在 290 組全都沒有重複符文。但下面這個坑咬過兩次，程式碼請維持 multiset 寫法。〕
  原本 04冊的「神聖結界」是 `光+光+神+魂`、「冥界障壁」是 `闇+闇+魂+玄`，規格書原文就這樣寫，代表要插兩張同符文，不是轉錄錯誤。用 `set()` 去重會把洞數算錯。
  * **這個坑咬過兩次。** 2026-08-27 發現「另觸發」那一欄（同日稍後改名為「蓋過」）也中招 —— 算子集時把符文清單去重了，於是只有一張光的組合被判定成也能觸發要兩張光的「神聖結界」，共 9 筆是假的。伺服器端不是這樣算的：`pc_checkcombo_sameitem`（`src/map/pc.cpp`）用 `card_used[]` 把每張實體卡標記為已消耗，註解寫死「組合寫 `[4001, 4001]` 就真的要兩張插在不同槽」。**凡是拿符文清單做比對的地方，一律用計數（multiset）不要用集合。**
* **名稱跨冊重複已經沒有了。**〔2026-08-27〕原本有 11 個組合名重複（「長生」出現 3 次），去重複版把短名擴成長名解掉（`天罰` → `雷劫天罰`）。現在 290 個名字互不重複。
* **停用的設定是註解掉、不是刪掉。** `$@PETUP_MAT`（升階要的善惡晶核）在 2026-08-25 停用，做法是把整行 `//` 掉並留在原處。解析時抓不到它要當成「這項需求不存在」，不能當成解析失敗 —— 抓不到就報錯的話，會一直修不好一個根本沒壞的解析器。
* **註解裡的方括號是寫給開發看的，不要印到頁面上。** 來源的 `// 法術爆傷 +1~40%   [2026-08-25 新增, 164 的魔法版]`，方括號那段要去掉。圓括號的 `(合併 1000~10000 與 3000~15000)` 相反，那是給玩家的說明，要留著。
* **大道星盤有五格效果是「填正數代表改善」。** `$@dao_ks` 裡 16（技能後延遲）、26（受到 Boss 傷害）、30（固定詠唱）、31（變動詠唱）是 `-1`，資料表填 `3` 要顯示成 `-3%`。照抄數字會把減延遲寫成加延遲，而且看起來完全正常。移動速度（17）**不在**這一組，它填正數就是正數。
* **節點的等級上限與每級點數不在節點表裡。** 逐節點找 `max_level` 會一無所獲 —— 它們由 tier 查 `$@dao_tmax` / `$@dao_tcost` 得到，同類型一律相同。
* **「56 點最多拿 2 個核心」是錯的，實際是 3 個。** 同一條道的兩個核心**共用整條前置鏈**，只要不同互斥群組就能一起拿（守道走到 22 點拿第一個，第二個只要再 6 點）。最省的三核心組合是不動明王＋金剛怒目＋血祭大道，合計 50 點。要下這種結論一定要實際跑組合搜尋，不要用「單一核心成本 × 個數」估。
* **神域寵物的外觀圖是從客戶端 sprite 轉出來的，`spr` 有兩種版本、`act` 也有兩種。** 162 隻裡 `spr 2.1`（索引格 RLE 壓縮）122 隻、`spr 2.0`（索引格未壓縮）40 隻；`act 2.5` 157 隻、`act 2.3` 5 隻（差在 `scaleY` 與 `width/height` 兩個欄位）。只寫其中一種版本的解析會在中途炸掉，而且錯誤訊息長得像檔案損毀。**RGBA 格是 `ABGR` 順序而且上下顛倒**，索引格則是正常方向、索引 0 當透明。取的是 `act` 動作 0（站立朝南）第 0 格。
* **完整的 162 隻 sprite 只在 `3.客戶端/old/data09/`。** `3.客戶端/data/sprite/` 底下只有 129~162 那批共 34 隻，前 128 隻早就打包進 `drw02.grf` 了。去 `data/sprite` 抓會只拿到五分之一，而且不會有任何錯誤。
* **符文的階級名稱在 2026-08-25 整層錯開一格改過。** 舊的「凡符 / 仙符 / 神符 / 上古符」對到新的「凡階 / 靈階 / 仙階 / 神階」—— 注意不是單純改字，是整層平移，舊的「仙符」現在叫「靈階」。ID 區段一個沒動。頁面的 CSS class 也跟著改名成 `t-fan` / `t-ling` / `t-xian` / `t-shen`，顏色梯度（灰→綠→金→朱）維持原樣。

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

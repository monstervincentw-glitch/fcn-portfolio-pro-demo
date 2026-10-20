# 測試結果

## 本輪最終交接｜2026-10-20
最終完整Pytest：207 passed in 12.47s、0 failed（184原測試＋23新增）。新增23項包括真實gate、六頁資料流、原生入口、試打參數/暫存/失敗清除、客戶篩選、刷新、空值/欄位/遮罩、HTTP逾時與429重試上限。Timeout反例最初對重試次數預期錯誤，依既有3次策略精確驗證後全過。66個tracked Python語法通過；pip check無破損依賴；Streamlit本機health200、缺PIN安全停止。未進行正式登入、真人客戶收款核對及真實網路壓測；詳見evidence/e2e-readiness-20261020.json。

## 本輪最新｜2026-10-20｜本地驗收單位
test_e2e_acceptance.py：16 passed in 8.70s，0 failed。未替換gate／模型／表單，僅替換Sheets外部I/O，重播中央30商品與三檔已讀回實價，客戶全部合成。首版15項測試有4項測試端欄名／圖表型別／分類範圍假設錯誤，依實際介面更正後15 passed；F-019另以失敗反例確認。完整套件待本輪後續執行。

## 本輪最終交接｜2026-10-19
本輪最終：184 passed in 1.94s，0 failed；新增27項聯動／六頁測試＋15項實價證據測試，共42項。真實3檔必要觀察日27／69／67、缺價0，獨立掃描與V2一致；二次讀回中央5表及價格5區段一致。沒有把合成案例當實價，沒有把本地AppTest當部署驗收。明細見 KO_LINKAGE.md、KO_MARKET.md；Bundle還原紀錄及最終SHA在交付包MANIFEST.json。

## 本階段最新狀態｜2026-10-19
最新：169 passed in 2.01s，0 failed；新增 27 項 KO 持倉與六頁 AppTest，首次有 12 個失敗反例。測試使用虛構客戶；既有 142 項保留。真實行情尚待下一單位。詳見 KO_LINKAGE.md。

以下保留先前交接記錄，最新段落優先。

## 最新結果｜2026-10-19｜GitHub 恢復＋V2 本金邊界
- 遠端讀回：恢復提交 e768a50 與原 cb3e895 的 tree 同為 c6a05e0ae8351a4843161b2996bf7b6793738f11；fetch 後 git diff 為空，所有測試及 docs/audit 檔完整。
- 新增 test_v2_redemption.py：27 項合成行情案例，包含 AKI/EKI/Non-KI、Strike、相對最差標的、提前 KO、缺價及 105% 門檻。最終反例修正前 20 passed／7 failed。
- 修正比率重複縮放後執行 .venv/Scripts/python.exe -X utf8 -m pytest -q：142 passed in 1.23s，0 failed；原 115 項全部保留通過。
- git diff --check 通過。合成案例不是實際商品結算驗收；本輪未寫入 Sheets、未部署網站。完整範圍見 RECOVERY_V2.md。
- Bundle 還原與最終 SHA／SHA256 證據隨保存包 MANIFEST.json 交付。

## 以下為歷史測試
日期：2026-10-19；基準 Commit SHA：858b8d941029c82997b1e372ddea49c182242fe6；狀態：DONE（基準執行，非驗收通過）

環境：Windows、Python 3.12 bundled runtime、repo .venv，依 requirements.txt 安裝；pytest 9.1.1、pandas 2.3.3、Streamlit 1.66.0。

1. 原始 python 指令指向無法啟動的 WindowsApps 別名；bundled Python 缺 pytest，已建立專案 .venv。
2. .\\.venv\\Scripts\\python.exe -m pytest -q：0 執行、4 個收集錯誤（封存撞名與 tools 模組不存在），exit 1。
3. .\\.venv\\Scripts\\python.exe -m pytest -q test_central_cutover.py test_release_fixes.py：22 passed、3 failed，exit 1。兩個 UTF-8 解碼失敗、一個不存在 hero_uri 匯入。
4. Sheets metadata 三份成功；中央條款 A1:AD40、股價矩陣 A1:D4、總帳持倉 API A3:AD3 讀取成功。未修改資料。
5. GitHub /actions/runs?per_page=5：total_count=0。
6. 線上網站工具讀取失敗，未登入／未完成六頁驗收。

測試結果不含帳號金鑰、PIN 或客戶個資。


## 2026-10-19 測試入口修復單位
狀態：DONE；前一成功 Commit SHA：dd431921223668c6bfd1815ec2ce29e8daeb27c5。
F-001 已修復：pytest.ini 排除兩套歷史封存；更新器測試改匯入根目錄；中文檔案明確 UTF-8；圖片驗證改用目前 hero_image 並實際解碼驗證。
F-002 IN_PROGRESS：既有 fcn_stock_library_daily.yml 複製至 .github/workflows/，執行根目錄更新器；每天 UTC 01:15、03:15（台北 09:15、11:15）。尚未推送、未確認 writer secret、未成功執行遠端排程，不標 DONE。
測試：.\.venv\Scripts\python.exe -m pytest -q → 32 passed in 1.83s，0 failed。
此單位未變更正式計算、PIN、安全設定或 Google Sheets。歷史試打入口回歸及更新器冪等測試包含於 32 項。

## 2026-10-19 V2 無效輸入與 KO 邊界修復單位
狀態：DONE；前一成功 Commit SHA：ab5b4d511f7581deb75082a798016699bfd1d66b。
F-006 已修復本單位：v2_portfolio_engine.py 拒絕 NaN／Infinity／布林／非數值行情與比率；缺漏回報不拋未處理例外、不回傳假本金；KO 起日不得早於定價日。百分比字串依百分號轉換。
新增 test_v2_audit.py，29 個反例與邊界案例。修復前 23 failed、6 passed；修復後全套 61 passed in 1.06s、0 failed。
獨立測試證明：閉鎖期達標不帶入記憶；KO 起日當日可累積；分日達標只觸發記憶式；非記憶式需同日達標；KO 日停止計息（2/3 交易日比例）。
限制：此結果不是全部 AKI/EKI/Strike、30 檔真實行情及六頁驗收；階段 2 仍 IN_PROGRESS。未修改 Google Sheets 或線上網站。

## 2026-10-19 SA94 API 連結修復
狀態：DONE（F-003 的 SA94 KI 最小單位）；程式 Commit SHA：aa32d4dd550090df8306bf3f205e7412bd6273c1。
證據：商品完整參數輸入 K2=0.75、商品主檔 K2 ARRAYFORMULA 結果=0.75；API_商品條款_V1 K2 原本無 userEnteredValue。API_標的_V1 第2列 MU、198.47、KI障礙148.85；198.47×0.75=148.8525，KI類型EKI。
先備份 docs/audit/backups/SA94_API_K2_20261019.json，再只更新 API_商品條款_V1 K2 的 userEnteredValue 為連結商品主檔 K2 的 IF 公式。讀回 effectiveValue=0.75、formattedValue=75.00%，鄰格 J2=80.00%、L2=記憶式、M2=EKI。寫入成功，未修改其他欄位、格式、客戶紀錄或行情庫。
Google 原生畫面排版未驗證；此次僅單格公式更正，API讀回數值與鄰格成功。
30檔初步盤點已保存 PRODUCT_INVENTORY.md；19檔缺主要條款。其餘欄位、來源表、公式連動與完整30檔驗收仍 IN_PROGRESS。

## 目前狀態覆蓋｜2026-10-19｜保存單位
狀態：DONE（本地安全保存）；遠端同步：BLOCKED（F-008）。最後成功成果 Commit SHA：7b95b5e2b752a9741d2424ff14e93aca6e5e16eb。
四個 Commit、四份 Patch 與五份交接文件完整；git status 乾淨、git fsck 無錯誤。61 項測試重新通過（1.08s）。建立 audit/fcn-20261019 分支及完整歷史 fcn-audit-20261019.bundle，git bundle verify 成功。RESTORE.md 提供環境重建與推送操作；requirements-audit-lock.txt 記錄套件版本。
F-008 BLOCKED：git push 缺少憑證，Connector create_branch 回覆 HTTP403 Resource not accessible by integration。遠端分支不存在、未建立 PR；交接文件尚無遠端可讀證據。未更動 main，未部署。
已完成 F-001、F-006 的無效輸入與KO邊界、F-003 的SA94 API K2。階段2整體 IN_PROGRESS；階段1整體 IN_PROGRESS。較早段落記錄的是當時狀態，不應覆蓋本段。

## 2026-10-19 中央11檔一致性單位
狀態：DONE（有界一致性）；前一成功 Commit SHA：3ad2464；階段1整體 IN_PROGRESS。
CENTRAL_CONSISTENCY.md 與 evidence/central-20261019.json 保存30檔快照及11檔主要條款、25標的、33配息期來源/API核對，錯誤0；19檔缺條款獨立列出未補值。SA94 K2重新讀回0.75，SM25首期符合基準。
新增18項測試，全套79 passed in 1.13s。初次78成功/1失敗是公式測試未接受兩檔合法的外層空白判斷；讀回確認後修正測試，無資料改寫。
F-009 TODO：SB04第2期、SP43第3期、SB19第2/3期之前有日曆間隔，需與休市日核對。其他未驗收範圍見 CENTRAL_CONSISTENCY.md；未宣稱行情或全網站驗收完成。
本輪無Google Sheets寫入，無UI/PIN/V2規則/共用股價庫/歷史試打改動。F-008仍BLOCKED；無遠端PR。

## 2026-10-19 Bundle還原驗證
狀態：DONE；成果 Commit SHA：cf37e34e2688250e32c7e2b4e670dabfc9c297e0。
從完整Bundle複製至獨立 fcn-audit-restore-check 目錄，六個Commit皆存在；git fsck通過（僅未掛接舊v8-preview commit提示，非損壞）。還原目錄使用現有相同Python環境重跑79項，79 passed in 1.17s。尚未在另一台機器重新安裝依賴。
交付包包含完整歷史Bundle、原始四份Patch、RESTORE.md、套件鎖定清單與SHA256清單；可移出本工作區保存。

## 2026-10-19 配息期／營業日／API階段
狀態：DONE（11檔本地驗收）；基準 Commit SHA：f1e6521638279dd5e82a578818fffc94cb5f1455。
F-009四處間隔全為週末／NYSE休市，無交易日缺口，不改中央日期。11檔33期與公式實際輸出、網站load_model_inputs、V2日期傳遞一致。完整逐期結果與來源見 COUPON_CALENDAR.md 及 evidence/period-calendar-results.json。
F-010 DONE：共用V2期間驗證拒絕重疊、交易日缺口、重複期別及無效付款日。F-011 DONE：保留無效期別提示，核對輸入/API日期與期數；存續商品不因資料不足而消失。
新增36項測試，原79項保留；最終115 passed in 1.18s，0 failed。首批反例修復前15成功/9失敗，過程腳本修正詳見報告。
Sheets本輪寫入0次，五表二次讀回逐值unchanged=true；未更動UI、PIN、共用行情、歷史試打或客戶紀錄。線上版本尚未驗證。
F-012 TODO：2027-12-31中央休市紀錄與NYSE公告不符，超出本11檔涵蓋期間，另案處理。F-008遠端推送受阻仍保留，未重試、未宣稱部署。

## 最終保存驗證｜2026-10-19
狀態：DONE；本階段程式 Commit SHA：5ac3646e59e0d5035ca4d7c9e209d4253417a0d2。
由fcn-coupon-calendar.bundle在獨立目錄還原，HEAD正確；使用同一已鎖定Python環境重跑115 passed in 1.25s。無新程式修改。本階段停止於配息期／營業日／API驗收，下一階段按NEXT_STEPS開始KI/KO/本金全面稽核。

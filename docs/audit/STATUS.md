# 稽核進度

## 本階段最新狀態｜2026-10-19
第一單位完成：提前 KO、客戶持倉與六頁本地聯動。新增 27 測試，全套 169 passed／0 failed。F-014～018 已修正；詳見 KO_LINKAGE.md。正式網站未部署；真實三檔行情下一單位處理。

以下保留先前交接記錄，最新段落優先。

## 最新狀態｜GitHub 恢復與 V2 本金邊界
日期：2026-10-19。本單位 DONE；全案 IN_PROGRESS。以下最新狀態優先於歷史記錄。

GitHub Connector 寫入成功，F-008 遠端保存阻礙解除；分支 codex-audit-recovery、[草稿 PR #1](https://github.com/monstervincentw-glitch/fcn-portfolio-pro-demo/pull/1)。原 cb3e895 與遠端 e768a50 的 tree 完全一致，16 個交接／證據檔與 6 個測試檔已讀回；原始 9 個 Commit 仍完整保留於 Bundle。終端機推送仍缺憑證，main 未修改、未部署。

新增 27 項 V2 合成反例並修正 F-013：正規化比率超過 1 時被再次除以 100，會造成錯誤提早 KO。全套 142 passed in 1.23s，0 failed。沒有 Sheets 寫入、UI/PIN/客戶歷史紀錄修改。完整證據、SHA 對照與驗收限制見 RECOVERY_V2.md；最終 Commit 由 git log -1 與交付包 MANIFEST.json 確認。

下一單位：檢查提前 KO 後模型／持倉顯示欄位一致性，再以共用股價庫驗證 SB04、SP43、SB19 實際逐日結果；19 檔缺條款繼續保留。

## 以下為歷史進度
日期：2026-10-19（Asia/Taipei）
基準 Commit SHA：858b8d941029c82997b1e372ddea49c182242fe6

|工作|狀態|證據／問題|
|---|---|---|
|0.1 GitHub main 取得與根目錄盤點|DONE|根目錄正式入口 streamlit_app.py；兩個 V8.5 封存目錄|
|0.2 原始測試執行|DONE|TEST_RESULTS.md；4 個收集錯誤；指定兩套測試 22 成功／3 失敗|
|0.3 三份 Sheets 存取確認|DONE|三份 metadata 與有界範圍讀取成功|
|0.4 持久交接檔建立|DONE|本目錄五份文件；本次 commit 可用 git log 查詢|
|0.5 線上部署版本辨識|BLOCKED|F-004：公開網站讀取工具無法存取；不可聲稱部署 SHA 已確認|
|1 全商品參數稽核|IN_PROGRESS|API 30 檔，19 檔缺主要條款；F-003|
|2 V2 完整驗證|TODO|F-006；目前僅靜態讀取|
|3 六頁驗收|TODO|F-005、F-007|
|4 股價更新排程|TODO|F-002|
|5 整合與部署|TODO|尚未部署或推送|

正式來源：中央商品庫、既有股價庫、客戶總帳。未修改 Sheets、客戶資料、Secrets、PIN 或 sources/。


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

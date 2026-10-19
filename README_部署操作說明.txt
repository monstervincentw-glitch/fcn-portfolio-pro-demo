FCN Portfolio Pro｜V9.1 共用成分股股價庫版（2026-10-19）
==================================================
一、這次修正

1. 商品條款／股票組合／配息期間／年化票息：讀 FCN_中央商品參數庫_V1。
2. 真實歷史收盤價：直接讀「原有 526 檔成分股股價庫／收盤價矩陣」。
   和原本「FCN 歷史試打」使用同一份原始股價！沒有再複製到中央庫。
3. 客戶及持倉：原客戶總帳保持不變。對應商品代號重算商品模型，
   再依每筆持倉本金計算票息／本金模型數字；不依賴總帳的舊試算欄位。
4. 不讀舊 V2 Data 試算表、不開啟個別 FCN Chart 試算表。
5. 不以銀行核約、核價、正式啟用勾選作為模型計算門檻。
   仍需必要條款日期、價格、KO／KI 類型，缺漏則顯示資料不足。
6. PIN 登入、隱私遮罩與站台部署安全限制保留；不修改歷史試打原始程式。

二、GitHub 覆蓋操作

進入 GitHub 專案：
https://github.com/monstervincentw-glitch/fcn-portfolio-pro-demo

1. 解壓縮 FCN_V9_共用股價庫_直接覆蓋版.zip。
2. GitHub 專案根目錄 → Add file → Upload files，覆蓋下列 7 個檔案：
   streamlit_app.py
   central_catalog.py
   central_live_pages.py
   central_catalog_page.py
   fcn_central_model.py
   v2_portfolio_adapter.py
   test_central_cutover.py
   （沒有的檔案直接新增；請勿刪除其他既有檔案。）
3. 按 Commit changes。
4. 唯一的每日股價庫排程：把壓縮包內的
   .github/workflows/fcn_stock_library_daily.yml
   放入 GitHub 專案的同一路徑（資料夾必須是 .github/workflows/）。
   可以在 GitHub 根目錄 Add file → Create new file，檔名輸入
   .github/workflows/fcn_stock_library_daily.yml
   將解壓檔案的內容貼入後 Commit。
   注意：不要把 yml 只放在根目錄；那樣 GitHub Actions 不會運作。

三、只有一套行情更新，不需要第二個行情庫

排程運行 root/update_stock_prices.py（GitHub 原本就有）。
寫入：原 526 檔成分股股價庫／收盤價矩陣。
讀取：FCN 商品監控、客戶報表，以及原歷史試打都用此收盤價矩陣。
不需要上傳 tools/update_central_prices.py，不需要建立第二份中央行情排程。

四、GitHub Actions 設定（若之前還沒設定）

GitHub 專案 → Settings → Secrets and variables → Actions → New repository secret
名稱：FCN_PRICE_WRITER_JSON
內容：具備「原 526 成分股股價庫」編輯權限的 Google 服務帳號 JSON。
憑證不要貼到聊天裡，也不要放進 GitHub 程式檔。

GitHub → Actions → FCN Shared 526-Stock Library Daily Update → Run workflow
第一次可手動測試；執行紀錄呈 Success 才算排程有成功。
每日排程：台灣時間 09:15、11:15 各嘗試一次（如果尚無新行情則不重複寫入）。
實際能否成功由 GoogleFinance 可用性、既有股價庫寫入權限決定。

五、非常重要的界線

- 已確認原成分股庫包含 INTC、MU、AMD、NVDA；這些股票不必再建第二份。
- 若未來新增 FCN 連結的是「原成分股庫沒有的股票」，網站將顯示缺標的。
  需將該股票補進同一份原成分股股價庫（不是新建第二個行情庫）。
- 模型價格每天隨股價庫更新後，網站重新整理會取得新資料；不代表盤中即時報價。
- 股票分割、停牌、特殊 KO 觀察日、固定票息等仍以中央參數內容為準。
- SM25 的第 1 期起日仍為 N.A.，SP34 與 SM25 的 KO 類型目前尚非有效值，
  因此相關完整 V2 計算仍會明確標示「資料不足」，不是銀行核對阻擋。
- GitHub 連線沒有可用寫入權限，此 ZIP 尚未自動部署；部署與 Actions 成功需用 GitHub 驗收。
- Streamlit 站台需有讀取「中央商品庫、成分股股價庫、客戶總帳」的服務帳號權限。

六、驗收檢查

[ ] 網站成功開啟、PIN 登入正常。
[ ] 商品監控中能看見中央參數的 SP34 / SM25 / SQ59。
[ ] 詳情股價出自「收盤價矩陣」，沒有個別 FCN Chart 或舊 V2 試算表的 Google API 讀取。
[ ] 修改中央商品參數後，重新整理能看到該商品更新。
[ ] 新增一筆客戶持有商品後，重新整理能在客戶投資顯示該 FCN。
[ ] 歷史試打頁功能仍能操作。
[ ] GitHub Actions 手動執行成功、最新交易日於成分股庫新增。

程式測試：本次共 11 個共用來源／資料缺漏／客戶聯動測試通過；
測試不等於正式 Google 權限、站台實際部署與金融產品結算驗收。

# FCN Portfolio Pro V8.5.5 正式修復版

此套件以 main 的 ae417f3d021ad183503ec8e7a5dadf85476fd1ef 為基礎，保留正式版 Google Sheets 讀取與歷史試打引擎。

## 本次修正

- 使用測試版柴犬財神圖片與登入版型，暖色樣式放入正確 assets 目錄，並補齊 .streamlit/config.toml。
- 登入頁、側邊欄顯示 V8.5.5，便於確認部署版本。
- 日常監控包含執行中／存續監控，以及結束後三個月追蹤。若有 visible_until，採用來源截止日；否則以結束事件日加三個日曆月，含截止當日。已結束商品不參與存續商品 KI 預警。
- 顧問台可顯示 Chart 已有的 KI 水位及距離，不因 KI 類型缺漏而隱藏。明確註記來源及條款待核對；不將水位比較宣告為已觸發敲入。
- 條款欄名可接受中英文間空格、全形字元；增加「全部有效行情與 KI 距離」明細，以及缺少 KI 水位提示。
- 股價更新程式放入 tools/，排程放入 .github/workflows/。保留原有更新程式內容與執行時程（台灣時間每日 11:15）。

## 更新到現有正式站

1. 解壓縮 ZIP。最外層應直接看到 streamlit_app.py、site_login.py、assets、tools、tests、.streamlit、.github。
2. 開啟原 GitHub 專案的 main 分支。將「解壓縮資料夾裡的內容」上傳到儲存庫根目錄並覆蓋同名檔案，不能再多包一層 FCN 資料夾。新版不需要舊的 FCN_PortfolioPro_V8_5 子資料夾，但不必刪除它。
3. 上傳後核對 assets/shiba-login-v8-1.jpg、assets/warm-theme.css、.streamlit/config.toml、.github/workflows/update_stock_prices.yml 均在正確位置。Windows 若未顯示點開頭資料夾，請先顯示隱藏項目；GitHub 檔案清單必須看得到 .streamlit 與 .github。
4. Streamlit 正式站設定應指向同一 repository、main 分支與根目錄 streamlit_app.py；保留目前 Secrets。
5. 在 Streamlit 管理頁執行 Reboot，等待啟動完成。僅刷新瀏覽器不一定會清除舊的已載入模組。
6. 登入前確認柴犬出現及 V8.5.5 標記；登入後側邊欄也要顯示 V8.5.5。若仍看到舊 PIN 登入標題，請檢查部署記錄與入口，不要重複上傳不同版本。

## 股價排程

此套件只修正排程檔案位置，尚未在線上執行寫入。若 GitHub 已設定原本的 FCN_PRICE_WRITER_JSON repository secret，排程上傳 main 後將可依原設定執行。若缺少該 secret，請在 GitHub Secrets 設定原本專用的股價庫寫入服務帳號；不要將 JSON 上傳成檔案，也不要改用網站唯讀帳號。

## 上線驗收

- 「全部商品」數量應與部署前一致；「日常監控」應包含 SAE9、SR67 等存續商品，以及來源仍列入三個月追蹤的 SQ29、SR50。
- SAE9 商品頁與顧問台的 KI 水位應一致；以先前 2026/10/16 資料，門檻 70%，COHR 80.92%，距離為 10.92 個百分點。最新資料變動時以實際來源為準。
- 顧問台的缺值另列，不能把沒有門檻誤讀成沒有風險。
- 歷史試打及客戶頁資料應正常。
- SR67 客戶代號對應未驗證的情況仍保留，不以猜測名稱取代；需要另外對照總帳來源。

本套件未包含任何真實 PIN、服務帳號私鑰或客戶資料。網站 Sheets 讀取範圍、底層公式及歷史試打引擎未變更。本次是更新包交付，尚未替你上傳或重新部署正式網站。

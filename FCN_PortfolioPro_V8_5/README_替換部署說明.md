# FCN Portfolio Pro V8.5｜正式整站覆蓋與股價每日更新

## A. 覆蓋網站（立即可做）

1. 在 GitHub 正式版 repository（`main`）按 **Add file → Upload files**，將此 ZIP 解壓後的**內容**（不是外面一層資料夾）放到根目錄；同名檔案覆蓋並提交。不要只上傳 ZIP 檔。
2. 必須連同隱藏資料夾 `.streamlit/`、`.github/workflows/`、`assets/` 一起上傳。Streamlit Cloud 主程式維持 `streamlit_app.py`。
3. Streamlit Cloud 原本的 `[site_login]` 6 位 PIN、`[app]`、`[gcp_service_account]` Secrets **不要更動**；這個 ZIP 沒有任何私鑰。
4. 已移除「🧪 虛擬試打」入口，保留「🧪 FCN 歷史試打」與其 V2 模型，以及其餘 7 個主要頁面。舊 repo 若還留有 `virtual_trial.py`，可從 GitHub 刪除；新版改為 `historical_trial_engine.py`。

> GitHub 網頁的「Upload files」通常會覆蓋同名檔案，但不會刪除 ZIP 中未出現的舊檔；若 repo 還有舊的額外檔案，要單獨清理。請不要將 `.streamlit/secrets.example.toml` 當作平台正式 Secrets。

## B. 啟用股價庫每日自動更新（**第一次必做**）

股價庫：[FCN V8.4 四大指數成分股歷史股價庫](https://docs.google.com/spreadsheets/d/1ef0Whr7-bgj37DdOnC7ug8Dyv5Ab92-AMw5n9V18UJY/edit)，目前固定至 **2026-10-16**。本包只增加 GitHub 排程與程式，**不可能靠覆蓋 ZIP 自動取得 Google 寫入授權**。

1. 準備一組有 **Google Sheets API** 存取權限的 Google 服務帳號 JSON。建議用「股價更新專用帳號」，避免授予客戶總帳寫入權限。
2. 只對上面這一份**獨立股價庫**，將服務帳號的 `client_email` 分享為 **編輯者**。正式客戶／FCN 總帳仍維持現有唯讀設定。
3. GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**，名稱**完全照打** `FCN_PRICE_WRITER_JSON`，值貼入該服務帳號的**完整 JSON**，包含 `private_key` 的換行格式。**不要提交 JSON 到 GitHub 檔案**。
4. repo → **Actions → FCN 股價庫每日自動更新 → Run workflow**，先手動執行一次確認憑證通過。2026-10-17 為週六，無新交易日是正常結果。
5. 之後 GitHub Actions 每日 **03:15 UTC** 執行（美東夏令時 23:15、冬令時 22:15），自動抓取上一次成功日期後的美股交易日，將固定數值追加到「收盤價矩陣」，並更新「逐檔匯入進度／行情總覽／更新紀錄」。**GitHub 定時工作可能延遲，遇到 API 限制也可能失敗；請查看 Actions 的最後成功紀錄**。

### 股價更新設計

- 股票範圍讀取原股價庫第一列 **526 個代號**，不硬編排欄位次序。原始資料來源為 `GOOGLEFINANCE`；在隱藏的「FCN_自動更新暫存」頁面短暫抓資料，再只把已核實的**數字**寫到正式矩陣。若 GoogleFinance 回傳錯誤／非指定交易日／無值，保持空白、**不補虛構價格**。
- **只新增交易日、不覆寫既有歷史**；重跑時先檢查日期，避免重複。週末及 NYSE 例行假日跳過。遇特殊停市／無法辨識的行情供應商錯誤，程式中止並待下一次排程重試，不會造出假日期。
- 如果不足約 80% 代號能拿到指定日真實收盤價，拒絕追加整日，避免錯誤的部分日歷史；通過門檻後個別缺價仍保持空白。已寫入日期的個別缺價不會自動回填，需人工核實後再處理。
- 股價歷史試打網站維持**唯讀**：它和 GitHub 股價排程寫入服務彼此分離；網站頁面會讀取最新已存入交易日，不再固定顯示 2026-10-16。
- 過往資料有拆股/股息調整口徑未完全確認的例外；請在實際結算前核對股價口徑。**排程是新寫入能力，不等於現在已在你帳號啟用，也不等於保證每日成功。**

## C. 覆蓋後快速驗收

登入 6 位 PIN → 投資總覽 → 顧問工作台 → 股票曝險 → 客戶投資 → FCN 商品 → **FCN 歷史試打** → 例外處理 → 銀行驗收。確認虛擬試打已不再出現。歷史試打先查 `AAPL,NVDA` 及已知歷史日期；執行 GitHub Actions 後在「更新紀錄」確認最新成功交易日，網站的資料日期也同步變更。

**限制：** 本包通過離線程式檢查，但無法從這個聊天室確認 GitHub main 已實際覆蓋、Actions secret 已設好、Google Sheets 編輯權已開通，故不宣稱這些外部步驟已完成。

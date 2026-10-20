# 正式部署前驗收｜2026-10-20

結論：**尚未具備正式部署／合併驗收條件**。本地功能與修復通過；線上PIN後操作、實際部署SHA與真實環境延遲仍BLOCKED。未修改main、未合併PR、未部署、未寫入Sheets。

基準main：858b8d941029c82997b1e372ddea49c182242fe6；第一修復遠端：8fcbef5157b4edb2c7c38aef82ad45639a9938e0。最後文件提交SHA以GitHub工作分支及保存包MANIFEST.json為準。

| 項目 | 狀態 | 已有證據／限制 |
|---|---|---|
| 恢復先前進度 | PASS | dde477b與原cb3e895歷史保留；在原分支工作，未重做V2稽核 |
| 六頁本地功能及資料流 | PASS | E2E_ACCEPTANCE.md；真實PIN gate、正式解析器及V2；只有Sheets I/O替換為快照／合成總帳 |
| PIN登入、登出、失效 | PASS | 未認證時零資料讀取，錯誤輸入拒絕，正確測試PIN登入，登出／逾時重新阻擋；正式PIN未取得 |
| 歷史試打實際提交 | PASS | 股票／日期／KO 105、Strike 80、AKI 70及閉鎖設定進入原模擬；本金倍增、結果session重讀與跨頁保留；錯誤輸入清舊結果 |
| 試打永久存檔 | NOT_TESTED | 現有功能只有session暫存，沒有持久化寫入介面；新瀏覽器session不保證保存，非交易資料遺失 |
| 客戶篩選及實收分離 | PASS | 兩個合成客戶、USD/EUR/JPY、未知實收保留空值、重新載入後重算；不是正式客戶收款核對，也不是每客戶獨立帳號授權 |
| API失敗／空資料／欄位異動 | PASS | 中央／行情／總帳故障、遮罩失敗、無法對應客戶、缺欄均有反例；舊模型不頂替中央失敗 |
| 網路逾時及重試上限 | PASS | 真實HTTP函式以模擬Timeout/429驗證25/35/45秒限制、中央最多3次與1.5/3秒等待；未假裝實測Google延遲 |
| 原生中央商品庫快取 F-019 | PASS | 修正前1失敗；修正後每次走enrich，讀回中央、清舊值、失敗後清快取 |
| 全部Pytest | PASS | 207 passed in 12.47s，0 failed；184原測試＋23新增整合／邊界測試 |
| Python語法／套件依賴 | PASS | 66個tracked .py（含既有封存）ast.parse；pip check無錯誤 |
| Streamlit啟動 | PASS | 真實本機127.0.0.1:18501啟動、health HTTP200 ok、瀏覽器顯示缺PIN設定阻擋，檢查後已停止服務 |
| 正式網址 | BLOCKED | 新提供...zzbdzzmnjdp...回not_found；前提供...zzbdzzmnrjdp...可到PIN。無法由公開資訊判定新網址是不存在或無權限 |
| 正式站精確部署SHA | BLOCKED | 舊網址title V9.1、PIN畫面V8.5.8不等於Commit證據；使用者先前稱main，尚無管理頁SHA證據 |
| 六頁正式登入後操作／刷新一致性 | BLOCKED | 不索取PIN、不繞過登入。正式Google憑證與資料存取未使用於本輪 |
| 真實網路長時間讀取 | BLOCKED | 無正式登入後量測；單批最壞45秒×3＋4.5秒，多批累加仍可能較慢，不宣稱無延遲風險 |
| 瀏覽器圖表縮放／手機視覺 | NOT_TESTED | AppTest確認圖表規格生成，未替代瀏覽器像素／手勢驗收 |
| 新資料來源限制 | PASS | 整合讀取僅原總帳、中央庫、既有股價庫；正式六頁未走獨立商品Chart；舊helper及封存未刪除 |
| API重複請求 | PASS | 同一次主頁rerun三個中央頁共用snapshot；中央失敗只嘗試一個批次路徑。每次rerun仍會重載，未做跨session永久cache |
| PR檔案／敏感值檢查 | PASS | tracked檔案未發現私鑰、GitHub/Google token及固定六位PIN特徵；未追蹤secrets/.venv；不含客戶總帳證據。屬有界特徵與差異審查，不是全歷史秘密掃描 |
| PR不必要封存 | PASS | 無新增bundle/zip/patch及舊網站封存目錄；保存包在repo外；docs快照是既有稽核證據 |
| Actions設定靜態檢查 | PASS | 真正.github/workflows下為既有股價庫更新器；入口檔案存在、read權限、並行限制、120分鐘上限，使用獨立writer secret引用；未印出值 |
| Actions線上成功執行 | BLOCKED | Connector本次PR runs/status皆空；不等於排程成功或失敗，未觸發會寫正式庫的更新器 |
| 全新主機／所有允許依賴版本 | NOT_TESTED | 本次Windows Python3.12.14，Streamlit1.66.0/pandas2.3.3/Altair6.3.0；鎖定環境通過，不代表requirements所有版本組合 |
| 既有19檔缺條款 | BLOCKED | 保留缺漏與警告，未虛構；不能宣稱30檔資料全面驗收 |
| 既有F-012未來休市日 | FAIL | 前階段已確認中央2027-12-31日曆錯誤，未影響本次三檔期間，依原交接另案備份與修正；本輪未改Sheets |

安全與限制：沒有發現本輪寫入或刪除正式資料的路徑。已修正的F-019會造成顯示過期模型，非實際帳本資料刪除。API慢回應、缺商品條款及未驗收的正式環境仍是具體風險。既有bank_approved設定未更動或新增；相關歷史議題F-005仍留存。根目錄config.toml不是預設.streamlit/config.toml；本地CORS/XSRF預設啟用，未擅自搬移設定或改外觀，線上主題／設定需管理者確認。

最少人工驗收（不回傳PIN、Secrets、客戶明細或Logs）：
1. 在自己的Streamlit管理介面確認正式網址、部署分支及Commit SHA；只回報這三項非敏感資訊。勿改部署分支。
2. 若能建立私有預覽，從codex-audit-recovery啟動獨立環境並保留同等PIN與唯讀權限；不要改正式設定。沒有預覽時登入正式站只能驗證舊部署，不能宣稱修復已上線。
3. 自行PIN登入，依E2E_ACCEPTANCE表逐頁切換，選SB04及一位客戶，核對KO/本金/幣別/歷史仍存在；不傳客戶資料。歷史試打提交後換本金、換頁回來及刷新；按重新讀取，最後安全登出確認再次需要PIN。
4. 回報每頁PASS/FAIL、測試版本及是否出現錯誤，不附私人數據。完成後再評估是否明確授權合併／部署。

續跑位置：優先核對部署身份及預覽瀏覽器驗收，接著處理F-012與排程成功證據；不要重做已完成的V2演算法稽核。GitHub顯示mergeable僅表示可合併性，不代表本報告的正式驗收通過。

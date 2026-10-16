# FCN Portfolio Pro V8｜暖米白・奶茶金候選版

本包為 **V7 功能基準 + V8 視覺更新**，包含可部署的完整程式與測試。尚未完成 Streamlit 實機／線上驗收，請先部署測試版本。

## 基準來源

- 使用者提供：V7 多輪驗證候選包；其虛擬試打、顧問工作台、股票曝險及圖表修正完整保留。
- 已對照 V5 UI 包、V6 Advisor 包。V6 與 V7 主頁相同；V7 新增 KO 觀察期間 70% 行情涵蓋率防護。
- V7 未附的登入、資料連線、示範資料、彙總及依賴檔，取自 https://github.com/monstervincentw-glitch/fcn-portfolio-pro-demo ，基準提交 `e46ed0cc88255cc45316c4dad6eb434f0f2d6155`。
- 登入圖片使用使用者指定的柴犬財神圖，原檔封裝於 `assets/shiba-login.png`，沒有重新生成或改動圖片內容。

## 本輪更新

登入採左側柴犬、右側 PIN 卡片；窄螢幕改為上圖下表單。全站統一暖米白背景、奶茶金操作色、暖棕文字、柔和綠／橘／磚紅狀態。客戶狀態改為卡片，商品詳情改為雙欄指標；試打表單增加分區，圖表沿用原有資料與尺度，改用暖色背景、網格及色階。字體使用系統字體，移除外部 Google Fonts 載入。

## 部署

1. 解壓 ZIP 到獨立測試目錄／測試分支，入口為 `streamlit_app.py`。保留 `assets/`、`tests/` 與 `.streamlit/config.toml`。
2. 安裝原有 `requirements.txt`；V8 沒有增加套件依賴。
3. 若既有 `.streamlit/config.toml` 還有其他設定，只合併本包的 `[theme]` 區段。不要覆寫其他部署設定。
4. 沿用既有託管環境設定。**本包不含、也不要求修改 Secrets、PIN、服務帳號或總帳 ID。** 沒有登入設定時仍會停止，沒有未授權的展示入口。
5. 測試環境先以原有 DEMO 模式驗收；保留原本 live／diagnostic 模式及核准邊界。
6. 本機測試可執行 `python -m unittest discover -s tests -v`，啟動使用 `streamlit run streamlit_app.py`。請在專案根目錄執行。
7. 確認本包 `ONLINE_ACCEPTANCE.md` 各項後，再決定正式站更新。本次沒有推送 GitHub 或部署線上網站。

## 完整套件與僅更新 UI

本包包含完整 V7 功能，所以可獨立作為部署候選版。若環境已經是相同 V7 基準，實際 UI 更新檔為：

- `streamlit_app.py`
- `site_login.py`（僅呈現，驗證與鎖定流程保持）
- `chart_render.py`（僅配色與圖表外觀）
- 新增 `warm_theme.py`、`assets/warm-theme.css`、`assets/shiba-login.png`
- 新增 `.streamlit/config.toml` 的 `[theme]` 設定

不要把本包當成可無條件覆蓋任何未比對的更晚版本。`tests/v8_baseline.json` 記錄受保護模組 SHA-256；附帶的差異檔以 V7 及已抓取 GitHub 登入程式為比較基準。

## 驗證範圍

- 最終離線測試：37 項，36 通過、1 略過；略過項為 Altair 實際圖表規格檢查。
- Python 語法檢查通過。
- Sheets 連線、試打、解析、彙總、示範資料與依賴檔內容不變。
- PIN 驗證／限流／逾時／登出流程的語法樹比對通過；主頁計算及讀取呼叫參數一致。
- 主文字與按鈕的指定實色組合對比達 4.5:1；這不等於所有實際畫面的無障礙驗收。
- 本機缺少 Streamlit、Altair；安裝因 DNS／網路限制失敗。預覽連線受阻，本機檔案網址也被瀏覽器工具政策拒絕。
- 靜態 HTML 預覽只用於看設計方向，不是 Streamlit 實際截圖，也不驗證登入、試打或 Altair 渲染。瀏覽器視覺檢查與線上驗收明確未完成。

原 V7 試打模型的市場假日、真實行情及合約核對限制仍適用；本次沒有變更其算法或宣稱新增財務驗證。

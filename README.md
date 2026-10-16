# FCN Portfolio Pro｜銀行 Edge 專用 Streamlit 測試版

## 為什麼這次選 Streamlit？

銀行電腦實際照片顯示 `https://my-fcn-app.streamlit.app` 可由 Microsoft Edge 開啟並正常顯示 FCN 網頁及圖表，故**先以同一 Streamlit Community Cloud 平台驗收**，節省開發與測試時間。但那個網址屬於同事，請勿把我們的測試站部署到他人的 App，也不要複製其資料或憑證。

**本包是全虛構資料的可部署原始碼，尚未部署，不含真實 Google Sheets、私鑰及個資。**

## 不用在銀行電腦安裝任何程式

你只要用**私人電腦**完成 GitHub 和 Streamlit Cloud 的部署；銀行電腦只用 Edge 開啟最終 HTTPS 測試網址。不得在銀行電腦執行安裝指令，亦不以 VPN／私人熱點繞過公司政策。

### 一次性的部署步驟

1. 用自己的 GitHub 帳號建立 `fcn-portfolio-pro-demo` repository，此**虛構資料驗收版可以使用公開 repository**，這樣較容易先確認銀行 Edge 能否開啟，不必先完成 Streamlit Viewer 登入；若希望先測登入也可選私人 repository。絕對不要放入任何客戶資料、API 金鑰或服務帳號 JSON。
2. 將本 ZIP 解壓，把 **`streamlit_app.py`、`demo_data.py`、`demo_utils.py`、`requirements.txt`、`.streamlit/config.toml`** 等檔案直接放在該 repository 根目錄（注意隱藏資料夾 `.streamlit` 需保留）。
3. 開啟 https://share.streamlit.io，登入並連接 GitHub。選 **Create app → Yup, I have an app**，指定你的 repository、`main` branch、入口檔 `streamlit_app.py`。
4. 建立後 Streamlit 會提供 `https://<你選的名稱>.streamlit.app` 網址。這才是我們銀行電腦驗收的網址；同事既有網址不需要動。
5. 先用私人電腦驗收，再依銀行資訊安全規範使用銀行 Edge 驗收。若選用私人 app，還需測試 Streamlit Cloud 的 Viewer 驗證在銀行 Edge 是否正常；若驗證受阻，先找 IT 判定，不繞過控管。

**測試資料絕對不能替換成實際客戶資料來圖方便。** 後續真正讀取 Google Sheets，需要公司同意外部平台處理業務資料、僅伺服器使用最小權限唯讀服務帳號、使用企業登入／MFA 及角色授權。在完成這些前，本程式維持 `DATA = make_demo()`，不連正式總帳。

### 銀行 Edge 驗收重點

- Edge 的網頁載入與 Streamlit 元件互動正常；不同銀行代理規則可能影響 WebSocket，因此要實際測試下拉、頁籤、切換。
- USD / EUR / JPY 數字與小數呈現正確，不同幣別不加總；缺條款的本金維持未知。
- 客戶清單和所有圖表皆屬虛構範例。
- 不需要瀏覽器外掛、瀏覽器端 Google API 或私人帳號權限。

## 後續產品化

未來將建立獨立的唯讀 Google Sheets 連線層來取得 `API_客戶 / API_持倉 / API_商品 / API_現金流`；**此展示包不含真正總帳 ID、沒有 Google 連線程式或憑證**。正式版必須在銀行合規及身份驗證完成後開發及測試。

Google 官方部署文件：https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

### 本機測試（私人電腦、非銀行電腦）

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

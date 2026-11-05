# 成長股觀測站：Streamlit 研究入口

公開唯讀入口，使用原站同一套買入訊號。提供美股／台股、主策略／背離長抱候選、資料異常名單、更新紀錄、2016–2026 年回測與出場稽核下載。

## 部署

- GitHub repository：`monstervincentw-glitch/fcn-portfolio-pro-demo`
- Branch：`growth-observatory-streamlit`
- Main file path：`streamlit_app.py`
- Python：3.12
- 不需要 Secrets、不需要 GPT 登入。此分支專供觀測入口，不合併回 FCN 的 `main`。
- Streamlit Community Cloud 登入後選 Create app，填上述三項再 Deploy。
- 正式網址須待 Streamlit 部署成功後才產生；銀行端另須實測。

## 讀取與權限

瀏覽器只連線 Streamlit。Streamlit 伺服器透過匿名 GET 讀取原站 `/api/dashboard`，不傳送 Cookie、使用者 ID 或任何管理金鑰。以白名單保留公開市場欄位；不保留持股、組合、自選或身份欄位。沒有更新後台、修改持股或券商操作功能。

資料每五分鐘失效重讀，按「重新讀取資料」可提前清除快取。這是讀取原站已完成的觀測；每日資料計算仍由原站既有排程執行。網站沒有訪客時不會因快取 TTL 自行執行更新。

如果原站無法連線、回應時間過舊或資料庫未就緒，入口停止顯示買入候選，保留本地回測與策略說明。出現錯誤不會以打包的舊候選清單冒充最新資料。上線驗收必須檢查 Streamlit 伺服器能匿名讀取原站，才能稱為即時同步成功。

公開研究資料原本已免登入，不需要任何 Sites bypass token 或更新授權；切勿把這類金鑰放進 Secrets 或程式。

## 本次候選差異

11/05 台灣時間最新台股工作為 24/80 成功、56 檔待核對。這些來源回傳的末日為 11/03，而目標為 11/04。程式保留上次成功資料，但寫入來源錯誤，`fresh=false`，因此停止新買入候選。

用 11/04 公開初始快照加上該輪 56 檔錯誤名單，能重現主策略 34→8、背離 9→3。這是錯誤遮罩的重建，不是每一日完整快照的逐檔資料版本稽核。六檔背離候選為 2330、2303、2317、2383、3019、3481。美股最新為 43/17，81/89 更新成功，八檔因 126 日內單日還原價變動超過 30% 暫停；已確認 DIOD 新增背離候選，無完整歷史快照可解釋所有美股逐檔變化。

## 本地驗證

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m streamlit run streamlit_app.py
```

回測檔案結算至 2026/11/04，非每日重跑。美股估值以拆股尺度修正版為預設；台股 2016–2018 資料不足。所有結果仍有目前存活樣本偏誤，台股公告時點有推估限制。

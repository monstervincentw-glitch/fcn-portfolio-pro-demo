# 資料流與模組盤點
日期：2026-10-19；基準 Commit SHA：858b8d941029c82997b1e372ddea49c182242fe6；狀態：IN_PROGRESS（靜態盤點完成，逐頁執行待驗）

正式根目錄入口 streamlit_app.py；封存 FCN_PortfolioPro_V8_5/ 與 FCN_Portfolio_Pro_V8_5_5_Fix/ 不作正式入口。pages/01_📚_中央商品庫.py 為額外 Streamlit 頁。

- 登入：streamlit_app → site_login.gate → SheetsReader；UI 使用 warm_theme、chart_render、demo_charts。
- 中央計算：central_catalog.load_model_inputs（商品條款 API、標的 API、配息期、休市日、輸入規則）＋load_market_matrix（原有收盤價矩陣）→ v2_portfolio_adapter.load_models → fcn_central_model.model_one → v2_portfolio_engine.calculate_v2。
- 顧問工作台／FCN 商品／股票曝險：central_live_pages 的 render_dashboard／render_product_page／render_exposure，使用中央商品模型。
- 客戶持倉：sheets_backend 讀取總帳 API → enrich_new_holdings 按 product_id 合併中央模型並按本金換算 → 投資總覽／客戶投資；實際現金流與模型欄位需續查。
- 歷史試打：streamlit_app → price_library_trial.render_trial → historical_trial_engine.simulate_history；價格來源同一股價庫。此獨立試打算法需回歸，不可貿然替換 UI。
- 舊路徑：sheets_backend.chart 仍能讀個別來源 Chart；正式頁面是否可到達尚待完整追蹤（F-007）。
- 更新器：根目錄 update_stock_prices.py；根目錄兩個 YAML 不會被 Actions 自動載入（F-002）。

三份來源連線：中央庫 Asia/Taipei；行情庫 America/New_York；總帳 Etc/GMT。總帳只讀 API_持倉 A3:AD3 欄名，未輸出客戶紀錄。


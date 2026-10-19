# 接續工作

## 最新續跑位置｜2026-10-19（優先於下方歷史記錄）
已完成 GitHub 遠端恢復與 V2 比率／本金邊界；全案仍 IN_PROGRESS。

目前使用 codex-audit-recovery，草稿 PR #1 已建立，main 未變動。原 cb3e895／9 個提交保留在 audit/fcn-20261019 及 Bundle。遠端等內容恢復提交 e768a50；本次新修改另存 audit/v2-local-20261019 並同步 recovery。最終 SHA 看 git log -1 與交付包 MANIFEST.json。Connector 可寫入；終端機無登入憑證不再阻礙保存。

全套 142 passed in 1.23s，0 failed。已完成 11 檔／25 標的／33 配息期來源與公式/API一致性；本次新增 27 項 KI／本金／比率反例。勿重做已完成修復。本輪 Sheets 寫入 0 次，原備份及讀回證據保留。

下一個最小單位：先讀 RECOVERY_V2.md，檢查 fcn_central_model.py 的 price_history／worst_ticker 與 KO 日期，以及 v2_portfolio_adapter.py 的舊估值欄位清除。新增可重現反例，有錯才改。接著從既有共用股價庫唯讀載入 SB04、SP43、SB19 的應有交易日與收盤價，逐日核對 KO/KI/Strike／本金。缺價列出，不可用合成價冒充實際驗收，再擴至其餘 8 檔。19 檔缺條款保持缺漏。

尚未完成：實際行情全面稽核、六頁線上驗收／部署 SHA、F-005 既有 bank_approved 路徑、F-007 舊 Chart 可達性／持倉欄位、F-012 中央 2027-12-31 休市記錄。不得更動客戶實際收款、歷史交易、UI/PIN 或建立第二股價庫。F-012 若另案修正須備份與讀回，不能滾動契約指定日期。

每單位完成測試、交接文件、Commit、Connector 同步 recovery 及核對 tree，再更新完整 Bundle／Patch。最新交付為上一層 FCN-recovery-v2-delivery-20261019.zip 及 fcn-audit-latest.bundle，重建見 RESTORE.md。停止於此最小單位，不宣稱全案驗收。

## 以下為歷史交接（其中 BLOCKED 與測試數已由上述覆蓋）
日期：2026-10-19；狀態：IN_PROGRESS；本階段基準Commit SHA：f1e6521638279dd5e82a578818fffc94cb5f1455。

- 最後成功完成階段：配息期、營業日與API一致性 DONE（11檔33期，本地程式）；詳見COUPON_CALENDAR.md。F-009/010/011關閉。
- 最後成功 Commit SHA：f1e6521638279dd5e82a578818fffc94cb5f1455為本階段開始點；本次程式提交完成後用git log -1取得；下一提交回填。分支audit/fcn-20261019。
- 尚未完成的工作清單：下一階段V2 KI/KO/Strike/本金回收全面反例及實際行情；19檔缺必要條款；六頁線上驗收；F-012未來2027-12-31休市錯誤另案；F-008推送權限。
- 正在修改的檔案：central_catalog.py、fcn_central_model.py、v2_portfolio_engine.py、test_coupon_calendar.py、scripts/audit_coupon_calendar.py與docs/audit；提交後應乾淨。
- 尚未解決的測試錯誤：0；115 passed in 1.18s。原79項全部保留通過。
- Google Sheets 已修改的欄位與備份位置：本輪0寫入；快照evidence/period-calendar-20261019.json、二次讀回period-readback-20261019.json五表相同。歷史SA94 K2備份仍在backups/SA94_API_K2_20261019.json。
- 外部權限阻礙：先前Git缺憑證與Connector HTTP403未解除；沒有PR、遠端未同步；線上部署SHA與付款地完整日曆未取得。這些不阻止本地引擎測試。
- 下一次應執行的第一個命令：Get-Content docs/audit/STATUS.md,docs/audit/NEXT_STEPS.md
- 明確的完成條件：下一單位先新增AKI/EKI/Non-KI邊界、最差標的與Strike回收反例並驗證現有引擎；有錯才改、相關測試及全套通過後Commit及更新Bundle。實際價格缺漏不得以合成價格冒充驗收。F-012若處理須先備份中央對應列再讀回，勿更改商品契約日期。

本次交付採coupon-calendar保存包，含最新完整Bundle及自858b8d9起全部Patch。RESTORE.md適用，完整包還原後以audit/fcn-20261019分支執行。

最後成功程式 Commit SHA：5ac3646e59e0d5035ca4d7c9e209d4253417a0d2；獨立Bundle還原115項全通過。正在修改的檔案：無（最後文件保存提交後）。最新完整Bundle同步為../fcn-audit-latest.bundle，交付包為../FCN-coupon-calendar-delivery-20261019.zip。

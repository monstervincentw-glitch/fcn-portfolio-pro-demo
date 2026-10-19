# 稽核成果重建與推送

## KO聯動與三檔實價保存包（最新）
使用上一層 FCN-ko-linkage-delivery-20261019.zip；內含最新完整 fcn-audit-latest.bundle、原始9份Patch、recovery分支自858b8d9起全部Patch、交接與實價證據、鎖定依賴、MANIFEST.json／SHA256SUMS.txt。保留所有舊保存包與本地提交備份分支。

下方新版 clone 指令仍適用（分支 codex-audit-recovery）。安裝相同Python3.12鎖定依賴後預期184項通過；Streamlit AppTest需要允許本機loopback socket。若沙箱阻擋請在正常授權的本機環境跑測試，不跳過或降低測試。實價重播指令：python scripts/audit_ko_market.py。

最新版README、Commit SHA及Bundle SHA256以保存包MANIFEST.json為準；原始和recovery兩組Patch不能混合套用。main不曾合併或部署。本輪Sheets寫入0次，沒有需要重放的資料寫入。

## 最新保存包｜2026-10-19
使用 FCN-recovery-v2-delivery-20261019.zip；內含 fcn-audit-latest.bundle、原始 9 份 Patch、本輪 recovery 分支全部 Patch、鎖定依賴清單、交接文件及 MANIFEST.json／SHA256SUMS.txt。原始 audit/fcn-20261019（cb3e895）與本輪 audit/v2-local-20261019 均保留。舊保存包未刪除。

新版重建（PowerShell、Git、Python 3.12）：

```powershell
git bundle verify ./fcn-audit-latest.bundle
git clone -b codex-audit-recovery ./fcn-audit-latest.bundle fcn-restored
Set-Location fcn-restored
git log -1 --oneline
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r docs/audit/requirements-audit-lock.txt
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
git remote set-url origin https://github.com/monstervincentw-glitch/fcn-portfolio-pro-demo.git
```

預期 142 passed；不包含憑證或客戶資料。Patch 亦可從基準 858b8d9 依序 git am 還原；原始／recovery 兩組是不同歷史，不可混用，優先 Bundle。

GitHub 已有 codex-audit-recovery 與草稿 PR #1；Connector 可寫入，終端機仍缺憑證。不要照下方舊記錄另建重複 PR。不得直接推送或合併 main。復原後先讀 NEXT_STEPS.md；本輪沒改 Sheets，歷史 SA94 修正也不可盲目重放。

## 以下為第一版保存記錄

日期：2026-10-19；狀態：DONE（Bundle 已驗證）；保存基準 SHA：7b95b5e2b752a9741d2424ff14e93aca6e5e16eb。

原始四個 Commit：dd43192、ab5b4d5、aa32d4d、7b95b5e。完整歷史檔 fcn-audit-20261019.bundle 位於專案 repo 的上一層；audit-patches/ 保存四份原始 Patch。Bundle 不含 .venv、Secrets 或客戶資料。

Git push 無登入憑證；GitHub Connector 建立分支回覆 403 Resource not accessible by integration。未建立遠端分支／PR，未改遠端 main。這是寫入權限限制，不是測試失敗。

## 從 Bundle 還原（PowerShell，Git 與 Python 3.12）

將 Bundle 下載至自己的持久備份位置。於新目錄執行：

```powershell
git clone -b audit/fcn-20261019 ./fcn-audit-20261019.bundle fcn-restored
Set-Location fcn-restored
git log -5 --oneline
git fsck --no-reflogs
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

第一版 Bundle 對應 7b95b5e、61 passed。後續完整包 fcn-audit-latest.bundle 含本次續跑文件與稽核結果，操作相同；要重現本次環境，改安裝 `docs/audit/requirements-audit-lock.txt`（Python 3.12 / Windows）。不保證不同作業系統的完全相同相依版本可用。

## 有寫入權限後推送與建立 PR

使用 Git Credential Manager 正常登入；不要將 token 放入 remote URL、文件或命令紀錄。

```powershell
git remote set-url origin https://github.com/monstervincentw-glitch/fcn-portfolio-pro-demo.git
git fetch origin
git push -u origin audit/fcn-20261019
```

在 GitHub 建立 base=main、compare=audit/fcn-20261019 的 PR。未驗收項目請保留為草稿，不直接合併部署。遠端 main 若有新提交，先比較差異並解決衝突，禁止 force push main。

四份 Patch 亦可在基準 858b8d941029c82997b1e372ddea49c182242fe6 的新分支依序 `git am` 還原；Bundle 優先，因能完整保留原 Commit SHA。SA94 的遠端 Sheets 單格修復不會由 Git 自動重放，讀取備份與現值後再決定，避免盲目覆寫。

## 驗證

本次重新執行 61 passed in 1.08s；git fsck 無錯誤；git bundle verify 確認 complete history。第一版 Bundle SHA256：9F36CEC5DA691FD2841C6A38A9A0072247E06D137A4DC199DEE851E44DA87BC2。

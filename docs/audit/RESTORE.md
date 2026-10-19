# 稽核成果重建與推送

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

"""FCN Portfolio Pro — central Google Sheets product library.

This is a native Streamlit multipage entry point. Upload it to `pages/` and
upload `central_catalog.py` + `central_catalog_page.py` to the repo root.
There is NO change to the existing streamlit_app.py, PIN flow, or Secrets.
"""
from __future__ import annotations

import streamlit as st

from central_catalog_page import render_central_catalog
from sheets_backend import SheetConnectionError, SheetsReader, validate_masked_portfolio
from site_login import gate, logout
from v2_portfolio_adapter import enrich_new_holdings

st.set_page_config(
    page_title="中央商品庫｜FCN Portfolio Pro",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _secret_group(name: str) -> dict:
    """Match the existing site's fail-closed Secrets handling."""
    try:
        return dict(st.secrets.get(name, {}))
    except Exception:
        return {}


app = _secret_group("app")
mode = str(app.get("mode", "demo")).strip().lower()

# The existing six-digit server-side PIN gate runs BEFORE any Google read.
gate(_secret_group("site_login"), mode, bank_approved=app.get("bank_approved") is True)

with st.sidebar:
    st.markdown("### ◈ FCN Portfolio Pro")
    st.caption("中央商品庫｜私人 Google Sheets 唯讀連線")
    st.button("安全登出", on_click=logout, use_container_width=True)
    st.caption("原網站的所有其他功能均未變更。")

st.title("📚 FCN 中央商品庫")
st.caption("商品條款與歷史行情由自有 Google Sheets 讀取，不使用 Yahoo、GOOGLEFINANCE 或每檔獨立 FCN 檔案。")

# Do not silently turn on real client data just because a product workbook
# has been shared. Preserve all of the existing application's live-mode rules.
if mode not in {"demo", "diagnostic", "live"}:
    st.error("不支援的資料模式；系統已停止。")
    st.stop()
if mode == "demo":
    st.info("目前網站為 DEMO 模式。為避免混用真實資料，本頁不會讀取中央商品庫。請先依銀行資訊安全規範啟用正式唯讀模式。")
    st.stop()
if mode == "diagnostic":
    st.info("目前為 diagnostic 模式，僅用於既有總帳連線診斷；本頁不顯示商品或客戶資料。")
    st.stop()
if app.get("bank_approved") is not True:
    st.error("正式資料模式尚未通過 bank_approved 安全檢查。")
    st.stop()

svc = _secret_group("gcp_service_account")
master_id = str(app.get("master_sheet_id") or "").strip()
if not svc or not master_id:
    st.error("請先在 Streamlit Secrets 設定既有唯讀 Google 服務帳號及總帳 ID。")
    st.stop()
try:
    reader = SheetsReader.from_secrets(svc, master_id)
except SheetConnectionError as exc:
    st.error(str(exc))
    st.stop()

# The product catalog is independent of the customer portfolio. If the
# existing portfolio read fails, the product page can still be inspected, but
# it will not invent customer holdings or show an unvalidated customer name.
holdings: list[dict] = []
try:
    portfolio = validate_masked_portfolio(reader.portfolio(model_only=True))
    holdings = portfolio.get("holdings", [])
except SheetConnectionError:
    st.warning("原客戶總帳目前無法讀取；下方承作客戶區僅顯示空白。商品條款及歷史行情仍可獨立檢視。")

# Native page reruns do not execute streamlit_app.py. Refresh the same central
# snapshot and replace legacy ledger estimates here as well, even without holdings.
holdings = enrich_new_holdings(reader, holdings)
render_central_catalog(reader, holdings)

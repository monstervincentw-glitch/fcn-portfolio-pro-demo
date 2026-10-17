"""PIN-gated, read-only Streamlit central FCN product catalog page."""
from __future__ import annotations

import datetime as dt

import altair as alt
import pandas as pd
import streamlit as st

from central_catalog import (
    CatalogSchemaError, barriers_for_chart, load_catalog, load_history,
    to_day, verified_for_barriers, history_as_relative, _today_taipei,
)
from chart_render import build_stock_chart
from fcn_customer_panel import render_product_clients
from sheets_backend import SheetConnectionError


def _percent(x: object) -> str:
    try:
        if x is None or str(x).strip() == "":
            return "—"
        return f"{float(x) * 100:.2f}%"
    except (TypeError, ValueError, OverflowError):
        return "—"


def _date(x: object) -> str:
    day = to_day(x)
    return day.isoformat() if day else "—"


def render_central_catalog(reader, holdings: list[dict]) -> None:
    """Use only AFTER existing site_login.gate and MODE == 'live' checks."""
    st.subheader("📚 FCN 中央商品庫｜Google Sheets")
    st.caption("直接讀取中央 Google Sheets 的 API_商品條款_V1、API_標的_V1、歷史行情_核心。"
               "無外部即時行情，也不逐檔讀取 FCN Chart。")
    try:
        catalog = load_catalog(reader)
    except (SheetConnectionError, CatalogSchemaError):
        st.error("無法讀取中央商品庫。請確認中央試算表已分享給網站唯讀服務帳號，並核對 API 欄位。")
        return
    if not catalog.products:
        st.info("中央資料庫還沒有可讀的商品。")
        return
    col1, col2 = st.columns([1, 2])
    with col1:
        only_complete = st.checkbox("只顯示已填條款商品", value=True)
    ids = sorted(pid for pid, prod in catalog.products.items()
                 if not only_complete or str(prod.get("data_state") or "") == "來源表已提取")
    if not ids:
        st.info("目前沒有符合篩選的商品。")
        return
    with col2:
        selected = st.selectbox("選擇 FCN 商品代號", ids, index=ids.index("SR67") if "SR67" in ids else 0)
    product = catalog.products[selected]
    legs = catalog.legs.get(selected, ())
    st.caption(f"中央庫共 {len(catalog.products)} 個商品代號；本商品 {len(legs)} 檔連結標的。"
               "未核實／未啟用者僅供內部參考。")
    tabs = st.tabs(["商品條款", "歷史股價與圖表", "資料核對"])
    with tabs[0]:
        a, b, c = st.columns(3)
        a.metric("年化票息（條款值）", _percent(product.get("annual_coupon_rate")))
        b.metric("KO 門檻", _percent(product.get("ko_barrier_ratio")))
        c.metric("Strike 執行價", _percent(product.get("strike_ratio")))
        st.dataframe(pd.DataFrame([{
            "股票代號": x.get("ticker"), "期初股價": x.get("initial_price"),
            "KO 價格": x.get("ko_price"), "KI 價格": x.get("ki_price"),
            "Strike 價格": x.get("strike_price"), "行情核對": x.get("quote_review"),
        } for x in legs]), hide_index=True, use_container_width=True)
        st.caption("幣別：" + str(product.get("currency") or "—")
                   + "｜期初定價：" + _date(product.get("pricing_date"))
                   + "｜KO 觀察起日：" + _date(product.get("ko_start_date"))
                   + "｜期末評價：" + _date(product.get("final_eval_date")))
        st.caption("KO 類型：" + str(product.get("ko_type") or "待核")
                   + "｜KI 類型：" + str(product.get("ki_type") or "待核"))
    with tabs[1]:
        if not legs:
            st.info("本商品尚未輸入連結標的，無法畫圖。")
        else:
            try:
                records, missing = load_history(reader, [x["ticker"] for x in legs])
            except (SheetConnectionError, CatalogSchemaError):
                st.warning("歷史行情未能從中央庫載入；不使用外部來源補價。")
                records, missing = [], []
            if missing:
                st.warning("內部歷史股價庫沒有以下股票：" + ", ".join(missing))
            df = pd.DataFrame.from_records(records, columns=["date", "stock", "close"])
            if df.empty:
                st.info("尚無符合條件的內部歷史收盤價。")
            else:
                latest = max(r["date"] for r in records)
                freshness = (_today_taipei() - latest).days
                st.caption(f"歷史資料最後交易日：{latest.isoformat()}。"
                           "原始價格固定儲存於 Google Sheets，不是即時報價。")
                if freshness > 4:
                    st.warning("行情超過 4 個日曆日未更新，請先檢查股價資料庫。")
                symbol_latest = {symbol: max((p["date"] for p in records if p["stock"] == symbol),
                                             default=None)
                                 for symbol in [leg["ticker"] for leg in legs]}
                all_symbols_fresh = all(last is not None and (_today_taipei() - last).days <= 4
                                        for last in symbol_latest.values())
                ready = all_symbols_fresh and verified_for_barriers(product, legs, latest)
                if ready and not missing:
                    relative = pd.DataFrame(history_as_relative(records, legs, product))
                    if relative.empty:
                        st.warning("定價日與歷史資料無交集，無法進行 KO／KI 比價。")
                    else:
                        stock_plot = build_stock_chart(relative, barriers_for_chart(product),
                                                       sorted(relative.stock.unique().tolist()))
                        st.altair_chart(stock_plot, use_container_width=True)
                        st.caption("KO／KI／Strike 為模型障礙水準，不代表銀行正式認定的結算結果。")
                else:
                    st.warning("合約條款、公司行動／價格可比性或行情時效尚未全部核對；"
                               "目前只顯示個別股票的歷史收盤價，不顯示 KO／KI 觸發推定。")
                    d = df.copy()
                    d["date"] = pd.to_datetime(d["date"])
                    d = d.sort_values(["stock", "date"])
                    chart = (alt.Chart(d).mark_line()
                             .encode(x=alt.X("date:T", title="交易日期"),
                                     y=alt.Y("close:Q", title="收盤價（原幣）", scale=alt.Scale(zero=False)),
                                     tooltip=[alt.Tooltip("date:T", title="日期", format="%Y/%m/%d"),
                                              "stock:N", "close:Q"])
                             .properties(height=170).facet(row=alt.Row("stock:N", title=None))
                             .resolve_scale(y="independent"))
                    st.altair_chart(chart, use_container_width=True)
    with tabs[2]:
        st.write("來源：中央商品參數庫（私人 Google Sheets，唯讀）。")
        st.write("條款審核：", product.get("contract_review_state") or "待核")
        st.write("資料狀態：", product.get("data_state") or "待補")
        st.write("正式啟用：", product.get("website_visible") or "否")
        st.caption("如需修改條款、標的或 12 期配息，僅編輯中央參數庫「商品完整參數輸入」。"
                   "本網頁不提供寫入功能；原客戶總帳及現金流未改動。")
        if product.get("source_note"):
            st.warning("來源條款註記：" + str(product["source_note"]))
    st.divider()
    # Existing masked client list is always at the BOTTOM and collapsed by default.
    render_product_clients(selected, holdings, mode="live")

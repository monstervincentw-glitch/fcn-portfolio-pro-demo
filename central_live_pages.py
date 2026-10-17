"""Central-source pages for FCN Portfolio Pro.

The site's original PIN, customer/holding/cash-flow ledger, demo mode and
exception handling remain unchanged. This module reads only the centralized
product API and its Sheets price matrix; it never opens per-product Chart
workbooks, never writes Google Sheets, and never fetches prices from the web.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import pandas as pd

from central_catalog import (
    Catalog, CatalogSchemaError, CENTRAL_CATALOG_ID, as_positive_number, barriers_for_chart,
    history_as_relative, load_catalog, load_history, to_day,
    verified_for_barriers, _today_taipei,
)
from sheets_backend import SheetConnectionError


@dataclass(frozen=True)
class ProductGroup:
    category: str
    note: str
    key_date: dt.date | None


def code(value: object) -> str:
    return str(value or "").strip()


def _date(value: object) -> str:
    day = to_day(value)
    return day.strftime("%Y/%m/%d") if day else "—"


def _pct(value: object) -> str:
    v = as_positive_number(value)
    return f"{v * 100:.2f}%" if v is not None else "—"


def contract_complete(product: dict, legs: tuple[dict, ...]) -> bool:
    """Completeness != bank verification; never infer an approval from filled cells."""
    if not legs:
        return False
    required = ("pricing_date", "ko_start_date", "final_eval_date", "maturity_date")
    return all(to_day(product.get(k)) is not None for k in required)


def classify(product: dict, legs: tuple[dict, ...], *, today: dt.date) -> ProductGroup:
    """Classify central *model*, not bank settlement; missing data stays pending."""
    if not contract_complete(product, legs):
        return ProductGroup("待建檔", "商品條款或連結標的不足", None)
    start = to_day(product.get("ko_start_date"))
    mature = to_day(product.get("maturity_date"))
    model_ko = to_day(product.get("model_ko_date"))
    state = code(product.get("model_state"))
    exited_model = state in ("模型已KO", "模型提前KO", "模型已提前KO") and model_ko and model_ko <= today
    three_months_ago = (pd.Timestamp(today) - pd.DateOffset(months=3)).date()
    if exited_model:
        return ProductGroup("近三個月模型出場" if model_ko >= three_months_ago else "歷史歸檔",
                            "模型顯示已 KO；銀行實際贖回仍待核實", model_ko)
    if mature and mature < today:
        return ProductGroup("近三個月模型出場" if mature >= three_months_ago else "歷史歸檔",
                            "到期日已過；銀行實際結算仍待核實", mature)
    if start and today < start:
        return ProductGroup("閉鎖中", "尚未到 KO 觀察起日（依中央條款日期）", start)
    if start and mature and start <= today <= mature:
        return ProductGroup("比價中", "進入 KO 觀察期間（模型狀態、非銀行確認）", start)
    return ProductGroup("待建檔", "日期或模型狀態需人工核對", None)


def dashboard_breakdown(catalog: Catalog, holdings: list[dict], *, today: dt.date) -> tuple[dict, list[dict]]:
    """One held FCN is one product; never count underlying leg or client twice."""
    buckets = {x: [] for x in ("閉鎖中", "比價中", "近三個月模型出場", "近兩週到期")}
    problems = []
    held = sorted({code(h.get("product_id")) for h in holdings if code(h.get("product_id"))})
    for pid in held:
        product = catalog.products.get(pid)
        if not product:
            problems.append({"FCN": pid, "原因": "中央商品庫沒有此代號；不使用舊商品表替代"})
            continue
        classification = classify(product, catalog.legs.get(pid, ()), today=today)
        maturity = to_day(product.get("maturity_date"))
        record = {"FCN": pid, "參考日期": classification.key_date.isoformat() if classification.key_date else "—",
                  "模型與資料說明": classification.note}
        if classification.category in ("閉鎖中", "比價中", "近三個月模型出場"):
            buckets[classification.category].append(record)
        elif classification.category == "待建檔":
            problems.append({"FCN": pid, "原因": classification.note})
        if classification.category in ("閉鎖中", "比價中") and maturity and today <= maturity <= today + dt.timedelta(days=14):
            buckets["近兩週到期"].append({"FCN": pid, "參考日期": maturity.isoformat(),
                                       "模型與資料說明": "即將到期；非銀行確認的交割日期"})
    return buckets, problems


def exposure_rows(catalog: Catalog, symbol: str, holdings: list[dict]) -> list[dict]:
    """Never fetch per-product Charts to do simple ticker membership."""
    ticker = code(symbol).upper()
    if not ticker:
        return []
    held = {code(h.get("product_id")) for h in holdings}
    rows = []
    for pid in sorted(catalog.products):
        product = catalog.products[pid]
        for leg in catalog.legs.get(pid, ()):
            if code(leg.get("ticker")).upper() != ticker:
                continue
            rows.append({"FCN 代號": pid, "是否在持倉總帳": "是" if pid in held else "否",
                         "計價幣別": code(product.get("currency")) or "—",
                         "模型狀態": code(product.get("model_state")) or "待補",
                         "條款核對": code(product.get("contract_review_state")) or "待核",
                         "股價可比性": code(leg.get("quote_review")) or "待核",
                         "期初價格": leg.get("initial_price")})
    return rows


def coupon_schedule(reader, product_id: str) -> list[dict]:
    """Central contractual observation/payment dates, not realized coupons."""
    values = reader.read(CENTRAL_CATALOG_ID, "'配息期'!A1:I1201")
    if not values or "商品代號" not in values[0] or "配息期" not in values[0]:
        raise CatalogSchemaError("中央配息期表頭不存在或已變更")
    result = []
    for row in values[1:]:
        padded = list(row) + [None]*max(0, 6-len(row))
        if code(padded[1]) != product_id:
            continue
        try:
            number = int(padded[2])
        except (TypeError,ValueError,OverflowError):
            continue
        result.append({"期數":number,"期初日":_date(padded[3]),
                       "觀察期末":_date(padded[4]),"契約付款日":_date(padded[5])})
    result.sort(key=lambda row:row["期數"])
    return result


def _get_catalog(reader) -> Catalog | None:
    import streamlit as st
    try:
        return load_catalog(reader)
    except (SheetConnectionError, CatalogSchemaError):
        st.error("中央參數庫讀取失敗或欄位格式錯誤。正式監控不會退回各商品獨立 Chart；請檢查服務帳號 Viewer 權限與 API 分頁。")
        return None


def render_dashboard(reader, holdings: list[dict]) -> None:
    import streamlit as st
    st.subheader("📋 FCN 商品狀態｜中央參數庫")
    st.caption("商品分類與合約日期從中央庫取得；統計範圍限原持倉總帳內的 FCN，一代號算一檔。銀行實際收付仍依原總帳。")
    catalog = _get_catalog(reader)
    if catalog is None:
        return
    buckets, problems = dashboard_breakdown(catalog, holdings, today=_today_taipei())
    labels = ["閉鎖中", "比價中", "近三個月模型出場", "近兩週到期"]
    cols = st.columns(4)
    for col, name in zip(cols, labels):
        with col:
            st.metric(name, f"{len(buckets[name])} 檔")
            if st.button("查看清單", key="central_dashboard_"+name, use_container_width=True):
                st.session_state["central_dashboard_bucket"] = name
    chosen = st.session_state.get("central_dashboard_bucket", labels[0])
    if chosen not in buckets:
        chosen = labels[0]
    st.markdown(f"#### {chosen}｜{len(buckets[chosen])} 檔")
    if buckets[chosen]:
        st.dataframe(pd.DataFrame(buckets[chosen]), hide_index=True, use_container_width=True)
    else:
        st.info("本分類目前沒有符合條件的已承作商品。")
    if problems:
        with st.expander(f"中央條款待補／找不到代號：{len(problems)} 檔"):
            st.dataframe(pd.DataFrame(problems), use_container_width=True, hide_index=True)
    st.caption("『近兩週到期』可與閉鎖／比價重疊；模型 KO 不等於銀行已贖回。中央價格超過時效時，請勿推定是否觸及 KO/KI。")


def render_exposure(reader, holdings: list[dict]) -> None:
    import streamlit as st
    st.subheader("🔎 股票曝險｜中央連結標的")
    st.caption("股票與 FCN 的對應關係直接取自中央參數庫，包含未持有商品；不讀取個別 FCN Chart。")
    catalog = _get_catalog(reader)
    if catalog is None:
        return
    symbols = sorted({code(l.get("ticker")).upper() for legs in catalog.legs.values() for l in legs if code(l.get("ticker"))})
    chosen = st.selectbox("股票代號", [""]+symbols, format_func=lambda x:x or "請選擇", key="central_exposure_symbol")
    if not chosen:
        return
    rows = exposure_rows(catalog, chosen, holdings)
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.caption(f"中央庫共有 {len(rows)} 檔 FCN 連結 {chosen}；此為標的名單，不代表真實敞口金額或銀行實際交割。")
    else:
        st.info("中央商品庫沒有這檔股票的連結商品。")


def product_overview(catalog: Catalog, ledger_products: list[dict], *, today: dt.date) -> list[dict]:
    """Only central fields determine contractual status; ledger funds are sidecars."""
    ledger={code(x.get("product_id")):x for x in ledger_products}
    result=[]
    for pid, product in sorted(catalog.products.items()):
        status=classify(product,catalog.legs.get(pid,()),today=today)
        old=ledger.get(pid,{})
        ccy=code(product.get("currency")) or code(old.get("product_currency")) or "—"
        outstanding=old.get("estimated_outstanding_"+ccy.lower()) if ccy in ("USD","EUR","JPY") else None
        result.append({"FCN":pid,"幣別":ccy,"中央分類":status.category,
                       "模型狀態":code(product.get("model_state")) or "條款待補",
                       "中央核約":code(product.get("contract_review_state")) or "待核",
                       "年化票息":_pct(product.get("annual_coupon_rate")),
                       "模型KO日":_date(product.get("model_ko_date")),
                       "到期日":_date(product.get("maturity_date")),
                       "原總帳模型未回本金":outstanding,
                       "_group":status.category})
    return result


def render_product_page(reader, holdings: list[dict], ledger_products: list[dict]) -> None:
    import altair as alt
    import streamlit as st
    from chart_render import build_stock_chart
    from fcn_customer_panel import render_product_clients

    st.markdown("#### 📈 FCN 商品監控｜中央參數正式資料源")
    st.caption("商品條款、股票組合、歷史行情：中央 Google Sheets。承作客戶／本金／現金流：原總帳（兩者分開核對）。")
    catalog = _get_catalog(reader)
    if catalog is None:
        return
    rows=product_overview(catalog, ledger_products, today=_today_taipei())
    filters=["日常監控","全部商品","待建檔","歷史歸檔"]
    col1,col2=st.columns([1,2])
    with col1:
        scope=st.selectbox("顯示範圍",filters,key="central_product_scope")
    with col2:
        search=st.text_input("搜尋 FCN 代號",key="central_product_search").strip().upper()
    def keep(row):
        if search and search not in row["FCN"].upper():
            return False
        category=row["_group"]
        if scope=="日常監控": return category in ("閉鎖中","比價中","近三個月模型出場")
        if scope=="待建檔": return category=="待建檔"
        if scope=="歷史歸檔": return category=="歷史歸檔"
        return True
    shown=[r for r in rows if keep(r)]
    st.dataframe(pd.DataFrame([{k:v for k,v in r.items() if k!="_group"} for r in shown]),
                 use_container_width=True,hide_index=True)
    st.caption(f"中央商品庫共 {len(rows)} 個 FCN 代號；目前顯示 {len(shown)} 檔。未填條款不會被當作已結清。")
    if not shown:
        st.info("這個篩選沒有商品；切換『全部商品』可確認中央庫目前所有代號。")
        return
    selected=st.selectbox("開啟商品詳情",[r["FCN"] for r in shown],key="central_product_selected")
    prod=catalog.products[selected]
    legs=catalog.legs.get(selected,())
    st.markdown(f"#### {selected}｜{code(prod.get('currency')) or '—'}")
    st.caption("中央模型狀態："+(code(prod.get("model_state")) or "待補")+
               "；銀行實際結算應另由總帳／對帳單確認。")
    if not contract_complete(prod,legs):
        st.warning("此 FCN 中央條款尚未補齊，無法計算商品價格圖及 KO/KI 指標；請先在『商品完整參數輸入』填寫。");
        render_product_clients(selected, holdings, mode="live")
        return
    m1,m2,m3=st.columns(3)
    m1.metric("年化票息",_pct(prod.get("annual_coupon_rate")))
    m2.metric("KO 障礙比例",_pct(prod.get("ko_barrier_ratio")))
    m3.metric("Strike 比例",_pct(prod.get("strike_ratio")))
    st.caption("期初訂價："+_date(prod.get("pricing_date"))+"｜KO觀察起日："+_date(prod.get("ko_start_date"))+
               "｜期末評價日："+_date(prod.get("final_eval_date"))+"｜合約到期："+_date(prod.get("maturity_date")))
    st.caption("KO 類型："+(code(prod.get("ko_type")) or "待核")+
               "｜KI 類型："+(code(prod.get("ki_type")) or "待核")+
               "｜契約審核："+(code(prod.get("contract_review_state")) or "待核"))
    st.dataframe(pd.DataFrame([{"股票":x["ticker"],"期初價":x.get("initial_price"),
                               "KO價":x.get("ko_price"),"KI價":x.get("ki_price"),
                               "Strike價":x.get("strike_price"),"股價核對":x.get("quote_review")}
                              for x in legs]),hide_index=True,use_container_width=True)
    with st.expander("中央合約配息／觀察期日期", expanded=False):
        try:
            periods = coupon_schedule(reader, selected)
            if periods:
                st.dataframe(pd.DataFrame(periods), hide_index=True, use_container_width=True)
                st.caption("此表只呈現契約日期；模型配息金額和銀行實際入帳仍由原總帳管理，不在此重算或假定收到。")
            else:
                st.info("此商品中央庫尚未填寫配息期日期。")
        except (SheetConnectionError, CatalogSchemaError):
            st.warning("中央配息期無法讀取或表頭格式錯誤。")
    try:
        hist,missing=load_history(reader,[l["ticker"] for l in legs])
    except (SheetConnectionError,CatalogSchemaError):
        st.error("無法讀取中央歷史行情，不會從商品舊 Chart 或外部網站補入缺漏股價。")
        hist,missing=[],[]
    if missing:
        st.warning("中央股價庫尚缺標的："+"、".join(missing))
    if hist:
        latest_per={k:max((r["date"] for r in hist if r["stock"]==k),default=None)
                    for k in [l["ticker"] for l in legs]}
        complete_fresh=all(day is not None and 0<=(_today_taipei()-day).days<=4 for day in latest_per.values())
        last=max(r["date"] for r in hist)
        st.caption(f"中央歷史行情最後日期：{last.isoformat()}（固定收盤價，非即時行情）。")
        safe=complete_fresh and not missing and verified_for_barriers(prod,legs,last)
        if safe:
            relative=pd.DataFrame(history_as_relative(hist,legs,prod))
            if not relative.empty:
                chart=build_stock_chart(relative,barriers_for_chart(prod),sorted(relative.stock.unique().tolist()))
                st.altair_chart(chart,use_container_width=True)
                st.caption("圖上的 KO／KI／Strike 為合約模型價格比例，並非銀行正式敲入／敲出認定。")
            else:
                st.warning("定價期間沒有可用行情，無法畫正規化比價。")
        else:
            st.warning("中央行情目前尚未完成時效、契約或拆股／可比性核對：僅展示歷史原始收盤價，不標示 KO／KI 觸發或計算緩衝。")
            illustrative=st.checkbox("以期初價 100% 顯示未核對的相對走勢（僅資料視覺化）", value=False)
            if illustrative:
                display=pd.DataFrame(history_as_relative(hist,legs,prod))
                if not display.empty:
                    display["date"]=pd.to_datetime(display["date"])
                    st.altair_chart((alt.Chart(display).mark_line().encode(
                        x=alt.X("date:T",title="交易日期"),
                        y=alt.Y("ratio:Q",title="相對期初價（%）— 未核對",scale=alt.Scale(zero=False)),
                        color=alt.Color("stock:N",title="股票"),
                        tooltip=[alt.Tooltip("date:T",format="%Y/%m/%d"),"stock:N","ratio:Q"]
                    ).properties(height=330).interactive()),use_container_width=True)
                    st.caption("示意百分比使用中央庫提供的合約期初價；尚未核對公司行動，絕不可用於 KO/KI/Strike 判斷。")
                else:
                    st.info("此商品定價期間尚無可比的歷史行情。")
            else:
                df=pd.DataFrame(hist)
                df["date"]=pd.to_datetime(df["date"])
                chart=(alt.Chart(df).mark_line().encode(
                    x=alt.X("date:T",title="交易日期"),
                    y=alt.Y("close:Q",title="收盤價（原單位）",scale=alt.Scale(zero=False)),
                    color=alt.Color("stock:N",title="連結股票"),
                    tooltip=[alt.Tooltip("date:T",title="日期",format="%Y/%m/%d"),"stock:N","close:Q"]
                ).properties(height=330).interactive())
                st.altair_chart(chart,use_container_width=True)
        if len(set(day for day in latest_per.values() if day is not None))>1:
            st.caption("注意：各標的最後可用行情日可能不同，不應視為同一交易日比較。")
    else:
        st.info("本商品尚無可用的中央歷史收盤價。")
    if prod.get("source_note"):
        st.caption("原始條款備註："+str(prod["source_note"]))
    render_product_clients(selected, holdings, mode="live")

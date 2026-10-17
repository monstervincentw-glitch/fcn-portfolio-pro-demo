"""FCN trial screen: arbitrary US symbols -> external market data -> existing V2 model.

This module is isolated from customers, holdings, and Google Sheets. It is a
feature expansion, not a modification of the ledger or coupon settlement rules.
"""
from __future__ import annotations

import datetime as dt

import altair as alt
import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta

from market_data import MarketFeedError, fetch_daily_closes, verify_pricing_session
from virtual_trial import TrialInputs, TrialDataError, parse_symbols, simulate_history
from warm_theme import COLORS, LEVEL_COLORS, page_intro, style_chart


def _market_key() -> str:
    try:
        return str(st.secrets.get("market_data", {}).get("api_key", ""))
    except Exception:
        return ""


def render_market_trial() -> None:
    page_intro("FCN 自由試打", "任意美股組合，按下執行就向外部行情服務查詢，套用既有 V2 模型。", "MARKET-ON-DEMAND SCENARIO")
    st.info("本頁行情獨立來自市場資料供應商，**不是 Google Sheets 既有商品清單**。"
            "若站點仍為 DEMO 模式，其餘客戶頁仍是虛構資料；試打條款及收益一律為假設情境。")
    st.caption("本版以供應商的 **美股每日歷史收盤價** 計算；按試打時即時查詢，不代表盤中即時報價。"
               "交易日、合約事件、除權與股價調整應以正式契約另行核對。")

    with st.form("v82_market_trial_form"):
        st.markdown("#### 01　選擇股票與期初")
        left,right = st.columns(2)
        with left:
            tickers_text = st.text_input("美股代號（1～5 檔）", value="NVDA,AMD,MU", help="不必事先在 Google Sheets 建立商品")
            mode = st.radio("期初模式", ["指定期初定價日", "快速模式：當月首個共同交易日"], horizontal=False)
            if mode.startswith("指定"):
                d = st.date_input("期初定價日", value=dt.date(2026, 7, 20), format="YYYY/MM/DD")
                first_month = None
            else:
                first_month = st.text_input("期初月份（YYYY-MM）", value="2026-07")
                d = None
        with right:
            tenor = st.number_input("合約期間（月）", min_value=1, max_value=12, value=3, step=1)
            lock = st.number_input("閉鎖期（月）", min_value=0, max_value=11, value=1, step=1)
            coupon = st.number_input("預估年化票息 (%)", min_value=0., max_value=100., value=20., step=.1)
            principal = st.number_input("假設本金（USD）", min_value=1., value=100000., step=10000.)
        with st.expander("02　進階條款（V2 KO／Strike／KI）"):
            c1,c2,c3,c4 = st.columns(4)
            ko = c1.number_input("KO (%)", min_value=1., max_value=300., value=100.)
            strike = c2.number_input("Strike (%)", min_value=1., max_value=200., value=75.)
            ki_mode = c3.selectbox("KI 類型", ["EKI", "AKI", "Non-KI"])
            ki = c4.number_input("KI (%)", min_value=1., max_value=200., value=65.)
        submitted = st.form_submit_button("即時取得行情 · V2 自由試打", type="primary", use_container_width=True)

    if submitted:
        st.session_state.pop("v82_market_trial", None)
        try:
            symbols = parse_symbols(tickers_text)
            if d is not None:
                chosen = d
            else:
                import re
                if not re.fullmatch(r"\d{4}-(0?[1-9]|1[0-2])", str(first_month or "")):
                    raise TrialDataError("期初月份格式須為 YYYY-MM。")
                yy,mm=(int(x) for x in first_month.split("-"))
                chosen=dt.date(yy,mm,1)
            if chosen > dt.date.today():
                raise MarketFeedError("期初日期在未來，尚無歷史行情；請改選過去日期。")
            params = TrialInputs(symbols,chosen,int(tenor),int(lock),float(coupon),float(principal),
                                 float(ko),float(strike),float(ki) if ki_mode != "Non-KI" else None,ki_mode)
            params.validate()
            api_key = _market_key()
            # Fetch from the chosen day through maturity + settlement buffer; only
            # data up to today is requested. The simulator prevents look-ahead.
            expected_issue = chosen + dt.timedelta(days=9)  # generous search buffer, not contractual issue date
            until = min(dt.date.today(), expected_issue + relativedelta(months=int(tenor), days=14))
            with st.spinner("正在取得每檔股票的最新可用歷史收盤價…"):
                data, meta = fetch_daily_closes(symbols,chosen,until,api_key)
            if d is not None:
                verify_pricing_session(data,chosen,symbols)
            trial = simulate_history(data,params,as_of=dt.date.today())
            st.session_state["v82_market_trial"] = (trial,params,meta)
        except (MarketFeedError, TrialDataError, ValueError) as e:
            st.warning(str(e))

    if "v82_market_trial" not in st.session_state:
        return
    trial,params,meta=st.session_state["v82_market_trial"]
    page_intro("試打結果",trial["status"],"V2 HISTORICAL SIMULATION")
    if dt.date.today() > meta.last_date + dt.timedelta(days=7):
        st.warning("行情資料日期已超過七天，請確認供應商與方案。")
    st.caption(f"資料商：{meta.provider}｜{meta.adjustment}｜最後交易日：{meta.last_date}｜"
               f"共同交易日：{meta.observed_common_days}。無行情日期不會補造收盤價。")
    a,b,c=st.columns(3)
    a.metric("模型可估票息",f"{trial['coupon_pct']:.4f}%")
    b.metric("模型本金回收", "尚不可判定" if trial['principal_return_pct'] is None else f"{trial['principal_return_pct']:.2f}%")
    c.metric("模型總損益率", "尚不可判定" if trial['total_return_pct'] is None else f"{trial['total_return_pct']:.4f}%")
    if trial['total_profit_amount'] is not None:
        st.metric("模型淨損益（USD）",f"USD {trial['total_profit_amount']:,.2f}")
    else:
        st.info("尚無足夠行情觀察到 KO 或期末，不顯示確定的本金和總損益。")
    st.caption(f"期初定價：{trial['pricing_date']}｜推估起息：{trial['estimated_issue_date']}｜"
               f"預定期末：{trial['scheduled_maturity']}｜KO：{trial['ko_date'] or '尚未發生或資料不足'}")
    frame=trial['chart']
    base=alt.Chart(frame).encode(
        x=alt.X("date:T",title="交易日期"),
        y=alt.Y("ratio:Q",title="相對期初定價 (%)",scale=alt.Scale(zero=False)))
    stock=base.mark_line(strokeWidth=2.6).encode(
        color=alt.Color("stock:N",title="連結標的",scale=alt.Scale(domain=list(params.symbols),range=COLORS[:len(params.symbols)])),
        tooltip=[alt.Tooltip("date:T",title="交易日期"),"stock:N",alt.Tooltip("ratio:Q",title="比價 (%)",format=".2f")])
    levels=[{"name":"KO","level":params.ko_pct},{"name":"Strike","level":params.strike_pct}]
    if params.ki_type!="Non-KI" and params.ki_pct is not None:
        levels.append({"name":"KI","level":params.ki_pct})
    barriers=alt.Chart(pd.DataFrame(levels)).mark_rule(strokeDash=[5,4]).encode(
        y="level:Q",color=alt.Color("name:N",title="參考門檻",scale=alt.Scale(domain=["KO","Strike","KI"],range=LEVEL_COLORS)))
    rule=alt.Chart(pd.DataFrame({"date":[pd.Timestamp(trial["ko_start"])]})).mark_rule(color="#8A7660",strokeDash=[2,4]).encode(x="date:T")
    st.altair_chart(style_chart((stock+barriers+rule).resolve_scale(color="independent").properties(height=390).interactive()),use_container_width=True)
    st.subheader("模型配息期間明細")
    st.dataframe(pd.DataFrame(trial['coupon_steps']),use_container_width=True,hide_index=True)
    st.caption("試打不是銀行實際合約或交割結果。除權事件、交易所休市、盤中股價與發行人條款仍需獨立核對。")

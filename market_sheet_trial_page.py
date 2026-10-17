"""FCN V8.4 trial UI: use stored real CLOSE prices; no Massive calls, no writes."""
from __future__ import annotations
import datetime as dt
import re
import altair as alt
import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta
from market_sheet_data import fetch_sheet_closes
from market_data import MarketFeedError, verify_pricing_session
from virtual_trial import TrialInputs,TrialDataError,parse_symbols,simulate_history
from warm_theme import COLORS,LEVEL_COLORS,page_intro,style_chart


def _config(name:str)->dict:
    try:return dict(st.secrets.get(name,{}))
    except Exception:return {}


def render_market_trial()->None:
    page_intro('FCN 自由試打 · 真實歷史股價庫','自選美股、指定日期，直接使用 V8.4 已儲存的真實收盤價套用 V2 模型。','HISTORICAL MARKET SCENARIO')
    st.info('資料來源：獨立 Google Sheets「收盤價矩陣」。**不是客戶 FCN 總帳**，不使用虛構行情、不寫入試算表，也不消耗 Massive API 額度。')
    st.caption('股價庫目前含 2024/01/02～2026/10/16 的部分成分股歷史價格。歷史收盤價口徑及拆股／股息調整仍須按使用目的核對；結果僅供個人情境研究。')
    with st.form('v84_price_library_trial'):
        st.markdown('#### 01　自選標的與定價日')
        left,right=st.columns(2)
        with left:
            symbols_text=st.text_input('股票代號（1～5檔，逗號分隔）',value='NVDA,AMD,MU')
            mode=st.radio('期初模式',['指定期初定價日','快速模式：當月首個共同交易日'])
            if mode.startswith('指定'):
                chosen_date=st.date_input('期初定價日',value=dt.date(2026,7,20),format='YYYY/MM/DD')
                month_text=None
            else:
                chosen_date=None
                month_text=st.text_input('期初月份（YYYY-MM）',value='2026-07')
        with right:
            months=st.number_input('合約期間（月）',min_value=1,max_value=12,value=3,step=1)
            lock=st.number_input('閉鎖期（月）',min_value=0,max_value=11,value=1,step=1)
            coupon=st.number_input('年化票息（%）',min_value=0.,max_value=100.,value=20.,step=.1)
            principal=st.number_input('假設本金（USD）',min_value=1.,value=100000.,step=10000.)
        with st.expander('02　進階 V2 條款（KO / Strike / KI）'):
            c1,c2,c3,c4=st.columns(4)
            ko=c1.number_input('KO (%)',min_value=1.,max_value=300.,value=100.)
            strike=c2.number_input('Strike (%)',min_value=1.,max_value=200.,value=75.)
            ki_mode=c3.selectbox('KI 類型',['EKI','AKI','Non-KI'])
            ki=c4.number_input('KI (%)',min_value=1.,max_value=200.,value=65.)
        submitted=st.form_submit_button('讀取真實歷史股價 · V2 試打',type='primary',use_container_width=True)
    if submitted:
        st.session_state.pop('v84_sheet_trial',None)
        try:
            symbols=parse_symbols(symbols_text)
            if chosen_date is not None:
                chosen=chosen_date
            else:
                if not re.fullmatch(r'\d{4}-(0?[1-9]|1[0-2])',str(month_text or '')):
                    raise TrialDataError('月份格式應為 YYYY-MM。')
                yy,mm=map(int,month_text.split('-'))
                chosen=dt.date(yy,mm,1)
            if chosen>dt.date.today():
                raise TrialDataError('不能選擇未來日期作為歷史定價日。')
            params=TrialInputs(symbols,chosen,int(months),int(lock),float(coupon),float(principal),float(ko),float(strike),float(ki) if ki_mode!='Non-KI' else None,ki_mode)
            params.validate()
            until=min(dt.date.today(),chosen+dt.timedelta(days=9)+relativedelta(months=int(months),days=14))
            sheet_id=str(_config('price_library').get('sheet_id','')).strip()
            svc=_config('gcp_service_account')
            with st.spinner('正在從獨立 Google Sheets 讀取真實日收盤價…'):
                data,meta=fetch_sheet_closes(symbols,chosen,until,svc,sheet_id)
            if chosen_date is not None:
                verify_pricing_session(data,chosen,symbols)
            trial=simulate_history(data,params,as_of=dt.date.today())
            st.session_state['v84_sheet_trial']=(trial,params,meta)
        except (MarketFeedError,TrialDataError,ValueError) as e:
            st.warning(str(e))
    if 'v84_sheet_trial' not in st.session_state:return
    trial,params,meta=st.session_state['v84_sheet_trial']
    page_intro('試打結果',trial['status'],'V2 HISTORICAL SIMULATION')
    st.caption(f'資料來源：{meta.provider}｜價格口徑：{meta.adjustment}｜資料截止：{meta.last_date}｜共同交易日：{meta.observed_common_days}')
    if trial['scheduled_maturity']<=dt.date.today() and trial['principal_return_pct'] is None:
        st.warning('合約預定期末已過，但資料可能缺價或尚未覆蓋期末，不能推定本金回收。')
    if trial['scheduled_maturity']>meta.last_date:
        st.info('股價庫尚未涵蓋合約預定期末，模型不會推定未來股票價格。')
    a,b,c=st.columns(3)
    a.metric('模型可估票息',f"{trial['coupon_pct']:.4f}%")
    b.metric('模型本金回收','尚不可判定' if trial['principal_return_pct'] is None else f"{trial['principal_return_pct']:.2f}%")
    c.metric('模型總損益率','尚不可判定' if trial['total_return_pct'] is None else f"{trial['total_return_pct']:.4f}%")
    if trial['total_profit_amount'] is not None:
        st.metric('模型淨損益（USD）',f"USD {trial['total_profit_amount']:,.2f}")
    else:
        st.caption('尚不能核定本金或總損益，不能把理論票息視為確定收益。')
    st.caption(f"定價日 {trial['pricing_date']}｜估算起息 {trial['estimated_issue_date']}｜預定期末 {trial['scheduled_maturity']}｜KO {trial['ko_date'] or '未發生／未能判定'}")
    base=alt.Chart(trial['chart']).encode(x=alt.X('date:T',title='交易日期'),y=alt.Y('ratio:Q',title='相對期初價格 (%)',scale=alt.Scale(zero=False)))
    lines=base.mark_line(strokeWidth=2.6).encode(color=alt.Color('stock:N',title='連結標的',scale=alt.Scale(domain=list(params.symbols),range=COLORS[:len(params.symbols)])),tooltip=[alt.Tooltip('date:T',title='交易日期'),'stock:N',alt.Tooltip('ratio:Q',format='.2f')])
    barriers=[{'name':'KO','level':params.ko_pct},{'name':'Strike','level':params.strike_pct}]
    if params.ki_type!='Non-KI' and params.ki_pct is not None:barriers.append({'name':'KI','level':params.ki_pct})
    rules=alt.Chart(pd.DataFrame(barriers)).mark_rule(strokeDash=[5,4]).encode(y='level:Q',color=alt.Color('name:N',title='參考門檻',scale=alt.Scale(domain=['KO','Strike','KI'],range=LEVEL_COLORS)))
    ko_start=alt.Chart(pd.DataFrame({'date':[pd.Timestamp(trial['ko_start'])]})).mark_rule(color='#8A7660',strokeDash=[2,4]).encode(x='date:T')
    st.altair_chart(style_chart((lines+rules+ko_start).resolve_scale(color='independent').properties(height=390).interactive()),use_container_width=True)
    st.subheader('模型配息期間明細')
    st.dataframe(pd.DataFrame(trial['coupon_steps']),use_container_width=True,hide_index=True)
    st.caption('這是歷史假設試算，不是實際 FCN 合約、銀行入帳或可成交報價。')

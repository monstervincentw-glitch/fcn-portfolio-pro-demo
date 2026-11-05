from __future__ import annotations

import gzip
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from public_data import load_dashboard, classification, sorted_candidates

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title='成長股觀測站', page_icon='📊', layout='wide')
st.markdown('''<style>
.stApp{background:#f5f7fb;color:#17243b} [data-testid="stSidebar"]{background:#eaf0f7}
[data-testid="stMetric"]{background:white;border:1px solid #e0e7f0;border-radius:12px;padding:16px}
h1,h2,h3{letter-spacing:-.02em} [data-testid="stCaptionContainer"]{color:#52647a}
</style>''', unsafe_allow_html=True)


@st.cache_data(ttl=300, show_spinner=False)
def read_live():
    return load_dashboard()


def local_time(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(ZoneInfo('Asia/Taipei')).strftime('%Y/%m/%d %H:%M')
    except (TypeError, ValueError, AttributeError):
        return '—'


def pct(value):
    return '—' if value is None else f'{value * 100:+.1f}%'


def stock_frame(stocks):
    rows = []
    for s in stocks:
        f, x = s.get('financial', {}), s.get('features', {})
        rows.append({'代碼': s['symbol'], '公司': s['name'], '分數': s.get('rankScore'),
                     '收盤價': s.get('close'), '收盤日': s.get('priceDate'),
                     '營收年增': f.get('revenue_growth'), '營益率': f.get('operating_margin'),
                     '現金流率': f.get('cfo_margin'), '126日回撤': x.get('drawdown_126'),
                     '63日相對報酬': x.get('relative_63'), '狀態': classification(s),
                     '原因': s.get('sourceError') or '；'.join(s.get('evaluation', {}).get('reasons', []))})
    return pd.DataFrame(rows)


def show_stocks(stocks):
    df = stock_frame(stocks)
    if df.empty:
        st.info('目前沒有符合此篩選的標的。')
        return
    config = {c: st.column_config.NumberColumn(c, format='percent', width='small')
              for c in ('營收年增', '營益率', '現金流率', '126日回撤', '63日相對報酬')}
    config['分數'] = st.column_config.NumberColumn('分數', format='%.1f')
    st.dataframe(df, hide_index=True, width='stretch', column_config=config)
    st.download_button('下載目前清單 CSV', df.to_csv(index=False).encode('utf-8-sig'),
                       file_name=f'growth_{market}_{strategy}.csv', mime='text/csv', key='stocks_csv')


st.sidebar.markdown('### 成長股觀測站')
st.sidebar.caption('美股 × 台股｜銀行端研究入口')
market_label = st.sidebar.radio('市場', ['美股 US', '台股 TW'])
market = 'US' if market_label.startswith('美') else 'TW'
strategy_label = st.sidebar.radio('策略', ['基本面／資金主策略', '背離長抱策略'])
strategy = 'primary' if strategy_label.startswith('基本') else 'buy_hold'
if st.sidebar.button('重新讀取資料', width='stretch'):
    read_live.clear()
st.sidebar.caption('重新讀取原站已完成的結果；不觸發行情補抓或下單。')
st.sidebar.markdown('---')
st.sidebar.caption('資料排程（台灣時間）\n\n美股：週二至週六 07:00\n\n台股：週一至週五 21:00')
st.sidebar.caption('此入口僅供公開研究。個人組合由原站登入後管理。')
st.title('成長股觀測站')
st.caption('依同一套策略，查看候選、辨認資料異常、比較不同年份入場。')

data, load_error = None, None
try:
    with st.spinner('讀取公開研究資料…'):
        data = read_live()
except Exception as exc:
    load_error = type(exc).__name__
    st.error('目前無法讀取原站最新資料，已停止顯示買入候選。回測與策略說明仍可使用。')
    st.caption(f'連線狀態：{load_error}。請稍後按「重新讀取資料」。')

stocks = [s for s in data['instruments'] if s['market'] == market] if data else []
candidates = sorted_candidates(stocks, strategy)
pending = [s for s in stocks if classification(s) == '資料待核對']
if data:
    dates = sorted({s['priceDate'] for s in stocks})
    st.caption(f'原站回應：{local_time(data["serverTime"])}（台灣）｜收盤資料：{"、".join(dates)}｜畫面資料最多快取 5 分鐘')
    cols = st.columns(4)
    cols[0].metric('研究樣本', len(stocks))
    cols[1].metric('本策略合格候選', len(candidates))
    cols[2].metric('資料待核對', len(pending))
    macro = data['macros'][market]
    cols[3].metric('資金壓力', f'{macro.get("macro_stress", "—")} / 4')
    if pending:
        st.warning(f'{len(pending)} 檔資料待核對，已暫停新買入訊號。候選減少可能來自資料異常；既有持股須另核對出場條件。')

tab_candidates, tab_quality, tab_research, tab_changes = st.tabs(['買入候選', '資料品質與更新', '策略與回測', '候選變動說明'])
with tab_candidates:
    st.subheader(strategy_label)
    st.caption('候選是研究清單。每組最多十檔，分數決定進場先後；登錄持股與實際成交分開處理。')
    query = st.text_input('搜尋代碼或公司', placeholder='例如 NVDA、2330')
    filtered = [s for s in candidates if not query or query.casefold() in (s['symbol']+' '+s['name']).casefold()]
    show_stocks(filtered)
    if filtered:
        selected = st.selectbox('查看標的細節', [s['key'] for s in filtered],
                                format_func=lambda k: next(s['symbol']+'｜'+s['name'] for s in filtered if s['key']==k))
        stock = next(s for s in filtered if s['key']==selected)
        f = stock['financial']
        st.write(f'財報季末：{f.get("latest_period", "—")}｜最新輸入申報日：{f.get("max_input_filed") or "—"}｜基準：{stock.get("benchmark", "—")}')
        st.caption(f.get('date_basis') or '財報資料時點依原站規則；台股歷史公告時間仍有推估限制。')
        hist = pd.DataFrame(stock.get('history', []))
        if not hist.empty:
            st.line_chart(hist.set_index('date')['close'], height=230)
            st.caption('走勢使用還原價格，與表格中的收盤報價尺度可能不同。')

with tab_quality:
    st.subheader('先確認資料，再判讀訊號')
    if data:
        quality = st.selectbox('顯示範圍', ['資料待核對', '全部樣本'])
        quality_stocks = pending if quality=='資料待核對' else stocks
        if quality_stocks:
            st.dataframe(stock_frame(quality_stocks), hide_index=True, width='stretch')
        else:
            st.success('目前沒有待核對標的。')
        jobs = [j for j in data['jobs'] if j['market']==market]
        for job in jobs:
            title = f'{local_time(job.get("created_at"))}｜{job["status"]}｜成功 {job["updated"]}／{job["total"]}，待核對 {job["failed"]}'
            with st.expander(title):
                errors = job.get('errors', [])
                if isinstance(errors, str):
                    try: errors = json.loads(errors)
                    except ValueError: errors = [errors]
                for error in errors: st.write(error)
                if not errors: st.write('本次無來源錯誤。')
    st.info('資料來源失敗時保留舊快照並暫停新買入訊號。這種情況不能直接解讀成基本面轉弱，也不能據此推論全部持股都應賣出。')

with tab_research:
    st.subheader('2016–2026 各年度起始至 2026/11/04')
    research = json.loads((ROOT/'data/research.json').read_text())
    basis = st.radio('美股估值算法', ['拆股尺度修正版', '原算法對照'], horizontal=True) if market=='US' else '拆股尺度修正版'
    key = ('us' if basis=='拆股尺度修正版' else 'usOriginal') if market=='US' else 'tw'
    result_rows = []
    for row in research[key]:
        invalid = market=='TW' and row['cohort_year']<2019
        result_rows.append({'起始年': str(row['cohort_year']),
                           '主策略累積報酬': '資料不足' if invalid else pct(row.get('primary_total_return')),
                           '背離長抱累積報酬': '資料不足' if invalid else pct(row.get('buy_hold_total_return')),
                           '主策略年化': '—' if invalid else pct(row.get('primary_cagr')),
                           '主策略最大回撤': '—' if invalid else pct(row.get('primary_max_drawdown'))})
    st.dataframe(pd.DataFrame(result_rows), hide_index=True, width='stretch')
    st.warning('台股 2016–2018 財報不足，不據此判定策略優劣。兩市場採目前指定的存活樣本；台股歷史財報時點有推估，尚非完整排除前視與存活者偏誤的回測。')
    st.markdown('**買入：**收盤通過基本面、資金與交易門檻，依分數排序；有空位時於下一交易日開盤成交。每組最多十檔，新買入預算為該組淨值的 10%，受可用現金與最低 2% 門檻限制。')
    st.markdown('**主策略賣出：**基本面門檻失守、成長／營益率降溫，或全球資金壓力達兩項，收盤產生訊號後安排下一交易日開盤出場。回測中的資料缺漏出場另須區分。**背離長抱回測完全不賣。**')
    st.markdown('**新增本金：**另建獨立組合，各自保留本金、成本、現金與十檔額度。建立組合不會自動買入；目前績效須依登錄成交追蹤。')
    st.download_button('下載年度比較 CSV', (ROOT/'data/comparison-summary-2016-2026.csv').read_bytes(),
                       file_name='comparison-summary-2016-2026.csv', mime='text/csv')
    st.download_button('下載完整互動回測報告', gzip.decompress((ROOT/'data/backtest.html.gz').read_bytes()),
                       file_name='growth-backtest-2016-2026.html', mime='text/html')
    st.download_button('下載逐筆出場稽核 CSV', gzip.decompress((ROOT/'data/exit-audits.csv.gz').read_bytes()),
                       file_name='exit-audits-2016-2026.csv', mime='text/csv')

with tab_changes:
    st.subheader('2026/11/04 → 11/05：這次差異從哪裡來')
    st.caption('以下是建置時核對的固定事件說明，並非每次重新載入都會更新的昨日比較。')
    st.dataframe(pd.DataFrame([
        {'市場／策略':'台股主策略','先前候選':34,'核對時候選':8,'差異原因':'26 檔落在來源日期未到齊的標的中'},
        {'市場／策略':'台股背離長抱','先前候選':9,'核對時候選':3,'差異原因':'6 檔落在來源日期未到齊的標的中'}
    ]), hide_index=True, width='stretch')
    st.write('台股最新一輪 80 檔中，24 檔更新成功、56 檔來源回傳的最後行情日是 11/03，而該輪要求 11/04。系統在保留既有快照的同時加上來源錯誤標記；買入條件要求沒有來源錯誤，因此候選暫時退出清單。')
    st.write('以原始公開快照套用這 56 檔錯誤標記，可重現 34→8、9→3；不需要改動策略門檻。背離清單受影響的六檔為 2330、2303、2317、2383、3019、3481。此核對不是完整逐日資料版本歸因。')
    st.write('美股核對時為主策略 43 檔、背離 17 檔；81／89 檔更新成功，其餘八檔在最近 126 日出現還原價單日跳動超過 30%，尚未確認是否為真實行情、拆股或來源問題。此檢核會影響可觀測範圍。')
    st.write('另確認 DIOD 在 11/04 收盤新增符合背離長抱條件。系統目前沒有保存每一日完整候選快照與每檔消失原因，不能宣稱已逐檔解釋所有美股差異。')
    st.info('實際判讀順序：先看資料待核對數量，再看基本面／資金／背離條件；候選消失本身不是持股賣出訊號。')

st.caption('研究資訊依原站規則產生；本入口不連接券商，也不保存個人持股或交易成本。')

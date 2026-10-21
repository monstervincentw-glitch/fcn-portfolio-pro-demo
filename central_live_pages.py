"""FCN pages: central product parameters + shared constituent-stock price library."""
from __future__ import annotations
import datetime as dt
import pandas as pd
from central_catalog import Catalog,load_catalog,to_day,_today_taipei
from v2_portfolio_adapter import load_models


def code(x): return str(x or '').strip()

def _day(x):
    d=to_day(x)
    return d.strftime('%Y/%m/%d') if d else '—'

def _pct(x):
    try:
        n=float(x)
        return f'{n*100:.2f}%' if n<=2 else f'{n:.2f}%'
    except (TypeError,ValueError):return '—'


def contract_complete(product,legs):
    return bool(legs) and all(to_day(product.get(k)) for k in (
        'pricing_date','ko_start_date','final_eval_date','maturity_date'))


def classify(product,legs,*,today):
    # Compatibility with original page callers; actual display always calls model.
    from dataclasses import dataclass
    @dataclass
    class Group:
        category:str
        note:str
        key_date:dt.date|None
    if not contract_complete(product,legs):return Group('待建檔','中央日期或標的資料不足',None)
    m=to_day(product.get('maturity_date'));start=to_day(product.get('ko_start_date'))
    k=to_day(product.get('model_ko_date'))
    if k and k<=today:
        return Group('近三個月出場' if (today-k).days<=93 else '歷史歸檔','中央模型記錄 KO 日期',k)
    if m<today:
        return Group('近三個月出場' if (today-m).days<=93 else '歷史歸檔','到期日已過',m)
    if today<start:return Group('閉鎖中','尚未開始 KO 觀察',start)
    return Group('比價中','進入 KO 觀察期',start)


def dashboard_breakdown(catalog,holdings,*,today):
    groups={k:[] for k in ('閉鎖中','比價中','近三個月出場','近兩週到期')}
    missing=[]
    for pid in sorted({code(x.get('product_id')) for x in holdings if code(x.get('product_id'))}):
        p=catalog.products.get(pid)
        if not p:missing.append({'FCN':pid,'原因':'中央參數庫尚未有此商品'});continue
        c=classify(p,catalog.legs.get(pid,()),today=today)
        if c.category in groups:
            groups[c.category].append({'FCN':pid,'參考日期':_day(c.key_date),'模型狀態':c.note})
        elif c.category=='待建檔':missing.append({'FCN':pid,'原因':c.note})
        maturity=to_day(p.get('maturity_date'))
        if c.category in ('閉鎖中','比價中') and maturity and today<=maturity<=today+dt.timedelta(days=14):
            groups['近兩週到期'].append({'FCN':pid,'參考日期':_day(maturity),'模型狀態':c.note})
    return groups,missing


def exposure_rows(catalog,symbol,holdings):
    sym=code(symbol).upper();held={code(h.get('product_id')) for h in holdings}
    return [{'FCN 代號':pid,'股票':sym,'計價幣別':p.get('currency'),
             '是否持有':'是' if pid in held else '否','期初價':leg.get('initial_price')}
            for pid,p in sorted(catalog.products.items())
            for leg in catalog.legs.get(pid,()) if leg['ticker']==sym]


def product_overview(catalog,ledger_products,*,today):
    # Products ALWAYS originate from the central catalog; ledger_products is unused.
    return [{'FCN':pid,'幣別':p.get('currency'),'中央分類':classify(p,catalog.legs.get(pid,()),today=today).category,
             '到期日':_day(p.get('maturity_date')),'年化票息':_pct(p.get('annual_coupon_rate')),
             '_group':classify(p,catalog.legs.get(pid,()),today=today).category}
            for pid,p in sorted(catalog.products.items())]


def _snapshot(reader):
    import streamlit as st
    cached=st.session_state.get('_fcn_v9_catalog_models')
    if cached is not None:
        return cached
    # Avoid sending another burst of Sheets API requests after the adapter
    # has already failed earlier during this same Streamlit rerun.
    failure=st.session_state.get('_fcn_v9_model_error')
    if failure:
        st.error(failure+'。網站不會連回舊商品檔案。')
        return None,None
    try:return load_models(reader)
    except Exception as exc:
        st.error('中央商品庫讀取失敗：'+str(exc)+'。網站不會連回舊商品檔案。')
        return None,None


def model_dashboard_groups(models,holdings,*,today):
    groups={name:[] for name in ('閉鎖中','比價中','近三個月出場','近兩週到期','資料不足','歷史歸檔')}
    unique=sorted({code(h.get('product_id')) for h in holdings if code(h.get('product_id'))})
    for pid in unique:
        m=models.get(pid)
        if not m:
            groups['資料不足'].append({'FCN':pid,'狀態':'商品尚未輸入中央庫','資料日期':'—'})
            continue
        entry={'FCN':pid,'狀態':m.state,'試算資料':'待補' if m.issues else '完整',
               '資料日期':_day(m.latest_date),
               'KO 日':_day(m.ko_date),'最差標的':m.worst_ticker or '—'}
        category=m.category
        if category in groups:groups[category].append(entry)
        else:groups['資料不足'].append(entry)
        if category in ('閉鎖中','比價中') and m.maturity_day and today<=m.maturity_day<=today+dt.timedelta(days=14):
            groups['近兩週到期'].append(entry)
    return groups


def render_dashboard(reader,holdings):
    import streamlit as st
    st.subheader('🧭 FCN 商品監控工作台｜中央即時計算')
    st.caption('依中央商品日期分類閉鎖／比價，KO 由 V2 模型判定；資料不足仍留在原監控分類並標示試算狀態。股價為收盤價。')
    catalog,models=_snapshot(reader)
    if models is None:return
    groups=model_dashboard_groups(models,holdings,today=_today_taipei())
    unique={code(h.get('product_id')) for h in holdings}
    cols=st.columns(5)
    for col,k in zip(cols,groups):col.metric(k,len(groups[k]))
    name=st.selectbox('選擇監控狀態',list(groups),key='central_dashboard_filter')
    if groups[name]:st.dataframe(pd.DataFrame(groups[name]),hide_index=True,use_container_width=True)
    else:st.info('目前沒有符合的商品。')
    issues=[{'FCN':pid,'待補資料':'；'.join(m.issues)} for pid,m in sorted(models.items()) if m.issues and pid in unique]
    if issues:
        with st.expander(f'中央參數／歷史行情缺漏：{len(issues)} 檔'):
            st.dataframe(pd.DataFrame(issues),hide_index=True,use_container_width=True)
    st.caption('分類依模型 KO／到期日及中央資料計算；缺資料時顯示「資料不足」，不沿用舊試算表結果。')


def model_exposure_rows(catalog,models,symbol,holdings):
    rows=[]
    counts={}
    for h in holdings:
        pid=code(h.get('product_id'));counts[pid]=counts.get(pid,0)+1
    for pid,p in sorted(catalog.products.items()):
        if symbol not in [leg['ticker'] for leg in catalog.legs.get(pid,())]:continue
        m=models[pid]
        risk=('無持倉紀錄' if not counts.get(pid) else '待確認（資料不足）' if m.issues
              else '無（模型已出場）' if m.ko_date or m.principal_ratio is not None else '有')
        rows.append({'FCN':pid,'存續曝險':risk,'歷史持倉筆數':counts.get(pid,0),'幣別':p.get('currency'),
                     '模型狀態':m.state,'最新行情日期':_day(m.latest_date),
                     '最差標的':m.worst_ticker or '—'})
    return rows


def render_exposure(reader,holdings):
    import streamlit as st
    st.subheader('🔎 股票曝險｜中央商品聯動')
    catalog,models=_snapshot(reader)
    if models is None:return
    symbols=sorted({leg['ticker'] for legs in catalog.legs.values() for leg in legs})
    symbol=st.selectbox('搜尋連結股票',['']+symbols,format_func=lambda x:x or '請選擇股票',key='exposure_central')
    if not symbol:return
    rows=model_exposure_rows(catalog,models,symbol,holdings)
    if rows:st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    else:st.info('中央商品參數庫尚無此連結股票商品。')
    st.caption('模型 KO／到期後停止存續曝險，歷史連結與持倉紀錄保留；模型出場不代表客戶已入帳。')


def render_product_page(reader,holdings,ledger_products):
    import streamlit as st
    import pandas as pd
    from chart_render import build_stock_chart
    from fcn_customer_panel import render_product_clients
    st.subheader('📈 FCN 商品｜中央參數與收盤價監控')
    st.caption('商品條款與配息期取中央參數庫；收盤價共用歷史試打的成分股股價庫。無銀行核約或行情人工確認門檻。')
    catalog,models=_snapshot(reader)
    if models is None:return
    names=['日常監控','閉鎖中','比價中','近三個月出場','全部商品','資料不足','歷史歸檔']
    a,b=st.columns([1,2])
    with a:scope=st.selectbox('顯示範圍',names,key='central_p_scope')
    with b:search=st.text_input('搜尋商品代號',key='central_p_search').strip().upper()
    rows=[]
    for pid,p in sorted(catalog.products.items()):
        m=models[pid]
        if scope=='日常監控' and m.category not in ('閉鎖中','比價中','近兩週到期','近三個月出場'):continue
        if scope in ('閉鎖中','比價中','近三個月出場') and m.category!=scope:continue
        if scope=='資料不足' and m.category!='資料不足':continue
        if scope=='歷史歸檔' and m.category!='歷史歸檔':continue
        if search and search not in pid:continue
        rows.append({'FCN':pid,'幣別':p.get('currency'),'狀態':m.state,
                     '試算資料':'待補' if m.issues else '完整',
                     '最近行情':_day(m.latest_date),'最差標的':m.worst_ticker or '—',
                     '最差相對期初':_pct(m.worst_ratio) if m.worst_ratio is not None else '—',
                     'KO 日':_day(m.ko_date),'到期日':_day(m.maturity_day)})
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    st.caption(f'中央商品庫 {len(models)} 檔；目前顯示 {len(rows)} 檔。閉鎖／比價依商品日期與 V2 KO 判定；必要數值缺漏僅影響試算，不隱藏商品。')
    if not rows:return
    pid=st.selectbox('開啟商品詳情',[r['FCN'] for r in rows],key='central_p_selected')
    p=catalog.products[pid]; m=models[pid]
    st.markdown(f'#### {pid} · {p.get("currency") or "—"}｜{m.state}')
    x,y,z=st.columns(3)
    x.metric('年化票息',_pct(p.get('annual_coupon_rate')))
    y.metric('KO 門檻',_pct(p.get('ko_barrier_ratio')))
    z.metric('Strike 執行價',_pct(p.get('strike_ratio')))
    st.caption(f'定價日 {_day(m.pricing_day)} ｜ KO 開始 {_day(m.ko_start)} ｜ 最終評價 {_day(m.final_eval)} ｜ 到期 {_day(m.maturity_day)}')
    st.caption(f'KO 類型 {p.get("ko_type") or "未填"} ｜ KI 類型 {p.get("ki_type") or "未填"} ｜ 票息模式 {m.coupon_mode} ｜ KO 觀察假設：{m.ko_observation}')
    if m.issues:st.warning('本商品資料尚不完整：'+'；'.join(m.issues))
    if m.quote_rows:
        st.markdown('##### 連結股票｜觀察期間最後可得收盤價及障礙距離')
        st.dataframe(pd.DataFrame(m.quote_rows),hide_index=True,use_container_width=True)
    if m.price_history:
        frame=pd.DataFrame(m.price_history)
        frame['date']=pd.to_datetime(frame['date'])
        try:
            chart=build_stock_chart(frame,m.levels,sorted(frame['stock'].unique()))
            st.altair_chart(chart,use_container_width=True)
        except (ValueError,KeyError,TypeError) as exc:
            st.warning('圖表目前無法顯示：'+str(exc))
        st.caption('期初價＝100%；KO／Strike／KI 為中央模型門檻；每日收盤價非盤中即時報價。')
    if m.ko_date:st.success('模型推定 KO 觸發日：'+m.ko_date.isoformat())
    if m.ki_touched is not None:st.caption('模型 KI 曾觸發：'+('是' if m.ki_touched else '否'))
    if m.principal_ratio is not None:st.metric('模型本金回收比例',f'{m.principal_ratio*100:.2f}%')
    if m.coupon_rows:
        with st.expander('各期模型票息及預定付款日'):
            st.dataframe(pd.DataFrame([{'期數':r['期數'],'計息起日':r['計息起日'],
                '計息末日':r['計息末日'],'付款日':r['配息日'],
                '模型票息率 (%)':round(r['模型票息率']*100,5),
                '未來情境票息率 (%)':round(r['未來假設票息率']*100,5)} for r in m.coupon_rows]),
                hide_index=True,use_container_width=True)
    render_product_clients(pid,holdings,mode='live')

"""FCN model uses central terms plus the unchanged 526-stock library.

One product model serves all customer holdings; no bank confirmation gates.
No old V2/Data file, individual FCN Chart files or second daily price feed.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from central_catalog import (
    load_model_inputs, load_market_matrix,
    as_positive_number, to_day,
    _today_taipei,
)
from fcn_central_model import model_one, ratio


def load_models(reader, *, today=None):
    """Build a single same-version snapshot of all central products.

    Return (Catalog, models); one model per product, never one per customer.
    """
    # 1 central batch instead of multiple sequential requests.
    catalog, holidays, periods, input_rules = load_model_inputs(reader)
    tickers={leg['ticker'] for legs in catalog.legs.values() for leg in legs}
    market_failure = None
    try:
        # Header request + one multi-column batch from EXISTING 526-stock library.
        market, latest, symbols=load_market_matrix(reader,tickers)
    except Exception as exc:
        # Product lifecycle must remain visible if the price feed is unavailable.
        market, latest, symbols = {}, None, set()
        market_failure = '成分股歷史股價庫讀取失敗：' + str(exc)
    models={}
    for pid, product in catalog.products.items():
        model=model_one(product,catalog.legs.get(pid,()),periods.get(pid,()),
                        market,holidays,input_rules.get(pid),today=today)
        if market_failure:
            model.issues.append(market_failure)
        else:
            absent=sorted({leg['ticker'] for leg in catalog.legs.get(pid,()) if leg['ticker'] not in symbols})
            if absent and not any('未收錄' in issue for issue in model.issues):
                model.issues.append('股票未收錄於現有成分股股價庫：'+'、'.join(absent))
                model.principal_ratio=None
                model.earned_coupon_rate=None
                model.forecast_coupon_rate=None
                model.ko_date=None
                # Do not relabel contractually active FCN as '資料不足'.
        # Historical closes are shared with the independent history-trial page.
        for leg in catalog.legs.get(pid,()):
            ticker=leg['ticker']
            end=min(today or _today_taipei(), model.ko_date or model.final_eval or today or _today_taipei())
            day=next((date for date in sorted(market,reverse=True)
                      if date<=end and (not model.pricing_day or date>=model.pricing_day)
                      and date.weekday()<5 and date not in holidays
                      and as_positive_number(market[date].get(ticker)) is not None),None)
            close=as_positive_number(market[day][ticker]) if day else None
            initial=as_positive_number(leg.get('initial_price'))
            pct=close/initial if close and initial else None
            model.quote_rows.append({
                '股票':ticker,'收盤日期':day.isoformat() if day else '—',
                '最新收盤價':close,'期初價':initial,
                '相對期初':round(pct*100,2) if pct else None,
                '距 KO':round((pct/ratio(product.get('ko_barrier_ratio'))-1)*100,2)
                          if pct and ratio(product.get('ko_barrier_ratio')) else None,
                '距 Strike':round((pct/ratio(product.get('strike_ratio'))-1)*100,2)
                          if pct and ratio(product.get('strike_ratio')) else None,
                '距 KI':round((pct/ratio(product.get('ki_barrier_ratio'))-1)*100,2)
                         if pct and ratio(product.get('ki_barrier_ratio')) else None,
            })
        models[pid]=model
    return catalog,models


def enrich_new_holdings(reader, holdings):
    """Update copies of EACH customer's holding using one central FCN calculation.

    Remove all old ledger model projection values in memory. Real transaction
    records in customer ledger are NOT changed. Missing central inputs => null,
    NOT a stale ledger estimate, invented zero or 'bank verification pending'.
    """
    copied=[dict(h) for h in holdings]
    # A failed Sheets refresh must never leave previous product results cached.
    try:
        import streamlit as st
        st.session_state.pop('_fcn_v9_catalog_models',None)
        st.session_state.pop('_fcn_v9_model_error',None)
    except (ImportError,AttributeError):
        pass
    try:
        catalog,models=load_models(reader)
    except Exception as exc:
        catalog,models=None,{}
        failure='商品監控來源讀取失敗：'+str(exc)
        try:
            import streamlit as st
            st.session_state['_fcn_v9_model_error']=failure
        except (ImportError,AttributeError):
            pass
    else:
        failure=None
        # Cache product-only calculations for the CURRENT authenticated Streamlit
        # rerun. Client data is never cached and the next rerun reloads Sheets.
        try:
            import streamlit as st
            st.session_state['_fcn_v9_catalog_models']=(catalog,models)
        except (ImportError,AttributeError):
            pass
    for h in copied:
        pid=str(h.get('product_id') or '').strip()
        capital=as_positive_number(h.get('invested_amount'))
        # Stop projecting from the legacy customer's bank spreadsheet columns.
        for field in ('estimated_principal_total','estimated_coupon_total',
                      'estimated_outstanding','expected_principal_date',
                      'expected_principal_amount','v2_forecast_coupon_total',
                      'v2_state','ko_date','model_state','monitor_group',
                      'v2_exit_date','v2_principal_ratio','v2_active_exposure','v2_principal_loss',
                      'estimated_pnl','expected_coupon_amount','model_coupon_rate',
                      'model_coupon_amount','model_total_return','product_status','holding_state'):
            h[field]=None
        h['v2_coupon_schedule']=[]
        h['v2_model_source']='中央商品參數庫＋成分股股價庫'
        h['v2_issues']=''
        if failure:
            h['v2_issues']=failure
            h['estimated_settlement_state']='中央資料讀取失敗'
            continue
        m=models.get(pid)
        if m is None:
            h['v2_issues']='中央商品庫找不到此商品代號'
            h['estimated_settlement_state']='中央商品待建檔'
            continue
        h['v2_state']=m.state
        h['model_state']=m.state
        h['product_status']=m.state
        h['holding_state']=m.state
        h['monitor_group']=m.category
        h['ko_date']=m.ko_date
        h['v2_exit_date']=m.ko_date or (m.final_eval if m.principal_ratio is not None else None)
        h['v2_principal_ratio']=m.principal_ratio
        # Unknown model observations never imply zero exposure or an exit.
        h['v2_active_exposure']=None if m.issues else m.principal_ratio is None
        if m.issues:
            h['v2_issues']='；'.join(m.issues)
            h['estimated_settlement_state']='中央 V2：'+m.state+'（部分試算資料待補）'
            continue
        if capital is None:
            h['v2_issues']='客戶持倉本金缺漏'
            h['estimated_settlement_state']='客戶資料不足'
            continue
        h['v2_coupon_schedule']=[{
            '期別':r['期數'],'計息起日':r['計息起日'],'計息末日':r['計息末日'],
            '預定配息日':r['配息日'],
            '模型票息率 (%)':round(r['模型票息率']*100,5),
            '模型票息金額':round(capital*r['模型票息率'],2),
            '未來情境票息':round(capital*r['未來假設票息率'],2),
            '模式':r['計息模式']}
            for r in m.coupon_rows]
        h['estimated_coupon_total']=(round(capital*m.earned_coupon_rate,2)
                                     if m.earned_coupon_rate is not None else None)
        h['v2_forecast_coupon_total']=(round(capital*m.forecast_coupon_rate,2)
                                      if m.forecast_coupon_rate is not None else None)
        h['model_coupon_rate']=m.earned_coupon_rate
        h['model_coupon_amount']=h['estimated_coupon_total']
        h['expected_coupon_amount']=h['v2_forecast_coupon_total']
        if m.principal_ratio is not None:
            h['estimated_principal_total']=round(capital*m.principal_ratio,2)
            h['estimated_outstanding']=0.0  # Model notional no longer at market risk.
            h['v2_principal_loss']=max(0,round(capital*(1-m.principal_ratio),2))
            h['expected_principal_amount']=h['estimated_principal_total']
            h['estimated_pnl']=round(h['estimated_principal_total']+h['estimated_coupon_total']-capital,2)
            h['model_total_return']=h['estimated_pnl']/capital
            # Early KO is an observation event, not evidence of cash settlement.
            h['expected_principal_date']=None if m.ko_date else m.maturity_day
        else:
            # Unmatured and not KO: capital is still exposed to the FCN.
            h['estimated_principal_total']=None
            h['estimated_outstanding']=capital
            h['expected_principal_date']=m.maturity_day
        h['estimated_settlement_state']='中央 V2：'+m.state
    return copied

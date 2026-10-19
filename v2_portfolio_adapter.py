"""Opt-in central catalog -> V2 -> new holdings. Never writes Google Sheets.
Legacy products remain byte-for-byte untouched; incomplete new products retain ledger values.
"""
from __future__ import annotations
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from central_catalog import load_catalog, CENTRAL_CATALOG_ID
from v2_portfolio_engine import CouponPeriod, calculate_v2, to_date

ORIGINAL_V2_ID = '1pc2O3CB4vp1Tq0CcgfngitpVQsbb64ibSucL3fKFI44'
NEW_PRODUCT_IDS = frozenset(('SP34','SM25','SQ59'))  # Explicit rollout; legacy untouched.

def _float(x):
    try: return float(str(x).replace(',','').replace('%',''))
    except (TypeError,ValueError): return None

def _rows(reader, spreadsheet, tab, span):
    raw=reader.read(spreadsheet,f"'{tab}'!{span}")
    if not raw: return []
    header=[str(x or '').strip() for x in raw[0]]
    return [dict(zip(header, list(r)+[None]*max(0,len(header)-len(r)))) for r in raw[1:]]

def _holidays(reader):
    """Read same holiday column used by original V2; if unavailable, do not calculate."""
    rows=reader.read(ORIGINAL_V2_ID,"'Data'!AL31:AL129")
    days={to_date(r[0]) for r in rows if r and r[0] not in ('',None)}
    days.discard(None)
    if not days: raise ValueError('原 V2 休市日表未讀取成功')
    return days

def _periods(reader, pid):
    records=_rows(reader,CENTRAL_CATALOG_ID,'配息期','A1:I300')
    result=[]
    for r in records:
        if str(r.get('商品代號') or '').strip()!=pid: continue
        start=to_date(r.get('期初日')); end=to_date(r.get('期末日'))
        payment=to_date(r.get('配息日'))
        n=_float(r.get('配息期'))
        if start is None or end is None or payment is None or n is None:
            raise ValueError('中央配息期缺完整起訖日／配息日／期別')
        result.append(CouponPeriod(int(n),start,end,payment))
    if not result: raise ValueError('中央配息期不存在')
    return sorted(result,key=lambda x:x.number)

def _prices(reader, tickers, pricing, end):
    data=reader.read(CENTRAL_CATALOG_ID,"'歷史行情_核心'!A1:AZ1100")
    if not data: raise ValueError('中央歷史行情缺漏')
    headers=[str(x or '').strip().upper() for x in data[0]]
    idx={t:headers.index(t) for t in tickers if t in headers}
    if len(idx)!=len(tickers): raise ValueError('中央歷史行情缺少連結標的欄位')
    result={}
    for row in data[1:]:
        day=to_date(row[0] if row else None)
        if day is None or day<pricing or day>end: continue
        result[day]={t:_float(row[j]) if j<len(row) else None for t,j in idx.items()}
    return result

def enrich_new_holdings(reader, holdings):
    """Read-only enhancement, preserving old products and incomplete new-product ledger values.

    For transparency, attaches v2_issues / v2_state; only complete V2 results overwrite
    projected fields in memory. Does not mutate source holdings or cash-flow records.
    """
    copied=[dict(h) for h in holdings]
    selected=[h for h in copied if str(h.get('product_id') or '').strip() in NEW_PRODUCT_IDS]
    if not selected: return copied
    try:
        catalog=load_catalog(reader)
        holidays=_holidays(reader)
    except Exception as exc:
        for h in selected: h['v2_issues']=f'V2 資料讀取失敗：{exc}'
        return copied
    today=datetime.now(timezone(timedelta(hours=8))).date()
    cache={}
    for h in selected:
        pid=str(h.get('product_id') or '').strip()
        if pid not in cache:
            try:
                p=catalog.products[pid]; legs=catalog.legs[pid]
                start=to_date(p.get('pricing_date')); ko_start=to_date(p.get('ko_start_date'))
                end=to_date(p.get('final_eval_date'))
                if not start or not ko_start or not end: raise ValueError('商品重要日期缺漏')
                initial={str(x['ticker']):_float(x.get('initial_price')) for x in legs}
                if not initial or any(v is None for v in initial.values()): raise ValueError('期初價格缺漏')
                periods=_periods(reader,pid)
                prices=_prices(reader,list(initial),start,end)
                ko_type=str(p.get('ko_type') or '').strip()
                if ko_type in ('記憶KO','記憶式KO','memory KO'): ko_type='記憶式'
                ki_type=str(p.get('ki_type') or '').strip()
                if 'Non-KI' in ki_type: ki_type='Non-KI'
                elif 'EKI' in ki_type: ki_type='EKI'
                elif 'AKI' in ki_type: ki_type='AKI'
                res=calculate_v2(pricing_date=start,ko_start=ko_start,final_eval=end,
                    initial_prices=initial,daily_prices=prices,ko_barrier=_float(p.get('ko_barrier_ratio')) or 0,
                    strike=_float(p.get('strike_ratio')) or 0,
                    ki_barrier=_float(p.get('ki_barrier_ratio')),
                    ko_type=ko_type,ki_type=ki_type,annual_rate=_float(p.get('annual_coupon_rate')) or 0,
                    periods=periods,holidays=holidays,as_of=today)
                cache[pid]=res
            except Exception as exc: cache[pid]=exc
        res=cache[pid]
        if isinstance(res,Exception): h['v2_issues']=str(res); continue
        h['v2_state']=res.state
        if res.issues: h['v2_issues']='；'.join(res.issues); continue
        amount=_float(h.get('invested_amount'))
        if amount is None: h['v2_issues']='持倉本金缺漏'; continue
        h['v2_coupon_schedule']=[{'期別':c.number,'配息日':c.payment.isoformat(),
                                  '交易日':c.full_trading_days,'KO前交易日':c.ko_trading_days,
                                  '計息比例':c.accrual_ratio,'預估票息':round(amount*c.coupon_rate,2)}
                                 for c in res.coupons]
        if res.principal_recovery_ratio is not None:
            principal=round(amount*res.principal_recovery_ratio,2)
            h['estimated_principal_total']=principal
            h['estimated_outstanding']=max(0.,round(amount-principal,2))
            h['estimated_coupon_total']=round(amount*res.coupon_total_rate,2)
            h['estimated_settlement_state']='V2 模型：'+res.state
            h['expected_principal_amount']=principal
            h['expected_principal_date']=(res.ko_date or to_date(catalog.products[pid].get('maturity_date')))
        # No settlement value for live product before KO/final evaluation.
    return copied

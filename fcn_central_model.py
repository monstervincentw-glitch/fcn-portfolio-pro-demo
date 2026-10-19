"""Pure market-close FCN model; no bank review/approval checks.

Input KO observations default to each US exchange trading day starting at ko_start_date,
matching the existing V2 model. It is an explicit MODEL assumption, not a bank ledger.
Coupon mode is either fixed period or V2 trading-day prorating from central input text.
"""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, field
from math import isfinite
from typing import Any
from central_catalog import as_positive_number, to_day


@dataclass
class ProductModel:
    product_id: str
    category: str = '資料不足'
    state: str = '資料不足'
    issues: list[str] = field(default_factory=list)
    latest_date: dt.date | None = None
    ko_date: dt.date | None = None
    ki_touched: bool | None = None
    worst_ticker: str | None = None
    worst_ratio: float | None = None
    principal_ratio: float | None = None
    earned_coupon_rate: float | None = None
    forecast_coupon_rate: float | None = None
    quote_rows: list[dict] = field(default_factory=list)
    coupon_rows: list[dict] = field(default_factory=list)
    price_history: list[dict] = field(default_factory=list)
    levels: dict = field(default_factory=dict)
    pricing_day: dt.date | None = None
    final_eval: dt.date | None = None
    maturity_day: dt.date | None = None
    ko_start: dt.date | None = None
    coupon_mode: str = '按交易日比例（V2）'
    ko_observation: str = '每日收盤觀察（V2 模型假設）'


def ratio(value):
    if value is None or str(value).strip()=='': return None
    text=str(value).replace(',','').strip()
    try: n=float(text.replace('%',''))
    except (TypeError,ValueError,OverflowError): return None
    if not isfinite(n) or n<=0: return None
    # Google Sheets percent cells are normally fractional (e.g. 1.10 = 110%).
    # Whole-number percentages such as 95 or '95%' require conversion.
    return n/100 if '%' in text or n>2 else n


def parse_ko(text):
    value=str(text or '').strip().lower()
    if '非記憶' in value or 'non-memory' in value or 'non memory' in value: return '非記憶式'
    if '記憶' in value or 'memory' in value: return '記憶式'
    return None


def parse_ki(text):
    value=str(text or '').upper()
    if 'NON-KI' in value or 'NON KI' in value or '無敲入' in value: return 'Non-KI'
    if 'AKI' in value: return 'AKI'
    if 'EKI' in value: return 'EKI'
    return None


def trading_days_between(start,end,holidays):
    if start>end: return []
    return [start+dt.timedelta(days=i) for i in range((end-start).days+1)
            if (start+dt.timedelta(days=i)).weekday()<5
            and (start+dt.timedelta(days=i)) not in holidays]


def coupon_style(rule):
    explicit=str(rule.get('票息計算方式') or '').strip()
    if explicit in ('固定每期','按交易日比例'): return explicit
    desc=str(rule.get('特殊結算／配息規則') or '')
    if '每期固定' in desc or '每月配息' in desc or '固定配息' in desc: return '固定每期'
    return '按交易日比例'


def model_one(product,legs,periods,price_matrix,holidays,rule=None,*,today=None):
    pid=str(product.get('product_id') or '').strip()
    result=ProductModel(pid)
    rule=rule or {}
    today=today or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    pricing=to_day(product.get('pricing_date'))
    start=to_day(product.get('ko_start_date'))
    finish=to_day(product.get('final_eval_date'))
    maturity=to_day(product.get('maturity_date'))
    result.pricing_day=pricing;result.final_eval=finish;result.maturity_day=maturity;result.ko_start=start
    result.coupon_mode=coupon_style(rule)
    ko_frequency=str(rule.get('KO觀察方式') or '').strip()
    if ko_frequency=='各期末日':
        result.ko_observation='各期計息末日'
        allowed_ko_days={x[2] for x in periods if len(x)>2}
    else:
        # Original site's V2 approach: every available market trading day after KO start.
        result.ko_observation='每日交易日（V2 模型預設）'
        allowed_ko_days=None
    rko=ratio(product.get('ko_barrier_ratio'))
    rstrike=ratio(product.get('strike_ratio'))
    rki=ratio(product.get('ki_barrier_ratio'))
    rcoupon=ratio(product.get('annual_coupon_rate'))
    ko=parse_ko(product.get('ko_type'))
    ki=parse_ki(product.get('ki_type'))
    result.levels={'ko':rko*100 if rko else None,'strike':rstrike*100 if rstrike else None,
                   'ki':None if ki=='Non-KI' else rki*100 if rki else None,'ko_start':start}
    if not all((pricing,start,finish,maturity)) or not (pricing<=start<=finish<=maturity):
        result.issues.append('中央商品日期不完整或先後順序錯誤')
    if not legs:
        result.issues.append('中央商品缺少連結股票')
    init={}
    for l in legs:
        ticker=str(l.get('ticker') or '').strip().upper()
        val=as_positive_number(l.get('initial_price'))
        if not ticker or val is None: result.issues.append('標的代號／期初價格缺漏')
        else: init[ticker]=val
    if len(init)!=len(legs): result.issues.append('標的資料不完整或代號重複')
    if ko is None: result.issues.append('中央 KO 類型未指定（記憶式／非記憶式）')
    if ki is None: result.issues.append('中央 KI 類型未指定（AKI／EKI／Non-KI）')
    if ki not in ('Non-KI',None) and rki is None: result.issues.append('中央 KI 門檻缺漏')
    if any(v is None for v in (rko,rstrike,rcoupon)):
        result.issues.append('中央 KO／Strike／年化票息必要參數缺漏')
    if not periods: result.issues.append('中央配息期尚未建立')
    elif any(not (isinstance(x[0],int) and x[1] and x[2] and x[3]
                    and x[1]<=x[2]<=x[3]) for x in periods):
        result.issues.append('中央配息期起訖日／付款日缺漏')
    elif len({x[0] for x in periods}) !=len(periods):
        result.issues.append('中央配息期數重複')
    if result.issues:
        return result

    last_market=max((d for d in price_matrix if d<=today),default=None)
    if last_market is None or last_market<pricing:
        result.issues.append('中央股價歷史尚未涵蓋商品定價日')
        return result
    analysis_end=min(finish,last_market,today)
    expected=trading_days_between(pricing,analysis_end,holidays)
    # Strict coverage: a missing required market close never silently means no KO.
    missing=[]
    memory={symbol:False for symbol in init}
    aki=False
    last_complete=None;last_ratios={}
    stop_day=None
    for day in expected:
        day_quotes=price_matrix.get(day) or {}
        if any(day_quotes.get(sym) is None for sym in init):
            missing.append(day)
            continue
        ratios={sym:float(day_quotes[sym])/start_price for sym,start_price in init.items()}
        last_ratios=ratios;last_complete=day
        for symbol, r in ratios.items():
            result.price_history.append({'date':day,'stock':symbol,'ratio':r*100})
        if ki=='AKI' and any(r<=rki for r in ratios.values()): aki=True
        if start<=day<=finish and (allowed_ko_days is None or day in allowed_ko_days):
            if ko=='記憶式':
                for symbol,r in ratios.items():
                    if r>=rko:memory[symbol]=True
                knocked=all(memory.values())
            else: knocked=all(r>=rko for r in ratios.values())
            if knocked:
                stop_day=day
                break
    # Until full observation coverage, redemption and KI status cannot be reliable.
    if missing:
        result.issues.append(f'必要交易日行情缺漏 {len(missing)} 天（首日 {missing[0]}）')
    result.latest_date=last_complete
    result.ko_date=stop_day
    if stop_day is None and today>=finish and last_market<finish:
        result.issues.append('中央行情未覆蓋最終評價日')
    if last_complete is not None:
        result.worst_ticker=min(last_ratios,key=last_ratios.get)
        result.worst_ratio=last_ratios[result.worst_ticker]
    result.ki_touched = None if ki=='Non-KI' else aki if ki=='AKI' else None
    if ki=='EKI' and stop_day is None and today>=finish and finish<=last_market:
        final_prices=price_matrix.get(finish) or {}
        if any(final_prices.get(s) is None for s in init):
            result.issues.append('EKI 最終評價日收盤價缺漏')
        else:
            result.ki_touched=any((final_prices[s]/init[s])<=rki for s in init)
            result.worst_ticker=min(init,key=lambda s:final_prices[s]/init[s])
            result.worst_ratio=final_prices[result.worst_ticker]/init[result.worst_ticker]

    if stop_day:
        result.state='模型提前 KO'
        result.category='近三個月出場' if (today-stop_day).days<=93 else '歷史歸檔'
    elif today<start:
        result.state='閉鎖中';result.category='閉鎖中'
    elif today<=maturity:
        result.state='比價中' if today<finish else '到期結算中'
        result.category='近兩週到期' if today<=maturity<=today+dt.timedelta(days=14) else '比價中'
    else:
        result.state='已到期';result.category='近三個月出場' if (today-maturity).days<=93 else '歷史歸檔'

    # Coupon cashflows: never present projected future coupon as already earned.
    total_earned=0.0;future=0.0
    for number,period_start,period_end,payment_day in periods:
        full=trading_days_between(period_start,period_end,holidays)
        if not full: result.issues.append(f'第{number}期無交易日');continue
        if stop_day and stop_day<period_start: earned=0
        elif stop_day: earned=len(trading_days_between(period_start,min(stop_day,period_end),holidays))
        elif period_end<=analysis_end: earned=len(full)
        else: earned=0
        if result.coupon_mode=='固定每期':
            # Entire coupon for a completed accrual period, including period of KO.
            fraction=(1.0 if stop_day and period_start<=stop_day
                      else 1.0 if period_end<=analysis_end and (stop_day is None or period_start<=stop_day)
                      else 0.0)
        else:
            fraction=earned/len(full)
        rate=(rcoupon/12)*fraction
        forecast=(rcoupon/12) if (not stop_day and period_end>analysis_end) else 0.0
        total_earned+=rate
        future+=forecast
        result.coupon_rows.append({'期數':number,'計息起日':period_start.isoformat(),
            '計息末日':period_end.isoformat(),'配息日':payment_day.isoformat(),
            '計息模式':result.coupon_mode,'整期交易日':len(full),'計入交易日':earned,
            '模型票息率':rate,'未來假設票息率':forecast})
    if result.issues:
        result.category='資料不足';result.state='資料不足'
        result.earned_coupon_rate=None; result.forecast_coupon_rate=None
        result.principal_ratio=None
    else:
        result.earned_coupon_rate=total_earned
        result.forecast_coupon_rate=total_earned+future
        if stop_day:
            result.principal_ratio=1.0
        elif today>=finish:
            if result.worst_ratio is None:result.issues.append('末日價格不足')
            elif ki=='Non-KI' or result.ki_touched:
                result.principal_ratio=min(1.0,result.worst_ratio/rstrike) if result.worst_ratio<rstrike else 1.0
            else:
                result.principal_ratio=1.0
        if result.issues: result.state='資料不足';result.category='資料不足'
    return result

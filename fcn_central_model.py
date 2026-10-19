"""Personal FCN monitor: V2 is the single KO/KI/coupon/redemption rule engine.

Product lifecycle is determined independently of P&L-input completeness so that
閉鎖中 and 比價中 remain visible when an input/quote is missing. No bank approval
or confirmation gates. Prices come only from the existing 526-stock library.
"""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, field
from math import isfinite
from typing import Any
from demo_utils import recent_end
from central_catalog import as_positive_number, to_day
from v2_portfolio_engine import CouponPeriod, calculate_v2, trading_days


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
    ko_observation: str = '每交易日觀察（V2）'


def ratio(value):
    if value is None or str(value).strip() == '':
        return None
    raw = str(value).strip().replace(',', '')
    try:
        value = float(raw.replace('%', ''))
    except (TypeError, ValueError, OverflowError):
        return None
    if not isfinite(value) or value <= 0:
        return None
    return value / 100 if '%' in raw or value > 2 else value


def parse_ko(value):
    s = str(value or '').strip().lower()
    if '非記憶' in s or 'non-memory' in s or 'non memory' in s:
        return '非記憶式'
    if '記憶' in s or 'memory' in s:
        return '記憶式'
    return None


def parse_ki(value):
    s = str(value or '').upper()
    if 'NON-KI' in s or 'NON KI' in s or '無敲入' in s:
        return 'Non-KI'
    if 'AKI' in s:
        return 'AKI'
    if 'EKI' in s:
        return 'EKI'
    return None


def coupon_style(rule):
    """No product-specific bank rounding/exception paths; use original V2."""
    return '按交易日比例（V2）'


def _date_lifecycle(m, today):
    """Date-level classification DOES NOT rely on successful KI/KO/P&L simulation."""
    if not (m.pricing_day and m.ko_start and m.final_eval and m.maturity_day):
        m.category = '資料不足'
        m.state = '商品日期待補'
    elif not (m.pricing_day <= m.ko_start <= m.final_eval <= m.maturity_day):
        m.category = '資料不足'
        m.state = '商品日期順序有誤'
    elif today < m.ko_start:
        m.category = '閉鎖中'
        m.state = '閉鎖中'
    elif today < m.final_eval:
        m.category = '比價中'
        m.state = '比價中'
    elif today <= m.maturity_day:
        m.category = '比價中'
        m.state = '到期結算期間'
    else:
        m.category = '近三個月出場' if recent_end({'end_event_date':m.maturity_day},today) else '歷史歸檔'
        m.state = '已到期（模型尚無 KO 結果）'


def _incomplete(m):
    """Do not hide an active FCN merely because its numerical model is incomplete."""
    m.principal_ratio = None
    m.earned_coupon_rate = None
    m.forecast_coupon_rate = None
    m.ko_date = None
    m.ki_touched = None
    if m.category in ('閉鎖中', '比價中'):
        m.state += '（試算資料待補）'
    return m


def model_one(product, legs, periods, price_matrix, holidays, rule=None, *, today=None):
    pid = str(product.get('product_id') or '').strip()
    m = ProductModel(pid)
    today = today or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    m.pricing_day = to_day(product.get('pricing_date'))
    m.ko_start = to_day(product.get('ko_start_date'))
    m.final_eval = to_day(product.get('final_eval_date'))
    m.maturity_day = to_day(product.get('maturity_date'))
    _date_lifecycle(m, today)

    # Compare the same central batch's raw inputs and derived API dates. This is
    # data integrity, never an approval gate or an alternate coupon calculation.
    rule = rule or {}
    for source, derived in [('期初訂價日','pricing_date'), ('起息日','issue_date'),
                            ('KO開始觀察日','ko_start_date'), ('期末評價日','final_eval_date'),
                            ('到期／交割日','maturity_date')]:
        if source in rule and to_day(rule[source]) != to_day(product.get(derived)):
            m.issues.append(f'中央輸入／API日期不一致：{source}')
    expected_count = as_positive_number(product.get('coupon_period_count'))
    if expected_count is not None and expected_count != len(periods):
        m.issues.append('中央API配息期數與實際期間不一致')

    m.coupon_mode = coupon_style(rule or {})
    m.ko_observation = '每交易日觀察；KO 記憶從觀察起日開始，不計閉鎖期'
    ko_barrier = ratio(product.get('ko_barrier_ratio'))
    strike = ratio(product.get('strike_ratio'))
    ki_barrier = ratio(product.get('ki_barrier_ratio'))
    annual_coupon = ratio(product.get('annual_coupon_rate'))
    ko_type = parse_ko(product.get('ko_type'))
    ki_type = parse_ki(product.get('ki_type'))
    m.levels = {'ko':ko_barrier*100 if ko_barrier is not None else None,
                'strike':strike*100 if strike is not None else None,
                'ki':None if ki_type=='Non-KI' else ki_barrier*100 if ki_barrier is not None else None,
                'ko_start':m.ko_start}

    if m.category == '資料不足':
        m.issues.append('中央商品日期缺漏或順序不正確')
    initial = {}
    for leg in legs:
        symbol = str(leg.get('ticker') or '').strip().upper()
        value = as_positive_number(leg.get('initial_price'))
        if not symbol or value is None or symbol in initial:
            m.issues.append('中央連結標的代號／期初價缺漏或重複')
            continue
        initial[symbol] = value
    if not initial or len(initial) != len(legs):
        m.issues.append('中央連結標的資料不完整')
    if ko_type is None:
        m.issues.append('中央 KO 類型未填（記憶式／非記憶式）')
    if ki_type is None:
        m.issues.append('中央 KI 類型未填（AKI／EKI／Non-KI）')
    if ki_type not in ('Non-KI', None) and ki_barrier is None:
        m.issues.append('中央 KI 門檻未填')
    if None in (ko_barrier, strike, annual_coupon):
        m.issues.append('中央 KO／Strike／年化票息未填')

    coupon_periods = []
    seen = set()
    for item in periods:
        if len(item) < 4 or type(item[0]) is not int or item[0]<1 or item[0] in seen:
            m.issues.append('中央配息期編號無效或重複')
            continue
        n, beg, end, payment = item[:4]
        seen.add(n)
        names = [f'第{n}期{x}' for x in ('起日','止日','付款日')]
        if any(name in rule for name in names):
            if [beg,end,payment] != [to_day(rule.get(name)) for name in names]:
                m.issues.append(f'中央第{n}期來源／API日期不一致')
        if not (beg and end and payment and beg <= end <= payment):
            m.issues.append(f'中央第 {n} 期計息起訖／付款日期不完整')
            continue
        coupon_periods.append(CouponPeriod(n, beg, end, payment))
    if not coupon_periods or len(coupon_periods) != len(periods):
        m.issues.append('中央配息期不存在或不完整')
    if len(coupon_periods) > 12:
        m.issues.append('中央配息期超過 12 期')
    issue_day = to_day(product.get('issue_date'))
    if coupon_periods and issue_day:
        if coupon_periods[0].start != issue_day:
            m.issues.append('中央首期起日與起息日不一致')
        if coupon_periods[-1].end != m.final_eval:
            m.issues.append('中央末期止日與期末評價日不一致')

    # A quote's absence can block KO/P&L, but must NOT block lifecycle display.
    quotes = {day: value for day, value in (price_matrix or {}).items()
              if isinstance(day, dt.date) and day <= today}
    available_days = sorted(quotes)
    if not available_days:
        m.issues.append('共用成分股價庫目前沒有可用的收盤價')
        return _incomplete(m)
    latest_day = available_days[-1]
    if m.pricing_day and latest_day < m.pricing_day:
        m.issues.append('成分股價庫尚未涵蓋商品定價日')

    # Show any available close-history even when another model input is missing.
    if m.pricing_day:
        upper = min(latest_day, m.final_eval or latest_day)
        last_seen = {}
        for day in available_days:
            if day < m.pricing_day or day > upper or day.weekday()>=5 or day in holidays:
                continue
            day_quotes = quotes[day] or {}
            if not initial or any(as_positive_number(day_quotes.get(t)) is None for t in initial):
                continue
            for t, start_price in initial.items():
                pct = float(day_quotes[t]) / start_price
                m.price_history.append({'date':day, 'stock':t, 'ratio':pct*100})
                last_seen[t] = pct
            m.latest_date = day
        if last_seen:
            m.worst_ticker = min(last_seen, key=last_seen.get)
            m.worst_ratio = last_seen[m.worst_ticker]

    if m.issues:
        return _incomplete(m)

    # Use V2 itself, not a second approximate version of V2 mechanics.
    # `as_of` is the last available EOD price, so the US session not yet closed
    # is not mistaken for a missing quote. Calendar classification still uses today.
    as_of = min(today, latest_day)
    v2 = calculate_v2(
        pricing_date=m.pricing_day, ko_start=m.ko_start, final_eval=m.final_eval,
        initial_prices=initial, daily_prices=quotes,
        ko_barrier=ko_barrier, strike=strike,
        ki_barrier=ki_barrier, ko_type=ko_type, ki_type=ki_type,
        annual_rate=annual_coupon, periods=tuple(coupon_periods),
        holidays=holidays, as_of=as_of)
    if v2.issues:
        m.issues.extend(v2.issues)
        return _incomplete(m)

    m.ko_date = v2.ko_date
    m.ki_touched = v2.ki_touched
    m.worst_ratio = v2.worst_ratio if v2.worst_ratio is not None else m.worst_ratio
    m.earned_coupon_rate = v2.coupon_total_rate
    m.principal_ratio = v2.principal_recovery_ratio
    if v2.ko_date:
        # Freeze every model display at the same event that stops the engine.
        m.price_history = [r for r in m.price_history if r['date'] <= v2.ko_date]
        m.latest_date = v2.ko_date
        event_ratios = {t:float(quotes[v2.ko_date][t])/p for t,p in initial.items()}
        m.worst_ticker = min(event_ratios, key=event_ratios.get)
        m.state = '模型提前 KO'
        m.category = '近三個月出場' if recent_end({'end_event_date':v2.ko_date},today) else '歷史歸檔'
    elif today >= m.final_eval and as_of < m.final_eval:
        m.issues.append('末日收盤價尚未取得；不能推定到期贖回')
        return _incomplete(m)
    else:
        _date_lifecycle(m, today)

    # Exposed per-period amounts follow the V2 canonical trading-day ratio.
    period_by_number = {p.number:p for p in coupon_periods}
    m.coupon_rows = []
    forecast = v2.coupon_total_rate or 0.0
    for r in v2.coupons:
        period = period_by_number[r.number]
        future = 0.0
        if m.ko_date is None and period.end > as_of:
            future = annual_coupon / 12
            forecast += future
        m.coupon_rows.append({
            '期數':r.number, '計息起日':period.start.isoformat(),
            '計息末日':period.end.isoformat(), '配息日':period.payment.isoformat(),
            '計息模式':m.coupon_mode,
            '整期交易日':r.full_trading_days, '計入交易日':r.ko_trading_days,
            '模型票息率':r.coupon_rate, '未來假設票息率':future,
        })
    m.forecast_coupon_rate = forecast
    return m

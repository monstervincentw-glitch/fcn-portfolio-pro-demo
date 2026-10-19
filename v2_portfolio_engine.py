"""Standalone FCN V2 mechanics, based on original Data!M34, F13, AW42:BD53.
No bank confirmation gate. Incomplete inputs produce an explicit unavailable result.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Mapping
from math import isfinite

@dataclass(frozen=True)
class CouponPeriod:
    number: int
    start: date
    end: date
    payment: date

@dataclass(frozen=True)
class CouponResult:
    number: int
    payment: date
    full_trading_days: int
    ko_trading_days: int
    accrual_ratio: float
    coupon_rate: float

@dataclass(frozen=True)
class V2Result:
    state: str
    ko_date: date | None
    ki_touched: bool | None
    worst_ratio: float | None
    principal_recovery_ratio: float | None
    coupons: tuple[CouponResult, ...]
    coupon_total_rate: float | None
    total_return_rate: float | None
    issues: tuple[str, ...]


def to_date(value):
    if isinstance(value, datetime): return value.date()
    if isinstance(value, date): return value
    if isinstance(value, (int, float)) and 20000 < value < 110000:
        return date(1899,12,30)+timedelta(days=int(value))
    if not value or str(value).strip() in ('', 'None'): return None
    try: return date.fromisoformat(str(value).strip()[:10].replace('/','-'))
    except ValueError: return None


def trading_days(start: date, end: date, holidays: Iterable[date] = ()) -> int:
    """NETWORKDAYS.INTL(...,1,holidays), inclusive endpoints."""
    if end < start: return 0
    closed=set(holidays)
    return sum((start+timedelta(days=i)).weekday()<5 and (start+timedelta(days=i)) not in closed
               for i in range((end-start).days+1))


def validate_coupon_periods(periods: Iterable[CouponPeriod], holidays: Iterable[date] = ()) -> tuple[CouponPeriod, ...]:
    """Validate exact supplied dates; never roll dates to a payment calendar."""
    periods = tuple(periods)
    closed = tuple(holidays)
    if not periods or len(periods) > 12:
        raise ValueError('配息期數缺漏或超過12期')
    previous = None
    for expected, p in enumerate(periods, start=1):
        if type(p.number) is not int or p.number != expected:
            raise ValueError('配息期編號缺漏、重複或順序錯誤')
        if not all(isinstance(d, date) for d in (p.start, p.end, p.payment)):
            raise ValueError(f'第{p.number}期起訖／付款日期缺漏')
        if not p.start <= p.end <= p.payment:
            raise ValueError(f'第{p.number}期起訖／付款日期順序錯誤')
        if previous is not None:
            if p.start <= previous:
                raise ValueError(f'第{p.number}期與前期重疊')
            if trading_days(previous+timedelta(days=1), p.start-timedelta(days=1), closed):
                raise ValueError(f'第{p.number}期前缺少交易日覆蓋')
        if not trading_days(p.start, p.end, closed):
            raise ValueError(f'第{p.number}期沒有交易日')
        previous = p.end
    return periods


def v2_coupon_periods(periods: Iterable[CouponPeriod], annual_rate: float, *,
                      ko_date: date | None = None, as_of: date | None = None,
                      holidays: Iterable[date] = ()) -> list[CouponResult]:
    as_of=as_of or date.today()
    closed=tuple(holidays)
    periods=validate_coupon_periods(periods, closed)
    output=[]
    for p in periods:
        if p.end<p.start: raise ValueError(f'Period {p.number}: end before start')
        total=trading_days(p.start,p.end,closed)
        if not total: raise ValueError(f'Period {p.number}: no trading days')
        if ko_date is not None:
            earned=0 if ko_date<p.start else trading_days(p.start,min(ko_date,p.end),closed)
        else:
            earned=total if p.end<=as_of else 0
        ratio=earned/total
        output.append(CouponResult(p.number,p.payment,total,earned,ratio,annual_rate/12*ratio))
    return output


def _finite_number(value):
    if isinstance(value, bool): return None
    try: number = float(value)
    except (TypeError, ValueError, OverflowError): return None
    return number if isfinite(number) else None


def _rate(value):
    if value is None or str(value).strip()=='': return None
    if isinstance(value, bool): return None
    raw = str(value).strip()
    v = _finite_number(raw.replace('%', ''))
    if v is None: return None
    return v/100 if '%' in raw or v>1 else v


def calculate_v2(*, pricing_date: date, ko_start: date, final_eval: date,
                 initial_prices: Mapping[str,float],
                 daily_prices: Mapping[date,Mapping[str,float]],
                 ko_barrier: float, strike: float, ki_barrier: float | None,
                 ko_type: str, ki_type: str, annual_rate: float,
                 periods: Iterable[CouponPeriod], holidays: Iterable[date],
                 as_of: date | None = None, holiday_calendar_complete: bool = True) -> V2Result:
    """Evaluate every required trading day, V2 memory/non-memory KO and KI, and F13 redemption.

    Missing daily prices invalidate settlement; do not treat a missing price as no KO/KI.
    Prices must be exact trading-date closes, never nearest-day substitutions.
    """
    today=as_of or date.today(); issues=[]; periods=tuple(periods); holidays=tuple(holidays)
    if not all((pricing_date,ko_start,final_eval)) or not pricing_date<=ko_start<=final_eval:
        issues.append('商品日期缺漏或順序錯誤')
    if not initial_prices or any(_finite_number(x) is None or _finite_number(x)<=0 for x in initial_prices.values()):
        issues.append('期初價格缺漏')
    ko_barrier=_rate(ko_barrier); strike=_rate(strike); ki_barrier=_rate(ki_barrier)
    annual_rate=_rate(annual_rate)
    if ko_type not in ('記憶式','非記憶式'): issues.append('KO 類型不完整')
    if ki_type not in ('AKI','EKI','Non-KI'): issues.append('KI 類型不完整')
    if ki_type!='Non-KI' and (ki_barrier is None or ki_barrier<=0): issues.append('KI 門檻缺漏')
    if (ko_barrier is None or strike is None or annual_rate is None
            or ko_barrier<=0 or strike<=0 or annual_rate<0): issues.append('商品比率錯誤')
    try:
        validate_coupon_periods(periods, holidays)
    except ValueError as exc:
        issues.append(str(exc))
    if not holiday_calendar_complete: issues.append('交易所休市日清單尚未確認完整')
    if issues: return V2Result('資料不足',None,None,None,None,(),None,None,tuple(issues))
    closed=set(holidays); ko_date=None; touched={ticker:False for ticker in initial_prices}
    aki=False; latest=None; missing=[]
    stop=min(final_eval,today)
    for i in range((stop-pricing_date).days+1):
        day=pricing_date+timedelta(days=i)
        if day.weekday()>=5 or day in closed: continue
        quotes=daily_prices.get(day,{})
        if any(_finite_number(quotes.get(t)) is None or _finite_number(quotes.get(t))<=0 for t in initial_prices):
            missing.append(day); continue
        ratios={t:float(quotes[t])/float(initial_prices[t]) for t in initial_prices}
        latest=ratios
        if ki_type=='AKI' and any(x<=ki_barrier for x in ratios.values()): aki=True
        # FCN V2 rule: the KO memory window begins ONLY on ko_start.
        # Hits in the initial locked period do not count toward future KO.
        if ko_start <= day <= final_eval and ko_date is None:
            if ko_type == '記憶式':
                for t, r in ratios.items():
                    touched[t] |= r >= ko_barrier
                knocked = all(touched.values())
            else:
                knocked = all(r >= ko_barrier for r in ratios.values())
            if knocked:
                ko_date = day
        if ko_date: break
    if missing:
        return V2Result('行情缺漏',None,None,None,None,(),None,None,
                        (f'缺少 {len(missing)} 個交易日完整行情（首日 {missing[0]}）',))
    if ki_type=='AKI': ki_touched=aki
    elif ki_type=='Non-KI': ki_touched=None
    else: ki_touched=None
    if ko_date is None and today>=final_eval:
        final_prices=daily_prices.get(final_eval,{})
        if any(_finite_number(final_prices.get(t)) is None or _finite_number(final_prices.get(t))<=0 for t in initial_prices):
            return V2Result('行情缺漏',None,ki_touched,None,None,(),None,None,('最終評價日行情缺漏',))
        latest={t:float(final_prices[t])/float(initial_prices[t]) for t in initial_prices}
        if ki_type=='EKI': ki_touched=any(x<=ki_barrier for x in latest.values())
    try: coupons=tuple(v2_coupon_periods(periods,annual_rate,ko_date=ko_date,as_of=today,holidays=closed))
    except ValueError as exc:
        return V2Result('配息資料錯誤',ko_date,ki_touched,None,None,(),None,None,(str(exc),))
    coupon_rate=sum(x.coupon_rate for x in coupons)
    if ko_date is not None:
        if sum(p.start<=ko_date<=p.end for p in periods)!=1:
            return V2Result('配息資料錯誤',ko_date,ki_touched,None,None,coupons,None,None,('KO 日未落於單一配息期間',))
        return V2Result('已提前KO',ko_date,ki_touched,min(latest.values()),1.0,coupons,coupon_rate,coupon_rate,())
    if today<final_eval:
        return V2Result('存續中',None,ki_touched,min(latest.values()) if latest else None,
                        None,coupons,coupon_rate,None,())
    worst=min(latest.values())
    principal=(min(1.,worst/strike) if worst<strike and (ki_type=='Non-KI' or ki_touched) else 1.)
    return V2Result('已到最終評價日',None,ki_touched,worst,principal,coupons,coupon_rate,
                    coupon_rate+principal-1.,())


def assert_complete_v2_inputs(periods: Iterable[CouponPeriod], *, ko_type: str,
                              ki_type: str, has_full_history: bool,
                              has_holiday_calendar: bool) -> None:
    if not tuple(periods): raise ValueError('Missing exact contract coupon periods')
    if ko_type not in ('記憶式','非記憶式'): raise ValueError('Missing V2 KO type')
    if ki_type not in ('AKI','EKI','Non-KI'): raise ValueError('Missing V2 KI type')
    if not has_full_history or not has_holiday_calendar:
        raise ValueError('Missing complete trading-day price history or holidays')

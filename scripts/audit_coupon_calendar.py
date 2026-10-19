"""Audit saved live formula results through the production central loader."""
from datetime import timedelta
import json
from pathlib import Path
from central_catalog import (load_model_inputs, PRODUCT_RANGE, LEGS_RANGE,
                             PERIOD_RANGE, CALENDAR_RANGE, INPUT_RANGE, to_day)
from v2_portfolio_engine import CouponPeriod, trading_days, v2_coupon_periods

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'docs/audit/evidence/period-calendar-20261019.json'


class SnapshotReader:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def read(self, sheet_id, span):
        self.calls.append((sheet_id, span))
        key = dict(zip([PRODUCT_RANGE, LEGS_RANGE, PERIOD_RANGE, CALENDAR_RANGE, INPUT_RANGE],
                       ['terms', 'legs', 'periods', 'calendar', 'inputs']))[span]
        return self.data[key]['values']


def audit(data):
    reader = SnapshotReader(data)
    catalog, holidays, periods, rules = load_model_inputs(reader)
    output = []
    for pid, product in catalog.products.items():
        if not to_day(product.get('issue_date')):
            continue
        rule = rules[pid]
        issue, final = to_day(product['issue_date']), to_day(product['final_eval_date'])
        ko = to_day(product['ko_start_date'])
        schedule, gaps, errors = [], [], []
        previous = None
        parsed = periods.get(pid, [])
        canonical = {r.number:r for r in v2_coupon_periods(
            [CouponPeriod(*p) for p in parsed], .12, as_of=final, holidays=holidays)}
        if not parsed or parsed[0][1] != issue:
            errors.append('起息日與首期起日不一致')
        if not parsed or parsed[-1][2] != final:
            errors.append('期末評價日與末期止日不一致')
        for n, start, end, payment in parsed:
            if [start, end, payment] != [to_day(rule.get(f'第{n}期{x}')) for x in ('起日','止日','付款日')]:
                errors.append(f'第{n}期來源／網站解析不一致')
            if not all((start, end, payment)) or not start <= end <= payment:
                errors.append(f'第{n}期日期缺漏或逆序')
                continue
            if previous and start <= previous:
                errors.append(f'第{n}期重疊')
            if previous and start > previous + timedelta(days=1):
                missing_days = [previous + timedelta(days=i) for i in range(1, (start-previous).days)]
                active = [d for d in missing_days if d.weekday()<5 and d not in holidays]
                gaps.append({'before_period':n, 'dates':[str(d) for d in missing_days],
                             'uncovered_trading_days':[str(d) for d in active]})
                if active:
                    errors.append(f'第{n}期前缺交易日覆蓋')
            previous = end
            schedule.append(dict(number=n,start=str(start),end=str(end),payment=str(payment),
                                 trading_days=canonical[n].full_trading_days,
                                 closed_endpoints=[name for name, d in [('start',start),('end',end)]
                                                   if d.weekday()>=5 or d in holidays],
                                 payment_on_exchange_closed=payment.weekday()>=5 or payment in holidays))
        if not (issue <= ko <= final):
            errors.append('KO起日範圍錯誤')
        output.append(dict(product_id=pid, issue=str(issue), ko_start=str(ko),
                           ko_equals_first_end=bool(parsed and ko==parsed[0][2]),
                           periods=schedule,gaps=gaps,errors=errors))
    return {'products':output, 'missing_products':sorted(set(catalog.products)-{p['product_id'] for p in output}),
            'source_calls':reader.calls}


if __name__ == '__main__':
    data = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    print(json.dumps(audit(data), ensure_ascii=False, indent=2))

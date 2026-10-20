"""Read-only consistency audit of a bounded, privacy-filtered Sheets snapshot.

Run from repo root: python -m scripts.audit_central_snapshot
No spreadsheet writes, network reads, or model calculations.
"""
from collections import Counter
from datetime import timedelta
import json
from math import isclose, isfinite
from pathlib import Path

from v2_portfolio_engine import to_date

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'docs/audit/evidence/central-20261019.json'


def blank(value):
    return value is None or value == ''


def number(value):
    if blank(value) or isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace('%', ''))
        if '%' in str(value):
            result /= 100
        return result if isfinite(result) else None
    except (ValueError, TypeError):
        return None


def equal(left, right, kind='text'):
    if blank(left) or blank(right):
        return blank(left) and blank(right)
    if kind == 'date':
        return to_date(left) is not None and to_date(left) == to_date(right)
    if kind == 'number':
        a, b = number(left), number(right)
        return a is not None and b is not None and isclose(a, b, abs_tol=1e-8)
    return str(left).strip() == str(right).strip()


def rows(data, name):
    return [row for row in data[name]['values'][1:] if row and not blank(row[0])]


def audit(data):
    errors, incomplete, products = [], [], []
    tables = {name: rows(data, name) for name in
              ('inputs', 'master', 'terms', 'legs', 'source_legs', 'periods')}
    for name, table in tables.items():
        keys = [(r[0], r[1]) if name == 'legs' else r[0] for r in table]
        for key, count in Counter(keys).items():
            if count > 1:
                errors.append(f'{name}: 重複鍵 {key}')
    source = {r[0]: r for r in tables['inputs']}
    for name in ('master', 'terms'):
        if set(source) != {r[0] for r in tables[name]}:
            errors.append(f'{name}: 商品代號集合與輸入表不一致')
    for name, id_col in [('legs', 0), ('source_legs', 1), ('periods', 1)]:
        for row in tables[name]:
            if row[id_col] not in source:
                errors.append(f'{name}: 孤立商品 {row[id_col]}')

    for pid, src in source.items():
        problems, notes = [], []
        terms = next((r for r in tables['terms'] if r[0] == pid), None)
        master = next((r for r in tables['master'] if r[0] == pid), None)
        for name, dest in [('master', master), ('terms', terms)]:
            if dest is None:
                problems.append(f'{name}: 缺整列')
                continue
            for col in range(13):
                kind = 'date' if 2 <= col <= 6 else 'number' if 7 <= col <= 10 else 'text'
                if not equal(src[col], dest[col], kind):
                    problems.append(f'{name}: 第{col+1}欄與輸入不一致')
        if blank(src[2]):
            incomplete.append(pid)
            errors.extend(f'{pid}: {p}' for p in problems)
            continue
        dates = [to_date(v) for v in src[2:7]]
        if None in dates or dates != sorted(dates):
            problems.append('日期缺漏或順序錯誤')
        for col in (7, 8, 9):
            if number(src[col]) is None or number(src[col]) <= 0:
                problems.append(f'必要比率第{col+1}欄缺漏或無效')
        non_ki = 'Non-KI' in str(src[12])
        if not non_ki and (number(src[10]) is None or number(src[10]) <= 0):
            problems.append('KI 比例缺漏或無效')
        if src[1] not in ('USD', 'EUR', 'TWD', 'HKD', 'JPY', 'AUD', 'GBP', 'CHF', 'CAD'):
            problems.append('幣別需確認')
        if src[11] not in ('記憶式', '記憶式KO', '非記憶式'):
            problems.append('KO 類型無法辨識')
        if not any(t in str(src[12]) for t in ('EKI', 'AKI', 'Non-KI')):
            problems.append('KI 類型無法辨識')
        # Snapshot projects original V:AT to indexes 13:38 and AU:CD to 38:74.
        expected_legs = [(n+1, src[13+n*5:18+n*5]) for n in range(5)
                         if not all(blank(v) for v in src[13+n*5:18+n*5])]
        actual_legs = [r for r in tables['legs'] if r[0] == pid]
        source_legs = [r for r in tables['source_legs'] if r[1] == pid]
        if len(expected_legs) != len(actual_legs) or len(source_legs) != len(actual_legs):
            problems.append('標的數量不一致')
        for n, leg in expected_legs:
            targets = [r[2:7] for r in actual_legs if number(r[1]) == n]
            targets += [r[3:8] for r in source_legs if number(r[2]) == n]
            if len(targets) != 2 or any(not all(equal(a, b, 'text' if i == 0 else 'number')
                    for i, (a, b) in enumerate(zip(leg, target))) for target in targets):
                problems.append(f'標的{n}來源／API不一致')
            initial = number(leg[1])
            if not leg[0] or initial is None or initial <= 0:
                problems.append(f'標的{n}代號／期初價無效')
            else:
                for price_idx, ratio_idx in [(2, 8), (3, 10), (4, 9)]:
                    if price_idx == 3 and non_ki:
                        continue
                    barrier, ratio = number(leg[price_idx]), number(src[ratio_idx])
                    if barrier is None or ratio is None or abs(barrier-initial*ratio) > .00501:
                        problems.append(f'標的{n}障礙價第{price_idx+1}欄與比率不符')
        expected_periods = [(n+1, src[38+n*3:41+n*3]) for n in range(12)
                            if not all(blank(v) for v in src[38+n*3:41+n*3])]
        actual_periods = [r for r in tables['periods'] if r[1] == pid]
        if len(expected_periods) != len(actual_periods):
            problems.append('配息期數不一致')
        previous_end = None
        for n, period in expected_periods:
            targets = [r[3:6] for r in actual_periods if number(r[2]) == n]
            if len(targets) != 1 or not all(equal(a, b, 'date') for a, b in zip(period, targets[0])):
                problems.append(f'第{n}期來源／衍生分頁不一致')
            days = [to_date(v) for v in period]
            if None in days or days != sorted(days):
                problems.append(f'第{n}期日期無效')
            else:
                if previous_end and days[0] <= previous_end:
                    problems.append(f'第{n}期與前期重疊')
                if previous_end and days[0] > previous_end + timedelta(days=1):
                    notes.append(f'第{n}期前有日曆間隔，需休市日核對')
                previous_end = days[1]
        for name, dest in [('master', master), ('terms', terms)]:
            if dest and (number(dest[13]) != len(expected_legs) or number(dest[14]) != len(expected_periods)):
                problems.append(f'{name}: 標的／配息期計數不符')
        products.append(dict(product_id=pid, legs=[x[1][0] for x in expected_legs],
                             periods=len(expected_periods), errors=problems, notes=notes))
        errors.extend(f'{pid}: {p}' for p in problems)
    return dict(count=len(source), complete_basic=products, incomplete=incomplete, errors=errors)


def main():
    result = audit(json.loads(SNAPSHOT.read_text(encoding='utf-8')))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return bool(result['errors'])


if __name__ == '__main__':
    raise SystemExit(main())

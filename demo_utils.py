"""Aggregation helpers for display; do not conflate currencies."""
import datetime as dt
import calendar
from math import isfinite

def _date(value):
    if isinstance(value, dt.datetime): return value.date()
    if isinstance(value, dt.date): return value
    try: return dt.date.fromisoformat(str(value).strip()[:10].replace('/', '-'))
    except (ValueError, TypeError): return None

def is_active_product(p):
    group = str(p.get('monitor_group') or '').strip()
    state = str(p.get('model_state') or '').strip()
    if any(x in group+state for x in ('待建檔','條款不足','歷史歸檔','結束後','提前KO','已到期','已結案','已贖回','已結束')):
        return False
    return any(x in group for x in ('持續監控','日常監控','存續監控')) or any(x in state for x in ('執行中','存續中'))

def recent_end(p, today):
    end = next((d for k in ('end_event_date','ko_date','maturity_date','final_eval_date') if (d := _date(p.get(k))) and d <= today), None)
    until = _date(p.get('visible_until'))
    if end:
        if until is None:
            month = end.month - 1 + 3
            year = end.year + month // 12
            month = month % 12 + 1
            until = dt.date(year, month, min(end.day, calendar.monthrange(year, month)[1]))
        return end <= today <= until
    # Honor the master sheet's explicit tracking category when its dates are absent.
    group = str(p.get('monitor_group') or '')
    return ('結束後三個月' in group or '結束後3個月' in group) and (until is None or today <= until)
def num(v):
    if isinstance(v,bool): return None
    try:
        n=float(v) if v not in ('',None) else None
        return n if n is not None and isfinite(n) else None
    except (ValueError,TypeError):return None

def product_group(p, today=None):
    """Map real master-sheet labels to the four website views.

    Actual Google Sheets calls active products 持續監控; the website used to filter
    only 日常監控, hiding ALL active products. Never rewrite source values.
    """
    group = str(p.get("monitor_group") or "").strip()
    state = str(p.get("model_state") or "").strip()
    if "待建檔" in group or "待建檔" in state or "條款不足" in state:
        return "待建檔"
    if is_active_product(p):
        return "日常監控"
    if "歷史歸檔" in group or "結束後" in group or any(x in state for x in ("提前KO", "已到期", "已結案", "已贖回", "已結束")):
        today = today or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
        return "日常監控" if recent_end(p, today) else "歷史歸檔"
    return "其他"

def currency_summary(rows):
    """Model-only per-currency totals derived from central V2-enriched holdings.

    Known subtotals remain visible even when another holding cannot be modeled.
    Missing data is counted separately rather than silently converted to zero.
    Legacy ledger receipts/estimated projections are never inputs here.
    """
    fields = {
        'invested': 'invested_amount',
        'returned': 'estimated_principal_total',
        'outstanding': 'estimated_outstanding',
        'coupon': 'estimated_coupon_total',
    }
    output = {
        currency: {
            **{key: 0.0 for key in fields},
            'count': 0,
            'known_count': {key: 0 for key in fields},
            'missing_count': {key: 0 for key in fields},
        }
        for currency in ('USD', 'EUR', 'JPY')
    }
    for row in rows:
        item = output.get(row.get('currency'))
        if item is None:
            continue
        item['count'] += 1
        for metric, source in fields.items():
            value = num(row.get(source))
            # A valid still-active model has returned no principal *yet*.
            # This is zero modeled recovery, NOT a missing settlement receipt.
            if (metric == 'returned' and value is None
                    and row.get('v2_active_exposure') is True
                    and num(row.get('estimated_outstanding')) is not None
                    and not row.get('v2_issues')):
                value = 0.0
            if value is None:
                item['missing_count'][metric] += 1
            else:
                item[metric] += value
                item['known_count'][metric] += 1
    return output

"""Pure presentation helpers for SYNTHETIC demo data (no personal or cloud identifiers)."""
import math

CURRENCIES = ('USD', 'EUR', 'JPY')

def num(value):
    try:
        n=float(value)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):
        return None

def currency_summary(rows):
    out={}
    for cc in CURRENCIES:
        subset=[r for r in rows if r.get('currency')==cc]
        modeled=[r for r in subset if num(r.get('estimated_outstanding')) is not None]
        pending=[r for r in subset if num(r.get('estimated_outstanding')) is None]
        total=lambda rows,key:sum(num(r.get(key)) or 0 for r in rows)
        out[cc]={
            'count':len(subset),
            'invested':total(subset,'invested_amount'),
            'returned':total(subset,'estimated_principal_total'),
            'coupon':total(subset,'estimated_coupon_total'),
            'outstanding':total(modeled,'estimated_outstanding'),
            'pending_principal':total(pending,'invested_amount'),
            'pending_count':len(pending),
            'pnl':total(subset,'estimated_pnl'),
        }
    return out

def product_group(p):
    x=str(p.get('visibility_flag') or '')
    if '待建檔' in x:return '待建檔'
    if '顯示中' in x:return '日常監控'
    if '超過三個月' in x:return '歷史歸檔'
    return '其他'

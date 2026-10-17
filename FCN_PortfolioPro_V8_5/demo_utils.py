"""Aggregation helpers for display; do not conflate currencies."""
def num(v):
    try:return float(v) if v not in ('',None) else None
    except (ValueError,TypeError):return None

def product_group(p):
    return str(p.get('monitor_group') or '待建檔')

def currency_summary(rows):
    output={c:dict(invested=0.,returned=0.,outstanding=0.,coupon=0.,pending_count=0,pending_principal=0.,count=0) for c in ('USD','EUR','JPY')}
    for r in rows:
        d=output.get(r.get('currency'))
        if d is None:continue
        principal=num(r.get('invested_amount')) or 0
        d['count']+=1;d['invested']+=principal
        if num(r.get('estimated_outstanding')) is None:
            d['pending_count']+=1;d['pending_principal']+=principal
        else:
            d['outstanding']+=num(r.get('estimated_outstanding')) or 0
        d['returned']+=num(r.get('estimated_principal_total')) or 0
        d['coupon']+=num(r.get('estimated_coupon_total')) or 0
    return output

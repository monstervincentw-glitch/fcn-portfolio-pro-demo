"""Aggregation helpers for display; do not conflate currencies."""
def num(v):
    try:return float(v) if v not in ('',None) else None
    except (ValueError,TypeError):return None

def product_group(p):
    """Map real master-sheet labels to the four website views.

    Actual Google Sheets calls active products 持續監控; the website used to filter
    only 日常監控, hiding ALL active products. Never rewrite source values.
    """
    group = str(p.get("monitor_group") or "").strip()
    state = str(p.get("model_state") or "").strip()
    if "待建檔" in group or "待建檔" in state or "條款不足" in state:
        return "待建檔"
    if "歷史歸檔" in group or "結束後" in group or any(x in state for x in ("提前KO", "已到期", "已結案")):
        return "歷史歸檔"
    if group in ("持續監控", "日常監控", "存續監控") or any(x in state for x in ("執行中", "存續中")):
        return "日常監控"
    return "其他"

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

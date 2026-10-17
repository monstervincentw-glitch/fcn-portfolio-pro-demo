"""Pure, read-only, non-PII portfolio dashboard aggregation.
No Google Sheets mutations, client identifiers or web requests.
"""
from __future__ import annotations

def _has_source(product):
    return str(product.get('source_connection') or '').strip().lower() in ('已連線','connected','ok','✅ 已連線')

def summarize_portfolio(customers, holdings, products):
    missing=sum(1 for p in products if not _has_source(p))
    return {'customers':len(customers),'holdings':len(holdings),'products':len(products),
            'missing_sources':missing,'quality_flags':missing}

def rank_quality_issues(products, holdings):
    out=[]
    for p in products:
        if not _has_source(p):
            out.append({'FCN':p.get('product_id',''),'待確認':'商品來源尚未確認','判定':'不計算 KI／Strike 安全距離'})
    return sorted(out,key=lambda x:x['FCN'])

def stock_exposures(product_to_symbols, symbol):
    key=symbol.strip().upper()
    return sorted([p for p,stocks in product_to_symbols.items() if key in {str(s).upper() for s in stocks}])


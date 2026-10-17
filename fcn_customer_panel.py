"""FCN product-linked client holdings panel. PIN gate must already have passed.

Read-only from the already validated in-memory HOLDINGS; do not access private
spreadsheets or create any persistent client cache here.
"""
from __future__ import annotations
import datetime as dt
import re
import pandas as pd
import streamlit as st


def _mask_name(value: object) -> str:
    name = str(value or '').strip()
    if not name:
        return '未提供'
    # Existing masked names are kept as supplied by the master sheet.
    if '*' in name or '＊' in name:
        return name
    # Never expose an unmasked source customer identifier verbatim.
    if len(name) == 1:
        return '*'
    if len(name) == 2:
        return name[0] + '*'
    return name[0] + '*' * (len(name) - 2) + name[-1]


def _money(value: object, ccy: str) -> str:
    try:
        number = float(value)
        if not (0 <= number < 1e16):
            return '—'
        return f'{ccy} {number:,.0f}' if ccy == 'JPY' else f'{ccy} {number:,.2f}'
    except (ValueError, TypeError, OverflowError):
        return '—'


def _day(value: object) -> str:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.strftime('%Y/%m/%d')
    if isinstance(value, (int, float)) and 20_000 < value < 110_000:
        return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(value))).strftime('%Y/%m/%d')
    t = str(value or '').strip()[:10]
    if re.fullmatch(r'\d{4}[-/]\d{2}[-/]\d{2}', t):
        return t.replace('-', '/')
    return '—'


def render_product_clients(product_id: str, holdings: list[dict], *, mode: str) -> None:
    """Render only on the PIN-protected FCN Product page. Default is collapsed."""
    if mode == 'diagnostic':
        return
    # Explicit product match, no cross-product aggregation / client data leak.
    rows = [r for r in holdings if str(r.get('product_id') or '').strip() == product_id]
    with st.expander('🔒 承作客戶資料（點擊展開）', expanded=False):
        st.caption('內部限閱 · 唯讀 · 僅顯示遮罩客戶名稱；預設收合。請遵守機構資料使用規範。')
        if not rows:
            st.info('此商品目前沒有已登錄的客戶持倉。')
            return
        view = []
        for r in rows:
            ccy = str(r.get('currency') or 'USD').upper()
            view.append({
                '客戶（遮罩）': _mask_name(r.get('customer_id')),
                '幣別': ccy,
                '承作金額': _money(r.get('invested_amount'), ccy),
                '申購日期': _day(r.get('trade_date')),
                '模型狀態': str(r.get('estimated_settlement_state') or '—'),
            })
        st.dataframe(pd.DataFrame(view), use_container_width=True, hide_index=True)
        st.caption(f'共 {len(rows)} 筆承作紀錄；同一客戶多次承作分別列示。結算狀態為模型推定，非銀行入帳證明。')

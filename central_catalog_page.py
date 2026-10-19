"""Compatibility entrypoint for the existing separate Streamlit central-catalog page.
There is no bank quote/contract confirmation gate.
"""
from __future__ import annotations

def render_central_catalog(reader,holdings):
    from central_live_pages import render_product_page
    return render_product_page(reader,holdings,[])

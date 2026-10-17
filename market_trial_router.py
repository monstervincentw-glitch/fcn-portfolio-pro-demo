"""Switch between V8.4 Google Sheets price library and existing Massive mode."""
import streamlit as st

def render_market_trial():
    provider=st.radio('行情來源', ['Google Sheets 股價庫（2024起，已儲存真實價格）','Massive 即時查詢歷史日線（原V8.2）'], horizontal=False, key='v84_trial_source')
    if provider.startswith('Google Sheets'):
        from market_sheet_trial_page import render_market_trial as render
    else:
        from market_trial_page import render_market_trial as render
    return render()

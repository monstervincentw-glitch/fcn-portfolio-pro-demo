"""V8 presentation only: no credentials, Sheets access, or portfolio calculations."""
from __future__ import annotations

import base64
import html
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COLORS = ["#986127", "#547C70", "#B65F4D", "#76668D", "#497C91"]
LEVEL_COLORS = ["#517A61", "#A36B22", "#B34E48"]


@lru_cache(maxsize=1)
def hero_uri() -> str:
    image = ROOT / "assets" / "shiba-login.png"
    return "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode("ascii")


def apply_theme() -> None:
    import streamlit as st
    css = (ROOT / "assets" / "warm-theme.css").read_text(encoding="utf-8")
    st.markdown("<style>" + css + "</style>", unsafe_allow_html=True)


def login_intro() -> None:
    import streamlit as st
    # A marker scopes login-only layout; the native form remains keyboard accessible.
    st.markdown('<span class="fcn-login-marker"></span>', unsafe_allow_html=True)
    st.markdown("<style>.stApp:has(.fcn-login-marker){background-image:linear-gradient(90deg,transparent 35%,rgba(250,246,239,.18) 65%,rgba(250,246,239,.45)),url('"
                + hero_uri() + "');background-size:cover;background-position:left center;background-attachment:fixed}</style>", unsafe_allow_html=True)
    st.markdown('<div class="fcn-login-heading"><span class="fcn-eyebrow">FCN PORTFOLIO PRO · V8</span>'
                '<h1>每一份投資，<br>都值得用心照看。</h1>'
                '<p>歡迎回到你的投資工作台</p></div>', unsafe_allow_html=True)


def page_intro(title: str, subtitle: str, eyebrow: str = "PORTFOLIO WORKSPACE") -> None:
    import streamlit as st
    st.markdown(f'<header class="fcn-page-heading"><span class="fcn-eyebrow">{html.escape(eyebrow)}</span>'
                f'<h2>{html.escape(title)}</h2><p>{html.escape(subtitle)}</p></header>', unsafe_allow_html=True)


def status_card(product: str, currency: str, status: str) -> None:
    import streamlit as st
    tone = "pending" if any(x in status for x in ("待建檔", "不足", "未知")) else "neutral" if "存續" in status else "success"
    st.markdown(f'<div class="fcn-status-row"><div><strong>{html.escape(str(product))}</strong>'
                f'<span class="fcn-currency">{html.escape(str(currency))}</span></div>'
                f'<span class="fcn-status {tone}">{html.escape(str(status))}</span></div>', unsafe_allow_html=True)


def style_chart(chart):
    """Apply presentation config only; never transform source values."""
    return (chart.configure(background="#FFFCF7")
            .configure_view(stroke=None)
            .configure_axis(gridColor="#EAE0D2", domainColor="#D8C9B5", tickColor="#D8C9B5",
                            labelColor="#6D5C4B", titleColor="#514333", labelFontSize=12, titleFontSize=12)
            .configure_legend(labelColor="#514333", titleColor="#514333", orient="bottom", labelFontSize=12))

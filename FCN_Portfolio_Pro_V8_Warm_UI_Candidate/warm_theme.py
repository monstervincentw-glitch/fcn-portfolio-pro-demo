"""V8.1 presentation-only refinements; no credentials, Sheets access, or calculations.

Keeps the V8 warm-theme CSS and all existing business/authorization code unchanged.
The newly composed Shiba illustration is a separate asset, preserving V8's original.
"""
from __future__ import annotations

import base64
import html
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COLORS = ["#986127", "#547C70", "#B65F4D", "#76668D", "#497C91"]
LEVEL_COLORS = ["#517A61", "#A36B22", "#B34E48"]

# Styles deliberately scoped to existing Streamlit page classes/testids. They
# affect presentation only and preserve the native accessible form controls.
POLISH_CSS = r"""
/* FCN Portfolio Pro V8.1 | warm refinement; no data or calculation changes */
:root { --fcn-paper:#FAF6EF; --fcn-card:#FFFCF7; --fcn-ink:#403529; --fcn-gold:#946328; }

/* Keep the first screen focused on the portfolio instead of a tall welcome banner. */
.fcn-banner { padding:17px 25px !important; margin-bottom:17px !important;
  border-radius:18px !important; background:linear-gradient(116deg,#F1E1CA,#FBF1E4) !important; }
.fcn-banner h1 { font-size:clamp(1.30rem,2.1vw,1.65rem) !important; }
.fcn-banner p { margin-top:5px !important; line-height:1.5 !important; }
.fcn-banner::after { opacity:.26 !important; }
.fcn-page-heading { padding:7px 0 13px !important; }
.fcn-section { margin:1.1rem 0 .75rem !important; }

/* Muted notices. Severity remains distinguishable by symbols and text. */
[data-testid="stAlert"] { border-color:#E8D5B7 !important; box-shadow:none !important; }
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]),
[data-testid="stAlert"][kind="info"] { background:#F6EADB !important; color:#6C512C !important; }
[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]),
[data-testid="stAlert"][kind="warning"] { background:#F8EDCB !important; color:#7D581A !important; }

/* Less dense dashboard, balanced metrics and navigational whitespace. */
[data-testid="stMetric"] { padding:16px 19px !important; min-height:101px !important;
  box-shadow:0 5px 18px rgba(100,72,36,.05) !important; }
.fcn-panel,[data-testid="stExpander"], [data-testid="stForm"] { box-shadow:0 6px 20px rgba(99,68,28,.04); }
[data-testid="stVegaLiteChart"] { background:#FFFCF7; border-color:#E7D9C5; }
[data-testid="stDataFrame"] { border-color:#E7D9C5; }
button[kind="primary"],button[kind="primaryFormSubmit"] { background:#946328 !important; color:#FFF !important; }
button[kind="primary"]:hover,button[kind="primaryFormSubmit"]:hover {
  background:#76501F !important; border-color:#76501F !important; }

/* A narrower sidebar gives tables and charts room on wide screens. */
@media (min-width:1100px) {
  section[data-testid="stSidebar"] { width:320px !important; min-width:320px !important; }
  section[data-testid="stSidebar"] > div:first-child { width:320px !important; }
  .block-container { padding-top:1.7rem !important; }
}

/* Keep title comfortably below the browser header on the Shiba login page. */
.stApp:has(.fcn-login-marker) .block-container {
  padding-top:clamp(5.5rem,11vh,8rem) !important;
  padding-bottom:3.4rem !important;
  min-height:100vh !important;
}
.stApp:has(.fcn-login-marker) .fcn-login-heading { margin-top:5px !important; margin-bottom:20px !important; }
.stApp:has(.fcn-login-marker) .fcn-login-heading .fcn-eyebrow {
  margin-bottom:13px !important; padding-top:3px !important; letter-spacing:.14em;
}
.stApp:has(.fcn-login-marker) .fcn-login-heading h1 {
  font-size:clamp(1.8rem,3vw,2.7rem) !important; line-height:1.38 !important;
}
.stApp:has(.fcn-login-marker) [data-testid="stForm"] {
  padding:25px 29px !important;
  border:1px solid rgba(224,204,175,.9) !important;
  box-shadow:0 18px 55px rgba(112,75,29,.13) !important;
}
.stApp:has(.fcn-login-marker) [data-testid="stAlert"] {
  background:#F7E9D1 !important; color:#705126 !important;
  border:1px solid #E7CCA0 !important; border-radius:13px !important;
}
.stApp:has(.fcn-login-marker) [data-testid="stAlert"] * { color:inherit !important; }

/* Smaller screens: do not force desktop sidebar or push the form off-screen. */
@media (max-width:900px) {
  .stApp:has(.fcn-login-marker) .block-container { padding:40vh 5% 3.5rem !important; }
  .stApp:has(.fcn-login-marker) [data-testid="stForm"] { padding:20px !important; }
}
@media (max-width:540px) {
  .stApp:has(.fcn-login-marker) .block-container { padding-top:39vh !important; }
  .stApp:has(.fcn-login-marker) .fcn-login-heading h1 { font-size:1.48rem !important; }
  .fcn-banner { padding:14px 18px !important; }
}
@media (prefers-reduced-motion:reduce) { * { animation:none !important; transition:none !important; } }
"""


@lru_cache(maxsize=1)
def hero_uri() -> str:
    v81 = ROOT / "assets" / "shiba-login-v8-1.jpg"
    original = ROOT / "assets" / "shiba-login.png"
    image = v81 if v81.is_file() else original
    mime = "image/jpeg" if image.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64," + base64.b64encode(image.read_bytes()).decode("ascii")


def apply_theme() -> None:
    import streamlit as st
    css = (ROOT / "assets" / "warm-theme.css").read_text(encoding="utf-8")
    st.markdown("<style>" + css + "\n" + POLISH_CSS + "</style>", unsafe_allow_html=True)


def login_intro() -> None:
    import streamlit as st
    st.markdown('<span class="fcn-login-marker"></span>', unsafe_allow_html=True)
    st.markdown("<style>.stApp:has(.fcn-login-marker){background-image:linear-gradient(90deg,transparent 35%,rgba(250,246,239,.18) 65%,rgba(250,246,239,.45)),url('"
                + hero_uri() + "');background-size:cover;background-position:left center;background-attachment:fixed}</style>", unsafe_allow_html=True)
    st.markdown('<div class="fcn-login-heading"><span class="fcn-eyebrow">FCN PORTFOLIO PRO · V8.1</span>'
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

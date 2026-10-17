"""PIN-only user experience for FCN Portfolio Pro.

Server-side access gate runs before ANY Sheets API calls. For production use,
combine with organisational approval, read-only credentials and hosting/network
controls. A six-digit PIN alone is not a high-assurance security control.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import threading
import time

PIN_PATTERN = re.compile(r"[0-9]{6}\Z")
MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60
SESSION_MAX_AGE = 30 * 60  # 30 minutes of inactivity


def pin_valid(pin: object) -> bool:
    return isinstance(pin, str) and bool(PIN_PATTERN.fullmatch(pin))


def pin_matches(candidate: object, expected: str) -> bool:
    return pin_valid(expected) and isinstance(candidate, str) and bool(
        PIN_PATTERN.fullmatch(candidate) and hmac.compare_digest(candidate, expected)
    )


def session_tag(pin: str) -> str:
    """Changing the PIN invalidates current Streamlit session authorization."""
    return hashlib.sha256(("fcn-pin-session-v2:\x00" + pin).encode("utf-8")).hexdigest()


class AttemptLimiter:
    """Shared within ONE server process; not a distributed brute-force solution."""
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.failures = 0
        self.locked_until = 0.0

    def blocked(self) -> int:
        with self.lock:
            return max(0, int(self.locked_until - time.monotonic() + 0.999))

    def record(self, succeeded: bool) -> None:
        with self.lock:
            if succeeded:
                self.failures = 0
                self.locked_until = 0.0
            else:
                self.failures += 1
                if self.failures >= MAX_FAILURES:
                    self.failures = 0
                    self.locked_until = time.monotonic() + LOCK_SECONDS


def can_enter_mode(mode: str, approved: bool) -> bool:
    """Explicit production approval is required in addition to a valid PIN."""
    if mode not in {"demo", "diagnostic", "live"}:
        return False
    if mode == "live" and approved is not True:
        return False
    return True


def gate(config: dict, app_mode: str = "demo", bank_approved: bool = False) -> None:
    """Stop unauthenticated Streamlit execution before any business-data fetch."""
    import streamlit as st

    mode = str(app_mode).strip().lower()
    if not can_enter_mode(mode, bank_approved):
        st.error("🔒 尚未啟用的資料模式。正式資料需確認銀行核准並在 Secrets 設定 bank_approved = true。")
        st.stop()

    pin = config.get("pin")
    if not pin_valid(pin):
        st.error('🔒 請先在 Streamlit Secrets 的 [site_login] 設定 pin = "六位數字"。')
        st.stop()

    fingerprint = session_tag(pin)
    now = time.monotonic()
    if st.session_state.get("fcn_authorized_session") == fingerprint:
        last = st.session_state.get("fcn_last_activity")
        if isinstance(last, (int, float)) and 0 <= now - last < SESSION_MAX_AGE:
            st.session_state["fcn_last_activity"] = now
            return

    st.session_state.pop("fcn_authorized_session", None)
    st.session_state.pop("fcn_last_activity", None)

    @st.cache_resource
    def limiter() -> AttemptLimiter:
        return AttemptLimiter()

    limit = limiter()

    # V8.5.6: one responsive layout, not independently positioned fragments.
    # Current warm_theme.py already embeds the original Shiba PNG and warm CSS.
    from warm_theme import hero_image
    st.markdown(r"""
<style>
/* Scoped to the PIN page. No absolute/fixed positions or dependence on assets/. */
.stApp:has(.fcn-login-unified) .block-container {
    max-width:1180px !important;
    padding:clamp(2.0rem,6vh,4.2rem) clamp(1rem,3vw,2rem) 3rem !important;
}
.stApp:has(.fcn-login-unified) section[data-testid="stSidebar"] { display:none !important; }
.stApp:has(.fcn-login-unified) [data-testid="stImage"] img {
    width:100% !important;
    height:auto !important;
    max-height:480px !important;
    aspect-ratio:1.48 !important;
    object-fit:cover !important;
    object-position:30% center !important;
    border-radius:24px !important;
    box-shadow:0 18px 42px rgba(91,59,24,.13) !important;
}
.stApp:has(.fcn-login-unified) .fcn-unified-heading {
    padding:.3rem .2rem 1rem;
}
.stApp:has(.fcn-login-unified) .fcn-unified-eyebrow {
    font-size:.76rem !important;
    font-weight:750 !important;
    letter-spacing:.11em;
    color:#946328 !important;
}
.stApp:has(.fcn-login-unified) .fcn-unified-heading h1 {
    color:#513a26 !important;
    font-size:clamp(1.65rem,2.65vw,2.45rem) !important;
    font-weight:800 !important;
    line-height:1.34 !important;
    margin:1rem 0 1rem !important;
    letter-spacing:0 !important;
}
.stApp:has(.fcn-login-unified) .fcn-unified-heading p {
    color:#775f49 !important;
    line-height:1.7 !important;
    margin:0 !important;
    font-size:.96rem !important;
}
/* Native st.container is the one and only card containing heading + PIN form. */
.stApp:has(.fcn-login-unified) [data-testid="stForm"] {
    border:0 !important;
    padding:0 !important;
    background:transparent !important;
    box-shadow:none !important;
}
.stApp:has(.fcn-login-unified) [data-testid="stFormSubmitButton"] button {
    border-radius:11px !important;
    background:#946328 !important;
    color:#fff !important;
    border-color:#946328 !important;
}
@media (max-width:750px) {
    .stApp:has(.fcn-login-unified) .block-container {padding:1rem .8rem 2rem !important;}
    .stApp:has(.fcn-login-unified) [data-testid="stImage"] img {max-height:320px !important;aspect-ratio:1.65 !important;}
    .stApp:has(.fcn-login-unified) .fcn-unified-heading h1 {font-size:1.8rem !important;}
}
</style>
<div class="fcn-login-unified" aria-hidden="true"></div>
""", unsafe_allow_html=True)

    left, right = st.columns([1.06, 0.94], gap="large", vertical_alignment="center")
    with left:
        # Native image element is INSIDE the same horizontal layout as the PIN card.
        st.image(hero_image(), use_container_width=True)
    with right:
        with st.container(border=True):
            st.markdown('''<div class="fcn-unified-heading"><span class="fcn-unified-eyebrow">FCN PORTFOLIO PRO · V8.5.6</span>
<h1>每一份投資，<br>都值得用心照看。</h1>
<p>歡迎回到你的投資工作台</p></div>''', unsafe_allow_html=True)
            if mode == "demo":
                st.info("目前為虛構資料展示模式，不含真實客戶資料。")
            elif mode == "diagnostic":
                st.info("登入後只檢查試算表欄位，不顯示投資資料。")
            else:
                st.caption("資料由網站伺服器從私人 Google Sheets 唯讀取得。")

            remaining = limit.blocked()
            if remaining:
                st.error(f"輸入錯誤次數過多，請約 {max(1, (remaining + 59) // 60)} 分鐘後再試。")
                st.stop()

            with st.form("fcn_pin_login", clear_on_submit=True):
                candidate = st.text_input(
                    "6 位數字 PIN", type="password", max_chars=6,
                    placeholder="請輸入 6 位數字"
                )
                submitted = st.form_submit_button("登入 FCN Portfolio Pro", type="primary", use_container_width=True)

            if submitted:
                valid = pin_matches(candidate, pin)
                limit.record(valid)
                if valid:
                    st.session_state["fcn_authorized_session"] = fingerprint
                    st.session_state["fcn_last_activity"] = time.monotonic()
                    st.rerun()
                st.error("PIN 不正確，請重新輸入。")
    st.stop()


def logout() -> None:
    import streamlit as st
    st.session_state.pop("fcn_authorized_session", None)
    st.session_state.pop("fcn_last_activity", None)
    st.rerun()

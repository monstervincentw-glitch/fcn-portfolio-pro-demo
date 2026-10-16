"""Server-side password gate for a *single-authorized-user* Streamlit app.

Credentials are read from Streamlit Secrets at runtime, never hardcoded or
sent to Google; no Google login is required on the client device.
A public web endpoint still requires organizational authorization and
production-grade perimeter controls before hosting regulated client data.
"""
from __future__ import annotations

import hashlib
import hmac
import threading
import time


MIN_PASSWORD_LENGTH = 20
MAX_FAILURES = 8
LOCK_SECONDS = 15 * 60


def credentials_valid(username: str, password: str) -> bool:
    """Refuse placeholder / weak / unset server-side credentials."""
    return bool(
        isinstance(username, str)
        and username.strip()
        and isinstance(password, str)
        and len(password) >= MIN_PASSWORD_LENGTH
        and username.strip().lower() not in {"admin", "username", "user"}
        and password not in {"YOUR_PASSWORD", "CHANGE_ME"}
    )


def verify_credentials(candidate_user: str, candidate_pass: str,
                       expected_user: str, expected_pass: str) -> bool:
    """Check both fields without interpolating passwords into logs or HTML."""
    if not credentials_valid(expected_user, expected_pass):
        return False
    a = str(candidate_user or "").strip().encode("utf-8")
    b = expected_user.strip().encode("utf-8")
    c = str(candidate_pass or "").encode("utf-8")
    d = expected_pass.encode("utf-8")
    return bool(hmac.compare_digest(a, b) & hmac.compare_digest(c, d))


def session_tag(username: str, password: str) -> str:
    """Invalidate live sessions when configured credentials are rotated."""
    return hashlib.sha256((username + "\x00" + password).encode()).hexdigest()


class AttemptLimiter:
    """Per-app-process throttle; complement with provider/WAF rate limiting."""
    def __init__(self):
        self.lock = threading.Lock()
        self.failures = 0
        self.locked_until = 0.0

    def blocked(self) -> int:
        with self.lock:
            remaining = self.locked_until - time.monotonic()
            return max(0, int(remaining) + (1 if remaining > int(remaining) else 0))

    def record(self, succeeded: bool) -> None:
        with self.lock:
            if succeeded:
                self.failures = 0
                self.locked_until = 0
                return
            self.failures += 1
            if self.failures >= MAX_FAILURES:
                self.failures = 0
                self.locked_until = time.monotonic() + LOCK_SECONDS


def gate(config: dict) -> None:
    """Stop the Streamlit script BEFORE any Google Sheets read or report UI."""
    import streamlit as st

    username = config.get("username")
    password = config.get("password")
    if not credentials_valid(username, password):
        st.error("🔒 網站尚未設定有效的專用帳號與高強度密碼，所有資料存取已停用。")
        st.caption("請在 Streamlit App settings → Secrets 設定 [site_login] username 和 20 字元以上獨立密碼。")
        st.stop()

    fingerprint = session_tag(username, password)
    if st.session_state.get("fcn_authorized_session") == fingerprint:
        return
    # Never preserve a prior session if the configured secret changes.
    st.session_state.pop("fcn_authorized_session", None)

    @st.cache_resource
    def attempt_limiter() -> AttemptLimiter:
        return AttemptLimiter()

    limiter = attempt_limiter()
    st.title("🔒 FCN Portfolio Pro｜專屬登入")
    st.caption("銀行 Edge 可使用｜無需 Google 登入｜未登入不會讀取 Google Sheets")
    remaining = limiter.blocked()
    if remaining:
        st.error(f"密碼嘗試次數過多，請約 {max(1, (remaining + 59) // 60)} 分鐘後再試。")
        st.stop()

    with st.form("fcn_login_form", clear_on_submit=True):
        entered_user = st.text_input("專用帳號")
        entered_pass = st.text_input("專用密碼", type="password")
        submitted = st.form_submit_button("登入 FCN Portfolio Pro", type="primary", use_container_width=True)

    if submitted:
        passed = verify_credentials(entered_user, entered_pass, username, password)
        limiter.record(passed)
        if passed:
            st.session_state["fcn_authorized_session"] = fingerprint
            st.rerun()
        else:
            st.error("帳號或密碼不正確，請重新確認。")
    st.info("網站僅限授權本人使用；不論是否知道網址，未登入都不能查看資料或操作商品。")
    st.stop()


def logout() -> None:
    """Remove authorization for this Streamlit browser session."""
    import streamlit as st
    st.session_state.pop("fcn_authorized_session", None)
    st.rerun()

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
    from warm_theme import login_intro
    login_intro()
    st.caption("使用 6 位數字 PIN，開啟你的投資工作台。")
    if mode == "demo":
        st.info("目前為虛構資料展示模式。")
    elif mode == "diagnostic":
        st.info("登入後只檢查試算表欄位，不顯示投資資料。")
    else:
        st.caption("連線至私人 Google Sheets：資料由網站伺服器唯讀取得。")

    remaining = limit.blocked()
    if remaining:
        st.error(f"輸入錯誤次數過多，請約 {max(1, (remaining + 59) // 60)} 分鐘後再試。")
        st.stop()

    with st.form("fcn_pin_login", clear_on_submit=True):
        st.markdown("### 歡迎回來")
        st.caption("請輸入你的登入 PIN")
        candidate = st.text_input(
            "6 位數字 PIN", type="password", max_chars=6,
            placeholder="請輸入 6 位數字"
        )
        submitted = st.form_submit_button("進入投資工作台", type="primary", use_container_width=True)

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


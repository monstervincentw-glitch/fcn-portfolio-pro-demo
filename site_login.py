"""Six-digit PIN gate for a fictional-data-only FCN Portfolio Pro demo.

This is a UX demonstration, NOT an authorization mechanism for client/financial
records. Any non-demo mode fails closed. No credentials are stored in GitHub.
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


def pin_valid(pin: object) -> bool:
    """Keep leading zeros intact: the secret must be a quoted TOML string."""
    return isinstance(pin, str) and bool(PIN_PATTERN.fullmatch(pin))


def pin_matches(candidate: str, expected: str) -> bool:
    return pin_valid(expected) and bool(
        PIN_PATTERN.fullmatch(str(candidate or ""))
        and hmac.compare_digest(str(candidate), expected)
    )


def session_tag(pin: str) -> str:
    """Change of PIN invalidates earlier session-state authorization."""
    return hashlib.sha256(("fcn-demo-pin-v1:\x00" + pin).encode("utf-8")).hexdigest()


class AttemptLimiter:
    """Best-effort per-process throttle (not distributed or bank-grade)."""
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.failures = 0
        self.locked_until = 0.0

    def blocked(self) -> int:
        with self.lock:
            remaining = self.locked_until - time.monotonic()
            return max(0, int(remaining) + (remaining > int(remaining)))

    def record(self, succeeded: bool) -> None:
        with self.lock:
            if succeeded:
                self.failures = 0
                self.locked_until = 0.0
                return
            self.failures += 1
            if self.failures >= MAX_FAILURES:
                self.failures = 0
                self.locked_until = time.monotonic() + LOCK_SECONDS


def gate(config: dict, app_mode: str = "demo") -> None:
    """Stop before any Sheets calls; PIN-only access is permitted for DEMO only."""
    import streamlit as st

    if str(app_mode).strip().lower() != "demo":
        st.error("🔒 六位數 PIN 僅提供虛構資料 DEMO 測試。正式資料與 Google Sheets 連線模式已停用；需先配置更強的身分驗證。")
        st.stop()

    pin = config.get("pin")
    if not pin_valid(pin):
        st.error("🔒 請先在 Streamlit Secrets 的 [site_login] 設定 pin = \"六位數字\"。")
        st.caption("請將 PIN 寫在 Streamlit Secrets，不要放進公開 GitHub 或聊天。")
        st.stop()

    fingerprint = session_tag(pin)
    if st.session_state.get("fcn_authorized_session") == fingerprint:
        return
    st.session_state.pop("fcn_authorized_session", None)

    @st.cache_resource
    def limiter() -> AttemptLimiter:
        return AttemptLimiter()

    limit = limiter()
    st.title("🔒 FCN Portfolio Pro｜PIN 登入")
    st.caption("銀行 Edge 可使用｜免 Google 登入｜虛構資料 DEMO")
    st.warning("6 位數 PIN 僅適用 DEMO 測試；真實客戶資料尚未開放。")
    remaining = limit.blocked()
    if remaining:
        st.error(f"嘗試次數過多，請約 {max(1, (remaining + 59) // 60)} 分鐘後再試。")
        st.stop()

    with st.form("fcn_pin_login", clear_on_submit=True):
        candidate = st.text_input("6 位數字 PIN", type="password", max_chars=6,
                                  placeholder="請輸入 6 位數字")
        submitted = st.form_submit_button("登入 FCN Portfolio Pro", type="primary", use_container_width=True)

    if submitted:
        passed = pin_matches(candidate, pin)
        limit.record(passed)
        if passed:
            st.session_state["fcn_authorized_session"] = fingerprint
            st.rerun()
        else:
            st.error("PIN 不正確，請重新輸入。")
    st.stop()


def logout() -> None:
    import streamlit as st
    st.session_state.pop("fcn_authorized_session", None)
    st.rerun()

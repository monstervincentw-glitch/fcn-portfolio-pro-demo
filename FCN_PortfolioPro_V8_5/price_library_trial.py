"""Production FCN personal historical trial: read-only Google Sheets stock library.

No client/portfolio rows, write permissions, dynamic pricing, or invented prices.
This page runs behind the existing Streamlit PIN gate. No credentials in source.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta

from sheets_backend import SheetsReader, SheetConnectionError
from historical_trial_engine import TrialInputs, TrialDataError, parse_symbols, simulate_history

# A spreadsheet ID is only a locator, not a credential. Access remains restricted
# by sharing the workbook Viewer with the existing gcp_service_account.
PRICE_LIBRARY_ID = "1ef0Whr7-bgj37DdOnC7ug8Dyv5Ab92-AMw5n9V18UJY"
PRICE_TAB = "收盤價矩陣"
DATE_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}\Z")

class PriceLibraryError(ValueError):
    """Recoverable data/connection failure; safe to display to signed-in users."""

@dataclass(frozen=True)
class PriceProvenance:
    first: dt.date
    last: dt.date
    ticker_count: int
    joint_days: int
    provider: str = "Google Sheets / GOOGLEFINANCE 歷史收盤價（已固定儲存）"
    adjustment: str = "拆股與股息調整口徑尚待逐檔核實"


def sheet_column(zero_index: int) -> str:
    if not isinstance(zero_index, int) or zero_index < 0:
        raise ValueError("Invalid column index")
    out = ""
    i = zero_index + 1
    while i:
        i, d = divmod(i - 1, 26)
        out = chr(65 + d) + out
    return out


def parse_prices(
    symbols: tuple[str, ...], headers: list[Any],
    date_rows: list[list[Any]], stock_columns: list[list[list[Any]]],
    start: dt.date, end: dt.date,
) -> tuple[pd.DataFrame, PriceProvenance]:
    """Parse sparse one-column Sheets API ranges without filling blanks.

    Row alignment is kept by the Sheets API for internal blank rows. Ranges
    start on row 2; trailing blank rows may be omitted but are never shifted.
    """
    symbols = tuple(str(s).strip().upper() for s in symbols)
    if not 1 <= len(symbols) <= 5 or len(set(symbols)) != len(symbols):
        raise PriceLibraryError("請輸入 1～5 檔不重複股票。")
    labels = [str(s).strip().upper() for s in headers]
    if not labels or labels[0] != "交易日期":
        raise PriceLibraryError("股價庫表頭格式不符，找不到交易日期。")
    if len(labels) != len(set(labels)):
        raise PriceLibraryError("股價庫表頭重複，避免錯配已停止。")
    missing = [s for s in symbols if s not in labels]
    if missing:
        raise PriceLibraryError("股價庫尚未收錄：" + "、".join(missing))
    if len(stock_columns) != len(symbols):
        raise PriceLibraryError("股價欄位回傳數量不符。")
    seen_dates: set[dt.date] = set()
    records: list[dict] = []
    for i, date_cell in enumerate(date_rows):
        if not date_cell or date_cell[0] in (None, ""):
            continue
        raw = str(date_cell[0]).strip()
        if not DATE_FORMAT.fullmatch(raw):
            raise PriceLibraryError(f"股價庫第 {i+2} 列日期不是 YYYY-MM-DD。")
        try:
            trading_day = dt.date.fromisoformat(raw)
        except ValueError:
            raise PriceLibraryError(f"股價庫第 {i+2} 列日期無效。") from None
        if trading_day in seen_dates:
            raise PriceLibraryError(f"股價庫重複交易日 {trading_day}，已停止。")
        seen_dates.add(trading_day)
        if not start <= trading_day <= end:
            continue
        for symbol, col in zip(symbols, stock_columns):
            if i >= len(col) or not col[i] or col[i][0] in (None, ""):
                continue
            try:
                close = float(col[i][0])
            except (TypeError, ValueError, OverflowError):
                raise PriceLibraryError(f"{symbol} {trading_day} 收盤價格式錯誤。") from None
            if not math.isfinite(close) or close <= 0:
                raise PriceLibraryError(f"{symbol} {trading_day} 收盤價無效。")
            records.append({"date": pd.Timestamp(trading_day), "stock": symbol, "ratio": close})
    if not records:
        raise PriceLibraryError("指定日期範圍內找不到真實歷史收盤價。")
    frame = pd.DataFrame.from_records(records).sort_values(["date", "stock"]).reset_index(drop=True)
    panel = frame.pivot(index="date", columns="stock", values="ratio")
    if any(s not in panel.columns for s in symbols):
        raise PriceLibraryError("部分股票在指定日期範圍內完全沒有股價，不能試算。")
    common = panel[list(symbols)].dropna()
    if len(common) < 2:
        raise PriceLibraryError("全部連結股票共同有效交易日不足兩日，不能試算。")
    return frame, PriceProvenance(
        first=frame.date.min().date(), last=frame.date.max().date(),
        ticker_count=len(symbols), joint_days=len(common)
    )


def fetch_library_prices(
    symbols: tuple[str, ...], start: dt.date, end: dt.date,
    service_account: dict[str, Any], *, sheet_id: str = PRICE_LIBRARY_ID,
) -> tuple[pd.DataFrame, PriceProvenance]:
    if not service_account:
        raise PriceLibraryError("正式版 Secrets 尚未設定 [gcp_service_account]。")
    if not isinstance(start, dt.date) or not isinstance(end, dt.date) or start > end:
        raise PriceLibraryError("行情查詢日期範圍錯誤。")
    try:
        reader = SheetsReader.from_secrets(service_account, sheet_id)
        # Actual matrix has 527 occupied columns and 530 columns allocated.
        # Column TJ is the last of current grid; do not exceed grid limits.
        top = reader.read(sheet_id, f"'{PRICE_TAB}'!A1:TJ1")
        if not top:
            raise PriceLibraryError("股價庫尚未建立收盤價矩陣表頭。")
        header = top[0]
        upper = [str(x).strip().upper() for x in header]
        absent = [x for x in symbols if x not in upper]
        if absent:
            raise PriceLibraryError("股價庫尚無以下股票的收盤價欄位：" + "、".join(absent))
        # Unbounded lower ranges remain valid when the daily update adds rows.
        ranges = [f"'{PRICE_TAB}'!A2:A"]
        ranges.extend(f"'{PRICE_TAB}'!{sheet_column(upper.index(s))}2:{sheet_column(upper.index(s))}" for s in symbols)
        cells = reader.read_many(ranges)
        if len(cells) != 1 + len(symbols):
            raise PriceLibraryError("股價庫查詢回傳的欄位數量異常。")
        return parse_prices(symbols, header, cells[0], cells[1:], start, end)
    except SheetConnectionError as e:
        # Avoid showing account credentials or URLs in exception text.
        raise PriceLibraryError("讀取股價庫遭拒或失敗。請確認新股價庫已分享給正式站服務帳號（檢視者），且 Sheets API 可用。") from None


def latest_available_day(service_account: dict[str, Any]) -> dt.date:
    """Read latest persisted trading day instead of showing a frozen hardcoded date."""
    if not service_account:
        raise PriceLibraryError("無股價庫憑證。")
    reader = SheetsReader.from_secrets(service_account, PRICE_LIBRARY_ID)
    cells = reader.read(PRICE_LIBRARY_ID, f"'{PRICE_TAB}'!A2:A")
    parsed = []
    for cell in cells:
        if cell:
            try:
                parsed.append(dt.date.fromisoformat(str(cell[0]).strip()))
            except ValueError:
                raise PriceLibraryError("股價庫交易日期格式錯誤。") from None
    if not parsed:
        raise PriceLibraryError("股價庫無交易日期。")
    if parsed != sorted(set(parsed)):
        raise PriceLibraryError("股價庫交易日期重複或亂序。")
    return parsed[-1]


def verify_explicit_pricing_date(frame: pd.DataFrame, symbols: tuple[str, ...], day: dt.date) -> None:
    subset = frame.loc[frame["date"].dt.date == day]
    if set(subset["stock"].tolist()) != set(symbols):
        raise PriceLibraryError(
            f"{day.isoformat()} 缺少一檔或多檔股票的真實收盤價；指定日期不會自動改成其他日期。"
        )


def _secret_section(name: str) -> dict[str, Any]:
    try:
        return dict(st.secrets.get(name, {}))
    except Exception:
        return {}


def render_trial() -> None:
    st.subheader("🧪 FCN 自由試打｜真實美股歷史股價")
    st.caption("個人歷史情境研究 · 優先從獨立 Google Sheets 股價庫讀取已儲存收盤價；不呼叫 Massive、不修改任何試算表。")
    svc = _secret_section("gcp_service_account")
    if svc:
        try:
            latest = latest_available_day(svc)
            st.info(f"股價庫最早從 2024/01/02 開始；目前最新成功匯入的交易日：{latest.isoformat()}。若未更新，請檢查 GitHub Actions 的股價更新作業。")
        except (PriceLibraryError, SheetConnectionError):
            st.warning("目前無法確認股價庫最後交易日，請檢查股價庫的分享權限及排程狀態。")
    else:
        st.warning("股價庫尚未連線，請檢查 [gcp_service_account] Secrets。")
    if st.button("🔎 先檢查股價庫讀取權限"):
        try:
            reader = SheetsReader.from_secrets(svc, PRICE_LIBRARY_ID)
            r = reader.read(PRICE_LIBRARY_ID, f"'{PRICE_TAB}'!A1:C3")
            if r and len(r) > 1 and str(r[0][0]).strip() == "交易日期":
                st.success("正式網站可讀取股價庫，已有真實收盤價欄位與交易日。")
            else:
                st.warning("讀取成功，但股價庫表頭或內容異常。")
        except (SheetConnectionError, PriceLibraryError):
            st.error("尚無法讀取新股價庫：請將股價庫以「檢視者」分享給正式版 [gcp_service_account] 的 client_email。")

    with st.form("fcn_main_price_library_trial"):
        left, right = st.columns(2)
        with left:
            ticker_input = st.text_input("美股標的（1～5 檔）", value="NVDA,AMD,MU")
            start_mode = st.radio("期初模式", ["指定期初定價日", "選擇月份首個共同交易日"])
            if start_mode.startswith("指定"):
                selected_day = st.date_input("期初定價日", value=dt.date(2026, 5, 18), format="YYYY/MM/DD")
                selected_month = None
            else:
                selected_day = None
                selected_month = st.text_input("期初月份 YYYY-MM", value="2026-05")
        with right:
            tenor = st.number_input("合約月數", 1, 12, 3, 1)
            lock = st.number_input("閉鎖月數", 0, 11, 1, 1)
            coupon = st.number_input("年化票息（%）", 0.0, 100.0, 20.0, 0.1)
            principal = st.number_input("假設本金（USD）", min_value=1.0, value=100000.0, step=10000.0)
        with st.expander("進階 V2 條款：KO／Strike／KI"):
            c1, c2, c3, c4 = st.columns(4)
            ko = c1.number_input("KO (%)", 1.0, 300.0, 100.0)
            strike = c2.number_input("Strike (%)", 1.0, 200.0, 75.0)
            ki_mode = c3.selectbox("KI 類型", ["EKI", "AKI", "Non-KI"])
            ki = c4.number_input("KI (%)", 1.0, 200.0, 65.0)
        submitted = st.form_submit_button("讀取 Google Sheets 真實收盤價並試打", type="primary", use_container_width=True)

    if submitted:
        st.session_state.pop("official_price_trial", None)
        try:
            symbols = parse_symbols(ticker_input)
            if selected_day is not None:
                chosen = selected_day
            else:
                if not re.fullmatch(r"\d{4}-(0?[1-9]|1[0-2])", str(selected_month or "")):
                    raise TrialDataError("月份請填 YYYY-MM。")
                yyyy, mm = map(int, selected_month.split("-"))
                chosen = dt.date(yyyy, mm, 1)
            today = dt.date.today()
            if chosen < dt.date(2024, 1, 1):
                raise PriceLibraryError("股價庫從 2024 年開始，無法試打更早日期。")
            if chosen > today:
                raise PriceLibraryError("不能選擇未來日期。")
            params = TrialInputs(symbols, chosen, int(tenor), int(lock), float(coupon),
                                 float(principal), float(ko), float(strike),
                                 float(ki) if ki_mode != "Non-KI" else None, ki_mode)
            params.validate()
            until = min(today, chosen + dt.timedelta(days=9) + relativedelta(months=int(tenor), days=14))
            with st.spinner("讀取真實歷史日收盤價，執行 V2 試算中…"):
                frame, provenance = fetch_library_prices(symbols, chosen, until, svc)
                if selected_day is not None:
                    verify_explicit_pricing_date(frame, symbols, chosen)
                trial = simulate_history(frame, params, as_of=today)
                st.session_state["official_price_trial"] = (trial, params, provenance)
        except (PriceLibraryError, TrialDataError, ValueError) as e:
            st.warning(str(e))

    if "official_price_trial" not in st.session_state:
        return
    trial, params, provenance = st.session_state["official_price_trial"]
    st.subheader("歷史情境試算結果")
    st.caption(f"來源：{provenance.provider}｜共同交易日：{provenance.joint_days}｜實際資料末日：{provenance.last}｜{provenance.adjustment}")
    if trial["scheduled_maturity"] > provenance.last:
        st.warning("歷史行情尚未涵蓋預定期末，不能預設本金或未來價格。")
    if trial["scheduled_maturity"] <= dt.date.today() and trial["principal_return_pct"] is None:
        st.warning("預定期末已過，但缺少足以判定回收的完整行情；不產生假設結算。")
    a, b, c = st.columns(3)
    a.metric("模型可估票息", f"{trial['coupon_pct']:.4f}%")
    b.metric("模型本金回收", "尚不可判定" if trial["principal_return_pct"] is None else f"{trial['principal_return_pct']:.2f}%")
    c.metric("模型總損益率", "尚不可判定" if trial["total_return_pct"] is None else f"{trial['total_return_pct']:.4f}%")
    if trial["total_profit_amount"] is not None:
        st.metric("模型淨損益（USD）", f"USD {trial['total_profit_amount']:,.2f}")
    st.caption(f"期初：{trial['pricing_date']}｜模型起息：{trial['estimated_issue_date']}｜預定期末：{trial['scheduled_maturity']}｜KO：{trial['ko_date'] or '未發生／尚無法判定'}")
    chart = trial["chart"]
    base = alt.Chart(chart).encode(x=alt.X("date:T", title="日期"), y=alt.Y("ratio:Q", title="相對期初股價（%）", scale=alt.Scale(zero=False)))
    curve = base.mark_line(strokeWidth=2.4).encode(color=alt.Color("stock:N", title="股票"), tooltip=[alt.Tooltip("date:T", title="日期"), "stock:N", alt.Tooltip("ratio:Q", title="期初比價", format=".2f")])
    levels = [{"level": params.ko_pct, "label": "KO"}, {"level": params.strike_pct, "label": "Strike"}]
    if params.ki_type != "Non-KI" and params.ki_pct is not None:
        levels.append({"level": params.ki_pct, "label": "KI"})
    bands = alt.Chart(pd.DataFrame(levels)).mark_rule(strokeDash=[5, 4]).encode(y="level:Q", color=alt.Color("label:N", title="門檻"))
    obs = alt.Chart(pd.DataFrame({"date": [pd.Timestamp(trial["ko_start"])]})).mark_rule(strokeDash=[2, 4]).encode(x="date:T")
    st.altair_chart((curve + bands + obs).resolve_scale(color="independent").properties(height=360).interactive(), use_container_width=True)
    st.subheader("V2 模型配息期間明細")
    st.dataframe(pd.DataFrame(trial["coupon_steps"]), hide_index=True, use_container_width=True)
    st.caption("本工具僅為個人歷史情境研究，不代表實際金融商品、銀行結算或可成交報價。")

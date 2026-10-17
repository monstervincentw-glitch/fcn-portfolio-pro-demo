"""Independent US equity daily-close provider for FCN scenario trials.

No Google Sheets, portfolios, customer data, credentials on disk, or writes.
Provider: Massive (formerly Polygon.io), REST custom aggregated daily bars.
The return values are vendor split-adjusted historical daily closing prices,
NOT tick-by-tick real-time quotes or contractual corporate-action adjustments.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from urllib.parse import quote
import re

import pandas as pd
import requests

API_ORIGIN = "https://api.massive.com"
SYMBOL_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,20}\Z")


class MarketFeedError(ValueError):
    """A friendly, deliberately credential-free market-feed error."""


@dataclass(frozen=True)
class MarketQuoteMeta:
    provider: str
    adjustment: str
    first_date: date
    last_date: date
    symbol_count: int
    observed_common_days: int
    freshness: str


def _symbols(symbols: tuple[str, ...]) -> tuple[str, ...]:
    out = tuple(str(x).strip().upper() for x in symbols)
    if not 1 <= len(out) <= 5 or len(set(out)) != len(out) or any(not SYMBOL_PATTERN.fullmatch(x) for x in out):
        raise MarketFeedError("請輸入 1～5 檔不重複的有效美股代號，例如 NVDA, AMD, MU。")
    return out


def _rows(payload: object, symbol: str, start: date, end: date) -> list[dict]:
    if not isinstance(payload, dict):
        raise MarketFeedError(f"{symbol} 的行情格式異常，請稍後重試。")
    if payload.get("status") == "ERROR" or payload.get("error"):
        raise MarketFeedError(f"{symbol} 行情服務回報錯誤；請確認代號與訂閱權限。")
    items = payload.get("results")
    if not isinstance(items, list) or not items:
        raise MarketFeedError(f"{symbol} 在指定區間沒有有效歷史收盤價，可能是代號、上市時間或方案限制。")
    output = []
    for item in items:
        try:
            timestamp = int(item["t"])
            close = float(item["c"])
            if timestamp <= 0 or not isfinite(close) or close <= 0:
                continue
            # Aggregate bars are timestamped in UTC, with session date in US/Eastern.
            session_date = pd.Timestamp(timestamp, unit="ms", tz="UTC").tz_convert("America/New_York").date()
            if start <= session_date <= end:
                output.append({"date": pd.Timestamp(session_date), "stock": symbol, "ratio": close})
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    if not output:
        raise MarketFeedError(f"{symbol} 無有效每日收盤價，請修改日期範圍或確認行情權限。")
    d = pd.DataFrame(output)
    if d.duplicated(["date", "stock"]).any():
        raise MarketFeedError(f"{symbol} 行情包含重複交易日，為避免 KO 誤判已停止。")
    return output


def fetch_daily_closes(
    symbols: tuple[str, ...], start: date, end: date, api_key: str,
    *, http: object | None = None,
) -> tuple[pd.DataFrame, MarketQuoteMeta]:
    """Fetch 1..5 tickers afresh on submission; fail closed on invalid/missing data.

    Historical end-of-day bars, split adjusted for chart continuity.
    `http` is injectable for deterministic, no-network unit tests.
    """
    symbols = _symbols(symbols)
    if not isinstance(start, date) or not isinstance(end, date) or start > end:
        raise MarketFeedError("期初日期及查詢截止日不正確。")
    if (end - start).days > 550:
        raise MarketFeedError("單次試打限查詢約 18 個月的每日行情，請縮短期間。")
    if not isinstance(api_key, str) or not api_key.strip():
        raise MarketFeedError("尚未設定外部行情 API Key；需在測試站的 Secrets 設定 [market_data] api_key。")
    http = http if http is not None else requests.Session()
    records = []
    for symbol in symbols:
        url = f"{API_ORIGIN}/v2/aggs/ticker/{quote(symbol, safe='')}/range/1/day/{start.isoformat()}/{end.isoformat()}"
        try:
            response = http.get(
                url,
                params={"adjusted": "true", "sort": "asc", "limit": 50000},
                headers={"Authorization": f"Bearer {api_key.strip()}"},
                timeout=(5, 18),
            )
        except requests.RequestException:
            raise MarketFeedError(f"{symbol} 行情連線失敗，請檢查網路與 API 服務狀態。") from None
        if response.status_code in (401, 403):
            raise MarketFeedError("行情 API 無法授權，請檢查訂閱方案及 Secrets（不要提供金鑰）。")
        if response.status_code == 429:
            raise MarketFeedError("行情 API 已達每分鐘呼叫上限，請稍後再試；五檔股票需要五次查詢。")
        if response.status_code >= 400:
            raise MarketFeedError(f"{symbol} 行情 API 暫時無法提供資料（HTTP {response.status_code}）。")
        try:
            records.extend(_rows(response.json(), symbol, start, end))
        except (ValueError, requests.RequestException):
            raise MarketFeedError(f"{symbol} 行情回應內容無法解析。") from None
    frame = pd.DataFrame(records).sort_values(["date", "stock"]).reset_index(drop=True)
    common = frame.pivot(index="date", columns="stock", values="ratio")
    shared = common.dropna().index
    if len(shared) < 2:
        raise MarketFeedError("連結標的只有不到兩個共同有效交易日，無法建立 V2 試打模型。")
    latest = frame.date.max().date()
    meta = MarketQuoteMeta(
        provider="Massive / US equities daily aggregates",
        adjustment="split-adjusted daily close (not intraday quote)",
        first_date=frame.date.min().date(), last_date=latest,
        symbol_count=len(symbols), observed_common_days=len(shared),
        freshness="歷史每日收盤資料（非交易所即時成交價）",
    )
    return frame, meta


def verify_pricing_session(frame: pd.DataFrame, chosen: date, symbols: tuple[str, ...]) -> None:
    """Explicit date MUST be a trading session with prices for every chosen ticker.

    The pre-existing V2 simulator's `start_month` also accepts a date within
    the month. We pass this exact date and independently prohibit quiet roll-forward.
    """
    symbols = _symbols(symbols)
    at = frame.loc[frame.date.dt.date == chosen]
    present = set(at.stock.astype(str).str.upper())
    if present != set(symbols):
        raise MarketFeedError(
            f"{chosen.isoformat()} 沒有全部標的的完整收盤行情（週末、休市或個別停牌）；"
            "指定日期模式不會自動替換日期，請另選交易日。"
        )

"""Read-only, single-Google-Sheets FCN product catalog and price history.

This module reads only the user's central Google workbook with the EXISTING
server-side SheetsReader. It does not call GOOGLEFINANCE, Yahoo, or FCN-by-FCN
workbooks, and it does not access customer holdings.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from math import isfinite
from typing import Any

TAIPEI = dt.timezone(dt.timedelta(hours=8))

def _today_taipei() -> dt.date:
    return dt.datetime.now(TAIPEI).date()

CENTRAL_CATALOG_ID = "1peKhu1Nt8UuCiCnajGqC9bT_GXyL3qCzQBO3z-VzzOI"
PRODUCT_RANGE = "'API_商品條款_V1'!A1:X101"
LEGS_RANGE = "'API_標的_V1'!A1:M501"
PRICE_HEADER_RANGE = "'歷史行情_核心'!A1:AZ1"
PRICE_DATE_RANGE = "'歷史行情_核心'!A2:A850"
REQUIRED_PRODUCTS = {
    "product_id", "currency", "pricing_date", "annual_coupon_rate",
    "contract_review_state", "website_visible",
}
REQUIRED_LEGS = {
    "product_id", "leg_no", "ticker", "initial_price",
    "ko_price", "ki_price", "strike_price", "quote_review",
}


class CatalogSchemaError(ValueError):
    """A changed central Google Sheet schema: fail closed, never guess columns."""


@dataclass(frozen=True)
class Catalog:
    products: dict[str, dict[str, Any]]
    legs: dict[str, tuple[dict[str, Any], ...]]


def parse_table(values: list[list[Any]], required: set[str]) -> list[dict[str, Any]]:
    if not values:
        raise CatalogSchemaError("中央庫沒有回傳表頭")
    header = [str(x or "").strip() for x in values[0]]
    if len(set(h for h in header if h)) != len([h for h in header if h]):
        raise CatalogSchemaError("中央庫出現重複的欄位名稱")
    if not required.issubset(header):
        raise CatalogSchemaError("中央庫欄位不完整：" + ", ".join(sorted(required - set(header))))
    parsed = []
    for row in values[1:]:
        padded = list(row) + [None] * (len(header) - len(row))
        item = {h: padded[i] for i, h in enumerate(header) if h}
        if str(item.get("product_id") or "").strip():
            parsed.append(item)
    return parsed


def parse_catalog(products_values: list[list], legs_values: list[list]) -> Catalog:
    products = parse_table(products_values, REQUIRED_PRODUCTS)
    legs = parse_table(legs_values, REQUIRED_LEGS)
    by_product: dict[str, dict[str, Any]] = {}
    for product in products:
        pid = str(product["product_id"]).strip()
        if pid in by_product:
            raise CatalogSchemaError("商品代號重複，請檢查中央庫")
        by_product[pid] = product
    by_leg: dict[str, list[dict[str, Any]]] = {pid: [] for pid in by_product}
    seen = set()
    for leg in legs:
        pid = str(leg["product_id"]).strip()
        if pid not in by_product:  # Ignore orphan rows; never silently create products.
            continue
        symbol = str(leg.get("ticker") or "").strip().upper()
        if not symbol:
            continue
        try:
            leg_no = int(leg.get("leg_no"))
        except (TypeError, ValueError, OverflowError):
            raise CatalogSchemaError("有連結標的缺少有效序號") from None
        if leg_no not in (1, 2, 3, 4, 5) or (pid, leg_no) in seen:
            raise CatalogSchemaError("連結標的序號重複或超出 1～5")
        seen.add((pid, leg_no))
        by_leg[pid].append({**leg, "ticker": symbol, "leg_no": leg_no})
    return Catalog(by_product, {pid: tuple(sorted(v, key=lambda x: x["leg_no"]))
                               for pid, v in by_leg.items()})


def load_catalog(reader: Any, sheet_id: str = CENTRAL_CATALOG_ID) -> Catalog:
    """reader is the already-authorized, PIN-gated SheetsReader."""
    return parse_catalog(reader.read(sheet_id, PRODUCT_RANGE),
                         reader.read(sheet_id, LEGS_RANGE))


def sheet_column(index: int) -> str:
    if index < 0:
        raise ValueError("negative column")
    index += 1
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def to_day(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 20000 < value < 110000:
            return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(value))).date()
        return None
    if isinstance(value, str) and value.strip():
        try:
            return dt.date.fromisoformat(value.strip()[:10].replace("/", "-"))
        except ValueError:
            return None
    return None


def as_positive_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        x = float(str(value).replace(",", "").strip())
        return x if isfinite(x) and x > 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def load_history(reader: Any, tickers: list[str],
                 sheet_id: str = CENTRAL_CATALOG_ID) -> tuple[list[dict], list[str]]:
    """Get real dated close values from internal history only. Missing stays missing."""
    symbols = list(dict.fromkeys(str(t).strip().upper() for t in tickers if t))
    if not symbols:
        return [], []
    header_rows = reader.read(sheet_id, PRICE_HEADER_RANGE)
    if not header_rows:
        raise CatalogSchemaError("歷史行情資料表沒有標題列")
    headers = [str(h or "").strip().upper() for h in header_rows[0]]
    if not headers or headers[0] not in ("日期", "交易日期"):
        raise CatalogSchemaError("歷史行情日期欄不符合預期")
    dates = reader.read(sheet_id, PRICE_DATE_RANGE)
    columns: dict[str, list[list]] = {}
    missing = []
    for ticker in symbols:
        if ticker not in headers:
            missing.append(ticker)
            continue
        pos = headers.index(ticker)
        if pos == 0:
            missing.append(ticker)
            continue
        c = sheet_column(pos)
        columns[ticker] = reader.read(sheet_id, f"'歷史行情_核心'!{c}2:{c}850")
    points = []
    today = _today_taipei()
    for i, raw_date in enumerate(dates):
        day = to_day(raw_date[0] if raw_date else None)
        if day is None or day > today:
            continue
        for symbol, col in columns.items():
            val = col[i][0] if i < len(col) and col[i] else None
            price = as_positive_number(val)
            if price is not None:
                points.append({"date": day, "stock": symbol, "close": price})
    return points, missing


def verified_for_barriers(product: dict, legs: tuple[dict, ...],
                          latest_date: dt.date | None,
                          today: dt.date | None = None) -> bool:
    """Block KO/KI risk views unless actual data and contract review are verified."""
    today = today or _today_taipei()
    if not legs or latest_date is None or (today - latest_date).days > 4:
        return False
    if str(product.get("contract_review_state") or "").strip() != "已核實":
        return False
    if str(product.get("website_visible") or "").strip() != "是":
        return False
    if str(product.get("ko_type") or "").strip() not in ("記憶式", "非記憶式"):
        return False
    if str(product.get("ki_type") or "").strip() not in ("AKI", "EKI", "Non-KI"):
        return False
    for leg in legs:
        if str(leg.get("quote_review") or "").strip() != "已核對":
            return False
        if as_positive_number(leg.get("initial_price")) is None:
            return False
    return True


def history_as_relative(points: list[dict], legs: tuple[dict, ...],
                        product: dict) -> list[dict]:
    """Convert to percentages of contractual initial price; only caller may verify."""
    initial = {l["ticker"]: as_positive_number(l.get("initial_price")) for l in legs}
    begin, finish = to_day(product.get("pricing_date")), to_day(product.get("final_eval_date"))
    out = []
    for point in points:
        d = point["date"]
        if (begin and d < begin) or (finish and d > finish):
            continue
        start = initial.get(point["stock"])
        if start:
            out.append({"date": d, "stock": point["stock"],
                        "ratio": point["close"] / start * 100})
    return out


def barriers_for_chart(product: dict) -> dict[str, float | dt.date | None]:
    def pct(key: str) -> float | None:
        v = as_positive_number(product.get(key))
        return v * 100 if v is not None and 0 < v <= 2 else None
    ki_type = str(product.get("ki_type") or "")
    return {
        "ko": pct("ko_barrier_ratio"),
        "strike": pct("strike_ratio"),
        "ki": None if ki_type == "Non-KI" else pct("ki_barrier_ratio"),
        "ko_start": to_day(product.get("ko_start_date")),
    }

"""Daily incremental EOD price updater for FCN's independent Google Sheets library.

This is NOT part of Streamlit; GitHub Actions owns this write-only workflow.
Only the dedicated PRICE_LIBRARY_ID is written. Source: GOOGLEFINANCE historic
close, the same source as existing stored matrix values. A missing price stays
blank. Scripts may fail closed if GOOGLEFINANCE data is late/unavailable.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

PRICE_LIBRARY_ID = "1ef0Whr7-bgj37DdOnC7ug8Dyv5Ab92-AMw5n9V18UJY"
PRICE_TAB = "收盤價矩陣"
STAGING_TAB = "FCN_自動更新暫存"
PROGRESS_TAB = "逐檔匯入進度"
AUDIT_TAB = "更新紀錄"
OVERVIEW_TAB = "行情總覽"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
NY = ZoneInfo("America/New_York")
SYMBOL_RE = re.compile(r"[A-Z0-9.^_-]{1,22}\Z")
MIN_COVERAGE = 0.80  # abort rather than append a largely empty/truncated trading day
BATCH_SIZE = 25
WAIT_SECONDS = 8
MAX_DAYS_PER_RUN = 12


def a1_column(index: int) -> str:
    if index < 0: raise ValueError("Negative column")
    out = ""
    i = index + 1
    while i:
        i, v = divmod(i - 1, 26)
        out = chr(65 + v) + out
    return out


def normalize_trading_date(value: Any) -> dt.date | None:
    if value in (None, ""): return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)): return None
        return (dt.date(1899, 12, 30) + dt.timedelta(days=int(value)))
    if isinstance(value, str):
        try: return dt.date.fromisoformat(value[:10].replace("/", "-"))
        except ValueError: return None
    return None


def valid_close(value: Any) -> float | None:
    if isinstance(value, bool): return None
    try:
        number = float(value)
        if number > 0 and math.isfinite(number):
            return round(number, 8)
    except (ValueError, TypeError, OverflowError):
        pass
    return None


def expected_last_day(now: dt.datetime) -> dt.date:
    ny = now.astimezone(NY)
    # GoogleFinance delayed prices: do not fetch the same day before 20:00 NY.
    return ny.date() if ny.hour >= 20 else ny.date() - dt.timedelta(days=1)


def weekdays_after(last: dt.date, through: dt.date) -> list[dt.date]:
    out = []
    day = last + dt.timedelta(days=1)
    while day <= through:
        if day.weekday() < 5: out.append(day)
        day += dt.timedelta(days=1)
        if len(out) > 300: raise RuntimeError("Too many missed days; manually inspect before updating")
    return out


@dataclass
class SheetAPI:
    session: Any

    @classmethod
    def authorized(cls, info: dict[str, Any]):
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return cls(AuthorizedSession(credentials))

    def request(self, method: str, path: str, *, params=None, payload=None) -> dict:
        url = f"{SHEETS_API}/{PRICE_LIBRARY_ID}" + (path if path.startswith(":") else ("/" + path if path else ""))
        # Explicitly fixed spreadsheet; never accept a destination supplied at runtime.
        for attempt in range(4):
            resp = self.session.request(method, url, params=params, json=payload, timeout=55)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt * 3)
                continue
            if not resp.ok:
                raise RuntimeError(f"Google Sheets API {resp.status_code} ({method} {path.split('/')[0]}); do not publish credentials")
            return resp.json() if resp.content else {}
        raise RuntimeError("Google Sheets API retry exhausted")

    def values(self, a1: str) -> list[list[Any]]:
        encoded = quote(a1, safe="")
        result = self.request("GET", f"values/{encoded}", params={"valueRenderOption": "UNFORMATTED_VALUE"})
        return result.get("values", [])

    def write(self, a1: str, rows: list[list], mode: str = "RAW") -> None:
        encoded = quote(a1, safe="")
        self.request("PUT", f"values/{encoded}", params={"valueInputOption": mode}, payload={"values": rows})

    def clear(self, a1: str) -> None:
        self.request("POST", f"values/{quote(a1,safe='')}:clear", payload={})

    def write_many(self, data: list[tuple[str, list[list]]]):
        self.request("POST", "values:batchUpdate", payload={
            "valueInputOption": "RAW", "data": [
                {"range": range_, "values": values} for range_, values in data
            ]
        })

    def append(self, a1: str, row: list):
        self.request("POST", f"values/{quote(a1,safe='')}:append", params={
            "valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"
        }, payload={"values": [row]})

    def metadata(self) -> dict:
        return self.request("GET", "", params={"fields": "sheets(properties(title,sheetId,gridProperties))"})

    def ensure_grid(self, title: str, min_rows: int, min_cols: int):
        sheets = [x.get("properties", {}) for x in self.metadata().get("sheets", [])]
        s = next((x for x in sheets if x.get("title") == title), None)
        if s is None:
            if title != STAGING_TAB:
                raise RuntimeError("Expected price library worksheet not found")
            self.request("POST", ":batchUpdate", payload={"requests": [{"addSheet": {"properties": {
                "title": STAGING_TAB, "hidden": True, "gridProperties": {
                    "rowCount": max(5, min_rows), "columnCount": max(80, min_cols)
                }
            }}}]})
            return
        props = s.get("gridProperties", {})
        requests = []
        if props.get("rowCount", 0) < min_rows:
            requests.append({"appendDimension": {"sheetId": s["sheetId"], "dimension": "ROWS", "length": min_rows - props["rowCount"]}})
        if props.get("columnCount", 0) < min_cols:
            requests.append({"appendDimension": {"sheetId": s["sheetId"], "dimension": "COLUMNS", "length": min_cols - props["columnCount"]}})
        if requests: self.request("POST", ":batchUpdate", payload={"requests": requests})


def formula(symbol: str, date: dt.date) -> str:
    if not SYMBOL_RE.fullmatch(symbol):
        raise ValueError("Unsupported ticker, refusing formula injection")
    return f'=GOOGLEFINANCE("{symbol}","close",DATE({date.year},{date.month},{date.day}),DATE({date.year},{date.month},{date.day}),"DAILY")'


def extract_quotes(matrix: list[list[Any]], symbols: list[str], date: dt.date) -> dict[str, float]:
    # Each GOOGLEFINANCE formula spills into 2 rows x 2 columns, using a 3-column stride.
    # matrix[0] is header Date/Close; matrix[1] is (numeric date, numeric close).
    if len(matrix) < 2: return {}
    row = matrix[1]
    valid = {}
    for ix, sym in enumerate(symbols):
        pos = ix * 3
        if pos + 1 >= len(row): continue
        found_day = normalize_trading_date(row[pos])
        value = valid_close(row[pos + 1])
        if found_day == date and value is not None:
            valid[sym] = value
    return valid


def get_quotes(api: SheetAPI, day: dt.date, symbols: list[str]) -> dict[str, float]:
    if not symbols: return {}
    columns = len(symbols) * 3
    last = a1_column(columns - 1)
    # Use a scratch worksheet, never paste volatile GOOGLEFINANCE formulas into
    # the permanent historical matrix. Once values arrive, only plain values persist.
    api.clear(f"'{STAGING_TAB}'!A2:{last}4")
    fields = [None] * columns
    for ix, sym in enumerate(symbols):
        fields[ix * 3] = formula(sym, day)
    api.write(f"'{STAGING_TAB}'!A2:{last}2", [fields], mode="USER_ENTERED")
    seen: dict[str, float] = {}
    for _ in range(3):
        time.sleep(WAIT_SECONDS)
        results = api.values(f"'{STAGING_TAB}'!A2:{last}3")
        seen.update(extract_quotes(results, symbols, day))
        if len(seen) == len(symbols): break
    return seen


def check_headings(values: list[list]) -> list[str]:
    if not values or not values[0] or values[0][0] != "交易日期":
        raise RuntimeError("Price matrix header mismatch; aborting")
    syms = [str(x).strip().upper() for x in values[0][1:]]
    if len(syms) < 400 or len(syms) != len(set(syms)) or not all(SYMBOL_RE.fullmatch(x) for x in syms):
        raise RuntimeError("Price universe missing/duplicated/unsafe; aborting")
    return syms


def _int_or_zero(value: Any) -> int:
    try: return int(str(value).replace(",", ""))
    except (ValueError, TypeError): return 0


def update_one_day(api: SheetAPI, day: dt.date, history: list[dt.date], symbols: list[str]) -> bool:
    # Reference ticker avoids adding non-trading weekdays or future fabricated dates.
    anchor = get_quotes(api, day, ["AAPL"])
    if "AAPL" not in anchor:
        print(f"No AAPL close for {day}; holiday OR transient GOOGLEFINANCE error; will retry later")
        raise RuntimeError("Unable to distinguish market closure from API delay; retry on next scheduled run")

    prices: dict[str, float] = {}
    for idx in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[idx:idx+BATCH_SIZE]
        prices.update(get_quotes(api, day, batch))
        print(f"{day}: quotes retrieved {len(prices)} / {len(symbols)}")
    if len(prices) < math.ceil(len(symbols) * MIN_COVERAGE):
        raise RuntimeError(f"Refusing incomplete day {day}: {len(prices)}/{len(symbols)} valid closes")

    # Double-check latest date immediately before writing: other runs could have
    # updated sheet while current job fetched prices. GitHub concurrency also guards.
    current = [normalize_trading_date(row[0]) for row in api.values(f"'{PRICE_TAB}'!A2:A") if row]
    if not current or current != history:
        raise RuntimeError("Matrix dates changed during update; aborting duplicate insert")
    target_row = len(current) + 2
    api.ensure_grid(PRICE_TAB, target_row, len(symbols) + 1)
    matrix_row = [day.isoformat()] + [prices.get(s, "") for s in symbols]
    last_col = a1_column(len(symbols))

    # Update independently named progress and overview cells using preserved data.
    progress = api.values(f"'{PROGRESS_TAB}'!A2:G")
    patched = []
    for existing in progress:
        cells = list(existing) + [""] * (7 - len(existing))
        sym = str(cells[0]).strip().upper()
        if sym in prices:
            cells[2] = _int_or_zero(cells[2]) + 1
            cells[4] = day.isoformat()
            cells[5] = "GOOGLEFINANCE"
        patched.append(cells[:7])
    overview = api.values(f"'{OVERVIEW_TAB}'!B9")
    base_count = _int_or_zero(overview[0][0]) if overview and overview[0] else 0
    values = [
        (f"'{PRICE_TAB}'!A{target_row}:{last_col}{target_row}", [matrix_row]),
        (f"'{OVERVIEW_TAB}'!B3", [[f"{history[0].isoformat()} ～ {day.isoformat()}"]]),
        (f"'{OVERVIEW_TAB}'!A6:B6", [[f"截至 {day.isoformat()} 有價格", len(prices)]]),
        (f"'{OVERVIEW_TAB}'!B9", [[base_count + len(prices)]]),
        (f"'{OVERVIEW_TAB}'!B10", [[len(history) + 1]]),
    ]
    if patched:
        values.append((f"'{PROGRESS_TAB}'!A2:G{len(patched) + 1}", patched))
    api.write_many(values)
    actual = api.values(f"'{PRICE_TAB}'!A{target_row}:B{target_row}")
    if not actual or normalize_trading_date(actual[0][0]) != day:
        raise RuntimeError("Price row write could not be verified")
    now = dt.datetime.now(NY).isoformat(timespec="seconds")
    api.append(f"'{AUDIT_TAB}'!A:F", [now, "定時增量收盤更新", day.isoformat(), len(symbols), len(prices),
                                   "成功" if len(prices) == len(symbols) else "部分缺價（保留空白）"])
    print(f"Successfully committed {day}: {len(prices)}/{len(symbols)} closes")
    return True


def run(api: SheetAPI, now: dt.datetime | None = None) -> None:
    now = now or dt.datetime.now(dt.timezone.utc)
    header = api.values(f"'{PRICE_TAB}'!A1:TJ1")
    symbols = check_headings(header)
    date_values = api.values(f"'{PRICE_TAB}'!A2:A")
    history = [normalize_trading_date(row[0]) for row in date_values if row and row[0] not in (None, "")]
    if not history or any(x is None for x in history) or history != sorted(set(history)):
        raise RuntimeError("Matrix dates are missing, invalid, duplicated or unsorted")
    cutoff = expected_last_day(now)
    candidates = weekdays_after(history[-1], cutoff)
    if not candidates:
        print(f"No newer weekday after {history[-1]}; no changes")
        return
    if len(candidates) > MAX_DAYS_PER_RUN:
        raise RuntimeError("Too many missed dates to catch up safely in one run")
    api.ensure_grid(STAGING_TAB, 5, BATCH_SIZE * 3)
    for day in candidates:
        if day in us_market_holidays(day.year):
            print(f"NYSE holiday {day}, skipped")
            continue
        # On unscheduled closures, missing anchor fails closed and is retried;
        # it is never misidentified as a valid trading day.
        update_one_day(api, day, history, symbols)
        history.append(day)


def us_market_holidays(year: int) -> set[dt.date]:
    """NYSE regular full-day holidays; special closures must be reviewed separately."""
    def observed(d):
        return d-dt.timedelta(days=1) if d.weekday()==5 else d+dt.timedelta(days=1) if d.weekday()==6 else d
    def nth(month, weekday, n):
        first=dt.date(year,month,1)
        return first+dt.timedelta(days=(weekday-first.weekday())%7+7*(n-1))
    def last(month, weekday):
        from calendar import monthrange
        end=dt.date(year,month,monthrange(year,month)[1])
        return end-dt.timedelta(days=(end.weekday()-weekday)%7)
    # Juneteenth/Independence/New Year's observed on adjacent calendar years.
    days={nth(1,0,3),nth(2,0,3),last(5,0),nth(9,0,1),nth(11,3,4)}
    for y in (year-1,year,year+1):
        for mo,dd in ((1,1),(6,19),(7,4),(12,25)):
            observed_day = observed(dt.date(y,mo,dd))
            if observed_day.year==year:days.add(observed_day)
    # Good Friday: two days before Easter via Gregorian computus
    a=year%19;b=year//100;c=year%100;d=b//4;e=b%4;f=(b+8)//25
    g=(b-f+1)//3;h=(19*a+b-d-g+15)%30;i=c//4;k=c%4
    l=(32+2*e+2*i-h-k)%7;m=(a+11*h+22*l)//451
    mm=(h+l-7*m+114)//31;dd=(h+l-7*m+114)%31+1
    days.add(dt.date(year,mm,dd)-dt.timedelta(days=2))
    return days


def main() -> int:
    secret = os.environ.get("FCN_PRICE_WRITER_JSON", "")
    if not secret:
        raise RuntimeError("GitHub secret FCN_PRICE_WRITER_JSON is not set; scheduled update cannot run")
    try:
        info = json.loads(secret)
        if info.get("type") != "service_account" or not info.get("private_key"):
            raise ValueError()
    except (ValueError, TypeError):
        raise RuntimeError("GitHub secret is not a valid Google service account JSON") from None
    run(SheetAPI.authorized(info))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FCN price update FAILED: {exc}", file=sys.stderr)
        sys.exit(1)


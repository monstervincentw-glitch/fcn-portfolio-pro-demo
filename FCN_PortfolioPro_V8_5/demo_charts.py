"""Fictional normalized FCN chart data and a reusable Sheet Chart parser.

No live prices, client records, Google Sheet IDs, or secrets appear in this module.
The visible chart is explicitly marked as a simulated demonstration.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Sequence

import pandas as pd


DEMO_CHARTS = {
    "DEMO01": {
        "stocks": ("DEMO-X", "DEMO-Y"),
        "start": "2026-06-01", "end": "2026-09-01",
        "ko": 100.0, "strike": 80.0, "ki": 70.0,
        "ko_start": "2026-07-01",
    },
    "DEMO02": {
        "stocks": ("DEMO-A", "DEMO-B", "DEMO-C"),
        "start": "2026-09-01", "end": "2026-10-16",
        "ko": 100.0, "strike": 80.0, "ki": 75.0,
        "ko_start": "2026-10-01",
    },
}


def demo_chart(product_id: str):
    """Return (long-form normalized percentage dataframe, metadata), or (empty, None)."""
    info = DEMO_CHARTS.get(product_id)
    if not info:
        return pd.DataFrame(columns=["date", "stock", "ratio"]), None
    dates = pd.bdate_range(info["start"], info["end"])
    out = []
    for i, date in enumerate(dates):
        for j, stock in enumerate(info["stocks"]):
            # Deterministic, invented values: NEVER confuse with market history.
            direction = (0.12 if product_id == "DEMO01" else -0.11) * i
            swing = 3.5 * math.sin(i / 7.5 + j * 1.7)
            separation = j * (-4.1)
            ratio = 100.0 + direction + swing + separation
            out.append({"date": date, "stock": stock, "ratio": round(ratio, 2)})
    return pd.DataFrame(out), info


def _date(value):
    """Return a real trade date, rejecting accidental chart-marker numbers.

    In Sheets Chart columns, trading dates are serials around 46,000 in 2026,
    but the KO-start *plot marker* is typically a price-level such as 130.
    Converting 130 to a Sheets date would produce 1900-05-09 and make the
    timeline span 130 years, hiding the underlying series.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        if isinstance(value, (dt.datetime, dt.date, pd.Timestamp)):
            parsed = pd.Timestamp(value)
        elif isinstance(value, (int, float)):
            if not math.isfinite(value) or not 32_874 <= float(value) <= 73_415:
                return None  # circa 1990–2100; levels like 130 are NOT dates
            parsed = pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(value))
        elif isinstance(value, str):
            raw = value.strip()
            # ISO or YYYY/MM/DD only. No loose parsing of short numbers.
            if not re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ T].*)?", raw):
                return None
            parsed = pd.Timestamp(raw)
        else:
            return None
    except (ValueError, TypeError, OverflowError, pd.errors.OutOfBoundsDatetime):
        return None
    if not 1990 <= parsed.year <= 2100:
        return None
    return parsed.normalize()


def _numeric_percentage(value):
    """Return (number, explicitly_percentage) without guessing a numeric unit.

    Source Sheets vary: a 100% ratio may be stored as 100, 1.0 or
    the textual display ``100.0%``. We infer a unit per column below.
    """
    if value is None or value == "" or isinstance(value, bool):
        return None, False
    try:
        if isinstance(value, str):
            v = value.strip().replace(",", "")
            if not v or v.startswith("#"):
                return None, False
            explicit = v.endswith("%")
            number = float(v[:-1].strip() if explicit else v)
        else:
            explicit = False
            number = float(value)
        return (number, explicit) if math.isfinite(number) else (None, explicit)
    except (TypeError, ValueError, OverflowError):
        return None, False


def _numeric_unit_multiplier(rows: Sequence[Sequence], column: int) -> float:
    """Infer unit using samples in *this one column*, not each value.

    A normalized stock column begins near either 100 (percentage points) or
    1 (fraction). KO / Strike / KI thresholds likewise may be 100/70 or
    1/.7. This preserves a genuinely low stock value later in the series
    (e.g. 1.5%) instead of mistakenly turning it into 150%.
    """
    samples = []
    for row in rows:
        if len(row) <= column:
            continue
        value, explicit = _numeric_percentage(row[column])
        if value is not None and not explicit and value != 0:
            samples.append(abs(value))
        if len(samples) >= 25:
            break
    if not samples:
        return 1.0
    # The first valid source value is the usual normalization baseline;
    # the median of early observations guards against a single stray cell.
    central = sorted(samples)[len(samples) // 2]
    return 100.0 if central < 5.0 else 1.0


def _percentage(value, multiplier=1.0):
    number, explicit = _numeric_percentage(value)
    if number is None:
        return None
    return number if explicit else number * multiplier


def chart_sheet_rows(rows: Sequence[Sequence]):
    """Parse values from Google Sheets 'Chart'!N11:W1000.

    Columns: date, up to five underlying normalised ratios, KO, Strike, KI,
    KO observation start. Percentage fields may be 100, 1.0 or '100%'.
    Returns (long-form chart data, level metadata) without exposing sheet URLs.
    """
    empty = pd.DataFrame(columns=["date", "stock", "ratio"])
    if not rows:
        return empty, None
    header = list(rows[0])
    symbols = [str(header[j]).strip() if j < len(header) else "" for j in range(1, 6)]
    records = []
    data_rows = rows[1:]
    column_multiplier = {
        j: _numeric_unit_multiplier(data_rows, j) for j in range(1, 9)
    }
    ko = strike = ki = None
    ko_start = None
    for row in rows[1:]:
        if not row:
            continue
        date = _date(row[0])
        if date is None:
            continue
        for j, symbol in enumerate(symbols, 1):
            if not symbol or j >= len(row):
                continue
            ratio = _percentage(row[j], column_multiplier[j])
            if ratio is not None and math.isfinite(ratio):
                records.append({"date": date, "stock": symbol, "ratio": ratio})
        for j, attr in ((6, "ko"), (7, "strike"), (8, "ki")):
            if j < len(row):
                level = _percentage(row[j], column_multiplier[j])
                if level is not None and math.isfinite(level):
                    if attr == "ko": ko = level
                    elif attr == "strike": strike = level
                    else: ki = level
        if ko_start is None and len(row) > 9:
            # Chart!W is a plot-annotation Y level, NOT a date column.
            # A finite marker (e.g. 130) means this row's N-column
            # trading date is the KO observation start.
            marker, _ = _numeric_percentage(row[9])
            if marker is not None and marker != 0:
                ko_start = date
            elif isinstance(row[9], (str, dt.date, dt.datetime, pd.Timestamp)):
                # Older/alternate sources may store the date directly.
                ko_start = _date(row[9])
    if not records:
        return empty, None
    return pd.DataFrame(records), {"ko": ko, "strike": strike, "ki": ki, "ko_start": ko_start}

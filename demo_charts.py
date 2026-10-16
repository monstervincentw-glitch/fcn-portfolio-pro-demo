"""Fictional normalized FCN chart data and a reusable Sheet Chart parser.

No live prices, client records, Google Sheet IDs, or secrets appear in this module.
The visible chart is explicitly marked as a simulated demonstration.
"""
from __future__ import annotations

import datetime as dt
import math
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
    if isinstance(value, (dt.datetime, dt.date, pd.Timestamp)):
        return pd.Timestamp(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(value))
    if isinstance(value, str):
        try:
            return pd.Timestamp(value.strip())
        except (ValueError, TypeError):
            return None
    return None


def _percentage(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            v = value.strip()
            if v.startswith("#"):
                return None
            return float(v[:-1]) if v.endswith("%") else float(v) * 100.0
        return float(value) * 100.0
    except (TypeError, ValueError, OverflowError):
        return None


def chart_sheet_rows(rows: Sequence[Sequence]):
    """Parse values from Google Sheets 'Chart'!N11:W1000.

    Columns: date, up to five underlying normalised ratios, KO, Strike, KI,
    KO observation start. Percentage fields may be numeric fractions or '100%'.
    Returns (long-form chart data, level metadata) without exposing sheet URLs.
    """
    empty = pd.DataFrame(columns=["date", "stock", "ratio"])
    if not rows:
        return empty, None
    header = list(rows[0])
    symbols = [str(header[j]).strip() if j < len(header) else "" for j in range(1, 6)]
    records = []
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
            ratio = _percentage(row[j])
            if ratio is not None and math.isfinite(ratio):
                records.append({"date": date, "stock": symbol, "ratio": ratio})
        for j, attr in ((6, "ko"), (7, "strike"), (8, "ki")):
            if j < len(row):
                level = _percentage(row[j])
                if level is not None and math.isfinite(level):
                    if attr == "ko": ko = level
                    elif attr == "strike": strike = level
                    else: ki = level
        if ko_start is None and len(row) > 9:
            ko_start = _date(row[9])
    if not records:
        return empty, None
    return pd.DataFrame(records), {"ko": ko, "strike": strike, "ki": ki, "ko_start": ko_start}

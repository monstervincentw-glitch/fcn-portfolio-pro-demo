"""FCN Portfolio Pro — high-contrast V2 price / KO / KI / Strike chart.

Drop-in replacement for the existing ``chart_render.py``.  This module
changes visualization only.  No quote, product state, settlement or bank-
verification logic is modified.  The product lines share a deliberate
high-contrast palette and sparse distinct-shaped markers; contractual reference
levels have separate dash patterns and inline labels, without entering the
stock legend/color scale.
"""
from __future__ import annotations

import math
import pandas as pd
import altair as alt

# Legibility on light backgrounds, in a chart screenshot, and under approximate
# color-vision deficiency.  Distinct marker shapes are used as a second cue.
STOCK_COLORS = [
    "#1164B4",  # cobalt blue
    "#DE542C",  # vermilion
    "#793CB1",  # vivid purple
    "#087F75",  # deep teal
    "#B32E78",  # magenta
]
STOCK_SHAPES = ["circle", "square", "diamond", "triangle-up", "cross"]

# Unlike stocks, guide lines are dashed and labeled on-chart.
BARRIERS = {
    "ko": ("KO", "#008B62", [11, 4]),
    "strike": ("Strike", "#BA7600", [8, 3, 2, 3]),
    "ki": ("KI", "#BC2535", [2, 4]),
}
KO_START_COLOR = "#1F2937"


def _number(value):
    """Only chart legitimate, finite reference values; never create a default."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _stock_list(data, requested):
    """Preserve explicit legend order and avoid a stock exceeding palette size."""
    available = {str(v) for v in data["stock"].dropna().unique()}
    ordered = [str(v) for v in requested if str(v) in available]
    return list(dict.fromkeys(ordered))


def build_stock_chart(data, settings, stocks):
    settings = settings or {}
    frame = data.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame["ratio"] = pd.to_numeric(frame["ratio"], errors="coerce")
    selected = _stock_list(frame, stocks)
    if not selected:
        raise ValueError("沒有可繪製的股票代號")
    frame = (frame.loc[frame["stock"].isin(selected)]
             .dropna(subset=["date", "ratio"])
             .sort_values(["stock", "date"]))
    frame = frame.loc[frame["ratio"].map(lambda x: math.isfinite(float(x)) and float(x) > 0)]
    if frame.empty:
        raise ValueError("沒有可繪製的股價")

    selected = [s for s in selected if s in set(frame["stock"])]
    if len(selected) > len(STOCK_COLORS):
        raise ValueError("一檔 FCN 最多顯示五檔股票")

    guides = [(key, *info, _number(settings.get(key)))
              for key, info in BARRIERS.items()]
    guides = [(key, name, color, dash, level)
              for key, name, color, dash, level in guides if level is not None]
    extrema = [float(frame["ratio"].min()), float(frame["ratio"].max())]
    extrema.extend(g[-1] for g in guides)
    bottom = max(0.0, min(extrema) - 6.0)
    top = max(extrema) + 9.0
    y_scale = alt.Scale(domain=[bottom, top], zero=False, nice=False)
    price_colors = alt.Scale(domain=selected, range=STOCK_COLORS[:len(selected)])
    price_shapes = alt.Scale(domain=selected, range=STOCK_SHAPES[:len(selected)])

    x_enc = alt.X("date:T", title="交易日期", axis=alt.Axis(labelAngle=0))
    y_enc = alt.Y("ratio:Q", title="相對期初價格（%）", scale=y_scale)
    line = (alt.Chart(frame).mark_line(strokeWidth=3.1, point=False)
            .encode(x=x_enc, y=y_enc,
                    color=alt.Color("stock:N", title="連結標的", scale=price_colors),
                    tooltip=[alt.Tooltip("date:T", title="日期", format="%Y/%m/%d"),
                             alt.Tooltip("stock:N", title="標的"),
                             alt.Tooltip("ratio:Q", title="相對期初價", format=".2f")]))

    # Sparse point shapes help distinguish stock series without turning the
    # chart into a dense scatter plot.  The lines themselves remain SOLID.
    frame = frame.copy()
    frame["_marker_number"] = frame.groupby("stock", sort=False).cumcount()
    markers = frame.loc[frame["_marker_number"] % 9 == 0]
    points = (alt.Chart(markers)
              .mark_point(filled=True, size=63, opacity=1,
                          stroke="#FFFFFF", strokeWidth=0.8)
              .encode(x="date:T", y="ratio:Q",
                      color=alt.Color("stock:N", scale=price_colors, legend=None),
                      shape=alt.Shape("stock:N", scale=price_shapes, legend=None)))
    chart = line + points

    # Each horizontal guide gets its own conspicuous hue + dash pattern and
    # an on-plot label.  Keep barrier data OUT of the stock legend.
    right_edge = frame["date"].max()
    for _key, label, color, dash, level in guides:
        guide_data = pd.DataFrame({
            "level": [level], "name": [label],
            "label": [f"{label}  {level:.1f}%"], "end_date": [right_edge],
        })
        rule = (alt.Chart(guide_data)
                .mark_rule(color=color, strokeWidth=2.8, strokeDash=dash, opacity=1)
                .encode(y=alt.Y("level:Q"),
                        tooltip=[alt.Tooltip("name:N", title="檢核線"),
                                 alt.Tooltip("level:Q", title="參考水位", format=".2f")]))
        tag = (alt.Chart(guide_data)
               .mark_text(color=color, fontWeight="bold", fontSize=12,
                          align="right", baseline="bottom", dx=-5, dy=-6)
               .encode(x="end_date:T", y="level:Q", text="label:N"))
        chart = chart + rule + tag

    # A dark vertical line with explicit date label has a different visual
    # language than both solid stock series and horizontal price levels.
    ko_date = pd.to_datetime(settings.get("ko_start"), errors="coerce")
    if pd.notna(ko_date):
        ko_date = ko_date.normalize()
        if frame["date"].min() <= ko_date <= right_edge:
            ko_label = f"KO 觀察開始 {ko_date:%m/%d}"
            event = pd.DataFrame({
                "date": [ko_date], "top": [top - 0.5],
                "event": [ko_label],
            })
            vertical = (alt.Chart(event)
                        .mark_rule(color=KO_START_COLOR, strokeWidth=2.4,
                                   strokeDash=[4, 4], opacity=0.95)
                        .encode(x="date:T",
                                tooltip=[alt.Tooltip("date:T", title="KO 開始觀察日", format="%Y/%m/%d")]))
            date_tag = (alt.Chart(event)
                        .mark_text(color=KO_START_COLOR, fontWeight="bold",
                                   fontSize=12, align="left", baseline="top",
                                   dx=6, dy=3)
                        .encode(x="date:T", y="top:Q", text="event:N"))
            chart = chart + vertical + date_tag

    return (chart.properties(height=400)
            .resolve_scale(color="shared")
            .interactive())

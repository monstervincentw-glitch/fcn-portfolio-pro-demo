"""FCN advisor market-risk monitor.

Observations and KI levels MUST come from connected product terms / dated charts;
missing product records are a separate data-maintenance backlog, never KI alerts.
The comparison is of dated *closing values* versus a barrier level, NOT a legal
KI trigger determination (AKI may involve intraday trades; EKI maturity only).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from math import isfinite
from typing import Any
import pandas as pd
import re
import unicodedata
from demo_utils import is_active_product


def _day(x: Any) -> date | None:
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    if isinstance(x, (int, float)) and not isinstance(x, bool) and 20_000 < x < 110_000:
        return (datetime(1899, 12, 30) + timedelta(days=x)).date()
    if x is None or str(x).strip() in {"", "#N/A", "—"}:
        return None
    try:
        d = pd.to_datetime(str(x).strip(), errors="coerce")
        return d.date() if pd.notna(d) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _pct(x: Any) -> float | None:
    if x is None:
        return None
    s = str(x).strip().replace(",", "").replace("％", "%")
    try:
        v = float(s.rstrip("%"))
    except (TypeError, ValueError):
        return None
    if not isfinite(v):
        return None
    return v * 100 if "%" not in s and 0 < abs(v) <= 2 else v


def active_product(product: dict) -> bool:
    return is_active_product(product)


def parse_terms(rows: list[list] | None) -> dict:
    """Parse first columns of actual 商品條款, with no inferred KI thresholds."""
    result = {"ki": None, "ki_type": "未記載", "ko_start": None,
              "final_eval": None, "period_ends": []}
    if not rows:
        return result
    within_periods = False
    for row in rows:
        if not row:
            continue
        key = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(row[0] or ""))).upper()
        val = row[1] if len(row) > 1 else None
        if any(label in key for label in ("KI門檻", "KI水位", "KI障礙")):
            result["ki"] = _pct(val)
        elif "KI類型" in key:
            result["ki_type"] = str(val or "未記載").strip()
        elif "KO開始觀察日" in key:
            result["ko_start"] = _day(val)
        elif "期末評價日" in key:
            result["final_eval"] = _day(val)
        elif key == "配息期":
            within_periods = True
        elif within_periods and key.isdigit() and len(row) > 2:
            end = _day(row[2])
            if end:
                result["period_ends"].append(end)
    return result


def next_observation(terms: dict, coupon_rows: list[dict], product_id: str, today: date) -> tuple[date | None, str]:
    ko_start = terms.get("ko_start")
    options = []
    for d in terms.get("period_ends", []):
        if d >= today and (ko_start is None or d >= ko_start):
            options.append((d, "商品條款配息期末（比價日需依契約確認）"))
    # Use master coupon dates only as a fallback; never claim they are contractual KO days.
    if not options:
        for row in coupon_rows:
            if str(row.get("商品代號") or "").strip() != product_id:
                continue
            d = _day(row.get("觀察期末日"))
            if d and d >= today and (ko_start is None or d >= ko_start):
                options.append((d, "總帳配息觀察期末（比價日需依契約確認）"))
    if not options and terms.get("final_eval") and terms["final_eval"] >= today:
        options.append((terms["final_eval"], "期末評價日"))
    return min(options, key=lambda r:r[0]) if options else (None, "")


def market_risks(products: list[dict], coupons: list[dict], snapshots: dict,
                 today: date, days_ahead: int = 30, ki_buffer_points: float = 10.0,
                 max_stale_days: int = 7) -> dict:
    """Return risk alerts, separate maintenance backlog, and stale market data.

    snapshots[product_id] = (chart_dataframe, settings_dict, terms_dict).
    No fake prices or KI levels are added when data is unavailable.
    """
    warnings = []
    pending = []
    stale = []
    missing_ki = []
    observations = []
    market_count = 0
    for product in products:
        pid = str(product.get("product_id") or "").strip()
        if not pid or not active_product(product):
            continue
        if pid not in snapshots:
            pending.append(pid)
            continue
        chart, settings, terms = snapshots[pid]
        settings = settings or {}
        terms = terms or {}
        obs_day, obs_note = next_observation(terms, coupons, pid, today)
        days = (obs_day-today).days if obs_day else None
        upcoming = days is not None and 0 <= days <= days_ahead
        ki_type = str(terms.get("ki_type") or "未記載")
        # Display observed barrier distance even when contractual trigger type is unknown.
        # This is a level comparison, never a determination that KI has triggered.
        ki = terms.get("ki") if terms.get("ki") is not None else settings.get("ki")
        ki_source = "商品條款" if terms.get("ki") is not None else "Chart 水位（條款待核對）"
        type_key = re.sub(r"[\s_-]+", "", unicodedata.normalize("NFKC", ki_type)).upper()
        no_ki = type_key in {"NONKI", "NOKI", "無KI", "無敲入"}
        if no_ki:
            ki = None
        if ki is not None:
            try:
                ki = float(ki)
                if not isfinite(ki) or ki <= 0:
                    ki = None
            except (TypeError, ValueError):
                ki = None
        if chart is None or chart.empty:
            if upcoming:
                warnings.append({"FCN":pid, "標的":"—", "行情日":"—", "最新水位 %":None,
                                 "KI 水位 %":ki, "距 KI 百分點":None, "下次觀察期末":str(obs_day),
                                 "距觀察期末(天)":days, "預警":"近期觀察期末（缺行情）", "說明":obs_note,
                                 "_rank":3})
            else:
                pending.append(pid)
            continue
        frame = chart.copy()
        frame["date"] = pd.to_datetime(frame["date"],errors="coerce")
        frame["ratio"] = pd.to_numeric(frame["ratio"],errors="coerce")
        frame = frame.dropna(subset=["date","ratio","stock"])
        frame=frame[(frame["date"].dt.date<=today) & (frame["ratio"]>0)]
        if frame.empty:
            stale.append(pid)
            continue
        latest = frame.sort_values("date").groupby("stock",as_index=False).tail(1)
        for _,rec in latest.iterrows():
            d=rec["date"].date()
            symbol=str(rec["stock"]).upper().strip()
            ratio=float(rec["ratio"])
            if (today - d).days > max_stale_days:
                stale.append(f"{pid}/{symbol} ({d.isoformat()})")
                continue
            market_count+=1
            gap=ratio-ki if ki is not None and ki>0 else None
            if gap is None and not no_ki:
                missing_ki.append(f"{pid}/{symbol}")
            observation={"FCN":pid,"標的":symbol,"行情日":d.isoformat(),
                         "最新水位 %":round(ratio,2),"KI 水位 %":round(ki,2) if ki is not None else None,
                         "距 KI 百分點":round(gap,2) if gap is not None else None,
                         "KI 類型":ki_type,"KI 來源":ki_source if ki is not None else ("不適用（無 KI 條款）" if no_ki else "未取得")}
            observations.append(observation)
            if gap is not None and gap<=0:
                status="低於 KI 水位（不代表已觸發 KI）";rank=0
            elif gap is not None and gap<=ki_buffer_points:
                status="接近 KI 水位";rank=1
            elif upcoming:
                status="近期觀察期末";rank=2
            else:
                continue
            warnings.append({"FCN":pid,"標的":symbol,"行情日":d.isoformat(),
                             "最新水位 %":round(ratio,2),"KI 水位 %":round(ki,2) if ki is not None else None,
                             "距 KI 百分點":round(gap,2) if gap is not None else None,
                             "下次觀察期末":str(obs_day) if obs_day else "—",
                             "距觀察期末(天)":days,"預警":status,
                             "說明":(obs_note+"；" if obs_note else "")+f"KI類型：{ki_type}；來源：{ki_source}；僅比較水位，不判定敲入", "_rank":rank})
    warnings.sort(key=lambda r:(r["_rank"],r["距 KI 百分點"] if r["距 KI 百分點"] is not None else 999,
                                r["距觀察期末(天)"] if r["距觀察期末(天)"] is not None else 999,r["FCN"]))
    below=sum(x["_rank"]==0 for x in warnings)
    near=sum(x["_rank"]==1 for x in warnings)
    imminent=len({x["FCN"] for x in warnings if x["距觀察期末(天)"] is not None and x["距觀察期末(天)"]<=days_ahead})
    for r in warnings:
        r.pop("_rank",None)
    return {"alerts":warnings,"below":below,"near":near,"imminent":imminent,
            "market_count":market_count,"pending":sorted(set(pending)),"stale":sorted(set(stale)),
            "missing_ki":sorted(set(missing_ki)),"observations":observations}


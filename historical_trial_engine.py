"""FCN Portfolio Pro - read-only historic scenario simulator.

FCN 通用最終 V2 assumptions: up to five linked stocks, monthly coupons,
KO/Strike/KI and EKI/AKI/Non-KI principal modelling. No real client data,
future forecasts, external price feeds, or write access in this module.
All returns are *conditional model outputs*, never booked bank cash flows.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd
from dateutil.relativedelta import relativedelta


class TrialDataError(ValueError):
    """Input or historical source cannot support an honest trial result."""


def parse_symbols(text: str) -> tuple[str, ...]:
    raw = [x.strip().upper() for x in re.split(r"[,，;；\s]+", str(text or "")) if x.strip()]
    codes = tuple(dict.fromkeys(raw))
    if not codes or len(codes) > 5 or any(not re.fullmatch(r"[A-Z0-9.^_-]{1,22}", s) for s in codes):
        raise TrialDataError("請輸入 1～5 檔有效標的代號，以逗號分開。")
    return codes


def parse_month(value: str) -> dt.date:
    if not re.fullmatch(r"\d{4}-(0?[1-9]|1[0-2])", str(value or "").strip()):
        raise TrialDataError("期初月份請填 YYYY-MM，例如 2026-05。")
    year, month = map(int, value.strip().split("-"))
    if not 2000 <= year <= 2099:
        raise TrialDataError("請選擇 2000～2099 年之間的期初月份。")
    return dt.date(year, month, 1)


def _finite_number(value: Any) -> float | None:
    try:
        v = float(value)
        return v if math.isfinite(v) and v > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def choose_available_series(
    sources: list[tuple[str, pd.DataFrame]], codes: tuple[str, ...],
    month_start: dt.date, term_months: int
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Pick one coherent authorized FCN Chart source per stock.

    Chart normalized percentages can be re-based to a new starting month, as
    long as all prices are from the *same* product source for one ticker.
    Never stitch across different sources with inconsistent corporate actions.
    """
    needed_end = pd.Timestamp(month_start) + relativedelta(months=term_months + 1)
    # If possible reuse ONE product Chart containing all requested underlyings:
    # this preserves a consistent universe of observation days for worst-of KO.
    candidates_one_sheet = []
    for source_name, df in sources:
        if df is None or df.empty or not {"date", "stock", "ratio"}.issubset(df.columns):
            continue
        available = {str(x).upper() for x in df.stock.unique()}
        if all(code in available for code in codes):
            dat = pd.to_datetime(df.date, errors="coerce")
            mask = (dat >= pd.Timestamp(month_start)) & (dat < (pd.Timestamp(month_start) + relativedelta(months=1)))
            overlap = df.loc[mask & df.stock.astype(str).str.upper().isin(codes)]
            present = len(set(overlap.stock.astype(str).str.upper())) == len(codes)
            candidates_one_sheet.append((present, len(overlap), source_name, df))
    if candidates_one_sheet:
        good = [v for v in candidates_one_sheet if v[0]]
        if good:
            _, _, common_name, common_df = max(good, key=lambda x:(x[1], x[2]))
            sources = [(common_name, common_df)]
    selected = []
    provenance = {}
    for code in codes:
        candidates = []
        for source_name, df in sources:
            if df is None or df.empty or not {"date", "stock", "ratio"}.issubset(df.columns):
                continue
            sub = df.loc[df["stock"].astype(str).str.upper() == code, ["date", "ratio"]].copy()
            if sub.empty:
                continue
            sub["date"] = pd.to_datetime(sub["date"], errors="coerce").dt.normalize()
            sub["ratio"] = pd.to_numeric(sub["ratio"], errors="coerce")
            sub = sub.dropna().loc[lambda x: x["ratio"] > 0].drop_duplicates("date", keep="last").sort_values("date")
            if sub.empty:
                continue
            in_scope = sub[(sub.date >= pd.Timestamp(month_start)) & (sub.date <= needed_end)]
            first = sub.date.min()
            last = sub.date.max()
            in_month = in_scope[in_scope.date < (pd.Timestamp(month_start)+relativedelta(months=1))]
            coverage_score = (not in_month.empty, last >= needed_end, last, len(in_scope))
            candidates.append((coverage_score, source_name, sub))
        if not candidates:
            raise TrialDataError(f"{code} 沒有已授權商品的歷史 Chart 資料，無法計算。")
        _, source, prices = max(candidates, key=lambda x: x[0])
        provenance[code] = source
        prices["stock"] = code
        selected.append(prices)
    return pd.concat(selected, ignore_index=True), provenance


@dataclass(frozen=True)
class TrialInputs:
    symbols: tuple[str, ...]
    start_month: dt.date
    term_months: int
    lockup_months: int
    annual_coupon_pct: float
    principal: float = 100000.0
    ko_pct: float = 100.0
    strike_pct: float = 75.0
    ki_pct: float | None = 65.0
    ki_type: str = "EKI"

    def validate(self):
        if not 1 <= len(self.symbols) <= 5 or len(set(self.symbols)) != len(self.symbols):
            raise TrialDataError("股票代號需為 1～5 個不重複標的。")
        if not 1 <= self.term_months <= 12:
            raise TrialDataError("合約期間應為 1～12 個月（依 V2 的 12 期模型）。")
        if not 0 <= self.lockup_months < self.term_months:
            raise TrialDataError("閉鎖期需短於合約期間，單位是月。")
        if not 0 <= self.annual_coupon_pct <= 100 or not math.isfinite(self.annual_coupon_pct):
            raise TrialDataError("年化票息需在 0～100% 之間。")
        if not math.isfinite(self.principal) or self.principal <= 0:
            raise TrialDataError("示範本金需大於零。")
        if self.ki_type not in ("EKI", "AKI", "Non-KI"):
            raise TrialDataError("KI 模式必須是 EKI、AKI 或 Non-KI。")
        if not 0 < self.ko_pct <= 300 or not 0 < self.strike_pct <= 200:
            raise TrialDataError("KO 和 Strike 需為有效百分比。")
        if self.ki_type != "Non-KI" and (self.ki_pct is None or not 0 < self.ki_pct <= 200):
            raise TrialDataError("有 KI 模式時需提供 KI 門檻。")


def _first_from(index: pd.DatetimeIndex, date: pd.Timestamp, max_days: int = 7):
    loc = index.searchsorted(date, side="left")
    if loc >= len(index):
        return None
    result = index[loc]
    return result if 0 <= (result - date).days <= max_days else None


def _last_upto(index: pd.DatetimeIndex, date: pd.Timestamp, max_days: int = 7):
    loc = index.searchsorted(date, side="right") - 1
    if loc < 0:
        return None
    result = index[loc]
    return result if 0 <= (date - result).days <= max_days else None


def simulate_history(prices: pd.DataFrame, params: TrialInputs, as_of=None) -> dict:
    """Run historical as-of FCN model without inventing future prices.

    Prices are expected in columns: date / stock / ratio (source-normalized
    percentages). Observations require simultaneous prices for ALL stocks.
    Eligible KO is checked at monthly observation dates at/after lockup.
    Coupon on KO month is prorated by available common trading days; calendar
    and payout date are approximations, not contractual bank settlement.
    """
    params.validate()
    if prices is None or prices.empty or not {"date", "stock", "ratio"}.issubset(prices.columns):
        raise TrialDataError("查無可用的歷史價格資料，不能計算試打收益。")
    frame = prices[["date", "stock", "ratio"]].copy()
    frame["date"] = pd.to_datetime(frame.date, errors="coerce").dt.normalize()
    frame["stock"] = frame.stock.astype(str).str.upper().str.strip()
    frame["ratio"] = pd.to_numeric(frame.ratio, errors="coerce")
    frame = frame.dropna()
    frame = frame[(frame.stock.isin(params.symbols)) & (frame.ratio > 0)]
    if frame.duplicated(["date", "stock"]).any():
        raise TrialDataError("同一標的與日期出現不同筆行情，請先檢查來源。")
    panel = frame.pivot(index="date", columns="stock", values="ratio")
    if any(x not in panel.columns for x in params.symbols):
        raise TrialDataError("不是所有連結標的都有有效行情。")
    panel = panel.loc[:, list(params.symbols)].dropna().sort_index()
    if panel.empty:
        raise TrialDataError("標的間沒有同一天的完整價格，無法判定 KO。")
    start = pd.Timestamp(params.start_month)
    if as_of is None:
        as_of = pd.Timestamp.today().normalize()
    cutoff = pd.Timestamp(as_of).normalize()
    panel = panel[panel.index <= cutoff]
    if panel.empty:
        raise TrialDataError("指定日期前沒有歷史行情，無法進行試打。")
    first = _first_from(panel.index, start, max_days=31)
    if first is None or first.month != start.month:
        raise TrialDataError("期初月份沒有完整股票行情，無法建立期初基準。")
    panel = panel[panel.index >= first]
    if len(panel) < 2:
        raise TrialDataError("期初後至少需兩個有完整股價的交易日。")
    panel = panel.div(panel.loc[first], axis=1) * 100.0
    issue = first + pd.offsets.BDay(5)  # V2 first convention: 5 weekdays after pricing
    maturity_date = issue + relativedelta(months=params.term_months)
    # The historical contract chart should not leak beyond its requested tenor.
    panel = panel.loc[panel.index <= maturity_date]
    maturity_mark = _last_upto(panel.index, maturity_date, max_days=7)
    if maturity_mark is not None and maturity_mark < issue:
        maturity_mark = None
    history_end = panel.index.max()
    ko_observation_start = issue + relativedelta(months=params.lockup_months)
    # FCN V2 observes KO on EVERY trading day from lockup expiry, not only
    # monthly coupon boundaries. SR39/SQ29 may knock out between coupon dates.
    eligible = panel.loc[(panel.index >= ko_observation_start) &
                         (panel.index <= maturity_date)]
    # A long trading-day data gap can conceal an earlier KO. Holidays may
    # explain short gaps, but never infer a conclusive payoff from long gaps.
    window_end = min(maturity_date, cutoff, panel.index.max())
    expected = pd.bdate_range(ko_observation_start, window_end)
    actual = set(panel.index[(panel.index >= ko_observation_start) & (panel.index <= window_end)])
    consecutive_missing = 0
    longest_missing = 0
    for day in expected:
        consecutive_missing = 0 if day in actual else consecutive_missing + 1
        longest_missing = max(longest_missing, consecutive_missing)
    if longest_missing > 5:
        raise TrialDataError("KO 觀察期間有連續超過五個工作日缺價，可能漏判提前 KO，不能核定總收益。")
    if len(expected) and len(actual) / len(expected) < 0.70:
        raise TrialDataError("KO 觀察期間歷史行情涵蓋率低於 70%，不能核定總收益。")
    qualifying = eligible[eligible.min(axis=1) >= params.ko_pct]
    ko_date = qualifying.index[0] if not qualifying.empty else None
    observations = [{"date":pd.Timestamp(i), "worst_pct":float(row.min())}
                    for i,row in eligible.iterrows()]
    final_date = None
    principal_return_pct = None
    if ko_date is not None:
        final_date = ko_date
        principal_return_pct = 100.0
        status = "歷史情境：提前KO"
    elif cutoff >= maturity_date and maturity_mark is not None and (cutoff - maturity_date).days >= 0:
        # Do not manufacture a result when the sheet ends long before maturity;
        # must also observe an actual trade close near the valuation date.
        final_date = maturity_mark
        final_worst = float(panel.loc[final_date].min())
        triggered = params.ki_type == "Non-KI" or (
            params.ki_type == "EKI" and final_worst < float(params.ki_pct)
        ) or (
            params.ki_type == "AKI" and float(panel.loc[panel.index <= final_date].min(axis=1).min()) <= float(params.ki_pct)
        )
        principal_return_pct = min(100.0, max(0.0, 100.0 * final_worst / params.strike_pct)) if triggered and final_worst < params.strike_pct else 100.0
        status = "歷史情境：到期"  # never 'actually settled'
    else:
        status = "尚未到期／資料未覆蓋到期日"
    coupon_steps = []
    coupon_sum = 0.0
    for month in range(1, params.term_months + 1):
        prior = issue + relativedelta(months=month - 1)
        end = issue + relativedelta(months=month)
        whole = panel.index[(panel.index >= prior) & (panel.index <= end)]
        if len(whole) == 0:
            fraction = None
        elif final_date is not None and ko_date is not None and ko_date < end:
            # Source often includes post-KO chart prices; when not complete,
            # denominator approximates remaining sessions via weekdays.
            count = (whole <= ko_date).sum()
            denominator = len(whole) if panel.index.max() >= end else len(pd.bdate_range(prior,end))
            fraction = min(1.0, count / denominator) if count and denominator else None
        elif final_date is not None and ko_date is not None and ko_date >= prior:
            fraction = 1.0
        elif final_date is not None:
            fraction = 1.0
        elif end <= cutoff and _first_from(panel.index, end, max_days=7) is not None:
            fraction = 1.0
        else:
            fraction = None
        if ko_date is not None and prior > ko_date:
            break
        rate = params.annual_coupon_pct / 12.0 * fraction if fraction is not None else None
        if rate is not None:
            coupon_sum += rate
        coupon_steps.append({"期數":month,"期間開始日":prior.date(),"期間結束日":end.date(),
                             "計息比例":fraction,"模型票息率(%)":rate})
        if ko_date is not None and end >= ko_date:
            break
    model_total = coupon_sum + principal_return_pct - 100.0 if principal_return_pct is not None else None
    price_records = panel.stack().rename("ratio").reset_index().rename(columns={"level_1":"stock"})
    price_records["date"] = pd.to_datetime(price_records["date"])
    return {
        "status": status, "pricing_date": first.date(), "estimated_issue_date": issue.date(),
        "scheduled_maturity": maturity_date.date(), "ko_date": ko_date.date() if ko_date is not None else None,
        "last_market_date": history_end.date(), "final_date": final_date.date() if final_date is not None else None,
        "principal_return_pct": principal_return_pct,"coupon_pct":round(coupon_sum, 8),
        "total_return_pct": round(model_total, 8) if model_total is not None else None,
        "principal_return_amount": params.principal * principal_return_pct / 100.0 if principal_return_pct is not None else None,
        "coupon_amount": params.principal * coupon_sum / 100.0,
        "total_profit_amount": params.principal * model_total / 100.0 if model_total is not None else None,
        "max_coupon_if_full_term_pct":params.annual_coupon_pct*params.term_months/12.0,
        "ko_start":(_first_from(panel.index,ko_observation_start,max_days=7) or ko_observation_start).date(),
        "chart":price_records,"coupon_steps":coupon_steps,"observations":observations,
    }

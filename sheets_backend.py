"""Read-only Google Sheets adapter for FCN Portfolio Pro.

NO API keys or workbook contents are included in this source file.
Uses OAuth service-account credentials provided only through Streamlit secrets.
The adapter never writes or edits Google Sheets.
"""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import quote
from dataclasses import dataclass
from typing import Any

import pandas as pd

from demo_charts import chart_sheet_rows

READ_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
SHEET_URL = re.compile(r"^https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)(?:/|$)")

# The master API tabs deliberately expose assumed contractual settlements,
# not bank-confirmed transactions. Do NOT use historic bank cash-flow columns.
DATA_RANGES = {
    "customers": "'API_客戶'!A3:I160",
    "holdings": "'API_持倉'!A3:AD160",
    "products": "'API_商品'!A3:Z110",
    "coupons": "'配息期快取'!A4:M520",
    "exceptions": "'異常覆寫'!A4:M130",
}

class SheetConnectionError(RuntimeError):
    """A sanitized error message safe to display to the authorized user."""


def serial_date(value: Any) -> dt.date | None:
    """Convert Google Sheets serial dates (or ISO dates) to date objects."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        if not 20_000 < float(value) < 110_000:
            return None
        return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(value))).date()
    if isinstance(value, str) and value.strip():
        try:
            return pd.to_datetime(value.strip(), errors="raise").date()
        except (ValueError, TypeError, OverflowError):
            return None
    return None


def normalized_rows(values: list[list], required: tuple[str, ...] = ()) -> list[dict]:
    """Parse sheet header + rows into dictionaries; never turn blanks into zero."""
    if not values:
        raise SheetConnectionError("Google Sheets 分頁沒有標題列，請檢查資料來源。")
    header = [str(v).strip() if v is not None else "" for v in values[0]]
    absent = [f for f in required if f not in header]
    if absent:
        raise SheetConnectionError("Google Sheets 欄位異動，缺少：" + "、".join(absent))
    result = []
    for cells in values[1:]:
        if not any(c not in (None, "") for c in cells):
            continue
        item = {}
        for i, h in enumerate(header):
            if not h:
                continue
            x = cells[i] if i < len(cells) else None
            item[h] = x if x != "" else None
        result.append(item)
    return result


def sheet_id_from_url(url: str | None) -> str | None:
    """Only accept exact Google Sheets URLs; no arbitrary server-side URLs."""
    if not url or not isinstance(url, str):
        return None
    m = SHEET_URL.match(url.strip())
    return m.group(1) if m else None


def _coerce_date_fields(items: list[dict], keys: tuple[str, ...]) -> list[dict]:
    for item in items:
        for key in keys:
            if key in item:
                item[key] = serial_date(item[key])
    return items


def validate_masked_portfolio(data: dict) -> dict:
    """Fail closed if a user renames an API customer to an unmasked real name.

    This is a display-layer guardrail, NOT a substitute for access control or
    genuine anonymisation. Portfolio values/positions may remain identifying.
    """
    customer_rows = data.get("customers", [])
    customer_aliases = {str(r.get("customer_id") or "").strip() for r in customer_rows}
    display_aliases = {str(r.get("display_name") or "").strip() for r in customer_rows}
    holding_aliases = {str(r.get("customer_id") or "").strip() for r in data.get("holdings", [])}
    if not customer_aliases or any("*" not in x for x in customer_aliases | display_aliases):
        raise SheetConnectionError("客戶名稱遮罩檢查未通過，已停止載入正式資料。請檢查 API_客戶。")
    if not holding_aliases.issubset(customer_aliases):
        raise SheetConnectionError("持倉的客戶代號無法對應模糊化名冊，已停止載入。")
    # 'customer_ids' is a free-text field from API_商品, so it must never reveal
    # a newly inserted unmapped name.
    for product in data.get("products", []):
        participants = str(product.get("customer_ids") or "")
        if participants:
            tokens = [t.strip() for t in participants.replace(",", "、").split("、") if t.strip()]
            if any(token not in customer_aliases for token in tokens):
                product["customer_ids"] = "已遮罩（未驗證對應）"
    return data


@dataclass
class SheetsReader:
    master_sheet_id: str
    session: Any

    @classmethod
    def from_secrets(cls, service_account_info: dict, master_sheet_id: str):
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,}", str(master_sheet_id or "")):
            raise SheetConnectionError("尚未設定有效的總帳試算表 ID。")
        try:
            from google.auth.transport.requests import AuthorizedSession
            from google.oauth2 import service_account
            credentials = service_account.Credentials.from_service_account_info(
                dict(service_account_info), scopes=[READ_SCOPE]
            )
        except (KeyError, ValueError, TypeError, ImportError):
            raise SheetConnectionError("Google 服務帳號格式不完整，請檢查 Streamlit Secrets。") from None
        return cls(master_sheet_id=master_sheet_id, session=AuthorizedSession(credentials))

    def read(self, sheet_id: str, a1: str) -> list[list]:
        """Read a single range; credentials stay on the application server."""
        try:
            response = self.session.get(
                f"{SHEETS_API}/{sheet_id}/values/{quote(a1, safe='')}",
                params={"valueRenderOption": "UNFORMATTED_VALUE"}, timeout=25,
            )
            if response.status_code in (401, 403):
                raise SheetConnectionError("連線遭拒：請用 Viewer 權限分享試算表給服務帳號，並確認 Google Sheets API 已啟用。")
            if response.status_code == 404:
                raise SheetConnectionError("找不到試算表：請核對 ID 及服務帳號的分享權限。")
            response.raise_for_status()
            return response.json().get("values", [])
        except SheetConnectionError:
            raise
        except Exception as exc:
            raise SheetConnectionError("無法讀取 Google Sheets，請確認網路、憑證、API 與分享權限。") from None

    def read_many(self, ranges: list[str]) -> list[list[list]]:
        params = [("ranges", x) for x in ranges]
        params.append(("valueRenderOption", "UNFORMATTED_VALUE"))
        try:
            response = self.session.get(
                f"{SHEETS_API}/{self.master_sheet_id}/values:batchGet",
                params=params, timeout=35,
            )
            if response.status_code in (401, 403):
                raise SheetConnectionError("讀取總帳遭拒：請把總帳以 Viewer 權限分享給服務帳號。")
            if response.status_code == 404:
                raise SheetConnectionError("總帳試算表不存在或服務帳號無讀取權限。")
            response.raise_for_status()
            value_ranges = response.json().get("valueRanges", [])
            if len(value_ranges) != len(ranges):
                raise SheetConnectionError("總帳回傳的分頁數量異常，請確認 API 工作表名稱。")
            return [v.get("values", []) for v in value_ranges]
        except SheetConnectionError:
            raise
        except Exception:
            raise SheetConnectionError("Google Sheets API 暫時無法取得資料，請稍後重試。") from None

    def diagnostic(self) -> dict[str, bool]:
        """Only read header rows; DO NOT show private customer data."""
        heads = self.read_many([
            "'API_客戶'!A3:I3", "'API_持倉'!A3:AD3", "'API_商品'!A3:Z3",
            "'配息期快取'!A4:M4",
        ])
        expected = (
            "customer_id", "holding_id", "product_id", "商品代號"
        )
        return {name: bool(rows and required in rows[0]) for name, rows, required in zip(
            ("客戶 API", "持倉 API", "商品 API", "配息期快取"), heads, expected
        )}

    def portfolio(self) -> dict:
        keys = list(DATA_RANGES)
        vals = self.read_many([DATA_RANGES[k] for k in keys])
        data = {}
        for key, values in zip(keys, vals):
            if key == "customers":
                records = normalized_rows(values, ("customer_id", "display_name"))
            elif key == "holdings":
                records = normalized_rows(values, (
                    "holding_id", "customer_id", "product_id", "currency",
                    "invested_amount", "estimated_settlement_state"
                ))
                _coerce_date_fields(records, (
                    "trade_date", "pricing_date", "issue_date", "ko_date",
                    "final_eval_date", "expected_principal_date", "last_return_date"
                ))
            elif key == "products":
                records = normalized_rows(values, (
                    "product_id", "visibility_flag", "product_currency", "source_url"
                ))
                _coerce_date_fields(records, (
                    "ko_date", "maturity_date", "end_event_date", "visible_until", "final_eval_date"
                ))
            elif key == "coupons":
                records = normalized_rows(values, ("商品代號", "期數", "模型本期票息率"))
                _coerce_date_fields(records, ("觀察期起日", "觀察期末日", "契約配息日", "預估入帳日"))
            else:  # exceptions: read only; edits still take place inside private Sheets
                records = normalized_rows(values, ("持倉ID", "啟用狀態"))
                _coerce_date_fields(records, ("覆寫結算日",))
            data[key] = records
        # Hide empty reserve rows; never invent currency or principal state.
        data["customers"] = [x for x in data["customers"] if x.get("customer_id")]
        data["holdings"] = [x for x in data["holdings"] if x.get("holding_id") and x.get("customer_id")]
        data["products"] = [x for x in data["products"] if x.get("product_id")]
        data["coupons"] = [x for x in data["coupons"] if x.get("商品代號") and x.get("期數")]
        return data

    def product_chart(self, product: dict):
        source = sheet_id_from_url(product.get("source_url"))
        if not source:
            return pd.DataFrame(columns=["date", "stock", "ratio"]), None
        # Only one chosen product is read at a time, from its private Chart sheet.
        return chart_sheet_rows(self.read(source, "'Chart'!N11:W1000"))


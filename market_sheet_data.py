"""Read selected US-stock historical CLOSE prices from the private V8.4 Sheet.

This module NEVER writes to Google Sheets and NEVER invents missing prices.
The independent price library must be shared Viewer with the same service
account used by the Streamlit deployment. Read-only credentials are required.
"""
from __future__ import annotations
from datetime import date
from math import isfinite
import re
import pandas as pd
from market_data import MarketQuoteMeta, MarketFeedError
from sheets_backend import SheetsReader, SheetConnectionError

PRICE_TAB = '收盤價矩陣'
ID_RE = re.compile(r'[A-Za-z0-9_-]{20,}\Z')


def column_name(index: int) -> str:
    """0-indexed column number to Sheets A1 column letters."""
    if index < 0:
        raise ValueError('negative column index')
    result = ''
    n = index + 1
    while n:
        n, digit = divmod(n - 1, 26)
        result = chr(65 + digit) + result
    return result


def parse_matrix_rows(symbols, headers, price_columns, date_column, start, end):
    """Parse paired 1-column row-aligned ranges. Strict: blanks stay missing."""
    expected = {str(s).strip().upper() for s in symbols}
    if not expected or len(expected) != len(symbols):
        raise MarketFeedError('股票代號不可重複或空白。')
    header = [str(x).upper().strip() for x in headers]
    if len(header) != len(set(header)):
        raise MarketFeedError('股價資料庫存在重複股票代號，請先修正表頭。')
    missing = sorted(expected - set(header))
    if missing:
        raise MarketFeedError('股價資料庫尚無以下股票：' + ', '.join(missing))
    if len(price_columns) != len(symbols):
        raise MarketFeedError('股價欄位數量錯誤，試打已停止。')
    records=[]
    seen=set()
    # Ranges start at the same row (2), including rows where price is blank.
    for idx, day_row in enumerate(date_column):
        if not day_row or day_row[0] in ('', None):
            continue
        try:
            raw_date=str(day_row[0]).strip()
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw_date):
                raise ValueError('bad date format')
            day=date.fromisoformat(raw_date)
        except ValueError:
            raise MarketFeedError('股價庫含無法辨識的交易日期，為避免錯配已停止。') from None
        if day < start or day > end:
            continue
        for sym, col in zip(symbols, price_columns):
            if idx >= len(col) or not col[idx] or col[idx][0] in ('',None):
                continue
            try:
                price=float(col[idx][0])
            except (TypeError,ValueError,OverflowError):
                raise MarketFeedError(f'{sym} 在 {day} 的收盤價非數字，請檢查資料庫。') from None
            if not isfinite(price) or price<=0:
                raise MarketFeedError(f'{sym} 在 {day} 的收盤價無效，試打已停止。')
            key=(day,sym)
            if key in seen:
                raise MarketFeedError('股價庫存在重複的交易日，試打已停止。')
            seen.add(key)
            records.append({'date':pd.Timestamp(day),'stock':sym,'ratio':price})
    if not records:
        raise MarketFeedError('指定期間內沒有已儲存的歷史股價。')
    frame=pd.DataFrame.from_records(records)
    panel=frame.pivot(index='date',columns='stock',values='ratio')
    for s in symbols:
        if s not in panel.columns:
            raise MarketFeedError(f'{s} 在指定期間沒有可用歷史股價，請改選日期或代號。')
    common=panel.dropna()
    if len(common)<2:
        raise MarketFeedError('連結標的少於兩個共同有效交易日，不能試算。')
    return frame.sort_values(['date','stock']).reset_index(drop=True),MarketQuoteMeta(
        provider='Google Sheets 股價庫（GOOGLEFINANCE 來源固定數值）',
        adjustment='歷史收盤價；拆股及股息調整口徑尚待逐檔確認',
        first_date=frame.date.min().date(),last_date=frame.date.max().date(),
        symbol_count=len(symbols),observed_common_days=len(common),
        freshness='資料庫最近更新日；不是即時行情',
    )


def fetch_sheet_closes(symbols:tuple[str,...],start:date,end:date,
                        service_account_info:dict,price_sheet_id:str):
    """Use the existing app read-only SheetsReader for an independent sheet."""
    symbols=tuple(str(s).strip().upper() for s in symbols)
    if not 1<=len(symbols)<=5 or len(set(symbols))!=len(symbols):
        raise MarketFeedError('請輸入一至五檔不重複股票。')
    if not isinstance(price_sheet_id,str) or not ID_RE.fullmatch(price_sheet_id):
        raise MarketFeedError('尚未設定 V8.4 股價資料庫 ID：請檢查 Secrets [price_library] sheet_id。')
    if not service_account_info:
        raise MarketFeedError('尚未設定 Google 唯讀服務帳號；請在測試站 Secrets 設定 [gcp_service_account]。')
    if not isinstance(start,date) or not isinstance(end,date) or start>end:
        raise MarketFeedError('日期區間無效。')
    try:
        reader=SheetsReader.from_secrets(service_account_info,price_sheet_id)
        header_data=reader.read(price_sheet_id,f"'{PRICE_TAB}'!A1:UK1")
        if not header_data:
            raise MarketFeedError('股價矩陣缺少股票表頭。')
        headers=[str(h).strip().upper() for h in header_data[0]]
        if not headers or headers[0]!='交易日期':
            raise MarketFeedError('股價資料庫格式不符，找不到交易日期欄。')
        cols=[]
        for s in symbols:
            if s not in headers:
                raise MarketFeedError('股價庫尚未收錄 ' + s + ' 的歷史價格。')
            cols.append(headers.index(s))
        ranges=[f"'{PRICE_TAB}'!A2:A800"]+[f"'{PRICE_TAB}'!{column_name(i)}2:{column_name(i)}800" for i in cols]
        values=reader.read_many(ranges)
    except SheetConnectionError as exc:
        # SheetsReader provides credential-free error messages.
        raise MarketFeedError(str(exc)) from None
    return parse_matrix_rows(symbols,headers,values[1:],values[0],start,end)

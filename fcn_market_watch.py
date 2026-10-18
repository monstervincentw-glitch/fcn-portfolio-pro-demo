"""Read-only FCN chart snapshot. No external quotes, no contractual event assertions."""
from __future__ import annotations
import datetime as dt
import math
import pandas as pd


def _threshold(value):
    try:
        if value is None or str(value).strip() == '':
            return None
        v = float(str(value).replace('%','').replace(',',''))
        return v if math.isfinite(v) and 0 < v <= 300 else None
    except (TypeError, ValueError):
        return None


def summarize_chart(frame, settings, *, value_column, asof=None, stale_days=3):
    """Summarize explicitly identified 100-based observations, not live quotes.

    Normalization contract: 100 = fixing price, 85 = 85% of fixing price.
    Never guess the numeric value column, thresholds, or business-day calendar.
    """
    asof = asof or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    if value_column not in frame.columns:
        raise ValueError('所選的相對價格欄位不存在')
    if not {'date','stock'}.issubset(frame.columns):
        raise ValueError('圖表需有 date、stock 欄位')
    df = frame[['date','stock',value_column]].copy()
    df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.date
    df['stock'] = df['stock'].astype(str).str.strip()
    df['level'] = pd.to_numeric(df[value_column], errors='coerce')
    df = df.dropna(subset=['date','level'])
    df = df[(df['stock'] != '') & (df['level'] > 0) & (df['level'] <= 10000) & (df['date'] <= asof)]
    df = df.sort_values(['stock','date']).drop_duplicates(['stock','date'],keep='last')
    if df.empty:
        return [], {'worst':None,'asof':None,'warnings':['沒有截至評估日的有效相對價格資料']}
    names = df['stock'].unique().tolist()
    if len(names)>5:
        raise ValueError('單筆 FCN 最多支援 5 檔標的；請核對圖表所屬商品')
    ki,ko,strike = (_threshold((settings or {}).get(k)) for k in ('ki','ko','strike'))
    latest = df.groupby('stock', sort=True).tail(1).sort_values('level')
    rows=[]; warnings=[]
    for _, r in latest.iterrows():
        age=(asof-r['date']).days
        rows.append({'股票':r['stock'],'最新資料日':r['date'].isoformat(),'相對期初價格%':round(float(r['level']),2),
                     '距KI百分點':round(float(r['level'])-ki,2) if ki is not None else None,
                     '距KO百分點':round(float(r['level'])-ko,2) if ko is not None else None,
                     '距Strike百分點':round(float(r['level'])-strike,2) if strike is not None else None,
                     '資料超過門檻天數':age>stale_days})
        if age>stale_days: warnings.append(f'{r["stock"]} 最後一筆距今 {age} 個日曆天（包含非交易日）')
    if len({r['最新資料日'] for r in rows})>1:
        warnings.append('各標的最新資料日不同；Worst-of 是異步快照，不是同日比較')
    if ki is None or ko is None or strike is None:
        warnings.append('KI／KO／Strike 存在缺漏或無法解析的門檻，對應距離不顯示')
    warnings.append('僅為 Sheets Chart 觀測值；KO 須依合約觀察日及條件，KI 須依連續／收盤／到期等實際條款確認')
    return rows, {'worst':rows[0]['相對期初價格%'], 'worst_stock':rows[0]['股票'],
                  'asof':max(r['最新資料日'] for r in rows),'warnings':warnings,
                  'stale':any(r['資料超過門檻天數'] for r in rows), 'thresholds':{'ki':ki,'ko':ko,'strike':strike}}

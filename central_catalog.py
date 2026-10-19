"""FCN product terms: central parameters; historical closes: existing 526-stock library.

Do not copy stock closes into the central product workbook. The read-only LIVE
site shares the stock library with the unchanged historical trial. Customer
holdings come only from the protected customer ledger. No old V2 product sheets.
"""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass
from math import isfinite
from typing import Any

CENTRAL_CATALOG_ID = '1peKhu1Nt8UuCiCnajGqC9bT_GXyL3qCzQBO3z-VzzOI'
# EXACT same ID/tab as the existing price_library_trial.py used by historical trial.
STOCK_LIBRARY_ID = '1ef0Whr7-bgj37DdOnC7ug8Dyv5Ab92-AMw5n9V18UJY'
STOCK_PRICE_TAB = '收盤價矩陣'
TAIPEI = dt.timezone(dt.timedelta(hours=8))
PRODUCT_RANGE = "'API_商品條款_V1'!A1:X150"
LEGS_RANGE = "'API_標的_V1'!A1:M501"
PERIOD_RANGE = "'配息期'!A1:I1201"
CALENDAR_RANGE = "'市場休市日'!A1:C400"
INPUT_RANGE = "'商品完整參數輸入'!A1:CJ101"
REQUIRED_PRODUCTS = {'product_id','currency','pricing_date','annual_coupon_rate'}
REQUIRED_LEGS = {'product_id','leg_no','ticker','initial_price'}

class CatalogSchemaError(ValueError):
    pass

@dataclass(frozen=True)
class Catalog:
    products: dict[str,dict[str,Any]]
    legs: dict[str,tuple[dict[str,Any],...]]


def _today_taipei():
    return dt.datetime.now(TAIPEI).date()


def parse_table(values, required):
    if not values: raise CatalogSchemaError('中央參數庫無標題列')
    header=[str(x or '').strip() for x in values[0]]
    nonempty=[x for x in header if x]
    if len(set(nonempty)) != len(nonempty): raise CatalogSchemaError('中央參數庫欄位重複')
    missing=set(required)-set(header)
    if missing: raise CatalogSchemaError('中央庫缺少欄位：'+','.join(sorted(missing)))
    out=[]
    for row in values[1:]:
        values_ = list(row) + [None]*(len(header)-len(row))
        item={key:values_[i] for i,key in enumerate(header) if key}
        if str(item.get('product_id') or '').strip(): out.append(item)
    return out


def parse_catalog(p_values,l_values):
    products={}
    for p in parse_table(p_values,REQUIRED_PRODUCTS):
        pid=str(p['product_id']).strip()
        if pid in products: raise CatalogSchemaError('商品代號重複：'+pid)
        products[pid]=p
    legs={pid:[] for pid in products}
    unique=set()
    for raw in parse_table(l_values,REQUIRED_LEGS):
        pid=str(raw['product_id']).strip()
        if pid not in products: continue
        sym=str(raw.get('ticker') or '').strip().upper()
        if not sym: continue
        try: pos=int(raw['leg_no'])
        except (ValueError,TypeError,OverflowError): raise CatalogSchemaError('連結標的序號無效：'+pid) from None
        if pos<1 or pos>5 or (pid,pos) in unique: raise CatalogSchemaError('連結標的重複或超過五檔：'+pid)
        unique.add((pid,pos))
        legs[pid].append({**raw,'ticker':sym,'leg_no':pos})
    return Catalog(products,{key:tuple(sorted(ls,key=lambda l:l['leg_no'])) for key,ls in legs.items()})


def load_catalog(reader, sheet_id=CENTRAL_CATALOG_ID):
    return parse_catalog(reader.read(sheet_id,PRODUCT_RANGE),reader.read(sheet_id,LEGS_RANGE))


def to_day(value):
    if isinstance(value,dt.datetime): return value.date()
    if isinstance(value,dt.date): return value
    if isinstance(value,(int,float)) and not isinstance(value,bool) and 20000<float(value)<110000:
        return (dt.date(1899,12,30)+dt.timedelta(days=int(value)))
    if isinstance(value,str) and value.strip():
        try: return dt.date.fromisoformat(value.strip()[:10].replace('/','-'))
        except ValueError: return None
    return None


def as_positive_number(value):
    if value is None or isinstance(value,bool): return None
    try:
        x=float(str(value).strip().replace(',',''))
        return x if isfinite(x) and x>0 else None
    except (ValueError,TypeError,OverflowError): return None


def sheet_column(index):
    if index<0: raise ValueError('negative col index')
    n=index+1;result=''
    while n:
        n,rem=divmod(n-1,26)
        result=chr(65+rem)+result
    return result


def load_market_matrix(reader, tickers=None, sheet_id=STOCK_LIBRARY_ID):
    """Read *existing* 526-stock matrix, only columns used by central FCNs.

    One stock price library feeds the historical trial and FCN portfolio.
    Dates are aligned to original matrix rows; empty closes remain missing.
    No GOOGLEFINANCE execution, write operation or duplicate market table.
    """
    header_rows=reader.read(sheet_id,f"'{STOCK_PRICE_TAB}'!A1:TJ1")
    if not header_rows or not header_rows[0] or str(header_rows[0][0]).strip()!='交易日期':
        raise CatalogSchemaError('成分股股價庫日期欄或標題列錯誤')
    labels=[str(x or '').strip().upper() for x in header_rows[0]]
    while labels and not labels[-1]:
        labels.pop()  # Ignore only trailing blank columns.
    if any(not v for v in labels):
        raise CatalogSchemaError('成分股股價庫標題列中間有空欄，不可錯位讀價')
    if len(set(labels))!=len(labels):
        raise CatalogSchemaError('成分股股價庫出現重複股票代號')
    included=set(labels[1:])
    requested=sorted(set(str(t or '').strip().upper() for t in (tickers or ()) if t))
    # Explicit symbols ensure the routine cannot accidentally fetch 526*all rows.
    if tickers is None:
        requested=list(labels[1:])
    raw_dates=reader.read(sheet_id,f"'{STOCK_PRICE_TAB}'!A2:A")
    dates=[]
    for row in raw_dates:
        day=to_day(row[0] if row else None)
        if day is None:
            if row and row[0] not in (None,''):
                raise CatalogSchemaError('成分股股價庫出現無效交易日期')
            # Preserve row offset; do not shift all later dates if a gap exists.
            dates.append(None)
        else:
            dates.append(day)
    valid=[x for x in dates if x is not None]
    if not valid or valid!=sorted(set(valid)):
        raise CatalogSchemaError('成分股股價庫交易日期重複或排序錯誤')
    today=_today_taipei()
    market={day:{} for day in valid if day<=today}
    endrow=len(dates)+1
    for symbol in requested:
        if symbol not in included:
            continue
        column=sheet_column(labels.index(symbol))
        values=reader.read(sheet_id,f"'{STOCK_PRICE_TAB}'!{column}2:{column}{endrow}")
        for i,day in enumerate(dates):
            if day not in market:
                continue
            cell=values[i][0] if i<len(values) and values[i] else None
            market[day][symbol]=as_positive_number(cell)
    latest=max(market,default=None)
    return market,latest,included


def load_holidays(reader,sheet_id=CENTRAL_CATALOG_ID):
    rows=reader.read(sheet_id,CALENDAR_RANGE)
    if not rows or not rows[0] or str(rows[0][0]).strip()!='休市日期':
        raise CatalogSchemaError('中央市場休市日分頁缺少「休市日期」標題')
    holiday=set()
    for r in rows[1:]:
        day=to_day(r[0] if r else None)
        if day: holiday.add(day)
    if not holiday: raise CatalogSchemaError('中央市場休市日尚未建立')
    return holiday


def load_periods(reader,sheet_id=CENTRAL_CATALOG_ID):
    rows=reader.read(sheet_id,PERIOD_RANGE)
    if not rows or not rows[0] or rows[0][1:3]!=['商品代號','配息期']:
        raise CatalogSchemaError('中央配息期表頭異動')
    groups={}
    for row in rows[1:]:
        if len(row)<3: continue
        pid=str(row[1] or '').strip()
        if not pid: continue
        try: ix=int(row[2])
        except (ValueError,TypeError): continue
        groups.setdefault(pid,[]).append((ix,to_day(row[3] if len(row)>3 else None),
                                            to_day(row[4] if len(row)>4 else None),
                                            to_day(row[5] if len(row)>5 else None)))
    return {pid:sorted(v) for pid,v in groups.items()}


def load_input_rules(reader,sheet_id=CENTRAL_CATALOG_ID):
    rows=reader.read(sheet_id,INPUT_RANGE)
    if not rows or not rows[0] or rows[0][0]!='商品代號':
        raise CatalogSchemaError('中央原始輸入欄位異動')
    headers=[str(s or '').strip() for s in rows[0]]
    rules={}
    for row in rows[1:]:
        pid=str(row[0] or '').strip() if row else ''
        if not pid: continue
        record={h:row[j] if j<len(row) else None for j,h in enumerate(headers) if h}
        rules[pid]=record
    return rules


def load_history(reader,tickers,sheet_id=STOCK_LIBRARY_ID):
    requested=sorted(set(str(s or '').strip().upper() for s in tickers if s))
    market,_,symbols=load_market_matrix(reader,requested,sheet_id)
    missing=[s for s in requested if s not in symbols]
    data=[{'date':day,'stock':sym,'close':p}
          for day,row in market.items() for sym in requested
          if (p:=row.get(sym)) is not None]
    return data,missing


def barriers_for_chart(p):
    def pct(key):
        v=as_positive_number(p.get(key))
        return v*100 if v is not None and v<=2 else v if v is not None and v<=200 else None
    kind=str(p.get('ki_type') or '').upper()
    return {'ko':pct('ko_barrier_ratio'),'strike':pct('strike_ratio'),
            'ki':None if 'NON-KI' in kind else pct('ki_barrier_ratio'),
            'ko_start':to_day(p.get('ko_start_date'))}


def history_as_relative(points,legs,product):
    initial={p['ticker']:as_positive_number(p.get('initial_price')) for p in legs}
    start=to_day(product.get('pricing_date'));end=to_day(product.get('final_eval_date'))
    return [{'date':r['date'],'stock':r['stock'],'ratio':r['close']/initial[r['stock']]*100}
            for r in points if initial.get(r['stock']) and (not start or r['date']>=start)
            and (not end or r['date']<=end)]


def verified_for_barriers(product,legs,latest_date,today=None):
    """Backward-compatible API name. Checks only numerical completeness/freshness.
    The function deliberately NEVER checks bank approval or quote review fields.
    """
    today=today or _today_taipei()
    return (bool(legs) and latest_date is not None and 0<=(today-latest_date).days<=5
            and all(as_positive_number(l.get('initial_price')) for l in legs))

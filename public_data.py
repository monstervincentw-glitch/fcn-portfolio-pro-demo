"""Credential-free, server-side reader for public research only."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

SOURCE = 'https://growth-observatory-manyface.huedcow4.chatgpt.site'
DASHBOARD_URL = SOURCE + '/api/dashboard'
MAX_BYTES = 8 * 1024 * 1024
STOCK_FIELDS = ('key', 'market', 'symbol', 'name', 'industry', 'benchmark', 'currency',
                'priceDate', 'close', 'history', 'financial', 'features', 'rankScore',
                'observedAt', 'sourceQuality', 'integrity', 'sourceError', 'evaluation')
FINANCIAL_FIELDS = ('financial_status', 'revenue_growth', 'quarterly_growth',
                    'operating_margin', 'cfo_margin', 'financial_age_days',
                    'latest_period', 'max_input_filed', 'financial_event_date',
                    'date_basis', 'prior_release_growth', 'prior_release_margin')
FEATURE_FIELDS = ('history_sessions', 'dollar_volume', 'drawdown_126', 'relative_63',
                  'market_cap_estimate', 'price_sales')
EVALUATION_FIELDS = ('fundamental', 'funding', 'tradable', 'divergence', 'fresh',
                     'primary', 'buy_hold', 'reasons', 'fundamentalReasons')
MACRO_FIELDS = ('status', 'macro_stress', 'macro_vintage_date', 'observedAt',
                'marketAsOf', 'sourceError')
JOB_FIELDS = ('id', 'market', 'status', 'cursor', 'total', 'updated', 'failed',
              'errors', 'created_at', 'updated_at')


def project(obj, fields):
    return {key: obj[key] for key in fields if key in obj}


def public_projection(raw):
    """Allowlist output even if an upstream response unexpectedly contains identity data."""
    if raw.get('storageReady') is not True:
        raise ValueError('原站資料庫未就緒；停止顯示新的買入候選')
    if not isinstance(raw.get('instruments'), list) or not raw['instruments']:
        raise ValueError('公開資料格式不完整')
    stocks = []
    for item in raw['instruments']:
        if item.get('market') not in ('US', 'TW') or not item.get('key'):
            raise ValueError('公開標的格式不完整')
        stock = project(item, STOCK_FIELDS)
        stock['financial'] = project(item.get('financial', {}), FINANCIAL_FIELDS)
        stock['features'] = project(item.get('features', {}), FEATURE_FIELDS)
        stock['evaluation'] = project(item.get('evaluation', {}), EVALUATION_FIELDS)
        stock['history'] = [project(v, ('date', 'close')) for v in item.get('history', [])][-90:]
        stocks.append(stock)
    if len({i['key'] for i in stocks}) != len(stocks):
        raise ValueError('標的代碼重複，停止顯示訊號')
    return {
        'instruments': stocks,
        'macros': {m: project(raw.get('macros', {}).get(m, {}), MACRO_FIELDS) for m in ('US', 'TW')},
        'jobs': [project(j, JOB_FIELDS) for j in raw.get('jobs', [])],
        'serverTime': raw.get('serverTime'),
    }


def load_dashboard():
    # No cookies, user IDs, tokens, private endpoints, or client-side source requests.
    req = Request(DASHBOARD_URL, headers={'Accept': 'application/json',
                  'User-Agent': 'GrowthObservatory-Streamlit/1.0'})
    with urlopen(req, timeout=15) as response:
        raw_bytes = response.read(MAX_BYTES + 1)
    if len(raw_bytes) > MAX_BYTES:
        raise ValueError('來源回應過大')
    raw = json.loads(raw_bytes)
    timestamp = datetime.fromisoformat(str(raw.get('serverTime', '')).replace('Z', '+00:00'))
    age = (datetime.now(timezone.utc) - timestamp).total_seconds()
    if age < -300 or age > 1200:
        raise ValueError('來源回應時間過舊或異常；停止顯示新的買入候選')
    return public_projection(raw)


def classification(stock):
    e = stock.get('evaluation', {})
    if stock.get('sourceError') or not stock.get('integrity') or not e.get('fresh'):
        return '資料待核對'
    if e.get('primary'):
        return '合格候選'
    return '未達策略條件'


def eligible(stock, strategy):
    return classification(stock) == '合格候選' and stock.get('evaluation', {}).get(strategy) is True


def sorted_candidates(stocks, strategy):
    return sorted((s for s in stocks if eligible(s, strategy)),
                  key=lambda s: (-(s.get('rankScore') or 0), s['symbol']))

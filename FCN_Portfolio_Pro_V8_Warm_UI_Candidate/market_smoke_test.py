"""One-call opt-in live connectivity probe (local/admin only).

Run only after market-data commercial terms are independently approved:
  export MASSIVE_API_KEY='...'
  export MARKET_LICENSE_APPROVED='true'
  python market_smoke_test.py

Never prints the token, customer data, or vendor raw response.
"""
from __future__ import annotations
import os
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from datetime import datetime
from market_data import fetch_daily_closes, MarketFeedError


def main() -> int:
    if os.getenv('MARKET_LICENSE_APPROVED', '').strip().lower() != 'true':
        print('未執行連線：先確認行情公司的商業資料使用授權。')
        return 2
    token = os.getenv('MASSIVE_API_KEY', '')
    if not token:
        print('未執行連線：未在本機環境變數 MASSIVE_API_KEY 設定 API Key。')
        return 2
    exchange_today = datetime.now(ZoneInfo('America/New_York')).date()
    end = exchange_today - timedelta(days=1)  # request completed daily bars only
    start = end - timedelta(days=20)
    try:
        bars, meta = fetch_daily_closes(('AAPL',), start, end, token)
    except MarketFeedError as exc:
        print('連線檢查未通過：' + str(exc))
        return 1
    # Metadata only, no sensitive input or secret output.
    print(f'連線成功 | AAPL | {meta.first_date} 至 {meta.last_date} | 交易日 {meta.observed_common_days} | {meta.freshness}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

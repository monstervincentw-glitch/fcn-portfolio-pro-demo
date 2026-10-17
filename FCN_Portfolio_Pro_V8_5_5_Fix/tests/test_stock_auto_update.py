"""Unit tests of the daily automatic updater; do not require live Sheets credentials."""
import datetime as dt
import math
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from tools import update_stock_prices as upd


class PriceUpdaterTests(unittest.TestCase):
    def test_excel_col(self):
        self.assertEqual(upd.a1_column(0), 'A')
        self.assertEqual(upd.a1_column(26), 'AA')
        self.assertEqual(upd.a1_column(526), 'TG')

    def test_market_cutoff_and_weekends(self):
        ny = ZoneInfo('America/New_York')
        self.assertEqual(upd.expected_last_day(dt.datetime(2026,10,19,19,0,tzinfo=ny)),dt.date(2026,10,18))
        self.assertEqual(upd.expected_last_day(dt.datetime(2026,10,19,23,0,tzinfo=ny)),dt.date(2026,10,19))
        self.assertEqual(upd.weekdays_after(dt.date(2026,10,16),dt.date(2026,10,19)),[dt.date(2026,10,19)])
        self.assertIn(dt.date(2026,11,26),upd.us_market_holidays(2026))
        self.assertIn(dt.date(2026,4,3),upd.us_market_holidays(2026))

    def test_formula_safety(self):
        self.assertIn('GOOGLEFINANCE("AAPL"', upd.formula('AAPL',dt.date(2026,10,19)))
        with self.assertRaises(ValueError):
            upd.formula('AAPL";IMPORTRANGE(',dt.date(2026,10,19))

    def test_parse_quotes_exact_date_only(self):
        date=dt.date(2026,10,19)
        serial=(date-dt.date(1899,12,30)).days
        matrix=[['Date','Close','','Date','Close'],[serial,142.2,'',serial-1,195.1]]
        self.assertEqual(upd.extract_quotes(matrix,['A','AAPL'],date),{'A':142.2})
        self.assertIsNone(upd.valid_close('#N/A'))
        self.assertIsNone(upd.valid_close(float('nan')))

    def test_no_new_days_leaves_existing_data_unchanged(self):
        class NoWrite:
            def values(self,range_):
                if range_=="'收盤價矩陣'!A1:TJ1": return [['交易日期']+['T'+str(i) for i in range(526)]]
                return [['2026-10-16']]
        with patch.object(upd,'check_headings',return_value=['AAPL']*526):
            # validation stub returns stock universe, no requests to update
            upd.run(NoWrite(),dt.datetime(2026,10,17,12,tzinfo=dt.timezone.utc))

    def test_sheet_api_builds_correct_batch_endpoint(self):
        class Response:
            ok=True
            status_code=200
            content=b'{}'
            def json(self):return {}
        class Session:
            def __init__(self):self.called=None
            def request(self,method,url,**kwargs):
                self.called=(method,url);return Response()
        sess=Session();api=upd.SheetAPI(sess)
        api.request('POST',':batchUpdate',payload={'requests':[]})
        self.assertTrue(sess.called[1].endswith('/spreadsheets/'+upd.PRICE_LIBRARY_ID+':batchUpdate'))


if __name__=='__main__': unittest.main()

class PriceUpdaterIntegrationTest(unittest.TestCase):
    def test_append_new_day_and_idempotent_retry(self):
        # Fake Google Sheets client verifies the intended data changes, never
        # connects to an external spreadsheet.
        class FakeAPI:
            def __init__(self):
                self.dates=[dt.date(2026,10,16)]
                self.symbols=['AAPL'] + ['T'+str(i).zfill(4) for i in range(525)]
                self.out=[];self.logs=[];self.grid=[]
            def values(self,key):
                if key=="'收盤價矩陣'!A1:TJ1":return [['交易日期']+self.symbols]
                if key=="'收盤價矩陣'!A2:A":return [[d.isoformat()] for d in self.dates]
                if key.startswith("'收盤價矩陣'!A3:B3"):
                    return [[self.dates[-1].isoformat(),1.0]]
                if key=="'逐檔匯入進度'!A2:G":
                    return [[s,'完成',701,'2024-01-02','2026-10-16','GOOGLEFINANCE',''] for s in self.symbols]
                if key=="'行情總覽'!B9":return [[364137]]
                raise AssertionError(key)
            def ensure_grid(self,*args):self.grid.append(args)
            def write_many(self,data):
                self.out.extend(data)
                self.dates.append(dt.date.fromisoformat(data[0][1][0][0]))
            def append(self,range_,row):self.logs.append((range_,row))
        api=FakeAPI()
        def quotes(client, day, symbols):
            return {s:170.50 for s in symbols}
        with patch.object(upd,'get_quotes',side_effect=quotes):
            upd.run(api, dt.datetime(2026,10,20,3,15,tzinfo=dt.timezone.utc))
            self.assertEqual(api.dates[-1],dt.date(2026,10,19))
            self.assertEqual(len(api.out[0][1][0]),527)
            self.assertEqual(api.out[0][1][0][0],'2026-10-19')
            self.assertEqual(api.out[0][1][0][1],170.5)
            self.assertEqual(len(api.logs),1)
            self.assertEqual(api.logs[0][1][4],526)
            upd.run(api,dt.datetime(2026,10,20,3,15,tzinfo=dt.timezone.utc))
            self.assertEqual(len(api.logs),1)


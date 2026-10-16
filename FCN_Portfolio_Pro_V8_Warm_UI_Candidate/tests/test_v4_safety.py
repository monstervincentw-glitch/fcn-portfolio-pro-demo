import unittest
import datetime as dt
import pandas as pd
from virtual_trial import TrialInputs, simulate_history, TrialDataError
from demo_charts import chart_sheet_rows

class V4Regression(unittest.TestCase):
    def params(self):
        return TrialInputs(symbols=('AMD','NVDA'),start_month=dt.date(2026,5,1),term_months=3,lockup_months=1,annual_coupon_pct=20)

    def test_long_missing_middle_is_not_passed_as_no_knockout(self):
        dates = pd.bdate_range('2026-05-01','2026-09-01')
        rows=[{'date':d,'stock':t,'ratio':100 if d==dates[0] else 90} for d in dates if not ('2026-07-01' <= str(d.date()) <= '2026-07-21') for t in ('AMD','NVDA')]
        with self.assertRaisesRegex(TrialDataError,'缺價'):
            simulate_history(pd.DataFrame(rows),self.params(),as_of='2026-10-17')

    def test_partial_history_remains_pending_not_falsely_final(self):
        dates=pd.bdate_range('2026-05-01','2026-06-30')
        rows=[{'date':d,'stock':t,'ratio':100 if d==dates[0] else 90} for d in dates for t in ('AMD','NVDA')]
        result=simulate_history(pd.DataFrame(rows),self.params(),as_of='2026-10-17')
        self.assertIsNone(result['total_return_pct'])

    def test_marker_is_not_a_stock_and_stock_rows_survive(self):
        dates=pd.bdate_range('2026-05-12','2026-08-19')
        raw=[['日期','NVDA','AMD','MU','','','KO','執行價','KI','KO觀察起日']]
        for k,d in enumerate(dates):
            serial=(d - pd.Timestamp('1899-12-30')).days
            raw.append([serial,100 + k*.2,100 + k*.4,100 + k*.1,None,None,100,70,'#N/A',130 if str(d.date())=='2026-06-22' else '#N/A'])
        data, meta=chart_sheet_rows(raw)
        self.assertEqual(set(data.stock.unique()),{'NVDA','AMD','MU'})
        self.assertEqual(len(data),len(dates)*3)
        self.assertEqual(str(meta['ko_start'].date()),'2026-06-22')
        self.assertAlmostEqual(meta['strike'],70)

if __name__=='__main__': unittest.main()

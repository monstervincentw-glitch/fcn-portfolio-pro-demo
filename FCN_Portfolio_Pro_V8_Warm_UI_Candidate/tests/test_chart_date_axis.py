"""Regression checks for the exact SQ29 KO observation annotation behavior."""
import datetime as dt
import unittest
import pandas as pd
from demo_charts import chart_sheet_rows, _date

HEADER = ["日期", "NVDA", "AMD", "MU", "", "", "KO", "執行價", "KI", "KO觀察起日"]

class ChartDateAxisRegressionTest(unittest.TestCase):
    def test_sq29_plot_marker_130_is_not_a_date(self):
        # Google Sheets Chart!N11:W: KO observation start appears in W as
        # numeric 130 at the *same ROW* whose N value is 2026/06/22.
        rows = [HEADER,
            [46154, 100, 100, 100, "#N/A ()", "#N/A ()", 100, 70, "#N/A ()", "#N/A ()"],
            [46155, 102.287, 99.378, 104.833, "#N/A ()", "#N/A ()", 100, 70, "#N/A ()", "#N/A ()"],
            [46191, 94.5, 123.1, 158.0, "#N/A ()", "#N/A ()", 100, 70, "#N/A ()", 130],
            [46192, 90.6, 116.0, 137.2, "#N/A ()", "#N/A ()", 100, 70, "#N/A ()", "#N/A ()"],
        ]
        # Use a calculated Sheets serial for 2026-06-22 to avoid a guessed day.
        serial = (pd.Timestamp('2026-06-22') - pd.Timestamp('1899-12-30')).days
        rows[3][0] = serial
        rows[4][0] = serial + 1
        df, meta = chart_sheet_rows(rows)
        self.assertEqual(len(df), 12)
        self.assertEqual(set(df['stock']), {'NVDA','AMD','MU'})
        self.assertTrue(all(df.groupby('stock').size() == 4))
        self.assertTrue(df['date'].between(pd.Timestamp('2026-05-01'), pd.Timestamp('2026-08-31')).all())
        self.assertEqual(meta['ko_start'], pd.Timestamp('2026-06-22'))
        self.assertEqual(meta['ko'], 100.0)
        self.assertEqual(meta['strike'], 70.0)
        self.assertEqual(float(df.loc[(df.stock=='MU') & (df.date==pd.Timestamp('2026-06-22')),'ratio'].iloc[0]),158.0)

    def test_numeric_chart_marker_130_cannot_become_1900_date(self):
        self.assertIsNone(_date(130))
        self.assertIsNone(_date('130'))
        self.assertIsNone(_date(0))
        self.assertIsNone(_date(1.3))
        self.assertIsNone(_date('#N/A ()'))
        self.assertEqual(_date('2026/06/22'), pd.Timestamp('2026-06-22'))

    def test_only_real_marker_row_is_observation_start(self):
        rows = [HEADER,
                ['2026/06/18','95%','120%','145%','','','100%','70%','','#N/A'],
                ['2026/06/22','94.5%','123.1%','158.0%','','','100%','70%','',130],
                ['2026/06/23','90.6%','116.0%','137.2%','','','100%','70%','','#N/A']]
        df, meta = chart_sheet_rows(rows)
        self.assertEqual(meta['ko_start'], pd.Timestamp('2026-06-22'))
        self.assertEqual(df.groupby('stock').size().to_dict(), {'AMD':3, 'MU':3, 'NVDA':3})
        self.assertAlmostEqual(df.ratio.max(), 158.0)

    def test_legacy_date_in_annotation_still_works(self):
        rows = [HEADER,
                ['2026/05/12',1.0,1.0,1.0,'','',1.0,.7,'','2026/06/22'],
                ['2026/05/13',1.02,.95,1.05,'','',1.0,.7,'','']]
        df, meta = chart_sheet_rows(rows)
        self.assertEqual(meta['ko_start'], pd.Timestamp('2026-06-22'))
        self.assertEqual(meta['ko'],100)
        self.assertEqual(len(df),6)

if __name__=='__main__': unittest.main()

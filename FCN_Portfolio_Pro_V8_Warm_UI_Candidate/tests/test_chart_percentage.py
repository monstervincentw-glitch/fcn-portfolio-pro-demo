import math
import unittest

from demo_charts import chart_sheet_rows, demo_chart

HEADER = ["日期", "NVDA", "AMD", "MU", "", "", "KO", "執行價", "KI", "KO觀察起日"]

class ChartPercentageTest(unittest.TestCase):
    def test_sq29_values_are_not_multiplied_twice(self):
        data = [HEADER,
                [46154, 100.0, 100.0, 100.0, "#N/A", "#N/A", 100.0, 70.0, "#N/A", "#N/A"],
                [46155, 102.287344868, 99.377635013, 104.833155052, "#N/A", "#N/A", 100.0, 70.0, "#N/A", "#N/A"]]
        df, meta = chart_sheet_rows(data)
        self.assertEqual(len(df), 6)
        self.assertEqual(set(df['stock']), {'NVDA', 'AMD', 'MU'})
        self.assertAlmostEqual(float(df.loc[(df.stock == 'NVDA') & (df.date == df.date.min()), 'ratio'].iloc[0]), 100.0)
        self.assertAlmostEqual(float(df['ratio'].max()), 104.833155052)
        self.assertEqual(meta['ko'], 100.0)
        self.assertEqual(meta['strike'], 70.0)
        self.assertIsNone(meta['ki'])

    def test_fractional_numbers_are_scaled_once(self):
        data = [HEADER,
                [46154, 1.0, 1.0, 1.0, '', '', 1.0, .7, .6, 46180],
                [46155, 1.02, .97, 1.14, '', '', 1.0, .7, .6, '']]
        df, meta = chart_sheet_rows(data)
        self.assertEqual(len(df), 6)
        self.assertAlmostEqual(df['ratio'].max(), 114.0)
        self.assertEqual(meta['ko'], 100.0)
        self.assertEqual(meta['strike'], 70.0)
        self.assertEqual(meta['ki'], 60.0)
        self.assertIsNotNone(meta['ko_start'])

    def test_display_percent_strings_and_numeric_mix(self):
        data = [HEADER,
                ['2026/05/12', '100.0%', '100%', '100%', '', '', '100%', '70%', '#N/A', ''],
                ['2026/05/13', 102.3, '99.4%', 104.8, '', '', 100, 70, '', '']]
        df, meta = chart_sheet_rows(data)
        self.assertEqual(len(df), 6)
        self.assertAlmostEqual(df['ratio'].max(), 104.8)
        self.assertEqual(meta['strike'], 70.0)

    def test_low_percentage_does_not_turn_into_150_percent(self):
        data = [HEADER,
                [46154, 100, None, None, '', '', 100, 70, '', ''],
                [46155, 90, None, None, '', '', 100, 70, '', ''],
                [46156, 1.5, None, None, '', '', 100, 70, '', '']]
        df, _ = chart_sheet_rows(data)
        self.assertEqual(df.loc[df.date == df.date.max(), 'ratio'].iloc[0], 1.5)

    def test_no_data_returns_empty(self):
        df, meta = chart_sheet_rows([HEADER, [46154, '#N/A', None]])
        self.assertTrue(df.empty)
        self.assertIsNone(meta)

    def test_demo_remains_available(self):
        df, meta = demo_chart('DEMO01')
        self.assertFalse(df.empty)
        self.assertTrue(50 < df.ratio.min() < 200)
        self.assertEqual(meta['ko'], 100)

if __name__ == '__main__':
    unittest.main()

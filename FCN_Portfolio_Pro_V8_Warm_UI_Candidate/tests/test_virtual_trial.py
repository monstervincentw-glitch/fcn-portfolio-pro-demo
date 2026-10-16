"""Synthetic historical observations: never deploy sample prices as market facts."""
import datetime as dt
import unittest

import pandas as pd

from virtual_trial import (TrialDataError, TrialInputs, choose_available_series,
                           parse_month, parse_symbols, simulate_history)


def prices(start='2026-05-12', end='2026-08-20', when_ko=None, final_worst=None):
    dates = pd.bdate_range(start, end)
    arr=[]
    for i, d in enumerate(dates):
        if i == 0:
            vals=(100.0,100.0,100.0)
        elif when_ko and d >= pd.Timestamp(when_ko):
            vals=(101.44,107.82,114.48)
        elif final_worst is not None and d == dates[-1]:
            vals=(final_worst,80.0,90.0)
        else:
            vals=(94.5,123.1,158.0)
        for ticker,value in zip(('NVDA','AMD','MU'),vals):
            arr.append({'date':d,'stock':ticker,'ratio':value})
    return pd.DataFrame(arr)


class TrialRegression(unittest.TestCase):
    def get_params(self, **kwargs):
        args=dict(symbols=('NVDA','AMD','MU'),start_month=dt.date(2026,5,1),term_months=3,
                  lockup_months=1,annual_coupon_pct=23.22,principal=200000.0,ko_pct=100.0,
                  strike_pct=70.0,ki_pct=None,ki_type='Non-KI')
        args.update(kwargs)
        return TrialInputs(**args)

    def test_symbol_input_requires_max_five(self):
        self.assertEqual(parse_symbols(' amd，MU, nvda AMD '),('AMD','MU','NVDA'))
        with self.assertRaises(TrialDataError):parse_symbols('A,B,C,D,E,F')
        with self.assertRaises(TrialDataError):parse_symbols('')

    def test_month_text_only(self):
        self.assertEqual(parse_month('2026-05'),dt.date(2026,5,1))
        with self.assertRaises(TrialDataError):parse_month('2026-05-19')

    def test_daily_ko_not_monthly(self):
        result=simulate_history(prices(when_ko='2026-08-07'),self.get_params(),as_of='2026-10-17')
        self.assertEqual(result['pricing_date'],dt.date(2026,5,12))
        self.assertEqual(result['estimated_issue_date'],dt.date(2026,5,19))
        self.assertEqual(result['ko_date'],dt.date(2026,8,7))
        self.assertEqual(result['principal_return_pct'],100.0)
        self.assertIsNotNone(result['total_profit_amount'])
        self.assertEqual(set(result['chart'].stock),{'AMD','MU','NVDA'})
        self.assertTrue(len(result['observations'])>20)
        self.assertGreater(result['coupon_pct'],0)

    def test_as_of_earlier_does_not_know_future_KO(self):
        result=simulate_history(prices(when_ko='2026-08-07'),self.get_params(),as_of='2026-07-20')
        self.assertIsNone(result['ko_date'])
        self.assertIsNone(result['total_return_pct'])
        self.assertIsNone(result['principal_return_pct'])

    def test_EKI_maturity_can_lose_principal(self):
        df=prices(end='2026-08-19',final_worst=50.0)
        p=self.get_params(ki_type='EKI',ki_pct=65.0,strike_pct=75.0)
        result=simulate_history(df,p,as_of='2026-09-01')
        self.assertIn('到期',result['status'])
        self.assertAlmostEqual(result['principal_return_pct'],100*50/75)
        self.assertTrue(result['total_return_pct']<0)

    def test_no_lookahead_after_sparse_data(self):
        result=simulate_history(prices(end='2026-06-30'),self.get_params(),as_of='2026-10-17')
        self.assertIsNone(result['principal_return_pct'])
        self.assertIsNone(result['total_return_pct'])

    def test_missing_stock_and_duplicate_dates(self):
        df=prices().query("stock != 'AMD'")
        with self.assertRaises(TrialDataError):simulate_history(df,self.get_params(),as_of='2026-10-17')
        df=prices()
        with self.assertRaises(TrialDataError):simulate_history(pd.concat([df,df.head(1)],ignore_index=True),self.get_params(),as_of='2026-10-17')

    def test_lockup_must_be_shorter_than_term(self):
        with self.assertRaises(TrialDataError):self.get_params(lockup_months=3).validate()

    def test_rebase_from_one_source_only(self):
        data=prices()
        only,provenance=choose_available_series([('SQ29',data)],('NVDA','AMD','MU'),dt.date(2026,5,1),3)
        self.assertEqual(set(only.stock),{'NVDA','AMD','MU'})
        self.assertEqual(set(provenance.values()),{'SQ29'})
        with self.assertRaises(TrialDataError):choose_available_series([('SQ29',data)],('NVDA','XYZ'),dt.date(2026,5,1),3)

    def test_missing_first_month_raises(self):
        with self.assertRaises(TrialDataError):simulate_history(prices(start='2026-06-01'),self.get_params(),as_of='2026-10-17')

if __name__=='__main__':unittest.main()

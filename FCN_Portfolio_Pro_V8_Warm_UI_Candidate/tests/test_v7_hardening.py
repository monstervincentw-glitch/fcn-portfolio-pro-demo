import unittest
import pandas as pd
from virtual_trial import TrialInputs, TrialDataError, simulate_history

class TrialCoverageTests(unittest.TestCase):
    def test_sparsely_observed_ko_does_not_yield_definitive_return(self):
        days=pd.bdate_range('2026-01-02','2026-04-01')
        sparse=[d for i,d in enumerate(days) if i%3==0]
        data=pd.DataFrame({'date':sparse,'stock':['NVDA']*len(sparse),'ratio':[100.0]*len(sparse)})
        p=TrialInputs(symbols=('NVDA',),start_month='2026-01',term_months=3,lockup_months=1,annual_coupon_pct=20)
        with self.assertRaisesRegex(TrialDataError,'涵蓋率'):
            simulate_history(data,p,as_of='2026-04-10')

if __name__=='__main__': unittest.main()

import datetime as dt
import unittest
from pathlib import Path
import pandas as pd
from demo_utils import product_group
from risk_monitor import active_product, parse_terms, market_risks
from site_login import pin_matches, can_enter_mode

TODAY = dt.date(2026,10,17)

class ReleaseFixTests(unittest.TestCase):
    def test_active_labels_are_shared(self):
        for state, group in [('📈 執行中','持續監控'),('存續中','存續監控'),('','日常監控')]:
            p={'model_state':state,'monitor_group':group}
            self.assertEqual(product_group(p,TODAY),'日常監控')
            self.assertTrue(active_product(p))

    def test_recently_closed_is_daily_but_not_active_risk(self):
        p={'model_state':'🎊 已提前KO','monitor_group':'結束後三個月追蹤','end_event_date':'2026-09-01'}
        self.assertEqual(product_group(p,TODAY),'日常監控')
        self.assertFalse(active_product(p))

    def test_calendar_month_boundary(self):
        p={'model_state':'已到期','end_event_date':'2026-07-31'}
        self.assertEqual(product_group(p,dt.date(2026,10,31)),'日常監控')
        self.assertEqual(product_group(p,dt.date(2026,11,1)),'歷史歸檔')

    def test_explicit_until_and_missing_dates(self):
        p={'monitor_group':'結束後三個月追蹤','visible_until':'2026-10-16'}
        self.assertEqual(product_group(p,TODAY),'歷史歸檔')
        p.pop('visible_until')
        self.assertEqual(product_group(p,TODAY),'日常監控')

    def test_pending_and_unknown_not_assumed_active(self):
        self.assertEqual(product_group({'model_state':'商品條款待建檔'},TODAY),'待建檔')
        self.assertFalse(active_product({'model_state':'商品條款待建檔'}))
        self.assertEqual(product_group({},TODAY),'其他')

    def test_terms_spacing_and_fullwidth(self):
        for key in ['KI 門檻','KI門檻','ＫＩ　門檻']:
            terms=parse_terms([[key,'70%'],['KI類型','EKI'],['KO開始觀察日','2026-10-20']])
            self.assertEqual(terms['ki'],70)
            self.assertEqual(terms['ki_type'],'EKI')
            self.assertEqual(terms['ko_start'],dt.date(2026,10,20))

    def risks(self, ratios, settings=None, terms=None, date='2026-10-16'):
        frame=pd.DataFrame([{'date':date,'stock':f'T{i}','ratio':v} for i,v in enumerate(ratios)])
        p={'product_id':'TEST','model_state':'執行中','monitor_group':'持續監控'}
        return market_risks([p],[],{'TEST':(frame,settings or {},terms or {})},TODAY)

    def test_chart_ki_visible_without_contract_type(self):
        r=self.risks([80.92,82.51,84.85],{'ki':70})
        self.assertEqual(r['market_count'],3)
        self.assertAlmostEqual(r['observations'][0]['距 KI 百分點'],10.92)
        self.assertEqual(r['observations'][0]['KI 水位 %'],70)
        self.assertEqual(r['near'],0)
        self.assertEqual(r['missing_ki'],[])

    def test_near_below_and_no_trigger_claim(self):
        r=self.risks([69,70,80,80.01],{'ki':70})
        self.assertEqual((r['below'],r['near']),(2,1))
        self.assertIn('不代表已觸發',r['alerts'][0]['預警'])

    def test_contract_precedence(self):
        r=self.risks([79],{'ki':70},{'ki':75,'ki_type':'EKI'})
        self.assertEqual(r['observations'][0]['距 KI 百分點'],4)
        self.assertEqual(r['observations'][0]['KI 來源'],'商品條款')

    def test_explicit_non_ki_does_not_create_false_alert(self):
        r=self.risks([60],{'ki':70},{'ki_type':'Non-KI'})
        self.assertEqual(r['below'],0)
        self.assertEqual(r['missing_ki'],[])
        self.assertIsNone(r['observations'][0]['KI 水位 %'])

    def test_missing_ki_not_silent_zero(self):
        for value in [None,0,float('nan'),float('inf')]:
            r=self.risks([79],{'ki':value})
            self.assertEqual(r['missing_ki'],['TEST/T0'])
            self.assertIsNone(r['observations'][0]['KI 水位 %'])

    def test_stale_future_excluded(self):
        for date in ['2026-10-01','2026-10-18']:
            r=self.risks([60],{'ki':70},date=date)
            self.assertEqual(r['market_count'],0)
            self.assertEqual(r['below'],0)
            self.assertTrue(r['stale'])

    def test_auth_still_fails_closed(self):
        self.assertFalse(pin_matches('12345','123456'))
        self.assertFalse(can_enter_mode('live',False))
        self.assertTrue(pin_matches('123456','123456'))

    def test_image_and_deployment_paths(self):
        from warm_theme import hero_uri
        self.assertTrue(hero_uri().startswith('data:image/jpeg;base64,/9j/'))
        root=Path(__file__).resolve().parents[1]
        self.assertTrue((root/'assets/warm-theme.css').is_file())
        self.assertTrue((root/'.streamlit/config.toml').is_file())
        self.assertTrue((root/'.github/workflows/update_stock_prices.yml').is_file())
        self.assertTrue((root/'tools/update_stock_prices.py').is_file())

if __name__=='__main__': unittest.main()

import copy
import json
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import public_data


def fixture():
    return {
        'storageReady': True,
        'serverTime': datetime.now(timezone.utc).isoformat(),
        'instruments': [{'key':'US:TEST', 'market':'US', 'symbol':'TEST', 'name':'Test stock',
            'priceDate':'2026-11-04', 'close':100, 'rankScore':80, 'integrity':True,
            'sourceError':None, 'history':[{'date':'2026-11-04','close':100}],
            'financial':{'financial_status':'ok','revenue_growth':.2,'operating_margin':.1,'cfo_margin':.2},
            'features':{'drawdown_126':-.2,'relative_63':-.1},
            'evaluation':{'fresh':True,'primary':True,'buy_hold':True,'reasons':[]}}],
        'macros': {m:{'macro_stress':0,'status':'vintage_verified'} for m in ['US','TW']},
        'jobs': [],
    }


class Response:
    def __init__(self, data): self.data=json.dumps(data).encode()
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,n): return self.data[:n]


class DataSafetyTests(unittest.TestCase):
    def test_projection_strips_private_identity_and_nested_fields(self):
        raw=fixture()
        raw.update(holdings=[{'owner_id':'private'}],portfolios=[{'initial_capital':999}],
                   watchlist=['private'],authenticated=True,signedIn=True)
        raw['instruments'][0]['financial']['owner_id']='private'
        raw['instruments'][0]['history'][0]['token']='private'
        result=public_data.public_projection(raw)
        self.assertNotIn('private',json.dumps(result))
        self.assertNotIn('holdings',result)
        self.assertNotIn('authenticated',result)

    def test_quality_error_blocks_old_true_buy_flag(self):
        stock=fixture()['instruments'][0]
        stock['sourceError']='收盤日期未到齊'
        self.assertEqual(public_data.classification(stock),'資料待核對')
        self.assertFalse(public_data.eligible(stock,'primary'))
        self.assertEqual(public_data.sorted_candidates([stock],'buy_hold'),[])

    def test_database_failure_never_displays_seed_candidates(self):
        raw=fixture();raw['storageReady']=False
        with self.assertRaises(ValueError):public_data.public_projection(raw)

    def test_duplicate_instruments_rejected(self):
        raw=fixture();raw['instruments']*=2
        with self.assertRaises(ValueError):public_data.public_projection(raw)

    def test_anonymous_get_and_no_auth_headers(self):
        with patch.object(public_data,'urlopen',return_value=Response(fixture())) as call:
            data=public_data.load_dashboard()
        req=call.call_args.args[0]
        self.assertEqual(req.get_method(),'GET')
        self.assertEqual(req.full_url,public_data.DASHBOARD_URL)
        self.assertFalse(any(k.lower() in ('cookie','authorization','oai-sites-authorization') for k in req.headers))
        self.assertEqual(len(data['instruments']),1)

    def test_stale_server_response_rejected(self):
        raw=fixture();raw['serverTime']=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
        with patch.object(public_data,'urlopen',return_value=Response(raw)):
            with self.assertRaises(ValueError):public_data.load_dashboard()


class StreamlitFlowTests(unittest.TestCase):
    def test_market_strategy_quality_and_research(self):
        from streamlit.testing.v1 import AppTest
        raw=fixture()
        tw=copy.deepcopy(raw['instruments'][0]);tw.update(key='TW:2330',market='TW',symbol='2330',name='台積電',sourceError='來源日期未到齊')
        raw['instruments'].append(tw)
        projected=public_data.public_projection(raw)
        with patch.object(public_data,'load_dashboard',return_value=projected):
            app=AppTest.from_file(str(ROOT/'streamlit_app.py')).run(timeout=30)
            self.assertEqual(len(app.exception),0)
            self.assertEqual(app.metric[1].value,'1')
            app.sidebar.radio[0].set_value('台股 TW').run(timeout=30)
            self.assertEqual(len(app.exception),0)
            self.assertEqual(app.metric[1].value,'0')
            self.assertEqual(app.metric[2].value,'1')
            self.assertTrue(any('資料不足' in str(d.value) for d in app.dataframe))
            app.sidebar.radio[1].set_value('背離長抱策略').run(timeout=30)
            self.assertEqual(len(app.exception),0)

    def test_connection_failure_keeps_research_hides_candidates(self):
        from streamlit.testing.v1 import AppTest
        with patch.object(public_data,'load_dashboard',side_effect=OSError('test connection failure')):
            app=AppTest.from_file(str(ROOT/'streamlit_app.py')).run(timeout=30)
            self.assertEqual(len(app.exception),0)
            self.assertEqual(len(app.metric),0)
            self.assertTrue(any('停止顯示買入候選' in e.value for e in app.error))
            self.assertTrue(any('2016' in str(d.value) for d in app.dataframe))


if __name__=='__main__':unittest.main()

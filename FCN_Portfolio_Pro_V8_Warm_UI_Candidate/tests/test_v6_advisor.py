import sys, unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from advisor_analytics import summarize_portfolio,stock_exposures

class V6Tests(unittest.TestCase):
 def test_chart_has_3_stocks_and_no_barrier_color_domain(self):
  try:
   from chart_render import build_stock_chart
  except ModuleNotFoundError as exc:
   if exc.name == 'altair': self.skipTest('Altair 不在離線容器；線上渲染仍需驗收')
   raise
  dates=pd.bdate_range('2026-05-12',periods=15)
  df=pd.DataFrame([{'date':d,'stock':s,'ratio':100+j+i/3} for i,d in enumerate(dates) for j,s in enumerate(['AMD','MU','NVDA'])])
  spec=build_stock_chart(df,{'ko':100,'strike':70,'ki':None,'ko_start':'2026-05-22'},['AMD','MU','NVDA']).to_dict()
  layers=spec['layer']; self.assertEqual(len(layers),4)
  self.assertEqual(layers[0]['encoding']['color']['scale']['domain'],['AMD','MU','NVDA'])
  self.assertEqual(len(layers[0]['data']['values']),45)
  self.assertTrue(all('encoding' not in layer or 'color' not in layer['encoding'] for layer in layers[1:]))
 def test_unknown_source_flag(self):
  s=summarize_portfolio([],[],[{'source_connection':'已連線'},{'source_connection':'待授權'}]);self.assertEqual(s['missing_sources'],1)
 def test_exposure_is_exact_symbol(self):
  self.assertEqual(stock_exposures({'A':['AMD'],'B':['AMDX'],'C':['amd']},'AMD'),['A','C'])

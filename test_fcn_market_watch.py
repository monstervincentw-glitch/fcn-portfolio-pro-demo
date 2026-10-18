import datetime as dt
import pandas as pd
from fcn_market_watch import summarize_chart

D=dt.date(2026,10,18)
frame=pd.DataFrame({'stock':['A','A','B','B'], 'date':['2026-10-10','2026-10-16','2026-10-10','2026-10-15'], 'norm':[100,78,100,102]})
rows,info=summarize_chart(frame, {'ki':70,'ko':105,'strike':80},value_column='norm',asof=D,stale_days=2)
assert info['worst']==78 and info['worst_stock']=='A'
assert rows[0]['距KI百分點']==8 and rows[0]['距Strike百分點']==-2
assert info['stale'] and any('不同' in w for w in info['warnings'])
try:
    summarize_chart(frame,{},value_column='missing',asof=D)
except ValueError:pass
else:raise AssertionError('missing column should fail')
five=pd.DataFrame({'stock':list('ABCDEF'), 'date':['2026-10-16']*6,'norm':[100]*6})
try:
    summarize_chart(five,{},value_column='norm',asof=D)
except ValueError:pass
else:raise AssertionError('more than 5 underlyings should fail')
future=pd.DataFrame({'stock':['A'],'date':['2026-10-20'],'norm':[90]})
rows,info=summarize_chart(future,{},value_column='norm',asof=D)
assert not rows and info['worst'] is None
print('5 checks passed')

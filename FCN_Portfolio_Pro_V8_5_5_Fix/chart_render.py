"""Deterministic Altair layered FCN chart with independent legend/axes.
The underlying stock lines are never filtered by barrier-only color domains.
"""
from __future__ import annotations
import pandas as pd
import altair as alt
PALETTE=['#986127','#547C70','#B65F4D','#76668D','#497C91']
BARRIERS={'ko':('KO','#20977e'),'strike':('Strike','#e79b32'),'ki':('KI','#d45165')}

def build_stock_chart(data,settings,stocks):
    frame=data.copy()
    frame['date']=pd.to_datetime(frame['date'],errors='coerce').dt.normalize()
    frame['ratio']=pd.to_numeric(frame['ratio'],errors='coerce')
    frame=frame.loc[frame['stock'].isin(stocks)].dropna(subset=['date','ratio']).sort_values(['stock','date'])
    if frame.empty: raise ValueError('沒有可繪製的股價')
    levels=[float(settings[k]) for k in BARRIERS if settings.get(k) is not None]
    extrema=[frame.ratio.min(),frame.ratio.max(),*levels]
    scale=alt.Scale(domain=[max(0,float(min(extrema))-5),float(max(extrema))+5],zero=False)
    stock_scale=alt.Scale(domain=list(stocks),range=PALETTE[:len(stocks)])
    lines=(alt.Chart(frame).mark_line(strokeWidth=2.8,point=False)
           .encode(x=alt.X('date:T',title='交易日期'),
                   y=alt.Y('ratio:Q',title='相對期初價格（%）',scale=scale),
                   color=alt.Color('stock:N',title='連結標的',scale=stock_scale),
                   tooltip=[alt.Tooltip('date:T',title='日期',format='%Y/%m/%d'),
                            alt.Tooltip('stock:N',title='標的'),alt.Tooltip('ratio:Q',title='期初比價',format='.2f')]))
    chart=lines
    for key,(label,color) in BARRIERS.items():
        if settings.get(key) is None:continue
        level=float(settings[key])
        rule=(alt.Chart(pd.DataFrame({'level':[level],'name':[label]}))
              .mark_rule(color=color,strokeDash=[6,4],strokeWidth=1.7)
              .encode(y='level:Q',tooltip=['name:N',alt.Tooltip('level:Q',format='.2f')]))
        chart=chart+rule
    if settings.get('ko_start') is not None:
        dt=pd.to_datetime(settings['ko_start'],errors='coerce')
        if pd.notna(dt) and frame.date.min()<=dt<=frame.date.max():
            obs=alt.Chart(pd.DataFrame({'date':[dt],'event':['KO觀察起日']})).mark_rule(color='#64748b',strokeDash=[2,4]).encode(x='date:T',tooltip=['event:N','date:T'])
            chart=chart+obs
    return chart.properties(height=390).interactive()


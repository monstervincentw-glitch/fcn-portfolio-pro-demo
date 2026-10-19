"""Replay bounded, real Sheets evidence through production loaders and V2.

The independent first-hit scan is audit-only, never used by website calculations.
No network, ledger access, price filling, or Sheets writes.
"""
from datetime import date, timedelta
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from central_catalog import (PRODUCT_RANGE,LEGS_RANGE,PERIOD_RANGE,CALENDAR_RANGE,INPUT_RANGE,
                             CENTRAL_CATALOG_ID,STOCK_LIBRARY_ID,load_model_inputs,to_day,
                             as_positive_number)
from v2_portfolio_adapter import load_models
from fcn_central_model import ratio

SNAPSHOT=ROOT/'docs/audit/evidence/ko-market-20261019.json'
RESULT=ROOT/'docs/audit/evidence/ko-market-results-20261019.json'


class EvidenceReader:
    def __init__(self,data): self.data=data
    def read(self,sheet_id,span):
        if sheet_id==CENTRAL_CATALOG_ID:
            key=dict(zip([PRODUCT_RANGE,LEGS_RANGE,PERIOD_RANGE,CALENDAR_RANGE,INPUT_RANGE],
                         ['terms','legs','periods','calendar','inputs']))[span]
            return self.data['central'][key]['values']
        assert sheet_id==STOCK_LIBRARY_ID
        symbols=list(self.data['market']['rows'][0]['prices'])
        rows=self.data['market']['rows']
        if span=="'收盤價矩陣'!A1:TJ1":return [['交易日期']+symbols]
        if span=="'收盤價矩陣'!A2:A":return [[r['date']] for r in rows]
        letter=span.split('!')[1].split('2:')[0]
        index=ord(letter)-ord('B')
        assert 0<=index<len(symbols)
        return [[r['prices'][symbols[index]]] for r in rows]


def audit(data):
    reader=EvidenceReader(data)
    catalog,holidays,periods,rules=load_model_inputs(reader)
    _,models=load_models(reader,today=date(2026,10,19))
    by_date={to_day(r['date']):r for r in data['market']['rows']}
    results=[]
    for pid in ('SB04','SP43','SB19'):
        p=catalog.products[pid];m=models[pid];legs=catalog.legs[pid]
        pricing,ko_start,final=(to_day(p[k]) for k in ('pricing_date','ko_start_date','final_eval_date'))
        initial={l['ticker']:as_positive_number(l['initial_price']) for l in legs}
        hits={s:None for s in initial};ko=None;missing=[];trace=[];excluded=[]
        for offset in range((final-pricing).days+1):
            day=pricing+timedelta(days=offset)
            if day.weekday()>=5 or day in holidays:
                excluded.append(day.isoformat());continue
            row=by_date.get(day,{})
            quotes={s:as_positive_number(row.get('prices',{}).get(s)) for s in initial}
            absent=[s for s,v in quotes.items() if v is None]
            if absent: missing.append({'date':day.isoformat(),'tickers':absent})
            relative={s:v/initial[s] if v is not None else None for s,v in quotes.items()}
            reached={s:relative[s] is not None and relative[s]>=ratio(p['ko_barrier_ratio']) for s in initial}
            eligible=day>=ko_start and ko is None
            if eligible and not absent:
                for s in initial:
                    if reached[s] and hits[s] is None:hits[s]=day
                triggered=all(hits.values()) if p['ko_type']=='記憶式' else all(reached.values())
                if triggered and not missing:ko=day
            trace.append(dict(date=day.isoformat(),source_row=row.get('source_row'),quotes=quotes,
                              ratios=relative,eligible=eligible,reached=reached,
                              memory={s:v.isoformat() if v else None for s,v in hits.items()},
                              first_ko=ko.isoformat() if ko else None))
            if ko:break
        # Independently count the contractual coupon trading days, no rounding override.
        coupons=[]
        for n,start,end,payment in periods[pid]:
            days=[start+timedelta(days=i) for i in range((end-start).days+1)
                  if (start+timedelta(days=i)).weekday()<5 and start+timedelta(days=i) not in holidays]
            earned=sum(day<=ko for day in days) if ko else len(days)
            coupons.append(dict(number=n,start=start.isoformat(),end=end.isoformat(),payment=payment.isoformat(),
                                full_days=len(days),earned_days=earned,
                                expected_rate=ratio(p['annual_coupon_rate'])/12*earned/len(days)))
        source_checks=[]
        for i,leg in enumerate(legs,1):
            source_checks.append(dict(ticker=leg['ticker'],initial_price=leg['initial_price'],
                input_ticker=rules[pid].get(f'標的{i}股票'),input_initial=rules[pid].get(f'標的{i}期初價'),
                pricing_close=by_date.get(pricing,{}).get('prices',{}).get(leg['ticker']),
                matches_input=leg['ticker']==rules[pid].get(f'標的{i}股票') and
                as_positive_number(leg['initial_price'])==as_positive_number(rules[pid].get(f'標的{i}期初價'))))
        old_ko=to_day(p.get('model_ko_date'))
        last_ratios=trace[-1]['ratios']
        worst=min(last_ratios,key=lambda s:last_ratios[s]) if all(v is not None for v in last_ratios.values()) else None
        worst_ratio=last_ratios[worst] if worst else None
        reference_principal=None
        if not missing and worst_ratio is not None:
            reference_principal=1.0
            if not ko and p['ki_type']=='EKI' and worst_ratio<=ratio(p['ki_barrier_ratio']) and worst_ratio<ratio(p['strike_ratio']):
                reference_principal=worst_ratio/ratio(p['strike_ratio'])
        results.append(dict(product_id=pid,pricing_date=pricing.isoformat(),ko_start=ko_start.isoformat(),
            final_eval=final.isoformat(),maturity=to_day(p['maturity_date']).isoformat(),ko_type=p['ko_type'],
            ko_barrier=ratio(p['ko_barrier_ratio']),legs=source_checks,
            reference_ko=ko.isoformat() if ko else None,v2_ko=m.ko_date.isoformat() if m.ko_date else None,
            legacy_api_ko=old_ko.isoformat() if old_ko else None,
            legacy_api_disagrees=old_ko!=m.ko_date,
            state=m.state,category=m.category,principal_ratio=m.principal_ratio,ki_touched=m.ki_touched,
            reference_principal=reference_principal,worst_ticker=worst,worst_ratio=worst_ratio,
            coupon_rate=m.earned_coupon_rate,forecast_rate=m.forecast_coupon_rate,
            missing=missing,issues=m.issues,excluded_dates=excluded,observed_trading_days=len(trace),
            first_hits={s:v.isoformat() if v else None for s,v in hits.items()},
            coupons=coupons,model_coupons=m.coupon_rows,trace=trace))
    return dict(source_snapshot=SNAPSHOT.name,captured_at=data['captured_at'],
                note='Actual source prices; independent audit scan only. No deployment or settlement confirmation.',products=results)


if __name__=='__main__':
    report=audit(json.loads(SNAPSHOT.read_text(encoding='utf-8')))
    RESULT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for r in report['products']:
        print(json.dumps({k:r[k] for k in ('product_id','ko_start','reference_ko','v2_ko','legacy_api_ko',
                         'observed_trading_days','missing','issues','principal_ratio','coupon_rate','legs')},ensure_ascii=False))

from copy import deepcopy
from datetime import date, timedelta
import json
import pytest
from scripts.audit_coupon_calendar import SNAPSHOT, SnapshotReader, audit
from central_catalog import load_model_inputs, parse_periods
from fcn_central_model import model_one
from v2_portfolio_engine import CouponPeriod, v2_coupon_periods, trading_days
from central_catalog import PRODUCT_RANGE,LEGS_RANGE,PERIOD_RANGE,CALENDAR_RANGE,INPUT_RANGE


@pytest.fixture
def data():
    return json.loads(SNAPSHOT.read_text(encoding='utf-8'))


@pytest.mark.parametrize('pid,counts', [
    ('SB04',[22,20,19]),('SP43',[20,23,21]),('SB19',[23,19,20]),
    ('SA94',[23,19,21]),('SQ29',[23,19,22]),('SR50',[21,22,23]),
    ('SAE9',[24,19,21]),('SR67',[23,22,20]),('SP34',[22,19,21]),
    ('SM25',[20,22,23]),('SQ59',[20,22,23])])
def test_live_formula_results_match_production_loader_and_v2(data,pid,counts):
    result = next(p for p in audit(data)['products'] if p['product_id']==pid)
    assert not result['errors']
    assert [p['trading_days'] for p in result['periods']] == counts
    assert result['ko_equals_first_end']
    assert result['ko_start'] != result['periods'][0]['payment']
    assert not any(g['uncovered_trading_days'] for g in result['gaps'])


def test_gap_dates_are_weekends_and_exchange_holidays(data):
    products={p['product_id']:p for p in audit(data)['products']}
    assert products['SB04']['gaps'][0]['dates']==['2026-01-17','2026-01-18','2026-01-19']
    assert products['SP43']['gaps'][0]['dates']==['2026-04-03','2026-04-04','2026-04-05']
    assert products['SB19']['gaps'][0]['dates']==['2026-02-14','2026-02-15','2026-02-16']
    assert products['SB19']['gaps'][1]['dates']==['2026-03-14','2026-03-15']


def test_cross_month_holiday_and_early_ko_preserve_payment():
    p=CouponPeriod(1,date(2026,6,5),date(2026,7,6),date(2026,7,8))
    holidays=[date(2026,6,19),date(2026,7,3)]
    result=v2_coupon_periods([p],.21,ko_date=date(2026,7,2),holidays=holidays)[0]
    assert (result.full_trading_days,result.ko_trading_days)==(20,19)
    assert result.coupon_rate==pytest.approx(.21/12*19/20)
    assert result.payment==date(2026,7,8)


def test_explicit_holiday_dates_are_not_rolled_and_future_coupon_is_zero():
    p=CouponPeriod(1,date(2026,4,3),date(2026,4,6),date(2026,4,11))
    result=v2_coupon_periods([p],.12,as_of=date(2026,4,2),holidays=[date(2026,4,3)])[0]
    assert result.full_trading_days==1
    assert result.coupon_rate==0
    assert result.payment==date(2026,4,11)  # Explicit Saturday remains unchanged.


def test_bank_holidays_are_not_exchange_holidays(data):
    _,holidays,_,_=load_model_inputs(SnapshotReader(data))
    assert date(2026,4,3) in holidays
    assert date(2026,10,12) not in holidays
    assert date(2026,11,11) not in holidays
    assert trading_days(date(2026,11,27),date(2026,11,27),holidays)==1


@pytest.mark.parametrize('case',['overlap','gap','duplicate','payment_before_end','missing_payment'])
def test_invalid_schedules_are_rejected(case):
    a=CouponPeriod(1,date(2026,1,29),date(2026,1,30),date(2026,2,2))
    b=CouponPeriod(2,date(2026,2,2),date(2026,2,3),date(2026,2,4))
    if case=='overlap': b=CouponPeriod(2,a.end,b.end,b.payment)
    if case=='gap': b=CouponPeriod(2,date(2026,2,3),b.end,b.payment)
    if case=='duplicate': b=CouponPeriod(1,b.start,b.end,b.payment)
    if case=='payment_before_end': b=CouponPeriod(2,b.start,b.end,b.start)
    if case=='missing_payment': b=CouponPeriod(2,b.start,b.end,None)
    with pytest.raises(ValueError):
        v2_coupon_periods([a,b],.12,as_of=date(2026,3,1))


def test_invalid_period_number_is_not_silently_dropped():
    rows=[['商品|期別','商品代號','配息期','期初日','期末日','配息日'],
          ['X|?','X','bad','2026-01-01','2026-01-30','2026-02-02']]
    result=parse_periods(rows)
    assert 'X' in result and len(result['X'])==1


@pytest.mark.parametrize('field',['payment','ko','missing_last_period'])
def test_api_date_drift_is_reported_and_lifecycle_remains(data,field):
    catalog,holidays,periods,rules=load_model_inputs(SnapshotReader(data))
    pid='SAE9'
    product=deepcopy(catalog.products[pid]); schedule=list(periods[pid])
    if field=='payment':
        n,start,end,payment=schedule[0]; schedule[0]=(n,start,end,payment+timedelta(days=1))
    elif field=='ko': product['ko_start_date']='2026-11-10'
    else: schedule.pop()
    result=model_one(product,catalog.legs[pid],schedule,{},holidays,rules[pid],today=date(2026,10,19))
    assert result.category=='閉鎖中'
    assert any('一致' in x or '期數' in x for x in result.issues)


def test_real_reader_path_uses_one_central_batch(data):
    spans=[PRODUCT_RANGE,LEGS_RANGE,PERIOD_RANGE,CALENDAR_RANGE,INPUT_RANGE]
    keys=['terms','legs','periods','calendar','inputs']
    class Response:
        status_code=200
        def json(self):
            return {'valueRanges':[{'range':span,'values':data[key]['values']}
                                   for span,key in zip(spans,keys)]}
    class Session:
        calls=[]
        def get(self,url,params,timeout):
            self.calls.append((url,params))
            return Response()
    class Reader:
        session=Session()
        def read(self,*args):
            raise AssertionError('Production path must not issue separate reads')
    reader=Reader()
    catalog,_,periods,_=load_model_inputs(reader)
    assert len(reader.session.calls)==1
    url,params=reader.session.calls[0]
    assert data['spreadsheet_id'] in url
    assert [v for k,v in params if k=='ranges']==spans
    assert ('valueRenderOption','UNFORMATTED_VALUE') in params
    assert len(catalog.products)==30 and sum(map(len,periods.values()))==33


@pytest.mark.parametrize('pid',['SB04','SP43','SB19','SA94','SQ29','SR50',
                                'SAE9','SR67','SP34','SM25','SQ59'])
def test_model_coupon_dates_equal_live_sheet_with_synthetic_prices(data,pid):
    catalog,holidays,periods,rules=load_model_inputs(SnapshotReader(data))
    from central_catalog import to_day
    from scripts.audit_central_snapshot import number
    product=catalog.products[pid]
    first,last=to_day(product['pricing_date']),to_day(product['final_eval_date'])
    # Synthetic quotes isolate date propagation; never claim these are market results.
    quotes={first+timedelta(days=i):{leg['ticker']:number(leg['initial_price'])*.9
            for leg in catalog.legs[pid]} for i in range((last-first).days+1)}
    result=model_one(product,catalog.legs[pid],periods[pid],quotes,holidays,rules[pid],today=last)
    assert not result.issues
    assert result.ko_date is None
    assert [(r['計息起日'],r['計息末日'],r['配息日']) for r in result.coupon_rows] == [
        (str(s),str(e),str(p)) for _,s,e,p in periods[pid]]

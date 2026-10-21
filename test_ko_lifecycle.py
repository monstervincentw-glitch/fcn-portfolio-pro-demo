"""Synthetic customer rows only; never persist or mutate a real ledger."""
from datetime import date, timedelta
from copy import deepcopy
import pytest
import streamlit as st

import v2_portfolio_adapter as adapter
from central_catalog import Catalog
from fcn_central_model import model_one
from demo_utils import currency_summary, receipt_values

D1, D2, D3, D4, D5 = [date(2026, 10, d) for d in (14,15,16,19,20)]
PRODUCT = dict(product_id='TEST', currency='USD', pricing_date=D1, issue_date=D1,
               ko_start_date=D2, final_eval_date=D5, maturity_date=date(2026,10,22),
               annual_coupon_rate=.12, ko_barrier_ratio=1, strike_ratio=.8,
               ki_barrier_ratio=.6, ko_type='非記憶式', ki_type='AKI')
LEGS = ({'ticker':'A','initial_price':100}, {'ticker':'B','initial_price':200})
PERIODS = [(1,D1,D3,D4), (2,D4,D5,date(2026,10,22))]
PRICES = {D1:{'A':120,'B':240}, D2:{'A':110,'B':200},
          D3:{'A':10,'B':60}, D4:{'A':10,'B':60}, D5:{'A':10,'B':60}}
CATALOG = Catalog({'TEST':PRODUCT}, {'TEST':LEGS})


def model(prices=None, today=D5):
    return model_one(PRODUCT, LEGS, PERIODS, PRICES if prices is None else prices, [], today=today)


def holdings():
    return [dict(holding_id=str(i),customer_id='客*',product_id='TEST',currency=cc,
                 invested_amount=n, estimated_coupon_total=99999, v2_forecast_coupon_total=99999,
                 v2_state='OLD',ko_date=date(2000,1,1),model_state='OLD',
                 returned_principal_amount=0,received_coupon_amount=12)
            for i,(cc,n) in enumerate([('USD',10000),('USD',30000),('EUR',20000),('JPY',1000000)])]


def enriched(monkeypatch, m=None):
    monkeypatch.setattr(adapter, 'load_models', lambda reader: (CATALOG, {'TEST':m or model()}))
    return adapter.enrich_new_holdings(None, holdings())


def test_ko_freezes_chart_worst_leg_and_ki():
    m=model()
    assert not m.issues
    assert m.ko_date == D2 and m.ki_touched is False
    assert m.latest_date == D2
    assert m.worst_ticker == 'B' and m.worst_ratio == 1
    assert max(p['date'] for p in m.price_history) == D2
    assert m.coupon_rows[1]['模型票息率'] == 0
    assert m.coupon_rows[1]['未來假設票息率'] == 0
    assert m.earned_coupon_rate == pytest.approx(.01*2/3)
    assert m.forecast_coupon_rate == m.earned_coupon_rate


@pytest.mark.parametrize('bad', [None, 'bad', float('nan'), 0])
def test_invalid_quotes_after_ko_cannot_change_settlement(bad):
    prices=deepcopy(PRICES);prices[D3]['A']=bad
    m=model(prices)
    assert not m.issues and m.ko_date==D2 and m.principal_ratio==1


def test_known_ko_does_not_require_final_evaluation_quotes():
    m=model({D1:PRICES[D1], D2:PRICES[D2]}, today=date(2027,2,1))
    assert not m.issues and m.ko_date==D2
    assert m.category=='歷史歸檔'


@pytest.mark.parametrize('today, category', [(date(2027,1,15),'近三個月出場'),
                                           (date(2027,1,16),'歷史歸檔')])
def test_exit_uses_three_calendar_months(today,category):
    assert model(today=today).category==category


def test_multiclient_amounts_and_unpaid_cash_are_separate(monkeypatch):
    rows=enriched(monkeypatch)
    for h in rows:
        assert h['ko_date']==D2 and h['v2_exit_date']==D2
        assert h['v2_principal_ratio']==1 and h['v2_active_exposure'] is False
        assert h['estimated_principal_total']==h['invested_amount']
        assert h['estimated_outstanding']==0
        assert h['estimated_coupon_total']==round(h['invested_amount']*.01*2/3,2)
        assert h['returned_principal_amount']==0 and h['received_coupon_amount']==12
        assert receipt_values(h)['actual_outstanding']==h['invested_amount']
        assert h['expected_principal_date'] is None  # KO observation is not a payment date.
    assert len(rows)==4


def test_terminated_loss_is_not_remaining_market_exposure(monkeypatch):
    m=model({d:{'A':50,'B':100} for d in PRICES})
    rows=enriched(monkeypatch,m)
    assert rows[0]['estimated_principal_total']==6250
    assert rows[0]['v2_principal_loss']==3750
    assert rows[0]['estimated_outstanding']==0


@pytest.mark.parametrize('failure', ['api','unknown','missing'])
def test_stale_model_fields_cleared_even_when_reload_fails(monkeypatch,failure):
    original=holdings();before=deepcopy(original)
    if failure=='api':
        def fail(reader): raise RuntimeError('offline')
        monkeypatch.setattr(adapter,'load_models',fail)
    else:
        missing=model({D1:PRICES[D1],D3:PRICES[D3]})
        monkeypatch.setattr(adapter,'load_models',lambda reader:(CATALOG,{} if failure=='unknown' else {'TEST':missing}))
    st.session_state['_fcn_v9_catalog_models']=('OLD','OLD')
    rows=adapter.enrich_new_holdings(None,original)
    assert original==before
    assert st.session_state.get('_fcn_v9_catalog_models')!=('OLD','OLD')
    for h in rows:
        assert h['ko_date'] is None
        assert h['v2_forecast_coupon_total'] is None
        assert h['estimated_coupon_total'] is None
        assert h['v2_active_exposure'] is None
        assert h['v2_state']!='OLD' and h['model_state']!='OLD'
        assert h['returned_principal_amount']==0


def test_missing_quotes_keep_active_lifecycle_visible():
    m=model({D1:PRICES[D1]},today=D3)
    # No observed session at/after KO start; no inferred KO.
    assert m.ko_date is None and m.category=='比價中'


def test_currency_aggregates_are_separate_and_unknown_is_not_zero(monkeypatch):
    rows=enriched(monkeypatch)
    totals=currency_summary(rows)
    assert [totals[c]['invested'] for c in ('USD','EUR','JPY')]==[40000,20000,1000000]
    missing=dict(rows[0], estimated_outstanding=None,estimated_coupon_total=None,estimated_principal_total=None)
    summary=currency_summary([missing])['USD']
    assert summary['missing_count']['outstanding'] == 1
    assert summary['missing_count']['returned'] == 1
    assert summary['missing_count']['coupon'] == 1
    assert summary['known_count']['returned'] == 0


def test_historical_holdings_survive_exit_and_dashboard(monkeypatch):
    from central_live_pages import model_dashboard_groups, model_exposure_rows
    m=model(today=date(2027,2,1));rows=enriched(monkeypatch,m)
    groups=model_dashboard_groups({'TEST':m},rows,today=date(2027,2,1))
    assert len(groups['歷史歸檔'])==1 and not groups['資料不足']
    assert not groups['閉鎖中'] and not groups['比價中']
    exposures=model_exposure_rows(CATALOG,{'TEST':m},'A',rows)
    assert exposures[0]['存續曝險']=='無（模型已出場）'
    assert exposures[0]['歷史持倉筆數']==4
    assert len(rows)==4


def test_quote_panel_stops_at_ko(monkeypatch):
    monkeypatch.setattr(adapter,'load_model_inputs',lambda reader:(CATALOG,[],{'TEST':PERIODS},{}))
    monkeypatch.setattr(adapter,'load_market_matrix',lambda reader,tickers:(PRICES,D5,{'A','B'}))
    _, models=adapter.load_models(None,today=D5)
    assert {r['收盤日期'] for r in models['TEST'].quote_rows}=={D2.isoformat()}


def test_stock_api_failure_preserves_lifecycle_and_no_false_exit(monkeypatch):
    monkeypatch.setattr(adapter,'load_model_inputs',lambda reader:(CATALOG,[],{'TEST':PERIODS},{}))
    def fail(*args): raise RuntimeError('unavailable')
    monkeypatch.setattr(adapter,'load_market_matrix',fail)
    _, models=adapter.load_models(None,today=D3)
    m=models['TEST']
    assert m.issues and m.category=='比價中' and m.ko_date is None
    assert m.principal_ratio is None


def test_mixed_known_unknown_currency_total_is_incomplete():
    rows=[dict(currency='USD',invested_amount=10,estimated_outstanding=10,
               estimated_principal_total=None,estimated_coupon_total=1),
          dict(currency='USD',invested_amount=20,estimated_outstanding=None,
               estimated_principal_total=None,estimated_coupon_total=None)]
    s=currency_summary(rows)['USD']
    assert s['invested']==30 and s['outstanding']==10 and s['coupon']==1
    assert s['missing_count']['outstanding']==1 and s['missing_count']['coupon']==1
    assert s['known_count']['returned']==0


def test_cash_receipt_fields_are_not_rewritten(monkeypatch):
    monkeypatch.setattr(adapter,'load_models',lambda reader:(CATALOG,{'TEST':model()}))
    source=holdings();source[0]['returned_principal_amount']=1234
    before=deepcopy(source)
    result=adapter.enrich_new_holdings(None,source)
    assert source==before and result[0]['returned_principal_amount']==1234
    assert result[0]['estimated_principal_total']==10000


def test_absent_cash_receipts_remain_unknown():
    s=currency_summary([dict(currency='USD',invested_amount=10000,estimated_outstanding=0,
                             estimated_principal_total=10000,estimated_coupon_total=50)])['USD']
    assert 'actual_returned' not in s and 'actual_coupon' not in s
    assert s['returned']==10000 and s['outstanding']==0

"""Regression tests for the model-only investment overview.

All rows are synthetic: no Sheets I/O, customer data, actual receipts or
additional price database. Only V2-enriched holding fields determine cash flow.
"""
from demo_utils import currency_summary
from copy import deepcopy
from datetime import date
import pytest
import v2_portfolio_adapter as adapter
from fcn_central_model import model_one


def synthetic_model(case):
    start, observation, final = (date(2026, 10, n) for n in (14, 15, 16))
    product = dict(product_id='SYNTHETIC', pricing_date=start, issue_date=start,
                   ko_start_date=observation, final_eval_date=final,
                   maturity_date=date(2026, 10, 19), annual_coupon_rate=.12,
                   ko_barrier_ratio=1, strike_ratio=.8, ki_barrier_ratio=.6,
                   ko_type='非記憶式', ki_type='EKI')
    quotes = {start: {'A': 90}, observation: {'A': 90}, final: {'A': 90}}
    if case == 'ko':
        quotes[observation]['A'] = 100
        quotes[final]['A'] = 20  # losses after KO must not change redemption
    elif case == 'loss':
        quotes[final]['A'] = 50
    elif case == 'missing_price':
        quotes[observation]['A'] = None
    elif case == 'missing_terms':
        product['strike_ratio'] = None
    return model_one(product, [{'ticker': 'A', 'initial_price': 100}],
                     [(1, start, final, date(2026, 10, 19))], quotes, [],
                     today=observation if case == 'active' else final)


@pytest.mark.parametrize('case, returned, outstanding, coupon', [
    ('ko', 100, 0, .67), ('maturity', 100, 0, 1),
    ('loss', 62.5, 0, 1), ('active', 0, 100, 0),
    ('missing_price', None, None, None), ('missing_terms', None, None, None),
])
def test_real_model_to_holding_amounts(monkeypatch, case, returned, outstanding, coupon):
    m = synthetic_model(case)
    monkeypatch.setattr(adapter, 'load_models', lambda reader: (None, {'SYNTHETIC': m}))
    original = [dict(holding_id='S-1', customer_id='虛構甲*', product_id='SYNTHETIC',
                     currency='USD', invested_amount=100,
                     estimated_principal_total=999999, returned_principal_amount=999999)]
    before = deepcopy(original)
    row = adapter.enrich_new_holdings(None, original)[0]
    assert original == before
    assert row['estimated_principal_total'] == returned
    assert row['estimated_outstanding'] == outstanding
    assert row['estimated_coupon_total'] == coupon
    if case == 'active':
        assert row['v2_active_exposure'] is True and not row['v2_issues']
        assert row['v2_forecast_coupon_total'] == 1  # future is not earned
    if case == 'loss':
        assert row['v2_principal_loss'] == 37.5
        assert row['estimated_pnl'] == -36.5


def test_same_product_multiple_holdings_computes_model_once(monkeypatch):
    calls = []
    def counted_model(*args, **kwargs):
        calls.append(1)
        return synthetic_model('ko')
    from central_catalog import Catalog
    monkeypatch.setattr(adapter, 'load_model_inputs', lambda reader:
                        (Catalog({'SYNTHETIC': {}}, {'SYNTHETIC': []}), [], {}, {}))
    monkeypatch.setattr(adapter, 'load_market_matrix', lambda reader, tickers: ({}, None, set()))
    monkeypatch.setattr(adapter, 'model_one', counted_model)
    rows = adapter.enrich_new_holdings(None, [
        dict(holding_id=str(i), customer_id='虛構甲*', product_id='SYNTHETIC',
             currency=cc, invested_amount=n)
        for i, (cc, n) in enumerate([('USD', 100), ('USD', 200), ('EUR', 50), ('JPY', 1000)])])
    totals = currency_summary(rows)
    assert len(calls) == 1 and len(rows) == 4
    assert [totals[c]['returned'] for c in ('USD', 'EUR', 'JPY')] == [300, 50, 1000]


def test_adapter_uses_exit_ratio_not_ko_label(monkeypatch):
    # Defensive adapter contract only: canonical V2 KO always redeems at par.
    # Do not invent a real KO-loss term, but never overwrite a supplied ratio.
    m = synthetic_model('ko')
    m.principal_ratio = .7
    monkeypatch.setattr(adapter, 'load_models', lambda reader: (None, {'SYNTHETIC': m}))
    row = adapter.enrich_new_holdings(None, [dict(product_id='SYNTHETIC', invested_amount=100)])[0]
    assert row['estimated_principal_total'] == 70
    assert row['estimated_outstanding'] == 0 and row['v2_principal_loss'] == 30


def test_known_model_subtotals_remain_visible_with_missing_product():
    holdings = [
        dict(currency='USD', invested_amount=100, estimated_principal_total=100,
             estimated_outstanding=0, estimated_coupon_total=6,
             v2_active_exposure=False, returned_principal_amount=999999),
        dict(currency='USD', invested_amount=150, estimated_principal_total=None,
             estimated_outstanding=150, estimated_coupon_total=3,
             v2_active_exposure=True, v2_issues='',
             returned_principal_amount=999999),
        dict(currency='USD', invested_amount=200, estimated_principal_total=None,
             estimated_outstanding=None, estimated_coupon_total=None,
             v2_active_exposure=None, v2_issues='缺行情',
             returned_principal_amount=999999),
    ]
    result = currency_summary(holdings)['USD']
    assert result['invested'] == 450
    assert result['returned'] == 100  # exited: 100; valid active: 0
    assert result['outstanding'] == 150
    assert result['coupon'] == 9
    assert result['known_count']['returned'] == 2
    assert result['missing_count']['returned'] == 1
    assert result['missing_count']['outstanding'] == 1
    assert result['missing_count']['coupon'] == 1
    assert not any(key.startswith('actual_') for key in result)


def test_model_principal_loss_and_currency_are_not_ledger_cash():
    holdings = [
        dict(currency='USD', invested_amount=100, estimated_principal_total=70,
             estimated_outstanding=0, estimated_coupon_total=2,
             v2_active_exposure=False, returned_principal_amount=100),
        dict(currency='EUR', invested_amount=40, estimated_principal_total=40,
             estimated_outstanding=0, estimated_coupon_total=1,
             v2_active_exposure=False, returned_principal_amount=0),
    ]
    result = currency_summary(holdings)
    assert result['USD']['returned'] == 70
    assert result['USD']['outstanding'] == 0
    assert result['EUR']['returned'] == 40
    assert result['EUR']['invested'] == 40
    assert result['JPY']['count'] == 0


def test_all_models_missing_cannot_be_misread_as_zero():
    output = currency_summary([
        dict(currency='USD', invested_amount=100,
             estimated_principal_total=None, estimated_outstanding=None,
             estimated_coupon_total=None, v2_issues='中央條款缺漏',
             returned_principal_amount=100)
    ])['USD']
    assert output['returned'] == 0
    assert output['known_count']['returned'] == 0
    assert output['missing_count']['returned'] == 1
    assert output['missing_count']['outstanding'] == 1

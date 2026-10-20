"""Regression tests for the model-only investment overview.

All rows are synthetic: no Sheets I/O, customer data, actual receipts or
additional price database. Only V2-enriched holding fields determine cash flow.
"""
from demo_utils import currency_summary


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

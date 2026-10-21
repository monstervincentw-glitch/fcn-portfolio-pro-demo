"""Focused regression: model-only overview after PR2 rollback.

Synthetic numbers only. No real customer data, credentials, or sheet writes.
"""
from demo_utils import currency_summary


def test_five_exited_and_one_active_model_recover_900k():
    rows = [
        dict(currency='USD', invested_amount=amount,
             estimated_principal_total=amount, estimated_outstanding=0,
             estimated_coupon_total=1000, v2_active_exposure=False,
             returned_principal_amount=0)
        for amount in (100000, 200000, 200000, 200000, 200000)
    ]
    rows.append(dict(currency='USD', invested_amount=200000,
        estimated_principal_total=None, estimated_outstanding=200000,
        estimated_coupon_total=0, v2_active_exposure=True, v2_issues='',
        returned_principal_amount=999999))
    total=currency_summary(rows)['USD']
    assert total['invested']==1100000
    assert total['returned']==900000
    assert total['outstanding']==200000
    assert total['coupon']==5000
    assert total['missing_count']['returned']==0
    assert total['known_count']['returned']==6
    assert 'actual_returned' not in total


def test_missing_price_is_unknown_not_zero_but_known_subtotal_remains():
    rows=[
        dict(currency='USD',invested_amount=100,
             estimated_principal_total=75,estimated_outstanding=0,
             estimated_coupon_total=2,v2_active_exposure=False),
        dict(currency='USD',invested_amount=200,
             estimated_principal_total=None,estimated_outstanding=None,
             estimated_coupon_total=None,v2_active_exposure=None,v2_issues='缺股價')
    ]
    total=currency_summary(rows)['USD']
    assert total['returned']==75
    assert total['known_count']['returned']==1
    assert total['missing_count']['returned']==1
    assert total['missing_count']['outstanding']==1


def test_loss_not_counted_as_outstanding_and_currencies_separate():
    total=currency_summary([
        dict(currency='USD',invested_amount=100,estimated_principal_total=70,
             estimated_outstanding=0,estimated_coupon_total=3),
        dict(currency='EUR',invested_amount=90,estimated_principal_total=None,
             estimated_outstanding=90,estimated_coupon_total=1,
             v2_active_exposure=True,v2_issues='')
    ])
    assert total['USD']['returned']==70
    assert total['USD']['outstanding']==0
    assert total['EUR']['returned']==0
    assert total['EUR']['outstanding']==90
    assert total['JPY']['count']==0

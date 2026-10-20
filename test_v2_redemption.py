"""Synthetic V2 redemption counterexamples; not verification of live settlements."""
from datetime import date

import pytest

from fcn_central_model import model_one
from test_v2_audit import D1, D2, D3, evaluate


def closes(first=90, final=70):
    return {D1: {'A': first, 'B': 190},
            D2: {'A': 90, 'B': 180},
            D3: {'A': final, 'B': 180}}


@pytest.mark.parametrize('kind, touched, principal', [
    ('AKI', True, .875), ('EKI', False, 1), ('Non-KI', None, .875)])
def test_recovered_intraperiod_ki_and_final_only_ki(kind, touched, principal):
    r = evaluate(initial_prices={'A': 100, 'B': 200},
                 daily_prices=closes(first=60), ki_type=kind)
    assert not r.issues
    assert r.ki_touched is touched
    assert r.principal_recovery_ratio == pytest.approx(principal)
    assert r.total_return_rate == pytest.approx(.01 + principal - 1)


@pytest.mark.parametrize('kind', ['AKI', 'EKI'])
@pytest.mark.parametrize('final, touched, principal', [
    (60, True, .75), (60.01, False, 1), (59.99, True, .5999 / .8)])
def test_ki_boundary_includes_equality(kind, final, touched, principal):
    r = evaluate(initial_prices={'A': 100, 'B': 200},
                 daily_prices=closes(final=final), ki_type=kind)
    assert not r.issues
    assert r.ki_touched is touched
    assert r.principal_recovery_ratio == pytest.approx(principal)


@pytest.mark.parametrize('final, principal', [(79, .79/.8), (80, 1), (81, 1)])
def test_nonki_strike_boundary(final, principal):
    r = evaluate(initial_prices={'A': 100, 'B': 200},
                 daily_prices=closes(final=final), ki_type='Non-KI', ki_barrier=None)
    assert not r.issues
    assert r.principal_recovery_ratio == pytest.approx(principal)


def test_worst_is_relative_performance_not_lowest_absolute_price():
    r = evaluate(initial_prices={'A': 100, 'B': 200}, ki_type='Non-KI',
                 daily_prices={D1: {'A': 90, 'B': 180},
                               D2: {'A': 90, 'B': 180},
                               D3: {'A': 90, 'B': 120}})
    assert r.worst_ratio == pytest.approx(.6)
    assert r.principal_recovery_ratio == pytest.approx(.75)


@pytest.mark.parametrize('kind', ['AKI', 'EKI', 'Non-KI'])
def test_early_ko_returns_par_and_ignores_later_losses(kind):
    r = evaluate(ki_type=kind, daily_prices={
        D1: {'A': 50, 'B': 50}, D2: {'A': 100, 'B': 100},
        D3: {'A': 20, 'B': 20}})
    assert not r.issues
    assert r.ko_date == D2
    assert r.principal_recovery_ratio == 1
    assert r.total_return_rate == pytest.approx(.01 * 2 / 3)


def test_unmatured_aki_does_not_claim_principal_settlement():
    r = evaluate(ki_type='AKI', as_of=D2, daily_prices={
        D1: {'A': 50, 'B': 90}, D2: {'A': 90, 'B': 90}})
    assert r.ki_touched is True
    assert r.principal_recovery_ratio is None
    assert r.total_return_rate is None


@pytest.mark.parametrize('missing', [D1, D3])
def test_missing_observation_blocks_redemption(missing):
    prices = closes()
    del prices[missing]
    r = evaluate(initial_prices={'A': 100, 'B': 200}, daily_prices=prices)
    assert r.issues
    assert r.principal_recovery_ratio is None
    assert r.total_return_rate is None


@pytest.mark.parametrize('barrier', [1.05, '105%'])
def test_105_percent_ko_is_not_1_point_05_percent(barrier):
    r = evaluate(ko_barrier=barrier, daily_prices={
        D1: {'A': 100, 'B': 100}, D2: {'A': 100, 'B': 100},
        D3: {'A': 105, 'B': 105}})
    assert not r.issues
    assert r.ko_date == D3
    assert r.coupon_total_rate == pytest.approx(.01)


@pytest.mark.parametrize('field', ['strike', 'ki_barrier', 'annual_rate'])
def test_normalized_ratios_above_one_match_explicit_percent(field):
    # A canonical ratio of 1.1 means 110%, for every engine rate field.
    args = dict(ki_type='AKI', daily_prices={
        D1: {'A': 50, 'B': 90}, D2: {'A': 90, 'B': 90},
        D3: {'A': 70, 'B': 70}})
    decimal = evaluate(**args, **{field: 1.1})
    percent = evaluate(**args, **{field: '110%'})
    assert not decimal.issues
    assert decimal == percent


@pytest.mark.parametrize('raw', [1.05, 105, '105%'])
def test_central_model_preserves_105_percent_barrier(raw):
    product = dict(product_id='SYNTHETIC', pricing_date=D1, issue_date=D1,
                   ko_start_date=D2, final_eval_date=D3, maturity_date=date(2026,10,19),
                   ko_barrier_ratio=raw, strike_ratio=.8, ki_barrier_ratio=.6,
                   annual_coupon_rate=.12, ko_type='非記憶式', ki_type='EKI')
    r = model_one(product, [{'ticker':'A', 'initial_price':100}],
                  [(1, D1, D3, date(2026,10,19))],
                  {D1:{'A':100}, D2:{'A':100}, D3:{'A':105}}, [], today=D3)
    assert not r.issues
    assert r.levels['ko'] == pytest.approx(105)
    assert r.ko_date == D3
    assert r.principal_ratio == 1
    assert r.earned_coupon_rate == pytest.approx(.01)

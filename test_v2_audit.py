"""Independent V2 boundary and malformed-input regressions; synthetic data only."""
from datetime import date
import pytest
from v2_portfolio_engine import CouponPeriod, calculate_v2

D1, D2, D3 = date(2026, 10, 14), date(2026, 10, 15), date(2026, 10, 16)


def evaluate(**changes):
    args = dict(pricing_date=D1, ko_start=D2, final_eval=D3,
                initial_prices={'A': 100, 'B': 100},
                daily_prices={D1: {'A': 110, 'B': 90},
                              D2: {'A': 90, 'B': 110},
                              D3: {'A': 90, 'B': 90}},
                ko_barrier=1, strike=.8, ki_barrier=.6,
                ko_type='記憶式', ki_type='EKI', annual_rate=.12,
                periods=[CouponPeriod(1, D1, D3, date(2026, 10, 19))],
                holidays=[], as_of=D3)
    args.update(changes)
    return calculate_v2(**args)


def test_locked_hit_never_carries_into_memory():
    result = evaluate()
    assert not result.issues
    assert result.ko_date is None


@pytest.mark.parametrize('kind, expected', [('記憶式', D3), ('非記憶式', None)])
def test_observation_start_inclusive_and_separate_hits(kind, expected):
    result = evaluate(ko_type=kind, daily_prices={
        D1: {'A': 110, 'B': 110}, D2: {'A': 110, 'B': 90},
        D3: {'A': 90, 'B': 110}})
    assert not result.issues
    assert result.ko_date == expected


def test_simultaneous_hit_on_observation_start():
    result = evaluate(ko_type='非記憶式', daily_prices={
        D1: {'A': 90, 'B': 90}, D2: {'A': 100, 'B': 100}})
    assert result.ko_date == D2
    assert result.coupon_total_rate == pytest.approx(.12 / 12 * 2 / 3)


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -float('inf'), 'bad', True])
def test_invalid_close_never_produces_settlement(bad):
    result = evaluate(daily_prices={D1: {'A': 90, 'B': 90},
                                   D2: {'A': bad, 'B': 110},
                                   D3: {'A': 110, 'B': 110}})
    assert result.issues
    assert result.ko_date is None
    assert result.principal_recovery_ratio is None


@pytest.mark.parametrize('field', ['ko_barrier', 'strike', 'ki_barrier', 'annual_rate'])
@pytest.mark.parametrize('bad', [float('nan'), float('inf'), None, 'bad'])
def test_invalid_terms_return_missing_data(field, bad):
    result = evaluate(**{field: bad})
    assert result.issues
    assert result.principal_recovery_ratio is None


def test_ko_start_cannot_precede_pricing():
    assert evaluate(ko_start=date(2026, 10, 13)).issues


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), True])
def test_invalid_initial_price_is_rejected(bad):
    assert evaluate(initial_prices={'A': bad, 'B': 100}).issues

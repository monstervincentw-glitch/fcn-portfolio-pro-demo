"""Real bounded source snapshot plus explicitly perturbed missing-data cases."""
from copy import deepcopy
from datetime import date
import json
import pytest
from scripts.audit_ko_market import SNAPSHOT, EvidenceReader, audit
from v2_portfolio_adapter import load_models


@pytest.fixture(scope='module')
def evidence(): return json.loads(SNAPSHOT.read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def results(evidence): return {r['product_id']:r for r in audit(evidence)['products']}


@pytest.mark.parametrize('pid,ko,count', [('SB04','2026-01-16',27),('SP43',None,69),('SB19',None,67)])
def test_actual_first_ko_matches_independent_daily_scan(results,pid,ko,count):
    r=results[pid]
    assert r['reference_ko']==r['v2_ko']==ko
    assert r['observed_trading_days']==count
    assert not r['issues'] and not r['missing']
    assert r['principal_ratio']==pytest.approx(r['reference_principal'])
    assert r['coupon_rate']==pytest.approx(sum(p['expected_rate'] for p in r['coupons']))


@pytest.mark.parametrize('pid',['SB04','SP43','SB19'])
def test_actual_initial_prices_match_input_api_and_pricing_close(results,pid):
    assert all(leg['matches_input'] and float(leg['initial_price'])==leg['pricing_close'] for leg in results[pid]['legs'])


@pytest.mark.parametrize('pid',['SB04','SP43','SB19'])
def test_actual_price_dates_preserve_source_row_and_exclude_closures(evidence,results,pid):
    source={r['source_row']:r for r in evidence['market']['rows']}
    r=results[pid]
    for day in r['trace']:
        assert date.fromisoformat(day['date']).weekday()<5
        assert day['date'] not in r['excluded_dates']
        raw=source[day['source_row']]
        assert day['date']==raw['date']
        assert all(price==raw['prices'][ticker] for ticker,price in day['quotes'].items())
        if day['date']<r['ko_start']:
            assert not day['eligible'] and not any(day['memory'].values())


def test_sb04_stops_at_ko_and_never_uses_payment_date(results):
    r=results['SB04']
    assert r['v2_ko']!=r['coupons'][0]['payment']
    assert [p['earned_days'] for p in r['coupons']]==[22,0,0]
    assert r['forecast_rate']==r['coupon_rate']
    assert all(p['未來假設票息率']==0 for p in r['model_coupons'])


def test_sp43_memory_never_completes_all_legs(results):
    assert results['SP43']['first_hits']=={'AVGO':'2026-03-05','NVDA':'2026-04-10','TSLA':None}


def test_sb19_final_ki_and_principal(results):
    r=results['SB19']
    assert r['ko_type']=='非記憶式' and r['ki_touched'] is True
    assert r['principal_ratio']==pytest.approx(.9207194925157197)


@pytest.mark.parametrize('mode',['blank_cell','missing_date'])
def test_perturbed_real_snapshot_missing_observation_is_never_filled(evidence,mode):
    changed=deepcopy(evidence)
    rows=changed['market']['rows']
    if mode=='blank_cell': rows[0]['prices']['MU']=None
    else: rows.pop(0)
    _,models=load_models(EvidenceReader(changed),today=date(2026,10,19))
    assert models['SB04'].issues
    assert models['SB04'].ko_date is None and models['SB04'].principal_ratio is None


def test_legacy_central_ko_cache_does_not_override_real_scan(evidence):
    changed=deepcopy(evidence)
    table=changed['central']['terms']['values'];index=table[0].index('model_ko_date')
    for row in table[1:]: row[index]='2000-01-01'
    _,models=load_models(EvidenceReader(changed),today=date(2026,10,19))
    assert models['SB04'].ko_date==date(2026,1,16)
    assert models['SP43'].ko_date is None and models['SB19'].ko_date is None

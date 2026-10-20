"""Saved live-data evidence and negative controls for the read-only audit."""
from copy import deepcopy
from datetime import date
import json
import pytest
from scripts.audit_central_snapshot import SNAPSHOT, audit, rows, number
from v2_portfolio_engine import to_date
from fcn_central_model import model_one


@pytest.fixture
def snapshot():
    return json.loads(SNAPSHOT.read_text(encoding='utf-8'))


def test_30_products_are_separated_without_fabricated_terms(snapshot):
    result = audit(snapshot)
    assert result['count'] == 30
    assert len(result['complete_basic']) == 11
    assert len(result['incomplete']) == 19
    assert result['errors'] == []
    for row in rows(snapshot, 'inputs'):
        if row[0] in result['incomplete']:
            assert all(v is None or v == '' for v in row[2:13])


@pytest.mark.parametrize('pid', ['SA94','SB04','SP43','SQ29','SR50','SAE9',
                                'SR67','SB19','SP34','SM25','SQ59'])
def test_existing_basic_product_matches_api_and_all_three_periods(snapshot, pid):
    product = next(p for p in audit(snapshot)['complete_basic'] if p['product_id'] == pid)
    assert product['periods'] == 3
    assert product['errors'] == []


def test_terms_api_formulas_link_correct_master_cell(snapshot):
    for row_no, row in enumerate(snapshot['term_formulas']['values'][1:], start=2):
        for col_no, formula in enumerate(row):
            cell = f'{chr(65+col_no)}{row_no}'
            direct = f'IF(\'商品主檔\'!{cell}="","",\'商品主檔\'!{cell})'
            # SM25/SQ59 also guard against an empty product ID; same mapping.
            guarded = f'IF(\'商品主檔\'!$A{row_no}="","",{direct})'
            assert formula in ('=' + direct, '=' + guarded)


def test_audit_detects_original_sa94_missing_ki(snapshot):
    corrupted = deepcopy(snapshot)
    corrupted['terms']['values'][1][10] = None
    assert any('SA94' in err and '不一致' in err for err in audit(corrupted)['errors'])


def test_audit_detects_duplicate_and_missing_period(snapshot):
    corrupted = deepcopy(snapshot)
    target = next(i for i, r in enumerate(corrupted['periods']['values']) if len(r)>1 and r[1]=='SM25')
    corrupted['periods']['values'].pop(target)
    corrupted['legs']['values'].append(corrupted['legs']['values'][1])
    errors = audit(corrupted)['errors']
    assert any('重複鍵' in err for err in errors)
    assert any('SM25' in err and '配息期數' in err for err in errors)


def test_known_terms_and_sm25_first_period(snapshot):
    terms = {r[0]: r for r in rows(snapshot, 'terms')}
    assert number(terms['SA94'][10]) == .75
    assert terms['SA94'][12] == 'EKI'
    for pid in ('SB19', 'SP34', 'SM25'):
        assert terms[pid][11] == '非記憶式'
    assert terms['SP34'][12] == 'Non-KI'
    assert '記憶式' in terms['SQ59'][11]
    assert terms['SQ59'][12] == 'EKI'
    period = next(r for r in rows(snapshot, 'periods') if r[1] == 'SM25' and number(r[2]) == 1)
    assert [to_date(v) for v in period[3:6]] == [date(2026,6,5),date(2026,7,6),date(2026,7,8)]


@pytest.mark.parametrize('pid, category', [('SAE9', '閉鎖中'), ('SR67', '比價中')])
def test_known_lifecycle_does_not_disappear_when_quotes_missing(snapshot, pid, category):
    table = snapshot['terms']['values']
    product = dict(zip(table[0], next(r for r in table[1:] if r[0] == pid)))
    result = model_one(product, [], [], {}, [], today=date(2026,10,19))
    assert result.category == category
    assert result.issues
    assert result.ko_date is None  # No price history => no proven KO claim.

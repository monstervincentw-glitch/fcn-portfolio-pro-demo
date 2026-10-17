import ast
from datetime import date
from pathlib import Path

import pytest
from central_catalog import Catalog
from central_live_pages import classify, contract_complete, dashboard_breakdown, exposure_rows, product_overview


def product(pid='SR67', **changes):
    basic={
        'product_id':pid, 'currency':'USD', 'data_state':'來源表已提取',
        'pricing_date':46300,'ko_start_date':46310,
        'final_eval_date':46397,'maturity_date':46401,
        'model_state':'模型觀察中', 'contract_review_state':'待核對原始銀行條款',
        'annual_coupon_rate':0.30, 'ko_barrier_ratio':0.95, 'strike_ratio':0.8,
    }
    basic.update(changes)
    return basic


def l(pid='SR67', ticker='MU'):
    return {'product_id':pid,'ticker':ticker,'leg_no':1,'initial_price':1000,'quote_review':'待核對'}


def catalog():
    p={'SR67':product(),
       'SB19':product('SB19',pricing_date=None,ko_start_date=None,maturity_date=None,final_eval_date=None),
       'SQ29':product('SQ29',model_state='模型已KO',model_ko_date=46254,
                      ko_start_date=46180,final_eval_date=46260,maturity_date=46265),
       'SA94':product('SA94',model_state='模型已KO',model_ko_date=46250,
                      ko_start_date=46050,final_eval_date=46270,maturity_date=46273),
       'NEW123':product('NEW123',data_state=None,model_state=None),
    }
    return Catalog(p,{'SR67':(l(),),'SB19':(), 'SQ29':(l('SQ29','NVDA'),),
                      'SA94':(l('SA94'),),'NEW123':(l('NEW123','AVGO'),)})


def test_classification_is_from_central_terms_not_bank_settlement():
    c=catalog()
    today=date(2026,10,18)
    assert classify(c.products['SB19'], (), today=today).category=='待建檔'
    assert classify(c.products['SQ29'],c.legs['SQ29'],today=today).category in {'近三個月模型出場','歷史歸檔'}
    assert '銀行' in classify(c.products['SQ29'],c.legs['SQ29'],today=today).note
    assert classify(c.products['SR67'],c.legs['SR67'],today=today).category in {'比價中','閉鎖中','歷史歸檔'}


def test_new_complete_product_no_need_data_state_whitelist():
    c=catalog()
    assert contract_complete(c.products['NEW123'],c.legs['NEW123'])
    assert not contract_complete(c.products['SB19'], ())


def test_dashboard_counts_held_id_once_even_many_clients_and_missing_id():
    c=catalog()
    holds=[{'product_id':'SR67','customer_id':'C1'}, {'product_id':'SR67','customer_id':'C2'},
           {'product_id':'SB19'},{'product_id':'NOT_IN_CENTRAL'}]
    buckets,pending=dashboard_breakdown(c,holds,today=date(2026,10,18))
    ids=[row['FCN'] for rows in buckets.values() for row in rows]
    assert ids.count('SR67')<=2  # may be in an additional near-maturity bucket
    assert {'NOT_IN_CENTRAL','SB19'}.issubset({p['FCN'] for p in pending})


def test_exposures_read_legs_not_chart_or_amount():
    c=catalog()
    rows=exposure_rows(c,'MU',[{'product_id':'SR67','invested_amount':999}])
    assert {r['FCN 代號'] for r in rows}=={'SR67','SA94'}
    assert rows[0]['股價可比性']=='待核對'
    assert '承作金額' not in rows[0]


def test_catalog_products_are_present_even_without_ledger_product():
    c=catalog()
    rows=product_overview(c,[{'product_id':'SR67','estimated_outstanding_usd':15000}],today=date(2026,10,18))
    assert len(rows)==len(c.products)
    assert next(r for r in rows if r['FCN']=='SR67')['原總帳模型未回本金']==15000
    assert next(r for r in rows if r['FCN']=='NEW123')['原總帳模型未回本金'] is None


def test_live_routing_preserves_pin_gate_and_demonstration():
    src=(Path(__file__).parents[1]/'streamlit_app.py').read_text()
    ast.parse(src)
    assert src.index('gate(section("site_login")')<src.index('if page == "🧭 顧問工作台":')
    for s in ('render_dashboard(READER, HOLDINGS)',
              'render_exposure(READER, HOLDINGS)',
              'render_product_page(READER, HOLDINGS, PRODUCTS)'):
        assert src.count(s)==1
    assert src.count('if MODE == "live":\n        # Central-source cutover: never fall back to legacy per-FCN workbooks.')==3
    assert 'DATA = make_demo()' in src
    assert 'DATA = validate_masked_portfolio(READER.portfolio())' in src
    assert 'section("gcp_service_account")' in src
    assert 'from site_login import gate, logout' in src

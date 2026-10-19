"""Verification: FCN terms, shared 526-stock library, protected client ledger."""
from datetime import date
from pathlib import Path

from central_catalog import (
    CENTRAL_CATALOG_ID,STOCK_LIBRARY_ID,load_market_matrix,load_history,
    load_catalog,load_periods,CatalogSchemaError,
)
from fcn_central_model import model_one
from v2_portfolio_adapter import load_models,enrich_new_holdings
import pytest

TODAY=date(2026,10,19)

class FakeReader:
    def __init__(self,prices=((105,221),(97,219)), *, missing=False,unknown=False):
        self.calls=[]
        self.prices=prices
        self.missing=missing
        self.unknown=unknown

    def read(self, sheet_id, a1):
        self.calls.append((sheet_id,a1))
        if sheet_id==STOCK_LIBRARY_ID:
            if a1=="'收盤價矩陣'!A1:TJ1":
                return [['交易日期','AMD','NVDA']] if not self.unknown else [['交易日期','NVDA']]
            if a1=="'收盤價矩陣'!A2:A":
                return [['2026-10-15'],['2026-10-16']]
            if a1=="'收盤價矩陣'!B2:B3":
                return [[x[0]] if not (self.missing and i==0) else [] for i,x in enumerate(self.prices)]
            if a1=="'收盤價矩陣'!C2:C3":
                return [[x[1]] for x in self.prices]
            raise AssertionError('Unexpected stock-library range: '+a1)
        assert sheet_id==CENTRAL_CATALOG_ID,('Old V2 or per-product sheet read!',sheet_id,a1)
        if a1.startswith("'API_商品條款_V1'"):
            return [['product_id','currency','pricing_date','ko_start_date','final_eval_date',
                     'maturity_date','annual_coupon_rate','ko_barrier_ratio',
                     'strike_ratio','ki_barrier_ratio','ko_type','ki_type'],
                    ['TEST01','USD','2026-10-15','2026-10-16','2026-11-16',
                     '2026-11-18',.12,1,.85,.60,'非記憶式','EKI']]
        if a1.startswith("'API_標的_V1'"):
            return [['product_id','leg_no','ticker','initial_price'],['TEST01',1,'AMD',100]]
        if a1.startswith("'配息期'"):
            return [['商品|期別','商品代號','配息期','期初日','期末日','配息日','票息算法','條款核實','備註'],
                    ['TEST01|1','TEST01',1,'2026-10-15','2026-10-16','2026-10-19','','','']]
        if a1.startswith("'市場休市日'"):
            return [['休市日期','類別','備註'],['2026-01-01','NYSE','']]
        if a1.startswith("'商品完整參數輸入'"):
            return [['商品代號','票息計算方式'],['TEST01','固定每期']]
        raise AssertionError('Unexpected central range '+a1)


def test_stock_library_is_the_same_one_as_historical_trial():
    # Verified against the unchanged historical trial: price_library_trial.py.
    assert STOCK_LIBRARY_ID=='1ef0Whr7-bgj37DdOnC7ug8Dyv5Ab92-AMw5n9V18UJY'
    assert STOCK_LIBRARY_ID!=CENTRAL_CATALOG_ID


def test_quotes_date_aligned_and_only_needed_stock_read():
    f=FakeReader()
    prices,latest,all_symbols=load_market_matrix(f,{'AMD'})
    assert latest==date(2026,10,16)
    assert all_symbols=={'AMD','NVDA'}
    assert prices[date(2026,10,15)]['AMD']==105
    assert prices[date(2026,10,16)]['AMD']==97
    assert not any('C2:C' in r for _,r in f.calls)
    assert all(sheet_id==STOCK_LIBRARY_ID for sheet_id,_ in f.calls)


def test_stock_library_missing_quote_remains_null_no_date_shift():
    f=FakeReader(missing=True)
    prices,_,_=load_market_matrix(f,{'AMD'})
    assert prices[date(2026,10,15)]['AMD'] is None
    assert prices[date(2026,10,16)]['AMD']==97


def test_models_join_central_terms_with_stock_library():
    f=FakeReader()
    catalog,models=load_models(f,today=TODAY)
    assert models['TEST01'].state=='比價中'
    assert not models['TEST01'].issues
    assert len(models['TEST01'].quote_rows)==1
    assert models['TEST01'].quote_rows[0]['最新收盤價']==97
    assert {s for s,_ in f.calls}=={STOCK_LIBRARY_ID,CENTRAL_CATALOG_ID}
    assert "'配息期'!A1:I1201" in [a for _,a in f.calls]
    assert not any("'歷史行情_核心'" in a for _,a in f.calls)


def test_one_product_model_applies_to_multiple_customers():
    f=FakeReader()
    rows=enrich_new_holdings(f,[{'product_id':'TEST01','invested_amount':10000,'holding_id':'1',
                                  'estimated_coupon_total':99999},
                                 {'product_id':'TEST01','invested_amount':30000,'holding_id':'2',
                                  'estimated_coupon_total':99999}])
    assert rows[0]['estimated_coupon_total']*3==rows[1]['estimated_coupon_total']
    assert rows[0]['estimated_outstanding']==10000
    assert rows[1]['estimated_outstanding']==30000
    assert rows[0]['estimated_coupon_total']!=99999


def test_price_gap_blocks_legacy_estimate_overwrite():
    f=FakeReader(missing=True)
    original={'product_id':'TEST01','invested_amount':10000,'estimated_coupon_total':101010,'holding_id':'1'}
    row=enrich_new_holdings(f,[original])[0]
    assert row['estimated_coupon_total'] is None
    assert row['v2_issues']
    assert original['estimated_coupon_total']==101010


def test_ticker_not_in_library_reports_missing():
    f=FakeReader(unknown=True)
    _,m=load_models(f,today=TODAY)
    assert '未收錄' in ';'.join(m['TEST01'].issues)
    assert m['TEST01'].principal_ratio is None


def test_history_reader_uses_same_stock_library():
    f=FakeReader()
    pts,missing=load_history(f,['AMD'])
    assert not missing
    assert len(pts)==2
    assert all(ref==STOCK_LIBRARY_ID for ref,_ in f.calls)


def test_untrusted_bank_review_strings_do_not_gate_calculation():
    f=FakeReader()
    _,m=load_models(f,today=TODAY)
    assert not m['TEST01'].issues
    assert m['TEST01'].category=='比價中'


def test_existing_historical_trial_untouched():
    s=(Path(__file__).parent/'streamlit_app.py').read_text(encoding='utf-8')
    assert 'from price_library_trial import render_trial' in s
    assert 'render_trial()' in s
    assert 'render_trial()' in s


def test_production_has_no_old_v2_workbook_or_duplicate_quote_updater():
    here=Path(__file__).parent
    source='\n'.join((here/f).read_text(encoding='utf-8') for f in (
        'v2_portfolio_adapter.py','central_catalog.py','fcn_central_model.py',
        'central_live_pages.py'))
    assert '1pc2O3CB4vp1Tq0CcgfngitpVQsbb64ibSucL3fKFI44' not in source
    assert "'歷史行情_核心'" not in source
    assert 'contract_review_state' not in source
    assert 'quote_review' not in source
    assert not (here/'tools/update_central_prices.py').exists()
    workflow=(here/'.github/workflows/fcn_stock_library_daily.yml').read_text(encoding='utf-8')
    assert 'python update_stock_prices.py' in workflow
    assert 'FCN_PRICE_WRITER_JSON' in workflow
    assert not (here/'.github/workflows/fcn_central_daily.yml').exists()

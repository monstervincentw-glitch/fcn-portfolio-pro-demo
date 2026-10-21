"""Real PIN, loaders, model and forms; only external Sheets I/O is substituted.

Public term/price snapshots are replayed offline. Ledger rows are synthetic.
The random test PIN exists only in memory and is never reported or committed.
"""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import secrets
import time

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest
import sheets_backend as backend
from central_catalog import CENTRAL_CATALOG_ID, STOCK_LIBRARY_ID
from scripts.audit_ko_market import EvidenceReader

ROOT = Path(__file__).parent
PAGES = ['🧭 顧問工作台', '📈 FCN 商品', '🧪 FCN 歷史試打',
         '🔎 股票曝險', '🏠 投資總覽', '👥 客戶投資']


class ReplayReader(backend.SheetsReader):
    def __init__(self, sheet_id, state):
        self.master_sheet_id = sheet_id
        self.state = state

    def read(self, sheet_id, span):
        self.state['reads'].append((sheet_id, span))
        if self.state['failure'] == sheet_id:
            raise backend.SheetConnectionError('Google Sheets API 暫時無法取得資料，請稍後重試。')
        if sheet_id in (CENTRAL_CATALOG_ID, STOCK_LIBRARY_ID):
            return deepcopy(EvidenceReader(self.state['evidence']).read(sheet_id, span))
        for name, prefix in [('customers', "'API_客戶'!"), ('holdings', "'API_持倉'!"),
                             ('products', "'API_商品'!"), ('coupons', "'配息期快取'!"),
                             ('exceptions', "'異常覆寫'!")]:
            if span.startswith(prefix):
                return deepcopy(self.state['ledger'][name])
        raise AssertionError('Unexpected data source')

    def read_many(self, ranges):
        return [self.read(self.master_sheet_id, span) for span in ranges]


@pytest.fixture
def live_app(monkeypatch):
    st.cache_resource.clear()
    evidence = json.loads((ROOT/'docs/audit/evidence/ko-market-20261019.json').read_text('utf-8'))
    central = json.loads((ROOT/'docs/audit/evidence/period-calendar-20261019.json').read_text('utf-8'))
    evidence['central'] = {k: central[k] for k in ('terms', 'legs', 'periods', 'calendar', 'inputs')}
    columns = ['holding_id', 'customer_id', 'product_id', 'currency', 'invested_amount',
               'estimated_settlement_state', 'estimated_principal_total',
               'returned_principal_amount', 'received_coupon_amount']
    state = dict(reads=[], failure=None, evidence=evidence, ledger=dict(
        customers=[['customer_id', 'display_name'], ['測試甲*', '測試甲*'], ['測試乙*', '測試乙*']],
        holdings=[columns,
                  ['TEST-A', '測試甲*', 'SB04', 'USD', 10000, 'OLD', 999999, 0, 12],
                  ['TEST-B', '測試乙*', 'SB04', 'USD', 30000, 'OLD', 999999, None, None],
                  ['TEST-E', '測試甲*', 'SP43', 'EUR', 20000, 'OLD', 999999, 0, 0],
                  ['TEST-J', '測試甲*', 'SB19', 'JPY', 1000000, 'OLD', 999999, 0, 0]],
        products=[['product_id', 'visibility_flag', 'product_currency', 'source_url']],
        coupons=[['商品代號', '期數', '模型本期票息率']],
        exceptions=[['持倉ID', '啟用狀態']]))
    monkeypatch.setattr(backend.SheetsReader, 'from_secrets',
                        lambda svc, sheet_id: ReplayReader(sheet_id, state))
    app = AppTest.from_file(str(ROOT/'streamlit_app.py'), default_timeout=20)
    app.secrets['app'] = dict(mode='live', bank_approved=True, master_sheet_id='SYNTHETIC_LEDGER')
    app.secrets['gcp_service_account'] = {'synthetic': True}
    pin = f'{secrets.randbelow(1_000_000):06d}'
    app.secrets['site_login'] = {'pin': pin}
    app.run()
    assert not state['reads']
    # Exercise rejection first; no gate monkeypatch or authorized-session injection.
    element(app.text_input, '6 位數字 PIN').set_value('invalid')
    element(app.button, '登入 FCN Portfolio Pro').click().run()
    assert not state['reads'] and app.error
    element(app.text_input, '6 位數字 PIN').set_value(pin)
    element(app.button, '登入 FCN Portfolio Pro').click().run()
    assert not app.exception and state['reads']
    yield app, state
    st.cache_resource.clear()


def element(elements, label):
    return next(x for x in elements if x.label == label)


def page(app, name):
    app.sidebar.radio[0].set_value(name).run()
    assert not app.exception


def test_pin_logout_and_expiration_stop_reads(live_app):
    app, state = live_app
    state['reads'].clear()
    element(app.button, '安全登出').click().run()
    assert not state['reads']
    assert element(app.text_input, '6 位數字 PIN')
    element(app.text_input, '6 位數字 PIN').set_value(app.secrets['site_login']['pin'])
    element(app.button, '登入 FCN Portfolio Pro').click().run()
    app.session_state['fcn_last_activity'] = time.monotonic()-1801
    state['reads'].clear()
    app.run()
    assert not state['reads']
    assert element(app.text_input, '6 位數字 PIN')


@pytest.mark.parametrize('entry', ['streamlit_app.py', 'pages/01_📚_中央商品庫.py'])
def test_direct_entry_requires_pin_before_reader_creation(monkeypatch, entry):
    def forbidden(*args, **kwargs):
        pytest.fail('Unauthenticated entry attempted to create the Sheets reader')
    monkeypatch.setattr(backend.SheetsReader, 'from_secrets', forbidden)
    app = AppTest.from_file(str(ROOT/entry), default_timeout=20)
    app.secrets['app'] = dict(mode='live', bank_approved=True, master_sheet_id='SYNTHETIC_LEDGER')
    app.secrets['gcp_service_account'] = {'synthetic': True}
    app.secrets['site_login'] = {'pin': f'{secrets.randbelow(1_000_000):06d}'}
    app.run()
    assert not app.exception and not app.dataframe
    assert element(app.text_input, '6 位數字 PIN')


@pytest.mark.parametrize('name', PAGES[:2]+PAGES[3:])
def test_pages_use_actual_loaders_and_v2(live_app, name):
    app, state = live_app
    original = deepcopy(state['ledger'])
    page(app, name)
    catalog, models = app.session_state['_fcn_v9_catalog_models']
    assert len(catalog.products) == 30
    assert models['SB04'].ko_date == date(2026, 1, 16)
    if name == PAGES[0]:
        app.selectbox(key='central_dashboard_filter').set_value('歷史歸檔').run()
        assert 'SB04' in app.dataframe[0].value.to_string()
        assert int(element(app.metric, '比價中').value) == 0
        state['ledger']['holdings'].append(['TEST-M', '測試甲*', 'MISSING', 'USD', 500, 'OLD', 999999, None, None])
        app.run()
        assert int(element(app.metric, '資料不足').value) == 1
        state['ledger']['holdings'].pop()
    elif name == PAGES[1]:
        app.selectbox(key='central_p_scope').set_value('全部商品').run()
        assert len(app.dataframe[0].value) == 30
        app.selectbox(key='central_p_selected').set_value('SB04').run()
        assert element(app.metric, '模型本金回收比例').value == '100.00%'
        assert '2026/01/16' in app.dataframe[0].value.to_string()
        assert app.get('vega_lite_chart')
    elif name == PAGES[3]:
        app.selectbox(key='exposure_central').set_value('TSLA').run()
        table = app.dataframe[0].value
        row = table.loc[table['FCN'] == 'SB04']
        assert len(row) == 1
        assert row.iloc[0]['存續曝險'] == '無（模型已出場）'
    elif name == PAGES[4]:
        assert [m.value for m in app.metric if m.label == '歷史申購'] == [
            'USD 10,000.00', 'EUR 20,000.00', 'JPY 1,000,000']
        assert [m.value for m in app.metric if m.label == '模型本金回收（已計算）'][0] == 'USD 10,000.00'
        app.selectbox(key='customer').set_value('測試乙*').run()
        assert [m.value for m in app.metric if m.label == '歷史申購'][0] == 'USD 30,000.00'
        assert [m.value for m in app.metric if m.label == '模型本金回收（已計算）'][0] == 'USD 30,000.00'
    else:
        assert len(app.dataframe[0].value) == 3
        app.selectbox(key='customer').set_value('測試乙*').run()
        table = app.dataframe[0].value
        assert len(table) == 1 and table.iloc[0]['投入本金'] == 30000
        assert table.iloc[0]['模型回收本金'] == 30000
        assert table.iloc[0]['模型出場日'] == '2026/01/16'
        assert table.iloc[0]['預估票息'] == pytest.approx(353)
    assert not app.exception
    assert state['ledger'] == original


def submit_history(app, symbols='NVDA,TSLA', day=date(2026, 1, 6)):
    element(app.text_input, '美股標的（1～5 檔）').set_value(symbols)
    element(app.date_input, '期初定價日').set_value(day)
    element(app.button, '讀取 Google Sheets 真實收盤價並試打').click().run()
    assert not app.exception


def test_history_form_calculates_and_retains_session_result(live_app):
    app, state = live_app
    page(app, PAGES[2])
    submit_history(app)
    trial, params, provenance = app.session_state['official_price_trial']
    assert trial['pricing_date'] == date(2026, 1, 6)
    assert trial['principal_return_pct'] is not None
    assert app.get('vega_lite_chart') and app.dataframe
    result = trial['total_profit_amount']
    app.run()
    assert app.session_state['official_price_trial'][0]['total_profit_amount'] == result
    element(app.number_input, '假設本金（USD）').set_value(200000.0)
    submit_history(app)
    assert app.session_state['official_price_trial'][0]['total_profit_amount'] == pytest.approx(result*2)
    assert {s for s, r in state['reads']} <= {'SYNTHETIC_LEDGER', CENTRAL_CATALOG_ID, STOCK_LIBRARY_ID}


@pytest.mark.parametrize('kind', ['empty', 'weekend', 'missing_quote', 'api'])
def test_history_invalid_submission_clears_previous_result(live_app, kind):
    app, state = live_app
    page(app, PAGES[2])
    submit_history(app)
    assert 'official_price_trial' in app.session_state
    if kind == 'api':
        state['failure'] = STOCK_LIBRARY_ID
    if kind == 'missing_quote':
        for row in state['evidence']['market']['rows']:
            if row['date'] == '2026-01-06':
                row['prices']['NVDA'] = None
    submit_history(app, '' if kind == 'empty' else 'NVDA,TSLA',
                   date(2026, 1, 10) if kind == 'weekend' else date(2026, 1, 6))
    assert 'official_price_trial' not in app.session_state
    assert app.error or app.warning


def test_refresh_reloads_ledger_and_never_uses_old_model(live_app):
    app, state = live_app
    page(app, PAGES[5])
    state['ledger']['holdings'][1][4] = 17000
    element(app.button, '🔄 重新讀取中央資料').click().run()
    row = app.dataframe[0].value.iloc[0]
    assert row['投入本金'] == row['模型回收本金'] == 17000
    assert row['預估票息'] == pytest.approx(round(17000*.0117666666667, 2))


def test_partial_model_overview_keeps_known_subtotal_and_only_three_sources(live_app):
    app, state = live_app
    state['ledger']['holdings'].extend([
        ['TEST-DUP', '測試甲*', 'SB04', 'USD', 5000, 'OLD', 999999, 999999, 999999],
        ['TEST-MISSING', '測試甲*', 'MISSING', 'USD', 700, 'OLD', 999999, 999999, 999999],
    ])
    original = deepcopy(state['ledger'])
    state['reads'].clear()
    page(app, PAGES[4])
    assert element(app.metric, '歷史申購').value == 'USD 15,700.00'
    assert element(app.metric, '模型本金回收（已計算）').value == 'USD 15,000.00'
    assert element(app.metric, '模型存續本金（已計算）').value == 'USD 0.00'
    assert any('不能視為完整組合總額' in w.value for w in app.warning)
    app.selectbox(key='customer').set_value('測試乙*').run()
    assert element(app.metric, '模型本金回收（已計算）').value == 'USD 30,000.00'
    app.selectbox(key='customer').set_value('測試甲*').run()
    element(app.button, '🔄 重新讀取中央資料').click().run()
    assert element(app.metric, '模型本金回收（已計算）').value == 'USD 15,000.00'
    app.switch_page('pages/01_📚_中央商品庫.py').run()
    assert not app.exception
    ledger_ranges = {span for sid, span in state['reads'] if sid == 'SYNTHETIC_LEDGER'}
    assert ledger_ranges == {backend.DATA_RANGES['customers'], backend.DATA_RANGES['holdings']}
    assert {sid for sid, _ in state['reads']} == {'SYNTHETIC_LEDGER', CENTRAL_CATALOG_ID, STOCK_LIBRARY_ID}
    assert state['ledger'] == original


def test_active_recovery_is_zero_on_both_customer_pages(live_app, monkeypatch):
    import v2_portfolio_adapter as adapter
    from test_model_only_overview import synthetic_model
    app, _ = live_app
    catalog, _ = app.session_state['_fcn_v9_catalog_models']
    active = synthetic_model('active')
    monkeypatch.setattr(adapter, 'load_models', lambda reader: (catalog, {'SB04': active}))
    page(app, PAGES[4])
    assert element(app.metric, '模型本金回收（已計算）').value == 'USD 0.00'
    assert element(app.metric, '模型存續本金（已計算）').value == 'USD 10,000.00'
    assert element(app.metric, '模型累計票息（已計算）').value == 'USD 0.00'
    page(app, PAGES[5])
    row = app.dataframe[0].value.query("FCN == 'SB04'").iloc[0]
    assert row['模型回收本金'] == 0 and row['模型存續本金'] == 10000
    assert row['預估票息'] == 0


@pytest.mark.parametrize('failed_source', [CENTRAL_CATALOG_ID, STOCK_LIBRARY_ID, 'SYNTHETIC_LEDGER'])
def test_outage_does_not_render_old_success(live_app, failed_source):
    app, state = live_app
    state['failure'] = failed_source
    state['reads'].clear()
    app.run()
    assert not app.exception
    assert app.error or app.warning or app.info
    if failed_source == CENTRAL_CATALOG_ID:
        assert '_fcn_v9_catalog_models' not in app.session_state
        assert sum(s == CENTRAL_CATALOG_ID for s, r in state['reads']) == 1
    elif failed_source == STOCK_LIBRARY_ID:
        models = app.session_state['_fcn_v9_catalog_models'][1]
        assert models['SB04'].ko_date is None and models['SB04'].issues
    else:
        assert not app.dataframe


def test_native_catalog_page_refreshes_shared_model_and_customer_amounts(live_app):
    app, state = live_app
    old = app.session_state['_fcn_v9_catalog_models']
    state['ledger']['holdings'][1][4] = 17000
    state['reads'].clear()
    app.switch_page('pages/01_📚_中央商品庫.py').run()
    assert not app.exception
    assert any(s == CENTRAL_CATALOG_ID for s, r in state['reads'])
    assert app.session_state['_fcn_v9_catalog_models'] is not old
    app.selectbox(key='central_p_scope').set_value('全部商品').run()
    app.selectbox(key='central_p_selected').set_value('SB04').run()
    tables = [x.value for x in app.dataframe]
    assert not any('999999' in t.to_string() for t in tables)
    state['failure'] = CENTRAL_CATALOG_ID
    app.run()
    assert '_fcn_v9_catalog_models' not in app.session_state
    assert app.error


@pytest.mark.parametrize('problem', ['empty_customers', 'unmasked', 'unmapped', 'missing_column'])
def test_malformed_ledger_fails_closed(live_app, problem):
    app, state = live_app
    if problem == 'empty_customers':
        state['ledger']['customers'] = [state['ledger']['customers'][0]]
    elif problem == 'unmasked':
        state['ledger']['customers'][1][1] = 'SYNTHETIC_UNMASKED'
    elif problem == 'unmapped':
        state['ledger']['holdings'][1][1] = 'UNMAPPED'
    else:
        state['ledger']['holdings'][0][4] = 'missing_invested_column'
    state['reads'].clear()
    app.run()
    assert not app.exception and app.error
    assert not app.dataframe
    assert not any(s == CENTRAL_CATALOG_ID for s, r in state['reads'])


def test_history_thresholds_and_page_return_keep_actual_result(live_app):
    app, state = live_app
    page(app, PAGES[2])
    element(app.number_input, 'KO (%)').set_value(105.0)
    element(app.number_input, 'Strike (%)').set_value(80.0)
    element(app.selectbox, 'KI 類型').set_value('AKI')
    element(app.number_input, 'KI (%)').set_value(70.0)
    element(app.number_input, '閉鎖月數').set_value(2)
    submit_history(app)
    trial, params, provenance = app.session_state['official_price_trial']
    assert (params.ko_pct, params.strike_pct, params.ki_pct, params.ki_type) == (105, 80, 70, 'AKI')
    assert trial['ko_start'] > trial['pricing_date']
    old = trial['total_profit_amount']
    page(app, PAGES[0])
    page(app, PAGES[2])
    assert app.session_state['official_price_trial'][0]['total_profit_amount'] == old


def test_http_failures_are_sanitized_and_have_timeouts(monkeypatch):
    """Exercise the production HTTP boundary; never perform a real API call."""
    import requests
    import central_catalog as central
    calls = []
    waits = []
    monkeypatch.setattr(central.time, 'sleep', waits.append)
    class Session:
        def get(self, url, params, timeout):
            calls.append(timeout)
            raise requests.exceptions.Timeout('SYNTHETIC_PRIVATE_TRANSPORT_DETAIL')
    reader = backend.SheetsReader('SYNTHETIC_LEDGER', Session())
    for call in (lambda: reader.read('SYNTHETIC_LEDGER', 'A1'),
                 lambda: reader.read_many(['A1'])):
        with pytest.raises(backend.SheetConnectionError) as caught:
            call()
        assert 'SYNTHETIC_PRIVATE' not in str(caught.value)
    with pytest.raises(central.BatchReadError) as caught:
        central.read_bundle(reader, CENTRAL_CATALOG_ID, ['A1'])
    assert 'SYNTHETIC_PRIVATE' not in str(caught.value)
    assert calls == [25, 35, 45, 45, 45] and waits == [1.5, 3.0]


def test_http_rate_limit_retry_is_bounded(monkeypatch):
    import central_catalog as central
    calls, waits = [], []
    class Response:
        status_code = 429
    class Session:
        def get(self, url, params, timeout):
            calls.append(timeout)
            return Response()
    monkeypatch.setattr(central.time, 'sleep', waits.append)
    with pytest.raises(central.BatchReadError, match='429'):
        central.read_bundle(backend.SheetsReader('SYNTHETIC', Session()),
                            CENTRAL_CATALOG_ID, ['A1'])
    assert calls == [45, 45, 45] and waits == [1.5, 3.0]

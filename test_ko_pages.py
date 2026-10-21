"""Render real page routing with synthetic inputs; production auth is untouched."""
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
import site_login
import sheets_backend
import v2_portfolio_adapter as adapter
import price_library_trial
from test_ko_lifecycle import CATALOG, holdings, model


@pytest.mark.parametrize('page', ['🧭 顧問工作台','📈 FCN 商品','🧪 FCN 歷史試打',
                                  '🔎 股票曝險','🏠 投資總覽','👥 客戶投資'])
def test_six_page_routes_with_ko_customer_holdings(monkeypatch,page):
    class Reader:
        def portfolio(self, *, model_only=False):
            assert model_only is True
            return dict(customers=[dict(customer_id='客*',display_name='客*')],
                        holdings=holdings(),products=[],coupons=[],exceptions=[])
    monkeypatch.setattr(site_login,'gate',lambda *a,**kw:None)
    monkeypatch.setattr(sheets_backend.SheetsReader,'from_secrets',lambda *a:Reader())
    monkeypatch.setattr(adapter,'load_models',lambda reader:(CATALOG,{'TEST':model()}))
    # Only history routing is smoke-tested here; its original source is unchanged.
    def history():
        import streamlit as st
        st.info('HISTORY_ROUTE_UNCHANGED')
    monkeypatch.setattr(price_library_trial,'render_trial',history)
    app=AppTest.from_file(str(Path(__file__).parent/'streamlit_app.py'))
    app.secrets['app']={'mode':'live','bank_approved':True,'master_sheet_id':'SYNTHETIC'}
    app.secrets['site_login']={}
    app.secrets['gcp_service_account']={'synthetic':True}
    app.run()
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception
    if page=='🧭 顧問工作台':
        assert next(m.value for m in app.metric if m.label=='比價中')=='0'
        assert next(m.value for m in app.metric if m.label=='近三個月出場')=='1'
    elif page=='📈 FCN 商品':
        assert app.dataframe[0].value.iloc[0]['KO 日']=='2026/10/15'
        assert any(m.label=='模型本金回收比例' and m.value=='100.00%' for m in app.metric)
    elif page=='🔎 股票曝險':
        app.selectbox(key='exposure_central').set_value('A').run()
        assert not app.exception
        assert app.dataframe[0].value.iloc[0]['存續曝險']=='無（模型已出場）'
    elif page=='🏠 投資總覽':
        assert [m.value for m in app.metric if m.label=='歷史申購']==['USD 40,000.00','EUR 20,000.00','JPY 1,000,000']
    elif page=='👥 客戶投資':
        assert len(app.dataframe[0].value)==4
        assert set(app.dataframe[0].value['模型出場日'])=={'2026/10/15'}
        assert set(app.dataframe[0].value['預定本金付款日'])=={'—'}
    else:
        assert any(x.value=='HISTORY_ROUTE_UNCHANGED' for x in app.info)

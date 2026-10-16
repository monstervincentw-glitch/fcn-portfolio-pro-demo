"""Synthetic demo dataset. These are examples, not the user's transactions."""
import datetime as dt

def make_demo():
    customers = [{"customer_id":"示範客戶 A", "display_name":"示範客戶 A"}, {"customer_id":"示範客戶 B", "display_name":"示範客戶 B"}]
    holdings = [
        dict(holding_id="DEMO-1",customer_id="示範客戶 A",product_id="DEMO01",currency="USD",invested_amount=100000,trade_date=dt.date(2026,6,1),estimated_principal_total=100000,estimated_coupon_total=2200,estimated_outstanding=0,estimated_pnl=2200,estimated_settlement_state="✅ 系統自動結案",expected_principal_date=dt.date(2026,9,5)),
        dict(holding_id="DEMO-2",customer_id="示範客戶 A",product_id="DEMO02",currency="EUR",invested_amount=120000,trade_date=dt.date(2026,9,30),estimated_principal_total=None,estimated_coupon_total=0,estimated_outstanding=120000,estimated_pnl=None,estimated_settlement_state="⏳ 尚未到預估結算日",expected_principal_date=dt.date(2027,1,15)),
        dict(holding_id="DEMO-3",customer_id="示範客戶 B",product_id="DEMO03",currency="JPY",invested_amount=10000000,trade_date=dt.date(2026,5,10),estimated_principal_total=None,estimated_coupon_total=None,estimated_outstanding=None,estimated_pnl=None,estimated_settlement_state="⚠️ 商品條款不足",expected_principal_date=None),
    ]
    products = [dict(product_id="DEMO01",product_currency="USD",model_state="🎊 已提前KO",visibility_flag="✅ 顯示中",monitor_group="結束後三個月追蹤",invested_usd=100000,estimated_outstanding_usd=0,source_connection="✅ 已連線",customer_ids="示範客戶 A",ko_date=dt.date(2026,9,1)),dict(product_id="DEMO02",product_currency="EUR",model_state="📈 執行中",visibility_flag="✅ 顯示中",monitor_group="持續監控",invested_eur=120000,estimated_outstanding_eur=120000,source_connection="✅ 已連線",customer_ids="示範客戶 A",maturity_date=dt.date(2027,1,10)),dict(product_id="DEMO03",product_currency="JPY",model_state="⚠️ 商品條款待建檔",visibility_flag="⚠️ 待建檔",monitor_group="條款待建檔",invested_jpy=10000000,customer_ids="示範客戶 B",source_connection="待建檔")]
    return {"customers":customers,"holdings":holdings,"products":products,"cashflows":[]}

"""Entirely fictional preview data; never substitute for private customer data."""
import datetime as dt

def make_demo():
    today=dt.date.today()
    customers=[{'customer_id':'DEMO-C001'},{'customer_id':'DEMO-C002'}]
    products=[];holdings=[]
    for i,(pid,currency,customer) in enumerate([('DEMO01','USD','DEMO-C001'),('DEMO02','EUR','DEMO-C002')],1):
        products.append({'product_id':pid,'product_currency':currency,'monitor_group':'日常監控','model_state':'尚未結算', 'customer_ids':customer,'source_url':'','ko_date':None,'maturity_date':today+dt.timedelta(days=90),'invested_'+currency.lower():100000.,'estimated_outstanding_'+currency.lower():100000.})
        holdings.append({'holding_id':f'DEMO-H{i}','customer_id':customer,'product_id':pid,'currency':currency,'invested_amount':100000.,'trade_date':today-dt.timedelta(days=28),'expected_principal_date':today+dt.timedelta(days=95),'estimated_principal_total':0.,'estimated_coupon_total':0.,'estimated_outstanding':100000.,'estimated_settlement_state':'尚未結算'})
    return {'customers':customers,'holdings':holdings,'products':products,'coupons':[],'exceptions':[]}


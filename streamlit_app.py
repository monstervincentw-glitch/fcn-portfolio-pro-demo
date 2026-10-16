"""FCN Portfolio Pro · bank Edge compatibility demo · fictional data ONLY.
No personal or client data, no external data connections, no write access.
"""
from __future__ import annotations
import datetime as dt
import html
from collections import defaultdict

import pandas as pd
import altair as alt
from demo_charts import demo_chart
import streamlit as st
from demo_utils import currency_summary, product_group
from demo_data import make_demo

st.set_page_config(page_title="FCN Portfolio Pro｜銀行相容測試", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
.block-container{padding-top:1.3rem;padding-bottom:3rem;max-width:1500px}
h1,h2,h3{color:#18324b;letter-spacing:-.025em}
[data-testid="stMetric"]{background:#f0f7f9;border:1px solid #dce9ec;padding:16px 18px;border-radius:12px}
[data-testid="stMetricLabel"]{color:#567078}
[data-testid="stSidebar"]{background:#f3f7f8}
.fcn-banner{background:#123350;color:#fff;border-radius:14px;padding:22px 28px;margin:0 0 22px}
.fcn-banner h1{color:#fff;margin:0;font-size:1.8rem}
.fcn-banner p{margin:9px 0 0;color:#d8e8ee}
.fcn-tag{display:inline-block;border-radius:30px;padding:4px 12px;background:#fff0d6;color:#865c16;font-size:.81rem;font-weight:650}
.fcn-small{color:#667e8b;font-size:.87rem}
.fcn-panel{padding:1rem 1.1rem;border:1px solid #e1eaec;border-radius:12px;margin-bottom:12px}
</style>""", unsafe_allow_html=True)

DATA = make_demo()  # Intentionally synthetic and isolated from real Sheets.
CUSTOMERS = DATA["customers"]
HOLDINGS = DATA["holdings"]
PRODUCTS = DATA["products"]
CURRENCY = ("USD", "EUR", "JPY")

def money(value, currency="USD"):
    return "—" if value is None else f"{currency} {value:,.2f}" if currency != "JPY" else f"JPY {value:,.0f}"

def date_str(x):
    return x.strftime("%Y/%m/%d") if isinstance(x, (dt.date,dt.datetime)) else "—"

def display_status(raw):
    raw = raw or ""
    if "系統自動結案" in raw: return "✅ 自動結案"
    if "條款不足" in raw: return "⚠️ 待建檔"
    if "尚未" in raw: return "⏳ 存續中"
    return raw

with st.sidebar:
    st.markdown("### 📊 FCN Portfolio Pro")
    st.caption("銀行 Edge 相容性驗收版")
    st.warning("**虛構資料 DEMO** · 沒有連接真實 Google Sheets", icon="🔒")
    page = st.radio("功能選單", ["🏠 投資總覽", "👥 客戶投資", "📈 FCN 商品", "📝 例外處理", "🛡️ 銀行驗收"], label_visibility="collapsed")
    st.divider()
    st.caption("標準 HTTPS ｜ Microsoft Edge ｜ USD / EUR / JPY")

st.markdown('<div class="fcn-banner"><h1>FCN Portfolio Pro</h1><p>多客戶結構型商品投資管理 · 合約自動結算 · 異常才修正</p></div>', unsafe_allow_html=True)
st.warning("目前為銀行電腦**畫面及互動驗收版**，所有名稱、價格與金額均為虛構，不含銀行或客戶資料。", icon="🧪")

if page in ("🏠 投資總覽","👥 客戶投資"):
    st.subheader("選擇客戶")
    chosen=st.selectbox("客戶",[x["customer_id"] for x in CUSTOMERS],key="customer")
    rows=[x for x in HOLDINGS if x["customer_id"]==chosen]
    if page=="🏠 投資總覽":
        st.subheader("投資組合摘要")
        groups=currency_summary(rows)
        tabs=st.tabs([f"{cc} 統計" for cc in CURRENCY])
        for tab,cc in zip(tabs,CURRENCY):
            with tab:
                data=groups[cc]
                a,b,c,d=st.columns(4)
                a.metric("歷史申購",money(data["invested"],cc))
                b.metric("推定本金回收",money(data["returned"],cc))
                c.metric("模型可估未回本金",money(data["outstanding"],cc))
                d.metric("自動累計票息",money(data["coupon"],cc))
                if data["pending_count"]:
                    st.info(f"另有 {data['pending_count']} 筆缺商品條款，涉及歷史申購 {money(data['pending_principal'],cc)}。**存續狀態未知**，不可把這些本金當成已返還。")
                elif not data["count"]:st.caption("這位客戶沒有此幣別的申購。")
        st.subheader("近期商品狀態")
        for r in rows: st.write(f"**{r['product_id']}** · {r['currency']} · {display_status(r.get('estimated_settlement_state'))}")
    else:
        st.subheader("客戶完整投資歷史")
        table=[]
        for r in rows:
            table.append({"FCN":r['product_id'],"幣別":r['currency'],"投入本金":r['invested_amount'],"申購日期":date_str(r.get('trade_date')),"推定入帳日":date_str(r.get('expected_principal_date')),"預估回收本金":r.get('estimated_principal_total'),"預估票息":r.get('estimated_coupon_total'),"估算未回本金":r.get('estimated_outstanding'),"結算狀態":display_status(r.get('estimated_settlement_state'))})
        st.dataframe(pd.DataFrame(table),use_container_width=True,hide_index=True,column_config={"投入本金":st.column_config.NumberColumn(format="%.2f"),"預估回收本金":st.column_config.NumberColumn(format="%.2f"),"預估票息":st.column_config.NumberColumn(format="%.2f"),"估算未回本金":st.column_config.NumberColumn(format="%.2f")})
        st.caption("空白表示無法估算，並不代表本金為零。歷史資料不因 KO 或到期三個月而刪除。")
elif page=="📈 FCN 商品":
    st.subheader("跨客戶 FCN 商品監控")
    types=["日常監控","全部商品","待建檔","歷史歸檔"]
    a,b=st.columns([1,2])
    with a:view=st.selectbox("顯示範圍",types)
    with b:term=st.text_input("搜尋商品代號",placeholder="例如 DEMO01")
    data=[]
    for p in PRODUCTS:
        group=product_group(p)
        if view=="日常監控" and group!="日常監控":continue
        if view=="待建檔" and group!="待建檔":continue
        if view=="歷史歸檔" and group!="歷史歸檔":continue
        if term and term.lower() not in p['product_id'].lower():continue
        cc=p.get('product_currency') or 'USD'
        data.append({"商品":p['product_id'],"幣別":cc,"狀態":p.get('model_state'),"分類":p.get('monitor_group'),"參與客戶":p.get('customer_ids'),"累計申購":p.get('invested_'+cc.lower(),0),"模型未回本金":p.get('estimated_outstanding_'+cc.lower()),"KO日期":date_str(p.get('ko_date')),"到期日":date_str(p.get('maturity_date'))})
    st.dataframe(pd.DataFrame(data) if data else pd.DataFrame(columns=['商品','幣別','狀態','分類']),use_container_width=True,hide_index=True)
    if data:
        chosen_product=st.selectbox("開啟商品詳情",[r['商品'] for r in data])
        p=next(x for x in PRODUCTS if x['product_id']==chosen_product)
        st.markdown(f"#### {html.escape(chosen_product)} · {html.escape(p.get('product_currency',''))}")
        st.write("合約狀態：",p.get('model_state'));st.write("監控分類：",p.get('monitor_group'))
        st.write("參與客戶：",p.get('customer_ids'))
        st.divider()
        st.subheader("📉 連結標的走勢圖｜期初價格 = 100%")
        chart_data, settings = demo_chart(chosen_product)
        if chart_data.empty:
            st.info("此商品尚未建立完整條款或走勢資料，暫時無法顯示圖表。")
        else:
            st.warning("⚠️ 以下為虛構的圖表測試資料，不是真實股價、即時行情或投資建議。")
            stocks = sorted(chart_data["stock"].unique().tolist())
            selected_stocks = st.multiselect("圖表顯示標的", stocks, default=stocks, key="chart_stocks_" + chosen_product)
            chart_view = chart_data[chart_data["stock"].isin(selected_stocks)]
            if chart_view.empty:
                st.info("請至少選擇一個連結標的。")
            else:
                domain = [float(chart_view["ratio"].min()), float(chart_view["ratio"].max())]
                for key in ("ko", "strike", "ki"):
                    level = settings.get(key)
                    if level is not None: domain.append(float(level))
                yscale = alt.Scale(domain=[max(0, min(domain)-6), max(domain)+6], zero=False)
                base = alt.Chart(chart_view).encode(
                    x=alt.X("date:T", title="交易日期"),
                    y=alt.Y("ratio:Q", title="相對期初價格（%）", scale=yscale),
                )
                lines = base.mark_line(strokeWidth=2.4).encode(
                    color=alt.Color("stock:N", title="連結標的"),
                    tooltip=[alt.Tooltip("date:T",title="日期",format="%Y/%m/%d"),alt.Tooltip("stock:N",title="標的"),alt.Tooltip("ratio:Q",title="相對期初",format=".2f")],
                )
                rule_rows = [{"level":settings[key],"name":label} for key,label in (("ko","KO"),("strike","Strike"),("ki","KI")) if settings.get(key) is not None]
                overlays = lines
                if rule_rows:
                    rules = alt.Chart(pd.DataFrame(rule_rows)).mark_rule(strokeDash=[6,4],strokeWidth=1.5).encode(
                        y="level:Q",color=alt.Color("name:N",title="參考門檻",scale=alt.Scale(domain=["KO","Strike","KI"],range=["#269e83","#ee9b39","#d85c63"])),
                        tooltip=[alt.Tooltip("name:N",title="門檻"),alt.Tooltip("level:Q",title="相對期初 %",format=".2f")],
                    )
                    overlays = overlays + rules
                if settings.get("ko_start"):
                    obs = pd.DataFrame({"date":[pd.Timestamp(settings["ko_start"])],"event":["KO 觀察起日"]})
                    ko_rule = alt.Chart(obs).mark_rule(color="#57697e",strokeDash=[2,4]).encode(x="date:T",tooltip=["event:N","date:T"])
                    overlays = overlays + ko_rule
                st.altair_chart(overlays.properties(height=390).interactive(),use_container_width=True)
                cols = st.columns(3)
                for box,key,label in zip(cols,("ko","strike","ki"),("KO 門檻","Strike 執行價","KI 門檻")):
                    box.metric(label, "—" if settings.get(key) is None else f"{settings[key]:.1f}%")
                st.caption("折線以期初定價 = 100% 正規化；虛線是示範 KO／KI／Strike 門檻。正式版預計讀取每份 FCN 私有 Google Sheets「Chart」分頁並顯示實際行情更新時間。")
        st.caption("圖表資料來源：目前只有虛構示範資料；尚未連接真實 Google Sheets 或即時行情服務。")
elif page=="📝 例外處理":
    st.subheader("異常才修正，不用逐筆對銀行")
    st.info("正常 FCN 按契約日及 3 個工作日的預設規則推定結算；特殊本金、票息、日期才需例外覆寫。")
    st.markdown("**第一階段是唯讀驗收，不在示範網站中寫入任何總帳。** 正式版的編輯需具備角色授權、操作紀錄和回復能力。")
    exceptions=[r for r in HOLDINGS if "不足" in str(r.get("estimated_settlement_state"))]
    st.dataframe(pd.DataFrame([{"示範持倉":r['holding_id'],"商品":r['product_id'],"幣別":r['currency'],"提示":r.get('estimated_settlement_state')} for r in exceptions]),use_container_width=True,hide_index=True)
else:
    st.subheader("銀行 Microsoft Edge 驗收")
    st.markdown("**銀行電腦只需開啟 HTTPS 網址，不安裝任何外掛或軟體。**")
    checklist=["銀行 Edge 開啟 *.streamlit.app，無憑證警示或公司政策阻擋", "選單、中文字體、表格與圖表可正常顯示", "客戶切換後數字變動；USD/EUR/JPY 不直接加總", "商品日常監控／全部商品／待建檔切換正常", "商品詳情、頁面重新整理均正常", "頁面未要求銀行電腦登入私人 Google 帳號或安裝程式", "測試資料全為虛構，未連正式客戶或銀行資料", "如未來需接客戶資料，先取得銀行資訊安全核准與企業登入"]
    for i,item in enumerate(checklist,1):st.checkbox(f"{i}. {item}",key=f"check_{i}")
    st.caption("畫面上的勾選僅供測試人員記錄，不會寫入雲端。")

st.divider()
st.caption("FCN Portfolio Pro · Streamlit Community Cloud 相容性驗收版 · 無真實客戶資料 · 非銀行核准正式環境")

"""FCN Portfolio Pro · Google Sheets read-only connector.

All pages are protected by a server-side six-digit PIN gate before read.
Google Sheets remain read-only and LIVE mode requires explicit policy approval.
No credential is stored in source code.
"""
from __future__ import annotations
import datetime as dt
import html
from collections import defaultdict

import pandas as pd
import altair as alt
from demo_charts import demo_chart
import streamlit as st
from demo_utils import currency_summary, product_group, num
from sheets_backend import SheetsReader, SheetConnectionError, validate_masked_portfolio
from site_login import gate, logout
from demo_data import make_demo
from advisor_analytics import summarize_portfolio, stock_exposures, rank_quality_issues
from chart_render import build_stock_chart
from warm_theme import apply_theme, login_intro

st.set_page_config(page_title="FCN Portfolio Pro｜正式整合版", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;600;700&display=swap');
:root{--fcn-ink:#1b3045;--fcn-muted:#62798d;--fcn-border:#e0e8ef;--fcn-navy:#132c43;--fcn-teal:#0b7885;--fcn-bg:#f5f8fb}
html,body,[class*="css"],.stApp{font-family:Inter,'Noto Sans TC','Microsoft JhengHei',sans-serif;color:var(--fcn-ink)}
.stApp{background:var(--fcn-bg)}
.block-container{padding-top:1.35rem;padding-bottom:3.5rem;max-width:1420px}
h1,h2,h3{color:#1a344d;letter-spacing:-.025em;font-weight:700}
h2{margin-top:1.15rem}h3{font-size:1.12rem}
[data-testid="stSidebar"]{background:#eef3f8;border-right:1px solid #d9e4ef}
[data-testid="stSidebar"] .block-container{padding-top:1.15rem}
[data-testid="stSidebar"] div[role="radiogroup"] label{border-radius:10px;padding:.48rem .65rem;transition:background .15s}
[data-testid="stSidebar"] div[role="radiogroup"] label:hover{background:#e2edf5}
[data-testid="stMetric"]{background:#fff;border:1px solid var(--fcn-border);box-shadow:0 3px 14px rgba(19,44,67,.035);padding:18px 20px;border-radius:15px}
[data-testid="stMetricLabel"]{color:var(--fcn-muted);font-weight:600}
[data-testid="stMetricValue"]{color:var(--fcn-navy);letter-spacing:-.03em;font-size:clamp(1.25rem,2vw,2.1rem)}
[data-testid="stDataFrame"]{border:1px solid var(--fcn-border);border-radius:12px;overflow:hidden}
[data-testid="stForm"],div[data-testid="stExpander"]{background:#fff;border:1px solid var(--fcn-border);border-radius:14px;padding:12px}
[data-baseweb="input"]>div,[data-baseweb="select"]>div{border-radius:10px!important}
.stButton button[kind="primary"],div[data-testid="stFormSubmitButton"] button[kind="primary"]{background:var(--fcn-teal);border-color:var(--fcn-teal);border-radius:10px;font-weight:700}
.stButton button[kind="primary"]:hover,div[data-testid="stFormSubmitButton"] button[kind="primary"]:hover{background:#075f6b;border-color:#075f6b}
.stButton button{border-radius:10px}
[data-testid="stTabs"] button{font-weight:600}
[data-testid="stAlert"]{border-radius:11px}
.fcn-banner{background:linear-gradient(115deg,#142e46 0%,#1c4760 64%,#147a85 100%);color:white;border-radius:18px;padding:28px 32px;margin:0 0 22px;box-shadow:0 8px 24px rgba(15,44,66,.1);position:relative;overflow:hidden}
.fcn-banner::after{content:"";width:250px;height:250px;border:1px solid rgba(255,255,255,.12);border-radius:50%;position:absolute;right:-50px;top:-100px}
.fcn-banner h1{color:white;margin:0;font-size:clamp(1.55rem,3vw,2.1rem)}
.fcn-banner p{margin:10px 0 0;color:#dcecf1;font-size:.95rem}
.fcn-eyebrow{font-size:.68rem;color:#8cdee5;letter-spacing:.16em;text-transform:uppercase;font-weight:800;margin-bottom:8px}
.fcn-tag{display:inline-block;border-radius:30px;padding:4px 12px;background:#fff0d6;color:#865c16;font-size:.81rem;font-weight:650}
.fcn-small{color:var(--fcn-muted);font-size:.87rem}
.fcn-panel{padding:1rem 1.1rem;background:#fff;border:1px solid var(--fcn-border);border-radius:12px;margin-bottom:12px}
.fcn-divider{height:1px;background:var(--fcn-border);margin:1.5rem 0}
.fcn-section{margin:1.5rem 0 .85rem}.fcn-section strong{font-size:1.1rem;color:#18344c}.fcn-section p{color:var(--fcn-muted);font-size:.86rem;margin:4px 0}
@media(max-width:750px){.block-container{padding:1rem .8rem 2rem}.fcn-banner{padding:20px 20px;border-radius:14px}[data-testid="stMetric"]{padding:12px}}
@media print{[data-testid="stSidebar"],.stButton{display:none!important}.fcn-banner{box-shadow:none}}
</style>""", unsafe_allow_html=True)

apply_theme()

def section(name):
    # Missing secrets must fail closed at the password gate, even in DEMO.
    try:
        return dict(st.secrets.get(name, {}))
    except Exception:
        # Streamlit also raises StreamlitSecretNotFoundError when no secrets file exists.
        # Do not expose an unprotected DEMO when Secrets are absent.
        return {}

login_intro() if "fcn_authorized_session" not in st.session_state else None
gate(section("site_login"), section("app").get("mode", "demo"),
     bank_approved=section("app").get("bank_approved") is True)  # PIN before ANY Sheets read.

APP = section("app")
MODE = str(APP.get("mode", "demo")).strip().lower()
if MODE not in ("demo", "diagnostic", "live"):
    st.error("不支援的資料模式；為保護客戶資料，網站已停止。")
    st.stop()

READER = None
if MODE in ("diagnostic", "live"):
    # Fail closed BEFORE any Sheets API request or client-data UI generation.
    if MODE == "live" and APP.get("bank_approved") is not True:
        st.error("正式資料模式尚未獲確認。請先依銀行資料與雲端使用政策完成核准，再設定 bank_approved = true。")
        st.stop()
    svc = section("gcp_service_account")
    if not svc or not APP.get("master_sheet_id"):
        st.error("Google Sheets 的唯讀服務帳號或總帳 ID 尚未設定。")
        st.stop()
    try:
        READER = SheetsReader.from_secrets(svc, str(APP["master_sheet_id"]))
    except SheetConnectionError as exc:
        st.error(str(exc))
        st.stop()
    if MODE == "diagnostic":
        st.title("🔐 Google Sheets 連線診斷")
        st.caption("只檢查私人總帳的標題列，不展示任何客戶、交易或金額。")
        try:
            results = READER.diagnostic()
            for name, ok in results.items():
                (st.success if ok else st.error)(("✅ " if ok else "❌ ") + name)
            if all(results.values()):
                st.info("連線及欄位測試通過。正式資料顯示仍須經銀行/公司批准，然後才可啟用 live。")
        except SheetConnectionError as exc:
            st.error(str(exc))
        st.button("安全登出", on_click=logout)
        st.stop()
    try:
        DATA = validate_masked_portfolio(READER.portfolio())
    except SheetConnectionError as exc:
        st.error(str(exc))
        st.stop()
else:
    DATA = make_demo()

CUSTOMERS = DATA["customers"]
HOLDINGS = DATA["holdings"]
PRODUCTS = DATA["products"]
CURRENCY = ("USD", "EUR", "JPY")
if not CUSTOMERS:
    st.warning("目前沒有可選擇的客戶。請檢查總帳的客戶名冊。")
    st.stop()

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
    st.markdown("### ◈ FCN Portfolio Pro")
    st.caption("銀行 Edge 專用 · " + ("私人資料唯讀模式" if MODE == "live" else "相容性驗收版"))
    st.success("🔒 6 位數 PIN 已驗證 · 唯讀模式" if MODE != "demo" else "🔒 6 位數 PIN 已驗證 · 虛構資料 DEMO")
    st.button("安全登出", on_click=logout, use_container_width=True)
    if MODE == "demo":
        st.warning("**虛構資料 DEMO** · 沒有連接真實 Google Sheets", icon="🔒")
    else:
        st.caption("Google Sheets 服務帳號僅在伺服器端唯讀使用；不需在銀行電腦登入 Google")
    page = st.radio("功能選單", ["🏠 投資總覽", "🧭 顧問工作台", "🔎 股票曝險", "👥 客戶投資", "📈 FCN 商品", "🧪 FCN 歷史試打", "📝 例外處理", "🛡️ 銀行驗收"], label_visibility="collapsed")
    st.divider()
    st.caption("標準 HTTPS ｜ Microsoft Edge ｜ USD / EUR / JPY")

st.markdown('<div class="fcn-banner"><div class="fcn-eyebrow">Structured Notes · Portfolio Intelligence</div><h1>FCN Portfolio Pro</h1><p>投資組合總覽　／　FCN 商品監控　／　真實歷史股價試打</p></div>', unsafe_allow_html=True)
if MODE == "demo":
    st.warning("目前為銀行電腦**畫面及互動驗收版**，所有名稱、價格與金額均為虛構，不含銀行或客戶資料。", icon="🧪")
else:
    st.info("資料來源：私人 Google Sheets（伺服器端唯讀）。配息與本金是**依合約推定**，並非銀行實際入帳證明。", icon="🔒")

if page == "🧪 FCN 歷史試打":
    from price_library_trial import render_trial
    render_trial()
    st.stop()

if page == "🧭 顧問工作台":
    st.subheader("今日商品風險與資料品質")
    summary = summarize_portfolio(CUSTOMERS, HOLDINGS, PRODUCTS)
    cols=st.columns(4)
    for c,(label,value) in zip(cols,[('商品數',summary['products']),('持倉筆數',summary['holdings']),('待補來源',summary['missing_sources']),('需確認資料',summary['quality_flags'])]):
        c.metric(label, str(value))
    st.caption("風險排序只能根據已連線且有日期標記的行情計算；沒有最新價格就不提供假的 KI 距離。")
    issues=rank_quality_issues(PRODUCTS, HOLDINGS)
    if issues: st.dataframe(pd.DataFrame(issues),use_container_width=True,hide_index=True)
    else: st.success("目前沒有可從唯讀資料推定的品質問題。")
elif page == "🔎 股票曝險":
    st.subheader("股票曝險搜尋")
    st.caption("從現有授權 FCN Chart 分析標的關聯；只有已授權來源才會列入，結果不包含未連線商品。")
    q=st.text_input("股票代號（例如 NVDA）",value="").strip().upper()
    if q:
        exposures=[]
        for p in PRODUCTS:
            if MODE == "live":
                try: chart,_=READER.product_chart(p)
                except SheetConnectionError: continue
            else: chart,_=demo_chart(p['product_id'])
            if not chart.empty and q in chart.stock.astype(str).str.upper().unique():
                exposures.append({'FCN':p['product_id'],'幣別':p.get('product_currency'),'分類':p.get('monitor_group'),'來源': '已授權 Chart' if MODE=='live' else 'DEMO'})
        if exposures:
            st.dataframe(pd.DataFrame(exposures),use_container_width=True,hide_index=True)
            st.caption('多幣別本金不直接加總；此清單不代表全部商品都有授權行情。')
        else: st.info('授權商品中沒有找到此標的；也可能部分商品尚未連線。')
elif page in ("🏠 投資總覽","👥 客戶投資"):

    st.markdown('<div class="fcn-section"><strong>客戶選擇</strong><p>切換客戶查看幣別摘要與完整歷史持倉</p></div>', unsafe_allow_html=True)
    chosen=st.selectbox("客戶",[x["customer_id"] for x in CUSTOMERS],key="customer")
    rows=[x for x in HOLDINGS if x["customer_id"]==chosen]
    if page=="🏠 投資總覽":
        st.markdown('<div class="fcn-section"><strong>投資組合摘要</strong><p>每種幣別分別統計，模型推定與銀行實際入帳不得混淆</p></div>', unsafe_allow_html=True)
        groups=currency_summary(rows)
        tabs=st.tabs([f"{cc} 統計" for cc in CURRENCY])
        for tab,cc in zip(tabs,CURRENCY):
            with tab:
                data=groups[cc]
                a,b=st.columns(2)
                a.metric("歷史申購",money(data["invested"],cc))
                b.metric("推定本金回收",money(data["returned"],cc))
                c,d=st.columns(2)
                c.metric("模型可估未回本金",money(data["outstanding"],cc))
                d.metric("自動累計票息",money(data["coupon"],cc))
                if data["pending_count"]:
                    st.info(f"另有 {data['pending_count']} 筆缺商品條款，涉及歷史申購 {money(data['pending_principal'],cc)}。**存續狀態未知**，不可把這些本金當成已返還。")
                elif not data["count"]:st.caption("這位客戶沒有此幣別的申購。")
        st.subheader("近期商品狀態")
        for r in rows: st.write(f"**{r['product_id']}** · {r['currency']} · {display_status(r.get('estimated_settlement_state'))}")
    else:
        st.markdown('<div class="fcn-section"><strong>客戶完整投資歷史</strong><p>所有 FCN 保留歷史，可查看預估回收日與收益</p></div>', unsafe_allow_html=True)
        table=[]
        for r in rows:
            table.append({"FCN":r['product_id'],"幣別":r['currency'],"投入本金":r['invested_amount'],"申購日期":date_str(r.get('trade_date')),"推定入帳日":date_str(r.get('expected_principal_date')),"預估回收本金":r.get('estimated_principal_total'),"預估票息":r.get('estimated_coupon_total'),"估算未回本金":r.get('estimated_outstanding'),"結算狀態":display_status(r.get('estimated_settlement_state'))})
        st.dataframe(pd.DataFrame(table),use_container_width=True,hide_index=True,column_config={"投入本金":st.column_config.NumberColumn(format="%.2f"),"預估回收本金":st.column_config.NumberColumn(format="%.2f"),"預估票息":st.column_config.NumberColumn(format="%.2f"),"估算未回本金":st.column_config.NumberColumn(format="%.2f")})
        st.caption("空白表示無法估算，並不代表本金為零。歷史資料不因 KO 或到期三個月而刪除。")
        if MODE == "live" and rows:
            st.divider()
            st.subheader("各期配息明細（合約模型）")
            choice=st.selectbox("選擇客戶持倉", [r["holding_id"] for r in rows],
                                format_func=lambda h: next(f"{x['product_id']} · {x.get('currency','')} · {h}" for x in rows if x['holding_id']==h))
            holding=next(x for x in rows if x["holding_id"]==choice)
            periods=[x for x in DATA.get("coupons",[]) if x.get("商品代號")==holding["product_id"] and x.get("契約配息日")]
            items=[]
            for r in periods:
                rate=num(r.get("模型本期票息率"))
                amount=(num(holding.get("invested_amount")) or 0)*rate if rate is not None else None
                items.append({"期數":r.get("期數"),"契約配息日":date_str(r.get("契約配息日")),
                    "系統推定入帳日":date_str(r.get("預估入帳日")),"本期票息率 (%)":rate * 100 if rate is not None else None,
                    "推定票息金額":amount,"資料狀態":r.get("來源狀態")})
            if items:
                st.dataframe(pd.DataFrame(items), hide_index=True, use_container_width=True,
                    column_config={"本期票息率 (%)":st.column_config.NumberColumn(format="%.4f"),
                                   "推定票息金額":st.column_config.NumberColumn(format="%.2f")})
                st.caption("本期票息以百分比顯示，例如 1.4225%。上表是依合約模型估算，未到預估入帳日的票息不代表已收到。")
            else:
                st.info("這檔 FCN 尚無可計算的合約配息期，不能將空白當成已領取 0 元。")
elif page=="📈 FCN 商品":
    st.markdown('<div class="fcn-section"><strong>跨客戶 FCN 商品監控</strong><p>以商品代號搜尋，或切換監控、待建檔與歷史歸檔</p></div>', unsafe_allow_html=True)
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
        if MODE == "live":
            try:
                chart_data, settings = READER.product_chart(p)
            except SheetConnectionError:
                chart_data, settings = pd.DataFrame(), None
                st.warning("這份商品的 Chart 尚無讀取權限或暫時無法載入。請分享該商品檔給服務帳號（Viewer）。")
        else:
            chart_data, settings = demo_chart(chosen_product)
        if chart_data.empty:
            st.info("此商品尚未建立完整條款或走勢資料，暫時無法顯示圖表。")
        else:
            if MODE == "demo":
                st.warning("⚠️ 以下為虛構的圖表測試資料，不是真實股價、即時行情或投資建議。")
            else:
                st.caption("來源：此 FCN 私人 Google Sheets「Chart」工作表。不是交易所直接報價，更新頻率依原試算表。")
            settings = settings or {}
            stocks = sorted(chart_data["stock"].unique().tolist())
            selected_stocks = st.multiselect("圖表顯示標的", stocks, default=stocks, key="chart_stocks_" + chosen_product)
            chart_view = chart_data[chart_data["stock"].isin(selected_stocks)]
            if chart_view.empty:
                st.info("請至少選擇一個連結標的。")
            else:
                stock_plot=build_stock_chart(chart_view, settings, selected_stocks)
                st.altair_chart(stock_plot,use_container_width=True)
                cols = st.columns(3)
                for box,key,label in zip(cols,("ko","strike","ki"),("KO 門檻","Strike 執行價","KI 門檻")):
                    box.metric(label, "—" if settings.get(key) is None else f"{settings[key]:.1f}%")
                last=chart_view["date"].max()
                st.caption("折線以期初定價 = 100% 正規化；KO／KI／Strike 依商品模型。圖表最後資料日期："
                           + (str(pd.Timestamp(last).date()) if pd.notna(last) else "未知")
                           + "。此日期不等於即時行情報價時間。")
        if MODE == "demo":
            st.caption("圖表資料來源：虛構示範資料；尚未連接真實 Google Sheets 或即時行情服務。")
        elif p.get("source_url"):
            st.caption("原始 Chart 已嵌入上方，不需要銀行電腦開啟 Google Sheets。")
elif page=="📝 例外處理":
    st.markdown('<div class="fcn-section"><strong>例外處理與資料品質</strong><p>集中追蹤條款不足與已啟用的人工覆寫</p></div>', unsafe_allow_html=True)
    st.info("正常 FCN 按契約日及 3 個工作日的預設規則推定結算；特殊本金、票息、日期才需例外覆寫。")
    st.markdown("**目前網站完全唯讀，不會直接修改總帳。** 如有例外，在私人 Google Sheets 的『異常覆寫』修改；不需銀行逐筆核實。")
    exceptions=[r for r in HOLDINGS if "不足" in str(r.get("estimated_settlement_state"))]
    st.dataframe(pd.DataFrame([{"持倉":r['holding_id'],"商品":r['product_id'],"幣別":r['currency'],"提示":r.get('estimated_settlement_state')} for r in exceptions]),use_container_width=True,hide_index=True)
    if MODE == "live":
        enabled=[r for r in DATA.get("exceptions", []) if r.get("啟用狀態")=="啟用"]
        st.subheader("已啟用的人工例外（唯讀檢視）")
        st.dataframe(pd.DataFrame([{"持倉ID":r.get("持倉ID"),"FCN":r.get("商品"),"幣別":r.get("幣別"),
            "人工覆寫本金":r.get("覆寫總本金"),"人工覆寫票息":r.get("覆寫總票息"),"說明":r.get("異常說明")}
            for r in enabled]),hide_index=True,use_container_width=True)
        st.caption("若要更正，仍在私人 Google Sheets『異常覆寫』操作；網站目前不開放寫入。")
else:
    st.markdown('<div class="fcn-section"><strong>Microsoft Edge 驗收</strong><p>部署、相容性與資料安全檢核清單</p></div>', unsafe_allow_html=True)
    st.markdown("**銀行電腦只需開啟 HTTPS 網址，不安裝任何外掛或軟體。**")
    checklist=["銀行 Edge 開啟 *.streamlit.app，無憑證警示或公司政策阻擋", "選單、中文字體、表格與圖表可正常顯示", "客戶切換後數字變動；USD/EUR/JPY 不直接加總", "商品日常監控／全部商品／待建檔切換正常", "商品詳情、頁面重新整理均正常", "網站登入方式符合銀行資訊安全政策，不需在銀行電腦安裝程式", "資料處理與部署環境符合銀行規範（公開DEMO僅使用虛構資料）", "正式資料的取用已經過銀行資訊安全核准"]
    for i,item in enumerate(checklist,1):st.checkbox(f"{i}. {item}",key=f"check_{i}")
    st.caption("畫面上的勾選僅供測試人員記錄，不會寫入雲端。")

st.divider()
st.caption("FCN Portfolio Pro · " + ("私人 Google Sheets 唯讀模式（需銀行正式核准）" if MODE=="live" else "Streamlit 相容性驗收版 · 虛構資料")
           + " · USD / EUR / JPY")

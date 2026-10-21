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
from demo_utils import currency_summary, product_group, num, receipt_values
from sheets_backend import SheetsReader, SheetConnectionError, validate_masked_portfolio, DATA_RANGES
from site_login import gate, logout
from demo_data import make_demo
from advisor_analytics import summarize_portfolio, stock_exposures, rank_quality_issues
from risk_monitor import active_product, market_risks
from chart_render import build_stock_chart
from warm_theme import apply_theme, style_chart
from central_live_pages import render_dashboard, render_exposure, render_product_page
from v2_portfolio_adapter import enrich_new_holdings

# Open-ended master ledger API ranges: newly added customer holdings automatically load.
DATA_RANGES["customers"] = "'API_客戶'!A3:I"
DATA_RANGES["holdings"] = "'API_持倉'!A3:AD"
DATA_RANGES["products"] = "'API_商品'!A3:Z"


st.set_page_config(page_title="FCN Portfolio Pro｜V9.1 共用股價庫版", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
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


if MODE == "live":
    DATA["holdings"] = enrich_new_holdings(READER, DATA["holdings"])

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
    st.caption("V9.1 · 共用股價庫版")
    st.caption("銀行 Edge 專用 · " + ("私人資料唯讀模式" if MODE == "live" else "相容性驗收版"))
    st.success("🔒 6 位數 PIN 已驗證 · 唯讀模式" if MODE != "demo" else "🔒 6 位數 PIN 已驗證 · 虛構資料 DEMO")
    st.button("安全登出", on_click=logout, use_container_width=True)
    if MODE == "live":
        st.button("🔄 重新讀取中央資料", use_container_width=True, key="manual_refresh")
    if MODE == "demo":
        st.warning("**虛構資料 DEMO** · 沒有連接真實 Google Sheets", icon="🔒")
    else:
        st.caption("Google Sheets 服務帳號僅在伺服器端唯讀使用；不需在銀行電腦登入 Google")
    page = st.radio("功能選單", ["🧭 顧問工作台", "📈 FCN 商品", "🧪 FCN 歷史試打", "🔎 股票曝險", "🏠 投資總覽", "👥 客戶投資", "📝 例外處理", "🛠️ 系統狀態"], index=0, label_visibility="collapsed")
    st.divider()
    st.caption("標準 HTTPS ｜ Microsoft Edge ｜ USD / EUR / JPY")


st.markdown('<div class="fcn-banner"><div class="fcn-eyebrow">Structured Notes · Portfolio Intelligence</div><h1>FCN Portfolio Pro</h1><p>投資組合總覽 ／ 中央 FCN 動態監控 ／ 成分股歷史試打</p></div>', unsafe_allow_html=True)
if MODE == "demo":
    st.warning("目前為銀行電腦**畫面及互動驗收版**，所有名稱、價格與金額均為虛構，不含銀行或客戶資料。", icon="🧪")
else:
    st.info("商品條款／配息期：中央參數庫；歷史收盤價：與歷史試打共用既有成分股股價庫；客戶持倉：既有總帳。結果皆為模型估算。", icon="🔒")


if page == "🧪 FCN 歷史試打":
    if MODE == "live":
        st.caption("歷史試打沿用既有的 526 檔成分股歷史股價庫；正式商品監控亦共用相同收盤價資料。")
    from price_library_trial import render_trial
    render_trial()
    st.stop()


if page == "🧭 顧問工作台":
    if MODE == "live":
        # Central-source cutover: never fall back to legacy per-FCN workbooks.
        render_dashboard(READER, HOLDINGS)
        st.stop()
    # FCN Dashboard V2: count unique FCN products, never underlying stock lines.
    st.subheader("📋 FCN 商品狀態總覽")
    st.caption("一個 FCN 代號算一檔；即使連結三檔股票，或有多位客戶申購，同一商品也只計一次。")
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    three_months_ago = (pd.Timestamp(today) - pd.DateOffset(months=3)).date()

    def dashboard_date(value):
        if isinstance(value, dt.datetime):
            return value.date()
        if isinstance(value, dt.date):
            return value
        if value is None or str(value).strip() in ("", "—", "#N/A"):
            return None
        # Google Sheets may supply serial dates in the native numeric format.
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if 20000 < value < 110000:
                return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(value))).date()
            return None
        parsed = pd.to_datetime(value, errors="coerce")
        return parsed.date() if pd.notna(parsed) else None

    # 只統計已出現在客戶持倉的 FCN；以商品代號去重，不按客戶或連結股票計數。
    held_ids = {str(h.get("product_id") or "").strip() for h in HOLDINGS}
    products_by_id = {str(p.get("product_id") or "").strip(): p for p in PRODUCTS
                      if str(p.get("product_id") or "").strip() in held_ids}
    group_labels = ("🔒 閉鎖中", "📊 比價中", "🏁 近三個月出場", "📅 近兩週到期")
    lists = {label: [] for label in group_labels}
    unknown = []

    for pid, product in sorted(products_by_id.items()):
        state = str(product.get("model_state") or "")
        monitor_group = str(product.get("monitor_group") or "")
        maturity = dashboard_date(product.get("maturity_date"))
        ko_date = dashboard_date(product.get("ko_date"))
        exit_date = dashboard_date(product.get("end_event_date"))
        is_ko = (ko_date is not None and ko_date <= today) or "已提前KO" in state or "提前贖回" in state
        is_matured = "已到期" in state or (maturity is not None and maturity < today)
        has_exited = is_ko or is_matured

        if has_exited:
            actual_event_day = exit_date or (ko_date if is_ko else maturity)
            # 如商品已結束，但來源日期缺漏，避免把日期不明的商品硬塞進近期清單。
            if actual_event_day and three_months_ago <= actual_event_day <= today:
                kind = "提前 KO" if is_ko else "合約到期"
                lists["🏁 近三個月出場"].append({
                    "FCN 代號": pid, "參考日期": actual_event_day.isoformat(), "事件／狀態": kind
                })
            continue

        if "待建檔" in state or "待建檔" in monitor_group or not maturity:
            unknown.append((pid, "商品條款／到期日不足"))
            continue

        if today <= maturity <= today + dt.timedelta(days=14):
            lists["📅 近兩週到期"].append({
                "FCN 代號": pid, "參考日期": maturity.isoformat(), "事件／狀態": "合約到期日"
            })

        # 閉鎖期界線一定依商品合約 KO 開始觀察日，不用第一檔股票的走勢推算。
        # DEMO uses only demo product data; LIVE already routes to central_live_pages.
        ko_start = dashboard_date(product.get("ko_start_date"))
        if ko_start is None:
            unknown.append((pid, "無法確認 KO 開始觀察日"))
        elif today < ko_start:
            lists["🔒 閉鎖中"].append({
                "FCN 代號": pid, "參考日期": ko_start.isoformat(), "事件／狀態": "KO 開始觀察日"
            })
        else:
            lists["📊 比價中"].append({
                "FCN 代號": pid, "參考日期": ko_start.isoformat(), "事件／狀態": "KO 已開始觀察"
            })

    descriptions = {
        "🔒 閉鎖中": "KO 開始觀察日尚未到，仍處於閉鎖期。",
        "📊 比價中": "已進入 KO 觀察期，且尚未確認提前出場或到期。",
        "🏁 近三個月出場": "自今天起往前推三個月，已提前 KO 或已到期的商品。",
        "📅 近兩週到期": "未出場，且合約到期日位於今天起 14 天內的商品。",
    }
    st.markdown("##### 以商品代號統計｜點選查看 FCN 清單")
    cards = st.columns(4)
    for col, label in zip(cards, group_labels):
        with col:
            st.metric(label, f"{len(lists[label])} 檔")
            if st.button("查看 FCN 代號", key="fcn_advisor_show_" + label, use_container_width=True):
                st.session_state["fcn_advisor_selected_group"] = label

    chosen = st.session_state.get("fcn_advisor_selected_group", group_labels[0])
    if chosen not in lists:
        chosen = group_labels[0]
    st.markdown(f"#### {chosen}｜{len(lists[chosen])} 檔")
    st.caption(descriptions[chosen])
    if lists[chosen]:
        st.dataframe(pd.DataFrame(lists[chosen]), hide_index=True, use_container_width=True)
    else:
        st.info("此分類目前沒有可確認的 FCN。")

    if unknown:
        with st.expander(f"資料待補／分類未確定：{len(unknown)} 檔 FCN（不計入閉鎖或比價）"):
            st.dataframe(pd.DataFrame([{"FCN 代號": pid, "原因": why} for pid, why in unknown]),
                         hide_index=True, use_container_width=True)
            st.caption("未取得合約 KO 開始觀察日時，不自行猜測閉鎖期或比價期。")

    st.caption("「近兩週到期」可同時屬於「比價中」，四項統計不能相加當作總持倉數。")
    st.info("點開上述清單查看 FCN 代號後，可至左側「📈 FCN 商品」查閱各商品條款、連結股票與 KI／KO 走勢。顧問工作台不顯示參與客戶。")
elif page == "🔎 股票曝險":
    if MODE == "live":
        # Central-source cutover: never fall back to legacy per-FCN workbooks.
        render_exposure(READER, HOLDINGS)
        st.stop()
    st.subheader("股票曝險搜尋")
    st.caption("從現有授權 FCN Chart 分析標的關聯；只有已授權來源才會列入，結果不包含未連線商品。")
    q=st.text_input("股票代號（例如 NVDA）",value="").strip().upper()
    if q:
        exposures=[]
        for p in PRODUCTS:
            chart,_=demo_chart(p['product_id'])
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
    if MODE == "live":
        for item in rows:
            if item.get("v2_issues"):
                st.warning(f"{item['product_id']}：V2 資料尚未完整 — {item['v2_issues']}；舊總帳模型值不作為本頁試算結果。")
    if page=="🏠 投資總覽":
        st.markdown('<div class="fcn-section"><strong>投資組合摘要</strong><p>每種幣別分別統計，模型推定與銀行實際入帳不得混淆</p></div>', unsafe_allow_html=True)
        groups=currency_summary(rows)
        tabs=st.tabs([f"{cc} 統計" for cc in CURRENCY])
        for tab,cc in zip(tabs,CURRENCY):
            with tab:
                data=groups[cc]
                a,b=st.columns(2)
                a.metric("歷史申購",money(data["invested"],cc))
                b.metric("模型本金回收",("—" if data["pending_count"]==data["count"] and data["count"] else money(data["returned"],cc)))
                c,d=st.columns(2)
                c.metric("模型存續本金",money(data["outstanding"],cc))
                d.metric("中央模型票息",("—" if data["pending_count"]==data["count"] and data["count"] else money(data["coupon"],cc)))
                e,f,g=st.columns(3)
                e.metric('總帳已收本金',money(data['actual_returned'],cc))
                f.metric('總帳已收配息',money(data['actual_coupon'],cc))
                g.metric('依實收計未回本金',money(data['actual_outstanding'],cc))
                if data["pending_count"]:
                    st.info(f"另有 {data['pending_count']} 筆試算資料待補，已知歷史申購 {money(data['pending_principal'],cc)}。缺漏合計顯示空白，不能從原總帳模型補數。")
                elif not data["count"]:st.caption("這位客戶沒有此幣別的申購。")
        st.subheader("近期商品狀態")
        st.caption('模型存續本金是尚未模型出場的本金；出場損失不列為存續曝險。總帳已收本金與配息僅取原始收款欄，未提供則顯示空白；模型出場不代表實際入帳。')
        for r in rows: st.write(f"**{r['product_id']}** · {r['currency']} · {display_status(r.get('estimated_settlement_state'))}")
    else:
        st.markdown('<div class="fcn-section"><strong>客戶完整投資歷史</strong><p>所有 FCN 保留歷史，可查看預估回收日與收益</p></div>', unsafe_allow_html=True)
        table=[]
        for r in rows:
            table.append({"FCN":r['product_id'],"幣別":r['currency'],"投入本金":r['invested_amount'],"申購日期":date_str(r.get('trade_date')),"模型出場日":date_str(r.get('v2_exit_date')),"預定本金付款日":date_str(r.get('expected_principal_date')),"預估回收本金":r.get('estimated_principal_total'),"預估票息":r.get('estimated_coupon_total'),"模型存續本金":r.get('estimated_outstanding'),"模型本金損失":r.get('v2_principal_loss'),"結算狀態":display_status(r.get('estimated_settlement_state'))})
        st.dataframe(pd.DataFrame(table),use_container_width=True,hide_index=True,column_config={"投入本金":st.column_config.NumberColumn(format="%.2f"),"預估回收本金":st.column_config.NumberColumn(format="%.2f"),"預估票息":st.column_config.NumberColumn(format="%.2f"),"估算未回本金":st.column_config.NumberColumn(format="%.2f")})
        st.caption("空白表示未知，不代表零。KO 是模型出場日，提前 KO 本金付款日尚無來源，不能視為已入帳。歷史資料不因 KO 或到期三個月而刪除。")
        with st.expander('總帳實際收款（與模型分開）'):
            st.dataframe(pd.DataFrame([{'持倉ID':r.get('holding_id'),'FCN':r['product_id'],'幣別':r['currency'],
                '總帳已收本金':receipt_values(r)['actual_returned'],'總帳已收配息':receipt_values(r)['actual_coupon'],
                '依實收計未回本金':receipt_values(r)['actual_outstanding']} for r in rows]),hide_index=True,use_container_width=True)
            st.caption('僅顯示原總帳收款欄；缺漏保持空白。模型結果不會回寫或替代這些紀錄。')
        if MODE == "live" and rows:
            st.divider()
            st.subheader("各期配息明細（合約模型）")
            choice=st.selectbox("選擇客戶持倉", [r["holding_id"] for r in rows],
                                format_func=lambda h: next(f"{x['product_id']} · {x.get('currency','')} · {h}" for x in rows if x['holding_id']==h))
            holding=next(x for x in rows if x["holding_id"]==choice)
            schedule=holding.get("v2_coupon_schedule") or []
            if schedule:
                st.dataframe(pd.DataFrame(schedule), hide_index=True, use_container_width=True)
                st.caption("所有日期與票息來自中央 V2 模型；未來情境票息不代表已收到。")
            else:
                st.info("中央商品資料尚不足以產生逐期模型票息；不改用舊客戶總帳的配息估算。")
elif page=="📈 FCN 商品":
    if MODE == "live":
        # Central-source cutover: never fall back to legacy per-FCN workbooks.
        render_product_page(READER, HOLDINGS, PRODUCTS)
        st.stop()
    st.markdown('<div class="fcn-section"><strong>跨客戶 FCN 商品監控</strong><p>日常監控含存續中與結束後三個月追蹤；可切換全部商品、待建檔與歷史歸檔</p></div>', unsafe_allow_html=True)
    types=["日常監控","全部商品","待建檔","歷史歸檔"]
    a,b=st.columns([1,2])
    with a:view=st.selectbox("顯示範圍",types)
    with b:term=st.text_input("搜尋商品代號",placeholder="例如 DEMO01")
    data=[]
    for p in PRODUCTS:
        group=product_group(p, today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date())
        if view=="日常監控" and group!="日常監控":continue
        if view=="待建檔" and group!="待建檔":continue
        if view=="歷史歸檔" and group!="歷史歸檔":continue
        if term and term.lower() not in p['product_id'].lower():continue
        cc=p.get('product_currency') or 'USD'
        data.append({"商品":p['product_id'],"幣別":cc,"狀態":p.get('model_state'),"分類":p.get('monitor_group'),"累計申購":p.get('invested_'+cc.lower(),0),"模型未回本金":p.get('estimated_outstanding_'+cc.lower()),"KO日期":date_str(p.get('ko_date')),"到期日":date_str(p.get('maturity_date'))})
    st.dataframe(pd.DataFrame(data) if data else pd.DataFrame(columns=['商品','幣別','狀態','分類']),use_container_width=True,hide_index=True)
    if not data:
        st.info("此篩選目前沒有符合的商品。可切換『全部商品』確認來源資料；日常監控包含存續中及結束後三個月內的 FCN。")
    else:
        st.caption(f"目前顯示 {len(data)} 檔商品；商品分類依私人 Google Sheets 原始狀態對應，沒有改寫總帳。")
    if data:
        chosen_product=st.selectbox("開啟商品詳情",[r['商品'] for r in data])
        p=next(x for x in PRODUCTS if x['product_id']==chosen_product)
        st.markdown(f"#### {html.escape(chosen_product)} · {html.escape(p.get('product_currency',''))}")
        st.write("合約狀態：",p.get('model_state'));st.write("監控分類：",p.get('monitor_group'))
        
        st.divider()
        st.subheader("📉 連結標的走勢圖｜期初價格 = 100%")
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
                st.altair_chart(style_chart(stock_plot),use_container_width=True)
                cols = st.columns(3)
                for box,key,label in zip(cols,("ko","strike","ki"),("KO 門檻","Strike 執行價","KI 門檻")):
                    box.metric(label, "—" if settings.get(key) is None else f"{settings[key]:.1f}%")
                last=chart_view["date"].max()
                st.caption("折線以期初定價 = 100% 正規化；KO／KI／Strike 依商品模型。圖表最後資料日期："
                           + (str(pd.Timestamp(last).date()) if pd.notna(last) else "未知")
                           + "。此日期不等於即時行情報價時間。")
        st.caption("圖表資料來源：虛構示範資料。此頁不連接正式資料。");
        from fcn_customer_panel import render_product_clients
        render_product_clients(chosen_product, HOLDINGS, mode=MODE)
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
    st.subheader("🛠️ 系統狀態｜中央聯動資料來源")
    st.caption("商品監控與客戶報表均由伺服器唯讀載入；此頁不提供銀行核約、核價或結算確認功能。")
    st.write("**商品條款與配息**：中央商品參數庫（API_商品條款_V1、API_標的_V1、配息期、商品完整參數輸入）。")
    st.write("**客戶與持倉**：既有客戶總帳，依 product_id 自動匹配中央商品。")
    st.write("**股價來源**：既有 526 檔成分股股價庫（收盤價矩陣）。歷史試打與正式商品監控共用股價，不複製行情。")
    st.write("**每日行情**：原股價庫的 GitHub Actions 排程於美股收盤後增量更新同一份收盤價矩陣；網站僅唯讀。排程需完成 GitHub Secrets 設定後才會執行。")
    st.info("如果商品顯示『資料不足』，請檢查中央必要條款或成分股庫是否包含該股票及完整歷史價；不會以舊商品表、其他來源或零值替補。")


st.divider()
st.caption("FCN Portfolio Pro · " + ("中央商品參數＋獨立客戶總帳（網站唯讀）" if MODE=="live" else "Streamlit 相容性驗收版 · 虛構資料")
           + " · USD / EUR / JPY")

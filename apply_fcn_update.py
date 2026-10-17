#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FCN Portfolio Pro V8.5.5 顧問工作台更新工具。

功能：
1. 顧問工作台：一個 FCN 商品代號只計算一檔，四張可點擊清單的狀態卡。
2. FCN 商品頁：取消所有「參與客戶」資訊顯示。
3. 不修改客戶頁、商品走勢、資料來源、登入/Secrets 或試算表。

使用：將本檔放在與 streamlit_app.py 相同的目錄執行：
    python apply_fcn_update.py
工具將備份原始檔至 streamlit_app.py.before_fcn_dashboard_update.bak。
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path

START = 'if page == "🧭 顧問工作台":'
END = 'elif page == "🔎 股票曝險":'
DETAIL_CUSTOMER = 'st.write("參與客戶：",p.get(\'customer_ids\'))'
TABLE_CUSTOMER = '"參與客戶":p.get(\'customer_ids\'),'

# 使用原有 st、pd、dt、PRODUCTS、HOLDINGS、READER、parse_terms、sheet_id_from_url；
# 不增加 requirements.txt、API 或權限依賴。
NEW_DASHBOARD = '''if page == "🧭 顧問工作台":
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
        ko_start = None
        if MODE == "live" and product.get("source_url"):
            sid = sheet_id_from_url(product.get("source_url"))
            if sid:
                try:
                    terms = parse_terms(READER.read(sid, "'商品條款'!A1:F100"))
                    ko_start = dashboard_date(terms.get("ko_start"))
                except SheetConnectionError:
                    pass
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
'''


def update_source(source: str) -> tuple[str, bool]:
    """Patch exact known locations; reject unknown layouts instead of broad replacements."""
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError("找不到預期的顧問工作台區塊；請確認使用原始 streamlit_app.py。")
    pos = source.index(START)
    end = source.index(END, pos)
    old_workbench = source[pos:end]
    if not ("market_risks(" in old_workbench or "FCN Dashboard V2" in old_workbench):
        raise ValueError("顧問工作台結構與已檢查的版本不同，為避免覆蓋他人修改，已中止。")
    result = source[:pos] + NEW_DASHBOARD + source[end:]
    # Both instances are in the FCN 商品 page; fail closed when unexpected.
    if TABLE_CUSTOMER not in result and '"參與客戶"' in result:
        raise ValueError("FCN 商品的客戶欄位程式碼已變動，請手動確認。")
    result = result.replace(TABLE_CUSTOMER, "")
    result = result.replace(DETAIL_CUSTOMER, "")
    product_start = result.index('elif page=="📈 FCN 商品":')
    product_end = result.index('elif page=="📝 例外處理":', product_start)
    if "參與客戶" in result[product_start:product_end] or "customer_ids" in result[product_start:product_end]:
        raise ValueError("商品頁可能仍會顯示客戶資訊；為安全起見，更新已中止。")
    ast.parse(result, filename="streamlit_app.py")
    return result, result != source


def main() -> None:
    parser = argparse.ArgumentParser(description="更新 FCN 顧問工作台及商品頁客戶隱私")
    parser.add_argument("--target", default="streamlit_app.py", help="網站原程式路徑")
    parser.add_argument("--check-only", action="store_true", help="檢查但不寫入")
    args = parser.parse_args()
    target = Path(args.target).resolve()
    if not target.is_file():
        parser.error(f"找不到 {target}。請把更新工具放在 streamlit_app.py 同一資料夾執行。")
    source = target.read_text(encoding="utf-8-sig")
    updated, changed = update_source(source)
    if not changed:
        print("✅ 已是最新版本；沒有修改。")
        return
    if args.check_only:
        print("✅ 檢查通過：可以更新；目前尚未寫入。")
        return
    backup = target.with_name(target.name + ".before_fcn_dashboard_update.bak")
    if not backup.exists():
        backup.write_text(source, encoding="utf-8")
    target.write_text(updated, encoding="utf-8")
    compile(updated, str(target), "exec")
    print("✅ 更新完成：" + str(target))
    print("✅ 原檔備份：" + str(backup))
    print("✅ 顧問工作台：四項 FCN 去重統計、可點開代號")
    print("✅ FCN 商品：已移除參與客戶欄位及詳情")
    print("✅ 原有登入、Secrets、客戶頁、Google Sheets 設定未變更")


if __name__ == "__main__":
    main()

"""Contract-data action queue for FCN Portfolio Pro.

This module never infers KI/KO from unverified market prices, never confirms bank
settlement, and does not make external API calls. Dates are local calendar dates.
"""
from __future__ import annotations
import datetime as dt
from collections import Counter


def _date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if value is None or str(value).strip().lower() in ('', '—', 'none', 'nan', '#n/a'):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 20000 < value < 110000:
            return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(value))).date()
        return None
    try:
        return dt.date.fromisoformat(str(value).strip()[:10].replace('/', '-'))
    except ValueError:
        return None


def action_queue(products, holdings, today=None, due_within_days=14):
    """Return deterministic review flags, grouped by FCN product ID.

    Output has no financial-advice classification and no inferred market events.
    Items are cues for a professional to check source records, not assertions of
    contract outcome or actual payment receipt.
    """
    today = today or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    if due_within_days < 0:
        raise ValueError('due_within_days must be non-negative')
    held_ids = {str(h.get('product_id') or '').strip() for h in holdings if str(h.get('product_id') or '').strip()}
    by_id = {str(p.get('product_id') or '').strip(): p for p in products if str(p.get('product_id') or '').strip()}
    tasks = []
    def add(rank, typ, pid, why, date=None):
        tasks.append({'優先級': rank, '類別': typ, 'FCN代號': pid, '參考日期': date.isoformat() if date else '', '待辦說明': why})

    for pid in sorted(held_ids):
        p = by_id.get(pid)
        if p is None:
            add('高', '商品資料缺漏', pid, '客戶持倉存在，但找不到對應商品主檔；先核對商品代號與條款')
            continue
        maturity = _date(p.get('maturity_date'))
        ko = _date(p.get('ko_date'))
        state = str(p.get('model_state') or '')
        exit_date = _date(p.get('end_event_date'))
        exited = bool((ko and ko <= today) or '已提前KO' in state or '提前贖回' in state or '已到期' in state or (maturity and maturity < today))
        if not maturity:
            add('高', '商品資料缺漏', pid, '缺少可解析的到期日，不能判定近期到期與完整存續狀態')
        elif not exited and today <= maturity <= today + dt.timedelta(days=due_within_days):
            add('中', '即將到期', pid, '合約到期日接近；核對最終觀察規則及結算安排', maturity)
        if ko and maturity and ko > maturity:
            add('高', '日期衝突', pid, '記錄的 KO 日期晚於合約到期日；請核對原始合約')
        if exit_date and exit_date > today:
            add('中', '日期衝突', pid, '結束事件日期在未來，但已有記錄；核對日期語意')
        if exited and not (ko or exit_date or maturity):
            add('高', '出場證據不足', pid, '標示已出場，但缺少事件日期，無法確認三個月追蹤區間')

    for h in holdings:
        pid = str(h.get('product_id') or '').strip() or '（缺商品代號）'
        hid = str(h.get('holding_id') or '').strip()
        state = str(h.get('estimated_settlement_state') or '')
        when = _date(h.get('expected_principal_date'))
        if any(token in state for token in ('不足', '未知', '待建檔', '無法')):
            add('高', '持倉模型待補', pid, f'持倉 {hid or "（無ID）"}：推定結算狀態待補條款或查核')
        if when and when < today and not any(token in state for token in ('不足', '未知', '無法')):
            # Never label as unpaid: receipt status isn't provided by the model.
            add('低', '推定結算檢視', pid, f'持倉 {hid or "（無ID）"}：推定本金入帳日已過；此提醒不代表尚未入帳', when)
    order = {'高': 0, '中': 1, '低': 2}
    tasks.sort(key=lambda x: (order[x['優先級']], x['FCN代號'], x['類別'], x['參考日期']))
    return tasks


def queue_summary(tasks):
    counts = Counter(t['優先級'] for t in tasks)
    return {'高': counts['高'], '中': counts['中'], '低': counts['低'], '涉及商品數': len({t['FCN代號'] for t in tasks})}

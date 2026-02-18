"""ERP 대시보드 display 헬퍼: structured_data → Order 표시용 속성·경보."""
import json
import datetime
import pytz
from services.erp_policy import (
    STAGE_NAME_TO_CODE,
    STAGE_LABELS,
    can_modify_domain,
    get_assignee_ids,
)
from services.business_calendar import business_days_until


def _ensure_dict(data):
    """JSONB 필드가 문자열로 오인될 경우를 대비해 딕셔너리로 확실히 변환"""
    if not data:
        return {}
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except Exception:
            return {}
    return {}


def apply_erp_display_fields(order):
    """structured_data에서 Order 표시용 속성 채우기 (customer_name, phone, product 등)"""
    if not order or not order.structured_data:
        return
    sd = order.structured_data
    if not isinstance(sd, dict):
        return

    parties = sd.get('parties') or {}
    customer = (parties.get('customer') or {}).get('name')
    if customer:
        order.customer_name = customer
    phone = (parties.get('customer') or {}).get('phone')
    if phone:
        order.phone = phone
    manager_name = (parties.get('manager') or {}).get('name')
    if manager_name:
        order.manager_name = manager_name
    orderer = (parties.get('orderer') or {}).get('name')
    if orderer:
        order.orderer_name = orderer

    site = sd.get('site') or {}
    address_full = site.get('address_full')
    address_main = site.get('address_main')
    address_detail = site.get('address_detail')
    if address_full:
        order.address = address_full
    elif address_main:
        order.address = f"{address_main} {address_detail}".strip() if address_detail else address_main

    items = sd.get('items') or []
    if isinstance(items, list) and items:
        product_parts = []
        for item in items:
            if not isinstance(item, dict):
                continue
            product_name = item.get('product_name')
            if isinstance(product_name, str):
                product_name = product_name.strip()
            else:
                product_name = None
            if not product_name:
                continue
            product_parts.append(product_name)
        if product_parts:
            order.product = ", ".join(product_parts)

    schedule = sd.get('schedule') or {}
    measurement = schedule.get('measurement') or {}
    measurement_date = measurement.get('date')
    if measurement_date:
        order.measurement_date = str(measurement_date)
    measurement_time = measurement.get('time')
    if measurement_time:
        order.measurement_time = measurement_time
    construction = schedule.get('construction') or {}
    construction_date = construction.get('date')
    if construction_date:
        order.scheduled_date = str(construction_date)


def _erp_get_urgent_flag(structured_data):
    try:
        return bool((structured_data or {}).get('flags', {}).get('urgent'))
    except Exception:
        return False


def _erp_get_stage(order, structured_data):
    try:
        st = ((structured_data or {}).get('workflow') or {}).get('stage')
        if st:
            if st in STAGE_LABELS:
                return STAGE_LABELS.get(st)
            stage_code = STAGE_NAME_TO_CODE.get(st, None)
            if stage_code and stage_code in STAGE_LABELS:
                return STAGE_LABELS.get(stage_code)
            for code, label in STAGE_LABELS.items():
                if st.startswith(label) or label.startswith(st.replace('(CS)', '')):
                    return label
            return st
    except Exception:
        pass
    return '주문접수'


def _erp_has_media(order, attachments_count: int):
    return attachments_count > 0


def _erp_alerts(order, structured_data, attachments_count: int):
    urgent = _erp_get_urgent_flag(structured_data)
    meas_date = (((structured_data or {}).get('schedule') or {}).get('measurement') or {}).get('date')
    cons_date = (((structured_data or {}).get('schedule') or {}).get('construction') or {}).get('date')
    try:
        today_kst = datetime.datetime.now(pytz.timezone('Asia/Seoul')).date()
    except Exception:
        today_kst = datetime.date.today()
    meas_d = business_days_until(meas_date, today=today_kst) if meas_date else None
    cons_d = business_days_until(cons_date, today=today_kst) if cons_date else None
    measurement_d4 = meas_d is not None and 0 <= meas_d <= 4
    construction_d3 = cons_d is not None and 0 <= cons_d <= 3
    try:
        stage = ((structured_data or {}).get('workflow') or {}).get('stage')
    except Exception:
        stage = None
    production_d2 = cons_d is not None and 0 <= cons_d <= 2 and stage not in ('CONSTRUCTION',)
    drawing_overdue = False
    try:
        wf = (structured_data or {}).get('workflow') or {}
        st = wf.get('stage')
        stage_updated_at = wf.get('stage_updated_at')
        if st in ('DRAWING', 'CONFIRM') and stage_updated_at:
            ts = datetime.datetime.fromisoformat(str(stage_updated_at))
            delta = datetime.datetime.now() - ts
            drawing_overdue = delta.total_seconds() >= (48 * 3600)
    except Exception:
        drawing_overdue = False
    return {
        'urgent': urgent,
        'measurement_d4': measurement_d4,
        'measurement_days': meas_d,
        'construction_d3': construction_d3,
        'construction_days': cons_d,
        'production_d2': production_d2,
        'production_days': cons_d,
        'drawing_overdue': drawing_overdue
    }


def _sales_domain_fallback_match(user, order, structured_data) -> bool:
    if not user:
        return False
    try:
        sales_assignee_ids = get_assignee_ids(order, 'SALES_DOMAIN')
    except Exception:
        sales_assignee_ids = []
    if sales_assignee_ids:
        return False
    manager_names = set()
    parties = (structured_data.get('parties') or {}) if isinstance(structured_data, dict) else {}
    manager_name_sd = ((parties.get('manager') or {}).get('name') or '').strip()
    if manager_name_sd:
        manager_names.add(manager_name_sd.lower())
    manager_name_col = (order.manager_name or '').strip()
    if manager_name_col:
        manager_names.add(manager_name_col.lower())
    wf_tmp = (structured_data.get('workflow') or {}) if isinstance(structured_data, dict) else {}
    current_quest = (wf_tmp.get('current_quest') or {})
    owner_person = (current_quest.get('owner_person') or '').strip()
    if owner_person:
        manager_names.add(owner_person.lower())
    user_name = (user.name or '').strip().lower()
    user_username = (user.username or '').strip().lower()
    return (user_name in manager_names) or (user_username in manager_names)


def _can_modify_sales_domain(user, order, structured_data, emergency_override=False, override_reason=None) -> bool:
    if not user:
        return False
    if can_modify_domain(user, order, 'SALES_DOMAIN', emergency_override, override_reason):
        return True
    return _sales_domain_fallback_match(user, order, structured_data)


def _drawing_status_label(status: str) -> str:
    code = (status or '').upper()
    return {
        'PENDING': '작업중',
        'TRANSFERRED': '확정 대기',
        'RETURNED': '수정 요청됨',
        'CONFIRMED': '완료',
        'DONE': '완료',
    }.get(code, code or '-')


def _drawing_next_action_text(drawing_status: str, has_assignee: bool) -> str:
    s = (drawing_status or 'PENDING').upper()
    if not has_assignee:
        return '도면 담당자 지정 필요'
    if s == 'TRANSFERRED':
        return '주문 담당 수령 확정 또는 수정 요청'
    if s == 'RETURNED':
        return '도면 담당 수정본 재전달 필요'
    if s in ('CONFIRMED', 'DONE'):
        return '도면 완료 · 다음 단계 확인'
    return '도면 담당 전달 진행'


def apply_erp_display_fields_to_orders(orders, processed_ids=None):
    if not orders:
        return
    if processed_ids is None:
        processed_ids = set()
    for order in orders:
        if order and order.id not in processed_ids:
            apply_erp_display_fields(order)

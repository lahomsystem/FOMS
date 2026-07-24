"""ERP 대시보드 display 헬퍼: structured_data → Order 표시용 속성·경보."""
import datetime
import json
import unicodedata

from foms.services.common.business_calendar import business_days_until
from foms.services.datetime_kst import format_datetime_kst, get_today_kst, now_utc_naive, to_utc_naive
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.erp_policy import (
    STAGE_LABELS,
    STAGE_NAME_TO_CODE,
    can_modify_domain,
    get_assignee_ids,
)

__all__ = [
    "_normalize_for_search",
    "get_today_kst",
    "format_datetime_kst",
    "self_measurement_four_checks_done",
    "_extract_name_candidate",
    "_manager_candidates",
    "_lookup_user_name_from_candidate",
    "normalize_manager_name",
    "clean_dict_like_name",
    "_ensure_dict",
    "_normalize_date_to_yyyymmdd",
    "apply_erp_display_fields",
    "erp_shipping_price_from_structured",
    "_erp_get_urgent_flag",
    "_erp_get_stage",
    "_erp_has_media",
    "_erp_alerts",
    "_sales_domain_fallback_match",
    "_can_modify_sales_domain",
    "_drawing_status_label",
    "_drawing_next_action_text",
    "apply_erp_display_fields_to_orders",
]


def _normalize_for_search(s):
    """검색 매칭용 문자열 정규화 (유니코드 NFC, 공백 정리)."""
    if s is None:
        return ""
    s = str(s).strip()
    if not s:
        return ""
    return unicodedata.normalize("NFC", s)


def self_measurement_four_checks_done(order):
    """자가실측 주문의 4개 필수 체크(실측완료·영업발주 업로드·도면 발송·발주 업로드)가 모두 완료되었는지 반환.
    비자가실측 주문은 False. 실측 대시보드 제외/시공 대시보드 포함 판단에 사용."""
    if not getattr(order, 'is_self_measurement', False):
        return False
    return (
        getattr(order, 'measurement_completed', False)
        and getattr(order, 'regional_sales_order_upload', False)
        and getattr(order, 'regional_blueprint_sent', False)
        and getattr(order, 'regional_order_upload', False)
    )


def _extract_name_candidate(value):
    """이름/ID 후보를 문자열로 정규화한다."""
    if value is None:
        return ''
    if isinstance(value, dict):
        for key in ('name', 'user_name', 'display_name', 'username', 'user_id', 'id'):
            candidate = value.get(key)
            if candidate not in (None, ''):
                return _extract_name_candidate(candidate)
        return ''
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return ''
        if s.startswith('{') and 'name' in s:
            try:
                import ast
                parsed = ast.literal_eval(s)
                return _extract_name_candidate(parsed)
            except Exception:
                return s
        return s
    return str(value).strip()


def _manager_candidates(value):
    """담당자 입력에서 표시명/ID 후보 목록을 수집한다."""
    if value is None:
        return []
    if isinstance(value, dict):
        candidates = []
        for key in ('name', 'user_id', 'id', 'user_name', 'display_name', 'username'):
            cleaned = _extract_name_candidate(value.get(key))
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)
        return candidates
    cleaned = _extract_name_candidate(value)
    return [cleaned] if cleaned else []


def _lookup_user_name_from_candidate(candidate_text):
    """숫자형 담당자 ID 후보를 User.name으로 복구한다."""
    if not candidate_text or not str(candidate_text).isdigit():
        return ''
    try:
        from foms.persistence.main.db import db_session
        from foms.persistence.main.models import User

        user = db_session.query(User).filter(User.id == int(candidate_text)).first()
        if user and getattr(user, 'name', None):
            return str(user.name).strip()
    except Exception:
        return ''
    return ''


def normalize_manager_name(value, fallback=''):
    """담당자 이름을 문자열 표시명으로 정규화한다."""
    candidates = []
    for raw in (value, fallback):
        for cleaned in _manager_candidates(raw):
            if cleaned not in candidates:
                candidates.append(cleaned)

    for candidate in candidates:
        resolved = _lookup_user_name_from_candidate(candidate)
        if resolved:
            return resolved
        if not candidate.isdigit():
            return candidate

    return candidates[0] if candidates else ''


def clean_dict_like_name(value):
    """dict 문자열/숫자형 ID를 담당자 표시명으로 정규화한다."""
    return normalize_manager_name(value)


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


def _normalize_date_to_yyyymmdd(value):
    """실측일/시공일 등 날짜 값을 YYYY-MM-DD 문자열로 통일. 표시 오류(월/일 뒤바뀜 등) 방지."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date().strftime('%Y-%m-%d')
    if isinstance(value, datetime.date):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # 이미 YYYY-MM-DD 형태면 그대로 (앞 10자만 사용해 ISO 시간 제거)
        if len(s) >= 10 and s[4] == '-' and s[7] == '-':
            try:
                datetime.datetime.strptime(s[:10], '%Y-%m-%d')
                return s[:10]
            except ValueError:
                pass
        try:
            dt = datetime.datetime.strptime(s[:10], '%Y-%m-%d')
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            pass
        try:
            dt = datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S')
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            pass
    if isinstance(value, dict):
        y, m, d = value.get('year'), value.get('month'), value.get('day')
        if y is not None and m is not None and d is not None:
            try:
                dt = datetime.date(int(y), int(m), int(d))
                return dt.strftime('%Y-%m-%d')
            except (TypeError, ValueError):
                pass
    return None


def _erp_coerce_item_price_krw(item: dict) -> int:
    """structured_data.items[] 행에서 단가(원) 정수 추출. 클라이언트 erpRecalcItemsTotal과 동일하게 숫자만 파싱."""
    if not isinstance(item, dict):
        return 0
    raw = item.get('price')
    if raw is None or raw is False:
        return 0
    if isinstance(raw, bool):
        return 0
    try:
        if isinstance(raw, (int, float)):
            if raw < 0:
                return 0
            return int(raw) if raw == int(raw) else int(float(raw))
        digits = ''.join(c for c in str(raw) if c.isdigit())
        return int(digits) if digits else 0
    except (TypeError, ValueError):
        return 0


def _erp_coerce_items_total_krw(raw) -> int | None:
    """structured_data.totals.items_total 단일 값 정규화. 불가 시 None."""
    if raw is None or raw is False:
        return None
    if isinstance(raw, bool):
        return None
    try:
        if isinstance(raw, (int, float)):
            if raw < 0:
                return None
            return int(raw) if raw == int(raw) else int(float(raw))
        s = str(raw).strip().replace(',', '')
        if not s:
            return None
        v = int(float(s))
        return max(0, v)
    except (TypeError, ValueError):
        return None


def _erp_coerce_payment_deposit_krw(raw) -> int | None:
    """structured_data.payment.deposit / payments.deposit 값을 원화 정수로 정규화."""
    if raw is None or raw is False:
        return None
    if isinstance(raw, dict):
        if 'amount' in raw:
            return _erp_coerce_payment_deposit_krw(raw.get('amount'))
        if 'raw' in raw:
            return _erp_coerce_payment_deposit_krw(raw.get('raw'))
        return None
    if isinstance(raw, bool):
        return None
    try:
        if isinstance(raw, (int, float)):
            if raw < 0:
                return None
            return int(raw) if raw == int(raw) else int(float(raw))
        digits = ''.join(c for c in str(raw) if c.isdigit())
        return int(digits) if digits else None
    except (TypeError, ValueError):
        return None


def erp_deposit_amount_from_structured(sd: dict) -> int | None:
    """
    ERP 주문 structured_data에서 예약금(선금) 원화 금액을 산출한다.
    웹 클라이언트 `#erp-deposit-amount`와 동일한 payment.deposit 소스.
    """
    if not isinstance(sd, dict):
        return None
    for payment_key in ('payment', 'payments'):
        payment_data = sd.get(payment_key)
        if not isinstance(payment_data, dict) or 'deposit' not in payment_data:
            continue
        coerced = _erp_coerce_payment_deposit_krw(payment_data.get('deposit'))
        if coerced is None:
            return None
        return max(0, coerced)
    return None


def erp_payment_amount_from_structured(sd: dict) -> int | None:
    """
    ERP 주문 structured_data에서 품목 합계(원)를 산출한다.
    웹 클라이언트 `#erp-items-total`은 totals.items_total 또는 품목 price 합과 일치한다.
    """
    if not isinstance(sd, dict):
        return None
    totals = sd.get('totals')
    if isinstance(totals, dict) and 'items_total' in totals:
        coerced = _erp_coerce_items_total_krw(totals.get('items_total'))
        if coerced is not None:
            return coerced
    items = sd.get('items')
    if not isinstance(items, list) or not items:
        return None
    return sum(_erp_coerce_item_price_krw(it) for it in items)


def erp_shipping_price_from_structured(sd: dict) -> int | None:
    """
    ERP 주문 structured_data에서 출고가(원)를 산출한다.

    출고가 = max(0, 품목합 + 자유입력(배송 등) - 할인)로, 읽기전용 요약 표면
    (대시보드 상세·모바일 상세·실측 readonly)이 표시하는 grand total이다.
    잔금 = 출고가 - 예약금 관계를 유지하며, 저장된 totals.items_total(품목합)은
    바꾸지 않고 파생만 한다.

    Args:
        sd: 주문 structured_data(JSONB) 딕셔너리.

    Returns:
        출고가(원) 정수. 품목합(items_total)을 산출할 수 없으면 None.
    """
    items_total = erp_payment_amount_from_structured(sd)
    if items_total is None:
        return None
    # estimate_service를 함수 지역에서 import(모듈 로드 시 순환 import 방지) —
    # dashboard_control_tower와 동일한 파생 소스 사용.
    from foms.services.estimate_service import (
        _extract_discount_amount,
        _extract_free_input_amount,
    )
    free_input = _extract_free_input_amount(sd) if isinstance(sd, dict) else 0
    discount = _extract_discount_amount(sd) if isinstance(sd, dict) else 0
    return max(0, int(items_total) + int(free_input or 0) - int(discount or 0))


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
    raw_manager = parties.get('manager')
    manager_name = normalize_manager_name(raw_manager, getattr(order, 'manager_name', ''))
    if manager_name:
        order.manager_name = manager_name
    elif getattr(order, 'manager_name', None) and isinstance(order.manager_name, str):
        cleaned = clean_dict_like_name(order.manager_name)
        if cleaned != order.manager_name:
            order.manager_name = cleaned
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
    # 실측일: ERP Order일 때만 schedule.measurement.date 사용 (비 ERP 주문은 DB 컬럼 유지, 예: 1843)
    measurement = schedule.get('measurement') or {}
    measurement_date_raw = measurement.get('date')
    measurement_date = _normalize_date_to_yyyymmdd(measurement_date_raw) if measurement_date_raw else None
    is_erp_order = is_erp_order_record(order)
    if is_erp_order and measurement_date:
        order.measurement_date = measurement_date
    measurement_time = measurement.get('time')
    if measurement_time:
        order.measurement_time = measurement_time
    # 시공일: ERP Order일 때만 schedule.construction.date 사용
    construction = schedule.get('construction') or {}
    construction_date_raw = construction.get('date')
    construction_date = _normalize_date_to_yyyymmdd(construction_date_raw) if construction_date_raw else None
    if is_erp_order and construction_date:
        order.scheduled_date = construction_date

    # AS 방문일: ERP Beta / 레거시 공통으로 structured_data의 schedule.as_visit.date 조회
    as_visit = schedule.get('as_visit') or {}
    as_visit_date_raw = as_visit.get('date')
    if as_visit_date_raw:
        order.as_visit_date = _normalize_date_to_yyyymmdd(as_visit_date_raw)
    else:
        order.as_visit_date = None

    # 기존 주문(실측일 컬럼): ERP Beta가 아니거나 schedule.measurement.date 없을 때 DB measurement_date 정규화만
    if not (is_erp_order and measurement_date) and getattr(order, 'measurement_date', None):
        normalized_legacy = _normalize_date_to_yyyymmdd(order.measurement_date)
        if normalized_legacy:
            order.measurement_date = normalized_legacy

    # 결제금액: ERP는 structured payment.deposit(예약금)이 진실값 — #erp-deposit-amount와 동일
    if is_erp_order:
        pa = erp_deposit_amount_from_structured(sd)
        if pa is not None:
            order.payment_amount = pa


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
        pass  # failopen: intentional: 표시 라벨 매칭 실패 시 원본 문자열 폴백
    return '주문접수'


def _erp_has_media(order, attachments_count: int):
    return attachments_count > 0


def _erp_alerts(order, structured_data, attachments_count: int):
    urgent = _erp_get_urgent_flag(structured_data)
    meas_date = (((structured_data or {}).get('schedule') or {}).get('measurement') or {}).get('date')
    cons_date = (((structured_data or {}).get('schedule') or {}).get('construction') or {}).get('date')
    today_kst = get_today_kst()
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
            ts = to_utc_naive(stage_updated_at)
            if ts is not None:
                delta = now_utc_naive() - ts
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
    """주문 목록에 표시용 필드를 한 번씩만 적용한다."""
    if not orders:
        return
    if processed_ids is None:
        processed_ids = set()
    for order in orders:
        if order and order.id not in processed_ids:
            apply_erp_display_fields(order)

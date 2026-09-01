"""
ERP 주문 구조화 데이터 API (structured GET/PUT, parse-text, erp/draft).
"""

import copy
import datetime
import hashlib
import json
import logging
import re
import time
import uuid
from typing import Any, List, Mapping, Optional, Tuple

from flask import Blueprint, g, has_request_context, request, jsonify, session

logger = logging.getLogger(__name__)
from sqlalchemy import text
from sqlalchemy.orm import Session, object_session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, OrderEvent, User
from foms.services.orders.estimate_defaults import (
    ERP_DRAFT_PLACEHOLDER_CUSTOMER,
    ERP_DRAFT_PLACEHOLDER_PHONE,
    ERP_DRAFT_PLACEHOLDER_PRODUCT,
)
from foms.services.orders.as_cycle_view import as_cycle_detail_payload
from foms.services.orders.construction_type import normalize_regional_construction_type
from foms.services.orders.stage_override import normalize_main_stage
from foms.services.orders.status_constants import STATUS
from foms.web.auth import log_access, login_required, role_required
from foms.services.audit_message_display import describe_order_action, summarize_changes
from foms.services.audit_writer import record_access_denied
from foms.services.integrations.naver_commerce.auto_assign import (
    auto_assign_sales_owner_from_manager,
)
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.structured_item_uid import ensure_item_uids
from foms.services.orders.order_field_change_writer import record_field_changes
from foms.services.orders.order_flag_permissions import can_toggle_order_flags
from foms.services.orders.change_reason import is_reason_required
from foms.services.orders.structured_diff import MAX_CHANGES, DiffResult, diff_structured
from foms.services.datetime_kst import now_kst
from foms.services.erp_order_flags import (
    is_erp_draft_structured_data,
    is_erp_order_draft,
    is_erp_order_record,
)
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.structured_form_projection import recompute_totals
from foms.services.orders.erp_automation import apply_auto_tasks
from foms.services.orders.order_text_parser import parse_order_text
from foms.services.geocode_helpers import extract_address_from_structured_data
from foms.services.jobs.queue import enqueue_geocode_order_address
from foms.services.kakao_alimtalk import maybe_send_measure_alimtalk
from foms.services.notifications.drawing_order_change import (
    apply_drawing_order_change_alert,
    finalize_drawing_order_change_alert,
)
from foms.services.notifications.production_change import (
    apply_production_change_alert,
    finalize_production_change_alert,
)
from foms.services.order_geocode import reset_order_geocode_on_address_change
from foms.services.feature_flags import env_bool
from foms.services.erp_inline_patch import apply_field_patch, is_critical_field
from foms.services.order_draft_service import format_updated_at, parse_updated_at
from foms.services.orders.revision import (
    PreconditionRequiredError,
    RevisionConflictError,
    RevisionError,
    execute_order_mutation,
)
from foms.services.orders.structured_form_projection import project_structured_form

#: structured PUT 저장의 mutation 정책 id(receipt policy_id·OrderEvent scope). AUTH-01 manifest
#: 는 이 엔드포인트를 STAFF_MUTATION guard 로 이미 enforce 하므로 route 는 정책 id 만 공유한다.
STRUCTURED_PUT_POLICY_ID = "ERP_STRUCTURED_PUT"

#: ERP 주력 생성 경로(draft → 승격)가 남기는 정본 생성 이벤트. ``create_order()`` 가 쓰는
#: 타입과 같고 payload ``via`` 로 경로를 구분한다(타임라인·감사 질의를 한 타입으로 통일).
ORDER_CREATED_EVENT = "ORDER_CREATED"
#: draft 행이 **처음 만들어진** 시점의 이벤트(설계 결정 ② — 승격 이벤트와 분리).
ORDER_DRAFT_CREATED_EVENT = "ORDER_DRAFT_CREATED"
#: 두 이벤트 payload 의 경로 표기 — 마법사/레거시 폼(``create_order`` 경유)과 구분한다.
ERP_DRAFT_EVENT_VIA = "erp_draft"

_CUSTOMER_PLACEHOLDERS = {ERP_DRAFT_PLACEHOLDER_CUSTOMER}
_PRODUCT_PLACEHOLDERS = {ERP_DRAFT_PLACEHOLDER_PRODUCT}
_ERP_DRAFT_TOKEN_MAX_LENGTH = 128

#: 결제 확인 토글 대상 라벨(감사 문장 부연).
_PAYMENT_TYPE_LABELS = {'deposit': '예약금', 'balance': '잔금'}

erp_orders_structured_bp = Blueprint('erp_orders_structured', __name__, url_prefix='/api')


def _coerce_draft_token(value: Any) -> str:
    """Return a compact draft idempotency token from request data."""
    if not isinstance(value, str):
        return ''
    token = value.strip()
    if not token or len(token) > _ERP_DRAFT_TOKEN_MAX_LENGTH:
        return ''
    return token


def _lock_draft_token_if_supported(db: Session, draft_token: str) -> None:
    """Serialize same-token draft creation on PostgreSQL."""
    if not draft_token:
        return
    try:
        bind = db.get_bind()
        dialect_name = getattr(getattr(bind, 'dialect', None), 'name', '')
        if dialect_name == 'postgresql':
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {'lock_key': f'erp-draft:{draft_token}'},
            )
    except Exception as e:
        logger.warning("draft token lock failed: %s", e, exc_info=True)


def _find_existing_draft_by_token(db: Session, draft_token: str) -> Optional[Order]:
    """Find a still-open draft created by the same browser-page token."""
    if not draft_token:
        return None
    candidates = (
        db.query(Order)
        .filter(Order.status == 'DRAFT', Order.not_deleted_filter())
        .order_by(Order.id.desc())
        .limit(50)
        .all()
    )
    for order in candidates:
        structured_data = order.structured_data if isinstance(order.structured_data, dict) else {}
        meta = structured_data.get('meta') if isinstance(structured_data.get('meta'), dict) else {}
        if meta.get('draft_token') == draft_token and is_erp_order_draft(order):
            return order
    return None


def _first_product_name_from_structured_data(structured_data: dict) -> str:
    items = structured_data.get('items') or []
    if not isinstance(items, list):
        return ''
    for item in items:
        if not isinstance(item, dict):
            continue
        product_name = (item.get('product_name') or item.get('name') or '').strip()
        if product_name:
            return product_name
    return ''


def _missing_required_structured_fields(structured_data: dict) -> list[str]:
    parties = structured_data.get('parties') or {}
    customer = (parties.get('customer') or {}) if isinstance(parties, dict) else {}
    site = structured_data.get('site') or {}

    customer_name = (customer.get('name') or '').strip()
    customer_phone = (customer.get('phone') or '').strip()
    address = (
        (site.get('address_full') or site.get('address_main') or '').strip()
        if isinstance(site, dict) else ''
    )
    product_name = _first_product_name_from_structured_data(structured_data)

    missing = []
    if not customer_name or customer_name in _CUSTOMER_PLACEHOLDERS:
        missing.append('고객명')
    if not customer_phone or customer_phone == ERP_DRAFT_PLACEHOLDER_PHONE:
        missing.append('전화번호')
    if not address or address == '-':
        missing.append('주소')
    if not product_name or product_name in _PRODUCT_PLACEHOLDERS:
        missing.append('제품명')
    return missing


def _get_actor_name(db: Session) -> Optional[str]:
    user_id = session.get('user_id')
    if not user_id:
        return session.get('username')
    user = db.query(User).filter(User.id == user_id).first()
    return user.name if user and getattr(user, 'name', None) else (session.get('username') or None)


def _normalize_construction_workers(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = str(value or '').replace('\n', ',').split(',')
    workers: list[str] = []
    for item in raw_values:
        if isinstance(item, dict):
            raw_name = item.get('name') or item.get('text') or item.get('value') or ''
        else:
            raw_name = item
        name = str(raw_name or '').strip()
        if name and name not in workers:
            workers.append(name)
    return workers


def _preserve_or_normalize_construction_workers(old_sd: dict, structured_data: dict) -> None:
    """Keep shipment construction workers unless the caller explicitly sends the field."""
    shipment = structured_data.get('shipment')
    old_shipment = old_sd.get('shipment') if isinstance(old_sd.get('shipment'), dict) else {}
    old_workers = _normalize_construction_workers(
        old_shipment.get('construction_workers') if isinstance(old_shipment, dict) else None
    )
    if shipment is None:
        if old_workers:
            structured_data['shipment'] = {'construction_workers': old_workers}
        return
    if not isinstance(shipment, dict):
        structured_data['shipment'] = {'construction_workers': old_workers} if old_workers else {}
        return
    if 'construction_workers' not in shipment:
        if old_workers:
            shipment['construction_workers'] = old_workers
        return
    shipment['construction_workers'] = _normalize_construction_workers(
        shipment.get('construction_workers')
    )


_OPERATIONAL_TOP_LEVEL_KEYS = (
    # Drawing lifecycle is managed by dedicated drawing APIs, not by the ERP order form.
    'drawing',
    'blueprint',
    'drawing_status',
    'drawing_transferred',
    'drawing_confirmed_at',
    'drawing_confirmed_by',
    'drawing_current_files',
    'drawing_transfer_history',
    'last_drawing_transfer',
    'drawing_assignees',
    # Estimate preview manual rows are edited from the contract tab, not the main form.
    'estimate_preview',
    # ChannelTalk manual push history (server-managed on /api/channel/push-manual,
    # /api/channel/push-estimate). Never rendered by the form, so preserve across PUTs.
    'channeltalk_push',
    'channeltalk_push_drawing',
    'channeltalk_push_estimate',
    'channeltalk_push_as',
    'channeltalk_push_measure_room',
    # 채널 수집 provenance + 채널이 기록한 결제. 폼은 이 셋을 렌더하지도 보내지도 않는다.
    # 보존 목록에 없으면 **주문을 한 번 열어 저장하는 것만으로 조용히 사라진다** —
    # allowlist(structured_form_projection.enforce_form_allowlist)는 들어온 dict 에서
    # 낯선 키를 걷어낼 뿐, 빠진 옛 키를 되살리지 않는다(strip 목록에도 안 남아 로그가 없다).
    # 2026-08-24 스테이징 실측: 네이버 링크가 붙은 주문 9건 중 ERP 편집 흔적이 있는 5건은
    # 전부 'source' 를 잃었고, 편집이 없던 4건은 전부 남아 있었다(9/9 일치).
    #  · source  — 없으면 주문 편집 화면이 네이버 원본 도크를 아예 렌더하지 않고
    #              (foms/web/orders/edit.py), 대시보드의 채널 취급도 함께 꺼진다
    #              (foms/services/orders/dashboard_read_model.py).
    #  · naver   — 수집 원본 참조(주문번호 등). 버리면 다시 만들 방법이 없다.
    #  · pricing — 붙이기가 기록한 추가결제·재결제 금액이 여기 있다. 폼 저장 한 번에
    #              돈 기록이 통째로 날아가는 자리였다(주문 4485: 1,610,780원 6건).
    #  · naver_linked — 네이버 원본 도크 렌더 게이트(constants.LINKED_MARKER_KEY).
    #              2026-08-28 부터 붙이기는 출처('source')가 아니라 이 키를 켠다 — 출처와
    #              게이트는 뜻이 다르고, ERP 에 직접 등록한 주문(예약금 건)에 재결제를
    #              붙였다고 출처가 네이버가 되지는 않기 때문이다. 여기 없으면 **편집 한 번에
    #              도크가 닫힌다** — 2026-08-24 사고와 정확히 같은 재발 경로다.
    'source',
    'naver',
    'pricing',
    'naver_linked',
)


def _merge_preserving_missing(old_value: Any, incoming_value: Any) -> Any:
    """Deep-merge dicts so form PUTs cannot drop subtrees they do not render."""
    if not isinstance(old_value, dict):
        return copy.deepcopy(incoming_value)
    if not isinstance(incoming_value, dict):
        return copy.deepcopy(old_value)

    merged = copy.deepcopy(old_value)
    for key, value in incoming_value.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _merge_preserving_missing(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


# STATE-FORM-01: 폼 저장은 단계를 바꾸지 않는다(form save ≠ stage change). 폼이 보낸
# workflow.stage 는 서버 현재값으로 고정하고, 단계 전이는 오직 명시적 stage-override
# (STATE-CORE transition) 경로로만 일어난다. 이렇게 하면 stale 탭이 전진/역행/건너뛰기
# 어느 쪽으로도 상태를 덮어쓰지 못한다(암묵 단계전이 0).


def _pin_form_stage_to_server(old_sd: dict, structured_data: dict) -> None:
    """폼 payload 의 workflow.stage 를 서버 현재 단계로 고정한다(단계 불변).

    STATE-FORM-01: structured PUT 은 폼 데이터만 저장하고 단계 전이는 하지 않는다.
    old_sd 에 단계가 있으면 그 값으로 강제해, 폼 select(전진 포함)나 stale 탭이 상태를
    바꾸지 못하게 한다. 실제 단계 변경은 stage-override API(explicit override)만 담당한다.

    Args:
        old_sd: 저장 직전 서버 structured_data(단계 SSOT).
        structured_data: 클라이언트가 보낸 폼 payload(이 자리에서 stage 를 덮어씀).

    Returns:
        None. ``structured_data['workflow']['stage']`` 를 in-place 로 고정한다.
    """
    if not isinstance(old_sd, dict) or not isinstance(structured_data, dict):
        return
    old_wf = old_sd.get("workflow") if isinstance(old_sd.get("workflow"), dict) else {}
    old_stage = old_wf.get("stage")
    if not old_stage:
        return
    wf = structured_data.setdefault("workflow", {})
    if isinstance(wf, dict):
        wf["stage"] = old_stage
    else:
        structured_data["workflow"] = {"stage": old_stage}


#: 실측일이 잡히면 자동 전진하는 출발 단계(전진 1칸만 — RECEIVED → MEASURE).
_AUTO_MEASURE_FROM_STAGES = ('RECEIVED', '주문접수')
#: 실측일 삭제 시 자동 복귀하는 출발 단계(역행 1칸만 — MEASURE → RECEIVED).
_AUTO_RECEIVED_FROM_STAGES = ('MEASURE', '실측')


def _structured_measurement_date(structured_data: dict) -> str:
    """schedule.measurement.date 원문을 공백 제거해 반환한다(없으면 빈 문자열)."""
    if not isinstance(structured_data, dict):
        return ''
    schedule = structured_data.get('schedule')
    measurement = schedule.get('measurement') if isinstance(schedule, dict) else None
    if not isinstance(measurement, dict):
        return ''
    return str(measurement.get('date') or '').strip()


def _structured_orderer_name(structured_data: dict) -> str:
    """parties.orderer.name 원문을 공백 제거해 반환한다(없으면 빈 문자열)."""
    if not isinstance(structured_data, dict):
        return ''
    parties = structured_data.get('parties')
    if not isinstance(parties, dict):
        return ''
    orderer = parties.get('orderer')
    if isinstance(orderer, dict):
        return str(orderer.get('name') or '').strip()
    if isinstance(orderer, str):
        return orderer.strip()
    return ''


def _is_lahom_like_orderer(structured_data: dict) -> bool:
    """라홈(또는 미지정)만 실측일 삭제로 접수 복귀. 하우드·직접입력은 MEASURE 가 기본."""
    name = _structured_orderer_name(structured_data)
    return (not name) or name == '라홈'


def _should_auto_advance_to_measure(order: Order, requested_stage: str = '') -> bool:
    """접수 건을 실측 단계로 올려야 하는지 판정한다(상태는 쓰지 않는다).

    두 경로가 있다(둘 다 출발은 RECEIVED, 목적지는 MEASURE — 전진 1칸뿐):

    1. 실측일 지정: 서버 저장본에 ``schedule.measurement.date`` 가 있으면 자동 전진한다.
    2. 지방주문·자가실측: 실측 일정을 잡지 않는 유형이라 1번 조건이 영원히 성립하지 않는다.
       이 두 유형에 한해, 폼에서 사용자가 단계를 '실측'으로 고른 저장을 전이 의사로 받는다.

    STATE-FORM-01(폼 저장 ≠ 단계 전이)을 지키기 위해 폼 저장 트랜잭션은 단계를
    건드리지 않는다. 이 함수는 커밋된 서버 저장본만 보고 조건을 판정하고, 실제 전이는
    커밋 뒤 canonical 엔진(``SET_MAIN_STAGE``)이 수행한다 — 그래야 STAGE_CHANGED 이벤트·
    outbox·version bump·receipt 가 다른 전이와 동일한 경로로 남는다.

    2번에서 폼 값을 보긴 하지만 그것만으로는 아무 단계도 열리지 않는다. 목적지는 MEASURE
    고정이고, 출발은 서버가 보관한 RECEIVED 여야 하며, 유형 판정(is_regional·
    is_self_measurement)은 서버 컬럼으로 한다. 따라서 stale 탭이 임의 단계를 밀어 넣거나
    역행·건너뛰기를 만들 수 없다.

    Args:
        order: 폼 저장이 커밋된 뒤의 대상 Order.
        requested_stage: 폼이 보낸 workflow.stage 원본(pin 되기 전 값).

    Returns:
        MEASURE 로 전진해야 하면 True.
    """
    if not is_erp_order_record(order):
        return False
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    workflow = sd.get('workflow') if isinstance(sd.get('workflow'), dict) else {}
    if str(workflow.get('stage') or '').strip() not in _AUTO_MEASURE_FROM_STAGES:
        return False
    if _structured_measurement_date(sd):
        return True
    if normalize_main_stage(requested_stage) != 'MEASURE':
        return False
    return bool(getattr(order, 'is_regional', False) or getattr(order, 'is_self_measurement', False))


def _should_auto_regress_to_received(order: Order, had_measurement_date: bool) -> bool:
    """실측일이 지워진 실측 주문을 접수로 되돌릴지 판정한다(상태는 쓰지 않는다).

    자동 전진의 대칭. 이전에 실측일이 있었고 이번 저장에서 비워진 MEASURE 만
    1칸 복귀한다. 실제 전이는 커밋 뒤 canonical 엔진(``SET_MAIN_STAGE``)이 수행한다.
    도면 이후 단계·하우드(실측일 없이 MEASURE 가 정상)는 건드리지 않는다.

    Args:
        order: 폼 저장이 커밋된 뒤의 대상 Order.
        had_measurement_date: 저장 직전 서버에 실측일이 있었는지.

    Returns:
        RECEIVED 로 복귀해야 하면 True.
    """
    if not had_measurement_date:
        return False
    if not is_erp_order_record(order):
        return False
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    if not _is_lahom_like_orderer(sd):
        return False
    workflow = sd.get('workflow') if isinstance(sd.get('workflow'), dict) else {}
    if str(workflow.get('stage') or '').strip() not in _AUTO_RECEIVED_FROM_STAGES:
        return False
    if _structured_measurement_date(sd):
        return False
    return True


def _force_preserve_drawing_transfer_history(old_sd: dict, structured_data: dict) -> None:
    """drawing_transfer_history 는 누적 감사 로그 — 폼 stale 배열로 덮어쓰지 않음.

    서버(old) 이력을 기본으로 두고, 클라이언트 이력이 더 길 때만(신규 append) 수용한다.
    같은 길이 stale 스냅샷이 ack 플래그를 되돌리는 것을 막는다.
    """
    if not isinstance(old_sd, dict) or not isinstance(structured_data, dict):
        return
    old_hist = old_sd.get("drawing_transfer_history")
    if not isinstance(old_hist, list) or not old_hist:
        return
    new_hist = structured_data.get("drawing_transfer_history")
    if not isinstance(new_hist, list) or len(new_hist) <= len(old_hist):
        structured_data["drawing_transfer_history"] = copy.deepcopy(old_hist)


# shipment 하위 AS 서버 전용 키 — 폼은 렌더하지 않고 AS 전용 API 만 쓴다.
_AS_SERVER_OWNED_SHIPMENT_KEYS = ('as_billing', 'as_log')


def _force_preserve_as_server_state(old_sd: dict, structured_data: dict) -> None:
    """shipment 의 AS 서버 전용 키(as_billing·as_log)를 DB 값으로 강제.

    폼 JS 는 shipment 를 페이지 로드 시점 스냅샷에서 통째로 복사해 보낸다. deep-merge 는
    dict 만 병합하고 나머지는 incoming 으로 교체하므로 두 키 모두 stale 스냅샷에 진다 —
    확정된 유상 판정이 무상으로 회귀했고, append-only 인 as_log 는 항목이 통째로 사라졌다.
    as_log 는 접수 모달이 register 직후 erpSaveStructured() 를 호출하는 탓에 방금 만든
    reception/system 항목이 즉시 소실되는 결정적 발현 경로를 갖는다.
    DB 에 값이 없으면 폼이 보낸 값도 채택하지 않는다(서버 전용 키).
    """
    if not isinstance(old_sd, dict) or not isinstance(structured_data, dict):
        return
    new_shipment = structured_data.get('shipment')
    if not isinstance(new_shipment, dict):
        return
    old_shipment = old_sd.get('shipment')
    if not isinstance(old_shipment, dict):
        old_shipment = {}
    for key in _AS_SERVER_OWNED_SHIPMENT_KEYS:
        old_value = old_shipment.get(key)
        if isinstance(old_value, (dict, list)):
            new_shipment[key] = copy.deepcopy(old_value)
        else:
            new_shipment.pop(key, None)


def _force_preserve_as_lifecycle(old_sd: dict, structured_data: dict) -> None:
    """as_lifecycle 은 AS cycle API 소관 — 폼 stale 스냅샷으로 덮거나 빼지 않는다.

    접수 모달은 register 직후 erpSaveStructured() 를 호출한다. 폼 payload 는 페이지 로드
    시점 JSONB 라 as_lifecycle 이 없거나 이전 COMPLETED cycle 이다. allowlist 에 없는
    최상위 키는 incoming 에 없으면 그대로 탈락하므로, 가드가 없으면 방금 연 RECEIVED
    cycle 이 한 번의 폼 저장으로 사라진다.
    """
    if not isinstance(old_sd, dict) or not isinstance(structured_data, dict):
        return
    old_life = old_sd.get("as_lifecycle")
    if isinstance(old_life, dict):
        structured_data["as_lifecycle"] = copy.deepcopy(old_life)
    else:
        structured_data.pop("as_lifecycle", None)


def _preserve_operational_structured_state(old_sd: dict, structured_data: dict) -> None:
    """Preserve non-form operational state during ERP order full-form saves."""
    if not isinstance(old_sd, dict) or not isinstance(structured_data, dict):
        return

    for key in _OPERATIONAL_TOP_LEVEL_KEYS:
        if key not in structured_data and key in old_sd:
            structured_data[key] = copy.deepcopy(old_sd.get(key))

    # 'parties' 는 폼이 렌더하는 키(customer.name/phone·orderer.name·manager.name)만 보내고
    # 나머지는 payload 에 아예 없다. 통째 대입이면 수집이 채운 값이 첫 저장에서 사라진다 —
    # 2026-08-20 스테이징 실측: 네이버가 보존한 parties.orderer.phone(대리주문 주문자)과
    # parties.customer.phone2(보조 연락처, 수집 주석 왈 "버리면 다시 구할 방법이 없다")가
    # 주문을 한 번 열어 저장하는 것만으로 지워졌다. 키가 오면 덮고, 안 오면 남긴다.
    # AUDIT-GAP-01(2026-08-26): ``schedule`` 합류. PC 폼은 schedule 을
    # ``{measurement, construction}`` 만 조립해 보내는데(erp-order-shared.js) 이 목록에
    # 없어서, **AS 주문을 ERP 폼으로 한 번 저장할 때마다 ``schedule.as_visit`` 이 통째로
    # 사라졌다** — 고객과 약속한 AS 방문일·시간·가능시간대가 흔적 없이 증발했다.
    # 폼이 measurement/construction 의 date·time 키를 **항상** 보내므로(빈 문자열 포함)
    # 값 비우기는 그대로 동작하고, 폼이 렌더하지 않는 as_visit 만 보존된다.
    for key in ('workflow', 'assignments', 'shipment', 'meta', 'parties', 'schedule'):
        old_value = old_sd.get(key)
        incoming_value = structured_data.get(key)
        if isinstance(old_value, dict):
            if isinstance(incoming_value, dict):
                structured_data[key] = _merge_preserving_missing(old_value, incoming_value)
            elif key not in structured_data or incoming_value in (None, ''):
                structured_data[key] = copy.deepcopy(old_value)

    if 'quests' not in structured_data and old_sd.get('quests') is not None:
        structured_data['quests'] = copy.deepcopy(old_sd.get('quests'))

    _force_preserve_drawing_transfer_history(old_sd, structured_data)
    # 폼 저장의 암묵 전이 0(STATE-FORM-01): 단계는 서버값으로 고정하고, AS 전용 API 소관
    # 키(as_billing·as_log·as_lifecycle)는 폼 스냅샷이 되돌리지 못하게 서버값으로 되돌린다.
    _pin_form_stage_to_server(old_sd, structured_data)
    _force_preserve_as_server_state(old_sd, structured_data)
    _force_preserve_as_lifecycle(old_sd, structured_data)


#: 화면용 변경 목록이 쓸 수 있는 직렬화 예산(자). ``SECURITY_DETAIL_LIMIT``(4,000)에서
#: 맥락 키(mode·customer_name·order_type·change_set·카운터)와 JSON 구두점 몫을 빼고 잡았다.
#: 이 예산을 넘기면 detail 전체가 표식으로 대체돼 맥락까지 사라진다.
_DETAIL_CHANGES_BUDGET = 3200


def _new_change_set_id() -> str:
    """저장 1회 묶음 id 를 만든다 (ORDER-DIFF-01).

    같은 값이 감사 헤더(``security_logs.detail['change_set']``)와 항목 원장
    (``order_field_changes.change_set_id``) 양쪽에 들어가 **FK 없이** 둘을 잇는다.

    :return: UUID4 문자열.
    """
    return str(uuid.uuid4())


def _save_note(base: str, diff: DiffResult) -> str:
    """저장 로그 문장의 꼬리말을 만든다 (ORDER-DIFF-00).

    변경이 있으면 저장 종류 뒤에 요약을 붙인다 — ``전체 저장 · 실측일 8/12 → 8/14 외 3건``.
    변경이 없으면 기존 문장 그대로 둔다(없는 변경을 지어내지 않는다).

    :param base: 저장 종류(``전체 저장``·``인라인 수정``).
    :param diff: 변경 비교 결과.
    :return: ``describe_order_action(note=...)`` 에 넘길 문자열.
    """
    summary = summarize_changes(diff.changes, total=diff.total)
    return f"{base} · {summary}" if summary else base


def _diff_detail(diff: DiffResult, change_set_id: str, reason_required: bool = False) -> dict:
    """변경 비교 결과를 ``security_logs.detail`` 조각으로 만든다 (ORDER-DIFF-00·01).

    detail 은 **화면용**이라 두 겹으로 줄인다:

    1. 건수 상한(:data:`~foms.services.orders.structured_diff.MAX_CHANGES`)
    2. **바이트 예산** — ``normalize_security_detail`` 은 4,000자를 넘는 detail 을 통째로
       ``{'truncated': True, 'size': N}`` 표식으로 바꾼다. 그러면 변경 목록만이 아니라
       ``mode``·``customer_name`` 같은 맥락까지 사라진다. 건수만 세다가 그 한도를 넘긴 실사고가
       있었다(품목 46개 일괄 변경, 2026-08-11).

    품목 식별자(``uid``)는 화면이 쓰지 않으므로 여기서 뺀다 — 그 값은 질의용이라
    ``order_field_changes`` 원장에만 실린다(같은 값을 두 곳에 두면 예산만 먹는다).

    넘친 분량은 사라지지 않는다: 원장에 전량이 있고 여기서는 ``truncated`` 개수로 표시한다.

    :param diff: 변경 비교 결과(상한 없이 계산된 전량).
    :param change_set_id: 저장 1회 묶음 id — 항목 원장과 잇는 유일한 열쇠다.
    :param reason_required: 사유를 물어야 하는 저장인지(ORDER-REASON-00). 참일 때만 키를 넣고
        그 몫을 예산에서 **먼저** 뺀다 — 변경 목록이 예산을 다 쓴 뒤 이 키를 얹으면 detail
        전체가 표식으로 바뀐다.
    :return: ``{'change_set','change_count','truncated','changes'[,'reason_required']}``.
    """
    shown: list[dict] = []
    budget = _DETAIL_CHANGES_BUDGET
    if reason_required:
        budget -= len('"reason_required": true, ')
    for change in diff.changes[:MAX_CHANGES]:
        display = {key: value for key, value in change.items() if key != 'uid'}
        cost = len(json.dumps(display, ensure_ascii=False, default=str))
        if budget - cost < 0:
            break
        budget -= cost
        shown.append(display)

    detail = {
        'change_set': change_set_id,
        'change_count': diff.total,
        'truncated': max(0, diff.total - len(shown)),
        'changes': shown,
    }
    if reason_required:
        # 사유가 실제로 붙었는지는 order_change_reasons 가 답한다. 여기 표식은 "물어야 했던
        # 저장"을 감사 화면에서 바로 구분하기 위한 것이다(미입력 저장 추적).
        detail['reason_required'] = True
    return detail


def _record_structured_events(
    db: Session,
    order: Order,
    old_sd: dict,
    structured_data: dict,
) -> None:
    """긴급/실측일/실측시간/오너팀 변경 이벤트 기록.

    시공일(``CONSTRUCTION_DATE_CHANGED``)은 제외 — ``order_date_sync`` before_flush 훅이
    SSOT 다.
    """
    try:
        new_urgent = bool((structured_data.get('flags') or {}).get('urgent'))
        old_urgent = bool((old_sd.get('flags') or {}).get('urgent'))
        if new_urgent != old_urgent:
            db.add(OrderEvent(
                order_id=order.id,
                event_type='URGENT_CHANGED',
                payload={'from': old_urgent, 'to': new_urgent, 'reason': (structured_data.get('flags') or {}).get('urgent_reason')},
                created_by_user_id=session.get('user_id')
            ))
    except Exception as e:
        logger.warning("URGENT_CHANGED event record failed: %s", e, exc_info=True)
    try:
        new_meas = (structured_data.get('schedule') or {}).get('measurement') or {}
        old_meas = (old_sd.get('schedule') or {}).get('measurement') or {}
        # 알림톡 실측 안내는 날짜와 시간을 같이 싣는다 — 시간만 바뀌어도 타임라인에 남아야
        # 재발송 근거를 추적할 수 있다(같은 try: 새 broad catch 를 늘리지 않는다).
        for key, event_type in (
            ('date', 'MEASUREMENT_DATE_CHANGED'),
            ('time', 'MEASUREMENT_TIME_CHANGED'),
        ):
            if new_meas.get(key) != old_meas.get(key):
                db.add(OrderEvent(
                    order_id=order.id,
                    event_type=event_type,
                    payload={'from': old_meas.get(key), 'to': new_meas.get(key)},
                    created_by_user_id=session.get('user_id')
                ))
    except Exception as e:
        logger.warning("MEASUREMENT_DATE/TIME_CHANGED event record failed: %s", e, exc_info=True)
    # CONSTRUCTION_DATE_CHANGED 는 여기서 남기지 않는다 — 시공일 이벤트 SSOT 는
    # foms/services/order_date_sync.py 의 전역 before_flush 훅이다(모든 쓰기 경로가
    # 통과하는 유일 지점). 여기서도 add 하면 같은 변경이 2건으로 기록된다.
    try:
        new_team = (structured_data.get('assignments') or {}).get('owner_team')
        old_team = (old_sd.get('assignments') or {}).get('owner_team')
        if new_team != old_team:
            db.add(OrderEvent(
                order_id=order.id,
                event_type='OWNER_TEAM_CHANGED',
                payload={'from': old_team, 'to': new_team},
                created_by_user_id=session.get('user_id')
            ))
    except Exception as e:
        logger.warning("OWNER_TEAM_CHANGED event record failed: %s", e, exc_info=True)


def _apply_structured_side_effects(db: Session, order_id: int, structured_data: dict) -> None:
    """auto-task 적용."""
    try:
        apply_auto_tasks(db, order_id, structured_data)
    except Exception as e:
        logger.warning("[ERP_ORDER] auto-task apply: %s", e, exc_info=True)


def _actor_name(db: Session) -> Tuple[Optional[int], str]:
    """세션 사용자 id·표시명."""
    user_id = session.get('user_id')
    if not user_id:
        return None, session.get('username') or 'SYSTEM'
    user = db.query(User).filter(User.id == user_id).first()
    name = (user.name if user and getattr(user, 'name', None) else None) or session.get('username') or 'SYSTEM'
    return int(user_id), str(name)


def _emit_drawing_order_change_if_needed(
    db: Session,
    order: Order,
    old_sd: dict,
    new_sd: dict,
    *,
    old_notes: Any,
    new_notes: Any,
    old_is_regional: Any,
    new_is_regional: Any,
    old_construction_type: Any,
    new_construction_type: Any,
) -> Tuple[Any, bool]:
    """도면팀 ERP_ORDER_CHANGED 알림·history 반영. 실패해도 저장은 계속."""
    try:
        actor_id, actor_name = _actor_name(db)
        return apply_drawing_order_change_alert(
            db,
            order,
            old_sd,
            new_sd,
            actor_user_id=actor_id,
            actor_name=actor_name,
            old_notes=old_notes,
            new_notes=new_notes,
            old_is_regional=old_is_regional,
            new_is_regional=new_is_regional,
            old_construction_type=old_construction_type,
            new_construction_type=new_construction_type,
        )
    except Exception as e:
        logger.warning("[ERP_ORDER] drawing order-change alert failed: %s", e, exc_info=True)
        return None, False


def _emit_production_change_if_needed(
    db: Session,
    order: Order,
    old_sd: dict,
    new_sd: dict,
) -> Tuple[Any, bool]:
    """시공일 변경 시 생산팀 알림 반영(생산 파이프라인 게이트는 서비스가 판정).

    실패해도 저장은 계속한다(로그만).
    """
    try:
        old_c = (old_sd or {}).get("schedule") or {}
        new_c = (new_sd or {}).get("schedule") or {}
        old_date = ((old_c.get("construction") or {}) if isinstance(old_c, dict) else {}).get("date")
        new_date = ((new_c.get("construction") or {}) if isinstance(new_c, dict) else {}).get("date")
        if old_date == new_date:
            return None, False
        from foms.services.production_change_alerts import _date_to_md

        actor_id, actor_name = _actor_name(db)
        return apply_production_change_alert(
            db,
            order,
            "construction_date",
            f"{_date_to_md(old_date)} → {_date_to_md(new_date)}",
            actor_user_id=actor_id,
            actor_name=actor_name,
        )
    except Exception as e:
        logger.warning("[ERP_ORDER] production change alert failed: %s", e, exc_info=True)
        return None, False


def _event_actor_user_id() -> Optional[int]:
    """생성 이벤트의 actor(세션 사용자 id).

    요청 밖(백필 스크립트·워커)에서 호출돼도 예외를 던지지 않고 ``None`` 을 돌려준다 —
    감사 기록의 부재가 주문 저장을 죽여선 안 된다.

    Returns:
        세션 사용자 id(요청 밖이거나 미로그인이면 ``None``).
    """
    if not has_request_context():
        return None
    raw = session.get('user_id')
    return int(raw) if str(raw or '').strip().isdigit() else None


def _emit_draft_created_event(db: Session, order_id: int, created_via: str) -> None:
    """draft 행이 **새로 만들어진** 시점에 ``ORDER_DRAFT_CREATED`` 1건을 남긴다.

    자동저장(기존 draft 재저장)에서는 부르지 않는다 — draft 는 수십 번 갱신되므로
    "언제 누가 이 초안을 열었나"만이 감사 가치가 있다. 이벤트는 draft insert 와 같은
    트랜잭션에 동승하므로 생성이 롤백되면 이벤트도 함께 사라진다.

    Args:
        db: draft 를 생성 중인 활성 세션(별도 commit 하지 않는다).
        order_id: flush 로 확보한 draft 주문 id.
        created_via: ``meta.created_via``(``ADD_ORDER`` · ``ADD_ORDER_AUTOSAVE``).

    Returns:
        None.
    """
    db.add(OrderEvent(
        order_id=order_id,
        event_type=ORDER_DRAFT_CREATED_EVENT,
        payload={'via': ERP_DRAFT_EVENT_VIA, 'created_via': created_via},
        created_by_user_id=_event_actor_user_id(),
    ))


def _emit_order_created_event(order: Order) -> None:
    """draft → 실주문 승격이 확정된 지점에 ``ORDER_CREATED`` 1건을 남긴다.

    ERP 주력 생성 경로(draft POST → 자동저장 → 전체저장 승격)는 ``create_order()`` 를
    경유하지 않아 운영 대부분 주문에 "누가 만들었나" 기록이 0이었다. 승격이 곧 생성이므로
    정본과 같은 타입을 쓰되 payload ``via`` 로 경로를 구분한다. 같은 주문에 생성 이벤트가
    이미 있으면(레거시 ``create_order`` 경유 주문이 draft 플래그를 다시 통과하는 경우)
    추가하지 않는다 — 주문당 정확히 1건이 계약이다.

    Args:
        order: 승격이 확정된 주문(활성 세션에 attach 된 상태여야 한다).

    Returns:
        None.
    """
    db = object_session(order)
    if db is None or getattr(order, 'id', None) is None:
        logger.warning("ORDER_CREATED emit skipped: order not attached to a session")
        return
    with db.no_autoflush:
        already = (
            db.query(OrderEvent.id)
            .filter(
                OrderEvent.order_id == order.id,
                OrderEvent.event_type == ORDER_CREATED_EVENT,
            )
            .first()
        )
    if already is not None:
        return
    db.add(OrderEvent(
        order_id=order.id,
        event_type=ORDER_CREATED_EVENT,
        payload={'via': ERP_DRAFT_EVENT_VIA, 'status': order.status},
        created_by_user_id=_event_actor_user_id(),
    ))


def _is_placeholder_phone(phone: str) -> bool:
    """실제 연락처가 아닌 자리표시자 전화인가.

    ``000-0000-0000`` 한 값만 막던 시절의 구멍: 운영 주문 #4648 의 정본에
    ``000000000`` 이 들어가 있다(사람이 편집 중 남긴 값). 문자열 비교 한 줄로는 그 변형을
    못 걸러서, 정본을 따라가는 flat 동기가 **진짜 번호를 자리표시자로 덮는다.**

    판정은 숫자만 남긴 뒤에 한다 — 하이픈 유무·자릿수 변형이 전부 같은 값으로 접힌다.

    Args:
        phone: 정본에 들어 있는 전화 문자열.

    Returns:
        자리표시자(전부 0이거나 숫자가 모자람)면 True.

    >>> _is_placeholder_phone('000-0000-0000')
    True
    >>> _is_placeholder_phone('000000000')
    True
    >>> _is_placeholder_phone('010-3468-7933')
    False
    """
    digits = re.sub(r'[^0-9]', '', phone or '')
    if not digits:
        return True
    if set(digits) == {'0'}:
        return True
    # 시내번호(02-xxx-xxxx)까지 살리려면 9자리가 하한이다.
    return len(digits) < 9


def _sync_identity_flat_columns(order: Order, structured_data: dict) -> None:
    """고객 신원 flat 컬럼(``customer_name``·``phone``)을 structured_data 에 맞춘다.

    **왜 저장 경로마다 부르는가.** ``structured_data`` 가 정본이고 flat 컬럼은 SQL 이
    물을 수 있게 편 사본이다. 그런데 이 두 컬럼은 승격 시점에만 동기됐고, 승격 뒤 고객이
    전화를 바꾸면 :func:`sync_erp_flat_columns` 는 ``erp_phone_digits`` 만 새 값으로
    갱신하고 ``phone`` 컬럼은 옛 값 그대로 남았다. 표시 경로가
    :func:`~foms.services.erp_display.apply_erp_display_fields` 로 덮어 그려서 화면은 늘
    옳고 **SQL 만 틀린** 무증상 상태가 됐다(운영 활성 주문 130건이 신호 없이 쌓였다).

    그 어긋남이 실제로 낸 사고: 네이버 수집 자동 매칭이 ``erp_phone_digits`` 로 사람을
    찾는데 그 값만 새 번호로 바뀌어, 옛 번호로 결제된 수집분이 같은 고객의 주문을 못 찾았다
    (2026-09-01, ``docs/incidents/2026-09-01-naver-triage-auto-match-miss.md``).
    ``customer_name`` 도 같은 구멍이다 — 자동 매칭의 이름 축은 이 컬럼을 **정확일치**로
    본다.

    **주소·제품은 여기서 다루지 않는다.** 주소는 저장 경로가 이미
    :func:`~foms.services.order_geocode.reset_order_geocode_on_address_change` 로 동기하고,
    제품은 매칭 축이 아니다 — 축이 아닌 컬럼까지 끌어들이면 이 함수의 계약이 흐려진다.

    Args:
        order: 저장 중인 주문.
        structured_data: 저장되는 structured payload.

    Returns:
        None.
    """
    customer = ((structured_data.get('parties') or {}).get('customer') or {})
    cust_name = (customer.get('name') or '').strip()
    cust_phone = (customer.get('phone') or '').strip()
    # draft 가 심어둔 플레이스홀더는 실제 값을 덮지 않는다.
    if cust_name and cust_name not in _CUSTOMER_PLACEHOLDERS:
        order.customer_name = cust_name
    if cust_phone and not _is_placeholder_phone(cust_phone):
        order.phone = cust_phone


def _sync_promoted_flat_columns(order: Order, structured_data: dict) -> None:
    """승격 시 structured_data 의 실제 고객/제품 정보를 flat 컬럼에 반영한다.

    draft 가 심어둔 플레이스홀더(고객명·전화·주소·제품)는 덮어쓰지 않는다 — 실제 값이
    들어왔을 때만 승격한다.

    Args:
        order: 승격 중인 주문.
        structured_data: 승격에 쓰이는 structured payload.

    Returns:
        None.
    """
    site = (structured_data.get('site') or {})
    addr = (site.get('address_full') or site.get('address_main') or '').strip()
    items = structured_data.get('items') or []
    first_product = ''
    if items and isinstance(items, list) and len(items) > 0:
        first_product = (items[0].get('product_name') or '').strip()

    _sync_identity_flat_columns(order, structured_data)
    if addr and addr != '-':
        order.address = addr
    if first_product and first_product not in _PRODUCT_PLACEHOLDERS:
        order.product = first_product


def _finalize_draft_state(
    order: Order,
    structured_data: Optional[dict],
    now: datetime.datetime,
    old_structured_data: Optional[dict] = None,
) -> bool:
    """draft 메타 정리, 플레이스홀더 → 실제 데이터로 flat 컬럼 동기화, session 정리. draft_cleared 여부 반환.

    승격이 실제로 일어난 경우(``meta.draft`` truthy → falsy)에만 ``ORDER_CREATED`` 를
    남긴다. session 정리만으로 ``draft_cleared`` 가 True 가 되는 경로에서는 남기지 않는다.
    """
    draft_cleared = False
    promoted = False
    old_sd = old_structured_data if isinstance(old_structured_data, dict) else {}
    existing_draft = is_erp_order_draft(order) or is_erp_draft_structured_data(old_sd)
    if structured_data:
        try:
            meta = structured_data.get('meta') or {}
            if existing_draft or meta.get('draft') is True:
                meta['draft'] = False
                meta['finalized_at'] = now.isoformat()
                structured_data['meta'] = meta
                draft_cleared = True
                stage = (structured_data.get('workflow') or {}).get('stage') or (old_sd.get('workflow') or {}).get('stage')
                order.status = stage if stage in STATUS else 'RECEIVED'
                _sync_promoted_flat_columns(order, structured_data)
                promoted = True
        except Exception as e:
            logger.warning("draft meta clear failed: %s", e, exc_info=True)
    if promoted:
        _emit_order_created_event(order)
    try:
        existing_id = session.get('erp_draft_order_id')
        if existing_id and int(existing_id) == order.id:
            session.pop('erp_draft_order_id', None)
            draft_cleared = True
    except Exception as e:
        logger.warning("session erp_draft_order_id clear failed: %s", e, exc_info=True)
    return draft_cleared


@erp_orders_structured_bp.route('/orders/<int:order_id>/structured', methods=['GET'])
@login_required
def api_get_order_structured(order_id):
    """구조화 데이터 조회(전사 공용)."""
    db = get_db()
    try:
        order = db.query(Order).filter(Order.id == order_id, Order.not_deleted_filter()).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        _updated_at = getattr(order, 'structured_updated_at', None)
        return jsonify({
            'success': True,
            'order_id': order.id,
            'raw_order_text': order.raw_order_text,
            'structured_data': order.structured_data,
            'structured_schema_version': order.structured_schema_version,
            'structured_confidence': order.structured_confidence,
            'structured_updated_at': _updated_at.strftime('%Y-%m-%d %H:%M:%S') if _updated_at is not None else None,
            # DATA-01: If-Match(mutation_version) 낙관 잠금 토큰. 저장 시 이 값을 If-Match 로 보낸다.
            'mutation_version': getattr(order, 'mutation_version', None),
            'received_date': order.received_date or '',
            'received_time': order.received_time or '',
            'notes': order.notes or '',
            'is_self_measurement': getattr(order, 'is_self_measurement', False),
            'is_regional': getattr(order, 'is_regional', False),
            'construction_type': getattr(order, 'construction_type', None) or '',
            # ORDER-FLAG-01: 라홈시스템·지방주문 편집 가능 여부. 화면이 서버와 **같은 판정**을
            # 쓰게 내려준다 — 켤 수 있어 보이는데 저장이 무시되면 그게 더 나쁜 회귀다.
            'can_toggle_order_flags': can_toggle_order_flags(getattr(g, 'current_user', None)),
            # 지방주문 AS 재상차 모달 prefill용(flat 컬럼, structured_data에는 없음).
            'shipping_scheduled_date': getattr(order, 'shipping_scheduled_date', None) or '',
            # AS 재접수 모달의 'N번째 AS' 제목·지난 건 요약용 투영
            # (SSOT: services/orders/as_cycle_view). 부트스트랩 payload 와 같은 shape.
            'as_cycle': as_cycle_detail_payload(order.structured_data),
        })
    except Exception as e:
        logger.exception("[ERP_ORDER] structured GET 오류: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_structured_bp.route('/orders/<int:order_id>/detail-payload', methods=['GET'])
@login_required
def api_get_order_detail_payload(order_id: int):
    """작업 큐 상세 패널용 경량 payload (slim structured_data + role_assignees).

    대시보드 fragment에 50행분 detail_payload를 선적재하던 것을 제거하고, 상세 패널을
    처음 열 때만 이 엔드포인트로 lazy fetch한다(fragment 크기 대폭 감소). 반환 shape는
    기존 preload(build_order_detail_payload_map 단건)와 100% 동일해 클라이언트 렌더 로직은
    변경하지 않는다. 첨부는 기존과 동일하게 2단(/attachments)에서 별도 패치한다.
    """
    from foms.services.erp_order_detail import build_order_detail_payload_map

    db = get_db()
    try:
        order = (
            db.query(Order)
            .filter(Order.id == order_id, Order.not_deleted_filter())
            .first()
        )
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        payload = build_order_detail_payload_map(db, [order]).get(order_id)
        if payload is None:
            return jsonify({'success': False, 'message': '상세 데이터를 만들 수 없습니다.'}), 500
        return jsonify(payload)
    except Exception as e:
        logger.exception("[ERP_ORDER] detail-payload GET 오류: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500


def _field_affects_totals(field: str) -> bool:
    """이 인라인 필드가 **금액 파생값을 바꾸는가**.

    ``totals`` 는 ``items[].price`` 와 ``payment.*`` 에서만 나온다
    (:func:`~foms.services.orders.structured_form_projection.recompute_totals`).
    그 두 곳을 고쳤는데 재계산을 안 하면 저장된 ``totals`` 가 옛 값으로 남아, 저장
    ``totals`` 를 먼저 읽는 표면(모바일 요약 등)이 **품목금액을 넣었는데도 잔금 0원**을
    계속 보여준다. 2026-08-26 CEO 지적(M-1): 품목금액 인라인 저장 버튼을 화면에 다는
    순간 돈이 사라지는 트립와이어였다.

    Args:
        field: 인라인 패치 경로(예: ``items.0.price``, ``payment.deposit``).

    Returns:
        재계산이 필요하면 True.
    """
    if field.startswith("payment."):
        return True
    parts = field.split(".")
    return len(parts) >= 3 and parts[0] == "items" and parts[2] == "price"


@erp_orders_structured_bp.route('/orders/<int:order_id>/structured/fields', methods=['PATCH'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_patch_order_structured_fields(order_id: int):
    """Inline-edit partial patch with X-If-Match on structured_updated_at (P1-04)."""
    if not env_bool('FOMS_INLINE_EDIT_ENABLED'):
        return jsonify({'success': False, 'error': 'INLINE_DISABLED'}), 403

    db = get_db()
    try:
        order = db.query(Order).filter(Order.id == order_id, Order.not_deleted_filter()).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        payload = request.get_json(silent=True) or {}
        field = str(payload.get('field') or '').strip()
        value = payload.get('value')
        if not field:
            return jsonify({'success': False, 'error': 'MISSING_FIELD'}), 400

        if_match = request.headers.get('X-If-Match')
        current_updated = getattr(order, 'structured_updated_at', None)
        if if_match and current_updated is not None:
            expected = parse_updated_at(if_match)
            if expected is not None:
                stored = current_updated.replace(microsecond=0)
                if stored != expected.replace(microsecond=0):
                    return jsonify({
                        'success': False,
                        'error': 'CONFLICT',
                        'current': {
                            'structured_updated_at': format_updated_at(current_updated),
                        },
                    }), 409

        old_sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        old_notes = getattr(order, 'notes', None)
        old_is_regional = getattr(order, 'is_regional', None)
        old_construction_type = getattr(order, 'construction_type', None)
        structured_data = apply_field_patch(old_sd, field, value)
        # 금액 소스를 고쳤으면 파생값도 그 자리에서 다시 센다. 폼 전체저장(PUT)은
        # project_structured_form 안에서 이미 이걸 한다 — 인라인만 빠져 있었다.
        if _field_affects_totals(field):
            recompute_totals(structured_data)

        if field == 'site.address_full':
            flat_addr = str(value or '').strip()
            if flat_addr:
                setattr(order, 'address', flat_addr)
        if field == 'parties.customer.phone':
            setattr(order, 'phone', str(value or '').strip())
        if field == 'parties.customer.name':
            setattr(order, 'customer_name', str(value or '').strip())
        if field.endswith('.product_name'):
            prod = _first_product_name_from_structured_data(structured_data)
            if prod:
                setattr(order, 'product', prod)

        now = datetime.datetime.now()
        _record_structured_events(db, order, old_sd, structured_data)
        drawing_notif, drawing_notif_created = _emit_drawing_order_change_if_needed(
            db,
            order,
            old_sd,
            structured_data,
            old_notes=old_notes,
            new_notes=getattr(order, 'notes', None),
            old_is_regional=old_is_regional,
            new_is_regional=getattr(order, 'is_regional', None),
            old_construction_type=old_construction_type,
            new_construction_type=getattr(order, 'construction_type', None),
        )
        prod_notif, prod_notif_created = _emit_production_change_if_needed(
            db, order, old_sd, structured_data
        )
        order.structured_data = copy.deepcopy(structured_data)
        flag_modified(order, 'structured_data')
        sync_erp_flat_columns(order, structured_data)
        setattr(order, 'structured_updated_at', now)
        # 인라인 수정으로 주문담당자를 채운 경우도 같은 자동 배정을 태운다(PUT 과 동일 계약).
        auto_assign_sales_owner_from_manager(
            db, order_id=order.id, structured_data=structured_data,
            actor_user_id=session.get('user_id'),
        )
        patch_context = order_audit_context(order)
        # ORDER-DIFF-00: 경로만 남기던 인라인 로그에 이전값→새값을 채운다.
        # ORDER-DIFF-01: 원장에는 전량을 싣는다(상한은 화면용 detail 에만 건다).
        patch_diff = diff_structured(old_sd, structured_data, max_changes=-1)
        patch_change_set = _new_change_set_id()
        # ORDER-REASON-00: 판정은 서버가 사후에 한다(클라 사전 판정은 경로 목록이 2벌이 된다).
        # 인라인은 blur 자동저장이라 모달을 띄우지 않는다 — 화면은 응답을 보고 배너를 띄운다.
        patch_reason_required = is_reason_required(
            patch_diff.changes,
            stage=((structured_data.get('workflow') or {}).get('stage')
                   if isinstance(structured_data, dict) else None),
        )
        record_field_changes(
            db, patch_diff.changes,
            order_id=int(order_id),
            actor_user_id=session.get('user_id'),
            change_set_id=patch_change_set,
        )
        log_access(
            describe_order_action(order_id=order_id, action='ORDER_STRUCTURED_SAVED',
                                  note=_save_note('인라인 수정', patch_diff), **patch_context),
            session.get('user_id'),
            auto_commit=False,
            action='ORDER_STRUCTURED_SAVED', target_type='order', target_id=int(order_id),
            detail={
                'mode': 'inline',
                'field': field,
                **_diff_detail(patch_diff, patch_change_set, patch_reason_required),
                **patch_context,
            },
        )
        db.commit()

        # Tier A(broad): 주문 구조(structured_data) 수정은 workflow.stage/order.status를
        # 포함해 탭 간 이동이 실제로 일어나므로 전체 무효화를 유지한다.
        from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches
        invalidate_all_dashboard_slice_caches()
        finalize_drawing_order_change_alert(db, drawing_notif, created_new=drawing_notif_created)
        try:
            finalize_production_change_alert(db, prod_notif, created_new=prod_notif_created)
        except Exception as e:
            logger.warning("[ERP_ORDER] production change finalize failed: %s", e, exc_info=True)

        # 실측 예약 알림톡 자동 발송 — 커밋 성공 이후에만. 자격 판정·멱등은 서비스가
        # 담당하고 내부에서 모든 예외를 흡수한다(저장 트랜잭션 비차단 계약).
        maybe_send_measure_alimtalk(order_id)

        return jsonify({
            'success': True,
            'structured_updated_at': format_updated_at(now),
            'critical': is_critical_field(field),
            # ORDER-REASON-00: 사유는 저장을 막지 않는다 — 저장 성공 뒤에 붙인다.
            'change_reason_required': patch_reason_required,
            'change_set': patch_change_set,
        }), 200
    except ValueError as exc:
        db.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as e:
        db.rollback()
        logger.exception("[ERP_ORDER] structured PATCH 오류: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500


def _denied_flag_paths(order: Order, payload: Mapping[str, Any]) -> list[str]:
    """무권한 요청이 실제로 바꾸려 한 플래그 경로만 골라낸다 (ORDER-FLAG-01).

    폼은 저장할 때마다 세 값을 늘 함께 보낸다 — 값이 그대로인 요청까지 감사에 남기면
    무권한 사용자가 주문을 열어보기만 해도 ``ACCESS_DENIED`` 가 쌓인다.

    :param order: 대상 주문(현재 저장값 비교 기준).
    :param payload: 요청 JSON.
    :return: 실제로 달라진 경로 목록(``is_regional``·``construction_type``·``flags.factory2``).
    """
    denied: list[str] = []
    incoming_regional = payload.get('is_regional')
    if incoming_regional is not None and bool(incoming_regional) != bool(getattr(order, 'is_regional', False)):
        denied.append('is_regional')
    incoming_ct = payload.get('construction_type')
    if incoming_ct is not None:
        normalized_ct = normalize_regional_construction_type(incoming_ct) or None
        if normalized_ct != (getattr(order, 'construction_type', None) or None):
            denied.append('construction_type')
    structured = payload.get('structured_data')
    incoming_flags = structured.get('flags') if isinstance(structured, dict) else None
    if isinstance(incoming_flags, dict) and 'factory2' in incoming_flags:
        stored_sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        stored_flags = stored_sd.get('flags') if isinstance(stored_sd.get('flags'), dict) else {}
        if bool(incoming_flags.get('factory2')) != bool(stored_flags.get('factory2')):
            denied.append('flags.factory2')
    return denied


def _restore_locked_factory2(old_sd: Mapping[str, Any], structured_data: dict) -> None:
    """저장 직전에 ``flags.factory2`` 를 기존값으로 되돌린다 (ORDER-FLAG-01).

    ``flags`` 는 서버 보존 대상이 아니라 클라이언트가 통째로 덮는 자리다
    (``_preserve_operational_structured_state`` 의 deep-merge 목록에 없다). 그래서
    무권한 요청은 payload 를 고쳐 놓는 것 말고는 막을 자리가 없다. 키가 없었으면
    없는 채로 되돌린다 — 없던 키를 ``False`` 로 채우면 원장에 없는 변경이 생긴다.

    :param old_sd: 락 아래에서 읽은 저장값.
    :param structured_data: 이번 요청의 payload(제자리 수정).
    """
    stored_flags = old_sd.get('flags') if isinstance(old_sd.get('flags'), dict) else {}
    if 'factory2' in stored_flags:
        structured_data['flags']['factory2'] = stored_flags['factory2']
    else:
        structured_data['flags'].pop('factory2', None)


#: PUT 이 setattr 하는 평면 컬럼 → 원장 ``path`` (ORDER-FLAG-01 · AUDIT-GAP-01).
#:
#: 경로는 점 없는 컬럼명을 그대로 쓴다 — 점 경로로 적으면 되돌리기가 없는
#: ``structured_data`` 키를 만들어 두 벌 진실이 된다. ``notes`` 만 이름이 다른데,
#: ``sd['notes']`` 는 phone/address/measurement/construction 4칸짜리 **객체**라 같은 path 를
#: 쓰면 서로 다른 두 필드가 한 이력으로 합쳐지기 때문이다.
_FLAT_LEDGER_PATHS: dict[str, str] = {
    'is_regional': 'is_regional',
    'construction_type': 'construction_type',
    'is_self_measurement': 'is_self_measurement',
    'received_date': 'received_date',
    'received_time': 'received_time',
    'notes': 'order_notes',
}

#: 불리언으로 비교할 평면 컬럼. ``None`` 과 ``False`` 는 같은 뜻이라 op 는 항상 ``set`` 이다.
_FLAT_BOOL_COLUMNS: frozenset[str] = frozenset({'is_regional', 'is_self_measurement'})


def _flat_text_value(value: Any) -> Optional[str]:
    """평면 텍스트 컬럼의 원장 비교값.

    컬럼마다 빈값이 ``None`` 이기도 하고 ``''`` 이기도 하다(경로에 따라 다르게 쓰였다).
    둘을 같은 뜻으로 접어야 빈값→빈값 저장이 가짜 변경으로 기록되지 않는다.

    :param value: 컬럼에서 읽은 원시 값.
    :return: 문자열 또는 ``None``(빈값).
    """
    if value is None:
        return None
    text_value = value if isinstance(value, str) else str(value)
    return text_value or None


def _flat_flag_changes(order: Order, old_values: Mapping[str, Any]) -> list[dict[str, Any]]:
    """평면 컬럼 변경을 원장 change dict 로 옮긴다 (ORDER-FLAG-01 · AUDIT-GAP-01).

    자가실측·지방주문·시공구분·접수일·접수시간·주문비고는 ``structured_data`` 밖이라
    :func:`diff_structured` 가 못 본다. 값이 실제로 달라진 컬럼만 싣는다 — 저장 버튼만 눌러도
    행이 쌓이면 진짜 변경이 묻힌다.

    :param order: setattr 이 모두 끝난 주문(현재값 출처).
    :param old_values: setattr **전에** 떠 둔 저장값 스냅샷(컬럼명 → 값).
    :return: ``{'path','before','after','op'}`` 목록(변경 없으면 빈 목록).
    """
    changes: list[dict[str, Any]] = []
    for column, path in _FLAT_LEDGER_PATHS.items():
        old_raw = old_values.get(column)
        new_raw = getattr(order, column, None)
        if column in _FLAT_BOOL_COLUMNS:
            before: Any = bool(old_raw)
            after: Any = bool(new_raw)
            if before == after:
                continue
            op = 'set'
        else:
            before = _flat_text_value(old_raw)
            after = _flat_text_value(new_raw)
            if before == after:
                continue
            op = 'add' if before is None else ('clear' if after is None else 'set')
        changes.append({'path': path, 'before': before, 'after': after, 'op': op})
    return changes


@erp_orders_structured_bp.route('/orders/<int:order_id>/structured', methods=['PUT'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_put_order_structured(order_id):
    """구조화 데이터 저장(전사 공용).

    DATA-01: 저장은 REV-00 :func:`execute_order_mutation` 을 경유해 If-Match
    (mutation_version) 낙관 잠금 · ``FOR UPDATE`` 직렬화 · version bump · idempotency
    receipt 를 **한 transaction** 에 원자화한다(stale tab · PG race 방어). 폼 payload 는
    :func:`project_structured_form`(partial allowlist · provenance lock · server pricing)
    으로 정본화한다 — 클라이언트가 보낸 ``totals`` 및 provenance(raw/schema/confidence)는
    신뢰하지 않는다.

    optional 헤더: ``If-Match``(현재 mutation_version) · ``Idempotency-Key``(재요청 replay).
    """
    start_time = time.perf_counter()
    db = get_db()
    try:
        order = db.query(Order).filter(Order.id == order_id, Order.not_deleted_filter()).first()
        query_time = (time.perf_counter() - start_time) * 1000
        logger.info(f"save latency - query_order: {query_time:.1f}ms")

        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        payload = request.get_json(silent=True) or {}
        structured_data = payload.get('structured_data')
        raw_order_text = payload.get('raw_order_text')
        schema_version = payload.get('structured_schema_version', 1)
        confidence = payload.get('structured_confidence')
        received_date = payload.get('received_date')
        received_time = payload.get('received_time')
        notes = payload.get('notes')
        is_self_measurement = payload.get('is_self_measurement')
        is_regional = payload.get('is_regional')
        construction_type = payload.get('construction_type')
        # ORDER-FLAG-01: 라홈시스템(2공장)·지방주문은 CS(라홈팀/하우드팀)·관리자만 바꾼다.
        # 거부(403)가 아니라 **무시**다 — 이 PUT 은 저장 버튼 말고도 견적 미리보기·알림톡
        # 발송이 함께 태우므로, 403 으로 만들면 무권한 사용자의 정상 저장 전체가 막힌다.
        # 지방주문 구분(construction_type)은 체크박스와 한 몸이라 함께 잠근다 — 여기만
        # 열어두면 is_regional 을 떨어뜨린 뒤 아래 검증이 400 을 낸다.
        flags_editable = can_toggle_order_flags(getattr(g, 'current_user', None))
        if not flags_editable:
            denied_flag_paths = _denied_flag_paths(order, payload)
            is_regional = None
            construction_type = None
            if denied_flag_paths:
                record_access_denied(
                    f"권한 없는 주문 플래그 변경 시도(주문 {order_id}): {', '.join(denied_flag_paths)}",
                    user_id=session.get('user_id'),
                    ip=request.remote_addr,
                    endpoint=request.endpoint,
                    action='order-flag:ORDER_FLAG_FORBIDDEN',
                    structured_action='ACCESS_DENIED',
                    detail={
                        'endpoint': request.endpoint,
                        'reason': 'ORDER_FLAG_FORBIDDEN',
                        'order_id': int(order_id),
                        'paths': denied_flag_paths,
                    },
                )
        now = datetime.datetime.now()
        # 폼이 고른 단계. _pin_form_stage_to_server 가 곧 서버값으로 덮으므로 여기서 보관한다
        # (실측일 없는 지방주문/자가실측의 실측 단계 이동 판정에만 쓰인다).
        _wf_in = (structured_data or {}).get('workflow') if isinstance(structured_data, dict) else None
        requested_stage = str((_wf_in or {}).get('stage') or '').strip() if isinstance(_wf_in, dict) else ''
        had_measurement_date = bool(_structured_measurement_date(
            order.structured_data if isinstance(order.structured_data, dict) else {}
        ))

        if structured_data is not None and not isinstance(structured_data, dict):
            return jsonify({'success': False, 'message': 'structured_data는 JSON 객체여야 합니다.'}), 400

        # 요청 검증(락 전, 400 경로): 필수값 누락은 write 전에 거부한다.
        if structured_data is not None:
            _missing = _missing_required_structured_fields(structured_data)
            if _missing:
                logger.warning(f"[ERP_ORDER] 필수값 누락 저장 차단 order_id={order_id}: {_missing}")
                return jsonify({
                    'success': False,
                    'message': f"필수 항목을 입력해주세요: {', '.join(_missing)}"
                }), 400

        # 지방주문/시공구분 검증(락 전, 400 경로): 원본과 동일 semantics — 검증 실패 시 DB 무접근.
        # 적용 지시는 regional_set 으로 캡처해 락 안에서 setattr 한다.
        #   None            → 미변경
        #   (bool, ct|None) → is_regional·construction_type 동시 설정
        #   ('__ct_only__', ct|None) → construction_type 만 설정
        regional_set: Optional[tuple] = None
        if is_regional is not None:
            is_regional_flag = bool(is_regional)
            normalized_construction_type = normalize_regional_construction_type(construction_type)
            if str(construction_type or '').strip() and not normalized_construction_type:
                return jsonify({
                    'success': False,
                    'message': '지방주문 구분은 하우드 또는 협력사만 가능합니다.',
                }), 400
            if is_regional_flag and not normalized_construction_type:
                return jsonify({
                    'success': False,
                    'message': '지방주문 구분(하우드/협력사)을 선택해주세요.',
                }), 400
            regional_set = (is_regional_flag, normalized_construction_type if is_regional_flag else None)
        elif construction_type is not None:
            normalized_construction_type = normalize_regional_construction_type(construction_type)
            if str(construction_type or '').strip() and not normalized_construction_type:
                return jsonify({
                    'success': False,
                    'message': '지방주문 구분은 하우드 또는 협력사만 가능합니다.',
                }), 400
            if not getattr(order, 'is_regional', False) and normalized_construction_type:
                return jsonify({
                    'success': False,
                    'message': '비지방 주문에는 지방주문 구분을 저장할 수 없습니다.',
                }), 400
            if getattr(order, 'is_regional', False) and not normalized_construction_type:
                return jsonify({
                    'success': False,
                    'message': '지방주문 구분(하우드/협력사)을 선택해주세요.',
                }), 400
            regional_set = ('__ct_only__', normalized_construction_type or None)

        # optional If-Match(mutation_version) 낙관 잠금 — 형식 오류는 삼키지 않고 400.
        if_match_raw = (request.headers.get('If-Match') or '').strip().strip('"')
        expected_versions: Optional[Mapping[int, int]] = None
        if if_match_raw:
            try:
                expected_versions = {order_id: int(if_match_raw)}
            except ValueError:
                return jsonify({'success': False, 'message': 'If-Match 형식이 올바르지 않습니다.'}), 400
        idempotency_key = (request.headers.get('Idempotency-Key') or '').strip() or None

        actor_user_id = session.get('user_id')
        scope_hash = hashlib.sha256(f"{STRUCTURED_PUT_POLICY_ID}:{order_id}".encode()).hexdigest()
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
        ).hexdigest()

        # mutation 안에서 채워 커밋 후 사용할 값(캐시 무효화·알림 finalize·geocode enqueue).
        captured: dict = {
            'draft_cleared': False,
            'address_changed': False,
            # ORDER-DIFF-00: 감사용 변경 비교는 락 안에서만 만들 수 있다(저장 후엔 이전값이 없다).
            'diff': None,
            # ORDER-FLAG-01: structured 밖(평면 컬럼) 변경 — diff 와 같은 change_set 에 실린다.
            'flat_changes': [],
            'drawing_notif': None,
            'drawing_notif_created': False,
            'prod_notif': None,
            'prod_notif_created': False,
        }

        def _mutate(sess: Session, orders: List[Order]) -> Mapping[int, List[str]]:
            """FOR UPDATE 락 아래에서 폼 저장 전체(컬럼·structured projection·side-effect)."""
            o = orders[0]
            _sd_raw: Any = o.structured_data
            old_sd = _sd_raw if isinstance(_sd_raw, dict) else {}
            # ORDER-DIFF-00: 아래 보존/projection 단계가 old_sd 를 참조하며 값을 옮기므로,
            # 감사 비교 기준은 그 전에 떠 둔 사본이어야 한다(비교가 자기 자신과의 비교가 되면 안 된다).
            audit_old_sd = copy.deepcopy(old_sd)
            old_notes = getattr(o, 'notes', None)
            old_is_regional = getattr(o, 'is_regional', None)
            old_construction_type = getattr(o, 'construction_type', None)
            # AUDIT-GAP-01: 평면 컬럼 원장 비교의 기준값 — 아래 setattr 보다 **먼저** 떠야 한다.
            old_flat_values: dict[str, Any] = {
                'is_regional': old_is_regional,
                'construction_type': old_construction_type,
                'is_self_measurement': getattr(o, 'is_self_measurement', None),
                'received_date': getattr(o, 'received_date', None),
                'received_time': getattr(o, 'received_time', None),
                'notes': old_notes,
            }

            # provenance(raw_order_text): 폼의 빈 문자열이 원본 파싱 텍스트를 지우지 못하게 한다.
            # 실제 내용이 있고 기존이 비어 있을 때만 설정(client overwrite 금지 — DATA-01).
            if raw_order_text is not None and str(raw_order_text).strip():
                if not (getattr(o, 'raw_order_text', None) or '').strip():
                    setattr(o, 'raw_order_text', raw_order_text)
            if is_self_measurement is not None:
                setattr(o, 'is_self_measurement', bool(is_self_measurement))
            if regional_set is not None:
                _flag, _ct = regional_set
                if _flag == '__ct_only__':
                    setattr(o, 'construction_type', _ct)
                else:
                    setattr(o, 'is_regional', _flag)
                    setattr(o, 'construction_type', _ct)
            if received_date is not None and isinstance(received_date, str) and received_date.strip():
                setattr(o, 'received_date', received_date.strip())
            if received_time is not None and isinstance(received_time, str):
                setattr(o, 'received_time', received_time.strip() or None)
            if notes is not None:
                setattr(o, 'notes', (notes if isinstance(notes, str) else str(notes or '')) or None)

            if structured_data is not None:
                if not structured_data.get('workflow'):
                    structured_data['workflow'] = {}
                if not structured_data.get('flags'):
                    structured_data['flags'] = {}
                if not flags_editable:
                    _restore_locked_factory2(old_sd, structured_data)
                if not structured_data.get('assignments'):
                    structured_data['assignments'] = {}
                _preserve_operational_structured_state(old_sd, structured_data)
                _preserve_or_normalize_construction_workers(old_sd, structured_data)
                # DATA-01 정본 projection: partial allowlist · provenance lock · server pricing.
                project_structured_form(old_sd, structured_data)

                # STATE-FORM-01: 폼 저장은 단계를 바꾸지 않는다. workflow.stage 는
                # _pin_form_stage_to_server 가 이미 서버값으로 고정했고, 단계 전이는
                # 명시적 stage-override(STATE-CORE transition) 경로 전용이다.
                # 실측일 지정 자동 전진·실측일 삭제 자동 복귀도 여기서 쓰지 않고,
                # 커밋 뒤 canonical 엔진이 맡는다.

                t0 = time.perf_counter()
                _record_structured_events(sess, o, old_sd, structured_data)
                _apply_structured_side_effects(sess, o.id, structured_data)
                side_effect_time = (time.perf_counter() - t0) * 1000
                logger.info(f"save latency - side_effects: {side_effect_time:.1f}ms")

                captured['draft_cleared'] = _finalize_draft_state(o, structured_data, now, old_sd)

                drawing_notif, drawing_notif_created = _emit_drawing_order_change_if_needed(
                    sess,
                    o,
                    old_sd,
                    structured_data,
                    old_notes=old_notes,
                    new_notes=getattr(o, 'notes', None),
                    old_is_regional=old_is_regional,
                    new_is_regional=getattr(o, 'is_regional', None),
                    old_construction_type=old_construction_type,
                    new_construction_type=getattr(o, 'construction_type', None),
                )
                prod_notif, prod_notif_created = _emit_production_change_if_needed(
                    sess, o, old_sd, structured_data
                )
                captured['drawing_notif'] = drawing_notif
                captured['drawing_notif_created'] = drawing_notif_created
                captured['prod_notif'] = prod_notif
                captured['prod_notif_created'] = prod_notif_created

                # ORDER-DIFF-00: 보존·projection 까지 끝난 최종본과 비교해야 실제로 저장된
                # 변경만 남는다(중간 상태로 비교하면 서버가 되돌린 값까지 변경으로 찍힌다).
                # ORDER-ITEM-UID: 품목 식별자를 **비교 직전에** 보장한다. 클라이언트가 uid 를
                # 빠뜨렸어도 위치로 물려받으므로 저장 한 번이 "전 품목 재생성"으로 기록되지 않는다.
                ensure_item_uids(audit_old_sd, structured_data)

                # ORDER-DIFF-01: 상한 없이 계산한다 — 원장에는 전량, 화면 detail 에만 상한.
                captured['diff'] = diff_structured(audit_old_sd, structured_data, max_changes=-1)

                o.structured_data = copy.deepcopy(structured_data)
                flag_modified(o, 'structured_data')
                sync_erp_flat_columns(o, structured_data)
                # 신원 컬럼(customer_name·phone)은 sync_erp_flat_columns 의 계약 밖이라
                # 여기서 따로 맞춘다. 안 맞추면 이 경로의 저장만 flat 을 옛 값으로 남긴다.
                _sync_identity_flat_columns(o, structured_data)

                # 수집 주문 담당자 자동 배정: 보류함이 owner 인 채로 주문담당자만 적히면
                # 취소 알림이 담당자에게 안 간다(claim_watch 는 SALES owner 로 보낸다).
                # 이미 락 안이라 REV-00 mutation 을 새로 열지 않는 in-tx 경로를 쓴다.
                auto_assign_sales_owner_from_manager(
                    sess, order_id=o.id, structured_data=structured_data,
                    actor_user_id=actor_user_id,
                )

            # provenance(schema/confidence 컬럼): 기존 값이 있으면 클라이언트 값으로 덮지 않는다.
            if getattr(o, 'structured_schema_version', None) is None:
                setattr(o, 'structured_schema_version', int(schema_version) if schema_version else 1)
            if not getattr(o, 'structured_confidence', None):
                setattr(
                    o,
                    'structured_confidence',
                    confidence or (structured_data.get('confidence') if isinstance(structured_data, dict) else None),
                )
            setattr(o, 'structured_updated_at', now)

            # ERP structured 저장은 자동 ChannelTalk 푸시하지 않는다(수동 푸쉬만).
            if structured_data is not None:
                old_addr = (extract_address_from_structured_data(old_sd) or '').strip()
                new_addr = (extract_address_from_structured_data(structured_data) or '').strip()
                if old_addr != new_addr:
                    captured['address_changed'] = True
                    reset_order_geocode_on_address_change(o, new_addr)

            # ORDER-FLAG-01 · AUDIT-GAP-01: 평면 컬럼 변경도 같은 change_set 에 싣는다 —
            # structured 밖이라 diff_structured 가 못 본다. structured_data 가 없는 요청에서도
            # 남긴다(접수일·접수시간·주문비고만 고치는 저장이 실제로 있다).
            captured['flat_changes'] = _flat_flag_changes(o, old_flat_values)

            return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

        try:
            outcome = execute_order_mutation(
                db,
                actor_user_id=actor_user_id,
                policy_id=STRUCTURED_PUT_POLICY_ID,
                order_ids=[order_id],
                expected_versions=expected_versions,
                idempotency_key=idempotency_key,
                scope_hash=scope_hash,
                request_hash=request_hash,
                mutation=_mutate,
            )
            put_context = order_audit_context(order)
            put_diff = captured['diff'] or DiffResult([], 0, 0)
            # ORDER-FLAG-01: 지방주문·시공구분은 평면 컬럼이라 structured diff 밖에 있다.
            # 같은 change_set 에 합쳐 원장·감사 detail·저장 요약이 한 벌로 보이게 한다.
            put_flat_changes = captured.get('flat_changes') or []
            if put_flat_changes:
                put_diff = DiffResult(
                    list(put_diff.changes) + list(put_flat_changes),
                    put_diff.total + len(put_flat_changes),
                    put_diff.truncated,
                )
            put_change_set = _new_change_set_id()
            # ORDER-REASON-00: 금액·일정·단계가 바뀐 저장이면 화면이 저장 성공 뒤에 사유를
            # 묻는다. 판정은 여기(서버)에만 있고, 응답으로 내려보낸다.
            put_reason_required = is_reason_required(
                put_diff.changes,
                stage=((structured_data.get('workflow') or {}).get('stage')
                       if isinstance(structured_data, dict) else None),
            )
            # 원장 행은 저장과 같은 트랜잭션에 실린다(아래 db.commit() 이 함께 커밋한다).
            record_field_changes(
                db, put_diff.changes,
                order_id=int(order_id),
                actor_user_id=actor_user_id,
                change_set_id=put_change_set,
            )
            log_access(
                describe_order_action(order_id=order_id, action='ORDER_STRUCTURED_SAVED',
                                      note=_save_note('전체 저장', put_diff), **put_context),
                actor_user_id,
                auto_commit=False,
                action='ORDER_STRUCTURED_SAVED', target_type='order', target_id=int(order_id),
                detail={
                    'mode': 'full',
                    **_diff_detail(put_diff, put_change_set, put_reason_required),
                    **put_context,
                },
            )
            db.commit()
        except RevisionConflictError as conflict:
            # 동시편집 충돌은 정상 운영 흐름이므로 exception 이 아니라 info 로 남긴다.
            # 클라이언트는 409 + current.mutation_version 으로 덮어쓰기 여부를 사용자에게 묻는다.
            db.rollback()
            logger.info(
                "[ERP_ORDER] structured PUT version conflict: order=%s expected=%s current=%s",
                order_id, expected_versions, conflict.current_versions,
            )
            return jsonify({
                'success': False,
                'error': 'VERSION_CONFLICT',
                # STATE-FORM 기존 계약(code) 유지 — error/current 는 추가 필드다.
                'code': conflict.error_code,
                'message': '다른 사용자가 이 주문을 먼저 수정했습니다.',
                'current': {'mutation_version': conflict.current_versions.get(order_id)},
            }), 409
        except PreconditionRequiredError as precondition:
            db.rollback()
            logger.warning("[ERP_ORDER] structured PUT If-Match 누락: %s", precondition)
            return jsonify({
                'success': False,
                'error': 'IF_MATCH_REQUIRED',
                'code': precondition.error_code,
                'message': '최신 주문 상태를 다시 불러온 뒤 저장해주세요.',
            }), 428
        except RevisionError as rev:
            db.rollback()
            return jsonify(
                {'success': False, 'message': str(rev), 'code': rev.error_code}
            ), rev.status_code

        # 실측일 지정 → MEASURE 전진, 실측일 삭제 → RECEIVED 복귀.
        # 폼 트랜잭션 밖에서 별도 전이로 수행해야 STAGE_CHANGED·outbox·receipt 가 다른
        # 전이와 같은 경로로 남는다. 전이 실패는 폼 저장을 되돌리지 않는다(저장은 이미 성공).
        auto_stage_error = None
        auto_target = None
        if _should_auto_advance_to_measure(order, requested_stage):
            auto_target = 'MEASURE'
            auto_body = {'auto': 'MEASUREMENT_DATE_SET', 'order_id': order_id}
        elif _should_auto_regress_to_received(order, had_measurement_date):
            auto_target = 'RECEIVED'
            auto_body = {'auto': 'MEASUREMENT_DATE_CLEARED', 'order_id': order_id}
        if auto_target is not None:
            from foms.api.orders.status import apply_canonical_main_stage

            auto_stage_error = apply_canonical_main_stage(
                db,
                order,
                auto_target,
                actor_user_id=actor_user_id,
                body=auto_body,
                idempotency_key=None,
            )
            if auto_stage_error is None:
                db.commit()
            else:
                logger.warning(
                    "[ERP_ORDER] 실측일 자동 단계 이동 실패: order=%s to=%s status=%s",
                    order_id, auto_target, auto_stage_error[1],
                )

        # Tier A(broad): 주문 저장(PUT structured)은 stage/status 변경을 포함 → 탭 이동.
        from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches

        invalidate_all_dashboard_slice_caches()
        finalize_drawing_order_change_alert(
            db, captured['drawing_notif'], created_new=captured['drawing_notif_created']
        )
        try:
            finalize_production_change_alert(
                db, captured['prod_notif'], created_new=captured['prod_notif_created']
            )
        except Exception as e:
            logger.warning("[ERP_ORDER] production change finalize failed: %s", e, exc_info=True)
        commit_time = (time.perf_counter() - start_time) * 1000
        logger.info(f"save latency - main_commit: {commit_time:.1f}ms")

        if captured['address_changed']:
            enqueue_geocode_order_address(order_id)

        # 실측 예약 알림톡 자동 발송 — 커밋 성공 이후에만. 자격 판정·멱등은 서비스가
        # 담당하고 내부에서 모든 예외를 흡수한다(저장 트랜잭션 비차단 계약).
        maybe_send_measure_alimtalk(order_id)

        total_time = (time.perf_counter() - start_time) * 1000
        logger.info(f"save latency - TOTAL: {total_time:.1f}ms")
        _resources = outcome.body.get('resources') or [{}]
        # 자동 단계전진이 붙었으면 version 이 한 번 더 올라간다 — 폼 저장 시점 값을 돌려주면
        # 다음 저장이 무조건 409(stale If-Match)가 된다. 실제 최종 version 을 돌려준다.
        final_version = _resources[0].get('resulting_version')
        if auto_stage_error is None and getattr(order, 'mutation_version', None) is not None:
            final_version = order.mutation_version
        resp = jsonify({
            'success': True,
            'draft_cleared': captured['draft_cleared'],
            'mutation_receipt': outcome.read_receipt_id,
            'mutation_version': final_version,
            # ORDER-REASON-00: 저장은 이미 성공했다. 화면은 이 두 값으로 사유를 붙인다.
            'change_reason_required': put_reason_required,
            'change_set': put_change_set,
        })
        for header, value in outcome.headers.items():
            resp.headers[header] = value
        return resp
    except Exception as e:
        db.rollback()
        logger.exception("[ERP_ORDER] structured PUT 오류: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_structured_bp.route('/orders/parse-text', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_parse_order_text():
    """텍스트 붙여넣기 → 구조화 파싱(미리보기용). 저장은 하지 않음."""
    start_time = time.perf_counter()
    try:
        payload = request.get_json(silent=True) or {}
        raw_text = (payload.get('raw_text') or '').strip()
        if not raw_text:
            return jsonify({'success': False, 'message': 'raw_text가 필요합니다.'}), 400

        structured = parse_order_text(raw_text)
        
        total_time = (time.perf_counter() - start_time) * 1000
        logger.info(f"parse-text latency - TOTAL: {total_time:.1f}ms")
        return jsonify({'success': True, 'structured_data': structured})
    except Exception as e:
        logger.exception("[ERP_ORDER] parse-text 오류: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_structured_bp.route('/orders/<int:order_id>/payment-confirm', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_payment_confirm(order_id):
    """예약금/잔금 확인 토글 API."""
    db = get_db()
    try:
        order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        payload = request.get_json(silent=True) or {}
        payment_type = payload.get('type')
        confirmed = payload.get('confirmed', False)

        if payment_type not in ['deposit', 'balance']:
            return jsonify({'success': False, 'message': '잘못된 결제 타입입니다.'}), 400

        structured_data = copy.deepcopy(order.structured_data) if isinstance(order.structured_data, dict) else {}
        if 'payment' not in structured_data or not isinstance(structured_data['payment'], dict):
            structured_data['payment'] = {}
        
        payment_obj = structured_data['payment']
        now_str = datetime.datetime.now().isoformat()
        
        user_id = session.get('user_id')
        user = db.query(User).filter(User.id == user_id).first() if user_id else None
        user_name = user.name if user and hasattr(user, 'name') else (session.get('username') or 'SYSTEM')

        if payment_type == 'deposit':
            payment_obj['deposit_confirmed'] = confirmed
            payment_obj['deposit_confirmed_at'] = now_str if confirmed else None
            payment_obj['deposit_confirmed_by'] = user_name if confirmed else None
            payment_obj['deposit_confirmed_by_user_id'] = user_id if confirmed else None
        else:
            payment_obj['balance_confirmed'] = confirmed
            payment_obj['balance_confirmed_at'] = now_str if confirmed else None
            payment_obj['balance_confirmed_by'] = user_name if confirmed else None
            payment_obj['balance_confirmed_by_user_id'] = user_id if confirmed else None

        order.structured_data = structured_data
        flag_modified(order, 'structured_data')

        audit_context = order_audit_context(order)
        audit_action = 'PAYMENT_CONFIRMED' if confirmed else 'PAYMENT_CONFIRM_CLEARED'
        log_access(
            describe_order_action(
                order_id=order_id, action=audit_action,
                note=_PAYMENT_TYPE_LABELS.get(payment_type, payment_type), **audit_context,
            ),
            user_id,
            auto_commit=False,
            action=audit_action, target_type='order', target_id=int(order_id),
            detail={'payment_type': payment_type, 'confirmed': bool(confirmed), **audit_context},
        )

        db.commit()
        # Tier A(broad): 결제/구조 필드 patch도 structured_data 전반을 갱신 → 탭 이동 가능.
        from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches

        invalidate_all_dashboard_slice_caches()

        ret_payment = {
            'deposit': payment_obj.get('deposit', 0),
            'discount': payment_obj.get('discount', 0),
            'cash_receipt': payment_obj.get('cash_receipt') or '',
            'deposit_confirmed': payment_obj.get('deposit_confirmed', False),
            'deposit_confirmed_at': payment_obj.get('deposit_confirmed_at'),
            'deposit_confirmed_by': payment_obj.get('deposit_confirmed_by'),
            'deposit_confirmed_by_user_id': payment_obj.get('deposit_confirmed_by_user_id'),
            'balance_confirmed': payment_obj.get('balance_confirmed', False),
            'balance_confirmed_at': payment_obj.get('balance_confirmed_at'),
            'balance_confirmed_by': payment_obj.get('balance_confirmed_by'),
            'balance_confirmed_by_user_id': payment_obj.get('balance_confirmed_by_user_id'),
        }

        return jsonify({'success': True, 'payment': ret_payment})
    except Exception as e:
        db.rollback()
        logger.exception("[ERP_ORDER] payment-confirm 오류: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_structured_bp.route('/orders/erp/draft', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_erp_create_draft():
    """ERP '새 주문' 화면용 draft 주문 생성. order_id를 먼저 확보."""
    db = get_db()
    try:
        payload = request.get_json(silent=True) or {}
        draft_token = _coerce_draft_token(
            payload.get('draft_token') or request.headers.get('X-ERP-Draft-Token')
        )
        _lock_draft_token_if_supported(db, draft_token)

        existing_id = session.get('erp_draft_order_id')
        if existing_id:
            order = db.query(Order).filter(Order.id == int(existing_id), Order.not_deleted_filter()).first()
            if order and is_erp_order_draft(order):
                return jsonify({'success': True, 'order_id': order.id, 'reused': True})
            session.pop('erp_draft_order_id', None)

        token_order = _find_existing_draft_by_token(db, draft_token)
        if token_order:
            session['erp_draft_order_id'] = token_order.id
            return jsonify({'success': True, 'order_id': token_order.id, 'reused': True})

        now = now_kst()
        today = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M')
        structured = {
            'workflow': {'stage': 'RECEIVED', 'stage_updated_at': now.isoformat()},
            'flags': {'urgent': False},
            'assignments': {},
            'schedule': {},
            'meta': {'draft': True, 'created_via': 'ADD_ORDER'},
        }
        if draft_token:
            structured['meta']['draft_token'] = draft_token

        order = Order(
            received_date=today,
            received_time=time_str,
            customer_name=ERP_DRAFT_PLACEHOLDER_CUSTOMER,
            phone=ERP_DRAFT_PLACEHOLDER_PHONE,
            address='-',
            product=ERP_DRAFT_PLACEHOLDER_PRODUCT,
            options=None,
            notes=None,
            status='DRAFT',
            is_erp_order=True,
            raw_order_text='',
            structured_data=structured,
            structured_schema_version=1,
            structured_confidence=None,
            structured_updated_at=now,
        )
        db.add(order)
        db.flush()
        sync_erp_flat_columns(order, structured)
        # draft 생성 감사(ORDER_DRAFT_CREATED): 같은 트랜잭션 동승 — 생성이 롤백되면 함께 사라진다.
        _emit_draft_created_event(db, order.id, structured['meta']['created_via'])
        db.commit()
        # Tier A(broad): 신규 초안 생성은 새 주문이 목록/단계 집계에 진입 → 전체 무효화.
        from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches

        invalidate_all_dashboard_slice_caches()
        db.refresh(order)

        session['erp_draft_order_id'] = order.id
        return jsonify({'success': True, 'order_id': order.id, 'reused': False})
    except Exception as e:
        try:
            db.rollback()
        except Exception as rb_err:
            logger.warning("draft create: rollback failed: %s", rb_err, exc_info=True)
        logger.warning("[ERP_ORDER] draft create error: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


def _lock_draft_row(db: Session, order_id: int) -> Optional[Order]:
    """``FOR UPDATE`` 로 잠근 최신 행을 돌려준다(자동저장이 승격을 되돌리지 못하게).

    명시 저장(PUT structured)은 REV-00 mutation core 가 같은 행을 ``FOR UPDATE`` 로
    잡고 draft 를 승격한다. 자동저장이 잠금 없이 미리 읽은 draft 스냅샷을 그대로 쓰면,
    승격 커밋 직후에 ``meta.draft=True`` 를 되살려 주문이 대시보드에서 사라진다
    (production 실사고). 같은 잠금을 태워 승격 완료를 관측한 뒤 재판정한다.

    Args:
        db: 활성 세션.
        order_id: 대상 주문 id.

    Returns:
        잠긴 최신 Order(없으면 None). identity map 의 stale 값은 populate_existing 로 갱신.
    """
    return (
        db.query(Order)
        .filter(Order.id == order_id, Order.not_deleted_filter())
        .populate_existing()
        .with_for_update()
        .first()
    )


def _resolve_draft_for_autosave(db: Session, draft_token: str = '') -> tuple[Optional[Order], bool]:
    """자동저장용 draft 해석. ``(draft, promoted)`` 를 돌려준다.

    ``promoted=True`` 는 "이 세션의 draft 가 방금 명시 저장으로 승격됐다"는 뜻이다.
    이 경우 자동저장은 아무것도 쓰지 않는다 — 되살리면 주문이 사라지고(draft 부활),
    새 draft 를 만들면 보이지 않는 중복 행이 쌓인다.

    Args:
        db: 활성 세션.
        draft_token: 브라우저 페이지 토큰(선택).

    Returns:
        (열려 있는 draft Order 또는 None, 승격 감지 여부).
    """
    existing_id = session.get('erp_draft_order_id')
    if existing_id:
        order = _lock_draft_row(db, int(existing_id))
        if order and is_erp_order_draft(order):
            return order, False
        session.pop('erp_draft_order_id', None)
        if order is not None:
            return None, True
    return _resolve_session_draft(db, draft_token), False


def _resolve_session_draft(db: Session, draft_token: str = '') -> Optional[Order]:
    """Return the current session/token ERP draft Order, or None. Never creates.

    Args:
        db: Active SQLAlchemy session.
        draft_token: Browser-page idempotency token (optional).

    Returns:
        The open draft Order owned by this session/token, or None.
    """
    existing_id = session.get('erp_draft_order_id')
    if existing_id:
        order = _lock_draft_row(db, int(existing_id))
        if order and is_erp_order_draft(order):
            return order
        session.pop('erp_draft_order_id', None)
    token_order = _find_existing_draft_by_token(db, draft_token)
    if token_order:
        locked = _lock_draft_row(db, token_order.id)
        if locked and is_erp_order_draft(locked):
            session['erp_draft_order_id'] = locked.id
            return locked
        return None
    return None


def _create_session_draft(db: Session, draft_token: str = '') -> Order:
    """Create a new ERP draft Order and bind it to the session.

    Mirrors :func:`api_erp_create_draft` so autosave can establish a draft
    without a separate round-trip. Keeps ``status='DRAFT'`` / ``meta.draft=True``.

    Args:
        db: Active SQLAlchemy session.
        draft_token: Browser-page idempotency token (optional).

    Returns:
        The newly created draft Order (already flushed/committed).
    """
    now = now_kst()
    structured = {
        'workflow': {'stage': 'RECEIVED', 'stage_updated_at': now.isoformat()},
        'flags': {'urgent': False},
        'assignments': {},
        'schedule': {},
        'meta': {'draft': True, 'created_via': 'ADD_ORDER_AUTOSAVE'},
    }
    if draft_token:
        structured['meta']['draft_token'] = draft_token
    order = Order(
        received_date=now.strftime('%Y-%m-%d'),
        received_time=now.strftime('%H:%M'),
        customer_name=ERP_DRAFT_PLACEHOLDER_CUSTOMER,
        phone=ERP_DRAFT_PLACEHOLDER_PHONE,
        address='-',
        product=ERP_DRAFT_PLACEHOLDER_PRODUCT,
        options=None,
        notes=None,
        status='DRAFT',
        is_erp_order=True,
        raw_order_text='',
        structured_data=structured,
        structured_schema_version=1,
        structured_confidence=None,
        structured_updated_at=now,
    )
    db.add(order)
    db.flush()
    sync_erp_flat_columns(order, structured)
    # 자동저장이 만든 draft 도 '생성'이다 — POST /orders/erp/draft 와 같은 1건을 남긴다.
    _emit_draft_created_event(db, order.id, structured['meta']['created_via'])
    db.commit()
    db.refresh(order)
    session['erp_draft_order_id'] = order.id
    return order


def _structured_has_meaningful_content(
    structured_data: Any, received_notes: str = ''
) -> bool:
    """Decide whether a draft has real content worth persisting server-side.

    Guards against spawning DRAFT Order rows for forms abandoned after a single
    keystroke. localStorage still mirrors those locally; only meaningful drafts
    reach the DB (and cross-device restore).

    Args:
        structured_data: Partial structured payload from the form.
        received_notes: Free-text notes field value.

    Returns:
        True when a customer/site/product/payment/estimate/notes signal is present.
    """
    if (received_notes or '').strip():
        return True
    if not isinstance(structured_data, dict):
        return False
    if _structured_has_payment_content(structured_data):
        return True
    if _structured_has_estimate_preview_content(structured_data):
        return True
    customer = (((structured_data.get('parties') or {}).get('customer')) or {})
    name = (customer.get('name') or '').strip()
    phone = (customer.get('phone') or '').strip()
    if name and name not in _CUSTOMER_PLACEHOLDERS:
        return True
    if phone and phone != ERP_DRAFT_PLACEHOLDER_PHONE:
        return True
    site = structured_data.get('site') or {}
    addr = (site.get('address_full') or site.get('address_main') or '').strip()
    if addr and addr != '-':
        return True
    for item in (structured_data.get('items') or []):
        if not isinstance(item, dict):
            continue
        # 사용자가 실제로 채우는 필드만 신호로 본다. color/handle/misc/option_detail/
        # internal은 기본값 '상담'이라, 포함하면 빈 폼도 '내용 있음'으로 오판 → 빈 draft가
        # 기존 draft를 덮어써 데이터 유실. product_name/spec/price만 본다.
        for key in ('product_name', 'spec', 'price'):
            if str(item.get(key) or '').strip():
                return True
    return False


def _autosave_coerce_amount(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, dict):
        return _autosave_coerce_amount(
            value.get('amount') or value.get('raw') or value.get('value') or 0
        )
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else 0
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return int(digits) if digits else 0


def _autosave_text_value(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, dict):
        return _autosave_text_value(
            value.get('value') or value.get('raw') or value.get('text') or ''
        )
    return str(value or '').strip()


def _structured_has_payment_content(structured_data: dict) -> bool:
    payment = structured_data.get('payment') if isinstance(structured_data.get('payment'), dict) else {}
    legacy = structured_data.get('payments') if isinstance(structured_data.get('payments'), dict) else {}
    totals = structured_data.get('totals') if isinstance(structured_data.get('totals'), dict) else {}

    if _autosave_coerce_amount(
        payment.get('deposit') or legacy.get('deposit') or totals.get('deposit_amount')
    ) > 0:
        return True
    if _autosave_coerce_amount(payment.get('discount') or totals.get('discount_amount')) > 0:
        return True
    if _autosave_text_value(payment.get('free_input') or legacy.get('free_input')):
        return True
    if _autosave_text_value(payment.get('cash_receipt') or legacy.get('cash_receipt')):
        return True
    if _autosave_text_value(payment.get('balance_note')):
        return True
    return False


def _structured_has_estimate_preview_content(structured_data: dict) -> bool:
    preview = structured_data.get('estimate_preview')
    if not isinstance(preview, dict):
        return False
    rows = preview.get('manual_rows') or []
    if not isinstance(rows, list):
        return False
    meaningful_keys = ('product_name', 'spec', 'color', 'quantity', 'amount')
    for row in rows:
        if not isinstance(row, dict):
            continue
        if any(str(row.get(key) or '').strip() for key in meaningful_keys):
            return True
    return False


def _apply_autosave_columns(order: Order, payload: dict) -> None:
    """Leniently mirror flat draft columns from an autosave payload (no validation)."""
    received_date = payload.get('received_date')
    received_time = payload.get('received_time')
    notes = payload.get('notes')
    if isinstance(received_date, str) and received_date.strip():
        order.received_date = received_date.strip()
    if isinstance(received_time, str):
        order.received_time = received_time.strip() or None
    if notes is not None:
        order.notes = (notes if isinstance(notes, str) else str(notes or '')) or None
    if payload.get('is_self_measurement') is not None:
        order.is_self_measurement = bool(payload.get('is_self_measurement'))
    # is_regional/construction_type: 자동저장은 검증/차단하지 않는다. 미선택 협력사 등
    # 불완전 상태도 그대로 보존하고, 승격(명시 저장) 시점에 PUT /structured가 검증한다.
    if payload.get('is_regional') is not None:
        order.is_regional = bool(payload.get('is_regional'))
    ctype = payload.get('construction_type')
    if isinstance(ctype, str):
        normalized = normalize_regional_construction_type(ctype)
        order.construction_type = normalized or None


@erp_orders_structured_bp.route('/orders/erp/draft/autosave', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_erp_draft_autosave():
    """ERP '새 주문' 자동저장. 부분 입력을 draft에 보존하되 승격하지 않는다.

    PUT /orders/<id>/structured(=명시 저장/승격 경로)와 달리 필수값 검증,
    단계 전환, 이벤트 기록, side-effect, geocode를 일절 수행하지 않는다.
    meta.draft=True를 강제 유지해 대시보드에 노출되지 않게 한다.

    Body: {draft_token, structured_data, received_date, received_time, notes,
           is_self_measurement, is_regional, construction_type}
    Returns: {success, order_id|null, updated_at}
        order_id=null은 "내용이 미약해 서버 draft 미생성(로컬만 저장)" 신호.
    """
    db = get_db()
    try:
        payload = request.get_json(silent=True) or {}
        draft_token = _coerce_draft_token(
            payload.get('draft_token') or request.headers.get('X-ERP-Draft-Token')
        )
        structured_data = payload.get('structured_data')
        if structured_data is not None and not isinstance(structured_data, dict):
            return jsonify({'success': False, 'message': 'structured_data는 JSON 객체여야 합니다.'}), 400

        _lock_draft_token_if_supported(db, draft_token)
        order, already_promoted = _resolve_draft_for_autosave(db, draft_token)
        if already_promoted:
            # 명시 저장이 먼저 커밋됨 → 자동저장은 no-op(draft 부활·중복 행 방지).
            return jsonify({
                'success': True,
                'order_id': None,
                'updated_at': None,
                'skipped': 'already_promoted',
            })
        if order is None:
            # 기존 draft가 없으면 의미 있는 내용이 있을 때만 생성(빈 draft row 폭증 방지).
            if not _structured_has_meaningful_content(structured_data, payload.get('notes') or ''):
                return jsonify({'success': True, 'order_id': None, 'updated_at': None})
            order = _create_session_draft(db, draft_token)

        now = datetime.datetime.now()

        # 데이터 유실 방어(defense-in-depth): 무의미한(빈) 자동저장이 이미 내용이 있는
        # draft를 덮어쓰지 못하게 한다. 클라이언트가 ORDER_ID>0 경로에서 빈 폼을 전송해도
        # 기존 작성분을 보존. 전체를 비우려면 사용자가 '버리기'를 눌러야 한다.
        existing_sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        new_meaningful = _structured_has_meaningful_content(structured_data, payload.get('notes') or '')
        existing_meaningful = _structured_has_meaningful_content(existing_sd, order.notes or '')
        if not new_meaningful and existing_meaningful:
            return jsonify({
                'success': True,
                'order_id': order.id,
                'updated_at': format_updated_at(order.structured_updated_at) if order.structured_updated_at else None,
                'skipped': 'no_downgrade',
            })

        if structured_data is not None:
            sd = copy.deepcopy(structured_data)
            meta = sd.get('meta') if isinstance(sd.get('meta'), dict) else {}
            meta['draft'] = True
            meta.setdefault('created_via', 'ADD_ORDER_AUTOSAVE')
            if draft_token:
                meta['draft_token'] = draft_token
            meta['autosaved_at'] = now.isoformat()
            sd['meta'] = meta
            order.structured_data = sd
            flag_modified(order, 'structured_data')
            sync_erp_flat_columns(order, sd)

        _apply_autosave_columns(order, payload)
        order.status = 'DRAFT'
        order.structured_updated_at = now
        db.commit()
        return jsonify({
            'success': True,
            'order_id': order.id,
            'updated_at': format_updated_at(now),
        })
    except Exception as e:
        try:
            db.rollback()
        except Exception as rb_err:
            logger.warning("draft autosave: rollback failed: %s", rb_err, exc_info=True)
        logger.warning("[ERP_ORDER] draft autosave error: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_structured_bp.route('/orders/erp/draft', methods=['GET'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_erp_get_draft():
    """복원 배너용: 현재 세션 draft 존재/내용 여부를 반환(생성하지 않음).

    Returns: {success, draft: null | {order_id, has_content, updated_at}}
    """
    db = get_db()
    try:
        draft_token = _coerce_draft_token(request.args.get('draft_token'))
        order = _resolve_session_draft(db, draft_token)
        if order is None:
            return jsonify({'success': True, 'draft': None})
        sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        has_content = _structured_has_meaningful_content(sd, order.notes or '')
        updated = order.structured_updated_at
        # updated_at_ms: epoch ms(UTC 기준). 클라이언트 상대시간 계산은 문자열 파싱 대신
        # 이 값을 써야 서버(UTC)·브라우저(KST) 시차로 "9시간 전" 오표시가 안 난다.
        updated_ms = None
        if updated is not None:
            try:
                updated_ms = int(updated.timestamp() * 1000)
            except Exception:
                updated_ms = None
        return jsonify({
            'success': True,
            'draft': {
                'order_id': order.id,
                'has_content': has_content,
                'updated_at': format_updated_at(updated) if updated else None,
                'updated_at_ms': updated_ms,
            },
        })
    except Exception as e:
        logger.warning("[ERP_ORDER] draft get error: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_structured_bp.route('/orders/erp/draft/discard', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_erp_discard_draft():
    """복원 배너 '버리기': 현재 세션 draft를 소프트 삭제하고 세션에서 분리한다.

    Body: {draft_token}
    Returns: {success}
    """
    db = get_db()
    try:
        payload = request.get_json(silent=True) or {}
        draft_token = _coerce_draft_token(
            payload.get('draft_token') or request.headers.get('X-ERP-Draft-Token')
        )
        order = _resolve_session_draft(db, draft_token)
        if order is not None and is_erp_order_draft(order):
            order.status = 'DELETED'
            order.deleted_at = datetime.datetime.now().isoformat()
            db.commit()
        session.pop('erp_draft_order_id', None)
        return jsonify({'success': True})
    except Exception as e:
        try:
            db.rollback()
        except Exception as rb_err:
            logger.warning("draft discard: rollback failed: %s", rb_err, exc_info=True)
        logger.warning("[ERP_ORDER] draft discard error: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

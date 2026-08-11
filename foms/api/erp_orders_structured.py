"""
ERP 주문 구조화 데이터 API (structured GET/PUT, parse-text, erp/draft).
"""

import copy
import datetime
import hashlib
import json
import logging
import time
from typing import Any, List, Mapping, Optional, Tuple

from flask import Blueprint, has_request_context, request, jsonify, session

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
from foms.services.orders.construction_type import normalize_regional_construction_type
from foms.services.orders.stage_override import normalize_main_stage
from foms.services.orders.status_constants import STATUS
from foms.web.auth import log_access, login_required, role_required
from foms.services.audit_message_display import describe_order_action
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.datetime_kst import now_kst
from foms.services.erp_order_flags import (
    is_erp_draft_structured_data,
    is_erp_order_draft,
    is_erp_order_record,
)
from foms.services.erp_sync_columns import sync_erp_flat_columns
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
    schedule = sd.get('schedule') if isinstance(sd.get('schedule'), dict) else {}
    measurement = schedule.get('measurement') if isinstance(schedule.get('measurement'), dict) else {}
    if str(measurement.get('date') or '').strip():
        return True
    if normalize_main_stage(requested_stage) != 'MEASURE':
        return False
    return bool(getattr(order, 'is_regional', False) or getattr(order, 'is_self_measurement', False))


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


def _preserve_operational_structured_state(old_sd: dict, structured_data: dict) -> None:
    """Preserve non-form operational state during ERP order full-form saves."""
    if not isinstance(old_sd, dict) or not isinstance(structured_data, dict):
        return

    for key in _OPERATIONAL_TOP_LEVEL_KEYS:
        if key not in structured_data and key in old_sd:
            structured_data[key] = copy.deepcopy(old_sd.get(key))

    for key in ('workflow', 'assignments', 'shipment', 'meta'):
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
    # 키(as_billing·as_log)는 폼 스냅샷이 되돌리지 못하게 서버값으로 되돌린다. 전자가
    # 단계를, 후자가 AS 서버 상태를 지키므로 둘 다 필요하다.
    _pin_form_stage_to_server(old_sd, structured_data)
    _force_preserve_as_server_state(old_sd, structured_data)


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
    customer = ((structured_data.get('parties') or {}).get('customer') or {})
    cust_name = (customer.get('name') or '').strip()
    cust_phone = (customer.get('phone') or '').strip()
    site = (structured_data.get('site') or {})
    addr = (site.get('address_full') or site.get('address_main') or '').strip()
    items = structured_data.get('items') or []
    first_product = ''
    if items and isinstance(items, list) and len(items) > 0:
        first_product = (items[0].get('product_name') or '').strip()

    if cust_name and cust_name not in _CUSTOMER_PLACEHOLDERS:
        order.customer_name = cust_name
    if cust_phone and cust_phone != '000-0000-0000':
        order.phone = cust_phone
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
            # 지방주문 AS 재상차 모달 prefill용(flat 컬럼, structured_data에는 없음).
            'shipping_scheduled_date': getattr(order, 'shipping_scheduled_date', None) or '',
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
        patch_context = order_audit_context(order)
        log_access(
            describe_order_action(order_id=order_id, action='ORDER_STRUCTURED_SAVED',
                                  note='인라인 수정', **patch_context),
            session.get('user_id'),
            auto_commit=False,
            action='ORDER_STRUCTURED_SAVED', target_type='order', target_id=int(order_id),
            detail={'mode': 'inline', 'field': field, **patch_context},
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
        }), 200
    except ValueError as exc:
        db.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as e:
        db.rollback()
        logger.exception("[ERP_ORDER] structured PATCH 오류: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500


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
        now = datetime.datetime.now()
        # 폼이 고른 단계. _pin_form_stage_to_server 가 곧 서버값으로 덮으므로 여기서 보관한다
        # (실측일 없는 지방주문/자가실측의 실측 단계 이동 판정에만 쓰인다).
        _wf_in = (structured_data or {}).get('workflow') if isinstance(structured_data, dict) else None
        requested_stage = str((_wf_in or {}).get('stage') or '').strip() if isinstance(_wf_in, dict) else ''

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
            old_notes = getattr(o, 'notes', None)
            old_is_regional = getattr(o, 'is_regional', None)
            old_construction_type = getattr(o, 'construction_type', None)

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
                if not structured_data.get('assignments'):
                    structured_data['assignments'] = {}
                _preserve_operational_structured_state(old_sd, structured_data)
                _preserve_or_normalize_construction_workers(old_sd, structured_data)
                # DATA-01 정본 projection: partial allowlist · provenance lock · server pricing.
                project_structured_form(old_sd, structured_data)

                # STATE-FORM-01: 폼 저장은 단계를 바꾸지 않는다. workflow.stage 는
                # _pin_form_stage_to_server 가 이미 서버값으로 고정했고, 단계 전이는
                # 명시적 stage-override(STATE-CORE transition) 경로 전용이다.
                # 실측일 지정 자동 전진도 여기서 쓰지 않고, 커밋 뒤 canonical 엔진이 맡는다.

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

                o.structured_data = copy.deepcopy(structured_data)
                flag_modified(o, 'structured_data')
                sync_erp_flat_columns(o, structured_data)

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
            log_access(
                describe_order_action(order_id=order_id, action='ORDER_STRUCTURED_SAVED',
                                      note='전체 저장', **put_context),
                actor_user_id,
                auto_commit=False,
                action='ORDER_STRUCTURED_SAVED', target_type='order', target_id=int(order_id),
                detail={'mode': 'full', **put_context},
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

        # 실측일이 지정된 접수 건은 canonical 엔진(SET_MAIN_STAGE)으로 실측 단계에 올린다.
        # 폼 트랜잭션 밖에서 별도 전이로 수행해야 STAGE_CHANGED·outbox·receipt 가 다른
        # 전이와 같은 경로로 남는다. 전이 실패는 폼 저장을 되돌리지 않는다(저장은 이미 성공).
        auto_stage_error = None
        if _should_auto_advance_to_measure(order, requested_stage):
            from foms.api.orders.status import apply_canonical_main_stage

            auto_stage_error = apply_canonical_main_stage(
                db,
                order,
                'MEASURE',
                actor_user_id=actor_user_id,
                body={'auto': 'MEASUREMENT_DATE_SET', 'order_id': order_id},
                idempotency_key=None,
            )
            if auto_stage_error is None:
                db.commit()
            else:
                logger.warning(
                    "[ERP_ORDER] 실측일 자동 단계전진 실패: order=%s status=%s",
                    order_id, auto_stage_error[1],
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

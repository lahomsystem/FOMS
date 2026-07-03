"""
ERP 주문 구조화 데이터 API (structured GET/PUT, parse-text, erp/draft).
"""

import copy
import datetime
import json
import logging
import time
from typing import Any, Optional

from flask import Blueprint, request, jsonify, session

logger = logging.getLogger(__name__)
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, OrderEvent, User
from foms.services.orders.estimate_defaults import (
    ERP_DRAFT_PLACEHOLDER_CUSTOMER,
    ERP_DRAFT_PLACEHOLDER_PHONE,
    ERP_DRAFT_PLACEHOLDER_PRODUCT,
)
from foms.services.orders.construction_type import normalize_regional_construction_type
from foms.services.orders.status_constants import STATUS
from foms.web.auth import login_required, role_required
from foms.services.erp_policy import (
    STAGE_LABELS,
    check_quest_approvals_complete,
    create_quest_from_template,
)
from foms.services.datetime_kst import get_today_kst, now_kst
from foms.services.erp_order_flags import is_erp_draft_structured_data, is_erp_order_draft
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.erp_automation import apply_auto_tasks
from foms.services.orders.order_text_parser import parse_order_text
from foms.services.geocode_helpers import extract_address_from_structured_data
from foms.services.jobs.queue import enqueue_geocode_order_address
from foms.services.order_geocode import reset_order_geocode_on_address_change
from foms.services.feature_flags import env_bool
from foms.services.erp_inline_patch import apply_field_patch, is_critical_field
from foms.services.order_draft_service import format_updated_at, parse_updated_at

TEAM_LABELS = {
    'CS': '라홈팀', 'SALES': '영업팀', 'MEASURE': '실측팀',
    'DRAWING': '도면팀', 'PRODUCTION': '생산팀', 'CONSTRUCTION': '시공팀',
}
_CUSTOMER_PLACEHOLDERS = {ERP_DRAFT_PLACEHOLDER_CUSTOMER}
_PRODUCT_PLACEHOLDERS = {ERP_DRAFT_PLACEHOLDER_PRODUCT}
_ERP_DRAFT_TOKEN_MAX_LENGTH = 128

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


def _handle_stage_transition(
    db: Session,
    order: Order,
    old_sd: dict,
    structured_data: dict,
) -> None:
    """단계 전환 감지 및 OrderEvent/Quest 생성."""
    new_stage = (structured_data.get('workflow') or {}).get('stage')
    old_stage = (old_sd.get('workflow') or {}).get('stage')
    if not new_stage or new_stage == old_stage:
        return
    if new_stage in STATUS:
        setattr(order, 'status', new_stage)
        # Entering the AS lifecycle through either stage should stamp the first received date once.
        if new_stage in ('AS', 'AS_RECEIVED') and not getattr(order, 'as_received_date', None):
            setattr(order, 'as_received_date', get_today_kst().strftime('%Y-%m-%d'))
    is_quest_complete, missing_teams = check_quest_approvals_complete(old_sd, old_stage)
    if not is_quest_complete and missing_teams:
        stage_label = STAGE_LABELS.get(old_stage, old_stage) if old_stage else '알 수 없음'
        missing_team_labels = [TEAM_LABELS.get(t, t) for t in missing_teams]
        logger.warning("[%s] Quest 승인 미완료 팀: %s", stage_label, ', '.join(missing_team_labels))
    (structured_data.get('workflow') or {})['stage_updated_at'] = datetime.datetime.now().isoformat()
    db.add(OrderEvent(
        order_id=order.id,
        event_type='STAGE_CHANGED',
        payload={'from': old_stage, 'to': new_stage, 'manual': True},
        created_by_user_id=session.get('user_id')
    ))
    quests = structured_data.get('quests') or []
    has_new_stage_quest = any(
        isinstance(q, dict) and q.get('stage') == new_stage for q in quests
    )
    if not has_new_stage_quest:
        new_quest = create_quest_from_template(new_stage, session.get('username') or '', structured_data)
        if new_quest:
            if not structured_data.get('quests'):
                structured_data['quests'] = []
            structured_data['quests'].append(new_quest)


def _record_structured_events(
    db: Session,
    order: Order,
    old_sd: dict,
    structured_data: dict,
) -> None:
    """긴급/일정/오너팀 변경 이벤트 기록."""
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
        new_meas = ((structured_data.get('schedule') or {}).get('measurement') or {}).get('date')
        old_meas = ((old_sd.get('schedule') or {}).get('measurement') or {}).get('date')
        if new_meas != old_meas:
            db.add(OrderEvent(
                order_id=order.id,
                event_type='MEASUREMENT_DATE_CHANGED',
                payload={'from': old_meas, 'to': new_meas},
                created_by_user_id=session.get('user_id')
            ))
    except Exception as e:
        logger.warning("MEASUREMENT_DATE_CHANGED event record failed: %s", e, exc_info=True)
    try:
        new_cons = ((structured_data.get('schedule') or {}).get('construction') or {}).get('date')
        old_cons = ((old_sd.get('schedule') or {}).get('construction') or {}).get('date')
        if new_cons != old_cons:
            db.add(OrderEvent(
                order_id=order.id,
                event_type='CONSTRUCTION_DATE_CHANGED',
                payload={'from': old_cons, 'to': new_cons},
                created_by_user_id=session.get('user_id')
            ))
    except Exception as e:
        logger.warning("CONSTRUCTION_DATE_CHANGED event record failed: %s", e, exc_info=True)
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


def _finalize_draft_state(
    order: Order,
    structured_data: Optional[dict],
    now: datetime.datetime,
    old_structured_data: Optional[dict] = None,
) -> bool:
    """draft 메타 정리, 플레이스홀더 → 실제 데이터로 flat 컬럼 동기화, session 정리. draft_cleared 여부 반환."""
    draft_cleared = False
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

                # Draft finalize 시 structured_data 의 실제 고객 정보를 flat 컬럼에 동기화
                parties = (structured_data.get('parties') or {})
                customer = (parties.get('customer') or {})
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
        except Exception as e:
            logger.warning("draft meta clear failed: %s", e, exc_info=True)
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
            'received_date': order.received_date or '',
            'received_time': order.received_time or '',
            'notes': order.notes or '',
            'is_self_measurement': getattr(order, 'is_self_measurement', False),
            'is_regional': getattr(order, 'is_regional', False),
            'construction_type': getattr(order, 'construction_type', None) or '',
        })
    except Exception as e:
        logger.exception("[ERP_ORDER] structured GET 오류: %s", e)
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
        order.structured_data = copy.deepcopy(structured_data)
        flag_modified(order, 'structured_data')
        sync_erp_flat_columns(order, structured_data)
        setattr(order, 'structured_updated_at', now)
        db.commit()

        # Tier A(broad): 주문 구조(structured_data) 수정은 workflow.stage/order.status를
        # 포함해 탭 간 이동이 실제로 일어나므로 전체 무효화를 유지한다.
        from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches
        invalidate_all_dashboard_slice_caches()

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
    """구조화 데이터 저장(전사 공용)."""
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
        draft_cleared = False

        if structured_data is not None and not isinstance(structured_data, dict):
            return jsonify({'success': False, 'message': 'structured_data는 JSON 객체여야 합니다.'}), 400

        _sd_raw: Any = order.structured_data
        old_sd = _sd_raw if isinstance(_sd_raw, dict) else {}

        # 모든 structured PUT은 실제 저장/승격 경로다. draft row도 여기서만 실제 주문으로 확정된다.
        if structured_data is not None:
            _missing = _missing_required_structured_fields(structured_data)
            if _missing:
                logger.warning(f"[ERP_ORDER] 필수값 누락 저장 차단 order_id={order_id}: {_missing}")
                return jsonify({
                    'success': False,
                    'message': f"필수 항목을 입력해주세요: {', '.join(_missing)}"
                }), 400

        if raw_order_text is not None:
            setattr(order, 'raw_order_text', raw_order_text)
        if is_self_measurement is not None:
            setattr(order, 'is_self_measurement', bool(is_self_measurement))
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
            setattr(order, 'is_regional', is_regional_flag)
            setattr(order, 'construction_type', normalized_construction_type if is_regional_flag else None)
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
            setattr(order, 'construction_type', normalized_construction_type or None)
        if received_date is not None and isinstance(received_date, str) and received_date.strip():
            setattr(order, 'received_date', received_date.strip())
        if received_time is not None and isinstance(received_time, str):
            setattr(order, 'received_time', received_time.strip() or None)
        if notes is not None:
            setattr(order, 'notes', (notes if isinstance(notes, str) else str(notes or '')) or None)
        if structured_data is not None:
            if not structured_data.get('workflow'):
                structured_data['workflow'] = {}
            if not structured_data.get('flags'):
                structured_data['flags'] = {}
            if not structured_data.get('assignments'):
                structured_data['assignments'] = {}
            _preserve_operational_structured_state(old_sd, structured_data)
            _preserve_or_normalize_construction_workers(old_sd, structured_data)

            try:
                _handle_stage_transition(db, order, old_sd, structured_data)
            except Exception as e:
                logger.warning("단계 전환 검증 오류: %s", e, exc_info=True)

            t0 = time.perf_counter()
            _record_structured_events(db, order, old_sd, structured_data)
            _apply_structured_side_effects(db, order.id, structured_data)
            side_effect_time = (time.perf_counter() - t0) * 1000
            logger.info(f"save latency - side_effects: {side_effect_time:.1f}ms")
            
            draft_cleared = _finalize_draft_state(order, structured_data, now, old_sd)

            order.structured_data = copy.deepcopy(structured_data)
            flag_modified(order, 'structured_data')
            
            sync_erp_flat_columns(order, structured_data)
            
        setattr(order, 'structured_schema_version', int(schema_version) if schema_version else 1)
        setattr(order, 'structured_confidence', confidence or (structured_data.get('confidence') if structured_data else None))
        setattr(order, 'structured_updated_at', now)

        # ERP structured 저장은 자동 ChannelTalk 푸시하지 않는다.
        # 발주방 알림은 ERP Beta 「푸쉬」 수동 전송(/api/channel/push-manual)만 사용.

        address_changed = False
        if structured_data is not None:
            old_addr = (extract_address_from_structured_data(old_sd) or '').strip()
            new_addr = (extract_address_from_structured_data(structured_data) or '').strip()
            if old_addr != new_addr:
                address_changed = True
                reset_order_geocode_on_address_change(order, new_addr)

        db.commit()
        # Tier A(broad): 주문 저장(PUT structured)은 stage/status 변경을 포함 → 탭 이동.
        from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches

        invalidate_all_dashboard_slice_caches()
        commit_time = (time.perf_counter() - start_time) * 1000
        logger.info(f"save latency - main_commit: {commit_time:.1f}ms")

        if address_changed:
            enqueue_geocode_order_address(order_id)

        total_time = (time.perf_counter() - start_time) * 1000
        logger.info(f"save latency - TOTAL: {total_time:.1f}ms")
        return jsonify({'success': True, 'draft_cleared': draft_cleared})
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
        order = db.query(Order).filter(Order.id == int(existing_id), Order.not_deleted_filter()).first()
        if order and is_erp_order_draft(order):
            return order
        session.pop('erp_draft_order_id', None)
    token_order = _find_existing_draft_by_token(db, draft_token)
    if token_order:
        session['erp_draft_order_id'] = token_order.id
        return token_order
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
        True when a customer/site/product/notes signal is present.
    """
    if (received_notes or '').strip():
        return True
    if not isinstance(structured_data, dict):
        return False
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
        order = _resolve_session_draft(db, draft_token)
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

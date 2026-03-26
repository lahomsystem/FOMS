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
from constants import STATUS, ERP_DRAFT_PLACEHOLDER_CUSTOMER, ERP_DRAFT_PLACEHOLDER_PHONE, ERP_DRAFT_PLACEHOLDER_PRODUCT
from apps.auth import login_required, role_required
from services.erp_policy import (
    STAGE_LABELS,
    check_quest_approvals_complete,
    create_quest_from_template,
)
from services.erp_sync_columns import sync_erp_flat_columns
from erp_automation import apply_auto_tasks
from erp_order_text_parser import parse_order_text
from services.geocode_helpers import extract_address_from_structured_data
from services.jobs.queue import enqueue_geocode_order_address, enqueue_channeltalk_push
from services.order_geocode import reset_order_geocode_on_address_change

TEAM_LABELS = {
    'CS': '라홈팀', 'SALES': '영업팀', 'MEASURE': '실측팀',
    'DRAWING': '도면팀', 'PRODUCTION': '생산팀', 'CONSTRUCTION': '시공팀',
}

erp_orders_structured_bp = Blueprint('erp_orders_structured', __name__, url_prefix='/api')
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
        if new_stage == 'AS_RECEIVED' and not getattr(order, 'as_received_date', None):
            setattr(order, 'as_received_date', datetime.date.today().strftime('%Y-%m-%d'))
    elif new_stage == 'AS':
        setattr(order, 'status', 'AS')
        if not getattr(order, 'as_received_date', None):
            setattr(order, 'as_received_date', datetime.date.today().strftime('%Y-%m-%d'))
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
        logger.warning("[ERP_BETA] auto-task apply: %s", e, exc_info=True)


def _finalize_draft_state(
    order: Order,
    structured_data: Optional[dict],
    now: datetime.datetime,
) -> bool:
    """draft 메타 정리 및 session 정리. draft_cleared 여부 반환."""
    draft_cleared = False
    if structured_data:
        try:
            meta = structured_data.get('meta') or {}
            if meta.get('draft') is True:
                meta['draft'] = False
                meta['finalized_at'] = now.isoformat()
                structured_data['meta'] = meta
                draft_cleared = True
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
        order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
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
        })
    except Exception as e:
        logger.exception("[ERP_BETA] structured GET 오류: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_structured_bp.route('/orders/<int:order_id>/structured', methods=['PUT'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_put_order_structured(order_id):
    """구조화 데이터 저장(전사 공용)."""
    start_time = time.perf_counter()
    db = get_db()
    try:
        order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
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
        now = datetime.datetime.now()
        draft_cleared = False

        if structured_data is not None and not isinstance(structured_data, dict):
            return jsonify({'success': False, 'message': 'structured_data는 JSON 객체여야 합니다.'}), 400

        _sd_raw: Any = order.structured_data
        old_sd = _sd_raw if isinstance(_sd_raw, dict) else {}

        if raw_order_text is not None:
            setattr(order, 'raw_order_text', raw_order_text)
        if is_self_measurement is not None:
            setattr(order, 'is_self_measurement', bool(is_self_measurement))
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

            try:
                _handle_stage_transition(db, order, old_sd, structured_data)
            except Exception as e:
                logger.warning("단계 전환 검증 오류: %s", e, exc_info=True)

            t0 = time.perf_counter()
            _record_structured_events(db, order, old_sd, structured_data)
            _apply_structured_side_effects(db, order.id, structured_data)
            side_effect_time = (time.perf_counter() - t0) * 1000
            logger.info(f"save latency - side_effects: {side_effect_time:.1f}ms")
            
            draft_cleared = _finalize_draft_state(order, structured_data, now)

            order.structured_data = copy.deepcopy(structured_data)
            flag_modified(order, 'structured_data')
            
            sync_erp_flat_columns(order, structured_data)
            
        setattr(order, 'structured_schema_version', int(schema_version) if schema_version else 1)
        setattr(order, 'structured_confidence', confidence or (structured_data.get('confidence') if structured_data else None))
        setattr(order, 'structured_updated_at', now)

        from services.channel_delivery import mark_order_updated_for_channel
        mark_order_updated_for_channel(order, "update")

        address_changed = False
        if structured_data is not None:
            old_addr = extract_address_from_structured_data(old_sd)
            new_addr = extract_address_from_structured_data(structured_data)
            if new_addr and old_addr != new_addr:
                address_changed = True
                reset_order_geocode_on_address_change(order, new_addr)

        db.commit()
        commit_time = (time.perf_counter() - start_time) * 1000
        logger.info(f"save latency - main_commit: {commit_time:.1f}ms")

        if address_changed:
            enqueue_geocode_order_address(order_id)
        if structured_data is not None:
            enqueue_channeltalk_push(order_id, "update")

        total_time = (time.perf_counter() - start_time) * 1000
        logger.info(f"save latency - TOTAL: {total_time:.1f}ms")
        return jsonify({'success': True, 'draft_cleared': draft_cleared})
    except Exception as e:
        db.rollback()
        logger.exception("[ERP_BETA] structured PUT 오류: %s", e)
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
        logger.exception("[ERP_BETA] parse-text 오류: %s", e)
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

        from services.channel_delivery import mark_order_updated_for_channel
        mark_order_updated_for_channel(order, "update")

        db.commit()

        ret_payment = {
            'deposit': payment_obj.get('deposit', 0),
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
        logger.exception("[ERP_BETA] payment-confirm 오류: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_structured_bp.route('/orders/erp/draft', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_erp_create_draft():
    """ERP '새 주문' 화면용 draft 주문 생성. order_id를 먼저 확보."""
    db = get_db()
    try:
        existing_id = session.get('erp_draft_order_id')
        if existing_id:
            order = db.query(Order).filter(Order.id == int(existing_id), Order.active_filter()).first()
            if order:
                return jsonify({'success': True, 'order_id': order.id, 'reused': True})

        now = datetime.datetime.now()
        today = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M')
        structured = {
            'workflow': {'stage': 'RECEIVED', 'stage_updated_at': now.isoformat()},
            'flags': {'urgent': False},
            'assignments': {},
            'schedule': {},
            'meta': {'draft': True, 'created_via': 'ADD_ORDER'},
        }

        order = Order(
            received_date=today,
            received_time=time_str,
            customer_name=ERP_DRAFT_PLACEHOLDER_CUSTOMER,
            phone=ERP_DRAFT_PLACEHOLDER_PHONE,
            address='-',
            product=ERP_DRAFT_PLACEHOLDER_PRODUCT,
            options=None,
            notes=None,
            status='RECEIVED',
            is_erp_beta=True,
            raw_order_text='',
            structured_data=structured,
            structured_schema_version=1,
            structured_confidence=None,
            structured_updated_at=now,
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        session['erp_draft_order_id'] = order.id
        return jsonify({'success': True, 'order_id': order.id, 'reused': False})
    except Exception as e:
        try:
            db.rollback()
        except Exception as rb_err:
            logger.warning("draft create: rollback failed: %s", rb_err, exc_info=True)
        logger.warning("[ERP_BETA] draft create error: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

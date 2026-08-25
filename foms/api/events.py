"""
주문 이벤트·변경 로그 API (Palantir-style).
"""

import copy
import hashlib
import json
import uuid
from typing import Any, Dict, List

from foms.services.error_logging import log_handled_exception
from flask import Blueprint, request, jsonify, session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, OrderEvent, OrderFieldChange, User, SecurityLog
from foms.services.audit_message_display import (
    describe_change,
    describe_order_action,
    is_first_fill_row,
    path_label,
    resolve_mirror_rows,
)
from foms.services.datetime_kst import format_datetime_kst
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.field_restore import (
    RestoreRejected,
    apply_restore,
    describe_restorability,
    plan_restore,
)
from foms.services.orders.revision import RevisionError, execute_order_mutation
from foms.services.orders.change_reason import (
    REASON_CODES,
    REASON_OTHER,
    ReasonAttachError,
    attach_reason,
    reason_label,
    reason_stats,
    reasons_for_change_sets,
)
from foms.web.auth.routes import log_access
from foms.services.order_event_display import (
    generate_change_description,
    translate_event_type_to_korean,
    translate_reason_to_korean,
    translate_target_to_korean,
    translate_value_to_korean,
)
from foms.web.auth import login_required, role_required


def get_order_display_name(order):
    """로그 카드에 표시할 주문명(고객명)을 최대한 정확히 추출."""
    if not order:
        return ''

    generic_names = {'erp beta', 'erp_beta', 'beta'}

    def _clean_text(value):
        if value is None:
            return ''
        text = str(value).strip()
        if not text:
            return ''
        if text.lower() in generic_names:
            return ''
        return text

    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    customer = sd.get('customer') if isinstance(sd.get('customer'), dict) else {}
    orderer = sd.get('orderer') if isinstance(sd.get('orderer'), dict) else {}
    contact = sd.get('contact') if isinstance(sd.get('contact'), dict) else {}
    order_node = sd.get('order') if isinstance(sd.get('order'), dict) else {}
    parties = sd.get('parties') if isinstance(sd.get('parties'), dict) else {}
    parties_customer = parties.get('customer') if isinstance(parties.get('customer'), dict) else {}
    parties_orderer = parties.get('orderer') if isinstance(parties.get('orderer'), dict) else {}
    parties_buyer = parties.get('buyer') if isinstance(parties.get('buyer'), dict) else {}
    parties_manager = parties.get('manager') if isinstance(parties.get('manager'), dict) else {}

    candidates = [
        parties_customer.get('name'),
        parties_customer.get('customer_name'),
        # 주문한 사람이 발주사(라홈)보다 앞선다 — parties.orderer 는 발주처 이름이라
        # 카드 제목이 전부 '라홈'이 돼 버린다(ORDERER-AXIS-01).
        parties_buyer.get('name'),
        parties_orderer.get('name'),
        parties_manager.get('name'),
        customer.get('name'),
        customer.get('customer_name'),
        orderer.get('name'),
        contact.get('name'),
        sd.get('client_name'),
        sd.get('client'),
        sd.get('name'),
        sd.get('customer'),
        sd.get('customer_name'),
        sd.get('orderer_name'),
        order_node.get('customer_name'),
        order.customer_name,
    ]
    for candidate in candidates:
        name = _clean_text(candidate)
        if name:
            return name
    return f'주문 #{order.id}'


events_bp = Blueprint('events', __name__, url_prefix='/api')


@events_bp.route('/orders/<int:order_id>/events', methods=['GET'])
@login_required
def api_order_events(order_id):
    """주문 이벤트 스트림 조회(최근 N개).

    ``event_type`` 쿼리 파라미터(쉼표 구분)로 종류를 좁힐 수 있다 — 알림톡 발송 흔적 칩의
    이력 패널처럼 한 종류만 필요한 화면이 200건을 받아 클라이언트에서 거르지 않게 한다.

    사람이 읽을 라벨(``event_label``)과 보낸 사람 이름(``created_by_name``)을 함께 준다.
    이름은 id 집합 한 번의 조회로 붙인다(N+1 금지).
    """
    try:
        db = get_db()
        limit = int(request.args.get('limit', 50))
        limit = max(1, min(limit, 200))

        query = db.query(OrderEvent).filter(OrderEvent.order_id == order_id)
        wanted = [t.strip() for t in (request.args.get('event_type') or '').split(',')]
        wanted = [t for t in wanted if t]
        if wanted:
            query = query.filter(OrderEvent.event_type.in_(wanted))
        rows = query.order_by(OrderEvent.created_at.desc()).limit(limit).all()

        user_ids = {r.created_by_user_id for r in rows if r.created_by_user_id}
        names = {}
        if user_ids:
            names = {
                uid: name
                for uid, name in db.query(User.id, User.name).filter(User.id.in_(user_ids)).all()
            }

        events = []
        for r in rows:
            events.append({
                'id': r.id,
                'order_id': r.order_id,
                'event_type': r.event_type,
                'event_label': translate_event_type_to_korean(r.event_type),
                'payload': r.payload,
                'created_by_user_id': r.created_by_user_id,
                'created_by_name': names.get(r.created_by_user_id),
                'created_at': format_datetime_kst(r.created_at) if r.created_at else None
            })
        return jsonify({'success': True, 'events': events})
    except Exception as e:
        log_handled_exception()
        return jsonify({'success': False, 'message': str(e)}), 500


#: 한 번에 돌려줄 change set(저장 묶음) 상한. 주문 하나의 이력이라 페이지네이션 없이도
#: 충분하지만, 오래 산 주문은 저장이 수백 번이라 상한은 필요하다.
_FIELD_CHANGE_SET_LIMIT = 50

#: change set 하나가 담을 수 있는 변경 행 상한(대량 저장이 응답을 덮지 않게).
_FIELD_CHANGE_ROW_LIMIT = 200


@events_bp.route('/orders/<int:order_id>/field-changes', methods=['GET'])
@login_required
def api_order_field_changes(order_id: int):
    """주문 1건의 필드 변경 이력을 저장 묶음(change set)별로 돌려준다 (ORDER-DIFF-02).

    원장(:class:`~models.OrderFieldChange`)에는 경로와 값만 있고 사람 라벨은 없다 —
    라벨·문장은 표시 SSOT(:mod:`foms.services.audit_message_display`)가 **읽는 시점에** 붙인다
    (라벨을 고치면 과거 이력까지 함께 고쳐진다).

    가시성은 기존 ``/change-events`` 규약을 그대로 따른다: **ADMIN 은 전체, 그 외는 본인이
    바꾼 것만**. 감사 화면(ADMIN 전용)과 달리 이 탭은 현장 직원도 여는 화면이다.

    :param order_id: 대상 주문 id.
    :return: ``{'success': True, 'data': {'change_sets': [...], 'truncated': bool}}``.
    """
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'error': '주문을 찾을 수 없습니다.'}), 404

        user = db.query(User).filter(User.id == session.get('user_id')).first()
        if not user:
            return jsonify({'success': False, 'error': '사용자를 찾을 수 없습니다.'}), 401

        # 최신 change set 부터 상한만큼 고른다(원장 전체를 읽지 않는다).
        set_query = (
            db.query(OrderFieldChange.change_set_id, OrderFieldChange.created_at)
            .filter(OrderFieldChange.order_id == order_id)
        )
        if user.role != 'ADMIN':
            set_query = set_query.filter(OrderFieldChange.actor_user_id == user.id)

        ordered_sets: list[str] = []
        seen: set[str] = set()
        for change_set_id, _created_at in (
            set_query.order_by(OrderFieldChange.id.desc())
            .limit(_FIELD_CHANGE_SET_LIMIT * _FIELD_CHANGE_ROW_LIMIT)
            .all()
        ):
            if change_set_id in seen:
                continue
            seen.add(change_set_id)
            ordered_sets.append(change_set_id)
            if len(ordered_sets) >= _FIELD_CHANGE_SET_LIMIT:
                break

        if not ordered_sets:
            return jsonify({'success': True, 'data': {'change_sets': [], 'truncated': False}})

        rows = (
            db.query(OrderFieldChange)
            .filter(OrderFieldChange.order_id == order_id)
            .filter(OrderFieldChange.change_set_id.in_(ordered_sets))
            .order_by(OrderFieldChange.id)
            .all()  # perf-ok: bounded by change set limit above
        )
        # 되돌리기 가능 판정은 "현재 값" 과 대조해야 하므로 주문 sd 를 한 번만 읽어 돌려쓴다.
        current_sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        actor_ids = {row.actor_user_id for row in rows if row.actor_user_id}
        actors = {}
        if actor_ids:
            actors = {
                u.id: {'name': u.name, 'username': u.username}
                for u in db.query(User).filter(User.id.in_(actor_ids)).all()  # perf-ok: batched
            }

        # 파생 totals 와 입력 payment 가 같은 값을 말하면 화면은 한 줄만 낸다(원장은 둘 다 보존).
        mirror_dropped: set = set()
        mirror_labels: dict = {}
        by_set: dict[str, list] = {}
        for row in rows:
            by_set.setdefault(row.change_set_id, []).append(row)
        for set_rows in by_set.values():
            dropped, labels = resolve_mirror_rows([
                {'id': r.id, 'path': r.path, 'before': r.before_value, 'after': r.after_value}
                for r in set_rows
            ])
            mirror_dropped |= dropped
            mirror_labels.update(labels)

        grouped: dict[str, dict] = {}
        for row in rows:
            if row.id in mirror_dropped:
                continue
            bucket = grouped.setdefault(row.change_set_id, {
                'change_set': row.change_set_id,
                'at': format_datetime_kst(row.created_at) if row.created_at else None,
                'actor': actors.get(row.actor_user_id),
                'changes': [],
                'truncated': 0,
            })
            if len(bucket['changes']) >= _FIELD_CHANGE_ROW_LIMIT:
                bucket['truncated'] += 1
                continue
            payload = {
                'path': row.path,
                'before': row.before_value,
                'after': row.after_value,
                'op': row.op,
                'item': row.item_name,
            }
            # RESTORE-GUI-01 T1: 화면이 버튼을 켤지 끌지 판단하려면 되돌리기 가능 여부와
            # 그 이유가 함께 와야 한다(눌러 보고 400 을 받는 UI 는 만들지 않는다).
            override_label = mirror_labels.get(row.id)
            entry = {
                'id': row.id,
                'label': override_label or path_label(row.path),
                'text': describe_change(payload, label_override=override_label),
                'item': row.item_name,
                # 최초 입력(빈칸→첫 값)은 화면이 접어 둔다 — 원장에는 그대로 남고
                # 펼치면 되돌리기도 그대로 쓸 수 있다(은닉이 아니라 접기).
                'first_fill': is_first_fill_row(row.op, row.before_value),
            }
            entry.update(describe_restorability(row, current_sd))
            bucket['changes'].append(entry)

        # ORDER-REASON-00: "왜" 는 별도 원장에 있다 — change set 단위로 한 번에 붙인다.
        reasons = reasons_for_change_sets(db, grouped.keys())
        for change_set_id, bucket in grouped.items():
            bucket['reason'] = reasons.get(change_set_id)

        return jsonify({'success': True, 'data': {
            'change_sets': [grouped[key] for key in ordered_sets if key in grouped],
            # 상한에 걸렸다면 더 오래된 이력이 남아 있다는 뜻이다(화면이 그 사실을 표시한다).
            'truncated': len(ordered_sets) >= _FIELD_CHANGE_SET_LIMIT,
        }})
    except Exception as e:
        log_handled_exception()
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route('/orders/change-reason-stats', methods=['GET'])
@login_required
@role_required(['ADMIN'])
def api_change_reason_stats():
    """최근 N일 사유 분포와 미입력(우회) 건수를 돌려준다 (ORDER-REASON-00).

    목록형 사유를 택한 이유가 "입력 오류 정정이 이번 달 몇 건"을 묻기 위해서였다. 함께
    돌려주는 ``skipped`` 는 **물었는데 안 붙은 저장** 수다 — 규칙이 과하거나 화면이 불편하면
    이 값이 먼저 커진다.

    :return: ``{'success': True, 'data': {...}}`` (:func:`~foms.services.orders.change_reason.reason_stats`).
    """
    try:
        days = max(1, min(request.args.get('days', 30, type=int) or 30, 365))
        return jsonify({'success': True, 'data': reason_stats(get_db(), days=days)})
    except Exception as e:
        log_handled_exception()
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route('/orders/change-reason-codes', methods=['GET'])
@login_required
def api_change_reason_codes():
    """사유 목록을 화면에 내려준다 (ORDER-REASON-00).

    목록을 JS 에 복사해 두면 서버·클라 2벌이 되고, 코드가 하나 늘 때 화면만 옛 목록을 보인다.
    화면은 처음 사유를 물을 때 한 번만 부른다(정적 상수라 캐시해도 된다).

    :return: ``{'success': True, 'data': {'codes': [{'code','label','note_required'}]}}``.
    """
    return jsonify({'success': True, 'data': {'codes': [
        {'code': code, 'label': reason_label(code), 'note_required': code == REASON_OTHER}
        for code in REASON_CODES
    ]}})


@events_bp.route('/orders/<int:order_id>/change-reason', methods=['POST'])
@login_required
def api_set_order_change_reason(order_id: int):
    """저장 1회(change set)에 **변경 사유**를 붙인다 (ORDER-REASON-00).

    저장 자체는 이미 성공했다 — 사유는 저장을 막지 않는다(막으면 사유 때문에 주문 저장이
    실패한다). 화면은 저장 응답의 ``change_reason_required``·``change_set`` 을 보고 이
    엔드포인트를 부른다(PC=모달, 인라인=배너).

    거절 규칙과 근거는 :func:`~foms.services.orders.change_reason.attach_reason` 에 있다
    (남의 주문·기간 만료·타인 저장·중복 첨부).

    :param order_id: 대상 주문 id.
    :return: ``{'success': True, 'data': {'reason': {...}}}``.
    """
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'error': '주문을 찾을 수 없습니다.'}), 404

        user = db.query(User).filter(User.id == session.get('user_id')).first()
        if not user:
            return jsonify({'success': False, 'error': '사용자를 찾을 수 없습니다.'}), 401

        payload = request.get_json(silent=True) or {}
        try:
            reason = attach_reason(
                db,
                order_id=order_id,
                change_set_id=str(payload.get('change_set') or ''),
                code=payload.get('code'),
                note=payload.get('note'),
                actor_user_id=user.id,
                is_admin=(user.role == 'ADMIN'),
            )
        except ValueError as invalid:
            return jsonify({'success': False, 'error': str(invalid)}), 400
        except ReasonAttachError as refused:
            return jsonify({'success': False, 'error': str(refused)}), refused.status

        log_access(
            describe_order_action(
                order_id=order_id,
                action='ORDER_CHANGE_REASON_SET',
                note=reason_label(reason.reason_code),
                **order_audit_context(order),
            ),
            user.id,
            auto_commit=False,
            action='ORDER_CHANGE_REASON_SET', target_type='order', target_id=int(order_id),
            detail={
                'change_set': reason.change_set_id,
                'reason_code': reason.reason_code,
                # 메모는 사람이 쓴 짧은 문장이라 그대로 싣는다(컬럼 상한 200자).
                'reason_note': reason.reason_note,
            },
        )
        db.commit()

        return jsonify({'success': True, 'data': {'reason': {
            'code': reason.reason_code,
            'label': reason_label(reason.reason_code),
            'note': reason.reason_note,
        }}})
    except Exception as e:
        log_handled_exception()
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route('/orders/<int:order_id>/change-events', methods=['GET'])
@login_required
def api_order_change_events(order_id):
    """변경 이벤트 로그 조회 (ADMIN: 전체, 일반: 본인 로그만)"""
    try:
        db = get_db()
        user_id = session.get('user_id')
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401

        query = db.query(OrderEvent).filter(OrderEvent.order_id == order_id)
        if user.role != 'ADMIN':
            query = query.filter(OrderEvent.created_by_user_id == user_id)

        limit = int(request.args.get('limit', 100))
        limit = max(1, min(limit, 500))
        rows = query.order_by(OrderEvent.created_at.desc()).limit(limit).all()

        user_ids = list(set([r.created_by_user_id for r in rows if r.created_by_user_id]))
        users_map = {}
        if user_ids:
            users = db.query(User).filter(User.id.in_(user_ids)).all()  # perf-ok: user_ids from limited event rows
            users_map = {u.id: {'name': u.name, 'team': u.team} for u in users}

        order = db.query(Order).filter(Order.id == order_id).first()
        customer_name = get_order_display_name(order) if order else f'주문 #{order_id}'

        events = []
        for r in rows:
            payload = r.payload or {}
            creator = users_map.get(r.created_by_user_id, {'name': 'Unknown', 'team': ''})

            event_label = translate_event_type_to_korean(r.event_type)
            target = payload.get('target', '')
            before = payload.get('before', '')
            after = payload.get('after', '')
            reason = translate_reason_to_korean(payload.get('reason', ''), r.event_type, payload)
            is_override = payload.get('is_override', False)

            target_kr = translate_target_to_korean(target)
            before_kr = translate_value_to_korean(target, before)
            after_kr = translate_value_to_korean(target, after)
            how_text = generate_change_description(r.event_type, target_kr, before_kr, after_kr, payload)

            events.append({
                'id': r.id,
                'when': format_datetime_kst(r.created_at) if r.created_at else '',
                'who_name': creator['name'],
                'who_team': creator['team'],
                'what_label': event_label,
                'how_text': how_text,
                'reason': reason,
                'is_override': is_override,
                'override_reason': payload.get('override_reason'),
                'event_type': r.event_type,
                'payload': payload,
            })

        return jsonify({
            'success': True,
            'events': events,
            'total': len(events),
            'customer_name': customer_name,
            'order_id': order_id
        })

    except Exception as e:
        log_handled_exception()
        return jsonify({'success': False, 'message': str(e)}), 500


@events_bp.route('/me/change-events', methods=['GET'])
@login_required
def api_my_change_events():
    """본인의 전체 변경 이벤트 로그 조회 (여러 주문 통합)"""
    try:
        db = get_db()
        user_id = session.get('user_id')
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401

        limit = int(request.args.get('limit', 200))
        limit = max(1, min(limit, 1000))

        rows = db.query(OrderEvent).filter(
            OrderEvent.created_by_user_id == user_id
        ).order_by(OrderEvent.created_at.desc()).limit(limit).all()

        order_ids = list(set([r.order_id for r in rows if r.order_id]))
        orders_map = {}
        if order_ids:
            orders = db.query(Order).filter(Order.id.in_(order_ids)).all()  # perf-ok: order_ids from limited event rows
            orders_map = {
                o.id: {
                    'customer_name': get_order_display_name(o),
                    'order_id': o.id
                }
                for o in orders
            }

        events = []
        for r in rows:
            payload = r.payload or {}
            order_info = orders_map.get(r.order_id, {'customer_name': f'주문 #{r.order_id}', 'order_id': r.order_id})

            event_label = translate_event_type_to_korean(r.event_type)
            action_label = payload.get('action', event_label)
            target = payload.get('target', '')
            before = payload.get('before', '')
            after = payload.get('after', '')
            reason = translate_reason_to_korean(payload.get('reason', ''), r.event_type, payload)
            is_override = payload.get('is_override', False)

            target_kr = translate_target_to_korean(target)
            before_kr = translate_value_to_korean(target, before)
            after_kr = translate_value_to_korean(target, after)
            how_text = generate_change_description(r.event_type, target_kr, before_kr, after_kr, payload)

            events.append({
                'id': r.id,
                'order_id': r.order_id,
                'customer_name': order_info['customer_name'],
                'when': format_datetime_kst(r.created_at) if r.created_at else '',
                'what_label': event_label,
                'how_text': how_text,
                'reason': reason,
                'is_override': is_override,
                'event_type': r.event_type,
            })

        return jsonify({'success': True, 'events': events, 'total': len(events)})

    except Exception as e:
        log_handled_exception()
        return jsonify({'success': False, 'message': str(e)}), 500


# ── typed compensation (generic JSON-path revert 대체) ───────────────────────
# 임의 target 을 이름/JSON-path 로 되돌리던 generic revert route 는 제거됐다(임의
# structured_data 경로 write primitive = 보안 위험). undo 는 아래 registry 에 event_type
# 으로 등록된 typed compensation 만 허용한다 — 각 compensation 은 만지는 key·효과가 코드로
# 고정이고, 요청이 target/JSON-path 를 지정할 수 없다(arbitrary target 0). 되돌리기는
# 원본을 다시 쓰지 않고 append-only 보상 event(CHANGE_REVERTED)를 남긴다(REV-00
# receipt/compensation 모델과 정합; 여기서는 helper 를 route 에 배선하지 않고 structured_data
# 를 직접 쓴다 — REV-00 은 helper 를 route 에 적용하지 않으며 order_mutation_policy 는 이
# packet 이 변경하지 않는다).


class CompensationRejected(Exception):
    """typed compensation 을 안전하게 적용할 수 없음(예: 후속 변경으로 현재 값 불일치).

    Attributes:
        message: 사용자 표시 메시지.
        status_code: HTTP 상태(기본 409 conflict).
    """

    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _split_names(value: object) -> "list[str]":
    """쉼표 구분 이름 문자열을 정규화된 이름 리스트로(‘None’·공백 제거)."""
    if not isinstance(value, str):
        return []
    return [x.strip() for x in value.split(',') if x.strip() and x.strip().lower() != 'none']


def _current_drawing_ids(sd: dict) -> "list[int]":
    """structured_data 의 현재 도면 담당자 user id 리스트(정수만)."""
    assignments = sd.get('assignments') if isinstance(sd.get('assignments'), dict) else {}
    ids = assignments.get('drawing_assignee_user_ids')
    return [int(x) for x in ids if str(x).isdigit()] if isinstance(ids, list) else []


def _compensate_drawing_assignee(db, sd: dict, payload: dict) -> dict:
    """DRAWING_ASSIGNEE_SET 을 되돌린다 — 고정 target 만 쓰는 typed compensation.

    ``assignments.drawing_assignee_user_ids`` 를 event 의 before 상태로 복원하고 파생
    projection(``drawing_assignees``, ``shipment.drawing_managers``) 을 재동기화한다.
    이 handler 가 만지는 key 는 코드로 고정 — 임의 JSON-path 는 없다.

    Args:
        db: 요청 DB 세션.
        sd: 수정할 structured_data(deepcopy, 호출자가 flag_modified/commit).
        payload: 되돌릴 event 의 payload(before_ids/after_ids/before/after).

    Returns:
        보상 event 기록용 dict(target, reverted_value, event_before, event_after).

    Raises:
        CompensationRejected: 현재 값이 event 의 after 예상과 달라 되돌릴 수 없음(409).
    """
    target = 'assignments.drawing_assignee_user_ids'
    after_value = payload.get('after')
    before_value = payload.get('before')
    current_ids = sorted(_current_drawing_ids(sd))

    # after(예상) 상태 확인 — 후속 변경이 있으면 되돌리지 않는다(compensation 불변).
    after_ids = payload.get('after_ids') if isinstance(payload.get('after_ids'), list) else None
    if after_ids is not None:
        expected = sorted(int(x) for x in after_ids if str(x).isdigit())
        if current_ids != expected:
            raise CompensationRejected(
                f'현재 값({current_ids})이 예상 값({expected})과 다릅니다. '
                '이미 다른 변경이 발생했을 수 있습니다.'
            )
    else:
        # 구(舊) event: 이름 기반 비교로 폴백.
        expected_names = _split_names(after_value)
        if expected_names:
            users_now = db.query(User).filter(User.id.in_(current_ids)).all() if current_ids else []  # perf-ok: revert display id batch
            current_names = sorted(u.name for u in users_now if u.name)
            if current_names != sorted(expected_names):
                raise CompensationRejected(
                    f'현재 값({current_names})이 예상 값({sorted(expected_names)})과 다릅니다. '
                    '이미 다른 변경이 발생했을 수 있습니다.'
                )

    # before(되돌릴) id 해석 — id 우선, 구 event 는 이름 폴백.
    before_ids = payload.get('before_ids') if isinstance(payload.get('before_ids'), list) else None
    if before_ids is None:
        names = _split_names(before_value)
        if names:
            users_prev = db.query(User).filter(User.name.in_(names), User.is_active == True).all()  # perf-ok: revert name batch
            before_ids = [u.id for u in users_prev]
        else:
            before_ids = []
    before_ids = [int(x) for x in before_ids if str(x).isdigit()]

    # 고정 target + 파생 projection 만 기록(임의 key write 없음).
    assignments = sd.get('assignments') if isinstance(sd.get('assignments'), dict) else {}
    assignments['drawing_assignee_user_ids'] = before_ids
    sd['assignments'] = assignments

    restored = db.query(User).filter(User.id.in_(before_ids), User.is_active == True).all() if before_ids else []  # perf-ok: revert id batch
    sd['drawing_assignees'] = [{'id': u.id, 'name': u.name, 'team': u.team} for u in restored]
    shipment = sd.get('shipment') if isinstance(sd.get('shipment'), dict) else {}
    shipment['drawing_managers'] = [u.name for u in restored if u.name]
    sd['shipment'] = shipment

    return {
        'target': target,
        'reverted_value': before_ids,
        'event_before': after_value,
        'event_after': before_value,
    }


# event_type → typed compensation handler. 여기 없는 event_type 은 되돌릴 수 없다(400).
_COMPENSATION_REGISTRY = {
    'DRAWING_ASSIGNEE_SET': _compensate_drawing_assignee,
}


@events_bp.route('/orders/<int:order_id>/change-events/<int:event_id>/compensate', methods=['POST'])
@login_required
def api_compensate_change_event(order_id, event_id):
    """등록된 typed compensation 으로만 변경을 되돌린다(generic JSON-path revert 대체).

    ``_COMPENSATION_REGISTRY`` 에 event_type 이 등록된 변경만 되돌리고, 각 compensation 은
    만지는 key·효과가 코드로 고정된다(요청이 임의 target/JSON-path 를 지정할 수 없다).
    미등록 event_type 은 400.

    Args:
        order_id: 대상 주문 ID.
        event_id: 되돌릴 OrderEvent ID.

    Returns:
        JSON ``{success, message, reverted_target, new_value}`` / 실패 시 4xx·5xx.
    """
    try:
        data = request.get_json() or {}
        reason = data.get('reason', '').strip()
        if not reason:
            return jsonify({'success': False, 'message': '되돌리기 사유를 입력해주세요.'}), 400

        db = get_db()
        user_id = session.get('user_id')
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401

        event = db.query(OrderEvent).filter(
            OrderEvent.id == event_id,
            OrderEvent.order_id == order_id
        ).first()
        if not event:
            return jsonify({'success': False, 'message': '이벤트를 찾을 수 없습니다.'}), 404

        # 권한 고정: ADMIN 또는 이벤트 생성자 본인(typed compensation 내부 고정).
        if user.role != 'ADMIN' and event.created_by_user_id != user_id:
            return jsonify({'success': False, 'message': '본인이 생성한 이벤트만 되돌릴 수 있습니다.'}), 403

        handler = _COMPENSATION_REGISTRY.get(event.event_type)
        if handler is None:
            return jsonify({'success': False, 'message': '이 변경 유형은 되돌릴 수 없습니다.'}), 400

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        payload = event.payload or {}
        sd = copy.deepcopy(order.structured_data or {})

        try:
            result = handler(db, sd, payload)
        except CompensationRejected as rej:
            return jsonify({'success': False, 'message': rej.message}), rej.status_code

        order.structured_data = sd
        flag_modified(order, "structured_data")

        revert_payload = {
            'domain': payload.get('domain', 'UNKNOWN'),
            'action': 'REVERTED',
            'target': result['target'],
            'before': result['event_before'],
            'after': result['event_after'],
            'reverted_value': result['reverted_value'],
            'change_method': 'API_COMPENSATE',
            'source_screen': 'change_log_viewer',
            'reason': reason,
            'reverted_event_id': event_id,
            'original_event_type': event.event_type,
        }
        db.add(OrderEvent(
            order_id=order_id,
            event_type='CHANGE_REVERTED',
            payload=revert_payload,
            created_by_user_id=user_id
        ))
        db.add(SecurityLog(
            user_id=user_id,
            message=f"주문 #{order_id} 변경 되돌리기(typed): {result['target']}"
        ))
        db.commit()

        return jsonify({
            'success': True,
            'message': '변경이 성공적으로 되돌려졌습니다.',
            'reverted_target': result['target'],
            'new_value': result['reverted_value']
        })

    except Exception as e:
        db = get_db()
        db.rollback()
        log_handled_exception()
        return jsonify({'success': False, 'message': str(e)}), 500


@events_bp.route('/orders/<int:order_id>/field-changes/<int:change_id>/restore', methods=['POST'])
@login_required
def api_restore_field_change(order_id: int, change_id: int):
    """변경 원장 행 하나를 근거로 그 필드를 이전 값으로 되돌린다 (RESTORE-GUI-01 T1).

    요청은 **원장 행 id 하나**만 받는다 — 경로도 값도 서버가 기록에서 읽으므로 임의
    ``structured_data`` 경로 쓰기가 성립하지 않는다(제거된 generic revert 라우트를 위험 없이
    대체하는 지점이다). 판정·거부 규칙은 :mod:`foms.services.orders.field_restore` 가 소유한다.

    쓰기는 :func:`~foms.services.orders.revision.execute_order_mutation` 으로 감싸 row lock·
    version bump·idempotency receipt 를 얻는다(직접 ``flag_modified`` 금지 — mutation writer
    인벤토리에서 EXTERNAL 로 새지 않게).

    Args:
        order_id: 대상 주문 ID.
        change_id: 되돌릴 ``order_field_changes`` 행 ID.

    Returns:
        JSON ``{'success', 'data': {'path', 'restored_to'}}`` / 실패 시 4xx·5xx.
    """
    db = get_db()
    try:
        data = request.get_json(silent=True) or {}
        reason = str(data.get('reason') or '').strip()
        if not reason:
            return jsonify({'success': False, 'error': '되돌리기 사유를 입력해주세요.'}), 400

        user_id = session.get('user_id')
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({'success': False, 'error': '사용자를 찾을 수 없습니다.'}), 401

        row = db.query(OrderFieldChange).filter(
            OrderFieldChange.id == change_id,
            OrderFieldChange.order_id == order_id,
        ).first()
        if row is None:
            return jsonify({'success': False, 'error': '변경 기록을 찾을 수 없습니다.'}), 404

        # 권한: ADMIN 또는 그 변경을 만든 본인(기존 typed compensation 과 같은 규칙).
        if user.role != 'ADMIN' and row.actor_user_id != user_id:
            return jsonify({'success': False, 'error': '본인이 만든 변경만 되돌릴 수 있습니다.'}), 403

        order = db.query(Order).filter(Order.id == order_id).first()
        if order is None:
            return jsonify({'success': False, 'error': '주문을 찾을 수 없습니다.'}), 404

        current_sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        try:
            plan_restore(row, current_sd)
        except RestoreRejected as rejected:
            return jsonify({'success': False, 'error': rejected.message}), rejected.status_code

        change_set_id = str(uuid.uuid4())
        body = {'change_id': change_id, 'reason': reason, 'change_set': change_set_id}
        applied: Dict[str, Any] = {}

        def _mutate(sess, orders: List[Order]) -> Dict[int, List[str]]:
            """잠긴 row 아래에서 복원을 적용한다(쓰기 본체는 정본 mutator 소유)."""
            locked = orders[0]
            applied.update(apply_restore(
                sess, locked, row,
                actor_user_id=user_id,
                change_set_id=change_set_id,
            ))
            return {locked.id: [f'ORDER_DETAIL:{locked.id}', 'ORDERS_INDEX']}

        try:
            execute_order_mutation(
                db,
                actor_user_id=user_id,
                policy_id='ORDER_FIELD_RESTORE',
                order_ids=[order_id],
                scope_hash=hashlib.sha256(
                    f'ORDER_FIELD_RESTORE:{order_id}:{change_id}'.encode('utf-8')
                ).hexdigest(),
                request_hash=hashlib.sha256(
                    json.dumps(body, sort_keys=True, ensure_ascii=False).encode('utf-8')
                ).hexdigest(),
                mutation=_mutate,
                idempotency_key=(request.headers.get('Idempotency-Key') or '')[:64] or None,
            )
        except RestoreRejected as rejected:
            db.rollback()
            return jsonify({'success': False, 'error': rejected.message}), rejected.status_code
        except RevisionError as conflict:
            db.rollback()
            return jsonify({'success': False, 'error': f'동시 수정이 감지됐습니다: {conflict}'}), 409

        db.add(OrderEvent(
            order_id=order_id,
            event_type='CHANGE_REVERTED',
            payload={
                'domain': 'ORDER_FIELD',
                'action': 'RESTORED',
                'target': applied['path'],
                'before': applied['after'],
                'after': applied['before'],
                'reason': reason,
                'restored_change_id': change_id,
                'change_method': 'API_FIELD_RESTORE',
                'source_screen': 'order_change_history',
            },
            created_by_user_id=user_id,
        ))
        db.add(SecurityLog(
            user_id=user_id,
            action='ORDER_FIELD_RESTORED',
            target_type='ORDER',
            target_id=order_id,
            message=f"주문 #{order_id} 필드 되돌리기: {applied['path']}",
        ))
        db.commit()

        return jsonify({'success': True, 'data': {
            'path': applied['path'],
            'restored_to': applied['before'],
        }})

    except Exception:
        db.rollback()
        log_handled_exception()
        return jsonify({'success': False, 'error': '되돌리기 처리 중 오류가 발생했습니다.'}), 500

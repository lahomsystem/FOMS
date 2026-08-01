"""
주문 이벤트·변경 로그 API (Palantir-style).
"""

import copy
from foms.services.error_logging import log_handled_exception
from flask import Blueprint, request, jsonify, session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, OrderEvent, User, SecurityLog
from foms.services.datetime_kst import format_datetime_kst
from foms.services.order_event_display import (
    generate_change_description,
    translate_event_type_to_korean,
    translate_reason_to_korean,
    translate_target_to_korean,
    translate_value_to_korean,
)
from foms.web.auth import login_required


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
    parties_manager = parties.get('manager') if isinstance(parties.get('manager'), dict) else {}

    candidates = [
        parties_customer.get('name'),
        parties_customer.get('customer_name'),
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
    """주문 이벤트 스트림 조회(최근 N개)"""
    try:
        db = get_db()
        limit = int(request.args.get('limit', 50))
        limit = max(1, min(limit, 200))

        rows = db.query(OrderEvent).filter(OrderEvent.order_id == order_id).order_by(OrderEvent.created_at.desc()).limit(limit).all()
        events = []
        for r in rows:
            events.append({
                'id': r.id,
                'order_id': r.order_id,
                'event_type': r.event_type,
                'payload': r.payload,
                'created_by_user_id': r.created_by_user_id,
                'created_at': format_datetime_kst(r.created_at) if r.created_at else None
            })
        return jsonify({'success': True, 'events': events})
    except Exception as e:
        log_handled_exception()
        return jsonify({'success': False, 'message': str(e)}), 500


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

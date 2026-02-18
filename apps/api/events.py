"""
주문 이벤트·변경 로그 API (Palantir-style).
"""

import copy
from flask import Blueprint, request, jsonify, session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, OrderEvent, User, SecurityLog
from apps.auth import login_required


def translate_target_to_korean(target):
    """영어 타겟을 한글로 변환"""
    target_map = {
        'workflow.stage': '진행 단계',
        'workflow.current_quest': '현재 퀘스트',
        'quests': '퀘스트',
        'quest.team_approvals': '팀 승인',
        'quest.assignee_approval': '담당자 승인',
        'assignments.drawing_assignee_user_ids': '도면 담당자',
        'drawings.status': '도면 상태',
        'production.completed': '생산 완료',
        'construction.completed': '시공 완료',
        'cs.completed': 'CS 완료',
        'as.status': 'AS 상태',
    }
    return target_map.get(target, target)


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


def translate_event_type_to_korean(event_type):
    """이벤트 타입 영문 코드를 한글 라벨로 변환."""
    labels = {
        'QUEST_APPROVAL_CHANGED': '퀘스트 승인',
        'QUEST_ASSIGNEE_APPROVED': '담당자 승인',
        'QUEST_CREATED': '퀘스트 생성',
        'QUEST_UPDATED': '퀘스트 수정',
        'QUEST_COMPLETED': '퀘스트 완료',
        'STAGE_CHANGED': '단계 변경',
        'STAGE_AUTO_TRANSITIONED': '단계 자동 전환',
        'STAGE_MANUAL_OVERRIDE': '단계 수동 변경',
        'DRAWING_STATUS_CHANGED': '도면 상태 변경',
        'DRAWING_ASSIGNEE_SET': '도면 담당자 지정',
        'DRAWING_SENT': '도면 전달',
        'DRAWING_CONFIRMED': '도면 확인',
        'DRAWING_REVISION_REQUESTED': '도면 수정 요청',
        'PRODUCTION_STARTED': '생산 시작',
        'PRODUCTION_COMPLETED': '생산 완료',
        'PRODUCTION_DELAYED': '생산 지연',
        'CONSTRUCTION_STARTED': '시공 시작',
        'CONSTRUCTION_COMPLETED': '시공 완료',
        'CONSTRUCTION_SCHEDULED': '시공 예약',
        'CS_STARTED': 'CS 시작',
        'CS_COMPLETED': 'CS 완료',
        'CS_ISSUE_REPORTED': 'CS 이슈 보고',
        'AS_STARTED': 'AS 시작',
        'AS_COMPLETED': 'AS 완료',
        'AS_RECEIVED': 'AS 접수',
        'MEASUREMENT_SCHEDULED': '실측 예약',
        'MEASUREMENT_COMPLETED': '실측 완료',
        'SHIPMENT_SCHEDULED': '출고 예정',
        'SHIPMENT_COMPLETED': '출고 완료',
        'CHANGE_REVERTED': '변경 되돌림',
        'ORDER_CREATED': '주문 생성',
        'ORDER_UPDATED': '주문 수정',
        'ORDER_DELETED': '주문 삭제',
        'ASSIGNMENT_CHANGED': '담당자 변경',
        'STATUS_CHANGED': '상태 변경',
        'FIELD_UPDATED': '필드 수정',
        'COMMENT_ADDED': '메모 추가',
        'ATTACHMENT_ADDED': '첨부파일 추가',
        'ATTACHMENT_DELETED': '첨부파일 삭제',
        'URGENT_CHANGED': '긴급 여부 변경',
    }
    return labels.get(event_type, '기타 변경')


def translate_reason_to_korean(reason, event_type='', payload=None):
    """시스템 reason 코드를 사람이 이해하기 쉬운 한글로 변환."""
    payload = payload or {}
    raw = str(reason or '').strip()
    if not raw:
        raw = str(payload.get('override_reason') or '').strip()
    if not raw and event_type == 'STAGE_AUTO_TRANSITIONED':
        raw = 'quest_approvals_complete'

    if not raw:
        return ''

    reason_map = {
        'quest_approvals_complete': '퀘스트 승인 조건이 충족되어 자동 전환되었습니다.',
        'all_approvals_complete': '모든 승인 조건이 충족되었습니다.',
        'auto_transition_rule_matched': '자동 단계 전환 규칙에 따라 처리되었습니다.',
        'manager_override': '관리자 권한으로 예외 처리되었습니다.',
        'emergency_override': '긴급 권한으로 예외 처리되었습니다.',
        'manual_update': '담당자가 수동으로 변경했습니다.',
    }
    if raw in reason_map:
        return reason_map[raw]

    if '_' in raw and raw.islower():
        return raw.replace('_', ' ')
    return raw


def translate_value_to_korean(target, value):
    """값을 한글로 변환"""
    if not value:
        return '없음'

    if isinstance(value, bool):
        return '완료' if value else '미완료'

    if 'stage' in target.lower():
        stage_map = {
            'MEASURE': '실측',
            'DRAWING': '도면',
            'CONFIRM': '고객확인',
            'PRODUCTION': '생산',
            'CONSTRUCTION': '시공',
            'CS': 'CS',
            'AS': 'AS',
            'SHIPMENT': '출고',
        }
        return stage_map.get(str(value), value)

    if 'approval' in target.lower():
        if isinstance(value, dict):
            if value.get('approved'):
                return f"승인됨 ({value.get('approved_by_name', '담당자')})"
            return '미승인'
        return '승인됨' if value else '미승인'

    if 'drawing' in target.lower() and 'status' in target.lower():
        status_map = {
            'pending': '대기중',
            'sent': '전달됨',
            'confirmed': '확인완료',
            'revision_requested': '수정요청',
        }
        return status_map.get(str(value), value)

    return str(value)


def generate_change_description(event_type, target_kr, before_kr, after_kr, payload):
    """이벤트 타입에 따라 이해하기 쉬운 설명 생성"""
    payload = payload or {}

    if event_type == 'QUEST_APPROVAL_CHANGED':
        team = payload.get('team', '')
        team_map = {'CS': 'CS팀', 'SALES': '영업팀', 'DRAWING': '도면팀',
                   'PRODUCTION': '생산팀', 'CONSTRUCTION': '시공팀', 'SHIPMENT': '출고팀'}
        team_kr = team_map.get(team, team)
        return f"{team_kr}이 퀘스트를 승인했습니다"

    if event_type == 'QUEST_ASSIGNEE_APPROVED':
        approved_by = payload.get('approved_by_name', '담당자')
        quest_title = payload.get('quest_title', '')
        return f"{approved_by}님이 '{quest_title}' 퀘스트를 승인했습니다"

    if event_type == 'STAGE_CHANGED':
        return f"진행 단계를 '{before_kr}'에서 '{after_kr}'로 변경했습니다"

    if event_type == 'STAGE_AUTO_TRANSITIONED':
        return f"퀘스트 완료로 인해 단계가 '{before_kr}'에서 '{after_kr}'로 자동 전환되었습니다"

    if event_type == 'DRAWING_ASSIGNEE_SET':
        assignees = payload.get('assignee_names', [])
        if not assignees:
            after_raw = payload.get('after')
            if isinstance(after_raw, str):
                assignees = [x.strip() for x in after_raw.split(',') if x.strip() and x.strip().lower() != 'none']
        if assignees:
            return f"도면 담당자를 {', '.join(assignees)}님으로 지정했습니다"
        return "도면 담당자를 지정했습니다"

    if event_type == 'DRAWING_STATUS_CHANGED':
        return f"도면 상태를 '{before_kr}'에서 '{after_kr}'로 변경했습니다"

    if event_type == 'PRODUCTION_COMPLETED':
        return "생산을 완료 처리했습니다"
    if event_type == 'PRODUCTION_STARTED':
        return "생산을 시작했습니다"
    if event_type == 'CONSTRUCTION_COMPLETED':
        return "시공을 완료 처리했습니다"
    if event_type == 'CONSTRUCTION_STARTED':
        return "시공을 시작했습니다"
    if event_type == 'CS_COMPLETED':
        return "CS를 완료 처리했습니다"
    if event_type == 'CS_STARTED':
        return "CS를 시작했습니다"
    if event_type == 'AS_STARTED':
        return "AS를 시작했습니다"
    if event_type == 'AS_COMPLETED':
        return "AS를 완료 처리했습니다"
    if event_type == 'AS_RECEIVED':
        return "AS를 접수했습니다"
    if event_type == 'MEASUREMENT_SCHEDULED':
        return "실측 일정을 등록했습니다"
    if event_type == 'MEASUREMENT_COMPLETED':
        return "실측을 완료했습니다"
    if event_type == 'SHIPMENT_SCHEDULED':
        return "출고 일정을 등록했습니다"
    if event_type == 'SHIPMENT_COMPLETED':
        return "출고를 완료했습니다"

    if event_type == 'CHANGE_REVERTED':
        return f"이전 변경사항을 되돌렸습니다 ({translate_target_to_korean(payload.get('target', ''))})"

    if event_type == 'ORDER_CREATED':
        return "주문을 생성했습니다"
    if event_type == 'ORDER_UPDATED':
        return "주문 정보를 수정했습니다"
    if event_type == 'ORDER_DELETED':
        return "주문을 삭제했습니다"
    if event_type == 'ASSIGNMENT_CHANGED':
        return "담당자를 변경했습니다"
    if event_type == 'URGENT_CHANGED':
        return "긴급 여부를 변경했습니다"

    if target_kr and before_kr and after_kr:
        return f"{target_kr}를 '{before_kr}'에서 '{after_kr}'로 변경했습니다"
    if target_kr:
        return f"{target_kr} 변경"
    return "변경 이력"


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
                'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S') if r.created_at else None
            })
        return jsonify({'success': True, 'events': events})
    except Exception as e:
        import traceback
        print(f"주문 이벤트 조회 오류: {e}")
        print(traceback.format_exc())
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
            users = db.query(User).filter(User.id.in_(user_ids)).all()
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
                'when': r.created_at.strftime('%Y-%m-%d %H:%M:%S') if r.created_at else '',
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
        import traceback
        print(f"변경 이벤트 조회 오류: {e}")
        print(traceback.format_exc())
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
            orders = db.query(Order).filter(Order.id.in_(order_ids)).all()
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
                'when': r.created_at.strftime('%Y-%m-%d %H:%M:%S') if r.created_at else '',
                'what_label': event_label,
                'how_text': how_text,
                'reason': reason,
                'is_override': is_override,
                'event_type': r.event_type,
            })

        return jsonify({'success': True, 'events': events, 'total': len(events)})

    except Exception as e:
        import traceback
        print(f"내 변경 이벤트 조회 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@events_bp.route('/orders/<int:order_id>/change-events/<int:event_id>/revert', methods=['POST'])
@login_required
def api_revert_change_event(order_id, event_id):
    """변경 이벤트 되돌리기 (Rollback)"""
    try:
        data = request.get_json() or {}
        revert_reason = data.get('reason', '').strip()

        if not revert_reason:
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

        if user.role != 'ADMIN' and event.created_by_user_id != user_id:
            return jsonify({'success': False, 'message': '본인이 생성한 이벤트만 되돌릴 수 있습니다.'}), 403

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        payload = event.payload or {}
        target = payload.get('target', '')
        before_value = payload.get('before')
        after_value = payload.get('after')

        if not target or before_value is None:
            return jsonify({'success': False, 'message': '되돌리기 정보가 불완전합니다.'}), 400

        sd = order.structured_data or {}
        keys = target.split('.')
        current_obj = sd
        for k in keys[:-1]:
            if k not in current_obj or not isinstance(current_obj[k], dict):
                current_obj[k] = {}
            current_obj = current_obj[k]

        last_key = keys[-1]
        current_value = current_obj.get(last_key)

        is_drawing_assignee_target = (target == 'assignments.drawing_assignee_user_ids')
        is_expected_state = False
        current_display = current_value
        expected_display = after_value

        if is_drawing_assignee_target:
            current_ids = current_value if isinstance(current_value, list) else []
            expected_ids = payload.get('after_ids') if isinstance(payload.get('after_ids'), list) else None
            if expected_ids is not None:
                current_norm = sorted([int(x) for x in current_ids if str(x).isdigit()])
                expected_norm = sorted([int(x) for x in expected_ids if str(x).isdigit()])
                is_expected_state = (current_norm == expected_norm)
                current_display = current_norm
                expected_display = expected_norm
            else:
                expected_names = []
                if isinstance(after_value, str):
                    expected_names = [x.strip() for x in after_value.split(',') if x.strip() and x.strip().lower() != 'none']
                if expected_names:
                    users_now = db.query(User).filter(User.id.in_(current_ids)).all() if current_ids else []
                    current_names = [u.name for u in users_now if u.name]
                    is_expected_state = (sorted(current_names) == sorted(expected_names))
                    current_display = ', '.join(current_names) if current_names else 'None'
                    expected_display = ', '.join(expected_names) if expected_names else 'None'
                else:
                    is_expected_state = (str(current_value) == str(after_value))
        else:
            is_expected_state = (str(current_value) == str(after_value))

        if not is_expected_state:
            return jsonify({
                'success': False,
                'message': f'현재 값({current_display})이 예상 값({expected_display})과 다릅니다. 이미 다른 변경이 발생했을 수 있습니다.'
            }), 409

        revert_to_value = before_value
        if is_drawing_assignee_target:
            before_ids = payload.get('before_ids') if isinstance(payload.get('before_ids'), list) else None
            if before_ids is None:
                if isinstance(before_value, list):
                    before_ids = before_value
                elif isinstance(before_value, str):
                    names = [x.strip() for x in before_value.split(',') if x.strip() and x.strip().lower() != 'none']
                    if names:
                        users_prev = db.query(User).filter(User.name.in_(names), User.is_active == True).all()
                        before_ids = [u.id for u in users_prev]
                    else:
                        before_ids = []
                elif before_value in (None, 'None', ''):
                    before_ids = []
            if before_ids is not None:
                revert_to_value = before_ids

        current_obj[last_key] = revert_to_value

        if is_drawing_assignee_target:
            ids_for_sync = revert_to_value if isinstance(revert_to_value, list) else []
            restored_users = db.query(User).filter(User.id.in_(ids_for_sync), User.is_active == True).all() if ids_for_sync else []
            sd['drawing_assignees'] = [{'id': u.id, 'name': u.name, 'team': u.team} for u in restored_users]
            shipment = sd.get('shipment') or {}
            shipment['drawing_managers'] = [u.name for u in restored_users if u.name]
            sd['shipment'] = shipment

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")

        revert_payload = {
            'domain': payload.get('domain', 'UNKNOWN'),
            'action': 'REVERTED',
            'target': target,
            'before': after_value,
            'after': before_value,
            'reverted_value': revert_to_value,
            'change_method': 'API_REVERT',
            'source_screen': 'change_log_viewer',
            'reason': revert_reason,
            'reverted_event_id': event_id,
            'original_event_type': event.event_type,
        }

        revert_event = OrderEvent(
            order_id=order_id,
            event_type='CHANGE_REVERTED',
            payload=revert_payload,
            created_by_user_id=user_id
        )
        db.add(revert_event)
        db.add(SecurityLog(
            user_id=user_id,
            message=f"주문 #{order_id} 변경 되돌리기: {target} ({after_value} -> {before_value})"
        ))

        db.commit()

        return jsonify({
            'success': True,
            'message': '변경이 성공적으로 되돌려졌습니다.',
            'reverted_target': target,
            'new_value': before_value
        })

    except Exception as e:
        db = get_db()
        db.rollback()
        import traceback
        print(f"변경 되돌리기 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

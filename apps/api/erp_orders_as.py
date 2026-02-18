"""
ERP 주문 AS(설치) API. (Phase 4-5h)
erp.py에서 분리: as/start, as/complete, as/schedule.
"""
import copy
import datetime

from flask import Blueprint, request, jsonify, session

from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, OrderEvent, SecurityLog
from apps.auth import login_required, get_user_by_id
from services.erp_permissions import erp_edit_required
from apps.erp import _ensure_dict

erp_orders_as_bp = Blueprint(
    'erp_orders_as',
    __name__,
    url_prefix='/api/orders',
)


@erp_orders_as_bp.route('/<int:order_id>/as/start', methods=['POST'])
@login_required
@erp_edit_required
def api_as_start(order_id):
    """AS 시작 (CS 단계에서 AS가 필요한 경우)"""
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        data = request.get_json() or {}
        as_reason = data.get('reason', '')
        as_description = data.get('description', '')

        user_id = session.get('user_id')
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}

        as_info = sd.get('as_info') or []
        as_entry = {
            'id': len(as_info) + 1,
            'started_at': datetime.datetime.now().isoformat(),
            'started_by': user.name if user else 'Unknown',
            'reason': as_reason,
            'description': as_description,
            'status': 'OPEN',
            'visit_date': None,
            'completed_at': None
        }
        as_info.append(as_entry)
        sd['as_info'] = as_info

        wf['stage'] = 'AS'
        wf['stage_updated_at'] = datetime.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'

        hist = wf.get('history') or []
        hist.append({
            'stage': 'AS',
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': f'AS 시작: {as_reason}'
        })
        wf['history'] = hist
        sd['workflow'] = wf

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = 'AS'

        event_payload = {
            'domain': 'AS_DOMAIN',
            'action': 'AS_STARTED',
            'target': 'workflow.stage',
            'before': 'CS',
            'after': 'AS',
            'change_method': 'API',
            'source_screen': 'erp_cs_dashboard',
            'reason': f'AS 시작: {as_reason}',
            'as_id': as_entry['id'],
            'as_description': as_description
        }
        db.add(OrderEvent(
            order_id=order_id,
            event_type='AS_STARTED',
            payload=event_payload,
            created_by_user_id=user_id
        ))
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 시작: {as_reason}"))
        db.commit()

        return jsonify({
            'success': True,
            'message': 'AS가 시작되었습니다.',
            'new_status': 'AS',
            'as_id': as_entry['id']
        })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_as_bp.route('/<int:order_id>/as/complete', methods=['POST'])
@login_required
@erp_edit_required
def api_as_complete(order_id):
    """AS 완료 → CS 복귀"""
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        data = request.get_json() or {}
        as_id = data.get('as_id')
        completion_note = data.get('note', '')

        user_id = session.get('user_id')
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}

        as_info = sd.get('as_info') or []
        for entry in as_info:
            if isinstance(entry, dict) and (entry.get('id') == as_id or as_id is None):
                if entry.get('status') == 'OPEN':
                    entry['status'] = 'COMPLETED'
                    entry['completed_at'] = datetime.datetime.now().isoformat()
                    entry['completed_by'] = user.name if user else 'Unknown'
                    entry['completion_note'] = completion_note
                    break
        sd['as_info'] = as_info

        wf['stage'] = 'CS'
        wf['stage_updated_at'] = datetime.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'

        hist = wf.get('history') or []
        hist.append({
            'stage': 'CS',
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': 'AS 완료 → CS 복귀'
        })
        wf['history'] = hist
        sd['workflow'] = wf

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = 'CS'

        event_payload = {
            'domain': 'AS_DOMAIN',
            'action': 'AS_COMPLETED',
            'target': 'workflow.stage',
            'before': 'AS',
            'after': 'CS',
            'change_method': 'API',
            'source_screen': 'erp_as_dashboard',
            'reason': 'AS 완료 → CS 복귀',
            'as_id': as_id,
            'completion_note': completion_note
        }
        db.add(OrderEvent(
            order_id=order_id,
            event_type='AS_COMPLETED',
            payload=event_payload,
            created_by_user_id=user_id
        ))
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 완료 → CS 복귀"))
        db.commit()

        return jsonify({'success': True, 'message': 'AS가 완료되었습니다.', 'new_status': 'CS'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_as_bp.route('/<int:order_id>/as/schedule', methods=['POST'])
@login_required
@erp_edit_required
def api_as_schedule(order_id):
    """AS 방문일 확정"""
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        data = request.get_json() or {}
        as_id = data.get('as_id')
        visit_date = data.get('visit_date')
        visit_time = data.get('visit_time', '')

        if not visit_date:
            return jsonify({'success': False, 'message': '방문일을 입력해주세요.'}), 400

        user_id = session.get('user_id')
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)

        as_info = sd.get('as_info') or []
        for entry in as_info:
            if isinstance(entry, dict) and (entry.get('id') == as_id or as_id is None):
                if entry.get('status') == 'OPEN':
                    entry['visit_date'] = visit_date
                    entry['visit_time'] = visit_time
                    entry['scheduled_by'] = user.name if user else 'Unknown'
                    entry['scheduled_at'] = datetime.datetime.now().isoformat()
                    break
        sd['as_info'] = as_info

        schedule = sd.get('schedule') or {}
        construction = schedule.get('construction') or {}
        construction['date'] = visit_date
        construction['time'] = visit_time
        construction['type'] = 'AS'
        schedule['construction'] = construction
        sd['schedule'] = schedule

        wf = sd.get('workflow') or {}
        hist = wf.get('history') or []
        hist.append({
            'stage': 'AS',
            'updated_at': datetime.datetime.now().isoformat(),
            'updated_by': user.name if user else 'Unknown',
            'note': f'AS 방문일 확정: {visit_date}'
        })
        wf['history'] = hist
        sd['workflow'] = wf

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 방문일 확정: {visit_date}"))
        db.commit()

        return jsonify({
            'success': True,
            'message': f'AS 방문일이 {visit_date}로 확정되었습니다.',
            'visit_date': visit_date
        })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

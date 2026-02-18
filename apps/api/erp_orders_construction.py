"""
ERP 주문 시공 API. (Phase 4-5g)
erp.py에서 분리: construction/start, construction/complete, construction/fail.
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

erp_orders_construction_bp = Blueprint(
    'erp_orders_construction',
    __name__,
    url_prefix='/api/orders',
)


@erp_orders_construction_bp.route('/<int:order_id>/construction/start', methods=['POST'])
@login_required
@erp_edit_required
def api_construction_start(order_id):
    """시공 시작 (히스토리 기록)"""
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': 'Order not found'}), 404

        user_id = session.get('user_id')
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}

        hist = wf.get('history') or []
        hist.append({
            'stage': 'CONSTRUCTION',
            'updated_at': datetime.datetime.now().isoformat(),
            'updated_by': user.name if user else 'Unknown',
            'note': '시공 시작'
        })
        wf['history'] = hist
        sd['workflow'] = wf

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 시공 시작"))
        db.commit()

        return jsonify({'success': True, 'message': '시공이 시작되었습니다.'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_construction_bp.route('/<int:order_id>/construction/complete', methods=['POST'])
@login_required
@erp_edit_required
def api_construction_complete(order_id):
    """시공 완료 → CS 단계로 이동"""
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': 'Order not found'}), 404

        user_id = session.get('user_id')
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}

        wf['stage'] = 'CS'
        wf['stage_updated_at'] = datetime.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'

        hist = wf.get('history') or []
        hist.append({
            'stage': 'CS',
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': '시공 완료 → CS 단계 진입'
        })
        wf['history'] = hist
        sd['workflow'] = wf

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = 'CS'

        event_payload = {
            'domain': 'CONSTRUCTION_DOMAIN',
            'action': 'CONSTRUCTION_COMPLETED',
            'target': 'workflow.stage',
            'before': 'CONSTRUCTION',
            'after': 'CS',
            'change_method': 'API',
            'source_screen': 'erp_construction_dashboard',
            'reason': '시공 완료 → CS 단계 진입'
        }
        order_event = OrderEvent(
            order_id=order_id,
            event_type='CONSTRUCTION_COMPLETED',
            payload=event_payload,
            created_by_user_id=user_id
        )
        db.add(order_event)

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 시공 완료 → CS 단계 진입"))
        db.commit()

        return jsonify({
            'success': True,
            'message': '시공이 완료되었습니다. CS 단계로 이동합니다.',
            'new_status': 'CS'
        })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_construction_bp.route('/<int:order_id>/construction/fail', methods=['POST'])
@login_required
@erp_edit_required
def api_construction_fail(order_id):
    """시공 불가 → 원인별 재작업 단계로 이동"""
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        data = request.get_json() or {}
        reason = data.get('reason', 'site_issue')
        detail = data.get('detail', '')
        reschedule_date = data.get('reschedule_date')

        user_id = session.get('user_id')
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}

        fail_info = sd.get('construction_fail_history') or []
        fail_entry = {
            'id': len(fail_info) + 1,
            'failed_at': datetime.datetime.now().isoformat(),
            'failed_by': user.name if user else 'Unknown',
            'reason': reason,
            'detail': detail,
            'reschedule_date': reschedule_date,
            'previous_stage': 'CONSTRUCTION'
        }
        fail_info.append(fail_entry)
        sd['construction_fail_history'] = fail_info

        reason_stage_map = {
            'drawing_error': 'DRAWING',
            'measurement_error': 'MEASURE',
            'product_defect': 'PRODUCTION',
            'site_issue': 'CONSTRUCTION'
        }
        new_stage = reason_stage_map.get(reason, 'CONSTRUCTION')

        wf['stage'] = new_stage
        wf['stage_updated_at'] = datetime.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'
        wf['rework_reason'] = reason

        reason_labels = {
            'drawing_error': '도면 오류',
            'measurement_error': '실측 오류',
            'product_defect': '제품 불량',
            'site_issue': '현장 문제'
        }
        hist = wf.get('history') or []
        hist.append({
            'stage': new_stage,
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': f'시공 불가 → {reason_labels.get(reason, reason)}: {detail}'
        })
        wf['history'] = hist
        sd['workflow'] = wf

        if reschedule_date:
            schedule = sd.get('schedule') or {}
            construction = schedule.get('construction') or {}
            construction['date'] = reschedule_date
            construction['rescheduled'] = True
            construction['reschedule_reason'] = reason
            schedule['construction'] = construction
            sd['schedule'] = schedule

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = new_stage

        db.add(SecurityLog(
            user_id=user_id,
            message=f"주문 #{order_id} 시공 불가: {reason_labels.get(reason, reason)}"
        ))
        db.commit()

        return jsonify({
            'success': True,
            'message': f'시공 불가로 처리되었습니다. {reason_labels.get(reason, reason)}로 인해 {new_stage} 단계로 이동합니다.',
            'new_status': new_stage,
            'reason': reason
        })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

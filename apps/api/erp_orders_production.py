"""
ERP 주문 생산(제작) API. (Phase 4-5f)
erp.py에서 분리: production/start, production/complete.
"""
import copy
import datetime

from flask import Blueprint, jsonify, session

from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, OrderEvent, SecurityLog
from apps.auth import login_required, get_user_by_id
from services.erp_permissions import erp_edit_required
from apps.erp import _ensure_dict

erp_orders_production_bp = Blueprint(
    'erp_orders_production',
    __name__,
    url_prefix='/api/orders',
)


@erp_orders_production_bp.route('/<int:order_id>/production/start', methods=['POST'])
@login_required
@erp_edit_required
def api_production_start(order_id):
    """제작 시작 (PRODUCTION 단계로 이동)"""
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        user_id = session.get('user_id')
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}

        wf['stage'] = 'PRODUCTION'
        wf['stage_updated_at'] = datetime.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'

        hist = wf.get('history') or []
        hist.append({
            'stage': 'PRODUCTION',
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': '제작 시작'
        })
        wf['history'] = hist
        sd['workflow'] = wf

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = 'PRODUCTION'

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 제작 시작 (PRODUCTION)"))
        db.commit()

        return jsonify({'success': True, 'message': '제작이 시작되었습니다.', 'new_status': 'PRODUCTION'})

    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_production_bp.route('/<int:order_id>/production/complete', methods=['POST'])
@login_required
@erp_edit_required
def api_production_complete(order_id):
    """제작 완료 (CONSTRUCTION 단계로 이동)"""
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        user_id = session.get('user_id')
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}

        wf['stage'] = 'CONSTRUCTION'
        wf['stage_updated_at'] = datetime.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'

        hist = wf.get('history') or []
        hist.append({
            'stage': 'CONSTRUCTION',
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': '제작 완료 (시공/출고 대기)'
        })
        wf['history'] = hist
        sd['workflow'] = wf

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = 'CONSTRUCTION'

        event_payload = {
            'domain': 'PRODUCTION_DOMAIN',
            'action': 'PRODUCTION_COMPLETED',
            'target': 'workflow.stage',
            'before': 'PRODUCTION',
            'after': 'CONSTRUCTION',
            'change_method': 'API',
            'source_screen': 'erp_production_dashboard',
            'reason': '제작 완료 (시공 대기)'
        }
        order_event = OrderEvent(
            order_id=order_id,
            event_type='PRODUCTION_COMPLETED',
            payload=event_payload,
            created_by_user_id=user_id
        )
        db.add(order_event)

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 제작 완료 (CONSTRUCTION)"))
        db.commit()

        return jsonify({
            'success': True,
            'message': '제작이 완료되었습니다. (시공 대기 상태로 변경)',
            'new_status': 'CONSTRUCTION'
        })

    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

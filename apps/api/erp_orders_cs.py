"""
ERP 주문 CS API. (Phase 4-5h)
erp.py에서 분리: cs/complete.
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

erp_orders_cs_bp = Blueprint(
    'erp_orders_cs',
    __name__,
    url_prefix='/api/orders',
)


@erp_orders_cs_bp.route('/<int:order_id>/cs/complete', methods=['POST'])
@login_required
@erp_edit_required
def api_cs_complete(order_id):
    """
    CS 단계 완료 처리
    원본 요구사항: CS(H) 완료 후 → COMPLETED(최종 완료) 단계로 이동
    """
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        user_id = session.get('user_id')
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}

        wf['stage'] = 'COMPLETED'
        wf['stage_updated_at'] = datetime.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'

        hist = wf.get('history') or []
        hist.append({
            'stage': 'COMPLETED',
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': 'CS 완료 → 최종 완료'
        })
        wf['history'] = hist
        sd['workflow'] = wf

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = 'COMPLETED'

        event_payload = {
            'domain': 'CS_DOMAIN',
            'action': 'CS_COMPLETED',
            'target': 'workflow.stage',
            'before': 'CS',
            'after': 'COMPLETED',
            'change_method': 'API',
            'source_screen': 'erp_cs_dashboard',
            'reason': 'CS 완료 → 최종 완료'
        }
        db.add(OrderEvent(
            order_id=order_id,
            event_type='CS_COMPLETED',
            payload=event_payload,
            created_by_user_id=user_id
        ))
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} CS 완료 → 최종 완료"))
        db.commit()

        return jsonify({'success': True, 'message': 'CS가 완료되었습니다.', 'new_status': 'COMPLETED'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

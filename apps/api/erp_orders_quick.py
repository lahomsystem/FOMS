"""
ERP 주문 Quick API. (Phase 4-5a)
erp.py에서 분리: 빠른 검색·상세·상태 변경 (quick-search, quick-info, quick-status).
"""
import copy
import datetime as dt_mod

from flask import Blueprint, request, jsonify, session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, SecurityLog
from apps.auth import login_required, get_user_by_id
from services.erp_permissions import erp_edit_required
from apps.erp import (
    _normalize_for_search,
    _ensure_dict,
    apply_erp_display_fields_to_orders,
)
from services.erp_policy import STAGE_LABELS, create_quest_from_template

erp_orders_quick_bp = Blueprint(
    'erp_orders_quick',
    __name__,
    url_prefix='/api/orders',
)


@erp_orders_quick_bp.route('/quick-search', methods=['GET'])
@login_required
def api_order_quick_search():
    """빠른 상태 변경용 주문 검색 (고객명/주문번호)"""
    try:
        q = (request.args.get('q') or '').strip()
        if not q:
            return jsonify({'success': False, 'message': '검색어를 입력해주세요.'}), 400

        db = get_db()
        q_norm = _normalize_for_search(q).lower()

        rows = (
            db.query(Order)
            .filter(Order.deleted_at.is_(None))
            .order_by(Order.id.desc())
            .limit(500)
            .all()
        )

        def _customer_display(o):
            sd = _ensure_dict(o.structured_data)
            return (
                (((sd.get('parties') or {}).get('customer') or {}).get('name'))
                or o.customer_name
                or ''
            )

        def _manager_display(o):
            sd = _ensure_dict(o.structured_data)
            return (
                (((sd.get('parties') or {}).get('manager') or {}).get('name'))
                or o.manager_name
                or ''
            )

        matched = [
            r for r in rows
            if q_norm in _normalize_for_search(_customer_display(r)).lower()
            or q_norm in _normalize_for_search(_manager_display(r)).lower()
            or q_norm in _normalize_for_search(r.order_number or '').lower()
            or (r.id and str(r.id) == q.strip())
        ]

        if not matched:
            return jsonify({'success': False, 'message': '검색 결과가 없습니다.', 'orders': []})

        apply_erp_display_fields_to_orders(matched)
        orders_payload = [
            {
                'id': o.id,
                'order_number': o.order_number,
                'customer_name': _customer_display(o),
                'manager_name': _manager_display(o),
                'status': o.status,
                'status_label': STAGE_LABELS.get(o.status, o.status),
            }
            for o in matched[:20]
        ]
        return jsonify({'success': True, 'orders': orders_payload})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_quick_bp.route('/<int:order_id>/quick-info', methods=['GET'])
@login_required
def api_order_quick_info(order_id):
    """빠른 상태 변경용 주문 상세 (quick-search 후 선택 시)"""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id, Order.deleted_at.is_(None)).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        apply_erp_display_fields_to_orders([order])
        sd = _ensure_dict(order.structured_data)
        customer_name = (((sd.get('parties') or {}).get('customer') or {}).get('name')) or order.customer_name or ''
        manager_name = (((sd.get('parties') or {}).get('manager') or {}).get('name')) or order.manager_name or ''
        return jsonify({
            'success': True,
            'order': {
                'id': order.id,
                'order_number': order.order_number,
                'customer_name': customer_name,
                'manager_name': manager_name,
                'status': order.status,
                'status_label': STAGE_LABELS.get(order.status, order.status),
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_quick_bp.route('/<int:order_id>/quick-status', methods=['POST'])
@login_required
@erp_edit_required
def api_order_quick_status_update(order_id):
    """빠른 상태 변경 처리"""
    db = None
    try:
        data = request.get_json(silent=True) or {}
        new_status = (data.get('status') or '').strip()
        note = data.get('note')

        if not new_status:
            return jsonify({'success': False, 'message': '변경할 상태가 필요합니다.'}), 400

        legacy_to_stage = {
            'MEASURED': 'MEASURE',
            'REGIONAL_MEASURED': 'MEASURE',
            'AS_RECEIVED': 'AS',
            'AS_COMPLETED': 'CS',
            'SCHEDULED': 'CONSTRUCTION',
            'SHIPPED_PENDING': 'PRODUCTION',
        }
        new_status = legacy_to_stage.get(new_status, new_status)

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        old_status = order.status

        if old_status == new_status:
            return jsonify({'success': True, 'message': '변경된 내용이 없습니다.'})

        order.status = new_status

        sd = _ensure_dict(order.structured_data)
        user = get_user_by_id(session.get('user_id'))
        user_name = user.name if user else 'Unknown'
        wf = sd.get('workflow') or {}
        old_stage = wf.get('stage')

        wf['stage'] = new_status
        wf['stage_updated_at'] = dt_mod.datetime.now().isoformat()
        wf['stage_updated_by'] = user_name

        hist = wf.get('history') or []
        hist.append({
            'stage': new_status,
            'updated_at': wf['stage_updated_at'],
            'updated_by': user_name,
            'note': note or f'빠른 상태 변경: {old_status} → {new_status}'
        })
        wf['history'] = hist
        sd['workflow'] = wf

        quests = sd.get('quests') or []
        for q in quests:
            if isinstance(q, dict) and q.get('stage') in (old_status, old_stage) and q.get('status') == 'OPEN':
                q['status'] = 'SKIPPED'
                q['updated_at'] = dt_mod.datetime.now().isoformat()
                q['note'] = '빠른 상태 변경으로 건너뜀'

        new_quest = create_quest_from_template(new_status, user_name, sd)
        if new_quest:
            quests.append(new_quest)

        sd['quests'] = quests
        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, 'structured_data')
        db.flush()

        log_msg = f"빠른 상태 변경: {old_status} → {new_status}"
        if note:
            log_msg += f" (메모: {note})"
        user_id = session.get('user_id')
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} {log_msg}"))

        db.commit()
        return jsonify({'success': True, 'message': '상태가 변경되었습니다.'})

    except Exception as e:
        if db is not None:
            db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

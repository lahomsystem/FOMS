"""
ERP 주문 AS(설치) API. (Phase 4-5h)
erp.py에서 분리: as/start, as/complete, as/schedule.
"""
import datetime

from flask import Blueprint, request, jsonify, session

from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, OrderEvent, SecurityLog
from apps.auth import login_required, get_user_by_id
from services.erp_permissions import erp_edit_required, erp_construction_edit_required
from services.erp_sync_columns import sync_erp_flat_columns
from services.erp_utils import ensure_path
from services.as_content_safety import (
    load_structured_data_dict_or_raise,
    sanitize_as_content_html,
)

erp_orders_as_bp = Blueprint(
    'erp_orders_as',
    __name__,
    url_prefix='/api/orders',
)


def _load_order_structured_data_for_update(order):
    """structured_data가 안전할 때만 AS 쓰기 작업 진행."""
    try:
        return load_structured_data_dict_or_raise(getattr(order, 'structured_data', None))
    except ValueError as exc:
        raise ValueError(
            f'structured_data를 안전하게 불러올 수 없어 저장을 중단했습니다: {exc}'
        ) from exc


@erp_orders_as_bp.route('/<int:order_id>/as/start', methods=['POST'])
@login_required
@erp_edit_required
def api_as_start(order_id):
    """AS 시작 (CS 단계에서 AS가 필요한 경우)"""
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        data = request.get_json() or {}
        as_reason = data.get('reason', '')
        as_description = data.get('description', '')

        user_id = session.get('user_id')
        user = get_user_by_id(user_id)

        sd = _load_order_structured_data_for_update(order)
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

        order.structured_data = sd
        flag_modified(order, "structured_data")
        order.status = 'AS'
        sync_erp_flat_columns(order, sd)

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
    except ValueError as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 409
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
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        data = request.get_json() or {}
        as_id = data.get('as_id')
        completion_note = data.get('note', '')

        user_id = session.get('user_id')
        user = get_user_by_id(user_id)

        sd = _load_order_structured_data_for_update(order)
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

        order.structured_data = sd
        flag_modified(order, "structured_data")
        order.status = 'CS'
        sync_erp_flat_columns(order, sd)

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
    except ValueError as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 409
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_as_bp.route('/<int:order_id>/as/register', methods=['POST'])
@login_required
@erp_construction_edit_required
def api_as_register(order_id):
    """AS 접수 등록: 시공 대시보드에서 AS 이미지 업로드 후 호출. as_content 저장, 접수일=오늘, status=AS_RECEIVED."""
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        data = request.get_json(silent=True) or {}
        as_content = sanitize_as_content_html(data.get('as_content'))

        today = datetime.datetime.now().strftime('%Y-%m-%d')
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        sd = _load_order_structured_data_for_update(order)
        shipment = ensure_path(sd, 'shipment')
        shipment['as_content'] = as_content
        wf = sd.get('workflow') or {}
        wf['stage'] = 'AS_RECEIVED'
        wf['stage_updated_at'] = datetime.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'
        sd['workflow'] = wf
        order.structured_data = sd
        flag_modified(order, 'structured_data')

        order.as_received_date = today
        order.status = 'AS_RECEIVED'
        sync_erp_flat_columns(order, sd)

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 접수 등록 (접수일: {today})"))
        db.commit()

        return jsonify({
            'success': True,
            'message': 'AS 접수가 등록되었습니다.',
            'as_received_date': today,
            'new_status': 'AS_RECEIVED',
        })
    except ValueError as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 409
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
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        data = request.get_json() or {}
        as_id = data.get('as_id')
        visit_date = data.get('visit_date')
        visit_time = data.get('visit_time', '')

        if not visit_date:
            return jsonify({'success': False, 'message': '방문일을 입력해주세요.'}), 400

        user_id = session.get('user_id')
        user = get_user_by_id(user_id)

        sd = _load_order_structured_data_for_update(order)

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
        as_visit = schedule.get('as_visit') or {}
        as_visit['date'] = visit_date
        as_visit['time'] = visit_time
        as_visit['type'] = 'AS'
        schedule['as_visit'] = as_visit
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

        order.structured_data = sd
        flag_modified(order, "structured_data")

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 방문일 확정: {visit_date}"))
        db.commit()

        return jsonify({
            'success': True,
            'message': f'AS 방문일이 {visit_date}로 확정되었습니다.',
            'visit_date': visit_date
        })
    except ValueError as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 409
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

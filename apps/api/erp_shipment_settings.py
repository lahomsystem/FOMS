"""
ERP 출고 설정 페이지 및 API. (Phase 4-2)
erp.py에서 분리. 서비스는 services/erp_shipment_settings 사용.
"""
import datetime

from flask import Blueprint, request, jsonify, session, render_template
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order
from apps.auth import login_required, role_required, get_user_by_id
from apps.erp import can_edit_erp, erp_edit_required
from services.erp_shipment_settings import (
    load_erp_shipment_settings,
    save_erp_shipment_settings,
    normalize_erp_shipment_workers,
)

erp_shipment_bp = Blueprint('erp_shipment', __name__)


@erp_shipment_bp.route('/erp/shipment-settings')
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def erp_shipment_settings():
    """ERP 출고 설정 페이지."""
    settings = load_erp_shipment_settings()
    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    return render_template(
        'erp_shipment_settings.html',
        settings=settings,
        can_edit_erp=can_edit_erp(current_user),
    )


@erp_shipment_bp.route('/api/erp/shipment-settings', methods=['GET'])
@login_required
def api_erp_shipment_settings_get():
    """출고 설정 목록 조회."""
    settings = load_erp_shipment_settings()
    return jsonify({'success': True, 'settings': settings})


@erp_shipment_bp.route('/api/erp/shipment-settings', methods=['POST'])
@login_required
@erp_edit_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_erp_shipment_settings_save():
    """출고 설정 저장."""
    try:
        payload = request.get_json(silent=True) or {}
        current = load_erp_shipment_settings()
        for key in ('construction_time', 'drawing_manager', 'construction_workers', 'site_extra'):
            if key in payload and isinstance(payload[key], list):
                if key == 'construction_workers':
                    current[key] = normalize_erp_shipment_workers(payload[key])
                elif key == 'site_extra':
                    cleaned = []
                    for x in payload[key]:
                        if isinstance(x, dict):
                            text = str(x.get('text', '')).strip()
                        else:
                            text = str(x).strip()
                        if text:
                            cleaned.append(text)
                    current[key] = cleaned
                else:
                    current[key] = [str(x).strip() for x in payload[key] if str(x).strip()]
        if save_erp_shipment_settings(current):
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': '저장 실패'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@erp_shipment_bp.route('/api/erp/shipment/update/<int:order_id>', methods=['POST'])
@login_required
@erp_edit_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_erp_shipment_update(order_id):
    """출고 대시보드 업데이트."""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id, Order.status != 'DELETED').first()
        if not order:
            return jsonify({'success': False, 'error': '주문을 찾을 수 없습니다.'}), 404
        if not order.is_erp_beta and order.status not in ('AS_RECEIVED', 'AS_COMPLETED'):
            return jsonify({'success': False, 'error': 'ERP Beta 또는 AS 주문만 수정할 수 있습니다.'}), 400

        payload = request.get_json(silent=True) or {}
        structured_data = dict(order.structured_data or {})

        if 'shipment' not in structured_data:
            structured_data['shipment'] = {}

        shipment = structured_data['shipment']

        if 'site_extra' in payload:
            site_extra = payload.get('site_extra')
            if isinstance(site_extra, list):
                normalized = []
                for x in site_extra:
                    if isinstance(x, dict):
                        text = (x.get('text') or '').strip()
                        color = (x.get('color') or 'black').strip() or 'black'
                        if text:
                            normalized.append({'text': text, 'color': color})
                    else:
                        t = str(x).strip()
                        if t:
                            normalized.append({'text': t, 'color': 'black'})
                shipment['site_extra'] = normalized
            else:
                shipment['site_extra'] = []
        if 'construction_time' in payload:
            shipment['construction_time'] = str(payload.get('construction_time', '')).strip()
        if 'drawing_manager' in payload:
            shipment['drawing_manager'] = str(payload.get('drawing_manager', '')).strip()
        if 'drawing_managers' in payload:
            dms = payload.get('drawing_managers')
            if isinstance(dms, list):
                shipment['drawing_managers'] = [str(x).strip() for x in dms if str(x).strip()]
            else:
                shipment['drawing_managers'] = []
        if 'construction_workers' in payload:
            workers = payload.get('construction_workers')
            if isinstance(workers, list):
                shipment['construction_workers'] = [str(x).strip() for x in workers]
            else:
                shipment['construction_workers'] = []

        structured_data['shipment'] = shipment
        order.structured_data = structured_data
        order.structured_updated_at = datetime.datetime.now()
        flag_modified(order, 'structured_data')
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        import traceback
        print(f"[ERP_SHIPMENT] 업데이트 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

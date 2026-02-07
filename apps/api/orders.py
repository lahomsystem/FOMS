
from flask import Blueprint, jsonify, request, session, current_app
from apps.auth import login_required, role_required, log_access
from db import get_db
from models import Order
from constants import STATUS
from sqlalchemy import or_, and_, func
from sqlalchemy.orm.attributes import flag_modified
import traceback
import json

orders_bp = Blueprint('orders', __name__, url_prefix='/api')

def ensure_path(parent, key):
    if key not in parent or not isinstance(parent.get(key), dict):
        parent[key] = {}
    return parent[key]

@orders_bp.route('/update_regional_status', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def update_regional_status():
    """지방 주문 및 자가실측 체크리스트 상태 업데이트"""
    db = get_db()
    data = request.get_json()
    
    order_id = data.get('order_id')
    field = data.get('field')
    value = data.get('value')

    order = db.query(Order).filter_by(id=order_id).first()

    if not order or (not order.is_regional and not order.is_self_measurement):
        return jsonify({'success': False, 'message': '유효하지 않은 주문입니다.'}), 404

    # 업데이트 가능한 필드인지 확인 (보안 목적)
    allowed_fields = [
        'measurement_completed',
        'regional_sales_order_upload',
        'regional_blueprint_sent',
        'regional_order_upload',
        'regional_cargo_sent',
        'regional_construction_info_sent'
    ]
    if field not in allowed_fields:
        return jsonify({'success': False, 'message': '허용되지 않은 필드입니다.'}), 400

    try:
        setattr(order, field, value)
        db.commit()
        order_type = "자가실측" if order.is_self_measurement else "지방 주문"
        log_access(f"{order_type} #{order.id}의 '{field}' 상태를 '{value}'(으)로 변경", session['user_id'])
        return jsonify({'success': True, 'message': '상태가 업데이트되었습니다.'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500

@orders_bp.route('/update_regional_memo', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def update_regional_memo():
    """지방 주문 메모 업데이트"""
    db = get_db()
    data = request.get_json()
    
    order_id = data.get('order_id')
    memo = data.get('memo', '')

    order = db.query(Order).filter_by(id=order_id).first()

    if not order or (not order.is_regional and not order.is_self_measurement):
        return jsonify({'success': False, 'message': '유효하지 않은 주문입니다.'}), 404

    try:
        order.regional_memo = memo
        db.commit()
        order_type = "자가실측" if order.is_self_measurement else "지방 주문"
        log_access(f"{order_type} #{order.id}의 메모를 업데이트", session['user_id'])
        return jsonify({'success': True, 'message': '메모가 저장되었습니다.'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500

@orders_bp.route('/update_order_field', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def update_order_field():
    """주문 필드 업데이트 (수도권 및 지방 대시보드용)"""
    db = get_db()
    data = request.get_json()
    
    order_id = data.get('order_id')
    # 두 가지 파라미터명 지원: field/value (수도권), field_name/new_value (지방)
    field = data.get('field') or data.get('field_name')
    value = data.get('value') or data.get('new_value')

    order = db.query(Order).filter_by(id=order_id).first()

    if not order:
        return jsonify({'success': False, 'message': '유효하지 않은 주문입니다.'}), 404

    # 업데이트 가능한 필드인지 확인 (보안 목적)
    allowed_fields = [
        'manager_name', 'scheduled_date', 'status',  # 기존 필드들
        'shipping_scheduled_date', 'completion_date',  # 지방 대시보드 날짜 필드들
        'measurement_completed', 'regional_sales_order_upload',  # 지방 체크박스 필드들
        'regional_blueprint_sent', 'regional_order_upload',
        'regional_cargo_sent', 'regional_construction_info_sent',
        'as_received_date', 'as_completed_date',  # AS 관련 날짜 필드들
        'as_visit_date', 'as_content', # AS 방문일 및 내용 (직접 입력용)
        'measurement_date',  # 실측일 필드
        'regional_memo',  # 메모 필드 허용 (수납장 대시보드 등)
        'is_cabinet', 'cabinet_status',  # 수납장 관련
        'shipping_fee'  # 배송비 필드 (수납장 대시보드용)
    ]
    if field not in allowed_fields:
        return jsonify({'success': False, 'message': f'허용되지 않은 필드입니다: {field}'}), 400

    try:
        old_value = getattr(order, field, None)
        if field == 'as_visit_date':
            order.scheduled_date = value
        elif field == 'as_content':
            # as_content는 모델 필드가 아니므로 건너뜀 (아래 structured_data 로직에서 처리)
            pass
        else:
            setattr(order, field, value)

        # ERP Beta 주문이거나 structured_data 연동이 필요한 필드(as_content 등)인 경우
        if order.is_erp_beta or field == 'as_content' or field == 'as_visit_date':
            # structured_data가 None이면 빈 딕셔너리로 초기화 (JSONB 필드 대응)
            if order.structured_data is None:
                order.structured_data = {}
            
            if isinstance(order.structured_data, dict):
                sd = order.structured_data
            else:
                sd = {}

            if field == 'manager_name':
                parties = ensure_path(sd, 'parties')
                manager = ensure_path(parties, 'manager')
                manager['name'] = value
                flag_modified(order, 'structured_data')
            elif field == 'measurement_date':
                schedule = ensure_path(sd, 'schedule')
                measurement = ensure_path(schedule, 'measurement')
                measurement['date'] = value
                flag_modified(order, 'structured_data')
            elif field == 'scheduled_date':
                schedule = ensure_path(sd, 'schedule')
                construction = ensure_path(schedule, 'construction')
                construction['date'] = value
                flag_modified(order, 'structured_data')
            elif field == 'customer_name':
                parties = ensure_path(sd, 'parties')
                customer = ensure_path(parties, 'customer')
                customer['name'] = value
                flag_modified(order, 'structured_data')
            elif field == 'phone':
                parties = ensure_path(sd, 'parties')
                customer = ensure_path(parties, 'customer')
                customer['phone'] = value
                flag_modified(order, 'structured_data')
            elif field == 'address':
                site = ensure_path(sd, 'site')
                site['address_full'] = value
                flag_modified(order, 'structured_data')
            elif field == 'as_visit_date':
                # as_visit_date는 scheduled_date 필드와 동기화
                schedule = ensure_path(sd, 'schedule')
                construction = ensure_path(schedule, 'construction')
                construction['date'] = value
                order.scheduled_date = value
                flag_modified(order, 'structured_data')
            elif field == 'as_content':
                # as_content는 structured_data.shipment.as_content에 저장
                shipment = ensure_path(sd, 'shipment')
                shipment['as_content'] = value
                flag_modified(order, 'structured_data')

        db.commit()
        
        # 상태 변경 시 특별한 로깅
        if field == 'status':
            log_access(f"자가실측 주문 #{order.id} 상태 변경: '{old_value}' → '{value}'", session['user_id'])
        else:
            log_access(f"주문 #{order.id}의 '{field}' 필드를 '{value}'(으)로 변경", session['user_id'])
        
        return jsonify({'success': True, 'message': '정보가 업데이트되었습니다.'})
    except Exception as e:
        db.rollback()
        current_app.logger.error(f"주문 #{order_id} 필드 업데이트 실패: {str(e)}")
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500

@orders_bp.route('/update_order_status', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def update_order_status():
    """수도권 대시보드에서 주문 상태 직접 변경"""
    db = get_db()  # Define outside try block for proper error handling
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        new_status = data.get('status')
        
        if not order_id or not new_status:
            return jsonify({'success': False, 'message': '필수 파라미터가 누락되었습니다.'}), 400
        
        # 유효한 상태인지 확인
        if new_status not in STATUS:
            return jsonify({'success': False, 'message': '유효하지 않은 상태입니다.'}), 400
        
        order = db.query(Order).filter(Order.id == order_id).first()
        
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        
        # 상태 업데이트
        old_status = order.status
        order.status = new_status
        db.commit()
        
        # 로그 기록
        user_id = session.get('user_id')
        old_status_name = STATUS.get(old_status, old_status)
        new_status_name = STATUS.get(new_status, new_status)
        log_access(f"주문 #{order_id} 상태 변경: {old_status_name} → {new_status_name}", user_id)
        
        return jsonify({
            'success': True,
            'old_status': old_status,
            'new_status': new_status,
            'status_display': STATUS.get(new_status, new_status)
        })
        
    except Exception as e:
        db.rollback()
        current_app.logger.error(f"주문 상태 업데이트 실패: {str(e)}")
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500

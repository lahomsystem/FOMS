"""
견적서/계약서 API Blueprint.

엔드포인트:
  POST   /api/orders/<order_id>/estimates        — 견적서 생성
  GET    /api/orders/<order_id>/estimates        — 주문별 견적서 목록
  GET    /api/estimates/<estimate_id>            — 견적서 상세 조회
  PUT    /api/estimates/<estimate_id>            — 견적서 수정
  DELETE /api/estimates/<estimate_id>            — 견적서 삭제
  GET    /api/orders/<order_id>/estimate-preview — 주문 데이터에서 견적서 미리보기 데이터 추출
"""
import logging

from flask import Blueprint, request, jsonify, session

from db import get_db
from models import Order, OrderEstimate
from apps.auth import login_required
from constants import ESTIMATE_COMPANY_INFO, ESTIMATE_PAYMENT_INFO, ESTIMATE_LEGAL_NOTICE
from foms.services.estimate_service import (
    create_estimate,
    update_estimate,
    extract_estimate_data_from_order,
)

logger = logging.getLogger(__name__)

erp_estimates_bp = Blueprint('erp_estimates', __name__, url_prefix='/api')


@erp_estimates_bp.route('/orders/<int:order_id>/estimate-preview', methods=['GET'])
@login_required
def get_estimate_preview(order_id: int):
    """주문의 structured_data에서 견적서 프리뷰 데이터를 추출한다."""
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return jsonify({'success': False, 'error': '주문을 찾을 수 없습니다.'}), 404

    try:
        data = extract_estimate_data_from_order(order)
    except Exception:
        logger.exception("견적서 프리뷰 추출 실패: order_id=%d", order_id)
        return jsonify({'success': False, 'error': '견적서 데이터를 불러오는 중 오류가 발생했습니다.'}), 500

    data['company_info'] = ESTIMATE_COMPANY_INFO
    data['payment_info'] = ESTIMATE_PAYMENT_INFO
    data['legal_notice'] = ESTIMATE_LEGAL_NOTICE

    return jsonify({'success': True, 'data': data})


@erp_estimates_bp.route('/orders/<int:order_id>/estimates', methods=['POST'])
@login_required
def create_order_estimate(order_id: int):
    """주문에 대한 견적서를 생성한다."""
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return jsonify({'success': False, 'error': '주문을 찾을 수 없습니다.'}), 404

    payload = request.get_json(silent=True) or {}
    user_id = session.get('user_id')

    try:
        estimate = create_estimate(
            db, order,
            override_data=payload.get('override_data'),
            created_by_user_id=user_id,
        )
        db.commit()
        return jsonify({'success': True, 'data': estimate.to_dict()}), 201

    except Exception:
        db.rollback()
        logger.exception("견적서 생성 실패: order_id=%d", order_id)
        return jsonify({'success': False, 'error': '견적서 생성 중 오류가 발생했습니다.'}), 500


@erp_estimates_bp.route('/orders/<int:order_id>/estimates', methods=['GET'])
@login_required
def list_order_estimates(order_id: int):
    """주문에 연결된 견적서 목록을 조회한다."""
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return jsonify({'success': False, 'error': '주문을 찾을 수 없습니다.'}), 404

    estimates = (
        db.query(OrderEstimate)
        .filter(OrderEstimate.order_id == order_id)
        .order_by(OrderEstimate.created_at.desc())
        .all()
    )

    return jsonify({
        'success': True,
        'data': [e.to_dict() for e in estimates],
        'company_info': ESTIMATE_COMPANY_INFO,
        'payment_info': ESTIMATE_PAYMENT_INFO,
        'legal_notice': ESTIMATE_LEGAL_NOTICE,
    })


@erp_estimates_bp.route('/estimates/<int:estimate_id>', methods=['GET'])
@login_required
def get_estimate(estimate_id: int):
    """견적서 단건 상세 조회."""
    db = get_db()
    estimate = db.query(OrderEstimate).filter(OrderEstimate.id == estimate_id).first()
    if not estimate:
        return jsonify({'success': False, 'error': '견적서를 찾을 수 없습니다.'}), 404

    return jsonify({
        'success': True,
        'data': estimate.to_dict(),
        'company_info': ESTIMATE_COMPANY_INFO,
        'payment_info': ESTIMATE_PAYMENT_INFO,
        'legal_notice': ESTIMATE_LEGAL_NOTICE,
    })


@erp_estimates_bp.route('/estimates/<int:estimate_id>', methods=['PUT'])
@login_required
def update_estimate_api(estimate_id: int):
    """견적서 수정. DRAFT/ISSUED 상태에서만 가능."""
    db = get_db()
    estimate = db.query(OrderEstimate).filter(OrderEstimate.id == estimate_id).first()
    if not estimate:
        return jsonify({'success': False, 'error': '견적서를 찾을 수 없습니다.'}), 404

    if estimate.status not in ('DRAFT', 'ISSUED'):
        return jsonify({'success': False, 'error': f'현재 상태({estimate.status})에서는 수정할 수 없습니다.'}), 400

    payload = request.get_json(silent=True) or {}

    try:
        update_estimate(db, estimate, payload)
        db.commit()
        return jsonify({'success': True, 'data': estimate.to_dict()})
    except Exception:
        db.rollback()
        logger.exception("견적서 수정 실패: estimate_id=%d", estimate_id)
        return jsonify({'success': False, 'error': '견적서 수정 중 오류가 발생했습니다.'}), 500


@erp_estimates_bp.route('/estimates/<int:estimate_id>', methods=['DELETE'])
@login_required
def delete_estimate(estimate_id: int):
    """견적서 삭제. DRAFT 상태에서만 물리 삭제, 그 외는 CANCELLED 처리."""
    db = get_db()
    estimate = db.query(OrderEstimate).filter(OrderEstimate.id == estimate_id).first()
    if not estimate:
        return jsonify({'success': False, 'error': '견적서를 찾을 수 없습니다.'}), 404

    try:
        if estimate.status == 'DRAFT':
            db.delete(estimate)
        else:
            estimate.status = 'CANCELLED'
        db.commit()
        return jsonify({'success': True, 'message': '견적서가 삭제되었습니다.'})
    except Exception:
        db.rollback()
        logger.exception("견적서 삭제 실패: estimate_id=%d", estimate_id)
        return jsonify({'success': False, 'error': '견적서 삭제 중 오류가 발생했습니다.'}), 500

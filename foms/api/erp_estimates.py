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
from foms.web.auth import login_required
from foms.services.orders.estimate_defaults import (
    ESTIMATE_LEGAL_NOTICE,
    resolve_estimate_company_info,
    resolve_estimate_payment_info,
)
from foms.services.estimate_service import (
    create_estimate,
    update_estimate,
    extract_estimate_data_from_order,
    is_factory2_order,
)

logger = logging.getLogger(__name__)

erp_estimates_bp = Blueprint('erp_estimates', __name__, url_prefix='/api')


def _is_factory2(order: Order) -> bool:
    """주문 structured_data.flags.factory2 여부."""
    return is_factory2_order(order.structured_data or {})


def _company_info_for_order(order: Order) -> dict:
    """주문 structured_data.flags.factory2에 따라 공급자 정보를 선택한다."""
    return resolve_estimate_company_info(_is_factory2(order))


def _payment_info_for_order(order: Order) -> dict:
    """주문 structured_data.flags.factory2에 따라 결제정보를 선택한다."""
    return resolve_estimate_payment_info(_is_factory2(order))


def _estimate_info_variants() -> dict:
    """견적 프리뷰 UI에서 2공장 체크 토글 시 클라이언트가 즉시 전환할 수 있도록 변형 목록."""
    return {
        'company_info': {
            'default': resolve_estimate_company_info(False),
            'factory2': resolve_estimate_company_info(True),
        },
        'payment_info': {
            'default': resolve_estimate_payment_info(False),
            'factory2': resolve_estimate_payment_info(True),
        },
    }


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

    variants = _estimate_info_variants()
    data['company_info'] = _company_info_for_order(order)
    data['payment_info'] = _payment_info_for_order(order)
    data['company_info_variants'] = variants['company_info']
    data['payment_info_variants'] = variants['payment_info']
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

    variants = _estimate_info_variants()
    return jsonify({
        'success': True,
        'data': [e.to_dict() for e in estimates],
        'company_info': _company_info_for_order(order),
        'payment_info': _payment_info_for_order(order),
        'company_info_variants': variants['company_info'],
        'payment_info_variants': variants['payment_info'],
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

    order = db.query(Order).filter(Order.id == estimate.order_id).first()
    stored_payment = estimate.payment_info if isinstance(estimate.payment_info, dict) else None
    payment_info = stored_payment or (_payment_info_for_order(order) if order else resolve_estimate_payment_info(False))
    variants = _estimate_info_variants()

    return jsonify({
        'success': True,
        'data': estimate.to_dict(),
        'company_info': _company_info_for_order(order) if order else resolve_estimate_company_info(False),
        'payment_info': payment_info,
        'company_info_variants': variants['company_info'],
        'payment_info_variants': variants['payment_info'],
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

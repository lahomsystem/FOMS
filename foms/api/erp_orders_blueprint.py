"""
도면 이미지 API (주문별 blueprint 업로드/조회/삭제).
"""

import logging
from foms.services.error_logging import log_handled_exception
import os

from flask import Blueprint, request, jsonify

from db import get_db

logger = logging.getLogger(__name__)
from models import Order
from foms.web.auth import login_required
from foms.api.files import build_file_view_url
from foms.services.storage import get_storage


erp_orders_blueprint_bp = Blueprint('erp_orders_blueprint', __name__, url_prefix='/api')


@erp_orders_blueprint_bp.route('/orders/<int:order_id>/blueprint', methods=['POST'])
@login_required
def api_upload_blueprint(order_id):
    """도면 이미지 업로드"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '파일이 없습니다.'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '파일명이 없습니다.'}), 400

        allowed_image_exts = ['png', 'jpg', 'jpeg', 'gif', 'webp']
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_image_exts:
            return jsonify({'success': False, 'message': '이미지 파일만 업로드 가능합니다. (png, jpg, jpeg, gif, webp)'}), 400

        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        max_size = 50 * 1024 * 1024  # 50MB
        if file_size > max_size:
            return jsonify({'success': False, 'message': '파일 크기가 너무 큽니다. 최대 50MB까지 업로드 가능합니다.'}), 400

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        storage = get_storage()
        folder = f"orders/{order_id}/blueprint"
        result = storage.upload_file(file, file.filename, folder)

        if not result.get('success'):
            return jsonify({'success': False, 'message': '파일 업로드 실패: ' + result.get('message', '알 수 없는 오류')}), 500

        order.blueprint_image_url = build_file_view_url(result.get('key'))
        db.commit()

        return jsonify({
            'success': True,
            'url': result.get('url'),
            'message': '도면이 업로드되었습니다.'
        })
    except Exception as e:
        log_handled_exception()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_blueprint_bp.route('/orders/<int:order_id>/blueprint', methods=['GET'])
@login_required
def api_get_blueprint(order_id):
    """도면 이미지 조회"""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        return jsonify({
            'success': True,
            'url': order.blueprint_image_url if order.blueprint_image_url else None
        })
    except Exception as e:
        log_handled_exception()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_blueprint_bp.route('/orders/<int:order_id>/blueprint', methods=['DELETE'])
@login_required
def api_delete_blueprint(order_id):
    """도면 이미지 삭제"""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        order.blueprint_image_url = None
        db.commit()
        return jsonify({'success': True, 'message': '도면이 삭제되었습니다.'})
    except Exception as e:
        log_handled_exception()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_blueprint_bp.route('/orders/<int:order_id>/blueprint/complete', methods=['POST'])
@login_required
def api_blueprint_complete(order_id):
    """Phase D: Direct R2 업로드 완료 후 order.blueprint_image_url 갱신."""
    db = None
    try:
        data = request.get_json(silent=True) or {}
        key = data.get('key')
        filename = data.get('filename')
        if not key or not filename:
            return jsonify({'success': False, 'message': 'key, filename 필수가 필요합니다.'}), 400

        expected_prefix = f"orders/{order_id}/blueprint"
        if expected_prefix not in key or '..' in key:
            return jsonify({'success': False, 'message': '유효하지 않은 key 경로입니다.'}), 400

        allowed_exts = ['png', 'jpg', 'jpeg', 'gif', 'webp']
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        if ext not in allowed_exts:
            return jsonify({'success': False, 'message': '이미지 파일만 업로드 가능합니다. (png, jpg, jpeg, gif, webp)'}), 400

        storage = get_storage()
        if not storage.object_exists(key):
            return jsonify({'success': False, 'message': '업로드된 파일을 찾을 수 없습니다. 먼저 PUT으로 업로드하세요.'}), 404

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        order.blueprint_image_url = build_file_view_url(key)
        db.commit()

        return jsonify({
            'success': True,
            'url': order.blueprint_image_url,
            'message': '도면이 업로드되었습니다.'
        })
    except Exception as e:
        if db is not None:
            try:
                db.rollback()
            except Exception as rb_err:
                logger.warning("Blueprint complete: rollback failed: %s", rb_err, exc_info=True)
        logger.warning("Blueprint complete 오류: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

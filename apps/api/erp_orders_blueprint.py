"""
도면 이미지 API (주문별 blueprint 업로드/조회/삭제).
"""

import os
from flask import Blueprint, request, jsonify

from db import get_db
from models import Order
from apps.auth import login_required
from apps.api.files import build_file_view_url
from services.storage import get_storage


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
        import traceback
        print(f"도면 업로드 오류: {e}")
        print(traceback.format_exc())
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
        import traceback
        print(f"도면 조회 오류: {e}")
        print(traceback.format_exc())
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
        import traceback
        print(f"도면 삭제 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

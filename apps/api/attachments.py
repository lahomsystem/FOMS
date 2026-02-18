"""
주문 첨부 API (ERP Beta 사진/동영상/도면).
"""

import os
from flask import Blueprint, request, jsonify
from sqlalchemy import text

from db import get_db
from models import Order, OrderAttachment
from apps.auth import login_required
from apps.api.files import build_file_view_url, build_file_download_url
from services.storage import get_storage
from constants import ERP_MEDIA_ALLOWED_EXTENSIONS

DRAWING_ATTACHMENT_EXTRA_EXTENSIONS = {'pdf', 'zip', 'dwg', 'dxf'}
ATTACHMENT_CATEGORIES = ('measurement', 'drawing', 'construction')


def normalize_attachment_category(raw_category):
    """첨부 카테고리 정규화."""
    category = (raw_category or 'measurement').strip().lower()
    if category not in ATTACHMENT_CATEGORIES:
        return None
    return category


def parse_attachment_item_index(raw_item_index):
    """제품별 첨부를 위한 item_index 파싱."""
    if raw_item_index is None:
        return True, None, None
    s = str(raw_item_index).strip().lower()
    if s in ('', 'null', 'none'):
        return True, None, None
    try:
        value = int(s)
    except (TypeError, ValueError):
        return False, None, 'item_index는 0 이상의 정수 또는 null 이어야 합니다.'
    if value < 0:
        return False, None, 'item_index는 0 이상의 정수 또는 null 이어야 합니다.'
    return True, value, None


def allowed_erp_attachment_file(filename, category='measurement'):
    """ERP Beta 첨부 확장자 검증 (카테고리별 정책)."""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    allowed_exts = set(ERP_MEDIA_ALLOWED_EXTENSIONS)
    if normalize_attachment_category(category) == 'drawing':
        allowed_exts.update(DRAWING_ATTACHMENT_EXTRA_EXTENSIONS)
    return ext in allowed_exts


def get_erp_media_max_size(filename):
    """ERP Beta 첨부 파일 타입별 최대 크기 (바이트)."""
    if '.' not in filename:
        return 10 * 1024 * 1024
    ext = filename.rsplit('.', 1)[1].lower()
    image_exts = ['jpg', 'jpeg', 'png', 'gif', 'webp']
    video_exts = ['mp4', 'mov', 'avi', 'mkv', 'webm']
    if ext in image_exts:
        return 20 * 1024 * 1024  # 20MB
    if ext in video_exts:
        return 500 * 1024 * 1024  # 500MB
    return 20 * 1024 * 1024


def ensure_order_attachments_category_column():
    """레거시 DB용: order_attachments.category 컬럼 존재 보장."""
    db = None
    try:
        db = get_db()
        db.execute(text(
            "ALTER TABLE order_attachments "
            "ADD COLUMN IF NOT EXISTS category VARCHAR(50) NOT NULL DEFAULT 'measurement'"
        ))
        db.commit()
        return True
    except Exception as e:
        try:
            if db is not None:
                db.rollback()
        except Exception:
            pass
        print(f"[AUTO-MIGRATION] Failed to ensure order_attachments.category: {e}")
        return False


def ensure_order_attachments_item_index_column():
    """레거시 DB용: order_attachments.item_index 컬럼 존재 보장."""
    db = None
    try:
        db = get_db()
        db.execute(text(
            "ALTER TABLE order_attachments "
            "ADD COLUMN IF NOT EXISTS item_index INTEGER NULL"
        ))
        db.commit()
        return True
    except Exception as e:
        try:
            if db is not None:
                db.rollback()
        except Exception:
            pass
        print(f"[AUTO-MIGRATION] Failed to ensure order_attachments.item_index: {e}")
        return False


attachments_bp = Blueprint('attachments', __name__, url_prefix='/api')


@attachments_bp.route('/orders/<int:order_id>/attachments', methods=['GET'])
@login_required
def api_order_attachments_list(order_id):
    """주문 첨부 목록(ERP Beta 사진/동영상)."""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        raw_filter_category = request.args.get('category')
        filter_category = normalize_attachment_category(raw_filter_category) if raw_filter_category else None
        if raw_filter_category and not filter_category:
            return jsonify({'success': False, 'message': '유효하지 않은 첨부 카테고리입니다.'}), 400
        raw_filter_item_index = request.args.get('item_index')
        filter_item_index = None
        has_item_filter = raw_filter_item_index is not None
        if has_item_filter:
            ok, filter_item_index, err = parse_attachment_item_index(raw_filter_item_index)
            if not ok:
                return jsonify({'success': False, 'message': err}), 400

        query = db.query(OrderAttachment).filter(OrderAttachment.order_id == order_id)
        if filter_category:
            query = query.filter(OrderAttachment.category == filter_category)
        if has_item_filter:
            if filter_item_index is None:
                query = query.filter(OrderAttachment.item_index.is_(None))
            else:
                query = query.filter(OrderAttachment.item_index == filter_item_index)

        atts = query.order_by(OrderAttachment.created_at.desc()).all()
        items = []
        for a in atts:
            d = a.to_dict()
            d['category'] = normalize_attachment_category(d.get('category')) or 'measurement'
            d['view_url'] = build_file_view_url(a.storage_key)
            d['download_url'] = build_file_download_url(a.storage_key)
            d['thumbnail_view_url'] = build_file_view_url(a.thumbnail_key) if a.thumbnail_key else None
            items.append(d)

        return jsonify({'success': True, 'attachments': items})
    except Exception as e:
        import traceback
        print(f"주문 첨부 목록 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@attachments_bp.route('/orders/<int:order_id>/attachments', methods=['POST'])
@login_required
def api_order_attachments_upload(order_id):
    """주문 첨부 업로드(ERP Beta 사진/동영상)."""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '파일이 없습니다.'}), 400
        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({'success': False, 'message': '파일명이 없습니다.'}), 400

        category = normalize_attachment_category(request.form.get('category', 'measurement'))
        if not category:
            return jsonify({'success': False, 'message': '유효하지 않은 첨부 카테고리입니다.'}), 400
        ok, item_index, err = parse_attachment_item_index(request.form.get('item_index'))
        if not ok:
            return jsonify({'success': False, 'message': err}), 400

        if not allowed_erp_attachment_file(file.filename, category):
            allowed_exts = set(ERP_MEDIA_ALLOWED_EXTENSIONS)
            if category == 'drawing':
                allowed_exts.update(DRAWING_ATTACHMENT_EXTRA_EXTENSIONS)
            allowed_exts = ', '.join(sorted(allowed_exts))
            return jsonify({'success': False, 'message': f'허용되지 않은 파일 형식입니다. 지원 형식: {allowed_exts}'}), 400

        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        max_size = get_erp_media_max_size(file.filename)
        if file_size > max_size:
            size_mb = max_size / (1024 * 1024)
            return jsonify({'success': False, 'message': f'파일 크기가 너무 큽니다. 최대 {size_mb:.0f}MB까지 업로드 가능합니다.'}), 400

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        storage = get_storage()
        folder = f"orders/{order_id}/attachments"

        result = storage.upload_file(file, file.filename, folder)
        if not result.get('success'):
            return jsonify({'success': False, 'message': '파일 업로드 실패: ' + result.get('message', '알 수 없는 오류')}), 500

        storage_key = result.get('key')
        filename = file.filename
        file_type = storage._get_file_type(filename)
        if category == 'drawing':
            if file_type not in ['image', 'video', 'file']:
                return jsonify({'success': False, 'message': '지원되지 않는 도면 파일 형식입니다.'}), 400
        else:
            if file_type not in ['image', 'video']:
                return jsonify({'success': False, 'message': '이미지/동영상만 업로드 가능합니다.'}), 400

        thumbnail_key = None
        try:
            if file_type == 'image' and hasattr(storage, '_generate_thumbnail'):
                unique_filename = storage_key.rsplit('/', 1)[-1] if storage_key else None
                if unique_filename:
                    file.seek(0)
                    storage._generate_thumbnail(file, unique_filename, folder, 'image', storage_key=storage_key)
                    thumbnail_key = f"{folder}/thumb_{unique_filename}"
        except Exception:
            thumbnail_key = None

        att = OrderAttachment(
            order_id=order_id,
            filename=filename,
            file_type=file_type,
            category=category,
            item_index=item_index,
            file_size=file_size,
            storage_key=storage_key,
            thumbnail_key=thumbnail_key
        )
        db.add(att)
        db.commit()
        db.refresh(att)

        d = att.to_dict()
        d['view_url'] = build_file_view_url(att.storage_key)
        d['download_url'] = build_file_download_url(att.storage_key)
        d['thumbnail_view_url'] = build_file_view_url(att.thumbnail_key) if att.thumbnail_key else None

        return jsonify({'success': True, 'attachment': d})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            pass
        import traceback
        print(f"주문 첨부 업로드 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@attachments_bp.route('/orders/<int:order_id>/attachments/<int:attachment_id>', methods=['PATCH'])
@login_required
def api_order_attachments_patch(order_id, attachment_id):
    """주문 첨부 메타 수정(제품 항목 연결/해제)."""
    try:
        payload = request.get_json(silent=True) or {}
        if 'item_index' not in payload:
            return jsonify({'success': False, 'message': 'item_index 필드가 필요합니다.'}), 400
        ok, item_index, err = parse_attachment_item_index(payload.get('item_index'))
        if not ok:
            return jsonify({'success': False, 'message': err}), 400

        db = get_db()
        att = db.query(OrderAttachment).filter(
            OrderAttachment.id == attachment_id,
            OrderAttachment.order_id == order_id
        ).first()
        if not att:
            return jsonify({'success': False, 'message': '첨부파일을 찾을 수 없습니다.'}), 404

        att.item_index = item_index
        db.commit()
        db.refresh(att)

        d = att.to_dict()
        d['category'] = normalize_attachment_category(d.get('category')) or 'measurement'
        d['view_url'] = build_file_view_url(att.storage_key)
        d['download_url'] = build_file_download_url(att.storage_key)
        d['thumbnail_view_url'] = build_file_view_url(att.thumbnail_key) if att.thumbnail_key else None
        return jsonify({'success': True, 'attachment': d})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            pass
        import traceback
        print(f"주문 첨부 수정 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@attachments_bp.route('/orders/<int:order_id>/attachments/<int:attachment_id>', methods=['DELETE'])
@login_required
def api_order_attachments_delete(order_id, attachment_id):
    """주문 첨부 삭제(ERP Beta)."""
    try:
        db = get_db()
        att = db.query(OrderAttachment).filter(
            OrderAttachment.id == attachment_id,
            OrderAttachment.order_id == order_id
        ).first()
        if not att:
            return jsonify({'success': False, 'message': '첨부파일을 찾을 수 없습니다.'}), 404

        storage = get_storage()
        try:
            if att.storage_key:
                storage.delete_file(att.storage_key)
            if att.thumbnail_key:
                storage.delete_file(att.thumbnail_key)
        except Exception:
            pass

        db.delete(att)
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            pass
        import traceback
        print(f"주문 첨부 삭제 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

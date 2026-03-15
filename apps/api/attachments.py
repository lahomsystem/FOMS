"""
주문 첨부 API (ERP Beta 사진/동영상/도면).
"""

import os
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, request, jsonify, session
from sqlalchemy import text

from db import get_db
from models import Order, OrderAttachment
from apps.auth import login_required, get_user_by_id
from apps.api.files import build_file_view_url, build_file_download_url
from services.storage import get_storage
from services.order_attachment_thumbnail import schedule_order_attachment_thumbnail_generation
from constants import ERP_MEDIA_ALLOWED_EXTENSIONS, DIRECT_UPLOAD_ALLOWED_CONTENT_TYPES

DRAWING_ATTACHMENT_EXTRA_EXTENSIONS = {'pdf', 'zip', 'dwg', 'dxf'}
ATTACHMENT_CATEGORIES = ('measurement', 'drawing', 'construction', 'as')
ASYNC_ATTACHMENT_THUMBNAIL = os.environ.get('ASYNC_ATTACHMENT_THUMBNAIL', '1').lower() in ('1', 'true', 'yes', 'on')


def _att_key(att: OrderAttachment, key: str) -> str | None:
    """ORM 인스턴스에서 storage_key/thumbnail_key 값을 꺼내 타입 체커 만족용."""
    v = getattr(att, key, None)
    return str(v) if v is not None and v else None


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


def ensure_order_attachments_user_id_column():
    """레거시 DB용: order_attachments.user_id 컬럼 존재 보장 (업로더 식별, AS 재업로드 시 본인 것만 삭제)."""
    db = None
    try:
        db = get_db()
        db.execute(text(
            "ALTER TABLE order_attachments "
            "ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
        ))
        db.commit()
        return True
    except Exception as e:
        try:
            if db is not None:
                db.rollback()
        except Exception:
            pass
        print(f"[AUTO-MIGRATION] Failed to ensure order_attachments.user_id: {e}")
        return False


attachments_bp = Blueprint('attachments', __name__, url_prefix='/api')

USE_DIRECT_UPLOAD = os.environ.get('USE_DIRECT_UPLOAD', '1').lower() in ('1', 'true', 'yes', 'on')


@attachments_bp.route('/upload/session', methods=['POST'])
@login_required
def api_upload_session():
    """Phase D: Direct R2 업로드용 세션 발급 (presigned PUT URL).
    R2/S3 환경에서만 동작. 로컬 스토리지는 400 반환.
    """
    try:
        data = request.get_json(silent=True) or {}
        filename = data.get('filename')
        size = data.get('size', 0)
        folder = data.get('folder', '')
        category_param = data.get('category')

        if not filename or not isinstance(size, (int, float)) or size <= 0 or not folder:
            return jsonify({'success': False, 'message': 'filename, size, folder 필수가 필요합니다.'}), 400

        if '..' in folder or folder.startswith('/'):
            return jsonify({'success': False, 'message': '유효하지 않은 folder 경로입니다.'}), 400

        storage = get_storage()
        key = storage.generate_direct_upload_key(filename, folder)
        ct = storage._get_content_type(filename)
        if ct not in DIRECT_UPLOAD_ALLOWED_CONTENT_TYPES:
            return jsonify({'success': False, 'message': '허용되지 않은 파일 형식입니다.'}), 400
        upload_url = storage.generate_presigned_put_url(key, ct, expires_in=900)
        if upload_url is None:
            return jsonify({'success': False, 'message': 'Direct upload는 R2/S3 환경에서만 사용 가능합니다.'}), 400
        if not upload_url:
            return jsonify({'success': False, 'message': 'Presigned URL 생성 실패'}), 500

        max_size = get_erp_media_max_size(filename)
        if size > max_size:
            size_mb = max_size / (1024 * 1024)
            return jsonify({'success': False, 'message': f'파일 크기가 너무 큽니다. 최대 {size_mb:.0f}MB'}), 400

        if category_param is not None:
            category = normalize_attachment_category(category_param) or 'measurement'
        else:
            parts = folder.split('/')
            if len(parts) >= 2 and parts[0] == 'orders' and parts[1].isdigit():
                seg = parts[2] if len(parts) > 2 else 'measurement'
                if seg == 'drawing_gateway':
                    category = 'drawing'
                elif seg == 'blueprint':
                    category = 'measurement'
                else:
                    category = normalize_attachment_category(seg) or 'measurement'
            else:
                category = 'measurement'
        if not allowed_erp_attachment_file(filename, category):
            return jsonify({'success': False, 'message': '허용되지 않은 파일 형식입니다.'}), 400

        from datetime import datetime, timezone
        expires_at = datetime.now(timezone.utc)
        from datetime import timedelta
        expires_at = expires_at + timedelta(seconds=900)

        return jsonify({
            'success': True,
            'upload_url': upload_url,
            'key': key,
            'expires_at': expires_at.isoformat().replace('+00:00', 'Z')
        })
    except Exception as e:
        import traceback
        print(f"업로드 세션 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

@attachments_bp.route('/upload/session/batch', methods=['POST'])
@login_required
def api_upload_session_batch():
    """Phase D: Direct R2 다중 업로드용 세션 발급 (여러 파일의 presigned PUT URL 일괄 발급)."""
    try:
        data = request.get_json(silent=True) or {}
        files = data.get('files', [])
        folder = data.get('folder', '')
        category_param = data.get('category')

        if not files or not isinstance(files, list):
            return jsonify({'success': False, 'message': 'files 리스트가 필요합니다.'}), 400

        if not folder or '..' in folder or folder.startswith('/'):
            return jsonify({'success': False, 'message': '유효하지 않은 folder 경로입니다.'}), 400

        if category_param is not None:
            category = normalize_attachment_category(category_param) or 'measurement'
        else:
            parts = folder.split('/')
            if len(parts) >= 2 and parts[0] == 'orders' and parts[1].isdigit():
                seg = parts[2] if len(parts) > 2 else 'measurement'
                if seg == 'drawing_gateway':
                    category = 'drawing'
                elif seg == 'blueprint':
                    category = 'measurement'
                else:
                    category = normalize_attachment_category(seg) or 'measurement'
            else:
                category = 'measurement'

        storage = get_storage()
        sessions = []
        
        from datetime import datetime, timezone, timedelta
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=900)
        expires_at_str = expires_at.isoformat().replace('+00:00', 'Z')

        for f_data in files:
            filename = f_data.get('filename')
            size = f_data.get('size', 0)
            
            if not filename or not isinstance(size, (int, float)) or size <= 0:
                continue

            max_size = get_erp_media_max_size(filename)
            if size > max_size:
                continue

            if not allowed_erp_attachment_file(filename, category):
                continue
                
            key = storage.generate_direct_upload_key(filename, folder)
            ct = storage._get_content_type(filename)
            if ct not in DIRECT_UPLOAD_ALLOWED_CONTENT_TYPES:
                continue

            upload_url = storage.generate_presigned_put_url(key, ct, expires_in=900)
            if not upload_url:
                continue
                
            sessions.append({
                'filename': filename,
                'upload_url': upload_url,
                'key': key,
                'expires_at': expires_at_str
            })

        return jsonify({'success': True, 'sessions': sessions})
    except Exception as e:
        import traceback
        print(f"업로드 다중 세션 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@attachments_bp.route('/orders/<int:order_id>/attachments/complete', methods=['POST'])
@login_required
def api_order_attachments_complete(order_id):
    """Phase D: Direct R2 업로드 완료 후 DB 등록."""
    try:
        data = request.get_json(silent=True) or {}
        key = data.get('key')
        filename = data.get('filename')
        category = normalize_attachment_category(data.get('category', 'measurement')) or 'measurement'
        ok, item_index, err = parse_attachment_item_index(data.get('item_index'))
        if not ok:
            return jsonify({'success': False, 'message': err}), 400

        if not key or not filename:
            return jsonify({'success': False, 'message': 'key, filename 필수가 필요합니다.'}), 400

        if f'orders/{order_id}/' not in key or '..' in key:
            return jsonify({'success': False, 'message': '유효하지 않은 key 경로입니다.'}), 400

        storage = get_storage()
        if not storage.object_exists(key):
            return jsonify({'success': False, 'message': '업로드된 파일을 찾을 수 없습니다. 먼저 PUT으로 업로드하세요.'}), 404

        if not allowed_erp_attachment_file(filename, category):
            return jsonify({'success': False, 'message': '허용되지 않은 파일 형식입니다.'}), 400

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        file_type = storage.get_file_type(filename)
        file_size = 0
        used_client_size = False
        client_size = data.get('size')
        max_size = get_erp_media_max_size(filename)
        if client_size is not None:
            try:
                sz = int(client_size)
                if 0 <= sz <= max_size:
                    file_size = sz
                    used_client_size = True
            except (TypeError, ValueError):
                pass
        if not used_client_size and storage.storage_type in ['r2', 's3']:
            try:
                resp = storage.client.head_object(Bucket=storage.bucket_name, Key=key)
                file_size = resp.get('ContentLength', 0)
            except Exception:
                pass

        thumbnail_key = None
        att = OrderAttachment(
            order_id=order_id,
            filename=filename,
            file_type=file_type,
            category=category,
            item_index=item_index,
            file_size=file_size,
            storage_key=key,
            thumbnail_key=thumbnail_key,
            user_id=session.get('user_id'),
        )
        db.add(att)
        db.commit()
        db.refresh(att)
        sk = _att_key(att, 'storage_key')
        tk = _att_key(att, 'thumbnail_key')
        if ASYNC_ATTACHMENT_THUMBNAIL and file_type == 'image' and sk and not tk:
            schedule_order_attachment_thumbnail_generation(att.id, sk)

        d = att.to_dict()
        d['view_url'] = build_file_view_url(sk) if sk else ''
        d['download_url'] = build_file_download_url(sk) if sk else ''
        d['thumbnail_view_url'] = build_file_view_url(tk) if tk else None
        return jsonify({'success': True, 'attachment': d})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            pass
        import traceback
        print(f"Direct upload 완료 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


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
            sk = _att_key(a, 'storage_key')
            tk = _att_key(a, 'thumbnail_key')
            d['view_url'] = build_file_view_url(sk) if sk else ''
            d['download_url'] = build_file_download_url(sk) if sk else ''
            d['thumbnail_view_url'] = build_file_view_url(tk) if tk else None
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
        file_type = storage.get_file_type(filename)
        if category == 'drawing':
            if file_type not in ['image', 'video', 'file']:
                return jsonify({'success': False, 'message': '지원되지 않는 도면 파일 형식입니다.'}), 400
        else:
            if file_type not in ['image', 'video']:
                return jsonify({'success': False, 'message': '이미지/동영상만 업로드 가능합니다.'}), 400

        thumbnail_key = None
        try:
            if file_type == 'image' and hasattr(storage, '_generate_thumbnail'):
                if not ASYNC_ATTACHMENT_THUMBNAIL:
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
            thumbnail_key=thumbnail_key,
            user_id=session.get('user_id'),
        )
        db.add(att)
        db.commit()
        db.refresh(att)
        sk = _att_key(att, 'storage_key')
        tk = _att_key(att, 'thumbnail_key')
        if ASYNC_ATTACHMENT_THUMBNAIL and file_type == 'image' and sk and not tk:
            schedule_order_attachment_thumbnail_generation(att.id, sk)

        d = att.to_dict()
        d['view_url'] = build_file_view_url(sk) if sk else ''
        d['download_url'] = build_file_download_url(sk) if sk else ''
        d['thumbnail_view_url'] = build_file_view_url(tk) if tk else None

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

        setattr(att, 'item_index', item_index)
        db.commit()
        db.refresh(att)

        d = att.to_dict()
        d['category'] = normalize_attachment_category(d.get('category')) or 'measurement'
        sk = _att_key(att, 'storage_key')
        tk = _att_key(att, 'thumbnail_key')
        d['view_url'] = build_file_view_url(sk) if sk else ''
        d['download_url'] = build_file_download_url(sk) if sk else ''
        d['thumbnail_view_url'] = build_file_view_url(tk) if tk else None
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
    """주문 첨부 삭제(ERP Beta). 관리자(ADMIN)는 모든 첨부 삭제 가능, 그 외는 본인 업로드만 삭제 가능(AS 재업로드 보호)."""
    try:
        db = get_db()
        att = db.query(OrderAttachment).filter(
            OrderAttachment.id == attachment_id,
            OrderAttachment.order_id == order_id
        ).first()
        if not att:
            return jsonify({'success': False, 'message': '첨부파일을 찾을 수 없습니다.'}), 404

        att_user_id = getattr(att, 'user_id', None)
        current_user_id = session.get('user_id')
        current_user = get_user_by_id(current_user_id) if current_user_id else None
        is_admin = current_user and getattr(current_user, 'role', None) == 'ADMIN'
        if not is_admin and att_user_id is not None and current_user_id is not None and att_user_id != current_user_id:
            return jsonify({'success': False, 'message': '다른 사용자가 업로드한 파일은 삭제할 수 없습니다.'}), 403

        storage = get_storage()
        sk = _att_key(att, 'storage_key')
        tk = _att_key(att, 'thumbnail_key')
        try:
            keys_to_delete = [k for k in (sk, tk) if k]
            if keys_to_delete:
                with ThreadPoolExecutor(max_workers=2) as ex:
                    list(ex.map(storage.delete_file, keys_to_delete))
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

"""Direct-upload endpoints for order attachments."""

from flask import jsonify, request, session

from foms.web.auth import get_user_by_id, login_required
from foms.api.files.blueprint import (
    ASYNC_ATTACHMENT_THUMBNAIL,
    attachments_bp,
)
from foms.api.files.common import (
    allowed_erp_attachment_file,
    get_erp_media_max_size,
    parse_attachment_item_index,
    resolve_attachment_category,
    serialize_attachment,
)
from foms.api.files.routes import build_file_view_url
from foms.services.files.upload_policy import DIRECT_UPLOAD_ALLOWED_CONTENT_TYPES
from db import get_db
from foms.services.order_attachment_thumbnail import (
    schedule_order_attachment_thumbnail_generation,
)
from foms.services.storage import get_storage
from models import Order, OrderAttachment


@attachments_bp.route("/upload/session", methods=["POST"])
@login_required
def api_upload_session():
    """Phase D: Direct R2 업로드용 세션 발급."""
    try:
        data = request.get_json(silent=True) or {}
        filename = data.get("filename")
        size = data.get("size", 0)
        folder = data.get("folder", "")
        category = resolve_attachment_category(str(folder or ""), data.get("category"))

        if not filename or not isinstance(size, (int, float)) or size <= 0 or not folder:
            return jsonify({"success": False, "message": "filename, size, folder 필수가 필요합니다."}), 400
        if not isinstance(folder, str):
            folder = str(folder)
        if not isinstance(filename, str):
            filename = str(filename)
        if ".." in folder or folder.startswith("/"):
            return jsonify({"success": False, "message": "유효하지 않은 folder 경로입니다."}), 400

        storage = get_storage()
        key = storage.generate_direct_upload_key(filename, folder)
        ct = storage._get_content_type(filename)
        if ct not in DIRECT_UPLOAD_ALLOWED_CONTENT_TYPES:
            return jsonify({"success": False, "message": "허용되지 않은 파일 형식입니다."}), 400
        upload_url = storage.generate_presigned_put_url(key, ct, expires_in=900)
        if upload_url is None:
            return jsonify({"success": False, "message": "Direct upload는 R2/S3 환경에서만 사용 가능합니다."}), 400
        if not upload_url:
            return jsonify({"success": False, "message": "Presigned URL 생성 실패"}), 500

        max_size = get_erp_media_max_size(filename)
        if size > max_size:
            size_mb = max_size / (1024 * 1024)
            return jsonify({"success": False, "message": f"파일 크기가 너무 큽니다. 최대 {size_mb:.0f}MB"}), 400

        if not allowed_erp_attachment_file(filename, category):
            return jsonify({"success": False, "message": "허용되지 않은 파일 형식입니다."}), 400

        from datetime import datetime, timedelta, timezone

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=900)
        return jsonify(
            {
                "success": True,
                "upload_url": upload_url,
                "key": key,
                "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            }
        )
    except Exception as e:
        import traceback

        print(f"업로드 세션 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@attachments_bp.route("/upload/session/batch", methods=["POST"])
@login_required
def api_upload_session_batch():
    """Phase D: Direct R2 다중 업로드용 세션 발급."""
    try:
        data = request.get_json(silent=True) or {}
        files = data.get("files", [])
        folder = data.get("folder", "")
        if not files or not isinstance(files, list):
            return jsonify({"success": False, "message": "files 리스트가 필요합니다."}), 400

        if not isinstance(folder, str):
            folder = str(folder)
        if not folder or ".." in folder or folder.startswith("/"):
            return jsonify({"success": False, "message": "유효하지 않은 folder 경로입니다."}), 400

        category = resolve_attachment_category(folder, data.get("category"))
        storage = get_storage()
        sessions = []

        from datetime import datetime, timedelta, timezone

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=900)
        expires_at_str = expires_at.isoformat().replace("+00:00", "Z")

        for file_data in files:
            filename = file_data.get("filename")
            size = file_data.get("size", 0)
            raw_client_id = file_data.get("client_id")
            client_id = raw_client_id if isinstance(raw_client_id, str) and len(raw_client_id) <= 128 else None

            if not filename or not isinstance(size, (int, float)) or size <= 0:
                continue
            if size > get_erp_media_max_size(filename):
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

            session_payload = {
                "filename": filename,
                "upload_url": upload_url,
                "key": key,
                "expires_at": expires_at_str,
            }
            if client_id:
                session_payload["client_id"] = client_id
            sessions.append(session_payload)

        return jsonify({"success": True, "sessions": sessions})
    except Exception as e:
        import traceback

        print(f"업로드 다중 세션 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@attachments_bp.route("/orders/<int:order_id>/attachments/complete", methods=["POST"])
@login_required
def api_order_attachments_complete(order_id):
    """Phase D: Direct R2 업로드 완료 후 DB 등록."""
    try:
        data = request.get_json(silent=True) or {}
        key = data.get("key")
        filename = data.get("filename")
        category = resolve_attachment_category("", data.get("category", "measurement"))
        ok, item_index, err = parse_attachment_item_index(data.get("item_index"))
        if not ok:
            return jsonify({"success": False, "message": err}), 400

        if not key or not filename:
            return jsonify({"success": False, "message": "key, filename 필수가 필요합니다."}), 400
        if not isinstance(key, str):
            key = str(key)
        if not isinstance(filename, str):
            filename = str(filename)
        if f"orders/{order_id}/" not in key or ".." in key:
            return jsonify({"success": False, "message": "유효하지 않은 key 경로입니다."}), 400

        storage = get_storage()
        if not storage.object_exists(key):
            return (
                jsonify({"success": False, "message": "업로드된 파일을 찾을 수 없습니다. 먼저 PUT으로 업로드하세요."}),
                404,
            )
        if not allowed_erp_attachment_file(filename, category):
            return jsonify({"success": False, "message": "허용되지 않은 파일 형식입니다."}), 400

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        file_type = storage.get_file_type(filename)
        file_size = 0
        used_client_size = False
        client_size = data.get("size")
        max_size = get_erp_media_max_size(filename)
        if client_size is not None:
            try:
                size_value = int(client_size)
                if 0 <= size_value <= max_size:
                    file_size = size_value
                    used_client_size = True
            except (TypeError, ValueError):
                pass
        if not used_client_size and storage.storage_type in ["r2", "s3"]:
            try:
                resp = storage.client.head_object(Bucket=storage.bucket_name, Key=key)
                file_size = resp.get("ContentLength", 0)
            except Exception:
                pass

        attachment = OrderAttachment(
            order_id=order_id,
            filename=filename,
            file_type=file_type,
            category=category,
            item_index=item_index,
            file_size=file_size,
            storage_key=key,
            thumbnail_key=None,
            user_id=session.get("user_id"),
        )
        db.add(attachment)
        db.commit()
        from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches

        invalidate_all_dashboard_slice_caches()
        db.refresh(attachment)
        storage_key = getattr(attachment, "storage_key", None)
        thumbnail_key = getattr(attachment, "thumbnail_key", None)
        if ASYNC_ATTACHMENT_THUMBNAIL and file_type == "image" and storage_key and not thumbnail_key:
            schedule_order_attachment_thumbnail_generation(attachment.id, storage_key)

        payload = serialize_attachment(
            attachment,
            order=order,
            user=get_user_by_id(session.get("user_id")) if session.get("user_id") else None,
        )
        payload["view_url"] = build_file_view_url(storage_key) if storage_key else ""
        return jsonify({"success": True, "attachment": payload})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            pass
        import traceback

        print(f"Direct upload 완료 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


__all__ = [
    "api_order_attachments_complete",
    "api_upload_session",
    "api_upload_session_batch",
]

"""Order attachment CRUD routes."""

import os
from concurrent.futures import ThreadPoolExecutor

from flask import jsonify, request, session

from foms.web.auth import get_user_by_id, login_required
from foms.api.attachments_internal.blueprint import (
    ASYNC_ATTACHMENT_THUMBNAIL,
    attachments_bp,
)
from foms.api.attachments_internal.common import (
    DRAWING_ATTACHMENT_EXTRA_EXTENSIONS,
    allowed_erp_attachment_file,
    get_erp_media_max_size,
    normalize_attachment_category,
    parse_attachment_item_index,
    serialize_attachment,
)
from db import get_db
from foms.services.files.upload_policy import ERP_MEDIA_ALLOWED_EXTENSIONS
from foms.services.order_attachment_thumbnail import (
    schedule_order_attachment_thumbnail_generation,
)
from foms.services.storage import get_storage
from models import Order, OrderAttachment


@attachments_bp.route("/orders/<int:order_id>/attachments", methods=["GET"])
@login_required
def api_order_attachments_list(order_id):
    """주문 첨부 목록(ERP Beta 사진/동영상)."""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        raw_filter_category = request.args.get("category")
        filter_category = None
        if raw_filter_category:
            filter_category = normalize_attachment_category(raw_filter_category)
            if not filter_category:
                return jsonify({"success": False, "message": "유효하지 않은 첨부 카테고리입니다."}), 400

        raw_filter_item_index = request.args.get("item_index")
        filter_item_index = None
        has_item_filter = raw_filter_item_index is not None
        if has_item_filter:
            ok, filter_item_index, err = parse_attachment_item_index(raw_filter_item_index)
            if not ok:
                return jsonify({"success": False, "message": err}), 400

        query = db.query(OrderAttachment).filter(OrderAttachment.order_id == order_id)
        if filter_category:
            query = query.filter(OrderAttachment.category == filter_category)
        if has_item_filter:
            if filter_item_index is None:
                query = query.filter(OrderAttachment.item_index.is_(None))
            else:
                query = query.filter(OrderAttachment.item_index == filter_item_index)

        attachments = query.order_by(OrderAttachment.created_at.desc()).all()
        items = [serialize_attachment(attachment) for attachment in attachments]
        return jsonify({"success": True, "attachments": items})
    except Exception as e:
        import traceback

        print(f"주문 첨부 목록 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@attachments_bp.route("/orders/<int:order_id>/attachments", methods=["POST"])
@login_required
def api_order_attachments_upload(order_id):
    """주문 첨부 업로드(ERP Beta 사진/동영상)."""
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "message": "파일이 없습니다."}), 400
        file = request.files["file"]
        if not file or file.filename == "":
            return jsonify({"success": False, "message": "파일명이 없습니다."}), 400

        category = normalize_attachment_category(request.form.get("category", "measurement"))
        if not category:
            return jsonify({"success": False, "message": "유효하지 않은 첨부 카테고리입니다."}), 400
        ok, item_index, err = parse_attachment_item_index(request.form.get("item_index"))
        if not ok:
            return jsonify({"success": False, "message": err}), 400

        if not allowed_erp_attachment_file(file.filename, category):
            allowed_exts = set(ERP_MEDIA_ALLOWED_EXTENSIONS)
            if category == "drawing":
                allowed_exts |= DRAWING_ATTACHMENT_EXTRA_EXTENSIONS
            allowed_exts_str = ", ".join(sorted(allowed_exts))
            return jsonify({"success": False, "message": f"허용되지 않은 파일 형식입니다. 지원 형식: {allowed_exts_str}"}), 400

        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        max_size = get_erp_media_max_size(file.filename)
        if file_size > max_size:
            size_mb = max_size / (1024 * 1024)
            return jsonify({"success": False, "message": f"파일 크기가 너무 큽니다. 최대 {size_mb:.0f}MB까지 업로드 가능합니다."}), 400

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        storage = get_storage()
        folder = f"orders/{order_id}/attachments"
        result = storage.upload_file(file, file.filename, folder)
        if not result.get("success"):
            return jsonify({"success": False, "message": "파일 업로드 실패: " + result.get("message", "알 수 없는 오류")}), 500

        storage_key = result.get("key")
        filename = file.filename
        file_type = storage.get_file_type(filename)
        if category == "drawing":
            if file_type not in ["image", "video", "file"]:
                return jsonify({"success": False, "message": "지원되지 않는 도면 파일 형식입니다."}), 400
        elif file_type not in ["image", "video"]:
            return jsonify({"success": False, "message": "이미지/동영상만 업로드 가능합니다."}), 400

        thumbnail_key = None
        try:
            if file_type == "image" and hasattr(storage, "_generate_thumbnail") and not ASYNC_ATTACHMENT_THUMBNAIL:
                unique_filename = storage_key.rsplit("/", 1)[-1] if storage_key else None
                if unique_filename:
                    file.seek(0)
                    storage._generate_thumbnail(file, unique_filename, folder, "image", storage_key=storage_key)
                    thumbnail_key = f"{folder}/thumb_{unique_filename}"
        except Exception:
            thumbnail_key = None

        attachment = OrderAttachment(
            order_id=order_id,
            filename=filename,
            file_type=file_type,
            category=category,
            item_index=item_index,
            file_size=file_size,
            storage_key=storage_key,
            thumbnail_key=thumbnail_key,
            user_id=session.get("user_id"),
        )
        db.add(attachment)
        db.commit()
        db.refresh(attachment)
        if ASYNC_ATTACHMENT_THUMBNAIL and file_type == "image" and storage_key and not thumbnail_key:
            schedule_order_attachment_thumbnail_generation(attachment.id, storage_key)

        return jsonify({"success": True, "attachment": serialize_attachment(attachment)})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            pass
        import traceback

        print(f"주문 첨부 업로드 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@attachments_bp.route("/orders/<int:order_id>/attachments/<int:attachment_id>", methods=["PATCH"])
@login_required
def api_order_attachments_patch(order_id, attachment_id):
    """주문 첨부 메타 수정(제품 항목 연결/해제)."""
    try:
        payload = request.get_json(silent=True) or {}
        if "item_index" not in payload:
            return jsonify({"success": False, "message": "item_index 필드가 필요합니다."}), 400
        ok, item_index, err = parse_attachment_item_index(payload.get("item_index"))
        if not ok:
            return jsonify({"success": False, "message": err}), 400

        db = get_db()
        attachment = (
            db.query(OrderAttachment)
            .filter(OrderAttachment.id == attachment_id, OrderAttachment.order_id == order_id)
            .first()
        )
        if not attachment:
            return jsonify({"success": False, "message": "첨부파일을 찾을 수 없습니다."}), 404

        setattr(attachment, "item_index", item_index)
        db.commit()
        db.refresh(attachment)
        return jsonify({"success": True, "attachment": serialize_attachment(attachment)})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            pass
        import traceback

        print(f"주문 첨부 수정 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@attachments_bp.route("/orders/<int:order_id>/attachments/<int:attachment_id>", methods=["DELETE"])
@login_required
def api_order_attachments_delete(order_id, attachment_id):
    """주문 첨부 삭제(ERP Beta)."""
    try:
        db = get_db()
        attachment = (
            db.query(OrderAttachment)
            .filter(OrderAttachment.id == attachment_id, OrderAttachment.order_id == order_id)
            .first()
        )
        if not attachment:
            return jsonify({"success": False, "message": "첨부파일을 찾을 수 없습니다."}), 404

        attachment_user_id = getattr(attachment, "user_id", None)
        current_user_id = session.get("user_id")
        current_user = get_user_by_id(current_user_id) if current_user_id else None
        is_admin = current_user and getattr(current_user, "role", None) == "ADMIN"
        if not is_admin and (
            current_user_id is None or attachment_user_id is None or attachment_user_id != current_user_id
        ):
            return jsonify({"success": False, "message": "본인이 업로드한 파일만 삭제할 수 있습니다."}), 403

        storage = get_storage()
        try:
            keys_to_delete = [
                key
                for key in (
                    getattr(attachment, "storage_key", None),
                    getattr(attachment, "thumbnail_key", None),
                )
                if key
            ]
            if keys_to_delete:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    list(executor.map(storage.delete_file, keys_to_delete))
        except Exception:
            pass

        db.delete(attachment)
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            pass
        import traceback

        print(f"주문 첨부 삭제 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


__all__ = [
    "api_order_attachments_delete",
    "api_order_attachments_list",
    "api_order_attachments_patch",
    "api_order_attachments_upload",
]

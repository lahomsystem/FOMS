"""Search endpoints for attachment metadata."""

from flask import jsonify, request

from apps.auth import login_required
from apps.api.attachments_internal.blueprint import attachments_bp
from apps.api.files import build_file_download_url, build_file_view_url
from db import get_db
from models import Order, OrderAttachment


@attachments_bp.route("/search", methods=["GET"])
@login_required
def api_search_attachments():
    """Phase M: 전체 첨부/멀티미디어 메타데이터 검색 API."""
    try:
        db = get_db()
        query_text = request.args.get("q", "").strip()
        category = request.args.get("category", "").strip()
        file_type = request.args.get("file_type", "").strip()
        order_id_str = request.args.get("order_id", "").strip()

        page = request.args.get("page", 1, type=int)
        if page < 1:
            page = 1
        per_page = request.args.get("per_page", 50, type=int)
        if per_page > 100:
            per_page = 100

        query = db.query(OrderAttachment).join(Order, OrderAttachment.order_id == Order.id)
        query = query.filter(Order.status != "DELETED", Order.deleted_at.is_(None))

        if query_text:
            query = query.filter(OrderAttachment.filename.ilike(f"%{query_text}%"))
        if category:
            query = query.filter(OrderAttachment.category == category)
        if file_type:
            query = query.filter(OrderAttachment.file_type == file_type)
        if order_id_str and order_id_str.isdigit():
            query = query.filter(OrderAttachment.order_id == int(order_id_str))

        total_count = query.count()
        attachments = (
            query.order_by(OrderAttachment.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        results = []
        for attachment in attachments:
            storage_key = str(attachment.storage_key or "")
            thumbnail_key = str(attachment.thumbnail_key) if attachment.thumbnail_key is not None else ""
            results.append(
                {
                    "id": attachment.id,
                    "order_id": attachment.order_id,
                    "filename": attachment.filename,
                    "file_type": attachment.file_type,
                    "category": attachment.category or "measurement",
                    "item_index": attachment.item_index,
                    "file_size": attachment.file_size,
                    "storage_key": storage_key,
                    "key": storage_key,
                    "thumbnail_key": thumbnail_key or None,
                    "view_url": build_file_view_url(storage_key) if storage_key else "",
                    "download_url": build_file_download_url(storage_key) if storage_key else "",
                    "thumbnail_view_url": build_file_view_url(thumbnail_key) if thumbnail_key else None,
                    "created_at": attachment.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if attachment.created_at is not None
                    else None,
                    "user_id": attachment.user_id,
                }
            )

        return jsonify(
            {
                "success": True,
                "total_count": total_count,
                "page": page,
                "per_page": per_page,
                "total_pages": (total_count + per_page - 1) // per_page,
                "attachments": results,
            }
        )
    except Exception as e:
        import traceback

        print(f"첨부 검색 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


__all__ = ["api_search_attachments"]

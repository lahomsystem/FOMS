"""HTTP routes for the canonical files API (`foms.api.files` package).

Registry and product code import `foms.api.files` directly.
Wave 8 (W8-B5): legacy `apps.api.files` direct-import bridge removed.
"""
from __future__ import annotations

import logging
import os
import posixpath

from flask import Blueprint, g, jsonify, redirect, send_file
from sqlalchemy import or_

from db import get_db
from models import Order, OrderAttachment
from foms.web.auth import login_required
from foms.services.orders.order_mutation_policy import user_can_read_order
from foms.services.storage import get_storage

logger = logging.getLogger(__name__)

_ACCESS_DENIED_MSG = "이 파일에 접근할 권한이 없습니다."


def _user_id(user) -> int | None:
    try:
        return int(getattr(user, "id", None))
    except (TypeError, ValueError):
        return None


def _deny_order_scope(user, order_id: int):
    """order_id 소유 order 를 read scope(:func:`user_can_read_order`)로 게이트."""
    order = get_db().query(Order).filter(Order.id == order_id).first()
    if not user_can_read_order(user, order):
        return 403, _ACCESS_DENIED_MSG
    return None


def _deny_draft_scope(user, owner_id: int):
    """``order-drafts/{user_id}/...`` 는 본인(또는 ADMIN/MANAGER)만 접근."""
    role = (getattr(user, "role", None) or "").strip().upper()
    if owner_id == _user_id(user) or role in ("ADMIN", "MANAGER"):
        return None
    return 403, _ACCESS_DENIED_MSG


def _deny_file_access(storage_key: str):
    """view/download/presigned 공용 권한 게이트 (FILE-01).

    요청 key 의 소유 order 를 canonical key path 또는 attachment row 로 resolve 한 뒤
    order read scope 를 적용한다. resolve 되지 않는 raw/비정규 key 는 거부한다(arbitrary
    object 접근 차단). ``ponytail: order read scope 는 현재 order-무관 전역 read 이나
    per-order 확장 시 자동 적용되도록 chokepoint 로 order 를 load 한다``.

    Args:
        storage_key: 요청된 object key(``<path:storage_key>``).

    Returns:
        거부면 ``(status, message)``, 허용이면 ``None``.
    """
    user = getattr(g, "current_user", None)
    if user is None or getattr(user, "is_active", None) is False:
        return 403, _ACCESS_DENIED_MSG

    raw = (storage_key or "").strip()
    norm = posixpath.normpath(raw) if raw else ""
    canonical = bool(raw) and norm == raw and not norm.startswith(("..", "/"))
    if canonical:
        parts = norm.split("/")
        if len(parts) >= 2 and parts[1].isdigit():
            if parts[0] == "orders":
                return _deny_order_scope(user, int(parts[1]))
            if parts[0] == "order-drafts":
                return _deny_draft_scope(user, int(parts[1]))

    # legacy coverage gate: 비정규/미지원 namespace 는 attachment row 가 cover 해야 허용.
    att = (
        get_db()
        .query(OrderAttachment)
        .filter(or_(OrderAttachment.storage_key == raw,
                    OrderAttachment.thumbnail_key == raw))
        .first()
    )
    if att is None:
        return 403, _ACCESS_DENIED_MSG
    return _deny_order_scope(user, att.order_id)


def build_file_view_url(storage_key: str) -> str:
    """파일 미리보기 URL 생성 (files_bp /api/files/view 경로)"""
    return f"/api/files/view/{storage_key}"


def build_file_download_url(storage_key: str) -> str:
    """파일 다운로드 URL 생성 (files_bp /api/files/download 경로)"""
    return f"/api/files/download/{storage_key}"


files_bp = Blueprint("files", __name__, url_prefix="/api/files")


def _with_no_store(response):
    """Prevent browser/SW reuse of short-lived storage redirects and URL JSON."""
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _no_store_json(payload: dict, status: int = 200):
    response = jsonify(payload)
    response.status_code = status
    return _with_no_store(response)


@files_bp.route("/view/<path:storage_key>", methods=["GET"])
@login_required
def view(storage_key: str):
    """공용 파일 미리보기(인라인)"""
    try:
        if ".." in storage_key or storage_key.startswith("/"):
            return jsonify({"success": False, "message": "비정상적인 경로입니다."}), 400

        denied = _deny_file_access(storage_key)
        if denied:
            status, message = denied
            return jsonify({"success": False, "message": message}), status

        storage = get_storage()
        if storage.storage_type in ["r2", "s3"]:
            url = storage.get_download_url(storage_key, expires_in=3600)
            if not url:
                return jsonify({"success": False, "message": "파일을 찾을 수 없습니다."}), 404
            return _with_no_store(redirect(url))

        file_path = os.path.join(storage.upload_folder, storage_key)
        if not os.path.exists(file_path):
            return jsonify({"success": False, "message": "파일을 찾을 수 없습니다."}), 404
        return send_file(file_path, as_attachment=False)
    except Exception:
        logger.exception("파일 미리보기 오류")
        return (
            jsonify(
                {
                    "success": False,
                    "message": "파일을 처리하는 중 오류가 발생했습니다.",
                }
            ),
            500,
        )


@files_bp.route("/presigned-urls/<path:storage_key>", methods=["GET"])
@login_required
def presigned_urls(storage_key: str):
    """R2/S3 직접 링크용 presigned URL 반환. 미리보기/다운로드 시 앱 경유 없이 최단 경로."""
    try:
        if ".." in storage_key or storage_key.startswith("/"):
            return _no_store_json({"success": False, "message": "비정상적인 경로입니다."}, 400)

        denied = _deny_file_access(storage_key)
        if denied:
            status, message = denied
            return _no_store_json({"success": False, "message": message}, status)

        storage = get_storage()
        if storage.storage_type in ["r2", "s3"]:
            url = storage.get_download_url(storage_key, expires_in=3600)
            if not url:
                return _no_store_json({"success": False, "message": "파일을 찾을 수 없습니다."}, 404)
            return _no_store_json({"success": True, "view_url": url, "download_url": url})

        return _no_store_json(
            {
                "success": True,
                "view_url": build_file_view_url(storage_key),
                "download_url": build_file_download_url(storage_key),
            }
        )
    except Exception:
        logger.exception("presigned-urls 오류")
        return (
            _no_store_json(
                {
                    "success": False,
                    "message": "파일을 처리하는 중 오류가 발생했습니다.",
                },
                500,
            )
        )


@files_bp.route("/download/<path:storage_key>", methods=["GET"])
@login_required
def download(storage_key: str):
    """공용 파일 다운로드. R2/S3에서는 presigned URL에 ResponseContentDisposition(attachment)을 넣어 새 창에서도 다운로드되게 함."""
    try:
        if ".." in storage_key or storage_key.startswith("/"):
            return jsonify({"success": False, "message": "비정상적인 경로입니다."}), 400

        denied = _deny_file_access(storage_key)
        if denied:
            status, message = denied
            return jsonify({"success": False, "message": message}), status

        storage = get_storage()
        if storage.storage_type in ["r2", "s3"]:
            filename = os.path.basename(storage_key)
            if not filename:
                filename = "download"
            filename_safe = filename.replace('"', "'")
            disposition = f'attachment; filename="{filename_safe}"'
            url = storage.get_download_url(
                storage_key,
                expires_in=3600,
                response_content_disposition=disposition,
            )
            if not url:
                return jsonify({"success": False, "message": "파일을 찾을 수 없습니다."}), 404
            return _with_no_store(redirect(url))

        file_path = os.path.join(storage.upload_folder, storage_key)
        if not os.path.exists(file_path):
            return jsonify({"success": False, "message": "파일을 찾을 수 없습니다."}), 404
        return send_file(file_path, as_attachment=True)
    except Exception:
        logger.exception("파일 다운로드 오류")
        return (
            jsonify(
                {
                    "success": False,
                    "message": "파일을 처리하는 중 오류가 발생했습니다.",
                }
            ),
            500,
        )

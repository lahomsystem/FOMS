"""HTTP routes for the canonical files API (`foms.api.files` package).

Registry and product code import `foms.api.files` directly.
Wave 8 (W8-B5): legacy `apps.api.files` direct-import bridge removed.
"""
from __future__ import annotations

import logging
import os

from flask import Blueprint, jsonify, redirect, send_file

from foms.web.auth import login_required
from foms.services.storage import get_storage

logger = logging.getLogger(__name__)


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

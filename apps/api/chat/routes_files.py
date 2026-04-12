"""Chat file upload/download routes."""

import datetime
import os

from flask import jsonify, redirect, request, send_file, session

from apps.auth import log_access, login_required
from apps.api.chat.blueprint import chat_bp
from apps.api.chat.utils import allowed_chat_file, get_chat_file_max_size
from apps.api.files import build_file_view_url
from constants import CHAT_ALLOWED_EXTENSIONS, DIRECT_UPLOAD_ALLOWED_CONTENT_TYPES
from foms.services.storage import get_storage


@chat_bp.route("/api/chat/upload/session", methods=["POST"])
@login_required
def api_chat_upload_session():
    """Phase D: 채팅 Direct R2 업로드용 세션 발급."""
    try:
        data = request.get_json(silent=True) or {}
        filename = data.get("filename")
        size = data.get("size", 0)
        room_id = data.get("room_id", "")

        if not filename or not isinstance(size, (int, float)) or size <= 0:
            return jsonify({"success": False, "message": "filename, size 필수가 필요합니다."}), 400

        if not allowed_chat_file(filename):
            allowed_exts = ", ".join(sorted(CHAT_ALLOWED_EXTENSIONS))
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"허용되지 않은 파일 형식입니다. 지원: {allowed_exts}",
                    }
                ),
                400,
            )

        max_size = get_chat_file_max_size(filename)
        if size > max_size:
            size_mb = max_size / (1024 * 1024)
            return jsonify({"success": False, "message": f"파일 크기가 너무 큽니다. 최대 {size_mb:.0f}MB"}), 400

        temp_id = f"temp_{int(datetime.datetime.now().timestamp() * 1000)}"
        folder = f"chat/room_{room_id}_{temp_id}" if room_id else f"chat/{temp_id}"

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

        from datetime import datetime as _utc_now, timedelta, timezone

        expires_at = _utc_now.now(timezone.utc) + timedelta(seconds=900)
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

        print(f"채팅 업로드 세션 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@chat_bp.route("/api/chat/upload/complete", methods=["POST"])
@login_required
def api_chat_upload_complete():
    """Phase D: 채팅 Direct R2 업로드 완료 후 file_info 반환."""
    try:
        data = request.get_json(silent=True) or {}
        key = data.get("key")
        filename = data.get("filename")

        if not key or not filename:
            return jsonify({"success": False, "message": "key, filename 필수가 필요합니다."}), 400

        if ".." in key or key.startswith("/") or not key.startswith("chat/"):
            return jsonify({"success": False, "message": "유효하지 않은 key 경로입니다."}), 400

        if not allowed_chat_file(filename):
            return jsonify({"success": False, "message": "허용되지 않은 파일 형식입니다."}), 400

        storage = get_storage()
        if not storage.object_exists(key):
            return jsonify({"success": False, "message": "업로드된 파일을 찾을 수 없습니다."}), 404

        file_size = 0
        try:
            if storage.storage_type in ["r2", "s3"]:
                resp = storage.client.head_object(Bucket=storage.bucket_name, Key=key)
                file_size = resp.get("ContentLength", 0)
        except Exception:
            pass

        file_url = build_file_view_url(key)
        file_type = storage.get_file_type(filename)
        file_info = {
            "filename": filename,
            "url": file_url,
            "storage_url": file_url,
            "thumbnail_url": None,
            "file_type": file_type,
            "size": file_size,
            "key": key,
            "download_url": f"/api/chat/download/{key}",
        }
        log_access(f"채팅 Direct 업로드 완료: {filename}", session.get("user_id"))
        return jsonify({"success": True, "message": "파일이 성공적으로 업로드되었습니다.", "file_info": file_info})
    except Exception as e:
        import traceback

        print(f"채팅 업로드 완료 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@chat_bp.route("/api/chat/upload", methods=["POST"])
@login_required
def api_chat_upload():
    """채팅 파일 업로드 API (Quest 3)."""
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "message": "파일이 선택되지 않았습니다."}), 400
        file = request.files["file"]
        room_id = request.form.get("room_id")
        if file.filename == "":
            return jsonify({"success": False, "message": "파일명이 없습니다."}), 400
        if not allowed_chat_file(file.filename):
            allowed_exts = ", ".join(sorted(CHAT_ALLOWED_EXTENSIONS))
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"허용되지 않은 파일 형식입니다. 지원 형식: {allowed_exts}",
                    }
                ),
                400,
            )
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        max_size = get_chat_file_max_size(file.filename)
        if file_size > max_size:
            size_mb = max_size / (1024 * 1024)
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"파일 크기가 너무 큽니다. 최대 {size_mb:.0f}MB까지 업로드 가능합니다.",
                    }
                ),
                400,
            )
        storage = get_storage()
        temp_id = f"temp_{int(datetime.datetime.now().timestamp() * 1000)}"
        if room_id:
            temp_id = f"room_{room_id}_{temp_id}"
        result = storage.upload_chat_file(file, file.filename, temp_id, generate_thumbnail=False)
        if not result.get("success"):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f'파일 업로드 실패: {result.get("error", "알 수 없는 오류")}',
                    }
                ),
                500,
            )
        storage_key = result.get("key") or ""
        file_url = build_file_view_url(storage_key)
        thumbnail_key = result.get("thumbnail_key")
        thumbnail_url = build_file_view_url(thumbnail_key) if thumbnail_key else None
        file_info = {
            "filename": file.filename,
            "url": file_url,
            "storage_url": file_url,
            "thumbnail_url": thumbnail_url,
            "file_type": result.get("file_type"),
            "size": file_size,
            "key": storage_key,
            "download_url": f"/api/chat/download/{storage_key}",
        }
        log_access(
            f"채팅 파일 업로드: {file.filename} ({result.get('file_type')}, {file_size / 1024 / 1024:.2f}MB)",
            session.get("user_id"),
        )
        return jsonify({"success": True, "message": "파일이 성공적으로 업로드되었습니다.", "file_info": file_info})
    except Exception as e:
        import traceback

        print(f"채팅 파일 업로드 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": f"파일 업로드 중 오류가 발생했습니다: {str(e)}"}), 500


@chat_bp.route("/api/chat/download/<path:storage_key>", methods=["GET"])
@login_required
def api_chat_download(storage_key):
    """채팅 파일 다운로드 API (Quest 4)."""
    try:
        if ".." in storage_key or storage_key.startswith("/"):
            return jsonify({"success": False, "message": "잘못된 파일 경로입니다."}), 400
        storage = get_storage()
        if storage.storage_type in ["r2", "s3"]:
            url = storage.get_download_url(storage_key, expires_in=3600)
            if url:
                log_access(f"채팅 파일 다운로드 요청: {storage_key}", session.get("user_id"))
                return redirect(url)
            return jsonify({"success": False, "message": "파일을 찾을 수 없습니다."}), 404

        file_path = os.path.join(storage.upload_folder, storage_key)
        if not os.path.exists(file_path):
            return jsonify({"success": False, "message": "파일을 찾을 수 없습니다."}), 404
        log_access(f"채팅 파일 다운로드: {storage_key}", session.get("user_id"))
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        import traceback

        print(f"파일 다운로드 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@chat_bp.route("/api/chat/preview/<path:storage_key>", methods=["GET"])
@login_required
def api_chat_preview(storage_key):
    """채팅 파일 미리보기 API (Quest 4)."""
    try:
        if ".." in storage_key or storage_key.startswith("/"):
            return jsonify({"success": False, "message": "잘못된 파일 경로입니다."}), 400
        storage = get_storage()
        filename = storage_key.rsplit("/", 1)[-1] if "/" in storage_key else storage_key
        file_type = storage.get_file_type(filename)
        if file_type == "image":
            if storage.storage_type in ["r2", "s3"]:
                url = storage.get_download_url(storage_key, expires_in=3600)
                if url:
                    return redirect(url)
                return jsonify({"success": False, "message": "파일을 찾을 수 없습니다."}), 404

            file_path = os.path.join(storage.upload_folder, storage_key)
            if os.path.exists(file_path):
                return send_file(file_path)
            return jsonify({"success": False, "message": "파일을 찾을 수 없습니다."}), 404

        if file_type == "video":
            if storage.storage_type in ["r2", "s3"]:
                url = storage.get_download_url(storage_key, expires_in=3600)
                if url:
                    return jsonify({"success": True, "type": "video", "url": url})
                return jsonify({"success": False, "message": "파일을 찾을 수 없습니다."}), 404

            file_path = os.path.join(storage.upload_folder, storage_key)
            if os.path.exists(file_path):
                return send_file(file_path)
            return jsonify({"success": False, "message": "파일을 찾을 수 없습니다."}), 404

        return jsonify({"success": False, "message": "미리보기를 지원하지 않는 파일 형식입니다.", "type": "file"}), 400
    except Exception as e:
        import traceback

        print(f"파일 미리보기 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500

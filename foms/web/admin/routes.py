"""관리자 Blueprint.

/admin - 관리자 페이지
/admin/update_menu - 메뉴 구성 업데이트
/admin/migration - DB 마이그레이션 (SQLite → Postgres)
/admin/test-r2 - R2 스토리지 연결 테스트
/admin/notifications - 공지/알림 발송 화면
"""

import os

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for, flash
from werkzeug.utils import secure_filename

from foms.web.auth import get_user_by_id, log_access, login_required, role_required
from db import get_db
from foms.services.menu_config import invalidate_menu_config_cache
from foms.services.storage import get_storage
from models import User

admin_bp = Blueprint("admin", __name__, url_prefix="")


@admin_bp.route("/admin")
@login_required
@role_required(["ADMIN"])
def admin():
    """관리자 페이지."""
    return render_template("admin/admin.html")


@admin_bp.route("/admin/update_menu", methods=["POST"])
@login_required
@role_required(["ADMIN"])
def update_menu():
    """메뉴 구성 업데이트."""
    try:
        menu_config = request.form.get("menu_config")
        if menu_config:
            os.makedirs("data/admin", exist_ok=True)
            with open("data/admin/menu_config.json", "w", encoding="utf-8") as file_obj:
                file_obj.write(menu_config)

            invalidate_menu_config_cache()

            user_for_log = get_user_by_id(session.get("user_id"))
            user_name_for_log = user_for_log.name if user_for_log else "Unknown user"
            log_access(
                f"메뉴 설정 업데이트 - 담당자: {user_name_for_log} (ID: {session.get('user_id')})",
                session.get("user_id"),
            )

            flash("메뉴 구성이 업데이트되었습니다.", "success")
        else:
            flash("메뉴 구성을 입력해주세요.", "error")
    except Exception as exc:
        flash(f"메뉴 업데이트 중 오류가 발생했습니다: {str(exc)}", "error")

    return redirect(url_for("admin.admin"))


@admin_bp.route("/admin/migration", methods=["GET", "POST"])
@login_required
@role_required(["ADMIN", "MANAGER"])
def admin_migration():
    """Web-based Data Migration (SQLite Upload -> Postgres)."""
    from flask import current_app

    if request.method == "POST":
        if "db_file" not in request.files:
            flash("파일이 없습니다.", "error")
            return redirect(request.url)

        file_obj = request.files["db_file"]
        if file_obj.filename == "":
            flash("파일을 선택해주세요.", "error")
            return redirect(request.url)

        if file_obj:
            filename = secure_filename(file_obj.filename or "")
            temp_path = os.path.join(current_app.config["UPLOAD_FOLDER"], "temp_migration.db")
            file_obj.save(temp_path)

            do_reset = request.form.get("reset") == "on"

            from scripts.migrations.web_migration import run_web_migration

            db_session = get_db()

            success, logs = run_web_migration(temp_path, db_session, reset=do_reset)

            if os.path.exists(temp_path):
                os.remove(temp_path)

            if success:
                flash(f"마이그레이션 완료! ({len(logs)} logs)", "success")
            else:
                flash("마이그레이션 중 오류가 발생했습니다.", "error")

            return render_template("admin/migration_result.html", logs=logs, success=success)

    return render_template("admin/migration_upload.html")


@admin_bp.route("/admin/test-r2")
@login_required
@role_required(["ADMIN", "MANAGER"])
def admin_test_r2():
    """R2 연결 테스트 및 디버깅."""
    try:
        storage = get_storage()

        env_status = {
            "STORAGE_TYPE": storage.storage_type,
            "HAS_ENDPOINT": bool(storage.endpoint_url),
            "HAS_ACCESS_KEY": bool(storage.access_key_id),
            "HAS_SECRET_KEY": bool(storage.secret_access_key),
            "HAS_BUCKET": bool(storage.bucket_name),
            "ENDPOINT_URL": storage.endpoint_url if storage.endpoint_url else "None",
        }

        if storage.storage_type != "r2":
            return jsonify(
                {
                    "success": False,
                    "message": "현재 R2가 활성화되지 않았습니다.",
                    "debug_info": env_status,
                }
            )

        try:
            response = storage.client.list_objects_v2(Bucket=storage.bucket_name, MaxKeys=1)
            test_url = storage.get_download_url("test_connection.txt")

            return jsonify(
                {
                    "success": True,
                    "message": "R2 연결 성공! (AWS S3 API 통신 확인됨)",
                    "bucket_name": storage.bucket_name,
                    "key_count": response.get("KeyCount", 0),
                    "debug_info": env_status,
                    "generated_test_url": test_url,
                }
            )

        except Exception as exc:
            return jsonify(
                {
                    "success": False,
                    "message": f"R2 통신 실패: {str(exc)}",
                    "error_type": type(exc).__name__,
                    "debug_info": env_status,
                }
            )

    except Exception as exc:
        return jsonify({"success": False, "message": f"테스트 중 오류: {str(exc)}"})


@admin_bp.route("/admin/notifications")
@login_required
@role_required(["ADMIN", "MANAGER"])
def admin_notifications():
    """공지/알림 발송 페이지."""
    return render_template("admin/notifications_send.html")


@admin_bp.route("/admin/api/users", methods=["GET"])
@login_required
@role_required(["ADMIN", "MANAGER"])
def admin_api_users():
    """사용자 목록 API (알림 발송 대상 선택용)."""
    try:
        db = get_db()
        users = db.query(User.id, User.name, User.team, User.role).order_by(User.name).limit(500).all()
        return jsonify(
            {
                "success": True,
                "users": [
                    {"id": user.id, "name": user.name, "team": user.team, "role": user.role}
                    for user in users
                ],
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500

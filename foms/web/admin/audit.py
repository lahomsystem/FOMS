"""Admin change logs and security logs (SLG-B4)."""

from flask import render_template, request
from sqlalchemy import or_

from db import get_db
from models import SecurityLog, User
from foms.web.admin.routes import admin_bp
from foms.web.auth import login_required, role_required


@admin_bp.route("/change-logs")
@login_required
def change_logs():
    """변경 로그 페이지 - 모든 사용자가 본인의 변경 이력 확인 가능."""
    return render_template("admin/change_logs.html")


@admin_bp.route("/security_logs")
@login_required
@role_required(["ADMIN"])
def security_logs():
    """보안 로그 목록 조회 (관리자 전용)."""
    db = get_db()

    page = request.args.get("page", 1, type=int)
    per_page = 50
    search_query = request.args.get("search", "")

    query = db.query(SecurityLog).order_by(SecurityLog.timestamp.desc())

    if search_query:
        query = query.join(User, User.id == SecurityLog.user_id, isouter=True).filter(
            or_(
                User.name.ilike(f"%{search_query}%"),
                SecurityLog.message.ilike(f"%{search_query}%"),
            )
        )

    total_logs = query.count()
    logs = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total_logs + per_page - 1) // per_page

    return render_template(
        "admin/security_logs.html",
        logs=logs,
        page=page,
        total_pages=total_pages,
        search_query=search_query,
        total_logs=total_logs,
    )

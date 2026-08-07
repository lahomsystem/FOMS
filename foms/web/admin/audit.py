"""Admin change logs and security logs (SLG-B4; AUDIT-LOG T8 구조화 필터)."""

from typing import Any

from flask import render_template, request
from sqlalchemy import or_
from sqlalchemy.orm import Query

from db import get_db
from models import SecurityLog, User
from foms.web.admin.routes import admin_bp
from foms.web.auth import login_required, role_required

# 페이지당 행 수(고정) — 감사 조회는 관리자 cold path 라 페이지네이션으로 충분하다.
_PER_PAGE = 50

# action 자동완성 후보를 뽑을 때 훑는 최근 행 수 상한. ``SELECT DISTINCT action`` 을
# 테이블 전체에 돌리면 감사 원장이 커질수록 매 페이지 로드가 Seq Scan 이 된다 —
# PK 역순 N행만 본다. 그래서 후보는 "최근에 실제로 쓰인 action" 이며, 화면은 select 가
# 아니라 datalist 라 목록에 없는 값도 직접 입력해 조회할 수 있다.
_ACTION_SAMPLE_ROWS = 5000


def _apply_security_log_filters(query: Query, filters: dict[str, Any]) -> Query:
    """보안 로그 조회에 구조화 필터 + 자유 검색을 적용한다(AUDIT-LOG T8).

    구조화 컬럼(``action``/``target_type``/``target_id``/``user_id``)은 **동등 비교**로
    인덱스를 타고, 자유 검색만 기존처럼 ILIKE 로 남긴다 — "누가 무엇을"을 SQL 로 묻는 게
    T8 의 목적이므로 자유 텍스트 파싱에 의존하지 않는다.

    :param query: 필터를 얹을 ``SecurityLog`` 쿼리.
    :param filters: ``{'search','action','target_type','target_id','user_id'}`` 값 dict
        (빈 문자열/``None`` 은 미적용).
    :return: 필터가 적용된 쿼리.
    """
    if filters.get("user_id"):
        query = query.filter(SecurityLog.user_id == filters["user_id"])
    if filters.get("action"):
        query = query.filter(SecurityLog.action == filters["action"])
    if filters.get("target_type"):
        query = query.filter(SecurityLog.target_type == filters["target_type"])
    if filters.get("target_id"):
        query = query.filter(SecurityLog.target_id == filters["target_id"])
    if filters.get("search"):
        pattern = f"%{filters['search']}%"
        query = query.join(User, User.id == SecurityLog.user_id, isouter=True).filter(
            or_(
                User.name.ilike(pattern),  # perf-ok: bounded admin audit search cold path
                SecurityLog.message.ilike(pattern),  # perf-ok: bounded admin audit search cold path
            )
        )
    return query


@admin_bp.route("/change-logs")
@login_required
def change_logs():
    """변경 로그 페이지 - 모든 사용자가 본인의 변경 이력 확인 가능."""
    return render_template("admin/change_logs.html")


@admin_bp.route("/security_logs")
@login_required
@role_required(["ADMIN"])
def security_logs():
    """보안 로그 목록 조회 (관리자 전용) — 구조화 필터 + 자유 검색 + 페이지네이션.

    :return: ``admin/security_logs.html`` 렌더 결과.
    """
    db = get_db()

    page = max(request.args.get("page", 1, type=int) or 1, 1)
    filters = {
        "search": (request.args.get("search") or "").strip(),
        "action": (request.args.get("action") or "").strip(),
        "target_type": (request.args.get("target_type") or "").strip(),
        "target_id": request.args.get("target_id", type=int),
        "user_id": request.args.get("user_id", type=int),
    }

    query = _apply_security_log_filters(
        db.query(SecurityLog).order_by(SecurityLog.timestamp.desc(), SecurityLog.id.desc()),
        filters,
    )

    total_logs = query.count()
    logs = query.offset((page - 1) * _PER_PAGE).limit(_PER_PAGE).all()
    total_pages = max((total_logs + _PER_PAGE - 1) // _PER_PAGE, 1)

    # 필터 자동완성 소스: 최근 N행에서 실제로 쓰인 action(전수 DISTINCT 금지 — 위 주석).
    recent_actions = (
        db.query(SecurityLog.action)
        .filter(SecurityLog.action.isnot(None))
        .order_by(SecurityLog.id.desc())
        .limit(_ACTION_SAMPLE_ROWS)
        .all()
    )
    action_options = sorted({row[0] for row in recent_actions})
    users = db.query(User).order_by(User.name, User.username).all()

    return render_template(
        "admin/security_logs.html",
        logs=logs,
        page=page,
        total_pages=total_pages,
        total_logs=total_logs,
        filters=filters,
        action_options=action_options,
        users=users,
        # 행위자 표기용 map — SecurityLog 에 relationship 이 없어 행마다 조회하면 N+1 이다.
        user_map={u.id: u for u in users},
    )

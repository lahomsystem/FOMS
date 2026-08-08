"""Admin change logs, security logs, file access logs (SLG-B4; AUDIT-LOG T8·T12)."""

import datetime
import json
from typing import Any

from flask import render_template, request
from sqlalchemy import or_
from sqlalchemy.orm import Query

from db import get_db
from foms.services.datetime_kst import to_utc_naive
from models import AccessLog, SecurityLog, User
from foms.web.admin.routes import admin_bp
from foms.web.auth import login_required, role_required

# 페이지당 행 수(고정) — 감사 조회는 관리자 cold path 라 페이지네이션으로 충분하다.
_PER_PAGE = 50

# 파일 접근 종류 — writer(:func:`foms.services.audit_writer.record_file_access`)가 쓰는
# 3종이 전부다. security_logs 의 action 과 달리 폐집합이라 datalist 가 아닌 select 로 낸다.
_FILE_ACCESS_ACTIONS = ("FILE_VIEW", "FILE_PRESIGNED", "FILE_DOWNLOAD")

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


def _kst_date_bound_utc(raw: str, *, next_day: bool) -> datetime.datetime | None:
    """``YYYY-MM-DD``(KST 입력)를 DB 비교용 UTC naive 경계로 바꾼다.

    ``access_logs.timestamp`` 는 naive=UTC 규약이라 한국 날짜를 그대로 비교하면 9시간이
    밀린다(한국 오전 9시 이전 열람이 전날로 샌다). 종료일은 **다음날 00:00 KST 미만**으로
    비교해야 그 날 하루가 온전히 포함된다 — 그래서 경계 계산을 한 곳에 모은다.

    :param raw: 화면에서 온 ``YYYY-MM-DD`` 문자열(빈 값 허용).
    :param next_day: True 면 하루 더한 날의 00:00 KST(=종료 경계, 미만 비교용).
    :return: UTC naive datetime, 값이 없거나 형식이 틀리면 ``None``(필터 미적용).
    """
    if not raw:
        return None
    try:
        day = datetime.date.fromisoformat(raw)
    except ValueError:
        return None
    if next_day:
        day += datetime.timedelta(days=1)
    return to_utc_naive(f"{day.isoformat()}T00:00:00+09:00")


def _apply_access_log_filters(query: Query, filters: dict[str, Any]) -> Query:
    """파일 열람 기록 조회에 사용자·행위·기간·주문·파일 키 필터를 적용한다.

    ``user_id``·``action``·``timestamp`` 는 인덱스(``ix_access_logs_user_id_timestamp``·
    ``ix_access_logs_timestamp``)를 타는 동등/범위 비교다. 주문·파일 키만 문자열 매칭인데,
    ``additional_data`` 가 JSON **문자열** 컬럼이라 다른 수단이 없다(컬럼 승격은 별건).

    :param query: 필터를 얹을 ``AccessLog`` 쿼리.
    :param filters: ``{'user_id','action','timestamp_from','timestamp_to','order_id',
        'storage_key'}`` 값 dict(빈 값/``None`` 은 미적용).
    :return: 필터가 적용된 쿼리.
    """
    if filters.get("user_id"):
        query = query.filter(AccessLog.user_id == filters["user_id"])
    if filters.get("action"):
        query = query.filter(AccessLog.action == filters["action"])
    if filters.get("timestamp_from") is not None:
        query = query.filter(AccessLog.timestamp >= filters["timestamp_from"])
    if filters.get("timestamp_to") is not None:
        query = query.filter(AccessLog.timestamp < filters["timestamp_to"])
    if filters.get("order_id"):
        # 주문 축은 ``additional_data`` JSON 문자열 안에 있다. 구분자(``,``/``}``)까지 붙여
        # 비교하지 않으면 주문 12 가 주문 123 의 행까지 끌고 온다(접두 오탐).
        order_id = int(filters["order_id"])
        query = query.filter(
            or_(
                AccessLog.additional_data.like(f'%"order_id": {order_id},%'),  # perf-ok: bounded admin audit cold path
                AccessLog.additional_data.like(f'%"order_id": {order_id}}}%'),  # perf-ok: bounded admin audit cold path
            )
        )
    if filters.get("storage_key"):
        pattern = f"%{filters['storage_key']}%"
        query = query.filter(AccessLog.additional_data.ilike(pattern))  # perf-ok: bounded admin audit cold path
    return query


def _access_log_row(log_entry: AccessLog) -> dict[str, Any]:
    """행 1건을 화면 표시용 dict 로 편다(``additional_data`` JSON 해석).

    파싱에 실패하거나 dict 가 아니면 원문을 그대로 넘긴다 — 감사 화면이 읽지 못한 값을
    조용히 감추면 "기록은 있는데 화면에 없다"가 되어 감사가 무력해진다.

    :param log_entry: ``AccessLog`` 행.
    :return: ``{'log','storage_key','order_id','suppressed','raw'}`` dict.
    """
    payload: Any = None
    raw = log_entry.additional_data or ""
    if raw:
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            payload = None
    if not isinstance(payload, dict):
        return {"log": log_entry, "storage_key": None, "order_id": None,
                "suppressed": None, "raw": raw or None}

    order_id = payload.get("order_id")
    return {
        "log": log_entry,
        "storage_key": payload.get("storage_key"),
        "order_id": order_id if isinstance(order_id, int) else None,
        "suppressed": payload.get("suppressed"),
        # 계약 외 키(향후 writer 확장분)는 버리지 않고 원문으로 함께 보여준다.
        "raw": raw if set(payload) - {"storage_key", "order_id", "suppressed"} else None,
    }


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


@admin_bp.route("/admin/file-access-logs")
@login_required
@role_required(["ADMIN"])
def file_access_logs():
    """파일 열람 기록 조회 (관리자 전용) — 누가·언제·어떤 파일을 열었는가.

    ``access_logs`` 는 T6 에서 writer 만 살아났고 조회 화면이 없어 SQL 로만 물을 수
    있었다. 열람 이력은 사고 조사에서 가장 먼저 필요한 원장이라 화면으로 낸다.
    필터(사용자·행위·기간·주문·파일 키)와 페이지네이션은 보안 로그 화면과 같은 규약이다.

    :return: ``admin/file_access_logs.html`` 렌더 결과.
    """
    db = get_db()

    page = max(request.args.get("page", 1, type=int) or 1, 1)
    filters: dict[str, Any] = {
        "user_id": request.args.get("user_id", type=int),
        "action": (request.args.get("action") or "").strip(),
        "order_id": request.args.get("order_id", type=int),
        "storage_key": (request.args.get("storage_key") or "").strip(),
        "date_from": (request.args.get("date_from") or "").strip(),
        "date_to": (request.args.get("date_to") or "").strip(),
    }
    filters["timestamp_from"] = _kst_date_bound_utc(filters["date_from"], next_day=False)
    filters["timestamp_to"] = _kst_date_bound_utc(filters["date_to"], next_day=True)

    query = _apply_access_log_filters(
        db.query(AccessLog).order_by(AccessLog.timestamp.desc(), AccessLog.id.desc()),
        filters,
    )

    total_logs = query.count()
    logs = query.offset((page - 1) * _PER_PAGE).limit(_PER_PAGE).all()
    total_pages = max((total_logs + _PER_PAGE - 1) // _PER_PAGE, 1)

    users = db.query(User).order_by(User.name, User.username).all()

    return render_template(
        "admin/file_access_logs.html",
        rows=[_access_log_row(entry) for entry in logs],
        page=page,
        total_pages=total_pages,
        total_logs=total_logs,
        filters=filters,
        action_options=_FILE_ACCESS_ACTIONS,
        users=users,
        # 행위자 표기용 map — 행마다 relationship 을 타면 페이지당 50회 조회(N+1)다.
        user_map={u.id: u for u in users},
    )

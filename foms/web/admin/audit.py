"""Admin change logs, security logs, file access logs (SLG-B4; AUDIT-LOG T8·T12)."""

import datetime
import json
from typing import Any

from flask import render_template, request
from sqlalchemy import or_
from sqlalchemy.orm import Query

from db import get_db
from foms.services.audit_message_display import (
    action_label,
    collect_order_ids,
    describe_field_change,
    humanize_message,
)
from foms.services.datetime_kst import to_utc_naive
from models import AccessLog, Order, SecurityLog, User
from foms.web.admin.routes import admin_bp
from foms.web.auth import login_required, role_required

# 페이지당 행 수(고정) — 감사 조회는 관리자 cold path 라 페이지네이션으로 충분하다.
_PER_PAGE = 50

# 파일 접근 종류 — writer(:func:`foms.services.audit_writer.record_file_access`)가 쓰는
# 3종이 전부다. security_logs 의 action 과 달리 폐집합이라 datalist 가 아닌 select 로 낸다.
_FILE_ACCESS_ACTIONS = ("FILE_VIEW", "FILE_PRESIGNED", "FILE_DOWNLOAD")

# 권한 거부 기록 — 구조화 action 과 T8 이전 자유 텍스트 두 형태가 공존한다.
# 운영 실측(최근 30일): 1,471건 중 474건(32%)이 거부 로그이고 그 중 282건이 한 사람의
# `/trash` 반복 클릭이었다. 기본 목록에 섞으면 첫 페이지가 거부로 덮여 정작 "누가 무엇을
# 했는가"가 안 보인다 — 기본은 빼고 스위치로 본다(값을 지우는 게 아니라 분리다).
_DENIED_ACTIONS = ("ACCESS_DENIED", "CSRF_BLOCKED")
_DENIED_MESSAGE_PREFIX = "권한 없는 접근 시도"

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

    기간(``timestamp_from``/``timestamp_to``)은 ``ix_security_logs_timestamp_id``
    범위 비교다(SEC-LOG-TIME-00). 운영 원장이 2만 건을 넘어 "그날 무슨 일이 있었나"를
    페이지를 넘겨 찾을 수 없었다 — 파일 열람 화면과 같은 KST 경계 규약을 쓴다.

    거부 기록(:data:`_DENIED_ACTIONS`·구형식 "권한 없는 접근 시도")은 ``include_denied``
    를 켤 때만 포함한다(위 상수 주석의 실측 근거).

    :param query: 필터를 얹을 ``SecurityLog`` 쿼리.
    :param filters: ``{'search','action','target_type','target_id','user_id',
        'timestamp_from','timestamp_to','include_denied'}`` 값 dict(빈 문자열/``None`` 은 미적용).
    :return: 필터가 적용된 쿼리.
    """
    if filters.get("timestamp_from") is not None:
        query = query.filter(SecurityLog.timestamp >= filters["timestamp_from"])
    if filters.get("timestamp_to") is not None:
        query = query.filter(SecurityLog.timestamp < filters["timestamp_to"])
    if not filters.get("include_denied") and not filters.get("action"):
        query = query.filter(
            or_(SecurityLog.action.is_(None), SecurityLog.action.notin_(_DENIED_ACTIONS)),
            or_(
                SecurityLog.message.is_(None),
                SecurityLog.message.notlike(f"{_DENIED_MESSAGE_PREFIX}%"),
            ),
        )
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
    ``ix_access_logs_timestamp``)를 타는 동등/범위 비교다. 주문 축도 ACCESS-LOG-DETAIL-00
    이후로는 구조화 컬럼 ``detail``(JSONB) 위의 **정수 동등 비교**라
    ``ix_access_logs_detail_order_id`` 표현식 인덱스를 탄다 — 예전처럼 JSON 문자열에
    구분자를 붙여 LIKE 하지 않으므로 접두 오탐(주문 12 ↔ 123)이 구조적으로 불가능하다.
    파일 키만 ``additional_data`` 원문 ILIKE 로 남는다(부분 문자열 검색이라 인덱스 대상 아님).

    ``access_logs`` 에는 T6 이전 구현이 남긴 **구 형식 행**이 섞여 있다(운영 실측: 스테이징
    121행 중 119행). 그 행들은 ``action`` 컬럼에 문장을 통째로 넣었고 payload 에 고객명·연락처
    변경 이력까지 담겨 있다 — 파일 열람 화면이 기본으로 그것까지 보여주면 화면 이름과 내용이
    어긋나고 파일 감사와 무관한 PII 가 노출된다. 그래서 기본 범위는 파일 접근 3종이고,
    ``include_legacy`` 를 켤 때만 전체를 본다(원장이 화면에서 사라지지는 않게).

    :param query: 필터를 얹을 ``AccessLog`` 쿼리.
    :param filters: ``{'user_id','action','timestamp_from','timestamp_to','order_id',
        'storage_key','include_legacy'}`` 값 dict(빈 값/``None`` 은 미적용).
    :return: 필터가 적용된 쿼리.
    """
    if not filters.get("include_legacy"):
        query = query.filter(AccessLog.action.in_(_FILE_ACCESS_ACTIONS))
    if filters.get("user_id"):
        query = query.filter(AccessLog.user_id == filters["user_id"])
    if filters.get("action"):
        query = query.filter(AccessLog.action == filters["action"])
    if filters.get("timestamp_from") is not None:
        query = query.filter(AccessLog.timestamp >= filters["timestamp_from"])
    if filters.get("timestamp_to") is not None:
        query = query.filter(AccessLog.timestamp < filters["timestamp_to"])
    if filters.get("order_id"):
        # 주문 축은 구조화 컬럼 ``detail`` 의 정수 동등 비교다(ACCESS-LOG-DETAIL-00).
        # PG 에서는 ``CAST((detail ->> 'order_id') AS INTEGER) = ?`` 로 나가
        # ``ix_access_logs_detail_order_id`` 를 탄다.
        query = query.filter(
            AccessLog.detail["order_id"].as_integer() == int(filters["order_id"])
        )
    if filters.get("storage_key"):
        pattern = f"%{filters['storage_key']}%"
        query = query.filter(AccessLog.additional_data.ilike(pattern))  # perf-ok: bounded admin audit cold path
    return query


def _access_log_row(log_entry: AccessLog) -> dict[str, Any]:
    """행 1건을 화면 표시용 dict 로 편다(``detail`` 우선, 없으면 ``additional_data`` 해석).

    ACCESS-LOG-DETAIL-00 이후 writer 는 두 컬럼에 같은 값을 쓴다. 그래도 원문 파싱 경로를
    남기는 이유는 **``detail`` 이 NULL 인 행**이 실제로 있기 때문이다 — 마이그레이션이
    백필하지 않은 구 형식 행, 그리고 코드 배포와 마이그레이션 사이에 쓰인 행.

    파싱에 실패하거나 dict 가 아니면 원문을 그대로 넘긴다 — 감사 화면이 읽지 못한 값을
    조용히 감추면 "기록은 있는데 화면에 없다"가 되어 감사가 무력해진다.

    :param log_entry: ``AccessLog`` 행.
    :return: ``{'log','storage_key','order_id','suppressed','raw'}`` dict.
    """
    payload: Any = log_entry.detail
    raw = log_entry.additional_data or ""
    if not isinstance(payload, dict) and raw:
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
        "user_agent_short": summarize_user_agent(log_entry.user_agent),
        "action_label": action_label(log_entry.action),
    }


def summarize_user_agent(raw: str | None) -> str:
    """UA 원문을 ``Chrome 150 · Windows`` 형태로 줄인다(원문은 화면이 ``title`` 로 보존).

    UA 전문은 한 줄이 120자를 넘어 표에서 4줄을 차지했다 — 7칸짜리 감사 표가 UA 로 덮여
    정작 "누가 어떤 파일을" 이 안 보였다(2026-08-11 운영 실측). 조사에 실제로 쓰이는 축은
    브라우저와 OS 두 개뿐이라 그 둘만 남긴다. **원문을 지우지는 않는다** — 알 수 없는 UA 는
    앞부분을 그대로 보여줘 감사 기록이 화면에서 사라지지 않게 한다.

    :param raw: ``AccessLog.user_agent`` 원문(``None``·빈 값 허용).
    :return: 요약 문자열. 값이 없으면 ``""``.
    """
    if not raw:
        return ""
    ua = raw.strip()
    browser = ""
    # 순서가 규칙이다 — Edge·Samsung·Chrome 은 UA 에 "Chrome" 을 함께 달고,
    # Chrome 은 "Safari" 를 함께 단다. 더 구체적인 것부터 본다.
    for token, label in (("Edg/", "Edge"), ("SamsungBrowser/", "Samsung Internet"),
                         ("OPR/", "Opera"), ("Chrome/", "Chrome"),
                         ("Firefox/", "Firefox"), ("Version/", "Safari")):
        index = ua.find(token)
        if index < 0:
            continue
        major = ""
        for char in ua[index + len(token):]:
            if not char.isdigit():
                break
            major += char
        browser = f"{label} {major}".strip()
        break

    platform = ""
    for token, label in (("Windows NT", "Windows"), ("Android", "Android"),
                         ("iPhone", "iPhone"), ("iPad", "iPad"),
                         ("Mac OS X", "macOS"), ("Linux", "Linux")):
        if token in ua:
            platform = label
            break

    if browser and platform:
        return f"{browser} · {platform}"
    if browser or platform:
        return browser or platform
    return ua[:40]


def _order_display_names(db: Any, logs: list[SecurityLog]) -> dict[int, str]:
    """이 페이지가 언급하는 주문들의 고객명을 **한 번에** 읽는다(N+1 금지).

    로그 문장은 주문번호만 담고 있어 "누구 건인지"를 알 수 없다. 행마다 주문을 조회하면
    페이지당 50회가 되므로, 문장에서 id 를 모아 ``in_()`` 1회로 끝낸다.

    :param db: 활성 세션.
    :param logs: 이번 페이지에 그릴 로그 행들.
    :return: ``{주문 id: 고객명}`` (없는 주문은 키 자체가 없다).
    """
    order_ids = set(collect_order_ids(entry.message for entry in logs))
    # 구조화 행은 문장이 아니라 target_id 로 주문을 가리킨다.
    order_ids.update(
        entry.target_id for entry in logs
        if entry.target_type == "order" and entry.target_id
    )
    if not order_ids:
        return {}
    rows = (
        db.query(Order.id, Order.customer_name)
        .filter(Order.id.in_(order_ids))
        .all()  # perf-ok: bounded by page size, single batched lookup
    )
    return {row[0]: row[1] for row in rows if row[1]}


def _security_log_row(entry: SecurityLog, customer_names: dict[int, str]) -> dict[str, Any]:
    """보안 로그 1행을 화면 표시용 dict 로 편다(문장 한글화 + 원문 보존).

    구조화 detail 이 있으면 그것으로 문장을 다시 만들고(``before → after`` 까지 보인다),
    없으면 저장된 자유 텍스트를 역파싱한다. **원문은 항상 함께 넘긴다** — 화면이 "원문 보기"
    로 되짚을 수 있어야 감사 기록을 신뢰할 수 있다.

    :param entry: ``SecurityLog`` 행.
    :param customer_names: ``{주문 id: 고객명}`` 배치 조회 결과.
    :return: ``{'log','display','raw_message','changed'}`` dict.
    """
    detail = entry.detail if isinstance(entry.detail, dict) else {}
    field = detail.get("field")
    display: str | None = None

    if field and entry.target_type == "order" and entry.target_id:
        order_id = entry.target_id
        display = describe_field_change(
            order_id=order_id,
            field=str(field),
            after=detail.get("after"),
            before=detail.get("before"),
            has_before="before" in detail,
            customer_name=detail.get("customer_name") or customer_names.get(order_id),
            order_type=detail.get("order_type"),
        )
    if display is None:
        display = humanize_message(entry.message, customer_names)

    return {
        "log": entry,
        "display": display,
        "raw_message": entry.message or "",
        "changed": display != (entry.message or ""),
        "detail_text": _detail_text(entry.detail),
        # 배지는 업무 라벨로 낸다(코드는 화면이 title 로 보존) — 표시 SSOT 재사용.
        "action_label": action_label(entry.action),
        "detail_keys": len(entry.detail) if isinstance(entry.detail, dict) else 0,
    }


def _detail_text(detail: Any) -> str:
    """부가정보(JSONB)를 사람이 읽는 문자열로 만든다.

    Jinja ``tojson`` 은 Flask 기본 provider 를 타서 ``ensure_ascii=True`` 다 — 고객명이
    화면에 ``"\\uc774\\uac00\\uc5b8"`` 로 나와 감사 화면이 읽히지 않았다(2026-08-11 운영 실측).
    HTML 안전은 이스케이프가 아니라 **Jinja 자동 escape** 가 책임진다(템플릿이 ``{{ }}`` 로
    출력하므로 ``<``·``&`` 는 엔티티가 된다) — 그러니 여기서는 한글을 그대로 둔다.

    :param detail: ``SecurityLog.detail`` 값(dict 가 아니면 빈 문자열).
    :return: 들여쓴 JSON 문자열. 값이 없으면 ``""``.
    """
    if not isinstance(detail, dict) or not detail:
        return ""
    try:
        return json.dumps(detail, ensure_ascii=False, indent=2, sort_keys=True)
    except (TypeError, ValueError):
        # 직렬화 불가 값이 섞여도 화면은 살아야 한다 — 원문 repr 로 낸다(감사 기록 은닉 금지).
        return repr(detail)


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
        "date_from": (request.args.get("date_from") or "").strip(),
        "date_to": (request.args.get("date_to") or "").strip(),
        # 권한 거부 기록 포함 여부 — 기본 꺼짐(위 _DENIED_ACTIONS 주석).
        "include_denied": bool(request.args.get("include_denied")),
    }
    filters["timestamp_from"] = _kst_date_bound_utc(filters["date_from"], next_day=False)
    filters["timestamp_to"] = _kst_date_bound_utc(filters["date_to"], next_day=True)

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

    customer_names = _order_display_names(db, logs)

    return render_template(
        "admin/security_logs.html",
        rows=[_security_log_row(entry, customer_names) for entry in logs],
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
        # 구 형식 행(파일 접근 이전 자유 텍스트 기록)까지 볼지 — 기본 꺼짐(위 필터 주석).
        "include_legacy": bool(request.args.get("include_legacy")),
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

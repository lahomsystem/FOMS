"""정산 대시보드 조회 API — SETTLE-DASH-01 M2 + SETTLE-TABS (읽기 전용).

- ``GET /api/settlement/aggregates?month_from=YYYY-MM&month_to=YYYY-MM&granularity=day|week|month``
- ``GET /api/settlement/rows?period=&settlement=&channel=&aging=&page=`` (실무 탭)

집계 커널은 :func:`foms.services.settlement_aggregation.aggregate_settlement` (M1)이고
이 모듈은 파라미터 파싱·권한 판정·응답 포장만 한다.

**두 엔드포인트의 노출 계약이 다르다(스펙 개정 A §13.1).**
``aggregates`` 는 앞으로도 **주문 행 원본을 절대 넣지 않는다** — 집계 버킷만 낸다.
``rows`` 는 실무 탭이 쓰는 행 표면이라 고객 **성명 + 주문번호**까지 낸다.
연락처·주소·현금영수증 요청 자유텍스트 원문은 ``rows`` 에서도 내지 않는다
(§13.3-1). 두 계약은 각자 전용 테스트로 고정돼 있다 — 한쪽을 다른 쪽 근거로 완화하지 마라.

``rows`` 안에는 **게이트가 하나 더** 있다(v1.1 T13). 네이버 정산 상태
(``row.naver_settlement``)는 회계 전용이라
:func:`foms.services.settlement_channel_access.can_view_channel_settlement` 를 통과한
actor 의 응답에만 **키가 생긴다**. 응답 최상위 ``channel_settlement_visible`` 이 그 판정의
사본이다 — 화면이 컬럼을 그릴지 말지 같은 신호로 정하게 한다.

**권한(§5)**: GET 은 ``enforce_order_mutation_policy`` 의 ``_WRITE_METHODS`` 밖이라
before_request 가드에 도달하지 않는다. 그래서 이 핸들러가 페이지와 **같은 policy_id
상수**(:data:`foms.web.cs.settlement_dashboard.SETTLEMENT_DASHBOARD_POLICY_ID`)로 직접
판정한다. ``@login_required`` 는 그대로 두어 미인증은 로그인 경로로 보낸다.

이 모듈은 읽기 전용이다 — 커밋·flag_modified·Order 속성 대입을 하지 않는다.
"""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from db import get_db
from foms.services.datetime_kst import get_today_kst
from foms.services.settlement_aggregation import aggregate_settlement
from foms.services.settlement_channel_access import can_view_channel_settlement
from foms.services.settlement_rows import PER_PAGE, list_settlement_rows
from foms.web.auth import login_required
from foms.web.cs.settlement_dashboard import (
    can_view_manager_breakdown,
    can_view_settlement_dashboard,
)

#: 담당자별 매출 = 직원 실적. 관리자급이 아니면 **payload 에서 빼고** 내려보낸다
#: (클라 숨김 금지 — 데이터를 내려주고 감추면 개발자 도구로 그대로 보인다).
_MANAGER_ONLY_KEYS = ("managers", "managers_total")

#: 파라미터 미지정 시 시계열 세밀도. 화면 기본이 "이번 달 일별"이다.
_DEFAULT_GRANULARITY = "day"
#: 파라미터 미지정 시 조회 범위 길이(개월). 전월 비교선이 서게 2개월을 기본으로 낸다.
_DEFAULT_RANGE_MONTHS = 2

settlement_api_bp = Blueprint(
    "settlement_api",
    __name__,
    url_prefix="/api/settlement",
)


def _month_key(year: int, month: int) -> str:
    """(년, 월) → "YYYY-MM" 키."""
    return f"{year:04d}-{month:02d}"


def _default_month_range() -> tuple[str, str]:
    """파라미터 미지정 시 기본 조회 범위(전월 ~ 이번 달, KST 기준).

    ``get_today_kst()`` 는 ``date`` 를 반환한다 — ``.date()`` 를 부르면 AttributeError
    로 500 이 된다(프로젝트 함정 기록).

    Returns:
        (month_from, month_to) — 각각 "YYYY-MM".
    """
    today = get_today_kst()
    index = today.year * 12 + (today.month - 1)
    start = index - (_DEFAULT_RANGE_MONTHS - 1)
    return (
        _month_key(start // 12, start % 12 + 1),
        _month_key(today.year, today.month),
    )


def _error(message: str, status: int):
    """공통 실패 응답(``{'success': False, 'data': None, 'error': ...}``)."""
    return jsonify({"success": False, "data": None, "error": message}), status


@settlement_api_bp.route("/aggregates", methods=["GET"])
@login_required
def api_settlement_aggregates():
    """정산 대시보드 집계 조회(읽기 전용).

    Query Args:
        month_from: 조회 시작 월 "YYYY-MM"(기본 전월).
        month_to: 조회 종료 월 "YYYY-MM"(기본 이번 달, KST).
        granularity: "day" | "week" | "month"(기본 "day").

    Returns:
        200 ``{'success': True, 'data': <aggregate_settlement 반환값>, 'error': None}``.
        권한 거부 403, 파라미터 오류(형식·범위 역전·12개월 초과·granularity) 400 —
        모두 같은 형식이다.
    """
    user = getattr(g, "current_user", None)
    if not can_view_settlement_dashboard(user):
        return _error("정산 대시보드 열람 권한이 없습니다.", 403)

    default_from, default_to = _default_month_range()
    month_from = (request.args.get("month_from") or "").strip() or default_from
    month_to = (request.args.get("month_to") or "").strip() or default_to
    granularity = (request.args.get("granularity") or "").strip() or _DEFAULT_GRANULARITY

    try:
        data = aggregate_settlement(
            get_db(),
            month_from=month_from,
            month_to=month_to,
            granularity=granularity,
        )
    except ValueError as exc:
        # 집계 커널이 사람이 읽는 한글 사유를 담아 던진다 — 그대로 전달한다(내부 스택 노출 없음).
        return _error(str(exc), 400)

    if not can_view_manager_breakdown(user):
        for key in _MANAGER_ONLY_KEYS:
            data.pop(key, None)

    return jsonify({"success": True, "data": data, "error": None})


@settlement_api_bp.route("/rows", methods=["GET"])
@login_required
def api_settlement_rows():
    """정산 실무 탭의 주문 행 목록(읽기 전용).

    ``aggregates`` 와 **같은 권한 게이트**를 쓰되 노출 계약이 다르다 — 고객 성명과
    주문번호까지 낸다(스펙 개정 A §13). 연락처·주소·현금영수증 원문은 내지 않는다.

    Query Args:
        period: "all" | "7" | "30" | "31" — 완료 후 **경과일** 기준(기본 "all").
        settlement: "all" | "pending" | "issued"(기본 "all").
        channel: "all" 또는 채널 코드(기본 "all").
        aging: aging 버킷 코드 또는 빈 값(기본 빈 값).
        page: 1부터(기본 1).

    Returns:
        200 ``{'success': True, 'data': <list_settlement_rows 반환값>, 'error': None}``.
        ``data.channel_settlement_visible`` 이 True 인 응답의 행에만
        ``naver_settlement`` 키가 있다. 권한 거부 403, 필터 값 오류 400 — 모두 같은 형식이다.
    """
    user = getattr(g, "current_user", None)
    if not can_view_settlement_dashboard(user):
        return _error("정산 대시보드 열람 권한이 없습니다.", 403)

    # 이 표면의 게이트(정산 대시보드)는 CS·영업까지 열려 있고, 네이버 정산 상태는 **회계
    # 전용**이라 게이트가 하나 더 있다. 서버가 키 자체를 만들지 않는다 — 내려보내고
    # 화면에서 감추면 개발자 도구로 그대로 보인다(클라 숨김 금지).
    include_naver_settlement = can_view_channel_settlement(user)

    try:
        data = list_settlement_rows(
            get_db(),
            period=(request.args.get("period") or "").strip() or "all",
            settlement=(request.args.get("settlement") or "").strip() or "all",
            channel=(request.args.get("channel") or "").strip() or "all",
            aging=(request.args.get("aging") or "").strip(),
            page=request.args.get("page", type=int) or 1,
            per_page=PER_PAGE,
            include_naver_settlement=include_naver_settlement,
        )
    except ValueError as exc:
        return _error(str(exc), 400)

    # 화면이 "칸이 없는 것"과 "값이 비어 있는 것"을 구분하려면 권한 판정 자체가 필요하다.
    data["channel_settlement_visible"] = include_naver_settlement
    return jsonify({"success": True, "data": data, "error": None})

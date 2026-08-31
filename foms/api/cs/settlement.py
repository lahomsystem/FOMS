"""정산 대시보드 집계 API — SETTLE-DASH-01 M2 (읽기 전용).

``GET /api/settlement/aggregates?month_from=YYYY-MM&month_to=YYYY-MM&granularity=day|week|month``

집계 커널은 :func:`foms.services.settlement_aggregation.aggregate_settlement` (M1)이고
이 모듈은 파라미터 파싱·권한 판정·응답 포장만 한다. **주문 행 원본을 응답에 넣지 않는다**
— 집계 버킷만 내보내는 것이 §5 권한 설계와 정합이다.

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
from foms.web.auth import login_required
from foms.web.cs.settlement_dashboard import can_view_settlement_dashboard

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
    if not can_view_settlement_dashboard(getattr(g, "current_user", None)):
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

    return jsonify({"success": True, "data": data, "error": None})

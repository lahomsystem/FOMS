"""ERP 출고 대시보드 요청 파라미터 파서 (Batch 3 shipment 구조-추출, 동작 보존).

`erp_shipment_dashboard()` 라우트의 request.args 파싱·정규화 + range/single-day 파생을
분리한다. 값·검증 규칙은 기존 라우트와 1:1 동일:
- q/search/manager alias 검색어
- date_from/date_to 둘 다 유효 ISO일 때만 range
- date 단일일(range 아닐 때, 유효 ISO)
- range/single 둘 다 없으면 당일 기본 진입
- is_construction(시공팀)·mine_only(시공 한정)·user_locked_calendar_date(date 인자 고정)

검색 기반 자동 날짜 보정(_pick_shipment_search_focus_date)은 DB 의존이므로 라우트가 유지한다.
flat 모듈(measurement_* 관행, subpackage __init__ 순환 회피).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from foms.services.request_utils import get_search_query_arg
from foms.services.common.erp_mine_filter import erp_mine_only_for_construction


@dataclass(frozen=True)
class ShipmentDashboardFilters:
    """출고 대시보드 라우트가 사용하는 파싱·정규화된 필터 값 묶음."""

    search_q: str
    date_from: str
    date_to: str
    req_date: str
    is_construction: object  # 원본 보존: current_user and (team=='CONSTRUCTION') → None/bool
    mine_only: bool
    use_range: bool
    use_single_day: bool
    selected_date: str
    user_locked_calendar_date: bool


def parse_shipment_dashboard_filters(request, current_user, today_kst) -> ShipmentDashboardFilters:
    """`erp_shipment_dashboard`의 request.args 파싱·정규화를 동작 보존으로 분리.

    Args:
        request: Flask 요청 객체.
        current_user: 현재 사용자(없을 수 있음). is_construction/mine_only 판정.
        today_kst: get_today_kst() 결과(라우트와 동일 인스턴스). 기본 날짜 기준.

    Returns:
        ShipmentDashboardFilters: 라우트가 그대로 쓰는 정규화 필터 값.
        selected_date/req_date는 초기값이며, 라우트의 검색 자동 날짜 보정이 이후 덮어쓸 수 있다.
    """
    today_date = today_kst.strftime('%Y-%m-%d')
    search_q = get_search_query_arg('q', 'search', 'manager')
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_arg_raw = (request.args.get('date') or '').strip()
    req_date = date_arg_raw

    is_construction = current_user and getattr(current_user, 'team', None) == 'CONSTRUCTION'
    mine_only = erp_mine_only_for_construction(request, current_user)

    use_range = bool(date_from and date_to)
    if use_range:
        try:
            datetime.datetime.strptime(date_from, '%Y-%m-%d').date()
            datetime.datetime.strptime(date_to, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            use_range = False
    use_single_day = bool(req_date) and not use_range
    if use_single_day:
        try:
            datetime.datetime.strptime(req_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            use_single_day = False
    # 기본 진입은 당일 주문만 로드한다. 전체 목록 로드는 대시보드 기본 동작에서 제외.
    if not use_range and not use_single_day:
        req_date = today_date
        use_single_day = True
    selected_date = req_date

    user_locked_calendar_date = bool(date_arg_raw)

    return ShipmentDashboardFilters(
        search_q=search_q,
        date_from=date_from,
        date_to=date_to,
        req_date=req_date,
        is_construction=is_construction,
        mine_only=mine_only,
        use_range=use_range,
        use_single_day=use_single_day,
        selected_date=selected_date,
        user_locked_calendar_date=user_locked_calendar_date,
    )

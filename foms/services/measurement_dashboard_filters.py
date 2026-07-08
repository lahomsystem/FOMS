"""ERP 실측 대시보드 요청 파라미터 파서 (Batch 3 measurement 구조-추출, 동작 보존).

`erp_measurement_dashboard()` 라우트의 request.args 파싱·정규화 + 날짜창 파생을
분리한다. 값·검증 규칙은 기존 라우트와 1:1 동일:
- q/search/manager alias 검색어
- date_from/date_to 둘 다 유효 ISO일 때만 range
- date 단일일(range 아닐 때, 유효 ISO)
- range도 single도 없으면 당일(today)로 기본 진입
- 패널 창 = [today, today+14d]

SQL/count/render는 일절 건드리지 않는다. measurement 헬퍼 관행대로 flat 모듈로 둔다
(`measurement_dates.py` 등과 동일; subpackage `__init__` 순환 회피).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from datetime import date

from foms.services.request_utils import get_search_query_arg

# 기간 조회 최대 창(일). 3개월(92일)을 초과하는 range는 date_to를 date_from+92일로 clamp.
MEASUREMENT_RANGE_MAX_DAYS = 92


@dataclass(frozen=True)
class MeasurementDashboardFilters:
    """실측 대시보드 라우트가 사용하는 파싱·정규화된 필터 값 묶음."""

    search_q: str
    date_from: str
    date_to: str
    open_map: bool
    use_range: bool
    use_single_day: bool
    selected_date: str
    range_start: date
    range_end: date
    range_start_str: str
    range_end_str: str
    manager_filter: str


def parse_measurement_dashboard_filters(request, today_kst) -> MeasurementDashboardFilters:
    """`erp_measurement_dashboard`의 request.args 파싱·정규화를 동작 보존으로 분리.

    Args:
        request: Flask 요청 객체.
        today_kst: get_today_kst() 결과(라우트와 동일 인스턴스). 기본 날짜·패널 창 기준.

    Returns:
        MeasurementDashboardFilters: 라우트가 그대로 쓰는 정규화 필터 값.
    """
    today_date = today_kst.strftime('%Y-%m-%d')
    search_q = get_search_query_arg('q', 'search', 'manager')
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    req_date = (request.args.get('date') or '').strip()
    open_map = request.args.get('open_map') == '1'
    manager_filter = (request.args.get('manager_filter') or '').strip()

    use_range = bool(date_from and date_to)
    if use_range:
        try:
            _df = datetime.datetime.strptime(date_from, '%Y-%m-%d').date()
            _dt = datetime.datetime.strptime(date_to, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            use_range = False
        else:
            # 기간 최대 3개월(92일) 캡: 초과분은 date_to를 date_from+92일로 clamp.
            _max_dt = _df + datetime.timedelta(days=MEASUREMENT_RANGE_MAX_DAYS)
            if _dt > _max_dt:
                date_to = _max_dt.strftime('%Y-%m-%d')
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

    range_start = today_kst
    range_end = today_kst + datetime.timedelta(days=14)
    range_start_str = range_start.strftime('%Y-%m-%d')
    range_end_str = range_end.strftime('%Y-%m-%d')

    return MeasurementDashboardFilters(
        search_q=search_q,
        date_from=date_from,
        date_to=date_to,
        open_map=open_map,
        use_range=use_range,
        use_single_day=use_single_day,
        selected_date=selected_date,
        range_start=range_start,
        range_end=range_end,
        range_start_str=range_start_str,
        range_end_str=range_end_str,
        manager_filter=manager_filter,
    )

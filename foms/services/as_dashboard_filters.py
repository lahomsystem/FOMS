"""ERP AS 대시보드 요청 파라미터 파서 (Batch 5 AS 구조-추출, 동작 보존).

`erp_as_dashboard()` 라우트 상단의 request.args 파싱·정규화를 분리한다.
값·검증 규칙은 기존 라우트와 1:1 동일:
- status 필터(.strip())
- q/search/manager alias 검색어
- date(원본 그대로, None 가능)
- open_map 플래그
- tab 화이트리스트(incomplete/completed/sales_delivery, 그 외 incomplete)

쿼리/리다이렉트/카운트/렌더는 일절 건드리지 않는다. flat 모듈(subpackage 순환 회피).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from foms.services.request_utils import get_search_query_arg


@dataclass(frozen=True)
class AsDashboardFilters:
    """AS 대시보드 라우트가 사용하는 파싱·정규화된 상단 필터 값 묶음."""

    status_filter: str
    search_q: str
    selected_date: Optional[str]
    open_map: bool
    tab: str


def parse_as_dashboard_filters(request) -> AsDashboardFilters:
    """`erp_as_dashboard` 상단 request.args 파싱·정규화를 동작 보존으로 분리.

    Args:
        request: Flask 요청 객체.

    Returns:
        AsDashboardFilters: 라우트가 그대로 쓰는 정규화 필터 값.
    """
    status_filter = (request.args.get('status') or '').strip()
    search_q = get_search_query_arg('q', 'search', 'manager')
    selected_date = request.args.get('date')
    open_map = request.args.get('open_map') == '1'
    tab = (request.args.get('tab') or 'incomplete').strip()

    if tab not in ('incomplete', 'completed', 'sales_delivery'):
        tab = 'incomplete'

    return AsDashboardFilters(
        status_filter=status_filter,
        search_q=search_q,
        selected_date=selected_date,
        open_map=open_map,
        tab=tab,
    )

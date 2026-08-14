"""ERP 생산 대시보드 요청 파라미터 파서 (Batch 4 production 구조-추출, 동작 보존).

`erp_production_dashboard()` 상단/중간의 request.args 파싱·정규화를 분리한다.
값·검증 규칙은 기존 라우트와 1:1 동일:
- stage 필터(.strip())
- q/search alias 검색어
- erp_mine_only(공용 mine 판정)
- focus_order int(실패 시 None) — 검색 카드 딥링크
- page int(기본 1) — 번호 페이저

쿼리/KPI/pagination/render는 일절 건드리지 않는다. flat 모듈(subpackage 순환 회피).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from foms.services.request_utils import get_search_query_arg
from foms.services.common.erp_mine_filter import erp_mine_only_from_request


@dataclass(frozen=True)
class ProductionDashboardFilters:
    """생산 대시보드 라우트가 사용하는 파싱·정규화된 요청 값 묶음."""

    stage: str
    q: str
    erp_mine_only: bool
    focus_order_id: Optional[int]
    page: int
    # 실측일/시공일 컬럼 헤더 정렬. ''(기본)이면 기존 시공일 빠른 순 정렬을 유지한다.
    sort: str = ''
    sort_dir: str = 'asc'


def parse_production_dashboard_filters(request) -> ProductionDashboardFilters:
    """`erp_production_dashboard` request.args 파싱·정규화를 동작 보존으로 분리.

    Args:
        request: Flask 요청 객체.

    Returns:
        ProductionDashboardFilters: 라우트가 그대로 쓰는 정규화 요청 값.
    """
    f_stage = (request.args.get('stage') or '').strip()
    f_q = get_search_query_arg('q', 'search')
    erp_mine_only = erp_mine_only_from_request(request)
    focus_order_id = request.args.get('focus_order', type=int)
    page = request.args.get('page', 1, type=int)
    # 컬럼 헤더 정렬(실측일/시공일). 화이트리스트 밖이면 기본 정렬로 되돌린다.
    f_sort = (request.args.get('sort') or '').strip()
    if f_sort not in ('measure_date', 'construction_date'):
        f_sort = ''
    f_sort_dir = (request.args.get('dir') or 'asc').strip().lower()
    if f_sort_dir not in ('asc', 'desc'):
        f_sort_dir = 'asc'

    return ProductionDashboardFilters(
        stage=f_stage,
        q=f_q,
        erp_mine_only=erp_mine_only,
        focus_order_id=focus_order_id,
        page=page,
        sort=f_sort,
        sort_dir=f_sort_dir,
    )

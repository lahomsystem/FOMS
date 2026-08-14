"""ERP 시공 대시보드 요청 파라미터 파서 (Batch 4 construction 구조-추출, 동작 보존).

`erp_construction_dashboard()` 상단의 request.args 파싱·정규화를 분리한다.
값·검증 규칙은 기존 라우트와 1:1 동일:
- stage 필터(.strip())
- q/search alias 검색어
- focus_order int(실패 시 None)
- is_construction(시공팀; current_user and team=='CONSTRUCTION' → None/bool 원본 보존)
- mine_only(시공팀 또는 mine=1)

쿼리/KPI/pagination/render는 일절 건드리지 않는다. flat 모듈(subpackage 순환 회피).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from foms.services.request_utils import get_search_query_arg
from foms.services.common.erp_mine_filter import erp_mine_only_for_construction


@dataclass(frozen=True)
class ConstructionDashboardFilters:
    """시공 대시보드 라우트가 사용하는 파싱·정규화된 상단 필터 값 묶음."""

    stage: str
    q: str
    focus_order_id: Optional[int]
    is_construction: object  # 원본 보존: user and (team=='CONSTRUCTION') → None/bool
    mine_only: bool
    # 실측일/시공일 컬럼 헤더 정렬. ''(기본)이면 기존 접수 최신순을 유지한다.
    sort: str = ''
    sort_dir: str = 'asc'


def parse_construction_dashboard_filters(request, user) -> ConstructionDashboardFilters:
    """`erp_construction_dashboard` 상단 request.args 파싱·정규화를 동작 보존으로 분리.

    Args:
        request: Flask 요청 객체.
        user: 현재 사용자(없을 수 있음). is_construction/mine_only 판정.

    Returns:
        ConstructionDashboardFilters: 라우트가 그대로 쓰는 정규화 필터 값.
    """
    f_stage = (request.args.get("stage") or "").strip()
    f_q = get_search_query_arg("q", "search")
    focus_order_id = request.args.get("focus_order", type=int)
    is_construction = user and getattr(user, "team", None) == "CONSTRUCTION"
    mine_only = erp_mine_only_for_construction(request, user)

    # 컬럼 헤더 정렬(실측일/시공일). 화이트리스트 밖이면 기본 정렬로 되돌린다.
    f_sort = (request.args.get("sort") or "").strip()
    if f_sort not in ("measure_date", "construction_date"):
        f_sort = ""
    f_sort_dir = (request.args.get("dir") or "asc").strip().lower()
    if f_sort_dir not in ("asc", "desc"):
        f_sort_dir = "asc"

    return ConstructionDashboardFilters(
        stage=f_stage,
        q=f_q,
        focus_order_id=focus_order_id,
        is_construction=is_construction,
        mine_only=mine_only,
        sort=f_sort,
        sort_dir=f_sort_dir,
    )

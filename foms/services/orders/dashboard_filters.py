"""ERP 주문 대시보드 요청 파라미터 파서 (Batch 2a 구조-추출, 동작 보존).

`erp_dashboard()` 라우트의 `request.args` 파싱/정규화 책임만 분리한다.
값·검증 규칙은 기존 라우트와 1:1 동일:
- 레거시 호환 `MEASURED` -> `MEASURE`
- `sort` 화이트리스트(`latest`/`schedule`/`amount`, 그 외 `latest`)
- `date` ISO 유효성(`fromisoformat` 실패 시 무시)
- `risk` 키 화이트리스트(`RISK_KEYS` 밖이면 무시)
- `focus_order` int 파싱(실패 시 None)
- `effective_stage = '' if q else stage`

SQL/count/cache/render는 일절 건드리지 않는다.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional

from foms.services.request_utils import get_search_query_arg
from foms.services.orders.dashboard_control_tower import RISK_KEYS
from foms.services.common.erp_mine_filter import (
    erp_mine_only_from_request,
    erp_tower_mine_from_request,
)


@dataclass(frozen=True)
class OrdersDashboardFilters:
    """대시보드 라우트가 사용하는 파싱·정규화된 필터 값 묶음."""

    stage: str
    urgent: str
    has_alert: str
    alert_type: str
    q: str
    effective_stage: str
    team: str
    sort: str
    today: str
    tower_mine: bool
    mine: bool
    date: str
    field: str
    risk: str
    focus_order_id: Optional[int]


def parse_orders_dashboard_filters(request) -> OrdersDashboardFilters:
    """`erp_dashboard` 라우트의 request.args 파싱을 동작 보존으로 분리한다.

    Args:
        request: Flask 요청 객체(라우트의 전역 request와 동일 인스턴스).

    Returns:
        OrdersDashboardFilters: 라우트가 그대로 쓰는 정규화 필터 값.
    """
    f_stage = (request.args.get('stage') or '').strip()
    # 레거시 호환: MEASURED -> MEASURE
    if f_stage == 'MEASURED':
        f_stage = 'MEASURE'
    f_urgent = (request.args.get('urgent') or '').strip()
    f_has_alert = (request.args.get('has_alert') or '').strip()
    f_alert_type = (request.args.get('alert_type') or '').strip()
    f_q = get_search_query_arg('q', 'search')
    effective_stage = '' if f_q else f_stage
    f_team = (request.args.get('team') or '').strip()
    f_sort = (request.args.get('sort') or 'latest').strip()
    if f_sort not in ('latest', 'schedule', 'amount'):
        f_sort = 'latest'
    f_today = (request.args.get('today') or '').strip()
    # 내작업 토글(타워 전용): drill을 발동시키지 않고 타워 페이로드만 내 담당분으로 축소.
    f_tower_mine = erp_tower_mine_from_request(request)
    f_mine = erp_mine_only_from_request(request)
    # 주간 타일/현장 탭 deep-link: 특정 날짜(+선택 타입) 큐. 유효한 ISO일 때만.
    f_date = (request.args.get('date') or '').strip()
    f_field = (request.args.get('field') or '').strip()
    if f_date:
        try:
            datetime.date.fromisoformat(f_date)
        except ValueError:
            f_date = ''
    # 위험 레이더 드릴다운: 카드와 동일 술어의 정확 order-id 집합으로 착지(SSOT).
    f_risk = (request.args.get('risk') or '').strip()
    if f_risk not in RISK_KEYS:
        f_risk = ''
    # 검색 카드 딥링크(?focus_order=)는 단건 PK를 60일 창·페이지·술어와 무관하게 강제 착지.
    focus_order_id = request.args.get('focus_order', type=int)

    return OrdersDashboardFilters(
        stage=f_stage,
        urgent=f_urgent,
        has_alert=f_has_alert,
        alert_type=f_alert_type,
        q=f_q,
        effective_stage=effective_stage,
        team=f_team,
        sort=f_sort,
        today=f_today,
        tower_mine=f_tower_mine,
        mine=f_mine,
        date=f_date,
        field=f_field,
        risk=f_risk,
        focus_order_id=focus_order_id,
    )

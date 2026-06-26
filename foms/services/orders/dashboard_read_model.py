"""ERP 주문 대시보드 read-model 쿼리 빌드 (Batch 2a-2 구조-추출, 동작 보존).

`erp_dashboard()` 라우트의 SQL 필터·정렬·`_q_stats` 분기 빌드를 분리한다.
필터 적용 순서, `_q_stats` 복제 시점(f_stage/f_urgent 적용 전), 정렬 규칙,
today 재계산 타이밍을 원본과 1:1 동일하게 유지한다. count/pagination/cache/DTO는
여전히 라우트가 담당한다(한 PR 한 경계).
"""
from __future__ import annotations

import datetime

from sqlalchemy import or_, false

from models import Order
from foms.services.erp_display import get_today_kst
from foms.services.erp_policy import (
    STAGE_NAME_TO_CODE,
    STAGE_SQL_FILTER_MAP,
    STAGES_REQUIRING_TEAM,
)
from foms.services.erp_dashboard_search import erp_order_dashboard_search_predicate
from foms.services.orders.dashboard_control_tower import build_risk_order_ids
from foms.services.orders.dashboard_filters import OrdersDashboardFilters


def build_orders_dashboard_queries(db, current_user, is_admin: bool, filters: OrdersDashboardFilters):
    """대시보드 base/stats 쿼리를 동작 보존으로 빌드한다.

    Args:
        db: 요청 스코프 DB 세션.
        current_user: 현재 사용자(없을 수 있음).
        is_admin: 관리자 여부(팀 필터 분기).
        filters: parse_orders_dashboard_filters 결과.

    Returns:
        (base_query, stats_query, today_date, today_iso)
        - base_query(`_q`): 페이지/카운트용 최종 필터·정렬 적용 쿼리.
        - stats_query(`_q_stats`): f_stage/f_urgent 적용 전 집계용(order_by 제거) 쿼리.
        - today_date, today_iso: 라우트 다운스트림(payload date 등) 호환용.
    """
    # Phase H: 대시보드 운영 화면은 최근 활성 데이터만 조회 (과거 완료건 제외)
    _q = db.query(Order).filter(Order.dashboard_active_filter(days=60), Order.is_erp_order.is_(True))

    if filters.q:
        search_term = f"%{filters.q}%"
        _q = _q.filter(
            erp_order_dashboard_search_predicate(
                search_term,
                include_structured_data_blob=False,
                customer_contact_only=True,
            )
        )

    if filters.mine and current_user:
        # lazy import: erp_permissions canonical path (namespace 계약 + circular 회피, 원본 패턴 유지)
        from foms.services.erp_permissions import build_mine_sql_filter
        mine_conds = build_mine_sql_filter(current_user)
        if mine_conds:
            _q = _q.filter(or_(*mine_conds))

    today_date = get_today_kst()
    today_iso = today_date.isoformat()
    if filters.today == '1':
        _q = _q.filter(
            or_(
                Order.erp_measurement_date == today_iso,
                Order.erp_construction_date == today_iso,
            )
        )

    # 특정 날짜 현장 큐 (주간 타일/현장 탭 '그날 전체'). field로 실측/시공 한정.
    if filters.date:
        if filters.field == 'measure':
            _q = _q.filter(Order.erp_measurement_date == filters.date)
        elif filters.field == 'construction':
            _q = _q.filter(Order.erp_construction_date == filters.date)
        else:
            _q = _q.filter(
                or_(
                    Order.erp_measurement_date == filters.date,
                    Order.erp_construction_date == filters.date,
                )
            )

    # 위험 레이더 드릴다운: 카드와 동일 술어의 정확 id 집합으로 스코프.
    # _q_stats 복제 이전에 적용 → 칩·리스트·total이 모두 같은 집합(SSOT). 빈 집합이면 정상 0건.
    if filters.risk:
        _risk_ids = build_risk_order_ids(db, current_user, filters.risk)
        _q = _q.filter(Order.id.in_(_risk_ids))

    # C. f_team SQL 필터
    if filters.team and not is_admin:
        team_stages = STAGES_REQUIRING_TEAM.get(filters.team)
        if team_stages is not None:
            if not team_stages:
                _q = _q.filter(false())
            else:
                # Phase D: 플랫 컬럼 사용 (따옴표 제거된 정규화 코드 배열로 변환)
                flat_target_stages = [s.strip('"\'') for s in team_stages]
                _q = _q.filter(Order.erp_stage_code.in_(flat_target_stages))

    # --- 분기 시점: 집계용 base query 복제 (f_stage, f_urgent 적용 전) ---
    _q_stats = _q.order_by(None)

    # A-1. f_stage SQL 필터
    if filters.effective_stage:
        target_stages = STAGE_SQL_FILTER_MAP.get(filters.effective_stage, [])
        if target_stages:
            flat_target_stages = [s.strip('"\'') for s in target_stages]
            _q = _q.filter(Order.erp_stage_code.in_(flat_target_stages))

    # A-2. f_urgent SQL 필터
    if filters.urgent == '1':
        _q = _q.filter(Order.erp_urgent == True)

    # B-4. D-day SQL 후보군 필터 (1차)
    if filters.alert_type in ('measurement_d4', 'construction_d3', 'production_d2', 'drawing_overdue'):
        today_date = get_today_kst()

        if filters.alert_type == 'drawing_overdue':
            drawing_cutoff = datetime.datetime.now() - datetime.timedelta(hours=48)
            _q = _q.filter(
                Order.erp_stage_code.in_(['DRAWING', 'CONFIRM']),
                Order.erp_stage_updated_at.isnot(None),
                Order.erp_stage_updated_at <= drawing_cutoff,
            )
        elif filters.alert_type == 'measurement_d4':
            cutoff = (today_date + datetime.timedelta(days=12)).isoformat()
            _q = _q.filter(
                Order.erp_measurement_date.isnot(None),
                Order.erp_measurement_date >= today_date.isoformat(),
                Order.erp_measurement_date <= cutoff
            )
        elif filters.alert_type == 'construction_d3':
            cutoff = (today_date + datetime.timedelta(days=10)).isoformat()
            _q = _q.filter(
                Order.erp_construction_date.isnot(None),
                Order.erp_construction_date >= today_date.isoformat(),
                Order.erp_construction_date <= cutoff
            )
        elif filters.alert_type == 'production_d2':
            cutoff = (today_date + datetime.timedelta(days=8)).isoformat()
            _q = _q.filter(
                Order.erp_construction_date.isnot(None),
                Order.erp_construction_date >= today_date.isoformat(),
                Order.erp_construction_date <= cutoff,
                Order.erp_stage_code != 'CONSTRUCTION'
            )

    if filters.today == '1':
        today_iso = get_today_kst().isoformat()
        _q = _q.filter(
            or_(
                Order.erp_measurement_date == today_iso,
                Order.erp_construction_date == today_iso,
                Order.received_date == today_iso,
            )
        )

    # 순수 DB 정렬: 실측/시공 단계 진입 시 해당 날짜 내림차순 정렬 우선
    if filters.risk:
        # P1 트리아지: 위험 착지는 마감/정체 오름차순(가장 급한 게 위). 페이지 경계도 동일 순서.
        if filters.risk in ('construction_unready', 'balance_due'):
            _q = _q.order_by(Order.erp_construction_date.asc().nullslast(), Order.created_at.desc())
        elif filters.risk == 'measure_unassigned':
            _q = _q.order_by(Order.erp_measurement_date.asc().nullslast(), Order.created_at.desc())
        elif filters.risk == 'drawing_stalled':
            _q = _q.order_by(Order.erp_stage_updated_at.asc().nullslast(), Order.created_at.desc())
        else:
            _q = _q.order_by(Order.created_at.desc())
    elif filters.effective_stage:
        _req_code = STAGE_NAME_TO_CODE.get(filters.effective_stage, filters.effective_stage)
        if _req_code == 'MEASURE':
            _q = _q.order_by(Order.erp_measurement_date.desc().nullslast(), Order.created_at.desc())
        elif _req_code == 'CONSTRUCTION':
            _q = _q.order_by(Order.erp_construction_date.desc().nullslast(), Order.created_at.desc())
        else:
            _q = _q.order_by(Order.created_at.desc())
    else:
        _q = _q.order_by(Order.created_at.desc())

    return _q, _q_stats, today_date, today_iso

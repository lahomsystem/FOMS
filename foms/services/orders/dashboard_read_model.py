"""ERP 주문 대시보드 read-model 쿼리 빌드 (Batch 2a-2 구조-추출, 동작 보존).

`erp_dashboard()` 라우트의 SQL 필터·정렬·`_q_stats` 분기 빌드를 분리한다.
필터 적용 순서, `_q_stats` 복제 시점(f_stage/f_urgent 적용 전), 정렬 규칙,
today 재계산 타이밍을 원본과 1:1 동일하게 유지한다. count/pagination/cache/DTO는
여전히 라우트가 담당한다(한 PR 한 경계).
"""
from __future__ import annotations

import datetime

from sqlalchemy import or_, false, and_, func, case as sql_case
from sqlalchemy.orm import aliased

from models import Order, OrderScheduleDate, User
from foms.services.erp_display import get_today_kst, _erp_get_stage
from foms.services.datetime_kst import now_utc_naive
from foms.services.common.business_calendar import business_days_until
from foms.services.erp_policy import (
    STAGE_NAME_TO_CODE,
    STAGE_SQL_FILTER_MAP,
    STAGES_REQUIRING_TEAM,
)
from foms.services.erp_dashboard_search import erp_order_dashboard_search_predicate
from foms.services.orders.dashboard_control_tower import build_risk_order_ids
from foms.services.orders.dashboard_filters import OrdersDashboardFilters
from foms.services.shipment_dashboard_helpers import AS_SHIPMENT_STATUSES


def _as_visit_order_id_query(db, date_iso: str):
    as_order = aliased(Order)
    return (
        db.query(OrderScheduleDate.order_id)
        .join(as_order, as_order.id == OrderScheduleDate.order_id)
        .filter(
            as_order.status.in_(AS_SHIPMENT_STATUSES),
            OrderScheduleDate.kind == "as_visit",
            OrderScheduleDate.date == date_iso,
        )
    )


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
        as_visit_ids = _as_visit_order_id_query(db, today_iso)
        _q = _q.filter(
            or_(
                Order.erp_measurement_date == today_iso,
                Order.erp_construction_date == today_iso,
                Order.id.in_(as_visit_ids),
            )
        )

    # 특정 날짜 현장 큐 (주간 타일/현장 탭 '그날 전체'). field로 실측/시공/AS 한정.
    if filters.date:
        if filters.field == 'measure':
            _q = _q.filter(Order.erp_measurement_date == filters.date)
        elif filters.field == 'construction':
            _q = _q.filter(Order.erp_construction_date == filters.date)
        elif filters.field == 'as':
            _q = _q.filter(Order.id.in_(_as_visit_order_id_query(db, filters.date)))
        else:
            as_visit_ids = _as_visit_order_id_query(db, filters.date)
            _q = _q.filter(
                or_(
                    Order.erp_measurement_date == filters.date,
                    Order.erp_construction_date == filters.date,
                    Order.id.in_(as_visit_ids),
                )
            )

    # 위험 레이더 드릴다운: 카드와 동일 술어의 정확 id 집합으로 스코프.
    # _q_stats 복제 이전에 적용 → 칩·리스트·total이 모두 같은 집합(SSOT). 빈 집합이면 정상 0건.
    if filters.risk:
        _risk_ids = build_risk_order_ids(db, current_user, filters.risk)
        _q = _q.filter(Order.id.in_(_risk_ids))

    # v3→v2 이식(A4): CS 접수 상태 칩 필터(전체/보류/재확인). risk와 동일하게
    # _q_stats 복제 이전 적용 → 리스트·total·칩 카운트가 모두 같은 집합(SSOT).
    if filters.status:
        _q = _q.filter(Order.status == filters.status)

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
            drawing_cutoff = now_utc_naive() - datetime.timedelta(hours=48)
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
        as_visit_ids = _as_visit_order_id_query(db, today_iso)
        _q = _q.filter(
            or_(
                Order.erp_measurement_date == today_iso,
                Order.erp_construction_date == today_iso,
                Order.received_date == today_iso,
                Order.id.in_(as_visit_ids),
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


def _business_alert_date_values(
    today_date: datetime.date,
    *,
    max_business_days: int,
    calendar_window_days: int,
) -> list[str]:
    """Return date strings matching the existing business-day alert rule."""
    values: list[str] = []
    for offset in range(calendar_window_days + 1):
        value = today_date + datetime.timedelta(days=offset)
        days_until = business_days_until(value.isoformat(), today=today_date)
        if days_until is not None and 0 <= days_until <= max_business_days:
            values.append(value.isoformat())
    return values


def compute_orders_summary_slice(stats_query):
    """주문 대시보드 summary(KPIs/process_steps) 집계 (구 _compute_orders_summary_slice).

    Batch 2a-3: 라우트 캐시 슬라이스 compute closure를 read-model로 분리(동작 보존).
    cache 키·fingerprint·get_or_compute는 라우트가 유지하고, 이 함수는 캐시 미스 시
    `stats_query`(=_q_stats, f_stage/f_urgent 적용 전 집계용)로 동일 결과를 산출한다.

    Args:
        stats_query: order_by 제거된 집계용 base query(_q_stats).

    Returns:
        {"kpis": {...}, "process_steps": [...]} — 원본 closure와 동일 형태.
    """
    kpis = {'urgent_count': 0, 'measurement_d4_count': 0, 'construction_d3_count': 0, 'production_d2_count': 0, 'drawing_overdue_count': 0, 'today_count': 0}
    step_stats = {k: {'count': 0, 'overdue': 0, 'imminent': 0} for k in [
        '주문접수', '실측', '도면', '고객컨펌', '생산', '시공', 'CS', '완료', 'AS처리'
    ]}

    # Phase D: 플랫 컬럼을 활용한 집계 (NULL은 주문접수로 기본 분류)
    stage_bucket_expr = sql_case(
        (Order.erp_stage_code.is_(None), '주문접수'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('주문접수', [])]), '주문접수'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('실측', [])]), '실측'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('도면', [])]), '도면'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('고객컨펌', [])]), '고객컨펌'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('생산', [])]), '생산'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('시공', [])]), '시공'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('CS', [])]), 'CS'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('완료', [])]), '완료'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('AS처리', [])]), 'AS처리'),
        else_='기타'
    )

    today_date = get_today_kst()
    today_iso = today_date.isoformat()
    measurement_d4_dates = _business_alert_date_values(
        today_date,
        max_business_days=4,
        calendar_window_days=12,
    )
    construction_d3_dates = _business_alert_date_values(
        today_date,
        max_business_days=3,
        calendar_window_days=10,
    )
    production_d2_dates = _business_alert_date_values(
        today_date,
        max_business_days=2,
        calendar_window_days=10,
    )
    production_d2_filter = and_(
        Order.erp_construction_date.in_(production_d2_dates),
        or_(Order.erp_stage_code.is_(None), Order.erp_stage_code != 'CONSTRUCTION'),
    )
    imminent_filter = or_(
        Order.erp_measurement_date.in_(measurement_d4_dates),
        Order.erp_construction_date.in_(construction_d3_dates),
        production_d2_filter,
    )

    drawing_overdue_cutoff = now_utc_naive() - datetime.timedelta(hours=48)
    drawing_overdue_filter = and_(
        Order.erp_stage_code.in_(['DRAWING', 'CONFIRM']),
        Order.erp_stage_updated_at.isnot(None),
        Order.erp_stage_updated_at <= drawing_overdue_cutoff,
    )

    summary_rows = (
        stats_query
        .with_entities(
            stage_bucket_expr.label('bucket'),
            func.count(Order.id).label('cnt'),
            func.coalesce(func.sum(sql_case((Order.erp_urgent == True, 1), else_=0)), 0).label('urgent_cnt'),
            func.coalesce(func.sum(sql_case((Order.erp_measurement_date.in_(measurement_d4_dates), 1), else_=0)), 0).label('measurement_d4_cnt'),
            func.coalesce(func.sum(sql_case((Order.erp_construction_date.in_(construction_d3_dates), 1), else_=0)), 0).label('construction_d3_cnt'),
            func.coalesce(func.sum(sql_case((production_d2_filter, 1), else_=0)), 0).label('production_d2_cnt'),
            func.coalesce(func.sum(sql_case((imminent_filter, 1), else_=0)), 0).label('imminent_cnt'),
            func.coalesce(func.sum(sql_case((drawing_overdue_filter, 1), else_=0)), 0).label('overdue_cnt'),
        )
        .group_by(stage_bucket_expr)
        .all()
    )
    kpis['today_count'] = (
        stats_query.filter(
            or_(
                Order.erp_measurement_date == today_iso,
                Order.erp_construction_date == today_iso,
            )
        ).count()
    )
    for row in summary_rows:
        kpis['urgent_count'] += int(row.urgent_cnt or 0)
        kpis['measurement_d4_count'] += int(row.measurement_d4_cnt or 0)
        kpis['construction_d3_count'] += int(row.construction_d3_cnt or 0)
        kpis['production_d2_count'] += int(row.production_d2_cnt or 0)
        # 도면 지연(drawing_overdue) 전체 합계 — overdue_cnt 는 이미 summary_rows 집계에
        # 존재(step_stats['overdue'] 와 동일 소스). DRAWING/CONFIRM 버킷만 비영(0)이라 전 버킷
        # 합산이 곧 전체 도면 지연 건수(신규 쿼리 없음, urgent_count 등과 동일 패턴).
        kpis['drawing_overdue_count'] += int(row.overdue_cnt or 0)
        if row.bucket in step_stats:
            step_stats[row.bucket]['count'] = int(row.cnt or 0)
            step_stats[row.bucket]['imminent'] = int(row.imminent_cnt or 0)
            step_stats[row.bucket]['overdue'] = int(row.overdue_cnt or 0)

    process_steps = [
        {'label': '주문접수', **step_stats['주문접수']},
        {'label': '실측', **step_stats['실측']},
        {'label': '도면', **step_stats['도면']},
        {'label': '고객컨펌', **step_stats['고객컨펌']},
        {'label': '생산', **step_stats['생산']},
        {'label': '시공', **step_stats['시공']},
        {'label': '완료', **step_stats['완료']},
        {'label': 'CS', **step_stats['CS']},
        {'label': 'AS처리', **step_stats['AS처리']},
    ]
    return {"kpis": kpis, "process_steps": process_steps}


def compute_orders_attachment_assignee_maps(db, page_orders, page_sds):
    """주문 대시보드 첨부 수/담당자 맵 (구 _compute_orders_attachment_assignee_maps).

    Batch 2a-4: 라우트 캐시 슬라이스 compute closure를 read-model로 분리(동작 보존).
    cache 키·fingerprint·get_or_compute는 라우트가 유지하고, 이 함수는 캐시 미스 시
    현재 페이지(page_orders, 50건)에 대해 att_counts/user_map을 동일하게 산출한다.

    Args:
        db: 요청 스코프 DB 세션.
        page_orders: 현재 페이지 Order 객체 리스트(표시용 50건).
        page_sds: order_id -> structured_data dict 맵.

    Returns:
        {"att_counts": {str(order_id): cnt}, "user_map": {str(user_id): name}}
        — JSON 직렬화 호환을 위해 키는 str(원본과 동일).
    """
    # att_counts: 50건만 배치 조회 (원래 1000건 → 50건)
    att_counts: dict[int, int] = {}
    if page_orders:
        try:
            from models import OrderAttachment
            from sqlalchemy import func
            order_ids = [o.id for o in page_orders]
            rows = db.query(OrderAttachment.order_id, func.count(OrderAttachment.id).label('cnt')) \
                     .filter(OrderAttachment.order_id.in_(order_ids)) \
                     .group_by(OrderAttachment.order_id).all()
            for r in rows:
                att_counts[int(r.order_id)] = int(r.cnt)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("att_counts query failed: %s", e)
            att_counts = {}

    # user_map: 50건 assignee만 조회 (원래 1000건 전체 → 50건으로 절감)
    all_assignee_ids: set[int] = set()
    for o in page_orders:
        sd = page_sds[o.id]
        stage = _erp_get_stage(o, sd)
        stage_key = stage if isinstance(stage, str) else ''
        stage_code = STAGE_NAME_TO_CODE.get(stage_key, stage_key)
        if stage_code in ('MEASURE', 'DRAWING', 'CONFIRM'):
            assignments = sd.get('assignments') or {}
            if stage_code in ('MEASURE', 'CONFIRM'):
                uids = assignments.get('sales_assignee_user_ids') or []
            else:
                uids = assignments.get('drawing_assignee_user_ids') or []
                if not uids:
                    for a in ((assignments.get('drawing_assignees') or []) + (sd.get('drawing_assignees') or [])):
                        if isinstance(a, dict) and a.get('id'):
                            uids.append(a['id'])
            for uid in uids:
                try:
                    all_assignee_ids.add(int(uid))
                except (TypeError, ValueError):
                    pass
    user_map: dict[int, str] = {}
    if all_assignee_ids:
        users = db.query(User).filter(User.id.in_(all_assignee_ids)).all()  # perf-ok: assignee id.in_ from dashboard page
        for u in users:
            user_id = getattr(u, 'id', None)
            user_name = getattr(u, 'name', None)
            if isinstance(user_id, int) and isinstance(user_name, str) and user_name:
                user_map[user_id] = user_name
    # JSON 키는 str — 역직렬화 후 int 복원
    return {
        "att_counts": {str(k): v for k, v in att_counts.items()},
        "user_map": {str(k): v for k, v in user_map.items()},
    }

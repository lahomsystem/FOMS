"""ERP 생산 대시보드 read-model (Batch 4 production 구조-추출, 동작 보존).

`erp_production_dashboard()`의 SQL 쿼리 빌드·단계 버킷 카운트·KPI/프로세스맵 배지 집계·
첨부 카운트·페이지네이션을 분리한다. 필터 적용 순서, 전체셋 KPI 스캔(의도적; 페이지 50건과
무관, 성능 최적화는 별도 웨이브), 정렬/페이지 규칙을 원본과 1:1 동일하게 유지한다.
row DTO 조립/표시는 production_dashboard_display가 담당한다(한 슬라이스 한 경계).
flat 모듈(subpackage __init__ 순환 회피).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import (
    String, and_, bindparam, case as sql_case, cast, exists, func, or_, text,
)
from sqlalchemy.orm import Query

from models import Order, ProductionRun
from foms.services.erp_display import _ensure_dict, _erp_alerts, _erp_get_stage

PRODUCTION_DASHBOARD_PAGE_SIZE = 50
# 태블릿 칸반은 페이지 윈도가 아닌 정렬 전량을 렌더한다(시공일 변경 카드 소실 회귀 방지).
# 이 캡을 넘으면 상위 N건만 렌더하고 kanban_capped 로 노출(silent 축소 금지).
PRODUCTION_KANBAN_MAX_ROWS = 300

# 버킷 축 = 단계 + current production run(2026-09-17 CONFIRM→PRODUCTION 재설계).
#   제작대기 = CONFIRM(호환) 또는 PRODUCTION 이면서 current run 없음
#   제작중   = PRODUCTION 이면서 current run 있음
#   제작완료 = CONSTRUCTION
_BUCKET_WAIT_STAGES = ['고객컨펌', 'CONFIRM']
_BUCKET_PROD_STAGES = ['생산', 'PRODUCTION']
_BUCKET_DONE_STAGES = ['시공', 'CONSTRUCTION']


def current_production_run_exists() -> Any:
    """``Order`` 에 상관된 EXISTS(current production run) SQL 식.

    ``production_runs`` 부분 유니크 ``uq_production_run_current``(``order_id`` WHERE
    ``is_current``, models.py ProductionRun)를 탐침해 주문당 최대 1행만 본다. JSONB 는
    SQL 에 넣지 않는다(인덱스 보존 — perf-gate 대상 쿼리).
    """
    return exists().where(
        ProductionRun.order_id == Order.id, ProductionRun.is_current.is_(True)
    ).correlate(Order)


def build_production_orders_query(
    db: Any,
    user: Any,
    f_stage: str,
    f_q: str,
    erp_mine_only: bool,
) -> Query:
    """필터를 적용한 생산 대시보드용 ERP Order 쿼리(정렬 전).

    단계 필터는 flat 컬럼 ``Order.erp_stage_code``(index=True)를 직접 참조한다.
    JSONB path cast(``structured_data['workflow']['stage']``, 인덱스 없음)를 제거해
    ``ix_orders_erp_stage_code`` 인덱스 스캔으로 전환한다. erp_stage_code는
    workflow.stage 원문 그대로(JSON 따옴표 없음)이므로 IN 목록은 따옴표를 붙이지 않는다.
    한글 값(고객컨펌/생산/시공)은 운영에 없으나 sync가 원문 복사라 미래 방어로 유지(비용 0).
    """
    _q = db.query(Order).filter(Order.active_filter(), Order.is_erp_order.is_(True))
    base_stages = ['고객컨펌', '생산', '시공', 'CONFIRM', 'PRODUCTION', 'CONSTRUCTION']
    _q = _q.filter(Order.erp_stage_code.in_(base_stages))

    if f_stage:
        run = current_production_run_exists()
        if f_stage == '제작대기':
            _q = _q.filter(or_(
                Order.erp_stage_code.in_(_BUCKET_WAIT_STAGES),
                and_(Order.erp_stage_code.in_(_BUCKET_PROD_STAGES), ~run),
            ))
        elif f_stage == '제작중':
            _q = _q.filter(and_(Order.erp_stage_code.in_(_BUCKET_PROD_STAGES), run))
        elif f_stage == '제작완료':
            _q = _q.filter(Order.erp_stage_code.in_(_BUCKET_DONE_STAGES))

    if f_q:
        search_term = f"%{f_q}%"
        _q = _q.filter(
            or_(
                Order.customer_name.ilike(search_term),  # perf-ok: ix_orders_customer_name_trgm
                Order.phone.ilike(search_term),  # perf-ok: ix_orders_phone_trgm
                Order.address.ilike(search_term),  # perf-ok: ix_orders_address_trgm
                cast(Order.structured_data, String).ilike(search_term),  # perf-ok: ix_orders_structured_data_text_trgm
            )
        )

    if erp_mine_only and user:
        # lazy import: erp_permissions canonical path (namespace 계약 + circular 회피, 원본 패턴 유지)
        from foms.services.erp_permissions import build_mine_sql_filter
        conds = build_mine_sql_filter(user)
        if conds:
            _q = _q.filter(or_(*conds))
        else:
            _q = _q.filter(Order.id == -1)

    return _q


def production_stage_bucket_expr() -> Any:
    """DB 단계 + current run → 제작대기/제작중/제작완료 버킷.

    flat 컬럼 ``Order.erp_stage_code``(index=True)와 ``production_runs`` 상관 EXISTS 만
    참조한다(JSONB path 없음 → ``ix_orders_erp_stage_code``·``uq_production_run_current``
    인덱스 보존). PRODUCTION 단계는 current run 이 있어야 제작중이고, 없으면(승인 직후·
    제작 취소 뒤·stage_override 로 놓인 주문) 제작대기다. erp_stage_code는 원문값
    (JSON 따옴표 없음)이므로 IN 목록에도 따옴표를 붙이지 않는다.
    """
    run = current_production_run_exists()
    return sql_case(
        (Order.erp_stage_code.in_(_BUCKET_WAIT_STAGES), '제작대기'),
        # run 분기를 먼저 두어 상관 EXISTS 를 한 번만 평가한다(CEO 판정 P3).
        (and_(Order.erp_stage_code.in_(_BUCKET_PROD_STAGES), run), '제작중'),
        (Order.erp_stage_code.in_(_BUCKET_PROD_STAGES), '제작대기'),
        (Order.erp_stage_code.in_(_BUCKET_DONE_STAGES), '제작완료'),
        else_='기타',
    )


def empty_production_step_stats() -> dict[str, dict[str, int]]:
    return {
        '제작대기': {'count': 0, 'overdue': 0, 'imminent': 0},
        '제작중': {'count': 0, 'overdue': 0, 'imminent': 0},
        '제작완료': {'count': 0, 'overdue': 0, 'imminent': 0},
    }


def fill_production_step_counts(
    _q: Query, stage_bucket_expr: Any, step_stats: dict[str, dict[str, int]]
) -> None:
    """step_stats['*']['count']만 SQL GROUP BY로 채운다."""
    stats_rows = (
        _q.order_by(None)
        .with_entities(stage_bucket_expr.label('bucket'), func.count(Order.id).label('cnt'))
        .group_by(stage_bucket_expr)
        .all()
    )
    for row in stats_rows:
        if row.bucket in step_stats:
            step_stats[row.bucket]['count'] = row.cnt


def _kpi_stage_label_from_erp_stage(stage: str, has_current_run: bool = False) -> str | None:
    """KPI 배지용 버킷 라벨. PRODUCTION 은 current run 유무로 제작대기/제작중을 가른다."""
    if stage not in ('고객컨펌', '생산', '시공', 'CONFIRM', 'PRODUCTION', 'CONSTRUCTION'):
        return None
    if stage in ('CONFIRM', '고객컨펌'):
        return '제작대기'
    if stage in ('PRODUCTION', '생산'):
        return '제작중' if has_current_run else '제작대기'
    if stage in ('CONSTRUCTION', '시공'):
        return '제작완료'
    return None


def compute_production_kpis_and_badges(
    _q: Query, step_stats: dict[str, dict[str, int]]
) -> tuple[list[Any], dict[str, int]]:
    """
    KPI 상단 알림 + 프로세스 맵 배지(임박/지연).

    필터와 동일한 전체 집합을 한 번 스캔한다(의도적; 페이지 50건과 무관).
    성능 최적화는 별도 웨이브에서 다룬다.
    """
    # Batch 4: KPI 전체스캔은 전체 structured_data(대용량 items/parties/quests 포함)를
    # 행마다 로드/파싱했다. KPI 산출은 flags/schedule/workflow 서브트리만 읽으므로
    # (_erp_alerts·_erp_get_stage) 해당 3개 JSON 경로만 투영해 전송·파싱 비용을 줄인다.
    # kpi_rows는 호출부에서 len()(총건수)으로만 쓰여 행 수는 불변. _ensure_dict가
    # dict/JSON문자열 양쪽을 처리해 동작은 byte 동일하게 보존된다.
    sd_json = Order.structured_data
    kpi_rows = _q.order_by(None).with_entities(
        Order.id,
        sd_json['flags'].label('sd_flags'),
        sd_json['schedule'].label('sd_schedule'),
        sd_json['workflow'].label('sd_workflow'),
        current_production_run_exists().label('has_run'),
    ).all()
    kpis = {
        'urgent_count': 0,
        'production_d2_count': 0,
        'measurement_d4_count': 0,
        'construction_d3_count': 0,
    }
    for kpi_row in kpi_rows:
        kpi_sd = {
            'flags': _ensure_dict(kpi_row.sd_flags),
            'schedule': _ensure_dict(kpi_row.sd_schedule),
            'workflow': _ensure_dict(kpi_row.sd_workflow),
        }
        kpi_alerts = _erp_alerts(None, kpi_sd, 0)
        if kpi_alerts.get('urgent'):
            kpis['urgent_count'] += 1
        if kpi_alerts.get('production_d2'):
            kpis['production_d2_count'] += 1
        if kpi_alerts.get('measurement_d4'):
            kpis['measurement_d4_count'] += 1
        if kpi_alerts.get('construction_d3'):
            kpis['construction_d3_count'] += 1

        stage_label = _kpi_stage_label_from_erp_stage(
            _erp_get_stage(None, kpi_sd) or '', bool(kpi_row.has_run)
        )
        if not stage_label or stage_label not in step_stats:
            continue
        if kpi_alerts.get('production_d2'):
            step_stats[stage_label]['imminent'] += 1
        if kpi_alerts.get('drawing_overdue'):
            step_stats[stage_label]['overdue'] += 1

    return kpi_rows, kpis


def compute_production_summary_blob(_q: Query) -> dict[str, Any]:
    """KPI + step_stats + total for micro-cache.

    단계 버킷 집계는 flat 컬럼 erp_stage_code(index=True)를 직접 참조한다
    (production_stage_bucket_expr, JSONB path cast 제거 → ix_orders_erp_stage_code 스캔).
    """
    stage_bucket_expr = production_stage_bucket_expr()
    step_stats = empty_production_step_stats()
    fill_production_step_counts(_q, stage_bucket_expr, step_stats)
    kpi_rows, kpis = compute_production_kpis_and_badges(_q, step_stats)
    return {
        "step_stats": step_stats,
        "kpis": kpis,
        # W3-3 판단(유지): total_orders=len(kpi_rows). compute_production_kpis_and_badges가
        # 뱃지 집계로 rows 전행을 이미 파이썬 루프 순회하므로 별도 _q.count() 쿼리는
        # 이중조회 낭비다. W3-2 전환 후 필터셋이 소량이라 hydrate 비용도 작아 len 유지가 최적.
        "total_orders": len(kpi_rows),
    }


def fetch_production_attachment_counts(db: Any, page_rows: list[Any]) -> dict[int, int]:
    att_counts: dict[int, int] = {}
    if not page_rows:
        return att_counts
    try:
        order_ids = [o.id for o in page_rows]
        # ATTACH-LIFE-01: raw SQL 은 ORM 전역 tombstone 필터를 안 받는다 — 삭제된 첨부가
        # 카운트에 남지 않도록 여기서 명시적으로 제외한다(allowlist 대상, 계약 테스트가 고정).
        stmt = text(
            "SELECT order_id, COUNT(*) AS cnt FROM order_attachments "
            "WHERE order_id = ANY(:order_ids) AND deleted_at IS NULL GROUP BY order_id"
        )
        stmt = stmt.bindparams(bindparam('order_ids', value=order_ids))
        rows = db.execute(stmt).fetchall()
        for r in rows:
            att_counts[int(r.order_id)] = int(r.cnt)
    except Exception as e:
        logging.getLogger(__name__).warning("att_counts query failed: %s", e)
    return att_counts


def fetch_production_current_run_ids(db: Any, page_rows: list[Any]) -> set[int]:
    """행 목록 중 current production run 이 있는 주문 id 집합(쿼리 1회, 캐시 없음).

    행 DTO(``build_production_enriched_rows``)·묘비 버킷이 PRODUCTION 단계를 제작대기/제작중으로
    가르는 데 쓴다. 빈 목록이면 쿼리 없이 빈 set.
    """
    if not page_rows:
        return set()
    ids = [o.id for o in page_rows]
    rows = (
        db.query(ProductionRun.order_id)
        .filter(ProductionRun.order_id.in_(ids), ProductionRun.is_current.is_(True))
        .all()
    )
    return {int(r.order_id) for r in rows}


def paginate_production_rows(
    _q: Query, page_raw: int | None, total_orders: int
) -> tuple[int, int, list[Any]]:
    """페이지 인덱스·총 페이지 수·현재 페이지 행."""
    page = page_raw or 1
    if page < 1:
        page = 1
    per_page = PRODUCTION_DASHBOARD_PAGE_SIZE
    total_pages = (total_orders + per_page - 1) // per_page
    page_rows = _q.offset((page - 1) * per_page).limit(per_page).all()
    return page, total_pages, page_rows

"""실측일 미정 주문 조회 read-model.

실측 대시보드 '실측일 미정' 모달이 쓰는 모집단 술어·행 DTO·API 페이로드 빌더를 모은다.

핵심 규율(어기면 목록이 조용히 빈다):
- **날짜 축은 SQL 로 좁히지 않는다.** '추후통보'/'미정' 같은 텍스트가 실제로 컬럼에 들어 있고
  그 값들은 파이썬 정규화 단계에서만 탈락하므로, SQL 날짜 필터는 이 기능의 목표 집합을
  통째로 지운다. SQL 은 상태·단계 축만 좁히고 최종 판정은 `is_measurement_undated` 가 한다.
- **표시 상한은 파이썬 판정이 전부 끝난 뒤에만 적용한다.** 캡을 먼저 걸고 좁히면
  목록이 통째로 비는 기존 함정을 그대로 반복하게 된다.
- SQL `NOT IN` 은 NULL 을 통과시키지 않는다. status·erp_stage_code 는 비ERP 주문에서
  NULL 이므로 반드시 `or_(col.is_(None), ~col.in_(...))` 형태로 쓴다.

flat 모듈로 둔다(`measurement_dates.py`·`measurement_read_model.py` 와 동일 관행 —
`foms.services.measurement` 서브패키지는 순환 import 위험이 있다).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from flask import url_for
from sqlalchemy import or_
from sqlalchemy.orm import Query, Session, selectinload

from models import Order
from foms.services.erp_dashboard_search import erp_measurement_main_search_predicate
from foms.services.erp_display import (
    _ensure_dict,
    apply_erp_display_fields_to_orders,
    normalize_manager_name,
    self_measurement_four_checks_done,
)
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.erp_permissions import build_mine_sql_filter
from foms.services.erp_policy import STAGE_LABELS, STAGE_NAME_TO_CODE
from foms.services.measurement_dates import extract_all_measurement_dates
from foms.services.measurement_read_model import apply_measurement_dashboard_order_scope
from foms.services.orders.status_constants import STATUS

logger = logging.getLogger(__name__)


# 모집단을 id 내림차순 keyset 으로 훑을 때의 배치 크기(메모리 평탄화 용도).
MEASUREMENT_UNDATED_SCAN_BATCH = 500
# 폭주 방지용 최후 backstop — 정상 운영에서는 도달하지 않는다.
# **정렬 상한이 아니다**: 모집단 전체를 배치로 다 훑고, 이 값을 넘길 때만 중단하며
# 그 사실을 scan_capped 로 노출한다. 예전처럼 `id DESC LIMIT n` 을 파이썬 판정보다
# 먼저 걸면 상한 예산을 '날짜가 이미 있는' 최신 주문이 다 먹어, 정작 목표 집합인
# 오래 방치된 '실측일 미정' 주문이 통째로 사라진다(캡 먼저 → 필터 나중 함정).
MEASUREMENT_UNDATED_SCAN_LIMIT = 50000
# 파이썬 판정이 끝난 뒤 적용하는 표시 상한.
MEASUREMENT_UNDATED_DISPLAY_CAP = 300

# 실측이 이미 끝났거나 종료된 status (진행 중이면 목록에 남긴다).
# 포함(=목록 대상): RECEIVED / MEASURE / SELF_MEASUREMENT / ON_HOLD / NULL / 미지값
_EXCLUDED_STATUS_VALUES: frozenset[str] = frozenset({
    'DRAWING', 'CONFIRM', 'PRODUCTION', 'CONSTRUCTION', 'CS', 'COMPLETED',
    'MEASURED', 'REGIONAL_MEASURED', 'SELF_MEASURED',
    'SCHEDULED', 'SHIPPED_PENDING',
    'AS', 'AS_RECEIVED', 'AS_COMPLETED', 'DELETED',
})

# erp_stage_code 는 workflow.stage 원문 복사라 코드와 한글 라벨이 섞여 들어온다
# (`erp_sync_columns.py`: `order.erp_stage_code = stage if isinstance(stage, str) else None`).
_EXCLUDED_STAGE_CODES: tuple[str, ...] = (
    'DRAWING', 'CONFIRM', 'PRODUCTION', 'CONSTRUCTION', 'CS', 'COMPLETED',
    'AS', 'AS_RECEIVED', 'AS_COMPLETED',
)
# 한글 라벨은 손으로 적지 않고 STAGE_LABELS 에서 파생한다 — 정책 쪽 라벨이 바뀌면
# 이 목록만 낡아 완료 단계 주문이 '실측일 미정' 목록에 되살아나기 때문.
_EXCLUDED_STAGE_BASE: tuple[str, ...] = _EXCLUDED_STAGE_CODES + tuple(
    STAGE_LABELS[code] for code in _EXCLUDED_STAGE_CODES if code in STAGE_LABELS
)


def _with_json_quoted_variants(values: Iterable[str]) -> list[str]:
    """SQL IN 절용으로 원문과 JSON 따옴표 변형(`"X"`)을 함께 돌려준다.

    `models.py` 의 `dashboard_active_filter` 가 completed_stages 를 두 형태로 넣는 것과
    같은 이유다 — 동기화 경로에 따라 따옴표가 붙은 값이 실데이터에 존재한다.

    파라미터:
        values: 제외 대상 원문 값들.
    반환값:
        중복이 제거된 정렬 리스트.
    """
    variants: set[str] = set()
    for value in values:
        text = str(value)
        variants.add(text)
        variants.add(f'"{text}"')
    return sorted(variants)


EXCLUDED_STAGE_SQL_VALUES: list[str] = _with_json_quoted_variants(_EXCLUDED_STAGE_BASE)


def is_measurement_undated(order: Any) -> bool:
    """실측일이 하나도 정해지지 않은 주문인지 판정한다.

    '추후통보'/'미정' 같은 텍스트는 날짜 정규화에 실패해 빈 리스트가 되므로
    여기서 True 가 된다 — 이것이 이 기능의 목표 집합이다.

    파라미터:
        order: Order ORM 행 (schedule_dates 관계가 로드돼 있어야 N+1 이 안 난다).
    반환값:
        실측일이 하나도 없으면 True.
    """
    return not extract_all_measurement_dates(order)


def apply_measurement_undated_sql_scope(query: Query) -> Query:
    """실측일 미정 목록의 SQL 모집단(상위집합)을 좁힌다.

    날짜 축은 절대 건드리지 않는다 — '추후통보' 텍스트 건이 빠지기 때문.
    상태·단계 축만 좁히고, 최종 판정은 파이썬(`is_measurement_undated`)이 한다.

    파라미터:
        query: `db.query(Order)` 기반 쿼리.
    반환값:
        필터가 적용된 쿼리.
    """
    query = query.filter(Order.active_filter())
    query = apply_measurement_dashboard_order_scope(query)
    # NULL 통과 필수: SQL NOT IN 은 NULL 행을 탈락시킨다.
    query = query.filter(or_(
        Order.status.is_(None),
        ~Order.status.in_(_EXCLUDED_STATUS_VALUES),
    ))
    # erp_stage_code 는 비ERP·미동기 주문에서 영원히 NULL 이다.
    query = query.filter(or_(
        Order.erp_stage_code.is_(None),
        ~Order.erp_stage_code.in_(EXCLUDED_STAGE_SQL_VALUES),
    ))
    return query


def resolve_manager_name(order: Any) -> str:
    """담당자 표시명을 해석한다(실측 대시보드 담당자 필터와 동일 규칙).

    ERP 주문은 structured_data.parties.manager 를 우선하고 Order.manager_name 을 폴백한다.

    파라미터:
        order: Order ORM 행.
    반환값:
        정규화된 담당자명(없으면 빈 문자열).
    """
    sd = getattr(order, 'structured_data', None)
    # truthiness 로 판정한다 — 대시보드 get_manager_name_for_sort 와 1:1 일치시키기 위함.
    # isinstance 로 보면 sd == {} 인 ERP 주문이 ERP 분기로 들어가, 대시보드는 raw
    # manager_name 을 쓰는데 여기만 사용자 id 를 이름으로 해석해 집합이 갈린다.
    if getattr(order, 'is_erp_order', False) and isinstance(sd, dict) and sd:
        parties = sd.get('parties')
        raw_manager = parties.get('manager') if isinstance(parties, dict) else None
        erp_manager = normalize_manager_name(raw_manager, getattr(order, 'manager_name', '') or '')
        if erp_manager:
            return erp_manager
    return getattr(order, 'manager_name', '') or ''


def resolve_measurement_undated_status_label(order: Any) -> str:
    """목록에 표시할 상태 라벨(ERP 주문은 단계, 그 외는 legacy 상태).

    파라미터:
        order: Order ORM 행.
    반환값:
        표시용 라벨 문자열(없으면 빈 문자열).
    """
    if not is_erp_order_record(order):
        status = getattr(order, 'status', None) or ''
        return STATUS.get(status, status)

    sd = _ensure_dict(getattr(order, 'structured_data', None))
    workflow = sd.get('workflow')
    workflow_stage = workflow.get('stage') if isinstance(workflow, dict) else None
    raw = str(getattr(order, 'erp_stage_code', None) or workflow_stage or '').strip().strip('"')
    if not raw:
        return '주문접수'
    if raw in STAGE_LABELS:
        return STAGE_LABELS[raw]
    if raw in STAGE_NAME_TO_CODE:
        return STAGE_LABELS.get(STAGE_NAME_TO_CODE[raw], raw)
    return raw


def build_measurement_undated_row(order: Any) -> dict[str, Any]:
    """모달 목록 1행 DTO를 만든다.

    파라미터:
        order: 표시 필드가 이미 적용된(`apply_erp_display_fields_to_orders`) Order 행.
    반환값:
        JSON 직렬화 가능한 dict.
    """
    return {
        'id': order.id,
        'customer_name': order.customer_name or '',
        'phone': order.phone or '',
        'address': order.address or '',
        'manager_name': resolve_manager_name(order),
        'status_label': resolve_measurement_undated_status_label(order),
        'received_date': order.received_date or '',
        'product': order.product or '',
        'is_regional': bool(order.is_regional),
        'is_self_measurement': bool(order.is_self_measurement),
        'edit_url': url_for(
            'order_edit.edit_order',
            order_id=order.id,
            return_to='erp_measurement_dashboard',
            open='erp-order',
        ),
    }


def _build_measurement_undated_query(
    db: Session,
    *,
    search_q: str,
    current_user: Any,
    mine_filter_active: bool,
) -> Query:
    """SQL 모집단 쿼리를 조립한다(검색어·mine·selectinload 포함).

    파라미터:
        db: SQLAlchemy 세션.
        search_q: 검색어(빈 문자열이면 미적용).
        current_user: 로그인 사용자.
        mine_filter_active: True 면 내 담당 OR 절을 적용한다.
    반환값:
        정렬·상한이 아직 적용되지 않은 쿼리.
    """
    query = apply_measurement_undated_sql_scope(db.query(Order))

    term = (search_q or '').strip()
    if term:
        query = query.filter(erp_measurement_main_search_predicate(f'%{term}%'))

    if mine_filter_active and current_user:
        # build_mine_sql_filter 는 조건 "리스트"를 반환한다 — or_ 로 감싸지 않으면 AND 결합된다.
        conds = build_mine_sql_filter(current_user)
        if conds:
            query = query.filter(or_(*conds))

    # extract_all_measurement_dates 가 schedule_dates 관계를 읽는다 — N+1 방지 필수.
    return query.options(selectinload(Order.schedule_dates))


def _passes_measurement_undated_python_filters(order: Any, manager_filter: str) -> bool:
    """파이썬 정밀 판정(자가실측 완료 제외 → 실측일 미정 → 담당자 일치).

    파라미터:
        order: 표시 필드가 적용된 Order 행.
        manager_filter: 담당자 정확 일치 필터(빈 문자열이면 미적용).
    반환값:
        목록에 남길 주문이면 True.
    """
    if self_measurement_four_checks_done(order):
        return False
    if not is_measurement_undated(order):
        return False
    if manager_filter:
        if resolve_manager_name(order).strip().lower() != manager_filter.strip().lower():
            return False
    return True


def collect_measurement_undated_orders(
    db: Session,
    *,
    search_q: str = '',
    manager_filter: str = '',
    current_user: Any = None,
    mine_filter_active: bool = False,
) -> tuple[list[Any], bool]:
    """실측일 미정 주문을 수집한다.

    파라미터:
        db: SQLAlchemy 세션.
        search_q: 검색어(대시보드와 동일 술어). 빈 문자열이면 미적용.
        manager_filter: 담당자 정확 일치 필터(대소문자 무시). 빈 문자열이면 미적용.
        current_user: 로그인 사용자(mine 필터용).
        mine_filter_active: True 면 build_mine_sql_filter 를 SQL WHERE 로 적용.
    반환값:
        (판정 통과 주문 리스트, 스캔 상한 발동 여부). 표시 상한은 여기서 자르지 않는다.
    """
    base_query = _build_measurement_undated_query(
        db,
        search_q=search_q,
        current_user=current_user,
        mine_filter_active=mine_filter_active,
    )

    matched: list[Any] = []
    scanned = 0
    scan_capped = False
    cursor_id: int | None = None

    while True:
        chunk_query = base_query
        if cursor_id is not None:
            chunk_query = chunk_query.filter(Order.id < cursor_id)
        chunk = (
            chunk_query.order_by(Order.id.desc())
            .limit(MEASUREMENT_UNDATED_SCAN_BATCH)
            .all()
        )
        if not chunk:
            break
        cursor_id = chunk[-1].id
        scanned += len(chunk)

        for row in chunk:
            row.structured_data = _ensure_dict(row.structured_data)
        apply_erp_display_fields_to_orders(chunk)
        matched.extend(
            o for o in chunk
            if _passes_measurement_undated_python_filters(o, manager_filter)
        )

        if len(chunk) < MEASUREMENT_UNDATED_SCAN_BATCH:
            break
        if scanned >= MEASUREMENT_UNDATED_SCAN_LIMIT:
            scan_capped = True
            logger.warning(
                '[MEAS_UNDATED] 스캔 backstop 발동 scanned=%s limit=%s',
                scanned, MEASUREMENT_UNDATED_SCAN_LIMIT,
            )
            break

    return matched, scan_capped


def build_measurement_undated_payload(
    db: Session,
    *,
    search_q: str = '',
    manager_filter: str = '',
    current_user: Any = None,
    mine_filter_active: bool = False,
) -> dict[str, Any]:
    """API `data` 페이로드를 만든다(표시 상한 적용 + 절단 사실 노출).

    파라미터:
        db: SQLAlchemy 세션.
        search_q: 검색어(선택).
        manager_filter: 담당자 정확 일치 필터(선택).
        current_user: 로그인 사용자(mine 필터용).
        mine_filter_active: True 면 내 담당 주문만.
    반환값:
        {rows, count, total, truncated, scan_capped, display_cap} dict.
    """
    orders, scan_capped = collect_measurement_undated_orders(
        db,
        search_q=search_q,
        manager_filter=manager_filter,
        current_user=current_user,
        mine_filter_active=mine_filter_active,
    )
    total = len(orders)
    truncated = total > MEASUREMENT_UNDATED_DISPLAY_CAP
    visible = orders[:MEASUREMENT_UNDATED_DISPLAY_CAP]
    return {
        'rows': [build_measurement_undated_row(o) for o in visible],
        'count': len(visible),
        'total': total,
        'truncated': truncated,
        'scan_capped': scan_capped,
        'display_cap': MEASUREMENT_UNDATED_DISPLAY_CAP,
    }

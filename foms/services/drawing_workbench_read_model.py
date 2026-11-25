"""ERP drawing workbench read-model — 모집단 술어(SQL) + order id 캐시 DTO.

**seed 는 도면 모집단으로 선스코프한 뒤 cap 을 적용한다.** 과거처럼 단계 조건 없이
``created_at desc LIMIT cap`` 으로 최신 N건만 뽑고 파이썬에서 걸러내면, 오래 머문
도면 주문이 접수순 창 밖으로 밀려 조용히 사라진다(2026-08-23 운영 사고: 프로세스 맵
28건 vs 작업실 1건 — 활성 ERP 2480건에 cap 250). 시공 대시보드가 같은 사고 뒤
``apply_construction_list_scope_filter`` 로 옮겨간 것과 동일한 구조다.

cap 은 이제 모집단 크기 가드일 뿐이며, 도달 시 **경고 로그를 남긴다**(조용한 누락 금지).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import and_, exists, func, or_

from foms.services.orders.as_drawing import AS_DRAWING_STATUS_KEY, OPEN_STATUSES as AS_DRAWING_OPEN_STATUSES
from foms.services.orders.drawing_factory import DRAWING_FIX_KEY
from models import Order, OrderConstructionAttempt

logger = logging.getLogger(__name__)

# 모집단 선스코프 후의 폭주 가드(도면 큐 자체가 이 크기를 넘으면 운영 이상 신호).
DRAWING_WORKBENCH_SEED_CAP = 1000

# workflow.stage 미러 컬럼(erp_stage_code)의 도면 단계 표기 — 코드/한글 라벨 양쪽.
DRAWING_STAGE_CODES = ('DRAWING', '도면')

# 도면 단계를 지난 뒤 새 도면이 와서 영업 수령 확정을 기다리는(TRANSFERRED) 단계 — 코드/한글.
# 생산 단계 재전달은 [제작 시작]을 막는데(confirm_drawing_gate) 목록에서 빠지면 영업이 확정할
# 곳을 못 찾는다(2026-10-22 주문 5625). 시공 이후 옛 주문(운영 65건)은 넣지 않는다.
POST_DRAWING_RECEIPT_STAGE_CODES = ('CONFIRM', '고객컨펌', 'PRODUCTION', '생산')

# 시공이 끝난 단계(완료 주문 AS 도면, 설계서 2026-11-11-as-drawing-after-completion §6.1) — 코드/한글.
# 검색어가 있을 때만 이 단계 주문을 모집단에 더한다(AS 도면 시작할 주문 찾기). 평소 목록은 그대로다.
AS_DRAWING_STAGE_CODES = ('CS', 'COMPLETED', '완료')


def _drawing_status_exprs():
    """행 판정이 읽는 두 키(``sd['drawing']['status']`` / ``sd['drawing_status']``) 식.

    Returns:
        (중첩 키 식, flat 키 식). 각각을 **단순 동등 비교**로만 쓴다 — coalesce 로 합치면
        부분 인덱스 predicate 와 식이 어긋나 Seq Scan 으로 추락하기 쉽다.
    """
    return (
        Order.structured_data[('drawing', 'status')].as_string(),
        Order.structured_data['drawing_status'].as_string(),
    )


def count_confirmed_drawing_orders(base_query) -> int:
    """수령확정(``CONFIRMED``) 도면 주문 수를 base scope 안에서 센다.

    기본 목록은 노이즈를 줄이려고 컨펌 주문을 모집단에서 뺀다(``include_confirmed=False``).
    그러면 화면 행만으로 세는 '완료' 타일이 **항상 0** 이 되어, 도면팀 입장에서는 수령확정한
    주문이 화면에서 통째로 사라진 것처럼 보인다. 타일 숫자는 목록 필터와 무관한 전체 큐
    기준이므로 여기서 따로 센다.

    Args:
        base_query: 목록과 같은 base scope(active·ERP·mine) 가 적용된 ``Order`` 쿼리.

    Returns:
        컨펌 상태 주문 수. 목록 행 판정(``effective_drawing_status``)과 같은 순서로 읽는다 —
        최상위 ``drawing_status`` 가 있으면 그 값, 비었을 때만 중첩 ``drawing.status``.
        두 키 중 하나라도 ``CONFIRMED`` 면 세던 옛 식은 최상위가 ``RETURNED`` 인데 중첩이
        ``CONFIRMED`` 로 남은 주문을 수정요청과 완료 양쪽에 이중으로 셌다.
    """
    nested, flat = _drawing_status_exprs()
    return base_query.filter(
        or_(
            flat == 'CONFIRMED',
            and_(or_(flat.is_(None), flat == ''), nested == 'CONFIRMED'),
        )
    ).count()


def build_drawing_queue_filter(*, include_confirmed: bool = False, as_search_clause: Any = None):
    """도면 작업실 모집단 술어(SQL) — 라우트 행 필터의 **상위집합(superset)**.

    Args:
        include_confirmed: 컨펌(수령확정) 주문 포함 여부(``?include_confirmed=1``).
        as_search_clause: 검색어 SQL 술어. 있으면 시공이 끝난 단계 주문 중 검색에 맞는 것을 더한다.

    Returns:
        SQLAlchemy ``or_`` 절. 도면 단계 ∪ 수정요청(RETURNED, 단계 무관)
        [∪ 수령확정(CONFIRMED)].

    Note:
        - RETURNED 축을 단계로 대체하면 안 된다 — 도면 전달/수령확정은 workflow.stage 를
          바꾸지 않으므로(erp_orders_drawing.py) CONFIRMED 주문은 도면 단계 밖에 있고,
          그 주문에 수정 요청이 들어오면 단계 조건만으로는 목록에서 사라진다.
        - 두 상태 키를 ``or`` 로 나란히 본다. 파이썬은 중첩 키 우선(``nested or flat``)이라
          두 키가 어긋나면 SQL 이 더 넓게 잡지만, 최종 판정은 라우트 행 필터가 한다.
          모집단이 상위집합이면 표시는 그대로이고 **누락만 불가능**해진다.
        - 단계도 미러 컬럼(``erp_stage_code``)과 원본(``workflow.stage``)을 함께 본다.
    """
    nested, flat = _drawing_status_exprs()
    statuses = ['RETURNED'] + (['CONFIRMED'] if include_confirmed else [])
    conditions = [
        Order.erp_stage_code.in_(DRAWING_STAGE_CODES),
        # 미러 컬럼이 드리프트해도 원본(structured_data)만으로 잡히도록 두 축을 함께 본다.
        # 운영은 현재 1:1 일치(드리프트 0건)지만, 술어가 미러 하나에만 걸리면 동기화 사고가
        # 곧바로 "목록에서 사라짐"으로 나타난다 — 이 화면이 겪은 사고와 같은 모양.
        Order.structured_data[('workflow', 'stage')].as_string().in_(DRAWING_STAGE_CODES),
    ]
    for status in statuses:
        conditions.append(nested == status)
        conditions.append(flat == status)
    # 생산 전 단계의 수령 대기 재전달 — 단계 축은 색인 있는 미러 컬럼(대상 수십 건)으로 좁힌다.
    conditions.append(and_(
        Order.erp_stage_code.in_(POST_DRAWING_RECEIPT_STAGE_CODES),
        or_(nested == 'TRANSFERRED', flat == 'TRANSFERRED'),
    ))
    # 완료 주문 AS 도면 차수 — 차수는 늘 AS 접수에 묶이므로(흐름 1·2) AS 축 부분 색인으로 먼저 좁힌다.
    as_statuses = list(AS_DRAWING_OPEN_STATUSES) + (['CONFIRMED'] if include_confirmed else [])
    conditions.append(and_(
        Order.as_axis_status.isnot(None),
        Order.structured_data[AS_DRAWING_STATUS_KEY].as_string().in_(as_statuses),
    ))
    if as_search_clause is not None:
        conditions.append(and_(Order.erp_stage_code.in_(AS_DRAWING_STAGE_CODES), as_search_clause))
    return or_(*conditions)


def fetch_drawing_seed_order_ids(
    orders_query: Any,
    *,
    cap: int = DRAWING_WORKBENCH_SEED_CAP,
    include_confirmed: bool = False,
    as_search_clause: Any = None,
) -> list[int]:
    """도면 모집단으로 선스코프한 뒤 접수순으로 cap 까지 뽑는다.

    Args:
        orders_query: active/ERP/mine 스코프가 적용된 ``Order`` 쿼리.
        cap: 폭주 가드 상한(모집단 선스코프 후 적용).
        include_confirmed: 컨펌 주문 포함 여부.
        as_search_clause: 검색어 SQL 술어(:func:`build_drawing_queue_filter`).

    Returns:
        접수 최신순 주문 id 목록.
    """
    rows = (
        orders_query.filter(build_drawing_queue_filter(
            include_confirmed=include_confirmed, as_search_clause=as_search_clause))
        .order_by(Order.created_at.desc())
        .with_entities(Order.id)
        .limit(cap)
        .all()
    )
    ids = [int(row[0]) for row in rows]
    if len(ids) >= cap:
        # 조용한 누락 금지: 캡에 닿았다는 사실 자체가 관측돼야 한다(운영 사고의 교훈).
        logger.warning(
            "drawing workbench seed cap reached (cap=%s, include_confirmed=%s) — 목록 누락 가능",
            cap,
            include_confirmed,
        )
    return ids


def hydrate_drawing_orders_by_ids(orders_query: Any, order_ids: list[int]) -> list[Order]:
    """Preserve id order; re-apply workbench scope filters (cache-hit safe)."""
    if not order_ids:
        return []
    rows = orders_query.filter(Order.id.in_(order_ids)).all()
    by_id = {int(o.id): o for o in rows}
    return [by_id[i] for i in order_ids if i in by_id]


# --------------------------------------------------------------------------- #
# '생산 중' 칸(설계서 2026-11-25 §2-1 · §7, D3)
# --------------------------------------------------------------------------- #
#: 생산 단계 · 시공 단계 미러 컬럼 값(코드/한글). 모집단 = 생산 전부 + 시공일이 오늘(KST)이거나 뒤이고 시공 방문이 안 열린 시공 대기.
PRODUCTION_TAB_STAGE_CODES = ('PRODUCTION', '생산')
CONSTRUCTION_WAIT_STAGE_CODES = ('CONSTRUCTION', '시공')
#: 나머지(요청 · 고치는 중이 아닌) 주문 상한 — 요청 · 고치는 중 주문은 상한 없이 먼저 모두 든다(잘리지 않음).
PRODUCTION_TAB_CAP = 1000


def build_production_tab_filter(today: str):
    """'생산 중' 칸 모집단 술어(SQL) — 생산 단계 전부 ∪ (시공 단계 ∧ 시공일 ≥ 오늘 ∧ 열린 시공 방문 없음).

    단계는 색인 있는 미러 컬럼(``erp_stage_code``), 시공일은 미러 컬럼(``erp_construction_date`` — 'YYYY-MM-DD' 글이라 글 비교가
    날짜 비교와 같다), 시공 시작은 ``order_construction_attempts.is_current`` 줄(부분 유일 색인 — 주문당 0/1). 시공일이 지난 것 ·
    시공을 시작한 것은 빠진다(사장님 답 Q1 · Q15 — 검색으로 찾는다). PostgreSQL · SQLite 모두 같은 SQL(JSON 연산 없음).

    Args:
        today: 오늘(KST) 'YYYY-MM-DD'.
    """
    started = exists().where(and_(OrderConstructionAttempt.order_id == Order.id, OrderConstructionAttempt.is_current.is_(True)))
    return or_(
        Order.erp_stage_code.in_(PRODUCTION_TAB_STAGE_CODES),
        and_(Order.erp_stage_code.in_(CONSTRUCTION_WAIT_STAGE_CODES), Order.erp_construction_date >= today, ~started),
    )


def _production_flagged_filter():
    """요청 · 고치는 중 후보(상위집합) — 영업 수정 요청(RETURNED, 두 상태 키) 또는 ``drawing_fix`` 칸이 있는 주문.

    ``drawing_fix`` 는 풀린 뒤에도 ``log`` 로 남으므로 상위집합이다 — 열린 요청 · 고치는 중인지는 행 판정(파이썬)이 가른다.
    JSONB ``?`` 대신 ``->>`` 의 NULL 여부로 본다(SQLite 시험 · PostgreSQL 운영 같은 뜻). 단계 술어가 색인으로 먼저 좁힌다.
    """
    nested, flat = _drawing_status_exprs()
    return or_(nested == 'RETURNED', flat == 'RETURNED', Order.structured_data[DRAWING_FIX_KEY].as_string().isnot(None))


def fetch_production_tab_order_ids(orders_query: Any, *, today: str, cap: int = PRODUCTION_TAB_CAP) -> dict[str, Any]:
    """'생산 중' 칸 주문 id — SQL 두 번(① 요청 · 고치는 중 후보 전부 ② 나머지 시공일 순 ``cap`` 건). 캡에 닿으면 경고 로그 + 수 한 번 더.

    Args:
        orders_query: active/ERP/mine/협력사 스코프가 적용된 ``Order`` 쿼리.
        today: 오늘(KST) 'YYYY-MM-DD'.
        cap: ② 상한.

    Returns:
        ``{"order_ids": [...], "hidden": N}`` — ① 다음 ② (겹치면 한 번), ``hidden`` = 캡 때문에 안 보이는 주문 수(캡에 안 닿으면 0).
    """
    population = build_production_tab_filter(today)
    flagged = [int(row[0]) for row in orders_query.filter(population, _production_flagged_filter())
               .with_entities(Order.id).order_by(Order.id).all()]
    rest = [int(row[0]) for row in orders_query.filter(population).with_entities(Order.id)
            .order_by(Order.erp_construction_date.is_(None), Order.erp_construction_date, Order.id).limit(cap).all()]
    ids = list(dict.fromkeys(flagged + rest))
    hidden = 0
    if len(rest) >= cap:
        hidden = max(0, int(orders_query.filter(population).count()) - len(ids))
        logger.warning("drawing workbench production tab cap reached (cap=%s, hidden=%s) — 목록 아래 안내", cap, hidden)
    return {"order_ids": ids, "hidden": hidden}


def production_tab_count_column(orders_query: Any, *, today: str):
    """'생산 중' 칸 숫자 식 — 모집단 수 스칼라 하위 질의(바깥과 묶지 않는다, ``orders_query`` 범위 = 내 것만 · 협력사 거르개)."""
    return (orders_query.filter(build_production_tab_filter(today)).with_entities(func.count(Order.id))
            .statement.correlate(None).scalar_subquery())


def hydrate_with_production_count(orders_query: Any, order_ids: list[int], *, today: str) -> tuple[list[Order], int]:
    """하이드레이트(:func:`hydrate_drawing_orders_by_ids` 와 같은 결과) + '생산 중' 칸 숫자를 **한 문장**으로(캐시 밖).

    칸 숫자는 5분 캐시(seed 블롭)에 두지 않는다 — 생산 · 시공 단계 쓰기(제작 완료 · 시공 시작 · 시공일 · [수정 시작] 등)는
    도면 캐시 갈래를 지우지 않아 숫자가 낡고 줄 수와 어긋났다(D3 검토 4). 하이드레이트 문장에 스칼라 하위 질의로 실어 요청마다 새
    값이면서 쿼리 수는 그대로다. 줄이 하나도 없으면(빈 큐) 숫자만 한 번 센다.

    Returns:
        ``(주문 목록 — order_ids 순서, 모집단 수)``.
    """
    count_col = production_tab_count_column(orders_query, today=today)
    rows = orders_query.filter(Order.id.in_(order_ids)).add_columns(count_col).all() if order_ids else []
    if not rows:
        return [], int(orders_query.session.query(count_col).scalar() or 0)
    by_id = {int(order.id): order for order, _count in rows}
    return [by_id[i] for i in order_ids if i in by_id], int(rows[0][1] or 0)

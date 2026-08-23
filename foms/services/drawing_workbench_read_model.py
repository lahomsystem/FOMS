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

from sqlalchemy import or_

from models import Order

logger = logging.getLogger(__name__)

# 모집단 선스코프 후의 폭주 가드(도면 큐 자체가 이 크기를 넘으면 운영 이상 신호).
DRAWING_WORKBENCH_SEED_CAP = 1000

# workflow.stage 미러 컬럼(erp_stage_code)의 도면 단계 표기 — 코드/한글 라벨 양쪽.
DRAWING_STAGE_CODES = ('DRAWING', '도면')


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


def build_drawing_queue_filter(*, include_confirmed: bool = False):
    """도면 작업실 모집단 술어(SQL) — 라우트 행 필터의 **상위집합(superset)**.

    Args:
        include_confirmed: 컨펌(수령확정) 주문 포함 여부(``?include_confirmed=1``).

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
    return or_(*conditions)


def fetch_drawing_seed_order_ids(
    orders_query: Any,
    *,
    cap: int = DRAWING_WORKBENCH_SEED_CAP,
    include_confirmed: bool = False,
) -> list[int]:
    """도면 모집단으로 선스코프한 뒤 접수순으로 cap 까지 뽑는다.

    Args:
        orders_query: active/ERP/mine 스코프가 적용된 ``Order`` 쿼리.
        cap: 폭주 가드 상한(모집단 선스코프 후 적용).
        include_confirmed: 컨펌 주문 포함 여부.

    Returns:
        접수 최신순 주문 id 목록.
    """
    rows = (
        orders_query.filter(build_drawing_queue_filter(include_confirmed=include_confirmed))
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

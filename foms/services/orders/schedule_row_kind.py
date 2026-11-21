"""일정 줄 종류 판정 — AS 상태 주문의 그날 줄이 시공 줄인지 AS 방문 줄인지 한 곳에서 정한다.

설계서 ``docs/specs/2026-11-20-multi-item-split-schedule_SPEC.md`` §4.1 (결정 M1 · M2 · M3).

* 본 흐름 열림 = ``erp_stage_code`` 가 생산 · 시공 진행 코드(CS · 완료는 닫힘).
* 시공 줄 = 일정 줄 ``kind='construction'`` 이고 (AS 상태가 아님 또는 본 흐름 열림).
* AS 방문 줄 = 일정 줄 ``kind='as_visit'`` 이고 AS 상태.
* 같은 주문 · 같은 날 둘 다면 시공 줄 하나 + "AS 방문도".

본 흐름이 닫힌 AS 주문은 날짜와 무관하게 AS 줄이다 — 옛 흐름은 AS 방문일을 시공일 칸에 적기도 해서,
AS 상태의 시공 줄을 통째로 풀면 지난 AS 가 시공 줄로 되살아난다.

잎 모듈이다(``sqlalchemy`` 만 가져온다). 출고 · 시공 읽기 모델이 모두 여기서 가져오므로 다른 읽기 모델을
가져오면 순환한다 — 단계 코드 묶음도 그래서 여기 다시 적는다(같은 값인지는 시험이 견준다).
"""
from __future__ import annotations

from typing import Any, NamedTuple

from sqlalchemy import case, or_

#: 본 흐름이 열려 있는 단계 코드(생산 + 시공 진행).
MAIN_FLOW_OPEN_STAGE_CODES: tuple[str, ...] = ("PRODUCTION", "생산", "CONSTRUCTION", "시공", "CONSTRUCTING")
#: AS 상태 글. AS 를 끝내도 현재 건 표시가 남아 상태가 계속 ``AS_COMPLETED`` 라 세 값 모두 다룬다.
AS_ORDER_STATUSES: tuple[str, ...] = ("AS", "AS_RECEIVED", "AS_COMPLETED")
#: 시공 줄에 붙이는 작은 글(같은 날 AS 방문도 있을 때).
AS_VISIT_TOO_TEXT = "AS 방문도"
#: 읽기 모델이 줄 객체에 붙이는 칸 이름 — 그날 일정으로 정한 줄 종류.
ROW_IS_AS_ATTR = "schedule_row_is_as"
ROW_AS_VISIT_TOO_ATTR = "schedule_as_visit_too"


class RowKind(NamedTuple):
    """한 주문 · 한 날짜 줄의 종류."""

    is_as: bool          # True = AS 방문 줄, False = 시공 줄
    as_visit_too: bool   # 시공 줄인데 같은 날 AS 방문도 있다


def is_as_status(order: Any) -> bool:
    """주문 상태 글이 AS 계열인가."""
    return getattr(order, "status", None) in AS_ORDER_STATUSES


def is_main_flow_open(order: Any) -> bool:
    """본 흐름이 열려 있는가(단계가 생산 또는 시공 진행)."""
    return str(getattr(order, "erp_stage_code", None) or "").strip().upper() in MAIN_FLOW_OPEN_STAGE_CODES


def as_hides_main_flow(order: Any) -> bool:
    """AS 상태이고 본 흐름이 닫힌 주문인가 — 그 주문의 줄 · 카드는 날짜와 무관하게 AS 로 그린다."""
    return is_as_status(order) and not is_main_flow_open(order)


def row_kind(order: Any, *, on_construction_date: bool, on_as_visit_date: bool) -> RowKind:
    """그날 줄의 종류.

    Args:
        order: ``status`` · ``erp_stage_code`` 를 가진 주문.
        on_construction_date: 그 날짜(또는 기간)에 시공 일정 줄이 있는가.
        on_as_visit_date: 그 날짜(또는 기간)에 AS 방문 일정 줄이 있는가.

    Returns:
        AS 상태가 아니면 시공 줄. 본 흐름이 닫힌 AS 주문이면 AS 줄. 본 흐름이 열린 AS 주문은
        AS 방문일에만 걸린 날이면 AS 줄, 그 밖은 시공 줄(같은 날 AS 방문도 있으면 ``as_visit_too``).
    """
    if not is_as_status(order):
        return RowKind(False, False)
    if not is_main_flow_open(order):
        return RowKind(True, False)
    if on_as_visit_date and not on_construction_date:
        return RowKind(True, False)
    return RowKind(False, bool(on_as_visit_date))


def row_is_as(row: Any) -> bool:
    """줄에 붙은 종류를 읽는다. 안 붙었으면 날짜를 모르므로 주문만 보고 정한다."""
    flag = getattr(row, ROW_IS_AS_ATTR, None)
    return bool(flag) if isinstance(flag, bool) else as_hides_main_flow(row)


def row_as_visit_too(row: Any) -> bool:
    """시공 줄에 "AS 방문도"를 붙일지(읽기 모델이 붙인 값, 없으면 False)."""
    return getattr(row, ROW_AS_VISIT_TOO_ATTR, None) is True


def as_status_clause(entity: Any) -> Any:
    """SQL — AS 상태 주문."""
    return entity.status.in_(AS_ORDER_STATUSES)


def not_as_status_clause(entity: Any) -> Any:
    """SQL — AS 상태가 아닌 주문(상태 NULL 포함)."""
    return or_(entity.status.is_(None), ~entity.status.in_(AS_ORDER_STATUSES))


def construction_line_clause(entity: Any) -> Any:
    """SQL — 시공 일정 줄을 시공 줄로 그리는 주문: AS 아님 또는 본 흐름 열림.

    OR 은 주문 표 한 곳 안에만 둔다(두 표에 걸치면 PostgreSQL 계획 세우기가 느려진다 — :func:`kind_pair_case`).
    """
    return or_(
        entity.status.is_(None),
        ~entity.status.in_(AS_ORDER_STATUSES),
        entity.erp_stage_code.in_(MAIN_FLOW_OPEN_STAGE_CODES),
    )


def kind_pair_case(kind_column: Any, entity: Any) -> Any:
    """SQL — 일정 줄 종류 ↔ 주문 짝을 CASE 한 식으로(그 밖 종류는 NULL = 빠짐).

    ``(종류 = AS 방문 AND AS 상태) OR (종류 = 시공 AND 시공 줄 조건)`` 과 뜻이 같다. 두 표에 걸친 OR 은
    PostgreSQL 계획기가 표마다 OR 조건을 뽑아 색인 묶음(BitmapOr)을 두루 맞춰 보느라 계획 세우기가 실행보다
    3배 넘게 걸렸다(로컬 PG 17 · 운영 규모 가짜 자료: 날짜별 집 수 2.2ms → 0.55ms, 그날 줄 1.8 → 0.65ms).
    """
    return case(
        (kind_column == "as_visit", as_status_clause(entity)),
        (kind_column == "construction", construction_line_clause(entity)),
    )

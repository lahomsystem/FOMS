"""정산 모집단의 **얇은** ``structured_data`` — 금액·정산 판정이 읽는 경로만 싣는다 (성능 원장 P3-6).

정산 집계(:mod:`foms.services.settlement_aggregation`)·실무 탭(:mod:`foms.services.settlement_rows`)은
모집단 전량을 읽고 파이썬에서 거른다(미수·aging 이 기간 무관 지표라 전량이 필요하다). 비용은 행 수가
아니라 **행마다 통째로 싣는 문서**였다 — 2026-10-05 스테이징 1,586행에 출력 3,675kB 인데, 판정이
읽는 것은 그중 일부다(``quests``·``site``·``workflow``·``notes`` 같은 큰 갈래는 어떤 정산 함수도
안 읽는다). 여기서는 그 경로만 남긴 문서를 SQL 이 조립하게 한다.

규율은 네이버 처리 목록 투영(:mod:`foms.web.admin.naver_list_snapshot`)과 같다 — 판정 함수를 두 벌로
만들지 않고 **입력만** 얇게 한다. 남긴 경로 안에서는 원본과 한 글자도 다르지 않다:

- 남기는 키는 원본에 **있을 때만** 싣는다. 없는 키를 ``null`` 로 채우지 않는다
  (``erp_deposit_amount_from_structured`` 가 ``'deposit' in payment`` 로 "없음"과 "null"을 가른다).
- dict(배열)가 아닌 자리(``null``·문자열·숫자)는 원본 그대로 둔다 — 판정 함수의 ``isinstance``
  방어가 그 모양으로 갈린다.
- 배열 마디(``items``)는 **원소 수와 순서를 그대로** 두고 원소 안만 줄인다. 품목합은
  "빈 목록이면 None, 원소가 있으면 단가 합"이라 원소 수가 결과를 가른다.

읽는 경로와 읽는 함수(전부 이 투영의 소비자 — 추적 계약 테스트
``tests/services/test_settlement_source.py`` 가 실제 경로를 돌려 잡는다):

- ``schedule.construction.date`` — 완료일 키(``completion_day_key``·``completion_month_key``).
- ``payment``·``payments`` (통째) — 예약금·할인·자유입력·잔금 확인·현금영수증 요청
  (``erp_deposit_amount_from_structured``·``_extract_discount_amount``·
  ``_extract_free_input_amount``·``balance_confirmed``·``deposit_confirmed``·``cash_receipt``).
- ``totals`` (통째) — ``items_total``·``discount_amount``·``free_input_amount``.
- ``items[].price`` — 품목합 폴백(``erp_payment_amount_from_structured``). 원소의 다른 키
  (품명·규격·도면 메타)는 싣지 않는다 — 이 갈래가 문서에서 가장 크다.
- ``settlement`` (통째) — 부서별 차감·현금영수증 발행(``_deduction_entries``·``_cash_receipt_issued``).
- ``shipment.as_billing`` — AS 청구 판정(``as_billing_badge_kind``·``_as_billing_paid_amount``).
- ``parties.manager.name``·``parties.customer.name`` — 담당자·고객 표시명.

원본은 행마다 **한 번만** 푼다. 투영 식은 원본을 여러 번 참조하는데 TOAST 에 있는 jsonb 는 참조마다
다시 풀린다 — 그래서 안쪽 조회가 ``structured_data #> '{}'``(같은 값의 풀린 사본)로 한 번 풀고
``OFFSET 0`` 울타리로 바깥에 끌려 올라가지 않게 막는다(네이버 ``fenced_snapshot_source`` 와 같은 수,
공용 조각은 :mod:`foms.services.common.jsonb_projection`).
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy import case, cast, column, func, literal_column, select
from sqlalchemy.dialects.postgresql import JSON as PG_JSON
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by

from foms.services.common.jsonb_projection import (
    json_object_absent,
    jsonb_key_order,
    supports_sql_projection,
)
from models import Order

__all__ = [
    "ARRAY_ITEMS",
    "SETTLEMENT_SD_SPEC",
    "fetch_settlement_rows",
    "project_settlement_sd",
    "settlement_rows_statement",
]

#: 배열 마디 표식 — ``{ARRAY_ITEMS: 원소 나무}`` 는 "배열이면 원소마다 원소 나무로 줄인다".
#: 경로 추적기(``naver_list_snapshot_helpers.traced``)가 배열 원소 자리를 같은 글자로 적는다.
ARRAY_ITEMS = "[]"

#: SQL 에 글자 그대로 박는 투영 키의 허용 모양(상수 키만 온다 — 방어선).
_KEY_PATTERN = re.compile(r"^[A-Za-z_]+$")

#: 투영 나무. 값이 ``None`` 이면 그 자리를 통째로, dict 면 그 키들만 남긴다.
SETTLEMENT_SD_SPEC: dict[str, Any] = {
    "items": {ARRAY_ITEMS: {"price": None}},
    "totals": None,
    "parties": {"manager": {"name": None}, "customer": {"name": None}},
    "payment": None,
    "payments": None,
    "schedule": {"construction": {"date": None}},
    "shipment": {"as_billing": None},
    "settlement": None,
}


def project_settlement_sd(raw: Any, spec: Optional[dict[str, Any]] = None) -> Any:
    """원본 ``structured_data`` 를 :data:`SETTLEMENT_SD_SPEC` 대로 줄인다 — SQL 투영의 **파이썬 정본**.

    SQLite 레인(투영 SQL 이 없다)과 PostgreSQL 16 미만에서는 이 함수가 투영을 맡고, PG 레인
    테스트는 SQL 결과가 이 함수 결과와 같은지 못박는다.

    Args:
        raw: ``Order.structured_data`` (dict 가 아니면 그대로 돌려준다).
        spec: 투영 나무(기본 :data:`SETTLEMENT_SD_SPEC`). 계약 테스트의 음성 대조군이 경로
            하나를 뺀 나무를 넘긴다.

    Returns:
        남기는 키만 담은 새 문서(원본 키 순서 유지). 남기는 값은 원본 객체를 그대로 쓴다.
    """
    return _project(raw, SETTLEMENT_SD_SPEC if spec is None else spec)


def _project(value: Any, spec: Optional[dict[str, Any]]) -> Any:
    """:func:`project_settlement_sd` 의 재귀 본체(``spec`` 이 None 이면 통째)."""
    if spec is None:
        return value
    if ARRAY_ITEMS in spec:
        if not isinstance(value, list):
            return value
        return [_project(item, spec[ARRAY_ITEMS]) for item in value]
    if not isinstance(value, dict):
        return value
    return {key: _project(item, spec[key]) for key, item in value.items() if key in spec}


def _node(doc: Any, spec: Optional[dict[str, Any]]) -> Any:
    """jsonb 식 ``doc`` 을 ``spec`` 대로 줄인 식(SQL 투영 한 마디).

    Args:
        doc: jsonb 식. 없는 키면 SQL NULL 이다 — 결과도 NULL 이라 바깥 ``ABSENT ON NULL`` 이
            키를 뺀다(없는 키를 ``null`` 로 채우지 않는다).
        spec: 투영 나무의 한 마디.

    Returns:
        json 식. 통째 마디는 jsonb 그대로 둔다(``JSON_OBJECT`` 가 값으로 받는다).
    """
    if spec is None:
        return doc
    if ARRAY_ITEMS in spec:
        # 원소 수·순서를 그대로 둔다(빈 배열은 json_agg 가 NULL 을 내므로 '[]' 로 되돌린다).
        elements = func.jsonb_array_elements(doc).table_valued(
            column("value", JSONB), with_ordinality="ord").render_derived(name="settle_el")
        reduced = select(func.json_agg(aggregate_order_by(
            _node(elements.c.value, spec[ARRAY_ITEMS]), elements.c.ord))).scalar_subquery()
        return case((func.jsonb_typeof(doc) == "array",
                     func.coalesce(reduced, cast(literal_column("'[]'"), PG_JSON))),
                    else_=cast(doc, PG_JSON))
    entries: list[Any] = []
    for key in sorted(spec, key=jsonb_key_order):
        if not _KEY_PATTERN.match(key):
            raise ValueError(f"투영 키는 영문자·밑줄만 허용한다: {key!r}")
        entries += [literal_column(f"'{key}'"), _node(doc[key], spec[key])]
    # 남길 키가 없는 마디는 빈 객체다(``JSON_OBJECT()`` 에 ABSENT ON NULL 만 붙이면 문법 오류).
    picked = (json_object_absent(*entries) if entries
              else cast(literal_column("'{}'"), PG_JSON))
    return case((func.jsonb_typeof(doc) == "object", picked), else_=cast(doc, PG_JSON))


def settlement_rows_statement(columns: tuple, criteria: tuple,
                              spec: Optional[dict[str, Any]] = None) -> Any:
    """``columns`` + 얇은 ``structured_data`` 를 읽는 PostgreSQL 문장(원본은 행마다 한 번만 푼다).

    Args:
        columns: 함께 읽을 ``Order`` 컬럼.
        criteria: WHERE 조건(모집단 술어 그대로).
        spec: 투영 나무(기본 :data:`SETTLEMENT_SD_SPEC`).

    Returns:
        ``columns`` 순서의 컬럼 + ``structured_data``(투영 문서)를 내는 select.
    """
    detoasted = Order.structured_data.op("#>", return_type=JSONB)(
        literal_column("'{}'::text[]"))
    inner = (select(*columns, detoasted.label("sd")).where(*criteria)
             .offset(0).subquery("settle_src"))
    document = _node(inner.c.sd, SETTLEMENT_SD_SPEC if spec is None else spec)
    return select(*[inner.c[col.key] for col in columns],
                  document.label("structured_data"))


def fetch_settlement_rows(db: Any, columns: tuple, criteria: tuple) -> list[Any]:
    """정산 모집단 행을 읽는다 — 술어는 호출자 그대로, ``structured_data`` 만 얇다.

    Args:
        db: SQLAlchemy Session.
        columns: 함께 읽을 ``Order`` 컬럼(행 속성 이름은 컬럼 키 그대로).
        criteria: WHERE 조건.

    Returns:
        ``columns`` 키 + ``structured_data`` 속성을 가진 결과 행 목록. 정렬은 보장하지 않는다
        (옛 조회도 ORDER BY 가 없었다 — 소비자는 집계하거나 스스로 정렬한다).
    """
    if supports_sql_projection(db):
        return db.execute(settlement_rows_statement(columns, criteria)).all()
    rows = db.query(*columns, Order.structured_data).filter(*criteria).all()
    keys = [col.key for col in columns] + ["structured_data"]
    return [SimpleNamespace(**dict(zip(keys, (*row[:-1], project_settlement_sd(row[-1])))))
            for row in rows]


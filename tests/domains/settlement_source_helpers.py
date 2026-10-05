"""정산 얇은 문서(:mod:`foms.services.settlement_source`) 계약의 공용 재료 — 모양 표본·시드·판정 소비자.

SQLite 레인(``tests/domains/test_settlement_source.py``)과 PG 레인
(``tests/postgres/test_settlement_source_pg.py``)이 **같은 표본**을 쓴다. 표본은 금액·정산 판정의
갈래가 한 번씩 걸리게 만든 것이다: 품목합이 저장된 주문·품목 단가 폴백(문자·실수·dict 아닌 원소·
단가 없는 원소)·빈 품목·레거시 ``payments``·명시적 null·dict 아닌 자리·AS 청구 4분류·콤마 복수
완료일·현금영수증 요청/발행·부서별 차감, 그리고 정산이 **안 읽는** 큰 갈래(``quests``·``site``·
``workflow``·품목 메타)를 든 주문.
"""
from __future__ import annotations

import copy
import datetime
from types import SimpleNamespace
from typing import Any, Optional

from foms.services import settlement_aggregation, settlement_rows
from foms.services.erp_display import _ensure_dict, erp_shipping_price_from_structured
from foms.services.settlement_source import ARRAY_ITEMS
from models import Order

#: 정산이 안 읽는 큰 갈래 — 투영이 떨어뜨려야 할 것들.
_UNREAD = {
    "quests": [{"stage": "MEASURE", "done": True, "memo": "실측 완료" * 20}],
    "site": {"address_full": "서울 강남구 테헤란로 1", "address_detail": "101호"},
    "workflow": {"stage": "COMPLETED", "stage_updated_at": "2026-09-01T10:00:00"},
    "notes": "현장 메모" * 30,
}


def _items(*prices: Any) -> list[dict[str, Any]]:
    """단가 + 정산이 안 읽는 품목 메타(품명·규격·색상)."""
    return [{"product_name": f"붙박이장 {i}", "standard": "3조", "color": "화이트",
             "option_detail": "손잡이 없음", "price": price}
            for i, price in enumerate(prices, start=1)]


#: 표본: 라벨 → (structured_data, 컬럼 값). ``schedule.construction.date`` 는 문서 안에 직접 둔다.
SHAPES: dict[str, tuple[Any, dict[str, Any]]] = {
    "정상-전부": ({
        **_UNREAD,
        "items": _items(1_200_000, 300_000),
        "totals": {"items_total": 1_500_000, "discount_amount": 0, "free_input_amount": None},
        "parties": {"manager": {"name": "이시영", "phone": "010-1"},
                    "customer": {"name": "윤인선", "phone": "010-2562-9522"},
                    "orderer": {"name": "라홈"}},
        "payment": {"deposit": 500_000, "discount": "50,000", "free_input": "배송: 30,000\n설치 : 20000",
                    "balance_confirmed": False, "deposit_confirmed": True,
                    "cash_receipt": "010-1234-5678 소득공제"},
        "schedule": {"construction": {"date": "2026-09-15", "time": "오전"},
                     "measurement": {"date": "2026-09-01"}},
        "shipment": {"as_billing": {"type": "paid", "confirmed": True, "amount": 70_000},
                     "carrier": "직배", "memo": "x" * 50},
        "settlement": {"deductions": [{"department": "sales", "amount": -30_000},
                                      {"department": "DRAWING", "amount": 12_000},
                                      {"department": "ETC", "amount": "오류"}, "깨진-행"],
                       "cash_receipt": {"issued": True, "issued_at": "2026-09-20"}},
    }, {"manager_name": "옛담당", "customer_name": "컬럼고객"}),
    "품목합-폴백-단가모양": ({
        **_UNREAD,
        "items": [*_items("1,000,000", 250_000.0, None, True, -5), "dict 아닌 원소", 7,
                  {"product_name": "단가 없음"}],
        "totals": {"discount_amount": "100,000"},
        "payment": {"deposit": {"amount": "200,000"}, "balance_confirmed": "Y"},
        "schedule": {"construction": {"date": "2026-05-27,2026-05-28"}},
    }, {}),
    "빈-품목": ({"items": [], "payment": {"deposit": 100_000},
                "schedule": {"construction": {"date": "2026-10-01"}}}, {}),
    "dict-아닌-원소만": ({"items": ["x", 3, None],
                       "schedule": {"construction": {"date": "2026-08-31"}}}, {}),
    "레거시-payments": ({
        **_UNREAD,
        "items": _items(800_000),
        "payments": {"deposit": {"raw": "300,000원"}, "free_input": {"value": "양중: 40,000"}},
        "totals": {"items_total": "800,000", "free_input_amount": 0},
        "schedule": {"construction": {"date": "2025-12-31"}},
    }, {"manager_name": None}),
    "명시적-null": ({
        "items": None, "totals": None, "payment": {"deposit": None, "cash_receipt": None},
        "parties": {"manager": None, "customer": {"name": None}},
        "schedule": {"construction": None}, "shipment": {"as_billing": None},
        "settlement": None,
    }, {"manager_name": "  컬럼담당  "}),
    "dict-아닌-자리": ({
        "items": {"price": 10}, "totals": "문자", "payment": "문자",
        "parties": "문자", "shipment": [], "settlement": ["x"],
        "schedule": {"construction": {"date": "미정"}},
    }, {}),
    "AS-유상-미확정": ({
        "items": _items(90_000), "totals": {"items_total": 90_000},
        "shipment": {"as_billing": {"type": "PAID", "confirmed": "yes", "amount": 90_000}},
        "schedule": {"construction": {"date": "2026-09-30"}},
    }, {"status": "AS_COMPLETED", "as_axis_status": "COMPLETED"}),
    "AS-미정": ({
        "totals": {"items_total": 0},
        "shipment": {"as_billing": {"type": "undecided"}},
        "schedule": {"construction": {"date": "2026-02-29"}},
    }, {"status": "AS_RECEIVED", "as_axis_status": "RECEIVED"}),
    "과입금-완료일없음": ({
        **_UNREAD,
        "items": _items(100_000), "totals": {"items_total": 100_000},
        "payment": {"deposit": 150_000, "free_input": ""},
        "parties": {"manager": "문자담당", "customer": "문자고객"},
    }, {"manager_name": "Kim"}),
    "빈-문서": ({}, {"manager_name": "kim "}),
    "문서-없음": (None, {}),
}

#: 단계 카드(``_build_stages``) 모집단에 넣을 진행 중 표본 — 같은 문서를 진행 단계로 시드한다.
STAGE_SHAPES = ("정상-전부", "품목합-폴백-단가모양", "빈-품목", "레거시-payments", "명시적-null")

_TODAY = datetime.date(2026, 10, 5)


def seed_shapes(session: Any, *, prefix: str = "SSRC") -> list[int]:
    """표본마다 정산 모집단 주문 1건 + 진행 중 단계 주문을 넣는다(flush 만, 커밋은 호출자).

    Args:
        session: SQLAlchemy Session.
        prefix: 고객명 앞머리(다른 테스트 데이터와 갈라 보기용).

    Returns:
        만든 주문 id 목록.
    """
    orders: list[Order] = []
    for label, (sd, attrs) in SHAPES.items():
        orders.append(_order(session, f"{prefix}-{label}", sd, attrs))
    for label in STAGE_SHAPES:
        sd, attrs = SHAPES[label]
        orders.append(_order(session, f"{prefix}-진행-{label}", sd,
                             {**attrs, "status": "RECEIVED", "erp_stage_code": "MEASURE"}))
    session.flush()
    return [order.id for order in orders]


def _order(session: Any, name: str, sd: Any, attrs: dict[str, Any]) -> Order:
    values = {"received_date": "2026-01-01", "customer_name": name, "phone": "010-0000-0000",
              "address": "서울", "product": "붙박이장", "status": "COMPLETED",
              "is_erp_order": True, "erp_stage_code": "COMPLETED", "manager_name": "담당자"}
    values.update(attrs)
    order = Order(**values, structured_data=copy.deepcopy(sd))
    session.add(order)
    return order


def row_for(sd: Any, attrs: Optional[dict[str, Any]] = None) -> SimpleNamespace:
    """판정 소비자에 넣을 결과 행 1건(두 모듈이 읽는 컬럼 전부)."""
    values = {"id": 1, "status": "COMPLETED", "manager_name": "담당자", "as_axis_status": None,
              "customer_name": "컬럼고객", "erp_stage_code": "MEASURE"}
    values.update(attrs or {})
    return SimpleNamespace(**values, structured_data=sd)


#: 행 1건을 받는 판정 소비자 전부 — 이 투영을 읽는 함수가 늘면 여기에 더한다.
CONSUMERS = {
    "aggregation._settlement_row": lambda row: settlement_aggregation._settlement_row(row, "일반"),
    "rows._settlement_row": lambda row: settlement_rows._settlement_row(
        row, "NAVER", _TODAY, include_naver_settlement=True, naver_settle=None),
    "stages.shipping_price": lambda row: erp_shipping_price_from_structured(
        _ensure_dict(row.structured_data)),
}


def spec_node(spec: Any, path: tuple) -> tuple[bool, Any]:
    """``(투영이 이 자리를 싣는가, 그 자리의 나무 마디)`` — 통째 마디 아래는 전부 싣는다."""
    node: Any = spec
    for key in path:
        if node is None:
            return True, None
        if not isinstance(node, dict) or key not in node:
            return False, False
        node = node[key]
    return True, node


#: 자리 전체를 보는 접근. 통째 마디 안이거나, **배열 마디**의 순회·길이여야 한다(배열 마디는
#: 원소 수·순서를 그대로 두므로 순회해도 같은 원소를 같은 순서로 만난다).
_WHOLE_OPS = frozenset({"iter", "keys", "items", "values", "eq", "repr", "copy", "reduce",
                        "index", "contains_value"})
_ARRAY_OK_OPS = frozenset({"iter", "index", "len"})


def uncovered_reads(ops: set, spec: dict) -> set:
    """투영 나무가 못 덮는 읽기(빈 집합이면 계약 통과).

    Args:
        ops: 경로 추적기가 모은 ``(경로, 접근)`` 집합.
        spec: 투영 나무(:data:`SETTLEMENT_SD_SPEC` 또는 음성 대조군).

    Returns:
        덮이지 않은 ``(경로, 접근)`` 집합.
    """
    missing = set()
    for path, op in ops:
        kept, node = spec_node(spec, path)
        if not kept:
            missing.add((path, op))
            continue
        if op in _WHOLE_OPS:
            is_array = isinstance(node, dict) and ARRAY_ITEMS in node
            if node is not None and not (is_array and op in _ARRAY_OK_OPS):
                missing.add((path, op))
    return missing


def spec_without(spec: dict, path: tuple) -> dict:
    """``path`` 하나를 뺀 투영 나무 사본 — 음성 대조군용."""
    clone = copy.deepcopy(spec)
    node = clone
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return clone

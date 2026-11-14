"""ERP 물건 종류 10개 · 주문 속성 표 — **선언만** 있는 작은 목록(설계서 2026-11-14-foms-graft 3.2). DB 를 읽지 않는다.

새 표를 만들지 않는다. 물건 종류마다 지금 FOMS 의 어느 표 · 칸이 정본인지 가리키기만 한다. 온톨로지 화면(ERP 물건 칸) ·
능력 질문의 ERP 재료 · 물어보기의 읽기 도구가 이 목록을 같이 본다.

- :data:`OBJECT_TYPES` — 코드 이름(``erp:<종류>``) · 화면 이름 · 정본 자리(표 · JSON 칸 · 설계서 글 그대로) · 판 1 읽기 도구가
  있나 · 가림(AI 에 안 감).
- :data:`ORDER_PROPS` — 주문 속성 ↔ 지금 칸. 설계서 3.2 '실제 정본' 칸 그대로다 — 목업의 ``orders.status`` ·
  ``orders.measurement_date`` · ``orders.customer_name`` 같은 옛 칸은 정본이 아니다(설계서 9절).
- 쓰기는 이 목록에 없다 — 할 일 목록(:mod:`foms.services.erp_actions.registry`)의 이름만 ``via`` 로 가리킨다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = [
    "ACCESS_LABELS", "ErpObject", "OBJECT_TYPES", "ORDER_PROPS", "OrderProp", "get_type", "masked_props",
]

#: 읽기 · 쓰기 갈래 → 화면 말(온톨로지 '속성 ↔ 지금 칸' 표).
ACCESS_LABELS: dict[str, str] = {
    "read": "읽기만",
    "action": "할 일로만",
    "link": "바로가기",
    "person": "사람만",
    "masked": "사람만 · 가림",
    "money": "사람만 · 돈",
}


@dataclass(frozen=True)
class ErpObject:
    """물건 종류 하나 — 지금 표 · 칸을 가리키는 이름표."""

    type: str  # 코드 이름 'erp:<종류>'
    label: str  # 화면 이름
    sub: str  # 왼쪽 목록 옆 짧은 말(없으면 빈 글)
    icon: str  # 디자인 시스템 아이콘 class('i-…')
    table: str  # 정본 표(여럿이면 대표 하나)
    json: str  # structured_data 안 자리(없으면 빈 글)
    source: str  # 정본 자리 글(설계서 3.2 표 그대로)
    readable: bool  # 판 1 읽기 도구로 읽히나(주문 읽기 안에서 일부만 읽혀도 참)
    read_note: str  # 판 1 읽기 도구 칸 글(설계서 3.2 그대로)
    masked: bool  # 이 물건의 값이 AI 에 가지 않나(통째 또는 주소처럼 일부)

    @property
    def slug(self) -> str:
        """주소에 쓰는 짧은 이름('erp:order' → 'order')."""
        return self.type.split(":", 1)[1]


OBJECT_TYPES: tuple[ErpObject, ...] = (
    ErpObject("erp:order", "주문", "orders", "i-cube", "orders", "structured_data",
              "orders + structured_data", True, "있음", False),
    ErpObject("erp:order_item", "주문 품목", "", "i-box", "order_item_identities", "structured_data.items[]",
              "structured_data.items[](이름 product_name) + order_item_identities", True, "이름만(주문 읽기 안)", False),
    ErpObject("erp:customer", "손님", "가림", "i-person", "orders", "structured_data.parties.customer",
              "structured_data.parties.customer.{name, phone} · 숫자만 orders.erp_phone_digits", False,
              "없음 — 가림(AI 에 안 감)", True),
    ErpObject("erp:site", "현장", "가림", "i-map-marker", "orders", "structured_data.site",
              "structured_data.site.{address_full, address_main} · orders.is_regional", True, "지방 여부만", True),
    ErpObject("erp:visit", "방문", "실측 · 시공 · AS · 배송", "i-calendar", "order_schedule_dates", "structured_data.schedule",
              "실측 structured_data.schedule.measurement.{date, time} · 시공 schedule.construction.{date, time} · "
              "AS schedule.as_visit.date · 배송 orders.shipping_scheduled_date · 날짜 찾기 표 order_schedule_dates",
              True, "있음", False),
    ErpObject("erp:drawing", "도면", "", "i-document", "drawing_revisions", "",
              "drawing_revisions · drawing_revision_requests", False, "선언만", False),
    ErpObject("erp:production_run", "생산 작업", "", "i-build", "production_runs", "",
              "production_runs", False, "선언만", False),
    ErpObject("erp:shipment", "출고", "", "i-truck", "orders", "",
              "orders.shipping_scheduled_date + 물류 축(foms/services/orders/state_axes.py)", False, "선언만", False),
    ErpObject("erp:partner_order", "협력사 발주", "", "i-people", "partner_orgs", "",
              "orders.partner_org_id + partner_orgs", False, "선언만", False),
    ErpObject("erp:as_case", "AS 건", "", "i-wrench", "order_as_cycles", "",
              "order_as_cycles + orders.as_axis_status", True, "상태 · 방문 날만(주문 읽기 안)", False),
)

_BY_TYPE: dict[str, ErpObject] = {obj.type: obj for obj in OBJECT_TYPES}


def get_type(code: object) -> Optional[ErpObject]:
    """코드 이름('erp:order') 또는 짧은 이름('order') → 물건 종류(모르면 ``None``)."""
    if not isinstance(code, str):
        return None
    return _BY_TYPE.get(code) or _BY_TYPE.get(f"erp:{code}")


@dataclass(frozen=True)
class OrderProp:
    """주문 속성 하나 — 화면 이름 · 실제 정본 칸 · 값 모양 · 읽기 · 쓰기 갈래 · 거치는 할 일 이름 · 덧말."""

    key: str
    name: str
    column: str
    shape: str
    access: str  # ACCESS_LABELS 키
    via: tuple[str, ...] = ()  # 쓰기를 맡는 할 일 이름(foms/services/erp_actions/registry.py ACTIONS)
    note: str = ""

    @property
    def access_label(self) -> str:
        """읽기 · 쓰기 갈래 화면 말."""
        return ACCESS_LABELS[self.access]


ORDER_PROPS: tuple[OrderProp, ...] = (
    OrderProp("order_id", "주문 번호", "orders.id", "번호(화면 #<번호>)", "read"),
    OrderProp("stage", "상태", "orders.erp_stage_code ← structured_data.workflow.stage · AS 축 orders.as_axis_status",
              "단계 여덟 + AS 축", "action", ("advance_stage",), "orders.status 는 옛 화면용 비춤 값이라 정본이 아니다"),
    OrderProp("customer_name", "손님 이름", "structured_data.parties.customer.name", "글", "masked", (), "AI 에 안 감"),
    OrderProp("phone", "전화", "structured_data.parties.customer.phone · 숫자만 orders.erp_phone_digits", "전화",
              "masked", (), "AI 에 안 감"),
    OrderProp("address", "현장 주소", "structured_data.site.address_full(없으면 address_main)", "주소 → 현장", "masked",
              (), "AI 에 안 감 · 지방 여부만 읽음"),
    OrderProp("items", "품목", "structured_data.items[]", "목록 → 주문 품목", "person", (),
              "판 1 에 품목 고치기 할 일 없음 · 이름만 가림 검사 뒤 읽음"),
    OrderProp("measurement_date", "실측 날짜", "structured_data.schedule.measurement.date · orders.erp_measurement_date",
              "날짜 · 시간대(예정) → 방문", "action", ("move_measurement",), "시간대는 예정 값"),
    OrderProp("construction_date", "시공 날짜",
              "structured_data.schedule.construction.date · orders.erp_construction_date", "날짜 · 시간대 → 방문",
              "action", ("schedule_construction", "move_construction")),
    OrderProp("manager", "담당 영업", "structured_data.parties.manager(대표 .name · 여러 명 .names)", "연결 → 직원",
              "person", (), "화면에만 · AI 에 안 감"),
    OrderProp("payment_amount", "결제 금액", "orders.payment_amount ← structured_data.payment · pricing", "금액", "money",
              (), "AI 에 안 감"),
)


def masked_props() -> tuple[OrderProp, ...]:
    """AI 에 가지 않는 주문 속성(가림 · 돈)."""
    return tuple(prop for prop in ORDER_PROPS if prop.access in ("masked", "money"))

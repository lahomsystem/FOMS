"""ERP 물건 이름표 · 읽기 도구(설계서 2026-11-14-foms-graft 3.2 · 3.7).

완료 기준: 물건 종류 10개 · 정본 표가 지금 표 · 속성 표가 설계서 '실제 정본' 칸(옛 칸 아님) · 읽기 도구가 허용 목록 칸 밖을 읽지
않음 · 손님 이름 · 전화 · 주소 · 금액 · 메모 · 협력사 · 직원 연락처를 어떤 돌려준 값에도 싣지 않음 · 가림에 걸리는 품목 이름 ·
시간대는 그 칸만 빠짐 · 담당 영업 이름은 화면 칸에만(모델 줄에 없음) · 방문 상태 · 실측 시간대는 '예정' · 주문 키.
지어낸 값만 쓴다(전화 꼴은 실행 때 만든다). DB · 바깥 호출 없음.
"""

from __future__ import annotations

import dataclasses
import datetime

import pytest

from db import Base
from foms.services.cs_agent.brain_cases import QUOTE
from foms.services.erp_actions.registry import ACTIONS
from foms.services.erp_ontology import objects, read
from models import Order

PHONE = "01" + "0" + "5550" + "1234"  # 합성 휴대폰(실행 때 만든다)
STAFF_PHONE = "01" + "0" + "5550" + "9876"
NAME = "합성손님"
ADDRESS = "합성시 가상구 시험로 7"
AMOUNT = 4321987
MEMO = "합성 내부 메모 비밀글"
PARTNER = "합성 협력상회"
MANAGER = "합성담당"
SECRETS = (NAME, PHONE, PHONE[-4:], STAFF_PHONE, STAFF_PHONE[-4:], ADDRESS, "시험로", str(AMOUNT), "4,321,987", MEMO,
           PARTNER, MANAGER)


def make_order(*, stage="MEASURE", as_status=None, products=("합성 붙박이장",), measure_time="10:00~12:00",
               construction_time="오전", **extra):
    items = [{"product_name": name, "price": AMOUNT, "memo": MEMO} for name in products]
    data = {
        "parties": {"customer": {"name": NAME, "phone": PHONE}, "manager": {"name": MANAGER, "phone": STAFF_PHONE},
                    "orderer": {"name": PARTNER, "phone": STAFF_PHONE}},
        "site": {"address_full": ADDRESS, "address_main": ADDRESS},
        "payment": {"total": AMOUNT}, "pricing": {"total": AMOUNT},
        "notes": {"construction_note": MEMO, "memo": MEMO},
        "items": items,
        "schedule": {"measurement": {"date": "2026-11-20", "time": measure_time},
                     "construction": {"date": "2026-12-03", "time": construction_time},
                     "as_visit": {"date": "2026-12-10"}},
        "workflow": {"stage": stage},
    }
    values = dict(id=41, received_date="2026-11-01", customer_name=NAME, phone=PHONE, address=ADDRESS, product=MEMO,
                  notes=MEMO, manager_name=MANAGER, payment_amount=AMOUNT, regional_memo=MEMO, options=MEMO,
                  measurement_date="2026-11-01", measurement_time=MEMO, status="RECEIVED", is_erp_order=True,
                  erp_stage_code=stage, erp_stage_updated_at=datetime.datetime(2026, 11, 10, 3, 0),
                  erp_measurement_date="2026-11-20", erp_construction_date="2026-12-03",
                  shipping_scheduled_date="2026-12-01", erp_phone_digits=PHONE, is_regional=True,
                  is_self_measurement=False, as_axis_status=as_status, erp_owner_team_code="SALES",
                  structured_data=data)
    values.update(extra)
    return Order(**values)


def returned_texts(order):
    """읽기 도구가 돌려준 모든 글(담당 영업 화면 칸 빼고) — 카드 값 · 방문 값 · 모델 줄."""
    card = read.order_card(order)
    found = read.visits(order)
    values = {k: v for k, v in dataclasses.asdict(card).items() if k != "manager_label"}
    texts = [str(v) for v in values.values()] + [str(v) for visit in found for v in visit.as_dict().values()]
    return texts + read.prompt_lines(card, found)


# ── 물건 목록 · 속성 표 ────────────────────────────────────────────────────
def test_ten_object_types_point_at_existing_tables():
    codes = [obj.type for obj in objects.OBJECT_TYPES]
    assert codes == ["erp:order", "erp:order_item", "erp:customer", "erp:site", "erp:visit", "erp:drawing",
                     "erp:production_run", "erp:shipment", "erp:partner_order", "erp:as_case"]
    assert all(obj.table in Base.metadata.tables for obj in objects.OBJECT_TYPES)  # 새 표 없음 — 지금 표만
    assert {obj.slug for obj in objects.OBJECT_TYPES if obj.readable} == {"order", "order_item", "site", "visit",
                                                                          "as_case"}
    assert [obj.slug for obj in objects.OBJECT_TYPES if obj.masked] == ["customer", "site"]
    assert objects.get_type("order") is objects.get_type("erp:order") is objects.OBJECT_TYPES[0]
    assert objects.get_type("nope") is None and objects.get_type(None) is None


def test_order_props_use_the_canonical_columns_not_the_legacy_ones():
    props = {prop.key: prop for prop in objects.ORDER_PROPS}
    assert len(props) == 10
    legacy = ("orders.status", "orders.measurement_date", "orders.customer_name", "orders.phone", "orders.address")
    for prop in props.values():
        assert not any(prop.column == old or prop.column.startswith(old + " ") for old in legacy), prop.key
        assert set(prop.via) <= set(ACTIONS), prop.key  # 쓰기는 할 일 이름으로만
        assert prop.access in objects.ACCESS_LABELS
    assert props["stage"].column.startswith("orders.erp_stage_code") and props["stage"].via == ("advance_stage",)
    assert props["customer_name"].column == "structured_data.parties.customer.name"
    assert props["measurement_date"].via == ("move_measurement",) and props["measurement_date"].access == "action"
    assert props["construction_date"].via == ("schedule_construction", "move_construction")
    assert {prop.key for prop in objects.masked_props()} == {"customer_name", "phone", "address", "payment_amount"}


# ── 읽기 도구 ────────────────────────────────────────────────────────────
def test_order_card_reads_the_flat_columns_first():
    card = read.order_card(make_order(stage="PRODUCTION", as_status="RECEIVED"))
    assert (card.order_id, card.stage, card.stage_label, card.stage_since) == (41, "PRODUCTION", "생산",
                                                                              datetime.date(2026, 11, 10))
    assert (card.products, card.owner_team, card.regional, card.self_measure) == (("합성 붙박이장",), "SALES", True,
                                                                                False)
    assert (card.as_state, card.as_label, card.key) == ("RECEIVED", "AS 접수됨", "erp:order/41")
    assert card.manager_label == MANAGER  # 화면 전용 칸에만


def test_nothing_private_reaches_any_returned_value():
    for stage, as_status in (("MEASURE", None), ("CS", "IN_PROGRESS"), ("COMPLETED", "COMPLETED")):
        texts = returned_texts(make_order(stage=stage, as_status=as_status))
        assert texts, stage
        leaks = [secret for secret in SECRETS for text in texts if secret in text]
        assert leaks == [], (stage, leaks)


def test_the_tool_reads_no_column_outside_the_allow_list():
    class Strict:
        """허용 목록 밖 칸을 읽으면 바로 실패하는 주문."""

        def __init__(self, order):
            self.__dict__["_order"] = order

        def __getattr__(self, name):
            if name not in (*read.ALLOWED_COLUMNS, "structured_data"):
                raise AssertionError(f"허용 목록 밖 칸: {name}")
            return getattr(self.__dict__["_order"], name)

    order = Strict(make_order(as_status="RECEIVED"))
    card, found = read.order_card(order), read.visits(order)
    assert card.order_id == 41 and len(found) == 4 and read.prompt_lines(card, found)
    assert set(read.ALLOWED_COLUMNS) <= set(Order.__table__.c.keys())


def test_masked_check_drops_only_the_leaking_product_name_and_time():
    leaking = f"합성 수납장 {PHONE}"
    order = make_order(products=("합성 붙박이장", leaking, "합성 붙박이장", "합성 신발장"),
                       measure_time=f"연락 {STAFF_PHONE}")
    card, found = read.order_card(order), read.visits(order)
    assert card.products == ("합성 붙박이장", "합성 신발장")  # 겹침 · 걸린 이름만 빠진다
    measurement = next(v for v in found if v.kind == "measurement")
    assert measurement.time == "" and measurement.day == datetime.date(2026, 11, 20)  # 시간대만 빠지고 날은 남는다
    assert not any(STAFF_PHONE in line or PHONE in line for line in read.prompt_lines(card, found))


def test_cancelled_items_and_long_names_are_left_out_and_products_stop_at_five():
    names = [f"합성 품목 {chr(0xAC00 + i)}" for i in range(7)]
    order = make_order(products=names)
    order.structured_data["items"][0]["cancel"] = {"at": "2026-11-02"}
    order.structured_data["items"].insert(1, {"product_name": "합" * 41})  # 상한(40자) 넘는 이름 — 앞자리에 둬도 빠진다
    assert read.order_card(order).products == tuple(names[1:6])


def test_visits_states_and_measurement_time_is_planned():
    found = read.visits(make_order(stage="MEASURE", as_status="RECEIVED"))
    assert [(v.kind, v.day.isoformat(), v.state) for v in found] == [
        ("measurement", "2026-11-20", "planned"), ("shipping", "2026-12-01", "planned"),
        ("construction", "2026-12-03", "planned"), ("as_visit", "2026-12-10", "planned")]
    measurement, construction = found[0], found[2]
    assert (measurement.time_label, construction.time_label) == ("10:00~12:00 예정", "오전")
    assert measurement.as_dict() == {"kind": "measurement", "label": "실측", "day": "2026-11-20",
                                     "time_label": "10:00~12:00 예정", "state": "planned", "state_label": "잡힘"}
    done = {v.kind: v.state for v in read.visits(make_order(stage="CS", as_status="COMPLETED"))}
    assert done == {"measurement": "done", "construction": "done", "shipping": "done", "as_visit": "done"}
    middle = {v.kind: v.state for v in read.visits(make_order(stage="PRODUCTION"))}
    assert middle == {"measurement": "done", "construction": "planned", "shipping": "planned"}  # AS 이력 없으면 AS 방문 없음


def test_empty_order_gives_a_bare_card_and_no_visits():
    order = Order(id=5, received_date="2026-11-01", customer_name=NAME, phone=PHONE, address=ADDRESS, product=MEMO,
                  structured_data=None, erp_stage_code="WEIRD", erp_owner_team_code="NOPE")
    card = read.order_card(order)
    assert (card.stage, card.stage_label, card.owner_team, card.products, card.manager_label) == ("", "", "", (), "")
    assert read.visits(order) == []
    assert read.prompt_lines(card, []) == [read.PROMPT_HEAD, "주문 번호: #5"]


def test_prompt_lines_quote_human_text_and_leave_out_the_manager():
    card = read.order_card(make_order(stage="MEASURE", as_status="RECEIVED"))
    lines = read.prompt_lines(card, read.visits(make_order(stage="MEASURE", as_status="RECEIVED")))
    assert lines[0] == read.PROMPT_HEAD and "주문 번호: #41" in lines
    assert "단계: 실측 (2026-11-10(화)부터)" in lines and "담당 팀: 영업팀" in lines and "AS: AS 접수됨" in lines
    assert "실측 날: 2026-11-20(금) · 잡힘" in lines and f"{QUOTE}10:00~12:00" in lines
    assert f"{QUOTE}합성 붙박이장" in lines and f"{QUOTE}오전" in lines
    assert not any(MANAGER in line for line in lines)


def test_order_key_round_trips():
    assert read.order_key(7) == "erp:order/7" and read.order_id_of("erp:order/7") == 7
    for bad in (0, -1, True, "7", None, 7.0):
        with pytest.raises(ValueError):
            read.order_key(bad)
    for bad in ("erp:order/", "erp:order/07", "erp:order/x", "common/door", None, 7):
        assert read.order_id_of(bad) is None

"""새 주문 안내 — 같은 고객의 진행 중 주문 찾기 (설계서 2026-11-20 6.1 · M16).

완료 기준: 전화로 걸림(번호를 두 개 적은 주문 · 입력에 두 번호 포함) · 주소(도로명 + 건물번호 + 동 · 호)로 걸림 ·
이름만 같으면 안 걸림 · 주소는 양쪽 호수 + 같은 시 · 구일 때만 · 자기 자신 · 초안(상태 DRAFT · 숨은 초안 표식) · 휴지통 · 완료 단계 · 비 ERP 주문 · 자리표시자
전화는 빠짐 · 완료됐는데 AS 가 열린 주문은 진행 중이 아님 · 세 건까지 + 더 걸린 건수 · 범위 조건.
합성 고객 · 합성 번호만 쓴다.
"""

from __future__ import annotations

from db import db_session
from foms.services.common.address_query import same_unit_address, unit_address_key
from foms.services.orders.open_order_lookup import (
    DONE_STAGE_CODES,
    OPEN_ORDER_NOTICE_LIMIT,
    find_open_orders_for_customer,
    find_open_orders_with_more,
)
from models import Order, OrderScheduleDate

PHONE = "010-5550-1234"
PHONE_DIGITS = "01055501234"
OTHER = "010-5550-9876"
OTHER_DIGITS = "01055509876"
HOME = "경기도 화성시 동탄구 시험대로10길 20 (가상동, 합성아파트) 2505동 1103호"
HOME_SHORT = "시험대로10길 20 합성아파트 2505동 1103호"
NEIGHBOR = "시험대로10길 20 합성아파트 2505동 1104호"


def add_order(*, name="합성고객", phone=PHONE, digits=PHONE_DIGITS, address="합성시 가상구 다른로 1",
              stage="PRODUCTION", status=None, erp=True, deleted=False, meta_draft=False, as_status=None,
              partner_org_id=None, construction=()):
    sd = {"parties": {"customer": {"name": name, "phone": phone}}, "workflow": {"stage": stage}}
    if meta_draft:
        sd["meta"] = {"draft": True}
    order = Order(
        received_date="2026-11-01", customer_name=name, phone=phone, address=address, product="합성 붙박이장",
        status=status or (stage if stage else "RECEIVED"), is_erp_order=erp, erp_stage_code=stage if erp else None,
        erp_phone_digits=digits if erp else None, structured_data=sd if erp else None, as_axis_status=as_status,
        partner_org_id=partner_org_id, deleted_at="2026-11-01 10:00:00" if deleted else None,
    )
    db_session.add(order)
    db_session.flush()
    for index, date in enumerate(construction):
        db_session.add(OrderScheduleDate(order_id=order.id, kind="construction", date=date,
                                         source="beta_item", item_index=index))
    db_session.commit()
    return order


def ids(rows):
    return [row["order_id"] for row in rows]


def test_phone_match_returns_stage_dates_and_reason(app):
    hit = add_order(construction=("2026-11-17", "2026-11-05", "2026-11-17"))
    add_order(phone=OTHER, digits=OTHER_DIGITS)  # 대조군: 다른 번호

    rows = find_open_orders_for_customer(db_session, phone=PHONE)

    assert rows == [{
        "order_id": hit.id, "stage_code": "PRODUCTION", "stage_label": "생산",
        "construction_dates": ["2026-11-05", "2026-11-17"], "address": "합성시 가상구 다른로 1",
        "customer_name": "합성고객", "reason": "phone",
    }]


def test_two_numbers_in_one_field_match_either_number(app):
    both = add_order(phone=f"{PHONE} / {OTHER}", digits=PHONE_DIGITS + OTHER_DIGITS)

    assert ids(find_open_orders_for_customer(db_session, phone=OTHER)) == [both.id]
    assert ids(find_open_orders_for_customer(db_session, phone=PHONE)) == [both.id]
    # 번호 조각이 정확히 같아야 한다 — 이어 붙은 숫자 사이에 걸친 번호는 남의 번호다.
    straddle = PHONE_DIGITS[3:] + OTHER_DIGITS[:3]
    assert find_open_orders_for_customer(db_session, phone=straddle) == []


def test_input_with_two_numbers_checks_both(app):
    first = add_order()
    second = add_order(phone=OTHER, digits=OTHER_DIGITS)

    rows = find_open_orders_for_customer(db_session, phone=f"{PHONE}, {OTHER}")

    assert sorted(ids(rows)) == sorted([first.id, second.id])


def test_address_match_needs_road_building_and_unit(app):
    same_home = add_order(name="가족", phone=OTHER, digits=OTHER_DIGITS, address=HOME)
    add_order(name="이웃", phone="010-5550-0001", digits="01055500001", address=NEIGHBOR)  # 대조군: 옆집

    rows = find_open_orders_for_customer(db_session, phone="", address=HOME_SHORT)

    assert ids(rows) == [same_home.id]
    assert rows[0]["reason"] == "address"
    # 동 · 호가 없는 주소는 단지 단위라 견주지 않는다.
    assert find_open_orders_for_customer(db_session, phone="", address="시험대로10길 20 합성아파트") == []


def test_phone_reason_wins_and_comes_first(app):
    by_address = add_order(name="가족", phone=OTHER, digits=OTHER_DIGITS, address=HOME)
    by_both = add_order(address=HOME)

    rows = find_open_orders_for_customer(db_session, phone=PHONE, address=HOME_SHORT)

    assert [(row["order_id"], row["reason"]) for row in rows] == [(by_both.id, "phone"), (by_address.id, "address")]


def test_name_only_does_not_match(app):
    add_order(name="합성고객", phone=OTHER, digits=OTHER_DIGITS)

    assert find_open_orders_for_customer(db_session, phone="010-5550-7777", name="합성고객") == []
    assert find_open_orders_for_customer(db_session, phone="", name="합성고객") == []


def test_excludes_self_drafts_trash_completed_and_non_erp(app):
    open_order = add_order(stage="MEASURE")
    me = add_order(stage="RECEIVED")
    add_order(stage="RECEIVED", status="DRAFT")  # 쓰다 만 PC 초안 줄
    add_order(stage="RECEIVED", meta_draft=True)  # 숨은 초안(상태는 DRAFT 가 아닌데 표식이 켜짐)
    add_order(deleted=True)  # 휴지통
    add_order(stage="COMPLETED")
    add_order(stage="AS_COMPLETED")
    add_order(stage="완료")  # 옛 한글 단계 값
    add_order(stage="COMPLETED", status="AS_RECEIVED", as_status="RECEIVED")  # 완료 + 열린 AS 는 진행 중이 아니다
    add_order(erp=False)  # 옛 폼 주문

    rows = find_open_orders_for_customer(db_session, phone=PHONE, exclude_order_id=me.id)

    assert ids(rows) == [open_order.id]
    # 대조군: 자기 자신을 빼지 않으면 같이 걸린다.
    assert ids(find_open_orders_for_customer(db_session, phone=PHONE)) == [me.id, open_order.id]


def test_as_status_with_open_main_flow_is_in_progress(app):
    order = add_order(stage="PRODUCTION", status="AS_RECEIVED", as_status="RECEIVED")

    assert ids(find_open_orders_for_customer(db_session, phone=PHONE)) == [order.id]


def test_placeholder_phones_are_ignored(app):
    add_order(phone="000-0000-0000", digits="00000000000")
    add_order(phone="010-0000-0000", digits="01000000000")
    add_order(phone="", digits=None)

    for placeholder in ("000-0000-0000", "010-0000-0000", "000000000", "0000", "", None):
        assert find_open_orders_for_customer(db_session, phone=placeholder) == [], placeholder


def test_limit_and_more_count(app):
    made = [add_order(stage="MEASURE") for _ in range(5)]

    rows, more = find_open_orders_with_more(db_session, phone=PHONE)

    assert OPEN_ORDER_NOTICE_LIMIT == 3
    assert ids(rows) == [order.id for order in reversed(made)][:3]  # 새 주문 먼저
    assert more == 2
    assert ids(find_open_orders_for_customer(db_session, phone=PHONE, limit=1)) == [made[-1].id]
    exact, none_more = find_open_orders_with_more(db_session, phone=PHONE, limit=5)
    assert len(exact) == 5 and none_more == 0


def test_scope_clause_narrows_the_population(app):
    add_order()
    scoped = add_order(partner_org_id=7)

    rows = find_open_orders_for_customer(db_session, phone=PHONE, scope_clause=Order.partner_org_id == 7)

    assert ids(rows) == [scoped.id]


def test_legacy_stage_label_and_missing_stage(app):
    no_stage = add_order(stage=None, status="RECEIVED")
    korean = add_order(stage="실측")

    rows = {row["order_id"]: row for row in find_open_orders_for_customer(db_session, phone=PHONE)}

    assert rows[no_stage.id]["stage_label"] == "주문접수" and rows[no_stage.id]["stage_code"] is None
    assert rows[korean.id]["stage_label"] == "실측"
    assert rows[korean.id]["construction_dates"] == []


# --------------------------------------------------------------------------- #
# 주소 축은 같은 집만 — 호수가 양쪽에 있고 적힌 시 · 구가 같을 때 (검수 C-1)
# --------------------------------------------------------------------------- #
def test_address_without_unit_number_does_not_match_another_home_in_the_complex(app):
    add_order(name="갑", phone=OTHER, digits=OTHER_DIGITS, address="경기 화성시 동탄대로 100 래미안2차")
    add_order(name="을", phone="010-5550-0002", digits="01055500002", address="동탄대로 100 래미안2차 상가 2층")

    # 단지 이름 속 '2' 가 동 · 호 키로 잡혀도 호수가 없으면 남의 집이다.
    assert find_open_orders_for_customer(db_session, phone="", address="동탄대로 100 래미안2차 아파트") == []


def test_address_in_another_city_does_not_match(app):
    add_order(name="부산 고객", phone=OTHER, digits=OTHER_DIGITS, address="부산 해운대구 테헤란로 100 3동 101호")
    add_order(name="부산시 고객", phone="010-5550-0003", digits="01055500003",
              address="부산광역시 해운대구 테헤란로 100 3동 101호")

    assert find_open_orders_for_customer(db_session, phone="", address="서울 강남구 테헤란로 100 3동 101호") == []


def test_same_unit_written_differently_still_matches_by_address(app):
    seoul = add_order(name="가족", phone=OTHER, digits=OTHER_DIGITS,
                      address="서울특별시 강남구 테헤란로 100 (역삼동) 래미안 3동 101호")
    add_order(name="부산", phone="010-5550-0004", digits="01055500004",
              address="부산 해운대구 테헤란로 100 3동 101호")  # 대조군: 다른 시의 같은 길 이름

    rows = find_open_orders_for_customer(db_session, phone="", address="서울시 강남구 테헤란로 100 3동 101호")
    no_region = find_open_orders_for_customer(db_session, phone="", address="테헤란로 100 3동 101호")

    assert [(row["order_id"], row["reason"]) for row in rows] == [(seoul.id, "address")]
    # 한쪽만 시 · 구를 적었으면 시 · 구로 가르지 않는다(부산 주문도 같은 집 후보다).
    assert seoul.id in ids(no_region) and len(no_region) == 2


def test_phone_match_ignores_the_address_rule(app):
    busan = add_order(address="부산 해운대구 테헤란로 100 3동 101호")
    no_unit = add_order(address="경기 화성시 동탄대로 100 래미안2차")

    rows = find_open_orders_for_customer(db_session, phone=PHONE, address="서울 강남구 테헤란로 100 3동 101호")

    assert [(row["order_id"], row["reason"]) for row in rows] == [(no_unit.id, "phone"), (busan.id, "phone")]


def test_unit_address_key_itself_is_unchanged_for_other_callers():
    # 네이버 붙이기 후보 · 상담 AI 는 느슨한 키를 그대로 쓴다 — 엄격한 견주기는 새 함수에만 있다.
    assert unit_address_key("경기 화성시 동탄대로 100 래미안2차") == ("동탄대로", "", "100", "2")
    assert unit_address_key("서울 강남구 테헤란로 100 3동 101호") == unit_address_key("부산 해운대구 테헤란로 100 3동 101호")
    assert same_unit_address("서울 강남구 테헤란로 100 3동 101호", "서울 강남구 테헤란로 100 3동 101호") is True
    assert same_unit_address("테헤란로 100 3동 101호", "테헤란로 100 3동 102호") is False


# --------------------------------------------------------------------------- #
# 단계 칸이 빈 옛 주문은 상태로 완료를 본다 · 따옴표 붙은 옛 완료 값 (검수 C-2 · C-7)
# --------------------------------------------------------------------------- #
def test_missing_stage_with_done_status_is_not_in_progress(app):
    add_order(stage=None, status="COMPLETED")
    add_order(stage=None, status="AS_COMPLETED")
    add_order(stage=None, status="완료")
    open_legacy = add_order(stage=None, status="MEASURE")  # 대조군: 단계 칸이 비어도 상태가 진행 중

    assert ids(find_open_orders_for_customer(db_session, phone=PHONE)) == [open_legacy.id]


def test_quoted_legacy_done_stage_values_are_done(app):
    for stage in ('"COMPLETED"', '"AS_COMPLETED"', '"완료"', '"AS완료"'):
        add_order(stage=stage, status="COMPLETED")
    in_progress = add_order(stage='"PRODUCTION"', status="PRODUCTION")  # 대조군: 따옴표 붙은 진행 단계

    assert ids(find_open_orders_for_customer(db_session, phone=PHONE)) == [in_progress.id]
    assert {'"COMPLETED"', '"AS_COMPLETED"'} <= set(DONE_STAGE_CODES)

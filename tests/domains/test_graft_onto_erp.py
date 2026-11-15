"""온톨로지 ERP 물건 칸(설계서 2026-11-14-foms-graft 3.8) — ``erp_read`` 스위치가 켜진 사람에게만.

1. 꺼짐(``erp=False`` · 처음 값): 답이 지금과 같다 — ``erp`` 칸 없음 · 능력 질문 ERP 재료는 '없음' · 점수 그대로.
2. 켬: 물건 종류 열 · 할 일 종류(감싼 기능 · 수준 · 어디서 결정) · ERP 재료가 드는 질문 수 · ERP 재료는 읽기 도구가 있는 종류면
   '있음'(주문 · 일정=방문) · 켜기 전 점수를 같이 싣는다(같은 모집단 대조군).
3. ERP 물건 상세: 주문 속성 ↔ 실제 정본 칸(옛 칸 아님) · 가린 칸 수 · 연결 · 할 일 · 질문 번호. 모르는 종류는 ``None``.
합성 항목만 · DB 는 회사 지식 표만 읽는다(ERP 물건은 코드 목록).
"""

from __future__ import annotations

import json

import pytest

from db import db_session
from foms.services.brain.ontology_cqs import CQS, ERP_NEEDS
from foms.services.brain.ontology_view import erp_ready_needs, ontology_erp_type, ontology_summary
from foms.services.brain.scope import viewer_of
from foms.services.erp_actions.registry import ACTIONS
from foms.services.erp_ontology.objects import OBJECT_TYPES, ORDER_PROPS
from tests.support.brain_screen_support import TODAY, world

ERP_CQS = [cq.cq_id for cq in CQS if any(n in ERP_NEEDS for n in cq.needs)]


@pytest.fixture
def admin(app):
    return viewer_of(world(db_session)["admin"])


def _rows(summary):
    return {row["id"]: row for row in summary["cq"]["rows"]}


def test_switch_off_answer_is_todays_answer(admin):
    default = ontology_summary(db_session, admin, today=TODAY)
    off = ontology_summary(db_session, admin, today=TODAY, erp=False)
    assert json.dumps(off, sort_keys=True) == json.dumps(default, sort_keys=True)
    assert "erp" not in off and "covered_before" not in off["cq"]
    assert all(not n["have"] for row in off["cq"]["rows"] for n in row["needs"] if n["erp"])  # ERP 재료는 '없음'
    assert not _rows(off)["P09"]["covered"]  # 주문만 드는 질문 — 꺼짐이면 못 푼다


def test_switch_on_adds_erp_types_actions_and_counts_erp_material(admin):
    off = ontology_summary(db_session, admin, today=TODAY)
    on = ontology_summary(db_session, admin, today=TODAY, erp=True)
    assert {k: v for k, v in on.items() if k not in ("cq", "erp")} == {k: v for k, v in off.items() if k != "cq"}
    erp = on["erp"]
    assert [t["type"] for t in erp["types"]] == [o.type for o in OBJECT_TYPES]
    assert {t["type"] for t in erp["types"] if t["readable"]} == {"erp:order", "erp:order_item", "erp:site",
                                                                    "erp:visit", "erp:as_case"}
    assert [a["name"] for a in erp["actions"]] == list(ACTIONS)
    where = {a["name"]: a["where"] for a in erp["actions"]}
    assert where["cancel_order"] == "PC · 사장님" and where["advance_stage"] == "폰 승인"  # D206 — 바로가기 아님(T14)
    assert where["schedule_construction"] == "폰 승인" and where["assign_draftsman"] == "PC 승인"
    assert {a["name"]: a["level_label"] for a in erp["actions"]}["cancel_order"] == "사람만"
    assert erp["cq_erp"] == len(ERP_CQS) > 0
    assert erp_ready_needs() == frozenset(ERP_NEEDS)  # 주문 · 일정(방문) 모두 읽기 도구가 있다
    assert all(n["have"] for row in on["cq"]["rows"] for n in row["needs"] if n["erp"])
    assert on["cq"]["covered_before"] == off["cq"]["covered"]  # 켜기 전 점수 — 같은 모집단
    assert on["cq"]["covered"] > off["cq"]["covered"]
    assert _rows(on)["P09"]["covered"] and not _rows(off)["P09"]["covered"]  # 재료가 생겨 풀린 질문(대조군 P09 꺼짐)
    non_erp = [cq.cq_id for cq in CQS if cq.cq_id not in ERP_CQS]
    assert all(_rows(on)[i]["covered"] == _rows(off)[i]["covered"] for i in non_erp)  # ERP 아닌 질문은 그대로


def test_order_detail_points_at_the_real_columns_not_old_ones():
    order = ontology_erp_type("order")
    assert order is not None and ontology_erp_type("erp:order") == order
    assert order["source"]["table"] == "orders" and order["readable"] is True and order["hidden"] is False
    props = {p["key"]: p for p in order["props"]}
    assert [p["key"] for p in order["props"]] == [p.key for p in ORDER_PROPS]
    assert props["customer_name"]["column"] == "structured_data.parties.customer.name"
    assert props["stage"]["column"].startswith("orders.erp_stage_code") and props["stage"]["via"] == "단계 넘기기"
    assert props["construction_date"]["via"] == "시공 잡기 · 방문 옮기기(시공)"
    assert props["payment_amount"]["access_label"] == "사람만 · 돈"
    columns = " ".join(p["column"] for p in order["props"])
    for old in ("orders.status ", "orders.customer_name", "orders.phone ", "orders.address"):
        assert old not in columns + " ", old
    assert order["masked"] == 4  # 손님 이름 · 전화 · 주소 · 결제 금액
    assert {(l["rel"], l["type"]) for l in order["links"]} >= {("손님", "erp:customer"), ("방문", "erp:visit")}
    assert {a["name"] for a in order["actions"]} == {n for n, s in ACTIONS.items() if s.target == "erp:order"}
    assert "P09" in order["cq"] and "S01" in order["cq"]


def test_visit_and_masked_types_and_unknown_kind():
    visit = ontology_erp_type("visit")
    assert visit["props"] == [] and visit["masked"] == 0
    assert {"S01", "S02", "A01"} <= set(visit["cq"]) and "P09" not in visit["cq"]  # 일정 재료 = 방문
    assert {(l["direction"], l["type"]) for l in visit["links"]} == {("in", "erp:order"), ("in", "erp:as_case")}
    assert {a["name"] for a in visit["actions"]} == {n for n, s in ACTIONS.items() if s.target == "erp:visit"}
    customer = ontology_erp_type("customer")
    assert customer["hidden"] is True and customer["readable"] is False and customer["cq"] == []
    assert ontology_erp_type("no_such") is None and ontology_erp_type(None) is None

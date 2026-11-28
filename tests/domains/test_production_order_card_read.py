"""'도면 없음' 주문 카드(key ``@order``) 읽기 — 날짜 줄 칸 아래 이름 · 아침 칩 · 판 카드 한 장 · '내 공정' · '작업 중' · 탭 숫자 ·
쿼리 수 · 조사표에서 "아무 일 없음"으로 본 곳 확인(설계서 2026-11-28-production-my-steps-flow §3-5, 조사 전문 48줄).

되돌리면 실패: 0장 생산 주문이 '도면 없음' 기다림 글로만 남음 · 판 카드에 ``order_card`` 표지 없음 · 담아도 판에서 안 빠짐 · 내 공정 · 작업 중에
안 나옴 · 탭 숫자가 안 셈 · 칸 아래 이름이 "미정" · 아침 칩에서 빠짐 · 0장 주문을 더해 쿼리가 늚 · 2공장 계정에 누를 수 있는 카드로 나옴 ·
작업 시트에 "도면 1/1" · 보류 알람이 주문 카드 작업자에게 안 감. 이름은 모두 지어낸 값이다(김재단 · 박엣지 · 박반장, 고객 정하늘 · 윤봄).
"""
from __future__ import annotations

import copy
import datetime

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.drawing_fix_progress import drawings_progress
from foms.services.orders.drawing_factory import hand_checked_parts
from foms.services.production import floor_alarm_text as T
from foms.services.production.factory_home import factory_finished
from foms.services.production.floor_alarm_rules import Reads, plan
from foms.services.production.part_marks_query import order_marks
from models import Order, ProductionPartMark
from tests.domains.test_production_flow_read import (  # noqa: F401 — cohort = 픽스처
    HOME,
    _cards,
    _ctx,
    _order,
    _q,
    _tomorrow,
    cohort,
)
from tests.support.production_factory_seed import TABLET, factory_user
from tests.support.production_part_claim_seed import login, make_user

KEY = "@order"


def _press(client, who, oid: int, part: str, action: str, seen: str, **extra):
    login(client, who)
    resp = client.post("/api/production/part-marks",
                       json={"order_id": oid, "drawing_key": KEY, "part": part, "action": action, "seen": seen, **extra})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]


def _row_of(page: dict, oid: int) -> dict:
    return next(r for r in page["pane"]["make_rows"] if int(r["id"]) == oid)


def _order_cards(pane: dict) -> list[dict]:
    return [c for c in pane["cards"] if c.get("order_card")]


# --------------------------------------------------------------------------- #
# 날짜 줄 칸 아래 이름 · 아침 칩
# --------------------------------------------------------------------------- #
def test_date_row_cell_names_the_order_card_worker_and_finisher(client, cohort):
    kim, lead = make_user("김재단", part="cut"), make_user("박반장", lead=True)
    bare = _order("정하늘", 0)
    _press(client, kim, bare.id, "cut", "take", "none")
    cut = _row_of(_ctx(client, lead), bare.id)["part_holders"][0]
    assert (cut["kind"], cut["name"], cut["label"]) == ("held", "김재단", "재단 0/1")  # "미정" 이 아니다(조사 3 · 10)
    assert cut["aria"].startswith("재단 0/1 · 1장 미완료")
    _press(client, kim, bare.id, "cut", "done", "need")
    cut = _row_of(_ctx(client, lead), bare.id)["part_holders"][0]
    assert (cut["kind"], cut["name"], cut["label"]) == ("done", "김재단", "재단")
    edge = _row_of(_ctx(client, lead), bare.id)["part_holders"][1]
    assert (edge["kind"], edge["label"]) == ("none", "엣지")  # 주문 카드를 안 쓴 파트는 지금 그대로


def test_morning_chip_counts_an_overnight_order_card(client, cohort):
    kim = make_user("김재단", part="cut")
    bare = _order("정하늘", 0)
    _press(client, kim, bare.id, "cut", "take", "none")
    mark = db_session.query(ProductionPartMark).filter_by(order_id=bare.id, drawing_key=KEY, part="cut").one()
    yesterday = mark.picked_at - datetime.timedelta(days=1)
    holders = copy.deepcopy(mark.holders)
    holders[0]["at"] = yesterday.replace(tzinfo=datetime.timezone.utc).isoformat()
    mark.holders, mark.picked_at = holders, yesterday
    flag_modified(mark, "holders")
    db_session.commit()
    page = _ctx(client, kim)
    assert page["part_morning"]["count"] == 1  # 지금 장 = @order(조사 2)


# --------------------------------------------------------------------------- #
# 판 카드 · 내 공정 · 작업 중 · 탭 숫자
# --------------------------------------------------------------------------- #
def test_order_card_is_one_card_on_the_board_and_moves_to_my_steps(client, cohort):
    kim, lead = make_user("김재단", part="cut"), make_user("박반장", lead=True)
    bare, drawn = _order("정하늘", 0), _order("윤봄", 2)
    pane = _ctx(client, kim)["part_board"]["panes"][_tomorrow()]
    card = _order_cards(pane)[0]
    assert {k: card[k] for k in ("order_id", "key", "no", "of", "is_image", "order_card", "state")} == {
        "order_id": bare.id, "key": KEY, "no": 0, "of": 0, "is_image": False, "order_card": True, "state": "none"}
    assert card["customer_name"] == "정하늘" and card["item_label"] == "붙박이장" and len(card["others"]) == 3
    assert all(c["order_card"] is False for c in pane["cards"] if c["order_id"] == drawn.id)
    assert pane["no_drawing_rows"] == [] and pane["bulk"] == 2 and pane["counts"]["unseen"] == 2  # 일괄 기본 숫자에 안 든다
    _press(client, kim, bare.id, "cut", "take", "none")
    page = _ctx(client, kim)
    pane = page["part_board"]["panes"][_tomorrow()]
    assert _order_cards(pane) == [] and pane["mine_out"] == 1  # 담으면 판에서 빠진다
    mine = _cards(_ctx(client, kim, HOME + "?tab=mine")["my_steps"])
    assert [(c["key"], c["order_card"], c["part"]) for c in mine] == [(KEY, True, "cut")]
    assert page["counts"]["mine"] == 1 and page["counts"]["crew"] == 1
    crew = _ctx(client, lead, HOME + "?tab=crew")["crew"]
    assert [(g["name"], [c["key"] for c in g["cards"]]) for g in crew["people"]] == [("김재단", [KEY])]
    assert crew["none"]["counts"] == {"cut": 2, "edge": 3, "assemble": 3, "inspect": 3}  # 주문 카드도 미정 숫자에 든다
    edge_none = _ctx(client, lead, HOME + "?tab=crew&part=edge")["crew"]["none"]["cards"]
    assert [c["key"] for c in edge_none if c["order_id"] == bare.id] == [KEY]
    lead_pane = _ctx(client, lead, HOME + "?tab=parts&part=cut")["part_board"]["panes"][_tomorrow()]
    assert [c["key"] for c in _order_cards(lead_pane)] == [KEY]  # 반장 판은 안 빠진다


def test_not_production_orders_without_drawings_stay_in_the_wait_group(client, cohort):
    kim = make_user("김재단", part="cut")
    _order("정하늘", 0, stage="DRAWING")  # 도면 기다림 — 주문 카드 아님(대조군)
    pane = _ctx(client, kim)["part_board"]["panes"][_tomorrow()]
    assert _order_cards(pane) == [] and len(pane["wait_rows"]) == 1


def test_second_factory_account_sees_the_order_card_only_in_the_other_factory_group(client, cohort):
    f2 = factory_user("김재단", factory=2, part="cut")
    bare = _order("정하늘", 0)
    page = _ctx(client, f2)
    pane = page["part_board"]["panes"][_tomorrow()]
    assert _order_cards(pane) == [] and [c["key"] for c in pane["elsewhere"] if c["order_id"] == bare.id] == [KEY]
    assert page["counts"]["mine"] == 0


def test_adding_order_card_orders_adds_no_query(client, cohort):
    kim, admin = make_user("김재단", part="cut"), make_user("관리자", team="CS", role="ADMIN")
    _order("윤봄", 2)
    date_q, date_m = _q(client, kim, HOME, TABLET)
    crew_q, crew_m = _q(client, admin, HOME + "?tab=crew", TABLET)
    for name in ("정하늘", "서가을", "강단비"):
        _order(name, 0)
    assert _q(client, kim, HOME, TABLET) == (date_q, date_m)  # IN 목록에 id 만 더 든다
    assert _q(client, admin, HOME + "?tab=crew", TABLET) == (crew_q, crew_m)
    assert _q(client, kim, HOME + "?tab=mine", TABLET)[1] == 1


# --------------------------------------------------------------------------- #
# 조사표 "가"(아무 일 없음)로 본 곳 — @order 줄을 줘도 안 깨지는지
# --------------------------------------------------------------------------- #
def _bare_with_marks(client) -> tuple[int, object]:
    kim, edge = make_user("김재단", part="cut"), make_user("박엣지", part="edge")
    bare = _order("정하늘", 0)
    _press(client, kim, bare.id, "cut", "take", "none")
    _press(client, kim, bare.id, "cut", "done", "need")
    _press(client, edge, bare.id, "edge", "take", "none")
    return bare.id, kim


def _state(oid: int):
    db_session.expire_all()
    order = db_session.get(Order, oid)
    return order.structured_data, order_marks(db_session, oid)


def test_factory_and_drawing_workshop_readers_ignore_the_order_card(client, cohort):
    oid, _kim = _bare_with_marks(client)
    sd, marks = _state(oid)
    assert factory_finished(sd, marks, 1) is False  # 2공장 칸은 섞인 주문만(0장은 늘 거짓 — 지금 그대로)
    assert hand_checked_parts(sd, marks) == ()  # @order 를 쓴 파트는 손 체크로 안 봄
    assert drawings_progress(sd, marks, []) == []  # 도면 작업실 진행 — 도면이 없으면 줄 없음


def test_pc_part_sheet_window_and_work_sheet_do_not_say_drawing_one_of_one(client, cohort):
    oid, _kim = _bare_with_marks(client)
    lead = make_user("박반장", lead=True)
    login(client, lead)
    data = client.get(f"/api/production/part-sheet?order_id={oid}&part=cut").get_json()["data"]
    assert data["total"] == 0 and data["rows"] == [] and data["notice"] is None
    page = client.get(f"/erp/production/sheet/{oid}")
    assert page.status_code == 200 and "도면 1/1" not in page.get_data(as_text=True)
    from foms.services.production_sheet_view import build_production_sheet_view  # noqa: PLC0415
    from models import User  # noqa: PLC0415

    db_session.expire_all()
    sheet = build_production_sheet_view(db_session, db_session.get(Order, oid), db_session.get(User, lead.id), full=True)
    assert sheet["step_notes"] == {} and sheet["step_lines"] is None  # 칸 옆 글 · 보기 줄 없음 = 지금 칸 글(칸을 켠 사람) 그대로
    assert sheet["complete_why"] == "미완료가 있어요 — 엣지 1장 · 조립 1장 · 검수 1장"  # [제작 완료] 막힘 글("도면이 없어요" 아님)


def test_hold_alarm_reaches_the_order_card_worker(client, cohort):
    oid, kim = _bare_with_marks(client)  # 박엣지가 @order 엣지 작업 중
    lead = make_user("박반장", lead=True)
    edge = db_session.query(ProductionPartMark).filter_by(order_id=oid, drawing_key=KEY, part="edge").one()
    reads = Reads(db_session, now_utc_naive(), get_today_kst())
    result = plan(reads, {"kind": "hold", "order_id": oid, "by": lead.id, "by_name": "박반장", "m": {"reason": "자재 기다림"}})
    assert [(a.user_id, a.ntype) for a in result.alarms] == [(edge.picked_by_user_id, T.STOP_HOLD)]
    assert kim.id != edge.picked_by_user_id  # 끝낸 김재단은 안 받는다(작업 중인 사람만)

"""파트 맡기 고침 P1 읽기 모델(설계서 2026-11-23 §4-2 · §4-6 · §4-9 · §4-10 · §4-11 · §8-1) — 순수 계산 · 판 자료 · 기록 글.

* 칸 아래 이름(part_holders): 완료(카드) = 마지막 완료한 사람 + 외 n · 손 체크 = 체크한 사람 · 하는 중 = 담당(밤 넘김) · 담당 바뀜 =
  바꿔 맡은 사람 + "바뀜" · 없음 = "미정" · 카드 부분이면 "재단 3/5" · 단계 칸 "2장 미완료". 태블릿 글(aria)에는 시각이 없다.
* 카드 판(part_board): 손으로 체크한 파트 = 모든 장 '완료'(state hand, 파트 계정 '완료' 칸 · 미정 수 · 일괄 기본에서 빠짐) · 막힘
  (보류 · 도면 고치는 중 · 검수 전, 까닭 = 쓰기 API 거절 글 그대로) · 내 담당 한 층 · 꼬리 · 남의 담당 둘째 줄 · 첫 카드.
* 기록 글(order_event_display): 새 기록(담당 바꾸기 · 맡기 취소 · 작업 시트 손 체크)만 새 글, 지금 기록은 지금 글 그대로.
대조군: 카드를 안 쓴 파트 · 손 체크 없는 주문은 지금 그대로(칸 아래는 손 체크한 사람 · 미정만).
"""
from __future__ import annotations

import datetime
from itertools import count
from types import SimpleNamespace as N

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.order_event_display import generate_change_description
from foms.services.production.part_board import build_part_board
from foms.services.production.part_holders import attach_part_holders, handed_text, part_holder, since_text
from foms.services.production.part_mark_gates import HOLD_MESSAGE, REVISING_MESSAGE, inspect_gate
from foms.services.production.part_screen import morning_chip
from foms.services.production_home_days import production_home_days
from foms.services.production_home_read_model import build_production_home
from models import Order, ProductionPartMark, ProductionRun, User

TODAY = datetime.date(2026, 11, 24)
_seq = count(1)


def _files(n: int, prefix: str = "k") -> dict:
    return {"drawing_current_files": [{"key": f"{prefix}{i}", "filename": f"{prefix}{i}.png"} for i in range(n)]}


def _m(key, part, state, picked=None, pat=None, done=None, dat=None, handed=None, hat=None):
    return N(order_id=1, drawing_key=key, part=part, state=state, picked_by_name=picked, picked_at=pat, picked_by_user_id=7,
             done_by_name=done, done_at=dat, handed_from_name=handed, handed_at=hat)


T = datetime.datetime(2026, 11, 24, 5, 20)  # KST 14:20
Y = datetime.datetime(2026, 11, 23, 0, 10)  # KST 11/23 09:10 = 어제


# --------------------------------------------------------------------------- #
# 칸 아래 이름 — 순수
# --------------------------------------------------------------------------- #
def test_밤_넘김_바뀜_글은_서버_KST_날로() -> None:
    assert since_text(T, TODAY) == "" and since_text(Y, TODAY) == "어제부터"
    assert since_text(datetime.datetime(2026, 11, 20, 1, 0), TODAY) == "11/20부터"
    assert handed_text("박엣지", T, TODAY) == "박엣지에서 바뀜 14:20" and handed_text("박엣지", T, TODAY, with_time=False) == "박엣지에서 바뀜"
    assert handed_text("박엣지", Y, TODAY) == "박엣지에서 바뀜 · 어제" and handed_text("", T, TODAY) == ""


def test_칸_아래_이름_다섯_꼴() -> None:
    sd = _files(5)
    marks = [_m("k0", "cut", "DONE", "김재단", Y, "김재단", Y), _m("k1", "cut", "DONE", "박재단", Y, "박재단", T),
             _m("k2", "cut", "BASIC", None, None, "박재단", Y), _m("k3", "cut", "NEED", "최재단", Y), _m("k4", "cut", "NONE"),
             _m("k0", "edge", "NEED", "김민준", T, handed="박엣지", hat=T), _m("k1", "edge", "NEED", "최가은", T)]
    cut = part_holder(sd, marks, "cut", {"by": ""}, TODAY)
    assert (cut["kind"], cut["name"], cut["tail"], cut["old"], cut["label"]) == ("held", "최재단", "", True, "재단 3/5")
    assert cut["aria"] == "재단 3/5 · 2장 미완료 · 담당 최재단 · 어제부터"  # 태블릿 글 — 시각 없음
    assert cut["tip"] == "재단 3/5 · 2장 미완료 · 담당 최재단"  # PC 마우스 글(카드 부분일 때만 새 글)
    edge = part_holder(sd, marks, "edge", {"by": ""}, TODAY)
    assert (edge["kind"], edge["name"], edge["tail"], edge["old"]) == ("held", "김민준", "바뀜", False)  # 바뀜이 외 n 보다 앞
    assert "박엣지에서 바뀜" in edge["aria"] and "14:20" not in edge["aria"] and "함께 하는 사람 최가은" in edge["aria"]
    assert "박엣지에서 바뀜 14:20" in edge["tip"]
    none = part_holder(sd, marks, "assemble", {"by": ""}, TODAY)
    assert (none["kind"], none["name"], none["label"], none["tip"]) == ("none", "미정", "조립", None)  # 카드 안 씀 = 지금 마우스 글
    # 모두 카드로 완료 — 마지막으로 완료한 사람 + 외 n
    done = [_m(f"k{i}", "cut", "DONE", n, Y, n, T + datetime.timedelta(minutes=i)) for i, n in enumerate(["가", "나", "다", "가", "나"])]
    full = part_holder(sd, done, "cut", {"by": ""}, TODAY)
    assert (full["kind"], full["name"], full["tail"], full["label"]) == ("done", "나", "외 2", "재단")
    # 손 체크(카드 안 쓴 파트) — 체크한 사람, 외 n 없음
    hand = part_holder({**sd, "production": {"steps": [{"key": "cut", "done": True, "by_name": "박반장"}]}}, [], "cut",
                       {"by": "박반장"}, TODAY)
    assert (hand["kind"], hand["name"], hand["tail"], hand["aria"]) == ("done", "박반장", "", "재단 완료 · 박반장")


def test_단계_칸_둘째_줄은_지금_공정이_카드_부분일_때만() -> None:
    sd = {**_files(5), "production": {"steps": []}}
    steps = [{"key": k, "label": lb, "done": False} for k, lb in (("cut", "재단"), ("edge", "엣지"), ("assemble", "조립"), ("inspect", "검수"))]
    rows = [{"id": 1, "home_view": "prod", "home_stage": "재단 중", "home_steps": steps, "structured_data": sd},
            {"id": 2, "home_view": "prod", "home_stage": "재단 중", "home_steps": steps, "structured_data": sd},
            {"id": 3, "home_view": "wait", "home_steps": steps, "structured_data": sd}]
    marks = {1: [_m("k0", "cut", "DONE", "김재단", Y, "김재단", T), _m("k1", "cut", "DONE", "김재단", Y, "김재단", T),
                 _m("k2", "cut", "DONE", "김재단", Y, "김재단", T)]}
    attach_part_holders(rows, marks, TODAY)
    assert rows[0]["part_miss"] == "2장 미완료" and rows[0]["part_holders"][0]["label"] == "재단 3/5"
    assert rows[1]["part_miss"] == "" and [h["name"] for h in rows[1]["part_holders"]] == ["미정"] * 4  # 대조군: 카드 안 씀
    assert "part_holders" not in rows[2]  # 안 내려온 주문(기다림 칸)은 공정 칸이 없다


# --------------------------------------------------------------------------- #
# 카드 판 — DB
# --------------------------------------------------------------------------- #
def _user(name: str, part: str | None = None, role: str = "STAFF", team: str = "PRODUCTION") -> User:
    user = User(username=f"sfrm_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True, production_part=part)
    db_session.add(user)
    db_session.commit()
    return user


def _order(name: str, n: int, *, steps=None, hold=False, status=None, run=True) -> Order:
    when = get_today_kst().isoformat()
    sd = {"workflow": {"stage": "PRODUCTION"}, "parties": {"customer": {"name": name, "phone": "010-0000-0000"}},
          "schedule": {"construction": {"date": when}}, "items": [{"product_name": "붙박이장"}],
          "drawing_current_files": [{"key": f"{name}/d{j}.png", "filename": f"d{j}.png"} for j in range(n)],
          "production": {"steps": steps or []}}
    if hold:
        sd["production"]["hold"] = {"active": True, "reason": "자재 기다림"}
    if status:
        sd["drawing_status"] = status
    order = Order(received_date=when, customer_name=name, phone="010-0000-0000", address="가짜시", product="붙박이장",
                  status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION", erp_construction_date=when, structured_data=sd)
    db_session.add(order)
    db_session.flush()
    if run:
        db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
    db_session.commit()
    return order


def _mark(order: Order, j: int, part: str, state: str, who: User | None = None, *, picked_at=None, handed=None) -> None:
    db_session.add(ProductionPartMark(
        order_id=order.id, drawing_key=f"{order.customer_name}/d{j}.png", part=part, state=state,
        picked_by_user_id=who.id if who and state != "BASIC" else None, picked_by_name=who.name if who and state != "BASIC" else None,
        picked_at=picked_at or now_utc_naive(), done_by_user_id=who.id if who and state in ("DONE", "BASIC") else None,
        done_by_name=who.name if who and state in ("DONE", "BASIC") else None,
        done_at=now_utc_naive() if state in ("DONE", "BASIC") else None, handed_from_name=handed,
        handed_at=now_utc_naive() if handed else None, updated_by_user_id=who.id if who else None, updated_at=now_utc_naive()))
    db_session.commit()


def _pane(user: User) -> dict:
    rows, _ = build_production_home(db_session, user)
    days = production_home_days(rows, get_today_kst(), None)
    board = build_part_board(db_session, user, days)
    return board["panes"][get_today_kst().isoformat()]


def _card(pane: dict, name: str, j: int) -> dict:
    return next(c for c in pane["cards"] if c["key"] == f"{name}/d{j}.png")


def test_손_체크한_파트는_모든_장_완료_막힘_까닭은_서버_글(app) -> None:
    me, admin = _user("김재단", "cut"), _user("관리", role="ADMIN", team="CS")
    hand = _order("손체크집", 2, steps=[{"key": "cut", "label": "재단", "done": True, "by_name": "박반장"}])
    _order("빈집", 1)
    pane = _pane(me)
    c = _card(pane, "손체크집", 0)
    assert (c["state"], c["hand"]["text"], c["in_done"], c["in_need"]) == ("hand", "재단 완료 · 박반장", False, False)
    assert c["hand"]["why"] == "박반장이 작업 시트에서 재단 칸을 체크했어요. 다시 해야 하면 박반장에게 말해 주세요."
    assert pane["counts"]["unseen"] == 1 and pane["counts"]["done"] == 0  # 미정 · 내가 완료에서 빠짐(§4-2 판 숫자)
    assert _card(_pane(admin), "손체크집", 1)["in_done"] is True  # 관리자 '완료' 에는 셈
    # 엣지 판에서 재단 낱말 = 끝(손 체크 = 모든 장 완료)
    edge_card = _card(_pane(_user("최엣지", "edge")), "손체크집", 0)
    assert edge_card["others"][0]["word"] == "끝" and edge_card["hand_parts"] == ["cut"]
    assert hand.id


def test_보류_도면_고치는_중_검수_전은_막힌_칸(app) -> None:
    me = _user("윤검수", "inspect")
    held = _order("보류집", 1, hold=True)
    fixing = _order("고침집", 1, status="RETURNED")
    pre = _order("검수집", 2)
    cut = _user("김재단", "cut")
    for part in ("cut", "edge", "assemble"):
        _mark(pre, 0, part, "DONE" if part != "cut" else "BASIC", cut)
    pane = _pane(me)
    assert _card(pane, "보류집", 0)["block"] == {"kind": "hold", "text": "보류 · 자재 기다림", "why": HOLD_MESSAGE, "code": "HOLD_ACTIVE"}
    assert _card(pane, "고침집", 0)["block"]["kind"] == "revise" and _card(pane, "고침집", 0)["block"]["why"] == REVISING_MESSAGE
    ready, waiting = _card(pane, "검수집", 0), _card(pane, "검수집", 1)
    assert ready["block"] is None  # 앞 셋이 완료(재단 기본도 완료)된 장은 열림
    assert waiting["block"]["text"] == "재단 · 엣지 · 조립 미완료"
    marks = db_session.query(ProductionPartMark).filter_by(order_id=pre.id).all()
    assert waiting["block"]["why"] == inspect_gate(pre.structured_data, marks, "검수집/d1.png", "inspect", "take").message
    keys = [c["key"] for c in pane["cards"]]
    assert keys.index("검수집/d0.png") < keys.index("검수집/d1.png")  # 검수 할 수 있음 → 검수 전
    assert fixing.id and held.id


def test_내_담당_한_층_꼬리_남의_담당_둘째_줄_첫_카드(app) -> None:
    me, park = _user("김민준", "edge"), _user("박엣지", "edge")
    yesterday = now_utc_naive() - datetime.timedelta(days=1)
    order = _order("한빛", 3)
    fresh = _order("새집", 1, run=False)
    _mark(order, 0, "edge", "NEED", me, picked_at=yesterday)
    _mark(order, 1, "edge", "NEED", park, handed="최가은")
    pane = _pane(me)
    mine, other = _card(pane, "한빛", 0), _card(pane, "한빛", 1)
    assert mine["mine_row"] and mine["tag"] == {"old": "어제부터", "chg": "", "aria": "내 담당 · 어제부터"}
    assert mine["picked_by_user_id"] == me.id and mine["picked_day"] and mine["picked_at"]
    assert not other["mine_row"] and other["tag"] is None and other["held_note"].startswith("최가은에서 바뀜 ")
    assert _card(pane, "새집", 0)["first_card"] is True and mine["first_card"] is False  # 회차 없는 집 = 첫 카드(§4-8)
    assert fresh.id


def test_아침_칩은_밤_넘긴_내_담당만_지금_장만(app) -> None:
    me = _user("김재단", "cut")
    order = _order("아침집", 3)
    old = now_utc_naive() - datetime.timedelta(days=2)
    _mark(order, 0, "cut", "NEED", me, picked_at=old)
    _mark(order, 1, "cut", "NEED", me)  # 오늘 맡음 = 안 셈
    db_session.add(ProductionPartMark(order_id=order.id, drawing_key="옛판/d9.png", part="cut", state="NEED",
                                      picked_by_user_id=me.id, picked_by_name=me.name, picked_at=old,
                                      updated_by_user_id=me.id, updated_at=old))  # 옛 판 key = 안 셈
    db_session.commit()
    rows, _ = build_production_home(db_session, me)
    chip = morning_chip(db_session, me, "cut", rows, get_today_kst())
    assert chip["count"] == 1 and chip["days"][0]["key"] == get_today_kst().isoformat()
    assert chip["days"][0]["label"].startswith(f"시공 {get_today_kst().month}/{get_today_kst().day} (")
    assert morning_chip(db_session, _user("박재단", "cut"), "cut", rows, get_today_kst()) is None  # 대조군


# --------------------------------------------------------------------------- #
# 기록 글
# --------------------------------------------------------------------------- #
def test_기록_글은_새_기록만_새_글() -> None:
    assert generate_change_description("PRODUCTION_PART_MARKED", "", "", "", {"part": "edge", "action": "takeover",
                                                                               "from_name": "박엣지", "by_name": "김민준"}) \
        == "엣지 담당을 박엣지에서 김민준으로 바꿨습니다"
    assert generate_change_description("PRODUCTION_PART_MARKED", "", "", "", {"part": "cut", "action": "release",
                                                                               "holder_name": "박재단"}) \
        == "재단 맡기를 취소했습니다 (박재단 담당)"
    assert generate_change_description("PRODUCTION_STEP_CHECKED", "", "", "", {"key": "cut", "done": True, "via": "sheet"}) \
        == "작업 시트에서 재단 칸을 체크했습니다"
    # 대조군: 지금 기록(맡기 · 옛 칸 체크)은 지금 글 그대로
    assert generate_change_description("PRODUCTION_PART_MARKED", "공정", "", "", {"part": "cut", "action": "take"}) == "공정 변경"
    assert generate_change_description("PRODUCTION_STEP_CHECKED", "", "", "", {"key": "cut", "done": True}) == "변경 이력"

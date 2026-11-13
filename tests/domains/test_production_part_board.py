"""생산 파트 도면 카드 읽기 모델(``foms/services/production/part_board.py``) — 설계서 §15.6 · D48 · D56 · D57(P15-3).

지금 첫 화면 길(``build_production_home`` → ``production_home_days``)을 그대로 지나 판을 만든다 — 날짜 묶음 · 만들 것 줄
순서를 다시 쓰는지까지 본다. 대조군: 남이 맡은 장은 내 '작업 필요' 숫자에 안 들어감 · 시트 신원 없는 파일 · 다른 시트의
옛 줄은 바뀐 도면 짝이 아님 · 도면·컨펌 기다림 주문은 카드가 아님.
"""
from __future__ import annotations

import datetime
from itertools import count

from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.production.part_board import (
    PART_BOARD_CARD_CAP,
    build_part_board,
    card_counts,
    other_part_word,
    sort_cards,
)
from foms.services.production_home_days import production_home_days
from foms.services.production_home_read_model import build_production_home
from models import Order, ProductionPartMark, User

_seq = count(1)


def _user(name: str, *, team: str = "PRODUCTION", role: str = "STAFF", part: str | None = None) -> User:
    user = User(username=f"pb_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True, production_part=part)
    db_session.add(user)
    db_session.commit()
    return user


def _files(prefix: str, n: int, *, sheet: bool = False) -> list[dict]:
    return [{"key": f"{prefix}/d{j}.png", "filename": f"d{j}.png", **({"sheet_id": f"{prefix}-s{j}"} if sheet else {})}
            for j in range(n)]


def _order(name: str, files: list[dict], *, stage: str = "PRODUCTION", day: int = 0, items: list | None = None) -> Order:
    when = (get_today_kst() + datetime.timedelta(days=day)).isoformat()
    sd = {"workflow": {"stage": stage}, "parties": {"customer": {"name": name}}, "schedule": {"construction": {"date": when}},
          "items": items or [{"product_name": "거실장", "spec_width": "3100"}], "drawing_current_files": files}
    order = Order(received_date=when, customer_name=name, phone="010-0000-0000", address="서울", product="거실장",
                  status=stage, is_erp_order=True, erp_stage_code=stage, erp_construction_date=when, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order


def _mark(order: Order, key: str, part: str, state: str, *, picked: User | None = None, done: User | None = None,
          sheet_id: str | None = None) -> None:
    db_session.add(ProductionPartMark(
        order_id=order.id, drawing_key=key, part=part, state=state, sheet_id=sheet_id,
        picked_by_user_id=picked.id if picked else None, picked_by_name=picked.name if picked else None,
        done_by_user_id=done.id if done else None, done_by_name=done.name if done else None,
        updated_by_user_id=(done or picked).id if (done or picked) else None, updated_at=now_utc_naive(),
    ))
    db_session.commit()


def _board(user: User, part: str | None = None) -> dict:
    rows, stats = build_production_home(db_session, user)
    days = production_home_days(rows, get_today_kst(), None, past_hidden=stats["past_hidden"])
    return build_part_board(db_session, user, days, part=part)


def _today(board: dict) -> dict:
    return board["panes"][get_today_kst().isoformat()]


def _card(pane: dict, key: str) -> dict:
    return next(c for c in pane["cards"] if c["key"] == key)


# --------------------------------------------------------------------------- #
# 낱말 · 상태별 카드
# --------------------------------------------------------------------------- #
def test_other_part_words_cut_has_basic_others_say_not_yet():
    assert [other_part_word("cut", s)["word"] for s in ("done", "basic", "need", "none")] == ["끝", "기본", "중", "안 봄"]
    assert [other_part_word("assemble", s)["word"] for s in ("done", "need", "none")] == ["끝", "중", "아직"]
    assert other_part_word("edge", "none") == {"part": "edge", "label": "엣지", "word": "아직", "tone": "none"}


def test_cards_carry_state_names_badges_and_other_part_line(app):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    edge_man = _user("최엣지", part="edge")
    order = _order("한빛", _files("o1", 4))
    _mark(order, "o1/d0.png", "cut", "NEED", picked=me)
    _mark(order, "o1/d1.png", "cut", "NEED", picked=park)
    _mark(order, "o1/d2.png", "cut", "BASIC", done=park)
    _mark(order, "o1/d0.png", "edge", "DONE", picked=edge_man, done=edge_man)
    _mark(order, "o1/d0.png", "assemble", "NEED", picked=edge_man)

    board = _board(me)
    assert (board["mode"], board["part"], board["part_label"], board["mine"]) == ("part", "cut", "재단", True)
    pane = _today(board)
    mine, taken, basic, fresh = (_card(pane, f"o1/d{j}.png") for j in range(4))
    assert (mine["state"], mine["badge"], mine["picked_by_name"], mine["picked_by_me"]) == ("need", "need", "김재단", True)
    assert (taken["state"], taken["badge"], taken["taken_by_other"]) == ("need", "taken", True)
    assert (basic["state"], basic["badge"], basic["done_by_name"]) == ("basic", "basic", "박재단")
    assert (fresh["state"], fresh["badge"]) == ("none", None)  # 안 봄 = 배지 없음(D52)
    assert [(o["label"], o["word"]) for o in mine["others"]] == [("엣지", "끝"), ("조립", "중"), ("검수", "아직")]
    assert (mine["no"], mine["of"], mine["customer_name"], mine["order_id"]) == (1, 4, "한빛", order.id)

    # 엣지 계정이 보면 재단 줄 낱말이 '안 봄 · 기본 · 중' 으로 선다(그 밖 파트는 '기본' 낱말이 없다).
    edge_pane = _today(_board(edge_man))
    assert [o["word"] for o in _card(edge_pane, "o1/d3.png")["others"]] == ["안 봄", "아직", "아직"]
    assert _card(edge_pane, "o1/d2.png")["others"][0]["word"] == "기본"
    assert _card(edge_pane, "o1/d0.png")["state"] == "done"


def test_item_label_follows_item_uids_else_big_line(app):
    me = _user("김재단", part="cut")
    uid_a, uid_b = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"  # 서버 uid 꼴(36자)
    items = [{"uid": uid_a, "product_name": "붙박이장", "spec_width": "2400"},
             {"uid": uid_b, "product_name": "신발장", "spec_width": "900", "spec_height": "1200"}]
    files = [{"key": "o2/a.png", "item_uids": [uid_b]}, {"key": "o2/b.png"}]
    _order("이음", files, items=items)
    pane = _today(_board(me))
    linked, plain = _card(pane, "o2/a.png"), _card(pane, "o2/b.png")
    assert (linked["item_label"], linked["item_spec"]) == ("신발장", "W900 × H1200")
    assert (plain["item_label"], plain["item_spec"]) == ("붙박이장, 신발장", "W2400")  # 지금 큰 줄 글


# --------------------------------------------------------------------------- #
# 칸 숫자 — 내 것 / 전체 · 안 본 수
# --------------------------------------------------------------------------- #
def test_counts_are_mine_for_part_account_and_whole_part_for_admin_and_readonly(app):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    order = _order("한빛", _files("o3", 6))
    _mark(order, "o3/d0.png", "cut", "NEED", picked=me)
    _mark(order, "o3/d1.png", "cut", "NEED", picked=park)
    _mark(order, "o3/d2.png", "cut", "DONE", picked=me, done=me)
    _mark(order, "o3/d3.png", "cut", "BASIC", done=me)
    _mark(order, "o3/d4.png", "cut", "DONE", picked=park, done=park)

    mine = _today(_board(me))["counts"]
    assert mine == {"all": 6, "need": 1, "done": 2, "unseen": 1}  # 남이 맡은 · 남이 끝낸 장은 내 숫자 밖(대조군)
    assert _today(_board(park))["counts"] == {"all": 6, "need": 1, "done": 1, "unseen": 1}

    admin = _user("관리자", team="CS", role="ADMIN", part=None)
    readonly = _user("영업", team="SALES")
    for viewer in (admin, readonly):
        board = _board(viewer)
        assert board["mine"] is False and board["part"] == "cut"
        assert _today(board)["counts"] == {"all": 6, "need": 2, "done": 3, "unseen": 1}
    assert _board(admin)["writable"] is True and _board(readonly)["writable"] is False
    assert all(c["badge"] != "taken" for c in _today(_board(readonly))["cards"])  # '맡음'은 파트 계정 말


def test_part_account_ignores_requested_part_admin_and_readonly_pick(app):
    me = _user("김재단", part="cut")
    _order("한빛", _files("o4", 1))
    assert _board(me, part="assemble")["part"] == "cut"
    assert _board(_user("관리자", team="PRODUCTION", role="ADMIN", part="cut"), part="inspect")["mode"] == "admin"
    assert _board(_user("영업", team="SALES"), part="edge")["part"] == "edge"
    assert _board(_user("영업2", team="SALES"), part="paint")["part"] == "cut"  # 모르는 파트 → 재단
    assert _board(_user("반장", team="PRODUCTION"))["mode"] == "readonly"  # 파트 없는 생산 = 읽기 전용
    assert _board(_user("도면", team="DRAWING")) is None  # 첫 화면을 못 보는 팀


# --------------------------------------------------------------------------- #
# 바뀐 도면(D56)
# --------------------------------------------------------------------------- #
def test_replaced_drawing_pairs_by_sheet_id_only(app):
    me = _user("김재단", part="cut")
    files = [{"key": "o5/new-a.png", "sheet_id": "S-A"}, {"key": "o5/direct-new.png"}, {"key": "o5/new-c.png", "sheet_id": "S-C"}]
    order = _order("바뀜", files)
    _mark(order, "o5/old-a.png", "cut", "DONE", picked=me, done=me, sheet_id="S-A")  # 같은 시트 옛 판
    _mark(order, "o5/old-a.png", "assemble", "NEED", picked=me, sheet_id="S-A")
    _mark(order, "o5/direct-old.png", "cut", "DONE", done=me, sheet_id=None)  # 직접 올린 파일 — 신원 없음
    _mark(order, "o5/old-x.png", "cut", "DONE", done=me, sheet_id="S-X")  # 다른 시트(대조군)

    pane = _today(_board(me))
    new_a = _card(pane, "o5/new-a.png")
    assert new_a["state"] == "none"  # 새 판은 안 봄부터
    assert new_a["replaced"]["label"] == "바뀐 도면 · 전 판 재단 끝(김재단)"
    assert new_a["replaced"]["prev"] == {"cut": {"state": "done", "name": "김재단"},
                                         "assemble": {"state": "need", "name": "김재단"}}
    assert _card(pane, "o5/direct-new.png")["replaced"] is None
    assert _card(pane, "o5/new-c.png")["replaced"] is None

    edge_view = _today(_board(_user("최엣지", part="edge")))
    assert _card(edge_view, "o5/new-a.png")["replaced"]["label"] == "바뀐 도면"  # 엣지 옛 진행 없음 — 짝만
    assert _card(_today(_board(_user("이조립", part="assemble"))), "o5/new-a.png")["replaced"]["label"] == \
        "바뀐 도면 · 전 판 조립 중(김재단)"


# --------------------------------------------------------------------------- #
# 정렬 · 캡 · 기다림
# --------------------------------------------------------------------------- #
def test_cut_puts_unseen_first_then_order_and_sheet_others_keep_order(app):
    me, edge = _user("김재단", part="cut"), _user("최엣지", part="edge")
    first = _order("앞집", _files("o6", 3))
    second = _order("뒷집", _files("o7", 2))
    _mark(first, "o6/d0.png", "cut", "DONE", picked=me, done=me)
    _mark(first, "o6/d2.png", "cut", "NEED", picked=me)
    _mark(second, "o7/d1.png", "cut", "BASIC", done=me)

    rows, _stats = build_production_home(db_session, me)
    days = production_home_days(rows, get_today_kst(), None)
    make_ids = [r["id"] for r in next(p for p in days["panes"] if p["key"] == get_today_kst().isoformat())["make_rows"]]
    pane = _today(build_part_board(db_session, me, days))
    order_of = {oid: pos for pos, oid in enumerate(make_ids)}  # 주문 순서 = 지금 만들 것 줄 순서
    assert all(c["order_pos"] == order_of[c["order_id"]] for c in pane["cards"])
    keys = [c["key"] for c in pane["cards"]]
    assert set(keys[:2]) == {"o6/d1.png", "o7/d0.png"}  # 안 본 장 먼저
    assert set(keys[2:]) == {"o6/d0.png", "o6/d2.png", "o7/d1.png"}
    for group in (pane["cards"][:2], pane["cards"][2:]):  # 묶음 안은 주문 · 장 번호 순
        assert [(c["order_pos"], c["no"]) for c in group] == sorted((c["order_pos"], c["no"]) for c in group)
    edge_cards = _today(_board(edge))["cards"]
    assert [(c["order_id"], c["no"]) for c in edge_cards] == \
        [(c["order_id"], c["no"]) for c in sorted(edge_cards, key=lambda c: (c["order_pos"], c["no"]))]
    # 순수 함수 대조군: 재단이 아니면 안 본 장을 앞으로 당기지 않는다.
    cards = [{"state": "done", "order_pos": 0, "no": 1}, {"state": "none", "order_pos": 0, "no": 2}]
    assert [c["no"] for c in sort_cards(cards, "cut")] == [2, 1]
    assert [c["no"] for c in sort_cards(cards, "edge")] == [1, 2]


def test_card_cap_200_reports_hidden_and_counts_everything(app):
    me = _user("김재단", part="cut")
    _order("큰집", _files("o8", PART_BOARD_CARD_CAP + 5))
    pane = _today(_board(me))
    assert len(pane["cards"]) == PART_BOARD_CARD_CAP
    assert pane["hidden"] == 5
    assert pane["counts"]["all"] == PART_BOARD_CARD_CAP + 5 and pane["counts"]["unseen"] == PART_BOARD_CARD_CAP + 5
    assert card_counts([]) == {"all": 0, "need": 0, "done": 0, "unseen": 0}


def test_wait_section_reuses_wait_rows_and_adds_no_drawing_production(app):
    me = _user("김재단", part="cut")
    _order("그림없음", [])
    _order("도면대기", [], stage="DRAWING")
    _order("컨펌대기", _files("o9", 2), stage="CONFIRM")  # 확정 도면이 있어도 단계가 컨펌 — 카드 아님(대조군)
    _order("시공대기", _files("o10", 1), stage="CONSTRUCTION")
    made = _order("만들집", _files("o11", 2))

    pane = _today(_board(me))
    assert {c["order_id"] for c in pane["cards"]} == {made.id}
    assert [r["customer_name"] for r in pane["no_drawing_rows"]] == ["그림없음"]
    assert sorted(r["customer_name"] for r in pane["wait_rows"]) == ["도면대기", "컨펌대기"]
    assert pane["wait_count"] == 3
    assert pane["done_count"] == 1
    assert (pane["orders_total"], pane["drawn_orders"]) == (5, 1)


# --------------------------------------------------------------------------- #
# 쿼리 수 — 표시 줄 읽기 한 번, 카드 수와 무관
# --------------------------------------------------------------------------- #
def _count(fn):
    seen = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        seen["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, seen["n"]


def test_board_adds_one_query_regardless_of_card_count(app):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    order = _order("작은집", _files("q1", 4))
    _mark(order, "q1/d0.png", "cut", "NEED", picked=park)
    rows, stats = build_production_home(db_session, me)
    days = production_home_days(rows, get_today_kst(), None)
    small, q_small = _count(lambda: build_part_board(db_session, me, days))
    assert _today(small)["counts"]["all"] == 4

    for i in range(9):  # +36장 → 40장
        big_order = _order(f"큰집{i}", _files(f"q2-{i}", 4), day=i % 3)
        _mark(big_order, f"q2-{i}/d1.png", "cut", "DONE", picked=park, done=park)
    rows, stats = build_production_home(db_session, me)
    days = production_home_days(rows, get_today_kst(), None)
    big, q_big = _count(lambda: build_part_board(db_session, me, days))
    assert sum(p["counts"]["all"] for p in big["panes"].values()) == 40
    assert q_small == 1 and 0 <= q_big - q_small <= 1, (q_small, q_big)

"""[<파트> 시작 취소] 창 미리 안내 — 그 취소로 제작 시작도 같이 취소될 때만 한 줄(사장님 2026-11-27 "창에도 미리 알리기").

답(글자 그대로): "예: 김재단 님이 잘못 누른 [재단 시작]을 취소할 때 창에 '이 주문에서 시작한 도면이 이것뿐이라 제작 시작도 같이 취소돼요.'
한 줄이 보입니다. 같이 취소될 때만 보입니다."

* 깃발 = ``GET /api/production/part-marks/cancel-preview`` 의 ``run_cancelled`` — 한 장 쓰기(``mark_one``)를 ``dry`` 로 쓰기 직전까지 돌린 답이라
  되돌림 판정(``start_rollback.plan_start_rollback``)이 쓰기와 같은 한 곳에서 나온다. 화면은 이 깃발만 읽는다(조건을 JS 에 다시 적지 않는다).
* 깃발과 실제 쓰기 결과를 **같은 준비물**로 짝지어 본다(:func:`_pair` — 미리 보기 → 아무것도 안 바뀜 → 같은 몸으로 쓰기 → 두 값이 같음).
  서는 경우: 주문의 유일한 시작 표시 · 회차가 도면 작업으로 열림(내 시작 취소 · 반장이 남의 시작 취소).
  안 서는 경우: 같은 주문 다른 도면 표시 · 다른 파트 표시 · 보류 · 불량 기록 · 공정 칸 켜짐 · [제작 시작] 단추로 연 회차 · 같이 작업 중 내 몫만 빠짐.
* 낡은 화면: 창을 열 때마다 새로 묻는다 — 그사이 다른 사람이 같은 주문 다른 도면을 시작했으면 다음 창에는 줄이 없다.
* 읽기 전용(SELECT 만 · 버전 · 이벤트 · 감사 · 회차 · 표시 그대로) · 문은 카드 쓰기와 같다 · 쓰기 길 쿼리 수 그대로.
* 화면(JS — 서버 답은 진짜 API JSON): 줄 자리 = 첫 도면 줄과 같은 칸(.pp-mbody), 답이 올 때까지 실행 잠금, 늦은 답은 버림.
  반장 고르기 창은 어느 단추인지 말한다("[김재단 시작 취소]를 누르면 제작 시작도 같이 취소돼요." — 사장님 11-27 "어느 단추인지 말해 주기").
  [완료 취소] · [기본 취소] 창(사장님 11-27 "여기도 미리 알리기")은 ``test_production_cancel_notice_undo_1127.py``.

되돌리면 실패: 줄이 떴는데 안 취소됨 / 안 떴는데 취소됨 / 미리 보기가 표시 · 주문을 바꿈 / 다른 창에 늦은 답이 줄을 넣음.
이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest
from sqlalchemy import event

from db import db_session, engine
from foms.api.production.part_marks import PREVIEW_ACTIONS
from models import OrderEvent, ProductionPartMark, SecurityLog
from tests.domains.test_production_home_query_count import _count_queries
from tests.domains.test_production_lead_direct_done_1127 import _admin, _lead
from tests.domains.test_production_multi_holder_board import CUT_ADMIN, _node, _page, _post, cohort  # noqa: F401
from tests.support.production_part_claim_seed import (
    current_runs,
    events,
    fresh,
    login,
    make_order,
    make_user,
    mark,
    patch_sd,
)

ROOT = Path(__file__).resolve().parents[2]
PREVIEW = "/api/production/part-marks/cancel-preview"
CANCEL_LINE = "이 주문에서 시작한 도면이 이것뿐이라 제작 시작도 같이 취소돼요."
FIRST_LINE = "이 주문 첫 도면이라 제작 시작도 같이 돼요."
CANCELLED_TAIL = " · 제작 시작도 같이 취소됐어요"


def _kim():
    return make_user("김재단", part="cut")


def _oh():
    return make_user("오재단", part="cut")


def _body(order, j: int = 0, part: str = "cut", action: str = "release", **extra) -> dict:
    """화면이 보내는 몸 — [시작 취소]는 본 상태 작업 중 · 본 내 몫 작업 중, 반장의 남의 시작 취소는 본 내 몫 없음 + 고른 사람."""
    base = {"order_id": order.id, "drawing_key": order.keys[j], "part": part, "action": action, "seen": "need",
            "seen_me": "held" if action == "release" else "none"}
    return {**base, **extra}


def _ask(client, body: dict):
    """미리 보기 — 쓰기 몸과 같은 칸을 질의로(null 은 빈 글)."""
    return client.get(PREVIEW, query_string={k: "" if v is None else v for k, v in body.items()})


def _flag(client, body: dict) -> bool:
    resp = _ask(client, body)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["success"] is True and data["error"] is None and set(data["data"]) == {"run_cancelled"}
    assert resp.headers["Cache-Control"] == "private, no-store"
    return data["data"]["run_cancelled"]


def _snapshot(oid: int) -> tuple:
    """주문 하나의 쓰기 흔적 — 버전 · 이벤트 수 · 감사 수 · 지금 회차 수 · 표시 줄 모습."""
    db_session.expire_all()
    marks = sorted((m.drawing_key, m.part, m.state, str(m.holders), m.updated_at) for m in
                   db_session.query(ProductionPartMark).filter_by(order_id=oid).all())
    return (fresh(oid).mutation_version, db_session.query(OrderEvent).filter_by(order_id=oid).count(),
            db_session.query(SecurityLog).filter_by(target_id=oid).count(), current_runs(oid), marks)


def _pair(client, body: dict, expect: bool) -> dict:
    """깃발 ↔ 실제 결과를 같은 준비물로 — 미리 보기(아무것도 안 바뀜) 뒤 같은 몸으로 쓰고 두 값이 ``expect`` 로 같은지."""
    oid = body["order_id"]
    before = _snapshot(oid)
    flag = _flag(client, body)
    assert _snapshot(oid) == before, "미리 보기가 무언가를 바꿨다"
    resp = client.post("/api/production/part-marks", json=body)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["changed"] is True
    assert (flag, data["run_cancelled"]) == (expect, expect), (flag, data["run_cancelled"])
    assert (current_runs(oid) == 0) is expect and (len(events(oid, "PRODUCTION_CANCELLED")) == 1) is expect
    return data


def _took(client, who, n: int = 1, *, run: bool = False, **order_kw):
    """제작 대기 주문(도면 ``n`` 장)의 첫 도면을 ``who`` 가 [재단 시작] — 도면이 회차를 연다."""
    order = make_order(n, run=run, **order_kw)
    login(client, who)
    data = mark(client, order, 0, "cut", "take", "none").get_json()["data"]
    assert data["run_started"] is (not run)
    return order


# --------------------------------------------------------------------------- #
# 깃발이 서는 경우 — 실제로도 같이 취소된다
# --------------------------------------------------------------------------- #
def test_only_started_drawing_of_a_card_opened_run_flags_and_really_cancels(client):
    kim = _kim()
    order = _took(client, kim, 2)
    data = _pair(client, _body(order, seen_by=kim.id), True)
    assert data["mark"]["state"] == "none"
    assert _flag(client, _body(order, seen_by=kim.id)) is False  # 이미 미정(같은 몸을 다시 — 멱등) — 취소될 것이 없다


def test_lead_removing_the_only_holder_flags_and_really_cancels(client):
    kim = _kim()
    order = _took(client, kim)
    login(client, _lead())
    _pair(client, _body(order, action="remove", seen_by=kim.id, target_user_id=kim.id), True)
    again = _took(client, kim)  # 관리자도 같은 답
    login(client, _admin())
    _pair(client, _body(again, action="remove", seen_by=kim.id, target_user_id=kim.id), True)


# --------------------------------------------------------------------------- #
# 깃발이 안 서는 경우 — 실제로도 회차 그대로
# --------------------------------------------------------------------------- #
def test_other_drawing_of_the_same_order_started_keeps_run(client):
    kim = _kim()
    order = _took(client, kim, 3)
    assert mark(client, order, 1, "cut", "take", "none").status_code == 200
    _pair(client, _body(order, 0), False)
    _pair(client, _body(order, 1), True)  # 남은 하나까지 취소하면 그때 선다(같은 주문 · 같은 사람)


def test_other_part_mark_keeps_run(client):
    order = make_order(1, run=False)
    login(client, make_user("박엣지", part="edge"))
    assert mark(client, order, 0, "edge", "take", "none").get_json()["data"]["run_started"] is True
    login(client, _kim())
    mark(client, order, 0, "cut", "take", "none")
    _pair(client, _body(order), False)


def test_hold_defect_and_hand_checked_step_keep_run(client):
    kim = _kim()
    held = _took(client, kim)
    patch_sd(held.id, hold={"active": True, "reason": "자재 기다림", "at": "2026-11-27T00:00:00", "by_name": "박반장"})
    _pair(client, _body(held), False)

    broken = _took(client, kim)
    patch_sd(broken.id, defects=[{"reason": "파손", "at": "2026-11-27T00:00:00+00:00", "by_name": "박반장"}])
    _pair(client, _body(broken), False)

    stepped = _took(client, kim, steps_done=("edge",))  # 작업 시트에서 손으로 켠 공정 칸
    _pair(client, _body(stepped), False)

    clean = _took(client, kim)  # 대조 — 같은 누름, 걸리는 것이 없는 주문
    _pair(client, _body(clean), True)


def test_run_opened_by_work_sheet_start_button_keeps_run(client):
    order = make_order(2, run=False)
    login(client, _lead())
    assert client.post(f"/api/orders/{order.id}/production/start", json={}).status_code == 200  # 작업 시트 [제작 시작]
    login(client, _kim())
    assert mark(client, order, 0, "cut", "take", "none").get_json()["data"]["run_started"] is False
    _pair(client, _body(order), False)
    seeded = _took(client, _kim(), run=True)  # 시작 이벤트가 없는 옛 회차도 그대로
    _pair(client, _body(seeded), False)


def test_co_working_release_takes_only_my_share_out(client):
    """같이 작업 중 내 몫만 빠짐 — 도면은 작업 중 그대로라 안 선다. 마지막 사람이 취소할 때 선다."""
    kim, oh = _kim(), _oh()
    order = _took(client, kim)
    login(client, oh)
    assert mark(client, order, 0, "cut", "join", "need", seen_me="none").status_code == 200
    login(client, kim)
    data = _pair(client, _body(order), False)
    assert data["mark"]["state"] == "need"
    login(client, _lead())  # 반장이 남은 한 사람(오재단)의 시작을 취소 — 이제 유일한 표시가 미정이 된다
    _pair(client, _body(order, action="remove", seen_by=oh.id, target_user_id=oh.id), True)


def test_lead_removing_one_of_two_holders_keeps_run(client):
    kim, oh = _kim(), _oh()
    order = _took(client, kim)
    login(client, oh)
    mark(client, order, 0, "cut", "join", "need", seen_me="none")
    login(client, _lead())
    _pair(client, _body(order, action="remove", seen_by=kim.id, target_user_id=oh.id), False)


# --------------------------------------------------------------------------- #
# 낡은 화면 — 창을 열 때마다 새로 묻는다
# --------------------------------------------------------------------------- #
def test_flag_follows_other_peoples_writes_between_dialogs(client):
    kim, oh = _kim(), _oh()
    order = _took(client, kim, 2)
    assert _flag(client, _body(order, seen_by=kim.id)) is True  # 김재단 창 ① — 줄이 뜬다(누르지 않고 닫음)
    login(client, oh)
    assert mark(client, order, 1, "cut", "take", "none").status_code == 200  # 그사이 오재단이 같은 주문 다른 도면을 시작
    login(client, kim)
    _pair(client, _body(order, seen_by=kim.id), False)  # 김재단 창 ② — 화면 카드는 그대로지만 줄이 없고, 눌러도 회차 그대로
    login(client, oh)
    _pair(client, _body(order, 1, seen_by=oh.id), True)  # 오재단이 마지막 표시 — 이번에는 선다


def test_press_that_would_be_refused_is_not_flagged(client):
    """누르면 거절될 누름(낡은 화면 409)은 같이 취소될 것도 없다 — 200 False(창에는 줄이 없고, 누르면 지금처럼 거절 글)."""
    kim, oh = _kim(), _oh()
    order = _took(client, kim)
    login(client, oh)
    stale = _body(order, seen_by=oh.id)  # 오재단 화면이 자기가 작업 중이라고 본 낡은 몸
    assert client.post("/api/production/part-marks", json=stale).status_code in (403, 409)
    assert _flag(client, stale) is False
    login(client, kim)
    assert _flag(client, _body(order, seen_by=kim.id)) is True


# --------------------------------------------------------------------------- #
# 읽기 전용 · 문 · 쿼리 수
# --------------------------------------------------------------------------- #
def test_preview_only_reads(client):
    kim = _kim()
    order = _took(client, kim)
    body = _body(order, seen_by=kim.id)
    _flag(client, body)  # warmup
    seen: list[str] = []

    def _before(conn, cursor, statement, params, context, executemany):
        seen.append(statement.strip().split(None, 1)[0].upper())

    before = _snapshot(order.id)
    event.listen(engine, "before_cursor_execute", _before)
    try:
        assert _flag(client, body) is True
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    assert _snapshot(order.id) == before
    writes = [word for word in seen if word in ("INSERT", "UPDATE", "DELETE")]
    assert writes == [] and "SELECT" in seen, seen
    assert len(seen) <= 6, seen  # 로그인 사람 · 주문 · 표시 줄 · 회차 · 마지막 시작 이벤트(주문 수와 무관)


def test_write_path_query_count_is_unchanged_by_the_preview_switch(client, monkeypatch):
    """쓰기 길은 그대로 — 미리 보기를 먼저 부르든 안 부르든 같은 쓰기의 쿼리 수가 같다(``dry`` 갈래는 쓰기 때 안 탄다)."""
    kim = _kim()
    login(client, kim)
    mark(client, make_order(1), 0, "cut", "take", "none")  # warmup

    def _release_count(ask_first: bool) -> int:
        order = _took(client, kim, 2)
        body = _body(order, seen_by=kim.id)
        if ask_first:
            assert _flag(client, body) is True
        resp, n = _count_queries(lambda: client.post("/api/production/part-marks", json=body))
        assert resp.status_code == 200 and resp.get_json()["data"]["run_cancelled"] is True
        return n

    assert _release_count(False) == _release_count(True)


def test_gates_match_the_card_write(client):
    kim = _kim()
    order = _took(client, kim)
    body = _body(order, seen_by=kim.id)
    for action in ("take", "basic", "done", "takeover", "join", "check", "nope"):
        resp = _ask(client, {**body, "action": action})
        assert resp.status_code == 400 and resp.get_json()["data"]["code"] == "BAD_REQUEST", action
    assert set(PREVIEW_ACTIONS) == {"release", "remove", "undo"}
    for bad in ({"order_id": "abc"}, {"order_id": "0"}, {"drawing_key": ""}, {"part": "paint"}, {"seen": "maybe"},
                {"seen_by": "x"}, {"target_user_id": "x"}, {"seen_me": "half"}):
        assert _ask(client, {**body, **bad}).status_code == 400, bad
    assert _ask(client, {**body, "order_id": 987654}).status_code == 404
    assert _ask(client, {**body, "drawing_key": "x/none.png"}).status_code == 200  # 지금 도면이 아닌 key = 누르면 409 → False
    assert _flag(client, {**body, "drawing_key": "x/none.png"}) is False
    login(client, make_user("박엣지", part="edge"))  # 내 파트 밖 — 쓰기와 같은 403
    resp = _ask(client, body)
    assert resp.status_code == 403 and resp.get_json()["data"]["code"] == "PART_FORBIDDEN"
    assert client.post("/api/production/part-marks", json=body).get_json()["data"]["code"] == "PART_FORBIDDEN"
    login(client, make_user("상담", team="CS"))  # 생산 파트가 없는 계정 — 쓰기와 같은 403
    resp = _ask(client, body)
    assert resp.status_code == 403 and resp.get_json()["data"]["code"] == "PART_REQUIRED"
    assert current_runs(order.id) == 1
    with client.session_transaction() as sess:
        sess.clear()
    assert _ask(client, body).status_code in (401, 302)  # 로그인 없이는 답하지 않는다


# --------------------------------------------------------------------------- #
# 화면 — 창 글(서버 답은 진짜 API JSON)
# --------------------------------------------------------------------------- #
def _answer(client, who, body: dict) -> dict:
    login(client, who)
    resp = _ask(client, body)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _query(url: str) -> dict:
    parts = urlsplit(url)
    assert parts.path == PREVIEW
    return dict(parse_qsl(parts.query, keep_blank_values=True))


def _as_query(body: dict) -> dict:
    return {k: "" if v is None else str(v) for k, v in body.items()}


def test_js_release_dialog_shows_the_line_only_when_the_server_says_so(client, cohort, tmp_path):
    order = make_order(2, run=False)
    kim = _kim()
    page = tmp_path / "kim.html"
    page.write_text(_page(client, kim), encoding="utf-8")
    k = order.keys
    take0 = {"order_id": order.id, "drawing_key": k[0], "part": "cut", "action": "take", "seen": "none", "seen_me": "none"}
    take1 = {**take0, "drawing_key": k[1]}
    rel0 = {"order_id": order.id, "drawing_key": k[0], "part": "cut", "action": "release", "seen": "need", "seen_me": "held",
            "seen_by": kim.id}
    rel1 = {**rel0, "drawing_key": k[1]}
    posts = [_post(client, kim, take0)]
    yes = _answer(client, kim, rel0)  # 도면 1 만 시작한 때 — 서버 답 True
    posts.append(_post(client, kim, take1))
    no = _answer(client, kim, rel0)  # 도면 둘을 시작한 때 — False
    posts.append(_post(client, kim, rel1))
    last = _answer(client, kim, rel0)  # 도면 2 를 취소한 뒤 — 다시 True
    posts.append(_post(client, kim, rel0))
    assert [a["data"]["run_cancelled"] for a in (yes, no, last)] == [True, False, True]
    assert posts[3]["data"]["run_cancelled"] is True and posts[2]["data"]["run_cancelled"] is False
    res = _node(page, {"posts": posts, "previews": [yes, no, no, last], "steps": [
        {"do": "click", "key": k[0], "act": "take"}, {"do": "run"},              # 0 1  첫 도면 [재단 시작]
        {"do": "click", "key": k[0], "act": "release"}, {"do": "modal"}, {"do": "close"},  # 2 3 4  창 ① 줄이 뜬다 — 닫음
        {"do": "click", "key": k[1], "act": "take"}, {"do": "run"},              # 5 6  도면 2 도 시작
        {"do": "click", "key": k[0], "act": "release"}, {"do": "modal"}, {"do": "close"},  # 7 8 9  창 ② 줄 없음
        {"do": "click", "key": k[1], "act": "release"}, {"do": "modal"}, {"do": "run"},  # 10 11 12  도면 2 취소 — 줄 없음 · 회차 그대로
        {"do": "click", "key": k[0], "act": "release"}, {"do": "modal"}, {"do": "run"}]})  # 13 14 15  마지막 도면 — 줄 · 같이 취소
    out, calls, previews = res["out"], res["calls"], res["previews"]
    assert out[0]["modal"]["body"] == FIRST_LINE and out[1]["status"] == "재단 시작했어요 · 제작 시작도 같이 됐어요"
    opened = out[2]["modal"]  # 답이 오기 전 — 지금 창 그대로 + 실행 잠금(줄 없음)
    assert (opened["title"], opened["line"], opened["run"]["text"]) == ("재단 시작을 취소할까요?", "담당 김재단 → 미정", "재단 시작 취소")
    assert opened["body"] == "" and opened["run"]["locked"] is True
    shown = out[3]["modal"]  # 답이 온 뒤 — 첫 도면 줄과 같은 칸에 한 줄 · 잠금 풀림 · 그 밖 글은 그대로
    assert shown["body"] == CANCEL_LINE and shown["run"]["locked"] is False
    assert {**shown, "body": "", "run": opened["run"]} == opened
    assert out[5]["modal"]["body"] == ""  # [재단 시작] 창은 묻지 않는다(제작이 이미 시작돼 첫 도면 줄도 없다)
    for i in (8, 11):
        assert out[i]["modal"]["body"] == "" and out[i]["modal"]["run"]["locked"] is False, i
    assert out[12]["sent"] == 1 and out[12]["status"] == "재단 시작 취소했어요"
    assert out[14]["modal"]["body"] == CANCEL_LINE
    assert out[15]["sent"] == 1 and out[15]["status"] == "재단 시작 취소했어요" + CANCELLED_TAIL
    assert [c["body"] for c in calls] == [take0, take1, rel1, rel0]  # 쓰기는 지금 그대로 넷
    assert [_query(u) for u in previews] == [_as_query(b) for b in (rel0, rel0, rel1, rel0)]  # 묻는 칸 = 그 창이 보낼 몸 그대로


def test_js_run_is_locked_until_the_answer_and_a_late_answer_is_dropped(client, cohort, tmp_path):
    kim = _kim()
    order = _took(client, kim, 2)
    page = tmp_path / "kim.html"
    page.write_text(_page(client, kim), encoding="utf-8")
    k = order.keys
    rel0 = _body(order, seen_by=kim.id)
    yes = _answer(client, kim, rel0)
    assert yes["data"]["run_cancelled"] is True
    res = _node(page, {"posts": [_post(client, kim, rel0)], "previews": ["__hang", {"__hold": yes}, {"__status": 500, "body": {}}],
                       "steps": [
        {"do": "click", "key": k[0], "act": "release"}, {"do": "run"},    # 0 1  답이 안 옴 — 눌러도 안 나간다
        {"do": "timers"}, {"do": "modal"}, {"do": "close"},               # 2 3 4  3초 뒤 — 줄 없이 열린다
        {"do": "click", "key": k[0], "act": "release"}, {"do": "close"},  # 5 6  답이 오기 전에 닫음
        {"do": "click", "key": k[1], "act": "take"}, {"do": "answer"},    # 7 8  다른 창([재단 시작])에 늦은 답 — 버린다
        {"do": "close"},                                                  # 9
        {"do": "click", "key": k[0], "act": "release"}, {"do": "modal"}, {"do": "run"}]})  # 10 11 12  서버 오류 — 줄 없이 열리고 쓰기는 된다
    out = res["out"]
    assert out[0]["modal"]["run"]["locked"] is True and out[1]["sent"] == 0 and out[1]["modal"]["hidden"] is False
    assert out[3]["modal"]["body"] == "" and out[3]["modal"]["run"]["locked"] is False
    assert out[7]["modal"]["title"] == "재단 시작할까요?" and out[7]["modal"]["run"]["locked"] is False
    assert out[8]["modal"]["body"] == "" and out[8]["modal"]["title"] == "재단 시작할까요?"
    assert out[11]["modal"]["body"] == "" and out[11]["modal"]["run"]["locked"] is False
    assert out[12]["sent"] == 1 and out[12]["status"] == "재단 시작 취소했어요" + CANCELLED_TAIL  # 못 물은 때는 지금처럼 알림으로
    assert len(res["previews"]) == 3 and len(res["calls"]) == 1


def test_js_lead_choice_dialog_names_the_button_and_co_working(client, cohort, tmp_path):
    kim, oh, lead = _kim(), _oh(), _lead()
    solo = _took(client, kim)  # 김재단 혼자 시작한 한 장짜리 주문
    both = _took(client, kim)  # 김재단 · 오재단이 같이 작업
    login(client, oh)
    mark(client, both, 0, "cut", "join", "need", seen_me="none")
    page = tmp_path / "lead.html"
    page.write_text(_page(client, lead, CUT_ADMIN), encoding="utf-8")
    remove = _body(solo, action="remove", seen_by=kim.id, target_user_id=kim.id)
    yes = _answer(client, lead, remove)
    crew_no = [_answer(client, lead, _body(both, action="remove", seen_by=kim.id, target_user_id=who.id)) for who in (kim, oh)]
    assert [a["data"]["run_cancelled"] for a in (*crew_no, yes)] == [False, False, True]
    res = _node(page, {"posts": [_post(client, lead, remove)], "previews": [*crew_no, yes], "steps": [
        {"do": "click", "key": both.keys[0], "act": "held"}, {"do": "modal"}, {"do": "close"},    # 0 1 2
        {"do": "click", "key": solo.keys[0], "act": "held"}, {"do": "modal"},                     # 3 4
        {"do": "choice", "text": "김재단 시작 취소"}]})                                             # 5
    out, previews = res["out"], [_query(u) for u in res["previews"]]
    crew = out[1]["modal"]  # 둘이 같이 작업 중 — 사람마다 묻고(둘) 어느 쪽도 참이 아니라 줄이 없다(한 사람만 빼서는 미정이 안 된다)
    assert [c["text"] for c in crew["choices"]][:2] == ["김재단 시작 취소", "오재단 시작 취소"] and crew["body"] == ""
    assert [(q["action"], q["target_user_id"]) for q in previews[:2]] == [("remove", str(kim.id)), ("remove", str(oh.id))]
    assert out[3]["modal"]["body"] == ""
    pick = out[4]["modal"]  # 반장 고르기 창 — 같은 자리, 어느 단추인지 말하는 글(단추 글 그대로)
    assert pick["title"].startswith("김재단 ") and pick["title"].endswith("작업 중")
    assert pick["body"] == "[김재단 시작 취소]를 누르면 제작 시작도 같이 취소돼요."
    assert [c["text"] for c in pick["choices"]] == ["김재단 시작 취소", "담당 바꾸기", "같이 작업", "대신 완료"]
    assert previews[2] == _as_query(remove) and len(previews) == 3
    assert out[5]["sent"] == 1 and out[5]["status"] == "김재단 시작 취소했어요" + CANCELLED_TAIL
    assert [c["body"] for c in res["calls"]] == [remove]

    mine = tmp_path / "kim.html"  # 같이 작업 중 내 몫 [재단 시작 취소] — 묻지만 답이 거짓이라 줄이 없다
    mine.write_text(_page(client, kim), encoding="utf-8")
    rel = _body(both, seen_by=kim.id)
    no = _answer(client, kim, rel)
    assert no["data"]["run_cancelled"] is False
    got = _node(mine, {"previews": [no], "steps": [{"do": "click", "key": both.keys[0], "act": "release"}, {"do": "modal"}]})
    assert got["out"][1]["modal"]["body"] == "" and got["out"][1]["modal"]["run"]["locked"] is False
    assert [q["action"] for q in map(_query, got["previews"])] == ["release"]


def test_source_contract_one_line_one_judge_and_sizes():
    js = {name: (ROOT / f"static/js/production/foms-production-{name}.js").read_text(encoding="utf-8")
          for name in ("parts", "parts-modal", "parts-crew", "parts-claim")}
    modal = js["parts-modal"]
    assert modal.count(CANCEL_LINE) == 1 and all(CANCEL_LINE not in text for name, text in js.items() if name != "parts-modal")
    assert modal.count("fetch(") == 1 and "'/api/production/part-marks/cancel-preview'" in modal and "method: 'GET'" in modal
    assert modal.index("try {") < modal.index("fetch(") < modal.index("} catch (e)") and "data.success === true" in modal
    line = next(text for text in modal.splitlines() if "var asks" in text)  # 화면은 누름 이름만 고른다 — 판정 조건은 적지 않는다
    assert "ASKS.indexOf(c[0]) >= 0" in line and "var ASKS = ['release', 'remove', 'undo'];" in modal
    assert modal.count("'를 누르면 제작 시작도 같이 취소돼요.'") == 1  # 고르기 창 글 — 단추 글은 늘 '취소'로 끝나 토씨 '를' 고정
    for word in ("data-pp-first", "hold", "defect", "cr.n", "run_started"):
        assert word not in modal[modal.index("function cancelLine"):modal.index("// ── 창 그리기")], word
    assert "M.cancelLine(pending, p, " in js["parts"]
    assert len(js["parts"].splitlines()) <= 299 and len(modal.splitlines()) <= 300
    write = (ROOT / "foms/services/production/part_mark_write.py").read_text(encoding="utf-8")
    assert write.count("plan_start_rollback(") == 1 and len(write.splitlines()) <= 499  # 판정을 부르는 곳은 쓰기 · 미리 보기가 같은 한 줄
    assert write.index("closing = plan_start_rollback(") < write.index("if dry:") < write.index("steps, started = apply_order_changes(")
    api = (ROOT / "foms/api/production/part_marks.py").read_text(encoding="utf-8")
    assert 'mark_one(db, user, override, req, dry=True)' in api and 'methods=["GET"]' in api
    tpl = (ROOT / "templates/production/partials/home_scripts.html").read_text(encoding="utf-8")
    for name in ("parts", "parts-modal"):
        assert f"foms-production-{name}.js') }}}}?v=20261128b\" defer" in tpl, name
    overlay = (ROOT / "templates/production/partials/home_parts_overlays.html").read_text(encoding="utf-8")
    assert overlay.count('class="pp-mbody" data-pp-modal-body hidden') == 1  # 줄 자리 = 첫 도면 줄과 같은 칸(새 칸 · 새 CSS 없음)


@pytest.mark.parametrize("action", sorted(PREVIEW_ACTIONS))
def test_preview_route_is_get_only(app, action):
    rules = [r for r in app.url_map.iter_rules() if r.rule == PREVIEW]
    assert len(rules) == 1 and rules[0].methods <= {"GET", "HEAD", "OPTIONS"}
    assert rules[0].endpoint == "production_part_marks.api_part_mark_cancel_preview"

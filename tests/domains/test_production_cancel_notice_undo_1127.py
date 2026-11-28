"""[<파트> 완료 취소] · [기본 취소] 창 미리 안내 + 반장 고르기 창 글(사장님 2026-11-27 후속 답 둘).

답(글자 그대로):
* 완료 취소 창 = "여기도 미리 알리기" — "[재단 완료 취소] 창에도 같이 취소될 때만 '이 주문에서 작업한 도면이 이것뿐이라 제작 시작도 같이
  취소돼요.' 한 줄을 보입니다. [기본 취소] 창도 같은 경우면 같이 보입니다."
* 반장 고르기 창 = "어느 단추인지 말해 주기" — "고르기 창에서만 글을 '[오재단 시작 취소]를 누르면 제작 시작도 같이 취소돼요.'로 바꿉니다."

깃발은 앞 파일과 같은 ``GET /api/production/part-marks/cancel-preview``(``mark_one`` 을 ``dry`` 로) — 받는 누름에 ``undo`` 가 더해졌다.
깃발 ↔ 실제 ``run_cancelled`` 를 같은 준비물로 짝지어 본다(:func:`_pair`):

* 참: 반장 · 관리자가 바로 완료한 유일한 도면의 [완료 취소](한 번에 미정) · 유일한 표시인 [기본 취소] · 한꺼번에 기본 뒤 마지막 한 장.
* 거짓: 작업 중으로만 돌아가는 완료 취소(파트 계정 · 반장 대신 되돌리기 · 내 몫만 되돌리기) · 다른 도면 표시가 남음 · [제작 시작] 단추로 연 회차 · 보류.
* 화면: 완료 취소 · 기본 취소 창을 열 때만 GET 1 이 늘고, [시작] · [기본] · [완료] · [같이 작업] · [담당 바꾸기] 창은 0.

되돌리면 실패: 완료 취소 창에 줄이 떴는데 작업 중으로만 돌아감 / 줄 없이 제작 시작이 취소됨 / 고르기 창 글이 어느 단추인지 말하지 않음.
이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import pytest

from tests.domains.test_production_cancel_notice_1127 import (
    CANCELLED_TAIL,
    FIRST_LINE,
    _answer,
    _as_query,
    _ask,
    _body,
    _kim,
    _oh,
    _pair,
    _query,
    _took,
)
from tests.domains.test_production_lead_direct_done_1127 import _admin, _check, _lead
from tests.domains.test_production_multi_holder_board import CUT_ADMIN, _node, _page, _post, cohort  # noqa: F401
from tests.support.production_part_claim_seed import BULK, current_runs, finish, login, make_order, mark, patch_sd

UNDO_LINE = "이 주문에서 작업한 도면이 이것뿐이라 제작 시작도 같이 취소돼요."


def _undo(order, j: int = 0, seen: str = "done", seen_me: str = "none", **extra) -> dict:
    """화면이 보내는 몸 — [<파트> 완료 취소](본 상태 완료) · [기본 취소](본 상태 기본)."""
    return {"order_id": order.id, "drawing_key": order.keys[j], "part": "cut", "action": "undo", "seen": seen, "seen_me": seen_me,
            **extra}


def _direct_done(client, lead, n: int = 1, *, run: bool = False):
    """제작 대기 주문의 첫 도면을 반장이 바로 [재단 완료] — 도면이 회차를 연다."""
    order = make_order(n, run=run)
    login(client, lead)
    assert _check(client, order, 0).get_json()["data"]["run_started"] is (not run)
    return order


# --------------------------------------------------------------------------- #
# 참 — 미정까지 한 번에 돌아가고 그 표시가 유일할 때
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sheets", [1, 2])
def test_direct_done_undo_of_the_only_mark_flags_and_really_cancels(client, sheets):
    lead = _lead()
    order = _direct_done(client, lead, sheets)
    data = _pair(client, _undo(order, seen_me="done"), True)
    assert data["mark"]["state"] == "none"


def test_admin_undoing_leads_direct_done_flags_too(client):
    order = _direct_done(client, _lead())
    login(client, _admin())
    _pair(client, _undo(order), True)


def test_basic_undo_of_the_only_mark_flags_and_other_mark_does_not(client):
    kim = _kim()
    login(client, kim)
    only = make_order(1, run=False)
    assert mark(client, only, 0, "cut", "basic", "none").get_json()["data"]["run_started"] is True
    data = _pair(client, _undo(only, seen="basic"), True)
    assert data["mark"]["state"] == "none" and data["order_step"]["done"] is False

    two = make_order(2, run=False)  # 같은 주문 다른 도면도 기본 — 한 장 취소로는 그대로, 마지막 한 장에서 선다
    items = [{"order_id": two.id, "drawing_key": k} for k in two.keys]
    assert client.post(BULK, json={"part": "cut", "seen": "none", "items": items}).get_json()["data"]["run_started"] == [two.id]
    _pair(client, _undo(two, 0, seen="basic"), False)
    _pair(client, _undo(two, 1, seen="basic"), True)


# --------------------------------------------------------------------------- #
# 거짓 — 미정까지 안 가거나, 가도 되돌릴 조건이 아닐 때
# --------------------------------------------------------------------------- #
def test_undo_that_only_goes_back_to_working_is_never_flagged(client):
    kim, oh, lead = _kim(), _oh(), _lead()
    mine = make_order(1, run=False)  # 파트 계정의 [재단 완료 취소] — 작업 중으로만 돌아간다
    login(client, kim)
    assert finish(client, mine, 0, "cut").status_code == 200
    data = _pair(client, _undo(mine, seen_me="done"), False)
    assert data["mark"]["state"] == "need"

    by_lead = make_order(1, run=False)  # 반장이 김재단의 완료를 대신 되돌림 — 김재단 작업 중으로
    login(client, kim)
    finish(client, by_lead, 0, "cut")
    login(client, lead)
    data = _pair(client, _undo(by_lead), False)
    assert data["mark"]["state"] == "need"

    share = _took(client, kim)  # 둘이 같이 작업 — 김재단 몫만 완료했다가 그 몫만 되돌림(도면은 계속 작업 중)
    login(client, oh)
    mark(client, share, 0, "cut", "join", "need", seen_me="none")
    login(client, kim)
    assert mark(client, share, 0, "cut", "done", "need", seen_me="held").status_code == 200
    data = _pair(client, _undo(share, seen="need", seen_me="done", seen_by=kim.id, target_user_id=kim.id), False)
    assert data["mark"]["state"] == "need"


def test_direct_done_undo_with_another_mark_or_sheet_started_run_keeps_run(client):
    lead, kim = _lead(), _kim()
    other = _direct_done(client, lead, 2)  # 같은 주문 다른 도면을 김재단이 시작
    login(client, kim)
    mark(client, other, 1, "cut", "take", "none")
    login(client, lead)
    _pair(client, _undo(other, seen_me="done"), False)

    sheet = make_order(1, run=False)  # 작업 시트 [제작 시작]으로 연 회차
    assert client.post(f"/api/orders/{sheet.id}/production/start", json={}).status_code == 200
    assert _check(client, sheet, 0).get_json()["data"]["run_started"] is False
    _pair(client, _undo(sheet, seen_me="done"), False)

    held = _direct_done(client, lead)  # 보류 — 완료 취소는 되지만 보류 주문의 회차는 건드리지 않는다
    patch_sd(held.id, hold={"active": True, "reason": "자재 기다림", "at": "2026-11-27T00:00:00", "by_name": "박반장"})
    _pair(client, _undo(held, seen_me="done"), False)


def test_undo_gates_match_the_card_write(client):
    order = _direct_done(client, _lead())
    body = _undo(order, seen_me="done")
    assert _ask(client, {**body, "seen": "none"}).status_code == 400  # 본 상태가 미정인 완료 취소 = 쓰기와 같은 400
    assert client.post("/api/production/part-marks", json={**body, "seen": "none"}).status_code == 400
    login(client, _kim())  # 파트 계정은 남(반장)이 완료한 도면을 되돌릴 수 없다 — 미리 보기도 쓰기와 같은 거절
    asked, wrote = _ask(client, _undo(order)), client.post("/api/production/part-marks", json=_undo(order))
    assert (asked.status_code, wrote.status_code) == (403, 403) and current_runs(order.id) == 1
    assert asked.get_json()["data"]["code"] == wrote.get_json()["data"]["code"] == "UNDO_NOT_MINE"


# --------------------------------------------------------------------------- #
# 화면 — 창 글(서버 답은 진짜 API JSON)
# --------------------------------------------------------------------------- #
def test_js_direct_done_undo_dialog_line_and_status(client, cohort, tmp_path):
    lead, kim = _lead(), _kim()
    only = _direct_done(client, lead)  # 유일한 표시 — 줄이 뜬다
    busy = _direct_done(client, lead, 2)  # 다른 도면을 김재단이 시작 — 줄 없음
    login(client, kim)
    mark(client, busy, 1, "cut", "take", "none")
    page = tmp_path / "lead.html"
    page.write_text(_page(client, lead, CUT_ADMIN), encoding="utf-8")
    undo_only, undo_busy = _undo(only, seen_me="done"), _undo(busy, seen_me="done")
    no, yes = _answer(client, lead, undo_busy), _answer(client, lead, undo_only)
    assert (no["data"]["run_cancelled"], yes["data"]["run_cancelled"]) == (False, True)
    sent = {**undo_only, "seen_cancel": True}  # 화면이 보내는 몸 = 묻는 칸 + 창이 보여 준 것(줄 있음)
    res = _node(page, {"posts": [_post(client, lead, sent)], "previews": [no, yes], "steps": [
        {"do": "click", "key": busy.keys[0], "act": "undo"}, {"do": "modal"}, {"do": "close"},  # 0 1 2
        {"do": "click", "key": only.keys[0], "act": "undo"}, {"do": "modal"}, {"do": "run"}]})  # 3 4 5
    out = res["out"]
    quiet = out[1]["modal"]
    assert (quiet["title"], quiet["line"], quiet["body"], quiet["run"]["locked"]) == ("재단 완료를 취소할까요?", "재단 완료 → 미정", "", False)
    assert out[3]["modal"]["body"] == "" and out[3]["modal"]["run"]["locked"] is True  # 답이 오기 전 — 잠금
    shown = out[4]["modal"]
    assert (shown["title"], shown["line"], shown["run"]["text"]) == ("재단 완료를 취소할까요?", "재단 완료 → 미정", "재단 완료 취소")
    assert shown["body"] == UNDO_LINE and shown["run"]["locked"] is False
    assert out[5]["sent"] == 1 and out[5]["status"] == "재단 완료 취소했어요" + CANCELLED_TAIL
    assert [c["body"] for c in res["calls"]] == [sent]
    assert [_query(u) for u in res["previews"]] == [_as_query(undo_busy), _as_query(undo_only)]  # 묻는 칸 = 그 창이 보낼 몸


def test_js_basic_undo_dialog_and_part_account_done_undo(client, cohort, tmp_path):
    kim = _kim()
    login(client, kim)
    basic = make_order(1, run=False)
    assert mark(client, basic, 0, "cut", "basic", "none").get_json()["data"]["run_started"] is True
    done = make_order(1, run=False)
    assert finish(client, done, 0, "cut").status_code == 200
    page = tmp_path / "kim.html"
    page.write_text(_page(client, kim), encoding="utf-8")
    res = _node(page, {"steps": [{"do": "click", "key": basic.keys[0], "act": "undo"}, {"do": "close"},
                                 {"do": "click", "key": done.keys[0], "act": "undo"}, {"do": "close"}]})
    asked = [_query(u) for u in res["previews"]]  # 화면이 실제로 묻는 칸 — 아래에서 그 칸 그대로 진짜 API 에 묻는다
    assert [(q["order_id"], q["action"], q["seen"]) for q in asked] == [(str(basic.id), "undo", "basic"), (str(done.id), "undo", "done")]
    bodies = [{**q, "order_id": int(q["order_id"])} for q in asked]
    yes, no = _answer(client, kim, bodies[0]), _answer(client, kim, bodies[1])
    assert (yes["data"]["run_cancelled"], no["data"]["run_cancelled"]) == (True, False)
    sent = {**bodies[0], "seen_cancel": True}
    res = _node(page, {"posts": [_post(client, kim, sent)], "previews": [no, yes], "steps": [
        {"do": "click", "key": done.keys[0], "act": "undo"}, {"do": "modal"}, {"do": "close"},   # 0 1 2
        {"do": "click", "key": basic.keys[0], "act": "undo"}, {"do": "modal"}, {"do": "run"}]})  # 3 4 5
    out = res["out"]
    back = out[1]["modal"]  # 작업 중으로만 돌아가는 완료 취소 — 묻지만 답이 거짓이라 줄이 없다
    assert (back["title"], back["line"], back["body"]) == ("재단 완료를 취소할까요?", "재단 완료 → 작업 중 · 김재단", "")
    shown = out[4]["modal"]
    assert (shown["title"], shown["line"], shown["run"]["text"], shown["body"]) == ("기본을 취소할까요?", "기본 → 미정", "기본 취소", UNDO_LINE)
    assert out[5]["sent"] == 1 and out[5]["status"] == "기본 취소했어요" + CANCELLED_TAIL
    assert [c["body"] for c in res["calls"]] == [sent]


def test_js_other_dialogs_ask_nothing(client, cohort, tmp_path):
    """[시작] · [기본] · [완료] · [같이 작업] · [담당 바꾸기] · 반장 [완료] · [남은 N장 모두 기본] 창은 미리 보기 요청 0."""
    kim, oh, lead = _kim(), _oh(), _lead()
    order = make_order(4, run=False)
    login(client, kim)
    mark(client, order, 1, "cut", "take", "none")
    login(client, oh)
    mark(client, order, 2, "cut", "take", "none")
    k = order.keys
    page = tmp_path / "kim.html"
    page.write_text(_page(client, kim), encoding="utf-8")
    steps = []
    for key, act in ((k[0], "take"), (k[0], "basic"), (k[1], "done"), (k[2], "join"), (k[2], "held")):
        steps += [{"do": "click", "key": key, "act": act}, {"do": "close"}]
    res = _node(page, {"steps": steps})
    titles = [o["modal"]["title"] for o in res["out"] if o["do"] == "click"]
    assert titles == ["재단 시작할까요?", "기본으로 처리할까요?", "재단 완료할까요?", "재단 같이 작업할까요?", "담당을 오재단에서 김재단으로 바꿀까요?"]
    assert res["previews"] == [] and res["calls"] == []
    assert all(o["modal"]["run"]["locked"] is False for o in res["out"] if o["do"] == "click")
    fresh_order = make_order(1, run=False)
    page = tmp_path / "lead.html"
    page.write_text(_page(client, lead, CUT_ADMIN), encoding="utf-8")
    res = _node(page, {"steps": [{"do": "click", "key": fresh_order.keys[0], "act": "check"}, {"do": "close"},
                                 {"do": "click", "key": k[2], "act": "check"}, {"do": "close"}]})
    assert res["out"][0]["modal"]["body"] == FIRST_LINE and res["previews"] == []


def test_js_choice_dialog_names_every_flagged_button_in_one_line(client, cohort, tmp_path):
    """고르기 창에 시작 취소 단추가 둘일 때 — 진짜 서버는 둘 다 거짓(한 사람만 빼서는 미정이 안 된다, 앞 파일이 짝지어 확인).
    참인 단추만 이름을 부르고, 둘 다 참이면 줄 둘이 아니라 한 줄에 잇는다. 아래 참 답은 **지어낸 답**이다(글 꼴만 본다)."""
    kim, oh, lead = _kim(), _oh(), _lead()
    both = _took(client, kim)
    login(client, oh)
    mark(client, both, 0, "cut", "join", "need", seen_me="none")
    page = tmp_path / "lead.html"
    page.write_text(_page(client, lead, CUT_ADMIN), encoding="utf-8")
    real = [_answer(client, lead, _body(both, action="remove", seen_by=kim.id, target_user_id=who.id)) for who in (kim, oh)]
    assert [a["data"]["run_cancelled"] for a in real] == [False, False]
    made_yes = {"success": True, "data": {"run_cancelled": True}, "error": None}
    made_no = {"success": True, "data": {"run_cancelled": False}, "error": None}
    click = {"do": "click", "key": both.keys[0], "act": "held"}
    res = _node(page, {"previews": [*real, made_no, made_yes, made_yes, made_yes], "steps": [
        click, {"do": "modal"}, {"do": "close"}, click, {"do": "modal"}, {"do": "close"}, click, {"do": "modal"}]})
    bodies = [o["modal"]["body"] for o in res["out"] if o["do"] == "modal"]
    assert bodies == ["", "[오재단 시작 취소]를 누르면 제작 시작도 같이 취소돼요.",
                      "[김재단 시작 취소] · [오재단 시작 취소]를 누르면 제작 시작도 같이 취소돼요."]
    assert len(res["previews"]) == 6 and res["calls"] == []

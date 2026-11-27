"""반장 · 관리자가 바로 완료한 도면의 [완료 취소] = 한 번에 미정(사장님 2026-11-27 "한 번에 미정으로" — 취소는 완료 전 모습으로).

바로 완료한 도면 = 그 파트 표시 줄에서 작업한 사람이 한 명뿐이고 그 사람이 시작과 자기 몫 완료를 **한 요청에서** 적은 줄
(``mark_crew.done_at_once`` — 시작한 때 == 완료한 때 · 완료한 사람 == 그 사람, 시간 문턱 없음). 반장 · 관리자 누구든 [<파트> 완료 취소]를
누르면 서버가 한 tx 에서 완료 취소 + 시작 취소를 같이 해 표시 줄이 NONE(재단 '안 봄' — 다시 셈), 감사는 한 줄 "재단 재단 완료 → 안 봄".

* 대조군(지금 그대로): 남이 시작한 도면을 반장이 대신 완료 → 취소 = 그 사람 작업 중 · 반장이 [작업 시작] 뒤 따로 [완료] → 취소 = 반장
  작업 중(한 요청이 아님) · 같이 작업 도면 · 파트 계정은 남의 완료를 못 되돌림(403) · 검수 완료 뒤 앞 공정 취소 거절 · 보류 중에도 취소는 됨 ·
  도면이 연 제작 시작은 표시가 모두 미정이 되면 같이 되돌림(2026-11-27 결정 — ``test_production_start_rollback_1127.py``).
* 화면: 창 줄 "재단 완료 → 미정" / "엣지 완료 → 미정"(화면 글은 재단도 '미정' — 11-26)(대조 "재단 완료 → 이시영 작업 중") · 끝난 뒤 알림 "재단 완료 취소했어요" · 칸이
  미정 칸으로 · 숫자 · 409 뒤 · 받아 오기 다시 그리기.

되돌리면 실패: 취소 뒤 "박반장 작업 중" · 감사 두 줄 · 대신 완료한 도면까지 미정 · 시간 문턱(2분) · 창 줄 "→ 작업 중". 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import copy
from pathlib import Path

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.production import mark_crew as mc
from foms.services.production.part_card_crew import crew_view
from tests.domains.test_production_lead_direct_done_1127 import (
    CUT_LEAD_NONE,
    EDGE_ADMIN,
    EDGE_LEAD_NONE,
    INSPECT_ADMIN,
    _admin,
    _box,
    _check,
    _lead,
)
from tests.domains.test_production_multi_holder_api import _audits, _names
from tests.domains.test_production_multi_holder_board import CUT_ADMIN, _act, _card, _crew, _node, _page, _post, cohort  # noqa: F401
from tests.support.production_part_claim_seed import (
    BULK,
    code,
    current_runs,
    events,
    finish,
    login,
    make_order,
    make_user,
    mark,
    patch_sd,
    row,
    step,
)

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static/js/production"
CREW_JS = JS / "foms-production-parts-crew.js"


def _undo(client, order, j: int, part: str = "cut", seen_me: str = "done"):
    """화면이 보내는 몸 그대로 — 완료 칸 [<파트> 완료 취소](대상 없음, 본 내 몫 = 바로 완료한 사람이면 done · 다른 반장이면 none)."""
    return mark(client, order, j, part, "undo", "done", seen_me=seen_me)


def _undo_body(order, j: int, part: str = "cut", seen_me: str = "done") -> dict:
    return {"order_id": order.id, "drawing_key": order.keys[j], "part": part, "action": "undo", "seen": "done", "seen_me": seen_me}


def _cleared(order, j: int, part: str = "cut") -> None:
    saved = row(order.id, order.keys[j], part)
    assert (saved.state, saved.picked_by_name, saved.done_by_name, saved.picked_at, saved.done_at) == ("NONE", None, None, None, None)
    assert _names(order.id, order.keys[j], part) == []


# --------------------------------------------------------------------------- #
# 판정 — 한 요청에서 시작 + 완료(시간 문턱 없음)
# --------------------------------------------------------------------------- #
def test_done_at_once_is_one_person_started_and_finished_in_one_press() -> None:
    at = "2026-11-27T01:00:00.123456+00:00"
    once = mc.member(7, "박반장", at, done_at=at, done_uid=7, done_name="박반장")
    assert mc.done_at_once([once]) is True
    later = mc.member(7, "박반장", at, done_at="2026-11-27T01:00:01.000001+00:00", done_uid=7, done_name="박반장")
    proxy = mc.member(3, "이시영", at, done_at=at, done_uid=7, done_name="박반장")  # 완료한 사람이 그 사람이 아님
    held = mc.member(7, "박반장", at)
    assert [mc.done_at_once(c) for c in ([later], [proxy], [held], [once, later], [])] == [False] * 5
    rows = [{"user_id": 7, "name": "박반장", "done": True, "picked_at": at, "done_at": at, "done_name": "박반장", "once": True}]
    assert crew_view(rows, 7, "박반장")["once"] is True and crew_view(rows + rows, 7, "박반장")["once"] is False
    assert crew_view([{**rows[0], "once": False}], 7, "박반장")["once"] is False


# --------------------------------------------------------------------------- #
# API — 바로 완료 → [완료 취소] = 한 번에 미정
# --------------------------------------------------------------------------- #
def test_lead_undoes_own_direct_done_to_unseen_in_one_press(client):
    order = make_order(2)
    login(client, _lead())
    assert _check(client, order, 0).status_code == 200
    res = _undo(client, order, 0)
    assert res.status_code == 200, res.get_json()
    data = res.get_json()["data"]
    assert (data["changed"], data["mark"]["state"], data["mark"]["holders"], data["mark"]["crew"]["n"]) == (True, "none", [], 0)
    _cleared(order, 0)
    audits = _audits(order.id)
    assert len(audits) == 2 and "재단 재단 완료 → 안 봄" in audits[-1]  # 감사 한 줄(지금 낱말 함수) — 시작 취소 줄이 따로 안 생김
    assert "(대신 처리)" not in audits[-1] and "시작 취소" not in audits[-1]
    payload = events(order.id, "PRODUCTION_PART_MARKED")[-1].payload
    assert (payload["action"], payload["from"], payload["to"], payload["override"]) == ("undo", "DONE", "NONE", False)
    assert [h["name"] for h in payload["holders_before"]] == ["박반장"] and payload["holders_after"] == []
    again = _undo(client, order, 0)  # 연결이 얼어 두 번 = 멱등(이미 미정)
    assert again.status_code == 200 and again.get_json()["data"]["changed"] is False
    assert again.get_json()["data"]["mark"]["state"] == "none" and len(_audits(order.id)) == 2
    took = mark(client, order, 0, "cut", "take", "none")  # 미정이라 다시 [작업 시작] · [기본] · [재단 완료]가 된다
    assert took.status_code == 200 and took.get_json()["data"]["mark"]["state"] == "need"


def test_other_lead_and_admin_undo_direct_done_to_unseen_with_proxy_tail(client):
    order = make_order(2)
    login(client, _lead())
    _check(client, order, 0)
    login(client, _admin())
    res = _undo(client, order, 0, seen_me="none")  # 관리자가 반장이 바로 완료한 도면을 취소
    assert res.status_code == 200 and res.get_json()["data"]["mark"]["state"] == "none"
    _cleared(order, 0)
    assert "재단 재단 완료 → 안 봄 (관리자 덮어쓰기)" in _audits(order.id)[-1]
    assert events(order.id, "PRODUCTION_PART_MARKED")[-1].payload["holder_name"] == "박반장"
    _check(client, order, 1, "edge")  # 관리자가 엣지를 바로 완료 → 다른 반장이 취소
    login(client, make_user("원반장", lead=True))
    res = _undo(client, order, 1, "edge", seen_me="none")
    assert res.status_code == 200 and res.get_json()["data"]["mark"]["state"] == "none"
    _cleared(order, 1, "edge")
    assert "엣지 엣지 완료 → 안 고름 (대신 처리)" in _audits(order.id)[-1]


def test_no_time_window_old_direct_done_still_goes_to_unseen(client):
    """PC 는 '2분 안'(undo_releases)이지만 태블릿은 시간 문턱이 없다 — 사흘 전에 바로 완료한 도면도 한 번에 미정."""
    order = make_order(1)
    login(client, _lead())
    _check(client, order, 0)
    saved = row(order.id, order.keys[0], "cut")
    holders = copy.deepcopy(saved.holders)
    holders[0]["at"] = holders[0]["done_at"] = "2026-11-24T00:00:00+00:00"
    saved.holders = holders
    flag_modified(saved, "holders")
    db_session.commit()
    assert _undo(client, order, 0).get_json()["data"]["mark"]["state"] == "none"
    _cleared(order, 0)


# --------------------------------------------------------------------------- #
# 대조군 — 지금 그대로
# --------------------------------------------------------------------------- #
def test_proxy_finish_undo_returns_to_starter_working(client):
    order = make_order(1)
    login(client, make_user("이시영", part="cut"))
    mark(client, order, 0, "cut", "take", "none")
    login(client, _lead())
    assert _check(client, order, 0).get_json()["data"]["proxied"] is True  # 남이 시작한 도면을 대신 완료
    res = _undo(client, order, 0, seen_me="none")
    assert res.status_code == 200 and res.get_json()["data"]["mark"]["state"] == "need"
    assert _names(order.id, order.keys[0]) == [("이시영", False)] and row(order.id, order.keys[0], "cut").picked_by_name == "이시영"
    assert "재단 재단 완료 → 작업 필요 (대신 처리)" in _audits(order.id)[-1]


def test_lead_take_then_separate_done_undo_keeps_lead_working(client):
    """[작업 시작] 뒤 따로 [재단 완료](두 요청 — 1초 안이어도) = 바로 완료가 아님 → 지금처럼 "박반장 작업 중"."""
    order = make_order(1)
    login(client, _lead())
    assert mark(client, order, 0, "cut", "take", "none").status_code == 200
    assert mark(client, order, 0, "cut", "done", "need", seen_me="held").get_json()["data"]["mark"]["state"] == "done"
    res = _undo(client, order, 0)
    assert res.status_code == 200 and res.get_json()["data"]["mark"]["state"] == "need"
    assert _names(order.id, order.keys[0]) == [("박반장", False)]
    assert "재단 재단 완료 → 작업 필요" in _audits(order.id)[-1]


def test_crew_drawing_and_part_account_undo_are_unchanged(client):
    order = make_order(2)
    lee, kim = make_user("이시영", part="cut"), make_user("김재단", part="cut")
    login(client, lee)
    mark(client, order, 0, "cut", "take", "none")
    login(client, kim)
    mark(client, order, 0, "cut", "join", "need")
    for who in (lee, kim):
        login(client, who)
        mark(client, order, 0, "cut", "done", "need", seen_me="held")
    login(client, _lead())
    res = _undo(client, order, 0, seen_me="none")  # 같이 작업 도면 = 완료만 모두 끄고 둘 다 작업 중(Q23)
    assert res.status_code == 200 and res.get_json()["data"]["mark"]["state"] == "need"
    assert _names(order.id, order.keys[0]) == [("이시영", False), ("김재단", False)]
    _check(client, order, 1)  # 반장이 바로 완료한 도면을 파트 계정이 취소 = 403 그대로
    login(client, lee)
    res = _undo(client, order, 1, seen_me="none")
    assert (res.status_code, code(res)) == (403, "UNDO_NOT_MINE")
    assert row(order.id, order.keys[1], "cut").state == "DONE"


def test_part_account_own_undo_keeps_working(client):
    order = make_order(1)
    login(client, make_user("김재단", part="cut"))
    finish(client, order, 0, "cut")
    res = _undo(client, order, 0)
    assert res.status_code == 200 and res.get_json()["data"]["mark"]["state"] == "need"
    assert _names(order.id, order.keys[0]) == [("김재단", False)]


def test_gates_stay_inspect_done_blocks_hold_allows_and_card_started_run_rolls_back(client):
    login(client, _lead())
    order = make_order(1)
    for part in ("cut", "edge", "assemble", "inspect"):
        assert _check(client, order, 0, part).status_code == 200
    res = _undo(client, order, 0)
    assert (res.status_code, code(res)) == (409, "INSPECT_DONE_FIRST")  # 검수 완료 뒤 앞 공정 취소 금지 그대로
    assert row(order.id, order.keys[0], "cut").state == "DONE"
    held = make_order(1)
    _check(client, held, 0)
    patch_sd(held.id, hold={"active": True, "reason": "자재 기다림"})
    assert _undo(client, held, 0).get_json()["data"]["mark"]["state"] == "none"  # 보류 중에도 취소는 된다
    waiting = make_order(2, run=False)
    assert _check(client, waiting, 0).get_json()["data"]["run_started"] is True
    res = _undo(client, waiting, 0)
    assert res.get_json()["data"]["mark"]["state"] == "none" and res.get_json()["data"]["run_started"] is False
    # 2026-11-27 결정: 표시가 모두 미정이 되면 도면이 연 제작 시작도 같이 되돌린다([시작 취소]와 같은 규칙 — 11-23 "그대로"를 뒤집음)
    assert res.get_json()["data"]["run_cancelled"] is True and current_runs(waiting.id) == 0
    assert _audits(waiting.id)[-1].endswith(" · 제작 시작 취소")


def test_one_sheet_order_step_turns_off_and_card_is_not_locked(client):
    """도면 1장 주문 — 바로 완료로 켜진 공정 칸이 취소 뒤 꺼진다(남으면 손 체크 칸으로 잠겨 409 ``STEP_SET_BY_HAND``)."""
    order = make_order(1)
    login(client, _admin())
    assert _check(client, order, 0, "edge").get_json()["data"]["order_step"]["done"] is True
    data = _undo(client, order, 0, "edge").get_json()["data"]
    assert data["mark"]["state"] == "none" and data["order_step"]["done"] is False and step(order.id, "edge")["done"] is False
    assert " · 공정 엣지 끔" in _audits(order.id)[-1]
    again = mark(client, order, 0, "edge", "take", "none")
    assert again.status_code == 200, again.get_json()  # 다시 [작업 시작]이 된다
    two = make_order(2)  # 대조 — 2장 주문은 남은 장이 완료 줄이라 지금 규칙으로 꺼짐
    for j in (0, 1):
        _check(client, two, j, "edge")
    assert _undo(client, two, 0, "edge").get_json()["data"]["order_step"]["done"] is False


# --------------------------------------------------------------------------- #
# 화면 — 서버가 그린 판
# --------------------------------------------------------------------------- #
def test_board_after_undo_shows_unseen_cell_counts_and_once_flag(client, cohort):
    order = make_order(3)
    lead = _lead()
    login(client, make_user("이시영", part="cut"))
    mark(client, order, 2, "cut", "take", "none")
    login(client, lead)
    _check(client, order, 0)
    _check(client, order, 2)  # 대신 완료(대조)
    page = _page(client, lead, CUT_ADMIN)
    assert _crew(_card(page, order.keys[0]))["once"] is True and _crew(_card(page, order.keys[2]))["once"] is False
    assert "안 본 도면 <b>1</b>장" in page
    login(client, lead)
    _undo(client, order, 0)
    page = _page(client, lead, CUT_ADMIN)
    assert _box(page, order.keys[0]) == CUT_LEAD_NONE and "data-pp-crew" not in _card(page, order.keys[0])
    assert "안 본 도면 <b>2</b>장" in page and '남은 <span data-pp-count="unseen">2</span>장 모두 기본' in page
    admin = _admin()
    login(client, admin)
    _check(client, order, 1, "edge")
    assert _undo(client, order, 1, "edge").status_code == 200
    assert _box(_page(client, admin, EDGE_ADMIN), order.keys[1]) == EDGE_LEAD_NONE


# --------------------------------------------------------------------------- #
# 화면 — JS(서버가 그린 판 위에서, 서버 답은 진짜 API JSON)
# --------------------------------------------------------------------------- #
def test_js_cut_undo_window_unseen_cell_and_counts(client, cohort, tmp_path):
    order = make_order(3)
    lead = _lead()
    login(client, lead)
    _check(client, order, 0)
    page = tmp_path / "lead.html"
    page.write_text(_page(client, lead, CUT_ADMIN), encoding="utf-8")
    k = order.keys
    reply = _post(client, lead, _undo_body(order, 0))
    assert reply["data"]["mark"]["state"] == "none"
    res = _node(page, {"posts": [reply], "steps": [
        {"do": "parity"}, {"do": "card", "key": k[0]}, {"do": "click", "key": k[0], "act": "undo"}, {"do": "run"},
        {"do": "card", "key": k[0]}]})
    out, calls = res["out"], res["calls"]
    assert out[0]["diffs"] == []
    w = out[2]["modal"]
    assert (w["title"], w["line"], w["run"]["text"], w["body"]) == ("재단 완료를 취소할까요?", "재단 완료 → 미정", "재단 완료 취소", "")
    assert calls[0]["body"] == {**_undo_body(order, 0), "seen_cancel": False}  # 취소 창이 보여 준 것까지(줄 없음 — 11-27 "창에 보인 대로만 된다")
    assert out[3]["sent"] == 1 and out[3]["modal"]["hidden"] is True and out[3]["status"] == "재단 완료 취소했어요"
    before, after = out[1], out[4]
    assert (after["card"]["state"], after["card"]["in_done"], after["card"]["in_need"], after["card"]["crew"]) == ("none", "0", "0", {})
    assert [a["act"] for a in after["card"]["act"][0]["kids"]] == ["basic", "take"] and after["card"]["act"][1]["act"] == "check"
    assert int(after["counts"]["done"][0]) == int(before["counts"]["done"][0]) - 1
    assert int(after["counts"]["unseen"][0]) == int(before["counts"]["unseen"][0]) + 1  # [남은 N장 모두 기본]
    assert after["counts"]["need"] == before["counts"]["need"] and after["counts"]["all"] == before["counts"]["all"]


def test_js_edge_window_line_and_proxy_control(client, cohort, tmp_path):
    order = make_order(2)
    admin = _admin()
    login(client, make_user("이시영", part="cut"))
    mark(client, order, 1, "cut", "take", "none")
    login(client, admin)
    _check(client, order, 0, "edge")
    _check(client, order, 1)  # 재단 대신 완료(대조)
    _check(client, order, 0)  # 재단 바로 완료
    edge = tmp_path / "edge.html"
    edge.write_text(_page(client, admin, EDGE_ADMIN), encoding="utf-8")
    out = _node(edge, {"steps": [{"do": "click", "key": order.keys[0], "act": "undo"}]})["out"]
    assert (out[0]["modal"]["title"], out[0]["modal"]["line"]) == ("엣지 완료를 취소할까요?", "엣지 완료 → 미정")
    cut = tmp_path / "cut.html"
    cut.write_text(_page(client, admin, CUT_ADMIN), encoding="utf-8")
    out = _node(cut, {"steps": [{"do": "click", "key": order.keys[1], "act": "undo"}, {"do": "close"},
                                {"do": "click", "key": order.keys[0], "act": "undo"}]})["out"]
    assert out[0]["modal"]["line"] == "재단 완료 → 이시영 작업 중"  # 대신 완료한 도면 = 지금 창 그대로
    assert out[2]["modal"]["line"] == "재단 완료 → 미정"


def test_js_409_and_synced_mark_redraw_unseen(client, cohort, tmp_path):
    order = make_order(2)
    lead, admin = _lead(), _admin()
    login(client, lead)
    _check(client, order, 0)
    _check(client, order, 1)
    page = tmp_path / "lead.html"
    page.write_text(_page(client, lead, CUT_ADMIN), encoding="utf-8")
    login(client, admin)  # 그사이 관리자가 두 장 모두 취소 — 반장 화면은 아직 완료
    _undo(client, order, 0, seen_me="none")
    _undo(client, order, 1, seen_me="none")
    refused = _post(client, lead, _undo_body(order, 0))
    assert refused["__status"] == 409 and refused["body"]["data"]["mark"]["state"] == "none"
    login(client, lead)
    got = client.get(f"/api/production/part-marks?order_ids={order.id}&since=2000-01-01T00:00:00").get_json()["data"]["marks"]
    synced = next(m for m in got if m["drawing_key"] == order.keys[1] and m["part"] == "cut")
    assert synced["state"] == "none"
    res = _node(page, {"posts": [refused], "steps": [
        {"do": "click", "key": order.keys[0], "act": "undo"}, {"do": "run"}, {"do": "card", "key": order.keys[0]},
        {"do": "apply", "key": order.keys[1], "mark": synced}]})
    out = res["out"]
    assert out[1]["modal"]["lost"] is True and out[1]["modal"]["err"] == refused["body"]["error"]  # 서버 글 그대로
    for got_card in (out[2]["card"], out[3]["card"]):  # 409 뒤 서버 모습 · 받아 오기 표시로 다시 그려도 미정 칸
        assert got_card["state"] == "none" and [a["act"] for a in got_card["act"][0]["kids"]] == ["basic", "take"]
        assert got_card["act"][1]["act"] == "check"


def test_inspect_board_after_cut_undo_is_pre(client, cohort):
    order = make_order(1)
    lead = _lead()
    login(client, lead)
    _check(client, order, 0)
    _undo(client, order, 0)
    pre = _act(_card(_page(client, lead, INSPECT_ADMIN), order.keys[0]))
    assert "pp-st-pre" in pre and 'data-pp-act="check"' not in pre  # 재단이 미정으로 돌아가 검수 전 칸


# --------------------------------------------------------------------------- #
# JS 원문 계약
# --------------------------------------------------------------------------- #
def test_source_contract_undo_line_from_server_flag():
    crew = CREW_JS.read_text(encoding="utf-8")
    assert "if (action === 'undo' && st === 'done' && cr.once && !MINE) {" in crew
    assert "line: LABEL + ' 완료 → 미정', run:" in crew and "'안 봄' : '미정'" not in crew  # 화면 글은 재단도 '미정'(11-26)
    assert crew.index("cr.once && !MINE") < crew.index("(cr.me !== 'done' || !MINE)")  # 대신 되돌리기 창보다 먼저
    assert len(crew.splitlines()) <= 300


# --------------------------------------------------------------------------- #
# 같은 뿌리 — [기본] → [기본 취소]로 기본 줄이 미정이 되면 공정 칸도 맞춘다(옛 결함: 1장 주문 칸이 켜진 채 손 체크로 잠김)
# --------------------------------------------------------------------------- #
def _one_sheet_basic_undo_unlocks(client, order) -> None:
    assert step(order.id, "cut")["done"] is True
    data = mark(client, order, 0, "cut", "undo", "basic").get_json()["data"]
    assert data["mark"]["state"] == "none" and data["order_step"]["done"] is False and step(order.id, "cut")["done"] is False
    assert " · 공정 재단 끔" in _audits(order.id)[-1]
    took = mark(client, order, 0, "cut", "take", "none")  # 옛 결함: 409 STEP_SET_BY_HAND
    assert took.status_code == 200, took.get_json()


def test_basic_undo_on_one_sheet_order_turns_step_off_one_card(client):
    order = make_order(1)
    login(client, make_user("김재단", part="cut"))
    assert mark(client, order, 0, "cut", "basic", "none").get_json()["data"]["order_step"]["done"] is True
    _one_sheet_basic_undo_unlocks(client, order)


def test_basic_undo_after_bulk_basic_turns_step_off(client):
    """[남은 N장 모두 기본](일괄)으로 켜진 칸도 — [기본 취소]는 한 장씩 길(mark_one) 하나다."""
    order = make_order(1)
    login(client, make_user("김재단", part="cut"))
    res = client.post(BULK, json={"part": "cut", "seen": "none", "items": [{"order_id": order.id, "drawing_key": order.keys[0]}]})
    assert res.status_code == 200 and res.get_json()["data"]["order_steps"][0]["done"] is True
    _one_sheet_basic_undo_unlocks(client, order)


def test_basic_undo_on_multi_sheet_order_keeps_today_rule(client):
    """대조 — 다른 장이 남아 있으면 지금 규칙(모든 장 완료일 때만 켬) 그대로: 켜진 칸은 지금처럼 꺼지고, 꺼진 칸은 그대로 꺼진 채."""
    login(client, make_user("김재단", part="cut"))
    both = make_order(2)
    for j in (0, 1):
        mark(client, both, j, "cut", "basic", "none")
    assert step(both.id, "cut")["done"] is True
    data = mark(client, both, 0, "cut", "undo", "basic").get_json()["data"]
    assert data["order_step"]["done"] is False and row(both.id, both.keys[1], "cut").state == "BASIC"
    one = make_order(2)  # 한 장만 기본 = 칸 꺼짐 → 그 장 [기본 취소] 뒤에도 칸은 그대로(바뀜 없음)
    mark(client, one, 1, "cut", "basic", "none")
    assert step(one.id, "cut")["done"] is False
    data = mark(client, one, 1, "cut", "undo", "basic").get_json()["data"]
    assert data["mark"]["state"] == "none" and data["order_step"] is None and step(one.id, "cut")["done"] is False
    assert mark(client, one, 1, "cut", "take", "none").status_code == 200

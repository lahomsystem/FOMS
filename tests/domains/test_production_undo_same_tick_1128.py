"""[완료 취소]가 가끔 미정으로 가던 결함 — 시작과 완료가 같은 시각이어도 '바로 완료'로 치지 않는다(2026-11-28).

옛 판정(``mark_crew.done_in_one_press``)은 "시작한 때 == 완료한 때"만 봤다 — 주석은 "따로 누른 두 요청은 같은 시각을 못 쓴다"였지만 시계
눈금(Windows 는 0.3 ~ 16ms)이 요청 하나보다 굵으면 [작업 시작] 뒤 따로 누른 [완료]도 같은 시각이 적혔고, 반장 · 관리자가 그 완료를 취소하면
'작업 중'이 아니라 미정이 됐다(가끔 실패하던 시험 셋의 뿌리). 고친 뒤: 완료를 적을 때 "한 요청에서 시작 + 완료"인지를 목록 칸 ``once``
에 **적어 둔다** — 시각은 판정에 쓰지 않는다. ``once`` 가 없는 옛 칸(이 고침 전에 완료한 줄)만 지금처럼 시각으로 읽는다.

이 파일은 시계를 한 시각에 세워 놓고(:func:`frozen`) 누른다 — 옛 코드에서는 늘 실패하고 고친 코드에서는 늘 통과한다(sleep · 재시도 없음).
사장님 규칙은 그대로: 반장 · 관리자가 바로 [완료 처리]한 것의 취소 = 미정, 시작한 뒤 따로 완료한 것의 취소 = 작업 중.

되돌리면 실패: 같은 시각에 시작 · 완료한 줄의 취소가 미정 / 창 줄 "→ 미정" / 제작 시작까지 취소. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import datetime

import pytest

from foms.services.production import mark_crew as mc
from foms.services.production import part_mark_write
from foms.services.production.part_mark_decide import decide_mark
from foms.services.production.part_mark_rules import MarkSnapshot, holder_rows
from tests.domains.test_production_cancel_notice_1127 import _pair
from tests.domains.test_production_lead_direct_done_1127 import _admin, _check, _lead
from tests.domains.test_production_multi_holder_api import _audits, _names
from tests.support.production_part_claim_seed import finish, login, make_order, make_user, mark, row

T = datetime.datetime(2026, 11, 28, 1, 0, 0, 123456)
T_ISO = "2026-11-28T01:00:00.123456+00:00"


@pytest.fixture
def frozen(monkeypatch):
    """표시 쓰기가 읽는 시계를 한 시각에 세운다 — 모든 누름이 같은 시각을 적는다(시계 눈금 하나 안에 두 요청이 든 꼴)."""
    monkeypatch.setattr(part_mark_write, "now_utc_naive", lambda: T)
    return T


def _undo(order, seen_me: str = "none", part: str = "cut") -> dict:
    return {"order_id": order.id, "drawing_key": order.keys[0], "part": part, "action": "undo", "seen": "done", "seen_me": seen_me}


def _stored(order, part: str = "cut") -> dict:
    return row(order.id, order.keys[0], part).holders[0]


# --------------------------------------------------------------------------- #
# 재현 — 같은 시각에 [작업 시작] · [완료]를 따로 누른 줄의 취소는 '작업 중'
# --------------------------------------------------------------------------- #
def test_lead_take_then_done_in_the_same_tick_undo_keeps_lead_working(client, frozen):
    order = make_order(1)
    login(client, _lead())
    assert mark(client, order, 0, "cut", "take", "none").status_code == 200
    done = mark(client, order, 0, "cut", "done", "need", seen_me="held").get_json()["data"]["mark"]
    saved = _stored(order)
    assert (saved["at"], saved["done_at"]) == (T_ISO, T_ISO)  # 준비물 확인 — 두 요청이 정말 같은 시각을 적었다
    assert (done["state"], done["holders"][0]["once"], done["crew"]["once"]) == ("done", False, False)  # 창 줄도 "→ 박반장 작업 중"
    res = mark(client, order, 0, "cut", "undo", "done", seen_me="done")
    assert res.status_code == 200 and res.get_json()["data"]["mark"]["state"] == "need"
    assert _names(order.id, order.keys[0]) == [("박반장", False)]
    assert "재단 재단 완료 → 작업 필요" in _audits(order.id)[-1]


def test_lead_undoing_a_workers_same_tick_done_keeps_worker_and_run(client, frozen):
    """가끔 실패하던 ``test_undo_that_only_goes_back_to_working_is_never_flagged`` 의 둘째 토막 — 창 깃발도 실제 결과도 '같이 취소 안 됨'."""
    kim = make_user("김재단", part="cut")
    order = make_order(1, run=False)
    login(client, kim)
    assert finish(client, order, 0, "cut").status_code == 200
    login(client, _lead())
    data = _pair(client, _undo(order), False)
    assert data["mark"]["state"] == "need" and _names(order.id, order.keys[0]) == [("김재단", False)]
    again = make_order(1)  # 관리자도 같은 답
    login(client, kim)
    finish(client, again, 0, "cut")
    login(client, _admin())
    assert mark(client, again, 0, "cut", "undo", "done", seen_me="none").get_json()["data"]["mark"]["state"] == "need"


def test_admin_own_take_then_done_on_every_part_undoes_to_working(client, frozen):
    """가끔 실패하던 ``test_one_finished_inspector_blocks_earlier_part_undo`` 의 끝 단언 — 관리자가 시작 · 완료를 따로 누른 파트 넷."""
    order = make_order(1)
    login(client, _admin())
    for part in ("cut", "edge", "assemble", "inspect"):
        assert finish(client, order, 0, part).status_code == 200
    for part in ("inspect", "assemble", "edge", "cut"):
        res = mark(client, order, 0, part, "undo", "done", seen_me="done")
        assert res.status_code == 200 and res.get_json()["data"]["mark"]["state"] == "need", part
        assert row(order.id, order.keys[0], part).state == "NEED"


def test_lead_start_then_pc_done_and_takeover_then_done_are_not_direct_done(client, frozen):
    order = make_order(2)
    lead = _lead()
    login(client, lead)
    mark(client, order, 0, "cut", "take", "none")
    assert _check_need(client, order, 0).get_json()["data"]["mark"]["state"] == "done"  # 시작한 뒤 PC [완료 처리](check) — 따로 누름
    assert mark(client, order, 0, "cut", "undo", "done", seen_me="done").get_json()["data"]["mark"]["state"] == "need"
    kim = make_user("김재단", part="cut")
    login(client, kim)
    mark(client, order, 1, "cut", "take", "none")
    login(client, lead)
    assert mark(client, order, 1, "cut", "takeover", "need", seen_me="none", seen_by=kim.id).status_code == 200
    mark(client, order, 1, "cut", "done", "need", seen_me="held")
    res = mark(client, order, 1, "cut", "undo", "done", seen_me="done")
    assert res.get_json()["data"]["mark"]["state"] == "need" and _names(order.id, order.keys[1]) == [("박반장", False)]


def _check_need(client, order, j: int):
    return mark(client, order, j, "cut", "check", "need", seen_me="held")


# --------------------------------------------------------------------------- #
# 대조군 — 사장님 규칙 그대로: 바로 [완료 처리]한 것의 취소는 미정
# --------------------------------------------------------------------------- #
def test_direct_done_in_the_same_tick_still_undoes_to_unseen(client, frozen):
    order = make_order(1, run=False)
    lead = _lead()
    login(client, lead)
    done = _check(client, order, 0).get_json()["data"]
    assert (done["mark"]["holders"][0]["once"], done["mark"]["crew"]["once"]) == (True, True)
    assert _stored(order)["once"] is True
    data = _pair(client, _undo(order, seen_me="done"), True)  # 미정 + 도면이 연 제작 시작도 같이 취소
    assert data["mark"]["state"] == "none" and row(order.id, order.keys[0], "cut").holders == []
    again = make_order(1)  # 다른 반장 · 관리자가 취소해도 미정
    _check(client, again, 0)
    login(client, _admin())
    assert mark(client, again, 0, "cut", "undo", "done", seen_me="none").get_json()["data"]["mark"]["state"] == "none"


def test_direct_done_then_undo_then_separate_done_is_working_again(client, frozen):
    """바로 완료 → 취소(미정) → 이번에는 [작업 시작] · [완료]를 따로 → 취소 = 작업 중(앞 완료의 표지가 남지 않는다)."""
    order = make_order(1)
    login(client, _lead())
    _check(client, order, 0)
    mark(client, order, 0, "cut", "undo", "done", seen_me="done")
    finish(client, order, 0, "cut")
    assert _stored(order)["once"] is False
    assert mark(client, order, 0, "cut", "undo", "done", seen_me="done").get_json()["data"]["mark"]["state"] == "need"
    assert "once" not in _stored(order)  # 완료를 끄면 표지도 지운다


# --------------------------------------------------------------------------- #
# 판정 — 순수 함수(시각이 아니라 적어 둔 표지)
# --------------------------------------------------------------------------- #
def test_finish_writes_the_flag_and_time_is_not_the_evidence() -> None:
    held = mc.join([], 7, "박반장", T)
    apart = mc.finish(held, 7, by_uid=7, by_name="박반장", now=T)  # 따로 누른 완료 — 같은 시각이어도 바로 완료가 아님
    assert (apart[0]["at"], apart[0]["done_at"], apart[0]["once"]) == (T_ISO, T_ISO, False)
    assert mc.done_in_one_press(apart[0]) is False and mc.done_at_once(apart) is False
    rest = mc.finish_rest(held, by_uid=7, by_name="박반장", now=T)
    assert rest[0]["once"] is False and mc.done_at_once(rest) is False
    once = mc.finish(held, 7, by_uid=7, by_name="박반장", now=T + datetime.timedelta(seconds=3), once=True)
    assert once[0]["at"] != once[0]["done_at"] and mc.done_at_once(once) is True  # 시각이 달라도 적힌 표지를 따른다
    assert "once" not in mc.unfinish(once)[0] and mc.done_at_once(mc.unfinish(once)) is False
    assert "once" not in held[0] and "once" not in mc.member(7, "박반장", T_ISO)  # 완료 전 칸 모양은 그대로


def test_decide_marks_only_the_empty_row_check_as_one_press() -> None:
    def crew(snap, action, seen, **kw):
        return decide_mark(snap, action=action, seen=seen, actor_id=7, admin=True, actor_name="박반장", now=T, **kw).crew

    direct = crew(MarkSnapshot.from_row(None), "check", "none")
    assert direct[0]["once"] is True
    took = crew(MarkSnapshot.from_row(None), "take", "none")
    row_need = _row(list(took), "NEED")
    for action in ("done", "check"):  # 시작한 줄의 [완료] · PC [완료 처리] — 같은 시각이어도 따로 누른 것
        done = crew(MarkSnapshot.from_row(row_need), action, "need")
        assert (done[0]["at"], done[0]["done_at"], done[0]["once"]) == (T_ISO, T_ISO, False)
        undo = decide_mark(MarkSnapshot.from_row(_row(list(done), "DONE")), action="undo", seen="done", actor_id=7, admin=True,
                           actor_name="박반장", now=T)
        assert (undo.target, [m["uid"] for m in undo.crew]) == ("NEED", [7])
    undo = decide_mark(MarkSnapshot.from_row(_row(list(direct), "DONE")), action="undo", seen="done", actor_id=7, admin=True,
                       actor_name="박반장", now=T)
    assert (undo.target, undo.crew) == ("NONE", ())


def _row(crew: list, state: str):
    from types import SimpleNamespace

    summary = mc.summarize(crew)
    return SimpleNamespace(state=state, holders=crew, updated_by_user_id=7, updated_at=T, handed_from_name=None, handed_at=None,
                           **{k: v for k, v in summary.items() if k != "state"})


def test_stored_flag_survives_reading_and_old_rows_without_it_read_by_time() -> None:
    """읽기 정규화(``crew_of``)가 표지를 지우지 않는다 · 표지가 없는 옛 칸(이 고침 전에 완료한 줄)은 지금처럼 시각으로 읽는다."""
    for flag in (True, False):
        stored = [{"uid": 7, "name": "박반장", "at": T_ISO, "done_at": T_ISO, "done_uid": 7, "done_name": "박반장", "once": flag}]
        read = mc.crew_of(_row(stored, "DONE"))
        assert read[0]["once"] is flag and mc.done_at_once(read) is flag and holder_rows(read)[0]["once"] is flag
    old = [{"uid": 7, "name": "박반장", "at": T_ISO, "done_at": T_ISO, "done_uid": 7, "done_name": "박반장"}]
    assert "once" not in mc.crew_of(_row(old, "DONE"))[0] and mc.done_at_once(mc.crew_of(_row(old, "DONE"))) is True
    later = [{**old[0], "done_at": "2026-11-28T01:00:09+00:00"}]
    assert mc.done_at_once(mc.crew_of(_row(later, "DONE"))) is False
    junk = [{**old[0], "once": "yes"}]  # 모르는 꼴은 표지로 치지 않는다(옛 칸처럼 읽음)
    assert "once" not in mc.crew_of(_row(junk, "DONE"))[0]

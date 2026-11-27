"""여러 명이 같이 작업 — 쓰기 API 시험(설계서 2026-11-25 multi-holder §5 · §7 · §11 M1).

``POST /api/production/part-marks`` 의 늦은 [작업 시작](Q16 넘김) · [같이 작업] · 모두 완료 · 본인 몫만 되돌리기 · 시작 취소 ·
반장의 남의 시작 취소 · 대신 완료 · 담당 바꾸기 고르기 · PC [완료 처리](``check``) · 검수 순서 · 공정 칸 · 남의 공장 · 보류를 본다.
SQLite 레인은 ``FOR UPDATE`` 를 무시하므로 '거의 같이'는 줄 선 차례(먼저 온 쓰기가 끝난 뒤 늦은 화면이 보내는 쓰기)로 본다 —
진짜 동시는 PG 레인 ``tests/postgres/test_production_part_marks_race_pg.py``. 이름은 모두 지어낸 값이다.

되돌리면 실패: 늦은 [작업 시작]을 409 로 거절 · 한 명 완료로 도면 완료 · 남의 완료 되돌리기 받기 · 완료 뒤 시작 취소 받기 ·
파트 계정의 남의 시작 취소 받기 · 대신 완료가 반장을 목록에 넣기 · 1/2 완료에서 검수 열기 · 알림 · '바뀐 것' 만들기.
대조군: 한 명만 작업하는 도면은 상태 · 완료 판정 · 공정 칸이 지금 그대로.
"""
from __future__ import annotations

import copy

from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified

from db import db_session, engine
from models import Notification, OrderEvent, ProductionPartMark, SecurityLog, User
from tests.domains.test_production_part_marks_api import ONE_WRITE_CAP
from tests.support.production_part_claim_seed import (
    BULK,
    HISTORY,
    code,
    current_runs,
    events,
    finish,
    fresh,
    login,
    make_order,
    make_user,
    mark,
    patch_sd,
    row,
    step,
)


def _names(oid: int, key: str, part: str = "cut") -> list[tuple[str, bool]]:
    saved = row(oid, key, part)
    return [(m["name"], m["done_at"] is not None) for m in (saved.holders or [])]


def _two(client, order, j: int = 0, part: str = "cut"):
    """이시영이 먼저 [작업 시작], 김재단이 늦게 [작업 시작] → 둘이 같이 작업. (이시영, 김재단, 늦은 응답)."""
    lee, kim = make_user("이시영", part=part), make_user("김재단", part=part)
    login(client, lee)
    assert mark(client, order, j, part, "take", "none").status_code == 200
    login(client, kim)
    late = mark(client, order, j, part, "take", "none")  # 같은 '미정' 화면을 보고 늦게 누름
    assert late.status_code == 200, late.get_json()
    return lee, kim, late


def _audits(oid: int) -> list[str]:
    db_session.expire_all()
    return [a.message for a in db_session.query(SecurityLog).filter_by(action="PRODUCTION_PART_MARKED", target_id=oid)
            .order_by(SecurityLog.id)]


def _lead():
    return make_user("박반장", lead=True)


# --------------------------------------------------------------------------- #
# Q16 — 거의 같이 [작업 시작] = 저절로 같이 작업
# --------------------------------------------------------------------------- #
def test_late_take_joins_with_notice_and_resend_is_same(client):
    order = make_order(2)
    lee, kim, late = _two(client, order)
    data = late.get_json()["data"]
    assert (data["joined_late"], data["notice"], data["changed"]) == (True, "이시영이 먼저 시작했어요.", True)
    assert [(h["name"], h["done"]) for h in data["mark"]["holders"]] == [("이시영", False), ("김재단", False)]
    assert (data["mark"]["holder_n"], data["mark"]["done_n"], data["mark"]["picked_by_name"]) == (2, 0, "이시영")
    assert _names(order.id, order.keys[0]) == [("이시영", False), ("김재단", False)]
    assert "재단 같이 작업 (먼저 시작: 이시영)" in _audits(order.id)[-1]
    payload = events(order.id, "PRODUCTION_PART_MARKED")[-1].payload
    assert (payload["action"], payload["joined_late"], [h["name"] for h in payload["holders_after"]]) == (
        "join", True, ["이시영", "김재단"])
    again = mark(client, order, 0, "cut", "take", "none")  # 같은 사람이 또 보냄 = 멱등
    assert again.status_code == 200 and again.get_json()["data"]["changed"] is False
    login(client, make_user("최재단", part="cut"))
    third = mark(client, order, 0, "cut", "take", "none").get_json()["data"]
    assert third["notice"] == "이시영 · 김재단이 먼저 시작했어요."


def test_late_take_on_finished_or_blocked_rows_is_refused_as_today(client):
    order = make_order(4)
    login(client, make_user("이시영", part="cut"))
    finish(client, order, 0, "cut")
    assert mark(client, order, 1, "cut", "basic", "none").status_code == 200
    login(client, make_user("김재단", part="cut"))
    done = mark(client, order, 0, "cut", "take", "none")
    assert (done.status_code, code(done), done.get_json()["error"]) == (409, "MARK_CONFLICT", "이시영이 먼저 완료했어요")
    basic = mark(client, order, 1, "cut", "take", "none")
    assert (basic.status_code, basic.get_json()["error"]) == (409, "이시영이 먼저 기본으로 했어요")
    login(client, make_user("박재단", part="cut"))
    assert mark(client, order, 2, "cut", "take", "none").status_code == 200
    patch_sd(order.id, hold={"active": True, "reason": "자재 기다림"})
    login(client, make_user("최재단", part="cut"))
    held = mark(client, order, 2, "cut", "take", "none")
    assert code(held) == "HOLD_ACTIVE" and _names(order.id, order.keys[2]) == [("박재단", False)]


def test_late_take_on_other_factory_or_unready_inspect_is_not_switched(client):
    order = make_order(2, extra={"drawing_factory": {"sheets": {}}})
    login(client, make_user("이시영", part="cut"))
    assert mark(client, order, 0, "cut", "take", "none").status_code == 200
    far = make_user("원재단", part="cut")
    db_session.query(User).filter_by(id=far.id).update({"production_factory": 2})
    db_session.commit()
    login(client, far)
    other = mark(client, order, 0, "cut", "take", "none")
    assert (other.status_code, code(other)) == (403, "OTHER_FACTORY")
    db_session.add(ProductionPartMark(order_id=order.id, drawing_key=order.keys[1], part="inspect", state="NEED",
                                      picked_by_name="윤검수", holders=None))  # 규칙 전 검수 시작(옛 줄)
    db_session.commit()
    login(client, make_user("강검수", part="inspect"))
    early = mark(client, order, 1, "inspect", "take", "none")
    assert code(early) == "INSPECT_NOT_READY"
    assert _names(order.id, order.keys[0]) == [("이시영", False)]


def test_late_join_on_waiting_order_starts_production(client):
    order = make_order(1, run=False)
    login(client, make_user("이시영", part="cut"))
    db_session.add(ProductionPartMark(order_id=order.id, drawing_key=order.keys[0], part="cut", state="NEED",
                                      picked_by_name="이시영", picked_by_user_id=None))
    db_session.commit()
    seeded = row(order.id, order.keys[0], "cut")
    db_session.query(ProductionPartMark).filter_by(id=seeded.id).update({"picked_by_user_id": make_user("옛재단").id})
    db_session.commit()
    login(client, make_user("김재단", part="cut"))
    late = mark(client, order, 0, "cut", "take", "none").get_json()["data"]
    assert late["joined_late"] is True and late["run_started"] is True and current_runs(order.id) == 1


def test_bulk_basic_skips_row_in_work_with_new_words(client):
    order = make_order(2)
    _two(client, order)
    data = client.post(BULK, json={"part": "cut", "seen": "none", "items": [
        {"order_id": order.id, "drawing_key": k} for k in order.keys]}).get_json()["data"]
    assert [(s["reason"], s["error"]) for s in data["skipped"]] == [("MARK_CONFLICT", "이시영 · 김재단이 먼저 시작했어요.")]
    assert [a["drawing_key"] for a in data["applied"]] == [order.keys[1]]


# --------------------------------------------------------------------------- #
# 완료 · 같이 작업(Q1 · Q2) · 되돌리기(Q3 · Q4) · 시작 취소(Q5 ~ Q7)
# --------------------------------------------------------------------------- #
def test_everyone_must_finish_and_half_done_can_still_be_joined(client):
    order = make_order(2)
    lee, kim, _ = _two(client, order)
    login(client, lee)
    half = mark(client, order, 0, "cut", "done", "need").get_json()["data"]
    assert (half["mark"]["state"], half["mark"]["done_n"], half["order_step"]) == ("need", 1, None)
    assert "재단 작업 필요 → 재단 1/2 완료" in _audits(order.id)[-1]
    login(client, make_user("박재단", part="cut"))
    joined = mark(client, order, 0, "cut", "join", "need", seen_me="none").get_json()["data"]  # 1/2 완료에도 들어옴(Q1)
    assert (joined["mark"]["holder_n"], joined["notice"]) == (3, None)
    for who in (kim,):
        login(client, who)
        assert mark(client, order, 0, "cut", "done", "need").status_code == 200
    assert row(order.id, order.keys[0], "cut").state == "NEED"  # 박재단이 아직
    assert step(order.id, "cut")["done"] is False


def test_join_after_all_done_is_refused(client):
    order = make_order(1)
    lee, kim, _ = _two(client, order)
    for who in (lee, kim):
        login(client, who)
        assert mark(client, order, 0, "cut", "done", "need").status_code == 200
    assert row(order.id, order.keys[0], "cut").state == "DONE"
    login(client, make_user("박재단", part="cut"))
    late = mark(client, order, 0, "cut", "join", "need")
    assert (late.status_code, code(late)) == (409, "JOIN_DONE")
    assert late.get_json()["error"] == "이미 완료된 도면이에요. 다시 해야 하면 완료한 사람이 [재단 완료 취소]를 먼저 눌러 주세요."


def test_undo_is_own_share_only_and_lead_can_undo_for_them(client):
    order = make_order(1)
    lee, kim, _ = _two(client, order)
    for who in (lee, kim):
        login(client, who)
        mark(client, order, 0, "cut", "done", "need")
    back = mark(client, order, 0, "cut", "undo", "done").get_json()["data"]  # 김재단 몫만(Q4)
    assert (back["mark"]["state"], back["mark"]["done_n"]) == ("need", 1)
    assert _names(order.id, order.keys[0]) == [("이시영", True), ("김재단", False)]
    login(client, make_user("박재단", part="cut"))
    other = mark(client, order, 0, "cut", "undo", "need")
    assert (other.status_code, code(other)) == (403, "UNDO_NOT_MINE")
    assert other.get_json()["error"] == "내가 완료한 것만 되돌릴 수 있어요. 이시영이 완료한 것은 이시영에게 말해 주세요."
    login(client, _lead())
    assert mark(client, order, 0, "cut", "undo", "need").status_code == 200  # 반장 대신 되돌리기(판결 3)
    assert _names(order.id, order.keys[0]) == [("이시영", False), ("김재단", False)]


def test_lead_undo_without_target_reverts_every_finished_share(client):
    """반장 · 관리자가 대상 없이 [되돌리기](PC [완료 취소]도 같은 길) = 두 사람 완료를 모두 되돌림(사장님 2026-11-25)."""
    order = make_order(1)
    lee, kim, _ = _two(client, order)
    for who in (lee, kim):
        login(client, who)
        mark(client, order, 0, "cut", "done", "need")
    assert row(order.id, order.keys[0], "cut").state == "DONE"
    login(client, _lead())
    back = mark(client, order, 0, "cut", "undo", "done").get_json()["data"]
    assert (back["changed"], back["mark"]["state"], back["mark"]["done_n"], back["mark"]["holder_n"]) == (True, "need", 0, 2)
    assert _names(order.id, order.keys[0]) == [("이시영", False), ("김재단", False)]  # 사람 목록은 그대로 · 둘 다 작업 중
    assert "재단 재단 완료 → 작업 필요 (대신 처리)" in _audits(order.id)[-1]


def test_release_rules_and_auto_complete_turns_step_on(client):
    order = make_order(1)
    lee, kim, _ = _two(client, order)
    login(client, lee)
    mark(client, order, 0, "cut", "done", "need")
    after_done = mark(client, order, 0, "cut", "release", "need")  # 완료 뒤 시작 취소(Q7)
    assert (after_done.status_code, code(after_done)) == (409, "RELEASE_AFTER_DONE")
    assert after_done.get_json()["error"] == "[재단 완료]를 누른 도면은 시작을 취소할 수 없어요. 먼저 [재단 완료 취소]를 눌러 주세요."
    login(client, kim)
    left = mark(client, order, 0, "cut", "release", "need").get_json()["data"]  # 남은 사람 모두 완료 = 저절로 완료(Q6)
    assert left["mark"]["state"] == "done" and left["order_step"]["done"] is True
    cut = step(order.id, "cut")
    assert (cut["done"], cut["by_name"]) == (True, "이시영")
    assert "재단 시작 취소 (김재단)" in _audits(order.id)[-1]


def test_remove_is_lead_only_and_names_both(client):
    order = make_order(1)
    lee, kim, _ = _two(client, order)
    login(client, make_user("박재단", part="cut"))
    denied = mark(client, order, 0, "cut", "remove", "need", target_user_id=kim.id)
    assert (denied.status_code, code(denied)) == (403, "REMOVE_FORBIDDEN")
    assert denied.get_json()["error"] == "다른 사람의 시작을 취소하는 것은 반장이나 관리자만 할 수 있어요."
    login(client, _lead())
    ask = mark(client, order, 0, "cut", "remove", "need")
    assert (ask.status_code, code(ask), ask.get_json()["error"]) == (400, "TARGET_REQUIRED", "누구의 시작을 취소할지 골라 주세요.")
    ok = mark(client, order, 0, "cut", "remove", "need", target_user_id=kim.id)
    assert ok.status_code == 200 and _names(order.id, order.keys[0]) == [("이시영", False)]
    assert "재단 시작 취소 (김재단, 박반장)" in _audits(order.id)[-1]
    gone = mark(client, order, 0, "cut", "remove", "need", target_user_id=kim.id, seen_me="none")
    assert gone.status_code == 200 and gone.get_json()["data"]["changed"] is False  # 같은 사람이 다시 보냄
    login(client, make_user("반장둘", lead=True))
    late = mark(client, order, 0, "cut", "remove", "need", target_user_id=kim.id)
    assert (code(late), late.get_json()["error"]) == ("TARGET_GONE", "그사이 김재단의 시작이 취소됐어요. [다시 받기]를 눌러 주세요.")


# --------------------------------------------------------------------------- #
# 담당 바꾸기 고르기(Q8 · 판결 4) · 인원(Q9) · 대신 완료(Q15) · 반장 같이 작업(Q22)
# --------------------------------------------------------------------------- #
def test_takeover_picks_one_and_refuses_done_or_ambiguous(client):
    order = make_order(1)
    lee, kim, _ = _two(client, order)
    login(client, make_user("박재단", part="cut"))
    ask = mark(client, order, 0, "cut", "takeover", "need", seen_by=lee.id)
    assert (ask.status_code, code(ask)) == (400, "TARGET_REQUIRED")
    login(client, lee)
    mark(client, order, 0, "cut", "done", "need")
    login(client, make_user("최재단", part="cut"))
    done = mark(client, order, 0, "cut", "takeover", "need", target_user_id=lee.id)
    assert (code(done), done.get_json()["error"]) == ("TARGET_DONE", "완료를 누른 사람은 바꿀 수 없어요.")
    swap = mark(client, order, 0, "cut", "takeover", "need", seen_by=lee.id)  # 아직인 사람이 하나 = 고르기 없이
    assert swap.status_code == 200 and _names(order.id, order.keys[0]) == [("이시영", True), ("최재단", False)]
    assert "재단 담당 바꿈 (김재단 → 최재단)" in _audits(order.id)[-1]
    assert row(order.id, order.keys[0], "cut").handed_from_name == "김재단"


def test_five_people_lead_and_admin_join_then_lead_finishes_the_rest(client):
    order = make_order(1)
    _two(client, order)
    for who in (make_user("박재단", part="cut"), make_user("최재단", part="cut"), _lead(),
                make_user("관리", team="CS", role="ADMIN")):
        login(client, who)
        assert mark(client, order, 0, "cut", "join", "need").status_code == 200  # 반장 · 관리자도 들어옴(Q22)
    assert len(_names(order.id, order.keys[0])) == 6  # 상한 없음(Q9)
    boss = make_user("반장셋", lead=True)
    login(client, boss)
    done = mark(client, order, 0, "cut", "done", "need").get_json()["data"]  # 대신 완료 = 남은 사람 몫을 한 번에(Q15)
    assert done["mark"]["state"] == "done" and done["mark"]["done_n"] == 6
    saved = row(order.id, order.keys[0], "cut")
    assert all(m["done_name"] == "반장셋" for m in saved.holders) and boss.id not in {m["uid"] for m in saved.holders}


def test_basic_row_cannot_be_joined(client):
    order = make_order(1)
    login(client, make_user("이시영", part="cut"))
    mark(client, order, 0, "cut", "basic", "none")
    login(client, make_user("김재단", part="cut"))
    joined = mark(client, order, 0, "cut", "join", "need")
    assert (joined.status_code, code(joined), joined.get_json()["error"]) == (409, "MARK_CONFLICT", "이시영이 먼저 기본으로 했어요")


# --------------------------------------------------------------------------- #
# 판결 1(같이 작업인데 빈 도면) · 판결 2(PC [완료 처리] = check)
# --------------------------------------------------------------------------- #
def test_join_on_emptied_row_is_plain_take_without_notice(client):
    order = make_order(1)
    lee = make_user("이시영", part="cut")
    login(client, lee)
    mark(client, order, 0, "cut", "take", "none")
    mark(client, order, 0, "cut", "release", "need")
    login(client, make_user("김재단", part="cut"))
    data = mark(client, order, 0, "cut", "join", "need").get_json()["data"]
    assert (data["changed"], data["joined_late"], data["notice"]) == (True, False, None)
    assert _names(order.id, order.keys[0]) == [("김재단", False)]


def test_pc_check_starts_and_finishes_or_finishes_for_others(client):
    order = make_order(3)
    boss = _lead()
    login(client, boss)
    empty = mark(client, order, 0, "cut", "check", "none").get_json()["data"]
    assert empty["mark"]["state"] == "done" and _names(order.id, order.keys[0]) == [("박반장", True)]
    login(client, make_user("이시영", part="cut"))
    mark(client, order, 1, "cut", "take", "none")
    forbidden = mark(client, order, 2, "cut", "check", "none")  # 파트 계정은 못 누름
    assert (forbidden.status_code, code(forbidden)) == (403, "PART_FORBIDDEN")
    login(client, boss)
    busy = mark(client, order, 1, "cut", "check", "none").get_json()["data"]  # 그사이 남이 시작한 줄 = 대신 완료
    assert (busy["proxied"], busy["mark"]["state"]) == (True, "done")
    assert _names(order.id, order.keys[1]) == [("이시영", True)]
    again = mark(client, order, 1, "cut", "check", "need").get_json()["data"]
    assert again["changed"] is False
    early = mark(client, order, 0, "inspect", "check", "none")
    assert code(early) == "INSPECT_NOT_READY"


# --------------------------------------------------------------------------- #
# 검수 순서 · 완료 물음 · 공정 칸
# --------------------------------------------------------------------------- #
def test_inspect_waits_for_all_cutters_and_order_ready_waits_for_all_inspectors(client):
    order = make_order(1)
    lee, kim, _ = _two(client, order)
    login(client, lee)
    mark(client, order, 0, "cut", "done", "need")
    login(client, make_user("관리", team="CS", role="ADMIN"))
    for part in ("edge", "assemble"):
        finish(client, order, 0, part)
    early = mark(client, order, 0, "inspect", "take", "none")
    assert code(early) == "INSPECT_NOT_READY"
    assert "재단(이시영 · 김재단 작업 중)" in early.get_json()["error"]
    login(client, kim)
    mark(client, order, 0, "cut", "done", "need")
    yun, kang = make_user("윤검수", part="inspect"), make_user("강검수", part="inspect")
    login(client, yun)
    assert mark(client, order, 0, "inspect", "take", "none").status_code == 200
    login(client, kang)
    assert mark(client, order, 0, "inspect", "take", "none").get_json()["data"]["joined_late"] is True
    first = mark(client, order, 0, "inspect", "done", "need").get_json()["data"]
    assert first["order_ready"] is None  # 검수 1/2 완료 = 안 묻는다
    login(client, yun)
    last = mark(client, order, 0, "inspect", "release", "need")  # 빠지면 남은 사람 모두 완료 = 저절로 완료(Q6)
    assert last.status_code == 200 and last.get_json()["data"]["order_ready"] == {"order_id": order.id}


def _inspect_two(client, order):
    """재단 · 엣지 · 조립 완료(관리) → 윤검수 · 강검수가 같이 검수(아직 아무도 완료 안 함). (관리, 강검수)."""
    admin = make_user("관리", team="CS", role="ADMIN")
    login(client, admin)
    for part in ("cut", "edge", "assemble"):
        finish(client, order, 0, part)
    yun, kang = make_user("윤검수", part="inspect"), make_user("강검수", part="inspect")
    for who in (yun, kang):
        login(client, who)
        assert mark(client, order, 0, "inspect", "take", "none").status_code == 200
    return admin, kang


def test_one_finished_inspector_blocks_earlier_part_undo(client):
    """한 명이라도 검수 완료를 눌렀으면("검수 1/2 완료") 재단 · 엣지 · 조립 되돌리기를 막는다(사장님 2026-11-25) — 본인 · 반장
    대신 모두. 검수 완료를 되돌려 0명이 되면 다시 된다."""
    order = make_order(1)
    admin, kang = _inspect_two(client, order)
    half = mark(client, order, 0, "inspect", "done", "need").get_json()["data"]  # 강검수만 완료
    assert (half["mark"]["state"], half["mark"]["done_n"]) == ("need", 1)
    login(client, admin)
    own = mark(client, order, 0, "cut", "undo", "done")
    assert (own.status_code, code(own)) == (409, "INSPECT_DONE_FIRST")
    assert own.get_json()["error"] == ("강검수가 이 장 검수를 완료했어요. 재단 완료를 취소하려면 강검수에게 검수 완료부터 "
                                       "취소해 달라고 해 주세요.")
    login(client, _lead())
    assert code(mark(client, order, 0, "edge", "undo", "done")) == "INSPECT_DONE_FIRST"  # 반장 대신 되돌리기도
    login(client, kang)
    assert mark(client, order, 0, "inspect", "undo", "need", seen_me="done").status_code == 200  # 검수 완료 0명
    login(client, admin)
    assert mark(client, order, 0, "cut", "undo", "done").status_code == 200  # 다시 된다
    assert row(order.id, order.keys[0], "cut").state == "NEED"


def test_inspect_started_without_any_done_allows_earlier_part_undo(client):
    """음성 대조군 — 검수를 시작만 하고 아무도 완료를 안 누른 도면은 앞 파트 되돌리기가 된다."""
    order = make_order(1)
    admin, _kang = _inspect_two(client, order)
    login(client, admin)
    assert mark(client, order, 0, "assemble", "undo", "done").status_code == 200
    assert row(order.id, order.keys[0], "assemble").state == "NEED"


def test_step_cell_stays_off_until_everyone_finishes(client):
    order = make_order(1)
    lee, kim, _ = _two(client, order)
    login(client, lee)
    assert mark(client, order, 0, "cut", "done", "need").get_json()["data"]["order_step"] is None
    assert step(order.id, "cut")["done"] is False
    login(client, kim)
    data = mark(client, order, 0, "cut", "done", "need").get_json()["data"]
    assert data["order_step"]["done"] is True and step(order.id, "cut")["by_name"] == "김재단"


# --------------------------------------------------------------------------- #
# 남의 공장 · 보류 · 알림 없음(Q19) · 바뀐 기록 · 쓰기 쿼리 수
# --------------------------------------------------------------------------- #
def test_other_factory_and_hold_rules(client):
    order = make_order(2)
    lee, kim, _ = _two(client, order)
    sheet = order.keys[0].replace("/d0.png", "-s0")
    live = fresh(order.id)
    sd = copy.deepcopy(live.structured_data)
    sd["drawing_factory"] = {"sheets": {sheet: 2}}  # 같이 작업한 뒤 장이 2공장으로 옮겨짐
    live.structured_data = sd
    flag_modified(live, "structured_data")
    db_session.commit()
    login(client, make_user("박재단", part="cut"))
    assert code(mark(client, order, 0, "cut", "join", "need")) == "OTHER_FACTORY"
    login(client, kim)
    assert mark(client, order, 0, "cut", "release", "need").status_code == 200  # 내가 작업하는 남의 공장 장 = 됨
    login(client, make_user("최재단", part="cut"))
    mark(client, order, 1, "cut", "take", "none")
    patch_sd(order.id, hold={"active": True, "reason": "자재 기다림"})
    login(client, make_user("정재단", part="cut"))
    assert code(mark(client, order, 1, "cut", "join", "need")) == "HOLD_ACTIVE"
    login(client, _lead())
    assert mark(client, order, 1, "cut", "remove", "need").status_code == 200  # 보류 중에도 남의 시작 취소는 됨


def test_no_alerts_only_history_rows_for_join_and_remove(client):
    order = make_order(1)
    before = db_session.query(Notification).count()
    lee, kim, _ = _two(client, order)
    login(client, _lead())
    mark(client, order, 0, "cut", "remove", "need", target_user_id=kim.id)
    db_session.expire_all()
    assert db_session.query(Notification).count() == before  # 알리지 않고 기록만(Q19)
    kinds = {e.event_type for e in db_session.query(OrderEvent).filter_by(order_id=order.id)}
    assert kinds == {"PRODUCTION_PART_MARKED"}
    items = client.get(HISTORY, query_string={"order_id": order.id, "part": "cut"}).get_json()["data"]["items"]
    assert [(i["kind"], i["by_name"], i["joined_late"], i["target_name"]) for i in items] == [
        ("take", "이시영", False, None), ("join", "김재단", True, None), ("remove", "박반장", False, "김재단")]


def test_switched_join_stays_under_the_one_write_cap(client):
    order = make_order(2)
    login(client, make_user("이시영", part="cut"))
    mark(client, order, 0, "cut", "take", "none")
    login(client, make_user("김재단", part="cut"))
    mark(client, order, 1, "cut", "take", "none")  # warmup
    seen = {"n": 0}

    def _before(*_args):
        seen["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        resp = mark(client, order, 0, "cut", "take", "none")
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    assert resp.get_json()["data"]["joined_late"] is True and seen["n"] <= ONE_WRITE_CAP, seen["n"]
    assert seen["n"] == 7, seen["n"]  # 실측(SQLite 레인): 지금 [작업 시작]과 같다 — 한 장 쓰기 6 + 회차 찾기 1(넘김은 같은 줄)

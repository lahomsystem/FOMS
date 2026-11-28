"""담당 바꾸기 — 누구에게 줄지 고르기(설계서 2026-11-28 흐름 셋 §1 · §4-3 약속 1 · 2 · 3).

사장님 2026-11-28: "누구에게 줄지 고르고" · 남에게 줄 수 있는 사람 = "반장 · 관리자만". 반장 · 관리자의 [담당 바꾸기 ›]는 묻지 않고
누른 사람이 담당이 되던 것을 "누구에게 줄까요?" 창으로 바꿨다. 쓰기 ``takeover`` 에 받는 사람 칸 ``to_user_id`` 가 생기고(안 보내면 누른
사람 — 옛 화면 그대로), 응답이 ``gave`` · ``holders_before`` 를 싣고, 쓰기 뒤에 알람 거는 줄 둘이 붙는다(몸은 다른 일꾼).

되돌리면 실패: 받는 사람 칸을 안 읽기(반장이 담당이 됨) · 파트 계정이 남에게 주기를 받기 · 꺼진 계정 · 다른 파트 · 다른 공장 계정에게
주기 · 이미 든 사람에게 또 주기 · 응답에서 ``gave`` · ``holders_before`` 빼기 · 되감은 쓰기에서 알람 보내기 · 고르기 창이 '나'를 미리
고르거나 바로 실행하기(화면 쪽은 ``test_production_give_holder_screen_1128.py``). 대조군: 받는 사람을 안 보낸 담당 바꾸기는 응답 · 줄 ·
감사 글 · 쿼리 수가 지금과 같다.
이름은 모두 지어낸 값이다(박반장 · 김재단 · 오재단 …).
"""
from __future__ import annotations

import datetime

from sqlalchemy import event

from db import db_session, engine
from foms.services.production import mark_crew as mc
from foms.services.production.part_mark_decide import decide_mark
from foms.services.production.part_mark_rules import MarkSnapshot
from models import ProductionPartMark, SecurityLog, User
from tests.support.production_part_claim_seed import HISTORY, code, events, login, make_order, make_user, mark, patch_sd, row

RECEIVERS = "/api/production/part-marks/receivers"
NOW = datetime.datetime(2026, 11, 28, 5, 20)
KIM, OH, LEAD = 11, 12, 99


def _snap(*members: dict, updated_by: int | None = None) -> MarkSnapshot:
    crew = tuple(members)
    return MarkSnapshot(state="NEED", picked_by_user_id=crew[0]["uid"] if crew else None,
                        picked_by_name=crew[0]["name"] if crew else None, updated_by_user_id=updated_by, crew=crew)


def _held(uid: int, name: str) -> dict:
    return mc.member(uid, name, "2026-11-27T23:10:00+00:00")


def _done(uid: int, name: str) -> dict:
    return mc.member(uid, name, "2026-11-27T23:10:00+00:00", done_at="2026-11-28T01:00:00+00:00", done_uid=uid, done_name=name)


def _give(snap: MarkSnapshot, **kw):
    base = dict(action="takeover", seen="need", actor_id=LEAD, admin=True, actor_name="박반장", now=NOW, label="재단")
    return decide_mark(snap, **{**base, **kw})


def _names(decision) -> list[tuple[str, bool]]:
    return [(m["name"], mc.is_done(m)) for m in decision.crew]


def _audit(oid: int) -> str:
    db_session.expire_all()
    return (db_session.query(SecurityLog).filter_by(action="PRODUCTION_PART_MARKED", target_id=oid)
            .order_by(SecurityLog.id.desc()).first().message)


def _crew(oid: int, key: str, part: str = "cut") -> list[tuple[str, bool]]:
    return [(m["name"], m["done_at"] is not None) for m in (row(oid, key, part).holders or [])]


def _count(fn):
    seen = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        seen["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        return fn(), seen["n"]
    finally:
        event.remove(engine, "before_cursor_execute", _before)


def _started(client, part: str = "cut", n: int = 2):
    """김재단이 [재단 시작]한 도면 — (주문, 김재단, 오재단, 박반장)."""
    order = make_order(n)
    kim, oh, lead = make_user("김재단", part=part), make_user("오재단", part=part), make_user("박반장", lead=True)
    login(client, kim)
    assert mark(client, order, 0, part, "take", "none").status_code == 200
    return order, kim, oh, lead


# --------------------------------------------------------------------------- #
# 순수 판정
# --------------------------------------------------------------------------- #
def test_decide_gives_the_seat_to_the_receiver_and_keeps_everyone_else():
    one = _give(_snap(_held(KIM, "김재단")), to_uid=OH, to_name="오재단")
    assert (one.kind, one.target, _names(one)) == ("apply", "NEED", [("오재단", False)])
    assert (one.target_uid, one.target_name, one.to_uid, one.to_name) == (KIM, "김재단", OH, "오재단")
    assert one.crew[0]["at"] == mc.to_iso(NOW)  # 시작한 때 = 지금
    seat = _give(_snap(_held(KIM, "김재단"), _done(OH, "오재단")), target_uid=KIM, to_uid=13, to_name="최재단")
    assert _names(seat) == [("최재단", False), ("오재단", True)]  # 자리 · 남은 사람 그대로
    empty = _give(_snap(), to_uid=OH, to_name="오재단")  # 사람 없는 옛 줄
    assert (_names(empty), empty.target_uid, empty.target_name, empty.to_uid) == ([("오재단", False)], None, "", OH)


def test_decide_without_receiver_is_todays_takeover():
    snap = _snap(_held(KIM, "김재단"))
    plain = _give(snap)
    same = _give(snap, to_uid=LEAD, to_name="박반장")  # 받는 사람 = 누른 사람도 같은 길
    for decision in (plain, same):
        assert (decision.kind, _names(decision), decision.to_uid, decision.to_name) == ("apply", [("박반장", False)], LEAD, "박반장")
    other = decide_mark(snap, action="release", seen="need", actor_id=LEAD, admin=True, target_uid=KIM, to_uid=OH, to_name="오재단")
    assert (other.action, other.to_uid, other.crew) == ("release", None, ())  # 다른 누름은 받는 사람 칸을 안 읽는다


def test_decide_refuses_done_seat_and_receiver_already_in():
    crew = (_held(KIM, "김재단"), _done(OH, "오재단"))
    done_seat = _give(_snap(*crew), target_uid=OH, to_uid=13, to_name="최재단")
    assert (done_seat.kind, done_seat.code) == ("refuse", "TARGET_DONE")
    inside = _give(_snap(*crew), target_uid=KIM, to_uid=OH, to_name="오재단")
    assert (inside.kind, inside.code, inside.status, inside.message) == (
        "refuse", "RECEIVER_ALREADY_IN", 409, "오재단은 이미 이 도면을 작업 중이에요.")
    held_in = _give(_snap(_held(KIM, "김재단"), _held(13, "최재단")), target_uid=KIM, to_uid=13, to_name="최재단")
    assert (held_in.code, held_in.message) == ("RECEIVER_ALREADY_IN", "최재단은 이미 이 도면을 작업 중이에요.")
    two = _give(_snap(_held(KIM, "김재단"), _held(13, "최재단")), to_uid=OH, to_name="오재단")
    assert (two.code, two.status) == ("TARGET_REQUIRED", 400)  # 자리를 안 골랐다(지금 규칙 그대로)


def test_decide_same_request_twice_is_no_change():
    after = _snap(_held(OH, "오재단"), updated_by=LEAD)  # 박반장이 김재단 자리를 오재단에게 준 뒤
    again = _give(after, target_uid=KIM, to_uid=OH, to_name="오재단")
    assert (again.kind, again.target) == ("same", "NEED")
    assert _give(after, to_uid=OH, to_name="오재단").kind == "same"  # 자리를 안 실은 요청(한 명짜리 줄)도
    by_other = _give(_snap(_held(OH, "오재단"), updated_by=KIM), target_uid=KIM, to_uid=OH, to_name="오재단")
    assert by_other.code == "RECEIVER_ALREADY_IN"  # 내가 만든 결과가 아니면 멱등이 아니다
    seat_still = _give(_snap(_held(KIM, "김재단"), _held(OH, "오재단"), updated_by=LEAD), target_uid=KIM, to_uid=OH, to_name="오재단")
    assert seat_still.code == "RECEIVER_ALREADY_IN"  # 자리 주인이 아직 있다 = 같은 요청의 되풀이가 아니다


# --------------------------------------------------------------------------- #
# 쓰기 API
# --------------------------------------------------------------------------- #
def test_lead_gives_to_another_person(client):
    order, kim, oh, lead = _started(client)
    login(client, lead)
    resp = mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id, seen_me="none", target_user_id=kim.id, to_user_id=oh.id)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["changed"] is True and data["gave"] == {
        "order_id": order.id, "drawing_key": order.keys[0], "part": "cut", "by": {"user_id": lead.id, "name": "박반장"},
        "from": {"user_id": kim.id, "name": "김재단"}, "to": {"user_id": oh.id, "name": "오재단"}, "self": False}
    assert data["holders_before"] == [{"user_id": kim.id, "name": "김재단", "done": False}]
    assert [(h["user_id"], h["name"]) for h in data["mark"]["holders"]] == [(oh.id, "오재단")]
    saved = row(order.id, order.keys[0], "cut")
    assert (saved.state, saved.picked_by_user_id, saved.handed_from_name, saved.updated_by_user_id) == ("NEED", oh.id, "김재단", lead.id)
    assert saved.handed_at is not None and _crew(order.id, order.keys[0]) == [("오재단", False)]
    payload = events(order.id, "PRODUCTION_PART_MARKED")[-1].payload
    assert (payload["action"], payload["by_name"], payload["from_name"], payload["to_user_id"], payload["to_name"]) == (
        "takeover", "박반장", "김재단", oh.id, "오재단")
    assert _audit(order.id).endswith("재단 담당 바꿈 (김재단 → 오재단, 박반장)")
    item = [i for i in client.get(f"{HISTORY}?order_id={order.id}").get_json()["data"]["items"] if i["kind"] == "takeover"][-1]
    assert (item["by_name"], item["from_name"], item["to_name"]) == ("박반장", "김재단", "오재단")
    again = mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id, seen_me="none", target_user_id=kim.id, to_user_id=oh.id)
    assert again.status_code == 200 and again.get_json()["data"]["changed"] is False  # 연결이 얼어 두 번
    assert "gave" not in again.get_json()["data"] and "holders_before" not in again.get_json()["data"]
    assert len(events(order.id, "PRODUCTION_PART_MARKED")) == 2  # 시작 · 담당 바꾸기 — 다시 보낸 것은 0


def test_lead_gives_to_self_is_todays_takeover(client):
    order, kim, _oh, lead = _started(client)
    login(client, lead)
    mine = mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id, to_user_id=lead.id).get_json()["data"]
    assert (mine["gave"]["self"], mine["gave"]["to"], mine["gave"]["from"]["name"]) == (True, {"user_id": lead.id, "name": "박반장"}, "김재단")
    assert _crew(order.id, order.keys[0]) == [("박반장", False)]
    assert _audit(order.id).endswith("재단 담당 바꿈 (김재단 → 박반장)")  # 감사 글은 지금 꼴
    login(client, kim)
    assert mark(client, order, 1, "cut", "take", "none").status_code == 200
    login(client, lead)
    plain = mark(client, order, 1, "cut", "takeover", "need", seen_by=kim.id).get_json()["data"]  # 받는 사람 칸 없는 옛 화면
    assert plain["gave"]["self"] is True and plain["gave"]["to"]["user_id"] == lead.id
    payload = events(order.id, "PRODUCTION_PART_MARKED")[-1].payload
    assert (payload["to_user_id"], payload["to_name"], payload["from_name"]) == (lead.id, "박반장", "김재단")


def test_part_account_cannot_give_but_still_takes_over(client):
    order, kim, oh, _lead = _started(client)
    choi = make_user("최재단", part="cut")
    login(client, choi)
    refused = mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id, to_user_id=oh.id)
    assert (refused.status_code, code(refused), refused.get_json()["error"]) == (
        403, "GIVE_FORBIDDEN", "다른 사람에게 주는 것은 반장이나 관리자만 할 수 있어요.")
    assert _crew(order.id, order.keys[0]) == [("김재단", False)]
    bad = mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id, to_user_id="오재단")
    assert (bad.status_code, code(bad), bad.get_json()["error"]) == (400, "BAD_REQUEST", "받는 사람 값이 올바르지 않아요.")
    own = mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id)  # 대조군 — 내가 가져오기는 지금 그대로
    assert own.status_code == 200 and own.get_json()["data"]["gave"]["self"] is True
    assert _crew(order.id, order.keys[0]) == [("최재단", False)]


def test_receiver_must_be_able_to_start_that_sheet(client):
    order, kim, oh, lead = _started(client)
    off, edge, far = make_user("꺼진재단", part="cut"), make_user("한엣지", part="edge"), make_user("원재단", part="cut")
    viewer, cs = make_user("보기재단", part="cut", role="VIEWER"), make_user("상담", team="CS")
    db_session.query(User).filter_by(id=off.id).update({"is_active": False})
    db_session.query(User).filter_by(id=far.id).update({"production_factory": 2})
    db_session.commit()
    login(client, lead)
    for who in (off, edge, far, viewer, cs):
        resp = mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id, to_user_id=who.id)
        assert (resp.status_code, code(resp)) == (409, "RECEIVER_NOT_ALLOWED"), who.name
        assert resp.get_json()["data"]["mark"]["picked_by_name"] == "김재단"  # 서버의 지금 표시를 싣는다
    assert resp.get_json()["error"] == "상담은 지금 이 도면을 받을 수 없어요. [다시 받기]를 눌러 주세요."
    gone = mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id, to_user_id=987654)
    assert (code(gone), gone.get_json()["error"]) == (
        "RECEIVER_NOT_ALLOWED", "그 사람은 지금 이 도면을 받을 수 없어요. [다시 받기]를 눌러 주세요.")
    assert _crew(order.id, order.keys[0]) == [("김재단", False)] and len(events(order.id, "PRODUCTION_PART_MARKED")) == 1
    ok = mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id, to_user_id=oh.id)  # 대조군
    assert ok.status_code == 200 and _crew(order.id, order.keys[0]) == [("오재단", False)]


def test_receiver_already_in_and_seats_with_many_people(client):
    order, kim, oh, lead = _started(client)
    login(client, oh)
    assert mark(client, order, 0, "cut", "join", "need").status_code == 200  # 김재단 · 오재단 같이 작업
    choi = make_user("최재단", part="cut")
    login(client, lead)
    inside = mark(client, order, 0, "cut", "takeover", "need", target_user_id=kim.id, to_user_id=oh.id)
    assert (inside.status_code, code(inside), inside.get_json()["error"]) == (
        409, "RECEIVER_ALREADY_IN", "오재단은 이미 이 도면을 작업 중이에요.")
    ask = mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id, to_user_id=choi.id)
    assert (ask.status_code, code(ask)) == (400, "TARGET_REQUIRED")  # 누구 자리인지 안 골랐다
    login(client, oh)
    assert mark(client, order, 0, "cut", "done", "need").status_code == 200  # 오재단 자기 몫 완료
    login(client, lead)
    done_seat = mark(client, order, 0, "cut", "takeover", "need", target_user_id=oh.id, to_user_id=choi.id)
    assert code(done_seat) == "TARGET_DONE"
    seat = mark(client, order, 0, "cut", "takeover", "need", target_user_id=kim.id, to_user_id=choi.id).get_json()["data"]
    assert _crew(order.id, order.keys[0]) == [("최재단", False), ("오재단", True)]  # 자리 · 남은 사람 그대로
    assert seat["holders_before"] == [{"user_id": kim.id, "name": "김재단", "done": False}, {"user_id": oh.id, "name": "오재단", "done": True}]
    assert (seat["gave"]["from"]["name"], seat["gave"]["to"]["name"], row(order.id, order.keys[0], "cut").handed_from_name) == (
        "김재단", "최재단", "김재단")


def test_give_on_a_row_without_people_and_first_card_start(client):
    order = make_order(1, run=False)
    oh, lead = make_user("오재단", part="cut"), make_user("박반장", lead=True)
    db_session.add(ProductionPartMark(order_id=order.id, drawing_key=order.keys[0], part="cut", state="NEED"))  # 사람 없는 옛 줄
    db_session.commit()
    login(client, lead)
    data = mark(client, order, 0, "cut", "takeover", "need", seen_by=None, to_user_id=oh.id).get_json()["data"]
    assert (data["gave"]["from"], data["gave"]["to"]["name"], data["holders_before"], data["run_started"]) == (None, "오재단", [], True)
    saved = row(order.id, order.keys[0], "cut")
    assert (saved.picked_by_user_id, saved.handed_from_name) == (oh.id, None)


def test_give_keeps_todays_gates(client):
    order, kim, oh, lead = _started(client)
    patch_sd(order.id, hold={"active": True, "reason": "자재 기다림"})
    login(client, lead)
    assert code(mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id, to_user_id=oh.id)) == "HOLD_ACTIVE"
    patch_sd(order.id, hold={"active": False})
    stale = mark(client, order, 0, "cut", "takeover", "none", seen_by=None, to_user_id=oh.id)
    assert (stale.status_code, code(stale)) == (409, "MARK_CONFLICT")  # 미정으로 본 낡은 화면(그사이 김재단 작업 중) — 미정 주기는 11-28 부터 있다
    far_lead = make_user("이반장", lead=True)
    db_session.query(User).filter_by(id=far_lead.id).update({"production_factory": 2})
    db_session.commit()
    login(client, far_lead)
    assert code(mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id, to_user_id=oh.id)) == "OTHER_FACTORY"
    insp, insp2 = make_user("한검수", part="inspect"), make_user("강검수", part="inspect")
    db_session.add(ProductionPartMark(order_id=order.id, drawing_key=order.keys[1], part="inspect", state="NEED",
                                      picked_by_name="한검수", picked_by_user_id=insp.id))  # 규칙 전 검수 시작(옛 줄)
    db_session.commit()
    login(client, lead)
    early = mark(client, order, 1, "inspect", "takeover", "need", seen_by=insp.id, to_user_id=insp2.id)
    assert code(early) == "INSPECT_NOT_READY"
    assert _crew(order.id, order.keys[0]) == [("김재단", False)]


def test_give_on_a_revising_drawing_is_blocked(client, monkeypatch):
    monkeypatch.setattr("foms.services.notifications.push_sender.enqueue_push_for_notification", lambda *a, **k: None)
    monkeypatch.setattr("foms.api.drawing.erp_orders_revision.emit_erp_notification_to_users", lambda *a, **k: None)
    order = make_order(2, extra={"drawing_status": "CONFIRMED"})
    kim, oh, lead = make_user("김재단", part="cut"), make_user("오재단", part="cut"), make_user("박반장", lead=True)
    login(client, kim)
    assert mark(client, order, 0, "cut", "take", "none").status_code == 200
    login(client, make_user("가짜관리", team="CS", role="ADMIN"))
    asked = client.post(f"/api/orders/{order.id}/request-revision", json={"note": "측판 길이", "target_drawing_keys": [order.keys[0]]})
    assert asked.status_code == 200, asked.get_json()
    login(client, lead)
    assert code(mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id, to_user_id=oh.id)) == "DRAWING_REVISING"
    assert _crew(order.id, order.keys[0]) == [("김재단", False)]


def test_give_query_counts(client):
    order, kim, oh, lead = _started(client, n=3)
    login(client, kim)
    assert mark(client, order, 1, "cut", "take", "none").status_code == 200
    login(client, lead)
    client.get(f"{HISTORY}?order_id={order.id}")  # warmup
    to_me, n_me = _count(lambda: mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id))
    to_other, n_other = _count(lambda: mark(client, order, 1, "cut", "takeover", "need", seen_by=kim.id, to_user_id=oh.id))
    assert to_me.status_code == 200 and to_other.status_code == 200
    assert n_other - n_me == 1, (n_me, n_other)  # 남에게 줄 때만 받는 사람 한 줄 읽기


# --------------------------------------------------------------------------- #
# 알람 거는 줄 둘(약속 3) — 몸은 빈 틀이라 부르는 때 · 재료만 본다
# --------------------------------------------------------------------------- #
def test_alarm_hooks_run_around_the_commit_and_cost_no_query(client, monkeypatch):
    from foms.services.production import floor_alarm

    order, kim, oh, lead = _started(client)
    calls: list[tuple] = []
    real_note, real_flush = floor_alarm.note_mark, floor_alarm.flush

    def _commit(conn):
        calls.append(("commit",))

    def note_mark(db, actor, req, data):
        (_, n) = _count(lambda: real_note(db, actor, req, data))
        calls.append(("note", actor.id, req.action, req.to_uid, bool(data.get("gave")), data.get("holders_before"), n))

    def flush(db):
        (_, n) = _count(lambda: real_flush(db))
        calls.append(("flush", n))

    monkeypatch.setattr(floor_alarm, "note_mark", note_mark)
    monkeypatch.setattr(floor_alarm, "flush", flush)
    login(client, lead)
    event.listen(engine, "commit", _commit)
    try:
        assert mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id, to_user_id=oh.id).status_code == 200
        kinds = [c[0] for c in calls]
        assert kinds[0] == "note" and kinds[-1] == "flush" and "commit" in kinds[1:-1], calls  # 적기 → 커밋 → 보내기
        assert calls[0] == ("note", lead.id, "takeover", oh.id, True, [{"user_id": kim.id, "name": "김재단", "done": False}], 0)
        assert calls[-1] == ("flush", 0)  # 스위치가 꺼진 빈 틀 = 쿼리 0
        calls.clear()
        refused = mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id, to_user_id=oh.id + 9999)
        assert refused.status_code == 409 and [c[0] for c in calls if c[0] != "commit"] == []  # 되감은 쓰기에는 닿지 않는다
        login(client, make_user("최재단", part="cut"))
        calls.clear()
        assert mark(client, order, 1, "cut", "basic", "none").status_code == 200  # 다른 누름도 같은 두 줄을 탄다
        assert [c[0] for c in calls] == ["note", "commit", "flush"] and calls[0][2:5] == ("basic", None, False)
    finally:
        event.remove(engine, "commit", _commit)


# --------------------------------------------------------------------------- #
# 받을 사람 목록 API
# --------------------------------------------------------------------------- #
def _receivers(client, order, j: int = 0, part: str = "cut", **extra):
    query = {"order_id": order.id, "drawing_key": order.keys[j], "part": part, **extra}
    return client.get(RECEIVERS, query_string=query)


def test_receivers_lists_same_part_same_factory_live_accounts_with_me_first(client):
    order, kim, oh, lead = _started(client)
    ga, off, edge = make_user("가재단", part="cut"), make_user("꺼진재단", part="cut"), make_user("한엣지", part="edge")
    far, viewer, lead_cut = make_user("원재단", part="cut"), make_user("보기재단", part="cut", role="VIEWER"), make_user("조반장", part="cut", lead=True)
    make_user("관리", team="CS", role="ADMIN")
    make_user("영업재단", part="cut", team="SALES")  # 생산팀이 아니면 파트 칸이 남아 있어도 못 받는다
    db_session.query(User).filter_by(id=off.id).update({"is_active": False})
    db_session.query(User).filter_by(id=far.id).update({"production_factory": 2})
    db_session.commit()
    login(client, lead)
    resp = _receivers(client, order)
    assert resp.status_code == 200, resp.get_json()
    people = resp.get_json()["data"]["people"]
    assert [(p["user_id"], p["name"], p["me"]) for p in people] == [
        (lead.id, "박반장", True), (ga.id, "가재단", False), (oh.id, "오재단", False), (lead_cut.id, "조반장", False)]
    assert [p["line"] for p in people] == ["담당 김재단 → 담당 박반장", "담당 김재단 → 담당 가재단", "담당 김재단 → 담당 오재단",
                                           "담당 김재단 → 담당 조반장"]
    assert resp.headers["Cache-Control"] == "private, no-store"
    for who in people[1:]:  # 목록에 있는 사람은 쓰기도 받는다(같은 판정)
        assert who["user_id"] not in (kim.id, off.id, edge.id, far.id, viewer.id)
    given = mark(client, order, 0, "cut", "takeover", "need", seen_by=kim.id, to_user_id=people[1]["user_id"])
    assert given.status_code == 200 and _crew(order.id, order.keys[0]) == [("가재단", False)]


def test_receivers_drops_people_already_in_and_marks_same_names(client):
    order, kim, oh, lead = _started(client)
    twin = make_user("오재단", part="cut")
    login(client, lead)
    assert mark(client, order, 0, "cut", "join", "need").status_code == 200  # 박반장도 같이 작업 — 이미 든 사람
    people = _receivers(client, order, target_user_id=kim.id).get_json()["data"]["people"]
    assert [(p["user_id"], p["name"], p["me"]) for p in people] == [
        (oh.id, f"오재단 ({oh.username})", False), (twin.id, f"오재단 ({twin.username})", False)]  # '나'도 이미 들었으면 빠진다
    assert people[0]["line"] == "담당 김재단 · 박반장 → 담당 오재단 · 박반장"  # 고른 자리만 바뀐다(이름은 아이디 없이)
    empty = make_order(1)
    alone = _receivers(client, empty).get_json()["data"]["people"]  # 표시 줄이 없는 도면 — 목록은 그대로 나온다
    assert alone[0]["me"] is True and alone[0]["line"] == "담당 미정 → 담당 박반장"


def test_receivers_gates_and_query_count(client):
    order, kim, oh, lead = _started(client)
    login(client, oh)
    part_account = _receivers(client, order)
    assert (part_account.status_code, code(part_account)) == (403, "GIVE_FORBIDDEN")
    assert code(_receivers(client, order, part="edge")) == "PART_FORBIDDEN"
    login(client, make_user("상담", team="CS"))
    assert code(_receivers(client, order)) == "PART_REQUIRED"
    far_lead = make_user("이반장", lead=True)
    db_session.query(User).filter_by(id=far_lead.id).update({"production_factory": 2})
    db_session.commit()
    login(client, far_lead)
    assert (_receivers(client, order).status_code, code(_receivers(client, order))) == (403, "OTHER_FACTORY")
    login(client, lead)
    assert code(client.get(RECEIVERS, query_string={"order_id": "x", "drawing_key": order.keys[0], "part": "cut"})) == "BAD_REQUEST"
    assert code(client.get(RECEIVERS, query_string={"order_id": order.id, "drawing_key": "없는/도면.png", "part": "cut"})) == "DRAWING_NOT_CURRENT"
    assert client.get(RECEIVERS, query_string={"order_id": 987654, "drawing_key": "k", "part": "cut"}).status_code == 404
    _receivers(client, order)  # warmup
    few, n_few = _count(lambda: _receivers(client, order))
    for j in range(8):
        make_user(f"새재단{j}", part="cut")
    login(client, lead)
    many, n_many = _count(lambda: _receivers(client, order))
    assert len(many.get_json()["data"]["people"]) == len(few.get_json()["data"]["people"]) + 8
    assert n_few == n_many == 3, (n_few, n_many)  # 로그인 사용자 읽기 1 + 주문 ⟕ 표시 줄 1 + 켜진 직원 1 — 사람 수와 무관
    with client.session_transaction() as sess:
        sess.clear()
    assert _receivers(client, order).status_code in (401, 302)

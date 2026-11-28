"""생산 현장 알람 서버 — 스위치 · 받는 사람 문 · 담당 변경 글 · 60초 합치기 · 다시 받기 API · 실패해도 본 쓰기는 남는다.

설계서 ``docs/specs/2026-11-28-production-floor-alarm_SPEC.md`` §2-3 · §4 · §6-2 · §7 · '사장님 답 2차'. 표시 쓰기 API(다른 일꾼 몫)는 열지 않고,
약속 1 · 2 모양(``gave`` · ``holders_before``)을 직접 넣어 알람 모듈을 부른다. 시각은 늘 넣어 준다(준비물 ``switch_on``).

되돌리면 실패: 스위치 꺼짐에 줄 · 쿼리 · 본인에게 보냄 · 꺼진 계정/협력사/영업/파트도 반장도 아닌 생산팀에게 보냄 · 관리자에게 멈춤 ·
받은 사람 글의 이/가 · 원래 담당 글의 으로/로 · 가져간 때 글 · 합치기 없이 줄 셋 · 누른 뒤에도 합침 · 남의 알람이 다시 받기에 실림 ·
[확인] 뒤에도 실림 · 띠 12시간/긴급 72시간 경계 · 알람 실패가 본 쓰기를 되감음 · 되감은 쓰기의 알람이 나감.
"""
from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.api.production.alarms import pending_for
from foms.services.context_processors import inject_foms_flags
from foms.services.production import floor_alarm
from foms.services.production import floor_alarm_rules as rules
from foms.services.production import floor_alarm_text as T
from foms.services.production.floor_alarm_reads import can_receive
from models import Order, PartnerOrg, User
from tests.support.production_floor_alarm_seed import (
    NOW,
    SWITCH,
    ack,
    alarm_order,
    alarms,
    capture,
    count_queries,
    gave,
    give,
    kinds,
    press,
    state_of,
    switch_on,
    who,
)
from tests.support.production_part_claim_seed import login, make_user, mark

PENDING = "/api/production/alarms/pending"
ACK_HEADERS = {"X-FOMS-Notification-Write": "1"}


@pytest.fixture
def crew(app):
    """박반장(반장) · 김재단 · 오재단(재단) · 한검수(검수 — 받침 없는 이름)."""
    return {"lead": make_user("박반장", lead=True), "kim": make_user("김재단", part="cut"),
            "oh": make_user("오재단", part="cut"), "han": make_user("한검수", part="inspect")}


# --------------------------------------------------------------------------- #
# 스위치(§4-5 의 1 · §4-10)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", [None, "off", "0", ""])
def test_switch_off_makes_no_rows_and_no_queries(crew, monkeypatch, value):
    monkeypatch.delenv(SWITCH, raising=False)
    if value is not None:
        monkeypatch.setenv(SWITCH, value)
    wire, order = capture(monkeypatch), alarm_order()
    assert floor_alarm.enabled() is False

    def writes():
        floor_alarm.note_mark(db_session, crew["lead"], press(order, 0, "cut", "takeover"),
                              gave(order, 0, "cut", by=crew["lead"], src=crew["kim"], to=crew["oh"]))
        floor_alarm.note(db_session, "hold", order.id, crew["lead"], reason="자재 기다림")
        floor_alarm.flush(db_session)

    _none, queries = count_queries(writes)
    assert queries == [] and alarms() == [] and wire.sent == [] and floor_alarm.POCKET not in db_session.info
    # 음성 대조군(같은 준비물 · 같은 부름): 켜면 줄이 생긴다.
    switch_on(monkeypatch)
    writes()
    assert kinds() == ["NEW_GIVEN", "STOP_TAKEN"]


def test_template_flag_follows_the_switch(app, monkeypatch):
    monkeypatch.delenv(SWITCH, raising=False)
    with app.test_request_context("/"):
        assert inject_foms_flags()["flag_floor_alarm"] is False
        monkeypatch.setenv(SWITCH, "on")
        assert inject_foms_flags()["flag_floor_alarm"] is True


# --------------------------------------------------------------------------- #
# 담당 변경 — 받은 사람 · 원래 담당 둘 다 긴급(사장님 답 1 · 답 2차 1 ~ 3)
# --------------------------------------------------------------------------- #
def test_give_to_someone_alarms_receiver_and_previous_holder(crew, monkeypatch):
    switch_on(monkeypatch)
    wire, order = capture(monkeypatch), alarm_order(3)
    give(order, 1, "cut", by=crew["lead"], src=crew["kim"], to=crew["oh"])
    (new,), (stop,) = alarms(crew["oh"].id), alarms(crew["kim"].id)
    assert (new.notification_type, new.is_urgent, new.target_type) == (T.NEW_GIVEN, True, "USER")
    assert new.title == "박반장이 재단 담당을 당신으로 변경했어요"
    assert new.message == "11/30 시공 · 정하늘 · 도면 2번\n[확인]을 누르면 그 주문 도면 칸으로 가요."
    assert (stop.notification_type, stop.is_urgent) == (T.STOP_TAKEN, True)
    assert stop.title == "박반장이 재단 담당을 오재단으로 변경했어요"
    assert stop.message == "11/30 시공 · 정하늘 · 도면 2번 · 하던 작업은 멈춰 주세요."
    assert alarms(crew["lead"].id) == []  # 누른 사람 본인에게는 안 보낸다
    assert (new.created_by_user_id, new.created_by_name, new.order_id) == (crew["lead"].id, "박반장", order.id)
    # 실시간 값(약속 6) — 지금 긴급 값과 같은 칸만, ``kind`` · ``notice`` · ``interrupt`` 는 싣지 않는다.
    (body,) = wire.to(crew["oh"].id)
    assert body == {"urgent": True, "notification_id": new.id, "notification_type": T.NEW_GIVEN, "title": new.title,
                    "message": new.message, "order_id": order.id, "created_by_name": "박반장"}
    assert sorted(wire.pushed) == sorted([new.id, stop.id]) and sorted(wire.badges) == sorted([crew["oh"].id, crew["kim"].id])
    assert state_of(new.id).user_id == crew["oh"].id and state_of(new.id).ack_at is None


def test_self_take_alarms_only_the_previous_holder(crew, monkeypatch):
    switch_on(monkeypatch)
    order = alarm_order()
    give(order, 0, "cut", by=crew["lead"], src=crew["kim"], to=crew["lead"])  # 고르기 창에서 '나'
    assert kinds() == ["STOP_TAKEN"]
    (stop,) = alarms(crew["kim"].id)
    assert stop.title == "박반장이 재단 담당을 가져갔어요" and stop.message.endswith("도면 1번 · 하던 작업은 멈춰 주세요.")
    # 받침 없는 이름은 '가'(§2-3 "한검수가 검수 담당을 가져갔어요")
    gang = make_user("강검수", part="inspect")
    give(order, 1, "inspect", by=crew["han"], src=gang, to=crew["han"])
    assert alarms(gang.id)[0].title == "한검수가 검수 담당을 가져갔어요"


def test_particles_follow_the_last_letter(crew, monkeypatch):
    switch_on(monkeypatch)
    order, jo = alarm_order(), make_user("이조", part="cut")
    give(order, 0, "cut", by=crew["han"], src=crew["kim"], to=jo)  # 준 사람 '한검수'(받침 없음 → 가) · 받은 사람 '이조'(받침 없음 → 로)
    assert alarms(jo.id)[0].title == "한검수가 재단 담당을 당신으로 변경했어요"
    assert alarms(crew["kim"].id)[0].title == "한검수가 재단 담당을 이조로 변경했어요"


def test_no_previous_holder_means_receiver_only(crew, monkeypatch):
    switch_on(monkeypatch)
    give(alarm_order(), 0, "cut", by=crew["lead"], src=None, to=crew["oh"])  # 사람 없는 옛 줄
    assert kinds() == ["NEW_GIVEN"]


# --------------------------------------------------------------------------- #
# 받는 사람 문(§4-5) — 음성 대조군은 같은 준비물 안에서
# --------------------------------------------------------------------------- #
def test_recipient_gate_keeps_alarms_inside_the_floor(crew, monkeypatch):
    switch_on(monkeypatch)
    org = PartnerOrg(name="가짜협력사")
    db_session.add(org)
    db_session.commit()
    off = make_user("꺼진재단", part="cut")
    db_session.get(User, off.id).is_active = False
    db_session.commit()
    refused = {
        "꺼진 계정": off,
        "협력사": make_user("협력직원", team=None, role="PARTNER", partner_org_id=org.id),
        "영업(프리랜서가 될 수 있는 팀)": make_user("이영업", team="SALES"),
        "CS": make_user("최상담", team="CS"),
        "파트도 반장도 아닌 생산팀": make_user("그냥생산", team="PRODUCTION"),
        "조회 전용 생산팀": make_user("보기생산", team="PRODUCTION", role="VIEWER", part="cut"),
    }
    order = alarm_order(len(refused) + 3)
    for j, person in enumerate(refused.values()):
        give(order, j, "cut", by=crew["lead"], src=None, to=person)
    assert alarms() == [], [n.target_user_id for n in alarms()]
    admin = make_user("관리", team="CS", role="ADMIN")
    for person, admin_ok, expected in ((crew["oh"], False, True), (crew["lead"], False, True), (admin, True, True),
                                       (admin, False, False), (refused["CS"], True, False)):
        assert can_receive(db_session.get(User, person.id), admin_ok=admin_ok) is expected, person.name
    # 대조군: 같은 주문 · 같은 누름에서 파트 계정 · 반장 · (담당을 받은) 관리자는 받는다.
    j = len(refused)
    give(order, j, "cut", by=crew["lead"], src=None, to=crew["oh"])
    give(order, j + 1, "cut", by=crew["kim"], src=None, to=crew["lead"])
    give(order, j + 2, "cut", by=crew["lead"], src=admin, to=admin)  # 관리자: 받은 것은 오고, 원래 담당 멈춤은 안 간다
    assert kinds(crew["oh"].id) == ["NEW_GIVEN"] and kinds(crew["lead"].id) == ["NEW_GIVEN"] and kinds(admin.id) == ["NEW_GIVEN"]


def test_admin_holder_gets_no_stop_alarm(crew, monkeypatch):
    """관리자는 담당을 받았을 때만 받는다 — 멈춤 · 띠는 자동으로 가지 않는다(§4-5 의 2)."""
    switch_on(monkeypatch)
    order, admin = alarm_order(), make_user("관리", team="CS", role="ADMIN")
    give(order, 0, "cut", by=crew["lead"], src=admin, to=crew["oh"])
    assert kinds(admin.id) == [] and kinds(crew["oh"].id) == ["NEW_GIVEN"]


# --------------------------------------------------------------------------- #
# 60초 합치기(§2-2)
# --------------------------------------------------------------------------- #
def test_same_order_part_giver_receiver_merge_within_60_seconds(crew, monkeypatch):
    clock = switch_on(monkeypatch)
    wire, order = capture(monkeypatch), alarm_order(4)
    for step, j in enumerate((0, 1, 3)):
        clock["now"] = NOW + datetime.timedelta(seconds=20 * step)
        give(order, j, "cut", by=crew["lead"], src=crew["kim"], to=crew["oh"])
    (new,), (stop,) = alarms(crew["oh"].id), alarms(crew["kim"].id)
    assert new.title == "박반장이 재단 담당을 당신으로 변경했어요 — 도면 3장"
    assert new.message == "11/30 시공 · 정하늘 · 도면 1번 · 2번 · 4번"
    assert stop.title == "박반장이 재단 담당을 오재단으로 변경했어요 — 도면 3장"
    assert stop.message == "11/30 시공 · 정하늘 · 도면 1번 · 2번 · 4번 · 하던 작업은 멈춰 주세요."
    assert [b["notification_id"] for b in wire.to(crew["oh"].id)] == [new.id] * 3  # 같은 번호로 글만 갈아 끼운다
    assert sorted(wire.pushed) == sorted([new.id, stop.id])  # 폰 알림은 새 줄일 때 한 번만
    # 60초가 지나면 · 이미 눌렀으면 · 다른 주문이면 · 다른 파트면 새 줄.
    clock["now"] = NOW + datetime.timedelta(seconds=40 + 61)
    give(order, 2, "cut", by=crew["lead"], src=crew["kim"], to=crew["oh"])
    assert len(alarms(crew["oh"].id)) == 2
    ack(alarms(crew["oh"].id)[-1].id)
    give(order, 2, "cut", by=crew["lead"], src=None, to=crew["oh"])
    give(alarm_order(), 0, "cut", by=crew["lead"], src=None, to=crew["oh"])
    assert len(alarms(crew["oh"].id)) == 4
    multi = make_user("다재다", part="cut")
    db_session.get(User, multi.id).production_parts = ["cut", "edge"]
    db_session.commit()
    for part in ("cut", "edge"):
        give(order, 0, part, by=crew["lead"], src=None, to=multi)
    assert [n.title for n in alarms(multi.id)] == ["박반장이 재단 담당을 당신으로 변경했어요", "박반장이 엣지 담당을 당신으로 변경했어요"]


def test_handover_costs_three_reads(crew, monkeypatch):
    """§4-10 — 담당 바꾸기 한 번: 주문 1 + 사람 1 + 합치기 찾기 1(+ 받는 사람마다 넣기 3)."""
    switch_on(monkeypatch)
    capture(monkeypatch)
    order = alarm_order()
    floor_alarm.note_mark(db_session, crew["lead"], press(order, 0, "cut", "takeover"),
                          gave(order, 0, "cut", by=crew["lead"], src=crew["kim"], to=crew["oh"]))
    db_session.commit()
    _none, queries = count_queries(lambda: floor_alarm.flush(db_session))
    reads = [q for q in queries if q.lstrip().upper().startswith("SELECT")]
    inserts = [q for q in queries if q.lstrip().upper().startswith("INSERT")]
    assert len(reads) == 3 and len(inserts) == 6, queries


# --------------------------------------------------------------------------- #
# 남의 시작 취소 · 남의 완료 취소(약속 2)
# --------------------------------------------------------------------------- #
def test_removed_and_undone_people_get_a_band(crew, monkeypatch):
    switch_on(monkeypatch)
    wire, order = capture(monkeypatch), alarm_order()
    edge = make_user("박엣지", part="edge")
    removed = {"changed": True, "holders_before": [who(crew["kim"], done=False), who(crew["oh"], done=False)],
               "mark": {"holders": [who(crew["oh"], done=False)]}}
    floor_alarm.note_mark(db_session, crew["lead"], press(order, 1, "cut", "remove"), removed)
    undone = {"changed": True, "holders_before": [who(edge, done=True)], "mark": {"holders": [who(edge, done=False)]}}
    floor_alarm.note_mark(db_session, crew["lead"], press(order, 1, "edge", "undo"), undone)
    db_session.commit()
    floor_alarm.flush(db_session)
    (start,), (done,) = alarms(crew["kim"].id), alarms(edge.id)
    assert (start.notification_type, start.is_urgent, start.title, start.message) == (
        T.NOTICE_START_CANCELLED, False, "박반장이 재단 시작을 취소했어요", "정하늘 · 도면 2번")
    assert (done.notification_type, done.title, done.message) == (
        T.NOTICE_DONE_CANCELLED, "박반장이 엣지 완료를 취소했어요 — 다시 봐 주세요", "정하늘 · 도면 2번")
    assert alarms(crew["oh"].id) == []  # 남아 있는 사람은 안 받는다
    (band,) = wire.to(edge.id)
    assert band["urgent"] is False and band["floor_notice"] is True and "notice" not in band and wire.pushed == []  # 띠는 폰 알림 없음
    # 자기 시작 취소 · 자기 완료 취소 · 바뀐 것 없는 응답(멱등)은 알람이 없다.
    own = {"changed": True, "holders_before": [who(crew["oh"], done=False)], "mark": {"holders": []}}
    floor_alarm.note_mark(db_session, crew["oh"], press(order, 0, "cut", "release"), own)
    floor_alarm.note_mark(db_session, crew["lead"], press(order, 0, "cut", "remove"), {**removed, "changed": False})
    db_session.commit()
    floor_alarm.flush(db_session)
    assert len(alarms()) == 2


def test_mark_events_reads_the_promised_shapes():
    data = {"changed": True, "gave": {"by": {"user_id": 1, "name": "박반장"}, "from": {"user_id": 2, "name": "김재단"},
                                      "to": {"user_id": 3, "name": "오재단"}, "self": False}}
    assert floor_alarm.mark_events(1, "takeover", data) == [
        ("given", {"to": [3]}), ("taken", {"to": [2], "self": False, "to_name": "오재단"})]
    assert floor_alarm.mark_events(1, "take", {"changed": True, "mark": {"holders": [{"user_id": 1, "name": "박", "done": False}]}}) == []


# --------------------------------------------------------------------------- #
# 다시 받기 API(약속 7 · §4-4)
# --------------------------------------------------------------------------- #
def test_pending_api_returns_only_my_unacked_alarms(client, crew, monkeypatch):
    monkeypatch.setenv(SWITCH, "on")  # 시계는 그대로(API 가 지금 시각으로 기간을 본다)
    capture(monkeypatch)
    order = alarm_order()
    give(order, 0, "cut", by=crew["lead"], src=crew["kim"], to=crew["oh"])
    removed = {"changed": True, "holders_before": [who(crew["oh"], done=False)], "mark": {"holders": []}}
    floor_alarm.note_mark(db_session, crew["lead"], press(order, 1, "edge", "remove"), removed)  # 다른 파트 — 새 일 알람은 그대로
    db_session.commit()
    floor_alarm.flush(db_session)
    login(client, crew["oh"])
    res = client.get(PENDING)
    data = res.get_json()["data"]
    assert res.status_code == 200 and res.get_json()["success"] is True and res.headers["Cache-Control"] == "private, no-store"
    assert [a["notification_type"] for a in data["urgent"]] == [T.NEW_GIVEN]
    assert [a["notification_type"] for a in data["notices"]] == [T.NOTICE_START_CANCELLED]
    assert set(data["urgent"][0]) == {"urgent", "notification_id", "notification_type", "title", "message", "order_id",
                                      "created_by_name"} and data["notices"][0]["floor_notice"] is True
    # 본인 계정 화면에만(사장님 답 4): 다른 계정으로 물으면 그 계정 것만.
    login(client, crew["kim"])
    mine = client.get(PENDING).get_json()["data"]
    assert [a["notification_type"] for a in mine["urgent"]] == [T.STOP_TAKEN] and mine["notices"] == []
    login(client, crew["lead"])
    assert client.get(PENDING).get_json()["data"] == {"urgent": [], "notices": []}
    # [확인] 기록 API(지금 것 그대로) 뒤에는 안 실린다. 지금 긴급 다시 띄우기에도 같은 줄이 실려 있었다.
    login(client, crew["oh"])
    urgent_id = data["urgent"][0]["notification_id"]
    assert [i["notification_id"] for i in client.get("/erp/api/notifications/pending-urgent").get_json()["data"]["items"]] == [urgent_id]
    assert client.post(f"/erp/api/notifications/{urgent_id}/ack", headers=ACK_HEADERS).status_code == 200
    assert client.get(PENDING).get_json()["data"]["urgent"] == []
    # 스위치를 끄면 빈 목록 · 협력사 계정은 문지기가 막는다 · 로그인 안 하면 빈 목록.
    monkeypatch.setenv(SWITCH, "off")
    assert client.get(PENDING).get_json()["data"] == {"urgent": [], "notices": []}
    monkeypatch.setenv(SWITCH, "on")
    org = PartnerOrg(name="가짜협력사")
    db_session.add(org)
    db_session.commit()
    login(client, make_user("협력직원", team=None, role="PARTNER", partner_org_id=org.id))
    partner = client.get(PENDING)
    assert partner.status_code in (302, 403) and b"PRODUCTION_FLOOR" not in partner.data
    with client.session_transaction() as sess:
        sess.clear()
    anonymous = client.get(PENDING)  # 로그인 안 했으면 빈 목록(약속 7)
    assert anonymous.status_code == 200 and anonymous.get_json()["data"] == {"urgent": [], "notices": []}


def test_pending_windows_limits_and_one_query(crew, monkeypatch):
    clock = switch_on(monkeypatch)
    capture(monkeypatch)
    ages = {"73시간": 73, "71시간": 71, "13시간": 13, "11시간": 11}
    for label, hours in ages.items():
        clock["now"] = NOW - datetime.timedelta(hours=hours)
        order = alarm_order(customer=label)
        give(order, 0, "cut", by=crew["lead"], src=crew["kim"], to=crew["oh"])  # 긴급 둘(오재단 새 일 · 김재단 멈춤)
        floor_alarm.note_mark(db_session, crew["lead"], press(order, 1, "edge", "remove"),  # 띠 하나(오재단)
                              {"changed": True, "holders_before": [who(crew["oh"], done=False)], "mark": {"holders": []}})
        db_session.commit()
        floor_alarm.flush(db_session)
    out, queries = count_queries(lambda: pending_for(db_session, crew["oh"].id, NOW))
    assert len(queries) == 1
    customer = lambda row: row["message"].splitlines()[0].split(" · ")[-2]  # noqa: E731 - "… · 고객 · 도면 n번"
    assert [customer(n) for n in out["urgent"]] == ["71시간", "13시간", "11시간"]  # 72시간 안 · 오래된 것부터
    assert [customer(n) for n in out["notices"]] == ["11시간"]  # 띠는 12시간 안
    clock["now"] = NOW
    for _ in range(4):  # 오래된 것부터 5건까지만
        give(alarm_order(customer="새것"), 0, "cut", by=crew["lead"], src=crew["kim"], to=crew["oh"])
    capped = pending_for(db_session, crew["oh"].id, NOW)["urgent"]
    assert len(capped) == 5 and customer(capped[0]) == "71시간"


# --------------------------------------------------------------------------- #
# 알람이 실패해도 본 쓰기는 남는다 · 되감은 쓰기의 알람은 안 나간다(§4-10 · 약속 3)
# --------------------------------------------------------------------------- #
def test_failing_flush_never_raises_and_keeps_the_committed_write(crew, monkeypatch):
    switch_on(monkeypatch)
    order = alarm_order()
    db_session.get(Order, order.id).product = "본 쓰기"
    floor_alarm.note(db_session, "hold", order.id, crew["lead"], reason="자재")
    db_session.commit()
    monkeypatch.setattr(rules, "plan", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    floor_alarm.flush(db_session)  # 예외가 밖으로 안 나온다
    db_session.expire_all()
    assert db_session.get(Order, order.id).product == "본 쓰기" and alarms() == []
    # 적기 함수도 예외를 내지 않는다(주문 번호가 글이어도).
    floor_alarm.note(db_session, "hold", "주문번호아님", crew["lead"])
    floor_alarm.note_mark(db_session, crew["lead"], object(), {"changed": True, "gave": {"to": "모양이 다름"}})
    floor_alarm.flush(db_session)
    assert alarms() == []


def test_rolled_back_write_sends_nothing(crew, monkeypatch):
    switch_on(monkeypatch)
    order = alarm_order()
    mark_order = db_session.get(Order, order.id)
    mark_order.product = "되감길 쓰기"
    db_session.flush()
    floor_alarm.note_mark(db_session, crew["lead"], press(order, 0, "cut", "takeover"),
                          gave(order, 0, "cut", by=crew["lead"], src=crew["kim"], to=crew["oh"]))
    assert len(db_session.info[floor_alarm.POCKET]) == 2
    db_session.rollback()  # 거절 · 오류 길 — flush 를 안 부른다. 그래도 주머니는 비어 있다.
    assert floor_alarm.POCKET not in db_session.info
    floor_alarm.flush(db_session)
    assert alarms() == []
    # 대조군: 같은 적기를 커밋하면 나간다.
    give(order, 0, "cut", by=crew["lead"], src=crew["kim"], to=crew["oh"])
    assert kinds() == ["NEW_GIVEN", "STOP_TAKEN"]


def test_real_press_makes_real_marks_for_the_seed(client, crew):
    """준비물 확인(대조군) — 카드 누름이 진짜 표시 줄을 만든다(다음 파일의 '작업 중인 사람' 판정이 읽는 줄)."""
    order = alarm_order()
    login(client, crew["kim"])
    assert mark(client, order, 0, "cut", "take", "none").status_code == 200

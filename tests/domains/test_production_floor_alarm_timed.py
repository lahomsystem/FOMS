"""생산 현장 알람 #21 — "오늘 나가는 주문이 아직 안 끝났어요"(설계서 2026-11-28 생산 현장 알람 §4-6 · 사장님 답 2차 4 "오전 9시 · 오후 1시 두 번").

WORKER 1분 알림 루프의 한 단계다. 시각은 늘 넣어 준다(한국 시각 — 벽시계에 기대지 않는다).

되돌리면 실패: 9시 전에 냄 · 같은 칸에 두 번 냄 · 13시에 다시 안 냄 · 주문마다 따로 냄 · 다른 공장 반장에게 냄 · 내일 나갈 주문 ·
제작이 끝난 공장 몫을 셈 · 스위치 꺼짐에 쿼리 · 올림 대상(긴급)으로 만듦.
"""
from __future__ import annotations

import datetime
import importlib.util
import pathlib

import pytest
import pytz

from db import db_session
from foms.services.production import floor_alarm_text as T
from foms.services.production import floor_alarm_timed as timed
from models import Order
from tests.support.production_factory_seed import factory_user, mixed_order, set_factory_done
from tests.support.production_floor_alarm_seed import SWITCH, alarm_order, alarms, capture, count_queries, kinds
from tests.support.production_part_claim_seed import make_user

KST = pytz.timezone("Asia/Seoul")
DAY = "2026-11-30"
ROOT = pathlib.Path(__file__).resolve().parents[2]


def _at(hour: int, minute: int = 0, day: int = 30) -> datetime.datetime:
    return KST.localize(datetime.datetime(2026, 11, day, hour, minute))


@pytest.fixture
def loop(app, monkeypatch):
    monkeypatch.setenv(SWITCH, "on")
    monkeypatch.setitem(timed._DONE, "day", "")
    monkeypatch.setitem(timed._DONE, "slots", set())
    return capture(monkeypatch)


def _pass(now: datetime.datetime) -> dict:
    """루프 한 바퀴 — 줄 만들기 → 커밋 → 배달(스크립트의 그 단계와 같은 차례)."""
    result = timed.run(db_session, now=now)
    db_session.commit()
    timed.deliver(db_session, result)
    return result


def test_slots_are_nine_and_thirteen_kst():
    assert timed.SLOT_HOURS == (9, 13)
    assert [timed.current_slot(_at(h, m)) for h, m in ((8, 59), (9, 0), (12, 59), (13, 0), (23, 30))] == [None, 9, 9, 13, 13]


def test_one_band_per_lead_per_slot_twice_a_day(loop):
    lead, lead2 = make_user("박반장", lead=True), factory_user("이반장", factory=2, lead=True)
    worker, admin = make_user("김재단", part="cut"), make_user("관리", team="CS", role="ADMIN")
    alarm_order(1, customer="정하늘", build=DAY)
    alarm_order(1, customer="윤봄", build=DAY)
    alarm_order(1, customer="내일주문", build="2026-12-01")
    # 9시 전 — 쿼리 0 · 줄 0.
    result, queries = count_queries(lambda: timed.run(db_session, now=_at(8, 59)))
    assert queries == [] and result["slot"] is None and alarms() == []
    # 9시 뒤 첫 바퀴 — 1공장 반장에게 띠 하나(주문 둘을 한 줄로). 2공장 반장 · 작업자 · 관리자는 안 받는다.
    first = _pass(_at(9, 3))
    assert (first["slot"], first["orders"], first["notifications"]) == (9, 2, 1)
    (band,) = alarms()
    assert (band.target_user_id, band.notification_type, band.is_urgent, band.order_id) == (lead.id, T.NOTICE_DUE_TODAY, False, None)
    assert (band.title, band.message) == ("오늘 나가는 주문 2건이 아직 안 끝났어요", "정하늘 · 윤봄")
    assert alarms(lead2.id) == [] and alarms(worker.id) == [] and alarms(admin.id) == []
    assert loop.to(lead.id) == [{"urgent": False, "floor_notice": True, "notification_id": band.id,
                                 "notification_type": T.NOTICE_DUE_TODAY, "title": band.title, "message": band.message,
                                 "order_id": None, "created_by_name": ""}]
    assert loop.pushed == []  # 띠는 폰 알림을 걸지 않는다
    # 같은 칸 다음 바퀴들 — 줄 0. 첫 다음 바퀴는 "보냈나 찾기" 하나, 그 뒤는 쿼리 0.
    _again, queries = count_queries(lambda: _pass(_at(9, 4)))
    assert len(queries) == 1 and len(alarms()) == 1
    _again, queries = count_queries(lambda: _pass(_at(12, 59)))
    assert queries == [] and len(alarms()) == 1
    # 오후 1시 칸 — 같은 주문도 다시 뜬다(하루 두 번).
    second = _pass(_at(13, 0))
    assert (second["slot"], second["notifications"]) == (13, 1) and kinds(lead.id) == ["NOTICE_DUE_TODAY"] * 2
    _pass(_at(13, 1))
    _pass(_at(17, 0))
    assert len(alarms()) == 2


def test_first_pass_of_a_slot_costs_three_reads(loop):
    """§4-10 — 칸의 첫 바퀴: 보냈나 찾기 1 + 주문 읽기 1 + 반장 읽기 1(+ 받는 반장마다 넣기 3)."""
    make_user("박반장", lead=True)
    for name in ("정하늘", "윤봄", "한겨울"):
        alarm_order(1, customer=name, build=DAY)
    _result, queries = count_queries(lambda: _pass(_at(9, 0)))
    head = [q.lstrip().upper()[:6] for q in queries]
    assert (head.count("SELECT"), head.count("INSERT")) == (3, 3), queries


def test_other_worker_process_does_not_send_again(loop):
    """이 프로세스가 기억하는 칸이 없어도(다른 WORKER · 다시 뜬 WORKER) 이미 만든 줄이 있으면 안 만든다."""
    make_user("박반장", lead=True)
    alarm_order(1, build=DAY)
    assert _pass(_at(9, 1))["notifications"] == 1
    timed._DONE["slots"].clear()  # 다시 뜬 프로세스
    assert _pass(_at(9, 30))["notifications"] == 0 and len(alarms()) == 1


def test_nothing_due_or_nobody_to_tell_sends_nothing(loop):
    lead = make_user("박반장", lead=True)
    alarm_order(1, customer="내일주문", build="2026-12-01")
    done = alarm_order(1, customer="끝난주문", build=DAY)
    order = db_session.get(Order, done.id)
    order.erp_stage_code, order.status = "CONSTRUCTION", "CONSTRUCTION"  # 제작 완료 = 생산 단계를 떠났다
    db_session.commit()
    assert _pass(_at(9, 5))["notifications"] == 0 and alarms() == []
    _again, queries = count_queries(lambda: _pass(_at(9, 6)))  # 보낼 것이 없던 칸은 다시 안 본다
    assert queries == []
    alarm_order(1, customer="늦게 잡힌 주문", build=DAY)
    assert _pass(_at(10, 0))["notifications"] == 0  # 칸마다 한 번 — 다음 칸(13시)에 본다
    assert _pass(_at(13, 2))["notifications"] == 1 and alarms(lead.id)[0].message == "늦게 잡힌 주문"


def test_each_factory_lead_gets_only_unfinished_factory_share(loop):
    lead1, lead2 = make_user("박반장", lead=True), factory_user("이반장", factory=2, lead=True)
    mixed = mixed_order(3, f2=(2,), extra={"parties": {"customer": {"name": "섞인주문"}}, "schedule": {"construction": {"date": DAY}}})
    order = db_session.get(Order, mixed.id)
    order.erp_construction_date = DAY
    db_session.commit()
    alarm_order(1, customer="일공장주문", build=DAY)
    set_factory_done(mixed.id, 2, [mixed.keys[2]])  # 2공장 몫은 끝났다
    _pass(_at(9, 0))
    assert [n.message for n in alarms(lead1.id)] == ["섞인주문 · 일공장주문"] and alarms(lead2.id) == []


def test_switch_off_costs_nothing(app, monkeypatch):
    monkeypatch.delenv(SWITCH, raising=False)
    monkeypatch.setitem(timed._DONE, "slots", set())
    make_user("박반장", lead=True)
    alarm_order(1, build=DAY)
    result, queries = count_queries(lambda: timed.run(db_session, now=_at(9, 30)))
    assert queries == [] and result["enabled"] is False and alarms() == []


def test_loop_script_runs_the_step_after_the_other_steps():
    """1분 루프 스크립트에 이 단계가 걸려 있다(글로 확인 — 스크립트는 앱을 통째로 싣는다)."""
    source = (ROOT / "scripts" / "maintenance" / "run_notification_escalation.py").read_text(encoding="utf-8")
    assert 'result["floor_alarm_due"] = _floor_alarm_due_once(db)' in source
    assert source.index("_drawing_deadline_alert_once(db)") < source.index("_floor_alarm_due_once(db)")
    step = source[source.index("def _floor_alarm_due_once"):source.index("def _print_result")]
    assert step.index("floor_alarm_timed.run(db)") < step.index("db.commit()") < step.index("floor_alarm_timed.deliver(db, due)")
    assert importlib.util.find_spec("foms.services.production.floor_alarm_timed") is not None

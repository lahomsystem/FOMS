"""CS 감시 루프(플랜 C1-3) — 바로 끄기 · 대표 잠금 · TERM 깃발 · 아침 보고 한 번 · 약속 · 웹훅 · 수신 누락 경보.

완료 기준(브리프): 끈 바퀴는 일 0 · env 를 안 켜면 자식이 없다 · 대표 잠금이 두 번째 대표를 막는다 · TERM 뒤엔 쓰기 0 ·
아침 보고는 운영일 하루 한 번이고 손님 글이 없다 · 약속 넘김은 약속마다 한 번 · 넘기기 대기 웹훅 경보 · 웹훅이 없는
환경(스테이징)은 수신 누락 경보를 끈다 · Open API 키가 없어도 바퀴가 끝난다. PostgreSQL advisory lock 자체는
``tests/postgres/test_cs_loop_leader_pg.py``. 손으로 꾸민 합성 글만 쓴다(전화 꼴 숫자 없음).
시각은 2026-11 KST(11-02 월요일), 운영일 달력은 '주말만 쉼' 가짜 달력이다.
"""

from __future__ import annotations

import datetime
import importlib.util
import pathlib
import re
import threading
import time

import pytest
from sqlalchemy.exc import NoResultFound
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.cs_agent import channel_read as cr
from foms.services.cs_agent import loop, report
from foms.services.cs_agent.state import KST
from foms.services.sidefx_worker import upsert_heartbeat
from models import (
    ChannelWebhookJob,
    ChannelWebhookReceipt,
    Notification,
    NotificationUserState,
    SideEffectWorkerHeartbeat,
    SystemSetting,
    User,
)
from tests.support.cs_agent_fakes import (
    HAUD_CHANNEL,
    LAHOM_CHANNEL,
    FakeReader,
    at,
    chat_row,
    chat_snap,
    derived,
    entity,
    inbound,
    message_count,
    msg_row,
    naive,
    weekdays_only,
)
from tests.support.worker_jobs import jobs

_RUNNER = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "run_cs_loop.py"
#: 손님 글 속 표지 — 알림 제목 · 본문 어디에도 나오면 안 된다.
MARKS = ("주황선반", "보라문고리")


def run(now, *, reader=None, stop=None, watch=False, clock=None, budget=120.0):
    config = loop.LoopConfig(watch_missing_inbound=watch, reconcile_budget_seconds=budget)
    return loop.run_pass(db_session, config=config, stop=stop, reader=reader or FakeReader(), now=now,
                         clock=clock or (lambda: 0.0), is_business_day=weekdays_only)


def notes(kind):
    return db_session.query(Notification).filter_by(notification_type=kind).order_by(Notification.id).all()


def admin(name="보고받는관리자", role="ADMIN"):
    user = User(username=f"cs_{name}", password=generate_password_hash("pw"), name=name, role=role,
                is_active=True)
    db_session.add(user)
    db_session.commit()
    return int(user.id)


def waiting_customer(chat="uc-1", when=None, log_id=1, channel=LAHOM_CHANNEL):
    inbound(log_id, entity(f"m-{chat}", when or at(2, 9), text=f"{MARKS[0]} {MARKS[1]} 문의드려요",
                           chat=chat, channel=channel))


def webhook_job(created, status="pending"):
    receipt = ChannelWebhookReceipt(source="channel_talk", content_hash="0" * 64, accepted_at=created,
                                    dedup_expires_at=created + datetime.timedelta(days=30), envelope={"v": 1})
    db_session.add(receipt)
    db_session.flush()
    db_session.add(ChannelWebhookJob(receipt_id=receipt.id, status=status, created_at=created, updated_at=created))
    db_session.commit()


def load_runner():
    spec = importlib.util.spec_from_file_location("run_cs_loop_ut", _RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── 감독자 배선 · 깃발 ───────────────────────────────────────────────────


def test_child_starts_only_when_the_env_flag_is_on():
    assert "cs_loop" not in [j.name for j in jobs({})]
    assert "cs_loop" not in [j.name for j in jobs({"FOMS_CS_LOOP_ENABLED": "0"})]
    listed = jobs({"FOMS_CS_LOOP_ENABLED": "1"})
    child = next(j for j in listed if j.name == "cs_loop")
    assert child.deferred and listed[-1].name == "rq_worker"  # rq 뒤에 켜진다(부팅 순서)
    assert child.argv[1:] == ("scripts/maintenance/run_cs_loop.py", "--loop", "--interval", "900", "--json")


def test_stop_flag_wakes_a_sleep_and_stops_the_pass():
    stop = loop.StopFlag()
    assert stop.sleep(0.01) is False
    stop.check()  # 깃발이 내려 있으면 아무 일 없다
    threading.Timer(0.2, stop.set, args=(15, None)).start()  # 자는 도중 TERM(signal.signal 처리기 꼴)
    started = time.monotonic()
    assert stop.sleep(30, tick=0.05) is True and time.monotonic() - started < 2
    with pytest.raises(loop.PassStopped):
        stop.check()


# ── 바로 끄기 · 대표 잠금 · TERM ─────────────────────────────────────────


def test_kill_switch_is_read_every_pass_and_stops_all_work(app):
    admin()
    waiting_customer()
    loop.set_switch(db_session, on=False)
    assert run(at(2, 8, 30)).outcome == loop.OUTCOME_KILLED
    assert message_count() == 0 and not notes(report.NOTIFY_MORNING_REPORT)
    row = db_session.get(SystemSetting, loop.SWITCH_KEY)
    row.setting_value = {"loop": "of"}  # 꼴이 틀린 값은 끈 것으로 본다(오타로 켜진 채 남지 않게)
    db_session.commit()
    assert run(at(2, 8, 45)).outcome == loop.OUTCOME_KILLED and message_count() == 0
    row.setting_value = None  # 줄은 있는데 값이 비어도 끈 것(R5-8)
    db_session.commit()
    assert run(at(2, 8, 50)).outcome == loop.OUTCOME_KILLED and message_count() == 0
    loop.set_switch(db_session, on=True)  # 음성 대조군: 다시 켜면 재배포 없이 다음 바퀴부터 돈다
    result = run(at(2, 9))
    assert result.outcome == loop.OUTCOME_OK and result.ingested == 1 and len(notes(report.NOTIFY_MORNING_REPORT)) == 1


def test_advisory_lock_blocks_a_second_leader(app):
    waiting_customer()
    with loop.leader_lock(engine) as first:
        assert first is True
        assert run(at(2, 9)).outcome == loop.OUTCOME_NOT_LEADER
        assert message_count() == 0 and db_session.get(SystemSetting, report.STATE_KEY) is None
    assert run(at(2, 9)).outcome == loop.OUTCOME_OK and message_count() == 1  # 풀리면 돈다


def test_term_flag_means_no_write_starts(app):
    admin()
    waiting_customer()
    stop = loop.StopFlag()
    stop.set()
    assert run(at(2, 9), stop=stop).outcome == loop.OUTCOME_STOPPED and message_count() == 0

    # 읽는 도중 TERM: 읽은 채널톡 글은 버리고, 상태 · 알림 · 기록 줄 쓰기를 시작하지 않는다.
    stop = loop.StopFlag()
    reader = FakeReader([chat_snap("uc-7", at(2, 8, 50))], {"uc-7": [derived("m7", at(2, 8, 50), chat="uc-7")]},
                        on_read=lambda _chat: stop.set())
    result = run(at(2, 9), reader=reader, stop=stop)
    assert result.outcome == loop.OUTCOME_STOPPED and ("read", "LAHOM", "uc-7") in reader.calls
    assert result.ingested == 1 and message_count() == 1  # TERM 전에 끝난 수신 기록 읽기만 남았다
    assert not db_session.query(Notification).count() and db_session.get(SystemSetting, report.STATE_KEY) is None
    with pytest.raises(NoResultFound):
        chat_row("uc-7")  # 상담 상태도 반영하지 않았다


def test_term_between_the_message_write_and_the_state_write(app, monkeypatch):
    stop, real_apply = loop.StopFlag(), loop.apply_api_messages

    def apply_then_term(*args, **kwargs):
        written = real_apply(*args, **kwargs)  # 글 반영은 커밋까지 끝났다
        stop.set()
        return written

    monkeypatch.setattr(loop, "apply_api_messages", apply_then_term)
    reader = FakeReader([chat_snap("uc-8", at(2, 8, 55))], {"uc-8": [derived("m8", at(2, 8, 55), chat="uc-8")]})
    assert run(at(2, 9, 5), reader=reader, stop=stop).outcome == loop.OUTCOME_STOPPED
    row = chat_row("uc-8")  # 상태(updatedAt)는 쓰지 않았다 — 다음 바퀴가 이 상담을 다시 맞춘다(R5-3)
    assert (row.chat_state, row.state_at, message_count()) == (None, None, 1)


def test_term_after_reconcile_and_while_publishing_sends_nothing(app, monkeypatch):
    admin()
    waiting_customer()
    stop, real_states = loop.StopFlag(), loop.compute_open_states

    def states_then_term(*args, **kwargs):
        found = real_states(*args, **kwargs)
        stop.set()  # 보정 · 상태 계산 뒤, 알림 전 TERM(R5-3)
        return found

    monkeypatch.setattr(loop, "compute_open_states", states_then_term)
    assert run(at(2, 9), stop=stop).outcome == loop.OUTCOME_STOPPED
    assert not db_session.query(Notification).count() and db_session.get(SystemSetting, report.STATE_KEY) is None

    # publish 안: 기록 줄을 잠근 뒤(다른 컨테이너를 기다리는 사이) TERM — 알림은 쓰지 않는다.
    checks = []

    def term_on_second_check():
        checks.append(1)
        if len(checks) == 2:
            raise loop.PassStopped()

    with pytest.raises(loop.PassStopped):
        report.publish(db_session, states=[], missing=[], checks={}, watch_missing_inbound=False, now=at(2, 9),
                       is_business_day=weekdays_only, stop_check=term_on_second_check)
    db_session.rollback()
    assert not db_session.query(Notification).count() and len(checks) == 2
    assert "report_date" not in (db_session.get(SystemSetting, report.STATE_KEY).setting_value or {})
    assert report.publish(db_session, states=[], missing=[], checks={}, watch_missing_inbound=False, now=at(2, 9),
                          is_business_day=weekdays_only).report_sent  # 음성 대조: 깃발이 없으면 낸다


# ── 아침 보고 ───────────────────────────────────────────────────────────


def test_morning_report_once_per_business_day_without_customer_text(app):
    admin_id = admin()
    admin("영업직원", role="STAFF")
    waiting_customer("uc-1", datetime.datetime(2026, 10, 27, 10, tzinfo=KST), log_id=1)  # 화요일 → 3일+
    waiting_customer("uc-2", datetime.datetime(2026, 10, 30, 16, tzinfo=KST), log_id=2)  # 금요일 저녁 → 답 필요
    waiting_customer("uc-3", datetime.datetime(2026, 10, 30, 9, tzinfo=KST), log_id=3, channel=HAUD_CHANNEL)
    inbound(4, entity("a3", datetime.datetime(2026, 10, 30, 10, tzinfo=KST), person="manager",
                      text="내일 다시 연락드리겠습니다", chat="uc-3", channel=HAUD_CHANNEL))
    assert not run(at(2, 7, 59)).report_sent  # 8시 전
    assert run(at(2, 8)).report_sent
    (note,) = notes(report.NOTIFY_MORNING_REPORT)
    assert note.target_role == "ADMIN" and note.order_id is None and not note.is_urgent
    assert "11-02(월)" in note.title and "라홈 2 · 하우드 0" in note.title
    assert "[라홈] 3일+ 1 · 약속 넘김 0 · 답 필요 1 · 약속 기한 전 0" in note.message
    assert "[하우드] 3일+ 0 · 약속 넘김 0 · 답 필요 0 · 약속 기한 전 1" in note.message
    assert "https://desk.channel.io/#/channels/201824/user_chats/uc-1" in note.message
    assert "'내일' 약속(채팅) · 기한 11-02 18:00" in note.message and "[마지막 정상 바퀴] 없음" in note.message
    assert note.message.index("uc-1") < note.message.index("uc-2") < note.message.index("uc-3")  # 우선순위 순
    assert not any(mark in note.title + note.message for mark in MARKS)
    assert not re.search(r"\d{3}-?\d{3,4}-?\d{4}", note.message)  # 전화 꼴 숫자 없음
    receivers = {s.user_id for s in db_session.query(NotificationUserState).filter_by(notification_id=note.id)}
    assert receivers == {admin_id}

    assert not run(at(2, 8, 15)).report_sent  # 같은 날 다음 바퀴
    assert not run(at(2, 9), reader=FakeReader(), stop=loop.StopFlag()).report_sent  # 재시작 · 두 번째 컨테이너
    upsert_heartbeat(engine, "CS_LOOP", metadata={report.HEARTBEAT_LAST_SUCCESS_KEY: "2026-11-02T22:45:00"})
    assert run(at(3, 8)).report_sent  # 다음 운영일
    assert not run(at(7, 8)).report_sent  # 토요일은 보고하지 않는다
    reports = notes(report.NOTIFY_MORNING_REPORT)
    assert len(reports) == 2 and "[마지막 정상 바퀴] 11-03 07:45" in reports[-1].message


# ── 경보 ────────────────────────────────────────────────────────────────


def test_promise_overdue_alerts_once_per_promise(app):
    admin()
    inbound(1, entity("m1", at(2, 9), text="배송 문의", chat="uc-1"))
    inbound(2, entity("a1", at(2, 10), person="manager", text="내일 다시 연락드리겠습니다", chat="uc-1"))
    inbound(3, entity("m2", at(2, 9, 30), text="시공 문의", chat="uc-2"))
    inbound(4, entity("a2", at(2, 11), person="manager", text="확인 후 전화 드리겠습니다", chat="uc-2"))
    assert run(at(2, 16, 50)).alerts == {}  # 둘 다 기한 전
    assert run(at(2, 17, 30)).alerts == {"promise": 1}
    (first,) = notes(report.NOTIFY_PROMISE_OVERDUE)
    assert "uc-2" in first.message and "uc-1" not in first.message
    assert "전화 약속 — 채팅으로는 확인 불가" in first.message and first.title == "상담 약속 기한 넘김 1건"
    assert run(at(2, 17, 45)).alerts == {}  # 같은 약속은 다시 알리지 않는다
    assert run(at(3, 17, 30)).alerts == {"promise": 1}
    latest = notes(report.NOTIFY_PROMISE_OVERDUE)[-1]
    assert "uc-1" in latest.message and "uc-2" not in latest.message and "'내일' 약속(채팅)" in latest.message
    assert len(notes(report.NOTIFY_PROMISE_OVERDUE)) == 2


def test_pending_webhook_jobs_alarm_once_each_after_a_minute(app):
    admin()
    base = naive(at(2, 10))
    webhook_job(base - datetime.timedelta(minutes=5))  # 경보
    webhook_job(base - datetime.timedelta(seconds=30))  # 아직 1분 안
    webhook_job(base - datetime.timedelta(minutes=10), status="enqueued")  # 넘겼다
    webhook_job(base - datetime.timedelta(days=8))  # 경보 나이 상한 밖
    assert run(at(2, 10)).alerts == {"webhook": 1}
    assert "[웹훅] 넘기기 대기(1분 넘음) 1건" in notes(report.NOTIFY_MORNING_REPORT)[0].message
    assert run(at(2, 10, 1)).alerts == {"webhook": 1}  # 30초짜리가 이제 1분을 넘었다
    assert run(at(2, 10, 2)).alerts == {}
    titles = [n.title for n in notes(report.NOTIFY_WEBHOOK_PENDING)]
    assert titles == ["채널톡 웹훅 넘기기 대기 1건", "채널톡 웹훅 넘기기 대기 1건"]


def test_missing_inbound_alarm_only_where_webhooks_arrive(app, monkeypatch, caplog):
    admin()
    for chat, log_id in (("uc-1", 1), ("uc-2", 2)):
        inbound(log_id, entity(f"m-{chat}", at(2, 10), text="첫 글", chat=chat))
    api = {chat: [derived(f"m-{chat}", at(2, 10), chat=chat, text="첫 글"),
                  derived(f"late-{chat}", at(2, 10, 10), chat=chat, text="웹훅이 빠뜨린 글")]
           for chat in ("uc-1", "uc-2")}
    caplog.set_level("WARNING")
    staging = run(at(2, 11), reader=FakeReader([chat_snap("uc-1", at(2, 10, 10))], api), watch=False)
    assert staging.outcome == loop.OUTCOME_OK and not notes(report.NOTIFY_INBOUND_MISSING)
    assert "수신 기록에 없는" not in caplog.text  # 웹훅이 없는 환경은 누락을 찾지도 않는다(R5-10)
    assert msg_row("late-uc-1", chat="uc-1").source == "openapi"  # 보정은 그대로 돈다
    assert "수신 누락 감시 꺼짐" in notes(report.NOTIFY_MORNING_REPORT)[0].message
    production = run(at(2, 11, 15), reader=FakeReader([chat_snap("uc-2", at(2, 10, 10))], api), watch=True)
    assert production.alerts == {"inbound": 1}
    (alarm,) = notes(report.NOTIFY_INBOUND_MISSING)
    assert "uc-2" in alarm.message and "웹훅이 빠뜨린" not in alarm.message
    assert run(at(2, 11, 30), reader=FakeReader([chat_snap("uc-2", at(2, 10, 20))], api), watch=True).alerts == {}

    runner = load_runner()  # 환경 판정은 저장소의 resolve_environment(FOMS_ENV → Railway 프로젝트 이름)
    monkeypatch.delenv("FOMS_ENV", raising=False)
    monkeypatch.setenv("RAILWAY_PROJECT_NAME", "FOMS-DEV")
    assert runner.loop_config().watch_missing_inbound is False
    monkeypatch.setenv("RAILWAY_PROJECT_NAME", "FOMS-PRODUCTION")
    assert runner.loop_config().watch_missing_inbound is True


def test_pass_completes_without_open_api_keys(app, monkeypatch):
    for brand in ("LAHOM", "HAUD"):
        monkeypatch.delenv(f"CHANNEL_OPENAPI_KEY_{brand}", raising=False)
        monkeypatch.delenv(f"CHANNEL_OPENAPI_SECRET_{brand}", raising=False)
    admin()
    waiting_customer()
    result = loop.run_pass(db_session, now=at(2, 9, 30), is_business_day=weekdays_only)  # 기본 읽기 도우미
    assert result.outcome == loop.OUTCOME_OK and result.report_sent
    assert {check.status for check in result.checks.values()} == {loop.CHECK_NOT_CONFIGURED}
    assert result.needs_reply == {"LAHOM": 1, "HAUD": 0}
    assert "라홈 키 없음(웹훅 기록만으로 셈)" in notes(report.NOTIFY_MORNING_REPORT)[0].message


# ── 채널톡 보정: 시간 상한 · 오래된 것부터 · 다음 바퀴가 잇는다 ──────────


def test_reconcile_is_budgeted_oldest_first_and_the_next_pass_resumes(app):
    ticks = [0.0]
    chats = [chat_snap("uc-b", at(2, 9, 20)), chat_snap("uc-a", at(2, 9, 10)), chat_snap("uc-c", at(2, 9, 30)),
             chat_snap("uc-x", at(2, 9, 5), state="closed")]
    messages = {c: [derived(f"m-{c}", at(2, 9), chat=c, text="합성 문의")] for c in ("uc-a", "uc-b", "uc-c")}
    reader = FakeReader(chats, messages, on_read=lambda _chat: ticks.__setitem__(0, ticks[0] + 1.0))

    def one(now):
        return run(now, reader=reader, clock=lambda: ticks[0], budget=2.0).checks["LAHOM"]  # 브랜드마다 1초

    def reads():
        return [call[2] for call in reader.calls if call[0] == "read"]

    first = one(at(2, 10))
    assert (first.status, first.done, reads()) == (loop.CHECK_PARTIAL, 2, ["uc-a"])  # 닫힌 상담은 읽지 않는다
    assert chat_row("uc-x").chat_state == "closed"
    second = one(at(2, 10, 15))
    windows = [call[2] for call in reader.calls if call[:2] == ("list", "LAHOM")]
    assert windows[1] == cr.aware_utc(at(2, 9, 10)) - loop.RECONCILE_OVERLAP  # 반영한 마지막 updatedAt 에서
    assert (second.status, reads()) == (loop.CHECK_PARTIAL, ["uc-a", "uc-b"])
    third = one(at(2, 10, 30))
    assert (third.status, reads(), message_count()) == (loop.CHECK_OK, ["uc-a", "uc-b", "uc-c"], 3)


def test_a_failed_chat_read_stops_the_brand_so_the_next_pass_retries_it(app):
    # 잠깐 오류 뒤 더 새 상담을 맞추면 창 시작이 실패한 상담을 넘어가 영영 안 본다 — 그 바퀴 보정을 멈춘다(R5-1)
    chats = [chat_snap("uc-a", at(2, 9, 10)), chat_snap("uc-b", at(2, 9, 20)), chat_snap("uc-c", at(2, 9, 30))]
    messages = {c: [derived(f"m-{c}", at(2, 9), chat=c, text="합성 문의")] for c in ("uc-a", "uc-b", "uc-c")}
    reader = FakeReader(chats, messages, errors={"uc-a": [cr.ChannelReadError("http_503", status=503)]})
    first = run(at(2, 10), reader=reader).checks["LAHOM"]
    assert (first.status, first.done, first.errors, message_count()) == (loop.CHECK_ERROR, 0, 1, 0)
    second = run(at(2, 10, 15), reader=reader).checks["LAHOM"]
    assert (second.status, second.done, message_count()) == (loop.CHECK_OK, 3, 3)
    assert [call[2] for call in reader.calls if call[0] == "read"] == ["uc-a", "uc-a", "uc-b", "uc-c"]


def test_a_deleted_chat_is_skipped_and_the_rest_reconciled(app):
    chats = [chat_snap("uc-d", at(2, 11)), chat_snap("uc-e", at(2, 11, 5))]
    reader = FakeReader(chats, {"uc-e": [derived("m-uc-e", at(2, 11, 5), chat="uc-e", text="합성 문의")]},
                        errors={"uc-d": [cr.ChannelReadError("http_404", status=404)]})
    check = run(at(2, 11, 30), reader=reader).checks["LAHOM"]
    assert (check.status, check.done, check.errors, message_count()) == (loop.CHECK_OK, 2, 1, 1)
    assert chat_row("uc-d").chat_state == "opened"  # 상태만 반영 — 다음 바퀴 창 시작이 넘어간다


# ── 러너 ────────────────────────────────────────────────────────────────


def test_runner_beats_after_a_pass_and_writes_nothing_after_term(app, monkeypatch):
    runner = load_runner()
    stop, calls, beats = loop.StopFlag(), [], []

    def fake_pass(_stop, _config):
        calls.append(1)
        if len(calls) == 2:
            stop.set()
            return {"outcome": loop.OUTCOME_STOPPED}
        return {"outcome": loop.OUTCOME_OK, "ingested": 2, "needs_reply": 1, "chat_id": "uc-1"}

    real_emit = runner.emit_heartbeat
    monkeypatch.setattr(runner, "_pass_once", fake_pass)
    monkeypatch.setattr(stop, "sleep", lambda seconds: False)
    monkeypatch.setattr(runner, "emit_heartbeat", lambda *a, **k: beats.append(k["metadata"]) or real_emit(*a, **k))
    assert runner._run_loop(900, False, stop) == 0
    assert len(calls) == 2 and len(beats) == 1  # TERM 뒤 바퀴는 하트비트도 쓰지 않았다
    meta = beats[0]
    assert set(meta) == {"interval_seconds", "outcome", "ingested", "reconciled", "needs_reply", "alerts",
                         "report_sent", report.HEARTBEAT_LAST_SUCCESS_KEY, "daily_cap_usd"}  # 상담 id 는 싣지 않는다
    assert (meta["interval_seconds"], meta["outcome"], meta["ingested"]) == (900, "ok", 2)
    assert db_session.get(SideEffectWorkerHeartbeat, "CS_LOOP").metadata_json == meta
    assert report.read_last_success(db_session) is not None


def test_runner_wakes_for_the_morning_report_and_retries_soon_when_not_leader():
    runner = load_runner()
    assert runner.next_sleep_seconds(900, loop.OUTCOME_OK, at(2, 7, 50)) == 605.0  # 8시 + 여유 5초
    assert runner.next_sleep_seconds(900, loop.OUTCOME_OK, at(2, 9)) == 900.0
    assert runner.next_sleep_seconds(900, loop.OUTCOME_NOT_LEADER, at(2, 9)) == 60.0
    assert report.seconds_until_report(at(2, 8)) == 86400.0
    # 7:58 에 시작해 8시를 넘겨 끝난 바퀴는 보고를 안 냈다 — 곧 다시 돈다(끝난 때로 재면 15분 밀림, R5-4)
    assert runner.next_sleep_seconds(900, loop.OUTCOME_OK, at(2, 8, 1), started=at(2, 7, 58)) == 1.0
    assert runner.next_sleep_seconds(900, loop.OUTCOME_OK, at(2, 8, 1), started=at(2, 8)) == 900.0


def test_runner_drops_frame_locals_from_sentry_events():
    runner = load_runner()
    event = {"exception": {"values": [{"stacktrace": {"frames": [{"function": "f", "vars": {"payload": "합성"}}]}}]},
             "threads": {"values": [{"stacktrace": {"frames": [{"vars": {"x": "1"}}]}}]}}
    frames = runner.drop_frame_locals(event)["exception"]["values"][0]["stacktrace"]["frames"]
    assert frames == [{"function": "f"}]  # 지역 변수만 빠지고 스택은 남는다(R5-2)
    assert "vars" not in event["threads"]["values"][0]["stacktrace"]["frames"][0]
    assert runner.drop_frame_locals({"exception": "꼴이 다름"}) == {"exception": "꼴이 다름"}  # 꼴이 달라도 던지지 않는다

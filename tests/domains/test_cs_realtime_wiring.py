"""빠른 길(플랜 C10-1) 배선 — 15분 바퀴와의 관계 · 켜짐 조건 · 감독자 자식 · 러너 하트비트 · 패널 새 칸 · 마이그레이션 꼴.

완료 기준 ①~⑩ 은 ``test_cs_realtime.py``. 여기서는 그 둘레: 빠른 길이 켜지면 15분 바퀴는 초안을 쓰지 않고(보정 · 아침 보고만)
꺼지면 예전 그대로 · 켜짐 조건이 하나라도 아니면 차례는 스위치만 읽고 일 0 · 같은 env 로 자식 하나 더 · 하트비트 칸 · 패널 칸
범위(조용 10~120 · 최대 20~300 · 시간 상한 잠금 풂 · 학습 돈 상한은 WORKER 천장과 따로) · ``csagent_02`` 가 모델과 같은 꼴.
"""

from __future__ import annotations

import datetime
import functools
import importlib.util
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, func, select

from db import db_session
from foms.services.cs_agent import brain, drafting, loop, realtime, turns
from foms.services.cs_agent import brain_spend as bs
from foms.services.cs_agent import settings as st
from foms.services.datetime_kst import now_utc_naive
from foms.services.sidefx_worker import WORKER_KIND_CS_REALTIME, WORKER_KIND_SPECS
from models import CsAgentMessage, CsAgentTurn, SideEffectWorkerHeartbeat, SystemSetting, User
from tests.domains.test_cs_drafting import FakeBrain, FakePoster, channel, customer  # noqa: F401
from tests.domains.test_cs_realtime import Talk, sec, switch_on, tick
from tests.support.cs_agent_fakes import FakeClock, at, keys, make_reader, weekdays_only  # noqa: F401
from tests.support.worker_jobs import jobs

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "csagent_02_turn_claim_owner.py"
RUNNER = ROOT / "scripts" / "maintenance" / "run_cs_realtime.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def turn_count():
    return db_session.scalar(select(func.count()).select_from(CsAgentTurn.__table__))


def loop_pass(channel, now):
    return loop.run_pass(db_session, config=loop.LoopConfig(), stop=loop.StopFlag(),
                         reader=make_reader(channel, FakeClock()), now=now, clock=lambda: 0.0,
                         is_business_day=weekdays_only)


# ── 15분 바퀴와의 관계 ───────────────────────────────────────────────────
def test_with_the_fast_path_on_the_quarter_hour_pass_only_reconciles_and_reports(channel, monkeypatch):
    customer(channel)
    switch_on()
    monkeypatch.setattr(loop, "run_drafting", lambda *a, **k: pytest.fail("빠른 길이 켜졌는데 15분 바퀴가 초안을 돌렸다"))
    result = loop_pass(channel, at(2, 9))
    assert (result.outcome, result.drafting, result.summary()["drafting"]) == ("ok", None, "realtime")
    assert result.report_sent is True and turn_count() == 0  # 아침 보고는 그대로 돈다


def test_with_the_fast_path_off_the_quarter_hour_pass_drafts_as_before(channel, monkeypatch):
    customer(channel)
    switch_on(realtime_enabled=False)
    brain_fn = FakeBrain()
    monkeypatch.setattr(loop, "run_drafting", functools.partial(drafting.run_drafting, brain=brain_fn,
                                                                poster=FakePoster()))
    result = loop_pass(channel, at(2, 9))
    assert (result.drafting.stored, len(brain_fn.requests)) == (1, 1) and brain_fn.requests[0].realtime is False
    row = db_session.scalars(select(CsAgentTurn)).one()
    assert row.claim_owner.startswith("pass:")  # 15분 바퀴 선점도 주인 · 만료(예전 20분)를 남긴다
    assert row.claim_expires_at - row.updated_at == drafting.STALE_CLAIM_AFTER
    assert tick(channel, sec(30), realtime.TickMemory()).outcome == "idle"  # 빠른 길은 꺼져 일 0


@pytest.mark.parametrize("switch,settings", [
    ({"loop": "on", "draft": "store"}, {"realtime_enabled": False}),  # 빠른 길 스위치 끔(처음 값)
    ({"loop": "on", "draft": "off"}, {"realtime_enabled": True}),  # 초안 끔
    ({"loop": "off", "draft": "memo"}, {"realtime_enabled": True}),  # 비상 정지
    ({"loop": "on", "draft": "store"}, None),  # 설정 줄 없음 — 처음 값(끔)
])
def test_any_switch_off_makes_the_tick_read_only(channel, switch, settings):
    db_session.merge(SystemSetting(setting_key=turns.SWITCH_KEY, setting_value=switch))
    if settings is not None:
        db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, setting_value={**st.DEFAULTS, **settings}))
    db_session.commit()
    Talk(channel).say("m-1", sec(0))
    result = tick(channel, sec(30), realtime.TickMemory(), brain_fn=FakeBrain(max_calls=0))
    assert (result.outcome, result.examined) == ("idle", 0)
    assert turn_count() == 0 and db_session.scalar(select(func.count()).select_from(CsAgentMessage.__table__)) == 0
    assert channel.calls == []


def test_a_tick_that_is_not_leader_is_retried_on_the_next_tick(channel):
    switch_on()
    Talk(channel).say("m-1", sec(0))
    memory = realtime.TickMemory()
    with loop.leader_lock(db_session.get_bind(), realtime.REALTIME_LOCK_KEY):  # 재배포 겹침 — 옛 컨테이너가 쥐고 있다
        assert tick(channel, sec(20), memory).outcome == "not_leader"
    assert tick(channel, sec(25), memory).outcome == "ok" and turn_count() == 1  # 60초가 아니라 다음 차례(5초)에


# ── 감독자 자식 · 하트비트 ───────────────────────────────────────────────
def test_the_fast_path_child_starts_with_the_same_env_as_the_loop():
    assert "cs_realtime" not in [j.name for j in jobs({})]
    assert "cs_realtime" not in [j.name for j in jobs({"FOMS_CS_LOOP_ENABLED": "0"})]
    listed = jobs({"FOMS_CS_LOOP_ENABLED": "1"})
    child = next(j for j in listed if j.name == "cs_realtime")
    assert child.deferred and listed[-1].name == "rq_worker"
    assert child.argv[1:] == ("scripts/maintenance/run_cs_realtime.py", "--loop", "--json")
    assert [j.name for j in listed].index("cs_loop") < [j.name for j in listed].index("cs_realtime")


def test_the_runner_declares_a_registered_kind_and_beats_without_customer_data(app, monkeypatch):
    runner = load(RUNNER, "run_cs_realtime_ut")
    assert runner.HEARTBEAT_WORKER_KIND == WORKER_KIND_CS_REALTIME and WORKER_KIND_CS_REALTIME in WORKER_KIND_SPECS
    assert realtime.REALTIME_LOCK_KEY != loop.LEADER_LOCK_KEY
    totals: dict = {}
    for summary in ({"outcome": "ok", "ingested": 2, "picked": 1, "drafting": {"brain_calls": 1}}, None,
                    {"outcome": "idle", "customer_name": "합성손님"}):
        runner._add(totals, summary)
    meta = runner._heartbeat_metadata(totals)
    assert meta == {"interval_seconds": runner.HEARTBEAT_SECONDS, "outcome": "idle", "ticks": 3, "ingested": 2,
                    "picked": 1, "brain_calls": 1}
    stop, beats = loop.StopFlag(), []
    monkeypatch.setattr(runner, "_tick", lambda _stop, _memory, _gate=None: {"outcome": "ok"})
    monkeypatch.setattr(runner, "emit_heartbeat", lambda *a, **k: beats.append(k["metadata"]) or stop.set())
    assert runner._run_loop(False, stop) == 0 and [beat["ticks"] for beat in beats] == [1]
    monkeypatch.setattr(runner, "_tick", lambda the_stop, _memory, _gate=None: the_stop.set())  # TERM 뒤엔 하트비트도 안 쓴다
    assert runner._run_loop(False, loop.StopFlag()) == 0 and len(beats) == 1


# ── 패널 새 칸 ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("name,good,bad", [
    ("quiet_wait_s", (10, 15, 120), (9, 121, 15.0, "15", True)),
    ("max_wait_s", (20, 60, 300), (19, 301, None)),
    ("realtime_timeout_s", (20, 45, 60), (19, 61)),
    ("realtime_enabled", (True, False), ("true", 1, None)),
    ("learning_cap_usd_panel", (None, "", "0", "12.5"), ("-1", "1.234", True)),
])
def test_new_panel_fields_check_their_ranges(name, good, bad):
    field = st.FIELD_BY_NAME[name]
    assert field.locked == (name == "learning_cap_usd_panel")  # 학습 돈 상한은 C10-7 까지 잠김(R13-12)
    assert all(st.check_value(field, value)[0] for value in good), name
    assert not any(st.check_value(field, value)[0] for value in bad), name


def test_the_learning_cap_starts_empty_and_stays_locked_until_c10_7(app, monkeypatch):
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "5")
    actor = User(username="cs-realtime-admin", password="x", role="ADMIN", name="합성 관리자", is_active=True)
    db_session.add(actor)
    db_session.commit()
    assert st.DEFAULTS["learning_cap_usd_panel"] is None and st.value_label("learning_cap_usd_panel", None) == "비움"
    db_session.merge(SideEffectWorkerHeartbeat(worker_kind="CS_LOOP", last_heartbeat_at=now_utc_naive(),
                                               metadata_json={"outcome": "ok", bs.HEARTBEAT_CAP_KEY: "5"}))
    db_session.commit()
    with pytest.raises(st.SettingsLockedError) as caught:  # 총괄 결정(R13-12) — 학습 길(C10-7)이 생길 때까지 잠김
        st.save_settings(db_session, {"learning_cap_usd_panel": "9", "quiet_wait_s": 30},
                         expected_version=0, actor_user_id=actor.id)
    assert caught.value.fields == ("learning_cap_usd_panel",)
    db_session.rollback()
    saved = st.save_settings(db_session, {"quiet_wait_s": 30}, expected_version=0, actor_user_id=actor.id)
    db_session.commit()
    cfg = st.read_settings(db_session)
    assert (cfg.get("learning_cap_usd_panel"), cfg.get("quiet_wait_s"), saved.changed) == (None, 30, ("quiet_wait_s",))
    with pytest.raises(st.SettingsInvalidError):  # 하루 상한 화면 값은 여전히 WORKER 천장 아래만
        st.save_settings(db_session, {"daily_cap_usd_panel": "9"}, expected_version=1, actor_user_id=actor.id)


# ── 마이그레이션 꼴 ──────────────────────────────────────────────────────
def test_csagent_02_chains_onto_csagent_01_and_matches_the_model():
    module = load(MIGRATION, "csagent_02_mig_unit")
    assert (module.revision, module.down_revision) == ("csagent_02", "csagent_01")
    source = MIGRATION.read_text(encoding="utf-8")
    assert "import models" not in source and "from models" not in source  # 상수 동결
    assert module.NEW_STATES == turns.STATES and set(module.OLD_STATES) < set(module.NEW_STATES)
    (check,) = [c for c in CsAgentTurn.__table__.constraints
                if isinstance(c, CheckConstraint) and c.name == module.CHECK_NAME]
    assert str(check.sqltext) == module._state_check(module.NEW_STATES)  # DDL 과 모델이 같은 글자
    columns = CsAgentTurn.__table__.c
    assert (columns.claim_owner.type.length, columns.claim_owner.nullable) == (64, True)
    assert type(columns.claim_expires_at.type).__name__ == "DateTime" and columns.claim_expires_at.nullable
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1 and "csagent_02" in {rev.revision for rev in script.walk_revisions("base", heads[0])}


def test_the_downgrade_maps_new_states_back_before_restoring_the_old_check():
    source = MIGRATION.read_text(encoding="utf-8")
    body = source.split("def downgrade", 1)[1]
    assert body.index("UPDATE") < body.index("drop_constraint") < body.index("create_check_constraint")
    assert body.index("create_check_constraint") < body.index("drop_column")
    assert datetime.timedelta(seconds=90) == realtime.CLAIM_TTL  # 처음 값 90초(시간 상한 45초 + 여유)

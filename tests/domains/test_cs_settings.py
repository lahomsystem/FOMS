"""관리 패널 설정(설계서 16.1 · 단계 1) — 처음 값 = 오늘 상수 · 칸 검사 · 통째 거절 · 잠긴 칸(다음 단계) · 버전 대조 ·
칸마다 처음 값 · 저장 때 모르는 칸 · 잠긴 칸을 남김 · 틀린 칸 고침 기록 · WORKER 가 하트비트에 남긴 하루 상한이 천장.

DB 는 SQLite(다른 test_cs_* 와 같다). 값은 모델 id · 숫자 · 코드뿐이라 손님 글이 없다.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import pytest

from db import db_session
from foms.services.cs_agent import brain, drafting
from foms.services.cs_agent import brain_prompt as bp
from foms.services.cs_agent import brain_spend as bs
from foms.services.cs_agent import settings as st
from foms.services.datetime_kst import now_utc_naive
from models import SecurityLog, SideEffectWorkerHeartbeat, SystemSetting, SystemSettingReceipt, User
from tests.domains.test_cs_brain import KNOWLEDGE, NOW

#: 잠긴 칸 — 빠른 길(C10-1)이 생겨 시간 상한(realtime_timeout_s)은 잠금을 풀었다(설계서 17.1 · 원장 V10-9).
LOCKED = {"intent_model", "intent_effort", "intent_max_tokens", "realtime_retries",
          "max_brain_calls_per_pass", "max_wait_business_days"}


@pytest.fixture
def admin_id(app, monkeypatch):
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "5")
    user = User(username="cs-settings-admin", password="x", role="ADMIN", name="설정 관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user.id


def save(values, *, version=0, actor):
    result = st.save_settings(db_session, values, expected_version=version, actor_user_id=actor)
    db_session.commit()
    return result


def receipts():
    return db_session.query(SystemSettingReceipt).filter_by(policy_id=st.POLICY_ID).order_by(
        SystemSettingReceipt.id).all()


def put_row(value, version=4):
    db_session.add(SystemSetting(setting_key=st.SETTINGS_KEY, setting_value=value, version=version))
    db_session.commit()


def stored():
    db_session.expire_all()
    return db_session.get(SystemSetting, st.SETTINGS_KEY).setting_value


def worker_beat(cap):
    """감시 루프 하트비트(WORKER 가 남긴 env 하루 상한 칸 — ``cap`` 이 ``...`` 이면 칸 없음)."""
    meta = {"interval_seconds": 900, "outcome": "ok"}
    if cap is not ...:
        meta[bs.HEARTBEAT_CAP_KEY] = cap
    db_session.merge(SideEffectWorkerHeartbeat(worker_kind="CS_LOOP", last_heartbeat_at=now_utc_naive(),
                                               metadata_json=meta))
    db_session.commit()


# ── 처음 값 = 오늘 상수 ──────────────────────────────────────────────────
def test_defaults_equal_todays_constants_and_no_row_reads_them(app):
    expected = {
        "draft_model": brain.MODEL, "intent_model": brain.MODEL,
        "draft_effort": brain.EFFORTS[bp.PURPOSE_DRAFT], "intent_effort": brain.EFFORTS[bp.PURPOSE_INTENT],
        "draft_max_tokens": brain.MAX_TOKENS[bp.PURPOSE_DRAFT], "intent_max_tokens": brain.MAX_TOKENS[bp.PURPOSE_INTENT],
        "realtime_timeout_s": brain.REALTIME_TIMEOUT_SECONDS, "batch_timeout_s": brain.BATCH_TIMEOUT_SECONDS,
        "realtime_retries": brain.REALTIME_RETRIES, "cache_policy": st.CACHE_DAYTIME,
        "cache_ttl": bp.CACHE_CONTROL_DAY["ttl"], "fallback_enabled": True,
        "daily_cap_usd_panel": None, "learning_cap_usd_panel": None,
        "max_brain_calls_per_pass": drafting.MAX_BRAIN_CALLS, "max_wait_business_days": drafting.MAX_WAIT_BUSINESS_DAYS,
        "realtime_enabled": False, "quiet_wait_s": 15, "max_wait_s": 60,  # 빠른 길(C10-1) — 처음 끔 · D65 15초
    }
    assert st.DEFAULTS == expected and list(st.DEFAULTS) == [f.name for f in st.FIELDS]
    assert st.LOCKED_FIELDS == LOCKED  # 승인 밖(고르기) · 아직 길이 없는 칸(의도 고르기 · 실시간)
    for field in st.FIELDS:  # 처음 값은 자기 칸 검사를 지난다
        assert st.check_value(field, field.default) == (True, field.default), field.name
    cfg = st.read_settings(db_session)
    assert (dict(cfg.values), cfg.version, cfg.fallback_fields) == (expected, 0, ())
    assert db_session.get(SystemSetting, st.SETTINGS_KEY) is None  # 읽기는 줄을 만들지 않는다


def test_only_the_three_verified_models_are_selectable(app):
    field = st.FIELD_BY_NAME["draft_model"]
    assert tuple(value for value, _label in field.choices) == bp.BRAIN_MODELS == (
        "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")
    assert all(model in bp.PRICES for model in bp.BRAIN_MODELS)
    for locked in ("claude-fable-5-1", "claude-opus-5", "claude-opus-4-8", "CLAUDE-OPUS-5-5", ""):
        assert st.check_value(field, locked) == (False, None)
    assert bp.SERVER_FALLBACK_MODELS == {"claude-opus-5-5", "claude-sonnet-5-5"}  # Haiku 5.5 는 대체가 없다


# ── 통째 거절 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("name,value", [
    ("draft_model", "claude-fable-5-1"), ("intent_model", None), ("draft_effort", "xhigh"), ("intent_effort", "LOW"),
    ("draft_max_tokens", 1999), ("draft_max_tokens", 32001), ("draft_max_tokens", 16000.5),
    ("draft_max_tokens", "16000"), ("intent_max_tokens", True), ("realtime_timeout_s", 19),
    ("realtime_timeout_s", 61), ("batch_timeout_s", 29), ("batch_timeout_s", 121), ("realtime_retries", 2),
    ("realtime_retries", -1), ("cache_policy", "sometimes"), ("cache_ttl", "24h"), ("cache_ttl", "1H"),
    ("fallback_enabled", "true"), ("fallback_enabled", 1),
    ("daily_cap_usd_panel", -1), ("daily_cap_usd_panel", "abc"), ("daily_cap_usd_panel", "1.234"),
    ("daily_cap_usd_panel", "NaN"), ("daily_cap_usd_panel", True), ("daily_cap_usd_panel", "10000.01"),
    ("max_brain_calls_per_pass", 0), ("max_brain_calls_per_pass", 21), ("max_wait_business_days", 3),
    ("max_wait_business_days", True), ("max_wait_business_days", "1"), ("temperature", 0.2),
])
def test_one_bad_field_rejects_the_whole_save_and_names_only_the_field(admin_id, name, value):
    values = {"draft_effort": "medium", name: value}  # 맞는 칸이 섞여 있어도 통째로 거절
    with pytest.raises(st.SettingsInvalidError) as excinfo:
        save(values, actor=admin_id)
    assert excinfo.value.fields == (name,) and not isinstance(excinfo.value, st.SettingsLockedError)
    if isinstance(value, str) and value:
        assert value not in str(excinfo.value)  # 값은 오류 글에 싣지 않는다
    db_session.rollback()
    assert db_session.get(SystemSetting, st.SETTINGS_KEY) is None and receipts() == []


def test_non_mapping_values_and_odd_names_are_refused(admin_id):
    for values in (None, ["draft_model"], "draft_model"):
        with pytest.raises(st.SettingsInvalidError) as excinfo:
            save(values, actor=admin_id)
        assert excinfo.value.fields == ("values",)
    with pytest.raises(st.SettingsInvalidError) as excinfo:
        save({"<script>": 1, 7: 1}, actor=admin_id)
    assert excinfo.value.fields == ("(이름 꼴 아님)",)


# ── 잠긴 칸(다음 단계) ───────────────────────────────────────────────────
@pytest.mark.parametrize("name,value", [
    ("intent_model", bp.MODEL_HAIKU), ("intent_effort", "high"), ("intent_max_tokens", 4000),
    ("realtime_retries", 1), ("max_brain_calls_per_pass", 1),
    ("max_wait_business_days", 2),
])
def test_changing_a_locked_field_refuses_the_whole_save(admin_id, name, value):
    with pytest.raises(st.SettingsLockedError) as excinfo:
        save({"draft_effort": "max", name: value}, actor=admin_id)
    assert excinfo.value.fields == (name,) and "다음 단계" in str(excinfo.value)
    db_session.rollback()
    assert db_session.get(SystemSetting, st.SETTINGS_KEY) is None and receipts() == []  # 맞는 칸도 저장되지 않았다


def test_a_locked_field_sent_with_its_current_value_is_not_a_change(admin_id):
    result = save({"draft_effort": "max", "max_wait_business_days": 1.0, "realtime_retries": 0}, actor=admin_id)
    assert result.changed == ("draft_effort",)  # 음성 대조: 값이 그대로면 잠긴 칸을 보내도 받는다
    assert set(stored()) == set(st.DEFAULTS) - LOCKED  # 잠긴 칸은 문서에 새로 쓰지 않는다


def test_locked_values_in_the_row_are_ignored_on_read_and_kept_on_save(admin_id):
    put_row({**st.DEFAULTS, "max_brain_calls_per_pass": 1, "intent_model": bp.MODEL_HAIKU,
             "future_knob": {"합성": [1, 2]}})
    cfg = st.read_settings(db_session)
    assert (cfg.get("max_brain_calls_per_pass"), cfg.model_for(bp.PURPOSE_INTENT)) == (10, brain.MODEL)  # 늘 처음 값
    assert cfg.fallback_fields == ()
    save({"draft_effort": "max"}, version=4, actor=admin_id)
    row = stored()
    assert (row["max_brain_calls_per_pass"], row["intent_model"], row["future_knob"]) == (1, bp.MODEL_HAIKU,
                                                                                          {"합성": [1, 2]})
    assert row["draft_effort"] == "max"  # 저장한 칸은 바뀌고, 뒤 단계 칸은 그대로 이어 붙었다


# ── 쓰기 · 버전 · 기록 ───────────────────────────────────────────────────
def test_save_merges_bumps_the_version_and_leaves_a_receipt_and_audit(admin_id):
    first = save({"draft_model": bp.MODEL_HAIKU, "cache_policy": "off"}, actor=admin_id)
    assert (first.version, first.changed) == (1, ("draft_model", "cache_policy"))
    cfg = st.read_settings(db_session)
    assert cfg.version == 1 and cfg.model_for(bp.PURPOSE_DRAFT) == "claude-haiku-5-5"
    assert cfg.get("cache_policy") == "off" and cfg.get("draft_effort") == "high"  # 나머지 그대로
    [receipt] = receipts()
    assert (receipt.resulting_version, receipt.actor_user_id, receipt.setting_key) == (1, admin_id, st.SETTINGS_KEY)
    data = receipt.response_body["data"]
    assert data["changed"] == {"draft_model": {"from": brain.MODEL, "to": bp.MODEL_HAIKU},
                               "cache_policy": {"from": "daytime", "to": "off"}}
    assert data["values"] == stored()
    log = db_session.query(SecurityLog).filter_by(action="CS_AGENT_SETTINGS_UPDATE").one()
    assert log.user_id == admin_id and "fields=draft_model,cache_policy" in log.message
    second = save({"fallback_enabled": False}, version=1, actor=admin_id)
    assert (second.version, second.changed) == (2, ("fallback_enabled",))


def test_a_stale_version_is_a_conflict_and_the_same_values_are_no_change(admin_id):
    save({"draft_effort": "max"}, actor=admin_id)
    with pytest.raises(st.SettingsConflictError) as excinfo:  # 다른 사람이 먼저 저장했다(읽은 버전 0)
        save({"draft_effort": "low"}, version=0, actor=admin_id)
    assert excinfo.value.current_version == 1
    db_session.rollback()
    with pytest.raises(st.SettingsNoChangeError):
        save({"draft_effort": "max"}, version=1, actor=admin_id)
    db_session.rollback()
    assert len(receipts()) == 1 and st.read_settings(db_session).get("draft_effort") == "max"
    assert save({"draft_effort": "low"}, version=1, actor=admin_id).version == 2  # 음성 대조: 맞는 버전이면 저장


def test_wrong_stored_fields_are_recorded_as_repaired(admin_id):
    put_row({**{n: v for n, v in st.DEFAULTS.items() if n not in LOCKED}, "draft_model": "claude-fable-5-1",
             "batch_timeout_s": 9999})
    only_repair = save({}, version=4, actor=admin_id)  # 받은 칸이 없어도 틀린 칸을 고치는 것은 바뀜이다
    assert only_repair.changed == ("draft_model", "batch_timeout_s")
    changed = receipts()[-1].response_body["data"]["changed"]
    assert changed["draft_model"] == {"from": "claude-fable-5-1", "to": brain.MODEL, "repaired": True}
    assert changed["batch_timeout_s"] == {"from": 9999, "to": 90, "repaired": True}
    assert (stored()["draft_model"], st.read_settings(db_session).fallback_fields) == (brain.MODEL, ())
    db_session.get(SystemSetting, st.SETTINGS_KEY).setting_value = ["합성"]  # 문서가 아예 틀림 — 모든 칸을 고친다
    db_session.commit()
    result = save({"draft_effort": "max"}, version=5, actor=admin_id)
    assert set(result.changed) == set(st.DEFAULTS) - LOCKED
    assert receipts()[-1].response_body["data"]["changed"]["draft_effort"] == {"from": None, "to": "max",
                                                                               "repaired": True}


# ── 읽기: 칸마다 처음 값 ─────────────────────────────────────────────────
def test_read_falls_back_field_by_field_and_logs_names_only(app, caplog):
    row = {**st.DEFAULTS, "draft_model": "claude-fable-5-1", "draft_effort": "max", "realtime_retries": True}
    del row["cache_policy"]
    put_row(row)
    caplog.set_level(logging.WARNING, logger=st.__name__)
    cfg = st.read_settings(db_session)
    assert cfg.version == 4 and cfg.get("draft_effort") == "max"  # 맞는 칸은 그대로
    assert (cfg.get("draft_model"), cfg.get("cache_policy"), cfg.get("realtime_retries")) == (brain.MODEL, "daytime", 0)
    assert cfg.fallback_fields == ("draft_model", "cache_policy")  # 잠긴 칸은 늘 처음 값이라 세지 않는다
    assert "draft_model" in caplog.text and "claude-fable-5-1" not in caplog.text
    caplog.clear()
    st.read_settings(db_session, log=False)
    assert "[CS 설정]" not in caplog.text  # 두뇌 · 준비 확인 · 화면은 남기지 않는다(초안 바퀴가 바퀴마다 한 번)
    db_session.get(SystemSetting, st.SETTINGS_KEY).setting_value = ["합성"]
    db_session.commit()
    assert dict(st.read_settings(db_session).values) == st.DEFAULTS  # 꼴이 아예 틀리면 모두 처음 값


# ── 돈 천장: WORKER 가 하트비트에 남긴 값 ────────────────────────────────
def test_the_worker_cap_from_the_heartbeat_is_the_ceiling_not_the_web_env(admin_id, monkeypatch):
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "1")  # 이 프로세스(web) env 는 보지 않는다(음성 대조)
    worker_beat("5")
    assert bs.worker_daily_cap(db_session).cap == Decimal("5")
    with pytest.raises(st.SettingsInvalidError) as excinfo:
        save({"daily_cap_usd_panel": "5.01"}, actor=admin_id)  # WORKER 5 보다 높다
    assert excinfo.value.fields == ("daily_cap_usd_panel",)
    db_session.rollback()
    save({"daily_cap_usd_panel": "3"}, actor=admin_id)  # web env 1 보다 높아도 WORKER 5 아래라 받는다
    cfg = st.read_settings(db_session)
    assert cfg.get("daily_cap_usd_panel") == "3.00" and cfg.daily_cap(Decimal("5")) == Decimal("3")
    assert cfg.daily_cap(Decimal("2")) == Decimal("2")  # WORKER env 를 나중에 낮추면 env 가 이긴다


@pytest.mark.parametrize("beat,expected", [
    ("no-heartbeat", "unknown"), (..., "unknown"), (None, "missing"), ("abc", "missing"),
], ids=["no-heartbeat", "no-cap-key", "worker-env-missing", "worker-env-broken"])
def test_an_unknown_worker_cap_only_limits_to_the_field_maximum(admin_id, beat, expected):
    if beat != "no-heartbeat":
        worker_beat(beat)
    state = bs.worker_daily_cap(db_session)
    assert state.cap is None and state.state == expected
    assert save({"daily_cap_usd_panel": "8"}, actor=admin_id).version == 1  # 칸의 최댓값(10,000)으로만 막는다
    with pytest.raises(st.SettingsInvalidError):
        save({"daily_cap_usd_panel": "10000.01"}, version=1, actor=admin_id)


def test_the_brain_still_cuts_with_its_own_env(admin_id, monkeypatch):
    save({"daily_cap_usd_panel": "3"}, actor=admin_id)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-placeholder")
    assert brain.check_ready("LAHOM", KNOWLEDGE, session=db_session, now=NOW) == Decimal("3")
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "2")
    assert brain.check_ready("LAHOM", KNOWLEDGE, session=db_session, now=NOW) == Decimal("2")  # env 가 천장
    save({"daily_cap_usd_panel": None}, version=1, actor=admin_id)
    assert brain.check_ready("LAHOM", KNOWLEDGE, session=db_session, now=NOW) == Decimal("2")  # 비우면 env 그대로


def test_the_runner_value_for_the_heartbeat():
    assert bs.heartbeat_cap_value({brain.DAILY_CAP_ENV: " 4.5 "}) == "4.5"
    assert bs.heartbeat_cap_value({}) is None and bs.heartbeat_cap_value({brain.DAILY_CAP_ENV: "-1"}) is None


def test_value_labels_for_the_history_table():
    assert st.value_label("draft_model", bp.MODEL_HAIKU) == "Haiku 5.5"
    assert st.value_label("fallback_enabled", False) == "끔" and st.value_label("daily_cap_usd_panel", None) == "env 그대로"
    assert st.value_label("draft_max_tokens", 16000) == "16,000 토큰" and st.value_label("max_wait_business_days", 0.5) \
        == "운영일 반나절"

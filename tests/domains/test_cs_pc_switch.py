"""PC 반복 비상 정지 읽기 길(``GET /api/cs-agent/pc-switch``, 사장님 결정 10-29) — 열쇠 env 없음 · 32자 미만 503 · 틀린
열쇠 401 · 맞는 열쇠면 ``stop`` 하나만 · DB 오류면 닫힌 쪽(``stop=true``) · 로그인 · CSRF 없이(기계 요청) · 다른 칸 없음 ·
IP 기준 분당 한도(쿠키를 갈아 끼워도 같은 묶음 — 넘으면 429) · 틀린 열쇠 경고는 분당 한 줄로 묶음(검수 R9).

손님 글이 없는 합성 값만 쓴다. 열쇠는 시험용 가짜 글이다.
"""

from __future__ import annotations

import logging

import pytest
from sqlalchemy.exc import OperationalError

from db import db_session
from foms.api import cs_agent_pc
from foms.services import rate_limit
from foms.services.cs_agent import loop, turns
from foms.services.datetime_kst import now_kst
from models import SystemSetting

PATH = "/api/cs-agent/pc-switch"
TOKEN = "synthetic-pc-switch-token-abcdefghij"  # 전화 꼴 숫자 없이(공개 저장소 R6-19) · 32자 넘음


def _reset_limits(app):
    for limiter in app.extensions.get("limiter", set()):
        limiter.reset()


@pytest.fixture(autouse=True)
def fresh_limits(app, monkeypatch):
    """IP 한도 · 경고 묶음은 프로세스에 남는다 — 시험마다 비운다."""
    monkeypatch.setattr(cs_agent_pc, "_WARNINGS", cs_agent_pc.LogBundle())
    _reset_limits(app)
    yield
    _reset_limits(app)


@pytest.fixture
def token_env(monkeypatch):
    monkeypatch.setenv(cs_agent_pc.TOKEN_ENV, TOKEN)


def ask(client, token=TOKEN, **kwargs):
    headers = {} if token is None else {cs_agent_pc.SWITCH_HEADER: token}
    return client.get(PATH, headers=headers, **kwargs)


def denied_lines(caplog):
    return [record.getMessage() for record in caplog.records if "CS_PC_SWITCH_DENIED" in record.getMessage()]


@pytest.mark.parametrize("value", [None, "", "   "], ids=["unset", "empty", "blank"])
def test_no_token_env_means_the_road_is_closed(client, monkeypatch, value):
    if value is None:
        monkeypatch.delenv(cs_agent_pc.TOKEN_ENV, raising=False)
    else:
        monkeypatch.setenv(cs_agent_pc.TOKEN_ENV, value)
    resp = ask(client)
    assert resp.status_code == 503 and resp.get_json() == {
        "success": False, "data": None, "error": "PC 스위치 길이 꺼져 있습니다."}


@pytest.mark.parametrize("length,status", [(31, 503), (32, 200)], ids=["31-chars", "32-chars"])
def test_a_token_env_shorter_than_32_characters_keeps_the_road_closed(client, monkeypatch, caplog, length, status):
    key = ("synthetic-pc-key-" * 3)[:length]
    monkeypatch.setenv(cs_agent_pc.TOKEN_ENV, f"  {key}  ")  # 앞뒤 빈칸은 길이에 들지 않는다
    caplog.set_level(logging.WARNING, logger=cs_agent_pc.__name__)
    resp = ask(client, key)  # 맞는 열쇠를 보내도
    assert resp.status_code == status
    if status == 503:  # 설정 미비 — 꺼진 길과 같은 답(열쇠가 있다는 것도 알리지 않는다), 서버 로그에만 남긴다
        assert resp.get_json() == {"success": False, "data": None, "error": "PC 스위치 길이 꺼져 있습니다."}
        assert "CS_PC_SWITCH_KEY_SHORT" in caplog.text and key not in caplog.text
    else:  # 음성 대조: 32자면 연다
        assert resp.get_json()["data"] == {"stop": False} and "CS_PC_SWITCH_KEY_SHORT" not in caplog.text


@pytest.mark.parametrize("given", [None, "", "wrong-token", TOKEN[:-1], TOKEN + "x", "töken-é"],
                         ids=["missing", "empty", "wrong", "short", "long", "non-ascii"])
def test_a_wrong_token_is_401_and_the_token_is_not_logged(client, token_env, caplog, given):
    caplog.set_level(logging.WARNING, logger=cs_agent_pc.__name__)
    resp = ask(client, given)
    assert resp.status_code == 401 and resp.get_json()["data"] is None and resp.get_json()["success"] is False
    assert "CS_PC_SWITCH_DENIED" in caplog.text and TOKEN not in caplog.text


def test_wrong_token_warnings_are_bundled_into_one_line_a_minute(client, token_env, caplog, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(cs_agent_pc, "_WARNINGS", cs_agent_pc.LogBundle(clock=lambda: clock[0]))
    caplog.set_level(logging.WARNING, logger=cs_agent_pc.__name__)
    for _ in range(5):  # 1000 · 1010 · 1020 · 1030 · 1040 초 — 한 창
        assert ask(client, "wrong-token").status_code == 401
        clock[0] += 10
    clock[0] += 20  # 첫 줄에서 70초 — 다음 창
    assert ask(client, "wrong-token").status_code == 401
    assert denied_lines(caplog) == ["CS_PC_SWITCH_DENIED ip=127.0.0.1 suppressed=0",
                                    "CS_PC_SWITCH_DENIED ip=127.0.0.1 suppressed=4"]  # 묶은 4번은 다음 줄에


def test_the_ip_limit_counts_every_request_whatever_cookie_it_carries(client, app, token_env):
    limit = int(rate_limit.DEFAULT_PC_SWITCH_RATE_LIMIT.split()[0])
    cookie = app.config.get("SESSION_COOKIE_NAME", "session")
    for n in range(limit):
        client.set_cookie(cookie, f"synthetic-cookie-{n}")  # 쿠키를 갈아 끼워도 같은 IP 묶음(공용 한도는 쿠키로 나뉜다)
        assert ask(client).status_code == 200, n
    assert ask(client).status_code == 429
    assert ask(client, "wrong-token").status_code == 429  # 열쇠 맞혀 보기도 같은 묶음에서 막힌다
    other = ask(client, environ_base={"REMOTE_ADDR": "198.51.100.7"})
    assert other.status_code == 200  # 음성 대조: 다른 IP 는 따로 센다


def test_the_right_token_reports_the_emergency_stop_only(client, token_env):
    running = ask(client)  # 줄이 없으면 돈다(감시 루프 규칙 그대로)
    assert running.status_code == 200 and running.get_json() == {"success": True, "data": {"stop": False}, "error": None}
    assert running.headers["Cache-Control"] == "no-store"
    loop.set_switch(db_session, on=False)
    assert ask(client).get_json() == {"success": True, "data": {"stop": True}, "error": None}
    loop.set_switch(db_session, on=True)
    assert ask(client).get_json()["data"] == {"stop": False}
    turns.set_draft_mode(db_session, "off", reason="synthetic", now=now_kst())  # 초안 끔은 비상 정지가 아니다
    db_session.commit()
    assert ask(client).get_json()["data"] == {"stop": False}


def test_a_broken_switch_value_counts_as_stopped(client, token_env):
    db_session.merge(SystemSetting(setting_key=turns.SWITCH_KEY, setting_value={"loop": "of"}))  # 오타 — 끈 것으로 본다
    db_session.commit()
    assert ask(client).get_json()["data"] == {"stop": True}


def test_a_db_error_answers_stop_true(client, token_env, monkeypatch):
    def boom(_session):
        raise OperationalError("SELECT 1", {}, Exception("synthetic db down"))

    monkeypatch.setattr(cs_agent_pc, "read_switch", boom)
    resp = ask(client)
    assert resp.status_code == 200 and resp.get_json() == {"success": True, "data": {"stop": True}, "error": None}


def test_no_login_or_csrf_is_needed_and_writes_are_not_allowed(client, app, token_env):
    sentinel = object()
    previous = app.config.get("WRITE_GUARD_ENABLED", sentinel)
    app.config["WRITE_GUARD_ENABLED"] = True  # 쓰기 가드가 켜져 있어도 GET 은 지난다
    try:
        assert ask(client).status_code == 200  # 세션 · CSRF 없이
        assert client.post(PATH, headers={cs_agent_pc.SWITCH_HEADER: TOKEN}).status_code == 405  # 읽기만
    finally:
        if previous is sentinel:
            app.config.pop("WRITE_GUARD_ENABLED", None)
        else:
            app.config["WRITE_GUARD_ENABLED"] = previous
    rules = [rule for rule in app.url_map.iter_rules() if rule.rule == PATH]
    assert len(rules) == 1 and rules[0].methods - {"HEAD", "OPTIONS"} == {"GET"}
    assert rate_limit.PC_SWITCH_ENDPOINT in app.view_functions  # IP 한도가 이 이름으로 걸린다(이름이 바뀌면 한도가 빠진다)

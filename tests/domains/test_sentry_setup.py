"""foms.platform.sentry_setup 계약 테스트 (AUDIT-LOG T10).

고정하는 계약:

- ``SENTRY_DSN`` 부재 = **완전 no-op** (``sentry_sdk``가 sys.modules에 로드조차
  되지 않는다 — 미설치 환경에서도 앱 import가 죽지 않는 근거).
- DSN 존재 시 ``sentry_sdk.init`` 인자 계약(FlaskIntegration·PII off·
  traces 0·before_send 배선). 실네트워크 0 — init을 monkeypatch로 가로챈다.
- ``_scrub_event``의 재귀 마스킹: 중첩 dict/list·breadcrumbs·exception values·
  request 데이터·비밀 키 이름·깊이 상한(순환 참조)·원본 비파괴·실패 시 최소
  이벤트(절대 drop 아님, 예외 전파 없음).
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from foms.platform import app_factory
from foms.platform.sentry_setup import (
    MAX_SCRUB_DEPTH,
    REDACTED,
    SCRUB_FAILURE_MESSAGE,
    _scrub_event,
    init_sentry,
    resolve_environment,
)

_ENV_VARS = ("SENTRY_DSN", "RAILWAY_ENVIRONMENT", "FOMS_ENV")


@pytest.fixture()
def clean_env(monkeypatch):
    """Sentry 관련 env를 모두 제거한 상태에서 시작한다."""
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _sentry_modules() -> list[str]:
    """현재 로드된 ``sentry_sdk`` 계열 모듈 이름 목록."""
    return [
        name
        for name in sys.modules
        if name == "sentry_sdk" or name.startswith("sentry_sdk.")
    ]


# --------------------------------------------------------------------------
# init_sentry — env gate
# --------------------------------------------------------------------------


def test_init_sentry_without_dsn_is_noop_and_never_imports_sdk(clean_env):
    """DSN 부재 시 False + sentry_sdk 미로드(import 부작용 0)."""
    for name in _sentry_modules():
        clean_env.delitem(sys.modules, name)

    assert init_sentry() is False
    assert _sentry_modules() == []


def test_init_sentry_ignores_blank_dsn(clean_env):
    """공백뿐인 DSN은 미설정과 동일하게 취급한다."""
    clean_env.setenv("SENTRY_DSN", "   ")
    for name in _sentry_modules():
        clean_env.delitem(sys.modules, name)

    assert init_sentry() is False
    assert _sentry_modules() == []


def test_app_factory_wires_init_sentry():
    """build_app 경로가 이 모듈의 init_sentry를 그대로 참조한다."""
    assert app_factory.init_sentry is init_sentry


# --------------------------------------------------------------------------
# init_sentry — DSN 존재 시 인자 계약 (실네트워크 0)
# --------------------------------------------------------------------------


def _capture_init(monkeypatch) -> dict[str, Any]:
    """``sentry_sdk.init``을 가로채 호출 인자를 담을 dict를 돌려준다."""
    import sentry_sdk

    captured: dict[str, Any] = {}

    def _fake_init(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(sentry_sdk, "init", _fake_init)
    return captured


def test_init_sentry_passes_expected_options(clean_env):
    """DSN 존재 시 init 인자 계약(PII off·traces 0·before_send·환경 태그)."""
    captured = _capture_init(clean_env)
    clean_env.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    clean_env.setenv("RAILWAY_ENVIRONMENT", "staging")

    assert init_sentry() is True

    from sentry_sdk.integrations.flask import FlaskIntegration

    assert captured["dsn"] == "https://public@example.invalid/1"
    assert captured["send_default_pii"] is False
    assert captured["traces_sample_rate"] == 0
    assert captured["before_send"] is _scrub_event
    assert captured["environment"] == "staging"
    assert any(
        isinstance(integration, FlaskIntegration)
        for integration in captured["integrations"]
    )


def test_environment_falls_back_to_foms_env_then_local(clean_env):
    """환경 태그는 RAILWAY_ENVIRONMENT → FOMS_ENV → 'local' 순으로 해석된다."""
    assert resolve_environment() == "local"

    clean_env.setenv("FOMS_ENV", "dev")
    assert resolve_environment() == "dev"

    clean_env.setenv("RAILWAY_ENVIRONMENT", "production")
    assert resolve_environment() == "production"


def test_init_sentry_survives_bad_dsn(clean_env):
    """DSN 형식 오류(BadDsn=ValueError)로 앱 기동이 죽지 않는다."""
    import sentry_sdk
    from sentry_sdk.utils import BadDsn

    def _raising_init(**_kwargs: Any) -> None:
        raise BadDsn("Unsupported scheme")

    clean_env.setattr(sentry_sdk, "init", _raising_init)
    clean_env.setenv("SENTRY_DSN", "not-a-dsn")

    assert init_sentry() is False


# --------------------------------------------------------------------------
# _scrub_event — 재귀 마스킹
# --------------------------------------------------------------------------


def _secret_event() -> dict[str, Any]:
    """비밀값이 여러 깊이·형태로 박힌 대표 이벤트 dict."""
    return {
        "event_id": "abc123",
        "level": "error",
        "logentry": {"message": "boom while login password=hunter2secret"},
        "breadcrumbs": {
            "values": [
                {
                    "type": "default",
                    "message": "auth call token=deadbeefsecretvalue",
                },
                {"type": "default", "message": "connected to db"},
            ]
        },
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "value": "bad AKIAIOSFODNN7EXAMPLE key",
                }
            ]
        },
        "request": {
            "url": "postgresql://dbuser:dbpassword@dbhost:5432/foms",
            "data": {"password": "hunter2", "order_id": 41},
            "headers": {"Authorization": "Bearer abc123token"},
            "cookies": {"session_staging": "opaque-cookie-value"},
        },
        "extra": {
            "trail": ["harmless", "api_key=supersecretapikeyvalue"],
            "long": "A" * 45,
        },
    }


def test_scrub_masks_secrets_across_nested_structures():
    """logentry·breadcrumbs·exception·request·list 안 비밀값이 모두 마스킹된다."""
    scrubbed = _scrub_event(_secret_event(), {})

    assert scrubbed is not None
    assert "hunter2secret" not in repr(scrubbed)
    assert "password=***" in scrubbed["logentry"]["message"]

    crumbs = scrubbed["breadcrumbs"]["values"]
    assert "deadbeefsecretvalue" not in crumbs[0]["message"]
    assert "token=***" in crumbs[0]["message"]
    assert crumbs[1]["message"] == "connected to db"

    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed["exception"]["values"][0]["value"]
    assert scrubbed["exception"]["values"][0]["type"] == "ValueError"

    assert scrubbed["request"]["url"] == "postgresql://***:***@dbhost:5432/foms"
    assert "supersecretapikeyvalue" not in repr(scrubbed["extra"]["trail"])
    assert scrubbed["extra"]["trail"][0] == "harmless"
    assert scrubbed["extra"]["long"] == REDACTED


def test_scrub_masks_secret_named_dict_keys():
    """키 이름이 비밀값을 뜻하면(form body·헤더·쿠키) 값 전체를 마스킹한다."""
    scrubbed = _scrub_event(_secret_event(), {})

    assert scrubbed["request"]["data"]["password"] == REDACTED
    assert scrubbed["request"]["data"]["order_id"] == 41
    assert scrubbed["request"]["headers"]["Authorization"] == REDACTED
    assert scrubbed["request"]["cookies"] == REDACTED
    assert "hunter2" not in repr(scrubbed["request"])


def test_scrub_does_not_mutate_the_original_event():
    """원본 이벤트는 비파괴 — 새 구조를 만들어 돌려준다."""
    event = _secret_event()
    scrubbed = _scrub_event(event, {})

    assert event["logentry"]["message"] == "boom while login password=hunter2secret"
    assert event["request"]["data"]["password"] == "hunter2"
    assert scrubbed["request"]["data"] is not event["request"]["data"]


def test_scrub_terminates_on_cyclic_structures():
    """순환 참조도 깊이 상한에서 끊겨 RecursionError 없이 끝난다."""
    node: dict[str, Any] = {"note": "loop"}
    node["self"] = node
    event = {"event_id": "cycle-1", "extra": node}

    scrubbed = _scrub_event(event, {})

    depth = 0
    cursor: Any = scrubbed["extra"]
    while isinstance(cursor, dict) and "self" in cursor:
        cursor = cursor["self"]
        depth += 1
        assert depth <= MAX_SCRUB_DEPTH
    assert cursor == REDACTED


def test_scrub_failure_returns_minimal_event_without_raising():
    """마스킹이 깨져도 예외 전파 없이 최소 이벤트만 남긴다(drop 아님)."""

    class _ExplodingDict(dict):
        """순회 중 예외를 일으키는 dict(마스킹 실패 재현용)."""

        def items(self):  # type: ignore[override]
            raise TypeError("boom")

    event = {
        "event_id": "evt-1",
        "level": "error",
        "environment": "staging",
        "exception": {"values": [{"type": "KeyError", "value": "password=hunter2"}]},
        "extra": _ExplodingDict({"password": "hunter2"}),
    }

    minimal = _scrub_event(event, {})

    assert minimal is not None
    assert minimal["logentry"]["message"] == SCRUB_FAILURE_MESSAGE
    assert minimal["event_id"] == "evt-1"
    assert minimal["level"] == "error"
    assert minimal["environment"] == "staging"
    assert minimal["extra"] == {"exception_types": ["KeyError"]}
    assert "hunter2" not in repr(minimal)


def test_scrub_never_returns_none_for_odd_payloads():
    """dict가 아닌 입력·빈 이벤트에도 None(drop)을 돌려주지 않는다."""
    assert _scrub_event({}, {}) == {}
    assert _scrub_event({"level": "info"}, {}) == {"level": "info"}

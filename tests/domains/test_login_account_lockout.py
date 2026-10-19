"""AUTH-LOGIN-LOCK-02: 계정 기준 로그인 잠금 카운터 계약(2026-10-19).

``test_login_rate_limit_lockout.py`` 가 (아이디, IP) 잠금을 고정하고, 이 파일은 그 옆에 붙은
계정 카운터(정규화한 아이디, IP 없음)와 저장소 공유·실패 관측을 고정한다.
설계서 ``docs/specs/2026-10-19-login-lockout-key_SPEC.md``.

* 앱이 보는 IP 가 요청마다 바뀌어도(프록시 뒤 ``X-Forwarded-For`` 회전) 같은 아이디면 잠긴다 —
  계정이 있든 없든 같은 429.
* 대소문자·공백 변형은 같은 계정 카운터로 접힌다. 성공 로그인은 계정 카운터도 지운다.
* 같은 저장소 URI 를 쓰는 워커 2개는 함께 잠기고, 프로세스 메모리 저장소면 카운터가 나뉜다.
* 저장소 실패는 요청당 경고 1건 + fail-open, 배포 환경 메모리 저장소는 기동 경고.

격리 픽스처(한도 저장소 초기화·짧은 창·limiter 핸들러 복원)와 헬퍼는 기존 파일의 것을 그대로 쓴다.
"""

from __future__ import annotations

import logging

import pytest
from flask import Flask
from limits.storage import MemoryStorage
from werkzeug.middleware.proxy_fix import ProxyFix

import foms.services.rate_limit as rate_limit
import foms.services.security.auth_rate.login_lockout as login_lockout
from foms.platform.app_factory import build_app
from tests.domains.test_login_rate_limit_lockout import (  # noqa: F401  autouse 픽스처 등록
    _STRONG_PW,
    _THRESHOLD,
    _WRONG_PW,
    _make_user,
    _post_login,
    _reset_rate_limits,
    _restore_flask_limiter_handlers,
    _rows,
    _small_lockout_window,
)


# --------------------------------------------------------------------------
# 8. 계정 카운터 — 앱이 보는 IP 가 요청마다 바뀌어도 같은 아이디면 잠긴다 (2026-10-19)
# --------------------------------------------------------------------------
#: 계정 카운터 시험 임계. (아이디, IP) 임계(_THRESHOLD=3)보다 커야 운영 관계(8 < 20)를 흉내낸다.
_ACCOUNT_THRESHOLD = 5


def _behind_proxy(app, monkeypatch) -> None:
    """운영처럼 ProxyFix(홉 1) 뒤에 앱을 둔다 — ``X-Forwarded-For`` 가 ``remote_addr`` 를 정한다."""
    monkeypatch.setattr(
        app, "wsgi_app", ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    )


def _post_from(client, username: str, password: str, ip: str):
    """주어진 클라이언트 IP(프록시가 붙인 ``X-Forwarded-For``)로 /login POST 1회."""
    return client.post(
        "/login",
        data={"username": username, "password": password},
        headers={"X-Forwarded-For": ip},
    )


@pytest.mark.parametrize("account_exists", [True, False], ids=["existing", "unknown"])
def test_rotating_forwarded_for_still_locks_same_account(client, app, monkeypatch, account_exists):
    """스테이징 증상(없는 아이디 9회 → 200×9)의 재현: IP 가 매번 바뀌어도 계정 임계에서 429.

    계정이 있든 없든 같은 순서로 같은 상태 코드가 나와야 한다(존재를 드러내지 않는다).
    """
    monkeypatch.setenv("FOMS_LOGIN_ACCOUNT_LOCKOUT_THRESHOLD", str(_ACCOUNT_THRESHOLD))
    _behind_proxy(app, monkeypatch)
    if account_exists:
        _make_user("rotating-target")

    statuses = [
        _post_from(client, "rotating-target", _WRONG_PW, f"203.0.113.{i + 1}").status_code
        for i in range(_ACCOUNT_THRESHOLD + 1)
    ]
    assert statuses == [200] * (_ACCOUNT_THRESHOLD - 1) + [429, 429], statuses

    # 잠긴 계정은 새 IP 에서 맞는 비밀번호여도 비밀번호 대조 앞에서 끊긴다.
    locked = _post_from(app.test_client(), "rotating-target", _STRONG_PW, "198.51.100.200")
    assert locked.status_code == 429
    assert locked.headers.get("Retry-After") == "60", "잠금 429 는 대기 시간을 알린다"

    locks = _rows("LOGIN_LOCKED")
    assert len(locks) == 1
    assert locks[0].detail["scope"] == "account"
    assert locks[0].detail["threshold"] == _ACCOUNT_THRESHOLD

    # 대조군: 같은 IP 들에서 다른 아이디는 그대로 로그인된다(잠금이 번지지 않는다).
    _make_user("rotating-bystander")
    other = _post_from(app.test_client(), "rotating-bystander", _STRONG_PW, "203.0.113.1")
    assert other.status_code == 302


def test_account_counter_folds_case_and_whitespace(client, app, monkeypatch):
    """대소문자·앞뒤 공백만 다른 아이디는 같은 계정 카운터를 쓴다(정규화한 아이디)."""
    monkeypatch.setenv("FOMS_LOGIN_ACCOUNT_LOCKOUT_THRESHOLD", str(_ACCOUNT_THRESHOLD))
    _behind_proxy(app, monkeypatch)
    _make_user("fold-target")

    variants = ["Fold-Target", " fold-target", "FOLD-TARGET ", "fold-target", "Fold-target"]
    statuses = [
        _post_from(client, name, _WRONG_PW, f"203.0.113.{i + 1}").status_code
        for i, name in enumerate(variants)
    ]
    assert statuses == [200] * (_ACCOUNT_THRESHOLD - 1) + [429], statuses
    assert _post_from(client, "fold-target", _STRONG_PW, "198.51.100.9").status_code == 429


def test_success_clears_account_failure_counter(client, app, monkeypatch):
    """성공 로그인은 계정 실패 카운터도 지운다 — 안 지우면 다음 묶음에서 임계 전에 잠긴다."""
    monkeypatch.setenv("FOMS_LOGIN_ACCOUNT_LOCKOUT_THRESHOLD", str(_ACCOUNT_THRESHOLD))
    _behind_proxy(app, monkeypatch)
    _make_user("account-reset")

    for i in range(_ACCOUNT_THRESHOLD - 1):
        resp = _post_from(client, "account-reset", _WRONG_PW, f"203.0.113.{i + 1}")
        assert resp.status_code == 200
    ok = _post_from(app.test_client(), "account-reset", _STRONG_PW, "198.51.100.1")
    assert ok.status_code == 302

    for i in range(_ACCOUNT_THRESHOLD - 1):
        resp = _post_from(app.test_client(), "account-reset", _WRONG_PW, f"192.0.2.{i + 1}")
        assert resp.status_code == 200, f"성공 뒤 {i + 1}번째 실패가 잠겼다 — 계정 카운터가 남았다"
    assert _rows("LOGIN_LOCKED") == []


# --------------------------------------------------------------------------
# 9. 워커 2개 — 같은 저장소 주소를 쓰는 앱 2개가 카운터를 공유한다
# --------------------------------------------------------------------------
class _SharedUriStorage(MemoryStorage):
    """같은 URI 면 같은 카운터를 보는 시험용 저장소 — 프로세스 밖 Redis 를 흉내낸다.

    ``limits`` 는 ``STORAGE_SCHEME`` 을 클래스 정의 시점에 전역 등록하므로
    ``REDIS_URL=foms-shared-test://...`` 이면 :func:`init_limiter` 가 이 저장소를 고른다.
    """

    STORAGE_SCHEME = ["foms-shared-test"]
    _shared: dict = {}

    def __init__(self, uri=None, wrap_exceptions=False, **options):
        """URI 별 공유 상태(카운터·만료·이벤트)에 붙는다."""
        super().__init__(uri, wrap_exceptions=wrap_exceptions, **options)
        state = self._shared.setdefault(uri or "", (self.storage, self.expirations, self.events))
        self.storage, self.expirations, self.events = state


def _worker_pair(monkeypatch, storage_uri):
    """같은 env 로 앱 2개를 만든다 — gunicorn ``-w 2`` 의 두 워커 흉내.

    :param storage_uri: ``REDIS_URL`` 로 줄 저장소 주소. ``None`` 이면 지워서 ``memory://``.
    :return: 두 앱의 test client 튜플.
    """
    if storage_uri is None:
        monkeypatch.delenv("REDIS_URL", raising=False)
    else:
        monkeypatch.setenv("REDIS_URL", storage_uri)
    first = build_app(socketio_available=False).app
    second = build_app(socketio_available=False).app
    return first.test_client(), second.test_client()


def _alternate_failures(w1, w2, username: str, count: int) -> list[int]:
    """두 워커에 번갈아 틀린 비밀번호를 보내고 상태 코드를 돌려준다."""
    return [
        (w1 if i % 2 == 0 else w2)
        .post("/login", data={"username": username, "password": _WRONG_PW})
        .status_code
        for i in range(count)
    ]


def test_two_workers_sharing_storage_uri_lock_together(app, monkeypatch):
    """두 워커가 같은 저장소 주소를 쓰면 번갈아 받은 실패가 합쳐져 임계에서 잠긴다."""
    _SharedUriStorage._shared.clear()
    _make_user("two-workers")
    w1, w2 = _worker_pair(monkeypatch, "foms-shared-test://lockout-two-workers")

    statuses = _alternate_failures(w1, w2, "two-workers", _THRESHOLD)
    assert statuses == [200] * (_THRESHOLD - 1) + [429], statuses
    resp = w2.post("/login", data={"username": "two-workers", "password": _STRONG_PW})
    assert resp.status_code == 429


def test_two_workers_with_memory_storage_split_counters(app, monkeypatch):
    """음성 대조군: ``memory://`` 워커 2개는 카운터를 나눠 가져 임계에서 잠기지 않는다.

    이 테스트가 빨개지면(=잠기면) 위 공유 테스트가 공유를 증명하지 못한다.
    """
    w1, w2 = _worker_pair(monkeypatch, None)
    assert _alternate_failures(w1, w2, "split-workers", _THRESHOLD) == [200] * _THRESHOLD


# --------------------------------------------------------------------------
# 10. 저장소 관측 — 실행 중 실패는 요청당 경고 1건, 배포 환경의 메모리 저장소는 기동 경고
# --------------------------------------------------------------------------
class _DeadStorage:
    """모든 호출이 저장소 예외를 내는 저장소(Redis 연결 끊김 흉내)."""

    base_exceptions = (ConnectionError,)

    def incr(self, key, expiry, amount=1):
        """항상 실패."""
        raise ConnectionError("storage down")

    def get(self, key):
        """항상 실패."""
        raise ConnectionError("storage down")

    def clear(self, key):
        """항상 실패."""
        raise ConnectionError("storage down")


def test_storage_failure_logs_once_per_request_and_fails_open(client, app, monkeypatch, caplog):
    """저장소가 죽으면 로그인은 막지 않고(200, 500 아님) 요청당 경고 1건을 남긴다."""
    monkeypatch.setattr(login_lockout, "_limiter_storage", lambda: _DeadStorage())
    attempts = _THRESHOLD + 1

    with caplog.at_level(logging.WARNING, logger=login_lockout.__name__):
        for _ in range(attempts):
            assert _post_login(client, "dead-storage", _WRONG_PW).status_code == 200

    records = [r for r in caplog.records if r.name == login_lockout.__name__]
    assert len(records) == attempts, [r.getMessage() for r in records]
    assert all("fail-open" in r.getMessage() for r in records)
    assert _rows("LOGIN_LOCKED") == []


def test_startup_warns_when_deployed_limiter_uses_process_memory(monkeypatch, caplog):
    """배포 환경에서 저장소가 ``memory`` 면 기동 때 경고 — 워커마다 카운터가 따로다."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("REDIS_URL", raising=False)

    with caplog.at_level(logging.INFO, logger=rate_limit.__name__):
        rate_limit.init_limiter(Flask(__name__))

    warnings = [
        r for r in caplog.records
        if r.name == rate_limit.__name__ and r.levelno >= logging.WARNING
    ]
    assert len(warnings) == 1, [r.getMessage() for r in warnings]
    assert "storage=memory" in warnings[0].getMessage()


def test_startup_does_not_warn_when_limiter_uses_redis(monkeypatch, caplog):
    """대조군: Redis 주소면 기동 경고가 없다(기동 때 연결하지 않는다)."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6390")

    with caplog.at_level(logging.INFO, logger=rate_limit.__name__):
        rate_limit.init_limiter(Flask(__name__))

    records = [r for r in caplog.records if r.name == rate_limit.__name__]
    assert [r for r in records if r.levelno >= logging.WARNING] == []
    assert any("storage=redis" in r.getMessage() for r in records), "저장소 종류는 INFO 로 남는다"
    assert not any("127.0.0.1:6390" in r.getMessage() for r in records), "URL 원문은 싣지 않는다"

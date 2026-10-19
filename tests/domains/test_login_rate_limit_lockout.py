"""AUTH-LOGIN-LOCK-01: 로그인 전용 한도·실패 잠금·레이트리미터 폴백 관측 계약.

2026-09-06 검토 R7/D6 이 센 두 구멍을 코드로 봉인한다:

1. 쓰기 경로 209 라우트는 ``before_request`` SSOT 가 판정하는데 **로그인에는 한도도 잠금도
   0** 이었다 — 가장 흔한 공격면이 무방비였다.
2. ``build_limiter`` 는 ``swallow_errors`` + ``in_memory_fallback_enabled`` 라 Redis 가 죽으면
   **조용히** 인메모리로 떨어졌다 — 한도가 열린 것을 아무도 몰랐다.

검증 대상:

* 연속 실패가 임계를 넘으면 429 로 잠기고, 감사에 ``LOGIN_FAIL`` 이 임계 수만큼
  · ``LOGIN_LOCKED`` 가 **1건** 남는다(비밀번호는 어디에도 남지 않는다).
* **음성 대조군** — 임계 미만 실패 뒤 올바른 비밀번호는 그대로 성공하고, 성공이 카운터를
  되돌린다(같은 창 안에서 다시 임계 미만을 틀려도 잠기지 않는다).
* **계정 DoS 방지** — 다른 아이디는 같은 IP 여도 독립적으로 센다.
* 로그인 전용 한도(``FOMS_LOGIN_RATE_LIMIT``)가 **실패한** POST 볼륨만 자른다 — GET 폼과
  성공한 로그인은 버킷을 깎지 않는다(공용 단말 교대 로그인을 거짓 차단하지 않는다).
* 저장소가 죽어 인메모리 폴백으로 떨어지면 **warning 1건 + Sentry 이벤트 1건**이 남는다
  (요청마다 쏟지 않는다 — 로그가 폭주하면 관측이 오히려 죽는다).
* 새 감사 action ``LOGIN_LOCKED`` 가 한글 라벨 표에 등재돼 있다(빠지면 화면에 raw 태그).

**테스트 격리**: 레이트리미터 저장소는 프로세스 전역이라 한 테스트의 카운터가 다음 테스트로
샌다. 매 테스트 앞에서 ``limiter.reset()`` 으로 저장소를 통째로 비우고(잠금 카운터도 같은
저장소에 살아서 함께 지워진다), 임계·창은 env 로 낮춰 고정한다. 폴백 관측 핸들러는 프로세스
전역 ``flask-limiter`` 로거에 붙으므로 핸들러 목록도 스냅샷 후 복원한다.
"""

from __future__ import annotations

import logging

import pytest
import sentry_sdk
from flask import Flask
from limits.storage import MemoryStorage
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

import foms.services.rate_limit as rate_limit
import foms.services.security.auth_rate.login_lockout as login_lockout
from db import db_session
from foms.platform.app_factory import build_app
from foms.services.audit_message_display import ACTION_LABELS, action_label
from models import SecurityLog, User

_STRONG_PW = "Abcdef12"
_WRONG_PW = "Wrongpw99"

#: 테스트용 임계. 운영 기본(8)로 돌리면 매 테스트가 POST 9번씩 돈다.
_THRESHOLD = 3


@pytest.fixture(autouse=True)
def _reset_rate_limits(app):
    """레이트리미터 저장소(=잠금 카운터 저장소)를 테스트마다 비운다.

    메모리 저장소가 프로세스 수명 동안 유지되어 버킷·실패 카운터가 테스트 사이로 샌다.
    """
    for limiter in app.extensions.get("limiter", set()):
        limiter.reset()
    yield


@pytest.fixture(autouse=True)
def _small_lockout_window(monkeypatch):
    """임계·창을 테스트 크기로 낮춘다(값은 호출 시점에 읽히므로 monkeypatch 로 충분)."""
    monkeypatch.setenv("FOMS_LOGIN_LOCKOUT_THRESHOLD", str(_THRESHOLD))
    monkeypatch.setenv("FOMS_LOGIN_LOCKOUT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("FOMS_LOGIN_LOCKOUT_SECONDS", "60")
    yield


@pytest.fixture(autouse=True)
def _restore_flask_limiter_handlers():
    """``flask-limiter`` 전역 로거의 핸들러 목록을 스냅샷 후 복원한다.

    폴백 관측 테스트가 새 limiter 를 만들면 그 핸들러가 세션 앱 limiter 의 것을 밀어낸다.
    """
    limiter_logger = logging.getLogger(rate_limit.FLASK_LIMITER_LOGGER_NAME)
    saved = list(limiter_logger.handlers)
    yield
    limiter_logger.handlers[:] = saved


class _ActiveSentryClient:
    """활성 Sentry 클라이언트 흉내(폴백 관측의 Sentry 다리를 세기 위한 것)."""

    def is_active(self) -> bool:
        """항상 활성.

        :return: ``True``.
        """
        return True


def _make_user(username: str, *, raw_password: str = _STRONG_PW) -> int:
    """활성 STAFF 사용자를 만들고 정수 id 를 돌려준다(teardown detach 대비)."""
    user = User(
        username=username,
        password=generate_password_hash(raw_password),
        role="STAFF",
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _post_login(client, username: str, password: str):
    """/login POST 1회."""
    return client.post("/login", data={"username": username, "password": password})


def _rows(action: str) -> list[SecurityLog]:
    """해당 action 의 감사 행을 오래된 순으로 돌려준다."""
    return (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == action)
        .order_by(SecurityLog.id.asc())
        .all()
    )


# --------------------------------------------------------------------------
# 1. 임계 초과 → 429
# --------------------------------------------------------------------------
def test_repeated_bad_password_locks_with_429(client, app):
    """연속 실패가 임계에 닿으면 429 로 잠기고, 이후 시도도 계속 429 다."""
    _make_user("lock-target")

    for attempt in range(_THRESHOLD - 1):
        resp = _post_login(client, "lock-target", _WRONG_PW)
        assert resp.status_code == 200, f"{attempt + 1}번째 실패는 아직 잠기면 안 된다"

    assert _post_login(client, "lock-target", _WRONG_PW).status_code == 429
    # 잠긴 뒤에는 올바른 비밀번호여도 통과하지 못한다(비밀번호 대조 앞에서 끊긴다).
    assert _post_login(client, "lock-target", _STRONG_PW).status_code == 429


# --------------------------------------------------------------------------
# 2. 감사 행 — LOGIN_FAIL 임계 수 + LOGIN_LOCKED 1건
# --------------------------------------------------------------------------
def test_lock_writes_login_fail_rows_and_single_login_locked(client, app):
    """실패는 임계 수만큼, 잠금은 1건. 비밀번호는 어떤 형태로도 남지 않는다."""
    user_id = _make_user("audit-target")

    for _ in range(_THRESHOLD + 2):
        _post_login(client, "audit-target", _WRONG_PW)

    fails = _rows("LOGIN_FAIL")
    locks = _rows("LOGIN_LOCKED")
    assert len(fails) == _THRESHOLD, "잠긴 뒤 시도는 실패로 세지 않는다(감사 폭주 방지)"
    assert len(locks) == 1, "잠금 감사는 전이 1회에만 남는다"

    lock = locks[0]
    assert lock.user_id == user_id
    assert lock.target_type is None and lock.target_id is None
    assert lock.detail["reason"] == "lockout_threshold"
    assert lock.detail["threshold"] == _THRESHOLD
    assert lock.detail["scope"] == "ip", "같은 자리에서 8회(여기선 3회)면 (아이디, IP) 잠금이 먼저다"
    assert lock.detail["username"] == "audit-target"

    for row in fails + locks:
        blob = f"{row.message}{row.detail}"
        assert _WRONG_PW not in blob and _STRONG_PW not in blob


# --------------------------------------------------------------------------
# 3. 음성 대조군 — 임계 미만이면 잠기지 않고, 성공이 카운터를 되돌린다
# --------------------------------------------------------------------------
def test_below_threshold_then_correct_password_succeeds(client, app):
    """임계 미만 실패 뒤 올바른 비밀번호는 성공하고, 성공이 실패 카운터를 지운다."""
    _make_user("negative-control")

    for _ in range(_THRESHOLD - 1):
        assert _post_login(client, "negative-control", _WRONG_PW).status_code == 200

    resp = _post_login(client, "negative-control", _STRONG_PW)
    assert resp.status_code == 302, "임계 미만이면 잠기지 않는다"
    assert _rows("LOGIN_LOCKED") == []
    assert len(_rows("LOGIN_OK")) == 1

    # 성공이 카운터를 되돌렸다면, 같은 창 안에서 임계 미만을 다시 틀려도 잠기지 않는다.
    # (되돌리지 않았다면 (임계-1)+(임계-1) >= 임계 라 여기서 429 가 났을 것이다.)
    fresh = app.test_client()
    for _ in range(_THRESHOLD - 1):
        assert _post_login(fresh, "negative-control", _WRONG_PW).status_code == 200
    assert _rows("LOGIN_LOCKED") == []


# --------------------------------------------------------------------------
# 4. 계정 DoS 방지 — 같은 IP 라도 아이디가 다르면 따로 센다
# --------------------------------------------------------------------------
def test_other_username_from_same_ip_is_counted_independently(client, app):
    """한 아이디가 잠겨도 같은 IP 의 다른 아이디는 그대로 로그인된다."""
    _make_user("victim")
    _make_user("bystander")

    for _ in range(_THRESHOLD):
        _post_login(client, "victim", _WRONG_PW)
    assert _post_login(client, "victim", _STRONG_PW).status_code == 429

    other = app.test_client()
    assert _post_login(other, "bystander", _STRONG_PW).status_code == 302
    assert len(_rows("LOGIN_LOCKED")) == 1


# --------------------------------------------------------------------------
# 5. 로그인 전용 한도 — POST 볼륨만 자른다
# --------------------------------------------------------------------------
def test_login_rate_limit_caps_post_volume_and_spares_the_form(client, app, monkeypatch):
    """잠금을 사실상 꺼도 ``FOMS_LOGIN_RATE_LIMIT``(기본 10/분)이 POST 를 자른다."""
    monkeypatch.setenv("FOMS_LOGIN_LOCKOUT_THRESHOLD", "10000")
    _make_user("volume-target")

    for attempt in range(10):
        resp = _post_login(client, "volume-target", _WRONG_PW)
        assert resp.status_code == 200, f"{attempt + 1}번째 POST 는 한도 안이다"

    assert _post_login(client, "volume-target", _WRONG_PW).status_code == 429
    assert _rows("LOGIN_LOCKED") == [], "이건 한도지 잠금이 아니다"
    # GET(폼 표시)은 제한 대상이 아니다(methods=["POST"]).
    assert client.get("/login").status_code == 200


def test_successful_logins_do_not_consume_the_login_cap(app, monkeypatch):
    """성공한 로그인은 한도를 깎지 않는다(``deduct_when`` 계약).

    공용 단말에서 여러 명이 잇달아 정상 로그인해도 429 가 나면 안 된다. 차감이 성공까지
    센다면 11번째 로그인에서 429 가 났을 것이다.
    """
    monkeypatch.setenv("FOMS_LOGIN_LOCKOUT_THRESHOLD", "10000")
    _make_user("shared-terminal")

    for attempt in range(12):
        fresh = app.test_client()
        resp = _post_login(fresh, "shared-terminal", _STRONG_PW)
        assert resp.status_code == 302, f"{attempt + 1}번째 정상 로그인이 막혔다"

    assert len(_rows("LOGIN_OK")) == 12


# --------------------------------------------------------------------------
# 6. 폴백 관측 — 죽은 저장소에서 warning 1건
# --------------------------------------------------------------------------
def test_dead_storage_reports_in_memory_fallback_once(caplog, monkeypatch):
    """도달 불가 REDIS_URL 이면 폴백 진입 warning + Sentry 이벤트가 **각 1건** 남는다."""
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6390")
    monkeypatch.setenv("FLASK_DEFAULT_RATE_LIMITS", "100 per minute")

    # Sentry 는 DSN 이 없으면 비활성이라 아무것도 보내지 않는다. 활성 클라이언트를 흉내내
    # "이벤트 1건" 을 실제로 세운다(SDK 자체는 건드리지 않는다).
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(sentry_sdk, "get_client", lambda: _ActiveSentryClient())
    monkeypatch.setattr(
        sentry_sdk,
        "capture_message",
        lambda message, level=None: sent.append((message, level)),
    )

    probe = Flask(__name__)

    @probe.route("/ping")
    def ping() -> str:
        return "ok"

    rate_limit.init_limiter(probe)
    probe_client = probe.test_client()

    with caplog.at_level(logging.WARNING, logger=rate_limit.__name__):
        assert probe_client.get("/ping").status_code == 200  # fail-open: 500 이 아니다
        assert probe_client.get("/ping").status_code == 200

    # 관측이 매달린 로거 이름 고정 — flask-limiter 가 로거 이름을 바꾸면 배선이 조용히
    # 죽는 대신 여기가 빨개진다.
    limiter_instance = next(iter(probe.extensions["limiter"]))
    assert limiter_instance.logger.name == rate_limit.FLASK_LIMITER_LOGGER_NAME

    # 기동 INFO(저장소 종류, 2026-10-19)는 세지 않는다 — 여기서 세는 것은 폴백 warning 이다.
    records = [
        r for r in caplog.records
        if r.name == rate_limit.__name__ and r.levelno >= logging.WARNING
    ]
    assert len(records) == 1, f"폴백 warning 은 전이 1회만 (실제 {len(records)}건)"
    message = records[0].getMessage()
    assert "인메모리 폴백" in message
    assert "storage=redis" in message
    assert "127.0.0.1:6390" not in message, "저장소 URL 원문은 로그에 싣지 않는다"

    assert len(sent) == 1, f"Sentry 이벤트도 전이 1회만 (실제 {len(sent)}건)"
    assert sent[0][1] == "warning"
    assert "127.0.0.1:6390" not in sent[0][0], "저장소 URL 원문은 Sentry 에도 싣지 않는다"


# --------------------------------------------------------------------------
# 7. 라벨 등재
# --------------------------------------------------------------------------
def test_login_locked_action_has_korean_label():
    """새 감사 action 은 라벨 표에 있어야 한다 — 빠지면 감사 화면에 raw 태그가 뜬다."""
    assert ACTION_LABELS.get("LOGIN_LOCKED") == "로그인 잠금"
    assert action_label("LOGIN_LOCKED") == "로그인 잠금"


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

"""채널톡 앱 토큰 공유 캐시 — 프로세스 여럿이 토큰 하나를 같이 쓴다(Redis + 잠금, 원장 R10-17 · 설계서 17.2.1 '토큰').

web · WORKER · 15분 바퀴 · 빠른 길 · SIDEFX 가 각자 ``issueToken`` 을 부르면 앱마다 30분 10번 한도(원장 F12-5)에 닿아 배포
직후 [보내기]가 실패할 수 있다. :func:`foms.services.channel_client._get_access_token` 이 프로세스 캐시 다음에 이 모듈을 본다.

- **읽기**: Redis 키 :func:`shared_key` — ``foms:channel_token:<환경>:<앱 지문>:<채널 id>`` (JSON ``{"token", "expires_at"}``)
  — 만료 전이면 그 값. 환경(Railway 프로젝트 · 환경 이름)과 앱 지문(앱 비밀의 sha256 앞 12자 — 비밀값 자체는 넣지 않는다)이
  열쇠에 들어 있어 스테이징 · 운영이 Redis 를 같이 써도 섞이지 않는다(검수 R15-6). 수명은 발급 응답의 ``expiresIn`` 으로 정한
  만료 그대로다(고정 수명을 새로 정하지 않는다 — EXT-TOKEN-01 R1).
- **없으면 잠금 하나만 발급**: ``…:lock`` 을 ``SET NX PX`` 로 잡은 쪽만 ``issueToken`` 을 부른다(잡은 뒤 한 번 더 읽는다).
  못 잡은 쪽은 :data:`WAIT_SECONDS` 까지 짧게 쉬며 다시 읽는다. 그래도 없으면(발급자가 죽음 · 느림) 스스로 발급한다 —
  Redis 때문에 채널톡 기능이 멈추지 않게.
- **무효(401)**: 공유 값이 그 죽은 토큰일 때만 지운다 — 읽은 값과 같을 때만 지우는 한 걸음(Lua)이라 그사이 다른 프로세스가
  넣은 새 토큰은 남는다(R2). 발급 잠금 풀기도 같은 한 걸음이다.
- **Redis 가 없거나(REDIS_URL 없음) 실패하면** ``None`` — 부르는 쪽이 지금처럼 이 프로세스에서 발급한다(앱의 다른 채널
  기능이 같은 함수를 쓴다 — 동작이 같아야 한다). 토큰 값은 로그에 싣지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Callable, Optional

from foms.platform.sentry_setup import resolve_environment

try:
    from redis.exceptions import RedisError as _RedisError
except ImportError:  # pragma: no cover - redis 는 rq 와 함께 늘 깔린다
    _RedisError = OSError

logger = logging.getLogger(__name__)

__all__ = ["KEY_PREFIX", "LOCK_MS", "WAIT_SECONDS", "drop_shared_token", "shared_key", "shared_token"]

KEY_PREFIX = "foms:channel_token:"
#: 발급 잠금 수명(밀리초) — 발급 요청 상한(10초)보다 길게.
LOCK_MS = 15_000
#: 잠금을 못 잡은 쪽이 공유 값을 기다리는 상한(초)과 쉬는 간격.
WAIT_SECONDS = 5.0
WAIT_STEP = 0.1
#: 남은 수명이 이보다 짧은 공유 값은 쓰지 않는다(쓰는 도중 죽지 않게).
MIN_LEFT_SECONDS = 5.0
_ERRORS = (_RedisError, OSError, ValueError, TypeError)
_CLIENTS: dict[str, Any] = {}
#: 읽은 값과 같을 때만 지우기(한 걸음) — 그사이 다른 프로세스가 넣은 값은 지우지 않는다.
_DELETE_IF_SAME = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
_SCOPE_PART = re.compile(r"[^A-Za-z0-9_.-]+")

Issued = tuple[str, float]


def _client() -> Optional[Any]:
    """REDIS_URL 의 Redis 클라이언트(프로세스마다 하나) — 없으면 ``None``(프로세스 캐시로 돈다)."""
    url = (os.environ.get("REDIS_URL") or "").strip()
    if not url:
        return None
    client = _CLIENTS.get(url)
    if client is None:
        try:
            from redis import Redis
        except ImportError:  # pragma: no cover
            return None
        client = _CLIENTS[url] = Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
    return client


def shared_key(channel_id: str, secret: str) -> str:
    """공유 열쇠 — 환경(프로젝트 · 환경 이름) · 앱 지문(비밀의 sha256 앞 12자) · 채널. 비밀값 자체는 넣지 않는다."""
    project = _SCOPE_PART.sub("-", (os.environ.get("RAILWAY_PROJECT_NAME") or "local").strip())[:40]
    environment = _SCOPE_PART.sub("-", resolve_environment())[:20]
    fingerprint = hashlib.sha256((secret or "").encode("utf-8")).hexdigest()[:12]
    return f"{KEY_PREFIX}{project}/{environment}:{fingerprint}:{channel_id}"


def _delete_if_same(redis: Any, key: str, value: Any) -> None:
    """``key`` 의 값이 ``value`` 일 때만 지운다(한 걸음)."""
    redis.eval(_DELETE_IF_SAME, 1, key, value)


def _read(client: Any, key: str, now: float) -> Optional[Issued]:
    """공유 값 — 꼴이 맞고 남은 수명이 :data:`MIN_LEFT_SECONDS` 넘는 것만."""
    raw = client.get(key)
    if raw is None:
        return None
    data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else str(raw))
    token, expires_at = data.get("token"), data.get("expires_at")
    if not isinstance(token, str) or not token or not isinstance(expires_at, (int, float)):
        return None
    return (token, float(expires_at)) if float(expires_at) - now > MIN_LEFT_SECONDS else None


def _store(client: Any, key: str, issued: Issued, now: float) -> None:
    """발급한 값을 그 만료까지 넣는다(Redis 수명 = 만료 − 지금). 못 넣어도 발급한 토큰은 쓴다(한 번 더 발급하지 않게)."""
    ttl_ms = int((issued[1] - now) * 1000)
    if ttl_ms <= 0:
        return
    try:
        client.set(key, json.dumps({"token": issued[0], "expires_at": issued[1]}), px=ttl_ms)
    except _ERRORS as exc:
        logger.warning("[채널톡] 발급한 토큰을 공유 캐시에 못 넣었다 err=%s", type(exc).__name__)


class _IssueFailed(Exception):
    """발급 함수가 낸 예외를 Redis 실패와 가르는 껍데기 — :func:`shared_token` 이 원래 예외를 다시 올린다."""


def _issue(issue: Callable[[], Issued]) -> Issued:
    """발급 — 실패는 :class:`_IssueFailed` 로 싸서 올린다(Redis 실패로 읽혀 한 번 더 발급하지 않게)."""
    try:
        return issue()
    except Exception as exc:
        raise _IssueFailed() from exc


def _unlock(redis: Any, lock: str, owner: str) -> None:
    """잡은 잠금을 푼다(그사이 수명이 끝나 남이 잡았으면 그대로). 못 풀면 수명이 끝나 풀린다."""
    try:
        _delete_if_same(redis, lock, owner)
    except _ERRORS as exc:
        logger.warning("[채널톡] 토큰 발급 잠금을 못 풀었다(수명이 끝나면 풀린다) err=%s", type(exc).__name__)


def shared_token(channel_id: str, issue: Callable[[], Issued], *, secret: str, client: Any = None,
                 now: Optional[Callable[[], float]] = None,
                 sleep: Optional[Callable[[float], None]] = None) -> Optional[Issued]:
    """채널의 공유 토큰 ``(토큰, 만료 유닉스 초)`` — 없으면 잠금을 잡은 한 프로세스만 ``issue()`` 로 발급해 넣는다.

    Args:
        channel_id: 채널톡 채널 id.
        issue: 발급 함수(``issueToken`` — 부르는 쪽의 것, 시험이 바꿔 끼운다).
        secret: 앱 비밀(열쇠의 앱 지문만 만든다 — 값은 어디에도 두지 않는다).
        client: Redis 클라이언트(시험 주입). 없으면 REDIS_URL 로 만든다.
        now · sleep: 시계 · 쉬기(시험 주입 — 없으면 부를 때의 ``time.time`` · ``time.sleep``).

    Returns:
        공유 토큰, 또는 Redis 가 없거나 실패하면 ``None``(부르는 쪽이 프로세스 캐시로 발급한다).

    Raises:
        ``issue()`` 가 낸 예외(발급 실패) — 잠금은 풀고 그대로 올린다.
    """
    redis = client if client is not None else _client()
    if redis is None:
        return None
    key = shared_key(channel_id, secret)
    lock = f"{key}:lock"
    try:
        return _shared(redis, key, lock, issue, now=now or time.time, sleep=sleep or _sleep)
    except _IssueFailed as failed:
        raise failed.__cause__ from None
    except _ERRORS as exc:
        logger.warning("[채널톡] 토큰 공유 캐시를 못 썼다 — 이 프로세스 캐시로 돈다 channel=%s err=%s", channel_id,
                       type(exc).__name__)
        return None


def _shared(redis: Any, key: str, lock: str, issue: Callable[[], Issued], *, now: Callable[[], float],
            sleep: Callable[[float], None]) -> Issued:
    """:func:`shared_token` 의 본문 — 읽기 → 잠금 → (다시 읽기 · 발급 · 넣기) 또는 기다리며 읽기."""
    found = _read(redis, key, now())
    if found is not None:
        return found
    owner, waited = uuid.uuid4().hex, 0.0
    while not redis.set(lock, owner, nx=True, px=LOCK_MS):
        if waited >= WAIT_SECONDS:
            logger.warning("[채널톡] 토큰 발급 잠금을 기다리다 넘겼다 — 이 프로세스가 발급한다")
            issued = _issue(issue)
            _store(redis, key, issued, now())
            return issued
        sleep(WAIT_STEP)
        waited += WAIT_STEP
        found = _read(redis, key, now())
        if found is not None:
            return found
    try:
        found = _read(redis, key, now())  # 잠금을 잡는 사이 다른 프로세스가 넣었을 수 있다
        if found is not None:
            return found
        issued = _issue(issue)
        _store(redis, key, issued, now())
        return issued
    finally:
        _unlock(redis, lock, owner)


def drop_shared_token(channel_id: str, stale_token: str, *, secret: str, client: Any = None) -> None:
    """채널톡이 거절한(401) 토큰이 공유 값이면 지운다 — 읽은 값과 같을 때만 지우는 한 걸음이라 그사이 다른 프로세스가 넣은 새
    토큰은 그대로 남는다."""
    redis = client if client is not None else _client()
    if redis is None:
        return
    key = shared_key(channel_id, secret)
    try:
        raw = redis.get(key)
        if raw is not None and json.loads(_text(raw)).get("token") == stale_token:
            _delete_if_same(redis, key, raw)
    except _ERRORS as exc:
        logger.warning("[채널톡] 죽은 공유 토큰을 못 지웠다 channel=%s err=%s", channel_id, type(exc).__name__)


def _text(raw: Any) -> str:
    """Redis 값 → 글(바이트면 UTF-8)."""
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw or "")


def _sleep(seconds: float) -> None:
    """기다리기 — 부를 때의 ``time.sleep``(시험이 바꿔 끼운다)."""
    time.sleep(seconds)

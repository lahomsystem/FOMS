"""채널톡 읽기 한도 — 채널마다 공유 양동이(Redis) · 429 쉼 표시 · ``Retry-After`` 읽기(원장 R1-16 · R4-17).

채널톡 Open API 한도는 채널마다 상담 목록 양동이 100 · 초당 10, 그 밖 1,000 · 초당 10 이고 넘으면 429 +
``Retry-After`` 다(설계서 2.5). 상담 에이전트 읽기는 그중 정해 둔 몫만 쓰고 나머지를 '상담 먼저' 버튼 ·
이름표(보내기 쪽)에 남긴다. 저장소에 나가는 요청용 공유 양동이가 없어(flask-limiter 는 들어오는 요청용,
네이버 ``CallSpacer`` 는 프로세스 안) 여기 두고, Redis 클라이언트는 대시보드 캐시와 같은 것을 쓴다.
"""

from __future__ import annotations

import datetime
import email.utils
import logging
import math
import threading
import time
from typing import Any, Callable, Mapping, Optional, Protocol

from redis.exceptions import RedisError

from foms.services.common.dashboard_cache import get_dashboard_redis

logger = logging.getLogger(__name__)

__all__ = [
    "BUCKET_LIST",
    "BUCKET_MESSAGE",
    "ChannelBudget",
    "LocalChannelBudget",
    "READ_BUDGET_PER_SECOND",
    "RedisChannelBudget",
    "default_budget",
    "note_remaining",
    "retry_after_seconds",
]

# ── 채널톡 읽기 한도(채널마다 공유 양동이) ───────────────────────────────
BUCKET_LIST = "list"  # 상담 목록 조회(채널톡 양동이 100 · 초당 10)
BUCKET_MESSAGE = "message"  # 그 밖(글 조회 — '상담 먼저' 버튼 · 이름표와 같은 1,000 · 초당 10 양동이)

#: 우리 읽기 몫(1초 칸마다 건수). 칸 경계에서 두 칸이 붙어도 초당 6 을 넘지 않아, 채널톡 한도(초당 10 —
#: 설계서 2.5) 안에 '상담 먼저' 버튼 · 이름표(보내기 쪽) 몫이 남는다(R1-16). 1초 칸(고정 창)을 고른 이유:
#: Redis 명령 셋(INCR · PEXPIRE · PTTL)만으로 원자적이고, 열쇠에 초가 들어 있어 죽어도 막힘이 남지 않는다.
READ_BUDGET_PER_SECOND: dict[str, int] = {BUCKET_LIST: 3, BUCKET_MESSAGE: 3}

_BUDGET_KEY_PREFIX = "foms:cs:chread:v1"
_WINDOW_TTL_MS = 2000
#: ``Retry-After`` 를 이만큼까지만 믿는다 — 이상한 값(무한대 · 아주 긴 값)이 그 채널 읽기를 오래 막지 않게.
MAX_RETRY_AFTER_SECONDS = 600.0
#: 남은 칸이 이 값 이하면 경고(x-ratelimit-remaining — 관측만).
RATE_LIMIT_WARN_REMAINING = 5


def _block_key(brand: str) -> str:
    """그 채널의 429 쉼 표시 열쇠(값은 의미 없고 남은 수명이 쉼 시간이다)."""
    return f"{_BUDGET_KEY_PREFIX}:block:{brand}"


def _window_key(brand: str, bucket: str, window: int) -> str:
    """그 채널 · 양동이의 1초 칸 열쇠(``window`` = 그 초의 epoch 초)."""
    return f"{_BUDGET_KEY_PREFIX}:win:{brand}:{bucket}:{window}"


class ChannelBudget(Protocol):
    """채널마다 나눠 쓰는 읽기 한도."""

    def acquire(self, brand: str, bucket: str) -> float:
        """한 칸을 받으면 0, 아니면 기다릴 초."""

    def block(self, brand: str, seconds: float) -> None:
        """429 를 받았다 — 그 채널 읽기를 ``seconds`` 동안 모두 쉬게 한다."""


class LocalChannelBudget:
    """프로세스 안 양동이 — Redis 가 없거나 죽었을 때만 쓴다(다른 프로세스와 나누지 못한다)."""

    def __init__(self, rates: Optional[Mapping[str, int]] = None, *,
                 clock: Callable[[], float] = time.time) -> None:
        """``rates`` 는 양동이마다 1초 몫(기본 :data:`READ_BUDGET_PER_SECOND`), ``clock`` 은 벽시계(시험 주입)."""
        self._rates = dict(rates or READ_BUDGET_PER_SECOND)
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: dict[tuple[str, str], tuple[int, int]] = {}
        self._blocked_until: dict[str, float] = {}

    def acquire(self, brand: str, bucket: str) -> float:
        """한 칸을 받으면 0, 쉬는 중이거나 이 초의 몫을 다 썼으면 기다릴 초."""
        with self._lock:
            now = self._clock()
            until = self._blocked_until.get(brand, 0.0)
            if until > now:
                return until - now
            window = int(now)
            start, count = self._windows.get((brand, bucket), (window, 0))
            count = (count if start == window else 0) + 1
            self._windows[(brand, bucket)] = (window, count)
            return 0.0 if count <= self._rates.get(bucket, 1) else (window + 1) - now

    def block(self, brand: str, seconds: float) -> None:
        """그 채널 읽기를 ``seconds`` 동안 쉬게 한다(더 긴 쉼이 이미 있으면 그대로)."""
        with self._lock:
            until = self._clock() + max(0.0, seconds)
            self._blocked_until[brand] = max(self._blocked_until.get(brand, 0.0), until)


class RedisChannelBudget:
    """채널마다 Redis 공유 양동이(1초 칸 + 429 쉼 표시) — 프로세스 · 서비스가 같은 몫을 나눠 쓴다.

    Redis 오류면 프로세스 안 양동이로 내려가며 경고를 한 번 남기고, 살아나면 다시 올라온다.
    """

    def __init__(self, client: Any, rates: Optional[Mapping[str, int]] = None, *,
                 clock: Callable[[], float] = time.time,
                 fallback: Optional[LocalChannelBudget] = None) -> None:
        """``client`` 는 Redis 클라이언트(기본은 대시보드 캐시와 같은 것), ``fallback`` 은 Redis 오류 때 쓸 양동이."""
        self._client = client
        self._rates = dict(rates or READ_BUDGET_PER_SECOND)
        self._clock = clock
        self._fallback = fallback or LocalChannelBudget(self._rates, clock=clock)
        self._degraded = False

    def acquire(self, brand: str, bucket: str) -> float:
        """한 칸을 받으면 0, 쉬는 중이거나 이 초의 몫을 다 썼으면 기다릴 초."""
        try:
            blocked_ms = int(self._client.pttl(_block_key(brand)) or 0)
            if blocked_ms > 0:
                wait = blocked_ms / 1000
            else:
                now = self._clock()
                window = int(now)
                key = _window_key(brand, bucket, window)
                pipe = self._client.pipeline(transaction=True)
                pipe.incr(key)
                pipe.pexpire(key, _WINDOW_TTL_MS)
                count = int(pipe.execute()[0])
                wait = 0.0 if count <= self._rates.get(bucket, 1) else (window + 1) - now
        except RedisError as exc:
            self._degrade(exc)
            return self._fallback.acquire(brand, bucket)
        self._recover()
        return wait

    def block(self, brand: str, seconds: float) -> None:
        """그 채널 읽기를 모든 프로세스가 ``seconds`` 동안 쉬게 한다(더 긴 쉼이 이미 있으면 그대로)."""
        self._fallback.block(brand, seconds)
        ms = max(1, int(seconds * 1000))
        try:
            if int(self._client.pttl(_block_key(brand)) or 0) < ms:
                self._client.set(_block_key(brand), "1", px=ms)
        except RedisError as exc:
            self._degrade(exc)

    def _degrade(self, exc: Exception) -> None:
        """Redis 오류 — 처음 한 번만 경고를 남기고 프로세스 안 양동이로 내려간다(오류 종류만, 내용 없음)."""
        if not self._degraded:
            logger.warning("[CS 상담] 채널톡 읽기 양동이 Redis 실패 — 이 프로세스 안 양동이로 내려감(%s)",
                           type(exc).__name__)
        self._degraded = True

    def _recover(self) -> None:
        """Redis 가 다시 대답했다 — 내려가 있었으면 한 줄 남기고 공유 양동이로 돌아온다."""
        if self._degraded:
            logger.info("[CS 상담] 채널톡 읽기 양동이 Redis 다시 씀")
        self._degraded = False


def default_budget() -> ChannelBudget:
    """대시보드 캐시와 같은 Redis 클라이언트가 있으면 공유 양동이, 없으면 프로세스 안 양동이(경고)."""
    client = get_dashboard_redis()
    if client is None:
        logger.warning("[CS 상담] Redis 없음 — 채널톡 읽기 한도를 이 프로세스 안에서만 지킨다")
        return LocalChannelBudget()
    return RedisChannelBudget(client)


# ── 응답 머리값(429 · 남은 칸) ───────────────────────────────────────────
def _header(response: Any, name: str) -> Optional[str]:
    """응답 머리값(대소문자 무관). 없으면 ``None``."""
    headers = getattr(response, "headers", None) or {}
    value = headers.get(name)
    if value is None:
        value = headers.get(name.lower())
    return None if value is None else str(value).strip()


def retry_after_seconds(response: Any) -> Optional[float]:
    """``Retry-After``(초 또는 HTTP 날짜) → 기다릴 초(:data:`MAX_RETRY_AFTER_SECONDS` 까지). 없거나 못 읽으면 ``None``."""
    raw = _header(response, "Retry-After")
    if not raw:
        return None
    try:
        seconds: Optional[float] = float(raw)
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
        utc = datetime.timezone.utc
        when = when if when.tzinfo else when.replace(tzinfo=utc)
        seconds = (when - datetime.datetime.now(utc)).total_seconds()
    if seconds is None or not math.isfinite(seconds):
        return None
    return min(max(0.0, seconds), MAX_RETRY_AFTER_SECONDS)


def note_remaining(brand: str, bucket: str, response: Any) -> None:
    """남은 칸(x-ratelimit-remaining)이 적으면 경고만 남긴다 — 호출 동작은 바뀌지 않는다."""
    raw = _header(response, "x-ratelimit-remaining")
    try:
        remaining = int(raw) if raw is not None else None
    except ValueError:
        return
    if remaining is not None and remaining <= RATE_LIMIT_WARN_REMAINING:
        logger.warning("[CS 상담] 채널톡 남은 칸 %d brand=%s bucket=%s", remaining, brand, bucket)

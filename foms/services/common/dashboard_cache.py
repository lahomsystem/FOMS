"""
Dashboard read-model slice cache (Redis JSON DTO only).

- 전체 HTML 캐시 금지. dict/list/primitive JSON 직렬화 가능한 DTO만 저장.
- Redis 장애 시 compute 경로로 fail-open (경고 로그 필수).
- 무효화는 TTL 1차, family 단위 삭제는 invalidate_dashboard_family().

Key: ``foms:dashcache:v1:<page>:<slice>:<fp_hash>``
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Callable, Final, TypeVar

logger = logging.getLogger(__name__)


def _ensure_dashcache_log_to_stderr() -> None:
    """
    Gunicorn 등에서 run.py의 basicConfig가 없을 때, [DashCache] INFO가 루트 WARNING에 막혀
    Deploy Logs에 안 보이는 문제를 막는다. 모듈 로거에만 stderr 핸들러를 한 번 붙인다.

    pytest(caplog)는 동일 로거에 핸들러가 있으면 캡처가 어긋나므로 테스트 세션에서는 생략한다.
    """
    if (os.environ.get("PYTEST_CURRENT_TEST") or "").strip():
        return
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


_dashcache_stderr_configured = False


def _lazy_ensure_dashcache_log_to_stderr() -> None:
    """import 시점이 아니라 첫 요청 시점에 설정(pytest 환경변수가 그때 확실함)."""
    global _dashcache_stderr_configured
    if _dashcache_stderr_configured:
        return
    _dashcache_stderr_configured = True
    _ensure_dashcache_log_to_stderr()


T = TypeVar("T")

KEY_VERSION: Final[str] = "v1"
CACHE_KEY_PREFIX: Final[str] = f"foms:dashcache:{KEY_VERSION}"

# TTL 기본값(초) — mutation 후 family invalidation(invalidate_dashboard_family)이
# 신선도를 보장하므로, 조회-only 상황에서 TTL은 miss 빈도를 낮추는 쪽으로 넉넉히
# 둔다. 짧은 TTL은 잦은 만료 → read-model 재계산(2-phase 쿼리+DTO 직렬화) 반복으로
# 이어지므로, 쓰기 시 무효화가 있는 슬라이스는 상향해 재계산 비용을 줄인다.
# (2026-07-02 상향: miss 재계산 오버헤드 완화. 네트워크 tail과는 무관.)
TTL_SUMMARY_COUNTS: Final[int] = 300
TTL_PANEL_ROWS: Final[int] = 300
TTL_ATTACHMENT_COUNT_MAP: Final[int] = 120
TTL_ASSIGNEE_OPTIONS_LOOKUP: Final[int] = 180
TTL_PAYLOAD_ASSEMBLY: Final[int] = 90

# Singleflight(캐시 stampede 방지): TTL 만료 순간 동시 요청이 전부 재계산해 DB로
# 몰리는 herd를 막는다. miss 시 짧은 Redis 락을 잡은 요청만 계산하고, 나머지는
# 잠깐 대기하며 채워진 캐시를 읽는다. Redis에 락 API가 없거나 오류면 fail-open
# (락 없이 계산) — 절대 무한 대기하지 않는다(사용자 응답 지연 금지).
_SINGLEFLIGHT_LOCK_TTL_S: Final[int] = 10
_SINGLEFLIGHT_WAIT_MAX_S: Final[float] = 3.0
_SINGLEFLIGHT_POLL_S: Final[float] = 0.05

_ENV_FLAG: Final[str] = "FOMS_DASHBOARD_MICRO_CACHE_ENABLED"
_REDIS_URL_ENV: Final[str] = "REDIS_URL"

_redis_lock = threading.Lock()
# None: 미초기화, False: 연결 실패(프로세스 내 재시도 안 함), 그 외: redis.Redis
_redis_client: Any | None = None

__all__ = [
    "KEY_VERSION",
    "CACHE_KEY_PREFIX",
    "TTL_SUMMARY_COUNTS",
    "TTL_PANEL_ROWS",
    "TTL_ATTACHMENT_COUNT_MAP",
    "TTL_ASSIGNEE_OPTIONS_LOOKUP",
    "TTL_PAYLOAD_ASSEMBLY",
    "is_dashboard_micro_cache_enabled",
    "build_dashboard_cache_key",
    "get_dashboard_redis",
    "get_or_compute_dashboard_slice",
    "invalidate_dashboard_family",
    "invalidate_all_dashboard_slice_caches",
    "reset_dashboard_cache_runtime_for_tests",
]


def _env_truthy(name: str) -> bool:
    """환경변수가 켜짐으로 해석되는지 (1/true/yes/on, 대소문자 무시)."""
    raw = (os.environ.get(name) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def is_dashboard_micro_cache_enabled() -> bool:
    """
    REDIS_URL 존재 + FOMS_DASHBOARD_MICRO_CACHE_ENABLED 가 truthy 일 때만 캐시 사용.

    그 외(플래그 미설정/거짓/Redis 없음)는 항상 bypass.
    """
    if not (os.environ.get(_REDIS_URL_ENV) or "").strip():
        return False
    return _env_truthy(_ENV_FLAG)


def get_dashboard_redis() -> Any | None:
    """
    대시보드 micro-cache 전용 Redis 클라이언트.

    연결 실패 시 경고 로그 후 None (호출부는 compute로 fallback).
    프로세스당 최초 1회 성공 시 클라이언트 캐시; 실패 시 이후 None 고정.
    """
    global _redis_client
    if _redis_client is not None:
        return None if _redis_client is False else _redis_client
    with _redis_lock:
        if _redis_client is not None:
            return None if _redis_client is False else _redis_client
        redis_url = (os.environ.get(_REDIS_URL_ENV) or "").strip()
        if not redis_url:
            _redis_client = False
            return None
        try:
            from redis import Redis

            client = Redis.from_url(redis_url, decode_responses=True)
            # 연결 확인 (lazy 연결 대비 ping)
            client.ping()
            _redis_client = client
            return client
        except Exception as exc:
            logger.warning(
                "[DashCache] Redis client init failed, cache bypass: %s",
                exc,
                exc_info=True,
            )
            _redis_client = False
            return None


def reset_dashboard_cache_runtime_for_tests() -> None:
    """단위 테스트 전용: Redis 클라이언트 캐시 초기화."""
    global _redis_client
    _redis_client = None


def _fingerprint_hash(fingerprint: dict[str, Any]) -> str:
    """정규 JSON → SHA-256 hex 앞 20자."""
    canonical = json.dumps(fingerprint, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def build_dashboard_cache_key(page: str, slice_name: str, fingerprint: dict[str, Any]) -> str:
    """
    캐시 키 문자열 생성.

    Args:
        page: ``orders`` | ``measurement`` | ``shipment`` 등.
        slice_name: summary_counts, panel_rows, attachment_map 등.
        fingerprint: 사용자/가시성/필터 등 변동 요소 (JSON 직렬화 가능한 dict).
    """
    page_n = str(page).strip()
    slice_n = str(slice_name).strip()
    if not page_n or not slice_n:
        raise ValueError("page and slice_name must be non-empty")
    h = _fingerprint_hash(fingerprint)
    return f"{CACHE_KEY_PREFIX}:{page_n}:{slice_n}:{h}"


def _json_dumps_dto(value: Any) -> str:
    """DTO를 JSON 문자열로 직렬화 (캐시 저장용)."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads_dto(raw: str) -> Any:
    return json.loads(raw)


def _release_singleflight_lock(r: Any, lock_key: str, lock_token: str) -> None:
    """singleflight 락을 **소유 토큰이 일치할 때만** 해제(best-effort, 실패 무시).

    lock_token이 빈 문자열이면(락 미획득/미지원) 아무 것도 하지 않는다. 토큰 비교로
    자신이 잡은 락만 지워, 팔로워가 리더의 락을 실수로 지우는 것을 방지한다.
    """
    if not lock_token:
        return
    try:
        if r.get(lock_key) == lock_token:
            r.delete(lock_key)
    except Exception:
        pass


def get_or_compute_dashboard_slice(
    cache_key: str,
    ttl_seconds: int,
    compute: Callable[[], T],
    *,
    page: str,
    slice_name: str,
) -> T:
    """
    캐시 hit 시 역직렬화 값 반환, miss/장애 시 compute() 결과를 저장 후 반환.

    - 캐시 비활성/Redis 없음/오류 시 항상 compute()만 사용.
    - 저장 값은 JSON으로 round-trip 가능한 DTO여야 함 (그렇지 않으면 저장 생략 + 경고).
    - 계획 §1.2.9: hit/miss 외 **compute_ms**를 info 로그로 남긴다 (관측용).
    """
    _lazy_ensure_dashcache_log_to_stderr()
    key_suffix = cache_key.rsplit(":", 1)[-1]

    def _run_compute_and_log(result: str, used_cache: bool) -> T:
        t0 = time.perf_counter()
        out = compute()
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "[DashCache] page=%s slice=%s result=%s compute_ms=%s key_suffix=%s cache=%s",
            page,
            slice_name,
            result,
            elapsed_ms,
            key_suffix,
            "on" if used_cache else "off",
        )
        return out

    if not is_dashboard_micro_cache_enabled():
        return _run_compute_and_log("bypass", False)

    r = get_dashboard_redis()
    if r is None:
        return _run_compute_and_log("bypass", False)

    ttl = max(int(ttl_seconds), 1)

    try:
        cached = r.get(cache_key)
        if cached is not None:
            try:
                out = _json_loads_dto(cached)
                logger.info(
                    "[DashCache] page=%s slice=%s result=hit compute_ms=0 key_suffix=%s cache=on",
                    page,
                    slice_name,
                    key_suffix,
                )
                return out  # type: ignore[return-value]
            except Exception as exc:
                logger.warning(
                    "[DashCache] deserialize failed, recomputing: %s",
                    exc,
                    exc_info=True,
                )
    except Exception as exc:
        logger.warning(
            "[DashCache] redis get failed, bypass: %s",
            exc,
            exc_info=True,
        )

    # --- miss: singleflight로 stampede 방지 (fail-open, 무한 대기 금지) ---
    lock_key = f"{cache_key}:sf"
    lock_token = os.urandom(8).hex()
    try:
        got_lock = bool(r.set(lock_key, lock_token, nx=True, ex=_SINGLEFLIGHT_LOCK_TTL_S))
    except Exception:
        # Redis에 set(nx) 미지원/오류 → 락 없이 진행(fail-open)
        got_lock = True
        lock_token = ""

    if not got_lock:
        # 다른 요청이 계산 중. 잠깐 대기하며 캐시가 채워지길 기다렸다가 읽는다.
        # (gevent monkey-patch 하에서 time.sleep은 그린렛 양보라 워커를 막지 않는다.)
        lock_token = ""  # 팔로워는 락을 소유하지 않으므로 해제 대상 아님
        deadline = time.perf_counter() + _SINGLEFLIGHT_WAIT_MAX_S
        while time.perf_counter() < deadline:
            time.sleep(_SINGLEFLIGHT_POLL_S)
            try:
                cached = r.get(cache_key)
            except Exception:
                break
            if cached is not None:
                try:
                    out = _json_loads_dto(cached)
                    logger.info(
                        "[DashCache] page=%s slice=%s result=hit_sf compute_ms=0 key_suffix=%s cache=on",
                        page,
                        slice_name,
                        key_suffix,
                    )
                    return out  # type: ignore[return-value]
                except Exception:
                    break
        # 대기 타임아웃/역직렬화 실패 → 직접 계산(fail-open, 사용자 무한대기 금지)

    t0 = time.perf_counter()
    computed = compute()
    compute_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "[DashCache] page=%s slice=%s result=miss compute_ms=%s key_suffix=%s cache=on",
        page,
        slice_name,
        compute_ms,
        key_suffix,
    )

    try:
        payload = _json_dumps_dto(computed)
        # round-trip 검증 — ORM 등 비직렬화 객체가 섞이면 캐시하지 않음
        _json_loads_dto(payload)
    except (TypeError, ValueError) as exc:
        logger.warning(
            "[DashCache] value not JSON-serializable, skip cache: %s",
            exc,
            exc_info=True,
        )
        _release_singleflight_lock(r, lock_key, lock_token)
        return computed

    try:
        r.setex(cache_key, ttl, payload)
        logger.debug(
            "[DashCache] stored page=%s slice=%s key_suffix=%s ttl=%s",
            page,
            slice_name,
            key_suffix,
            ttl,
        )
    except Exception as exc:
        logger.warning(
            "[DashCache] redis set failed (response still returned): %s",
            exc,
            exc_info=True,
        )

    _release_singleflight_lock(r, lock_key, lock_token)
    return computed


def invalidate_dashboard_family(family: str) -> int:
    """
    ``foms:dashcache:v1:<family>:*`` 패턴 키 삭제. commit 성공 후에만 호출할 것.

    Returns:
        삭제한 키 개수 (대략치).
    """
    family_n = str(family).strip()
    if not family_n:
        return 0
    if not is_dashboard_micro_cache_enabled():
        return 0
    r = get_dashboard_redis()
    if r is None:
        return 0

    pattern = f"{CACHE_KEY_PREFIX}:{family_n}:*"
    deleted = 0
    try:
        for key in r.scan_iter(match=pattern, count=500):
            try:
                r.delete(key)
                deleted += 1
                if deleted >= 10000:
                    logger.warning(
                        "[DashCache] invalidate_family cap reached for %s", family_n
                    )
                    break
            except Exception as exc:
                logger.warning(
                    "[DashCache] delete key failed during invalidate: %s",
                    exc,
                    exc_info=True,
                )
    except Exception as exc:
        logger.warning(
            "[DashCache] scan/invalidate failed: %s",
            exc,
            exc_info=True,
        )
    if deleted:
        logger.info("[DashCache] invalidated family=%s keys=%s", family_n, deleted)
    return deleted


def invalidate_all_dashboard_slice_caches() -> int:
    """
    ``orders`` / ``measurement`` / ``shipment`` / ``construction`` / ``history`` /
    ``production`` / ``drawing`` 대시보드 read-slice 캐시를 한 번에 무효화.

    DB commit이 성공한 뒤에만 호출할 것.
    """
    total = 0
    for fam in ("orders", "measurement", "shipment", "construction", "history", "production", "drawing"):
        total += invalidate_dashboard_family(fam)
    return total

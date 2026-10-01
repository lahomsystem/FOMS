"""
Dashboard read-model slice cache (Redis JSON DTO only).

- 전체 HTML 캐시 금지. dict/list/primitive JSON 직렬화 가능한 DTO만 저장.
- Redis 장애 시 compute 경로로 fail-open (경고 로그 필수).
- 무효화는 TTL 1차, family 단위 삭제는 invalidate_dashboard_family().

Key: ``foms:dashcache:v1:<page>:<slice>:<fp_hash>``
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import re
import threading
import time
from collections.abc import Iterable, Mapping
from typing import Any, Callable, Final, TypeVar

from foms.services.datetime_kst import get_today_kst
from foms.services.erp_order_flags import is_erp_draft_structured_data

# AUDIT-LOG T1: 과거 이 자리에 있던 모듈 전용 stderr 핸들러(국소 우회)는 제거됐다.
# root 로깅은 foms.platform.logging_setup.configure_logging이 전역으로 구성하므로
# 모듈 로거는 기본 propagate(True)로 root 핸들러에 전파되면 충분하다.
logger = logging.getLogger(__name__)


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

# family 무효화: SCAN 한 번에 훑는 힌트 수 · UNLINK 한 번에 지우는 키 수 · 한 family 상한.
_INVALIDATE_SCAN_COUNT: Final[int] = 500
_INVALIDATE_DELETE_BATCH: Final[int] = 500
_INVALIDATE_MAX_KEYS: Final[int] = 10000

_ENV_FLAG: Final[str] = "FOMS_DASHBOARD_MICRO_CACHE_ENABLED"
_REDIS_URL_ENV: Final[str] = "REDIS_URL"

# 슬라이스 관측(진단) — 요청 하나가 어떤 슬라이스를 hit/miss 했고 재계산에 몇 ms 를
# 썼는지 모은다. 로그만으로는 배포 환경별 로그 접근 권한에 막혀 확인이 어려워, 라우트가
# 이 값을 진단 헤더로 노출할 수 있게 한다(EPT-B7 render_ms 와 같은 성격: 진단용이며
# 권한 판정에 쓰지 않는다). 값은 슬라이스명·결과·ms 뿐이라 업무 데이터가 없다.
_SLICE_OBS_KEY: Final[str] = "_foms_dash_slice_obs"

# --- 무효화 스코프 상수 (Wave 2) ------------------------------------------------
# family 문자열 = build_dashboard_cache_key(page=...) 의 page 인자와 1:1. 오타 시
# 무효화 누락 → stale 버그이므로 항상 이 상수를 통해서만 참조한다.
DASHBOARD_FAMILY_ORDERS: Final[str] = "orders"
DASHBOARD_FAMILY_MEASUREMENT: Final[str] = "measurement"
DASHBOARD_FAMILY_SHIPMENT: Final[str] = "shipment"
DASHBOARD_FAMILY_CONSTRUCTION: Final[str] = "construction"
DASHBOARD_FAMILY_HISTORY: Final[str] = "history"
DASHBOARD_FAMILY_PRODUCTION: Final[str] = "production"
DASHBOARD_FAMILY_DRAWING: Final[str] = "drawing"

ALL_DASHBOARD_FAMILIES: Final[tuple[str, ...]] = (
    DASHBOARD_FAMILY_ORDERS,
    DASHBOARD_FAMILY_MEASUREMENT,
    DASHBOARD_FAMILY_SHIPMENT,
    DASHBOARD_FAMILY_CONSTRUCTION,
    DASHBOARD_FAMILY_HISTORY,
    DASHBOARD_FAMILY_PRODUCTION,
    DASHBOARD_FAMILY_DRAWING,
)

# 첨부(OrderAttachment) mutation 시 무효화할 family 집합.
#
# 근거(각 family read-model/대시보드가 첨부를 실제로 읽는지 코드로 확정):
#   - orders: dashboard_read_model.compute_orders_attachment_assignee_maps 가
#     OrderAttachment 카운트 집계 + 모바일 큐 미리보기(batch_resolve_queue_attachment_preview_items).
#   - measurement: erp_product_items.build_product_items_for_orders 가 measurement/
#     measure_photo/photo 첨부를 조회, 모바일 큐 행이 첨부 카운트·미리보기 사용.
#   - construction: construction_dashboard_display / construction_read_model 이
#     OrderAttachment 미리보기·카운트 조회.
#   - production: production_read_model.fetch_production_attachment_counts +
#     production_dashboard_display has_media.
#   - drawing: drawing_workbench_display 가 OrderAttachment.thumbnail_key 조회.
#   - shipment: shipment_read_model 자체엔 첨부 read 없으나 모바일 v2 큐
#     (build_shipment_mobile_queue_rows → build_mobile_queue_order_row)가 첨부
#     카운트·미리보기를 읽으므로 포함.
#   - history: history_read_model / history 라우트에 첨부 read 없음 → 제외.
# 애매하면 포함(과무효화 > 과소무효화) 원칙을 따른다.
ATTACHMENT_DASHBOARD_FAMILIES: Final[frozenset[str]] = frozenset(
    {
        DASHBOARD_FAMILY_ORDERS,
        DASHBOARD_FAMILY_MEASUREMENT,
        DASHBOARD_FAMILY_SHIPMENT,
        DASHBOARD_FAMILY_CONSTRUCTION,
        DASHBOARD_FAMILY_PRODUCTION,
        DASHBOARD_FAMILY_DRAWING,
    }
)

# erp_stage_code(=workflow.stage) → 해당 단계 주문이 나타나는 도메인 대시보드 family.
# 값 SSOT: foms.services.orders.erp_policy_constants.STAGE_LABELS /
# STAGE_NAME_TO_CODE(코드=RECEIVED/MEASURE/DRAWING/CONFIRM/PRODUCTION/CONSTRUCTION/
# CS/COMPLETED/AS/AS_RECEIVED/AS_COMPLETED). 매핑 없는 stage는 폴백(broad)로 처리한다.
_STAGE_CODE_TO_FAMILY: Final[dict[str, str]] = {
    "MEASURE": DASHBOARD_FAMILY_MEASUREMENT,
    "DRAWING": DASHBOARD_FAMILY_DRAWING,
    "CONFIRM": DASHBOARD_FAMILY_PRODUCTION,
    "PRODUCTION": DASHBOARD_FAMILY_PRODUCTION,
    "CONSTRUCTION": DASHBOARD_FAMILY_CONSTRUCTION,
    "CS": DASHBOARD_FAMILY_CONSTRUCTION,
    "AS": DASHBOARD_FAMILY_CONSTRUCTION,
    "AS_RECEIVED": DASHBOARD_FAMILY_CONSTRUCTION,
    "AS_COMPLETED": DASHBOARD_FAMILY_HISTORY,
    "COMPLETED": DASHBOARD_FAMILY_HISTORY,
    # 운영 데이터에 한글 stage 값이 실재한다(근거: production_read_model.py 기본 필터가
    # '"고객컨펌"/"생산"/"시공"'과 영문 코드를 이중으로 매칭). 미등록 시 해당 주문은 매번
    # broad 폴백으로 빠져 스코프 무효화 실효가 반감된다. 검증된 값만 등록(그 외 한글
    # stage는 폴백 유지 — 오매핑보다 broad가 안전).
    "고객컨펌": DASHBOARD_FAMILY_PRODUCTION,
    "생산": DASHBOARD_FAMILY_PRODUCTION,
    "시공": DASHBOARD_FAMILY_CONSTRUCTION,
}

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
    "format_slice_observations",
    "get_dashboard_redis",
    "get_or_compute_dashboard_slice",
    "record_slice_observation",
    "invalidate_dashboard_family",
    "invalidate_dashboard_families",
    "invalidate_order_dashboard_families",
    "stage_code_to_dashboard_family",
    "invalidate_all_dashboard_slice_caches",
    "invalidate_dashboard_caches_after_delete_transition",
    "order_dashboard_cache_axes",
    "dashboard_families_for_order_save",
    "invalidate_dashboard_families_for_order_save",
    "dashboard_families_for_schedule_change",
    "CONSTRUCTION_SUMMARY_STAGE_CODES",
    "PRODUCTION_SUMMARY_STAGE_CODES",
    "DASHBOARD_DATE_WINDOW_DAYS",
    "dashboard_families_for_mutation_intent",
    "register_dashboard_cache_invalidation_listener",
    "MUTATION_CACHE_INTENT_KEY",
    "reset_dashboard_cache_runtime_for_tests",
    "ALL_DASHBOARD_FAMILIES",
    "ATTACHMENT_DASHBOARD_FAMILIES",
    "DASHBOARD_FAMILY_ORDERS",
    "DASHBOARD_FAMILY_MEASUREMENT",
    "DASHBOARD_FAMILY_SHIPMENT",
    "DASHBOARD_FAMILY_CONSTRUCTION",
    "DASHBOARD_FAMILY_HISTORY",
    "DASHBOARD_FAMILY_PRODUCTION",
    "DASHBOARD_FAMILY_DRAWING",
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

            # socket_timeout: Redis 응답 지연 시 요청이 무한 대기하지 않도록 상한.
            # 초과 시 예외 → 기존 fail-open(compute 경로)이 흡수한다.
            client = Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=2,
                socket_connect_timeout=2,
            )
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
        pass  # failopen: intentional: 분산 락 해제 best-effort; Redis 오류 시 TTL 만료


def record_slice_observation(slice_name: str, result: str, compute_ms: int) -> None:
    """요청 컨텍스트에 슬라이스 관측을 누적한다(진단 전용, 실패 무시).

    요청 밖(잡·스크립트)에서 호출되면 Flask 컨텍스트가 없으므로 조용히 건너뛴다 —
    관측 실패가 대시보드 응답을 깨뜨려선 안 된다.

    Args:
        slice_name: summary_counts 등 슬라이스 이름.
        result: hit | miss | bypass | ...
        compute_ms: 재계산에 쓴 밀리초(hit 은 0).
    """
    try:
        from flask import g, has_request_context

        if not has_request_context():
            return
        observations = getattr(g, _SLICE_OBS_KEY, None)
        if observations is None:
            observations = []
            setattr(g, _SLICE_OBS_KEY, observations)
        observations.append((slice_name, result, int(compute_ms)))
    except Exception:  # noqa: BLE001 - 진단 실패는 응답에 영향을 주지 않는다
        logger.debug("[DashCache] slice observation skipped", exc_info=True)


def format_slice_observations() -> str:
    """이번 요청의 슬라이스 관측을 헤더 값 한 줄로 만든다.

    Returns:
        ``summary_counts=miss:87;attachment_counts=hit:0`` 형태. 관측이 없으면 빈 문자열.
    """
    try:
        from flask import g, has_request_context

        if not has_request_context():
            return ""
        observations = getattr(g, _SLICE_OBS_KEY, None) or []
        return ";".join(f"{name}={result}:{ms}" for name, result, ms in observations)
    except Exception:  # noqa: BLE001 - 진단 실패는 응답에 영향을 주지 않는다
        logger.debug("[DashCache] slice observation format skipped", exc_info=True)
        return ""


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
        record_slice_observation(slice_name, result, elapsed_ms)
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
                record_slice_observation(slice_name, "hit", 0)
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
                    record_slice_observation(slice_name, "hit_sf", 0)
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
    record_slice_observation(slice_name, "miss", compute_ms)

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
    # 키마다 DELETE 를 보내면 저장 요청 하나가 Redis 를 키 수만큼 왕복했다(P1-2, 2026-10-01).
    # SCAN 으로 모은 키를 묶음째 UNLINK(값 해제는 Redis 가 백그라운드로) 한 번에 지운다.
    # 무엇을 지우는지는 그대로다 — 같은 패턴, 같은 상한.
    deleted = 0
    scanned = 0
    batch: list[str] = []

    def _flush_batch() -> None:
        nonlocal deleted
        if not batch:
            return
        keys = list(batch)
        batch.clear()
        try:
            unlink = getattr(r, "unlink", None)
            removed = unlink(*keys) if callable(unlink) else r.delete(*keys)
            deleted += removed if isinstance(removed, int) else len(keys)
        except Exception as exc:
            logger.warning(
                "[DashCache] delete batch failed during invalidate: %s",
                exc,
                exc_info=True,
            )

    try:
        for key in r.scan_iter(match=pattern, count=_INVALIDATE_SCAN_COUNT):
            batch.append(key)
            scanned += 1
            if len(batch) >= _INVALIDATE_DELETE_BATCH:
                _flush_batch()
            if scanned >= _INVALIDATE_MAX_KEYS:
                logger.warning(
                    "[DashCache] invalidate_family cap reached for %s", family_n
                )
                break
        _flush_batch()
    except Exception as exc:
        logger.warning(
            "[DashCache] scan/invalidate failed: %s",
            exc,
            exc_info=True,
        )
    if deleted:
        logger.info("[DashCache] invalidated family=%s keys=%s", family_n, deleted)
    return deleted


def invalidate_dashboard_families(*families: str) -> int:
    """여러 family를 한 번에 무효화(중복 제거). commit 성공 후에만 호출할 것.

    Tier B/C/D 및 도메인-스코프 mutation이 broad 대신 필요한 family만 지우도록 하는
    배치 진입점. 빈 문자열/중복은 무시한다.

    Args:
        *families: 무효화할 family 문자열들(DASHBOARD_FAMILY_* 상수 사용 권장).

    Returns:
        삭제한 키 개수 합(대략치).
    """
    seen: set[str] = set()
    total = 0
    for fam in families:
        fam_n = str(fam).strip()
        if not fam_n or fam_n in seen:
            continue
        seen.add(fam_n)
        total += invalidate_dashboard_family(fam_n)
    return total


def stage_code_to_dashboard_family(stage_code: str | None) -> str | None:
    """erp_stage_code(=workflow.stage) → 도메인 대시보드 family. 미매핑이면 None.

    None 반환은 호출부가 "안전하게 broad" 폴백을 택하라는 신호다(값 미상 = stale 최악).
    """
    if not stage_code:
        return None
    return _STAGE_CODE_TO_FAMILY.get(str(stage_code).strip().upper())


def invalidate_order_dashboard_families(order: Any, extra: tuple[str, ...] = ()) -> int:
    """단일 주문 mutation 후, ``orders`` + 주문 현재 단계 family(+extra)만 무효화.

    주문의 ``erp_stage_code``(workflow.stage 동기 컬럼)로 도메인 family를 매핑한다.
    stage가 None/미매핑이면 stale이 최악이므로 안전하게 **전체(broad)** 무효화로
    폴백한다. 출고일/완료 등 특정 필드가 걸린 경우 호출부가 ``extra``로 shipment/
    history 등을 추가한다.

    Args:
        order: erp_stage_code 속성을 갖는 Order 객체.
        extra: 추가로 무효화할 family(예: 출고일 변경 시 shipment).

    Returns:
        삭제한 키 개수 합(대략치).
    """
    stage_code = getattr(order, "erp_stage_code", None)
    family = stage_code_to_dashboard_family(stage_code)
    if family is None:
        # 단계 미상/미매핑 → 어느 탭에 나타날지 알 수 없으므로 broad.
        return invalidate_all_dashboard_slice_caches()
    families = [DASHBOARD_FAMILY_ORDERS, family, *extra]
    return invalidate_dashboard_families(*families)


def invalidate_all_dashboard_slice_caches() -> int:
    """
    ``orders`` / ``measurement`` / ``shipment`` / ``construction`` / ``history`` /
    ``production`` / ``drawing`` 대시보드 read-slice 캐시를 한 번에 무효화.

    DB commit이 성공한 뒤에만 호출할 것.
    """
    total = 0
    for fam in ALL_DASHBOARD_FAMILIES:
        total += invalidate_dashboard_family(fam)
    return total


def invalidate_dashboard_caches_after_delete_transition(reason: str) -> int:
    """주문 soft delete/복원 직후 대시보드 read-slice + AS 추천 캐시를 무효화한다.

    삭제/복원은 주문이 **모든** 탭에서 사라지거나 다시 나타나는 전이다. stage family로
    좁히면 다른 대시보드(실측 패널 카운트 등)에 유령 행이 TTL(최대 300초) 동안 남는다
    — 2026-08-10 운영 사고(삭제한 주문이 실측 날짜별 집계에 계속 잡힘)의 원인이다.
    그래서 status 변경과 동일하게 broad 무효화로 처리한다(삭제/복원은 저빈도 이벤트라
    재계산 비용보다 stale 비용이 크다).

    DB commit이 성공한 뒤에만 호출할 것.

    Args:
        reason: AS 추천 캐시 무효화 로그에 남길 사유(예: ``"order_delete"``).

    Returns:
        삭제한 대시보드 슬라이스 키 개수(대략치).
    """
    total = invalidate_all_dashboard_slice_caches()
    # lazy import: shipment_as_recommendation_cache가 이 모듈을 import하므로 순환 회피.
    from foms.services.shipment_as_recommendation_cache import (
        invalidate_shipment_as_recommendation_cache,
    )

    invalidate_shipment_as_recommendation_cache(reason=reason)
    return total


# --- 단건 주문 저장 → 무효화 범위 (P1-2, 2026-10-01) ----------------------------------
# 저장 경로 13곳이 손으로 broad(7 family 전부)를 불러 운영 하루 500~1,300번 캐시가 통째로
# 비워졌다(적중률 38~53%). 판정 기준은 하나다: **그 family 의 캐시된 slice DTO 가 이
# 주문의 바뀐 값을 담을 수 있는가.** 주문이 담기는 자리는 단계만으로 정해지지 않는다 —
# 실측·출고 패널은 날짜 창으로 담고(단계 무관), 시공·생산 숫자판은 자기 탭 밖 단계(완료·
# 시공)도 함께 센다. 그래서 단계 family 에 더해 날짜·단계 범위·검색/담당 필드를 저장 전후로
# 비교한다. 소속 자체가 바뀌는 전이(삭제·초안 승격·status 변경·미지의 단계)는 broad 그대로다.
#
# 남는 틈(의도): 지난 날짜를 직접 골라 연 실측 목록의 품목 내용(TTL 90초)은 날짜 창 밖이라
# 비우지 않는다. 검색어·'내 것' 필터 소속은 history 만 비운다(다른 탭의 검색 결과는 날짜 창·
# 단계 범위 안 주문이면 위 규칙으로 함께 비워진다).

#: 시공 숫자판(summary_counts)이 세는 단계. 정본은
#: ``construction_read_model.CONSTRUCTION_ALL_STAGE_CODES`` — 계약 테스트가 같음을 고정한다.
CONSTRUCTION_SUMMARY_STAGE_CODES: Final[frozenset[str]] = frozenset(
    {"CONSTRUCTION", "시공", "CONSTRUCTING", "COMPLETED", "완료", "AS_WAIT", "CS"}
)
#: 생산 숫자판(summary_counts)이 세는 단계. 정본은
#: ``production_read_model.PRODUCTION_BASE_STAGE_CODES`` — 계약 테스트가 같음을 고정한다.
PRODUCTION_SUMMARY_STAGE_CODES: Final[frozenset[str]] = frozenset(
    {"고객컨펌", "생산", "시공", "CONFIRM", "PRODUCTION", "CONSTRUCTION"}
)
#: 실측 패널·실측 기본 목록·출고 패널이 담는 날짜 창(오늘 ~ 오늘+14일, KST). 정본은
#: ``measurement_dashboard_filters.parse_measurement_dashboard_filters`` 와 출고 대시보드.
DASHBOARD_DATE_WINDOW_DAYS: Final[int] = 14
#: 도메인 탭이 없고 orders 탭(주문접수)에만 나타나는 단계. 그 밖의 미매핑 단계는 broad.
_ORDERS_ONLY_STAGE_CODES: Final[frozenset[str]] = frozenset({"", "RECEIVED"})
_ISO_DATE_PREFIX_RE = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _norm_stage(value: Any) -> str:
    """단계 값 정규화(대문자·공백·JSON 따옴표 제거). 없으면 빈 문자열."""
    return str(value or "").strip().strip('"').strip().upper()


def _norm_date(raw: str) -> str:
    """``2026-9-3``·``2026/09/03`` → ``2026-09-03``. 날짜 꼴이 아니면 원문."""
    m = _ISO_DATE_PREFIX_RE.match(raw)
    if not m:
        return raw
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _date_tuple(*raws: Any) -> tuple[str, ...]:
    """콤마 다중 날짜를 포함한 값들 → 정규화된 날짜 정렬 튜플(중복 제거)."""
    out: set[str] = set()
    for raw in raws:
        for chunk in str(raw or "").split(","):
            chunk = chunk.strip()
            if chunk:
                out.add(_norm_date(chunk))
    return tuple(sorted(out))


def _frozen(value: Any) -> str:
    """비교용 정본 문자열. 저장 전 스냅샷이 뒤의 제자리 수정에 끌려가지 않게 값을 굳힌다."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _any_date_in_window(dates: Iterable[str], today: datetime.date) -> bool:
    """날짜 중 하나라도 오늘~오늘+14일 창에 들면 True(날짜 꼴이 아니면 건너뛴다)."""
    end = today + datetime.timedelta(days=DASHBOARD_DATE_WINDOW_DAYS)
    for value in dates:
        try:
            day = datetime.date.fromisoformat(value[:10])
        except (TypeError, ValueError):
            continue
        if today <= day <= end:
            return True
    return False


def order_dashboard_cache_axes(order: Any) -> dict[str, Any]:
    """주문 1건에서 대시보드 캐시 소속·내용을 가르는 값만 떠 둔 스냅샷.

    저장 **전**(잠근 직후)과 **후**에 한 번씩 떠서 :func:`dashboard_families_for_order_save`
    에 넘긴다. 값은 문자열로 굳혀 두므로 저장 도중 structured_data 를 제자리에서 고쳐도
    전 스냅샷은 변하지 않는다.

    축과 근거(캐시 compute 가 읽는 값):
      * core — status·삭제·ERP 여부·초안. 모든 family 기준 쿼리의 active/draft 필터.
      * stages — ``erp_stage_code``·``workflow.stage``. 단계 family·시공/생산 숫자판 범위.
      * measurement_dates/measurement_flags — 실측 패널·목록 소속(날짜)과 지방/자가실측 집계
        (``measurement_read_model.compute_measurement_panel_assembly``).
      * shipment_dates — 출고 패널 소속(시공일·AS 방문일, ``shipment/dashboard.py`` panel_query).
      * drawing — 도면 큐 소속(``build_drawing_queue_filter`` 의 도면 상태·도면 담당).
      * identity — 과거 이력 검색·'내 것' 필드(``erp_order_dashboard_search_predicate``·
        ``build_mine_sql_filter``). history page_rows 는 단계 무관 전체 주문의 검색 결과다.
    """
    sd = _as_dict(getattr(order, "structured_data", None))
    schedule = _as_dict(sd.get("schedule"))
    raw_items = sd.get("items")
    items = [it for it in raw_items if isinstance(it, dict)] if isinstance(raw_items, list) else []
    first_item = items[0] if items else {}
    workflow = _as_dict(sd.get("workflow"))
    parties = _as_dict(sd.get("parties"))
    site = _as_dict(sd.get("site"))
    assignments = _as_dict(sd.get("assignments"))
    shipment = _as_dict(sd.get("shipment"))
    status = str(getattr(order, "status", "") or "")
    is_draft = status.upper() == "DRAFT" or is_erp_draft_structured_data(sd)
    return {
        "core": _frozen((
            status,
            getattr(order, "deleted_at", None) is not None,
            bool(getattr(order, "is_erp_order", False)),
            is_draft,
        )),
        "stages": (
            _norm_stage(getattr(order, "erp_stage_code", None)),
            _norm_stage(workflow.get("stage")),
        ),
        "measurement_dates": _date_tuple(
            getattr(order, "measurement_date", None),
            getattr(order, "erp_measurement_date", None),
            _as_dict(schedule.get("measurement")).get("date"),
            *[it.get("measurement_date") for it in items],
        ),
        "measurement_flags": _frozen((
            getattr(order, "is_regional", None),
            getattr(order, "is_self_measurement", None),
            getattr(order, "measurement_completed", None),
            getattr(order, "regional_sales_order_upload", None),
            getattr(order, "regional_blueprint_sent", None),
            getattr(order, "regional_order_upload", None),
        )),
        "shipment_dates": _date_tuple(
            getattr(order, "scheduled_date", None),
            getattr(order, "erp_construction_date", None),
            _as_dict(schedule.get("construction")).get("date"),
            _as_dict(schedule.get("as_visit")).get("date"),
            *[it.get("construction_date") for it in items],
        ),
        "drawing": _frozen((
            sd.get("drawing_status"),
            _as_dict(sd.get("drawing")).get("status"),
            sd.get("drawing_assignees"),
            assignments.get("drawing_assignees"),
            assignments.get("drawing_assignee_user_ids"),
        )),
        "identity": _frozen((
            getattr(order, "customer_name", None),
            getattr(order, "phone", None),
            getattr(order, "address", None),
            getattr(order, "product", None),
            getattr(order, "manager_name", None),
            _as_dict(parties.get("customer")).get("name"),
            _as_dict(parties.get("customer")).get("phone"),
            _as_dict(parties.get("manager")).get("name"),
            _as_dict(parties.get("orderer")).get("name"),
            _as_dict(parties.get("buyer")).get("name"),
            _as_dict(parties.get("buyer")).get("phone"),
            site.get("address_full"),
            site.get("address_main"),
            first_item.get("product_name"),
            first_item.get("name"),
            _as_dict(schedule.get("measurement")).get("date"),
            _as_dict(schedule.get("measurement")).get("time"),
            _as_dict(schedule.get("construction")).get("date"),
            _as_dict(workflow.get("current_quest")).get("owner_person"),
            shipment.get("construction_workers"),
            assignments.get("sales_assignee_user_ids"),
        )),
    }


def dashboard_families_for_order_save(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    today: datetime.date | None = None,
) -> tuple[str, ...]:
    """저장 전/후 스냅샷 → 비워야 할 family 튜플(정의 순서). broad 면 7개 전부.

    규칙(과소무효화보다 과무효화가 안전):
      * 스냅샷이 없거나 core(status·삭제·ERP·초안)가 바뀌면 → 전부(탭 소속 자체가 바뀐다).
      * 전/후 단계 중 매핑도 orders 전용도 아닌 값이 있거나, 단계가 바뀌었는데 한쪽이 매핑
        없는 단계면 → 전부(어느 탭인지 모른다. MUT-CACHE-01 리스너와 같은 규칙).
      * 그 밖: orders + 전/후 단계 family(단계가 바뀌었으면 history 도), 그리고
        - measurement: 실측일·지방/자가실측 값이 바뀌었거나, 전/후 실측일이 날짜 창 안.
        - shipment: 시공일·AS 방문일이 바뀌었거나, 전/후 그 날짜가 날짜 창 안.
        - construction / production: 전/후 단계가 그 숫자판이 세는 단계.
        - drawing: 도면 상태·도면 담당이 바뀜.
        - history: 검색·'내 것' 필드가 바뀜.

    Args:
        before: 저장 전 :func:`order_dashboard_cache_axes` (없으면 None → broad).
        after: 저장 후 스냅샷.
        today: 날짜 창 기준일(테스트 주입용). 생략하면 KST 오늘.

    Returns:
        무효화할 family 튜플.
    """
    if not before or not after or before.get("core") != after.get("core"):
        return ALL_DASHBOARD_FAMILIES
    stages = {*before.get("stages", ()), *after.get("stages", ())}
    stage_moved = set(before.get("stages", ())) != set(after.get("stages", ()))
    families = {DASHBOARD_FAMILY_ORDERS}
    for stage in stages:
        family = stage_code_to_dashboard_family(stage)
        if family is not None:
            families.add(family)
        elif stage_moved or stage not in _ORDERS_ONLY_STAGE_CODES:
            # 단계 이동의 한쪽이 도메인 탭 없는 단계면 어느 탭이 바뀔지 모른다 — MUT-CACHE-01
            # 리스너(dashboard_families_for_mutation_intent)와 같은 규칙.
            return ALL_DASHBOARD_FAMILIES
    if stage_moved:
        # 과거 이력의 단계 필터 결과가 바뀐다.
        families.add(DASHBOARD_FAMILY_HISTORY)
    day = today or get_today_kst()
    m_before, m_after = before.get("measurement_dates", ()), after.get("measurement_dates", ())
    if (
        m_before != m_after
        or before.get("measurement_flags") != after.get("measurement_flags")
        or _any_date_in_window((*m_before, *m_after), day)
    ):
        families.add(DASHBOARD_FAMILY_MEASUREMENT)
    s_before, s_after = before.get("shipment_dates", ()), after.get("shipment_dates", ())
    if s_before != s_after or _any_date_in_window((*s_before, *s_after), day):
        families.add(DASHBOARD_FAMILY_SHIPMENT)
    if stages & CONSTRUCTION_SUMMARY_STAGE_CODES:
        families.add(DASHBOARD_FAMILY_CONSTRUCTION)
    if stages & PRODUCTION_SUMMARY_STAGE_CODES:
        families.add(DASHBOARD_FAMILY_PRODUCTION)
    if before.get("drawing") != after.get("drawing"):
        families.add(DASHBOARD_FAMILY_DRAWING)
    if before.get("identity") != after.get("identity"):
        families.add(DASHBOARD_FAMILY_HISTORY)
    return tuple(f for f in ALL_DASHBOARD_FAMILIES if f in families)


def invalidate_dashboard_families_for_order_save(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> int:
    """단건 주문 저장 커밋 뒤 :func:`dashboard_families_for_order_save` 범위만 비운다.

    DB commit이 성공한 뒤에만 호출할 것.

    Returns:
        삭제한 키 개수 합(대략치).
    """
    families = dashboard_families_for_order_save(before, after)
    if families == ALL_DASHBOARD_FAMILIES:
        return invalidate_all_dashboard_slice_caches()
    return invalidate_dashboard_families(*families)


#: 일정 종류(``OrderScheduleDate.kind``) → 그 날짜를 읽는 캐시 family.
#: 근거: 실측일 = 실측 패널·목록, orders/생산 숫자판 D-4(``_erp_alerts`` measurement_d4).
#: 시공일 = 출고 패널, 시공 D-3·생산 D-2 숫자판, orders 숫자판·관제탑. AS 방문일 = 출고 패널
#: (AS 상태 주문), orders 관제탑. 시공 숫자판은 날짜 표시단계를 쓰므로 세 종류 모두에 넣는다.
#: 실측일·시공일 문자열은 과거 이력 검색 대상이기도 하다(``erp_order_dashboard_search_predicate``
#: 의 schedule.*.date) → history. 도면 캐시(접수순 id 목록)는 일정 날짜를 담지 않는다.
_SCHEDULE_KIND_FAMILIES: Final[dict[str, tuple[str, ...]]] = {
    "measurement": (
        DASHBOARD_FAMILY_ORDERS,
        DASHBOARD_FAMILY_MEASUREMENT,
        DASHBOARD_FAMILY_CONSTRUCTION,
        DASHBOARD_FAMILY_HISTORY,
        DASHBOARD_FAMILY_PRODUCTION,
    ),
    "construction": (
        DASHBOARD_FAMILY_ORDERS,
        DASHBOARD_FAMILY_SHIPMENT,
        DASHBOARD_FAMILY_CONSTRUCTION,
        DASHBOARD_FAMILY_HISTORY,
        DASHBOARD_FAMILY_PRODUCTION,
    ),
    "as_visit": (
        DASHBOARD_FAMILY_ORDERS,
        DASHBOARD_FAMILY_SHIPMENT,
        DASHBOARD_FAMILY_CONSTRUCTION,
    ),
}


def dashboard_families_for_schedule_change(
    kinds: Iterable[str], *, item_level: bool = False
) -> tuple[str, ...]:
    """바뀐 일정 종류 → 비워야 할 family 튜플. 모르는 종류가 섞이면 전부.

    Args:
        kinds: 바뀐 ``OrderScheduleDate.kind`` 들.
        item_level: 품목별 날짜(``item_index`` 있는 행)가 바뀌었는가. 품목 날짜는 품목
            dict 안에 있고, 실측 제품 목록 DTO(``measurement_product_items_build``)가 품목
            dict 를 통째로 싣는다 → 실측 family 도 비운다.

    Returns:
        무효화할 family 튜플(정의 순서).
    """
    families: set[str] = set()
    for kind in kinds:
        mapped = _SCHEDULE_KIND_FAMILIES.get(str(kind or ""))
        if mapped is None:
            return ALL_DASHBOARD_FAMILIES
        families.update(mapped)
    if item_level and families:
        families.add(DASHBOARD_FAMILY_MEASUREMENT)
    return tuple(f for f in ALL_DASHBOARD_FAMILIES if f in families)


# --- canonical mutation 자동 무효화 (MUT-CACHE-01) --------------------------------
# session.info 에 쌓는 intent 키. revision.execute_order_mutation 이 채우고,
# after_commit 리스너가 소비(pop)한다. 커밋 실패/롤백 시 소비자가 돌지 않으므로
# 무효화도 일어나지 않는다(정확한 시점 = commit 성공 직후).
MUTATION_CACHE_INTENT_KEY: Final[str] = "foms_dashcache_mutation_intent"


def dashboard_families_for_mutation_intent(intent: Mapping[str, Any]) -> tuple[str, ...]:
    """mutation intent → 무효화할 dashboard family 튜플.

    intent 형태: ``{"broad": bool, "stages": [stage_code|None, ...]}``.

    규칙(과소무효화보다 과무효화가 안전):
      * ``broad`` 표식(삭제/복원 등 전 탭 전이) → 전체 family.
      * 단계가 **바뀐** mutation 인데 before/after 중 매핑 없는 stage가 있으면 → 전체
        (어느 탭으로 갔는지 모르면 stale 이 최악).
      * 그 외 → ``orders`` + 관련된 stage family.

    Args:
        intent: ``execute_order_mutation`` 이 session.info 에 쌓은 intent.

    Returns:
        무효화 대상 family 튜플(중복 제거, 정의 순서 유지).
    """
    if intent.get("broad"):
        return ALL_DASHBOARD_FAMILIES
    stages = list(intent.get("stages") or [])
    mapped = {stage_code_to_dashboard_family(s) for s in stages}
    changed = len({(s or "") for s in stages}) > 1
    if changed and None in mapped:
        return ALL_DASHBOARD_FAMILIES
    families = {DASHBOARD_FAMILY_ORDERS} | {m for m in mapped if m}
    return tuple(f for f in ALL_DASHBOARD_FAMILIES if f in families)


def register_dashboard_cache_invalidation_listener() -> None:
    """canonical order mutation commit 직후 dashboard 캐시를 자동 무효화하도록 배선한다.

    MUT-CACHE-01: 지금까지는 라우트마다 손으로 ``invalidate_*`` 를 호출해야 했고, 빠뜨리면
    삭제/단계 이동이 최대 TTL(300초)만큼 숫자판에 남았다(2026-08-10 운영 사고 #4717,
    단계 강제 변경 스테이징 재현 310초). ``revision.execute_order_mutation`` 이 남긴
    intent 를 ``after_commit`` 에서 소비하므로, 엔진을 경유하는 **모든** 경로가 경로별
    배선 없이 커버된다.

    ``after_soft_rollback`` 에서 intent 를 폐기해 롤백된 트랜잭션의 의도가 다음
    트랜잭션으로 새지 않게 한다.
    """
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    @event.listens_for(Session, "after_commit")
    def _dashcache_after_order_mutation(session):  # pragma: no cover - 배선은 통합 테스트로 검증
        intent = session.info.pop(MUTATION_CACHE_INTENT_KEY, None)
        if not intent:
            return
        try:
            families = dashboard_families_for_mutation_intent(intent)
            invalidate_dashboard_families(*families)
            if intent.get("broad"):
                from foms.services.shipment_as_recommendation_cache import (
                    invalidate_shipment_as_recommendation_cache,
                )

                invalidate_shipment_as_recommendation_cache(reason="order_mutation")
        except Exception:
            # fail-open: 캐시 무효화 실패가 이미 커밋된 업무 변경을 되돌릴 수는 없다.
            logger.warning("[DashCache] mutation invalidate failed", exc_info=True)

    @event.listens_for(Session, "after_soft_rollback")
    def _dashcache_drop_intent(session, previous_transaction):  # pragma: no cover
        session.info.pop(MUTATION_CACHE_INTENT_KEY, None)

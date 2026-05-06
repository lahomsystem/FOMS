"""AS shipment recommendation read-model cache (JSON DTO only, Redis or process-local TTL)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import load_only

from foms.services.as_content_safety import as_content_html_to_text, sanitize_as_content_html
from foms.services.common.dashboard_cache import get_dashboard_redis
from foms.services.geocode_helpers import get_order_display_address
from foms.services.schedule_recommendations import get_order_display_customer_name
from models import Order

logger = logging.getLogger(__name__)

KEY_VERSION = "v2"
KEY_PREFIX = f"foms:asrec:{KEY_VERSION}"

TTL_CANDIDATE_POOL_SECONDS = 300
TTL_TARGET_SECONDS = 600
TTL_ROUTE_SUCCESS_SECONDS = 7 * 24 * 60 * 60
TTL_ROUTE_FAILURE_SECONDS = 60
TTL_LOCK_SECONDS = 30

_ENV_DISABLE = "FOMS_SHIPMENT_AS_REC_CACHE_ENABLED"

_redis_warn_lock = threading.Lock()
_last_redis_warn_ts: float = 0.0

_proc_lock = threading.RLock()
_proc_candidate_pool: dict[str, Any] | None = None
_proc_candidate_expires: float = 0.0
_proc_route: dict[str, tuple[float, dict[str, Any]]] = {}
_proc_target: dict[str, tuple[float, dict[str, Any]]] = {}
_proc_lock_keys: set[str] = set()


def _env_falsey(name: str) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    return raw in ("0", "false", "no", "off")


def is_asrec_cache_enabled() -> bool:
    """기본 true. FOMS_SHIPMENT_AS_REC_CACHE_ENABLED=false일 때만 완전 bypass."""
    return not _env_falsey(_ENV_DISABLE)


def build_hash(value: Any) -> str:
    """정렬 JSON + SHA256 앞 20자. 주소 원문 key 노출 방지."""
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _redis_log_throttled(msg: str, *args: Any) -> None:
    global _last_redis_warn_ts
    with _redis_warn_lock:
        now = time.monotonic()
        if now - _last_redis_warn_ts < 2.0:
            return
        _last_redis_warn_ts = now
    logger.warning(msg, *args)


def _open_as_entries(sd: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in sd.get("as_info") or []:
        if isinstance(entry, dict) and entry.get("status") == "OPEN":
            out.append(entry)
    return out


def _candidate_as_info_id(sd: dict[str, Any]) -> tuple[int | None, bool]:
    open_ = _open_as_entries(sd)
    if len(open_) == 1:
        rid = open_[0].get("id")
        return (int(rid) if rid is not None else None, False)
    if len(open_) > 1:
        return (None, True)
    return (None, False)


def _as_sort_date(order: Order, sd: dict[str, Any]) -> str:
    open_ = _open_as_entries(sd)
    if open_:
        started = open_[0].get("started_at") or ""
        if started:
            return str(started)[:10]
    su = getattr(order, "structured_updated_at", None)
    if su is not None:
        return str(su)[:10]
    ca = getattr(order, "created_at", None)
    if ca is not None:
        return str(ca)[:10]
    return "9999-99-99"


def _visit_date_str(order: Order, sd: dict[str, Any]) -> str:
    av = (sd.get("schedule") or {}).get("as_visit") or {}
    if isinstance(av, dict):
        return str(av.get("date") or "").strip()
    return ""


def _as_content_text(sd: dict[str, Any]) -> str:
    shipment = sd.get("shipment") or {}
    if not isinstance(shipment, dict):
        return ""
    parts = [
        as_content_html_to_text(shipment.get("as_content")),
        as_content_html_to_text(shipment.get("as_content_2")),
    ]
    return "\n\n".join(part for part in parts if part)


def _as_content_html(order: Order, sd: dict[str, Any]) -> str:
    """AS 대시보드와 동일 sanitize + 탭2 notes 폴백(as_dashboard) 후 HTML 결합."""
    shipment = sd.get("shipment") or {}
    if not isinstance(shipment, dict):
        return ""
    primary = sanitize_as_content_html(shipment.get("as_content"))
    has_secondary_key = "as_content_2" in shipment
    secondary = sanitize_as_content_html(shipment.get("as_content_2"))
    if not has_secondary_key and not secondary:
        secondary = sanitize_as_content_html(getattr(order, "notes", None) or "")
    chunks: list[str] = []
    if primary:
        chunks.append(primary)
    if secondary:
        chunks.append(secondary)
    return "<br><br>".join(chunks)


def _shipment_rec_meta(sd: dict[str, Any]) -> dict[str, Any] | None:
    av = (sd.get("schedule") or {}).get("as_visit") or {}
    if not isinstance(av, dict):
        return None
    meta = av.get("shipment_recommendation")
    return meta if isinstance(meta, dict) else None


def _order_candidate_fingerprint(order: Order, sd: dict[str, Any], *, source_value: str) -> dict[str, Any]:
    addr = get_order_display_address(order)
    meta = _shipment_rec_meta(sd) or {}
    linked = None
    if meta.get("source") == source_value:
        sid = meta.get("shipment_order_id")
        if sid is not None:
            try:
                linked = int(sid)
            except (TypeError, ValueError):
                linked = None
    open_entries = _open_as_entries(sd)
    as_info_fp = build_hash(
        [
            {
                "id": e.get("id"),
                "status": e.get("status"),
                "visit_date": e.get("visit_date"),
            }
            for e in open_entries
            if isinstance(e, dict)
        ]
    )
    su = getattr(order, "structured_updated_at", None)
    ca = getattr(order, "created_at", None)
    return {
        "id": order.id,
        "status": order.status,
        "addr_hash": build_hash(addr.strip()),
        "visit": _visit_date_str(order, sd),
        "lat_ok": bool(
            order.lat and order.lng and getattr(order, "geocode_status", None) == "success"
        ),
        "as_info_fp": as_info_fp,
        "meta_fp": build_hash(meta) if meta else "",
        "linked": linked,
        "structured_updated_at": str(su)[:32] if su is not None else "",
        "created_at": str(ca)[:32] if ca is not None else "",
        "dto_hash": build_hash(
            {
                "customer": get_order_display_customer_name(order),
                "visit": _visit_date_str(order, sd),
                "as_content": _as_content_text(sd),
                "as_content_html": _as_content_html(order, sd),
            }
        ),
    }


def _build_candidate_pool_payload(
    db,
    converter: Any,
    *,
    source_value: str,
    as_statuses: tuple[str, ...],
    log_warning: Callable[..., None] | None,
) -> dict[str, Any]:
    warn = log_warning or logger.warning
    cand_query = (
        db.query(Order)
        .options(
            load_only(
                Order.id,
                Order.status,
                Order.deleted_at,
                Order.address,
                Order.is_erp_order,
                Order.structured_data,
                Order.customer_name,
                Order.lat,
                Order.lng,
                Order.geocode_status,
                Order.structured_updated_at,
                Order.created_at,
                Order.notes,
            )
        )
        .filter(
            Order.status.in_(as_statuses),
            Order.active_filter(),
        )
        .order_by(Order.id.desc())
        .limit(800)
    )
    candidates_in: list[dict[str, Any]] = []
    fingerprints: list[dict[str, Any]] = []
    link_as_to_shipment: dict[int, int] = {}

    for order in cand_query:
        sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        addr = get_order_display_address(order)
        if not addr.strip():
            continue
        fingerprints.append(_order_candidate_fingerprint(order, sd, source_value=source_value))
        meta = _shipment_rec_meta(sd)
        if meta and meta.get("source") == source_value:
            sid = meta.get("shipment_order_id")
            if sid is not None:
                try:
                    link_as_to_shipment[order.id] = int(sid)
                except (TypeError, ValueError):
                    pass
        info_id, ambiguous = _candidate_as_info_id(sd)
        row: dict[str, Any] = {
            "order_id": order.id,
            "customer_name": get_order_display_customer_name(order),
            "address": addr,
            "current_visit_date": _visit_date_str(order, sd),
            "status": order.status,
            "sort_date": _as_sort_date(order, sd),
            "as_info_id": None if ambiguous else info_id,
            "as_info_ambiguous": ambiguous,
            "as_content_text": _as_content_text(sd),
            "as_content_html": _as_content_html(order, sd),
        }
        if order.lat and order.lng and order.geocode_status == "success":
            row["cached_lat"] = float(order.lat)
            row["cached_lng"] = float(order.lng)
        else:
            try:
                lat, lng, _, _ = converter.analyze_address(addr)
                if lat and lng:
                    row["cached_lat"] = float(lat)
                    row["cached_lng"] = float(lng)
            except Exception as exc:
                warn("[AS-REC] analyze_address for candidate pool failed order=%s: %s", order.id, exc)

        candidates_in.append(row)

    pool_version = build_hash({"rule": "candidate_pool_v1", "orders": fingerprints})
    return {
        "pool_version": pool_version,
        "computed_at": _now_iso(),
        "candidates": candidates_in,
        "link_as_to_shipment": {str(k): v for k, v in link_as_to_shipment.items()},
    }


def _normalize_link_map(raw: dict[str, Any] | dict[int, int]) -> dict[int, int]:
    out: dict[int, int] = {}
    for k, v in raw.items():
        try:
            out[int(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def get_or_compute_candidate_pool(
    db,
    converter: Any,
    *,
    source_value: str,
    as_statuses: tuple[str, ...],
    log_warning: Callable[..., None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Return:
      pool = {"pool_version", "computed_at", "candidates", "link_as_to_shipment"}
      stats = {"candidate_pool_hit": bool, "candidate_count": int}
    """
    warn = log_warning or logger.warning
    stats = {"candidate_pool_hit": False, "candidate_count": 0}

    if not is_asrec_cache_enabled():
        pool = _build_candidate_pool_payload(
            db, converter, source_value=source_value, as_statuses=as_statuses, log_warning=warn
        )
        pool["link_as_to_shipment"] = _normalize_link_map(pool["link_as_to_shipment"])
        stats["candidate_count"] = len(pool["candidates"])
        return pool, stats

    cache_key = f"{KEY_PREFIX}:candidate_pool:latest"
    lock_key = f"{KEY_PREFIX}:lock:candidate_pool"

    def _from_proc() -> dict[str, Any] | None:
        with _proc_lock:
            if _proc_candidate_pool is None:
                return None
            if time.monotonic() >= _proc_candidate_expires:
                return None
            return json.loads(json.dumps(_proc_candidate_pool))

    def _set_proc(data: dict[str, Any]) -> None:
        global _proc_candidate_pool, _proc_candidate_expires
        with _proc_lock:
            _proc_candidate_pool = json.loads(json.dumps(data))
            _proc_candidate_expires = time.monotonic() + TTL_CANDIDATE_POOL_SECONDS

    r = get_dashboard_redis()
    if r is not None:
        try:
            raw = r.get(cache_key)
            if raw:
                data = json.loads(raw)
                stats["candidate_pool_hit"] = True
                stats["candidate_count"] = len(data.get("candidates") or [])
                data["link_as_to_shipment"] = _normalize_link_map(data.get("link_as_to_shipment") or {})
                return data, stats
        except Exception as exc:
            _redis_log_throttled("[AS-REC] candidate_pool redis get failed: %s", exc, exc_info=True)

    hit_proc = _from_proc()
    if hit_proc is not None:
        stats["candidate_pool_hit"] = True
        stats["candidate_count"] = len(hit_proc.get("candidates") or [])
        hit_proc["link_as_to_shipment"] = _normalize_link_map(hit_proc.get("link_as_to_shipment") or {})
        return hit_proc, stats

    lock_acquired = False
    if r is not None:
        try:
            lock_acquired = bool(r.set(lock_key, "1", nx=True, ex=TTL_LOCK_SECONDS))
        except Exception as exc:
            _redis_log_throttled("[AS-REC] candidate_pool lock redis failed: %s", exc, exc_info=True)

    if not lock_acquired and r is None:
        with _proc_lock:
            if lock_key not in _proc_lock_keys:
                _proc_lock_keys.add(lock_key)
                lock_acquired = True

    try:
        if r is not None and not lock_acquired:
            try:
                time.sleep(0.05)
                raw_retry = r.get(cache_key)
                if raw_retry:
                    data = json.loads(raw_retry)
                    stats["candidate_pool_hit"] = True
                    stats["candidate_count"] = len(data.get("candidates") or [])
                    data["link_as_to_shipment"] = _normalize_link_map(data.get("link_as_to_shipment") or {})
                    return data, stats
            except Exception as exc:
                _redis_log_throttled("[AS-REC] candidate_pool redis retry get failed: %s", exc, exc_info=True)

        pool = _build_candidate_pool_payload(
            db, converter, source_value=source_value, as_statuses=as_statuses, log_warning=warn
        )
        pool["link_as_to_shipment"] = _normalize_link_map(pool["link_as_to_shipment"])
        stats["candidate_count"] = len(pool["candidates"])

        payload = json.dumps(pool, ensure_ascii=False, separators=(",", ":"))
        json.loads(payload)

        if r is not None:
            try:
                r.setex(cache_key, TTL_CANDIDATE_POOL_SECONDS, payload)
            except Exception as exc:
                _redis_log_throttled("[AS-REC] candidate_pool redis set failed: %s", exc, exc_info=True)
        _set_proc(pool)
        return pool, stats
    finally:
        if lock_acquired:
            if r is not None:
                try:
                    r.delete(lock_key)
                except Exception as exc:
                    _redis_log_throttled("[AS-REC] candidate_pool lock release failed: %s", exc, exc_info=True)
            else:
                with _proc_lock:
                    _proc_lock_keys.discard(lock_key)


def make_route_provider(
    converter: Any,
    stats: dict[str, Any],
    *,
    log_warning: Callable[..., None] | None = None,
) -> Callable[..., dict[str, Any]]:
    """
    반환 callable:
      route_provider(slat, slng, elat, elng, timeout=None) -> dict
    """

    warn = log_warning or logger.warning

    def provider(slat: float, slng: float, elat: float, elng: float, timeout: float | None = None) -> dict[str, Any]:
        coord_fp = build_hash(
            {
                "slat": round(float(slat), 6),
                "slng": round(float(slng), 6),
                "elat": round(float(elat), 6),
                "elng": round(float(elng), 6),
            }
        )
        route_key = f"{KEY_PREFIX}:route:{coord_fp}"

        if is_asrec_cache_enabled():
            r = get_dashboard_redis()
            if r is not None:
                try:
                    raw = r.get(route_key)
                    if raw:
                        stats["route_hits"] = int(stats.get("route_hits") or 0) + 1
                        return dict(json.loads(raw))
                except Exception as exc:
                    _redis_log_throttled("[AS-REC] route redis get failed: %s", exc, exc_info=True)
            with _proc_lock:
                ent = _proc_route.get(route_key)
                if ent and time.monotonic() < ent[0]:
                    stats["route_hits"] = int(stats.get("route_hits") or 0) + 1
                    return dict(ent[1])

        stats["route_misses"] = int(stats.get("route_misses") or 0) + 1
        try:
            info = converter.calculate_route(slat, slng, elat, elng, timeout=timeout)
        except Exception as exc:
            warn("[AS-REC] calculate_route exception: %s", exc, exc_info=True)
            info = {"status": "error", "message": str(exc)}

        dto = dict(info)
        ttl = TTL_ROUTE_SUCCESS_SECONDS if dto.get("status") == "success" else TTL_ROUTE_FAILURE_SECONDS
        dto["computed_at"] = _now_iso()
        dto["provider"] = "kakao_directions"

        if is_asrec_cache_enabled():
            try:
                serial = json.dumps(dto, ensure_ascii=False, separators=(",", ":"))
                json.loads(serial)
            except Exception as exc:
                warn("[AS-REC] route dto not serializable, skip cache: %s", exc)
                return dto

            r = get_dashboard_redis()
            if r is not None:
                try:
                    r.setex(route_key, ttl, serial)
                except Exception as exc:
                    _redis_log_throttled("[AS-REC] route redis set failed: %s", exc, exc_info=True)
            with _proc_lock:
                _proc_route[route_key] = (time.monotonic() + ttl, json.loads(serial))

        return dto

    return provider


def get_cached_target(cache_key: str) -> dict[str, Any] | None:
    """target recommendation cache hit면 target payload 반환."""
    if not is_asrec_cache_enabled():
        return None
    r = get_dashboard_redis()
    if r is not None:
        try:
            raw = r.get(cache_key)
            if raw:
                return dict(json.loads(raw))
        except Exception as exc:
            _redis_log_throttled("[AS-REC] target redis get failed: %s", exc, exc_info=True)
    with _proc_lock:
        ent = _proc_target.get(cache_key)
        if ent and time.monotonic() < ent[0]:
            return dict(ent[1])
    return None


def set_cached_target(cache_key: str, target_payload: dict[str, Any]) -> None:
    """JSON DTO만 저장. 실패는 warning 후 무시."""
    if not is_asrec_cache_enabled():
        return
    try:
        serial = json.dumps(target_payload, ensure_ascii=False, separators=(",", ":"))
        json.loads(serial)
    except Exception as exc:
        logger.warning("[AS-REC] target cache skip non-json: %s", exc, exc_info=True)
        return

    r = get_dashboard_redis()
    if r is not None:
        try:
            r.setex(cache_key, TTL_TARGET_SECONDS, serial)
            return
        except Exception as exc:
            _redis_log_throttled("[AS-REC] target redis set failed: %s", exc, exc_info=True)

    with _proc_lock:
        _proc_target[cache_key] = (time.monotonic() + TTL_TARGET_SECONDS, json.loads(serial))


def build_target_cache_key(target: dict[str, Any], pool_version: str, rule_version: str) -> str:
    """shipment_order_id + target fingerprint + pool_version + rule_version."""
    addr = (target.get("address") or "").strip()
    fp = build_hash(
        {
            "order_id": int(target.get("order_id") or 0),
            "target_date": (target.get("target_date") or "").strip(),
            "addr_hash": build_hash(addr),
            "workers": list(target.get("workers") or []),
            "cached_lat": target.get("cached_lat"),
            "cached_lng": target.get("cached_lng"),
        }
    )
    safe = build_hash({"pool": pool_version, "rule": rule_version, "tgt": fp})
    return f"{KEY_PREFIX}:target:{safe}"


def invalidate_shipment_as_recommendation_cache(*, reason: str = "") -> int:
    """foms:asrec:v1:* 전체 삭제. Redis/process cache 모두 제거."""
    deleted = 0
    if reason:
        logger.info("[AS-REC] invalidate reason=%s", reason)

    with _proc_lock:
        global _proc_candidate_pool, _proc_candidate_expires
        _proc_candidate_pool = None
        _proc_candidate_expires = 0.0
        _proc_route.clear()
        _proc_target.clear()
        _proc_lock_keys.clear()

    r = get_dashboard_redis()
    if r is None:
        return deleted

    pattern = f"{KEY_PREFIX}:*"
    try:
        for key in r.scan_iter(match=pattern, count=500):
            try:
                r.delete(key)
                deleted += 1
                if deleted >= 10000:
                    logger.warning("[AS-REC] invalidate cap reached")
                    break
            except Exception as exc:
                logger.warning("[AS-REC] delete key failed: %s", exc, exc_info=True)
    except Exception as exc:
        logger.warning("[AS-REC] redis scan invalidate failed: %s", exc, exc_info=True)

    return deleted


def reset_asrec_cache_runtime_for_tests() -> None:
    """테스트에서 프로세스 로컬 캐시 초기화."""
    invalidate_shipment_as_recommendation_cache(reason="test_reset")


__all__ = [
    "KEY_PREFIX",
    "KEY_VERSION",
    "TTL_CANDIDATE_POOL_SECONDS",
    "TTL_TARGET_SECONDS",
    "TTL_ROUTE_SUCCESS_SECONDS",
    "TTL_ROUTE_FAILURE_SECONDS",
    "TTL_LOCK_SECONDS",
    "build_hash",
    "build_target_cache_key",
    "get_cached_target",
    "get_or_compute_candidate_pool",
    "invalidate_shipment_as_recommendation_cache",
    "is_asrec_cache_enabled",
    "make_route_provider",
    "reset_asrec_cache_runtime_for_tests",
    "set_cached_target",
]

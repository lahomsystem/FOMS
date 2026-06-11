"""ERP mobile bottom-nav stage badge counts (P1-01)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

from sqlalchemy import cast, func, or_, String

from db import get_db
from models import Order

__all__ = [
    "NAV_BADGE_CACHE_TTL_SEC",
    "NAV_STATUS_BUCKETS",
    "compute_nav_badge_counts",
    "get_nav_badge_counts",
]

NAV_BADGE_CACHE_TTL_SEC = 30

# nav tab id → Order.status keys (MOBILE_TABLET_REDESIGN_PLAN §Bottom Nav)
NAV_STATUS_BUCKETS: dict[str, frozenset[str]] = {
    "dashboard": frozenset({"RECEIVED", "HAPPYCALL", "ON_HOLD", "RECHECK"}),
    # DRAWING은 drawing_workbench bucket 전담(아래). 실측 탭 배지에 합산하면
    # 영업 통합 사용자가 "밀린 실측"으로 오해 → 단계별 배지 SSOT 정합.
    "measurement": frozenset({"MEASURE"}),
    "shipment": frozenset({"CONFIRM", "PRODUCTION"}),
    "construction": frozenset({"CONSTRUCTION", "CS", "AS"}),
    "completion": frozenset({"COMPLETED", "AS_COMPLETED"}),
    "drawing_workbench": frozenset({"DRAWING"}),
    "production": frozenset({"PRODUCTION"}),
    "as": frozenset({"AS"}),
    "history": frozenset(),
}


@dataclass(frozen=True)
class _CacheEntry:
    expires_at: float
    counts: dict[str, int]


_cache_lock = Lock()
_cache: dict[tuple[int, bool], _CacheEntry] = {}


def _mine_only_for_user(user: Any) -> bool:
    """시공팀은 대시보드와 동일하게 담당 주문만 집계한다."""
    return bool(user and (getattr(user, "team", None) or "") == "CONSTRUCTION")


def _apply_mine_filter(query: Any, user: Any) -> Any:
    """생산 대시보드와 동일한 담당자 매칭( manager_name / structured_data )."""
    u_name = (getattr(user, "name", None) or "").strip()
    u_username = (getattr(user, "username", None) or "").strip()
    conds = []
    if u_name:
        conds.append(Order.manager_name.ilike(f"%{u_name}%"))
        conds.append(cast(Order.structured_data, String).ilike(f'%"{u_name}"%'))
    if u_username:
        conds.append(Order.manager_name.ilike(f"%{u_username}%"))
        conds.append(cast(Order.structured_data, String).ilike(f'%"{u_username}"%'))
    if not conds:
        return query.filter(Order.id == -1)
    return query.filter(or_(*conds))


def compute_nav_badge_counts(user: Any, *, mine_only: bool | None = None) -> dict[str, int]:
    """
    Bottom nav 탭별 미처리 건수.

    단일 GROUP BY status 쿼리 후 NAV_STATUS_BUCKETS로 합산한다.
    """
    if user is None:
        return {nav_id: 0 for nav_id in NAV_STATUS_BUCKETS}

    if mine_only is None:
        mine_only = _mine_only_for_user(user)

    db = get_db()
    q = db.query(Order.status, func.count(Order.id)).filter(
        Order.active_filter(),
        Order.is_erp_order.is_(True),
    )
    if mine_only:
        q = _apply_mine_filter(q, user)

    rows = q.group_by(Order.status).all()
    status_totals: dict[str, int] = {}
    for status, cnt in rows:
        if not status:
            continue
        status_totals[str(status)] = int(cnt or 0)

    counts: dict[str, int] = {}
    for nav_id, statuses in NAV_STATUS_BUCKETS.items():
        counts[nav_id] = sum(status_totals.get(s, 0) for s in statuses)
    return counts


def get_nav_badge_counts(user: Any) -> dict[str, int]:
    """30초 TTL 인메모리 캐시로 nav badge dict 반환."""
    if user is None:
        return {nav_id: 0 for nav_id in NAV_STATUS_BUCKETS}

    mine_only = _mine_only_for_user(user)
    cache_key = (int(user.id), mine_only)
    now = time.monotonic()

    with _cache_lock:
        entry = _cache.get(cache_key)
        if entry and entry.expires_at > now:
            return dict(entry.counts)

    counts = compute_nav_badge_counts(user, mine_only=mine_only)
    with _cache_lock:
        _cache[cache_key] = _CacheEntry(
            expires_at=now + NAV_BADGE_CACHE_TTL_SEC,
            counts=counts,
        )
    return counts

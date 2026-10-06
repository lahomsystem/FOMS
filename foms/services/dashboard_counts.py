"""ERP mobile bottom-nav stage badge counts (P1-01)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

from sqlalchemy import func, select, union
from sqlalchemy.sql.util import ClauseAdapter

from db import get_db
from foms.services.erp_permissions import build_mine_sql_filter
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


# 배지를 "내 차례"로 집계하는 팀: 시공 + 영업 통합(SALES/MEASURE).
# 영업 통합은 manager_name이 본인이라 담당자 매칭(_apply_mine_filter)이 신뢰 가능 →
# 배지가 팀 전체 backlog가 아닌 "내 할 일 N건"이 된다.
# 도면(DRAWING)은 manager가 아니라 drawing_assignee로 배정되므로 제외(전체 집계 유지,
# 도면 워크벤치 my_todo가 별도 SSOT) — 포함하면 본인 큐를 대량 누락한다.
MINE_ONLY_TEAMS = frozenset({"CONSTRUCTION", "SALES", "MEASURE"})


def _mine_only_for_user(user: Any) -> bool:
    """시공·영업 통합은 대시보드와 동일하게 담당 주문만 집계한다(배지 = 내 차례)."""
    return bool(user and (getattr(user, "team", None) or "") in MINE_ONLY_TEAMS)


def _apply_mine_filter(query: Any, user: Any) -> Any:
    """로그인 사용자의 역할 관계로 nav badge 집계를 제한.

    조건을 OR 하나로 묶으면 플래너가 trgm 인덱스를 못 쓰고 ERP 행마다 JSONB 를
    여러 번 풀어 읽는다(운영 평균 696ms). 조건마다 별칭 테이블에서 주문 번호를 뽑아
    UNION 한 뒤 멤버십만 본다 — 갈래마다 자기 인덱스를 탄다(스테이징 SALES 94→7ms,
    설계서 docs/specs/2026-10-06-nav-badge-count-query_SPEC.md). 조건 정의는
    ``build_mine_sql_filter`` 한 곳 그대로 쓴다.
    """
    conds = build_mine_sql_filter(user)
    if not conds:
        return query.filter(Order.id == -1)
    om = Order.__table__.alias("orders_mine")
    adapter = ClauseAdapter(om)
    branches = [select(om.c.id).where(adapter.traverse(cond)) for cond in conds]
    return query.filter(Order.id.in_(union(*branches)))


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


def get_nav_badge_counts(user: Any, *, mine_only: bool | None = None) -> dict[str, int]:
    """30초 TTL 인메모리 캐시로 nav badge dict 반환."""
    if user is None:
        return {nav_id: 0 for nav_id in NAV_STATUS_BUCKETS}

    if mine_only is None:
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

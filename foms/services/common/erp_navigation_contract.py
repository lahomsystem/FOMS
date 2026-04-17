"""ERP shell / fragment / heavy navigation contract (EPT tranche).

This module is the **single source of truth** for cross-cutting constants used by
ERP fast-page + tab navigation. Semantic meaning must stay aligned with
`docs/specs/2026-04-17-erp-shell-fragment-contract_SPEC.md`.

Do not change values here without a new execution batch + SPEC update.
"""

from __future__ import annotations

from urllib.parse import urlencode

# -----------------------------------------------------------------------------
# Micro-cache policy (locked: retain read-model slice cache from DMC tranche)
# -----------------------------------------------------------------------------

MICRO_CACHE_READ_SLICES_RETAINED: bool = True

# -----------------------------------------------------------------------------
# ERP primary surface (9) vs fragment-ready subset (9) — EPT-B4 secondary primary 편입
# -----------------------------------------------------------------------------
# PRIMARY_NAV: 잠금판 9 primary — 문서/인벤토리/B1과 동일 문자열.
# FRAGMENT_READY: 서버가 shell+view=fragment 로 본문 조각을 내는 경로만 (fetch 허용).
# ERP_CANONICAL_TAB_PATHS: SPEC §2·하위 호환 — FRAGMENT_READY 와 동일 튜플 객체.

ERP_PRIMARY_NAV_PATHS: tuple[str, ...] = (
    "/erp/dashboard",
    "/erp/measurement",
    "/erp/drawing-workbench",
    "/erp/production/dashboard",
    "/erp/shipment",
    "/erp/as",
    "/erp/construction/dashboard",
    "/erp/completion",
    "/erp/history/",
)

ERP_FRAGMENT_READY_PATHS: tuple[str, ...] = (
    "/erp/dashboard",
    "/erp/measurement",
    "/erp/drawing-workbench",
    "/erp/production/dashboard",
    "/erp/shipment",
    "/erp/as",
    "/erp/construction/dashboard",
    "/erp/completion",
    "/erp/history/",
)

ERP_CANONICAL_TAB_PATHS: tuple[str, ...] = ERP_FRAGMENT_READY_PATHS

# Stable tab id for shell cache keys and analytics (path-scoped; multi-segment paths use short ids).
ERP_TAB_IDS: tuple[str, ...] = (
    "dashboard",
    "measurement",
    "drawing_workbench",
    "production",
    "shipment",
    "as",
    "construction",
    "completion",
    "history",
)

ERP_PATH_TO_TAB_ID: dict[str, str] = {
    "/erp/dashboard": "dashboard",
    "/erp/measurement": "measurement",
    "/erp/drawing-workbench": "drawing_workbench",
    "/erp/production/dashboard": "production",
    "/erp/shipment": "shipment",
    "/erp/as": "as",
    "/erp/construction/dashboard": "construction",
    "/erp/completion": "completion",
    "/erp/history/": "history",
}

assert frozenset(ERP_FRAGMENT_READY_PATHS) <= frozenset(ERP_PRIMARY_NAV_PATHS)
assert len(ERP_PRIMARY_NAV_PATHS) == len(frozenset(ERP_PRIMARY_NAV_PATHS))

# -----------------------------------------------------------------------------
# Dual-mode request discrimination (full HTML vs fragment HTML)
# -----------------------------------------------------------------------------

# Shell-driven fetch sets this header so the server can return body-only HTML.
ERP_SHELL_REQUEST_HEADER: str = "X-FOMS-ERP-SHELL"
ERP_SHELL_REQUEST_HEADER_ACTIVE: str = "1"

# Optional query discriminator (recommended alongside header for caches/proxies).
ERP_VIEW_QUERY_PARAM: str = "view"

# ``view`` omitted or unknown → treat as full page document (direct visit, refresh, JS off).
VIEW_FRAGMENT: str = "fragment"
VIEW_CRITICAL: str = "critical"
VIEW_HEAVY: str = "heavy"

ERP_VIEW_MODES_KNOWN: frozenset[str] = frozenset({VIEW_FRAGMENT, VIEW_CRITICAL, VIEW_HEAVY})

# Response: fragment HTML (not a full document) — shell client checks this header.
ERP_FRAGMENT_RESPONSE_HEADER: str = "X-FOMS-ERP-FRAGMENT"
ERP_FRAGMENT_RESPONSE_ACTIVE: str = "1"

# Which shell view mode was honored (fragment | critical | heavy). EPT-B3+.
ERP_FRAGMENT_VIEW_TIER_HEADER: str = "X-FOMS-ERP-FRAGMENT-TIER"

# -----------------------------------------------------------------------------
# Browser-side tab cache key (client responsibility; documented contract)
# -----------------------------------------------------------------------------


def normalize_erp_query_for_cache_fingerprint(args) -> str:
    """Return a stable query string for cache keys (sorted keys, deterministic).

    Args:
        args: Typically Werkzeug ``request.args`` (supports duplicate keys).

    Returns:
        Percent-encoded query string without leading ``?``, or empty string.
    """
    if not args:
        return ""
    try:
        pairs = sorted(args.items(multi=True))
    except TypeError:
        pairs = sorted(args.items())
    return urlencode(pairs, doseq=True)

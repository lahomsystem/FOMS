"""Tablet split-view master list helpers (P1-05)."""

from __future__ import annotations

from typing import Any

from foms.services.common.erp_navigation_contract import (
    ERP_PRIMARY_NAV_PATHS,
    ERP_TAB_IDS,
)
from foms.services.erp_mobile_order_display import resolve_queue_card_schedule

# Rail labels/icons mirror the erp_mobile_shell.html nav catalog (short rail
# labels); the path/id ordering is the erp_navigation_contract SSOT (parallel
# ERP_PRIMARY_NAV_PATHS × ERP_TAB_IDS tuples). No policy is duplicated: this only
# adds presentation (label + Font Awesome icon) keyed by the contract tab id.
_RAIL_LABELS: dict[str, str] = {
    "dashboard": "대시보드",
    "measurement": "실측",
    "drawing_workbench": "도면",
    "production": "생산",
    "shipment": "출고",
    "as": "AS",
    "construction": "시공",
    "completion": "완료",
    "history": "이력",
}
_RAIL_ICONS: dict[str, str] = {
    "dashboard": "fas fa-layer-group",
    "measurement": "fas fa-ruler-combined",
    "drawing_workbench": "fas fa-drafting-compass",
    "production": "fas fa-industry",
    "shipment": "fas fa-truck-loading",
    "as": "fas fa-wrench",
    "construction": "fas fa-hammer",
    "completion": "fas fa-clipboard-check",
    "history": "fas fa-history",
}
# CONSTRUCTION team sees only these stages (mirrors erp_mobile_shell/erp_sub_nav
# _allowed_ids for CONSTRUCTION) and no calculator.
_CONSTRUCTION_RAIL_IDS: frozenset[str] = frozenset(
    {"shipment", "construction", "completion", "history"}
)
_CALCULATOR_ITEM: dict[str, str] = {
    "id": "calculator",
    "label": "계산기",
    "icon": "fas fa-calculator",
    "href": "/wdcalculator",
}


def build_split_master_cards(orders: list[dict[str, Any]], *, active_order_id: int | None = None) -> list[dict[str, Any]]:
    """Build master pane card descriptors from dashboard order rows."""
    cards: list[dict[str, Any]] = []
    for row in orders[:30]:
        oid = int(row.get("id") or 0)
        if not oid:
            continue
        stage = str(row.get("stage_badge_label") or row.get("stage") or "")
        schedule = resolve_queue_card_schedule(
            stage=row.get("stage"),
            stage_code=row.get("stage_code"),
            measurement_date=row.get("measurement_date"),
            construction_date=row.get("construction_date"),
        )
        schedule_label = str(schedule.get("label") or "")
        schedule_value = str(schedule.get("value") or "")
        cards.append(
            {
                "order_id": oid,
                "title": str(row.get("customer_name") or f"#{oid}"),
                "stage": stage,
                "meta": stage,
                "subtitle": str(row.get("product_subtitle") or ""),
                "schedule_label": schedule_label,
                "schedule_value": schedule_value,
                "phone": str(row.get("phone") or "-"),
                "address": str(row.get("address") or "-"),
                "manager": str(row.get("manager_name") or "-"),
                # detail_href = HTMX fragment body (split-shell.js swaps this into the
                # detail pane). edit_href = canonical full edit page — used as the card
                # <a href> so a full navigation / new tab / middle-click (or any HTMX
                # miss) lands on the styled page instead of a raw fragment document (W15).
                "detail_href": f"/api/foms/fragment/order/{oid}/edit?open=erp-order",
                "edit_href": f"/edit/{oid}?open=erp-order",
                "active": active_order_id is not None and oid == active_order_id,
            }
        )
    return cards


def _is_construction_team(user: Any) -> bool:
    """Return whether the user belongs to the CONSTRUCTION team (rail scoping).

    Byte-identical to the ``(current_user.team or '') == 'CONSTRUCTION'`` gate in
    erp_sub_nav.html / erp_mobile_shell.html — no ``.strip()`` (the templates do not
    strip either), so a whitespace-padded ``team`` is classified the same way on both
    the rail and the mobile nav, keeping the two in exact lockstep (no ADMIN
    exception — same as those templates).
    """
    if user is None:
        return False
    return (getattr(user, "team", None) or "") == "CONSTRUCTION"


def build_split_side_items(user: Any = None, *, active_id: str = "dashboard") -> list[dict[str, Any]]:
    """Build permission-scoped side-rail items for the tablet split shell.

    Non-construction users get all nine ERP primary stages (dashboard→history,
    ordered per ``erp_navigation_contract``) plus the calculator; CONSTRUCTION-team
    users get only shipment/construction/completion/history and no calculator —
    reusing the same permission branch as erp_mobile_shell/erp_sub_nav.

    Args:
        user: Current user; needs a ``team`` attribute. ``None`` → full menu.
        active_id: Tab id to highlight as the current tab.

    Returns:
        Side-tab descriptors with ``id``/``label``/``icon``/``href``/``active``.
    """
    construction = _is_construction_team(user)
    items: list[dict[str, Any]] = []
    for path, tab_id in zip(ERP_PRIMARY_NAV_PATHS, ERP_TAB_IDS):
        if construction and tab_id not in _CONSTRUCTION_RAIL_IDS:
            continue
        items.append(
            {
                "id": tab_id,
                "label": _RAIL_LABELS[tab_id],
                "icon": _RAIL_ICONS[tab_id],
                "href": path,
                "active": tab_id == active_id,
            }
        )
    if not construction:
        items.append({**_CALCULATOR_ITEM, "active": active_id == "calculator"})
    return items


def resolve_tablet_rail_active_id(path: str) -> str:
    """Resolve the active rail tab id for a request path (longest segment-prefix match).

    Matches ``path`` against ``ERP_PRIMARY_NAV_PATHS`` on segment boundaries (so
    ``/erp/measurement/42`` maps to ``measurement`` but a hypothetical ``/erp/ashley``
    does NOT falsely match ``/erp/as``) and returns the id of the longest matching
    prefix. The calculator lives OUTSIDE the ERP nav contract (at ``/wdcalculator``),
    so it is mapped explicitly to ``"calculator"`` — matching the ``_CALCULATOR_ITEM``
    href — so the global rail highlights 계산기 on that page. No match → empty string so
    the global rail renders with no highlighted tab rather than a false ``dashboard``
    highlight.

    Args:
        path: Current request path (e.g. ``request.path``).

    Returns:
        The matching ``ERP_TAB_IDS`` entry, ``"calculator"`` for the calculator page,
        or ``""`` when nothing matches.
    """
    normalized = (path or "").rstrip("/")
    # Calculator is not an ERP_PRIMARY_NAV_PATHS entry; map it explicitly (segment
    # boundary so /wdcalculatorx does not falsely match).
    if normalized == "/wdcalculator" or normalized.startswith("/wdcalculator/"):
        return "calculator"
    best_id = ""
    best_len = -1
    for nav_path, tab_id in zip(ERP_PRIMARY_NAV_PATHS, ERP_TAB_IDS):
        prefix = nav_path.rstrip("/")
        if normalized == prefix or normalized.startswith(prefix + "/"):
            if len(prefix) > best_len:
                best_len = len(prefix)
                best_id = tab_id
    return best_id


def build_tablet_rail_items(user: Any = None, path: str = "") -> list[dict[str, Any]]:
    """Build tablet-landscape global rail items for a request path (T2 rail).

    Thin wrapper over :func:`build_split_side_items` that derives the active tab id
    from ``path`` (:func:`resolve_tablet_rail_active_id`) so the global rail highlights
    the current ERP surface. Reuses the exact permission scoping + label/icon catalog
    of the split-shell rail — no navigation policy is duplicated.

    Args:
        user: Current user; needs a ``team`` attribute. ``None`` → full menu.
        path: Current request path used to resolve the active tab.

    Returns:
        Rail item descriptors (``id``/``label``/``icon``/``href``/``active``).
    """
    return build_split_side_items(user, active_id=resolve_tablet_rail_active_id(path))

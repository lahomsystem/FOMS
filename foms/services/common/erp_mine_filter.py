"""ERP global '내 담당/내 작업' filter — URL query + ``erp_mine_only`` cookie SSOT."""

from __future__ import annotations

from typing import Any

ERP_MINE_ONLY_COOKIE = "erp_mine_only"


def _cookie_mine_active(request: Any) -> bool:
    """Return True when the global mine-only preference cookie is set."""
    return (request.cookies.get(ERP_MINE_ONLY_COOKIE) or "").strip() == "1"


def erp_mine_only_from_request(request: Any, *, force: bool = False) -> bool:
    """Resolve list/dashboard mine filter from ``?mine=`` or cookie.

    Explicit ``?mine=`` (including empty) wins over the cookie so a page can
    opt out without clearing the global preference.
    """
    if force:
        return True
    if "mine" in request.args:
        return (request.args.get("mine") or "").strip() == "1"
    return _cookie_mine_active(request)


def erp_tower_mine_from_request(request: Any) -> bool:
    """Orders dashboard control-tower mine toggle (``tower_mine`` + cookie)."""
    if request.args.get("tower_mine") == "1":
        return True
    if "tower_mine" in request.args:
        return False
    return _cookie_mine_active(request)


def erp_mine_only_for_construction(request: Any, user: Any) -> bool:
    """Construction team always sees own orders; others use global mine filter."""
    is_construction = bool(user and getattr(user, "team", None) == "CONSTRUCTION")
    return is_construction or erp_mine_only_from_request(request)

"""ERP global '내 담당/내 작업' filter — URL query + ``erp_mine_only`` cookie SSOT.

켜진 프리랜서(FCOMM-01 §6.3 겹 3)는 손님 쪽 값(``?mine=`` · ``?tower_mine=`` · 쿠키)과 무관하게 늘 "내 것만"이다
— 시공팀 강제(:func:`erp_mine_only_for_construction`)와 같은 자리에서 강제한다. 프리랜서의 "내 것" 판정
자체(연결 표 하나)는 :mod:`foms.services.auth.freelancer_lists` 가 한다.
"""

from __future__ import annotations

from typing import Any

from foms.services.auth.freelancer_lists import current_user_is_list_freelancer

ERP_MINE_ONLY_COOKIE = "erp_mine_only"


def _cookie_mine_active(request: Any) -> bool:
    """Return True when the global mine-only preference cookie is set."""
    return (request.cookies.get(ERP_MINE_ONLY_COOKIE) or "").strip() == "1"


def erp_mine_only_from_request(request: Any, *, force: bool = False) -> bool:
    """Resolve list/dashboard mine filter from ``?mine=`` or cookie.

    Explicit ``?mine=`` (including empty) wins over the cookie so a page can
    opt out without clearing the global preference. 켜진 프리랜서는 끌 수 없다(늘 True).
    """
    if force or current_user_is_list_freelancer():
        return True
    if "mine" in request.args:
        return (request.args.get("mine") or "").strip() == "1"
    return _cookie_mine_active(request)


def erp_tower_mine_from_request(request: Any) -> bool:
    """Orders dashboard control-tower mine toggle (``tower_mine`` + cookie). 켜진 프리랜서는 늘 True."""
    if request.args.get("tower_mine") == "1" or current_user_is_list_freelancer():
        return True
    if "tower_mine" in request.args:
        return False
    return _cookie_mine_active(request)


def erp_mine_only_for_construction(request: Any, user: Any) -> bool:
    """Construction team always sees own orders; others use global mine filter."""
    is_construction = bool(user and getattr(user, "team", None) == "CONSTRUCTION")
    return is_construction or erp_mine_only_from_request(request)

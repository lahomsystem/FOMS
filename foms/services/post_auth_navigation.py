"""Canonical authenticated landing paths (legacy ``/`` vs ERP mobile ``/erp/dashboard``)."""

from __future__ import annotations

from flask import Request, g, redirect, session, url_for
from werkzeug.wrappers import Response

from foms.services.feature_flags import prefers_mobile_wizard_client, wizard_new_order_enabled
from foms.services.orders.order_mutation_policy import normalize_team

_BACKSLASH = chr(92)


def should_use_erp_mobile_home(user_id: int | None, request: Request) -> bool:
    """Return True when this client should treat ``/erp/dashboard`` as home.

    Args:
        user_id: Authenticated user id, or None when unknown.
        request: Current Flask/Werkzeug request.

    Returns:
        True for ERP mobile v2 cohort on mobile/PWA clients.
    """
    if user_id is None or not wizard_new_order_enabled(user_id):
        return False
    if prefers_mobile_wizard_client(request):
        return True
    mobile_app = (request.args.get("mobile_app") or "").strip().lower()
    return mobile_app in {"1", "true", "yes"}


def is_production_home_user(user: object | None) -> bool:
    """생산팀 직원인가 — 첫 화면이 생산 홈(``/erp/production/home``)인 사람(설계서 §12, D10·D12).

    조건 = 팀 PRODUCTION 이고 협력사 계정이 아님. 기기와 무관하다(PC 도 생산 홈). 프리랜서는
    영업팀만 될 수 있어(``freelancer_scope.could_be_freelancer``) 여기서 따로 보지 않는다.
    """
    if user is None:
        return False
    if getattr(user, "partner_org_id", None) is not None:
        return False
    return normalize_team(getattr(user, "team", None)) == "PRODUCTION"


def _is_production_home_user_id(user_id: int | None) -> bool:
    """id 로 판정 — 같은 요청이 이미 읽은 ``g.current_user`` 가 그 사람이면 다시 읽지 않는다."""
    if user_id is None:
        return False
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    current = getattr(g, "current_user", None)
    if current is not None and getattr(current, "id", None) == uid:
        return is_production_home_user(current)
    from db import get_db  # 지연 import: 서비스 모듈 import 순서(DB 바인딩) 유지
    from models import User

    return is_production_home_user(get_db().get(User, uid))


def production_home_url(**url_kwargs: str) -> str:
    """생산 홈 주소(착지 세 곳 + switch_user 가 같은 함수를 탄다)."""
    return url_for("erp_production_page.erp_production_home", **url_kwargs)


def authenticated_home_url(*, user_id: int | None, request: Request, **url_kwargs: str) -> str:
    """Resolve the default authenticated landing URL for this client.

    Args:
        user_id: Authenticated user id, or None when unknown.
        request: Current Flask/Werkzeug request.
        **url_kwargs: Optional query args forwarded to ``url_for``.

    Returns:
        Relative URL for ERP mobile home or legacy order list.
    """
    if _is_production_home_user_id(user_id):
        return production_home_url(**url_kwargs)
    if should_use_erp_mobile_home(user_id, request):
        return url_for("erp_dashboard.erp_dashboard", **url_kwargs)
    return url_for("order_pages.index", **url_kwargs)


def is_legacy_home_path(path: str | None) -> bool:
    """Return True for legacy desktop home aliases that mobile ERP should upgrade.

    Args:
        path: Relative path, optionally with query string.

    Returns:
        True for ``/`` and ``/orders`` variants.
    """
    pathname = (path or "").split("?", 1)[0].rstrip("/") or "/"
    return pathname in ("/", "/orders")


def normalize_internal_next_url(raw_next: str | None, *, fallback: str) -> str:
    """Normalize ``next`` to a safe same-origin relative path.

    Args:
        raw_next: Raw ``next`` query/form value.
        fallback: Path used when ``next`` is missing or invalid.

    Returns:
        Safe internal relative URL.
    """
    if not raw_next:
        return fallback
    next_url = str(raw_next).strip()
    if not next_url or next_url.startswith("//") or not next_url.startswith("/"):
        return fallback
    # Browsers read a backslash as "/" and drop tab/CR/LF inside URLs, so "/\host" or "/<TAB>/host" become
    # "//host" (another origin). Werkzeug keeps both in the Location header, so reject them here.
    if _BACKSLASH in next_url or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in next_url):
        return fallback
    return next_url


def resolve_post_login_redirect(
    raw_next: str | None,
    *,
    user_id: int,
    request: Request,
) -> str:
    """Pick the post-login redirect, upgrading legacy home paths on mobile ERP.

    Args:
        raw_next: Requested ``next`` destination.
        user_id: Newly authenticated user id.
        request: Current Flask/Werkzeug request.

    Returns:
        Relative redirect target.
    """
    fallback = authenticated_home_url(user_id=user_id, request=request)
    next_url = normalize_internal_next_url(raw_next, fallback=fallback)
    if is_legacy_home_path(next_url):
        if _is_production_home_user_id(user_id):
            return production_home_url()
        if should_use_erp_mobile_home(user_id, request):
            return url_for("erp_dashboard.erp_dashboard")
    return next_url


def redirect_to_authenticated_home(
    request: Request,
    *,
    user_id: int | None = None,
    **url_kwargs: str,
) -> Response:
    """HTTP redirect to the canonical authenticated home for this client.

    Args:
        request: Current Flask/Werkzeug request.
        user_id: Authenticated user id; defaults to ``session['user_id']``.
        **url_kwargs: Optional query args forwarded to ``url_for``.

    Returns:
        Flask redirect response.
    """
    resolved_user_id = user_id
    if resolved_user_id is None:
        raw_uid = session.get("user_id")
        resolved_user_id = int(raw_uid) if raw_uid is not None else None
    return redirect(
        authenticated_home_url(user_id=resolved_user_id, request=request, **url_kwargs)
    )

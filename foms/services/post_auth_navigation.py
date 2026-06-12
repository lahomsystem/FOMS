"""Canonical authenticated landing paths (legacy ``/`` vs ERP mobile ``/erp/dashboard``)."""

from __future__ import annotations

from flask import Request, redirect, session, url_for
from werkzeug.wrappers import Response

from foms.services.feature_flags import prefers_mobile_wizard_client, wizard_new_order_enabled


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


def authenticated_home_url(*, user_id: int | None, request: Request, **url_kwargs: str) -> str:
    """Resolve the default authenticated landing URL for this client.

    Args:
        user_id: Authenticated user id, or None when unknown.
        request: Current Flask/Werkzeug request.
        **url_kwargs: Optional query args forwarded to ``url_for``.

    Returns:
        Relative URL for ERP mobile home or legacy order list.
    """
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
    if not next_url or next_url.startswith("//"):
        return fallback
    if next_url.startswith("/"):
        return next_url
    return fallback


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
    if is_legacy_home_path(next_url) and should_use_erp_mobile_home(user_id, request):
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

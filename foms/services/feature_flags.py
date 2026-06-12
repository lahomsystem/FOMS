"""Environment-backed feature flags and cohort rollout helpers."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from werkzeug.wrappers import Request

__all__ = [
    "env_bool",
    "env_bool_or_mobile_v2",
    "env_id_list",
    "is_cohort_all",
    "is_enabled_for_user",
    "prefers_mobile_wizard_client",
    "should_render_new_order_wizard",
    "wizard_new_order_enabled",
]

_MOBILE_UA_RE = re.compile(
    r"(android|webos|iphone|ipod|blackberry|iemobile|opera mini|mobile)",
    re.IGNORECASE,
)

_TRUTHY = frozenset({"true", "1", "yes", "y", "on"})
_COHORT_ALL_TOKENS = frozenset({"all", "*"})


def env_bool(key: str, default: bool = False) -> bool:
    """Return whether an environment variable is truthy.

    Args:
        key: Environment variable name.
        default: Value used when ``key`` is unset.

    Returns:
        True when the normalized env value is one of true/1/yes/y/on.
    """
    raw = os.getenv(key, str(default))
    return raw.strip().lower() in _TRUTHY


def env_bool_or_mobile_v2(key: str, *, mobile_v2_active: bool = False) -> bool:
    """Return explicit env flag, or mobile v2 cohort when env is unset.

    P0-02~04 gap patch: cohort users see thumbnails without extra ops flags.
    Explicit ``false`` / ``0`` still disables rollout.

    Args:
        key: Environment variable name (e.g. ``FOMS_V3_DRAWING_THUMB_ENABLED``).
        mobile_v2_active: Whether ERP mobile v2 shell is active for the user.

    Returns:
        Parsed env value when set; otherwise ``mobile_v2_active``.
    """
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return mobile_v2_active
    return raw.strip().lower() in _TRUTHY


def env_id_list(key: str) -> set[int]:
    """Parse a comma-separated list of integer user ids from the environment.

    Args:
        key: Environment variable name.

    Returns:
        Set of parsed integer ids; non-numeric tokens are ignored.
    """
    raw = os.getenv(key, "")
    return {int(part) for part in raw.split(",") if part.strip().isdigit()}


def is_cohort_all(key: str) -> bool:
    """Return whether a cohort env value requests rollout to all users.

    Recognizes comma-separated tokens ``all``, ``*``, or ``ALL`` (case-insensitive
    for ``all``). Numeric ids in the same value are ignored when an all-token is
    present.

    Args:
        key: Environment variable name (e.g. ``FOMS_V3_SHELL_COHORT``).

    Returns:
        True when any comma-separated token is an all-rollout sentinel.
    """
    raw = os.getenv(key, "")
    for part in raw.split(","):
        if part.strip().lower() in _COHORT_ALL_TOKENS:
            return True
    return False


def is_enabled_for_user(
    flag: str,
    user_id: int | None = None,
    cohort_key: str | None = None,
) -> bool:
    """Check whether a flag is enabled for a specific user via cohort whitelist.

    Global flag must be truthy. Cohort may be a numeric id list, the sentinel
    ``all`` / ``*`` / ``ALL`` (case-insensitive for ``all``), or empty. When the
    cohort env is empty, the flag is treated as disabled even if the global
    switch is on.

    Args:
        flag: Flag name, with or without the ``_ENABLED`` suffix.
        user_id: Current user id, or None when unauthenticated.
        cohort_key: Optional env var name for the cohort id list. When omitted,
            ``{base}_COHORT`` is derived from ``flag``.

    Returns:
        True when the flag is on, ``user_id`` is set, and either the cohort env
        contains an all-rollout token or ``user_id`` is in the parsed id list.
    """
    enabled_key = flag if flag.endswith("_ENABLED") else f"{flag}_ENABLED"
    if not env_bool(enabled_key):
        return False
    base = flag[:-8] if flag.endswith("_ENABLED") else flag
    ck = cohort_key or f"{base}_COHORT"
    if is_cohort_all(ck):
        return user_id is not None
    cohort = env_id_list(ck)
    if not cohort:
        return False
    return user_id is not None and user_id in cohort


def wizard_new_order_enabled(user_id: int | None = None) -> bool:
    """주문 생성 wizard(모바일 4단계) 기능 활성 여부.

    전역 ``FOMS_WIZARD_NEW_ORDER_ENABLED`` 플래그가 켜져 있거나, 사용자가 ERP
    모바일 v2 코호트에 속하면 wizard API·draft 경로를 활성화한다.
    실제 ``/add`` 렌더는 :func:`should_render_new_order_wizard`가 모바일
    클라이언트 여부까지 함께 판정한다.

    Args:
        user_id: 현재 사용자 id(미인증 시 None).

    Returns:
        wizard 기능을 켜야 하면 True.
    """
    if env_bool("FOMS_WIZARD_NEW_ORDER_ENABLED"):
        return True
    return is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED", user_id, cohort_key="FOMS_V3_SHELL_COHORT"
    )


def prefers_mobile_wizard_client(request: Request) -> bool:
    """모바일 new-order wizard 셸을 노출해야 하는 클라이언트인지 판정.

    모바일 v2 FAB·휴대폰 브라우저는 wizard로, PC 브라우저는 데스크톱
    ``add_order`` 탭 UI로 분기하기 위한 단일 기준이다.

    Args:
        request: 현재 Flask/Werkzeug request.

    Returns:
        wizard 셸을 렌더해야 하면 True.
    """
    wizard_arg = (request.args.get("wizard") or "").strip().lower()
    if wizard_arg in {"1", "true", "yes"}:
        return True
    sec_mobile = (request.headers.get("Sec-CH-UA-Mobile") or "").strip()
    if sec_mobile == "?1":
        return True
    ua = request.headers.get("User-Agent") or ""
    return _MOBILE_UA_RE.search(ua) is not None


def should_render_new_order_wizard(
    user_id: int | None,
    request: Request,
) -> bool:
    """``/add`` GET에서 wizard 셸을 렌더할지 여부.

    Args:
        user_id: 현재 사용자 id(미인증 시 None).
        request: 현재 Flask/Werkzeug request.

    Returns:
        wizard 셸을 렌더해야 하면 True.
    """
    if not wizard_new_order_enabled(user_id):
        return False
    return prefers_mobile_wizard_client(request)

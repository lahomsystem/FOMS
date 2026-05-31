"""Environment-backed feature flags and cohort rollout helpers."""

from __future__ import annotations

import os

__all__ = [
    "env_bool",
    "env_bool_or_mobile_v2",
    "env_id_list",
    "is_cohort_all",
    "is_enabled_for_user",
]

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

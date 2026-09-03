"""User last-seen tracking (LAST-SEEN-01).

`User.last_login` used to be written only by the login route, but sessions are
permanent for `FOMS_SESSION_DAYS` (30 by default) and refresh on every request,
so a daily user could go months without logging in again and the admin user list
showed a timestamp frozen in the past.

This module keeps that same column tracking the user's *most recent activity*
instead. The true login moment is still audited in the security log
(`LOGIN_OK`), so no history is lost by the change.

Writes are throttled per session (default 5 minutes) so a normal page load costs
no extra UPDATE.
"""

from __future__ import annotations

import os
import time
from typing import Any

from flask import session
from sqlalchemy import update

from foms.services.datetime_kst import now_utc_naive
from foms.services.error_logging import log_handled_exception

_SESSION_KEY = "last_seen_touch_ts"
_DEFAULT_INTERVAL_SECONDS = 300


def touch_interval_seconds() -> int:
    """Minimum seconds between two last-seen writes for one session."""
    raw = os.environ.get("FOMS_LAST_SEEN_TOUCH_SECONDS", "") or ""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_INTERVAL_SECONDS
    return max(0, value)


def touch_last_seen(user: Any) -> bool:
    """Record `user` as active now, at most once per throttle window.

    The write runs on its own short-lived connection instead of the request's
    ORM session. Committing the request session here would expire every object
    already loaded in it, which detaches rows the caller still holds
    (DetachedInstanceError) — the update must stay invisible to the request.

    Args:
        user: The `User` row for the current request (may be ``None``).

    Returns:
        True when the timestamp was written, False when throttled or skipped.
    """
    user_id = getattr(user, "id", None)
    if not user_id:
        return False

    interval = touch_interval_seconds()
    now_ts = time.time()
    last_ts = session.get(_SESSION_KEY)
    if isinstance(last_ts, (int, float)) and (now_ts - last_ts) < interval:
        return False

    from db import engine
    from models import User

    try:
        with engine.begin() as conn:
            conn.execute(
                update(User).where(User.id == user_id).values(last_login=now_utc_naive())
            )
    except Exception:
        # A last-seen write must never break the request it rides on, but the
        # failure still has to be visible in the server log (fail-open policy).
        log_handled_exception("user_activity.touch_last_seen")
        return False

    session[_SESSION_KEY] = now_ts
    return True

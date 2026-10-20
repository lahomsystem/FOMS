"""세션 세대 번호·로그아웃 회수 목록 (SPEC 2026-10-20-session-revoke).

로그인 상태는 서명된 쿠키에만 있어서 서버가 개별로 끊을 수 없었다. 사용자 행의 두 칸으로
끊는다 — 요청마다 ``_set_current_user`` 가 이미 그 행을 읽으므로 쿼리가 늘지 않는다.

* ``users.session_version`` — 비밀번호·역할이 바뀌면 +1. 그 계정의 모든 세션이 끊긴다.
* ``users.revoked_session_ids`` — 로그아웃한 세션 표지(``sid``). 그 기기만 끊긴다.
"""
from __future__ import annotations

import secrets
import time
from typing import Any, MutableMapping

SESSION_VERSION_KEY = "sv"
SESSION_ID_KEY = "sid"
IMPERSONATOR_VERSION_KEY = "impersonator_sv"

#: 쿠키 수명(30일) + 하루. 이보다 오래된 회수 표지는 쿠키가 이미 죽었으므로 지운다.
_REVOKE_TTL_SECONDS = 31 * 24 * 3600
_REVOKE_MAX = 200


def new_session_id() -> str:
    return secrets.token_urlsafe(9)


def user_session_version(user: Any) -> int:
    return int(getattr(user, "session_version", None) or 0)


def pin_session(sess: MutableMapping[str, Any], user: Any) -> None:
    """로그인 직후 세션을 이 사용자의 현재 세대 번호와 새 표지로 묶는다."""
    sess[SESSION_VERSION_KEY] = user_session_version(user)
    sess[SESSION_ID_KEY] = new_session_id()


def _revoked_ids(user: Any) -> set[str]:
    return {str(e.get("sid")) for e in (getattr(user, "revoked_session_ids", None) or [])
            if isinstance(e, dict) and e.get("sid")}


def session_is_current(sess: MutableMapping[str, Any], user: Any,
                       *, version_key: str = SESSION_VERSION_KEY) -> bool:
    """세션이 아직 유효한가 — 세대 번호가 같고 회수 목록에 없어야 한다.

    번호가 없는 옛 세션(이 기능 배포 전 로그인)은 0 으로 본다. 사용자 번호도 처음엔 0 이라
    배포 순간 전 직원이 로그아웃되지 않고, 비밀번호·역할이 바뀐 계정만 끊긴다.
    """
    try:
        pinned = int(sess.get(version_key) or 0)
    except (TypeError, ValueError):
        return False
    if pinned != user_session_version(user):
        return False
    sid = sess.get(SESSION_ID_KEY)
    return not (sid and str(sid) in _revoked_ids(user))


def impersonator_ok(sess: MutableMapping[str, Any]) -> bool:
    """대리 로그인 세션이면 원 관리자가 아직 활성 ADMIN 이고 그 세션이 유효한지 본다.

    전환 세션에서만 사용자 행을 한 번 더 읽는다(평소 요청은 쿼리 증가 0).
    """
    admin_id = sess.get("impersonating_from")
    if not admin_id:
        return True
    from db import get_db
    from models import User

    try:
        admin = get_db().get(User, int(admin_id))
    except (TypeError, ValueError):
        return False
    if admin is None or not admin.is_active or (admin.role or "").strip().upper() != "ADMIN":
        return False
    return session_is_current(sess, admin, version_key=IMPERSONATOR_VERSION_KEY)


def revoke_session(user: Any, sid: Any) -> None:
    """로그아웃한 세션 표지를 사용자 회수 목록에 넣는다(호출자가 commit)."""
    if not sid:
        return
    now = int(time.time())
    kept = [e for e in (getattr(user, "revoked_session_ids", None) or [])
            if isinstance(e, dict) and now - int(e.get("at") or 0) < _REVOKE_TTL_SECONDS]
    kept.append({"sid": str(sid), "at": now})
    # JSON 칸은 새 리스트를 대입해야 변경으로 잡힌다.
    user.revoked_session_ids = kept[-_REVOKE_MAX:]


def bump_session_version(user: Any) -> None:
    """이 계정의 모든 세션을 끊는다(호출자가 commit)."""
    user.session_version = user_session_version(user) + 1

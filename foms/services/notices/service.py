"""공지 서비스(받는 사람 쪽) — 설계서 2026-11-02-foms-notices §3.

받는 사람 판정은 :mod:`.audience` 한 곳. 관리자 쪽(만들기 · 고치기 · 지우기 · 확인 현황 · 목록)은 :mod:`.admin` 에 있고
여기서 같은 이름으로 다시 내보낸다(설계서의 ``service.create_notice`` 등). 쓰기 함수는 commit 하지 않는다 — 부르는 쪽이
commit 한다. 시간은 UTC naive 로 저장하고 화면 글은 한국 시간(KST)으로 만든다.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from foms.services.datetime_kst import format_datetime_kst, now_utc_naive
from foms.services.notices.admin import (  # noqa: F401 — 설계서 이름 그대로 다시 내보낸다
    ack_status,
    admin_notice_rows,
    audience_options,
    create_notice,
    delete_notice,
    notice_detail,
    update_notice,
)
from foms.services.notices.audience import audience_label, is_live, user_matches
from foms.services.notices.payload import NoticeInputError  # noqa: F401
from models import Notice, NoticeAck, PartnerOrg

__all__ = [
    "NoticeInputError",
    "ack_notice",
    "ack_status",
    "admin_notice_rows",
    "audience_options",
    "create_notice",
    "delete_notice",
    "live_notices_query",
    "mark_read",
    "notice_detail",
    "pending_popups",
    "pending_popups_from",
    "unread_count",
    "update_notice",
    "visible_notices",
]

#: 창 공지는 한 번에 최대 5건(오래된 것부터) — 기존 협력사 공지 창과 같다.
POPUP_LIMIT = 5
_CREATED_FMT = "%Y-%m-%d %H:%M"


def live_notices_query(db, now: Optional[datetime.datetime] = None):
    """게시 중 공지 질의(지우지 않음 · 시작 지남 · 끝 안 지남) — 고정 먼저 · 최근 순."""
    now = now or now_utc_naive()
    return (
        db.query(Notice)
        .filter(
            Notice.deleted_at.is_(None),
            or_(Notice.starts_at.is_(None), Notice.starts_at <= now),
            or_(Notice.ends_at.is_(None), Notice.ends_at > now),
        )
        .order_by(Notice.pinned.desc(), Notice.created_at.desc(), Notice.id.desc())
    )


def _org_active(db, user: Any) -> bool:
    """협력사 직원이면 그 협력사가 켜져 있는가(본사 직원은 True)."""
    org_id = getattr(user, "partner_org_id", None)
    if org_id is None:
        return True
    org = db.get(PartnerOrg, int(org_id))
    return bool(org is not None and org.is_active)


def _my_notices(db, user: Any, now: Optional[datetime.datetime] = None) -> list[Notice]:
    """이 사람이 지금 받는 게시 중 공지(고정 먼저 · 최근 순)."""
    if user is None or getattr(user, "id", None) is None:
        return []
    org_active = _org_active(db, user)
    return [n for n in live_notices_query(db, now).all() if user_matches(n, user, org_active)]


def _acks_for(db, user_id: int, notice_ids: list[int]) -> dict[int, NoticeAck]:
    if not notice_ids:
        return {}
    rows = (
        db.query(NoticeAck)
        .filter(NoticeAck.user_id == int(user_id), NoticeAck.notice_id.in_(notice_ids))
        .all()
    )
    return {int(r.notice_id): r for r in rows}


def _org_names(db, notices: list[Notice]) -> dict[int, str]:
    ids: set[int] = set()
    for n in notices:
        for raw in n.audience_partner_org_ids or []:
            try:
                ids.add(int(raw))
            except (TypeError, ValueError):
                continue
    if not ids:
        return {}
    return {int(o.id): o.name for o in db.query(PartnerOrg).filter(PartnerOrg.id.in_(ids)).all()}


def _created_text(value: Optional[datetime.datetime]) -> str:
    return format_datetime_kst(value, _CREATED_FMT) or ""


def visible_notices(db, user: Any) -> list[dict[str, Any]]:
    """내 공지 목록(게시 중 · 받는 사람인 것) — 고정 먼저 · 최근 순.

    Returns:
        ``[{id, title, body, pinned, display_mode, created_at(KST 글), created_by_name, read, acked, audience_label}]``
    """
    notices = _my_notices(db, user)
    acks = _acks_for(db, user.id, [int(n.id) for n in notices]) if notices else {}
    names = _org_names(db, notices)
    items: list[dict[str, Any]] = []
    for n in notices:
        ack = acks.get(int(n.id))
        acked = bool(ack is not None and ack.ack_at is not None)
        items.append({
            "id": int(n.id),
            "title": n.title or "",
            "body": n.body or "",
            "pinned": bool(n.pinned),
            "display_mode": n.display_mode,
            "created_at": _created_text(n.created_at),
            "created_by_name": n.created_by_name or "",
            "read": bool(ack is not None and (ack.read_at is not None or acked)),
            "acked": acked,
            "audience_label": audience_label(n, names),
        })
    return items


def pending_popups_from(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """:func:`visible_notices` 결과에서 확인 안 한 창 공지(오래된 것부터 최대 5) — 다시 읽지 않는다."""
    popups = [i for i in items if i["display_mode"] == "POPUP" and not i["acked"]]
    popups.sort(key=lambda i: (i["created_at"], i["id"]))
    return [
        {k: i[k] for k in ("id", "title", "body", "created_by_name", "created_at")}
        for i in popups[:POPUP_LIMIT]
    ]


def pending_popups(db, user: Any) -> list[dict[str, Any]]:
    """확인 안 한 창(POPUP) 공지 — 오래된 것부터 최대 5. ``{id, title, body, created_by_name, created_at}``."""
    return pending_popups_from(visible_notices(db, user))


def unread_count(db, user: Any) -> int:
    """안 읽은 공지 수(목록 배지)."""
    return sum(1 for item in visible_notices(db, user) if not item["read"])


def _target(db, user: Any, notice_id: Any) -> Optional[Notice]:
    """게시 중이고 이 사람이 받는 공지 — 아니면 None(남의 공지 · 없는 공지 · 지난 공지)."""
    if user is None or getattr(user, "id", None) is None:
        return None
    try:
        nid = int(notice_id)
    except (TypeError, ValueError):
        return None
    notice = db.get(Notice, nid)
    if notice is None or not is_live(notice):
        return None
    if not user_matches(notice, user, _org_active(db, user)):
        return None
    return notice


def _ack_row(db, notice_id: int, user_id: int) -> NoticeAck:
    """(공지, 사람) 기록 줄 — 없으면 만든다. 두 번 눌러 같이 만들면 먼저 만든 줄을 쓴다."""
    row = db.query(NoticeAck).filter(NoticeAck.notice_id == notice_id, NoticeAck.user_id == user_id).first()
    if row is not None:
        return row
    savepoint = db.begin_nested()
    try:
        row = NoticeAck(notice_id=notice_id, user_id=user_id)
        db.add(row)
        db.flush()
        savepoint.commit()
        return row
    except IntegrityError:
        savepoint.rollback()
        return db.query(NoticeAck).filter(NoticeAck.notice_id == notice_id, NoticeAck.user_id == user_id).one()


def ack_notice(db, user: Any, notice_id: Any) -> bool:
    """공지 확인(창의 "확인") — 확인 · 읽음 때를 채운다(없으면 줄을 만든다). 받는 사람이 아니거나 없으면 False.

    이미 확인했으면 처음 때를 그대로 두고 True. commit 은 부르는 쪽.
    """
    notice = _target(db, user, notice_id)
    if notice is None:
        return False
    row = _ack_row(db, int(notice.id), int(user.id))
    now = now_utc_naive()
    if row.ack_at is None:
        row.ack_at = now
    if row.read_at is None:
        row.read_at = now
    return True


def mark_read(db, user: Any, notice_id: Any) -> bool:
    """공지 읽음(목록에서 열어 봄) — 읽은 때만 채운다. 받는 사람이 아니거나 없으면 False. commit 은 부르는 쪽."""
    notice = _target(db, user, notice_id)
    if notice is None:
        return False
    row = _ack_row(db, int(notice.id), int(user.id))
    if row.read_at is None:
        row.read_at = now_utc_naive()
    return True

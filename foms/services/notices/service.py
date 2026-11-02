"""공지 서비스(받는 사람 쪽) — 설계서 2026-11-02-foms-notices §3.

받는 사람 판정은 :mod:`.audience` 한 곳. 관리자 쪽(만들기 · 고치기 · 지우기 · 확인 현황 · 목록)은 :mod:`.admin` 에 있고
여기서 같은 이름으로 다시 내보낸다(설계서의 ``service.create_notice`` 등). 쓰기 함수는 commit 하지 않는다 — 부르는 쪽이
commit 한다. 시간은 UTC naive 로 저장하고 화면 글은 한국 시간(KST)으로 만든다.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy import false, or_, type_coerce
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer

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
from foms.services.notices.audience import is_live, user_matches, viewer_audience_label
from foms.services.notices.payload import NoticeInputError  # noqa: F401
from foms.services.orders.order_mutation_policy import normalize_team
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
    "notice_summary",
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


def _jsonb(db) -> bool:
    """PostgreSQL 이면 받는 쪽 목록(JSONB)을 SQL 의 ``@>`` 로 거른다. SQLite 시험 레인은 넓게 거르고 파이썬이 마저 본다."""
    bind = db.get_bind()
    return getattr(getattr(bind, "dialect", None), "name", "") == "postgresql"


def _audience_clause(db, user: Any, org_active: bool):
    """받는 쪽 조건을 SQL 로 먼저 줄인다(본사 전체 · 팀 포함 / 협력사 전체 · 회사 포함).

    최종 판정은 :func:`user_matches` 가 파이썬에서 한 번 더 한다(꺼진 계정 · 정규화 · 숫자가 아닌 값). 여기서는
    :func:`user_matches` 가 받는다고 할 줄을 빼지 않는 것만 지킨다 — 팀 · 회사 목록은 저장할 때 정규화된 값이다
    (:func:`foms.services.notices.payload.parse_notice_payload`).
    """
    org_id = getattr(user, "partner_org_id", None)
    if org_id is None:
        team = normalize_team(getattr(user, "team", None))
        if not team:
            return Notice.audience_staff_all.is_(True)
        if _jsonb(db):
            hit = type_coerce(Notice.audience_staff_teams, JSONB).contains([team])
        else:
            hit = Notice.audience_staff_teams.isnot(None)
        return or_(Notice.audience_staff_all.is_(True), hit)
    if not org_active:
        return false()
    if _jsonb(db):
        hit = type_coerce(Notice.audience_partner_org_ids, JSONB).contains([int(org_id)])
    else:
        hit = Notice.audience_partner_org_ids.isnot(None)
    return or_(Notice.audience_partner_all.is_(True), hit)


def _my_notices(db, user: Any, now: Optional[datetime.datetime] = None, *, with_body: bool = True) -> list[Notice]:
    """이 사람이 지금 받는 게시 중 공지(고정 먼저 · 최근 순). ``with_body=False`` 면 본문을 읽지 않는다(창 · 배지용)."""
    if user is None or getattr(user, "id", None) is None:
        return []
    org_active = _org_active(db, user)
    query = live_notices_query(db, now).filter(_audience_clause(db, user, org_active))
    if not with_body:
        query = query.options(defer(Notice.body))
    return [n for n in query.all() if user_matches(n, user, org_active)]


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
    """받는 쪽 이름에 쓸 협력사 이름(본사 직원 화면만 부른다)."""
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
    """내 공지 목록(게시 중 · 받는 사람인 것) — 고정 먼저 · 최근 순. 본문까지 싣는다 — 목록 화면 · 목록 API 만 쓴다.

    ``audience_label`` 은 보는 사람에게 맞춘다 — 협력사 직원에게는 다른 회사 이름 · 본사 팀을 보이지 않는다
    (:func:`foms.services.notices.audience.viewer_audience_label`).

    Returns:
        ``[{id, title, body, pinned, display_mode, created_at(KST 글), created_by_name, read, acked, audience_label}]``
    """
    notices = _my_notices(db, user)
    acks = _acks_for(db, user.id, [int(n.id) for n in notices]) if notices else {}
    staff_viewer = user is not None and getattr(user, "partner_org_id", None) is None
    names = _org_names(db, notices) if staff_viewer else {}
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
            "audience_label": viewer_audience_label(n, user, names),
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


def _tally(db, user: Any) -> tuple[int, list[Notice]]:
    """(안 읽은 수, 확인 안 한 창 공지 오래된 것부터 최대 5) — 본문 없이 공지 1번 · 확인 기록 1번만 읽는다."""
    notices = _my_notices(db, user, with_body=False)
    if not notices:
        return 0, []
    acks = _acks_for(db, user.id, [int(n.id) for n in notices])
    unread = 0
    popups: list[Notice] = []
    for n in notices:
        ack = acks.get(int(n.id))
        acked = ack is not None and ack.ack_at is not None
        if not (acked or (ack is not None and ack.read_at is not None)):
            unread += 1
        if n.display_mode == "POPUP" and not acked:
            popups.append(n)
    popups.sort(key=lambda n: (n.created_at or datetime.datetime.min, int(n.id)))
    return unread, popups[:POPUP_LIMIT]


def notice_summary(db, user: Any) -> dict[str, Any]:
    """창 · 배지용 요약 ``{pending, unread}`` — 공지 목록 본문은 읽지 않는다(창에 띄울 최대 5건 본문만 한 번 더).

    질의 수는 공지 수와 무관하게 일정하다(협력사 회사 1 · 공지 1 · 확인 기록 1 · 창 본문 1).
    ``pending`` 항목: ``{id, title, body, created_by_name, created_at}``.
    """
    unread, popups = _tally(db, user)
    if not popups:
        return {"pending": [], "unread": unread}
    ids = [int(n.id) for n in popups]
    bodies = {int(i): b for i, b in db.query(Notice.id, Notice.body).filter(Notice.id.in_(ids)).all()}
    pending = [{
        "id": int(n.id),
        "title": n.title or "",
        "body": bodies.get(int(n.id)) or "",
        "created_by_name": n.created_by_name or "",
        "created_at": _created_text(n.created_at),
    } for n in popups]
    return {"pending": pending, "unread": unread}


def pending_popups(db, user: Any) -> list[dict[str, Any]]:
    """확인 안 한 창(POPUP) 공지 — 오래된 것부터 최대 5. ``{id, title, body, created_by_name, created_at}``."""
    return notice_summary(db, user)["pending"]


def unread_count(db, user: Any) -> int:
    """안 읽은 공지 수(목록 배지) — 본문을 읽지 않는다."""
    return _tally(db, user)[0]


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

"""공지 관리자 쪽 — 만들기 · 고치기 · 지우기(soft) · 목록 · 확인 현황 · 받는 사람 고르기(설계서 2026-11-02-foms-notices §3 · §4).

쓰기마다 감사 원장(``SecurityLog``) 한 줄 — action ``NOTICE_CREATED`` · ``NOTICE_UPDATED`` · ``NOTICE_DELETED``,
대상 ``notice``. 본문 원문은 원장에 넣지 않는다(제목 · 받는 쪽 · 보이는 방식만). commit 은 부르는 쪽.
설계서 이름(``service.create_notice`` 등)은 :mod:`.service` 가 다시 내보낸다.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from foms.services.datetime_kst import format_datetime_kst, now_utc_naive
from foms.services.notices.audience import (
    NOTICE_TEAM_CODES,
    audience_label,
    audience_pool,
    notice_org_ids,
    notice_team_codes,
    notice_team_label,
    recipients,
)
from foms.services.notices.payload import format_input_kst, parse_notice_payload
from foms.services.orders.order_mutation_policy import normalize_team
from models import Notice, NoticeAck, PartnerOrg, SecurityLog

__all__ = [
    "ack_status",
    "admin_notice_rows",
    "audience_options",
    "create_notice",
    "delete_notice",
    "notice_detail",
    "update_notice",
]

_CREATED_FMT = "%Y-%m-%d %H:%M"
_AUDIT_TARGET = "notice"
#: 고치기 감사에 적는 칸(바뀐 칸 이름만 — 본문 원문은 적지 않는다).
_TRACKED_FIELDS = (
    "title", "body", "audience_staff_all", "audience_staff_teams", "audience_partner_all",
    "audience_partner_org_ids", "display_mode", "pinned", "starts_at", "ends_at",
)


def _kst(value) -> str:
    """UTC naive → 한국 시간 글(``YYYY-MM-DD HH:MM``). 비면 빈 글."""
    if value is None:
        return ""
    return format_datetime_kst(value, _CREATED_FMT) or ""


def _org_name_map(db) -> dict[int, str]:
    return {int(o.id): o.name for o in db.query(PartnerOrg).all()}


def _audit(db, actor: Any, action: str, notice: Notice, message: str, **detail: Any) -> None:
    db.add(SecurityLog(
        user_id=getattr(actor, "id", None), action=action, target_type=_AUDIT_TARGET, target_id=int(notice.id),
        message=message, detail={"title": notice.title, **detail},
    ))


def _live_notice(db, notice_id: Any) -> Optional[Notice]:
    """지우지 않은 공지 — 없거나 지웠으면 None."""
    try:
        nid = int(notice_id)
    except (TypeError, ValueError):
        return None
    notice = db.get(Notice, nid)
    if notice is None or notice.deleted_at is not None:
        return None
    return notice


def create_notice(db, actor: Any, payload: Any) -> Notice:
    """공지 만들기(검증 → 한 줄 + 감사). 틀리면 :class:`~.payload.NoticeInputError`."""
    values = parse_notice_payload(db, payload)
    notice = Notice(
        created_by_user_id=getattr(actor, "id", None),
        created_by_name=(getattr(actor, "name", None) or "")[:100] or None,
        **values,
    )
    db.add(notice)
    db.flush()
    label = audience_label(notice, _org_name_map(db))
    _audit(db, actor, "NOTICE_CREATED", notice, f"공지 만듦: {notice.title} ({label})",
           audience=label, display_mode=notice.display_mode, pinned=bool(notice.pinned))
    return notice


def update_notice(db, actor: Any, notice_id: Any, payload: Any) -> Optional[Notice]:
    """공지 고치기 — 없거나 지운 공지면 None. 틀리면 :class:`~.payload.NoticeInputError`.

    받는 쪽을 바꿔도 이미 남은 확인 기록은 지우지 않는다(현황은 지금 받는 사람 기준으로 센다).
    """
    notice = _live_notice(db, notice_id)
    if notice is None:
        return None
    values = parse_notice_payload(db, payload)
    changed = [f for f in _TRACKED_FIELDS if getattr(notice, f) != values[f]]
    for field, value in values.items():
        setattr(notice, field, value)
    notice.updated_at = now_utc_naive()
    db.flush()
    label = audience_label(notice, _org_name_map(db))
    _audit(db, actor, "NOTICE_UPDATED", notice, f"공지 고침: {notice.title} ({label})",
           audience=label, changed=changed, display_mode=notice.display_mode)
    return notice


def delete_notice(db, actor: Any, notice_id: Any) -> bool:
    """공지 지우기(soft — ``deleted_at``). 없거나 이미 지웠으면 False."""
    notice = _live_notice(db, notice_id)
    if notice is None:
        return False
    notice.deleted_at = now_utc_naive()
    db.flush()
    _audit(db, actor, "NOTICE_DELETED", notice, f"공지 지움: {notice.title}")
    return True


def _acked_by_notice(db, notice_ids: list[int]) -> dict[int, set[int]]:
    """공지 id → 확인한 사람 id 집합(한 번에 읽는다)."""
    out: dict[int, set[int]] = {nid: set() for nid in notice_ids}
    if not notice_ids:
        return out
    rows = (
        db.query(NoticeAck.notice_id, NoticeAck.user_id)
        .filter(NoticeAck.notice_id.in_(notice_ids), NoticeAck.ack_at.isnot(None))
        .all()
    )
    for nid, uid in rows:
        out.setdefault(int(nid), set()).add(int(uid))
    return out


def admin_notice_rows(db) -> list[dict[str, Any]]:
    """관리자 목록(지운 것 빼고, 고정 먼저 · 최근 순).

    Returns:
        ``[{id, title, pinned, display_mode, audience_label, starts_at, ends_at, created_at, created_by_name,
        ack: {total, acked}}]`` — 시간은 한국 시간 글(``starts_at`` · ``ends_at`` 은 입력 칸 모양, 비면 빈 글).
    """
    notices = (
        db.query(Notice)
        .filter(Notice.deleted_at.is_(None))
        .order_by(Notice.pinned.desc(), Notice.created_at.desc(), Notice.id.desc())
        .all()
    )
    if not notices:
        return []
    pool = audience_pool(db)
    names = _org_name_map(db)
    acked = _acked_by_notice(db, [int(n.id) for n in notices])
    rows: list[dict[str, Any]] = []
    for n in notices:
        people = {int(u.id) for u in recipients(db, n, pool)}
        rows.append({
            "id": int(n.id),
            "title": n.title or "",
            "pinned": bool(n.pinned),
            "display_mode": n.display_mode,
            "audience_label": audience_label(n, names),
            "starts_at": format_input_kst(n.starts_at),
            "ends_at": format_input_kst(n.ends_at),
            "created_at": _kst(n.created_at),
            "created_by_name": n.created_by_name or "",
            "ack": {"total": len(people), "acked": len(people & acked.get(int(n.id), set()))},
        })
    return rows


def notice_detail(db, notice_id: Any) -> Optional[dict[str, Any]]:
    """고치기 화면용 공지 한 건(지운 공지는 None) — 페이로드와 같은 모양 + 표시 칸."""
    notice = _live_notice(db, notice_id)
    if notice is None:
        return None
    return {
        "id": int(notice.id),
        "title": notice.title or "",
        "body": notice.body or "",
        "audience": {
            "staff_all": bool(notice.audience_staff_all),
            "staff_teams": notice_team_codes(notice),
            "partner_all": bool(notice.audience_partner_all),
            "partner_org_ids": notice_org_ids(notice),
        },
        "display_mode": notice.display_mode,
        "pinned": bool(notice.pinned),
        "starts_at": format_input_kst(notice.starts_at),
        "ends_at": format_input_kst(notice.ends_at),
        "created_at": _kst(notice.created_at),
        "created_by_name": notice.created_by_name or "",
        "audience_label": audience_label(notice, _org_name_map(db)),
    }


def _group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """확인 안 한 사람 먼저 · 이름 순 + 수."""
    rows.sort(key=lambda r: (bool(r["acked_at"]), r["name"], r["user_id"]))
    return {"total": len(rows), "acked": sum(1 for r in rows if r["acked_at"]), "people": rows}


def ack_status(db, notice_id: Any) -> Optional[dict[str, Any]]:
    """확인 현황 — 지금 받는 사람 기준. 없거나 지운 공지면 None.

    Returns:
        ``{notice: {id, title, audience_label, display_mode}, total, acked,
        staff: {total, acked, people: [{user_id, name, team_label, acked_at, read_at}]},
        partner: {total, acked, people: [{user_id, name, org_name, acked_at, read_at}]}}`` — 사람은 확인 안 한 사람 먼저 ·
        이름 순, 시간은 한국 시간 글(비면 빈 글).
    """
    notice = _live_notice(db, notice_id)
    if notice is None:
        return None
    pool = audience_pool(db)
    acks = {int(r.user_id): r for r in db.query(NoticeAck).filter(NoticeAck.notice_id == int(notice.id)).all()}
    orgs = pool["orgs"]
    staff_people: list[dict[str, Any]] = []
    partner_people: list[dict[str, Any]] = []
    for user in recipients(db, notice, pool):
        ack = acks.get(int(user.id))
        entry = {
            "user_id": int(user.id),
            "name": user.name or user.username,
            "acked_at": _kst(ack.ack_at) if ack is not None else "",
            "read_at": _kst(ack.read_at) if ack is not None else "",
        }
        if user.partner_org_id is None:
            entry["team_label"] = notice_team_label(user.team)
            staff_people.append(entry)
        else:
            org = orgs.get(int(user.partner_org_id))
            entry["org_name"] = org.name if org is not None else ""
            partner_people.append(entry)
    staff = _group(staff_people)
    partner = _group(partner_people)
    return {
        "notice": {
            "id": int(notice.id),
            "title": notice.title or "",
            "audience_label": audience_label(notice, _org_name_map(db)),
            "display_mode": notice.display_mode,
        },
        "total": staff["total"] + partner["total"],
        "acked": staff["acked"] + partner["acked"],
        "staff": staff,
        "partner": partner,
    }


def audience_options(db) -> dict[str, Any]:
    """받는 사람 고르기 칩과 사람 수(쓰기 화면의 실시간 수).

    Returns:
        ``{teams: [{code, label}], partners: [{id, name}], counts: {staff_all, by_team: {code: n},
        partner_all, by_org: {id: n}}}`` — 켜진 계정 · 켜진 협력사만 센다. ``by_org`` 키는 글자 id.
    """
    pool = audience_pool(db)
    team_counts = Counter(normalize_team(u.team) for u in pool["staff"])
    org_counts = Counter(int(u.partner_org_id) for u in pool["partner"])
    partners = sorted(pool["orgs"].values(), key=lambda o: (o.name or "", int(o.id)))
    return {
        "teams": [{"code": code, "label": notice_team_label(code)} for code in NOTICE_TEAM_CODES],
        "partners": [{"id": int(o.id), "name": o.name} for o in partners],
        "counts": {
            "staff_all": len(pool["staff"]),
            "by_team": {code: int(team_counts.get(code, 0)) for code in NOTICE_TEAM_CODES},
            "partner_all": len(pool["partner"]),
            "by_org": {str(int(o.id)): int(org_counts.get(int(o.id), 0)) for o in partners},
        },
    }

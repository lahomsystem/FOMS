"""공지 받는 사람 판정 — 설계서 2026-11-02-foms-notices §2(한 곳).

* 본사 직원 = ``partner_org_id`` 없음 · 켜진 계정. ``audience_staff_all`` 이면 모두, 아니면 ``normalize_team(team)`` 이
  ``audience_staff_teams`` 안.
* 협력사 직원 = ``partner_org_id`` 있음 · 켜진 계정 · 켜진 협력사. ``audience_partner_all`` 이면 모두, 아니면 회사 id 가
  ``audience_partner_org_ids`` 안.
* 게시 중 = 지우지 않음 · (시작 없거나 ≤ 지금) · (끝 없거나 > 지금).

받는 사람을 미리 펼치지 않고 **볼 때** 판정한다 — 공지를 쓴 뒤에 생긴 계정도 받는다.
"""
from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.order_mutation_policy import normalize_team
from foms.services.orders.team_labels import TEAM_LABELS
from models import Notice, PartnerOrg, User

__all__ = [
    "NOTICE_TEAM_CODES",
    "audience_label",
    "audience_pool",
    "is_live",
    "notice_org_ids",
    "notice_team_codes",
    "notice_team_label",
    "recipients",
    "user_matches",
]

#: 공지를 고를 수 있는 본사 팀(정규화 값 — 실측팀 MEASURE 는 영업팀 SALES 로 묶인다).
NOTICE_TEAM_CODES: tuple[str, ...] = (
    "CS", "SALES", "DRAWING", "PRODUCTION", "CONSTRUCTION", "SHIPMENT", "ACCOUNTING",
)
# 팀 라벨 정본(``TEAM_LABELS``)에 없는 팀(2026-09-02 신설 회계팀)만 여기서 채운다.
_EXTRA_TEAM_LABELS = {"ACCOUNTING": "회계팀"}
_NO_TEAM_LABEL = "팀 없음"


def notice_team_label(code: Any) -> str:
    """팀 코드 → 화면 팀 이름(예 ``SALES`` → ``영업팀``). 비면 ``팀 없음``."""
    key = normalize_team(code)
    if not key:
        return _NO_TEAM_LABEL
    return TEAM_LABELS.get(key) or _EXTRA_TEAM_LABELS.get(key) or key


def _short_team(code: str) -> str:
    """받는 쪽 이름에 쓰는 짧은 팀 이름(``영업팀`` → ``영업``)."""
    label = notice_team_label(code)
    return label[:-1] if label.endswith("팀") and len(label) > 1 else label


def notice_team_codes(notice: Any) -> list[str]:
    """공지의 본사 팀 코드(정규화 · 중복 없음 · 순서 유지)."""
    out: list[str] = []
    for raw in getattr(notice, "audience_staff_teams", None) or []:
        code = normalize_team(raw)
        if code and code not in out:
            out.append(code)
    return out


def notice_org_ids(notice: Any) -> list[int]:
    """공지의 협력사 id(정수 · 중복 없음 · 순서 유지). 숫자가 아닌 값은 버린다."""
    out: list[int] = []
    for raw in getattr(notice, "audience_partner_org_ids", None) or []:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value not in out:
            out.append(value)
    return out


def is_live(notice: Any, now: Optional[datetime.datetime] = None) -> bool:
    """게시 중인가(지우지 않음 · 시작 지남 · 끝 안 지남). ``now`` 는 UTC naive."""
    if notice is None or getattr(notice, "deleted_at", None) is not None:
        return False
    now = now or now_utc_naive()
    starts_at = getattr(notice, "starts_at", None)
    ends_at = getattr(notice, "ends_at", None)
    if starts_at is not None and starts_at > now:
        return False
    if ends_at is not None and ends_at <= now:
        return False
    return True


def _account_on(user: Any) -> bool:
    """켜진 계정인가(꺼진 계정 · 가입 승인 대기는 받지 않는다)."""
    if user is None or getattr(user, "is_active", None) is False:
        return False
    status = getattr(user, "approval_status", None)
    return status in (None, "", "ACTIVE")


def user_matches(notice: Any, user: Any, org_active: bool) -> bool:
    """이 사람이 이 공지를 받는가(게시 기간은 보지 않는다 — :func:`is_live` 가 따로 본다).

    Args:
        notice: :class:`models.Notice`.
        user: :class:`models.User`.
        org_active: 협력사 직원이면 그 협력사가 켜져 있는가(본사 직원은 무시).
    """
    if notice is None or not _account_on(user):
        return False
    org_id = getattr(user, "partner_org_id", None)
    if org_id is None:
        if bool(getattr(notice, "audience_staff_all", False)):
            return True
        return normalize_team(getattr(user, "team", None)) in set(notice_team_codes(notice))
    if not org_active:
        return False
    if bool(getattr(notice, "audience_partner_all", False)):
        return True
    return int(org_id) in set(notice_org_ids(notice))


def audience_pool(db) -> dict[str, Any]:
    """받을 수 있는 사람 전부(한 번에 읽어 여러 공지에 쓴다).

    Returns:
        ``{"staff": [User], "partner": [User], "orgs": {id: PartnerOrg}}`` — 켜진 본사 직원 · 켜진 협력사의 켜진 직원 ·
        켜진 협력사. 정렬은 이름 → id.
    """
    orgs = {int(o.id): o for o in db.query(PartnerOrg).filter(PartnerOrg.is_active.is_(True)).all()}
    users = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.name, User.id)
        .all()
    )
    staff = [u for u in users if u.partner_org_id is None and _account_on(u)]
    partner = [u for u in users if u.partner_org_id is not None and int(u.partner_org_id) in orgs and _account_on(u)]
    return {"staff": staff, "partner": partner, "orgs": orgs}


def recipients(db, notice: Any, pool: Optional[dict[str, Any]] = None) -> list[User]:
    """지금 이 공지를 받는 사람(본사 먼저, 그다음 협력사). ``pool`` 을 주면 다시 읽지 않는다."""
    pool = pool or audience_pool(db)
    staff = [u for u in pool["staff"] if user_matches(notice, u, True)]
    partner = [u for u in pool["partner"] if user_matches(notice, u, True)]
    return staff + partner


def _org_names(db, org_ids: Iterable[int]) -> dict[int, str]:
    ids = list(org_ids)
    if not ids:
        return {}
    return {int(o.id): o.name for o in db.query(PartnerOrg).filter(PartnerOrg.id.in_(ids)).all()}


def audience_label(notice: Any, org_names: Optional[dict[int, str]] = None) -> str:
    """받는 쪽 이름 — "본사 전체" · "본사: 영업 · 도면" · "협력사 전체" · "협력사: 라운즈", 둘이면 " + " 로 잇는다.

    Args:
        notice: :class:`models.Notice`.
        org_names: 협력사 id → 이름(없으면 세션에서 읽는다 — 세션이 없으면 ``협력사 #id``).
    """
    parts: list[str] = []
    if bool(getattr(notice, "audience_staff_all", False)):
        parts.append("본사 전체")
    else:
        teams = notice_team_codes(notice)
        if teams:
            parts.append("본사: " + " · ".join(_short_team(t) for t in teams))
    if bool(getattr(notice, "audience_partner_all", False)):
        parts.append("협력사 전체")
    else:
        ids = notice_org_ids(notice)
        if ids:
            if org_names is None:
                org_names = _names_from_session(notice, ids)
            parts.append("협력사: " + " · ".join(org_names.get(i) or f"협력사 #{i}" for i in ids))
    return " + ".join(parts) if parts else "받는 사람 없음"


def _names_from_session(notice: Any, ids: list[int]) -> dict[int, str]:
    from sqlalchemy.orm import object_session

    session = object_session(notice) if isinstance(notice, Notice) else None
    if session is None:
        return {}
    return _org_names(session, ids)

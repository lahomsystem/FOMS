"""PARTNER-02: 협력사 · 협력사 계정 관리(ADMIN 화면이 부른다).

계정은 우리 관리자만 만든다. 협력사 계정은 ``role='PARTNER'`` + ``partner_org_id`` 짝이며
(DB 제약 ``ck_users_partner_role_org``), 일반 사용자 관리 화면(``/admin/users``)에서는 만들거나
고칠 수 없다.
"""
from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import func

from foms.services.notifications.recipients import expand_team_codes
from foms.services.orders.order_mutation_policy import normalize_team
from foms.services.security.password_policy import WeakPasswordError, set_strong_password
from models import PARTNER_ROLE, Order, PartnerOrg, User


class PartnerAdminError(ValueError):
    """관리 화면에 그대로 보여 줄 수 있는 입력 오류."""


def _clean(value: Any, *, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _validate_owner(db, owner_user_id: Any) -> int:
    """우리 쪽 담당 직원: 활성 · 영업팀 · 협력사 계정 아님."""
    try:
        owner_id = int(owner_user_id)
    except (TypeError, ValueError):
        raise PartnerAdminError("우리 쪽 담당 직원을 골라 주세요.")
    owner = db.query(User).filter(User.id == owner_id).first()
    if (
        owner is None
        or not owner.is_active
        or owner.partner_org_id is not None
        or normalize_team(owner.team) != "SALES"
    ):
        raise PartnerAdminError("담당 직원은 활성 영업팀 직원이어야 합니다.")
    return owner_id


def create_partner_org(db, *, name: Any, owner_user_id: Any, biz_reg_no: Any = None,
                       contact_name: Any = None, contact_phone: Any = None) -> PartnerOrg:
    """협력사를 만든다(호출자가 commit)."""
    clean_name = _clean(name, limit=100)
    if not clean_name:
        raise PartnerAdminError("협력사 이름을 넣어 주세요.")
    if db.query(PartnerOrg.id).filter(PartnerOrg.name == clean_name).first():
        raise PartnerAdminError("같은 이름의 협력사가 이미 있습니다.")
    org = PartnerOrg(
        name=clean_name,
        owner_user_id=_validate_owner(db, owner_user_id),
        biz_reg_no=_clean(biz_reg_no, limit=20) or None,
        contact_name=_clean(contact_name, limit=100) or None,
        contact_phone=_clean(contact_phone, limit=30) or None,
    )
    db.add(org)
    db.flush()
    return org


def update_partner_owner(db, org: PartnerOrg, owner_user_id: Any) -> None:
    """우리 쪽 담당 직원을 바꾼다. 이미 등록된 주문의 담당은 그대로 둔다."""
    org.owner_user_id = _validate_owner(db, owner_user_id)


def create_partner_user(db, org: PartnerOrg, *, username: Any, name: Any, password: Any) -> User:
    """협력사 계정을 만든다. 비밀번호는 강도 정책을 거친다(호출자가 commit)."""
    clean_username = _clean(username, limit=64)
    clean_name = _clean(name, limit=50) or org.name
    if not clean_username:
        raise PartnerAdminError("아이디를 넣어 주세요.")
    if db.query(User.id).filter(User.username == clean_username).first():
        raise PartnerAdminError("이미 사용 중인 아이디입니다.")
    user = User(
        username=clean_username,
        name=clean_name,
        role=PARTNER_ROLE,
        team=None,
        is_active=True,
        partner_org_id=org.id,
    )
    try:
        set_strong_password(user, password)
    except WeakPasswordError as exc:
        raise PartnerAdminError(str(exc)) from exc
    db.add(user)
    db.flush()
    return user


def get_partner_user(db, user_id: Any) -> User | None:
    """협력사 계정만 돌려준다(우리 직원 id 면 None)."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    return (
        db.query(User)
        .filter(User.id == uid, User.partner_org_id.isnot(None))
        .first()
    )


def reset_partner_user_password(user: User, password: Any) -> None:
    try:
        set_strong_password(user, password)
    except WeakPasswordError as exc:
        raise PartnerAdminError(str(exc)) from exc


def list_partner_orgs_with_users(db) -> list[dict[str, Any]]:
    """관리 화면용: 협력사 + 소속 계정 + 담당 직원 이름 + 주문 수(쿼리 4번, N+1 없음)."""
    orgs = db.query(PartnerOrg).order_by(PartnerOrg.name).all()
    if not orgs:
        return []
    org_ids = [o.id for o in orgs]
    users = (
        db.query(User)
        .filter(User.partner_org_id.in_(org_ids))  # perf-ok: 협력사 수만큼의 작은 id 목록
        .order_by(User.username)
        .all()
    )
    owner_ids = {o.owner_user_id for o in orgs if o.owner_user_id}
    owner_names = (
        dict(db.query(User.id, User.name).filter(User.id.in_(owner_ids)).all())  # perf-ok: 협력사 수 이하
        if owner_ids else {}
    )
    order_counts = dict(
        db.query(Order.partner_org_id, func.count(Order.id))
        .filter(Order.partner_org_id.in_(org_ids))  # perf-ok: 부분 색인 ix_orders_partner_org_id
        .group_by(Order.partner_org_id)
        .all()
    )
    by_org: dict[int, list[User]] = {}
    for u in users:
        by_org.setdefault(u.partner_org_id, []).append(u)
    return [
        {
            "org": o,
            "users": by_org.get(o.id, []),
            "owner_name": owner_names.get(o.owner_user_id),
            "order_count": int(order_counts.get(o.id, 0)),
        }
        for o in orgs
    ]


def sales_owner_choices(db) -> list[User]:
    """담당 직원 선택지: 활성 영업팀(MEASURE 표기 포함) 우리 직원."""
    return (
        db.query(User)
        .filter(
            User.is_active.is_(True),
            User.partner_org_id.is_(None),
            func.upper(User.team).in_(expand_team_codes("SALES")),
        )
        .order_by(User.name)
        .all()
    )


def load_partner_org_names(db, orders: Iterable[Any]) -> dict[int, str]:
    """화면 표식용 ``{partner_org_id: 이름}`` — 협력사 주문이 없으면 쿼리하지 않는다."""
    ids = {getattr(o, "partner_org_id", None) for o in orders}
    ids.discard(None)
    if not ids:
        return {}
    return dict(
        db.query(PartnerOrg.id, PartnerOrg.name).filter(PartnerOrg.id.in_(ids)).all()  # perf-ok: 페이지 안 협력사 id
    )

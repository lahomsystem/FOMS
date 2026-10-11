"""PARTNER-02: 협력사 · 협력사 계정 관리(ADMIN 화면이 부른다).

계정은 우리 관리자만 만든다. 협력사 계정은 ``role='PARTNER'`` + ``partner_org_id`` 짝이며
(DB 제약 ``ck_users_partner_role_org``), 일반 사용자 관리 화면(``/admin/users``)에서는 만들거나
고칠 수 없다.
"""
from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import func

from foms.services.partners.manager import PartnerManagerError, clean_contact_phone, set_partner_user_phone
from foms.services.security.password_policy import WeakPasswordError, set_strong_password
from models import PARTNER_ROLE, Order, PartnerOrg, User


class PartnerAdminError(ValueError):
    """관리 화면에 그대로 보여 줄 수 있는 입력 오류."""


def _clean(value: Any, *, limit: int) -> str:
    return str(value or "").strip()[:limit]


def create_partner_org(db, *, name: Any, biz_reg_no: Any = None,
                       contact_name: Any = None, contact_phone: Any = None) -> PartnerOrg:
    """협력사를 만든다(호출자가 commit)."""
    clean_name = _clean(name, limit=100)
    if not clean_name:
        raise PartnerAdminError("협력사 이름을 넣어 주세요.")
    if db.query(PartnerOrg.id).filter(PartnerOrg.name == clean_name).first():
        raise PartnerAdminError("같은 이름의 협력사가 이미 있습니다.")
    org = PartnerOrg(
        name=clean_name,
        biz_reg_no=_clean(biz_reg_no, limit=20) or None,
        contact_name=_clean(contact_name, limit=100) or None,
        contact_phone=_clean(contact_phone, limit=30) or None,
    )
    db.add(org)
    db.flush()
    return org


def create_partner_user(db, org: PartnerOrg, *, username: Any, name: Any, password: Any,
                        contact_phone: Any) -> User:
    """협력사 계정을 만든다. 비밀번호는 강도 정책을 거친다(호출자가 commit).

    연락처는 필수다 — 이 직원이 담당인 주문의 도면 "담당 연락처"에 찍힌다(스펙 §16).
    """
    clean_username = _clean(username, limit=64)
    clean_name = _clean(name, limit=50) or org.name
    if not clean_username:
        raise PartnerAdminError("아이디를 넣어 주세요.")
    try:
        phone = clean_contact_phone(contact_phone)
    except PartnerManagerError as exc:
        raise PartnerAdminError(str(exc)) from exc
    if db.query(User.id).filter(User.username == clean_username).first():
        raise PartnerAdminError("이미 사용 중인 아이디입니다.")
    user = User(
        username=clean_username,
        name=clean_name,
        role=PARTNER_ROLE,
        team=None,
        is_active=True,
        partner_org_id=org.id,
        contact_phone=phone,
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


def update_partner_user_phone(db, user: User, phone: Any, *, actor_user_id: int) -> int:
    """관리 화면에서 협력사 직원 연락처를 바꾼다 — 진행 중 담당 주문도 같이 바뀐다(고친 주문 수)."""
    try:
        return set_partner_user_phone(db, user, phone, actor_user_id=actor_user_id)
    except PartnerManagerError as exc:
        raise PartnerAdminError(str(exc)) from exc


def reset_partner_user_password(user: User, password: Any) -> None:
    try:
        set_strong_password(user, password)
    except WeakPasswordError as exc:
        raise PartnerAdminError(str(exc)) from exc


def list_partner_orgs_with_users(db) -> list[dict[str, Any]]:
    """관리 화면용: 협력사 + 소속 계정 + 주문 수(쿼리 3번, N+1 없음)."""
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
    order_counts = dict(
        db.query(Order.partner_org_id, func.count(Order.id))
        # 지운 주문 · 초안은 세지 않는다(운영 화면과 같은 기준).
        .filter(Order.partner_org_id.in_(org_ids), Order.active_filter())  # perf-ok: 부분 색인 ix_orders_partner_org_id
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
            "order_count": int(order_counts.get(o.id, 0)),
        }
        for o in orgs
    ]


def load_partner_org_names(db, orders: Iterable[Any]) -> dict[int, str]:
    """화면 표식용 ``{partner_org_id: 이름}`` — 협력사 주문이 없으면 쿼리하지 않는다."""
    ids = {getattr(o, "partner_org_id", None) for o in orders}
    ids.discard(None)
    if not ids:
        return {}
    return dict(
        db.query(PartnerOrg.id, PartnerOrg.name).filter(PartnerOrg.id.in_(ids)).all()  # perf-ok: 페이지 안 협력사 id
    )

"""PARTNER-04: 협력사 주문의 담당 = 협력사 직원 · 담당 연락처.

사용자 결정(2026-10-11, 스펙 §16):

* 협력사 주문의 담당은 **주문을 올린 협력사 직원**이다. 같은 회사 직원끼리 바꿀 수 있다.
* 우리 쪽은 CS 팀이 챙긴다(영업 쪽 권한 · 알림은 CS — ``erp_policy_permissions`` · 도면 알림 대상).
* 담당 이름은 ``이름 (회사명)`` 으로 남긴다. 이 시스템은 담당 이름 문자열로 사용자를 맞춰 보는 곳이
  많아서(알림 · "내 주문" · 첨부 권한), 우리 직원과 이름이 같으면 그 직원에게 넘어간다. 꼬리를 붙이면
  어떤 내부 계정 이름과도 맞지 않는다.
* 담당 연락처(``users.contact_phone``)는 ``parties.manager.phone`` 에 적는다 — 도면 마법사가 이 칸을
  맨 먼저 읽는다. 도면에는 꼬리 없는 이름(``partner_user_name``)을 찍는다.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from foms.services.audit_writer import normalize_security_detail
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.assignment import replace_sales_owner_in_tx
from foms.services.orders.revision import execute_single_order_write, lock_order_row
from models import Order, OrderAssignment, PartnerOrg, SecurityLog, User

# 담당 바꾸기 쓰기 정책 id(직원 담당 지정과 같은 원장 이름).
MANAGER_CHANGE_POLICY_ID = "SET_SALES_ASSIGNEE"
# 번호가 바뀌어도 그대로 두는 단계(이미 끝난 주문 — ``Order.dashboard_active_filter`` 의 완료 집합과 같은 뜻).
_CLOSED_STAGES = frozenset({"COMPLETED", "AS_COMPLETED"})
_PHONE_DIGITS_MIN = 9
_PHONE_DIGITS_MAX = 12


class PartnerManagerError(ValueError):
    """화면에 그대로 보여 줄 수 있는 거부 사유. ``status`` 는 HTTP 코드."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def clean_contact_phone(value: Any) -> str:
    """연락처를 ``010-1234-5678`` 꼴로 다듬는다. 숫자가 9~12자가 아니면 :class:`PartnerManagerError`."""
    digits = re.sub(r"\D", "", str(value or ""))
    if not (_PHONE_DIGITS_MIN <= len(digits) <= _PHONE_DIGITS_MAX):
        raise PartnerManagerError("연락처를 숫자로 정확히 넣어 주세요(예: 010-1234-5678).")
    if len(digits) == 11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    if len(digits) == 10:
        head = 2 if digits.startswith("02") else 3
        return f"{digits[:head]}-{digits[head:-4]}-{digits[-4:]}"
    return digits


def manager_party(user: User, org: PartnerOrg) -> dict[str, Any]:
    """``parties.manager`` 값 — 표시 이름 · 연락처 · 도면용 이름 · 협력사 직원 id."""
    party: dict[str, Any] = {
        "name": f"{user.name} ({org.name})",
        "partner_user_id": user.id,
        "partner_user_name": user.name,
    }
    if user.contact_phone:
        party["phone"] = user.contact_phone
    return party


def org_member_choices(db, org_id: int) -> list[User]:
    """담당으로 고를 수 있는 같은 회사 활성 직원."""
    return (
        db.query(User)
        .filter(User.partner_org_id == org_id, User.is_active.is_(True))
        .order_by(User.name)
        .all()
    )


def _apply_manager(sd: dict[str, Any], old_user_id: int | None, user: User, org: PartnerOrg) -> None:
    """sd 의 담당 칸과 담당이던 사람의 quest ``owner_person`` 을 새 담당으로 바꾼다(in-place)."""
    parties = sd.setdefault("parties", {})
    parties["manager"] = manager_party(user, org)
    old_key = str(old_user_id) if old_user_id else None
    for quest in sd.get("quests") or []:
        if isinstance(quest, dict) and old_key and str(quest.get("owner_person") or "") == old_key:
            quest["owner_person"] = str(user.id)
    current = (sd.get("workflow") or {}).get("current_quest")
    if isinstance(current, dict) and old_key and str(current.get("owner_person") or "") == old_key:
        current["owner_person"] = str(user.id)


def change_partner_order_manager(db, actor: User, order_id: int, new_user_id: Any) -> Order:
    """협력사 주문 담당을 같은 회사 다른 직원으로 바꾼다(호출자가 commit).

    Raises:
        PartnerManagerError: 주문 없음(404) · 같은 회사 활성 직원 아님(400).
    """
    order = lock_order_row(db, order_id)
    if order is None or order.deleted_at is not None or order.partner_org_id != actor.partner_org_id:
        raise PartnerManagerError("주문을 찾을 수 없습니다.", 404)
    try:
        target_id = int(new_user_id)
    except (TypeError, ValueError):
        raise PartnerManagerError("담당을 골라 주세요.")
    target = db.query(User).filter(User.id == target_id).first()
    if target is None or not target.is_active or target.partner_org_id != order.partner_org_id:
        raise PartnerManagerError("같은 회사의 사용 중인 직원만 담당이 될 수 있습니다.")
    org = db.query(PartnerOrg).filter(PartnerOrg.id == order.partner_org_id).first()
    old_user_id = reassign_partner_order(db, order, target, org, actor_user_id=actor.id,
                                         reason=f"협력사 담당 변경 ({actor.name})")
    if old_user_id != target.id:
        db.add(SecurityLog(
            user_id=actor.id,
            message=f"협력사 주문 담당 변경: #{order.id}",
            action="PARTNER_ORDER_MANAGER_CHANGED",
            target_type="order",
            target_id=order.id,
            detail=normalize_security_detail({
                "partner_org_id": order.partner_org_id, "from_user_id": old_user_id, "to_user_id": target.id,
            }),
        ))
    return order


def reassign_partner_order(db, order: Order, target: User, org: PartnerOrg, *,
                           actor_user_id: int, reason: str) -> int | None:
    """잠근 협력사 주문의 담당을 ``target`` 으로 바꾼다(SALES 배정 · 담당 칸 · quest owner · manager_name).

    이미 ``target`` 이 담당이고 담당 칸도 맞으면 아무것도 쓰지 않는다. 호출자가 행을 잠그고 commit 한다.

    Returns:
        바꾸기 전 SALES owner user id(없으면 ``None``).
    """
    old_row = (
        db.query(OrderAssignment)
        .filter(OrderAssignment.order_id == order.id, OrderAssignment.domain == "SALES",
                OrderAssignment.active.is_(True))
        .first()
    )
    old_user_id = old_row.user_id if old_row is not None else None
    party = manager_party(target, org)
    current = ((order.structured_data or {}).get("parties") or {}).get("manager")
    if old_user_id == target.id and current == party:
        return old_user_id
    sd = copy.deepcopy(order.structured_data or {})
    _apply_manager(sd, old_user_id, target, org)

    def _write(locked):
        locked.structured_data = sd
        flag_modified(locked, "structured_data")
        sync_erp_flat_columns(locked, sd)  # orders.manager_name(목록 · 검색) 맞추기

    execute_single_order_write(
        db, order_id=order.id, actor_user_id=actor_user_id, policy_id=MANAGER_CHANGE_POLICY_ID,
        payload={"user_id": target.id, "source": "partner"}, write=_write,
    )
    if old_user_id != target.id:
        replace_sales_owner_in_tx(db, order_id=order.id, user_id=target.id, actor_user_id=actor_user_id,
                                  reason=reason)
    return old_user_id


def set_partner_user_phone(db, user: User, phone: Any, *, actor_user_id: int) -> int:
    """협력사 직원 연락처를 바꾸고, 그 직원이 담당인 진행 중 주문의 담당 연락처도 바꾼다(호출자가 commit).

    끝난 주문(완료 · AS 완료)은 그대로 둔다 — 그때 보낸 도면과 같은 번호가 남는다.

    Returns:
        담당 연락처를 고친 주문 수.
    """
    user.contact_phone = clean_contact_phone(phone)
    order_ids = [
        oid for (oid,) in (
            db.query(Order.id)
            .join(OrderAssignment, OrderAssignment.order_id == Order.id)
            .filter(
                OrderAssignment.domain == "SALES",
                OrderAssignment.active.is_(True),
                OrderAssignment.user_id == user.id,
                Order.partner_org_id == user.partner_org_id,
                Order.deleted_at.is_(None),
            )
            .all()
        )
    ]
    changed = 0
    for order_id in order_ids:
        order = lock_order_row(db, order_id)
        if order is None or (order.erp_stage_code or "").upper() in _CLOSED_STAGES:
            continue
        sd = copy.deepcopy(order.structured_data or {})
        manager = (sd.get("parties") or {}).get("manager")
        if not isinstance(manager, dict) or manager.get("phone") == user.contact_phone:
            continue
        manager["phone"] = user.contact_phone

        def _write(locked, sd=sd):
            locked.structured_data = sd
            flag_modified(locked, "structured_data")

        execute_single_order_write(
            db, order_id=order.id, actor_user_id=actor_user_id, policy_id=MANAGER_CHANGE_POLICY_ID,
            payload={"manager_phone": user.contact_phone, "source": "partner_phone"}, write=_write,
        )
        changed += 1
    return changed

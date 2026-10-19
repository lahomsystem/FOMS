"""PARTNER-FOMS 3-1: 접수 확인 중 협력사 품목 고치기.

협력사가 보낸 주문을 우리 CS 가 아직 확인하는 동안(RECEIVED · MEASURE)만 협력사가 품목을 다시 고친다.
그 뒤에는 바꿀 것을 수정 요청으로 보낸다. 스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §4-4 · §5-4 · §12.

* 협력사가 고칠 수 있는 키(:data:`PARTNER_ITEM_KEYS`)만 바꾼다. 나머지 품목 키(금액 · 품목 일정 · 취소 표시 등
  우리 직원이 넣은 값)는 품목 uid 로 짝지어 그대로 둔다.
* 원문 사본(``partner_intake.items``)도 같이 바꾸고, ``partner_intake.item_edits`` 에 누가 · 언제 · 바꾸기 전
  품목을 남긴다(사용자 결정 §5-4).
* 품목에 묶인 첨부(``item_index`` · ``item_id``)는 uid 로 새 자리를 찾는다. 지운 품목의 사진은 공통 사진이 된다.
"""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from foms.services.audit_writer import normalize_security_detail
from foms.services.auth.partner_scope import partner_can_read_order
from foms.services.datetime_kst import now_kst
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.orders.item_identity import get_or_create_identity
from foms.services.orders.revision import execute_single_order_write, lock_order_row
from foms.services.orders.structured_item_uid import ensure_item_uids, item_uid_of
from foms.services.partners.orders import ATTRIBUTE_KEYS, PartnerOrderError, clean_partner_items
from models import Notification, OrderAttachment, SecurityLog

ITEMS_EDIT_POLICY_ID = "PARTNER_ITEMS_EDIT"
ITEMS_EDIT_STAGES = frozenset({"RECEIVED", "MEASURE"})
MAX_EDIT_HISTORY = 20
# 협력사 화면이 고치는 품목 키. 우리 저장이 규격 첫 줄로 함께 쓰는 옛 칸(spec_width 등)은 아래에서 다시 맞춘다.
PARTNER_ITEM_KEYS = ("product_name", "spec_rows", "quantity", *ATTRIBUTE_KEYS, "extra_input")
_LEGACY_SPEC_KEYS = ("spec_width", "spec_depth", "spec_height")


class PartnerItemsError(PartnerOrderError):
    """화면에 그대로 보여 줄 수 있는 거부 사유. ``status`` 는 HTTP 코드."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _merge_item(old: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
    """옛 품목의 우리 쪽 키는 두고, 협력사 키만 새 값으로(빈 속성은 지운다)."""
    merged = copy.deepcopy(old) if old else {}
    for key in PARTNER_ITEM_KEYS:
        merged.pop(key, None)
    merged.update(new)
    if any(key in merged for key in (*_LEGACY_SPEC_KEYS, "spec")):
        first = merged["spec_rows"][0]
        for key in _LEGACY_SPEC_KEYS:
            merged[key] = first.get(key, "")
        lines = ["x".join(v for v in (r.get(k, "") for k in _LEGACY_SPEC_KEYS) if v) for r in merged["spec_rows"]]
        merged["spec"] = ", ".join(line for line in lines if line)
    return merged


def _intake_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """원문 사본 모양 — 협력사 키만, uid 없음(등록 때 사본과 같은 모양)."""
    return [{k: copy.deepcopy(it[k]) for k in PARTNER_ITEM_KEYS if k in it} for it in items]


def _record_intake(sd: dict[str, Any], user: Any) -> dict[str, Any]:
    """원문 사본을 새 품목으로 바꾸고 바꾸기 전 품목을 기록에 남긴다(in-place, 최근 20번)."""
    intake = sd.setdefault("partner_intake", {})
    history = list(intake.get("item_edits") or [])
    history.append({"at": now_kst().isoformat(), "by_user_id": user.id, "by_name": user.name,
                    "before": copy.deepcopy(intake.get("items") or [])})
    intake["item_edits"] = history[-MAX_EDIT_HISTORY:]
    intake["items"] = _intake_items(sd["items"])
    return intake


def _remap_item_attachments(db, order_id: int, old_items: list, new_items: list) -> int:
    """품목에 묶인 첨부를 uid 로 새 자리에 옮긴다. 옮긴(또는 공통이 된) 첨부 수를 돌려준다."""
    new_index = {item_uid_of(it): i for i, it in enumerate(new_items) if item_uid_of(it)}
    slot_ids = {i: get_or_create_identity(db, order_id, i).id for i in range(len(new_items))}
    moved = 0
    rows = db.query(OrderAttachment).filter(OrderAttachment.order_id == order_id,
                                            OrderAttachment.item_index.isnot(None)).all()
    for att in rows:
        old_i = att.item_index
        uid = item_uid_of(old_items[old_i]) if 0 <= old_i < len(old_items) else None
        target = new_index.get(uid) if uid else (old_i if old_i < len(new_items) else None)
        target_id = slot_ids.get(target) if target is not None else None
        if (target, target_id) != (att.item_index, att.item_id):
            att.item_index, att.item_id = target, target_id
            moved += 1
    return moved


def _notify_cs(db, user: Any, order_id: int, customer: str, count: int) -> None:
    notification = Notification(
        order_id=order_id,
        notification_type="PARTNER_ORDER_ITEMS_EDITED",
        target_team="CS",
        title="협력사 품목 고침",
        message=f"[협력사] 주문 #{order_id}" + (f" ({customer})" if customer else "")
        + f" 품목을 고쳤습니다(지금 {count}개). 확인해 주세요.",
        created_by_user_id=user.id,
        created_by_name=f"{user.name} (협력사)",
    )
    db.add(notification)
    db.flush()
    fan_out_new_notification(db, notification, actor_user_id=user.id)


def update_partner_items(db, user: Any, order_id: int, payload: Any) -> list[dict[str, Any]]:
    """협력사 품목을 고친다(호출자가 commit). 저장된 품목(uid 포함)을 돌려준다.

    Raises:
        PartnerItemsError: 주문 없음(404) · 접수 확인이 끝남(409) · 품목 없음(400).
    """
    order = lock_order_row(db, order_id)
    if order is None or order.deleted_at is not None or not partner_can_read_order(user, order):
        raise PartnerItemsError("주문을 찾을 수 없습니다.", 404)
    if (order.erp_stage_code or "").upper() not in ITEMS_EDIT_STAGES:
        raise PartnerItemsError("도면 작업이 시작되어 품목을 고칠 수 없습니다. 바꿀 곳은 수정 요청으로 보내 주세요.", 409)
    data = payload if isinstance(payload, dict) else {}
    try:
        cleaned = clean_partner_items(data.get("items"), keep_uid=True)
    except PartnerOrderError as exc:
        raise PartnerItemsError(str(exc)) from exc

    old_sd = order.structured_data or {}
    old_items = [it for it in (old_sd.get("items") or []) if isinstance(it, dict)]
    sd = copy.deepcopy(old_sd)
    sd["items"] = cleaned
    ensure_item_uids(old_sd, sd)  # 이 주문에 있던 uid 만 인정, 나머지는 새로 발급
    by_uid = {item_uid_of(it): it for it in old_items if item_uid_of(it)}
    sd["items"] = [_merge_item(by_uid.get(item_uid_of(it)), it) for it in cleaned]

    intake = _record_intake(sd, user)

    def _write(locked):
        locked.structured_data = sd
        flag_modified(locked, "structured_data")
        locked.product = sd["items"][0]["product_name"]

    execute_single_order_write(db, order_id=order.id, actor_user_id=user.id, policy_id=ITEMS_EDIT_POLICY_ID,
                               payload={"items": intake["items"]}, write=_write)
    moved = _remap_item_attachments(db, order.id, old_items, sd["items"])
    db.add(SecurityLog(
        user_id=user.id,
        message=f"협력사 품목 고침: #{order.id}",
        action="PARTNER_ORDER_ITEMS_EDITED",
        target_type="order",
        target_id=order.id,
        detail=normalize_security_detail({"partner_org_id": order.partner_org_id, "before": len(old_items),
                                          "after": len(sd["items"]), "attachments_moved": moved}),
    ))
    customer = str(((sd.get("parties") or {}).get("customer") or {}).get("name") or "").strip()
    _notify_cs(db, user, order.id, customer, len(sd["items"]))
    return sd["items"]

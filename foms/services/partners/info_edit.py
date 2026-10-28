"""PARTNER-FOMS 18-1: 협력사 주문 정보 — 실측 시간 · 희망 시공일 · 보낸 뒤 고치기.

스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §18.

* 실측일 · 실측시간은 원문 사본(``partner_intake.measured_on`` · ``measured_time``)에만 둔다 — 우리 실측
  일정표에 협력사 실측이 섞이지 않게(등록 때와 같은 규칙).
* 희망 시공일은 ``partner_intake.requested_construction = {date, time}``. 우리 ``schedule.construction`` 은
  건드리지 않는다 — 확정은 출고 담당자가 협력사와 이야기한 뒤 우리 화면에서 한다. 넣거나 바꾸면 출고팀 알림.
* 보낸 뒤 고치기: 고객명 · 연락처 · 주소 · 실측일 · 실측시간은 접수 확인 중(RECEIVED · MEASURE)만,
  희망 시공일은 우리가 시공일을 정하기 전까지. 바꾸기 전 값을 ``partner_intake.info_edits`` 에(최근 20번).
"""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from foms.services.audit_writer import normalize_security_detail
from foms.services.auth.partner_scope import partner_can_read_order
from foms.services.datetime_kst import now_kst
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.order_geocode import reset_order_geocode_on_address_change
from foms.services.orders.revision import execute_single_order_write, lock_order_row
from foms.services.partners.items_edit import (
    EDIT_CLOSED_MESSAGE,
    MAX_EDIT_HISTORY,
    PartnerItemsError,
    partner_edit_open,
    partner_notice_team,
)
from foms.services.partners.schedule_request import (
    clean_date,
    clean_request,
    clean_time,
    request_open,
    notify_shipment_request,
)
from models import Notification, SecurityLog

INFO_EDIT_POLICY_ID = "PARTNER_INFO_EDIT"
# 접수 확인 중에만 고치는 칸(payload 키 → 원문 사본 자리는 아래 _apply_info).
INFO_KEYS = ("customer_name", "customer_phone", "address", "measured_on", "measured_time")
REQUEST_KEYS = ("requested_construction_date", "requested_construction_time")


def _notify_cs(db, user: Any, order_id: int, customer: str, team: str = "CS") -> None:
    notification = Notification(
        order_id=order_id,
        notification_type="PARTNER_ORDER_INFO_EDITED",
        target_team=team,
        title="협력사 주문 정보 고침",
        message=f"[협력사] 주문 #{order_id}" + (f" ({customer})" if customer else "")
        + " 고객 · 주소 · 실측 정보를 고쳤습니다. 확인해 주세요.",
        created_by_user_id=user.id,
        created_by_name=f"{user.name} (협력사)",
    )
    db.add(notification)
    db.flush()
    fan_out_new_notification(db, notification, actor_user_id=user.id)


def _apply_info(sd: dict[str, Any], intake: dict[str, Any], data: dict[str, Any]) -> dict[str, str]:
    name = str(data.get("customer_name") or "").strip()[:50]
    phone = str(data.get("customer_phone") or "").strip()[:30]
    address = str(data.get("address") or "").strip()[:300]
    if not name or not phone or not address:
        raise PartnerItemsError("고객 이름 · 연락처 · 현장 주소를 넣어 주세요.")
    customer = sd.setdefault("parties", {}).setdefault("customer", {})
    customer.update({"name": name, "phone": phone})
    sd.setdefault("site", {})["address_full"] = address
    intake["customer"] = {"name": name, "phone": phone}
    intake["address"] = address
    intake["measured_on"] = clean_date(data.get("measured_on")) or None
    intake["measured_time"] = clean_time(data.get("measured_time")) or None
    return {"name": name, "phone": phone, "address": address}


def update_partner_info(db, user: Any, order_id: int, payload: Any) -> dict[str, Any]:
    """협력사가 보낸 주문의 정보를 고친다(호출자가 commit).

    Returns:
        ``{"address_changed": bool, "request_changed": bool}`` — 라우트가 지도 좌표 다시 찾기 · 알림 배지에 쓴다.

    Raises:
        PartnerItemsError: 주문 없음(404) · 고칠 수 있는 때가 지남(409) · 빈 칸(400).
    """
    order = lock_order_row(db, order_id)
    if order is None or order.deleted_at is not None or not partner_can_read_order(user, order):
        raise PartnerItemsError("주문을 찾을 수 없습니다.", 404)
    data = payload if isinstance(payload, dict) else {}
    wants_info = any(k in data for k in INFO_KEYS)
    wants_request = any(k in data for k in REQUEST_KEYS)
    if not wants_info and not wants_request:
        raise PartnerItemsError("고칠 내용이 없습니다.")
    old_sd = order.structured_data or {}
    if wants_info and not partner_edit_open(order):
        raise PartnerItemsError(EDIT_CLOSED_MESSAGE, 409)
    if wants_request and not request_open(old_sd, order.erp_stage_code or ""):
        raise PartnerItemsError("시공일이 이미 정해졌습니다. 바꾸려면 저희 출고 담당자에게 알려 주세요.", 409)

    sd = copy.deepcopy(old_sd)
    intake = sd.setdefault("partner_intake", {})
    before = {k: copy.deepcopy(intake.get(k)) for k in
              ("customer", "address", "measured_on", "measured_time", "requested_construction")}
    info = _apply_info(sd, intake, data) if wants_info else None
    request_changed = False
    if wants_request:
        request = clean_request(data)
        request_changed = request != before["requested_construction"]
        intake["requested_construction"] = request
    history = list(intake.get("info_edits") or [])
    history.append({"at": now_kst().isoformat(), "by_user_id": user.id, "by_name": user.name, "before": before})
    intake["info_edits"] = history[-MAX_EDIT_HISTORY:]
    old_address = str(((old_sd.get("site") or {}) if isinstance(old_sd.get("site"), dict) else {}).get("address_full") or "")
    address_changed = bool(info) and info["address"] != old_address.strip()

    def _write(locked):
        locked.structured_data = sd
        flag_modified(locked, "structured_data")
        if info:
            locked.customer_name, locked.phone, locked.address = info["name"], info["phone"], info["address"]
            if address_changed:
                reset_order_geocode_on_address_change(locked, info["address"])

    execute_single_order_write(db, order_id=order.id, actor_user_id=user.id, policy_id=INFO_EDIT_POLICY_ID,
                               payload={k: data.get(k) for k in (*INFO_KEYS, *REQUEST_KEYS) if k in data},
                               write=_write)
    db.add(SecurityLog(
        user_id=user.id,
        message=f"협력사 주문 정보 고침: #{order.id}",
        action="PARTNER_ORDER_INFO_EDITED",
        target_type="order",
        target_id=order.id,
        detail=normalize_security_detail({"partner_org_id": order.partner_org_id, "info": bool(info),
                                          "address_changed": address_changed, "request_changed": request_changed}),
    ))
    customer = str(((sd.get("parties") or {}).get("customer") or {}).get("name") or "").strip()
    if info:
        _notify_cs(db, user, order.id, customer, partner_notice_team(order))
    if request_changed and intake.get("requested_construction"):
        notify_shipment_request(db, user, order.id, customer, intake["requested_construction"])
    return {"address_changed": address_changed, "request_changed": request_changed}

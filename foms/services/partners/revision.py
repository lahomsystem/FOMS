"""PARTNER-03: 협력사 "수정 요청" — 우리 최종 도면을 보고 고칠 곳을 도면팀에 보낸다.

효과는 직원 수정 요청(``foms/api/drawing/erp_orders_revision.py`` ``api_order_request_revision``)과
같다: ``drawing_status`` RETURNED · 이력 REQUEST_REVISION · 고객확인 무효화 · 같은 쓰기 정책
(DRAWING_REVISION_REQUEST) · 도면팀 알림(확인 창). 직원 라우트는 직원 팀·영업 담당을 요구해
협력사가 쓸 수 없다. 대상 도면은 고르지 않는다 — 현재 최종 도면 전부가 대상이다.

참고 사진은 API 가 ``orders/<id>/drawing_gateway/revisions/`` 에 올린 뒤 key 목록으로 넘긴다
(직원 수정 요청이 받는 경로와 같은 폴더 — ``is_revision_reference_key``).
스펙: docs/specs/2026-10-08-partner-portal_SPEC.md §14
"""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from foms.services.audit_writer import normalize_security_detail
from foms.services.auth.partner_scope import partner_can_read_order
from foms.services.datetime_kst import now_utc_naive
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.orders.drawing_gate_followups import invalidate_customer_confirmation
from foms.services.orders.drawing_revision_files import normalize_revision_files
from foms.services.orders.revision import execute_single_order_write, lock_order_row
from models import Notification, SecurityLog

# 직원 경로와 같은 쓰기 정책 id(``erp_orders_revision.DRAWING_REVISION_REQUEST_POLICY_ID``).
DRAWING_REVISION_REQUEST_POLICY_ID = "DRAWING_REVISION_REQUEST"
REVISION_FOLDER = "drawing_gateway/revisions"
MAX_NOTE = 2000


class PartnerRevisionError(ValueError):
    """협력사 화면에 그대로 보여 줄 수 있는 거부 사유. ``status`` 는 HTTP 코드."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def request_partner_revision(db, user: Any, order_id: int, note: Any, files: list[dict[str, Any]]) -> Notification:
    """수정 요청을 기록하고 도면팀 알림을 만든다(호출자가 commit 뒤 push·배지·실시간을 보낸다).

    Args:
        files: ``[{key, filename}]`` — 이미 ``orders/<id>/drawing_gateway/revisions/`` 에 올라간 사진.

    Raises:
        PartnerRevisionError: 주문 없음(404)·수정 요청할 수 없는 상태(409)·메모 없음(400).
    """
    text = str(note or "").strip()[:MAX_NOTE]
    if not text:
        raise PartnerRevisionError("고칠 내용을 적어 주세요.", 400)
    order = lock_order_row(db, order_id)
    if order is None or order.deleted_at is not None or not partner_can_read_order(user, order):
        raise PartnerRevisionError("주문을 찾을 수 없습니다.", 404)
    sd = copy.deepcopy(order.structured_data or {})
    if sd.get("drawing_status") not in ("TRANSFERRED", "CONFIRMED"):
        raise PartnerRevisionError("지금은 수정 요청을 받을 수 없습니다. 화면을 새로고침해 주세요.")
    rows, errors = normalize_revision_files(order.id, files)
    if errors:
        raise PartnerRevisionError("참고 사진을 다시 올려 주세요.", 400)

    current = [f for f in (sd.get("drawing_current_files") or []) if (f or {}).get("key")]
    target_keys = [f["key"] for f in current]
    target_numbers = list(range(1, len(current) + 1))
    sd["drawing_status"] = "RETURNED"
    history = list(sd.get("drawing_transfer_history") or [])
    history.append({
        "action": "REQUEST_REVISION",
        "by_user_id": user.id,
        "by_user_name": f"{user.name} (협력사)",
        "at": now_utc_naive().strftime("%Y-%m-%d %H:%M:%S"),
        "note": text,
        "files": rows,
        "files_count": len(rows),
        "target_drawing_keys": target_keys or None,
        "target_drawing_numbers": target_numbers or None,
        "target_drawing_key": target_keys[0] if len(target_keys) == 1 else None,
        "target_drawing_number": target_numbers[0] if len(target_numbers) == 1 else None,
        "partner_org_id": order.partner_org_id,
    })
    invalidate_customer_confirmation(sd, history[-1])
    sd["drawing_transfer_history"] = history

    def _write(locked):
        locked.structured_data = sd
        flag_modified(locked, "structured_data")

    execute_single_order_write(
        db, order_id=order.id, actor_user_id=user.id,
        policy_id=DRAWING_REVISION_REQUEST_POLICY_ID,
        payload={"note": text, "files": [r.get("key") for r in rows], "source": "partner"},
        write=_write,
    )

    customer = (((sd.get("parties") or {}).get("customer") or {}).get("name") or "").strip()
    message = (f"[협력사] 주문 #{order.id}" + (f" ({customer})" if customer else "")
               + f" 도면 수정 요청이 접수되었습니다. 메모: {text}")
    if rows:
        message += f" (첨부 {len(rows)}건)"
    notification = Notification(
        order_id=order.id,
        notification_type="DRAWING_REVISION",
        target_team="DRAWING",
        title="협력사 도면 수정 요청",
        message=message,
        created_by_user_id=user.id,
        created_by_name=f"{user.name} (협력사)",
    )
    db.add(notification)
    db.flush()
    fan_out_new_notification(db, notification, actor_user_id=user.id)
    db.add(SecurityLog(
        user_id=user.id,
        message=f"협력사 도면 수정 요청: #{order.id}",
        action="PARTNER_DRAWING_REVISION_REQUESTED",
        target_type="order",
        target_id=order.id,
        detail=normalize_security_detail({"partner_org_id": order.partner_org_id, "files": len(rows)}),
    ))
    return notification

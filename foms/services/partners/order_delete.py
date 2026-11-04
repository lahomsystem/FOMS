"""협력사 주문 지우기 — 라운즈가 올린 주문을 라운즈가 휴지통으로(설계서 docs/specs/2026-11-04-partner-order-delete_SPEC.md).

지울 수 있는 때는 "이대로 만들어 주세요" 전까지다(사용자 2026-11-04) — 접수 · 실측 예정 · 도면 작업 중 · 도면 확인 대기.
지우기는 우리 직원과 같은 :func:`soft_delete_order`(휴지통 — 관리자가 되살린다)이고, 이유 한 줄이 꼭 있어야 한다.
담당 팀 알림(품목 고치기와 같은 팀)을 남기고, 커밋 뒤 발주방에 짧은 "주문 삭제" 글을 한 번 보낸다(실패해도 지우기는 그대로).
발행 명세서가 있는 주문은 지울 수 없다(명세서는 주문과 함께 영구 정리된다).
"""
from __future__ import annotations

import logging
import re
from typing import Any

from foms.services.audit_writer import normalize_security_detail
from foms.services.auth.partner_scope import partner_can_read_order
from foms.services.channel_client import build_channel_bot_name, is_configured, send_group_message
from foms.services.channel_policy import ChannelGroupRetiredError, get_routing_group_id
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.orders.revision import lock_order_row
from foms.services.orders.soft_delete import soft_delete_order
from foms.services.partners.items_edit import partner_notice_team
from foms.services.partners.orders import partner_stage_label
from foms.services.partners.view import build_partner_order_view
from models import Notification, PartnerOrg, PartnerStatement, SecurityLog

logger = logging.getLogger(__name__)

#: "이대로 만들어 주세요"(제작 요청) 전 단계 — 이 단계에서만 협력사가 지운다.
DELETABLE_STAGES = ("RECEIVED", "MEASURE", "DRAWING", "CONFIRM")
MAX_REASON = 200
CLOSED_MESSAGE = "제작을 시작한 주문은 지울 수 없습니다. 저희 담당자에게 연락해 주세요."


class PartnerDeleteError(ValueError):
    """협력사 화면에 그대로 보여 줄 거부 이유. ``status`` 는 HTTP 코드."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def partner_delete_open(order: Any) -> bool:
    """협력사가 이 주문을 지울 수 있는가 — 제작 요청(도면 확정) 전 단계만."""
    stage = (getattr(order, "erp_stage_code", None) or "").upper()
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    blueprint = sd.get("blueprint") if isinstance(sd.get("blueprint"), dict) else {}
    return stage in DELETABLE_STAGES and not blueprint.get("customer_confirmed")


def _notify(db, user: Any, order: Any, customer: str, reason: str) -> None:
    notification = Notification(
        order_id=order.id,
        notification_type="PARTNER_ORDER_DELETED",
        target_team=partner_notice_team(order),
        title="협력사 주문 지움",
        message=f"[협력사] 주문 #{order.id}" + (f" ({customer})" if customer else "")
        + f"을 협력사가 지웠습니다. 이유: {reason} — 휴지통에서 되살릴 수 있습니다.",
        created_by_user_id=user.id,
        created_by_name=f"{user.name} (협력사)",
    )
    db.add(notification)
    db.flush()
    fan_out_new_notification(db, notification, actor_user_id=user.id)


def delete_partner_order(db, user: Any, order_id: int, reason: Any) -> dict[str, Any]:
    """협력사 주문을 휴지통으로(호출자가 commit). 발주방 글에 쓸 ``{order_id, org_name, customer, stage, reason}``."""
    order = lock_order_row(db, order_id)
    if order is None or order.deleted_at is not None or not partner_can_read_order(user, order):
        raise PartnerDeleteError("주문을 찾을 수 없습니다.", 404)
    text = re.sub(r"\s+", " ", str(reason if reason is not None else "")).strip()[:MAX_REASON]
    if not text:
        raise PartnerDeleteError("지우는 이유를 한 줄 적어 주세요.", 400)
    if not partner_delete_open(order):
        raise PartnerDeleteError(CLOSED_MESSAGE)
    if db.query(PartnerStatement.id).filter(PartnerStatement.order_id == order.id,
                                            PartnerStatement.status != "VOID").first() is not None:
        raise PartnerDeleteError("거래명세서가 있는 주문은 지울 수 없습니다. 저희 담당자에게 연락해 주세요.")
    view = build_partner_order_view(order)
    stage = partner_stage_label(order.erp_stage_code, order.as_axis_status,
                                (order.structured_data or {}).get("drawing_status") == "CONFIRMED",
                                (order.structured_data or {}).get("drawing_status") == "TRANSFERRED")
    soft_delete_order(db, order_id=order.id, actor_user_id=user.id, reason=f"협력사 삭제: {text}")
    org = db.get(PartnerOrg, order.partner_org_id)
    detail = {"order_id": order.id, "partner_org_id": order.partner_org_id, "stage": order.erp_stage_code,
              "reason": text}
    db.add(SecurityLog(user_id=user.id, action="PARTNER_ORDER_DELETED", target_type="order", target_id=order.id,
                       message=f"협력사 주문 지움: #{order.id} — {text}", detail=normalize_security_detail(detail)))
    _notify(db, user, order, view["customer_name"], text)
    return {"order_id": order.id, "org_name": org.name if org else "", "customer": view["customer_name"],
            "stage": stage, "reason": text, "team": partner_notice_team(order)}


def channel_notice_text(info: dict[str, Any], user_name: str) -> str:
    """발주방에 보낼 짧은 글 — 누가 · 어느 주문을 · 왜 지웠는지(주문 PUSH 본문 · 도면은 싣지 않는다)."""
    head = " · ".join(v for v in (f"[주문 삭제] {info['org_name']}".strip(), f"주문 #{info['order_id']}",
                                    info["customer"]) if v)
    return "\n".join((head, f"단계: {info['stage']}", f"지운 사람: {user_name} (협력사)", f"이유: {info['reason']}",
                      "휴지통에서 되살릴 수 있습니다."))


def send_channel_notice(info: dict[str, Any], user: Any) -> bool:
    """커밋 뒤 발주방 글 한 번. 실패해도 지우기는 되돌리지 않는다(기록만). 반환: 보냈는가."""
    try:
        if not is_configured():
            logger.warning("[협력사 주문 지움] 채널톡 설정 없음 — 발주방 글 건너뜀 order=%s", info["order_id"])
            return False
        group_id = get_routing_group_id("manual", {"push_kind": "drawing"})
        result = send_group_message(group_id, channel_notice_text(info, user.name),
                                    bot_name=build_channel_bot_name(f"{user.name} (협력사)"))
        return bool(result.get("success"))
    except ChannelGroupRetiredError:
        logger.info("[협력사 주문 지움] 발주방이 닫혀 있어 글을 건너뜀 order=%s", info["order_id"])
        return False
    except Exception:  # noqa: BLE001 - 지우기는 끝났다, 글 실패만 남긴다
        logger.exception("[협력사 주문 지움] 발주방 글 실패 order=%s", info["order_id"])
        return False

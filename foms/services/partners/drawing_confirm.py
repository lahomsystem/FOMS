"""PARTNER-03: 협력사 "이대로 만들어 주세요" — 고객컨펌(CONFIRM) 승인 → 생산(PRODUCTION).

우리 시스템에는 고객 확인 단계가 없고(협력사가 고객과 따로 확인), 협력사가 우리 최종 도면을 보고
누르는 이 버튼이 기존 CONFIRM 담당자 승인 자리를 대신한다(사용자 결정 2026-10-08).
기록은 직원 승인(``foms/api/quest.py`` ``api_order_quest_approve`` 의 assignee 갈래)과 **같은 모양**
으로 남긴다 — quest.assignee_approval · quest COMPLETED · blueprint.customer_confirmed ·
QUEST_APPROVAL_CHANGED 이벤트 — 그리고 전이는 같은 정본(``advance_stage_on_quest_completion``)을
탄다. 직원 라우트는 직원 role/팀을 요구해 협력사가 쓸 수 없다.

도면 게이트(``confirm_exit_block`` — 도면 수령 확정 CONFIRMED 여야 함)는 그대로 지킨다. 관리자
강제 진행 같은 우회는 협력사에게 없다.
스펙: docs/specs/2026-10-08-partner-portal_SPEC.md §13
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from foms.services.audit_writer import normalize_security_detail
from foms.services.auth.partner_scope import partner_can_read_order
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.erp_policy import STAGE_NAME_TO_CODE, create_quest_from_template, get_stage
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.confirm_drawing_gate import confirm_exit_block, normalize_stage_code
from foms.services.orders.drawing_customer_send import drawing_round_info
from foms.services.orders.drawing_transfer import _is_drawing_key
from foms.services.orders.quest_transition_service import (
    advance_stage_on_quest_completion,
    find_stage_quest_for_approve,
)
from foms.services.orders.revision import lock_order_row
from models import OrderEvent, SecurityLog

_COMMAND = "PARTNER_DRAWING_APPROVE"
_SOURCE_SCREEN = "partner_portal"


class PartnerConfirmError(ValueError):
    """협력사 화면에 그대로 보여 줄 수 있는 거부 사유. ``status`` 는 HTTP 코드."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def final_drawings_for_partner(order: Any) -> list[dict[str, Any]]:
    """협력사에게 보여 줄 우리 최종 도면 — 도면팀이 넘긴 현재 파일만(협력사 초안은 제외)."""
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    return [
        f for f in resolve_final_drawing_files(sd)
        if _is_drawing_key(order.id, f.get("key") or "")
    ]


def approve_partner_drawing(db, user: Any, order_id: int, *, idempotency_key: str | None = None) -> Any:
    """협력사가 최종 도면을 확인하고 제작을 요청한다(호출자가 commit).

    Raises:
        PartnerConfirmError: 주문 없음(404)·도면 확인 차례 아님·도면 미확정(409).
    """
    order = lock_order_row(db, order_id)
    if order is None or not partner_can_read_order(user, order):
        raise PartnerConfirmError("주문을 찾을 수 없습니다.", 404)
    sd = copy.deepcopy(order.structured_data or {})
    stage_code = normalize_stage_code(get_stage(sd))
    if stage_code != "CONFIRM":
        raise PartnerConfirmError("지금은 도면 확인 차례가 아닙니다. 화면을 새로고침해 주세요.")
    if confirm_exit_block(sd) is not None:
        raise PartnerConfirmError("도면이 아직 확정되지 않았습니다. 저희 담당자에게 문의해 주세요.")

    stage_name = {v: k for k, v in STAGE_NAME_TO_CODE.items()}.get(stage_code, stage_code)
    quest, index = find_stage_quest_for_approve(sd, stage_name, stage_code)
    if quest is None:
        quest = create_quest_from_template(stage_name, "", sd)
        if quest is None:
            raise PartnerConfirmError("도면 확인 단계를 찾을 수 없습니다. 저희 담당자에게 문의해 주세요.")
        sd.setdefault("quests", []).append(quest)
        index = len(sd["quests"]) - 1

    now = datetime.datetime.now()
    approver = f"{user.name} (협력사)"
    quest["assignee_approval"] = {
        "approved": True,
        "approved_by": user.id,
        "approved_by_name": approver,
        "approved_at": now.isoformat(),
    }
    quest["status"] = "COMPLETED"
    quest["completed_at"] = now.isoformat()
    quest["updated_at"] = now.isoformat()
    sd["quests"][index] = quest
    blueprint = sd.get("blueprint") if isinstance(sd.get("blueprint"), dict) else {}
    blueprint.update({"customer_confirmed": True, "confirmed_at": now.isoformat(), "confirmed_by": approver})
    sd["blueprint"] = blueprint

    round_info = drawing_round_info(sd)
    finals = [f.get("key") for f in final_drawings_for_partner(order)]
    db.add(OrderEvent(
        order_id=order.id,
        event_type="QUEST_APPROVAL_CHANGED",
        payload={
            "domain": "SALES_DOMAIN",
            "action": "QUEST_ASSIGNEE_APPROVED",
            "target": "quest.assignee_approval",
            "stage": stage_code,
            "before": "not_approved",
            "after": "approved",
            "change_method": "API",
            "source_screen": _SOURCE_SCREEN,
            "reason": "협력사 도면 확인 — 이대로 제작",
            "is_override": False,
            "override_reason": None,
        },
        created_by_user_id=user.id,
    ))
    order.structured_data = sd
    flag_modified(order, "structured_data")
    order.updated_at = now
    sync_erp_flat_columns(order, sd)
    # 누가 · 몇 차 도면 · 어떤 파일을 보고 눌렀는지 — 잘못 만들어졌을 때 책임을 가리는 근거.
    db.add(SecurityLog(
        user_id=user.id,
        message=f"협력사 도면 확인(이대로 제작): #{order.id}",
        action="PARTNER_DRAWING_APPROVED",
        target_type="order",
        target_id=order.id,
        detail=normalize_security_detail({
            "partner_org_id": order.partner_org_id,
            "drawing_round": getattr(round_info, "round", None),
            "final_drawing_keys": finals,
        }),
    ))
    body = {"order_id": order.id, "idempotency_key": idempotency_key}
    return advance_stage_on_quest_completion(
        db,
        order_id=order.id,
        actor_user_id=user.id,
        scope_hash=hashlib.sha256(f"{_COMMAND}:{order.id}".encode("utf-8")).hexdigest(),
        request_hash=hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest(),
        idempotency_key=idempotency_key,
        reason="고객컨펌 최종 승인(협력사)",
        source_screen=_SOURCE_SCREEN,
        now=now,
    )

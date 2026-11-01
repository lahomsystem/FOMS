"""협력사 "실측 끝 · 도면 요청" — 실측 예정(MEASURE) → 도면 단계(DRAWING)(사용자 결정 2026-11-01).

본사 "도면 단계로 넘기기"(실측 quest 최종 승인 → ``COMPLETE_MEASUREMENT``)와 같은 한 경로를 탄다 — 실측 quest 를
협력사 이름으로 승인하고 :func:`advance_stage_on_quest_completion` 로 옮긴다(:mod:`drawing_confirm` 의
"이대로 만들어 주세요"와 같은 모양). 조건(:mod:`measure_ready`)이 모자라면 무엇이 빠졌는지 돌려준다.
영발 PUSH 는 커밋 뒤 API 층이 한 번 보낸다(``foms/api/partner/channel_push.py``).
스펙: docs/specs/2026-11-01-partner-measure-pending_SPEC.md
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
from foms.services.erp_policy import STAGE_NAME_TO_CODE, create_quest_from_template, get_stage
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.confirm_drawing_gate import normalize_stage_code
from foms.services.orders.quest_transition_service import (
    advance_stage_on_quest_completion,
    find_stage_quest_for_approve,
)
from foms.services.orders.revision import lock_order_row
from foms.services.partners.measure_ready import PRE_DRAWING_STAGES, order_drawing_missing
from foms.services.partners.orders import notify_partner_teams
from models import OrderEvent, SecurityLog

_COMMAND = "PARTNER_DRAWING_REQUEST"
_SOURCE_SCREEN = "partner_portal"


class PartnerDrawingRequestError(ValueError):
    """협력사 화면에 그대로 보일 거부 사유. ``status`` 는 HTTP 코드, ``missing`` 은 빠진 것."""

    def __init__(self, message: str, status: int = 409, missing: list[str] | None = None):
        super().__init__(message)
        self.status = status
        self.missing = missing or []


def _approve_measure_quest(sd: dict[str, Any], stage_code: str, approver: str, user_id: int, now: datetime.datetime) -> None:
    """실측 quest 를 협력사 이름으로 승인 · 완료한다(없으면 템플릿으로 만든다). ``sd`` 를 제자리에서 고친다."""
    stage_name = {v: k for k, v in STAGE_NAME_TO_CODE.items()}.get(stage_code, stage_code)
    quest, index = find_stage_quest_for_approve(sd, stage_name, stage_code)
    if quest is None:
        quest = create_quest_from_template(stage_name, "", sd)
        if quest is None:
            return
        sd.setdefault("quests", []).append(quest)
        index = len(sd["quests"]) - 1
    stamp = now.isoformat()
    quest = dict(quest)
    quest["assignee_approval"] = {"approved": True, "approved_by": user_id, "approved_by_name": approver,
                                  "approved_at": stamp}
    quest["status"] = "COMPLETED"
    quest["completed_at"] = stamp
    quest["updated_at"] = stamp
    sd["quests"][index] = quest


def request_partner_drawing(db, user: Any, order_id: int) -> Any:
    """실측 예정 주문을 도면 단계로 보낸다(호출자가 commit).

    Raises:
        PartnerDrawingRequestError: 주문 없음(404) · 실측 예정이 아님(409) · 조건 모자람(400, ``missing``).
    """
    order = lock_order_row(db, order_id)
    if order is None or not partner_can_read_order(user, order):
        raise PartnerDrawingRequestError("주문을 찾을 수 없습니다.", 404)
    sd = copy.deepcopy(order.structured_data or {})
    stage_code = normalize_stage_code(get_stage(sd))
    if stage_code not in PRE_DRAWING_STAGES:
        raise PartnerDrawingRequestError("이미 도면 단계로 넘어간 주문입니다. 화면을 새로고침해 주세요.")
    missing = order_drawing_missing(order)
    if missing:
        raise PartnerDrawingRequestError("도면을 요청하려면 더 넣어야 할 것이 있습니다.", 400, missing)

    now = datetime.datetime.now()
    approver = f"{user.name} (협력사)"
    _approve_measure_quest(sd, stage_code, approver, user.id, now)
    sd.setdefault("assignments", {})["owner_team"] = "DRAWING"
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
            "reason": "협력사 실측 끝 · 도면 요청",
            "is_override": False,
            "override_reason": None,
        },
        created_by_user_id=user.id,
    ))
    order.structured_data = sd
    flag_modified(order, "structured_data")
    order.measurement_completed = True
    order.updated_at = now
    sync_erp_flat_columns(order, sd)
    db.add(SecurityLog(
        user_id=user.id,
        message=f"협력사 도면 요청(실측 끝): #{order.id}",
        action="PARTNER_DRAWING_REQUESTED",
        target_type="order",
        target_id=order.id,
        detail=normalize_security_detail({"partner_org_id": order.partner_org_id}),
    ))
    body = {"order_id": order.id, "partner_drawing_request": True}
    advance_stage_on_quest_completion(
        db,
        order_id=order.id,
        actor_user_id=user.id,
        scope_hash=hashlib.sha256(f"{_COMMAND}:{order.id}".encode("utf-8")).hexdigest(),
        request_hash=hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest(),
        reason="실측 완료 — 협력사 도면 요청",
        source_screen=_SOURCE_SCREEN,
        now=now,
    )
    customer = ((sd.get("parties") or {}).get("customer") or {}).get("name") or order.customer_name or ""
    head = f"[{(sd.get('partner_intake') or {}).get('partner_name') or '협력사'}] 주문 #{order.id} ({customer})"
    notify_partner_teams(db, user, order.id, (
        ("DRAWING", f"{head} 실측 끝 — 도면을 요청했습니다. 도면 작업을 시작해 주세요."),
        ("CS", f"{head} 실측 끝 — 도면 단계로 넘어갔습니다(확인용)."),
    ), title="협력사 도면 요청")
    return order

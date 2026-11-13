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
from foms.services.partners.item_options import ItemOptionsError, confirm_partner_options
from foms.services.orders.drawing_transfer import _is_drawing_key
from foms.services.orders.quest_transition_service import (
    advance_stage_on_quest_completion,
    find_stage_quest_for_approve,
)
from foms.services.orders.drawing_confirm_partial import PartialConfirmError, PartialConfirmPlan, plan_partial_confirm
from foms.services.orders.drawing_receipt_command import advance_receipt_stage, record_drawing_receipt
from foms.services.orders.revision import lock_order_row
from foms.services.orders.state_axes import read_main_stage
from models import OrderEvent, SecurityLog

_COMMAND = "PARTNER_DRAWING_APPROVE"
_SOURCE_SCREEN = "partner_portal"


class PartnerConfirmError(ValueError):
    """협력사 화면에 그대로 보여 줄 수 있는 거부 사유. ``status`` 는 HTTP 코드."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def final_drawings_for_partner(order: Any) -> list[dict[str, Any]]:
    """협력사에게 보여 줄 우리 최종 도면 — 도면팀이 넘긴 현재 파일만(협력사 초안은 제외).

    ``no`` 는 우리 ERP 도면 번호 — ``drawing_current_files`` 안 자리(1부터, 수정 요청 "2번 도면"과 같은 셈).
    협력사 초안 같은 줄을 걸러도 번호를 다시 세지 않는다(사용자 2026-11-05 "도면 번호와 썸네일 번호가 같아야").
    """
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    numbers: dict[str, int] = {}
    for idx, raw in enumerate(sd.get("drawing_current_files") or [], start=1):
        key = str((raw or {}).get("key") or "").strip() if isinstance(raw, dict) else ""
        numbers.setdefault(key, idx)
    return [
        {**f, "no": numbers.get(f.get("key") or "", 0)} for f in resolve_final_drawing_files(sd)
        if _is_drawing_key(order.id, f.get("key") or "")
    ]


def approve_partner_drawing(db, user: Any, order_id: int, *, idempotency_key: str | None = None,
                            options: Any = None) -> Any:
    """협력사가 최종 도면을 확인하고 제작을 요청한다(호출자가 commit).

    협력사 옵션 줄이 있는 주문이면 같은 트랜잭션에서 옵션도 확정한다(설계서 2026-11-03-partner-statement §5.4) —
    "상담 후 정함" 품목은 ``options``(``{품목 uid: 고른 옵션}``)로 고른 값을 넣고, 지금 값을 확정본으로 복사하며,
    확정 목록의 지문을 감사 기록에 남긴다.

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
    try:
        options_fingerprint = confirm_partner_options(db, order, options, user.id, s_data=sd)
    except ItemOptionsError as exc:
        raise PartnerConfirmError(str(exc)) from exc

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
            "options_fingerprint": options_fingerprint,
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


def confirm_partner_drawing_receipt(db, user: Any, order_id: int, request_body: Any = None) -> str:
    """협력사가 저희가 보낸 도면을 확인했다(호출자가 commit) — 고객컨펌(CONFIRM)으로 넘어간다.

    FOMS 영업 담당의 "도면 수령 확인"과 같은 한 경로(``advance_receipt_stage`` + ``record_drawing_receipt``)를
    탄다. 협력사 주문은 담당이 협력사 직원이라 이 단추를 협력사가 누른다(사용자 2026-10-28 — 전에는 우리
    CS 가 눌렀다). 그 뒤 고객과 확인하고 "이대로 만들어 주세요"(:func:`approve_partner_drawing`).

    ``request_body`` 의 ``final_drawing_keys`` 가 오면 그 도면만 최종으로 남긴다(우리 영업 확정 창과 같은 ``plan_partial_confirm``,
    설계서 2026-11-09-partner-receipt-pick-drawings). ``None`` 이면 지금처럼 전부.

    Raises:
        PartnerConfirmError: 주문 없음(404) · 보낸 도면 확인 차례가 아님(409) · 고른 도면이 틀림(400).
    """
    order = lock_order_row(db, order_id)
    if order is None or not partner_can_read_order(user, order):
        raise PartnerConfirmError("주문을 찾을 수 없습니다.", 404)
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    old_stage = read_main_stage(order)
    old_status = sd.get("drawing_status")
    # 고객컨펌(CONFIRM)에서 다시 보낸 도면도 받는다 — 단계는 그대로(advance_receipt_stage 가 건너뜀), 우리 영업 수령 확인과 같다.
    if old_stage not in ("DRAWING", "CONFIRM") or old_status != "TRANSFERRED" or not final_drawings_for_partner(order):
        raise PartnerConfirmError("지금은 도면 확인 차례가 아닙니다. 화면을 새로고침해 주세요.")
    picked = request_body.get("final_drawing_keys") if isinstance(request_body, dict) else None
    plan = _partner_pick_plan(order, sd, picked)
    body = {"order_id": order.id, "partner_drawing_receipt": True}
    stage_moved = advance_receipt_stage(db, order, actor_user_id=user.id, body=body)
    next_stage = record_drawing_receipt(
        db, order, actor_user_id=user.id, actor_name=f"{user.name} (협력사)", old_drawing_status=old_status,
        old_stage=old_stage, stage_moved=stage_moved, body=body, partial_plan=plan, source_screen=_SOURCE_SCREEN)
    db.add(SecurityLog(
        user_id=user.id,
        message=f"협력사 도면 확인(받음): #{order.id}",
        action="PARTNER_DRAWING_RECEIVED",
        target_type="order",
        target_id=order.id,
        detail=normalize_security_detail({
            "partner_org_id": order.partner_org_id,
            "drawing_round": getattr(drawing_round_info(sd), "round", None),
            "final_drawing_keys": plan.final_keys if plan else None,
            "excluded_keys": [e["key"] for e in plan.excluded] if plan else [],
        }),
    ))
    return next_stage


def _partner_pick_plan(order: Any, sd: dict[str, Any], final_drawing_keys: Any) -> PartialConfirmPlan | None:
    """협력사가 고른 도면으로 부분 확정 계획을 만든다(아무것도 바꾸지 않는다).

    협력사는 화면에 보이는 우리 도면(:func:`final_drawings_for_partner`)만 고를 수 있다. 화면에 안 보이는 줄
    (협력사 초안 등)은 협력사가 고르지 않아도 그대로 남긴다 — 못 보는 것을 지우지 않게.
    """
    if final_drawing_keys is None:
        return None
    if not isinstance(final_drawing_keys, list):
        raise PartnerConfirmError("고른 도면 형식이 올바르지 않습니다. 화면을 새로고침해 주세요.", 400)
    visible = {str(f.get("key") or "") for f in final_drawings_for_partner(order)}
    picked = {str(k or "").strip() for k in final_drawing_keys} - {""}
    if picked - visible:
        raise PartnerConfirmError("지금 도면 목록에 없는 도면이 있습니다. 화면을 새로고침해 주세요.", 400)
    if not picked:
        raise PartnerConfirmError("진행할 도면을 하나 이상 골라 주세요.", 400)
    current = [str((f or {}).get("key") or "").strip() for f in (sd.get("drawing_current_files") or [])
               if isinstance(f, dict)]
    keep = sorted(picked) + [k for k in current if k and k not in visible]
    try:
        return plan_partial_confirm(sd, keep, None)
    except PartialConfirmError as exc:
        raise PartnerConfirmError(str(exc), 400) from exc

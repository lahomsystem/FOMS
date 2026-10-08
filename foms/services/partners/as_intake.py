"""PARTNER-03: 협력사 AS 접수 — 협력사 고객의 AS 는 협력사를 통해서만 받는다(사용자 결정 2026-10-08).

직원 AS 접수(``foms/api/cs/as_orders.py`` ``api_as_register``)와 같은 정본 서비스
(:func:`register_as_cycle`)로 새 AS 건을 연다. 부수 기록도 같은 모양으로 남긴다 — 레거시 원문
굳히기 · 접수 원문(reception) · "AS 접수됨" 시스템 줄 · 비용 판정 기본값. 고객에게는 아무것도 보내지
않는다(직원 경로도 접수 때 보내지 않는다).

열린 AS 건이 있으면 새로 열지 않는다(409) — 재접수(같은 건 갱신)는 우리 직원 몫이다.
스펙: docs/specs/2026-10-08-partner-portal_SPEC.md §14
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from foms.services.audit_writer import normalize_security_detail
from foms.services.auth.partner_scope import partner_can_read_order
from foms.services.datetime_kst import get_today_kst
from foms.services.orders.as_cycle_service import (
    AS_IN_PROGRESS,
    AS_RECEIVED,
    current_cycle,
    cycle_status,
    register_as_cycle,
)
from foms.services.orders.as_log import append_client_log, append_system_log, migrate_legacy_into_log
from foms.services.orders.revision import lock_order_row
from models import SecurityLog

MAX_CONTENT = 2000
# AS 를 받을 수 있는 단계 — 시공이 시작된 뒤(우리가 시공을 간다).
AS_OPEN_STAGES = frozenset({"CONSTRUCTION", "CS", "COMPLETED", "AS", "AS_RECEIVED", "AS_COMPLETED"})


class PartnerASError(ValueError):
    """협력사 화면에 그대로 보여 줄 수 있는 거부 사유. ``status`` 는 HTTP 코드."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def register_partner_as(db, user: Any, order_id: int, content: Any, *, idempotency_key: str | None = None) -> str | None:
    """AS 건을 연다(호출자가 commit). 접수 원문 로그 id 를 돌려준다(사진을 그 줄에 붙인다).

    Raises:
        PartnerASError: 주문 없음(404)·내용 없음(400)·아직 시공 전·진행 중인 AS 있음(409).
    """
    text = str(content or "").strip()[:MAX_CONTENT]
    if not text:
        raise PartnerASError("AS 내용을 적어 주세요.", 400)
    order = lock_order_row(db, order_id)
    if order is None or order.deleted_at is not None or not partner_can_read_order(user, order):
        raise PartnerASError("주문을 찾을 수 없습니다.", 404)
    if (order.erp_stage_code or "").upper() not in AS_OPEN_STAGES:
        raise PartnerASError("시공이 끝난 주문만 AS 를 접수할 수 있습니다.")
    open_cycle = current_cycle(order.structured_data or {})
    if open_cycle is not None and cycle_status(open_cycle) in (AS_RECEIVED, AS_IN_PROGRESS):
        raise PartnerASError("이미 진행 중인 AS 가 있습니다. 추가 내용은 저희 담당자에게 알려 주세요.")

    who = f"{user.name} (협력사)"
    captured: dict[str, Any] = {}

    def _hook(sd: dict[str, Any]) -> None:
        shipment = sd.setdefault("shipment", {})
        migrate_legacy_into_log(sd)
        entry = append_client_log(sd, log_type="reception", text=text, by=who, by_id=user.id)
        captured["reception_log_id"] = entry["id"]
        append_system_log(sd, text="AS 접수됨 (협력사)")
        # 비용 판정은 우리 몫 — 판정이 없을 때만 '미정' 기본값을 둔다(확정 판정은 덮지 않는다).
        if not isinstance(shipment.get("as_billing"), dict):
            shipment["as_billing"] = {
                "type": "undecided", "confirmed": False, "amount": None,
                "reason": "", "decided_by": "", "decided_at": "",
            }

    body = {"order_id": order.id, "content": text, "idempotency_key": idempotency_key}
    register_as_cycle(
        db,
        order_id=order.id,
        actor_user_id=user.id,
        as_content=text,
        source_screen="partner_portal",
        received_date=get_today_kst().strftime("%Y-%m-%d"),
        scope_hash=hashlib.sha256(f"PARTNER_AS_REGISTER:{order.id}".encode("utf-8")).hexdigest(),
        request_hash=hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
        idempotency_key=idempotency_key,
        sd_hook=_hook,
    )
    db.add(SecurityLog(
        user_id=user.id,
        message=f"협력사 AS 접수: #{order.id}",
        action="PARTNER_AS_REGISTERED",
        target_type="order",
        target_id=order.id,
        detail=normalize_security_detail({"partner_org_id": order.partner_org_id}),
    ))
    return captured.get("reception_log_id")

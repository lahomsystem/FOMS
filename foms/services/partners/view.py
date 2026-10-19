"""PARTNER-FOMS 3-1: 협력사 주문 화면 투영 — 협력사에게 보여 줄 값만 고른다.

우리 주문 화면은 주문 데이터 전체(입금 · 잔금 · 견적 · 내부 비고)를 페이지에 싣는다. 협력사 화면은 이 함수가
고른 허용 키만 받는다(빼고 싶은 칸을 숨기는 방식이 아니다). 스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md
§3.3 · §4-1 · §12.

* 품목은 도면팀이 고친 **현재값**이다(사용자 결정 §5-5). 협력사가 고칠 수 있는 키 + uid 만 싣는다.
* 시공 특이사항(시공팀 메모)은 넣지 않는다(§5-1).
"""
from __future__ import annotations

import copy
from typing import Any

from foms.services.partners.items_edit import ITEMS_EDIT_STAGES, PARTNER_ITEM_KEYS
from foms.services.partners.orders import partner_stage_label
from models import Order

# 진행 칸(쉬운 단계). 내부 단계 코드 → 칸 번호. AS 는 "완료" 칸에 둔다(AS 진행은 완공 사진 탭이 보여 준다).
PARTNER_STEPS = ("접수 확인", "도면 작업", "도면 확인", "생산", "시공", "완료")
_STEP_OF_STAGE = {
    "RECEIVED": 0, "MEASURE": 0, "DRAWING": 1, "CONFIRM": 2, "PRODUCTION": 3, "CONSTRUCTION": 4,
    "CS": 5, "COMPLETED": 5, "AS": 5, "AS_RECEIVED": 5, "AS_COMPLETED": 5,
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _steps(stage: str) -> list[dict[str, str]]:
    now = _STEP_OF_STAGE.get(stage, 0)
    return [
        {"label": label, "state": "done" if i < now else ("now" if i == now else "todo")}
        for i, label in enumerate(PARTNER_STEPS)
    ]


def _items(sd: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in sd.get("items") or []:
        if not isinstance(item, dict):
            continue
        row = {key: copy.deepcopy(item[key]) for key in PARTNER_ITEM_KEYS if item.get(key) not in (None, "")}
        rows.append({**row, "uid": _text(item.get("uid")), "spec_rows": _spec_rows(item)})
    return rows


def _spec_rows(item: dict[str, Any]) -> list[dict[str, str]]:
    """규격 줄. 옛 품목(줄 없이 첫 줄 칸만)도 한 줄로 보인다."""
    keys = ("spec_width", "spec_depth", "spec_height")
    rows = [{k: _text(r.get(k)) for k in keys} for r in item.get("spec_rows") or [] if isinstance(r, dict)]
    return rows or [{k: _text(item.get(k)) for k in keys}]


def build_partner_order_view(order: Order) -> dict[str, Any]:
    """협력사 주문 화면이 받는 값(허용 키만). 금액 · 견적 · 입금 · 비고 · 내부 표시는 없다."""
    sd = _dict(order.structured_data)
    intake = _dict(sd.get("partner_intake"))
    parties = _dict(sd.get("parties"))
    customer = _dict(parties.get("customer"))
    manager = _dict(parties.get("manager"))
    notes = _dict(sd.get("notes"))  # 협력사 주문은 등록 때 문자열(보낸 메모)이라 dict 일 때만 읽는다
    site = _dict(sd.get("site"))
    construction = _dict(_dict(sd.get("schedule")).get("construction"))
    stage = (order.erp_stage_code or "").upper()
    return {
        "id": order.id,
        "customer_name": _text(customer.get("name")) or _text(order.customer_name),
        "customer_phone": _text(customer.get("phone")) or _text(order.phone),
        "phone_note": _text(notes.get("phone_note")),
        "received_by": _text(intake.get("submitted_by_name")),
        "received_date": _text(order.received_date),
        "received_time": _text(order.received_time),
        "manager_user_id": manager.get("partner_user_id"),
        "manager_name": _text(manager.get("partner_user_name")),
        "manager_phone": _text(manager.get("phone")),
        "stage_code": stage,
        "stage_label": partner_stage_label(order.erp_stage_code, order.as_axis_status),
        "steps": _steps(stage),
        "address": _text(site.get("address_full")) or _text(order.address),
        "address_note": _text(notes.get("address_note")),
        "measured_on": _text(intake.get("measured_on")),
        "measurement_note": _text(notes.get("measurement_note")),
        "construction_date": _text(construction.get("date")) or _text(order.erp_construction_date),
        "construction_time": _text(construction.get("time")),
        "memo": _text(intake.get("memo")),
        "submitted_at": _text(intake.get("submitted_at"))[:16].replace("T", " "),
        "items": _items(sd),
        "items_editable": stage in ITEMS_EDIT_STAGES,
    }

"""
ChannelTalk automatic push payload builders.

These helpers convert domain-level order changes into durable, human-readable
message payloads so the worker does not have to reconstruct diffs later.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

from foms.services.orders.status_constants import STATUS
from foms.services.erp_policy import STAGE_LABELS

__all__ = [
    "build_structured_update_payload",
    "build_field_change_payload",
    "build_shipment_update_payload",
    "build_payment_confirmation_payload",
]

TEAM_LABELS = {
    "CS": "상담팀",
    "SALES": "영업팀",
    "MEASURE": "실측팀",
    "DRAWING": "도면팀",
    "PRODUCTION": "생산팀",
    "CONSTRUCTION": "시공팀",
}


def _is_empty(value: Any) -> bool:
    return value in (None, "", [], {})


def _display_default(value: Any) -> str:
    if _is_empty(value):
        return "없음"
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if isinstance(value, (list, tuple, set)):
        rendered = [str(v).strip() for v in value if str(v).strip()]
        return ", ".join(rendered) if rendered else "없음"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip() or "없음"


def _display_stage(value: Any) -> str:
    if _is_empty(value):
        return "없음"
    value_str = str(value).strip()
    return STAGE_LABELS.get(value_str, STATUS.get(value_str, value_str))


def _display_team(value: Any) -> str:
    if _is_empty(value):
        return "없음"
    value_str = str(value).strip()
    return TEAM_LABELS.get(value_str, value_str)


def _display_urgent(value: Any) -> str:
    return "긴급" if bool(value) else "일반"


def _display_confirmed(value: Any) -> str:
    return "확인" if bool(value) else "미확인"


def _display_site_extra(value: Any) -> str:
    if _is_empty(value):
        return "없음"
    normalized: List[str] = []
    for item in value if isinstance(value, list) else [value]:
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            color = str(item.get("color", "")).strip()
            if text and color and color != "black":
                normalized.append(f"{text} ({color})")
            elif text:
                normalized.append(text)
        else:
            text = str(item).strip()
            if text:
                normalized.append(text)
    return ", ".join(normalized) if normalized else "없음"


def _change_line(label: str, before: Any, after: Any, formatter=_display_default) -> Optional[str]:
    before_text = formatter(before)
    after_text = formatter(after)
    if before_text == after_text:
        return None
    return f"{label}: {before_text} -> {after_text}"


def _actor_payload(payload: Dict[str, Any], actor_name: Optional[str]) -> Dict[str, Any]:
    if actor_name:
        payload["changed_by"] = actor_name
    return payload


def _order_change_payload(
    *,
    event_type: str,
    event_title: str,
    change_lines: Iterable[str],
    actor_name: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "event_type": event_type,
        "event_title": event_title,
        "change_lines": [line for line in change_lines if line],
    }
    if reason:
        payload["reason"] = reason
    return _actor_payload(payload, actor_name)


def build_structured_update_payload(
    old_sd: Dict[str, Any],
    new_sd: Dict[str, Any],
    actor_name: Optional[str] = None,
) -> Dict[str, Any]:
    workflow_old = old_sd.get("workflow") or {}
    workflow_new = new_sd.get("workflow") or {}
    schedule_old = old_sd.get("schedule") or {}
    schedule_new = new_sd.get("schedule") or {}
    assignments_old = old_sd.get("assignments") or {}
    assignments_new = new_sd.get("assignments") or {}
    parties_old = old_sd.get("parties") or {}
    parties_new = new_sd.get("parties") or {}
    flags_old = old_sd.get("flags") or {}
    flags_new = new_sd.get("flags") or {}
    site_old = old_sd.get("site") or {}
    site_new = new_sd.get("site") or {}

    change_lines: List[str] = []
    line = _change_line("상태", workflow_old.get("stage"), workflow_new.get("stage"), _display_stage)
    if line:
        change_lines.append(line)

    line = _change_line(
        "담당자",
        (parties_old.get("manager") or {}).get("name"),
        (parties_new.get("manager") or {}).get("name"),
    )
    if line:
        change_lines.append(line)

    line = _change_line(
        "담당 팀",
        assignments_old.get("owner_team"),
        assignments_new.get("owner_team"),
        _display_team,
    )
    if line:
        change_lines.append(line)

    line = _change_line(
        "실측일",
        (schedule_old.get("measurement") or {}).get("date"),
        (schedule_new.get("measurement") or {}).get("date"),
    )
    if line:
        change_lines.append(line)

    line = _change_line(
        "시공일",
        (schedule_old.get("construction") or {}).get("date"),
        (schedule_new.get("construction") or {}).get("date"),
    )
    if line:
        change_lines.append(line)

    line = _change_line(
        "긴급 여부",
        flags_old.get("urgent"),
        flags_new.get("urgent"),
        _display_urgent,
    )
    if line:
        change_lines.append(line)

    line = _change_line(
        "연락처",
        (parties_old.get("customer") or {}).get("phone"),
        (parties_new.get("customer") or {}).get("phone"),
    )
    if line:
        change_lines.append(line)

    old_address = site_old.get("address_full") or site_old.get("address_main")
    new_address = site_new.get("address_full") or site_new.get("address_main")
    line = _change_line("주소", old_address, new_address)
    if line:
        change_lines.append(line)

    payment_old = old_sd.get("payment") if isinstance(old_sd.get("payment"), dict) else {}
    payment_new = new_sd.get("payment") if isinstance(new_sd.get("payment"), dict) else {}
    line = _change_line(
        "계약금 확인",
        payment_old.get("deposit_confirmed"),
        payment_new.get("deposit_confirmed"),
        _display_confirmed,
    )
    if line:
        change_lines.append(line)
    line = _change_line(
        "잔금 확인",
        payment_old.get("balance_confirmed"),
        payment_new.get("balance_confirmed"),
        _display_confirmed,
    )
    if line:
        change_lines.append(line)

    urgent_now = bool(flags_new.get("urgent"))
    urgent_changed = bool(flags_old.get("urgent")) != urgent_now
    if urgent_changed and urgent_now:
        return _order_change_payload(
            event_type="urgent",
            event_title="긴급 알림",
            change_lines=change_lines or ["긴급 여부: 일반 -> 긴급"],
            actor_name=actor_name,
            reason=(flags_new.get("urgent_reason") or "긴급 확인 필요"),
        )

    if change_lines and all(
        ln.startswith("계약금 확인:") or ln.startswith("잔금 확인:")
        for ln in change_lines
    ):
        return _order_change_payload(
            event_type="payment_confirmation_changed",
            event_title="결제 확인 변경",
            change_lines=change_lines,
            actor_name=actor_name,
        )

    if len(change_lines) == 1:
        only_line = change_lines[0]
        if only_line.startswith("상태:"):
            return _order_change_payload(
                event_type="stage_changed",
                event_title="상태 변경",
                change_lines=change_lines,
                actor_name=actor_name,
            )
        if only_line.startswith("담당자:"):
            return _order_change_payload(
                event_type="manager_changed",
                event_title="담당자 변경",
                change_lines=change_lines,
                actor_name=actor_name,
            )
        if only_line.startswith("담당 팀:"):
            return _order_change_payload(
                event_type="owner_team_changed",
                event_title="담당 팀 변경",
                change_lines=change_lines,
                actor_name=actor_name,
            )
        if only_line.startswith("실측일:") or only_line.startswith("시공일:"):
            return _order_change_payload(
                event_type="schedule_changed",
                event_title="일정 변경",
                change_lines=change_lines,
                actor_name=actor_name,
            )

    return _order_change_payload(
        event_type="order_updated",
        event_title="정보 변경",
        change_lines=change_lines,
        actor_name=actor_name,
    )


def build_field_change_payload(
    *,
    label: str,
    before: Any,
    after: Any,
    event_type: str,
    event_title: str,
    actor_name: Optional[str] = None,
    formatter=_display_default,
) -> Dict[str, Any]:
    line = _change_line(label, before, after, formatter) or f"{label}: {_display_default(after)}"
    return _order_change_payload(
        event_type=event_type,
        event_title=event_title,
        change_lines=[line],
        actor_name=actor_name,
    )


def build_shipment_update_payload(
    before_shipment: Dict[str, Any],
    after_shipment: Dict[str, Any],
    actor_name: Optional[str] = None,
) -> Dict[str, Any]:
    change_lines: List[str] = []
    mapping = (
        ("construction_time", "시공시간", _display_default),
        ("drawing_manager", "도면 담당", _display_default),
        ("drawing_managers", "도면 담당자 목록", _display_default),
        ("construction_workers", "시공자", _display_default),
        ("site_extra", "현장 특이사항", _display_site_extra),
    )
    for key, label, formatter in mapping:
        line = _change_line(label, before_shipment.get(key), after_shipment.get(key), formatter)
        if line:
            change_lines.append(line)

    return _order_change_payload(
        event_type="shipment_updated",
        event_title="출고/시공 정보 변경",
        change_lines=change_lines,
        actor_name=actor_name,
    )


def build_payment_confirmation_payload(
    *,
    payment_type: str,
    before_confirmed: Any,
    after_confirmed: Any,
    actor_name: Optional[str] = None,
) -> Dict[str, Any]:
    label = "계약금 확인" if payment_type == "deposit" else "잔금 확인"
    line = _change_line(label, before_confirmed, after_confirmed, _display_confirmed)
    return _order_change_payload(
        event_type="payment_confirmation_changed",
        event_title="결제 확인 변경",
        change_lines=[line] if line else [f"{label}: {_display_confirmed(after_confirmed)}"],
        actor_name=actor_name,
    )

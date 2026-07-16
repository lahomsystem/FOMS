"""ERP Order 변경 → 도면팀 알림·워크벤치 타임라인·목록 배지 SSOT.

실측/CS가 주문 필드를 바꾸면 도면 담당이 모르고 옛 도면을 전달하는 사고를 막는다.
패턴: ``erp_orders_revision`` (history + Notification + fan_out + push + realtime).
"""
from __future__ import annotations

import copy
import datetime as _dt
import json
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from models import Notification, Order
from foms.services.geocode_helpers import extract_address_from_structured_data
from foms.services.orders.erp_policy_constants import STAGE_LABELS, STAGE_NAME_TO_CODE
from foms.services.erp_policy import get_assignee_ids

logger = logging.getLogger(__name__)

NOTIFICATION_TYPE = "ERP_ORDER_CHANGED"
HISTORY_ACTION = "ERP_ORDER_CHANGED"
DEBOUNCE_SECONDS = 60
NOTE_MAX_LEN = 200

_ACTIVE_DRAWING_STATUSES = frozenset(
    {"IN_PROGRESS", "TRANSFERRED", "RETURNED", "CONFIRMED"}
)
_STAGE_RANK = {
    "RECEIVED": 0,
    "MEASURE": 1,
    "DRAWING": 2,
    "CONFIRM": 3,
    "PRODUCTION": 4,
    "CONSTRUCTION": 5,
    "CS": 6,
    "COMPLETED": 7,
}
_ITEM_COMPARE_KEYS = (
    "product_name",
    "width",
    "depth",
    "height",
    "w",
    "d",
    "h",
    "spec_width",
    "spec_depth",
    "spec_height",
    "color",
    "interior",
    "option",
    "handle",
    "material",
    "spec",
    "note",
    "memo",
    "internal",
    "options",
    "spec_rows",
)


def _now_str() -> str:
    """타임라인 at 필드용 로컬 naive 시각 문자열."""
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_history_at(raw: Any) -> Optional[_dt.datetime]:
    """history.at 파싱. 실패 시 None."""
    text = str(raw or "").strip()
    if not text:
        return None
    cleaned = text.replace("Z", "").split(".")[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(cleaned[:19] if "T" in cleaned or " " in cleaned else cleaned[:10], fmt)
        except ValueError:
            continue
    try:
        return _dt.datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _stage_code(sd: dict) -> str:
    """workflow.stage → canonical code (DRAWING 등)."""
    raw = str(((sd or {}).get("workflow") or {}).get("stage") or "").strip()
    if not raw:
        return "RECEIVED"
    if raw in STAGE_LABELS:
        return raw
    mapped = STAGE_NAME_TO_CODE.get(raw)
    if mapped:
        return mapped
    return raw


def _drawing_status(sd: dict) -> str:
    """drawing.status / drawing_status 정규화."""
    drawing = (sd or {}).get("drawing") if isinstance((sd or {}).get("drawing"), dict) else {}
    raw = (drawing.get("status") or (sd or {}).get("drawing_status") or "PENDING")
    return str(raw or "PENDING").strip().upper()


def should_alert_drawing_team(order: Order, sd: dict) -> bool:
    """도면팀 알림 게이트. 미충족이면 history/Notification/목록 배지 전부 생략."""
    if _drawing_status(sd) in _ACTIVE_DRAWING_STATUSES:
        return True
    try:
        if get_assignee_ids(order, "DRAWING_DOMAIN"):
            return True
    except Exception:
        logger.warning("get_assignee_ids failed order=%s", getattr(order, "id", None), exc_info=True)
    rank = _STAGE_RANK.get(_stage_code(sd), -1)
    return rank >= _STAGE_RANK["DRAWING"]


def _norm_scalar(value: Any) -> str:
    """비교용 스칼라 정규화(구조체 금지 — 구조는 format_value_for_display)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        return format_value_for_display(value)
    return str(value).strip()


def format_spec_rows_display(val: Any) -> str:
    """스펙행 사람 표기. JSON 금지 — ``WxDxH`` (복수 행은 `` / ``)."""
    if val is None or val == "":
        return ""
    raw: Any = val
    if isinstance(val, str):
        s = val.strip()
        if not s or s == "(없음)":
            return "" if s != "(없음)" else "(없음)"
        if s.startswith("["):
            try:
                raw = json.loads(s)
            except (TypeError, ValueError, json.JSONDecodeError):
                return s
        else:
            return s
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return _norm_scalar_plain(raw)

    lines: List[str] = []
    for row in raw:
        if not isinstance(row, dict):
            piece = _norm_scalar_plain(row)
            if piece:
                lines.append(piece)
            continue
        w = str(row.get("spec_width") or row.get("w") or row.get("width") or "").strip()
        d = str(row.get("spec_depth") or row.get("d") or row.get("depth") or "").strip()
        h = str(row.get("spec_height") or row.get("h") or row.get("height") or "").strip()
        parts = [p for p in (w, d, h) if p]
        if parts:
            lines.append("x".join(parts))
    return " / ".join(lines)


def _norm_scalar_plain(value: Any) -> str:
    """재귀 없는 스칼라 문자열(format_value_for_display 내부용)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip()


_STRUCT_FIELD_LABELS: Dict[str, str] = {
    "name": "이름",
    "phone": "전화",
    "amount": "금액",
    "raw": "금액",
    "deposit": "계약금",
    "balance": "잔금",
    "total": "합계",
    "method": "결제방법",
    "status": "상태",
    "memo": "메모",
    "note": "비고",
    "text": "내용",
    "special": "특이",
    "remark": "비고",
    "phone_note": "연락처 특이사항",
    "address_note": "주소 특이사항",
    "measurement_note": "실측 특이사항",
    "urgent": "긴급",
    "urgent_reason": "긴급사유",
    "factory2": "2공장",
    "self_measure": "자가실측",
    "special_notes": "특이사항",
    "special_note": "특이사항",
}


def format_value_for_display(val: Any) -> str:
    """변경 이력 from/to 표기 SSOT. JSON·dict/list repr 절대 금지."""
    if val is None:
        return ""
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        s = val.strip()
        if not s or s == "(없음)":
            return s
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                parsed = json.loads(s)
            except (TypeError, ValueError, json.JSONDecodeError):
                return s
            formatted = format_value_for_display(parsed)
            return formatted if formatted else "(구조 변경)"
        return s
    if isinstance(val, list):
        if not val:
            return ""
        # 스펙행 형태면 WxDxH
        if any(
            isinstance(x, dict)
            and any(k in x for k in ("spec_width", "spec_depth", "spec_height", "w", "d", "h", "width", "depth", "height"))
            for x in val
        ):
            spec = format_spec_rows_display(val)
            if spec:
                return spec
        parts = [format_value_for_display(x) for x in val]
        return ", ".join(p for p in parts if p)
    if isinstance(val, dict):
        if not val:
            return ""
        # 단일 치수 dict
        if any(k in val for k in ("spec_width", "spec_depth", "spec_height", "w", "d", "h", "width", "depth", "height")):
            spec = format_spec_rows_display([val])
            if spec:
                return spec
        parts: List[str] = []
        for key, nested in val.items():
            nested_s = format_value_for_display(nested)
            if not nested_s:
                continue
            label = (
                _ITEM_FIELD_LABELS.get(key)
                or _STRUCT_FIELD_LABELS.get(key)
                or str(key)
            )
            parts.append(f"{label} {nested_s}")
        return ", ".join(parts)
    return _norm_scalar_plain(val)


def humanize_change_display_value(label: Any, path: Any, value: Any) -> str:
    """변경 from/to 표시값 — 모든 경로에서 JSON 금지."""
    if value is None:
        return "(없음)"
    text = str(value)
    if not text.strip():
        return "(없음)" if not text else text
    if text == "(없음)":
        return text
    formatted = format_value_for_display(text)
    # format 후에도 JSON 잔존 시 안전 폴백
    stripped = (formatted or "").lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return "(구조 변경)"
    return formatted if formatted else text


def humanize_order_change_changes(
    changes: Optional[Sequence[Any]],
) -> List[Dict[str, str]]:
    """history.changes 표시용 복사본(원본 JSON from/to 를 사람 표기로)."""
    out: List[Dict[str, str]] = []
    for raw in changes or []:
        if not isinstance(raw, dict):
            continue
        row = {
            "path": str(raw.get("path") or ""),
            "label": str(raw.get("label") or ""),
            "from": humanize_change_display_value(
                raw.get("label"), raw.get("path"), raw.get("from")
            ),
            "to": humanize_change_display_value(
                raw.get("label"), raw.get("path"), raw.get("to")
            ),
        }
        out.append(row)
    return out


# forward ref: _ITEM_FIELD_LABELS used above — defined immediately below
_ITEM_FIELD_LABELS: Dict[str, str] = {
    "product_name": "제품명",
    "width": "W(가로)",
    "w": "W(가로)",
    "spec_width": "W(가로)",
    "depth": "D(깊이)",
    "d": "D(깊이)",
    "spec_depth": "D(깊이)",
    "height": "H(높이)",
    "h": "H(높이)",
    "spec_height": "H(높이)",
    "color": "색상",
    "interior": "내부재",
    "internal": "내부재",
    "option": "옵션",
    "options": "옵션",
    "handle": "손잡이",
    "material": "자재",
    "spec": "스펙",
    "note": "항목비고",
    "memo": "항목비고",
    "spec_rows": "스펙행",
}


def _item_snapshot(item: Any) -> Dict[str, str]:
    """제품 행에서 도면 관련 키만 추출(표시·비교용 문자열). JSON 덤프 금지."""
    if not isinstance(item, dict):
        return {"_raw": _norm_scalar(item)}
    out: Dict[str, str] = {}
    for key in _ITEM_COMPARE_KEYS:
        if key in item:
            val = item.get(key)
            if key == "spec_rows":
                out[key] = format_spec_rows_display(val)
            elif isinstance(val, (list, dict)):
                out[key] = format_value_for_display(val)
            else:
                out[key] = _norm_scalar_plain(val)
    if not out:
        out["_raw"] = _norm_scalar(item.get("product_name") or item.get("name") or "항목")
    return out


def _items_fingerprint(sd: dict) -> str:
    """items(+spec_rows) 비교용 fingerprint."""
    items = (sd or {}).get("items") or []
    rows = [_item_snapshot(it) for it in items] if isinstance(items, list) else []
    spec_rows = (sd or {}).get("spec_rows")
    payload = {"items": rows, "spec_rows": spec_rows}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _append_item_field_changes(
    changes: List[Dict[str, str]],
    old_sd: dict,
    new_sd: dict,
) -> None:
    """제품 행별 치수·옵션 before→after를 changes에 추가."""
    old_items = old_sd.get("items") if isinstance(old_sd.get("items"), list) else []
    new_items = new_sd.get("items") if isinstance(new_sd.get("items"), list) else []
    max_n = max(len(old_items), len(new_items))
    for idx in range(max_n):
        old_it = old_items[idx] if idx < len(old_items) else None
        new_it = new_items[idx] if idx < len(new_items) else None
        prefix = f"항목{idx + 1}"
        if old_it is None and isinstance(new_it, dict):
            name = _norm_scalar(new_it.get("product_name")) or f"#{idx + 1}"
            changes.append({
                "path": f"items.{idx}",
                "label": f"{prefix} 추가",
                "from": "(없음)",
                "to": name,
            })
            # 신규 행의 주요 값도 from→to로 남겨 도면팀이 스펙을 바로 본다.
            snap = _item_snapshot(new_it)
            for key, val in snap.items():
                if key.startswith("_") or not val:
                    continue
                label = _ITEM_FIELD_LABELS.get(key, key)
                changes.append({
                    "path": f"items.{idx}.{key}",
                    "label": f"{prefix} {label}",
                    "from": "(없음)",
                    "to": val,
                })
            continue
        if new_it is None and isinstance(old_it, dict):
            name = _norm_scalar(old_it.get("product_name")) or f"#{idx + 1}"
            changes.append({
                "path": f"items.{idx}",
                "label": f"{prefix} 삭제",
                "from": name,
                "to": "(없음)",
            })
            continue
        if not isinstance(old_it, dict) or not isinstance(new_it, dict):
            _add_change(
                changes,
                f"items.{idx}",
                prefix,
                old_it,
                new_it,
            )
            continue
        old_snap = _item_snapshot(old_it)
        new_snap = _item_snapshot(new_it)
        for key in sorted(set(old_snap) | set(new_snap)):
            label_key = _ITEM_FIELD_LABELS.get(key, key if not key.startswith("_") else "내용")
            old_v = old_snap.get(key)
            new_v = new_snap.get(key)
            # 스펙 문자열과 동일하면 스펙행 행은 중복 — 숨김.
            if key == "spec_rows":
                if old_v == old_snap.get("spec") and new_v == new_snap.get("spec"):
                    continue
            _add_change(
                changes,
                f"items.{idx}.{key}",
                f"{prefix} {label_key}",
                old_v,
                new_v,
            )

    old_spec = old_sd.get("spec_rows")
    new_spec = new_sd.get("spec_rows")
    if json.dumps(old_spec, ensure_ascii=False, sort_keys=True, default=str) != json.dumps(
        new_spec, ensure_ascii=False, sort_keys=True, default=str
    ):
        _add_change(
            changes,
            "spec_rows",
            "스펙행",
            format_spec_rows_display(old_spec) or "(없음)",
            format_spec_rows_display(new_spec) or "(없음)",
        )


def _flag_note(sd: dict) -> str:
    """특이사항/비고 계열 플래그·notes 객체 텍스트."""
    parts = []
    flags = (sd or {}).get("flags") if isinstance((sd or {}).get("flags"), dict) else {}
    for key in ("special_notes", "special_note", "memo", "remark", "notes"):
        val = _norm_scalar(flags.get(key))
        if val:
            parts.append(val)
    notes_obj = (sd or {}).get("notes") if isinstance((sd or {}).get("notes"), dict) else {}
    for key in ("address_note", "measurement_note", "memo", "special", "remark", "text"):
        val = _norm_scalar(notes_obj.get(key))
        if val:
            parts.append(val)
    meas = (sd or {}).get("measurement") if isinstance((sd or {}).get("measurement"), dict) else {}
    for key in ("note", "notes", "memo"):
        val = _norm_scalar(meas.get(key))
        if val:
            parts.append(val)
    return " | ".join(parts)


def _add_change(
    changes: List[Dict[str, str]],
    path: str,
    label: str,
    old: Any,
    new: Any,
) -> None:
    """from≠to 이면 changes에 추가. from/to 는 항상 사람 표기(JSON 금지)."""
    old_s = format_value_for_display(old)
    new_s = format_value_for_display(new)
    if old_s == new_s:
        return
    changes.append({
        "path": path,
        "label": label,
        "from": old_s or "(없음)",
        "to": new_s or "(없음)",
    })


def _party_name(sd: dict, *keys: str) -> str:
    """parties 중첩에서 name 추출. keys 예: ('manager',) 또는 ('customer',)."""
    parties = (sd or {}).get("parties") if isinstance((sd or {}).get("parties"), dict) else {}
    cur: Any = parties
    for key in keys:
        if not isinstance(cur, dict):
            return ""
        cur = cur.get(key)
    if isinstance(cur, dict):
        return _norm_scalar(cur.get("name") or cur.get("phone") or "")
    return _norm_scalar(cur)


def _party_phone(sd: dict, key: str) -> str:
    """parties.<key>.phone."""
    parties = (sd or {}).get("parties") if isinstance((sd or {}).get("parties"), dict) else {}
    node = parties.get(key) if isinstance(parties.get(key), dict) else {}
    return _norm_scalar(node.get("phone"))


def _shipment_workers(sd: dict) -> str:
    """시공 담당자 (shipment.construction_workers 또는 parties)."""
    shipment = (sd or {}).get("shipment") if isinstance((sd or {}).get("shipment"), dict) else {}
    val = shipment.get("construction_workers")
    if isinstance(val, list):
        return ", ".join(_norm_scalar(x) for x in val if _norm_scalar(x))
    if val is not None and _norm_scalar(val):
        return _norm_scalar(val)
    return _party_name(sd, "construction") or _party_name(sd, "construction_workers")


def _payment_fingerprint(sd: dict) -> str:
    """결제 블록 비교용."""
    payment = (sd or {}).get("payment")
    if not isinstance(payment, dict):
        return ""
    return json.dumps(payment, ensure_ascii=False, sort_keys=True, default=str)


def _flags_fingerprint(sd: dict) -> str:
    """flags 전체(특이사항 텍스트 포함) 비교용."""
    flags = (sd or {}).get("flags")
    if not isinstance(flags, dict):
        return ""
    return json.dumps(flags, ensure_ascii=False, sort_keys=True, default=str)


def _notes_object_fingerprint(sd: dict) -> str:
    """notes 객체(연락처/주소/실측 비고) 비교용."""
    notes = (sd or {}).get("notes")
    if isinstance(notes, dict):
        return json.dumps(notes, ensure_ascii=False, sort_keys=True, default=str)
    return _norm_scalar(notes)


def compute_drawing_relevant_changes(
    old_sd: dict,
    new_sd: dict,
    *,
    old_notes: Any = None,
    new_notes: Any = None,
    old_is_regional: Any = None,
    new_is_regional: Any = None,
    old_construction_type: Any = None,
    new_construction_type: Any = None,
) -> List[Dict[str, str]]:
    """ERP Order 폼·주문 내용 diff → 도면 타임라인/알림용.

    도면 작업실에는 ERP에서 바뀐 **주문 내용 전부**가 보여야 한다
    (담당자·고객·일정·제품·메모·결제 등).
    제외: drawing/quest/workflow.stage/전달이력 등 운영 전용 JSON
    (단계 변경은 STAGE 전용 경로 유지).
    """
    old_sd = old_sd if isinstance(old_sd, dict) else {}
    new_sd = new_sd if isinstance(new_sd, dict) else {}
    changes: List[Dict[str, str]] = []

    # --- 당사자 ---
    _add_change(
        changes,
        "parties.manager.name",
        "담당자",
        _party_name(old_sd, "manager"),
        _party_name(new_sd, "manager"),
    )
    _add_change(
        changes,
        "parties.customer.name",
        "고객명",
        _party_name(old_sd, "customer"),
        _party_name(new_sd, "customer"),
    )
    _add_change(
        changes,
        "parties.customer.phone",
        "연락처",
        _party_phone(old_sd, "customer"),
        _party_phone(new_sd, "customer"),
    )
    _add_change(
        changes,
        "parties.orderer.name",
        "발주사",
        _party_name(old_sd, "orderer"),
        _party_name(new_sd, "orderer"),
    )
    _add_change(
        changes,
        "shipment.construction_workers",
        "시공 담당자",
        _shipment_workers(old_sd),
        _shipment_workers(new_sd),
    )

    # --- 주소·일정 ---
    _add_change(
        changes,
        "site.address",
        "주소",
        extract_address_from_structured_data(old_sd),
        extract_address_from_structured_data(new_sd),
    )
    old_sched = old_sd.get("schedule") if isinstance(old_sd.get("schedule"), dict) else {}
    new_sched = new_sd.get("schedule") if isinstance(new_sd.get("schedule"), dict) else {}
    old_meas = old_sched.get("measurement") if isinstance(old_sched.get("measurement"), dict) else {}
    new_meas = new_sched.get("measurement") if isinstance(new_sched.get("measurement"), dict) else {}
    old_cons = old_sched.get("construction") if isinstance(old_sched.get("construction"), dict) else {}
    new_cons = new_sched.get("construction") if isinstance(new_sched.get("construction"), dict) else {}
    _add_change(changes, "schedule.measurement.date", "실측일", old_meas.get("date"), new_meas.get("date"))
    _add_change(changes, "schedule.measurement.time", "실측시간", old_meas.get("time"), new_meas.get("time"))
    _add_change(changes, "schedule.construction.date", "시공일", old_cons.get("date"), new_cons.get("date"))
    _add_change(changes, "schedule.construction.time", "시공시간", old_cons.get("time"), new_cons.get("time"))

    # --- 제품/스펙 (필드별 before→after) ---
    _append_item_field_changes(changes, old_sd, new_sd)

    # --- 메모·플래그·결제·지방 ---
    _add_change(changes, "notes", "주문비고", old_notes, new_notes)
    if _notes_object_fingerprint(old_sd) != _notes_object_fingerprint(new_sd):
        # 세부 필드별 표기 (연락처/주소/실측 비고)
        old_notes_obj = old_sd.get("notes") if isinstance(old_sd.get("notes"), dict) else {}
        new_notes_obj = new_sd.get("notes") if isinstance(new_sd.get("notes"), dict) else {}
        for key, label in (
            ("phone_note", "연락처 특이사항"),
            ("address_note", "주소 특이사항"),
            ("measurement_note", "실측 특이사항"),
        ):
            _add_change(
                changes,
                f"notes.{key}",
                label,
                old_notes_obj.get(key) if isinstance(old_notes_obj, dict) else None,
                new_notes_obj.get(key) if isinstance(new_notes_obj, dict) else None,
            )
        # dict가 아니거나 위 키 외 변경만 있으면 묶음
        if not any(c.get("path", "").startswith("notes.") for c in changes):
            _add_change(
                changes,
                "notes.object",
                "비고(상세)",
                old_notes_obj if isinstance(old_notes_obj, dict) else old_sd.get("notes"),
                new_notes_obj if isinstance(new_notes_obj, dict) else new_sd.get("notes"),
            )

    if _flags_fingerprint(old_sd) != _flags_fingerprint(new_sd):
        old_flags = old_sd.get("flags") if isinstance(old_sd.get("flags"), dict) else {}
        new_flags = new_sd.get("flags") if isinstance(new_sd.get("flags"), dict) else {}
        for key, label in (
            ("urgent", "긴급"),
            ("urgent_reason", "긴급사유"),
            ("factory2", "2공장"),
            ("self_measure", "자가실측"),
            ("special_notes", "특이사항"),
            ("special_note", "특이사항"),
        ):
            _add_change(changes, f"flags.{key}", label, old_flags.get(key), new_flags.get(key))
        # 남은 flags 키
        all_keys = set(old_flags) | set(new_flags)
        covered = {
            "urgent", "urgent_reason", "factory2", "self_measure",
            "special_notes", "special_note", "memo", "remark", "notes",
        }
        for key in sorted(all_keys - covered):
            _add_change(changes, f"flags.{key}", f"플래그({key})", old_flags.get(key), new_flags.get(key))

    if _payment_fingerprint(old_sd) != _payment_fingerprint(new_sd):
        changes.append({
            "path": "payment",
            "label": "결제/금액",
            "from": "이전",
            "to": "변경됨",
        })

    _add_change(changes, "is_regional", "지방주문", old_is_regional, new_is_regional)
    _add_change(
        changes,
        "construction_type",
        "지방시공유형",
        old_construction_type,
        new_construction_type,
    )
    return changes


def summarize_changes(changes: Sequence[Dict[str, str]], *, max_len: int = NOTE_MAX_LEN) -> str:
    """타임라인/알림용 한글 요약 (항상 before→after, JSON 금지)."""
    if not changes:
        return ""
    parts = []
    for ch in humanize_order_change_changes(changes):
        label = ch.get("label") or ch.get("path") or "항목"
        from_v = ch.get("from") or "(없음)"
        to_v = ch.get("to") or "(없음)"
        parts.append(f"{label} {from_v}→{to_v}")
    text = " · ".join(parts)
    if len(text) <= max_len:
        return text
    keep = text[: max_len - 12].rstrip(" ·")
    extra = max(0, len(parts) - 1)
    return f"{keep}… 외 {extra}건" if extra else f"{keep}…"


def is_order_change_pending(sd: dict) -> bool:
    """목록/상세 배지용 pending 플래그."""
    drawing = (sd or {}).get("drawing") if isinstance((sd or {}).get("drawing"), dict) else {}
    if bool(drawing.get("order_change_pending")):
        return True
    history = list((sd or {}).get("drawing_transfer_history") or [])
    for entry in reversed(history):
        if not isinstance(entry, dict):
            continue
        if entry.get("action") != HISTORY_ACTION:
            continue
        return not bool(entry.get("acked"))
    return False


def _set_pending_flag(sd: dict, pending: bool) -> None:
    """structured_data.drawing.order_change_pending 설정."""
    drawing = sd.get("drawing")
    if not isinstance(drawing, dict):
        drawing = {}
        sd["drawing"] = drawing
    drawing["order_change_pending"] = bool(pending)


def _merge_change_lists(
    existing: Sequence[Dict[str, str]],
    incoming: Sequence[Dict[str, str]],
) -> List[Dict[str, str]]:
    """path 기준 최신 to로 merge (from은 최초 유지)."""
    by_path: Dict[str, Dict[str, str]] = {}
    for ch in list(existing) + list(incoming):
        if not isinstance(ch, dict):
            continue
        path = str(ch.get("path") or "")
        if not path:
            continue
        prev = by_path.get(path)
        if prev is None:
            by_path[path] = dict(ch)
        else:
            by_path[path] = {
                **prev,
                "to": ch.get("to"),
                "label": ch.get("label") or prev.get("label"),
            }
    return list(by_path.values())


def _find_mergeable_history(
    history: List[Any],
    *,
    actor_user_id: Optional[int],
    now: _dt.datetime,
) -> Optional[int]:
    """60초 debounce merge 대상 history 인덱스. 없으면 None."""
    if not history:
        return None
    idx = len(history) - 1
    last = history[idx]
    if not isinstance(last, dict) or last.get("action") != HISTORY_ACTION:
        return None
    if actor_user_id is not None and last.get("by_user_id") != actor_user_id:
        return None
    last_at = _parse_history_at(last.get("at"))
    if not last_at:
        return None
    if (now - last_at).total_seconds() > DEBOUNCE_SECONDS:
        return None
    return idx


def _find_mergeable_notification(
    db: Session,
    order_id: int,
    *,
    actor_user_id: Optional[int],
    now: _dt.datetime,
) -> Optional[Notification]:
    """동일 order·actor·60초 내 최근 ERP_ORDER_CHANGED 알림."""
    q = (
        db.query(Notification)
        .filter(
            Notification.order_id == order_id,
            Notification.notification_type == NOTIFICATION_TYPE,
        )
        .order_by(Notification.id.desc())
    )
    prev = q.first()
    if prev is None:
        return None
    if actor_user_id is not None and prev.created_by_user_id != actor_user_id:
        return None
    created = prev.created_at
    if created is None:
        return None
    if (now - created).total_seconds() > DEBOUNCE_SECONDS:
        return None
    return prev


def apply_drawing_order_change_alert(
    db: Session,
    order: Order,
    old_sd: dict,
    new_sd: dict,
    *,
    actor_user_id: Optional[int],
    actor_name: str,
    old_notes: Any = None,
    new_notes: Any = None,
    old_is_regional: Any = None,
    new_is_regional: Any = None,
    old_construction_type: Any = None,
    new_construction_type: Any = None,
) -> Tuple[Optional[Notification], bool]:
    """diff·게이트 후 history/pending/Notification 반영.

    ``new_sd`` 를 in-place 수정한다. 호출자가 commit 후
    ``finalize_drawing_order_change_alert`` 를 호출해야 한다.

    Returns:
        (notification_or_None, created_new_bool)
        created_new_bool=False 이면 debounce merge(푸시 재발송 생략 권장).
    """
    if not isinstance(new_sd, dict):
        return None, False

    changes = compute_drawing_relevant_changes(
        old_sd,
        new_sd,
        old_notes=old_notes,
        new_notes=new_notes,
        old_is_regional=old_is_regional,
        new_is_regional=new_is_regional,
        old_construction_type=old_construction_type,
        new_construction_type=new_construction_type,
    )
    if not changes:
        return None, False
    if not should_alert_drawing_team(order, new_sd):
        return None, False

    now = _dt.datetime.now()
    note = summarize_changes(changes)
    # Form PUT may send a stale drawing_transfer_history snapshot — always base on DB old_sd.
    history = list(copy.deepcopy((old_sd or {}).get("drawing_transfer_history") or []))
    merge_idx = _find_mergeable_history(history, actor_user_id=actor_user_id, now=now)

    if merge_idx is not None:
        entry = dict(history[merge_idx])
        merged = _merge_change_lists(entry.get("changes") or [], changes)
        entry["changes"] = merged
        entry["changed_fields"] = [c.get("path") for c in merged if c.get("path")]
        entry["note"] = summarize_changes(merged)
        entry["at"] = _now_str()
        entry["acked"] = False
        entry["by_user_id"] = actor_user_id
        entry["by_user_name"] = actor_name
        history[merge_idx] = entry
        new_sd["drawing_transfer_history"] = history
        _set_pending_flag(new_sd, True)

        notif = _find_mergeable_notification(
            db, int(order.id), actor_user_id=actor_user_id, now=now
        )
        if notif is not None:
            notif.title = "주문 내용 변경 (도면 확인 필요)"
            notif.message = f"주문 #{order.id} — {entry['note']} (변경: {actor_name})"
            return notif, False
        # history만 merge되고 알림 row가 없으면 새로 생성
        note = entry["note"]

    else:
        entry = {
            "action": HISTORY_ACTION,
            "by_user_id": actor_user_id,
            "by_user_name": actor_name,
            "at": _now_str(),
            "note": note,
            "changed_fields": [c.get("path") for c in changes if c.get("path")],
            "changes": list(changes),
            "acked": False,
        }
        history.append(entry)
        new_sd["drawing_transfer_history"] = history
        _set_pending_flag(new_sd, True)

    notif = Notification(
        order_id=int(order.id),
        notification_type=NOTIFICATION_TYPE,
        target_team="DRAWING",
        title="주문 내용 변경 (도면 확인 필요)",
        message=f"주문 #{order.id} — {note} (변경: {actor_name})",
        created_by_user_id=actor_user_id,
        created_by_name=actor_name,
    )
    db.add(notif)
    db.flush()
    from foms.services.notifications.recipients import fan_out_new_notification

    fan_out_new_notification(db, notif, actor_user_id=actor_user_id)
    return notif, True


def finalize_drawing_order_change_alert(
    db: Session,
    notification: Optional[Notification],
    *,
    created_new: bool,
) -> None:
    """commit 이후 push enqueue + realtime emit.

    debounce merge(created_new=False)는 OS push만 생략하고, 배지 invalidate +
    realtime은 유지해 인박스가 즉시 갱신되게 한다.
    """
    if notification is None:
        return
    from foms.api.notifications import (
        invalidate_badge_cache_for_user_ids,
        resolve_notification_recipient_user_ids,
    )
    from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users

    if created_new:
        from foms.services.notifications.push_sender import enqueue_push_for_notification

        enqueue_push_for_notification(notification.id, db=db)

    recipient_user_ids = resolve_notification_recipient_user_ids(
        db,
        target_team="DRAWING",
        target_manager_name=None,
        include_admin=True,
    )
    invalidate_badge_cache_for_user_ids(recipient_user_ids)
    emit_erp_notification_to_users(
        recipient_user_ids,
        {
            "notification_id": notification.id,
            "order_id": notification.order_id,
            "notification_type": NOTIFICATION_TYPE,
            "title": notification.title,
            "message": notification.message,
        },
    )


def ack_drawing_order_change(
    db: Session,
    order: Order,
    *,
    actor_user_id: Optional[int] = None,
    actor_name: str = "",
) -> bool:
    """목록/상세 '확인' — pending 해제 + history acked.

    Returns:
        True if structured_data mutated.
    """
    sd_raw = order.structured_data
    if not isinstance(sd_raw, dict):
        return False
    sd = copy.deepcopy(sd_raw)
    history = list(sd.get("drawing_transfer_history") or [])
    changed = False
    for idx, entry in enumerate(history):
        if not isinstance(entry, dict):
            continue
        if entry.get("action") != HISTORY_ACTION:
            continue
        if bool(entry.get("acked")):
            continue
        updated = dict(entry)
        updated["acked"] = True
        updated["acked_at"] = _now_str()
        if actor_user_id is not None:
            updated["acked_by_user_id"] = actor_user_id
        if actor_name:
            updated["acked_by_name"] = actor_name
        history[idx] = updated
        changed = True
    if is_order_change_pending(sd) or changed:
        sd["drawing_transfer_history"] = history
        _set_pending_flag(sd, False)
        order.structured_data = sd
        flag_modified(order, "structured_data")
        return True
    return False

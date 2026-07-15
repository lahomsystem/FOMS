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
    """비교용 스칼라 정규화."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip()


def _item_snapshot(item: Any) -> Dict[str, str]:
    """제품 행에서 도면 관련 키만 추출."""
    if not isinstance(item, dict):
        return {"_raw": _norm_scalar(item)}
    out: Dict[str, str] = {}
    for key in _ITEM_COMPARE_KEYS:
        if key in item:
            out[key] = _norm_scalar(item.get(key))
    if not out:
        out["_json"] = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
    return out


def _items_fingerprint(sd: dict) -> str:
    """items(+spec_rows) 비교용 fingerprint."""
    items = (sd or {}).get("items") or []
    rows = [_item_snapshot(it) for it in items] if isinstance(items, list) else []
    spec_rows = (sd or {}).get("spec_rows")
    payload = {"items": rows, "spec_rows": spec_rows}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


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
    """from≠to 이면 changes에 추가."""
    old_s = _norm_scalar(old)
    new_s = _norm_scalar(new)
    if old_s == new_s:
        return
    changes.append({
        "path": path,
        "label": label,
        "from": old_s or "(없음)",
        "to": new_s or "(없음)",
    })


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
    """도면에 영향 주는 필드 diff. 빈 리스트면 알림 불필요."""
    old_sd = old_sd if isinstance(old_sd, dict) else {}
    new_sd = new_sd if isinstance(new_sd, dict) else {}
    changes: List[Dict[str, str]] = []

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
    _add_change(changes, "schedule.construction.date", "시공일", old_cons.get("date"), new_cons.get("date"))

    if _items_fingerprint(old_sd) != _items_fingerprint(new_sd):
        changes.append({
            "path": "items",
            "label": "제품/치수/옵션",
            "from": "이전 스펙",
            "to": "변경됨",
        })

    _add_change(changes, "notes", "메모", old_notes, new_notes)
    _add_change(changes, "flags.notes", "특이사항", _flag_note(old_sd), _flag_note(new_sd))
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
    """타임라인/알림용 한글 요약."""
    if not changes:
        return ""
    parts = []
    for ch in changes:
        label = ch.get("label") or ch.get("path") or "항목"
        if ch.get("path") == "items":
            parts.append(f"{label} 변경")
        else:
            parts.append(f"{label} {ch.get('from')}→{ch.get('to')}")
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

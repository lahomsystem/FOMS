"""도면 확정 때 일부 품목 취소 + 최종 생산 도면 고르기 (DRAWING-PARTIAL-CONFIRM).

설계 정본: ``docs/specs/2026-10-12-drawing-confirm-partial-cancel_SPEC.md``.

품목은 배열에서 지우지 않는다 — ``items[].cancel`` 을 붙여 취소를 표시한다(사유·이력 보존).
도면은 지우지 않는다 — 최종본에서 빠진 도면은 ``drawing_excluded_files`` 로 옮긴다
(2026-09-29 "확정은 아무것도 지우지 않는다" 결정 유지).

이 모듈은 순수 계산이다: DB·commit·event 없이 ``structured_data`` dict 만 다룬다.
검증(:func:`plan_partial_confirm`)은 아무것도 바꾸지 않고, 적용(:func:`apply_partial_confirm`)은
호출자가 deepcopy 한 dict 를 제자리에서 고친다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from foms.services.orders.structured_item_uid import item_uid_of

__all__ = [
    "CANCEL_REASONS",
    "CANCEL_SOURCE_AFTER_CONFIRM",
    "CANCEL_SOURCE_DRAWING_CONFIRM",
    "EXCLUDE_REASON_ITEM_CANCELLED",
    "EXCLUDE_REASON_NOT_SELECTED",
    "PartialConfirmError",
    "PartialConfirmPlan",
    "active_items",
    "apply_partial_confirm",
    "build_confirm_result_view",
    "build_ok_scope",
    "cancel_label",
    "drop_cancelled",
    "file_item_uids",
    "cancel_event_payload",
    "is_item_cancelled",
    "plan_after_confirm_cancel",
    "plan_partial_confirm",
    "preserve_item_cancel_state",
]

#: 취소 사유 — 고객 변심 · 기타(메모 필수). 2026-10-12 사용자 결정.
CANCEL_REASONS = ("customer_change", "other")
CANCEL_NOTE_MAX = 200

CANCEL_SOURCE_DRAWING_CONFIRM = "drawing_confirm"
CANCEL_SOURCE_AFTER_CONFIRM = "after_confirm"

EXCLUDE_REASON_ITEM_CANCELLED = "item_cancelled"
EXCLUDE_REASON_NOT_SELECTED = "not_selected"


class PartialConfirmError(ValueError):
    """부분 확정 입력이 계약을 어겼다. ``code`` 는 API 응답 코드, 메시지는 사용자 문구."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class PartialConfirmPlan:
    """검증을 통과한 부분 확정 계획."""

    final_keys: list[str]
    excluded: list[dict[str, Any]] = field(default_factory=list)
    cancels: list[dict[str, Any]] = field(default_factory=list)

    @property
    def cancelled_uids(self) -> list[str]:
        return [c["uid"] for c in self.cancels]


def is_item_cancelled(item: Any) -> bool:
    """품목에 취소 표시(``cancel`` dict)가 있는가."""
    return isinstance(item, dict) and isinstance(item.get("cancel"), dict)


def drop_cancelled(items: Any) -> list[Any]:
    """품목 목록에서 취소 품목만 뺀다(순서·나머지 항목 그대로). 목록이 아니면 빈 목록."""
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return []
    return [it for it in items if not is_item_cancelled(it)]


def active_items(structured_data: Any) -> list[dict[str, Any]]:
    """취소되지 않은 품목 목록(생산·출고·일정·안내 대상). 형식이 아니면 빈 목록.

    ``items`` 가 비면 옛 별칭(``products``·``product_items``)을 본다 — 생산 표시와 같은 규칙.
    """
    sd = structured_data if isinstance(structured_data, dict) else {}
    items = sd.get("items") or sd.get("products") or sd.get("product_items") or []
    return [it for it in drop_cancelled(items) if isinstance(it, dict)]


def _file_key(entry: Any) -> str:
    return str(entry.get("key") or "").strip() if isinstance(entry, dict) else ""


def _explicit_item_uids(entry: dict[str, Any]) -> list[str]:
    raw = entry.get("item_uids")
    if not isinstance(raw, list):
        return []
    return [u.strip() for u in raw if isinstance(u, str) and u.strip()]


def _wizard_sheet_item_uid(sd: dict[str, Any], sheet_id: Any) -> str | None:
    """마법사 시트(``drawing_wizard.sheets[].id``)의 ``product_index`` → 그 품목 uid.

    마법사는 제품 칸에서 시트를 만들 때 ``product_index`` 를 시트에 저장한다(wizard.js
    ``currentSheet().product_index``). 품목이 그 뒤 재배열되면 어긋날 수 있어, 인덱스가
    범위 밖이거나 uid 가 없으면 연결하지 않는다(모름 = 자동 제외 안 함 — 안전한 쪽).
    """
    sid = str(sheet_id or "").strip()
    wizard = sd.get("drawing_wizard") if isinstance(sd.get("drawing_wizard"), dict) else {}
    if not sid:
        return None
    for sheet in wizard.get("sheets") or []:
        if not isinstance(sheet, dict) or str(sheet.get("id") or "") != sid:
            continue
        idx = sheet.get("product_index")
        items = sd.get("items") if isinstance(sd.get("items"), list) else []
        if isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(items):
            return item_uid_of(items[idx])
        return None
    return None


def file_item_uids(sd: dict[str, Any], entry: dict[str, Any]) -> list[str]:
    """도면 항목이 묶인 품목 uid 목록 — 명시값(``item_uids``) 우선, 없으면 마법사 시트에서 유도."""
    explicit = _explicit_item_uids(entry)
    if explicit:
        return explicit
    uid = _wizard_sheet_item_uid(sd, entry.get("sheet_id"))
    return [uid] if uid else []


def _parse_cancel_items(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise PartialConfirmError("INVALID_CANCEL_ITEMS", "취소할 제품 목록 형식이 올바르지 않아요.")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise PartialConfirmError("INVALID_CANCEL_ITEMS", "취소할 제품 목록 형식이 올바르지 않아요.")
        uid = str(entry.get("uid") or "").strip()
        reason = str(entry.get("reason") or "").strip()
        note = str(entry.get("note") or "").strip()[:CANCEL_NOTE_MAX] or None
        if not uid:
            raise PartialConfirmError("INVALID_CANCEL_ITEMS", "취소할 제품이 지정되지 않았어요.")
        if reason not in CANCEL_REASONS:
            raise PartialConfirmError("INVALID_CANCEL_REASON", "취소 사유를 골라 주세요.")
        if reason == "other" and not note:
            raise PartialConfirmError("CANCEL_NOTE_REQUIRED", "'기타' 사유는 메모를 적어 주세요.")
        if uid in seen:
            continue
        seen.add(uid)
        out.append({"uid": uid, "reason": reason, "note": note})
    return out


def plan_partial_confirm(
    structured_data: dict[str, Any],
    final_drawing_keys: Any,
    cancel_items: Any,
) -> PartialConfirmPlan | None:
    """부분 확정 입력을 검증해 계획을 만든다. 아무것도 바꾸지 않는다.

    Args:
        structured_data: 주문 ``structured_data``(읽기만).
        final_drawing_keys: 최종 생산 도면 key 목록. ``None`` 이면 전체 도면.
        cancel_items: ``[{uid, reason, note?}]``. ``None``/빈 목록이면 취소 없음.

    Returns:
        두 입력이 모두 비어 있으면 ``None``(기존 확정과 똑같이 동작). 아니면 계획.

    Raises:
        PartialConfirmError: 계약 위반(사용자 문구 포함).
    """
    cancels = _parse_cancel_items(cancel_items)
    if final_drawing_keys is None and not cancels:
        return None

    sd = structured_data if isinstance(structured_data, dict) else {}
    current = [f for f in (sd.get("drawing_current_files") or []) if _file_key(f)]
    current_keys = [_file_key(f) for f in current]

    items = [it for it in (sd.get("items") or []) if isinstance(it, dict)]
    uid_to_item = {item_uid_of(it): it for it in items if item_uid_of(it)}
    for c in cancels:
        item = uid_to_item.get(c["uid"])
        if item is None:
            raise PartialConfirmError("UNKNOWN_ITEM", "이 주문에 없는 제품이에요. 화면을 새로 고쳐 주세요.")
        if is_item_cancelled(item):
            raise PartialConfirmError("ITEM_ALREADY_CANCELLED", "이미 취소된 제품이에요.")

    cancel_uids = {c["uid"] for c in cancels}
    remaining = [it for it in items if not is_item_cancelled(it) and item_uid_of(it) not in cancel_uids]
    if items and not remaining:
        raise PartialConfirmError(
            "NO_ITEMS_LEFT", "생산할 제품이 없어요. 전부 취소라면 주문 취소로 처리해 주세요.")

    if final_drawing_keys is None:
        selected = list(current_keys)
    else:
        if not isinstance(final_drawing_keys, list):
            raise PartialConfirmError("INVALID_FINAL_DRAWINGS", "최종 도면 목록 형식이 올바르지 않아요.")
        wanted = {str(k or "").strip() for k in final_drawing_keys} - {""}
        unknown = wanted - set(current_keys)
        if unknown:
            raise PartialConfirmError(
                "UNKNOWN_DRAWING", "지금 도면 목록에 없는 도면이 있어요. 화면을 새로 고쳐 주세요.")
        selected = [k for k in current_keys if k in wanted]  # 도면 번호 순서 유지

    excluded: list[dict[str, Any]] = []
    final_keys: list[str] = []
    for entry, key in zip(current, current_keys):
        linked = file_item_uids(sd, entry)
        only_cancelled = bool(linked) and all(u in cancel_uids for u in linked)
        if only_cancelled:
            if final_drawing_keys is not None and key in selected:
                raise PartialConfirmError(
                    "CANCELLED_ITEM_DRAWING_SELECTED", "취소한 제품의 도면은 최종 도면에 넣을 수 없어요.")
            excluded.append({"key": key, "reason": EXCLUDE_REASON_ITEM_CANCELLED, "item_uids": linked})
        elif key in selected:
            final_keys.append(key)
        else:
            excluded.append({"key": key, "reason": EXCLUDE_REASON_NOT_SELECTED, "item_uids": linked})

    if current_keys and not final_keys:
        raise PartialConfirmError("NO_FINAL_DRAWING", "공장으로 갈 도면을 하나 이상 골라 주세요.")

    return PartialConfirmPlan(final_keys=final_keys, excluded=excluded, cancels=cancels)


def apply_partial_confirm(
    structured_data: dict[str, Any],
    plan: PartialConfirmPlan,
    *,
    actor_user_id: int | None,
    at_iso: str,
    source: str = CANCEL_SOURCE_DRAWING_CONFIRM,
) -> dict[str, Any]:
    """계획을 ``structured_data`` 에 제자리 적용한다(호출자가 deepcopy 한 dict).

    Returns:
        확정 이력 항목에 붙일 요약 ``{final_drawing_keys, excluded_drawings,
        cancelled_item_uids, estimate_needs_update}``.
    """
    by_uid = {c["uid"]: c for c in plan.cancels}
    for item in structured_data.get("items") or []:
        uid = item_uid_of(item)
        if uid in by_uid:
            c = by_uid[uid]
            item["cancel"] = {
                "at": at_iso, "by_user_id": actor_user_id,
                "reason": c["reason"], "note": c["note"], "source": source,
            }

    current = [f for f in (structured_data.get("drawing_current_files") or []) if _file_key(f)]
    excluded_by_key = {e["key"]: e for e in plan.excluded}
    keep = set(plan.final_keys)
    structured_data["drawing_current_files"] = [f for f in current if _file_key(f) in keep]

    moved = list(structured_data.get("drawing_excluded_files") or [])
    for f in current:
        key = _file_key(f)
        if key in excluded_by_key:
            moved.append(dict(f, excluded_reason=excluded_by_key[key]["reason"], excluded_at=at_iso))
    if moved:
        structured_data["drawing_excluded_files"] = moved

    needs_estimate = bool(plan.cancels)
    if needs_estimate:
        flags = dict(structured_data.get("flags") or {})
        flags["estimate_needs_update"] = True
        structured_data["flags"] = flags

    return {
        "final_drawing_keys": list(plan.final_keys),
        "excluded_drawings": [dict(e) for e in plan.excluded],
        "cancelled_item_uids": plan.cancelled_uids,
        "estimate_needs_update": needs_estimate,
    }


def preserve_item_cancel_state(old_sd: Any, new_sd: Any) -> int:
    """폼 저장이 지운 서버 소유 취소 상태를 되살린다(제자리).

    ERP 폼은 품목·``flags`` 를 통째로 보내므로 ``items[].cancel`` 과
    ``flags.estimate_needs_update`` 를 모른다. ``ensure_item_uids`` **뒤에** 불러 uid 로
    짝짓는다 — 위치로 짝지으면 품목 하나 끼울 때 취소 표시가 옆 품목으로 옮겨 간다.
    클라이언트가 보낸 ``cancel`` 은 믿지 않는다(취소는 전용 API 만 쓴다).

    Returns:
        되살린 품목 취소 수.
    """
    if not isinstance(new_sd, dict):
        return 0
    old = old_sd if isinstance(old_sd, dict) else {}
    old_cancels = {
        item_uid_of(it): it["cancel"]
        for it in (old.get("items") or [])
        if is_item_cancelled(it) and item_uid_of(it)
    }
    restored = 0
    for item in new_sd.get("items") or []:
        if not isinstance(item, dict):
            continue
        prev = old_cancels.get(item_uid_of(item))
        if prev is not None:
            item["cancel"] = dict(prev)
            restored += 1
        else:
            item.pop("cancel", None)

    old_flags = old.get("flags") if isinstance(old.get("flags"), dict) else {}
    new_flags = new_sd.get("flags")
    if isinstance(new_flags, dict):
        if old_flags.get("estimate_needs_update"):
            new_flags["estimate_needs_update"] = True
        else:
            new_flags.pop("estimate_needs_update", None)
    return restored


def cancel_event_payload(plan: PartialConfirmPlan, summary: dict[str, Any]) -> dict[str, Any]:
    """``ITEM_CANCELLED_AT_CONFIRM`` OrderEvent payload."""
    return {
        "domain": "SALES_DOMAIN",
        "cancels": [dict(c) for c in plan.cancels],
        "excluded_drawings": summary["excluded_drawings"],
        "change_method": "API",
        "source_screen": "erp_drawing_workbench",
    }


def _spec_text(item: dict[str, Any]) -> str:
    dims = [str(item.get(k) or item.get(f"spec_{k}") or "").strip() for k in ("width", "depth", "height")]
    size = "×".join(d for d in dims if d)
    qty = str(item.get("quantity") or "").strip()
    return " · ".join(p for p in (size, f"{qty}개" if qty else "") if p)


def build_ok_scope(structured_data: Any) -> dict[str, Any]:
    """확정 창 ①제품 ②최종 생산 도면 칸의 화면값. 템플릿이 ``data-*`` JSON 으로 싣는다.

    ``show`` 는 고를 거리가 있을 때만 참이다(제품 2개+ 또는 도면 2장+). 아니면 확정 창은
    지금 모양 그대로다. uid 가 없는 품목은 취소를 못 고른다(``cancellable=False``).
    """
    sd = structured_data if isinstance(structured_data, dict) else {}
    items = [it for it in (sd.get("items") or []) if isinstance(it, dict)]
    item_rows = [
        {
            "uid": item_uid_of(it) or "",
            "name": str(it.get("product_name") or it.get("name") or f"제품 {i + 1}").strip(),
            "spec": _spec_text(it),
            "cancellable": bool(item_uid_of(it)),
        }
        for i, it in enumerate(items)
        if not is_item_cancelled(it)
    ]
    names = {r["uid"]: r["name"] for r in item_rows if r["uid"]}
    drawings = []
    for no, f in enumerate((f for f in (sd.get("drawing_current_files") or []) if _file_key(f)), start=1):
        key = _file_key(f)
        linked = file_item_uids(sd, f)
        drawings.append({
            "key": key,
            "no": no,
            "filename": str(f.get("filename") or key.rsplit("/", 1)[-1]),
            "view_url": f"/api/files/view/{key}",
            "item_uids": linked,
            "item_names": [names[u] for u in linked if u in names],
        })
    return {
        "show": len(item_rows) > 1 or len(drawings) > 1,
        "items": item_rows,
        "drawings": drawings,
        "reasons": [{"value": "customer_change", "label": "고객 변심"}, {"value": "other", "label": "기타"}],
    }


_REASON_LABELS = {"customer_change": "고객 변심", "other": "기타"}
_EXCLUDE_LABELS = {
    EXCLUDE_REASON_ITEM_CANCELLED: "제품 취소",
    EXCLUDE_REASON_NOT_SELECTED: "최종 도면에서 뺌",
}


def cancel_label(item: Any) -> str:
    """취소 품목의 화면 문구('취소 · 고객 변심', '취소 · 기타(메모)'). 취소가 아니면 빈 문자열."""
    if not is_item_cancelled(item):
        return ""
    c = item["cancel"]
    label = _REASON_LABELS.get(str(c.get("reason") or ""), "취소")
    note = str(c.get("note") or "").strip()
    return f"취소 · {label}" + (f"({note})" if note else "")


def build_confirm_result_view(structured_data: Any) -> dict[str, Any]:
    """확정 뒤 화면값 — 취소 제품·제외 도면·견적 수정 필요. 보일 것이 없으면 ``show=False``."""
    sd = structured_data if isinstance(structured_data, dict) else {}
    cancelled = [
        {"name": str(it.get("product_name") or it.get("name") or "제품").strip(), "label": cancel_label(it)}
        for it in (sd.get("items") or [])
        if is_item_cancelled(it)
    ]
    excluded = []
    for f in sd.get("drawing_excluded_files") or []:
        key = _file_key(f)
        if not key:
            continue
        excluded.append({
            "filename": str(f.get("filename") or key.rsplit("/", 1)[-1]),
            "view_url": f"/api/files/view/{key}",
            "reason": _EXCLUDE_LABELS.get(str(f.get("excluded_reason") or ""), "제외"),
        })
    flags = sd.get("flags") if isinstance(sd.get("flags"), dict) else {}
    estimate = bool(flags.get("estimate_needs_update"))
    # 확정 뒤 취소 후보(§10) — 확정됐고 남은 생산 품목이 2개 이상일 때만(마지막 하나는 주문 취소 몫).
    alive = [it for it in active_items(sd) if item_uid_of(it)]
    active = [
        {"uid": item_uid_of(it), "name": str(it.get("product_name") or it.get("name") or "제품").strip()}
        for it in alive
    ] if sd.get("drawing_status") == "CONFIRMED" and len(alive) > 1 else []
    return {
        "show": bool(cancelled or excluded or estimate or active),
        "active": active,
        "cancelled": cancelled,
        "excluded": excluded,
        "estimate_needs_update": estimate,
    }


EXCLUDE_REASON_ITEM_CANCELLED_AFTER = "item_cancelled_after_confirm"
_EXCLUDE_LABELS[EXCLUDE_REASON_ITEM_CANCELLED_AFTER] = "확정 뒤 제품 취소"


def plan_after_confirm_cancel(structured_data: dict[str, Any], uid: str, reason: Any, note: Any) -> PartialConfirmPlan:
    """확정 뒤 품목 하나 취소 계획(설계서 §10). 그 품목에만 묶인 최종 도면은 제외 대상.

    Raises:
        PartialConfirmError: 확정 전·없는 품목·이미 취소·생산 품목 0개·도면 0장·사유 오류.
    """
    sd = structured_data if isinstance(structured_data, dict) else {}
    if sd.get("drawing_status") != "CONFIRMED":
        raise PartialConfirmError("NOT_CONFIRMED", "도면 확정 뒤에만 쓸 수 있어요. 확정 전에는 확정 창에서 고르세요.")
    cancels = _parse_cancel_items([{"uid": uid, "reason": reason, "note": note}])
    plan = plan_partial_confirm(sd, None, cancels)
    for e in plan.excluded:
        e["reason"] = EXCLUDE_REASON_ITEM_CANCELLED_AFTER
    return plan

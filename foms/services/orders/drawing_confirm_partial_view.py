"""도면 확정 창·확정 뒤 화면값 (DRAWING-PARTIAL-CONFIRM). 순수 계산 — 조회·쓰기 없음.

계산 규칙은 :mod:`foms.services.orders.drawing_confirm_partial` 이 정본이고, 여기는 템플릿이
쓸 모양으로만 바꾼다(파일 500줄 래칫으로 나눴다).
"""
from __future__ import annotations

from typing import Any

from foms.services.orders.drawing_confirm_partial import (
    EXCLUDE_REASON_ITEM_CANCELLED,
    EXCLUDE_REASON_ITEM_CANCELLED_AFTER,
    EXCLUDE_REASON_NOT_SELECTED,
    _file_key,
    _items_by_ref,
    file_item_uids,
    is_item_cancelled,
    item_ref,
)

__all__ = ["build_confirm_result_view", "build_ok_scope", "cancel_label"]


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
    raw = sd.get("items") if isinstance(sd.get("items"), list) else []
    item_rows = [
        {
            "uid": item_ref(raw, i),
            "name": str(it.get("product_name") or it.get("name") or f"제품 {i + 1}").strip(),
            "spec": _spec_text(it),
            "cancellable": True,
        }
        for i, it in enumerate(raw)
        if isinstance(it, dict) and not is_item_cancelled(it)
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
    EXCLUDE_REASON_ITEM_CANCELLED_AFTER: "확정 뒤 제품 취소",
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
    alive = [(ref, it) for ref, it in _items_by_ref(sd).items() if not is_item_cancelled(it)]
    active = [
        {"uid": ref, "name": str(it.get("product_name") or it.get("name") or "제품").strip()}
        for ref, it in alive
    ] if sd.get("drawing_status") == "CONFIRMED" and len(alive) > 1 else []
    return {
        "show": bool(cancelled or excluded or estimate or active),
        "active": active,
        "cancelled": cancelled,
        "excluded": excluded,
        "estimate_needs_update": estimate,
    }

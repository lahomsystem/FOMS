"""도면 작업실 상세 요청사항 칸의 공장 요청 줄 값(설계서 2026-11-25 §2-2 · §10, D4). 순수 계산 — 쿼리 0(이미 든 주문 JSON).

공장 요청(``drawing_fix.requests``, ``from == "factory"``)을 영업 요청과 같은 목록(요청사항 칸) 맨 위에 새 것부터 그린다
(``templates/drawing/partials/workbench_fix_requests.html``). 한 줄 = "수정 요청 · 공장" · 시각 · 요청한 사람 · 대상 도면 칩 ·
"사유: …" · 사진(지금 사진 보기 길 — ``drawing_revision_files.revision_reference_display_rows``) · [반영 완료] · [요청 반려], 반려된 요청은
"반려 · 오도면 · 11/25 16:02 · 사유: …" 기록 줄.

* 상태 표: [반영 완료]를 누른 요청 = "반영 완료"(지금 글 — 초록), 누르지 않은 열린 요청 = "미완료"(지금 글 — 색 있는 표, 회색 아님).
  반려된 요청은 표 대신 기록 줄. 단계가 생산 밖으로 나가 닫힌 요청(``via: stage_exit``)은 [반영 완료]를 안 눌렀으면 표 없이 남는다
  (사실과 맞는 지금 글이 없다 — 새 글은 만들지 않았다).
* 단추: ``can_fix_production_drawing``(도면팀 누구나 + 관리자, 생산 · 시공 단계) 이고 요청이 열려 있을 때만 — [반영 완료] ↔ [완료 해제]
  (영업 요청 줄의 지금 단추 글) · [요청 반려].
"""

from __future__ import annotations

from typing import Any, Optional

from foms.services.datetime_kst import format_datetime_kst
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.files.list_thumb import list_thumb_url
from foms.services.orders.drawing_factory import DRAWING_FIX_KEY
from foms.services.orders.drawing_fix import REQUEST_OPEN, fix_ident, request_checked
from foms.services.orders.drawing_fix_requests import STATE_REJECTED, left_numbers, reject_body
from foms.services.orders.drawing_fix_transfer import can_fix_production_drawing
from foms.services.orders.drawing_key_safety import is_own_order_key
from foms.services.orders.drawing_revision_files import revision_reference_display_rows

_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic", ".heif")


def md_hm(raw: Any) -> str:
    """UTC 시각 → KST "11/25 16:02"(앞 0 없음). 못 읽으면 빈 글."""
    text = format_datetime_kst(raw, "%m/%d %H:%M") if raw else None
    if not text:
        return ""
    month, rest = text.split("/", 1)
    day, hm = rest.split(" ", 1)
    return f"{int(month)}/{int(day)} {hm}"


def _target_chips(order_id: int, request: dict[str, Any], current: dict[str, tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    """대상 도면 칩(영업 요청 줄 ``dw_target_chips`` 와 같은 꼴 ``{no, name, view_url, thumb_url}``) — 지금 도면이면 그 번호 · 이름 ·
    그림, 바뀌어 없으면 적힌 번호만("3번 대상")."""
    stored = dict(zip(request.get("targets") or [], request.get("numbers") or []))
    rows = []
    for ident in request.get("targets") or []:
        hit = current.get(ident)
        if hit is None:
            no = stored.get(ident)
            if isinstance(no, int) and not isinstance(no, bool):
                rows.append({"no": no, "name": "", "view_url": ""})
            continue
        no, entry = hit
        key = str(entry.get("key") or "")
        filename = str(entry.get("filename") or key.rsplit("/", 1)[-1])
        image = filename.lower().endswith(_IMAGE_EXTENSIONS) and is_own_order_key(order_id, key)
        view_url = f"/api/files/view/{key}" if image else ""
        rows.append({"no": no, "name": filename.rsplit(".", 1)[0], "view_url": view_url,
                     "thumb_url": (list_thumb_url(key) or "") if view_url else ""})
    return rows


def _status(request: dict[str, Any]) -> tuple[Optional[str], str]:
    """(상태 표 — ``checked`` · ``open`` · None, 반려 기록 줄)."""
    if request.get("state") == STATE_REJECTED:
        parts = ["반려", str(request.get("rejected_by_name") or "").strip(), md_hm(request.get("rejected_at")),
                 f"사유: {request.get('reject_note') or ''}"]
        return None, " · ".join(p for p in parts if p)
    if request_checked(request):
        return "checked", ""
    return ("open", "") if request.get("state") == REQUEST_OPEN else (None, "")


def _row(order_id: int, sd: Any, request: dict[str, Any], current: dict[str, tuple[int, dict[str, Any]]],
         can_fix: bool) -> dict[str, Any]:
    badge, reject_line = _status(request)
    photos, hidden = revision_reference_display_rows(order_id, request.get("photos"))
    is_open = request.get("state") == REQUEST_OPEN
    checked_by = " · ".join(p for p in (str(request.get("checked_by_name") or "").strip(), md_hm(request.get("checked_at"))) if p)
    return {
        "id": str(request.get("id") or ""), "at_text": md_hm(request.get("at")), "by_name": str(request.get("by_name") or "").strip(),
        "targets": _target_chips(order_id, request, current), "note": str(request.get("note") or ""),
        "photos": photos, "photos_hidden": hidden, "badge": badge, "checked_by": checked_by if badge == "checked" else "",
        "reject_line": reject_line, "can_act": can_fix and is_open, "checked": request_checked(request),
        "reject_body": reject_body(left_numbers(sd, request)) if is_open else "",
    }


def factory_requests_view(order: Any, sd: Any, user: Any) -> list[dict[str, Any]]:
    """요청사항 칸 공장 요청 줄들(새 것부터). 공장 요청이 없으면 빈 목록(칸은 지금 그대로).

    Args:
        order: 주문. sd: 그 주문 ``structured_data``(읽기만). user: 보는 사람(단추 술어).
    """
    table = sd.get(DRAWING_FIX_KEY) if isinstance(sd, dict) else None
    requests = [r for r in (table.get("requests") if isinstance(table, dict) else None) or []
                if isinstance(r, dict) and (r.get("from") or "factory") == "factory" and r.get("id")]
    if not requests:
        return []
    current = {fix_ident(entry): (no, entry) for no, entry in enumerate(resolve_final_drawing_files(sd), 1)}
    can_fix = can_fix_production_drawing(user, order)
    rows = [_row(int(order.id), sd, r, current, can_fix) for r in requests]
    return list(reversed(rows))


__all__ = ["factory_requests_view", "md_hm"]

"""생산 도면 펜 기록 읽기 — 판 · 작업 시트 · 주문 첨부 목록 · 판 설정이 부르는 곳(설계서 2026-11-28 생산 도면 펜 기록
§3-4 · §5-3 · §8 '쿼리' · §9-5 약속 1 ~ 3).

* 쿼리: 부르는 곳마다 **한 번**(``order_id IN (…)`` — 기록 줄 ⟕ 지금 합친 그림 첨부). 기록 원본 ``objects`` 칸은 읽지 않는다
  (버전 · 쓴 사람 · 시각 · 시트 신원 · 도면 번호 · 첨부 key 만). 스위치(:func:`~foms.services.production.pen_record.enabled`)가
  꺼져 있으면 쿼리 0 이고 판 · 시트 · 첨부 목록 응답이 지금과 같다.
* 판 카드(약속 1): ``note`` = ``{version, by, at, view_url}`` 또는 None, ``note_old`` = 지금 기록은 없는데 같은 ``sheet_id``(그 장에
  시트 신원이 없으면 같은 도면 번호)의 **바뀌기 전 기록**(key 가 지금 확정 도면에 없는 줄)이 있으면 True.
* 판 설정(약속 2): :func:`pen_config` — 켜짐 = ``{"pen": {on, can_write, first}}``, 꺼짐 = 빈 dict(``pen`` 키가 없다).
* 작업 시트(약속 3): 장마다 같은 ``note``. '생산 기록 먼저 보기'를 켠 사람에게는 그 장의 큰 그림 주소(``view``)를 합친 그림으로.
* 주문 첨부 목록(§5-3): '생산' 분류 그림이 있을 때만 그 주문 기록 줄을 한 번 읽어, 지금 확정 도면에 없는 key 의 기록이 가리키는
  그림에 ``production_old`` · ``production_label`` "생산 · 바뀌기 전"을 싣는다.
* ``view_url`` = 첨부 · 도면 그림이 쓰는 길 그대로(``/api/files/view/<key>`` — 로그인 + 그 주문 읽기 범위, 지운 표시된 그림은 404).
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.production import pen_record
from models import OrderAttachment, ProductionDrawingNote

#: 주문 첨부 목록에서 바뀌기 전 생산 기록 그림에 붙이는 글(§5-3).
OLD_LABEL = "생산 · 바뀌기 전"
PRODUCTION_CATEGORY = "production"
_KST = datetime.timezone(datetime.timedelta(hours=9))

NoteIndex = dict[int, list[Any]]


def note_view_url(storage_key: Optional[str]) -> str:
    """합친 그림 주소 — 주문 첨부 · 도면 그림과 같은 보기 길(key 가 없으면 빈 글)."""
    key = str(storage_key or "").strip()
    return f"/api/files/view/{key}" if key else ""


def note_at(value: Any) -> str:
    """저장 시각(UTC naive) → 'M/D HH:MM'(KST, 생산 화면 공정 칸과 같은 꼴). 없으면 빈 글."""
    if not isinstance(value, datetime.datetime):
        return ""
    stamp = value if value.tzinfo is not None else value.replace(tzinfo=datetime.timezone.utc)
    local = stamp.astimezone(_KST)
    return f"{local.month}/{local.day} {local.hour:02d}:{local.minute:02d}"


def note_view(head: Any) -> dict[str, Any]:
    """기록 줄 하나(머리 칸만) → 카드 · 시트가 싣는 ``{version, by, at, view_url}``."""
    return {"version": int(head.version), "by": head.updated_by_name or "", "at": note_at(head.updated_at),
            "view_url": note_view_url(getattr(head, "storage_key", None))}


def fetch_note_heads(db: Any, order_ids: Iterable[int]) -> list[Any]:
    """그 주문들 기록 줄의 머리 칸 + 지금 합친 그림 key — 쿼리 한 번(주문이 없으면 0번). ``objects`` 는 안 읽는다.

    첨부 쪽은 바깥 잇기라 그림이 지운 표시된 줄(전역 tombstone 거르기)도 기록 줄은 남는다(``storage_key`` 가 None).
    """
    ids = sorted({int(i) for i in order_ids})
    if not ids:
        return []
    note = ProductionDrawingNote
    return (
        db.query(note.id, note.order_id, note.drawing_key, note.sheet_id, note.drawing_no, note.version,
                 note.attachment_id, note.updated_by_name, note.updated_at, OrderAttachment.storage_key)
        .outerjoin(OrderAttachment, OrderAttachment.id == note.attachment_id)
        .filter(note.order_id.in_(ids))
        .all()
    )


def index_notes(heads: Iterable[Any]) -> NoteIndex:
    """기록 머리 → ``{주문 id: [머리…]}``(주문마다 장 수만큼이라 작다)."""
    out: NoteIndex = {}
    for head in heads:
        out.setdefault(int(head.order_id), []).append(head)
    return out


def board_notes(db: Any, files: dict[int, list[dict[str, Any]]]) -> Optional[NoteIndex]:
    """판(그날들 주문)의 기록 사전 — 스위치 꺼짐이면 None(쿼리 0), 켜짐이면 확정 도면이 있는 주문만 한 번 읽는다(+1).

    Args:
        db: 세션.
        files: ``{주문 id: 확정 도면 항목들}``(판이 이미 푼 값).
    """
    if not pen_record.enabled():
        return None
    return index_notes(fetch_note_heads(db, (oid for oid, entries in files.items() if entries)))


def _is_old_twin(head: Any, entry: dict[str, Any], number: int, current_keys: set[str]) -> bool:
    """바뀌기 전 기록인지 — key 가 지금 확정 도면에 없고, 같은 시트 신원(그 장에 없으면 같은 도면 번호)."""
    if str(head.drawing_key) in current_keys:
        return False
    sheet = str(entry.get("sheet_id") or "")
    if sheet:
        return str(head.sheet_id or "") == sheet
    return head.drawing_no is not None and int(head.drawing_no) == number


def note_fields(index: Optional[NoteIndex], order_id: int, entry: dict[str, Any], number: int,
                current_keys: set[str]) -> dict[str, Any]:
    """카드 · 시트 한 장의 ``note`` · ``note_old``(쿼리 0 — 읽은 사전에서).

    Args:
        index: :func:`board_notes` 의 사전(None = 스위치 꺼짐).
        order_id: 주문 id.
        entry: 지금 확정 도면 항목(``key`` · ``sheet_id``).
        number: 도면 번호(1부터).
        current_keys: 그 주문 지금 확정 도면 key 집합.

    Returns:
        ``{"note": {version, by, at, view_url} 또는 None, "note_old": bool}``.
    """
    heads = (index or {}).get(int(order_id), [])
    key = str(entry.get("key") or "")
    head = next((h for h in heads if str(h.drawing_key) == key), None)
    if head is not None:
        return {"note": note_view(head), "note_old": False}
    return {"note": None, "note_old": any(_is_old_twin(h, entry, number, current_keys) for h in heads)}


def card_note(ctx: dict[str, Any], order_id: int, entry: dict[str, Any], number: int) -> dict[str, Any]:
    """판 카드 한 장의 ``note`` · ``note_old`` — 판 맥락(``notes`` · ``current_keys``)에서."""
    return note_fields(ctx.get("notes"), order_id, entry, number, ctx["current_keys"].get(int(order_id), set()))


def pen_config(user: Any) -> dict[str, Any]:
    """판 설정(``data-foms-parts-config``)에 펼칠 펜 칸 — 꺼짐이면 빈 dict(설정이 지금과 한 글자도 같다).

    Returns:
        켜짐 = ``{"pen": {"on": True, "can_write": 쓰기 문, "first": 먼저 보기}}``.
    """
    if not pen_record.enabled():
        return {}
    return {"pen": {"on": True, "can_write": pen_record.can_write(user), "first": pen_record.sees_note_first(user)}}


def attach_sheet_notes(db: Any, order: Any, user: Any, items: list[dict[str, Any]]) -> None:
    """작업 시트 도면 목록 장마다 ``note``(쿼리 +1 — 켜짐 · 장이 있을 때만). 먼저 보기를 켠 사람은 큰 그림 주소를 합친 그림으로.

    꺼짐이면 장마다 ``note`` None 만 싣는다(쿼리 0 — 템플릿이 그리는 것은 그대로).

    Args:
        db: 세션.
        order: 이미 읽은 주문.
        user: 보는 사람.
        items: ``drawing_files`` 장들(``key`` 를 가진 dict) — 제자리에서 고친다.
    """
    for item in items:
        item["note"] = None
    if not pen_record.enabled() or not items:
        return
    files = resolve_final_drawing_files(order.structured_data or {})
    numbers = {entry["key"]: (n, entry) for n, entry in enumerate(files, 1)}
    index = index_notes(fetch_note_heads(db, [order.id]))
    current = set(numbers)
    first = pen_record.sees_note_first(user)
    for item in items:
        number, entry = numbers.get(str(item.get("key") or ""), (0, {"key": item.get("key")}))
        fields = note_fields(index, int(order.id), entry, number, current)
        item["note"] = fields["note"]
        if first and fields["note"] and fields["note"]["view_url"]:
            item["view"] = fields["note"]["view_url"]


def annotate_production_old(db: Any, order: Any, attachments: list[Any], items: list[dict[str, Any]]) -> None:
    """주문 첨부 목록의 '생산 · 바뀌기 전'(§5-3) — 켜짐이고 '생산' 분류 그림이 있을 때만 기록 줄을 한 번 읽는다(+1).

    바뀌기 전 = 그 그림을 가리키는 기록 줄의 key 가 지금 확정 도면에 없다(도면이 바뀌어 옛 기록이 따로 남은 것 — 4번 답).
    """
    if not pen_record.enabled():
        return
    if not any(str(getattr(a, "category", "") or "").strip().lower() == PRODUCTION_CATEGORY for a in attachments):
        return
    current = {entry["key"] for entry in resolve_final_drawing_files(getattr(order, "structured_data", None) or {})}
    old_ids = {int(h.attachment_id) for h in fetch_note_heads(db, [order.id])
               if h.attachment_id is not None and str(h.drawing_key) not in current}
    for attachment, item in zip(attachments, items):
        if getattr(attachment, "id", None) in old_ids:
            item["production_old"] = True
            item["production_label"] = OLD_LABEL


__all__ = [
    "OLD_LABEL",
    "annotate_production_old",
    "attach_sheet_notes",
    "board_notes",
    "card_note",
    "fetch_note_heads",
    "index_notes",
    "note_at",
    "note_fields",
    "note_view",
    "note_view_url",
    "pen_config",
]

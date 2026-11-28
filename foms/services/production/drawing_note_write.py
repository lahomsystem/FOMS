"""생산 도면 펜 기록 쓰기 — 받는 값 검사 · 합치기 · 저장 · 지우기(설계서 2026-11-28 생산 도면 펜 기록 §3-2 · §3-3 · §6-5 · §8).

API(``foms/api/production/drawing_notes.py``)는 스위치 · 로그인 · 몸 읽기 · tx(커밋 · 되감기)만 하고 여기를 부른다.

저장 한 tx(§8): 쓰기 문(:func:`~foms.services.production.pen_record.can_write`, 403 ``PEN_FORBIDDEN``) → 주문 줄 잠금(``FOR UPDATE`` —
같은 주문의 저장 · 지우기를 줄 세운다) → 살아 있는 ERP 주문 · 읽기 범위(아니면 404) → key 가 지금 확정 도면(409
``DRAWING_NOT_CURRENT``) · 그림 도면(400 ``NOT_AN_IMAGE``) → 버전 견줌(409 ``NOTE_CHANGED`` — 글의 이름 = 그 기록을 마지막에 고친
사람) → 값 검사(400 ``BAD_REQUEST`` · 413 ``NOTE_TOO_LARGE``) → 원본 읽기 + 흰 바탕에 얹고 펜 기록 투명 PNG 를 원본 크기로 맞춰
겹침 → 저장소 ``orders/<주문>/production/`` 에 PNG → 첨부 한 줄('생산' · ``도면2_생산기록.png``) → 같은 도면의 앞 그림은 지운
표시(``deleted_at``) + 파일 지우기 예약(``STORAGE_DELETE`` — 첨부 삭제와 같은 유예 · 같은 dedupe 열쇠라 복구 API 가 되살린다) →
기록 줄 upsert(``version`` +1) → 이벤트 ``PRODUCTION_DRAWING_NOTE_SAVED`` → 감사 한 줄.

지우기(15번 답 "그림도 지움"): 같은 문 · 잠금 · 확정 도면 · 버전 견줌 → 기록 줄 삭제 + 그림 지운 표시 · 지우기 예약 → 이벤트
``PRODUCTION_DRAWING_NOTE_DELETED`` → 감사. 이벤트 payload 는 ``drawing_key`` · ``drawing_no`` · ``version`` · ``count``(기록 개수) ·
``attachment_id`` 만이고 기록 원본은 싣지 않는다.

저장소에 올린 새 그림은 tx 가 되감기면 고아가 된다 — :class:`NoteJob` 이 올린 key 를 모으고 API 가 :func:`discard_uploads` 로 바로 지운다.
"""

from __future__ import annotations

import datetime
import io
import json
import math
from dataclasses import dataclass, field
from typing import Any, Optional

from foms.services.audit_message_display import describe_order_action
from foms.services.datetime_kst import now_utc_naive
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.files.purge_policy import ATTACHMENT_PURGE_GRACE
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.order_mutation_policy import user_can_read_order
from foms.services.orders.revision import lock_order_row
from foms.services.production import pen_record
from foms.services.production.drawing_notes_read import note_at, note_view_url
from foms.services.production.part_board import is_part_thumb_image
from foms.services.production.part_mark_notes import actor_name
from foms.services.production.part_mark_rules import subject_particle
from foms.services.sidefx_outbox import enqueue_side_effect
from foms.services.storage import get_storage
from models import Order, OrderAttachment, OrderEvent, ProductionDrawingNote, SecurityLog

SAVED_EVENT = "PRODUCTION_DRAWING_NOTE_SAVED"
DELETED_EVENT = "PRODUCTION_DRAWING_NOTE_DELETED"
STORAGE_DELETE = "STORAGE_DELETE"

#: 받는 값(§3-2 — 위자드 저장 꼴과 칸 이름이 같다).
NOTE_TYPES = ("pen", "arrow", "text")
INK_COLORS = ("#e11d1d", "#1c62d6", "#000000")
HIGHLIGHT_COLOR, HIGHLIGHT_WIDTH, HIGHLIGHT_OPACITY = "#ffd400", 24, 0.4
STROKE_WIDTHS = (3, 5, 9)
MAX_OBJECTS = 300
MAX_POINTS = 2000  # 한 선의 점(x, y 한 쌍) 수
MAX_NOTE_BYTES = 400 * 1024  # 검사한 기록 원본(빈칸 없는 JSON) 전체
MAX_TEXT_CHARS = 40
FONT_SIZE_RANGE = (8, 200)
COORD_LIMIT = 100_000
BASE_RANGE = (1, 10_000)
#: 펜 기록 투명 PNG(태블릿이 원본 긴 변 · 최대 2,956px 로 그린다) · 원본 그림의 한계.
MAX_INK_BYTES = 10 * 1024 * 1024  # 플랫폼 본문 캡(request_limits ``pen_note``)이 이보다 크다
MAX_INK_SIDE = 4096
MAX_BASE_PIXELS = 40_000_000

MESSAGES = {
    "PEN_FORBIDDEN": "펜 기록은 정해진 사람만 쓸 수 있어요.",
    "DRAWING_NOT_CURRENT": "도면이 바뀌었어요. [다시 받기]를 눌러 주세요.",
    "NOT_AN_IMAGE": "그림 도면에만 적을 수 있어요.",
    "NOTE_TOO_LARGE": "기록이 너무 많아요. 조금 지우고 다시 저장해 주세요.",
    "BAD_REQUEST": "보낸 값이 올바르지 않아요.",
    "SAVE_FAILED": "저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.",
    "NOT_FOUND": "주문을 찾을 수 없어요.",
}
_STATUS = {"PEN_FORBIDDEN": 403, "DRAWING_NOT_CURRENT": 409, "NOT_AN_IMAGE": 400, "NOTE_TOO_LARGE": 413,
           "BAD_REQUEST": 400, "SAVE_FAILED": 500, "NOT_FOUND": 404, "NOTE_CHANGED": 409}


def changed_message(name: Optional[str]) -> str:
    """409 ``NOTE_CHANGED`` 글 — 이름 자리는 그 기록을 마지막에 고친 사람(모르면 "다른 사람")."""
    return f"그사이 {subject_particle(str(name or '').strip() or '다른 사람')} 기록을 고쳤어요. 닫고 다시 열어 주세요."


class NoteRefusal(Exception):
    """요청을 거절하는 까닭(상태 · 코드 · 글) — API 가 ``{success: false, data: {code}, error: 글}`` 로 바꾼다."""

    def __init__(self, code: str, message: Optional[str] = None) -> None:
        self.code, self.status = code, _STATUS[code]
        self.message = message or MESSAGES[code]
        super().__init__(self.message)


@dataclass
class NoteJob:
    """한 요청 — 주문 · 장 · 본 버전 + (저장만) 기록 원본 · 좌표 기준 · 펜 기록 PNG. ``uploaded`` = 이 요청이 저장소에 올린 key."""

    order_id: int
    key: str
    seen_version: int
    objects: Any = None
    base_w: Any = None
    base_h: Any = None
    ink: bytes = b""
    uploaded: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# 받는 값 검사(§3-2)
# --------------------------------------------------------------------------- #
def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or abs(value) > COORD_LIMIT:
        raise NoteRefusal("BAD_REQUEST")
    return value


def _choice(value: Any, allowed: tuple) -> Any:
    """색(대소문자 무시) · 굵기 값이 허용 목록 안인지 — 목록의 값을 돌려준다."""
    probe = value.strip().lower() if isinstance(value, str) else value
    if isinstance(probe, bool):
        raise NoteRefusal("BAD_REQUEST")
    for item in allowed:
        if probe == item:
            return item
    raise NoteRefusal("BAD_REQUEST")


def _points(value: Any, *, exact: Optional[int] = None) -> list:
    if not isinstance(value, list) or len(value) < 2 or len(value) % 2:
        raise NoteRefusal("BAD_REQUEST")
    if exact is not None and len(value) != exact:
        raise NoteRefusal("BAD_REQUEST")
    if len(value) // 2 > MAX_POINTS:
        raise NoteRefusal("NOTE_TOO_LARGE")
    return [_number(v) for v in value]


def _pen(obj: dict[str, Any]) -> dict[str, Any]:
    """펜 · 형광펜 — 형광펜은 색 ``#ffd400`` · 굵기 24 · 투명 0.4 로만(§6-3 '형광펜은 굵기도 고정')."""
    stroke = _choice(obj.get("stroke"), (*INK_COLORS, HIGHLIGHT_COLOR))
    out = {"type": "pen", "points": _points(obj.get("points")), "stroke": stroke}
    opacity = obj.get("opacity")
    if stroke == HIGHLIGHT_COLOR:
        out["strokeWidth"] = _choice(obj.get("strokeWidth"), (HIGHLIGHT_WIDTH,))
        if opacity is not None and (isinstance(opacity, bool) or not isinstance(opacity, (int, float))
                                    or abs(opacity - HIGHLIGHT_OPACITY) > 1e-6):
            raise NoteRefusal("BAD_REQUEST")
        out["opacity"] = HIGHLIGHT_OPACITY
        return out
    out["strokeWidth"] = _choice(obj.get("strokeWidth"), STROKE_WIDTHS)
    if opacity is not None and (isinstance(opacity, bool) or opacity != 1):
        raise NoteRefusal("BAD_REQUEST")
    return out


def _arrow(obj: dict[str, Any]) -> dict[str, Any]:
    return {"type": "arrow", "points": _points(obj.get("points"), exact=4),
            "stroke": _choice(obj.get("stroke"), INK_COLORS), "strokeWidth": _choice(obj.get("strokeWidth"), STROKE_WIDTHS)}


def _text(obj: dict[str, Any]) -> dict[str, Any]:
    text = obj.get("text").strip() if isinstance(obj.get("text"), str) else ""
    size = _number(obj.get("fontSize"))
    if not text or len(text) > MAX_TEXT_CHARS or not FONT_SIZE_RANGE[0] <= size <= FONT_SIZE_RANGE[1]:
        raise NoteRefusal("BAD_REQUEST")
    return {"type": "text", "x": _number(obj.get("x")), "y": _number(obj.get("y")), "text": text,
            "fill": _choice(obj.get("fill"), INK_COLORS), "fontSize": size}


_CLEANERS = {"pen": _pen, "arrow": _arrow, "text": _text}


def clean_objects(objects: Any) -> list[dict[str, Any]]:
    """기록 원본 검사 — 종류 셋 · 색 넷 · 굵기 넷만 받고, 정한 칸만 남긴 새 목록을 돌려준다(모르는 칸은 버린다).

    Raises:
        NoteRefusal: 꼴이 틀림 · 빈 목록 400 ``BAD_REQUEST``, 300개 · 한 선 2,000점 · 전체 400KB 를 넘음 413 ``NOTE_TOO_LARGE``.
    """
    if not isinstance(objects, list) or not objects:
        raise NoteRefusal("BAD_REQUEST")
    if len(objects) > MAX_OBJECTS:
        raise NoteRefusal("NOTE_TOO_LARGE")
    cleaned = []
    for obj in objects:
        kind = obj.get("type") if isinstance(obj, dict) else None
        if kind not in _CLEANERS:
            raise NoteRefusal("BAD_REQUEST")
        cleaned.append(_CLEANERS[kind](obj))
    if len(json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAX_NOTE_BYTES:
        raise NoteRefusal("NOTE_TOO_LARGE")
    return cleaned


def clean_base(value: Any) -> int:
    """좌표 기준 크기(가로 1478 기준 · 세로는 그림 비율) — 1 ~ 10,000 정수."""
    if isinstance(value, bool) or not isinstance(value, int) or not BASE_RANGE[0] <= value <= BASE_RANGE[1]:
        raise NoteRefusal("BAD_REQUEST")
    return value


# --------------------------------------------------------------------------- #
# 합치기(§3-3)
# --------------------------------------------------------------------------- #
def compose_note_png(raw: bytes, ink: bytes) -> bytes:
    """원본 그림 바이트 + 펜 기록 투명 PNG → 원본 크기 · 흰 바탕 PNG 바이트.

    원본은 EXIF 회전을 풀고 **흰 바탕에 얹는다**(투명 칸이 검정이 되는 함정 — 작은 그림 길과 같은 까닭). 펜 기록은 원본 크기로
    맞춰(크기가 다르면 늘이거나 줄여) 알파로 겹친다(형광펜 0.4 가 그대로 비친다).

    Raises:
        NoteRefusal: 펜 기록이 PNG 가 아니거나 · 너무 큼 400 ``BAD_REQUEST``, 원본을 그림으로 못 읽음 500 ``SAVE_FAILED``.
    """
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(ink)) as source:
            if source.format != "PNG" or max(source.size) > MAX_INK_SIDE:
                raise NoteRefusal("BAD_REQUEST")
            layer = source.convert("RGBA")
    except (OSError, ValueError, Image.DecompressionBombError):
        raise NoteRefusal("BAD_REQUEST") from None
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.size[0] * source.size[1] > MAX_BASE_PIXELS:
                raise NoteRefusal("SAVE_FAILED")
            base = ImageOps.exif_transpose(source).convert("RGBA")
    except (OSError, ValueError, Image.DecompressionBombError):
        raise NoteRefusal("SAVE_FAILED") from None
    canvas = Image.new("RGB", base.size, (255, 255, 255))
    canvas.paste(base, mask=base.getchannel("A"))  # 투명 칸 = 흰색
    del base
    if layer.size != canvas.size:
        layer = layer.resize(canvas.size, Image.Resampling.LANCZOS)
    canvas.paste(layer, mask=layer.getchannel("A"))
    out = io.BytesIO()
    canvas.save(out, "PNG")
    return out.getvalue()


# --------------------------------------------------------------------------- #
# tx 몸통
# --------------------------------------------------------------------------- #
def _locked_entry(db: Any, user: Any, job: NoteJob) -> tuple[Order, dict[str, Any], int]:
    """쓰기 문 → 잠금 → 주문 · 확정 도면 · 그림 도면 검사. ``(주문, 확정 도면 항목, 도면 번호)``."""
    if not pen_record.can_write(user):
        raise NoteRefusal("PEN_FORBIDDEN")
    order = lock_order_row(db, job.order_id)
    if (order is None or order.status == "DELETED" or order.deleted_at is not None or not order.is_erp_order
            or not user_can_read_order(user, order)):
        raise NoteRefusal("NOT_FOUND")
    for number, entry in enumerate(resolve_final_drawing_files(order.structured_data or {}), 1):
        if entry["key"] == job.key:
            if not is_part_thumb_image(entry):
                raise NoteRefusal("NOT_AN_IMAGE")
            return order, entry, number
    raise NoteRefusal("DRAWING_NOT_CURRENT")


def _note_row(db: Any, order_id: int, key: str) -> Optional[ProductionDrawingNote]:
    return db.query(ProductionDrawingNote).filter_by(order_id=order_id, drawing_key=key).one_or_none()


def _compare(row: Optional[ProductionDrawingNote], seen: int) -> None:
    """본 버전(새 기록이면 0)이 지금 값과 다르면 409 — 글의 이름은 그 기록을 마지막에 고친 사람."""
    now = int(row.version) if row is not None else 0
    if now != seen:
        raise NoteRefusal("NOTE_CHANGED", changed_message(row.updated_by_name if row is not None else None))


def winner_message(db: Any, order_id: int, key: str) -> str:
    """동시 첫 저장(유일 제약)에 진 쪽의 409 글 — 되감은 뒤 이긴 줄의 이름을 한 번 읽는다(거절 길만 +1)."""
    name = (db.query(ProductionDrawingNote.updated_by_name)
            .filter_by(order_id=order_id, drawing_key=key).scalar())
    return changed_message(name)


def _retire_picture(db: Any, user: Any, attachment_id: Optional[int], event_id: int, now: datetime.datetime) -> None:
    """앞 그림(또는 지운 기록의 그림)을 지운 표시로 돌리고 파일 지우기를 예약한다(첨부 삭제와 같은 유예 · dedupe 열쇠)."""
    old = db.get(OrderAttachment, attachment_id) if attachment_id else None
    if old is None or old.deleted_at is not None:
        return
    old.deleted_at, old.deleted_by_user_id = now, user.id
    for object_key in (k for k in (old.storage_key, old.thumbnail_key) if k):
        enqueue_side_effect(db, source_domain="ORDER_EVENT", source_id=event_id, effect_type=STORAGE_DELETE,
                            payload={"object_key": object_key, "order_id": int(old.order_id), "attachment_id": int(old.id)},
                            dedupe_key=f"attachment:{old.id}:{object_key}", available_at=now + ATTACHMENT_PURGE_GRACE, now=now)


def _event_and_audit(db: Any, user: Any, order: Order, kind: str, payload: dict[str, Any], note: str,
                     now: datetime.datetime) -> OrderEvent:
    """이벤트 한 줄(기록 원본 없음) + 감사 한 줄 — 같은 tx."""
    event = OrderEvent(order_id=order.id, event_type=kind, payload=payload, created_by_user_id=user.id, created_at=now)
    db.add(event)
    db.flush()
    context = order_audit_context(order)
    db.add(SecurityLog(user_id=user.id, action=kind, target_type="order", target_id=int(order.id),
                       message=describe_order_action(order_id=order.id, action=kind, note=note, **context),
                       detail={**payload, **context}))
    return event


def _store_picture(job: NoteJob, number: int, png: bytes) -> str:
    """합친 그림을 ``orders/<주문>/production/`` 에 올린다(파일 이름은 영문 — 저장소 key 에 한글이 빠지지 않게)."""
    result = get_storage().upload_file(io.BytesIO(png), f"drawing{number}_production.png", f"orders/{job.order_id}/production")
    key = str((result or {}).get("key") or "") if (result or {}).get("success") else ""
    if not key:
        raise NoteRefusal("SAVE_FAILED")
    job.uploaded.append(key)
    return key


def save_note(db: Any, user: Any, job: NoteJob) -> dict[str, Any]:
    """저장 한 tx 의 커밋 전까지(모듈 설명의 순서). 커밋은 API 가 한다.

    Returns:
        ``{"note": {version, view_url, by, at}}``.

    Raises:
        NoteRefusal: 거절(§6-5). sqlalchemy ``IntegrityError``: 동시 첫 저장(API 가 409 ``NOTE_CHANGED`` 로 바꾼다).
    """
    order, entry, number = _locked_entry(db, user, job)
    row = _note_row(db, job.order_id, job.key)
    _compare(row, job.seen_version)
    objects = clean_objects(job.objects)
    base_w, base_h = clean_base(job.base_w), clean_base(job.base_h)
    if not job.ink:
        raise NoteRefusal("BAD_REQUEST")
    raw = get_storage().read_file_bytes(job.key)
    if not raw:
        raise NoteRefusal("SAVE_FAILED")
    png = compose_note_png(raw, job.ink)
    storage_key = _store_picture(job, number, png)
    now, name = now_utc_naive(), actor_name(user)
    picture = OrderAttachment(order_id=order.id, filename=f"도면{number}_생산기록.png", file_type="image", category="production",
                              file_size=len(png), storage_key=storage_key, thumbnail_key=None, user_id=user.id)
    db.add(picture)
    db.flush()
    previous = row.attachment_id if row is not None else None
    values = {"objects": objects, "base_w": base_w, "base_h": base_h, "sheet_id": entry.get("sheet_id"), "drawing_no": number,
              "attachment_id": picture.id, "updated_by_user_id": user.id, "updated_by_name": name, "updated_at": now}
    if row is None:
        row = ProductionDrawingNote(order_id=order.id, drawing_key=job.key, version=1, created_by_user_id=user.id,
                                    created_at=now, **values)
        db.add(row)
    else:
        for column, value in values.items():
            setattr(row, column, value)
        row.version = int(row.version) + 1
    db.flush()  # 동시 첫 저장이면 여기서 유일 제약(IntegrityError)
    payload = {"drawing_key": job.key, "drawing_no": number, "version": int(row.version), "count": len(objects),
               "attachment_id": picture.id}
    event = _event_and_audit(db, user, order, SAVED_EVENT, payload,
                             f"도면 {number} · 기록 {len(objects)}개 · {int(row.version)}번째 저장", now)
    _retire_picture(db, user, previous, event.id, now)
    return {"note": {"version": int(row.version), "view_url": note_view_url(storage_key), "by": name or "", "at": note_at(now)}}


def delete_note(db: Any, user: Any, job: NoteJob) -> dict[str, Any]:
    """기록 지우기 한 tx 의 커밋 전까지 — 기록 줄 삭제 + 그림 지운 표시 · 지우기 예약 + 이벤트 · 감사.

    기록이 없고 본 버전도 0 이면 할 일이 없다(200 · 이벤트 없음). 기록이 없는데 본 버전이 있으면 409(그사이 누가 지웠다).

    Returns:
        ``{"note": None}``.
    """
    order, _entry, number = _locked_entry(db, user, job)
    row = _note_row(db, job.order_id, job.key)
    _compare(row, job.seen_version)
    if row is None:
        return {"note": None}
    now = now_utc_naive()
    count = len(row.objects) if isinstance(row.objects, list) else 0
    payload = {"drawing_key": job.key, "drawing_no": number, "version": int(row.version), "count": count,
               "attachment_id": row.attachment_id}
    attachment_id = row.attachment_id
    db.delete(row)
    event = _event_and_audit(db, user, order, DELETED_EVENT, payload, f"도면 {number} · 기록 {count}개", now)
    _retire_picture(db, user, attachment_id, event.id, now)
    return {"note": None}


def read_note(db: Any, user: Any, order_id: int, key: str) -> dict[str, Any]:
    """쓰기 화면을 열 때 한 번 — 문(생산 첫 화면을 볼 수 있음 · 주문 읽기 범위)은 API 가 본 뒤, 주문 · 확정 도면 · 그림 도면 검사.

    Returns:
        ``{"note": {objects, base_w, base_h, version, by, at} 또는 None}``.
    """
    order = (db.query(Order).filter(Order.id == order_id, Order.active_filter(), Order.is_erp_order.is_(True)).first())
    if order is None or not user_can_read_order(user, order):
        raise NoteRefusal("NOT_FOUND")
    entry = next((e for e in resolve_final_drawing_files(order.structured_data or {}) if e["key"] == key), None)
    if entry is None:
        raise NoteRefusal("DRAWING_NOT_CURRENT")
    if not is_part_thumb_image(entry):
        raise NoteRefusal("NOT_AN_IMAGE")
    row = _note_row(db, order_id, key)
    if row is None:
        return {"note": None}
    return {"note": {"objects": row.objects if isinstance(row.objects, list) else [], "base_w": int(row.base_w),
                     "base_h": int(row.base_h), "version": int(row.version), "by": row.updated_by_name or "",
                     "at": note_at(row.updated_at)}}


def discard_uploads(job: NoteJob) -> None:
    """되감은 요청이 저장소에 올린 그림을 바로 지운다(줄이 없으니 고아 — 실패해도 응답에는 영향 없음)."""
    storage = get_storage()
    for key in job.uploaded:
        storage.delete_file(key)
    job.uploaded.clear()


__all__ = [
    "DELETED_EVENT",
    "MESSAGES",
    "NoteJob",
    "NoteRefusal",
    "SAVED_EVENT",
    "changed_message",
    "clean_base",
    "clean_objects",
    "compose_note_png",
    "delete_note",
    "discard_uploads",
    "read_note",
    "save_note",
    "winner_message",
]

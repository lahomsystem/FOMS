"""시공 메모 한 줄 더하기 — 새 쓰기 길(설계서 2026-11-14-foms-graft 3.3 ``add_construction_note``).

정본 자리는 ``structured_data.notes.construction_note`` 다(주문 폼 '시공 특이사항' 칸 — 출고 화면 · 출고 시트가 읽는다).
글은 가림 검사(:func:`require_masked`)를 지난 한 줄 · :data:`NOTE_LIMIT` 자까지만 받고, 있던 메모 **끝에** 붙인다
(있던 글은 고치지 않는다).

:mod:`.construction_schedule` 의 ``write_construction_schedule`` 과 같은 부품 · 같은 차례다: 깊은 복사 → 고침 → 도면팀
알림(apply) → 대입 → ``flag_modified`` → 납작 칸 맞춤 → 변경 원장. 줄 잠금 · 판 번호 올리기 · 영수증은 REV-00
:func:`execute_single_order_write` 가 맡는다. 감사 줄 · 커밋 · 알림 마무리(:func:`finalize_note_notifications`)는 부르는
쪽(할 일 실행기)이 한다.

``structured_data.notes`` 는 주문 폼에서는 칸 dict 이지만 마법사 · 옛 주문에서는 **글 한 칸**일 수 있다. 글 한 칸이면 칸 dict 로
바꾸면 그 글이 사라지므로 더하지 않는다(:class:`NoteInputError`).
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified

from foms.services.cs_agent.masking import MaskLeak, require_masked
from foms.services.datetime_kst import now_utc_naive
from foms.services.error_logging import log_handled_exception
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.notifications.drawing_order_change import (
    apply_drawing_order_change_alert,
    finalize_drawing_order_change_alert,
)
from foms.services.orders.order_field_change_writer import record_field_changes
from foms.services.orders.revision import execute_single_order_write
from foms.services.orders.structured_diff import diff_structured

__all__ = [
    "NOTE_KEY", "NOTE_LIMIT", "NOTE_SCOPE", "NoteInputError", "NoteWrite", "add_construction_note", "clean_note_line",
    "finalize_note_notifications", "note_lines", "note_problem", "notes_block",
]

#: ``structured_data.notes`` 안 시공 메모 칸 이름.
NOTE_KEY = "construction_note"
#: 한 줄 글 상한(할 일 목록 ``add_construction_note`` 의 넣을 값 상한과 같다).
NOTE_LIMIT = 200
#: REV-00 영수증의 범위 글(정책 표 이름이 아니다 — AS 전이의 ``STATE_AS_*`` 와 같은 쓰임).
NOTE_SCOPE = "CONSTRUCTION_NOTE_ADD"
_TEXT_NOTES = "주문 메모가 글 한 칸이라 시공 메모를 따로 더할 수 없어요 — 주문 화면에서 적어 주세요."


class NoteInputError(ValueError):
    """더할 수 없는 메모(빈 글 · 너무 김 · 가림 검사 걸림 · 메모 칸이 글 한 칸) — 글은 코드가 정한 말만."""


@dataclass
class NoteWrite:
    """쓰기 결과 — 실행기가 감사 · 커밋 · 알림 마무리에 쓴다(글은 담지 않는다)."""

    before_lines: int
    change_set_id: str
    change_count: int
    notifications: list[tuple[str, Any, bool]] = field(default_factory=list)


def clean_note_line(value: Any) -> str:
    """더할 한 줄 — 공백을 하나로 모으고 비지 않고 :data:`NOTE_LIMIT` 자 안이며 가림 검사 0 이어야 한다.

    Raises:
        NoteInputError: 위 조건 가운데 하나라도 어긋남(받은 글은 싣지 않는다).
    """
    text = " ".join(str(value or "").split())
    if not text:
        raise NoteInputError("더할 메모가 비었어요.")
    if len(text) > NOTE_LIMIT:
        raise NoteInputError(f"메모는 {NOTE_LIMIT}자까지예요.")
    try:
        return require_masked(text)
    except MaskLeak as exc:
        raise NoteInputError("손님 정보가 든 글은 메모로 더할 수 없어요.") from exc


def notes_block(sd: Any) -> Optional[dict[str, Any]]:
    """``structured_data.notes`` 칸 dict(없거나 비면 빈 dict). 글 한 칸처럼 dict 가 아닌 값이 들어 있으면 ``None``."""
    notes = sd.get("notes") if isinstance(sd, dict) else None
    if notes is None or (isinstance(notes, str) and not notes.strip()):
        return {}
    return notes if isinstance(notes, dict) else None


def note_lines(sd: Any) -> list[str]:
    """지금 시공 메모의 줄(앞뒤 공백을 뗀 빈 줄 빼고) — 메모 칸이 글 한 칸이면 빈 목록."""
    block = notes_block(sd) or {}
    return [line.strip() for line in str(block.get(NOTE_KEY) or "").splitlines() if line.strip()]


def note_problem(sd: Any, line: Any) -> Optional[str]:
    """이 주문 메모에 이 줄을 더할 수 없는 까닭(정한 말) — 메모 칸이 글 한 칸 · 글 규칙 · 이미 같은 줄. 더할 수 있으면 ``None``."""
    if notes_block(sd) is None:
        return _TEXT_NOTES
    try:
        clean = clean_note_line(line)
    except NoteInputError as exc:
        return str(exc)
    return "이미 같은 메모가 있어요." if clean in note_lines(sd) else None


def _alert_drawing_team(db: Any, order: Any, old_sd: dict, sd: dict, user: Any) -> list[tuple[str, Any, bool]]:
    """도면팀 알림(apply) — 시공일 쓰기와 같은 인자 · 같은 실패 처리(알림 실패가 메모 저장을 막지 않는다)."""
    try:
        notif, created = apply_drawing_order_change_alert(
            db, order, old_sd, sd, actor_user_id=getattr(user, "id", None),
            actor_name=getattr(user, "name", None) or "SYSTEM",
            old_notes=getattr(order, "notes", None), new_notes=getattr(order, "notes", None),
            old_is_regional=getattr(order, "is_regional", None), new_is_regional=getattr(order, "is_regional", None),
            old_construction_type=getattr(order, "construction_type", None),
            new_construction_type=getattr(order, "construction_type", None),
        )
        return [("drawing", notif, created)]
    except Exception:  # noqa: BLE001 — 도면팀 알림 실패가 메모 저장을 막으면 안 된다(시공일 쓰기와 같다)
        log_handled_exception("construction note drawing alert")
        return []


def _apply(db: Any, order: Any, user: Any, line: str) -> NoteWrite:
    """잠근 주문에 한 줄을 붙인다 — 깊은 복사 → 고침 → 도면팀 알림 → 대입 → flag_modified → 납작 칸 → 변경 원장."""
    old_sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    block = notes_block(old_sd)
    if block is None:
        raise NoteInputError(_TEXT_NOTES)
    before = note_lines(old_sd)
    sd = copy.deepcopy(old_sd)
    notes = copy.deepcopy(block)
    existing = str(notes.get(NOTE_KEY) or "").rstrip()
    notes[NOTE_KEY] = f"{existing}\n{line}" if existing else line
    sd["notes"] = notes
    notifications = _alert_drawing_team(db, order, old_sd, sd, user)

    order.structured_data = sd
    flag_modified(order, "structured_data")
    sync_erp_flat_columns(order, sd)
    order.structured_updated_at = now_utc_naive()

    changes = diff_structured(old_sd, sd, max_changes=-1).changes
    change_set_id = str(uuid.uuid4())
    count = record_field_changes(db, changes, order_id=int(order.id), actor_user_id=getattr(user, "id", None),
                                 change_set_id=change_set_id)
    return NoteWrite(before_lines=len(before), change_set_id=change_set_id, change_count=count,
                     notifications=notifications)


def add_construction_note(db: Any, order: Any, user: Any, *, line: Any) -> NoteWrite:
    """주문의 시공 메모 끝에 한 줄을 더한다(커밋 없음 — 감사 · 커밋 · 알림 마무리는 부르는 쪽).

    Args:
        db: 요청 · 작업 세션.
        order: 대상 주문(부르는 쪽이 ``lock_order_row`` 로 잠근 것 — 엔진이 같은 행을 다시 잠그고 판 번호를 올린다).
        user: 쓰는 사람(로그인 사용자) — 변경 원장 · 도면팀 알림의 행위자.
        line: 더할 한 줄(가림 검사를 지나야 한다).

    Returns:
        :class:`NoteWrite` — 변경 묶음 번호 · 원장 줄 수 · 알림 마무리 재료.

    Raises:
        NoteInputError: 글이 규칙을 어기거나 메모 칸이 글 한 칸.
    """
    clean = clean_note_line(line)
    captured: dict[str, NoteWrite] = {}

    def _write(locked: Any) -> None:
        captured["result"] = _apply(db, locked, user, clean)

    execute_single_order_write(db, order_id=int(order.id), actor_user_id=getattr(user, "id", None),
                               policy_id=NOTE_SCOPE, payload={"note": clean}, write=_write)
    return captured["result"]


def finalize_note_notifications(db: Any, result: NoteWrite) -> None:
    """커밋 뒤 — 도면팀 알림 푸시 · 배지(시공일 쓰기의 마무리와 같다). 실패는 기록만."""
    for _kind, notif, created in result.notifications:
        try:
            finalize_drawing_order_change_alert(db, notif, created_new=created)
        except Exception:  # noqa: BLE001 — 커밋은 끝났다, 알림 마무리 실패는 기록만
            log_handled_exception("construction note notify finalize")

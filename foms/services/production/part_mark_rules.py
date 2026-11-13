"""생산 파트 표시의 상태 전이 표 — 순수 계산(설계서 §15.4 '바뀌는 길' · '경합 409').

DB · commit · 요청 없이 표시 줄 하나의 지금 모습(:class:`MarkSnapshot`)과 누름(action · seen)만 보고
'바꾼다 / 이미 그렇다(멱등) / 경합 / 잘못된 요청' 을 정한다. 쓰기 API 가 한 장 쓰기와 일괄 기본에서 같이 쓴다.

바뀌는 길(재단: 안 봄 → 기본 / 안 봄 → 작업 필요 → 끝, 그 밖 파트: 안 고름 → 작업 필요 → 끝):

=======  ==========================  ==============================
action   지금 → 새 상태                조건
=======  ==========================  ==============================
take     없음 · NONE → NEED           맡은 사람 = 나
basic    없음 · NONE → BASIC          재단만(API 가 400 으로 막는다)
done     NEED → DONE                  맡은 사람이 나(관리자는 덮어쓰기)
undo     DONE → NEED / BASIC → NONE   끝낸 사람이 나(관리자는 덮어쓰기)
=======  ==========================  ==============================

같은 사람이 같은 결과를 다시 보내면(연결이 얼어 두 번 누름) 성공으로 친다 — 표의 지금 상태가 곧 멱등 열쇠다.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Optional

from foms.services.production.part_constants import (
    MARK_STATE_BASIC,
    MARK_STATE_DONE,
    MARK_STATE_NEED,
    MARK_STATE_NONE,
)

ACTION_TAKE = "take"
ACTION_BASIC = "basic"
ACTION_DONE = "done"
ACTION_UNDO = "undo"
MARK_ACTIONS: tuple[str, ...] = (ACTION_TAKE, ACTION_BASIC, ACTION_DONE, ACTION_UNDO)

#: 화면이 본 상태(``seen``) — 표 상태의 작은 글자 꼴. 줄이 없으면 ``none``.
SEEN_VALUES: tuple[str, ...] = ("none", "need", "basic", "done")

#: 결정 종류.
DECISION_APPLY = "apply"
DECISION_SAME = "same"
DECISION_CONFLICT = "conflict"
DECISION_INVALID = "invalid"

STALE_MESSAGE = "그사이 다른 사람이 바꿨어요. 다시 받아 주세요."

#: 표 ``production_part_marks`` 의 쓰는 칸(``id`` 제외) — 쓰기 API 가 표마다 한 번에 INSERT/UPDATE 할 때 쓴다.
MARK_COLUMNS: tuple[str, ...] = (
    "order_id", "drawing_key", "sheet_id", "part", "state",
    "picked_by_user_id", "picked_by_name", "picked_at",
    "done_by_user_id", "done_by_name", "done_at",
    "updated_by_user_id", "updated_at",
)


@dataclass(frozen=True)
class MarkSnapshot:
    """표시 줄 하나의 지금 모습(줄이 없으면 :meth:`from_row` 가 NONE 빈 모습을 만든다)."""

    state: str = MARK_STATE_NONE
    picked_by_user_id: Optional[int] = None
    picked_by_name: Optional[str] = None
    done_by_user_id: Optional[int] = None
    done_by_name: Optional[str] = None
    updated_by_user_id: Optional[int] = None

    @classmethod
    def from_row(cls, row: Any) -> "MarkSnapshot":
        """``ProductionPartMark`` 줄(또는 None) → 모습."""
        if row is None:
            return cls()
        return cls(
            state=str(row.state or MARK_STATE_NONE), picked_by_user_id=row.picked_by_user_id,
            picked_by_name=row.picked_by_name, done_by_user_id=row.done_by_user_id,
            done_by_name=row.done_by_name, updated_by_user_id=row.updated_by_user_id,
        )

    @property
    def seen_key(self) -> str:
        """화면 글자 꼴(none · need · basic · done)."""
        return self.state.lower() if self.state in (MARK_STATE_NEED, MARK_STATE_BASIC, MARK_STATE_DONE) else "none"


@dataclass(frozen=True)
class MarkDecision:
    """누름 하나의 결정. ``target`` 은 apply · same 일 때 새 상태, ``override`` 는 관리자가 남의 장을 바꿀 때."""

    kind: str
    target: Optional[str] = None
    override: bool = False
    message: str = ""


def action_target(action: str, seen: str) -> Optional[str]:
    """누름 + 화면이 본 상태 → 새 상태. 표에 없는 짝이면 None(잘못된 요청).

    Args:
        action: take · basic · done · undo.
        seen: 화면이 본 상태(none · need · basic · done).

    Returns:
        새 표 상태(NEED · BASIC · DONE · NONE) 또는 None.
    """
    table = {
        (ACTION_TAKE, "none"): MARK_STATE_NEED,
        (ACTION_BASIC, "none"): MARK_STATE_BASIC,
        (ACTION_DONE, "need"): MARK_STATE_DONE,
        (ACTION_UNDO, "done"): MARK_STATE_NEED,
        (ACTION_UNDO, "basic"): MARK_STATE_NONE,
    }
    return table.get((action, seen))


def _subject(name: str) -> str:
    """이름 뒤 토씨 — 마지막 글자에 받침이 있으면 '이', 없으면 '가'(한글이 아니면 '이')."""
    last = name[-1]
    if "가" <= last <= "힣":
        return "이" if (ord(last) - ord("가")) % 28 else "가"
    return "이"


def conflict_message(snapshot: MarkSnapshot) -> str:
    """경합 409 글 — 지금 주인 이름을 넣은 해요체 한 문장.

    Args:
        snapshot: 서버의 지금 모습.

    Returns:
        "박재단이 먼저 맡았어요" 같은 글. 이름을 모르면 두루 쓰는 글.
    """
    if snapshot.state == MARK_STATE_NEED:
        name, verb = snapshot.picked_by_name, "먼저 맡았어요"
    elif snapshot.state == MARK_STATE_DONE:
        name, verb = snapshot.done_by_name, "먼저 끝냈어요"
    elif snapshot.state == MARK_STATE_BASIC:
        name, verb = snapshot.done_by_name, "먼저 기본으로 했어요"
    else:
        return STALE_MESSAGE
    name = (name or "").strip()
    return f"{name}{_subject(name)} {verb}" if name else f"다른 사람이 {verb}"


def _same_result(snapshot: MarkSnapshot, target: str, actor_id: int) -> bool:
    """이미 그 결과이고 그 결과를 만든 사람이 나인지(멱등).

    작업 필요 = 내가 맡았거나 내가 마지막으로 바꿈(관리자 되돌리기는 맡은 사람을 그대로 둔다) · 기본 · 끝 = 끝낸 사람이 나 ·
    안 봄 = 마지막으로 바꾼 사람이 나.
    """
    if snapshot.state != target:
        return False
    if target == MARK_STATE_NEED:
        return actor_id in (snapshot.picked_by_user_id, snapshot.updated_by_user_id)
    if target in (MARK_STATE_BASIC, MARK_STATE_DONE):
        return snapshot.done_by_user_id == actor_id
    return snapshot.updated_by_user_id == actor_id


def _owner_id(snapshot: MarkSnapshot, action: str) -> Optional[int]:
    """그 누름을 할 수 있는 주인 — 완료는 맡은 사람, 되돌리기는 끝낸 사람. 그 밖은 None(주인 없음)."""
    if action == ACTION_DONE:
        return snapshot.picked_by_user_id
    if action == ACTION_UNDO:
        return snapshot.done_by_user_id
    return None


def decide_mark(snapshot: MarkSnapshot, *, action: str, seen: str, actor_id: int, admin: bool) -> MarkDecision:
    """누름 하나를 표로 판정한다.

    순서: 표에 없는 짝 → invalid · 같은 사람이 같은 결과 → same(멱등) · 지금 ≠ seen → conflict ·
    주인이 남 → conflict(관리자는 apply + override) · 그 밖 apply.

    Args:
        snapshot: 서버의 지금 모습.
        action: take · basic · done · undo.
        seen: 화면이 본 상태.
        actor_id: 누른 사람 id.
        admin: 관리자 덮어쓰기 허용 여부(D55).

    Returns:
        :class:`MarkDecision`.
    """
    target = action_target(action, seen)
    if target is None:
        return MarkDecision(DECISION_INVALID, message="이 상태에서는 그렇게 바꿀 수 없어요.")
    if _same_result(snapshot, target, actor_id):
        return MarkDecision(DECISION_SAME, target=target)
    if snapshot.seen_key != seen:
        return MarkDecision(DECISION_CONFLICT, message=conflict_message(snapshot))
    owner = _owner_id(snapshot, action)
    if owner is not None and owner != actor_id:
        if not admin:
            return MarkDecision(DECISION_CONFLICT, message=conflict_message(snapshot))
        return MarkDecision(DECISION_APPLY, target=target, override=True)
    return MarkDecision(DECISION_APPLY, target=target)


def apply_mark(row: Any, target: str, *, actor_id: int, actor_name: Optional[str], now: datetime.datetime) -> None:
    """표시 줄을 새 상태로 고친다(제자리). 이름은 스냅샷이다(공정 칸 ``by_name`` 과 같은 꼴).

    * NEED(맡기) — 맡은 사람이 비었으면 나로. 되돌리기(DONE → NEED)는 맡은 사람을 그대로 둔다.
    * BASIC · DONE — 끝낸 사람 = 나.
    * NONE(기본 되돌리기) — 맡은 · 끝낸 사람을 모두 비운다.

    Args:
        row: ``ProductionPartMark`` 줄(새 줄 포함).
        target: 새 표 상태.
        actor_id: 누른 사람 id.
        actor_name: 누른 사람 이름.
        now: 쓰는 시각(UTC naive).
    """
    if target == MARK_STATE_NEED:
        if row.state != MARK_STATE_DONE:
            row.picked_by_user_id, row.picked_by_name, row.picked_at = actor_id, actor_name, now
        row.done_by_user_id, row.done_by_name, row.done_at = None, None, None
    elif target in (MARK_STATE_BASIC, MARK_STATE_DONE):
        row.done_by_user_id, row.done_by_name, row.done_at = actor_id, actor_name, now
    else:
        row.picked_by_user_id, row.picked_by_name, row.picked_at = None, None, None
        row.done_by_user_id, row.done_by_name, row.done_at = None, None, None
    row.state = target
    row.updated_by_user_id = actor_id
    row.updated_at = now


def next_mark_values(row: Any, *, order_id: int, drawing_key: str, part: str, sheet_id: Optional[str], target: str,
                     actor_id: int, actor_name: Optional[str], now: datetime.datetime) -> dict[str, Any]:
    """표시 줄 하나의 새 칸 값 전부(줄은 건드리지 않는다 — 쓰기는 부르는 쪽이 표마다 한 번에 한다).

    Args:
        row: 지금 줄(없으면 None — 새 줄).
        order_id: 주문 id.
        drawing_key: 확정 도면 장 key.
        part: 파트 key.
        sheet_id: 지금 확정 도면 항목의 시트 신원(표시할 때의 스냅샷 — 바뀐 도면 짝짓기).
        target: 새 표 상태.
        actor_id: 누른 사람 id.
        actor_name: 누른 사람 이름.
        now: 쓰는 시각(UTC naive).

    Returns:
        :data:`MARK_COLUMNS` 칸 이름 → 값.
    """
    view = SimpleNamespace(**{column: getattr(row, column, None) if row is not None else None for column in MARK_COLUMNS})
    view.order_id, view.drawing_key, view.part, view.sheet_id = order_id, drawing_key, part, sheet_id
    apply_mark(view, target, actor_id=actor_id, actor_name=actor_name, now=now)
    return {column: getattr(view, column) for column in MARK_COLUMNS}


def mark_payload(row: Any) -> dict[str, Any]:
    """응답 · 경합 자료에 싣는 표시 한 장(화면이 그 카드만 서버 상태로 고친다).

    Args:
        row: ``ProductionPartMark`` 줄 또는 None(안 봄 · 안 고름).

    Returns:
        ``{state, picked_by_name, done_by_name, picked_by_user_id, done_by_user_id}`` — state 는 작은 글자 꼴.
    """
    snap = MarkSnapshot.from_row(row)
    return {
        "state": snap.seen_key,
        "picked_by_name": snap.picked_by_name,
        "done_by_name": snap.done_by_name,
        "picked_by_user_id": snap.picked_by_user_id,
        "done_by_user_id": snap.done_by_user_id,
    }

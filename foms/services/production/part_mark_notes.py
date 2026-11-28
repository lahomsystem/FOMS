"""생산 파트 표시 쓰기의 감사 글 · 이벤트 payload(설계서 2026-11-25 multi-holder §8-1 · §8-2 · §3-2) — 순수 계산, 쿼리 0.

``part_mark_write`` 가 500줄 래칫에 닿아 글 만드는 곳을 여기로 옮겼다(뜻은 그대로). 알림 · '바뀐 것' 줄은 만들지 않는다(Q19 —
기록 · 감사만).

* 감사 상태 낱말: 안 봄(재단) · 안 고름 · 작업 필요 · 기본 · "재단 1/2 완료"(같이 작업 중 일부 완료) · "재단 완료".
* 감사 글: 같이 작업 "재단 같이 작업 (이시영 → 이시영 · 김재단)" · 넘김 "재단 같이 작업 (먼저 시작: 이시영)" · 시작 취소
  "재단 시작 취소 (이시영)" · 반장이 남의 시작 취소 "재단 시작 취소 (김재단, 박반장)" · 담당 바꾸기 "재단 담당 바꿈 (박엣지 → 김민준)"
  (K1 그대로) · 반장 · 관리자가 남에게 준 담당 바꾸기 "재단 담당 바꿈 (김재단 → 오재단, 박반장)"(2026-11-28 흐름 셋 §1-5).
  덮어쓰기 꼬리는 관리자 "(관리자 덮어쓰기)", 반장 "(대신 처리)".
* 이벤트 payload: 지금 칸(key · part · from · to · action · override · sheet_id · by_name …) + 목록 전후(``holders_before`` ·
  ``holders_after``) · 대상(``target_name``) · 넘김 표지(``joined_late``) · 담당 바꾸기에서 받은 사람(``to_user_id`` · ``to_name``).
* 쓰기 응답 재료(알람 · 화면이 읽는다 — 흐름 셋 §4-3 약속 1 · 2): :func:`gave_body` · :func:`holders_before`.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from foms.services.production import mark_crew as mc
from foms.services.production.part_constants import BASIC_ALLOWED_PART, MARK_STATE_BASIC, MARK_STATE_DONE, PRODUCTION_PART_LABELS
from foms.services.production.part_mark_rules import (
    ACTION_JOIN,
    ACTION_RELEASE,
    ACTION_REMOVE,
    ACTION_TAKEOVER,
    MarkDecision,
    MarkSnapshot,
)

#: 이름을 모를 때 감사 글 자리(지금 글 그대로).
NO_HOLDER = "담당 없음"


def actor_name(user: Any) -> Optional[str]:
    """이름 스냅샷(표시 줄 · 이벤트 ``by_name`` — 사용자가 지워져도 남는다)."""
    return getattr(user, "name", None) or getattr(user, "username", None)


def state_words(part: str, state: str, crew: Iterable[dict[str, Any]] = ()) -> str:
    """감사 글의 상태 낱말 — 안 봄(재단) · 안 고름 · 작업 필요 · 기본 · "<파트> 1/2 완료" · "<파트> 완료".

    Args:
        part: 파트 key.
        state: 표 상태(NONE · NEED · BASIC · DONE).
        crew: 그 줄의 작업하는 사람 목록(작업 필요인데 일부 완료면 "재단 1/2 완료").
    """
    label = PRODUCTION_PART_LABELS.get(part, part)
    crew = list(crew)
    if state == "NEED":
        done_n = sum(1 for m in crew if mc.is_done(m))
        return f"{label} {done_n}/{len(crew)} 완료" if 0 < done_n < len(crew) else "작업 필요"
    return {"BASIC": "기본", "DONE": f"{label} 완료"}.get(state, "안 봄" if part == BASIC_ALLOWED_PART else "안 고름")


def _brief(crew: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """이벤트에 싣는 목록 줄인 꼴 ``[{uid, name, done}]``."""
    return [{"uid": m.get("uid"), "name": m.get("name"), "done": mc.is_done(m)} for m in crew]


def _member_key(item: dict[str, Any]) -> tuple[Any, Any]:
    """목록 칸 짝짓기 열쇠 — 사람 id(지워진 사용자면 이름)."""
    uid = item.get("uid")
    return (uid, None) if uid is not None else (None, item.get("name"))


def _flipped(before: Iterable[dict[str, Any]], after: Iterable[dict[str, Any]], actor_id: Any = None) -> list[dict[str, Any]]:
    """이번 쓰기로 완료가 바뀐 **남** — 새로 완료가 찍힌 사람(대신 완료), 없으면 완료가 꺼진 사람(대신 되돌리기). 누른 사람 몫(반장이
    같이 작업자면 [대신 완료] · 대상 없는 되돌리기가 자기 몫도 바꾼다)은 '대신'이 아니라 뺀다."""
    was = {_member_key(m): mc.is_done(m) for m in before}
    now = {_member_key(m): mc.is_done(m) for m in after}
    mine = (actor_id, None) if actor_id is not None else None
    finished = [m for m in after if mc.is_done(m) and not was.get(_member_key(m), False) and _member_key(m) != mine]
    return finished or [m for m in before if mc.is_done(m) and not now.get(_member_key(m), False) and _member_key(m) != mine]


def _holder_name(before: MarkSnapshot, decision: Optional[MarkDecision], after: list[dict[str, Any]],
                 actor_id: Any = None) -> Optional[str]:
    """덮어쓰기 이벤트의 '대신' 대상 — 고른 사람(시작 취소 · 바꾸기), 아니면 **이번 쓰기로** 완료가 찍힌 남(이미 완료한 사람 · 누른 사람
    빼고 — "남은 사람 몫을 한 번에 완료" Q15, 바뀐 기록 "박반장 (김재단 대신) 완료") · 완료가 꺼진 남(대신 되돌리기). 이름 줄은 둘까지 +
    "외 n". 사람 없는 줄은 지금 칸 그대로."""
    if decision is not None and decision.target_name:
        return decision.target_name
    people = mc.names(_flipped(before.crew, after, actor_id))
    if people:
        return mc.name_line(people)
    if before.state in (MARK_STATE_DONE, MARK_STATE_BASIC):
        return mc.name_line(mc.done_names(before.crew)) or before.done_by_name
    return mc.name_line(mc.names(before.crew)) or before.picked_by_name


def event_payload(entry: dict[str, Any], before: MarkSnapshot, *, part: str, target: str, user: Any, action: str,
                  override: bool, decision: Optional[MarkDecision] = None,
                  crew_after: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    """이벤트 ``PRODUCTION_PART_MARKED`` payload — 지금 칸 + 3판 칸(§4-11) + 목록 전후 · 대상 · 넘김(multi-holder §3-2).

    Args:
        entry: 확정 도면 항목.
        before: 바뀌기 전 모습.
        part · target · action · override: 파트 · 새 상태 · 실제 누름(넘김 뒤) · 덮어쓰기.
        user: 누른 사람.
        decision: 판정 결정(대상 · 넘김 — 없으면 결정 없이 쓰는 곳: 풀어 쓰기 · 일괄 기본).
        crew_after: 쓴 뒤 목록.
    """
    payload: dict[str, Any] = {"key": entry["key"], "part": part, "from": before.state, "to": target, "action": action,
                               "override": override, "sheet_id": entry.get("sheet_id"), "domain": "PRODUCTION_DOMAIN",
                               "by_name": actor_name(user)}
    after = list(crew_after)
    if action == ACTION_TAKEOVER:
        uid = decision.target_uid if decision is not None and decision.target_uid is not None else before.picked_by_user_id
        name = decision.target_name if decision is not None and decision.target_name else before.picked_by_name
        payload.update(from_user_id=uid, from_name=name, **_receiver(decision, user))
    if override:  # 반장 · 관리자가 남의 몫을 완료 · 시작 취소 · 되돌리기 — 그 전 담당(되돌리기는 완료한 사람)
        payload["holder_name"] = _holder_name(before, decision, after, getattr(user, "id", None))
    if before.crew or after:
        payload.update(holders_before=_brief(before.crew), holders_after=_brief(after))
    if decision is not None and decision.target_name and action in (ACTION_REMOVE, ACTION_RELEASE, ACTION_TAKEOVER):
        payload["target_name"] = decision.target_name
    if decision is not None and decision.joined_late:
        payload["joined_late"] = True
    return payload


def _receiver(decision: Optional[MarkDecision], user: Any) -> dict[str, Any]:
    """담당 바꾸기에서 받은 사람 ``{to_user_id, to_name}`` — 결정이 없거나 받는 사람이 비면 누른 사람(옛 길)."""
    if decision is not None and decision.to_uid is not None:
        return {"to_user_id": decision.to_uid, "to_name": decision.to_name or None}
    return {"to_user_id": getattr(user, "id", None), "to_name": actor_name(user)}


def holders_before(before: MarkSnapshot) -> list[dict[str, Any]]:
    """누르기 전 그 도면 · 파트의 사람 목록 ``[{user_id, name, done}]``(약속 2 — 남의 시작 취소 · 완료 취소 알람이 "누가 빠졌나"를 읽는다)."""
    return [{"user_id": m.get("uid"), "name": m.get("name"), "done": mc.is_done(m)} for m in before.crew]


def gave_body(order_id: int, key: str, part: str, user: Any, decision: MarkDecision) -> dict[str, Any]:
    """담당 바꾸기 쓰기 응답의 ``gave``(약속 1) — ``by`` 누른 사람 · ``from`` 자리를 내준 사람(사람 없는 옛 줄이면 None) · ``to`` 받은
    사람 · ``self`` 누른 사람이 받음. 화면은 ``self`` 가 거짓이면 "오재단에게 줬어요", 알람은 ``to`` · ``from`` 에게 건다."""
    to = _receiver(decision, user)
    source = None
    if decision.target_uid is not None or decision.target_name:
        source = {"user_id": decision.target_uid, "name": decision.target_name or None}
    return {"order_id": order_id, "drawing_key": key, "part": part,
            "by": {"user_id": getattr(user, "id", None), "name": actor_name(user)}, "from": source,
            "to": {"user_id": to["to_user_id"], "name": to["to_name"]},
            "self": to["to_user_id"] == getattr(user, "id", None)}


def _who(names: Iterable[str]) -> str:
    """감사 글의 이름들(모두 — "이시영 · 김재단", 없으면 "담당 없음")."""
    return " · ".join(names) or NO_HOLDER


def mark_note(part: str, action: str, before: MarkSnapshot, target: str, crew_after: Iterable[dict[str, Any]], *,
              user: Any, override: bool, admin_tail: bool, decision: Optional[MarkDecision] = None) -> str:
    """감사 글 한 줄(§8-1 · §8-2 25 · 36). 바뀐 기록 · 감사는 모든 이름을 적는다(Q10 — "외 n" 없이).

    Args:
        part: 파트 key.
        action: 실제 누름(넘김 뒤).
        before: 바뀌기 전 모습.
        target: 새 상태.
        crew_after: 쓴 뒤 목록.
        user: 누른 사람.
        override: 남의 몫을 바꿨는지(꼬리).
        admin_tail: 관리자면 "(관리자 덮어쓰기)", 아니면(반장) "(대신 처리)".
        decision: 판정 결정(대상 · 넘김).
    """
    label = PRODUCTION_PART_LABELS[part]
    after = list(crew_after)
    if action == ACTION_TAKEOVER:
        before_name = (decision.target_name if decision is not None and decision.target_name else before.picked_by_name)
        to = _receiver(decision, user)
        tail = f", {actor_name(user)}" if to["to_user_id"] != getattr(user, "id", None) else ""  # 남에게 줌 — 준 사람을 뒤에
        return f"{label} 담당 바꿈 ({before_name or NO_HOLDER} → {to['to_name'] or NO_HOLDER}{tail})"
    if action == ACTION_REMOVE:
        who = decision.target_name if decision is not None and decision.target_name else NO_HOLDER
        return f"{label} 시작 취소 ({who}, {actor_name(user)})"
    if action == ACTION_JOIN:
        if decision is not None and decision.joined_late:
            return f"{label} 같이 작업 (먼저 시작: {_who(mc.names(before.crew))})"
        return f"{label} 같이 작업 ({_who(mc.names(before.crew))} → {_who(mc.names(after))})"
    if action == ACTION_RELEASE:
        who = decision.target_name if decision is not None and decision.target_name else before.picked_by_name
        note = f"{label} 시작 취소 ({who or NO_HOLDER})"
    else:
        note = f"{label} {state_words(part, before.state, before.crew)} → {state_words(part, target, after)}"
    if not override:
        return note
    return note + (" (관리자 덮어쓰기)" if admin_tail else " (대신 처리)")


__all__ = ["NO_HOLDER", "actor_name", "event_payload", "gave_body", "holders_before", "mark_note", "state_words"]

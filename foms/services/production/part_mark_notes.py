"""생산 파트 표시 쓰기의 감사 글 · 이벤트 payload(설계서 2026-11-25 multi-holder §8-1 · §8-2 · §3-2) — 순수 계산, 쿼리 0.

``part_mark_write`` 가 500줄 래칫에 닿아 글 만드는 곳을 여기로 옮겼다(뜻은 그대로). 알림 · '바뀐 것' 줄은 만들지 않는다(Q19 —
기록 · 감사만).

* 감사 상태 낱말: 안 봄(재단) · 안 고름 · 작업 필요 · 기본 · "재단 1/2 완료"(같이 작업 중 일부 완료) · "재단 완료".
* 감사 글: 같이 작업 "재단 같이 작업 (이시영 → 이시영 · 김재단)" · 넘김 "재단 같이 작업 (먼저 시작: 이시영)" · 시작 취소
  "재단 시작 취소 (이시영)" · 반장이 남의 시작 취소 "재단 시작 취소 (김재단, 박반장)" · 담당 바꾸기 "재단 담당 바꿈 (박엣지 → 김민준)"
  (K1 그대로). 덮어쓰기 꼬리는 관리자 "(관리자 덮어쓰기)", 반장 "(대신 처리)".
* 이벤트 payload: 지금 칸(key · part · from · to · action · override · sheet_id · by_name …) + 목록 전후(``holders_before`` ·
  ``holders_after``) · 대상(``target_name``) · 넘김 표지(``joined_late``).
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


def _holder_name(before: MarkSnapshot, decision: Optional[MarkDecision]) -> Optional[str]:
    """덮어쓰기 이벤트의 그 전 담당(대상을 골랐으면 그 사람, 되돌리기는 완료한 사람)."""
    if decision is not None and decision.target_name:
        return decision.target_name
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
        payload.update(from_user_id=uid, from_name=name)
    if override:  # 반장 · 관리자가 남의 몫을 완료 · 시작 취소 · 되돌리기 — 그 전 담당(되돌리기는 완료한 사람)
        payload["holder_name"] = _holder_name(before, decision)
    if before.crew or after:
        payload.update(holders_before=_brief(before.crew), holders_after=_brief(after))
    if decision is not None and decision.target_name and action in (ACTION_REMOVE, ACTION_RELEASE, ACTION_TAKEOVER):
        payload["target_name"] = decision.target_name
    if decision is not None and decision.joined_late:
        payload["joined_late"] = True
    return payload


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
        return f"{label} 담당 바꿈 ({before_name or NO_HOLDER} → {actor_name(user)})"
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


__all__ = ["NO_HOLDER", "actor_name", "event_payload", "mark_note", "state_words"]

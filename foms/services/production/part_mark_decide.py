"""생산 파트 표시 누름 판정 — 여러 명이 같이 작업하는 줄의 전이(설계서 2026-11-25 multi-holder §5 · §7-3). 순수 계산.

전이 표 · 글 · 모습(:class:`~foms.services.production.part_mark_rules.MarkSnapshot`)은 :mod:`part_mark_rules`, 목록 함수는
:mod:`mark_crew` 다. 여기는 누름 하나를 '바꾼다(새 목록) / 멱등 / 경합 / 거절 / 잘못된 요청' 으로 정하는 차례만 둔다(500줄 래칫 —
``part_mark_rules`` 에서 나눔). 막는 까닭(남의 공장 · 보류 · 도면 고치는 중 · 손 체크 칸 · 검수 순서)은 쓰기 몸통
(``part_mark_write._decide``)이 이 결정과 사이에 끼운다 — §7-3 차례 4 · 5 · 9.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, replace
from typing import Any, Optional

from foms.services.datetime_kst import now_utc_naive
from foms.services.production import mark_crew as mc
from foms.services.production.part_constants import MARK_STATE_BASIC, MARK_STATE_DONE, MARK_STATE_NEED, MARK_STATE_NONE
from foms.services.production.part_mark_rules import (
    ACTION_BASIC,
    ACTION_CHECK,
    ACTION_DONE,
    ACTION_JOIN,
    ACTION_RELEASE,
    ACTION_REMOVE,
    ACTION_TAKE,
    ACTION_TAKEOVER,
    ACTION_UNDO,
    DECISION_APPLY,
    DECISION_CONFLICT,
    DECISION_FORBIDDEN,
    DECISION_INVALID,
    DECISION_REFUSE,
    DECISION_SAME,
    JOIN_DONE,
    JOIN_DONE_MESSAGE,
    NEW_ACTIONS,
    RELEASE_AFTER_DONE,
    RELEASE_AFTER_DONE_MESSAGE,
    RELEASE_NOT_HOLDER,
    RELEASE_NOT_HOLDER_MESSAGE,
    REMOVE_FORBIDDEN,
    REMOVE_FORBIDDEN_MESSAGE,
    SEEN_BY_UNSET,
    STALE_MESSAGE,
    TARGET_DONE,
    TARGET_DONE_MESSAGE,
    TARGET_GONE,
    TARGET_REQUIRED,
    TARGET_REQUIRED_REMOVE,
    TARGET_REQUIRED_SWAP,
    UNDO_NOT_MINE,
    MarkDecision,
    MarkSnapshot,
    action_target,
    conflict_message,
    crew_line,
    holder_changed_message,
    new_action_conflict_message,
    target_gone_message,
    took_first_message,
    undo_not_mine_message,
)


@dataclass(frozen=True)
class _Press:
    """판정 재료 — 누른 사람 · 반장 · 관리자인지 · 시각 · 화면이 보낸 값."""

    actor_id: int
    actor_name: Optional[str]
    admin: bool
    now: datetime.datetime
    seen_by: Any
    seen_me: Optional[str]
    target_uid: Optional[int]
    label: str


def _same_result(snap: MarkSnapshot, action: str, target: str, me: int, target_uid: Optional[int] = None,
                 seen_me: Optional[str] = None) -> bool:
    """이미 그 결과이고 그 결과를 만든 사람이 나인지(멱등 — 연결이 얼어 두 번 누름).

    [작업 시작] · [같이 작업] · 담당 바꾸기 = 내가 이미 목록에 있음, 완료 = 내 몫이 이미 완료(대신 완료 · 사람 없는 완료는 끝낸 사람이
    나), 되돌리기 = 내 몫이 이미 작업 중(화면이 내 몫을 완료로 봤거나 안 보냄 — 내 몫이 작업 중으로 보인 화면의 되돌리기는 남의
    몫이다, 대신 되돌리기는 마지막으로 바꾼 사람이 나), 시작 취소 = 빠질 사람이 이미 없고 마지막으로 바꾼 사람이 나, PC [완료 처리] =
    이미 완료 · 기본.
    """
    crew, state = snap.crew, snap.state
    share = mc.share_of(crew, me)
    if action in (ACTION_TAKE, ACTION_JOIN, ACTION_TAKEOVER):
        return state == MARK_STATE_NEED and share != mc.SHARE_NONE
    if action == ACTION_CHECK:
        return state in (MARK_STATE_DONE, MARK_STATE_BASIC)
    if action == ACTION_DONE:
        return share == mc.SHARE_DONE or (state == MARK_STATE_DONE and snap.done_by_user_id == me)
    if action == ACTION_BASIC:
        return state == MARK_STATE_BASIC and snap.done_by_user_id == me
    if action == ACTION_UNDO and target == MARK_STATE_NEED:
        held = share == mc.SHARE_HELD and seen_me in (None, mc.SHARE_DONE) and target_uid in (None, me)
        return state == MARK_STATE_NEED and (held or (share == mc.SHARE_NONE and snap.updated_by_user_id == me))
    if action in (ACTION_RELEASE, ACTION_REMOVE):
        gone = mc.find(crew, target_uid if target_uid is not None else me) is None
        return gone and snap.updated_by_user_id == me and state != MARK_STATE_BASIC
    return state == target and snap.updated_by_user_id == me


def _seen_by_ok(snap: MarkSnapshot, seen_by: Any) -> bool:
    """옛 화면이 본 담당 id — 한 명(이하)일 때는 지금 담당과 같아야, 여럿이면 그중 한 사람이어야."""
    if len(snap.crew) <= 1:
        return snap.picked_by_user_id == seen_by
    return mc.find(snap.crew, seen_by) is not None


def _applied(crew: list[dict[str, Any]], action: str, *, empty_state: str = MARK_STATE_NONE, **extra: Any) -> MarkDecision:
    """쓰기 결정 — 새 상태 = 목록의 요약(비면 ``empty_state`` — 사람 없는 줄은 지금 규칙)."""
    summary = mc.summarize(crew)
    target = summary["state"] if summary is not None else empty_state
    return MarkDecision(DECISION_APPLY, target=target, action=action, crew=tuple(crew), **extra)


def _refuse(code: str, message: str, status: int = 409, **extra: Any) -> MarkDecision:
    """거절 결정(409 · 400 — 막는 까닭 뒤에 낸다)."""
    return MarkDecision(DECISION_REFUSE, message=message, code=code, status=status, **extra)


def _forbid(code: str, message: str) -> MarkDecision:
    """권한 거절 결정(403)."""
    return MarkDecision(DECISION_FORBIDDEN, message=message, code=code, status=403)


def _pick_target(crew: list[dict[str, Any]], target_uid: Optional[int]) -> tuple[Optional[dict[str, Any]], bool]:
    """바꾸기 · 시작 취소 대상 — 고른 사람(목록에 없으면 ``(None, True)`` = 빠짐), 안 골랐으면 아직 완료 안 한 사람이 하나일 때만.

    Returns:
        (대상 칸 또는 None, 고른 사람이 빠졌는지).
    """
    if target_uid is not None:
        item = mc.find(crew, target_uid)
        return item, item is None
    pending = [m for m in crew if not mc.is_done(m)]
    if len(crew) == 1:
        return crew[0], False
    return (pending[0] if len(pending) == 1 else None), False


def _decide_done(snap: MarkSnapshot, p: _Press) -> MarkDecision:
    """[재단 완료] — 내 몫 완료(모두 완료면 DONE) · 반장 · 관리자는 남은 사람 몫을 한 번에(Q15) · 목록 밖 파트 계정은 경합."""
    crew = list(snap.crew)
    if mc.share_of(crew, p.actor_id) == mc.SHARE_HELD:
        return _applied(mc.finish(crew, p.actor_id, by_uid=p.actor_id, by_name=p.actor_name, now=p.now), ACTION_DONE)
    if not crew:  # 담당 없는 작업 필요 줄(사람 없는 완료를 되돌린 줄) — 지금처럼 누른 사람이 완료
        return _applied([], ACTION_DONE, empty_state=MARK_STATE_DONE)
    if p.admin:  # 대신 완료 — 남은 사람 몫을 한 번에(Q15)
        return _applied(mc.finish_rest(crew, by_uid=p.actor_id, by_name=p.actor_name, now=p.now), ACTION_DONE, override=True)
    return MarkDecision(DECISION_CONFLICT, message=conflict_message(snap), action=ACTION_DONE)


def _decide_undo(snap: MarkSnapshot, p: _Press, seen: str) -> MarkDecision:
    """[되돌리기] — 재단 기본은 지금 그대로, 그 밖은 본인 몫만(Q3 · Q4) · 반장 · 관리자는 남의 완료 몫(고른 사람 또는 모두)."""
    crew = list(snap.crew)
    if seen == "basic":  # 재단 기본 되돌리기 — 지금 그대로
        owner = snap.done_by_user_id
        if owner is not None and owner != p.actor_id and not p.admin:
            return MarkDecision(DECISION_CONFLICT, message=conflict_message(snap))
        return _applied([], ACTION_UNDO, override=owner is not None and owner != p.actor_id)
    own = p.target_uid is None or p.target_uid == p.actor_id
    if own and mc.share_of(crew, p.actor_id) == mc.SHARE_DONE:  # 본인 몫만(Q3 · Q4)
        return _applied(mc.unfinish(crew, [p.actor_id]), ACTION_UNDO)
    others = [m for m in crew if mc.is_done(m) and m.get("uid") != p.actor_id
              and (p.target_uid is None or m.get("uid") == p.target_uid)]
    if others:
        if not p.admin:
            return _forbid(UNDO_NOT_MINE, undo_not_mine_message(mc.name_sentence(mc.done_names(others))))
        return _applied(mc.unfinish(crew, [m.get("uid") for m in others]), ACTION_UNDO, override=True)
    if not crew and snap.state == MARK_STATE_DONE:  # 사람 없는 완료(풀어 쓴 완료 · 옛 줄)
        owner = snap.done_by_user_id
        if owner is not None and owner != p.actor_id and not p.admin:
            return _forbid(UNDO_NOT_MINE, undo_not_mine_message((snap.done_by_name or "").strip()))
        return _applied([], ACTION_UNDO, empty_state=MARK_STATE_NEED, override=owner is not None and owner != p.actor_id)
    return MarkDecision(DECISION_CONFLICT, message=STALE_MESSAGE)


def _leave(crew: list[dict[str, Any]], item: dict[str, Any], action: str, **extra: Any) -> MarkDecision:
    """한 사람을 뺀 결정 — 남은 사람 0 = NONE, 남은 사람 모두 완료 = 저절로 DONE(Q6), 그 밖 NEED."""
    return _applied(mc.leave(crew, item.get("uid")), action, target_uid=item.get("uid"),
                    target_name=str(item.get("name") or ""), **extra)


def _decide_release(snap: MarkSnapshot, p: _Press) -> MarkDecision:
    """[시작 취소] — 나 빼기(완료 뒤는 409 — Q7). 반장 · 관리자가 남의 장을 누르면(옛 화면) 고른 사람 빼기, 파트 계정은 403."""
    crew = list(snap.crew)
    mine = mc.find(crew, p.actor_id)
    if mine is not None:
        if mc.is_done(mine):
            return _refuse(RELEASE_AFTER_DONE, RELEASE_AFTER_DONE_MESSAGE.format(label=p.label))
        return _leave(crew, mine, ACTION_RELEASE)
    if not crew:  # 담당 없는 작업 필요 줄 — 지금처럼 안 봄으로
        return _applied([], ACTION_RELEASE)
    if not p.admin:
        return _forbid(RELEASE_NOT_HOLDER, RELEASE_NOT_HOLDER_MESSAGE)
    return _remove_one(crew, p, ACTION_RELEASE)


def _remove_one(crew: list[dict[str, Any]], p: _Press, action: str) -> MarkDecision:
    """반장 · 관리자가 고른 사람의 시작을 취소(옛 화면의 남의 장 [맡기 취소]도 여기 — 한 명이면 그 사람)."""
    item, gone = _pick_target(crew, p.target_uid)
    if gone:
        return _refuse(TARGET_GONE, target_gone_message(""), target_uid=p.target_uid)
    if item is None:
        return _refuse(TARGET_REQUIRED, TARGET_REQUIRED_REMOVE, status=400)
    if mc.is_done(item):
        return _refuse(RELEASE_AFTER_DONE, RELEASE_AFTER_DONE_MESSAGE.format(label=p.label))
    return _leave(crew, item, action, override=item.get("uid") != p.actor_id)


def _decide_remove(snap: MarkSnapshot, p: _Press) -> MarkDecision:
    """[{이름} 시작 취소] — 고른 사람이 빠졌으면 409 ``TARGET_GONE``, 파트 계정 403 ``REMOVE_FORBIDDEN``(Q5)."""
    crew = list(snap.crew)
    if p.target_uid is not None and mc.find(crew, p.target_uid) is None:
        return _refuse(TARGET_GONE, target_gone_message(""), target_uid=p.target_uid)
    if not p.admin:
        return _forbid(REMOVE_FORBIDDEN, REMOVE_FORBIDDEN_MESSAGE)
    return _remove_one(crew, p, ACTION_REMOVE)


def _decide_takeover(snap: MarkSnapshot, p: _Press) -> MarkDecision:
    """[담당 바꾸기] — 고른 한 사람 자리를 나로(완료를 누른 사람은 못 고름 — 판결 4, 고를 사람이 하나면 고르기 없이)."""
    crew = list(snap.crew)
    if not crew:  # 담당 없는 작업 필요 줄 — 지금처럼 나로
        return _applied(mc.join([], p.actor_id, p.actor_name, p.now), ACTION_TAKEOVER)
    item, gone = _pick_target(crew, p.target_uid)
    if gone:
        return _refuse(TARGET_GONE, target_gone_message(""), target_uid=p.target_uid)
    if item is None:
        return _refuse(TARGET_REQUIRED, TARGET_REQUIRED_SWAP, status=400)
    if mc.is_done(item):
        return _refuse(TARGET_DONE, TARGET_DONE_MESSAGE)
    return _applied(mc.swap(crew, item.get("uid"), p.actor_id, p.actor_name, p.now), ACTION_TAKEOVER,
                    target_uid=item.get("uid"), target_name=str(item.get("name") or ""))


def _decide_check(snap: MarkSnapshot, p: _Press) -> MarkDecision:
    """PC [완료 처리](판결 2) — 빈 줄 = 시작 + 내 몫 완료, 남이 작업 중 = 대신 완료(감독은 목록에 안 들어감)."""
    crew = list(snap.crew)
    if snap.state == MARK_STATE_NONE:
        mine = mc.join([], p.actor_id, p.actor_name, p.now)
        return _applied(mc.finish(mine, p.actor_id, by_uid=p.actor_id, by_name=p.actor_name, now=p.now), ACTION_CHECK)
    if not crew:
        return _applied([], ACTION_CHECK, empty_state=MARK_STATE_DONE)
    proxied = any(not mc.is_done(m) and m.get("uid") != p.actor_id for m in crew)
    return _applied(mc.finish_rest(crew, by_uid=p.actor_id, by_name=p.actor_name, now=p.now), ACTION_CHECK,
                    override=proxied, proxied=proxied)


def _decide_apply(snap: MarkSnapshot, action: str, seen: str, p: _Press) -> MarkDecision:
    """경합을 지난 누름의 결정(누름마다)."""
    crew = list(snap.crew)
    if action == ACTION_TAKE:
        return _applied(mc.join([], p.actor_id, p.actor_name, p.now), ACTION_TAKE)
    if action == ACTION_JOIN:
        return _applied(mc.join(crew, p.actor_id, p.actor_name, p.now), ACTION_JOIN)
    if action == ACTION_BASIC:
        return _applied([], ACTION_BASIC, empty_state=MARK_STATE_BASIC)
    handlers = {ACTION_DONE: _decide_done, ACTION_RELEASE: _decide_release, ACTION_REMOVE: _decide_remove,
                ACTION_TAKEOVER: _decide_takeover, ACTION_CHECK: _decide_check}
    if action == ACTION_UNDO:
        return _decide_undo(snap, p, seen)
    return handlers[action](snap, p)


def decide_mark(snapshot: MarkSnapshot, *, action: str, seen: str, actor_id: int, admin: bool,
                seen_by: Any = SEEN_BY_UNSET, seen_me: Optional[str] = None, target_uid: Optional[int] = None,
                actor_name: Optional[str] = None, now: Optional[datetime.datetime] = None,
                label: str = "") -> MarkDecision:
    """누름 하나를 판정한다(§7-3 차례 — 막는 까닭 · 검수 순서는 부르는 쪽이 이 결정과 사이에 끼운다).

    차례: 표에 없는 짝 → invalid · 같은 사람이 같은 결과 → same(멱등) · 넘김(take → join · join → take) · 지금 ≠ seen →
    conflict(join 인데 모두 완료 = ``JOIN_DONE``) · 본 담당(``seen_by``) · 본 내 몫(``seen_me``) 다름 → conflict ·
    누름마다 결정(권한 403 · 새 거절 · apply).

    Args:
        snapshot: 서버의 지금 모습(목록 포함).
        action: :data:`MARK_ACTIONS` 중 하나.
        seen: 화면이 본 상태.
        actor_id: 누른 사람 id.
        admin: 반장 · 관리자 덮어쓰기 허용 여부(D55).
        seen_by: 옛 화면이 본 담당 id(None = 담당 없음으로 봄). 안 보내면(:data:`SEEN_BY_UNSET`) 담당은 견주지 않는다.
        seen_me: 새 화면이 본 내 몫(none · held · done). None 이면 견주지 않는다.
        target_uid: 바꾸기 · 시작 취소 · 대신 되돌리기 대상(없으면 고를 사람이 하나일 때만).
        actor_name: 누른 사람 이름(목록 스냅샷).
        now: 쓰는 시각(UTC naive, 없으면 지금).
        label: 파트 이름(거절 글).

    Returns:
        :class:`MarkDecision`.
    """
    target = action_target(action, seen)
    if target is None:
        return MarkDecision(DECISION_INVALID, message="이 상태에서는 그렇게 바꿀 수 없어요.", code="BAD_REQUEST", status=400)
    if _same_result(snapshot, action, target, actor_id, target_uid, seen_me):
        return MarkDecision(DECISION_SAME, target=snapshot.state, action=action)
    crew = list(snapshot.crew)
    action, seen, late = mc.late_join(action, seen, snapshot.state, crew, actor_id)
    if action != ACTION_CHECK and snapshot.seen_key != seen:
        if action == ACTION_JOIN and snapshot.state == MARK_STATE_DONE:
            return _refuse(JOIN_DONE, JOIN_DONE_MESSAGE, action=action)
        message = new_action_conflict_message(snapshot) if action in NEW_ACTIONS else conflict_message(snapshot)
        return MarkDecision(DECISION_CONFLICT, message=message, action=action)
    if (seen_by is not SEEN_BY_UNSET and seen == "need" and action not in (ACTION_JOIN, ACTION_CHECK)
            and not _seen_by_ok(snapshot, seen_by)):
        return MarkDecision(DECISION_CONFLICT, message=holder_changed_message(snapshot), action=action)
    if seen_me is not None and action != ACTION_CHECK and seen_me != mc.share_of(crew, actor_id):
        return MarkDecision(DECISION_CONFLICT, message=STALE_MESSAGE, action=action)
    press = _Press(actor_id, actor_name, admin, now or now_utc_naive(), seen_by, seen_me, target_uid, label)
    decision = _decide_apply(snapshot, action, seen, press)
    if late and decision.kind == DECISION_APPLY:
        decision = replace(decision, joined_late=True, notice=took_first_message(crew_line(snapshot)))
    return decision


__all__ = ["decide_mark"]

"""액션 이름 → 서비스(설계서 7.7 · D104) — :mod:`.actions` 목록의 얇은 실행 층. 엔진은 그대로 :func:`.apply.apply_change`.

:func:`perform` 하나가 본문을 그 액션 꼴로 검사하고(:func:`.actions.parse`) 서비스 하나를 부른다. HTTP API
(:mod:`foms.api.brain_review`)와 ⑤-5 챗봇 · 에이전트 도구가 같은 길을 쓴다 — 권한 · 보기 범위 · 기준 판은 서비스 · 엔진이
다시 본다. 결정한 사람은 늘 ``actor``(로그인 사용자)이고 본문의 사람 칸은 읽지 않는다(R10-18). 커밋은 호출자 몫이다.
"""

from __future__ import annotations

import copy
import datetime
from typing import Any, Callable, Mapping, Optional

from foms.services.brain.actions import ActionType, parse
from foms.services.brain.decide import apply_decision, bulk_apply, record_proposal, reject_decision
from foms.services.brain.errors import BrainPermissionError, BrainShapeError
from foms.services.brain.chat_reports import build_conflict_proposal
from foms.services.brain.proposals import (
    Proposer, propose_create, propose_delete, propose_retire, propose_rollback, propose_update,
)
from foms.services.brain.read import current_item, item_history
from foms.services.brain.recheck import confirm_still_true
from foms.services.brain.rollback import rollback_release
from foms.services.brain.schemas import PAYLOAD, payload_props
from foms.services.brain.scope import Viewer, viewer_of
from foms.services.datetime_kst import now_utc_naive

Handler = Callable[[Any, Any, dict[str, Any], datetime.datetime], dict[str, Any]]


def _seen_item(session: Any, actor: Any, key: str) -> tuple[Viewer, dict[str, Any]]:
    """제안하는 사람 · 그 항목(볼 수 없거나 없으면 같은 권한 오류)."""
    viewer = viewer_of(actor)
    item = current_item(session, viewer, key) if viewer.user_id is not None else None
    if item is None:
        raise BrainPermissionError("볼 수 없는 항목이다")
    return viewer, item


def expand_after(item: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    """``payload.<칸>`` 꼴 고칠 칸 → 실음 칸 통째(지금 실음 칸에 덮어씀 · 빈 값은 칸 빼기). 틀 밖 칸은 꼴 오류."""
    allowed = {p.path for p in payload_props(item.get("type"))}
    unknown = sorted(k for k in after if k.startswith(PAYLOAD) and k not in allowed)
    if unknown:
        raise BrainShapeError([f"after: {item.get('type')} 속성 틀에 없는 칸 {unknown}"])
    out = {k: v for k, v in after.items() if not k.startswith(PAYLOAD)}
    subs = {k[len(PAYLOAD):]: v for k, v in after.items() if k.startswith(PAYLOAD)}
    if subs:
        payload = copy.deepcopy(item.get("payload") or {})
        for name, value in subs.items():
            if value is None or value == "" or value == []:
                payload.pop(name, None)
            else:
                payload[name] = value
        out["payload"] = payload
    return out


def _proposed(session: Any, viewer: Viewer, change: Any, now: datetime.datetime) -> dict[str, Any]:
    """사람 제안 감사 한 줄 + 돌려줄 값."""
    record_proposal(session, change, actor_id=int(viewer.user_id or 0), now=now)
    return {"change_id": change.id, "op": change.op, "grade": change.grade, "action": change.action}


def _propose_edit(session: Any, actor: Any, p: dict[str, Any], now: datetime.datetime) -> dict[str, Any]:
    viewer, item = _seen_item(session, actor, p["key"])
    change = propose_update(session, key=p["key"], base_version=p["base_version"], after=expand_after(item, p["after"]),
                            reason=p["reason"], proposer=Proposer.user(int(viewer.user_id or 0)), now=now,
                            action="propose_edit")
    return _proposed(session, viewer, change, now)


def _propose_end(maker: Callable[..., Any], name: str) -> Handler:
    def run(session: Any, actor: Any, p: dict[str, Any], now: datetime.datetime) -> dict[str, Any]:
        viewer, _item = _seen_item(session, actor, p["key"])
        change = maker(session, key=p["key"], base_version=p["base_version"], reason=p["reason"],
                       proposer=Proposer.user(int(viewer.user_id or 0)), now=now, action=name)
        return _proposed(session, viewer, change, now)
    return run


def _item_rollback(session: Any, actor: Any, p: dict[str, Any], now: datetime.datetime) -> dict[str, Any]:
    viewer, _item = _seen_item(session, actor, p["key"])
    if p["to_version"] not in {v["version"] for v in item_history(session, viewer, p["key"])}:
        raise BrainPermissionError("볼 수 없는 판이다")
    change = propose_rollback(session, key=p["key"], to_version=p["to_version"], reason=p["reason"],
                              proposer=Proposer.user(int(viewer.user_id or 0)), now=now)
    return _proposed(session, viewer, change, now)


def _apply(session: Any, actor: Any, p: dict[str, Any], now: datetime.datetime) -> dict[str, Any]:
    result = apply_decision(session, p["change_id"], actor=actor, base_version=p["base_version"], confirm=p["confirm"],
                            edits=p.get("edits"), view_ms=p["view_ms"], now=now)
    return {"change_id": result.change_id, "version": result.version, "release": result.release_no}


def _reject(session: Any, actor: Any, p: dict[str, Any], now: datetime.datetime) -> dict[str, Any]:
    change = reject_decision(session, p["change_id"], actor=actor, code=p["code"], view_ms=p["view_ms"], now=now)
    return {"change_id": change.id, "code": change.reject_code}


def _bulk(session: Any, actor: Any, p: dict[str, Any], now: datetime.datetime) -> dict[str, Any]:
    return bulk_apply(session, p["ids"], actor=actor, now=now)


def _recheck(session: Any, actor: Any, p: dict[str, Any], now: datetime.datetime) -> dict[str, Any]:
    result = confirm_still_true(session, p["key"], actor=actor, version=p["version"], view_ms=p["view_ms"], now=now)
    if result is None:
        return {"already": True, "version": p["version"], "message": "오늘 이미 확인한 항목이에요."}
    return {"version": result.version, "release": result.release_no}


def _release_rollback(session: Any, actor: Any, p: dict[str, Any], now: datetime.datetime) -> dict[str, Any]:
    return rollback_release(session, p["number"], p["layer"], actor=actor, confirm_number=p["confirm_number"], now=now)


_propose_retire = _propose_end(propose_retire, "propose_retire")
_propose_delete = _propose_end(propose_delete, "propose_delete")
#: 실행 길이 있는 액션 이름(:func:`_dispatch` 갈래와 같다 — 시험이 액션 목록과 견준다).
HANDLED: frozenset[str] = frozenset({"propose_edit", "propose_retire", "propose_delete", "item_rollback", "apply",
                                     "edit_apply", "reject", "bulk_apply", "recheck", "release_rollback"})


def _dispatch(name: str, session: Any, actor: Any, p: dict[str, Any], now: datetime.datetime) -> dict[str, Any]:
    """이름 → 서비스 — 갈래를 그대로 적는다(정적 감사 범위 스캐너가 감사 줄을 쓰는 서비스까지 따라가게)."""
    if name == "propose_edit":
        return _propose_edit(session, actor, p, now)
    if name == "propose_retire":
        return _propose_retire(session, actor, p, now)
    if name == "propose_delete":
        return _propose_delete(session, actor, p, now)
    if name == "item_rollback":
        return _item_rollback(session, actor, p, now)
    if name in ("apply", "edit_apply"):
        return _apply(session, actor, p, now)
    if name == "reject":
        return _reject(session, actor, p, now)
    if name == "bulk_apply":
        return _bulk(session, actor, p, now)
    if name == "recheck":
        return _recheck(session, actor, p, now)
    if name == "release_rollback":
        return _release_rollback(session, actor, p, now)
    raise BrainShapeError([f"action: 실행 길이 없는 액션 {name}"])


def perform_agent(session: Any, name: Any, *, agent: str, body: Mapping[str, Any],
                  now: Optional[datetime.datetime] = None) -> tuple[ActionType, dict[str, Any]]:
    """코드(에이전트) 길 액션 하나 — 꼴 검사(:data:`.actions.AGENT_ACTION_TYPES`) → 서비스. 제안만 만든다(정본은 그대로).

    제안한 이는 늘 ``agent:<이름>`` 이라 관문 셋(:mod:`.ai_gates`)이 돈다. 커밋은 호출자 몫이다.

    Raises:
        BrainError 갈래(꼴 · 대상 · 관문).
    """
    action, params = parse(name, body, agent=True)
    when = now or now_utc_naive()
    if action.name == "report_conflict":
        change = build_conflict_proposal(session, key=params["key"], proposer=Proposer.agent_named(agent), now=when,
                                         propose_create=propose_create)
        return action, {"message": action.done, "change_id": change.id, "op": change.op, "grade": change.grade}
    raise BrainShapeError([f"action: 실행 길이 없는 액션 {action.name}"])  # pragma: no cover


def perform(session: Any, name: Any, *, actor: Any, body: Mapping[str, Any],
            now: Optional[datetime.datetime] = None) -> tuple[ActionType, dict[str, Any]]:
    """액션 하나 — 꼴 검사 → 서비스. 돌려주는 값: (액션, 결과 값 — 끝난 말 ``message`` 포함).

    Raises:
        BrainError 갈래(꼴 · 권한 · 대상 · 기준 판 · 확인 · 막힘).
    """
    action, params = parse(name, body)
    data = _dispatch(action.name, session, actor, params, now or now_utc_naive())
    return action, {"message": action.done, **data}

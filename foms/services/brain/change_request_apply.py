"""문장으로 고치기 — 이대로 고치기 · 묶음 되돌리기(설계서 2026-11-18-brain-sentence-change 2절 ⑤ ⑥ ⑧ · 8절 · D246 · D247).

**정본은 여기서 직접 쓰지 않는다** — 줄마다 지금 제안 함수(:func:`.change_request_check.propose_line` → :mod:`.proposals`)로
제안 줄을 만들고(제안한 이 = 넣은 사람 · ``request_id`` = 묶음 번호), 반영은 반영 동작 한 곳(:func:`.apply.apply_change` —
권한은 :func:`.apply.check_permission` 그대로)으로 한다. 설정 줄은 :func:`foms.services.ai_staff.levels.save_levels`(감사 줄은 그
함수가 남긴다)로 저장한다.

- :func:`apply` — ``skip`` 줄을 빼고 미리 보기 줄만. 넣은 사람이 반영할 수 없는 줄(권한)은 **열린 채 승인 대기**에 남는다
  (``pending``). 줄 하나가 실패해도 나머지는 간다 — 줄마다 저장점(실패한 줄은 제안 줄도 남기지 않는다). 모두 반영이면
  ``applied``, 승인 대기 · 실패가 있으면 ``partial``. 등급 B 의 '핵심 값 확인'은 미리 보기를 보고 [이대로 고치기]를 누른 것으로
  갈음한다(D246 — 한 번 누르기).
- :func:`revert` — **이 묶음이 반영한 것만** 되돌린다(같은 날 다른 승인은 건드리지 않는다 — 판 되돌리기와 다르다). 차례는 판
  되돌리기(:mod:`.rollback`)와 같다: ① 더한 연결 빼기 ② 항목(고친 · 은퇴한 것은 반영 전 판으로 — :func:`.proposals.propose_rollback`,
  만든 것은 지우기) ③ 뺀 연결 다시 더하기 ④ 설정은 전 값으로. **그 뒤 다른 고침이 같은 곳에 얹혔으면** 그 줄은 되돌리지 않고
  까닭(``later_change``)을 적는다. 아직 열린 제안 줄은 거둔다(``expired`` · ``decided_action='withdraw'`` — :func:`.plan_proposals.withdraw_open`
  과 같은 꼴). 승인자가 그 사이 반영한 줄도 이 묶음의 제안이라 되돌린다.
- **새 항목과 그 연결은 한 저장점**: 같은 묶음의 새 항목(``new:<n>``)에서 나가는 연결 줄은 만들기 줄 바로 뒤에 넣는다. 새 제작
  조건은 적용 연결이 하나도 들어가지 않으면 만들기째 되돌린다(외톨이 금지 — 설계서 2026-11-13 C). 새 지식 문서 항목의 승인
  칸은 반영하는 사람 · 반영 날(한국)로 다시 적는다(:func:`.change_request_check.approve_doc`).
- 반영이 끝나면 넣은 사람에게 FOMS 안 알림 한 줄(:mod:`foms.services.notifications.brain_change_notice` — 폰 알림 없음).
커밋은 부르는 쪽(API)이다.
"""

from __future__ import annotations

import copy
import datetime
from typing import Any, Optional

from sqlalchemy import and_, select

from foms.persistence.brain.models import BrainChange, BrainLink, BrainChangeRequest
from foms.services.ai_staff.levels import LevelError, save_levels
from foms.services.ai_staff.registry import level_table
from foms.services.brain.apply import apply_change
from foms.services.brain.change_request_check import (
    KIND_CREATE, KIND_LINK_ADD, KIND_LINK_REMOVE, KIND_RETIRE, KIND_SETTING, KIND_UPDATE, RULE_TYPE, STATE_APPLIED,
    STATE_FAILED, STATE_PENDING, STATE_PREVIEW, STATE_REVERT_BLOCKED, STATE_REVERTED, STATE_SKIPPED, STATE_WITHDRAWN,
    approve_doc, check_of, is_new_link, propose_line, reason_of,
)
from foms.services.brain.change_request_store import (
    APPLIED, PARTIAL, READY, REVERTED, ChangeRequestError, audit, load, require_user, save_bundle, view_of,
)
from foms.services.brain.constants import CHANGE_APPLIED, CHANGE_EXPIRED, CHANGE_OPEN, CHANGE_REJECTED, LINK_OPS
from foms.services.brain.decide import record_proposal
from foms.services.brain.errors import BrainError, BrainPermissionError, BrainTargetError
from foms.services.brain.proposals import Proposer, known_text, propose_delete, propose_link, propose_rollback
from foms.services.brain.store import LINK_FIELDS, current_link, current_object, kst_day, values_of
from foms.services.datetime_kst import now_utc_naive
from foms.services.notifications.brain_change_notice import BRAIN_CHANGE_REQUEST_TYPE, TITLE, notice_message
from foms.services.notifications.recipients import fan_out_new_notification
from models import Notification

#: 되돌림 제안 · 결정의 액션 이름(:mod:`.actions` — 항목 하나 되돌리기).
REVERT_ACTION = "item_rollback"
STATE_REJECTED = "rejected"


def _skip_numbers(skip: Any) -> set[int]:
    """뺄 줄 번호들 — 정수 목록이어야 한다(아니면 ``shape``)."""
    if skip is None:
        return set()
    if not isinstance(skip, list) or len(skip) > 200 or not all(
            isinstance(n, int) and not isinstance(n, bool) for n in skip):
        raise ChangeRequestError("shape")
    return set(skip)


def _apply_item(session: Any, user: Any, line: dict[str, Any], *, request_id: int, known: str,
                now: datetime.datetime) -> None:
    """항목 · 연결 줄 하나 — 제안 줄 → (넣은 사람이 반영할 수 있으면) 반영. 권한이 없으면 승인 대기, 그 밖 실패는 줄째 되돌림."""
    outer = session.begin_nested()
    try:
        change = propose_line(session, line, proposer=Proposer.user(user.id), request_id=request_id,
                              reason=reason_of(request_id, line), known=known, now=now)
        record_proposal(session, change, actor_id=user.id, now=now)
        try:
            with session.begin_nested():
                result = apply_change(session, change.id, actor=user, now=now, detail={"request": request_id})
            line["state"], line["version"] = STATE_APPLIED, result.version
        except BrainPermissionError:
            line["state"] = STATE_PENDING  # 넣은 사람이 반영할 수 없는 줄 — 승인 대기에 열린 채(D247)
        line["change_id"] = change.id
        outer.commit()
    except BrainError as exc:
        outer.rollback()
        line["state"], line["check"], line["change_id"] = STATE_FAILED, check_of(exc.code), None


def _apply_setting(session: Any, user: Any, line: dict[str, Any]) -> None:
    """설정 줄 하나 — 수준 표 칸 하나를 저장(감사 줄은 save_levels). 저장 직전 값을 '전'으로 적는다."""
    plan = line["plan"]
    savepoint = session.begin_nested()
    try:
        before = level_table(session)[plan["agent"]][plan["action"]]
        save_levels(session, user, {"levels": {plan["agent"]: {plan["action"]: plan["value"]}}})
        savepoint.commit()
        line["before"], line["state"] = {"level": before}, STATE_APPLIED
        line["fields"] = [{**f, "before": before} for f in line["fields"]]
        plan["before"] = before
    except (LevelError, KeyError) as exc:
        savepoint.rollback()
        code = exc.code if isinstance(exc, LevelError) else "setting_value"
        line["state"], line["check"] = STATE_FAILED, check_of("setting_admin" if code == "LEVEL_FORBIDDEN" else
                                                               "setting_value")


def _fail(line: dict[str, Any], code: str) -> None:
    """줄 실패 — 까닭 코드 · 제안 줄 없음(저장점째 되돌린 줄)."""
    line["state"], line["check"], line["change_id"] = STATE_FAILED, check_of(code), None


def _apply_group(session: Any, user: Any, create: dict[str, Any], links: list[dict[str, Any]], *, request_id: int,
                 known: str, now: datetime.datetime) -> None:
    """새 항목 + 그 연결 줄들(한 저장점). 새 제작 조건은 적용 연결이 하나도 안 들어가면 만들기째 되돌린다."""
    outer = session.begin_nested()
    _apply_item(session, user, create, request_id=request_id, known=known, now=now)
    if create["state"] != STATE_APPLIED:
        for link in links:
            _fail(link, "new_waiting" if create["state"] == STATE_PENDING else "new_blocked")
        outer.commit()
        return
    for link in links:
        _apply_item(session, user, link, request_id=request_id, known=known, now=now)
    rule = create["plan"]["type"] == RULE_TYPE
    if rule and not any(x["state"] == STATE_APPLIED and x["plan"]["kind"] == "applies_to" for x in links):
        outer.rollback()
        _fail(create, "orphan_rule")
        for link in links:
            if link["state"] != STATE_FAILED:
                _fail(link, "new_blocked")
            link["change_id"] = None
        return
    outer.commit()


def _apply_lines(session: Any, user: Any, todo: list[dict[str, Any]], *, request_id: int, known: str,
                 now: datetime.datetime) -> None:
    """줄마다 반영 — 설정 · 항목 · 새 항목 묶음(만들기 줄 뒤 그 연결). 만들기 줄을 뺀 새 항목 연결은 실패."""
    day = kst_day(now)
    groups: dict[int, list[dict[str, Any]]] = {}
    for line in todo:
        if is_new_link(line):
            groups.setdefault(line["plan"].get("after_line") or 0, []).append(line)
    creates = {line["no"] for line in todo if line["kind"] == KIND_CREATE}
    for line in todo:
        if line["kind"] == KIND_SETTING:
            _apply_setting(session, user, line)
        elif is_new_link(line):
            if line["plan"].get("after_line") not in creates:
                _fail(line, "new_blocked")
        elif line["kind"] == KIND_CREATE:
            approve_doc(line, request_id=request_id, user_id=user.id, day=day)
            links = groups.get(line["no"], [])
            if line["plan"]["type"] == RULE_TYPE and not any(x["plan"]["kind"] == "applies_to" for x in links):
                _fail(line, "orphan_rule")
                continue
            _apply_group(session, user, line, links, request_id=request_id, known=known, now=now)
        else:
            _apply_item(session, user, line, request_id=request_id, known=known, now=now)


def _notify(session: Any, row: BrainChangeRequest, user: Any, todo: list[dict[str, Any]]) -> None:
    """넣은 사람에게 FOMS 안 알림 한 줄(고친 곳 수 · 승인 대기 수 — 글 없음). 폰 알림은 보내지 않는다."""
    applied = sum(1 for line in todo if line["state"] == STATE_APPLIED)
    pending = sum(1 for line in todo if line["state"] == STATE_PENDING)
    note = Notification(notification_type=BRAIN_CHANGE_REQUEST_TYPE, target_type="USER", target_user_id=row.created_by,
                        order_id=None, is_urgent=False, title=TITLE, message=notice_message(row.id, applied, pending),
                        created_by_user_id=int(user.id), created_by_name=getattr(user, "name", None), is_read=False)
    session.add(note)
    session.flush()
    fan_out_new_notification(session, note, actor_user_id=int(user.id))


def apply(session: Any, user: Any, request_id: Any, *, skip: Any = None,
          now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """이대로 고치기 — 넣은 사람만 · 미리 보기 상태만. ``skip`` = 뺄 줄 번호들.

    Raises:
        ChangeRequestError: forbidden · shape · state(미리 보기 아님) · empty(고칠 줄이 하나도 없음).
    """
    viewer = require_user(user)
    row = load(session, viewer, request_id, lock=True, owner_only=True)
    if row.status != READY:
        raise ChangeRequestError("state")
    skipped = _skip_numbers(skip)
    now = now or now_utc_naive()
    bundle = copy.deepcopy(row.bundle or {})
    lines = bundle.get("lines") or []
    todo = [line for line in lines if line["state"] == STATE_PREVIEW and line["no"] not in skipped]
    if not todo:
        raise ChangeRequestError("empty")
    known = known_text(session)
    for line in lines:
        if line["state"] == STATE_PREVIEW and line["no"] in skipped:
            line["state"] = STATE_SKIPPED
    _apply_lines(session, user, todo, request_id=row.id, known=known, now=now)
    done = sum(1 for line in todo if line["state"] == STATE_APPLIED)
    row.status = APPLIED if done == len(todo) else PARTIAL
    row.decided_at = now
    save_bundle(row, bundle)
    audit(session, viewer.user_id, row, "APPLY", {"applied": done, "pending": sum(
        1 for line in todo if line["state"] == STATE_PENDING), "failed": sum(
        1 for line in todo if line["state"] == STATE_FAILED), "skipped": len(skipped & {line["no"] for line in lines})},
        now)
    _notify(session, row, user, todo)
    session.flush()
    return view_of(row, viewer)


# ── 되돌리기 ─────────────────────────────────────────────────────────────
def _later_link_change(session: Any, change: BrainChange) -> bool:
    """이 연결 제안 뒤 같은 연결(종류 · 양 끝)에 반영된 다른 제안이 있나."""
    later = session.execute(select(BrainChange.id).where(
        BrainChange.status == CHANGE_APPLIED, BrainChange.id > change.id, BrainChange.op.in_(LINK_OPS),
        and_(BrainChange.link_kind == change.link_kind, BrainChange.link_from == change.link_from,
             BrainChange.link_to == change.link_to)).limit(1)).first()
    return later is not None


def _undo_change(session: Any, change: BrainChange, ctx: dict[str, Any]) -> Optional[BrainChange]:
    """반영된 제안 하나의 되돌림 제안(뒤 고침이 얹혔으면 :class:`_Later`, 할 일이 없으면 ``None``)."""
    kw = {"reason": ctx["reason"], "proposer": ctx["proposer"], "now": ctx["now"]}
    if change.op in ("update", "retire"):
        current = current_object(session, change.item_key)
        if current is None or current.version != change.result_version:
            raise _Later()
        try:
            return propose_rollback(session, key=change.item_key, to_version=int(change.base_version),
                                    action=REVERT_ACTION, **kw)
        except BrainTargetError as exc:
            if str(exc) == "바뀐 칸이 없다":
                return None
            raise
    if change.op == "create":
        current = current_object(session, change.item_key)
        if current is None or current.version != change.result_version:
            raise _Later()
        return propose_delete(session, key=change.item_key, base_version=current.version, rollback_of=0,
                              action=REVERT_ACTION, **kw)
    link = current_link(session, change.link_kind, change.link_from, change.link_to)
    if change.op == "link_add":
        if link is None or link.version != change.result_version:
            raise _Later()
        return propose_link(session, op="link_remove", kind=change.link_kind, from_key=change.link_from,
                            to_key=change.link_to, base_version=link.version, rollback_of=0, action=REVERT_ACTION, **kw)
    if link is not None or _later_link_change(session, change):
        raise _Later()
    old = session.execute(select(BrainLink).where(
        BrainLink.kind == change.link_kind, BrainLink.from_key == change.link_from, BrainLink.to_key == change.link_to,
        BrainLink.version == change.base_version)).scalar_one_or_none()
    if old is None:
        raise _Later()
    values = {k: v for k, v in values_of(old, LINK_FIELDS).items() if v is not None}
    return propose_link(session, op="link_add", kind=change.link_kind, from_key=change.link_from,
                        to_key=change.link_to, values=values, rollback_of=old.version, action=REVERT_ACTION, **kw)


class _Later(Exception):
    """그 뒤 다른 고침이 같은 곳에 얹혔다(되돌리지 않는다)."""


def _revert_item(session: Any, user: Any, line: dict[str, Any], ctx: dict[str, Any]) -> None:
    """반영된 항목 · 연결 줄 하나를 되돌린다(줄마다 저장점 — 막히면 까닭만 적고 다음 줄로)."""
    change = session.get(BrainChange, int(line["change_id"]), populate_existing=True)
    savepoint = session.begin_nested()
    try:
        undo = _undo_change(session, change, ctx)
        if undo is not None:
            undo.request_id = ctx["request_id"]
            session.flush()
            apply_change(session, undo.id, actor=user, now=ctx["now"],
                         detail={"request": ctx["request_id"], "revert": 1}, action=REVERT_ACTION)
            line["revert_change_id"] = undo.id
        savepoint.commit()
        line["state"] = STATE_REVERTED
    except _Later:
        savepoint.rollback()
        line["state"], line["check"] = STATE_REVERT_BLOCKED, check_of("later_change")
    except BrainError as exc:
        savepoint.rollback()
        line["state"], line["check"] = STATE_REVERT_BLOCKED, check_of(exc.code)


def _revert_setting(session: Any, user: Any, line: dict[str, Any]) -> None:
    """설정 줄 하나를 전 값으로 — 지금 값이 이 묶음이 넣은 값일 때만(아니면 뒤 고침이 얹힌 것)."""
    plan = line["plan"]
    savepoint = session.begin_nested()
    try:
        if level_table(session)[plan["agent"]][plan["action"]] != plan["value"]:
            raise _Later()
        save_levels(session, user, {"levels": {plan["agent"]: {plan["action"]: plan["before"]}}})
        savepoint.commit()
        line["state"] = STATE_REVERTED
    except _Later:
        savepoint.rollback()
        line["state"], line["check"] = STATE_REVERT_BLOCKED, check_of("later_change")
    except (LevelError, KeyError):
        savepoint.rollback()
        line["state"], line["check"] = STATE_REVERT_BLOCKED, check_of("setting_admin")


def _settle_pending(session: Any, line: dict[str, Any], now: datetime.datetime) -> None:
    """승인 대기 줄 — 아직 열렸으면 거둔다, 그 사이 승인자가 반영했으면 반영된 줄로 본다, 거절됐으면 그대로."""
    change = session.get(BrainChange, int(line["change_id"]), with_for_update=True, populate_existing=True)
    if change.status == CHANGE_OPEN:
        change.status, change.decided_at, change.decided_action = CHANGE_EXPIRED, now, "withdraw"
        line["state"] = STATE_WITHDRAWN
    elif change.status == CHANGE_APPLIED:
        line["state"] = STATE_APPLIED
    elif change.status == CHANGE_REJECTED:
        line["state"] = STATE_REJECTED


_ORDER = {KIND_LINK_ADD: 0, KIND_UPDATE: 1, KIND_RETIRE: 1, KIND_CREATE: 1, KIND_LINK_REMOVE: 2, KIND_SETTING: 3}


def revert(session: Any, user: Any, request_id: Any, *, now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """이 묶음 되돌리기 — 넣은 사람 · 관리자, 반영됨 · 일부 반영 상태만.

    Raises:
        ChangeRequestError: forbidden · state.
    """
    viewer = require_user(user)
    row: BrainChangeRequest = load(session, viewer, request_id, lock=True)
    if row.status not in (APPLIED, PARTIAL):
        raise ChangeRequestError("state")
    now = now or now_utc_naive()
    bundle = copy.deepcopy(row.bundle or {})
    lines = bundle.get("lines") or []
    for line in lines:
        if line["state"] == STATE_PENDING and line.get("change_id"):
            _settle_pending(session, line, now)
    ctx = {"reason": f"문장으로 고치기 #{row.id} 되돌리기", "proposer": Proposer.user(viewer.user_id), "now": now,
           "request_id": row.id}
    for line in sorted((x for x in lines if x["state"] == STATE_APPLIED), key=lambda x: (_ORDER[x["kind"]], -x["no"])):
        if line["kind"] == KIND_SETTING:
            _revert_setting(session, user, line)
        else:
            _revert_item(session, user, line, ctx)
    row.status, row.decided_at = REVERTED, now
    save_bundle(row, bundle)
    audit(session, viewer.user_id, row, "REVERT", {
        "reverted": sum(1 for x in lines if x["state"] == STATE_REVERTED),
        "blocked": sum(1 for x in lines if x["state"] == STATE_REVERT_BLOCKED),
        "withdrawn": sum(1 for x in lines if x["state"] == STATE_WITHDRAWN)}, now)
    session.flush()
    return view_of(row, viewer)

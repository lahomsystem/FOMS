"""제안함 결정 — 넣기 · 고쳐 넣기 · 거절 · 한꺼번에 넣기(등급 A 만) · AI 제안 저절로 닫기(설계서 7.5 승인 흐름 · D101 · D103).

**정본을 쓰는 길은 여전히 :func:`.apply.apply_change` 하나**다. 여기는 그 앞에서 결정마다 다시 확인한다:

1. **권한**(:func:`.access.approval_problem` — 반영 동작이 한 번 더 본다) · **보기 범위**(그 항목 · 새 보기 범위를 볼 수 있어야 —
   볼 수 없으면 없는 제안과 같은 답).
2. **기준 판** — 화면이 보낸 기준 판이 제안의 기준 판과 같아야 하고, 반영 동작이 지금 판과 다시 견준다.
3. **고쳐 넣기** — 승인자가 고친 '후' 값으로 제안을 고치고(처음 값은 ``proposed`` 로 남김) 꼴 · 글 관문을 다시 돌린 뒤 넣는다.
4. **등급 B** — 핵심 값 하나(:func:`.review_rules.confirm_value`)를 화면이 보낸 글과 견준다.

결정 시간(화면이 잰 밀리초) · 제안 나이 · 고쳐 넣음 · 한꺼번에는 감사 줄에 숫자 · 코드로만 남는다(:mod:`.metrics` 가 센다).
커밋은 호출자 몫이다.
"""

from __future__ import annotations

import copy
import datetime
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import aliased
from sqlalchemy.orm.attributes import flag_modified

from foms.persistence.brain.models import BrainChange, BrainObject
from foms.services.brain.access import approval_problem, wide_bins
from foms.services.brain.apply import ApplyResult, apply_change, reject_change
from foms.services.brain.constants import (
    BULK_MAX, CHANGE_EXPIRED, CHANGE_OPEN, GRADE_A, GRADE_B, HUMAN_EDIT_FIELDS, LINK_OPS, OP_CREATE, OP_UPDATE,
)
from foms.services.brain.errors import (
    BrainConfirmError, BrainConflictError, BrainError, BrainPermissionError, BrainShapeError, BrainTargetError,
)
from foms.services.brain.gates import merge_gates, payload_gates, text_gates
from foms.services.brain.inbox import agent_clause, current_join, link_versions, visible_clause
from foms.services.brain.inbox_bins import bulk_ok_any_grade, label_only_change
from foms.services.brain.proposals import known_text, link_target_type
from foms.services.brain.review_rules import ai_cutoff, clamp_ms, confirm_value
from foms.services.brain.schemas import PAYLOAD, edit_props
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object, values_of
from foms.services.datetime_kst import now_utc_naive
from models import SecurityLog


def expire_ai_proposals(session: Any, *, now: datetime.datetime) -> int:
    """만든 뒤 4주가 지난 **AI 제안만** '기간 끝남'으로 닫는다(사람 제안은 그대로). 닫은 수를 돌려주고 감사 한 줄."""
    result = session.execute(update(BrainChange).where(
        BrainChange.status == CHANGE_OPEN, agent_clause(), BrainChange.created_at < ai_cutoff(now),
    ).values(status=CHANGE_EXPIRED, decided_at=now, decided_action="expire")
        .execution_options(synchronize_session="fetch"))
    count = int(result.rowcount or 0)
    if count:
        session.add(SecurityLog(user_id=None, action="BRAIN_EXPIRE", target_type="brain_change", target_id=None,
                                timestamp=now, message=f"BRAIN_EXPIRE count={count}", detail={"count": count}))
    return count


def flag_stale_bases(session: Any, *, now: datetime.datetime) -> int:
    """열린 항목 제안 가운데 기준 판이 지금 판과 다른데 표시가 없는 것에 '기준 판 바뀜' 시각을 적는다(밤 단계 — 반영 동작이
    바로 적지 못한 옛 제안까지 맞춘다). 적은 수를 돌려준다."""
    cur = aliased(BrainObject)
    rows = session.execute(select(BrainChange.id, BrainChange.op, BrainChange.base_version, cur.version)
                           .outerjoin(cur, current_join(cur))
                           .where(BrainChange.status == CHANGE_OPEN, BrainChange.base_changed_at.is_(None),
                                  BrainChange.op.notin_(LINK_OPS))).all()
    stale = [i for i, op, base, version in rows if (version is not None if op == OP_CREATE else version != base)]
    if stale:
        session.execute(update(BrainChange).where(BrainChange.id.in_(stale)).values(base_changed_at=now)
                        .execution_options(synchronize_session="fetch"))
    return len(stale)


def record_proposal(session: Any, change: BrainChange, *, actor_id: int, now: datetime.datetime) -> None:
    """사람이 화면에서 만든 제안 — 감사 한 줄(제안 번호 · 동작 · 키 · 등급 — 글 없음)."""
    session.add(SecurityLog(user_id=actor_id, action="BRAIN_PROPOSE", target_type="brain_change", target_id=change.id,
                            timestamp=now, message=f"BRAIN_PROPOSE change={change.id} op={change.op} key={change.item_key}",
                            detail={"op": change.op, "grade": change.grade,
                                    "rollback_of": change.rollback_of_version}))


def _locked_open(session: Any, change_id: Any, actor: Any) -> BrainChange:
    """제안을 잠가 읽고 결정할 사람인지 본 뒤 열린 제안인지 본다 — 없음 · 결정할 수 없음 · 볼 수 없음은 모두 권한 오류
    (호출자가 같은 404), 닫힌 제안은 대상 오류(409). 차례가 이래야 볼 수 없는 제안의 닫힘 여부도 새지 않는다."""
    try:
        number = int(change_id)
    except (TypeError, ValueError):
        raise BrainPermissionError("제안 번호가 아니다") from None
    change = session.get(BrainChange, number, with_for_update=True, populate_existing=True)
    if change is None:
        raise BrainPermissionError("없는 제안이다")
    _check_reader(session, change, actor)
    if change.status != CHANGE_OPEN:
        raise BrainTargetError(f"열린 제안이 아니다: {number}")
    return change


def _check_reader(session: Any, change: BrainChange, actor: Any) -> None:
    """결정할 수 있고 볼 수 있는 사람인가 — 아니면 권한 오류(호출자가 없는 제안과 같은 404)."""
    viewer = viewer_of(actor)
    types = [change.item_type] + ([link_target_type(session, change.link_to)] if change.op in LINK_OPS else [])
    problem = approval_problem(viewer, op=change.op, layer=change.layer, types=types,
                               label_only=label_only_change(change.op, change.fields))
    if problem is not None:
        raise BrainPermissionError(problem)
    cur = aliased(BrainObject)
    seen = session.execute(select(BrainChange.id).outerjoin(cur, current_join(cur)).where(
        BrainChange.id == change.id, visible_clause(viewer, cur))).first()
    if seen is None:
        raise BrainPermissionError("볼 수 없는 제안이다")


def _current_version(session: Any, change: BrainChange) -> Optional[int]:
    """그 제안이 닿는 것의 지금 판(링크면 링크 판)."""
    if change.op in LINK_OPS:
        return link_versions(session, [change]).get((change.link_kind, change.link_from, change.link_to))
    current = current_object(session, change.item_key)
    return current.version if current is not None else None


def _timing(change: BrainChange, view_ms: Any, now: datetime.datetime, **flags: int) -> dict[str, int]:
    """감사 줄 숫자 — 화면이 잰 결정 시간(ms) · 제안 나이(초) · 표시."""
    detail = {key: int(value) for key, value in flags.items() if value}
    ms = clamp_ms(view_ms)
    if ms is not None:
        detail["ms"] = ms
    if change.created_at is not None:
        detail["age_s"] = max(0, int((now - change.created_at).total_seconds()))
    return detail


def _apply_edits(session: Any, change: BrainChange, edits: Mapping[str, Any]) -> None:
    """고쳐 넣기 — 바뀐 칸의 '후' 값만 고친다(처음 값은 ``proposed``). 고친 뒤 바뀐 칸이 없으면 대상 오류."""
    if change.op not in (OP_CREATE, OP_UPDATE):
        raise BrainShapeError(["edits: 새로 만듦 · 고침 제안만 고쳐 넣는다"])
    editable = set(HUMAN_EDIT_FIELDS) | {p.path for p in edit_props(change.item_type)}
    unknown = sorted(str(n)[:40] for n in edits if n not in editable)
    if unknown:
        raise BrainShapeError([f"edits: {sorted(editable)} 칸만 고쳐 넣는다 — {unknown}"])
    fields = copy.deepcopy(change.fields or {})
    current = values_of(current_object(session, change.item_key)) if change.op == OP_UPDATE else {}
    for name, value in edits.items():
        if name.startswith(PAYLOAD):
            _edit_payload(fields, current, name[len(PAYLOAD):], value)
            continue
        entry = fields.get(name) or {"before": current.get(name)}
        entry.setdefault("proposed", entry.get("after"))
        entry["after"] = value
        fields[name] = entry
    fields = {n: e for n, e in fields.items() if change.op == OP_CREATE or e.get("before") != e.get("after")}
    if not fields:
        raise BrainTargetError("바뀐 칸이 없다")
    change.fields = fields
    flag_modified(change, "fields")
    texts = [(fields.get(n) or {}).get("after") for n in ("name", "text") if n in fields]
    payload = fields.get("payload") or {}
    rechecked = merge_gates(text_gates(texts, known_text(session)),
                            payload_gates(payload.get("after"), payload.get("before")) if "payload" in fields else {})
    change.gates = {**(change.gates or {}), **rechecked}
    flag_modified(change, "gates")
    session.flush()  # 반영 동작이 제안을 DB 에서 다시 읽는다(populate_existing) — 고친 값을 먼저 내려 둔다


def _edit_payload(fields: dict[str, Any], current: Mapping[str, Any], sub: str, value: Any) -> None:
    """고쳐 넣기 — 실음 칸 속성 하나(``payload.<칸>``)의 '후' 값을 고친다(처음 실음 칸 전체는 ``proposed``). 빈 값은 칸 빼기."""
    base = current.get("payload") if isinstance(current.get("payload"), dict) else {}
    entry = fields.get("payload") or {"before": copy.deepcopy(base) or None, "after": copy.deepcopy(base)}
    entry.setdefault("proposed", copy.deepcopy(entry.get("after")))
    after = dict(entry.get("after") or {})
    if value is None or value == "" or value == []:
        after.pop(sub, None)
    else:
        after[sub] = value
    entry["after"] = after
    fields["payload"] = entry


def _check_confirm(change: BrainChange, confirm: Optional[Mapping[str, Any]]) -> None:
    """등급 B — 핵심 값 하나를 화면이 보낸 글과 견준다(고쳐 넣기면 고친 값)."""
    if change.grade != GRADE_B:
        return
    field, value = confirm_value(change.op, change.fields, change.item_type)
    got = confirm or {}
    if got.get("field") != field or str(got.get("value", "")) != value:
        raise BrainConfirmError(field)


def apply_decision(session: Any, change_id: Any, *, actor: Any, base_version: Any = None,
                   confirm: Optional[Mapping[str, Any]] = None, edits: Optional[Mapping[str, Any]] = None,
                   view_ms: Any = None, now: Optional[datetime.datetime] = None,
                   bulk: bool = False) -> ApplyResult:
    """넣기 · 고쳐 넣기 — 권한 · 보기 범위 · 기준 판 · (고친 값) · 등급 B 확인을 다시 본 뒤 반영 동작 한 곳으로.

    Raises:
        BrainTargetError · BrainPermissionError · BrainShapeError · BrainConflictError · BrainConfirmError.
    """
    now = now or now_utc_naive()
    expire_ai_proposals(session, now=now)
    change = _locked_open(session, change_id, actor)
    if base_version != change.base_version:
        raise BrainConflictError(_current_version(session, change))
    if edits:
        _apply_edits(session, change, edits)
    if not bulk_ok_any_grade(change.op, change.item_type, change.fields, change.link_kind, wide_bins(viewer_of(actor))):
        _check_confirm(change, confirm)  # ① 이름표만 · ④ 사본 링크만은 확인할 핵심 값(글 · 금액)이 없다(D151 · D167)
    detail = _timing(change, view_ms, now, edited=bool(edits), bulk=bulk)
    action = "bulk_apply" if bulk else ("edit_apply" if edits else "apply")
    return apply_change(session, change.id, actor=actor, now=now, detail=detail, action=action)


def reject_decision(session: Any, change_id: Any, *, actor: Any, code: str, view_ms: Any = None,
                    now: Optional[datetime.datetime] = None) -> BrainChange:
    """거절(까닭 칩) — 권한 · 보기 범위를 다시 본다. 기준 판은 보지 않는다(거절은 정본을 쓰지 않는다)."""
    now = now or now_utc_naive()
    expire_ai_proposals(session, now=now)
    change = _locked_open(session, change_id, actor)
    return reject_change(session, change.id, actor=actor, code=code, now=now, detail=_timing(change, view_ms, now))


def bulk_apply(session: Any, change_ids: Iterable[Any], *, actor: Any,
               now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """한꺼번에 승인 — 등급 A, 또는 관리자의 ① 이름표만 · ④ 사본 링크만 · 상담팀장의 ① 제안(등급 상관없음 — 설계서 7.9 ·
    D151 · D167).

    하나라도 받을 수 없는 제안이 섞이면 아무것도 쓰지 않는다. ① · ④ 는 확인할 핵심 값이 글 · 금액이 아니라서 등급 B 확인 글을
    서버가 채운다(표에서 보인 값 그대로). 하나씩 저장점에서 넣고 막힌 것은 코드로 알린다."""
    now = now or now_utc_naive()
    ids = list(dict.fromkeys(change_ids))
    if not ids or len(ids) > BULK_MAX or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise BrainShapeError([f"ids: 제안 번호 1 ~ {BULK_MAX}개여야 한다"])
    rows = {r.id: r for r in session.execute(select(
        BrainChange.id, BrainChange.grade, BrainChange.op, BrainChange.item_type, BrainChange.fields,
        BrainChange.link_kind).where(BrainChange.id.in_(ids))).all()}
    bins = wide_bins(viewer_of(actor))
    wide = {i for i, r in rows.items() if bulk_ok_any_grade(r.op, r.item_type, r.fields, r.link_kind, bins)}
    if any(i not in rows or (rows[i].grade != GRADE_A and i not in wide) for i in ids):
        raise BrainShapeError(["ids: 한꺼번에 승인은 등급 A, 또는 관리자의 이름표만 · 사본 링크만 · 상담팀장의 이름표만 제안만 받는다"])
    applied, failed = [], []
    for change_id in ids:
        base = session.execute(select(BrainChange.base_version).where(BrainChange.id == change_id)).scalar()
        try:
            confirm = None
            if change_id in wide:
                field, value = confirm_value(rows[change_id].op, rows[change_id].fields, rows[change_id].item_type)
                confirm = {"field": field, "value": value}
            with session.begin_nested():
                result = apply_decision(session, change_id, actor=actor, base_version=base, confirm=confirm, now=now,
                                        bulk=True)
            applied.append({"id": change_id, "version": result.version, "release": result.release_no})
        except BrainError as exc:
            failed.append({"id": change_id, "code": exc.code})
    return {"applied": applied, "failed": failed}

"""반영 동작 — **정본 줄을 쓰는 유일한 길**(설계서 5절 '쓰기는 액션으로만' · 6절 · 7.5 'API ... 정본 쓰기는 반영 동작 한 곳').

:func:`apply_change` 는 열린 제안 하나를 잠그고 다시 확인한다:

1. **권한** — 켜진 내부 사람 계정만(에이전트 시스템 계정은 꺼져 있어 못 한다). 가격 규칙 · 정책 · 사장님 결정과 공통 바탕
   은퇴 · 지우기는 **사장님(ADMIN)만**. 그 밖은 ADMIN 또는 그 층 승인자 팀의 MANAGER(:data:`.constants.LAYER_APPROVER_TEAMS`).
   **그 항목(지금 줄 · 새 보기 범위 · 링크 양 끝)을 볼 수 있어야 한다**(7.7 · D104 — 쓰기 권한이 보기 범위도 본다).
2. **꼴 · 대상** — 값 목록 · 길이 · 날짜 · 유형과 층 · 지식 문서 꼴, 같은 지식 문서 id 겹침, 링크 허용 짝 · 양 끝. 링크
   더하기는 **연결 개수 최대**(:func:`.quality.check_link_limit` — 가격 규칙은 근거 종류별)와 **바깥 정본 자리 실재**
   (:func:`.external.require_refs`)(7.7 · D105), **링크 제약**(근거 종류 끝 · 맞서는 짝 · 고리 — :mod:`.link_rules`, 7.8)도 본다.
   ``supersedes`` 반영은 앞 항목의 유효 끝을 찍은 새 판도 같은 반영에서 쓴다(7.8 다음 2).
3. **기준 판** — 제안을 만든 때의 판이 지금 판과 같아야 한다(다르면 :class:`BrainConflictError` — 제안은 열린 채).

그다음 앞 줄을 닫고(``superseded_at``) 새 판 줄을 쓰고, 제안을 ``applied`` 로 닫고, 그날 판에 붙이고, 감사 원장에 한 줄.
**확신은 이 동작이 정한다**(7.7 · D104 — 제안이 적은 값을 그대로 쓰지 않는다): 옮기기(D102)는 옮긴 값, 사람 승인자가 넣으면
'확정', 관찰 유형은 늘 '관찰'. 같은 항목 · 링크의 다른 열린 제안에는 '기준 판 바뀜' 시각을 적는다(``base_changed_at``).
닫은 액션 이름(``decided_action`` — :mod:`.actions`)을 제안 줄에 남긴다.
은퇴(새 판 · 상태 ``retired``) · 지우기(지금 판 닫기 + 닿은 링크 닫기)도 이 길이다. 거절은 :func:`reject_change`.
커밋은 호출자 몫이다(``flush`` 만). 다시 확인에서 멈추면 그 반영의 쓰기는 저장점으로 되돌리고 제안은 열린 채 둔다.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from foms.persistence.brain.models import BrainChange, BrainLink, BrainObject
from foms.services.brain import releases
from foms.services.brain.access import approval_problem
from foms.services.brain.ai_gates import sources
from foms.services.brain.constants import (
    BRAND_COMMON, BRANDS, CHANGE_APPLIED, CHANGE_OPEN, CHANGE_REJECTED, CONFIRMED, DOC_TYPES, LINK_OPS, OBJECT_OPS,
    OBSERVATION_TYPES, OBSERVED, OP_CREATE, OP_DELETE, OP_LINK_ADD, REJECT_CODES, STALE_DAYS, cardinality,
    external_type, is_doc_item, link_allowed,
)
from foms.services.brain.errors import (
    BrainConflictError, BrainPermissionError, BrainShapeError, BrainTargetError,
)
from foms.services.brain.external import require_refs
from foms.services.brain.gates import link_problems, object_problems
from foms.services.brain.link_rules import check_link_rules, superseded_end
from foms.services.brain.proposals import IMPORT_PROPOSER, link_target_type
from foms.services.brain.quality import check_link_limit
from foms.services.brain.scope import can_see, viewer_of
from foms.services.brain.store import (
    LINK_FIELDS, OBJECT_FIELDS, column_values, current_link, current_object, is_current, kst_day, values_of,
)
from foms.services.datetime_kst import now_utc_naive
from models import SecurityLog

SUPERSEDES = "supersedes"


@dataclass(frozen=True)
class ApplyResult:
    """반영 결과 — 제안 id · 동작 · 키 · 새 판(지우기 · 링크 빼기는 ``None``) · 판 번호."""

    change_id: int
    op: str
    key: str
    version: Optional[int]
    release_no: int


def check_permission(actor: Any, *, op: str, layer: Optional[str], types: Iterable[Optional[str]],
                     visibilities: Iterable[Optional[str]] = ()) -> int:
    """반영 · 거절 권한을 확인하고 사람 id 를 돌려준다(판정은 :func:`.access.approval_problem` 하나 + 보기 범위).

    Args:
        visibilities: 닿는 줄들의 보기 범위(지금 줄 · 새 값 · 링크 양 끝) — 하나라도 볼 수 없으면 권한 없음.

    Raises:
        BrainPermissionError: 사람 아님 · 꺼짐 · 바깥 역할 · 사장님 몫 · 층 승인자 아님 · 볼 수 없는 항목.
    """
    viewer = viewer_of(actor)
    problem = approval_problem(viewer, op=op, layer=layer, types=types)
    if problem is not None or viewer.user_id is None:
        raise BrainPermissionError(problem or "켜진 내부 사람 계정만 반영한다")
    if not all(can_see(viewer, v) for v in visibilities if v):
        raise BrainPermissionError("볼 수 없는 항목이다")
    return viewer.user_id


def settled_confidence(item_type: Optional[str], declared: Optional[str], *, as_import: bool) -> str:
    """새 판의 확신 — 옮기기(D102)만 옮긴 값을 쓰고, 그 밖은 사람 승인자가 넣은 것이라 '확정'(관찰 유형은 늘 '관찰')."""
    if as_import and declared:
        return declared
    return OBSERVED if item_type in OBSERVATION_TYPES else CONFIRMED


def _link_end_visibility(session: Any, key: Optional[str]) -> Optional[str]:
    """링크 끝의 보기 범위(바깥 정본 자리 · 없는 끝은 ``None`` — 보는 일 없음)."""
    if not key or external_type(key) is not None:
        return None
    row = current_object(session, key)
    return row.visibility if row is not None else None


def source_type(session: Any, key: Optional[str]) -> Optional[str]:
    """링크 시작 항목의 유형(없으면 ``None``) — 잠그기 전에 연결 개수 규칙이 있는 짝인지 보려고."""
    row = current_object(session, key) if key else None
    return row.item_type if row is not None else None


def _open_change(session: Any, change_id: int) -> BrainChange:
    """열린 제안을 잠가 읽는다."""
    change = session.get(BrainChange, int(change_id), with_for_update=True, populate_existing=True)
    if change is None or change.status != CHANGE_OPEN:
        raise BrainTargetError(f"열린 제안이 아니다: {change_id}")
    return change


def _after(change: BrainChange) -> dict[str, Any]:
    """제안의 칸별 '후' 값."""
    return {name: (entry or {}).get("after") for name, entry in (change.fields or {}).items()}


def _locked_current(session: Any, key: str) -> Optional[BrainObject]:
    """지금 줄을 잠가 읽는다. 잠금을 기다리는 사이 앞 세션이 그 줄을 닫고 새 판을 넣었으면(READ COMMITTED 는 닫힌 줄만
    다시 보고 새 줄은 못 본다) 새 문장으로 한 번 더 읽어 새 판을 잠근다 — 기준 판 충돌을 정확한 지금 판으로 알리게."""
    current = current_object(session, key, lock=True)
    return current if current is not None else current_object(session, key, lock=True)


def _check_object_target(change: BrainChange, current: Optional[BrainObject]) -> None:
    """만들기는 지금 판이 없어야, 그 밖은 정체 칸이 같고 기준 판이 지금 판이어야 한다."""
    if change.op == OP_CREATE:
        if current is not None:
            raise BrainConflictError(current.version)
        return
    if current is None:
        raise BrainConflictError(None)
    if (current.brand, current.layer, current.item_type) != (change.brand, change.layer, change.item_type):
        raise BrainTargetError("정체 칸(브랜드 · 층 · 유형)이 제안과 다르다")
    if current.version != change.base_version:
        raise BrainConflictError(current.version)


def _doc_collision(session: Any, change: BrainChange, values: dict[str, Any]) -> None:
    """지식 문서 유형 — 같은 브랜드(공통은 모든 브랜드와 겹친다) 지금 줄에 같은 문서 id 가 있으면 대상 오류."""
    if not is_doc_item(change.item_type, values.get("payload")):
        return
    doc_id = (values.get("payload") or {}).get("doc_id")
    brands = BRANDS if change.brand == BRAND_COMMON else (change.brand, BRAND_COMMON)
    rows = session.execute(select(BrainObject.payload).where(
        is_current(BrainObject), BrainObject.item_type.in_(DOC_TYPES), BrainObject.brand.in_(brands),
        BrainObject.item_key != change.item_key)).scalars()
    if any((payload or {}).get("doc_id") == doc_id for payload in rows):
        raise BrainTargetError(f"같은 지식 문서 id 의 지금 항목이 있다: {doc_id}")


def _stale_after(item_type: str, checked_at: Optional[datetime.date]) -> Optional[datetime.date]:
    """낡음 날 = 마지막 확인 날 + 유형별 주기(주기 없는 유형은 없음)."""
    days = STALE_DAYS.get(item_type)
    return checked_at + datetime.timedelta(days=days) if days and checked_at else None


def _insert_version(session: Any, row: Any, current_version: Optional[int]) -> None:
    """새 판 줄 — 같은 때 들어온 만들기와 부분 유일 색인에서 갈리면 충돌로 알린다."""
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        raise BrainConflictError(current_version) from None


def _close(session: Any, row: Any, now: datetime.datetime) -> None:
    """지금 줄을 닫는다 — 새 줄보다 먼저 flush 해 '지금 판 하나' 자리를 비운다."""
    row.superseded_at = now
    session.flush()


def _write_object(session: Any, change: BrainChange, current: Optional[BrainObject], values: Optional[dict[str, Any]],
                  *, approver_id: Optional[int], release_no: int, now: datetime.datetime) -> Optional[int]:
    """앞 줄 닫기 → 새 판 줄(지우기면 닿은 링크 닫기). 새 판 번호를 돌려준다."""
    if current is not None:
        _close(session, current, now)
    if values is None:
        session.execute(update(BrainLink).where(
            is_current(BrainLink), or_(BrainLink.from_key == change.item_key, BrainLink.to_key == change.item_key),
        ).values(superseded_at=now).execution_options(synchronize_session=False))
        return None
    top = session.execute(select(func.max(BrainObject.version)).where(
        BrainObject.item_key == change.item_key)).scalar()
    columns = column_values(values)
    row = BrainObject(
        item_key=change.item_key, version=int(top or 0) + 1, brand=change.brand, layer=change.layer,
        item_type=change.item_type, **columns, stale_after=_stale_after(change.item_type, columns.get("checked_at")),
        evidence_count=len(sources(change.evidence or [])), usage_count=current.usage_count if current is not None else 0,
        recorded_at=now, created_by=change.proposed_by, human_approver_id=approver_id, change_id=change.id,
        release_no=release_no)
    _insert_version(session, row, current.version if current is not None else None)
    return row.version


def _apply_object(session: Any, change: BrainChange, actor: Any, *, now: datetime.datetime,
                  as_import: bool) -> tuple[int, Optional[int], int]:
    """항목 동작 — (사람 id, 새 판, 판 번호)."""
    current = _locked_current(session, change.item_key)
    values: Optional[dict[str, Any]] = None
    if change.op != OP_DELETE:
        base = values_of(current) if current is not None else dict.fromkeys(OBJECT_FIELDS)
        values = {**base, **_after(change)}
        values["confidence"] = settled_confidence(change.item_type, values.get("confidence"), as_import=as_import)
    seen = [current.visibility if current is not None else None, (values or {}).get("visibility")]
    actor_id = check_permission(actor, op=change.op, layer=change.layer, types=[change.item_type], visibilities=seen)
    _check_object_target(change, current)
    if values is not None:
        problems = object_problems(values, brand=change.brand, layer=change.layer, item_type=change.item_type)
        if problems:
            raise BrainShapeError(problems)
        _doc_collision(session, change, values)
    release_no = releases.attach(session, layer=change.layer, op=change.op, key=change.item_key, actor_id=actor_id,
                                 now=now, as_import=as_import)
    version = _write_object(session, change, current, values, approver_id=None if as_import else actor_id,
                            release_no=release_no, now=now)
    return actor_id, version, release_no


def _apply_link(session: Any, change: BrainChange, actor: Any, *, now: datetime.datetime,
                as_import: bool) -> tuple[int, Optional[int], int]:
    """링크 동작 — 양 끝 · 허용 짝 · 기준 판을 다시 보고 새 판 줄(더하기) 또는 지금 줄 닫기(빼기).

    빼기는 허용 짝을 다시 보지 않는다(짝 표가 바뀐 옛 링크도 끊을 수 있게 — 7.8 다음 5). 더하기는 링크 제약(:mod:`.link_rules`)
    도 다시 보고, ``supersedes`` 면 앞 항목의 유효 끝을 찍는다(:func:`_end_superseded` — 7.8 다음 2)."""
    adding = change.op == OP_LINK_ADD
    limited = adding and cardinality(source_type(session, change.link_from), change.link_kind)[1] is not None
    # 연결 개수 상한이 있는 짝은 시작 항목 줄을 잠근 뒤 센다 — 같은 때 두 반영이 같은 항목에 더하지 못하게(D105)
    source = current_object(session, change.link_from, lock=limited)
    to_type = link_target_type(session, change.link_to)
    if source is None or to_type is None or (adding and not link_allowed(source.item_type, change.link_kind, to_type)):
        raise BrainTargetError(f"허용하지 않는 링크 짝이거나 끝이 없다: {change.link_kind}")
    actor_id = check_permission(actor, op=change.op, layer=source.layer, types=[source.item_type, to_type],
                                visibilities=[source.visibility, _link_end_visibility(session, change.link_to)])
    if adding:  # 바깥 정본 자리가 지금도 있나 · 연결 개수 최대(7.7 · D105) · 링크 제약(7.8) — 빼기는 보지 않는다
        require_refs(session, [change.link_to])
        check_link_limit(session, source, change.link_kind, kst_day(now))
        check_link_rules(session, source, change.link_kind, change.link_to, to_type, kst_day(now))
    identity = (change.link_kind, change.link_from, change.link_to)
    link = current_link(session, *identity, lock=True)
    if link is None:  # :func:`_locked_current` 와 같은 까닭
        link = current_link(session, *identity, lock=True)
    if (link.version if link is not None else None) != change.base_version:
        raise BrainConflictError(link.version if link is not None else None)
    values = {**dict.fromkeys(LINK_FIELDS), **_after(change)} if adding else None
    if values is not None:
        values["confidence"] = settled_confidence(None, values.get("confidence"), as_import=as_import)
    if values is not None and link_problems(values, change.link_kind):
        raise BrainShapeError(link_problems(values, change.link_kind))
    key = f"{change.link_kind}:{change.link_from}>{change.link_to}"[:200]
    release_no = releases.attach(session, layer=source.layer, op=change.op, key=key, actor_id=actor_id, now=now,
                                 as_import=as_import)
    if link is not None:
        _close(session, link, now)
    if values is None:
        return actor_id, None, release_no
    top = session.execute(select(func.max(BrainLink.version)).where(
        BrainLink.kind == change.link_kind, BrainLink.from_key == change.link_from,
        BrainLink.to_key == change.link_to)).scalar()
    row = BrainLink(kind=change.link_kind, from_key=change.link_from, to_key=change.link_to, version=int(top or 0) + 1,
                    **column_values(values), recorded_at=now, created_by=change.proposed_by,
                    human_approver_id=None if as_import else actor_id, change_id=change.id, release_no=release_no)
    _insert_version(session, row, None)
    if change.link_kind == SUPERSEDES:
        _end_superseded(session, change, source, approver_id=None if as_import else actor_id, release_no=release_no,
                        now=now)
    return actor_id, row.version, release_no


def _end_superseded(session: Any, change: BrainChange, decision: BrainObject, *, approver_id: Optional[int],
                    release_no: int, now: datetime.datetime) -> None:
    """``supersedes`` 반영 — 앞 항목의 유효 끝을 새 결정의 유효 시작 전날(없으면 반영 날)로 찍은 새 판(7.8 다음 2).

    이미 그보다 이르게 끝나는 항목과 아직 시작 전인 앞 항목(유효 시작이 끝 날보다 뒤 — 효력을 갖기 전에 대체됐다. 대체 링크가
    읽기에서 뺀다)은 그대로 둔다. 새 판은 이 링크 제안 · 판 번호에 붙고, 그 항목의 다른 열린 제안에는 '기준 판 바뀜'을 적는다.
    판 되돌리기(:mod:`.rollback`)는 링크만 뺀다 — 찍은 유효 끝은 그 항목 되돌리기(옛 판을 새 제안으로)로 푼다."""
    target = current_object(session, change.link_to, lock=True)
    end = superseded_end(decision.valid_from, kst_day(now))
    if target is None or (target.valid_to is not None and target.valid_to <= end) or (
            target.valid_from is not None and target.valid_from > end):
        return
    values = {**values_of(target), "valid_to": end.isoformat()}
    problems = object_problems(values, brand=target.brand, layer=target.layer, item_type=target.item_type)
    if problems:
        raise BrainShapeError(problems)
    _close(session, target, now)
    columns = column_values(values)
    top = session.execute(select(func.max(BrainObject.version)).where(BrainObject.item_key == target.item_key)).scalar()
    row = BrainObject(
        item_key=target.item_key, version=int(top or 0) + 1, brand=target.brand, layer=target.layer,
        item_type=target.item_type, **columns, stale_after=target.stale_after, evidence_count=target.evidence_count,
        usage_count=target.usage_count, recorded_at=now, created_by=change.proposed_by, human_approver_id=approver_id,
        change_id=change.id, release_no=release_no)
    _insert_version(session, row, target.version)
    session.execute(update(BrainChange).where(
        BrainChange.status == CHANGE_OPEN, BrainChange.op.in_(OBJECT_OPS), BrainChange.item_key == target.item_key,
        BrainChange.base_changed_at.is_(None)).values(base_changed_at=now).execution_options(synchronize_session="fetch"))


def _audit(session: Any, actor_id: int, change: BrainChange, verb: str, detail: dict[str, Any],
           now: datetime.datetime) -> None:
    """감사 원장 한 줄(키 · 동작 · 판 · 숫자 — 글 없음). 시각은 결정 시각(UTC naive) 그대로 — 결정 숫자(:mod:`.metrics`)가 센다."""
    session.add(SecurityLog(user_id=actor_id, action=f"BRAIN_{verb}", target_type="brain_change", target_id=change.id,
                            timestamp=now,
                            message=f"BRAIN_{verb} change={change.id} op={change.op} key={change.item_key} "
                                    + " ".join(f"{k}={v}" for k, v in detail.items()), detail=detail))


def _flag_siblings(session: Any, change: BrainChange, now: datetime.datetime) -> None:
    """같은 항목(링크)의 다른 열린 제안에 '기준 판 바뀜' 시각을 적는다 — 지우기는 그 항목에 닿은 링크 제안까지."""
    if change.op in LINK_OPS:
        target = and_(BrainChange.op.in_(LINK_OPS), BrainChange.link_kind == change.link_kind,
                      BrainChange.link_from == change.link_from, BrainChange.link_to == change.link_to)
    else:
        target = and_(BrainChange.op.in_(OBJECT_OPS), BrainChange.item_key == change.item_key)
    clauses = [target]
    if change.op == OP_DELETE:
        clauses.append(and_(BrainChange.op.in_(LINK_OPS), or_(BrainChange.link_from == change.item_key,
                                                             BrainChange.link_to == change.item_key)))
    session.execute(update(BrainChange).where(
        BrainChange.status == CHANGE_OPEN, BrainChange.id != change.id, BrainChange.base_changed_at.is_(None),
        or_(*clauses)).values(base_changed_at=now).execution_options(synchronize_session="fetch"))


def apply_change(session: Any, change_id: int, *, actor: Any, now: Optional[datetime.datetime] = None,
                 as_import: bool = False, detail: Optional[Mapping[str, Any]] = None,
                 action: str = "apply") -> ApplyResult:
    """열린 제안 하나를 반영한다(커밋은 호출자).

    Args:
        session: DB 세션.
        change_id: 제안 id.
        actor: 반영하는 사람(로그인 사용자 — 결정한 사람 번호는 여기서만 받는다).
        now: 시험 주입(UTC naive).
        as_import: 지식 문서 옮기기(:mod:`.doc_import`) — 옮기기 제안만, 판 0 에 붙고 사람 승인자 칸은 비운다.
        detail: 감사 줄에 더할 숫자 · 코드(결정 시간 · 고쳐 넣음 · 다시 확인 같은 측정 — 글 없음).
        action: 이 반영을 부른 액션 이름(:mod:`.actions` — 제안 줄 ``decided_action`` · 감사 줄).

    Raises:
        BrainTargetError · BrainPermissionError · BrainShapeError · BrainConflictError.
    """
    now = now or now_utc_naive()
    change = _open_change(session, change_id)
    if as_import and change.proposed_by != IMPORT_PROPOSER.name:
        raise BrainTargetError("옮기기 반영은 옮기기 제안만 받는다")
    run = _apply_object if change.op in OBJECT_OPS else _apply_link
    with session.begin_nested():  # 다시 확인에서 멈추면 판 줄 · 앞 줄 닫기가 반쯤 남지 않게
        actor_id, version, release_no = run(session, change, actor, now=now, as_import=as_import)
    change.status, change.decided_by, change.decided_at = CHANGE_APPLIED, actor_id, now
    change.result_version, change.release_no = version, release_no
    change.decided_action = "import" if as_import else action
    _flag_siblings(session, change, now)
    _audit(session, actor_id, change, "APPLY", {"version": version, "release": release_no,
                                                "action": change.decided_action, **dict(detail or {})}, now)
    session.flush()
    return ApplyResult(change.id, change.op, change.item_key, version, release_no)


def _reject_visibilities(session: Any, change: BrainChange) -> list[Optional[str]]:
    """거절도 볼 수 있어야 한다 — 항목 동작은 지금 줄 · 새 보기 범위, 링크는 양 끝."""
    if change.op in LINK_OPS:
        return [_link_end_visibility(session, change.link_from), _link_end_visibility(session, change.link_to)]
    current = current_object(session, change.item_key)
    after = ((change.fields or {}).get("visibility") or {}).get("after")
    return [current.visibility if current is not None else None, after]


def reject_change(session: Any, change_id: int, *, actor: Any, code: str, now: Optional[datetime.datetime] = None,
                  detail: Optional[Mapping[str, Any]] = None) -> BrainChange:
    """열린 제안을 거절한다(까닭 칩 — 같은 제안이 다시 오지 않게 남긴다). 권한은 반영과 같다. 커밋은 호출자.

    ``detail`` 은 감사 줄에 더할 숫자 · 코드(결정 시간 같은 측정)."""
    if code not in REJECT_CODES:
        raise BrainShapeError([f"code: {' / '.join(REJECT_CODES)} 가운데 하나여야 한다"])
    now = now or now_utc_naive()
    change = _open_change(session, change_id)
    types = [change.item_type] + ([link_target_type(session, change.link_to)] if change.link_to else [])
    actor_id = check_permission(actor, op=change.op, layer=change.layer, types=types,
                                visibilities=_reject_visibilities(session, change))
    change.status, change.reject_code, change.decided_by, change.decided_at = CHANGE_REJECTED, code, actor_id, now
    change.decided_action = "reject"
    _audit(session, actor_id, change, "REJECT", {"code": code, "action": "reject", **dict(detail or {})}, now)
    session.flush()
    return change

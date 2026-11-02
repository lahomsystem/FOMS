"""반영 동작 — **정본 줄을 쓰는 유일한 길**(설계서 5절 '쓰기는 액션으로만' · 6절 · 7.5 'API ... 정본 쓰기는 반영 동작 한 곳').

:func:`apply_change` 는 열린 제안 하나를 잠그고 다시 확인한다:

1. **권한** — 켜진 내부 사람 계정만(에이전트 시스템 계정은 꺼져 있어 못 한다). 가격 규칙 · 정책 · 사장님 결정과 공통 바탕
   은퇴 · 지우기는 **사장님(ADMIN)만**. 그 밖은 ADMIN 또는 그 층 승인자 팀의 MANAGER(:data:`.constants.LAYER_APPROVER_TEAMS`).
2. **꼴 · 대상** — 값 목록 · 길이 · 날짜 · 유형과 층 · 지식 문서 꼴, 같은 지식 문서 id 겹침, 링크 허용 짝 · 양 끝.
3. **기준 판** — 제안을 만든 때의 판이 지금 판과 같아야 한다(다르면 :class:`BrainConflictError` — 제안은 열린 채).

그다음 앞 줄을 닫고(``superseded_at``) 새 판 줄을 쓰고, 제안을 ``applied`` 로 닫고, 그날 판에 붙이고, 감사 원장에 한 줄.
은퇴(새 판 · 상태 ``retired``) · 지우기(지금 판 닫기 + 닿은 링크 닫기)도 이 길이다. 거절은 :func:`reject_change`.
커밋은 호출자 몫이다(``flush`` 만). 다시 확인에서 멈추면 그 반영의 쓰기는 저장점으로 되돌리고 제안은 열린 채 둔다.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from foms.persistence.brain.models import BrainChange, BrainLink, BrainObject
from foms.services.brain import releases
from foms.services.brain.constants import (
    BRAND_COMMON, BRANDS, CHANGE_APPLIED, CHANGE_OPEN, CHANGE_REJECTED, DOC_TYPES, LAYER_APPROVER_TEAMS, LAYER_COMMON,
    OBJECT_OPS, OP_CREATE, OP_DELETE, OP_LINK_ADD, OP_RETIRE, OWNER_ONLY_TYPES, REJECT_CODES, STALE_DAYS,
    link_allowed,
)
from foms.services.brain.errors import (
    BrainConflictError, BrainPermissionError, BrainShapeError, BrainTargetError,
)
from foms.services.brain.gates import link_problems, object_problems
from foms.services.brain.proposals import IMPORT_PROPOSER, link_target_type
from foms.services.brain.scope import ROLE_MANAGER, viewer_of
from foms.services.brain.store import (
    LINK_FIELDS, OBJECT_FIELDS, column_values, current_link, current_object, is_current, values_of,
)
from foms.services.datetime_kst import now_utc_naive
from models import SecurityLog


@dataclass(frozen=True)
class ApplyResult:
    """반영 결과 — 제안 id · 동작 · 키 · 새 판(지우기 · 링크 빼기는 ``None``) · 판 번호."""

    change_id: int
    op: str
    key: str
    version: Optional[int]
    release_no: int


def check_permission(actor: Any, *, op: str, layer: Optional[str], types: Iterable[Optional[str]]) -> int:
    """반영 · 거절 권한을 확인하고 사람 id 를 돌려준다.

    Raises:
        BrainPermissionError: 사람 아님 · 꺼짐 · 바깥 역할 · 사장님 몫 · 층 승인자 아님.
    """
    viewer = viewer_of(actor)
    if not viewer.internal or viewer.user_id is None:
        raise BrainPermissionError("켜진 내부 사람 계정만 반영한다")
    if viewer.is_admin:
        return viewer.user_id
    if any(t in OWNER_ONLY_TYPES for t in types) or (op in (OP_RETIRE, OP_DELETE) and layer == LAYER_COMMON):
        raise BrainPermissionError("사장님(ADMIN)만 반영한다 — 가격 · 정책 · 사장님 결정 · 공통 바탕 은퇴 · 지우기")
    team = LAYER_APPROVER_TEAMS.get(layer or "")
    if viewer.role == ROLE_MANAGER and team is not None and viewer.team == team:
        return viewer.user_id
    raise BrainPermissionError("이 층 승인자가 아니다")


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
    if change.item_type not in DOC_TYPES:
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
        evidence_count=len(change.evidence or []), usage_count=current.usage_count if current is not None else 0,
        recorded_at=now, created_by=change.proposed_by, human_approver_id=approver_id, change_id=change.id,
        release_no=release_no)
    _insert_version(session, row, current.version if current is not None else None)
    return row.version


def _apply_object(session: Any, change: BrainChange, actor: Any, *, now: datetime.datetime,
                  as_import: bool) -> tuple[int, Optional[int], int]:
    """항목 동작 — (사람 id, 새 판, 판 번호)."""
    current = _locked_current(session, change.item_key)
    actor_id = check_permission(actor, op=change.op, layer=change.layer, types=[change.item_type])
    _check_object_target(change, current)
    values: Optional[dict[str, Any]] = None
    if change.op != OP_DELETE:
        base = values_of(current) if current is not None else dict.fromkeys(OBJECT_FIELDS)
        values = {**base, **_after(change)}
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
    """링크 동작 — 양 끝 · 허용 짝 · 기준 판을 다시 보고 새 판 줄(더하기) 또는 지금 줄 닫기(빼기)."""
    source, to_type = current_object(session, change.link_from), link_target_type(session, change.link_to)
    if source is None or to_type is None or not link_allowed(source.item_type, change.link_kind, to_type):
        raise BrainTargetError(f"허용하지 않는 링크 짝이거나 끝이 없다: {change.link_kind}")
    actor_id = check_permission(actor, op=change.op, layer=source.layer, types=[source.item_type, to_type])
    identity = (change.link_kind, change.link_from, change.link_to)
    link = current_link(session, *identity, lock=True)
    if link is None:  # :func:`_locked_current` 와 같은 까닭
        link = current_link(session, *identity, lock=True)
    if (link.version if link is not None else None) != change.base_version:
        raise BrainConflictError(link.version if link is not None else None)
    values = {**dict.fromkeys(LINK_FIELDS), **_after(change)} if change.op == OP_LINK_ADD else None
    if values is not None and link_problems(values):
        raise BrainShapeError(link_problems(values))
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
    return actor_id, row.version, release_no


def _audit(session: Any, actor_id: int, change: BrainChange, verb: str, detail: dict[str, Any]) -> None:
    """감사 원장 한 줄(키 · 동작 · 판 — 글 없음)."""
    session.add(SecurityLog(user_id=actor_id, action=f"BRAIN_{verb}", target_type="brain_change", target_id=change.id,
                            message=f"BRAIN_{verb} change={change.id} op={change.op} key={change.item_key} "
                                    + " ".join(f"{k}={v}" for k, v in detail.items()), detail=detail))


def apply_change(session: Any, change_id: int, *, actor: Any, now: Optional[datetime.datetime] = None,
                 as_import: bool = False) -> ApplyResult:
    """열린 제안 하나를 반영한다(커밋은 호출자).

    Args:
        session: DB 세션.
        change_id: 제안 id.
        actor: 반영하는 사람(로그인 사용자 — 결정한 사람 번호는 여기서만 받는다).
        now: 시험 주입(UTC naive).
        as_import: 지식 문서 옮기기(:mod:`.doc_import`) — 옮기기 제안만, 판 0 에 붙고 사람 승인자 칸은 비운다.

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
    _audit(session, actor_id, change, "APPLY", {"version": version, "release": release_no})
    session.flush()
    return ApplyResult(change.id, change.op, change.item_key, version, release_no)


def reject_change(session: Any, change_id: int, *, actor: Any, code: str,
                  now: Optional[datetime.datetime] = None) -> BrainChange:
    """열린 제안을 거절한다(까닭 칩 — 같은 제안이 다시 오지 않게 남긴다). 권한은 반영과 같다. 커밋은 호출자."""
    if code not in REJECT_CODES:
        raise BrainShapeError([f"code: {' / '.join(REJECT_CODES)} 가운데 하나여야 한다"])
    now = now or now_utc_naive()
    change = _open_change(session, change_id)
    types = [change.item_type] + ([link_target_type(session, change.link_to)] if change.link_to else [])
    actor_id = check_permission(actor, op=change.op, layer=change.layer, types=types)
    change.status, change.reject_code, change.decided_by, change.decided_at = CHANGE_REJECTED, code, actor_id, now
    _audit(session, actor_id, change, "REJECT", {"code": code})
    session.flush()
    return change

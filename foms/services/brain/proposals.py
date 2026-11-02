"""제안 만들기 — 에이전트 · 사람은 **제안만** 만든다(설계서 5절 '액션으로만' · 6절 · 7.5 승인 흐름). 정본은 :mod:`.apply` 가 쓴다.

제안 하나 = 바꿀 항목 · 칸별 전 → 후 · 기준 판 · 까닭 · 근거 id · 등급 · 층. 만들 때 꼴 검사와 글 관문(:mod:`.gates`)을 돌려
결과를 ``gates`` 에 남긴다. **에이전트 제안**은 글 관문 하나라도 떨어지면 제안함에 넣지 않는다(:class:`BrainGateError`).
에이전트 제안은 **안 돌던 관문 셋**(부딪침 — 두 순서 · 서로 다른 근거 2곳 · 평가 묶음 재시험 — :mod:`.ai_gates`, 7.7 · D105)도
실제로 돌리고, 떨어지거나 부딪침 판정을 못 하면 넣지 않는다. 사람 · 옮기기 제안은 예전 그대로 결과만 남기고(``not_run``)
승인자가 본다.

- 링크 더하기 제안은 바깥 정본 끝(``calc:`` · ``setting:`` · ``erp:stage/``)이 정말 있는지 본다(:func:`.external.require_refs` —
  7.7 · D105)과 링크 제약(근거 종류 · 맞서는 짝 · 고리 — :func:`.link_rules.check_link_rules`, 7.8)을 본다. 빼기는 허용 짝이
  바뀐 옛 링크(그림 조각 종류 → 제품 라인 ``applies_to`` 등)도 끊을 수 있게 짝 표를 다시 보지 않는다.
- 은퇴 · 지우기도 제안이다(7.5 — 지우기가 승인을 비켜 가지 않게). 항목 하나 되돌리기 = **옛 값을 새 제안으로**
  (:func:`propose_rollback`).
- **제안은 확신 값을 정하지 않는다**(7.7 · D104 — '확정'은 사람 승인 또는 옮기기만): 옮기기 제안이 아니면 적힌 확신 값을
  버리고 제안 칸에도 싣지 않는다. 반영 동작이 정한다(:func:`.apply.settled_confidence`). 링크 제안도 기본 '확정'이 없다.
- 제안 줄에 만든 액션 이름(``action`` — :mod:`.actions`)을 남긴다(옮기기는 늘 ``import``).
- 커밋은 호출자 몫이다(``flush`` 만).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainChange, BrainObject
from foms.services.brain.ai_gates import blocking, run_ai_gates
from foms.services.brain.constants import (
    AGENT_WORK_TYPES, CHANGE_OPEN, CHANGE_REJECTED, CONFIRMED, OBSERVED, GRADE_A, GRADE_B, GRADES, KEY_RE, MAX_EVIDENCE, MAX_REASON,
    MAX_REF, OP_CREATE, OP_DELETE, OP_LINK_ADD, OP_LINK_REMOVE, OP_RETIRE, OP_UPDATE, STATUS_ACTIVE, STATUS_RETIRED,
    TYPE_GRADES, external_type, heavier_grade, link_allowed, value_problems,
)
from foms.services.brain.errors import (
    BrainConflictError, BrainGateError, BrainRejectedError, BrainShapeError, BrainTargetError,
)
from foms.services.brain.external import require_refs
from foms.services.brain.gates import FAIL, end_key_problems, key_problems, link_problems, object_problems, text_gates
from foms.services.brain.link_rules import check_link_rules
from foms.services.brain.store import (
    LINK_FIELDS, OBJECT_FIELDS, current_link, current_object, is_current, kst_day, object_version, values_of,
)
from foms.services.datetime_kst import now_utc_naive

_NOT_RUN = {"conflict": "not_run", "evidence": "not_run", "eval": "unavailable"}


@dataclass(frozen=True)
class Proposer:
    """제안한 이 — ``user:<id>`` · ``agent:<이름>`` · ``import``. 에이전트면 글 관문이 막는다."""

    name: str
    agent: bool = False

    @classmethod
    def user(cls, user_id: int) -> "Proposer":
        """사람(로그인 사용자)."""
        return cls(f"user:{int(user_id)}")

    @classmethod
    def agent_named(cls, name: str) -> "Proposer":
        """에이전트(상담 · 도면 · 생산 · 챗봇 등) — 이름은 짧은 소문자 키."""
        if not KEY_RE.fullmatch(name) or len(name) > 50:
            raise BrainShapeError(["proposer: 에이전트 이름이 짧은 소문자 키가 아니다"])
        return cls(f"agent:{name}", agent=True)


IMPORT_PROPOSER = Proposer("import")


def _trusted(proposer: Proposer) -> bool:
    """확신 값을 그대로 둘 제안(옮기기 — D102)인가."""
    return proposer.name == IMPORT_PROPOSER.name


def known_text(session: Any) -> str:
    """숫자 관문의 허용 목록 — 지금 반영된 · 확정(사람 승인) 항목 글 전부."""
    rows = session.execute(select(BrainObject.text).where(
        is_current(BrainObject), BrainObject.status == STATUS_ACTIVE, BrainObject.confidence == CONFIRMED)).scalars()
    return "\n".join(t for t in rows if t)


def _common_problems(reason: Any, evidence: Any, grade: Any) -> list[str]:
    """까닭 · 근거 id · 등급 꼴."""
    problems = []
    if not isinstance(reason, str) or not reason.strip() or len(reason) > MAX_REASON:
        problems.append(f"reason: 1 ~ {MAX_REASON}자 글이어야 한다")
    if not isinstance(evidence, (list, tuple)) or len(evidence) > MAX_EVIDENCE or not all(
            isinstance(e, str) and e.strip() and len(e) <= MAX_REF and "\n" not in e for e in evidence):
        problems.append(f"evidence: {MAX_EVIDENCE}개 이하 한 줄 글 목록이어야 한다")
    if grade is not None and grade not in GRADES:
        problems.append(f"grade: {' / '.join(GRADES)} 가운데 하나여야 한다")
    return problems


def _gates(texts: Iterable[Optional[str]], known: str, proposer: Proposer,
           item_type: Optional[str] = None) -> dict[str, str]:
    """글 관문 결과. 에이전트 제안이 떨어지면 넣지 않는다 — 에이전트 일 유형(엇갈림 · 물어볼 것)은 지식이 아니라 알림이라
    숫자 출처 관문은 결과만 남기고 막지 않는다(직원 고칠 말의 숫자 — 가림 · 한자는 그대로 막는다)."""
    result = text_gates(texts, known)
    failed = [name for name, value in result.items()
              if value == FAIL and not (name == "numbers" and item_type in AGENT_WORK_TYPES)]
    if proposer.agent and failed:
        raise BrainGateError(failed)
    return {"form": "pass", **result, **_NOT_RUN}


def _ai_gates(session: Any, gates: dict[str, str], proposer: Proposer, **kwargs: Any) -> dict[str, str]:
    """에이전트 제안이면 관문 셋(:mod:`.ai_gates`)을 돌려 결과를 얹는다 — 막는 관문이 있으면 넣지 않는다. 사람은 그대로."""
    if not proposer.agent:
        return gates
    result = run_ai_gates(session, **kwargs)
    failed = blocking(result)
    if failed:
        raise BrainGateError(failed)
    return {**gates, **result}


def after_values(fields: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """제안 ``fields`` 의 칸별 '후' 값(같은 제안 견주기 · 반영이 같이 쓴다)."""
    return {name: (entry or {}).get("after") for name, entry in (fields or {}).items()}


def _rejected_before(session: Any, columns: Mapping[str, Any]) -> None:
    """같은 항목 · 동작 · 링크 · 새 값의 제안이 이미 거절됐으면 막는다(7.5 거절 까닭 — 같은 제안이 다시 오지 않게)."""
    rows = session.execute(select(BrainChange.fields, BrainChange.reject_code).where(
        BrainChange.item_key == columns.get("item_key"), BrainChange.status == CHANGE_REJECTED,
        BrainChange.op == columns["op"], BrainChange.link_kind.is_(columns.get("link_kind"))
        if columns.get("link_kind") is None else BrainChange.link_kind == columns["link_kind"],
        BrainChange.link_to.is_(None) if columns.get("link_to") is None else BrainChange.link_to == columns["link_to"],
    ).order_by(BrainChange.id.desc())).all()
    wanted = after_values(columns.get("fields"))
    for fields, code in rows:
        if after_values(fields) == wanted:
            raise BrainRejectedError(code)


def _insert(session: Any, *, now: Optional[datetime.datetime], **columns: Any) -> BrainChange:
    """열린 제안 한 줄을 넣는다(flush 만). 같은 제안이 이미 거절됐으면 :class:`BrainRejectedError` — 되돌리기 제안
    (``rollback_of_version`` 있음 — 옛 값을 다시 넣는 일)은 앞 거절에 막히지 않는다."""
    if columns.get("rollback_of_version") is None:
        _rejected_before(session, columns)
    if columns.get("proposed_by") == IMPORT_PROPOSER.name:
        columns["action"] = "import"
    change = BrainChange(status=CHANGE_OPEN, created_at=now or now_utc_naive(), **columns)
    session.add(change)
    session.flush()
    return change


def _target(session: Any, key: str, base_version: Any) -> BrainObject:
    """고칠 · 은퇴 · 지울 지금 줄 — 없으면 대상 오류, 기준 판이 다르면 충돌."""
    current = current_object(session, key)
    if current is None:
        raise BrainTargetError(f"지금 판이 없는 키다: {key}")
    if base_version != current.version:
        raise BrainConflictError(current.version)
    return current


def propose_create(session: Any, *, key: str, brand: str, layer: str, item_type: str, values: Mapping[str, Any],
                   reason: str, proposer: Proposer, evidence: Iterable[str] = (), grade: Optional[str] = None,
                   now: Optional[datetime.datetime] = None, known: Optional[str] = None,
                   rollback_of: Optional[int] = None, action: str = "propose_create") -> BrainChange:
    """새 항목 제안. ``values`` 는 값 칸(:data:`OBJECT_FIELDS` — 없는 칸은 비움). 확신 값은 옮기기만 싣는다."""
    evidence = list(evidence)
    full = {**dict.fromkeys(OBJECT_FIELDS), **values}
    if not _trusted(proposer):
        full["confidence"] = None
    problems = key_problems(key) + _common_problems(reason, evidence, grade)
    problems += object_problems({**full, "confidence": full["confidence"] or OBSERVED}, brand=brand, layer=layer,
                                item_type=item_type)
    if problems:
        raise BrainShapeError(problems)
    if current_object(session, key) is not None:
        raise BrainTargetError(f"이미 지금 판이 있는 키다: {key}")
    gates = _gates((full["name"], full["text"]), known_text(session) if known is None else known, proposer, item_type)
    gates = _ai_gates(session, gates, proposer, op=OP_CREATE, key=key, item_type=item_type,
                      texts=[full["name"] or "", full["text"] or ""], evidence=evidence, after=full)
    return _insert(session, now=now, op=OP_CREATE, item_key=key, brand=brand, layer=layer, item_type=item_type,
                   fields={n: {"before": None, "after": v} for n, v in full.items() if v is not None},
                   reason=reason.strip(), evidence=evidence, gates=gates, rollback_of_version=rollback_of,
                   grade=heavier_grade(grade or GRADE_A, TYPE_GRADES[item_type]), proposed_by=proposer.name,
                   action=action)


def propose_update(session: Any, *, key: str, base_version: int, after: Mapping[str, Any], reason: str,
                   proposer: Proposer, evidence: Iterable[str] = (), grade: Optional[str] = None,
                   now: Optional[datetime.datetime] = None, known: Optional[str] = None,
                   rollback_of: Optional[int] = None, action: str = "propose_edit") -> BrainChange:
    """값 칸 고침 제안(칸별 전 → 후). 은퇴는 :func:`propose_retire` 로만. 확신 값은 옮기기만 싣는다(그 밖은 버림)."""
    evidence = list(evidence)
    after = {name: value for name, value in after.items() if name != "confidence" or _trusted(proposer)}
    problems = _common_problems(reason, evidence, grade)
    if not after or set(after) - set(OBJECT_FIELDS):
        problems.append(f"after: {list(OBJECT_FIELDS)} 가운데 바꿀 칸이 있어야 한다")
    if after.get("status") == STATUS_RETIRED:
        problems.append("status: 은퇴는 은퇴 제안으로만 한다")
    if problems:
        raise BrainShapeError(problems)
    current = _target(session, key, base_version)
    before = values_of(current)
    new = {**before, **{name: after[name] for name in after}}
    changed = [name for name in OBJECT_FIELDS if name in after and before[name] != new[name]]
    if not changed:
        raise BrainTargetError("바뀐 칸이 없다")
    problems = object_problems(new, brand=current.brand, layer=current.layer, item_type=current.item_type)
    if problems:
        raise BrainShapeError(problems)
    texts = [new[name] for name in ("name", "text") if name in changed]
    gates = _gates(texts, known_text(session) if known is None else known, proposer)
    gates = _ai_gates(session, gates, proposer, op=OP_UPDATE, key=key, item_type=current.item_type,
                      texts=[t or "" for t in texts], evidence=evidence, before=before, after=new)
    return _insert(session, now=now, op=OP_UPDATE, item_key=key, brand=current.brand, layer=current.layer,
                   item_type=current.item_type, base_version=current.version,
                   fields={n: {"before": before[n], "after": new[n]} for n in changed}, reason=reason.strip(),
                   evidence=evidence, gates=gates, rollback_of_version=rollback_of, proposed_by=proposer.name,
                   grade=heavier_grade(grade or GRADE_A, TYPE_GRADES[current.item_type]), action=action)


def _propose_end(session: Any, op: str, *, key: str, base_version: int, reason: str, proposer: Proposer,
                 evidence: Iterable[str], now: Optional[datetime.datetime],
                 rollback_of: Optional[int] = None, action: Optional[str] = None) -> BrainChange:
    """은퇴 · 지우기 제안(늘 등급 B)."""
    evidence = list(evidence)
    problems = _common_problems(reason, evidence, None)
    if problems:
        raise BrainShapeError(problems)
    current = _target(session, key, base_version)
    before = values_of(current)
    if op == OP_RETIRE and before["status"] == STATUS_RETIRED:
        raise BrainTargetError("이미 은퇴한 항목이다")
    fields = ({"status": {"before": before["status"], "after": STATUS_RETIRED}} if op == OP_RETIRE
              else {n: {"before": v, "after": None} for n, v in before.items() if v is not None})
    return _insert(session, now=now, op=op, item_key=key, brand=current.brand, layer=current.layer,
                   item_type=current.item_type, base_version=current.version, fields=fields, reason=reason.strip(),
                   evidence=evidence, grade=GRADE_B, proposed_by=proposer.name,
                   gates=_ai_gates(session, {"form": "pass", **_NOT_RUN}, proposer, op=op, key=key,
                                   item_type=current.item_type, texts=[], evidence=evidence, before=before),
                   rollback_of_version=rollback_of, action=action or ("propose_retire" if op == OP_RETIRE
                                                                      else "propose_delete"))


def propose_retire(session: Any, *, key: str, base_version: int, reason: str, proposer: Proposer,
                   evidence: Iterable[str] = (), now: Optional[datetime.datetime] = None,
                   rollback_of: Optional[int] = None, action: Optional[str] = None) -> BrainChange:
    """은퇴 제안 — 반영하면 상태 ``retired`` 인 새 판(이력 그대로)."""
    return _propose_end(session, OP_RETIRE, key=key, base_version=base_version, reason=reason, proposer=proposer,
                        evidence=evidence, now=now, rollback_of=rollback_of, action=action)


def propose_delete(session: Any, *, key: str, base_version: int, reason: str, proposer: Proposer,
                   evidence: Iterable[str] = (), now: Optional[datetime.datetime] = None,
                   rollback_of: Optional[int] = None, action: Optional[str] = None) -> BrainChange:
    """지우기 제안 — 반영하면 지금 판을 닫고(새 판 없음) 그 항목에 닿은 링크도 닫는다. 이력은 남는다.

    ``rollback_of`` = 0 은 '처음 판 앞(없던 항목)으로 되돌리기'(판 되돌리기가 그 판에서 만든 항목을 지울 때)."""
    return _propose_end(session, OP_DELETE, key=key, base_version=base_version, reason=reason, proposer=proposer,
                        evidence=evidence, now=now, rollback_of=rollback_of, action=action)


def link_target_type(session: Any, to_key: str) -> Optional[str]:
    """링크 끝의 유형 — 바깥 정본 자리면 가짜 유형, brain 키면 지금 판 유형(없으면 ``None``)."""
    external = external_type(to_key)
    if external is not None:
        return external
    target = current_object(session, to_key)
    return target.item_type if target is not None else None


def propose_link(session: Any, *, op: str, kind: str, from_key: str, to_key: str, reason: str, proposer: Proposer,
                 base_version: Optional[int] = None, values: Optional[Mapping[str, Any]] = None,
                 evidence: Iterable[str] = (), grade: Optional[str] = None,
                 now: Optional[datetime.datetime] = None, rollback_of: Optional[int] = None,
                 action: str = "propose_link") -> BrainChange:
    """링크 더하기 · 빼기 제안. 허용 짝(:data:`.constants.ALLOWED_LINKS`) 밖이면 대상 오류. ``rollback_of`` 는 판 되돌리기
    표시(되돌린 링크 판 · 없던 링크는 0)."""
    evidence = list(evidence)
    full = {**dict.fromkeys(LINK_FIELDS), **(values or {})}
    if not _trusted(proposer):
        full["confidence"] = None  # 기본 '확정' 없음 — 반영 동작이 정한다(7.7 · D104)
    problems = _common_problems(reason, evidence, grade) + key_problems(from_key, "from") + end_key_problems(to_key, "to")
    if op not in (OP_LINK_ADD, OP_LINK_REMOVE):
        problems.append("op: 링크 동작이어야 한다")
    problems += value_problems(kind=kind, check=("kind",))  # 값 목록 한 곳(7.8 다음 14)
    problems += link_problems({**full, "confidence": full["confidence"] or OBSERVED}, kind)
    if problems:
        raise BrainShapeError(problems)
    source, to_type = current_object(session, from_key), link_target_type(session, to_key)
    adding = op == OP_LINK_ADD
    if source is None or to_type is None or (adding and not link_allowed(source.item_type, kind, to_type)):
        raise BrainTargetError(f"허용하지 않는 링크 짝이다: {kind}")
    link = current_link(session, kind, from_key, to_key)
    if adding and link is not None:
        raise BrainTargetError("이미 있는 링크다")
    if adding:
        check_link_rules(session, source, kind, to_key, to_type, kst_day(now or now_utc_naive()))  # 7.8 다음 1 · 14
        require_refs(session, [to_key])  # 가리킨 계산기 · 설정 자리가 정말 있나(7.7 · D105 — 반영 때 한 번 더)
    if op == OP_LINK_REMOVE and (link is None or link.version != base_version):
        raise BrainConflictError(link.version if link is not None else None)
    fields = ({n: {"before": None, "after": v} for n, v in full.items() if v is not None} if op == OP_LINK_ADD
              else {n: {"before": v, "after": None} for n, v in values_of(link, LINK_FIELDS).items() if v is not None})
    return _insert(session, now=now, op=op, item_key=from_key, link_kind=kind, link_from=from_key, link_to=to_key,
                   brand=source.brand, layer=source.layer, item_type=source.item_type,
                   base_version=link.version if link is not None else None, fields=fields, reason=reason.strip(),
                   evidence=evidence, proposed_by=proposer.name,
                   gates=_ai_gates(session, {"form": "pass", **_NOT_RUN}, proposer, op=op, key=from_key,
                                   item_type=source.item_type, texts=[], evidence=evidence),
                   rollback_of_version=rollback_of, action=action,
                   grade=heavier_grade(grade or GRADE_A, TYPE_GRADES[source.item_type],
                                       GRADE_B if op == OP_LINK_REMOVE else GRADE_A))


def propose_rollback(session: Any, *, key: str, to_version: int, reason: str, proposer: Proposer,
                     now: Optional[datetime.datetime] = None, action: str = "item_rollback") -> BrainChange:
    """항목 하나 되돌리기 = 그 판의 옛 값을 **새 제안**으로(지금 판 기준). 지운 항목이면 새로 만들기 제안."""
    old = object_version(session, key, to_version)
    if old is None:
        raise BrainTargetError(f"그 판이 없다: {key} 판 {to_version}")
    values, current = values_of(old), current_object(session, key)
    if current is None:
        return propose_create(session, key=key, brand=old.brand, layer=old.layer, item_type=old.item_type,
                              values=values, reason=reason, proposer=proposer, now=now, rollback_of=int(to_version),
                              action=action)
    if values["status"] == STATUS_RETIRED and current.status != STATUS_RETIRED:
        return propose_retire(session, key=key, base_version=current.version, reason=reason, proposer=proposer, now=now,
                              rollback_of=int(to_version), action=action)
    after = {n: v for n, v in values.items() if v != values_of(current)[n]}
    return propose_update(session, key=key, base_version=current.version, after=after, reason=reason,
                          proposer=proposer, now=now, rollback_of=int(to_version), action=action)

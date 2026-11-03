"""자료 계획 제안(:mod:`.plan_proposals`)의 바탕 — 한 번 돌리기 상태 · 제안 하나 넣고 세기 · 링크(정본 자리 · 사본 자리 ·
공정 단계 · 결정 · 엇갈림) · 나눈 사실 은퇴.

- 링크는 항목 제안을 다 넣은 뒤 넣는다. **허용 짝 → 양 끝 → 근거 종류 반영 → 이미 있음 · 열린 제안** 순으로 보고, 끝(또는 시작)이
  아직 없는데 그 키의 만들기 제안이 열려 있으면 다음 차례(``awaiting_create``)로 센다 — 승인 뒤 다시 돌리면 들어간다.
- 계산기 옵션 힌트(``calc:option/<묶음 이름>:<옵션 이름>``)는 지금 계산기 정본(:func:`.external.current_catalog`)에서 이름이
  **똑같은** 것 하나로 id 를 찾는다(띄어쓰기도 같아야 — 이름이 한 칸 다른 묶음이 따로 있다). 못 찾거나 둘 이상이면 그 링크만
  넘기고 항목 키를 남긴다.
- 세는 까닭 이름은 영어 짧은 코드(출력 칸 이름), 글 · 이름 · 금액은 세지도 싣지도 않는다.
"""

from __future__ import annotations

import datetime
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainChange, BrainObject
from foms.services.brain.constants import (
    CHANGE_OPEN, COPY_EXTERNAL_TYPES, MAX_REF, OP_CREATE, OP_LINK_ADD, OP_RETIRE, STATUS_RETIRED, cardinality,
    external_type, link_allowed,
)
from foms.services.brain.errors import (
    BrainConflictError, BrainExternalRefError, BrainLinkRuleError, BrainRejectedError, BrainShapeError, BrainTargetError,
)
from foms.services.brain.external import current_catalog
from foms.services.brain.proposals import IMPORT_PROPOSER, propose_link, propose_retire
from foms.services.brain.schemas import ERP_STAGES, UNSCHEMA_TYPES, prop_of
from foms.services.brain.store import current_link, current_object, is_current, kst_day

EVIDENCE_KIND = "document"
LABEL_KEYS: tuple[str, ...] = ("pref_label", "aliases", "hidden_labels")
HOLD_KEYS: tuple[str, ...] = ("unsure", "waiting")
#: 사실 나눔에서 새 항목을 만드는 유형 → 까닭 글 이름(공정 단계는 링크로만 · 브랜드는 칸 틀이 없어 넘긴다).
RETYPE_NAMES: dict[str, str] = {"spec": "규격", "term": "용어", "policy": "정책"}
_DECISION = re.compile(r"D\d{1,5}")
_CALC_NAME = re.compile(r"calc:option/<([^<>]+)>:<([^<>]+)>")
_SOURCE = re.compile(r"[^a-z0-9_.-]+")


@dataclass(frozen=True)
class Link:
    """넣을 링크 하나 — 시작 · 끝 유형은 계획에서 안다(끝이 아직 없어도 허용 짝을 먼저 본다)."""

    kind: str
    from_key: str
    from_type: str
    to_key: str
    to_type: Optional[str]
    ref_id: str
    basis: Optional[str] = None  # 가격 규칙 정본 링크 — 이 근거 종류가 반영돼 있어야 넣는다
    decisions: tuple[str, ...] = ()


@dataclass
class Run:
    """한 번 돌리기의 상태 — 세는 수 · 모은 링크 · 은퇴 · 공정 단계 키."""

    session: Any
    brand: str
    source: str
    now: datetime.datetime
    known: str
    filed: Counter = field(default_factory=Counter)
    skipped: Counter = field(default_factory=Counter)
    deferred: Counter = field(default_factory=Counter)
    unresolved: set = field(default_factory=set)
    links: list = field(default_factory=list)
    retires: list = field(default_factory=list)
    steps: dict = field(default_factory=dict)
    _catalog: Any = None
    _decisions: Optional[dict[str, str]] = None

    @property
    def today(self) -> str:
        """한국 오늘(승인 · 확인 날)."""
        return kst_day(self.now).isoformat()

    def ref(self, ref_id: str) -> str:
        """근거 자리 — ``plan:<계획 이름>#<id>``."""
        return f"plan:{self.source}#{ref_id}"[:MAX_REF]

    def catalog(self) -> Any:
        """계산기 정본(한 번만 읽는다 — 못 읽으면 ``False``)."""
        if self._catalog is None:
            self._catalog = current_catalog() or False
        return self._catalog

    def decision_keys(self) -> dict[str, str]:
        """결정 번호 → 지금 사장님 결정 항목 키."""
        if self._decisions is None:
            rows = self.session.execute(select(BrainObject.item_key, BrainObject.payload).where(
                is_current(BrainObject), BrainObject.item_type == "owner_decision")).all()
            self._decisions = {str((p or {}).get("decision_no")): k for k, p in rows if (p or {}).get("decision_no")}
        return self._decisions

    def summary(self) -> dict[str, Any]:
        """동작 · 까닭별 수와 못 찾은 가리킴의 항목 키만."""
        return {"filed": dict(sorted(self.filed.items())), "filed_total": sum(self.filed.values()),
                "skipped": dict(sorted(self.skipped.items())), "deferred": dict(sorted(self.deferred.items())),
                "unresolved_refs": sorted(self.unresolved)}


# ── 계획 꼴 · 작은 글 도구 ───────────────────────────────────────────────
def plan_problems(plan: Any) -> list[str]:
    """계획 꼴 문제(자리만 — 글은 싣지 않는다)."""
    if not isinstance(plan, Mapping):
        return ["계획: 객체여야 한다"]
    problems = [f"{name}: 목록이어야 한다" for name in ("items", "conflicts", "new_items")
                if not isinstance(plan.get(name, []), list)]
    if not problems:
        problems += [f"items[{i}]: id 가 있는 객체여야 한다" for i, item in enumerate(plan.get("items") or [])
                     if not isinstance(item, Mapping) or not isinstance(item.get("id"), str)]
    return problems


def source_name(plan: Mapping[str, Any], fallback: str = "plan") -> str:
    """근거 자리에 쓸 계획 이름(``schema`` 의 '/' 앞 — 소문자 · 숫자 · '_.-' 만)."""
    raw = str(plan.get("schema") or fallback).split("/")[0].lower()
    return _SOURCE.sub("-", raw).strip("-")[:60] or "plan"


def held(run: Run, block: Any) -> bool:
    """``unsure`` · ``waiting`` 이 달린 묶음이면 세고 ``True``."""
    flags = [name for name in HOLD_KEYS if isinstance(block, Mapping) and block.get(name)]
    for name in flags:
        run.skipped[name] += 1
    return bool(flags)


def one_line(value: Any, limit: int) -> Optional[str]:
    """한 줄 글(비거나 길면 ``None``)."""
    if not isinstance(value, str) or not value.strip() or "\n" in value.strip():
        return None
    return value.strip() if len(value.strip()) <= limit else None


def labels_for(block: Mapping[str, Any], item_type: str, *, pref: bool = True) -> dict[str, Any]:
    """그 유형 틀이 받는 이름표 칸만(대표 이름 · 다른 이름 · 숨은 이름 — 빈 값은 뺀다)."""
    out: dict[str, Any] = {}
    for name in LABEL_KEYS if pref else LABEL_KEYS[1:]:
        if item_type not in UNSCHEMA_TYPES and prop_of(item_type, "payload." + name) is None:
            continue
        value = block.get(name)
        if isinstance(value, list):
            value = list(dict.fromkeys(v.strip() for v in value if isinstance(v, str) and v.strip()))
        elif isinstance(value, str):
            value = value.strip()
        if value:
            out[name] = value
    return out


def decisions_in(*values: Any) -> tuple[str, ...]:
    """글 · 목록 속 결정 번호(차례 그대로 · 겹침 뺌)."""
    found: list[str] = []
    for value in values:
        for text in (value if isinstance(value, list) else [value]):
            found += _DECISION.findall(text) if isinstance(text, str) else []
    return tuple(dict.fromkeys(found))


def is_decision_no(value: Any) -> bool:
    """결정 번호 꼴(``D`` + 수)인가."""
    return isinstance(value, str) and _DECISION.fullmatch(value) is not None


def reason(head: str, decisions: Iterable[str]) -> str:
    """짧은 까닭 — 사람이 읽는 한 문장 + 사장님 결정 번호(글 · 금액 없음 — 설계서 7.9 '제안한 까닭')."""
    return f"{head} (자료 정리 · 사장님 결정 {' · '.join(dict.fromkeys([*decisions, 'D130']))})"


#: 링크 종류별 까닭 한 문장(제안 카드 '제안한 까닭').
LINK_REASONS: dict[str, str] = {
    "copy_in": "다른 곳에도 같은 값이 적혀 있다고 표시해요", "value_from": "금액을 가져오는 곳을 이어요",
    "at_step": "어느 단계에서 쓰는 지식인지 이어요", "decided_by": "어느 사장님 결정에서 왔는지 이어요",
    "about": "어느 지식에 대한 것인지 이어요",
}


# ── 제안 하나 넣기 ───────────────────────────────────────────────────────
def file_one(run: Run, kind: str, make: Callable[[], Any], *, ref_key: Optional[str] = None) -> bool:
    """제안 하나를 넣고 센다 — 막히면 까닭(거절됨 · 바깥 자리 없음 · 링크 제약 · 기준 판 · 꼴 · 대상)으로 센다."""
    try:
        make()
    except BrainRejectedError:
        run.skipped["rejected_before"] += 1
    except BrainExternalRefError:
        run.skipped["ref_missing"] += 1
        if ref_key:
            run.unresolved.add(ref_key)
    except BrainLinkRuleError:
        run.skipped["link_rule"] += 1
    except BrainConflictError:
        run.skipped["base_changed"] += 1
    except BrainShapeError:
        run.skipped["shape"] += 1
    except BrainTargetError:
        run.skipped["target"] += 1
    else:
        run.filed[kind] += 1
        return True
    return False


def open_changes(session: Any, op: str, key: str) -> list[BrainChange]:
    """그 키 · 동작의 열린 제안."""
    return list(session.execute(select(BrainChange).where(
        BrainChange.status == CHANGE_OPEN, BrainChange.op == op, BrainChange.item_key == key)).scalars())


def missing_end(run: Run, key: str) -> None:
    """끝(또는 시작) 항목이 없다 — 그 키의 만들기 제안이 열려 있으면 다음 차례, 아니면 넘김."""
    if open_changes(run.session, OP_CREATE, key):
        run.deferred["awaiting_create"] += 1
    else:
        run.skipped["end_missing"] += 1


# ── 링크 모으기 ──────────────────────────────────────────────────────────
def resolve(run: Run, hint: Any) -> Optional[str]:
    """정본 가리킴 힌트 → 키. 계산기 옵션 이름은 이름이 똑같은 것 하나만(못 찾음 · 둘 이상이면 ``None``)."""
    if not isinstance(hint, str) or not hint.strip():
        return None
    match = _CALC_NAME.fullmatch(hint.strip())
    if match is None:
        return hint.strip().lower() if hint.startswith("erp:stage/") else hint.strip()
    catalog = run.catalog()
    if not catalog:
        return None
    hits = [f"calc:option/{c.get('id')}:{o.get('id')}" for c in catalog.option_categories
            if c.get("name") == match.group(1) for o in c.get("options") or ()
            if isinstance(o, Mapping) and o.get("name") == match.group(2)]
    return hits[0] if len(hits) == 1 else None


def value_links(run: Run, key: str, item_type: str, hints: Any, basis: Optional[str], ref_id: str) -> None:
    """정본 자리 링크 — 못 찾은 힌트는 넘기고 항목 키를 남긴다. 연결 개수 최대(가격 규칙은 근거 종류별)를 넘는 것도 넘긴다."""
    refs: list[str] = []
    for hint in hints or []:
        ref = resolve(run, hint)
        if ref is None:
            run.skipped["ref_unresolved"] += 1
            run.unresolved.add(key)
        else:
            refs.append(ref)
    most = cardinality(item_type, "value_from", {"basis": basis})[1]
    most = len(refs) if most is None else most
    if len(refs) > most:
        run.skipped["over_limit"] += len(refs) - most
    run.links += [Link("value_from", key, item_type, ref, external_type(ref), ref_id, basis=basis,
                       decisions=("D115",) if basis else ()) for ref in refs[:most]]


def copy_links(run: Run, key: str, item_type: str, hints: Any, ref_id: str) -> None:
    """사본 자리 힌트(``form:`` · ``macro:`` · ``store:`` · ``screen:`` — 값의 사본이 실린 바깥 글) → ``copy_in``(7.8 다음 6).
    바깥 사본 자리는 있음을 확인할 길이 없어 키 꼴만 본다(:mod:`.proposals`)."""
    for hint in hints or []:
        ref = hint.strip() if isinstance(hint, str) else ""
        if external_type(ref) not in COPY_EXTERNAL_TYPES:
            run.skipped["copy_not_external"] += 1
            continue
        run.links.append(Link("copy_in", key, item_type, ref, external_type(ref), ref_id))


def step_link(run: Run, key: str, item_type: str, hint: Any, ref_id: str) -> None:
    """공정 단계 힌트 → ``at_step``(그 단계 새 항목 키, 계획에 없으면 ``process_step/<단계>``)."""
    if isinstance(hint, str) and hint.upper() in ERP_STAGES:
        to_key = run.steps.get(hint.upper(), f"process_step/{hint.lower()}")
        run.links.append(Link("at_step", key, item_type, to_key, "process_step", ref_id, decisions=("D117",)))


def decided_links(run: Run, key: str, item_type: str, decided: Any, ref_id: str) -> None:
    """결정 번호 → ``decided_by``(그 번호의 사장님 결정 항목이 지금 있을 때만 — 없으면 넘김)."""
    for number in decisions_in(decided):
        target = run.decision_keys().get(number)
        if target is None:
            run.skipped["decision_missing"] += 1
        else:
            run.links.append(Link("decided_by", key, item_type, target, "owner_decision", ref_id, decisions=(number,)))


# ── 링크 · 은퇴 넣기(항목 제안 뒤) ──────────────────────────────────────
def file_link(run: Run, link: Link) -> None:
    """링크 더하기 제안 하나(허용 짝 → 양 끝 → 근거 종류 반영 → 이미 있음 · 열린 제안 순으로 본다)."""
    session = run.session
    if link.to_type is None or not link_allowed(link.from_type, link.kind, link.to_type):
        run.skipped["not_allowed"] += 1
        return
    source = current_object(session, link.from_key)
    if source is None or (external_type(link.to_key) is None and current_object(session, link.to_key) is None):
        missing_end(run, link.from_key if source is None else link.to_key)
        return
    if link.basis is not None and (source.payload or {}).get("basis") != link.basis:
        run.deferred["basis_pending"] += 1  # 근거 종류 고침이 반영돼야 연결 개수가 맞다(D115)
        return
    if current_link(session, link.kind, link.from_key, link.to_key) is not None:
        run.skipped["same"] += 1
        return
    if session.execute(select(BrainChange.id).where(
            BrainChange.status == CHANGE_OPEN, BrainChange.op == OP_LINK_ADD, BrainChange.link_kind == link.kind,
            BrainChange.link_from == link.from_key, BrainChange.link_to == link.to_key).limit(1)).first():
        run.skipped["open_proposal"] += 1
        return
    file_one(run, f"link_add:{link.kind}", lambda: propose_link(
        session, op=OP_LINK_ADD, kind=link.kind, from_key=link.from_key, to_key=link.to_key,
        values={"evidence_kind": EVIDENCE_KIND, "evidence_ref": run.ref(link.ref_id)},
        reason=reason(LINK_REASONS.get(link.kind, "두 지식을 이어요"), link.decisions), proposer=IMPORT_PROPOSER,
        evidence=[run.ref(link.ref_id)], now=run.now), ref_key=link.from_key)


def file_retire(run: Run, old_key: str, new_key: str, target: str, ref_id: str) -> None:
    """나눈 사실 은퇴 — 새 항목이 반영된 뒤에만(그 전은 다음 차례). 까닭에 새 항목 키를 적는다."""
    current = current_object(run.session, old_key)
    if current is None or current.status == STATUS_RETIRED:
        run.skipped["same"] += 1
    elif current_object(run.session, new_key) is None:
        missing_end(run, new_key)
    elif open_changes(run.session, OP_RETIRE, old_key):
        run.skipped["open_proposal"] += 1
    else:
        file_one(run, OP_RETIRE, lambda: propose_retire(
            run.session, key=old_key, base_version=current.version, proposer=IMPORT_PROPOSER, now=run.now,
            reason=reason(f"사실 글을 새 {RETYPE_NAMES[target]} 지식({new_key})으로 옮겨서 옛 글은 그만 써요",
                          ("D103",)),
            evidence=[run.ref(ref_id)]))

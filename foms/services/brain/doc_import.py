"""지식 문서 → brain 표 옮기기(설계서 7.5 끝 '저장 꼴' · 11절 '판 1 부터 표' · D97 · D99).

브랜드마다 저장된(가장 최근) 지식 문서를 읽어 항목 줄로 바꾼다. **두 브랜드 문서에 칸 열 개까지 같은 항목은 ``COMMON``
항목 하나**(3.1 규칙 1), 다르거나 한쪽에만 있으면 브랜드마다 항목이다. 키는 ``common/<문서 id>`` · ``<브랜드>/<문서 id>``.

- 쓰기는 다른 길과 같다 — 옮기기 제안(:data:`.proposals.IMPORT_PROPOSER`, 근거 종류 ``import``)을 만들고 반영 동작
  (:func:`.apply.apply_change` ``as_import``)으로 넣는다. 처음 옮기기는 **판 0** 이다.
- **멱등**: 다시 돌리면 같은 항목은 건너뛴다(쓰기 0). 그림자 기간에 문서가 바뀌었으면 바뀐 칸(:data:`.doc_bridge.SYNC_FIELDS`)만
  고침 제안으로, 문서에서 빠진 항목은 지우기 제안으로 따라간다. 지우기는 옮기기가 만든 판(``created_by='import'``)만 —
  다른 길로 만든 항목은 건드리지 않고 ``unmanaged`` 로 알린다.
- 요약에는 키 · 개수 · 관문 이름만 싣는다(글 · 가격 없음).
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainObject
from foms.services.brain.apply import apply_change
from foms.services.brain.constants import BRAND_COMMON, DOC_TYPES, KIND_TYPES, STATUS_RETIRED
from foms.services.brain.doc_bridge import SYNC_FIELDS, doc_values
from foms.services.brain.gates import FAIL
from foms.services.brain.proposals import (
    IMPORT_PROPOSER, propose_create, propose_delete, propose_retire, propose_update,
)
from foms.services.brain.store import is_current, values_of
from foms.services.cs_agent.knowledge import KNOWN_BRANDS, knowledge_key, read_stored
from foms.services.cs_agent.knowledge_doc import STATUS_APPROVED
from foms.services.datetime_kst import now_utc_naive

REASON = "지식 문서에서 옮김(그림자 기간)"


@dataclass(frozen=True)
class Desired:
    """옮겨 올 항목 하나 — 키 · 정체 · 값 칸."""

    key: str
    brand: str
    layer: str
    item_type: str
    values: dict[str, Any] = field(repr=False)


@dataclass
class ImportPlan:
    """옮기기 계획 — 만들기 · 고치기(바뀐 칸) · 지우기 · 같음 · 손대지 않는 줄."""

    creates: list[Desired] = field(default_factory=list)
    updates: list[tuple[Desired, BrainObject, dict[str, Any]]] = field(default_factory=list)
    deletes: list[BrainObject] = field(default_factory=list)
    unchanged: int = 0
    unmanaged: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        """키 · 개수만."""
        return {"create": len(self.creates), "update": len(self.updates), "delete": len(self.deletes),
                "unchanged": self.unchanged, "unmanaged": sorted(self.unmanaged),
                "keys": {"create": [d.key for d in self.creates], "update": [d.key for d, _r, _a in self.updates],
                         "delete": [r.item_key for r in self.deletes]}}


def load_documents(session: Any) -> tuple[dict[str, tuple[int, dict[str, Any]]], dict[str, str]]:
    """브랜드마다 저장된 지식 문서 — (브랜드 → (버전, 정본 문서), 브랜드 → 읽지 못한 까닭). 넣은 적 없으면 빠진다."""
    docs: dict[str, tuple[int, dict[str, Any]]] = {}
    problems: dict[str, str] = {}
    for brand in sorted(KNOWN_BRANDS):
        stored = read_stored(session, brand)
        if stored.problem:
            problems[brand] = stored.problem
        elif stored.document is not None:
            docs[brand] = (stored.version, stored.document)
    return docs, problems


def _desired_one(doc_id: str, per: Mapping[str, tuple[int, dict[str, Any]]], brand: str) -> Desired:
    """한 브랜드(또는 공통)의 옮길 항목."""
    brands = sorted(per)
    item = per[brands[0]][1]
    item_type, layer = KIND_TYPES[item["kind"]]
    values = doc_values(item, item_type=item_type, positions={b: per[b][0] for b in brands},
                        evidence_ref=",".join(knowledge_key(b) for b in brands))
    return Desired(f"{brand.lower()}/{doc_id}", brand, layer, item_type, values)


def desired_items(docs: Mapping[str, Mapping[str, Any]]) -> dict[str, Desired]:
    """브랜드 → 정본 문서 에서 옮길 항목(키 → 항목). 두 브랜드 이상 문서가 모두 같은 항목을 가지면 공통 하나."""
    by_id: dict[str, dict[str, tuple[int, dict[str, Any]]]] = defaultdict(dict)
    for brand in sorted(docs):
        for position, item in enumerate(docs[brand]["items"]):
            by_id[item["id"]][brand] = (position, item)
    out: dict[str, Desired] = {}
    for doc_id, per in by_id.items():
        first = next(iter(per.values()))[1]
        if len(docs) >= 2 and len(per) == len(docs) and all(item == first for _pos, item in per.values()):
            desired = [_desired_one(doc_id, per, BRAND_COMMON)]
        else:
            desired = [_desired_one(doc_id, {brand: entry}, brand) for brand, entry in sorted(per.items())]
        out.update((d.key, d) for d in desired)
    return out


def plan_import(session: Any, desired: Mapping[str, Desired]) -> ImportPlan:
    """지금 표와 견준 계획(쓰기 없음)."""
    rows = session.execute(select(BrainObject).where(is_current(BrainObject),
                                                     BrainObject.item_type.in_(DOC_TYPES))).scalars().all()
    current = {row.item_key: row for row in rows}
    plan = ImportPlan()
    for key, row in sorted(current.items()):
        wanted = desired.get(key)
        same_identity = wanted is not None and (row.brand, row.layer, row.item_type) == (
            wanted.brand, wanted.layer, wanted.item_type)
        if not same_identity and row.created_by != IMPORT_PROPOSER.name:
            plan.unmanaged.append(key)
        elif not same_identity:
            plan.deletes.append(row)
    deleting = {row.item_key for row in plan.deletes}
    for key, wanted in sorted(desired.items()):
        row = current.get(key)
        if key in plan.unmanaged:  # 다른 길로 만든 줄이 그 키를 쓰고 있다 — 알리기만
            continue
        if row is None or key in deleting:
            plan.creates.append(wanted)
            continue
        values = values_of(row)
        after = {name: wanted.values[name] for name in SYNC_FIELDS if values[name] != wanted.values[name]}
        if after:
            plan.updates.append((wanted, row, after))
        else:
            plan.unchanged += 1
    return plan


def _known(docs: Mapping[str, Mapping[str, Any]]) -> str:
    """숫자 관문 허용 목록 — 문서들의 승인 항목 글."""
    return "\n".join(item["text"] for doc in docs.values() for item in doc["items"]
                     if item.get("status") == STATUS_APPROVED)


def _sync_update(session: Any, wanted: Desired, row: BrainObject, after: dict[str, Any], *, apply_one: Any,
                 common: dict[str, Any], known: str) -> None:
    """바뀐 칸 고침 — 문서에서 내림(retired)이 되면 다른 칸 고침 뒤 은퇴 제안으로(고침 제안은 은퇴를 받지 않는다)."""
    retiring = after.get("status") == STATUS_RETIRED
    rest = {name: value for name, value in after.items() if not (retiring and name == "status")}
    base = row.version
    if rest:
        base = apply_one(propose_update(session, key=wanted.key, base_version=base, after=rest, known=known, **common))
    if retiring:
        apply_one(propose_retire(session, key=wanted.key, base_version=base, **common))


def run_import(session: Any, versions: Mapping[str, tuple[int, Mapping[str, Any]]], *, actor: Any, apply: bool,
               now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """옮기기 — 모의 실행이면 계획만, ``apply`` 면 제안 → 반영을 하나씩(커밋은 호출자).

    Args:
        versions: 브랜드 → (지식 문서 버전, 정본 문서) — :func:`load_documents` 의 앞 값.
        actor: 반영하는 사람(켜진 ADMIN — 가격 · 정책 · 사장님 결정이 들어 있다).
    """
    docs = {brand: doc for brand, (_version, doc) in versions.items()}
    plan = plan_import(session, desired_items(docs))
    out: dict[str, Any] = {"applied": False, **plan.summary()}
    if not apply:
        return out
    now = now or now_utc_naive()
    common = {"proposer": IMPORT_PROPOSER, "now": now, "reason": REASON,
              "evidence": [f"{knowledge_key(b)}@v{v}" for b, (v, _doc) in sorted(versions.items())]}
    known, failed, releases = _known(docs), defaultdict(list), set()

    def apply_one(change: Any) -> Optional[int]:
        """옮기기 제안 하나를 반영하고 관문 결과 · 판 번호를 모은다."""
        result = apply_change(session, change.id, actor=actor, now=now, as_import=True)
        releases.add(result.release_no)
        for gate in (name for name, value in (change.gates or {}).items() if value == FAIL):
            failed[gate].append(change.item_key)
        return result.version

    for row in plan.deletes:  # 먼저 지운다 — 브랜드 항목 ↔ 공통 항목으로 바뀔 때 같은 문서 id 가 겹치지 않게
        apply_one(propose_delete(session, key=row.item_key, base_version=row.version, **common))
    for wanted, row, after in plan.updates:
        _sync_update(session, wanted, row, after, apply_one=apply_one, common=common, known=known)
    for wanted in plan.creates:
        apply_one(propose_create(session, key=wanted.key, brand=wanted.brand, layer=wanted.layer,
                                 item_type=wanted.item_type, values=wanted.values, known=known, **common))
    out.update(applied=True, releases=sorted(releases), gate_fail={g: sorted(k) for g, k in sorted(failed.items())})
    return out

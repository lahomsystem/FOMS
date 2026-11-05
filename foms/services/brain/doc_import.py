"""지식 문서 → brain 표 옮기기(설계서 7.5 끝 '저장 꼴' · 11절 '판 1 부터 표' · D97 · D99).

브랜드마다 저장된(가장 최근) 지식 문서를 읽어 항목 줄로 바꾼다. **두 브랜드 문서에 칸 열 개까지 같은 항목은 ``COMMON``
항목 하나**(3.1 규칙 1), 다르거나 한쪽에만 있으면 브랜드마다 항목이다. 키는 ``common/<문서 id>`` · ``<브랜드>/<문서 id>``.

- 쓰기는 다른 길과 같다 — 옮기기 제안(:data:`.proposals.IMPORT_PROPOSER`, 근거 종류 ``import``)을 만들고 반영 동작
  (:func:`.apply.apply_change` ``as_import``)으로 넣는다. 처음 옮기기는 **판 0** 이다.
- **멱등**: 다시 돌리면 같은 항목은 건너뛴다(쓰기 0). 표에서 다시 만든 문서가 저장된 문서와 모두 같으면(그림자 같음) 계획 없이
  끝난다. 문서를 직접 고쳤으면 바뀐 칸(:data:`.doc_bridge.SYNC_FIELDS`)만 고침 제안으로, 문서에서 빠진 항목은 지우기 제안으로,
  두 브랜드가 갈라지거나 같아지면 나누기 · 합치기(지우기 + 만들기)로 따라간다.
- **표가 정본이다(3.1 규칙 1 — 옮긴 뒤)**: 따라가기는 **옮기기만 쓴 지금 판**(``created_by='import'`` · 사람 승인자 없음 · 근거
  종류 ``import``)만 고친다. 사람이 승인한 판(고친 글 · 아직 맞음 · 자료 계획 제안 — 근거 종류 ``document`` 등)은 문서 값으로
  되돌리지 않고 ``protected`` 로 알린다(문서 칸이 이미 같으면 같음). 지우기 · 나누기 · 합치기는 그 문서 id 의 지울 줄이 모두
  옮기기만 쓴 판이고 **링크가 닿지 않을 때만** — 아니면 그 문서 id 는 지우기 · 만들기 없이 두고 손대지 않는 줄은
  ``unmanaged``, 만들지 않은 키는 ``protected`` 로 알린다(공통 항목을 나누다 링크를 잃거나, 남은 공통 항목과 문서 id 가 겹쳐
  멈추지 않게).
- **brain 만의 칸은 따라 맞추기에서 남는다**(7.8 다음 1 · 2): 실음 칸은 문서 칸만 문서 값으로 맞추고, 그 밖의 칸(이름표 · 근거
  종류 · 결정 번호 같은 유형 속성 틀 칸)은 brain 값을 그대로 둔다. 제작 조건 가운데 문서 id 가 없는 brain 만의 항목은 옮기기
  대상이 아니다(:func:`.constants.is_doc_item`).
- 요약에는 키 · 개수 · 관문 이름만 싣는다(글 · 가격 없음).
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from sqlalchemy import or_, select

from foms.persistence.brain.models import BrainLink, BrainObject
from foms.services.brain.apply import apply_change
from foms.services.brain.constants import (
    BRAND_COMMON, DOC_TYPES, EVIDENCE_IMPORT, KIND_TYPES, STATUS_RETIRED, is_doc_item,
)
from foms.services.brain.doc_bridge import (
    DOC_PAYLOAD_KEYS, IMPORT_SCOPE_OVERRIDES, SYNC_FIELDS, doc_item_of, doc_values, regenerate_document,
)
from foms.services.brain.gates import FAIL
from foms.services.brain.proposals import (
    IMPORT_PROPOSER, propose_create, propose_delete, propose_retire, propose_update,
)
from foms.services.brain.store import is_current, values_of
from foms.services.cs_agent.knowledge import KNOWN_BRANDS, KnowledgeSchemaError, knowledge_key, read_stored
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

    @property
    def doc_id(self) -> str:
        """문서 id."""
        return str(self.values["payload"]["doc_id"])


@dataclass
class ImportPlan:
    """옮기기 계획 — 만들기 · 고치기(바뀐 칸) · 지우기 · 같음 · 손대지 않는 줄 · 표가 정본이라 따라가지 않은 키."""

    creates: list[Desired] = field(default_factory=list)
    updates: list[tuple[Desired, BrainObject, dict[str, Any]]] = field(default_factory=list)
    deletes: list[BrainObject] = field(default_factory=list)
    unchanged: int = 0
    unmanaged: list[str] = field(default_factory=list)
    protected: list[str] = field(default_factory=list)
    shadow_equal: bool = False

    def summary(self) -> dict[str, Any]:
        """키 · 개수만."""
        return {"create": len(self.creates), "update": len(self.updates), "delete": len(self.deletes),
                "unchanged": self.unchanged, "unmanaged": sorted(self.unmanaged), "protected": sorted(self.protected),
                "shadow_equal": self.shadow_equal,
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


def import_owned(row: BrainObject) -> bool:
    """옮기기만 쓴 지금 판인가 — 옮기기가 만들고(사람 승인자 없음) 근거 종류가 ``import``. 아니면 표가 정본이라 따라가지 않는다."""
    return (row.created_by == IMPORT_PROPOSER.name and row.human_approver_id is None
            and row.evidence_kind == EVIDENCE_IMPORT)


def _linked(session: Any, keys: list[str]) -> set[str]:
    """지금 링크가 닿은 항목 키(시작 · 끝)."""
    if not keys:
        return set()
    pairs = session.execute(select(BrainLink.from_key, BrainLink.to_key).where(
        is_current(BrainLink), or_(BrainLink.from_key.in_(keys), BrainLink.to_key.in_(keys)))).all()
    return {key for pair in pairs for key in pair} & set(keys)


def _sync_after(row: BrainObject, wanted: Desired) -> dict[str, Any]:
    """문서를 따라 맞출 칸(바뀐 칸만) — brain 만의 실음 칸은 그대로 둔다. 정해 둔 항목은 보기 범위도(점검 지금 5)."""
    values = values_of(row)
    want = dict(wanted.values)
    if isinstance(want.get("payload"), dict) and isinstance(values.get("payload"), dict):  # brain 만의 칸은 그대로
        kept = {k: v for k, v in values["payload"].items() if k not in DOC_PAYLOAD_KEYS}
        want["payload"] = {**want["payload"], **kept}
    after = {name: want[name] for name in SYNC_FIELDS if values[name] != want[name]}
    if wanted.doc_id in IMPORT_SCOPE_OVERRIDES and values["visibility"] != IMPORT_SCOPE_OVERRIDES[wanted.doc_id]:
        after["visibility"] = IMPORT_SCOPE_OVERRIDES[wanted.doc_id]
    return after


def _plan_update(plan: ImportPlan, row: BrainObject, wanted: Desired) -> None:
    """키 · 정체가 같은 줄 — 옮기기만 쓴 판은 바뀐 칸을 따라가고, 사람이 승인한 판은 문서 칸이 다를 때 ``protected``."""
    after = _sync_after(row, wanted)
    if not after:
        plan.unchanged += 1
    elif import_owned(row):
        plan.updates.append((wanted, row, after))
    elif "visibility" not in after and doc_item_of(values_of(row), row.item_type) == doc_item_of(
            wanted.values, wanted.item_type):
        plan.unchanged += 1  # 문서 칸은 같고 차례 · 확신 같은 brain 칸만 다르다 — 표가 정본
    else:
        plan.protected.append(row.item_key)


def _same_identity(row: BrainObject, wanted: Desired) -> bool:
    """키가 같은 줄과 옮길 항목의 정체 칸(브랜드 · 층 · 유형)이 같은가."""
    return (row.brand, row.layer, row.item_type) == (wanted.brand, wanted.layer, wanted.item_type)


def _plan_group(plan: ImportPlan, rows: list[BrainObject], wants: list[Desired], linked: set[str]) -> None:
    """문서 id 하나의 지금 줄 ↔ 옮길 항목. 키 · 정체가 같은 짝은 고침, 남는 줄은 지우기 · 남는 항목은 만들기 — 지울 줄에
    사람이 승인한 판이나 링크가 닿은 줄이 있으면 그 문서 id 는 지우기 · 만들기 없이 둔다(나누기 · 합치기 막기)."""
    by_key = {wanted.key: wanted for wanted in wants}
    pairs = [(row, by_key[row.item_key]) for row in rows
             if row.item_key in by_key and _same_identity(row, by_key[row.item_key])]
    paired = {row.item_key for row, _wanted in pairs}
    stale = [row for row in rows if row.item_key not in paired]
    fresh = [wanted for wanted in wants if wanted.key not in paired]
    held = [row for row in stale if not import_owned(row) or row.item_key in linked]
    if held:
        plan.unmanaged.extend(row.item_key for row in held)
        plan.protected.extend(wanted.key for wanted in fresh)
    else:
        plan.deletes.extend(stale)
        plan.creates.extend(fresh)
    for row, wanted in pairs:
        _plan_update(plan, row, wanted)


def plan_import(session: Any, desired: Mapping[str, Desired]) -> ImportPlan:
    """지금 표와 견준 계획(쓰기 없음) — 문서 id 마다."""
    rows = session.execute(select(BrainObject).where(is_current(BrainObject),
                                                     BrainObject.item_type.in_(DOC_TYPES))).scalars().all()
    current = [row for row in rows if is_doc_item(row.item_type, row.payload)]
    linked = _linked(session, [row.item_key for row in current])
    groups: dict[str, tuple[list[BrainObject], list[Desired]]] = defaultdict(lambda: ([], []))
    for row in current:
        groups[str((row.payload or {}).get("doc_id"))][0].append(row)
    for wanted in desired.values():
        groups[wanted.doc_id][1].append(wanted)
    plan = ImportPlan()
    for doc_id in sorted(groups):
        rows_of, wants = groups[doc_id]
        _plan_group(plan, sorted(rows_of, key=lambda r: r.item_key), sorted(wants, key=lambda d: d.key), linked)
    plan.creates.sort(key=lambda d: d.key)  # 키 차례로 쓴다(문서 id 묶음 차례가 아니라)
    plan.updates.sort(key=lambda entry: entry[0].key)
    plan.deletes.sort(key=lambda r: r.item_key)
    return plan


def shadow_equal(session: Any, docs: Mapping[str, Mapping[str, Any]]) -> bool:
    """표에서 다시 만든 문서가 브랜드마다 저장된 문서와 같은가(저장 문서가 없는 브랜드는 표에도 그 브랜드 항목이 없어야)."""
    for brand in sorted(KNOWN_BRANDS):
        try:
            regenerated = regenerate_document(session, brand)
        except KnowledgeSchemaError:
            return False
        if brand in docs and regenerated != docs[brand]:
            return False
        if brand not in docs and regenerated["items"]:
            return False
    return True


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
    desired = desired_items(docs)
    if shadow_equal(session, docs):  # 표가 정본이고 문서가 그 사본 그대로 — 옮길 것이 없다
        plan = ImportPlan(unchanged=len(desired), shadow_equal=True)
    else:
        plan = plan_import(session, desired)
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

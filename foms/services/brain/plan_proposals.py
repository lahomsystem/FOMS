"""자료 계획 → 열린 제안(설계서 7.8 '자료(제안)' · 7.5 승인 흐름 · 사장님 D130) — 사장님이 승인한 자료 계획 파일을 읽어
**옮기기 묶음 제안**(:data:`.proposals.IMPORT_PROPOSER`)으로 넣는다. **반영하지 않는다** — 카드마다 사람이 승인한다(등급 A 는
한꺼번에). 옮기기 묶음이라 AI 주 상한 · 4주 닫힘 밖이다(D130).

계획 꼴(저장소 밖 파일 — 금액이 들어 있어 저장소에 두지 않는다): ``items[]``(지식 문서 id · 이름표 · 가격 규칙 근거 종류 · 나눔 ·
사실 나눔 · 공정 단계 힌트 · 결정 번호) · ``conflicts[]`` · ``new_items[]``.

- 항목마다 **고침 하나**(이름표 · 근거 종류 · 결정 번호를 실음 칸에 한 번에). 항목 키는 ``<브랜드>/<문서 id>``, 없으면
  ``common/<문서 id>``(:mod:`.doc_import` 키 꼴).
- **만들기**: 가격 규칙 나눔(자식 — 지식 문서 항목이라 문서 id · 승인 칸을 단다, 글은 대표 이름뿐이라 승인 때 고쳐 넣는다) ·
  새 항목(공정 단계 · 규격 · 용어 — 공통 / 지식 문서 유형(새 가격 규칙)은 나눔 자식과 같은 길, ``parent_hint`` 항목에서 의도 ·
  보기 범위) · 사실 나눔(규격 · 용어 · 정책 — 사실 글을 옮긴 새 항목 ``<옛 키>-<유형>`` + 옛 사실
  **은퇴 제안**, 은퇴는 새 항목이 반영된 뒤 다음 차례) · 엇갈림(갈림 · 덮어씀은 ``conflict``, 글만 고칠 것은 ``question``) +
  ``about``. ``supersedes`` 는 쓰지 않는다 — 엇갈림의 다른 쪽이 brain 항목이 아니라 바깥 사본(스토어 상세 · 매크로)이다.
- 사실 → 공정 단계는 새 항목 없이 ``at_step`` 링크로 둔다(사실이 그 단계에 매인다 — 같은 단계 항목을 여럿 만들지 않는다).
  사실 → 브랜드는 브랜드 칸 틀이 아직 없어 넘긴다(수만 센다).
- 링크(``value_from`` · ``copy_in``(``copy_hint`` — 값의 사본이 실린 양식 · 그림) · ``at_step`` · ``decided_by`` · ``about``)와
  은퇴는 :mod:`.plan_links` — 끝이 승인 대기면 다음 차례.
- ``unsure`` · ``waiting`` 이 달린 묶음(항목 · 가격 규칙 · 사실 나눔 · 나눈 자식 · 새 항목 · 엇갈림)은 넣지 않고 센다.
- **멱등**: 이미 같은 값 · 이미 있는 항목 · 링크 · 같은 열린 제안이면 넣지 않는다. 같은 제안이 거절됐으면 :mod:`.proposals` 가
  막는다(``rejected_before``).
- 요약은 동작 · 까닭별 수와 못 찾은 가리킴의 항목 키만(글 · 이름 · 금액 없음). 커밋은 호출자 몫, 모의 실행은 저장점을 되돌린다.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Optional

from foms.persistence.brain.models import BrainObject
from foms.services.brain.constants import (
    BRAND_COMMON, DOC_TYPES, KEY_RE, KIND_TYPES, LAYER_COMMON, OP_CREATE, OP_UPDATE, PRICE_BASES, PRICE_RULE_TYPE,
    SCOPE_ADMIN, SCOPE_ALL, STATUS_ACTIVE, TYPE_KINDS,
)
from foms.services.brain.errors import BrainShapeError
from foms.services.brain.plan_links import (
    EVIDENCE_KIND, LABEL_KEYS, RETYPE_NAMES, Link, Run, copy_links, decided_links, decisions_in, file_link, file_one,
    file_retire, held, is_decision_no, labels_for, one_line, open_changes, plan_problems, reason, source_name,
    step_link, value_links,
)
from foms.services.brain.proposals import IMPORT_PROPOSER, after_values, known_text, propose_create, propose_update
from foms.services.brain.schemas import ERP_STAGES, payload_props
from foms.services.brain.store import current_object, values_of
from foms.services.datetime_kst import now_utc_naive

APPROVED_BY = "D130 자료 계획"  # 나눈 지식 문서 항목의 승인 칸(실제 승인은 카드 승인)
NEW_TYPES: dict[str, str] = {"process_step": "공정 단계", "spec": "규격", "term": "용어"}
CONFLICT_TYPES: dict[str, str] = {"supersede": "conflict", "conflict_item": "conflict", "edit_text": "question"}
_DOC_ID = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
_PAYLOAD = "payload."


def _create(run: Run, *, key: str, brand: str, layer: str, item_type: str, values: dict[str, Any], ref_id: str,
            why: str) -> None:
    """만들기 제안(이미 있거나 열린 만들기가 있으면 넘김). 상태 '반영' · 근거 종류 ``document`` 가 기본."""
    if not KEY_RE.fullmatch(key):
        run.skipped["shape"] += 1
    elif current_object(run.session, key) is not None:
        run.skipped["same"] += 1
    elif open_changes(run.session, OP_CREATE, key):
        run.skipped["open_proposal"] += 1
    else:
        values = {"status": STATUS_ACTIVE, "evidence_kind": EVIDENCE_KIND, "evidence_ref": run.ref(ref_id), **values}
        file_one(run, OP_CREATE, lambda: propose_create(
            run.session, key=key, brand=brand, layer=layer, item_type=item_type, values=values, reason=why,
            proposer=IMPORT_PROPOSER, evidence=[run.ref(ref_id)], now=run.now, known=run.known))


# ── 항목(지식 문서에서 옮긴 것) ─────────────────────────────────────────
def _row(run: Run, doc_id: Any) -> Optional[BrainObject]:
    """계획 id → 지금 항목(그 브랜드 먼저, 없으면 공통)."""
    if not isinstance(doc_id, str) or not _DOC_ID.fullmatch(doc_id):
        return None
    for prefix in (run.brand.lower(), BRAND_COMMON.lower()):
        row = current_object(run.session, f"{prefix}/{doc_id}")
        if row is not None:
            return row
    return None


def _update(run: Run, row: BrainObject, item: Mapping[str, Any], price: Optional[Mapping[str, Any]]) -> None:
    """이름표 · 근거 종류(+ 계획에 적힌 가격 규칙 틀 칸) · 결정 번호를 실음 칸 고침 하나로."""
    want = labels_for(item, row.item_type)
    heads, decisions = (["이름표"] if want else []), []
    if price is not None and price.get("basis") in PRICE_BASES:
        names = [p.path[len(_PAYLOAD):] for p in payload_props(PRICE_RULE_TYPE)]
        want.update({name: price[name] for name in names if name in price and name not in LABEL_KEYS})
        heads.append("근거 종류")
        decisions.append("D115")
    if row.item_type == "owner_decision" and is_decision_no(item.get("decision_no")):
        want["decision_no"] = item["decision_no"]
        heads.append("결정 번호")
    payload = dict(row.payload or {})
    new = {**payload, **want}
    if not want or new == payload:
        run.skipped["same"] += 1
    elif any(after_values(c.fields) == {"payload": new} for c in open_changes(run.session, OP_UPDATE, row.item_key)):
        run.skipped["open_proposal"] += 1
    else:
        file_one(run, OP_UPDATE, lambda: propose_update(
            run.session, key=row.item_key, base_version=row.version, after={"payload": new},
            reason=reason(" · ".join(heads) + " 채움", decisions), proposer=IMPORT_PROPOSER,
            evidence=[run.ref(item["id"])], now=run.now, known=run.known))


def _doc_create(run: Run, block: Mapping[str, Any], *, kind: Any, cid: Any, parent: Optional[BrainObject],
                why: str) -> Optional[tuple[str, str]]:
    """새 지식 문서 항목(가격 규칙 나눔 자식 · 새 가격 규칙) — 문서 id · 승인 칸, 의도 · 꼬리표 · 근거 파일 · 보기 범위는 부모에서
    (부모가 없으면 비움 · '내부 모두'). 글은 대표 이름뿐이라 승인 때 고쳐 넣는다. 정본 · 사본 링크는 반영 뒤 다음 차례.
    (키, 유형)을 돌려준다(꼴이 틀리면 ``None``)."""
    if kind not in KIND_TYPES or not isinstance(cid, str) or not _DOC_ID.fullmatch(cid):
        run.skipped["shape"] += 1
        return None
    item_type, layer = KIND_TYPES[kind]
    basis = block.get("basis") if item_type == PRICE_RULE_TYPE and block.get("basis") in PRICE_BASES else None
    label, base = one_line(block.get("pref_label"), 200) or cid, (parent.payload if parent is not None else None) or {}
    payload = {**labels_for(block, item_type, pref=False), "doc_id": cid, "intents": list(base.get("intents") or []),
               "tags": list(base.get("tags") or []), "source": base.get("source"), "approved_by": APPROVED_BY,
               "approved_at": run.today, **({"basis": basis} if basis else {})}
    key = f"{(parent.item_key.split('/')[0] if parent is not None else run.brand.lower())}/{cid}"
    _create(run, key=key, brand=parent.brand if parent is not None else run.brand, layer=layer, item_type=item_type,
            ref_id=cid, why=why,
            values={"name": label, "text": label, "visibility": parent.visibility if parent is not None else SCOPE_ALL,
                    "checked_at": run.today, "payload": payload})
    if basis:
        value_links(run, key, item_type, block.get("value_from_hint"), basis, cid)
    copy_links(run, key, item_type, block.get("copy_hint"), cid)
    return key, item_type


def _child(run: Run, parent: BrainObject, item: Mapping[str, Any], child: Any) -> None:
    """가격 규칙 나눔 자식 하나(:func:`_doc_create` — 키 머리 · 브랜드는 부모 것)."""
    if isinstance(child, Mapping) and not held(run, child):
        _doc_create(run, child, kind=child.get("kind") or item.get("kind"), cid=child.get("id"), parent=parent,
                    why=reason(f"나눔 — {parent.item_key} 에서 하나씩", ("D115",)))


def _retype(run: Run, row: BrainObject, item: Mapping[str, Any], target: str) -> str:
    """사실 나눔 — 사실 글을 옮긴 새 항목(``<옛 키>-<유형>``) 만들기 + 옛 사실 은퇴(새 항목 반영 뒤). 새 키를 돌려준다."""
    key, old = f"{row.item_key}-{target}", values_of(row)
    payload = labels_for(item, target, pref=False)
    if target in DOC_TYPES:  # 지식 문서 유형(정책) — 문서 칸은 옛 사실에서(같은 승인 글), 문서 id 는 겹치지 않게
        base = row.payload or {}
        payload.update(doc_id=f"{base.get('doc_id') or item['id']}-{target}"[:64], intents=list(base.get("intents") or []),
                       tags=list(base.get("tags") or []), source=base.get("source"),
                       approved_by=base.get("approved_by"), approved_at=base.get("approved_at"))
    _create(run, key=key, brand=row.brand, layer=LAYER_COMMON, item_type=target, ref_id=item["id"],
            values={"name": one_line(item.get("pref_label"), 200) or item["id"], "text": old["text"],
                    "visibility": old["visibility"], "checked_at": old["checked_at"], "payload": payload or None},
            why=reason(f"사실 → {RETYPE_NAMES[target]} 나눔", ("D103",)))
    run.retires.append((row.item_key, key, target, item["id"]))
    return key


def _price_block(run: Run, row: BrainObject, item: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    """가격 규칙 항목의 계획 묶음(가격 규칙이 아니거나 보류면 ``None``)."""
    price = item.get("price_rule") if row.item_type == PRICE_RULE_TYPE else None
    return price if isinstance(price, Mapping) and not held(run, price) else None


def _items(run: Run, items: Iterable[Mapping[str, Any]]) -> None:
    """옮긴 항목 — 고침 · 나눔 · 사실 나눔 · 링크 모으기."""
    for item in items:
        if held(run, item):
            continue
        row = _row(run, item["id"])
        if row is None:
            run.skipped["item_missing"] += 1
            continue
        fact_to = item.get("fact_to") if row.item_type == "fact" and isinstance(item.get("fact_to"), Mapping) else None
        target = fact_to.get("type") if fact_to is not None and not held(run, fact_to) else None
        price = _price_block(run, row, item)
        if item.get("brand_split") and row.brand == BRAND_COMMON:
            run.skipped["brand_split_common"] += 1  # D125 — 공통 항목을 브랜드마다 둘로 나누는 일은 이 도구 밖
        key, key_type = row.item_key, row.item_type
        if target in RETYPE_NAMES:
            key, key_type = _retype(run, row, item, target), target
            run.skipped["retyped"] += 1  # 옛 사실은 고치지 않는다 — 이름표 · 링크는 새 항목으로
        else:
            if target is not None:  # 공정 단계 = at_step 링크로만 · 브랜드 = 브랜드 칸 틀이 없어 사실 그대로
                run.skipped[f"retype_{target}" if target in ("process_step", "brand") else "retype_unknown"] += 1
            _update(run, row, item, price)
        if price is not None:
            children = price.get("split_into") or []
            for child in children:
                _child(run, row, item, child)
            if not children and price.get("basis") in PRICE_BASES:
                value_links(run, row.item_key, row.item_type, price.get("value_from_hint"), price["basis"], item["id"])
            if price.get("condition_hint"):
                run.skipped["condition_hint"] += len(price["condition_hint"])  # 값이 아니라 조건 경계 — 링크 종류 없음
        copy_links(run, key, key_type, item.get("copy_hint"), item["id"])
        step_link(run, key, key_type, item.get("process_step_hint"), item["id"])
        decided_links(run, key, key_type, item.get("decided"), item["id"])


# ── 새 항목 · 엇갈림 ─────────────────────────────────────────────────────
def _stage_of(new: Mapping[str, Any]) -> str:
    """새 공정 단계의 ERP 단계 정본 코드(``erp`` 가리킴, 없으면 키 끝 — 대문자)."""
    return str(new.get("erp") or new.get("key") or "").rsplit("/", 1)[-1].upper()


def _new_items(run: Run, rows: Iterable[Any]) -> None:
    """새 항목(공정 단계 · 규격 · 용어 — 공통 층 · 공통 브랜드) + 정본 링크(반영 뒤 다음 차례)."""
    for new in rows:
        if not isinstance(new, Mapping) or held(run, new):
            continue
        item_type, key = new.get("type"), str(new.get("key") or "").lower()
        if item_type in TYPE_KINDS and KEY_RE.fullmatch(key):  # 지식 문서 유형(새 가격 규칙 등) — 나눔 자식과 같은 길
            made = _doc_create(run, new, kind=TYPE_KINDS[item_type], cid=key.rsplit("/", 1)[-1],
                               parent=_row(run, new.get("parent_hint")),
                               why=reason("새 지식 문서 항목", decisions_in(new.get("decided"), new.get("why"))))
            if made is not None:
                decided_links(run, *made, new.get("decided"), made[0].rsplit("/", 1)[-1])
            continue
        if item_type not in NEW_TYPES or not KEY_RE.fullmatch(key):
            run.skipped["unknown_type" if KEY_RE.fullmatch(key) else "shape"] += 1
            continue
        label, payload = one_line(new.get("pref_label"), 200) or key, labels_for(new, item_type, pref=False)
        refs = list(new.get("value_from_hint") or [])
        if item_type == "process_step":
            stage = _stage_of(new)
            if stage not in ERP_STAGES:
                run.skipped["shape"] += 1
                continue
            payload["erp_stage"], refs = stage, [f"erp:stage/{stage.lower()}"]
        _create(run, key=key, brand=BRAND_COMMON, layer=LAYER_COMMON, item_type=item_type, ref_id=key,
                values={"name": label, "text": label if item_type == "spec" else None, "visibility": SCOPE_ALL,
                        "payload": payload or None},
                why=reason(f"새 {NEW_TYPES[item_type]} 항목", decisions_in(new.get("why"))))
        value_links(run, key, item_type, refs, None, key)


def _conflicts(run: Run, rows: Iterable[Any]) -> None:
    """엇갈림 — 갈림 · 덮어씀은 ``conflict``, 글만 고칠 것은 ``question`` 항목 + ``about``(반영 뒤 다음 차례).

    키는 다루는 항목 id · 요약 글의 지문(같은 계획을 다시 돌려도 같은 키). 층 · 보기 범위는 다루는 항목이 모두 같으면 그 값,
    섞이면 공통 층 · 관리 범위(좁게)."""
    for conflict in rows:
        if not isinstance(conflict, Mapping) or held(run, conflict):
            continue
        item_type, summary = CONFLICT_TYPES.get(conflict.get("action")), conflict.get("summary")
        about = [a for a in conflict.get("about") or [] if isinstance(a, str)]
        found = [r for r in (_row(run, a) for a in about) if r is not None]
        if len(found) < len(about):
            run.skipped["item_missing"] += len(about) - len(found)
        if item_type is None or not isinstance(summary, str) or not summary.strip():
            run.skipped["unknown_type" if item_type is None else "shape"] += 1
            continue
        if not found:
            run.skipped["conflict_without_item"] += 1
            continue
        digest = hashlib.sha1(json.dumps([sorted(about), summary], ensure_ascii=False).encode("utf-8")).hexdigest()[:10]
        key, ref_id = f"{item_type}/{run.brand.lower()}-{digest}", f"{item_type}-{digest}"
        decisions = decisions_in(conflict.get("resolved_by"), conflict.get("settled_by_earlier"))
        layers, scopes, name = {r.layer for r in found}, {r.visibility for r in found}, " ".join(summary.split())
        _create(run, key=key, brand=run.brand, layer=layers.pop() if len(layers) == 1 else LAYER_COMMON,
                item_type=item_type, ref_id=ref_id,
                values={"name": name if len(name) <= 80 else name[:79] + "…", "text": summary.strip(),
                        "visibility": scopes.pop() if len(scopes) == 1 else SCOPE_ADMIN,
                        "payload": {"plan_action": conflict["action"],
                                    **({"decisions": list(decisions)} if decisions else {})}},
                why=reason("엇갈림 정리" if item_type == "conflict" else "글 고칠 것", decisions))
        run.links += [Link("about", key, item_type, r.item_key, r.item_type, ref_id) for r in found]


# ── 진입점 ───────────────────────────────────────────────────────────────
def file_plan(session: Any, plan: Mapping[str, Any], *, brand: str, apply: bool, source: Optional[str] = None,
              now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """자료 계획을 열린 제안으로 넣는다(반영 없음). ``apply`` 가 아니면 같은 일을 저장점 안에서 하고 되돌린다(쓰기 0) —
    꼴 · 관문 · 바깥 자리 검사까지 그대로 돌아 수가 넣을 때와 같다.

    Args:
        brand: 계획의 브랜드(항목 키 머리 — ``<브랜드>/<문서 id>``, 없으면 ``common/<문서 id>``).
        source: 근거 자리 계획 이름(없으면 계획 ``schema`` 에서).

    Raises:
        BrainShapeError: 계획 꼴이 틀렸다(자리만 — 글 없음).
    """
    problems = plan_problems(plan)
    if problems:
        raise BrainShapeError(problems)
    run = Run(session, brand, source or source_name(plan), now or now_utc_naive(), known_text(session))
    run.steps = {_stage_of(n): str(n.get("key") or "").lower() for n in plan.get("new_items") or []
                 if isinstance(n, Mapping) and n.get("type") == "process_step"}
    savepoint = session.begin_nested()
    try:
        _items(run, plan.get("items") or [])
        _new_items(run, plan.get("new_items") or [])
        _conflicts(run, plan.get("conflicts") or [])
        for retire in run.retires:
            file_retire(run, *retire)
        for link in run.links:
            file_link(run, link)
    except Exception:
        savepoint.rollback()
        raise
    if apply:
        savepoint.commit()
    else:
        savepoint.rollback()
    return {"applied": bool(apply), "brand": brand,
            "plan": {name: len(plan.get(name) or []) for name in ("items", "new_items", "conflicts")},
            **run.summary()}

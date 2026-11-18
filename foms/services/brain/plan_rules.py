"""자료 계획의 제작 조건 · 속성 칸(설계서 2026-11-13 온톨로지 빈 재료 채우기 2판 C · G — 사장님 D201 · D203).

계획(저장소 밖 파일 — 키 · 짧은 글만, 손님 글 · 금액 없음)을 옮기기 묶음(:data:`.proposals.IMPORT_PROPOSER`) 제안으로 넣는다.
반영하지 않는다 — 모두 제안함 ② 한 장씩이다(:mod:`.inbox_bins`).

- **외톨이 제작 조건 0**: 새 제작 조건(사실 나눔 ``items[].fact_to.type == "build_rule"`` · 새 항목 ``new_items[]`` ·
  아래 ``rules[]``)은 ``applies_to`` 끝(제품 라인 · 옵션 — 지금 항목이거나 열린 만들기 제안)이 하나 이상 있어야 넣는다. 없으면
  넣지 않고 ``orphan_rule`` 로 센다. 끝 링크는 만들기가 승인된 뒤 다음 차례(``awaiting_create``)이고 ⑥ 규칙 잇기 표에 든다.
- 제작 조건은 지식 문서 항목으로 만든다(실음 칸에 문서 id — :data:`.constants.OPTIONAL_DOC_TYPES`). 옮긴 글이 상담 두뇌 재료로
  남게 문서 칸(의도 · 꼬리표 · 근거 파일 · 승인 칸)은 옮겨 온 사실 · 정책에서 그대로 가져온다(:func:`doc_fields`).
- ``rules[]`` = ``{"policy": 정책 키, "id": 새 문서 id, "sentence": 정책 글 속 문장 그대로, "applies_to": [끝 키 …],
  "rule_kind"?, "pref_label"?, "why"?}`` → 제작 조건 만들기(글 = 그 문장) + **그 정책 글에서 그 문장을 빼는 고침**을 한 묶음으로.
  같은 문장이 두 곳에 남지도, 한 곳에서도 사라지지도 않게 고침은 새 제작 조건이 반영된 뒤 다음 차례다(사실 나눔의 옛 사실
  은퇴와 같은 차례). 문장은 정책 글에 **꼭 한 번** 나와야 하고(``sentence_missing`` · ``sentence_twice``), 빼고 남는 글이 있어야
  하며(``would_empty``), 글 관문(가림 · 한자 · 숫자는 승인된 글에 있는 것만 — :func:`.gates.text_gates`)을 지나야 한다
  (``gate_failed`` — 옮긴 문장이라 지나야 맞다, 못 지나면 그 줄은 넣지 않는다).
- ``props[]`` = ``{"key": 항목 키, "props": {칸: 값}, "why"?}`` → 실음 칸 고침 하나(G — 이름표가 아니라 내용 칸이라 ②). 받는 칸은
  :data:`PROP_EDITS` 뿐(금액 · 값 칸은 받지 않는다), 값 꼴은 유형 틀(:mod:`.schemas`)이 본다.

세는 까닭은 영어 짧은 코드, 글 · 이름은 세지도 싣지도 않는다.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from foms.services.brain.constants import KEY_RE, LAYER_COMMON, MAX_TEXT, OP_CREATE, OP_UPDATE
from foms.services.brain.gates import FAIL, text_gates
from foms.services.brain.plan_links import (
    DOC_ID, Link, Run, create_item, decisions_in, file_one, held, missing_end, one_line, open_changes, reason,
)
from foms.services.brain.proposals import IMPORT_PROPOSER, after_values, propose_update
from foms.services.brain.schemas import RULE_KINDS
from foms.services.brain.store import current_object, values_of

__all__ = ["PROP_EDITS", "RULE_END_TYPES", "RULE_TYPE", "cut_sentence", "doc_fields", "file_moves", "file_props",
           "file_rules", "rule_ends", "rule_links", "rule_payload"]

RULE_TYPE = "build_rule"
#: 제작 조건 ``applies_to`` 가 걸 수 있는 끝(허용 짝 :data:`.constants.ALLOWED_LINKS` 의 제품 쪽).
RULE_END_TYPES: frozenset[str] = frozenset({"product_line", "option"})
#: 계획이 고칠 수 있는 실음 칸(G — 문 방식 · 견적 규칙 종류 · 최소 · 최대 가로 · 정책 갈래).
PROP_EDITS: dict[str, tuple[str, ...]] = {
    "product_line": ("door_kinds", "quote_kind", "min_width_mm", "max_width_mm"), "policy": ("policy_kind",)}
_PROP_HEADS: dict[str, str] = {"product_line": "제품의 문 방식 · 견적 꼴 · 가로 범위를 적어요", "policy": "정책 갈래를 적어요"}
_DOC_KEYS: tuple[str, ...] = ("intents", "tags", "source", "approved_by", "approved_at")


def _known_type(run: Run, key: str) -> Optional[str]:
    """지금 항목, 없으면 열린 만들기 제안의 유형(둘 다 없으면 ``None`` — 키 머리로 짐작하지 않는다)."""
    current = current_object(run.session, key)
    if current is not None:
        return current.item_type
    pending = open_changes(run.session, OP_CREATE, key)
    return pending[0].item_type if pending else None


def rule_ends(run: Run, keys: Any) -> list[str]:
    """제작 조건이 걸 끝 — 제품 라인 · 옵션으로 있는(또는 만들기가 열린) 키만, 겹침 빼고. 못 쓴 끝은 ``rule_end_dropped``."""
    ends: list[str] = []
    for key in keys if isinstance(keys, list) else []:
        text = key.strip() if isinstance(key, str) else ""
        if KEY_RE.fullmatch(text) and _known_type(run, text) in RULE_END_TYPES:
            ends += [text] if text not in ends else []
        else:
            run.skipped["rule_end_dropped"] += 1
    return ends


def rule_links(run: Run, key: str, ends: Iterable[str], ref_id: str, decisions: tuple[str, ...] = ()) -> list[Link]:
    """새 제작 조건 → 제품 라인 · 옵션 ``applies_to`` 링크들(넣기는 :func:`.plan_links.file_link`)."""
    return [Link("applies_to", key, RULE_TYPE, end, _known_type(run, end), ref_id,
                 decisions=tuple(dict.fromkeys([*decisions, "D201"]))) for end in ends]


def rule_payload(block: Any) -> dict[str, Any]:
    """제작 조건 틀 칸(조건 꼴 — 필요 · 함께 못 함 · 한도)만."""
    kind = block.get("rule_kind") if isinstance(block, Mapping) else None
    return {"rule_kind": kind} if kind in RULE_KINDS else {}


def doc_fields(base: Any, doc_id: str) -> dict[str, Any]:
    """새 지식 문서 항목의 문서 칸 — 옮겨 온 항목의 의도 · 꼬리표 · 근거 파일 · 승인 칸(같은 승인 글) + 새 문서 id."""
    base = base if isinstance(base, Mapping) else {}
    fields = {name: base.get(name) for name in _DOC_KEYS}
    return {"doc_id": doc_id[:64], **fields, "intents": list(base.get("intents") or []),
            "tags": list(base.get("tags") or [])}


def cut_sentence(text: str, sentence: str) -> str:
    """글에서 문장 하나를 빼고 그 자리의 빈칸 · 빈 줄만 고른다(다른 줄은 손대지 않는다)."""
    at = text.index(sentence)
    before, after = text[:at].rstrip(" \t"), text[at + len(sentence):].lstrip(" \t")
    if before.endswith("\n") and after.startswith("\n"):
        after = after[1:]  # 그 줄 전체가 문장이었다
    elif before and after and not before.endswith("\n") and not after.startswith("\n"):
        before += " "
    return (before + after).strip()


# ── 정책 속 제작 조건 문장 옮기기 ────────────────────────────────────────
def file_rules(run: Run, rows: Iterable[Any]) -> None:
    """``rules[]`` — 제작 조건 만들기 + ``applies_to`` 링크 모으기 + 정책 고침 차례(:func:`file_moves`)."""
    for row in rows:
        if not isinstance(row, Mapping) or held(run, row):
            continue
        policy_key, doc_id = str(row.get("policy") or ""), str(row.get("id") or "")
        sentence = one_line(row.get("sentence"), MAX_TEXT)
        if not KEY_RE.fullmatch(policy_key) or not DOC_ID.fullmatch(doc_id) or sentence is None:
            run.skipped["shape"] += 1
            continue
        policy = current_object(run.session, policy_key)
        if policy is None or policy.item_type != "policy":
            run.skipped["not_policy" if policy is not None else "end_missing"] += 1
            continue
        key, ref_id = f"{policy_key.split('/')[0]}/{doc_id}", f"rules/{policy_key}>{doc_id}"
        ends = rule_ends(run, row.get("applies_to"))
        if not ends:
            run.skipped["orphan_rule"] += 1
            continue
        if current_object(run.session, key) is None:
            problem = _move_problem(run, policy.text or "", sentence)
            if problem:
                run.skipped[problem] += 1
                continue
            create_item(run, key=key, brand=policy.brand, layer=LAYER_COMMON, item_type=RULE_TYPE, ref_id=ref_id,
                        values={"name": one_line(row.get("pref_label"), 200) or doc_id, "text": sentence,
                                "visibility": policy.visibility, "checked_at": values_of(policy)["checked_at"],
                                "payload": {**doc_fields(policy.payload, doc_id), **rule_payload(row)}},
                        why=reason(f"정책 글 속 제작 조건 문장을 제작 조건 지식으로 옮겨요 — 정책({policy_key}) 글에서는 빼요",
                                   decisions_in(row.get("why"), "D201")))
        run.links += rule_links(run, key, ends, ref_id, decisions_in(row.get("why")))
        run.moves.append((policy_key, key, sentence, ref_id))


def _move_problem(run: Run, text: str, sentence: str) -> Optional[str]:
    """정책 글에서 문장을 옮길 수 없는 까닭(없으면 ``None``)."""
    count = text.count(sentence)
    if count != 1:
        return "sentence_missing" if count == 0 else "sentence_twice"
    if not cut_sentence(text, sentence):
        return "would_empty"
    if FAIL in text_gates([sentence], run.known).values():
        return "gate_failed"
    return None


def file_moves(run: Run) -> None:
    """정책 글에서 옮긴 문장 빼기 — 새 제작 조건이 반영된 뒤에만(그 전은 다음 차례). 까닭에 새 항목 키를 적는다."""
    for policy_key, key, sentence, ref_id in run.moves:
        policy = current_object(run.session, policy_key)
        text = (policy.text or "") if policy is not None else ""
        if policy is None:
            missing_end(run, policy_key)
        elif sentence not in text:
            run.skipped["same"] += 1  # 이미 뺐다
        elif current_object(run.session, key) is None:
            missing_end(run, key)
        elif text.count(sentence) != 1:
            run.skipped["sentence_twice"] += 1
        else:
            after = {"text": cut_sentence(text, sentence)}
            if any(after_values(c.fields) == after for c in open_changes(run.session, OP_UPDATE, policy_key)):
                run.skipped["open_proposal"] += 1
                continue
            file_one(run, "update:move_out", lambda: propose_update(
                run.session, key=policy_key, base_version=policy.version, after=after, proposer=IMPORT_PROPOSER,
                reason=reason(f"이 문장을 새 제작 조건 지식({key})으로 옮겨서 정책 글에서는 빼요", ("D201",)),
                evidence=[run.ref(ref_id)], now=run.now, known=run.known))


# ── 속성 칸(G) ───────────────────────────────────────────────────────────
def file_props(run: Run, rows: Iterable[Any]) -> None:
    """``props[]`` — 항목마다 실음 칸 고침 하나(받는 칸만 · 이미 같은 값 · 같은 열린 제안이면 넘김)."""
    for row in rows:
        if not isinstance(row, Mapping) or held(run, row):
            continue
        key, props = str(row.get("key") or ""), row.get("props")
        if not KEY_RE.fullmatch(key) or not isinstance(props, Mapping) or not props:
            run.skipped["shape"] += 1
            continue
        current = current_object(run.session, key)
        if current is None:
            missing_end(run, key)
            continue
        allowed = PROP_EDITS.get(current.item_type, ())
        want = {name: value for name, value in props.items() if name in allowed and value not in (None, "", [])}
        if len(want) < len(props):
            run.skipped["prop_not_allowed"] += len(props) - len(want)
        payload = dict(current.payload or {})
        after = {"payload": {**payload, **want}}
        if not want:
            continue
        if after["payload"] == payload:
            run.skipped["same"] += 1
            continue
        if any(after_values(c.fields) == after for c in open_changes(run.session, OP_UPDATE, key)):
            run.skipped["open_proposal"] += 1
            continue
        file_one(run, "update:props", lambda: propose_update(
            run.session, key=key, base_version=current.version, after=after, proposer=IMPORT_PROPOSER,
            reason=reason(_PROP_HEADS[current.item_type], decisions_in(row.get("why"))),
            evidence=[run.ref(f"props/{key}")], now=run.now, known=run.known))

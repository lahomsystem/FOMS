"""판정자에게 보이는 한 걸음 이웃 — 후보 지식마다 그 지식에서 **나가는** 살아 있는 잇기를 한 줄로(설계 글
``docs/specs/2026-11-26-brain-ontology-linking_SPEC.md`` 7.4 · 차례 9).

밤 배우기의 놓을 자리 판정자(:mod:`foms.services.cs_agent.handoff_learning_place`)와 엇갈림 판정자
(:mod:`foms.services.cs_agent.handoff_learning_judge`)는 후보 지식의 글만 받아, 그 지식이 어느 옵션 · 수량 표 · 낱말에 기대는지
못 봤다('통 당 값 × 통 수' 금액을 부딪침으로 봄 — 비평 3.3). 후보 줄 아래에 이렇게 붙인다::

      ↳ 이어진 것: 적용 대상 → 옵션 '합성 옵션'(단위 통) · 수량을 따르는 표 → 규격 '합성 표' — 앞 한 문장 · 값은 견적 계산기(옵션 '…')

- **잇기**: 후보에서 나가는 지금 판 · 유효 기간 안 잇기만(:func:`.store.is_current` · :func:`.store.in_force`). 이름은 카드와 같은
  나가는 쪽 이름(:func:`.display.link_side_label`).
- **끝이 회사 지식이면**: 반영 · 지금 판 · 유효(:func:`.read.effective_clauses`) + **모두가 보는 지식**(보기 범위 ``all``)만, 같은
  브랜드(:func:`.ai_gates.same_brand`)만. 이름이 가림 관문에 걸리면 그 이웃은 뺀다(:func:`.embeddings.safe_text`). 끝의 단위
  (``payload.unit`` · ``payload.price_unit``)가 있으면 '(단위 ○)'. 잇기가 :data:`GIST_KINDS` 이고 끝이 :data:`GIST_TYPES` 면 그 글의
  앞 한 문장(:data:`GIST_CHARS` 자 안 — 가림에 걸리면 싣지 않는다)도.
- **끝이 바깥 정본이면**: 이름만 — 계산기는 계산기 정본의 옵션 · 제품 이름, ERP 단계는 단계 이름, 설정은 '설정 값'(키는 코드 말이라
  싣지 않는다). **금액 · 설정 값은 싣지 않는다**(보기 범위 규칙 — 판정자에게도 가격 재량 값이 가지 않게).
- **상한**: 후보 하나에 이웃 :data:`MAX_NEIGHBOURS` 개 · 줄 하나 :data:`LINE_CHARS` 자(넘는 이웃은 뺀다 — 중간에서 자르지 않는다).
  차례는 :data:`KIND_ORDER`(값 · 수량 · 낱말이 먼저) → 끝 키.
- **조회**: 후보 묶음에 한 번 — 잇기 한 번 · 끝 지식 한 번 · (계산기 끝이 있으면) 계산기 정본 한 번.

잇기가 없는 후보는 줄이 없다(판정자 요청 글이 예전과 같다). 켜고 끄는 설정 칸은 없다.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Mapping, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainLink, BrainObject
from foms.services.brain.ai_gates import same_brand
from foms.services.brain.constants import (
    EXT_CALCULATOR, EXT_ERP_STAGE, LINK_KINDS, SCOPE_ALL, external_type,
)
from foms.services.brain.display import link_side_label, type_label
from foms.services.brain.embeddings import safe_text
from foms.services.brain.external import CALC, ERP_STAGE, OPTION, PRODUCT, ref_cards
from foms.services.brain.read import effective_clauses
from foms.services.brain.scope import SYSTEM
from foms.services.brain.store import in_force, is_current

__all__ = ["GIST_CHARS", "GIST_KINDS", "GIST_TYPES", "HEAD", "KIND_ORDER", "LINE_CHARS", "MAX_NEIGHBOURS", "NAME_CHARS",
           "first_sentence", "neighbour_lines"]

MAX_NEIGHBOURS, LINE_CHARS, GIST_CHARS, NAME_CHARS = 5, 300, 120, 60
#: 후보 줄 아래 붙는 줄 머리(판정자 지시문이 이 말을 가리킨다).
HEAD = "  ↳ 이어진 것: "
#: 끝 글의 앞 한 문장을 같이 싣는 잇기 · 끝 유형(판정자가 '통 수 표' · 낱말의 뜻을 알게).
GIST_KINDS = frozenset({"quantity_from", "refines", "uses"})
GIST_TYPES = frozenset({"spec", "term"})
#: 이웃 차례 — 값 · 수량 · 낱말 · 적용이 먼저, 나머지는 :data:`.constants.LINK_KINDS` 차례.
KIND_ORDER: tuple[str, ...] = tuple(dict.fromkeys(("value_from", "quantity_from", "uses", "applies_to", "refines",
                                                   *LINK_KINDS)))
_RANK = {kind: i for i, kind in enumerate(KIND_ORDER)}
_SENTENCE = re.compile(r"^(.+?[.!?])(?:\s|$)")
_CALC_WORDS = {PRODUCT: "제품", OPTION: "옵션"}


def _flat(value: Any) -> str:
    return " ".join(str(value or "").split())


def first_sentence(text: Any, limit: int = GIST_CHARS) -> str:
    """글의 앞 한 문장(마침표 · 물음표 · 느낌표까지) — ``limit`` 자를 넘으면 잘라 '…'."""
    flat = _flat(text)
    found = _SENTENCE.match(flat)
    head = found.group(1) if found else flat
    return head if len(head) <= limit else head[:limit - 1].rstrip() + "…"


def _unit(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    unit = payload.get("unit") or payload.get("price_unit")
    return unit if isinstance(unit, str) else ""


def _item_part(kind: str, owner_type: Optional[str], row: Any) -> Optional[str]:
    """끝이 회사 지식인 이웃 한 조각(이름이 가림에 걸리면 ``None``)."""
    name = _flat(row.name)[:NAME_CHARS]
    if not safe_text(name):
        return None
    unit = _unit(row.payload)
    part = f"{link_side_label(kind, 'out', owner_type)} → {type_label(row.item_type)} '{name}'"
    part += f"(단위 {unit})" if unit else ""
    if kind in GIST_KINDS and row.item_type in GIST_TYPES and row.text:
        gist = first_sentence(row.text)
        if safe_text(gist):
            part += f" — {gist}"
    return part


def _calc_word(ref: str) -> str:
    path = ref[len(CALC):]
    return next((word for prefix, word in _CALC_WORDS.items() if path.startswith(prefix)), "")


def _external_part(kind: str, owner_type: Optional[str], ref: str, labels: Mapping[str, str]) -> str:
    """끝이 바깥 정본 · 사본인 이웃 한 조각 — 이름만(금액 · 설정 값 없음)."""
    ext = external_type(ref) or ""
    label = labels.get(ref, "")
    named = ""
    if ext == EXT_CALCULATOR and label:
        named = f"({_calc_word(ref)} '{label}')" if _calc_word(ref) else f"('{label}')"
    elif ext == EXT_ERP_STAGE and label:
        named = f" '{label}'"
    if kind == "value_from":
        return f"값은 {type_label(ext)}{named}"
    return f"{link_side_label(kind, 'out', owner_type)} → {type_label(ext)}{named}"


def _external_labels(session: Any, refs: list[str]) -> dict[str, str]:
    """계산기 · ERP 단계 끝 → 이름(계산기 정본은 한 번 읽는다 · 못 읽으면 이름 없이). 값 칸은 쓰지 않는다."""
    chips = [{"ref": ref, "kind": "", "ext_type": external_type(ref)} for ref in refs
             if ref.startswith(CALC) or ref.startswith(ERP_STAGE)]
    if not chips:
        return {}
    out = {}
    for card in ref_cards(session, SYSTEM, chips):
        label = _flat(card.get("label"))[:NAME_CHARS]
        if card.get("exists") and label and safe_text(label):
            out[card["ref"]] = label
    return out


def _join(parts: list[str]) -> str:
    """조각 → 한 줄(이웃 :data:`MAX_NEIGHBOURS` 개 · :data:`LINE_CHARS` 자 안 — 넘는 조각은 뺀다)."""
    kept: list[str] = []
    for part in parts:
        if len(kept) >= MAX_NEIGHBOURS:
            break
        if len(HEAD + " · ".join([*kept, part])) <= LINE_CHARS:
            kept.append(part)
    return HEAD + " · ".join(kept) if kept else ""


def neighbour_lines(session: Any, owners: Mapping[str, Optional[str]], *, today: datetime.date,
                    brand: Optional[str] = None) -> dict[str, str]:
    """후보 키 → '이어진 것' 줄(모듈 설명). ``owners`` 는 후보 키 → 그 후보 유형(나가는 쪽 이름이 유형마다 갈리는 짝 —
    :data:`.display.LINK_SIDE_BY_TYPE`). 이어진 것이 하나도 없는 후보는 빠진다. 쓰지 않는다."""
    keys = [k for k in dict.fromkeys(owners) if k]
    if not keys:
        return {}
    links = session.execute(select(BrainLink.from_key, BrainLink.kind, BrainLink.to_key).where(
        BrainLink.from_key.in_(keys), is_current(BrainLink), in_force(BrainLink, today))).all()
    if not links:
        return {}
    ends = sorted({to for _f, _k, to in links if external_type(to) is None})
    rows = {row.item_key: row for row in session.execute(select(BrainObject).where(
        BrainObject.item_key.in_(ends), *effective_clauses(SYSTEM, today),
        BrainObject.visibility == SCOPE_ALL)).scalars()} if ends else {}
    labels = _external_labels(session, sorted({to for _f, _k, to in links if external_type(to) is not None}))
    parts: dict[str, list[str]] = {}
    for src, kind, to in sorted(links, key=lambda r: (r[0], _RANK.get(r[1], len(_RANK)), r[2])):
        if external_type(to) is not None:
            part: Optional[str] = _external_part(kind, owners.get(src), to, labels)
        elif to in rows and same_brand(brand, rows[to].brand):
            part = _item_part(kind, owners.get(src), rows[to])
        else:
            part = None
        if part:
            parts.setdefault(src, []).append(part)
    out = {key: _join(found) for key, found in parts.items()}
    return {key: line for key, line in out.items() if line}

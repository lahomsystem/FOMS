"""챗봇 찾기 — 가린 질문 → 묻는 사람의 보기 범위 안 후보 묶음(설계서 10.2 의 2 · 17.9-2 · 조사 '화면 설계' 에이전트 절).

**모델이 보기 전에 거른다**: 후보는 유형 있는 읽기 도구(:mod:`.chat_tools` — 찾기 · 키 하나 · 이웃)로만 모으고, 그 도구가 모두
보기 범위 · 유효 기간 · 반영 상태로 질의 단계에서 거른다. 볼 수 없는 항목은 후보 · 이웃 · 수 어디에도 없다.

- 후보 = 찾기(글자 · 다른 이름 · 켜졌으면 벡터를 RRF 로 섞은 순 — D114) 앞 :data:`TOP` 개 + 앞 :data:`AROUND_FROM` 개의
  한 걸음 이웃(Search Around)에서 몇 개 — 정체 유형만
  (공통 바탕 · 상담 · 도면 층 — 관찰 · 에이전트 일은 근거로 쓰지 않는다 — 17.5 '정체성과 관찰 분리').
- **'확인 필요'**(낡음 — 확인 날 지남 · 열린 제안 · 열린 엇갈림 · 서로 다른 사람 둘 이상의 틀림 신고)는 '확인 필요'라는 사실만 후보로 간다 —
  글 · 값을 싣지 않고 근거로 고를 수도 없다(3.1 규칙 4 · 10.2 의 2 · 12절).
- 쓸 수 있는 후보에는 글(앞부분) · 속성 틀 눈에 띄는 칸 · 계산기 값(가격 재량 범위를 볼 수 있는 사람만 — :mod:`.external`)을 싣는다.
  숫자 허용 목록(:func:`known_numbers_text`)은 근거로 고른 후보의 이 재료뿐이다(10.2 의 4).
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainChange, BrainLink, BrainObject
from foms.services.brain.chat_reports import reported_keys
from foms.services.brain.chat_tools import neighbours_of, search_objects
from foms.services.brain.conflicts import open_conflict_counts
from foms.services.brain.constants import (
    CHANGE_OPEN, CONFIDENCES, EXTERNAL_PREFIXES, IDENTITY_TYPES,
)
from foms.services.brain.display import CONFIDENCE_LABELS, LAYER_LABELS, type_label
from foms.services.brain.external import CALC, ref_cards
from foms.services.brain.labels import pref_of
from foms.services.brain.read import effective_clauses
from foms.services.brain.schemas import key_fields
from foms.services.brain.scope import Viewer
from foms.services.brain.store import in_force, is_current, values_of

TOP, AROUND_FROM, AROUND_EACH, MAX_CANDIDATES = 10, 3, 3, 16
TEXT_CHARS = 600
WHY_STALE, WHY_OPEN, WHY_REPORTED, WHY_CONFLICT = "stale", "open_change", "reported", "conflict"
WHY_LABELS = {WHY_STALE: "확인 날이 지남", WHY_OPEN: "고치는 제안이 열려 있음", WHY_REPORTED: "틀림 신고 둘 이상",
              WHY_CONFLICT: "열린 엇갈림"}


@dataclass
class Candidate:
    """후보 하나 — 쓸 수 있으면 글 · 칸 · 계산기 값까지, '확인 필요'면 이름 · 까닭만."""

    key: str
    name: str
    item_type: str
    layer: str
    confidence: str
    checked_at: Optional[str]
    via: str
    usable: bool = True
    why: Optional[str] = None
    text: str = ""
    fields: list[str] = field(default_factory=list)
    calc: list[str] = field(default_factory=list)
    copies: list[str] = field(default_factory=list)

    def prompt_row(self) -> dict[str, Any]:
        """모델에 가는 줄(자료 — 지시 아님)."""
        if not self.usable:
            return {"key": self.key, "name": self.name, "type": type_label(self.item_type),
                    "check": WHY_LABELS.get(self.why or "", "확인 필요")}
        return {"key": self.key, "type": type_label(self.item_type), "layer": LAYER_LABELS.get(self.layer, self.layer),
                "name": self.name, "confidence": CONFIDENCE_LABELS.get(self.confidence, self.confidence),
                "checked_at": self.checked_at, "text": self.text, "fields": self.fields, "calc": self.calc,
                "copies": self.copies}


@dataclass
class Retrieval:
    """찾기 결과 — 후보들(쓸 수 있는 것 먼저 · 점수 순)."""

    candidates: list[Candidate]

    @property
    def usable(self) -> list[Candidate]:
        """근거로 고를 수 있는 후보."""
        return [c for c in self.candidates if c.usable]

    @property
    def checks(self) -> list[Candidate]:
        """'확인 필요' 후보."""
        return [c for c in self.candidates if not c.usable]

    def by_key(self) -> dict[str, Candidate]:
        """키 → 후보."""
        return {c.key: c for c in self.candidates}


def needs_check(session: Any, rows: list[BrainObject], today: datetime.date) -> dict[str, str]:
    """'확인 필요' 항목 → 까닭(낡음 · 열린 제안 · 틀림 신고 둘 이상). 묶음 질의."""
    keys = [r.item_key for r in rows]
    if not keys:
        return {}
    out = {r.item_key: WHY_STALE for r in rows if r.stale_after is not None and r.stale_after < today}
    opened = set(session.execute(select(BrainChange.item_key).where(BrainChange.item_key.in_(keys),
                                                                    BrainChange.status == CHANGE_OPEN)).scalars())
    out.update({k: WHY_OPEN for k in opened if k not in out})
    out.update({k: WHY_CONFLICT for k in open_conflict_counts(session, keys, today) if k not in out})
    out.update({k: WHY_REPORTED for k in reported_keys(session, keys) if k not in out})
    return out


def _calc_values(session: Any, viewer: Viewer, keys: list[str], today: datetime.date) -> dict[str, list[str]]:
    """항목 → 계산기 지금 값 글(볼 수 있는 사람만 — 가격 재량 범위). 설정 값은 싣지 않는다(요약뿐이라 답 재료가 아님)."""
    if not keys:
        return {}
    rows = session.execute(select(BrainLink.from_key, BrainLink.kind, BrainLink.to_key).where(
        BrainLink.from_key.in_(keys), is_current(BrainLink), in_force(BrainLink, today),
        BrainLink.to_key.like(CALC + "%"))).all()
    chips = [{"from": src, "kind": kind, "ref": ref, "ext_type": next(
        (v for p, v in EXTERNAL_PREFIXES.items() if ref.startswith(p)), None)} for src, kind, ref in rows]
    out: dict[str, list[str]] = {}
    for card in ref_cards(session, viewer, chips) if chips else []:
        if card.get("exists") and card.get("value") and not card.get("value_hidden"):
            out.setdefault(card["from"], []).append(f"{card['label']} — {card['value']}")
    return out


def _candidate(row: BrainObject, *, via: str, why: Optional[str], calc: list[str]) -> Candidate:
    """줄 → 후보(확인 필요면 글 · 칸 · 값을 싣지 않는다)."""
    base = Candidate(key=row.item_key, name=pref_of(row.name, row.payload), item_type=row.item_type, layer=row.layer,
                     confidence=row.confidence, checked_at=row.checked_at.isoformat() if row.checked_at else None,
                     via=via)
    if why is not None:
        base.usable, base.why = False, why
        return base
    values = values_of(row)
    text = row.text or ""
    base.text = text[:TEXT_CHARS] + ("…" if len(text) > TEXT_CHARS else "")
    base.fields = [f"{f['label']}: {f['value']}" for f in key_fields(values, row.item_type) if f["value"]]
    base.calc = calc
    base.copies = [c for c in (row.copies or []) if isinstance(c, str)][:10]  # 이 값을 쓰는 곳(사본 목록 — 이름만)
    return base


def retrieve(session: Any, viewer: Viewer, question: str, *, today: datetime.date,
             vector: Optional[list[float]] = None) -> Retrieval:
    """가린 질문 → 후보 묶음(보기 범위 안 · 정체 유형 · 반영만). ``vector`` = 가린 질문의 벡터(의미 찾기 — 없으면 글자만)."""
    hits = [h for h in search_objects(session, viewer, question, today=today, limit=TOP * 2, vector=vector)
            if h["type"] in IDENTITY_TYPES][:TOP]
    order = [(h["key"], "search") for h in hits]
    seen = {k for k, _v in order}
    for hit in hits[:AROUND_FROM]:
        for near in neighbours_of(session, viewer, hit["key"], today=today, limit=AROUND_EACH * 2):
            if near["key"] not in seen and near["type"] in IDENTITY_TYPES and len(order) < MAX_CANDIDATES:
                order.append((near["key"], "neighbour"))
                seen.add(near["key"])
    if not order:
        return Retrieval([])
    rows = {r.item_key: r for r in session.execute(select(BrainObject).where(
        BrainObject.item_key.in_([k for k, _v in order]), *effective_clauses(viewer, today))).scalars()}
    checks = needs_check(session, list(rows.values()), today)
    calc = _calc_values(session, viewer, [k for k in rows if k not in checks], today)
    found = [_candidate(rows[k], via=via, why=checks.get(k), calc=calc.get(k, [])) for k, via in order if k in rows]
    return Retrieval(sorted(found, key=lambda c: not c.usable))


def prompt_block(retrieval: Retrieval) -> str:
    """모델에 가는 후보 묶음(JSON — 쓸 수 있는 것 · 확인 필요 따로)."""
    return json.dumps({"usable": [c.prompt_row() for c in retrieval.usable],
                       "needs_check": [c.prompt_row() for c in retrieval.checks]}, ensure_ascii=False, indent=1)


def known_numbers_text(retrieval: Retrieval, keys: list[str]) -> str:
    """숫자 허용 목록 — 근거로 고른 후보의 이름 · 글 · 칸 · 계산기 값(10.2 의 4 — 그 밖의 숫자는 답에 쓰지 않는다)."""
    by_key = retrieval.by_key()
    parts = []
    for key in keys:
        c = by_key.get(key)
        if c is not None and c.usable:
            parts.extend([c.name, c.text, *c.fields, *c.calc])
    return "\n".join(parts)


def weakest_confidence(retrieval: Retrieval, keys: list[str]) -> Optional[str]:
    """근거 가운데 가장 낮은 확신(확정 > 근거 있음 > 관찰)."""
    rank = {c: i for i, c in enumerate(CONFIDENCES)}
    found = [c.confidence for c in retrieval.candidates if c.key in keys and c.confidence in rank]
    return max(found, key=rank.get) if found else None

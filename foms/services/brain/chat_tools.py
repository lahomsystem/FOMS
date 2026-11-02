"""유형 있는 읽기 도구 셋 — ``search_objects`` · ``get_object`` · ``neighbours``(설계서 7.7 · D105 · 조사 '규격 비교' 다음 9).

**모든 도구는 보는 사람(:class:`foms.services.brain.scope.Viewer`)을 받아 질의 단계에서 보기 범위 · 유효 기간으로 거른다** —
볼 수 없는 항목은 결과 · 수 · 이웃 어디에도 없다(모델이 보기 전에 거른다 — 4절 · 12절 첫 줄).

- :func:`search_objects` — 질문 낱말(조사 · 물음말을 뗀 2글자 이상) 이름 · 글 부분 일치 + SKOS 꼴 다른 이름(:mod:`.labels` —
  다른 이름으로 맞으면 대표 이름 · 위 낱말로 한 번 넓힌다) + PostgreSQL 이면 이름 pg_trgm 단어 비슷함. 반영(``active``) 항목만,
  점수 순(이름 > 이름표 > 글 · 질문이 이름을 품음). **질문 벡터를 주면**(의미 찾기 — :mod:`.embeddings` · D114) 글자 · 다른 이름 ·
  벡터 코사인 세 줄을 RRF(:func:`rrf` — k=60)로 섞는다. 벡터 순위도 보기 범위를 SQL 에 건 뒤에 매긴다. 벡터가 없으면(꺼짐 ·
  실패) 지금의 글자 찾기 그대로다.
- :func:`get_object` — 키 하나(볼 수 없거나 없으면 ``None``) + 이름표 + 계산기 · 설정 가리킴의 지금 값(가격은 가격 재량 범위를
  볼 수 있는 사람만 — :func:`foms.services.brain.external.ref_cards`).
- :func:`neighbours_of` — 한 걸음 이웃(Search Around — :func:`foms.services.brain.read.neighbours`).

**에이전트 도구로 내놓는 것은 이 읽기 셋뿐**(:data:`AGENT_TOOLS` — 지금은 읽기만). 챗봇은 쓰지 않는다 — 고칠 말은 사람이 이름 있는
액션 ``propose_edit``(:data:`CHAT_OFFERED_ACTIONS`)으로 제안함에 넣는다. 챗봇은 이 도구를 **코드 쪽에서** 부른다(모델에 도구를
주지 않는다 — 설계서 10.2 '도구 없음 · 출력 꼴 고정').
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Mapping, Optional

from sqlalchemy import func, or_, select

from foms.persistence.brain.models import BrainObject
from foms.services.brain.card import external_chips
from foms.services.brain.constants import CONFIDENCES, LINK_KINDS, STATUS_ACTIVE
from foms.services.brain.embeddings import nearest
from foms.services.brain.external import ref_cards
from foms.services.brain.labels import LABEL_TYPES, label_hits, labels_of, norm, preferred_words
from foms.services.brain.read import _like, current_item, effective_clauses, neighbours
from foms.services.brain.scope import Viewer

_HANGUL = f"{chr(0xAC00)}-{chr(0xD7A3)}"
_WORD = re.compile(f"[0-9A-Za-z{_HANGUL}]+")
#: 낱말 끝 조사(긴 것 먼저) — 떼고 남는 말이 2글자 이상일 때만 뗀다.
_PARTICLES: tuple[str, ...] = tuple(sorted((
    "에서는", "으로는", "이라도", "까지", "부터", "에서", "으로", "에게", "하고", "이랑", "처럼", "보다", "마다", "이나",
    "라도", "은", "는", "이", "가", "을", "를", "에", "의", "도", "로", "와", "과", "만", "랑", "요"), key=len, reverse=True))
#: 물음말 · 흔한 말(찾기에 쓰지 않는다).
STOPWORDS = frozenset({
    "얼마", "얼마나", "얼마예", "어떻게", "무엇", "무엇인가", "뭐", "뭔가", "뭐예", "언제", "어디", "어디서", "어떤", "몇", "혹시",
    "있나", "있나요", "있어", "있어요", "있는", "없는", "인가요", "되나요", "돼요", "되요", "되는", "알려", "알려주", "주세요",
    "해주세요", "궁금", "궁금해", "궁금해요", "합니까", "입니까", "가요", "나요", "하나요", "해요", "인지", "건가요", "그리고",
    "하는", "하면", "해야", "할까", "할까요", "좀", "제일", "가장", "까요", "거", "것", "수", "우리", "회사", "지금", "보통",
    "말해", "말해주", "얼마인가요", "얼마예요", "인가", "건가", "입니다", "있습니까", "되나", "되죠", "맞나요", "맞죠",
})
MAX_TOKENS, FETCH_ROWS, SNIPPET = 12, 200, 400
DEFAULT_LIMIT, NEIGHBOUR_LIMIT = 12, 6
#: 에이전트 도구로 내놓는 이름(읽기만 — 쓰기 액션은 아직 하나도 도구로 내놓지 않는다).
AGENT_TOOLS: tuple[str, ...] = ("brain_search_objects", "brain_get_object", "brain_neighbours")
#: 챗봇 화면이 권하는 이름 있는 액션(사람이 누름 — :mod:`.actions` 정본, 서비스는 제안만 만든다).
CHAT_OFFERED_ACTIONS: tuple[str, ...] = ("propose_edit",)


def terms(text: str) -> list[str]:
    """찾기 낱말 — 2글자 이상 · 조사 뗌 · 물음말 뺌 · 겹침 뺌 · 앞 :data:`MAX_TOKENS` 개."""
    out: list[str] = []
    for raw in _WORD.findall(text or ""):
        word = raw.lower()
        for particle in _PARTICLES:
            if word.endswith(particle) and len(word) - len(particle) >= 2:
                word = word[: -len(particle)]
                break
        if len(word) >= 2 and word not in STOPWORDS and raw.lower() not in STOPWORDS:
            out.append(word)
    return list(dict.fromkeys(out))[:MAX_TOKENS]


def _light(row: BrainObject, *, score: float, matched: list[str]) -> dict[str, Any]:
    """찾기 줄(글은 앞부분만)."""
    text = row.text or ""
    return {"key": row.item_key, "name": row.name, "type": row.item_type, "layer": row.layer, "brand": row.brand,
            "confidence": row.confidence, "checked_at": row.checked_at.isoformat() if row.checked_at else None,
            "stale_after": row.stale_after.isoformat() if row.stale_after else None, "visibility": row.visibility,
            "text": text[:SNIPPET] + ("…" if len(text) > SNIPPET else ""), "score": round(score, 2), "matched": matched}


def score_values(name: str, text: str, question: str, words: list[str], label: Optional[str] = None,
                 extra: tuple[str, ...] = ()) -> tuple[float, list[str]]:
    """한 항목 점수 · 맞은 말 — 질문이 이름을 품음 6 · 이름 낱말 3 · 이름표 6 · 넓힌 말 2 · 글 낱말 1(셋까지)."""
    name_n, text_n, q_n = norm(name), norm(text), norm(question)
    score, matched = 0.0, []
    if len(name_n) >= 2 and name_n in q_n:
        score += 6
        matched.append(name)
    for word in words:
        if word in name_n:
            score += 3
            matched.append(word)
    if label:
        score += 6
        matched.append(label)
    for word in extra:
        if norm(word) and (norm(word) in name_n or norm(word) in text_n):
            score += 2
    text_hits = [w for w in words if w in text_n and w not in name_n]
    score += min(3, len(text_hits))
    matched.extend(text_hits[:3])
    return score, list(dict.fromkeys(matched))


def _label_rows(session: Any, viewer: Viewer, today: datetime.date) -> list[tuple[str, str, Any]]:
    """볼 수 있는 · 반영 · 유효 기간 안 이름표 유형 줄 — (키, 이름, 실음 칸)."""
    rows = session.execute(select(BrainObject.item_key, BrainObject.name, BrainObject.payload).where(
        *effective_clauses(viewer, today), BrainObject.item_type.in_(LABEL_TYPES)).limit(5000)).all()
    return [tuple(r) for r in rows]


RRF_K, VECTOR_K, VECTOR_MIN = 60, 10, 0.3


def rrf(lists: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """순위 섞기(Reciprocal Rank Fusion) — 줄마다 1/(k + 순위)를 더한 값 순(같으면 키 순)."""
    scores: dict[str, float] = {}
    for ranked in lists:
        for rank, key in enumerate(dict.fromkeys(ranked), start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def _fuse(session: Any, viewer: Viewer, lexical: list[dict[str, Any]], hits: dict[str, str],
          vector: list[float], *, today: datetime.date) -> list[dict[str, Any]]:
    """글자 · 다른 이름 · 벡터 세 줄 → RRF 순 항목들(벡터로만 닿은 항목도 보기 범위 · 반영 조건으로 다시 읽는다)."""
    near = [(key, sim) for key, sim in nearest(session, viewer, vector, today=today, limit=VECTOR_K) if sim >= VECTOR_MIN]
    by_key = {r["key"]: r for r in lexical}
    missing = [key for key, _sim in near if key not in by_key]
    if missing:
        for row in session.execute(select(BrainObject).where(BrainObject.item_key.in_(missing),
                                                             *effective_clauses(viewer, today))).scalars():
            by_key[row.item_key] = _light(row, score=0.0, matched=[])
    sims = dict(near)
    fused = rrf([[r["key"] for r in lexical], sorted(hits, key=lambda k: -len(hits[k])), [k for k, _s in near]])
    out = []
    for key, score in fused:
        if key in by_key:
            out.append({**by_key[key], "score": round(score, 5), "similarity": round(sims[key], 4) if key in sims else None})
    return out


def search_objects(session: Any, viewer: Viewer, query: str, *, today: datetime.date,
                   limit: int = DEFAULT_LIMIT, vector: Optional[list[float]] = None) -> list[dict[str, Any]]:
    """질문 → 반영 항목 후보(점수 순 · 볼 수 있는 것만). 낱말도 이름표도 벡터도 없으면 빈 목록. ``vector`` 는 가린 질문의 벡터."""
    question = (query or "").strip()[:500]
    words = terms(question)
    label_rows = _label_rows(session, viewer, today)
    hits = label_hits(label_rows, question)
    extra = tuple(w for w in preferred_words(label_rows, hits) if norm(w) not in {norm(x) for x in words})
    wanted = list(dict.fromkeys([*words, *(t for w in extra for t in terms(w))]))[:MAX_TOKENS]
    if not wanted and not hits and vector is None:
        return []
    conds = [or_(BrainObject.name.ilike(_like(w), escape="\\"), BrainObject.text.ilike(_like(w), escape="\\"))
             for w in wanted]
    if hits:
        conds.append(BrainObject.item_key.in_(sorted(hits)))
    postgres = session.get_bind().dialect.name == "postgresql"
    similar = func.word_similarity(BrainObject.name, question) if postgres else None
    if postgres and question:
        conds.append(similar >= 0.5)
    columns = (BrainObject, similar.label("sim")) if postgres else (BrainObject,)
    rows = session.execute(select(*columns).where(*effective_clauses(viewer, today), or_(*conds))
                           .limit(FETCH_ROWS)).all() if conds else []
    found = []
    for row in rows:
        obj, sim = row[0], (float(row[1] or 0) if postgres else 0.0)
        score, matched = score_values(obj.name, obj.text or "", question, words, hits.get(obj.item_key), extra)
        score += 4 * sim if sim >= 0.5 else 0
        if score > 0:
            found.append(_light(obj, score=score, matched=matched))
    found.sort(key=lambda r: (-r["score"], r["key"]))
    if vector is not None:
        found = _fuse(session, viewer, found, hits, vector, today=today)
    return found[:max(1, min(int(limit), 50))]


def get_object(session: Any, viewer: Viewer, key: str, *, today: datetime.date) -> Optional[dict[str, Any]]:
    """키 하나 — 볼 수 없거나 없으면 ``None``. 이름표 · 바깥 정본 지금 값(볼 수 있는 사람만) · 끝났나."""
    item = current_item(session, viewer, key, today)
    if item is None:
        return None
    refs = ref_cards(session, viewer, external_chips(session, key, today), layer=item["layer"])
    return {"key": item["key"], "name": item["name"], "type": item["type"], "layer": item["layer"],
            "brand": item["brand"], "status": item["status"], "confidence": item["confidence"],
            "text": item.get("text") or "", "checked_at": item.get("checked_at"), "stale_after": item.get("stale_after"),
            "ended": item["ended"], "labels": labels_of(item["name"], item.get("payload")),
            "values": [{"ref": r["ref"], "label": r["label"], "value": r["value"]} for r in refs
                       if r.get("exists") and r.get("value") and not r.get("value_hidden")]}


def neighbours_of(session: Any, viewer: Viewer, key: str, *, today: datetime.date,
                  kinds: Optional[tuple[str, ...]] = None, limit: int = NEIGHBOUR_LIMIT) -> list[dict[str, Any]]:
    """한 걸음 이웃(반영 항목만 · 볼 수 있는 것만) — 키 · 이름 · 유형 · 닿은 링크 종류."""
    found = neighbours(session, viewer, key, kinds=kinds, depth=1, limit=limit, today=today)
    if not found:
        return []
    return [{"key": i["key"], "name": i["name"], "type": i["type"], "via": i["via"]} for i in found["items"]
            if i["status"] == STATUS_ACTIVE]


#: 에이전트 도구 표(JSON Schema 입력 — 읽기만). 이름 있는 쓰기 액션 표는 :func:`foms.services.brain.actions.tool_specs`.
READ_TOOL_SPECS: list[dict[str, Any]] = [
    {"name": "brain_search_objects", "description": "회사 지식에서 질문 낱말 · 다른 이름으로 반영 항목을 찾는다(보기 범위 안).",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                      "required": ["query"], "additionalProperties": False}},
    {"name": "brain_get_object", "description": "항목 키 하나의 지금 판(보기 범위 안 · 계산기 값은 볼 수 있는 사람만).",
     "input_schema": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"],
                      "additionalProperties": False}},
    {"name": "brain_neighbours", "description": "항목 하나의 한 걸음 이웃(링크 종류로 거름 · 보기 범위 안).",
     "input_schema": {"type": "object", "properties": {
         "key": {"type": "string"}, "kinds": {"type": "array", "items": {"type": "string", "enum": list(LINK_KINDS)}}},
         "required": ["key"], "additionalProperties": False}},
]


def run_read_tool(session: Any, viewer: Viewer, name: str, args: Mapping[str, Any], *,
                  today: datetime.date) -> Any:
    """읽기 도구 하나를 이름으로 부른다(에이전트 길 — 모르는 이름 · 쓰기 이름은 거절)."""
    if name == "brain_search_objects":
        return search_objects(session, viewer, str(args.get("query") or ""), today=today,
                              limit=int(args.get("limit") or DEFAULT_LIMIT))
    if name == "brain_get_object":
        return get_object(session, viewer, str(args.get("key") or ""), today=today)
    if name == "brain_neighbours":
        kinds = tuple(k for k in (args.get("kinds") or ()) if k in LINK_KINDS) or None
        return neighbours_of(session, viewer, str(args.get("key") or ""), today=today, kinds=kinds)
    raise ValueError("읽기 도구가 아니다")


#: 확신 낮은 쪽부터(답 확신 = 근거 가운데 가장 낮은 것).
CONFIDENCE_RANK: dict[str, int] = {c: i for i, c in enumerate(CONFIDENCES)}

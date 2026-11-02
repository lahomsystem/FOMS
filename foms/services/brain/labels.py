"""SKOS 꼴 이름표(설계서 7.7 · 사장님 D105 · 전사 지식 온톨로지 점검 '지금 4') — 대표 · 다른 · 숨은 이름 · 위 낱말.
**찾기 · 벡터 글이 다른 이름 · 숨은 이름도 본다.**

- 대표 이름(``skos:prefLabel``) = ``payload.pref_label``(비우면 항목 ``name`` — 옮긴 항목은 이름이 문서 id 라 사람 말 이름을
  여기에). 다른 이름(``skos:altLabel``) = ``payload.aliases``(직원 말 · 손님 말 · 계산기 이름 · 도면 이름표). 숨은 이름
  (``skos:hiddenLabel``) = ``payload.hidden_labels``(잘못 쓴 말 · 줄임 — 찾기만, 화면에 안 보임). 위 낱말(``skos:broader``) =
  ``payload.broader``. 칸 꼴은 유형별 속성 틀(:mod:`.schemas`)이 정한다 — 용어 · 제품 라인 · 옵션 · 정책 · 공정 단계(손님용 단계
  이름은 다른 이름 — 7.8 다음 3)(:data:`LABEL_TYPES`).
- 견주기는 띄어쓰기 · 대소문자를 빼고 한다(:func:`norm`). 화면 찾기는 '물은 말이 이름표 안에 있거나 이름표가 물은 말 안에
  있음'(:func:`alias_keys`), 챗봇 찾기는 '이름표가 질문 안에 있음'(:func:`label_hits`)이다.
- 읽는 줄은 지금 판 · 이름표 유형만이다. 보기 범위 · 유효 기간은 부르는 쪽 질의가 다시 건다(여기서 찾은 키는 후보일 뿐 — 볼 수
  없는 항목은 결과 · 수에 들지 않는다).
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainObject
from foms.services.brain.store import is_current

#: 다른 이름 · 위 낱말 칸을 갖는 유형(속성 틀에 ``payload.aliases`` · ``payload.broader`` 가 있다).
LABEL_TYPES: tuple[str, ...] = ("term", "product_line", "option", "policy", "process_step")
#: 이름표 실음 칸(지식 문서 유형인 정책도 이 칸은 둘 수 있다 — :func:`foms.services.brain.gates.object_problems`).
LABEL_PAYLOAD_KEYS = frozenset({"pref_label", "aliases", "hidden_labels", "broader"})
MIN_LABEL = 2
MAX_LABEL_ROWS = 5000
_SPACE = re.compile(r"\s+")


def norm(text: Any) -> str:
    """견주기 꼴 — 띄어쓰기를 빼고 소문자."""
    return _SPACE.sub("", str(text or "")).lower()


def _texts(payload: Any, name: str) -> list[str]:
    """실음 칸 글 목록(글만 · 겹침 뺌)."""
    raw = payload.get(name) if isinstance(payload, Mapping) else None
    return list(dict.fromkeys(a.strip() for a in raw if isinstance(a, str) and a.strip())) if isinstance(raw, list) else []


def aliases_of(payload: Any, *, hidden: bool = True) -> list[str]:
    """찾기 이름표 — 다른 이름(+ 숨은 이름)."""
    return list(dict.fromkeys([*_texts(payload, "aliases"), *(_texts(payload, "hidden_labels") if hidden else [])]))


def pref_of(name: str, payload: Any) -> str:
    """대표 이름 — 실음 칸 ``pref_label``, 없으면 항목 이름."""
    value = payload.get("pref_label") if isinstance(payload, Mapping) else None
    return value.strip() if isinstance(value, str) and value.strip() else name


def broader_of(payload: Any) -> Optional[str]:
    """위 낱말(없으면 ``None``)."""
    value = payload.get("broader") if isinstance(payload, Mapping) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def labels_of(name: str, payload: Any) -> dict[str, Any]:
    """항목 이름표 — ``{"pref", "alt", "hidden", "broader"}``."""
    return {"pref": pref_of(name, payload), "alt": _texts(payload, "aliases"), "hidden": _texts(payload, "hidden_labels"),
            "broader": broader_of(payload)}


def _label_rows(session: Any, keys: Optional[Iterable[str]] = None) -> list[tuple[str, str, Any]]:
    """지금 판 이름표 유형 줄 — (키, 이름, 실음 칸). 범위 · 기간은 부르는 쪽 몫."""
    query = select(BrainObject.item_key, BrainObject.name, BrainObject.payload).where(
        is_current(BrainObject), BrainObject.item_type.in_(LABEL_TYPES))
    if keys is not None:
        query = query.where(BrainObject.item_key.in_(sorted(set(keys))))
    return [tuple(row) for row in session.execute(query.limit(MAX_LABEL_ROWS)).all()]


def alias_keys(session: Any, query: str) -> list[str]:
    """화면 찾기 — 다른 이름이 물은 말을 품거나 물은 말이 다른 이름을 품는 항목 키(범위 · 기간은 부르는 쪽 질의가 건다)."""
    wanted = norm(query)
    if len(wanted) < MIN_LABEL:
        return []
    out = []
    for key, name, payload in _label_rows(session):
        labels = [norm(a) for a in aliases_of(payload)] + ([norm(pref_of(name, payload))] if pref_of(name, payload) != name
                                                            else [])
        if any(len(a) >= MIN_LABEL and (wanted in a or a in wanted) for a in labels):
            out.append(key)
    return out


def label_hits(rows: Iterable[tuple[str, str, Any]], question: str) -> dict[str, str]:
    """챗봇 찾기 — 다른 이름이 질문 안에 있는 항목 키 → 맞은 이름표(긴 것 먼저). ``rows`` 는 (키, 이름, 실음 칸)."""
    text = norm(question)
    hits: dict[str, str] = {}
    for key, name, payload in rows:
        labels = aliases_of(payload) + ([pref_of(name, payload)] if pref_of(name, payload) != name else [])
        found = sorted((a for a in labels if len(norm(a)) >= MIN_LABEL and norm(a) in text),
                       key=lambda a: -len(norm(a)))
        if found:
            hits[key] = found[0]
    return hits


def preferred_words(rows: Iterable[tuple[str, str, Any]], keys: Iterable[str]) -> list[str]:
    """맞은 항목의 대표 이름 · 위 낱말(질문을 넓힐 말 — 다른 이름으로 물어도 대표 이름으로 적힌 항목을 찾게)."""
    chosen = set(keys)
    words: list[str] = []
    for key, name, payload in rows:
        if key in chosen:
            words.append(pref_of(name, payload))
            broader = broader_of(payload)
            if broader:
                words.append(broader)
    return list(dict.fromkeys(w for w in words if w))

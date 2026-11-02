"""꼴 · 글 관문 — 설계서 6절 자동 관문 ① '꼴 · 가림'(상담 17.6 관문 1 그대로) + 항목 꼴 검사(반영 동작이 다시 부른다).

- **글 관문**(:func:`text_gates`): 개인정보 꼴 0(:func:`foms.services.cs_agent.masking.leak_counts`) · 가림 표시 0
  (:func:`foms.services.cs_agent.checks_rules.mask_marker_count`) · 한자 0 · 숫자(금액 · 날짜 · 기간)는 승인 지식 글과
  계산기 값에 이미 있는 숫자만(학습한 숫자가 허용 목록으로 세탁되지 않게 — R10-19). 결과는 관문 이름 → ``pass`` · ``fail``.
- **꼴 검사**(:func:`object_problems`): 값 목록 · 길이 · 날짜 · 유형과 층 · 보기 범위 · 사본 목록 · 유형별 속성 틀
  (:mod:`.schemas` — 제안 때와 반영 때 같은 검사). 지식 문서 유형
  (:data:`.constants.DOC_TYPES`)은 그 항목을 지식 문서 꼴로 바꿔 :func:`foms.services.cs_agent.knowledge_doc.validate_document`
  로 검사한다 — 다시 만든 지식 문서가 늘 상담 두뇌가 받는 꼴이게.
"""

from __future__ import annotations

import datetime
import json
import re
from typing import Any, Iterable, Mapping, Optional

from foms.services.brain.constants import (
    BRAND_COMMON, BRANDS, CONFIDENCES, DOC_TYPES, EVIDENCE_KINDS, GRADES, KEY_RE, MAX_COPIES, MAX_NAME,
    MAX_PAYLOAD_CHARS, MAX_REF, MAX_TEXT, OBJECT_STATUSES, TYPE_LAYERS, TYPES, VISIBILITIES,
)
from foms.services.brain.doc_bridge import DOC_PAYLOAD_KEYS, doc_item_of
from foms.services.brain.labels import LABEL_PAYLOAD_KEYS
from foms.services.brain.schemas import schema_problems
from foms.services.brain.store import DATE_FIELDS, LINK_FIELDS, OBJECT_FIELDS
from foms.services.cs_agent.checks_rules import mask_marker_count
from foms.services.cs_agent.knowledge_doc import KNOWN_BRANDS, KnowledgeSchemaError, validate_document
from foms.services.cs_agent.masking import leak_counts

#: 한자(CJK 통합 한자 · 확장 A · 호환 한자) — 글자 범위는 코드 값으로 만든다(도구가 이스케이프를 글자로 바꾸는 함정).
_HANJA = re.compile(f"[{chr(0x3400)}-{chr(0x4DBF)}{chr(0x4E00)}-{chr(0x9FFF)}{chr(0xF900)}-{chr(0xFAFF)}]")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
PASS, FAIL = "pass", "fail"


# ── 글 관문 ──────────────────────────────────────────────────────────────
def hanja_count(text: str) -> int:
    """한자 글자 수."""
    return len(_HANJA.findall(text or ""))


def numbers_known(text: str, known: str) -> bool:
    """글 속 숫자가 모두 승인 지식 글 · 계산기 값에 이미 있나(쉼표는 떼고 견준다)."""
    plain = (known or "").replace(",", "")
    return all(number.replace(",", "") in plain for number in _NUMBER.findall(text or ""))


def text_gates(texts: Iterable[Optional[str]], known: str) -> dict[str, str]:
    """글 관문 셋 — ``mask``(개인정보 꼴 · 가림 표시 0) · ``hanja``(0) · ``numbers``(승인 지식 · 계산기 값에 있는 숫자만)."""
    rows = [t for t in texts if t]
    mask_ok = all(not any(leak_counts(t).values()) and not mask_marker_count(t) for t in rows)
    return {"mask": PASS if mask_ok else FAIL,
            "hanja": PASS if all(hanja_count(t) == 0 for t in rows) else FAIL,
            "numbers": PASS if all(numbers_known(t, known) for t in rows) else FAIL}


# ── 꼴 검사 ──────────────────────────────────────────────────────────────
def key_problems(key: Any, where: str = "키") -> list[str]:
    """항목 · 링크 키 꼴(소문자 · 숫자 · ``_.:/-`` · 120자 이하)."""
    return [] if isinstance(key, str) and KEY_RE.fullmatch(key) else [f"{where}: 소문자 · 숫자 · '_.:/-' 120자 이하여야 한다"]


def parse_day(value: Any) -> Optional[datetime.date]:
    """``YYYY-MM-DD`` 글 → 날짜(없거나 틀리면 ``None``)."""
    if not isinstance(value, str) or not _DAY.fullmatch(value):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def _line(value: Any, limit: int) -> bool:
    """한 줄 · 비지 않음 · 상한 이하."""
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and "\n" not in value


def _choice_problems(values: Mapping[str, Any]) -> list[str]:
    """값 목록 칸."""
    problems = []
    for name, choices, optional in (("status", OBJECT_STATUSES, False), ("confidence", CONFIDENCES, False),
                                    ("risk_grade", GRADES, True), ("evidence_kind", EVIDENCE_KINDS, True),
                                    ("visibility", VISIBILITIES, False)):
        value = values.get(name)
        if not (value in choices or (optional and value is None)):
            problems.append(f"{name}: {' / '.join(choices)} 가운데 하나여야 한다")
    return problems


def _date_problems(values: Mapping[str, Any]) -> list[str]:
    """날짜 칸 — ``YYYY-MM-DD`` 또는 없음, 유효 시작 ≤ 끝."""
    problems = [f"{name}: 날짜(YYYY-MM-DD)여야 한다" for name in DATE_FIELDS
                if values.get(name) is not None and parse_day(values.get(name)) is None]
    start, end = parse_day(values.get("valid_from")), parse_day(values.get("valid_to"))
    if start and end and start > end:
        problems.append("valid_from: valid_to 보다 늦다")
    return problems


def _body_problems(values: Mapping[str, Any]) -> list[str]:
    """이름 · 글 · 근거 위치 · 사본 목록 · 실음 칸."""
    problems = []
    if not _line(values.get("name"), MAX_NAME):
        problems.append(f"name: {MAX_NAME}자 이하 한 줄이어야 한다")
    text = values.get("text")
    if text is not None and (not isinstance(text, str) or len(text) > MAX_TEXT):
        problems.append(f"text: {MAX_TEXT}자 이하 글이어야 한다")
    if values.get("evidence_ref") is not None and not _line(values.get("evidence_ref"), MAX_REF):
        problems.append(f"evidence_ref: {MAX_REF}자 이하 한 줄이어야 한다")
    copies = values.get("copies")
    if copies is not None and not (isinstance(copies, list) and len(copies) <= MAX_COPIES
                                   and all(_line(c, MAX_REF) for c in copies)):
        problems.append(f"copies: {MAX_COPIES}개 이하 한 줄 글 목록이어야 한다")
    payload = values.get("payload")
    if payload is not None and not (isinstance(payload, dict)
                                    and len(json.dumps(payload, ensure_ascii=False)) <= MAX_PAYLOAD_CHARS):
        problems.append(f"payload: {MAX_PAYLOAD_CHARS}자 이하 객체여야 한다")
    return problems


def _doc_problems(values: Mapping[str, Any], brand: str, item_type: str) -> list[str]:
    """지식 문서 유형 — 지식 문서 꼴 검사(공통 항목은 브랜드마다). 문제 글은 칸 자리만."""
    payload = values.get("payload") if isinstance(values.get("payload"), dict) else {}
    extra = sorted(str(k)[:40] for k in payload if k not in DOC_PAYLOAD_KEYS | LABEL_PAYLOAD_KEYS)
    problems = [f"payload: 모르는 칸 {extra}"] if extra else []
    item = doc_item_of(values, item_type)
    for doc_brand in (sorted(KNOWN_BRANDS) if brand == BRAND_COMMON else [brand]):
        try:
            validate_document({"schema_version": 1, "brand": doc_brand, "items": [item]}, brand=doc_brand)
        except KnowledgeSchemaError as exc:
            problems.extend(f"지식 문서 꼴({doc_brand}): {p}" for p in exc.problems)
    return problems


def object_problems(values: Mapping[str, Any], *, brand: Any, layer: Any, item_type: Any) -> list[str]:
    """항목 하나(정체 + 값 칸)의 꼴 문제. 빈 목록이면 통과."""
    problems = [f"값 칸 밖: {sorted(str(k)[:40] for k in values if k not in OBJECT_FIELDS)}"] if (
        set(values) - set(OBJECT_FIELDS)) else []
    if brand not in BRANDS:
        problems.append(f"brand: {' / '.join(BRANDS)} 가운데 하나여야 한다")
    if item_type not in TYPES:
        problems.append("item_type: 정한 유형이 아니다(유형은 코드 + 설계서로만 더한다)")
    elif layer not in TYPE_LAYERS[item_type]:
        problems.append(f"layer: {item_type} 은 {sorted(TYPE_LAYERS[item_type])} 층에만 둔다")
    problems += _choice_problems(values) + _date_problems(values) + _body_problems(values)
    if not problems:
        problems += schema_problems(values, item_type)  # 유형별 속성 틀(7.7 · D104)
    if not problems and item_type in DOC_TYPES and brand in BRANDS:
        problems += _doc_problems(values, brand, item_type)
    return problems


def link_problems(values: Mapping[str, Any]) -> list[str]:
    """링크 값 칸(확신 · 유효 기간 · 근거 · 실음 칸)의 꼴 문제."""
    problems = [f"값 칸 밖: {sorted(str(k)[:40] for k in values if k not in LINK_FIELDS)}"] if (
        set(values) - set(LINK_FIELDS)) else []
    if values.get("confidence") not in CONFIDENCES:
        problems.append(f"confidence: {' / '.join(CONFIDENCES)} 가운데 하나여야 한다")
    if values.get("evidence_kind") is not None and values.get("evidence_kind") not in EVIDENCE_KINDS:
        problems.append(f"evidence_kind: {' / '.join(EVIDENCE_KINDS)} 가운데 하나여야 한다")
    if values.get("evidence_ref") is not None and not _line(values.get("evidence_ref"), MAX_REF):
        problems.append(f"evidence_ref: {MAX_REF}자 이하 한 줄이어야 한다")
    payload = values.get("payload")
    if payload is not None and not (isinstance(payload, dict)
                                    and len(json.dumps(payload, ensure_ascii=False)) <= MAX_PAYLOAD_CHARS):
        problems.append(f"payload: {MAX_PAYLOAD_CHARS}자 이하 객체여야 한다")
    return problems + _date_problems(values)

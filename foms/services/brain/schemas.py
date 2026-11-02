"""유형별 속성 틀(설계서 7.7 · 사장님 D104 — SHACL 꼴) — 유형마다 칸 · 자료형 · 꼭 있어야 함 · 고른 값 · 범위 · 단위.

- 칸 자리는 줄 칸(``text`` · ``checked_at`` · ``valid_from`` · ``evidence_ref`` …) 또는 ``payload.<칸>``(실음 칸 안).
  지식 문서 유형(정책 · 가격 규칙 · 사장님 결정 · 사실)은 실음 칸이 지식 문서 칸으로 닫혀 있어(:data:`.doc_bridge.DOC_PAYLOAD_KEYS`)
  줄 칸만 쓴다.
- **틀이 있는 유형의 실음 칸은 닫혀 있다** — 틀에 없는 칸(지식 문서 칸 빼고)은 막는다(SHACL ``sh:closed``).
- 검사는 :func:`schema_problems` 하나 — 제안 때와 반영 때 모두 :func:`.gates.object_problems` 가 부른다(문제 글은 칸 자리 ·
  규칙뿐, 값은 싣지 않는다).
- 카드 '눈에 띄는 칸'(:func:`key_fields`)과 제안함 칸별 전 → 후(:func:`diff_rows` — 실음 칸을 틀 칸마다 펼침)가 이 틀을 쓴다.
- **틀이 없는 유형은 :data:`UNSCHEMA_TYPES` 에 적어 둔다**(오늘 꼴 그대로 — 시험이 둘의 합이 모든 유형인지 본다).
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from foms.services.brain.constants import STATUS_ACTIVE
from foms.services.brain.doc_bridge import DOC_PAYLOAD_KEYS

PAYLOAD = "payload."
DATATYPES: tuple[str, ...] = ("text", "int", "number", "date", "enum", "list")


@dataclass(frozen=True)
class Prop:
    """속성 하나 — 자리 · 이름 · 자료형 · 꼭 있어야 함(반영 상태일 때만이면 ``when_active``) · 고른 값 · 범위 · 단위."""

    path: str
    label: str
    datatype: str
    required: bool = False
    when_active: bool = False
    choices: tuple[str, ...] = ()
    low: Optional[float] = None
    high: Optional[float] = None
    unit: Optional[str] = None
    max_len: Optional[int] = None
    max_items: Optional[int] = None
    key: bool = False


def _desc(label: str = "설명", *, required: bool = True) -> Prop:
    """글 칸(설명 · 뜻)."""
    return Prop("text", label, "text", required=required, max_len=2000, key=True)


_CHECKED = Prop("checked_at", "마지막 확인", "date", key=True)
_LEAD = Prop("payload.lead_days", "제작 기간", "int", low=1, high=180, unit="일", key=True)

#: 유형 → 속성 틀(차례 = 카드 · 제안함 차례).
TYPE_SCHEMAS: dict[str, tuple[Prop, ...]] = {
    "product_line": (_desc(), Prop("payload.door_kinds", "문 방식", "list", choices=("hinged", "sliding", "folding",
                                                                                   "none"), max_items=4, key=True),
                     _LEAD),
    "option": (_desc(), Prop("payload.price_kind", "값 방식", "enum", choices=("included", "extra", "quote"), key=True),
               _LEAD),
    "spec": (_desc(), Prop("payload.value", "값", "number", low=0, high=100_000, key=True),
             Prop("payload.unit", "단위", "enum", choices=("mm", "cm", "m", "개", "kg", "%"), key=True),
             Prop("payload.low", "아래 끝", "number", low=0, high=100_000),
             Prop("payload.high", "위 끝", "number", low=0, high=100_000)),
    "build_rule": (_desc("조건"), Prop("payload.rule_kind", "조건 꼴", "enum", choices=("requires", "excludes", "limit"),
                                       key=True), _CHECKED),
    "policy": (_desc("정책 글"), _CHECKED, Prop("valid_from", "유효 시작", "date", key=True)),
    "price_rule": (_desc("규칙 글"), Prop("checked_at", "마지막 확인", "date", when_active=True, key=True),
                   Prop("evidence_ref", "근거 위치", "text", max_len=200, key=True)),
    "owner_decision": (_desc("결정 글"), Prop("evidence_ref", "결정 근거(원장 번호)", "text", max_len=200, key=True),
                       Prop("valid_from", "유효 시작", "date", key=True)),
    "term": (_desc("뜻", required=False), Prop("payload.aliases", "다른 이름", "list", max_items=20, max_len=60, key=True),
             Prop("payload.broader", "위 낱말", "text", max_len=60)),
    "fact": (_desc("사실 글"), _CHECKED),
}
#: 틀이 아직 없는 유형(오늘 꼴 — 꼴 검사만). 틀을 더하면 여기서 뺀다.
UNSCHEMA_TYPES: tuple[str, ...] = (
    "brand", "situation", "template", "lesson", "tone", "image_read_rule", "part_kind", "bom_rule", "drawing_rule",
    "case", "image_read", "photo_observation", "conflict", "question",
)
#: 틀이 있어도 실음 칸에 둘 수 있는 지식 문서 칸(지식 문서 유형 — 옮기기 · 다시 만들기 꼴).
_DOC_KEYS = DOC_PAYLOAD_KEYS
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _is_day(value: Any) -> bool:
    """``YYYY-MM-DD`` 날짜 글인가."""
    if not isinstance(value, str) or not _DAY.fullmatch(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def get(values: Mapping[str, Any], path: str) -> Any:
    """값 칸에서 자리 하나(``payload.<칸>`` 은 실음 칸 안)."""
    if path.startswith(PAYLOAD):
        payload = values.get("payload")
        return payload.get(path[len(PAYLOAD):]) if isinstance(payload, dict) else None
    return values.get(path)


def prop_of(item_type: Optional[str], path: str) -> Optional[Prop]:
    """그 유형 틀의 자리 하나(없으면 ``None``)."""
    return next((p for p in TYPE_SCHEMAS.get(item_type or "", ()) if p.path == path), None)


def payload_props(item_type: Optional[str]) -> tuple[Prop, ...]:
    """그 유형 틀의 실음 칸 속성들(화면이 고칠 칸으로 쓴다)."""
    return tuple(p for p in TYPE_SCHEMAS.get(item_type or "", ()) if p.path.startswith(PAYLOAD))


def _number(value: Any, datatype: str) -> bool:
    """정수 · 수 자료형인가(참 · 거짓은 수가 아니다)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return datatype != "int" or float(value).is_integer()


def _value_problem(prop: Prop, value: Any) -> Optional[str]:
    """값 하나가 틀에 맞지 않는 까닭(맞으면 ``None``)."""
    kind = prop.datatype
    if kind in ("int", "number"):
        if not _number(value, kind):
            return "정수여야 한다" if kind == "int" else "수여야 한다"
        if (prop.low is not None and value < prop.low) or (prop.high is not None and value > prop.high):
            return f"{prop.low:g} ~ {prop.high:g}{prop.unit or ''} 안이어야 한다"
    elif kind == "date" and not _is_day(value):
        return "날짜(YYYY-MM-DD)여야 한다"
    elif kind == "enum" and value not in prop.choices:
        return f"{' / '.join(prop.choices)} 가운데 하나여야 한다"
    elif kind == "text" and (not isinstance(value, str) or (prop.max_len and len(value) > prop.max_len)):
        return f"{prop.max_len or ''}자 이하 글이어야 한다"
    elif kind == "list":
        items = value if isinstance(value, list) else None
        if items is None or (prop.max_items and len(items) > prop.max_items) or not all(
                (x in prop.choices) if prop.choices else (isinstance(x, str) and x.strip() and len(x) <= (
                    prop.max_len or 200)) for x in items):
            return "정한 값 목록이어야 한다" if prop.choices else f"{prop.max_items}개 이하 짧은 글 목록이어야 한다"
    return None


def _empty(value: Any) -> bool:
    """빈 값(없음 · 빈 글 · 빈 목록)."""
    return value is None or (isinstance(value, (str, list)) and not value)


def schema_problems(values: Mapping[str, Any], item_type: Optional[str]) -> list[str]:
    """그 유형 틀에 맞지 않는 칸 — 꼭 있어야 함 · 자료형 · 고른 값 · 범위 · 닫힌 실음 칸 · 아래 끝 ≤ 값 ≤ 위 끝."""
    props = TYPE_SCHEMAS.get(item_type or "")
    if not props:
        return []
    problems = []
    for prop in props:
        value = get(values, prop.path)
        if _empty(value):
            if prop.required or (prop.when_active and values.get("status") == STATUS_ACTIVE):
                problems.append(f"{prop.path}: {prop.label} 칸이 꼭 있어야 한다")
            continue
        problem = _value_problem(prop, value)
        if problem:
            problems.append(f"{prop.path}: {prop.label} — {problem}")
    payload = values.get("payload") if isinstance(values.get("payload"), dict) else {}
    known = {p.path[len(PAYLOAD):] for p in props if p.path.startswith(PAYLOAD)} | _DOC_KEYS
    extra = sorted(str(k)[:40] for k in payload if k not in known)
    if extra:
        problems.append(f"payload: {item_type} 틀에 없는 칸 {extra}")
    low, high, value = (get(values, "payload." + n) for n in ("low", "high", "value"))
    if prop_of(item_type, "payload.unit") and not _empty(value) and _empty(get(values, "payload.unit")):
        problems.append("payload.unit: 값이 있으면 단위가 꼭 있어야 한다")
    if all(_number(x, "number") for x in (low, high)) and low > high:
        problems.append("payload.low: 아래 끝이 위 끝보다 크다")
    if _number(value, "number") and any(_number(x, "number") for x in (low, high)) and not (
            (not _number(low, "number") or low <= value) and (not _number(high, "number") or value <= high)):
        problems.append("payload.value: 값이 아래 끝 ~ 위 끝 밖이다")
    return problems


_UNIT_FROM_PAYLOAD = ("payload.value", "payload.low", "payload.high")


def unit_of(prop: Prop, values: Mapping[str, Any]) -> Optional[str]:
    """그 칸의 단위 — 틀에 적힌 단위, 규격 값 · 끝은 항목의 ``payload.unit``."""
    if prop.unit:
        return prop.unit
    unit = get(values, "payload.unit") if prop.path in _UNIT_FROM_PAYLOAD else None
    return unit if isinstance(unit, str) else None


def value_label(prop: Prop, value: Any, unit: Optional[str] = None) -> str:
    """보이는 글 — 수에는 단위를 붙이고 목록은 ' · '."""
    if _empty(value):
        return ""
    text = " · ".join(str(v) for v in value) if isinstance(value, list) else str(value)
    return f"{text}{unit}" if unit and prop.datatype in ("int", "number") else text


def key_fields(values: Mapping[str, Any], item_type: Optional[str]) -> list[dict[str, Any]]:
    """카드 '눈에 띄는 칸' — 틀의 ``key`` 칸 차례대로(값이 없으면 빈 글 · 글 칸은 카드 본문이 보여 빼고)."""
    return [{"path": p.path, "label": p.label, "value": value_label(p, get(values, p.path), unit_of(p, values)),
             "unit": unit_of(p, values)} for p in TYPE_SCHEMAS.get(item_type or "", ()) if p.key and p.path != "text"]


def diff_rows(item_type: Optional[str], fields: Mapping[str, Any]) -> list[dict[str, Any]]:
    """제안 ``fields`` 의 실음 칸을 틀 칸마다 펼친 전 → 후 줄(틀 밖 실음 칸은 한 줄로). 줄 칸은 이름 · 단위만 붙인다."""
    rows = []
    for name, entry in fields.items():
        entry = entry or {}
        if name != "payload" or not payload_props(item_type):
            prop = prop_of(item_type, name)
            rows.append({"field": name, "before": entry.get("before"), "after": entry.get("after"),
                         **({"proposed": entry["proposed"]} if "proposed" in entry else {}),
                         "label": prop.label if prop else None, "unit": prop.unit if prop else None})
            continue
        before = entry.get("before") if isinstance(entry.get("before"), dict) else {}
        after = entry.get("after") if isinstance(entry.get("after"), dict) else {}
        for prop in payload_props(item_type):
            sub = prop.path[len(PAYLOAD):]
            if before.get(sub) != after.get(sub):
                unit = unit_of(prop, {"payload": after}) or unit_of(prop, {"payload": before})
                rows.append({"field": prop.path, "before": before.get(sub), "after": after.get(sub),
                             "label": prop.label, "unit": unit})
        known = {p.path[len(PAYLOAD):] for p in payload_props(item_type)}
        if any(before.get(k) != after.get(k) for k in set(before) | set(after) if k not in known):
            rows.append({"field": "payload", "before": {k: v for k, v in before.items() if k not in known},
                         "after": {k: v for k, v in after.items() if k not in known}, "label": "실음 칸(그 밖)",
                         "unit": None})
    return rows


def spec_table() -> dict[str, list[dict[str, Any]]]:
    """화면 · 도구 목록용 틀 표(JSON)."""
    return {t: [{"path": p.path, "label": p.label, "datatype": p.datatype, "required": p.required or p.when_active,
                 "choices": list(p.choices), "low": p.low, "high": p.high, "unit": p.unit, "key": p.key}
                for p in props] for t, props in TYPE_SCHEMAS.items()}

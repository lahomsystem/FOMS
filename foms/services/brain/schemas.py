"""유형별 속성 틀(설계서 7.7 · 사장님 D104 — SHACL 꼴) — 유형마다 칸 · 자료형 · 꼭 있어야 함 · 고른 값 · 범위 · 단위.

- 칸 자리는 줄 칸(``text`` · ``checked_at`` · ``valid_from`` · ``evidence_ref`` …) 또는 ``payload.<칸>``(실음 칸 안).
- **틀이 있는 유형의 실음 칸은 닫혀 있다** — 틀에 없는 칸(지식 문서 칸 빼고)은 막는다(SHACL ``sh:closed``).
- 지식 문서 유형(정책 · 가격 규칙 · 사장님 결정 · 사실 · 제작 조건)의 틀 실음 칸은 **brain 만의 칸**이다(7.8 다음 1 · 2 —
  :func:`brain_payload_keys`). 지식 문서 칸(:data:`.doc_bridge.DOC_PAYLOAD_KEYS`)과 같이 실음 칸에 살고, 옮기기를 다시 돌려도
  지워지지 않으며(:mod:`.doc_import`), 다시 만든 지식 문서로는 나가지 않는다(:func:`.doc_bridge.doc_item_of`).
- 검사는 :func:`schema_problems` 하나 — 제안 때와 반영 때 모두 :func:`.gates.object_problems` 가 부른다(문제 글은 칸 자리 ·
  규칙뿐, 값은 싣지 않는다).
- 카드 '눈에 띄는 칸'(:func:`key_fields`)과 제안함 칸별 전 → 후(:func:`diff_rows` — 실음 칸을 틀 칸마다 펼침)가 이 틀을 쓴다.
- **틀이 없는 유형은 :data:`UNSCHEMA_TYPES` 에 적어 둔다**(오늘 꼴 그대로 — 시험이 둘의 합이 모든 유형인지 본다).
- 반영 상태면 꼭 있어야 하는 칸 가운데 ``import_ok`` 칸은 지식 문서에서 옮긴 항목(근거 종류 ``import``)이면 비어도 된다 —
  카드가 '비었음'으로 알리고(:func:`empty_notices`), 채우는 일은 제안으로 한다(옮긴 결정에 번호 달기 — 7.8 자료).
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from foms.services.brain.constants import EVIDENCE_IMPORT, PRICE_BASES, STATUS_ACTIVE
from foms.services.brain.doc_bridge import DOC_PAYLOAD_KEYS
from foms.services.orders.erp_policy_constants import STAGE_LABELS

PAYLOAD = "payload."
DATATYPES: tuple[str, ...] = ("text", "int", "number", "date", "datetime", "enum", "list")


@dataclass(frozen=True)
class Prop:
    """속성 하나 — 자리 · 이름 · 자료형 · 꼭 있어야 함(반영 상태일 때만이면 ``when_active``) · 고른 값 · 범위 · 단위 · 글 꼴.

    ``import_ok`` 면 반영 상태여도 지식 문서에서 옮긴 항목은 비어도 된다(카드 '비었음')."""

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
    pattern: Optional[str] = None
    import_ok: bool = False


def _desc(label: str = "설명", *, required: bool = True) -> Prop:
    """글 칸(설명 · 뜻)."""
    return Prop("text", label, "text", required=required, max_len=2000, key=True)


_CHECKED = Prop("checked_at", "마지막 확인", "date", key=True)
_LEAD = Prop("payload.lead_days", "제작 기간", "int", low=1, high=180, unit="일", key=True)
#: SKOS 꼴 이름표(7.7 · D105 · 점검 '지금 4') — 대표 이름(비우면 ``name``) · 다른 이름 · 숨은 이름(잘못 쓴 말 · 줄임 —
#: 찾기만 보고 화면에 안 보임) · 위 낱말. 실음 칸이라 :mod:`.labels` 가 찾기 · 벡터 글에 쓴다.
_PREF = Prop("payload.pref_label", "대표 이름", "text", max_len=60, key=True)
_ALIASES = Prop("payload.aliases", "다른 이름", "list", max_items=20, max_len=60, key=True)
_HIDDEN = Prop("payload.hidden_labels", "숨은 이름", "list", max_items=20, max_len=60)
_BROADER = Prop("payload.broader", "위 낱말", "text", max_len=60)
_LABELS = (_PREF, _ALIASES, _HIDDEN, _BROADER)
#: 관찰이 일어난 때(7.8 다음 13) — 줄 쓴 때(``recorded_at``)와 따로, 원본(상담 · 그림 · 사진) 시각.
_OCCURRED = Prop("payload.occurred_at", "일어난 때", "datetime", max_len=40, key=True)
_MM = 100_000
_WON = 100_000_000

#: 고른 값 목록(설계서 7.8 다음 1 · 3 · 7 · D124). 상담 쪽 정본과 같은 값은 시험이 맞춘다 — 견적 규칙 종류
#: (:data:`foms.services.cs_agent.quote_rules.RULES`) · 몰딩 · 손잡이(그림 읽기 · 견적 뽑기 값에서 '모름' 뺌).
UNITS: tuple[str, ...] = ("mm", "cm", "m", "개", "kg", "%", "일", "통", "자")
DOOR_KINDS: tuple[str, ...] = ("hinged", "sliding", "folding", "none")
QUOTE_KINDS: tuple[str, ...] = ("hinge", "slide", "linear", "none")
PRICE_UNITS: tuple[str, ...] = ("30cm", "1m", "자", "통")
PRICE_RULE_UNITS: tuple[str, ...] = ("30cm", "1m", "자", "통", "개", "회", "%")
MOLDINGS: tuple[str, ...] = ("molding", "no_molding")
HANDLES: tuple[str, ...] = ("push", "bar", "other")
SPEC_BASES: tuple[str, ...] = ("inner", "wall_incl", "outer")
PRICE_STAGES: tuple[str, ...] = ("base", "extra", "discount")
POLICY_KINDS: tuple[str, ...] = ("general", "promotion", "install", "shipping")
#: 공정 단계 → ERP 주문 단계 정본 값(:data:`foms.services.orders.erp_policy_constants.STAGE_LABELS` 의 키).
ERP_STAGES: tuple[str, ...] = tuple(STAGE_LABELS)

#: 유형 → 속성 틀(차례 = 카드 · 제안함 차례).
TYPE_SCHEMAS: dict[str, tuple[Prop, ...]] = {
    "product_line": (_desc(), Prop("payload.door_kinds", "문 방식", "list", choices=DOOR_KINDS, max_items=4, key=True),
                     _LEAD,
                     Prop("payload.quote_kind", "견적 규칙 종류", "enum", choices=QUOTE_KINDS, key=True),
                     Prop("payload.price_unit", "값 단위", "enum", choices=PRICE_UNITS, key=True),
                     Prop("payload.molding_default", "기본 몰딩", "enum", choices=MOLDINGS, key=True),
                     Prop("payload.handle_default", "기본 손잡이", "enum", choices=HANDLES, key=True),
                     Prop("payload.min_width_mm", "최소 가로", "int", low=0, high=_MM, unit="mm", key=True),
                     Prop("payload.max_width_mm", "최대 가로", "int", low=0, high=_MM, unit="mm", key=True),
                     *_LABELS),
    "option": (_desc(), Prop("payload.price_kind", "값 방식", "enum", choices=("included", "extra", "quote"), key=True),
               _LEAD, Prop("payload.unit", "단위", "enum", choices=UNITS, key=True),
               Prop("payload.category", "옵션 묶음", "text", max_len=60, key=True),
               Prop("payload.door_kinds", "맞는 문 방식", "list", choices=DOOR_KINDS, max_items=4), *_LABELS),
    "spec": (_desc(), Prop("payload.value", "값", "number", low=0, high=_MM, key=True),
             Prop("payload.unit", "단위", "enum", choices=UNITS, key=True),
             Prop("payload.low", "아래 끝", "number", low=0, high=_MM),
             Prop("payload.high", "위 끝", "number", low=0, high=_MM),
             Prop("payload.basis", "치수 기준", "enum", choices=SPEC_BASES, key=True)),
    "build_rule": (_desc("조건"), Prop("payload.rule_kind", "조건 꼴", "enum", choices=("requires", "excludes", "limit"),
                                       key=True), _CHECKED),
    "policy": (_desc("정책 글"), _CHECKED, Prop("valid_from", "유효 시작", "date", key=True),
               Prop("valid_to", "유효 끝", "date", key=True),
               Prop("payload.policy_kind", "정책 종류", "enum", choices=POLICY_KINDS, key=True), *_LABELS),
    "price_rule": (_desc("규칙 글"), Prop("checked_at", "마지막 확인", "date", when_active=True, key=True),
                   Prop("evidence_ref", "근거 위치", "text", max_len=200, key=True),
                   Prop("payload.basis", "근거 종류", "enum", choices=PRICE_BASES, key=True),
                   Prop("payload.stage", "값 단계", "enum", choices=PRICE_STAGES, key=True),
                   Prop("payload.unit", "값 단위", "enum", choices=PRICE_RULE_UNITS, key=True),
                   Prop("payload.band_low", "값 아래 끝", "number", low=0, high=_WON, unit="원"),
                   Prop("payload.band_high", "값 위 끝", "number", low=0, high=_WON, unit="원"),
                   Prop("payload.from_price", "'부터' 값", "number", low=0, high=_WON, unit="원"),
                   Prop("payload.formula", "셈 꼴", "text", max_len=200)),
    "owner_decision": (_desc("결정 글"), Prop("evidence_ref", "결정 근거(원장 번호)", "text", max_len=200, key=True),
                       Prop("valid_from", "유효 시작", "date", key=True),
                       Prop("payload.decision_no", "결정 번호", "text", when_active=True, import_ok=True,
                            pattern=r"D\d{1,5}", max_len=6, key=True),
                       Prop("payload.decided_on", "결정 날", "date", key=True)),
    "term": (_desc("뜻", required=False), *_LABELS),
    "fact": (_desc("사실 글"), _CHECKED),
    "process_step": (_desc(required=False),
                     Prop("payload.erp_stage", "ERP 단계", "enum", required=True, choices=ERP_STAGES, key=True),
                     Prop("payload.step_order", "단계 차례", "int", low=1, high=99, key=True), *_LABELS),
    "case": (_desc("사례 글", required=False), _OCCURRED),
    "image_read": (_desc("그림 읽기 글", required=False), _OCCURRED),
    "photo_observation": (_desc("사진 관찰 글", required=False), _OCCURRED),
}
#: 틀이 아직 없는 유형(오늘 꼴 — 꼴 검사만). 틀을 더하면 여기서 뺀다.
UNSCHEMA_TYPES: tuple[str, ...] = (
    "brand", "situation", "template", "lesson", "tone", "image_read_rule", "part_kind", "bom_rule", "drawing_rule",
    "conflict", "question",
)
#: 틀이 있어도 실음 칸에 둘 수 있는 지식 문서 칸(지식 문서 유형 — 옮기기 · 다시 만들기 꼴).
_DOC_KEYS = DOC_PAYLOAD_KEYS
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
#: 아래 끝 ≤ 위 끝 짝(같은 항목 안).
_RANGES = (("payload.low", "payload.high"), ("payload.band_low", "payload.band_high"),
           ("payload.min_width_mm", "payload.max_width_mm"))


def _is_day(value: Any) -> bool:
    """``YYYY-MM-DD`` 날짜 글인가."""
    if not isinstance(value, str) or not _DAY.fullmatch(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_moment(value: Any) -> bool:
    """ISO 시각 글인가(``YYYY-MM-DDTHH:MM`` 이상 — 시간대 표시는 있어도 없어도)."""
    if not isinstance(value, str) or len(value) < 16 or len(value) > 40 or not _DAY.match(value):
        return False
    try:
        datetime.datetime.fromisoformat(value)
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


def brain_payload_keys(item_type: Optional[str]) -> frozenset[str]:
    """그 유형 틀의 실음 칸 이름 — 지식 문서 유형에서는 **brain 만의 칸**(문서로 나가지 않고, 옮기기를 다시 돌려도 남는다)."""
    return frozenset(p.path[len(PAYLOAD):] for p in payload_props(item_type)) - _DOC_KEYS


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
    elif kind == "datetime" and not _is_moment(value):
        return "시각(YYYY-MM-DDTHH:MM — ISO)이어야 한다"
    elif kind == "enum" and value not in prop.choices:
        return f"{' / '.join(prop.choices)} 가운데 하나여야 한다"
    elif kind == "text" and (not isinstance(value, str) or (prop.max_len and len(value) > prop.max_len)):
        return f"{prop.max_len or ''}자 이하 글이어야 한다"
    elif kind == "text" and prop.pattern and not re.fullmatch(prop.pattern, value):
        return f"꼴({prop.pattern})이 맞지 않는다"
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


def _must_fill(prop: Prop, values: Mapping[str, Any]) -> bool:
    """이 칸이 지금 꼭 있어야 하나 — 늘 · 반영 상태일 때(옮긴 항목은 ``import_ok`` 칸을 비울 수 있다)."""
    if prop.required:
        return True
    if not prop.when_active or values.get("status") != STATUS_ACTIVE:
        return False
    return not (prop.import_ok and values.get("evidence_kind") == EVIDENCE_IMPORT)


def schema_problems(values: Mapping[str, Any], item_type: Optional[str]) -> list[str]:
    """그 유형 틀에 맞지 않는 칸 — 꼭 있어야 함 · 자료형 · 고른 값 · 범위 · 닫힌 실음 칸 · 아래 끝 ≤ 값 ≤ 위 끝."""
    props = TYPE_SCHEMAS.get(item_type or "")
    if not props:
        return []
    problems = []
    for prop in props:
        value = get(values, prop.path)
        if _empty(value):
            if _must_fill(prop, values):
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
    if prop_of(item_type, "payload.unit") and prop_of(item_type, "payload.value") and not _empty(value) and _empty(
            get(values, "payload.unit")):
        problems.append("payload.unit: 값이 있으면 단위가 꼭 있어야 한다")
    for low_path, high_path in _RANGES:
        bottom, top = get(values, low_path), get(values, high_path)
        if all(_number(x, "number") for x in (bottom, top)) and bottom > top:
            problems.append(f"{low_path}: 아래 끝이 위 끝보다 크다")
    if _number(value, "number") and any(_number(x, "number") for x in (low, high)) and not (
            (not _number(low, "number") or low <= value) and (not _number(high, "number") or value <= high)):
        problems.append("payload.value: 값이 아래 끝 ~ 위 끝 밖이다")
    if item_type == "policy" and get(values, "payload.policy_kind") == "promotion" and _empty(values.get("valid_to")):
        problems.append("valid_to: 판촉 정책은 유효 끝이 꼭 있어야 한다(D124)")
    return problems


def empty_notices(values: Mapping[str, Any], item_type: Optional[str]) -> list[dict[str, str]]:
    """카드 알림 — 반영 상태인데 비어 둔(옮긴 항목이라 받아 준) 칸 · 근거 종류가 빈 가격 규칙(최소를 따지지 않음 — D115)."""
    out = []
    for prop in TYPE_SCHEMAS.get(item_type or "", ()):
        if prop.import_ok and values.get("status") == STATUS_ACTIVE and _empty(get(values, prop.path)):
            out.append({"code": "empty:" + prop.path, "text": f"{prop.label} 비었음"})
    if item_type == "price_rule" and get(values, "payload.basis") not in PRICE_BASES:
        out.append({"code": "empty:payload.basis", "text": "근거 종류 비었음 — 연결 개수 최소를 따지지 않아요"})
    return out


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

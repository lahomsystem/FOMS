"""문장으로 고치기 — 세부 칸(실음 칸) 고치기 · 새 항목의 세부 칸(설계서 2026-11-18-brain-sentence-change 12절 '세부 칸은 다음 판').

- **받는 칸은 한 곳**(:data:`PROP_FIELDS`): 계획 길이 연 칸(:data:`.plan_rules.PROP_EDITS` — 제품 라인의 문 방식 · 견적 규칙 종류 ·
  최소 · 최대 가로, 정책의 정책 갈래)에 제작 조건의 조건 꼴(``rule_kind``)을 더한 것뿐이다. 그 밖의 칸 · 금액 칸은 받지 않는다
  (``prop_field`` — '못 고친 것'). 새 항목은 정책 · 제작 조건만 세부 칸을 받는다(:data:`CREATE_PROP_TYPES`).
- **값 꼴은 유형 틀이 본다**(:func:`.schemas.schema_problems` — 고른 값 · 범위 · 목록). 밖이면 ``prop_value``.
- AI 는 값을 글 하나로 낸다(틀을 작게 — 칸 이름 → 값 목록 한 꼴): 고르기 값은 저장 값(영어), 목록 칸은 쉼표로 이은 온 목록,
  수는 숫자만. 여기서 틀의 자료형으로 바꾼다(:func:`parse_value`). 목록은 고른 값 차례로 맞추고, 같은 값 모음이면 고침이 아니다.
- **다른 실음 칸은 지우지 않는다** — 고침 값은 지금 실음 칸에 얹는다(:func:`merged` — :func:`.plan_rules.file_props` 꼴). 반영 ·
  되돌리기는 지금 고침 길(``propose_update`` → 반영 · ``propose_rollback``)이 실음 칸 통째로 한다.
- 화면 값(:func:`prop_fields`)은 화면 말 — 칸 이름은 틀 이름표('문 방식'), 값은 고르기 이름표('여닫이' · 목록은 ' · ' 로 이음),
  수에는 단위(:func:`.schemas.shown_label`).
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional

from foms.services.brain.plan_rules import PROP_EDITS
from foms.services.brain.schemas import CHOICE_LABELS, PAYLOAD, Prop, prop_of, schema_problems, shown_label, unit_of

#: 고칠 수 있는 세부 칸(유형 → 칸 이름들).
PROP_FIELDS: dict[str, tuple[str, ...]] = {**PROP_EDITS, "build_rule": ("rule_kind",)}
#: 새로 만들 때 세부 칸을 받는 유형(정책 갈래 · 조건 꼴).
CREATE_PROP_TYPES: tuple[str, ...] = ("policy", "build_rule")
#: AI 틀의 칸 이름 고른 값(모든 유형의 받는 칸 — 유형마다 받는지는 :func:`read_props` 가 본다).
PROP_NAMES: tuple[str, ...] = tuple(dict.fromkeys(n for names in PROP_FIELDS.values() for n in names))
#: 한 줄의 세부 칸 수 · 값 글자 상한.
MAX_PROPS, MAX_VALUE = 8, 200
PROP_FIELD, PROP_VALUE = "prop_field", "prop_value"
_SPLIT = re.compile(r"[,·、/]")
_INT = re.compile(r"-?\d{1,9}")


def allowed(item_type: Optional[str], *, create: bool = False) -> tuple[str, ...]:
    """그 유형이 받는 세부 칸(새로 만들 때는 정책 · 제작 조건만)."""
    if create and item_type not in CREATE_PROP_TYPES:
        return ()
    return PROP_FIELDS.get(item_type or "", ())


def _prop(item_type: Optional[str], name: str) -> Optional[Prop]:
    """틀의 칸 하나(``payload.<이름>``)."""
    return prop_of(item_type, PAYLOAD + name)


def _choices(prop: Prop) -> dict[str, str]:
    """고른 값 → 이름표(AI 재료 — 저장 값과 화면 말을 같이 준다)."""
    labels = CHOICE_LABELS.get(prop.path, {})
    return {c: labels.get(c, c) for c in prop.choices}


def _material_row(prop: Prop, name: str) -> dict[str, Any]:
    """재료 세부 칸 한 줄(지금 값은 부르는 쪽이 더한다)."""
    row: dict[str, Any] = {"name": name, "label": prop.label}
    if prop.choices:
        row["choices"] = _choices(prop)
    if prop.datatype == "list":
        row["list"] = True
    if prop.datatype in ("int", "number"):
        row.update(unit=prop.unit, low=prop.low, high=prop.high)
    return row


def material_props(item_type: Optional[str], payload: Any) -> dict[str, Any]:
    """재료 항목의 고칠 수 있는 세부 칸 → 지금 값(칸 뜻 · 고를 수 있는 값은 유형마다 한 번 — :func:`prop_cells`)."""
    payload = payload if isinstance(payload, Mapping) else {}
    return {name: payload.get(name) for name in allowed(item_type) if _prop(item_type, name) is not None}


def prop_cells() -> dict[str, list[dict[str, Any]]]:
    """유형마다 고칠 수 있는 세부 칸 — 이름 · 이름표 · 고를 수 있는 값(저장 값 → 이름표) · 목록 여부 · 단위 · 범위.

    항목마다 싣지 않고 유형마다 한 번(제품 라인이 많으면 재료 상한을 칸 뜻이 다 먹는다 — 한 줄 약 650자)."""
    return {t: [_material_row(p, n) for n in names if (p := _prop(t, n)) is not None] for t, names in PROP_FIELDS.items()}


def parse_value(prop: Prop, raw: str) -> Any:
    """AI 글 값 → 틀 자료형(고르기 · 목록 · 정수). 꼴이 아니면 :class:`ValueError`."""
    text = raw.strip()
    if prop.datatype == "list":
        items = list(dict.fromkeys(x.strip() for x in _SPLIT.split(text) if x.strip()))
        order = {c: n for n, c in enumerate(prop.choices)}
        return sorted(items, key=lambda x: order.get(x, len(order))) if prop.choices else items
    if prop.datatype == "int":
        digits = text.replace(",", "").replace(" ", "")
        if prop.unit and digits.endswith(prop.unit):
            digits = digits[:-len(prop.unit)]
        if not _INT.fullmatch(digits):
            raise ValueError("int")
        return int(digits)
    return text


def _same(prop: Prop, old: Any, new: Any) -> bool:
    """같은 값인가(목록은 모음으로 견준다)."""
    if prop.datatype == "list" and isinstance(old, list) and isinstance(new, list):
        return set(old) == set(new) and len(old) == len(new)
    return old == new


def read_props(item_type: Optional[str], payload: Any, wanted: Any, *, create: bool = False
               ) -> tuple[dict[str, Any], list[tuple[str, str]], Optional[str]]:
    """AI 가 낸 세부 칸(``{이름: 글 값}``) → (바뀐 칸 ``{이름: 값}``, 못 받은 칸 ``[(이름, 글 값)]``, 까닭 코드).

    같은 값은 바뀐 칸에서 뺀다. 받지 않는 칸이면 ``prop_field``, 꼴 · 고른 값 밖이면 ``prop_value``(먼저 걸린 것)."""
    payload = payload if isinstance(payload, Mapping) else {}
    names = allowed(item_type, create=create)
    changed: dict[str, Any] = {}
    refused: list[tuple[str, str]] = []
    code: Optional[str] = None
    for name, raw in (wanted or {}).items():
        prop = _prop(item_type, name) if name in names else None
        if prop is None:
            refused.append((name, raw))
            code = code or PROP_FIELD
            continue
        try:
            value = parse_value(prop, raw)
        except ValueError:
            value = None
        problems = [] if value is None else [
            p for p in schema_problems({"payload": {name: value}}, item_type) if p.startswith(prop.path + ":")]
        if value is None or value == [] or problems:
            refused.append((name, raw))
            code = code or PROP_VALUE
        elif not _same(prop, payload.get(name), value):
            changed[name] = value
    return changed, refused, code


def merged(payload: Any, changed: Mapping[str, Any]) -> dict[str, Any]:
    """지금 실음 칸에 바뀐 칸만 얹는다(다른 칸은 그대로)."""
    return {**(dict(payload) if isinstance(payload, Mapping) else {}), **changed}


def shown(item_type: Optional[str], name: str, value: Any, payload: Any = None) -> Optional[str]:
    """세부 칸 값 → 화면 말(빈 값은 ``None``)."""
    prop = _prop(item_type, name)
    if prop is None:
        return None if value in (None, "", []) else str(value)
    text = shown_label(prop, value, unit_of(prop, {"payload": payload or {}}))
    return text or None


def prop_label(item_type: Optional[str], name: str) -> str:
    """세부 칸 이름 → 화면 이름(틀에 없으면 '세부 칸')."""
    prop = _prop(item_type, name)
    return prop.label if prop is not None else "세부 칸"


def prop_fields(item_type: Optional[str], payload: Any, changed: Mapping[str, Any],
                refused: list[tuple[str, str]] = ()) -> list[dict[str, Any]]:
    """화면 줄의 세부 칸 전 → 후(화면 말). 못 받은 칸은 AI 가 낸 글 그대로 뒤에 붙인다."""
    payload = payload if isinstance(payload, Mapping) else {}
    rows = [{"name": PAYLOAD + n, "label": prop_label(item_type, n), "before": shown(item_type, n, payload.get(n)),
             "after": shown(item_type, n, v)} for n, v in changed.items()]
    rows += [{"name": PAYLOAD + n, "label": prop_label(item_type, n), "before": shown(item_type, n, payload.get(n)),
              "after": raw} for n, raw in refused]
    return rows

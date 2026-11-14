"""온톨로지 탭 자료 — Palantir Ontology Manager 꼴(설계서 2026-11-12 온톨로지 7절 · 사장님 D187 · D188). **읽기만**.

- 왼쪽 목록(:func:`ontology_summary`): 물건 종류(묶음 · 수 · 표준 이름) · 연결 종류(허용 짝 · 수 · 표준 이름) · 동작 종류 ·
  능력 질문(:mod:`.ontology_cqs`)마다 '답 재료가 있나'와 점수.
- 오른쪽 상세(:func:`ontology_type`): 고른 종류의 속성 틀(:data:`.schemas.TYPE_SCHEMAS` — 자료형 · 꼭 · 단위 · 고른 값 · 범위 ·
  표준 이름 · **채움**(지금 볼 수 있는 항목 가운데 값이 있는 수)) · 나가는 · 들어오는 연결(개수 규칙 · 지금 수) · 정본 바깥 자리 ·
  예시 항목.
- 종류 · 칸 · 연결은 코드 + 설계서가 정본이다(화면에서 고치지 않는다 — master brain 7.7). 수는 모두 보는 사람의 보기 범위 · 유효
  기간 안(:func:`.read.visible_clauses`)만 센다. '답 재료가 있나'는 필요한 종류 · 연결이 하나라도 있나이고, 내용이 맞는지는 평가
  단계(설계서 8절)가 잰다.
- **ERP 물건 칸**(접목판 ``erp_read`` 스위치가 켜진 사람만 — 설계서 2026-11-14-foms-graft 3.8): 왼쪽 목록에 ``erp`` 칸(물건 종류 열 ·
  할 일 종류 · ERP 재료가 드는 질문 수)이 붙고, 능력 질문의 ERP 재료는 읽기 도구가 있는 종류면 '있음'으로 센다(켜기 전 점수
  ``covered_before`` 를 같이 싣는다). 오른쪽 상세는 :func:`ontology_erp_type`. 꺼진 사람의 답은 지금과 글자까지 같다.
  ERP 물건 · 할 일은 코드 목록(:mod:`foms.services.erp_ontology.objects` · :mod:`foms.services.erp_actions.registry`)이 정본 — DB 를
  읽지 않는다.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy import func, select

from foms.persistence.brain.models import BrainLink, BrainObject
from foms.services.brain.actions import ACTIONS, AGENT_ACTION_TYPES
from foms.services.brain.browse import compress_types
from foms.services.brain.constants import (
    ALLOWED_LINKS, EXTERNAL_TYPES, LINK_KINDS, TYPE_LAYERS, TYPES, cardinality, link_allowed,
)
from foms.services.brain.display import LAYER_LABELS, LINK_DISPLAY, TYPE_DISPLAY, TYPE_GROUPS
from foms.services.brain.ontology_cqs import CQS, ERP_NEED_TYPES, ERP_NEEDS
from foms.services.brain.read import visible_clauses
from foms.services.brain.schemas import CHOICE_LABELS, TYPE_SCHEMAS
from foms.services.brain.scope import Viewer
from foms.services.brain.store import is_current
from foms.services.erp_actions.registry import ACTIONS as ERP_ACTIONS
from foms.services.erp_actions.registry import MODE_HUMAN, MODE_LINK, ActionSpec, level_label
from foms.services.erp_ontology.objects import OBJECT_TYPES, ORDER_PROPS, get_type, masked_props

__all__ = [
    "ERP_LINKS", "LINK_STANDARDS", "PROP_STANDARDS", "TYPE_STANDARDS", "erp_ready_needs", "ontology_erp_type",
    "ontology_summary", "ontology_type",
]

#: 물건 종류 → 표준 어휘의 짝(schema.org · SKOS · PROV-O · ODRL · SOSA · SHACL). ``foms:`` 는 우리 어휘.
TYPE_STANDARDS: dict[str, str] = {
    "brand": "schema:Brand", "product_line": "schema:ProductGroup", "option": "schema:Product",
    "spec": "schema:PropertyValue", "build_rule": "sh:NodeShape", "policy": "odrl:Policy",
    "price_rule": "schema:PriceSpecification", "owner_decision": "prov:Activity", "term": "skos:Concept",
    "fact": "schema:Claim", "process_step": "schema:HowToStep", "situation": "schema:Question",
    "template": "schema:Answer", "lesson": "prov:Entity", "tone": "schema:CreativeWork", "image_read_rule": "sh:NodeShape",
    "part_kind": "skos:Concept", "bom_rule": "sh:NodeShape", "drawing_rule": "sh:NodeShape", "case": "sosa:Observation",
    "image_read": "sosa:Observation", "photo_observation": "sosa:Observation", "conflict": "prov:Entity",
    "question": "schema:Question",
}
#: 연결 종류 → 표준 속성(역방향이면 ``^``).
LINK_STANDARDS: dict[str, str] = {
    "applies_to": "odrl:target", "requires": "foms:requires", "excludes": "foms:excludes",
    "value_from": "prov:wasQuotedFrom", "copy_in": "prov:alternateOf", "supersedes": "dcterms:replaces",
    "evidence_of": "^prov:wasDerivedFrom", "caused_by": "foms:causedBy", "fixed_by": "foms:fixedBy",
    "about": "dcterms:subject", "decided_by": "prov:wasGeneratedBy", "at_step": "^schema:step", "uses": "prov:used",
    "answers": "^schema:acceptedAnswer", "refines": "prov:wasRevisionOf", "broader": "skos:broader",
    "part_of": "schema:isPartOf",
}
#: 속성 자리 → 표준 속성(없으면 ``foms:<칸>``).
PROP_STANDARDS: dict[str, str] = {
    "text": "skos:definition", "checked_at": "dcterms:modified", "valid_from": "schema:validFrom",
    "valid_to": "schema:validThrough", "evidence_ref": "prov:wasDerivedFrom", "payload.pref_label": "skos:prefLabel",
    "payload.aliases": "skos:altLabel", "payload.hidden_labels": "skos:hiddenLabel", "payload.broader": "skos:broader",
    "payload.unit": "qudt:unit", "payload.value": "schema:value", "payload.low": "schema:minValue",
    "payload.high": "schema:maxValue", "payload.regions": "schema:areaServed", "payload.weekdays": "schema:dayOfWeek",
    "payload.time_windows": "schema:hoursAvailable", "payload.decision_no": "dcterms:identifier",
    "payload.decided_on": "dcterms:date", "payload.occurred_at": "sosa:resultTime",
    "payload.lead_days": "schema:deliveryLeadTime", "payload.category": "schema:category",
}
_EXAMPLES = 8
_SCAN_CAP = 5000  # 채움을 셀 때 읽는 항목 상한(회사 지식은 수천 개 아래 — 넘으면 표본)
#: ERP 물건 사이 연결(시작 · 연결 말 · 끝) — 지금 표 · 칸이 잇는 것만(설계서 3.2 표). 새 표 · 새 칸 없음.
ERP_LINKS: tuple[tuple[str, str, str], ...] = (
    ("erp:order", "품목", "erp:order_item"), ("erp:order", "손님", "erp:customer"), ("erp:order", "현장", "erp:site"),
    ("erp:order", "방문", "erp:visit"), ("erp:order", "도면", "erp:drawing"), ("erp:order", "생산", "erp:production_run"),
    ("erp:order", "출고", "erp:shipment"), ("erp:order", "협력사 발주", "erp:partner_order"),
    ("erp:order", "AS", "erp:as_case"), ("erp:as_case", "AS 방문", "erp:visit"),
)


def _type_row(item_type: str, counts: dict[str, int]) -> dict[str, Any]:
    label, color, icon = TYPE_DISPLAY.get(item_type, (item_type, "", "fa-circle"))
    return {"type": item_type, "label": label, "icon": icon, "count": int(counts.get(item_type, 0)),
            "standard": TYPE_STANDARDS.get(item_type, f"foms:{item_type}"),
            "layers": [LAYER_LABELS.get(layer, layer) for layer in sorted(TYPE_LAYERS.get(item_type, ()))]}


def _counts(session: Any, viewer: Viewer, today: datetime.date) -> dict[str, int]:
    query = select(BrainObject.item_type, func.count()).where(*visible_clauses(viewer, today)).group_by(BrainObject.item_type)
    return {item_type: int(n) for item_type, n in session.execute(query)}


def _link_counts(session: Any, viewer: Viewer, today: datetime.date) -> dict[tuple[str, str], int]:
    """(시작 유형, 링크 종류) → 지금 링크 수 — 시작 항목을 볼 수 있는 것만."""
    query = (select(BrainObject.item_type, BrainLink.kind, func.count())
             .join(BrainObject, BrainObject.item_key == BrainLink.from_key)
             .where(is_current(BrainLink), *visible_clauses(viewer, today))
             .group_by(BrainObject.item_type, BrainLink.kind))
    return {(item_type, kind): int(n) for item_type, kind, n in session.execute(query)}


def _actions() -> list[dict[str, Any]]:
    rows = [{"name": a.name, "label": a.label, "summary": a.summary, "stage": a.stage, "agent": False}
            for a in ACTIONS.values() if a.ui]
    rows += [{"name": a.name, "label": a.label, "summary": a.summary, "stage": a.stage, "agent": True}
             for a in AGENT_ACTION_TYPES.values()]
    return rows


def erp_ready_needs() -> frozenset[str]:
    """읽기 도구가 있는 ERP 재료(능력 질문의 ``erp:order`` · ``erp:schedule`` 가운데) — 코드 목록만 본다."""
    return frozenset(need for need, code in ERP_NEED_TYPES.items()
                     if (obj := get_type(code)) is not None and obj.readable)


def _coverage(counts: dict[str, int], link_totals: dict[str, int],
              erp_have: frozenset[str] = frozenset()) -> dict[str, Any]:
    """능력 질문마다 필요한 종류 · 연결이 하나라도 있나. ERP 재료는 ``erp_have`` 에 든 것만 '있음'(처음 값 — 없음)."""
    rows = []
    for cq in CQS:
        needs = [{"type": n, "label": ERP_NEEDS.get(n) or TYPE_DISPLAY.get(n, (n,))[0], "erp": n in ERP_NEEDS,
                  "have": n in erp_have if n in ERP_NEEDS else counts.get(n, 0) > 0} for n in cq.needs]
        links = [{"kind": k, "label": LINK_DISPLAY.get(k, (k,))[0], "have": link_totals.get(k, 0) > 0} for k in cq.links]
        rows.append({"id": cq.cq_id, "domain": cq.domain, "question": cq.question, "basis": cq.basis,
                     "needs": needs, "links": links, "covered": all(x["have"] for x in (*needs, *links))})
    covered = sum(1 for row in rows if row["covered"])
    return {"rows": rows, "covered": covered, "total": len(rows)}


def _erp_action_row(spec: ActionSpec) -> dict[str, Any]:
    """할 일 종류 한 줄 — 이름 · 감싼 기능 · 대상 · 수준 상한 · 갈래 · 어디서 결정하나."""
    if spec.mode == MODE_HUMAN:
        where = "PC · 사장님"
    elif spec.mode == MODE_LINK:
        where = "주문 화면에서"
    else:
        where = "폰 승인" if spec.phone_ok else "PC 승인"
    target = get_type(spec.target)
    return {"name": spec.name, "label": spec.label, "wraps": spec.wraps, "target": spec.target,
            "target_label": target.label if target is not None else spec.target, "level_label": level_label(spec),
            "mode": spec.mode, "where": where}


def _erp_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """왼쪽 목록 ``erp`` 칸 — 물건 종류 열 · 할 일 종류 · ERP 재료가 드는 능력 질문 수."""
    return {"types": [{"type": o.type, "label": o.label, "sub": o.sub, "icon": o.icon, "readable": o.readable,
                       "masked": o.masked} for o in OBJECT_TYPES],
            "actions": [_erp_action_row(spec) for spec in ERP_ACTIONS.values()],
            "cq_erp": sum(1 for row in rows if any(n["erp"] for n in row["needs"]))}


def ontology_summary(session: Any, viewer: Viewer, *, today: datetime.date, erp: bool = False) -> dict[str, Any]:
    """왼쪽 목록 자료 — 종류 묶음 · 연결 종류 · 동작 · 능력 질문 점수. ``erp`` = 접목판 ERP 읽기가 켜진 사람(ERP 칸 · 재료)."""
    counts = _counts(session, viewer, today)
    per_link = _link_counts(session, viewer, today)
    link_totals: dict[str, int] = {}
    for (_type, kind), n in per_link.items():
        link_totals[kind] = link_totals.get(kind, 0) + n
    groups = [{"key": key, "label": label, "types": [_type_row(t, counts) for t in types if t in TYPES]}
              for key, label, types in TYPE_GROUPS if any(t in TYPES for t in types)]
    links = []
    for kind in LINK_KINDS:
        starts, ends = ALLOWED_LINKS[kind]
        label, color, _out, _in = LINK_DISPLAY.get(kind, (kind, "", "", ""))
        links.append({"kind": kind, "label": label, "standard": LINK_STANDARDS.get(kind, f"foms:{kind}"),
                      "from": compress_types([t for t in (*TYPES, *EXTERNAL_TYPES) if t in starts]),
                      "to": compress_types([t for t in (*TYPES, *EXTERNAL_TYPES) if t in ends]),
                      "count": link_totals.get(kind, 0), "open": bool(starts)})
    out = {"groups": groups, "links": links, "actions": _actions(), "cq": _coverage(counts, link_totals),
           "total": sum(counts.values()), "group_labels": {key: label for key, label, _t in TYPE_GROUPS}}
    if erp:  # 켜기 전 점수를 같이 적는다(시험지를 쉽게 만든 것이 아니라 재료가 생긴 것 — 설계서 3.8)
        cq = _coverage(counts, link_totals, erp_ready_needs())
        cq["covered_before"] = out["cq"]["covered"]
        out.update(cq=cq, erp=_erp_summary(cq["rows"]))
    return out


def _value(row: BrainObject, path: str) -> Any:
    if path.startswith("payload."):
        return (row.payload or {}).get(path[len("payload."):]) if isinstance(row.payload, dict) else None
    return getattr(row, path, None)


def _props(rows: list[BrainObject], item_type: str) -> list[dict[str, Any]]:
    out = []
    for prop in TYPE_SCHEMAS.get(item_type, ()):
        filled = sum(1 for row in rows if _value(row, prop.path) not in (None, "", [], {}))
        labels = CHOICE_LABELS.get(prop.path, {})
        out.append({"path": prop.path, "label": prop.label, "datatype": prop.datatype,
                    "required": "always" if prop.required else "active" if prop.when_active else "",
                    "unit": prop.unit, "low": prop.low, "high": prop.high,
                    "choices": [{"value": c, "label": labels.get(c, c)} for c in prop.choices],
                    "standard": PROP_STANDARDS.get(prop.path, "foms:" + prop.path.rsplit(".", 1)[-1]),
                    "filled": filled, "total": len(rows)})
    return out


def _type_links(item_type: str, per_link: dict[tuple[str, str], int]) -> list[dict[str, Any]]:
    order = (*TYPES, *EXTERNAL_TYPES)
    out = []
    for kind in LINK_KINDS:
        starts, ends = ALLOWED_LINKS[kind]
        label, _color, out_label, in_label = LINK_DISPLAY.get(kind, (kind, "", kind, kind))
        if item_type in starts:
            targets = [t for t in order if t in ends and link_allowed(item_type, kind, t)]
            if targets:
                low, high = cardinality(item_type, kind)
                out.append({"kind": kind, "label": label, "direction": "out", "phrase": out_label,
                            "ends": compress_types(targets), "min": low, "max": high,
                            "count": per_link.get((item_type, kind), 0),
                            "standard": LINK_STANDARDS.get(kind, f"foms:{kind}"),
                            "external": [t for t in targets if t in EXTERNAL_TYPES]})
        if item_type in ends:
            sources = [t for t in order if t in starts and link_allowed(t, kind, item_type)]
            if sources:
                out.append({"kind": kind, "label": label, "direction": "in", "phrase": in_label,
                            "ends": compress_types(sources), "min": 0, "max": None,
                            "count": sum(per_link.get((t, kind), 0) for t in sources),
                            "standard": LINK_STANDARDS.get(kind, f"foms:{kind}"), "external": []})
    return out


def ontology_type(session: Any, viewer: Viewer, item_type: str, *, today: datetime.date) -> Optional[dict[str, Any]]:
    """오른쪽 상세 — 모르는 종류면 ``None``(404)."""
    if item_type not in TYPES:
        return None
    rows = list(session.execute(select(BrainObject).where(BrainObject.item_type == item_type,
                                                          *visible_clauses(viewer, today))
                                .order_by(BrainObject.usage_count.desc(), BrainObject.item_key)
                                .limit(_SCAN_CAP)).scalars())
    per_link = _link_counts(session, viewer, today)
    counts = _counts(session, viewer, today)
    return {**_type_row(item_type, counts),
            "props": _props(rows, item_type), "schema": item_type in TYPE_SCHEMAS,
            "links": _type_links(item_type, per_link),
            "examples": [{"key": r.item_key, "name": r.name, "brand": r.brand, "status": r.status}
                         for r in rows[:_EXAMPLES]],
            "cq": [cq.cq_id for cq in CQS if item_type in cq.needs]}


def _erp_props() -> list[dict[str, Any]]:
    """주문 속성 ↔ 지금 칸(설계서 3.2 '실제 정본') — 쓰기를 맡는 할 일은 화면 이름으로."""
    out = []
    for prop in ORDER_PROPS:
        via = [ERP_ACTIONS[name].label for name in prop.via if name in ERP_ACTIONS]
        out.append({"key": prop.key, "name": prop.name, "column": prop.column, "shape": prop.shape,
                    "access": prop.access, "access_label": prop.access_label, "via": " · ".join(via),
                    "note": prop.note})
    return out


def _erp_links(code: str) -> list[dict[str, Any]]:
    """그 물건 종류의 나가는 · 들어오는 연결(:data:`ERP_LINKS`)."""
    rows = []
    for start, label, end in ERP_LINKS:
        if code in (start, end):
            other = end if start == code else start
            obj = get_type(other)
            rows.append({"rel": label, "direction": "out" if start == code else "in", "type": other,
                         "label": obj.label if obj is not None else other})
    return rows


def ontology_erp_type(code: Any) -> Optional[dict[str, Any]]:
    """ERP 물건 종류 상세(``GET /api/brain/ontology/erp/<종류>``) — 모르는 종류는 ``None``(404). DB 를 읽지 않는다."""
    obj = get_type(code)
    if obj is None:
        return None
    needs = {need for need, mapped in ERP_NEED_TYPES.items() if mapped == obj.type}
    is_order = obj.type == "erp:order"
    return {"type": obj.type, "label": obj.label, "sub": obj.sub, "icon": obj.icon, "readable": obj.readable,
            "read_note": obj.read_note, "hidden": obj.masked,
            "source": {"table": obj.table, "json": obj.json, "text": obj.source},
            "masked": len(masked_props()) if is_order else 0, "props": _erp_props() if is_order else [],
            "links": _erp_links(obj.type),
            "actions": [_erp_action_row(spec) for spec in ERP_ACTIONS.values() if spec.target == obj.type],
            "cq": [cq.cq_id for cq in CQS if needs & set(cq.needs)]}

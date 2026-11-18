"""문장으로 고치기 — 줄마다 검사(설계서 2026-11-18-brain-sentence-change 2절 ④ · 8절 · D247).

AI 묶음(:func:`.change_request_model.read_bundle` 꼴)을 화면 줄로 펼치고 줄마다 본다. **검사에 걸린 줄은 빼지 않고** ``check``
에 까닭(코드 · 쉬운 말)을 달아 '못 고친 것'으로 보인다(상태 ``blocked``). 반영은 ``preview`` 줄만 한다.

1. **있는 키인가** — 넣은 사람이 볼 수 있는 지금 항목만(볼 수 없는 키는 없는 키와 같은 답 — 있는지도 알리지 않는다).
2. **고칠 수 있는 층인가**(D247) — 관리자는 모든 층, 층 승인자(:func:`.access.approver_layers` — 판정은
   :func:`.access.approval_problem` 과 같은 표)는 자기 층만. **다른 층 줄은 '같이 볼 것'으로 옮긴다**(줄에서 뺀다).
3. **꼴 · 허용 짝 · 관문** — 모의 실행: 지금 제안 함수(:mod:`.proposals`)를 저장점 안에서 돌리고 되돌린다(꼴 · 속성 틀 ·
   허용 짝 · 링크 제약 · 바깥 자리 실재 · 같은 제안 거절됨 — 넣을 때와 같은 검사). 가림 · 한자가 든 새 글도 막는다.
4. **이미 같은 값**(고침 0) · **서로 맞섬**(같은 항목 · 연결 · 설정 칸을 두 줄이 고침 · 같은 두 항목에 필요 + 제외).
5. **금액 숫자가 든 글** — 못 고친 것으로(가격은 계산기가 정본 — D179).
6. **설정** — 허용 목록(AI 직원 수준 표의 고칠 수 있는 칸 · 값 0 ~ 상한)에 있고 넣은 사람이 관리자일 때만. 상담 AI 관리 칸은 2판.
7. **세부 칸**(2판 — :mod:`.change_request_props`) — 받는 칸 밖(``prop_field``) · 고른 값 밖(``prop_value``)이면 그 줄째 '못 고친
   것'. 고침 값은 지금 실음 칸에 얹어 제안한다(다른 실음 칸은 그대로).

화면 값(줄 ``label`` · ``fields`` · 같이 볼 것 · AI 글)은 사람 말이다(:mod:`.change_request_words` — 주소 · 코드 이름 · 영어 상태
코드를 싣지 않는다, 주소는 ``key`` · ``after`` 칸에만).

``requires`` · ``excludes`` 연결 줄은 ``caution`` 참(미리 보기에서 따로 표시 — 8절). 쓰지 않는다(모의 실행은 저장점을 되돌린다).
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Mapping, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainChange, BrainObject
from foms.services.ai_staff.levels import LEVEL_LABELS
from foms.services.brain import actions
from foms.services.brain.change_request_model import AREA_CS, AREA_LEVELS, CREATE_TYPES, NEW_PREFIX, Material
from foms.services.brain.change_request_props import merged, prop_fields, read_props
from foms.services.brain.change_request_words import (
    CS_SETTING, UNKNOWN_LABEL, UNKNOWN_SETTING, UNNAMED_NEW, external_label, link_kind_label, names_of, status_label,
    tidy, tidy_bundle,
)
from foms.services.brain.constants import (
    BRANDS, DOC_TYPES, KEY_RE, LINK_KINDS, OP_LINK_ADD, OP_LINK_REMOVE, SCOPE_ALL, STATUS_ACTIVE, STATUS_RETIRED,
    TYPE_LAYERS, external_type, link_allowed,
)
from foms.services.brain.display import FIELD_LABELS, LAYER_LABELS
from foms.services.brain.errors import BrainError
from foms.services.brain.gates import hanja_count
from foms.services.brain.labels import pref_of
from foms.services.brain.proposals import Proposer, propose_create, propose_link, propose_retire, propose_update
from foms.services.brain.scope import Viewer, scope_clause
from foms.services.brain.store import current_link, is_current, values_of
from foms.services.cs_agent.masking import leak_counts

KIND_UPDATE, KIND_CREATE, KIND_RETIRE, KIND_SETTING = "update", "create", "retire", "setting"
KIND_LINK_ADD, KIND_LINK_REMOVE = OP_LINK_ADD, OP_LINK_REMOVE
ITEM_KINDS: tuple[str, ...] = (KIND_UPDATE, KIND_CREATE, KIND_RETIRE, KIND_LINK_ADD, KIND_LINK_REMOVE)
#: 줄 상태 — 미리 보기 · 못 고침(검사) · 뺌(넣은 사람) · 반영 · 승인 대기 · 실패 · 되돌림 · 되돌리지 못함 · 거둠.
STATE_PREVIEW, STATE_BLOCKED, STATE_SKIPPED = "preview", "blocked", "skipped"
STATE_APPLIED, STATE_PENDING, STATE_FAILED = "applied", "pending", "failed"
STATE_REVERTED, STATE_REVERT_BLOCKED, STATE_WITHDRAWN = "reverted", "revert_blocked", "withdrawn"
CAUTION_KINDS = frozenset({"requires", "excludes"})
#: 검사 까닭 → 쉬운 말(BrainError 코드는 :data:`.actions.FAILURES` 말을 쓴다).
CHECK_TEXTS: dict[str, str] = {
    "unknown_key": "없는 지식이거나 볼 수 없는 지식이에요.",
    "type": "이 길로는 만들 수 없는 종류예요(가격 규칙 · 사장님 결정 · 기준 답 문구는 따로 넣어요).",
    "orphan_rule": "제작 조건은 걸 제품 · 옵션(적용 연결)이 있어야 만들어요.",
    "new_blocked": "새 항목을 만들지 못해 이 연결도 잇지 않았어요.",
    "new_waiting": "새 항목이 승인을 기다려 연결은 아직 잇지 않았어요 — 승인된 뒤 다시 넣어 주세요.",
    "link_kind": "이을 수 없는 연결 짝이에요.",
    "same": "이미 같은 값이라 고칠 것이 없어요.",
    "missing_link": "이미 없는 연결이에요.",
    "conflict": "같은 묶음의 다른 줄과 맞서요 — 하나만 남겨 다시 넣어 주세요.",
    "money": "금액 숫자가 든 글은 고치지 않아요 — 가격은 계산기에서 고쳐 주세요.",
    "gate": "개인정보 · 한자가 든 글이에요.",
    "setting_area": "이 길로는 아직 못 고치는 설정이에요.",
    "setting_value": "고칠 수 없는 설정 칸이거나 값이에요.",
    "setting_admin": "설정은 관리자만 고쳐요.",
    "later_change": "그 뒤 다른 고침이 같은 곳에 얹혀서 되돌리지 않았어요.",
    "prop_field": "이 길로는 못 고치는 세부 칸이에요(문 방식 · 견적 규칙 종류 · 가로 범위 · 정책 갈래 · 조건 꼴만 고쳐요).",
    "prop_value": "세부 칸에 고를 수 없는 값이에요.",
}
RULE_TYPE, APPLIES_TO = "build_rule", "applies_to"
#: 금액 꼴(숫자 + 원 · 만원 · 억 원, 통화 기호 + 숫자, 숫자 + 달러).
_MONEY = re.compile(r"[₩$]\s*\d|\d[\d,.]*\s*(?:억|만|천)?\s*원|\d[\d,.]*\s*달러")


def check_of(code: str) -> dict[str, str]:
    """줄 ``check`` 칸 — 코드 · 쉬운 말."""
    text = CHECK_TEXTS.get(code) or (actions.message(code) if code in actions.FAILURES else actions.message("BRAIN_ERROR"))
    return {"code": code, "text": text}


def has_money(*texts: Optional[str]) -> bool:
    """글에 금액 숫자가 있나."""
    return any(_MONEY.search(t or "") for t in texts)


def _gate_fail(*texts: Optional[str]) -> bool:
    """가림 검사 · 한자 관문에 걸리나(사람 제안은 관문이 막지 않아 여기서 막는다)."""
    return any(any(leak_counts(t or "").values()) or hanja_count(t or "") for t in texts)


def _row(session: Any, viewer: Viewer, key: Any) -> Optional[BrainObject]:
    """볼 수 있는 지금 항목(없거나 볼 수 없으면 ``None`` — 둘을 가르지 않는다)."""
    if not isinstance(key, str) or not key:
        return None
    return session.execute(select(BrainObject).where(
        BrainObject.item_key == key, is_current(BrainObject), scope_clause(viewer, BrainObject.visibility))
    ).scalar_one_or_none()


def _line(kind: str, *, key: Optional[str], label: str, why: str, layer: Optional[str], plan: Optional[dict] = None,
          fields: Optional[list] = None, before: Any = None, after: Any = None, caution: bool = False) -> dict[str, Any]:
    """줄 하나(번호는 나중에)."""
    return {"no": 0, "kind": kind, "key": key, "label": label, "layer": layer, "before": before, "after": after,
            "fields": fields or [], "why": why, "check": None, "state": STATE_PREVIEW, "caution": caution,
            "change_id": None, "plan": plan or {}}


def _block(line: dict[str, Any], code: str) -> dict[str, Any]:
    """줄을 '못 고친 것'으로(까닭 하나 — 먼저 걸린 것)."""
    if line["check"] is None:
        line["check"], line["state"] = check_of(code), STATE_BLOCKED
    return line


def _update(session: Any, viewer: Viewer, row_in: Mapping[str, Any]) -> dict[str, Any]:
    """고침 줄 — 바뀐 칸만(같은 칸은 뺀다)."""
    row = _row(session, viewer, row_in["key"])
    if row is None:
        return _block(_line(KIND_UPDATE, key=row_in["key"], label=UNKNOWN_LABEL, why=row_in["why"], layer=None),
                      "unknown_key")
    before = values_of(row)
    changed = {f: v for f, v in row_in["after"].items() if before.get(f) != v}
    props, refused, problem = read_props(row.item_type, row.payload, row_in.get("props"))
    fields = [{"name": f, "label": FIELD_LABELS.get(f, f), "before": before.get(f), "after": v} for f, v in changed.items()]
    fields += prop_fields(row.item_type, row.payload, props, refused)
    plan_after = {**changed, **({"payload": merged(row.payload, props)} if props else {})}
    payload = row.payload if isinstance(row.payload, dict) else {}
    line = _line(KIND_UPDATE, key=row.item_key, label=pref_of(row.name, row.payload), why=row_in["why"],
                 layer=row.layer, fields=fields,
                 before={**{f: before.get(f) for f in changed}, **{f"payload.{n}": payload.get(n) for n in props}},
                 after={**changed, **{f"payload.{n}": v for n, v in props.items()}},
                 plan={"key": row.item_key, "base_version": row.version, "after": plan_after})
    if problem:
        return _block(line, problem)
    if not plan_after:
        return _block(line, "same")
    if has_money(changed.get("name"), changed.get("text")):
        return _block(line, "money")
    return _block(line, "gate") if _gate_fail(changed.get("name"), changed.get("text")) else line


def approver_of(user_id: Any, request_id: int) -> str:
    """지식 문서 승인 칸 글 — 반영한 사람 번호 · 묶음 번호(주간 고침 안 승인 :mod:`.template_fix` 와 같은 꼴)."""
    return f"FOMS 사용자 {int(user_id or 0)} · 문장으로 고치기 #{int(request_id)}"


def doc_fields(doc_id: str, *, request_id: int, user_id: Any, day: datetime.date) -> dict[str, Any]:
    """새 지식 문서 항목의 문서 칸(옮기기 묶음 ``plan_rules.doc_fields`` 꼴 — 옮겨 올 앞 항목이 없어 의도 · 꼬리표는 비우고 근거
    파일 칸은 묶음 번호, 승인 칸은 넣은 사람 · 그날). 반영 때 :func:`approve_doc` 가 반영하는 사람 · 반영 날로 다시 적는다."""
    return {"doc_id": doc_id[:64], "intents": [], "tags": [], "source": f"change_request:{int(request_id)}",
            "approved_by": approver_of(user_id, request_id), "approved_at": day.isoformat()}


def approve_doc(line: dict[str, Any], *, request_id: int, user_id: Any, day: datetime.date) -> None:
    """지식 문서 만들기 줄의 승인 칸을 지금 반영하는 사람 · 반영 날(한국 날짜)로."""
    payload = (line["plan"].get("values") or {}).get("payload")
    if isinstance(payload, dict) and payload.get("doc_id"):
        payload.update(approved_by=approver_of(user_id, request_id), approved_at=day.isoformat())


def _create(row_in: Mapping[str, Any], *, request_id: int, number: int, today: datetime.date,
            user_id: Any) -> dict[str, Any]:
    """새 항목 줄 — 키는 코드가 정한다. 지식 문서 유형(사실 · 정책 · 제작 조건)은 ``<브랜드>/cr<묶음>-<차례>``(문서 id 와 같은
    꼬리 — 옮기기 키 꼴)와 문서 칸, 그 밖은 ``<브랜드>/<유형>/cr<묶음>-<차례>``."""
    item_type, brand = row_in["type"], row_in["brand"]
    values = {"name": row_in["values"].get("name", ""), "text": row_in["values"].get("text") or None}
    props, refused, problem = read_props(item_type, {}, row_in.get("props"), create=True)
    layers = sorted(TYPE_LAYERS.get(item_type, ()))
    layer = layers[0] if len(layers) == 1 else None
    doc_id = f"cr{int(request_id)}-{int(number)}"
    is_doc = item_type in DOC_TYPES
    key = f"{str(brand).lower()}/{doc_id}" if is_doc else f"{str(brand).lower()}/{item_type}/{doc_id}"
    full = {**values, "status": STATUS_ACTIVE, "visibility": SCOPE_ALL, "evidence_kind": "person",
            "evidence_ref": f"change_request:{request_id}", "checked_at": today.isoformat()}
    if is_doc:
        full["payload"] = {**doc_fields(doc_id, request_id=request_id, user_id=user_id, day=today), **props}
    line = _line(KIND_CREATE, key=key, label=values["name"] or UNNAMED_NEW, why=row_in["why"], layer=layer,
                 fields=[{"name": f, "label": FIELD_LABELS.get(f, f), "before": None, "after": v}
                         for f, v in values.items() if v] + prop_fields(item_type, {}, props, refused),
                 before=None, after={**{f: v for f, v in values.items() if v},
                                     **{f"payload.{n}": v for n, v in props.items()}},
                 plan={"key": key, "brand": brand, "layer": layer, "type": item_type, "values": full, "new": number})
    if item_type not in CREATE_TYPES or layer is None:
        return _block(line, "type")
    if brand not in BRANDS or not values["name"]:
        return _block(line, "BRAIN_SHAPE")
    if problem:
        return _block(line, problem)
    if has_money(values["name"], values["text"]):
        return _block(line, "money")
    return _block(line, "gate") if _gate_fail(values["name"], values["text"]) else line


def _retire(session: Any, viewer: Viewer, row_in: Mapping[str, Any]) -> dict[str, Any]:
    """은퇴 줄."""
    row = _row(session, viewer, row_in["key"])
    if row is None:
        return _block(_line(KIND_RETIRE, key=row_in["key"], label=UNKNOWN_LABEL, why=row_in["why"], layer=None),
                      "unknown_key")
    line = _line(KIND_RETIRE, key=row.item_key, label=pref_of(row.name, row.payload), why=row_in["why"],
                 layer=row.layer, before={"status": row.status}, after={"status": STATUS_RETIRED},
                 fields=[{"name": "status", "label": FIELD_LABELS["status"], "before": status_label(row.status),
                          "after": status_label(STATUS_RETIRED)}],
                 plan={"key": row.item_key, "base_version": row.version})
    return _block(line, "same") if row.status == STATUS_RETIRED else line


def _end_name(session: Any, viewer: Viewer, key: str) -> tuple[Optional[str], Optional[str]]:
    """연결 끝 — (유형, 이름). 바깥 자리는 가짜 유형 · 그 자리 이름, 볼 수 없거나 없으면 (None, None)."""
    external = external_type(key)
    if external is not None:
        return external, external_label(key)
    row = _row(session, viewer, key)
    return (row.item_type, pref_of(row.name, row.payload)) if row is not None else (None, None)


def _source(session: Any, viewer: Viewer, start: str, news: Mapping[int, dict[str, Any]]) -> tuple[Any, ...]:
    """연결 시작 — (키, 유형, 이름, 층, 새 항목 차례). ``new:<n>`` 은 같은 묶음의 n 번째 새 항목, 없으면 모두 ``None``."""
    if start.startswith(NEW_PREFIX):
        number = start[len(NEW_PREFIX):]
        made = news.get(int(number)) if number.isdigit() else None
        if made is None:
            return None, None, None, None, None
        plan = made["plan"]
        return plan["key"], plan["type"], made["label"], made["layer"], plan["new"]
    row = _row(session, viewer, start)
    if row is None:
        return None, None, None, None, None
    return row.item_key, row.item_type, pref_of(row.name, row.payload), row.layer, None


def _link(session: Any, viewer: Viewer, row_in: Mapping[str, Any],
          news: Mapping[int, dict[str, Any]]) -> dict[str, Any]:
    """연결 더하기 · 빼기 줄 — 종류 · 양 끝 · 허용 짝 · 이미 있음. 시작이 ``new:<n>`` 이면 같은 묶음의 새 항목(더하기만)."""
    kind_op = KIND_LINK_ADD if row_in["op"] == "add" else KIND_LINK_REMOVE
    kind, end = row_in["kind"], row_in["to"]
    start, source_type, source_name, layer, new = _source(session, viewer, row_in["from"], news)
    start = start or row_in["from"]
    to_type, to_name = _end_name(session, viewer, end) if end else (None, None)
    label = f"{source_name or UNKNOWN_LABEL} → {to_name or UNKNOWN_LABEL} ({link_kind_label(kind)})"
    ident = {"kind": kind, "from": start, "to": end}
    plan = {"op": kind_op, "kind": kind, "from": start, "to": end, **({"new": new} if new is not None else {})}
    line = _line(kind_op, key=start, label=label, why=row_in["why"], layer=layer,
                 before=None if kind_op == KIND_LINK_ADD else ident, after=ident if kind_op == KIND_LINK_ADD else None,
                 caution=kind in CAUTION_KINDS, plan=plan)
    if row_in["op"] not in ("add", "remove") or kind not in LINK_KINDS or (new is not None and kind_op != KIND_LINK_ADD):
        return _block(line, "link_kind")
    if source_type is None or to_type is None:
        return _block(line, "unknown_key")
    if new is not None:
        return line if link_allowed(source_type, kind, to_type) else _block(line, "link_kind")
    link = current_link(session, kind, start, end)
    if kind_op == KIND_LINK_ADD:
        if not link_allowed(source_type, kind, to_type):
            return _block(line, "link_kind")
        return _block(line, "same") if link is not None else line
    if link is None:
        return _block(line, "missing_link")
    line["plan"]["base_version"] = link.version
    return line


def _setting(row_in: Mapping[str, Any], material: Material, *, admin: bool) -> dict[str, Any]:
    """설정 줄 — 허용 목록(수준 표 칸 · 값) · 관리자만 · 같은 값."""
    known = material.settings.get(row_in["name"]) if row_in["area"] == AREA_LEVELS else None
    before = known["value"] if known is not None else None
    agent, _dot, action = row_in["name"].partition(".")
    label = known["label"] if known else (CS_SETTING if row_in["area"] == AREA_CS else UNKNOWN_SETTING)
    line = _line(KIND_SETTING, key=row_in["name"], label=label, why=row_in["why"],
                 layer=None, before={"level": before}, after={"level": row_in["value"]},
                 fields=[{"name": "level", "label": "수준", "before": level_label(before),
                          "after": level_label(row_in["value"])}],
                 plan={"area": row_in["area"], "agent": agent, "action": action, "value": row_in["value"],
                       "before": before})
    if row_in["area"] != AREA_LEVELS:
        return _block(line, "setting_area")
    if known is None or row_in["value"] not in known["choices"]:
        return _block(line, "setting_value")
    if not admin:
        return _block(line, "setting_admin")
    return _block(line, "same") if before == row_in["value"] else line


def level_label(value: Any) -> Any:
    """AI 직원 수준 값 → 화면 말(모르는 값은 그대로 — 없는 칸이면 빈 값)."""
    return LEVEL_LABELS.get(value, value) if isinstance(value, int) and not isinstance(value, bool) else value


def _identities(line: dict[str, Any]) -> list[tuple]:
    """맞섬을 견줄 정체들 — 항목 키 · 연결(종류 · 양 끝) · 같은 두 항목의 필요/제외 짝 · 설정 칸."""
    plan = line["plan"]
    if line["kind"] in (KIND_UPDATE, KIND_RETIRE):
        return [("item", plan.get("key"))]
    if line["kind"] in (KIND_LINK_ADD, KIND_LINK_REMOVE):
        out = [("link", plan.get("kind"), plan.get("from"), plan.get("to"))]
        if line["kind"] == KIND_LINK_ADD and plan.get("kind") in CAUTION_KINDS:
            out.append(("pair", plan.get("from"), plan.get("to")))
        return out
    if line["kind"] == KIND_SETTING:
        return [("setting", line["key"])]
    return []


def _mark_conflicts(lines: list[dict[str, Any]]) -> None:
    """같은 정체를 두 줄 이상이 고치면 그 줄 모두 '맞섬'(검사를 지난 줄끼리만)."""
    seen: dict[tuple, list[dict[str, Any]]] = {}
    for line in lines:
        if line["check"] is None:
            for ident in _identities(line):
                seen.setdefault(ident, []).append(line)
    for group in seen.values():
        if len(group) > 1:
            for line in group:
                _block(line, "conflict")


def propose_line(session: Any, line: Mapping[str, Any], *, proposer: Proposer, request_id: int, reason: str,
                 known: str, now: datetime.datetime) -> BrainChange:
    """항목 · 연결 줄 하나를 지금 제안 함수로 제안 줄로 만든다(묶음 번호를 단다 · flush 만). 모의 실행과 반영이 같이 쓴다."""
    plan, evidence = line["plan"], [f"change_request:{request_id}"]
    kind = line["kind"]
    if kind == KIND_UPDATE:
        change = propose_update(session, key=plan["key"], base_version=plan["base_version"], after=plan["after"],
                                reason=reason, proposer=proposer, evidence=evidence, now=now, known=known)
    elif kind == KIND_CREATE:
        change = propose_create(session, key=plan["key"], brand=plan["brand"], layer=plan["layer"],
                                item_type=plan["type"], values=plan["values"], reason=reason, proposer=proposer,
                                evidence=evidence, now=now, known=known)
    elif kind == KIND_RETIRE:
        change = propose_retire(session, key=plan["key"], base_version=plan["base_version"], reason=reason,
                                proposer=proposer, evidence=evidence, now=now)
    else:
        change = propose_link(session, op=plan["op"], kind=plan["kind"], from_key=plan["from"], to_key=plan["to"],
                              reason=reason, proposer=proposer, base_version=plan.get("base_version"),
                              evidence=evidence, now=now)
    change.request_id = request_id
    session.flush()
    return change


def reason_of(request_id: int, line: Mapping[str, Any]) -> str:
    """제안 줄 까닭 — 묶음 번호 + AI 가 적은 한 줄(가린 글)."""
    return f"문장으로 고치기 #{request_id} — {line.get('why') or '바뀐 내용 반영'}"[:500]


def _dry_run(session: Any, line: dict[str, Any], *, actor_id: int, request_id: int, known: str,
             now: datetime.datetime) -> None:
    """모의 실행 — 저장점 안에서 제안 함수를 돌리고 늘 되돌린다. 걸리면 그 코드로 '못 고친 것'."""
    savepoint = session.begin_nested()
    try:
        propose_line(session, line, proposer=Proposer.user(actor_id), request_id=request_id,
                     reason=reason_of(request_id, line), known=known, now=now)
    except BrainError as exc:
        _block(line, exc.code)
    finally:
        savepoint.rollback()


def _also_from_notes(session: Any, viewer: Viewer, notes: list[str], names: Mapping[str, str]) -> list[dict[str, Any]]:
    """AI 의 '같이 볼 것'(``키 — 까닭``) — 볼 수 있는 키면 이름을 단다. 키 꼴인데 없거나 볼 수 없으면 주소 대신
    :data:`UNKNOWN_LABEL`(링크 없음 — ``key`` 비움), 키 꼴이 아닌 글이면 다듬은 글 그대로."""
    out = []
    for note in notes:
        head, _sep, why = note.partition(" — ")
        key = head.strip()
        row = _row(session, viewer, key)
        if row is not None:
            out.append({"key": row.item_key, "label": pref_of(row.name, row.payload), "why": why.strip() or None})
        elif KEY_RE.fullmatch(key) and ("/" in key or ":" in key or "." in key):
            label = names.get(key) or external_label(key) or UNKNOWN_LABEL  # 설정 칸 · 새 항목 · 바깥 자리는 그 이름
            out.append({"key": None, "label": label, "why": why.strip() or None})
        else:
            out.append({"key": None, "label": tidy(note, names), "why": None})
    return out


def check_bundle(session: Any, bundle: Mapping[str, Any], material: Material, *, viewer: Viewer,
                 scope: Optional[tuple[str, ...]], request_id: int, known: str,
                 now: datetime.datetime, today: datetime.date) -> dict[str, Any]:
    """AI 묶음 → ``{"lines", "also_look", "summary", "needs_code", "questions"}``(사람 글은 다듬은 것 —
    :func:`.change_request_words.tidy_bundle`). ``scope`` = 고칠 수 있는 층(``None`` = 모두 — 관리자)."""
    names = names_of(material.items, material.settings, bundle["creates"])
    bundle = tidy_bundle(bundle, names)
    lines: list[dict[str, Any]] = [_update(session, viewer, r) for r in bundle["updates"]]
    news = {n: _create(r, request_id=request_id, number=n, today=today, user_id=viewer.user_id)
            for n, r in enumerate(bundle["creates"], 1)}
    lines += list(news.values())
    lines += [_retire(session, viewer, r) for r in bundle["retires"]]
    lines += [_link(session, viewer, r, news) for r in bundle["links"]]
    lines += [_setting(r, material, admin=viewer.is_admin) for r in bundle["settings"]]
    also = _also_from_notes(session, viewer, bundle["also_look"], names)
    kept = []
    for line in lines:
        if scope is not None and line["kind"] != KIND_SETTING and line["layer"] is not None and line["layer"] not in scope:
            label = LAYER_LABELS.get(line["layer"], line["layer"])
            also.append({"key": line["key"] if line["kind"] != KIND_CREATE else None, "label": line["label"],
                         "why": f"{label} 층이라 그 층 승인자 · 관리자가 볼 것이에요 — {line['why']}".strip(" —")})
        else:
            kept.append(line)
    _mark_conflicts(kept)
    for line in kept:
        if (line["check"] is None and line["kind"] in ITEM_KINDS and viewer.user_id is not None
                and not is_new_link(line)):
            _dry_run(session, line, actor_id=viewer.user_id, request_id=request_id, known=known, now=now)
    _tie_new_links(kept)
    for number, line in enumerate(kept, 1):
        line["no"] = number
    for line in kept:  # 새 항목 연결 줄은 그 만들기 줄 번호를 안다(반영 차례 · 한 묶음 저장점)
        if is_new_link(line):
            line["plan"]["after_line"] = next((m["no"] for m in kept if m["kind"] == KIND_CREATE
                                               and m["plan"].get("new") == line["plan"]["new"]), None)
    return {"lines": kept, "also_look": also, "summary": bundle["summary"], "needs_code": bundle["needs_code"],
            "questions": bundle["questions"]}


def is_new_link(line: Mapping[str, Any]) -> bool:
    """같은 묶음의 새 항목에서 나가는 연결 줄인가."""
    return line["kind"] == KIND_LINK_ADD and line["plan"].get("new") is not None


def rule_links(line: Mapping[str, Any], lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """새 제작 조건 줄이 걸 적용 연결 줄들(검사를 지난 것)."""
    return [x for x in lines if is_new_link(x) and x["plan"]["new"] == line["plan"].get("new")
            and x["plan"]["kind"] == APPLIES_TO and x["check"] is None]


def _tie_new_links(lines: list[dict[str, Any]]) -> None:
    """새 항목과 그 연결 줄을 묶어 본다 — 만들기가 못 고친 것이면 연결도, 걸 곳 없는 제작 조건(외톨이)은 만들기도 못 고친 것."""
    creates = {x["plan"]["new"]: x for x in lines if x["kind"] == KIND_CREATE}
    for line in lines:
        if is_new_link(line) and (creates.get(line["plan"]["new"]) or {}).get("check") is not None:
            _block(line, "new_blocked")
    for line in creates.values():
        if line["check"] is None and line["plan"]["type"] == RULE_TYPE and not rule_links(line, lines):
            _block(line, "orphan_rule")
            for link in lines:
                if is_new_link(link) and link["plan"]["new"] == line["plan"]["new"]:
                    _block(link, "new_blocked")

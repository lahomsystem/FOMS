"""지식 문서(상담 두뇌가 읽는 꼴) ↔ brain 항목 — 짝 바꾸기 · 표에서 다시 만들기 · 그림자 견주기(설계서 7.5 끝 '저장 꼴').

- 지식 문서 항목 하나 = brain 항목 하나(지식 문서 유형 :data:`.constants.DOC_TYPES`). 문서 칸 열 개는 그대로 돌아온다 —
  ``text`` · ``checked_at`` 는 줄 칸, 나머지(문서 id · 의도 · 꼬리표 · 근거 파일 · 승인한 사람 · 승인 날 · 문서 차례)는
  ``payload``. 상태는 ``approved`` ↔ ``active``(반영)만 이름이 다르다.
- 두 브랜드에 같은 항목은 ``COMMON`` 항목 하나(3.1 규칙 1 · D99)이고, 다시 만들 때 두 브랜드 문서에 모두 들어간다. 문서
  차례는 ``payload.doc_pos[브랜드]`` 로 지킨다(차례가 바뀌면 두뇌가 고르는 의도 차례가 바뀐다).
- **아직 상담 두뇌는 표를 읽지 않고, 표에서 지식 문서를 쓰지도 않는다** — :func:`shadow_compare` 로 견주기만 한다.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainObject
from foms.services.brain.constants import (
    BRAND_COMMON, CONFIRMED, DOC_TYPES, EVIDENCE_IMPORT, OBSERVED, SCOPE_ALL, STATUS_ACTIVE, STATUS_DRAFT,
    STATUS_RETIRED, TYPE_GRADES, TYPE_KINDS,
)
from foms.services.brain.scope import SYSTEM, Viewer, scope_clause
from foms.services.brain.store import is_current, values_of
from foms.services.cs_agent.knowledge import knowledge_key, read_stored
from foms.services.cs_agent.knowledge_doc import (
    ITEM_FIELDS, SCHEMA_VERSION, STATUS_APPROVED, KnowledgeSchemaError, diff_documents, validate_document,
)
from foms.services.cs_agent.knowledge_doc import STATUS_DRAFT as DOC_DRAFT
from foms.services.cs_agent.knowledge_doc import STATUS_RETIRED as DOC_RETIRED

STATUS_TO_DOC: dict[str, str] = {STATUS_ACTIVE: STATUS_APPROVED, STATUS_DRAFT: DOC_DRAFT, STATUS_RETIRED: DOC_RETIRED}
DOC_TO_STATUS: dict[str, str] = {doc: status for status, doc in STATUS_TO_DOC.items()}
#: 지식 문서 유형 ``payload`` 칸.
DOC_PAYLOAD_KEYS = frozenset({"doc_id", "intents", "tags", "source", "approved_by", "approved_at", "doc_pos"})
#: 옮기기를 다시 돌릴 때 문서를 따라 맞추는 칸(이름 · 보기 범위 · 사본 목록 등 brain 에서만 정하는 칸은 건드리지 않는다).
SYNC_FIELDS: tuple[str, ...] = ("text", "status", "confidence", "checked_at", "payload")


def doc_item_of(values: Mapping[str, Any], item_type: str) -> dict[str, Any]:
    """brain 값 칸 → 지식 문서 항목(칸 순서 :data:`ITEM_FIELDS`)."""
    payload = values.get("payload") if isinstance(values.get("payload"), dict) else {}
    item = {
        "id": payload.get("doc_id"), "kind": TYPE_KINDS.get(item_type), "intents": list(payload.get("intents") or []),
        "text": values.get("text"), "status": STATUS_TO_DOC.get(values.get("status")),
        "approved_by": payload.get("approved_by"), "approved_at": payload.get("approved_at"),
        "checked_at": values.get("checked_at"), "source": payload.get("source"), "tags": list(payload.get("tags") or []),
    }
    return {name: item[name] for name in ITEM_FIELDS}


def doc_values(item: Mapping[str, Any], *, item_type: str, positions: Mapping[str, int], evidence_ref: str,
               ) -> dict[str, Any]:
    """정본 지식 문서 항목 → brain 값 칸(옮기기). 이름은 문서 id, 보기 범위는 모두(내부)."""
    approved = bool(item.get("approved_by")) and bool(item.get("approved_at"))
    return {
        "name": item["id"], "text": item["text"], "status": DOC_TO_STATUS[item["status"]],
        "confidence": CONFIRMED if approved else OBSERVED, "risk_grade": TYPE_GRADES[item_type],
        "valid_from": None, "valid_to": None, "checked_at": item.get("checked_at"),
        "evidence_kind": EVIDENCE_IMPORT, "evidence_ref": evidence_ref, "visibility": SCOPE_ALL, "copies": None,
        "payload": {"doc_id": item["id"], "intents": list(item.get("intents") or []), "tags": list(item.get("tags") or []),
                    "source": item.get("source"), "approved_by": item.get("approved_by"),
                    "approved_at": item.get("approved_at"), "doc_pos": dict(sorted(positions.items()))},
    }


def doc_rows(session: Any, brand: str, *, viewer: Viewer = SYSTEM) -> list[BrainObject]:
    """그 브랜드 지식 문서에 들어갈 지금 줄(그 브랜드 + 공통) — 문서 차례 → 키 순."""
    query = select(BrainObject).where(
        is_current(BrainObject), BrainObject.brand.in_((brand, BRAND_COMMON)), BrainObject.item_type.in_(DOC_TYPES),
        scope_clause(viewer, BrainObject.visibility))
    rows = session.execute(query).scalars().all()

    def order(row: BrainObject) -> tuple[int, int, str]:
        """문서 차례가 있는 줄 먼저(차례 순), 없는 줄은 뒤에 키 순."""
        position = ((row.payload or {}).get("doc_pos") or {}).get(brand)
        return (0, position, row.item_key) if isinstance(position, int) else (1, 0, row.item_key)

    return sorted(rows, key=order)


def regenerate_document(session: Any, brand: str, *, viewer: Viewer = SYSTEM) -> dict[str, Any]:
    """표에서 그 브랜드 지식 문서를 오늘 꼴 그대로 다시 만든다(정본 꼴 — :func:`validate_document` 를 지난 것).

    Raises:
        KnowledgeSchemaError: 표의 줄로 만든 문서가 지식 문서 꼴이 아니다(같은 문서 id 두 개 등).
    """
    items = [doc_item_of(values_of(row), row.item_type) for row in doc_rows(session, brand, viewer=viewer)]
    return validate_document({"schema_version": SCHEMA_VERSION, "brand": brand, "items": items}, brand=brand)


def shadow_compare(session: Any, brand: str) -> dict[str, Any]:
    """저장된 지식 문서와 표에서 다시 만든 문서를 견준다 — 항목 id · 칸 이름 · 개수만(글 없음)."""
    stored = read_stored(session, brand)
    out: dict[str, Any] = {"brand": brand, "setting_key": knowledge_key(brand), "stored_version": stored.version,
                           "stored_problem": stored.problem}
    regenerated: Optional[dict[str, Any]] = None
    try:
        regenerated = regenerate_document(session, brand)
    except KnowledgeSchemaError as exc:
        out["regenerate_problems"] = list(exc.problems)
    diff = diff_documents(stored.document, regenerated)
    out.update(equal=stored.document is not None and stored.document == regenerated,
               items_stored=len((stored.document or {}).get("items") or []),
               items_regenerated=len((regenerated or {}).get("items") or []), diff=diff.summary())
    return out

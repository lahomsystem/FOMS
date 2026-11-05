"""주간 고침 안 승인 → 회사 지식 반영(설계서 7.5 '반영 때마다 표에서 다시 만든다' · 3.1 규칙 1 — 표가 정본).

사장님(ADMIN)이 주간 고침 안(:mod:`foms.services.cs_agent.weekly_fix_store`)을 승인하면 **지식 문서를 직접 고치지 않는다** —
그 기준 답 항목의 brain 제안(사람 제안)을 만들어 곧바로 반영 동작(:func:`.apply.apply_change`)으로 넣는다. 지식 문서는 반영이
표에서 다시 쓴다(:mod:`.doc_sync`). 승인한 사람 = 제안한 사람 = 반영한 사람(로그인 ADMIN — 부르는 쪽이 넘긴다).

- 있는 항목: 그 브랜드 항목의 글 · 상태(반영) · 승인한 사람 · 승인 날을 고친다. **공통 항목이면 멈춘다**
  (:class:`TemplateFixCommonError`) — 두 브랜드가 같이 쓰는 글을 한 브랜드 대화에서 나온 고침 안으로 바꾸지 않는다. 회사 지식
  화면에서 고칠 말 제안으로 바꾼다.
- 표에 그 항목이 없으면(옮기기 전) 멈춘다 — 문서만 고치는 두 번째 정본을 만들지 않는다.
- 새 항목: 그 브랜드 기준 답 항목을 만든다(키 ``<브랜드>/fix-<안 id>`` · 문서 id ``fix-<안 id>`` — 예전과 같은 id).
커밋은 호출자 몫이다.
"""

from __future__ import annotations

import copy
import datetime
from typing import Any, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainObject
from foms.services.brain.apply import apply_change
from foms.services.brain.constants import (
    BRAND_COMMON, DOC_TYPES, LAYER_CS, SCOPE_ALL, STATUS_ACTIVE, TYPE_GRADES, is_doc_item,
)
from foms.services.brain.errors import BrainTargetError
from foms.services.brain.proposals import Proposer, propose_create, propose_update
from foms.services.brain.store import is_current
from foms.services.cs_agent.knowledge import read_stored

TEMPLATE = "template"
SOURCE = "weekly_fix"
REASON = "주간 고침 안 승인(사장님)"
#: 이 길이 만든 제안 · 결정의 액션 이름(:data:`.actions.SYSTEM_ACTIONS`).
ACTION = "weekly_fix"


class TemplateFixCommonError(BrainTargetError):
    """고칠 기준 답이 두 브랜드 공통 항목이다 — 한 브랜드 고침 안으로 바꾸지 않는다(회사 지식 화면에서 제안으로)."""

    code = "BRAIN_FIX_COMMON"


def doc_row(session: Any, brand: str, doc_id: str) -> Optional[BrainObject]:
    """그 브랜드 지식 문서에 들어가는 지금 줄 가운데 문서 id 가 같은 줄(브랜드 또는 공통 — 없으면 ``None``)."""
    rows = session.execute(select(BrainObject).where(
        is_current(BrainObject), BrainObject.item_type.in_(DOC_TYPES),
        BrainObject.brand.in_((brand, BRAND_COMMON)))).scalars()
    return next((row for row in rows if is_doc_item(row.item_type, row.payload)
                 and (row.payload or {}).get("doc_id") == doc_id), None)


def apply_fix(session: Any, *, brand: str, fix_id: str, item_id: Optional[str], intent: Optional[str], text: str,
              actor: Any, today: str, now: Optional[datetime.datetime] = None) -> int:
    """승인한 고침 안을 회사 지식으로 넣고, 다시 쓴 그 브랜드 지식 문서 버전을 돌려준다(커밋은 호출자).

    Raises:
        TemplateFixCommonError: 공통 항목. BrainTargetError: 표에 그 기준 답이 없음 · 같은 제안이 거절됨 · 바뀐 칸 없음.
        BrainError 갈래: 반영 동작이 멈춤(지식 문서가 표와 다름 ``BRAIN_DOC_SYNC`` 등).
    """
    proposer = Proposer.user(int(actor.id))
    approval = {"approved_by": f"FOMS 사용자 {int(actor.id)} · 주간 고침 안", "approved_at": today}
    evidence = [f"cs_agent_fix_proposals:{fix_id}"[:200]]
    if item_id:
        row = doc_row(session, brand, item_id)
        if row is None or row.item_type != TEMPLATE:
            raise BrainTargetError(f"고칠 기준 답이 회사 지식 표에 없다: {item_id}")
        if row.brand == BRAND_COMMON:
            raise TemplateFixCommonError(f"두 브랜드 공통 기준 답이다: {row.item_key}")
        payload = {**copy.deepcopy(row.payload or {}), **approval}
        change = propose_update(session, key=row.item_key, base_version=row.version, reason=REASON, proposer=proposer,
                                after={"text": text, "status": STATUS_ACTIVE, "payload": payload}, evidence=evidence,
                                now=now, action=ACTION)
    else:
        doc_id = f"fix-{fix_id.lower()}"
        values = {"name": doc_id, "text": text, "status": STATUS_ACTIVE, "risk_grade": TYPE_GRADES[TEMPLATE],
                  "evidence_kind": "case", "evidence_ref": evidence[0], "visibility": SCOPE_ALL,
                  "payload": {"doc_id": doc_id, "intents": [intent] if intent else [], "tags": ["weekly-fix"],
                              "source": SOURCE, **approval}}
        change = propose_create(session, key=f"{brand.lower()}/{doc_id}", brand=brand, layer=LAYER_CS,
                                item_type=TEMPLATE, values=values, reason=REASON, proposer=proposer, evidence=evidence,
                                now=now, action=ACTION)
    apply_change(session, change.id, actor=actor, now=now, action=ACTION)
    return read_stored(session, brand).version

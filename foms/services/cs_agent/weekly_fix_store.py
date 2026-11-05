"""주간 고침 안 제안함 — 저장 · 주 한 번 표 · 사장님(ADMIN) 승인 · 거절(설계서 17.6.1 (e) · 사장님 결정 D94).

SystemSetting 한 줄(:data:`PROPOSALS_KEY`)에 ``{"weeks": [ISO 주], "proposals": [...], "rejected": [지문]}`` 을 둔다. 글 칸
(``proposed_text`` · ``why``)은 가림 검사를 지난 글만 들어온다(:mod:`.weekly_fix`).

- **자동 반영 길이 없다**: 제안은 늘 ``pending_owner`` 로 들어오고, 바꾸는 길은 :func:`decide` 하나뿐이다. 부르는 쪽은 로그인한
  ADMIN 의 웹 승인 동작(:mod:`foms.api.cs_agent_fix_proposals`)이고, 결정한 사람 번호는 **로그인 사용자에서만** 받는다 — 본문의
  자유 글(``approved_by`` 등)로는 승인되지 않는다(R10-18). 등급 A 자동(D64)이 열려도 이 묶음은 열리지 않는다.
- **승인**: 지식 문서를 직접 고치지 않고 **회사 지식(brain 표)에 반영한다**(:func:`foms.services.brain.template_fix.apply_fix` —
  사람 제안 → 반영 동작, 설계서 master brain 7.5 · 3.1 규칙 1). 지식 문서는 반영이 표에서 다시 쓴다(버전 · 수정 기록 그대로).
  있는 항목이면 글 · 승인자 · 승인 날을 새로, 새 항목이면 그 묶음 의도의 그 브랜드 기준 답 문구(template)로 더한다. 넣지
  못하면(공통 항목 ``common_item`` · 표에 항목 없음 · 문서가 표와 다름 · 버전 충돌) 제안은 그대로 ``pending_owner``.
- **거절**: 한 줄 까닭과 같이 남기고, 같은 (항목, 고친 글) 지문은 다음 주에 다시 내지 않는다.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from foms.services.brain.errors import BrainError
from foms.services.brain.template_fix import TemplateFixCommonError, apply_fix
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.datetime_kst import get_today_kst
from models import SecurityLog, SystemSetting

__all__ = [
    "MAX_PROPOSALS", "PROPOSALS_KEY", "STATE_APPROVED", "STATE_PENDING", "STATE_REJECTED", "Decision",
    "add_proposals", "claim_week", "decide", "fingerprint", "list_proposals", "rejected_prints",
]

PROPOSALS_KEY = "cs_agent_fix_proposals"
STATE_PENDING, STATE_APPROVED, STATE_REJECTED = "pending_owner", "approved", "rejected"
MAX_PROPOSALS, MAX_WEEKS, MAX_NOTE = 200, 12, 200
SOURCE = "weekly_fix"


@dataclass(frozen=True)
class Decision:
    """결정 결과 — 코드 · HTTP 상태 · 넣은 지식 판(승인했을 때)."""

    code: str
    status: int
    version: Optional[int] = None


def fingerprint(item_id: str, text: str) -> str:
    """(항목, 고친 글) 지문 — 거절한 안을 다시 내지 않으려고 둔다(글은 남기지 않는 되돌릴 수 없는 값)."""
    return hashlib.sha256(f"{item_id}\n{text}".encode("utf-8")).hexdigest()[:24]


def _empty() -> dict[str, Any]:
    return {"weeks": [], "proposals": [], "rejected": []}


def _doc(row: Any) -> dict[str, Any]:
    """저장 값 → 꼴을 맞춘 사본(틀린 칸은 빈 값)."""
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    out = _empty()
    for name in out:
        if isinstance(value.get(name), list):
            out[name] = copy.deepcopy(value[name])
    return out


def _locked(session: Any) -> Any:
    """제안함 줄을 잠가 읽는다(없으면 먼저 만들어 커밋)."""
    if session.get(SystemSetting, PROPOSALS_KEY) is None:
        session.add(SystemSetting(setting_key=PROPOSALS_KEY, setting_value=_empty(),
                                  description="AI 상담팀원 주간 고침 안 — 사장님 승인 전 제안(설계서 17.6.1 (e))"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
    return session.get(SystemSetting, PROPOSALS_KEY, populate_existing=True, with_for_update=True)


def _put(row: Any, doc: dict[str, Any]) -> None:
    row.setting_value = doc
    flag_modified(row, "setting_value")
    row.version = int(row.version or 1) + 1


def claim_week(session: Any, week: str) -> bool:
    """이 주를 처음 돈다면 표를 남기고 커밋해 True — 이미 돈 주면 False(주 한 번 — 부르기 전에 표를 남긴다)."""
    row = _locked(session)
    doc = _doc(row)
    if week in doc["weeks"]:
        session.rollback()
        return False
    doc["weeks"] = [*doc["weeks"], week][-MAX_WEEKS:]
    _put(row, doc)
    session.commit()
    return True


def rejected_prints(session: Any) -> frozenset[str]:
    """거절한 안의 지문(다시 내지 않는다)."""
    return frozenset(_doc(session.get(SystemSetting, PROPOSALS_KEY, populate_existing=True))["rejected"])


def add_proposals(session: Any, proposals: list[dict[str, Any]]) -> int:
    """관문을 지난 안을 ``pending_owner`` 로 더하고 커밋한다(거절 지문 · 같은 지문 대기 안은 뺀다). 더한 수를 돌려준다."""
    row = _locked(session)
    doc = _doc(row)
    seen = set(doc["rejected"]) | {p.get("print") for p in doc["proposals"] if p.get("state") == STATE_PENDING}
    fresh = [dict(p, state=STATE_PENDING) for p in proposals if p["print"] not in seen]
    if not fresh:
        session.rollback()
        return 0
    doc["proposals"] = [*doc["proposals"], *fresh][-MAX_PROPOSALS:]
    _put(row, doc)
    session.commit()
    return len(fresh)


def list_proposals(session: Any) -> list[dict[str, Any]]:
    """제안 목록(새 것부터) — ADMIN 화면 재료(가린 글 · 숫자 · 코드)."""
    doc = _doc(session.get(SystemSetting, PROPOSALS_KEY, populate_existing=True))
    return list(reversed(doc["proposals"]))


def _apply(session: Any, proposal: dict[str, Any], *, user: Any, now: datetime.datetime) -> int:
    """승인한 안을 회사 지식에 반영한다(지식 문서는 반영이 표에서 다시 쓴다 — 커밋은 부르는 쪽). 그 브랜드 문서 버전을 돌려준다.

    Raises:
        BrainError: 공통 항목 · 표에 항목 없음 · 문서가 표와 다름 · 버전 충돌 등(반영 동작이 멈춤).
    """
    return apply_fix(session, brand=proposal["brand"], fix_id=str(proposal["id"]), item_id=proposal.get("item_id"),
                     intent=proposal.get("intent"), text=proposal["proposed_text"], actor=user,
                     today=get_today_kst().isoformat(), now=naive_utc(now))


def decide(session: Any, proposal_id: Any, *, decision: Any, user: Any, note: Any,
           now: datetime.datetime) -> Decision:
    """사장님(ADMIN) 결정 한 번 — 승인이면 회사 지식 반영(+ 지식 문서 새 판), 거절이면 한 줄 까닭 · 지문. 커밋한다.

    결정한 사람은 ``user``(로그인한 사용자 — 부르는 라우트가 넘긴다)에서만 받는다. ADMIN 이 아니면 403.
    """
    if user is None or getattr(user, "role", None) != "ADMIN" or not getattr(user, "is_active", True):
        return Decision("forbidden", 403)
    if decision not in ("approve", "reject") or not isinstance(proposal_id, str):
        return Decision("bad_request", 400)
    row = _locked(session)
    doc = _doc(row)
    proposal = next((p for p in doc["proposals"] if p.get("id") == proposal_id), None)
    if proposal is None:
        session.rollback()
        return Decision("not_found", 404)
    if proposal.get("state") != STATE_PENDING:
        session.rollback()
        return Decision("already", 409)
    version = None
    if decision == "approve":
        try:
            version = _apply(session, proposal, user=user, now=now)
        except TemplateFixCommonError:
            session.rollback()
            return Decision("common_item", 409)
        except BrainError:
            session.rollback()
            return Decision("apply_failed", 409)
    else:
        doc["rejected"] = [*doc["rejected"], proposal["print"]][-MAX_PROPOSALS:]
        proposal["decision_note"] = (note.strip().splitlines() or [""])[0][:MAX_NOTE] if isinstance(note, str) else ""
    proposal.update(state=STATE_APPROVED if version is not None else STATE_REJECTED, decided_by_user_id=int(user.id),
                    decided_at=now.isoformat(), applied_version=version)
    _put(row, doc)
    session.add(SecurityLog(user_id=int(user.id), action="CS_AGENT_FIX_DECIDE", target_type="cs_agent_fix_proposal",
                            message=f"CS_AGENT_FIX_DECIDE id={proposal_id} decision={decision} version={version}",
                            detail={"decision": decision, "version": version}))
    session.commit()
    return Decision("approved" if version is not None else "rejected", 200, version)

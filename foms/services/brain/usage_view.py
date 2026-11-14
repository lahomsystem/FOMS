"""지식 카드 '쓰인 곳'(설계서 2026-11-14-foms-graft 3.8 ``GET /api/brain/items/<키>/usage``) — **읽기만**.

접목판 ``erp_read`` 스위치가 켜진 사람에게만 API 가 부른다. 재료는 쓰인 곳 표 ``brain_usage_events``
(:mod:`.usage_events` — 상담 초안 · 할 일 제안 · 물어보기가 근거로 쓴 키마다 한 줄)다. 합 표 ``brain_usage`` 는 보지 않는다.

- **수**: 지난 14일 읽은 쪽마다(:func:`.usage_events.uses_window`).
- **최근 네 줄**: 가린 글만 — 상담 차례는 ``masked_question`` 앞부분 + 끝난 꼴, 할 일 제안은 제목(할 일 이름 · 주문 번호) + 상태,
  물어보기는 가린 질문 앞부분 + 모름 여부. 글은 한 번 더 가림 검사를 지난 것만 싣는다(걸리면 빈 글). 묻는 사람 · 보낸 직원
  번호는 싣지 않는다. **볼 수 없는 할 일 제안은 줄에 없다**(설계서 3.5 — ``actions`` 스위치 · 정책 · 주문 읽기 권한).
- **이어진 ERP 물건**: 적용 대상 제품 라인 → 주문 품목(이름으로 이어짐 — 그 이름이 든 진행 중 주문 수는 **세지 않는다**: 색인 없는
  글자 찾기가 된다) · 공정 단계 → ERP 단계 이름 짝. 항목 자신이 제품 라인 · 공정 단계여도 같다.
- 항목을 볼 수 없거나 없으면 ``None``(404 — 둘을 가르지 않는다).
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainLink, BrainObject, BrainQuestion
from foms.persistence.graft.models import ErpActionProposal
from foms.services.ai_staff.registry import AGENTS, agent_of
from foms.services.brain.labels import pref_of
from foms.services.brain.read import current_item, effective_clauses
from foms.services.brain.scope import Viewer
from foms.services.brain.store import in_force, is_current
from foms.services.brain.usage_events import READER_CHATBOT, READER_CS_DRAFT, recent_uses, uses_window
from foms.services.cs_agent.masking import leak_counts
from foms.services.erp_actions.registry import ACTIONS
from foms.services.erp_ontology.objects import get_type
from foms.services.graft_flags import enabled as graft_enabled
from foms.services.orders.erp_policy_constants import STAGE_LABELS
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy, user_can_read_order
from models import CsAgentTurn, Order

__all__ = ["RECENT", "USAGE_DAYS", "item_usage"]

USAGE_DAYS, RECENT, _SCAN, _TEXT_CHARS, _MAX_LINKS = 14, 4, 12, 60, 8
_KST = datetime.timedelta(hours=9)
_READER_LABELS = {READER_CS_DRAFT: AGENTS["cs"].label, READER_CHATBOT: AGENTS["ask"].label}
#: 상담 차례 끝난 꼴 → (화면 말, 꼬리표 색 갈래). 아직 끝나지 않은 차례는 '초안'.
_TURN_STATES = {"as_is": ("보냄", "success"), "edited": ("고쳐 보냄", "primary"), "direct": ("직접 답함", "warning"),
                "copied": ("복사함", "primary"), "discarded": ("버림", "danger")}
_PROPOSAL_STATES = {"open": ("승인 대기", "primary"), "executing": ("실행 중", "primary"), "executed": ("승인", "success"),
                    "failed": ("실패", "danger"), "rejected": ("거절", "danger"), "expired": ("기간 끝남", "warning"),
                    "superseded": ("새 제안으로 바뀜", "warning")}
_LINK_KINDS = ("applies_to", "at_step")


def _safe(text: Any, limit: int = _TEXT_CHARS) -> str:
    """가린 글 앞부분 — 한 번 더 가림 검사를 지나야 싣는다(걸리면 빈 글)."""
    body = " ".join(str(text or "").split())
    short = body[:limit] + ("…" if len(body) > limit else "")
    return "" if any(leak_counts(short).values()) else short


def _ids(uses: Iterable[Any], kind: str) -> list[int]:
    """그 종류 줄의 번호(정수인 것만)."""
    return [int(use.ref_id) for use in uses if use.ref_kind == kind and str(use.ref_id).isdigit()]


def _proposal_visible(session: Any, user: Any, row: ErpActionProposal) -> bool:
    """이 사람이 그 제안을 볼 수 있나(설계서 3.5) — ``actions`` 스위치 · 할 일 정책 · 주문 읽기 권한."""
    spec = ACTIONS.get(row.action)
    policy = POLICY_REGISTRY.get(spec.policy_id) if spec is not None and spec.policy_id else None
    if policy is None or not graft_enabled("actions", user) or not evaluate_policy(policy, user).allowed:
        return False
    if row.order_id is None:
        return True
    order = session.get(Order, int(row.order_id))
    return order is not None and user_can_read_order(user, order)


def _turn_row(turn: Any) -> tuple[str, str, str, str]:
    """상담 차례 → (읽은 쪽 이름, 글, 상태, 색 갈래)."""
    state, tone = _TURN_STATES.get(turn.outcome or "", ("초안", "primary"))
    return _READER_LABELS[READER_CS_DRAFT], _safe(turn.masked_question), state, tone


def _proposal_row(row: ErpActionProposal) -> tuple[str, str, str, str]:
    """할 일 제안 → (제안한 AI 직원 이름, 제목, 상태, 색 갈래)."""
    spec = ACTIONS.get(row.action)
    agent = agent_of(row.proposed_by)
    title = (spec.label if spec is not None else "할 일") + (f" · 주문 #{row.order_id}" if row.order_id else "")
    state, tone = _PROPOSAL_STATES.get(row.status, ("승인 대기", "primary"))
    return agent.label if agent is not None else "사람", title, state, tone


def _question_row(row: BrainQuestion) -> tuple[str, str, str, str]:
    """물어보기 질문 → (읽은 쪽 이름, 가린 질문, 상태, 색 갈래). 묻는 사람은 싣지 않는다."""
    state, tone = ("모름", "warning") if row.unknown else ("답함", "success")
    return _READER_LABELS[READER_CHATBOT], _safe(row.masked_question), state, tone


def _resolved(session: Any, user: Any, uses: list[Any]) -> dict[tuple[str, str], tuple[str, str, str, str]]:
    """(종류, 번호) → (이름, 글, 상태, 색) — 종류마다 질의 한 번. 볼 수 없는 제안 · 없는 줄은 빠진다."""
    out: dict[tuple[str, str], tuple[str, str, str, str]] = {}
    if ids := _ids(uses, "cs_turn"):
        for turn in session.execute(select(CsAgentTurn).where(CsAgentTurn.id.in_(ids))).scalars():
            out[("cs_turn", str(turn.id))] = _turn_row(turn)
    if ids := _ids(uses, "proposal"):
        for row in session.execute(select(ErpActionProposal).where(ErpActionProposal.id.in_(ids))).scalars():
            if _proposal_visible(session, user, row):
                out[("proposal", str(row.id))] = _proposal_row(row)
    if ids := _ids(uses, "question"):
        for row in session.execute(select(BrainQuestion).where(BrainQuestion.id.in_(ids))).scalars():
            out[("question", str(row.id))] = _question_row(row)
    return out


def _recent(session: Any, user: Any, key: str) -> list[dict[str, Any]]:
    """최근 줄 :data:`RECENT` 개(새것 먼저) — 글을 찾을 수 없거나 볼 수 없는 줄은 건너뛴다."""
    uses = recent_uses(session, key, _SCAN)
    found = _resolved(session, user, uses)
    rows = []
    for use in uses:
        hit = found.get((use.ref_kind, str(use.ref_id)))
        if hit is None:
            continue
        label, text, state, tone = hit
        rows.append({"day": (use.used_at + _KST).date().isoformat(), "reader": use.reader, "agent_label": label,
                     "text": text, "state": state, "tone": tone})
        if len(rows) >= RECENT:
            break
    return rows


def _erp_link(item_type: str, name: str, payload: Any) -> Optional[dict[str, Any]]:
    """제품 라인 · 공정 단계 항목 → 이어진 ERP 물건 한 줄(그 밖 유형은 ``None``)."""
    if item_type == "product_line":
        target = get_type("erp:order_item")
        return {"rel": "applies_to", "type": target.type, "type_label": target.label, "label": name,
                "note": "주문 품목 이름과 이어져요"}
    stage = payload.get("erp_stage") if isinstance(payload, dict) else None
    if item_type == "process_step" and stage in STAGE_LABELS:
        target = get_type("erp:order")
        return {"rel": "at_step", "type": target.type, "type_label": target.label, "label": name,
                "note": f"ERP 단계 · {STAGE_LABELS[stage]}", "stage": stage}
    return None


def _erp_links(session: Any, viewer: Viewer, item: dict[str, Any], today: datetime.date) -> list[dict[str, Any]]:
    """항목 자신 + '적용 대상' · '걸린 공정 단계' 링크 끝(볼 수 있는 · 효력 있는 항목만)의 ERP 물건 짝."""
    own = _erp_link(item["type"], pref_of(item.get("name") or "", item.get("payload")), item.get("payload"))
    rows = [own] if own is not None else []
    linked = session.execute(
        select(BrainObject.item_type, BrainObject.name, BrainObject.payload)
        .join(BrainLink, BrainLink.to_key == BrainObject.item_key)
        .where(BrainLink.from_key == item["key"], BrainLink.kind.in_(_LINK_KINDS), is_current(BrainLink),
               in_force(BrainLink, today), BrainObject.item_type.in_(("product_line", "process_step")),
               *effective_clauses(viewer, today))
        .order_by(BrainObject.item_key).limit(_MAX_LINKS)).all()
    for item_type, name, payload in linked:
        row = _erp_link(item_type, pref_of(name, payload), payload)
        if row is not None:
            rows.append(row)
    return rows[:_MAX_LINKS]


def item_usage(session: Any, viewer: Viewer, user: Any, key: str, *, today: datetime.date,
               now_utc: datetime.datetime) -> Optional[dict[str, Any]]:
    """'쓰인 곳' 한 덩어리 — 볼 수 없거나 없는 항목이면 ``None``.

    Args:
        session: DB 세션(읽기만).
        viewer: 화면을 연 사람의 보기 범위.
        user: 로그인 사용자(할 일 제안을 볼 수 있나 판정).
        key: 지식 항목 키.
        today: 한국 오늘(유효 기간 · 링크).
        now_utc: 지금(UTC naive — 지난 14일 기준).

    Returns:
        ``{"days", "by_reader", "recent", "erp_links"}`` 또는 ``None``.
    """
    item = current_item(session, viewer, key, today)
    if item is None:
        return None
    return {"days": USAGE_DAYS, "by_reader": uses_window(session, key, USAGE_DAYS, now=now_utc),
            "recent": _recent(session, user, key), "erp_links": _erp_links(session, viewer, item, today)}

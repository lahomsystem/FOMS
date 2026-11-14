"""ERP 할 일 제안 화면 값 — 수 · 주문 칩 · 승인 대기 카드 · 자세히(설계서 2026-11-14-foms-graft 3.5 · 3.6 · 3.11).

- **볼 수 없는 제안은 질의 단계에서 거른다**: 이 사람이 실행할 수 있는 할 일(:func:`.access.runnable_actions`) · 지워지지 않은
  주문 · (켜진 프리랜서면) 연결 표의 자기 주문만. 수 · 칩 · 카드 어디에도 남의 제안이 섞이지 않는다.
- 수(:func:`badge`)는 ERP 질의 하나(할 일별 수) + 회사 지식 화면을 여는 사람만 지금 제안함 수(:func:`inbox_counts`).
- 주문 칩(:func:`open_for_orders`)은 주문 번호 100개까지 질의 하나(``in_``).
- 카드는 저장된 미리 보기(제안 때 계산)를 보이고, 지금 주문으로 다시 계산한 '지금' 값이 다르면 ``base_changed`` 를 켠다
  (승인하면 409 ``ACTION_BASE_CHANGED`` 와 새 카드). 근거 칩 가운데 보는 사람이 볼 수 없는 회사 지식 항목은 뺀다.
- 글은 저장할 때 가림 검사를 지난 글 · 코드가 정한 말 · 날짜뿐이다. 시간은 한국 시간 글('YYYY-MM-DD HH:MM').
- 나중에(``snoozed_until``)로 접힌 제안은 수 · 칩에서 빼고, 승인 대기 카드에는 ``snoozed`` 로 표시해 따로 센다.
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional
from urllib.parse import quote

from sqlalchemy import false, func, or_, select

from foms.persistence.brain.models import BrainObject
from foms.persistence.graft.models import ErpActionProposal
from foms.services.ai_staff.registry import agent_of
from foms.services.brain.access import screen_viewer
from foms.services.brain.inbox import inbox_counts
from foms.services.brain.scope import scope_clause, viewer_of
from foms.services.brain.store import is_current
from foms.services.datetime_kst import format_datetime_kst, now_utc_naive
from foms.services.erp_actions import preview as fns
from foms.services.erp_actions.access import can_run, runnable_actions, scoped_reader
from foms.services.erp_actions.lifecycle import DECIDED_APPROVE, DECIDED_EDIT, DECIDED_REJECT
from foms.services.erp_actions.registry import (
    ACTIONS, MODE_RUN, REJECT_CODES, REJECT_LABELS, STATUS_FAILED, STATUS_OPEN,
)
from foms.services.erp_ontology.read import order_id_of
from foms.services.graft_flags import enabled
from foms.services.orders.change_reason import REASON_CODES, REASON_LABELS
from models import Order, OrderFreelancerLink

__all__ = [
    "AGENT_KEYS", "MAX_ORDER_IDS", "RATE_DAYS", "approval_rate", "badge", "card", "detail", "inbox", "open_for_orders",
    "title_of",
]

MAX_ORDER_IDS = 100
RATE_DAYS = 14
INBOX_LIMIT = 200
EST_CARD_SECONDS = 30
AGENT_KEYS: tuple[str, ...] = ("cs", "schedule", "ops")
_ACTIONABLE = (STATUS_OPEN, STATUS_FAILED)
_TITLE_LIMIT = 80
_SOURCE_LABELS = {"cs_turn": "손님 상담에서 나옴", "sweep": "훑기 규칙에서 나옴"}


def _now(now: Optional[datetime.datetime]) -> datetime.datetime:
    return now if now is not None else now_utc_naive()


def _scoped(query: Any, user: Any, statuses: Iterable[str]) -> Any:
    """볼 수 있는 제안만 — 실행할 수 있는 할 일 · 지워지지 않은 주문 · (프리랜서면) 자기 주문."""
    query = query.join(Order, Order.id == ErpActionProposal.order_id).where(
        ErpActionProposal.action.in_(runnable_actions(user)), ErpActionProposal.status.in_(tuple(statuses)),
        Order.not_deleted_filter())
    reader = scoped_reader(user)
    if reader is not None:
        query = query.where(ErpActionProposal.order_id.in_(
            select(OrderFreelancerLink.order_id).where(OrderFreelancerLink.user_id == reader)))
    return query


def _awake(now: datetime.datetime) -> Any:
    """'나중에'로 접히지 않은 제안 조건."""
    return or_(ErpActionProposal.snoozed_until.is_(None), ErpActionProposal.snoozed_until <= now)


def _rows_label(rows: list[dict[str, Any]]) -> list[tuple[Any, Any]]:
    return [(item.get("field"), item.get("before")) for item in rows or []]


def title_of(row: ErpActionProposal) -> str:
    """카드 제목 — '<할 일> — #<주문> <지금> → <승인하면>'(지금이 없으면 승인하면 값만)."""
    spec = ACTIONS.get(row.action)
    first = (row.preview or [{}])[0] if row.preview else {}
    head = f"{spec.label if spec else row.action} — #{row.order_id}"
    before, after = str(first.get("before") or ""), str(first.get("after") or "")
    if before and before != fns.NONE_LABEL and after:
        text = f"{head} {before} → {after}"
    else:
        text = f"{head} {after}".strip()
    return text[:_TITLE_LIMIT]


def _visible_brain_keys(session: Any, user: Any, rows: Iterable[ErpActionProposal]) -> set[str]:
    """근거 칩의 회사 지식 키 가운데 이 사람이 볼 수 있는 것(지금 판 · 보기 범위 — 질의 하나)."""
    keys = sorted({str(item.get("ref")) for row in rows for item in (row.evidence or [])
                   if isinstance(item, dict) and item.get("kind") == "brain"})
    if not keys:
        return set()
    viewer = viewer_of(user)
    clause = scope_clause(viewer, BrainObject.visibility) if viewer.internal else false()
    query = select(BrainObject.item_key).where(BrainObject.item_key.in_(keys), is_current(BrainObject), clause)
    return set(session.execute(query).scalars())


def _chip(item: dict[str, Any], order_id: Optional[int]) -> dict[str, Any]:
    """근거 칩 — 종류 · 이름 · 여는 주소(회사 지식 카드 · 주문 화면 — 상담 차례는 주소 없음)."""
    kind, ref = item.get("kind"), str(item.get("ref") or "")
    href = None
    if kind == "brain":
        href = "/brain/items/" + quote(ref, safe="/")
    elif kind in ("order", "visit"):
        target = (order_id_of(ref) or (int(ref) if ref.isdigit() else None)) if kind == "order" else order_id
        href = f"/erp/orders/{target}" if target else None
    return {"kind": kind, "label": str(item.get("label") or ""), "href": href}


def card(row: ErpActionProposal, order: Any, now: datetime.datetime,
         brain_keys: Optional[set[str]] = None) -> dict[str, Any]:
    """카드 하나(설계서 3.6 카드 칸 + ``status`` · ``snoozed``). ``brain_keys`` 밖의 회사 지식 근거는 뺀다."""
    spec, agent = ACTIONS[row.action], agent_of(row.proposed_by)
    stored = list(row.preview or [])
    first = stored[0] if stored else {}
    fresh = fns.preview(row.action, order, row.params or {}) if order is not None else stored
    shown = brain_keys if brain_keys is not None else set()
    evidence = [item for item in (row.evidence or []) if isinstance(item, dict)
                and (item.get("kind") != "brain" or str(item.get("ref")) in shown)]
    return {
        "id": row.id, "action": row.action, "action_label": spec.label, "agent": agent.key if agent else "",
        "agent_label": agent.label if agent else "", "title": title_of(row),
        "created_at": format_datetime_kst(row.created_at, "%Y-%m-%d %H:%M") if row.created_at else None,
        "order_id": row.order_id, "order_href": f"/erp/orders/{row.order_id}" if row.order_id else None,
        "field": str(first.get("field") or ""), "before": str(first.get("before") or ""),
        "after": str(first.get("after") or ""), "evidence": [_chip(item, row.order_id) for item in evidence],
        "level": row.level, "mode": spec.mode, "phone_ok": spec.phone_ok,
        "base_changed": _rows_label(fresh) != _rows_label(stored), "status": row.status,
        "snoozed": bool(row.snoozed_until and row.snoozed_until > now),
    }


def badge(session: Any, user: Any, *, now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """위 아이콘 · 레일 · 폰 칸 수 — ``{"on", "actions", "knowledge", "total", "labels"}``(이 사람 기준).

    ERP 수는 질의 하나(할 일별 수 — 접히지 않은 열림 · 실패). 회사 지식 수는 지식 화면을 여는 사람만 지금 제안함 카드 수.
    """
    moment = _now(now)
    rows = session.execute(_scoped(
        select(ErpActionProposal.action, func.count(ErpActionProposal.id)), user, _ACTIONABLE)
        .where(_awake(moment)).group_by(ErpActionProposal.action)).all() if runnable_actions(user) else []
    counts = {action: int(n) for action, n in rows}
    ranked = sorted(counts, key=lambda name: (-counts[name], list(ACTIONS).index(name)))
    viewer = screen_viewer(user)
    knowledge = int(inbox_counts(session, viewer, moment)["cards"]) if viewer is not None else 0
    actions = sum(counts.values())
    return {"on": {"actions": enabled("actions", user), "pc": enabled("cell_pc", user),
                   "tablet": enabled("cell_tablet", user), "mobile": enabled("cell_mobile", user)},
            "actions": actions, "knowledge": knowledge, "total": actions + knowledge,
            "labels": [ACTIONS[name].label for name in ranked[:3]]}


def open_for_orders(session: Any, user: Any, order_ids: Iterable[int], *,
                    now: Optional[datetime.datetime] = None) -> dict[int, dict[str, Any]]:
    """주문마다 가장 새 제안 하나(접히지 않은 열림 · 실패) — 주문 번호 :data:`MAX_ORDER_IDS` 개까지 질의 하나.

    Returns:
        ``{주문 번호: {"id", "action", "label", "agent_label", "can_decide"}}`` — ``can_decide`` 는 승인 길로 실행되는 할 일인가.
    """
    ids = sorted({int(oid) for oid in order_ids if isinstance(oid, int) and not isinstance(oid, bool) and oid > 0})
    if not ids or not runnable_actions(user):
        return {}
    query = _scoped(select(ErpActionProposal), user, _ACTIONABLE).where(
        ErpActionProposal.order_id.in_(ids[:MAX_ORDER_IDS]), _awake(_now(now)))
    out: dict[int, dict[str, Any]] = {}
    for row in session.execute(query.order_by(ErpActionProposal.created_at.desc(), ErpActionProposal.id.desc())).scalars():
        if row.order_id in out:
            continue
        spec, agent = ACTIONS[row.action], agent_of(row.proposed_by)
        out[row.order_id] = {"id": row.id, "action": row.action, "label": spec.label,
                             "agent_label": agent.label if agent else "", "can_decide": spec.mode == MODE_RUN}
    return out


def _card_seconds(session: Any, now: datetime.datetime) -> int:
    """카드 한 장에 드는 시간(초) — 지난 2주 결정의 본 시간 평균, 없으면 :data:`EST_CARD_SECONDS`."""
    average = session.execute(select(func.avg(ErpActionProposal.view_ms)).where(
        ErpActionProposal.decided_at >= now - datetime.timedelta(days=RATE_DAYS),
        ErpActionProposal.view_ms.isnot(None))).scalar()
    return max(1, int(round(float(average) / 1000))) if average else EST_CARD_SECONDS


def inbox(session: Any, user: Any, now: datetime.datetime) -> dict[str, Any]:
    """승인 대기 'AI 할 일 제안' 칸 — 카드(열림 · 실패, 새것 먼저) · 수 · 거절 까닭 · 어림 초."""
    if not runnable_actions(user):
        rows: list[Any] = []
    else:
        query = _scoped(select(ErpActionProposal, Order), user, _ACTIONABLE)
        rows = session.execute(query.order_by(ErpActionProposal.created_at.desc(), ErpActionProposal.id.desc())
                               .limit(INBOX_LIMIT)).all()
    keys = _visible_brain_keys(session, user, [row for row, _order in rows])
    cards = [card(row, order, now, keys) for row, order in rows]
    awake = [item for item in cards if not item["snoozed"]]
    by_agent = {key: sum(1 for item in awake if item["agent"] == key) for key in AGENT_KEYS}
    return {"cards": cards, "counts": {"total": len(awake), "by_agent": by_agent, "snoozed": len(cards) - len(awake)},
            "reject_codes": [{"value": code, "label": REJECT_LABELS[code]} for code in REJECT_CODES],
            "est_seconds": _card_seconds(session, now) * len(awake) if awake else 0}


def approval_rate(session: Any, proposed_by: str, action: str, now: datetime.datetime,
                  days: int = RATE_DAYS) -> dict[str, Any]:
    """(AI 직원, 할 일)의 지난 ``days`` 일 결정 수 · 승인 수 · 비율(결정 0 이면 ``pct`` 는 ``None``)."""
    rows = session.execute(select(ErpActionProposal.decided_action, func.count(ErpActionProposal.id)).where(
        ErpActionProposal.proposed_by == proposed_by, ErpActionProposal.action == action,
        ErpActionProposal.decided_at >= now - datetime.timedelta(days=days),
        ErpActionProposal.decided_action.in_((DECIDED_APPROVE, DECIDED_EDIT, DECIDED_REJECT)),
    ).group_by(ErpActionProposal.decided_action)).all()
    counts = {name: int(n) for name, n in rows}
    approved = counts.get(DECIDED_APPROVE, 0) + counts.get(DECIDED_EDIT, 0)
    decided = approved + counts.get(DECIDED_REJECT, 0)
    return {"days": days, "decided": decided, "approved": approved,
            "pct": round(100 * approved / decided) if decided else None}


def detail(session: Any, user: Any, proposal_id: Any, now: datetime.datetime) -> Optional[dict[str, Any]]:
    """제안 자세히 — 카드 + 이유 · 바뀌는 칸 · 승인하면 차례로 · 2주 승인율 · 넣을 값 · 기준 판. 볼 수 없으면 ``None``."""
    if isinstance(proposal_id, bool) or not isinstance(proposal_id, int):
        return None
    row = session.get(ErpActionProposal, proposal_id)
    spec = ACTIONS.get(row.action) if row is not None else None
    order = session.get(Order, row.order_id) if row is not None and row.order_id is not None else None
    if row is None or spec is None or not can_run(user, spec, order):
        return None
    params = dict(row.params or {})
    out = card(row, order, now, _visible_brain_keys(session, user, [row]))
    out.update({
        "reason": row.reason or "", "changes": list(row.preview or []),
        "steps": fns.steps(row.action, order, params), "rate": approval_rate(session, row.proposed_by, row.action, now),
        "params": [{"name": p.name, "label": p.label, "kind": p.kind, "value": params.get(p.name, ""),
                    "choices": fns.param_choices(row.action, p.name, order)} for p in spec.params],
        "base_version": row.base_version, "source_label": _SOURCE_LABELS.get(row.source_kind or "", ""),
        "change_reason": {"required": fns.reason_required(row.action, order, params),
                          "codes": [{"value": code, "label": REASON_LABELS[code]} for code in REASON_CODES]},
        "result": row.result if row.status != STATUS_OPEN else None, "error_code": row.error_code,
    })
    return out

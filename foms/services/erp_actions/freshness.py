"""제안 기간 · 낡음 판정 한 곳(설계서 2026-11-14-foms-graft 3.4 '기간 끝남' · 점검 2차 w6-01 ③ · w6-12).

- :func:`expiry` — 기간 끝: 만든 때 + 7일과 날짜들(넣을 값 ``date`` · 할 일의 끝날 :func:`.preview.deadline`)이 끝나는 때(한국
  자정) 가운데 가장 이른 때. 실측 예약 알림톡처럼 넣을 값이 빈 할 일도 실측일이 끝나면 기간이 끝난다.
- :func:`is_stale` — 넣을 값이 없는 할 일(실측 예약 · 시공일 안내 알림톡)의 겹침 열쇠 상황(:func:`.preview.scope` — 실측 일정 ·
  시공일)이 만든 때와 달라졌나. 달라졌으면 옛 제안은 낡은 것이다(승인하면 바뀐 일정으로 나가 버린다).
- :func:`close` — 되맞추기(:func:`.lifecycle.reconcile` — 승인 대기 읽기 · 밤 단계)가 부른다: 기간이 지난 열린 · 실패한 제안은
  ``expired``(밤 정리 전이라도 — 승인 대기 카드가 '보이는데 못 누르는' 채 남지 않게), 낡은 것은 ``superseded``. 다른 쪽이 잠근
  줄(승인 중)은 건너뛴다. 커밋은 부르는 쪽.
- 읽는 길(수 · 칩 · 작은 창 줄)은 기간이 지난 것을 열린 것으로 치지 않는다 — 같은 조건 ``expires_at > 지금``(:mod:`.views` ·
  :mod:`foms.services.cs_agent.send_view`).
"""

from __future__ import annotations

import datetime
from typing import Any, Mapping

from foms.persistence.graft.models import ErpActionProposal
from foms.services.erp_actions import preview as fns
from foms.services.erp_actions.registry import (
    STATUS_EXPIRED, STATUS_FAILED, STATUS_OPEN, STATUS_SUPERSEDED, dedupe_key,
)
from models import Order

__all__ = ["EXPIRED_REASON", "PROPOSAL_DAYS", "close", "expiry", "is_stale", "stale_reason"]

PROPOSAL_DAYS = 7
_KST = datetime.timedelta(hours=9)
_DECIDABLE = (STATUS_OPEN, STATUS_FAILED)
#: 기간이 지난 제안을 승인할 때의 말(F-13 — 밤 정리 전이라도 실행하지 않는다).
EXPIRED_REASON = "기간이 지난 제안이에요 — 새로 불러와 주세요."
_STALE_REASONS = {"send_measure_alimtalk": "제안을 만든 뒤 실측 일정이 바뀌었어요 — 이 제안은 닫았어요.",
                  "send_construction_alimtalk": "제안을 만든 뒤 시공일이 바뀌었어요 — 이 제안은 닫았어요."}


def expiry(now: datetime.datetime, params: Mapping[str, Any], *ends: Any) -> datetime.datetime:
    """기간 끝(UTC naive) — 7일 뒤와 날짜들(넣을 값 ``date`` · ``ends``)이 끝나는 때(한국 자정) 가운데 가장 이른 때.

    Args:
        now: 만든 때(UTC naive). params: 넣을 값(``date`` 가 있으면 그 날). ends: 'YYYY-MM-DD'(못 읽는 값 · ``None`` 은 뺀다).
    """
    limit = now + datetime.timedelta(days=PROPOSAL_DAYS)
    for value in (params.get("date"), *ends):
        try:
            day = datetime.date.fromisoformat(str(value or ""))
        except ValueError:
            continue
        limit = min(limit, datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time()) - _KST)
    return limit


def is_stale(row: Any, order: Any) -> bool:
    """겹침 열쇠 상황이 있는 할 일인데 지금 주문의 상황으로 만든 열쇠가 제안의 열쇠와 다르면 참(실측 일정 · 시공일이 바뀜)."""
    current = fns.scope(row.action, order)
    if current is None or row.order_id is None:
        return False
    return dedupe_key(row.action, int(row.order_id), dict(row.params or {}), current) != row.dedupe_key


def stale_reason(action: str) -> str:
    """낡은 제안을 승인할 때의 말."""
    return _STALE_REASONS.get(action, "제안을 만든 뒤 주문이 바뀌었어요 — 이 제안은 닫았어요.")


def close(session: Any, now: datetime.datetime) -> int:
    """기간이 지난 열린 · 실패한 제안 → ``expired``, 낡은 것 → ``superseded``. 바꾼 줄 수(커밋은 부르는 쪽).

    다른 쪽이 잠근 줄(승인 첫 걸음 중)은 건너뛴다. 낡음 판정은 상황 함수가 있는 할 일의 열린 · 실패한 제안만 읽는다(주문 줄은
    잠그지 않는다).
    """
    due = (session.query(ErpActionProposal)
           .filter(ErpActionProposal.status.in_(_DECIDABLE), ErpActionProposal.expires_at.isnot(None),
                   ErpActionProposal.expires_at <= now)
           .with_for_update(skip_locked=True).all())
    for row in due:
        row.status = STATUS_EXPIRED
    session.flush()
    scoped = [name for name, item in fns.FUNCTIONS.items() if item.scope is not None]
    rows = (session.query(ErpActionProposal, Order).join(Order, Order.id == ErpActionProposal.order_id)
            .filter(ErpActionProposal.status.in_(_DECIDABLE), ErpActionProposal.action.in_(scoped))
            .with_for_update(skip_locked=True, of=ErpActionProposal).all())
    stale = [row for row, order in rows if is_stale(row, order)]
    for row in stale:
        row.status = STATUS_SUPERSEDED
    session.flush()
    return len(due) + len(stale)

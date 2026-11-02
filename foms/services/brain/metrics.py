"""제안 결정 숫자(설계서 7.5 '잘 도는지 숫자로 본다' · 11절 '제안 결정 숫자 넷 기록') — ADMIN 만 보는 요약(읽기만).

새 칸을 만들지 않고 **이미 남는 것**에서 센다:

- 감사 줄(``security_logs`` — :mod:`.apply` · :mod:`.decide` · :mod:`.rollback` 가 숫자 · 코드로만 남김): 결정 시간(화면이 잰
  ``ms``) 분포 · 5초 안 누름 비율 · 제안 나이(``age_s``) 분포 · 고쳐 넣음 · 한꺼번에 · 다시 확인 · 판 되돌리기 · 기간 끝남.
- 제안 표(``brain_changes``): 거절 까닭 분포 · 승인 뒤 되돌림(``rollback_of_version`` 있는 반영 — 항목 되돌리기 · 판 되돌리기).

사람별로 묶지 않는다(직원 감시로 읽히지 않게 — 12절). 숫자만 돌려준다.
"""

from __future__ import annotations

import datetime
from collections import Counter
from typing import Any, Optional

from sqlalchemy import func, select

from foms.persistence.brain.models import BrainChange
from foms.services.brain.constants import CHANGE_APPLIED, CHANGE_REJECTED, FAST_DECISION_MS, REJECT_CODES
from models import SecurityLog

MAX_DAYS = 365
MAX_ROWS = 20000
#: 결정 시간 칸(밀리초 위 끝 — 마지막은 끝 없음).
DECIDE_BUCKETS: tuple[tuple[str, Optional[int]], ...] = (
    ("5초 안", FAST_DECISION_MS), ("5 ~ 30초", 30_000), ("30초 ~ 2분", 120_000), ("2 ~ 10분", 600_000), ("10분 넘음", None))
#: 제안 나이 칸(초 위 끝).
AGE_BUCKETS: tuple[tuple[str, Optional[int]], ...] = (
    ("1시간 안", 3600), ("하루 안", 86_400), ("7일 안", 604_800), ("7일 넘음", None))
_DECISIONS = ("BRAIN_APPLY", "BRAIN_REJECT")


def _bucket(value: int, buckets: tuple[tuple[str, Optional[int]], ...]) -> str:
    """값이 드는 칸 이름."""
    return next(label for label, top in buckets if top is None or value < top)


def _spread(values: list[int], buckets: tuple[tuple[str, Optional[int]], ...]) -> list[dict[str, Any]]:
    """칸별 수(칸 차례 그대로 · 0 칸도)."""
    counts = Counter(_bucket(v, buckets) for v in values)
    return [{"label": label, "count": counts.get(label, 0)} for label, _top in buckets]


def _audit_rows(session: Any, since: datetime.datetime) -> list[tuple[str, dict[str, Any]]]:
    """기간 안 brain 감사 줄(동작 · 숫자 칸)."""
    rows = session.execute(select(SecurityLog.action, SecurityLog.detail).where(
        SecurityLog.action.like("BRAIN\\_%", escape="\\"), SecurityLog.timestamp >= since)
        .order_by(SecurityLog.id.desc()).limit(MAX_ROWS)).all()
    return [(action, detail if isinstance(detail, dict) else {}) for action, detail in rows]


def _decision_numbers(rows: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """결정 수 · 결정 시간 · 5초 안 비율 · 제안 나이(다시 확인 · 판 되돌리기 줄은 결정 시간에 넣지 않는다)."""
    decisions = [(a, d) for a, d in rows if a in _DECISIONS and not d.get("recheck") and not d.get("release_rollback")]
    timed = [int(d["ms"]) for _a, d in decisions if isinstance(d.get("ms"), int)]
    fast = sum(1 for ms in timed if ms < FAST_DECISION_MS)
    return {
        "apply": sum(1 for a, _d in decisions if a == "BRAIN_APPLY"),
        "reject": sum(1 for a, _d in decisions if a == "BRAIN_REJECT"),
        "edited_apply": sum(1 for a, d in decisions if a == "BRAIN_APPLY" and d.get("edited")),
        "bulk_apply": sum(1 for a, d in decisions if a == "BRAIN_APPLY" and d.get("bulk")),
        "timed": len(timed), "fast": fast, "fast_share": round(fast / len(timed), 3) if timed else None,
        "decide_time": _spread(timed, DECIDE_BUCKETS),
        "proposal_age": _spread([int(d["age_s"]) for _a, d in decisions if isinstance(d.get("age_s"), int)],
                                AGE_BUCKETS),
    }


def decision_metrics(session: Any, *, now: datetime.datetime, days: int = 30) -> dict[str, Any]:
    """최근 ``days`` 일 결정 숫자 한 덩어리(ADMIN 화면 · API)."""
    days = max(1, min(int(days), MAX_DAYS))
    since = now - datetime.timedelta(days=days)
    rows = _audit_rows(session, since)
    rejects = dict(session.execute(select(BrainChange.reject_code, func.count()).where(
        BrainChange.status == CHANGE_REJECTED, BrainChange.decided_at >= since)
        .group_by(BrainChange.reject_code)).all())
    item_rollbacks = int(session.execute(select(func.count()).select_from(BrainChange).where(
        BrainChange.status == CHANGE_APPLIED, BrainChange.rollback_of_version.is_not(None),
        BrainChange.decided_at >= since)).scalar_one())
    return {
        "days": days, "decisions": _decision_numbers(rows),
        "rechecks": sum(1 for a, d in rows if a == "BRAIN_APPLY" and d.get("recheck")),
        "rollbacks": {"releases": sum(1 for a, _d in rows if a == "BRAIN_RELEASE_ROLLBACK"),
                      "applied_rollback_changes": item_rollbacks},
        "expired_ai": sum(int(d.get("count") or 0) for a, d in rows if a == "BRAIN_EXPIRE"),
        "reject_reasons": [{"code": code, "count": int(rejects.get(code, 0))} for code in REJECT_CODES],
    }

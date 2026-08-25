"""수집 워터마크 — 어디까지 수집했는지의 정본 (NAVER-INGEST-01 §3.3).

전용 테이블을 만들지 않고 기존 :class:`~models.SystemSetting` 한 행을 쓴다. 단일 행 스칼라
상태이고, 동시 갱신 방어는 그 테이블의 ``version`` optimistic lock 이 이미 제공한다.

핵심 규칙: **워터마크는 성공한 구간 끝까지만 전진한다.** 실패한 구간을 건너뛰고 전진하면
그 구간의 주문이 영영 수집되지 않는다(조용한 유실). 실패는 다음 실행이 같은 구간을 다시
훑도록 두고, 중복 수집은 ``UNIQUE (channel, external_id)`` 가 막는다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.integrations.naver_commerce.client import KST
from models import SystemSetting

logger = logging.getLogger(__name__)

SETTING_KEY = "naver_sync_watermark"

#: 워터마크가 비었을 때(최초 가동) 되돌아볼 기본 구간. 하루치만 본다 — 그보다 과거의
#: 주문은 이미 손으로 입력돼 있어 자동 수집 대상이 아니다.
DEFAULT_LOOKBACK = timedelta(hours=24)

#: 조회 끝을 현재보다 이만큼 앞당긴다. 네이버 쪽 인덱싱 지연으로 "지금"까지 조회하면
#: 경계에 걸친 변경이 다음 구간에서도 안 잡히고 사라질 수 있다.
END_SAFETY_MARGIN = timedelta(minutes=1)


def _row(session: Session) -> Optional[SystemSetting]:
    """워터마크 setting 행(없으면 None)."""
    return session.get(SystemSetting, SETTING_KEY)


def read_state(session: Session) -> dict[str, Any]:
    """저장된 수집 상태를 준다(없으면 빈 dict)."""
    row = _row(session)
    value = row.setting_value if row is not None else None
    return dict(value) if isinstance(value, dict) else {}


def read_watermark(session: Session) -> Optional[datetime]:
    """마지막으로 **성공한** 구간 끝(KST aware). 없으면 None."""
    raw = read_state(session).get("last_success_to")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        logger.warning("[NAVER] 워터마크 파싱 실패(무시하고 기본 구간 사용): %r", raw)
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)


def resolve_window(
    session: Session, *, now: datetime, lookback: timedelta = DEFAULT_LOOKBACK
) -> tuple[datetime, datetime]:
    """이번에 훑을 ``(시작, 끝)`` 구간을 정한다.

    시작은 워터마크(없으면 ``now - lookback``), 끝은 ``now - 안전여유``다. 구간이 24시간을
    넘어도 여기서 자르지 않는다 — 클라이언트가 하루씩 나눠 순회한다.

    Args:
        session: DB 세션.
        now: 현재 시각(KST aware 권장; naive 면 KST 로 간주).
        lookback: 워터마크가 없을 때 되돌아볼 길이.

    Returns:
        ``(start, end)``. ``start >= end`` 면 이번엔 조회할 게 없다는 뜻이다.
    """
    current = now if now.tzinfo else now.replace(tzinfo=KST)
    end = current - END_SAFETY_MARGIN
    start = read_watermark(session) or (current - lookback)
    return (start, end)


def advance(
    session: Session, *, success_to: datetime, summary: Optional[dict] = None,
    now: Optional[datetime] = None,
) -> None:
    """성공한 구간 끝으로 워터마크를 전진시킨다(뒤로 가지 않는다).

    Args:
        session: DB 세션(커밋은 호출자).
        success_to: 성공적으로 훑은 구간의 끝.
        summary: 마지막 실행 집계(관리 화면 표시용).
        now: 기록용 현재 시각.
    """
    aware = success_to if success_to.tzinfo else success_to.replace(tzinfo=KST)
    previous = read_watermark(session)
    if previous is not None and aware <= previous:
        return
    state = read_state(session)
    state["last_success_to"] = aware.isoformat()
    state["last_run_at"] = (now or datetime.now(KST)).isoformat()
    state["last_error"] = None
    if summary is not None:
        state["last_summary"] = summary
    _write(session, state)


def record_failure(session: Session, *, error: str, now: Optional[datetime] = None) -> None:
    """실패를 기록한다. **워터마크는 전진시키지 않는다**(다음 실행이 같은 구간을 재시도)."""
    state = read_state(session)
    state["last_error"] = str(error)[:2000]
    state["last_run_at"] = (now or datetime.now(KST)).isoformat()
    _write(session, state)


def _write(session: Session, state: dict[str, Any]) -> None:
    """setting 행을 만들거나 갱신한다(행이 없으면 생성)."""
    row = _row(session)
    if row is None:
        session.add(SystemSetting(
            setting_key=SETTING_KEY, setting_value=state,
            description="네이버 스마트스토어 수집 워터마크 (NAVER-INGEST-01)",
        ))
    else:
        row.setting_value = state
        row.version = int(row.version or 1) + 1
    session.flush()


__all__ = [
    "DEFAULT_LOOKBACK",
    "END_SAFETY_MARGIN",
    "SETTING_KEY",
    "advance",
    "read_state",
    "read_watermark",
    "record_failure",
    "resolve_window",
]

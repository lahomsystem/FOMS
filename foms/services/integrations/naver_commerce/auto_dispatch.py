"""네이버 발송처리 자동 실행 — 평일 정해진 시각 1회 (NAVER-AUTODISPATCH-01).

사람이 매일 화면에서 "오늘 N집 네이버 발송처리"를 눌러 왔다. 누르는 것을 잊으면 그날
건이 통째로 밀리고, 늦은 발송은 네이버 지연으로 이어진다. 그 누름을 정해진 시각에
대신한다.

**되돌릴 수 없는 조작의 무인화**라 규율이 다섯이다:

1. **대상은 서버가 다시 계산한다** — 수동 라우트와 **같은 함수**
   (:func:`~foms.services.integrations.naver_commerce.bulk_dispatch.select_sendable`).
   기준을 두 벌 두면 화면이 말하는 수와 자동이 보내는 수가 갈린다. 막힌 집(취소·반품
   걸림 · 발주확인 전 · 수집 이상)은 지금처럼 안 나간다.
2. **하루 1회** — 마지막 실행 날짜를 :data:`SETTING_KEY` 에 남긴다. 워커가 재시작하거나
   replica 가 늘어도 같은 날 두 번 나가지 않는다.
3. **영업일만** — :func:`~foms.services.common.business_calendar.is_business_day`
   (주말 + 한국 공휴일). 달력을 새로 만들지 않는다(사용자 결정 2026-09-02).
4. **기본 꺼짐** — ``FOMS_NAVER_AUTO_DISPATCH_ENABLED=1`` 로만 켠다. 기존 일괄 발송
   킬스위치도 함께 본다: 그게 꺼져 있으면 자동도 돌지 않는다(손잡이가 둘로 갈리면
   "껐는데 나갔다"가 생긴다).
5. **말없이 나가지 않는다** — 보낸 집이 있으면 감사 원장 1건 + 관리자 알림 1건.
   보낼 집이 0집이면 조용히 지나간다(사람이 이미 손으로 보낸 날이 그렇다 — 매일 뜨는
   알림은 읽히지 않고, 읽히지 않는 알림은 없는 것과 같다).

**WORKER 전용**이다. 네이버 HTTP 는 워커에서만 나가고(IP 3슬롯 계약), 이 모듈은 큐에
넣기만 한다 — 실제 호출은 기존 ``run_naver_fulfillment_task`` 가 한다.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_kst, now_utc_naive
from models import Notification, SecurityLog, SystemSetting

logger = logging.getLogger(__name__)

#: 마지막 자동 실행 기록을 담는 ``SystemSetting`` 키. 수집 워터마크·백필 상태와 **다른**
#: 행이다 — 한 행을 여럿이 쓰면 한쪽 갱신이 다른 쪽 기록을 지운다.
SETTING_KEY = "naver_auto_dispatch_state"

#: 감사 원장 태그. 수동 실행(``NAVER_INGEST_BULK_DISPATCH_ENQUEUE``)과 **가른다** —
#: 나중에 "이건 사람이 눌렀나 자동인가"를 물을 때 답할 수 있어야 한다.
AUDIT_ACTION = "NAVER_INGEST_BULK_DISPATCH_AUTO"

#: 결과 알림 종류.
NOTIFICATION_TYPE = "NAVER_AUTO_DISPATCH"


def read_state(session: Session) -> dict[str, Any]:
    """저장된 자동 실행 상태(없으면 빈 dict).

    Args:
        session: DB 세션.

    Returns:
        상태 dict.
    """
    row = session.get(SystemSetting, SETTING_KEY)
    value = row.setting_value if row is not None else None
    return dict(value) if isinstance(value, dict) else {}


def _write_state(session: Session, state: dict[str, Any]) -> None:
    """상태 행을 만들거나 갱신한다(커밋은 호출자)."""
    row = session.get(SystemSetting, SETTING_KEY)
    if row is None:
        session.add(SystemSetting(
            setting_key=SETTING_KEY, setting_value=state,
            description="네이버 발송처리 자동 실행 상태 (NAVER-AUTODISPATCH-01)",
        ))
    else:
        row.setting_value = state
        row.version = int(row.version or 1) + 1
    session.flush()


def is_enabled() -> bool:
    """자동 실행이 켜져 있나.

    두 손잡이를 **모두** 본다: 기능 자체의 킬스위치(일괄 발송처리)와 자동 실행 스위치.
    자동만 켜고 기능을 끄면 "껐는데 나갔다"가 되고, 그 반대는 수동만 남는다(의도된 상태).

    Returns:
        둘 다 켜져 있으면 True.
    """
    from foms.services.feature_flags import env_bool, is_naver_bulk_dispatch_enabled

    return bool(is_naver_bulk_dispatch_enabled()) and bool(
        env_bool("FOMS_NAVER_AUTO_DISPATCH_ENABLED"))


def _already_ran(session: Session, day: str) -> bool:
    """오늘 이미 돌았나(하루 1회 계약)."""
    return str(read_state(session).get("last_run_date") or "") == day


def _record(session: Session, *, day: str, now: datetime, outcome: str,
            summary: Optional[dict[str, Any]] = None) -> None:
    """실행 결과를 상태에 남긴다.

    **건너뛴 날도 기록한다** — "안 돌았다"와 "돌았는데 보낼 게 없었다"를 나중에 갈라야
    한다. 다만 ``last_run_date`` 는 실제로 판정까지 간 날에만 찍는다.

    Args:
        session: DB 세션(커밋은 호출자).
        day: ``YYYY-MM-DD``.
        now: 실행 시각.
        outcome: ``"sent"`` / ``"no_target"`` / ``"holiday"`` / ``"disabled"`` 등.
        summary: 집계(있으면 함께 저장).
    """
    state = read_state(session)
    state["last_outcome"] = outcome
    state["last_checked_at"] = now.isoformat()
    if outcome in {"sent", "no_target", "queue_failed"}:
        state["last_run_date"] = day
        state["last_run_at"] = now.isoformat()
    if summary is not None:
        state["last_summary"] = summary
    state["rev"] = int(state.get("rev") or 0) + 1
    _write_state(session, state)


def _notify(session: Session, *, day: str, queued: int, blocked: int, truncated: bool,
            now: datetime) -> int:
    """자동 발송 결과를 관리자에게 알린다 — ``ROLE`` 알림 **1건**.

    관리자 수만큼 복제하지 않는다(NOTIF-ROLE-01). 수신자별 읽음 상태는
    :func:`~foms.services.notifications.recipients.fan_out_new_notification` 이 만든다.

    Args:
        session: DB 세션(커밋은 호출자).
        day: ``YYYY-MM-DD``.
        queued: 큐에 넣은 집 수.
        blocked: 막혀서 안 보낸 집 수.
        truncated: 상한에 걸려 잘렸는가.
        now: 알림 생성 시각(UTC naive).

    Returns:
        만든 알림 row 수(0 또는 1).
    """
    from foms.services.notifications.recipients import fan_out_new_notification

    parts = [f"오늘 실측한 네이버 건 {queued}집을 자동 발송처리했습니다."]
    if blocked:
        parts.append(f"막힌 집 {blocked}집은 보내지 않았습니다 — 화면에서 사유를 확인하세요.")
    if truncated:
        parts.append("대상이 상한을 넘어 일부만 보냈습니다 — 남은 건은 화면에서 눌러 주세요.")
    notification = Notification(
        target_type="ROLE", target_role="ADMIN",
        notification_type=NOTIFICATION_TYPE, is_urgent=False,
        title=f"네이버 자동 발송처리 {queued}집 ({day})",
        message=" ".join(parts), created_at=now,
    )
    session.add(notification)
    session.flush()
    fan_out_new_notification(session, notification)
    return 1


def run_auto_dispatch(session: Session, *, now: Optional[datetime] = None,
                      on_date: Optional[str] = None, force: bool = False) -> dict[str, Any]:
    """오늘 보낼 수 있는 집을 자동으로 발송처리 큐에 넣는다(커밋은 이 함수가 한다).

    Args:
        session: DB 세션.
        now: 기준 시각(KST aware 권장, 테스트 주입).
        on_date: 대상 날짜(생략하면 ``now`` 의 날짜).
        force: True 면 영업일·하루1회 규칙을 건너뛴다(운영자가 러너를 ``--once`` 로
            직접 돌리는 경우 — 사람이 지금 그러기로 한 것이라 막지 않는다).
            **기능 스위치는 force 로도 못 넘는다.**

    Returns:
        ``{"outcome", "date", "queued", "blocked", "total", "truncated", "failed"}``.
    """
    from foms.services.common.business_calendar import is_business_day
    from foms.services.integrations.naver_commerce.bulk_dispatch import (
        BULK_DISPATCH_LIMIT, build_day_summary, select_sendable,
    )
    from foms.services.jobs.queue import enqueue_naver_fulfillment

    current = now or now_kst()
    day = on_date or current.strftime("%Y-%m-%d")
    result: dict[str, Any] = {"outcome": "", "date": day, "queued": 0, "blocked": 0,
                              "total": 0, "truncated": False, "failed": 0}

    if not is_enabled():
        result["outcome"] = "disabled"
        return result
    if not force and not is_business_day(date.fromisoformat(day)):
        # 주말·공휴일은 대상을 세지도 않는다 — 세면 "보낼 게 있었다"는 기록이 남아
        # 다음날 판단을 흐린다.
        logger.info("[NAVER][자동발송] %s 은 영업일이 아니다 — 건너뛴다", day)
        _record(session, day=day, now=current, outcome="holiday")
        session.commit()
        result["outcome"] = "holiday"
        return result
    if not force and _already_ran(session, day):
        logger.info("[NAVER][자동발송] %s 은 이미 실행했다 — 건너뛴다", day)
        result["outcome"] = "already_ran"
        return result

    targets, total = select_sendable(session, on_date=day)
    # 막힌 집은 "보낼 수 있는 집"에서 빠진 나머지다. 세는 이유는 알림이 그 수를 말해야
    # 사람이 화면을 열어 사유를 보기 때문이다 — 침묵하면 안 나간 집이 없는 것처럼 읽힌다.
    blocked = sum(1 for target in build_day_summary(session, on_date=day)
                  if target.pending_link_ids and not target.eligible)
    result["total"] = total
    result["blocked"] = blocked
    if not targets:
        # 사람이 이미 손으로 보냈거나, 오늘 네이버 집이 없다. 둘 다 조용히 지나간다.
        logger.info("[NAVER][자동발송] %s 보낼 집 0 (막힌 집 %d) — 조용히 지나간다", day, blocked)
        _record(session, day=day, now=current, outcome="no_target",
                summary={"queued": 0, "blocked": blocked, "total": 0})
        session.commit()
        result["outcome"] = "no_target"
        return result

    queued = [target.link_id for target in targets
              if enqueue_naver_fulfillment(target.link_id, "dispatch", None)]
    failed = len(targets) - len(queued)
    truncated = total > len(targets)
    result.update({"queued": len(queued), "failed": failed, "truncated": truncated})
    if not queued:
        # 큐가 죽었으면 **성공한 척하지 않는다.** 날짜를 찍어 오늘을 닫아 버리면 큐가
        # 살아난 뒤에도 자동은 내일까지 아무것도 안 한다 — 그래서 outcome 만 남긴다.
        logger.error("[NAVER][자동발송] %s 큐에 한 집도 넣지 못했다(대상 %d집)", day, total)
        _record(session, day=day, now=current, outcome="queue_failed",
                summary={"queued": 0, "blocked": blocked, "total": total, "failed": failed})
        state = read_state(session)
        state.pop("last_run_date", None)  # 오늘을 닫지 않는다 — 다음 창에서 다시 시도한다
        _write_state(session, state)
        session.commit()
        result["outcome"] = "queue_failed"
        return result

    session.add(SecurityLog(
        user_id=None,  # 사람이 아니라 스케줄이 한 일이다(행위자 없음이 사실이다)
        message=(f"네이버 자동 발송처리 ({len(queued)}집 / 대상 {total}집"
                 + (f" · 상한 {BULK_DISPATCH_LIMIT}집으로 잘림" if truncated else "")
                 + (f" · 큐 실패 {failed}집" if failed else "") + ")"),
        action=AUDIT_ACTION,
        detail={"date": day, "link_ids": queued, "total": total, "blocked": blocked,
                "failed": failed, "truncated": truncated},
    ))
    _notify(session, day=day, queued=len(queued), blocked=blocked, truncated=truncated,
            now=now_utc_naive())
    _record(session, day=day, now=current, outcome="sent",
            summary={"queued": len(queued), "blocked": blocked, "total": total,
                     "failed": failed, "truncated": truncated})
    session.commit()
    logger.info("[NAVER][자동발송] %s 요청 %d집 / 대상 %d집 · 막힌 집 %d · 잘림=%s",
                day, len(queued), total, blocked, truncated)
    result["outcome"] = "sent"
    return result


__all__ = [
    "AUDIT_ACTION",
    "NOTIFICATION_TYPE",
    "SETTING_KEY",
    "is_enabled",
    "read_state",
    "run_auto_dispatch",
]

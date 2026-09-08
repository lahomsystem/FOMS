"""워커 정지 감시 — 큐가 멎은 것을 사람이 화면에서 먼저 발견하지 않게 한다.

2026-09-08 운영 사고: WORKER 컨테이너가 죽어 큐가 11분 멎는 동안 아무도 몰랐다. 사용자가
반응 없는 [발주확인] 버튼을 6번 누르고 나서야 발견됐다. 같은 일이 2026-02(워커 offline),
2026-08-31(SIDEFX 미배포)에도 있었고 **세 번 다 사용자가 먼저 찾았다**.

**감시자가 어디서 도는가가 이 모듈의 핵심 결정이다.** WORKER 안에서 돌면 워커가 죽을 때
같이 죽어 아무 말도 못 한다. 그래서 별도 컨테이너인 SIDEFX(``run_domain_side_effect_outbox``)
에 얹었다 — 5초 루프를 이미 돌고 있고, 판정 재료인 ``side_effect_worker_heartbeats`` 를
이미 읽는다. web 에 얹지 않은 이유는 replica 가 둘이라 같은 알림이 두 번 나가기 때문이다.

판정은 새 규칙을 만들지 않는다. :data:`foms.services.sidefx_worker.WORKER_KIND_SPECS` 의
``max_heartbeat_age`` 가 정본이고 여기서는 그 등록부를 읽기만 한다.
"""
from __future__ import annotations

import datetime
import logging
import os
from typing import Any, Optional

from foms.services.datetime_kst import now_utc_naive
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.sidefx_worker import (
    WORKER_KIND_GEOCODE_SWEEP,
    WORKER_KIND_NAVER_AUTO_DISPATCH,
    WORKER_KIND_NAVER_ORDER_SYNC,
    WORKER_KIND_NAVER_SETTLE_SYNC,
    WORKER_KIND_NOTIFICATION_ESCALATION,
    WORKER_KIND_RQ_WORKER,
    WORKER_KIND_SPECS,
)
from models import Notification, SideEffectWorkerHeartbeat, SystemSetting

logger = logging.getLogger(__name__)

#: WORKER 컨테이너 소속 루프. 이 컨테이너가 죽으면 **여섯이 함께** 멎는다 — 그래서 한 kind 만
#: 보지 않고 묶어서 본다. SIDEFX 소속(DELIVERY/EXPIRY_SCAN/RETENTION)은 감시자 자신이 사는
#: 컨테이너라 여기 넣지 않는다(자기가 죽으면 어차피 아무 말도 못 한다).
WATCHED_KINDS: tuple[str, ...] = (
    WORKER_KIND_RQ_WORKER,
    WORKER_KIND_NAVER_ORDER_SYNC,
    WORKER_KIND_NAVER_AUTO_DISPATCH,
    WORKER_KIND_NAVER_SETTLE_SYNC,
    WORKER_KIND_NOTIFICATION_ESCALATION,
    WORKER_KIND_GEOCODE_SWEEP,
)

#: 마지막으로 알린 상태를 담는 SystemSetting 키. 이 값이 있어야 **전이에서만** 알린다.
SETTING_KEY = "worker_watchdog_state"

#: 알림 유형. push P1 집합에 등재해야 화면을 안 보고 있어도 닿는다(push_sender).
NOTIFICATION_TYPE = "WORKER_STALLED"

#: 게이트 env. 다른 루프와 같은 규율 — 기본은 off 로 두고 운영에서 켠다.
ENABLED_ENV = "FOMS_WORKER_WATCHDOG_ENABLED"

_TRUTHY = frozenset({"1", "true", "yes", "on"})

_TITLE_STALLED = "백그라운드 작업이 멈췄습니다"
_TITLE_RECOVERED = "백그라운드 작업이 다시 돌고 있습니다"


def is_enabled() -> bool:
    """감시자가 켜져 있는가(기본 off)."""
    return (os.environ.get(ENABLED_ENV) or "").strip().lower() in _TRUTHY


def evaluate_worker_health(session: Any, *,
                           now: Optional[datetime.datetime] = None) -> dict:
    """WORKER 소속 루프의 생존을 판정한다(읽기 전용).

    하트비트 **행이 아예 없는** kind 는 stale 로 세지 않는다. 그 루프가 게이트 off 라
    한 번도 안 뜬 경우와 죽은 경우를 표만 보고 구분할 수 없기 때문이다 — 죽은 것으로
    치면 게이트를 꺼 둔 기능마다 알림이 나간다.

    Args:
        session: SQLAlchemy 세션.
        now: 판정 기준 시각(UTC naive). 생략하면 지금.

    Returns:
        ``{"stalled": bool, "stale_kinds": [...], "ages": {kind: seconds}, "checked_at": iso}``.
    """
    now = now or now_utc_naive()
    rows = {hb.worker_kind: hb for hb in session.query(SideEffectWorkerHeartbeat).all()}
    ages: dict[str, int] = {}
    stale: list[str] = []
    for kind in WATCHED_KINDS:
        hb = rows.get(kind)
        if hb is None or hb.last_heartbeat_at is None:
            continue
        age = max(0, int((now - hb.last_heartbeat_at).total_seconds()))
        ages[kind] = age
        if age >= WORKER_KIND_SPECS[kind].max_heartbeat_age:
            stale.append(kind)
    return {"stalled": bool(stale), "stale_kinds": stale, "ages": ages,
            "checked_at": now.isoformat()}


def _read_state(session: Any) -> dict:
    """마지막으로 알린 상태."""
    row = session.get(SystemSetting, SETTING_KEY)
    value = row.setting_value if row is not None else None
    return value if isinstance(value, dict) else {}


def _write_state(session: Any, value: dict) -> None:
    """알린 상태를 남긴다(다음 회차가 전이인지 판정하는 근거)."""
    row = session.get(SystemSetting, SETTING_KEY)
    if row is None:
        session.add(SystemSetting(setting_key=SETTING_KEY, setting_value=value,
                                  description="워커 정지 감시가 마지막으로 알린 상태"))
        return
    row.setting_value = value


def _message(health: dict, *, stalled: bool) -> str:
    """사람이 읽는 한 줄. 무엇이 몇 분째 멎었는지까지 말한다."""
    if not stalled:
        return "멈췄던 백그라운드 작업이 다시 돌기 시작했습니다. 밀려 있던 요청은 순서대로 처리됩니다."
    parts = []
    for kind in health["stale_kinds"]:
        minutes = max(1, round(health["ages"].get(kind, 0) / 60))
        parts.append(f"{kind}({minutes}분째)")
    return ("워커가 응답하지 않아 발주확인·발송처리·정산 동기화 같은 작업이 처리되지 않고 "
            "쌓이는 중입니다 — " + ", ".join(parts) + ". 버튼을 다시 눌러도 소용없습니다.")


def _notify(session: Any, health: dict, *, stalled: bool,
            now: datetime.datetime) -> Optional[int]:
    """관리자 전원에게 알림 1건. 사건 1건 = Notification 1행 + 수신자별 state."""
    notif = Notification(
        order_id=None,
        notification_type=NOTIFICATION_TYPE,
        target_type="ROLE",
        target_role="ADMIN",
        # is_urgent=True 는 에스컬레이션 스윕을 부른다 — 사람이 아니라 인프라 사건이라
        # 상급자 에스컬레이션 대상이 아니다. 대신 push P1 집합으로 화면 밖까지 닿게 한다.
        is_urgent=False,
        title=_TITLE_STALLED if stalled else _TITLE_RECOVERED,
        message=_message(health, stalled=stalled),
        is_read=False,
        created_at=now,
    )
    session.add(notif)
    session.flush()
    fan_out_new_notification(session, notif, actor_user_id=None)
    return int(notif.id)


def run_watchdog_once(session: Any, *, now: Optional[datetime.datetime] = None,
                      notify: bool = True) -> dict:
    """1회 판정. **상태가 바뀔 때만** 알린다.

    같은 상태가 이어지는 동안 조용한 것이 계약이다 — 1분마다 "아직 멎어 있음"을 보내면
    알림 센터가 그 한 종류로 덮여 다른 알림이 안 보인다([[알림 단위]] 함정과 같은 결).

    Args:
        session: SQLAlchemy 세션. 커밋은 **호출부**가 한다.
        now: 판정 기준 시각.
        notify: False 면 판정만 하고 알림을 만들지 않는다(점검·테스트용).

    Returns:
        ``{"health": {...}, "changed": bool, "notification_id": int|None}``.
    """
    now = now or now_utc_naive()
    health = evaluate_worker_health(session, now=now)
    previous = _read_state(session)
    was_stalled = bool(previous.get("stalled"))
    changed = was_stalled != health["stalled"]

    notification_id = None
    if changed and notify:
        notification_id = _notify(session, health, stalled=health["stalled"], now=now)
        logger.warning("[worker-watchdog] 상태 전이: stalled=%s kinds=%s",
                       health["stalled"], health["stale_kinds"])
    if changed:
        _write_state(session, {"stalled": health["stalled"],
                               "stale_kinds": health["stale_kinds"],
                               "changed_at": now.isoformat()})
    return {"health": health, "changed": changed, "notification_id": notification_id}

"""워커 정지 감시 계약 (2026-09-08 사고 후속).

이 감시자가 없던 동안 같은 일이 세 번 났고 **세 번 다 사용자가 화면에서 먼저 발견**했다
(2026-02 워커 offline · 2026-08-31 SIDEFX 미배포 · 2026-09-08 워커 자멸 11분).

여기서 잠그는 것은 넷이다.

1. 감시자는 **WORKER 밖**에서 돈다 — 안에서 돌면 워커가 죽을 때 같이 죽어 아무 말도 못 한다.
2. 알림은 **상태 전이에서만** 나간다 — 1분마다 "아직 멎어 있음"을 보내면 알림 센터가
   그 한 종류로 덮인다.
3. 하트비트 행이 **없는** kind 는 죽은 것으로 세지 않는다 — 게이트를 꺼 둔 루프마다
   알림이 나가면 잡음이 된다.
4. push 는 **rq 를 거치지 않는다** — 알리려는 사실이 "그 큐가 안 돈다" 이기 때문이다.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Optional

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services import worker_watchdog
from foms.services.sidefx_worker import (
    WORKER_KIND_DELIVERY,
    WORKER_KIND_NAVER_ORDER_SYNC,
    WORKER_KIND_RQ_WORKER,
    WORKER_KIND_SPECS,
)
from models import Notification, SideEffectWorkerHeartbeat, SystemSetting, User

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SIDEFX_RUNNER = _REPO_ROOT / "tools" / "ops" / "run_domain_side_effect_outbox.py"
_START_SH = _REPO_ROOT / "start.sh"

_NOW = datetime.datetime(2026, 9, 8, 5, 0, 0)
_BUDGET = WORKER_KIND_SPECS[WORKER_KIND_RQ_WORKER].max_heartbeat_age
#: 2026-09-08 헛알림 당사자. 등록부 900 = 기본 간격 300초 x 3틱인데 운영 간격은 1800초다.
_SYNC_REGISTRY_BUDGET = WORKER_KIND_SPECS[WORKER_KIND_NAVER_ORDER_SYNC].max_heartbeat_age


def _admin(name: str = "감시자관리자") -> int:
    """알림 수신자 1명."""
    user = User(username=f"wd_{name}", password=generate_password_hash("pw"),
                name=name, role="ADMIN", is_active=True)
    db_session.add(user)
    db_session.commit()
    return int(user.id)


def _beat(kind: str, *, age_seconds: int, now: datetime.datetime = _NOW,
          metadata: Optional[dict] = None) -> None:
    """kind 하트비트를 ``now - age_seconds`` 시점으로 찍는다.

    Args:
        kind: worker_kind.
        age_seconds: 지금(``now``)으로부터의 나이(초).
        now: 기준 시각.
        metadata: 루프가 신고하는 ``metadata_json``(예 ``{"interval_seconds": 1800}``).
            생략하면 신고 없음 — 등록부 기본 예산이 그대로 쓰인다.
    """
    stamp = now - datetime.timedelta(seconds=age_seconds)
    hb = db_session.get(SideEffectWorkerHeartbeat, kind)
    if hb is None:
        db_session.add(SideEffectWorkerHeartbeat(worker_kind=kind, last_heartbeat_at=stamp,
                                                 metadata_json=metadata))
    else:
        hb.last_heartbeat_at = stamp
        hb.metadata_json = metadata
    db_session.commit()


def _notif_count() -> int:
    return (db_session.query(Notification)
            .filter(Notification.notification_type == worker_watchdog.NOTIFICATION_TYPE)
            .count())


# --------------------------------------------------------------------------- #
# 1. 판정
# --------------------------------------------------------------------------- #

def test_fresh_heartbeat_is_not_stalled(app):
    """방금 뛴 심장은 멎은 게 아니다."""
    _beat(WORKER_KIND_RQ_WORKER, age_seconds=10)
    health = worker_watchdog.evaluate_worker_health(db_session, now=_NOW)
    assert health["stalled"] is False
    assert health["stale_kinds"] == []


def test_stale_heartbeat_is_stalled_by_the_registry_budget(app):
    """신고가 없는 하트비트는 등록부 바닥값(900)이 그대로 문다.

    운영 rq worker 는 405 를 신고하므로 이 상황이 아니다 — 그 케이스는
    ``test_rq_worker_production_declared_interval_sets_the_budget`` 이 본다.
    """
    _beat(WORKER_KIND_RQ_WORKER, age_seconds=_BUDGET + 1)
    health = worker_watchdog.evaluate_worker_health(db_session, now=_NOW)
    assert health["stalled"] is True
    assert WORKER_KIND_RQ_WORKER in health["stale_kinds"]

    _beat(WORKER_KIND_RQ_WORKER, age_seconds=_BUDGET - 1)
    assert worker_watchdog.evaluate_worker_health(db_session, now=_NOW)["stalled"] is False


def test_missing_heartbeat_row_is_not_counted_as_dead(app):
    """한 번도 안 뜬 루프(게이트 off)와 죽은 루프는 표만 보고 구분할 수 없다."""
    health = worker_watchdog.evaluate_worker_health(db_session, now=_NOW)
    assert health["stalled"] is False, "행이 없는 kind 를 죽은 것으로 셌다"
    assert health["ages"] == {}


def test_sidefx_own_kinds_are_not_watched(app):
    """감시자 자신이 사는 컨테이너의 kind 는 안 본다 — 죽으면 어차피 말을 못 한다."""
    assert WORKER_KIND_DELIVERY not in worker_watchdog.WATCHED_KINDS
    assert WORKER_KIND_RQ_WORKER in worker_watchdog.WATCHED_KINDS


def test_declared_interval_widens_the_watchdog_budget(app):
    """루프가 신고한 간격(1800초)을 감시자도 읽는다 — 2026-09-08 헛알림의 원인이 이것이었다."""
    _beat(WORKER_KIND_NAVER_ORDER_SYNC, age_seconds=1000,
          metadata={"interval_seconds": 1800})
    health = worker_watchdog.evaluate_worker_health(db_session, now=_NOW)
    assert WORKER_KIND_NAVER_ORDER_SYNC not in health["stale_kinds"], (
        "신고 간격 1800초 루프를 나이 1000초에 죽었다고 판정했다(readiness 는 OK 라고 한다)")


def test_rq_worker_production_declared_interval_sets_the_budget(app):
    """운영 rq worker 는 405초를 신고한다 — 예산은 등록부 900 이 아니라 1215초다.

    두 번째 단언이 ``age >= 예산`` 경계 자체를 문다(1215 정확히). 이 테스트가 없으면
    ``>=`` 를 ``>`` 로 바꾸는 변이가 전 테스트를 통과한다.
    """
    _beat(WORKER_KIND_RQ_WORKER, age_seconds=1000, metadata={"interval_seconds": 405})
    health = worker_watchdog.evaluate_worker_health(db_session, now=_NOW)
    assert WORKER_KIND_RQ_WORKER not in health["stale_kinds"], (
        "405 신고를 안 읽고 등록부 900 으로 나이 1000초를 죽었다고 판정했다")

    _beat(WORKER_KIND_RQ_WORKER, age_seconds=1215, metadata={"interval_seconds": 405})
    health = worker_watchdog.evaluate_worker_health(db_session, now=_NOW)
    assert WORKER_KIND_RQ_WORKER in health["stale_kinds"], (
        "예산과 정확히 같은 나이(1215초)를 살아 있다고 판정했다 — 경계는 >= 다")


def test_without_a_declared_interval_the_registry_budget_still_bites(app):
    """음성 대조군 — 신고가 없으면 등록부 900 이 그대로 문다(예산이 통째로 넓어진 게 아니다)."""
    _beat(WORKER_KIND_NAVER_ORDER_SYNC, age_seconds=1000)
    health = worker_watchdog.evaluate_worker_health(db_session, now=_NOW)
    assert _SYNC_REGISTRY_BUDGET == 900
    assert WORKER_KIND_NAVER_ORDER_SYNC in health["stale_kinds"], (
        "신고가 없는데도 등록부 예산을 안 썼다")


def test_declared_interval_budget_is_not_infinite(app):
    """신고 1800 이어도 5400초(3틱)를 넘기면 멎은 것이다 — 예산은 유한하다."""
    _beat(WORKER_KIND_NAVER_ORDER_SYNC, age_seconds=5401,
          metadata={"interval_seconds": 1800})
    health = worker_watchdog.evaluate_worker_health(db_session, now=_NOW)
    assert WORKER_KIND_NAVER_ORDER_SYNC in health["stale_kinds"], (
        "신고 간격이 예산을 무한으로 늘렸다")


def test_nonsense_declared_interval_cannot_widen_the_budget(app):
    """말이 안 되는 신고(0초)로는 예산을 못 늘린다 — 등록부 900 으로 되돌아간다."""
    _beat(WORKER_KIND_NAVER_ORDER_SYNC, age_seconds=1000,
          metadata={"interval_seconds": 0})
    health = worker_watchdog.evaluate_worker_health(db_session, now=_NOW)
    assert WORKER_KIND_NAVER_ORDER_SYNC in health["stale_kinds"], (
        "0초 신고를 예산으로 받아들였다")


# --------------------------------------------------------------------------- #
# 2. 알림은 전이에서만
# --------------------------------------------------------------------------- #

def test_notifies_once_on_the_transition_then_stays_quiet(app):
    """멎은 순간 한 번 알리고, 계속 멎어 있는 동안은 조용하다."""
    _admin()
    _beat(WORKER_KIND_RQ_WORKER, age_seconds=_BUDGET + 60)

    first = worker_watchdog.run_watchdog_once(db_session, now=_NOW)
    db_session.commit()
    assert first["changed"] is True and first["notification_id"]
    assert _notif_count() == 1

    for tick in range(3):
        later = _NOW + datetime.timedelta(minutes=tick + 1)
        again = worker_watchdog.run_watchdog_once(db_session, now=later)
        db_session.commit()
        assert again["changed"] is False, "같은 상태가 이어지는데 또 알렸다"
    assert _notif_count() == 1, "멎어 있는 동안 알림이 쌓였다"


def test_recovery_is_announced_too(app):
    """다시 돌기 시작한 것도 알린다 — 안 알리면 사람이 계속 조마조마하다."""
    _admin()
    _beat(WORKER_KIND_RQ_WORKER, age_seconds=_BUDGET + 60)
    worker_watchdog.run_watchdog_once(db_session, now=_NOW)
    db_session.commit()

    _beat(WORKER_KIND_RQ_WORKER, age_seconds=5)
    back = worker_watchdog.run_watchdog_once(db_session, now=_NOW)
    db_session.commit()
    assert back["changed"] is True
    assert _notif_count() == 2
    latest = (db_session.query(Notification)
              .filter(Notification.notification_type == worker_watchdog.NOTIFICATION_TYPE)
              .order_by(Notification.id.desc()).first())
    assert "다시" in (latest.title or "")


def test_notification_targets_every_admin_without_an_order(app):
    """인프라 사건이라 주문이 없다. 대상은 관리자 전원(사건 1건 = 알림 1행)."""
    _admin("가")
    _admin("나")
    _beat(WORKER_KIND_RQ_WORKER, age_seconds=_BUDGET + 60)
    worker_watchdog.run_watchdog_once(db_session, now=_NOW)
    db_session.commit()

    notif = (db_session.query(Notification)
             .filter(Notification.notification_type == worker_watchdog.NOTIFICATION_TYPE)
             .one())
    assert notif.order_id is None
    assert notif.target_type == "ROLE" and notif.target_role == "ADMIN"
    # is_urgent 를 켜면 에스컬레이션 스윕이 사람에게 되묻는다 — 인프라 사건에는 안 맞는다.
    assert notif.is_urgent is False
    assert "쌓이는 중" in (notif.message or "")


def test_message_names_what_stalled_and_for_how_long(app):
    """"뭔가 멎었다" 만으로는 사람이 다음 행동을 못 정한다."""
    _admin()
    _beat(WORKER_KIND_RQ_WORKER, age_seconds=_BUDGET + 600)
    worker_watchdog.run_watchdog_once(db_session, now=_NOW)
    db_session.commit()
    notif = (db_session.query(Notification)
             .filter(Notification.notification_type == worker_watchdog.NOTIFICATION_TYPE)
             .one())
    assert WORKER_KIND_RQ_WORKER in notif.message
    assert "분째" in notif.message


def test_state_row_is_written_so_the_next_tick_knows(app):
    """전이 판정의 근거는 ``SystemSetting`` 한 행이다."""
    _admin()
    _beat(WORKER_KIND_RQ_WORKER, age_seconds=_BUDGET + 60)
    worker_watchdog.run_watchdog_once(db_session, now=_NOW)
    db_session.commit()
    row = db_session.get(SystemSetting, worker_watchdog.SETTING_KEY)
    assert row is not None and row.setting_value["stalled"] is True


def test_watchdog_records_that_it_ran_even_when_everything_is_fine(app):
    """정상일 때도 흔적을 남긴다 — 안 남기면 감시자가 도는지 확인할 길이 없다.

    2026-09-08 운영에서 게이트를 켜고 나서 "정말 켜졌나" 를 물을 수단이 없었다.
    감시자가 자기 생존을 안 남기는 것은 감시 대상의 결함과 같은 결함이다.
    """
    _beat(WORKER_KIND_RQ_WORKER, age_seconds=10)
    out = worker_watchdog.run_watchdog_once(db_session, now=_NOW)
    db_session.commit()
    assert out["changed"] is False, "정상인데 전이로 셌다"
    row = db_session.get(SystemSetting, worker_watchdog.SETTING_KEY)
    assert row is not None, "정상일 때 아무 흔적도 안 남겼다"
    assert row.setting_value["checked_at"] == _NOW.isoformat()
    assert row.setting_value["stalled"] is False


def test_changed_at_only_moves_on_a_transition(app):
    """"언제부터 이 상태인가" 는 매 회차 기록에 덮이면 안 된다."""
    _admin()
    _beat(WORKER_KIND_RQ_WORKER, age_seconds=_BUDGET + 60)
    worker_watchdog.run_watchdog_once(db_session, now=_NOW)
    db_session.commit()
    first = db_session.get(SystemSetting, worker_watchdog.SETTING_KEY).setting_value
    assert first["changed_at"] == _NOW.isoformat()

    later = _NOW + datetime.timedelta(minutes=5)
    worker_watchdog.run_watchdog_once(db_session, now=later)
    db_session.commit()
    db_session.expire_all()
    second = db_session.get(SystemSetting, worker_watchdog.SETTING_KEY).setting_value
    assert second["changed_at"] == _NOW.isoformat(), "전이가 아닌데 changed_at 이 움직였다"
    assert second["checked_at"] == later.isoformat(), "회차 시각이 안 갱신됐다"


def test_notify_false_judges_without_making_noise(app):
    """점검용 판정은 알림을 만들지 않는다."""
    _admin()
    _beat(WORKER_KIND_RQ_WORKER, age_seconds=_BUDGET + 60)
    out = worker_watchdog.run_watchdog_once(db_session, now=_NOW, notify=False)
    db_session.commit()
    assert out["changed"] is True and out["notification_id"] is None
    assert _notif_count() == 0


# --------------------------------------------------------------------------- #
# 3. 배선 — 어디서 도는가가 이 기능의 전부다
# --------------------------------------------------------------------------- #

def test_watchdog_runs_in_sidefx_not_in_the_worker_container():
    """WORKER 안에서 돌면 워커가 죽을 때 같이 죽어 아무 말도 못 한다."""
    runner = _SIDEFX_RUNNER.read_text(encoding="utf-8")
    assert "run_watchdog_once" in runner, "SIDEFX 루프가 감시자를 안 부른다"
    assert "next_watchdog" in runner, "감시가 주기로 안 돈다"

    start_sh = _START_SH.read_text(encoding="utf-8")
    worker_branch = (start_sh.split('if [ "$USE_RQ_WORKER" = "1" ]; then', 1)[1]
                     .split("\nelse\n", 1)[0])
    assert "worker_watchdog" not in worker_branch, \
        "감시자를 WORKER 컨테이너에 배선하면 감시 대상과 함께 죽는다"


def test_watchdog_is_gated_off_by_default():
    """다른 루프와 같은 규율 — 기본 off, env 로 켠다."""
    saved = os.environ.pop(worker_watchdog.ENABLED_ENV, None)
    try:
        assert worker_watchdog.is_enabled() is False
        os.environ[worker_watchdog.ENABLED_ENV] = "1"
        assert worker_watchdog.is_enabled() is True
    finally:
        os.environ.pop(worker_watchdog.ENABLED_ENV, None)
        if saved is not None:
            os.environ[worker_watchdog.ENABLED_ENV] = saved


def test_push_does_not_go_through_the_queue():
    """이 알림만은 rq 를 안 거친다 — 알리려는 사실이 그 큐가 안 돈다는 것이다."""
    runner = _SIDEFX_RUNNER.read_text(encoding="utf-8")
    block = runner.split("def _push_watchdog_notification", 1)[1].split("\ndef ", 1)[0]
    assert "send_push_for_notification" in block, "직접 발송 경로를 안 쓴다"
    assert "enqueue" not in block, "큐를 거치면 워커가 살아난 뒤에야 나간다"


def test_worker_stalled_is_registered_for_push():
    """P1 집합에 없으면 push 를 만들어도 조용히 no-op 된다(무음 push 의 유일한 기전)."""
    from foms.services.notifications import push_sender

    source = Path(push_sender.__file__).read_text(encoding="utf-8")
    assert '"WORKER_STALLED",' in source

"""도면 마감 알림 — WORKER 둘이 같은 바퀴를 돌아도 열쇠마다 한 번(PGTEST-00 lane, 설계서 2026-11-22 §9-6 · §10).

SQLite 는 ``FOR UPDATE`` 를 흉내 내지 못해 여기서만 잰다. 두 세션 = 두 WORKER.

* 기록 줄이 있을 때: A 가 잠그고 알림을 만든 채 커밋 전 → B 는 잠금에서 기다린다 → A 커밋 → B 는 A 의 열쇠를 보고 0건.
* 기록 줄이 아직 없을 때(맨 처음 켠 날): 둘 다 잠글 줄이 없어 알림을 만들지만, B 의 기록 줄 INSERT 가 A 의 커밋 뒤
  기본 키 충돌로 실패한다 → B 트랜잭션(알림 포함)이 통째로 되돌아간다 → 여전히 한 번. 루프는 이것을
  ``state_race`` 로 기록만 하고 다음 바퀴로 간다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 레인을 skip 한다. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import datetime
import threading
import time

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from foms.services.notifications import drawing_deadline_alert as alert
from models import Notification, Order, SystemSetting, User

KST = datetime.timezone(datetime.timedelta(hours=9))
NOW = datetime.datetime(2026, 11, 23, 8, 2, tzinfo=KST)  # 월 — 시공 11/25 (수) 의 마감 날
_SEQ = [0]


@pytest.fixture
def switch_on(monkeypatch):
    monkeypatch.setenv(alert.ENABLED_ENV, "1")
    monkeypatch.delenv(alert.ONLY_USERS_ENV, raising=False)
    alert.reset_process_memory()


def _seed(pg_engine, *, with_state: bool) -> int:
    """도면 담당 · 영업 담당 둘과 마감 날 주문 하나를 커밋한다 → 주문 번호."""
    _SEQ[0] += 1
    tag = f"{_SEQ[0]}_{int(time.time() * 1000) % 100000}"
    s = sessionmaker(bind=pg_engine)()
    try:
        # 같은 모듈 앞 시험이 남긴 주문 · 기록 줄을 치운다(레인은 모듈이 끝나야 비운다).
        s.query(Order).update({Order.erp_stage_code: "PRODUCTION"}, synchronize_session=False)
        s.query(SystemSetting).filter(SystemSetting.setting_key == alert.STATE_KEY).delete(synchronize_session=False)
        draw = User(username=f"dl_d_{tag}", password=generate_password_hash("pw"), role="STAFF", team="DRAWING",
                    name=f"장가짜{tag}", is_active=True)
        sales = User(username=f"dl_s_{tag}", password=generate_password_hash("pw"), role="STAFF", team="SALES",
                     name=f"이가짜{tag}", is_active=True)
        s.add_all([draw, sales])
        s.flush()
        sd = {"workflow": {"stage": "DRAWING"}, "drawing_status": "RETURNED",
              "parties": {"customer": {"name": "김가짜"}, "manager": {"name": sales.name}},
              "schedule": {"construction": {"date": "2026-11-25"}}, "items": [{"product_name": "붙박이장"}],
              "assignments": {"drawing_assignee_user_ids": [draw.id]},
              "drawing_assignees": [{"id": draw.id, "name": draw.name}]}
        order = Order(received_date="2026-11-01", customer_name="김가짜", phone="010-0000-0000", address="가짜시",
                      product="붙박이장", status="DRAWING", is_erp_order=True, erp_stage_code="DRAWING",
                      erp_construction_date="2026-11-25", structured_data=sd)
        s.add(order)
        if with_state:
            s.add(SystemSetting(setting_key=alert.STATE_KEY, version=1, setting_value={"sent": {}}))
        s.commit()
        return int(order.id)
    finally:
        s.close()


def _count(pg_engine, order_id: int) -> int:
    s = sessionmaker(bind=pg_engine)()
    try:
        return s.query(Notification).filter(Notification.order_id == order_id,
                                            Notification.notification_type == alert.NOTIFICATION_TYPE).count()
    finally:
        s.close()


def _worker_b(pg_engine, out: dict, done: threading.Event) -> None:
    """두 번째 WORKER — 같은 바퀴를 돌고 커밋한다(실패는 되돌리고 예외 이름만 남긴다)."""
    s = sessionmaker(bind=pg_engine)()
    try:
        out["result"] = alert.run_drawing_deadline_alerts(s, now=NOW)
        s.commit()
    except IntegrityError as exc:
        s.rollback()
        out["error"] = type(exc).__name__
    finally:
        s.close()
        done.set()


def _race(pg_engine, order_id: int) -> tuple[dict, dict, bool]:
    """A 가 보내고 커밋 전 → B 출발 → B 가 기다리는지 본 뒤 A 커밋 → B 끝."""
    a = sessionmaker(bind=pg_engine)()
    out: dict = {}
    done = threading.Event()
    try:
        first = alert.run_drawing_deadline_alerts(a, now=NOW)
        assert first["notifications"] == 2, first
        thread = threading.Thread(target=_worker_b, args=(pg_engine, out, done), daemon=True)
        thread.start()
        blocked = not done.wait(1.0)
        a.commit()
        assert done.wait(30), "B 가 끝나지 않았다(잠금이 안 풀림)"
        thread.join(5)
        return first, out, blocked
    finally:
        a.rollback()
        a.close()


def test_기록_줄이_있으면_둘째_WORKER_는_잠금에서_기다렸다가_0건(pg_engine, switch_on) -> None:
    oid = _seed(pg_engine, with_state=True)
    _first, out, blocked = _race(pg_engine, oid)
    assert blocked, "B 가 A 의 잠금을 기다리지 않았다 — FOR UPDATE 가 안 걸렸다"
    assert "error" not in out and out["result"]["sent"] == 0 and out["result"]["notifications"] == 0
    assert _count(pg_engine, oid) == 2  # 받는 사람 둘 × 한 번


def test_기록_줄이_없던_첫날도_한_번_늦은_쪽은_통째로_되돌아간다(pg_engine, switch_on) -> None:
    oid = _seed(pg_engine, with_state=False)
    _first, out, _blocked = _race(pg_engine, oid)
    assert out.get("error") == "IntegrityError", out
    assert _count(pg_engine, oid) == 2
    s = sessionmaker(bind=pg_engine)()
    try:
        sent = (s.get(SystemSetting, alert.STATE_KEY).setting_value or {})["sent"]
        assert list(sent) == [f"{oid}:2026-11-23:am"]
        again = alert.run_drawing_deadline_alerts(s, now=NOW.replace(minute=3))  # 다음 바퀴
        s.commit()
        assert again["sent"] == 0
    finally:
        s.close()
    assert _count(pg_engine, oid) == 2


def test_음성_대조_잠그지_않으면_둘째_WORKER_가_또_보낸다(pg_engine, switch_on, monkeypatch) -> None:
    """잠금을 일반 읽기로 바꾸면 같은 시나리오에서 B 가 A 의 열쇠를 못 본 채 같은 열쇠로 또 보낸다(기록 줄 UPDATE 에서야
    기다렸다가 덮어쓴다) — 위 시험이 결함을 실제로 잡는다."""
    monkeypatch.setattr(alert, "_lock_state_row", lambda db: db.get(SystemSetting, alert.STATE_KEY))
    oid = _seed(pg_engine, with_state=True)
    _first, out, _blocked = _race(pg_engine, oid)
    assert "error" not in out and out["result"]["notifications"] == 2
    assert _count(pg_engine, oid) == 4

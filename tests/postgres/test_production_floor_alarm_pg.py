"""PG 레인 — 생산 현장 알람의 쿼리가 운영 DB(PostgreSQL)에서 그대로 도는지(설계서 2026-11-28 생산 현장 알람 §4).

SQLite 시험이 못 보는 것: 종류 이름 ``LIKE … ESCAPE``(밑줄 풀어 쓰기 — 운영 드라이버 바인드) · 알림 줄 FK(만든 사람 · 받는 사람 · 주문) ·
표시 줄 ``holders`` JSONB 읽기 · 시각 알람의 출고일 후보 SQL. 한 흐름으로 본다: 담당 변경(합치기 찾기) → 보류(작업 중인 사람) →
보류 풀림(닫기) → 다시 받기 → 윗사람 올림 빼기 → 9시 칸 띠. 도메인 시험은 ``tests/domains/test_production_floor_alarm*.py``.
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytz
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from foms.api.production.alarms import pending_for
from foms.services.notifications.escalation import escalate_overdue_urgent
from foms.services.production import floor_alarm
from foms.services.production import floor_alarm_text as T
from foms.services.production import floor_alarm_timed as timed
from models import Notification, NotificationUserState, Order, ProductionPartMark, User

NOW = datetime.datetime(2026, 11, 28, 3, 0, 0)  # UTC naive = 한국 시각 낮 12시
TODAY = datetime.date(2026, 11, 28)
KST = pytz.timezone("Asia/Seoul")


def _user(s, name: str, tag: str, **columns) -> User:
    user = User(username=f"fa_{name}_{tag}", password=generate_password_hash("pw"), role="STAFF", team="PRODUCTION", name=name,
                is_active=True, **columns)
    s.add(user)
    s.flush()
    return user


def _types(s, user_id: int) -> list[str]:
    rows = (s.query(Notification.notification_type).filter(Notification.target_user_id == user_id)
            .order_by(Notification.id).all())
    return [ntype[len(T.PREFIX):] for (ntype,) in rows if ntype.startswith(T.PREFIX)]


def test_floor_alarm_flow_runs_on_postgres(pg_engine, monkeypatch):
    monkeypatch.setenv(floor_alarm.SWITCH_ENV, "on")
    monkeypatch.setattr(floor_alarm, "_clock", lambda: (NOW, TODAY))
    monkeypatch.setitem(timed._DONE, "day", "")
    monkeypatch.setitem(timed._DONE, "slots", set())
    sent: list[tuple[list[int], dict]] = []
    monkeypatch.setattr(floor_alarm, "emit_erp_notification_to_users", lambda uids, body=None: sent.append((list(uids), body)) or 1)
    monkeypatch.setattr(floor_alarm, "enqueue_push_for_notification", lambda nid, db=None: {"enqueued": False})
    s = sessionmaker(bind=pg_engine)()
    try:
        tag = "pg1"
        lead, kim, oh = _user(s, "박반장", tag, production_lead=True), _user(s, "김재단", tag, production_part="cut"), \
            _user(s, "오재단", tag, production_part="cut")
        key = f"{tag}/d0.png"
        steps = [{"key": k, "label": k, "done": False, "at": None, "by_name": None} for k in ("cut", "edge", "assemble", "inspect")]
        order = Order(received_date="2026-11-27", customer_name="정하늘", phone="010-0000-0000", address="가짜시", product="가짜장",
                      status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION", erp_construction_date=TODAY.isoformat(),
                      structured_data={"workflow": {"stage": "PRODUCTION"}, "parties": {"customer": {"name": "정하늘"}},
                                       "schedule": {"construction": {"date": TODAY.isoformat()}},
                                       "drawing_current_files": [{"key": key, "filename": "d0.png", "sheet_id": f"{tag}-s0"}],
                                       "production": {"steps": steps}})
        s.add(order)
        s.flush()
        s.add(ProductionPartMark(order_id=order.id, drawing_key=key, part="cut", state="NEED", picked_by_user_id=kim.id,
                                 picked_by_name="김재단", updated_by_user_id=kim.id,
                                 holders=[{"uid": kim.id, "name": "김재단", "at": "2026-11-28T01:00:00+00:00", "done_at": None,
                                           "done_uid": None, "done_name": None}]))
        s.commit()
        ids = {"lead": lead.id, "kim": kim.id, "oh": oh.id, "order": order.id}

        # 담당 변경 두 번(60초 안 — 둘째는 합치기 찾기 LIKE 로 앞 줄을 찾아 줄을 안 늘린다).
        for _ in range(2):
            data = {"changed": True, "gave": {"order_id": ids["order"], "drawing_key": key, "part": "cut",
                                              "by": {"user_id": ids["lead"], "name": "박반장"}, "from": None,
                                              "to": {"user_id": ids["oh"], "name": "오재단"}, "self": False}}
            floor_alarm.note_mark(s, s.get(User, ids["lead"]), SimpleNamespace(order_id=ids["order"], key=key, part="cut", action="takeover"), data)
            s.commit()
            floor_alarm.flush(s)
        assert _types(s, ids["oh"]) == ["NEW_GIVEN"]
        # 보류 → 작업 중인 사람(JSONB 목록)만 멈춤 → 보류 풀림은 닫고 띠.
        floor_alarm.note(s, "hold", ids["order"], s.get(User, ids["lead"]), reason="자재 기다림")
        s.commit()
        floor_alarm.flush(s)
        assert _types(s, ids["kim"]) == ["STOP_HOLD"] and _types(s, ids["oh"]) == ["NEW_GIVEN"]
        pending = pending_for(s, ids["kim"], NOW)
        assert [a["title"] for a in pending["urgent"]] == ["멈추세요 — 보류됐어요"] and pending["notices"] == []
        # 윗사람 올림: 10분이 지나도 생산 알람은 대상이 아니다(환경 변수 빼기 목록을 비워도).
        monkeypatch.setenv("FOMS_ESCALATION_EXEMPT_TYPES", "")
        swept = escalate_overdue_urgent(s, now=NOW + datetime.timedelta(minutes=10))
        assert (swept["checked"], swept["escalated"], swept["operator_escalated"]) == (0, 0, 0)
        s.rollback()
        floor_alarm.note(s, "hold_released", ids["order"], s.get(User, ids["lead"]))
        s.commit()
        floor_alarm.flush(s)
        assert _types(s, ids["kim"]) == ["STOP_HOLD", "NOTICE_HOLD_RELEASED"]
        closed = (s.query(NotificationUserState).join(Notification, Notification.id == NotificationUserState.notification_id)
                  .filter(Notification.notification_type == T.STOP_HOLD, NotificationUserState.user_id == ids["kim"]).one())
        assert closed.archived_at is not None
        after = pending_for(s, ids["kim"], NOW)
        assert after["urgent"] == [] and [a["notification_type"] for a in after["notices"]] == [T.NOTICE_HOLD_RELEASED]
        assert any(body.get("floor_closed") for _uids, body in sent)
        # 시각 알람 — 오늘 나가는 주문(출고일 후보 SQL)이 반장 띠 하나로, 같은 칸 다음 바퀴는 줄 0.
        at_nine = KST.localize(datetime.datetime(2026, 11, 28, 9, 5))
        first = timed.run(s, now=at_nine)
        s.commit()
        assert (first["slot"], first["orders"], first["notifications"]) == (9, 1, 1)
        assert timed.run(s, now=at_nine + datetime.timedelta(minutes=1))["notifications"] == 0
        s.commit()
        assert _types(s, ids["lead"]) == ["NOTICE_DUE_TODAY"]
    finally:
        s.rollback()
        s.close()

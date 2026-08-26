"""NAVER-INGEST-01 T7: 앱 인증 만료 알림 계약 테스트.

만료되면 애플리케이션이 자동 휴면돼 수집이 **조용히** 전면 중단된다(우리 화면엔 에러가
안 뜬다). 그래서 만료 전에 알리는 것 자체가 기능이고, 아래가 그 계약이다.
"""

from __future__ import annotations

from datetime import date, timedelta

from db import db_session
from foms.services.integrations.naver_commerce import app_expiry
from foms.services.notifications.push_sender import _DEFAULT_P1_TYPES
from models import (ExternalOrderLink, Notification, NotificationUserState,
                    SystemSetting, User)

TODAY = date(2026, 8, 13)


def _admin(username: str = "admin1", is_active: bool = True) -> User:
    user = User(username=username, password="pw-not-committed", name="관리자",
                role="ADMIN", team="CS", is_active=is_active)
    db_session.add(user)
    db_session.commit()
    return user


def _set_expiry(days_from_today: int) -> date:
    expires_on = TODAY + timedelta(days=days_from_today)
    app_expiry.set_expiry_date(db_session, expires_on)
    db_session.commit()
    return expires_on


def test_push_type_is_registered(app):
    """미등록이면 enqueue 해도 push 가 조용히 no-op 된다 — 무음 알림의 유일한 기전."""
    assert app_expiry.NOTIFICATION_TYPE in _DEFAULT_P1_TYPES


def test_no_expiry_date_means_no_alert(app):
    """만료일을 모르면 알리지 않는다(모름을 임박으로 오해하면 알림이 잡음이 된다)."""
    _admin()
    assert app_expiry.check_and_notify(db_session, today=TODAY) is None
    assert db_session.query(Notification).count() == 0


def test_alert_fires_at_d7(app):
    """스펙 요구선: D-7 에 알림이 나간다."""
    admin = _admin()
    _set_expiry(7)
    assert app_expiry.check_and_notify(db_session, today=TODAY) == 7
    db_session.commit()

    notification = db_session.query(Notification).one()
    assert notification.notification_type == app_expiry.NOTIFICATION_TYPE
    # ROLE 알림이라 row 에는 사람이 안 박힌다 — 수신자는 state 로 풀린다(NOTIF-ROLE-01).
    assert notification.target_type == "ROLE" and notification.target_role == "ADMIN"
    assert notification.target_user_id is None
    assert db_session.query(NotificationUserState).one().user_id == admin.id
    assert notification.is_urgent is True
    assert "D-7" in notification.title
    assert notification.order_id is None
    # 공유 row 직접 조작이 아니라 fan_out 훅을 거쳐야 수신자 state 가 생긴다.
    assert db_session.query(NotificationUserState).count() == 1


def test_far_future_expiry_is_quiet(app):
    """아직 여유가 있으면 알리지 않는다."""
    _admin()
    _set_expiry(30)
    assert app_expiry.check_and_notify(db_session, today=TODAY) is None
    assert db_session.query(Notification).count() == 0


def test_same_threshold_does_not_repeat(app):
    """5분 폴링마다 같은 알림을 쏘면 안 된다 — 임계값당 1회."""
    _admin()
    _set_expiry(7)
    app_expiry.check_and_notify(db_session, today=TODAY)
    db_session.commit()
    for _ in range(3):
        assert app_expiry.check_and_notify(db_session, today=TODAY) is None
    db_session.commit()
    assert db_session.query(Notification).count() == 1


def test_closer_threshold_alerts_again(app):
    """D-7 을 놓쳐도 D-3·D-1·D-0 에서 다시 알린다."""
    _admin()
    expires_on = _set_expiry(7)
    app_expiry.check_and_notify(db_session, today=TODAY)
    db_session.commit()
    assert app_expiry.check_and_notify(db_session, today=expires_on - timedelta(days=3)) == 3
    assert app_expiry.check_and_notify(db_session, today=expires_on - timedelta(days=1)) == 1
    assert app_expiry.check_and_notify(db_session, today=expires_on) == 0
    db_session.commit()
    assert db_session.query(Notification).count() == 4


def test_expired_already_uses_past_tense_title(app):
    """이미 만료된 상태도 알린다(제목이 D-음수가 되면 안 된다)."""
    _admin()
    _set_expiry(-2)
    assert app_expiry.check_and_notify(db_session, today=TODAY) == 0
    db_session.commit()
    assert "만료됨" in db_session.query(Notification).one().title


def test_every_active_admin_gets_one(app):
    """관리자 수와 무관하게 Notification 은 ROLE 1건 — 수신은 활성 ADMIN 전원(NOTIF-ROLE-01)."""
    admin1, admin2 = _admin("admin1"), _admin("admin2")
    _admin("admin3", is_active=False)
    db_session.add(User(username="staff1", password="pw-not-committed", name="사원",
                        role="STAFF", team="SALES", is_active=True))
    db_session.commit()
    _set_expiry(1)
    app_expiry.check_and_notify(db_session, today=TODAY)
    db_session.commit()

    rows = db_session.query(Notification).all()
    assert len(rows) == 1, "관리자 수만큼 알림이 복제됐다(NOTIF-ROLE-01 회귀)"
    assert rows[0].target_type == "ROLE" and rows[0].target_role == "ADMIN"
    assert rows[0].target_user_id is None
    # 수신자는 활성 ADMIN 2명뿐 — 비활성 admin3·STAFF 는 빠진다.
    states = (db_session.query(NotificationUserState)
              .filter(NotificationUserState.notification_id == rows[0].id).all())
    assert {s.user_id for s in states} == {admin1.id, admin2.id}


def test_renewing_expiry_resets_notified_history(app):
    """인증을 갱신하면 이전 임계값 이력은 무효다(다음 만료 때 다시 알려야 한다)."""
    _admin()
    _set_expiry(1)
    app_expiry.check_and_notify(db_session, today=TODAY)
    db_session.commit()
    _set_expiry(400)  # 갱신
    state = db_session.get(SystemSetting, app_expiry.SETTING_KEY).setting_value
    assert state["notified"] == []


def test_corrupt_expiry_value_is_ignored(app):
    """저장값이 깨져도 수집이 죽지 않는다."""
    _admin()
    db_session.add(SystemSetting(setting_key=app_expiry.SETTING_KEY,
                                 setting_value={"expires_on": "언젠가"}))
    db_session.commit()
    assert app_expiry.read_expiry_date(db_session) is None
    assert app_expiry.check_and_notify(db_session, today=TODAY) is None


def test_expiry_alert_failure_never_rolls_back_a_successful_sweep(app, monkeypatch):
    """부가 알림이 터져도 이미 성공한 수집은 유지돼야 한다."""
    from foms.services.integrations.naver_commerce import ingest as ingest_mod

    db_session.add_all([
        User(username=ingest_mod.ACTOR_USERNAME, password="pw-not-committed",
             name="봇", role="MANAGER", team="CS", is_active=True),
        User(username=ingest_mod.OWNER_USERNAME, password="pw-not-committed",
             name="미배정", role="STAFF", team="SALES", is_active=True),
    ])
    db_session.commit()

    def _boom(*args, **kwargs):
        raise RuntimeError("알림 경로 고장")

    monkeypatch.setattr(app_expiry, "check_and_notify", _boom)

    from datetime import datetime

    from foms.services.integrations.naver_commerce.client import KST
    from models import Order

    class _Stub:
        def get_last_changed_statuses(self, start, end):
            return [{"productOrderId": "PO-9", "productOrderStatus": "PAYED"}]

        def get_product_orders(self, ids):
            return [{
                "order": {"orderId": "1", "ordererName": "김주문", "ordererTel": "010-1-2",
                          "orderDate": "2026-08-13T09:00:00.000+09:00"},
                "productOrder": {
                    "productOrderId": "PO-9", "productOrderStatus": "PAYED",
                    "productName": "붙박이장", "totalPaymentAmount": 100,
                    "shippingAddress": {"name": "이수취", "tel1": "010-3-4",
                                        "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
                },
            }]

    payload = ingest_mod.run_sweep(db_session, client=_Stub(),
                                   now=datetime(2026, 8, 13, 12, 0, tzinfo=KST))
    assert payload["collected"] == 1
    assert db_session.query(ExternalOrderLink).count() == 1, "수집분은 살아남아야 한다"
    assert payload["expiry_alert"] is None

"""프리랜서 영업 차감 알림 ``SALES_COMMISSION_DEDUCTION`` 시험(설계서 FCOMM-01 §7 · D17).

- 영업 귀속 차감이 켜진 프리랜서에게 붙으면 넣을 때 · 취소할 때 그 사람 한 명에게 알림 한 줄.
- 일반 영업 직원 · 다른 부서 귀속은 알림이 없다(음성 대조군).
- 폰으로 가는 유형(P1)이고, 누르면 내 수수료 화면, 잠금 화면 글에 사유를 싣지 않는다.
고객 · 이름 · 금액은 모두 가짜 값이다.
"""
from __future__ import annotations

from types import SimpleNamespace

from db import db_session
from foms.services.notifications import push_sender
from foms.services.sales_commission import deduction_notify
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import Notification, NotificationUserState
from tests.domains.test_auth_finance import _login, _make_user
from tests.domains.test_settlement_deductions import _freelancer, _order_with, _reload


def _notifications(order_id: int) -> list[Notification]:
    db_session.expire_all()
    return (db_session.query(Notification)
            .filter(Notification.order_id == order_id,
                    Notification.notification_type == deduction_notify.NOTIFICATION_TYPE)
            .order_by(Notification.id).all())


def _issue_sales(client, order_id: int, user_id: int, amount: int = 50_000):
    return client.post(f"/api/orders/{order_id}/settlement/issue", json={
        "department": "SALES", "amount": amount, "reason": "가상 재방문", "charge_to_user_id": user_id})


def test_freelancer_gets_one_notification_on_issue_and_on_void(client, app):
    freelancer = _freelancer()
    freelancer_id = freelancer.id
    oid = _order_with([])
    _login(client, _make_user(role="STAFF", team="ACCOUNTING"))

    issued = _issue_sales(client, oid, freelancer_id)
    assert issued.status_code == 200, issued.get_data(as_text=True)
    ded_id = issued.get_json()["deduction_id"]

    rows = _notifications(oid)
    assert len(rows) == 1
    created = rows[0]
    assert (created.target_type, created.target_user_id) == ("USER", freelancer_id)
    assert created.title == "수수료 차감"
    assert created.message == "가상고객 주문에 차감 50,000원이 생겼어요 — 가상 재방문"
    states = db_session.query(NotificationUserState).filter(
        NotificationUserState.notification_id == created.id).all()
    assert [s.user_id for s in states] == [freelancer_id], "그 프리랜서 한 명에게만"

    voided = client.post(f"/api/orders/{oid}/settlement/deductions/{ded_id}/void",
                         json={"reason": "가상 취소"})
    assert voided.status_code == 200, voided.get_data(as_text=True)
    rows = _notifications(oid)
    assert len(rows) == 2
    assert rows[1].title == "수수료 차감 취소"
    assert rows[1].message == "가상고객 주문 차감 50,000원이 취소됐어요"


def test_no_notification_for_plain_seller_or_other_department(client, app):
    """음성 대조군 — 프리랜서가 아닌 영업 직원, 영업이 아닌 부서는 알림을 만들지 않는다."""
    seller_id = _make_user(role="STAFF", team="SALES").id
    freelancer_id = _freelancer().id
    oid = _order_with([])
    _login(client, _make_user(role="ADMIN"))

    assert _issue_sales(client, oid, seller_id).status_code == 200
    drawing = client.post(f"/api/orders/{oid}/settlement/issue", json={
        "department": "DRAWING", "amount": 10_000, "reason": "가상"})
    assert drawing.status_code == 200
    assert _notifications(oid) == []
    assert deduction_notify.freelancer_target(db_session, {"department": "CUSTOMER",
                                                           "charge_to_user_id": freelancer_id}) is None


def test_switched_off_freelancer_gets_no_notification(client, app):
    freelancer = _freelancer()
    version, configs = load_settings(db_session)
    cfg = configs[freelancer.id]
    save_freelancer(db_session, freelancer.id, {"match_name": cfg.match_name, "start_month": cfg.start_month,
                                                "tax_type": cfg.tax_type, "active": False},
                    base_version=version, actor_user_id=freelancer.id)
    db_session.commit()
    freelancer_id = freelancer.id
    oid = _order_with([])
    _login(client, _make_user(role="ADMIN"))

    assert _issue_sales(client, oid, freelancer_id).status_code == 200
    assert _notifications(oid) == []


def test_notification_failure_does_not_undo_the_deduction(client, app, monkeypatch):
    freelancer_id = _freelancer().id
    oid = _order_with([])
    _login(client, _make_user(role="ADMIN"))

    def _boom(*_a, **_k):
        raise RuntimeError("가상 알림 실패")

    monkeypatch.setattr(deduction_notify, "fan_out_new_notification", _boom)
    resp = _issue_sales(client, oid, freelancer_id)

    assert resp.status_code == 200 and resp.get_json()["success"] is True
    assert len(_reload(oid).structured_data["settlement"]["deductions"]) == 1
    assert _notifications(oid) == []


def test_type_reaches_phones_and_opens_my_commission():
    ntype = deduction_notify.NOTIFICATION_TYPE
    assert ntype == "SALES_COMMISSION_DEDUCTION"
    assert ntype in push_sender._DEFAULT_P1_TYPES, "P1 에 없으면 폰에 안 간다"
    notif = SimpleNamespace(id=9, order_id=5, notification_type=ntype, is_urgent=False,
                            created_at=None, message="가상고객 주문에 차감 50,000원이 생겼어요 — 비밀 사유",
                            title="수수료 차감", target_user_id=1)
    # 그 주문이 든 달을 연다(T8 스테이징: 달 없는 주소는 지난달을 열었다).
    assert deduction_notify.MY_COMMISSION_URL == "/erp/my-commission"
    assert push_sender._deep_link(notif) == "/erp/my-commission?order=5"

    named = push_sender._build_payload(notif, "가상고객")
    generic = push_sender._build_payload(notif, "")
    assert named["title"] == "수수료 차감 · 가상고객"
    assert generic["title"] == "수수료 차감"
    for payload in (named, generic):
        assert "비밀 사유" not in payload["body"], "잠금 화면에 사유를 싣지 않는다"
        assert payload["data"]["deep_link"] == "/erp/my-commission?order=5"


def test_bell_list_link_matches_the_phone_link():
    from foms.api.notifications import _resolve_notification_deep_link

    notif = SimpleNamespace(notification_type="SALES_COMMISSION_DEDUCTION", order_id=5, created_at=None)
    assert _resolve_notification_deep_link(notif, {})["deep_link_url"] == "/erp/my-commission?order=5"

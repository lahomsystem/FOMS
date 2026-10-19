"""ERP structured 라우트가 JSONB 시각을 naive UTC 규약으로 쓰는지 고정한다.

* payment-confirm: deposit/balance_confirmed_at 은 서버 시계 시간대와 무관한 naive UTC.
  (예전 ``datetime.now()`` 는 Railway(UTC)·로컬 Windows(KST) 에서 값이 9시간 달랐다.)
* draft 생성 2경로: workflow.stage_updated_at 은 다른 7개 writer 와 같은 naive UTC
  (예전 ``now_kst().isoformat()`` 은 +09:00 이 붙어 형식이 섞였다).
"""

from __future__ import annotations

import datetime

from werkzeug.security import generate_password_hash

import foms.api.erp_orders_structured as mod
from db import db_session
from models import Order, User

_FIXED = datetime.datetime(2026, 10, 19, 1, 2, 3)  # naive UTC = KST 10:02


def _login_admin(client) -> User:
    user = User(username="utc_ts_admin", password=generate_password_hash("pw"),
                role="ADMIN", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _assert_naive_utc(value: str) -> None:
    parsed = datetime.datetime.fromisoformat(value)
    assert parsed.tzinfo is None, value
    assert parsed == _FIXED, value


def test_payment_confirm_writes_naive_utc(client, monkeypatch):
    monkeypatch.setattr(mod, "now_utc_naive", lambda: _FIXED)
    _login_admin(client)
    order = Order(received_date="2026-10-19", customer_name="시각 검사", phone="010-0000-0000",
                  address="Seoul", product="Wardrobe", status="COMPLETED", is_erp_order=True,
                  structured_data={"payment": {}}, erp_stage_code="COMPLETED")
    db_session.add(order)
    db_session.commit()
    oid = order.id

    for kind in ("deposit", "balance"):
        resp = client.post(f"/api/orders/{oid}/payment-confirm",
                           json={"type": kind, "confirmed": True})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert resp.get_json()["success"] is True

    db_session.expire_all()
    payment = db_session.get(Order, oid).structured_data["payment"]
    _assert_naive_utc(payment["deposit_confirmed_at"])
    _assert_naive_utc(payment["balance_confirmed_at"])


def test_draft_post_stage_updated_at_is_naive_utc(client, monkeypatch):
    monkeypatch.setattr(mod, "now_utc_naive", lambda: _FIXED)
    _login_admin(client)
    resp = client.post("/api/orders/erp/draft", json={"draft_token": "utc-ts-token"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    oid = resp.get_json()["order_id"]
    db_session.expire_all()
    wf = db_session.get(Order, oid).structured_data["workflow"]
    _assert_naive_utc(wf["stage_updated_at"])


def test_session_draft_stage_updated_at_is_naive_utc(app, monkeypatch):
    monkeypatch.setattr(mod, "now_utc_naive", lambda: _FIXED)
    with app.test_request_context("/"):
        order = mod._create_session_draft(db_session, "utc-ts-session")
        _assert_naive_utc(order.structured_data["workflow"]["stage_updated_at"])

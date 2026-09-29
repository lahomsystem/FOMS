"""발송 흔적 쓰기 앞 행 잠금(설계서 2026-09-29 §4.6).

``ka.record_share_history`` 는 ``session.refresh(order)``(FOR UPDATE 아님) 뒤 ``structured_data``
를 통째로 되쓴다. 도면 탭에서 보내기가 늘면 도면 전달·수정요청(행 잠금 + 버전 +1)과 겹칠 여지가
커지므로, 두 발송 라우트는 흔적 쓰기 **바로 앞에** ``lock_order_row`` 로 행을 잠근다.
SQLite 는 ``FOR UPDATE`` 를 무시하므로 여기서는 소스 순서와 실제 호출 순서만 본다.
"""
from __future__ import annotations

import datetime
import inspect

import pytest
from werkzeug.security import generate_password_hash

import foms.api.share as share_routes
from db import db_session
from foms.services import kakao_alimtalk as ka
from foms.services import order_share as osvc
from models import Order, User

_ENV_KEYS = ('SOLAPI_PF_ID_HAUD', 'SOLAPI_TEMPLATE_SHARE_ID_HAUD', 'SOLAPI_TEMPLATE_SHARE_BOTH_ID_HAUD',
             'SOLAPI_SENDER_PHONE_HAUD', 'SOLAPI_SENDER_PHONE', 'SOLAPI_SENDER_FALLBACK_HAUD')


@pytest.mark.parametrize("func", [share_routes.api_share_send_alimtalk, share_routes.api_share_send_sms])
def test_lock_precedes_record_share_history_in_source(func):
    src = inspect.getsource(func)
    assert "lock_order_row(" in src
    assert src.index("lock_order_row(") < src.index("ka.record_share_history(")


@pytest.fixture
def recorder(monkeypatch):
    calls = []
    real_lock = share_routes.lock_order_row
    real_record = ka.record_share_history

    def _lock(session, order_id):
        calls.append(("lock", order_id))
        return real_lock(session, order_id)

    def _record(session, order, **kwargs):
        calls.append(("record", order.id))
        return real_record(session, order, **kwargs)

    monkeypatch.setattr(share_routes, "lock_order_row", _lock)
    monkeypatch.setattr(ka, "record_share_history", _record)
    monkeypatch.setattr(ka, "_solapi_send", lambda **k: "ATA-1")
    monkeypatch.setattr(ka, "_solapi_send_text", lambda **k: "SMS-1")
    for name in _ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SOLAPI_PF_ID_HAUD", "PF-HAUD")
    monkeypatch.setenv("SOLAPI_TEMPLATE_SHARE_ID_HAUD", "TPL-HAUD")
    monkeypatch.setenv("SOLAPI_SENDER_PHONE_HAUD", "15660703")
    return calls


def _setup(client):
    history = [{"action": "TRANSFER", "at": "2026-09-20 01:00:00"}]
    order = Order(received_date=datetime.date(2026, 9, 19), customer_name="잠금고객", phone="010-2473-6730",
                  address="Seoul", product="가구", status="ERPORDER", is_erp_order=True,
                  structured_data={"parties": {"customer": {"name": "잠금고객", "phone": "010-2473-6730"}},
                                   "drawing_transfer_history": history})
    user = User(username="lock_u_" + str(datetime.datetime.utcnow().timestamp()).replace(".", ""),
                password=generate_password_hash("pw"), role="STAFF", team="CS", name="잠금", is_active=True)
    db_session.add_all([order, user])
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, "STAFF"
    row, token = osvc.create_share_token(db_session, order.id, "drawing")
    db_session.commit()
    return order.id, row.id, token


@pytest.mark.parametrize("path", ["send-alimtalk", "send-sms"])
def test_lock_called_right_before_record_and_history_survives(client, recorder, path):
    oid, sid, token = _setup(client)
    res = client.post(f"/api/share/{path}/{sid}", json={"token": token})
    assert res.status_code == 200, res.get_json()
    assert recorder == [("lock", oid), ("record", oid)]
    db_session.expire_all()
    sd = db_session.get(Order, oid).structured_data
    assert sd["alimtalk_share"]["share_id"] == sid
    assert sd["drawing_transfer_history"] == [{"action": "TRANSFER", "at": "2026-09-20 01:00:00"}]

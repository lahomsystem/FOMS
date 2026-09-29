"""인라인 필드 수정(PATCH structured/fields)의 첫 조회 행 잠금 — S1 리뷰 P2(2026-09-30).

도면 탭 보내기 창의 '주문 고객 번호도 저장'(Q5-②, ``FomsCustomerSend.savePhone``)이 이 라우트를
부른다. 라우트는 ``structured_data`` 를 통째로 다시 쓰는데, 잠금 없이 읽으면 그사이 커밋된 도면
전달·수정요청(행 잠금 + 버전 +1) 이력을 옛 dict 로 덮는다. ``X-If-Match``(structured_updated_at)는
도면 쓰기가 올리지 않는 값이라 이 경합을 막지 못한다. 그래서 첫 조회를 ``lock_order_row`` 로 한다.
SQLite 는 ``FOR UPDATE`` 를 무시하므로 여기서는 소스 순서·실제 호출·이력 보존만 본다
(두 세션 실제 대기는 ``tests/postgres/test_drawing_send_edit_row_lock_pg.py``).
"""
from __future__ import annotations

import datetime
import inspect

import pytest
from werkzeug.security import generate_password_hash

import foms.api.erp_orders_structured as structured_api
from db import db_session
from models import Order, User

_HISTORY = [{"action": "TRANSFER", "at": "2026-09-20 01:00:00", "files": []},
            {"action": "REQUEST_REVISION", "at": "2026-09-21 01:00:00", "note": "폭", "source": "customer"}]


def test_first_order_read_is_row_lock_in_source():
    src = inspect.getsource(structured_api.api_patch_order_structured_fields)
    assert "lock_order_row(" in src
    first_sd_read = src.index("order.structured_data")
    assert src.index("lock_order_row(") < first_sd_read
    assert ".first()" not in src[:src.index("lock_order_row(")], "잠금 앞에 잠금 없는 주문 조회가 있다"


@pytest.fixture
def seeded(client, monkeypatch):
    monkeypatch.setenv("FOMS_INLINE_EDIT_ENABLED", "1")
    stamp = str(datetime.datetime.utcnow().timestamp()).replace(".", "")
    user = User(username=f"inl_lock_{stamp}", password=generate_password_hash("pw"), role="STAFF",
                team="SALES", name="잠금영업", is_active=True)
    order = Order(received_date="2026-09-19", customer_name="잠금고객", phone="010-1111-2222",
                  address="서울", product="붙박이장", status="DRAWING", is_erp_order=True,
                  erp_stage_code="DRAWING", manager_name="잠금영업",
                  structured_data={"parties": {"customer": {"name": "잠금고객", "phone": "010-1111-2222"},
                                               "manager": {"name": "잠금영업"}},
                                   "workflow": {"stage": "DRAWING"}, "drawing_status": "RETURNED",
                                   "drawing_transfer_history": _HISTORY})
    db_session.add_all([user, order])
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    return order.id


def test_phone_patch_locks_row_and_keeps_drawing_history(client, seeded, monkeypatch):
    calls = []
    real_lock = structured_api.lock_order_row

    def _lock(session, order_id):
        calls.append(order_id)
        return real_lock(session, order_id)

    monkeypatch.setattr(structured_api, "lock_order_row", _lock)
    res = client.patch(f"/api/orders/{seeded}/structured/fields",
                       json={"field": "parties.customer.phone", "value": "010-3333-4444"})
    assert res.status_code == 200, res.get_json()
    assert calls == [seeded]
    db_session.expire_all()
    order = db_session.get(Order, seeded)
    assert order.structured_data["parties"]["customer"]["phone"] == "010-3333-4444"
    assert order.phone == "010-3333-4444"
    history = order.structured_data["drawing_transfer_history"]
    assert history[:2] == _HISTORY
    # 알려진 부작용(contract_notes): 연락처가 바뀌면 도면팀 '주문 변경 · 연락처' 항목이 붙는다.
    assert [h["action"] for h in history[2:]] == ["ERP_ORDER_CHANGED"]


def test_deleted_order_is_404_after_lock(client, seeded):
    order = db_session.get(Order, seeded)
    order.deleted_at = datetime.datetime.utcnow()
    db_session.commit()
    res = client.patch(f"/api/orders/{seeded}/structured/fields",
                       json={"field": "parties.customer.phone", "value": "010-3333-4444"})
    assert res.status_code == 404

"""같은 요청에서 이미 읽은 사용자를 다시 조회하지 않는다(원장 P3-8).

before_request(``_set_current_user``)가 ``g.current_user`` 를 읽은 뒤에도 ``role_required``·
주문 목록·주문 수정 화면이 같은 사용자를 PK 로 다시 읽었다(수정 화면 한 번에 4번).
:func:`foms.web.auth.get_request_user` 는 **같은 사용자이고 세션에 붙어 있을 때만** 그
객체를 다시 쓰고, 아니면 예전처럼 조회한다. 양성(조회 0)과 음성(다른 id·떨어진 객체·요청
밖은 조회)을 함께 본다.
"""

from __future__ import annotations

import contextlib

from flask import g
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.erp_shipment_settings import ERP_SHIPMENT_SETTINGS_KEY
from foms.web.auth import get_request_user
from models import Order, SystemSetting, User


@contextlib.contextmanager
def _count_user_by_id_selects():
    seen: list[str] = []

    def _before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        flat = " ".join(statement.split())
        if flat.startswith("SELECT") and "FROM users" in flat and "users.id = " in flat:
            seen.append(flat)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", _before)


def _user(username: str, role: str = "ADMIN") -> User:
    user = User(username=username, password=generate_password_hash("x"), role=role,
                team="CS", name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def test_reuses_current_user_without_query(app) -> None:
    uid = _user("req_user_same").id
    with app.test_request_context("/"):
        current = db_session.get(User, uid)
        g.current_user = current
        db_session.expire_all()  # 만료돼도(커밋 뒤와 같은 상태) 다시 쓴다 — 판정에 DB 안 감
        with _count_user_by_id_selects() as seen:
            got = get_request_user(uid)
    assert got is current
    assert seen == []


def test_other_user_id_is_queried(app) -> None:
    """음성: 세션 사용자와 다른 id 를 물으면 그 사용자를 조회한다(현재 사용자를 돌려주지 않는다)."""
    me_id = _user("req_user_me").id
    other_id = _user("req_user_other").id
    with app.test_request_context("/"):
        g.current_user = db_session.get(User, me_id)
        with _count_user_by_id_selects() as seen:
            got = get_request_user(other_id)
    assert got is not None and got.id == other_id
    assert len(seen) == 1


def test_detached_current_user_is_not_reused(app) -> None:
    """음성: 세션에서 떨어진 객체는 다시 쓰지 않는다(지연 로딩이 DetachedInstanceError 로 터진다)."""
    uid = _user("req_user_detached").id
    with app.test_request_context("/"):
        detached = db_session.get(User, uid)
        db_session.expunge(detached)
        g.current_user = detached
        with _count_user_by_id_selects() as seen:
            got = get_request_user(uid)
        assert got is not detached
        assert got.id == uid
    assert len(seen) == 1


def test_outside_request_context_queries(app) -> None:
    """음성: 요청 밖(워커 등)에서는 g 를 보지 않고 조회한다."""
    uid = _user("req_user_outside").id
    with app.app_context():
        g.current_user = db_session.get(User, uid)  # 요청 밖이면 g 에 있어도 보지 않는다
        with _count_user_by_id_selects() as seen:
            got = get_request_user(uid)
        assert got.id == uid
    assert len(seen) == 1


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _seed_shipment_settings() -> None:
    """운영처럼 출고 설정 행을 둔다. 행이 없으면 렌더 도중 JSON 파일 이관이 커밋해 이미 읽은
    사용자 객체가 만료되고, 그 다시 읽기가 셈에 섞인다(테스트 환경에만 있는 경로)."""
    db_session.add(SystemSetting(setting_key=ERP_SHIPMENT_SETTINGS_KEY,
                                 setting_value={"measurement_manager": []}))
    db_session.commit()


def test_order_edit_page_reads_user_once(client) -> None:
    """ERP 주문 수정 화면: before_request 1번만(예전 4번 — role_required·권한 판정·컨텍스트)."""
    _seed_shipment_settings()
    user = _user("req_user_edit_page")
    order = Order(received_date="2026-09-01", customer_name="사용자 재조회", phone="010-0000-0009",
                  address="Seoul", product="가구", status="RECEIVED", is_erp_order=True,
                  structured_data={})
    db_session.add(order)
    db_session.commit()
    _login(client, user)

    with _count_user_by_id_selects() as seen:
        response = client.get(f"/edit/{order.id}")

    assert response.status_code == 200
    assert len(seen) == 1, seen


def test_order_list_and_role_gate_read_user_once(client) -> None:
    """주문 목록(``/``)과 role_required 에서 막히는 응답(없는 주문 수정 → 302)도 1번만."""
    user = _user("req_user_list_page")
    _login(client, user)

    with _count_user_by_id_selects() as list_seen:
        listing = client.get("/")
    with _count_user_by_id_selects() as gate_seen:
        missing = client.get("/edit/99999999")

    assert listing.status_code == 200
    assert missing.status_code == 302
    assert len(list_seen) == 1, list_seen
    assert len(gate_seen) == 1, gate_seen


def test_role_gate_still_rejects_wrong_role(client) -> None:
    """음성: 다시 쓴 사용자로도 역할 판정은 그대로다 — VIEWER 는 수정 화면에서 튕긴다."""
    viewer = _user("req_user_viewer", role="VIEWER")
    order = Order(received_date="2026-09-01", customer_name="권한 확인", phone="010-0000-0010",
                  address="Seoul", product="가구", status="RECEIVED", is_erp_order=True,
                  structured_data={})
    db_session.add(order)
    db_session.commit()
    order_id = order.id
    _login(client, viewer)

    response = client.get(f"/edit/{order_id}")

    assert response.status_code == 302
    assert f"/edit/{order_id}" not in (response.headers.get("Location") or "")

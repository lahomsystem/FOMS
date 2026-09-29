"""수정요청 출처·받은 경로 선택 필드(설계서 2026-09-29 §4.1 · §7.1 S1).

``POST /api/orders/<id>/request-revision`` 본문에 선택 키 ``source``(customer·sales)·
``received_via``(phone·kakao·store)를 더한다. 키가 없으면 지금과 같은 항목(옛 호출자 셋 —
도면 탭·대시보드·태블릿 — 은 안 보낸다), 목록 밖 값이면 **쓰기 전에** 400
``INVALID_REVISION_SOURCE``. 고객 요청이면 도면팀 알림 제목이 "고객 요청 · 도면 수정"이 되고
작업실 화면값(이력·요청·스레드)에 ``source_tag`` "고객 요청 · 1차 · 카톡 답장"이 붙는다.
실제 라우트를 탄다.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest
from flask import template_rendered
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_revision as revision_api
from db import db_session
from foms.services.orders.drawing_revision_source import (
    INVALID_REVISION_SOURCE,
    notification_message_prefix,
    notification_title,
    parse_revision_source,
    request_rounds,
    revision_source_tag,
)
from models import Notification, Order, User

SALES = "영업출처"


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(revision_api, "emit_erp_notification_to_users", lambda *a, **k: None)


def _user(username, *, role="MANAGER", team="SALES", name=SALES):
    u = User(username=username, password=generate_password_hash("pw"), role=role, team=team,
             name=name, is_active=True)
    db_session.add(u)
    db_session.commit()
    return {"id": u.id, "username": u.username, "role": u.role}


def _login(client, who):
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = who["id"], who["username"], who["role"]


def _order():
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="출처고객",
                  phone="010-5", address="서울", product="붙박이장", status="DRAWING",
                  manager_name=SALES, is_erp_order=True, erp_stage_code="DRAWING", structured_data={})
    db_session.add(order)
    db_session.commit()
    v1 = f"orders/{order.id}/drawing_wizard/exports/v1.png"
    order.structured_data = {
        "parties": {"customer": {"name": "출처고객"}, "manager": {"name": SALES}},
        "workflow": {"stage": "DRAWING"},
        "drawing_status": "TRANSFERRED",
        "drawing_current_files": [{"key": v1, "filename": "v1.png"}],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "at": "2026-09-29 01:00:00", "files": [{"key": v1}],
             "previous_current_files": []},
        ],
    }
    db_session.commit()
    return order.id


def _sd(oid):
    db_session.expire_all()
    return dict(db_session.get(Order, oid).structured_data or {})


def _version(oid):
    db_session.expire_all()
    return db_session.get(Order, oid).mutation_version


def _requests(sd):
    return [h for h in sd.get("drawing_transfer_history") or [] if h.get("action") == "REQUEST_REVISION"]


def _post(client, oid, **body):
    return client.post(f"/api/orders/{oid}/request-revision", json={"note": "문짝 폭 줄여 주세요", **body})


# ── 순수 함수 ────────────────────────────────────────────────────────────────
def test_parse_missing_or_null_keys_is_empty():
    assert parse_revision_source({}) == ({}, None)
    assert parse_revision_source({"source": None, "received_via": None}) == ({}, None)
    assert parse_revision_source(None) == ({}, None)


def test_parse_customer_with_via():
    assert parse_revision_source({"source": "customer", "received_via": "kakao"}) == (
        {"source": "customer", "received_via": "kakao"}, None)
    assert parse_revision_source({"source": "customer"}) == ({"source": "customer"}, None)
    # 받은 경로 칩은 선택 사항 — 빈 문자열은 고르지 않은 것.
    assert parse_revision_source({"source": "customer", "received_via": ""}) == ({"source": "customer"}, None)


def test_parse_sales_drops_via():
    assert parse_revision_source({"source": "sales", "received_via": "kakao"}) == ({"source": "sales"}, None)


@pytest.mark.parametrize("body", [
    {"source": "boss"},
    {"source": "customer", "received_via": "fax"},
    {"source": 1},
    {"source": "customer", "received_via": ["kakao"]},
    {"received_via": "fax"},
])
def test_parse_out_of_list_is_error(body):
    assert parse_revision_source(body) == ({}, INVALID_REVISION_SOURCE)


def test_source_tag_and_titles():
    assert revision_source_tag({"source": "customer", "received_via": "kakao"}, 1) == "고객 요청 · 1차 · 카톡 답장"
    assert revision_source_tag({"source": "customer"}, 2) == "고객 요청 · 2차"
    assert revision_source_tag({"source": "sales"}, 1) == ""
    assert revision_source_tag({}, 1) == ""  # 옛 항목 = 영업 의견
    assert notification_title({"source": "customer"}) == "고객 요청 · 도면 수정"
    assert notification_title({}) == "도면 수정 요청"
    assert notification_title({"source": "sales"}) == "도면 수정 요청"
    assert "수정요청 고침" in notification_title({"source": "customer"}, edited=True)
    assert "수정요청 고침" in notification_title({}, edited=True)
    assert notification_message_prefix({"source": "customer", "received_via": "kakao"}) == "[고객 요청 · 카톡 답장] "
    assert notification_message_prefix({"source": "customer"}) == "[고객 요청] "
    assert notification_message_prefix({"source": "sales"}) == ""


def test_request_rounds_counts_round_at_request_time():
    history = [
        {"action": "TRANSFER"},
        {"action": "REQUEST_REVISION"},          # 1차에 대한 요청
        {"action": "TRANSFER"},
        {"action": "TRANSFER"},                  # 요청 없는 추가 전달 — 여전히 2차
        {"action": "REQUEST_REVISION"},          # 2차에 대한 요청
    ]
    assert request_rounds(history) == {1: 1, 4: 2}


# ── 라우트 ───────────────────────────────────────────────────────────────────
def test_customer_source_and_via_are_saved(client, quiet):
    sales = _user("src_a")
    oid = _order()
    _login(client, sales)
    res = _post(client, oid, source="customer", received_via="kakao")
    assert res.status_code == 200, res.get_json()
    entry = _requests(_sd(oid))[-1]
    assert entry["source"] == "customer"
    assert entry["received_via"] == "kakao"


def test_missing_keys_keep_today_entry_shape(client, quiet):
    sales = _user("src_b")
    oid = _order()
    _login(client, sales)
    res = _post(client, oid)
    assert res.status_code == 200
    entry = _requests(_sd(oid))[-1]
    assert "source" not in entry and "received_via" not in entry


@pytest.mark.parametrize("body", [{"source": "boss"}, {"source": "customer", "received_via": "fax"}])
def test_out_of_list_is_400_and_writes_nothing(client, quiet, body):
    sales = _user("src_c_" + str(len(body)))
    oid = _order()
    before = _version(oid)
    _login(client, sales)
    res = _post(client, oid, **body)
    assert res.status_code == 400
    data = res.get_json()
    assert data["success"] is False
    assert data["code"] == "INVALID_REVISION_SOURCE" and data["error"] == "INVALID_REVISION_SOURCE"
    sd = _sd(oid)
    assert sd["drawing_status"] == "TRANSFERRED"
    assert _requests(sd) == []
    assert _version(oid) == before
    assert db_session.query(Notification).filter(Notification.order_id == oid).count() == 0


def test_sales_source_drops_via(client, quiet):
    sales = _user("src_d")
    oid = _order()
    _login(client, sales)
    assert _post(client, oid, source="sales", received_via="kakao").status_code == 200
    entry = _requests(_sd(oid))[-1]
    assert entry["source"] == "sales" and "received_via" not in entry


def test_customer_notification_title_and_prefix(client, quiet):
    sales = _user("src_e")
    oid = _order()
    _login(client, sales)
    assert _post(client, oid, source="customer", received_via="kakao").status_code == 200
    notif = db_session.query(Notification).filter(Notification.order_id == oid).one()
    assert notif.notification_type == "DRAWING_REVISION"
    assert notif.target_team == "DRAWING"
    assert notif.title == "고객 요청 · 도면 수정"
    assert notif.message.startswith("[고객 요청 · 카톡 답장] ")


def test_sales_notification_title_unchanged(client, quiet):
    sales = _user("src_f")
    oid = _order()
    _login(client, sales)
    assert _post(client, oid).status_code == 200
    notif = db_session.query(Notification).filter(Notification.order_id == oid).one()
    assert notif.title == "도면 수정 요청"
    assert not notif.message.startswith("[")


def test_files_contract_still_400_with_valid_source(client, quiet):
    sales = _user("src_g")
    oid = _order()
    _login(client, sales)
    res = _post(client, oid, source="customer", files=[{"key": "orders/999/drawing_gateway/x.png"}])
    assert res.status_code == 400
    assert res.get_json()["code"] == "INVALID_REVISION_FILE"
    assert _requests(_sd(oid)) == []


def test_second_request_while_returned_is_400(client, quiet):
    sales = _user("src_h")
    oid = _order()
    _login(client, sales)
    assert _post(client, oid, source="customer").status_code == 200
    res = _post(client, oid, source="customer")
    assert res.status_code == 400
    assert len(_requests(_sd(oid))) == 1


def test_cancel_keeps_source_in_revision_cancelled(client, quiet):
    sales = _user("src_i")
    oid = _order()
    _login(client, sales)
    assert _post(client, oid, source="customer", received_via="phone").status_code == 200
    res = client.post(f"/api/orders/{oid}/cancel-revision-request", json={})
    assert res.status_code == 200, res.get_json()
    cancelled = [h for h in _sd(oid)["drawing_transfer_history"] if h.get("action") == "REVISION_CANCELLED"]
    assert cancelled[-1]["request"]["source"] == "customer"
    assert cancelled[-1]["request"]["received_via"] == "phone"


# ── 작업실 화면값 source_tag ─────────────────────────────────────────────────
@contextmanager
def _captured(app):
    recorded = []

    def record(sender, template, context, **extra):
        recorded.append(context)

    template_rendered.connect(record, app)
    try:
        yield recorded
    finally:
        template_rendered.disconnect(record, app)


def test_workbench_values_carry_source_tag(app, client, quiet):
    sales = _user("src_j")
    oid = _order()
    _login(client, sales)
    assert _post(client, oid, source="customer", received_via="kakao").status_code == 200
    with _captured(app) as contexts:
        res = client.get(f"/erp/drawing-workbench/{oid}")
    assert res.status_code == 200
    ctx = next(c for c in contexts if "customer_send" in c)
    hist = [h for h in ctx["history"] if h.get("action") == "REQUEST_REVISION"]
    assert hist[-1]["source_tag"] == "고객 요청 · 1차 · 카톡 답장"
    assert ctx["revision_requests"][0]["source_tag"] == "고객 요청 · 1차 · 카톡 답장"
    thread = [e for e in ctx["mobile_handoff_thread"] if (e.get("action") or "") == "REQUEST_REVISION"]
    assert thread[0]["source_tag"] == "고객 요청 · 1차 · 카톡 답장"
    transfer = [h for h in ctx["history"] if h.get("action") == "TRANSFER"]
    assert transfer[0].get("source_tag", "") == ""


def test_workbench_list_row_latest_request_is_customer(app, client, quiet):
    sales = _user("src_k")
    oid = _order()
    _login(client, sales)
    assert _post(client, oid, source="customer").status_code == 200
    with _captured(app) as contexts:
        res = client.get(f"/erp/drawing-workbench?focus_order={oid}")
    assert res.status_code == 200
    rows = [r for c in contexts if "rows" in c for r in (c["rows"] or []) if r.get("id") == oid]
    assert rows, "목록 행이 없다"
    assert rows[0]["latest_request_is_customer"] is True
    assert rows[0]["round_text"] == "1차"

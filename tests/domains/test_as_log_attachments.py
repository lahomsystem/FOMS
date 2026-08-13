"""AS 기록별 첨부(AS-FRESH-01 T1~T4) 계약.

첨부는 ``order_attachments.as_log_id`` 로 as_log 항목에 결합된다. 이 축이 무너지면
기록 줄 썸네일과 PUSH 회차 필터가 함께 조용히 죽으므로, 결합 검증·응답 계약·렌더
주입(그리고 N+1 금지)을 여기서 고정한다.
"""

from __future__ import annotations

import io
from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.files.common import resolve_as_log_ref
from foms.services.orders.as_round_chart import build_as_round_chart_view
from models import Order, OrderAttachment, User


class _FakeOrder:
    def __init__(self, structured_data):
        self.structured_data = structured_data


def _sd_with_log(*entries):
    return {"shipment": {"as_log": list(entries)}}


def _login_admin(client, username="as-attach-admin") -> int:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="CS",
        name="AS 첨부 관리자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
    return user.id


def _as_order(**shipment):
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="AS 첨부 고객",
        phone="010-1234-5678",
        address="Seoul",
        product="붙박이장",
        status="AS_RECEIVED",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "AS_RECEIVED"}, "shipment": dict(shipment)},
    )
    db_session.add(order)
    db_session.commit()
    return order


# ── 결합 검증 (T2) ────────────────────────────────────────────────────────────


def test_resolve_as_log_ref_accepts_existing_entry() -> None:
    order = _FakeOrder(_sd_with_log({"id": "al_1", "type": "memo"}))

    assert resolve_as_log_ref(order, "as", "al_1") == (True, "al_1", None)


def test_resolve_as_log_ref_allows_empty() -> None:
    """값이 없으면 결합 없이 통과한다 — 기존 업로드 흐름이 그대로 산다."""
    order = _FakeOrder({})

    assert resolve_as_log_ref(order, "as", None) == (True, None, None)
    assert resolve_as_log_ref(order, "measurement", "") == (True, None, None)


def test_resolve_as_log_ref_rejects_unknown_entry() -> None:
    """임의 문자열이 컬럼에 들어가면 결합이 영원히 풀리지 않는 유령이 된다."""
    order = _FakeOrder(_sd_with_log({"id": "al_1", "type": "memo"}))

    ok, value, err = resolve_as_log_ref(order, "as", "al_none")

    assert (ok, value) == (False, None)
    assert "AS 기록" in err


def test_resolve_as_log_ref_rejects_deleted_entry() -> None:
    order = _FakeOrder(_sd_with_log({"id": "al_1", "type": "memo", "deleted": True}))

    assert resolve_as_log_ref(order, "as", "al_1")[0] is False


def test_resolve_as_log_ref_rejects_non_as_category() -> None:
    """결합 축은 AS 전용 — 다른 분류에 붙으면 회차 필터가 조용히 오작동한다."""
    order = _FakeOrder(_sd_with_log({"id": "al_1", "type": "memo"}))

    ok, _value, err = resolve_as_log_ref(order, "drawing", "al_1")

    assert ok is False
    assert "AS 첨부에만" in err


def test_attachment_upload_binds_as_log_id(client) -> None:
    _login_admin(client)
    order = _as_order(as_log=[{"id": "al_up", "type": "memo", "text": "현장 사진"}])

    response = client.post(
        f"/api/orders/{order.id}/attachments",
        data={
            "file": (io.BytesIO(b"fake-image-bytes"), "as-photo.jpg"),
            "category": "as",
            "as_log_id": "al_up",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["attachment"]["as_log_id"] == "al_up"

    saved = db_session.get(OrderAttachment, body["attachment"]["id"])
    assert saved.as_log_id == "al_up"


def test_attachment_upload_rejects_unknown_as_log_id(client) -> None:
    _login_admin(client, username="as-attach-admin-2")
    order = _as_order(as_log=[{"id": "al_up", "type": "memo"}])

    response = client.post(
        f"/api/orders/{order.id}/attachments",
        data={
            "file": (io.BytesIO(b"fake-image-bytes"), "as-photo.jpg"),
            "category": "as",
            "as_log_id": "al_ghost",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert db_session.query(OrderAttachment).filter(
        OrderAttachment.order_id == order.id).count() == 0


# ── 접수 응답 (T3) ────────────────────────────────────────────────────────────


def test_as_register_returns_reception_log_id(client) -> None:
    """접수 모달이 올린 파일을 접수 기록에 결합하려면 항목 id 가 응답에 있어야 한다."""
    _login_admin(client, username="as-attach-admin-3")
    order = _as_order()

    response = client.post(
        f"/api/orders/{order.id}/as/register", json={"as_content": "후드 교체 요청"}
    )

    assert response.status_code == 200
    log_id = response.get_json()["reception_log_id"]
    assert log_id.startswith("al_")

    db_session.expire_all()
    saved = db_session.get(Order, order.id)
    entries = saved.structured_data["shipment"]["as_log"]
    assert any(e.get("id") == log_id and e.get("type") == "reception" for e in entries)


def test_as_register_reuses_log_id_on_unedited_rereigster(client) -> None:
    """무편집 재접수는 append 를 건너뛰지만 **기존 항목 id** 를 돌려준다(첨부 고아 방지)."""
    _login_admin(client, username="as-attach-admin-4")
    order = _as_order()

    first = client.post(
        f"/api/orders/{order.id}/as/register", json={"as_content": "문짝 처짐"}
    )
    first_id = first.get_json()["reception_log_id"]

    second = client.post(
        f"/api/orders/{order.id}/as/register", json={"as_content": "문짝 처짐"}
    )

    assert second.status_code == 200
    assert second.get_json()["reception_log_id"] == first_id
    db_session.expire_all()
    saved = db_session.get(Order, order.id)
    receptions = [
        e for e in saved.structured_data["shipment"]["as_log"]
        if e.get("type") == "reception"
    ]
    assert len(receptions) == 1  # append-only 리스트에 중복이 남지 않는다


# ── 렌더 주입 (T4) ────────────────────────────────────────────────────────────


def test_round_chart_view_attaches_files_to_entries() -> None:
    sd = _sd_with_log(
        {"id": "al_1", "type": "memo", "text": "상판 교체", "ts": "2026-08-13T01:00:00",
         "round": 1},
    )
    files = {"al_1": [{"id": 7, "filename": "a.jpg", "is_image": True,
                       "view_url": "/v/a.jpg", "thumb_url": "/t/a.jpg"}]}

    view = build_as_round_chart_view(sd, attachments_by_log_id=files)

    entry = view["rounds"][0]["entries"][0]
    assert entry["files"][0]["filename"] == "a.jpg"


def test_round_chart_view_without_attachment_map_has_no_files_key() -> None:
    """미주입이면 기존 렌더와 동일 — files 키가 없어야 템플릿 분기가 그대로 산다."""
    sd = _sd_with_log(
        {"id": "al_1", "type": "memo", "text": "상판 교체", "ts": "2026-08-13T01:00:00"},
    )

    view = build_as_round_chart_view(sd)

    assert "files" not in view["rounds"][0]["entries"][0]


def test_as_timeline_fragment_loads_attachments_in_one_query(client) -> None:
    """첨부 조회는 주문당 1쿼리 — 항목마다 돌면 회차 차트가 N+1 이 된다."""
    _login_admin(client, username="as-attach-admin-5")
    order = _as_order(
        as_log=[
            {"id": f"al_{i}", "type": "memo", "text": f"기록{i}",
             "ts": f"2026-08-13T0{i}:00:00", "round": 1}
            for i in range(1, 4)
        ]
    )
    db_session.add_all([
        OrderAttachment(
            order_id=order.id, filename=f"as-{i}.jpg", file_type="image",
            category="as", as_log_id=f"al_{i}", storage_key=f"orders/{order.id}/as-{i}.jpg",
        )
        for i in range(1, 4)
    ])
    db_session.commit()

    from foms.web.cs import as_dashboard as as_dashboard_module

    calls = {"n": 0}
    original = as_dashboard_module._as_attachments_by_log_id

    def _counting(db, order_id):
        calls["n"] += 1
        return original(db, order_id)

    as_dashboard_module._as_attachments_by_log_id = _counting
    try:
        response = client.get(f"/erp/as/timeline/{order.id}")
    finally:
        as_dashboard_module._as_attachments_by_log_id = original

    assert response.status_code == 200
    assert calls["n"] == 1
    html = response.get_data(as_text=True)
    assert html.count('class="as-rchart-file"') == 3

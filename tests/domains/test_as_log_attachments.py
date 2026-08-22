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
from foms.services.attachment_sort import parse_attachment_sort_order
from foms.services.orders.as_round_chart import build_as_round_chart_view
from foms.services.orders.as_upload_anchor import (
    AS_UPLOAD_PARK_FLAG,
    peek_as_upload_anchor,
)
from models import Order, OrderAttachment, User


class _FakeOrder:
    def __init__(self, structured_data):
        self.structured_data = structured_data


def _sd_with_log(*entries):
    return {"shipment": {"as_log": list(entries)}}


def _login_user(
    client,
    username: str,
    *,
    role: str = "ADMIN",
    team: str = "CS",
    name: str = "AS 첨부 사용자",
) -> int:
    """테스트 사용자를 만들고 세션에 넣는다."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=name,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
    return user.id


def _login_admin(client, username="as-attach-admin") -> int:
    return _login_user(client, username, role="ADMIN", team="CS", name="AS 첨부 관리자")


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


def test_parse_attachment_sort_order_accepts_zero() -> None:
    assert parse_attachment_sort_order(0) == (True, 0, None)
    assert parse_attachment_sort_order("0") == (True, 0, None)
    assert parse_attachment_sort_order(None) == (True, None, None)


def test_parse_attachment_sort_order_rejects_bool_and_overflow() -> None:
    assert parse_attachment_sort_order(True)[0] is False
    assert parse_attachment_sort_order(10000)[0] is False


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
    assert saved.sort_order == 0
    assert body["attachment"]["sort_order"] == 0


def test_attachment_upload_stores_explicit_sort_order(client) -> None:
    _login_admin(client, username="as-attach-admin-sort")
    order = _as_order(as_log=[{"id": "al_up", "type": "memo", "text": "현장 사진"}])

    response = client.post(
        f"/api/orders/{order.id}/attachments",
        data={
            "file": (io.BytesIO(b"fake-image-bytes"), "as-photo.jpg"),
            "category": "as",
            "as_log_id": "al_up",
            "sort_order": "2",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    saved = db_session.get(OrderAttachment, response.get_json()["attachment"]["id"])
    assert saved.sort_order == 2


def test_attachment_upload_rejects_bad_sort_order(client) -> None:
    _login_admin(client, username="as-attach-admin-sort-bad")
    order = _as_order(as_log=[{"id": "al_up", "type": "memo"}])

    response = client.post(
        f"/api/orders/{order.id}/attachments",
        data={
            "file": (io.BytesIO(b"fake-image-bytes"), "as-photo.jpg"),
            "category": "as",
            "as_log_id": "al_up",
            "sort_order": "nope",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert db_session.query(OrderAttachment).filter(
        OrderAttachment.order_id == order.id).count() == 0


def test_attachment_reorder_writes_dense_sort_order(client) -> None:
    _login_admin(client, username="as-attach-admin-reorder")
    order = _as_order(as_log=[{"id": "al_up", "type": "memo", "text": "사진"}])
    rows = [
        OrderAttachment(
            order_id=order.id, filename=f"as-{i}.jpg", file_type="image",
            category="as", as_log_id="al_up", sort_order=i,
            storage_key=f"orders/{order.id}/as-{i}.jpg",
        )
        for i in range(3)
    ]
    db_session.add_all(rows)
    db_session.commit()
    ids = [row.id for row in rows]
    order_id = order.id

    response = client.post(
        f"/api/orders/{order_id}/attachments/reorder",
        json={"as_log_id": "al_up", "ids": [ids[2], ids[0], ids[1]]},
    )

    assert response.status_code == 200
    body_ids = [item["id"] for item in response.get_json()["attachments"]]
    assert body_ids == [ids[2], ids[0], ids[1]]
    db_session.expire_all()
    by_id = {row.id: row for row in db_session.query(OrderAttachment).filter(
        OrderAttachment.order_id == order_id).all()}
    assert by_id[ids[2]].sort_order == 0
    assert by_id[ids[0]].sort_order == 1
    assert by_id[ids[1]].sort_order == 2


def test_attachment_reorder_rejects_partial_list(client) -> None:
    _login_admin(client, username="as-attach-admin-reorder-bad")
    order = _as_order(as_log=[{"id": "al_up", "type": "memo"}])
    db_session.add_all([
        OrderAttachment(
            order_id=order.id, filename=f"as-{i}.jpg", file_type="image",
            category="as", as_log_id="al_up",
            storage_key=f"orders/{order.id}/as-{i}.jpg",
        )
        for i in range(2)
    ])
    db_session.commit()
    first_id = db_session.query(OrderAttachment).filter(
        OrderAttachment.order_id == order.id).first().id

    response = client.post(
        f"/api/orders/{order.id}/attachments/reorder",
        json={"as_log_id": "al_up", "ids": [first_id]},
    )

    assert response.status_code == 400


def _as_reorder_group(uploader_id: int | None = 99) -> tuple[int, list[int]]:
    """타인 업로드 AS 첨부 2장 그룹을 만들고 (order_id, ids) 를 돌려준다."""
    order = _as_order(as_log=[{"id": "al_up", "type": "memo", "text": "사진"}])
    rows = [
        OrderAttachment(
            order_id=order.id, filename=f"as-{i}.jpg", file_type="image",
            category="as", as_log_id="al_up", sort_order=i, user_id=uploader_id,
            storage_key=f"orders/{order.id}/as-{i}.jpg",
        )
        for i in range(2)
    ]
    db_session.add_all(rows)
    db_session.commit()
    return order.id, [row.id for row in rows]


def test_attachment_reorder_allows_cs_staff_on_others_files(client) -> None:
    _login_user(client, "as-attach-cs-reorder", role="STAFF", team="CS", name="CS직원")
    order_id, ids = _as_reorder_group()

    response = client.post(
        f"/api/orders/{order_id}/attachments/reorder",
        json={"as_log_id": "al_up", "ids": [ids[1], ids[0]]},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.get_json()["attachments"]] == [ids[1], ids[0]]


def test_attachment_reorder_allows_manager_role_on_others_files(client) -> None:
    _login_user(client, "as-attach-mgr-reorder", role="MANAGER", team="SALES", name="박매니저")
    order_id, ids = _as_reorder_group()

    response = client.post(
        f"/api/orders/{order_id}/attachments/reorder",
        json={"as_log_id": "al_up", "ids": [ids[1], ids[0]]},
    )

    assert response.status_code == 200


def test_attachment_reorder_denies_sales_outsider(client) -> None:
    _login_user(client, "as-attach-sales-reorder", role="STAFF", team="SALES", name="다른영업")
    order_id, ids = _as_reorder_group()

    response = client.post(
        f"/api/orders/{order_id}/attachments/reorder",
        json={"as_log_id": "al_up", "ids": [ids[1], ids[0]]},
    )

    assert response.status_code == 403


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


# ── 암시적 앵커 (AS-BIND-01) ──────────────────────────────────────────────────


def test_peek_anchor_uses_current_round_reception_not_global_first() -> None:
    """2회차 사진은 1회차 접수 칸에 붙지 않는다."""
    sd = _sd_with_log(
        {"id": "al_r1", "type": "reception", "text": "1차", "round": 1},
        {"id": "al_v", "type": "verdict", "verdict": "unresolved", "text": "미결",
         "round": 1},
        {"id": "al_r2", "type": "reception", "text": "2차", "round": 2},
    )

    assert peek_as_upload_anchor(sd) == "al_r2"


def test_peek_anchor_ignores_plan_and_prefers_park() -> None:
    """방안 줄은 앵커가 아니다. 주차 플래그만 접수 다음 후보."""
    sd = _sd_with_log(
        {"id": "al_plan", "type": "plan", "text": "방문", "round": 1},
        {"id": "al_park", "type": "memo", "text": "첨부 파일", "round": 1,
         AS_UPLOAD_PARK_FLAG: True},
    )

    assert peek_as_upload_anchor(sd) == "al_park"


def test_empty_as_upload_binds_current_round_reception(client) -> None:
    """공통 첨부 AS(빈 as_log_id)는 현재 회차 접수 줄에 붙는다."""
    _login_admin(client, username="as-bind-rec")
    order = _as_order(as_log=[
        {"id": "al_rec", "type": "reception", "text": "접수", "round": 1},
    ])

    response = client.post(
        f"/api/orders/{order.id}/attachments",
        data={
            "file": (io.BytesIO(b"fake-image-bytes"), "as-photo.jpg"),
            "category": "as",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.get_json()["attachment"]["as_log_id"] == "al_rec"


def test_empty_as_upload_parks_when_only_plan_exists(client) -> None:
    """방안만 있으면 그 줄에 붙이지 않고 주차 메모를 만든다."""
    _login_admin(client, username="as-bind-plan")
    order = _as_order(as_log=[
        {"id": "al_plan", "type": "plan", "text": "방문 예정", "round": 1},
    ])
    order_id = order.id

    response = client.post(
        f"/api/orders/{order_id}/attachments",
        data={
            "file": (io.BytesIO(b"fake-image-bytes"), "as-photo.jpg"),
            "category": "as",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    body = response.get_json()["attachment"]
    assert body["as_log_id"] != "al_plan"
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    park = next(
        e for e in saved.structured_data["shipment"]["as_log"]
        if e.get("id") == body["as_log_id"]
    )
    assert park.get(AS_UPLOAD_PARK_FLAG) is True
    assert park.get("type") == "memo"


def test_empty_as_upload_does_not_bind_round1_reception_in_round2(client) -> None:
    """미결 후 2회차 업로드는 1회차 접수 id 를 쓰지 않는다."""
    _login_admin(client, username="as-bind-r2")
    order = _as_order(as_log=[
        {"id": "al_r1", "type": "reception", "text": "1차", "round": 1},
        {"id": "al_v", "type": "verdict", "verdict": "unresolved", "text": "미결",
         "round": 1},
    ])

    response = client.post(
        f"/api/orders/{order.id}/attachments",
        data={
            "file": (io.BytesIO(b"fake-image-bytes"), "as-photo.jpg"),
            "category": "as",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.get_json()["attachment"]["as_log_id"] != "al_r1"


def test_as_register_promotes_parked_attachments(client) -> None:
    """주차 사진을 올린 뒤 접수하면 접수 줄로 옮기고 주차 메모는 숨긴다."""
    _login_admin(client, username="as-bind-promote")
    order = _as_order()
    order_id = order.id
    park_res = client.post(f"/api/orders/{order_id}/as/upload-anchor", json={})
    assert park_res.status_code == 200
    park_id = park_res.get_json()["as_log_id"]

    up = client.post(
        f"/api/orders/{order_id}/attachments",
        data={
            "file": (io.BytesIO(b"fake-image-bytes"), "parked.jpg"),
            "category": "as",
            "as_log_id": park_id,
        },
        content_type="multipart/form-data",
    )
    assert up.status_code == 200
    att_id = up.get_json()["attachment"]["id"]

    reg = client.post(
        f"/api/orders/{order_id}/as/register", json={"as_content": "후드 소음"}
    )
    assert reg.status_code == 200
    reception_id = reg.get_json()["reception_log_id"]
    assert reception_id
    assert reception_id != park_id

    db_session.expire_all()
    saved_att = db_session.get(OrderAttachment, att_id)
    assert saved_att.as_log_id == reception_id
    saved = db_session.get(Order, order_id)
    park = next(
        e for e in saved.structured_data["shipment"]["as_log"] if e.get("id") == park_id
    )
    assert park.get("deleted") is True


def test_as_register_does_not_promote_unbound_legacy(client) -> None:
    """as_log_id 없는 레거시 파일은 접수 때 자동으로 안 붙는다."""
    _login_admin(client, username="as-bind-legacy")
    order = _as_order()
    legacy = OrderAttachment(
        order_id=order.id, filename="old.jpg", file_type="image",
        category="as", as_log_id=None, storage_key=f"orders/{order.id}/old.jpg",
    )
    db_session.add(legacy)
    db_session.commit()
    legacy_id = legacy.id

    client.post(
        f"/api/orders/{order.id}/as/register", json={"as_content": "레거시 유지"}
    )

    db_session.expire_all()
    assert db_session.get(OrderAttachment, legacy_id).as_log_id is None


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


def test_round_chart_html_follows_sort_order_not_id(client) -> None:
    """차트 썸네일은 sort_order 순. id 삽입 순과 달라도 된다."""
    _login_admin(client, username="as-attach-admin-sort-html")
    order = _as_order(
        as_log=[{
            "id": "al_up", "type": "memo", "text": "사진",
            "ts": "2026-08-13T01:00:00", "round": 1,
        }]
    )
    db_session.add_all([
        OrderAttachment(
            order_id=order.id, filename="late.jpg", file_type="image",
            category="as", as_log_id="al_up", sort_order=2,
            storage_key=f"orders/{order.id}/late.jpg",
        ),
        OrderAttachment(
            order_id=order.id, filename="first.jpg", file_type="image",
            category="as", as_log_id="al_up", sort_order=0,
            storage_key=f"orders/{order.id}/first.jpg",
        ),
        OrderAttachment(
            order_id=order.id, filename="mid.jpg", file_type="image",
            category="as", as_log_id="al_up", sort_order=1,
            storage_key=f"orders/{order.id}/mid.jpg",
        ),
    ])
    db_session.commit()

    response = client.get(f"/erp/as/timeline/{order.id}")
    html = response.get_data(as_text=True)
    assert html.find("first.jpg") < html.find("mid.jpg") < html.find("late.jpg")

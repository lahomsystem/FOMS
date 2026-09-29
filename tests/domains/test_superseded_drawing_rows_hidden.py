"""교체된 옛 도면 행은 생산·시공·출고·발주방 화면 목록에 나오지 않는다(2026-09-29).

수령 확정이 옛 도면을 지우지 않게 되면서 ``category='drawing'`` 첨부 행이 남는다. 예전에는
확정 때 지워져 확정 뒤(=생산·시공·출고 단계) 화면에 안 나왔다. 그 모습을 지키려고 도면 첨부를
보여 주는 곳은 :func:`foms.services.drawing_confirm_cleanup.superseded_drawing_keys` 로 옛 도면
행을 뺀다. 전달 이력에 오른 적 없는 첨부 탭 '도면' 업로드와 다른 분류 첨부는 그대로다.

대상(브리프 4번 전수 표에서 막기로 한 곳):
* ``GET /api/orders/<id>/attachments`` — 생산·시공 대시보드 '도면' 탭, ERP 첨부 탭
* 시공 모바일 카드 미리보기·+N (``construction_dashboard_display``)
* 모바일 v2 큐 미리보기·개수·상세 첨부 그리드 (``erp_mobile_order_display`` — 생산 목록 미리보기,
  출고·시공 도면 전용 카드, 모바일 상세)
* 발주 PUSH(``push_kind='drawing'`` → 발주방) 첨부
"""

from __future__ import annotations

from sqlalchemy import event
from werkzeug.security import generate_password_hash

import foms.api.channel.channel_integration as channel_integration
from db import db_session, engine
from foms.services import erp_mobile_order_display as mobile
from foms.services.construction_dashboard_display import (
    build_construction_preview_attachments_map,
    enrich_construction_mobile_rows,
)
from models import Order, OrderAttachment, User


def _seed_confirmed_after_retransfer() -> tuple[int, dict[str, str]]:
    """1차 v1 → 수정요청 → v2 로 교체 → 확정된 주문 + 첨부 행 4개(옛 도면 v1 포함)."""
    order = Order(received_date="2026-09-29", customer_name="표면", phone="010-0000-0000",
                  address="Seoul", product="붙박이장", status="PRODUCTION", is_erp_order=True,
                  structured_data={})
    db_session.add(order)
    db_session.flush()
    oid = order.id
    keys = {
        "v1": f"orders/{oid}/drawing_wizard/exports/v1.png",
        "v2": f"orders/{oid}/drawing_wizard/exports/v2.png",
        "sketch": f"orders/{oid}/attachments/site_sketch.png",
        "measure": f"orders/{oid}/attachments/measure.jpg",
    }
    categories = {"v1": "drawing", "v2": "drawing", "sketch": "drawing", "measure": "measurement"}
    for name, key in keys.items():
        db_session.add(OrderAttachment(order_id=oid, filename=key.rsplit("/", 1)[-1],
                                       file_type="image", category=categories[name],
                                       storage_key=key))
    v1, v2 = {"key": keys["v1"], "filename": "v1.png"}, {"key": keys["v2"], "filename": "v2.png"}
    order.structured_data = {
        "workflow": {"stage": "PRODUCTION"},
        "drawing_status": "CONFIRMED",
        "drawing_current_files": [v2],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "mode": "APPEND", "files": [v1], "previous_current_files": []},
            {"action": "REQUEST_REVISION", "files": []},
            {"action": "TRANSFER", "mode": "REPLACE", "replace_target_keys": [keys["v1"]],
             "files": [v2], "previous_current_files": [v1]},
            {"action": "CONFIRM_RECEIPT", "files": [v2]},
        ],
    }
    db_session.commit()
    return oid, keys


def _login_admin(client, username: str = "superseded_admin") -> None:
    user = User(username=username, password=generate_password_hash("pass"), role="ADMIN",
                team="SALES", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _names(keys: dict[str, str], *which: str) -> set[str]:
    return {keys[w].rsplit("/", 1)[-1] for w in which}


def test_attachment_list_api_hides_replaced_drawing(client):
    """생산·시공 대시보드 '도면' 탭이 쓰는 목록 API — 옛 도면만 빠진다(휴지통 조회는 전부)."""
    oid, keys = _seed_confirmed_after_retransfer()
    _login_admin(client)

    listed = {a["storage_key"] for a in
              client.get(f"/api/orders/{oid}/attachments").get_json()["attachments"]}
    assert listed == {keys["v2"], keys["sketch"], keys["measure"]}

    drawing = {a["storage_key"] for a in
               client.get(f"/api/orders/{oid}/attachments?category=drawing")
               .get_json()["attachments"]}
    assert drawing == {keys["v2"], keys["sketch"]}

    trash_view = {a["storage_key"] for a in
                  client.get(f"/api/orders/{oid}/attachments?include_deleted=1")
                  .get_json()["attachments"]}
    assert keys["v1"] in trash_view


def test_construction_card_previews_and_count_hide_replaced_drawing(app):
    """시공팀 도면 전용 카드: 미리보기·+N 모두 옛 도면을 세지 않는다."""
    oid, keys = _seed_confirmed_after_retransfer()
    sd = db_session.get(Order, oid).structured_data
    rows = [{"id": oid, "structured_data": sd}]

    preview_map = build_construction_preview_attachments_map(db_session, rows, drawing_only=True)
    assert {a.storage_key for a in preview_map[oid]} == {keys["v2"], keys["sketch"]}

    enrich_construction_mobile_rows(rows, db_session, mobile_v2_active=True, drawing_only=True)
    labels = {item["label"] for item in rows[0]["attachment_preview_items"]}
    assert labels == _names(keys, "v2", "sketch")
    assert rows[0]["attachments_count"] == 2


def test_mobile_queue_batch_context_hides_replaced_drawing(app):
    """출고·시공 도면 전용 모바일 카드와 상세 첨부 그리드 — 옛 도면이 빠지고 개수도 맞다."""
    oid, keys = _seed_confirmed_after_retransfer()
    order = db_session.get(Order, oid)

    ctx = mobile.build_mobile_queue_batch_context(db_session, [order], drawing_preview_only=True)

    assert ctx.attachment_counts[oid] == 2
    assert {i["label"] for i in ctx.preview_items_by_order[oid]} == _names(keys, "v2", "sketch")
    assert {a["label"] for a in ctx.attachments_by_order[oid]} == _names(
        keys, "v2", "sketch", "measure")


def test_mobile_single_order_paths_load_structured_data_when_not_given(app):
    """structured_data 를 안 넘기는 호출자(생산 목록·주문 대시보드 미리보기, 모바일 상세)도 뺀다."""
    oid, keys = _seed_confirmed_after_retransfer()
    db_session.expire_all()  # 세션에 주문이 없거나 낡았을 때 — in_ 1회로 읽는 길

    previews = mobile.batch_resolve_queue_attachment_preview_items(db_session, [oid])
    assert {i["label"] for i in previews[oid]} == _names(keys, "v2", "sketch", "measure")
    grid = mobile.mobile_attachment_items(db_session, oid, limit=50)
    assert {a["label"] for a in grid} == _names(keys, "v2", "sketch", "measure")


def test_preview_reuses_orders_already_in_session(app):
    """대시보드가 이미 읽은 주문은 다시 읽지 않는다 — 미리보기 조회는 첨부 1회뿐(N+1·JSONB 재조회 없음)."""
    oid, _keys = _seed_confirmed_after_retransfer()
    db_session.expire_all()
    order = db_session.get(Order, oid)
    assert isinstance(order.structured_data, dict)  # 대시보드가 이미 읽은 상태

    statements: list[str] = []

    def _count(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        previews = mobile.batch_resolve_queue_attachment_preview_items(db_session, [oid])
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert len(previews[oid]) == 3
    assert len(statements) == 1, statements


class _PushStorage:
    def get_download_url(self, storage_key, expires_in=3600):
        return f"https://r2.example/{storage_key}?e={expires_in}"


def test_order_push_to_ordering_room_skips_replaced_drawing(client, monkeypatch):
    """발주 PUSH(도면 첨부 전량 → 발주방)는 옛 도면을 싣지 않는다."""
    oid, keys = _seed_confirmed_after_retransfer()
    _login_admin(client, "superseded_push_admin")
    monkeypatch.setenv("CHANNEL_GROUP_DRAWING", "group-draw")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _PushStorage())
    captured: dict = {}

    def _fake_dispatch(event_type, data, raise_on_error=False):
        captured["data"] = data
        return {"success": True, "message_id": "msg-superseded-1"}

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _fake_dispatch)

    res = client.post("/api/channel/push-manual",
                      json={"order_id": oid, "text": "발주 텍스트", "push_kind": "drawing"})

    assert res.status_code == 200, res.get_json()
    sent = {f["url"].split("?")[0].removeprefix("https://r2.example/")
            for f in captured["data"]["files"]}
    assert sent == {keys["v2"], keys["sketch"]}

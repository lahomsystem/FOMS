"""R3 — 첨부 개수 4곳이 교체된 옛 도면을 빼고 센다(개수 == 목록, 2c-2).

1차(2026-09-29)부터 수령 확정이 옛 도면 행을 지우지 않는다. 목록 API·미리보기·모바일 배치 개수는
옛 도면(:func:`superseded_drawing_keys`)을 빼는데, 개수 쿼리 4곳(주문 대시보드 ORM, 생산·시공
raw SQL, 모바일 단건 ``_attachment_count``)은 전체 행을 세서 📎N·+N 이 눌러 연 목록보다 컸다.

이 파일은 SQLite 레인에서 돌 수 있는 두 곳(주문 대시보드·모바일 단건)과 공용 도우미를 본다.
생산·시공 raw SQL 은 ``ANY(:ids)`` 가 PostgreSQL 전용이라 PG 레인
(``tests/postgres/test_superseded_drawing_counts_pg.py``)이 본다.
"""

from __future__ import annotations

from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services import erp_mobile_order_display as mobile
from foms.services.drawing_confirm_cleanup import (
    discount_superseded_drawing_rows,
    superseded_drawing_row_counts,
)
from foms.services.orders.dashboard_read_model import compute_orders_attachment_assignee_maps
from models import Order, OrderAttachment, User


def _seed(*, old_versions: int = 1) -> tuple[int, dict[str, str]]:
    """v1..vN 을 차례로 교체하고 확정한 주문 — 옛 도면 N개 + 현재본 1 + 첨부 탭 도면 1 + 실측 1."""
    order = Order(received_date="2026-09-29", customer_name="개수", phone="010-0000-0000",
                  address="Seoul", product="붙박이장", status="PRODUCTION", is_erp_order=True,
                  structured_data={})
    db_session.add(order)
    db_session.flush()
    oid = order.id
    olds = [f"orders/{oid}/drawing_wizard/exports/v{i}.png" for i in range(1, old_versions + 1)]
    keys = {
        "current": f"orders/{oid}/drawing_wizard/exports/final.png",
        "sketch": f"orders/{oid}/attachments/site_sketch.png",
        "measure": f"orders/{oid}/attachments/measure.jpg",
    }
    rows = [(k, "drawing") for k in olds] + [
        (keys["current"], "drawing"), (keys["sketch"], "drawing"), (keys["measure"], "measurement"),
    ]
    for key, category in rows:
        db_session.add(OrderAttachment(order_id=oid, filename=key.rsplit("/", 1)[-1],
                                       file_type="image", category=category, storage_key=key))
    history = []
    previous: list[dict] = []
    for key in olds + [keys["current"]]:
        entry = {"key": key, "filename": key.rsplit("/", 1)[-1]}
        history.append({"action": "TRANSFER", "mode": "REPLACE", "files": [entry],
                        "previous_current_files": previous})
        previous = [entry]
    history.append({"action": "CONFIRM_RECEIPT", "files": previous})
    order.structured_data = {
        "workflow": {"stage": "PRODUCTION"},
        "drawing_status": "CONFIRMED",
        "drawing_current_files": previous,
        "drawing_transfer_history": history,
    }
    db_session.commit()
    return oid, keys


def _seed_plain() -> int:
    """전달 이력이 없는 주문(옛 도면 없음) — 첨부 2개."""
    order = Order(received_date="2026-09-29", customer_name="평범", phone="010-0000-0000",
                  address="Seoul", product="붙박이장", status="MEASURE", is_erp_order=True,
                  structured_data={"workflow": {"stage": "MEASURE"}})
    db_session.add(order)
    db_session.flush()
    for name in ("a.jpg", "b.jpg"):
        db_session.add(OrderAttachment(order_id=order.id, filename=name, file_type="image",
                                       category="measurement",
                                       storage_key=f"orders/{order.id}/measurement/{name}"))
    db_session.commit()
    return order.id


def _login_admin(client) -> None:
    user = User(username="r3_count_admin", password=generate_password_hash("pass"), role="ADMIN",
                team="SALES", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _list_count(client, oid: int) -> int:
    body = client.get(f"/api/orders/{oid}/attachments").get_json()
    assert body["success"] is True
    return len(body["attachments"])


class _Statements:
    """engine 에 나간 SQL 문장 수를 센다."""

    def __init__(self) -> None:
        self.items: list[str] = []

    def __enter__(self):
        event.listen(engine, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *exc):
        event.remove(engine, "before_cursor_execute", self._on)

    def _on(self, conn, cursor, statement, params, context, executemany):
        self.items.append(statement)


def test_row_counts_count_only_superseded_drawing_rows(app):
    """옛 도면 k개 → k. 현재본·첨부 탭 도면·다른 분류는 세지 않는다."""
    oid, _keys = _seed(old_versions=2)
    sd = db_session.get(Order, oid).structured_data

    assert superseded_drawing_row_counts(db_session, {oid: sd}) == {oid: 2}


def test_row_counts_skip_query_when_no_superseded_keys(app):
    """옛 key 가 없는 주문만 있으면 쿼리 0회(개수 페이지 비용 무증가)."""
    oid = _seed_plain()
    sd = db_session.get(Order, oid).structured_data

    with _Statements() as seen:
        assert superseded_drawing_row_counts(db_session, {oid: sd}) == {}
        counts = {oid: 2}
        assert discount_superseded_drawing_rows(db_session, counts, {oid: sd}) == {oid: 2}
    assert seen.items == []


def test_orders_dashboard_count_matches_list_api(client):
    """주문 대시보드 📎N == 목록 API 개수(옛 도면 2개가 있어도)."""
    oid, _keys = _seed(old_versions=2)
    plain = _seed_plain()
    _login_admin(client)
    orders = [db_session.get(Order, oid), db_session.get(Order, plain)]
    sds = {o.id: o.structured_data for o in orders}

    blob = compute_orders_attachment_assignee_maps(db_session, orders, sds)

    assert blob["att_counts"][str(oid)] == _list_count(client, oid) == 3
    assert blob["att_counts"][str(plain)] == _list_count(client, plain) == 2


def test_orders_dashboard_count_adds_no_query_without_superseded(app):
    """옛 도면이 없는 페이지는 개수 조회가 예전처럼 1회뿐이다."""
    orders = [db_session.get(Order, _seed_plain()), db_session.get(Order, _seed_plain())]
    sds = {o.id: o.structured_data for o in orders}

    with _Statements() as seen:
        compute_orders_attachment_assignee_maps(db_session, orders, sds)
    attachment_queries = [s for s in seen.items if "order_attachments" in s]
    assert len(attachment_queries) == 1, attachment_queries


def test_mobile_single_row_count_matches_batch_and_list(client):
    """모바일 단건(배치 없음) == 배치 == 목록 — docstring '100% 동일' 계약."""
    oid, _keys = _seed(old_versions=1)
    _login_admin(client)
    order = db_session.get(Order, oid)

    single = mobile.build_mobile_queue_order_row(db_session, order, None, batch_ctx=None)
    ctx = mobile.build_mobile_queue_batch_context(db_session, [order])
    batch = mobile.build_mobile_queue_order_row(db_session, order, None, batch_ctx=ctx)

    assert single["attachments_count"] == batch["attachments_count"] == _list_count(client, oid) == 3

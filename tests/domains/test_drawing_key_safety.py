"""공통 판정 "지워도 되는 키" 단위 테스트(2b, SPEC §4.3.5).

규칙: 자기 주문 폴더이고, 지금 어떤 도면 기록·살아 있는 첨부 행도 쓰지 않는 key 만 지운다.
"""
from __future__ import annotations

from datetime import date

from db import db_session
from foms.services.orders.drawing_key_safety import (
    RETAIN_ATTACHMENT_IN_USE,
    RETAIN_DRAWING_HISTORY,
    RETAIN_FOREIGN_PATH,
    RETAIN_OUTSIDE_DRAWING_SCOPE,
    drawing_keys_in_use,
    history_referenced_keys,
    is_own_order_key,
    split_deletable_keys,
)
from models import Order, OrderAttachment


def _order():
    o = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="K", phone="010",
              address="서울", product="장", status="DRAWING", is_erp_order=True, structured_data={})
    db_session.add(o)
    db_session.commit()
    return o.id


def _sd(oid):
    k = lambda rel: f"orders/{oid}/{rel}"  # noqa: E731
    return {
        "drawing_current_files": [{"key": k("drawing/current.png")}],
        "last_drawing_transfer": {"files": [{"key": k("drawing/current.png")}]},
        "drawing_transfer_history": [
            {"action": "TRANSFER", "files": [{"key": k("drawing/old.png")}],
             "previous_current_files": [{"key": k("drawing/older.png")}]},
            {"action": "CONFIRM_RECEIPT", "files": [{"key": k("drawing/confirmed.png")}]},
            {"action": "REQUEST_REVISION", "files": [{"key": k("drawing_gateway/revisions/ref.jpg")}]},
            {"action": "REVISION_CANCELLED",
             "request": {"files": [{"key": k("drawing_gateway/revisions/cancelled.jpg")}]}},
            {"action": "SOMETHING_NEW", "files": [{"key": k("drawing/unknown.png")}]},
        ],
        "drawing_wizard": {"pending": {"s1": {"key": k("drawing_wizard/exports/pending.png")}},
                           "versions": [{"v": 1, "key": k("drawing_wizard/versions/v1_s1.json")}]},
        "blueprint": {"current": {"object_key": k("blueprint/bp.png")}},
    }


def test_keys_in_use_cover_every_drawing_record(app):
    oid = 7
    sd = _sd(oid)
    hist = history_referenced_keys(sd)
    used = drawing_keys_in_use(sd)
    for rel in ("drawing/current.png", "drawing/old.png", "drawing/older.png", "drawing/confirmed.png",
                "drawing_gateway/revisions/ref.jpg", "drawing_gateway/revisions/cancelled.jpg"):
        assert f"orders/{oid}/{rel}" in hist and f"orders/{oid}/{rel}" in used
    for rel in ("drawing_wizard/exports/pending.png", "drawing_wizard/versions/v1_s1.json",
                "blueprint/bp.png"):
        assert f"orders/{oid}/{rel}" not in hist  # 행 판정은 마법사를 보지 않는다
        assert f"orders/{oid}/{rel}" in used
    assert f"orders/{oid}/drawing/unknown.png" not in used  # 모르는 action 은 건너뛴다
    assert drawing_keys_in_use(None) == frozenset()


def test_is_own_order_key_shapes():
    assert is_own_order_key(7, "orders/7/drawing/x.png")
    assert is_own_order_key(7, "orders/7/drawing_wizard/exports/x.png")  # 서버 폴더 포함
    assert is_own_order_key(7, "orders/7/attachments/thumb_x.png")
    for bad in ("orders/8/drawing/x.png", " orders/7/drawing/x.png", "/orders/7/drawing/x.png",
                "orders\\7\\drawing\\x.png", "orders/7/drawing/../measurement/x.png",
                "orders/7//drawing/x.png", "orders/7/unknown/x.png", "orders/7/drawing",
                "uploads/x.png", None, ""):
        assert not is_own_order_key(7, bad), bad


def test_split_deletable_keys_rules(app):
    oid = _order()
    other = _order()
    sd = _sd(oid)
    shared = f"orders/{oid}/attachments/shared.jpg"
    db_session.add(OrderAttachment(order_id=oid, filename="s.jpg", file_type="image",
                                   category="measurement", storage_key=shared))
    db_session.commit()
    free_drawing = f"orders/{oid}/drawing/free.png"
    free_wizard = f"orders/{oid}/drawing_wizard/exports/free.png"
    measurement = f"orders/{oid}/measurement/site.jpg"
    candidates = {
        f"orders/{other}/drawing/b1.png",          # 남의 주문
        f"orders/{oid}/drawing/current.png",       # 현재본
        f"orders/{oid}/drawing/old.png",           # 이력
        shared,                                    # 다른 살아 있는 첨부 행
        free_drawing, free_wizard, measurement,
    }
    reasons: dict[str, str] = {}
    deletable, retained = split_deletable_keys(db_session, oid, sd, candidates, reasons_out=reasons)
    assert deletable == {free_drawing, free_wizard, measurement}
    assert reasons[f"orders/{other}/drawing/b1.png"] == RETAIN_FOREIGN_PATH
    assert reasons[f"orders/{oid}/drawing/current.png"] == RETAIN_DRAWING_HISTORY
    assert reasons[f"orders/{oid}/drawing/old.png"] == RETAIN_DRAWING_HISTORY
    assert reasons[shared] == RETAIN_ATTACHMENT_IN_USE
    assert retained == set(reasons)

    # scope='drawing' 에서는 자기 measurement/ key 도 보존.
    deletable, _ = split_deletable_keys(db_session, oid, sd, {measurement, free_drawing},
                                        scope="drawing", reasons_out=reasons)
    assert deletable == {free_drawing}
    assert reasons[measurement] == RETAIN_OUTSIDE_DRAWING_SCOPE


def test_excluded_and_tombstoned_rows_do_not_protect(app):
    oid = _order()
    key = f"orders/{oid}/drawing/gone.png"
    att = OrderAttachment(order_id=oid, filename="g.png", file_type="image", category="drawing",
                          storage_key=key, thumbnail_key=f"orders/{oid}/drawing/thumb_gone.png")
    db_session.add(att)
    db_session.commit()
    thumb = att.thumbnail_key
    deletable, _ = split_deletable_keys(db_session, oid, {}, {key, thumb})
    assert deletable == set(), "살아 있는 행이 쓰는 key 를 지워도 된다고 했다"
    deletable, _ = split_deletable_keys(db_session, oid, {}, {key, thumb},
                                        exclude_attachment_ids=[att.id])
    assert deletable == {key, thumb}

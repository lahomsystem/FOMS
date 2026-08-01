"""FILE-LEGACY-AUDIT-00 — legacy attachment/key read-only 감사 계약.

exact(row→order→purpose→key) 정확 분류 + ambiguous(order 불명·orphan·비정규 key·purpose
불명) 격리 분리 + **mutation 0**(감사 후 OrderAttachment row/count/object key 불변)을 고정한다.
분류 계약은 DB 없이 fake 로, read-only/mutation-0 증명은 실 session 으로 검증한다(2단).
"""
from __future__ import annotations

import csv
import io
from types import SimpleNamespace
from typing import Any

import pytest

from db import db_session
from models import Order, OrderAttachment
from foms.services.files.legacy_attachment_audit import (
    NONCANONICAL_KEY,
    ORDER_MISSING,
    ORPHAN,
    PURPOSE_MISMATCH,
    PURPOSE_UNRESOLVABLE,
    audit_legacy_attachments,
    classify_attachments,
    to_exact_csv,
    to_quarantine_csv,
)


def _att(**kwargs: Any) -> SimpleNamespace:
    """OrderAttachment-like fake. 분류가 읽는 속성만 채운다."""
    base = {
        "id": kwargs.pop("id", 1),
        "order_id": 1,
        "category": "measurement",
        "storage_key": "orders/1/attachments/photo.jpg",
        "thumbnail_key": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _csv_rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


# ── 1. 순수 분류 계약(fake, DB 무관) ─────────────────────────────────────────
def test_exact_when_order_key_purpose_all_confirmed() -> None:
    """order 실재 + canonical key + purpose 일치 → exact."""
    att = _att(id=1, order_id=5, category="drawing", storage_key="orders/5/drawing/plan.png")
    audit = classify_attachments([att], known_order_ids={5})
    assert len(audit.exact) == 1
    assert not audit.ambiguous
    row = audit.exact[0]
    assert (row.attachment_id, row.order_id, row.purpose) == (1, 5, "drawing")
    assert row.object_key == "orders/5/drawing/plan.png"


def test_order_missing_and_orphan_quarantined() -> None:
    """order_id None(order 불명) / 실재 안 하는 order(orphan) → ambiguous."""
    missing = _att(id=1, order_id=None, storage_key="orders/1/attachments/a.jpg")
    orphan = _att(id=2, order_id=999, storage_key="orders/999/attachments/b.jpg")
    audit = classify_attachments([missing, orphan], known_order_ids={5})
    assert not audit.exact
    reasons = {a.attachment_id: a.reasons for a in audit.ambiguous}
    assert ORDER_MISSING in reasons[1]
    assert ORPHAN in reasons[2]


def test_noncanonical_key_quarantined() -> None:
    """legacy 비정규 key(static/uploads 잔재·order 불일치) → ambiguous."""
    legacy = _att(id=1, order_id=5, storage_key="static/uploads/legacy/old.jpg")
    mismatch = _att(id=2, order_id=5, storage_key="orders/7/attachments/x.jpg")  # order segment 불일치
    audit = classify_attachments([legacy, mismatch], known_order_ids={5, 7})
    assert not audit.exact
    for a in audit.ambiguous:
        assert NONCANONICAL_KEY in a.reasons


def test_purpose_unresolvable_and_mismatch_quarantined() -> None:
    """category 무효(purpose 불명) / key 파생 category 와 불일치 → ambiguous."""
    bogus = _att(id=1, order_id=5, category="bogus", storage_key="orders/5/attachments/a.jpg")
    mismatch = _att(id=2, order_id=5, category="measurement", storage_key="orders/5/drawing/p.png")
    audit = classify_attachments([bogus, mismatch], known_order_ids={5})
    assert not audit.exact
    reasons = {a.attachment_id: a.reasons for a in audit.ambiguous}
    assert PURPOSE_UNRESOLVABLE in reasons[1]
    assert PURPOSE_MISMATCH in reasons[2]


def test_csv_separation_exact_vs_quarantine() -> None:
    """exact CSV 는 exact 만, quarantine CSV 는 ambiguous 만 — 분리 증명."""
    good = _att(id=1, order_id=5, category="measurement", storage_key="orders/5/attachments/a.jpg")
    bad = _att(id=2, order_id=None, storage_key="static/uploads/old.jpg")
    audit = classify_attachments([good, bad], known_order_ids={5})

    exact_rows = _csv_rows(to_exact_csv(audit))
    assert [r["attachment_id"] for r in exact_rows] == ["1"]
    assert exact_rows[0]["object_key"] == "orders/5/attachments/a.jpg"

    q_rows = _csv_rows(to_quarantine_csv(audit))
    assert [r["attachment_id"] for r in q_rows] == ["2"]
    assert ORDER_MISSING in q_rows[0]["reasons"]
    assert NONCANONICAL_KEY in q_rows[0]["reasons"]


# ── 2. 실 session: read-only 감사 + mutation 0 ───────────────────────────────
def _seed_order(**kwargs: Any) -> Order:
    order = Order(
        received_date="2026-07-24",
        customer_name="테스트",
        phone="010-0000-0000",
        address="서울",
        product="가구",
        **kwargs,
    )
    db_session.add(order)
    db_session.flush()
    return order


def _seed_att(order_id: int, category: str, storage_key: str, thumbnail_key=None) -> OrderAttachment:
    att = OrderAttachment(
        order_id=order_id,
        filename=storage_key.rsplit("/", 1)[-1],
        file_type="image",
        category=category,
        file_size=1,
        storage_key=storage_key,
        thumbnail_key=thumbnail_key,
    )
    db_session.add(att)
    db_session.flush()
    return att


def _snapshot() -> list[tuple]:
    return sorted(
        (a.id, a.order_id, a.category, a.storage_key, a.thumbnail_key)
        for a in db_session.query(OrderAttachment).all()
    )


def test_audit_session_classifies_and_mutates_nothing(app) -> None:
    """실 DB 에서 exact/ambiguous 분류 + 감사 후 row/count/key 전부 불변(read-only 증명)."""
    order = _seed_order()
    exact = _seed_att(order.id, "measurement", f"orders/{order.id}/attachments/photo.jpg", "orders/%d/attachments/thumb.jpg" % order.id)
    noncanon = _seed_att(order.id, "measurement", "static/uploads/legacy/old.jpg")
    mismatch = _seed_att(order.id, "measurement", f"orders/{order.id}/drawing/plan.png")
    db_session.commit()

    before = _snapshot()
    before_count = db_session.query(OrderAttachment).count()

    audit = audit_legacy_attachments(db_session)

    # 분류 정확성.
    exact_ids = {r.attachment_id for r in audit.exact}
    ambiguous_ids = {r.attachment_id for r in audit.ambiguous}
    assert exact.id in exact_ids
    assert noncanon.id in ambiguous_ids
    assert mismatch.id in ambiguous_ids
    reasons = {a.attachment_id: a.reasons for a in audit.ambiguous}
    assert NONCANONICAL_KEY in reasons[noncanon.id]
    assert PURPOSE_MISMATCH in reasons[mismatch.id]

    # mutation 0: 세션 identity map 을 비우고 fresh 재조회해도 row/count/key 불변.
    db_session.expunge_all()
    assert db_session.query(OrderAttachment).count() == before_count
    assert _snapshot() == before

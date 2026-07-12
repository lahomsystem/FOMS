"""B5 시공 완료 게이트 API 계약 테스트.

- evidence 등록(before/after/signature) 200 + JSONB 갱신 + OrderEvent.
- 잘못된 첨부(타 주문/타 카테고리) 400.
- 완료 게이트: env off = 기존 동작 불변(200), env on = 미충족 400(missing)·충족 200.
- 권한 403.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderAttachment, OrderEvent, User


def _login(client, *, role: str = "ADMIN", team: str | None = "CONSTRUCTION", suffix: str = "gate") -> User:
    user = User(
        username=f"cgate_{suffix}",
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"Gate {suffix}",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _construction_order() -> int:
    """시공 단계 주문 생성 후 PK(int)를 반환. (요청 후 detach 회피용 id 캡처)"""
    order = Order(
        received_date="2026-07-12",
        customer_name="게이트 고객",
        phone="010-1111-2222",
        address="Seoul",
        product="붙박이장",
        status="CONSTRUCTION",
        manager_name="Bob",
        is_erp_order=True,
        erp_stage_code="CONSTRUCTION",
        structured_data={"workflow": {"stage": "CONSTRUCTION"}},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _attachment(order_id: int, *, category: str = "construction", filename: str = "site.jpg") -> int:
    att = OrderAttachment(
        order_id=order_id,
        filename=filename,
        file_type="image",
        category=category,
        file_size=10,
        storage_key=f"orders/{order_id}/{filename}",
    )
    db_session.add(att)
    db_session.commit()
    return att.id


def _evidence(order_id: int):
    db_session.expire_all()
    order = db_session.query(Order).filter(Order.id == order_id).first()
    return ((order.structured_data or {}).get("construction") or {}).get("evidence") or {}


def test_evidence_register_before_after_signature(client, app):
    _login(client, suffix="ok")
    oid = _construction_order()
    a_before = _attachment(oid, filename="before.jpg")
    a_after1 = _attachment(oid, filename="after1.jpg")
    a_after2 = _attachment(oid, filename="after2.jpg")
    a_sig = _attachment(oid, filename="signature_x.png")

    for kind, att_id in (
        ("before", a_before),
        ("after", a_after1),
        ("after", a_after2),
        ("signature", a_sig),
    ):
        resp = client.post(
            f"/api/orders/{oid}/construction/evidence",
            json={"kind": kind, "attachment_id": att_id},
        )
        assert resp.status_code == 200, (kind, resp.get_data(as_text=True))
        assert resp.get_json()["success"] is True

    ev = _evidence(oid)
    assert ev["before"] == [a_before]
    assert ev["after"] == [a_after1, a_after2]
    assert ev["signature_att_id"] == a_sig
    assert ev.get("signed_by_name")
    assert ev.get("signed_at")

    events = (
        db_session.query(OrderEvent)
        .filter_by(order_id=oid, event_type="CONSTRUCTION_EVIDENCE_ADDED")
        .count()
    )
    assert events == 4


def test_evidence_idempotent_dedup(client, app):
    _login(client, suffix="dedup")
    oid = _construction_order()
    att = _attachment(oid, filename="after.jpg")

    for _ in range(2):
        resp = client.post(
            f"/api/orders/{oid}/construction/evidence",
            json={"kind": "after", "attachment_id": att},
        )
        assert resp.status_code == 200

    assert _evidence(oid)["after"] == [att]


def test_evidence_rejects_wrong_attachment(client, app):
    _login(client, suffix="wrong")
    oid = _construction_order()
    other = _construction_order()
    foreign = _attachment(other, filename="foreign.jpg")
    wrong_cat = _attachment(oid, category="measurement", filename="measure.jpg")

    # 타 주문 소속 첨부
    r1 = client.post(
        f"/api/orders/{oid}/construction/evidence",
        json={"kind": "before", "attachment_id": foreign},
    )
    assert r1.status_code == 400
    assert r1.get_json()["success"] is False

    # category != construction
    r2 = client.post(
        f"/api/orders/{oid}/construction/evidence",
        json={"kind": "before", "attachment_id": wrong_cat},
    )
    assert r2.status_code == 400

    # kind 오류
    r3 = client.post(
        f"/api/orders/{oid}/construction/evidence",
        json={"kind": "bogus", "attachment_id": wrong_cat},
    )
    assert r3.status_code == 400

    # attachment_id 누락
    r4 = client.post(
        f"/api/orders/{oid}/construction/evidence",
        json={"kind": "before"},
    )
    assert r4.status_code == 400


def test_evidence_requires_permission(client, app):
    _login(client, role="STAFF", team=None, suffix="forbidden")
    oid = _construction_order()
    att = _attachment(oid)

    resp = client.post(
        f"/api/orders/{oid}/construction/evidence",
        json={"kind": "before", "attachment_id": att},
    )
    assert resp.status_code == 403


def test_complete_gate_off_keeps_legacy_behavior(client, app, monkeypatch):
    monkeypatch.delenv("FOMS_CONSTRUCTION_GATE_ENABLED", raising=False)
    _login(client, suffix="off")
    oid = _construction_order()

    resp = client.post(
        f"/api/orders/{oid}/construction/complete",
        json={"completion_note": "게이트 off"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["new_status"] == "COMPLETED"


def test_complete_gate_on_blocks_without_evidence(client, app, monkeypatch):
    monkeypatch.setenv("FOMS_CONSTRUCTION_GATE_ENABLED", "true")
    _login(client, suffix="on_block")
    oid = _construction_order()

    resp = client.post(
        f"/api/orders/{oid}/construction/complete",
        json={"completion_note": ""},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert data["error"] == "완료 요건 미충족"
    assert set(data["data"]["missing"]) == {"after", "signature"}


def test_complete_gate_on_allows_with_evidence(client, app, monkeypatch):
    monkeypatch.setenv("FOMS_CONSTRUCTION_GATE_ENABLED", "true")
    _login(client, suffix="on_pass")
    oid = _construction_order()
    a_after1 = _attachment(oid, filename="after1.jpg")
    a_after2 = _attachment(oid, filename="after2.jpg")
    a_sig = _attachment(oid, filename="signature_x.png")

    for kind, att_id in (("after", a_after1), ("after", a_after2), ("signature", a_sig)):
        assert (
            client.post(
                f"/api/orders/{oid}/construction/evidence",
                json={"kind": kind, "attachment_id": att_id},
            ).status_code
            == 200
        )

    resp = client.post(
        f"/api/orders/{oid}/construction/complete",
        json={"completion_note": "완료"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["new_status"] == "COMPLETED"


def test_complete_gate_on_blocks_with_one_after_only(client, app, monkeypatch):
    monkeypatch.setenv("FOMS_CONSTRUCTION_GATE_ENABLED", "true")
    _login(client, suffix="on_partial")
    oid = _construction_order()
    a_after1 = _attachment(oid, filename="after1.jpg")
    a_sig = _attachment(oid, filename="signature_x.png")

    for kind, att_id in (("after", a_after1), ("signature", a_sig)):
        client.post(
            f"/api/orders/{oid}/construction/evidence",
            json={"kind": kind, "attachment_id": att_id},
        )

    resp = client.post(
        f"/api/orders/{oid}/construction/complete",
        json={"completion_note": ""},
    )
    assert resp.status_code == 400
    assert resp.get_json()["data"]["missing"] == ["after"]

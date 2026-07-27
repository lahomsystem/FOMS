"""BLUEPRINT-01 domain tests (SQLite lane) — route policy/ticket/projection + safe backfill.

PG lane(``tests/postgres/test_blueprint.py``)이 실 PostgreSQL 락/동시성을 고정하고, 이
파일은 DSN 없이도 돌아가는 SQLite 대체 증거다: exact order policy(VIEWER 403)·ORDER_BLUEPRINT
ticket(exact key·substr/tamper 거부)·current projection version/event(scalar 병행)·typed
replace/delete outbox(동기 R2 삭제 0)·legacy scalar safe backfill 100%(ambiguous auto-map 0).
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.blueprint_projection import (
    apply_blueprint_backfill,
    classify_blueprint_scalar,
    clear_current_blueprint,
    derive_object_key,
    get_current_blueprint,
    remove_backfill_projection,
    set_current_blueprint,
    verify_blueprint_coverage,
)
from models import (
    DomainSideEffectOutbox,
    Order,
    OrderAttachment,
    OrderEvent,
    User,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _user(role="STAFF", team="CS", username="bp-user"):
    u = User(username=username, password=generate_password_hash("x"), role=role,
             team=team, name=username, is_active=True)
    db_session.add(u)
    db_session.commit()
    return u


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _order(scalar=None):
    o = Order(received_date="2026-07-27", customer_name="홍길동", phone="010-0000-0000",
              address="서울", product="침대", blueprint_image_url=scalar)
    db_session.add(o)
    db_session.commit()
    return o


def _issue(client, order_id, filename="plan.png", size=1000):
    return client.post(f"/api/orders/{order_id}/blueprint",
                       json={"filename": filename, "size": size})


def _complete(client, order_id, ticket_id, key):
    return client.post(f"/api/orders/{order_id}/blueprint/complete",
                       json={"ticket_id": ticket_id, "key": key})


# --------------------------------------------------------------------------- #
# exact order policy (login-only 아님)
# --------------------------------------------------------------------------- #
def test_viewer_denied_upload_403(client):
    """VIEWER 는 in-handler evaluate_policy 로 403(단순 login 통과 아님)."""
    _login(client, _user(role="VIEWER", team=None, username="bp-viewer"))
    o = _order()
    resp = _issue(client, o.id)
    assert resp.status_code == 403
    assert resp.get_json()["success"] is False


def test_viewer_denied_delete_403(client):
    """삭제도 VIEWER 403(exact order policy)."""
    _login(client, _user(role="VIEWER", team=None, username="bp-viewer2"))
    o = _order()
    resp = client.delete(f"/api/orders/{o.id}/blueprint")
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# ORDER_BLUEPRINT ticket · exact key · substr/tamper 거부
# --------------------------------------------------------------------------- #
def test_upload_ticket_then_complete_sets_projection(client):
    """issue→complete 로 current projection·scalar 병행·version bump·SET event 를 만든다."""
    _login(client, _user(username="bp-staff1"))
    o = _order()
    oid, v0 = o.id, o.mutation_version

    iss = _issue(client, oid).get_json()["data"]
    key = iss["key"]
    assert key.startswith(f"orders/{oid}/")  # server-derived (client 입력 아님)

    resp = _complete(client, oid, iss["ticket_id"], key)
    assert resp.status_code == 200
    body = resp.get_json()

    db_session.expire_all()
    order = db_session.get(Order, oid)
    current = get_current_blueprint(order)
    assert current is not None
    assert current["object_key"] == key
    assert current["provenance"] == "ticket"
    # scalar 병행(파생 projection) — read 소비처 무회귀.
    assert order.blueprint_image_url == current["view_url"] == body["url"]
    # version bump(complete_ticket REV-00) + event.
    assert order.mutation_version > v0
    events = db_session.query(OrderEvent).filter_by(order_id=oid,
                                                    event_type="BLUEPRINT_SET").all()
    assert len(events) == 1
    # 첨부가 실제로 생성됨.
    assert db_session.query(OrderAttachment).filter_by(order_id=oid).count() == 1


def test_complete_rejects_tampered_key_no_substr(client):
    """substring 이 통과할 법한 변조 key 를 exact-match 로 거부(P0-11 substr 금지)."""
    _login(client, _user(username="bp-staff2"))
    o = _order()
    oid = o.id
    iss = _issue(client, oid).get_json()["data"]
    tampered = iss["key"] + "x"  # ticket key 의 superstring — substring 검사면 통과할 함정

    resp = _complete(client, oid, iss["ticket_id"], tampered)
    assert resp.status_code == 400
    db_session.expire_all()
    order = db_session.get(Order, oid)
    assert get_current_blueprint(order) is None  # 아무 것도 커밋되지 않음


def test_complete_rejects_ticket_of_other_order(client):
    """다른 주문의 ticket 으로 complete 시 exact order 검사로 거부."""
    _login(client, _user(username="bp-staff3"))
    o1, o2 = _order(), _order()
    o1id, o2id = o1.id, o2.id
    iss = _issue(client, o1id).get_json()["data"]

    resp = _complete(client, o2id, iss["ticket_id"], iss["key"])
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# typed replace / delete outbox (동기 R2 삭제 0)
# --------------------------------------------------------------------------- #
def test_replace_enqueues_storage_delete_for_previous(client):
    """두 번째 업로드는 이전 object 를 STORAGE_DELETE outbox 로 예약하고 REPLACED event 를 남긴다."""
    _login(client, _user(username="bp-staff4"))
    o = _order()
    oid = o.id
    iss1 = _issue(client, oid, filename="a.png").get_json()["data"]
    _complete(client, oid, iss1["ticket_id"], iss1["key"])

    iss2 = _issue(client, oid, filename="b.png").get_json()["data"]
    _complete(client, oid, iss2["ticket_id"], iss2["key"])

    outbox = db_session.query(DomainSideEffectOutbox).filter_by(
        effect_type="STORAGE_DELETE").all()
    assert any(r.payload.get("object_key") == iss1["key"] for r in outbox)
    assert db_session.query(OrderEvent).filter_by(
        order_id=oid, event_type="BLUEPRINT_REPLACED").count() == 1
    # 이전 첨부 row 제거, 현재 첨부만 남음.
    keys = {a.storage_key for a in db_session.query(OrderAttachment).filter_by(order_id=oid)}
    assert keys == {iss2["key"]}
    db_session.expire_all()
    assert get_current_blueprint(db_session.get(Order, oid))["object_key"] == iss2["key"]


def test_delete_enqueues_outbox_and_clears_projection(client, monkeypatch):
    """삭제는 STORAGE_DELETE outbox 로 예약하고 projection·scalar 를 비운다(동기 R2 삭제 0)."""
    import foms.services.storage as storage_mod

    _login(client, _user(username="bp-staff5"))
    o = _order()
    oid = o.id
    iss = _issue(client, oid).get_json()["data"]
    _complete(client, oid, iss["ticket_id"], iss["key"])

    # 동기 R2 삭제가 일어나면 실패하도록 감시.
    def _boom(*a, **k):
        raise AssertionError("동기 R2 삭제 금지 — STORAGE_DELETE outbox 여야 한다.")

    monkeypatch.setattr(storage_mod.StorageAdapter, "delete_file", _boom, raising=True)

    resp = client.delete(f"/api/orders/{oid}/blueprint")
    assert resp.status_code == 200

    db_session.expire_all()
    order = db_session.get(Order, oid)
    assert get_current_blueprint(order) is None
    assert order.blueprint_image_url is None
    assert db_session.query(OrderEvent).filter_by(
        order_id=oid, event_type="BLUEPRINT_DELETED").count() == 1
    rows = db_session.query(DomainSideEffectOutbox).filter_by(effect_type="STORAGE_DELETE").all()
    assert any(r.payload.get("object_key") == iss["key"] for r in rows)


# --------------------------------------------------------------------------- #
# legacy scalar safe backfill (100% · ambiguous auto-map 0)
# --------------------------------------------------------------------------- #
def test_derive_object_key_exact_vs_ambiguous(client):
    """canonical /api/files/view/<key> 만 유도, 외부/비정규는 None(auto-map 금지)."""
    exact = derive_object_key("/api/files/view/orders/7/blueprint/img.png", 7)
    assert exact == "orders/7/blueprint/img.png"
    assert derive_object_key("https://example.com/plan.png", 7) is None
    assert derive_object_key("/static/uploads/old/x.png", 7) is None
    # order mismatch → 유도 거부.
    assert derive_object_key("/api/files/view/orders/8/blueprint/img.png", 7) is None


def test_backfill_exact_ambiguous_coverage_idempotent(client):
    """scalar → projection: exact 유도·ambiguous 보존(무손실)·coverage 100%·멱등."""
    oe = _order(scalar=None)
    oe.blueprint_image_url = f"/api/files/view/orders/{oe.id}/blueprint/plan.png"
    oa = _order(scalar="https://cdn.example.com/legacy-plan.png")  # 외부(ambiguous)
    db_session.commit()

    dry = apply_blueprint_backfill(db_session, apply=False)
    assert dry.total == 2 and dry.exact == 1 and dry.ambiguous == 1 and dry.projected == 2
    assert dry.applied is False
    assert get_current_blueprint(db_session.query(Order).get(oe.id)) is None  # 무쓰기

    res = apply_blueprint_backfill(db_session, apply=True)
    db_session.commit()
    assert res.projected == 2 and res.applied is True

    ce = get_current_blueprint(db_session.query(Order).get(oe.id))
    assert ce["object_key"] == f"orders/{oe.id}/blueprint/plan.png"
    assert ce["provenance"] == "migration_backfill"
    ca = get_current_blueprint(db_session.query(Order).get(oa.id))
    assert ca["object_key"] is None and ca["ambiguous"] is True  # auto-map 금지
    assert ca["view_url"] == "https://cdn.example.com/legacy-plan.png"  # 원문 무손실

    cov = verify_blueprint_coverage(db_session)
    assert cov.total == 2 and cov.missing == 0 and cov.coverage_complete is True

    # 멱등: 재실행은 이미 있는 것을 건드리지 않는다.
    again = apply_blueprint_backfill(db_session, apply=True)
    assert again.already_present == 2 and again.projected == 0


def test_backfill_does_not_touch_scalar_and_downgrade_removes_only_backfill(client):
    """backfill 은 scalar 를 수정하지 않고, downgrade 는 backfill provenance 만 제거한다."""
    o = _order(scalar="https://cdn.example.com/p.png")
    apply_blueprint_backfill(db_session, apply=True)
    db_session.commit()
    db_session.expire_all()
    order = db_session.query(Order).get(o.id)
    assert order.blueprint_image_url == "https://cdn.example.com/p.png"  # scalar 불변

    removed = remove_backfill_projection(db_session)
    db_session.commit()
    assert removed == 1
    assert get_current_blueprint(db_session.query(Order).get(o.id)) is None


def test_backfill_preserves_other_blueprint_subkeys(client):
    """이미지 projection 은 blueprint dict 의 고객컨펌 등 다른 sub-key 를 보존한다."""
    o = _order(scalar=f"/api/files/view/orders/1/blueprint/x.png")
    o.structured_data = {"blueprint": {"customer_confirmed": True, "confirmed_by": "김담당"}}
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(o, "structured_data")
    db_session.commit()

    apply_blueprint_backfill(db_session, apply=True)
    db_session.commit()
    db_session.expire_all()
    bp = db_session.query(Order).get(o.id).structured_data["blueprint"]
    assert bp["customer_confirmed"] is True and bp["confirmed_by"] == "김담당"
    assert "current" in bp


def test_classify_preserves_raw_url_lossless(client):
    """분류는 exact/ambiguous 모두 원문 URL 을 view_url 에 무손실 보존한다."""
    kind, cur = classify_blueprint_scalar(3, "https://x/y.png", "2026-07-27T00:00:00")
    assert kind == "ambiguous" and cur["view_url"] == "https://x/y.png" and cur["object_key"] is None
    kind2, cur2 = classify_blueprint_scalar(3, "/api/files/view/orders/3/blueprint/z.png",
                                            "2026-07-27T00:00:00")
    assert kind2 == "exact" and cur2["object_key"] == "orders/3/blueprint/z.png"


# --------------------------------------------------------------------------- #
# service-level set/clear (route 밖 단위)
# --------------------------------------------------------------------------- #
def test_set_and_clear_current_blueprint_service(client):
    """set_current_blueprint / clear_current_blueprint 서비스 단위 계약."""
    o = _order()
    att = OrderAttachment(order_id=o.id, filename="p.png", file_type="image",
                          category="measurement", file_size=10,
                          storage_key=f"orders/{o.id}/measurement/p.png")
    db_session.add(att)
    db_session.flush()

    current = set_current_blueprint(db_session, o, attachment=att, actor_user_id=None)
    db_session.commit()
    assert current["object_key"] == att.storage_key
    assert o.blueprint_image_url == current["view_url"]

    removed = clear_current_blueprint(db_session, o, actor_user_id=None)
    db_session.commit()
    assert removed["object_key"] == att.storage_key
    assert get_current_blueprint(o) is None
    assert o.blueprint_image_url is None

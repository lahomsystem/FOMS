"""DRAFT-LIFECYCLE-01: ERP 주문 draft 생명주기 계약 (create/finalize/discard/hard-delete).

핵심 불변식:
- **create idempotency**: 같은 draft key 재요청 = 기존 draft 제자리 갱신(행 폭증 0, 최신 입력 반영).
- **finalize one tx**: submit 이 ORDER-CREATE-01 ``create_order`` 를 경유해 정본 Order 로 승격
  (version=1·SALES owner 배정·ORDER_CREATED event·quest seed·GEOCODE outbox 를 한 tx),
  성공 시 draft flag(=draft row)를 제거한다. 부분 실패는 전부 롤백하고 draft 를 보존한다.
- **discard child cleanup/outbox**: draft 폐기 시 이 draft 폴더에 속한 첨부에 대해서만
  STORAGE_DELETE outbox 를 enqueue(enqueue 만) 하고, 정본/타 draft 파일은 건드리지 않는다.
- **hard-delete scope**: draft 삭제는 draft row 범위만 — finalized Order 는 삭제/상태변경 불변.

DB 레인: 도메인 테스트는 in-memory SQLite(전 테이블 create_all)라 dev PG DSN 없이도 red→green.
"""

from __future__ import annotations

import json

import pytest
from werkzeug.security import generate_password_hash


@pytest.fixture
def wizard_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "true")


def _login(client, app, username: str = "draft_lifecycle_user") -> int:
    from db import db_session
    from models import User

    with app.app_context():
        user = db_session.query(User).filter_by(username=username).first()
        if user is None:
            user = User(
                username=username,
                password=generate_password_hash("admin"),
                role="ADMIN",
                team="SALES",
                name="Draft Lifecycle User",
            )
            db_session.add(user)
            db_session.commit()
        uid = user.id
    client.post(
        "/login",
        data={"username": username, "password": "admin"},
        follow_redirects=True,
    )
    return uid


def _put(client, key: str, data: dict, step: int = 4):
    payload = {"schema_version": 1, "step": step, "data": data}
    return client.put(
        "/api/erp/order-draft",
        data=json.dumps({"draft_key": key, "step": step, "payload": payload}),
        content_type="application/json",
    )


def _submit(client, key: str):
    return client.post(
        "/api/erp/order-draft/submit",
        data=json.dumps({"draft_key": key}),
        content_type="application/json",
    )


# --------------------------------------------------------------------------- #
# create idempotency
# --------------------------------------------------------------------------- #
def test_create_idempotent_same_key_reuses_row(client, app, wizard_enabled) -> None:
    from db import db_session
    from models import OrderDraft

    uid = _login(client, app, "draft_idem_user")
    key = "new.idem"
    first = _put(client, key, {"customer_name": "첫입력", "phone": "010-1"})
    assert first.status_code == 200
    second = _put(client, key, {"customer_name": "둘째입력", "phone": "010-2", "address": "대전"})
    assert second.status_code == 200

    with app.app_context():
        rows = db_session.query(OrderDraft).filter_by(user_id=uid, draft_key=key).all()
        assert len(rows) == 1  # 중복 0
        assert rows[0].payload["data"]["customer_name"] == "둘째입력"  # 최신 입력 반영


# --------------------------------------------------------------------------- #
# finalize one tx (create_order 경유)
# --------------------------------------------------------------------------- #
def test_finalize_promotes_via_create_order_one_tx(client, app, wizard_enabled) -> None:
    from db import db_session
    from models import (
        DomainSideEffectOutbox,
        Order,
        OrderAssignment,
        OrderDraft,
        OrderEvent,
    )

    uid = _login(client, app, "draft_finalize_user")
    key = "new.finalize"
    _put(
        client,
        key,
        {
            "customer_name": "승격테스트",
            "phone": "010-9999-8888",
            "address": "경기도 성남시",
            "received_date": "2026-05-30",
            "items": [{"product_name": "주방장", "spec_rows": [{}], "price": "1,000,000"}],
            "schedule": {},
        },
    )
    submit = _submit(client, key)
    assert submit.status_code == 200
    order_id = submit.get_json()["data"]["order_id"]

    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        assert order.is_erp_order is True
        assert order.mutation_version == 1  # ORDER-CREATE version=1
        # SALES owner 배정 1건(INITIAL_OWNER) — self-service wizard 이므로 생성자가 owner.
        owners = (
            db_session.query(OrderAssignment)
            .filter_by(order_id=order_id, domain="SALES", active=True)
            .all()
        )
        assert len(owners) == 1
        assert owners[0].source == "INITIAL_OWNER"
        assert owners[0].user_id == uid
        # ORDER_CREATED event 1건.
        assert (
            db_session.query(OrderEvent)
            .filter_by(order_id=order_id, event_type="ORDER_CREATED")
            .count()
            == 1
        )
        # quest seed(RECEIVED).
        quests = (order.structured_data or {}).get("quests")
        assert isinstance(quests, list) and any(q.get("stage") == "RECEIVED" for q in quests)
        # GEOCODE outbox 예약(주소 있음)·PENDING — postcommit 직접 지오코드가 아님.
        geo = (
            db_session.query(DomainSideEffectOutbox)
            .filter_by(effect_type="GEOCODE")
            .all()
        )
        assert len(geo) == 1 and geo[0].status == "PENDING"
        # draft flag 제거: draft row 삭제.
        assert (
            db_session.query(OrderDraft).filter_by(user_id=uid, draft_key=key).count() == 0
        )


def test_finalize_partial_failure_rolls_back_and_keeps_draft(
    client, app, wizard_enabled, monkeypatch
) -> None:
    from db import db_session
    from models import Order, OrderDraft

    uid = _login(client, app, "draft_rollback_user")
    key = "new.rollback"
    _put(
        client,
        key,
        {
            "customer_name": "롤백테스트",
            "phone": "010-1111-2222",
            "address": "서울시 3",
            "items": [{"product_name": "붙박이장", "spec_rows": [{}], "price": "500,000"}],
            "schedule": {},
        },
    )

    with app.app_context():
        before_orders = db_session.query(Order).count()

    import foms.services.orders.order_create as oc

    def _boom(*_a, **_k):
        raise RuntimeError("identity mint failed")

    monkeypatch.setattr(oc, "get_or_create_identity", _boom)

    # 전역 에러 핸들러 유무와 무관하게(500 또는 예외 전파) 불변식만 검증한다.
    try:
        resp = _submit(client, key)
        assert resp.status_code >= 500
    except RuntimeError:
        pass

    with app.app_context():
        db_session.rollback()
        # 부분 생성 없음.
        assert db_session.query(Order).count() == before_orders
        # 승격 실패 → draft flag 미제거(draft 보존).
        assert (
            db_session.query(OrderDraft).filter_by(user_id=uid, draft_key=key).count() == 1
        )


# --------------------------------------------------------------------------- #
# discard child cleanup / outbox
# --------------------------------------------------------------------------- #
def test_discard_enqueues_storage_delete_scoped_to_draft_folder(
    client, app, wizard_enabled
) -> None:
    from db import db_session
    from models import DomainSideEffectOutbox, OrderDraft
    from foms.services.order_draft_attachments import draft_attachment_folder

    uid = _login(client, app, "draft_discard_user")
    key = "new.discard"
    folder = draft_attachment_folder(uid, key)
    draft_tmp_key = f"{folder}/measure.jpg"
    foreign_key = "orders/999/real-photo.jpg"  # 정본 order 파일(이 draft 폴더 밖 → 범위 밖)
    _put(
        client,
        key,
        {
            "customer_name": "폐기테스트",
            "phone": "010-5",
            "address": "인천",
            "items": [
                {
                    "product_name": "주방",
                    "spec_rows": [{}],
                    "attachments": [
                        {"tmp_key": draft_tmp_key, "filename": "measure.jpg"},
                        {"tmp_key": foreign_key, "filename": "real-photo.jpg"},
                    ],
                }
            ],
            "schedule": {},
        },
    )

    deleted = client.delete(f"/api/erp/order-draft?key={key}")
    assert deleted.status_code == 200

    with app.app_context():
        # draft row 제거(hard-delete).
        assert (
            db_session.query(OrderDraft).filter_by(user_id=uid, draft_key=key).count() == 0
        )
        rows = (
            db_session.query(DomainSideEffectOutbox)
            .filter_by(effect_type="STORAGE_DELETE")
            .all()
        )
        object_keys = {r.payload.get("object_key") for r in rows}
        # draft 폴더 첨부만 enqueue, 정본 order 파일은 제외(scope 가드).
        assert draft_tmp_key in object_keys
        assert foreign_key not in object_keys
        assert len(rows) == 1
        assert rows[0].source_domain == "WIZARD_PENDING"
        assert rows[0].status == "PENDING"


# --------------------------------------------------------------------------- #
# hard-delete scope — finalized Order 불변
# --------------------------------------------------------------------------- #
def test_hard_delete_scope_leaves_finalized_order_untouched(
    client, app, wizard_enabled
) -> None:
    from db import db_session
    from models import Order, OrderDraft

    uid = _login(client, app, "draft_scope_user")

    # 정본 Order 를 wizard submit 으로 승격 생성.
    order_key = "new.scope-order"
    _put(
        client,
        order_key,
        {
            "customer_name": "정본주문",
            "phone": "010-7777-6666",
            "address": "부산시",
            "items": [{"product_name": "드레스룸", "spec_rows": [{}], "price": "800,000"}],
            "schedule": {},
        },
    )
    submit = _submit(client, order_key)
    assert submit.status_code == 200
    order_id = submit.get_json()["data"]["order_id"]

    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        status_before = order.status
        version_before = order.mutation_version

    # 별도 draft 생성 후 hard-delete.
    draft_key = "new.scope-draft"
    _put(client, draft_key, {"customer_name": "삭제될draft", "phone": "010-0"})
    deleted = client.delete(f"/api/erp/order-draft?key={draft_key}")
    assert deleted.status_code == 200

    with app.app_context():
        # draft 제거.
        assert (
            db_session.query(OrderDraft)
            .filter_by(user_id=uid, draft_key=draft_key)
            .count()
            == 0
        )
        # finalized Order 불변: 존재·상태·version 유지·미삭제.
        order = db_session.query(Order).filter_by(id=order_id).one()
        assert order.status == status_before
        assert order.mutation_version == version_before
        assert order.status != "DELETED"
        assert order.deleted_at is None

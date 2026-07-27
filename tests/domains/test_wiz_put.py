"""WIZ-01 도면 마법사 PUT 하드닝 계약 테스트 (row lock · projection · pending 소실/주입 차단).

``api_put_drawing_wizard`` 가 REV-00 :func:`execute_order_mutation` 을 경유하도록 바뀐 뒤의
근본 계약을 고정한다(P0-4):

* projection — 클라 페이로드는 허용 필드(v·sheets)만 반영하고 서버 소유 필드
  (pending·versions·updated_*)는 보존한다.
* 부분 페이로드가 서버 pending 을 비우지 않는다(소실 0).
* 위조 서버 필드/미허용 키 주입은 무시된다(주입 0).
* base_updated_at·If-Match stale → 409, version bump·receipt 발급.

기존 ``test_drawing_wizard_api.py`` 의 픽스처 관행을 따른다(db_session 직접 + session_transaction 로그인).
"""

import copy
import uuid
from datetime import date

from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderMutationReceipt, User


def _login_admin(client, username="wiz-admin"):
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role="ADMIN",
        team="DRAWING",
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _erp_order():
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="서으뜸",
        phone="010-1111-2222",
        address="대구",
        product="붙박이장",
        status="DRAWING",
        manager_name="하우드 김성일",
        is_erp_order=True,
        structured_data={"parties": {"customer": {"name": "서으뜸"}}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _state(sheet_name="도면 1"):
    return {
        "v": 1,
        "sheets": [{"id": "s-1", "name": sheet_name, "form": {}, "objects": []}],
    }


def _put(client, order_id, state, base=None, headers=None):
    return client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": state, "base_updated_at": base},
        headers=headers or {},
    )


def _seed_pending_preserving_updated_at(order_id, sheet_id="s-1"):
    """현재 drawing_wizard 에 pending 1건을 직접 심는다(updated_at 불변 — sheet-png 동작 모사)."""
    db_session.expire_all()
    order = db_session.query(Order).filter_by(id=order_id).first()
    sd = copy.deepcopy(order.structured_data)
    dw = sd["drawing_wizard"]
    dw.setdefault("pending", {})[sheet_id] = {
        "key": f"orders/{order_id}/drawing_wizard/exports/1_a.png",
        "filename": "a.png",
        "at": "2026-07-07 10:00",
        "sheet_name": "도면 1",
    }
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _stored_dw(order_id):
    db_session.expire_all()
    order = db_session.query(Order).filter_by(id=order_id).first()
    return (order.structured_data or {}).get("drawing_wizard") or {}


# --------------------------------------------------------------------------- #
# projection · pending 소실 차단 (P0-4 근본)
# --------------------------------------------------------------------------- #
def test_put_preserves_server_pending_across_partial_payload(client):
    """pending 을 안 실은 PUT 이 서버 pending 을 비우지 않는다(소실 0)."""
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    first = _put(client, order_id, _state())
    assert first.status_code == 200, first.get_json()
    base = first.get_json()["data"]["updated_at"]

    _seed_pending_preserving_updated_at(order_id)

    # sheets 만 바뀐 PUT — pending 은 페이로드에 없다.
    second = _put(client, order_id, _state("도면 1 수정"), base=base)
    assert second.status_code == 200, second.get_json()

    dw = _stored_dw(order_id)
    assert "s-1" in dw.get("pending", {}), dw          # pending 보존됨
    assert dw["sheets"][0]["name"] == "도면 1 수정"       # sheets 는 갱신됨

    pending = client.get(
        f"/api/orders/{order_id}/drawing-wizard/pending"
    ).get_json()["data"]["pending"]
    assert [p["sheet_id"] for p in pending] == ["s-1"]


def test_put_ignores_client_injected_server_fields(client):
    """클라가 pending·versions·미허용 키를 주입해도 무시된다(주입 0)."""
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    first = _put(client, order_id, _state())
    base = first.get_json()["data"]["updated_at"]
    _seed_pending_preserving_updated_at(order_id, sheet_id="s-1")

    hostile = _state("도면 1")
    hostile["pending"] = {"s-evil": {"key": "orders/9/x.png", "filename": "e.png"}}
    hostile["versions"] = [{"v": 999, "key": "bogus"}]
    hostile["updated_by"] = 999999
    hostile["injected_key"] = "x"

    resp = _put(client, order_id, hostile, base=base)
    assert resp.status_code == 200, resp.get_json()

    dw = _stored_dw(order_id)
    # 서버 pending 만 남고 위조 s-evil 은 들어오지 않는다.
    assert set(dw.get("pending", {}).keys()) == {"s-1"}
    # 위조 versions·미허용 키는 저장되지 않는다.
    assert dw.get("versions", []) == []
    assert "injected_key" not in dw
    # updated_by 는 서버가 actor 로 덮어쓴다(클라 위조 999999 무시).
    assert dw["updated_by"] != 999999


def test_put_preserves_server_versions_when_absent_in_payload(client, monkeypatch):
    """versions 없는 PUT 이 서버 보존 versions 를 유지한다(클라 삭제 사고 차단)."""
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    first = _put(client, order_id, _state())
    base = first.get_json()["data"]["updated_at"]

    # 서버 소유 versions 를 직접 심는다(version-snapshot 이 넣는 포인터 모사, updated_at 불변).
    db_session.expire_all()
    o = db_session.query(Order).filter_by(id=order_id).first()
    sd = copy.deepcopy(o.structured_data)
    sd["drawing_wizard"]["versions"] = [{"v": 1, "key": "orders/1/versions/v1.json"}]
    o.structured_data = sd
    flag_modified(o, "structured_data")
    db_session.commit()

    second = _put(client, order_id, _state("v2"), base=base)
    assert second.status_code == 200, second.get_json()

    dw = _stored_dw(order_id)
    assert dw.get("versions") == [{"v": 1, "key": "orders/1/versions/v1.json"}]


# --------------------------------------------------------------------------- #
# 낙관적 잠금 (base_updated_at) · REV-00 If-Match stale → 409
# --------------------------------------------------------------------------- #
def test_put_stale_base_updated_at_returns_409_with_server_meta(client):
    """base_updated_at 이 서버 최신과 다르면 409(error=conflict, server_updated_* 동봉)."""
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    assert _put(client, order_id, _state()).status_code == 200

    # 오래된 base(None)로 재저장 → stale.
    conflict = _put(client, order_id, _state("stale"), base=None)
    assert conflict.status_code == 409
    body = conflict.get_json()
    assert body["error"] == "conflict"
    assert body["server_updated_at"]
    assert body["server_updated_by_name"]

    # 충돌 저장은 반영되지 않는다(sheets 이름 불변).
    assert _stored_dw(order_id)["sheets"][0]["name"] == "도면 1"


def test_put_if_match_mismatch_returns_409_revision_conflict(client):
    """If-Match(mutation_version) 불일치면 REV-00 이 409 REVISION_CONFLICT 를 낸다."""
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    first = _put(client, order_id, _state())
    assert first.status_code == 200
    assert first.get_json()["mutation_version"] == 2  # 1 → 2

    base = first.get_json()["data"]["updated_at"]
    # base 는 최신이지만 If-Match 는 stale(1) → REV-00 precondition 에서 먼저 막힌다.
    resp = _put(client, order_id, _state("x"), base=base, headers={"If-Match": "1"})
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "REVISION_CONFLICT"


# --------------------------------------------------------------------------- #
# version bump · receipt 발급 (REV-00 경유 증거)
# --------------------------------------------------------------------------- #
def test_put_bumps_mutation_version_and_issues_receipt(client):
    """PUT 이 mutation_version 을 bump 하고 read receipt(+no-store)를 발급한다."""
    _login_admin(client)
    order = _erp_order()
    order_id = order.id
    assert order.mutation_version == 1

    resp = _put(client, order_id, _state())
    assert resp.status_code == 200, resp.get_json()
    payload = resp.get_json()
    assert payload["mutation_version"] == 2
    receipt_id = payload["mutation_receipt"]
    uuid.UUID(receipt_id)  # opaque 128-bit
    assert "no-store" in resp.headers.get("Cache-Control", "")

    db_session.expire_all()
    o = db_session.query(Order).filter_by(id=order_id).first()
    assert o.mutation_version == 2
    assert (
        db_session.query(OrderMutationReceipt)
        .filter_by(read_receipt_id=receipt_id)
        .count()
        == 1
    )


def test_put_rejects_non_participant_before_mutation(client):
    """비참여자는 403(락·mutation 이전) — receipt 미발급."""
    order = _erp_order()
    order_id = order.id
    # 비-ADMIN·비-DRAWING 사용자.
    viewer = User(
        username="wiz-viewer",
        password=generate_password_hash("x"),
        role="STAFF",
        team="CS",
        name="viewer",
        is_active=True,
    )
    db_session.add(viewer)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = viewer.id
        sess["role"] = viewer.role

    resp = _put(client, order_id, _state())
    assert resp.status_code == 403
    assert db_session.query(OrderMutationReceipt).count() == 0

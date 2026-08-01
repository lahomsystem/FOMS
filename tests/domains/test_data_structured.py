"""DATA-01: structured form projection · server pricing · REV-00 one-tx 계약 테스트 (red→green).

structured PUT 저장을 정본화한 계약을 고정한다.

* **envelope/path/item schema**: 저장 후 structured_data 가 정본 envelope 를 유지한다.
* **provenance 보존(client overwrite 금지)**: raw/schema/confidence(sd 키·Order 컬럼)를
  클라이언트가 덮어쓰지 못한다(old-wins).
* **server pricing/totals**: 클라이언트가 보낸 totals 를 무시하고 items·payment 로 재계산한다.
* **partial allowlist**: 폼이 도입할 수 없는 임의 최상위 키는 strip 한다.
* **clear intent**: 부분 누락(omission)은 clear 가 아니다(운영 subtree 보존). 명시 값만 반영.
* **stale tab(If-Match)**: mutation_version 불일치는 409 로 거부하고 상태를 바꾸지 않는다.

REV-00 :func:`execute_order_mutation` 을 경유하므로 저장은 version bump · receipt 를 한 tx
에 원자화한다. 실 PostgreSQL 다중 커밋 race 는 :mod:`tests.postgres.test_data_structured_pg`
(PG lane) 에서 별도 증명한다.
"""

import copy

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderMutationReceipt, User
from foms.services.orders.structured_form_projection import (
    FORM_INTRODUCED_KEYS,
    PROVENANCE_KEYS,
    project_structured_form,
    recompute_totals,
)


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
def _login_admin(client, username="data01-admin"):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="CS",
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = username
        sess["role"] = "ADMIN"
    return user.id


def _valid_form_payload(**overrides):
    """필수값(고객명/전화/주소/제품명)을 채운 최소 유효 폼 structured_data."""
    sd = {
        "entity_type": "order_structured",
        "workflow": {"stage": "RECEIVED"},
        "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
        "site": {"address_full": "서울 테헤란로 1", "address_main": "서울 테헤란로 1"},
        "items": [{"product_name": "붙박이장", "price": 0}],
    }
    sd.update(overrides)
    return sd


def _create_order(structured_data=None, **cols):
    order = Order(
        received_date="2026-04-07",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="서울 테헤란로 1",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        structured_data=structured_data if structured_data is not None else _valid_form_payload(),
    )
    for key, value in cols.items():
        setattr(order, key, value)
    db_session.add(order)
    db_session.commit()
    return order.id


def _fresh(oid):
    db_session.expire_all()
    return db_session.get(Order, oid)


# --------------------------------------------------------------------------
# 순수 projection 단위(envelope/allowlist/provenance/pricing) — DB 없이
# --------------------------------------------------------------------------
def test_projection_strips_arbitrary_top_level_keys():
    """partial allowlist: FORM_INTRODUCED_KEYS·old_sd 어디에도 없는 임의 키는 strip."""
    old = {"drawing": {"status": "X"}, "legacy_key": {"kept": True}}
    sd = {
        "parties": {"customer": {"name": "A"}},
        "evil_inject": {"is_admin": True},
        "drawing": {"status": "X"},   # old 에 있음 → 유지
        "legacy_key": {"kept": False},  # old 에 있음 → 유지
    }
    stripped = project_structured_form(old, sd)
    assert stripped == ["evil_inject"]
    assert "evil_inject" not in sd
    assert "drawing" in sd and "legacy_key" in sd


def test_projection_locks_provenance_old_wins():
    """provenance(raw/schema/confidence 등)는 old 값이 있으면 클라이언트 값으로 덮지 않는다."""
    old = {"confidence": "high", "raw": {"text": "ORIG"}, "schema_version": 3}
    sd = _valid_form_payload(confidence="forged", raw={"text": "HACK"}, schema_version=1)
    project_structured_form(old, sd)
    assert sd["confidence"] == "high"
    assert sd["raw"] == {"text": "ORIG"}
    assert sd["schema_version"] == 3


def test_projection_provenance_bootstrap_when_old_absent():
    """old 에 provenance 가 없으면 클라이언트 값 수용(신규 주문 bootstrap — 회귀 방지)."""
    sd = _valid_form_payload(confidence="medium")
    project_structured_form({}, sd)
    assert sd["confidence"] == "medium"
    assert sd["entity_type"] == "order_structured"


def test_projection_recomputes_totals_ignoring_client_values():
    """server pricing: 클라이언트 totals 무시, items·payment 로 재계산. 출고가=품목+배송-할인."""
    sd = {
        "items": [{"price": 100000}, {"price": 50000}],
        "payment": {"free_input": "배송:30000", "discount": 20000, "deposit": 40000},
        "totals": {"items_total": 999999, "shipping_price": 999999, "discount_amount": 1},
    }
    totals = recompute_totals(sd)
    assert totals["items_total"] == 150000            # 품목 price 합만(재정의 금지)
    assert totals["free_input_amount"] == 30000
    assert totals["discount_amount"] == 20000
    assert totals["deposit_amount"] == 40000
    assert totals["shipping_price"] == 160000         # 150000 + 30000 - 20000
    assert totals["balance_amount"] == 120000         # 180000 - 40000 - 20000
    assert sd["totals"] == totals


def test_provenance_keys_subset_of_form_introduced():
    """provenance 키는 폼 도입 허용 집합의 부분집합(allowlist 가 provenance 를 strip 하지 않음)."""
    assert PROVENANCE_KEYS <= FORM_INTRODUCED_KEYS


# --------------------------------------------------------------------------
# route 통합: envelope/path/item schema 저장
# --------------------------------------------------------------------------
def test_put_saves_canonical_envelope_and_bumps_version(client):
    """유효 폼 저장 후 정본 envelope(path/item schema)·mutation_version++·receipt 1."""
    _login_admin(client, "data01-envelope")
    oid = _create_order()
    before = _fresh(oid).mutation_version

    payload = _valid_form_payload(
        items=[{"product_name": "붙박이장", "price": 300000, "spec_rows": [{"spec_width": "1300"}]}],
        payment={"deposit": 100000, "discount": 0, "free_input": ""},
    )
    resp = client.put(
        f"/api/orders/{oid}/structured",
        json={"structured_data": payload},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True
    assert body["mutation_version"] == before + 1
    assert body.get("mutation_receipt")

    sd = _fresh(oid).structured_data
    assert sd["parties"]["customer"]["name"] == "홍길동"
    assert sd["parties"]["customer"]["phone"] == "010-1234-5678"
    assert sd["site"]["address_full"] == "서울 테헤란로 1"
    assert sd["items"][0]["product_name"] == "붙박이장"
    assert sd["items"][0]["price"] == 300000
    assert sd["workflow"]["stage"] == "RECEIVED"
    # server pricing 이 totals 를 심는다.
    assert sd["totals"]["items_total"] == 300000
    assert sd["totals"]["shipping_price"] == 300000

    assert _fresh(oid).mutation_version == before + 1
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id="ERP_STRUCTURED_PUT").count() == 1


# --------------------------------------------------------------------------
# server pricing/totals: 클라이언트 값 무시·서버 재계산
# --------------------------------------------------------------------------
def test_put_ignores_client_totals_and_recomputes(client):
    """클라이언트가 거짓 totals 를 보내도 서버가 items·payment 로 재계산해 저장한다."""
    _login_admin(client, "data01-pricing")
    oid = _create_order()

    payload = _valid_form_payload(
        items=[{"product_name": "장", "price": 100000}, {"product_name": "장2", "price": 50000}],
        payment={"free_input": "배송:30000", "discount": 20000, "deposit": 40000},
        totals={"items_total": 999999, "shipping_price": 888888, "discount_amount": 7},
    )
    resp = client.put(f"/api/orders/{oid}/structured", json={"structured_data": payload})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    totals = _fresh(oid).structured_data["totals"]
    assert totals["items_total"] == 150000
    assert totals["shipping_price"] == 160000       # 품목150000 + 배송30000 - 할인20000
    assert totals["discount_amount"] == 20000       # 클라이언트 7 무시
    assert totals["deposit_amount"] == 40000
    assert totals["balance_amount"] == 120000


# --------------------------------------------------------------------------
# provenance 보존: raw/schema/confidence(sd 키·Order 컬럼) client overwrite 금지
# --------------------------------------------------------------------------
def test_put_preserves_provenance_against_client_overwrite(client):
    """기존 provenance(sd confidence/raw/schema · Order 컬럼)를 폼 저장이 덮어쓰지 못한다."""
    _login_admin(client, "data01-provenance")
    sd0 = _valid_form_payload(
        confidence="high",
        raw={"text": "원본 파싱 텍스트"},
        schema_version=3,
        parsed_at="2026-01-01T00:00:00",
    )
    oid = _create_order(
        structured_data=sd0,
        raw_order_text="원본 파싱 텍스트",
        structured_confidence="high",
        structured_schema_version=3,
    )

    # 폼이 provenance 를 위조해서 보내도(구 클라이언트/공격자) 서버가 무시해야 한다.
    forged = _valid_form_payload(
        confidence="forged-low",
        raw={"text": "HACKED"},
        schema_version=1,
    )
    resp = client.put(
        f"/api/orders/{oid}/structured",
        json={
            "structured_data": forged,
            "raw_order_text": "",            # 원본 지우기 시도
            "structured_confidence": None,   # confidence 지우기 시도
            "structured_schema_version": 1,
        },
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    saved = _fresh(oid)
    assert saved.structured_data["confidence"] == "high"
    assert saved.structured_data["raw"] == {"text": "원본 파싱 텍스트"}
    assert saved.structured_data["schema_version"] == 3
    assert saved.raw_order_text == "원본 파싱 텍스트"
    assert saved.structured_confidence == "high"
    assert saved.structured_schema_version == 3


# --------------------------------------------------------------------------
# partial allowlist: 임의 최상위 키 거부
# --------------------------------------------------------------------------
def test_put_strips_arbitrary_injected_top_level_keys(client):
    """폼이 도입할 수 없는 임의 최상위 키는 저장되지 않는다(임의 필드 금지)."""
    _login_admin(client, "data01-allowlist")
    oid = _create_order()

    payload = _valid_form_payload()
    payload["evil_inject"] = {"is_admin": True}
    payload["__forged_axis"] = "COMPLETED"
    resp = client.put(f"/api/orders/{oid}/structured", json={"structured_data": payload})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    sd = _fresh(oid).structured_data
    assert "evil_inject" not in sd
    assert "__forged_axis" not in sd
    assert sd["parties"]["customer"]["name"] == "홍길동"   # 허용 필드는 반영


# --------------------------------------------------------------------------
# clear intent: 부분 누락은 clear 가 아니다 / 명시 값만 반영
# --------------------------------------------------------------------------
def test_put_omission_preserves_operational_subtree(client):
    """폼 payload 가 운영 subtree 를 누락해도 서버 스냅샷을 보존(clear 아님)."""
    _login_admin(client, "data01-clear-omit")
    sd0 = _valid_form_payload()
    sd0["channeltalk_push"] = {"pushed": True, "message_id": "keep-1"}
    sd0["assignments"] = {"drawing_assignee_user_ids": [41], "owner_team": "DRAWING"}
    oid = _create_order(structured_data=sd0)

    payload = _valid_form_payload()  # channeltalk_push·assignments 누락
    resp = client.put(f"/api/orders/{oid}/structured", json={"structured_data": payload})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    sd = _fresh(oid).structured_data
    assert sd["channeltalk_push"] == {"pushed": True, "message_id": "keep-1"}
    assert sd["assignments"]["drawing_assignee_user_ids"] == [41]


def test_put_explicit_field_value_is_applied(client):
    """명시적으로 보낸 폼 필드 값은 반영된다(clear intent 의 반대 방향)."""
    _login_admin(client, "data01-clear-explicit")
    sd0 = _valid_form_payload(flags={"urgent": False})
    oid = _create_order(structured_data=sd0)

    payload = _valid_form_payload(flags={"urgent": True, "urgent_reason": "긴급건"})
    resp = client.put(f"/api/orders/{oid}/structured", json={"structured_data": payload})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    sd = _fresh(oid).structured_data
    assert sd["flags"]["urgent"] is True
    assert sd["flags"]["urgent_reason"] == "긴급건"


# --------------------------------------------------------------------------
# stale tab (If-Match / mutation_version 낙관 잠금)
# --------------------------------------------------------------------------
def test_put_stale_if_match_conflicts_and_leaves_state_unchanged(client):
    """stale If-Match → 409 · structured_data/version 완전 불변."""
    _login_admin(client, "data01-stale")
    oid = _create_order()
    before = _fresh(oid)
    before_version = before.mutation_version
    before_sd = copy.deepcopy(before.structured_data)

    resp = client.put(
        f"/api/orders/{oid}/structured",
        json={"structured_data": _valid_form_payload(items=[{"product_name": "변경시도", "price": 1}])},
        headers={"If-Match": str(before_version + 5)},
    )
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json().get("code") == "REVISION_CONFLICT"

    fresh = _fresh(oid)
    assert fresh.mutation_version == before_version         # version 불변
    assert fresh.structured_data == before_sd               # 상태 불변


def test_put_matching_if_match_succeeds(client):
    """정확한 If-Match(현재 mutation_version) → 200 저장·version++."""
    _login_admin(client, "data01-match")
    oid = _create_order()
    current = _fresh(oid).mutation_version

    resp = client.put(
        f"/api/orders/{oid}/structured",
        json={"structured_data": _valid_form_payload(items=[{"product_name": "붙박이장", "price": 500000}])},
        headers={"If-Match": str(current)},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    fresh = _fresh(oid)
    assert fresh.mutation_version == current + 1
    assert fresh.structured_data["items"][0]["price"] == 500000


def test_get_returns_mutation_version_for_if_match(client):
    """GET structured 는 If-Match 로 되돌릴 mutation_version 을 반환한다."""
    _login_admin(client, "data01-get-version")
    oid = _create_order()
    resp = client.get(f"/api/orders/{oid}/structured")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["mutation_version"] == _fresh(oid).mutation_version

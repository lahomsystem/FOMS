"""ERP 주문 → WDCalculator 견적 동기화 엔드포인트 회귀 테스트.

Phase 1: POST /api/orders/<id>/wdc-estimate-sync (Estimate upsert + 멱등 매칭).
"""
from db import db_session
from models import Order
from wdcalculator_db import wd_calculator_session
from wdcalculator_models import Estimate, EstimateHistory, EstimateOrderMatch


def _create_order(**overrides) -> Order:
    payload = {
        "received_date": "2026-06-23",
        "customer_name": "현장 고객",
        "phone": "010-1111-2222",
        "address": "Seoul",
        "product": "Wardrobe",
        "status": "RECEIVED",
        "structured_data": {},
    }
    payload.update(overrides)
    order = Order(**payload)
    db_session.add(order)
    db_session.commit()
    return order


def _estimate_data():
    return {
        "estimates": [
            {
                "id": None,
                "productId": 1,
                "productName": "Seed Product",
                "widthMm": 300,
                "basePrice": 1000,
                "options": [],
                "additionalPrice": 0,
                "totalPrice": 1000,
            }
        ],
        "totalBasePrice": 1000,
        "totalAdditionalPrice": 0,
        "totalPrice": 1000,
        "source": "erp_spec_calc",
    }


def test_sync_creates_estimate_and_matches_order(wdcalculator_settings_env, login):
    """estimate_id 없이 호출하면 견적 생성 + 주문 매칭이 한 번에 된다."""
    client = login
    order = _create_order(customer_name="동기화 고객")
    order_id = order.id

    response = client.post(
        f"/api/orders/{order_id}/wdc-estimate-sync",
        json={"customer_name": "동기화 고객", "estimate_data": _estimate_data()},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert isinstance(payload["estimate_id"], int)
    assert payload["matched"] is True

    estimate = wd_calculator_session.query(Estimate).filter(
        Estimate.id == payload["estimate_id"]
    ).first()
    assert estimate is not None
    assert estimate.customer_name == "동기화 고객"

    matches = wd_calculator_session.query(EstimateOrderMatch).filter(
        EstimateOrderMatch.order_id == order_id
    ).all()
    assert len(matches) == 1
    assert matches[0].estimate_id == payload["estimate_id"]


def test_sync_is_idempotent_on_resave(wdcalculator_settings_env, login):
    """같은 estimate_id로 재호출하면 견적은 갱신, 매칭은 중복 생성되지 않는다."""
    client = login
    order = _create_order(customer_name="재저장 고객")
    order_id = order.id

    first = client.post(
        f"/api/orders/{order_id}/wdc-estimate-sync",
        json={"customer_name": "재저장 고객", "estimate_data": _estimate_data()},
    ).get_json()
    estimate_id = first["estimate_id"]

    updated = _estimate_data()
    updated["totalPrice"] = 2000
    second = client.post(
        f"/api/orders/{order_id}/wdc-estimate-sync",
        json={
            "estimate_id": estimate_id,
            "customer_name": "재저장 고객",
            "estimate_data": updated,
        },
    ).get_json()

    assert second["success"] is True
    assert second["estimate_id"] == estimate_id  # 동일 견적 갱신(누적 생성 없음)

    estimates = wd_calculator_session.query(Estimate).all()
    assert len(estimates) == 1
    assert estimates[0].estimate_data["totalPrice"] == 2000

    matches = wd_calculator_session.query(EstimateOrderMatch).filter(
        EstimateOrderMatch.order_id == order_id
    ).all()
    assert len(matches) == 1  # 멱등 매칭

    histories = wd_calculator_session.query(EstimateHistory).filter(
        EstimateHistory.estimate_id == estimate_id
    ).all()
    assert len(histories) == 1  # 갱신 시 직전 스냅샷 1건


def test_sync_rejects_missing_order(wdcalculator_settings_env, login):
    """존재하지 않는 주문은 실패를 반환하고 견적을 만들지 않는다."""
    client = login

    response = client.post(
        "/api/orders/999999/wdc-estimate-sync",
        json={"customer_name": "없는 고객", "estimate_data": _estimate_data()},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is False
    assert wd_calculator_session.query(Estimate).count() == 0


def test_sync_rejects_empty_estimate_data(wdcalculator_settings_env, login):
    """견적 데이터가 비면 실패(주문 저장은 클라이언트 책임이므로 여기선 거부만)."""
    client = login
    order = _create_order()

    response = client.post(
        f"/api/orders/{order.id}/wdc-estimate-sync",
        json={"customer_name": "고객", "estimate_data": {}},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is False


def test_sync_falls_back_to_order_customer_name(wdcalculator_settings_env, login):
    """customer_name 미제공 시 주문 고객명으로 폴백한다."""
    client = login
    order = _create_order(customer_name="주문측 고객")
    order_id = order.id

    response = client.post(
        f"/api/orders/{order_id}/wdc-estimate-sync",
        json={"estimate_data": _estimate_data()},
    )

    payload = response.get_json()
    assert payload["success"] is True
    estimate = wd_calculator_session.query(Estimate).filter(
        Estimate.id == payload["estimate_id"]
    ).first()
    assert estimate.customer_name == "주문측 고객"


def test_sync_persists_estimate_id_into_order_meta(wdcalculator_settings_env, login):
    """Phase 4: 동기화 성공 시 estimate_id가 주문 structured_data.meta에 영속화된다(SSOT 링크)."""
    client = login
    order = _create_order(customer_name="링크 고객", structured_data={"items": []})
    order_id = order.id

    payload = client.post(
        f"/api/orders/{order_id}/wdc-estimate-sync",
        json={"customer_name": "링크 고객", "estimate_data": _estimate_data()},
    ).get_json()
    estimate_id = payload["estimate_id"]

    db_session.expire_all()
    refreshed = db_session.query(Order).filter(Order.id == order_id).first()
    meta = (refreshed.structured_data or {}).get("meta") or {}
    assert meta.get("wdc_estimate_id") == estimate_id
    assert meta.get("wdc_synced_at")  # ISO 타임스탬프 존재


def test_sync_meta_persist_preserves_existing_meta_keys(wdcalculator_settings_env, login):
    """meta 링크 기록은 기존 meta 키(draft 등)를 보존한다(부분 갱신)."""
    client = login
    order = _create_order(
        customer_name="보존 고객",
        structured_data={"meta": {"draft": False, "custom": "keep"}, "items": []},
    )
    order_id = order.id

    payload = client.post(
        f"/api/orders/{order_id}/wdc-estimate-sync",
        json={"customer_name": "보존 고객", "estimate_data": _estimate_data()},
    ).get_json()

    db_session.expire_all()
    refreshed = db_session.query(Order).filter(Order.id == order_id).first()
    meta = (refreshed.structured_data or {}).get("meta") or {}
    assert meta.get("wdc_estimate_id") == payload["estimate_id"]
    assert meta.get("custom") == "keep"
    assert meta.get("draft") is False


def test_full_calculator_save_with_order_id_auto_matches_and_links_meta(wdcalculator_settings_env, login):
    """PC split: full WDCalculator save can persist and match to the source ERP order in one call."""
    client = login
    order = _create_order(customer_name="Split 고객", structured_data={"meta": {"custom": "keep"}})
    order_id = order.id

    response = client.post(
        "/api/wdcalculator/save-estimate",
        json={
            "order_id": order_id,
            "customer_name": "Split 고객",
            "estimate_data": _estimate_data(),
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["matched"] is True
    assert payload["order_id"] == order_id

    matches = wd_calculator_session.query(EstimateOrderMatch).filter(
        EstimateOrderMatch.order_id == order_id
    ).all()
    assert len(matches) == 1
    assert matches[0].estimate_id == payload["estimate_id"]

    db_session.expire_all()
    refreshed = db_session.query(Order).filter(Order.id == order_id).first()
    meta = (refreshed.structured_data or {}).get("meta") or {}
    assert meta.get("wdc_estimate_id") == payload["estimate_id"]
    assert meta.get("custom") == "keep"


def test_full_calculator_save_with_order_id_is_idempotent_on_resave(wdcalculator_settings_env, login):
    """Re-saving the same split estimate updates the estimate without duplicate matches."""
    client = login
    order = _create_order(customer_name="Split 재저장")
    order_id = order.id

    first = client.post(
        "/api/wdcalculator/save-estimate",
        json={
            "order_id": order_id,
            "customer_name": "Split 재저장",
            "estimate_data": _estimate_data(),
        },
    ).get_json()

    updated = _estimate_data()
    updated["totalPrice"] = 3000
    second = client.post(
        "/api/wdcalculator/save-estimate",
        json={
            "order_id": order_id,
            "estimate_id": first["estimate_id"],
            "customer_name": "Split 재저장",
            "estimate_data": updated,
        },
    ).get_json()

    assert second["success"] is True
    assert second["estimate_id"] == first["estimate_id"]
    matches = wd_calculator_session.query(EstimateOrderMatch).filter(
        EstimateOrderMatch.order_id == order_id
    ).all()
    assert len(matches) == 1
    estimate = wd_calculator_session.query(Estimate).filter(
        Estimate.id == first["estimate_id"]
    ).first()
    assert estimate.estimate_data["totalPrice"] == 3000

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


def test_sync_creates_estimate_without_matching_order(wdcalculator_settings_env, login):
    """estimate_id 없이 호출하면 견적은 만들지만 주문 매칭은 만들지 않는다."""
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
    assert payload["matched"] is False

    estimate = wd_calculator_session.query(Estimate).filter(
        Estimate.id == payload["estimate_id"]
    ).first()
    assert estimate is not None
    assert estimate.customer_name == "동기화 고객"

    matches = wd_calculator_session.query(EstimateOrderMatch).filter(
        EstimateOrderMatch.order_id == order_id
    ).all()
    assert matches == []


def test_sync_is_idempotent_on_resave(wdcalculator_settings_env, login):
    """이 주문에 이은 estimate_id로 재호출하면 견적은 갱신, 매칭은 중복 생성되지 않는다."""
    client = login
    order = _create_order(customer_name="재저장 고객")
    order_id = order.id

    first = client.post(
        f"/api/orders/{order_id}/wdc-estimate-sync",
        json={"customer_name": "재저장 고객", "estimate_data": _estimate_data()},
    ).get_json()
    estimate_id = first["estimate_id"]
    # 고치기는 이 주문에 이은 견적만(보안 검토 — 안 이은 견적 번호는 404, test_sync_rejects_estimate_not_matched_to_order).
    wd_calculator_session.add(EstimateOrderMatch(estimate_id=estimate_id, order_id=order_id))
    wd_calculator_session.commit()

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
    assert [m.estimate_id for m in matches] == [estimate_id]  # 손으로 이은 1건 그대로(자동 매칭 금지)

    histories = wd_calculator_session.query(EstimateHistory).filter(
        EstimateHistory.estimate_id == estimate_id
    ).all()
    assert len(histories) == 1  # 갱신 시 직전 스냅샷 1건


def test_sync_rejects_estimate_not_matched_to_order(wdcalculator_settings_env, login):
    """보안 검토 회귀: 본문 estimate_id 가 URL 주문에 이어져 있지 않으면(다른 주문 견적 · 안 이은 견적 · 없는 번호)
    404 이고 견적은 그대로다 — 전에는 번호만 맞으면 아무 견적이나 덮어썼다."""
    client = login
    order_id = _create_order(customer_name="내 주문 고객").id
    other_order_id = _create_order(customer_name="다른 주문 고객").id
    other = Estimate(customer_name="다른 주문 고객", estimate_data=_estimate_data())
    loose = Estimate(customer_name="안 이은 고객", estimate_data=_estimate_data())
    wd_calculator_session.add_all([other, loose])
    wd_calculator_session.flush()
    wd_calculator_session.add(EstimateOrderMatch(estimate_id=other.id, order_id=other_order_id))
    wd_calculator_session.commit()
    other_id, loose_id = other.id, loose.id

    tampered = _estimate_data()
    tampered["totalPrice"] = 1
    for estimate_id in (other_id, loose_id, 999999, "abc"):
        resp = client.post(
            f"/api/orders/{order_id}/wdc-estimate-sync",
            json={"estimate_id": estimate_id, "customer_name": "덮어쓰기", "estimate_data": tampered},
        )
        assert resp.status_code == 404, estimate_id
        assert resp.get_json()["success"] is False

    wd_calculator_session.expire_all()
    for estimate_id in (other_id, loose_id):
        row = wd_calculator_session.query(Estimate).filter(Estimate.id == estimate_id).first()
        assert row.estimate_data["totalPrice"] == 1000 and row.customer_name != "덮어쓰기"
    assert wd_calculator_session.query(EstimateHistory).count() == 0
    assert wd_calculator_session.query(Estimate).count() == 2  # 새 견적도 만들지 않는다

    # 대조군: 같은 견적을 그 견적이 이어진 주문 URL 로 부르면 고쳐진다.
    ok = client.post(
        f"/api/orders/{other_order_id}/wdc-estimate-sync",
        json={"estimate_id": other_id, "customer_name": "다른 주문 고객", "estimate_data": tampered},
    )
    assert ok.status_code == 200 and ok.get_json()["estimate_id"] == other_id
    wd_calculator_session.expire_all()
    assert wd_calculator_session.query(Estimate).filter(Estimate.id == other_id).first().estimate_data["totalPrice"] == 1


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


def test_sync_does_not_persist_estimate_id_into_order_meta(wdcalculator_settings_env, login):
    """자동 동기화 성공 시에도 meta.wdc_estimate_id를 기록하지 않는다."""
    client = login
    order = _create_order(customer_name="링크 고객", structured_data={"items": []})
    order_id = order.id

    payload = client.post(
        f"/api/orders/{order_id}/wdc-estimate-sync",
        json={"customer_name": "링크 고객", "estimate_data": _estimate_data()},
    ).get_json()
    assert payload["matched"] is False

    db_session.expire_all()
    refreshed = db_session.query(Order).filter(Order.id == order_id).first()
    meta = (refreshed.structured_data or {}).get("meta") or {}
    assert "wdc_estimate_id" not in meta
    assert "wdc_synced_at" not in meta


def test_sync_without_meta_link_preserves_existing_meta_keys(wdcalculator_settings_env, login):
    """자동 동기화는 기존 meta 키를 유지하되 wdc 링크를 추가하지 않는다."""
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
    assert "wdc_estimate_id" not in meta
    assert "wdc_synced_at" not in meta
    assert meta.get("custom") == "keep"
    assert meta.get("draft") is False


def test_full_calculator_save_with_order_id_does_not_auto_match_or_link_meta(wdcalculator_settings_env, login):
    """PC split 저장은 견적만 저장하고 주문 매칭/메타 링크는 만들지 않는다."""
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
    assert payload["matched"] is False
    assert payload["order_id"] == order_id

    matches = wd_calculator_session.query(EstimateOrderMatch).filter(
        EstimateOrderMatch.order_id == order_id
    ).all()
    assert matches == []

    db_session.expire_all()
    refreshed = db_session.query(Order).filter(Order.id == order_id).first()
    meta = (refreshed.structured_data or {}).get("meta") or {}
    assert "wdc_estimate_id" not in meta
    assert meta.get("custom") == "keep"


def test_full_calculator_save_with_order_id_is_idempotent_on_resave(wdcalculator_settings_env, login):
    """Re-saving the same split estimate updates the estimate without creating matches."""
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
    assert matches == []
    estimate = wd_calculator_session.query(Estimate).filter(
        Estimate.id == first["estimate_id"]
    ).first()
    assert estimate.estimate_data["totalPrice"] == 3000


def test_unmatch_order_removes_match_and_clears_meta(wdcalculator_settings_env, login):
    """POST unmatch-order는 매칭 행을 제거하고 meta.wdc_estimate_id를 지운다(견적은 유지)."""
    client = login
    order = _create_order(
        customer_name="매칭 해제",
        structured_data={"meta": {"custom": "keep"}},
    )
    order_id = order.id

    sync = client.post(
        f"/api/orders/{order_id}/wdc-estimate-sync",
        json={"customer_name": "매칭 해제", "estimate_data": _estimate_data()},
    ).get_json()
    assert sync["success"] is True
    estimate_id = sync["estimate_id"]
    match = client.post(
        "/api/wdcalculator/match-order",
        json={"estimate_id": estimate_id, "order_id": order_id},
    ).get_json()
    assert match["success"] is True

    response = client.post(
        "/api/wdcalculator/unmatch-order",
        json={"estimate_id": estimate_id, "order_id": order_id},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["removed"] == 1

    matches = wd_calculator_session.query(EstimateOrderMatch).filter(
        EstimateOrderMatch.order_id == order_id
    ).all()
    assert matches == []

    estimate = wd_calculator_session.query(Estimate).filter(Estimate.id == estimate_id).first()
    assert estimate is not None

    db_session.expire_all()
    refreshed = db_session.query(Order).filter(Order.id == order_id).first()
    meta = (refreshed.structured_data or {}).get("meta") or {}
    assert "wdc_estimate_id" not in meta
    assert meta.get("custom") == "keep"

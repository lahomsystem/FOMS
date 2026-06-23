"""ERP 현장 스펙 필드 프리셋(spec_field_presets) CRUD·영속성 회귀 테스트.

Phase 1: WDCalculatorProductSettings 확장 컬럼 + /api/wdcalculator/spec-field-presets.
"""
import json

from wdcalculator_db import wd_calculator_session
from wdcalculator_models import WDCalculatorProductSettings


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_spec_field_presets_get_returns_seed(wdcalculator_settings_env, login):
    """초기 GET은 시드 파일 기반 4개 필드 프리셋을 반환한다."""
    client = login

    response = client.get("/api/wdcalculator/spec-field-presets")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    presets = payload["spec_field_presets"]
    assert set(presets.keys()) == {"color", "handle", "internal", "misc"}
    assert presets["color"][0]["name"] == "화이트"
    assert presets["handle"][0]["name"] == "히든손잡이"


def test_spec_field_presets_add_single_value(wdcalculator_settings_env, login):
    """단건 추가 후 재조회 시 신규 값이 보존된다(자동 id 채번)."""
    client = login

    add_response = client.post(
        "/api/wdcalculator/spec-field-presets",
        json={"field": "color", "name": "네이비"},
    )

    assert add_response.status_code == 200
    add_payload = add_response.get_json()
    assert add_payload["success"] is True
    assert add_payload["preset"]["name"] == "네이비"
    assert isinstance(add_payload["preset"]["id"], int)

    reloaded = client.get("/api/wdcalculator/spec-field-presets").get_json()
    names = [p["name"] for p in reloaded["spec_field_presets"]["color"]]
    assert "네이비" in names


def test_spec_field_presets_rejects_unknown_field(wdcalculator_settings_env, login):
    """화이트리스트 밖 필드는 거부한다(제품명/옵션은 별도 소스)."""
    client = login

    response = client.post(
        "/api/wdcalculator/spec-field-presets",
        json={"field": "product_name", "name": "몰딩"},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is False


def test_spec_field_presets_replace_all_values(wdcalculator_settings_env, login):
    """values 배열 전체 교체 모드는 해당 필드 프리셋을 통째로 치환한다."""
    client = login

    response = client.post(
        "/api/wdcalculator/spec-field-presets",
        json={"field": "handle", "values": ["바형", "노브형", "노브형", ""]},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    handle_presets = payload["spec_field_presets"]["handle"]
    # 빈값·중복 제거 후 2개, id 자동 채번
    names = [p["name"] for p in handle_presets]
    assert names == ["바형", "노브형"]
    assert all(isinstance(p["id"], int) for p in handle_presets)


def test_spec_field_presets_delete(wdcalculator_settings_env, login):
    """단건 삭제 후 재조회 시 해당 id가 사라진다."""
    client = login
    add_payload = client.post(
        "/api/wdcalculator/spec-field-presets",
        json={"field": "misc", "name": "현관"},
    ).get_json()
    preset_id = add_payload["preset"]["id"]

    delete_response = client.delete(
        f"/api/wdcalculator/spec-field-presets/misc/{preset_id}"
    )

    assert delete_response.status_code == 200
    assert delete_response.get_json()["success"] is True
    reloaded = client.get("/api/wdcalculator/spec-field-presets").get_json()
    ids = [p["id"] for p in reloaded["spec_field_presets"]["misc"]]
    assert preset_id not in ids


def test_spec_field_presets_persist_in_db_after_seed_change(wdcalculator_settings_env, login):
    """저장 후 시드 파일이 바뀌어도 DB 상태가 우선된다(파일로 복귀 금지)."""
    client = login
    assert client.post(
        "/api/wdcalculator/spec-field-presets",
        json={"field": "color", "name": "민트"},
    ).get_json()["success"] is True

    _write_json(
        wdcalculator_settings_env["spec_presets_path"],
        {"spec_field_presets": {"color": [{"id": 1, "name": "파일값"}]}},
    )

    wd_calculator_session.expire_all()
    reloaded = client.get("/api/wdcalculator/spec-field-presets").get_json()
    names = [p["name"] for p in reloaded["spec_field_presets"]["color"]]
    assert "민트" in names
    assert "파일값" not in names

    settings = wd_calculator_session.query(WDCalculatorProductSettings).filter(
        WDCalculatorProductSettings.id == 1
    ).first()
    assert settings is not None
    assert any(p["name"] == "민트" for p in settings.spec_field_presets["color"])


def test_spec_field_presets_does_not_break_product_save(wdcalculator_settings_env, login):
    """프리셋 컬럼 추가 후에도 기존 제품 저장 경로가 정상 동작한다(회귀)."""
    client = login

    save_response = client.post(
        "/api/wdcalculator/products",
        json={
            "name": "몰딩(푸쉬)",
            "category": "몰딩",
            "pricing_type": "1m",
            "additional_options": [],
            "coupon_type": "percentage",
            "coupon_value": 0,
            "price_1m": 50000,
        },
    )

    assert save_response.status_code == 200
    assert save_response.get_json()["success"] is True
    # 같은 싱글턴에 presets가 공존해도 충돌 없음
    presets = client.get("/api/wdcalculator/spec-field-presets").get_json()
    assert presets["success"] is True

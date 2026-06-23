"""제품 설정 페이지의 '현장 스펙 프리셋 관리' 섹션 렌더 계약 테스트.

Phase 2: product_settings.html 섹션 + 초기 데이터 주입 + 분리 JS(defer) 로드.
"""
import json
import re


def test_product_settings_renders_spec_preset_section(wdcalculator_settings_env, login):
    """4개 스펙 필드 그룹과 입력/칩 컨테이너가 렌더된다."""
    client = login

    response = client.get("/wdcalculator/product-settings")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="specPresetGroups"' in body
    for field in ("color", "handle", "internal", "misc"):
        assert f'data-spec-field="{field}"' in body
    assert "현장 스펙 프리셋 관리" in body
    assert body.count("spec-preset-input") >= 4
    assert body.count("spec-preset-chips") >= 4


def test_product_settings_injects_initial_spec_presets(wdcalculator_settings_env, login):
    """초기 프리셋 데이터가 안전 JSON으로 주입된다(시드값 포함)."""
    client = login

    response = client.get("/wdcalculator/product-settings")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    match = re.search(
        r'<script type="application/json" id="initial-spec-presets">\s*(.+?)\s*</script>',
        body,
        re.S,
    )
    assert match is not None
    payload = json.loads(match.group(1))
    assert set(payload.keys()) == {"color", "handle", "internal", "misc"}
    color_names = [p["name"] for p in payload["color"]]
    assert "화이트" in color_names


def test_product_settings_loads_spec_presets_script_deferred(wdcalculator_settings_env, login):
    """전용 프리셋 JS가 defer로 로드된다(렌더 차단 금지, 가드 G1)."""
    client = login

    response = client.get("/wdcalculator/product-settings")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "js/wdcalculator/spec-presets-settings.js" in body
    match = re.search(
        r"<script[^>]*js/wdcalculator/spec-presets-settings\.js[^>]*>",
        body,
    )
    assert match is not None
    assert "defer" in match.group(0)


def test_product_settings_saved_preset_appears_on_reload(wdcalculator_settings_env, login):
    """프리셋 저장 후 페이지 재요청 시 주입 데이터에 반영된다(서버 라운드트립)."""
    client = login
    assert client.post(
        "/api/wdcalculator/spec-field-presets",
        json={"field": "handle", "name": "양개형"},
    ).get_json()["success"] is True

    body = client.get("/wdcalculator/product-settings").get_data(as_text=True)
    match = re.search(
        r'<script type="application/json" id="initial-spec-presets">\s*(.+?)\s*</script>',
        body,
        re.S,
    )
    payload = json.loads(match.group(1))
    handle_names = [p["name"] for p in payload["handle"]]
    assert "양개형" in handle_names

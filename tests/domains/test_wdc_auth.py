"""WDC-AUTH-01: WDCalculator blueprint 권한 registry 계약 테스트 (red→green).

SSOT: docs/plans/2026-07-22-foms-full-system-bug-audit-report.md §5.2 WDC-AUTH-01 —
"WDC blueprint policy registry | calculate pure; estimate CS/SALES; master MANAGER+;
VIEWER read | calculate 금지 rollback 금지".

**2026-07-31 결정 변경**: WDC-AUTH-01 은 master(product/category/notes/spec-preset)
mutation 을 ``MASTER_MUTATION``(ADMIN/MANAGER 전용)으로 분류했으나, 운영 배포 전
사용자 결재로 **잠금을 채우지 않고 운영 현행(로그인한 누구나, ``@login_required`` 만)을
유지**하기로 확정했다. 이에 따라 master 12개 엔드포인트는 ``MASTER_MUTATION`` 이 아니라
``WDC_CALCULATE``(teams="*", viewer=True — 로그인 사용자 누구나 통과, 미인증만 401)로
route manifest 를 재분류했다. ``MASTER_MUTATION`` 자체는 정책 정의·notifications
전용 라우트(``notifications.api_notifications_delete_all``)에 그대로 남는다(무편집).

investigation-first 로 확인한 사실: WDC 라우트는 이미 AUTH-01 이 만든 공용 정책 SSOT
(``foms.services.orders.order_mutation_policy``)와 route manifest
(``docs/harness/foms_order_mutation_policy_manifest.json``)에 ``WDC_CALCULATE``·
``WDC_ESTIMATE`` 로 분류되어 있다(재사용, 무편집). 이 파일은 그 분류가 위 결정(calculate
pure/estimate CS·SALES/master=로그인 전원 허용)과 정확히 일치함을 WDC 전용으로 증명하고,
"calculate 차단 rollback" 및 "master 잠금 무단 부활" 회귀를 감시한다.

가드는 ``AUTH_POLICY_ENABLED`` config(미지정 시 ``not TESTING``)로 켜진다. 기존 테스트는
``TESTING=True`` + 미지정이라 가드 OFF 로 통과하고(회귀 0), 이 파일만 ``policy_on``
픽스처로 명시 활성화한 뒤 원복한다(test_auth_enforcement.py 관례 준용).
"""

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import User
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, load_policy_manifest

_MASTER_ROUTE_ENDPOINTS = (
    "wdcalculator.api_wdcalculator_save_product",
    "wdcalculator.api_wdcalculator_delete_product",
    "wdcalculator.api_wdcalculator_save_category",
    "wdcalculator.api_wdcalculator_delete_category",
    "wdcalculator.api_wdcalculator_save_option",
    "wdcalculator.api_wdcalculator_delete_option",
    "wdcalculator.api_wdcalculator_save_notes_category",
    "wdcalculator.api_wdcalculator_delete_notes_category",
    "wdcalculator.api_wdcalculator_save_notes_option",
    "wdcalculator.api_wdcalculator_delete_notes_option",
    "wdcalculator.api_wdcalculator_save_spec_field_preset",
    "wdcalculator.api_wdcalculator_delete_spec_field_preset",
)

_ESTIMATE_ROUTE_ENDPOINTS = (
    "wdcalculator.api_wdcalculator_save_estimate",
    "wdcalculator.api_wdcalculator_match_order",
    "wdcalculator.api_wdcalculator_unmatch_order",
    "wdcalculator.api_orders_wdc_estimate_sync",
    "wdcalculator.api_wdcalculator_estimate",
)


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼 (test_auth_enforcement.py 관례 재사용)
# --------------------------------------------------------------------------
@pytest.fixture
def policy_on(app):
    """이 테스트 동안만 정책 가드를 강제 활성화하고 원복한다."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


def _make_user(username, *, role="STAFF", team=None):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _denied(resp, status=403):
    """정책 가드가 거부했는가(status + X-Auth-Policy)."""
    return resp.status_code == status and resp.headers.get("X-Auth-Policy") == "denied"


def _gate_passed(resp):
    """정책 가드를 통과했는가(handler 가 실행되었는가)."""
    return resp.headers.get("X-Auth-Policy") is None


def _estimate_payload(name="김철수"):
    return {"customer_name": name, "estimate_data": {"totalPrice": 1000, "estimates": []}}


def _product_payload(name="테스트 제품"):
    return {"name": name, "pricing_type": "30cm", "price_30cm": 1000, "price_1cm": 10}


# --------------------------------------------------------------------------
# manifest 정본 — calculate pure / estimate CS·SALES / master=로그인 전원 허용 분류 확인
# --------------------------------------------------------------------------
def test_manifest_classifies_wdc_routes_per_spec():
    """WDC route→policy_id 분류가 2026-07-31 결정(master 잠금 미채움, 운영 현행 유지)과 일치한다."""
    manifest = load_policy_manifest()
    routes = manifest["routes"]

    assert routes["wdcalculator.api_wdcalculator_calculate"]["policy_id"] == "WDC_CALCULATE"
    for ep in _ESTIMATE_ROUTE_ENDPOINTS:
        assert routes[ep]["policy_id"] == "WDC_ESTIMATE", ep
    # master(product/category/notes/spec-preset) 는 MASTER_MUTATION 이 아니라 WDC_CALCULATE
    # 로 분류된다 — 로그인 사용자 누구나 통과(잠금 미채움, 운영 현행 유지).
    for ep in _MASTER_ROUTE_ENDPOINTS:
        assert routes[ep]["policy_id"] == "WDC_CALCULATE", ep


def test_calculate_policy_is_pure_and_viewer_allowed():
    """calculate 정책은 VIEWER 허용(계산 자체를 role 로 막지 않음) — rollback 감시 지점."""
    policy = POLICY_REGISTRY["WDC_CALCULATE"]
    assert policy.viewer is True
    assert policy.teams == "*"


def test_estimate_policy_is_cs_sales_only():
    """estimate 정책은 CS/SALES team-wide, VIEWER deny."""
    policy = POLICY_REGISTRY["WDC_ESTIMATE"]
    assert policy.teams == ("CS", "SALES")
    assert policy.viewer is False


def test_master_mutation_policy_definition_unchanged_but_unused_by_wdc():
    """MASTER_MUTATION 정책 정의 자체(ADMIN/MANAGER 전용)는 그대로다 — 정책 SSOT 는 무편집
    (notifications.api_notifications_delete_all 이 계속 쓴다). 다만 WDC master 라우트는
    2026-07-31 결정 이후 더 이상 이 policy_id 를 참조하지 않는다 — manifest 상 잔여
    MASTER_MUTATION 라우트는 notifications 1건뿐이어야 한다."""
    policy = POLICY_REGISTRY["MASTER_MUTATION"]
    assert policy.teams == ()
    assert policy.viewer is False
    assert policy.manager_ok is True

    manifest = load_policy_manifest()
    routes = manifest["routes"]
    master_policy_routes = sorted(
        ep for ep, r in routes.items() if r.get("policy_id") == "MASTER_MUTATION"
    )
    assert master_policy_routes == ["notifications.api_notifications_delete_all"]


# --------------------------------------------------------------------------
# calculate: pure — VIEWER 포함 인증 사용자 허용, 미인증 거부, 부작용 0
# --------------------------------------------------------------------------
def test_calculate_allows_viewer_pure_no_side_effect(client, app, policy_on, wdcalculator_settings_env):
    """VIEWER 도 calculate 는 통과(pure calc)하고, 제품 마스터 데이터는 변하지 않는다."""
    _login(client, _make_user("wdc-viewer-calc", role="VIEWER"))
    before = client.get("/api/wdcalculator/products").get_json()["products"]

    resp = client.post("/api/wdcalculator/calculate", json={"product_id": 1, "width_mm": 900})

    assert _gate_passed(resp)
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    after = client.get("/api/wdcalculator/products").get_json()["products"]
    assert after == before  # 부작용 0


def test_calculate_denies_unauthenticated(client, app, policy_on):
    """미인증 calculate 호출은 정책 가드가 401 로 거부한다(handler 미실행)."""
    resp = client.post("/api/wdcalculator/calculate", json={"product_id": 1, "width_mm": 900})
    assert _denied(resp, status=401)


# --------------------------------------------------------------------------
# estimate: CS/SALES 200, 그 외(VIEWER/PRODUCTION 등) 403
# --------------------------------------------------------------------------
@pytest.mark.parametrize("team", ["CS", "SALES"])
def test_estimate_save_allowed_for_cs_and_sales(client, app, policy_on, wdcalculator_settings_env, team):
    """CS/SALES 팀 STAFF 는 견적 저장이 200 성공한다."""
    _login(client, _make_user(f"wdc-{team.lower()}-est", role="STAFF", team=team))
    resp = client.post("/api/wdcalculator/save-estimate", json=_estimate_payload())
    assert _gate_passed(resp)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["estimate_id"]


@pytest.mark.parametrize("role,team", [("VIEWER", None), ("STAFF", "PRODUCTION")])
def test_estimate_save_denied_for_others(client, app, policy_on, wdcalculator_settings_env, role, team):
    """VIEWER/무관 팀(PRODUCTION 등)은 견적 저장이 403."""
    _login(client, _make_user(f"wdc-deny-{role.lower()}-{team}", role=role, team=team))
    resp = client.post("/api/wdcalculator/save-estimate", json=_estimate_payload())
    assert _denied(resp)


def test_estimate_save_allowed_for_admin_and_manager_override(client, app, policy_on, wdcalculator_settings_env):
    """ADMIN/MANAGER 는 team 무관 override 로 견적 저장도 통과한다."""
    for role in ("ADMIN", "MANAGER"):
        _login(client, _make_user(f"wdc-{role.lower()}-est", role=role))
        resp = client.post("/api/wdcalculator/save-estimate", json=_estimate_payload())
        assert _gate_passed(resp)
        assert resp.status_code == 200 and resp.get_json()["success"] is True


# --------------------------------------------------------------------------
# master: 2026-07-31 결정 — 잠금 미채움, 운영 현행 유지(로그인 전원 200, 미인증만 401)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role,team", [
    ("ADMIN", None),
    ("MANAGER", None),
    ("VIEWER", None),
    ("STAFF", "CS"),
    ("STAFF", "SALES"),
    ("STAFF", "PRODUCTION"),
])
def test_master_mutation_allowed_for_any_logged_in_user(client, app, policy_on, wdcalculator_settings_env, role, team):
    """운영 현행 유지: WDC master(제품) 저장은 role/team 무관 로그인 사용자면 전부 200."""
    _login(client, _make_user(f"wdc-master-allow-{role.lower()}-{team}", role=role, team=team))
    resp = client.post("/api/wdcalculator/products", json=_product_payload())
    assert _gate_passed(resp)
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_master_mutation_denies_unauthenticated(client, app, policy_on):
    """미인증 WDC master 저장 호출은 정책 가드가 401 로 거부한다(handler 미실행) — 로그인만 요구."""
    resp = client.post("/api/wdcalculator/products", json=_product_payload())
    assert _denied(resp, status=401)


# --------------------------------------------------------------------------
# VIEWER: read 전부 200, master/calculate 도 통과(로그인=허용), estimate 만 403
# --------------------------------------------------------------------------
def test_viewer_can_read_all_wdc_endpoints(client, app, policy_on, wdcalculator_settings_env):
    """VIEWER 는 WDC 조회(GET) 전 엔드포인트를 200 으로 읽을 수 있다."""
    _login(client, _make_user("wdc-viewer-read", role="VIEWER"))
    assert client.get("/api/wdcalculator/products").status_code == 200
    assert client.get("/api/wdcalculator/additional-options/categories").status_code == 200
    assert client.get("/api/wdcalculator/notes/categories").status_code == 200
    assert client.get("/api/wdcalculator/spec-field-presets").status_code == 200
    assert client.get("/api/wdcalculator/search-estimates").status_code == 200


def test_viewer_allowed_wdc_master_and_calculate_denied_only_estimate(client, app, policy_on, wdcalculator_settings_env):
    """VIEWER 는 master(제품) 저장·calculate 는 통과(로그인=허용), estimate save/match 만 CS/SALES
    전용이라 403 — 2026-07-31 결정으로 master 잠금을 채우지 않은 계약을 못박는다."""
    _login(client, _make_user("wdc-viewer-mut", role="VIEWER"))
    assert _gate_passed(client.post("/api/wdcalculator/products", json=_product_payload()))
    assert _denied(client.post("/api/wdcalculator/save-estimate", json=_estimate_payload()))
    assert _denied(client.post("/api/wdcalculator/match-order", json={"estimate_id": 1, "order_id": 1}))
    assert _gate_passed(client.post("/api/wdcalculator/calculate", json={"product_id": 1, "width_mm": 900}))


# --------------------------------------------------------------------------
# 가드 OFF 기본값에서는 무회귀 (기존 테스트 영향 0 증명)
# --------------------------------------------------------------------------
def test_policy_inactive_by_default_under_testing(client, app, wdcalculator_settings_env):
    """AUTH_POLICY_ENABLED 미지정 + TESTING → 가드 OFF, VIEWER 도 master mutation 차단 없음."""
    app.config.pop("AUTH_POLICY_ENABLED", None)
    _login(client, _make_user("wdc-viewer-gateoff", role="VIEWER"))
    resp = client.post("/api/wdcalculator/products", json=_product_payload())
    assert resp.headers.get("X-Auth-Policy") is None  # 가드 미개입

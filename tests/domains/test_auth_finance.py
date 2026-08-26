"""AUTH-FINANCE-01: 금융 mutation 권한 확정 matrix (P0-3 완결, red→green).

settlement/cash-receipt/payment-confirm 세 금융 endpoint에 AUTH-01 ``FINANCE_MUTATION``
정책(§2.1 line 153)을 확정 적용한다:

* 허용: ``ADMIN`` / ``MANAGER`` / ``STAFF+CS`` / ``STAFF+SALES``.
* 거부(403): ``VIEWER`` 및 CS/SALES 가 아닌 모든 STAFF 팀(PRODUCTION/DRAWING/
  CONSTRUCTION/SHIPMENT). 거부 시 handler 미실행이라 **DB/OrderEvent/SecurityLog 변화 0**.
* payment-confirm 의 과거 ``@role_required(['ADMIN','MANAGER','STAFF'])`` **대칭 STAFF 허용**은
  이 matrix 로 교정된다(PRODUCTION 등 비-finance STAFF 는 이제 403).

정책 가드는 AUTH-01 과 동일하게 ``AUTH_POLICY_ENABLED`` config 로 켜고(``policy_on`` 픽스처),
manifest 는 세 endpoint 를 모두 ``FINANCE_MUTATION`` 으로 이미 분류한다(재사용). 가드는 handler
실행 **전** 차단이므로 거부 응답에는 ``X-Auth-Policy: denied`` 헤더가 붙는다.
"""

from collections import Counter

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, SecurityLog, User

# --------------------------------------------------------------------------
# 세 금융 endpoint: (method, path 템플릿, 잘 구성된 body)
# --------------------------------------------------------------------------
_FINANCE_SURFACES = [
    ("POST", "/api/orders/{oid}/settlement/issue",
     {"department": "SALES", "amount": 1000, "reason": "재방문 비용"}),
    ("POST", "/api/orders/{oid}/cash-receipt/issue", {"note": "지류 발행"}),
    ("POST", "/api/orders/{oid}/payment-confirm", {"type": "deposit", "confirmed": True}),
]

# 거부되어야 하는 role/team (VIEWER + 비 CS/SALES STAFF)
_DENIED_ACTORS = [
    ("VIEWER", None),
    ("STAFF", "PRODUCTION"),
    ("STAFF", "DRAWING"),
    ("STAFF", "CONSTRUCTION"),
    ("STAFF", "SHIPMENT"),
]

# 허용되어야 하는 role/team (ADMIN/MANAGER + STAFF CS/SALES)
_ALLOWED_ACTORS = [
    ("ADMIN", None),
    ("MANAGER", None),
    ("STAFF", "CS"),
    ("STAFF", "SALES"),
]


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼 (AUTH-01 test_auth_enforcement 규약 준용)
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


_seq = 0


def _make_user(role="STAFF", team=None):
    global _seq
    _seq += 1
    user = User(
        username=f"fin_{role}_{team}_{_seq}",
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{role}-{team}-{_seq}",
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


def _make_order(status="COMPLETED"):
    order = Order(
        received_date="2026-04-07",
        customer_name="금융 대상",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        status=status,
        manager_name="Alice",
        is_erp_order=True,
        structured_data={"payment": {}},
        erp_stage_code=status,
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _denied(resp):
    return resp.status_code == 403 and resp.headers.get("X-Auth-Policy") == "denied"


def _gate_passed(resp):
    return resp.headers.get("X-Auth-Policy") is None


# 거부 감사는 정책이 **의도적으로** 남기는 기록이다(order_mutation_policy._audit →
# record_access_denied, structured_action="ACCESS_DENIED"). 도메인 기록과 구분한다.
_DENIAL_AUDIT_PREFIX = "권한 거부(주문 정책)"


def _finance_side_effect_counts(order_id):
    """거부 증명용: 해당 주문의 OrderEvent, 전역 SecurityLog 메시지, structured_data 스냅샷.

    Args:
        order_id: 검사 대상 주문 id.

    Returns:
        ``(OrderEvent 수, SecurityLog 메시지 리스트, structured_data)``.
    """
    db_session.expire_all()
    events = db_session.query(OrderEvent).filter(OrderEvent.order_id == order_id).count()
    logs = [row.message or "" for row in db_session.query(SecurityLog).all()]
    saved = db_session.get(Order, order_id)
    sd = saved.structured_data or {}
    return events, logs, sd


# --------------------------------------------------------------------------
# 거부 matrix — VIEWER + 비 CS/SALES STAFF (P0-3, 403 + DB/event/log 0)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role,team", _DENIED_ACTORS)
@pytest.mark.parametrize("method,path,body", _FINANCE_SURFACES)
def test_finance_denied_no_side_effects(client, app, policy_on, role, team, method, path, body):
    """VIEWER·비 CS/SALES STAFF 의 금융 mutation → 403 + OrderEvent/DB 변화 0(거부 감사만 허용)."""
    _login(client, _make_user(role=role, team=team))
    oid = _make_order("COMPLETED")

    before = _finance_side_effect_counts(oid)
    resp = client.open(path.format(oid=oid), method=method, json=body)
    after = _finance_side_effect_counts(oid)

    assert _denied(resp), (role, team, path, resp.status_code, resp.headers.get("X-Auth-Policy"))
    assert resp.is_json and resp.get_json()["success"] is False
    assert "Location" not in resp.headers  # redirect 아님(/api JSON)

    # 거부 = handler 미실행 → 도메인 side-effect 0
    assert after[0] == before[0] == 0, f"OrderEvent 변화: {before[0]}→{after[0]}"

    # SecurityLog 는 "전역 개수 동결" 로 볼 수 없다. 정책 가드가 거부를 감사 기록으로
    # 남기는 것은 설계된 동작이기 때문이다(_audit → record_access_denied). 예전 단언은
    # 전역 개수가 그대로일 것을 요구했는데, 그건 record_access_denied 의 60초 dedupe
    # 창(user/IP, endpoint, action) 덕분에 **앞선 테스트가 같은 거부를 이미 기록해
    # 놓았을 때만** 성립했다. 그래서 이 파일을 단독으로 돌리면 실패했고, 전체 스위트
    # 순서에서만 통과했다(병렬 실행에서 드러난 잠복 순서 의존).
    # 진짜 계약은 "handler 가 안 돌았다" 이므로, 새로 생긴 기록이 거부 감사뿐임을 본다.
    added_logs = Counter(after[1]) - Counter(before[1])
    unexpected = [msg for msg in added_logs if not msg.startswith(_DENIAL_AUDIT_PREFIX)]
    assert not unexpected, f"거부인데 도메인 SecurityLog 가 생겼다: {unexpected}"
    # settlement/cash_receipt 미기록, payment 미확인
    settlement = after[2].get("settlement") or {}
    assert "cash_receipt" not in settlement and not settlement.get("deductions")
    assert not (after[2].get("payment") or {}).get("deposit_confirmed")


# --------------------------------------------------------------------------
# 허용 matrix — ADMIN/MANAGER + STAFF CS/SALES (정상 200)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role,team", _ALLOWED_ACTORS)
@pytest.mark.parametrize("method,path,body", _FINANCE_SURFACES)
def test_finance_allowed_roles_pass(client, app, policy_on, role, team, method, path, body):
    """ADMIN/MANAGER·STAFF+CS/SALES 는 금융 mutation 게이트 통과(정상 200)."""
    _login(client, _make_user(role=role, team=team))
    oid = _make_order("COMPLETED")

    resp = client.open(path.format(oid=oid), method=method, json=body)

    assert _gate_passed(resp), (role, team, path, resp.headers.get("X-Auth-Policy"))
    assert resp.status_code == 200, (role, team, path, resp.get_data(as_text=True))
    assert resp.get_json()["success"] is True


# --------------------------------------------------------------------------
# payment-confirm 대칭 STAFF 허용 교정 (구 @role_required 버그)
# --------------------------------------------------------------------------
def test_payment_confirm_symmetric_staff_allowance_corrected(client, app, policy_on):
    """과거 payment-confirm 은 모든 STAFF 를 대칭 허용했다 — 이제 비 CS/SALES STAFF 는 403."""
    _login(client, _make_user(role="STAFF", team="PRODUCTION"))
    oid = _make_order("COMPLETED")

    before = _finance_side_effect_counts(oid)
    resp = client.post(f"/api/orders/{oid}/payment-confirm", json={"type": "balance", "confirmed": True})
    after = _finance_side_effect_counts(oid)

    assert _denied(resp), (resp.status_code, resp.headers.get("X-Auth-Policy"))
    assert not (after[2].get("payment") or {}).get("balance_confirmed")
    assert after[0] == before[0] == 0  # OrderEvent 0

    # 대조군: STAFF/CS 는 동일 요청이 통과(200)해 대칭이 아님을 증명
    _login(client, _make_user(role="STAFF", team="CS"))
    oid2 = _make_order("COMPLETED")
    ok = client.post(f"/api/orders/{oid2}/payment-confirm", json={"type": "balance", "confirmed": True})
    assert ok.status_code == 200 and ok.get_json()["success"] is True


# --------------------------------------------------------------------------
# UI 은닉 — 같은 policy_id(FINANCE_MUTATION)로 finance control 을 실제 템플릿에서 숨긴다
# (backend 가드 대체 아님 — 렌더 결과를 직접 검사해 회귀를 잡는다)
# --------------------------------------------------------------------------
def _render_completion_body(app, user):
    """완료 대시보드 본문을 해당 사용자 세션으로 렌더(policy_can context processor 적용)."""
    from flask import render_template, session as flask_session

    with app.test_request_context("/"):
        flask_session["user_id"] = user.id
        return render_template(
            "cs/partials/completion_dashboard_body.html",
            erp_mobile_v2_enabled=False,
            is_construction_team=False,
            search_q="",
            focus_order_id="",
        )


@pytest.mark.parametrize("role,team", _DENIED_ACTORS)
def test_ui_finance_control_hidden_for_denied(app, client, role, team):
    """VIEWER·비 CS/SALES STAFF 렌더에는 비용 청구 모달·data-can-finance=true 가 없다."""
    html = _render_completion_body(app, _make_user(role=role, team=team))
    assert 'id="erp-settlement-modal"' not in html
    assert 'data-can-finance="true"' not in html


@pytest.mark.parametrize("role,team", _ALLOWED_ACTORS)
def test_ui_finance_control_shown_for_allowed(app, client, role, team):
    """ADMIN/MANAGER·CS/SALES 렌더에는 비용 청구 모달·data-can-finance=true 가 있다."""
    html = _render_completion_body(app, _make_user(role=role, team=team))
    assert 'id="erp-settlement-modal"' in html
    assert 'data-can-finance="true"' in html

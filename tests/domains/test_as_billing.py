"""AS 접수 무상/유상(as_billing) 계약 테스트 — 저장 API + 접수 모달 프론트 구조."""
from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]


def _login_as_admin(client, username="as-billing-admin"):
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="AS Billing Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_as_order(*, status="AS_RECEIVED", shipment_extra=None):
    today = date.today().strftime("%Y-%m-%d")
    shipment = dict(shipment_extra or {})
    order = Order(
        received_date=today,
        customer_name="AS 빌링 고객",
        phone="010-1234-5678",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Alice",
        is_erp_order=True,
        structured_data={"workflow": {"stage": status}, "shipment": shipment},
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_register_defaults_free_unconfirmed(client):
    _login_as_admin(client, username="as-billing-default-admin")
    order = _create_as_order(status="CS")
    res = client.post(f"/api/orders/{order.id}/as/register", json={"as_content": "문틀 뒤틀림"})
    assert res.status_code == 200 and res.get_json()["success"] is True
    db_session.expire_all()
    billing = db_session.get(Order, order.id).structured_data["shipment"]["as_billing"]
    assert billing["type"] == "free"
    assert billing["confirmed"] is False
    assert billing["amount"] is None


def test_register_paid_estimate_with_amount(client):
    _login_as_admin(client, username="as-billing-paid-admin")
    order = _create_as_order(status="CS")
    res = client.post(f"/api/orders/{order.id}/as/register",
                      json={"as_content": "부품 교체", "billing_type": "paid", "amount": 50000})
    assert res.get_json()["success"] is True
    db_session.expire_all()
    billing = db_session.get(Order, order.id).structured_data["shipment"]["as_billing"]
    assert billing["type"] == "paid" and billing["amount"] == 50000 and billing["confirmed"] is False


def test_billing_confirm_paid(client):
    # order_id는 요청 전에 확보한다. 요청 teardown이 세션을 remove 하면
    # commit으로 expire된 인스턴스가 detached 상태가 되어 재로딩이 불가능하다.
    _login_as_admin(client)
    order_id = _create_as_order(status="AS_RECEIVED").id
    res = client.post(f"/api/orders/{order_id}/as/billing",
                      json={"type": "paid", "amount": 30000})
    assert res.status_code == 200 and res.get_json()["success"] is True
    db_session.expire_all()
    b = db_session.get(Order, order_id).structured_data["shipment"]["as_billing"]
    assert b["type"] == "paid" and b["confirmed"] is True and b["amount"] == 30000
    assert b["decided_by"] and b["decided_at"]


def test_billing_transition_requires_reason(client):
    _login_as_admin(client)
    order_id = _create_as_order(
        status="AS_RECEIVED",
        shipment_extra={"as_billing": {"type": "free", "confirmed": True}},
    ).id
    res = client.post(f"/api/orders/{order_id}/as/billing", json={"type": "paid"})
    assert res.status_code == 400
    assert res.get_json()["success"] is False
    db_session.expire_all()
    b = db_session.get(Order, order_id).structured_data["shipment"]["as_billing"]
    assert b["type"] == "free"


def test_billing_transition_with_reason(client):
    """사유가 있으면 전환 성공하고 reason이 저장된다."""
    _login_as_admin(client)
    order_id = _create_as_order(
        status="AS_RECEIVED",
        shipment_extra={"as_billing": {"type": "free", "confirmed": True}},
    ).id
    res = client.post(f"/api/orders/{order_id}/as/billing",
                      json={"type": "paid", "amount": 30000, "reason": "고객 과실"})
    assert res.status_code == 200 and res.get_json()["success"] is True
    db_session.expire_all()
    b = db_session.get(Order, order_id).structured_data["shipment"]["as_billing"]
    assert b["type"] == "paid" and b["amount"] == 30000 and b["reason"] == "고객 과실"


def test_billing_reconfirm_preserves_amount(client):
    """amount 키 미전송은 기존 금액 보존(reason 빈값 보존과 대칭). 명시적 null은 삭제."""
    _login_as_admin(client)
    order_id = _create_as_order(
        status="AS_RECEIVED",
        shipment_extra={"as_billing": {"type": "paid", "confirmed": False, "amount": 50000}},
    ).id

    res = client.post(f"/api/orders/{order_id}/as/billing", json={"type": "paid"})
    assert res.status_code == 200 and res.get_json()["success"] is True
    db_session.expire_all()
    b = db_session.get(Order, order_id).structured_data["shipment"]["as_billing"]
    assert b["amount"] == 50000 and b["confirmed"] is True

    res = client.post(f"/api/orders/{order_id}/as/billing", json={"type": "paid", "amount": None})
    assert res.status_code == 200
    db_session.expire_all()
    b = db_session.get(Order, order_id).structured_data["shipment"]["as_billing"]
    assert b["amount"] is None


def test_billing_rejects_unknown_type(client):
    """미허용 type은 조용한 free 강등이 아니라 400 (오타가 매출 판정을 바꾸면 안 된다)."""
    _login_as_admin(client)
    # 접수 시드(유상 추정·미확정). 전환 사유 가드가 대신 잡아주지 않는 경로라서
    # type 검증이 없으면 오타가 곧바로 "무상 확정"으로 굳는다.
    seeded = {
        "type": "paid",
        "confirmed": False,
        "amount": 70000,
        "reason": "",
        "decided_by": "",
        "decided_at": "",
    }
    order_id = _create_as_order(
        status="AS_RECEIVED", shipment_extra={"as_billing": dict(seeded)}
    ).id
    res = client.post(f"/api/orders/{order_id}/as/billing", json={"type": "bogus"})
    assert res.status_code == 400
    assert res.get_json()["success"] is False
    db_session.expire_all()
    assert db_session.get(Order, order_id).structured_data["shipment"]["as_billing"] == seeded


def test_billing_invalid_amount_is_400(client):
    """검증 실패는 400 (409는 낙관/무결성 전용)."""
    _login_as_admin(client)
    order_id = _create_as_order(status="AS_RECEIVED").id
    res = client.post(f"/api/orders/{order_id}/as/billing",
                      json={"type": "paid", "amount": -1})
    assert res.status_code == 400
    assert res.get_json()["success"] is False


def test_register_preserves_existing_confirmed_billing(client):
    """재접수(지방 재상차 등)가 확정된 billing을 되돌리지 않는다. 확정/전환은 전용 API로만."""
    _login_as_admin(client, username="as-billing-preserve-admin")
    confirmed = {
        "type": "paid",
        "confirmed": True,
        "amount": 80000,
        "reason": "부품 파손 고객 과실",
        "decided_by": "CS 관리자",
        "decided_at": "2026-07-20T01:02:03",
    }
    order = _create_as_order(status="AS_RECEIVED", shipment_extra={"as_billing": dict(confirmed)})

    res = client.post(f"/api/orders/{order.id}/as/register",
                      json={"as_content": "재접수", "billing_type": "free", "amount": 0})

    assert res.status_code == 200 and res.get_json()["success"] is True
    db_session.expire_all()
    billing = db_session.get(Order, order.id).structured_data["shipment"]["as_billing"]
    assert billing == confirmed


# ---------------------------------------------------------------------------
# 접수 모달 프론트 구조 계약 (T3)
# ---------------------------------------------------------------------------

def _order_tab_html() -> str:
    return (ROOT / "templates/orders/partials/erp_order_tab.html").read_text(encoding="utf-8")


def _shared_js() -> str:
    return (ROOT / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")


def test_as_receive_modal_has_billing_segment():
    """접수 모달에 무상/유상/미정 3값 세그먼트가 있고 기본값은 무상 추정이다."""
    tpl = _order_tab_html()
    for value in ("free", "paid", "undecided"):
        assert f'name="as-receive-billing" id="as-billing-{value}" value="{value}"' in tpl
    # 기본 선택은 무상(추정) — 서버 기본값(_default_as_billing)과 일치해야 한다.
    assert 'id="as-billing-free" value="free" checked' in tpl
    assert 'id="as-billing-paid" value="paid">' in tpl
    assert 'id="as-billing-undecided" value="undecided">' in tpl


def test_as_receive_modal_amount_is_progressive_disclosure():
    """금액 입력은 기본 숨김(d-none) — 유상 선택 시에만 JS가 노출한다."""
    tpl = _order_tab_html()
    wrap_idx = tpl.index('id="as-receive-amount-wrap"')
    wrap_tag = tpl[tpl.rindex("<div", 0, wrap_idx):tpl.index(">", wrap_idx) + 1]
    assert "d-none" in wrap_tag
    assert 'id="as-receive-amount"' in tpl
    assert 'type="number"' in tpl[wrap_idx:wrap_idx + 400]


def test_as_receive_modal_since_badge_defaults_hidden():
    """경과 개월 배지는 시공일이 없으면 숨김이어야 하므로 마크업 기본값이 d-none."""
    tpl = _order_tab_html()
    idx = tpl.index('id="as-receive-since-badge"')
    badge_tag = tpl[tpl.rindex("<span", 0, idx):tpl.index(">", idx) + 1]
    assert "d-none" in badge_tag


def test_as_receive_billing_block_sits_between_content_and_shipping():
    """세그먼트는 AS 내용 뒤·상차일 앞. 순서가 깨지면 판정 전 금액을 먼저 묻게 된다."""
    tpl = _order_tab_html()
    assert (
        tpl.index('id="as-receive-content"')
        < tpl.index('id="as-receive-since-badge"')
        < tpl.index('id="as-receive-amount-wrap"')
        < tpl.index('id="as-receive-shipping-wrap"')
    )


def test_as_receive_billing_block_has_no_inline_style():
    """인라인 스타일 금지(프로젝트 규약) — 세그먼트 블록 구간에 style= 없음."""
    tpl = _order_tab_html()
    block = tpl[tpl.index('id="as-receive-since-badge"'):tpl.index('id="as-receive-shipping-wrap"')]
    assert "style=" not in block


def test_shared_js_sends_billing_type_and_conditional_amount():
    """regPayload는 billing_type을 항상, amount는 유상일 때만 싣는다."""
    js = _shared_js()
    reg_idx = js.index("const regPayload = { as_content: content };")
    block = js[reg_idx:reg_idx + 1200]
    assert "regPayload.billing_type = billingType;" in block
    assert "if (billingType === 'paid')" in block
    amount_idx = block.index("regPayload.amount")
    # amount 대입은 paid 분기 안에서만 일어나야 한다.
    assert block.index("if (billingType === 'paid')") < amount_idx


def test_shared_js_wires_segment_toggle_and_since_badge_on_modal_show():
    """모달이 열릴 때마다 세그먼트 상태·경과 배지를 재평가한다(오픈마다 재평가)."""
    js = _shared_js()
    assert "function selectedBillingType()" in js
    assert "function syncBillingUi()" in js
    assert "function refreshSinceBadge()" in js
    shown_idx = js.index("'shown.bs.modal'")
    handler = js[shown_idx:shown_idx + 300]
    assert "syncBillingUi()" in handler
    assert "refreshSinceBadge()" in handler


def test_since_badge_parses_multi_date_construction_field():
    """시공일 필드는 여러 날짜가 들어가는 text input이라 정규식으로 최신 날짜를 뽑아야 한다."""
    js = _shared_js()
    idx = js.index("function refreshSinceBadge()")
    block = js[idx:idx + 1200]
    assert "erp-construction-date" in block
    # new Date(raw) 직접 파싱은 "2026-03-13, 2026-03-14" 입력에서 NaN/오판이 난다.
    assert "match(" in block
    assert ".sort()" in block and ".pop()" in block


def test_existing_billing_locks_segment_on_reregister():
    """재접수는 서버가 billing 페이로드를 무시하므로(as_orders.py) 세그먼트를 잠근다.

    잠그지 않으면 사용자가 고른 값이 저장되지 않는데 UI만 바뀌어 "반영된 것처럼" 보인다.
    """
    js = _shared_js()
    idx = js.index("function applyExistingBillingLock()")
    block = js[idx:idx + 1400]
    assert "__erpLastStructuredData" in block and "as_billing" in block
    assert "disabled = true" in block
    assert "disabled = false" in block  # 최초 접수로 되돌아오면 잠금 해제
    tpl = _order_tab_html()
    assert 'id="as-receive-billing-locked-note"' in tpl
    assert "AS 대시보드" in tpl[tpl.index('id="as-receive-billing-locked-note"'):][:400]
    # 잠금 안내는 기본 숨김
    note_idx = tpl.index('id="as-receive-billing-locked-note"')
    assert "d-none" in tpl[tpl.rindex("<div", 0, note_idx):tpl.index(">", note_idx) + 1]

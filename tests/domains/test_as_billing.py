"""AS 접수 무상/유상(as_billing) 계약 테스트 — 저장 API + 접수 모달 프론트 구조 + 대시보드 표면."""
import re
from datetime import date
from pathlib import Path

import pytest
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


def _create_as_order(*, status="AS_RECEIVED", shipment_extra=None, customer_name="AS 빌링 고객"):
    today = date.today().strftime("%Y-%m-%d")
    shipment = dict(shipment_extra or {})
    order = Order(
        received_date=today,
        customer_name=customer_name,
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
# AS 대시보드 billing 필터·배지·KPI (T4)
# ---------------------------------------------------------------------------


def test_billing_filter_paid_only(client):
    _login_as_admin(client)
    _create_as_order(customer_name="유상건", shipment_extra={"as_billing": {"type": "paid", "confirmed": True}})
    _create_as_order(customer_name="무상건", shipment_extra={"as_billing": {"type": "free", "confirmed": True}})
    body = client.get("/erp/as?tab=incomplete&billing=paid").get_data(as_text=True)
    assert "유상건" in body and "무상건" not in body


def test_billing_badge_free_confirmed_hidden(client):
    _login_as_admin(client)
    _create_as_order(customer_name="무상확정", shipment_extra={"as_billing": {"type": "free", "confirmed": True}})
    body = client.get("/erp/as?tab=incomplete").get_data(as_text=True)
    assert "erp-as-billing-badge" not in body  # 무상 확정 무배지


def test_paid_unconfirmed_kpi_counts_only_unconfirmed(client):
    """'유상 미확정' KPI는 확정된 유상 건을 세지 않는다.

    JSON boolean은 dialect마다 표현이 달라(postgres 'true' / sqlite 1) 문자열
    등호 비교로 판정하면 확정 건이 미확정으로 새어 들어온다.
    """
    _login_as_admin(client)
    _create_as_order(customer_name="유상확정", shipment_extra={"as_billing": {"type": "paid", "confirmed": True}})
    _create_as_order(customer_name="유상미확정", shipment_extra={"as_billing": {"type": "paid", "confirmed": False}})
    _create_as_order(customer_name="무상건")
    body = client.get("/erp/as?tab=incomplete").get_data(as_text=True)
    assert re.search(r'data-as-incomplete-summary="paid_unconfirmed"[^>]*data-count="1"', body)


# AS 표면의 필터 지속 계약: status/q/sort_dir/mine을 나르는 링크는 billing도 날라야 한다.
# 하나라도 빠지면 탭 전환·정렬·페이지 이동 순간 비용 필터가 조용히 풀린다.
_AS_LINK_TEMPLATES = (
    "templates/cs/partials/as_dashboard_body.html",
    "templates/cs/partials/as_mobile_controls.html",
    "templates/cs/partials/tablet_as_compare_body.html",
)


@pytest.mark.parametrize("rel_path", _AS_LINK_TEMPLATES)
def test_status_preserving_links_also_preserve_billing(rel_path):
    """status를 보존하는 모든 AS 링크는 billing도 보존한다(초기화 링크는 status 미보존 → 면제)."""
    lines = [
        line
        for line in (ROOT / rel_path).read_text(encoding="utf-8").splitlines()
        if "erp_as_page.erp_as_dashboard" in line and "status=status_filter" in line
    ]
    assert lines, rel_path
    missing = [line.strip() for line in lines if "billing=billing_filter" not in line]
    assert not missing, missing


def test_route_redirects_also_preserve_billing():
    """라우트 리다이렉트(탭 자동 이동·검색 단건 이동)도 status와 함께 billing을 보존한다.

    템플릿 링크와 같은 규칙: status를 넘기면 billing도 넘긴다. 영업/택배 검색 리셋
    리다이렉트는 `status=''`로 필터를 비우는 동선이라 자동 면제된다.
    """
    src = (ROOT / "foms/web/cs/as_dashboard.py").read_text(encoding="utf-8")
    calls = [chunk.split("))")[0] for chunk in src.split("url_for(")[1:]]
    status_calls = [
        c for c in calls
        if "erp_as_page.erp_as_dashboard" in c and "status=" in c and "status=''" not in c
    ]
    assert status_calls
    missing = [c for c in status_calls if "billing=" not in c]
    assert not missing, missing


def test_billing_survives_mobile_pager_and_js_navigation():
    """모바일 페이저 쿼리 프리픽스와 JS 재이동(URL 화이트리스트)에도 billing이 남아야 한다."""
    body = (ROOT / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")
    assert "_as_ctx.append('billing=' ~ billing_filter|urlencode)" in body
    assert "'status', 'billing'" in js


def test_billing_filter_persists_in_rendered_links(client):
    """실제 렌더된 /erp/as 링크(탭·정렬·KPI pill) 전부가 billing=paid를 나른다."""
    _login_as_admin(client)
    _create_as_order(customer_name="유상건", shipment_extra={"as_billing": {"type": "paid"}})
    body = client.get("/erp/as?tab=incomplete&billing=paid").get_data(as_text=True)
    hrefs = re.findall(r'href="([^"]*/erp/as\?[^"]*)"', body)
    assert hrefs
    assert all("billing=paid" in href for href in hrefs), [h for h in hrefs if "billing=paid" not in h]


def test_billing_filter_selects_are_present_on_both_cohorts(client):
    """데스크톱 필터 form과 모바일 offcanvas 양쪽에 같은 name/option의 billing select가 있어야 한다."""
    desktop = (ROOT / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
    mobile = (ROOT / "templates/cs/partials/as_mobile_controls.html").read_text(encoding="utf-8")
    for src in (desktop, mobile):
        assert 'name="billing"' in src
        for value in ("free", "paid", "undecided"):
            assert f'value="{value}"' in src


# ---------------------------------------------------------------------------
# 접수 모달 프론트 구조 계약 (T3)
# ---------------------------------------------------------------------------

# AS 접수 모달은 PC/모바일 두 템플릿에 각각 존재하고 같은 erp-order-shared.js가 구동한다.
# 한쪽만 고치면 그 코호트에서 유상 접수가 불가능해져 매출 추적에 구멍이 난다.
_AS_MODAL_TEMPLATES = (
    "templates/orders/partials/erp_order_tab.html",
    "templates/orders/partials/erp_order_tab_mobile.html",
)


@pytest.fixture(params=_AS_MODAL_TEMPLATES)
def as_modal_tpl(request) -> str:
    """AS 접수 모달을 품은 템플릿 원문(PC·모바일 양쪽에 같은 계약을 강제)."""
    return (ROOT / request.param).read_text(encoding="utf-8")


def _shared_js() -> str:
    return (ROOT / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")


def test_as_receive_modal_has_billing_segment(as_modal_tpl):
    """접수 모달에 무상/유상/미정 3값 세그먼트가 있고 기본값은 무상 추정이다."""
    for value in ("free", "paid", "undecided"):
        assert f'name="as-receive-billing" id="as-billing-{value}" value="{value}"' in as_modal_tpl
    # 기본 선택은 무상(추정) — 서버 기본값(_default_as_billing)과 일치해야 한다.
    assert 'id="as-billing-free" value="free" checked' in as_modal_tpl
    assert 'id="as-billing-paid" value="paid">' in as_modal_tpl
    assert 'id="as-billing-undecided" value="undecided">' in as_modal_tpl


def test_as_receive_modal_amount_is_progressive_disclosure(as_modal_tpl):
    """금액 입력은 기본 숨김(d-none) — 유상 선택 시에만 JS가 노출한다."""
    wrap_idx = as_modal_tpl.index('id="as-receive-amount-wrap"')
    wrap_tag = as_modal_tpl[as_modal_tpl.rindex("<div", 0, wrap_idx):as_modal_tpl.index(">", wrap_idx) + 1]
    assert "d-none" in wrap_tag
    assert 'id="as-receive-amount"' in as_modal_tpl
    assert 'type="number"' in as_modal_tpl[wrap_idx:wrap_idx + 400]


def test_as_receive_modal_since_badge_defaults_hidden(as_modal_tpl):
    """경과 개월 배지는 시공일이 없으면 숨김이어야 하므로 마크업 기본값이 d-none."""
    idx = as_modal_tpl.index('id="as-receive-since-badge"')
    badge_tag = as_modal_tpl[as_modal_tpl.rindex("<span", 0, idx):as_modal_tpl.index(">", idx) + 1]
    assert "d-none" in badge_tag


def test_as_receive_billing_block_sits_between_content_and_shipping(as_modal_tpl):
    """세그먼트는 AS 내용 뒤·상차일 앞. 순서가 깨지면 판정 전 금액을 먼저 묻게 된다."""
    assert (
        as_modal_tpl.index('id="as-receive-content"')
        < as_modal_tpl.index('id="as-receive-since-badge"')
        < as_modal_tpl.index('id="as-receive-amount-wrap"')
        < as_modal_tpl.index('id="as-receive-shipping-wrap"')
    )


def test_as_receive_billing_block_has_no_inline_style(as_modal_tpl):
    """인라인 스타일 금지(프로젝트 규약) — 세그먼트 블록 구간에 style= 없음."""
    block = as_modal_tpl[
        as_modal_tpl.index('id="as-receive-since-badge"'):as_modal_tpl.index('id="as-receive-shipping-wrap"')
    ]
    assert "style=" not in block


def test_as_receive_billing_lock_note_present(as_modal_tpl):
    """재접수 잠금 안내는 양쪽 템플릿에 있고 기본 숨김이다."""
    note_idx = as_modal_tpl.index('id="as-receive-billing-locked-note"')
    assert "AS 대시보드" in as_modal_tpl[note_idx:note_idx + 400]
    note_tag = as_modal_tpl[as_modal_tpl.rindex("<div", 0, note_idx):as_modal_tpl.index(">", note_idx) + 1]
    assert "d-none" in note_tag


def test_as_modal_cohort_variants_are_mutually_exclusive_at_runtime():
    """PC/모바일 모달은 같은 id를 쓰므로 JS 실행 시점에 반드시 하나만 남아야 한다.

    edit_order_body.html은 두 파티얼을 모두 렌더한 뒤 **동기** 인라인 스크립트로
    한쪽을 remove 한다. erp-order-shared.js는 defer라 항상 그 뒤에 실행되므로
    getElementById/querySelector 단수 선택이 안전하다. 이 순서가 깨지면
    (인라인이 defer/async가 되거나 remove가 사라지면) 모바일에서 PC 모달을
    집어 배선이 엉킨다.
    """
    body = (ROOT / "templates/orders/partials/edit_order_body.html").read_text(encoding="utf-8")
    legacy_idx = body.index('id="erp-order-form-legacy"')
    mobile_idx = body.index('id="erp-order-form-mobile"')
    remove_idx = body.index("(useMobile ? legacy : mobile).remove();")
    assert legacy_idx < mobile_idx < remove_idx
    script_open = body.rindex("<script", 0, remove_idx)
    script_tag = body[script_open:body.index(">", script_open) + 1]
    assert "defer" not in script_tag and "async" not in script_tag


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
    assert "as-receive-billing-locked-note" in js

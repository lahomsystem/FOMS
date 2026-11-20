"""새 주문 안내 한 줄 — 화면 배선 계약 (설계서 2026-11-20 6.2 · M15 · M17).

완료 기준: PC 주문 폼 띠 자리 · 스크립트가 실림 · 복사로 만든 접수 단계 주문의 편집 화면만 도착 안내 표식을 가짐 ·
휴대폰 마법사 4단계 맨 위 자리 · 새 CSS 클래스 하나 · 새 JS 는 jQuery · innerHTML · 인라인 스타일 없이 fetch 를
try/catch + success 확인으로 부르고 새 창 링크로 연다 · 저장을 막는 창(confirm · alert)이 없다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User
from tests.domains.test_erp_order_draft_wizard import _login as _wizard_login
from tests.domains.test_erp_order_draft_wizard import wizard_enabled  # noqa: F401 — fixture

ROOT = Path(__file__).resolve().parents[2]
PC_JS = ROOT / "static/js/orders/erp-same-customer-notice.js"
WIZARD_JS = ROOT / "static/js/foms/wizard-same-customer.js"
ERP_TAB = ROOT / "templates/orders/partials/erp_order_tab.html"
ERP_JS_PARTIAL = ROOT / "templates/orders/partials/erp_order_js.html"
STEP4 = ROOT / "templates/orders/wizard/step4_confirm.html"
SHELL = ROOT / "templates/orders/wizard/wizard_shell.html"
WIZARD_CSS = ROOT / "static/css/components/foms-wizard.css"
PIN = "20261121c"
PC_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130"}
LOOKUP_URL = 'data-lookup-url="/api/orders/open-for-customer"'
ADDRESS = "합성시 시험대로10길 20 2505동 1103호"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _slot(html: str, element_id: str) -> str:
    """그 id 를 가진 여는 태그 한 개(속성까지)."""
    match = re.search(r'<div[^>]*\bid="%s"[^>]*>' % re.escape(element_id), html, flags=re.S)
    assert match, f"#{element_id} 자리가 없다"
    return match.group(0)


@pytest.fixture
def staff_client(client):
    user = User(username="c7_wiring_staff", password=generate_password_hash("pw"), role="STAFF", team="SALES",
                name="배선 직원", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return client


def _order(*, created_via: str, stage: str = "RECEIVED") -> int:
    order = Order(
        received_date="2026-11-20", customer_name="합성고객", phone="010-5551-2468", address=ADDRESS,
        product="합성 붙박이장", status=stage, is_erp_order=True, erp_stage_code=stage,
        erp_phone_digits="01055512468",
        structured_data={
            "workflow": {"stage": stage},
            "parties": {"customer": {"name": "합성고객", "phone": "010-5551-2468"}},
            "site": {"address_full": ADDRESS},
            "items": [{"product_name": "합성 붙박이장"}],
            "meta": {"draft": False, "created_via": created_via, "copied_from_order_id": 1},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order.id


# --------------------------------------------------------------------------- #
# PC 주문 폼
# --------------------------------------------------------------------------- #
def test_pc_slot_sits_under_the_restore_banner_without_inline_style():
    source = _read(ERP_TAB)
    slot = _slot(source, "erp-same-customer-notice")

    assert source.index('id="erp-restore-banner"') < source.index('id="erp-same-customer-notice"')
    assert source.index('id="erp-same-customer-notice"') < source.index('id="erp-customer-name"')
    assert "alert alert-warning" in slot and "d-none" in slot
    assert "data-foms-no-autodismiss" in slot, "없으면 공용 스크립트가 5초 뒤 닫는다"
    assert 'role="status"' in slot
    assert "style=" not in slot
    assert source.count('id="erp-same-customer-notice"') == 1


def test_pc_script_is_loaded_after_the_shared_form_script():
    partial = _read(ERP_JS_PARTIAL)
    tag = "<script src=\"{{ asset_url('js/orders/erp-same-customer-notice.js') }}\" defer></script>"

    assert partial.count(tag) == 1
    assert partial.index("js/orders/erp-order-shared.js") < partial.index(tag)


def test_new_order_page_renders_slot_without_copy_markers(staff_client):
    page = staff_client.get("/add?open=erp-order", headers=PC_UA)
    html = page.get_data(as_text=True)

    assert page.status_code == 200
    slot = _slot(html, "erp-same-customer-notice")
    assert LOOKUP_URL in slot
    assert "data-copy-arrival" not in slot and "data-order-id" not in slot
    assert "erp-same-customer-notice.js" in html


def test_copied_order_edit_page_asks_once_on_arrival(staff_client):
    copied = _order(created_via="ORDER_COPY")

    html = staff_client.get(f"/edit/{copied}?open=erp-order", headers=PC_UA).get_data(as_text=True)

    slot = _slot(html, "erp-same-customer-notice")
    assert LOOKUP_URL in slot
    assert f'data-order-id="{copied}"' in slot, "자기 자신을 빼는 번호"
    assert 'data-copy-arrival="true"' in slot
    assert 'data-copy-phone="010-5551-2468"' in slot
    assert f'data-copy-address="{ADDRESS}"' in slot


def test_ordinary_or_progressed_orders_do_not_ask_on_arrival(staff_client):
    ordinary = _order(created_via="ERP_ORDER")
    progressed_copy = _order(created_via="ORDER_COPY", stage="PRODUCTION")

    for order_id in (ordinary, progressed_copy):
        html = staff_client.get(f"/edit/{order_id}?open=erp-order", headers=PC_UA).get_data(as_text=True)
        slot = _slot(html, "erp-same-customer-notice")
        assert f'data-order-id="{order_id}"' in slot
        assert "data-copy-arrival" not in slot, order_id


# --------------------------------------------------------------------------- #
# 휴대폰 마법사 4단계
# --------------------------------------------------------------------------- #
def test_wizard_slot_is_the_first_thing_under_the_step4_subtitle():
    step4 = _read(STEP4)
    slot = _slot(step4, "foms-wizard-same-customer")

    assert step4.index("foms-wizard__subtitle") < step4.index('id="foms-wizard-same-customer"')
    assert step4.index('id="foms-wizard-same-customer"') < step4.index('id="foms-wizard-summary-basic"')
    assert 'class="foms-wizard__same-customer"' in slot
    assert " hidden" in slot and 'role="status"' in slot
    assert "style=" not in slot


def test_wizard_shell_pins_css_and_loads_the_script():
    shell = _read(SHELL)
    tag = (
        "<script src=\"{{ url_for('static', filename='js/foms/wizard-same-customer.js') }}?v="
        + PIN
        + '" defer></script>'
    )

    assert "css/components/foms-wizard.css') }}?v=" + PIN in shell, "CSS 를 고쳤으면 핀을 올린다"
    assert shell.count(tag) == 1
    assert shell.index("js/foms/wizard.js") < shell.index(tag)


def test_wizard_css_adds_one_class_that_respects_the_hidden_attribute():
    css = _read(WIZARD_CSS)
    block = re.search(r"\.foms-wizard__same-customer \{([^}]*)\}", css)

    assert block, "새 클래스가 없다"
    assert "display" not in block.group(1), "display 를 주면 hidden 속성이 안 먹는다"
    new_classes = set(re.findall(r"\.(foms-wizard__same-customer[\w-]*)", css))
    assert new_classes == {"foms-wizard__same-customer"}, "클래스는 하나만 더한다"


def test_wizard_page_renders_the_slot(client, app, wizard_enabled):  # noqa: F811
    _wizard_login(client, app, "c7_wizard_page_user")

    html = client.get("/add?wizard=1").get_data(as_text=True)

    slot = _slot(html, "foms-wizard-same-customer")
    assert LOOKUP_URL in slot
    assert "js/foms/wizard-same-customer.js?v=" + PIN in html


# --------------------------------------------------------------------------- #
# 새 JS 두 개의 규약
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", [PC_JS, WIZARD_JS], ids=["pc", "wizard"])
def test_notice_scripts_follow_frontend_rules(path):
    js = _read(path)
    flat = js.replace('"', "'")

    assert len(js.splitlines()) < 300
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js, "저장된 주소 · 이름을 HTML 로 넣지 않는다"
    assert "$(" not in js and "jQuery" not in js
    assert ".style." not in js and "cssText" not in js
    assert "confirm(" not in js and "alert(" not in js, "알리기만 한다 — 저장을 막는 창이 없다"
    assert "try {" in js and "catch (error)" in js
    assert "!data.success" in js
    assert "response.status === 403" in js, "프리랜서 · 협력사는 조용히 넘어간다"
    assert "이 고객의 진행 중인 주문이 있습니다" in js and "그 주문 열기" in js
    assert "'외 ' + more + '건'" in flat
    assert "link.target = '_blank'" in flat and "link.rel = 'noopener'" in flat
    assert "'주문 #'" in flat and "' 단계'" in flat and "'시공 '" in flat


def test_pc_script_only_asks_for_new_orders_and_excludes_itself():
    js = _read(PC_JS)

    assert "erpIsDraftBackedOrder" in js and "if (!isNewOrder()) return;" in js
    assert "exclude_order_id" in js
    assert "addEventListener('blur', checkForm)" in js
    assert "'erp-customer-phone'" in js and "'erp-address'" in js
    assert "data-copy-arrival" in js


def test_wizard_script_watches_the_step_attribute_instead_of_patching_wizard_js():
    js = _read(WIZARD_JS)

    assert "MutationObserver" in js and '"data-current-step"' in js
    assert '"wiz-phone"' in js and '"wiz-address"' in js
    assert "order.mobile_url || order.url" in js
    assert 'root.setAttribute("data-current-step", String(step));' in _read(ROOT / "static/js/foms/wizard.js")

"""주문 편집 outer 탭 pane 가시성 계약 (TAB-PANE-NEST-01).

부트스트랩은 ``.tab-content > .tab-pane { display:none }`` 하나로 비활성 pane 을 접는다.
ERP pane 은 모바일 코호트 래퍼(``#erp-order-form-legacy`` / ``#erp-order-form-mobile``)
안에 있어 이 **직계 자식** 선택자에 걸리지 않았고, 비활성일 때 ``.fade``(opacity:0)만
남아 자리를 통째로 차지했다 — 계산기·견적서·변경 이력 탭 내용이 화면 맨 아래로 밀렸다
(운영 실측: pane top 3757px, 문서 높이 3794px).

구조(래퍼)와 보정 CSS 는 한 쌍이라 함께 고정한다: 래퍼가 남아 있는 한 자손 선택자 규칙도
남아야 한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]
CSS = ROOT / "static/css/orders/erp-edit-embedded.css"
EDIT_TEMPLATE = ROOT / "templates/orders/edit_order.html"


def _login_cohort_admin(client, monkeypatch: pytest.MonkeyPatch) -> User:
    """모바일 v2 코호트에 든 ADMIN 으로 로그인한다(코호트에서만 래퍼가 렌더된다)."""
    user = User(
        username="tab_pane_nest_admin",
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="CS",
        name="탭 pane 관리자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _create_erp_order() -> Order:
    order = Order(
        received_date="2026-08-14",
        customer_name="탭 pane 고객",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}, "items": [{"product_name": "붙박이장"}]},
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_erp_pane_is_wrapped_so_css_must_use_descendant_rule(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """코호트 래퍼가 남아 있는 한, 비활성 pane 은 자손 선택자 규칙으로 접어야 한다."""
    _login_cohort_admin(client, monkeypatch)
    order_id = _create_erp_order().id

    body = client.get(f"/edit/{order_id}").get_data(as_text=True)

    # 래퍼가 pane 을 감싼다 = 부트스트랩 직계 자식 규칙이 끊긴다.
    assert 'id="erp-order-form-legacy"' in body
    wrapper_at = body.index('id="erp-order-form-legacy"')
    pane_at = body.index('id="erp-order"', wrapper_at)
    assert wrapper_at < pane_at

    css = CSS.read_text(encoding="utf-8")
    assert "#orderTabContent .tab-pane:not(.active)" in css


def test_embedded_estimate_rule_survives_the_wrapper(client) -> None:
    """임베드(?embedded=1) 화면도 같은 이유로 자손 선택자여야 한다.

    직계 자식 규칙만 두면 래퍼 안의 ERP 카드가 견적서 아래로 삐져나온다(실측 89px).
    """
    css = CSS.read_text(encoding="utf-8")

    assert "body.foms-edit-embedded #orderTabContent .tab-pane" in css
    assert "body.foms-edit-embedded .tab-content > .tab-pane" not in css
    # 견적서 pane 만 다시 펴는 예외는 그대로 남아야 한다(더 높은 특이도).
    assert "body.foms-edit-embedded .tab-content > #erp-estimate.tab-pane" in css


def test_edit_page_pins_the_bumped_stylesheet(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """SW staticCacheFirst 때문에 CSS 변경은 ?v 범프가 동반돼야 화면에 도달한다."""
    _login_cohort_admin(client, monkeypatch)
    order_id = _create_erp_order().id

    body = client.get(f"/edit/{order_id}").get_data(as_text=True)
    template = EDIT_TEMPLATE.read_text(encoding="utf-8")

    assert "erp-edit-embedded.css') }}?v=20260821a" in template
    assert "erp-edit-embedded.css?v=20260821a" in body

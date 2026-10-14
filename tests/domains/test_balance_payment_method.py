"""잔금 결제수단 꼬리표 — 서버 규칙과 PC·태블릿 JS 미러 계약."""

from pathlib import Path

import pytest

from foms.services.channel_measure_message import build_measure_push_text
from foms.services.orders.balance_payment_method import (
    balance_confirmed_suffix,
    normalize_balance_method,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "payment, expected",
    [
        ({"balance_confirmed": False, "balance_method": "카드"}, ""),
        ({"balance_confirmed": True}, "(결제 완)"),
        ({"balance_confirmed": True, "balance_method": "네이버"}, "(결제 완-네이버)"),
        ({"balance_confirmed": True, "balance_method": "카드"}, "(결제 완-카드)"),
        ({"balance_confirmed": True, "balance_method": "계좌입금"}, "(결제 완-계좌입금)"),
        (
            {"balance_confirmed": True, "balance_method": "custom", "balance_method_text": "현금"},
            "(결제 완-현금)",
        ),
        ({"balance_confirmed": True, "balance_method": "custom", "balance_method_text": " "}, "(결제 완)"),
        ({"balance_confirmed": "true", "balance_method": "모름"}, "(결제 완)"),
        (None, ""),
    ],
)
def test_balance_confirmed_suffix(payment, expected):
    assert balance_confirmed_suffix(payment) == expected


def test_normalize_trims_custom_text_to_20_chars():
    method, text = normalize_balance_method("custom", "가" * 30)
    assert method == "custom"
    assert text == "가" * 20


def test_push_text_uses_balance_method_suffix():
    from tests.domains.test_channel_measure_message import _SINGLE_SD, _sd

    sd = _sd(_SINGLE_SD, payment={"deposit": 200000, "balance_confirmed": True, "balance_method": "계좌입금"})
    text = build_measure_push_text(sd)
    assert "원(결제 완-계좌입금)" in text
    assert "(결제 완)" not in text


def test_js_mirrors_share_presets_and_format():
    shared = (ROOT / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    tablet = (ROOT / "static/js/foms/tablet-measure-form.js").read_text(encoding="utf-8")
    assert "const ERP_BALANCE_METHOD_PRESETS = ['네이버', '카드', '계좌입금'];" in shared
    assert "(결제 완-${label})" in shared
    assert 'var BALANCE_METHOD_PRESETS = ["네이버", "카드", "계좌입금"];' in tablet
    assert '"(결제 완-" + label + ")"' in tablet
    assert "erpBalanceConfirmedSuffix(state.paymentBase)" in tablet


def test_payment_normalizers_keep_balance_method_fields():
    """자동 저장·최종 저장이 결제수단을 지우지 않도록 3곳 정규화에 두 필드가 있어야 한다."""
    for rel in (
        "static/js/orders/erp-order-shared.js",
        "static/js/orders/erp-order-autosave.js",
        "static/js/foms/tablet-measure-form.js",
    ):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "balance_method:" in src, rel
        assert "balance_method_text:" in src, rel


def test_templates_render_balance_method_controls():
    pc = (ROOT / "templates/orders/partials/erp_order_tab.html").read_text(encoding="utf-8")
    mobile = (ROOT / "templates/orders/partials/erp_order_tab_mobile.html").read_text(encoding="utf-8")
    assert 'id="erp-balance-method"' in pc
    assert 'id="erp-balance-method-section"' in pc and 'id="erp-balance-method-section"' in mobile
    for label in ("네이버", "카드", "계좌입금"):
        assert f'data-balance-method="{label}"' in mobile
    assert 'data-balance-method="custom"' in mobile

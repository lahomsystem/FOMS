"""잔금 결제수단(네이버·카드·계좌입금·직접입력) 정규화와 PUSH 꼬리표.

``structured_data.payment`` 에 ``balance_method`` 와 ``balance_method_text`` 로 저장한다.
JS 미러: ``static/js/orders/erp-order-shared.js`` 의 ``erpBalanceConfirmedSuffix`` 와
``static/js/foms/tablet-measure-form.js`` 의 같은 이름 함수.
"""

from __future__ import annotations

from typing import Any, Mapping

__all__ = [
    "BALANCE_METHOD_CUSTOM",
    "BALANCE_METHOD_PRESETS",
    "BALANCE_METHOD_TEXT_MAX_LEN",
    "balance_confirmed_suffix",
    "balance_method_label",
    "normalize_balance_method",
]

BALANCE_METHOD_PRESETS = ("네이버", "카드", "계좌입금")
BALANCE_METHOD_CUSTOM = "custom"
BALANCE_METHOD_TEXT_MAX_LEN = 20

_TRUTHY_STRINGS = frozenset({"true", "1", "yes", "on"})


def _confirmed(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY_STRINGS
    return bool(value)


def normalize_balance_method(method: Any, text: Any) -> tuple[str | None, str | None]:
    """입력값을 저장 가능한 ``(balance_method, balance_method_text)`` 쌍으로 바꾼다.

    알 수 없는 수단이나 빈 직접입력은 ``(None, None)`` — 수단 미선택으로 본다.
    """
    method_str = str(method or "").strip()
    if method_str in BALANCE_METHOD_PRESETS:
        return method_str, None
    if method_str == BALANCE_METHOD_CUSTOM:
        custom = str(text or "").strip()[:BALANCE_METHOD_TEXT_MAX_LEN]
        if custom:
            return BALANCE_METHOD_CUSTOM, custom
    return None, None


def balance_method_label(payment: Mapping[str, Any] | None) -> str:
    """저장된 결제수단의 표시 글자(미선택이면 빈 문자열)."""
    if not isinstance(payment, Mapping):
        return ""
    method, text = normalize_balance_method(
        payment.get("balance_method"), payment.get("balance_method_text")
    )
    if method == BALANCE_METHOD_CUSTOM:
        return text or ""
    return method or ""


def balance_confirmed_suffix(payment: Mapping[str, Any] | None) -> str:
    """잔금 줄 꼬리표: 미확인 ``""``, 수단 없음 ``(결제 완)``, 수단 있음 ``(결제 완-카드)``."""
    if not isinstance(payment, Mapping) or not _confirmed(payment.get("balance_confirmed")):
        return ""
    label = balance_method_label(payment)
    return f"(결제 완-{label})" if label else "(결제 완)"

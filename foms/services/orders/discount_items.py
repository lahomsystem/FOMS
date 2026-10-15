"""주문 할인 항목(``payment.discounts``) 정규화.

할인은 "이름 + 금액" 줄 여러 개로 받는다. 잔금·견적·정산·결제 동기화는 모두
``payment.discount``(합계 숫자)만 읽으므로, 목록이 오면 서버가 합계를 다시 계산해
``payment.discount`` 에 써 둔다(클라이언트 합계는 믿지 않는다).

목록이 없는 옛 주문은 건드리지 않는다 — ``payment.discount`` 숫자가 그대로 정본이다.
"""

from __future__ import annotations

from typing import Any

MAX_DISCOUNT_ITEMS = 20
MAX_DISCOUNT_LABEL_LEN = 64
DEFAULT_DISCOUNT_LABEL = "할인"


def _coerce_amount(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return int(digits) if digits else 0


def clean_discount_items(raw: Any) -> list[dict[str, Any]]:
    """할인 줄 목록을 정리한다. 금액 0 이하 줄은 버리고 최대 20줄만 남긴다.

    Args:
        raw: 클라이언트가 보낸 ``payment.discounts`` 값.

    Returns:
        ``[{"label": str, "amount": int}, ...]`` — 이름이 비면 "할인".
    """
    if not isinstance(raw, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        amount = _coerce_amount(row.get("amount"))
        if amount <= 0:
            continue
        label = str(row.get("label") or "").strip()[:MAX_DISCOUNT_LABEL_LEN]
        cleaned.append({"label": label or DEFAULT_DISCOUNT_LABEL, "amount": amount})
        if len(cleaned) >= MAX_DISCOUNT_ITEMS:
            break
    return cleaned


def normalize_payment_discounts(structured_data: dict, old_sd: Any = None) -> None:
    """``payment.discounts`` 를 정리하고 ``payment.discount`` 를 합계로 맞춘다(in-place).

    목록을 모르는 화면(태블릿 실측 폼 등)은 ``discounts`` 없이 ``discount`` 숫자만 보낸다.
    그 숫자가 저장된 합계와 같으면 저장된 목록을 되살리고, 다르면 숫자가 이긴다(목록 삭제).
    목록도 저장값도 없으면 아무것도 하지 않는다(옛 주문 호환).

    Args:
        structured_data: 저장할 structured_data.
        old_sd: 저장 전 structured_data(목록 보존 판단용).
    """
    if not isinstance(structured_data, dict):
        return
    payment = structured_data.get("payment")
    if not isinstance(payment, dict):
        return
    if "discounts" not in payment:
        old_payment = old_sd.get("payment") if isinstance(old_sd, dict) else None
        old_items = old_payment.get("discounts") if isinstance(old_payment, dict) else None
        if not isinstance(old_items, list) or not old_items:
            return
        kept = clean_discount_items(old_items)
        if _coerce_amount(payment.get("discount")) != sum(row["amount"] for row in kept):
            return
        payment["discounts"] = kept
    items = clean_discount_items(payment.get("discounts"))
    payment["discounts"] = items
    payment["discount"] = sum(row["amount"] for row in items)


__all__ = [
    "MAX_DISCOUNT_ITEMS",
    "clean_discount_items",
    "normalize_payment_discounts",
]

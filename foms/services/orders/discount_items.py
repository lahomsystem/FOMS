"""주문 할인 항목(``payment.discounts``) 정규화.

할인은 "이름 + 금액" 줄 여러 개로 받는다. 잔금·견적·정산·결제 동기화는 모두
``payment.discount``(합계 숫자)만 읽으므로, 목록이 오면 서버가 합계를 다시 계산해
``payment.discount`` 에 써 둔다(클라이언트 합계는 믿지 않는다).

목록이 없는 옛 주문은 건드리지 않는다 — ``payment.discount`` 숫자가 그대로 정본이다.
"""

from __future__ import annotations

from typing import Any
import re

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


_EXPR_ALLOWED = re.compile(r"^[0-9,+\-\s원]+$")
_EXPR_TOKEN = re.compile(r"([+-]?)\s*([0-9][0-9,]*)")


def eval_discount_expr(value: Any) -> int | None:
    """"50,000-10,000" 같은 덧셈·뺄셈 식을 계산한다. 식이 아니면 None.

    숫자 하나만 있으면(연산자 없음) 식이 아니다. 결과는 0 이상으로 자른다.
    """
    text = str(value or "").strip()
    if not text or len(text) > MAX_DISCOUNT_LABEL_LEN or not _EXPR_ALLOWED.match(text):
        return None
    body = text.replace("원", "").replace(" ", "")
    if not re.search(r"[0-9][+-]", body):
        return None
    pos = 0
    total = 0
    for match in _EXPR_TOKEN.finditer(body):
        if match.start() != pos:
            return None
        num = int(match.group(2).replace(",", ""))
        total += -num if match.group(1) == "-" else num
        pos = match.end()
    if pos != len(body):
        return None
    return max(0, total)


def clean_discount_items(raw: Any) -> list[dict[str, Any]]:
    """할인 줄 목록을 정리한다. 금액 0 이하 줄은 버리고 최대 20줄만 남긴다.

    Args:
        raw: 클라이언트가 보낸 ``payment.discounts`` 값.

    Returns:
        ``[{"label": str, "amount": int, "expr"?: str}, ...]`` — 이름이 비면 "할인".
        ``expr`` 가 덧셈·뺄셈 식이면 금액은 그 식의 결과다.
    """
    if not isinstance(raw, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        expr_amount = eval_discount_expr(row.get("expr"))
        amount = expr_amount if expr_amount is not None else _coerce_amount(row.get("amount"))
        if amount <= 0:
            continue
        label = str(row.get("label") or "").strip()[:MAX_DISCOUNT_LABEL_LEN]
        item: dict[str, Any] = {"label": label or DEFAULT_DISCOUNT_LABEL, "amount": amount}
        if expr_amount is not None:
            # 식은 화면 표기용으로 남기고, 금액은 서버가 식으로 다시 계산한 값이다.
            item["expr"] = str(row.get("expr")).strip()
        cleaned.append(item)
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
    "eval_discount_expr",
    "normalize_payment_discounts",
]

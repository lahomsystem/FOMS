"""네이버 쿠폰 표시 값 — 주문 화면 예약금 옆 쿠폰 그림 · 한 줄 · 내역 (2026-11-24).

낱말과 돈 표기는 **여기 서버가 만든다**. 화면(``erp-naver-coupon.js``)은 받은 글을 그대로
그리기만 한다 — 누가 냈는지 판정이 두 곳에 생기면 한쪽만 고쳐져 어긋난다.

색 뜻(사장님 2026-11-24 결정): 우리가 낸 몫이 있으면 ``ours``(초록), 네이버가 전부 냈으면
``naver``(주황), 누가 냈는지 모르거나 원본을 못 읽었으면 ``unknown``(노랑).
"""
from __future__ import annotations

from typing import Any

#: 네이버 쿠폰 종류 부호 → 화면에 쓰는 이름. 모르는 부호는 그냥 "쿠폰" 이다.
COUPON_LABELS: dict[str, str] = {
    "NMP_PRD_DCNT": "상품 할인 쿠폰",
    "NMP_PRD_DUP_DCNT": "상품 중복 할인 쿠폰",
}

TONE_OURS = "ours"
TONE_NAVER = "naver"
TONE_UNKNOWN = "unknown"


def _won(amount: int) -> str:
    return f"{amount:,}원"


def _who(coupon: dict[str, Any]) -> str:
    """쿠폰 한 장을 누가 냈는지 한 줄."""
    ratio = coupon.get("naver_burden_ratio")
    if ratio is None:
        return "누가 냈는지 모름"
    if ratio >= 100:
        return "네이버가 전부 냄"
    burden = int(coupon.get("seller_burden_amount") or 0)
    if ratio <= 0:
        return "우리가 전부 냄"
    return f"네이버 {ratio}% · 우리 {_won(burden)}"


def build_coupon_view(coupons: list[dict[str, Any]], *, known: bool) -> dict[str, Any] | None:
    """쿠폰 표시 값을 만든다.

    Args:
        coupons: :func:`mapping.build_payment_info` 의 ``coupons`` 행을 주문 전체로 모은 목록.
        known: 모든 상품주문 원본을 읽었는가. 못 읽은 것이 있으면 "안 썼다"고 말할 수 없다.

    Returns:
        ``{tone, line, title, rows[{label, amount, who}], total, ours}``.
        쿠폰을 안 쓴 주문(원본을 다 읽었고 0장)은 ``None`` — 화면에 아무것도 안 생긴다.
    """
    if not coupons:
        if known:
            return None
        return {
            "tone": TONE_UNKNOWN,
            "line": "쿠폰 썼는지 모름",
            "title": "쿠폰 내역",
            "rows": [],
            "note": "네이버에서 받은 자료를 읽지 못해 쿠폰을 썼는지 알 수 없습니다. "
                    "네이버 판매자 화면에서 확인해 주세요.",
            "total": "",
            "ours": "",
        }
    total = sum(int(row.get("discount_amount") or 0) for row in coupons)
    ours = sum(int(row.get("seller_burden_amount") or 0) for row in coupons)
    ratio_unknown = any(row.get("naver_burden_ratio") is None for row in coupons)
    count = len(coupons)
    head = f"쿠폰 {_won(total)}" if count == 1 else f"쿠폰 {count}장 {_won(total)}"
    if ours > 0:
        tone, tail = TONE_OURS, f"우리 몫 {_won(ours)}"
    elif ratio_unknown:
        tone, tail = TONE_UNKNOWN, "누가 냈는지 모름"
    else:
        tone, tail = TONE_NAVER, "네이버가 냄"
    return {
        "tone": tone,
        "line": f"{head} · {tail}",
        "title": f"쿠폰 내역 {count}장",
        "rows": [
            {
                "label": COUPON_LABELS.get(str(row.get("class_code") or ""), "쿠폰"),
                "amount": f"-{_won(int(row.get('discount_amount') or 0))}",
                "who": _who(row),
            }
            for row in coupons
        ],
        "note": "" if known else "읽지 못한 네이버 자료가 있어 쿠폰이 더 있을 수 있습니다.",
        "total": f"-{_won(total)}",
        # 비율을 모르는 쿠폰이 섞이면 우리 몫 합계는 "적어도" 이 값이다.
        "ours": _won(ours) + (" 이상(모르는 쿠폰 있음)" if ratio_unknown else ""),
    }

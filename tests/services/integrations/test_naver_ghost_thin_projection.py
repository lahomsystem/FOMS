"""유령 스캔의 축소 스냅샷이 **판정 입력을 버리지 않는가** (2026-09-13).

`find_ghost_orders` 는 주문에 붙은 링크를 전부 읽는다. 운영에서 그 전량이 1,958KB 였고
판정이 읽는 경로만 남기면 290KB 다(조회 788ms → 167ms, 같은 연결·같은 489행). 그래서
입력을 얇게 했는데, **얇게 하다 판정 입력을 버리면 술어를 바꾼 것**이 된다 — R-7 이 정확히
그 사고였다(`claimStatus` 가 top-level `return` 에만 실려 오는 반품에서 얇은 경로는
"클레임 없음", 두꺼운 경로는 "반품"으로 갈렸다).

여기서 재는 것 둘:

1. 블록 목록이 :mod:`mapping` 에서 파생되는가(이름이 늘면 여기서 빨개진다).
2. 모양별로 얇은 문서와 통째 문서가 **같은 판정·같은 금액**을 내는가.
"""

from __future__ import annotations

from typing import Any

from foms.services.integrations.naver_commerce.ghost_orders import (
    GHOST_PROJECTION_BLOCK_KEYS,
    _claim_of,
    _fold_link,
    _new_bucket,
)
from foms.services.integrations.naver_commerce.mapping import (
    CLAIM_BLOCK_KEYS,
    RETURN_BLOCK_KEYS,
)

#: SQL 투영이 만드는 문서와 **같은 모양**을 파이썬으로 만든다.
def _project(snapshot: dict[str, Any]) -> dict[str, Any]:
    product = snapshot.get("productOrder")
    product = product if isinstance(product, dict) else {}
    order = snapshot.get("order")
    order = order if isinstance(order, dict) else {}
    thin: dict[str, Any] = {
        "order": {"claimStatus": order.get("claimStatus")},
        "productOrder": {
            "claimStatus": product.get("claimStatus", snapshot.get("claimStatus")),
            "claimType": product.get("claimType", snapshot.get("claimType")),
            # 금액은 `productOrder` 안만 본다 — SQL 투영도 COALESCE 를 쓰지 않는다.
            "totalPaymentAmount": product.get("totalPaymentAmount"),
        },
    }
    for key in GHOST_PROJECTION_BLOCK_KEYS:
        thin[key] = snapshot.get(key)
    return thin


#: 판정 경로를 한 번씩 태우는 모양들. 이름은 사람이 읽는 이름표다.
SHAPES: dict[str, dict[str, Any]] = {
    "중첩-정상": {
        "order": {"orderId": "G-1"},
        "productOrder": {"productOrderId": "P-1", "totalPaymentAmount": 100000,
                         "productName": "버리는 표시 값"},
    },
    "상품주문-취소확정": {
        "order": {"orderId": "G-2"},
        "productOrder": {"productOrderId": "P-2", "claimStatus": "CANCEL_DONE",
                         "claimType": "CANCEL", "totalPaymentAmount": 250000},
    },
    "평평-취소요청": {
        "order": {"orderId": "G-3"},
        "claimStatus": "CANCEL_REQUEST", "claimType": "CANCEL",
        "totalPaymentAmount": 70000,
    },
    "최상위블록-반품확정": {
        "order": {"orderId": "G-4"},
        "productOrder": {"productOrderId": "P-4", "totalPaymentAmount": 310000},
        "return": {"claimStatus": "RETURN_DONE", "claimType": "RETURN"},
    },
    "cancel-블록": {
        "order": {"orderId": "G-5"},
        "productOrder": {"productOrderId": "P-5", "totalPaymentAmount": 40000},
        "cancel": {"claimStatus": "CANCEL_DONE", "claimType": "CANCEL"},
    },
    "currentClaim": {
        "order": {"orderId": "G-6"},
        "productOrder": {"productOrderId": "P-6", "totalPaymentAmount": 55000},
        "currentClaim": {"claimStatus": "RETURN_REQUEST", "claimType": "RETURN"},
    },
    "주문단위-클레임": {
        "order": {"orderId": "G-7", "claimStatus": "CANCEL_DONE"},
        "productOrder": {"productOrderId": "P-7", "totalPaymentAmount": 12000},
    },
    "빈-원본": {},
}


def test_projection_block_list_is_derived_from_mapping() -> None:
    """판정이 읽는 블록 이름이 투영 목록에 전부 있어야 한다(드리프트 게이트)."""
    needed = set(CLAIM_BLOCK_KEYS) | set(RETURN_BLOCK_KEYS) | {"currentClaim", "beforeClaim"}
    missing = needed - set(GHOST_PROJECTION_BLOCK_KEYS)
    assert not missing, f"얇은 경로가 판정 입력을 버린다: {sorted(missing)}"


def test_thin_and_thick_agree_on_every_shape() -> None:
    """모양마다 얇은 문서와 통째 문서의 판정이 같아야 한다."""
    for name, snapshot in SHAPES.items():
        assert _claim_of(_project(snapshot)) == _claim_of(snapshot), f"{name} 판정이 갈린다"


def test_thin_and_thick_agree_on_the_folded_bucket() -> None:
    """접은 결과(건수·취소수·금액 합)도 같아야 한다 — 금액은 띠 문장이 말한다."""
    for name, snapshot in SHAPES.items():
        thick, thin = _new_bucket(), _new_bucket()
        _fold_link(thick, snapshot=snapshot, order_no="2026000001", link_id=1)
        _fold_link(thin, snapshot=_project(snapshot), order_no="2026000001", link_id=1)
        for key in ("link_count", "canceled", "amount_total", "order_nos",
                    "claim_labels", "phases", "kinds"):
            assert thick[key] == thin[key], f"{name} 의 {key} 가 갈린다"


def test_shapes_include_both_verdicts() -> None:
    """음성 대조군 — 모양 목록에 클레임 있는 것과 없는 것이 **둘 다** 있어야 한다.

    전부 클레임 없음이면 위 두 계약이 빈 판정끼리 비교해 늘 통과한다.
    """
    phases = {_claim_of(snapshot)[1] for snapshot in SHAPES.values()}
    assert {""} < phases, f"모양이 한쪽뿐이다: {phases}"

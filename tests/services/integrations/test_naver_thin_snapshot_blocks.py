"""얇은 스냅샷 투영이 **판정 입력을 버리지 않는가** (R-7, 2026-08-28).

`_snapshot_projection` docstring 은 스스로 규율을 적어 놓았다 — "판정 함수를 두 벌로
만들면 계약 §2.4(뱃지 == 탭 숫자 == 칩 '전체')가 깨진다 … 그래서 **술어가 아니라 입력만**
얇게 한다". 그런데 투영이 `return`·`returnInfo`·`exchange`·`delivery` 를 통째로 버렸다.
`extract_claim` 은 바로 그 블록들을 읽으므로(`_claim_blocks`), **입력을 얇게 한 것이 곧
술어를 바꾼 것**이었다.

발동 조건은 `claimStatus` 가 `productOrder`/`order` 밖에만 실려 오는 반품이다
(top-level `return.claimStatus` — 스테이징 실측 키 목록에 있다). 그러면 얇은 경로는
"클레임 없음", 두꺼운 경로는 "반품"으로 읽어 **배지 수 ≠ 목록**이 된다. 이 저장소가
두 번 겪은 결함이다(nav 67·탭 45 / nav 140·필터 43).
"""

from __future__ import annotations

from foms.services.integrations.naver_commerce.mapping import (
    CLAIM_BLOCK_KEYS,
    RETURN_BLOCK_KEYS,
    extract_claim,
    extract_delivery,
    extract_return_axis,
)
from foms.web.admin.naver_ingest import SNAPSHOT_PROJECTION_KEYS


def _project(snapshot: dict) -> dict:
    """SQL 투영이 남기는 최상위 키만 남긴다 — 얇은 경로가 보는 것과 같은 문서."""
    return {key: value for key, value in snapshot.items() if key in SNAPSHOT_PROJECTION_KEYS}


def test_projection_carries_every_block_the_predicates_read():
    """판정이 읽는 블록 이름이 투영 목록에 **전부** 있어야 한다(드리프트 게이트).

    `mapping` 에 블록 이름이 하나 늘면 여기서 빨개진다 — 늘려 놓고 투영에 안 넣으면
    얇은 경로만 조용히 다른 답을 낸다.
    """
    needed = set(CLAIM_BLOCK_KEYS) | set(RETURN_BLOCK_KEYS) | {"currentClaim", "delivery"}
    missing = needed - set(SNAPSHOT_PROJECTION_KEYS)
    assert not missing, f"얇은 경로가 판정 입력을 버린다: {sorted(missing)}"


def test_thin_path_reads_a_return_that_lives_only_in_the_top_level_block():
    """`claimStatus` 가 top-level `return` 에만 있는 반품을 얇은 경로도 읽는다."""
    snapshot = {
        "order": {"orderId": "N-THIN-1"},
        "productOrder": {"productOrderId": "PO-THIN-1"},
        "return": {"claimStatus": "RETURN_DONE", "claimType": "RETURN",
                   "returnCompletedDate": "2026-08-27T10:02:11.000+09:00"},
    }
    thick = extract_claim(snapshot)
    thin = extract_claim(_project(snapshot))

    assert thick["status"] == "RETURN_DONE"
    assert thin == thick, "얇은 경로가 '클레임 없음'이라 답한다"


def test_thin_path_keeps_the_return_axis_and_delivery():
    """반품 축과 발송 사실도 같아야 한다 — `is_return_pending` 이 이 둘을 읽는다."""
    snapshot = {
        "order": {"orderId": "N-THIN-2"},
        "productOrder": {"productOrderId": "PO-THIN-2", "claimStatus": "RETURN_DONE"},
        "return": {"claimStatus": "RETURN_DONE", "collectDeliveryMethod": "RETURN_INDIVIDUAL"},
        "delivery": {"sendDate": "2026-08-20T10:00:00.000+09:00"},
    }
    assert extract_return_axis(_project(snapshot)) == extract_return_axis(snapshot)
    assert extract_delivery(_project(snapshot)) == extract_delivery(snapshot)
    assert extract_delivery(_project(snapshot))["send_date"], "발송 사실이 사라졌다"


def test_projection_still_drops_display_only_fields():
    """**음성 대조군** — 표시 전용 필드는 그대로 버린다(얇게 만든 이유가 사라지면 안 된다).

    스냅샷 본문이 행 조회 비용의 약 80%였다(2026-08-24 실측). 판정이 안 읽는 것은 계속 뺀다.
    """
    for display_only in ("productName", "totalPaymentAmount", "productOrderDate",
                         "shippingDueDate", "ordererName"):
        assert display_only not in SNAPSHOT_PROJECTION_KEYS, display_only

# -*- coding: utf-8 -*-
"""2026-10-28 구 클레임 필드 지원 종료 대비 계약 (NVCLAIM-SUNSET-01).

커머스API 공지 **"구.클레임 필드 지원 종료 예정 안내 (10/28)"**
(https://github.com/commerce-api-naver/commerce-api/discussions/3608, author
``commerce-api-naver``)는 **2026년 10월 28일** 부터 우리가 쓰는 조회 API
``POST /v1/pay-order/seller/product-orders/query`` 응답에서 ``data[n].cancel`` ·
``data[n].return`` · ``data[n].exchange`` 를 반환하지 않는다고 적고, 대체 노드로
``data[n].currentClaim.*`` 과 **``data[n].beforeClaim.exchange``** 를 든다.

**이 파일의 픽스처는 전부 "그날 이후 모양"이다** — 구 필드가 아예 없다. 지금 테스트가
전부 구 필드가 있는 문서로만 돌기 때문에, 이 음성 공간을 채우지 않으면 10/28 에
조용히 깨진다. 깨지는 방식이 나쁘다: 클레임을 못 읽으면 :func:`blocks_irreversible`
이 열려 **이미 환불된 집에 발송처리가 나간다**(불가역·오발송).

문서가 ``beforeClaim`` 을 교환에만 적은 것은 그대로 둔다 — 취소·반품도 그리로 가는지는
**문서에 없다**. 그래서 판정을 추정으로 바꾸지 않고 **읽는 그릇만** 늘렸고, 이 파일은
그 그릇이 실제로 읽히는지만 잠근다.
"""
from __future__ import annotations

import pytest

from foms.services.integrations.naver_commerce.mapping import (
    blocks_irreversible,
    extract_claim,
)
from foms.web.admin.naver_ingest import SNAPSHOT_PROJECTION_KEYS


def _detail(**holders) -> dict:
    """구 필드가 **없는** 상세 1건 — 10/28 이후 응답 모양."""
    base = {"order": {"orderId": "N-SUNSET"},
            "productOrder": {"productOrderId": "PO-SUNSET",
                             "productClass": "조합형옵션상품"}}
    base.update(holders)
    return base


def test_current_claim_only_shape_is_still_read():
    """구 필드 없이 ``currentClaim`` 만 와도 클레임을 읽는다(취소·반품의 대체 경로)."""
    detail = _detail(currentClaim={"claimType": "RETURN", "claimStatus": "RETURN_DONE"})
    claim = extract_claim(detail)
    assert claim["status"] == "RETURN_DONE", claim
    assert blocks_irreversible(claim), "환불이 끝난 집에 불가역 호출이 열렸다"


def test_before_claim_shape_is_read_too():
    """``beforeClaim`` 에 실려 와도 놓치지 않는다 — 이것이 10/28 안전장치의 핵심이다.

    공지가 대체 노드로 명시한 자리이고, 우리가 **한 번도 읽지 않던** 그릇이다.
    """
    detail = _detail(beforeClaim={"claimType": "EXCHANGE", "claimStatus": "EXCHANGE_REQUEST"})
    claim = extract_claim(detail)
    assert claim["status"] == "EXCHANGE_REQUEST", claim
    assert blocks_irreversible(claim), (
        "교환이 도는 집을 '클레임 없음'으로 읽었다 — 불가역 호출이 그대로 나간다")


def test_current_claim_wins_over_before_claim():
    """지금 도는 클레임이 지나간 클레임을 이긴다 — 그릇 우선순위 계약."""
    detail = _detail(
        currentClaim={"claimType": "RETURN", "claimStatus": "RETURN_REQUEST"},
        beforeClaim={"claimType": "EXCHANGE", "claimStatus": "EXCHANGE_DONE"})
    assert extract_claim(detail)["status"] == "RETURN_REQUEST"


def test_no_claim_at_all_still_reads_as_clean():
    """**음성 대조군** — 그릇을 늘렸다고 없는 클레임을 만들어내면 안 된다.

    이게 없으면 위 두 테스트는 "무조건 막는다"로도 통과한다.
    """
    claim = extract_claim(_detail())
    assert not claim["status"], claim
    assert not blocks_irreversible(claim), "클레임이 없는 집을 막았다"


def test_thin_projection_keeps_the_replacement_nodes():
    """얇은 경로도 같은 그릇을 남긴다 — 안 그러면 얇은 화면만 갈린다(R-7 재발).

    입력을 얇게 하는 것이 곧 술어를 바꾸는 것이었던 사고가 이 저장소에 이미 있다.
    """
    for key in ("currentClaim", "beforeClaim"):
        assert key in SNAPSHOT_PROJECTION_KEYS, f"{key} 가 얇은 스냅샷에서 빠졌다"


@pytest.mark.parametrize("holder", ["currentClaim", "beforeClaim"])
def test_either_holder_blocks_an_irreversible_call(holder):
    """두 그릇 중 어디에 실려 와도 불가역 호출은 닫힌다."""
    detail = _detail(**{holder: {"claimType": "CANCEL", "claimStatus": "CANCEL_DONE"}})
    assert blocks_irreversible(extract_claim(detail))

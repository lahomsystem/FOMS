"""수집 링크의 **클레임 축 사본 컬럼** 값 한 벌 (NVMIRROR-01, 2026-09-13).

왜 사본인가
-----------
``raw_snapshot`` 평균이 **2,194 bytes** 라 PostgreSQL TOAST 임계(약 2KB)를 넘는다. 대부분의
스냅샷이 본체 밖에 있어서, 그 컬럼을 건드리는 조회는 행마다 TOAST 를 한 번 더 읽는다.
운영 실측(2026-09-13, 2,388행, 같은 스캔을 두 방식으로):

    raw_snapshot 에서 스칼라 두 개를 뽑는다 →  Buffers: shared hit=14736,  50.519 ms
    raw_snapshot 을 아예 안 건드린다       →  Buffers: shared hit=  249,   0.953 ms

스칼라 투영은 이미 쓰고 있으므로 투영으로는 더 줄지 않는다 — **컬럼을 건드리는 것 자체**가
비용이다. ``place_order_status``·``group_key``·``recipient_*`` 와 같은 규약으로 자주 보는 값을
컬럼으로 뺀다.

규약 (기존 사본 셋과 동일)
--------------------------
* **정본은 언제나** ``raw_snapshot`` 이다. 사본은 필터·집계 전용이다.
* 값이 없으면(백필 전 행) 읽는 쪽이 **스냅샷 경로로 폴백**해 예전과 같은 답을 낸다 —
  그래서 배포 순서가 어긋나도 화면이 안 바뀌고 게이트가 필요 없다.
* 추출 실패가 수집을 막지 않는다. 못 받은 주문은 되돌릴 수 없다.

**NULL 과 빈 문자열을 가른다** (이 모듈의 핵심 규약)
-----------------------------------------------------
* ``NULL`` = **아직 계산하지 않았다**(백필 전 행). 읽는 쪽은 이 행만 스냅샷으로 폴백한다.
* ``''``(빈 문자열) = **계산했고 값이 없다**(클레임이 없는 정상 건). 폴백하지 않는다.

이 구분이 없으면 "클레임 없음" 과 "모름" 이 같은 NULL 이 되어, 백필이 끝난 뒤에도 클레임 없는
행 전부가 폴백을 타 TOAST 를 다시 읽는다(운영 489행 중 클레임 있는 행은 119개뿐이라 나머지
370행이 그렇게 된다). 금액은 같은 이유로 계산됐으면 ``0`` 을 쓴다.

``claim_status``·``claim_type`` 은 원본 필드 하나가 아니라 :func:`mapping.extract_claim` 의
결과다. 그 함수가 6개 블록(``cancel``·``returnInfo``·``return``·``exchange``·``currentClaim``
·``beforeClaim``)을 훑는 SSOT 이고, 여기서 손으로 경로를 고르면 얇은 경로만 "클레임 없음" 이
되는 R-7 이 재발한다.

스펙: ``docs/specs/2026-09-13-naver-link-claim-mirror_SPEC.md``
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from foms.services.integrations.naver_commerce.mapping import extract_claim

logger = logging.getLogger(__name__)

#: 사본 컬럼 이름과 상한. 상한은 원본 규격이 아니라 **우리가 자르는 길이**다 — 채널이 더 긴
#: 코드를 보내도 사본이 수집을 깨지 않게 한다(마이그레이션 ``nvmirror_00`` 와 같은 값).
MIRROR_MAX_LENGTHS = {
    "product_order_status": 30,
    "claim_status": 40,
    "claim_type": 20,
}

#: 사본 컬럼 전체(정수 컬럼 포함). 갱신 자리가 빠짐없이 쓰는지 계약 테스트가 이 목록을 쓴다.
MIRROR_COLUMNS = ("product_order_status", "claim_status", "claim_type", "payment_amount")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _product_order(detail: Any) -> dict[str, Any]:
    """``productOrder`` 블록. 평평한 응답이면 최상위가 그 역할을 한다(``unwrap_detail`` 규약)."""
    if not isinstance(detail, dict):
        return {}
    nested = detail.get("productOrder")
    return nested if isinstance(nested, dict) else detail


def claim_mirror_values(detail: Any) -> dict[str, Optional[Any]]:
    """스냅샷 1건에서 사본 컬럼 네 개의 값을 만든다.

    반환 규약(모듈 docstring 의 NULL/`''` 구분):

    * 계산에 성공했고 값이 없으면 ``''``(금액은 ``0``) — "클레임 없음" 을 뜻한다.
    * 계산 자체를 못 했으면 ``None`` — "모름" 이고, 읽는 쪽이 스냅샷으로 폴백한다.

    Args:
        detail: 상품주문 상세 1건(``raw_snapshot`` 에 넣는 것과 같은 문서).

    Returns:
        ``{"product_order_status", "claim_status", "claim_type", "payment_amount"}``.
    """
    unknown: dict[str, Optional[Any]] = {name: None for name in MIRROR_COLUMNS}
    if not isinstance(detail, dict):
        return unknown

    product = _product_order(detail)
    values: dict[str, Optional[Any]] = {}

    status = _text(product.get("productOrderStatus")) or _text(detail.get("productOrderStatus"))
    values["product_order_status"] = status[:MIRROR_MAX_LENGTHS["product_order_status"]]

    # 금액은 **중첩 `productOrder` 안만** 본다. `ghost_orders._fold_link` 가 그렇게 읽으므로,
    # 여기서 평평한 최상위까지 폴백하면 평평한 응답에서 사본이 스냅샷보다 큰 합계를 낸다
    # (계약 테스트가 이 차이를 잡았다 — 사본은 동치가 먼저다).
    nested = detail.get("productOrder")
    amount = nested.get("totalPaymentAmount") if isinstance(nested, dict) else None
    # `bool` 은 `int` 의 하위형이다 — True 가 1원으로 새지 않게 막는다.
    values["payment_amount"] = (
        amount if isinstance(amount, int) and not isinstance(amount, bool) else 0)

    try:
        claim = extract_claim(detail)
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        # 사본이라 흐름을 막지 않는다. 클레임 축만 "모름" 으로 남기고 나머지 둘은 유지한다.
        logger.warning("[NAVER] 클레임 사본 추출 실패(무시): %s", exc)
        values["claim_status"] = None
        values["claim_type"] = None
        return values

    values["claim_status"] = _text(claim.get("status"))[:MIRROR_MAX_LENGTHS["claim_status"]]
    values["claim_type"] = _text(claim.get("type"))[:MIRROR_MAX_LENGTHS["claim_type"]]
    return values


def apply_claim_mirror(link: Any, detail: Any) -> dict[str, Optional[Any]]:
    """링크 객체에 사본 값을 **제자리로** 얹는다(수집·클레임 스윕이 함께 쓴다).

    발주확인(``fulfillment``)은 부르지 않는다 — 그 경로는 ``placeOrderStatus`` 만 바꾸고
    클레임 축·금액·``productOrderStatus`` 는 건드리지 않는다.

    값을 못 뽑아도 기존 사본을 **지우지 않는다** — 옛 사본이 빈 값보다 정확하다
    (``claim_watch`` 의 ``group_key`` 갱신과 같은 규율).

    Args:
        link: ``ExternalOrderLink`` 인스턴스.
        detail: 상품주문 상세 1건.

    Returns:
        실제로 얹은 값들(진단·테스트용).
    """
    values = claim_mirror_values(detail)
    applied: dict[str, Optional[Any]] = {}
    for name in MIRROR_COLUMNS:
        value = values.get(name)
        # ``None`` = 모름. 덮지 않는다 — 옛 사본이 "모름" 보다 정확하다.
        # ``''``·``0`` 은 계산된 값이므로 그대로 쓴다(그게 폴백을 끊는 신호다).
        if value is None:
            continue
        setattr(link, name, value)
        applied[name] = value
    return applied


def snapshot_from_mirror(*, claim_status: Any, claim_type: Any,
                         payment_amount: Any) -> dict[str, Any]:
    """사본 값으로 **판정용 최소 스냅샷**을 만든다 — 술어를 두 벌로 만들지 않으려고.

    사본을 읽는 쪽이 `if 사본: ... else: 스냅샷 ...` 처럼 판정을 따로 쓰면 그 순간 술어가
    두 벌이 된다(R-7 이 그 사고였다). 대신 사본을 **같은 모양의 문서**로 되돌려 기존 판정
    함수(:func:`mapping.extract_claim`·``ghost_orders._fold_link``)에 그대로 넣는다.

    되돌릴 수 있는 이유: ``claim_status``·``claim_type`` 자체가 :func:`mapping.extract_claim`
    의 결과라, 그것을 ``productOrder`` 자리에 놓으면 같은 함수가 같은 값을 다시 낸다.

    Args:
        claim_status: 사본 ``claim_status``.
        claim_type: 사본 ``claim_type``.
        payment_amount: 사본 ``payment_amount``.

    Returns:
        ``{"productOrder": {...}}`` 모양의 문서.
    """
    return {
        "productOrder": {
            "claimStatus": claim_status or "",
            "claimType": claim_type or "",
            "totalPaymentAmount": (payment_amount if isinstance(payment_amount, int)
                                   and not isinstance(payment_amount, bool) else None),
        },
    }

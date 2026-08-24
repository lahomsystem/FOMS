"""수집분에 대응하는 **기존 주문 후보**를 찾는다 (NAVER-INGEST-02 T16-C).

왜 필요한가
-----------
수집 판정은 ``productOrderStatus == PAYED`` 하나뿐이라 세 가지가 전부 "새 집"으로 들어온다:
신규 주문 / 취소 후 **재결제** / 기존 주문의 **차액 결제**(30cm·1cm 상품을 금액 맞춰 구매).
셋을 구분하지 못하면 CS 가 "주문 만들기"를 눌러 **중복 주문**을 만든다(스테이징 실데이터에
같은 고객 2회 4명, 소액 단독 집 2개가 이미 있다).

**자동으로 붙이지 않는다.** 돈과 시공이 걸린 판단이라 시스템은 후보와 근거만 제시하고,
확정은 사람이 한다(2026-08-19 사용자 확정: 옵션 귀속과 같은 원칙).

매칭 규칙
---------
전화번호는 digits 로 정규화해서 본다(``erp_phone_digits`` 는 P1-02 검색용 인덱스 컬럼이라
그대로 재사용한다). 주문자와 수취인이 다른 대리주문이 실재하므로 **둘 다** 본다.

점수는 신뢰도 순이다:

* 수취인 전화 일치 = 100 (가장 강한 단서)
* 주문자 전화 일치 = 80
* 이름 + 주소 앞부분 일치 = 60 (전화가 바뀐 재주문 대비)

같은 주문이 여러 규칙에 걸리면 가장 높은 점수만 남긴다.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import or_

from foms.services.datetime_kst import now_utc_naive
from foms.services.phone_search import normalize_phone_digits
from models import ExternalOrderLink, Order

logger = logging.getLogger(__name__)

__all__ = ["find_order_candidates", "CANDIDATE_WINDOW_DAYS", "CANDIDATE_LIMIT"]

#: 후보를 찾는 기간(일). 가구는 실측·제작·시공까지 몇 달이 걸려 차액 결제가 늦게 온다.
CANDIDATE_WINDOW_DAYS = 180

#: 화면에 보여줄 최대 후보 수. 더 많으면 사람이 못 고른다.
CANDIDATE_LIMIT = 5

#: 주소 비교에 쓰는 앞부분 길이. 상세주소(동·호)는 빼고 건물까지만 본다.
ADDRESS_PREFIX_LEN = 10

#: 점수 — 값 자체보다 순서가 의미다.
SCORE_RECIPIENT_PHONE = 100
SCORE_ORDERER_PHONE = 80
SCORE_NAME_ADDRESS = 60

#: 후보 스캔 상한. 이름+주소 규칙은 인덱스가 이름까지만 걸려 후보가 많아질 수 있다.
NAME_SCAN_CAP = 200


def _snapshot_keys(raw_snapshot: Any) -> dict[str, str]:
    """원본에서 매칭 키(수취인/주문자 전화·이름·주소)를 뽑는다.

    Args:
        raw_snapshot: ``ExternalOrderLink.raw_snapshot``.

    Returns:
        ``{"recipient_phone", "orderer_phone", "name", "address"}`` — digits 정규화 완료.
        읽을 수 없으면 전부 빈 문자열.
    """
    empty = {"recipient_phone": "", "orderer_phone": "", "name": "", "address": ""}
    if not isinstance(raw_snapshot, dict) or not raw_snapshot:
        return empty
    try:
        from foms.services.integrations.naver_commerce.mapping import (
            build_address,
            unwrap_detail,
        )

        order, _product_order, shipping = unwrap_detail(raw_snapshot)
    except (ValueError, TypeError, AttributeError) as exc:  # 표시용 보조라 흐름을 막지 않는다
        logger.warning("[NAVER] 후보 매칭 키 추출 실패: %s", exc)
        return empty
    return {
        "recipient_phone": normalize_phone_digits(shipping.get("tel1")) or "",
        "orderer_phone": normalize_phone_digits((order or {}).get("ordererTel")) or "",
        "name": str(shipping.get("name") or "").strip(),
        "address": build_address(shipping or {}),
    }


def _order_view(order: Order, *, score: int, reason: str,
                link_count: int) -> dict[str, Any]:
    """후보 1건을 화면용 dict 로 편다."""
    return {
        "order_id": int(order.id),
        "customer_name": order.customer_name,
        "phone": order.phone,
        "address": order.address,
        "product": order.product,
        "received_date": order.received_date,
        "status": order.status,
        "payment_amount": order.payment_amount,
        "score": score,
        "reason": reason,
        # 이미 네이버 수집분이 붙어 있는 주문인지(재결제·추가결제 판단에 쓰인다).
        "naver_link_count": link_count,
    }


def find_order_candidates(session, link: ExternalOrderLink, *,
                          limit: int = CANDIDATE_LIMIT,
                          window_days: int = CANDIDATE_WINDOW_DAYS) -> list[dict[str, Any]]:
    """이 수집분이 붙을 만한 **기존 주문 후보**를 점수순으로 돌려준다.

    자동 판정이 아니다 — 사람이 고르라고 근거와 함께 늘어놓는 것이다.

    Args:
        session: DB 세션.
        link: 기준 수집 링크(원본 스냅샷에서 매칭 키를 뽑는다).
        limit: 최대 후보 수.
        window_days: 최근 며칠 안에 접수된 주문만 볼지.

    Returns:
        후보 dict 목록(점수 내림차순, 같으면 최근 주문 먼저). 단서가 없으면 빈 목록.
    """
    keys = _snapshot_keys(link.raw_snapshot)
    if not any(keys.values()):
        return []

    since = (now_utc_naive() - timedelta(days=window_days))
    base = session.query(Order).filter(
        Order.not_deleted_filter(),
        Order.created_at >= since,
    )
    if link.order_id:
        # 이미 이 링크가 붙은 주문은 후보가 아니다(자기 자신).
        base = base.filter(Order.id != int(link.order_id))

    scored: dict[int, tuple[int, str]] = {}

    phone_terms = []
    if keys["recipient_phone"]:
        phone_terms.append((keys["recipient_phone"], SCORE_RECIPIENT_PHONE, "수취인 전화 일치"))
    if keys["orderer_phone"] and keys["orderer_phone"] != keys["recipient_phone"]:
        phone_terms.append((keys["orderer_phone"], SCORE_ORDERER_PHONE, "주문자 전화 일치"))

    for digits, score, reason in phone_terms:
        # erp_phone_digits 는 인덱스 컬럼(P1-02). phone 원문은 형식이 제각각이라 보조로만 본다.
        rows = (
            base.filter(or_(Order.erp_phone_digits == digits,
                            Order.phone == digits))
            .order_by(Order.created_at.desc())
            .limit(limit * 2)
            .all()
        )
        for order in rows:
            current = scored.get(int(order.id))
            if current is None or score > current[0]:
                scored[int(order.id)] = (score, reason)

    if keys["name"] and keys["address"]:
        prefix = keys["address"][:ADDRESS_PREFIX_LEN]
        # 이름으로 좁힌 뒤 주소는 파이썬에서 비교한다 — 주소 LIKE 는 인덱스가 없다.
        rows = (
            base.filter(Order.customer_name == keys["name"])
            .order_by(Order.created_at.desc())
            .limit(NAME_SCAN_CAP)
            .all()
        )
        for order in rows:
            if not (order.address or "").startswith(prefix):
                continue
            if int(order.id) not in scored:
                scored[int(order.id)] = (SCORE_NAME_ADDRESS, "이름·주소 일치")

    if not scored:
        return []

    orders = {
        int(order.id): order
        for order in session.query(Order).filter(Order.id.in_(list(scored.keys()))).all()
    }
    link_counts: dict[int, int] = {}
    from sqlalchemy import func as _func

    for order_id, count in (
        session.query(ExternalOrderLink.order_id, _func.count(ExternalOrderLink.id))
        .filter(ExternalOrderLink.order_id.in_(list(scored.keys())))
        .group_by(ExternalOrderLink.order_id)
        .all()
    ):
        link_counts[int(order_id)] = int(count)

    views = [
        _order_view(orders[order_id], score=score, reason=reason,
                    link_count=link_counts.get(order_id, 0))
        for order_id, (score, reason) in scored.items()
        if order_id in orders
    ]
    views.sort(key=lambda row: (-row["score"], -row["order_id"]))
    return views[:limit]

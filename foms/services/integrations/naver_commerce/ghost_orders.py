"""네이버 결제가 **전부 취소된** ERP 주문 찾기 — 유령 주문 (R-2 · 2026-08-25).

왜 필요한가
-----------
고객이 네이버 주문을 취소하면 ``claim_watch`` 가 그 사실을 목격해 링크에 표시하고 담당자에게
알린다. 그런데 **그 결제로 만들어진 ERP 주문은 아무도 건드리지 않는다** — 주문 상태를 자동으로
바꾸지 않는 것이 규율이기 때문이다(그 자체는 옳다: 취소가 곧 주문 폐기는 아니다).

문제는 그 다음이다. 취소 뒤 재결제가 들어오면 담당자가 새 집을 붙이지만, **재결제가 안 오면**
그 ERP 주문은 살아 있는 채로 남는다. 결제는 취소됐는데 주문은 접수 상태다.
2026-08-25 스테이징 실조회에서 그런 주문이 **3건** 나왔다(#4467 원주현 2,451,500원 ·
#4462 박선미 · #4466 강재상). **어떤 화면도 이 사실을 말하지 않는다.**

판정 기준(스펙 D-3)
-------------------
* 붙어 있는 네이버 링크가 **1건 이상**이고
* 그 링크가 **전부** 클레임(취소·반품) 상태이며
* 주문이 아직 살아 있다(``deleted_at IS NULL``).

부분 취소는 제외한다 — 일부만 취소된 주문은 정상 진행 중일 수 있고, 그걸 유령이라 부르면
띠가 거짓말을 한다.

**자동으로 지우지 않는다.** 목록과 근거를 내놓고 사람이 고른다.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from models import ExternalOrderLink, Order

logger = logging.getLogger(__name__)

__all__ = ["find_ghost_orders", "GHOST_LIST_LIMIT", "DISCARDABLE_STATUSES"]

#: 띠에서 펼쳐 보여줄 최대 건수. 더 많으면 사람이 못 훑는다(수는 배지가 말한다).
GHOST_LIST_LIMIT = 20

#: `취소 처리`(soft delete) 버튼을 열어 주는 진행 단계.
#: 실측 이후 단계는 방문 기록·치수가 붙어 있어 접으면 그 이력이 화면에서 사라진다 —
#: 그래서 **접수 단계에서만** 연다. 나머지는 승계(재결제로 정리)가 맞다.
DISCARDABLE_STATUSES = ("RECEIVED",)


def _claim_of(snapshot: Any) -> str:
    """상품주문 스냅샷의 클레임 상태 문자열(정상이면 빈 문자열)."""
    if not isinstance(snapshot, dict):
        return ""
    product_order = snapshot.get("productOrder")
    if not isinstance(product_order, dict):
        return ""
    return str(product_order.get("claimStatus") or "").strip()


def find_ghost_orders(session, *, limit: int = GHOST_LIST_LIMIT) -> dict[str, Any]:
    """네이버 결제가 전부 취소된 살아 있는 주문 목록 (R-2).

    Args:
        session: 요청 스코프 DB 세션.
        limit: 목록에 담을 최대 건수(수는 전체를 센다).

    Returns:
        ``{"count": 전체 건수, "rows": [...]}``. 각 행은 주문 요약 + 네이버 사실 +
        ``can_discard``(취소 처리 버튼을 열지) + ``discard_block``(못 여는 이유).
    """
    rows = (
        session.query(ExternalOrderLink.order_id, ExternalOrderLink.raw_snapshot,
                      ExternalOrderLink.external_order_no)
        .filter(ExternalOrderLink.order_id.isnot(None))
        .all()
    )
    buckets: dict[int, dict[str, Any]] = {}
    for order_id, snapshot, order_no in rows:
        bucket = buckets.setdefault(int(order_id), {
            "link_count": 0, "canceled": 0, "amount_total": 0,
            "order_nos": [], "claim_labels": set(),
        })
        bucket["link_count"] += 1
        claim = _claim_of(snapshot)
        if claim:
            bucket["canceled"] += 1
            bucket["claim_labels"].add(claim)
        product_order = snapshot.get("productOrder") if isinstance(snapshot, dict) else None
        if isinstance(product_order, dict):
            amount = product_order.get("totalPaymentAmount")
            if isinstance(amount, int):
                bucket["amount_total"] += amount
        text = str(order_no or "").strip()
        if text and text not in bucket["order_nos"]:
            bucket["order_nos"].append(text)

    # 전부 취소된 것만 남긴다(부분 취소 제외 — 정상 진행 중일 수 있다).
    ghost_ids = [order_id for order_id, bucket in buckets.items()
                 if bucket["link_count"] and bucket["canceled"] == bucket["link_count"]]
    if not ghost_ids:
        return {"count": 0, "rows": []}

    orders = (
        session.query(Order)
        .filter(Order.id.in_(ghost_ids), Order.not_deleted_filter())  # perf-ok: id batch
        .all()
    )
    if not orders:
        return {"count": 0, "rows": []}

    views: list[dict[str, Any]] = []
    for order in orders:
        bucket = buckets[int(order.id)]
        status = str(order.status or "")
        can_discard = status in DISCARDABLE_STATUSES
        views.append({
            "order_id": int(order.id),
            "customer_name": order.customer_name or "",
            "phone": order.phone or "",
            "status": status,
            "received_date": order.received_date or "",
            "payment_amount": order.payment_amount or 0,
            "naver_order_nos": bucket["order_nos"],
            "naver_link_count": bucket["link_count"],
            "naver_amount_total": bucket["amount_total"],
            # 반품(RETURN_*)과 취소(CANCEL_*)를 한 낱말로 뭉치지 않는다 — 사람이 보는 사실이 다르다.
            "claim_kind": "반품" if any(label.startswith("RETURN")
                                        for label in bucket["claim_labels"]) else "취소",
            "can_discard": can_discard,
            "discard_block": "" if can_discard else f"{status} 단계라 이력이 붙어 있습니다",
        })

    # 금액 큰 것부터 — 돈이 큰 유령이 더 급하다.
    views.sort(key=lambda row: (-int(row["naver_amount_total"] or 0), -row["order_id"]))
    return {"count": len(views), "rows": views[:limit]}


def find_repay_candidate_links(session, phones: list[str]) -> dict[str, list[dict[str, Any]]]:
    """유령 주문의 전화번호로 **아직 아무 주문에도 안 붙은 집**을 찾는다 (재결제 짝 후보).

    유령 주문 옆에 "8/24 집이 큐에 대기 중" 이 함께 보이면 담당자가 그 자리에서
    재결제로 정리할지 판단할 수 있다. 실데이터 3건 중 2건(#4462·#4466)에 짝이 있었다.

    Args:
        session: DB 세션.
        phones: 유령 주문의 전화번호 목록.

    Returns:
        ``{전화번호: [{external_order_no, created_at, link_id}]}``.
    """
    from foms.services.phone_search import normalize_phone_digits

    wanted = {normalize_phone_digits(phone) for phone in phones if phone}
    wanted.discard("")
    if not wanted:
        return {}

    pairs: dict[str, list[dict[str, Any]]] = {}
    rows = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.order_id.is_(None),
                ExternalOrderLink.sync_status == "COLLECTED")
        .order_by(ExternalOrderLink.id.desc())
        .limit(500)  # perf-ok: 미연결 집만, 최신 우선
        .all()
    )
    for link in rows:
        snapshot = link.raw_snapshot if isinstance(link.raw_snapshot, dict) else {}
        product_order = snapshot.get("productOrder")
        if not isinstance(product_order, dict):
            continue
        shipping = product_order.get("shippingAddress")
        tel = normalize_phone_digits((shipping or {}).get("tel1")) if isinstance(shipping, dict) else ""
        if not tel or tel not in wanted:
            continue
        # 이미 취소된 집은 재결제 짝이 아니다 — 그것도 유령이다.
        if _claim_of(snapshot):
            continue
        seen = pairs.setdefault(tel, [])
        order_no = str(link.external_order_no or "")
        if any(row["external_order_no"] == order_no for row in seen):
            continue
        seen.append({
            "external_order_no": order_no,
            "link_id": int(link.id),
            "created_at": link.created_at,
        })
    return pairs


def attach_repay_candidates(session, ghosts: dict[str, Any]) -> None:
    """유령 목록 각 행에 재결제 짝 후보를 붙인다(제자리 수정).

    Args:
        session: DB 세션.
        ghosts: :func:`find_ghost_orders` 결과.

    Returns:
        None.
    """
    from foms.services.phone_search import normalize_phone_digits

    rows = ghosts.get("rows") or []
    if not rows:
        return
    pairs = find_repay_candidate_links(session, [row["phone"] for row in rows])
    for row in rows:
        digits = normalize_phone_digits(row["phone"]) or ""
        row["repay_candidates"] = pairs.get(digits, [])

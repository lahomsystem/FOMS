"""수집분 → FOMS 주문 생성 (NAVER-INGEST-01 T12).

수집(:mod:`~foms.services.integrations.naver_commerce.ingest`)과 분리된 **두 번째 단계**다.
사람이 관리 화면에서 "주문 만들기"를 눌렀을 때만 돈다.

**네트워크를 쓰지 않는다** — 입력은 이미 저장된 ``ExternalOrderLink.raw_snapshot`` 이다.
그래서 web 프로세스에서 호출해도 안전하다(네이버 HTTP 는 여전히 WORKER 전용이라는 계약이
깨지지 않는다). 이 모듈을 ``ingest`` 안에 두지 않은 이유가 그것이다 — web 이 ``ingest`` 를
import 하면 WORKER 단일 출구 계약 테스트가 red 가 된다.

주문 생성은 ``create_order()`` 만 경유한다(raw ``Order(...)`` 금지 — ORDER-CREATE-01).
좌표는 주입하지 않는다: 네이버 좌표는 주문서 주소 기준이라 실제 시공 주소와 다를 수 있고,
주입하면 ``geocode_status='success'`` 로 굳어 재지오코딩에서도 빠진다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import (
    NaverMappingError,
    group_key,
    map_group,
)
from foms.services.orders.order_create import create_order
from models import ExternalOrderLink

logger = logging.getLogger(__name__)


class PromotionError(RuntimeError):
    """주문을 만들 수 없다(사유는 사람이 읽는 문장으로 담는다)."""


def promote_link_to_order(
    session: Session, *, link_id: int, actor_user_id: int, owner_user_id: int,
    now: Optional[datetime] = None,
) -> tuple[int, bool]:
    """수집 링크 1건을 FOMS 주문으로 만든다(이미 있으면 그대로 돌려준다).

    커밋은 호출자가 소유한다.

    Args:
        session: DB 세션.
        link_id: ``ExternalOrderLink.id``.
        actor_user_id: 생성 주체(이벤트 author).
        owner_user_id: 초기 owner(미배정 보류함 계정).
        now: 테스트용 시각 주입.

    Returns:
        ``(order_id, created)`` — ``created`` 는 이번 호출이 만들었는지 여부.
        버튼 두 번 눌러도 주문은 하나다(두 번째는 ``False``).

    Raises:
        PromotionError: 링크 부재 · 원본 없음 · 매핑 실패 · 이미 폐기된 상태.
    """
    link = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == CHANNEL)
        .with_for_update()
        .first()
    )
    if link is None:
        raise PromotionError(f"수집 기록을 찾을 수 없습니다 (link {link_id}).")
    if link.order_id:
        # 멱등: 동시 클릭·새로고침 재전송에도 주문은 하나다.
        return (int(link.order_id), False)
    if link.sync_status not in ("COLLECTED", "PENDING_REVIEW"):
        raise PromotionError(
            f"주문을 만들 수 있는 상태가 아닙니다 (현재 {link.sync_status})."
        )
    if not isinstance(link.raw_snapshot, dict) or not link.raw_snapshot:
        raise PromotionError("원본 스냅샷이 없어 주문을 만들 수 없습니다.")

    # 한 네이버 주문(본품 + 구성 옵션)을 한 FOMS 주문으로 묶는다 — T13.
    siblings = _group_siblings(session, link)
    today = get_today_kst().strftime("%Y-%m-%d")
    try:
        order_fields, structured = map_group(
            [row.raw_snapshot for row in siblings], today=today)
    except NaverMappingError as exc:
        link.sync_status = "PENDING_REVIEW"
        link.failure_reason = str(exc)[:2000]
        raise PromotionError(f"원본을 주문으로 옮길 수 없습니다: {exc}") from exc

    order = create_order(
        session,
        actor_user_id=actor_user_id,
        owner_user_id=owner_user_id,
        order_fields=order_fields,
        structured_data=structured,
        is_erp_order=True,
        now=now or now_utc_naive(),
    )
    for row in siblings:
        row.order_id = order.id
        row.sync_status = "LINKED"
        row.failure_reason = None
    session.flush()
    logger.info("[NAVER] 수집분 주문 생성 link=%s(+%d) order=%s",
                link_id, len(siblings) - 1, order.id)
    return (int(order.id), True)


def _group_siblings(session: Session, link: ExternalOrderLink) -> list[ExternalOrderLink]:
    """같은 묶음(주문번호·수취인 전화·주소)의 **주문 미생성** 링크들을 모은다.

    묶음 키에 전화·주소가 들어가는 이유는 분할배송이다 — 같은 주문번호라도 수취인이 다르면
    합치면 안 된다(남의 주소로 시공 나가는 사고).

    이미 주문이 붙은 형제는 제외한다. 사람이 부분적으로 먼저 만들었을 수 있고, 그때 다시
    묶으면 같은 상품주문이 두 주문에 들어간다.

    Args:
        session: DB 세션.
        link: 기준 링크(반드시 결과에 포함된다).

    Returns:
        묶을 링크 목록(기준 링크 우선, 나머지는 id 순).
    """
    key = group_key(link.raw_snapshot or {})
    order_no = key[0]
    if not order_no:
        return [link]

    candidates = (
        session.query(ExternalOrderLink)
        .filter(
            ExternalOrderLink.channel == CHANNEL,
            ExternalOrderLink.external_order_no == order_no,
            ExternalOrderLink.order_id.is_(None),
            ExternalOrderLink.sync_status.in_(("COLLECTED", "PENDING_REVIEW")),
            ExternalOrderLink.id != link.id,
        )
        .with_for_update()
        .order_by(ExternalOrderLink.id)
        .all()
    )
    siblings = [link]
    for row in candidates:
        if isinstance(row.raw_snapshot, dict) and group_key(row.raw_snapshot) == key:
            siblings.append(row)
    return siblings


def summarize_snapshot(raw_snapshot: Any) -> dict[str, Any]:
    """목록 표시용 요약(고객·제품·수량·금액·옵션 원문)을 원본에서 뽑는다.

    주문이 아직 없어도 사람이 무엇을 받았는지 보고 판단할 수 있어야 한다. 매핑이 실패하는
    원본도 있으므로 **실패해도 빈 값으로 돌려준다**(목록이 통째로 죽으면 안 된다).

    Args:
        raw_snapshot: ``ExternalOrderLink.raw_snapshot``.

    Returns:
        dict: ``customer_name``·``product``·``options``·``quantity``·``amount``·``order_date``.
    """
    empty = {"customer_name": "", "product": "", "options": "",
             "quantity": None, "amount": None, "order_date": ""}
    if not isinstance(raw_snapshot, dict) or not raw_snapshot:
        return empty
    try:
        from foms.services.integrations.naver_commerce.mapping import unwrap_detail

        _order, product_order, shipping = unwrap_detail(raw_snapshot)
    except (NaverMappingError, ValueError, TypeError, AttributeError) as exc:
        logger.warning("[NAVER] 목록 요약 실패(빈 값으로 표시): %s", exc)
        return empty

    product_order = product_order or {}
    shipping = shipping or {}
    quantity = product_order.get("quantity")
    amount = product_order.get("totalPaymentAmount")
    return {
        "customer_name": str(shipping.get("name") or "").strip(),
        "product": str(product_order.get("productName") or "").strip(),
        "options": str(product_order.get("productOption") or "").strip(),
        "quantity": int(quantity) if isinstance(quantity, int) else None,
        "amount": int(amount) if isinstance(amount, int) else None,
        "order_date": str((_order or {}).get("orderDate") or "")[:10],
    }


__all__ = ["PromotionError", "promote_link_to_order", "summarize_snapshot"]

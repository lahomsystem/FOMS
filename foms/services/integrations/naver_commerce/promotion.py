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
    extract_claim,
    extract_place_status,
    group_key,
    map_group,
)
from foms.services.orders.order_create import create_order
from models import ExternalOrderLink, Order

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

    # 취소·반품 건은 주문으로 만들지 않는다. 수집 필터가 productOrderStatus == PAYED
    # 하나뿐이라 **취소 요청 상태도 PAYED 로 수집된다**(2026-08-14 스테이징 실물 1건).
    # 화면 버튼만 잠그면 API 직접 호출로 뚫리므로 서비스에서 막는다.
    blocked = [row for row in siblings if extract_claim(row.raw_snapshot or {})["blocking"]]
    if blocked:
        claim = extract_claim(blocked[0].raw_snapshot or {})
        detail = f"{claim['label']}" + (f" · 사유 {claim['reason']}" if claim["reason"] else "")
        logger.warning("[NAVER] 클레임 건 주문 생성 차단 link=%s status=%s",
                       link_id, claim["status"])
        raise PromotionError(
            f"네이버에서 취소·반품이 진행 중인 주문입니다 ({detail}). "
            "네이버 판매자센터에서 상태를 확인한 뒤 진행하세요."
        )
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


#: 기존 주문에 붙일 수 있는 관계. ``NEW`` 는 붙이기가 아니라 주문 생성 경로다.
ATTACHABLE_RELATIONS = ("ADDON", "REPAY")


def attach_link_to_order(session: Session, *, link_id: int, order_id: int,
                         relation: str) -> tuple[int, int]:
    """수집분을 **기존 주문에 붙인다** — 새 주문을 만들지 않는다 (T16-E).

    차액 결제(ADDON)와 취소 후 재결제(REPAY)가 여기로 온다. 둘 다 새 집이 아니라 이미 있는
    집의 후속이라, 주문을 하나 더 만들면 같은 고객의 시공 건이 둘로 갈린다.

    묶음(집) 단위로 붙인다 — 네이버는 본품과 구성 옵션을 각각 다른 상품주문으로 주므로
    한 건만 붙이면 나머지가 미아가 된다(:func:`_group_siblings` 와 같은 규칙).

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        link_id: 기준 수집 링크 id.
        order_id: 붙일 기존 FOMS 주문 id.
        relation: ``ADDON`` 또는 ``REPAY``.

    Returns:
        ``(붙인 링크 수, 주문 id)``.

    Raises:
        PromotionError: 관계값·링크·주문이 잘못됐거나, 취소·반품 건을 ADDON 으로 붙이려 할 때,
            또는 이미 **다른** 주문에 붙어 있을 때.
    """
    if relation not in ATTACHABLE_RELATIONS:
        raise PromotionError(f"붙일 수 없는 관계입니다 ({relation}).")

    link = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == CHANNEL)
        .first()
    )
    if link is None:
        raise PromotionError(f"수집 기록을 찾을 수 없습니다 (link {link_id}).")

    order = session.get(Order, int(order_id))
    if order is None or order.deleted_at is not None or order.status == "DELETED":
        raise PromotionError(f"붙일 주문을 찾을 수 없습니다 (order {order_id}).")

    siblings = _group_siblings_for_attach(session, link)
    # 취소·반품 건은 추가결제로 붙이지 않는다 — 재결제(REPAY)는 원 주문이 취소된 경우라 허용.
    if relation == "ADDON":
        blocked = [row for row in siblings if extract_claim(row.raw_snapshot or {})["blocking"]]
        if blocked:
            claim = extract_claim(blocked[0].raw_snapshot or {})
            raise PromotionError(
                f"네이버에서 취소·반품이 진행 중인 주문입니다 ({claim['label']}). "
                "추가결제로 붙일 수 없습니다."
            )

    attached = 0
    for row in siblings:
        if row.order_id and int(row.order_id) != int(order_id):
            raise PromotionError(
                f"이미 다른 주문(#{row.order_id})에 붙어 있습니다. 먼저 되돌린 뒤 다시 붙이세요."
            )
        row.order_id = int(order_id)
        row.relation = relation
        row.sync_status = "LINKED"
        row.failure_reason = None
        attached += 1
    session.flush()
    logger.info("[NAVER] 수집분 기존 주문 연결 link=%s(+%d) order=%s relation=%s",
                link_id, attached - 1, order_id, relation)
    return (attached, int(order_id))


def detach_link_from_order(session: Session, *, link_id: int) -> tuple[int, Optional[int]]:
    """붙이기를 되돌린다 (T16-E) — 사람이 관계를 잘못 골랐을 때.

    ``NEW`` 로 만든 주문(승격)은 되돌리지 않는다. 그건 주문 삭제 문제라 이 경로의 일이 아니다.

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        link_id: 기준 수집 링크 id.

    Returns:
        ``(되돌린 링크 수, 원래 붙어 있던 주문 id)``.

    Raises:
        PromotionError: 링크가 없거나, 붙이기로 연결된 건이 아닐 때.
    """
    link = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == CHANNEL)
        .first()
    )
    if link is None:
        raise PromotionError(f"수집 기록을 찾을 수 없습니다 (link {link_id}).")
    if link.relation not in ATTACHABLE_RELATIONS:
        raise PromotionError("붙이기로 연결된 건이 아닙니다(주문 생성분은 되돌릴 수 없습니다).")

    previous_order_id = int(link.order_id) if link.order_id else None
    siblings = [row for row in _group_siblings_for_attach(session, link)
                if row.relation in ATTACHABLE_RELATIONS]
    for row in siblings:
        row.order_id = None
        row.relation = "NEW"
        row.sync_status = "COLLECTED"
    session.flush()
    logger.info("[NAVER] 붙이기 되돌림 link=%s(+%d) order=%s",
                link_id, len(siblings) - 1, previous_order_id)
    return (len(siblings), previous_order_id)


def _group_siblings_for_attach(session: Session,
                               link: ExternalOrderLink) -> list[ExternalOrderLink]:
    """붙이기·되돌리기 대상 묶음 — 같은 네이버 주문번호의 링크 전부.

    승격용 :func:`_group_siblings` 는 **주문이 없는** 링크만 모은다(부분 생성 방어). 붙이기는
    반대로 이미 같은 주문에 붙은 형제까지 함께 다뤄야 되돌리기가 반쪽이 되지 않는다.
    """
    order_no = (link.external_order_no or "").strip()
    if not order_no:
        return [link]
    rows = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.channel == CHANNEL,
                ExternalOrderLink.external_order_no == order_no)
        .order_by(ExternalOrderLink.id.asc())
        .all()
    )
    return rows or [link]


def _group_siblings(session: Session, link: ExternalOrderLink) -> list[ExternalOrderLink]:
    """같은 묶음(주문번호·수취인 전화·주소)의 **주문 미생성** 링크들을 모은다.

    묶음 키에 전화·주소가 들어가는 이유는 분할배송이다 — 같은 주문번호라도 수취인이 다르면
    합치면 안 된다(남의 주소로 시공 나가는 사고).

    이미 주문이 붙은 형제는 제외한다. 사람이 부분적으로 먼저 만들었을 수 있고, 그때 다시
    묶으면 같은 상품주문이 두 주문에 들어간다.

    Args:
        session: DB 세션.
        link: 기준 링크(반드시 결과에 포함된다).

    **순서가 의미를 갖는다**: 추가옵션 귀속(:mod:`attribution`)이 수집 순서를 읽으므로
    기준 링크를 앞으로 끌어내면 안 된다 — 그러면 본품 2개짜리 집이 ``M M a a`` 배치로
    보여 옵션이 한 본품에 몰린다(2026-08-19 스테이징 실사고: 12건이 180cm 본품에 몰림).
    그래서 **기준 링크를 포함한 전체를 id(수집) 순으로** 돌려준다.

    Returns:
        묶을 링크 목록 — **수집 순서(id 오름차순)**.
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
    return sorted(siblings, key=lambda row: row.id)


def summarize_snapshot(raw_snapshot: Any) -> dict[str, Any]:
    """목록 표시용 요약(고객·제품·수량·금액·옵션 원문)을 원본에서 뽑는다.

    주문이 아직 없어도 사람이 무엇을 받았는지 보고 판단할 수 있어야 한다. 매핑이 실패하는
    원본도 있으므로 **실패해도 빈 값으로 돌려준다**(목록이 통째로 죽으면 안 된다).

    Args:
        raw_snapshot: ``ExternalOrderLink.raw_snapshot``.

    Returns:
        dict: ``customer_name``·``product``·``options``·``quantity``·``amount``·``order_date``
        + 클레임 표시(``claim_*``) + 발주 상태(``place_*`` — T16-A).
    """
    empty = {"customer_name": "", "product": "", "options": "",
             "quantity": None, "amount": None, "order_date": "",
             "claim_label": "", "claim_blocking": False,
             # 원본이 없거나 깨졌으면 "발주확인 여부를 모른다" — 완료로 읽지 않는다.
             "place_status": "", "place_label": "", "place_confirmed": False,
             "shipping_due": ""}
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
    claim = extract_claim(raw_snapshot)
    place = extract_place_status(raw_snapshot)
    return {
        "customer_name": str(shipping.get("name") or "").strip(),
        "product": str(product_order.get("productName") or "").strip(),
        "options": str(product_order.get("productOption") or "").strip(),
        "quantity": int(quantity) if isinstance(quantity, int) else None,
        "amount": int(amount) if isinstance(amount, int) else None,
        "order_date": str((_order or {}).get("orderDate") or "")[:10],
        # 목록에서도 취소 건을 알아볼 수 있어야 한다(빈 문자열이면 정상 주문).
        "claim_label": claim["label"],
        "claim_blocking": claim["blocking"],
        # 발주확인 여부는 수집 시점 원본에 이미 들어온다 — 네이버 호출 0회로 표시한다(T16-A).
        "place_status": place["status"],
        "place_label": place["label"],
        "place_confirmed": place["confirmed"],
        "shipping_due": place["shipping_due"][:10],
    }


__all__ = ["PromotionError", "promote_link_to_order", "summarize_snapshot",
           "attach_link_to_order", "detach_link_from_order", "ATTACHABLE_RELATIONS"]

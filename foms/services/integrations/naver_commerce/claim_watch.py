"""수집 이후에 생긴 취소·반품을 따라간다 (NAVER-INGEST-01 T14-F).

수집은 ``productOrderStatus == PAYED`` 인 순간의 상태만 본다. 고객이 **주문을 받은 뒤에**
취소하면 FOMS 는 영영 모르고, 취소된 집으로 생산·시공이 나갈 수 있었다.

**추가 API 호출을 최소로 한다**: 5분 스윕이 이미 받아오는 변경 목록(``last-changed-statuses``)
에 이미 수집한 상품주문이 뜬 경우에만 그 건의 상세를 다시 부른다. 변경이 없으면 호출 0회다.
변경 목록의 상태 문자열로 바로 판정하지 않는 이유: 취소가 그 목록에 어떤 이름으로 실리는지
실물로 확인되지 않았다. 취소 여부의 정본은 **상세 응답의 ``claimStatus``** 다(실측 확인).

발견 시 동작은 **표시 + 담당자 알림**까지다(2026-08-15 사용자 확정). 주문 상태를 자동으로
바꾸지 않는다 — 이미 잡힌 일정·도면이 있으면 자동 변경이 더 큰 혼란을 만든다.
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import (
    extract_claim,
    extract_external_id,
)
from models import ExternalOrderLink, Notification, Order, OrderAssignment, User

logger = logging.getLogger(__name__)

#: 알림 타입. push 를 받으려면 ``push_sender._DEFAULT_P1_TYPES`` 에도 등재돼 있어야 한다
#: (미등재면 enqueue 해도 조용히 no-op — 무음 알림의 유일한 기전).
NOTIFICATION_TYPE = "NAVER_ORDER_CLAIMED"

#: ``triage_state`` 안에서 이 기능이 쓰는 키. 도크 체크(checked·assigned_main)와 다른 축이다.
STATE_KEY = "claim_sync"


def changed_external_ids(entries: list[dict]) -> list[str]:
    """변경 이벤트 목록에서 상품주문번호를 중복 없이 뽑는다(상태 불문).

    수집 후보(:func:`mapping.is_collectible`)와 달리 **상태로 거르지 않는다** — 취소·반품도
    변경 이벤트로 오기 때문이다.

    Args:
        entries: ``last-changed-statuses`` 항목 목록.

    Returns:
        상품주문번호 목록(입력 순서 보존).
    """
    out: list[str] = []
    seen: set[str] = set()
    for entry in entries or []:
        external_id = str((entry or {}).get("productOrderId") or "").strip()
        if external_id and external_id not in seen:
            seen.add(external_id)
            out.append(external_id)
    return out


def _notify_targets(session: Session, link: ExternalOrderLink) -> list[int]:
    """알림 받을 사용자 id — 주문 담당 SALES, 없으면 활성 ADMIN 전원.

    담당자가 아직 없으면(보류함 소유) 아무도 못 보는 알림이 되므로 ADMIN 으로 올린다.
    """
    if link.order_id:
        rows = (
            session.query(OrderAssignment)
            .filter(
                OrderAssignment.order_id == int(link.order_id),
                OrderAssignment.domain == "SALES",
                OrderAssignment.active.is_(True),
            )
            .all()
        )
        holder_ids = [int(row.user_id) for row in rows]
        if holder_ids:
            holders = (
                session.query(User)
                .filter(User.id.in_(holder_ids), User.is_active.is_(True))
                .all()
            )
            # 미배정 보류함 계정이 owner 면 사람이 아니다 — ADMIN 으로 넘긴다.
            from foms.services.integrations.naver_commerce.constants import OWNER_USERNAME

            real = [int(u.id) for u in holders if u.username != OWNER_USERNAME]
            if real:
                return real
    admins = (
        session.query(User)
        .filter(User.role == "ADMIN", User.is_active.is_(True))
        .all()
    )
    return [int(u.id) for u in admins]


def _notify(session: Session, link: ExternalOrderLink, claim: dict,
            *, now: datetime) -> int:
    """취소·반품 발생을 담당자(없으면 ADMIN)에게 알린다.

    Returns:
        만든 알림 건수.
    """
    from foms.services.notifications.recipients import fan_out_new_notification

    targets = _notify_targets(session, link)
    if not targets:
        logger.warning("[NAVER] 클레임 알림 대상이 없다 link=%s", link.id)
        return 0

    order = session.get(Order, int(link.order_id)) if link.order_id else None
    who = getattr(order, "customer_name", None) or ""
    title = f"네이버 {claim['label']} — {who}".strip(" —")
    detail = f" · 사유 {claim['reason']}" if claim["reason"] else ""
    where = (f"FOMS 주문 #{link.order_id}" if link.order_id
             else "아직 주문으로 만들지 않은 수집분")
    message = (
        f"네이버에서 {claim['label']} 상태로 바뀐 주문이 있습니다{detail}. "
        f"({where} · 상품주문번호 {link.external_id}) "
        "일정·생산이 잡혀 있으면 진행을 멈추고 네이버 판매자센터에서 확인하세요."
    )
    for user_id in targets:
        notification = Notification(
            order_id=int(link.order_id) if link.order_id else None,
            notification_type=NOTIFICATION_TYPE,
            target_type="USER",
            target_user_id=user_id,
            is_urgent=True,
            title=title[:200],
            message=message,
            created_at=now,
        )
        session.add(notification)
        session.flush()
        fan_out_new_notification(session, notification)
    return len(targets)


def refresh_claims(
    session: Session, *, client: Any, changed: list[dict],
    now: Optional[datetime] = None,
) -> dict[str, int]:
    """변경 이벤트가 온 **기존 링크**의 상세를 다시 받아 취소·반품을 반영한다.

    Args:
        session: DB 세션(커밋은 호출자).
        client: 네이버 클라이언트(상세 조회만 쓴다).
        changed: 이번 스윕의 변경 이벤트 목록(이미 받아 온 것을 재사용한다).
        now: 알림 생성 시각(테스트 주입).

    Returns:
        ``{"refreshed", "claimed", "notified"}`` 집계.
    """
    stamp = now or now_utc_naive()
    result = {"refreshed": 0, "claimed": 0, "notified": 0}
    ids = changed_external_ids(changed)
    if not ids:
        return result

    links = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.channel == CHANNEL,
                ExternalOrderLink.external_id.in_(ids))
        .all()
    )
    if not links:
        # 이미 수집한 건이 하나도 안 바뀌었다 — 추가 호출 없이 끝낸다.
        return result

    by_id = {str(link.external_id): link for link in links}
    details = client.get_product_orders(list(by_id.keys()))
    for detail in details or []:
        external_id = extract_external_id(detail)
        link = by_id.get(external_id)
        if link is None:
            continue
        claim = extract_claim(detail)
        # 원본을 최신으로 갈아 끼운다 — 화면(큐·트리아지·도크)이 전부 스냅샷에서 읽으므로
        # 이것만으로 표시가 최신이 된다.
        link.raw_snapshot = copy.deepcopy(detail)
        flag_modified(link, "raw_snapshot")
        state = copy.deepcopy(link.triage_state) if isinstance(link.triage_state, dict) else {}
        sync = dict(state.get(STATE_KEY) or {})
        sync["last_status"] = claim["status"]
        sync["refreshed_at"] = stamp.isoformat()
        result["refreshed"] += 1

        if claim["blocking"]:
            result["claimed"] += 1
            # 같은 상태로 두 번 알리지 않는다(5분 폴링이라 중복 방지가 필수).
            if sync.get("notified_status") != claim["status"]:
                sent = _notify(session, link, claim, now=stamp)
                if sent:
                    sync["notified_status"] = claim["status"]
                    result["notified"] += sent
                    logger.warning("[NAVER] 수집 후 클레임 감지 link=%s status=%s 알림 %d건",
                                   link.id, claim["status"], sent)
        state[STATE_KEY] = sync
        link.triage_state = state
        flag_modified(link, "triage_state")
    return result


__all__ = [
    "NOTIFICATION_TYPE",
    "STATE_KEY",
    "changed_external_ids",
    "refresh_claims",
]

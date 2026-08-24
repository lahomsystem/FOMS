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
    extract_place_status,
    group_key_text,
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


def _notify_targets(session: Session, link: ExternalOrderLink) -> tuple[list[int], bool]:
    """알림 받을 사용자 id 와 **ADMIN 폴백 여부**를 함께 준다.

    담당자가 아직 없으면(보류함 소유) 아무도 못 보는 알림이 되므로 ADMIN 으로 올린다.
    호출부가 두 경우를 구분해야 하는 이유: 담당자 특정은 ``USER`` 알림, ADMIN 폴백은
    ``ROLE`` 알림 1건으로 만들어야 한다(NOTIF-ROLE-01).

    Args:
        session: DB 세션.
        link: 클레임이 감지된 외부 주문 링크.

    Returns:
        ``(user_ids, is_admin_fallback)`` — 담당 SALES 가 있으면 그 사용자 id 목록과
        ``False``, 없으면 활성 ADMIN 전원의 id 목록과 ``True``. 둘 다 없으면 ``([], True)``.
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
                return real, False
    admins = (
        session.query(User)
        .filter(User.role == "ADMIN", User.is_active.is_(True))
        .all()
    )
    return [int(u.id) for u in admins], True


def _compose(session: Session, link: ExternalOrderLink, claim: dict) -> tuple[str, str]:
    """클레임 알림의 제목·본문을 만든다.

    Args:
        session: DB 세션(고객명 조회에만 쓴다).
        link: 클레임이 감지된 외부 주문 링크.
        claim: :func:`mapping.extract_claim` 결과(``label``·``reason`` 사용).

    Returns:
        ``(title, message)`` — title 은 200자로 잘라 둔 상태다.
    """
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
    return title[:200], message


def _is_our_cancel(link: ExternalOrderLink) -> bool:
    """이 링크의 취소를 **우리가** 냈는가 (판매자 직접취소 표식).

    표식은 ``fulfillment.cancel_order`` 가 집 전체에 남긴다
    (``triage_state['fulfillment']['canceled_at']``). 이 모듈의 상태 키
    (:data:`STATE_KEY` = ``claim_sync``)와 **다른 축**이라 서로 덮어쓰지 않는다.

    Args:
        link: 클레임이 감지된 링크.

    Returns:
        bool: 우리 취소 표식이 있으면 True.
    """
    state = link.triage_state if isinstance(link.triage_state, dict) else {}
    fulfillment = state.get("fulfillment")
    if not isinstance(fulfillment, dict):
        return False
    return bool(fulfillment.get("canceled_at"))


def _notify(session: Session, link: ExternalOrderLink, claim: dict,
            *, now: datetime) -> int:
    """취소·반품 발생을 담당자에게, 담당자가 없으면 ADMIN **역할**에게 알린다.

    담당자가 특정되면 그 사람 앞으로 ``target_type='USER'`` 알림을 만든다. 담당자가 없어
    관리자에게 올려야 하면 ``target_type='ROLE'`` + ``target_role='ADMIN'`` 알림을
    **1건만** 만든다 — 관리자 수만큼 Notification 을 복제하지 않는다(NOTIF-ROLE-01).
    사건 1건 = row 1건이 알림 SSOT 이고, 수신자별 읽음 상태는
    :func:`recipients.fan_out_new_notification` 이 ``notification_user_states`` 로 만든다.

    Args:
        session: DB 세션(커밋은 호출자).
        link: 클레임이 감지된 외부 주문 링크.
        claim: :func:`mapping.extract_claim` 결과.
        now: 알림 생성 시각.

    Returns:
        알림이 도달하는 **수신자 수**(대상이 없으면 0). Notification row 수가 아니다 —
        ROLE 알림은 row 1건으로 관리자 전원에게 간다. 호출부 카운터(``notified``)와
        중복 억제(``notified_status``)가 이 값의 "사람 수" 의미에 의존한다.
    """
    from foms.services.notifications.recipients import fan_out_new_notification

    targets, admin_fallback = _notify_targets(session, link)
    if not targets:
        logger.warning("[NAVER] 클레임 알림 대상이 없다 link=%s", link.id)
        return 0

    title, message = _compose(session, link, claim)
    order_id = int(link.order_id) if link.order_id else None
    common = dict(order_id=order_id, notification_type=NOTIFICATION_TYPE,
                  is_urgent=True, title=title, message=message, created_at=now)
    if admin_fallback:
        rows = [Notification(target_type="ROLE", target_role="ADMIN", **common)]
    else:
        rows = [Notification(target_type="USER", target_user_id=uid, **common)
                for uid in targets]
    for notification in rows:
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
        ``{"refreshed", "claimed", "notified", "self_canceled"}`` 집계.
        ``self_canceled`` 는 **우리가 낸 취소라 알림을 막은 건수**다 — 억제도
        세어야 "알림이 왜 안 왔지"를 나중에 확인할 수 있다.
    """
    stamp = now or now_utc_naive()
    result = {"refreshed": 0, "claimed": 0, "notified": 0, "self_canceled": 0}
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
        # 발주 상태 사본도 같이 갱신한다 — 판매자센터에서 발주확인을 하면 이 스윕이 첫
        # 목격자다. 안 갱신하면 목록 필터만 옛 값에 머문다(T16-B).
        place = extract_place_status(detail)
        link.place_order_status = (place["status"] or "")[:20] or None
        # 묶음키 사본도 같은 이유로 갱신한다 — 확인 큐는 스냅샷에서 매번 다시 계산하므로,
        # 컬럼만 옛 값에 머물면 두 화면의 집 수가 또 갈린다.
        # 값을 못 만들면 기존 값을 지우지 않는다(폴백보다 옛 사본이 정확하다).
        refreshed_group_key = group_key_text(detail)
        if refreshed_group_key:
            link.group_key = refreshed_group_key
        state = copy.deepcopy(link.triage_state) if isinstance(link.triage_state, dict) else {}
        sync = dict(state.get(STATE_KEY) or {})
        sync["last_status"] = claim["status"]
        sync["refreshed_at"] = stamp.isoformat()
        result["refreshed"] += 1

        if claim["blocking"]:
            result["claimed"] += 1
            # **우리가 낸 취소는 알리지 않는다.** 판매자 직접취소(`fulfillment.cancel_order`)를
            # 보내면 다음 스윕이 그 결과를 클레임으로 목격하고, 문안이 "일정·생산이 잡혀
            # 있으면 진행을 멈추고 판매자센터에서 확인하세요"인 긴급 알림을 담당자에게
            # 되돌려 보냈다. 방금 자기가 누른 일이 5분 뒤 경보로 돌아온다 — 진짜 고객
            # 취소와 구분이 안 되니 경보 전체가 무뎌진다(2026-08-24 감사).
            # 상태 갱신(스냅샷·발주상태·묶음키·last_status)은 그대로 한다. 사실은 사실이고,
            # 화면의 '취소 완료' 표시는 이 갱신에서 나온다. 막는 것은 **알림뿐**이다.
            if _is_our_cancel(link):
                # 조용히 넘기지 않는다 — 억제도 기록이 남아야 나중에 셀 수 있다.
                logger.info("[NAVER] 우리가 낸 취소라 클레임 알림을 보내지 않는다 link=%s status=%s",
                            link.id, claim["status"])
                sync["notified_status"] = claim["status"]
                result["self_canceled"] += 1
            # 같은 상태로 두 번 알리지 않는다(5분 폴링이라 중복 방지가 필수).
            elif sync.get("notified_status") != claim["status"]:
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

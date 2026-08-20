"""발주확인·발송처리 실행 (NAVER-INGEST-02 T16-G) — **WORKER 전용**.

네이버 HTTP 는 WORKER 에서만 나간다(커머스API 호출 IP 3슬롯 = Railway static IP 3개, 여유 0).
web 은 :func:`foms.services.jobs.queue.enqueue_naver_fulfillment` 로 enqueue 만 한다.

되돌릴 수 없는 조작이다
-----------------------
발송처리는 구매자에게 "물건이 출발했다"로 보이고 정산·구매확정 시계를 돌린다. 그래서:

* **멱등** — 링크의 ``triage_state['fulfillment']`` 에 처리 시각을 남기고, 값이 있으면
  네이버를 다시 부르지 않는다. 네이버의 400(이미 처리됨)을 정상 흐름으로 삼지 않는다.
* **실패는 조용히 넘기지 않는다** — 사유 문장을 상태에 남겨 화면이 그대로 보여준다.
* 배송방법은 자사 배송이라 ``DIRECT_DELIVERY``(직접 전달). 택배사·송장이 없다.
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce.constants import CHANNEL
from models import ExternalOrderLink

logger = logging.getLogger(__name__)

__all__ = [
    "FulfillmentError",
    "STATE_KEY",
    "DIRECT_DELIVERY",
    "confirm_place_order",
    "dispatch_order",
]

#: ``triage_state`` 안에서 이 기능이 쓰는 키. 도크 체크·클레임 동기화와 다른 축이다.
STATE_KEY = "fulfillment"

#: 자사 배송(택배사·송장 없음)의 배송방법 코드.
DIRECT_DELIVERY = "DIRECT_DELIVERY"

#: KST — 네이버는 발송일에 타임존이 붙은 ISO8601 을 요구한다.
KST = timezone(timedelta(hours=9))


class FulfillmentError(RuntimeError):
    """발주확인·발송처리 실패. 사유 문장을 그대로 사람에게 보여준다."""


def _household_key(link: ExternalOrderLink) -> tuple[str, str, str]:
    """이 링크가 속한 '집' 키 — 화면이 집을 가르는 것과 **같은 규칙**.

    화면 큐(:func:`foms.web.admin.naver_ingest._group_queue`)는
    :func:`mapping.group_key` ``(주문번호, 수취인 전화, 주소)`` 로 집을 가른다.
    여기서 주문번호만 보면 **분할배송**(같은 주문번호·다른 주소)에서 화면이 두 줄로
    보여준 것을 워커가 한 번에 처리한다 — A집만 골랐는데 B집까지 네이버로 나가고,
    그 호출은 되돌릴 수 없다.

    Args:
        link: ``ExternalOrderLink`` 행.

    Returns:
        같은 값이면 같은 집. 원본이 깨져 키를 못 만들면 그 링크 혼자인 집으로 본다
        (화면과 같은 폴백 — 큐에서 조용히 사라지는 것보다 낫다).
    """
    from foms.services.integrations.naver_commerce.mapping import group_key

    try:
        return group_key(link.raw_snapshot or {})
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        logger.warning("[NAVER] 집 키 계산 실패(link %s): %s", link.id, exc)
        return ("__ungrouped__", str(link.id), "")


def _links_of_group(session: Session, link_id: int) -> list[ExternalOrderLink]:
    """같은 **집**의 링크 전부(한 집은 통째로 처리한다).

    1차로 같은 네이버 주문번호를 모으고(인덱스 있는 축), 그중 :func:`_household_key` 가
    같은 것만 남긴다. 분할배송에서 화면이 가른 집과 서버가 처리하는 대상이 어긋나지 않게
    하는 자리다.
    """
    link = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == CHANNEL)
        .first()
    )
    if link is None:
        raise FulfillmentError(f"수집 기록을 찾을 수 없습니다 (link {link_id}).")
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
    base_key = _household_key(link)
    same_house = [row for row in rows if _household_key(row) == base_key]
    return same_house or [link]


def _state(link: ExternalOrderLink) -> dict[str, Any]:
    """링크의 fulfillment 상태(없으면 빈 dict)."""
    state = link.triage_state if isinstance(link.triage_state, dict) else {}
    value = state.get(STATE_KEY)
    return dict(value) if isinstance(value, dict) else {}


def _write_state(link: ExternalOrderLink, patch: dict[str, Any]) -> None:
    """fulfillment 상태를 병합 저장한다(다른 축은 건드리지 않는다)."""
    state = copy.deepcopy(link.triage_state) if isinstance(link.triage_state, dict) else {}
    current = dict(state.get(STATE_KEY) or {})
    current.update(patch)
    state[STATE_KEY] = current
    link.triage_state = state
    flag_modified(link, "triage_state")


def _dispatch_timestamp(now: datetime) -> str:
    """네이버가 요구하는 발송일 형식(ISO8601 밀리초 + 타임존)."""
    kst = now.replace(tzinfo=timezone.utc).astimezone(KST) if now.tzinfo is None else now.astimezone(KST)
    return kst.strftime("%Y-%m-%dT%H:%M:%S.") + f"{kst.microsecond // 1000:03d}" + kst.strftime("%z")[:3] + ":" + kst.strftime("%z")[3:]


def confirm_place_order(session: Session, client: Any, *, link_id: int,
                        actor_user_id: Optional[int] = None,
                        now: Optional[datetime] = None) -> dict[str, Any]:
    """한 집을 발주확인 처리한다 (WORKER 실행).

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        client: :class:`~...client.NaverCommerceClient`.
        link_id: 기준 링크 id.
        actor_user_id: 누른 사람(기록용).
        now: 시각 주입(테스트).

    Returns:
        ``{"confirmed": [...], "skipped": [...]}`` — 이미 처리된 건은 skipped.

    Raises:
        FulfillmentError: 링크가 없거나 네이버 호출이 실패했을 때.
    """
    stamp = now or now_utc_naive()
    links = _links_of_group(session, link_id)
    todo = [row for row in links if not _state(row).get("place_confirmed_at")]
    if not todo:
        return {"confirmed": [], "skipped": [row.external_id for row in links]}

    ids = [str(row.external_id) for row in todo]
    try:
        client.confirm_place_orders(ids)
    except Exception as exc:  # noqa: BLE001 - 사유를 상태에 남기고 그대로 올린다
        for row in todo:
            _write_state(row, {"last_error": str(exc)[:500], "last_error_at": stamp.isoformat()})
        session.flush()
        logger.warning("[NAVER] 발주확인 실패 link=%s: %s", link_id, exc)
        raise FulfillmentError(f"발주확인에 실패했습니다: {exc}") from exc

    for row in todo:
        _write_state(row, {"place_confirmed_at": stamp.isoformat(),
                           "place_confirmed_by": actor_user_id,
                           "last_error": "", "last_error_at": ""})
        # 화면 필터가 보는 사본도 같이 올린다(다음 스윕을 기다리지 않게).
        row.place_order_status = "OK"
    session.flush()
    logger.info("[NAVER] 발주확인 완료 link=%s 건수=%d", link_id, len(todo))
    return {"confirmed": ids, "skipped": [row.external_id for row in links if row not in todo]}


def dispatch_order(session: Session, client: Any, *, link_id: int,
                   delivery_method: str = DIRECT_DELIVERY,
                   actor_user_id: Optional[int] = None,
                   now: Optional[datetime] = None) -> dict[str, Any]:
    """한 집을 발송처리한다 (WORKER 실행).

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        client: 커머스API 클라이언트.
        link_id: 기준 링크 id.
        delivery_method: 배송방법 코드(기본 자사 직접 전달).
        actor_user_id: 누른 사람(기록용).
        now: 시각 주입(테스트).

    Returns:
        ``{"dispatched": [...], "skipped": [...]}``.

    Raises:
        FulfillmentError: 링크가 없거나 발주확인 전이거나 네이버 호출이 실패했을 때.
    """
    stamp = now or now_utc_naive()
    links = _links_of_group(session, link_id)
    # 발주확인 전에 발송처리를 하면 네이버가 거절한다 — 우리 화면에서 먼저 막는다.
    not_confirmed = [row for row in links
                     if not (_state(row).get("place_confirmed_at")
                             or (row.place_order_status or "").upper() == "OK")]
    if not_confirmed:
        raise FulfillmentError("발주확인이 먼저입니다(발주확인 전 상품주문이 있습니다).")

    todo = [row for row in links if not _state(row).get("dispatched_at")]
    if not todo:
        return {"dispatched": [], "skipped": [row.external_id for row in links]}

    payload = [{"productOrderId": str(row.external_id),
                "deliveryMethod": delivery_method,
                "dispatchDate": _dispatch_timestamp(stamp)}
               for row in todo]
    try:
        client.dispatch_product_orders(payload)
    except Exception as exc:  # noqa: BLE001
        for row in todo:
            _write_state(row, {"last_error": str(exc)[:500], "last_error_at": stamp.isoformat()})
        session.flush()
        logger.warning("[NAVER] 발송처리 실패 link=%s: %s", link_id, exc)
        raise FulfillmentError(f"발송처리에 실패했습니다: {exc}") from exc

    for row in todo:
        _write_state(row, {"dispatched_at": stamp.isoformat(),
                           "dispatched_by": actor_user_id,
                           "delivery_method": delivery_method,
                           "last_error": "", "last_error_at": ""})
    session.flush()
    logger.info("[NAVER] 발송처리 완료 link=%s 건수=%d", link_id, len(todo))
    return {"dispatched": [str(row.external_id) for row in todo],
            "skipped": [row.external_id for row in links if row not in todo]}

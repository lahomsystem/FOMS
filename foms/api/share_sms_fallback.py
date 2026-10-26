"""'상담 먼저' 알림톡 — 카톡이 실패한 고객에게 링크 문자를 자동으로 보낸다.

'상담 먼저' 알림톡은 링크가 없어 솔라피 문자 대체발송을 끄고 보낸다. 그래서 카톡을 못 받는
고객에게는 아무것도 가지 않았다. 워커 루프(``scripts/maintenance/run_share_consult_fallback.py``)가
1분마다 :func:`run_consult_sms_sweep` 을 불러 방금 보낸 알림톡의 결과를 솔라피에 묻고, 카톡이 실패했으면
[회사 문자]와 같은 방법(발신번호 규칙·본문·백업번호 재시도)으로 링크 문자를 보낸다.

라우트가 아니지만 ``foms/api`` 에 둔다 — 발신번호 규칙(:func:`share._resolve_sender`)과 문자
발송(:func:`share._send_sms_with_fallback`)이 API 모듈에 있고, 서비스는 API 를 import 하지 않는다.
설계서: ``docs/specs/2026-10-21-consult-sms-fallback-design.md``.
"""

from __future__ import annotations

import copy
import datetime
import logging
from typing import Any, Callable, Optional

from sqlalchemy.orm.attributes import flag_modified

from foms.api import share as share_api
from foms.services import kakao_alimtalk as ka
from foms.services import order_share as share_service
from foms.services import share_consult
from foms.services.auth.partner_scope import is_partner_order
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.drawing_customer_send import resolve_send_phone
from foms.services.orders.revision import lock_order_row
from models import Order, OrderEvent

logger = logging.getLogger(__name__)

__all__ = ["FIRST_CHECK_AFTER", "GIVE_UP_AFTER", "run_consult_sms_sweep"]

#: 보낸 뒤 이만큼 지나야 처음 묻는다(카톡 결과가 정해지는 데 수십 초 걸린다).
FIRST_CHECK_AFTER = datetime.timedelta(seconds=90)
#: 이만큼 지나도 결과를 모르면 문자를 보내지 않고 닫는다(이중 발송보다 안전).
GIVE_UP_AFTER = datetime.timedelta(minutes=30)
#: 수신 완료 · 아직 가는 중 결과 코드. 그 밖은 카톡 실패다.
_DELIVERED = "4000"
_PENDING = ("2000", "3000")
#: SHARE_SMS 이벤트로 옮길 회차 표지(도면 탭 상태 줄이 같은 회차로 짝짓는다).
_ROUND_TAGS = ("round_at", "round", "source_screen")


def _candidates(session, now: datetime.datetime) -> list[int]:
    """아직 판정하지 않은 '상담 먼저' 발송 이벤트 id(오래된 것부터)."""
    rows = (
        session.query(OrderEvent.id, OrderEvent.payload)
        .filter(OrderEvent.event_type == "SHARE_ALIMTALK",
                OrderEvent.created_at <= now - FIRST_CHECK_AFTER,
                OrderEvent.created_at >= now - GIVE_UP_AFTER - datetime.timedelta(minutes=10))
        .order_by(OrderEvent.id)
        .all()
    )
    picked = []
    for event_id, payload in rows:
        consult = (payload or {}).get("consult")
        if (payload or {}).get("status") == "sent" and isinstance(consult, dict) \
                and consult.get("message_id") and not consult.get("kakao_result"):
            picked.append(event_id)
    return picked


def _mark(event: OrderEvent, **fields: Any) -> None:
    """이벤트의 ``consult`` 에 판정 결과를 덧쓴다."""
    payload = copy.deepcopy(event.payload or {})
    payload["consult"] = {**payload.get("consult", {}), **fields}
    event.payload = payload
    flag_modified(event, "payload")


def _send_link_sms(session, event: OrderEvent, now: datetime.datetime) -> dict[str, Any]:
    """카톡 실패가 확정된 발송 하나에 링크 문자를 보낸다. 결과를 ``consult.sms_fallback`` 로 돌려준다."""
    payload = event.payload or {}
    order = (session.query(Order)
             .filter(Order.id == event.order_id, Order.active_filter()).one_or_none())
    if order is None or is_partner_order(order):
        return {"status": "skipped", "reason": "order_gone"}
    if payload.get("to_phone_override"):
        # 바꾼 번호는 저장하지 않는다(보내기 창 Q5-②) — 영업이 직접 보낸다.
        return {"status": "skipped", "reason": "phone_override"}
    to_phone, _override, phone_err = resolve_send_phone(order.structured_data, {})
    if phone_err:
        return {"status": "skipped", "reason": phone_err}
    brand = ka.resolve_brand(order.structured_data or {})
    from_phone, sender_source = share_api._resolve_sender(order, brand)
    if not from_phone:
        return {"status": "skipped", "reason": "not_configured"}

    kind = str(payload.get("kind") or "drawing")
    try:
        snapshot = (share_service.build_estimate_snapshot(order)
                    if kind in share_service.SNAPSHOT_KINDS else None)
        row, token = share_service.create_share_token(session, order.id, kind, snapshot=snapshot)
    except share_service.SnapshotTooLargeError:
        return {"status": "skipped", "reason": "snapshot_too_large"}
    text = share_api.share_link_message(order, kind=kind, url=share_consult._public_url(token),
                                        brand=brand)
    sms_event = OrderEvent(
        order_id=order.id, event_type="SHARE_SMS",
        payload={"share_id": row.id, "kind": kind, "status": "in_flight",
                 "source": "consult_fallback", "alimtalk_event_id": event.id,
                 **{k: payload[k] for k in _ROUND_TAGS if k in payload}})
    session.add(sms_event)
    session.commit()  # 링크·앵커를 먼저 굳힌다(벤더 호출 중 죽어도 '보냈다'로 남지 않게)

    error, attempts = share_api._send_sms_with_fallback(
        row.id, to_phone=to_phone, text=text, from_phone=from_phone,
        sender_source=sender_source, brand=brand)
    sms_event.payload = {**sms_event.payload, "status": "sent" if error is None else "failed",
                         "error": error, "attempts": attempts}
    flag_modified(sms_event, "payload")
    if error is not None:
        share_service.revoke_token(row)
    lock_order_row(session, order.id)
    ka.record_share_history(session, order, kind=kind, channel="sms", share_id=row.id,
                            error=error, sent_by=None)
    return {"status": "sent" if error is None else "failed", "error": error,
            "share_id": row.id, "sms_event_id": sms_event.id, "at": now.isoformat()}


def _judge_one(session, event_id: int, now: datetime.datetime,
               lookup: Callable[[str], Optional[str]]) -> str:
    """발송 하나를 잠그고 판정한다. 돌려주는 값은 집계 이름이다."""
    event = (session.query(OrderEvent).filter(OrderEvent.id == event_id)
             .with_for_update().populate_existing().one_or_none())
    consult = ((event.payload or {}).get("consult") if event else None) or {}
    if event is None or consult.get("kakao_result"):
        session.rollback()
        return "skipped"
    try:
        code = lookup(str(consult["message_id"]))
    except Exception as exc:  # 조회 실패는 다음 바퀴에 다시 묻는다
        session.rollback()
        logger.warning("[상담 먼저 문자] 결과 조회 실패 event=%s error=%s", event_id,
                       ka._classify_error(exc))
        return "lookup_failed"

    if code == _DELIVERED:
        _mark(event, kakao_result="delivered", kakao_status=code)
        session.commit()
        return "delivered"
    if code is None or code in _PENDING:
        if event.created_at and now - event.created_at >= GIVE_UP_AFTER:
            _mark(event, kakao_result="unknown", kakao_status=code)
            session.commit()
            return "unknown"
        session.rollback()
        return "pending"

    # 카톡 실패 — 판정을 먼저 굳혀 다른 워커가 다시 보내지 않게 한다.
    _mark(event, kakao_result="failed", kakao_status=code)
    session.commit()
    try:
        outcome = _send_link_sms(session, event, now)
    except Exception as exc:  # 문자 단계가 터져도 판정은 이미 굳었다 — 결과만 남긴다
        session.rollback()
        logger.exception("[상담 먼저 문자] 링크 문자 실패 event=%s", event_id)
        outcome = {"status": "failed", "error": ka._classify_error(exc)}
    event = session.get(OrderEvent, event_id)
    _mark(event, sms_fallback=outcome)
    session.commit()
    logger.info("[상담 먼저 문자] 카톡 실패 code=%s → 문자 %s (order=%s)", code,
                outcome.get("status"), event.order_id)
    return "sms_" + str(outcome.get("status"))


def run_consult_sms_sweep(session, *, now: Optional[datetime.datetime] = None,
              lookup: Optional[Callable[[str], Optional[str]]] = None) -> dict[str, int]:
    """방금 보낸 '상담 먼저' 알림톡들의 카톡 결과를 판정하고, 실패면 링크 문자를 보낸다.

    여러 워커가 동시에 돌아도 한 발송에 문자는 한 번만 나간다 — 이벤트 행을 잠근 채
    ``kakao_result`` 를 먼저 커밋하고 문자를 보낸다.

    Args:
        session: DB 세션(이 함수가 커밋한다).
        now: 기준 시각(테스트 주입, naive UTC).
        lookup: 결과 코드 조회 함수(기본 :func:`ka._solapi_lookup_status`).

    Returns:
        집계 이름별 건수(``delivered``·``pending``·``unknown``·``sms_sent``·``sms_failed`` …).
    """
    now = now or now_utc_naive()
    lookup = lookup or ka._solapi_lookup_status
    counts: dict[str, int] = {}
    for event_id in _candidates(session, now):
        name = _judge_one(session, event_id, now, lookup)
        counts[name] = counts.get(name, 0) + 1
    return counts

"""channel receipt → canonical Order 생성 (CHANNEL-INBOUND-ORDER-01 · ORDER-CREATE-01 경유).

채널 수신 receipt 를 raw ``Order(...)`` 가 아니라 :func:`ORDER-CREATE-01 create_order` 로
정본 생성한다(assignment/event/quest/version/geocode 한 tx). worker 와 recovery-CREATE 가 이
한 함수를 공유하며, **receipt 상태 갱신과 order 생성이 같은 session tx** 에서 일어나 two commit
이 없다(호출자가 최종 commit 소유).

owner 정책: 채널 주문은 사람 actor 가 없으므로 **명시 SALES owner**(recovery 승인 인자) 또는
운영 config(``FOMS_CHANNEL_INBOUND_DEFAULT_OWNER_USER_ID``)로 지정된 **활성 SALES** 사용자만
owner 로 삼는다. 하드코딩 admin fallback 은 없다(default Admin 금지). owner 를 해석할 수 없으면
:class:`ChannelOwnerAbsenceError` 로 신호해 worker 가 receipt 를 pause 한다(owner absence pause).

멱등: receipt 에 이미 ``created_order_id`` 가 있으면 그 order 를 그대로 반환한다(receipt 1개=
주문 1개·중복 0 — key rotation·크래시 후에도 정확히 1회 생성).
"""
from __future__ import annotations

import os
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.channel_inbound import parse_order_text
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.orders.order_create import create_order
from foms.services.orders.order_mutation_policy import normalize_team
from models import ChannelInboundEventLog, Order, User

ENV_DEFAULT_OWNER = "FOMS_CHANNEL_INBOUND_DEFAULT_OWNER_USER_ID"


class ChannelOwnerAbsenceError(RuntimeError):
    """채널 주문 owner(활성 SALES)를 해석할 수 없다 → worker 는 receipt 를 pause 한다."""


class ChannelReceiptParseError(RuntimeError):
    """receipt raw payload 를 주문 필드로 파싱할 수 없다(worker 는 재시도로 계수)."""


def resolve_channel_owner(
    session: Session, *, explicit_owner_user_id: Optional[int] = None
) -> int:
    """채널 주문의 SALES owner user_id 를 해석·검증한다(활성 SALES 만).

    Args:
        session: owner 후보 조회용 세션.
        explicit_owner_user_id: recovery-CREATE 등에서 운영자가 지정한 owner(우선).

    Returns:
        검증된 활성 SALES owner user_id.

    Raises:
        ChannelOwnerAbsenceError: owner 미지정/미존재/비활성/비SALES(하드코딩 admin fallback 없음).
    """
    candidate = explicit_owner_user_id
    if candidate is None:
        raw = (os.environ.get(ENV_DEFAULT_OWNER) or "").strip()
        if not raw:
            raise ChannelOwnerAbsenceError(
                "channel order owner is unresolved (no explicit owner and "
                f"{ENV_DEFAULT_OWNER} is unset) — pausing receipt."
            )
        try:
            candidate = int(raw)
        except ValueError as exc:
            raise ChannelOwnerAbsenceError(f"{ENV_DEFAULT_OWNER} is not an integer.") from exc

    owner = session.get(User, int(candidate))
    if owner is None or not owner.is_active or normalize_team(owner.team) != "SALES":
        raise ChannelOwnerAbsenceError(
            "channel order owner must be an active SALES user (default Admin bypass forbidden)."
        )
    return int(candidate)


def _order_fields_from_receipt(receipt: ChannelInboundEventLog, now: Any) -> dict:
    """receipt raw payload 를 재파싱해 Order scalar 필드 dict 를 만든다(마스킹 전 원본).

    저장된 ``parsed_result`` 는 PII 마스킹본이므로 실제 주문 값은 raw payload 에서 재파싱한다.
    """
    payload = receipt.raw_payload or {}
    entity = payload.get("entity", {}) if isinstance(payload, dict) else {}
    text = entity.get("plainText") or entity.get("message") or ""
    success, data, missing, _masked = parse_order_text(text)
    if not success:
        raise ChannelReceiptParseError(f"missing fields: {', '.join(missing)}")
    return {
        "received_date": get_today_kst().strftime("%Y-%m-%d"),
        "customer_name": data.get("customer_name"),
        "phone": data.get("phone"),
        "address": data.get("address"),
        "product": data.get("product", "-"),
        "status": "RECEIVED",
    }


def create_order_from_receipt(
    session: Session,
    receipt: ChannelInboundEventLog,
    *,
    owner_user_id: int,
    actor_user_id: Optional[int] = None,
    now: Optional[Any] = None,
) -> Order:
    """receipt 를 canonical Order 로 생성하고 receipt 를 CREATED 로 전이한다(멱등·단일 tx).

    이미 생성됐으면(``created_order_id`` 존재) 그 order 를 반환한다(중복 0). 호출자가 commit 을
    소유하므로 receipt 갱신과 order 생성이 원자적이다(two commit 0).

    Args:
        session: business tx 세션(호출자 소유, 커밋 미수행).
        receipt: 대상 :class:`ChannelInboundEventLog`.
        owner_user_id: 확정된 활성 SALES owner(:func:`resolve_channel_owner`).
        actor_user_id: event author/assigned_by. 기본은 owner(채널 SALES 담당 self).
        now: 테스트용 시각 주입.

    Returns:
        생성(또는 기존) :class:`Order`.

    Raises:
        ChannelReceiptParseError: raw payload 재파싱 실패.
    """
    now = now or now_utc_naive()
    if receipt.created_order_id is not None:
        return session.get(Order, receipt.created_order_id)

    actor = actor_user_id if actor_user_id is not None else owner_user_id
    order_fields = _order_fields_from_receipt(receipt, now)
    order = create_order(
        session,
        actor_user_id=actor,
        owner_user_id=owner_user_id,
        order_fields=order_fields,
        is_erp_order=True,
        now=now,
    )
    receipt.created_order_id = order.id
    receipt.created_order_ref = f"ORD-{order.id}"
    receipt.receipt_state = "CREATED"
    receipt.status = "created"
    receipt.processed_at = now
    session.flush()
    return order

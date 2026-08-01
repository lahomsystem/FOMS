"""Canonical Order 생성자 (ORDER-CREATE-01).

주문 생성을 **단일 서비스 함수**로 일원화한다. legacy ``/add`` 폼 어댑터와 JSON(ERP)
create 어댑터가 raw ``Order(...)`` 를 직접 조립하지 않고 :func:`create_order` 를 경유한다.
한 transaction 안에서 아래를 원자적으로 조립한다(호출자가 ``session.commit()`` 소유):

* ``mutation_version = 1`` (REV-00 신규 생성 규약).
* SALES **owner 배정**(:class:`~models.OrderAssignment`, ``source=INITIAL_OWNER``) —
  ASSIGNMENT-00 user-ID row 정본. 이름 배열이 아니라 이 row 가 authorization 근거다.
* 생성 **event**(``ORDER_CREATED`` :class:`~models.OrderEvent`).
* ERP 주문이면: RECEIVED **quest seed**(STATE-QUEST 템플릿), item **UUID identity**
  발급(ITEM-ID-00), server-authoritative **totals 재계산**(DATA-01), flat column projection.
* 주소가 있으면 **GEOCODE outbox** 예약(DATA-MEASUREMENT-01) — postcommit 직접 지오코드
  폴백 금지, business tx 안에서 typed side-effect 행 1개로 예약.

owner 정책(:func:`resolve_order_owner`): STAFF 는 self default owner(본인)로만 생성하고
(타 STAFF 명의 생성 금지), Admin/Manager 는 explicit active SALES owner 를 지정한다
(admin 자신을 owner 로 지정 금지).
"""
from __future__ import annotations

import copy
import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.order_geocode_outbox import enqueue_order_address_geocode
from foms.services.orders.erp_policy_quests import create_quest_from_template
from foms.services.orders.item_identity import get_or_create_identity
from foms.services.orders.order_mutation_policy import normalize_team
from foms.services.orders.structured_form_projection import recompute_totals
from models import Order, OrderAssignment, OrderEvent, User

#: 주소 없음/placeholder 로 취급해 geocode 를 예약하지 않는 값.
_BLANK_ADDRESSES = frozenset({"", "-"})
CREATED_EVENT = "ORDER_CREATED"


class OrderCreateError(RuntimeError):
    """ORDER-CREATE-01 계약 위반 베이스(호출자가 status_code 로 HTTP 매핑)."""

    status_code = 400
    error_code = "ORDER_CREATE_ERROR"


class OwnerPolicyError(OrderCreateError):
    """owner 정책 위반(admin self-owner·타 STAFF 명의·비활성/비SALES owner). 403."""

    status_code = 403
    error_code = "ORDER_OWNER_POLICY"


def resolve_order_owner(
    session: Session, *, actor: Any, requested_owner_user_id: Optional[int]
) -> int:
    """생성 주문의 SALES owner user_id 를 role 정책으로 판정한다(§ORDER-CREATE-01).

    * STAFF: 항상 self(본인 id). ``requested_owner_user_id`` 가 본인과 다르면 타 STAFF
      명의 생성으로 보고 거부한다.
    * ADMIN/MANAGER: ``requested_owner_user_id`` 필수. 본인 지정(admin owner) 금지,
      대상은 **활성 SALES** 사용자여야 한다(team 은 MEASURE→SALES 정규화).

    Args:
        session: DB 세션(owner 후보 조회용).
        actor: 요청 주체 User(``role``/``id`` 필요).
        requested_owner_user_id: 폼/JSON 이 지정한 owner user_id(없으면 None).

    Returns:
        확정된 owner user_id.

    Raises:
        OwnerPolicyError: role 부재·타 STAFF 명의·admin self-owner·비활성/비SALES owner.
    """
    role = (getattr(actor, "role", None) or "").strip().upper()
    actor_id = int(getattr(actor, "id"))
    requested = None if requested_owner_user_id is None else int(requested_owner_user_id)

    if role == "STAFF":
        if requested is not None and requested != actor_id:
            raise OwnerPolicyError("STAFF는 본인 명의로만 주문을 생성할 수 있습니다.")
        return actor_id

    if role in ("ADMIN", "MANAGER"):
        if requested is None:
            raise OwnerPolicyError("영업(SALES) 담당자를 지정해야 합니다.")
        if requested == actor_id:
            raise OwnerPolicyError("관리자는 자신을 영업 담당자로 지정할 수 없습니다.")
        owner = session.get(User, requested)
        if owner is None or not owner.is_active or normalize_team(owner.team) != "SALES":
            raise OwnerPolicyError("활성 영업(SALES) 담당자만 지정할 수 있습니다.")
        return requested

    raise OwnerPolicyError("주문을 생성할 권한이 없습니다.")


def _prepare_structured(
    structured_data: Optional[dict], owner_user_id: int, now: datetime.datetime
) -> Optional[dict]:
    """ERP structured_data 를 생성용으로 정규화한다(RECEIVED stage·quest seed·server totals).

    원본을 복사(``copy.deepcopy``)해 반환하며 호출자의 입력을 건드리지 않는다. workflow
    stage 가 없으면 RECEIVED 로 seed 하고, 그 stage 의 quest 가 없으면 템플릿으로 seed 한다.
    """
    sd = copy.deepcopy(structured_data or {})
    workflow = sd.setdefault("workflow", {})
    stage = (workflow.get("stage") or "RECEIVED").strip() or "RECEIVED"
    workflow["stage"] = stage
    workflow.setdefault("stage_updated_at", now.isoformat())

    recompute_totals(sd)

    quests = sd.get("quests")
    if not isinstance(quests, list):
        quests = []
    has_stage_quest = any(
        isinstance(q, dict) and q.get("stage") == stage for q in quests
    )
    if not has_stage_quest:
        seeded = create_quest_from_template(stage, str(owner_user_id), sd)
        if seeded:
            quests.append(seeded)
    sd["quests"] = quests
    return sd


def _mint_item_identities(session: Session, order_id: int, sd: dict) -> None:
    """structured_data['items'] 각 슬롯에 안정 UUID identity 를 발급한다(ITEM-ID-00, 멱등)."""
    items = sd.get("items")
    if not isinstance(items, list):
        return
    for index, item in enumerate(items):
        if isinstance(item, dict):
            get_or_create_identity(session, order_id, index)


def create_order(
    session: Session,
    *,
    actor_user_id: int,
    owner_user_id: int,
    order_fields: dict[str, Any],
    structured_data: Optional[dict] = None,
    is_erp_order: bool = False,
    now: Optional[datetime.datetime] = None,
) -> Order:
    """canonical Order 를 한 tx 로 조립한다(호출자가 commit).

    scalar 컬럼(``order_fields``) 위에 version=1, SALES owner 배정, ORDER_CREATED event,
    (ERP 면) RECEIVED quest seed·item identity·server totals·flat projection, 그리고
    주소가 있으면 GEOCODE outbox 예약을 원자적으로 더한다. 어느 단계가 실패하면 호출자
    tx 롤백으로 전부 되돌아간다(부분 생성 없음).

    Args:
        session: business transaction 세션(호출자 소유, 커밋 미수행).
        actor_user_id: 생성 주체 user id(event author·배정 assigned_by).
        owner_user_id: SALES owner user id(:func:`resolve_order_owner` 로 확정된 값).
        order_fields: :class:`~models.Order` scalar 컬럼 kwargs(customer_name/phone/... ).
        structured_data: ERP 주문의 구조화 데이터(legacy 폼이면 None).
        is_erp_order: ERP 주문이면 True(quest/item/projection 을 적용).
        now: 테스트용 시각 주입(기본 now_utc_naive()).

    Returns:
        flush 된 :class:`~models.Order` (id 채워짐; 커밋은 호출자).
    """
    now = now or now_utc_naive()
    sd = _prepare_structured(structured_data, owner_user_id, now) if is_erp_order else None

    order = Order(
        **order_fields,
        is_erp_order=is_erp_order,
        structured_data=sd,
        mutation_version=1,
    )
    if is_erp_order:
        order.structured_schema_version = 1
        order.structured_updated_at = now
    session.add(order)
    session.flush()  # order.id 확보(배정/event/identity FK 참조)

    if is_erp_order and sd is not None:
        _mint_item_identities(session, order.id, sd)
        sync_erp_flat_columns(order, sd)

    session.add(
        OrderAssignment(
            order_id=order.id, domain="SALES", user_id=owner_user_id,
            source="INITIAL_OWNER", active=True, assigned_at=now,
            assigned_by_user_id=actor_user_id,
        )
    )
    session.add(
        OrderEvent(
            order_id=order.id, event_type=CREATED_EVENT,
            payload={"owner_user_id": owner_user_id, "status": order.status},
            created_by_user_id=actor_user_id, created_at=now,
        )
    )
    session.flush()

    address = (order.address or "").strip()
    if address not in _BLANK_ADDRESSES:
        enqueue_order_address_geocode(
            session, order, address=address, actor_user_id=actor_user_id, now=now
        )
    return order


__all__ = [
    "OrderCreateError",
    "OwnerPolicyError",
    "CREATED_EVENT",
    "resolve_order_owner",
    "create_order",
]

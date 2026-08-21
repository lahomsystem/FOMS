"""Order copy service (ORDER-COPY-01) — fresh-identity duplication via create_order.

원본 주문을 **explicit form allowlist** 필드만 골라 새 주문으로 복제한다. 상태·버전·item
id·owner·quest·삭제·일정 등 서버 소유/운영 상태는 원본에서 복제하지 않고
:func:`~foms.services.orders.order_create.create_order` 가 새로 초기화한다(mutation_version=1,
SALES owner 배정, RECEIVED quest seed, item UUID identity, GEOCODE outbox 를 한 tx). 다건
복사는 Order ID 정렬 lock 으로 **all-or-none**(하나라도 없으면 전체 abort·partial commit 0)
이며, 배치 안에서는 ID 정렬 순서(결정적 key)로 처리해 교차 lock deadlock 이 없다.

금지: raw ``Order()`` column/blob clone, partial commit, 첨부(attachment)/일정(schedule) 복사.
"""

from __future__ import annotations

import copy
import datetime
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_kst, now_utc_naive
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.orders.order_create import create_order, resolve_order_owner
from models import Order, User

#: structured_data 에서 복사하지 않는 서버 소유/운영 상태 키. workflow/quests/totals 는
#: create_order 가 RECEIVED 로 새로 seed 하므로 여기서 지운다(원본 stage 승계 금지).
#: schedule(실측·시공 일정)은 "일정 복사 금지" 규약에 따라 제거한다.
_STRUCTURED_DROP_KEYS = frozenset(
    {
        "workflow",
        "assignments",
        "shipment",
        "schedule",
        "quests",
        "drawing",
        "blueprint",
        "drawing_status",
        "drawing_transferred",
        "drawing_confirmed_at",
        "drawing_confirmed_by",
        "drawing_current_files",
        "drawing_transfer_history",
        "last_drawing_transfer",
        "drawing_assignees",
        "drawing_wizard",
        "estimate_preview",
        "channeltalk_push",
        "channeltalk_push_drawing",
        "channeltalk_push_estimate",
        "channeltalk_push_measure_room",
    }
)

#: meta 하위에서 복사하지 않는 초안/견적 연결 토큰(새 주문은 draft/견적 링크를 승계하지 않음).
_META_DROP_KEYS = frozenset(
    {
        "draft",
        "draft_token",
        "wdc_estimate_id",
        "wdcalculator_estimate_id",
        "estimate_id",
    }
)


class OrderCopyError(RuntimeError):
    """복사 대상 주문이 없음(soft-deleted 포함)·빈 선택. 404 로 매핑(호출자)."""

    status_code = 404
    error_code = "ORDER_COPY_NOT_FOUND"


def _ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_product_name(structured_data: dict[str, Any]) -> str:
    items = structured_data.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                name = (item.get("product_name") or item.get("name") or "").strip()
                if name:
                    return name
    return ""


def _flat_customer_name(order: Order, structured_data: dict[str, Any]) -> str:
    customer = _ensure_dict(_ensure_dict(structured_data.get("parties")).get("customer"))
    name = (customer.get("name") or getattr(order, "customer_name", "") or "").strip()
    return name or "ERP Order"


def _flat_phone(order: Order, structured_data: dict[str, Any]) -> str:
    customer = _ensure_dict(_ensure_dict(structured_data.get("parties")).get("customer"))
    phone = (customer.get("phone") or getattr(order, "phone", "") or "").strip()
    return phone or "000-0000-0000"


def _flat_address(order: Order, structured_data: dict[str, Any]) -> str:
    site = _ensure_dict(structured_data.get("site"))
    address = (
        site.get("address_full")
        or site.get("address_main")
        or getattr(order, "address", "")
        or ""
    ).strip()
    return address or "-"


def _flat_product(order: Order, structured_data: dict[str, Any]) -> str:
    product = (_first_product_name(structured_data) or getattr(order, "product", "") or "").strip()
    return product or "ERP Order"


def _copy_structured_data(original: Order, copied_at: datetime.datetime) -> dict[str, Any]:
    """ERP structured_data 를 복사용으로 정규화한다(운영 상태 제거·meta 재작성).

    ``copy.deepcopy`` 로 원본을 격리한 뒤 서버 소유/운영 키를 제거한다. workflow·quest·
    totals 는 남기지 않고 create_order 가 RECEIVED 로 새로 seed 한다.

    Args:
        original: 복사 원본 주문.
        copied_at: 복사 시각(meta.copied_at 표기용, KST business 시각).

    Returns:
        복사 대상 필드만 남은 structured_data dict(create_order 로 넘길 값).
    """
    sd = copy.deepcopy(_ensure_dict(getattr(original, "structured_data", None)))
    for key in _STRUCTURED_DROP_KEYS:
        sd.pop(key, None)

    meta = copy.deepcopy(_ensure_dict(sd.get("meta")))
    for key in _META_DROP_KEYS:
        meta.pop(key, None)
    meta.update(
        {
            "draft": False,
            "created_via": "ORDER_COPY",
            "copied_from_order_id": original.id,
            "copied_at": copied_at.isoformat(),
        }
    )
    sd["meta"] = meta
    return sd


def _common_form_fields(original: Order, local: datetime.datetime) -> dict[str, Any]:
    """ERP·legacy 공통 form allowlist scalar(일정·재무·상태 등 서버 소유 컬럼 제외)."""
    return dict(
        received_date=local.strftime("%Y-%m-%d"),
        received_time=local.strftime("%H:%M"),
        options=copy.deepcopy(getattr(original, "options", None)),
        status="RECEIVED",
        is_regional=bool(getattr(original, "is_regional", False)),
        is_self_measurement=bool(getattr(original, "is_self_measurement", False)),
        is_cabinet=bool(getattr(original, "is_cabinet", False)),
        construction_type=getattr(original, "construction_type", None),
        regional_memo=getattr(original, "regional_memo", None),
        shipping_fee=getattr(original, "shipping_fee", None) or 0,
    )


def _copy_one(
    session: Session,
    original: Order,
    *,
    actor_user_id: int,
    owner_user_id: int,
    local: datetime.datetime,
    event_now: datetime.datetime,
) -> Order:
    """원본 한 건을 create_order 경유 fresh-identity 새 주문으로 복사한다(flush 됨)."""
    fields = _common_form_fields(original, local)
    if is_erp_order_record(original):
        sd = _copy_structured_data(original, local)
        fields.update(
            customer_name=_flat_customer_name(original, sd),
            phone=_flat_phone(original, sd),
            address=_flat_address(original, sd),
            product=_flat_product(original, sd),
            notes=getattr(original, "notes", None),
            raw_order_text=getattr(original, "raw_order_text", None),
            structured_confidence=getattr(original, "structured_confidence", None),
        )
        return create_order(
            session,
            actor_user_id=actor_user_id,
            owner_user_id=owner_user_id,
            order_fields=fields,
            structured_data=sd,
            is_erp_order=True,
            now=event_now,
        )

    original_name = getattr(original, "customer_name", "") or ""
    original_notes = getattr(original, "notes", None) or ""
    fields.update(
        customer_name=f"[복사: 원본 #{original.id}] {original_name}",
        phone=getattr(original, "phone", "") or "",
        address=getattr(original, "address", "") or "",
        product=getattr(original, "product", "") or "",
        notes=f"원본 주문 #{original.id} 에서 복사됨.\n---\n{original_notes}",
    )
    return create_order(
        session,
        actor_user_id=actor_user_id,
        owner_user_id=owner_user_id,
        order_fields=fields,
        is_erp_order=False,
        now=event_now,
    )


def copy_orders_batch(
    session: Session,
    *,
    actor: User,
    order_ids: Sequence[int],
    requested_owner_user_id: Optional[int] = None,
    now: Optional[datetime.datetime] = None,
) -> list[tuple[int, Order]]:
    """선택 주문을 fresh-identity 새 주문으로 복사한다 — sorted lock all-or-none.

    Order ID 오름차순으로 원본을 ``FOR UPDATE`` lock 해(교차 입력 순서라도 deadlock 0)
    일관 스냅샷을 읽고, 요청 id 중 하나라도 조회되지 않으면(soft-deleted 포함) 전체를
    abort 한다(partial commit 0). 각 복사는 create_order 를 경유해 mutation_version=1·
    fresh SALES owner·RECEIVED quest·item UUID·GEOCODE outbox 를 새로 부여받는다. 호출자가
    ``session.commit()`` 을 소유한다.

    Args:
        session: business transaction 세션(호출자 소유, 커밋 미수행).
        actor: 복사 주체 User(role/id — owner 정책 판정).
        order_ids: 복사할 원본 주문 id 목록(중복 제거·정렬됨).
        requested_owner_user_id: Admin/Manager 가 지정하는 SALES owner(STAFF 는 self).
        now: 접수일자/시각(KST business) 주입용 테스트 훅(기본 now_kst()).

    Returns:
        ``[(original_order_id, 복사된 Order), ...]`` (원본 id 오름차순).

    Raises:
        OrderCopyError: 빈 선택이거나 조회되지 않는 원본 id 가 하나라도 있음(404).
        OwnerPolicyError: owner 정책 위반(admin self·타 STAFF·비활성/비SALES·미지정, 403).
    """
    local = now or now_kst()
    event_now = now_utc_naive()
    ids = sorted({int(oid) for oid in order_ids})
    if not ids:
        raise OrderCopyError("복사할 주문을 선택하세요.")

    owner_user_id = resolve_order_owner(
        session, actor=actor, requested_owner_user_id=requested_owner_user_id
    )

    originals = {
        order.id: order
        for order in (
            session.query(Order)
            .filter(Order.id.in_(ids), Order.not_deleted_filter())
            .order_by(Order.id.asc())
            .with_for_update()
            .all()  # perf-ok: bounded selection batch, id 정렬 lock
        )
    }
    missing = [oid for oid in ids if oid not in originals]
    if missing:
        raise OrderCopyError(f"복사할 수 없는 주문입니다: {missing}")

    results: list[tuple[int, Order]] = []
    for oid in ids:  # 정렬 순서(결정적 key)로 처리 — 배치 내 deadlock 0
        copied = _copy_one(
            session,
            originals[oid],
            actor_user_id=actor.id,
            owner_user_id=owner_user_id,
            local=local,
            event_now=event_now,
        )
        results.append((oid, copied))
    return results


__all__ = ["OrderCopyError", "copy_orders_batch"]

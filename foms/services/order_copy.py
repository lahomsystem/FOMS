"""Order copy service (ORDER-COPY-01) — fresh-identity duplication via create_order.

원본 주문에서 **넣을 것만 골라**(허용 목록) 새 주문으로 복제한다. ``structured_data`` 는 아래
``_*_COPY_KEYS`` 에 적힌 칸만 옮기고, 적히지 않은 칸은 — 앞으로 새로 생기는 칸까지 — 옮기지 않는다
(설계서 2026-11-20 6.3 · M14). 빼는 목록이던 시절에는 결제 확인 · AS 기록 · 알림톡 발송 이력 · 제품별
날짜가 새 주문으로 흘러, 복사본이 AS 화면에 뜨고 옛 날짜로 일정 줄이 생겼다.

상태·버전·item id·owner·quest·일정 등 서버 소유/운영 상태는
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

#: 고객 · 발주사 · 주문한 사람 · 담당 뱃지에서 옮기는 칸. 협력사 직원 표식(``partner_user_id`` 등)은 없다.
_PARTY_COPY_KEYS: dict[str, tuple[str, ...]] = {
    "customer": ("name", "phone", "phone2"),
    "orderer": ("name",),
    "buyer": ("name", "phone"),
    "manager": ("name", "names", "phone"),
}

#: 주소(특이사항 포함).
_SITE_COPY_KEYS = ("address_full", "address_main", "address_detail", "address_note", "zip_code")

#: 제품 본문(규격 · 색 · 옵션 · 수량 · 가격 · 규격 계산 스냅샷). 날짜 · 첨부 · 취소 · uid · 네이버 금액은 없다 —
#: 날짜가 넘어가면 새 주문에 일정 줄이 생겨 출고판에 옛 날짜로 뜬다.
_ITEM_COPY_KEYS = (
    "product_name", "name",
    "spec", "spec_rows", "spec_width", "spec_depth", "spec_height",
    "width", "depth", "height",
    "internal", "color", "option_detail", "handle", "misc", "options",
    "quantity", "price", "raw_price", "extra_input",
    "pricing",
)

#: 전화 · 주소 특이사항. 실측 · 시공 메모는 그 주문의 작업 기록이라 없다.
_NOTES_COPY_KEYS = ("phone_note", "address_note")

#: 라홈시스템 표식. 긴급 · 해피콜 · 견적 수정 표시는 그 주문의 사정이라 없다.
_FLAGS_COPY_KEYS = ("factory2",)

#: 값(할인 · 자유입력)만. 예약금 · 결제 확인 · 현금영수증은 없다.
_PAYMENT_COPY_KEYS = ("discount", "discounts", "free_input")


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


def _pick(source: Any, keys: Sequence[str]) -> dict[str, Any]:
    """dict 에서 ``keys`` 에 있는 칸만 깊은 복사로 골라 낸다(dict 가 아니면 빈 dict)."""
    if not isinstance(source, dict):
        return {}
    return {key: copy.deepcopy(source[key]) for key in keys if key in source}


def _copy_parties(parties: Any) -> dict[str, Any]:
    """고객 · 발주사 · 주문한 사람 · 담당 뱃지만. 옛 주문의 스칼라 값(이름 글)은 그대로 옮긴다."""
    out: dict[str, Any] = {}
    for role, keys in _PARTY_COPY_KEYS.items():
        value = _ensure_dict(parties).get(role)
        if isinstance(value, dict):
            out[role] = _pick(value, keys)
        elif isinstance(value, (str, int)) and not isinstance(value, bool):
            out[role] = value
    return out


def _copy_structured_data(original: Order, copied_at: datetime.datetime) -> dict[str, Any]:
    """ERP structured_data 에서 넣을 것만 골라 새 dict 를 만든다(허용 목록 · meta 는 새로 씀).

    원본은 건드리지 않는다. 허용 목록 밖의 칸(결제 확인 · 정산 · AS · 알림톡 · 채널톡 이력 · 통화 · 제작 ·
    시공 기록 · 네이버 · 협력사 표식 · 도면 · 일정 · workflow · quests …)은 옮기지 않고, workflow · quest ·
    totals 는 create_order 가 RECEIVED 로 새로 seed 한다.

    Args:
        original: 복사 원본 주문.
        copied_at: 복사 시각(meta.copied_at 표기용, KST business 시각).

    Returns:
        복사 대상 필드만 담은 structured_data dict(create_order 로 넘길 값).
    """
    source = _ensure_dict(getattr(original, "structured_data", None))
    sd: dict[str, Any] = {}
    if isinstance(source.get("parties"), dict):
        sd["parties"] = _copy_parties(source["parties"])
    if isinstance(source.get("site"), dict):
        sd["site"] = _pick(source["site"], _SITE_COPY_KEYS)
    if isinstance(source.get("items"), list):
        sd["items"] = [
            _pick(item, _ITEM_COPY_KEYS) for item in source["items"] if isinstance(item, dict)
        ]
    notes = source.get("notes")
    if isinstance(notes, dict):
        sd["notes"] = _pick(notes, _NOTES_COPY_KEYS)
    elif isinstance(notes, str):
        # 마법사 · 협력사 주문은 접수 메모를 글 한 칸으로 둔다.
        sd["notes"] = notes
    if isinstance(source.get("flags"), dict):
        sd["flags"] = _pick(source["flags"], _FLAGS_COPY_KEYS)
    if isinstance(source.get("payment"), dict):
        sd["payment"] = _pick(source["payment"], _PAYMENT_COPY_KEYS)
    sd["meta"] = {
        "draft": False,
        "created_via": "ORDER_COPY",
        "copied_from_order_id": original.id,
        "copied_at": copied_at.isoformat(),
    }
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

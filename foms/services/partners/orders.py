"""PARTNER-02: 협력사 주문 등록 · 협력사 화면용 목록/상세.

협력사가 영업 · 실측 · 초안 도면까지 하고 넘긴다. 우리 쪽에서는 이 주문이:

* ``orders.partner_org_id`` = 협력사, ``structured_data.source`` = ``PARTNER``,
  발주사(``parties.orderer.name``) = 협력사 이름.
* 실측 단계(MEASURE) · 주관 팀 CS · ``measurement_completed`` 로 들어온다. CS 가 내용을 보고 기존
  "도면 단계로 넘기기"를 누르면 도면으로 간다. 새 단계 코드는 만들지 않는다.
* 영업 담당은 협력사를 맡는 우리 직원(``partner_orgs.owner_user_id``)이다.
* 협력사가 낸 원문은 ``structured_data.partner_intake`` 에 등록 시점 사본으로 남는다(도면팀이
  ``items`` 를 고쳐도 원문은 그대로 — 실측 책임을 가리는 근거).
* 실측일은 ``schedule.measurement`` 에 넣지 않는다 — 우리 실측 일정표에 협력사 실측이 섞이지 않게.
"""
from __future__ import annotations

import copy
from typing import Any

from foms.services.audit_writer import normalize_security_detail
from foms.services.auth.partner_scope import PARTNER_SOURCE_MARKER
from foms.services.datetime_kst import get_today_kst, now_kst
from foms.services.orders.order_create import create_order
from foms.services.notifications.recipients import fan_out_new_notification
from models import Notification, Order, PartnerOrg, SecurityLog, User

PARTNER_ORDER_NOTIFICATION_TYPE = "PARTNER_ORDER_CREATED"

MAX_ITEMS = 30
_TEXT_LIMIT = 500

# 협력사 화면의 쉬운 단계(내부 단계 코드를 묶는다). 스펙 §5.1.
_PARTNER_STAGE_LABELS = {
    "RECEIVED": "접수 확인 중",
    "MEASURE": "접수 확인 중",
    "DRAWING": "도면 작업 중",
    "CONFIRM": "도면 확인 대기",
    "PRODUCTION": "생산 중",
    "CONSTRUCTION": "시공 예정",
    "CS": "완료",
    "COMPLETED": "완료",
    "AS": "AS 진행 중",
    "AS_RECEIVED": "AS 진행 중",
    "AS_COMPLETED": "완료",
}


class PartnerOrderError(ValueError):
    """협력사 화면에 그대로 보여 줄 수 있는 입력 오류."""


def partner_stage_label(stage_code: Any, as_axis_status: Any = None) -> str:
    """쉬운 단계. AS 건이 열려 있으면(접수·진행) 단계와 무관하게 "AS 진행 중"."""
    if str(as_axis_status or "").upper() in ("RECEIVED", "IN_PROGRESS"):
        return "AS 진행 중"
    return _PARTNER_STAGE_LABELS.get(str(stage_code or "").upper(), "접수 확인 중")


def _text(value: Any, limit: int = _TEXT_LIMIT) -> str:
    return str(value if value is not None else "").strip()[:limit]


def _dim(value: Any) -> str:
    """치수 칸 — 숫자만 아니어도 받는다(현장 표기 그대로). 길이만 자른다."""
    return _text(value, 20)


def _clean_items(raw_items: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        raise PartnerOrderError("품목을 하나 이상 넣어 주세요.")
    items: list[dict[str, Any]] = []
    for raw in raw_items[:MAX_ITEMS]:
        if not isinstance(raw, dict):
            continue
        name = _text(raw.get("product_name"), 100)
        if not name:
            continue
        items.append({
            "product_name": name,
            "spec_rows": [{
                "spec_width": _dim(raw.get("width")),
                "spec_depth": _dim(raw.get("depth")),
                "spec_height": _dim(raw.get("height")),
            }],
            "quantity": _text(raw.get("quantity"), 10) or "1",
            "misc": _text(raw.get("memo")),
        })
    if not items:
        raise PartnerOrderError("품목을 하나 이상 넣어 주세요.")
    return items


def _require_owner(db, org: PartnerOrg) -> User:
    owner = (
        db.query(User).filter(User.id == org.owner_user_id).first()
        if org.owner_user_id else None
    )
    if owner is None or not owner.is_active:
        # 관리자가 담당 직원을 정하기 전에는 받지 않는다(담당 없는 주문이 생기지 않게).
        raise PartnerOrderError("우리 쪽 담당자가 아직 정해지지 않았습니다. 담당자에게 문의해 주세요.")
    return owner


def create_partner_order(db, user: User, org: PartnerOrg, payload: Any) -> Order:
    """협력사 주문을 만든다(호출자가 commit).

    Args:
        user: 등록하는 협력사 계정.
        org: 그 계정의 협력사(활성 확인은 문지기가 했다).
        payload: ``customer_name``·``customer_phone``·``address``·``items``·``memo``·``measured_on``.
    """
    data = payload if isinstance(payload, dict) else {}
    customer_name = _text(data.get("customer_name"), 50)
    customer_phone = _text(data.get("customer_phone"), 30)
    address = _text(data.get("address"), 300)
    if not customer_name or not customer_phone or not address:
        raise PartnerOrderError("고객 이름 · 연락처 · 현장 주소를 넣어 주세요.")
    items = _clean_items(data.get("items"))
    memo = _text(data.get("memo"), 2000)
    measured_on = _text(data.get("measured_on"), 10)
    owner = _require_owner(db, org)

    submitted_at = now_kst()
    intake = {
        "partner_org_id": org.id,
        "partner_name": org.name,
        "submitted_by_user_id": user.id,
        "submitted_by_name": user.name,
        "submitted_at": submitted_at.isoformat(),
        "customer": {"name": customer_name, "phone": customer_phone},
        "address": address,
        "measured_on": measured_on or None,
        "items": copy.deepcopy(items),
        "memo": memo,
    }
    sd: dict[str, Any] = {
        "source": PARTNER_SOURCE_MARKER,
        "parties": {
            "customer": {"name": customer_name, "phone": customer_phone},
            "orderer": {"name": org.name},
            "manager": {"name": owner.name},
        },
        "site": {"address_full": address},
        "items": items,
        "workflow": {"stage": "MEASURE"},
        "assignments": {"owner_team": "CS"},
        "flags": {},
        "notes": memo,
        "meta": {"created_via": "PARTNER_PORTAL"},
        "partner_intake": intake,
    }
    order = create_order(
        db,
        actor_user_id=user.id,
        owner_user_id=owner.id,
        order_fields=dict(
            received_date=get_today_kst().strftime("%Y-%m-%d"),
            received_time=submitted_at.strftime("%H:%M"),
            customer_name=customer_name,
            phone=customer_phone,
            address=address,
            product=items[0]["product_name"],
            options=None,
            notes=memo or None,
            status="MEASURE",
            raw_order_text="",
            structured_confidence=None,
            partner_org_id=org.id,
            measurement_completed=True,
        ),
        structured_data=sd,
        is_erp_order=True,
    )
    # 같은 트랜잭션에 감사 1줄(누가 · 어느 협력사로 · 몇 번 주문을).
    db.add(SecurityLog(
        user_id=user.id,
        message=f"협력사 주문 등록: #{order.id} ({org.name})",
        action="PARTNER_ORDER_CREATED",
        target_type="order",
        target_id=order.id,
        detail=normalize_security_detail({"partner_org_id": org.id}),
    ))
    # 우리 쪽이 새 협력사 주문을 놓치지 않게 — CS 팀 + 이 협력사를 맡은 영업 직원 알림(벨 목록).
    # 협력사 주문은 실측일이 없어 실측 화면에 뜨지 않으므로 알림이 접수 신호다.
    notification = Notification(
        order_id=order.id,
        notification_type=PARTNER_ORDER_NOTIFICATION_TYPE,
        target_team="CS",
        target_user_id=owner.id,
        title="협력사 새 주문",
        message=f"[{org.name}] 주문 #{order.id} ({customer_name}) 접수 — 내용 확인 후 도면 단계로 넘겨 주세요.",
        created_by_user_id=user.id,
        created_by_name=f"{user.name} (협력사)",
    )
    db.add(notification)
    db.flush()
    fan_out_new_notification(db, notification, actor_user_id=user.id)
    return order


def list_partner_orders(db, org_id: int, *, limit: int = 200) -> list[dict[str, Any]]:
    """협력사 화면 목록 — 자기 협력사의 운영 주문만(삭제 · 초안 제외), 최신순."""
    rows = (
        db.query(
            Order.id, Order.customer_name, Order.address, Order.received_date,
            Order.erp_stage_code, Order.erp_construction_date, Order.as_axis_status,
        )
        .filter(Order.partner_org_id == org_id, Order.active_filter())
        .order_by(Order.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "customer_name": r.customer_name,
            "address": r.address,
            "received_date": r.received_date,
            "stage_label": partner_stage_label(r.erp_stage_code, r.as_axis_status),
            "construction_date": r.erp_construction_date,
        }
        for r in rows
    ]


def partner_order_detail(order: Order, attachments: list[Any]) -> dict[str, Any]:
    """협력사 화면 상세 — 등록 원문 · 쉬운 단계 · 시공일 · 파일(금액 · 내부 메모 없음)."""
    sd = order.structured_data or {}
    intake = sd.get("partner_intake") or {}
    return {
        "id": order.id,
        "stage_label": partner_stage_label(order.erp_stage_code, order.as_axis_status),
        "construction_date": order.erp_construction_date,
        "intake": intake,
        "attachments": attachments,
    }

"""PARTNER-02: 협력사 주문 등록 · 협력사 화면용 목록/상세.

협력사가 영업 · 실측 · 초안 도면까지 하고 넘긴다. 우리 쪽에서는 이 주문이:

* ``orders.partner_org_id`` = 협력사, ``structured_data.source`` = ``PARTNER``,
  발주사(``parties.orderer.name``) = 협력사 이름.
* 실측 단계(MEASURE) · 주관 팀 CS · ``measurement_completed`` 로 들어온다. CS 가 내용을 보고 기존
  "도면 단계로 넘기기"를 누르면 도면으로 간다. 새 단계 코드는 만들지 않는다.
* 담당은 주문을 올린 협력사 직원이다(스펙 §16 — ``foms/services/partners/manager.py``). 우리 쪽은 CS 팀이 챙긴다.
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
from foms.services.partners.manager import manager_party
from models import Notification, Order, PartnerOrg, SecurityLog, User

PARTNER_ORDER_NOTIFICATION_TYPE = "PARTNER_ORDER_CREATED"

MAX_ITEMS = 30
MAX_SPEC_ROWS = 20
DIM_LIMIT = 100
_TEXT_LIMIT = 500
SPEC_KEYS = ("spec_width", "spec_depth", "spec_height")
# 제품 속성 다섯 칸 — 우리 주문 화면과 같은 키(static/js/orders/erp-order-shared.js 제품 속성 시트).
ATTRIBUTE_KEYS = ("internal", "color", "option_detail", "handle", "misc")

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
    """치수 칸 — 숫자만 아니어도 받는다(복합 폭 ``5700(2402+1864+1434)`` 등 현장 표기 그대로). 길이만 자른다."""
    return _text(value, DIM_LIMIT)


def _clean_spec_rows(raw: dict[str, Any]) -> list[dict[str, str]]:
    """품목 규격 줄들. 새 모양 ``spec_rows=[{spec_width,...}]``, 옛 모양 ``width/depth/height`` 둘 다 받는다.

    옛 모양은 하루 캐시된 옛 화면 스크립트가 보낼 수 있다. 빈 줄은 버리되 최소 한 줄은 남긴다(지금 규칙).
    """
    raw_rows = raw.get("spec_rows")
    if not isinstance(raw_rows, list):
        raw_rows = [{"spec_width": raw.get("width"), "spec_depth": raw.get("depth"), "spec_height": raw.get("height")}]
    rows = []
    for row in raw_rows[:MAX_SPEC_ROWS]:
        if not isinstance(row, dict):
            continue
        cleaned = {key: _dim(row.get(key)) for key in SPEC_KEYS}
        if any(cleaned.values()):
            rows.append(cleaned)
    return rows or [{key: "" for key in SPEC_KEYS}]


def _clean_item(raw: dict[str, Any], name: str) -> dict[str, Any]:
    """품목 하나 — 우리 주문 화면과 같은 키(규격 줄 · 제품 속성 다섯 칸 · 추가 입력)."""
    item: dict[str, Any] = {
        "product_name": name,
        "spec_rows": _clean_spec_rows(raw),
        "quantity": _text(raw.get("quantity"), 10) or "1",
    }
    for key in ATTRIBUTE_KEYS:
        value = _text(raw.get(key))
        if value:
            item[key] = value
    # 옛 화면의 "품목 메모"는 지금처럼 기타·설치(misc)로 받는다.
    if "misc" not in item and _text(raw.get("memo")):
        item["misc"] = _text(raw.get("memo"))
    extra = _text(raw.get("extra_input"), 2000)
    if extra:
        item["extra_input"] = extra
    return item


def clean_partner_items(raw_items: Any, *, keep_uid: bool = False) -> list[dict[str, Any]]:
    """협력사가 보낸 품목들. ``keep_uid`` 면 화면이 돌려보낸 품목 uid 를 싣는다(진위는 ``ensure_item_uids`` 가 본다)."""
    if not isinstance(raw_items, list):
        raise PartnerOrderError("품목을 하나 이상 넣어 주세요.")
    items: list[dict[str, Any]] = []
    for raw in raw_items[:MAX_ITEMS]:
        if not isinstance(raw, dict):
            continue
        name = _text(raw.get("product_name"), 100)
        if name:
            item = _clean_item(raw, name)
            if keep_uid and isinstance(raw.get("uid"), str):
                item["uid"] = raw["uid"][:64]
            items.append(item)
    if not items:
        raise PartnerOrderError("품목을 하나 이상 넣어 주세요.")
    return items


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
    items = clean_partner_items(data.get("items"))
    memo = _text(data.get("memo"), 2000)
    measured_on = _text(data.get("measured_on"), 10)

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
            "manager": manager_party(user, org),
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
        owner_user_id=user.id,
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
    # 우리 쪽이 새 협력사 주문을 놓치지 않게 — CS 팀 알림(벨 목록). 담당(협력사 직원)은 알림을 받지 않는다.
    # 협력사 주문은 실측일이 없어 실측 화면에 뜨지 않으므로 알림이 접수 신호다.
    notification = Notification(
        order_id=order.id,
        notification_type=PARTNER_ORDER_NOTIFICATION_TYPE,
        target_team="CS",
        title="협력사 새 주문",
        message=f"[{org.name}] 주문 #{order.id} ({customer_name}) 접수 — 내용 확인 후 도면 단계로 넘겨 주세요.",
        created_by_user_id=user.id,
        created_by_name=f"{user.name} (협력사)",
    )
    db.add(notification)
    db.flush()
    fan_out_new_notification(db, notification, actor_user_id=user.id)
    return order

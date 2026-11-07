"""FCOMM-01 D26: 켜진 프리랜서의 "예전 담당 주문"은 보통 영업 직원과 같게 다룬다.

사용자 결정(2026-11-07): 프리랜서로 바뀌기 전(시작 달 전)에 실측한 자기 담당 주문은 회사 영업 때처럼 막힘 없이
고칠 수 있어야 한다. 남의 주문은 그대로 안 보인다.

**예전 주문** = 내 주문(연결 표 — :func:`foms.services.auth.freelancer_orders.freelancer_can_access_order`) 이면서
수수료 대상이 아니고(:func:`foms.services.sales_commission.calc.is_before_start` — 수수료 대상 판정 ``is_eligible``
의 반대쪽) **주문이 만들어진 날도 시작 달 전**인 주문. 만든 날 조건은 프리랜서가 시작 달 뒤에 새로 등록하면서
실측일을 앞 달로 적어 이 규칙으로 들어오는 길을 막는다(시험 R1 회귀가 잡음) — 그런 주문은 수수료도 없고
프리랜서 규칙도 그대로다(막는 쪽).

풀리는 자리:

1. 문지기(겹 1) — :data:`LEGACY_ORDER_ENDPOINTS` 의 주문 일 API 는 URL 의 주문 번호가 모두 예전 주문이면 통과한다
   (:func:`legacy_order_request_allowed`). 그 뒤는 각 API 의 원래 권한이 보통 영업 직원과 똑같이 판정한다.
2. 허용 목록 문을 지난 요청도 실린 주문 번호가 모두 예전 주문이면 요청 표시를 남긴다(:func:`mark_if_legacy`).
3. 사람 단위로만 판정하던 곳(금융 정책 · 입금 확인 · PUSH 종류 · 퀘스트 단계)은 그 표시를 본다
   (:func:`freelancer_request_is_legacy`). 주문이 손에 있는 곳(발주사 · 담당자 저장)은 주문으로 직접 본다
   (:func:`freelancer_legacy_order`).

스펙: docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.6 (D26)
시험: tests/security/test_freelancer_legacy_orders.py
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from flask import g, has_request_context, request

from foms.services.auth.freelancer_orders import freelancer_can_access_order
from foms.services.sales_commission import calc
from foms.services.sales_commission.settings import active_freelancers
from foms.services.settlement_source import fetch_settlement_rows
from models import Order

#: 예전 주문이면 프리랜서에게 열어 주는 주문 일 API(endpoint → URL 의 주문 번호 인자). 모두 URL 에 주문 번호가
#: 있고, 그 주문 하나를 다룬다. 원래 권한(팀 · 역할 정책)은 각 API 가 그대로 본다.
#: 빼는 것: 관리자 · 협력사 · 협력사 명세서 · 회계 전용(수수료 입력 · 차감 취소) · 휴지통 영구 삭제 · 도면팀 전용
#: (도면 넘기기 · 마법사) · 채팅 · 판 화면(태블릿 조각 · 작업대 · AS 판).
_ORDER_ID = ("order_id",)
LEGACY_ORDER_ENDPOINTS: dict[str, tuple[str, ...]] = {endpoint: _ORDER_ID for endpoint in (
    # 옛 편집 화면 저장(허용 목록은 GET 만)
    "order_edit.edit_order",
    # 첨부 — 올리기 준비 · 순서 · 되살리기(목록 · 올리기 · 지우기는 이미 허용)
    "attachments.api_create_upload_draft",
    "attachments.api_issue_upload_ticket",
    "attachments.api_order_attachments_reorder",
    "attachments.api_order_attachments_restore",
    # 견적 · 계산기 견적
    "erp_estimates.create_order_estimate",
    "erp_estimates.get_estimate_preview",
    "erp_estimates.list_order_estimates",
    "wdcalculator.api_orders_wdc_estimate_sync",
    "wdcalculator.api_wdcalculator_get_order_estimates",
    # 주소 · 칸 하나 고치기 · 상세 묶음 · 라벨 · QR
    "erp_map.api_update_order_address",
    "erp_orders_structured.api_patch_order_structured_fields",
    "erp_orders_structured.api_get_order_detail_payload",
    "erp_dashboard.erp_order_label",
    "orders.api_order_qr_svg",
    # AS
    "erp_orders_as.api_as_billing",
    "erp_orders_as.api_as_classification",
    "erp_orders_as.api_as_complete",
    "erp_orders_as.api_as_log_append",
    "erp_orders_as.api_as_log_delete",
    "erp_orders_as.api_as_log_patch",
    "erp_orders_as.api_as_register",
    "erp_orders_as.api_as_reopen",
    "erp_orders_as.api_as_sales_delivery",
    "erp_orders_as.api_as_schedule",
    "erp_orders_as.api_as_schedule_link",
    "erp_orders_as.api_as_start",
    "erp_orders_as.api_as_unschedule",
    "erp_orders_as.api_as_upload_anchor",
    "erp_orders_as.api_as_verdict",
    # 도면 받기 · 수정 요청(영업 쪽) · 도면 담당 정하기
    "erp_orders_blueprint.api_blueprint_complete",
    "erp_orders_blueprint.api_delete_blueprint",
    "erp_orders_blueprint.api_get_blueprint",
    "erp_orders_blueprint.api_upload_blueprint",
    "erp_orders_draftsman.api_order_assign_draftsman",
    "erp_orders_draftsman.api_order_confirm_drawing_receipt",
    "erp_orders_drawing.api_drawing_gateway_complete",
    "erp_orders_drawing.api_drawing_gateway_upload",
    "erp_orders_revision.api_order_cancel_revision_request",
    "erp_orders_revision.api_order_edit_revision_request",
    "erp_orders_revision.api_order_request_revision",
    # 돈 — 차감 기록 · 현금영수증 · 입금 확인(차감 취소는 회계 전용이라 뺌)
    "erp_orders_completion.api_cash_receipt_issue",
    "erp_orders_completion.api_settlement_issue",
    "erp_orders_structured.api_payment_confirm",
    # 생산 · 출고 · 시공 · 완료
    "erp_orders_production.api_production_cancel",
    "erp_orders_production.api_production_change_ack",
    "erp_orders_production.api_production_complete",
    "erp_orders_production.api_production_defect",
    "erp_orders_production.api_production_hold",
    "erp_orders_production.api_production_rework",
    "erp_orders_production.api_production_start",
    "erp_orders_production.api_production_steps",
    "erp_orders_production.api_production_steps_get",
    "erp_orders_production.api_production_uncomplete",
    "erp_orders_production.api_set_logistics_status",
    "erp_shipment.api_confirm_partner_request",
    "erp_shipment.api_erp_shipment_update",
    "erp_shipment.api_set_construction_schedule",
    "erp_shipment.api_shipment_change_ack",
    "erp_shipment.api_shipment_packing_get",
    "erp_shipment.api_shipment_packing_save",
    "erp_orders_construction.api_construction_complete",
    "erp_orders_construction.api_construction_evidence",
    "erp_orders_construction.api_construction_fail",
    "erp_orders_construction.api_construction_start",
    "erp_orders_cs.api_cs_complete",
    "erp_orders_item_cancel.api_order_item_cancel_after_confirm",
    # 단계 · 변경 되돌리기 · 퀘스트 · 통화 기록 · 할 일 · 공유 링크 · 보관 칸 · 휴지통으로 보내기/되살리기
    "orders.api_order_stage_override",
    "events.api_compensate_change_event",
    "events.api_restore_field_change",
    "quest.api_order_quest_create",
    "quest.api_order_quest_get",
    "quest.api_order_quest_update_status",
    "orders.api_order_call_log",
    "tasks.api_order_tasks_create",
    "tasks.api_order_tasks_delete",
    "tasks.api_order_tasks_list",
    "tasks.api_order_tasks_update",
    "share_api.api_share_create",
    "share_api.api_share_list",
    "storage_dashboard.update_storage_field",
    "orders.mobile_delete_order",
    "orders.mobile_restore_order",
)}

#: 요청 안 캐시 ``{(user_id, order_id): bool}`` · 이 요청이 예전 주문만 다룬다는 표시.
_G_CACHE_ATTR = "_fcomm_legacy_order"
_G_FLAG_ATTR = "_fcomm_legacy_request"
#: 기준 날짜를 읽는 투영 나무(수수료 탭과 같은 칸).
_BASIS_SD_SPEC: dict[str, Any] = {"schedule": {"measurement": {"date": None}}}


def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _measurement_date(sd: Any) -> Any:
    schedule = sd.get("schedule") if isinstance(sd, dict) else None
    measurement = schedule.get("measurement") if isinstance(schedule, dict) else None
    return measurement.get("date") if isinstance(measurement, dict) else None


def _before_start(db: Any, user_id: int, order_id: int) -> bool:
    """주문의 기준 날짜가 이 프리랜서의 시작 달보다 앞서는가(설정 · 주문 하나씩 읽음)."""
    config = active_freelancers(db).get(user_id)
    if config is None:
        return False
    rows = fetch_settlement_rows(db, (Order.id, Order.received_date, Order.created_at),
                                 (Order.id == order_id,), _BASIS_SD_SPEC)
    if not rows:
        return False
    row = rows[0]
    if not calc.is_before_start(None, None, row.created_at, config.start_month):
        return False  # 시작 달 뒤에 만든 주문은 실측일을 앞으로 적어도 예전 주문이 아니다
    return calc.is_before_start(_measurement_date(row.structured_data), row.received_date, row.created_at,
                                config.start_month)


def freelancer_legacy_order(db: Any, user: Any, order_id: Any) -> bool:
    """켜진 프리랜서 ``user`` 에게 ``order_id`` 가 예전 담당 주문인가(내 주문 + 시작 달 전 기준 날짜).

    프리랜서인지는 부르는 쪽이 판정했다고 본다. 없는 주문 · 남의 주문 · 새 주문은 거짓. 요청 안에서는 (사람, 주문)
    마다 한 번만 읽는다.
    """
    uid = _int_or_none(getattr(user, "id", None)) if user is not None else None
    oid = _int_or_none(order_id)
    if uid is None or oid is None or oid <= 0:
        return False
    cache = None
    if has_request_context():
        cache = getattr(g, _G_CACHE_ATTR, None)
        if cache is None:
            cache = {}
            setattr(g, _G_CACHE_ATTR, cache)
        if (uid, oid) in cache:
            return cache[(uid, oid)]
    result = freelancer_can_access_order(db, user, oid) and _before_start(db, uid, oid)
    if cache is not None:
        cache[(uid, oid)] = result
    return result


def mark_if_legacy(db: Any, user: Any, order_ids: Iterable[Any]) -> bool:
    """실린 주문 번호가 하나 이상이고 모두 예전 주문이면 이 요청에 표시를 남기고 True."""
    ids = list(order_ids)
    legacy = bool(ids) and all(freelancer_legacy_order(db, user, oid) for oid in ids)
    if legacy and has_request_context():
        setattr(g, _G_FLAG_ATTR, True)
    return legacy


def legacy_order_request_allowed(db: Any, user: Any, endpoint: Optional[str]) -> bool:
    """문지기 — 허용 목록 밖이어도 :data:`LEGACY_ORDER_ENDPOINTS` 이고 URL 의 주문 번호가 모두 예전 주문이면 True."""
    names = LEGACY_ORDER_ENDPOINTS.get(endpoint or "")
    if not names:
        return False
    view_args = request.view_args or {}
    if any(name not in view_args for name in names):
        return False
    return mark_if_legacy(db, user, (view_args[name] for name in names))


def freelancer_request_is_legacy() -> bool:
    """문지기가 이 요청을 "예전 주문만 다룸"으로 표시했는가. 요청 밖이면 거짓."""
    return has_request_context() and bool(getattr(g, _G_FLAG_ATTR, False))


__all__ = [
    "LEGACY_ORDER_ENDPOINTS",
    "freelancer_legacy_order",
    "freelancer_request_is_legacy",
    "legacy_order_request_allowed",
    "mark_if_legacy",
]

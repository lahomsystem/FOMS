"""FCOMM-01 D27: 켜진 프리랜서도 **자기 주문**에서는 회사 영업 직원(매니저 등급 포함)과 똑같이 일한다.

사용자 결정(2026-11-07, D26 을 넓힘): "프리랜서도 주문건만 자기 것만 보이고 이전 회사 소속일 때랑 동일한 사용이
가능해야 돼". 남은 프리랜서 제한은 **주문 범위 하나**다 — 남의 주문은 안 보이고 못 고친다. 내 주문(연결 표 또는 내가
만든 초안 — :func:`foms.services.auth.freelancer_orders.freelancer_can_access_order`)에서는 발주사 · 담당자 바꾸기,
금융 쓰기(차감 · 입금 확인 · 현금영수증), PUSH 종류, 퀘스트 단계 같은 사람 단위 막기를 두지 않는다. 각 API 의 원래
권한(역할 · 팀 정책)이 회사 직원과 똑같이 판정한다.

이 모듈은 문지기(겹 1)가 허용 목록 밖에서도 열어 주는 **주문 일 API 목록**을 둔다 — URL 에 주문 번호가 있고 그 주문
하나를 다루는 API 다. 번호가 모두 내 주문이면 통과(:func:`own_order_request_allowed`), 아니면 문지기 응답 그대로.

예외 하나(사장님 2026-11-27 "새 화면에 '내 주문만' … 보기만, 단추 없음"): 생산 쓰기 여덟은 내 주문이어도 닫는다
(:data:`CLOSED_ORDER_ENDPOINTS`). 바뀐 것 [확인했어요](``api_production_change_ack``)는 "회사 영업처럼 보이게"라 그대로 연다.

스펙: docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.6 (D27)
시험: tests/security/test_freelancer_own_order_rights.py
"""
from __future__ import annotations

from typing import Any, Optional

from flask import request

from foms.services.auth.freelancer_orders import freelancer_can_access_order

#: 내 주문이면 프리랜서에게 열어 주는 주문 일 API(endpoint → URL 의 주문 번호 인자). 모두 URL 에 주문 번호가 있고,
#: 그 주문 하나를 다룬다. 원래 권한(팀 · 역할 정책)은 각 API 가 그대로 본다.
#: 빼는 것: 관리자 · 협력사 · 협력사 명세서 · 회계 전용(수수료 입력 · 차감 취소) · 도면팀 전용(도면 넘기기 · 마법사) ·
#: 채팅 · 판 화면(판 화면은 foms/services/auth/freelancer_screens/ 에서 거르기와 함께 연다).
_ORDER_ID = ("order_id",)
OWN_ORDER_ENDPOINTS: dict[str, tuple[str, ...]] = {endpoint: _ORDER_ID for endpoint in (
    # 옛 편집 화면 저장(허용 목록은 GET 만)
    "order_edit.edit_order",
    # 첨부 — 올리기 준비 · 순서 · 되살리기(목록 · 올리기 · 지우기는 이미 허용)
    "attachments.api_create_upload_draft",
    "attachments.api_issue_upload_ticket",
    "attachments.api_order_attachments_reorder",
    "attachments.api_order_attachments_restore",
    # 견적(미리보기 · 이은 계산기 견적 목록은 허용 목록에 있음)
    "erp_estimates.create_order_estimate",
    "erp_estimates.list_order_estimates",
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
    # 생산 — 바뀐 것 [확인했어요]만(사장님 2026-11-27 "회사 영업처럼 보이게"). 그 밖 생산 쓰기 여덟은 아래
    # CLOSED_ORDER_ENDPOINTS(내 주문이어도 닫음), 공정 읽기 GET 은 지우는 길이라 뺐다. 물류 상태는 생산 화면 밖이라 그대로.
    "erp_orders_production.api_production_change_ack",
    "erp_orders_production.api_set_logistics_status",
    # 출고 · 시공 · 완료
    "erp_shipment.api_confirm_partner_request",
    "erp_shipment.api_revert_partner_request",
    "erp_shipment.api_erp_shipment_update",
    "erp_shipment.api_set_construction_schedule",
    "erp_shipment.api_shipment_change_ack",
    "erp_shipment.api_shipment_packing_get",
    "erp_shipment.api_shipment_packing_save",
    "erp_orders_construction.api_construction_complete",
    "erp_orders_construction.api_construction_evidence",
    "erp_orders_construction.api_construction_fail",
    "erp_orders_construction.api_construction_start",
    # 제품마다 '시공 끝' — [시공 완료] 창의 "오늘 끝낸 제품" 목록(완료와 한 몸이라 같이 연다. 되돌리기는 CS 몫이라 뺌)
    "erp_orders_construction.api_construction_visit_items",
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
    # 휴지통으로 보내기(옛 길 — 매니저 등급 정책이 판정)
    "order_trash.delete_order",
)}


#: 내 주문이어도 프리랜서에게 **닫아 둔** 주문 일 API — 생산 쓰기 여덟(제작 시작 · 완료 · 수정 제작 · 제작 취소 · 완료 취소 · 공정 칸 ·
#: 불량 · 보류). 사장님 2026-11-27 "보기만, 단추 없음": 프리랜서의 생산 화면에는 [확인했어요]만 있다. 각 API 의 쓰기 판정(관리자 ·
#: 생산팀)도 영업팀을 403 으로 막지만 문지기에서 먼저 막아 두 겹으로 둔다. 답은 내 주문 403 "열 수 없는 화면", 남의 · 없는 주문은
#: 다른 주문 API 와 같은 404 "주문을 찾을 수 없어요."(:func:`closed_order_request_is_foreign` — 목록에서 빼기 전과 같은 답).
CLOSED_ORDER_ENDPOINTS: dict[str, tuple[str, ...]] = {endpoint: _ORDER_ID for endpoint in (
    "erp_orders_production.api_production_cancel",
    "erp_orders_production.api_production_complete",
    "erp_orders_production.api_production_defect",
    "erp_orders_production.api_production_hold",
    "erp_orders_production.api_production_rework",
    "erp_orders_production.api_production_start",
    "erp_orders_production.api_production_steps",
    "erp_orders_production.api_production_uncomplete",
)}


def own_order_request_allowed(db: Any, user: Any, endpoint: Optional[str]) -> bool:
    """문지기 — 허용 목록 밖이어도 :data:`OWN_ORDER_ENDPOINTS` 이고 URL 의 주문 번호가 모두 내 주문이면 True."""
    names = OWN_ORDER_ENDPOINTS.get(endpoint or "")
    if not names:
        return False
    view_args = request.view_args or {}
    if any(name not in view_args for name in names):
        return False
    return all(freelancer_can_access_order(db, user, view_args[name]) for name in names)


def closed_order_request_is_foreign(db: Any, user: Any, endpoint: Optional[str]) -> bool:
    """문지기 — :data:`CLOSED_ORDER_ENDPOINTS` 요청의 URL 주문 번호 중 내 주문이 아닌 것(없는 주문 포함)이 있으면 True.

    True 면 문지기가 404 로, False(닫아 둔 API 가 아니거나 모두 내 주문)면 기본 거부 403 으로 답한다 — 어느 쪽도 통과는 아니다.
    """
    names = CLOSED_ORDER_ENDPOINTS.get(endpoint or "")
    if not names:
        return False
    view_args = request.view_args or {}
    return not all(name in view_args and freelancer_can_access_order(db, user, view_args[name]) for name in names)


__all__ = ["CLOSED_ORDER_ENDPOINTS", "OWN_ORDER_ENDPOINTS", "closed_order_request_is_foreign", "own_order_request_allowed"]

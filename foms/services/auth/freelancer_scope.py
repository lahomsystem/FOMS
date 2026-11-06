"""FCOMM-01 3단계 겹 1: 프리랜서 영업 계정의 기본 거부 문지기(허용 목록 · 판정 함수).

켜진 프리랜서(``foms.services.sales_commission.settings`` 의 설정에서 ``active`` 인 직원 · 영업팀 계정)는
**허용 목록에 있는 endpoint 만** 쓸 수 있다. 나머지는 :func:`freelancer_gate` 가 막는다 — 직원 세션
endpoint 수백 개가 ``@login_required`` 만 보고 모든 주문을 열어 주므로, 화면을 하나씩 막지 않고
기본 거부로 간다. 새 라우트가 생겨도 저절로 막힌다(협력사 문지기 :mod:`foms.services.auth.partner_scope` 와 같은 틀).

허용 목록은 URL 접두어가 아니라 **endpoint 이름**이다. 허용한 endpoint 도 주문 단위 판정(겹 2, T15)과
목록 강제 거르기(겹 3, T16)를 따로 받아야 한다 — 이 모듈은 "어느 문을 열어 두나"만 정한다.
허용 목록 밖 쓰기는 여기서 모두 막히므로 쓰기 정책 엔진에 프리랜서 허용 정책 목록을 따로 두지 않는다.

꺼진 프리랜서(``active: false``)는 막지 않는다 — 보통 영업 직원과 같다(설계서 §6.3 "켜진 프리랜서").

스펙: docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.3 겹 1 · §6.5
시험: tests/security/test_freelancer_gate.py (모든 URL 규칙 막힘 전수)
"""
from __future__ import annotations

from typing import Any

from flask import g, jsonify, redirect, request, url_for

from db import get_db
from foms.services.orders.order_mutation_policy import normalize_team
from foms.services.sales_commission.settings import is_freelancer

# 프리랜서 세션이 쓸 수 있는 endpoint(분류마다 한 줄 이유).
FREELANCER_ALLOWED_ENDPOINTS: frozenset[str] = frozenset({
    # ── 공통: 정적 파일 · 로그아웃 · 관리자가 프리랜서 계정으로 들어가 본 뒤 돌아오는 길(라우트가 직접 판정)
    "static",
    "auth.logout",
    "auth.switch_back",
    # 브라우저가 스스로 부르는 아이콘 · 모든 화면이 보내는 익명 화면 속도 기록(읽는 것 없음)
    "favicon",
    "foms_rum.ingest_rum_event",
    # 내 정보 — 보기만. 저장(이름 · 비밀번호 한 폼)은 FREELANCER_METHOD_LIMITS 가 막는다(J8 · 검토 A1).
    "auth.profile",
    # ── 알림: 모두 내 알림 state 만 다룬다(목록 · 배지 · 읽음 · 확인 · 보관 · 다시 띄울 미확인 알림)
    "notifications.api_notifications_list",
    "notifications.api_notifications_badge",
    "notifications.api_notification_mark_read",
    "notifications.api_notifications_mark_all_read",
    "notifications.api_notification_ack",
    "notifications.api_notification_archive",
    "notifications.api_notifications_archive_all",
    "notifications.api_notifications_pending_interrupts",
    "notifications.api_notifications_pending_urgent",
    # 폰 알림 — 공개 키 · 내 기기 구독 · 나에게 시험 알림 · 내 알림 열람 기록 · 모바일 알림 상태
    "notifications_push.vapid_public_key",
    "notifications_push.subscribe",
    "notifications_push.push_test",
    "notifications_push.push_event",
    "notifications_push_state.mobile_state",
    # ── 공지: 목록 화면 · 내 공지 · 읽음 · 확인 · 사진(안에서 받는 사람 판정을 다시 한다)
    "notices_web.notice_list",
    "notices_api.list_notices",
    "notices_api.read_notice",
    "notices_api.ack_notice",
    "notices_api.notice_image",
    # ── 홈 · 목록: 모바일 홈 · 월 달력(달 이동 · 날짜 칸을 누르면 여는 그날 목록) · 실측 판 · 실측 요약 ·
    #    날짜 없는 실측. 남의 주문이 섞이지 않게 하는 것은 겹 3 강제 거르기(T16)다.
    "erp_dashboard.erp_dashboard",
    "erp_dashboard.erp_dashboard_field_calendar",
    "erp_dashboard.erp_dashboard_field_ops",
    "erp_measurement_dashboard.erp_measurement_dashboard",
    "erp_measurement.api_erp_measurement_summary",
    "erp_measurement.api_erp_measurement_undated",
    # ── 주문 1건: 모바일 상세 · 편집 화면(보기만 — 저장은 structured PUT) · 옛 상세 주소(편집으로 보냄) ·
    #    편집/타임라인 조각. 내 주문인지는 겹 2 주문 단위 판정(T15)이 본다.
    "erp_dashboard.erp_order_mobile_detail",
    "order_edit.edit_order",
    "order_edit.redirect_legacy_erp_order_detail",
    "foms_fragment.order_edit_fragment",
    "foms_fragment.order_timeline_fragment",
    # 주문 읽기 · 저장(발주사 바꾸기 거부는 겹 4, T17)
    "erp_orders_structured.api_get_order_structured",
    "erp_orders_structured.api_put_order_structured",
    # 이벤트 · 변경 이력, 저장 직후 서버가 묻는 일정 · 금액 변경 사유(사유 목록 · 사유 적기)
    "events.api_order_events",
    "events.api_order_field_changes",
    "events.api_order_change_events",
    "events.api_change_reason_codes",
    "events.api_set_order_change_reason",
    # 첨부 목록 · 올리기(직접 · 바로 올리기 완료 · 올리기 세션 1장/여러 장)
    "attachments.api_order_attachments_list",
    "attachments.api_order_attachments_upload",
    "attachments.api_order_attachments_complete",
    "attachments.api_upload_session",
    "attachments.api_upload_session_batch",
    # 파일 관문 3종 — 안에서 user_can_read_order 로 주문 단위 판정(겹 2 가 프리랜서 분기를 넣는다)
    "files.view",
    "files.presigned_urls",
    "files.download",
    # ── 등록: 새 주문 화면(보기만 — PC 는 ERP 탭, 휴대폰은 마법사) · PC 초안(만들기 · 자동 저장 · 복원 · 버리기,
    #    등록은 structured PUT) · 마법사 초안(내 초안만) · 마법사 초안 발송(내 초안을 서버가 다시 조립) ·
    #    주소 찾기 · 붙여넣기 해석(저장 없음)
    "order_pages.add_order",
    "erp_orders_structured.api_erp_create_draft",
    "erp_orders_structured.api_erp_draft_autosave",
    "erp_orders_structured.api_erp_get_draft",
    "erp_orders_structured.api_erp_discard_draft",
    "erp_order_draft.api_get_order_draft",
    "erp_order_draft.api_put_order_draft",
    "erp_order_draft.api_delete_order_draft",
    "erp_order_draft.api_list_order_drafts",
    "erp_order_draft.api_submit_order_draft",
    "erp_order_draft.api_upload_order_draft_attachment",
    "erp_order_draft_send.api_draft_alimtalk_preview",
    "erp_order_draft_send.api_draft_alimtalk_send",
    "erp_order_draft_send.api_draft_channel_push_preview",
    "erp_order_draft_send.api_draft_channel_push_send",
    "address.search",
    "erp_orders_structured.api_parse_order_text",
    # ── 수수료: 내 수수료 화면(언제나 본인 것)
    "sales_commission_web.my_commission",
})

# 허용한 endpoint 중 일부 방법만 여는 것. GET 을 열면 HEAD 도 연다.
FREELANCER_METHOD_LIMITS: dict[str, frozenset[str]] = {
    # 이름 저장 거부(J8 — 화면 표시 이름도 관리자만). 같은 폼의 비밀번호 바꾸기도 함께 막힌다.
    "auth.profile": frozenset({"GET"}),
    # 옛(비 ERP) 주문 폼 저장 · 옛 주문 만들기 — ERP 저장 길(structured PUT · 초안)만 쓴다.
    "order_edit.edit_order": frozenset({"GET"}),
    "order_pages.add_order": frozenset({"GET"}),
}

FREELANCER_DENIED_MSG = "프리랜서 계정으로는 열 수 없는 화면이에요."
FREELANCER_HOME_ENDPOINT = "erp_dashboard.erp_dashboard"


def could_be_freelancer(user: Any) -> bool:
    """프리랜서가 될 수 있는 계정인지 — 직원(STAFF) · 영업팀(MEASURE 포함) · 협력사 아님. 설정은 읽지 않는다.

    설정 저장(``settings._target_user``)이 같은 조건을 강제하므로 그 밖의 계정은 프리랜서일 수 없다.
    """
    if user is None or getattr(user, "partner_org_id", None) is not None:
        return False
    if str(getattr(user, "role", "") or "").strip().upper() != "STAFF":
        return False
    return normalize_team(getattr(user, "team", None)) == "SALES"


def is_freelancer_user(user: Any) -> bool:
    """켜진 프리랜서인지(요청 안에서는 설정을 한 번만 읽는다 — ``settings.is_freelancer`` 의 ``g`` 저장)."""
    return could_be_freelancer(user) and is_freelancer(get_db(), user)


def is_freelancer_request_allowed(endpoint: str | None, method: str | None) -> bool:
    """허용 목록 판정. endpoint 가 없으면(404 · 405) 거부한다."""
    if not endpoint or endpoint not in FREELANCER_ALLOWED_ENDPOINTS:
        return False
    limits = FREELANCER_METHOD_LIMITS.get(endpoint)
    if limits is None:
        return True
    verb = (method or "").upper()
    return verb in limits or (verb == "HEAD" and "GET" in limits)


def freelancer_gate() -> Any | None:
    """``before_request`` 문지기 — 켜진 프리랜서 세션이면 허용 목록 밖을 막는다.

    ``partner_gate`` 바로 뒤에 등록돼야 한다(``_set_current_user`` 가 채운 ``g.current_user`` 를 읽는다).
    직원 · 영업팀이 아닌 계정과 정적 파일은 설정을 읽지 않고 지나간다.

    Returns:
        막을 때 응답(API · 쓰기 = 403 JSON, 화면 = 프리랜서 홈으로 302), 통과면 ``None``.
    """
    user = getattr(g, "current_user", None)
    if not could_be_freelancer(user) or request.endpoint == "static":
        return None
    if not is_freelancer(get_db(), user):
        return None
    if is_freelancer_request_allowed(request.endpoint, request.method):
        return None
    # API 네임스페이스(``/api/``·``/erp/api/``)는 302 가 아니라 JSON 이어야 한다(협력사 문지기와 같은 기준).
    if "/api/" in (request.path or "") or request.method not in ("GET", "HEAD"):
        return jsonify({"success": False, "data": None, "error": FREELANCER_DENIED_MSG}), 403
    return redirect(url_for(FREELANCER_HOME_ENDPOINT))

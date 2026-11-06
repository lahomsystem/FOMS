"""FCOMM-01 3단계 겹 1: 프리랜서 영업 계정의 기본 거부 문지기(허용 목록 · 판정 함수).

켜진 프리랜서(``foms.services.sales_commission.settings`` 의 설정에서 ``active`` 인 직원 · 영업팀 계정)는
**허용 목록에 있는 endpoint 만** 쓸 수 있다. 나머지는 :func:`freelancer_gate` 가 막는다 — 직원 세션
endpoint 수백 개가 ``@login_required`` 만 보고 모든 주문을 열어 주므로, 화면을 하나씩 막지 않고
기본 거부로 간다. 새 라우트가 생겨도 저절로 막힌다(협력사 문지기 :mod:`foms.services.auth.partner_scope` 와 같은 틀).

허용 목록은 URL 접두어가 아니라 **endpoint 이름**이다. 허용 목록 밖 쓰기는 여기서 모두 막히므로 쓰기 정책
엔진에 프리랜서 허용 정책 목록을 따로 두지 않는다.

겹 2(T15) — 허용한 문에 실린 **주문 번호**도 여기서 본다. endpoint 마다 주문 번호가 실리는 자리를 적어 둔다
(추측하지 않는다): URL 인자(:data:`FREELANCER_ORDER_VIEW_ARGS`), query string(:data:`FREELANCER_ORDER_QUERY_ARGS`),
본문(:data:`FREELANCER_ORDER_BODY_CHECKS`). 내 주문이 아니면(없는 주문도) 404 — 존재 여부를 알리지 않는다.
"내 주문" 판정은 :func:`foms.services.auth.freelancer_orders.freelancer_can_access_order` 하나다. 파일 관문
3종(``files.*``)은 key 에서 주문을 찾는 일이 핸들러 안에 있어 거기서 ``user_can_read_order`` 로 본다.
목록 강제 거르기(겹 3, T16)는 따로다.

꺼진 프리랜서(``active: false``)는 막지 않는다 — 보통 영업 직원과 같다(설계서 §6.3 "켜진 프리랜서").

스펙: docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.3 겹 1 · 겹 2 · §6.5
시험: tests/security/test_freelancer_gate.py (모든 URL 규칙 막힘 전수),
      tests/security/test_freelancer_order_scope.py (허용 endpoint 의 주문 번호 전수)
"""
from __future__ import annotations

import posixpath
from typing import Any, Callable, Optional

from flask import abort, g, jsonify, redirect, request, url_for

from db import get_db
from foms.services.auth.freelancer_orders import freelancer_can_access_order
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
    # 내 정보 — 보기 · 비밀번호 바꾸기. 같은 폼의 이름은 핸들러가 지금 이름으로 되돌린다(J8 · 검토 A1,
    # foms.services.auth.freelancer_edit_guards.freelancer_profile_name).
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
    # 주문 읽기 · 저장(등록된 주문의 발주사 바꾸기 거부는 겹 4 — freelancer_edit_guards)
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
    # 첨부 지우기 · 제품에 잇기(D23). 첨부가 URL 주문 것인지는 핸들러가 본다(order_id 로 같이 찾는다),
    # 누가 지울 수 있는지는 can_delete/can_modify_order_attachment(주문 담당 · 올린 사람).
    "attachments.api_order_attachments_delete",
    "attachments.api_order_attachments_patch",
    # ── 주문 화면 보내기(D22): 실측 예약 알림톡 미리보기 · 보내기 · 나간 채널 확인, 채널톡 PUSH.
    #    PUSH 종류는 영발 · 실측만(겹 4 — freelancer_edit_guards.freelancer_push_kind_denial).
    "kakao.api_alimtalk_preview",
    "kakao.api_alimtalk_send_manual",
    "kakao.api_alimtalk_confirm_channel",
    "channel_integration.api_channel_push_manual",
    # ── 실측 일(D23): 도면으로 넘기기(퀘스트 승인 — 실측 단계만, 겹 4) · 실측 판 칸 고치기(담당자는 등록 뒤
    #    잠금, 겹 4) · 방문 체크
    "quest.api_order_quest_approve",
    "erp_measurement.api_erp_measurement_update",
    "orders.api_order_measurement_visit",
    # 긴급 호출(D23) — 받는 사람 목록(직원 이름 · 팀) · 보내기(주문을 고르면 내 주문만)
    "notifications.api_urgent_targets",
    "notifications.api_urgent_call",
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
    # 옛(비 ERP) 주문 폼 저장 · 옛 주문 만들기 — ERP 저장 길(structured PUT · 초안)만 쓴다.
    "order_edit.edit_order": frozenset({"GET"}),
    "order_pages.add_order": frozenset({"GET"}),
}

# ── 겹 2: 허용 endpoint 에 실린 주문 번호 ─────────────────────────────────────────────────────────
#: URL 인자 중 주문 번호. 허용 endpoint 의 정수 URL 인자는 모두 여기 있거나 주문이 아닌 것(공지 · 알림 번호)이어야
#: 한다 — 시험(tests/security/test_freelancer_order_scope.py)이 url_map 으로 강제한다.
FREELANCER_ORDER_VIEW_ARGS: dict[str, tuple[str, ...]] = {
    "erp_dashboard.erp_order_mobile_detail": ("order_id",),
    "order_edit.edit_order": ("order_id",),
    "order_edit.redirect_legacy_erp_order_detail": ("order_id",),
    "foms_fragment.order_edit_fragment": ("order_id",),
    "foms_fragment.order_timeline_fragment": ("order_id",),
    "erp_orders_structured.api_get_order_structured": ("order_id",),
    "erp_orders_structured.api_put_order_structured": ("order_id",),
    "events.api_order_events": ("order_id",),
    "events.api_order_field_changes": ("order_id",),
    "events.api_order_change_events": ("order_id",),
    "events.api_set_order_change_reason": ("order_id",),
    "attachments.api_order_attachments_list": ("order_id",),
    "attachments.api_order_attachments_upload": ("order_id",),
    # 본문 key 는 핸들러가 URL 주문과 같은지 본다(validate_upload_key) — URL 하나만 보면 된다.
    "attachments.api_order_attachments_complete": ("order_id",),
    # attachment_id 는 주문 번호가 아니다 — 핸들러가 (attachment_id, order_id) 둘 다로 찾는다.
    "attachments.api_order_attachments_delete": ("order_id",),
    "attachments.api_order_attachments_patch": ("order_id",),
    "kakao.api_alimtalk_preview": ("order_id",),
    "kakao.api_alimtalk_send_manual": ("order_id",),
    "kakao.api_alimtalk_confirm_channel": ("order_id",),
    "quest.api_order_quest_approve": ("order_id",),
    "erp_measurement.api_erp_measurement_update": ("order_id",),
    "orders.api_order_measurement_visit": ("order_id",),
}

#: query string 중 주문 번호(정수로 읽히는 값만 — 핸들러도 그 밖은 버린다).
FREELANCER_ORDER_QUERY_ARGS: dict[str, tuple[str, ...]] = {
    # 검색 딥링크 ?focus_order= 는 mine · 60일 창과 무관하게 그 주문 줄을 끼워 넣는다(검수 원장 A2).
    # ?order= 는 나눠 보기에서 고른 카드 강조뿐이지만 주문 번호라 같은 판정을 한다.
    "erp_dashboard.erp_dashboard": ("focus_order", "order"),
    # 실측 판 딥링크 — 날짜창 밖이어도 그 주문 줄을 끼워 넣는다.
    "erp_measurement_dashboard.erp_measurement_dashboard": ("focus_order",),
    # 일부러 뺀 것: 내 수수료 ?order= — 그 주문이 든 달을 고를 뿐 주문 내용은 내보내지 않고(언제나 내 줄만),
    # 담당에서 빠진 뒤에도 차감 알림 링크는 열려야 한다(§6.1 규칙 4 "쌓인 수수료 기록은 남는다").
}


def _body_json() -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _key_order_ids(value: Any) -> Optional[list[int]]:
    """저장소 key · 폴더 ``orders/<id>/...`` 의 주문 번호.

    정규형이 아닌 key(``..`` · ``.`` · ``//`` · 끝 ``/`` — ``posixpath.normpath`` 결과가 다르면)는 앞머리를 믿지 않고
    None(바로 거부)이다(검수 R8). 정규형이면 ``orders/<id>/`` 꼴일 때 그 번호, 아니면 빈 목록.
    """
    if not isinstance(value, str) or not value.strip():
        return []
    raw = value.strip()
    if posixpath.normpath(raw) != raw:
        return None
    parts = raw.split("/")
    if len(parts) >= 2 and parts[0] == "orders" and parts[1].isdigit():
        try:
            return [int(parts[1])]
        except ValueError:  # isdigit 는 맞지만 int 가 못 읽는 글자(위 첨자 숫자 등)
            return None
    return []


def _upload_folder_order_ids(user: Any) -> Optional[list[int]]:
    """올리기 세션(1장 · 여러 장) 본문 ``folder`` = ``orders/<id>/<칸>``. 정규형이 아니면 None."""
    return _key_order_ids(_body_json().get("folder"))


def _body_order_id(user: Any) -> Optional[list[int]]:
    """본문 ``order_id``(채널톡 PUSH · 긴급 호출). 핸들러와 같은 ``int()`` 로 읽는다 — 소수 · 참값도 핸들러가 읽는
    번호 그대로 본다. 비었거나 못 읽으면 빈 목록(핸들러가 400 · 500 으로 끝내 주문을 읽지 않는다)."""
    raw = _body_json().get("order_id")
    if raw is None or raw == "":
        return []
    try:
        return [int(raw)]
    except (TypeError, ValueError, OverflowError):
        return []


def _draft_attachment_keys(body: dict[str, Any]) -> list[str]:
    """마법사 초안 본문의 첨부 ``tmp_key``(PUT 은 ``payload`` 또는 본문 자체, 등록은 ``payload``)."""
    keys: list[str] = []
    for source in (body.get("payload"), body):
        data = source.get("data") if isinstance(source, dict) else None
        items = data.get("items") if isinstance(data, dict) else None
        for item in items if isinstance(items, list) else []:
            attachments = item.get("attachments") if isinstance(item, dict) else None
            for raw in attachments if isinstance(attachments, list) else []:
                key = str(raw.get("tmp_key") or "").strip() if isinstance(raw, dict) else ""
                if key:
                    keys.append(key)
    return keys


def _wizard_draft_order_ids(user: Any) -> Optional[list[int]]:
    """마법사 초안 저장 · 등록 본문.

    * ``order_id``(PUT) — 손님이 적는 값이라 초안 표에 남의 번호가 들어가지 않게 막는다(되채우기 ``CREATOR`` 는 이제 생성 이벤트만 근거로 쓴다 — R9).
      남의 번호를 적으면 그 주문이 내 것이 된다.
    * 첨부 ``tmp_key`` — 등록이 그 key 로 새 주문의 첨부 줄을 만든다(``promote_draft_attachments``). 내 초안 폴더
      ``order-drafts/<나>/`` 밖이면 거부, ``orders/<id>/`` 꼴이면 그 주문 판정.

    Returns:
        판정할 주문 번호 목록. 내 초안 폴더 밖 key 가 있으면 None(바로 거부).
    """
    body = _body_json()
    raw_order = body.get("order_id")
    ids = [int(raw_order)] if raw_order is not None and str(raw_order).isdigit() else []
    own_prefix = f"order-drafts/{getattr(user, 'id', '')}/"
    for key in _draft_attachment_keys(body):
        key_orders = _key_order_ids(key)
        if key_orders is None:
            return None
        if key_orders:
            ids.extend(key_orders)
        elif not key.startswith(own_prefix):
            return None
    return ids


#: 본문에 주문 번호를 싣는 허용 endpoint → 본문에서 판정할 주문 번호를 뽑는 함수(None = 바로 거부).
FREELANCER_ORDER_BODY_CHECKS: dict[str, Callable[[Any], Optional[list[int]]]] = {
    "attachments.api_upload_session": _upload_folder_order_ids,
    "attachments.api_upload_session_batch": _upload_folder_order_ids,
    "erp_order_draft.api_put_order_draft": _wizard_draft_order_ids,
    "erp_order_draft.api_submit_order_draft": _wizard_draft_order_ids,
    "channel_integration.api_channel_push_manual": _body_order_id,
    # 주문 없이도 보낸다(맨 위 줄 ⚡) — order_id 가 있을 때만 내 주문인지 본다.
    "notifications.api_urgent_call": _body_order_id,
}

FREELANCER_DENIED_MSG = "프리랜서 계정으로는 열 수 없는 화면이에요."
#: 남의 주문 · 없는 주문 — 같은 문구(존재 여부를 알리지 않는다).
FREELANCER_ORDER_NOT_FOUND_MSG = "주문을 찾을 수 없어요."
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
        막을 때 응답(허용 목록 밖: API · 쓰기 = 403 JSON, 화면 = 프리랜서 홈으로 302 / 남의 주문 번호: API · 쓰기 =
        404 JSON, 화면 = 404 화면), 통과면 ``None``.
    """
    user = getattr(g, "current_user", None)
    if not could_be_freelancer(user) or request.endpoint == "static":
        return None
    if not is_freelancer(get_db(), user):
        return None
    if is_freelancer_request_allowed(request.endpoint, request.method):
        return freelancer_order_scope_denial(user)
    if _wants_json():
        return jsonify({"success": False, "data": None, "error": FREELANCER_DENIED_MSG}), 403
    return redirect(url_for(FREELANCER_HOME_ENDPOINT))


def _wants_json() -> bool:
    """API 네임스페이스(``/api/``·``/erp/api/``) · 쓰기는 302 · 화면이 아니라 JSON(협력사 문지기와 같은 기준)."""
    return "/api/" in (request.path or "") or request.method not in ("GET", "HEAD")


def requested_order_ids(user: Any, endpoint: str | None) -> Optional[list[int]]:
    """이 요청이 가리키는 주문 번호(URL · query · 본문). 본문이 내 것이 아닌 key 를 실으면 None."""
    ids: list[Any] = []
    view_args = request.view_args or {}
    ids.extend(view_args[name] for name in FREELANCER_ORDER_VIEW_ARGS.get(endpoint or "", ()) if name in view_args)
    for name in FREELANCER_ORDER_QUERY_ARGS.get(endpoint or "", ()):
        for raw in request.args.getlist(name):
            try:
                value = int(raw)
            except (TypeError, ValueError):
                continue  # 핸들러도 정수가 아니면 버린다
            if value > 0:  # 0 은 "고른 주문 없음"(``int(... or 0) or None``)
                ids.append(value)
    body_check = FREELANCER_ORDER_BODY_CHECKS.get(endpoint or "")
    if body_check is not None:
        body_ids = body_check(user)
        if body_ids is None:
            return None
        ids.extend(body_ids)
    return [int(i) for i in ids]


def freelancer_order_scope_denial(user: Any) -> Any | None:
    """겹 2 — 허용 endpoint 에 실린 주문 번호가 모두 내 주문인가. 아니면 404(JSON 또는 화면), 맞으면 None."""
    ids = requested_order_ids(user, request.endpoint)
    if ids is not None:
        db = get_db()
        if all(freelancer_can_access_order(db, user, oid) for oid in ids):
            return None
    if _wants_json():
        return jsonify({"success": False, "data": None, "error": FREELANCER_ORDER_NOT_FOUND_MSG}), 404
    abort(404)

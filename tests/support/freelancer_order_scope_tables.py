"""프리랜서 주문 범위 시험(tests/security/test_freelancer_order_scope.py)의 분류 표.

허용 endpoint 마다 "주문 번호를 어디서 받는가"를 적는다 — 문지기 표(URL · query · 본문)에 없고 여기에도 없으면
분류 래칫이 실패한다. 판 화면 묶음(foms/services/auth/freelancer_screens/)을 열 때 여기에 줄을 더한다(시험 파일이
500줄 래칫에 닿아 표만 떼어 냄, 2026-11-07).
"""
from __future__ import annotations

# 허용 endpoint 의 정수 URL 인자 중 주문 번호가 아닌 것(내 알림 state · 공지 — 핸들러가 본인 것만 다룬다).
NON_ORDER_INT_ARGS: dict[str, set[str]] = {
    "notices_api.ack_notice": {"notice_id"},
    "notices_api.read_notice": {"notice_id"},
    "notices_api.notice_image": {"notice_id", "idx"},
    "notifications.api_notification_ack": {"notification_id"},
    "notifications.api_notification_archive": {"notification_id"},
    "notifications.api_notification_mark_read": {"notification_id"},
    # 첨부 번호 — 핸들러가 (attachment_id, URL order_id) 둘 다로 찾는다(남의 주문 첨부는 없는 것).
    "attachments.api_order_attachments_delete": {"attachment_id"},
    "attachments.api_order_attachments_patch": {"attachment_id"},
}
# 주문 번호를 핸들러가 key 에서 찾아 ``user_can_read_order`` 로 보는 것(파일 관문 3종).
HANDLER_CHECKED = {"files.view", "files.presigned_urls", "files.download"}
# AS 주문만 그리는 조각 — 실측 단계 시드는 핸들러 404(범위 404 와 같은 모양)라 내 주문은 문지기 통과로 본다(내 AS 주문
# 200 은 tests/security/test_freelancer_screen_completion.py).
STAGE_ONLY_HANDLERS = {"erp_as_page.erp_as_card_detail", "erp_as_page.erp_as_timeline"}
# query 에 주문 번호가 있지만 일부러 열어 둔 것 — 달만 고르고 주문 내용은 내보내지 않는다(문지기 주석 참고).
QUERY_EXEMPT = {"sales_commission_web.my_commission"}
# 주문 번호를 받지 않는 허용 endpoint(초안 토큰 · 초안 키 · 알림 · 공지 번호는 모두 본인 것만 다룬다).
NO_ORDER_ID = {
    "static", "favicon", "auth.logout", "auth.switch_back", "auth.profile", "foms_rum.ingest_rum_event",
    "notifications.api_notifications_list", "notifications.api_notifications_badge",
    "notifications.api_notification_mark_read", "notifications.api_notifications_mark_all_read",
    "notifications.api_notification_ack", "notifications.api_notification_archive",
    "notifications.api_notifications_archive_all", "notifications.api_notifications_pending_interrupts",
    "notifications.api_notifications_pending_urgent", "notifications_push.vapid_public_key",
    "notifications_push.subscribe", "notifications_push.push_test", "notifications_push.push_event",
    "notifications_push_state.mobile_state", "notices_web.notice_list", "notices_api.list_notices",
    "notices_api.read_notice", "notices_api.ack_notice", "notices_api.notice_image",
    "erp_dashboard.erp_dashboard_field_calendar", "erp_dashboard.erp_dashboard_field_ops",
    "erp_measurement.api_erp_measurement_summary", "erp_measurement.api_erp_measurement_undated",
    "order_pages.add_order", "erp_orders_structured.api_erp_create_draft",
    "erp_orders_structured.api_erp_draft_autosave", "erp_orders_structured.api_erp_get_draft",
    "erp_orders_structured.api_erp_discard_draft", "erp_order_draft.api_get_order_draft",
    "erp_order_draft.api_delete_order_draft", "erp_order_draft.api_list_order_drafts",
    "erp_order_draft.api_upload_order_draft_attachment", "erp_order_draft_send.api_draft_alimtalk_preview",
    "erp_order_draft_send.api_draft_alimtalk_send", "erp_order_draft_send.api_draft_channel_push_preview",
    "erp_order_draft_send.api_draft_channel_push_send", "address.search",
    "erp_orders_structured.api_parse_order_text", "events.api_change_reason_codes",
    "notifications.api_urgent_targets",
    # 통합 검색 JSON(긴급 호출 주문 고르기) — 검색어만 받는다. 결과는 서비스가 연결 표의 내 주문으로 좁힌다.
    "foms_search.api_foms_search",
    # 계산기 설정 목록(제품 · 규격 선택지 · 추가 옵션) — 주문 폼 제품 고르기용 읽기, 주문 번호 없음.
    "wdcalculator.api_wdcalculator_get_products", "wdcalculator.api_wdcalculator_get_spec_field_presets",
    "wdcalculator.api_wdcalculator_get_categories",
    # 출고 판(화면 묶음 freelancer_screens/shipment.py) — 날짜 · 검색어만 받는다. 목록은 화면이 연결 표로 거른다.
    "erp_shipment_page.erp_shipment_dashboard",
    # 도면 묶음(freelancer_screens/drawing.py) — 마법사가 읽는 도면팀 전역 설정(프리셋 · 자재표 숫자), 주문 번호 없음.
    "erp_orders_drawing_wizard.api_get_drawing_wizard_presets", "erp_orders_drawing_wizard.api_get_drawing_wizard_bom_rules",
}

# 화면 묶음 · 계산기(freelancer_screens/wdcalculator.py) — 견적 번호는 주문 아님, 본문 주문 · 견적은 핸들러가 본다.
NON_ORDER_INT_ARGS["wdcalculator.api_wdcalculator_estimate"] = {"estimate_id"}

# 고객 공유 링크(11-07 D27 후속) — 링크 · 이력 줄 번호. 핸들러가 그 줄의 주문을 보고 남의 것은 없는 줄과 같게 답한다
# (foms.api.share._share_hidden_from_user, 시험 tests/security/test_freelancer_share_links.py).
_SHARE_ROW_ARGS = {
    "share_api.api_share_send_sms": {"share_id"}, "share_api.api_share_send_alimtalk": {"share_id"},
    "share_api.api_share_revoke": {"share_id"}, "share_api.api_share_history": {"share_id"},
    "share_api.api_share_history_page": {"snapshot_id"},
}
NON_ORDER_INT_ARGS.update(_SHARE_ROW_ARGS)
HANDLER_CHECKED |= set(_SHARE_ROW_ARGS)
HANDLER_CHECKED |= {f"wdcalculator.api_wdcalculator_{n}" for n in ("save_estimate", "match_order", "unmatch_order")}
NO_ORDER_ID |= {f"wdcalculator.api_wdcalculator_{n}" for n in ("calculate", "search_estimates", "estimate", "search_orders")}

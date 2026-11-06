"""Blueprint registration helpers for the root app entrypoint.

Reads top-to-bottom: imports are grouped loosely by bounded-context lane for
navigation only; **registration order is the runtime contract** and must match
the historical root-app sequence (do not reorder calls below).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Flask


@dataclass(frozen=True)
class BlueprintBindings:
    """Runtime bindings the root `app` module must keep exporting.

    These are not blueprints: they are callables used during request handling
    and Socket.IO setup. Changing field names or meanings is a breaking change
    for `app.py` / `foms.platform.app_factory` consumers.
    """

    get_user_by_id: Callable[..., Any]
    register_chat_socketio_handlers: Callable[..., Any]


def register_blueprints(app: Flask) -> BlueprintBindings:
    """Register all blueprints in the existing root-app order."""
    from foms.web.auth import auth_bp, get_user_by_id

    # --- Lane: Auth (also supplies get_user_by_id binding) ---
    app.register_blueprint(auth_bp)

    from foms.platform.erp_blueprint import erp_bp

    # --- Lane: ERP hub / shell ---
    app.register_blueprint(erp_bp)

    # --- Imports: ERP HTML pages + API surfaces (see register block for order) ---
    from foms.web.orders import (
        erp_dashboard_bp,
        erp_history_bp,
        order_edit_bp,
        order_pages_bp,
        order_trash_bp,
    )
    from foms.web.drawing import erp_drawing_workbench_bp
    from foms.web.measurement import dashboards_bp, erp_measurement_dashboard_bp
    from foms.web.shipment import erp_shipment_page_bp
    from foms.web.cs import (
        erp_as_page_bp,
        erp_completion_page_bp,
        erp_settlement_page_bp,
    )
    from foms.web.production import erp_production_page_bp
    from foms.web.construction import erp_construction_page_bp
    from foms.api.files import files_bp
    from foms.api.address import address_bp
    from foms.api.orders import orders_bp
    from foms.api.notifications import notifications_bp
    from foms.api.notifications.push import push_bp, push_state_bp
    from foms.api.shipment import erp_shipment_bp
    from foms.api.measurement import erp_measurement_bp
    from foms.api.erp_map import erp_map_bp
    from foms.api.drawing import (
        erp_orders_drawing_bp,
        erp_orders_draftsman_bp,
        erp_orders_item_cancel_bp,
        erp_orders_revision_bp,
        erp_orders_drawing_wizard_bp,
    )
    from foms.api.production import erp_orders_production_bp
    from foms.api.construction import erp_orders_construction_bp
    from foms.api.cs import (
        erp_orders_as_bp,
        erp_orders_completion_bp,
        erp_orders_cs_bp,
        settlement_api_bp,
        settlement_channel_api_bp,
    )
    from foms.web.admin import storage_dashboard_bp
    from foms.api.wdcalculator import wdcalculator_bp
    from foms.web.admin import admin_bp, ops_ingest_bp
    from foms.api.attachments import attachments_bp
    from foms.api.tasks import tasks_bp
    from foms.api.events import events_bp
    from foms.api.quest import quest_bp
    from foms.api.erp_orders_blueprint import erp_orders_blueprint_bp
    from foms.api.erp_orders_structured import erp_orders_structured_bp
    from foms.api.erp_order_draft import erp_order_draft_bp
    from foms.api.erp_order_draft_send import erp_order_draft_send_bp
    from foms.api.channel import (
        channel_functions_bp,
        channel_integration_bp,
        channel_shortlink_bp,
        channel_wam_api_bp,
        channel_wam_bp,
        channel_webhooks_bp,
        chat_bp,
        register_chat_socketio_handlers,
    )
    from foms.web.channel import channel_chat_pages_bp
    from foms.api.kakao import kakao_bp
    from foms.api.share import share_api_bp, share_view_bp
    from foms.api.erp_estimates import erp_estimates_bp
    from foms.api.foms_rum import foms_rum_bp
    from foms.api.foms_search import foms_search_bp
    from foms.api.fragment import foms_fragment_bp
    from foms.api.foms_offline import foms_offline_bp
    from foms.api.ops_drift import ops_drift_bp
    from foms.api.ops_worker_heartbeat import ops_worker_heartbeat_bp
    # OPS-ROUTE-01: foms.api.debug.debug_bp 는 의도적으로 미등록(무인증 /debug-db 봉쇄).

    # --- Registration sequence (frozen): ERP page blueprints ---
    app.register_blueprint(erp_dashboard_bp)
    app.register_blueprint(erp_history_bp)
    app.register_blueprint(erp_drawing_workbench_bp)
    app.register_blueprint(erp_measurement_dashboard_bp)
    app.register_blueprint(erp_shipment_page_bp)
    app.register_blueprint(erp_as_page_bp)
    app.register_blueprint(erp_production_page_bp)
    app.register_blueprint(erp_construction_page_bp)
    app.register_blueprint(erp_completion_page_bp)
    # Core APIs: files / address / orders / notifications / shipment / measurement / map
    app.register_blueprint(files_bp)
    app.register_blueprint(address_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(push_bp)
    app.register_blueprint(push_state_bp)
    app.register_blueprint(erp_shipment_bp)
    app.register_blueprint(erp_measurement_bp)
    app.register_blueprint(erp_map_bp)
    app.register_blueprint(erp_orders_drawing_bp)
    app.register_blueprint(erp_orders_revision_bp)
    app.register_blueprint(erp_orders_draftsman_bp)
    app.register_blueprint(erp_orders_item_cancel_bp)
    app.register_blueprint(erp_orders_drawing_wizard_bp)
    app.register_blueprint(erp_orders_production_bp)
    app.register_blueprint(erp_orders_construction_bp)
    app.register_blueprint(erp_orders_cs_bp)
    app.register_blueprint(erp_orders_as_bp)
    app.register_blueprint(erp_orders_completion_bp)
    # Storage UI, chat (Socket.IO handler binding imported with chat_bp), WD calculator
    app.register_blueprint(storage_dashboard_bp)
    app.register_blueprint(channel_chat_pages_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(wdcalculator_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ops_ingest_bp)
    app.register_blueprint(dashboards_bp)
    # Auxiliary APIs: attachments / tasks / events / quest / structured order payloads
    app.register_blueprint(attachments_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(quest_bp)
    app.register_blueprint(erp_orders_blueprint_bp)
    app.register_blueprint(erp_orders_structured_bp)
    app.register_blueprint(erp_order_draft_bp)
    # 마법사 초안 발송(알림톡·실측 PUSH) — 초안 API 바로 뒤(같은 /api/erp/order-draft 계열)
    app.register_blueprint(erp_order_draft_send_bp)
    app.register_blueprint(order_pages_bp)
    app.register_blueprint(order_edit_bp)
    app.register_blueprint(order_trash_bp)
    # Channel: three modules, six registrations (channel_wam exports three blueprints)
    app.register_blueprint(channel_integration_bp)
    app.register_blueprint(channel_functions_bp)
    app.register_blueprint(channel_webhooks_bp)
    app.register_blueprint(channel_shortlink_bp)
    app.register_blueprint(channel_wam_bp)
    app.register_blueprint(channel_wam_api_bp)
    # Kakao: 알림톡 수동 발송(미리보기 + 발송) — 채널톡과 독립된 얇은 계층
    app.register_blueprint(kakao_bp)
    app.register_blueprint(share_view_bp)
    app.register_blueprint(share_api_bp)
    app.register_blueprint(erp_estimates_bp)
    app.register_blueprint(foms_rum_bp)
    app.register_blueprint(foms_search_bp)
    app.register_blueprint(foms_fragment_bp)
    app.register_blueprint(foms_offline_bp)
    # 정산 대시보드(SETTLE-DASH-01): 페이지 + 집계 API. 위 시퀀스는 런타임 계약이라
    # 재배열하지 않고 **뒤에만** 덧붙인다(경로가 고유해 shadowing 없음).
    app.register_blueprint(erp_settlement_page_bp)
    app.register_blueprint(settlement_api_bp)
    # SETTLE-CHANNEL-01: 채널(네이버) 정산 탭 API. 위와 경로가 겹치지 않는다
    # (/api/settlement/channel* 은 aggregates·rows 와 다른 prefix).
    app.register_blueprint(settlement_channel_api_bp)
    # OPS-DRIFT-01: 드리프트 감사 2종의 admin 전용 조회로(GET 1개). 위 시퀀스와 경로가
    # 겹치지 않아(/api/foms/ops/*) shadowing 이 없고, 규약대로 **뒤에만** 덧붙인다.
    app.register_blueprint(ops_drift_bp)
    app.register_blueprint(ops_worker_heartbeat_bp)
    # OPS-ROUTE-01: debug_bp 미등록 → deployed 앱에 /debug-db 라우트 0.

    # --- Lane: 외부 협력사 화면(PARTNER-02) — /partner(HTML) · /api/partner(JSON). 경로가 고유해
    # shadowing 이 없고 규약대로 **뒤에만** 덧붙인다. 협력사 세션은 문지기 허용 목록만 지난다.
    from foms.api.partner import partner_api_bp, partner_channel_push_bp, partner_notice_bp, partner_order_delete_bp
    from foms.web.partner import partner_portal_bp

    app.register_blueprint(partner_api_bp)
    # 협력사 주문 화면 영발 · 발주 PUSH(2026-10-29) — /api/partner/orders/<id>/channel-push 하나뿐이라 겹치지 않는다.
    app.register_blueprint(partner_channel_push_bp)
    # 협력사 공지 확인(2026-11-02) — /api/partner/notices/<id>/ack 하나뿐이라 겹치지 않는다.
    app.register_blueprint(partner_notice_bp)
    # 협력사 주문 지우기(2026-11-04) — /api/partner/orders/<id>/delete 하나뿐이라 겹치지 않는다.
    app.register_blueprint(partner_order_delete_bp)
    app.register_blueprint(partner_portal_bp)

    # --- Lane: FOMS 공지사항(본사 · 협력사, 2026-11-02 설계서 2026-11-02-foms-notices). 경로가 고유해
    # shadowing 이 없고 규약대로 **뒤에만** 덧붙인다.
    from foms.api.notices import notices_admin_api_bp, notices_api_bp
    from foms.web.admin.notices import notices_admin_bp
    from foms.web.notices import notices_web_bp

    app.register_blueprint(notices_admin_api_bp)
    app.register_blueprint(notices_api_bp)
    app.register_blueprint(notices_admin_bp)
    app.register_blueprint(notices_web_bp)

    # --- Lane: AI 도면팀원 학습 요약(GET /api/drawing-agent/digest, 토큰 전용 · 읽기만). 경로가 고유해
    # shadowing 이 없고 규약대로 **뒤에만** 덧붙인다. 설계서 docs/plans/2026-10-27-drawing-ai-teammate-spec.md
    from foms.api.drawing_agent import drawing_agent_bp

    app.register_blueprint(drawing_agent_bp)

    # --- Lane: AI 상담팀원 관리 패널 JSON(/api/admin/cs-agent/*, ADMIN 만 · 쓰기는 CSRF). 화면(/admin/cs-agent)은
    # admin_bp 에 붙는다. 경로가 고유해 shadowing 이 없고 규약대로 **뒤에만** 덧붙인다. 설계서 2026-10-27-cs-ai-agent 16.1
    from foms.api.admin import cs_agent_admin_api_bp

    app.register_blueprint(cs_agent_admin_api_bp)

    # --- Lane: AI 상담팀원 PC 반복 비상 정지 읽기(GET /api/cs-agent/pc-switch, 머리값 열쇠 전용 · 읽기만). 경로가 고유해
    # shadowing 이 없고 규약대로 **뒤에만** 덧붙인다. 토큰 읽기 길(drawing_agent digest)과 같은 꼴.
    from foms.api.cs_agent_pc import cs_agent_pc_bp

    app.register_blueprint(cs_agent_pc_bp)

    # --- Lane: AI 상담 초안 [보내기] · [수정하기](플랜 C10-3 · 설계서 17.2.1 링크 길) — 짧은 화면(/cs-agent/turns/<id>/send ·
    # edit, 로그인 · 상담 직원 · ADMIN) + JSON(/api/cs-agent/turns/<id>/*, 쓰기는 CSRF · 정책 CS_AGENT_SEND). 경로가 고유해
    # shadowing 이 없고 규약대로 **뒤에만** 덧붙인다.
    from foms.api.cs_agent_send import cs_agent_send_api_bp
    from foms.web.cs_agent_send import cs_agent_send_page_bp

    app.register_blueprint(cs_agent_send_page_bp)
    app.register_blueprint(cs_agent_send_api_bp)

    # --- Lane: AI 초안 채널톡 안 작은 창(WAM — 설계서 17.2.2) — 빈 틀 화면(/channel/wam/cs-draft, 로그인 없음 · 글 없음).
    # 글 · 보내기는 서명된 앱 함수(/api/channel/functions)로만. 옛 /channel/wam 블루프린트와 따로라 그 410 앞 검사를 타지
    # 않는다. 경로가 고유해 shadowing 이 없고 규약대로 **뒤에만** 덧붙인다.
    from foms.web.cs_draft_wam import cs_draft_wam_bp

    app.register_blueprint(cs_draft_wam_bp)

    # --- Lane: [수정하기] '왜 고쳤나요(자세히)' · 사진(설계서 17.6.1 · D94) — JSON(/api/cs-agent/turns/<id>/edit-detail ·
    # edit-photos, 쓰기는 CSRF · 정책 CS_AGENT_SEND) + 주간 고침 안 승인(/api/admin/cs-agent/fix-proposals, ADMIN 만 · 정책
    # ADMIN_OPS). 사진 원본 보기는 위 화면 블루프린트(/cs-agent/turns/<id>/photos/<seq>)다. 경로가 고유해 shadowing 이 없고
    # 규약대로 **뒤에만** 덧붙인다.
    from foms.api.cs_agent_edit_detail import cs_agent_edit_api_bp
    from foms.api.cs_agent_fix_proposals import cs_agent_fix_api_bp

    app.register_blueprint(cs_agent_edit_api_bp)
    app.register_blueprint(cs_agent_fix_api_bp)

    # --- Lane: 회사 지식(HAUD master brain 설계서 7.5 · ⑤-2) — 화면(/brain · /brain/items/<키>) + 읽기 JSON(/api/brain/*).
    # ADMIN · 층 승인자 팀 MANAGER 만(그 밖 404) · 모두 GET(쓰기 없음). 경로가 고유해 shadowing 이 없고 규약대로 **뒤에만**
    # 덧붙인다.
    from foms.api.brain import brain_api_bp
    from foms.web.brain import brain_web_bp

    app.register_blueprint(brain_web_bp)
    app.register_blueprint(brain_api_bp)

    # --- Lane: 회사 지식 제안함 · 다시 확인 · 판 되돌리기(설계서 7.5 화면 4 · 5 · 6 · ⑤-3) — JSON(/api/brain/inbox · proposals ·
    # recheck · releases/<번호>/rollback · metrics). 쓰기는 CSRF · 정책 MANAGER_MUTATION(판 되돌리기 ADMIN_OPS), 실제 결정 판정은
    # 서비스(층 승인자 · 사장님 몫 — D101). 읽기 API 와 같은 접두지만 경로가 겹치지 않고 규약대로 **뒤에만** 덧붙인다.
    from foms.api.brain_review import brain_review_api_bp

    app.register_blueprint(brain_review_api_bp)

    # --- Lane: 회사 지식 물어보기(직원 챗봇 — 설계서 10절 · D88 · D99 · ⑤-5) — JSON(/api/brain/chat/*). 여는 단계(admin → leads →
    # all)는 라우트가 다시 보고 그 밖 404 · 쓰기는 CSRF · 정책 BRAIN_ASK(설정 저장 ADMIN_OPS). 챗봇은 지식 정본을 쓰지 않는다.
    # 같은 접두 아래 고유 경로(/chat/…)라 겹치지 않고 규약대로 **뒤에만** 덧붙인다.
    from foms.api.brain_chat import brain_chat_api_bp

    app.register_blueprint(brain_chat_api_bp)

    # --- Lane: 협력사 단가표(ADMIN 전용 JSON — /api/admin/partners/<id>/price-lists, 설계서 2026-11-03-partner-statement
    # §5.1). 화면은 admin_bp 의 /admin/partners/<id>/price-list. 쓰기는 CSRF · 정책 ADMIN_OPS. 경로가 고유해 shadowing 이
    # 없고 규약대로 **뒤에만** 덧붙인다.
    from foms.api.partner_price_list import partner_price_list_api_bp

    app.register_blueprint(partner_price_list_api_bp)

    # --- Lane: 협력사 주문 옵션 직원 읽기(GET /api/orders/<id>/partner-options — 도면 전달 창, 설계서 2026-11-03-partner-statement
    # §5.3). 읽기 전용. 경로가 고유해 shadowing 이 없고 규약대로 **뒤에만** 덧붙인다.
    from foms.api.partner_options_staff import partner_options_staff_api_bp

    app.register_blueprint(partner_options_staff_api_bp)

    # --- Lane: 협력사 거래명세서 우리 CS(화면 /erp/partner-statements · JSON /api/partner-statements — 설계서
    # 2026-11-03-partner-statement §5.5). ADMIN 또는 CS 권한 팀만, 쓰기는 CSRF · 정책 PARTNER_STATEMENT. 경로가 고유해
    # shadowing 이 없고 규약대로 **뒤에만** 덧붙인다.
    from foms.api.partner_payments_staff import partner_payments_staff_api_bp
    from foms.api.partner_statements_staff import partner_statements_staff_api_bp
    from foms.web.cs.partner_statements import erp_partner_statements_page_bp

    app.register_blueprint(partner_statements_staff_api_bp)
    # 입금 장부(5단계 — /api/partner-payments): 명세서와 같은 권한 · 정책.
    app.register_blueprint(partner_payments_staff_api_bp)
    # 단가표 전 주문 옵션 채우기(결정 12 — /api/partner-statements/fill · /orders/<id>/options): 같은 권한 · 정책.
    from foms.api.partner_option_fill_staff import partner_option_fill_api_bp

    app.register_blueprint(partner_option_fill_api_bp)
    app.register_blueprint(erp_partner_statements_page_bp)

    # --- Lane: 협력사 거래명세서 협력사 쪽(화면 /partner/statements · JSON /api/partner/statements — 설계서
    # 2026-11-03-partner-statement §5.6). 협력사 계정만(partner_required · 문지기 허용 목록). 경로가 고유해 shadowing 이
    # 없고 규약대로 **뒤에만** 덧붙인다.
    from foms.api.partner.statements import partner_statements_api_bp
    from foms.web.partner.statements import partner_statements_portal_bp

    app.register_blueprint(partner_statements_api_bp)
    app.register_blueprint(partner_statements_portal_bp)

    # --- Lane: Infra liveness (Railway healthcheck / keep-warm 프로브) ---
    from foms.api.health import health_bp

    app.register_blueprint(health_bp)

    # --- Lane: 프리랜서 영업 수수료 설정(JSON — /api/admin/sales-freelancers, 설계서 2026-11-06-freelancer-sales-commission
    # §2.3 · §9). 읽기 회계팀 · 관리자, 쓰기 ADMIN(CSRF · 정책 ADMIN_OPS). 화면(/admin/sales-freelancers)은 admin_bp 에 붙는다.
    # 경로가 고유해 shadowing 이 없고 규약대로 **뒤에만** 덧붙인다.
    from foms.api.admin import sales_freelancers_admin_api_bp

    app.register_blueprint(sales_freelancers_admin_api_bp)

    # --- Lane: 프리랜서 영업 수수료 탭(JSON — /api/sales-commission, 설계서 2026-11-06-freelancer-sales-commission §2.1 · §9).
    # 읽기 · 쓰기 모두 회계팀 · 관리자(is_accounting_or_admin), 쓰기는 CSRF · 정책 SALES_COMMISSION_WRITE. 경로가 고유해
    # shadowing 이 없고 규약대로 **뒤에만** 덧붙인다.
    from foms.api.sales_commission import sales_commission_api_bp

    app.register_blueprint(sales_commission_api_bp)

    return BlueprintBindings(
        get_user_by_id=get_user_by_id,
        register_chat_socketio_handlers=register_chat_socketio_handlers,
    )

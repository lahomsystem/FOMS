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
        erp_orders_revision_bp,
        erp_orders_drawing_wizard_bp,
    )
    from foms.api.production import erp_orders_production_bp
    from foms.api.construction import erp_orders_construction_bp
    from foms.api.cs import (
        erp_orders_as_bp,
        erp_orders_completion_bp,
        erp_orders_confirm_bp,
        erp_orders_cs_bp,
        settlement_api_bp,
        settlement_channel_api_bp,
    )
    from foms.api.personal_board import personal_board_bp
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
    app.register_blueprint(erp_orders_drawing_wizard_bp)
    app.register_blueprint(erp_orders_production_bp)
    app.register_blueprint(erp_orders_construction_bp)
    app.register_blueprint(erp_orders_cs_bp)
    app.register_blueprint(erp_orders_as_bp)
    app.register_blueprint(erp_orders_completion_bp)
    app.register_blueprint(personal_board_bp)
    app.register_blueprint(erp_orders_confirm_bp)
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
    # OPS-ROUTE-01: debug_bp 미등록 → deployed 앱에 /debug-db 라우트 0.

    # --- Lane: Infra liveness (Railway healthcheck / keep-warm 프로브) ---
    from foms.api.health import health_bp

    app.register_blueprint(health_bp)

    return BlueprintBindings(
        get_user_by_id=get_user_by_id,
        register_chat_socketio_handlers=register_chat_socketio_handlers,
    )

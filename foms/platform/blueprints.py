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
    from apps.auth import auth_bp, get_user_by_id

    # --- Lane: Auth (also supplies get_user_by_id binding) ---
    app.register_blueprint(auth_bp)

    from apps.erp import erp_bp

    # --- Lane: ERP hub / shell ---
    app.register_blueprint(erp_bp)

    # --- Imports: ERP HTML pages + API surfaces (see register block for order) ---
    from apps.erp_dashboard import erp_dashboard_bp
    from apps.erp_history_page import erp_history_bp
    from apps.erp_drawing_workbench import erp_drawing_workbench_bp
    from apps.erp_measurement_dashboard import erp_measurement_dashboard_bp
    from apps.erp_shipment_page import erp_shipment_page_bp
    from apps.erp_as_page import erp_as_page_bp
    from apps.erp_production_page import erp_production_page_bp
    from apps.erp_construction_page import erp_construction_page_bp
    from apps.erp_completion_page import erp_completion_page_bp
    from apps.api.files import files_bp
    from apps.api.address import address_bp
    from apps.api.orders import orders_bp
    from apps.api.notifications import notifications_bp
    from apps.api.erp_shipment_settings import erp_shipment_bp
    from apps.api.erp_measurement import erp_measurement_bp
    from apps.api.erp_map import erp_map_bp
    from apps.api.erp_orders_drawing import erp_orders_drawing_bp
    from apps.api.erp_orders_revision import erp_orders_revision_bp
    from apps.api.erp_orders_draftsman import erp_orders_draftsman_bp
    from apps.api.erp_orders_production import erp_orders_production_bp
    from apps.api.erp_orders_construction import erp_orders_construction_bp
    from apps.api.erp_orders_cs import erp_orders_cs_bp
    from apps.api.erp_orders_as import erp_orders_as_bp
    from apps.api.erp_orders_completion import erp_orders_completion_bp
    from apps.api.personal_board import personal_board_bp
    from apps.api.erp_orders_confirm import erp_orders_confirm_bp
    from apps.storage_dashboard import storage_dashboard_bp
    from apps.api.chat import chat_bp, register_chat_socketio_handlers
    from apps.api.wdcalculator import wdcalculator_bp
    from apps.api.backup import backup_bp
    from apps.admin import admin_bp
    from apps.user_pages import user_pages_bp
    from apps.dashboards import dashboards_bp
    from apps.api.attachments import attachments_bp
    from apps.api.tasks import tasks_bp
    from apps.api.events import events_bp
    from apps.api.quest import quest_bp
    from apps.api.erp_orders_blueprint import erp_orders_blueprint_bp
    from apps.api.erp_orders_structured import erp_orders_structured_bp
    from apps.order_pages import order_pages_bp
    from apps.order_edit import order_edit_bp
    from apps.order_trash import order_trash_bp
    from apps.excel_import import excel_bp
    from apps.calendar_page import calendar_bp
    from apps.wdplanner_page import wdplanner_bp
    from apps.api.channel_integration import channel_integration_bp
    from apps.api.channel_functions import channel_functions_bp
    from apps.api.channel_webhooks import channel_webhooks_bp
    from apps.api.channel_wam import (
        channel_shortlink_bp,
        channel_wam_api_bp,
        channel_wam_bp,
    )
    from apps.api.erp_estimates import erp_estimates_bp
    from apps.api.debug import debug_bp

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
    app.register_blueprint(erp_shipment_bp)
    app.register_blueprint(erp_measurement_bp)
    app.register_blueprint(erp_map_bp)
    app.register_blueprint(erp_orders_drawing_bp)
    app.register_blueprint(erp_orders_revision_bp)
    app.register_blueprint(erp_orders_draftsman_bp)
    app.register_blueprint(erp_orders_production_bp)
    app.register_blueprint(erp_orders_construction_bp)
    app.register_blueprint(erp_orders_cs_bp)
    app.register_blueprint(erp_orders_as_bp)
    app.register_blueprint(erp_orders_completion_bp)
    app.register_blueprint(personal_board_bp)
    app.register_blueprint(erp_orders_confirm_bp)
    # Storage UI, chat (Socket.IO handler binding imported with chat_bp), WD calculator, backup
    app.register_blueprint(storage_dashboard_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(wdcalculator_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(user_pages_bp)
    app.register_blueprint(dashboards_bp)
    # Auxiliary APIs: attachments / tasks / events / quest / structured order payloads
    app.register_blueprint(attachments_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(quest_bp)
    app.register_blueprint(erp_orders_blueprint_bp)
    app.register_blueprint(erp_orders_structured_bp)
    app.register_blueprint(order_pages_bp)
    app.register_blueprint(order_edit_bp)
    app.register_blueprint(order_trash_bp)
    app.register_blueprint(excel_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(wdplanner_bp)
    # Channel: three modules, six registrations (channel_wam exports three blueprints)
    app.register_blueprint(channel_integration_bp)
    app.register_blueprint(channel_functions_bp)
    app.register_blueprint(channel_webhooks_bp)
    app.register_blueprint(channel_shortlink_bp)
    app.register_blueprint(channel_wam_bp)
    app.register_blueprint(channel_wam_api_bp)
    app.register_blueprint(erp_estimates_bp)
    app.register_blueprint(debug_bp)

    return BlueprintBindings(
        get_user_by_id=get_user_by_id,
        register_chat_socketio_handlers=register_chat_socketio_handlers,
    )

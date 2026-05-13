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
    from foms.web.cs import erp_as_page_bp, erp_completion_page_bp
    from foms.web.production import erp_production_page_bp
    from foms.web.construction import erp_construction_page_bp
    from foms.api.files import files_bp
    from foms.api.address import address_bp
    from foms.api.orders import orders_bp
    from foms.api.notifications import notifications_bp
    from foms.api.shipment import erp_shipment_bp
    from foms.api.measurement import erp_measurement_bp
    from foms.api.erp_map import erp_map_bp
    from foms.api.drawing import (
        erp_orders_drawing_bp,
        erp_orders_draftsman_bp,
        erp_orders_revision_bp,
    )
    from foms.api.production import erp_orders_production_bp
    from foms.api.construction import erp_orders_construction_bp
    from foms.api.cs import (
        erp_orders_as_bp,
        erp_orders_completion_bp,
        erp_orders_confirm_bp,
        erp_orders_cs_bp,
    )
    from foms.api.personal_board import personal_board_bp
    from foms.web.admin import excel_bp, storage_dashboard_bp
    from foms.api.wdcalculator import wdcalculator_bp
    from foms.api.backup import backup_bp
    from foms.web.admin import admin_bp
    from foms.api.attachments import attachments_bp
    from foms.api.tasks import tasks_bp
    from foms.api.events import events_bp
    from foms.api.quest import quest_bp
    from foms.api.erp_orders_blueprint import erp_orders_blueprint_bp
    from foms.api.erp_orders_structured import erp_orders_structured_bp
    from foms.web.wdcalculator import wdplanner_bp
    from foms.web.designer import designer_bp
    from foms.api.designer import (
        designer_projects_bp,
        designer_validation_bp,
        designer_ai_runs_bp,
        designer_ontology_bp,
    )
    from foms.api.designer.commands import commands_bp as designer_commands_bp
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
    from foms.api.erp_estimates import erp_estimates_bp
    from foms.api.debug import debug_bp

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
    app.register_blueprint(channel_chat_pages_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(wdcalculator_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(admin_bp)
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
    app.register_blueprint(wdplanner_bp)
    app.register_blueprint(designer_bp)
    app.register_blueprint(designer_projects_bp)
    app.register_blueprint(designer_validation_bp)
    app.register_blueprint(designer_ai_runs_bp)
    app.register_blueprint(designer_ontology_bp)
    app.register_blueprint(designer_commands_bp)
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

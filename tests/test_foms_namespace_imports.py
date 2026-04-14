"""Smoke tests for the Step 3 runtime namespace shims."""

import inspect
from pathlib import Path

import db as legacy_db
import services.db_url_resolver as legacy_db_url_resolver
import services.db_indexes as legacy_db_indexes
import services.as_content_safety as legacy_as_content_safety
import services.channel_dispatch as legacy_channel_dispatch
import services.channel_delivery as legacy_channel_delivery
import services.channel_inbound as legacy_channel_inbound
import services.channel_client as legacy_channel_client
import services.channel_quick_actions as legacy_channel_quick_actions
import services.channel_event_payloads as legacy_channel_event_payloads
import services.channel_identity as legacy_channel_identity
import services.channel_policy as legacy_channel_policy
import services.channel_security as legacy_channel_security
import services.channel_wam_attachments as legacy_channel_wam_attachments
import services.channel_wam_telemetry as legacy_channel_wam_telemetry
import services.channel_wam_service as legacy_channel_wam_service
import services.channel_wam_read_model as legacy_channel_wam_read_model
import services.channel_wam_view_models as legacy_channel_wam_view_models
import services.app_init as legacy_app_init
import services.context_processors as legacy_context_processors
import services.erp_permissions as legacy_erp_permissions
import services.file_utils as legacy_file_utils
import services.menu_config as legacy_menu_config
import services.order_display_utils as legacy_order_display_utils
import services.order_date_sync as legacy_order_date_sync
import services.order_date_sync_event as legacy_order_date_sync_event
import services.order_geocode as legacy_order_geocode
import services.order_attachment_thumbnail as legacy_order_attachment_thumbnail
import services.order_storage_cleanup as legacy_order_storage_cleanup
import services.erp_display as legacy_erp_display
import services.erp_order_detail as legacy_erp_order_detail
import services.erp_product_items as legacy_erp_product_items
import services.erp_shipment_settings as legacy_erp_shipment_settings
import services.erp_sync_columns as legacy_erp_sync_columns
import services.erp_template_filters as legacy_erp_template_filters
import services.erp_utils as legacy_erp_utils
import services.estimate_service as legacy_estimate_service
import services.geocode_helpers as legacy_geocode_helpers
import services.map_snapshot as legacy_map_snapshot
import services.measurement_manager_colors as legacy_measurement_manager_colors
import services.rate_limit as legacy_rate_limit
import services.realtime_notifications as legacy_realtime_notifications
import services.request_utils as legacy_request_utils
import services.storage as legacy_storage
import services.user_deletion as legacy_user_deletion
import services.erp_policy as legacy_erp_policy
import services.jobs.queue as legacy_jobs_queue
import services.jobs.tasks as legacy_jobs_tasks
import models as legacy_models

import foms.services.db_url_resolver as namespaced_db_url_resolver
import foms.services.db_indexes as namespaced_db_indexes
import foms.services.as_content_safety as namespaced_as_content_safety
import foms.services.channel_dispatch as namespaced_channel_dispatch
import foms.services.channel_delivery as namespaced_channel_delivery
import foms.services.channel_inbound as namespaced_channel_inbound
import foms.services.channel_client as namespaced_channel_client
import foms.services.channel_quick_actions as namespaced_channel_quick_actions
import foms.services.channel_event_payloads as namespaced_channel_event_payloads
import foms.services.channel_identity as namespaced_channel_identity
import foms.services.channel_policy as namespaced_channel_policy
import foms.services.channel_security as namespaced_channel_security
import foms.services.channel_wam_attachments as namespaced_channel_wam_attachments
import foms.services.channel_wam_service as namespaced_channel_wam_service
import foms.services.channel_wam_telemetry as namespaced_channel_wam_telemetry
import foms.services.channel_wam_read_model as namespaced_channel_wam_read_model
import foms.services.channel_wam_view_models as namespaced_channel_wam_view_models
import foms.services.app_init as namespaced_app_init
import foms.services.context_processors as namespaced_context_processors
import foms.services.erp_permissions as namespaced_erp_permissions
import foms.services.file_utils as namespaced_file_utils
import foms.services.menu_config as namespaced_menu_config
import foms.services.order_display_utils as namespaced_order_display_utils
import foms.services.order_date_sync as namespaced_order_date_sync
import foms.services.order_date_sync_event as namespaced_order_date_sync_event
import foms.services.order_geocode as namespaced_order_geocode
import foms.services.order_attachment_thumbnail as namespaced_order_attachment_thumbnail
import foms.services.order_storage_cleanup as namespaced_order_storage_cleanup
import foms.services.erp_display as namespaced_erp_display
import foms.services.erp_order_detail as namespaced_erp_order_detail
import foms.services.erp_product_items as namespaced_erp_product_items
import foms.services.erp_shipment_settings as namespaced_erp_shipment_settings
import foms.services.erp_sync_columns as namespaced_erp_sync_columns
import foms.services.erp_template_filters as namespaced_erp_template_filters
import foms.services.erp_utils as namespaced_erp_utils
import foms.services.estimate_service as namespaced_estimate_service
import foms.services.geocode_helpers as namespaced_geocode_helpers
import foms.services.map_snapshot as namespaced_map_snapshot
import foms.services.measurement_manager_colors as namespaced_measurement_manager_colors
import foms.services.rate_limit as namespaced_rate_limit
import foms.services.realtime_notifications as namespaced_realtime_notifications
import foms.services.request_utils as namespaced_request_utils
import foms.services.storage as namespaced_storage
import foms.services.user_deletion as namespaced_user_deletion
import foms.services.erp_policy as namespaced_erp_policy
import foms.services.jobs.queue as namespaced_jobs_queue
import foms.services.jobs.tasks as namespaced_jobs_tasks
from foms.persistence.main import db as namespaced_db
from foms.persistence.main import models as namespaced_models


def test_namespaced_db_reexports_legacy_contract() -> None:
    """The namespaced DB module should expose the same core objects."""
    assert namespaced_db.Base is legacy_db.Base
    assert namespaced_db.engine is legacy_db.engine
    assert namespaced_db.db_session is legacy_db.db_session


def test_namespaced_models_reexport_legacy_classes() -> None:
    """The namespaced models module should expose legacy model classes unchanged."""
    assert namespaced_models.Order is legacy_models.Order
    assert namespaced_models.OrderScheduleDate is legacy_models.OrderScheduleDate
    assert namespaced_models.SystemSetting is legacy_models.SystemSetting
    assert namespaced_models.User is legacy_models.User


def test_legacy_map_snapshot_shim_preserves_canonical_functions() -> None:
    """The legacy services path should re-export the canonical map snapshot functions."""
    assert legacy_map_snapshot.__all__ == [
        "build_measurement_map_query",
        "build_measurement_snapshot",
    ]
    assert namespaced_map_snapshot.__all__ == [
        "build_measurement_map_query",
        "build_measurement_snapshot",
    ]
    assert (
        legacy_map_snapshot.build_measurement_map_query
        is namespaced_map_snapshot.build_measurement_map_query
    )
    assert (
        legacy_map_snapshot.build_measurement_snapshot
        is namespaced_map_snapshot.build_measurement_snapshot
    )
    assert not hasattr(legacy_map_snapshot, "normalize_manager_name")


def test_legacy_request_utils_shim_preserves_canonical_functions() -> None:
    """The legacy services path should re-export the canonical request utils function."""
    assert legacy_request_utils.__all__ == ["get_preserved_filter_args"]
    assert namespaced_request_utils.__all__ == ["get_preserved_filter_args"]
    assert (
        legacy_request_utils.get_preserved_filter_args
        is namespaced_request_utils.get_preserved_filter_args
    )


def test_legacy_rate_limit_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical rate limiter helper."""
    expected_public_names = ["init_limiter"]

    assert legacy_rate_limit.__all__ == expected_public_names
    assert namespaced_rate_limit.__all__ == expected_public_names
    assert legacy_rate_limit.init_limiter is namespaced_rate_limit.init_limiter


def test_app_uses_canonical_rate_limit_import() -> None:
    """App bootstrap should bind the canonical rate limit initializer."""
    import app

    assert app.init_limiter is namespaced_rate_limit.init_limiter


def test_legacy_realtime_notifications_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical realtime notification helper."""
    expected_public_names = ["emit_erp_notification_to_users"]

    assert legacy_realtime_notifications.__all__ == expected_public_names
    assert namespaced_realtime_notifications.__all__ == expected_public_names
    assert (
        legacy_realtime_notifications.emit_erp_notification_to_users
        is namespaced_realtime_notifications.emit_erp_notification_to_users
    )


def test_notifications_package_submodule_matches_flat_and_legacy() -> None:
    """Root shim, flat compat, and package submodule expose the same function object."""
    import foms.services.notifications.realtime_notifications as pkg_rt

    assert (
        legacy_realtime_notifications.emit_erp_notification_to_users
        is namespaced_realtime_notifications.emit_erp_notification_to_users
    )
    assert (
        namespaced_realtime_notifications.emit_erp_notification_to_users
        is pkg_rt.emit_erp_notification_to_users
    )


def test_erp_orders_drawing_uses_canonical_realtime_notification_import() -> None:
    """Drawing API should bind realtime notification helper from the canonical namespace."""
    from apps.api import erp_orders_drawing

    assert (
        erp_orders_drawing.emit_erp_notification_to_users
        is namespaced_realtime_notifications.emit_erp_notification_to_users
    )


def test_erp_orders_revision_uses_canonical_realtime_notification_import() -> None:
    """Revision API should bind realtime notification helper from the canonical namespace."""
    from apps.api import erp_orders_revision

    assert (
        erp_orders_revision.emit_erp_notification_to_users
        is namespaced_realtime_notifications.emit_erp_notification_to_users
    )


def test_notifications_api_uses_canonical_realtime_notification_lazy_imports() -> None:
    """Notification API lazy imports should point at the canonical namespace path."""
    from apps.api import notifications

    send_source = inspect.getsource(notifications.api_notifications_send)
    urgent_source = inspect.getsource(notifications.api_order_urgent_mention)

    expected_import = (
        "from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users"
    )
    assert expected_import in send_source
    assert expected_import in urgent_source


def test_legacy_user_deletion_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical user deletion helpers."""
    expected_public_names = [
        "detach_user_references_for_delete",
        "ensure_order_attachment_user_fk_set_null",
    ]

    assert legacy_user_deletion.__all__ == expected_public_names
    assert namespaced_user_deletion.__all__ == expected_public_names
    assert (
        legacy_user_deletion.detach_user_references_for_delete
        is namespaced_user_deletion.detach_user_references_for_delete
    )
    assert (
        legacy_user_deletion.ensure_order_attachment_user_fk_set_null
        is namespaced_user_deletion.ensure_order_attachment_user_fk_set_null
    )


def test_auth_uses_canonical_user_deletion_import() -> None:
    """Auth routes should bind the canonical user deletion cleanup helper."""
    from apps import auth

    assert (
        auth.detach_user_references_for_delete
        is namespaced_user_deletion.detach_user_references_for_delete
    )


def test_attachments_api_uses_canonical_user_deletion_import() -> None:
    """Attachment API should bind the canonical attachment FK repair helper."""
    from apps.api import attachments

    assert (
        attachments.ensure_order_attachment_user_fk_set_null
        is namespaced_user_deletion.ensure_order_attachment_user_fk_set_null
    )


def test_legacy_db_indexes_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical DB index helpers."""
    expected_public_names = [
        "apply_phase2_indexes",
        "ensure_erp_date_columns",
    ]

    assert legacy_db_indexes.__all__ == expected_public_names
    assert namespaced_db_indexes.__all__ == expected_public_names
    assert legacy_db_indexes.apply_phase2_indexes is namespaced_db_indexes.apply_phase2_indexes
    assert legacy_db_indexes.ensure_erp_date_columns is namespaced_db_indexes.ensure_erp_date_columns


def test_legacy_app_init_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical app init entrypoint."""
    expected_public_names = ["run_auto_init"]

    assert legacy_app_init.__all__ == expected_public_names
    assert namespaced_app_init.__all__ == expected_public_names
    assert legacy_app_init.run_auto_init is namespaced_app_init.run_auto_init
    assert not hasattr(legacy_app_init, "_backfill_erp_flat_columns")


def test_app_uses_canonical_app_init_import() -> None:
    """App bootstrap should bind the canonical app init entrypoint."""
    import app

    assert app.run_auto_init is namespaced_app_init.run_auto_init


def test_app_exposes_public_bootstrap_helper_contract() -> None:
    """App bootstrap should keep the root helper exports wired to canonical modules."""
    import app

    assert hasattr(app, "app")
    assert hasattr(app, "socketio")
    assert hasattr(app, "SOCKETIO_AVAILABLE")
    assert app.run_auto_init is namespaced_app_init.run_auto_init
    assert app.init_limiter is namespaced_rate_limit.init_limiter
    assert app.register_context_processors is namespaced_context_processors.register_context_processors


def test_app_init_canonical_module_uses_canonical_persistence_imports() -> None:
    """Canonical app init should bind persistence helpers from the namespace package."""
    module_source = inspect.getsource(namespaced_app_init)
    backfill_source = inspect.getsource(namespaced_app_init._backfill_erp_flat_columns)

    assert "from foms.persistence.main.db import get_db, init_db" in module_source
    assert "from foms.persistence.main.models import User" in module_source
    assert "from foms.persistence.main.models import Order" in backfill_source


def test_app_init_uses_canonical_db_indexes_lazy_import() -> None:
    """App init should lazy import DB index helpers from the canonical namespace."""
    run_auto_init_source = inspect.getsource(namespaced_app_init.run_auto_init)
    expected_import = "from foms.services.db_indexes import apply_phase2_indexes, ensure_erp_date_columns"
    assert expected_import in run_auto_init_source


def test_legacy_order_date_sync_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical order date sync helpers."""
    expected_public_names = [
        "collect_order_schedule_date_specs",
        "sync_order_dates",
        "register_date_sync_listener",
    ]

    assert legacy_order_date_sync.__all__ == expected_public_names
    assert namespaced_order_date_sync.__all__ == expected_public_names
    for name in expected_public_names:
        assert getattr(legacy_order_date_sync, name) is getattr(namespaced_order_date_sync, name)


def test_legacy_order_date_sync_event_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical order date sync event stub."""
    expected_public_names = [
        "sync_order_dates",
        "register_order_date_sync_listener",
    ]

    assert legacy_order_date_sync_event.__all__ == expected_public_names
    assert namespaced_order_date_sync_event.__all__ == expected_public_names
    for name in expected_public_names:
        assert getattr(legacy_order_date_sync_event, name) is getattr(
            namespaced_order_date_sync_event, name
        )


def test_app_init_uses_canonical_order_date_sync_lazy_import() -> None:
    """App init should lazy import order date sync from the canonical namespace."""
    run_auto_init_source = inspect.getsource(namespaced_app_init.run_auto_init)
    expected_import = "from foms.services.order_date_sync import register_date_sync_listener"
    assert expected_import in run_auto_init_source


def test_order_date_sync_event_uses_canonical_order_date_sync_import() -> None:
    """Legacy order date sync event stub should bind the canonical sync helper."""
    assert legacy_order_date_sync_event.sync_order_dates is namespaced_order_date_sync.sync_order_dates


def test_order_date_sync_event_canonical_module_uses_canonical_persistence_import() -> None:
    """Canonical order date sync event stub should bind persistence imports from the namespace package."""
    module_source = inspect.getsource(namespaced_order_date_sync_event)

    assert "from foms.persistence.main.models import Order" in module_source


def test_backfill_phase4_dates_uses_canonical_order_date_sync_imports() -> None:
    """Backfill script should import order date helpers from the canonical namespace."""
    backfill_source = Path("scripts/backfill_phase4_dates.py").read_text(encoding="utf-8")
    expected_import = "from foms.services.order_date_sync import collect_order_schedule_date_specs, sync_order_dates"
    assert expected_import in backfill_source


def test_legacy_estimate_service_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical estimate helpers."""
    expected_public_names = [
        "generate_estimate_number",
        "extract_estimate_data_from_order",
        "create_estimate",
        "update_estimate",
    ]

    assert legacy_estimate_service.__all__ == expected_public_names
    assert namespaced_estimate_service.__all__ == expected_public_names
    for name in expected_public_names:
        assert getattr(legacy_estimate_service, name) is getattr(namespaced_estimate_service, name)


def test_erp_estimates_api_uses_canonical_estimate_service_imports() -> None:
    """Estimate API should bind estimate helpers from the canonical namespace."""
    from apps.api import erp_estimates

    assert erp_estimates.create_estimate is namespaced_estimate_service.create_estimate
    assert erp_estimates.update_estimate is namespaced_estimate_service.update_estimate
    assert (
        erp_estimates.extract_estimate_data_from_order
        is namespaced_estimate_service.extract_estimate_data_from_order
    )


def test_legacy_db_url_resolver_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical DB URL resolver."""
    expected_public_names = ["prepare_database_url_env"]

    assert legacy_db_url_resolver.__all__ == expected_public_names
    assert namespaced_db_url_resolver.__all__ == expected_public_names
    assert (
        legacy_db_url_resolver.prepare_database_url_env
        is namespaced_db_url_resolver.prepare_database_url_env
    )
    assert not hasattr(legacy_db_url_resolver, "_normalize_postgres_scheme")


def test_legacy_as_content_safety_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical AS content helpers."""
    expected_public_names = [
        "sanitize_as_content_html",
        "as_content_html_to_text",
        "load_structured_data_dict_or_raise",
    ]

    assert legacy_as_content_safety.__all__ == expected_public_names
    assert namespaced_as_content_safety.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_as_content_safety, name) is getattr(namespaced_as_content_safety, name)


def test_erp_as_page_uses_canonical_as_content_safety_import() -> None:
    """ERP AS page should bind sanitization helper from the canonical namespace."""
    from apps import erp_as_page

    assert erp_as_page.sanitize_as_content_html is namespaced_as_content_safety.sanitize_as_content_html


def test_legacy_channel_event_payloads_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical channel payload helpers."""
    expected_public_names = [
        "build_structured_update_payload",
        "build_field_change_payload",
        "build_shipment_update_payload",
        "build_payment_confirmation_payload",
    ]

    assert legacy_channel_event_payloads.__all__ == expected_public_names
    assert namespaced_channel_event_payloads.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_channel_event_payloads, name) is getattr(namespaced_channel_event_payloads, name)


def test_legacy_channel_identity_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical channel identity helpers."""
    expected_public_names = [
        "get_user_by_manager_id",
        "is_action_allowed_for_manager",
    ]

    assert legacy_channel_identity.__all__ == expected_public_names
    assert namespaced_channel_identity.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_channel_identity, name) is getattr(namespaced_channel_identity, name)


def test_legacy_channel_security_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical channel security helpers."""
    expected_public_names = [
        "verify_channel_signature",
        "require_channel_signature",
        "generate_wam_launch_token",
        "generate_wam_entry_token",
        "generate_wam_short_link_token",
        "generate_wam_session_token",
        "verify_wam_launch_token",
        "verify_wam_entry_token",
        "verify_wam_short_link_token",
        "verify_wam_session_token",
    ]

    assert legacy_channel_security.__all__ == expected_public_names
    assert namespaced_channel_security.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_channel_security, name) is getattr(namespaced_channel_security, name)

    assert not hasattr(legacy_channel_security, "_normalize_wam_payload")


def test_legacy_channel_client_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical channel client helpers."""
    expected_public_names = [
        "CHANNEL_APP_SECRET",
        "CHANNEL_ID",
        "CHANNEL_GROUP_MEASUREMENT",
        "CHANNEL_GROUP_CONSTRUCTION",
        "CHANNEL_GROUP_GENERAL",
        "FOMS_BASE_URL",
        "is_configured",
        "get_target_group_id",
        "get_attachment_category_for_status",
        "format_order_message",
        "send_group_message",
    ]

    assert legacy_channel_client.__all__ == expected_public_names
    assert namespaced_channel_client.__all__ == expected_public_names

    for name in expected_public_names[:6]:
        assert getattr(legacy_channel_client, name) == getattr(namespaced_channel_client, name)

    for name in expected_public_names[6:]:
        assert getattr(legacy_channel_client, name) is getattr(namespaced_channel_client, name)


def test_legacy_channel_policy_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical channel policy helpers."""
    expected_public_names = [
        "DEDUPE_WINDOWS",
        "build_message_blocks",
        "get_routing_group_id",
        "build_message_template",
        "apply_attachment_policy",
        "get_policy_version",
        "resolve_push_policy",
        "resolve_resend_policy",
        "resolve_inbound_policy",
    ]

    assert legacy_channel_policy.__all__ == expected_public_names
    assert namespaced_channel_policy.__all__ == expected_public_names
    assert legacy_channel_policy.DEDUPE_WINDOWS == namespaced_channel_policy.DEDUPE_WINDOWS

    for name in expected_public_names[1:]:
        assert getattr(legacy_channel_policy, name) is getattr(namespaced_channel_policy, name)


def test_legacy_channel_dispatch_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical channel dispatch helpers."""
    expected_public_names = [
        "dispatch_channel_push",
        "dispatch_order_event",
    ]

    assert legacy_channel_dispatch.__all__ == expected_public_names
    assert namespaced_channel_dispatch.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_channel_dispatch, name) is getattr(namespaced_channel_dispatch, name)


def test_legacy_channel_delivery_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical channel delivery helpers."""
    expected_public_names = [
        "create_pending_delivery",
        "mark_delivery_status",
        "mark_api_failed",
        "mark_api_rejected",
        "mark_token_rate_limited",
        "get_delivery_metrics",
        "get_queue_backlog",
        "check_legacy_only_success_after_cutover",
        "mark_order_updated_for_channel",
        "mask_payload",
    ]

    assert legacy_channel_delivery.__all__ == expected_public_names
    assert namespaced_channel_delivery.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_channel_delivery, name) is getattr(namespaced_channel_delivery, name)


def test_legacy_channel_inbound_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical channel inbound helpers."""
    expected_public_names = [
        "generate_payload_hash",
        "extract_keys",
        "receive_webhook",
        "parse_order_text",
        "process_inbound_job",
    ]

    assert legacy_channel_inbound.__all__ == expected_public_names
    assert namespaced_channel_inbound.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_channel_inbound, name) is getattr(namespaced_channel_inbound, name)


def test_channel_dispatch_canonical_module_uses_canonical_channel_client_and_policy_imports() -> None:
    """Canonical dispatch module should bind ChannelTalk client and policy helpers from canonical modules."""
    assert (
        namespaced_channel_dispatch.get_attachment_category_for_status
        is namespaced_channel_client.get_attachment_category_for_status
    )
    assert namespaced_channel_dispatch.send_group_message is namespaced_channel_client.send_group_message
    assert namespaced_channel_dispatch.apply_attachment_policy is namespaced_channel_policy.apply_attachment_policy
    assert namespaced_channel_dispatch.build_message_blocks is namespaced_channel_policy.build_message_blocks
    assert namespaced_channel_dispatch.build_message_template is namespaced_channel_policy.build_message_template
    assert namespaced_channel_dispatch.get_routing_group_id is namespaced_channel_policy.get_routing_group_id


def test_channel_dispatch_canonical_module_uses_canonical_channel_delivery_lazy_imports() -> None:
    """Canonical dispatch module should lazy import delivery helpers from the canonical namespace."""
    dispatch_source = inspect.getsource(namespaced_channel_dispatch.dispatch_channel_push)
    expected_import = "from foms.services.channel_delivery import ("
    assert expected_import in dispatch_source


def test_channel_dispatch_canonical_module_uses_canonical_storage_lazy_import() -> None:
    """Canonical dispatch module should lazy import storage helpers from the canonical namespace."""
    dispatch_source = inspect.getsource(namespaced_channel_dispatch.dispatch_channel_push)

    assert "from foms.services.storage import get_storage" in dispatch_source


def test_channel_delivery_canonical_module_uses_canonical_channel_policy_lazy_import() -> None:
    """Canonical delivery module should lazy import ChannelTalk policy from the canonical namespace."""
    expected_import = "from foms.services.channel_policy import get_routing_group_id"
    assert expected_import in inspect.getsource(namespaced_channel_delivery.create_pending_delivery)


def test_channel_delivery_lazy_callers_use_canonical_import_paths() -> None:
    """ERP API lazy imports should reference the canonical channel delivery path."""
    from apps.api import erp_measurement
    from apps.api import erp_orders_structured
    from apps.api import erp_shipment_settings

    expected_import = "from foms.services.channel_delivery import mark_order_updated_for_channel"

    assert expected_import in inspect.getsource(erp_measurement.api_erp_measurement_update)
    assert expected_import in inspect.getsource(erp_orders_structured.api_put_order_structured)
    assert expected_import in inspect.getsource(erp_orders_structured.api_payment_confirm)
    assert expected_import in inspect.getsource(erp_shipment_settings.api_erp_shipment_update)


def test_channel_inbound_canonical_module_uses_canonical_persistence_imports() -> None:
    """Canonical inbound module should bind persistence models from the canonical namespace."""
    assert namespaced_channel_inbound.ChannelInboundEventLog is namespaced_models.ChannelInboundEventLog
    assert namespaced_channel_inbound.Order is namespaced_models.Order


def test_channel_integration_uses_canonical_channel_dispatch_import() -> None:
    """Channel integration API should bind dispatch helper from the canonical namespace."""
    from apps.api import channel_integration

    assert channel_integration.dispatch_order_event is namespaced_channel_dispatch.dispatch_order_event


def test_channel_integration_uses_canonical_channel_delivery_imports() -> None:
    """Channel integration API should bind delivery helpers from the canonical namespace."""
    from apps.api import channel_integration

    assert channel_integration.get_delivery_metrics is namespaced_channel_delivery.get_delivery_metrics
    assert channel_integration.get_queue_backlog is namespaced_channel_delivery.get_queue_backlog
    assert (
        channel_integration.check_legacy_only_success_after_cutover
        is namespaced_channel_delivery.check_legacy_only_success_after_cutover
    )


def test_channel_integration_uses_canonical_channel_client_import() -> None:
    """Channel integration API should bind configuration helper from the canonical namespace."""
    from apps.api import channel_integration

    assert channel_integration.is_configured is namespaced_channel_client.is_configured


def test_tasks_use_canonical_channel_client_lazy_import() -> None:
    """Worker task lazy import should point at the canonical ChannelTalk client path."""
    from services.jobs import tasks

    push_source = inspect.getsource(tasks.push_order_to_channeltalk)
    expected_import = "from foms.services.channel_client import is_configured"
    assert expected_import in push_source


def test_tasks_use_canonical_channel_dispatch_lazy_import() -> None:
    """Worker task lazy import should point at the canonical ChannelTalk dispatch path."""
    from services.jobs import tasks

    push_source = inspect.getsource(tasks.push_order_to_channeltalk)
    expected_import = "from foms.services.channel_dispatch import dispatch_channel_push"
    assert expected_import in push_source


def test_queue_uses_canonical_channel_delivery_lazy_imports() -> None:
    """Queue helpers should lazy import delivery helpers from the canonical namespace."""
    from services.jobs import queue

    enqueue_source = inspect.getsource(queue.enqueue_channeltalk_push)
    expected_import = "from foms.services.channel_delivery import mark_delivery_status"
    assert expected_import in enqueue_source


def test_channel_webhooks_uses_canonical_channel_inbound_lazy_import() -> None:
    """Webhook endpoint should lazy import inbound handlers from the canonical namespace."""
    from apps.api import channel_webhooks

    webhook_source = inspect.getsource(channel_webhooks.handle_webhook)
    expected_import = "from foms.services.channel_inbound import receive_webhook"
    assert expected_import in webhook_source


def test_tasks_use_canonical_channel_inbound_lazy_import() -> None:
    """Worker task lazy import should point at the canonical inbound path."""
    from services.jobs import tasks

    inbound_source = inspect.getsource(tasks.process_channeltalk_inbound)
    expected_import = "from foms.services.channel_inbound import process_inbound_job"
    assert expected_import in inbound_source


def test_legacy_jobs_queue_shim_preserves_canonical_contract() -> None:
    """The legacy jobs queue module should re-export the canonical queue helpers."""
    expected_public_names = [
        "get_rq_queue",
        "get_rq_worker_count",
        "get_rq_runtime_status",
        "enqueue_thumbnail_generation",
        "enqueue_geocode_order_address",
        "enqueue_channeltalk_push",
        "enqueue_channeltalk_inbound",
    ]

    assert legacy_jobs_queue.__all__ == expected_public_names
    assert namespaced_jobs_queue.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_jobs_queue, name) is getattr(namespaced_jobs_queue, name)


def test_legacy_jobs_tasks_shim_preserves_canonical_contract() -> None:
    """The legacy jobs tasks module should re-export the canonical worker tasks."""
    expected_public_names = [
        "create_thumbnail_for_attachment",
        "geocode_order_address",
        "push_order_to_channeltalk",
        "process_channeltalk_inbound",
    ]

    assert legacy_jobs_tasks.__all__ == expected_public_names
    assert namespaced_jobs_tasks.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_jobs_tasks, name) is getattr(namespaced_jobs_tasks, name)


def test_canonical_jobs_queue_keeps_legacy_rq_task_path_prefix() -> None:
    """Queued Redis job strings should stay on the legacy path for worker compatibility."""
    assert namespaced_jobs_queue._TASK_PATH_PREFIX == "services.jobs.tasks"


def test_canonical_jobs_tasks_repo_root_matches_workspace() -> None:
    """The namespaced worker tasks should still resolve the project root correctly."""
    assert namespaced_jobs_tasks._REPO_ROOT == Path.cwd()


def test_channel_inbound_canonical_module_uses_canonical_jobs_queue_import() -> None:
    """Canonical inbound service should import enqueue helper from canonical jobs queue."""
    module_source = inspect.getsource(namespaced_channel_inbound)

    assert "from foms.services.jobs.queue import enqueue_channeltalk_inbound" in module_source


def test_order_attachment_thumbnail_canonical_module_uses_canonical_jobs_queue_import() -> None:
    """Canonical thumbnail scheduler should lazy import canonical jobs queue."""
    function_source = inspect.getsource(
        namespaced_order_attachment_thumbnail.schedule_order_attachment_thumbnail_generation
    )

    assert "from foms.services.jobs.queue import enqueue_thumbnail_generation" in function_source


def test_channel_integration_uses_canonical_jobs_queue_import() -> None:
    """Channel integration API should bind runtime status helper from canonical jobs queue."""
    from apps.api import channel_integration

    assert channel_integration.get_rq_runtime_status is namespaced_jobs_queue.get_rq_runtime_status


def test_erp_measurement_uses_canonical_jobs_queue_imports() -> None:
    """ERP measurement API should bind jobs queue helpers from the canonical namespace."""
    from apps.api import erp_measurement

    assert erp_measurement.enqueue_geocode_order_address is namespaced_jobs_queue.enqueue_geocode_order_address
    assert erp_measurement.enqueue_channeltalk_push is namespaced_jobs_queue.enqueue_channeltalk_push


def test_erp_measurement_uses_canonical_jobs_task_fallback_import() -> None:
    """ERP measurement API should use canonical jobs task fallback imports."""
    from apps.api import erp_measurement

    module_source = inspect.getsource(erp_measurement)
    assert "from foms.services.jobs.tasks import geocode_order_address" in module_source


def test_erp_orders_structured_uses_canonical_jobs_queue_imports() -> None:
    """Structured order API should bind jobs queue helpers from the canonical namespace."""
    from apps.api import erp_orders_structured

    assert (
        erp_orders_structured.enqueue_geocode_order_address
        is namespaced_jobs_queue.enqueue_geocode_order_address
    )
    assert erp_orders_structured.enqueue_channeltalk_push is namespaced_jobs_queue.enqueue_channeltalk_push


def test_erp_shipment_settings_uses_canonical_jobs_queue_import() -> None:
    """ERP shipment settings should bind ChannelTalk enqueue from canonical jobs queue."""
    from apps.api import erp_shipment_settings

    assert erp_shipment_settings.enqueue_channeltalk_push is namespaced_jobs_queue.enqueue_channeltalk_push


def test_orders_api_uses_canonical_jobs_queue_import() -> None:
    """Orders API should bind geocode enqueue from canonical jobs queue."""
    from apps.api import orders

    assert orders.enqueue_geocode_order_address is namespaced_jobs_queue.enqueue_geocode_order_address


def test_erp_map_uses_canonical_jobs_queue_and_task_imports() -> None:
    """ERP map API should use canonical jobs queue import and task fallback import."""
    from apps.api import erp_map

    module_source = inspect.getsource(erp_map)
    assert erp_map.enqueue_geocode_order_address is namespaced_jobs_queue.enqueue_geocode_order_address
    assert "from foms.services.jobs.tasks import geocode_order_address" in module_source


def test_order_pages_uses_canonical_jobs_queue_import() -> None:
    """Order pages should bind geocode enqueue from canonical jobs queue."""
    from apps import order_pages

    assert order_pages.enqueue_geocode_order_address is namespaced_jobs_queue.enqueue_geocode_order_address


def test_order_edit_uses_canonical_jobs_queue_import() -> None:
    """Order edit page should bind geocode enqueue from canonical jobs queue."""
    from apps import order_edit

    assert order_edit.enqueue_geocode_order_address is namespaced_jobs_queue.enqueue_geocode_order_address


def test_geocode_backfill_script_uses_canonical_jobs_queue_import() -> None:
    """Geocode backfill script should resolve the canonical jobs queue module."""
    import importlib

    module = importlib.import_module("scripts.geocode_backfill")
    module_source = inspect.getsource(module)

    assert "from foms.services.jobs.queue import enqueue_geocode_order_address" in module_source
    assert 'import_module("foms.services.jobs.queue").get_rq_queue()' in module_source


def test_legacy_channel_wam_attachments_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical WAM attachment helpers."""
    expected_public_names = [
        "get_scoped_attachment",
        "list_attachment_groups",
        "resolve_attachment_redirect_url",
    ]

    assert legacy_channel_wam_attachments.__all__ == expected_public_names
    assert namespaced_channel_wam_attachments.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_channel_wam_attachments, name) is getattr(
            namespaced_channel_wam_attachments,
            name,
        )


def test_channel_wam_attachments_uses_canonical_storage_import() -> None:
    """Canonical WAM attachment helpers should use canonical storage imports."""
    module_source = inspect.getsource(namespaced_channel_wam_attachments)

    assert "from foms.services.storage import get_storage" in module_source


def test_legacy_channel_wam_telemetry_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical WAM telemetry helpers."""
    expected_public_names = [
        "ALLOWED_EVENTS",
        "record_wam_telemetry",
    ]

    assert legacy_channel_wam_telemetry.__all__ == expected_public_names
    assert namespaced_channel_wam_telemetry.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_channel_wam_telemetry, name) is getattr(
            namespaced_channel_wam_telemetry,
            name,
        )


def test_legacy_channel_wam_view_models_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical WAM view models."""
    expected_public_names = [
        "WamRequestContext",
        "WamBadgeVM",
        "WamActionVM",
        "AttachmentItemVM",
        "AttachmentGroupVM",
        "WamSectionVM",
        "WamStickyActionBarVM",
        "WamPageVM",
        "vm_to_dict",
    ]

    assert legacy_channel_wam_view_models.__all__ == expected_public_names
    assert namespaced_channel_wam_view_models.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_channel_wam_view_models, name) is getattr(
            namespaced_channel_wam_view_models,
            name,
        )


def test_legacy_channel_wam_read_model_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical WAM order read model."""
    expected_public_names = [
        "STATUS_LABELS",
        "WamTimelineEntry",
        "WamOrderReadModel",
        "get_order_for_wam",
        "load_wam_order_read_model",
        "build_order_read_model",
        "get_recent_events_for_wam",
    ]

    assert legacy_channel_wam_read_model.__all__ == expected_public_names
    assert namespaced_channel_wam_read_model.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_channel_wam_read_model, name) is getattr(
            namespaced_channel_wam_read_model,
            name,
        )


def test_legacy_channel_wam_service_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical WAM service helpers."""
    expected_public_names = [
        "get_wam_feature_flags",
        "build_wam_request_context",
        "build_wam_page",
        "build_wam_bootstrap",
        "build_legacy_wam_context",
        "build_legacy_summary",
        "build_legacy_attachments",
    ]

    assert legacy_channel_wam_service.__all__ == expected_public_names
    assert namespaced_channel_wam_service.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_channel_wam_service, name) is getattr(
            namespaced_channel_wam_service,
            name,
        )


def test_legacy_channel_quick_actions_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical quick action helpers."""
    expected_public_names = [
        "STATUS_MAP",
        "parse_foms_command",
        "process_foms_command",
        "get_order_summary_for_wam",
        "get_order_attachments_for_wam",
    ]

    assert legacy_channel_quick_actions.__all__ == expected_public_names
    assert namespaced_channel_quick_actions.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_channel_quick_actions, name) is getattr(
            namespaced_channel_quick_actions,
            name,
        )


def test_channel_quick_actions_canonical_module_uses_canonical_imports() -> None:
    """Canonical quick actions should use canonical persistence/display imports."""
    module_source = inspect.getsource(namespaced_channel_quick_actions)

    assert "from foms.persistence.main.db import get_db" in module_source
    assert "from foms.persistence.main.models import Order, OrderAttachment" in module_source
    assert "from foms.services.erp_display import _ensure_dict, _erp_get_stage, apply_erp_display_fields" in module_source


def test_channel_quick_actions_uses_canonical_storage_import() -> None:
    """Canonical quick actions should use canonical storage imports."""
    module_source = inspect.getsource(namespaced_channel_quick_actions)

    assert "from foms.services.storage import get_storage" in module_source


def test_channel_wam_service_uses_canonical_read_model_import() -> None:
    """WAM service should bind the read model helper from the canonical namespace."""
    assert (
        namespaced_channel_wam_service.load_wam_order_read_model
        is namespaced_channel_wam_read_model.load_wam_order_read_model
    )


def test_channel_wam_service_uses_canonical_quick_actions_import() -> None:
    """WAM service should bind quick action helpers from the canonical namespace."""
    assert (
        namespaced_channel_wam_service.get_order_summary_for_wam
        is namespaced_channel_quick_actions.get_order_summary_for_wam
    )
    assert (
        namespaced_channel_wam_service.get_order_attachments_for_wam
        is namespaced_channel_quick_actions.get_order_attachments_for_wam
    )


def test_channel_wam_api_uses_canonical_service_import() -> None:
    """WAM API should bind service helpers from the canonical namespace."""
    from apps.api import channel_wam as channel_wam_api

    assert channel_wam_api.get_wam_feature_flags is namespaced_channel_wam_service.get_wam_feature_flags
    assert channel_wam_api.build_wam_request_context is namespaced_channel_wam_service.build_wam_request_context
    assert channel_wam_api.build_wam_page is namespaced_channel_wam_service.build_wam_page
    assert channel_wam_api.build_wam_bootstrap is namespaced_channel_wam_service.build_wam_bootstrap
    assert channel_wam_api.build_legacy_wam_context is namespaced_channel_wam_service.build_legacy_wam_context


def test_channel_wam_api_uses_canonical_identity_import() -> None:
    """WAM API should bind manager identity helper from the canonical namespace."""
    from apps.api import channel_wam as channel_wam_api

    assert channel_wam_api.get_user_by_manager_id is namespaced_channel_identity.get_user_by_manager_id


def test_channel_wam_api_uses_canonical_security_imports() -> None:
    """WAM API should bind WAM token helpers from the canonical namespace."""
    from apps.api import channel_wam as channel_wam_api

    assert channel_wam_api.generate_wam_entry_token is namespaced_channel_security.generate_wam_entry_token
    assert channel_wam_api.generate_wam_session_token is namespaced_channel_security.generate_wam_session_token
    assert channel_wam_api.verify_wam_entry_token is namespaced_channel_security.verify_wam_entry_token
    assert channel_wam_api.verify_wam_session_token is namespaced_channel_security.verify_wam_session_token
    assert channel_wam_api.verify_wam_short_link_token is namespaced_channel_security.verify_wam_short_link_token


def test_channel_functions_api_uses_canonical_security_import() -> None:
    """Function endpoint should bind signature verification from the canonical namespace."""
    from apps.api import channel_functions

    assert channel_functions.require_channel_signature is namespaced_channel_security.require_channel_signature


def test_channel_functions_api_uses_canonical_quick_actions_import() -> None:
    """Function endpoint should bind the quick action helper from the canonical namespace."""
    import apps.api.channel_functions as channel_functions

    handle_source = inspect.getsource(channel_functions.handle_function)

    assert "from foms.services.channel_quick_actions import process_foms_command" in handle_source


def test_channel_webhooks_api_uses_canonical_security_import() -> None:
    """Webhook endpoint should bind signature verification from the canonical namespace."""
    from apps.api import channel_webhooks

    assert channel_webhooks.require_channel_signature is namespaced_channel_security.require_channel_signature


def test_channel_wam_api_uses_canonical_attachments_import() -> None:
    """WAM API should bind attachment helpers from the canonical namespace."""
    from apps.api import channel_wam as channel_wam_api

    assert channel_wam_api.list_attachment_groups is namespaced_channel_wam_attachments.list_attachment_groups
    assert channel_wam_api.get_scoped_attachment is namespaced_channel_wam_attachments.get_scoped_attachment
    assert (
        channel_wam_api.resolve_attachment_redirect_url
        is namespaced_channel_wam_attachments.resolve_attachment_redirect_url
    )


def test_channel_wam_service_uses_canonical_attachments_import() -> None:
    """WAM service should bind list_attachment_groups from the canonical namespace."""
    assert (
        namespaced_channel_wam_service.list_attachment_groups
        is namespaced_channel_wam_attachments.list_attachment_groups
    )


def test_channel_wam_api_uses_canonical_telemetry_import() -> None:
    """WAM API should bind the telemetry helper from the canonical namespace."""
    from apps.api import channel_wam as channel_wam_api

    assert channel_wam_api.record_wam_telemetry is namespaced_channel_wam_telemetry.record_wam_telemetry


def test_legacy_file_utils_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical file utils helpers."""
    expected_public_names = [
        "allowed_file",
        "allowed_erp_media_file",
    ]

    assert legacy_file_utils.__all__ == expected_public_names
    assert namespaced_file_utils.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_file_utils, name) is getattr(namespaced_file_utils, name)


def test_files_package_submodule_matches_flat_and_legacy() -> None:
    """Root shim, flat compat, and package module expose the same helper objects."""
    import foms.services.files.file_utils as pkg_fu

    expected_public_names = [
        "allowed_file",
        "allowed_erp_media_file",
    ]
    for name in expected_public_names:
        assert getattr(legacy_file_utils, name) is getattr(namespaced_file_utils, name)
        assert getattr(namespaced_file_utils, name) is getattr(pkg_fu, name)


def test_legacy_menu_config_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical menu config helpers."""
    expected_public_names = [
        "load_menu_config",
        "invalidate_menu_config_cache",
    ]

    assert legacy_menu_config.__all__ == expected_public_names
    assert namespaced_menu_config.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_menu_config, name) is getattr(namespaced_menu_config, name)


def test_legacy_context_processors_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical context processor helpers."""
    expected_public_names = [
        "parse_json_string_filter",
        "parse_json_string",
        "inject_statuses",
        "inject_status_list",
        "utility_processor",
        "inject_menu",
        "register_context_processors",
    ]

    assert legacy_context_processors.__all__ == expected_public_names
    assert namespaced_context_processors.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_context_processors, name) is getattr(namespaced_context_processors, name)


def test_context_processors_canonical_module_uses_canonical_persistence_imports() -> None:
    """Canonical context processors should bind persistence helpers from the namespace package."""
    module_source = inspect.getsource(namespaced_context_processors)

    assert "from foms.persistence.main.db import get_db" in module_source
    assert "from foms.persistence.main.models import User" in module_source


def test_context_processors_uses_canonical_storage_lazy_import() -> None:
    """Context processors should lazily import storage from the canonical namespace."""
    inject_source = inspect.getsource(namespaced_context_processors.inject_status_list)

    assert "from foms.services.storage import get_storage" in inject_source


def test_app_uses_canonical_context_processors_import() -> None:
    """App bootstrap should bind the canonical context processor registrar."""
    import app

    assert app.register_context_processors is namespaced_context_processors.register_context_processors


def test_legacy_erp_permissions_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical ERP permission helpers."""
    expected_public_names = [
        "build_mine_sql_filter",
        "can_edit_erp",
        "can_edit_erp_construction",
        "erp_edit_required",
        "erp_construction_edit_required",
    ]

    assert legacy_erp_permissions.__all__ == expected_public_names
    assert namespaced_erp_permissions.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_erp_permissions, name) is getattr(namespaced_erp_permissions, name)


def test_erp_permissions_build_mine_sql_filter_uses_canonical_persistence_import() -> None:
    """Canonical ERP permissions should bind Order from the namespace persistence shim."""
    filter_source = inspect.getsource(namespaced_erp_permissions.build_mine_sql_filter)

    assert "from foms.persistence.main.models import Order" in filter_source


def test_app_uses_canonical_erp_permissions_import() -> None:
    """App bootstrap should bind the canonical ERP permission helper."""
    import app

    assert app.can_edit_erp is namespaced_erp_permissions.can_edit_erp


def test_erp_pages_use_canonical_erp_permissions_imports() -> None:
    """ERP page modules should bind permission helpers from the canonical namespace."""
    import importlib

    module_expectations = {
        "apps.erp": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "apps.erp_as_page": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
        },
        "apps.erp_construction_page": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
            "build_mine_sql_filter": namespaced_erp_permissions.build_mine_sql_filter,
        },
        "apps.erp_dashboard": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
        },
        "apps.erp_drawing_workbench": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
        },
        "apps.erp_measurement_dashboard": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
            "build_mine_sql_filter": namespaced_erp_permissions.build_mine_sql_filter,
        },
        "apps.erp_production_page": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
        },
        "apps.erp_shipment_page": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
        },
        "apps.order_edit": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
        },
    }

    for module_name, expectations in module_expectations.items():
        module = importlib.import_module(module_name)
        module_source = inspect.getsource(module)

        assert "from foms.services.erp_permissions import" in module_source

        for attr_name, expected in expectations.items():
            assert getattr(module, attr_name) is expected


def test_erp_api_modules_use_canonical_erp_permissions_imports() -> None:
    """ERP API modules should bind permission helpers from the canonical namespace."""
    import importlib

    module_expectations = {
        "apps.api.erp_map": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "apps.api.erp_measurement": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "apps.api.erp_orders_as": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
            "erp_construction_edit_required": namespaced_erp_permissions.erp_construction_edit_required,
        },
        "apps.api.erp_orders_confirm": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "apps.api.erp_orders_construction": {
            "erp_construction_edit_required": namespaced_erp_permissions.erp_construction_edit_required,
        },
        "apps.api.erp_orders_cs": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "apps.api.erp_orders_draftsman": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "apps.api.erp_orders_drawing": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "apps.api.erp_orders_production": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "apps.api.erp_orders_revision": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "apps.api.erp_shipment_settings": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "apps.api.orders": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
        },
        "apps.api.quest": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
        },
    }

    for module_name, expectations in module_expectations.items():
        module = importlib.import_module(module_name)
        module_source = inspect.getsource(module)

        assert "from foms.services.erp_permissions import" in module_source

        for attr_name, expected in expectations.items():
            assert getattr(module, attr_name) is expected


def test_erp_permissions_lazy_callers_use_canonical_import_paths() -> None:
    """Lazy ERP permission imports should reference the canonical namespace path."""
    from apps import erp_dashboard

    module_source = inspect.getsource(erp_dashboard)

    assert "from foms.services.erp_permissions import build_mine_sql_filter" in module_source


def test_legacy_order_display_utils_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical order display helpers."""
    expected_public_names = [
        "format_options_for_display",
        "_ensure_dict",
    ]

    assert legacy_order_display_utils.__all__ == expected_public_names
    assert namespaced_order_display_utils.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_order_display_utils, name) is getattr(namespaced_order_display_utils, name)


def test_legacy_order_attachment_thumbnail_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical thumbnail scheduler."""
    expected_public_names = ["schedule_order_attachment_thumbnail_generation"]

    assert legacy_order_attachment_thumbnail.__all__ == expected_public_names
    assert namespaced_order_attachment_thumbnail.__all__ == expected_public_names
    assert (
        legacy_order_attachment_thumbnail.schedule_order_attachment_thumbnail_generation
        is namespaced_order_attachment_thumbnail.schedule_order_attachment_thumbnail_generation
    )


def test_order_attachment_thumbnail_uses_canonical_storage_import() -> None:
    """Canonical thumbnail helper should use canonical storage imports."""
    module_source = inspect.getsource(namespaced_order_attachment_thumbnail)

    assert "from foms.services.storage import get_storage" in module_source


def test_attachments_api_uses_canonical_order_attachment_thumbnail_import() -> None:
    """Attachment API should bind thumbnail scheduler from the canonical namespace."""
    from apps.api import attachments

    assert (
        attachments.schedule_order_attachment_thumbnail_generation
        is namespaced_order_attachment_thumbnail.schedule_order_attachment_thumbnail_generation
    )


def test_legacy_order_storage_cleanup_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical order storage cleanup helper."""
    expected_public_names = [
        "delete_storage_files_for_order",
    ]

    assert legacy_order_storage_cleanup.__all__ == expected_public_names
    assert namespaced_order_storage_cleanup.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_order_storage_cleanup, name) is getattr(
            namespaced_order_storage_cleanup,
            name,
        )


def test_order_storage_cleanup_uses_canonical_storage_import() -> None:
    """Canonical storage cleanup helper should use canonical storage imports."""
    module_source = inspect.getsource(namespaced_order_storage_cleanup)

    assert "from foms.services.storage import get_storage" in module_source


def test_legacy_storage_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical storage helpers."""
    expected_public_names = [
        "BOTO3_AVAILABLE",
        "PILLOW_AVAILABLE",
        "StorageAdapter",
        "get_storage",
    ]

    assert legacy_storage.__all__ == expected_public_names
    assert namespaced_storage.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_storage, name) is getattr(namespaced_storage, name)


def test_app_and_api_modules_use_canonical_storage_imports() -> None:
    """App/API storage callers should bind the canonical storage helper directly."""
    import importlib

    module_names = [
        "app",
        "apps.admin",
        "apps.api.attachments",
        "apps.api.channel_integration",
        "apps.api.chat.routes",
        "apps.api.chat.utils",
        "apps.api.erp_orders_blueprint",
        "apps.api.erp_orders_draftsman",
        "apps.api.erp_orders_drawing",
        "apps.api.files",
    ]

    for module_name in module_names:
        module = importlib.import_module(module_name)
        module_source = inspect.getsource(module)

        assert "from foms.services.storage import get_storage" in module_source
        assert module.get_storage is namespaced_storage.get_storage


def test_jobs_tasks_uses_canonical_storage_lazy_import() -> None:
    """Worker thumbnail task should lazy import storage from the canonical namespace."""
    import services.jobs.tasks as jobs_tasks

    function_source = inspect.getsource(jobs_tasks.create_thumbnail_for_attachment)

    assert "from foms.services.storage import get_storage" in function_source


def test_order_trash_uses_canonical_storage_cleanup_import() -> None:
    """Trash workflow should bind permanent delete cleanup from the canonical namespace."""
    from apps import order_trash

    assert (
        order_trash.delete_storage_files_for_order
        is namespaced_order_storage_cleanup.delete_storage_files_for_order
    )


def test_legacy_erp_template_filters_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical ERP template filters."""
    expected_public_names = [
        "split_count_filter",
        "split_list_filter",
        "strip_product_w_filter",
        "spec_w300_filter",
        "format_phone_filter",
        "spec_w300_value",
        "item_spec_w300_display",
        "item_spec_w300_value",
        "schedule_datetime_display",
        "payment_confirmed_bool",
        "register_erp_template_filters",
    ]

    assert legacy_erp_template_filters.__all__ == expected_public_names
    assert namespaced_erp_template_filters.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_erp_template_filters, name) is getattr(namespaced_erp_template_filters, name)


def test_legacy_erp_utils_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical ERP shared utility."""
    expected_public_names = ["ensure_path"]

    assert legacy_erp_utils.__all__ == expected_public_names
    assert namespaced_erp_utils.__all__ == expected_public_names
    assert legacy_erp_utils.ensure_path is namespaced_erp_utils.ensure_path


def test_legacy_erp_sync_columns_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical ERP sync helper."""
    expected_public_names = ["sync_erp_flat_columns"]

    assert legacy_erp_sync_columns.__all__ == expected_public_names
    assert namespaced_erp_sync_columns.__all__ == expected_public_names
    assert (
        legacy_erp_sync_columns.sync_erp_flat_columns
        is namespaced_erp_sync_columns.sync_erp_flat_columns
    )


def test_legacy_geocode_helpers_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical geocode helpers."""
    expected_public_names = [
        "compute_address_hash",
        "extract_address_from_structured_data",
        "extract_address_from_order",
    ]

    assert legacy_geocode_helpers.__all__ == expected_public_names
    assert namespaced_geocode_helpers.__all__ == expected_public_names
    assert (
        legacy_geocode_helpers.compute_address_hash
        is namespaced_geocode_helpers.compute_address_hash
    )
    assert (
        legacy_geocode_helpers.extract_address_from_structured_data
        is namespaced_geocode_helpers.extract_address_from_structured_data
    )
    assert (
        legacy_geocode_helpers.extract_address_from_order
        is namespaced_geocode_helpers.extract_address_from_order
    )


def test_legacy_order_geocode_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical order geocode helpers."""
    expected_public_names = [
        "apply_erp_beta_site_address_to_sd",
        "reset_order_geocode_on_address_change",
        "clear_order_geocode_coords",
    ]

    assert legacy_order_geocode.__all__ == expected_public_names
    assert namespaced_order_geocode.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_order_geocode, name) is getattr(namespaced_order_geocode, name)


def test_legacy_measurement_manager_colors_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical measurement color helpers."""
    expected_public_names = [
        "MEASUREMENT_MANAGER_PALETTE",
        "DEFAULT_MEASUREMENT_MANAGER_BG_COLOR",
        "DEFAULT_MEASUREMENT_MANAGER_TEXT_COLOR",
        "normalize_measurement_manager_key",
        "build_measurement_manager_sort_order_map",
        "build_measurement_manager_color_map",
        "resolve_measurement_manager_color",
    ]

    assert legacy_measurement_manager_colors.__all__ == expected_public_names
    assert namespaced_measurement_manager_colors.__all__ == expected_public_names
    assert (
        legacy_measurement_manager_colors.MEASUREMENT_MANAGER_PALETTE
        is namespaced_measurement_manager_colors.MEASUREMENT_MANAGER_PALETTE
    )
    assert (
        legacy_measurement_manager_colors.DEFAULT_MEASUREMENT_MANAGER_BG_COLOR
        is namespaced_measurement_manager_colors.DEFAULT_MEASUREMENT_MANAGER_BG_COLOR
    )
    assert (
        legacy_measurement_manager_colors.DEFAULT_MEASUREMENT_MANAGER_TEXT_COLOR
        is namespaced_measurement_manager_colors.DEFAULT_MEASUREMENT_MANAGER_TEXT_COLOR
    )
    assert (
        legacy_measurement_manager_colors.normalize_measurement_manager_key
        is namespaced_measurement_manager_colors.normalize_measurement_manager_key
    )
    assert (
        legacy_measurement_manager_colors.build_measurement_manager_sort_order_map
        is namespaced_measurement_manager_colors.build_measurement_manager_sort_order_map
    )
    assert (
        legacy_measurement_manager_colors.build_measurement_manager_color_map
        is namespaced_measurement_manager_colors.build_measurement_manager_color_map
    )
    assert (
        legacy_measurement_manager_colors.resolve_measurement_manager_color
        is namespaced_measurement_manager_colors.resolve_measurement_manager_color
    )
    assert not hasattr(legacy_measurement_manager_colors, "_coerce_manager_entry")


def test_legacy_erp_shipment_settings_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical ERP shipment settings contract."""
    expected_public_names = [
        "ERP_SHIPMENT_SETTINGS_KEY",
        "ERP_SHIPMENT_SETTINGS_PATH",
        "DEFAULT_ERP_WORKER_CAPACITY",
        "normalize_measurement_managers",
        "normalize_erp_shipment_workers",
        "is_order_assigned_to_user_for_construction",
        "is_order_mine_for_user",
        "load_erp_shipment_settings",
        "save_erp_shipment_settings",
    ]

    assert legacy_erp_shipment_settings.__all__ == expected_public_names
    assert namespaced_erp_shipment_settings.__all__ == expected_public_names
    assert (
        legacy_erp_shipment_settings.ERP_SHIPMENT_SETTINGS_KEY
        is namespaced_erp_shipment_settings.ERP_SHIPMENT_SETTINGS_KEY
    )
    assert (
        legacy_erp_shipment_settings.ERP_SHIPMENT_SETTINGS_PATH
        is namespaced_erp_shipment_settings.ERP_SHIPMENT_SETTINGS_PATH
    )
    assert (
        legacy_erp_shipment_settings.DEFAULT_ERP_WORKER_CAPACITY
        is namespaced_erp_shipment_settings.DEFAULT_ERP_WORKER_CAPACITY
    )
    assert (
        legacy_erp_shipment_settings.normalize_measurement_managers
        is namespaced_erp_shipment_settings.normalize_measurement_managers
    )
    assert (
        legacy_erp_shipment_settings.normalize_erp_shipment_workers
        is namespaced_erp_shipment_settings.normalize_erp_shipment_workers
    )
    assert (
        legacy_erp_shipment_settings.is_order_assigned_to_user_for_construction
        is namespaced_erp_shipment_settings.is_order_assigned_to_user_for_construction
    )
    assert (
        legacy_erp_shipment_settings.is_order_mine_for_user
        is namespaced_erp_shipment_settings.is_order_mine_for_user
    )
    assert (
        legacy_erp_shipment_settings.load_erp_shipment_settings
        is namespaced_erp_shipment_settings.load_erp_shipment_settings
    )
    assert (
        legacy_erp_shipment_settings.save_erp_shipment_settings
        is namespaced_erp_shipment_settings.save_erp_shipment_settings
    )
    assert not hasattr(legacy_erp_shipment_settings, "db_session")


def test_legacy_erp_display_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical ERP display contract."""
    expected_public_names = [
        "get_today_kst",
        "self_measurement_four_checks_done",
        "_extract_name_candidate",
        "_manager_candidates",
        "_lookup_user_name_from_candidate",
        "normalize_manager_name",
        "clean_dict_like_name",
        "_ensure_dict",
        "_normalize_date_to_yyyymmdd",
        "apply_erp_display_fields",
        "_erp_get_urgent_flag",
        "_erp_get_stage",
        "_erp_has_media",
        "_erp_alerts",
        "_sales_domain_fallback_match",
        "_can_modify_sales_domain",
        "_drawing_status_label",
        "_drawing_next_action_text",
        "apply_erp_display_fields_to_orders",
    ]

    assert legacy_erp_display.__all__ == expected_public_names
    assert namespaced_erp_display.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_erp_display, name) is getattr(namespaced_erp_display, name)

    assert not hasattr(legacy_erp_display, "STAGE_NAME_TO_CODE")


def test_erp_pages_use_canonical_erp_display_imports() -> None:
    """ERP page modules should bind display helpers from the canonical namespace."""
    from apps import erp
    from apps import erp_as_page
    from apps import erp_construction_page
    from apps import erp_dashboard
    from apps import erp_drawing_workbench
    from apps import erp_measurement_dashboard
    from apps import erp_production_page
    from apps import erp_shipment_page
    from apps import order_edit
    from apps import order_trash

    assert erp._ensure_dict is namespaced_erp_display._ensure_dict
    assert erp._erp_get_stage is namespaced_erp_display._erp_get_stage
    assert erp._erp_alerts is namespaced_erp_display._erp_alerts
    assert erp.apply_erp_display_fields is namespaced_erp_display.apply_erp_display_fields
    assert (
        erp.apply_erp_display_fields_to_orders
        is namespaced_erp_display.apply_erp_display_fields_to_orders
    )

    assert erp_as_page._ensure_dict is namespaced_erp_display._ensure_dict
    assert (
        erp_as_page.apply_erp_display_fields_to_orders
        is namespaced_erp_display.apply_erp_display_fields_to_orders
    )
    assert erp_as_page.get_today_kst is namespaced_erp_display.get_today_kst

    assert erp_construction_page._ensure_dict is namespaced_erp_display._ensure_dict
    assert erp_construction_page._erp_get_stage is namespaced_erp_display._erp_get_stage
    assert erp_construction_page._erp_has_media is namespaced_erp_display._erp_has_media
    assert erp_construction_page._erp_alerts is namespaced_erp_display._erp_alerts
    assert (
        erp_construction_page.self_measurement_four_checks_done
        is namespaced_erp_display.self_measurement_four_checks_done
    )

    assert erp_dashboard._ensure_dict is namespaced_erp_display._ensure_dict
    assert erp_dashboard._erp_get_stage is namespaced_erp_display._erp_get_stage
    assert erp_dashboard._erp_alerts is namespaced_erp_display._erp_alerts
    assert erp_dashboard._erp_has_media is namespaced_erp_display._erp_has_media

    assert erp_drawing_workbench._ensure_dict is namespaced_erp_display._ensure_dict
    assert erp_drawing_workbench._erp_get_stage is namespaced_erp_display._erp_get_stage
    assert erp_drawing_workbench._erp_alerts is namespaced_erp_display._erp_alerts
    assert (
        erp_drawing_workbench._can_modify_sales_domain
        is namespaced_erp_display._can_modify_sales_domain
    )
    assert (
        erp_drawing_workbench._drawing_status_label
        is namespaced_erp_display._drawing_status_label
    )
    assert (
        erp_drawing_workbench._drawing_next_action_text
        is namespaced_erp_display._drawing_next_action_text
    )

    assert (
        erp_measurement_dashboard._ensure_dict
        is namespaced_erp_display._ensure_dict
    )
    assert (
        erp_measurement_dashboard._normalize_date_to_yyyymmdd
        is namespaced_erp_display._normalize_date_to_yyyymmdd
    )
    assert (
        erp_measurement_dashboard.apply_erp_display_fields_to_orders
        is namespaced_erp_display.apply_erp_display_fields_to_orders
    )
    assert erp_measurement_dashboard.get_today_kst is namespaced_erp_display.get_today_kst
    assert (
        erp_measurement_dashboard.normalize_manager_name
        is namespaced_erp_display.normalize_manager_name
    )
    assert (
        erp_measurement_dashboard.self_measurement_four_checks_done
        is namespaced_erp_display.self_measurement_four_checks_done
    )

    assert erp_production_page._ensure_dict is namespaced_erp_display._ensure_dict
    assert erp_production_page._erp_get_stage is namespaced_erp_display._erp_get_stage
    assert erp_production_page._erp_has_media is namespaced_erp_display._erp_has_media
    assert erp_production_page._erp_alerts is namespaced_erp_display._erp_alerts

    assert erp_shipment_page._ensure_dict is namespaced_erp_display._ensure_dict
    assert (
        erp_shipment_page.apply_erp_display_fields_to_orders
        is namespaced_erp_display.apply_erp_display_fields_to_orders
    )
    assert erp_shipment_page.get_today_kst is namespaced_erp_display.get_today_kst

    assert order_edit._ensure_dict is namespaced_erp_display._ensure_dict
    assert order_trash._ensure_dict is namespaced_erp_display._ensure_dict
    assert (
        order_trash.apply_erp_display_fields
        is namespaced_erp_display.apply_erp_display_fields
    )


def test_erp_api_modules_use_canonical_erp_display_imports() -> None:
    """ERP API modules should bind display helpers from the canonical namespace."""
    from apps.api import erp_map
    from apps.api import erp_measurement
    from apps.api import erp_orders_as
    from apps.api import erp_orders_completion
    from apps.api import erp_orders_structured
    from apps.api import orders as orders_api

    assert erp_map.normalize_manager_name is namespaced_erp_display.normalize_manager_name
    assert erp_measurement.get_today_kst is namespaced_erp_display.get_today_kst
    assert (
        erp_measurement.self_measurement_four_checks_done
        is namespaced_erp_display.self_measurement_four_checks_done
    )
    assert erp_orders_as.get_today_kst is namespaced_erp_display.get_today_kst
    assert (
        erp_orders_completion._ensure_dict
        is namespaced_erp_display._ensure_dict
    )
    assert erp_orders_structured.get_today_kst is namespaced_erp_display.get_today_kst
    assert orders_api.get_today_kst is namespaced_erp_display.get_today_kst


def test_erp_display_lazy_callers_use_canonical_import_paths() -> None:
    """Lazy display imports should reference the canonical namespace path."""
    from apps import erp_history_page
    from apps.api import erp_map
    from apps.api import erp_measurement
    from apps.api import orders as orders_api
    from foms.api import personal_board

    history_source = inspect.getsource(erp_history_page.history_dashboard)
    assert (
        "from foms.services.erp_display import _ensure_dict, _erp_get_stage, apply_erp_display_fields"
        in history_source
    )

    order_card_source = inspect.getsource(personal_board._order_card)
    schedule_source = inspect.getsource(personal_board._schedule_today_tomorrow)
    assert "from foms.services.erp_display import _erp_get_stage" in order_card_source
    assert "from foms.services.erp_display import _erp_get_stage" in schedule_source

    query_map_orders_source = inspect.getsource(erp_map._query_map_orders)
    api_map_data_source = inspect.getsource(erp_map.api_map_data)
    api_generate_map_source = inspect.getsource(erp_map.api_generate_map)
    expected_self_measurement_import = (
        "from foms.services.erp_display import self_measurement_four_checks_done"
    )
    assert expected_self_measurement_import in query_map_orders_source
    from foms.api import measurement_map as measurement_map_mod

    measurement_map_source = inspect.getsource(measurement_map_mod)
    assert expected_self_measurement_import in measurement_map_source
    assert "measurement_map_data_response" in api_map_data_source
    assert "measurement_generate_map_response" in api_generate_map_source

    measurement_update_source = inspect.getsource(erp_measurement.api_erp_measurement_update)
    assert (
        "from foms.services.erp_display import clean_dict_like_name"
        in measurement_update_source
    )

    order_update_source = inspect.getsource(orders_api.update_order_field)
    assert (
        "from foms.services.erp_display import clean_dict_like_name"
        in order_update_source
    )


def test_legacy_erp_order_detail_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical order detail helpers."""
    expected_public_names = [
        "build_order_detail_payload_map",
        "attach_order_detail_payloads",
    ]

    assert legacy_erp_order_detail.__all__ == expected_public_names
    assert namespaced_erp_order_detail.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_erp_order_detail, name) is getattr(namespaced_erp_order_detail, name)

    assert not hasattr(legacy_erp_order_detail, "_slim_structured_data")


def test_legacy_erp_product_items_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical ERP product item helpers."""
    expected_public_names = [
        "build_product_items_for_order",
        "build_product_items_for_orders",
    ]

    assert legacy_erp_product_items.__all__ == expected_public_names
    assert namespaced_erp_product_items.__all__ == expected_public_names

    for name in expected_public_names:
        assert getattr(legacy_erp_product_items, name) is getattr(namespaced_erp_product_items, name)


def test_legacy_erp_policy_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical ERP policy module."""
    assert legacy_erp_policy.__all__ == namespaced_erp_policy.__all__
    assert legacy_erp_policy.get_policy is namespaced_erp_policy.get_policy
    assert legacy_erp_policy.AutoTaskSpec is namespaced_erp_policy.AutoTaskSpec
    assert legacy_erp_policy.build_auto_tasks is namespaced_erp_policy.build_auto_tasks
    assert legacy_erp_policy.can_modify_domain is namespaced_erp_policy.can_modify_domain


def test_canonical_erp_policy_data_paths_resolve_to_repo_root_data() -> None:
    """Policy JSON paths must resolve to <repo>/data regardless of module file location."""
    repo = Path.cwd().resolve()
    assert Path(namespaced_erp_policy._POLICY_PATH) == repo / "data" / "erp_policy.json"
    assert Path(namespaced_erp_policy._TEMPLATES_PATH) == repo / "data" / "erp_task_templates.json"
    assert Path(namespaced_erp_policy._QUEST_TEMPLATES_PATH) == repo / "data" / "erp_quest_templates.json"


def test_app_uses_canonical_erp_policy_import() -> None:
    """App bootstrap should bind ERP policy helpers from the canonical namespace."""
    import app

    assert app.recommend_owner_team is namespaced_erp_policy.recommend_owner_team
    assert app.can_modify_domain is namespaced_erp_policy.can_modify_domain
    assert app.get_stage is namespaced_erp_policy.get_stage


def test_erp_automation_uses_canonical_erp_policy_import() -> None:
    """ERP automation runner should bind build_auto_tasks from the canonical namespace."""
    import erp_automation

    assert erp_automation.build_auto_tasks is namespaced_erp_policy.build_auto_tasks


def test_erp_dashboard_uses_canonical_erp_policy_import() -> None:
    """ERP dashboard should bind policy constants from the canonical namespace."""
    from apps import erp_dashboard

    assert erp_dashboard.STAGE_LABELS is namespaced_erp_policy.STAGE_LABELS
    assert erp_dashboard.recommend_owner_team is namespaced_erp_policy.recommend_owner_team


def test_quest_api_uses_canonical_erp_policy_import() -> None:
    """Quest API should bind policy helpers from the canonical namespace."""
    from apps.api import quest

    assert quest.get_stage is namespaced_erp_policy.get_stage
    assert quest.check_quest_approvals_complete is namespaced_erp_policy.check_quest_approvals_complete


def test_erp_display_canonical_module_uses_canonical_erp_policy_import() -> None:
    """Canonical erp_display should import ERP policy from the canonical namespace."""
    module_source = inspect.getsource(namespaced_erp_display)

    assert "from foms.services.erp_policy import (" in module_source


def test_channel_event_payloads_canonical_module_uses_canonical_erp_policy_import() -> None:
    """Canonical channel_event_payloads should import STAGE_LABELS from canonical erp_policy."""
    module_source = inspect.getsource(namespaced_channel_event_payloads)

    assert "from foms.services.erp_policy import STAGE_LABELS" in module_source


def test_personal_board_uses_canonical_erp_policy_imports() -> None:
    """Personal board API should use canonical erp_policy in module and lazy imports."""
    from foms.api import personal_board

    assert personal_board.DEFAULT_OWNER_TEAM_BY_STAGE is namespaced_erp_policy.DEFAULT_OWNER_TEAM_BY_STAGE

    order_card_source = inspect.getsource(personal_board._order_card)
    assert "from foms.services.erp_policy import STAGE_NAME_TO_CODE" in order_card_source

    schedule_source = inspect.getsource(personal_board._schedule_today_tomorrow)
    assert "from foms.services.erp_policy import STAGE_NAME_TO_CODE, STAGE_LABELS" in schedule_source


def test_erp_completion_page_shim_reexports_canonical_module() -> None:
    """Legacy apps.erp_completion_page should alias foms.web.cs.completion_dashboard (Wave 4)."""
    from apps import erp_completion_page as legacy
    from foms.web.cs import completion_dashboard as canonical

    assert legacy.erp_completion_page_bp is canonical.erp_completion_page_bp
    assert legacy.erp_completion_dashboard is canonical.erp_completion_dashboard


def test_cs_completion_dashboard_template_path_exists() -> None:
    """Canonical completion template must exist under templates/cs/ (Wave 4 namespace)."""
    root = Path(__file__).resolve().parents[1]
    template_path = root / "templates" / "cs" / "completion_dashboard.html"
    assert template_path.is_file()


def test_legacy_erp_completion_dashboard_is_thin_extends_wrapper() -> None:
    """Legacy template path must thin-extend the canonical cs template only."""
    root = Path(__file__).resolve().parents[1]
    text = (root / "templates" / "erp_completion_dashboard.html").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    assert lines == ['{% extends "cs/completion_dashboard.html" %}']


def test_erp_production_page_shim_reexports_canonical_module() -> None:
    """Legacy apps.erp_production_page should alias foms.web.production.dashboard (Wave 4)."""
    from apps import erp_production_page as legacy
    from foms.web.production import dashboard as canonical

    assert legacy.erp_production_page_bp is canonical.erp_production_page_bp
    assert legacy.erp_production_dashboard is canonical.erp_production_dashboard


def test_production_dashboard_template_path_exists() -> None:
    """Canonical production dashboard template must exist (Wave 4 namespace)."""
    root = Path(__file__).resolve().parents[1]
    assert (root / "templates" / "production" / "dashboard.html").is_file()


def test_legacy_erp_production_dashboard_is_thin_extends_wrapper() -> None:
    """Legacy erp_production_dashboard.html must thin-extend production/dashboard.html only."""
    root = Path(__file__).resolve().parents[1]
    text = (root / "templates" / "erp_production_dashboard.html").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    assert lines == ['{% extends "production/dashboard.html" %}']


"""Smoke tests for the Step 3 runtime namespace shims (substantive surface).

Wave 7 (W7-B3): moved from ``tests/domains/test_foms_namespace_imports.py`` (formerly root) for thin-aggregator
entrypoint. File name avoids ``test_*.py`` so full-suite collection does not duplicate these cases.
Wave 8 (W8-B3): notifications/files root+flat compat shims removed; retired paths covered by
`find_spec` absence tests + canonical package imports.
Wave 8 (W8-B5): apps direct-import bridges (files/address/measurement + three ERP pages) removed.
SFC-B11B: ``apps/api/**`` removed; root ``apps/`` overlay directory removed; API contracts are ``foms.api``-only (WR-H1/WR-O1).
SFC-B11C: root ``services/`` overlay removed; business logic contracts are ``foms.services``-only.
SFC: ``test_sfc_product_tree_no_apps_imports_in_foms_app_run`` locks zero ``apps`` imports under ``foms/`` + root ``app.py``/``run.py``;
``test_strict_canonical_apps_overlay_directory_removed_sfc_b11b_closeout`` locks no ``apps/`` on disk;
``test_strict_canonical_services_overlay_directory_removed_sfc_b11c_closeout`` locks no ``services/`` on disk;
``test_strict_canonical_src_overlay_directory_removed_sfc_b11d_closeout`` locks no ambiguous root ``src/`` on disk.
SLG-B1+: ``test_slg_literal_gap_*`` — subtree literal closed-set gates per
``docs/plans/2026-04-15-strict-final-canonical-tree-literal-gap-remediation-plan.md`` §4 (templates/web/api/services),
template shell fragments, ``render_template("errors/...)`` ban, ``orders/erp_policy_internal`` ban.
PAC-B1+: ``test_pac_b1_*`` — post-audit correction gates per
``docs/plans/2026-04-16-strict-final-canonical-tree-post-audit-correction-plan.md``
(chat blueprint url_for ban, ``partials/http_errors`` ban, ``templates/partials/shared/*.html`` exact allowlist).
"""

import importlib
import importlib.util
import inspect
import re
from pathlib import Path

from tests.contracts.runtime.importlib_contract_helpers import find_spec_or_none

import db as legacy_db
import models as legacy_models

import foms.services.db_url_resolver as namespaced_db_url_resolver
import foms.services.db_indexes as namespaced_db_indexes
import foms.services.as_content_safety as namespaced_as_content_safety
import foms.services.channel_dispatch as namespaced_channel_dispatch
import foms.services.channel_delivery as namespaced_channel_delivery
import foms.services.channel_inbound as namespaced_channel_inbound
import foms.services.channel_client as namespaced_channel_client
import foms.services.channel_quick_actions as namespaced_channel_quick_actions
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
import foms.services.request_utils as namespaced_request_utils
import foms.services.storage as namespaced_storage
import foms.services.user_deletion as namespaced_user_deletion
import foms.services.erp_policy as namespaced_erp_policy
import foms.services.jobs.queue as namespaced_jobs_queue
import foms.services.jobs.tasks as namespaced_jobs_tasks
from foms.persistence.main import db as namespaced_db
from foms.persistence.main import models as namespaced_models

import foms.services.files.file_utils as pkg_file_utils
import foms.services.notifications.realtime_notifications as pkg_realtime_notifications

# This module lives at tests/contracts/runtime/ — three levels below repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _line_is_apps_overlay_import(line: str) -> bool:
    """Return True if a non-comment stripped line is an import from the legacy ``apps`` package."""
    s = line.strip()
    if not s or s.startswith("#"):
        return False
    if s.startswith("from apps.") or s.startswith("from apps import"):
        return True
    return bool(re.match(r"import\s+apps(\.|$|\s|,)", s))


def _sfc_product_py_paths_for_apps_import_gate(repo_root: Path) -> list[Path]:
    """Product paths for the strict canonical ``no apps.* imports`` gate: ``foms/**``, ``app.py``, ``run.py``."""
    paths: list[Path] = []
    paths.extend(sorted((repo_root / "foms").rglob("*.py")))
    for name in ("app.py", "run.py"):
        candidate = repo_root / name
        if candidate.is_file():
            paths.append(candidate)
    return paths


def test_sfc_product_tree_no_apps_imports_in_foms_app_run() -> None:
    """SFC SF4-adjacent: canonical product code must not import the legacy ``apps`` package."""
    offenders: list[str] = []
    for path in _sfc_product_py_paths_for_apps_import_gate(_REPO_ROOT):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if _line_is_apps_overlay_import(line):
                rel = path.relative_to(_REPO_ROOT)
                offenders.append(f"{rel}:{lineno}:{line.strip()}")
    assert not offenders, (
        "legacy apps.* imports are forbidden under foms/ and root app.py/run.py:\n" + "\n".join(offenders)
    )


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


def test_namespaced_map_snapshot_shim_preserves_canonical_functions() -> None:
    """The legacy services path should re-export the canonical map snapshot functions."""
    assert namespaced_map_snapshot.__all__ == [
        "build_measurement_map_query",
        "build_measurement_snapshot",
        "build_as_incomplete_map_query",
        "apply_as_map_display_fields",
    ]


def test_namespaced_request_utils_shim_preserves_canonical_functions() -> None:
    """The legacy services path should re-export the canonical request utils public API."""
    assert namespaced_request_utils.__all__ == [
        "get_preserved_filter_args",
        "get_search_query_arg",
        "redirect_if_legacy_open_erp_beta",
    ]


def test_namespaced_rate_limit_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical rate limiter helper."""
    expected_public_names = ["init_limiter"]

    assert namespaced_rate_limit.__all__ == expected_public_names


def test_app_uses_canonical_rate_limit_import() -> None:
    """App bootstrap should bind the canonical rate limit initializer."""
    import app

    assert app.init_limiter is namespaced_rate_limit.init_limiter


def test_wave8_retired_realtime_notification_compat_modules_absent() -> None:
    """W8-B3: root and flat compat shims for realtime_notifications removed."""
    assert find_spec_or_none("services.realtime_notifications") is None
    assert find_spec_or_none("foms.services.realtime_notifications") is None


def test_realtime_notifications_canonical_package_public_api() -> None:
    """Canonical notifications package exports the single public helper."""
    expected_public_names = ["emit_erp_notification_to_users"]
    assert pkg_realtime_notifications.__all__ == expected_public_names


def test_notifications_package_submodule_is_canonical() -> None:
    """Single module object for realtime notifications (no flat duplicate)."""
    import foms.services.notifications.realtime_notifications as pkg_rt

    assert pkg_rt is pkg_realtime_notifications


def test_erp_orders_drawing_uses_canonical_realtime_notification_import() -> None:
    """Drawing API should bind realtime notification helper from the canonical namespace."""
    from foms.api.drawing import erp_orders_drawing

    assert (
        erp_orders_drawing.emit_erp_notification_to_users
        is pkg_realtime_notifications.emit_erp_notification_to_users
    )


def test_erp_orders_revision_uses_canonical_realtime_notification_import() -> None:
    """Revision API should bind realtime notification helper from the canonical namespace."""
    from foms.api.drawing import erp_orders_revision

    assert (
        erp_orders_revision.emit_erp_notification_to_users
        is pkg_realtime_notifications.emit_erp_notification_to_users
    )


def test_notifications_api_uses_canonical_realtime_notification_lazy_imports() -> None:
    """Notification API lazy imports should point at the canonical namespace path."""
    from foms.api import notifications

    send_source = inspect.getsource(notifications.api_notifications_send)
    urgent_source = inspect.getsource(notifications.api_order_urgent_mention)

    expected_import = (
        "from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users"
    )
    assert expected_import in send_source
    assert expected_import in urgent_source


def test_namespaced_user_deletion_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical user deletion helpers.

    Contract revised by AUDIT-LOG T11 (design decision 5): admin "delete" became an
    audit-preserving *deactivation*, so the module now also publishes the
    deactivation helpers alongside the legacy hard-delete detacher.
    """
    expected_public_names = [
        "anonymized_deactivated_username",
        "deactivate_user_preserving_audit",
        "detach_user_references_for_deactivate",
        "detach_user_references_for_delete",
        "ensure_order_attachment_user_fk_set_null",
    ]

    assert namespaced_user_deletion.__all__ == expected_public_names


def test_auth_uses_canonical_user_deletion_import() -> None:
    """Auth routes should bind the canonical user deletion cleanup helper."""
    import foms.web.auth as auth

    assert (
        auth.detach_user_references_for_delete
        is namespaced_user_deletion.detach_user_references_for_delete
    )


def test_attachments_api_uses_canonical_user_deletion_import() -> None:
    """Attachment API should bind the canonical attachment FK repair helper."""
    from foms.api import attachments

    assert (
        attachments.ensure_order_attachment_user_fk_set_null
        is namespaced_user_deletion.ensure_order_attachment_user_fk_set_null
    )


def test_namespaced_db_indexes_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical DB index helpers."""
    expected_public_names = [
        "apply_phase2_indexes",
        "ensure_erp_date_columns",
    ]

    assert namespaced_db_indexes.__all__ == expected_public_names


def test_namespaced_app_init_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical app init entrypoint."""
    expected_public_names = ["run_auto_init"]

    assert namespaced_app_init.__all__ == expected_public_names


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
    assert "from foms.persistence.main.models import Order" in backfill_source


def test_app_init_carries_no_admin_bootstrap_wiring() -> None:
    """STARTUP-ADMIN-01: web startup creates zero admin auto-create wiring.

    Admin bootstrap moved to the explicit ``tools/ops/bootstrap_admin.py`` CLI;
    ``foms.services.app_init`` must import neither ``User`` nor a password
    hasher, and ``run_auto_init`` must not reference the removed helper.
    """
    module_source = inspect.getsource(namespaced_app_init)
    run_auto_init_source = inspect.getsource(namespaced_app_init.run_auto_init)

    assert "from foms.persistence.main.models import User" not in module_source
    assert "generate_password_hash" not in module_source
    assert not hasattr(namespaced_app_init, "_ensure_default_admin")
    assert "_ensure_default_admin" not in run_auto_init_source


def test_app_init_runs_no_ensure_schema_ddl_at_startup() -> None:
    """STARTUP-SCHEMA-01: web startup issues zero ensure-schema DDL.

    The column/index schema is owned by Alembic (migration ``startup_schema_00``,
    applied in predeploy). ``run_auto_init`` must neither import nor invoke the
    runtime ensure-repair helpers, so replicas never race on ``ALTER TABLE`` /
    ``CREATE INDEX`` and a missing schema fails closed instead of self-healing.
    """
    run_auto_init_source = inspect.getsource(namespaced_app_init.run_auto_init)
    for banned in (
        "apply_phase2_indexes",
        "ensure_erp_date_columns",
        "ensure_order_attachments_category_column",
        "ensure_order_attachments_item_index_column",
        "ensure_order_attachments_user_id_column",
    ):
        assert banned not in run_auto_init_source


def test_namespaced_order_date_sync_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical order date sync helpers."""
    expected_public_names = [
        "collect_order_schedule_date_specs",
        "sync_order_dates",
        "register_date_sync_listener",
    ]

    assert namespaced_order_date_sync.__all__ == expected_public_names
    assert namespaced_order_date_sync.__all__ == expected_public_names

def test_namespaced_order_date_sync_event_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical order date sync event stub."""
    expected_public_names = [
        "sync_order_dates",
        "register_order_date_sync_listener",
    ]

    assert namespaced_order_date_sync_event.__all__ == expected_public_names
    assert namespaced_order_date_sync_event.__all__ == expected_public_names


def test_app_init_uses_canonical_order_date_sync_lazy_import() -> None:
    """App init should lazy import order date sync from the canonical namespace."""
    run_auto_init_source = inspect.getsource(namespaced_app_init.run_auto_init)
    expected_import = "from foms.services.order_date_sync import register_date_sync_listener"
    assert expected_import in run_auto_init_source


def test_order_date_sync_event_uses_canonical_order_date_sync_import() -> None:
    """Legacy order date sync event stub should bind the canonical sync helper."""
    assert namespaced_order_date_sync_event.sync_order_dates is namespaced_order_date_sync.sync_order_dates


def test_order_date_sync_event_canonical_module_uses_canonical_persistence_import() -> None:
    """Canonical order date sync event stub should bind persistence imports from the namespace package."""
    module_source = inspect.getsource(namespaced_order_date_sync_event)

    assert "from foms.persistence.main.models import Order" in module_source


def test_backfill_phase4_dates_uses_canonical_order_date_sync_imports() -> None:
    """Backfill script should import order date helpers from the canonical namespace."""
    backfill_source = Path("scripts/maintenance/backfill_phase4_dates.py").read_text(encoding="utf-8")
    expected_import = "from foms.services.order_date_sync import collect_order_schedule_date_specs, sync_order_dates"
    assert expected_import in backfill_source


def test_namespaced_estimate_service_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical estimate helpers."""
    expected_public_names = [
        "generate_estimate_number",
        "extract_estimate_data_from_order",
        "create_estimate",
        "update_estimate",
    ]

    assert namespaced_estimate_service.__all__ == expected_public_names
    assert namespaced_estimate_service.__all__ == expected_public_names

def test_erp_estimates_api_uses_canonical_estimate_service_imports() -> None:
    """Estimate API should bind estimate helpers from the canonical namespace."""
    from foms.api import erp_estimates

    assert erp_estimates.create_estimate is namespaced_estimate_service.create_estimate
    assert erp_estimates.update_estimate is namespaced_estimate_service.update_estimate
    assert (
        erp_estimates.extract_estimate_data_from_order
        is namespaced_estimate_service.extract_estimate_data_from_order
    )


def test_namespaced_db_url_resolver_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical DB URL resolver."""
    expected_public_names = [
        "prepare_database_url_env",
        "postgresql_psycopg2_connect_kwargs_from_url",
    ]

    assert namespaced_db_url_resolver.__all__ == expected_public_names


def test_namespaced_as_content_safety_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical AS content helpers."""
    expected_public_names = [
        "sanitize_as_content_html",
        "as_content_html_to_text",
        "combined_as_content_text",
        "load_structured_data_dict_or_raise",
    ]

    assert namespaced_as_content_safety.__all__ == expected_public_names
    assert namespaced_as_content_safety.__all__ == expected_public_names


def test_erp_as_page_uses_canonical_as_content_safety_import() -> None:
    """ERP AS page should bind sanitization helper from the canonical namespace."""
    import foms.web.cs.as_dashboard as erp_as_page

    assert erp_as_page.sanitize_as_content_html is namespaced_as_content_safety.sanitize_as_content_html


def test_namespaced_channel_identity_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical channel identity helpers."""
    expected_public_names = [
        "get_user_by_manager_id",
        "is_action_allowed_for_manager",
    ]

    assert namespaced_channel_identity.__all__ == expected_public_names
    assert namespaced_channel_identity.__all__ == expected_public_names


def test_namespaced_channel_security_shim_preserves_canonical_contract() -> None:
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

    assert namespaced_channel_security.__all__ == expected_public_names


def test_namespaced_channel_client_shim_preserves_canonical_contract() -> None:
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
        "build_channel_bot_name",
        "send_group_message",
    ]

    assert namespaced_channel_client.__all__ == expected_public_names
    assert namespaced_channel_client.__all__ == expected_public_names


def test_namespaced_channel_policy_shim_preserves_canonical_contract() -> None:
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

    assert namespaced_channel_policy.__all__ == expected_public_names
    assert namespaced_channel_policy.__all__ == expected_public_names


def test_namespaced_channel_dispatch_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical channel dispatch helpers."""
    expected_public_names = [
        "dispatch_order_event",
    ]

    assert namespaced_channel_dispatch.__all__ == expected_public_names
    assert namespaced_channel_dispatch.__all__ == expected_public_names


def test_namespaced_channel_delivery_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical channel delivery helpers."""
    expected_public_names = [
        "mark_delivery_status",
        "get_delivery_metrics",
        "get_queue_backlog",
        "check_legacy_only_success_after_cutover",
    ]

    assert namespaced_channel_delivery.__all__ == expected_public_names
    assert namespaced_channel_delivery.__all__ == expected_public_names


def test_namespaced_channel_inbound_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical channel inbound helpers."""
    expected_public_names = [
        "generate_payload_hash",
        "extract_keys",
        "receive_webhook",
        "parse_order_text",
        "process_inbound_job",
    ]

    assert namespaced_channel_inbound.__all__ == expected_public_names
    assert namespaced_channel_inbound.__all__ == expected_public_names


def test_channel_dispatch_canonical_module_uses_canonical_channel_client_and_policy_imports() -> None:
    """Canonical dispatch module should bind ChannelTalk client and policy helpers from canonical modules."""
    assert namespaced_channel_dispatch.send_group_message is namespaced_channel_client.send_group_message
    assert namespaced_channel_dispatch.apply_attachment_policy is namespaced_channel_policy.apply_attachment_policy
    assert namespaced_channel_dispatch.build_message_blocks is namespaced_channel_policy.build_message_blocks
    assert namespaced_channel_dispatch.build_message_template is namespaced_channel_policy.build_message_template
    assert namespaced_channel_dispatch.get_routing_group_id is namespaced_channel_policy.get_routing_group_id


def test_channel_dispatch_manual_only_exports_dispatch_order_event() -> None:
    """Auto outbox worker removed; only manual ERP push dispatch remains."""
    dispatch_source = inspect.getsource(namespaced_channel_dispatch.dispatch_order_event)

    assert "dispatch_channel_push" not in dispatch_source
    assert 'event_type != "manual"' in dispatch_source
    assert "from foms.services.storage import get_storage" not in dispatch_source


def test_channel_delivery_lazy_callers_removed_after_auto_push_retired() -> None:
    """ERP save paths no longer lazy-import mark_order_updated_for_channel."""
    from foms.api import erp_orders_structured
    from foms.api import measurement as erp_measurement
    from foms.api.shipment import settings as erp_shipment_settings

    expected_import = "from foms.services.channel_delivery import mark_order_updated_for_channel"
    for source in (
        erp_orders_structured.api_put_order_structured,
        erp_measurement.api_erp_measurement_update,
        erp_shipment_settings.api_erp_shipment_update,
    ):
        assert expected_import not in inspect.getsource(source)


def test_channel_event_payloads_module_removed_after_auto_push_retired() -> None:
    """Structured auto-push payload builder module was deleted with the outbox pipeline."""
    assert find_spec_or_none("foms.services.channel_event_payloads") is None


def test_channel_inbound_canonical_module_uses_canonical_persistence_imports() -> None:
    """Canonical inbound module should bind persistence models from the canonical namespace."""
    assert namespaced_channel_inbound.ChannelInboundEventLog is namespaced_models.ChannelInboundEventLog
    assert namespaced_channel_inbound.Order is namespaced_models.Order


def test_channel_integration_uses_canonical_channel_dispatch_import() -> None:
    """Channel integration API should bind dispatch helper from the canonical namespace."""
    import foms.api.channel.channel_integration as channel_integration

    assert channel_integration.dispatch_order_event is namespaced_channel_dispatch.dispatch_order_event


def test_channel_integration_uses_canonical_channel_delivery_imports() -> None:
    """Channel integration API should bind delivery helpers from the canonical namespace."""
    import foms.api.channel.channel_integration as channel_integration

    assert channel_integration.get_delivery_metrics is namespaced_channel_delivery.get_delivery_metrics
    assert channel_integration.get_queue_backlog is namespaced_channel_delivery.get_queue_backlog
    assert (
        channel_integration.check_legacy_only_success_after_cutover
        is namespaced_channel_delivery.check_legacy_only_success_after_cutover
    )


def test_channel_integration_uses_canonical_channel_client_import() -> None:
    """Channel integration API should bind configuration helper from the canonical namespace."""
    import foms.api.channel.channel_integration as channel_integration

    assert channel_integration.is_configured is namespaced_channel_client.is_configured


def test_tasks_legacy_push_order_to_channeltalk_drains_without_dispatch() -> None:
    """Stale auto-push RQ jobs drain safely without reintroducing dispatch_channel_push."""
    from foms.services.jobs import tasks

    push_source = inspect.getsource(tasks.push_order_to_channeltalk)
    assert "dispatch_channel_push" not in push_source
    assert "dispatch_order_event" not in push_source
    assert "ignored_stale" in push_source
    assert "from foms.services.channel_delivery import mark_delivery_status" in push_source


def test_channel_webhooks_uses_canonical_channel_inbound_lazy_import() -> None:
    """Webhook endpoint should lazy import inbound handlers from the canonical namespace."""
    import foms.api.channel.channel_webhooks as channel_webhooks

    webhook_source = inspect.getsource(channel_webhooks.handle_webhook)
    expected_import = "from foms.services.channel_inbound import receive_webhook"
    assert expected_import in webhook_source


def test_tasks_use_canonical_channel_inbound_lazy_import() -> None:
    """Worker task lazy import should point at the canonical inbound path."""
    from foms.services.jobs import tasks

    inbound_source = inspect.getsource(tasks.process_channeltalk_inbound)
    expected_import = "from foms.services.channel_inbound import process_inbound_job"
    assert expected_import in inbound_source


def test_namespaced_jobs_queue_shim_preserves_canonical_contract() -> None:
    """The legacy jobs queue module should re-export the canonical queue helpers."""
    expected_public_names = [
        "get_rq_queue",
        "get_rq_worker_count",
        "get_rq_runtime_status",
        "enqueue_thumbnail_generation",
        "enqueue_geocode_order_address",
        "enqueue_channeltalk_inbound",
        # NAVER-INGEST-01 §3.1: web 은 enqueue 만 한다(네이버 HTTP 는 WORKER 단일 출구).
        "enqueue_naver_order_sync",
    ]

    assert namespaced_jobs_queue.__all__ == expected_public_names
    assert namespaced_jobs_queue.__all__ == expected_public_names


def test_namespaced_jobs_tasks_shim_preserves_canonical_contract() -> None:
    """The legacy jobs tasks module should re-export the canonical worker tasks."""
    expected_public_names = [
        "create_thumbnail_for_attachment",
        "geocode_order_address",
        "push_order_to_channeltalk",
        "process_channeltalk_inbound",
        "send_push_for_notification_task",
        "run_notification_escalation_task",
        # NAVER-INGEST-01 §3.1: 수집 실행은 WORKER 의 rq job 이다(web 직접 호출 금지).
        "run_naver_order_sync_task",
        # NAVER-INGEST-BACKFILL: 과거 구간 소급 수집도 같은 이유로 WORKER job 이다.
        "run_naver_backfill_task",
    ]

    assert namespaced_jobs_tasks.__all__ == expected_public_names
    assert namespaced_jobs_tasks.__all__ == expected_public_names


def test_wr_b1_business_calendar_canonical_module_sfc_b11c() -> None:
    """WR-B1 / SFC-B11C: business calendar owner is ``foms.services.common.business_calendar`` (no root shim)."""
    import foms.services.common.business_calendar as canonical_bcal

    expected_public_names = [
        "get_holidays_kr",
        "is_business_day",
        "business_days_between",
        "business_days_until",
        "add_business_days",
    ]
    assert canonical_bcal.__all__ == expected_public_names
    assert callable(canonical_bcal.add_business_days)


def test_wr_h1_blueprint_registry_foms_api_only_b11b() -> None:
    """WR-H1 (B11B): blueprint registration uses foms.api only; apps.api overlay removed."""
    repo_root = Path.cwd()
    bp_text = (repo_root / "foms" / "platform" / "blueprints.py").read_text(encoding="utf-8")

    assert "from foms.api.notifications import notifications_bp" in bp_text
    assert "from foms.api.attachments import attachments_bp" in bp_text
    assert "from foms.api.channel import" in bp_text and "chat_bp" in bp_text
    assert "from foms.api.channel import" in bp_text

    forbidden = (
        "from apps.api.notifications",
        "from apps.api.attachments",
        "from apps.api.chat",
        "from apps.api.channel",
    )
    for needle in forbidden:
        assert needle not in bp_text, f"blueprints must not contain legacy import {needle!r}"

    assert not (repo_root / "apps" / "api").exists(), "B11B: apps/api overlay must be removed"
    assert find_spec_or_none("apps.api") is None


def test_b11b_canonical_api_cluster_importable() -> None:
    """B11B: notifications/attachments/chat/channel/aux API surfaces resolve from foms.api only."""
    assert find_spec_or_none("apps.api") is None

    from foms.api import notifications, attachments
    from foms.api.channel import chat_bp, register_chat_socketio_handlers
    from foms.api.channel.channel_integration import channel_integration_bp
    from foms.api.channel.channel_webhooks import channel_webhooks_bp
    from foms.api.channel.channel_functions import channel_functions_bp
    from foms.api.channel.channel_wam import channel_wam_bp
    from foms.api.tasks import tasks_bp
    from foms.api.events import events_bp
    from foms.api.debug import debug_bp
    from foms.api.quest import quest_bp
    from foms.api.wdcalculator import wdcalculator_bp

    assert notifications.notifications_bp is not None
    assert attachments.attachments_bp is not None
    assert chat_bp is not None
    assert register_chat_socketio_handlers is not None
    assert channel_integration_bp is not None
    assert channel_webhooks_bp is not None
    assert channel_functions_bp is not None
    assert channel_wam_bp is not None
    assert tasks_bp is not None
    assert events_bp is not None
    assert debug_bp is not None
    assert quest_bp is not None
    assert wdcalculator_bp is not None


def test_b11b_canonical_erp_orders_lane_importable() -> None:
    """B11B: ERP orders lane blueprints live under foms.api (no apps.api shims)."""
    from foms.api.erp_orders_blueprint import erp_orders_blueprint_bp
    from foms.api.erp_estimates import erp_estimates_bp
    from foms.api.drawing import (
        erp_orders_drawing_bp,
        erp_orders_revision_bp,
        erp_orders_draftsman_bp,
    )
    from foms.api.production.orders import erp_orders_production_bp
    from foms.api.construction.orders import erp_orders_construction_bp
    from foms.api.cs.complete import erp_orders_cs_bp
    from foms.api.cs.as_orders import erp_orders_as_bp
    from foms.api.cs.dashboard import erp_orders_completion_bp
    from foms.api.cs.confirm import erp_orders_confirm_bp
    from foms.api import erp_orders_structured
    from foms.api.erp_map import erp_map_bp
    from foms.api.shipment.settings import erp_shipment_bp

    assert erp_orders_blueprint_bp is not None
    assert erp_estimates_bp is not None
    assert erp_orders_drawing_bp is not None
    assert erp_orders_revision_bp is not None
    assert erp_orders_draftsman_bp is not None
    assert erp_orders_production_bp is not None
    assert erp_orders_construction_bp is not None
    assert erp_orders_cs_bp is not None
    assert erp_orders_as_bp is not None
    assert erp_orders_completion_bp is not None
    assert erp_orders_confirm_bp is not None
    assert erp_orders_structured is not None
    assert erp_map_bp is not None
    assert erp_shipment_bp is not None


def test_b11b_files_and_channel_chat_submodules_importable() -> None:
    """B11B: attachment helpers + chat submodules live under foms.api.files / foms.api.channel."""
    import foms.api.files.common as att_common
    import foms.api.files.blueprint as att_bp
    import foms.api.channel.routes as chat_routes
    import foms.api.channel.utils as chat_utils

    assert att_common is not None
    assert att_bp.attachments_bp is not None
    assert chat_routes is not None
    assert chat_utils is not None


def test_canonical_jobs_queue_uses_namespaced_rq_task_path_prefix() -> None:
    """New queued Redis jobs should use the canonical namespaced task path."""
    assert namespaced_jobs_queue._TASK_PATH_PREFIX == "foms.services.jobs.tasks"


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
    import foms.api.channel.channel_integration as channel_integration

    assert channel_integration.get_rq_runtime_status is namespaced_jobs_queue.get_rq_runtime_status


def test_erp_measurement_uses_canonical_jobs_queue_imports() -> None:
    """ERP measurement API should bind jobs queue helpers from the canonical namespace."""
    from foms.api import measurement as erp_measurement

    assert erp_measurement.enqueue_geocode_order_address is namespaced_jobs_queue.enqueue_geocode_order_address


def test_erp_measurement_address_change_uses_geocode_outbox() -> None:
    """DATA-MEASUREMENT-01: measurement address change enqueues GEOCODE via the SIDEFX
    outbox producer and no longer performs a postcommit synchronous geocode fallback.

    (Supersedes the previous contract that pinned the ``jobs.tasks`` sync fallback import;
    the 3-forbidden SSOT removes postcommit direct geocode from the write path.)
    """
    import importlib

    routes_mod = importlib.import_module("foms.api.measurement.routes")
    module_source = inspect.getsource(routes_mod)
    assert (
        "from foms.services.order_geocode_outbox import enqueue_order_address_geocode"
        in module_source
    )
    assert "from foms.services.jobs.tasks import geocode_order_address" not in module_source


def test_erp_orders_structured_uses_canonical_jobs_queue_imports() -> None:
    """Structured order API should bind jobs queue helpers from the canonical namespace."""
    from foms.api import erp_orders_structured

    assert (
        erp_orders_structured.enqueue_geocode_order_address
        is namespaced_jobs_queue.enqueue_geocode_order_address
    )


def test_orders_api_uses_canonical_jobs_queue_import() -> None:
    """Orders API should bind geocode enqueue from canonical jobs queue."""
    from foms.api import orders

    assert orders.enqueue_geocode_order_address is namespaced_jobs_queue.enqueue_geocode_order_address


def test_erp_map_uses_canonical_jobs_queue_and_task_imports() -> None:
    """ERP map API should use canonical jobs queue import and task fallback import."""
    from foms.api import erp_map

    module_source = inspect.getsource(erp_map)
    assert erp_map.enqueue_geocode_order_address is namespaced_jobs_queue.enqueue_geocode_order_address
    assert "from foms.services.jobs.tasks import geocode_order_address" in module_source


def test_order_pages_uses_canonical_jobs_queue_import() -> None:
    """Order pages should bind geocode enqueue from canonical jobs queue."""
    import foms.web.orders.listing as order_pages

    assert order_pages.enqueue_geocode_order_address is namespaced_jobs_queue.enqueue_geocode_order_address


def test_order_edit_uses_canonical_jobs_queue_import() -> None:
    """Order edit page should bind geocode enqueue from canonical jobs queue."""
    import foms.web.orders.edit as order_edit

    assert order_edit.enqueue_geocode_order_address is namespaced_jobs_queue.enqueue_geocode_order_address


def test_geocode_backfill_script_uses_canonical_jobs_queue_import() -> None:
    """Geocode backfill script should resolve the canonical jobs queue module."""
    path = _REPO_ROOT / "scripts" / "maintenance" / "geocode_backfill.py"
    spec = importlib.util.spec_from_file_location("geocode_backfill_script", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module_source = inspect.getsource(module)

    assert "from foms.services.jobs.queue import enqueue_geocode_order_address" in module_source
    assert 'import_module("foms.services.jobs.queue").get_rq_queue()' in module_source


def test_namespaced_channel_wam_attachments_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical WAM attachment helpers."""
    expected_public_names = [
        "get_scoped_attachment",
        "list_attachment_groups",
        "resolve_attachment_redirect_url",
    ]

    assert namespaced_channel_wam_attachments.__all__ == expected_public_names
    assert namespaced_channel_wam_attachments.__all__ == expected_public_names



def test_channel_wam_attachments_uses_canonical_storage_import() -> None:
    """Canonical WAM attachment helpers should use canonical storage imports."""
    module_source = inspect.getsource(namespaced_channel_wam_attachments)

    assert "from foms.services.storage import get_storage" in module_source


def test_namespaced_channel_wam_telemetry_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical WAM telemetry helpers."""
    expected_public_names = [
        "ALLOWED_EVENTS",
        "record_wam_telemetry",
    ]

    assert namespaced_channel_wam_telemetry.__all__ == expected_public_names
    assert namespaced_channel_wam_telemetry.__all__ == expected_public_names



def test_namespaced_channel_wam_view_models_shim_preserves_canonical_contract() -> None:
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

    assert namespaced_channel_wam_view_models.__all__ == expected_public_names
    assert namespaced_channel_wam_view_models.__all__ == expected_public_names



def test_namespaced_channel_wam_read_model_shim_preserves_canonical_contract() -> None:
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

    assert namespaced_channel_wam_read_model.__all__ == expected_public_names
    assert namespaced_channel_wam_read_model.__all__ == expected_public_names



def test_namespaced_channel_wam_service_shim_preserves_canonical_contract() -> None:
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

    assert namespaced_channel_wam_service.__all__ == expected_public_names
    assert namespaced_channel_wam_service.__all__ == expected_public_names



def test_namespaced_channel_quick_actions_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical quick action helpers."""
    expected_public_names = [
        "STATUS_MAP",
        "parse_foms_command",
        "process_foms_command",
        "get_order_summary_for_wam",
        "get_order_attachments_for_wam",
    ]

    assert namespaced_channel_quick_actions.__all__ == expected_public_names
    assert namespaced_channel_quick_actions.__all__ == expected_public_names



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
    import foms.api.channel.channel_wam as channel_wam_api

    assert channel_wam_api.get_wam_feature_flags is namespaced_channel_wam_service.get_wam_feature_flags
    assert channel_wam_api.build_wam_request_context is namespaced_channel_wam_service.build_wam_request_context
    assert channel_wam_api.build_wam_page is namespaced_channel_wam_service.build_wam_page
    assert channel_wam_api.build_wam_bootstrap is namespaced_channel_wam_service.build_wam_bootstrap
    assert channel_wam_api.build_legacy_wam_context is namespaced_channel_wam_service.build_legacy_wam_context


def test_channel_wam_api_uses_canonical_identity_import() -> None:
    """WAM API should bind manager identity helper from the canonical namespace."""
    import foms.api.channel.channel_wam as channel_wam_api

    assert channel_wam_api.get_user_by_manager_id is namespaced_channel_identity.get_user_by_manager_id


def test_channel_wam_api_uses_canonical_security_imports() -> None:
    """WAM API should bind WAM token helpers from the canonical namespace."""
    import foms.api.channel.channel_wam as channel_wam_api

    assert channel_wam_api.generate_wam_entry_token is namespaced_channel_security.generate_wam_entry_token
    assert channel_wam_api.generate_wam_session_token is namespaced_channel_security.generate_wam_session_token
    assert channel_wam_api.verify_wam_entry_token is namespaced_channel_security.verify_wam_entry_token
    assert channel_wam_api.verify_wam_session_token is namespaced_channel_security.verify_wam_session_token
    assert channel_wam_api.verify_wam_short_link_token is namespaced_channel_security.verify_wam_short_link_token


def test_channel_functions_api_owns_dedicated_signature_contract() -> None:
    """CHANNEL-FUNCTION-CONTRACT-01: Function endpoint owns a DEDICATED signature scheme.

    Function 서명(hex-decode key ≥32B → raw body HMAC-SHA256 → Base64 → constant-time)은
    Webhook 서명 helper(``require_channel_signature``, raw UTF-8 key + hex digest)를 재사용하지
    않는다. Function 은 전용 ``verify_function_signature`` 를 소유하고, Webhook helper 를 이
    모듈에 바인딩하지 않아야 한다.
    """
    import foms.api.channel.channel_functions as channel_functions

    assert hasattr(channel_functions, "verify_function_signature")
    assert not hasattr(channel_functions, "require_channel_signature")


def test_channel_functions_api_uses_canonical_quick_actions_import() -> None:
    """Function endpoint should bind the quick action helper from the canonical namespace."""
    import foms.api.channel.channel_functions as channel_functions

    handle_source = inspect.getsource(channel_functions.handle_function)

    assert "from foms.services.channel_quick_actions import process_foms_command" in handle_source


def test_channel_webhooks_api_uses_canonical_security_import() -> None:
    """Webhook endpoint should bind signature verification from the canonical namespace."""
    import foms.api.channel.channel_webhooks as channel_webhooks

    assert channel_webhooks.require_channel_signature is namespaced_channel_security.require_channel_signature


def test_channel_wam_api_uses_canonical_attachments_import() -> None:
    """WAM API should bind attachment helpers from the canonical namespace."""
    import foms.api.channel.channel_wam as channel_wam_api

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
    import foms.api.channel.channel_wam as channel_wam_api

    assert channel_wam_api.record_wam_telemetry is namespaced_channel_wam_telemetry.record_wam_telemetry


def test_wave8_retired_file_utils_compat_modules_absent() -> None:
    """W8-B3: root and flat compat shims for file_utils removed."""
    assert find_spec_or_none("services.file_utils") is None
    assert find_spec_or_none("foms.services.file_utils") is None


def test_file_utils_canonical_package_public_api() -> None:
    """Canonical files package exports the helper pair."""
    expected_public_names = [
        "allowed_file",
        "allowed_erp_media_file",
    ]
    assert pkg_file_utils.__all__ == expected_public_names


def test_files_package_submodule_matches_canonical() -> None:
    """Package module path is the single canonical surface."""
    import foms.services.files.file_utils as pkg_fu

    assert pkg_fu is pkg_file_utils
    for name in ["allowed_file", "allowed_erp_media_file"]:
        assert getattr(pkg_file_utils, name) is getattr(pkg_fu, name)


def test_namespaced_menu_config_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical menu config helpers."""
    expected_public_names = [
        "load_menu_config",
        "invalidate_menu_config_cache",
    ]

    assert namespaced_menu_config.__all__ == expected_public_names
    assert namespaced_menu_config.__all__ == expected_public_names


def test_namespaced_context_processors_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical context processor helpers."""
    expected_public_names = [
        "parse_json_string_filter",
        "parse_json_string",
        "inject_statuses",
        "inject_status_list",
        "utility_processor",
        "inject_menu",
        "inject_foms_flags",
        "inject_foms_nav_badges",
        # 2026-07-12 태블릿 시트 파이프라인: 단계 카탈로그 injector 공개 계약 편입.
        "inject_foms_stage_catalog",
        "register_context_processors",
    ]

    assert namespaced_context_processors.__all__ == expected_public_names
    assert namespaced_context_processors.__all__ == expected_public_names


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


def test_namespaced_erp_permissions_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical ERP permission helpers."""
    expected_public_names = [
        "build_mine_sql_filter",
        "can_edit_erp",
        "can_edit_erp_construction",
        "erp_edit_required",
        "erp_construction_edit_required",
    ]

    assert namespaced_erp_permissions.__all__ == expected_public_names
    assert namespaced_erp_permissions.__all__ == expected_public_names


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
        "foms.web.cs.as_dashboard": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
        },
        "foms.web.construction.dashboard": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
            "build_mine_sql_filter": namespaced_erp_permissions.build_mine_sql_filter,
        },
        "foms.web.orders.dashboard": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
        },
        "foms.web.drawing.workbench": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
        },
        "foms.web.measurement.dashboard": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
            "build_mine_sql_filter": namespaced_erp_permissions.build_mine_sql_filter,
        },
        "foms.web.production.dashboard": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
        },
        "foms.web.shipment.dashboard": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
        },
        "foms.web.orders.edit": {
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
        "foms.api.erp_map": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "foms.api.measurement": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "foms.api.cs.as_orders": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
            "erp_construction_edit_required": namespaced_erp_permissions.erp_construction_edit_required,
        },
        "foms.api.cs.confirm": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "foms.api.construction.orders": {
            "erp_construction_edit_required": namespaced_erp_permissions.erp_construction_edit_required,
        },
        "foms.api.cs.complete": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "foms.api.drawing.erp_orders_draftsman": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "foms.api.drawing.erp_orders_drawing": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "foms.api.production.orders": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "foms.api.drawing.erp_orders_revision": {
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "foms.api.shipment.settings": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
            "erp_edit_required": namespaced_erp_permissions.erp_edit_required,
        },
        "foms.api.orders": {
            "can_edit_erp": namespaced_erp_permissions.can_edit_erp,
        },
        # foms.api.quest 는 AUTH-QUEST-01 에서 quest approve 권한을 order_mutation_policy
        # (actor team=required team·ASSIGNMENT-00 배정) 기반 게이트로 정본화하며 can_edit_erp
        # 를 더 이상 쓰지 않는다 — 따라서 erp_permissions 바인딩 기대에서 제외한다.
    }

    for module_name, expectations in module_expectations.items():
        module = importlib.import_module(module_name)
        module_source = inspect.getsource(module)

        assert "from foms.services.erp_permissions import" in module_source

        for attr_name, expected in expectations.items():
            assert getattr(module, attr_name) is expected


def test_erp_permissions_lazy_callers_use_canonical_import_paths() -> None:
    """Lazy ERP permission imports should reference the canonical namespace path.

    Batch 2a-2: build_mine_sql_filter의 lazy 호출자가 orders 대시보드 read-model로
    이전됨(dashboard.py -> dashboard_read_model.py). 캐노니컬 경로는 동일 유지.
    """
    module_source = (
        _REPO_ROOT / "foms" / "services" / "orders" / "dashboard_read_model.py"
    ).read_text(encoding="utf-8")

    assert "from foms.services.erp_permissions import build_mine_sql_filter" in module_source


def test_namespaced_order_display_utils_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical order display helpers."""
    expected_public_names = [
        "format_options_for_display",
        "_ensure_dict",
    ]

    assert namespaced_order_display_utils.__all__ == expected_public_names
    assert namespaced_order_display_utils.__all__ == expected_public_names


def test_namespaced_order_attachment_thumbnail_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical thumbnail scheduler."""
    expected_public_names = ["schedule_order_attachment_thumbnail_generation"]

    assert namespaced_order_attachment_thumbnail.__all__ == expected_public_names
    assert namespaced_order_attachment_thumbnail.__all__ == expected_public_names


def test_order_attachment_thumbnail_uses_canonical_storage_import() -> None:
    """Canonical thumbnail helper should use canonical storage imports."""
    module_source = inspect.getsource(namespaced_order_attachment_thumbnail)

    assert "from foms.services.storage import get_storage" in module_source


def test_attachments_api_uses_canonical_order_attachment_thumbnail_import() -> None:
    """Attachment API should bind thumbnail scheduler from the canonical namespace."""
    from foms.api import attachments

    assert (
        attachments.schedule_order_attachment_thumbnail_generation
        is namespaced_order_attachment_thumbnail.schedule_order_attachment_thumbnail_generation
    )


def test_namespaced_order_storage_cleanup_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical order storage cleanup helper."""
    expected_public_names = [
        "delete_storage_files_for_order",
    ]

    assert namespaced_order_storage_cleanup.__all__ == expected_public_names
    assert namespaced_order_storage_cleanup.__all__ == expected_public_names



def test_order_storage_cleanup_uses_canonical_storage_import() -> None:
    """Canonical storage cleanup helper should use canonical storage imports."""
    module_source = inspect.getsource(namespaced_order_storage_cleanup)

    assert "from foms.services.storage import get_storage" in module_source


def test_wr_s2_legacy_storage_shim_retired() -> None:
    """WR-S2: canonical storage lives in foms.services.storage; root services/ overlay removed (SFC-B11C)."""
    expected_public_names = [
        "BOTO3_AVAILABLE",
        "PILLOW_AVAILABLE",
        "StorageAdapter",
        "get_storage",
    ]

    assert namespaced_storage.__all__ == expected_public_names
    assert find_spec_or_none("services") is None


def test_app_and_api_modules_use_canonical_storage_imports() -> None:
    """App/API storage callers should bind the canonical storage helper directly."""
    import importlib

    module_names = [
        "app",
        "foms.web.admin.routes",
        "foms.api.attachments",
        "foms.api.channel.channel_integration",
        "foms.api.channel.routes",
        "foms.api.channel.utils",
        "foms.api.erp_orders_blueprint",
        "foms.api.drawing.erp_orders_draftsman",
        "foms.api.drawing.erp_orders_drawing",
        "foms.api.files",
    ]

    for module_name in module_names:
        module = importlib.import_module(module_name)
        module_source = inspect.getsource(module)

        assert "from foms.services.storage import get_storage" in module_source
        assert module.get_storage is namespaced_storage.get_storage


def test_jobs_tasks_uses_canonical_storage_lazy_import() -> None:
    """Worker thumbnail task should lazy import storage from the canonical namespace."""
    import foms.services.jobs.tasks as jobs_tasks

    function_source = inspect.getsource(jobs_tasks.create_thumbnail_for_attachment)

    assert "from foms.services.storage import get_storage" in function_source


# DELETE-TRASH-01: trash 의 web hard-delete(물리 삭제) 경로가 제거되면서 trash.py 는 더 이상
# delete_storage_files_for_order 를 import 하지 않는다(물리 삭제는 DELETE-RETENTION-01 만 수행).
# 따라서 구 order_trash → 캐노니컬 storage cleanup import 계약 테스트는 폐기한다. namespaced
# storage cleanup shim 자체의 계약은 test_namespaced_order_storage_cleanup_shim_* 가 계속 고정한다.


def test_namespaced_erp_template_filters_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical ERP template filters."""
    expected_public_names = [
        "split_count_filter",
        "split_list_filter",
        "strip_product_w_filter",
        "spec_w300_filter",
        "format_phone_filter",
        "format_phone_no_prefix",
        "spec_w300_value",
        "item_spec_w300_display",
        "item_spec_w300_value",
        "schedule_datetime_display",
        "payment_confirmed_bool",
        "coerce_deposit_amount",
        "lahom_deposit_gold",
        "LAHOM_STANDARD_DEPOSIT_AMOUNTS",
        "queue_card_schedule_filter",
        "meas_daypart",
        "register_erp_template_filters",
    ]

    assert namespaced_erp_template_filters.__all__ == expected_public_names
    assert namespaced_erp_template_filters.__all__ == expected_public_names


def test_namespaced_erp_utils_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical ERP shared utility."""
    expected_public_names = ["ensure_path"]

    assert namespaced_erp_utils.__all__ == expected_public_names
    assert namespaced_erp_utils.__all__ == expected_public_names


def test_namespaced_erp_sync_columns_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical ERP sync helper."""
    expected_public_names = ["sync_erp_flat_columns"]

    assert namespaced_erp_sync_columns.__all__ == expected_public_names
    assert namespaced_erp_sync_columns.__all__ == expected_public_names


def test_namespaced_geocode_helpers_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical geocode helpers.

    ``apply_geocode_to_order`` + its outcome constants joined the surface when the SIDEFX
    ``GEOCODE`` handler landed: the RQ task and the outbox handler must share one decision
    function (no second copy of the geocode judgement/persist rules).
    """
    expected_public_names = [
        "compute_address_hash",
        "extract_address_from_structured_data",
        "extract_address_from_order",
        "get_order_display_address",
        "apply_geocode_to_order",
        "GEOCODE_OUTCOME_SKIPPED",
        "GEOCODE_OUTCOME_SUCCESS",
        "GEOCODE_OUTCOME_FAILED",
        "GEOCODE_OUTCOME_NO_ADDRESS",
    ]

    assert namespaced_geocode_helpers.__all__ == expected_public_names
    assert namespaced_geocode_helpers.__all__ == expected_public_names


def test_namespaced_order_geocode_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical order geocode helpers."""
    expected_public_names = [
        "apply_erp_order_site_address_to_sd",
        "reset_order_geocode_on_address_change",
        "clear_order_geocode_coords",
    ]

    assert namespaced_order_geocode.__all__ == expected_public_names
    assert namespaced_order_geocode.__all__ == expected_public_names


def test_namespaced_measurement_manager_colors_shim_preserves_canonical_contract() -> None:
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

    assert namespaced_measurement_manager_colors.__all__ == expected_public_names


def test_namespaced_erp_shipment_settings_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical ERP shipment settings contract."""
    expected_public_names = [
        "ERP_SHIPMENT_SETTINGS_KEY",
        "ERP_SHIPMENT_SETTINGS_PATH",
        "DEFAULT_ERP_WORKER_CAPACITY",
        "normalize_measurement_managers",
        "normalize_drawing_manager_en",
        "normalize_erp_shipment_workers",
        "is_order_assigned_to_user_for_construction",
        "is_order_mine_for_user",
        "load_erp_shipment_settings",
        "save_erp_shipment_settings",
    ]

    assert namespaced_erp_shipment_settings.__all__ == expected_public_names


def test_namespaced_erp_display_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical ERP display contract."""
    expected_public_names = [
        "_normalize_for_search",
        "get_today_kst",
        "format_datetime_kst",
        "self_measurement_four_checks_done",
        "_extract_name_candidate",
        "_manager_candidates",
        "_lookup_user_name_from_candidate",
        "normalize_manager_name",
        "clean_dict_like_name",
        "_ensure_dict",
        "_normalize_date_to_yyyymmdd",
        "apply_erp_display_fields",
        "erp_shipping_price_from_structured",
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

    assert namespaced_erp_display.__all__ == expected_public_names


def test_erp_pages_use_canonical_erp_display_imports() -> None:
    """ERP page modules should bind display helpers from the canonical namespace."""
    import foms.web.cs.as_dashboard as erp_as_page
    import foms.web.orders.dashboard as erp_dashboard
    import foms.web.drawing.workbench as erp_drawing_workbench
    from foms.web.measurement import dashboard as erp_measurement_dashboard
    from foms.web.production import dashboard as erp_production_page
    from foms.web.construction import dashboard as erp_construction_dashboard
    from foms.web.orders import trash as order_trash
    import foms.web.shipment.dashboard as erp_shipment_page
    import foms.web.orders.edit as order_edit

    assert erp_as_page._ensure_dict is namespaced_erp_display._ensure_dict
    assert (
        erp_as_page.apply_erp_display_fields_to_orders
        is namespaced_erp_display.apply_erp_display_fields_to_orders
    )
    assert erp_as_page.get_today_kst is namespaced_erp_display.get_today_kst

    assert erp_construction_dashboard._ensure_dict is namespaced_erp_display._ensure_dict
    assert erp_construction_dashboard._erp_get_stage is namespaced_erp_display._erp_get_stage
    assert erp_construction_dashboard._erp_has_media is namespaced_erp_display._erp_has_media
    assert erp_construction_dashboard._erp_alerts is namespaced_erp_display._erp_alerts
    assert (
        erp_construction_dashboard.self_measurement_four_checks_done
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
    from foms.api import erp_map
    from foms.api import measurement as erp_measurement
    from foms.api.cs import as_orders as erp_orders_as
    from foms.api.cs import dashboard as erp_orders_completion
    from foms.api import orders as orders_api

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
    assert orders_api.get_today_kst is namespaced_erp_display.get_today_kst


def test_erp_display_lazy_callers_use_canonical_import_paths() -> None:
    """Lazy display imports should reference the canonical namespace path."""
    import foms.web.orders.history as erp_history_page
    from foms.api import erp_map
    from foms.api import measurement as erp_measurement
    from foms.api import orders as orders_api
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
    from foms.api.measurement import map as measurement_map_mod

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


def test_wr_o1_orders_adapter_shell_collapsed_to_canonical_module() -> None:
    """WR-O1 (B11B): orders API lives on foms.api.orders; apps.api.orders overlay removed."""
    assert find_spec_or_none("apps.api.orders") is None

    from foms.api import orders as canonical_orders

    assert canonical_orders.orders_bp is not None

    canonical_route_source = inspect.getsource(canonical_orders.api_orders)
    assert '@orders_bp.route("/orders")' in canonical_route_source
    assert "@login_required" in canonical_route_source

    orders_init = (_REPO_ROOT / "foms" / "api" / "orders" / "__init__.py").read_text(encoding="utf-8")
    assert "orders_bp = Blueprint(" in orders_init
    assert '@orders_bp.route("/orders")' in orders_init

    registry_source = (_REPO_ROOT / "foms" / "platform" / "blueprints.py").read_text(encoding="utf-8")
    assert "from foms.api.orders import orders_bp" in registry_source
    assert "from apps.api.orders import orders_bp" not in registry_source


def test_namespaced_erp_order_detail_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical order detail helpers."""
    expected_public_names = [
        "build_order_detail_payload_map",
        "attach_order_detail_payloads",
    ]

    assert namespaced_erp_order_detail.__all__ == expected_public_names


def test_namespaced_erp_product_items_shim_preserves_canonical_contract() -> None:
    """The legacy services path should re-export the canonical ERP product item helpers."""
    expected_public_names = [
        "build_product_items_for_order",
        "build_product_items_for_orders",
    ]

    assert namespaced_erp_product_items.__all__ == expected_public_names
    assert namespaced_erp_product_items.__all__ == expected_public_names


def test_namespaced_erp_policy_shim_preserves_canonical_contract() -> None:
    """foms.services.erp_policy exposes policy helpers and task specs."""
    assert "AutoTaskSpec" in namespaced_erp_policy.__all__
    assert "can_modify_domain" in namespaced_erp_policy.__all__
    assert callable(namespaced_erp_policy.can_modify_domain)


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
    """ERP automation module should bind build_auto_tasks from the canonical namespace."""
    from foms.services.orders import erp_automation as erp_automation_mod

    assert erp_automation_mod.build_auto_tasks is namespaced_erp_policy.build_auto_tasks


def test_erp_dashboard_uses_canonical_erp_policy_import() -> None:
    """ERP dashboard should bind policy constants from the canonical namespace."""
    import foms.web.orders.dashboard as erp_dashboard

    assert erp_dashboard.STAGE_LABELS is namespaced_erp_policy.STAGE_LABELS
    assert erp_dashboard.recommend_owner_team is namespaced_erp_policy.recommend_owner_team


def test_quest_api_uses_canonical_erp_policy_import() -> None:
    """Quest API should bind policy helpers from the canonical namespace."""
    from foms.api import quest

    assert quest.get_stage is namespaced_erp_policy.get_stage
    assert quest.check_quest_approvals_complete is namespaced_erp_policy.check_quest_approvals_complete


def test_erp_display_canonical_module_uses_canonical_erp_policy_import() -> None:
    """Canonical erp_display should import ERP policy from the canonical namespace."""
    module_source = inspect.getsource(namespaced_erp_display)

    assert "from foms.services.erp_policy import (" in module_source


def test_personal_board_uses_canonical_erp_policy_imports() -> None:
    """Personal board API should use canonical erp_policy in module and lazy imports."""
    from foms.api import personal_board

    assert personal_board.DEFAULT_OWNER_TEAM_BY_STAGE is namespaced_erp_policy.DEFAULT_OWNER_TEAM_BY_STAGE

    order_card_source = inspect.getsource(personal_board._order_card)
    assert "from foms.services.erp_policy import STAGE_NAME_TO_CODE" in order_card_source

    schedule_source = inspect.getsource(personal_board._schedule_today_tomorrow)
    assert "from foms.services.erp_policy import STAGE_NAME_TO_CODE, STAGE_LABELS" in schedule_source


def test_wr_p1_personal_board_adapter_shell_retired() -> None:
    """WR-P1: personal board Blueprint shell should live on the canonical module only."""
    from foms.api import personal_board

    assert personal_board.personal_board_bp is not None
    assert find_spec_or_none("apps.api.personal_board") is None

    route_source = inspect.getsource(personal_board.api_summary)
    assert '@personal_board_bp.route("/summary", methods=["GET"])' in route_source
    assert "@login_required" in route_source

    registry_source = (_REPO_ROOT / "foms" / "platform" / "blueprints.py").read_text(encoding="utf-8")
    assert "from foms.api.personal_board import personal_board_bp" in registry_source
    assert "from apps.api.personal_board import personal_board_bp" not in registry_source


def test_wave8_erp_completion_page_legacy_bridge_retired_canonical_smoke() -> None:
    """W8-B5: apps.erp_completion_page shim removed; canonical CS completion dashboard is authoritative."""
    assert find_spec_or_none("apps.erp_completion_page") is None
    from foms.web.cs import completion_dashboard as canonical

    assert canonical.erp_completion_page_bp is not None
    assert canonical.erp_completion_dashboard is not None


def test_cs_completion_dashboard_template_path_exists() -> None:
    """Canonical completion template must exist under templates/cs/ (Wave 4 namespace)."""
    template_path = _REPO_ROOT / "templates" / "cs" / "completion_dashboard.html"
    assert template_path.is_file()


def test_wave8_erp_production_page_legacy_bridge_retired_canonical_smoke() -> None:
    """W8-B5: apps.erp_production_page shim removed; canonical production dashboard is authoritative."""
    assert find_spec_or_none("apps.erp_production_page") is None
    from foms.web.production import dashboard as canonical

    assert canonical.erp_production_page_bp is not None
    assert canonical.erp_production_dashboard is not None


def test_wave8_remaining_direct_import_bridges_retired() -> None:
    """W8-B5: files/address/measurement API + measurement dashboard legacy import paths removed."""
    assert find_spec_or_none("apps.api") is None
    assert find_spec_or_none("apps.api.files") is None
    assert find_spec_or_none("apps.api.address") is None
    assert find_spec_or_none("apps.api.erp_measurement") is None
    assert find_spec_or_none("apps.erp_measurement_dashboard") is None


def test_production_dashboard_template_path_exists() -> None:
    """Canonical production dashboard template must exist (Wave 4 namespace)."""
    assert (_REPO_ROOT / "templates" / "production" / "dashboard.html").is_file()


def test_strict_canonical_root_erp_dashboard_thin_wrappers_removed() -> None:
    """§2.2.1: root `templates/erp_*_dashboard.html` thin shims removed; canonical context paths only."""
    for name in (
        "erp_measurement_dashboard.html",
        "erp_completion_dashboard.html",
        "erp_production_dashboard.html",
    ):
        p = _REPO_ROOT / "templates" / name
        assert not p.is_file(), (
            f"Remove legacy root wrapper; canonical lives under templates/{{context}}/ — {name}"
        )


def test_strict_canonical_shipment_dashboard_template() -> None:
    """§2.2.1: ERP shipment dashboard lives under templates/shipment/dashboard.html."""
    dash = _REPO_ROOT / "templates" / "shipment" / "dashboard.html"
    assert dash.is_file()
    import foms.web.shipment.dashboard as erp_shipment_page

    src = inspect.getsource(erp_shipment_page.erp_shipment_dashboard)
    assert "shipment/dashboard.html" in src
    assert "erp_shipment_dashboard.html" not in src


def test_strict_canonical_construction_dashboard_template() -> None:
    """§2.2.1: ERP construction dashboard lives under templates/construction/dashboard.html."""
    dash = _REPO_ROOT / "templates" / "construction" / "dashboard.html"
    assert dash.is_file()
    from foms.web.construction import dashboard as construction_dashboard

    src = inspect.getsource(construction_dashboard.erp_construction_dashboard)
    assert "construction/dashboard.html" in src
    assert "erp_construction_dashboard.html" not in src


def test_strict_canonical_as_cs_dashboard_template() -> None:
    """§2.2.1: AS/CS dashboard lives under templates/cs/as_dashboard.html."""
    dash = _REPO_ROOT / "templates" / "cs" / "as_dashboard.html"
    assert dash.is_file()
    import foms.web.cs.as_dashboard as erp_as_page

    src = inspect.getsource(erp_as_page.erp_as_dashboard)
    assert "cs/as_dashboard.html" in src
    assert "erp_as_dashboard.html" not in src


def test_strict_canonical_orders_dashboard_templates() -> None:
    """§2.2.1: Main ERP dashboard + history under templates/orders/."""
    assert (_REPO_ROOT / "templates" / "orders" / "dashboard.html").is_file()
    assert (_REPO_ROOT / "templates" / "orders" / "history_dashboard.html").is_file()
    import foms.web.orders.dashboard as erp_dashboard
    import foms.web.orders.history as erp_history_page

    dash_src = inspect.getsource(erp_dashboard.erp_dashboard)
    assert "orders/dashboard.html" in dash_src
    assert "erp_dashboard.html" not in dash_src

    hist_src = inspect.getsource(erp_history_page.history_dashboard)
    assert "orders/history_dashboard.html" in hist_src
    assert "erp_history_dashboard.html" not in hist_src


def test_strict_canonical_shipment_settings_page_template() -> None:
    """§2.2.1: ERP shipment settings page under templates/shipment/settings.html."""
    p = _REPO_ROOT / "templates" / "shipment" / "settings.html"
    assert p.is_file()
    from foms.api.shipment import settings as shipment_settings_mod

    src = inspect.getsource(shipment_settings_mod.erp_shipment_settings)
    assert "shipment/settings.html" in src
    assert "erp_shipment_settings.html" not in src


def test_strict_canonical_drawing_workbench_templates() -> None:
    """§2.2.1: Drawing workbench under templates/drawing/workbench_*.html."""
    assert (_REPO_ROOT / "templates" / "drawing" / "workbench_dashboard.html").is_file()
    assert (_REPO_ROOT / "templates" / "drawing" / "workbench_detail.html").is_file()
    import foms.web.drawing.workbench as erp_drawing_workbench

    dash_src = inspect.getsource(erp_drawing_workbench.erp_drawing_workbench_dashboard)
    assert "drawing/workbench_dashboard.html" in dash_src
    assert "erp_drawing_workbench_dashboard.html" not in dash_src

    detail_src = inspect.getsource(erp_drawing_workbench.erp_drawing_workbench_detail)
    assert "drawing/workbench_detail.html" in detail_src
    assert "erp_drawing_workbench_detail.html" not in detail_src


def test_strict_canonical_orders_object_standalone_template() -> None:
    """§2.2.1: legacy root erp_object.html → templates/orders/object.html (no active route in repo)."""
    assert (_REPO_ROOT / "templates" / "orders" / "object.html").is_file()
    assert not (_REPO_ROOT / "templates" / "erp_object.html").is_file()


def test_strict_canonical_templates_root_has_no_html_files() -> None:
    """SFC-B7 (SG7): no Jinja page templates at templates/*.html — only context dirs + partials/shared."""
    loose = sorted(p.name for p in (_REPO_ROOT / "templates").glob("*.html"))
    assert not loose, f"templates/ root must not contain .html files — move under context/: {loose}"


def test_strict_canonical_static_js_css_taxonomy() -> None:
    """§2.2.1: static/js + static/css physical tree — no legacy erp/wam families at repo root of js/css."""
    static = _REPO_ROOT / "static"
    assert not (static / "js" / "erp").is_dir()
    assert not (static / "js" / "wam").is_dir()
    assert not (static / "css" / "wam").is_dir()
    assert not (static / "css" / "erp-pro.css").is_file()
    assert (static / "css" / "foundation" / "erp-pro.css").is_file()
    assert (static / "js" / "runtime" / "common_utils.js").is_file()
    assert (static / "js" / "orders" / "erp-order-shared.js").is_file()
    assert (static / "js" / "channel" / "core.js").is_file()
    assert (static / "js" / "shipment" / "dashboard-columns.js").is_file()
    assert (static / "css" / "contexts" / "channel" / "tokens.css").is_file()


def test_strict_canonical_static_materialized_nodes_sfc_b8() -> None:
    """SFC-B8: §2.2.1 `static/js` + `static/css` nodes from B1 gap inventory — dirs + `.gitkeep` sentinel."""
    static = _REPO_ROOT / "static"
    for name in ("drawing", "production", "construction", "cs", "admin", "auth"):
        p = static / "js" / name
        assert p.is_dir(), f"expected static/js/{name}/ (rebaseline SPEC §2.2.1)"
        assert (p / ".gitkeep").is_file(), f"static/js/{name}/ must include .gitkeep until context assets exist"
    for name in ("layout", "components"):
        p = static / "css" / name
        assert p.is_dir(), f"expected static/css/{name}/ (rebaseline SPEC §2.2.1)"
        assert (p / ".gitkeep").is_file(), f"static/css/{name}/ must include .gitkeep until layout/component CSS lands"


def test_strict_canonical_api_package_shape_sfc_b9() -> None:
    """SFC-B9 (SG3 slice): `foms/api/files` + `foms/api/measurement` as packages per §6.12 — no flat `*.py` twins."""
    api = _REPO_ROOT / "foms" / "api"
    files_pkg = api / "files"
    assert files_pkg.is_dir()
    assert (files_pkg / "__init__.py").is_file()
    assert (files_pkg / "routes.py").is_file()
    assert not (api / "files.py").is_file(), "flat foms/api/files.py retired — use foms.api.files package"

    meas_pkg = api / "measurement"
    assert meas_pkg.is_dir()
    assert (meas_pkg / "__init__.py").is_file()
    assert (meas_pkg / "routes.py").is_file()
    assert (meas_pkg / "map.py").is_file()
    assert not (api / "measurement.py").is_file()
    assert not (api / "measurement_map.py").is_file()


def test_strict_canonical_root_manual_artifacts_sfc_b10a() -> None:
    """§6.13 SFC-B10A: manuals/scripts/data DB artifacts cleared from repo root."""
    root = _REPO_ROOT
    forbidden = (
        "start_foms_utf8.bat",
        "findings.md",
        "progress.md",
        "task_plan.md",
        "MIGRATION_GUIDE_RAILWAY.md",
        "MIGRATION_RAILWAY_R2.md",
        "RAILWAY_ENV_VARS.md",
        "TEST_GUIDE.md",
        "foms.dump",
        "furniture_orders.db",
        "migration_ready.db",
        "ops_browser_qa.db",
        "foms_address_learning_data.json",
        "menu_config.json",
    )
    for name in forbidden:
        assert not (root / name).exists(), f"B10A: root must not contain {name}"

    assert (root / "scripts" / "maintenance" / "start_foms_utf8.bat").is_file()
    assert (root / "docs" / "context" / "analysis" / "findings.md").is_file()
    assert (root / "docs" / "context" / "analysis" / "progress.md").is_file()
    assert (root / "docs" / "context" / "analysis" / "task_plan.md").is_file()
    assert (root / "docs" / "guides" / "MIGRATION_GUIDE_RAILWAY.md").is_file()
    assert (root / "docs" / "guides" / "MIGRATION_RAILWAY_R2.md").is_file()
    assert (root / "docs" / "guides" / "RAILWAY_ENV_VARS.md").is_file()
    assert (root / "docs" / "guides" / "TEST_GUIDE.md").is_file()
    assert (root / "data" / "admin" / "menu_config.json").is_file()
    assert (root / "data" / "address" / "foms_address_learning_data.json").is_file()
    # PTC §4.3 / §2.6.2: runtime dumps/SQLite live under FOMS_RUNTIME_OUTPUT_ROOT — not repo data/dumps|localdb.
    # Do not assert data/dumps or data/localdb directories here (see test_ptc_tracked_data_forbids_runtime_output_paths).


def test_strict_canonical_root_deploy_tooling_artifacts_sfc_b10b() -> None:
    """§6.14 SFC-B10B: deploy/config/tooling artifacts cleared from repo root (ledger §2.5)."""
    root = _REPO_ROOT
    forbidden_files = (
        ".cursorrules",
        "app.yaml",
        "runtime.txt",
        "railway_bootstrap.py",
        "pyrightconfig.json",
    )
    for name in forbidden_files:
        assert not (root / name).exists(), f"B10B: root must not contain {name}"
    assert not (root / "config").exists(), "B10B: root config/ package removed (dead duplicate of foms.services.rate_limit)"

    assert (root / "scripts" / "ops" / "railway_bootstrap.py").is_file()
    assert (root / "tools" / "harness" / "pyrightconfig.json").is_file()
    legacy = root / "docs" / "context" / "manual-artifacts" / "legacy-deploy"
    assert (legacy / "app.yaml").is_file()
    assert (legacy / "runtime.txt").is_file()
    assert (root / ".vscode" / "settings.json").is_file()


def test_strict_canonical_tests_support_tree_taxonomy() -> None:
    """§2.2.1: domain pytest modules live under tests/domains/; load assets under tests/harness/load/."""
    tests_dir = _REPO_ROOT / "tests"
    assert not list(tests_dir.glob("test_*.py")), "domain tests must not sit at tests/ root"
    assert (tests_dir / "domains").is_dir()
    assert (tests_dir / "domains" / "__init__.py").is_file()
    assert not (tests_dir / "load").is_dir(), "tests/load/ retired — use tests/harness/load/"
    assert (tests_dir / "harness" / "load" / "foms_150_realistic.js").is_file()


def test_strict_canonical_scripts_taxonomy() -> None:
    """§2.2.1: scripts/ contains only ops/, maintenance/, migrations/ — no loose root scripts."""
    scripts_dir = _REPO_ROOT / "scripts"
    assert scripts_dir.is_dir()
    for p in scripts_dir.iterdir():
        if p.name.startswith(".") or p.name == "__pycache__":
            continue
        assert p.is_dir(), f"scripts/ must not contain loose files (use ops|maintenance|migrations): {p.name}"
        assert p.name in {"ops", "maintenance", "migrations"}, f"unexpected scripts child: {p.name}"


def test_strict_canonical_tools_taxonomy() -> None:
    """§2.2.1: tools/ contains harness/, ops/, smoke/, research_center/, designer/, cron/, design/ (+ README).

    designer/ added (PG-B2/PG-B5+): fixture management CLI tools for FOMS Brain.
    cron/ added: Railway scheduled job entrypoints (e.g. cleanup_order_drafts).
    design/ added: design SSOT lint helpers (ssot_lint.py).
    perf/ added: performance regression scanner (perf_scan.py — perf-guard/perf-audit skills).
    tests/ added (PACKET-HARNESS-00): bug-audit packet runner (run_packet.ps1, report §8.1).
    """
    tools_dir = _REPO_ROOT / "tools"
    assert tools_dir.is_dir()
    assert (tools_dir / "README.md").is_file()
    allowed = {
        "harness",
        "ops",
        "smoke",
        "research_center",
        "designer",
        "cron",
        "design",
        "sketchup_analyzer",
        "perf",
        "tests",
    }
    for p in tools_dir.iterdir():
        if p.name.startswith(".") or p.name == "README.md" or p.name == "__pycache__":
            continue
        assert p.is_dir(), f"tools/ must not contain loose non-README files: {p.name}"
        assert p.name in allowed, f"unexpected tools child: {p.name}"


def test_strict_canonical_docs_taxonomy() -> None:
    """§2.2.1: docs/ top-level dirs + root file allowlist; nested guides/validation + context bundles.

    design/ added (PG-B1): FOMS Brain design system documentation.
    """
    docs = _REPO_ROOT / "docs"
    allowed_dirs = frozenset(
        {
            "specs",
            "plans",
            "evolution",
            "guides",
            "incidents",
            "harness",
            "context",
            "design",
            "research",
            "runbooks",
        }
    )
    allowed_root_files = frozenset({"AI_STATUS.md", "AI_CHANGELOG.md", "ARCHIVE_INDEX.md"})
    for p in docs.iterdir():
        if p.name.startswith(".") or p.name == "__pycache__":
            continue
        if p.is_dir():
            assert p.name in allowed_dirs, f"unexpected docs/ child dir: {p.name}"
        else:
            assert p.name in allowed_root_files, (
                f"unexpected docs/ root file (use docs/guides/ or allowlist): {p.name}"
            )
    for name in allowed_dirs:
        assert (docs / name).is_dir(), f"missing canonical docs/ child: {name}"
    assert (docs / "guides" / "validation").is_dir()
    assert (docs / "context" / "analysis").is_dir()
    assert (docs / "context" / "manual-artifacts").is_dir()


def test_strict_canonical_apps_overlay_directory_removed_sfc_b11b_closeout() -> None:
    """§6.15–6.16 SFC-B11B closeout: transition ``apps/`` overlay directory removed (SF3 / SG1)."""
    apps_dir = _REPO_ROOT / "apps"
    assert not apps_dir.exists(), (
        "apps/ overlay must be removed; canonical owners live under foms.web / foms.api only"
    )
    assert find_spec_or_none("apps") is None


def test_strict_canonical_services_overlay_directory_removed_sfc_b11c_closeout() -> None:
    """SFC-B11C closeout: root ``services/`` shim directory removed; canonical owner is ``foms.services``."""
    services_dir = _REPO_ROOT / "services"
    assert not services_dir.exists(), (
        "services/ overlay must be removed; canonical business logic lives under foms.services only"
    )
    assert find_spec_or_none("services") is None


def test_strict_canonical_src_overlay_directory_removed_sfc_b11d_closeout() -> None:
    """SFC-B11D closeout: ambiguous root ``src/`` removed (SF3); prototype sources live under approved non-product home."""
    src_dir = _REPO_ROOT / "src"
    assert not src_dir.exists(), (
        "root src/ must be removed; non-product TS/RN prototype is under "
        "Add In Program/WDPlanner/legacy-mobile-prototype/"
    )
    legacy = _REPO_ROOT / "Add In Program" / "WDPlanner" / "legacy-mobile-prototype"
    assert legacy.is_dir(), "expected relocated prototype directory to exist"


# --- SLG literal-gap closed-set gates (remediation plan §4; freeze SLG-B1) ---

_SLG_TEMPLATES_TOP_LEVEL_ALLOWED = frozenset(
    {
        "admin",
        "auth",
        "channel",
        "construction",
        "cs",
        "drawing",
        "macros",
        "measurement",
        "orders",
        "partials",
        "production",
        "shipment",
        "wdcalculator",
    }
)

_SLG_FOMS_WEB_TOP_LEVEL_ALLOWED = frozenset(
    {
        "admin",
        "auth",
        "channel",
        "construction",
        "cs",
        "drawing",
        "measurement",
        "orders",
        "production",
        "shipment",
        "wdcalculator",
    }
)

_SLG_FOMS_API_TOP_LEVEL_ALLOWED = frozenset(
    {
        "admin",
        "auth",
        "channel",
        "construction",
        "cs",
        "drawing",
        "files",
        "kakao",
        "measurement",
        "notifications",
        "orders",
        "production",
        "shipment",
        "wdcalculator",
    }
)

_SLG_FOMS_SERVICES_TOP_LEVEL_ALLOWED = frozenset(
    {
        "admin",
        "auth",
        "channel",
        "common",
        "construction",
        "crew",
        "cs",
        "drawing",
        "files",
        # NAVER-INGEST-01 §3.2: 외부 판매채널 API 클라이언트 경계(네이버 커머스API 등).
        # 도메인 규칙이 아니라 인증·전송·재시도만 담는 자리라 orders/ 와 분리한다.
        "integrations",
        "jobs",
        "measurement",
        "notifications",
        "orders",
        "production",
        "security",
        "shipment",
        "wdcalculator",
    }
)


def _slg_iter_top_level_dirs(base: Path) -> set[str]:
    """Return non-hidden, non-``__pycache__`` child directory names under ``base``."""
    if not base.is_dir():
        return set()
    return {
        p.name
        for p in base.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name != "__pycache__"
    }


def _slg_py_paths_for_render_template_gate(repo_root: Path) -> list[Path]:
    """Python files scanned for ``render_template(..., 'errors/...')`` (product + bootstrap)."""
    paths: list[Path] = []
    paths.extend(sorted((repo_root / "foms").rglob("*.py")))
    for name in ("app.py", "run.py"):
        candidate = repo_root / name
        if candidate.is_file():
            paths.append(candidate)
    return paths


_RE_RENDER_TEMPLATE_ERRORS = re.compile(
    r"""render_template\s*\(\s*(["'])errors/"""
)


def test_slg_literal_gap_templates_top_level_dirs_closed_set() -> None:
    """§4.1: ``templates/`` top-level dirs == allowlist exactly (no ``shared``, ``errors``)."""
    root = _REPO_ROOT / "templates"
    actual = _slg_iter_top_level_dirs(root)
    assert actual == _SLG_TEMPLATES_TOP_LEVEL_ALLOWED, (
        "templates/ top-level dirs must match §4.1 allowlist exactly:\n"
        f"  expected={sorted(_SLG_TEMPLATES_TOP_LEVEL_ALLOWED)}\n"
        f"  actual={sorted(actual)}"
    )


def test_slg_literal_gap_foms_web_top_level_dirs_closed_set() -> None:
    """§4.2: ``foms/web/`` top-level dirs == allowlist (no legacy buckets)."""
    root = _REPO_ROOT / "foms" / "web"
    actual = _slg_iter_top_level_dirs(root)
    assert actual == _SLG_FOMS_WEB_TOP_LEVEL_ALLOWED, (
        "foms/web/ top-level dirs must match §4.2 allowlist exactly:\n"
        f"  expected={sorted(_SLG_FOMS_WEB_TOP_LEVEL_ALLOWED)}\n"
        f"  actual={sorted(actual)}"
    )


def test_slg_literal_gap_foms_api_top_level_dirs_closed_set() -> None:
    """§4.3: ``foms/api/`` top-level dirs == allowlist (no ``chat``, ``attachments_internal``)."""
    root = _REPO_ROOT / "foms" / "api"
    actual = _slg_iter_top_level_dirs(root)
    assert actual == _SLG_FOMS_API_TOP_LEVEL_ALLOWED, (
        "foms/api/ top-level dirs must match §4.3 allowlist exactly:\n"
        f"  expected={sorted(_SLG_FOMS_API_TOP_LEVEL_ALLOWED)}\n"
        f"  actual={sorted(actual)}"
    )


def test_slg_literal_gap_foms_services_top_level_dirs_closed_set() -> None:
    """§4.4: ``foms/services/`` top-level dirs == allowlist (no ``erp_policy_internal``)."""
    root = _REPO_ROOT / "foms" / "services"
    actual = _slg_iter_top_level_dirs(root)
    assert actual == _SLG_FOMS_SERVICES_TOP_LEVEL_ALLOWED, (
        "foms/services/ top-level dirs must match §4.4 allowlist exactly:\n"
        f"  expected={sorted(_SLG_FOMS_SERVICES_TOP_LEVEL_ALLOWED)}\n"
        f"  actual={sorted(actual)}"
    )


def test_slg_literal_gap_no_templates_shared_layout_file() -> None:
    """Closeout: ``templates/shared/layout.html`` must not exist (shell retire)."""
    p = _REPO_ROOT / "templates" / "shared" / "layout.html"
    assert not p.is_file(), f"forbidden template file must be removed: {p.relative_to(_REPO_ROOT)}"


def test_slg_literal_gap_no_templates_errors_dir() -> None:
    """Closeout: ``templates/errors/`` must not exist."""
    p = _REPO_ROOT / "templates" / "errors"
    assert not p.is_dir(), f"forbidden template dir must be removed: {p.relative_to(_REPO_ROOT)}"


def test_slg_literal_gap_no_render_template_errors_namespace() -> None:
    """No ``render_template(\"errors/...\")`` in product/bootstrap Python (inline error responses instead)."""
    bad: list[str] = []
    for path in _slg_py_paths_for_render_template_gate(_REPO_ROOT):
        text = path.read_text(encoding="utf-8")
        if _RE_RENDER_TEMPLATE_ERRORS.search(text):
            rel = path.relative_to(_REPO_ROOT)
            bad.append(str(rel))
    assert not bad, "render_template('errors/...') is forbidden:\n" + "\n".join(bad)


def test_slg_literal_gap_no_extends_shared_layout_html() -> None:
    """No ``{% extends \"shared/layout.html\" %}`` under ``templates/``."""
    hits: list[str] = []
    templates = _REPO_ROOT / "templates"
    for path in sorted(templates.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        if 'extends "shared/layout.html"' in text or "extends 'shared/layout.html'" in text:
            hits.append(str(path.relative_to(_REPO_ROOT)))
    assert not hits, "shared/layout extends must be retired:\n" + "\n".join(hits)


def test_slg_literal_gap_partials_shared_no_extends_tag() -> None:
    """``templates/partials/shared/*.html`` must not use ``{% extends ... %}`` (partial-only contract)."""
    partial = _REPO_ROOT / "templates" / "partials" / "shared"
    bad: list[str] = []
    for path in sorted(partial.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        if re.search(r"{%\s*extends\s+", text):
            bad.append(str(path.relative_to(_REPO_ROOT)))
    assert not bad, "partials/shared must not extend a parent layout:\n" + "\n".join(bad)


def test_slg_literal_gap_partials_shared_no_document_html_shell() -> None:
    """``templates/partials/shared/*.html`` must not contain full-page ``<!DOCTYPE`` / ``<html`` markers."""
    partial = _REPO_ROOT / "templates" / "partials" / "shared"
    bad: list[str] = []
    for path in sorted(partial.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        if "<!doctype" in lower or re.search(r"<\s*html\b", lower):
            bad.append(str(path.relative_to(_REPO_ROOT)))
    assert not bad, "partials/shared must not embed document/html shell:\n" + "\n".join(bad)


def test_slg_literal_gap_no_orders_erp_policy_internal_dir() -> None:
    """Forbidden nested package ``foms/services/orders/erp_policy_internal/`` must not exist."""
    p = _REPO_ROOT / "foms" / "services" / "orders" / "erp_policy_internal"
    assert not p.is_dir(), f"forbidden nested dir: {p.relative_to(_REPO_ROOT)}"


# --- PAC post-audit correction gates (2026-04-16 plan; PAC-B1 freeze) ---

_PAC_PARTIALS_SHARED_HTML_ALLOWLIST = frozenset(
    {
        "alpine_layout.html",
        # WRITE-GUARD-01 CSRF 배선 정본 partial. layout_head 와 standalone 문서
        # (measurement/map_view.html)가 함께 include 한다(2026-08-31).
        "csrf_bootstrap.html",
        "erp_mobile_bottom_nav.html",
        "erp_mobile_menu_drawer.html",
        "erp_mobile_notification_panel.html",
        "erp_mobile_order_timeline_sheet.html",
        "erp_mobile_urgent_call_panel.html",
        "erp_mobile_queue_card_v2.html",
        "erp_mobile_shell.html",
        "erp_mobile_shell_header.html",
        "erp_mobile_v2_tab_notice.html",
        "erp_sub_nav.html",
        # NAVER-BULKDISPATCH-01 T4: 일괄 발송처리 버튼 배선. 워크벤치(admin)와 실측
        # 대시보드(measurement) **둘 다** include 하는 교차 도메인 파셜이라 여기 산다 —
        # 되돌릴 수 없는 조작의 확인 문구와 요청 코드를 두 벌로 두면 한쪽만 고쳐진다.
        "naver_bulk_dispatch_button.html",
        "foms_alpine_toast.html",
        "foms_app_shell.html",
        "foms_attachment_preview_modal.html",
        "foms_master_list.html",
        "foms_mobile_queue_attachment_preview_bundle.html",
        "foms_order_contact_kv.html",
        "foms_order_detail_fragment.html",
        "foms_p2_surface_bundle.html",
        "foms_search_overlay.html",
        "foms_search_results_partial.html",
        "foms_side_tab.html",
        "foms_split_shell.html",
        "foms_density_toggle.html",
        "foms_tablet_rail.html",
        "foms_theme_toggle.html",
        "htmx_layout.html",
        "layout_flash.html",
        "layout_head.html",
        "layout_nav.html",
        "layout_scripts.html",
        "mobile_queue_pager.html",
        "status_select_options.html",
    }
)

_RE_FORBIDDEN_CHAT_URL_FOR = re.compile(
    r"url_for\s*\(\s*['\"]chat\.chat(?:_scripts_js)?['\"]"
)

_RE_RENDER_TEMPLATE_PARTIALS_HTTP_ERRORS = re.compile(
    r"""render_template\s*\(\s*(["'])partials/http_errors/"""
)


def _pac_paths_for_chat_url_for_gate(repo_root: Path) -> list[Path]:
    """Templates + product Python scanned for forbidden ``url_for('chat.chat'...)`` page endpoint strings."""
    paths: list[Path] = []
    paths.extend(sorted((repo_root / "templates").rglob("*.html")))
    paths.extend(sorted((repo_root / "foms").rglob("*.py")))
    for name in ("app.py", "run.py"):
        candidate = repo_root / name
        if candidate.is_file():
            paths.append(candidate)
    return paths


def test_pac_b1_no_templates_partials_http_errors_dir() -> None:
    """``templates/partials/http_errors/`` must not exist (404/500 owner is platform inline HTML, not templates)."""
    p = _REPO_ROOT / "templates" / "partials" / "http_errors"
    assert not p.is_dir(), f"forbidden template dir must be removed: {p.relative_to(_REPO_ROOT)}"


def test_pac_b1_no_render_template_partials_http_errors() -> None:
    """No ``render_template("partials/http_errors/...")`` in product/bootstrap Python."""
    bad: list[str] = []
    for path in _slg_py_paths_for_render_template_gate(_REPO_ROOT):
        text = path.read_text(encoding="utf-8")
        if _RE_RENDER_TEMPLATE_PARTIALS_HTTP_ERRORS.search(text):
            bad.append(str(path.relative_to(_REPO_ROOT)))
    assert not bad, "render_template('partials/http_errors/...') is forbidden:\n" + "\n".join(bad)


def test_pac_b1_no_forbidden_chat_page_url_for_strings() -> None:
    """Page templates and product code must not use ``chat`` blueprint endpoint names (use ``channel_chat_pages.*``)."""
    bad: list[str] = []
    for path in _pac_paths_for_chat_url_for_gate(_REPO_ROOT):
        text = path.read_text(encoding="utf-8")
        if _RE_FORBIDDEN_CHAT_URL_FOR.search(text):
            bad.append(str(path.relative_to(_REPO_ROOT)))
    assert not bad, "forbidden chat blueprint url_for strings (use channel_chat_pages.*):\n" + "\n".join(bad)


def test_pac_b1_partials_shared_html_exact_allowlist() -> None:
    """``templates/partials/shared/*.html`` must match the §3.3 exact allowlist (no count-based erp_* green)."""
    partials = _REPO_ROOT / "templates" / "partials"
    assert not list(partials.glob("erp_*.html")), (
        "Legacy flat partials/erp_*.html under templates/partials/ must not exist"
    )
    shared = partials / "shared"
    assert shared.is_dir(), "expected templates/partials/shared/"
    actual = {p.name for p in shared.glob("*.html")}
    assert actual == _PAC_PARTIALS_SHARED_HTML_ALLOWLIST, (
        "templates/partials/shared/*.html must equal exact allowlist:\n"
        f"  expected={sorted(_PAC_PARTIALS_SHARED_HTML_ALLOWLIST)}\n"
        f"  actual={sorted(actual)}"
    )

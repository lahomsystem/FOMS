"""Bootstrap contract tests for the Step 4 app.py slim entrypoint."""

import app as app_module

import foms.services.app_init as namespaced_app_init
import foms.services.context_processors as namespaced_context_processors
import foms.services.rate_limit as namespaced_rate_limit


def test_root_app_module_exposes_step4_public_contract() -> None:
    """The root app module should preserve the public bootstrap contract."""
    assert app_module.app is not None
    assert hasattr(app_module, "socketio")
    assert isinstance(app_module.SOCKETIO_AVAILABLE, bool)
    assert app_module.run_auto_init is namespaced_app_init.run_auto_init
    assert app_module.init_limiter is namespaced_rate_limit.init_limiter
    assert (
        app_module.register_context_processors
        is namespaced_context_processors.register_context_processors
    )


def test_root_app_bootstrap_registers_notification_badge_view() -> None:
    """The root bootstrap should keep the notification badge endpoint registered."""
    assert "notifications.api_notifications_badge" in app_module.app.view_functions


def test_root_app_socketio_config_matches_public_exports() -> None:
    """The public Socket.IO exports should agree with the app config contract."""
    assert app_module.app.config["SOCKETIO_AVAILABLE"] is app_module.SOCKETIO_AVAILABLE
    if app_module.SOCKETIO_AVAILABLE:
        assert app_module.app.config["_SOCKETIO_INSTANCE"] is app_module.socketio
    else:
        assert app_module.socketio is None
        assert app_module.app.config["_SOCKETIO_INSTANCE"] is None

"""Focused tests for local dev server flag resolution."""

from __future__ import annotations

import run


class _FakeSocketIO:
    def __init__(self) -> None:
        self.calls: list[tuple[object, dict]] = []

    def run(self, app, **kwargs) -> None:
        self.calls.append((app, kwargs))


class _FakeApp:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def run(self, **kwargs) -> None:
        self.calls.append(kwargs)


def test_resolve_debug_mode_defaults_to_reloader_state(monkeypatch) -> None:
    """Without FLASK_DEBUG, single-process QA should default to debug off."""
    monkeypatch.delenv("FLASK_DEBUG", raising=False)

    assert run._resolve_debug_mode(True) is True
    assert run._resolve_debug_mode(False) is False


def test_resolve_debug_mode_honors_explicit_env(monkeypatch) -> None:
    """Explicit FLASK_DEBUG should override the reloader-derived default."""
    monkeypatch.setenv("FLASK_DEBUG", "1")
    assert run._resolve_debug_mode(False) is True

    monkeypatch.setenv("FLASK_DEBUG", "false")
    assert run._resolve_debug_mode(True) is False


def test_run_dev_server_passes_debug_flag_to_socketio() -> None:
    """Socket.IO startup should preserve the resolved debug flag."""
    fake_app = object()
    fake_socketio = _FakeSocketIO()

    run._run_dev_server(
        fake_app,
        fake_socketio,
        socketio_available=True,
        use_reloader=False,
        debug_enabled=False,
        should_run_startup_tasks=False,
    )

    assert len(fake_socketio.calls) == 1
    called_app, kwargs = fake_socketio.calls[0]
    assert called_app is fake_app
    assert kwargs["debug"] is False
    assert kwargs["use_reloader"] is False


def test_run_dev_server_passes_debug_flag_to_flask_app() -> None:
    """Plain Flask startup should also preserve the resolved debug flag."""
    fake_app = _FakeApp()

    run._run_dev_server(
        fake_app,
        socketio=None,
        socketio_available=False,
        use_reloader=False,
        debug_enabled=False,
        should_run_startup_tasks=False,
    )

    assert fake_app.calls == [
        {
            "host": "0.0.0.0",
            "port": 5000,
            "debug": False,
            "use_reloader": False,
        }
    ]

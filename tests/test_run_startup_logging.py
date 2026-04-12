"""Tests for local dev startup logging configuration."""

import logging

import run


def test_get_startup_log_path_returns_none_when_unset(monkeypatch):
    """Default dev startup should not write a file log."""
    monkeypatch.delenv("FOMS_STARTUP_LOG_PATH", raising=False)

    assert run._get_startup_log_path() is None


def test_build_startup_logging_handlers_defaults_to_stdout_only(monkeypatch):
    """Stdout logging remains enabled when file logging is not configured."""
    monkeypatch.delenv("FOMS_STARTUP_LOG_PATH", raising=False)

    handlers, log_path = run._build_startup_logging_handlers()
    try:
        assert log_path is None
        assert len(handlers) == 1
        assert isinstance(handlers[0], logging.StreamHandler)
        assert not any(isinstance(handler, logging.FileHandler) for handler in handlers)
    finally:
        for handler in handlers:
            handler.close()


def test_get_startup_log_path_resolves_relative_path_from_cwd(monkeypatch, tmp_path):
    """Relative opt-in paths should resolve from the current working directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FOMS_STARTUP_LOG_PATH", "logs/startup.log")

    assert run._get_startup_log_path() == str((tmp_path / "logs" / "startup.log").resolve())


def test_build_startup_logging_handlers_uses_env_path(monkeypatch, tmp_path):
    """Opt-in file logging should create parent directories outside repo root."""
    log_file = tmp_path / "runtime" / "logs" / "startup.log"
    monkeypatch.setenv("FOMS_STARTUP_LOG_PATH", str(log_file))

    handlers, log_path = run._build_startup_logging_handlers()
    try:
        assert log_path == str(log_file)
        assert log_file.parent.is_dir()
        assert any(isinstance(handler, logging.FileHandler) for handler in handlers)
    finally:
        for handler in handlers:
            handler.close()


def test_build_startup_logging_handlers_can_skip_file_logging(monkeypatch, tmp_path):
    """Reloader parent should stay stdout-only even when env opt-in exists."""
    log_file = tmp_path / "runtime" / "logs" / "startup.log"
    monkeypatch.setenv("FOMS_STARTUP_LOG_PATH", str(log_file))

    handlers, log_path = run._build_startup_logging_handlers(enable_file_logging=False)
    try:
        assert log_path is None
        assert len(handlers) == 1
        assert not any(isinstance(handler, logging.FileHandler) for handler in handlers)
        assert not log_file.exists()
    finally:
        for handler in handlers:
            handler.close()

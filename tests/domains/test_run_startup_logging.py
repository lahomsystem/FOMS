"""run.py 기동 로깅이 logging_setup SSOT로 위임되는지 검증한다 (AUDIT-LOG T1 이관 후)."""

import logging
from pathlib import Path

import run


def test_legacy_basicconfig_helpers_are_removed():
    """basicConfig 시대 헬퍼가 부활하지 않는다 — 로깅 구성은 logging_setup 단일 SSOT."""
    assert not hasattr(run, "_get_startup_log_path")
    assert not hasattr(run, "_build_startup_logging_handlers")


def test_configure_startup_logging_delegates_to_logging_setup(monkeypatch):
    """기동 구성은 configure_logging을 정확히 1회 호출하고 파일 로그 미설정 시 None."""
    monkeypatch.delenv("FOMS_STARTUP_LOG_PATH", raising=False)

    from foms.platform import logging_setup

    calls = []
    monkeypatch.setattr(logging_setup, "configure_logging", lambda: calls.append(True))

    logger, startup_log_path = run._configure_startup_logging()

    assert calls == [True]
    assert isinstance(logger, logging.Logger)
    assert logger.name == "FOMS_Startup"
    assert startup_log_path is None


def test_configure_startup_logging_reports_env_file_path(monkeypatch, tmp_path):
    """FOMS_STARTUP_LOG_PATH 설정 시 해석된 절대경로를 돌려준다(핸들러는 logging_setup 소관)."""
    from foms.platform import logging_setup

    monkeypatch.setattr(logging_setup, "configure_logging", lambda: None)
    log_file = tmp_path / "runtime" / "logs" / "startup.log"
    monkeypatch.setenv("FOMS_STARTUP_LOG_PATH", str(log_file))

    _logger, startup_log_path = run._configure_startup_logging()

    assert startup_log_path is not None
    assert Path(startup_log_path) == log_file.resolve()


def test_configure_startup_logging_resolves_relative_path_from_cwd(monkeypatch, tmp_path):
    """상대경로 opt-in은 cwd 기준 절대경로로 해석된다(구 _get_startup_log_path 계약 승계)."""
    from foms.platform import logging_setup

    monkeypatch.setattr(logging_setup, "configure_logging", lambda: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FOMS_STARTUP_LOG_PATH", "logs/startup.log")

    _logger, startup_log_path = run._configure_startup_logging()

    assert startup_log_path == str((tmp_path / "logs" / "startup.log").resolve())

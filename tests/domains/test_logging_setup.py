"""foms.platform.logging_setup 계약 테스트 (AUDIT-LOG T1).

configure_logging()의 멱등성·레벨·핸들러 필터 2종(RedactionFilter+RequestIdFilter)·
request_id 주입·FOMS_STARTUP_LOG_PATH 파일 핸들러·dashboard_cache 국소 우회 제거를
고정한다. 캡처는 핸들러 stream 스왑으로 수행한다(pytest capsys와 무관하게 결정적).
"""

from __future__ import annotations

import io
import logging
from typing import Callable

import pytest
from flask import Flask, g

from foms.platform.logging_setup import (
    ROOT_HANDLER_NAME,
    STARTUP_FILE_HANDLER_NAME,
    RequestIdFilter,
    configure_logging,
)
from foms.services.error_logging import RedactionFilter


@pytest.fixture()
def restore_root_logging():
    """테스트 중 root logger에 추가된 핸들러·레벨 변경을 원복한다."""
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    level_before = root.level
    yield root
    for handler in list(root.handlers):
        if handler not in handlers_before:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level_before)


def _root_stream_handler() -> logging.StreamHandler:
    """root에서 foms-root-handler를 찾는다(없으면 테스트 실패)."""
    for handler in logging.getLogger().handlers:
        if handler.name == ROOT_HANDLER_NAME:
            assert isinstance(handler, logging.StreamHandler)
            return handler
    pytest.fail("foms-root-handler not attached to root logger")


def _capture_handler_output(
    handler: logging.StreamHandler, emit: Callable[[], None]
) -> str:
    """핸들러 stream을 임시 StringIO로 스왑해 emit 중 출력만 캡처한다."""
    stream = io.StringIO()
    original = handler.setStream(stream)
    try:
        emit()
    finally:
        handler.setStream(original)
    return stream.getvalue()


def test_configure_logging_sets_info_level_and_is_idempotent(
    restore_root_logging, monkeypatch
):
    """root 유효 레벨 INFO + foms-root-handler 정확히 1개(재호출 no-op)."""
    monkeypatch.delenv("FOMS_STARTUP_LOG_PATH", raising=False)

    configure_logging()
    root = logging.getLogger()

    assert root.getEffectiveLevel() == logging.INFO
    names = [handler.name for handler in root.handlers]
    assert names.count(ROOT_HANDLER_NAME) == 1

    configure_logging()
    names_after = [handler.name for handler in root.handlers]
    assert names_after.count(ROOT_HANDLER_NAME) == 1
    assert len(names_after) == len(names)


def test_root_handler_carries_both_filters(restore_root_logging, monkeypatch):
    """핸들러 레벨에 RedactionFilter + RequestIdFilter 2종이 붙는다."""
    monkeypatch.delenv("FOMS_STARTUP_LOG_PATH", raising=False)
    configure_logging()

    handler = _root_stream_handler()
    filter_types = {type(f) for f in handler.filters}
    assert RedactionFilter in filter_types
    assert RequestIdFilter in filter_types


def test_module_logger_secret_is_masked_in_handler_output(
    restore_root_logging, monkeypatch
):
    """임의 모듈 로거의 password 문자열이 핸들러 출력에서 마스킹된다."""
    monkeypatch.delenv("FOMS_STARTUP_LOG_PATH", raising=False)
    configure_logging()
    handler = _root_stream_handler()

    output = _capture_handler_output(
        handler,
        lambda: logging.getLogger("foms.t1_secret_probe").info(
            "login failed password=hunter2secret for user 7"
        ),
    )

    assert "hunter2secret" not in output
    assert "password=***" in output


def test_request_id_token_uses_flask_g_inside_request_context(
    restore_root_logging, monkeypatch
):
    """요청 컨텍스트 안에서는 g.request_id가 로그 라인에 찍힌다."""
    monkeypatch.delenv("FOMS_STARTUP_LOG_PATH", raising=False)
    configure_logging()
    handler = _root_stream_handler()
    app = Flask(__name__)

    def _emit_inside_request() -> None:
        with app.test_request_context("/t1-probe"):
            g.request_id = "rid-abc123"
            logging.getLogger("foms.t1_rid_probe").info("inside request")

    output = _capture_handler_output(handler, _emit_inside_request)

    assert "[rid-abc123]" in output
    assert "inside request" in output


def test_request_id_token_falls_back_to_dash(restore_root_logging, monkeypatch):
    """요청 컨텍스트 밖·g.request_id 부재 시 '-'로 대체된다."""
    monkeypatch.delenv("FOMS_STARTUP_LOG_PATH", raising=False)
    configure_logging()
    handler = _root_stream_handler()

    outside = _capture_handler_output(
        handler,
        lambda: logging.getLogger("foms.t1_rid_probe").info("outside request"),
    )
    assert "[-]" in outside

    app = Flask(__name__)

    def _emit_without_rid() -> None:
        with app.test_request_context("/t1-probe"):
            logging.getLogger("foms.t1_rid_probe").info("request without rid")

    inside_without_rid = _capture_handler_output(handler, _emit_without_rid)
    assert "[-]" in inside_without_rid


def test_third_party_record_without_request_id_formats_safely(
    restore_root_logging, monkeypatch
):
    """request_id 속성 없는 서드파티 LogRecord도 포맷 예외 없이 출력된다."""
    monkeypatch.delenv("FOMS_STARTUP_LOG_PATH", raising=False)
    configure_logging()
    handler = _root_stream_handler()

    record = logging.LogRecord(
        name="thirdparty.lib",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="third-party says %s",
        args=("hello",),
        exc_info=None,
    )
    assert not hasattr(record, "request_id")

    output = _capture_handler_output(handler, lambda: handler.handle(record))

    assert "third-party says hello" in output
    assert "[-]" in output


def test_startup_file_handler_env_opt_in_is_idempotent(
    restore_root_logging, monkeypatch, tmp_path
):
    """FOMS_STARTUP_LOG_PATH 설정 시 같은 포맷·필터의 파일 핸들러가 1개만 붙는다."""
    log_file = tmp_path / "runtime" / "logs" / "startup.log"
    monkeypatch.setenv("FOMS_STARTUP_LOG_PATH", str(log_file))

    configure_logging()
    configure_logging()

    root = logging.getLogger()
    file_handlers = [
        handler
        for handler in root.handlers
        if handler.name == STARTUP_FILE_HANDLER_NAME
    ]
    assert len(file_handlers) == 1
    assert log_file.parent.is_dir()

    filter_types = {type(f) for f in file_handlers[0].filters}
    assert RedactionFilter in filter_types
    assert RequestIdFilter in filter_types

    logging.getLogger("foms.t1_file_probe").info("file probe line")
    file_handlers[0].flush()
    content = log_file.read_text(encoding="utf-8")
    assert "file probe line" in content
    assert "[-]" in content


def test_dashboard_cache_module_logger_has_no_local_handlers():
    """dashboard_cache의 국소 stderr 우회가 제거됐고 propagate가 원복됐다."""
    import foms.services.common.dashboard_cache as dashboard_cache

    assert dashboard_cache.logger.handlers == []
    assert dashboard_cache.logger.propagate is True
    assert not hasattr(dashboard_cache, "_ensure_dashcache_log_to_stderr")
    assert not hasattr(dashboard_cache, "_lazy_ensure_dashcache_log_to_stderr")

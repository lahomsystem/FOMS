"""REQ-DIAG-01: 모든 요청의 공통 구간 계측 계약.

느린 요청(400ms 초과) 로그와 HTML 응답 헤더에 before_request·컨텍스트 프로세서·렌더·
템플릿 컴파일·SQL·새 DB 연결·CPU·전체 GC 구간이 실린다. 진단 전용이다 — 값이 응답 본문이나
권한 판정에 쓰이지 않는다. 각 칸은 "늘어야 할 때 늘고(양성), 안 늘어야 할 때 그대로(음성)"
두 쪽을 함께 본다.
"""

from __future__ import annotations

import gc
import logging
import re
import time
import weakref

from flask import Response, g, render_template_string
from sqlalchemy import text

from db import db_session, engine
from foms.services.common.request_phase_profile import (
    HEADER_REQ_DIAG,
    format_request_diag,
    install_request_phase_profile,
)

_DIAG_RE = re.compile(
    r"^pre=(\d+);ctx=(\d+)/(\d+);tpl=(\d+)/(\d+);cmp=(\d+)/(\d+);sql=(\d+)/(\d+)"
    r";sqlr=(\d+)/(\d+);acq=(\d+)/(\d+);conn=(\d+);cpu=(\d+);gc2=(\d+)/(\d+)$"
)


def _parse(diag: str) -> dict[str, int]:
    m = _DIAG_RE.match(diag)
    assert m, f"진단 한 줄 모양이 다르다: {diag!r}"
    keys = ("pre", "ctx", "ctx_n", "tpl", "tpl_n", "cmp", "cmp_n", "sql", "sql_n",
            "sqlr", "sqlr_n", "acq", "acq_n", "conn", "cpu", "gc2", "gc2_ms")
    return dict(zip(keys, (int(v) for v in m.groups())))


def test_html_page_carries_diag_header_with_render_and_sql(auth_client) -> None:
    """실제 HTML 화면(주문 목록)은 헤더에 렌더·컨텍스트 프로세서·SQL 칸을 싣는다."""
    resp = auth_client.get("/")
    assert resp.status_code == 200
    assert resp.mimetype == "text/html"
    diag = _parse(resp.headers[HEADER_REQ_DIAG])
    assert diag["tpl_n"] >= 1, diag
    assert diag["ctx_n"] >= 1, diag
    assert diag["sql_n"] >= 1, diag


def test_json_response_has_no_diag_header(auth_client) -> None:
    """음성 대조군: JSON 응답에는 헤더를 붙이지 않는다(폴링 응답 크기를 늘리지 않는다)."""
    resp = auth_client.get("/erp/api/notifications/badge")
    assert resp.status_code == 200
    assert resp.mimetype == "application/json"
    assert HEADER_REQ_DIAG not in resp.headers


def test_format_outside_request_is_empty() -> None:
    """요청 밖에서는 빈 문자열(예외 없음)."""
    assert format_request_diag() == ""


def test_template_compile_counted_only_on_cache_miss(app) -> None:
    """Jinja 캐시 미스(컴파일)만 cmp 로 센다 — 같은 템플릿 두 번째는 늘지 않는다(음성)."""
    env = app.jinja_env
    name = "orders/gnav_swap_shell.html"
    try:
        del env.cache[(weakref.ref(env.loader), name)]
    except (KeyError, TypeError):
        pass
    with app.test_request_context("/"):
        app.preprocess_request()
        env.get_template(name)
        first = _parse(format_request_diag())
        env.get_template(name)
        second = _parse(format_request_diag())
    assert first["cmp_n"] == 1, first
    assert second["cmp_n"] == 1, second


def test_sql_statements_counted_in_request(app) -> None:
    """SQL 한 문장마다 sql_n 이 1 늘고, 실행하지 않으면 그대로다(음성)."""
    with app.test_request_context("/"):
        app.preprocess_request()
        before = _parse(format_request_diag())["sql_n"]
        idle = _parse(format_request_diag())["sql_n"]
        db_session.execute(text("SELECT 1"))
        after = _parse(format_request_diag())["sql_n"]
    assert idle == before
    assert after == before + 1


def test_sql_inside_render_is_split_out(app) -> None:
    """렌더 도중 실행된 SQL(지연 로딩 등)만 sqlr 로 따로 센다. 렌더 밖 SQL 은 sqlr 에 안 든다(음성)."""

    def _query_in_template() -> str:
        db_session.execute(text("SELECT 1"))
        return ""

    with app.test_request_context("/"):
        app.preprocess_request()
        db_session.execute(text("SELECT 1"))
        outside = _parse(format_request_diag())
        render_template_string("{{ q() }}", q=_query_in_template)
        inside = _parse(format_request_diag())
    assert outside["sqlr_n"] == 0, outside
    assert inside["sqlr_n"] == 1, inside
    assert inside["sql_n"] == outside["sql_n"] + 1


def test_connection_acquire_counted(app) -> None:
    """풀에서 연결을 꺼낼 때마다 acq 가 는다. 꺼내지 않으면 그대로다(음성)."""
    with app.test_request_context("/"):
        app.preprocess_request()
        before = _parse(format_request_diag())["acq_n"]
        idle = _parse(format_request_diag())["acq_n"]
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        after = _parse(format_request_diag())["acq_n"]
    assert idle == before
    assert after == before + 1


def test_full_gc_counted_but_young_gc_is_not(app) -> None:
    """전체(2세대) GC 는 gc2 로 세고, 0세대 GC 는 세지 않는다(음성)."""
    with app.test_request_context("/"):
        app.preprocess_request()
        gc.collect(0)
        young = _parse(format_request_diag())["gc2"]
        gc.collect()
        full = _parse(format_request_diag())["gc2"]
    assert young == 0
    assert full >= 1


def test_render_counts_outer_render_once(app) -> None:
    """render_template 계열 렌더 1회 = tpl_n 1, ctx_n 1. 렌더가 없으면 둘 다 0(음성)."""
    with app.test_request_context("/"):
        app.preprocess_request()
        idle = _parse(format_request_diag())
        render_template_string("{{ 1 + 1 }}")
        once = _parse(format_request_diag())
    assert (idle["tpl_n"], idle["ctx_n"]) == (0, 0)
    assert (once["tpl_n"], once["ctx_n"]) == (1, 1)


def test_slow_request_log_line_keeps_prefix_and_adds_diag(app, caplog) -> None:
    """400ms 넘는 요청 로그는 기존 세 칸(endpoint·duration_ms·status)을 그대로 앞에 두고
    diag·phases 를 뒤에 붙인다. 400ms 이하는 찍지 않는다(음성)."""
    caplog.set_level(logging.INFO)
    with app.test_request_context("/"):
        app.preprocess_request()
        g._request_start = time.perf_counter()
        app.process_response(Response("ok", mimetype="text/html"))
        fast_lines = [r.getMessage() for r in caplog.records if "req_duration" in r.getMessage()]
        g._request_start = time.perf_counter() - 1.0
        resp = app.process_response(Response("ok", mimetype="text/html"))
    lines = [r.getMessage() for r in caplog.records if "req_duration" in r.getMessage()]
    assert fast_lines == []
    assert len(lines) == 1
    m = re.match(r"req_duration endpoint=(\S+) duration_ms=(\d+) status=(\d+) diag=(\S+) phases=(\S+)$",
                 lines[0])
    assert m, lines[0]
    assert int(m.group(2)) >= 1000
    _parse(m.group(4))
    assert HEADER_REQ_DIAG in resp.headers


def test_install_is_idempotent(app) -> None:
    """두 번 배선해도 감싸기가 겹치지 않는다 — before_request 시간이 두 번 더해지지 않는다."""
    wrapped = app.preprocess_request
    install_request_phase_profile(app)
    assert app.preprocess_request is wrapped

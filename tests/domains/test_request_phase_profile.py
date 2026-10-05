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

from flask import Flask, Response, g, render_template_string
from sqlalchemy import text

from db import db_session, engine
from foms.services.common.request_phase_profile import (
    HEADER_REQ_DIAG,
    format_request_diag,
    install_request_phase_profile,
)

# 앞 열 칸은 모양이 고정이고, 끝의 ``;ctxp=…`` 는 5ms 넘은 프로세서가 있을 때만 붙는다.
_DIAG_RE = re.compile(
    r"^pre=(\d+);ctx=(\d+)/(\d+);tpl=(\d+)/(\d+);cmp=(\d+)/(\d+);sql=(\d+)/(\d+)"
    r";sqlr=(\d+)/(\d+);acq=(\d+)/(\d+);conn=(\d+);cpu=(\d+);gc2=(\d+)/(\d+)"
    r"(?:;ctxp=([A-Za-z0-9_.#-]+:\d+/\d+(?:,[A-Za-z0-9_.#-]+:\d+/\d+)*))?$"
)
_DIAG_KEYS = ("pre", "ctx", "ctx_n", "tpl", "tpl_n", "cmp", "cmp_n", "sql", "sql_n",
              "sqlr", "sqlr_n", "acq", "acq_n", "conn", "cpu", "gc2", "gc2_ms")


def _parse(diag: str) -> dict[str, int]:
    m = _DIAG_RE.match(diag)
    assert m, f"진단 한 줄 모양이 다르다: {diag!r}"
    return dict(zip(_DIAG_KEYS, (int(v) for v in m.groups()[: len(_DIAG_KEYS)])))


def _parse_ctxp(diag: str) -> dict[str, tuple[int, int]]:
    """``ctxp`` 꼬리 → {이름: (ms, sqlms)}. 꼬리가 없으면 빈 딕셔너리."""
    m = _DIAG_RE.match(diag)
    assert m, f"진단 한 줄 모양이 다르다: {diag!r}"
    tail = m.group(len(_DIAG_KEYS) + 1)
    out: dict[str, tuple[int, int]] = {}
    for part in (tail.split(",") if tail else []):
        label, _, nums = part.partition(":")
        ms, _, sql_ms = nums.partition("/")
        out[label] = (int(ms), int(sql_ms))
    return out


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


# --- ctxp: 컨텍스트 프로세서 하나하나 (원장 P3-1) ------------------------------------
#
# 운영 아침 피크의 느린 HTML 은 ``ctx``(프로세서 전체 합) 안에서 SQL 을 650ms 기다렸는데,
# 어느 프로세서인지 이름을 댈 수 없었다. ``ctxp`` 는 5ms 넘은 프로세서를 이름·시간·그 안
# SQL 시간으로 적는다. 아래는 앱 상태를 더럽히지 않게 작은 Flask 앱으로 검증하고, 마지막
# 하나만 실제 앱 화면에서 헤더 한 줄을 확인한다.

_SLOW_SQL = text(
    "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 200000) "
    "SELECT count(*) FROM c"
)


def _label_ending(ctxp: dict[str, tuple[int, int]], suffix: str) -> str:
    hits = [name for name in ctxp if name.endswith(suffix)]
    assert len(hits) == 1, (suffix, ctxp)
    return hits[0]


def test_ctxp_names_slow_processor_even_if_registered_after_install() -> None:
    """배선 **뒤에** 등록한 프로세서도 이름이 나온다. 5ms 미만 프로세서는 안 나온다(음성).
    프로세서가 돌려주는 값은 그대로이고, 두 번째 렌더에서 다시 감싸지 않는다."""
    mini = Flask("req_diag_ctxp_late")

    def early_slow() -> dict[str, int]:
        time.sleep(0.02)
        return {"early": 1}

    def early_fast() -> dict[str, int]:
        return {"fast": 2}

    mini.context_processor(early_slow)
    mini.context_processor(early_fast)
    install_request_phase_profile(mini, engine=engine)

    def late_slow() -> dict[str, int]:
        time.sleep(0.04)
        return {"late": 3}

    mini.context_processor(late_slow)  # install 뒤 등록
    with mini.test_request_context("/"):
        mini.preprocess_request()
        out = render_template_string("{{ early }}{{ fast }}{{ late }}")
        wrapped_once = list(mini.template_context_processors[None])
        render_template_string("{{ late }}")
        wrapped_twice = list(mini.template_context_processors[None])
        diag = format_request_diag()
    assert out == "123"
    assert all(a is b for a, b in zip(wrapped_once, wrapped_twice, strict=True))
    ctxp = _parse_ctxp(diag)
    late = _label_ending(ctxp, ".late_slow")
    early = _label_ending(ctxp, ".early_slow")
    assert ctxp[late][0] >= 70, ctxp  # 렌더 2회 × 40ms 가 같은 이름에 합쳐진다
    assert 15 <= ctxp[early][0] < ctxp[late][0], ctxp
    assert ctxp[late][1] == 0 and ctxp[early][1] == 0, ctxp  # SQL 없음
    assert list(ctxp)[0] == late  # 오래 걸린 순
    assert not any(name.endswith("early_fast") for name in ctxp), ctxp
    assert not any("_default_template_ctx_processor" in name for name in ctxp), ctxp


def test_ctxp_attributes_sql_wait_to_the_processor_that_ran_it() -> None:
    """프로세서 안에서 실행된 SQL 시간은 그 프로세서 몫으로만 적힌다. 같은 렌더의 다른
    느린 프로세서(잠만 잔다)는 SQL 0 이다(음성)."""
    mini = Flask("req_diag_ctxp_sql")

    def heavy_sql() -> dict[str, int]:
        return {"n": db_session.execute(_SLOW_SQL).scalar()}

    def sleepy() -> dict[str, int]:
        time.sleep(0.02)
        return {}

    mini.context_processor(heavy_sql)
    mini.context_processor(sleepy)
    install_request_phase_profile(mini, engine=engine)
    with mini.test_request_context("/"):
        mini.preprocess_request()
        out = render_template_string("{{ n }}")
        diag = format_request_diag()
    assert out == "200000"
    ctxp = _parse_ctxp(diag)
    sql_proc = _label_ending(ctxp, ".heavy_sql")
    sleep_proc = _label_ending(ctxp, ".sleepy")
    ms, sql_ms = ctxp[sql_proc]
    assert sql_ms >= 5, ctxp
    assert sql_ms <= ms + 1, ctxp  # 프로세서 시간 안의 몫
    assert ctxp[sleep_proc][1] == 0, ctxp
    # 프로세서 안 SQL 은 렌더 밖(update_template_context)이라 sqlr 에 들지 않는다.
    assert _parse(diag)["sqlr_n"] == 0, diag


def test_ctxp_absent_when_every_processor_is_fast() -> None:
    """음성 대조군: 5ms 넘는 프로세서가 없으면 ``ctxp`` 칸을 붙이지 않는다 — 기존 열 칸 모양 그대로."""
    mini = Flask("req_diag_ctxp_fast")
    mini.context_processor(lambda: {"a": 1})
    install_request_phase_profile(mini, engine=engine)
    with mini.test_request_context("/"):
        mini.preprocess_request()
        render_template_string("{{ a }}")
        diag = format_request_diag()
    assert ";ctxp=" not in diag, diag
    assert _parse(diag)["ctx_n"] == 1
    assert _parse_ctxp(diag) == {}


def test_ctxp_covers_blueprint_processors_only_of_the_blueprint_that_rendered() -> None:
    """블루프린트 프로세서도 ``블루프린트이름.함수`` 로 나온다. 다른 블루프린트의 느린
    프로세서는 이 요청에서 안 돌았으므로 나오지 않는다(음성)."""
    from flask import Blueprint

    mini = Flask("req_diag_ctxp_bp")
    bp_diag = Blueprint("bp_diag", __name__)
    bp_other = Blueprint("bp_other", __name__)

    @bp_diag.context_processor
    def bp_slow() -> dict[str, int]:
        time.sleep(0.02)
        return {"v": 7}

    @bp_other.context_processor
    def other_slow() -> dict[str, int]:
        time.sleep(0.02)
        return {"v": 8}

    @bp_diag.route("/diag")
    def diag_view() -> str:
        body = render_template_string("{{ v }}")
        return f"{body}|{format_request_diag()}"

    mini.register_blueprint(bp_diag)
    mini.register_blueprint(bp_other)
    install_request_phase_profile(mini, engine=engine)
    body, _, diag = mini.test_client().get("/diag").get_data(as_text=True).partition("|")
    assert body == "7"
    ctxp = _parse_ctxp(diag)
    name = _label_ending(ctxp, ".bp_slow")
    assert name.startswith("bp_diag."), ctxp
    assert ctxp[name][0] >= 15, ctxp
    assert not any("other_slow" in n for n in ctxp), ctxp


def test_ctxp_does_not_swallow_processor_errors() -> None:
    """감싼 뒤에도 프로세서 예외는 그대로 올라간다(계측이 오류를 삼키지 않는다)."""
    mini = Flask("req_diag_ctxp_err")

    def broken() -> dict[str, int]:
        raise ValueError("boom")

    mini.context_processor(broken)
    install_request_phase_profile(mini, engine=engine)
    with mini.test_request_context("/"):
        mini.preprocess_request()
        try:
            render_template_string("x")
        except ValueError as exc:
            assert str(exc) == "boom"
        else:  # pragma: no cover - 실패 경로
            raise AssertionError("프로세서 예외가 사라졌다")


def test_real_html_page_diag_header_names_slow_processor(app, auth_client) -> None:
    """실제 앱 화면에서 늦게 등록한 느린 프로세서가 헤더 ``ctxp`` 맨 앞에 이름으로 나온다."""

    def p31_probe_slow() -> dict[str, int]:
        time.sleep(0.03)
        return {}

    # 첫 요청 뒤라 ``app.context_processor`` 는 막혀 있다 — 목록에 직접 넣는다(배선 뒤 추가와 같다).
    app.template_context_processors[None].append(p31_probe_slow)
    try:
        resp = auth_client.get("/")
    finally:
        procs = app.template_context_processors[None]
        procs[:] = [
            f for f in procs
            if f is not p31_probe_slow and getattr(f, "__wrapped__", None) is not p31_probe_slow
        ]
    assert resp.status_code == 200
    diag = resp.headers[HEADER_REQ_DIAG]
    print(f"\nsample X-FOMS-REQ-DIAG: {diag}")
    ctxp = _parse_ctxp(diag)
    probe = _label_ending(ctxp, ".p31_probe_slow")
    assert ctxp[probe][0] >= 25, ctxp
    assert ctxp[probe][1] == 0, ctxp
    assert _parse(diag)["ctx"] >= ctxp[probe][0], diag

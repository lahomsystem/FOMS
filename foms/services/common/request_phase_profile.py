"""REQ-DIAG-01: 모든 요청의 공통 구간을 재서 느린 요청 로그에 함께 남긴다(진단 전용).

왜 필요한가: 2026-09-09(KST)부터 HTML 화면에만 느린 꼬리가 생겼다. 운영 HTTP 로그 실측
(원장 P3-1) — 업무시간 HTML 10개 경로의 700ms 초과 비율이 09-01~09-08 0.8~1.8% 에서
09-09 8.5%, 09-10 11.1%, 09-11 13.3% 로 계단을 올랐고 10-01 까지 9~14% 로 남았다. 같은
기간 JSON API 는 그대로였다. EPT-B7 ``render_ms``(``render_template`` 한 덩어리)도
같은 날 올랐는데(생산 탭 500ms 이상 2% → 11%), 늘어난 몫은 기존 구간 표시 어디에도
잡히지 않았다. 응답 크기·인스턴스 나이·배포 콜드와는 무관했다.

그래서 **모든 요청**에 공통으로 끼는 구간을 잰다. 화면마다 구간 표시를 심는 대신 Flask
가 모든 화면에서 반드시 지나는 자리를 감싼다.

====  =============================================================  ===========
키    무엇                                                            단위
====  =============================================================  ===========
pre   before_request 전체(``preprocess_request``)                     ms
ctx   컨텍스트 프로세서 전체(``update_template_context``) / 호출 수      ms/회
tpl   템플릿 렌더(가장 바깥 ``render_template`` 의 render) / 렌더 수     ms/회
cmp   템플릿 컴파일(Jinja 캐시 미스 ``loader.load``) / 횟수             ms/회
sql   SQL 실행(cursor execute) / 문장 수                               ms/회
sqlr  그중 템플릿 렌더 도중 실행된 몫(지연 로딩 등) / 문장 수             ms/회
acq   DB 연결 얻기(풀 checkout·pre-ping·새 연결 포함) / 횟수            ms/회
conn  이 요청 동안 새로 만든 DB 연결 수                                  회
cpu   요청 동안 프로세스 CPU 시간(다른 greenlet 몫 포함)                 ms
gc2   요청 동안 일어난 전체(2세대) GC / 그 시간                         회/ms
ctxp  컨텍스트 프로세서 **하나하나**의 시간 / 그 안에서 기다린 SQL        이름:ms/ms,…
====  =============================================================  ===========

``ctxp`` 는 맨 끝에 붙는 선택 칸이다 — 이 요청에서 합계 5ms 이상 걸린 프로세서만 오래 걸린
순서로 적고(``ctxp=inject_status_list:612/598,inject_menu:7/6``), 그런 프로세서가 없으면 칸
자체를 붙이지 않는다(앞 열 칸의 모양은 그대로). 2026-10-02 운영 diag 판정에서 아침 피크의
느린 HTML 은 ``ctx`` 안에서 SQL 을 650ms 기다렸는데, ``ctx`` 는 프로세서 전체 합이라 어느
것인지 이름을 댈 수 없었다(원장 P3-1). 이름은 함수 ``__qualname__`` 에서 ``<locals>`` 를 뺀
것이고(람다는 ``register_write_guard.lambda`` 처럼 등록한 함수 이름), 블루프린트 몫은 앞에
블루프린트 이름이 붙는다. ``naver_triage_pending`` 같은 지연 값(LazyBadgeCount)은 렌더 도중
계산되므로 ``ctxp`` 가 아니라 ``sqlr``·``tpl`` 쪽에 잡힌다 — 계측이 값을 미리 계산시키지 않는다.

읽는 법: ``wall`` 이 큰데 ``cpu`` 가 작으면 무언가를 **기다린** 것이다 — ``sql`` 이 그 몫을
덮으면 DB(렌더 안이면 ``sqlr``), ``acq`` 가 크면 풀 고갈·연결 생성, 셋 다 아니면 Redis·외부
호출·잠금 대기다.
``cpu`` 가 ``wall`` 에 가까우면 계산이고, ``tpl``·``cmp``·``gc2`` 가 그 안에서 몫을 가른다.

오버헤드: 요청당 ``perf_counter``·``process_time`` 몇 번과 SQL 문장마다 두 번, 컨텍스트
프로세서 호출마다 두 번(렌더 1회에 약 10개). 렌더 결과나 권한 판정에는 절대 쓰지 않는다.
계측이 실패해도 요청은 그대로 간다(예외는 debug 로그만).
"""

from __future__ import annotations

import functools
import gc
import inspect
import logging
import re
import time
from typing import Any, Callable, Final

from flask import (
    Flask,
    before_render_template,
    g,
    has_request_context,
    request,
    template_rendered,
)
from sqlalchemy import event

logger = logging.getLogger(__name__)

__all__ = [
    "CTXP_MIN_MS",
    "HEADER_REQ_DIAG",
    "format_request_diag",
    "install_request_phase_profile",
]

#: HTML 응답에 붙는 진단 헤더(값은 :func:`format_request_diag` 한 줄). 스테이징에서 로그 없이
#: 읽기 위한 것이다 — EPT-B7 헤더와 같은 성격(진단 전용, 권한 판정 금지).
HEADER_REQ_DIAG: Final[str] = "X-FOMS-REQ-DIAG"

_G_KEY: Final[str] = "_foms_req_diag"
_INSTALLED_ATTR: Final[str] = "_foms_req_diag_installed"

#: ``ctxp`` 칸에 올리는 최소 합계 시간(ms). 이보다 짧은 프로세서는 줄을 길게 할 뿐이다.
CTXP_MIN_MS: Final[float] = 5.0
#: 감싼 프로세서에 붙이는 표식(값 = 이름). 이미 감싼 것을 다시 감싸지 않는 데 쓴다.
_CTXP_LABEL_ATTR: Final[str] = "_foms_req_diag_ctxp_label"
#: 앱별 이름 → 감싼 원래 함수. 이름이 겹치면 뒤에 ``#2`` 를 붙여 몫이 섞이지 않게 한다.
_CTXP_LABELS_ATTR: Final[str] = "_foms_req_diag_ctxp_labels"
#: 로그 한 줄의 칸 구분자(``;`` ``,`` ``:`` ``/`` 공백)와 겹치지 않는 글자만 이름에 남긴다.
_CTXP_UNSAFE_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9_.#-]")

#: 프로세스 전체 GC(2세대) 누적. 요청은 시작·끝 값의 차이만 본다(다른 greenlet 이 일으킨
#: GC 라도 이 요청을 멈춰 세웠다면 이 요청의 몫이다).
_GC_FULL: dict[str, float] = {"n": 0, "ms": 0.0, "t0": 0.0}
_gc_hooked = False
_sql_hooked_engines: set[int] = set()


def _diag() -> dict[str, Any] | None:
    """현재 요청의 누적 칸(없으면 ``None``). 요청 밖에서는 늘 ``None``."""
    if not has_request_context():
        return None
    return getattr(g, _G_KEY, None)


def _add(key: str, ms: float, count_key: str | None = None) -> None:
    """현재 요청 누적 칸에 ms 를 더한다(요청 밖이면 무시)."""
    d = _diag()
    if d is None:
        return
    d[key] = d.get(key, 0.0) + ms
    if count_key:
        d[count_key] = d.get(count_key, 0) + 1


def _start_request_diag() -> None:
    """요청 시작 기준점을 심는다(``preprocess_request`` 직전)."""
    setattr(g, _G_KEY, {
        "_cpu0": time.process_time(),
        "_gc_n0": _GC_FULL["n"],
        "_gc_ms0": _GC_FULL["ms"],
        "_tpl_stack": [],
    })


def format_request_diag() -> str:
    """현재 요청의 공통 구간을 한 줄로 만든다(로그·헤더 겸용).

    Returns:
        ``pre=3;ctx=1/2;tpl=640/1;cmp=0/0;sql=35/14;sqlr=0/0;acq=1/2;conn=0;cpu=120;gc2=0/0``
        형태. 5ms 이상 걸린 컨텍스트 프로세서가 있으면 끝에
        ``;ctxp=inject_status_list:612/598,inject_menu:7/6`` 이 붙는다(없으면 붙지 않는다).
        요청 밖이거나 기준점이 없으면 빈 문자열.
    """
    try:
        d = _diag()
        if d is None:
            return ""
        cpu_ms = (time.process_time() - d["_cpu0"]) * 1000.0
        gc_n = int(_GC_FULL["n"] - d["_gc_n0"])
        gc_ms = _GC_FULL["ms"] - d["_gc_ms0"]
        return (
            f"pre={d.get('pre', 0.0):.0f}"
            f";ctx={d.get('ctx', 0.0):.0f}/{d.get('ctx_n', 0)}"
            f";tpl={d.get('tpl', 0.0):.0f}/{d.get('tpl_n', 0)}"
            f";cmp={d.get('cmp', 0.0):.0f}/{d.get('cmp_n', 0)}"
            f";sql={d.get('sql', 0.0):.0f}/{d.get('sql_n', 0)}"
            f";sqlr={d.get('sqlr', 0.0):.0f}/{d.get('sqlr_n', 0)}"
            f";acq={d.get('acq', 0.0):.0f}/{d.get('acq_n', 0)}"
            f";conn={d.get('conn_n', 0)}"
            f";cpu={cpu_ms:.0f}"
            f";gc2={gc_n}/{gc_ms:.0f}"
        ) + _format_ctxp(d)
    except Exception:  # noqa: BLE001 - 진단 실패가 응답을 깨선 안 된다
        logger.debug("[REQ-DIAG] format skipped", exc_info=True)
        return ""


def _format_ctxp(d: dict[str, Any]) -> str:
    """``;ctxp=이름:ms/sqlms,…`` 꼬리(5ms 이상만, 오래 걸린 순). 해당 없으면 빈 문자열."""
    slots = d.get("_ctxp")
    if not slots:
        return ""
    slow = sorted(
        ((label, ms, sql_ms) for label, (ms, sql_ms) in slots.items() if ms >= CTXP_MIN_MS),
        key=lambda item: item[1],
        reverse=True,
    )
    if not slow:
        return ""
    return ";ctxp=" + ",".join(f"{label}:{ms:.0f}/{sql_ms:.0f}" for label, ms, sql_ms in slow)


# --- 컨텍스트 프로세서 하나하나 -------------------------------------------------


def _ctxp_label(key: str | None, func: Callable[..., Any]) -> str:
    """프로세서의 안정된 이름(로그 칸 구분자와 겹치는 글자는 ``_``)."""
    raw = (
        getattr(func, "__qualname__", None)
        or getattr(func, "__name__", None)
        or type(func).__name__
    )
    label = str(raw).replace(".<locals>", "").replace("<lambda>", "lambda")
    if key is not None:
        label = f"{key}.{label}"
    return _CTXP_UNSAFE_RE.sub("_", label) or "anon"


def _record_ctxp(d: dict[str, Any], label: str, ms: float, sql_ms: float) -> None:
    slots = d.get("_ctxp")
    if slots is None:
        slots = d["_ctxp"] = {}
    slot = slots.get(label)
    if slot is None:
        slots[label] = [ms, sql_ms]
    else:
        slot[0] += ms
        slot[1] += sql_ms


def _timed_context_processor(func: Callable[..., Any], label: str) -> Callable[..., Any]:
    """프로세서 하나를 감싼다 — 돌려주는 값은 손대지 않고 앞뒤 시각과 SQL 누적만 본다."""

    def _timed(*args: Any, **kwargs: Any) -> Any:
        d = _diag()
        if d is None:
            return func(*args, **kwargs)
        t0 = time.perf_counter()
        sql0 = d.get("sql", 0.0)
        try:
            return func(*args, **kwargs)
        finally:
            try:
                _record_ctxp(
                    d, label, (time.perf_counter() - t0) * 1000.0, d.get("sql", 0.0) - sql0
                )
            except Exception:  # noqa: BLE001 - 계측이 프로세서 결과를 바꾸면 안 된다
                logger.debug("[REQ-DIAG] ctxp record skipped", exc_info=True)

    functools.update_wrapper(_timed, func)
    setattr(_timed, _CTXP_LABEL_ATTR, label)
    return _timed


def _wrap_context_processors(app: Flask, keys: Any = None) -> None:
    """``app.template_context_processors`` 를 감싼다(``keys`` 가 없으면 앱·블루프린트 **모든 키**).

    배선 뒤에 등록된 프로세서도 잡도록 :func:`install_request_phase_profile` 끝(모든 키)과 매
    렌더의 ``update_template_context`` 앞(그 렌더가 실제로 부를 키 — 앱 + 현재 요청의
    블루프린트들)에서 부른다. 이미 감싼 것은 표식으로 건너뛰므로 두 번째부터는 프로세서 수만큼의
    속성 조회뿐이다. 코루틴 프로세서는 감싸지 않는다(동기 래퍼가 ``ensure_sync`` 판정을 바꾼다).
    """
    labels: dict[str, Any] | None = app.__dict__.get(_CTXP_LABELS_ATTR)
    if labels is None:
        labels = {}
        setattr(app, _CTXP_LABELS_ATTR, labels)
    registry = app.template_context_processors
    if keys is None:
        pairs = list(registry.items())
    else:
        # ``in`` 으로만 본다 — defaultdict 에 빈 키를 만들지 않는다(Flask 와 같은 방식).
        pairs = [(key, registry[key]) for key in keys if key in registry]
    for key, funcs in pairs:
        for index, func in enumerate(funcs):
            if getattr(func, _CTXP_LABEL_ATTR, None) is not None:
                continue
            if inspect.iscoroutinefunction(func):
                continue
            base = _ctxp_label(key, func)
            label = base
            suffix = 2
            while label in labels and labels[label] is not func:
                label = f"{base}#{suffix}"
                suffix += 1
            labels[label] = func
            funcs[index] = _timed_context_processor(func, label)


# --- 훅 ---------------------------------------------------------------------


def _gc_callback(phase: str, info: dict[str, Any]) -> None:
    """전체(2세대) GC 의 횟수·시간만 누적한다(0·1세대는 짧고 잦아 건너뛴다)."""
    if info.get("generation") != 2:
        return
    if phase == "start":
        _GC_FULL["t0"] = time.perf_counter()
    elif phase == "stop" and _GC_FULL["t0"]:
        _GC_FULL["ms"] += (time.perf_counter() - _GC_FULL["t0"]) * 1000.0
        _GC_FULL["n"] += 1
        _GC_FULL["t0"] = 0.0


def _on_before_render(sender: Any, template: Any = None, context: Any = None, **_: Any) -> None:
    d = _diag()
    if d is not None:
        d["_tpl_stack"].append(time.perf_counter())


def _on_rendered(sender: Any, template: Any = None, context: Any = None, **_: Any) -> None:
    d = _diag()
    if d is None or not d["_tpl_stack"]:
        return
    t0 = d["_tpl_stack"].pop()
    d["tpl_n"] = d.get("tpl_n", 0) + 1
    if not d["_tpl_stack"]:
        # 가장 바깥 렌더만 시간에 더한다 — 렌더 안에서 다시 렌더하면 두 번 세지 않게.
        d["tpl"] = d.get("tpl", 0.0) + (time.perf_counter() - t0) * 1000.0


def _hook_sql(engine: Any) -> None:
    """SQL 실행 시간·문장 수와 새 연결 수를 요청에 누적한다(엔진당 1회)."""
    if engine is None or id(engine) in _sql_hooked_engines:
        return

    def _before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if context is not None:
            context._foms_req_diag_t0 = time.perf_counter()

    def _after(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        t0 = getattr(context, "_foms_req_diag_t0", None) if context is not None else None
        d = _diag() if t0 is not None else None
        if d is None:
            return
        ms = (time.perf_counter() - t0) * 1000.0
        d["sql"] = d.get("sql", 0.0) + ms
        d["sql_n"] = d.get("sql_n", 0) + 1
        if d["_tpl_stack"]:
            d["sqlr"] = d.get("sqlr", 0.0) + ms
            d["sqlr_n"] = d.get("sqlr_n", 0) + 1

    def _on_connect(dbapi_connection, connection_record):  # noqa: ANN001
        d = _diag()
        if d is not None:
            d["conn_n"] = d.get("conn_n", 0) + 1

    original_raw_connection = engine.raw_connection

    def _timed_raw_connection(*args: Any, **kwargs: Any) -> Any:
        # Connection 하나를 열 때마다 풀에서 꺼낸다 — 풀이 바닥이면 여기서 기다린다.
        t0 = time.perf_counter()
        try:
            return original_raw_connection(*args, **kwargs)
        finally:
            _add("acq", (time.perf_counter() - t0) * 1000.0, "acq_n")

    event.listen(engine, "before_cursor_execute", _before)
    event.listen(engine, "after_cursor_execute", _after)
    event.listen(engine, "connect", _on_connect)
    engine.raw_connection = _timed_raw_connection
    _sql_hooked_engines.add(id(engine))


def install_request_phase_profile(app: Flask, *, engine: Any = None) -> None:
    """앱에 공통 구간 계측을 1회 배선한다(app_factory 에서 호출).

    감싸는 자리는 Flask·Jinja 가 **모든 화면에서 반드시 지나는 곳**뿐이다 — 동작은 그대로
    두고 앞뒤 시각만 잰다.

    Args:
        app: 대상 Flask 앱.
        engine: SQL 을 잴 SQLAlchemy engine(없으면 SQL·연결 칸은 0).
    """
    global _gc_hooked
    if getattr(app, _INSTALLED_ATTR, False):
        return

    original_preprocess = app.preprocess_request

    def _timed_preprocess_request() -> Any:
        try:
            _start_request_diag()
        except Exception:  # noqa: BLE001
            logger.debug("[REQ-DIAG] start skipped", exc_info=True)
        t0 = time.perf_counter()
        try:
            return original_preprocess()
        finally:
            _add("pre", (time.perf_counter() - t0) * 1000.0)

    original_update_ctx = app.update_template_context

    def _timed_update_template_context(context: dict[str, Any]) -> None:
        t0 = time.perf_counter()
        try:
            # 배선 뒤에 등록된 프로세서도 ctxp 로 이름이 나오게(이미 감싼 것은 건너뛴다).
            # Flask 가 이번 렌더에 부를 키만 본다: 앱(None) + 현재 요청의 블루프린트들.
            keys: tuple[Any, ...] = (None,)
            if has_request_context():
                keys = (None, *request.blueprints)
            _wrap_context_processors(app, keys)
        except Exception:  # noqa: BLE001
            logger.debug("[REQ-DIAG] ctxp wrap skipped", exc_info=True)
        try:
            original_update_ctx(context)
        finally:
            _add("ctx", (time.perf_counter() - t0) * 1000.0, "ctx_n")

    loader = app.jinja_env.loader
    if loader is not None:
        original_load = loader.load

        def _timed_load(environment: Any, name: str, globals: Any = None) -> Any:  # noqa: A002
            # Jinja 는 캐시 미스에서만 loader.load 를 부른다 — 여기 시간 = 읽기+컴파일.
            t0 = time.perf_counter()
            try:
                return original_load(environment, name, globals)
            finally:
                _add("cmp", (time.perf_counter() - t0) * 1000.0, "cmp_n")

        loader.load = _timed_load  # type: ignore[method-assign]

    app.preprocess_request = _timed_preprocess_request  # type: ignore[method-assign]
    app.update_template_context = _timed_update_template_context  # type: ignore[method-assign]
    before_render_template.connect(_on_before_render, app, weak=False)
    template_rendered.connect(_on_rendered, app, weak=False)
    _hook_sql(engine)
    try:
        _wrap_context_processors(app)
    except Exception:  # noqa: BLE001
        logger.debug("[REQ-DIAG] ctxp wrap skipped", exc_info=True)
    if not _gc_hooked:
        gc.callbacks.append(_gc_callback)
        _gc_hooked = True
    setattr(app, _INSTALLED_ATTR, True)

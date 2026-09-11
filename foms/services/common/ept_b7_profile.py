"""EPT-B7: optional server timing headers for template render (profiling; not a cache).

``render_ms`` 는 템플릿 렌더만 담는다. 그래서 "렌더는 30ms 인데 응답은 250ms" 같은 상황에서
나머지 시간이 어디로 갔는지(목록 쿼리·행 조립·payload 부착) 알 수 없었고, 최적화 대상 선정이
추정에 의존했다. ``phase`` 계측은 그 공백을 메운다 — 라우트가 구간을 직접 표시하면
응답 헤더로 나와 스테이징에서 바로 읽을 수 있다(로그 접근 권한과 무관).
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Final, Iterator

from flask import Response

logger = logging.getLogger(__name__)

HEADER_ROUTE = "X-FOMS-EPT-B7-ROUTE"
HEADER_RENDER_MS = "X-FOMS-EPT-B7-RENDER-MS"
HEADER_PHASES = "X-FOMS-EPT-B7-PHASES"

_PHASE_KEY: Final[str] = "_foms_ept_b7_phases"


def record_phase(name: str, elapsed_ms: float) -> None:
    """요청 컨텍스트에 구간 소요를 누적한다(진단 전용, 실패 무시).

    Args:
        name: 구간 이름(예: ``list_query``, ``row_dtos``).
        elapsed_ms: 소요 밀리초.
    """
    try:
        from flask import g, has_request_context

        if not has_request_context():
            return
        phases = getattr(g, _PHASE_KEY, None)
        if phases is None:
            phases = []
            setattr(g, _PHASE_KEY, phases)
        phases.append((name, float(elapsed_ms)))
    except Exception:  # noqa: BLE001 - 진단 실패가 응답을 깨선 안 된다
        logger.debug("[EPT-B7] phase record skipped", exc_info=True)


@contextmanager
def phase(name: str) -> Iterator[None]:
    """``with phase("list_query"):`` 로 구간을 재고 자동 기록한다."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        record_phase(name, (time.perf_counter() - t0) * 1000)


_MARK_KEY: Final[str] = "_foms_ept_b7_marks"


def template_mark(name: str) -> str:
    """템플릿 안에서 구간을 **쌍으로** 표시한다 — `{{ mark('hist') }}` … `{{ mark('hist') }}`.

    왜 필요한가: `render_template` 하나를 `phase("wb_template")` 로 감싸면 "템플릿이 500ms"
    까지만 알 수 있고 **그 안 어디인지는 모른다**. 2026-09-11 운영 실측에서 수집 이력 탭의
    서버 시간 대부분(300~545ms)이 그 한 덩어리에 묶여 있었다. 파이썬 `phase()` 는 컨텍스트
    매니저라 Jinja 에서 못 쓰므로, 같은 이름을 두 번 부르는 것으로 구간을 만든다.

    첫 호출은 시작 시각을 적고, 두 번째 호출이 경과를 :func:`record_phase` 로 넘긴다 —
    즉 결과가 기존 ``X-FOMS-EPT-B7-PHASES`` 헤더에 그대로 실린다. 짝이 안 맞으면(한 번만
    불렀으면) 아무것도 기록되지 않는다.

    **항상 빈 문자열을 돌려준다** — 화면에 아무것도 찍지 않는다. 요청 밖에서는 조용히 무시한다.

    Args:
        name: 구간 이름(헤더에 그대로 나온다).

    Returns:
        빈 문자열(템플릿 출력에 영향 없음).
    """
    try:
        from flask import g, has_request_context

        if not has_request_context():
            return ""
        marks = getattr(g, _MARK_KEY, None)
        if marks is None:
            marks = {}
            setattr(g, _MARK_KEY, marks)
        started = marks.pop(name, None)
        if started is None:
            marks[name] = time.perf_counter()
        else:
            record_phase(name, (time.perf_counter() - started) * 1000.0)
    except Exception:  # noqa: BLE001 - 계측이 화면을 깨뜨리면 안 된다
        logger.debug("[EPT-B7] template_mark(%s) 실패", name, exc_info=True)
    return ""


def format_phases() -> str:
    """구간 관측을 헤더 값 한 줄로 만든다.

    Returns:
        ``list_query=41;row_dtos=12`` 형태(밀리초 정수). 관측이 없으면 빈 문자열.
    """
    try:
        from flask import g, has_request_context

        if not has_request_context():
            return ""
        phases = getattr(g, _PHASE_KEY, None) or []
        return ";".join(f"{name}={ms:.0f}" for name, ms in phases)
    except Exception:  # noqa: BLE001 - 진단 실패가 응답을 깨선 안 된다
        logger.debug("[EPT-B7] phase format skipped", exc_info=True)
        return ""


def apply_ept_b7_render_headers(response: Response, *, route_id: str, render_ms: float) -> None:
    """Attach render-only timing. Safe for proxies: diagnostic, not authorization."""
    response.headers[HEADER_ROUTE] = route_id
    response.headers[HEADER_RENDER_MS] = f"{render_ms:.1f}"
    phases = format_phases()
    if phases:
        response.headers[HEADER_PHASES] = phases
    logger.info("[EPT-B7] route=%s render_ms=%.1f phases=%s", route_id, render_ms, phases or "-")

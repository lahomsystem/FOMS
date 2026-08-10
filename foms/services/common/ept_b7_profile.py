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

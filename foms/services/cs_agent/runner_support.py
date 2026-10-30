"""AI 상담팀원 러너 공통 — Sentry 지역 변수 빼기 · TERM 깃발 처리기(감시 루프 ``run_cs_loop`` · 빠른 길 ``run_cs_realtime``).

두 러너는 손님 글(수신 기록 원본 · 상담 글 원문)을 지역 변수로 들고 돈다. 오류가 나면 sentry-sdk 가 스택 지역 변수를 기본으로
싣기 때문에, 이 프로세스의 모든 Sentry 이벤트에서 지역 변수를 뺀다(원장 R5-2). TERM/INT 는 멈춤 깃발만 세운다(R4-4).
"""

from __future__ import annotations

import logging
import signal
from typing import Any, Callable, Optional

try:
    from sentry_sdk.scope import add_global_event_processor
except ImportError:  # sentry-sdk 가 없는 환경 — 걸 곳이 없으니 :func:`install_sentry_privacy` 는 지나간다
    add_global_event_processor = None

__all__ = ["drop_frame_locals", "install_sentry_privacy", "install_signal_handlers"]


def drop_frame_locals(event: Any, _hint: Any = None) -> Any:
    """Sentry 이벤트에서 스택 프레임 지역 변수(``vars``)를 뺀다 — 수신 기록 원본(손님 글 · 번호)을 든 지역 변수가
    오류와 함께 Sentry 로 가지 않게(sentry-sdk 는 지역 변수를 기본으로 싣는다, 원장 R5-2). 꼴이 달라도 던지지 않는다."""
    if not isinstance(event, dict):
        return event
    for section in ("exception", "threads"):
        values = event.get(section, {}).get("values") if isinstance(event.get(section), dict) else None
        for entry in values if isinstance(values, list) else ():
            trace = entry.get("stacktrace") if isinstance(entry, dict) else None
            frames = trace.get("frames") if isinstance(trace, dict) else None
            for frame in frames if isinstance(frames, list) else ():
                if isinstance(frame, dict):
                    frame.pop("vars", None)
    return event


def install_sentry_privacy() -> None:
    """이 프로세스의 Sentry 이벤트 모두에 :func:`drop_frame_locals` 를 건다(sentry-sdk 가 없으면 지나간다)."""
    if add_global_event_processor is not None:
        add_global_event_processor(drop_frame_locals)


def install_signal_handlers(stop_set: Callable[..., None], logger: Optional[logging.Logger] = None) -> None:
    """TERM/INT 에 멈춤 깃발(``StopFlag.set``)만 세운다. 처리기를 못 달면 경고만 남긴다(바퀴는 그래도 돈다)."""
    log = logger or logging.getLogger(__name__)
    for name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, stop_set)
        except (ValueError, OSError, RuntimeError) as exc:
            log.warning("signal %s handler not installed: %s", name, exc)

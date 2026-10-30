"""AI 상담팀원 러너 공통 — Sentry 지역 변수 빼기 · TERM 깃발 처리기(감시 루프 ``run_cs_loop`` · 빠른 길 ``run_cs_realtime``).

두 러너는 손님 글(수신 기록 원본 · 상담 글 원문)을 지역 변수로 들고 돈다. 오류가 나면 sentry-sdk 가 스택 지역 변수를 기본으로
싣기 때문에, 이 프로세스의 모든 Sentry 이벤트에서 지역 변수를 뺀다(원장 R5-2). 예외 글도 뺀다 — DB 오류 글에는 SQL 매개변수
(가린 직원 답 · 가린 질문 · 상담원 id)가 그대로 들어 있다(검수 R14-8). 러너 출력도 예외 이름 · 자리만(:func:`error_summary`).
TERM/INT 는 멈춤 깃발만 세운다(R4-4).
"""

from __future__ import annotations

import logging
import os
import signal
import traceback
from typing import Any, Callable, Optional

try:
    from sentry_sdk.scope import add_global_event_processor
except ImportError:  # sentry-sdk 가 없는 환경 — 걸 곳이 없으니 :func:`install_sentry_privacy` 는 지나간다
    add_global_event_processor = None

__all__ = ["drop_frame_locals", "error_summary", "install_sentry_privacy", "install_signal_handlers"]


def drop_frame_locals(event: Any, _hint: Any = None) -> Any:
    """Sentry 이벤트에서 스택 프레임 지역 변수(``vars``)와 예외 글(``value``)을 뺀다 — 수신 기록 원본(손님 글 · 번호)을 든
    지역 변수(원장 R5-2)와 SQL 매개변수가 든 DB 오류 글(R14-8)이 Sentry 로 가지 않게. 예외 이름 · 스택은 남는다. 꼴이 달라도
    던지지 않는다."""
    if not isinstance(event, dict):
        return event
    for section in ("exception", "threads"):
        values = event.get(section, {}).get("values") if isinstance(event.get(section), dict) else None
        for entry in values if isinstance(values, list) else ():
            if isinstance(entry, dict) and section == "exception":
                entry.pop("value", None)
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


def error_summary(exc: BaseException) -> str:
    """러너 오류 한 줄 — 예외 이름 · 마지막 자리(파일:줄) · 이어진 원인 이름만. 예외 글은 싣지 않는다(SQL 매개변수 — R14-8)."""
    parts: list[str] = []
    current: Optional[BaseException] = exc
    while current is not None and len(parts) < 3:
        frames = traceback.extract_tb(current.__traceback__)
        where = f" at {os.path.basename(frames[-1].filename)}:{frames[-1].lineno}" if frames else ""
        parts.append(f"{type(current).__name__}{where}")
        current = current.__cause__ or current.__context__
    return " <- ".join(parts)

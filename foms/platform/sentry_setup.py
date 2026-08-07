"""Sentry 초기화 + 이벤트 마스킹 (AUDIT-LOG T10).

외부 관측(Sentry)은 **env-gated opt-in**이다. ``SENTRY_DSN``이 없으면
:func:`init_sentry`는 완전한 no-op이고 ``sentry_sdk`` import조차 일어나지 않는다
(모듈 import 부작용 0 — DSN이 있을 때만 지연 import). 따라서 로컬/CI/테스트
환경은 이 모듈이 배선돼 있어도 동작·의존성 면에서 이전과 동일하다.

DSN이 있을 때는 ``before_send``로 :func:`_scrub_event`를 건다. 서버 로그는
:class:`~foms.services.error_logging.RedactionFilter`(문자열 레코드 1건 마스킹)로
보호되지만 Sentry 이벤트는 **중첩 dict/list 구조**라 그 필터를 그대로 쓸 수 없다.
그래서 같은 SSOT 패턴(:data:`foms.services.error_logging._REDACTIONS`)을 재귀
워커로 재사용해 breadcrumbs·exception values·request 데이터까지 전부 훑는다.

마스킹은 fail-safe다: 순회 중 예외가 나도 밖으로 전파하지 않고(호출자는 SDK
내부다) 이벤트를 drop하지도 않으며, 비밀값이 있을 수 없는 최소 골격만 남겨
보낸다(:func:`_minimal_event`).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

# 마스킹 패턴 SSOT. 로그 필터(RedactionFilter)와 같은 규칙을 쓰기 위한 의도적
# 재사용 — 패턴을 여기에 복제하면 두 경로가 조용히 어긋난다.
from foms.services.error_logging import _REDACTIONS

SENTRY_DSN_ENV = "SENTRY_DSN"

REDACTED = "***"

#: 순환 참조·과도한 중첩 방어용 깊이 상한. Sentry 직렬화기 자체가 databag 깊이를
#: 한 자릿수로 자르므로 12면 실제 이벤트를 자르지 않으면서 무한 재귀를 막는다.
MAX_SCRUB_DEPTH = 12

#: 마스킹 실패 시 남기는 최소 이벤트에 실릴 안전 스칼라 키.
_MINIMAL_EVENT_KEYS = (
    "event_id",
    "timestamp",
    "platform",
    "level",
    "environment",
    "release",
)

SCRUB_FAILURE_MESSAGE = "[foms] sentry event scrub failed; payload withheld"

#: 비밀값을 담는 **키 이름**. ``_REDACTIONS``의 ``credential_kv``는 키워드와 값이
#: 한 문자열 안에 있을 때만(``password=...``) 동작하는데, 이벤트 dict는 키와 값이
#: 별개 노드로 쪼개져 있어(``{"password": "hunter2"}``) 그 패턴이 걸리지 않는다.
#: 이 규칙이 그 사각을 덮는다(form body·cookies·headers 맵 등).
_SECRET_KEY_NAME = re.compile(
    r"(?i)^(?:x[-_]?)?(?:"
    r"password|passwd|pwd|secret|secret[_-]?key|"
    r"token|access[_-]?token|refresh[_-]?token|csrf[_-]?token|"
    r"api[_-]?key|apikey|access[_-]?key|private[_-]?key|"
    r"authorization|auth|cookie|cookies|session[_-]?id|sessionid|"
    r"aws[_-]?secret[_-]?access[_-]?key"
    r")$"
)

_logger = logging.getLogger(__name__)


def _redact_text(value: str) -> str:
    """문자열 하나에 ``_REDACTIONS`` 패턴을 순서대로 적용한다.

    Args:
        value: 마스킹 대상 문자열(이벤트 dict의 잎 노드).

    Returns:
        비밀값 형태의 부분 문자열이 ``***``로 치환된 문자열.
    """
    redacted = value
    for _name, pattern, replacement in _REDACTIONS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _scrub_value(value: Any, depth: int) -> Any:
    """dict/list/tuple/str를 재귀 순회하며 비밀값을 마스킹한 **새 구조**를 만든다.

    원본은 건드리지 않는다(비파괴) — SDK가 같은 dict를 다른 용도로 참조할 수
    있고, 마스킹 실패 시 원본에서 최소 이벤트를 다시 만들어야 하기 때문이다.

    Args:
        value: 이벤트 트리의 임의 노드.
        depth: 현재 재귀 깊이(루트 0).

    Returns:
        같은 모양의 마스킹된 사본. 깊이 상한을 넘으면 ``***``(순환 참조여도
        여기서 종료되며, 미마스킹 문자열이 새어나가지 않는 쪽으로 fail-safe).
    """
    if depth >= MAX_SCRUB_DEPTH:
        return REDACTED
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        scrubbed: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _SECRET_KEY_NAME.match(key.strip()):
                scrubbed[key] = REDACTED
                continue
            scrubbed[key] = _scrub_value(item, depth + 1)
        return scrubbed
    if isinstance(value, list):
        return [_scrub_value(item, depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_value(item, depth + 1) for item in value)
    return value


def _exception_types(event: Any) -> list[str]:
    """이벤트에서 예외 **타입 이름만** 뽑는다(값·스택은 제외).

    Args:
        event: Sentry 이벤트 dict(형식이 달라도 예외 없이 빈 목록 반환).

    Returns:
        ``["KeyError", ...]`` 형태의 타입 이름 목록.
    """
    if not isinstance(event, dict):
        return []
    exception = event.get("exception")
    if not isinstance(exception, dict):
        return []
    values = exception.get("values")
    if not isinstance(values, list):
        return []
    names: list[str] = []
    for entry in values:
        if isinstance(entry, dict):
            type_name = entry.get("type")
            if isinstance(type_name, str):
                names.append(type_name)
    return names


def _minimal_event(event: Any) -> dict[str, Any]:
    """마스킹 실패 시 보낼 최소 이벤트(비밀값이 있을 수 없는 골격만).

    이벤트를 drop(``None``)하지 않는 이유: "마스킹이 깨졌다"는 사실 자체가
    관측돼야 하고, 조용한 소실은 장애 시 최악이기 때문이다. 대신 payload
    (message·request·breadcrumbs·extra·stack)는 전부 버린다.

    Args:
        event: 원본 이벤트(형식 불문 — dict가 아니어도 안전하다).

    Returns:
        Sentry에 보낼 최소 이벤트 dict.
    """
    minimal: dict[str, Any] = {"logentry": {"message": SCRUB_FAILURE_MESSAGE}}
    if isinstance(event, dict):
        for key in _MINIMAL_EVENT_KEYS:
            value = event.get(key)
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                minimal[key] = value
        type_names = _exception_types(event)
        if type_names:
            minimal["extra"] = {"exception_types": type_names}
    return minimal


def _scrub_event(event: Any, hint: Any = None) -> Any:
    """Sentry ``before_send`` 훅 — 전송 직전 이벤트를 재귀 마스킹한다.

    SDK 내부에서 호출되므로 **어떤 예외도 밖으로 던지지 않는다**. 순회가
    실패하면 경고 1줄(예외 타입만 — 메시지에 비밀값이 섞일 수 있다)을 남기고
    최소 이벤트로 대체한다.

    Args:
        event: 직렬화가 끝난 Sentry 이벤트 dict.
        hint: SDK가 주는 부가 정보(원본 예외 등). 마스킹에는 쓰지 않는다.

    Returns:
        마스킹된 이벤트 dict(절대 ``None``이 아니다 — drop하지 않는다).
    """
    try:
        return _scrub_value(event, 0)
    except (
        AttributeError,
        IndexError,
        KeyError,
        MemoryError,
        RecursionError,
        TypeError,
        ValueError,
    ) as exc:
        _logger.warning(
            "sentry event scrub failed (%s); sending minimal event",
            type(exc).__name__,
        )
        return _minimal_event(event)


def resolve_environment() -> str:
    """Sentry ``environment`` 태그 값을 env에서 해석한다.

    Returns:
        ``RAILWAY_ENVIRONMENT`` → ``FOMS_ENV`` 순으로 처음 발견한 비어 있지 않은
        값. 둘 다 없으면 ``"local"``.
    """
    for env_name in ("RAILWAY_ENVIRONMENT", "FOMS_ENV"):
        value = (os.environ.get(env_name) or "").strip()
        if value:
            return value
    return "local"


def init_sentry() -> bool:
    """``SENTRY_DSN``이 설정된 경우에만 Sentry SDK를 초기화한다.

    DSN이 없으면 즉시 반환한다 — ``sentry_sdk`` import도 하지 않으므로 미설치
    환경(로컬·CI)에서도 부작용이 0이다.

    Returns:
        초기화를 수행했으면 ``True``. DSN 부재·SDK 미설치·DSN 형식 오류로
        건너뛰었으면 ``False``(기동은 절대 막지 않는다 — 관측 배선 실패가
        서비스 부팅을 죽이면 안 된다).
    """
    dsn = (os.environ.get(SENTRY_DSN_ENV) or "").strip()
    if not dsn:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
    except ImportError:
        _logger.warning(
            "%s is set but sentry-sdk is not installed; skipping Sentry init",
            SENTRY_DSN_ENV,
        )
        return False

    environment = resolve_environment()
    try:
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration()],
            send_default_pii=False,
            traces_sample_rate=0.0,
            environment=environment,
            before_send=_scrub_event,
        )
    except (ValueError, TypeError) as exc:
        # BadDsn은 ValueError 하위 — 잘못된 env 하나로 부팅이 죽지 않게 한다.
        _logger.warning("Sentry init skipped (%s)", type(exc).__name__)
        return False

    _logger.info("Sentry initialized environment=%s", environment)
    return True

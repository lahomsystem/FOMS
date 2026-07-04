"""Same-origin write guard 공용 팩토리.

민감한 write 엔드포인트(알림 read/archive/ack, 발송, 긴급 호출 등)는 커스텀
same-origin 헤더를 요구해, 크로스 사이트 form POST 가 사용자의 세션 쿠키를 조용히
재사용하지 못하게 한다. designer(`X-FOMS-Designer-Write`)에서 검증된 패턴을 일반화한 것.

- 헤더 값이 정확히 ``"1"`` 이어야 한다(없거나 다르면 403).
- ``Origin`` / ``Referer`` 가 있으면 요청 호스트와 같은 origin 이어야 한다(아니면 403).
- 실패는 앱 로거(`current_app.logger.warning`)로 audit 남긴다(묵시적 무시 금지).
"""

from __future__ import annotations

from functools import wraps
from typing import Callable, TypeVar, cast
from urllib.parse import urlparse

from flask import current_app, jsonify, request

F = TypeVar("F", bound=Callable[..., object])

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _same_origin(value: str) -> bool:
    """``value`` 의 scheme://netloc 이 현재 요청 origin 과 동일한지 판정.

    :param value: ``Origin`` 또는 ``Referer`` 헤더 문자열
    :return: 동일 origin 이면 True. scheme/netloc 이 없으면 False.
    """
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return False
    request_origin = f"{request.scheme}://{request.host}"
    return f"{parsed.scheme}://{parsed.netloc}" == request_origin


def _audit_block(header_name: str, reason: str) -> None:
    """차단 사유를 앱 로거로 기록(fail-open 이 아니라 항상 로그로 남김)."""
    try:
        current_app.logger.warning(
            "write-guard blocked: header=%s reason=%s path=%s ip=%s",
            header_name,
            reason,
            request.path,
            request.remote_addr,
        )
    except Exception:  # noqa: BLE001 - 로깅 실패가 요청을 죽이면 안 됨
        pass


def require_same_origin_write(header_name: str) -> Callable[[F], F]:
    """지정 헤더를 요구하는 same-origin write guard 데코레이터를 생성.

    :param header_name: 요구할 커스텀 헤더 이름(예: ``"X-FOMS-Notification-Write"``)
    :return: 뷰 함수를 감싸는 데코레이터. mutating method 에서만 검증하고,
        위반 시 ``{"success": False, ...}`` + 403 을 반환한다.
    """

    def decorator(f: F) -> F:
        @wraps(f)
        def wrapper(*args: object, **kwargs: object) -> object:
            if request.method in _WRITE_METHODS:
                if request.headers.get(header_name) != "1":
                    _audit_block(header_name, "missing_header")
                    return jsonify({
                        "success": False,
                        "data": None,
                        "error": "write header is required",
                    }), 403

                origin = request.headers.get("Origin")
                referer = request.headers.get("Referer")
                if origin and not _same_origin(origin):
                    _audit_block(header_name, "invalid_origin")
                    return jsonify({
                        "success": False,
                        "data": None,
                        "error": "invalid request origin",
                    }), 403
                if referer and not _same_origin(referer):
                    _audit_block(header_name, "invalid_referer")
                    return jsonify({
                        "success": False,
                        "data": None,
                        "error": "invalid request referer",
                    }), 403

            return f(*args, **kwargs)

        return cast(F, wrapper)

    return decorator

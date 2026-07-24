"""공용 CSRF + Origin write guard (WRITE-GUARD-01).

cookie-auth state-changing route 를 두 계층으로 보호한다.

1. **공용 before_request 가드**(:func:`enforce_csrf_origin`): 모든
   POST/PUT/PATCH/DELETE 요청에서 (a) ``Origin``/``Referer`` 가 있으면 same-origin,
   (b) 세션 바인딩 서명 CSRF 토큰이 유효한지 검증한다. 실패는 **핸들러 실행 전** 403
   으로 차단하므로 DB/상태 변화가 0 이다. exempt 엔드포인트(provider 서명
   webhook/Function, anonymous RUM, login/register)는
   ``docs/harness/foms_write_guard_manifest.json`` 에 명시로 등재되어 우회한다.
   manifest 에 없는 mutation endpoint 는 **fail-safe 로 guard** 되며 static gate 가
   미등재를 잡는다.

2. **레거시 per-route** :func:`require_same_origin_write` (커스텀 헤더 ``"1"``)는 호환을
   위해 유지한다. 공용 가드가 상위 방어이고 데코레이터는 추가(defense-in-depth)다.

CSRF 토큰은 세션에 저장된 per-session 랜덤 seed 를 ``itsdangerous`` (``app.secret_key``)
로 서명한 값이다. HTML 은 ``<meta name="csrf-token">``/hidden field, JSON·fetch 는
``X-CSRF-Token`` 헤더(또는 sendBeacon 용 JSON body ``csrf_token``)로 전달한다. 검증은
constant-time(:func:`hmac.compare_digest`). SameSite/CORS 는 보조 방어이며 이 가드를
대체하지 않는다.

가드는 ``WRITE_GUARD_ENABLED`` config(미지정 시 ``not TESTING``)로 켜지므로, 기존
테스트(``TESTING=True``)는 토큰 없이도 그대로 통과하고 write-guard 전용 테스트만 명시로
활성화한다(Flask-WTF ``WTF_CSRF_ENABLED`` 와 동일한 관례).
"""

from __future__ import annotations

import hmac
import json
import os
from functools import wraps
from typing import Any, Callable, TypeVar, cast
from urllib.parse import urlparse

from flask import Flask, current_app, jsonify, request, session
from itsdangerous import BadSignature, URLSafeSerializer

F = TypeVar("F", bound=Callable[..., object])

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# --- CSRF 토큰 상수 -------------------------------------------------------
_CSRF_SESSION_KEY = "_csrf_seed"
_CSRF_SALT = "foms-csrf-token"
_CSRF_HEADER = "X-CSRF-Token"
_CSRF_FIELD = "csrf_token"
_BLOCK_HEADER = "X-Write-Guard"

# manifest 정본 경로: foms/services/request_write_guard.py → repo root/docs/harness/…
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MANIFEST_PATH = os.path.join(
    _REPO_ROOT, "docs", "harness", "foms_write_guard_manifest.json"
)

# register_write_guard() 가 startup 에 1회 채운다(부재 시 loud fail — 아래 참고).
_EXEMPT_ENDPOINTS: frozenset[str] = frozenset()


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


# ---------------------------------------------------------------------------
# 공용 CSRF 토큰 (session-bound, itsdangerous 서명)
# ---------------------------------------------------------------------------


def _serializer() -> URLSafeSerializer:
    """현재 앱 secret_key 로 서명하는 CSRF 직렬화기.

    :return: ``app.secret_key`` + salt 로 초기화된 :class:`URLSafeSerializer`.
        만료 없는 서명(세션 seed 회전이 무효화 경계)이라 정상 세션 중 토큰 만료로
        인한 회귀를 만들지 않는다.
    """
    return URLSafeSerializer(current_app.secret_key, salt=_CSRF_SALT)


def _ensure_csrf_seed() -> str:
    """세션에 per-session CSRF seed 를 보장하고 반환.

    :return: 세션에 저장된(없으면 새로 생성한) 128-bit hex seed 문자열.
    """
    seed = session.get(_CSRF_SESSION_KEY)
    if not seed:
        seed = os.urandom(16).hex()
        session[_CSRF_SESSION_KEY] = seed
        session.permanent = True
    return seed


def generate_csrf_token() -> str:
    """세션 바인딩 서명 CSRF 토큰을 생성/반환.

    템플릿에서 ``{{ csrf_token() }}`` 로 노출된다(:func:`register_write_guard` 가
    context processor 로 주입). 매 호출은 같은 세션 seed 를 서명하므로 한 세션 내에서
    안정적이다.

    :return: URL-safe 서명 토큰 문자열.
    """
    return _serializer().dumps(_ensure_csrf_seed())


def validate_csrf_token(token: str | None) -> bool:
    """제출된 CSRF 토큰이 현재 세션 seed 와 일치하는지 constant-time 검증.

    :param token: 요청에서 추출한 토큰(헤더/폼/JSON). ``None``/빈 값이면 실패.
    :return: 서명이 유효하고 unsigned seed 가 세션 seed 와 동일하면 True.
    """
    if not token:
        return False
    seed = session.get(_CSRF_SESSION_KEY)
    if not seed:
        return False
    try:
        unsigned = _serializer().loads(token)
    except BadSignature:
        return False
    return hmac.compare_digest(str(unsigned), str(seed))


def _request_csrf_token() -> str:
    """요청에서 CSRF 토큰을 추출(헤더 → 폼 필드 → JSON body 순).

    헤더를 먼저 보므로 fetch/XHR/업로드는 body 파싱 없이 즉시 해결된다. sendBeacon 처럼
    헤더를 못 다는 JSON 요청만 body ``csrf_token`` 을 읽는다.

    :return: 발견한 토큰 문자열(없으면 빈 문자열).
    """
    header = request.headers.get(_CSRF_HEADER) or request.headers.get("X-CSRFToken")
    if header:
        return header
    ctype = (request.mimetype or "").lower()
    if ctype in ("application/x-www-form-urlencoded", "multipart/form-data"):
        field = request.form.get(_CSRF_FIELD)
        if field:
            return field
    if request.is_json or ctype == "application/json":
        data = request.get_json(silent=True)
        if isinstance(data, dict):
            val = data.get(_CSRF_FIELD)
            if isinstance(val, str):
                return val
    return ""


# ---------------------------------------------------------------------------
# 공용 before_request 가드
# ---------------------------------------------------------------------------


def _guard_active() -> bool:
    """이 요청에서 공용 write guard 를 적용할지 여부.

    :return: ``WRITE_GUARD_ENABLED`` config 가 있으면 그 값, 없으면 ``not TESTING``.
        (Flask-WTF ``WTF_CSRF_ENABLED`` 관례 — 기존 테스트 무회귀 + 전용 테스트 활성화.)
    """
    cfg = current_app.config
    if "WRITE_GUARD_ENABLED" in cfg:
        return bool(cfg["WRITE_GUARD_ENABLED"])
    return not cfg.get("TESTING", False)


def _block(reason: str) -> Any:
    """403 차단 응답을 만들고 audit 로그를 남긴다(핸들러 실행 전 차단 → DB0).

    :param reason: audit 사유 태그(예: ``invalid_csrf_token``).
    :return: ``X-Write-Guard: blocked`` 헤더가 붙은 403 JSON 응답.
    """
    _audit_block("csrf-origin", reason)
    resp = jsonify({
        "success": False,
        "data": None,
        "error": "요청 검증에 실패했습니다. 페이지를 새로고침한 뒤 다시 시도해 주세요.",
    })
    resp.status_code = 403
    resp.headers[_BLOCK_HEADER] = "blocked"
    return resp


def enforce_csrf_origin() -> Any:
    """공용 before_request 가드: cookie-auth mutation 의 CSRF+Origin 검증.

    non-mutating method, 가드 비활성(테스트), 미라우팅(``endpoint is None``), manifest
    exempt endpoint 는 통과시킨다. 그 외 mutation 은 same-origin(Origin/Referer 존재 시)
    과 유효 CSRF 토큰을 모두 요구하며, 실패 시 403 을 반환해 핸들러를 실행하지 않는다.

    :return: 차단 시 403 응답, 통과 시 ``None``.
    """
    if request.method not in _WRITE_METHODS:
        return None
    if not _guard_active():
        return None
    endpoint = request.endpoint
    if endpoint is None:  # 404/미라우팅 — 핸들러 없음
        return None
    if endpoint in _EXEMPT_ENDPOINTS:
        return None

    origin = request.headers.get("Origin")
    if origin and not _same_origin(origin):
        return _block("invalid_origin")
    referer = request.headers.get("Referer")
    if referer and not _same_origin(referer):
        return _block("invalid_referer")
    if not validate_csrf_token(_request_csrf_token()):
        return _block("invalid_csrf_token")
    return None


def load_write_guard_manifest() -> dict[str, Any]:
    """write-guard manifest(JSON)를 로드.

    :return: manifest dict(``routes`` 등).
    :raises OSError: 파일 부재.
    :raises ValueError: JSON 파싱 실패.
    """
    with open(_MANIFEST_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def register_write_guard(app: Flask) -> None:
    """앱에 공용 write guard 를 배선한다(app_factory 에서 1회 호출).

    startup 에 manifest 를 로드해 exempt endpoint 집합을 확정하고, before_request 가드와
    ``csrf_token`` context processor 를 등록한다. manifest 부재/파손은 여기서 예외를
    일으켜 앱 부팅을 막는다(per-request 로 조용히 degrade 하지 않음).

    :param app: 대상 Flask 앱.
    """
    global _EXEMPT_ENDPOINTS
    manifest = load_write_guard_manifest()
    _EXEMPT_ENDPOINTS = frozenset(
        ep
        for ep, meta in manifest.get("routes", {}).items()
        if isinstance(meta, dict) and meta.get("mode") == "exempt"
    )
    app.before_request(enforce_csrf_origin)
    app.context_processor(lambda: {"csrf_token": generate_csrf_token})

"""Rate limiter setup helpers."""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

from flask import request, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from foms.services.security.auth_rate.key_state import sign_rate_bucket
from foms.services.security.auth_rate.login_lockout import login_bucket_key

__all__ = ["init_limiter"]

logger = logging.getLogger(__name__)

#: 로그인 POST 전용 한도. 로그인은 사람이 하는 행위라 분당 10회면 오타 폭풍·비밀번호
#: 관리자 재시도·중복 제출을 전부 덮고도 남지만, 자동 추측기는 분당 수천 → 10 으로 떨어진다.
#: 시간당 100은 느리게 흘리는 추측기(분당 1.7회)까지 눌러 온라인 대입을 무의미하게 만든다.
#: env 로 여는 이유: 아침 출근 로그인 몰림처럼 현장에서만 드러나는 상황을 **재배포 없이**
#: 넓혀야 한다(FLASK_DEFAULT_RATE_LIMITS·FOMS_ACCOUNT_REQUEST_RATE_LIMIT 와 같은 관례).
LOGIN_RATE_LIMIT_ENV = "FOMS_LOGIN_RATE_LIMIT"
DEFAULT_LOGIN_RATE_LIMIT = "10 per minute;100 per hour"

#: 로그인 성공 응답의 상태 코드. 성공은 302(홈/next 로 리다이렉트), 실패는 폼 재렌더(200)
#: 또는 잠금(429)이다.
_LOGIN_SUCCESS_STATUS = 302

#: flask-limiter 가 자기 로그를 내보내는 로거 이름(패키지 소스 ``_extension.py``:
#: ``self.logger = logging.getLogger("flask-limiter")``). 배선은 인스턴스의 ``logger``
#: 속성을 쓰고, 이 상수는 그 이름을 계약 테스트가 고정하기 위한 것이다 — 패키지가
#: 로거 이름을 바꾸면 관측이 조용히 죽는 대신 테스트가 빨개진다.
FLASK_LIMITER_LOGGER_NAME = "flask-limiter"


def _capture_sentry_event(message: str, storage_scheme: str) -> bool:
    """레이트리미터 폴백을 Sentry 이벤트 1건으로 올린다(DSN 이 있을 때만).

    ``foms/services/jobs/tasks.py`` 와 같은 관례다 — DSN 이 없으면 ``sentry_sdk`` 를
    import 조차 하지 않는 :func:`foms.platform.sentry_setup.init_sentry` 뒤에 놓이므로
    여기서는 클라이언트가 살아 있을 때만 보낸다.

    :param message: 이벤트 제목(비밀값·PII 금지 — 저장소 scheme 만 싣는다).
    :param storage_scheme: ``redis``/``memory`` 등 저장소 scheme(자격증명 없음).
    :return: 이벤트를 실제로 보냈으면 ``True``.
    """
    try:
        import sentry_sdk
    except ImportError:
        return False
    try:
        if not sentry_sdk.get_client().is_active():
            return False
        # new_scope 로 감싼다 — set_tag 를 전역 스코프에 걸면 이후 다른 이벤트에도
        # 이 태그가 따라붙는다(관측 오염).
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("rate_limit_storage", storage_scheme)
            sentry_sdk.capture_message(message, level="warning")
    except (AttributeError, TypeError, ValueError):
        # 구버전 SDK(get_client 부재)·인자 계약 변경. 관측 배선이 요청을 죽이면 안 되므로
        # 여기서 멈추되(이 함수는 logging 핸들러 안에서 돈다) 조용히 넘기지는 않는다.
        logger.warning("Sentry 이벤트 전송 실패 — 로그만 남는다", exc_info=True)
        return False
    return True


class _StorageFallbackAlert(logging.Handler):
    """레이트리미터가 인메모리 폴백으로 떨어지는 **순간만** 1건으로 관측한다.

    :func:`init_limiter` 는 ``swallow_errors=True`` + ``in_memory_fallback_enabled=True`` 라
    Redis 가 죽으면 조용히 프로세스 로컬 메모리로 내려앉는다 — 한도가 replica 별로
    쪼개져 사실상 열리는데 아무도 모른다. flask-limiter 가 그 전이를 밖에 알리는 유일한
    지점이 자기 로거(``_extension.py``: ``_check_request_limit`` 와 ``__inject_headers``
    두 곳에서 ``logger.warning("Rate limit storage unreachable - falling back to
    in-memory storage")``)이므로 거기에 핸들러를 붙인다.

    **1건으로 만드는 방법**: flask-limiter 는 그 warning 을 낸 **직후에**
    ``_storage_dead = True`` 로 바꾼다. 그래서 핸들러가 도는 시점의 ``_storage_dead`` 가
    아직 ``False`` 인 레코드만이 "이번에 새로 떨어졌다" 를 뜻한다. 폴백 중에 나오는
    후속 warning/error 는 그 값이 이미 ``True`` 라 저절로 걸러지고, 저장소가 살아나면
    flask-limiter 가 ``_storage_dead`` 를 ``False`` 로 되돌리므로 **다음 장애 때 다시 1건**
    이 나간다(별도 재무장 상태를 우리가 들고 있지 않아도 된다).

    메시지 문자열을 대조하지 않는 것도 의도다 — 폴백 문구가 바뀌어도, 폴백이 아닌 다른
    degradation warning 이 새로 생겨도, "리미터가 정상이 아니다" 라는 알림 1건은 그대로 나간다.
    요청마다 도는 훅이 아니므로 정상 구간의 비용은 0이다.
    """

    def __init__(self, limiter: Any, storage_scheme: str) -> None:
        """전이를 감시할 limiter 와 로그에 실을 저장소 scheme 을 묶는다.

        :param limiter: 감시 대상 :class:`flask_limiter.Limiter`.
        :param storage_scheme: ``redis``/``memory`` 등 scheme 문자열(자격증명 없음).
        """
        super().__init__(level=logging.WARNING)
        self._limiter = limiter
        self._storage_scheme = storage_scheme

    def emit(self, record: logging.LogRecord) -> None:
        """폴백 전이 레코드 1건을 운영 로그 + Sentry 로 옮긴다.

        :param record: flask-limiter 가 낸 로그 레코드.
        :return: 없음.
        """
        if getattr(self._limiter, "_storage_dead", False):
            return
        detail = str(record.msg)
        logger.warning(
            "레이트리미터 저장소 장애 — 인메모리 폴백으로 떨어졌다(한도가 replica 별로 쪼개진다). "
            "storage=%s detail=%s",
            self._storage_scheme,
            detail,
        )
        _capture_sentry_event(
            f"rate limiter fell back to in-memory storage (storage={self._storage_scheme})",
            self._storage_scheme,
        )


def _install_storage_fallback_alert(limiter: Any, storage_scheme: str) -> None:
    """폴백 관측 핸들러를 flask-limiter 로거에 **하나만** 남기고 붙인다.

    로거는 프로세스 전역(``logging.getLogger("flask-limiter")``)이라 앱을 다시 만들면
    핸들러가 쌓여 같은 사건이 여러 번 보고된다. 기존 것을 걷어내고 최신 limiter 를
    가리키는 핸들러 하나만 남긴다.

    :param limiter: 감시 대상 limiter. ``logger`` 속성이 없으면(테스트 스파이 등) 아무 것도 하지 않는다.
    :param storage_scheme: ``redis``/``memory`` 등 scheme 문자열.
    :return: 없음.
    """
    target = getattr(limiter, "logger", None)
    if target is None:
        return
    for existing in list(target.handlers):
        if isinstance(existing, _StorageFallbackAlert):
            target.removeHandler(existing)
            existing.close()  # logging 모듈 전역 핸들러 목록에서도 뺀다(참조 누수 방지).
    target.addHandler(_StorageFallbackAlert(limiter, storage_scheme))


def _login_attempt_failed(response: Any) -> bool:
    """이 응답이 "인증되지 않은 로그인 시도" 인가 — 한도를 깎을지 판정한다.

    한도가 막으려는 것은 무차별 대입이고, 무차별 대입은 **실패**를 만든다. 그래서 성공한
    로그인(302)은 버킷을 깎지 않는다. 성공까지 세면 공용 계정을 여러 명이 잇달아 쓰는
    현장(교대 태블릿·공용 단말)이 정상 사용만으로 429 를 맞는데, 그건 이 한도가 막으려던
    것과 아무 상관이 없다. 자격증명을 이미 쥔 사람이 로그인을 반복하는 경우는 전역 기본
    한도(FLASK_DEFAULT_RATE_LIMITS)가 잡는다.

    flask-limiter 는 이 판정을 ``deduct_when`` 으로 제공한다 — 검사는 요청 전에(``test``),
    차감은 응답 뒤에(``hit``) 일어나므로 임계 초과 판정 시점은 그대로다.

    :param response: 로그인 요청의 최종 응답.
    :return: 버킷을 깎아야 하면 ``True``(= 인증되지 않은 시도).
    """
    return getattr(response, "status_code", 0) != _LOGIN_SUCCESS_STATUS


def _bind_login_rate_limit(app: Any, limiter: Any) -> None:
    """``auth.login`` POST 에 로그인 전용 한도를 건다.

    이 저장소의 관례 그대로다(``foms/platform/realtime.py`` 의 ``auth.register`` 배선) —
    블루프린트 등록이 끝난 뒤 ``app.view_functions`` 를 감싼다. 키는 기본 ``rate_limit_key``
    가 아니라 **아이디+IP** 다: 기본 키는 세션 쿠키 hash 를 우선하는데 로그인은 익명
    엔드포인트라 쿠키가 클라이언트 임의 값이고, 쿠키를 갈아 끼우면 버킷이 무한히 회전한다.
    차감 조건은 :func:`_login_attempt_failed` — 성공한 로그인은 한도를 깎지 않는다.

    :param app: 블루프린트 등록이 끝난 Flask 앱.
    :param limiter: 초기화된 limiter.
    :return: 없음.
    """
    view = app.view_functions.get("auth.login")
    if view is None:
        return
    limit_value = (os.environ.get(LOGIN_RATE_LIMIT_ENV) or "").strip() or DEFAULT_LOGIN_RATE_LIMIT
    app.view_functions["auth.login"] = limiter.limit(
        limit_value,
        methods=["POST"],
        key_func=login_bucket_key,
        deduct_when=_login_attempt_failed,
    )(view)


def init_limiter(app: Any) -> Limiter:
    """Initialize the Flask-Limiter instance for the current app."""
    redis_url = os.environ.get("REDIS_URL")

    def _base_rate_limit_key() -> str:
        try:
            user_id = session.get("user_id")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass  # failopen: intentional: 레이트리밋 키 산출 실패 시 폴백 키로 fail-open

        try:
            cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
            raw_cookie = request.cookies.get(cookie_name, "").strip()
            if raw_cookie:
                cookie_hash = hashlib.sha1(raw_cookie.encode("utf-8")).hexdigest()[:16]
                return f"sess:{cookie_hash}"
        except Exception:
            pass  # failopen: intentional: 레이트리밋 쿠키 키 산출 실패 시 폴백 키로 fail-open

        # Canonical client IP only. request.remote_addr is set by ProxyFix from
        # exactly FOMS_TRUSTED_PROXY_HOPS trusted X-Forwarded-For hops (see
        # foms.platform.app_factory.apply_proxy_fix). Parsing the raw
        # X-Forwarded-For / X-Real-IP headers here would let a client spoof its
        # rate-limit key via the attacker-controlled left-most entry, so it is
        # deliberately not done.
        return get_remote_address()

    def rate_limit_key() -> str:
        # AUTH-ACCOUNT-01 BRIDGE: sign the bucket with the active auth-rate key when
        # the state machine is engaged; a byte-identical pass-through otherwise (no
        # forced invalidation of existing buckets). sign_rate_bucket is fail-open.
        return sign_rate_bucket(_base_rate_limit_key())

    default_limits_raw = os.environ.get("FLASK_DEFAULT_RATE_LIMITS", "5000 per day,1200 per hour")
    default_limits = [value.strip() for value in default_limits_raw.split(",") if value.strip()]
    if not default_limits:
        default_limits = ["5000 per day", "1200 per hour"]

    # Fail open: a Redis outage must degrade to in-memory limiting, never 500s.
    storage_options = (
        {"socket_connect_timeout": 2, "socket_timeout": 2} if redis_url else {}
    )

    limiter = Limiter(
        rate_limit_key,
        app=app,
        storage_uri=redis_url or "memory://",
        default_limits=default_limits,
        storage_options=storage_options,
        swallow_errors=True,
        in_memory_fallback_enabled=True,
    )

    # 자격증명 없는 라벨만 남긴다(URL 원문은 로그·Sentry 어디에도 싣지 않는다).
    storage_scheme = redis_url.split("://", 1)[0] if redis_url else "memory"
    _install_storage_fallback_alert(limiter, storage_scheme)
    _bind_login_rate_limit(app, limiter)
    return limiter

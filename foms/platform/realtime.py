"""Realtime and limiter bootstrap helpers for the root Flask app entrypoint."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import Flask


@dataclass(frozen=True)
class RealtimeBindings:
    """Runtime bindings produced by the realtime bootstrap."""

    limiter: Any
    socketio: Any


def _mask_url_secret(raw_url: str) -> str:
    """로그 출력 시 URL의 인증정보를 마스킹."""
    try:
        parsed = urlsplit(raw_url)
        if not parsed.netloc or "@" not in parsed.netloc:
            return raw_url
        creds, hostpart = parsed.netloc.rsplit("@", 1)
        if ":" in creds:
            user, _ = creds.split(":", 1)
            masked = f"{user}:***@{hostpart}"
        else:
            masked = f"***@{hostpart}"
        return urlunsplit(
            (parsed.scheme, masked, parsed.path, parsed.query, parsed.fragment)
        )
    except Exception:
        return raw_url


def _augment_redis_url_for_socketio(raw_url: str | None) -> str | None:
    """Socket.IO Redis 매니저 연결 안정성을 위한 query 옵션 보강."""
    if not raw_url:
        return raw_url
    try:
        parsed = urlsplit(raw_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.setdefault("health_check_interval", "30")
        query.setdefault("socket_keepalive", "1")
        query.setdefault("retry_on_timeout", "1")
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(query),
                parsed.fragment,
            )
        )
    except Exception:
        return raw_url


def init_realtime_bootstrap(
    app: Flask,
    *,
    redis_url: str | None,
    socketio_available: bool,
    init_limiter: Callable[[Flask], Any],
    register_chat_socketio_handlers: Callable[..., Any],
) -> RealtimeBindings:
    """Initialize the limiter, Socket.IO, and related app config in existing order."""
    limiter = init_limiter(app)

    notification_badge_limit = os.environ.get(
        "ERP_NOTIFICATION_BADGE_RATE_LIMIT",
        "20000 per day,6000 per hour",
    )
    notification_badge_view = app.view_functions.get("notifications.api_notifications_badge")
    if notification_badge_view is not None:
        app.view_functions["notifications.api_notifications_badge"] = limiter.limit(
            notification_badge_limit
        )(notification_badge_view)

    # 읽음/보관/확인(state 변경) write 엔드포인트 rate limit.
    notification_read_limit = os.environ.get(
        "ERP_NOTIFICATION_READ_RATE_LIMIT",
        "600 per hour",
    )
    for endpoint in (
        "notifications.api_notification_mark_read",
        "notifications.api_notifications_mark_all_read",
        "notifications.api_notification_archive",
        "notifications.api_notifications_archive_all",
        "notifications.api_notification_ack",
    ):
        view = app.view_functions.get(endpoint)
        if view is not None:
            app.view_functions[endpoint] = limiter.limit(notification_read_limit)(view)

    # 주문 문맥형 긴급 호출(멘션) rate limit.
    urgent_mention_limit = os.environ.get(
        "ERP_URGENT_MENTION_RATE_LIMIT",
        "30 per hour",
    )
    urgent_mention_view = app.view_functions.get("notifications.api_order_urgent_mention")
    if urgent_mention_view is not None:
        app.view_functions["notifications.api_order_urgent_mention"] = limiter.limit(
            urgent_mention_limit
        )(urgent_mention_view)

    # Web Push 구독 upsert/soft-delete rate limit.
    push_subscribe_limit = os.environ.get(
        "ERP_PUSH_SUBSCRIBE_RATE_LIMIT",
        "120 per hour",
    )
    push_subscribe_view = app.view_functions.get("notifications_push.subscribe")
    if push_subscribe_view is not None:
        app.view_functions["notifications_push.subscribe"] = limiter.limit(
            push_subscribe_limit
        )(push_subscribe_view)

    # Web Push 테스트 발송(존재/flag 검증) rate limit.
    push_test_limit = os.environ.get(
        "ERP_PUSH_TEST_RATE_LIMIT",
        "10 per hour",
    )
    push_test_view = app.view_functions.get("notifications_push.push_test")
    if push_test_view is not None:
        app.view_functions["notifications_push.push_test"] = limiter.limit(
            push_test_limit
        )(push_test_view)

    # Web Push SW 상호작용 보고(opened/closed) rate limit.
    push_event_limit = os.environ.get(
        "ERP_PUSH_EVENT_RATE_LIMIT",
        "300 per hour",
    )
    push_event_view = app.view_functions.get("notifications_push.push_event")
    if push_event_view is not None:
        app.view_functions["notifications_push.push_event"] = limiter.limit(
            push_event_limit
        )(push_event_view)

    # 익명 RUM 수집(무인증 POST) rate limit — canonical client(remote_addr, PROXY-01)
    # 기준. 신뢰 불가 X-Forwarded-For 로 버킷을 우회할 수 없다(rate_limit_key 는
    # 원시 XFF 를 읽지 않는다).
    rum_ingest_limit = os.environ.get(
        "FOMS_RUM_INGEST_RATE_LIMIT",
        "120 per minute",
    )
    rum_ingest_view = app.view_functions.get("foms_rum.ingest_rum_event")
    if rum_ingest_view is not None:
        app.view_functions["foms_rum.ingest_rum_event"] = limiter.limit(
            rum_ingest_limit
        )(rum_ingest_view)

    # WAM telemetry 수집(scoped) rate limit — token+order 및 canonical client
    # (remote_addr, PROXY-01) 각 per-minute. 두 버킷 모두 신뢰 불가 XFF 로
    # 우회할 수 없다(WAM-TELEMETRY-01).
    wam_telemetry_limit = os.environ.get(
        "CHANNEL_WAM_TELEMETRY_RATE_LIMIT",
        "120 per minute",
    )
    wam_telemetry_view = app.view_functions.get("channel_wam_api.wam_telemetry")
    if wam_telemetry_view is not None:
        from foms.api.channel.channel_wam import (
            wam_telemetry_ip_rate_key,
            wam_telemetry_token_rate_key,
        )

        limited = limiter.limit(
            wam_telemetry_limit, key_func=wam_telemetry_token_rate_key
        )(wam_telemetry_view)
        limited = limiter.limit(
            wam_telemetry_limit, key_func=wam_telemetry_ip_rate_key
        )(limited)
        app.view_functions["channel_wam_api.wam_telemetry"] = limited

    # ACCOUNT-SELF-01: 셀프 가입 신청·비밀번호 재설정 요청(무인증 POST) rate limit.
    # GET(폼 표시)은 제한하지 않는다. 버킷 키는 **canonical client IP**(remote_addr,
    # PROXY-01) 고정 — 기본 rate_limit_key 는 세션 쿠키 hash 를 우선하는데 익명
    # 엔드포인트에서 쿠키는 클라이언트 임의 값이라 버킷 회전으로 우회 가능하다.
    from flask_limiter.util import get_remote_address as _account_request_rate_key

    account_request_limit = os.environ.get(
        "FOMS_ACCOUNT_REQUEST_RATE_LIMIT",
        "5 per hour;20 per day",
    )
    for endpoint in ("auth.register", "auth.password_reset_request"):
        view = app.view_functions.get(endpoint)
        if view is not None:
            app.view_functions[endpoint] = limiter.limit(
                account_request_limit,
                methods=["POST"],
                key_func=_account_request_rate_key,
            )(view)

    socketio = None
    if socketio_available:
        try:
            from flask_socketio import SocketIO as _SocketIO

            allowed_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "*").split(",")
            allowed_modes = ("threading", "eventlet", "gevent", "gevent_uwsgi")
            override = (os.environ.get("SOCKETIO_ASYNC_MODE") or "").strip().lower() or None
            mode_default = "gevent" if redis_url else "threading"
            mode = override if override in allowed_modes else mode_default

            socketio_kwargs = {
                "cors_allowed_origins": allowed_origins,
                "async_mode": mode,
                "ping_interval": 25,
                "ping_timeout": 60,
            }

            if redis_url:
                socketio_redis_url = _augment_redis_url_for_socketio(redis_url) or redis_url
                print(
                    f"[INFO] Socket.IO connecting to Redis Message Queue: {_mask_url_secret(socketio_redis_url)}"
                )
                socketio = _SocketIO(
                    app,
                    message_queue=socketio_redis_url,
                    **socketio_kwargs,
                )
                print(f"[INFO] Socket.IO initialized in {mode} mode with Redis.")
            else:
                print(
                    "[WARN] REDIS_URL not found. Socket.IO running in single-worker mode (Memory). "
                    "Procfile -w 2 사용 시 실시간 알림이 일부 사용자에게 미전달될 수 있음. REDIS_URL 설정 권장."
                )
                socketio = _SocketIO(
                    app,
                    **socketio_kwargs,
                )
                print(f"[INFO] Socket.IO initialized in {mode} mode (Universal Stable).")
        except Exception as e:
            print(f"[WARN] Socket.IO init failed: {e}")
            from flask_socketio import SocketIO as _SocketIO

            socketio = _SocketIO(app, cors_allowed_origins="*", async_mode="threading")

    if socketio_available and socketio:
        register_chat_socketio_handlers(socketio)
        app.config["SOCKETIO_AVAILABLE"] = True
        app.config["_SOCKETIO_INSTANCE"] = socketio
    else:
        app.config["SOCKETIO_AVAILABLE"] = False
        app.config["_SOCKETIO_INSTANCE"] = None

    app.config["SOCKETIO_CLIENT_ENABLED"] = (
        os.environ.get("SOCKETIO_CLIENT_ENABLED", "").lower() in ("true", "1", "yes")
    )
    app.config["SOCKETIO_ALLOW_POLLING_FALLBACK"] = (
        os.environ.get("SOCKETIO_ALLOW_POLLING_FALLBACK", "").lower()
        in ("true", "1", "yes")
    )

    return RealtimeBindings(limiter=limiter, socketio=socketio)

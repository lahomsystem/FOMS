"""앱 전역 표준 응답 헤더(RESP-HEADERS-01, 2026-10-19).

앞단이 Railway 엣지뿐이라(Cloudflare 없음) 표준 보안 헤더는 앱이 직접 붙인다.
등록은 :func:`foms.platform.http.register_http_bootstrap` 의 after_request 한 곳이다.

규칙은 **덮어쓰지 않기**(``setdefault``)다. 블루프린트 after_request 는 앱 after_request
보다 먼저 돌므로, 공유 화면의 ``Referrer-Policy: no-referrer``(``foms/api/share.py``)나
정산 CSV 의 ``nosniff`` 처럼 이미 정한 값은 그대로 남는다.

스크립트·스타일을 제한하는 CSP 본문(script-src 등)은 이번 범위가 아니다 — 인라인 스크립트와
CDN 목록 정리가 먼저다(설계서 ``docs/specs/2026-10-19-response-headers_SPEC.md`` "다음 단계").
"""

from __future__ import annotations

from typing import Any

# 채널톡 데스크(desk.channel.io) 안 iframe 으로 실리던 WAM 경로. 화면·API 는 410 으로
# 퇴역했지만(foms/api/channel/channel_wam.py) 데스크 앱 설정에 남은 WAM 주소가 여전히
# 이 경로를 열 수 있어, 퇴역 안내가 데스크 안에서 보이도록 채널톡 출처를 허용한다.
CHANNEL_FRAME_PATH_PREFIX = "/channel/wam"
CHANNEL_FRAME_ORIGINS = ("https://desk.channel.io", "https://*.channel.io")

FRAME_ANCESTORS_DEFAULT = "frame-ancestors 'self'"
FRAME_ANCESTORS_CHANNEL = "frame-ancestors 'self' " + " ".join(CHANNEL_FRAME_ORIGINS)

# 카메라: QR 스캔 getUserMedia(static/js/foms/foms-qr-scan.js). 마이크: 음성 입력
# SpeechRecognition(static/js/foms/voice-input.js, static/js/orders/foms-call-log.js).
# 위치: 현재 코드 사용처 0건이지만 현장 태블릿 용도로 self 허용(설계서 근거 표).
# 나머지는 코드 사용처 0건이라 막는다. 목록에 없는 기능(fullscreen·web-share·clipboard)은
# 브라우저 기본값(self)을 그대로 쓴다.
PERMISSIONS_POLICY = ", ".join(
    (
        "camera=(self)",
        "microphone=(self)",
        "geolocation=(self)",
        "accelerometer=()",
        "gyroscope=()",
        "magnetometer=()",
        "payment=()",
        "usb=()",
        "serial=()",
        "hid=()",
        "midi=()",
        "display-capture=()",
    )
)

REFERRER_POLICY = "strict-origin-when-cross-origin"

# 공용 도메인(*.up.railway.app)이라 includeSubDomains·preload 는 넣지 않는다.
HSTS_VALUE = "max-age=31536000"


def is_channel_frame_path(path: str) -> bool:
    """채널톡 데스크 iframe 에 실리는 경로인지 판정한다.

    Args:
        path: 요청 경로(``request.path``).

    Returns:
        ``/channel/wam`` 자체이거나 그 하위 경로면 True.
    """
    return path == CHANNEL_FRAME_PATH_PREFIX or path.startswith(CHANNEL_FRAME_PATH_PREFIX + "/")


def apply_security_headers(response: Any, path: str, *, hsts: bool) -> Any:
    """응답에 표준 보안 헤더를 붙인다. 이미 있는 헤더는 덮어쓰지 않는다.

    Args:
        response: Flask/werkzeug 응답 객체.
        path: 요청 경로 — 프레임 허용 범위를 고른다.
        hsts: 배포 환경(production·Railway)이면 True — HSTS 를 붙인다.

    Returns:
        헤더를 붙인 같은 응답 객체.
    """
    headers = response.headers
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("Referrer-Policy", REFERRER_POLICY)
    headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
    if is_channel_frame_path(path):
        # X-Frame-Options 는 출처 목록을 못 담는다(ALLOW-FROM 은 폐기) — CSP 만 둔다.
        headers.setdefault("Content-Security-Policy", FRAME_ANCESTORS_CHANNEL)
    else:
        headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        headers.setdefault("Content-Security-Policy", FRAME_ANCESTORS_DEFAULT)
    if hsts:
        headers.setdefault("Strict-Transport-Security", HSTS_VALUE)
    return response


__all__ = [
    "CHANNEL_FRAME_ORIGINS",
    "CHANNEL_FRAME_PATH_PREFIX",
    "FRAME_ANCESTORS_CHANNEL",
    "FRAME_ANCESTORS_DEFAULT",
    "HSTS_VALUE",
    "PERMISSIONS_POLICY",
    "REFERRER_POLICY",
    "apply_security_headers",
    "is_channel_frame_path",
]

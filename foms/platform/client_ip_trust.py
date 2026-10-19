"""프록시 뒤 손님 IP 신뢰 경계 (CLIENT-IP-01, 2026-10-19).

ProxyFix 는 ``X-Forwarded-For`` 를 오른쪽에서 ``FOMS_TRUSTED_PROXY_HOPS``(기본 1)번째 항목으로
``request.remote_addr`` 를 덮는다. 홉 수가 실제 프록시 체인과 다르면 ``remote_addr`` 는 손님이
아니라 중간 프록시 주소가 되고, IP 를 키로 쓰는 한도(로그인 잠금·볼륨 한도·limiter 기본 한도)가
조용히 꺼진다. 2026-10-19 스테이징에서 같은 PC 의 연속 요청이 요청마다 다른 IP 로 보였다.

이 모듈은 판정을 바꾸지 않고 세 가지만 한다(설계서
``docs/specs/2026-10-19-client-ip-behind-proxy_SPEC.md``).

1. 홉 수 해석을 한 곳에 모으고, 기동 때 적용값과 출처를 남긴다(잘못된 값은 경고).
2. ``X-Forwarded-Prefix`` 는 믿지 않는다 — Railway 가 보내지 않는 헤더라 값이 있으면 손님이 넣은 것이다.
3. ProxyFix 안쪽에서 요청마다 헤더 **모양**을 보고, 고른 IP 를 믿기 어려운 신호가 있으면 경고 로그를
   남긴다(사유 조합별로 프로세스당 10분에 1번). 로그에는 헤더 이름·항목 수·위치와 IP 앞 두 마디만
   남기고 전체 주소는 남기지 않는다. 응답과 ``remote_addr`` 는 손대지 않는다.

``X-Forwarded-Host`` 는 아직 믿는다(``x_host=1``). 쓰기 Origin 검사가 ``request.host`` 와 비교하므로
Railway 가 넘기는 ``Host`` 가 공개 도메인과 같다는 것을 경고 로그의 ``host_eq_xfh`` 로 확인한 뒤에 끈다.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import time
from collections.abc import Callable, Iterable
from typing import Any

from werkzeug.http import parse_list_header
from werkzeug.middleware.proxy_fix import ProxyFix

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_TRUSTED_PROXY_HOPS",
    "TRUSTED_PROXY_HOPS_ENV",
    "WARN_INTERVAL_SECONDS",
    "describe_forwarding",
    "log_proxy_trust_config",
    "mask_ip",
    "resolve_trusted_proxy_hops",
    "untrusted_reasons",
    "wrap_client_ip_monitor",
    "wrap_proxy_fix",
]

#: 믿을 ``X-Forwarded-For`` 홉 수 env. 실측 전 기본은 1(지금까지와 같다).
TRUSTED_PROXY_HOPS_ENV = "FOMS_TRUSTED_PROXY_HOPS"
DEFAULT_TRUSTED_PROXY_HOPS = 1

#: 같은 사유 조합의 경고를 다시 남기기까지의 간격(초). 워커 2개면 조합당 시간당 최대 12줄.
WARN_INTERVAL_SECONDS = 600.0

#: 로그에 보일 ``X-Forwarded-For`` 항목 수 상한(손님이 긴 값을 넣어도 로그 한 줄이 짧게).
_MAX_XFF_SHOWN = 4

#: 손님 IP 를 실어 나르는 것으로 알려진 헤더(+CDN 경유 표시) — 로그에는 **이름**(있음)만 남긴다.
_SHAPE_HEADERS: tuple[tuple[str, str], ...] = (
    ("HTTP_X_REAL_IP", "x-real-ip"),
    ("HTTP_FORWARDED", "forwarded"),
    ("HTTP_X_ENVOY_EXTERNAL_ADDRESS", "x-envoy-external-address"),
    ("HTTP_FASTLY_CLIENT_IP", "fastly-client-ip"),
    ("HTTP_CF_CONNECTING_IP", "cf-connecting-ip"),
    ("HTTP_TRUE_CLIENT_IP", "true-client-ip"),
    ("HTTP_CDN_LOOP", "cdn-loop"),
    ("HTTP_X_FORWARDED_HOST", "x-forwarded-host"),
    ("HTTP_X_FORWARDED_PREFIX", "x-forwarded-prefix"),
)

#: ``X-Railway-Edge``(엣지 위치 이름, IP 아님) 값에서 남길 글자.
_EDGE_UNSAFE = re.compile(r"[^A-Za-z0-9/_.\-]")
_EDGE_MAX_LEN = 48
_PATH_MAX_LEN = 80

_SPEC_PATH = "docs/specs/2026-10-19-client-ip-behind-proxy_SPEC.md"


def resolve_trusted_proxy_hops() -> tuple[int, str]:
    """``FOMS_TRUSTED_PROXY_HOPS`` 를 해석한다(지금까지의 해석 규칙 그대로 + 경고).

    :return: ``(홉 수, 출처)``. 출처는 ``default``(미설정)·``env``·``invalid``(정수 아님 → 기본값)·
        ``clamped``(음수 → 0, 프록시 불신).
    """
    raw = (os.environ.get(TRUSTED_PROXY_HOPS_ENV) or "").strip()
    if not raw:
        return DEFAULT_TRUSTED_PROXY_HOPS, "default"
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "%s=%r 를 정수로 읽지 못했다 — 기본값 %d 을 쓴다",
            TRUSTED_PROXY_HOPS_ENV, raw, DEFAULT_TRUSTED_PROXY_HOPS,
        )
        return DEFAULT_TRUSTED_PROXY_HOPS, "invalid"
    if value < 0:
        logger.warning(
            "%s=%d 는 음수라 0(어떤 프록시 헤더도 믿지 않음)으로 올린다", TRUSTED_PROXY_HOPS_ENV, value
        )
        return 0, "clamped"
    return value, "env"


def mask_ip(value: str | None) -> str:
    """IP 를 앞 두 마디만 남기고 가린다(IPv4 ``a.b.*.*``, IPv6 ``g1:g2:*``).

    :param value: IP 문자열(앞뒤 공백 허용).
    :return: 가린 값. 비어 있으면 ``-``, IP 모양이 아니면 ``invalid``.
    """
    text = (value or "").strip()
    if not text:
        return "-"
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        return "invalid"
    if addr.version == 4:
        first, second = addr.packed[0], addr.packed[1]
        return f"{first}.{second}.*.*"
    groups = addr.exploded.split(":")
    return f"{int(groups[0], 16):x}:{int(groups[1], 16):x}:*"


def _is_global_ip(value: str) -> bool:
    """공인 주소인지(사설·CGNAT·루프백·IP 모양 아님은 False).

    :param value: IP 문자열.
    :return: ``ipaddress`` 의 ``is_global`` 결과. 파싱 실패면 False.
    """
    try:
        return ipaddress.ip_address(value.strip()).is_global
    except ValueError:
        return False


def _forwarded_for(environ: dict[str, Any]) -> list[str]:
    """``X-Forwarded-For`` 항목 목록(ProxyFix 와 같은 파서).

    :param environ: WSGI environ.
    :return: 앞뒤 공백을 걷은 항목 목록. 헤더가 없으면 빈 목록.
    """
    return [item.strip() for item in parse_list_header(environ.get("HTTP_X_FORWARDED_FOR") or "")]


def untrusted_reasons(environ: dict[str, Any], hops: int) -> tuple[str, ...]:
    """ProxyFix 가 고른 IP 를 믿기 어려운 사유를 고른다(ProxyFix 를 지난 environ 기준).

    :param environ: ProxyFix 가 ``REMOTE_ADDR`` 를 덮은 뒤의 WSGI environ.
    :param hops: ProxyFix 에 준 ``x_for`` 홉 수.
    :return: 사유 튜플(순서 고정). 비어 있으면 의심 없음.
    """
    xff = _forwarded_for(environ)
    resolved = (environ.get("REMOTE_ADDR") or "").strip()
    real_ip = (environ.get("HTTP_X_REAL_IP") or "").strip()
    reasons: list[str] = []
    if hops > 0 and not xff:
        reasons.append("xff_missing")
    elif 0 < len(xff) < hops:
        reasons.append("xff_short")
    if len(xff) > hops:
        reasons.append("xff_long")
    if real_ip and real_ip != resolved:
        reasons.append("real_ip_mismatch")
    if not _is_global_ip(resolved):
        reasons.append("resolved_not_global")
    return tuple(reasons)


def _position(value: str, items: list[str]) -> str:
    """``value`` 가 ``X-Forwarded-For`` 의 몇 번째(왼쪽 0부터) 항목인지.

    :param value: 찾을 IP 문자열.
    :param items: ``X-Forwarded-For`` 항목 목록.
    :return: ``xff[i]``, 없으면 ``none``, 값이 비면 ``-``.
    """
    if not value:
        return "-"
    for index, item in enumerate(items):
        if item == value:
            return f"xff[{index}]"
    return "none"


def _host_matches_forwarded_host(environ: dict[str, Any]) -> str:
    """ProxyFix 이전 ``Host`` 와 ``X-Forwarded-Host`` 가 같은지(x_host 끄기 판단용).

    :param environ: ProxyFix 를 지난 WSGI environ(원래 값은 ``werkzeug.proxy_fix.orig``).
    :return: ``yes``/``no``, ``X-Forwarded-Host`` 가 없으면 ``-``.
    """
    forwarded_host = (environ.get("HTTP_X_FORWARDED_HOST") or "").split(",")[-1].strip().lower()
    if not forwarded_host:
        return "-"
    orig = environ.get("werkzeug.proxy_fix.orig") or {}
    host = (orig.get("HTTP_HOST") or environ.get("HTTP_HOST") or "").strip().lower()
    return "yes" if host == forwarded_host else "no"


def describe_forwarding(environ: dict[str, Any], hops: int) -> str:
    """경고 로그에 실을 헤더 모양 요약(전체 IP 없이 앞 두 마디만).

    :param environ: ProxyFix 를 지난 WSGI environ.
    :param hops: ProxyFix 에 준 ``x_for`` 홉 수.
    :return: ``key=value`` 를 공백으로 이은 한 줄.
    """
    xff = _forwarded_for(environ)
    resolved = (environ.get("REMOTE_ADDR") or "").strip()
    real_ip = (environ.get("HTTP_X_REAL_IP") or "").strip()
    orig = environ.get("werkzeug.proxy_fix.orig") or {}
    shown = ", ".join(mask_ip(item) for item in xff[:_MAX_XFF_SHOWN])
    if len(xff) > _MAX_XFF_SHOWN:
        shown += ", ..."
    edge = _EDGE_UNSAFE.sub("", environ.get("HTTP_X_RAILWAY_EDGE") or "")[:_EDGE_MAX_LEN] or "-"
    present = ",".join(name for key, name in _SHAPE_HEADERS if environ.get(key))
    path = (environ.get("PATH_INFO") or "")[:_PATH_MAX_LEN]
    return (
        f"hops={hops} xff_count={len(xff)} xff=[{shown}] "
        f"resolved={mask_ip(resolved)} resolved_pos={_position(resolved, xff)} "
        f"real_ip={mask_ip(real_ip)} real_ip_pos={_position(real_ip, xff)} "
        f"peer={mask_ip(orig.get('REMOTE_ADDR'))} host_eq_xfh={_host_matches_forwarded_host(environ)} "
        f"edge={edge} headers=[{present}] path={path}"
    )


def wrap_client_ip_monitor(
    wsgi_app: Callable[..., Iterable[bytes]],
    *,
    hops: int,
    interval: float = WARN_INTERVAL_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> Callable[..., Iterable[bytes]]:
    """ProxyFix **안쪽**에 둘 관측 미들웨어 — 의심 사유가 있으면 경고 로그(조합별 간격 제한).

    :param wsgi_app: 감쌀 WSGI 앱(ProxyFix 가 이것을 부른다).
    :param hops: ProxyFix 에 준 ``x_for`` 홉 수.
    :param interval: 같은 사유 조합을 다시 남기기까지의 초.
    :param clock: 단조 시계(테스트가 바꿔 끼운다).
    :return: 감싼 WSGI 앱. 응답·environ 은 바꾸지 않는다.
    """
    last_logged: dict[tuple[str, ...], float] = {}

    def _monitored(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        reasons = untrusted_reasons(environ, hops)
        if reasons:
            now = clock()
            previous = last_logged.get(reasons)
            if previous is None or now - previous >= interval:
                last_logged[reasons] = now
                logger.warning(
                    "client-ip 신뢰 의심: reasons=%s %s (설계서 %s)",
                    ",".join(reasons), describe_forwarding(environ, hops), _SPEC_PATH,
                )
        return wsgi_app(environ, start_response)

    return _monitored


def wrap_proxy_fix(
    wsgi_app: Callable[..., Iterable[bytes]], *, hops: int
) -> Callable[..., Iterable[bytes]]:
    """ProxyFix(+안쪽 관측 미들웨어)로 감싼다.

    :param wsgi_app: 감쌀 WSGI 앱.
    :param hops: 믿을 ``X-Forwarded-For`` 홉 수(``x_for``).
    :return: ProxyFix 로 감싼 WSGI 앱. ``x_proto=1``·``x_host=1``(보류)·``x_prefix=0``.
    """
    monitored = wrap_client_ip_monitor(wsgi_app, hops=hops)
    return ProxyFix(monitored, x_for=hops, x_proto=1, x_host=1, x_prefix=0)


def log_proxy_trust_config(hops: int, source: str) -> None:
    """기동 때 적용한 프록시 신뢰 설정을 INFO 한 줄로 남긴다.

    :param hops: 적용한 ``x_for`` 홉 수.
    :param source: :func:`resolve_trusted_proxy_hops` 의 출처 값.
    """
    origin = {
        "default": f"{TRUSTED_PROXY_HOPS_ENV} 미설정 → 기본값",
        "env": TRUSTED_PROXY_HOPS_ENV,
        "invalid": f"{TRUSTED_PROXY_HOPS_ENV} 값 오류 → 기본값",
        "clamped": f"{TRUSTED_PROXY_HOPS_ENV} 음수 → 0",
    }.get(source, source)
    logger.info("proxy trust: x_for=%d (%s) x_proto=1 x_host=1 x_prefix=0", hops, origin)

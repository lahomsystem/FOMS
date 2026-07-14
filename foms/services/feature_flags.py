"""Environment-backed feature flags and cohort rollout helpers."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from werkzeug.wrappers import Request

__all__ = [
    "env_bool",
    "env_bool_or_mobile_v2",
    "env_id_list",
    "is_cohort_all",
    "is_enabled_for_user",
    "is_mobile_v2_shell",
    "is_shell_v3_eligible",
    "prefers_mobile_wizard_client",
    "resolve_shell_variant",
    "resolve_shell_variant_cached",
    "should_render_new_order_wizard",
    "wizard_new_order_enabled",
]

_MOBILE_UA_RE = re.compile(
    r"(android|webos|iphone|ipod|blackberry|iemobile|opera mini|mobile)",
    re.IGNORECASE,
)

_TRUTHY = frozenset({"true", "1", "yes", "y", "on"})
_COHORT_ALL_TOKENS = frozenset({"all", "*"})


def env_bool(key: str, default: bool = False) -> bool:
    """Return whether an environment variable is truthy.

    Args:
        key: Environment variable name.
        default: Value used when ``key`` is unset.

    Returns:
        True when the normalized env value is one of true/1/yes/y/on.
    """
    raw = os.getenv(key, str(default))
    return raw.strip().lower() in _TRUTHY


def env_bool_or_mobile_v2(key: str, *, mobile_v2_active: bool = False) -> bool:
    """Return explicit env flag, or mobile v2 cohort when env is unset.

    P0-02~04 gap patch: cohort users see thumbnails without extra ops flags.
    Explicit ``false`` / ``0`` still disables rollout.

    Args:
        key: Environment variable name (e.g. ``FOMS_V3_DRAWING_THUMB_ENABLED``).
        mobile_v2_active: Whether ERP mobile v2 shell is active for the user.

    Returns:
        Parsed env value when set; otherwise ``mobile_v2_active``.
    """
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return mobile_v2_active
    return raw.strip().lower() in _TRUTHY


def env_id_list(key: str) -> set[int]:
    """Parse a comma-separated list of integer user ids from the environment.

    Args:
        key: Environment variable name.

    Returns:
        Set of parsed integer ids; non-numeric tokens are ignored.
    """
    raw = os.getenv(key, "")
    return {int(part) for part in raw.split(",") if part.strip().isdigit()}


def is_cohort_all(key: str) -> bool:
    """Return whether a cohort env value requests rollout to all users.

    Recognizes comma-separated tokens ``all``, ``*``, or ``ALL`` (case-insensitive
    for ``all``). Numeric ids in the same value are ignored when an all-token is
    present.

    Args:
        key: Environment variable name (e.g. ``FOMS_V3_SHELL_COHORT``).

    Returns:
        True when any comma-separated token is an all-rollout sentinel.
    """
    raw = os.getenv(key, "")
    for part in raw.split(","):
        if part.strip().lower() in _COHORT_ALL_TOKENS:
            return True
    return False


def is_enabled_for_user(
    flag: str,
    user_id: int | None = None,
    cohort_key: str | None = None,
) -> bool:
    """Check whether a flag is enabled for a specific user via cohort whitelist.

    Global flag must be truthy. Cohort may be a numeric id list, the sentinel
    ``all`` / ``*`` / ``ALL`` (case-insensitive for ``all``), or empty. When the
    cohort env is empty, the flag is treated as disabled even if the global
    switch is on.

    Args:
        flag: Flag name, with or without the ``_ENABLED`` suffix.
        user_id: Current user id, or None when unauthenticated.
        cohort_key: Optional env var name for the cohort id list. When omitted,
            ``{base}_COHORT`` is derived from ``flag``.

    Returns:
        True when the flag is on, ``user_id`` is set, and either the cohort env
        contains an all-rollout token or ``user_id`` is in the parsed id list.
    """
    enabled_key = flag if flag.endswith("_ENABLED") else f"{flag}_ENABLED"
    if not env_bool(enabled_key):
        return False
    base = flag[:-8] if flag.endswith("_ENABLED") else flag
    ck = cohort_key or f"{base}_COHORT"
    if is_cohort_all(ck):
        return user_id is not None
    cohort = env_id_list(ck)
    if not cohort:
        return False
    return user_id is not None and user_id in cohort


def _read_shell_pref_cookie(request: "Request | None" = None) -> str | None:
    """``foms_shell_pref`` 쿠키 값을 안전하게 읽는다.

    명시적으로 넘어온 ``request``가 있으면 그 쿠키를, 없으면 활성 Flask
    request context의 쿠키를 읽는다. request context가 없으면(백그라운드
    작업·테스트 등) ``None``을 반환한다. RuntimeError를 삼키지 않고
    ``has_request_context()``로 분기한다.

    Args:
        request: Flask/Werkzeug request 또는 None.

    Returns:
        쿠키 문자열(예: ``"v2"``/``"v3"``) 또는 미설정/컨텍스트 없음 시 None.
    """
    req = request
    if req is None:
        from flask import has_request_context
        from flask import request as flask_request

        if not has_request_context():
            return None
        req = flask_request
    cookies = getattr(req, "cookies", None)
    if cookies is None:
        return None
    return cookies.get("foms_shell_pref")


def resolve_shell_variant(
    user_id: int | None,
    request: "Request | None" = None,
) -> str:
    """활성 ERP 셸 variant(``legacy``/``v2``/``v3``)를 단일 기준으로 판정한다.

    2층 게이트(env 코호트 자격 + 자격자 쿠키 토글)의 SSOT(스펙 §2.3).
    v2 자격이 없으면 ``legacy``, v3 자격이 없으면 ``v2``, v3 자격자는
    쿠키 ``foms_shell_pref``가 ``"v2"``면 v2로 복귀하고 그 외/미설정이면
    기본 ``v3``이다. 쿠키를 위조해도 v3 코호트 밖이면 2단계에서 컷되어
    권한 상승은 불가능하다.

    Args:
        user_id: 현재 사용자 id(미인증 시 None).
        request: Flask/Werkzeug request 또는 None(None이면 활성 request
            context에서 쿠키를 시도, 컨텍스트 없으면 쿠키 없음 취급).

    Returns:
        ``"legacy"``, ``"v2"``, 또는 ``"v3"``.
    """
    if not is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED", user_id, cohort_key="FOMS_V3_SHELL_COHORT"
    ):
        return "legacy"
    if not is_enabled_for_user(
        "FOMS_SHELL_V3_ENABLED", user_id, cohort_key="FOMS_SHELL_V3_COHORT"
    ):
        return "v2"
    if _read_shell_pref_cookie(request) == "v2":
        return "v2"
    return "v3"


def is_shell_v3_eligible(user_id: int | None) -> bool:
    """사용자가 v3 셸 코호트 자격을 갖는지 판정한다(쿠키 무관).

    :func:`resolve_shell_variant`의 2단계 게이트(``FOMS_SHELL_V3_ENABLED`` +
    ``FOMS_SHELL_V3_COHORT``)만 평가한다. variant는 쿠키(``foms_shell_pref``)로
    v2로 복귀할 수 있으므로 자격(eligible)과 활성(variant)은 별개다. v2 셸에서
    "새 모바일(v3)로 전환" 진입점을 자격자에게만 노출하기 위한 헬퍼다.

    Args:
        user_id: 현재 사용자 id(미인증 시 None).

    Returns:
        v3 코호트 자격이 있으면 True.
    """
    return is_enabled_for_user(
        "FOMS_SHELL_V3_ENABLED", user_id, cohort_key="FOMS_SHELL_V3_COHORT"
    )


def is_mobile_v2_shell(variant: str) -> bool:
    """shell variant가 v2 셸 계열(``v2``/``v3``)인지 판정한다.

    기존 ``erp_mobile_v2_enabled`` / ``flag_mobile_v2`` boolean의 파생 계약이다.
    :func:`resolve_shell_variant`는 v2 자격이 없을 때만 ``legacy``를 돌려주므로,
    ``variant in ("v2", "v3")``는 과거
    ``is_enabled_for_user("ERP_MOBILE_V2_ENABLED", uid, "FOMS_V3_SHELL_COHORT")``
    값과 100% 동일하다(v3는 v2 자격의 부분집합).

    Args:
        variant: :func:`resolve_shell_variant` 반환값.

    Returns:
        v2 또는 v3 셸이 활성이면 True.
    """
    return variant in ("v2", "v3")


def resolve_shell_variant_cached(
    user_id: int | None,
    request: "Request | None" = None,
) -> str:
    """요청 스코프(flask.g)에 user_id별 1회 캐시된 shell variant를 반환한다.

    context_processor 3 injector와 뷰가 한 요청 안에서
    :func:`resolve_shell_variant`(env·쿠키 파싱)를 중복 호출하지 않도록
    요청당 user_id마다 1회만 계산한다. request context가 없으면(백그라운드
    작업·단위 테스트) 캐시 없이 직접 위임한다.

    Args:
        user_id: 현재 사용자 id(미인증 시 None).
        request: Flask/Werkzeug request 또는 None(None이면 활성 request
            context의 쿠키를 사용).

    Returns:
        ``"legacy"``, ``"v2"``, 또는 ``"v3"``.
    """
    from flask import g, has_request_context

    if not has_request_context():
        return resolve_shell_variant(user_id, request)
    cache = getattr(g, "_foms_shell_variant_cache", None)
    if cache is None:
        cache = {}
        g._foms_shell_variant_cache = cache
    if user_id not in cache:
        cache[user_id] = resolve_shell_variant(user_id, request)
    return cache[user_id]


def wizard_new_order_enabled(user_id: int | None = None) -> bool:
    """주문 생성 wizard(모바일 4단계) 기능 활성 여부.

    전역 ``FOMS_WIZARD_NEW_ORDER_ENABLED`` 플래그가 켜져 있거나, 사용자가 ERP
    모바일 v2 코호트에 속하면 wizard API·draft 경로를 활성화한다.
    실제 ``/add`` 렌더는 :func:`should_render_new_order_wizard`가 모바일
    클라이언트 여부까지 함께 판정한다.

    Args:
        user_id: 현재 사용자 id(미인증 시 None).

    Returns:
        wizard 기능을 켜야 하면 True.
    """
    if env_bool("FOMS_WIZARD_NEW_ORDER_ENABLED"):
        return True
    return is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED", user_id, cohort_key="FOMS_V3_SHELL_COHORT"
    )


def prefers_mobile_wizard_client(request: Request) -> bool:
    """모바일 new-order wizard 셸을 노출해야 하는 클라이언트인지 판정.

    모바일 v2 FAB·휴대폰 브라우저는 wizard로, PC 브라우저는 데스크톱
    ``add_order`` 탭 UI로 분기하기 위한 단일 기준이다.

    Args:
        request: 현재 Flask/Werkzeug request.

    Returns:
        wizard 셸을 렌더해야 하면 True.
    """
    wizard_arg = (request.args.get("wizard") or "").strip().lower()
    if wizard_arg in {"1", "true", "yes"}:
        return True
    sec_mobile = (request.headers.get("Sec-CH-UA-Mobile") or "").strip()
    if sec_mobile == "?1":
        return True
    ua = request.headers.get("User-Agent") or ""
    return _MOBILE_UA_RE.search(ua) is not None


def should_render_new_order_wizard(
    user_id: int | None,
    request: Request,
) -> bool:
    """``/add`` GET에서 wizard 셸을 렌더할지 여부.

    Args:
        user_id: 현재 사용자 id(미인증 시 None).
        request: 현재 Flask/Werkzeug request.

    Returns:
        wizard 셸을 렌더해야 하면 True.
    """
    if not wizard_new_order_enabled(user_id):
        return False
    return prefers_mobile_wizard_client(request)

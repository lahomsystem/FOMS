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
    "is_naver_workbench_enabled",
    "is_shell_v3_eligible",
    "prefers_mobile_wizard_client",
    "resolve_shell_variant",
    "resolve_shell_variant_cached",
    "should_render_new_order_wizard",
    "wants_wide_only_surfaces",
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


def wants_coarse_pointer_surfaces(request: "Request | None" = None) -> bool:
    """터치 전용(``pointer: coarse``) 표면을 이 요청에 렌더해야 하는지 판정한다.

    ``foms_ptr`` 쿠키는 pre-paint 부트(layout_head.html 인라인 + SSOT 사본
    ``static/js/runtime/foms-pointer-hint-boot.js``)가 ``matchMedia('(pointer: coarse)')``
    결과로 심는다. 마우스 기기(``fine``)에서는 시공 태블릿 작업 모드처럼 coarse 전용
    미디어쿼리로만 표시되는 표면이 **구조적으로 표시 불가능**하므로 렌더를 생략한다
    (스테이징 실측 241.8KB = 시공 fragment 의 32.4%).

    안전 폴백: 쿠키 미설정(첫 요청·쿠키 차단)이나 미지의 값이면 True — 즉 현행대로
    전부 렌더한다. 판정을 못 할 때 화면이 비는 대신 느려지기만 하도록 기울인다.

    뷰포트 폭 기반 표면(모바일 셸 ``max-width: 991.98px``)에는 쓰면 안 된다. 그쪽은
    PC 창을 좁히는 것만으로 필요해지는데 pointer 값은 그대로라 오판한다.

    Args:
        request: Flask/Werkzeug request 또는 None(활성 request context 사용).

    Returns:
        coarse 전용 표면을 렌더해야 하면 True.
    """
    req = request
    if req is None:
        from flask import has_request_context
        from flask import request as flask_request

        if not has_request_context():
            return True
        req = flask_request
    cookies = getattr(req, "cookies", None)
    if cookies is None:
        return True
    return cookies.get("foms_ptr") != "fine"


#: 광폭 전용 표면이 처음 나타나는 브레이크포인트(px). 물리 화면의 긴 변이 이 값
#: 미만인 기기는 어떤 방향으로도 해당 미디어쿼리에 도달할 수 없다.
WIDE_SURFACE_MIN_PX: int = 992


def wants_wide_only_surfaces(request: "Request | None" = None) -> bool:
    """``min-width: 992px`` 전용 표면을 이 요청에 렌더해야 하는지 판정한다.

    ``foms_scr`` 쿠키는 pre-paint 부트(layout_head.html 인라인 + SSOT 사본
    ``static/js/runtime/foms-screen-hint-boot.js``)가 ``max(screen.width,
    screen.height)``로 심는다. 긴 변이 992 미만인 기기(=폰)는 세로든 가로든
    ``min-width: 992px`` 미디어쿼리에 **구조적으로 도달할 수 없으므로**, 그 조건에서만
    보이는 데스크톱 작업 큐를 보내는 것은 순수 낭비다(스테이징 실측 주문 280.0KB ·
    시공 127.8KB · 생산 119.6KB).

    ``screen``은 기기 고정 특성이다 — 창 크기 조절로 바뀌지 않고, 회전하면 width/height
    가 서로 바뀔 뿐 최댓값은 그대로다. 그래서 :func:`wants_coarse_pointer_surfaces` 와
    같은 계열의 안전한 판정이며, 뷰포트(``innerWidth``) 기반 판정과 달리 값이 낡지 않는다.

    **768 기준 표면에는 쓰면 안 된다.** AS 데스크톱 표(``d-md-block``)는 폰 가로
    (예: 844px)에서 실제로 표시되므로 이 게이트로 스킵하면 화면이 빈다(실측 확인).

    안전 폴백: 쿠키 미설정(첫 요청·쿠키 차단)·숫자 아님·음수/0 이면 True — 현행대로
    전부 렌더한다. 판정을 못 할 때 화면이 비는 대신 느려지기만 하도록 기울인다.

    Args:
        request: Flask/Werkzeug request 또는 None(활성 request context 사용).

    Returns:
        광폭 전용 표면을 렌더해야 하면 True.
    """
    req = request
    if req is None:
        from flask import has_request_context
        from flask import request as flask_request

        if not has_request_context():
            return True
        req = flask_request
    cookies = getattr(req, "cookies", None)
    if cookies is None:
        return True
    raw = cookies.get("foms_scr")
    if not raw:
        return True
    try:
        longest_px = int(raw)
    except (TypeError, ValueError):
        return True
    if longest_px <= 0:
        return True
    return longest_px >= WIDE_SURFACE_MIN_PX


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


def is_naver_workbench_enabled(user_id: int | None) -> bool:
    """네이버 수집 워크벤치(UI 개편 본체) 자격 판정 — 2단계 게이트.

    기본 off 다. 꺼져 있으면 기존 트리아지 화면이 그대로 뜬다.

    게이트를 두는 이유는 롤백만이 아니다. 네이버 계약 테스트 79건 중 22건이 정확
    마크업을 물고 있어, 개편을 그 위에 바로 얹으면 그것들이 전부 빨개진다 — 그러면
    개편 도중 들어오는 **다른** 회귀를 감지하지 못한다. off 경로를 green 으로 남긴다.

    쿠키 토글은 두지 않는다(관리자 화면이라 코호트만으로 충분하고, 표면을 늘리지 않는다).

    Args:
        user_id: 현재 사용자 id(미인증 시 None).

    Returns:
        워크벤치를 보여줄 자격이 있으면 True.
    """
    return is_enabled_for_user(
        "FOMS_NAVER_WORKBENCH_ENABLED", user_id, cohort_key="FOMS_NAVER_WORKBENCH_COHORT"
    )


def is_naver_bulk_dispatch_enabled() -> bool:
    """네이버 **일괄 발송처리 실행**이 켜져 있나 (NAVER-BULKDISPATCH-01 T4).

    **코호트를 쓰지 않는다 — 전역 킬스위치 하나뿐이다.** 워크벤치 게이트
    (:func:`is_naver_workbench_enabled`)는 user-id 코호트라, 그걸 재사용하면 코호트 밖
    실측 담당자에게 실행 라우트가 403 이 된다. 진입점이 두 곳(워크벤치·실측 대시보드)인
    기능에서 한쪽을 조용히 죽이는 게이트는 쓸 수 없다.

    누가 누를 수 있는지는 **롤**이 정한다(ADMIN·MANAGER). 이 스위치의 일은 "기능 자체를
    당장 끌 수 있는가" 하나다 — 되돌릴 수 없는 조작이라 그 손잡이가 필요하다.

    기본값은 **꺼짐**이다. 켜려면 Railway 에 ``FOMS_NAVER_BULK_DISPATCH_ENABLED=1``.

    Returns:
        켜져 있으면 True.
    """
    return env_bool("FOMS_NAVER_BULK_DISPATCH_ENABLED")


def is_naver_return_reject_enabled() -> bool:
    """네이버 **반품 거부**가 켜져 있나 (T8-S3).

    **env 기본값은 꺼짐, 운영은 켜져 있다.** 2026-09-01 에 규격이 확인돼
    ``client.reject_return_product_order`` 가 열렸다(설계서 §2, 공개 문서 원문). 그전까지
    이 스위치가 닫고 있던 것은 "화면은 다 있는데 네이버로 나가는 한 줄만 비어 있는" 상태였다
    — 그 상태로 버튼이 보이면 담당자가 눌러 놓고 안 나간 줄 모른다.

    **운영은 2026-09-01 에 켰다**(web 재배포 ``09aeca29``). 남은 것은 관리자가 화면에서
    상용구 문장을 확정하는 일뿐이다 — 코드 5종은 아무도 저장하지 않았을 때의 기본값이다.

    **이 스위치는 web 전용이다.** 읽는 곳은 ``foms/web/admin/naver_ingest.py`` 두 곳
    (pane 재진술·라우트 가드)뿐이고, 워커의 ``run_naver_fulfillment_task`` 는 게이트를 보지
    않는다(큐에 들어온 일은 이미 라우트가 통과시킨 것이다). **``WORKER`` 에 변수를 넣거나
    재배포하지 마라** — worker 는 1 대라 재배포가 큐를 전면 정지시킨다.

    켤 때: 변수만 넣으면 **안 켜진다**. 실행 중 프로세스는 옛 env 를 들기 때문에, 재배포한
    컨테이너의 부팅 시각이 변수 등록보다 뒤라는 것을 확인한 뒤에만 "켜졌다"고 말한다.

    **거부는 불가역이고 문장이 구매자에게 그대로 간다.** 그래서 남은 관문은 상용구 문장
    확정이다 — 코드 기본 5종은 **법률 검토를 거친 문안이 아니다**(설계서 §7 Q1).

    코호트를 쓰지 않는 이유는 일괄 발송처리와 같다 — 이 스위치의 일은 "기능 자체를 당장
    끌 수 있는가" 하나이고, 누가 누를 수 있는지는 **롤**(ADMIN·MANAGER)이 정한다.

    Returns:
        켜져 있으면 True.
    """
    return env_bool("FOMS_NAVER_RETURN_REJECT_ENABLED")


def is_naver_cancel_approve_enabled() -> bool:
    """네이버 **취소 요청 승인**이 켜져 있나 (T9-G1).

    **기본값은 꺼짐.** 켜려면 Railway ``web`` 에 ``FOMS_NAVER_CANCEL_APPROVE_ENABLED=1``.

    **승인하면 환불이 확정되고 되돌리는 엔드포인트가 없다.** 취소를 **거절**하는 API 는
    아예 존재하지 않는다(철회는 구매자만 한다) — 잘못 눌러도 되돌릴 곳이 없다. 그래서
    반품 승인과 **게이트를 따로 판다**: 진짜 클레임 1건에서 이쪽을 먼저 켜 성공을 확인한
    뒤에 반품 승인을 켠다. 하나로 묶으면 첫 실호출이 두 배선의 동시 검증이 되어, 실패했을
    때 어느 쪽이 틀렸는지 안 갈린다.

    **이 스위치는 web 전용이다.** 읽는 곳은 ``foms/web/admin/naver_ingest.py`` 두 곳
    (pane 재진술·라우트 가드)뿐이고, 워커의 ``run_naver_fulfillment_task`` 는 게이트를 보지
    않는다(큐에 들어온 일은 이미 라우트가 통과시킨 것이다). **``WORKER`` 에 변수를 넣거나
    재배포하지 마라** — worker 는 1 대라 재배포가 큐를 전면 정지시킨다.

    켤 때: 변수만 넣으면 **안 켜진다**. 실행 중 프로세스는 옛 env 를 들기 때문에, 재배포한
    컨테이너의 부팅 시각이 변수 등록보다 뒤라는 것을 확인한 뒤에만 "켜졌다"고 말한다.

    코호트를 쓰지 않는 이유는 반품 거부와 같다 — 이 스위치의 일은 "기능 자체를 당장 끌 수
    있는가" 하나이고, 누가 누를 수 있는지는 **롤**(ADMIN·MANAGER)이 정한다.

    Returns:
        켜져 있으면 True.
    """
    return env_bool("FOMS_NAVER_CANCEL_APPROVE_ENABLED")


def is_naver_return_approve_enabled() -> bool:
    """네이버 **반품 승인 독립 버튼**이 켜져 있나 (T9-G2).

    **기본값은 꺼짐.** 켜려면 Railway ``web`` 에 ``FOMS_NAVER_RETURN_APPROVE_ENABLED=1``.

    **이 스위치는 독립 버튼만 연다.** 반품 접수 모달의 ``승인까지 한 번에`` 체크박스
    (T8-S2, 운영 배포 완료)는 이 게이트와 **무관하게** 지금처럼 동작한다 — 이미 나가 있는
    경로를 이 작업이 끄지 않는다.

    독립 버튼이 필요한 이유는 비대칭이다: 고객이 먼저 낸 반품 앞에서 화면이 내주는 불가역
    버튼이 ``반품 거부`` 하나뿐이었다. 승인 버튼이 없어서 담당자가 거부를 누르게 되는
    구조를 방치할 수 없다.

    web 전용·worker 무변경·부팅 시각 확인 규율은 :func:`is_naver_cancel_approve_enabled`
    와 같다.

    Returns:
        켜져 있으면 True.
    """
    return env_bool("FOMS_NAVER_RETURN_APPROVE_ENABLED")


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

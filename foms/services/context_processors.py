"""Flask context processors and template filters."""

from __future__ import annotations

import json
import os
import time
from collections import namedtuple
from typing import Any

from flask import g, request, session, url_for

from foms.services.feature_flags import (
    env_bool,
    env_bool_or_mobile_v2,
    is_mobile_v2_shell,
    is_naver_workbench_enabled,
    is_shell_v3_eligible,
    resolve_shell_variant_cached,
    should_render_new_order_wizard,
    wants_coarse_pointer_surfaces,
    wants_wide_only_surfaces,
    wizard_new_order_enabled,
)
from foms.services.datetime_kst import format_datetime_kst
from foms.services.dashboard_counts import get_nav_badge_counts
from foms.services.integrations.naver_commerce.triage_count import get_triage_pending_count
from foms.services.common.erp_mine_filter import erp_mine_only_from_request
from foms.services.common.geocode_config import KAKAO_JS_API_KEY
from foms.web.auth import ROLES
from foms.services.orders.status_constants import BULK_ACTION_STATUS, STATUS
from foms.persistence.main.db import get_db
from foms.persistence.main.models import User
from foms.services.menu_config import load_menu_config

__all__ = [
    "parse_json_string_filter",
    "parse_json_string",
    "inject_statuses",
    "inject_status_list",
    "utility_processor",
    "inject_menu",
    "inject_foms_flags",
    "inject_foms_nav_badges",
    "inject_foms_stage_catalog",
    "register_context_processors",
]


# ADMIN "다른 사용자로 전환" 드롭다운 유저 목록 마이크로 캐시.
# inject_status_list는 ADMIN이 여는 모든 전체페이지 렌더마다 활성 유저 전체를 조회했다.
# 목록은 거의 불변이므로 프로세스별 60s 캐시로 매 렌더 쿼리를 제거한다(멀티프로세스 각자
# 최대 60s stale 수용 — 관리자 드롭다운 특성상 안전).
_ADMIN_SWITCH_USERS_TTL_SEC = 60.0
_ADMIN_SWITCH_USERS_CACHE: dict[str, Any] = {"ts": 0.0, "users": []}

# 세션 밖(detached) lazy-load 회피용 경량 객체. 템플릿(layout_nav.html)이 참조하는
# u.id / u.name / u.username 3필드만 담는다. ORM User를 그대로 캐시하면 세션 만료 후
# 템플릿 접근 시 DetachedInstanceError가 나므로 반드시 이 형태로 변환해 캐시한다.
AdminSwitchUser = namedtuple("AdminSwitchUser", "id name username")


def _get_admin_switch_users(db: Any, current_user_id: Any) -> list[AdminSwitchUser]:
    """ADMIN 전환 드롭다운용 활성 유저 목록(자기 제외)을 캐시 경유로 반환한다.

    캐시는 자기 제외를 적용하지 않은 전체 활성 유저(모든 ADMIN 뷰어 공통)를 담아
    캐시 1개를 모든 관리자가 공유한다. 자기 제외(id != current_user_id)는 캐시 반환 후
    파이썬 필터로 적용해 뷰어별 캐시 분기를 없앤다. order_by(name)은 캐시 시점에 적용.

    Args:
        db: 활성 DB 세션.
        current_user_id: 결과에서 제외할 현재 사용자 id.

    Returns:
        detached-safe 경량 객체 리스트(id/name/username 접근 가능).
    """
    now = time.time()
    cache = _ADMIN_SWITCH_USERS_CACHE
    if now - cache["ts"] < _ADMIN_SWITCH_USERS_TTL_SEC:
        cached_users = cache["users"]
    else:
        rows = (
            db.query(User.id, User.name, User.username)
            .filter(User.is_active == True)  # noqa: E712 (SQL boolean, not Python identity)
            .order_by(User.name)
            .all()
        )
        cached_users = [AdminSwitchUser(r.id, r.name, r.username) for r in rows]
        cache["users"] = cached_users
        cache["ts"] = now
    return [u for u in cached_users if u.id != current_user_id]


def parse_json_string_filter(value: Any) -> Any:
    """Template filter: parse JSON-like strings, fallback to {} on failure."""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return {}


def parse_json_string(json_string: str | None) -> Any | None:
    """Template helper: parse json_string, fallback to None on failure."""
    if not json_string:
        return None
    try:
        return json.loads(json_string)
    except json.JSONDecodeError:
        return None


def inject_statuses() -> dict[str, Any]:
    """Inject status constants."""
    return {
        "ALL_STATUS": STATUS,
        "BULK_ACTION_STATUS": BULK_ACTION_STATUS,
    }


def _current_shell_variant() -> str:
    """현재 요청 사용자의 shell variant를 요청당 1회 캐시로 반환한다.

    ``g.current_user``에서 uid를 파생해 :func:`resolve_shell_variant_cached`에
    위임한다. 3개 injector가 공유하는 단일 진입점으로, 요청당 env·쿠키 파싱을
    1회로 줄여 중복 계산을 제거한다.

    Returns:
        ``"legacy"``, ``"v2"``, 또는 ``"v3"``.
    """
    current_user = getattr(g, "current_user", None)
    uid = current_user.id if current_user else None
    return resolve_shell_variant_cached(uid, request)


def inject_status_list() -> dict[str, Any]:
    """Inject status lists and current-user context into templates."""
    display_status = {k: v for k, v in STATUS.items() if k != "DELETED"}
    bulk_action_status = {k: v for k, v in STATUS.items() if k != "DELETED"}
    current_user = getattr(g, "current_user", None)

    admin_switch_users: list[AdminSwitchUser] = []
    impersonating_from_id = session.get("impersonating_from")
    # 수집 확인 대기 뱃지: 트리아지 화면을 쓸 수 있는 역할(T14-A 전 직원 개방)에만 계산.
    # VIEWER 는 화면 접근이 막혀 있으므로 쿼리를 내지 않는다. 30초 전역 캐시라
    # 역할이 늘어도 nav 렌더 비용은 그대로다.
    # 모집단은 **그 사람이 링크를 눌렀을 때 볼 목록**과 같아야 한다 — 워크벤치 v3 게이트가
    # 켜졌으면 처리 탭 목록(확인 큐 ∪ 발주확인 전), 아니면 옛 확인 대기 큐(v3 계약 §6).
    naver_triage_pending = 0
    if current_user:
        db = get_db()
        if current_user.role == "ADMIN":
            admin_switch_users = _get_admin_switch_users(db, current_user.id)
        if current_user.role in ("ADMIN", "MANAGER", "STAFF"):
            naver_triage_pending = get_triage_pending_count(
                db, workbench=is_naver_workbench_enabled(current_user.id))

    erp_order_enabled = env_bool("ERP_ORDER_ENABLED", default=True)
    shell_variant = _current_shell_variant()
    erp_mobile_v2_enabled = is_mobile_v2_shell(shell_variant)
    use_direct_upload_env = env_bool("USE_DIRECT_UPLOAD", default=True)
    try:
        from foms.services.storage import get_storage

        storage = get_storage()
        use_direct_upload = use_direct_upload_env and storage.storage_type in ("r2", "s3")
    except Exception:
        use_direct_upload = False

    return {
        "STATUS": display_status,
        "BULK_ACTION_STATUS": bulk_action_status,
        "ALL_STATUS": STATUS,
        "ROLES": ROLES,
        "current_user": current_user,
        "admin_switch_users": admin_switch_users,
        "impersonating_from_id": impersonating_from_id,
        "naver_triage_pending": naver_triage_pending,
        "erp_order_enabled": erp_order_enabled,
        "erp_mobile_v2_enabled": erp_mobile_v2_enabled,
        "coarse_pointer_surfaces": wants_coarse_pointer_surfaces(),
        "wide_only_surfaces": wants_wide_only_surfaces(),
        "shell_variant": shell_variant,
        "use_direct_upload": use_direct_upload,
    }


def utility_processor() -> dict[str, Any]:
    """Inject small template utility helpers."""
    return {"parse_json_string": parse_json_string}


def inject_menu() -> dict[str, Any]:
    """Inject menu config, narrowing the construction-team navigation."""
    menu = load_menu_config()
    if isinstance(menu, dict):
        user = getattr(g, "current_user", None)
        if user and getattr(user, "team", None) == "CONSTRUCTION":
            menu = dict(menu)
            menu["main_menu"] = [
                {
                    "id": "shipment",
                    "name": "출고",
                    "url": url_for("erp_shipment_page.erp_shipment_dashboard"),
                },
                {
                    "id": "construction",
                    "name": "시공",
                    "url": url_for("erp_construction_page.erp_construction_dashboard"),
                },
                {
                    "id": "completion",
                    "name": "완료",
                    "url": url_for("erp_completion_page.erp_completion_dashboard"),
                },
                {
                    "id": "history",
                    "name": "이력",
                    "url": url_for("erp_history.history_dashboard"),
                },
            ]
    return {"menu": menu}


def inject_foms_flags() -> dict[str, Any]:
    """Inject v1.1 design feature flags for template cohort rollout."""
    current_user = getattr(g, "current_user", None)
    uid = current_user.id if current_user else None
    shell_variant = _current_shell_variant()
    mobile_v2 = is_mobile_v2_shell(shell_variant)
    split_flag = env_bool_or_mobile_v2(
        "FOMS_TABLET_SPLIT_VIEW_ENABLED",
        mobile_v2_active=mobile_v2,
    )
    show_new_order_wizard = (
        request.endpoint == "order_pages.add_order"
        and should_render_new_order_wizard(uid, request)
    )
    return {
        "flag_mobile_v2": mobile_v2,
        "shell_variant": shell_variant,
        # v3 셸 코호트 자격(쿠키 무관). v2 셸 drawer의 "새 모바일(v3)" 진입점을
        # 자격자에게만 노출하기 위한 플래그(shell_variant=='v2' && shell_v3_eligible).
        "shell_v3_eligible": is_shell_v3_eligible(uid),
        "flag_tokens_v2": env_bool("FOMS_DESIGN_TOKENS_V2_ENABLED", True),
        # wizard draft/API 활성(코호트·전역 플래그). 실제 /add 렌더·chrome 숨김은 show_new_order_wizard.
        "flag_wizard": wizard_new_order_enabled(uid),
        "show_new_order_wizard": show_new_order_wizard,
        "flag_inline": env_bool("FOMS_INLINE_EDIT_ENABLED"),
        # 현장 스펙 피커(ERP order 항목 ▾ 선택 UI + 저장 스냅샷). 기본 on,
        # 비활성화하려면 FOMS_ERP_SPEC_PICKER_ENABLED=false.
        # (2026-08-04 자동 가격계산 제거로 개명 — 구 FOMS_ERP_SPEC_CALC_ENABLED는
        #  기존 배포 환경변수 호환을 위해 fallback으로만 읽는다.)
        "flag_spec_picker": env_bool(
            "FOMS_ERP_SPEC_PICKER_ENABLED",
            env_bool("FOMS_ERP_SPEC_CALC_ENABLED", True),
        ),
        "flag_split_view": split_flag,
        # split 셸 마크업은 v2 셸 전용: 그 스타일(foms-split-view.css 기본 은닉 포함)이
        # v2 전용 surfaces 번들(layout_head shell_variant=='v2' 게이트)로만 로드되므로,
        # v2∪v3(mobile_v2)로 렌더하면 v3에서 비스타일 split 마크업이 전 폭에 그대로
        # 흐른다(2026-07-12 staging 이중 레일 실사고 — 마크업↔CSS 게이트 불일치 봉합).
        "foms_split_enabled": shell_variant == "v2" and split_flag,
        "flag_rum_baseline": env_bool("FOMS_RUM_BASELINE_ENABLED", True),
        "flag_offline_sw": env_bool("FOMS_OFFLINE_SW_ENABLED"),
        "flag_bottom_nav_htmx": env_bool("FOMS_BOTTOM_NAV_HTMX_ENABLED"),
        # 고객 공유 모달 카톡 공유(Kakao JS SDK v2) 키. 공유 전용 앱을 분리하면
        # KAKAO_SHARE_JS_KEY 로 덮어쓰고, 기본은 지도와 같은 앱 키(스펙 §5 사용자
        # 확인 대기 — 도메인 등록 전에는 SDK init 이 실패하고 버튼이 비활성으로 표면화).
        "foms_kakao_share_js_key": os.environ.get("KAKAO_SHARE_JS_KEY", "")
        or KAKAO_JS_API_KEY,
    }


def inject_foms_nav_badges() -> dict[str, Any]:
    """Inject bottom-nav stage badge counts (P1-01, ERP mobile v2 cohort only)."""
    current_user = getattr(g, "current_user", None)
    if not is_mobile_v2_shell(_current_shell_variant()):
        return {"foms_nav_badges": {}}
    request_mine = erp_mine_only_from_request(request)
    return {
        "foms_nav_badges": get_nav_badge_counts(
            current_user,
            mine_only=True if request_mine else None,
        )
    }


_FOMS_STAGE_CATALOG: list[dict[str, str]] | None = None


def _foms_stage_catalog() -> list[dict[str, str]]:
    """8단계 워크플로 카탈로그(code+label, 진행 순서)를 1회 빌드 후 캐시해 반환한다.

    순서·표시명 SSOT 는 :data:`foms.services.order_timeline_v3.STAGE_SEQUENCE`
    (RECEIVED→MEASURE→…→COMPLETED). 태블릿 사이드 시트 파이프라인이 소비하며, JS 에
    단계 목록을 하드코딩하지 않도록 서버에서 data-* 속성으로 내려보낸다. 상수라 모듈
    수명 내 1회만 빌드한다(요청마다 재계산 없음).

    Returns:
        ``[{"code": <표준 코드>, "label": <한글 표시명>}, ...]`` 8원소.
    """
    global _FOMS_STAGE_CATALOG
    if _FOMS_STAGE_CATALOG is None:
        # Lazy import: order_timeline_v3 는 datetime_kst 만 끌어와 경량이지만, bootstrap
        # import 순서 리스크를 원천 차단하려 요청 시점(첫 렌더)에 로드한다.
        from foms.services.order_timeline_v3 import STAGE_SEQUENCE

        _FOMS_STAGE_CATALOG = [
            {"code": code, "label": label} for code, label, _slug in STAGE_SEQUENCE
        ]
    return _FOMS_STAGE_CATALOG


def inject_foms_stage_catalog() -> dict[str, Any]:
    """Inject the 8-stage workflow catalog for the tablet side-sheet pipeline.

    Returns the cached ``foms_stage_catalog`` list (no query, no per-request compute);
    templates serialize it via ``|tojson`` into ``data-foms-stage-catalog``.
    """
    return {"foms_stage_catalog": _foms_stage_catalog()}


def _tablet_rail_items() -> list[dict[str, Any]]:
    """Lazy rail-item provider bound to the current request (Jinja global body).

    Reads the request-scoped user (``g.current_user``) and ``request.path`` at call
    time so the tablet rail partial computes items only when it actually renders
    (non-/erp and non-tablet pages never invoke it). Delegates all navigation policy
    to :func:`foms.services.foms_split_view.build_tablet_rail_items`.

    Returns:
        Rail item descriptors for the current request.
    """
    # Lazy import: foms_split_view pulls the erp_display/erp_policy chain, which is not
    # yet initialized when context_processors is imported during early app bootstrap
    # (circular import). Importing here (request time) breaks the cycle — same pattern
    # as the canonical lazy storage import in inject_status_list.
    from foms.services.foms_split_view import build_tablet_rail_items

    current_user = getattr(g, "current_user", None)
    return build_tablet_rail_items(current_user, request.path)


def inject_tablet_rail_helper() -> dict[str, Any]:
    """Expose ``foms_tablet_rail_items`` as a lazy Jinja global (T2 tablet rail).

    Returns the callable itself (not its computed result) so the tablet rail partial
    invokes it only when rendered; pages that never include the partial pay no cost.

    Returns:
        Mapping with the ``foms_tablet_rail_items`` template callable.
    """
    return {"foms_tablet_rail_items": _tablet_rail_items}


def register_context_processors(app) -> None:
    """Register all template filters and context processors on the Flask app."""
    app.add_template_filter(parse_json_string_filter, "parse_json_string")
    app.add_template_filter(format_datetime_kst, "format_datetime_kst")
    app.context_processor(inject_statuses)
    app.context_processor(inject_status_list)
    app.context_processor(utility_processor)
    app.context_processor(inject_menu)
    app.context_processor(inject_foms_flags)
    app.context_processor(inject_foms_nav_badges)
    app.context_processor(inject_foms_stage_catalog)
    app.context_processor(inject_tablet_rail_helper)

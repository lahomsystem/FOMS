"""PARTNER-01: 외부 협력사 계정의 접근 범위(문지기 허용 목록 · 판정 함수).

협력사 계정(``users.role == 'PARTNER'``)은 **허용 목록에 있는 endpoint 만** 쓸 수 있다.
나머지는 문지기(:func:`partner_gate`, :func:`foms.platform.http.register_http_bootstrap` 가 등록)가
막는다 — 기존 라우트 수백 개는 ``@login_required`` 만 보고 모든 주문을 열어 주기 때문에,
라우트를 하나씩 고치는 대신 기본 거부로 간다. 새 라우트가 생겨도 저절로 막힌다.

허용 목록은 URL 접두어가 아니라 **endpoint 이름**이다. 접두어는 새 라우트가 우연히 같은
접두어로 생길 때 뚫린다. 허용한 endpoint 는 안에서 주문 단위 판정(``user_can_read_order``)을
다시 해야 한다 — ``tests/security/test_partner_gate.py`` 가 둘 다 강제한다.

스펙: docs/specs/2026-10-08-partner-portal_SPEC.md §4
"""
from __future__ import annotations

from typing import Any

from models import PARTNER_ROLE

# 협력사 세션이 쓸 수 있는 endpoint.
# * 파일 관문 3종은 안에서 ``_deny_file_access`` → ``user_can_read_order`` 로 주문 단위 판정을 한다.
# * 협력사 화면·API(``partner_portal.*``·``partner_api.*``)는 ``partner_required`` + 주문마다
#   ``partner_can_read_order`` 로 다시 판정한다.
# 로그인 화면은 넣지 않는다 — 공용 레이아웃이 내부 메뉴·단계 배지 수를 그린다. 로그인된 협력사가
# 다른 화면을 열면 협력사 첫 화면으로 보낸다.
PARTNER_ALLOWED_ENDPOINTS: frozenset[str] = frozenset({
    "static",
    "auth.logout",
    # 관리자가 협력사 계정으로 들어가 본 뒤 자기 계정으로 돌아오는 길(라우트가 직접 판정).
    "auth.switch_back",
    "files.view",
    "files.presigned_urls",
    "files.download",
    "partner_portal.home",
    "partner_portal.new_order",
    "partner_portal.order_detail",
    "partner_api.create_order",
    "partner_api.upload_file",
})

# 쓰기 정책 엔진(``evaluate_policy``)이 협력사 계정에 허용하는 policy_id. 문지기를 지난 쓰기 요청도
# 이 엔진을 한 번 더 지난다(운영에서만 켜짐 — ``AUTH_POLICY_ENABLED``). 로그아웃·관리자
# 복귀(ACCOUNT_SELF), 로그인 전 단계(ACCOUNT_ANON), 협력사 화면 쓰기(PARTNER_PORTAL).
PARTNER_ALLOWED_POLICIES: frozenset[str] = frozenset({"ACCOUNT_SELF", "ACCOUNT_ANON", "PARTNER_PORTAL"})


# 협력사 주문의 ``structured_data['source']`` 값(네이버의 ``NAVER_SMARTSTORE`` 와 같은 자리).
# 판정의 정본은 ``orders.partner_org_id`` 다 — sd 값은 주문 행이 아직 없는 경로(초안 발송)와
# 화면 표시용이다.
PARTNER_SOURCE_MARKER = "PARTNER"


def is_partner_sd(sd: Any) -> bool:
    """structured_data 가 협력사 주문의 것인가."""
    return isinstance(sd, dict) and sd.get("source") == PARTNER_SOURCE_MARKER


def is_partner_order(order: Any) -> bool:
    """협력사 주문인가 — ``partner_org_id`` 칸이 정본, sd 표식은 보조."""
    if order is None:
        return False
    if getattr(order, "partner_org_id", None) is not None:
        return True
    return is_partner_sd(getattr(order, "structured_data", None))


def partner_mark_name(order: Any, sd: Any = None) -> str | None:
    """직원 화면 "협력사" 표식에 쓸 이름 — 협력사 주문이 아니면 ``None``(추가 쿼리 없음).

    등록 때 발주사 칸에 협력사 이름을 넣으므로 그 값을 읽는다(판정은 ``partner_org_id``).
    """
    sd = sd if isinstance(sd, dict) else (getattr(order, "structured_data", None) or {})
    if getattr(order, "partner_org_id", None) is None and not is_partner_sd(sd):
        return None
    orderer = ((sd.get("parties") or {}).get("orderer") or {}) if isinstance(sd, dict) else {}
    return (orderer.get("name") or "").strip() or "협력사"


def is_partner_user(user: Any) -> bool:
    """협력사 계정인가. role 대소문자는 가리지 않는다(다른 판정과 같은 정규화)."""
    if user is None:
        return False
    return (getattr(user, "role", None) or "").strip().upper() == PARTNER_ROLE


def partner_can_read_order(user: Any, order: Any) -> bool:
    """협력사 계정이 이 주문을 읽을 수 있나 — 같은 협력사 주문일 때만.

    소속 협력사가 없는 협력사 계정(DB 제약상 생길 수 없지만)과 주문 없음은 거부한다.
    """
    org_id = getattr(user, "partner_org_id", None)
    if org_id is None or order is None:
        return False
    return getattr(order, "partner_org_id", None) == org_id


def is_partner_endpoint_allowed(endpoint: str | None) -> bool:
    """문지기 허용 목록 판정. endpoint 가 없으면(404 등) 거부한다."""
    return bool(endpoint) and endpoint in PARTNER_ALLOWED_ENDPOINTS


_DENIED_MSG = "협력사 계정으로는 이 화면을 쓸 수 없습니다."


def _wants_json(path: str) -> bool:
    """API 네임스페이스(``/api/``·``/erp/api/`` 등)는 302 가 아니라 JSON 이어야 한다(기존 불변식 P1-13/P1-18)."""
    return "/api/" in path


def partner_gate() -> Any | None:
    """``before_request`` 문지기 — 협력사 세션이면 허용 목록 밖을 막는다.

    ``_set_current_user`` 뒤에 등록돼야 한다(``g.current_user`` 를 읽는다).

    Returns:
        막을 때 응답, 통과면 ``None``.
    """
    from flask import g, jsonify, redirect, request, session, url_for

    user = getattr(g, "current_user", None)
    if not is_partner_user(user):
        return None

    from db import get_db
    from models import PartnerOrg

    org_id = getattr(user, "partner_org_id", None)
    org = get_db().query(PartnerOrg).filter(PartnerOrg.id == org_id).first() if org_id else None
    if org is None or not org.is_active:
        # 꺼진 협력사(또는 소속 없음) — 세션을 끊는다. 로그인 화면 자체는 열어 둔다.
        session.clear()
        g.current_user = None
        if request.endpoint in ("static", "auth.login"):
            return None
        if _wants_json(request.path or ""):
            return jsonify({"success": False, "data": None, "error": "로그인이 필요합니다."}), 401
        return redirect(url_for("auth.login"))

    if is_partner_endpoint_allowed(request.endpoint):
        return None

    path = request.path or ""
    if _wants_json(path) or request.method not in ("GET", "HEAD"):
        return jsonify({"success": False, "data": None, "error": _DENIED_MSG}), 403
    return redirect(url_for("partner_portal.home"))


def partner_required(view):
    """협력사 화면 · API 전용 데코레이터 — 활성 협력사 계정만 통과한다(우리 직원도 거부).

    로그인 안 됨: 화면은 로그인으로, API 는 401. 협력사가 아님: 403(우리 직원이 협력사 화면을
    열 일은 없다 — 관리자는 ``/switch-user`` 로 협력사 계정이 되어 본다).
    """
    from functools import wraps

    @wraps(view)
    def wrapper(*args, **kwargs):
        from flask import g, jsonify, redirect, request, url_for

        user = getattr(g, "current_user", None)
        wants_json = _wants_json(request.path or "")
        if user is None or getattr(user, "is_active", None) is False:
            if wants_json:
                return jsonify({"success": False, "data": None, "error": "로그인이 필요합니다."}), 401
            return redirect(url_for("auth.login"))
        if not is_partner_user(user) or getattr(user, "partner_org_id", None) is None:
            if wants_json:
                return jsonify({"success": False, "data": None, "error": "협력사 계정 전용입니다."}), 403
            return "협력사 계정 전용 화면입니다.", 403
        return view(*args, **kwargs)

    return wrapper

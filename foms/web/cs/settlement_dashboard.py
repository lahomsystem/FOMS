"""정산 대시보드 페이지 — SETTLE-DASH-01 M2 (읽기 전용 서버 렌더 셸).

스펙: ``docs/specs/2026-08-31-settlement-dashboard_SPEC.md`` §5·§6.

집계 커널은 :mod:`foms.services.settlement_aggregation` (M1) 이고, 이 모듈은 그 위의
HTML 진입점만 소유한다. 화면 내용(차트·KPI 카드·CSS/JS)은 M3 몫이라 템플릿은 스텁이다.

**권한(§5)**: ``enforce_order_mutation_policy`` 의 ``_WRITE_METHODS`` 는 POST/PUT/PATCH/
DELETE 뿐이라 **GET 은 before_request 가드에 도달하지 않는다.** 그래서 이 핸들러가
:func:`can_view_settlement_dashboard` 로 직접 판정한다. ``@login_required`` 는 그대로
유지해 미인증은 로그인 리다이렉트로 보낸다.

이 모듈은 읽기 전용이다 — 커밋·flag_modified·Order 속성 대입을 하지 않는다.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, g, make_response, render_template, request

from foms.services.common.erp_shell_http import (
    apply_erp_shell_fragment_headers,
    wants_erp_shell_tab_body,
)
from foms.services.orders.order_mutation_policy import user_can
from foms.web.auth import login_required

#: 정산 대시보드 열람 정책 id — 페이지·API·템플릿이 **이 상수 하나**를 공유한다.
#: ``user_can`` 은 미등록 policy_id 에 조용히 ``False`` 를 주므로 문자열을 여러 곳에 적으면
#: 오타가 "아무도 못 보는 화면"으로 조용히 끝난다(어떤 게이트도 red 로 잡지 않는다).
SETTLEMENT_DASHBOARD_POLICY_ID = "SETTLEMENT_DASHBOARD_READ"

erp_settlement_page_bp = Blueprint(
    'erp_settlement_page',
    __name__,
    url_prefix='/erp',
)


def can_view_settlement_dashboard(user: Any) -> bool:
    """사용자가 정산 대시보드를 열람할 수 있는지(§5 정책 판정 단일 진입점).

    허용 집합은 ``FINANCE_MUTATION`` 과 같다: ADMIN / MANAGER / STAFF+CS / STAFF+SALES.
    VIEWER 와 그 밖의 STAFF 팀(PRODUCTION/DRAWING/CONSTRUCTION/SHIPMENT)은 거부다.

    Args:
        user: 현재 사용자(``None`` 이면 미인증 — ``False``).

    Returns:
        열람 가능하면 True.
    """
    return user_can(SETTLEMENT_DASHBOARD_POLICY_ID, user)


@erp_settlement_page_bp.route('/settlement')
@login_required
def erp_settlement_dashboard():
    """정산 대시보드 셸(``GET /erp/settlement``).

    ERP 셸 탭 요청이면 body partial 만, 직접 GET/새로고침이면 전체 문서를 낸다(완료
    대시보드와 같은 분기·같은 헤더 처리). 데이터는 화면에서
    ``GET /api/settlement/aggregates`` 로 가져간다 — 이 라우트는 DB 를 읽지 않는다.

    Returns:
        HTML 응답. 권한 거부는 403(abort), 미인증은 ``@login_required`` 가 처리.
    """
    user = getattr(g, "current_user", None)
    if not can_view_settlement_dashboard(user):
        abort(403)

    template_name = (
        'cs/partials/settlement_dashboard_body.html'
        if wants_erp_shell_tab_body(request)
        else 'cs/settlement_dashboard.html'
    )
    response = make_response(
        render_template(
            template_name,
            erp_sub_nav_active='settlement',
        )
    )
    apply_erp_shell_fragment_headers(response, request)
    return response

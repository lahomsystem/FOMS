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
from foms.services.settlement_channel_access import is_accounting_or_admin
from foms.services.settlement_channel_access import can_view_channel_settlement
# 실무 탭 [정산 청구] 폼의 귀속 부서는 **서버 상수가 SSOT** 다. 화면에 코드를 적으면
# 5종 집합이 갈려 400 이 나는 부서가 생긴다(쓰기 API 가 이 집합으로 검증한다).
# 최상단 import 가 안전한 이유: 앱 부팅 시 `completion_dashboard` 가 이미
# `settlement_rows` 경유로 먼저 로드돼 `erp_display` 순환에 걸리지 않는다.
from foms.web.cs.completion_dashboard import SETTLEMENT_DEPARTMENT_OPTIONS
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

    허용 집합은 **ADMIN**, 또는 team 이 ``ACCOUNTING``(회계팀)인 MANAGER/STAFF 다
    (사용자 결정 2026-09-03 — 채널 정산 탭과 같은 집합으로 통일). 그 전에는
    ``FINANCE_MUTATION`` 과 같은 집합(CS/SALES 포함)이었으나, 전사 매출·미수 총액을
    회계팀과 관리자만 보도록 좁혔다. 주문 상세의 입금확인 같은 개별 금융 command 는
    여전히 ``FINANCE_MUTATION``(CS/SALES 포함)이라 영업 업무는 그대로다.

    판정 본체는 :func:`foms.services.settlement_channel_access.is_accounting_or_admin`
    이며 정책 엔진(``SETTLEMENT_DASHBOARD_READ``)도 gate 로 같은 함수를 쓴다 — MANAGER 가
    엔진에서 team 검사보다 먼저 통과하기 때문에 teams tuple 만으로는 표현할 수 없다.

    Args:
        user: 현재 사용자(``None`` 이면 미인증 — ``False``).

    Returns:
        열람 가능하면 True.
    """
    return is_accounting_or_admin(user)


def can_view_manager_breakdown(user: Any) -> bool:
    """담당자별 매출(직원 실적)을 볼 수 있는지 — 분석 탭 전용 상위 게이트.

    정산 화면 자체는 STAFF(CS·SALES)도 보지만, **담당자별 매출은 동료 실적 전량 공개**라
    사용자 결정(2026-08-31)으로 관리자급으로 좁혔다(스펙 §13.6).

    은닉은 **서버 payload 단계**에서 한다 — 데이터를 다 내려보내고 클라이언트에서
    감추면 개발자 도구로 그대로 보인다(이 저장소의 클라 숨김 금지 원칙).

    Args:
        user: 현재 사용자(``None`` 이면 미인증 — ``False``).

    Returns:
        담당자별 매출을 볼 수 있으면 True.
    """
    if not can_view_settlement_dashboard(user):
        return False
    return str(getattr(user, "role", "") or "").upper() in ("ADMIN", "MANAGER")


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
            department_options=SETTLEMENT_DEPARTMENT_OPTIONS,
            # 채널(네이버) 정산 탭은 ADMIN·회계팀만 본다(NAVER-SETTLE-01 §1). 서버에서
            # 마크업째 빼는 이유: 클라이언트 숨김은 개발자 도구로 그대로 보인다.
            # 두 렌더 분기(프래그먼트·전체 문서)가 같은 render_template 을 타므로 여기 1곳이다.
            can_view_channel_settlement=can_view_channel_settlement(user),
        )
    )
    apply_erp_shell_fragment_headers(response, request)
    return response

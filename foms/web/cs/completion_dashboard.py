"""
시공 완료 대시보드 (Construction Completion Dashboard) — canonical page owner.

계획서: docs/plans/2026-03-02-construction-completion-dashboard-plan.md
- 시공 완료·AS 접수 건의 사진 리뷰 및 비용 청구/정산 거점.
"""
from flask import Blueprint, g, make_response, render_template, request
from foms.web.auth import login_required
from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body

erp_completion_page_bp = Blueprint(
    'erp_completion_page',
    __name__,
    url_prefix='/erp',
)


@erp_completion_page_bp.route('/completion')
@login_required
def erp_completion_dashboard():
    """시공 완료 대시보드: 완료·AS 건 목록 + 시공 사진 갤러리."""
    user = getattr(g, "current_user", None)
    is_construction_team = bool(user and getattr(user, "team", None) == "CONSTRUCTION")
    template_name = (
        'cs/partials/completion_dashboard_fragment.html'
        if wants_erp_shell_tab_body(request)
        else 'cs/completion_dashboard.html'
    )
    response = make_response(
        render_template(
            template_name,
            erp_sub_nav_active='completion',
            is_construction_team=is_construction_team,
        )
    )
    apply_erp_shell_fragment_headers(response, request)
    return response

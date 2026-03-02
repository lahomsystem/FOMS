"""
시공 완료 대시보드 (Construction Completion Dashboard)
계획서: docs/plans/2026-03-02-construction-completion-dashboard-plan.md
- 시공 완료·AS 접수 건의 사진 리뷰 및 비용 청구/정산 거점.
"""
from flask import Blueprint, render_template
from apps.auth import login_required

erp_completion_page_bp = Blueprint(
    'erp_completion_page',
    __name__,
    url_prefix='/erp',
)


@erp_completion_page_bp.route('/completion')
@login_required
def erp_completion_dashboard():
    """시공 완료 대시보드: 완료·AS 건 목록 + 시공 사진 갤러리."""
    return render_template(
        'erp_completion_dashboard.html',
        erp_sub_nav_active='completion',
    )

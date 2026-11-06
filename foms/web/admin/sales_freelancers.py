"""프리랜서 설정 화면(``/admin/sales-freelancers``) — 설계서 FCOMM-01 §2.3 · J5.

보기는 회계팀 · 관리자(:func:`~foms.services.settlement_channel_access.is_accounting_or_admin`), 고치기는 ADMIN 만.
고칠 수 있는지는 서버가 정해 템플릿 깃발(``can_edit``)로 넘긴다 — 회계팀 화면에는 추가 · 요율 바꾸기 칸이 없다.
값은 ``static/js/admin/sales-freelancers.js`` 가 JSON API(:mod:`foms.api.admin.sales_freelancers`)에서 읽고 보낸다.
"""
from __future__ import annotations

from flask import abort, g, render_template

from foms.services.settlement_channel_access import is_accounting_or_admin
from foms.web.admin.routes import admin_bp
from foms.web.auth import login_required


@admin_bp.route("/admin/sales-freelancers")
@login_required
def sales_freelancers():
    """프리랜서 설정 화면 껍데기(목록 · 폼은 스크립트가 그린다). 회계팀 · 관리자 밖은 403."""
    user = getattr(g, "current_user", None)
    if not is_accounting_or_admin(user) or getattr(user, "partner_org_id", None) is not None:
        abort(403)
    can_edit = str(getattr(user, "role", "") or "").strip().upper() == "ADMIN"
    return render_template("admin/sales_freelancers.html", can_edit=can_edit,
                           api_url="/api/admin/sales-freelancers")

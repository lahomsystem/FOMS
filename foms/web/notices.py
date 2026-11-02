"""FOMS 공지사항 본사 직원 화면 ``/notices`` (설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §5).

본사 직원(``partner_org_id`` 없음)만 연다 — 협력사 계정은 협력사 공지 목록(``/partner/notices``)으로 보낸다.
목록은 서버가 그린다(``visible_notices``). 펼쳐 읽으면 ``POST /api/notices/<id>/read`` 로 읽음을 남기고,
확인 창(POPUP)은 공용 레이아웃의 ``partials/shared/notice_popup.html`` · ``foms-notice-popup.js`` 가 띄운다.
"""
from __future__ import annotations

from flask import Blueprint, g, redirect, render_template, request, url_for

from db import get_db
from foms.services.notices.service import visible_notices
from foms.web.auth import login_required

notices_web_bp = Blueprint("notices_web", __name__)

FILTERS = (("all", "전체"), ("unread", "안 읽음"))


@notices_web_bp.route("/notices")
@login_required
def notice_list():
    user = g.current_user
    if getattr(user, "partner_org_id", None):
        return redirect(url_for("partner_portal.notices"))
    items = visible_notices(get_db(), user)
    unread = sum(1 for n in items if not n.get("read"))
    current = request.args.get("filter") if request.args.get("filter") in dict(FILTERS) else "all"
    shown = [n for n in items if not n.get("read")] if current == "unread" else items
    return render_template(
        "notices/list.html",
        notices=shown,
        total=len(items),
        unread=unread,
        filters=FILTERS,
        current_filter=current,
    )

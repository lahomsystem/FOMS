"""협력사 거래명세서 — 우리 CS 화면(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.5 · §5.8).

- ``GET /erp/partner-statements`` 발행 대기 · 발행함 목록(ERP 셸 탭이면 body partial 만).
- ``GET /erp/partner-statements/<id>`` 명세서 한 장 고치기 · 발행(초안) / 보기 · 수정본 · 취소(발행본).
- ``GET /erp/partner-statements/<id>/print`` 양식(공급받는자용 · 공급자용 2장) — 브라우저 인쇄 · PDF.

GET 은 쓰기 정책 가드에 닿지 않아 핸들러가 :func:`can_manage_statements` 로 직접 본다(정산 화면과 같은 관례).
값은 화면에서 ``/api/partner-statements`` 로 가져간다. 이 모듈은 읽기 전용이다.
"""
from __future__ import annotations

from flask import Blueprint, abort, g, make_response, render_template, request

from db import get_db
from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body
from foms.services.partners.statement_view import form_context
from foms.services.partners.statements import can_manage_statements
from foms.web.auth import login_required
from models import Order, PartnerStatement

erp_partner_statements_page_bp = Blueprint("erp_partner_statements_page", __name__, url_prefix="/erp")


def _guard() -> None:
    if not can_manage_statements(getattr(g, "current_user", None)):
        abort(403)


@erp_partner_statements_page_bp.route("/partner-statements")
@login_required
def erp_partner_statements():
    """발행 대기 · 발행함 목록."""
    _guard()
    template = ("cs/partials/partner_statements_body.html" if wants_erp_shell_tab_body(request)
                else "cs/partner_statements.html")
    response = make_response(render_template(template, erp_sub_nav_active="partner_statements"))
    apply_erp_shell_fragment_headers(response, request)
    return response


@erp_partner_statements_page_bp.route("/partner-statements/<int:statement_id>")
@login_required
def erp_partner_statement(statement_id: int):
    """명세서 한 장(고치기 · 발행 · 수정본 · 취소)."""
    _guard()
    stmt = get_db().get(PartnerStatement, statement_id)
    if stmt is None:
        abort(404)
    response = make_response(render_template("cs/partner_statement_edit.html", statement_id=statement_id,
                                             order_id=stmt.order_id, erp_sub_nav_active="partner_statements"))
    response.headers["Cache-Control"] = "private, no-store"
    return response


@erp_partner_statements_page_bp.route("/partner-statements/<int:statement_id>/print")
@login_required
def erp_partner_statement_print(statement_id: int):
    """양식 인쇄(초안은 "초안" 표시가 찍힌다)."""
    _guard()
    db = get_db()
    stmt = db.get(PartnerStatement, statement_id)
    order = db.get(Order, stmt.order_id) if stmt is not None else None
    if stmt is None or order is None:
        abort(404)
    response = make_response(render_template("partner/statement_form.html", **form_context(db, stmt, order)))
    response.headers["Cache-Control"] = "private, no-store"
    return response

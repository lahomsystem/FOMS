"""협력사 거래명세서 화면 — 협력사 계정(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.6).

- ``GET /partner/statements`` 월 장부(이월 · 이달 판매 · 이달 입금 · 지금 잔액 + 이달 명세서 · 입금) · ``/export.csv`` 받기.
- ``GET /partner/statements/<id>`` 명세서 보기(양식 + 제품별 최종 도면 + 확인했어요 · 금액 문의). 처음 열면 "열어 봄"을 남긴다.
- ``GET /partner/statements/<id>/print`` 양식 인쇄(공급받는자용 · 공급자용 2장, 온라인 원본 QR).

자기 회사 발행 · 취소 명세서만(초안 · 남의 것은 404). 금액은 발행 스냅샷 그대로다.
"""
from __future__ import annotations

from flask import Blueprint, Response, abort, g, render_template, request, url_for

from db import get_db
from foms.api.partner_statements_staff import drawing_card
from foms.services.auth.partner_scope import partner_required
from foms.services.partners.drawing_confirm import final_drawings_for_partner
from foms.services.partners.statement_partner import ledger_csv, mark_viewed, partner_ledger, questions, visible_statement
from foms.services.partners.statement_view import form_context, qr_data_uri
from models import Order, PartnerOrg

partner_statements_portal_bp = Blueprint("partner_statements_portal", __name__, url_prefix="/partner/statements")


def _org() -> PartnerOrg:
    return get_db().query(PartnerOrg).filter(PartnerOrg.id == g.current_user.partner_org_id).first()


def _statement_or_404(db, statement_id: int):
    stmt = visible_statement(db, g.current_user.partner_org_id, statement_id)
    order = db.get(Order, stmt.order_id) if stmt is not None else None
    if stmt is None or order is None:
        abort(404)
    return stmt, order


def _context(db, stmt, order) -> dict:
    url = url_for("partner_statements_portal.view", statement_id=stmt.id, _external=True)
    return form_context(db, stmt, order, qr_svg=qr_data_uri(url))


@partner_statements_portal_bp.route("", endpoint="ledger")
@partner_required
def ledger():
    """월 장부."""
    return render_template("partner/statements.html", org=_org(),
                           ledger=partner_ledger(get_db(), g.current_user.partner_org_id, request.args.get("month")))


@partner_statements_portal_bp.route("/export.csv", endpoint="export")
@partner_required
def export():
    """월 장부 받기(CSV — 엑셀로 열림)."""
    ledger = partner_ledger(get_db(), g.current_user.partner_org_id, request.args.get("month"))
    response = Response(ledger_csv(ledger), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f"attachment; filename=statements-{ledger['month']}.csv"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@partner_statements_portal_bp.route("/<int:statement_id>", endpoint="view")
@partner_required
def view(statement_id: int):
    """명세서 보기 — 처음 열면 "열어 봄"을 남긴다."""
    db = get_db()
    stmt, order = _statement_or_404(db, statement_id)
    mark_viewed(stmt)
    db.commit()
    drawings = [drawing_card(f["no"], f) for f in final_drawings_for_partner(order) if f.get("key")]
    return render_template("partner/statement_view.html", org=_org(), drawings=drawings,
                           questions=questions(db, stmt), **_context(db, stmt, order))


@partner_statements_portal_bp.route("/<int:statement_id>/print", endpoint="print_form")
@partner_required
def print_form(statement_id: int):
    """양식 인쇄(2장)."""
    db = get_db()
    stmt, order = _statement_or_404(db, statement_id)
    return render_template("partner/statement_form.html", **_context(db, stmt, order))

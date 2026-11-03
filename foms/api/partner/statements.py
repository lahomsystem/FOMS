"""협력사 거래명세서 JSON API — 협력사 계정(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.6 · §6).

- ``POST /api/partner/statements/<id>/ack`` 명세서 확인했어요(처음 한 번 기록).
- ``POST /api/partner/statements/<id>/questions`` 금액 문의 ``{line_ref?, text}``.

자기 회사 발행 · 취소 명세서만(초안 · 남의 것은 404). 둘 다 감사 한 줄. 판정은
:mod:`foms.services.partners.statement_partner`.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.services.auth.partner_scope import partner_required
from foms.services.partners.statement_partner import ack, ask, questions, visible_statement
from foms.services.partners.statements import StatementError
from models import SecurityLog

partner_statements_api_bp = Blueprint("partner_statements_api", __name__, url_prefix="/api/partner/statements")

_FAILED = "보내지 못했습니다. 잠시 뒤 다시 시도해 주세요."


def _fail(status: int, error: str):
    return jsonify({"success": False, "data": None, "error": error}), status


def _log(db, action: str, stmt, message: str, **detail) -> None:
    db.add(SecurityLog(user_id=g.current_user.id, action=action, target_type="partner_statement",
                       target_id=int(stmt.id), message=message,
                       detail={"partner_org_id": stmt.partner_org_id, "order_id": stmt.order_id,
                               "doc_no": stmt.doc_no, **detail}))


@partner_statements_api_bp.route("/<int:statement_id>/ack", methods=["POST"], endpoint="ack")
@partner_required
def api_ack(statement_id: int):
    """명세서 확인했어요."""
    db = get_db()
    stmt = visible_statement(db, g.current_user.partner_org_id, statement_id)
    if stmt is None:
        return _fail(404, "명세서를 찾을 수 없습니다.")
    try:
        if ack(stmt, g.current_user.id):
            _log(db, "PARTNER_STATEMENT_ACKED", stmt, f"협력사 명세서 확인: {stmt.doc_no}")
        db.commit()
    except StatementError as exc:
        db.rollback()
        return _fail(exc.status, str(exc))
    except SQLAlchemyError:
        db.rollback()
        return _fail(500, _FAILED)
    return jsonify({"success": True, "data": {"acked": True}, "error": None})


@partner_statements_api_bp.route("/<int:statement_id>/questions", methods=["POST"], endpoint="ask")
@partner_required
def api_ask(statement_id: int):
    """금액 문의 — 줄을 골라 묻는다."""
    db = get_db()
    stmt = visible_statement(db, g.current_user.partner_org_id, statement_id)
    if stmt is None:
        return _fail(404, "명세서를 찾을 수 없습니다.")
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    try:
        question = ask(db, stmt, g.current_user.id, body.get("line_ref"), body.get("text"))
        _log(db, "PARTNER_STATEMENT_QUESTION", stmt, f"협력사 명세서 금액 문의: {stmt.doc_no}",
             question_id=question.id, line_ref=question.line_ref)
        db.commit()
    except StatementError as exc:
        db.rollback()
        return _fail(exc.status, str(exc))
    except SQLAlchemyError:
        db.rollback()
        return _fail(500, _FAILED)
    return jsonify({"success": True, "data": {"questions": questions(db, stmt)}, "error": None})

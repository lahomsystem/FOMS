"""협력사 입금 장부 — 우리 CS JSON API(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §3.4 · §5.7 — 5단계).

접두 ``/api/partner-payments``:

- ``GET ?org_id=`` 협력사 목록 · 고른 협력사 잔액 · 최근 입금 · 덜 받은 발행 명세서(입금 맞추기 고르기 칸).
- ``POST ""`` 입금 기록 ``{org_id, paid_on, amount, memo?, statement_id?}`` · ``POST /<id>/void`` 지우기 ``{reason}``(이유 필수).
- ``GET /export.csv?org_id=&month=`` 월 장부 CSV(협력사 화면 받기와 같은 값).

권한은 명세서와 같다(ADMIN, 또는 CS 권한 팀의 STAFF · MANAGER — 쓰기 정책 ``PARTNER_STATEMENT``). 기록 · 지우기는 감사 한 줄씩.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from flask import Blueprint, Response, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.services.partners.payments import allocate, payment_rows, record_payment, void_payment
from foms.services.partners.statement_partner import ledger_csv, partner_ledger
from foms.services.partners.statements import ISSUED, StatementError, balance, can_manage_statements
from models import PartnerOrg, PartnerStatement, SecurityLog

logger = logging.getLogger(__name__)

partner_payments_staff_api_bp = Blueprint("partner_payments_staff_api", __name__, url_prefix="/api/partner-payments")

_FAILED = "저장하지 못했습니다. 잠시 뒤 다시 해 주세요."


def _fail(status: int, error: str):
    return jsonify({"success": False, "data": None, "error": error}), status


def _staff() -> tuple[Optional[Any], Optional[tuple[Any, int]]]:
    user = getattr(g, "current_user", None)
    if user is None or getattr(user, "is_active", None) is False:
        return None, _fail(401, "로그인이 필요합니다.")
    if not can_manage_statements(user):
        return None, _fail(403, "CS 팀과 관리자만 쓸 수 있습니다.")
    return user, None


def _org_id(db, value: Any) -> Optional[int]:
    orgs = [o.id for o in db.query(PartnerOrg).filter(PartnerOrg.is_active.is_(True)).order_by(PartnerOrg.id).all()]
    try:
        wanted = int(value)
    except (TypeError, ValueError):
        wanted = None
    return wanted if wanted in orgs else (orgs[0] if orgs else None)


def _payload(db, org_id: Optional[int]) -> dict[str, Any]:
    orgs = [{"id": o.id, "name": o.name} for o in db.query(PartnerOrg).filter(PartnerOrg.is_active.is_(True)).order_by(PartnerOrg.id)]
    if org_id is None:
        return {"orgs": orgs, "org_id": None, "balance": 0, "payments": [], "statements": []}
    paid = allocate(db, org_id)
    stmts = db.query(PartnerStatement).filter(PartnerStatement.partner_org_id == org_id,
                                              PartnerStatement.status == ISSUED).order_by(
        PartnerStatement.statement_date.desc(), PartnerStatement.id.desc()).limit(200).all()
    open_stmts = [{"id": s.id, "doc_no": s.doc_no, "date": s.statement_date.isoformat() if s.statement_date else "",
                   "total": int(s.total or 0), "left": int(s.total or 0) - paid.get(s.id, 0)}
                  for s in stmts if paid.get(s.id, 0) < int(s.total or 0)]
    return {"orgs": orgs, "org_id": org_id, "balance": balance(db, org_id), "payments": payment_rows(db, org_id),
            "statements": open_stmts}


def _ok(db, org_id: Optional[int]):
    response = jsonify({"success": True, "data": _payload(db, org_id), "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response


@partner_payments_staff_api_bp.route("", methods=["GET"], endpoint="list")
def api_list():
    """협력사 잔액 · 입금 · 덜 받은 명세서."""
    _actor, denied = _staff()
    if denied:
        return denied
    db = get_db()
    return _ok(db, _org_id(db, request.args.get("org_id")))


@partner_payments_staff_api_bp.route("", methods=["POST"], endpoint="record")
def api_record():
    """입금 기록."""
    actor, denied = _staff()
    if denied:
        return denied
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    db = get_db()
    org_id = _org_id(db, body.get("org_id"))
    try:
        if org_id is None:
            raise StatementError("협력사를 찾을 수 없습니다.", 404)
        payment = record_payment(db, org_id, body, actor.id)
        db.add(SecurityLog(user_id=actor.id, action="PARTNER_PAYMENT_RECORDED", target_type="partner_payment",
                           target_id=int(payment.id), message=f"협력사 입금 기록: {payment.amount:,}원",
                           detail={"partner_org_id": org_id, "amount": int(payment.amount), "paid_on": payment.paid_on.isoformat(),
                                   "statement_id": payment.statement_id}))
        db.commit()
    except StatementError as exc:
        db.rollback()
        return _fail(exc.status, str(exc))
    except SQLAlchemyError:
        db.rollback()
        logger.exception("[PARTNER_PAYMENT] 입금 기록 실패")
        return _fail(500, _FAILED)
    return _ok(db, org_id)


@partner_payments_staff_api_bp.route("/<int:payment_id>/void", methods=["POST"], endpoint="void")
def api_void(payment_id: int):
    """입금 지우기(이유 필수)."""
    actor, denied = _staff()
    if denied:
        return denied
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    db = get_db()
    try:
        payment = void_payment(db, payment_id, actor.id, body.get("reason"))
        db.add(SecurityLog(user_id=actor.id, action="PARTNER_PAYMENT_VOIDED", target_type="partner_payment",
                           target_id=int(payment.id), message=f"협력사 입금 지우기: {payment.amount:,}원",
                           detail={"partner_org_id": payment.partner_org_id, "amount": int(payment.amount),
                                   "reason": payment.void_reason}))
        db.commit()
    except StatementError as exc:
        db.rollback()
        return _fail(exc.status, str(exc))
    except SQLAlchemyError:
        db.rollback()
        logger.exception("[PARTNER_PAYMENT] 입금 지우기 실패")
        return _fail(500, _FAILED)
    return _ok(db, payment.partner_org_id)


@partner_payments_staff_api_bp.route("/export.csv", methods=["GET"], endpoint="export")
def api_export():
    """월 장부 CSV(엑셀로 열림)."""
    _actor, denied = _staff()
    if denied:
        return denied
    db = get_db()
    org_id = _org_id(db, request.args.get("org_id"))
    if org_id is None:
        return _fail(404, "협력사를 찾을 수 없습니다.")
    ledger = partner_ledger(db, org_id, request.args.get("month"))
    response = Response(ledger_csv(ledger), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f"attachment; filename=partner-{org_id}-{ledger['month']}.csv"
    response.headers["Cache-Control"] = "private, no-store"
    return response

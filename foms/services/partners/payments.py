"""협력사 입금 장부 — 기록 · 지우기 · 잔액 · 명세서별 받은 돈(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §3.4 · §5.7 — 5단계).

* 잔액 = 발행(ISSUED) 명세서 합 − 지우지 않은 입금 합. 취소(VOID) 명세서 · 지운 입금은 빠진다.
* 명세서별 받은 돈(:func:`allocate`) — 명세서를 고른 입금은 그 명세서에, 고르지 않은 입금은 일자가 오래된 덜 받은 명세서부터
  채운다(넘치면 다음 명세서로). 출고 대시보드 "입금 대기"와 협력사 장부 상태가 이 값을 쓴다.
* 지우기는 줄을 남기고 지운 때 · 사람 · 이유만 적는다(이유 필수). 금액은 정수 원, 0 보다 커야 한다.
"""
from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Any, Iterable, Optional

from sqlalchemy import func

from foms.services.datetime_kst import now_utc_naive
from foms.services.partners.statements import ISSUED, StatementError
from models import PartnerOrg, PartnerPayment, PartnerStatement

MAX_AMOUNT = 10 ** 10
_TEXT_LIMIT = 200


def _active(q):
    return q.filter(PartnerPayment.voided_at.is_(None))


def paid_total(db, org_id: int, *, before: Optional[datetime.date] = None,
               start: Optional[datetime.date] = None) -> int:
    """지우지 않은 입금 합(날짜 범위 선택)."""
    q = _active(db.query(func.coalesce(func.sum(PartnerPayment.amount), 0)).filter(
        PartnerPayment.partner_org_id == org_id))
    if before is not None:
        q = q.filter(PartnerPayment.paid_on < before)
    if start is not None:
        q = q.filter(PartnerPayment.paid_on >= start)
    return int(q.scalar() or 0)


def allocate(db, org_id: int) -> dict[int, int]:
    """발행 명세서 id → 받은 돈. 고른 입금은 그 명세서, 나머지는 오래된 명세서부터 채운다."""
    stmts = db.query(PartnerStatement).filter(PartnerStatement.partner_org_id == org_id,
                                              PartnerStatement.status == ISSUED).order_by(
        PartnerStatement.statement_date, PartnerStatement.id).all()
    paid = {s.id: 0 for s in stmts}
    totals = {s.id: int(s.total or 0) for s in stmts}
    loose = 0
    for p in _active(db.query(PartnerPayment).filter(PartnerPayment.partner_org_id == org_id)).order_by(
            PartnerPayment.paid_on, PartnerPayment.id).all():
        if p.statement_id in paid:
            take = min(int(p.amount), totals[p.statement_id] - paid[p.statement_id])
            paid[p.statement_id] += take
            loose += int(p.amount) - take
        else:
            loose += int(p.amount)
    for s in stmts:
        if loose <= 0:
            break
        take = min(loose, totals[s.id] - paid[s.id])
        paid[s.id] += take
        loose -= take
    return paid


def unpaid_order_ids(db, order_ids: Iterable[int]) -> set[int]:
    """출고 대시보드 "입금 대기" — 발행 명세서 금액만큼 아직 다 받지 못한 주문(표시만, 막지 않는다)."""
    ids = {int(i) for i in order_ids if i}
    if not ids:
        return set()
    stmts = db.query(PartnerStatement.id, PartnerStatement.order_id, PartnerStatement.partner_org_id,
                     PartnerStatement.total).filter(PartnerStatement.order_id.in_(ids),
                                                    PartnerStatement.status == ISSUED).all()
    out: set[int] = set()
    for org_id in {s.partner_org_id for s in stmts}:
        paid = allocate(db, org_id)
        out |= {s.order_id for s in stmts if s.partner_org_id == org_id and paid.get(s.id, 0) < int(s.total or 0)}
    return out


def _amount(value: Any) -> int:
    try:
        amount = int(Decimal(str(value if value is not None else "").replace(",", "").strip()))
    except (ArithmeticError, ValueError) as exc:
        raise StatementError("입금 금액은 숫자로 넣어 주세요.") from exc
    if amount <= 0 or amount >= MAX_AMOUNT:
        raise StatementError("입금 금액은 0원보다 크게 넣어 주세요.")
    return amount


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:_TEXT_LIMIT]


def record_payment(db, org_id: int, raw: Any, user_id: Optional[int]) -> PartnerPayment:
    """입금 기록 ``{paid_on, amount, memo?, statement_id?}`` — 명세서는 이 협력사의 발행본만. 커밋은 부르는 쪽."""
    raw = raw if isinstance(raw, dict) else {}
    if db.get(PartnerOrg, org_id) is None:
        raise StatementError("협력사를 찾을 수 없습니다.", 404)
    try:
        paid_on = datetime.date.fromisoformat(str(raw.get("paid_on") or "")[:10])
    except ValueError as exc:
        raise StatementError("입금일을 넣어 주세요.") from exc
    statement_id = raw.get("statement_id") or None
    if statement_id is not None:
        stmt = db.get(PartnerStatement, int(statement_id)) if str(statement_id).isdigit() else None
        if stmt is None or stmt.partner_org_id != org_id or stmt.status != ISSUED:
            raise StatementError("고른 명세서를 찾을 수 없습니다. 이 협력사의 발행 명세서만 고를 수 있습니다.")
        statement_id = stmt.id
    payment = PartnerPayment(partner_org_id=org_id, paid_on=paid_on, amount=_amount(raw.get("amount")),
                             memo=_text(raw.get("memo")) or None, statement_id=statement_id, recorded_by=user_id)
    db.add(payment)
    db.flush()
    return payment


def void_payment(db, payment_id: int, user_id: Optional[int], reason: Any) -> PartnerPayment:
    """입금 지우기 — 이유 필수, 줄은 남긴다."""
    payment = db.query(PartnerPayment).filter(PartnerPayment.id == payment_id).with_for_update().first()
    if payment is None:
        raise StatementError("입금 기록을 찾을 수 없습니다.", 404)
    if payment.voided_at is not None:
        raise StatementError("이미 지운 입금입니다.", 409)
    text = _text(reason)
    if not text:
        raise StatementError("입금을 지우는 이유를 적어 주세요.")
    payment.voided_at, payment.voided_by, payment.void_reason = now_utc_naive(), user_id, text
    db.flush()
    return payment


def payment_rows(db, org_id: int, limit: int = 100) -> list[dict[str, Any]]:
    """최근 입금(지운 것 포함 — 회색)."""
    rows = db.query(PartnerPayment).filter(PartnerPayment.partner_org_id == org_id).order_by(
        PartnerPayment.paid_on.desc(), PartnerPayment.id.desc()).limit(limit).all()
    docs = {s.id: s.doc_no for s in db.query(PartnerStatement).filter(
        PartnerStatement.id.in_({r.statement_id for r in rows if r.statement_id}))} if rows else {}
    return [{"id": r.id, "paid_on": r.paid_on.isoformat(), "amount": int(r.amount), "memo": r.memo or "",
             "doc_no": docs.get(r.statement_id, ""), "voided": r.voided_at is not None, "void_reason": r.void_reason or ""}
            for r in rows]

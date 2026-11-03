"""협력사 거래명세서 — 협력사 쪽 월 장부 · 보기 · 확인했어요 · 금액 문의(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.6 · §6).

협력사는 자기 회사 명세서 중 발행(ISSUED) · 취소(VOID)만 본다 — 초안(DRAFT)은 없는 것처럼 404. 금액은 발행 스냅샷 그대로다.
월 장부 = 지난달까지 이월(그 달 1일 전 발행 합) · 이달 판매(이달 발행 합) · 지금 잔액. 입금은 5단계 ``partner_payments`` 가
들어오면 이월 · 잔액에서 뺀다(지금은 0). 문의는 줄을 골라(``line_ref`` "묶음-줄") 글로 묻고, 우리 CS 가 답을 단다.
"""
from __future__ import annotations

import datetime
import re
from typing import Any, Optional

from sqlalchemy import func

from foms.services.datetime_kst import format_datetime_kst, get_today_kst, now_utc_naive
from foms.services.partners.statements import ISSUED, VOID, StatementError
from foms.services.partners.view import build_partner_order_view
from models import Order, PartnerStatement, PartnerStatementQuestion, User

_TEXT_LIMIT = 500
MAX_OPEN_QUESTIONS = 20


def visible_statement(db, org_id: int, statement_id: int) -> Optional[PartnerStatement]:
    """자기 회사 발행 · 취소 명세서만(초안 · 남의 것은 None)."""
    return db.query(PartnerStatement).filter(
        PartnerStatement.id == statement_id, PartnerStatement.partner_org_id == org_id,
        PartnerStatement.status.in_((ISSUED, VOID))).first()


def _month(value: Any) -> datetime.date:
    match = re.fullmatch(r"(\d{4})-(\d{2})", str(value or ""))
    if match and 1 <= int(match.group(2)) <= 12:
        return datetime.date(int(match.group(1)), int(match.group(2)), 1)
    return get_today_kst().replace(day=1)


def _next_month(first: datetime.date) -> datetime.date:
    return (first.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)


def partner_status(stmt: PartnerStatement) -> str:
    if stmt.status == VOID:
        return "취소됨"
    if stmt.revision_of:
        return "수정본" + (" · 확인함" if stmt.partner_ack_at else "")
    return "확인함" if stmt.partner_ack_at else "새 명세서"


def _issued_total(db, org_id: int, *, before: Optional[datetime.date] = None,
                  start: Optional[datetime.date] = None) -> int:
    q = db.query(func.coalesce(func.sum(PartnerStatement.total), 0)).filter(
        PartnerStatement.partner_org_id == org_id, PartnerStatement.status == ISSUED)
    if before is not None:
        q = q.filter(PartnerStatement.statement_date < before)
    if start is not None:
        q = q.filter(PartnerStatement.statement_date >= start)
    return int(q.scalar() or 0)


def partner_ledger(db, org_id: int, month: Any = None) -> dict[str, Any]:
    """월 장부 — 이월 · 이달 판매 · 이달 입금 · 지금 잔액 + 이달 명세서 줄(날짜 순, 발행본은 잔액을 이어 센다)."""
    first = _month(month)
    nxt = _next_month(first)
    carry = _issued_total(db, org_id, before=first)
    stmts = db.query(PartnerStatement).filter(
        PartnerStatement.partner_org_id == org_id, PartnerStatement.status.in_((ISSUED, VOID)),
        PartnerStatement.statement_date >= first, PartnerStatement.statement_date < nxt).order_by(
        PartnerStatement.statement_date, PartnerStatement.doc_no).all()
    orders = {o.id: o for o in db.query(Order).filter(Order.id.in_({s.order_id for s in stmts}))} if stmts else {}
    running, sales, rows = carry, 0, []
    for s in stmts:
        order = orders.get(s.order_id)
        if s.status == ISSUED:
            running += int(s.total or 0)
            sales += int(s.total or 0)
        rows.append({"id": s.id, "date": s.statement_date.isoformat() if s.statement_date else "", "doc_no": s.doc_no or "",
                     "order_id": s.order_id, "customer_name": build_partner_order_view(order)["customer_name"] if order else "",
                     "products": [{"title": g.get("title") or "", "subtotal": int(g.get("subtotal") or 0)} for g in s.groups or []],
                     "total": int(s.total or 0), "paid": 0, "balance": running if s.status == ISSUED else None,
                     "status": s.status, "status_text": partner_status(s), "reason": s.reason or ""})
    return {"month": first.strftime("%Y-%m"), "prev": (first - datetime.timedelta(days=1)).strftime("%Y-%m"),
            "next": nxt.strftime("%Y-%m"), "carry": carry, "sales": sales, "paid": 0,
            "balance": _issued_total(db, org_id), "rows": rows}


def order_statements(db, org_id: int, order_id: int) -> list[dict[str, Any]]:
    """주문 화면 "거래명세서" 탭 — 이 주문의 발행 · 취소 명세서."""
    stmts = db.query(PartnerStatement).filter(
        PartnerStatement.partner_org_id == org_id, PartnerStatement.order_id == order_id,
        PartnerStatement.status.in_((ISSUED, VOID))).order_by(PartnerStatement.id.desc()).all()
    return [{"id": s.id, "doc_no": s.doc_no or "", "date": s.statement_date.isoformat() if s.statement_date else "",
             "total": int(s.total or 0), "status_text": partner_status(s)} for s in stmts]


def mark_viewed(stmt: PartnerStatement) -> None:
    if stmt.partner_viewed_at is None:
        stmt.partner_viewed_at = now_utc_naive()


def ack(stmt: PartnerStatement, user_id: int) -> bool:
    """명세서 확인했어요 — 발행본만, 처음 한 번만 기록(이미 확인했으면 False)."""
    if stmt.status != ISSUED:
        raise StatementError("취소된 명세서는 확인할 수 없습니다.", 409)
    if stmt.partner_ack_at is not None:
        return False
    stmt.partner_ack_at, stmt.partner_ack_by = now_utc_naive(), user_id
    return True


def _line_ref(stmt: PartnerStatement, value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.fullmatch(r"(\d+)(?:-(\d+))?", text)
    groups = stmt.groups or []
    if not match or not 0 < int(match.group(1)) <= len(groups):
        raise StatementError("물어볼 줄을 찾지 못했습니다. 화면을 새로 고친 뒤 다시 해 주세요.")
    if match.group(2) and not 0 < int(match.group(2)) <= len(groups[int(match.group(1)) - 1].get("lines") or []):
        raise StatementError("물어볼 줄을 찾지 못했습니다. 화면을 새로 고친 뒤 다시 해 주세요.")
    return text


def _clean_text(value: Any) -> str:
    return re.sub(r"[ \t]+", " ", str(value or "")).strip()[:_TEXT_LIMIT]


def ask(db, stmt: PartnerStatement, user_id: int, line_ref: Any, text: Any) -> PartnerStatementQuestion:
    """금액 문의 — 줄(또는 명세서 전체)을 골라 글로 묻는다. 답 없는 문의가 너무 많으면 막는다."""
    body = _clean_text(text)
    if not body:
        raise StatementError("물어볼 내용을 적어 주세요.")
    open_count = db.query(PartnerStatementQuestion).filter(
        PartnerStatementQuestion.statement_id == stmt.id, PartnerStatementQuestion.answered_at.is_(None)).count()
    if open_count >= MAX_OPEN_QUESTIONS:
        raise StatementError("답을 기다리는 문의가 많습니다. 저희 답을 받은 뒤 다시 물어 주세요.", 409)
    question = PartnerStatementQuestion(statement_id=stmt.id, line_ref=_line_ref(stmt, line_ref), text=body,
                                        asked_by=user_id, asked_at=now_utc_naive())
    db.add(question)
    db.flush()
    return question


def answer(db, question_id: int, user_id: int, text: Any) -> PartnerStatementQuestion:
    """우리 CS 답 — 고쳐 쓸 수 있다(마지막 답이 보인다)."""
    question = db.get(PartnerStatementQuestion, question_id)
    if question is None:
        raise StatementError("문의를 찾을 수 없습니다.", 404)
    body = _clean_text(text)
    if not body:
        raise StatementError("답을 적어 주세요.")
    question.answer, question.answered_by, question.answered_at = body, user_id, now_utc_naive()
    db.flush()
    return question


def _line_label(stmt: PartnerStatement, ref: Optional[str]) -> str:
    if not ref:
        return "명세서 전체"
    parts = [int(p) for p in ref.split("-")]
    group = (stmt.groups or [])[parts[0] - 1] if 0 < parts[0] <= len(stmt.groups or []) else {}
    if len(parts) == 1:
        return f"{parts[0]}. {group.get('title') or ''}"
    lines = group.get("lines") or []
    line = lines[parts[1] - 1] if 0 < parts[1] <= len(lines) else {}
    return f"{parts[0]}. {group.get('title') or ''} · {line.get('name') or ''}"


def questions(db, stmt: PartnerStatement) -> list[dict[str, Any]]:
    """문의 목록(오래된 순) — 누가 · 언제 · 어느 줄 · 답."""
    rows = db.query(PartnerStatementQuestion).filter(PartnerStatementQuestion.statement_id == stmt.id).order_by(
        PartnerStatementQuestion.id).all()
    ids = {r.asked_by for r in rows if r.asked_by} | {r.answered_by for r in rows if r.answered_by}
    names = {u.id: u.name or u.username for u in db.query(User).filter(User.id.in_(ids))} if ids else {}
    return [{"id": r.id, "line_ref": r.line_ref or "", "line": _line_label(stmt, r.line_ref), "text": r.text,
             "asked_by": names.get(r.asked_by, ""), "asked_at": format_datetime_kst(r.asked_at) if r.asked_at else "",
             "answer": r.answer or "", "answered_at": format_datetime_kst(r.answered_at) if r.answered_at else ""}
            for r in rows]

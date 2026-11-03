"""협력사 거래명세서 — 협력사 쪽 월 장부 · 보기 · 확인했어요 · 금액 문의(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.6 · §6).

협력사는 자기 회사 명세서 중 발행(ISSUED) · 취소(VOID)만 본다 — 초안(DRAFT)은 없는 것처럼 404. 금액은 발행 스냅샷 그대로다.
월 장부 = 지난달까지 이월(그 달 1일 전 발행 합 − 입금 합) · 이달 판매 · 이달 입금 · 지금 잔액(:mod:`foms.services.partners.payments`).
줄은 명세서와 입금을 날짜 순으로 섞어 잔액을 이어 센다. CSV 받기(엑셀로 열림)는 같은 값이다. 문의는 줄을 골라(``line_ref`` "묶음-줄") 글로 묻고, 우리 CS 가 답을 단다.
"""
from __future__ import annotations

import csv
import datetime
import io
import re
from typing import Any, Optional

from sqlalchemy import func

from foms.services.datetime_kst import format_datetime_kst, get_today_kst, now_utc_naive
from foms.services.partners.payments import allocate, paid_total
from foms.services.partners.statements import ISSUED, VOID, StatementError, balance
from foms.services.partners.view import build_partner_order_view
from models import Order, PartnerPayment, PartnerStatement, PartnerStatementQuestion, User

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


def partner_status(stmt: PartnerStatement, paid: Optional[int] = None) -> str:
    """협력사 화면 상태 — 취소됨 · 수정본 · 새 명세서 · 확인함, 발행본을 다 받지 못했으면 "입금 대기"를 붙인다."""
    if stmt.status == VOID:
        return "취소됨"
    head = ("수정본" + (" · 확인함" if stmt.partner_ack_at else "")) if stmt.revision_of else (
        "확인함" if stmt.partner_ack_at else "새 명세서")
    return head + (" · 입금 대기" if paid is not None and paid < int(stmt.total or 0) else "")


def _issued_total(db, org_id: int, *, before: Optional[datetime.date] = None) -> int:
    q = db.query(func.coalesce(func.sum(PartnerStatement.total), 0)).filter(
        PartnerStatement.partner_org_id == org_id, PartnerStatement.status == ISSUED)
    if before is not None:
        q = q.filter(PartnerStatement.statement_date < before)
    return int(q.scalar() or 0)


def partner_ledger(db, org_id: int, month: Any = None) -> dict[str, Any]:
    """월 장부 — 이월 · 이달 판매 · 이달 입금 · 지금 잔액 + 이달 명세서 · 입금 줄(날짜 순, 잔액을 이어 센다)."""
    first = _month(month)
    nxt = _next_month(first)
    carry = _issued_total(db, org_id, before=first) - paid_total(db, org_id, before=first)
    stmts = db.query(PartnerStatement).filter(
        PartnerStatement.partner_org_id == org_id, PartnerStatement.status.in_((ISSUED, VOID)),
        PartnerStatement.statement_date >= first, PartnerStatement.statement_date < nxt).all()
    pays = db.query(PartnerPayment).filter(
        PartnerPayment.partner_org_id == org_id, PartnerPayment.voided_at.is_(None),
        PartnerPayment.paid_on >= first, PartnerPayment.paid_on < nxt).all()
    orders = {o.id: o for o in db.query(Order).filter(Order.id.in_({s.order_id for s in stmts}))} if stmts else {}
    docs = {s.id: s.doc_no for s in db.query(PartnerStatement).filter(
        PartnerStatement.id.in_({p.statement_id for p in pays if p.statement_id}))} if pays else {}
    paid_by = allocate(db, org_id)
    events = [(s.statement_date, 0, s.doc_no or "", s) for s in stmts] + [(p.paid_on, 1, str(p.id), p) for p in pays]
    running, sales, paid, rows = carry, 0, 0, []
    for _day, kind, _key, obj in sorted(events, key=lambda e: (e[0], e[1], e[2])):
        if kind == 1:
            running -= int(obj.amount)
            paid += int(obj.amount)
            rows.append({"kind": "payment", "id": obj.id, "date": obj.paid_on.isoformat(), "doc_no": docs.get(obj.statement_id, ""),
                         "customer_name": obj.memo or "입금", "products": [], "total": 0, "paid": int(obj.amount),
                         "balance": running, "status": "PAID", "status_text": "입금", "reason": ""})
            continue
        order = orders.get(obj.order_id)
        if obj.status == ISSUED:
            running += int(obj.total or 0)
            sales += int(obj.total or 0)
        rows.append({"kind": "statement", "id": obj.id, "date": obj.statement_date.isoformat() if obj.statement_date else "",
                     "doc_no": obj.doc_no or "", "order_id": obj.order_id,
                     "customer_name": build_partner_order_view(order)["customer_name"] if order else "",
                     "products": [{"title": g.get("title") or "", "subtotal": int(g.get("subtotal") or 0)} for g in obj.groups or []],
                     "total": int(obj.total or 0), "paid": 0, "balance": running if obj.status == ISSUED else None,
                     "status": obj.status, "status_text": partner_status(obj, paid_by.get(obj.id)), "reason": obj.reason or ""})
    return {"month": first.strftime("%Y-%m"), "prev": (first - datetime.timedelta(days=1)).strftime("%Y-%m"),
            "next": nxt.strftime("%Y-%m"), "carry": carry, "sales": sales, "paid": paid,
            "balance": balance(db, org_id), "rows": rows}


_CSV_HEAD = ("일자", "문서번호", "고객(현장) · 메모", "판매", "입금", "잔액", "상태")


def ledger_csv(ledger: dict[str, Any]) -> str:
    """월 장부 CSV(엑셀로 열림) — UTF-8 BOM · CRLF · 금액은 콤마 없는 정수(저장소 CSV 관례)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(_CSV_HEAD)
    writer.writerow([ledger["month"] + "-01", "", "지난달까지 이월", "", "", ledger["carry"], ""])
    for r in ledger["rows"]:
        writer.writerow([r["date"], r["doc_no"], r["customer_name"], r["total"] or "", r["paid"] or "",
                         "" if r["balance"] is None else r["balance"], r["status_text"]])
    writer.writerow(["", "", "이달 합계", ledger["sales"], ledger["paid"], "", ""])
    return "\ufeff" + buf.getvalue()


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

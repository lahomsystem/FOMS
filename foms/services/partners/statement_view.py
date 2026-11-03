"""거래명세서 화면 값 — 우리 CS 발행 대기 목록 · 고치기 화면 · 양식(인쇄) 칸(설계서 §5.5 · §5.8).

금액은 :mod:`foms.services.partners.statements` 가 정한 값을 그대로 옮긴다(여기서 계산하지 않는다). 한글 금액만 여기서 쓴다.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

import segno
from sqlalchemy import func

from foms.services.datetime_kst import format_datetime_kst
from foms.services.partners.statement_calc import summarize
from foms.services.partners.statement_profile import load_profile, receiver_block
from foms.services.partners.statements import DRAFT, ISSUED, StatementError, bucket, compute, ship_date
from foms.services.partners.view import build_partner_order_view
from models import Order, OrderItemOption, PartnerOrg, PartnerStatement, PartnerStatementQuestion, User

_DIGITS = "영일이삼사오육칠팔구"
_SMALL = ("", "십", "백", "천")
_BIG = ("", "만", "억", "조")
STATUS_TEXT = {DRAFT: "초안", ISSUED: "발행", "VOID": "취소됨"}
BUCKET_TEXT = {"soon": "내일까지 출고", "later": "다음 출고", "none": "출고일 없음"}


def qr_data_uri(url: str) -> str:
    """온라인 원본 주소 QR(SVG data URI) — 양식 머리에 찍는다."""
    return segno.make(url, error="m").svg_data_uri(scale=4, border=1, dark="#111111")


def korean_amount(value: int) -> str:
    """정수 → 한글 금액(자리마다 숫자를 다 적는다 — 고쳐 쓰기 어렵게). 0 → "영"."""
    value = int(value)
    if value == 0:
        return "영"
    sign = "마이너스 " if value < 0 else ""
    value = abs(value)
    parts = []
    for big in range(len(_BIG)):
        chunk = value % 10000
        value //= 10000
        if chunk:
            tokens = [_DIGITS[int(d)] + _SMALL[pos] for pos, d in enumerate(reversed(f"{chunk}")) if d != "0"]
            parts.append("".join(reversed(tokens)) + _BIG[big])
        if not value:
            break
    return sign + "".join(reversed(parts))


def _lines_with_refs(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for gi, group in enumerate(groups or [], start=1):
        lines = [{**line, "ref": f"{gi}-{li}"} for li, line in enumerate(group.get("lines") or [], start=1)]
        out.append({**group, "lines": lines, "ref": str(gi)})
    return out


def _date_text(value: Optional[datetime.date]) -> str:
    return value.isoformat() if value else ""


def pending_rows(db) -> list[dict[str, Any]]:
    """발행 대기 — 협력사가 도면 · 옵션을 확정했고 아직 발행 명세서가 없는 주문(출고일 가까운 순)."""
    confirmed = {oid for (oid,) in db.query(OrderItemOption.order_id).filter(
        OrderItemOption.stage == "CONFIRMED").distinct().all()}
    issued = {oid for (oid,) in db.query(PartnerStatement.order_id).filter(
        PartnerStatement.status == ISSUED).distinct().all()}
    ids = sorted(confirmed - issued)
    if not ids:
        return []
    orders = db.query(Order).filter(Order.id.in_(ids), Order.active_filter(), Order.partner_org_id.isnot(None)).all()
    drafts = {s.order_id: s for s in db.query(PartnerStatement).filter(
        PartnerStatement.order_id.in_(ids), PartnerStatement.status == DRAFT).all()}
    orgs = {o.id: o.name for o in db.query(PartnerOrg).all()}
    rows = []
    for order in orders:
        draft = drafts.get(order.id)
        needs: list[str] = []
        try:
            groups = draft.groups if draft is not None else compute(db, order)["groups"]
        except StatementError as exc:
            groups, needs = [], [str(exc)]
        totals = summarize(groups)
        needs += [n for g in groups for n in g.get("needs") or []]
        custom_open = sum(1 for g in groups for line in g.get("lines") or [] if line.get("amount") is None)
        on_date = draft.statement_date if draft is not None else ship_date(order)
        view = build_partner_order_view(order)
        rows.append({"order_id": order.id, "customer_name": view["customer_name"], "org_name": orgs.get(order.partner_org_id, ""),
                     "date": _date_text(on_date), "bucket": bucket(on_date), "products": len(groups),
                     "total": totals["total"], "complete": bool(groups) and totals["complete"] and not needs,
                     "custom_open": custom_open, "needs": needs[:3],
                     "draft_id": draft.id if draft is not None else None,
                     "revision": bool(draft is not None and draft.revision_of)})
    rows.sort(key=lambda r: (r["date"] == "", r["date"], r["order_id"]))
    return rows


def issued_rows(db, limit: int = 100) -> list[dict[str, Any]]:
    """최근 발행 · 취소 명세서(고치기 · 취소 진입)."""
    stmts = db.query(PartnerStatement).filter(PartnerStatement.status != DRAFT).order_by(
        PartnerStatement.issued_at.desc().nullslast(), PartnerStatement.id.desc()).limit(limit).all()
    orders = {o.id: o for o in db.query(Order).filter(Order.id.in_({s.order_id for s in stmts}))} if stmts else {}
    orgs = {o.id: o.name for o in db.query(PartnerOrg).all()} if stmts else {}
    open_questions = dict(db.query(PartnerStatementQuestion.statement_id, func.count(PartnerStatementQuestion.id)).filter(
        PartnerStatementQuestion.statement_id.in_([s.id for s in stmts]), PartnerStatementQuestion.answered_at.is_(None)
    ).group_by(PartnerStatementQuestion.statement_id).all()) if stmts else {}
    rows = []
    for s in stmts:
        order = orders.get(s.order_id)
        rows.append({"id": s.id, "order_id": s.order_id, "doc_no": s.doc_no or "", "date": _date_text(s.statement_date),
                     "status": s.status, "status_text": STATUS_TEXT.get(s.status, s.status),
                     "customer_name": build_partner_order_view(order)["customer_name"] if order else "",
                     "org_name": orgs.get(s.partner_org_id, ""), "total": int(s.total or 0),
                     "acked": s.partner_ack_at is not None, "reason": s.reason or "",
                     "open_questions": int(open_questions.get(s.id, 0))})
    return rows


def _user_name(db, user_id: Optional[int]) -> str:
    user = db.get(User, user_id) if user_id else None
    return (getattr(user, "name", None) or getattr(user, "username", None) or "") if user else ""


def statement_json(db, stmt: PartnerStatement) -> dict[str, Any]:
    """CS 고치기 화면이 받는 값 — 묶음 · 줄(ref) · 합계 · 상태. 금액 계산은 서버가 했다."""
    groups = _lines_with_refs(stmt.groups or [])
    totals = summarize(stmt.groups or [])
    return {"id": stmt.id, "order_id": stmt.order_id, "status": stmt.status,
            "status_text": STATUS_TEXT.get(stmt.status, stmt.status), "version": int(stmt.version or 1),
            "doc_no": stmt.doc_no or "", "date": _date_text(stmt.statement_date), "revision_of": stmt.revision_of,
            "reason": stmt.reason or "", "groups": groups, "total": totals["total"], "supply": totals["supply"],
            "vat": totals["vat"], "complete": bool(groups) and totals["complete"],
            "needs": [n for g in groups for n in g.get("needs") or []],
            "prev_balance": stmt.prev_balance, "after_balance": stmt.after_balance,
            "issued_at": format_datetime_kst(stmt.issued_at) if stmt.issued_at else "",
            "issued_by": _user_name(db, stmt.issued_by),
            "partner_ack_at": format_datetime_kst(stmt.partner_ack_at) if stmt.partner_ack_at else ""}


def form_context(db, stmt: PartnerStatement, order: Order, *, qr_svg: str = "") -> dict[str, Any]:
    """양식(5.8) 칸 — 공급받는자 · 공급자 블록 · 묶음 · 합계(한글) · 잔액 · 계좌 · 안내 문구. 인쇄는 공급받는자용 · 공급자용 2장."""
    profile = load_profile(db)
    org = db.get(PartnerOrg, stmt.partner_org_id)
    view = build_partner_order_view(order)
    supplier = profile["supplier"]
    total = int(stmt.total or 0)
    return {"stmt": statement_json(db, stmt), "supplier": supplier,
            "receiver": receiver_block(profile, org) if org else {},
            "accounts": [a for a in supplier.get("accounts", "").split("\n") if a],
            "amount_words": korean_amount(total), "customer_name": view["customer_name"], "site": view["address"],
            "order_id": order.id, "qr_svg": qr_svg, "copies": ("공급받는자용", "공급자용")}

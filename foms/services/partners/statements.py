"""협력사 거래명세서 — 초안 만들기 · 고치기 · 발행 · 수정본 · 취소(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §3.3 · §5.5).

금액은 :func:`foms.services.partners.statement_calc.calc_item` 하나가 낸다(확정 옵션 × 단가표 판). 여기서는 그 값을 명세서
한 장으로 묶고, 우리 CS 가 넣는 것(커스텀 줄 금액 · 단가 고침 + 이유)만 받는다.

* 초안(DRAFT) — 주문마다 하나. 협력사가 도면을 확정한 품목(``order_item_options`` CONFIRMED)만 묶음이 된다. 취소 품목은 뺀다.
  "다시 계산"은 옵션 · 단가표에서 새로 만들되 CS 가 넣은 금액 · 고친 단가는 같은 줄에 다시 붙인다.
* 발행(ISSUED) — 일자(출고 · 시공일) · 번호 ``<머리>-<YYYYMMDD>-<순번 2자리>`` · 잔액 스냅샷을 정하고 잠근다. 금액이 빈 줄이
  남으면 막는다. 같은 협력사 발행은 협력사 줄 잠금으로 한 줄로 세운다(잔액 · 번호 경합).
* 수정본 — 발행본을 복사한 새 초안(``revision_of``). 수정본을 발행하면 옛 것은 VOID 가 된다. 취소도 이유가 꼭 있어야 한다.

잔액 = 이 협력사 발행 명세서 합(VOID 빼고) − 지우지 않은 입금 합(``partner_payments``).
"""
from __future__ import annotations

import copy
import datetime
import re
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.orders.drawing_confirm_partial import is_item_cancelled
from foms.services.orders.drawing_customer_send import drawing_round_info
from foms.services.orders.order_mutation_policy import team_has_capability
from foms.services.partners.drawing_confirm import final_drawings_for_partner
from foms.services.partners.statement_calc import calc_item, round_half_up, summarize
from foms.services.partners.statement_profile import doc_prefix_for, load_profile
from foms.services.shipment_dashboard_helpers import _get_order_construction_date
from models import OrderItemOption, PartnerOrg, PartnerPayment, PartnerPriceList, PartnerStatement

DRAFT, ISSUED, VOID = "DRAFT", "ISSUED", "VOID"
MAX_AMOUNT = 10 ** 10
_REASON_LIMIT = 200


class StatementError(ValueError):
    """화면에 그대로 보일 수 있는 거부 이유. ``status`` 는 HTTP 코드."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _date(value: Any) -> Optional[datetime.date]:
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def ship_date(order: Any) -> Optional[datetime.date]:
    """명세서 일자 = 출고 · 시공일(출고 대시보드와 같은 판정)."""
    return _date(_get_order_construction_date(order))


def price_list_for(db, org_id: int, on_date: Optional[datetime.date]) -> Optional[PartnerPriceList]:
    """그 날짜 출고분에 쓸 판 — 적용 시작일이 그날 이전인 판 가운데 가장 새 판. 없으면 지금 판."""
    q = db.query(PartnerPriceList).filter(PartnerPriceList.partner_org_id == org_id,
                                          PartnerPriceList.status != "DRAFT")
    if on_date is not None:
        found = q.filter(PartnerPriceList.effective_from <= on_date).order_by(PartnerPriceList.version.desc()).first()
        if found is not None:
            return found
    return q.filter(PartnerPriceList.status == "ACTIVE").first()


def _calc_input(no: int, item: dict[str, Any], row: OrderItemOption) -> dict[str, Any]:
    rows = [{"width": r.get("spec_width"), "depth": r.get("spec_depth"), "height": r.get("spec_height")}
            for r in item.get("spec_rows") or [] if isinstance(r, dict)]
    return {"uid": row.item_uid, "no": no, "title": str(item.get("product_name") or ""), "base_key": row.base_key,
            "spec_rows": rows or [{}], "quantity": item.get("quantity"), "internal": item.get("internal"),
            "lines": list(row.lines or []), "customs": list(row.customs or []), "changes": list(row.changes or [])}


def compute(db, order: Any, price_list: Optional[PartnerPriceList] = None) -> dict[str, Any]:
    """확정 옵션 × 그 날짜 단가표 판 → ``{groups, price_list_id, statement_date, drawing_round, drawing_keys}``.

    ``price_list`` 를 주면 그 판으로 센다(수정본 — 발행본과 같은 판).
    """
    rows = {r.item_uid: r for r in db.query(OrderItemOption).filter(
        OrderItemOption.order_id == order.id, OrderItemOption.stage == "CONFIRMED").all()}
    if not rows:
        raise StatementError("협력사가 도면 · 옵션을 확정하기 전입니다.", 409)
    on_date = ship_date(order)
    price_list = price_list or price_list_for(db, order.partner_org_id, on_date)
    if price_list is None:
        raise StatementError("이 협력사 단가표가 없습니다. 관리 화면에서 단가표를 먼저 저장해 주세요.", 409)
    groups = []
    for no, item in enumerate((order.structured_data or {}).get("items") or [], start=1):
        if not isinstance(item, dict) or is_item_cancelled(item):
            continue
        row = rows.get(str(item.get("uid") or ""))
        if row is None:
            continue
        group = calc_item(price_list.sheet, _calc_input(no, item, row), price_list.rules)
        group["no"] = no
        groups.append(group)
    sd = order.structured_data or {}
    return {"groups": groups, "price_list_id": price_list.id, "statement_date": on_date,
            "drawing_round": drawing_round_info(sd).round or None,
            "drawing_keys": [f.get("key") for f in final_drawings_for_partner(order) if f.get("key")]}


def _line_id(group: dict[str, Any], line: dict[str, Any]) -> tuple:
    return (group.get("item_uid"), line.get("source") if line.get("source") != "edited" else "auto",
            line.get("key"), line.get("name"), line.get("spec"))


def _carry_edits(fresh: list[dict[str, Any]], old: list[dict[str, Any]]) -> None:
    """다시 계산 — CS 가 넣은 커스텀 금액 · 고친 단가를 같은 줄(품목 · 열쇠 · 이름 · 규격)에 다시 붙인다(in-place)."""
    kept = {_line_id(g, line): line for g in old for line in g.get("lines") or []
            if line.get("source") == "edited" or (line.get("source") == "custom" and line.get("amount") is not None)}
    for group in fresh:
        for line in group.get("lines") or []:
            prev = kept.get(_line_id(group, line))
            if prev is None:
                continue
            if line.get("source") == "custom":
                line.update(amount=prev.get("amount"), unit_price=prev.get("unit_price"), reason=prev.get("reason"))
            else:
                _set_price(line, prev.get("unit_price"), prev.get("reason"))
        _subtotal(group)


def _subtotal(group: dict[str, Any]) -> None:
    group["subtotal"] = sum(line["amount"] for line in group.get("lines") or [] if line.get("amount") is not None)


def _set_price(line: dict[str, Any], unit_price: Any, reason: Any) -> None:
    original = line.get("orig_unit_price", line.get("unit_price"))
    line["unit_price"] = unit_price
    line["amount"] = int(round_half_up(Decimal(str(line.get("qty") or 1)) * unit_price)) if unit_price is not None else None
    if unit_price == original:
        line.pop("orig_unit_price", None)
        line.pop("reason", None)
        line["source"] = "auto"
    else:
        line.update(orig_unit_price=original, reason=reason, source="edited")


def _apply(stmt: PartnerStatement, data: dict[str, Any]) -> None:
    stmt.groups = data["groups"]
    totals = summarize(stmt.groups)
    stmt.total, stmt.supply, stmt.vat = totals["total"], totals["supply"], totals["vat"]
    stmt.price_list_id = data["price_list_id"]
    stmt.statement_date = data["statement_date"]
    stmt.drawing_round, stmt.drawing_keys = data["drawing_round"], data["drawing_keys"]
    flag_modified(stmt, "groups")


def open_draft(db, order: Any, user_id: Optional[int]) -> PartnerStatement:
    """주문의 초안 — 있으면 그대로, 없으면 지금 확정 옵션으로 새로 만든다(flush 만)."""
    stmt = draft_of(db, order.id)
    if stmt is not None:
        return stmt
    stmt = PartnerStatement(partner_org_id=order.partner_org_id, order_id=order.id, status=DRAFT, created_by=user_id)
    _apply(stmt, compute(db, order))
    db.add(stmt)
    db.flush()
    return stmt


def draft_of(db, order_id: int) -> Optional[PartnerStatement]:
    return db.query(PartnerStatement).filter(PartnerStatement.order_id == order_id,
                                             PartnerStatement.status == DRAFT).first()


def locked_draft(db, statement_id: int, base_version: Any) -> PartnerStatement:
    stmt = db.query(PartnerStatement).filter(PartnerStatement.id == statement_id).with_for_update().first()
    if stmt is None:
        raise StatementError("명세서를 찾을 수 없습니다.", 404)
    if stmt.status != DRAFT:
        raise StatementError("이미 발행한 명세서입니다. 고치려면 수정본을 만들어 주세요.", 409)
    if base_version is not None and str(base_version) != str(stmt.version):
        raise StatementError("그사이 다른 사람이 이 초안을 고쳤습니다. 화면을 새로 고친 뒤 다시 해 주세요.", 409)
    return stmt


def recalc_draft(db, order: Any, statement_id: int, base_version: Any) -> PartnerStatement:
    """다시 계산 — 지금 확정 옵션 · 단가표로 줄을 새로 만들고 CS 가 넣은 값은 이어 붙인다. 수정본은 다시 계산하지 않는다."""
    stmt = locked_draft(db, statement_id, base_version)
    if stmt.revision_of:
        raise StatementError("수정본은 발행본을 복사한 것이라 다시 계산하지 않습니다. 줄 금액을 고쳐 주세요.", 409)
    return refresh_draft(db, order, stmt)


def refresh_draft(db, order: Any, stmt: PartnerStatement) -> PartnerStatement:
    """잠근 초안 줄을 지금 확정 옵션으로 새로 만든다(CS 가 넣은 값은 같은 줄에 다시 붙음).

    수정본은 옵션을 고쳤을 때만 여기로 온다(설계서 2026-11-11-partner-confirmed-option-fix §2.3) — 발행본과 같은 단가표 판 ·
    같은 일자를 그대로 둔다(그사이 새 판이 나와도 금액 기준이 바뀌지 않게).
    """
    price_list = db.get(PartnerPriceList, stmt.price_list_id) if stmt.revision_of and stmt.price_list_id else None
    data = compute(db, order, price_list)
    if stmt.revision_of:
        data["statement_date"] = stmt.statement_date
    _carry_edits(data["groups"], stmt.groups or [])
    _apply(stmt, data)
    stmt.version = int(stmt.version or 1) + 1
    db.flush()
    return stmt


def _money(value: Any, where: str) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        amount = int(Decimal(str(value).replace(",", "").strip()))
    except (ArithmeticError, ValueError) as exc:
        raise StatementError(f"{where}: 금액은 숫자로 넣어 주세요.") from exc
    if amount < 0 or amount >= MAX_AMOUNT:
        raise StatementError(f"{where}: 금액이 너무 크거나 0보다 작습니다.")
    return amount


def save_draft(db, statement_id: int, edits: Any, base_version: Any) -> PartnerStatement:
    """CS 가 넣은 값 저장. ``edits`` = ``[{ref: "묶음-줄"(1부터), amount?(커스텀), unit_price?(자동 줄), reason?}]``.

    자동 줄 단가를 바꾸면 이유가 꼭 있어야 하고 원래 단가가 남는다(``edited``). 같은 값으로 되돌리면 자동 줄로 돌아간다.
    """
    stmt = locked_draft(db, statement_id, base_version)
    groups = copy.deepcopy(stmt.groups or [])
    for edit in edits if isinstance(edits, list) else []:
        edit = edit if isinstance(edit, dict) else {}
        match = re.fullmatch(r"(\d+)-(\d+)", str(edit.get("ref") or ""))
        if not match or not (0 < int(match.group(1)) <= len(groups)):
            raise StatementError("고칠 줄을 찾지 못했습니다. 화면을 새로 고친 뒤 다시 해 주세요.", 409)
        group = groups[int(match.group(1)) - 1]
        lines = group.get("lines") or []
        if not 0 < int(match.group(2)) <= len(lines):
            raise StatementError("고칠 줄을 찾지 못했습니다. 화면을 새로 고친 뒤 다시 해 주세요.", 409)
        line = lines[int(match.group(2)) - 1]
        where = f"{group.get('title') or '제품'} · {line.get('name') or '줄'}"
        reason = re.sub(r"\s+", " ", str(edit.get("reason") or "")).strip()[:_REASON_LIMIT]
        if line.get("source") == "custom":
            amount = _money(edit.get("amount"), where)
            line.update(amount=amount, unit_price=amount, reason=reason or None)
        else:
            price = _money(edit.get("unit_price"), where)
            if price is None:
                raise StatementError(f"{where}: 단가를 비울 수 없습니다.")
            if price != line.get("orig_unit_price", line.get("unit_price")) and not reason:
                raise StatementError(f"{where}: 단가를 바꾼 이유를 적어 주세요. 협력사에게 보입니다.")
            _set_price(line, price, reason)
        _subtotal(group)
    stmt.groups = groups
    totals = summarize(groups)
    stmt.total, stmt.supply, stmt.vat = totals["total"], totals["supply"], totals["vat"]
    stmt.version = int(stmt.version or 1) + 1
    flag_modified(stmt, "groups")
    db.flush()
    return stmt


def balance(db, org_id: int, *, exclude_ids: tuple[int, ...] = ()) -> int:
    """이 협력사 잔액 = 발행(ISSUED) 명세서 합 − 지우지 않은 입금 합(5단계 ``partner_payments``)."""
    q = db.query(func.coalesce(func.sum(PartnerStatement.total), 0)).filter(
        PartnerStatement.partner_org_id == org_id, PartnerStatement.status == ISSUED)
    if exclude_ids:
        q = q.filter(PartnerStatement.id.notin_(exclude_ids))
    paid = db.query(func.coalesce(func.sum(PartnerPayment.amount), 0)).filter(
        PartnerPayment.partner_org_id == org_id, PartnerPayment.voided_at.is_(None)).scalar()
    return int(q.scalar() or 0) - int(paid or 0)


def _next_doc_no(db, prefix: str, on_date: datetime.date) -> str:
    head = f"{prefix}-{on_date:%Y%m%d}-"
    taken = [n for (n,) in db.query(PartnerStatement.doc_no).filter(PartnerStatement.doc_no.like(head + "%")).all()]
    seqs = [int(n[len(head):]) for n in taken if n and n[len(head):].isdigit()]
    return f"{head}{(max(seqs) if seqs else 0) + 1:02d}"


def issue(db, statement_id: int, user_id: Optional[int], *, base_version: Any = None,
          statement_date: Any = None) -> PartnerStatement:
    """발행 — 금액이 다 찼는지 보고 일자 · 번호 · 잔액을 정해 잠근다. 수정본이면 옛 것을 VOID 로. 커밋은 부르는 쪽."""
    head = db.get(PartnerStatement, statement_id)
    if head is None:
        raise StatementError("명세서를 찾을 수 없습니다.", 404)
    db.query(PartnerOrg).filter(PartnerOrg.id == head.partner_org_id).with_for_update().one()
    stmt = locked_draft(db, statement_id, base_version)
    totals = summarize(stmt.groups or [])
    if not stmt.groups:
        raise StatementError("명세서에 제품이 없습니다.", 409)
    if not totals["complete"]:
        raise StatementError("금액이 빈 줄이 있습니다. 커스텀 줄 금액을 넣거나 단가표를 고친 뒤 다시 계산해 주세요.", 409)
    on_date = _date(statement_date) or stmt.statement_date
    if on_date is None:
        raise StatementError("출고일(시공일)이 없습니다. 명세서 일자를 넣어 주세요.", 409)
    old = db.get(PartnerStatement, stmt.revision_of) if stmt.revision_of else None
    if old is not None and old.status != ISSUED:
        raise StatementError("고치려던 옛 명세서가 이미 취소되었습니다. 이 초안을 지우고 다시 만들어 주세요.", 409)
    prev = balance(db, stmt.partner_org_id, exclude_ids=(old.id,) if old is not None else ())
    now = now_utc_naive()
    if old is not None:
        old.status, old.voided_at, old.voided_by = VOID, now, user_id
        old.reason = old.reason or stmt.reason
    prefix = doc_prefix_for(load_profile(db), stmt.partner_org_id)
    stmt.status, stmt.statement_date = ISSUED, on_date
    stmt.total, stmt.supply, stmt.vat = totals["total"], totals["supply"], totals["vat"]
    stmt.prev_balance, stmt.after_balance = prev, prev + totals["total"]
    stmt.issued_at, stmt.issued_by = now, user_id
    db.flush()
    # 번호는 협력사가 달라도 겹치면 안 된다(협력사 줄 잠금 밖) — 겹치면 그 번호만 되돌리고 다음 번호로.
    for _attempt in range(3):
        try:
            with db.begin_nested():
                stmt.doc_no = _next_doc_no(db, prefix, on_date)
                db.flush()
            break
        except IntegrityError:
            continue
    else:
        raise StatementError("번호를 정하지 못했습니다. 잠시 뒤 다시 해 주세요.", 409)
    return stmt


def _reason(value: Any, what: str) -> str:
    reason = re.sub(r"\s+", " ", str(value or "")).strip()[:_REASON_LIMIT]
    if not reason:
        raise StatementError(f"{what} 이유를 적어 주세요. 협력사에게 보입니다.")
    return reason


def start_revision(db, statement_id: int, user_id: Optional[int], reason: Any) -> PartnerStatement:
    """수정본 — 발행본을 복사한 새 초안. 발행하기 전까지 협력사는 옛 명세서를 그대로 본다."""
    old = db.query(PartnerStatement).filter(PartnerStatement.id == statement_id).with_for_update().first()
    if old is None:
        raise StatementError("명세서를 찾을 수 없습니다.", 404)
    if old.status != ISSUED:
        raise StatementError("발행한 명세서만 수정본을 만들 수 있습니다.", 409)
    if draft_of(db, old.order_id) is not None:
        raise StatementError("이 주문에 고치는 중인 초안이 이미 있습니다. 그 초안을 먼저 발행하거나 지워 주세요.", 409)
    stmt = PartnerStatement(
        partner_org_id=old.partner_org_id, order_id=old.order_id, status=DRAFT, revision_of=old.id,
        price_list_id=old.price_list_id, statement_date=old.statement_date, drawing_round=old.drawing_round,
        drawing_keys=list(old.drawing_keys or []), groups=copy.deepcopy(old.groups or []), total=old.total,
        supply=old.supply, vat=old.vat, reason=_reason(reason, "수정본을 만드는"), created_by=user_id)
    db.add(stmt)
    db.flush()
    return stmt


def void(db, statement_id: int, user_id: Optional[int], reason: Any) -> PartnerStatement:
    """발행 취소 — 이유가 꼭 있어야 한다. 협력사 화면에는 "취소됨"과 이유가 보인다."""
    stmt = db.query(PartnerStatement).filter(PartnerStatement.id == statement_id).with_for_update().first()
    if stmt is None:
        raise StatementError("명세서를 찾을 수 없습니다.", 404)
    if stmt.status != ISSUED:
        raise StatementError("발행한 명세서만 취소할 수 있습니다.", 409)
    stmt.reason = _reason(reason, "취소하는")
    stmt.status, stmt.voided_at, stmt.voided_by = VOID, now_utc_naive(), user_id
    db.flush()
    return stmt


def discard_draft(db, statement_id: int, base_version: Any) -> int:
    """초안 지우기(발행 전만) → 주문 id."""
    stmt = locked_draft(db, statement_id, base_version)
    order_id = stmt.order_id
    db.delete(stmt)
    db.flush()
    return order_id


def bucket(on_date: Optional[datetime.date], today: Optional[datetime.date] = None) -> str:
    """발행 대기 갈래 — ``soon``(내일까지 · 지난 날 포함) · ``later`` · ``none``(출고일 없음)."""
    if on_date is None:
        return "none"
    today = today or get_today_kst()
    return "soon" if on_date <= today + datetime.timedelta(days=1) else "later"


def can_manage_statements(user: Any) -> bool:
    """명세서 만들기 · 발행 · 취소 = ADMIN, 또는 CS 권한 팀(회계팀 포함)의 STAFF · MANAGER(설계서 §6). 협력사 계정은 안 된다."""
    if user is None or getattr(user, "partner_org_id", None) is not None or getattr(user, "is_active", True) is False:
        return False
    role = str(getattr(user, "role", "") or "").strip().upper()
    if role == "ADMIN":
        return True
    return role in ("STAFF", "MANAGER") and team_has_capability(getattr(user, "team", None), ("CS",))

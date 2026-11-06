"""프리랜서 "내 수수료" 화면(``/erp/my-commission``) — 설계서 FCOMM-01 §2.2 · §9 · §11.2 (플랜 T7).

서버가 다 그린다(스크립트 없음). 줄 계산은 :func:`foms.services.sales_commission.read_model.commission_rows`
한 곳이고, 여기서는 화면 글(금액 · 상태 · 계산식 한 줄)만 만든다.

누가 보나:
- 켜진 프리랜서 → 언제나 본인 것. ``user_id`` 는 무시한다.
- 회계팀 · 관리자(:func:`~foms.services.settlement_channel_access.is_accounting_or_admin`) → ``?user_id=`` 로
  켜진 프리랜서 한 명을 대신 본다(없거나 프리랜서가 아니면 404).
- 그 밖(협력사 계정 포함) → 403.

템플릿 전역 함수 두 개도 여기서 붙인다 — ``context_processors.py`` 가 500줄 래칫에 닿아 있어서다.
둘 다 템플릿이 부를 때만 설정을 읽고, 요청 안에서는 flask ``g`` 에 한 번만 읽어 둔다.
- ``is_sales_freelancer()``: 지금 사용자가 켜진 프리랜서인지(모바일 서랍 "내 수수료" 링크).
- ``sales_freelancer_orderer_names()``: 켜진 프리랜서 맞출 이름 목록(발주사 선택지, D3).
"""
from __future__ import annotations

import re
from typing import Any, Optional

from flask import Blueprint, abort, g, render_template, request, url_for

from db import get_db
from foms.services.datetime_kst import get_today_kst
from foms.services.orders.order_mutation_policy import normalize_team, user_can_read_order
from foms.services.sales_commission import calc
from foms.services.sales_commission.closing import STATUS_PAID, closing_payload
from foms.services.sales_commission.export import DEAL_LABELS
from foms.services.sales_commission.read_model import (
    BASES,
    BASIS_COMPLETION,
    BASIS_MEASUREMENT,
    STATE_DONE,
    STATE_FORECAST,
    STATE_WAIT_COST,
    STATE_WAIT_RATE,
    commission_rows,
)
from foms.services.sales_commission.settings import active_freelancers, is_freelancer
from foms.services.settlement_channel_access import is_accounting_or_admin
from foms.web.auth import login_required
from models import Order, SalesCommissionClosing

sales_commission_web_bp = Blueprint("sales_commission_web", __name__, url_prefix="/erp")

RECENT_CLOSINGS = 6
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_DATE_RE = re.compile(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})")
_G_NAMES_ATTR = "_sales_freelancer_orderer_names"


# --------------------------------------------------------------------------
# 템플릿 전역 함수
# --------------------------------------------------------------------------
def is_sales_freelancer() -> bool:
    """지금 로그인한 사용자가 켜진 프리랜서인지(요청당 한 번 읽음)."""
    user = getattr(g, "current_user", None)
    if user is None or getattr(user, "partner_org_id", None) is not None:
        return False
    # 프리랜서는 STAFF · 영업팀 계정만 될 수 있다(설정 저장이 강제) — 그 밖은 설정을 읽지 않는다.
    if str(getattr(user, "role", "") or "").strip().upper() != "STAFF":
        return False
    if normalize_team(getattr(user, "team", None)) != "SALES":
        return False
    return is_freelancer(get_db(), user)


def sales_freelancer_orderer_names() -> list[str]:
    """켜진 프리랜서의 맞출 이름(가나다순) — 발주사 선택지에 숨고 다음으로 붙는다(D3). 요청당 한 번 읽음."""
    names = getattr(g, _G_NAMES_ATTR, None)
    if names is None:
        names = sorted({c.match_name for c in active_freelancers(get_db()).values() if c.match_name})
        setattr(g, _G_NAMES_ATTR, names)
    return list(names)


sales_commission_web_bp.add_app_template_global(is_sales_freelancer, "is_sales_freelancer")
sales_commission_web_bp.add_app_template_global(sales_freelancer_orderer_names, "sales_freelancer_orderer_names")


# --------------------------------------------------------------------------
# 화면 글 도우미
# --------------------------------------------------------------------------
def _shift_month(month: str, delta: int) -> str:
    index = int(month[:4]) * 12 + int(month[5:7]) - 1 + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _won(value: Optional[int]) -> str:
    return f"{int(value or 0):,}"


def _signed_won(value: Optional[int]) -> str:
    """조정 금액 — 더하면 "+6,000", 빼면 "−6,000"(계산식과 같은 빼기 기호)."""
    number = int(value or 0)
    sign = "+" if number > 0 else ("−" if number < 0 else "")
    return f"{sign}{abs(number):,}"


def _percent(bp: int) -> str:
    """basis point → "4%" · "4.5%" · "4.25%"."""
    return f"{bp / 100:.2f}".rstrip("0").rstrip(".") + "%"


def _short_date(text: Optional[str]) -> str:
    """"2030-02-10"(여러 날이면 첫 날) → "2월 10일". 못 읽으면 원본 글 그대로, 비었으면 빈 글."""
    if not text:
        return ""
    found = _DATE_RE.search(text)
    if not found:
        return text
    return f"{int(found.group(2))}월 {int(found.group(3))}일"


def _status_text(row: dict[str, Any]) -> str:
    state, commission = row["state"], row["commission"]
    if state == STATE_DONE:
        return f"{_won(commission)}원"
    if state == STATE_FORECAST:
        return f"예상 {_won(commission)}원" if commission is not None else "예상"
    if state == STATE_WAIT_COST or row["install_cost"] is None:
        return "시공비 기다림"
    return "요율 정하는 중"


def _formula(row: dict[str, Any]) -> str:
    """``출고가 2,500,000 − 시공비 1,000,000 − 차감 0 = 1,500,000 × 4% = 60,000원`` (못 셀 때는 까닭 한 마디)."""
    shipping, install, deduction = row["shipping_price"], row["install_cost"], int(row["deduction_total"] or 0)
    if shipping is None:
        return "출고가가 아직 없어요."
    if install is None:
        return f"출고가 {_won(shipping)}원 · 시공비가 들어오면 계산해요."
    base = max(0, int(shipping) - int(install) - deduction)
    head = f"출고가 {_won(shipping)} − 시공비 {_won(install)} − 차감 {_won(deduction)} = {_won(base)}"
    if row["rate_bp"] is None or row["commission"] is None:
        return f"{head}원 · 요율이 정해지면 계산해요."
    return f"{head} × {_percent(int(row['rate_bp']))} = {_won(row['commission'])}원"


def _row_view(row: dict[str, Any], basis: str) -> dict[str, Any]:
    date_text = row["construction_date"] if basis == BASIS_COMPLETION else row["measurement_date"]
    return {
        "customer_name": row["customer_name"],
        "date": _short_date(date_text),
        "deal": DEAL_LABELS.get(row["deal_type"], ""),
        "status": _status_text(row),
        "is_done": row["state"] == STATE_DONE,
        "formula": _formula(row),
        "deductions": [{"reason": d["reason"] or "사유 없음", "amount": _won(d["amount"])} for d in row["deductions"]],
    }


def _tax_line(total: int, tax_type: str, net: Optional[int] = None) -> str:
    """세금 뺀(부가세는 더한) 실제 금액 한 줄. 마감한 달은 굳힌 ``net`` 을 그대로 쓴다."""
    if total <= 0 or tax_type not in calc.TAX_TYPES or tax_type == calc.TAX_NONE:
        return ""
    if net is None:
        net = calc.tax_breakdown(total, tax_type)["net"]
    word = "부가세 더해" if tax_type == calc.TAX_VAT_10 else "세금 빼고"
    return f"{word} {_won(net)}원"


def _month_word(month: Optional[str]) -> str:
    """``"2030-02"`` → ``"2월"``. 못 읽으면 빈 글."""
    return f"{int(month[5:7])}월" if month and _MONTH_RE.match(month) else ""


def _line_view(line: dict[str, Any]) -> dict[str, Any]:
    """마감 스냅샷 줄 하나 → 화면 줄(마감 때 굳힌 값 그대로, 다시 계산하지 않는다).

    조정 줄(``ADJUST`` — 지난 마감 뒤 차감 · 시공비 · 품목이 바뀌어 생긴 차액)은 금액에 + · − 를 붙인다.
    """
    deal = DEAL_LABELS.get(line.get("deal_type"), "")
    adjust = line.get("kind") == "ADJUST"
    month_word = _month_word(line.get("completion_month"))
    return {
        "customer_name": line.get("label") or "-",
        "date": f"{month_word} 시공" if month_word else "",
        "deal": f"조정 · {deal}" if adjust else deal,
        "status": f"{_signed_won(line.get('commission')) if adjust else _won(line.get('commission'))}원",
        "is_done": True,
        "formula": f"지난 마감 뒤 바뀐 몫 {_signed_won(line.get('commission'))}원" if adjust else _formula(line),
        "deductions": [],
    }


def _closings(db, user_id: int) -> list[SalesCommissionClosing]:
    """한 프리랜서의 마감(최근 달 먼저) — 프리랜서 한 명은 한 해 12줄 남짓이라 한 번에 읽는다."""
    return (db.query(SalesCommissionClosing).filter(SalesCommissionClosing.user_id == user_id)
            .order_by(SalesCommissionClosing.month.desc(), SalesCommissionClosing.id.desc()).all())


def _recent_view(rows: list[SalesCommissionClosing], link) -> list[dict[str, str]]:
    """"지난 지급" — 달 · 실지급 · 지급 완료/마감. 달을 누르면 그 달 확정 화면."""
    return [{
        "label": f"{row.month[:4]}년 {_month_word(row.month)}",
        "net": f"{_won(row.net)}원",
        "status": "지급 완료" if row.status == STATUS_PAID else "마감",
        "url": link(month=row.month, basis=BASIS_COMPLETION),
    } for row in rows[:RECENT_CLOSINGS]]


# --------------------------------------------------------------------------
# 화면
# --------------------------------------------------------------------------
def _target_user_id(db, user: Any) -> tuple[int, bool]:
    """``(볼 프리랜서 id, 남의 것을 대신 보는지)``. 권한이 없으면 403, 대상이 프리랜서가 아니면 404."""
    if user is None or getattr(user, "partner_org_id", None) is not None:
        abort(403)
    if is_freelancer(db, user):
        return int(user.id), False
    if not is_accounting_or_admin(user):
        abort(403)
    target = request.args.get("user_id", type=int)
    if target is None or target not in active_freelancers(db):
        abort(404)
    return target, True


def _month_for_order(db, order_id: Optional[int], viewer: Any = None) -> Optional[tuple[str, str]]:
    """주문이 들어가는 달과 기준 — 시공 완료면 (시공 달, 시공 완료), 아니면 (실측 달, 실측일). 없으면 None.

    달만 정하고 주문 내용은 내보내지 않는다(남의 주문 번호를 넣어도 그 달의 내 줄만 보인다).
    """
    if not order_id:
        return None
    order = db.get(Order, order_id)
    # 볼 수 없는 주문이면 달조차 알려 주지 않는다(남의 주문 번호로 시공 달 · 완료 여부를 캐는 길 — T15 지적).
    if order is None or not user_can_read_order(viewer, order):
        return None
    fields = calc.extract_order_fields(order.structured_data if isinstance(order.structured_data, dict) else {})
    done = calc.completion_month(order.erp_stage_code, fields["construction_date"])
    if done:
        return done, BASIS_COMPLETION
    measured = calc.measurement_month(fields["measurement_date"], order.received_date, order.created_at)
    return (measured, BASIS_MEASUREMENT) if measured else None


@sales_commission_web_bp.route("/my-commission")
@login_required
def my_commission():
    """프리랜서 한 명 · 달 하나의 수수료(기본: 지난달 · 시공 완료 기준)."""
    db = get_db()
    target_id, on_behalf = _target_user_id(db, getattr(g, "current_user", None))
    this_month = get_today_kst().strftime("%Y-%m")
    last_month = _shift_month(this_month, -1)
    month = request.args.get("month", "")
    basis = request.args.get("basis", "")
    order_month = (_month_for_order(db, request.args.get("order", type=int), getattr(g, "current_user", None))
                   if not month else None)
    if order_month:  # 차감 알림에서 왔다 — 그 주문이 든 달을 연다(D17 · T8 스테이징 지적)
        month, basis = order_month
    month = month if _MONTH_RE.match(month) else last_month
    basis = basis if basis in BASES else BASIS_COMPLETION

    closings = _closings(db, target_id)
    closed = next((c for c in closings if c.month == month), None) if basis == BASIS_COMPLETION else None
    latest = closings[0].month if closings else None

    month_no = int(month[5:7])
    if basis == BASIS_MEASUREMENT:
        heading = f"{month_no}월 실측분 — 마감 전 줄은 예상이에요"
    elif month == last_month:
        heading = "이번 10일 받을 돈"
    else:
        heading = f"{month_no}월 시공 완료분"

    extra = {"user_id": target_id} if on_behalf else {}

    def link(**args: str) -> str:
        return url_for("sales_commission_web.my_commission", **{"month": month, "basis": basis, **args, **extra})

    if closed is not None:  # 마감한 달 — 굳힌 스냅샷만 보인다(회계팀 내려받기 파일과 같은 숫자)
        snap = closing_payload(closed)
        total = int(snap["gross"])
        view = {
            "heading": f"{heading} · 확정",
            "total_text": f"{_won(total)}원",
            "tax_line": _tax_line(total, snap["tax_type"], net=int(snap["net"])),
            "paid_text": f"지급 완료 {_short_date(snap['paid_at'])}" if snap["status"] == STATUS_PAID else "",
            "pending_note": "",
            "rows": [_line_view(line) for line in snap["lines"] if isinstance(line, dict)],
        }
        name = active_freelancers(db)[target_id].match_name if on_behalf else ""
    else:
        data = commission_rows(db, target_id, month, basis)
        rows = data["rows"]
        if basis == BASIS_MEASUREMENT:
            total = sum(int(r["commission"]) for r in rows
                        if r["commission"] is not None and r["state"] in (STATE_DONE, STATE_FORECAST))
        else:
            total = int(data["summary"]["total_commission"])
        # 이 달보다 늦은 마감이 있으면 이 달 몫은 이미 그 마감에 들어갔다 — "마감 전" 이 아니다.
        unclosed = basis == BASIS_COMPLETION and (latest is None or latest < month)
        view = {
            "heading": heading,
            "total_text": f"{_won(total)}원",
            "tax_line": _tax_line(total, data["freelancer"]["tax_type"]),
            "paid_text": "",
            "pending_note": "아직 마감 전이라 바뀔 수 있어요." if unclosed else "",
            "rows": [_row_view(r, basis) for r in rows],
        }
        name = data["freelancer"]["match_name"] if on_behalf else ""

    next_month = _shift_month(month, 1)
    return render_template(
        "sales_commission/my_commission.html",
        **view,
        viewing_name=name,
        month_label=f"{month[:4]}년 {month_no}월",
        prev_url=link(month=_shift_month(month, -1)),
        # 마감 뒤 넘어간 줄(시공비 기다림)은 다음 달 화면에 나오므로 이번 달 다음 달까지 갈 수 있게 둔다(T11).
        next_url=link(month=next_month) if next_month <= _shift_month(this_month, 1) else "",
        basis_links=[
            {"label": "시공 완료 기준", "url": link(basis=BASIS_COMPLETION), "active": basis == BASIS_COMPLETION},
            {"label": "실측일 기준", "url": link(basis=BASIS_MEASUREMENT), "active": basis == BASIS_MEASUREMENT},
        ],
        recent=_recent_view(closings, link),
    )

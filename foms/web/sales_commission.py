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
from foms.services.sales_commission import calc
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

sales_commission_web_bp = Blueprint("sales_commission_web", __name__, url_prefix="/erp")

DEAL_LABELS = {
    calc.DEAL_LAHOM: "라홈",
    calc.DEAL_HAUD: "하우드",
    calc.DEAL_PERSONAL: "개인영업",
    calc.DEAL_MANUAL: "회계팀 지정",
}
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
    if state == STATE_FORECAST and commission is not None:
        return f"예상 {_won(commission)}원"
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


def _tax_line(total: int, tax_type: str) -> str:
    if total <= 0 or tax_type not in calc.TAX_TYPES or tax_type == calc.TAX_NONE:
        return ""
    net = calc.tax_breakdown(total, tax_type)["net"]
    word = "부가세 더해" if tax_type == calc.TAX_VAT_10 else "세금 빼고"
    return f"{word} {_won(net)}원"


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


@sales_commission_web_bp.route("/my-commission")
@login_required
def my_commission():
    """프리랜서 한 명 · 달 하나의 수수료(기본: 지난달 · 시공 완료 기준)."""
    db = get_db()
    target_id, on_behalf = _target_user_id(db, getattr(g, "current_user", None))
    this_month = get_today_kst().strftime("%Y-%m")
    last_month = _shift_month(this_month, -1)
    month = request.args.get("month", "")
    month = month if _MONTH_RE.match(month) else last_month
    basis = request.args.get("basis", "")
    basis = basis if basis in BASES else BASIS_COMPLETION

    data = commission_rows(db, target_id, month, basis)
    rows = data["rows"]
    if basis == BASIS_MEASUREMENT:
        total = sum(int(r["commission"]) for r in rows
                    if r["commission"] is not None and r["state"] in (STATE_DONE, STATE_FORECAST))
    else:
        total = int(data["summary"]["total_commission"])

    month_no = int(month[5:7])
    if basis == BASIS_MEASUREMENT:
        heading = f"{month_no}월 실측 — 앞으로 들어올 돈 미리 보기"
    elif month == last_month:
        heading = "이번 10일 받을 돈"
    else:
        heading = f"{month_no}월 시공 완료분"

    extra = {"user_id": target_id} if on_behalf else {}

    def link(**args: str) -> str:
        return url_for("sales_commission_web.my_commission", **{"month": month, "basis": basis, **args, **extra})

    next_month = _shift_month(month, 1)
    return render_template(
        "sales_commission/my_commission.html",
        heading=heading,
        total_text=("예상 " if basis == BASIS_MEASUREMENT else "") + f"{_won(total)}원",
        tax_line=_tax_line(total, data["freelancer"]["tax_type"]),
        viewing_name=data["freelancer"]["match_name"] if on_behalf else "",
        month_label=f"{month[:4]}년 {month_no}월",
        prev_url=link(month=_shift_month(month, -1)),
        next_url=link(month=next_month) if next_month <= this_month else "",
        basis_links=[
            {"label": "시공 완료 기준", "url": link(basis=BASIS_COMPLETION), "active": basis == BASIS_COMPLETION},
            {"label": "실측일 기준", "url": link(basis=BASIS_MEASUREMENT), "active": basis == BASIS_MEASUREMENT},
        ],
        rows=[_row_view(r, basis) for r in rows],
    )

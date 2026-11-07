"""프리랜서 영업 수수료 조정 줄(설계서 FCOMM-01 §8.2 · J9 — 플랜 T12).

프리랜서 F 의 달을 마감할 때, F 의 앞선 마감에 들어간 모든 주문을 **지금 값**으로 다시 계산한다.
``지금 값 − 지금까지 그 주문에 마감된 줄 합(일반 + 조정)`` 이 0 이 아니면 그 차액이 조정 줄(``ADJUST``)이다.
조정은 매 마감마다 처음부터 다시 센다 — 마감하지 못한 달의 차액은 다음 마감에서 저절로 다시 나온다.

- 주인 · 거래구분은 그 주문의 첫 일반 줄에 굳힌 값(J9). 지금의 대표 담당 · 발주사는 다시 보지 않는다 — 마감 뒤
  대표 담당이 G 로 바뀌어도 조정은 F 의 마감에서만 생기고, G 에게는 어떤 줄도 가지 않는다.
- 요율도 굳힌 값이다. 단 회계팀 지정 요율(``rate_override_bp``)이 지금 있고 굳힌 값과 다르면 그 값을 쓴다
  (J9 "회계팀 지정 요율이 바뀐 경우만 새 값"). 지정 요율을 지운 경우와 요율 이력 표가 바뀐 경우는 굳힌 값 그대로.
- 지금 값 = 출고가(취소 품목 뺌, :func:`calc.commission_shipping_price`) · 시공비 · F 에게 붙은 유효 영업 차감.
- 다시 계산하지 않는 주문은 ``skipped`` 로 알린다(회계팀이 미리 보기에서 본다): 지워졌거나 대상 밖으로 빠짐
  (``GONE``) · 메인 단계가 시공 완료(CS · COMPLETED)에서 되돌아감(``STAGE``) · 시공비가 빈칸이 됨(``WAIT_COST``) ·
  출고가를 낼 수 없음(``NO_PRICE``). 이미 준 돈은 저절로 되돌리지 않는다(§8.2) — 필요하면 회계팀이 차감으로 처리.
- 조회는 고정이다: F 의 마감 1번 · 주문 1번 · 시공비 입력 1번(:func:`read_model.current_values`). 주문마다 묻지 않는다.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from foms.services.sales_commission import calc
from foms.services.sales_commission.read_model import current_values
from models import SalesCommissionClosing

__all__ = [
    "KIND_ADJUST",
    "KIND_NORMAL",
    "SKIP_LABELS",
    "adjust_line",
    "compute_adjustments",
    "frozen_by_order",
    "line_label",
]

KIND_NORMAL = "NORMAL"
KIND_ADJUST = "ADJUST"

SKIP_GONE = "GONE"
SKIP_STAGE = "STAGE"
SKIP_WAIT_COST = "WAIT_COST"
SKIP_NO_PRICE = "NO_PRICE"
#: 미리 보기 확인 창에 그대로 보일 말(사람 말).
SKIP_LABELS = {
    SKIP_GONE: "지워진 주문",
    SKIP_STAGE: "단계가 되돌려진 주문",
    SKIP_WAIT_COST: "시공비가 빈 주문",
    SKIP_NO_PRICE: "출고가가 없는 주문",
}


def line_label(row: dict[str, Any]) -> str:
    """내려받기 · 화면용 "고객명 · 품목" 스냅샷(일반 줄 · 조정 줄 공통)."""
    parts = [str(row.get("customer_name") or "").strip(), str(row.get("product_summary") or "").strip()]
    return " · ".join(p for p in parts if p) or "-"


def frozen_by_order(closing_lines: Iterable[Any]) -> dict[int, dict[str, Any]]:
    """한 프리랜서의 마감 줄 목록들(달 오름차순) → 주문별 ``{"base": 첫 일반 줄, "paid": 마감된 줄 합}``.

    일반 줄이 없는 주문(정상 경로에서는 없다)은 처음 본 줄을 굳힌 값으로 쓴다.
    """
    out: dict[int, dict[str, Any]] = {}
    for lines in closing_lines:
        for line in lines if isinstance(lines, list) else []:
            order_id = calc._as_int(line.get("order_id")) if isinstance(line, dict) else None
            if order_id is None:
                continue
            entry = out.setdefault(order_id, {"base": line, "paid": 0})
            entry["paid"] += calc._as_int(line.get("commission")) or 0
            if entry["base"].get("kind") != KIND_NORMAL and line.get("kind") == KIND_NORMAL:
                entry["base"] = line
    return out


def _rate_now(base: dict[str, Any], now: dict[str, Any]) -> int:
    """굳힌 요율. 회계팀 지정 요율이 지금 있고 다르면 그 값(J9)."""
    override = calc._as_int(now.get("rate_override_bp"))
    return override if override is not None else int(calc._as_int(base.get("rate_bp")) or 0)


def adjust_line(order_id: int, base: dict[str, Any], paid: int,
                now: Optional[dict[str, Any]]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """주문 한 건 → ``(조정 줄 또는 None, 빠진 까닭 또는 None)``. 쿼리 없음.

    Args:
        order_id: 주문 번호.
        base: 그 주문의 첫 일반 줄(굳힌 거래구분 · 요율 · 시공 완료 달).
        paid: 지금까지 그 주문에 마감된 줄 합(일반 + 조정).
        now: :func:`read_model.current_values` 의 그 주문 값. 없으면 지워졌거나 대상 밖이다.
    """
    if now is None:
        return None, SKIP_GONE
    if not now["stage_done"]:
        return None, SKIP_STAGE
    if now["install_cost"] is None:
        return None, SKIP_WAIT_COST
    rate_bp = _rate_now(base, now)
    value = calc.line_commission(now["shipping_price"], now["install_cost"], now["deduction_total"], rate_bp)
    if value is None:
        return None, SKIP_NO_PRICE
    delta = int(value) - int(paid)
    if delta == 0:
        return None, None
    return {
        "order_id": int(order_id),
        "kind": KIND_ADJUST,
        "deal_type": base.get("deal_type"),
        "shipping_price": int(now["shipping_price"]),
        "install_cost": int(now["install_cost"]),
        "deduction_total": int(now["deduction_total"] or 0),
        "rate_bp": rate_bp,
        "commission": delta,
        "label": line_label(now),
        "completion_month": base.get("completion_month"),
    }, None


def compute_adjustments(db, user_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """프리랜서 한 명의 조정 줄과 빠진 주문 ``(lines, skipped)``. 앞선 마감이 없으면 둘 다 빈 목록.

    ``skipped`` 한 줄 = ``{order_id, reason, reason_text, label(굳힌 값), completion_month}``.
    """
    uid = int(user_id)
    rows = (db.query(SalesCommissionClosing.lines).filter(SalesCommissionClosing.user_id == uid)
            .order_by(SalesCommissionClosing.month.asc(), SalesCommissionClosing.id.asc()).all())
    frozen = frozen_by_order(lines for (lines,) in rows)
    if not frozen:
        return [], []
    now_by_id = current_values(db, frozen.keys(), uid)
    lines: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for order_id in sorted(frozen):
        base, paid = frozen[order_id]["base"], frozen[order_id]["paid"]
        line, reason = adjust_line(order_id, base, paid, now_by_id.get(order_id))
        if line is not None:
            lines.append(line)
        elif reason is not None:
            skipped.append({"order_id": order_id, "reason": reason, "reason_text": SKIP_LABELS[reason],
                            "label": str(base.get("label") or "-"),
                            "completion_month": base.get("completion_month")})
    lines.sort(key=lambda item: (str(item.get("completion_month") or ""), item["order_id"]))
    return lines, skipped

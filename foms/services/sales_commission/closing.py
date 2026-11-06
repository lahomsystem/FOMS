"""프리랜서 영업 수수료 달 마감 · 지급 완료 · 마감 취소(설계서 FCOMM-01 §4.3 · §8 · J9 — 플랜 T9).

회계팀이 매월 10일에 프리랜서 F 의 지난달(M)까지 몫을 마감한다.

- 마감 줄 = 시공 완료 기준 줄(:func:`~foms.services.sales_commission.read_model.commission_rows`) 중 계산이 끝난
  ``DONE`` 줄. 시공 완료 달 ≤ M 이고 아직 **누구의** 마감에도 없는 주문이다 — 시공비(``WAIT_COST``) · 요율
  (``WAIT_RATE``)을 기다리는 줄은 빠지고, 값이 들어간 뒤의 마감에 저절로 들어간다(넘김 칸 없음, 검수 A15).
  시작 달(D8)이 아래 한계라 엑셀로 지급한 달은 들어오지 않는다.
- 줄은 마감 때 값으로 굳힌다(``lines`` 스냅샷). 한 번 마감에 들어간 주문은 뒤에 대표 담당 · 발주사가 바뀌어도
  누구의 일반 줄에도 다시 나오지 않는다(J9, 검수 A14). 그 뒤 바뀐 금액은 다음 마감의 조정 줄(``ADJUST``) 몫이다 —
  :func:`foms.services.sales_commission.adjust.compute_adjustments` 가 F 의 앞선 마감 주문을 굳힌 주인 · 거래구분 ·
  요율로 다시 계산해 차액을 싣는다(§8.2 · T12). 지워졌거나 단계가 되돌려진 주문은 조정하지 않고 미리 보기에 알린다.
- 달은 오름차순으로만 마감한다. 마감 · 마감 취소는 트랜잭션 맨 앞에서 설정 줄(``SystemSetting``)을 ``FOR UPDATE``
  로 잡아 줄 세운다 — 같은 F 의 두 달 동시 마감 · 마감과 취소의 엇갈림을 막는다(검수 A16).
- 합계(일반 + 조정)가 0 이하면 마감하지 않는다. 세금은 합계에 한 번 매긴다(§3.5, :func:`calc.tax_breakdown`).
- CLOSED → PAID(지급 완료, 그 뒤로는 못 되돌림). 지급 전 마감 취소는 그 프리랜서의 **가장 최근** 마감만 —
  줄을 지우고 감사 기록에 합계 · 줄 수 · 주문 번호 · 이유를 남긴다(VOID 상태 없음).

커밋은 부르는 쪽(API 핸들러)이 한다. 거부는 :class:`ClosingError`(화면에 그대로 보일 한글 문장 + HTTP 코드).
감사 기록 ``detail`` 에는 고객명이 든 ``label`` 을 싣지 않는다(감사 원장 PII 금지) — 주문 번호만 싣는다.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError

from foms.services.datetime_kst import format_datetime_kst, get_today_kst, now_utc_naive
from foms.services.sales_commission import calc
from foms.services.sales_commission.adjust import KIND_ADJUST, KIND_NORMAL, compute_adjustments, line_label
from foms.services.sales_commission.read_model import (
    BASIS_COMPLETION,
    STATE_DONE,
    STATE_WAIT_COST,
    STATE_WAIT_RATE,
    commission_rows,
)
from foms.services.sales_commission.settings import (
    FreelancerConfig,
    active_freelancers,
    latest_closed_month,
    load_settings_locked,
)
from models import SalesCommissionClosing, SecurityLog

__all__ = [
    "ClosingError",
    "KIND_ADJUST",
    "KIND_NORMAL",
    "STATUS_CLOSED",
    "STATUS_PAID",
    "cancel_closing",
    "close_month",
    "closing_for_month",
    "closing_payload",
    "current_month_kst",
    "list_closings",
    "mark_paid",
    "preview_closing",
]

STATUS_CLOSED = "CLOSED"
STATUS_PAID = "PAID"
REASON_MAX = 500
TARGET_TYPE = "sales_commission_closing"
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_WAITING_STATES = (STATE_WAIT_COST, STATE_WAIT_RATE)

MSG_NOT_FREELANCER = "켜진 프리랜서가 아니에요."
MSG_FUTURE = "아직 오지 않은 달은 마감할 수 없어요."
MSG_NOTHING = "이번 달은 줄 돈이 없어요."
MSG_PAID_LOCKED = "지급한 마감은 되돌릴 수 없어요."


class ClosingError(ValueError):
    """화면에 그대로 보일 수 있는 거부 이유. ``status`` 는 HTTP 코드(409 = 순서 · 상태가 맞지 않음)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------
# 작은 도우미
# --------------------------------------------------------------------------
def current_month_kst() -> str:
    """오늘(한국 시각)의 ``YYYY-MM``."""
    today = get_today_kst()
    return f"{today.year:04d}-{today.month:02d}"


def _check_month(month: Any) -> str:
    text = str(month or "").strip()
    if not _MONTH_RE.match(text):
        raise ClosingError("달은 2026-11 처럼 연도-월로 적어 주세요.")
    return text


def _check_user_id(user_id: Any) -> int:
    if isinstance(user_id, bool):
        raise ClosingError("프리랜서를 골라 주세요.")
    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise ClosingError("프리랜서를 골라 주세요.") from None


def _normal_line(row: dict[str, Any]) -> dict[str, Any]:
    """``DONE`` 줄 하나 → 굳힌 마감 줄(§4.3 줄 모양 + 시공 완료 달)."""
    return {
        "order_id": int(row["order_id"]),
        "kind": KIND_NORMAL,
        "deal_type": row["deal_type"],
        "shipping_price": int(row["shipping_price"] or 0),
        "install_cost": int(row["install_cost"] or 0),
        "deduction_total": int(row["deduction_total"] or 0),
        "rate_bp": int(row["rate_bp"] or 0),
        "commission": int(row["commission"] or 0),
        "label": line_label(row),
        "completion_month": row.get("completion_month"),
    }


def _compute(db, cfg: FreelancerConfig, month: str) -> dict[str, Any]:
    """마감 줄 · 합계 · 세금 · 기다리는 줄 · 조정에서 빠진 주문(쿼리는 :func:`commission_rows` 한 번 + 조정 3번).

    조정 줄(§8.2)은 F 의 앞선 마감 전부를 다시 센다 — 첫 마감은 앞선 마감이 없어 조정이 없다.
    """
    data = commission_rows(db, cfg.user_id, month, BASIS_COMPLETION)
    normal: list[dict[str, Any]] = []
    waiting: list[dict[str, Any]] = []
    for row in data["rows"]:
        if row["state"] == STATE_DONE:
            normal.append(_normal_line(row))
        elif row["state"] in _WAITING_STATES:
            waiting.append({"order_id": int(row["order_id"]), "state": row["state"], "label": line_label(row),
                            "completion_month": row.get("completion_month")})
    adjust, skipped = compute_adjustments(db, cfg.user_id)
    lines = normal + adjust
    gross = sum(int(line["commission"]) for line in lines)  # 일반 + 조정. 0 이하면 마감 거부(§8.1)
    totals = calc.tax_breakdown(gross, cfg.tax_type)
    counts = {state: sum(1 for w in waiting if w["state"] == state) for state in _WAITING_STATES}
    return {"lines": lines, "totals": totals, "waiting": waiting, "waiting_counts": counts,
            "adjust_skipped": skipped}


def _block_reason(db, user_id: int, month: str, gross: int) -> Optional[tuple[str, int]]:
    """마감을 막는 이유 ``(문장, HTTP 코드)``. 막을 것이 없으면 None — 미리 보기와 마감이 같은 규칙을 쓴다."""
    if month > current_month_kst():
        return MSG_FUTURE, 400
    latest = latest_closed_month(db, user_id)
    if latest is not None and latest >= month:
        return f"이미 그 뒤 달까지 마감했어요({latest} 마감 있음). 그 다음 달만 마감할 수 있어요.", 409
    if gross <= 0:
        return MSG_NOTHING, 400
    return None


def _check_tax_type(cfg: FreelancerConfig) -> None:
    if cfg.tax_type not in calc.TAX_TYPES:
        raise ClosingError("세금 방식이 비었어요. 프리랜서 설정에서 골라 주세요.")


def closing_payload(row: SalesCommissionClosing, *, with_lines: bool = True) -> dict[str, Any]:
    """마감 한 줄을 응답 모양으로. 때는 한국 시각 글자."""
    lines = row.lines if isinstance(row.lines, list) else []
    out = {
        "id": int(row.id),
        "user_id": int(row.user_id),
        "month": row.month,
        "status": row.status,
        "gross": int(row.gross or 0),
        "tax_income": int(row.tax_income or 0),
        "tax_local": int(row.tax_local or 0),
        "vat": int(row.vat or 0),
        "net": int(row.net or 0),
        "tax_type": row.tax_type,
        "line_count": len(lines),
        "closed_by_user_id": row.closed_by_user_id,
        "closed_at": format_datetime_kst(row.closed_at, "%Y-%m-%d %H:%M"),
        "paid_by_user_id": row.paid_by_user_id,
        "paid_at": format_datetime_kst(row.paid_at, "%Y-%m-%d %H:%M"),
    }
    if with_lines:
        out["lines"] = lines
    return out


def _audit_detail(row: SalesCommissionClosing) -> dict[str, Any]:
    """감사 기록용 요약 — 합계 · 세금 · 줄 수 · 주문 번호(고객명 든 label 은 뺀다)."""
    payload = closing_payload(row, with_lines=False)
    lines = row.lines if isinstance(row.lines, list) else []
    payload["order_ids"] = [line.get("order_id") for line in lines if isinstance(line, dict)]
    return payload


def _locked_closing(db, closing_id: Any) -> SalesCommissionClosing:
    try:
        cid = int(closing_id)
    except (TypeError, ValueError):
        raise ClosingError("마감을 찾을 수 없어요.", 404) from None
    row = (db.query(SalesCommissionClosing).filter(SalesCommissionClosing.id == cid)
           .with_for_update().first())
    if row is None:
        raise ClosingError("마감을 찾을 수 없어요.", 404)
    return row


# --------------------------------------------------------------------------
# 읽기
# --------------------------------------------------------------------------
def preview_closing(db, user_id: Any, month: Any) -> dict[str, Any]:
    """마감하면 들어갈 줄 · 합계 · 세금 미리 보기(쓰기 없음).

    Returns:
        ``{user_id, month, tax_type, lines, adjust_count, adjust_total, adjust_skipped[],
        totals{gross, tax_income, tax_local, vat, net}, waiting[], waiting_counts{WAIT_COST, WAIT_RATE},
        latest_closed_month, can_close, block_reason}``. ``adjust_skipped`` 는 앞선 마감에 있지만 지금 다시 셀 수
        없어 조정하지 않는 주문(``{order_id, reason, reason_text, label, completion_month}``).

    Raises:
        ClosingError: 달 형식이 틀렸거나(400) 켜진 프리랜서가 아니다(404).
    """
    month = _check_month(month)
    uid = _check_user_id(user_id)
    cfg = active_freelancers(db).get(uid)
    if cfg is None:
        raise ClosingError(MSG_NOT_FREELANCER, 404)
    _check_tax_type(cfg)
    result = _compute(db, cfg, month)
    block = _block_reason(db, uid, month, result["totals"]["gross"])
    adjust = [line for line in result["lines"] if line["kind"] == KIND_ADJUST]
    return {
        "user_id": uid,
        "month": month,
        "tax_type": cfg.tax_type,
        "lines": result["lines"],
        "adjust_count": len(adjust),
        "adjust_total": sum(int(line["commission"]) for line in adjust),
        "adjust_skipped": result["adjust_skipped"],
        "totals": result["totals"],
        "waiting": result["waiting"],
        "waiting_counts": result["waiting_counts"],
        "latest_closed_month": latest_closed_month(db, uid),
        "can_close": block is None,
        "block_reason": block[0] if block else None,
    }


def closing_for_month(db, user_id: Any, month: Any) -> Optional[dict[str, Any]]:
    """한 프리랜서 · 달 하나의 마감(줄 스냅샷 포함). 형식이 틀렸거나 마감이 없으면 None — 내려받기 · 내 수수료가 쓴다."""
    try:
        uid, text = _check_user_id(user_id), _check_month(month)
    except ClosingError:
        return None
    row = (db.query(SalesCommissionClosing)
           .filter(SalesCommissionClosing.user_id == uid, SalesCommissionClosing.month == text).first())
    return closing_payload(row) if row is not None else None


def list_closings(db, user_id: Any) -> list[dict[str, Any]]:
    """한 프리랜서의 마감 목록(최근 달 먼저). 꺼진 프리랜서의 지난 마감도 보인다."""
    uid = _check_user_id(user_id)
    rows = (db.query(SalesCommissionClosing).filter(SalesCommissionClosing.user_id == uid)
            .order_by(SalesCommissionClosing.month.desc(), SalesCommissionClosing.id.desc()).all())
    return [closing_payload(row) for row in rows]


# --------------------------------------------------------------------------
# 쓰기 — 커밋은 부르는 쪽
# --------------------------------------------------------------------------
def close_month(db, user_id: Any, month: Any, *, actor_user_id: Any) -> SalesCommissionClosing:
    """프리랜서 한 명의 달 M 을 마감한다(줄 스냅샷 + 합계 + 세금 + 감사, 한 트랜잭션).

    Raises:
        ClosingError: 형식(400) · 앞으로 올 달(400) · 켜진 프리랜서 아님(404) · 이미 M 이상 마감 있음(409) ·
        합계 0 이하(400).
    """
    month = _check_month(month)
    uid = _check_user_id(user_id)
    if month > current_month_kst():
        raise ClosingError(MSG_FUTURE)
    _version, configs = load_settings_locked(db)  # 같은 프리랜서의 마감 · 취소를 줄 세운다(§8.1)
    cfg = configs.get(uid)
    if cfg is None or not cfg.active:
        raise ClosingError(MSG_NOT_FREELANCER, 404)
    _check_tax_type(cfg)
    result = _compute(db, cfg, month)
    totals = result["totals"]
    block = _block_reason(db, uid, month, totals["gross"])
    if block is not None:
        raise ClosingError(*block)
    row = SalesCommissionClosing(
        user_id=uid, month=month, status=STATUS_CLOSED, gross=totals["gross"], tax_income=totals["tax_income"],
        tax_local=totals["tax_local"], vat=totals["vat"], net=totals["net"], tax_type=cfg.tax_type,
        lines=result["lines"], closed_by_user_id=_actor_id(actor_user_id),
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:  # 잠금 밖에서 같은 달이 먼저 들어간 경우(정상 경로에선 위 순서 검사가 먼저 막는다)
        raise ClosingError("그사이 다른 사람이 이 달을 마감했어요. 새로 고친 뒤 다시 봐 주세요.", 409) from exc
    detail = _audit_detail(row)
    # 조정에서 빠진 주문(지워짐 · 단계 되돌림 · 시공비 빈칸)도 남긴다 — 번호와 까닭만(고객명 없음).
    detail["adjust_skipped"] = [{"order_id": s["order_id"], "reason": s["reason"]} for s in result["adjust_skipped"]]
    db.add(SecurityLog(
        user_id=_actor_id(actor_user_id), action="SALES_COMMISSION_CLOSED", target_type=TARGET_TYPE,
        target_id=row.id, message=f"영업 수수료 마감: {cfg.match_name} {month} · 줄 {len(result['lines'])}개",
        detail=detail,
    ))
    db.flush()
    return row


def mark_paid(db, closing_id: Any, *, actor_user_id: Any) -> SalesCommissionClosing:
    """CLOSED → PAID. 이미 PAID 면 409. 지급 완료 뒤로는 마감 취소가 막힌다."""
    row = _locked_closing(db, closing_id)
    if row.status == STATUS_PAID:
        raise ClosingError("이미 지급 완료로 바꾼 마감이에요.", 409)
    row.status = STATUS_PAID
    row.paid_by_user_id = _actor_id(actor_user_id)
    row.paid_at = now_utc_naive()
    db.add(SecurityLog(
        user_id=_actor_id(actor_user_id), action="SALES_COMMISSION_PAID", target_type=TARGET_TYPE,
        target_id=row.id, message=f"영업 수수료 지급 완료: 프리랜서 {row.user_id} {row.month}",
        detail=_audit_detail(row),
    ))
    db.flush()
    return row


def cancel_closing(db, closing_id: Any, *, actor_user_id: Any, reason: Any) -> dict[str, Any]:
    """지급 전 마감 취소 = 줄 삭제 + 감사(합계 · 줄 수 · 주문 번호 · 이유). 지운 마감의 요약을 돌려준다.

    Raises:
        ClosingError: 이유 없음(400) · 없음(404) · 이미 지급(409) · 가장 최근 마감이 아님(409).
    """
    text = str(reason or "").strip() if isinstance(reason, (str, type(None))) else ""
    if not text:
        raise ClosingError("취소 이유를 적어 주세요.")
    if len(text) > REASON_MAX:
        raise ClosingError(f"취소 이유는 {REASON_MAX}자까지 적을 수 있어요.")
    load_settings_locked(db)  # 마감과 엇갈리지 않게 같은 줄을 잡는다
    row = _locked_closing(db, closing_id)
    if row.status == STATUS_PAID:
        raise ClosingError(MSG_PAID_LOCKED, 409)
    latest = latest_closed_month(db, row.user_id)
    if latest != row.month:
        raise ClosingError(f"가장 최근 마감({latest})부터 차례로 취소할 수 있어요.", 409)
    detail = _audit_detail(row)
    detail["reason"] = text
    db.add(SecurityLog(
        user_id=_actor_id(actor_user_id), action="SALES_COMMISSION_CLOSING_CANCELLED", target_type=TARGET_TYPE,
        target_id=row.id, message=f"영업 수수료 마감 취소: 프리랜서 {row.user_id} {row.month}",
        detail=detail,
    ))
    snapshot = closing_payload(row, with_lines=False)
    db.delete(row)
    db.flush()
    return snapshot


def _actor_id(actor_user_id: Any) -> Optional[int]:
    try:
        return int(actor_user_id) if actor_user_id is not None else None
    except (TypeError, ValueError):
        return None

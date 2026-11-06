"""프리랜서 영업 수수료 탭 JSON API(설계서 FCOMM-01 §2.1 · §9 · §11.2 — 플랜 T5).

- ``GET /api/sales-commission/freelancers`` — 탭의 프리랜서 고르기용 켜진 프리랜서 목록.
- ``GET /api/sales-commission/rows?user_id=&month=YYYY-MM&basis=completion|measurement`` — 줄 · 합계 ·
  "비슷한 이름" 경고(:func:`foms.services.sales_commission.read_model.commission_rows`).
- ``PUT /api/sales-commission/inputs/<order_id>`` ``{install_cost, rate_override_bp, note, version}`` — 시공비 ·
  회계팀 지정 요율 · 메모 저장. 본문에 없는 칸은 그대로 둔다(칸마다 자동 저장). version 이 다르면 409.
- 달 마감(2단계 T9, :mod:`foms.services.sales_commission.closing`): ``GET /closings?user_id=`` 목록 ·
  ``GET /closings/preview?user_id=&month=`` 미리 보기 · ``POST /closings`` ``{user_id, month}`` 마감 ·
  ``POST /closings/<id>/paid`` 지급 완료 · ``DELETE /closings/<id>`` ``{reason}`` 지급 전 마감 취소.

권한은 정산 화면과 같다 — :func:`~foms.services.settlement_channel_access.is_accounting_or_admin`(ADMIN,
MANAGER/STAFF + 회계팀). 협력사 계정 · 프리랜서(STAFF + 영업팀)는 거부된다. 쓰기는 공용 CSRF · Origin 가드 뒤이고
정책 manifest 의 ``SALES_COMMISSION_WRITE`` 와 함께 핸들러가 한 번 더 본다. 응답은 ``{"success", "data", "error"}``.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from db import get_db
from foms.services.datetime_kst import get_today_kst
from foms.services.sales_commission.closing import (
    ClosingError,
    cancel_closing,
    close_month,
    closing_payload,
    list_closings,
    mark_paid,
    preview_closing,
)
from foms.services.sales_commission.read_model import (
    BASES,
    BASIS_COMPLETION,
    commission_row_for_order,
    commission_rows,
    input_payload,
)
from foms.services.sales_commission.settings import active_freelancers
from foms.services.settlement_channel_access import is_accounting_or_admin
from models import Order, SalesCommissionInput, SecurityLog

logger = logging.getLogger(__name__)

sales_commission_api_bp = Blueprint("sales_commission_api", __name__, url_prefix="/api/sales-commission")

NOTE_MAX = 500
BP_MAX = 10000
INSTALL_COST_MAX = 10 ** 12  # BIGINT 안 · 화면 실수(0 몇 개 더) 막기
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_INPUT_FIELDS = ("install_cost", "rate_override_bp", "note")
_STALE = "그사이 다른 사람이 고쳤어요. 다시 불러와 주세요."
_SAVE_FAILED = "저장하지 못했어요. 잠시 뒤 다시 해 주세요."


def _ok(data: Any, status: int = 200):
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response, status


def _fail(status: int, error: str, data: Any = None):
    return jsonify({"success": False, "data": data, "error": error}), status


def _accounting_user() -> tuple[Optional[Any], Optional[tuple[Any, int]]]:
    """회계팀 · 관리자만(정산 화면과 같은 게이트). 협력사 계정은 role 과 무관하게 거부."""
    user = getattr(g, "current_user", None)
    if user is None or getattr(user, "is_active", None) is False:
        return None, _fail(401, "로그인이 필요해요.")
    if not is_accounting_or_admin(user) or getattr(user, "partner_org_id", None) is not None:
        return None, _fail(403, "회계팀과 관리자만 볼 수 있어요.")
    return user, None


def _last_month() -> str:
    today = get_today_kst()
    year, month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    return f"{year:04d}-{month:02d}"


@sales_commission_api_bp.route("/freelancers", methods=["GET"], endpoint="list_freelancers")
def api_list_freelancers():
    """탭의 프리랜서 고르기 — 켜진 프리랜서만, 맞출 이름 순."""
    _actor, denied = _accounting_user()
    if denied:
        return denied
    db = get_db()
    configs = active_freelancers(db)
    db.rollback()
    data = [{"user_id": c.user_id, "match_name": c.match_name, "start_month": c.start_month}
            for c in sorted(configs.values(), key=lambda c: (c.match_name, c.user_id))]
    return _ok({"freelancers": data, "default_month": _last_month()})


@sales_commission_api_bp.route("/rows", methods=["GET"], endpoint="list_rows")
def api_list_rows():
    """프리랜서 한 명 · 달 하나의 수수료 줄(읽기만)."""
    _actor, denied = _accounting_user()
    if denied:
        return denied
    raw_user = (request.args.get("user_id") or "").strip()
    month = (request.args.get("month") or "").strip() or _last_month()
    basis = (request.args.get("basis") or "").strip() or BASIS_COMPLETION
    if not raw_user.isdigit():
        return _fail(400, "프리랜서를 골라 주세요.")
    if not _MONTH_RE.match(month):
        return _fail(400, "달은 2026-11 처럼 연도-월로 적어 주세요.")
    if basis not in BASES:
        return _fail(400, "기준은 시공 완료 또는 실측일 중에서 골라 주세요.")
    user_id = int(raw_user)
    db = get_db()
    if user_id not in active_freelancers(db):
        db.rollback()
        return _fail(404, "켜진 프리랜서가 아니에요.")
    data = commission_rows(db, user_id, month, basis)
    db.rollback()
    return _ok(data)


# --------------------------------------------------------------------------
# 시공비 입력 저장
# --------------------------------------------------------------------------
class _InputError(ValueError):
    pass


def _clean_int(value: Any, *, label: str, maximum: int) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _InputError(f"{label} 칸은 숫자로 적어 주세요.")
    if value < 0 or value > maximum:
        raise _InputError(f"{label} 칸 값이 너무 크거나 0보다 작아요.")
    return value


def _clean_body(body: dict[str, Any]) -> dict[str, Any]:
    """본문에 들어온 칸만 검사해 돌려준다. 없는 칸은 저장값을 그대로 둔다."""
    cleaned: dict[str, Any] = {}
    if "install_cost" in body:
        cleaned["install_cost"] = _clean_int(body["install_cost"], label="시공비", maximum=INSTALL_COST_MAX)
    if "rate_override_bp" in body:
        cleaned["rate_override_bp"] = _clean_int(body["rate_override_bp"], label="요율", maximum=BP_MAX)
    if "note" in body:
        note = body["note"]
        if note is not None and not isinstance(note, str):
            raise _InputError("메모는 글자로 적어 주세요.")
        note = (note or "").strip()
        if len(note) > NOTE_MAX:
            raise _InputError(f"메모는 {NOTE_MAX}자까지 적을 수 있어요.")
        cleaned["note"] = note or None
    return cleaned


def _expected_version(body: dict[str, Any]) -> int:
    raw = body.get("version")
    if raw is None:
        return 0
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        raise _InputError("version 이 틀렸어요. 다시 불러와 주세요.")
    return raw


def _target_order(db, order_id: int) -> Optional[Any]:
    """수수료 입력을 받을 수 있는 주문 — 살아 있는 ERP 주문 · 협력사 주문 아님."""
    return (
        db.query(Order.id)
        .filter(Order.id == order_id, Order.active_filter(), Order.is_erp_order.is_(True),
                Order.partner_org_id.is_(None))
        .first()
    )


def _current_payload(db, order_id: int) -> dict[str, Any]:
    row = db.get(SalesCommissionInput, order_id)
    return {"current": commission_row_for_order(db, order_id), "input": input_payload(order_id, row)}


@sales_commission_api_bp.route("/inputs/<int:order_id>", methods=["PUT"], endpoint="save_input")
def api_save_input(order_id: int):
    """시공비 · 회계팀 지정 요율 · 메모 저장(낙관적 잠금 + 감사 한 줄)."""
    actor, denied = _accounting_user()
    if denied:
        return denied
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _fail(400, "보낸 값이 비었어요.")
    try:
        cleaned = _clean_body(body)
        expected = _expected_version(body)
    except _InputError as exc:
        return _fail(400, str(exc))
    actor_id = int(actor.id)
    db = get_db()
    if _target_order(db, order_id) is None:
        db.rollback()
        return _fail(404, "주문을 찾을 수 없어요.")
    try:
        row = (db.query(SalesCommissionInput).filter(SalesCommissionInput.order_id == order_id)
               .with_for_update().first())
        current = int(row.version or 1) if row is not None else 0
        if expected != current:
            db.rollback()
            return _fail(409, _STALE, _current_payload(db, order_id))
        before = input_payload(order_id, row)
        if row is None:
            row = SalesCommissionInput(order_id=order_id, version=1)
            db.add(row)
        else:
            row.version = current + 1
        for field, value in cleaned.items():
            setattr(row, field, value)
        row.updated_by_user_id = actor_id
        db.flush()
        after = input_payload(order_id, row)
        changed = {f: {"before": before[f], "after": after[f]} for f in _INPUT_FIELDS if before[f] != after[f]}
        db.add(SecurityLog(
            user_id=actor_id, action="SALES_COMMISSION_INPUT_SAVED", target_type="order", target_id=order_id,
            message=f"영업 수수료 입력 저장: 주문 {order_id}",
            detail={"order_id": order_id, "version": after["version"], "changed": changed},
        ))
        db.commit()
    except IntegrityError:  # 같은 주문 첫 저장이 동시에 두 번 — 나중 것은 낡은 화면이다
        db.rollback()
        return _fail(409, _STALE, _current_payload(db, order_id))
    except SQLAlchemyError:
        db.rollback()
        logger.exception("[SALES_COMMISSION] 입력 저장 실패 order=%s", order_id)
        return _fail(500, _SAVE_FAILED)
    data = {"row": commission_row_for_order(db, order_id), "input": after}
    db.rollback()
    return _ok(data)


# --------------------------------------------------------------------------
# 달 마감 · 지급 완료 · 마감 취소(2단계 T9 — 설계서 §8)
# --------------------------------------------------------------------------
@sales_commission_api_bp.route("/closings", methods=["GET"], endpoint="list_closings")
def api_list_closings():
    """한 프리랜서의 마감 목록(최근 달 먼저, 줄 스냅샷 포함)."""
    _actor, denied = _accounting_user()
    if denied:
        return denied
    raw_user = (request.args.get("user_id") or "").strip()
    if not raw_user.isdigit():
        return _fail(400, "프리랜서를 골라 주세요.")
    db = get_db()
    data = list_closings(db, int(raw_user))
    db.rollback()
    return _ok({"closings": data})


@sales_commission_api_bp.route("/closings/preview", methods=["GET"], endpoint="preview_closing")
def api_preview_closing():
    """마감하면 들어갈 줄 · 합계 · 세금 · 기다리는 줄 · 마감 가능 여부(쓰기 없음)."""
    _actor, denied = _accounting_user()
    if denied:
        return denied
    raw_user = (request.args.get("user_id") or "").strip()
    month = (request.args.get("month") or "").strip() or _last_month()
    if not raw_user.isdigit():
        return _fail(400, "프리랜서를 골라 주세요.")
    db = get_db()
    try:
        data = preview_closing(db, int(raw_user), month)
    except ClosingError as exc:
        db.rollback()
        return _fail(exc.status, str(exc))
    db.rollback()
    return _ok(data)


def _closing_write(action, log_label: str):
    """마감 쓰기 공통 — 한 트랜잭션으로 돌리고 커밋. 거부는 한글 문장 그대로, DB 오류는 500."""
    db = get_db()
    try:
        result = action(db)
        db.commit()
    except ClosingError as exc:
        db.rollback()
        return db, None, _fail(exc.status, str(exc))
    except SQLAlchemyError:
        db.rollback()
        logger.exception("[SALES_COMMISSION] %s 실패", log_label)
        return db, None, _fail(500, _SAVE_FAILED)
    return db, result, None


@sales_commission_api_bp.route("/closings", methods=["POST"], endpoint="close_month")
def api_close_month():
    """프리랜서 한 명의 달 마감(줄 스냅샷 + 합계 + 세금). 달은 오름차순으로만."""
    actor, denied = _accounting_user()
    if denied:
        return denied
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _fail(400, "보낸 값이 비었어요.")
    actor_id = int(actor.id)
    db, row, failed = _closing_write(
        lambda db: close_month(db, body.get("user_id"), body.get("month"), actor_user_id=actor_id), "마감")
    if failed:
        return failed
    data = closing_payload(row)
    db.rollback()
    return _ok(data, 201)


@sales_commission_api_bp.route("/closings/<int:closing_id>/paid", methods=["POST"], endpoint="mark_closing_paid")
def api_mark_closing_paid(closing_id: int):
    """지급 완료(CLOSED → PAID). 그 뒤로는 마감 취소가 막힌다."""
    actor, denied = _accounting_user()
    if denied:
        return denied
    actor_id = int(actor.id)
    db, row, failed = _closing_write(lambda db: mark_paid(db, closing_id, actor_user_id=actor_id), "지급 완료")
    if failed:
        return failed
    data = closing_payload(row, with_lines=False)
    db.rollback()
    return _ok(data)


@sales_commission_api_bp.route("/closings/<int:closing_id>", methods=["DELETE"], endpoint="cancel_closing")
def api_cancel_closing(closing_id: int):
    """지급 전 마감 취소(가장 최근 마감만) — 줄 삭제 + 감사. 본문 ``{reason}`` 필수."""
    actor, denied = _accounting_user()
    if denied:
        return denied
    body = request.get_json(silent=True)
    reason = body.get("reason") if isinstance(body, dict) else None
    actor_id = int(actor.id)
    db, snapshot, failed = _closing_write(
        lambda db: cancel_closing(db, closing_id, actor_user_id=actor_id, reason=reason), "마감 취소")
    if failed:
        return failed
    db.rollback()
    return _ok({"cancelled": snapshot})

"""정산 차감 넣기 · 취소 API(설계서 FCOMM-01 §9 · §10).

두 라우트 모두 완료 대시보드 블루프린트(``erp_orders_completion``, ``/api/orders``)에 붙는다 — 넣기의 주소 ·
endpoint 이름은 예전 그대로다. 쓰기 본체(행 잠금 · 버전 증가 · 이벤트 · 감사)는
:mod:`foms.services.settlement_deduction_service`, 프리랜서 폰 알림은
:mod:`foms.services.sales_commission.deduction_notify`.

- ``POST /api/orders/<id>/settlement/issue`` — 정책 ``FINANCE_MUTATION``. 본문 · 응답 모양은 예전과 같다
  (완료 화면 모달 · 정산 실무 탭 · 태블릿 시트가 그대로 쓴다). If-Match 는 보내면 확인, 안 보내도 된다.
- ``POST /api/orders/<id>/settlement/deductions/<ded_id>/void`` ``{reason}`` — 정책 ``SALES_COMMISSION_WRITE``
  (회계팀 · 관리자). 엔진 가드가 꺼진 환경에서도 같은 판정을 핸들러가 한 번 더 본다.
"""
from __future__ import annotations

from typing import Any, Callable

from flask import g, jsonify, request

from db import get_db
from foms.api.cs.dashboard import erp_orders_completion_bp
from foms.services.error_logging import log_handled_exception
from foms.services.orders.revision import RevisionError
from foms.services.sales_commission.deduction_notify import notify_freelancer_deduction
from foms.services.settlement_channel_access import is_accounting_or_admin
from foms.services.settlement_deduction_service import DeductionError, issue_deduction, void_deduction

_CONFLICT_MESSAGE = "그사이 다른 사람이 이 주문을 저장했어요. 화면을 새로 고친 뒤 다시 해 주세요."


def _fail(status: int, message: str, code: str | None = None):
    body: dict[str, Any] = {"success": False, "data": None, "error": message, "message": message}
    if code:
        body["code"] = code
    return jsonify(body), status


def _current_user():
    user = getattr(g, "current_user", None)
    if user is None or getattr(user, "is_active", None) is False:
        return None
    return user


def _run(order_id: int, write: Callable[[Any], dict[str, Any]], *, voided: bool, failure: str):
    """쓰기 → 커밋 → (커밋 뒤) 프리랜서 알림. 거부는 사람이 읽는 글로, 예상 못 한 예외는 500."""
    db = get_db()
    try:
        result = write(db)
        db.commit()
    except DeductionError as exc:
        db.rollback()
        return None, _fail(exc.status, exc.message)
    except RevisionError as rev:
        db.rollback()
        message = _CONFLICT_MESSAGE if rev.status_code == 409 else str(rev)
        return None, _fail(rev.status_code, message, rev.error_code)
    except Exception:  # noqa: BLE001 — 롤백 뒤 500(원문은 로그에만)
        db.rollback()
        log_handled_exception(f"settlement deduction write order={order_id}")
        return None, _fail(500, failure)
    actor = _current_user()
    notify_freelancer_deduction(db, order_id, result["deduction"], voided=voided,
                                actor_user_id=getattr(actor, "id", None))
    return result, None


@erp_orders_completion_bp.route("/<int:order_id>/settlement/issue", methods=["POST"])
def api_settlement_issue(order_id):
    """비용 청구(차감) 한 건 기록 → ``settlement.deductions[]`` 에 더하고 버전 +1(FCOMM-01 §10.3)."""
    user = _current_user()
    if user is None:
        return _fail(401, "로그인이 필요합니다.")
    payload = request.get_json(silent=True)
    data = payload if isinstance(payload, dict) else {}
    result, failed = _run(
        order_id,
        lambda db: issue_deduction(db, order_id=order_id, actor=user, data=data,
                                   if_match=request.headers.get("If-Match")),
        voided=False, failure="비용 청구를 저장하지 못했어요.",
    )
    if failed:
        return failed
    deduction_id = result["deduction"]["id"]
    response = jsonify({
        "success": True,
        "message": "비용 청구가 등록되었습니다.",
        "deduction_id": deduction_id,
        "settlement": result["settlement"],
        "data": {"deduction_id": deduction_id, "settlement": result["settlement"],
                 "mutation_version": result["mutation_version"]},
        "error": None,
    })
    response.headers["Cache-Control"] = "private, no-store"
    return response


@erp_orders_completion_bp.route("/<int:order_id>/settlement/deductions/<ded_id>/void", methods=["POST"])
def api_settlement_deduction_void(order_id, ded_id):
    """차감 한 건 취소(지우지 않고 취소 표시) — 회계팀 · 관리자만(FCOMM-01 §10.2)."""
    user = _current_user()
    if user is None:
        return _fail(401, "로그인이 필요합니다.")
    if not is_accounting_or_admin(user) or getattr(user, "partner_org_id", None) is not None:
        return _fail(403, "회계팀과 관리자만 차감을 취소할 수 있어요.")
    payload = request.get_json(silent=True)
    data = payload if isinstance(payload, dict) else {}
    result, failed = _run(
        order_id,
        lambda db: void_deduction(db, order_id=order_id, deduction_id=ded_id, actor=user,
                                  reason=data.get("reason"), if_match=request.headers.get("If-Match")),
        voided=True, failure="차감을 취소하지 못했어요.",
    )
    if failed:
        return failed
    response = jsonify({"success": True, "data": {
        "deduction": result["deduction"], "settlement": result["settlement"],
        "mutation_version": result["mutation_version"],
    }, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response


__all__ = ["api_settlement_deduction_void", "api_settlement_issue"]

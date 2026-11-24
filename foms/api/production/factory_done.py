"""공장마다 제작 완료 API(설계서 2026-11-23 §4-4 · §4-14 · §7, 3단계 ⑥).

``POST /api/orders/<id>/production/factory-done`` — 몸 ``{factory: 1|2, done: bool, idempotency_key?}``(멱등 열쇠는 머리글
``Idempotency-Key`` 도 받는다). 본문은 서비스 한 곳(:func:`foms.services.production.factory_complete.finish_factory` — 마지막
공장이면 :mod:`foms.services.production.complete_order` 의 제작 완료 길 그대로). 이 모듈은 로그인 · 쓰기 문 · 몸 읽기 · 감사 함수 ·
대시보드 캐시만 맡는다.

* 문: 앞문 = 제작 완료와 같은 정책(매니페스트 두 곳 — ``PRODUCTION_EDIT`` · CSRF), 처리기 = 생산 쓰기 사람(관리자 + 생산팀 —
  :func:`~foms.services.production.write_access.can_write_production`) + 공장 문(서비스 ``can_finish_factory``).
* 응답 ``{success, data: {factory_done, stage, final, changed}, error}`` · 거절 ``{success: false, data: {code, …}, error: 글}``.
* API 층은 웹 층을 부르지 않는다(레이어 래칫) — 로그인은 ``g.current_user``, 감사는 이 모듈의 :func:`_audit` (SecurityLog 한 줄).
"""

from __future__ import annotations

from typing import Any, Optional

from flask import Blueprint, g, jsonify, request

from db import get_db
from foms.services.audit_message_display import describe_order_action
from foms.services.common.dashboard_cache import DASHBOARD_FAMILY_PRODUCTION, invalidate_order_dashboard_families
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.production.factory_complete import finish_factory
from foms.services.production.factory_constants import normalize_factory
from foms.services.production.write_access import PRODUCTION_WRITE_DENIED_MESSAGE, can_write_production
from models import Order, SecurityLog

erp_orders_factory_done_bp = Blueprint("erp_orders_factory_done", __name__, url_prefix="/api/orders")


def _fail(status: int, code: str, message: str):
    return jsonify({"success": False, "data": {"code": code}, "error": message}), status


def _audit(db: Any):
    """감사 한 줄 함수 — ``(order, action, user_id, *, note=None, extra=None)``(제작 완료 곁일과 같은 꼴, 같은 tx)."""

    def _write(order: Order, action: str, user_id: Any, note: Optional[str] = None, extra: Optional[dict] = None) -> None:
        context = order_audit_context(order)
        db.add(SecurityLog(user_id=user_id, action=action, target_type="order", target_id=int(order.id),
                           message=describe_order_action(order_id=order.id, action=action, note=note, **context),
                           detail={**(extra or {}), **context}))

    return _write


def _parse(body: dict[str, Any]) -> tuple[int, bool]:
    """몸 → (공장, 완료 여부). 틀리면 ValueError."""
    factory = normalize_factory(body.get("factory"))
    done = body.get("done")
    if factory is None or not isinstance(done, bool):
        raise ValueError("공장 값이 올바르지 않아요.")
    return factory, done


@erp_orders_factory_done_bp.route("/<int:order_id>/production/factory-done", methods=["POST"])
def api_production_factory_done(order_id: int):
    """그 공장 제작 완료 · 완료 취소 — 두 공장이 다 완료되면 그 요청 안에서 시공 대기로 넘어간다."""
    user = getattr(g, "current_user", None)  # before_request(_set_current_user) — 비활성 · 끊긴 세션은 이미 비웠다
    if user is None:
        return _fail(401, "AUTH_REQUIRED", "다시 로그인해 주세요.")
    if not can_write_production(user):
        return _fail(403, "FORBIDDEN", PRODUCTION_WRITE_DENIED_MESSAGE)
    body = request.get_json(silent=True) or {}
    try:
        factory, done = _parse(body)
    except ValueError as exc:
        return _fail(400, "BAD_REQUEST", str(exc))
    idem = (str(body.get("idempotency_key") or "").strip() or (request.headers.get("Idempotency-Key") or "").strip())[:64]
    db = get_db()
    response = finish_factory(db, order_id, user, body, idem or None, factory=factory, done=done, audit=_audit(db))
    payload, status = (response if isinstance(response, tuple) else (response, 200))
    if status == 200:
        order = db.get(Order, order_id)
        if order is not None:
            invalidate_order_dashboard_families(order, extra=(DASHBOARD_FAMILY_PRODUCTION,))
    return payload, status

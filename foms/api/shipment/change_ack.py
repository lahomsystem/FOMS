"""출고 시공일 변경 확인(ack) API (T3).

``POST /api/orders/<int:order_id>/shipment/change-ack`` — 출고 대시보드 행 배지·배너의
``확인`` 버튼이 호출한다. 생산 선례(``foms/api/production/orders.py`` ``change-ack``)의
의미를 그대로 복제한다:

* **Order 불변** — structured_data·상태·mutation_version 을 건드리지 않고
  ``OrderEvent(SHIPMENT_CHANGE_ACK)`` 1건(+ idempotency key 가 있으면 REV-00 receipt 1건)만
  남긴다. 이 ack 시각이 **본인** 미확인 윈도를 리셋하므로 동료 화면은 그대로다.
* **idempotent** — ``Idempotency-Key`` 헤더(또는 body ``idempotency_key``)를 주면 same-token
  재요청은 event/receipt 를 재기록하지 않고 저장된 응답을 replay 한다(event 0). key 가 없으면
  dedupe 하지 않는다(생산 선례와 동일 — 매 요청 기록).

권한은 출고 도메인의 기존 게이트를 재사용한다(신규 게이트 없음):
``_construction_team_forbidden``(시공팀은 출고 데이터 수정 불가) → ``_shipment_edit_decision``
(§2.1 ``SHIPMENT_EDIT``: CS/SALES/SHIPMENT 팀 또는 ADMIN/MANAGER, 미인증 401·VIEWER 403).
AUTH-01 before_request 가드가 꺼진 컨텍스트(TESTING 등)에서도 우회되지 않도록 payload 파싱
전에 in-handler 로 강제한다.

응답은 **새로고침 없이** 화면을 고칠 수 있을 만큼 담는다(T4 가 DOM 을 갱신한다):
``{success, remaining, banner_count_hint, data:{order_id, cleared, remaining,
banner_count_hint}}`` — ``remaining`` 은 ack 직후 이 주문의 미확인 건수(항상 0),
``banner_count_hint`` 는 상단 배너 카운트에 더할 **부호 있는 증감**(이 주문에 미확인이
있었으면 ``-1``, 없었으면 ``0``). 배너 count 는 "주문 수"라 한 주문을 확인하면 1 줄어든다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any

from flask import jsonify, request
from sqlalchemy.exc import IntegrityError

from db import get_db
from foms.api.shipment.recommendations import _construction_team_forbidden
from foms.api.shipment.settings import _shipment_edit_decision, erp_shipment_bp
from foms.services.common.dashboard_cache import (
    DASHBOARD_FAMILY_SHIPMENT,
    invalidate_dashboard_families,
)
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.revision import IDEMPOTENCY_REPLAY_WINDOW, READ_RECEIPT_TTL
from foms.services.shipment_change_alerts import (
    SHIPMENT_ACK_EVENT,
    collect_shipment_change_alerts,
)
from models import Order, OrderEvent, OrderMutationReceipt

logger = logging.getLogger(__name__)

#: REV-00 receipt 의 idempotency scope 식별자(free-form). AUTH 게이트는 §2.1 ``SHIPMENT_EDIT``
#: 를 그대로 쓰며 이 문자열은 POLICY_REGISTRY 와 무관하다(생산 ack 와 동일 관례).
_RECEIPT_POLICY_ID = "SHIPMENT_CHANGE_ACK"
_ACK_SOURCE = "shipment_dashboard"


def _idempotency_key(body: dict[str, Any]) -> str | None:
    """요청 idempotency key(헤더 우선, body fallback, ≤64자). 없으면 ``None``(중복제거 안 함)."""
    key = request.headers.get("Idempotency-Key") or body.get("idempotency_key")
    key = str(key).strip() if key is not None else ""
    return key[:64] if key else None


def _ack_response(order_id: int, cleared: int) -> dict[str, Any]:
    """ack 성공 응답 body 를 만든다(in-place DOM 갱신에 필요한 값 포함).

    Args:
        order_id: 대상 주문 id.
        cleared: 이번 ack 로 사라진 미확인 변경 건수(replay 는 0).

    Returns:
        ``{success, remaining, banner_count_hint, data:{...}}``.
    """
    banner_delta = -1 if cleared > 0 else 0
    return {
        "success": True,
        "remaining": 0,  # Order 불변 ack — 직후 이 주문의 미확인 건수는 언제나 0.
        "banner_count_hint": banner_delta,
        "data": {
            "order_id": order_id,
            "cleared": cleared,
            "remaining": 0,
            "banner_count_hint": banner_delta,
        },
    }


def _stored_ack_response(db: Any, actor_user_id: Any, idem_key: str | None) -> dict[str, Any] | None:
    """(actor, SHIPMENT_CHANGE_ACK, key) receipt 에 저장된 응답. 없으면 ``None``.

    존재하면 이 요청은 replay 다 — event/receipt 를 재기록하지 않고 저장 응답을 돌려준다.

    Args:
        db: 활성 DB 세션.
        actor_user_id: 요청 actor(receipt 소유자).
        idem_key: idempotency key(``None`` 이면 dedupe 하지 않는다).

    Returns:
        저장된 response_body dict 또는 ``None``.
    """
    if not idem_key or actor_user_id is None:
        return None
    row = (
        db.query(OrderMutationReceipt.response_body)
        .filter(
            OrderMutationReceipt.actor_user_id == actor_user_id,
            OrderMutationReceipt.policy_id == _RECEIPT_POLICY_ID,
            OrderMutationReceipt.idempotency_key == idem_key,
        )
        .first()
    )
    if row is None:
        return None
    return row[0] if isinstance(row[0], dict) else None


def _record_ack_receipt(
    db: Any, actor_user_id: Any, order_id: int, idem_key: str,
    body: dict[str, Any], response_body: dict[str, Any],
) -> None:
    """Order 불변 ack 의 REV-00 receipt 1건을 기록한다(mutation_version bump 없음).

    ``execute_order_mutation`` 은 version 을 무조건 bump 하므로 Order 를 바꾸지 않는 ack 에는
    쓸 수 없다. 대신 receipt-only 경로로 남겨 same-token 재요청을 replay(event 0)로 수렴시킨다.
    ``(actor, policy, key)`` unique 제약이 same-token 동시 요청을 막는다(두 번째 insert 는
    flush 에서 ``IntegrityError`` → 호출부가 rollback 후 replay).

    Args:
        db: business 트랜잭션 세션(호출부가 commit 소유).
        actor_user_id: 요청 actor.
        order_id: 대상 주문 id(scope_hash 구성).
        idem_key: idempotency key(≤64자, ``None`` 아님).
        body: 요청 payload(request_hash 계산).
        response_body: replay 시 돌려줄 저장 응답.

    Returns:
        None.
    """
    now = now_utc_naive()
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    db.add(
        OrderMutationReceipt(
            read_receipt_id=str(uuid.uuid4()),
            actor_user_id=actor_user_id,
            policy_id=_RECEIPT_POLICY_ID,
            idempotency_key=idem_key,
            scope_hash=hashlib.sha256(
                f"{_RECEIPT_POLICY_ID}:{order_id}".encode("utf-8")
            ).hexdigest(),
            request_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            response_status=200,
            response_body=response_body,
            resulting_versions={},  # Order 불변 — bump 없음.
            read_expires_at=now + READ_RECEIPT_TTL,
            expires_at=now + IDEMPOTENCY_REPLAY_WINDOW,
        )
    )
    db.flush()


def _json_error(message: str, status: int):
    """실패 응답(프로젝트 표준 ``{success, data, error, message}``) + status."""
    return jsonify({
        "success": False, "data": None, "error": message, "message": message,
    }), status


def _ack_permission_gate() -> tuple[Any, Any]:
    """시공팀 차단 → ``SHIPMENT_EDIT`` 판정 순으로 in-handler 권한을 강제한다.

    AUTH-01 before_request 가드가 꺼진 컨텍스트(TESTING 등)에서도 우회되지 않도록 payload
    파싱 전에 호출한다. 신규 게이트를 만들지 않고 출고 도메인의 기존 헬퍼만 조합한다.

    Returns:
        ``(user, None)`` 통과, 또는 ``(None, 거부 응답)``(미인증 401·시공팀/무권한 403).
    """
    blocked = _construction_team_forbidden()
    if blocked:
        return None, blocked
    user, decision = _shipment_edit_decision()
    if not decision.allowed:
        return None, (jsonify({
            "success": False, "data": None,
            "error": decision.reason, "message": decision.reason, "code": decision.code,
        }), decision.status)
    return user, None


def _unacked_count(db: Any, order: Order, user_id: Any) -> int:
    """ack 직전 이 주문의 미확인 변경 건수(배너 증감 계산용, 배치 쿼리 1회)."""
    collected = collect_shipment_change_alerts(db, [order], user_id)
    return len((collected.get(order.id) or {}).get("alerts") or [])


def _invalidate_shipment_dashboard_cache() -> None:
    """ack 커밋 후 출고 대시보드 family 캐시를 무효화한다(실패는 로그만)."""
    try:
        invalidate_dashboard_families(DASHBOARD_FAMILY_SHIPMENT)
    except Exception:
        logger.warning("[SHIPMENT_ACK] dashboard slice cache invalidate failed", exc_info=True)


@erp_shipment_bp.route("/api/orders/<int:order_id>/shipment/change-ack", methods=["POST"])
def api_shipment_change_ack(order_id: int):
    """출고 시공일 변경 확인(ack) — 개인별, Order 불변.

    시공팀 차단 → ``SHIPMENT_EDIT`` 판정 → ``OrderEvent(SHIPMENT_CHANGE_ACK)`` 1건 기록 →
    출고 대시보드 캐시 무효화 순으로 처리한다. 삭제(취소)된 주문에도 허용한다(행이 남아 있는
    동안 확인 가능해야 한다 — 존재 여부만 본다).

    Args:
        order_id: 대상 주문 id.

    Returns:
        성공 ``{success, remaining, banner_count_hint, data}``; 미인증 401 / 권한 없음 403 /
        주문 부재 404 / 예외 500 JSON.
    """
    user, denied = _ack_permission_gate()
    if denied is not None:
        return denied

    db = get_db()
    user_id = getattr(user, "id", None)
    body = request.get_json(silent=True) or {}
    idem_key = _idempotency_key(body)
    try:
        order = db.get(Order, order_id)
        if order is None:
            return _json_error("주문을 찾을 수 없습니다.", 404)

        replayed = _stored_ack_response(db, user_id, idem_key)
        if replayed is not None:
            return jsonify(replayed)

        response_body = _ack_response(order_id, _unacked_count(db, order, user_id))
        db.add(OrderEvent(
            order_id=order_id, event_type=SHIPMENT_ACK_EVENT,
            payload={"source": _ACK_SOURCE}, created_by_user_id=user_id,
        ))
        if idem_key is not None:
            try:
                _record_ack_receipt(db, user_id, order_id, idem_key, body, response_body)
            except IntegrityError:
                db.rollback()  # 동시 same-token → event/receipt 0, replay 로 수렴.
                return jsonify(_ack_response(order_id, 0))
        db.commit()
    except Exception as exc:  # noqa: BLE001 - 롤백 후 500(경계에서 본문은 컨테이너가 정리)
        db.rollback()
        logger.exception("[SHIPMENT_ACK] change-ack 실패: %s", exc)
        return _json_error(str(exc), 500)

    _invalidate_shipment_dashboard_cache()
    return jsonify(response_body)

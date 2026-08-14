"""의도적 워크플로 단계 강제 변경 API (역행·건너뛰기).

STATE-FORM-01: 명시적 단계 override 는 REV-00 :func:`execute_order_mutation` 을 경유해
If-Match(mutation_version) 낙관 잠금 · ``FOR UPDATE`` 직렬화 · version bump · idempotency
receipt 를 한 transaction 에 원자화한다(stale tab 방어). 실제 단계 write·``STAGE_OVERRIDE``
audit 이벤트는 :func:`apply_stage_override` 가 lock 아래에서 수행한다(폼 저장과 분리).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, List, Mapping, Optional

from flask import current_app, jsonify, request, session
from sqlalchemy.orm import Session

from db import get_db
from foms.services.orders.revision import RevisionError, execute_order_mutation
from foms.services.orders.stage_override import (
    OVERRIDE_ALLOWED_ROLES,
    apply_stage_override,
)
from foms.web.auth import log_access
from models import Order, User

#: override mutation 의 receipt idempotency scope 문자열(POLICY_REGISTRY 무관 — REV-00 receipt
#: scope 구성요소일 뿐; auth 게이트는 아래 role 검사가 담당).
STAGE_OVERRIDE_POLICY_ID = "STAGE_OVERRIDE"


def _parse_if_match(raw: Optional[str]) -> tuple[Optional[int], bool]:
    """If-Match 헤더를 mutation_version(int) 로 파싱한다.

    Args:
        raw: ``If-Match`` 헤더 원문(따옴표 포함 가능) 또는 None.

    Returns:
        (version, ok) — 헤더가 없으면 (None, True), 형식 오류면 (None, False).
    """
    cleaned = (raw or "").strip().strip('"')
    if not cleaned:
        return None, True
    try:
        return int(cleaned), True
    except ValueError:
        return None, False


def stage_override_response(order_id: int):
    """POST /api/orders/<id>/workflow/stage-override 핸들러."""
    db = get_db()
    try:
        user_id = session.get("user_id")
        user = db.query(User).filter(User.id == user_id).first() if user_id else None
        if not user:
            return jsonify({"success": False, "error": "로그인이 필요합니다."}), 401
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role not in OVERRIDE_ALLOWED_ROLES:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "단계 강제 변경은 ADMIN/MANAGER만 가능합니다.",
                    }
                ),
                403,
            )

        data = request.get_json(silent=True) or {}
        if data.get("confirm") is not True:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "confirm: true 가 필요합니다.",
                    }
                ),
                400,
            )

        to_stage = str(data.get("to_stage") or "")
        reason = str(data.get("reason") or "")

        # optional If-Match(mutation_version) 낙관 잠금 — 형식 오류는 삼키지 않고 400.
        expected_version, if_match_ok = _parse_if_match(request.headers.get("If-Match"))
        if not if_match_ok:
            return jsonify({"success": False, "error": "If-Match 형식이 올바르지 않습니다."}), 400
        expected_versions: Optional[Mapping[int, int]] = (
            {order_id: expected_version} if expected_version is not None else None
        )

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

        scope_hash = hashlib.sha256(
            f"{STAGE_OVERRIDE_POLICY_ID}:{order_id}".encode("utf-8")
        ).hexdigest()
        request_hash = hashlib.sha256(
            json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        ).hexdigest()
        captured: dict[str, Any] = {}

        def _mutate(sess: Session, orders: List[Order]) -> Mapping[int, List[str]]:
            """FOR UPDATE 락 아래에서 단계 override 를 적용한다(from 은 lock 아래 재확인).

            Args:
                sess: REV-00 이 lock 을 잡은 세션.
                orders: 잠긴 Order 목록(단건).

            Returns:
                order_id → 무효화할 cache family 목록(main stage 전이).
            """
            o = orders[0]
            payload = apply_stage_override(
                order=o,
                to_stage=to_stage,
                reason=reason,
                user_id=user_id,
                db=sess,
            )
            captured["payload"] = payload
            captured["status"] = o.status
            return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

        try:
            outcome = execute_order_mutation(
                db,
                actor_user_id=user_id,
                policy_id=STAGE_OVERRIDE_POLICY_ID,
                order_ids=[order_id],
                expected_versions=expected_versions,
                scope_hash=scope_hash,
                request_hash=request_hash,
                mutation=_mutate,
            )
            db.commit()
        except ValueError as exc:
            # apply_stage_override 검증 실패(무효 전이/빈 사유/동일 단계)는 400.
            db.rollback()
            return jsonify({"success": False, "error": str(exc)}), 400
        except RevisionError as rev:
            # stale tab(If-Match 불일치) → 409, 미존재 → 404 등.
            db.rollback()
            return (
                jsonify({"success": False, "error": str(rev), "code": rev.error_code}),
                rev.status_code,
            )

        payload = captured["payload"]
        resources = outcome.body.get("resources") or [{}]
        log_access(
            f"주문 #{order_id} 단계 강제 변경({payload['mode']}): "
            f"{payload['from']} → {payload['to']} ({payload['reason']})",
            user_id,
        )
        resp = jsonify(
            {
                "success": True,
                "data": {
                    "order_id": order_id,
                    "from": payload["from"],
                    "to": payload["to"],
                    "mode": payload["mode"],
                    "reason": payload["reason"],
                    "status": captured["status"],
                    "mutation_version": resources[0].get("resulting_version"),
                    "mutation_receipt": outcome.read_receipt_id,
                },
            }
        )
        for header, value in outcome.headers.items():
            resp.headers[header] = value
        return resp
    except Exception as exc:
        db.rollback()
        current_app.logger.error("stage_override 실패: %s", exc, exc_info=True)
        return (
            jsonify({"success": False, "error": f"오류 발생: {exc}"}),
            500,
        )


__all__ = ["stage_override_response", "STAGE_OVERRIDE_POLICY_ID"]

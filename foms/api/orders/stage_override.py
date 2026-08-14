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
from foms.services.orders.revision import (
    MAX_RESOURCES,
    RevisionError,
    execute_order_mutation,
)
from foms.services.orders.stage_override import (
    OVERRIDE_ALLOWED_ROLES,
    apply_stage_override,
    classify_stage_move,
    current_stage_for_order,
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


def _json_error(message: str, status: int):
    """표준 실패 JSON을 반환한다."""
    return jsonify({"success": False, "error": message}), status


def _override_user(db) -> tuple[Optional[User], Optional[tuple]]:
    """ADMIN/MANAGER 액터를 확인한다. 실패 시 (None, response)."""
    user_id = session.get("user_id")
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if not user:
        return None, _json_error("로그인이 필요합니다.", 401)
    role = str(getattr(user, "role", "") or "").strip().upper()
    if role not in OVERRIDE_ALLOWED_ROLES:
        return None, _json_error("단계 강제 변경은 ADMIN/MANAGER만 가능합니다.", 403)
    return user, None


def _parse_override_payload(data: Mapping[str, Any]) -> tuple[str, str, Optional[tuple]]:
    """confirm/to_stage/reason 을 파싱한다. 실패 시 세 번째가 response."""
    if data.get("confirm") is not True:
        return "", "", _json_error("confirm: true 가 필요합니다.", 400)
    return str(data.get("to_stage") or ""), str(data.get("reason") or ""), None


def _parse_bulk_ids(raw: Any) -> list[int]:
    """order_ids 배열을 양수 unique int 목록으로 정규화한다."""
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    seen: set[int] = set()
    for item in raw:
        try:
            oid = int(item)
        except (TypeError, ValueError):
            continue
        if oid <= 0 or oid in seen:
            continue
        seen.add(oid)
        out.append(oid)
    return out


def _split_override_targets(
    orders: List[Order], to_stage: str
) -> tuple[list[Order], list[int]]:
    """동일 단계는 건너뛰고 실제 변경 대상만 남긴다."""
    change: list[Order] = []
    skipped: list[int] = []
    for order in orders:
        if classify_stage_move(current_stage_for_order(order), to_stage) == "same":
            skipped.append(int(order.id))
        else:
            change.append(order)
    return change, skipped


def _apply_locked_overrides(
    sess: Session,
    orders: List[Order],
    *,
    to_stage: str,
    reason: str,
    user_id: int,
    captured: dict[str, Any],
) -> Mapping[int, List[str]]:
    """FOR UPDATE 락 아래 주문마다 apply_stage_override 를 적용한다."""
    families: dict[int, list[str]] = {}
    results: list[dict[str, Any]] = []
    for order in orders:
        payload = apply_stage_override(
            order=order, to_stage=to_stage, reason=reason, user_id=user_id, db=sess,
        )
        results.append({"order_id": int(order.id), **payload})
        families[int(order.id)] = [f"ORDER_DETAIL:{order.id}", "ORDERS_INDEX"]
    captured["results"] = results
    return families


def _execute_bulk_override(
    db,
    *,
    user_id: int,
    change_ids: list[int],
    to_stage: str,
    reason: str,
    data: Mapping[str, Any],
    captured: dict[str, Any],
):
    """잠금 아래 일괄 apply_stage_override. 성공 시 outcome, 실패 시 (None, response)."""
    scope_key = f"{STAGE_OVERRIDE_POLICY_ID}:bulk:{','.join(str(i) for i in sorted(change_ids))}"
    scope_hash = hashlib.sha256(scope_key.encode("utf-8")).hexdigest()
    request_hash = hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
    try:
        outcome = execute_order_mutation(
            db,
            actor_user_id=user_id,
            policy_id=STAGE_OVERRIDE_POLICY_ID,
            order_ids=change_ids,
            scope_hash=scope_hash,
            request_hash=request_hash,
            mutation=lambda sess, orders: _apply_locked_overrides(
                sess, orders, to_stage=to_stage, reason=reason,
                user_id=user_id, captured=captured,
            ),
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        return None, _json_error(str(exc), 400)
    except RevisionError as rev:
        db.rollback()
        return None, (
            jsonify({"success": False, "error": str(rev), "code": rev.error_code}),
            rev.status_code,
        )
    return outcome, None


def _bulk_override_success(
    outcome, results: list[dict[str, Any]], skipped_same: list[int], not_found: list[int],
    reason: str, user_id: int,
):
    """일괄 강제 변경 성공 JSON + no-store 헤더."""
    to_code = results[0]["to"] if results else ""
    log_access(
        f"주문 {len(results)}건 단계 강제 변경: → {to_code} ({str(reason or '').strip()})",
        user_id,
    )
    resp = jsonify(
        {
            "success": True,
            "data": {
                "updated": len(results),
                "to": to_code,
                "reason": str(reason or "").strip(),
                "results": results,
                "skipped_same": skipped_same,
                "not_found": not_found,
                "mutation_receipt": outcome.read_receipt_id,
            },
        }
    )
    for header, value in outcome.headers.items():
        resp.headers[header] = value
    return resp


def bulk_stage_override_response():
    """POST /api/orders/workflow/stage-override/bulk 핸들러."""
    db = get_db()
    user, auth_err = _override_user(db)
    if auth_err is not None:
        return auth_err
    data = request.get_json(silent=True) or {}
    to_stage, reason, payload_err = _parse_override_payload(data)
    if payload_err is not None:
        return payload_err
    order_ids = _parse_bulk_ids(data.get("order_ids"))
    if not order_ids:
        return _json_error("order_ids(배열)가 필요합니다.", 400)
    if len(order_ids) > MAX_RESOURCES:
        return _json_error(f"한 번에 {MAX_RESOURCES}건까지 변경할 수 있습니다.", 400)
    found = db.query(Order).filter(Order.id.in_(order_ids)).all()  # perf-ok: request bulk id batch
    found_map = {int(order.id): order for order in found}
    not_found = [oid for oid in order_ids if oid not in found_map]
    change, skipped_same = _split_override_targets(
        [found_map[oid] for oid in order_ids if oid in found_map],
        to_stage,
    )
    if not change:
        if skipped_same and not not_found:
            return _json_error("현재와 동일한 단계로는 변경할 수 없습니다.", 400)
        return _json_error("주문을 찾을 수 없습니다.", 404)
    captured: dict[str, Any] = {"results": []}
    user_id = int(user.id)
    outcome, mut_err = _execute_bulk_override(
        db,
        user_id=user_id,
        change_ids=[int(order.id) for order in change],
        to_stage=to_stage,
        reason=reason,
        data=data,
        captured=captured,
    )
    if mut_err is not None:
        return mut_err
    return _bulk_override_success(
        outcome, captured["results"], skipped_same, not_found, reason, user_id,
    )


__all__ = [
    "STAGE_OVERRIDE_POLICY_ID",
    "bulk_stage_override_response",
    "stage_override_response",
]

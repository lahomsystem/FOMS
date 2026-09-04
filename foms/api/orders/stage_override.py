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
from foms.services.audit_message_display import describe_field_change
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.stage_override import (
    AS_OVERLAY_BLOCK_MESSAGE,
    OVERRIDE_ALLOWED_ROLES,
    apply_stage_override,
    as_overlay_status,
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
            captured["order"] = o
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
            _audit_stage_override_status(
                [{"order_id": order_id, "order": captured.get("order"), **captured["payload"]}],
                user_id,
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
        # AS overlay 를 덮었으면 그 사실을 문장으로 남긴다. 감리#3 에 따라 AS→메인 복귀는
        # 허용이지만(오접수 정정 경로), order.status 의 AS 표시가 사라지면 출고 보드 AS
        # 필터·관제탑·정산 알림에서 그 건이 빠진다 — 조용하면 안 된다.
        overlay_cleared = str(payload.get("as_overlay_cleared") or "").strip()
        log_access(
            f"주문 #{order_id} 단계 강제 변경({payload['mode']}): "
            f"{payload['from']} → {payload['to']} ({payload['reason']})"
            + (f" · AS 표시 해제({overlay_cleared})" if overlay_cleared else ""),
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
                    "as_overlay_cleared": overlay_cleared or None,
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
    orders: List[Order], to_stage: str, *, include_as: bool = False
) -> tuple[list[Order], list[int], list[dict[str, Any]]]:
    """동일 단계·AS overlay 를 걸러 실제 변경 대상만 남긴다.

    AS 접수/완료 상태 주문을 메인 단계로 덮으면 AS 대시보드에서 통째로 사라진다
    (기록은 남지만 목록 술어가 status 기반). 일괄 경로는 사람이 건건이 확인하지 않으므로
    기본 제외하고 호출부가 ``include_as=True`` 로만 명시 포함할 수 있다.

    Args:
        orders: 요청 순서대로 정렬된 대상 주문 목록.
        to_stage: 목표 단계.
        include_as: True 면 AS overlay 주문도 변경 대상에 넣는다(명시 opt-in).

    Returns:
        (변경 대상, 동일 단계로 건너뛴 id, AS 로 제외한 ``{order_id, status}`` 목록).
    """
    change: list[Order] = []
    skipped: list[int] = []
    skipped_as: list[dict[str, Any]] = []
    for order in orders:
        if classify_stage_move(current_stage_for_order(order), to_stage) == "same":
            skipped.append(int(order.id))
            continue
        overlay = as_overlay_status(order)
        if overlay and not include_as:
            skipped_as.append({"order_id": int(order.id), "status": overlay})
            continue
        change.append(order)
    return change, skipped, skipped_as


def _audit_stage_override_status(results: list[dict[str, Any]], user_id: Any) -> None:
    """단계 강제 변경으로 바뀐 status 를 SQL 조회 가능한 감사행으로 남긴다.

    ``STAGE_OVERRIDE`` 이벤트만으로는 ``payload.from`` 이 workflow.stage 라 실제 status
    이전값이 남지 않았다(2026-08-14 사고에서 복구 근거가 부족했던 지점). 호출부의
    ``db.commit()`` 에 함께 실린다(``auto_commit=False``).

    Args:
        results: :func:`apply_stage_override` payload + ``order_id``/``order`` 목록.
        user_id: 행위자 user id.
    """
    for item in results:
        order = item.get("order")
        before = str(item.get("from_status") or "")
        after = str(getattr(order, "status", "") or item.get("to") or "")
        context = order_audit_context(order) if order is not None else {}
        detail = {
            "field": "status", "before": before, "after": after,
            "stage_override": True, "mode": item.get("mode"),
            "reason": item.get("reason"), **context,
        }
        if item.get("as_overlay_cleared"):
            detail["as_overlay_cleared"] = item["as_overlay_cleared"]
        log_access(
            describe_field_change(
                order_id=item["order_id"], field="status", before=before, after=after,
                has_before=True, **context,
            ) + " (단계 강제 변경)",
            user_id,
            auto_commit=False,
            action="ORDER_STATUS_CHANGED", target_type="order",
            target_id=int(item["order_id"]), detail=detail,
        )


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
        results.append({"order_id": int(order.id), "order": order, **payload})
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
        _audit_stage_override_status(captured.get("results") or [], user_id)
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
    reason: str, user_id: int, skipped_as: list[dict[str, Any]] | None = None,
):
    """일괄 강제 변경 성공 JSON + no-store 헤더."""
    to_code = results[0]["to"] if results else ""
    skipped_as = skipped_as or []
    log_access(
        f"주문 {len(results)}건 단계 강제 변경: → {to_code} ({str(reason or '').strip()})"
        + (f" · AS 상태 {len(skipped_as)}건 제외" if skipped_as else ""),
        user_id,
    )
    body: dict[str, Any] = {
        "updated": len(results),
        "to": to_code,
        "reason": str(reason or "").strip(),
        # order ORM 은 응답에 싣지 않는다(감사용 내부 참조).
        "results": [{k: v for k, v in item.items() if k != "order"} for item in results],
        "skipped_same": skipped_same,
        "skipped_as": skipped_as,
        "not_found": not_found,
        "mutation_receipt": outcome.read_receipt_id,
    }
    if skipped_as:
        body["warning"] = AS_OVERLAY_BLOCK_MESSAGE
    resp = jsonify({"success": True, "data": body})
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
    change, skipped_same, skipped_as = _split_override_targets(
        [found_map[oid] for oid in order_ids if oid in found_map],
        to_stage,
        include_as=data.get("include_as") is True,
    )
    if not change:
        if skipped_as:
            return _json_error(AS_OVERLAY_BLOCK_MESSAGE, 400)
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
        skipped_as=skipped_as,
    )


__all__ = [
    "STAGE_OVERRIDE_POLICY_ID",
    "bulk_stage_override_response",
    "stage_override_response",
]

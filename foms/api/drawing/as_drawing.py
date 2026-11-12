"""완료 주문 AS 도면 API (설계서 ``docs/specs/2026-11-11-as-drawing-after-completion_SPEC.md`` §6.3).

- ``GET  /api/orders/<id>/drawing/as``                   지금 차수·지난 차수·시작할 수 있는지
- ``POST /api/orders/<id>/drawing/as/start``             도면팀이 시작(AS 접수가 없으면 접수까지)
- ``POST /api/orders/<id>/drawing/as/transfer``          이번 차수 AS 시트 그림을 보냄
- ``POST /api/orders/<id>/drawing/as/confirm``           영업·AS 담당이 확인(한 명이면 끝)
- ``POST /api/orders/<id>/drawing/as/request-revision``  영업·AS 담당이 고쳐 달라고 함
- ``POST /api/orders/<id>/drawing/as/cancel``            한 번도 안 보낸 차수를 그만둠

원래 최종 도면(``drawing_current_files`` 등)은 어느 경로도 쓰지 않는다. 쓰기는 모두 REV-00
:func:`execute_order_mutation`(If-Match · 멱등 키 · 행 잠금) 위에서 한다. 채널톡 접수(AS PUSH)는
화면이 지금 ``/api/channel/push-manual`` ``push_kind='as'`` 를 그대로 부른다(새 경로 없음).
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
from typing import Any, Callable

from flask import Blueprint, g, jsonify, make_response, request
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from foms.api.cs.as_orders import register_as_from_payload
from foms.api.drawing.erp_orders_drawing import _drawing_notice_target
from foms.services.as_content_safety import as_content_html_to_text
from foms.services.audit_message_display import describe_order_action
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.auth.partner_scope import is_partner_sd, is_partner_user
from foms.services.orders.manager_names import order_manager_label
from foms.services.common.dashboard_cache import (
    DASHBOARD_FAMILY_DRAWING,
    DASHBOARD_FAMILY_ORDERS,
    invalidate_dashboard_families,
)
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.as_cycle_service import current_cycle
from foms.services.orders.as_drawing import (
    SOURCE_DRAWING_FIRST,
    STATUS_IN_PROGRESS,
    ASDrawingError,
    cancel_round,
    confirm_round,
    current_round,
    is_as_drawing_stage,
    open_as_cycle_id,
    open_round,
    request_revision,
    round_no,
    round_view,
    rounds,
    transfer_round,
)
from foms.services.orders.as_drawing_notify import enqueue_as_drawing_push, notify_as_drawing
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.orders.revision import RevisionError, execute_order_mutation
from models import Order, SecurityLog

logger = logging.getLogger(__name__)

#: 도면팀(시작 · 보내기 · 그만두기) — 매니페스트 가드와 같은 정책.
DRAWING_POLICY_ID = "DRAWING_TEAM"
#: 영업 · CS(확인 · 고쳐 달라기) — AS 담당과 영업 담당 중 한 명이면 끝(사용자 11-11).
CONFIRM_POLICY_ID = "ERP_EDIT"
#: REV-00 receipt 정책 식별자(권한 판정에는 쓰지 않는다).
RECEIPT_POLICY_ID = "AS_DRAWING"

erp_orders_as_drawing_bp = Blueprint("erp_orders_as_drawing", __name__, url_prefix="/api/orders")


def _fail(message: str, status: int, code: str | None = None):
    body: dict = {"success": False, "data": None, "error": message}
    if code:
        body["code"] = code
    return jsonify(body), status


def _guard(policy_id: str):
    """로그인 · 정책 판정. 통과면 ``(user, None)``, 아니면 ``(None, 응답)``."""
    user = getattr(g, "current_user", None)
    if user is None:
        return None, _fail("로그인이 필요해요.", 401, "AUTH_REQUIRED")
    decision = evaluate_policy(POLICY_REGISTRY[policy_id], user)
    if not decision.allowed:
        return None, _fail(decision.reason, decision.status, decision.code)
    return user, None


def _load_order(db, order_id: int):
    """AS 도면을 다룰 수 있는 주문을 읽는다. 아니면 ``(None, 응답)``."""
    order = db.get(Order, order_id)
    if (order is None or order.status == "DELETED" or order.deleted_at is not None
            or not getattr(order, "is_erp_order", False)):
        return None, _fail("주문을 찾을 수 없어요.", 404, "NOT_FOUND")
    if getattr(order, "partner_org_id", None):
        # 협력사 주문은 담당 · 명세서 흐름이 따로 있어 1차 범위 밖이다(설계서 §7).
        return None, _fail("협력사 주문은 아직 AS 도면을 쓸 수 없어요.", 409, "PARTNER_ORDER")
    return order, None


def _hashes(command: str, order_id: int, body: dict) -> tuple[str, str]:
    scope = hashlib.sha256(f"AS_DRAWING:{command}:{order_id}".encode()).hexdigest()
    req = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    return scope, req


#: 명령 → 감사 행위 이름(표시 문장은 audit_message_display 가 만든다).
_AUDIT_ACTIONS = {
    "start": "AS_DRAWING_STARTED",
    "transfer": "AS_DRAWING_TRANSFERRED",
    "confirm": "AS_DRAWING_CONFIRMED",
    "request-revision": "AS_DRAWING_REVISION_REQUESTED",
    "cancel": "AS_DRAWING_CANCELLED",
}


def _audit(db, order_id: int, user: Any, command: str, body: dict, result: dict) -> None:
    """행위 1건 = 감사 1행(같은 트랜잭션 — 호출자가 commit). 연락처·주소는 싣지 않는다."""
    order = db.get(Order, order_id)
    context = order_audit_context(order) if order is not None else {}
    action = _AUDIT_ACTIONS[command]
    rnd = (result or {}).get("round") or {}
    note = str(body.get("note") or body.get("reason") or body.get("memo") or "")[:200] or None
    # SecurityLog 를 같은 세션에 바로 싣는다 — API 층은 웹 층(log_access)을 부르지 않는다(레이어 래칫).
    db.add(SecurityLog(
        user_id=user.id,
        message=describe_order_action(order_id=order_id, action=action, note=note, **context),
        action=action, target_type="order", target_id=int(order_id),
        detail={"round_id": rnd.get("round_id"), "round_no": rnd.get("no"), "status": rnd.get("status"),
                "note": note, **context},
    ))


def _run(order_id: int, user: Any, command: str, body: dict,
         apply: Callable[[Any, Order, dict], dict]):
    """잠근 행 위에서 ``apply(sess, order, sd)`` 를 돌리고 감사 1행과 함께 commit 한다. 결과 dict 또는 오류 응답."""
    if_match = (request.headers.get("If-Match") or "").strip().strip('"')
    expected = {order_id: int(if_match)} if if_match.isdigit() else None
    idem = (request.headers.get("Idempotency-Key") or "").strip() or None
    scope_hash, request_hash = _hashes(command, order_id, body)
    captured: dict = {}

    def _mutate(sess, locked):
        order = locked[0]
        sd = copy.deepcopy(order.structured_data if isinstance(order.structured_data, dict) else {})
        result = apply(sess, order, sd)
        captured["notices"] = result.pop("_notices", None) or []   # 감사 기록에 싣지 않는다
        captured["result"] = result
        order.structured_data = sd
        flag_modified(order, "structured_data")
        return {order.id: [f"ORDER_DETAIL:{order.id}", "ORDERS_INDEX"]}

    db = get_db()
    try:
        execute_order_mutation(
            db, actor_user_id=user.id, policy_id=RECEIPT_POLICY_ID, order_ids=[order_id],
            expected_versions=expected, idempotency_key=idem,
            scope_hash=scope_hash, request_hash=request_hash, mutation=_mutate,
        )
        _audit(db, order_id, user, command, body, captured.get("result") or {})
        db.commit()
    except ASDrawingError as exc:
        db.rollback()
        return None, _fail(str(exc), exc.status, exc.code)
    except RevisionError as rev:
        db.rollback()
        return None, _fail(str(rev), rev.status_code, rev.error_code)
    except Exception as exc:  # noqa: BLE001 - 롤백 후 500
        db.rollback()
        logger.exception("[AS_DRAWING] %s order %s: %s", command, order_id, exc)
        return None, _fail("AS 도면을 저장하지 못했어요.", 500)
    _invalidate(order_id)
    enqueue_as_drawing_push(db, captured.get("notices"))
    return captured.get("result") or {}, None


def _invalidate(order_id: int) -> None:
    try:
        invalidate_dashboard_families(DASHBOARD_FAMILY_DRAWING, DASHBOARD_FAMILY_ORDERS)
    except Exception as err:  # noqa: BLE001 - fail-open(TTL 이 결국 맞춘다)
        logger.warning("[AS_DRAWING] cache invalidate failed (order %s): %s", order_id, err)


def _actor(user: Any) -> tuple[Any, str]:
    return getattr(user, "id", None), getattr(user, "name", None) or getattr(user, "username", "") or ""


def _now() -> str:
    return now_utc_naive().isoformat()


def _open_as_view(sd: dict) -> dict | None:
    """열린 AS 접수 요약(화면이 '이 접수에 묶기'로 보여 준다)."""
    if not open_as_cycle_id(sd):
        return None
    cycle = current_cycle(sd) or {}
    shipment = sd.get("shipment") if isinstance(sd.get("shipment"), dict) else {}
    return {
        "cycle_id": cycle.get("cycle_id"),
        "received_date": cycle.get("received_date") or "",
        "content": as_content_html_to_text(shipment.get("as_content") or "")[:300],
    }


@erp_orders_as_drawing_bp.route("/<int:order_id>/drawing/as", methods=["GET"])
def api_as_drawing_get(order_id: int):
    """지금 차수와 지난 차수, 시작할 수 있는지를 돌려준다."""
    user = getattr(g, "current_user", None)
    if user is None:
        return _fail("로그인이 필요해요.", 401, "AUTH_REQUIRED")
    if is_partner_user(user):
        return _fail("볼 수 없는 주문이에요.", 403, "FORBIDDEN")
    db = get_db()
    order, err = _load_order(db, order_id)
    if err:
        return err
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    cur = current_round(sd)
    as_stage = is_as_drawing_stage(order)

    def _view(rnd):
        out = round_view(sd, rnd)
        if out:
            # 저장된 URL 은 믿지 않는다 — key 로만 같은 출처 주소를 만든다(작업실 갤러리와 같은 규칙).
            for f in out["files"]:
                f["view_url"] = "/api/files/view/" + str(f.get("key") or "")
        return out

    review_ok = evaluate_policy(POLICY_REGISTRY[CONFIRM_POLICY_ID], user).allowed
    return jsonify({"success": True, "error": None, "data": {
        "as_stage": as_stage,
        "can_start": bool(as_stage and cur is None),
        "can_review": bool(review_ok and cur is not None and cur.get("status") == "TRANSFERRED"),
        "open_as": _open_as_view(sd),
        "current": _view(cur),
        "rounds": [_view(r) for r in rounds(sd)],
        "workbench_url": f"/erp/drawing-workbench/{order_id}",
        "mutation_version": getattr(order, "mutation_version", None),
    }})


@erp_orders_as_drawing_bp.route("/<int:order_id>/drawing/as/start", methods=["POST"])
def api_as_drawing_start(order_id: int):
    """도면팀이 AS 도면을 시작한다.

    열린 AS 접수가 있으면 거기에 묶는다. 없으면 ``as_register.content`` 로 AS 접수를 함께 한다 —
    지금 AS 접수 본체(``register_as_from_payload``)를 그대로 불러 같은 mutation 안에서 차수를 연다.
    채널톡 접수(AS PUSH)는 화면이 이 응답 뒤에 따로 부른다(설계서 §4.2-5).
    """
    user, err = _guard(DRAWING_POLICY_ID)
    if err:
        return err
    db = get_db()
    order, err = _load_order(db, order_id)
    if err:
        return err
    if not is_as_drawing_stage(order):
        return _fail("시공이 끝난 주문에서만 AS 도면을 시작할 수 있어요.", 409, "NOT_AS_STAGE")
    payload = request.get_json(silent=True) or {}
    memo = str(payload.get("memo") or "").strip()[:500]
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    if current_round(sd) is not None:
        return _fail("이미 그리고 있는 AS 도면이 있어요.", 409, "AS_DRAWING_OPEN")

    if open_as_cycle_id(sd) is None:
        reg = payload.get("as_register") if isinstance(payload.get("as_register"), dict) else {}
        content = str(reg.get("content") or "").strip()
        if not content:
            return _fail("이 주문은 AS 접수가 없어요. AS 내용을 적어 주세요.", 400, "AS_CONTENT_REQUIRED")
        resp = make_response(register_as_from_payload(
            order_id,
            {"as_content": content, "source_screen": "drawing_workbench", "billing_type": "free"},
            user.id,
            drawing_round={"source": SOURCE_DRAWING_FIRST, "status": STATUS_IN_PROGRESS,
                           "memo": memo or content[:500], "registered_as": True},
        ))
        body = resp.get_json(silent=True) or {}
        if resp.status_code >= 400 or not body.get("success"):
            return _fail(body.get("message") or "AS 접수를 하지 못했어요.",
                         resp.status_code if resp.status_code >= 400 else 409, "AS_REGISTER_FAILED")
        if body.get("as_drawing") != "opened":
            return _fail("AS 접수는 됐지만 AS 도면을 시작하지 못했어요. 다시 눌러 주세요.", 409,
                         "AS_DRAWING_NOT_OPENED")
        return jsonify({"success": True, "error": None, "data": {
            "registered_as": True,
            "round": body.get("as_drawing_round"),
            "cycle_no": body.get("cycle_no"),
            "reception_log_id": body.get("reception_log_id") or "",
            "mutation_version": body.get("mutation_version"),
        }})

    actor_id, actor_name = _actor(user)

    def _apply(sess, locked_order, locked_sd):
        cycle_id = open_as_cycle_id(locked_sd)
        rnd = open_round(locked_sd, source=SOURCE_DRAWING_FIRST, status=STATUS_IN_PROGRESS, memo=memo,
                         actor_id=actor_id, actor_name=actor_name, now_iso=_now(), cycle_id=cycle_id)
        return {"round": round_view(locked_sd, rnd)}

    result, err = _run(order_id, user, "start", {"memo": memo}, _apply)
    if err:
        return err
    return jsonify({"success": True, "error": None, "data": {"registered_as": False, **result}})


def run_as_transfer(order_id: int, user: Any, note: str = ""):
    """이번 차수 AS 시트 대기함 그림을 보낸다 — ``/drawing/as/transfer`` 와 마법사 ``transfer-pending``
    (시공이 끝난 주문) 이 같이 부른다. 권한은 부르는 쪽이 판정한다.

    Returns:
        ``(결과 dict, None)`` 또는 ``(None, 오류 응답)``.
    """
    note = str(note or "").strip()[:500]
    actor_id, actor_name = _actor(user)

    def _apply(sess, locked_order, sd):
        out = transfer_round(sd, actor_id=actor_id, actor_name=actor_name, now_iso=_now(), note=note)
        rnd = out["round"]
        locked_order.structured_data = sd  # 알림 본문이 최신 값을 읽게
        # 영업 쪽 수신은 도면 전달 알림과 같은 규칙(담당 영업 본인 · 라홈/하우드는 CS · 협력사는 CS).
        sales_target = _drawing_notice_target(sess, order_manager_label(sd), partner=is_partner_sd(sd))
        notices = notify_as_drawing(sess, locked_order, "transfer", round_no=round_no(sd, rnd), actor=user,
                                    text=note, sales_target=sales_target)
        return {"round": round_view(sd, rnd), "sent": len(out["files"]), "replaced": out["replaced"],
                "_notices": notices}

    return _run(order_id, user, "transfer", {"note": note}, _apply)


@erp_orders_as_drawing_bp.route("/<int:order_id>/drawing/as/transfer", methods=["POST"])
def api_as_drawing_transfer(order_id: int):
    """이번 차수 AS 시트의 대기함 그림을 차수 파일로 보낸다. 영업 담당 · CS 팀에 알린다."""
    user, err = _guard(DRAWING_POLICY_ID)
    if err:
        return err
    db = get_db()
    order, err = _load_order(db, order_id)
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    result, err = run_as_transfer(order_id, user, payload.get("note") or "")
    if err:
        return err
    return jsonify({"success": True, "error": None, "data": result})


@erp_orders_as_drawing_bp.route("/<int:order_id>/drawing/as/confirm", methods=["POST"])
def api_as_drawing_confirm(order_id: int):
    """영업 담당 · AS 담당 중 한 명이 확인하면 끝난다."""
    user, err = _guard(CONFIRM_POLICY_ID)
    if err:
        return err
    db = get_db()
    order, err = _load_order(db, order_id)
    if err:
        return err
    actor_id, actor_name = _actor(user)

    def _apply(sess, locked_order, sd):
        rnd = confirm_round(sd, actor_id=actor_id, actor_name=actor_name, now_iso=_now())
        locked_order.structured_data = sd
        notify_as_drawing(sess, locked_order, "confirm", round_no=round_no(sd, rnd), actor=user,
                          opener_id=rnd.get("opened_by"))
        return {"round": round_view(sd, rnd)}

    result, err = _run(order_id, user, "confirm", {}, _apply)
    if err:
        return err
    return jsonify({"success": True, "error": None, "data": result})


@erp_orders_as_drawing_bp.route("/<int:order_id>/drawing/as/request-revision", methods=["POST"])
def api_as_drawing_request_revision(order_id: int):
    """영업 담당 · AS 담당이 고쳐 달라고 한다(사유 필수)."""
    user, err = _guard(CONFIRM_POLICY_ID)
    if err:
        return err
    db = get_db()
    order, err = _load_order(db, order_id)
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip()[:500]
    actor_id, actor_name = _actor(user)

    def _apply(sess, locked_order, sd):
        rnd = request_revision(sd, actor_id=actor_id, actor_name=actor_name, now_iso=_now(), reason=reason)
        locked_order.structured_data = sd
        notices = notify_as_drawing(sess, locked_order, "revision", round_no=round_no(sd, rnd), actor=user,
                                    text=reason, opener_id=rnd.get("opened_by"))
        return {"round": round_view(sd, rnd), "_notices": notices}

    result, err = _run(order_id, user, "request-revision", {"reason": reason}, _apply)
    if err:
        return err
    return jsonify({"success": True, "error": None, "data": result})


@erp_orders_as_drawing_bp.route("/<int:order_id>/drawing/as/cancel", methods=["POST"])
def api_as_drawing_cancel(order_id: int):
    """한 번도 안 보낸 차수를 그만둔다. 도면팀이 함께 만든 AS 접수는 지우지 않는다."""
    user, err = _guard(DRAWING_POLICY_ID)
    if err:
        return err
    db = get_db()
    order, err = _load_order(db, order_id)
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip()[:500]
    actor_id, actor_name = _actor(user)

    def _apply(sess, locked_order, sd):
        rnd = cancel_round(sd, actor_id=actor_id, actor_name=actor_name, now_iso=_now(), reason=reason)
        return {"round": round_view(sd, rnd)}

    result, err = _run(order_id, user, "cancel", {"reason": reason}, _apply)
    if err:
        return err
    return jsonify({"success": True, "error": None, "data": result})

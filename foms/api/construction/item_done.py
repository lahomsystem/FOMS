"""제품마다 '시공 끝' — [시공 완료]의 나눠 시공 갈래 + "오늘 끝낸 제품" 목록 API.

설계: ``docs/specs/2026-11-21-item-construction-done_SPEC.md`` 4 · 5 (N2 · N3 · N5 · N6).

* ``GET /api/orders/<id>/construction/visit-items?date=YYYY-MM-DD`` — 완료 창의 체크 목록.
* [시공 완료](``orders.api_construction_complete``)는 스위치가 켜진 나눠 시공 주문이면
  :func:`split_complete_response` 로 넘긴다. 고른 제품을 찍은 뒤
  - 남은 제품이 있으면 **부분 방문**: 지금 방문 줄을 ``VISITED`` 로 봉인하고 사진 · 서명 칸을 비운다.
    단계 · 주문 상태 · 단계 알림은 그대로다(REV-00 :func:`execute_order_mutation` 한 거래).
  - 남은 제품이 0개면 **완료**: 찍은 표시를 먼저 내려 보낸(flush) 뒤 지금의 CONSTRUCTION→CS 전이를
    같은 거래에서 탄다 — 전이 엔진이 잠금 아래에서 주문을 다시 읽어도 찍은 표시가 보인다.

이 모듈은 ``orders`` 의 헬퍼를 쓴다. ``orders`` 는 그 헬퍼를 다 정의한 뒤 모듈 중간에서 이 모듈을 가져온다
(순서 고정 — 함수 안 지연 import 래칫을 늘리지 않는다). api → web import 도 늘리지 않는다(레이어 래칫).
"""
from __future__ import annotations

import copy
import uuid
from typing import Any, Optional

from flask import jsonify, request
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from foms.api.construction.orders import (
    _CONSTRUCTION_STAGES,
    _POLICY_CONSTRUCTION_COMPLETE,
    _apply_complete_side_effects,
    _audit_construction,
    _current_attempt,
    _evidence_gate_missing,
    _fresh_evidence,
    _idempotency_key,
    _idempotency_receipt_exists,
    _live_evidence,
    _request_hash,
    _scheduled_date,
    _scope_hash,
    _transition_error_response,
    erp_orders_construction_bp,
)
from foms.services.datetime_kst import get_today_kst, now_kst, now_utc_naive
from foms.services.erp_display import _ensure_dict
from foms.services.erp_permissions import erp_construction_edit_required
from foms.services.feature_flags import env_bool, is_item_construction_done_enabled
from foms.services.measurement.visit_check import normalize_visit_date
from foms.services.orders.admin_override import record_admin_override_event
from foms.services.orders.construction_visit import (
    PARTIAL_VISIT_NOTE_PREFIX,
    VISITED_STATUS,
    done_entries,
    names_for_uids,
    partial_visit_note,
    remaining_entries,
)
from foms.services.orders.item_construction_done import (
    SOURCE_VISIT,
    apply_done_marks,
    is_split_order,
    remaining_lines,
    remaining_summary,
    visit_candidates,
)
from foms.services.orders.order_transition_service import TransitionError, transition_order
from foms.services.orders.revision import RevisionError, execute_order_mutation, lock_order_row
from foms.services.orders.state_axes import read_main_stage
from foms.services.partners.notify import notify_partner_construction_done
from models import Order, OrderConstructionAttempt, OrderEvent

__all__ = [
    "ITEM_CONSTRUCTION_DONE",
    "CONSTRUCTION_VISIT_DONE",
    "api_construction_visit_items",
    "split_complete_response",
]

#: 부분 방문 receipt 범위(완료와 다른 정책 문자열 — 같은 키로 완료를 다시 눌러도 방문 replay 가 아니다).
_POLICY_CONSTRUCTION_VISIT = "STATE_CONSTRUCTION_VISIT"

ITEM_CONSTRUCTION_DONE = "ITEM_CONSTRUCTION_DONE"
CONSTRUCTION_VISIT_DONE = "CONSTRUCTION_VISIT_DONE"

_PRODUCTION_STAGES = ("생산", "PRODUCTION")
_ERR_NOT_FOUND = "주문을 찾을 수 없습니다."
_ERR_DATE = "날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)."
_ERR_DONE_ITEMS = "오늘 끝낸 제품을 골라 주세요"
_ERR_PRODUCTION = "제작 완료를 먼저 눌러 주세요"


def _is_gone(order: Optional[Order]) -> bool:
    return (
        order is None
        or getattr(order, "status", None) == "DELETED"
        or getattr(order, "deleted_at", None) is not None
    )


def _fail(error: str, status: int, **extra: Any):
    payload: dict[str, Any] = {"success": False, "data": None, "error": error, "message": error}
    payload.update(extra)
    return jsonify(payload), status


# --------------------------------------------------------------------------- #
# GET 오늘 끝낸 제품 목록
# --------------------------------------------------------------------------- #
@erp_orders_construction_bp.route("/<int:order_id>/construction/visit-items", methods=["GET"])
@erp_construction_edit_required  # 로그인 없으면 401 · 시공 권한(can_act_construction) 없으면 403
def api_construction_visit_items(order_id):
    """[시공 완료] 창의 "오늘 끝낸 제품" 체크 목록. 스위치가 꺼졌거나 나눠 시공이 아니면 빈 목록."""
    raw_date = request.args.get("date")
    day_iso = normalize_visit_date(raw_date) if raw_date else get_today_kst().isoformat()
    if day_iso is None:
        return _fail(_ERR_DATE, 400)
    order = get_db().get(Order, order_id)
    if _is_gone(order):
        return _fail(_ERR_NOT_FOUND, 404)

    sd = _ensure_dict(order.structured_data)
    enabled = is_item_construction_done_enabled()
    split = enabled and is_split_order(sd)
    data = {
        "enabled": enabled,
        "split": split,
        "date": day_iso,
        "items": visit_candidates(sd, day_iso) if split else [],
        "done": done_entries(sd) if split else [],
        "remaining_summary": remaining_summary(sd) if split else "",
    }
    return jsonify({"success": True, "data": data, "error": None})


# --------------------------------------------------------------------------- #
# [시공 완료] 나눠 시공 갈래
# --------------------------------------------------------------------------- #
def _done_refs(body: dict[str, Any]) -> list[str]:
    raw = body.get("done_item_uids")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for ref in raw:
        text = str(ref).strip() if isinstance(ref, (str, int)) and not isinstance(ref, bool) else ""
        if text and text not in out:
            out.append(text)
    return out


def _visit_day(body: dict[str, Any]) -> str:
    """방문 날 — 몸의 ``visit_date`` 가 바른 ``YYYY-MM-DD`` 면 그 날, 아니면 오늘(KST)."""
    return normalize_visit_date(body.get("visit_date")) or get_today_kst().isoformat()


def _user_name(user: Any) -> str:
    return getattr(user, "name", None) or "Unknown"


def split_complete_response(db: Any, order_id: int, *, body: dict[str, Any], user: Any, user_id: Any,
                            override: Any):
    """스위치가 켜진 나눠 시공 주문의 [시공 완료] — 부분 방문 또는 완료(설계서 5.3).

    판정은 잠근 최신 행으로 한다(:func:`lock_order_row`). 본문 ``done_item_uids`` 는 남은 제품의
    참조(uid 또는 ``idx:N``)만 받고 나머지는 버린다.
    """
    order = lock_order_row(db, order_id)
    if _is_gone(order):
        return _fail(_ERR_NOT_FOUND, 404)
    idem_key = _idempotency_key(body)
    ctx = {
        "body": body, "user": user, "user_id": user_id, "override": override, "idem_key": idem_key,
        "day_iso": _visit_day(body), "note": (body.get("completion_note") or "").strip(),
    }
    # 같은 키 재요청은 문을 다시 보지 않는다 — 엔진이 저장된 응답으로 replay 한다.
    if _idempotency_receipt_exists(db, user_id, _POLICY_CONSTRUCTION_VISIT, idem_key):
        return _partial_visit(db, order, [], [], ctx)
    if _idempotency_receipt_exists(db, user_id, _POLICY_CONSTRUCTION_COMPLETE, idem_key):
        return _full_complete(db, order, [], [], ctx)

    sd = _ensure_dict(order.structured_data)
    remaining_before = remaining_lines(sd)
    open_refs = {line.ref for line in remaining_before}
    wanted = [ref for ref in _done_refs(body) if ref in open_refs]
    if remaining_before and not wanted:
        return _fail(_ERR_DONE_ITEMS, 400, code="DONE_ITEMS_REQUIRED")
    preview = copy.deepcopy(sd)
    apply_done_marks(preview, wanted, day_iso=ctx["day_iso"], at_iso="", user_id=None, user_name="")
    full = not remaining_lines(preview)
    stage_code = order.erp_stage_code
    if full and stage_code in _PRODUCTION_STAGES:
        return _fail(_ERR_PRODUCTION, 400, code="PRODUCTION_NOT_DONE")

    punched: list[str] = []
    if env_bool("FOMS_CONSTRUCTION_GATE_ENABLED", default=True):
        missing = _evidence_gate_missing(order)
        if missing:
            if override is None:
                return (jsonify({"success": False, "error": "완료 요건 미충족", "message": "완료 요건 미충족",
                                 "data": {"missing": missing}}), 400)
            punched.append("EVIDENCE_MISSING")
    allowed_stages = _CONSTRUCTION_STAGES if full else _CONSTRUCTION_STAGES + _PRODUCTION_STAGES
    if stage_code not in allowed_stages:
        if override is None:
            return jsonify({"success": False, "code": "INVALID_STAGE",
                            "message": "시공중 상태에서만 시공을 완료할 수 있습니다."}), 409
        punched.append("INVALID_STAGE")
    if full:
        return _full_complete(db, order, wanted, punched, ctx)
    return _partial_visit(db, order, wanted, punched, ctx)


def _item_done_event(order_id: int, uids: list[str], names: list[str], day_iso: str,
                     attempt_id: Optional[str], user_id: Any) -> OrderEvent:
    return OrderEvent(
        order_id=order_id, event_type=ITEM_CONSTRUCTION_DONE,
        payload={"item_uids": uids, "names": names, "date": day_iso, "attempt_id": attempt_id,
                 "source": SOURCE_VISIT},
        created_by_user_id=user_id,
    )


def _full_complete(db: Any, order: Order, wanted: list[str], punched: list[str], ctx: dict[str, Any]):
    """마지막 방문 — 남은 제품을 찍고 같은 거래에서 CONSTRUCTION→CS 전이(지금의 시공 완료)."""
    user, user_id, override, day_iso = ctx["user"], ctx["user_id"], ctx["override"], ctx["day_iso"]
    from_stage = read_main_stage(order)
    marked: list[str] = []
    if wanted:
        attempt = _current_attempt(db, order.id)
        sd = copy.deepcopy(_ensure_dict(order.structured_data))
        marked = apply_done_marks(
            sd, wanted, day_iso=day_iso, at_iso=now_kst().isoformat(timespec="seconds"),
            user_id=user_id, user_name=_user_name(user), source=SOURCE_VISIT,
            attempt_id=attempt.id if attempt is not None else None)
        order.structured_data = sd
        flag_modified(order, "structured_data")
        db.add(_item_done_event(order.id, marked, names_for_uids(sd, marked), day_iso,
                                attempt.id if attempt is not None else None, user_id))
        # 전이 엔진은 깨끗한 주문을 비우고 잠금 조회로 다시 채운다 — 먼저 내려 보내야 찍은 표시가
        # 그 재조회(와 엔진 안 문지기)에도 보인다. 실패하면 호출자 rollback 으로 함께 사라진다.
        db.flush()
    try:
        result = transition_order(
            db, command_id="CONSTRUCTION_COMPLETE", order_id=order.id,
            actor_user_id=user_id, expected_from=from_stage, target_value="CS",
            scope_hash=_scope_hash("CONSTRUCTION_COMPLETE", order.id),
            request_hash=_request_hash(ctx["body"]), idempotency_key=ctx["idem_key"],
            emergency_override=bool(override),
            reason=(override.reason if override is not None else None),
        )
    except (TransitionError, RevisionError) as exc:
        db.rollback()
        return _transition_error_response(exc)

    if not result.replayed:
        visit = {"date": day_iso, "item_uids": marked} if marked else None
        _apply_complete_side_effects(db, order, user, user_id, ctx["note"], visit=visit)
    if override is not None and punched:
        record_admin_override_event(
            db, order, override=override, gates=punched,
            route="erp_orders_construction.api_construction_complete", axis="MAIN",
            from_value=from_stage, to_value="CS")
    db.commit()
    notify_partner_construction_done(db, order)
    return jsonify({
        "success": True, "message": "시공이 완료되었습니다. CS 단계로 이동합니다.", "new_status": "CS",
        "data": {"mode": "complete", "remaining_summary": "", "remaining": [], "done_item_uids": marked},
        "error": None,
    })


def _seal_visit_attempt(attempt: OrderConstructionAttempt, sd: dict[str, Any], marked: list[str],
                        ctx: dict[str, Any]) -> None:
    """지금 방문 줄을 VISITED 로 닫고 사진 · 서명 사본 + ``visit`` 을 봉인한다(설계서 4.2 ①)."""
    snapshot = _live_evidence(sd)
    snapshot["visit"] = {"date": ctx["day_iso"], "item_uids": list(marked)}
    attempt.evidence = snapshot
    attempt.status = VISITED_STATUS
    attempt.is_current = False
    attempt.completed_at = now_utc_naive()
    attempt.completed_by = getattr(ctx["user"], "name", None)
    if ctx["note"]:
        attempt.completion_note = ctx["note"]


def _partial_visit(db: Any, order: Order, wanted: list[str], punched: list[str], ctx: dict[str, Any]):
    """부분 방문 — 고른 제품만 '시공 끝', 방문 봉인, 사진 · 서명 칸 비움. 단계 · 상태 · 알림 그대로."""
    user, user_id, override, day_iso = ctx["user"], ctx["user_id"], ctx["override"], ctx["day_iso"]
    captured: dict[str, Any] = {}

    def _mutate(sess: Any, orders: list[Order]) -> dict[int, list[str]]:
        o = orders[0]
        sd = copy.deepcopy(_ensure_dict(o.structured_data))
        attempt = _current_attempt(sess, o.id)
        if attempt is None:  # [시공 시작] 없이 끝낸 옛 흐름 — 방문 기록이 남도록 닫힌 줄을 하나 만든다.
            attempt = OrderConstructionAttempt(id=str(uuid.uuid4()), order_id=o.id, status=VISITED_STATUS,
                                               is_current=False, scheduled_date=_scheduled_date(sd))
            sess.add(attempt)
        marked = apply_done_marks(
            sd, wanted, day_iso=day_iso, at_iso=now_kst().isoformat(timespec="seconds"),
            user_id=user_id, user_name=_user_name(user), source=SOURCE_VISIT, attempt_id=attempt.id)
        _seal_visit_attempt(attempt, sd, marked, ctx)  # 사진 · 서명 칸을 비우기 전에 봉인한다.
        construction = sd.get("construction") if isinstance(sd.get("construction"), dict) else {}
        construction["evidence"] = _fresh_evidence()  # 첨부 줄 · 파일은 지우지 않는다(참조만 비움).
        sd["construction"] = construction
        names = names_for_uids(sd, marked)
        note = partial_visit_note(names, sd)
        if ctx["note"]:
            note += " | 코멘트: " + ctx["note"][:100]
        wf = sd.get("workflow") if isinstance(sd.get("workflow"), dict) else {}
        hist = wf.get("history") if isinstance(wf.get("history"), list) else []
        hist.append({"stage": read_main_stage(o) or "CONSTRUCTION", "updated_at": now_utc_naive().isoformat(),
                     "updated_by": _user_name(user), "note": note})
        wf["history"] = hist
        sd["workflow"] = wf
        o.structured_data = sd
        flag_modified(o, "structured_data")
        summary = remaining_summary(sd)
        sess.add(_item_done_event(o.id, marked, names, day_iso, attempt.id, user_id))
        sess.add(OrderEvent(
            order_id=o.id, event_type=CONSTRUCTION_VISIT_DONE,
            payload={"attempt_id": attempt.id, "date": day_iso, "item_uids": marked, "names": names,
                     "remaining_summary": summary},
            created_by_user_id=user_id,
        ))
        captured.update(attempt_id=attempt.id, marked=marked, names=names, summary=summary)
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    try:
        result = execute_order_mutation(
            db, actor_user_id=user_id, policy_id=_POLICY_CONSTRUCTION_VISIT, order_ids=[order.id],
            scope_hash=_scope_hash("CONSTRUCTION_VISIT", order.id), request_hash=_request_hash(ctx["body"]),
            mutation=_mutate, idempotency_key=ctx["idem_key"],
        )
    except RevisionError as exc:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(exc), "code": exc.error_code}), exc.status_code

    if not result.replayed:
        _audit_construction(
            order, CONSTRUCTION_VISIT_DONE, user_id, note=" · ".join(captured["names"]) or None,
            extra={"attempt_id": captured["attempt_id"], "date": day_iso, "item_uids": captured["marked"],
                   "remaining_summary": captured["summary"], "completion_note": ctx["note"] or None},
        )
    if override is not None and punched:
        record_admin_override_event(
            db, order, override=override, gates=punched,
            route="erp_orders_construction.api_construction_complete", axis="CONSTRUCTION",
            from_value="", to_value="")
    db.commit()
    sd_after = _ensure_dict(order.structured_data)
    summary = remaining_summary(sd_after)
    return jsonify({
        "success": True,
        "message": f"{PARTIAL_VISIT_NOTE_PREFIX}으로 기록했어요." + (f" 남은 시공: {summary}" if summary else ""),
        "data": {"mode": "visit", "remaining_summary": summary, "remaining": remaining_entries(sd_after),
                 "attempt_id": captured.get("attempt_id"), "done_item_uids": captured.get("marked", [])},
        "error": None,
    })

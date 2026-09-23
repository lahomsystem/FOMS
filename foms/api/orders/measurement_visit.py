"""실측 방문 체크("실측만 완료") API (MEASUREMENT-VISIT-01).

``POST /api/orders/<id>/measurement-visit`` body ``{"date": "YYYY-MM-DD", "done": bool}``.
``structured_data['measurement_visits'][date]`` 에 체크 기록을 넣거나 지운다. 이 체크는 카드의
"실측 완료" 버튼(``measurement_completed`` · 도면 넘김)과 **다른 개념**이라 단계 전이·quest·
``measurement_completed``·알림을 전혀 건드리지 않는다.

쓰기는 REV-00 :func:`execute_order_mutation` 한 트랜잭션(row lock · mutation_version bump ·
idempotency receipt · OrderEvent parity)이다. 권한은 정책 ``ERP_EDIT``.

레이어 방향 래칫 때문에 ``foms.web.auth`` 를 import 하지 않는다 — 사용자는 ``g.current_user``,
감사는 ``SecurityLog`` 를 본 트랜잭션에 직접 싣는다(``mobile_delete.py`` 와 같은 방식).
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from typing import Any, List, Mapping, Optional

from flask import g, jsonify, request, session
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from foms.services.audit_message_display import describe_order_action
from foms.services.audit_writer import normalize_security_detail
from foms.services.common.dashboard_cache import (
    DASHBOARD_FAMILY_MEASUREMENT,
    invalidate_dashboard_families,
)
from foms.services.datetime_kst import now_kst
from foms.services.measurement.visit_check import (
    apply_visit_mark,
    is_visit_marked,
    normalize_visit_date,
    visit_entry,
)
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.orders.revision import RevisionError, execute_order_mutation
from models import Order, OrderEvent, SecurityLog

logger = logging.getLogger(__name__)

MEASUREMENT_VISIT_POLICY_ID = "ERP_EDIT"
MEASUREMENT_VISIT_MARKED = "MEASUREMENT_VISIT_MARKED"
MEASUREMENT_VISIT_UNMARKED = "MEASUREMENT_VISIT_UNMARKED"

_ERR_DATE = "실측일 형식이 올바르지 않습니다 (YYYY-MM-DD)."
_ERR_DONE = "체크 값(done)은 true 또는 false 여야 합니다."
_ERR_NOT_FOUND = "주문을 찾을 수 없습니다."
_ERR_IF_MATCH = "If-Match 형식이 올바르지 않습니다."
_ERR_SERVER = "실측 체크 저장 중 오류가 발생했습니다."


def _fail(error: str, status: int, **extra: Any):
    payload: dict = {"success": False, "data": None, "error": error}
    payload.update(extra)
    return jsonify(payload), status


def _by_name(user: Any) -> str:
    return getattr(user, "name", None) or session.get("username") or "SYSTEM"


def _mutation_hashes(order_id: int, date_iso: str, done: bool) -> tuple:
    """(scope_hash, request_hash) — receipt 저장·같은 키 다른 본문 감지용 sha256."""
    scope = hashlib.sha256(
        f"{MEASUREMENT_VISIT_POLICY_ID}:MEASUREMENT_VISIT:{order_id}".encode()
    ).hexdigest()
    body = json.dumps({"date": date_iso, "done": done}, sort_keys=True)
    return scope, hashlib.sha256(body.encode()).hexdigest()


def _visit_data(sd: Any, date_iso: str, done: bool, *, changed: bool, receipt: Any) -> dict:
    entry = visit_entry(sd, date_iso) if done else None
    return {
        "date": date_iso,
        "done": done,
        "at": (entry or {}).get("at"),
        "by_name": (entry or {}).get("by_name"),
        "changed": changed,
        "mutation_receipt": receipt,
    }


def _add_audit(sess: Any, *, order: Order, user_id: Any, date_iso: str, done: bool) -> None:
    """감사행을 본 트랜잭션에 싣는다(업무 변경이 되감기면 감사도 함께 되감긴다)."""
    ctx = order_audit_context(order)
    detail = normalize_security_detail({"date": date_iso, "done": done, **ctx})
    if done:
        message = describe_order_action(
            order_id=order.id, action="ORDER_MEASUREMENT_VISIT_MARKED", note=date_iso, **ctx
        )
        sess.add(SecurityLog(
            user_id=user_id, message=message, action="ORDER_MEASUREMENT_VISIT_MARKED",
            target_type="order", target_id=int(order.id), detail=detail,
        ))
    else:
        message = describe_order_action(
            order_id=order.id, action="ORDER_MEASUREMENT_VISIT_UNMARKED", note=date_iso, **ctx
        )
        sess.add(SecurityLog(
            user_id=user_id, message=message, action="ORDER_MEASUREMENT_VISIT_UNMARKED",
            target_type="order", target_id=int(order.id), detail=detail,
        ))


class _NoVisitChange(Exception):
    """잠금 아래에서 다시 보니 이미 요청 상태였다(경합) — 쓰기 없이 되감고 ``changed:false`` 로 끝낸다."""

    def __init__(self, sd: Any) -> None:
        super().__init__("measurement visit already in requested state")
        self.sd = sd


def _invalidate_measurement_caches() -> None:
    try:
        invalidate_dashboard_families(DASHBOARD_FAMILY_MEASUREMENT)
    except Exception:  # noqa: BLE001 - 캐시 무효화 실패는 저장 결과를 바꾸지 않는다
        logger.warning("[ORDERS] measurement-visit 캐시 무효화 실패", exc_info=True)


def measurement_visit_response(order_id: int) -> Any:
    """실측 방문 체크/해제. 같은 상태면 쓰기 없이 ``changed:false`` 로 성공한다."""
    db: Session = get_db()

    # 1) 권한 — ERP_EDIT(STAFF+CS/SALES 또는 ADMIN/MANAGER; VIEWER 거부).
    user = getattr(g, "current_user", None)
    decision = evaluate_policy(POLICY_REGISTRY[MEASUREMENT_VISIT_POLICY_ID], user)
    if not decision.allowed:
        return _fail(decision.reason, decision.status, message=decision.reason, code=decision.code)

    # 2) 입력 — date(엄격 ISO)·done(bool) 만 읽는다. 다른 키는 무시.
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        body = {}
    date_iso = normalize_visit_date(body.get("date"))
    if not date_iso:
        return _fail(_ERR_DATE, 400)
    done = body.get("done")
    if not isinstance(done, bool):
        return _fail(_ERR_DONE, 400)

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return _fail(_ERR_NOT_FOUND, 404)

    # 3) optional If-Match(mutation_version) — 형식 오류는 400.
    if_match_raw = (request.headers.get("If-Match") or "").strip().strip('"')
    expected_versions: Optional[Mapping[int, int]] = None
    if if_match_raw:
        try:
            expected_versions = {order_id: int(if_match_raw)}
        except ValueError:
            return _fail(_ERR_IF_MATCH, 400)
    idempotency_key = (request.headers.get("Idempotency-Key") or "").strip() or None

    # 4) 사전 no-op — execute_order_mutation 은 부르기만 해도 버전을 올리므로 잠금 전에 끝낸다.
    #    If-Match 가 먼저다(잠금 경로와 같은 순서): 버전이 어긋나면 no-op 로 끝내지 않고 잠금
    #    경로로 보내 409 를 받게 한다.
    if_match_ok = expected_versions is None or order.mutation_version == expected_versions[order_id]
    if if_match_ok and is_visit_marked(order.structured_data, date_iso) == done:
        data = _visit_data(order.structured_data, date_iso, done, changed=False, receipt=None)
        return jsonify({"success": True, "data": data, "error": None})

    # 위 읽기는 잠금 전 값이다. 비워 두어야 FOR UPDATE 조회가 최신 structured_data 로 다시 채운다
    # (identity map 이 같은 객체를 돌려주므로, 비우지 않으면 낡은 값을 통째로 되써 lost update).
    db.expire(order)

    user_id = session.get("user_id") or getattr(user, "id", None)
    by_name = _by_name(user)
    scope_hash, request_hash = _mutation_hashes(order_id, date_iso, done)
    captured: dict = {}

    def _mutate(sess: Session, orders: List[Order]) -> Mapping[int, List[str]]:
        """row lock 아래에서 measurement_visits 한 날짜만 고친다(축 불변)."""
        o = orders[0]
        sd = copy.deepcopy(o.structured_data) if isinstance(o.structured_data, dict) else {}
        changed = apply_visit_mark(
            sd, date_iso, done,
            at_iso=now_kst().isoformat(timespec="seconds"),
            by_user_id=user_id, by_name=by_name,
        )
        if not changed:
            # 경합으로 이미 같은 상태 — JSONB 쓰기·버전 bump·receipt 없이 되감는다(스펙 §3 no-op).
            raise _NoVisitChange(o.structured_data)
        o.structured_data = sd
        flag_modified(o, "structured_data")
        sess.add(OrderEvent(
            order_id=o.id,
            event_type=MEASUREMENT_VISIT_MARKED if done else MEASUREMENT_VISIT_UNMARKED,
            payload={"date": date_iso},
            created_by_user_id=user_id,
        ))
        _add_audit(sess, order=o, user_id=user_id, date_iso=date_iso, done=done)
        captured["sd"] = sd
        captured["changed"] = changed
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    try:
        outcome = execute_order_mutation(
            db,
            actor_user_id=user_id,
            policy_id=MEASUREMENT_VISIT_POLICY_ID,
            order_ids=[order_id],
            expected_versions=expected_versions,
            idempotency_key=idempotency_key,
            scope_hash=scope_hash,
            request_hash=request_hash,
            mutation=_mutate,
        )
        db.commit()
    except _NoVisitChange as same:
        db.rollback()
        data = _visit_data(same.sd, date_iso, done, changed=False, receipt=None)
        return jsonify({"success": True, "data": data, "error": None})
    except RevisionError as rev:
        db.rollback()
        return _fail(str(rev), rev.status_code, code=rev.error_code)
    except Exception:  # noqa: BLE001 - 롤백 후 고정 문구 500
        db.rollback()
        logger.exception("[ORDERS] measurement-visit 저장 오류 order_id=%s", order_id)
        return _fail(_ERR_SERVER, 500)

    _invalidate_measurement_caches()

    if outcome.replayed:  # 같은 키 재요청: 저장된 상태를 다시 읽어 응답을 만든다.
        db.expire_all()
        fresh = db.query(Order).filter(Order.id == order_id).first()
        sd = fresh.structured_data if fresh else None
        done_now = is_visit_marked(sd, date_iso)  # 요청값이 아니라 지금 저장된 상태
        changed = True  # 원래 요청이 바꾼 것(replay 는 그 응답의 재현)
    else:
        sd = captured.get("sd")
        done_now = done
        changed = bool(captured.get("changed"))
    data = _visit_data(sd, date_iso, done_now, changed=changed, receipt=outcome.read_receipt_id)

    resp = jsonify({"success": True, "data": data, "error": None})
    for header, value in outcome.headers.items():
        resp.headers[header] = value
    return resp


__all__ = [
    "MEASUREMENT_VISIT_MARKED",
    "MEASUREMENT_VISIT_POLICY_ID",
    "MEASUREMENT_VISIT_UNMARKED",
    "measurement_visit_response",
]

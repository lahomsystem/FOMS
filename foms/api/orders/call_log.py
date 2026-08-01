"""통화 결과 기록 command ``CALL_LOGGED`` mutation handler (CALL-LOG-01).

`POST /api/orders/<id>/call-log` — sd['calls']에 통화 결과를 **append 1** 하고,
measurement_date가 오면 schedule.measurement.date를 갱신한다. 이 append 는 정본 command
``CALL_LOGGED`` 로, REV-00 :func:`execute_order_mutation` 경유로 mutation_version bump +
idempotency receipt + OrderEvent parity 를 **한 transaction** 에 원자화한다. 권한은 §2.1
canonical 정책 ``ERP_EDIT`` (STAFF+CS/SALES 또는 ADMIN/MANAGER; VIEWER deny) 로 enforce 한다.

**orthogonal write**: main/logistics/hold/AS/delete 축은 전혀 건드리지 않는다(call 은 축 전이가
아니다). body 의 비-화이트리스트 키(workflow/quest 등)는 무시한다(generic structured PUT 아님).
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import logging
from typing import Any, List, Mapping, Optional, Tuple

from flask import jsonify, request, session
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.orders.revision import RevisionError, execute_order_mutation
from foms.web.auth import get_user_by_id
from models import Order, OrderEvent, User

logger = logging.getLogger(__name__)

CALL_RESULTS = ("connected", "no_answer", "callback", "schedule_confirmed")
_CALLS_CAP = 50
_MEMO_MAX = 1000

#: 정본 command·정책 식별자. OrderEvent.event_type 와 receipt policy_id 가 공유한다.
CALL_LOGGED_COMMAND = "CALL_LOGGED"
CALL_LOG_POLICY_ID = "ERP_EDIT"


def _parse_payload(
    data: dict,
) -> Tuple[Optional[str], str, Optional[str], Optional[str]]:
    """Validate request body → (result, memo, measurement_date, error).

    error가 not None이면 400. measurement_date는 ISO(YYYY-MM-DD)만 허용. result/memo/
    measurement_date 외의 키는 읽지 않는다(generic structured PUT 아님).
    """
    result = data.get("result")
    if result not in CALL_RESULTS:
        return None, "", None, "유효하지 않은 통화 결과입니다."
    memo = (data.get("memo") or "")
    if not isinstance(memo, str):
        return None, "", None, "메모 형식이 올바르지 않습니다."
    memo = memo.strip()[:_MEMO_MAX]
    raw_date = (data.get("measurement_date") or "").strip()
    measurement_date: Optional[str] = None
    if raw_date:
        try:
            measurement_date = datetime.date.fromisoformat(raw_date).isoformat()
        except (ValueError, TypeError):
            return None, "", None, "실측일 형식이 올바르지 않습니다 (YYYY-MM-DD)."
    return result, memo, measurement_date, None


def _resolve_by_name(db: Any, user_id: Optional[int]) -> str:
    """세션 사용자 표시명(없으면 username, 그래도 없으면 SYSTEM)."""
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if user and getattr(user, "name", None):
        return user.name
    return session.get("username") or "SYSTEM"


def _append_call(sd: dict, result: str, memo: str, user_id: Optional[int], by_name: str) -> dict:
    """sd['calls']에 통화 로그 append (cap 50, 초과 시 앞에서 절단). 마지막 항목 반환."""
    calls = sd.get("calls")
    if not isinstance(calls, list):
        calls = []
    calls.append(
        {
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "by": user_id,
            "by_name": by_name,
            "result": result,
            "memo": memo,
        }
    )
    if len(calls) > _CALLS_CAP:
        calls = calls[-_CALLS_CAP:]
    sd["calls"] = calls
    return calls[-1]


def _mutation_hashes(
    order_id: int, result: str, memo: str, measurement_date: Optional[str]
) -> Tuple[str, str]:
    """(scope_hash, request_hash) — receipt 저장·same-key/different-hash 감지용 sha256."""
    scope = hashlib.sha256(f"{CALL_LOG_POLICY_ID}:{order_id}".encode()).hexdigest()
    request_payload = json.dumps(
        {"result": result, "memo": memo, "measurement_date": measurement_date},
        sort_keys=True,
        ensure_ascii=False,
    )
    return scope, hashlib.sha256(request_payload.encode()).hexdigest()


def log_call_response(order_id: int) -> Any:
    """통화 결과를 command ``CALL_LOGGED`` 로 원자 기록한다(필요 시 실측일 갱신).

    Body: {result, memo?, measurement_date?(ISO)}. optional 헤더 ``If-Match``
    (mutation_version 낙관 잠금) · ``Idempotency-Key`` (재요청 replay).
    반환: {success, data:{call, calls_count, mutation_receipt}} 또는 오류.
    """
    db: Session = get_db()

    # 1) §2.1 canonical 권한 — ERP_EDIT(STAFF+CS/SALES 또는 ADMIN/MANAGER; VIEWER deny).
    #    AUTH-01 before_request 가드가 꺼진 컨텍스트(TESTING 등)에서도 항상 enforce 한다.
    user = get_user_by_id(session.get("user_id"))
    decision = evaluate_policy(POLICY_REGISTRY[CALL_LOG_POLICY_ID], user)
    if not decision.allowed:
        return jsonify({
            "success": False,
            "data": None,
            "error": decision.reason,
            "message": decision.reason,
            "code": decision.code,
        }), decision.status

    # 2) payload 검증(비-화이트리스트 키는 무시).
    result, memo, measurement_date, err = _parse_payload(request.get_json(silent=True) or {})
    if err:
        return jsonify({"success": False, "error": err}), 400

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

    # 3) optional If-Match(mutation_version) 파싱 — 형식 오류는 삼키지 않고 400.
    if_match_raw = (request.headers.get("If-Match") or "").strip().strip('"')
    expected_versions: Optional[Mapping[int, int]] = None
    if if_match_raw:
        try:
            expected_versions = {order_id: int(if_match_raw)}
        except ValueError:
            return jsonify({"success": False, "error": "If-Match 형식이 올바르지 않습니다."}), 400
    idempotency_key = (request.headers.get("Idempotency-Key") or "").strip() or None

    user_id = session.get("user_id")
    by_name = _resolve_by_name(db, user_id)
    scope_hash, request_hash = _mutation_hashes(order_id, result, memo, measurement_date)
    captured: dict = {}

    def _mutate(sess: Session, orders: List[Order]) -> Mapping[int, List[str]]:
        """row lock 아래에서 sd['calls'] append + OrderEvent parity(축 불변)."""
        o = orders[0]
        sd = copy.deepcopy(o.structured_data) if isinstance(o.structured_data, dict) else {}
        last_call = _append_call(sd, result, memo, user_id, by_name)

        old_meas = ((sd.get("schedule") or {}).get("measurement") or {}).get("date")
        if measurement_date:
            schedule = sd.get("schedule") if isinstance(sd.get("schedule"), dict) else {}
            meas = schedule.get("measurement") if isinstance(schedule.get("measurement"), dict) else {}
            meas["date"] = measurement_date
            schedule["measurement"] = meas
            sd["schedule"] = schedule

        o.structured_data = sd
        flag_modified(o, "structured_data")

        sess.add(
            OrderEvent(
                order_id=o.id,
                event_type=CALL_LOGGED_COMMAND,
                payload={"result": result, "memo_len": len(memo), "measurement_date": measurement_date},
                created_by_user_id=user_id,
            )
        )
        if measurement_date and measurement_date != old_meas:
            sess.add(
                OrderEvent(
                    order_id=o.id,
                    event_type="MEASUREMENT_DATE_CHANGED",
                    payload={"from": old_meas, "to": measurement_date},
                    created_by_user_id=user_id,
                )
            )

        captured["call"] = last_call
        captured["calls_count"] = len(sd["calls"])
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    # 4) REV-00 one-tx: If-Match + FOR UPDATE + version bump + idempotency + receipt.
    try:
        outcome = execute_order_mutation(
            db,
            actor_user_id=user_id,
            policy_id=CALL_LOG_POLICY_ID,
            order_ids=[order_id],
            expected_versions=expected_versions,
            idempotency_key=idempotency_key,
            scope_hash=scope_hash,
            request_hash=request_hash,
            mutation=_mutate,
        )
        db.commit()
    except RevisionError as rev:
        db.rollback()
        return jsonify({"success": False, "error": str(rev), "code": rev.error_code}), rev.status_code
    except Exception as exc:  # noqa: BLE001 - 상위에서 롤백 후 500 반환
        db.rollback()
        logger.exception("[ORDERS] call-log 오류: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500

    # 실측일/스케줄 변경이 대시보드 슬라이스에 반영되도록 캐시 무효화(payment-confirm 준용).
    try:
        from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches

        invalidate_all_dashboard_slice_caches()
    except Exception as cache_exc:  # noqa: BLE001 - 캐시 무효화 실패는 로깅만
        logger.warning("[ORDERS] call-log 캐시 무효화 실패: %s", cache_exc, exc_info=True)

    if outcome.replayed:  # same-key replay: 저장된 write 를 그대로 반영해 응답 재구성.
        fresh = db.query(Order).filter(Order.id == order_id).first()
        calls = (fresh.structured_data or {}).get("calls") or []
        data = {"call": calls[-1] if calls else None, "calls_count": len(calls)}
    else:
        data = {"call": captured["call"], "calls_count": captured["calls_count"]}
    data["mutation_receipt"] = outcome.read_receipt_id

    resp = jsonify({"success": True, "data": data})
    for header, value in outcome.headers.items():
        resp.headers[header] = value
    return resp


__all__ = ["CALL_RESULTS", "CALL_LOGGED_COMMAND", "CALL_LOG_POLICY_ID", "log_call_response"]

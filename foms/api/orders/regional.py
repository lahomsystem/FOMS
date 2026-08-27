"""지방/자가실측 체크리스트·메모 mutation handlers (DATA-MEASUREMENT-01).

P1-22 remediation: 예전엔 6종 체크리스트 불리언과 자유 메모를 로그인 사용자면 누구나
``setattr(order, field, value)`` + ``db.commit()`` 으로 **generic·direct** 저장했다(타입
검증 0·version/receipt/event 0). 이 모듈은 그것을 세 축으로 정본화한다.

* **typed field registry**: 체크리스트는 정확히 6개 불리언 필드만(``REGIONAL_ALLOWED_FIELDS``),
  값은 불리언으로 강제(임의 필드/타입 거부). 메모는 문자열만.
* **policy**: §2.1 canonical ``STAFF_MUTATION`` 을 handler 에서 enforce(VIEWER deny) —
  AUTH-01 before_request 가드가 꺼진 컨텍스트(TESTING)에서도 항상.
* **revision**: 저장은 REV-00 :func:`execute_order_mutation` 경유 — If-Match(mutation_version)
  낙관 잠금·``FOR UPDATE``·version bump·idempotency receipt·OrderEvent parity 를 한 tx 에.
* **ledger** (AUDIT-GAP-01): 이 경로가 지방 체크리스트 6종의 **실사용 정본 쓰기 경로**라,
  변경은 ``order_field_changes`` 원장에도 실린다. 경로(``path``)는 평면 컬럼명 그대로이고
  (점 경로 아님), 감사 헤더 ``security_logs.detail['change_set']`` 과 같은 id 로 묶인다.

**unrelated-path invariant**: 지정된 flat 컬럼 하나(또는 regional_memo)만 바꾸고 나머지
structured_data/컬럼은 건드리지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any, List, Mapping, Optional, Tuple

from flask import jsonify, request, session
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from db import get_db
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.orders.order_field_change_writer import ledger_text, record_field_changes
from foms.services.orders.structured_diff import CONTENT_MODIFIED_MARK
from foms.services.orders.revision import RevisionError, execute_order_mutation
from foms.web.auth import get_user_by_id, log_access
from foms.services.audit_message_display import describe_field_change
from foms.services.orders.audit_order_context import order_audit_context
from models import Order, OrderEvent

REGIONAL_ALLOWED_FIELDS = [
    "measurement_completed",
    "regional_sales_order_upload",
    "regional_blueprint_sent",
    "regional_order_upload",
    "regional_cargo_sent",
    "regional_construction_info_sent",
]
_REGIONAL_ALLOWED = frozenset(REGIONAL_ALLOWED_FIELDS)

#: 체크리스트/메모 write 정책 — 전 STAFF 팀 업무, VIEWER deny(§2.1 STAFF_MUTATION).
REGIONAL_POLICY_ID = "STAFF_MUTATION"
REGIONAL_CHECKLIST_EVENT = "REGIONAL_CHECKLIST_UPDATED"
REGIONAL_MEMO_EVENT = "REGIONAL_MEMO_UPDATED"
_MEMO_MAX = 2000


#: 감사 detail 에 남길 메모 발췌 상한. 원장은 본문 저장소가 아니다 — 무엇이 바뀌었는지
#: 알아볼 만큼만 남기고, 전문은 주문 화면이 정본이다.
_MEMO_AUDIT_MAX = 200


def _coerce_checklist_bool(value: Any) -> bool:
    """체크리스트 값을 불리언으로 강제한다(임의 타입 거부).

    Args:
        value: 요청 값(bool/숫자/문자 토큰만 허용).

    Returns:
        정규화된 불리언.

    Raises:
        ValueError: dict/list/None 등 불리언으로 해석할 수 없는 타입.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    raise ValueError("체크리스트 값은 불리언이어야 합니다.")


def _authorize() -> Optional[Any]:
    """STAFF_MUTATION 정책을 enforce. 거부면 (json, status), 허용이면 None."""
    user = get_user_by_id(session.get("user_id"))
    decision = evaluate_policy(POLICY_REGISTRY[REGIONAL_POLICY_ID], user)
    if not decision.allowed:
        return (
            jsonify({
                "success": False,
                "data": None,
                "error": decision.reason,
                "message": decision.reason,
                "code": decision.code,
            }),
            decision.status,
        )
    return None


def _parse_if_match(order_id: int) -> Tuple[Optional[Mapping[int, int]], Optional[Any]]:
    """optional If-Match(mutation_version) → expected_versions. 형식 오류는 (None, err)."""
    raw = (request.headers.get("If-Match") or "").strip().strip('"')
    if not raw:
        return None, None
    try:
        return {order_id: int(raw)}, None
    except ValueError:
        return None, (jsonify({"success": False, "message": "If-Match 형식이 올바르지 않습니다."}), 400)


def _hashes(order_id: int, payload: dict) -> Tuple[str, str]:
    """(scope_hash, request_hash) — receipt·same-key 감지용 sha256."""
    scope = hashlib.sha256(f"{REGIONAL_POLICY_ID}:{order_id}".encode()).hexdigest()
    req = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()
    return scope, req


def _order_or_404(db: Session, order_id: Any) -> Tuple[Optional[Order], Optional[Any]]:
    """지방/자가실측 주문만 허용. (order, None) 또는 (None, 404 응답)."""
    order = db.query(Order).filter_by(id=order_id).first()
    is_regional = getattr(order, "is_regional", False)
    is_self = getattr(order, "is_self_measurement", False)
    if not order or (not is_regional and not is_self):
        return None, (jsonify({"success": False, "message": "유효하지 않은 주문입니다."}), 404)
    return order, None


def _order_type_label(order: Order) -> str:
    return "자가실측" if getattr(order, "is_self_measurement", False) else "지방 주문"


def update_regional_status_response():
    """6종 체크리스트 불리언 1개를 typed·REV-00 로 저장한다."""
    err = _authorize()
    if err:
        return err
    db = get_db()
    data = request.get_json() or {}
    order_id = data.get("order_id")
    field = data.get("field")
    raw_value = data.get("value")

    if field not in _REGIONAL_ALLOWED:
        return jsonify({"success": False, "message": "허용되지 않은 필드입니다."}), 400
    try:
        value = _coerce_checklist_bool(raw_value)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    order, resp = _order_or_404(db, order_id)
    if resp:
        return resp
    order_id = order.id

    expected_versions, if_match_err = _parse_if_match(order_id)
    if if_match_err:
        return if_match_err
    idempotency_key = (request.headers.get("Idempotency-Key") or "").strip() or None
    user_id = session.get("user_id")
    scope_hash, request_hash = _hashes(order_id, {"field": field, "value": value})

    previous_value = getattr(order, field, None)
    # AUDIT-GAP-01: 감사 헤더(security_logs)와 원장 항목을 잇는 열쇠. 아래 log_access 의
    # ``detail['change_set']`` 과 **같은 값**이어야 관리자 감사 화면이 조인할 수 있다.
    change_set_id = str(uuid.uuid4())

    def _mutate(sess: Session, orders: List[Order]) -> Mapping[int, List[str]]:
        """row lock 아래에서 단일 체크리스트 컬럼만 설정 + event parity(축 불변) + 원장."""
        o = orders[0]
        # AUDIT-GAP-01: 원장 비교 기준은 아래 setattr **전에** 떠야 한다. 컬럼이 NULL 인
        # 낡은 행이 있어 불리언으로 정규화한다 — NULL 은 '체크 안 됨'이지 별개 값이 아니다
        # (NULL→False 저장이 변경으로 남으면 진짜 토글이 묻힌다).
        before_flag = bool(getattr(o, field, None))
        setattr(o, field, value)
        sess.add(OrderEvent(
            order_id=o.id,
            event_type=REGIONAL_CHECKLIST_EVENT,
            payload={"field": field, "value": value},
            created_by_user_id=user_id,
        ))
        # AUDIT-GAP-01: 원장 쓰기를 **``_mutate`` 안**에 두는 이유 — 컬럼 write 와 운명을
        # 같이해야 하기 때문이다. ``execute_order_mutation`` 반환 뒤(바깥)에 두면 두 경로가
        # 어긋난다: ① 같은 Idempotency-Key replay 는 ``mutation`` 을 아예 실행하지 않고
        # 저장된 응답을 반환하고(revision.py `_lookup_receipt` → `_replay`), ② receipt
        # insert 의 IntegrityError backstop 은 ``session.rollback()`` 뒤 replay 를 반환한다.
        # 두 경우 모두 컬럼은 그대로인데 바깥 쓰기만 살아남아 **유령 행**이 된다. 안에서 쓰면
        # FOR UPDATE 락 안·같은 tx 라 replay 는 애초에 도달하지 않고 rollback 은 함께 지운다.
        if before_flag != value:
            # 무변경 저장(같은 값 재클릭·중복 요청)은 행을 만들지 않는다.
            record_field_changes(
                sess,
                # path 는 점 없는 평면 컬럼명 그대로(ORDER-FLAG-01 확정 규약).
                [{"path": field, "before": before_flag, "after": value, "op": "set"}],
                order_id=o.id,
                actor_user_id=user_id,
                change_set_id=change_set_id,
            )
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    try:
        outcome = execute_order_mutation(
            db,
            actor_user_id=user_id,
            policy_id=REGIONAL_POLICY_ID,
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
        return jsonify({"success": False, "message": str(rev), "code": rev.error_code}), rev.status_code
    except Exception as exc:  # noqa: BLE001 - 롤백 후 500
        db.rollback()
        logger.exception("[REGIONAL] 체크리스트 업데이트 오류 order=%s field=%s", order_id, field)
        return jsonify({"success": False, "message": f"오류 발생: {str(exc)}"}), 500

    audit_context = order_audit_context(order)
    log_access(
        describe_field_change(
            order_id=order_id, field=field, before=previous_value, after=value,
            has_before=True, **audit_context,
        ),
        session["user_id"],
        action="ORDER_CHECKLIST_UPDATED", target_type="order", target_id=order_id,
        detail={"field": field, "before": previous_value, "after": value,
                "change_set": change_set_id, **audit_context},
    )
    resp = jsonify({
        "success": True,
        "message": "상태가 업데이트되었습니다.",
        "mutation_receipt": outcome.read_receipt_id,
    })
    for header, hvalue in outcome.headers.items():
        resp.headers[header] = hvalue
    return resp


def update_regional_memo_response():
    """자유 메모(문자열)를 typed·REV-00 로 저장한다."""
    err = _authorize()
    if err:
        return err
    db = get_db()
    data = request.get_json() or {}
    order_id = data.get("order_id")
    memo = data.get("memo", "")
    if not isinstance(memo, str):
        return jsonify({"success": False, "message": "메모는 문자열이어야 합니다."}), 400
    memo = memo[:_MEMO_MAX]

    order, resp = _order_or_404(db, order_id)
    if resp:
        return resp
    order_id = order.id

    previous_memo = getattr(order, "regional_memo", None) or ""
    if previous_memo == memo:
        # 무변경 저장은 쓰지 않는다. 대시보드 자동저장이 **디바운스(1초)와 blur 즉시저장으로
        # 두 번** 발사해(운영 실측: 09:34:35·09:34:36 동일 메모 2건) 감사 원장이 같은 내용으로
        # 겹쳐 쌓였다. 버전 bump·이벤트·감사 기록을 모두 건너뛴다(멱등 no-op).
        return jsonify({
            "success": True,
            "message": "메모가 저장되었습니다.",
            "unchanged": True,
        })

    expected_versions, if_match_err = _parse_if_match(order_id)
    if if_match_err:
        return if_match_err
    idempotency_key = (request.headers.get("Idempotency-Key") or "").strip() or None
    user_id = session.get("user_id")
    scope_hash, request_hash = _hashes(order_id, {"memo_len": len(memo)})
    # AUDIT-GAP-01: 감사 헤더 ``detail['change_set']`` 과 원장 행을 잇는 열쇠(위와 같은 규약).
    change_set_id = str(uuid.uuid4())

    def _mutate(sess: Session, orders: List[Order]) -> Mapping[int, List[str]]:
        """row lock 아래에서 regional_memo 컬럼만 설정 + event parity(축 불변) + 원장."""
        o = orders[0]
        # AUDIT-GAP-01: 비교 기준은 대입 전 값이고, **판정은 절단 전 원문으로** 한다.
        # 원장 표현(120자 절단)으로 판정하면 121자 이후만 고친 변경이 통째로 사라진다 —
        # 메모는 상한이 2000자라 흔한 길이이고, 잔금 조건·열쇠 보관처처럼 분쟁 소재가
        # 뒤쪽에 적힌다. 절단 때문에 표시값이 같아 보이는 행은 지우는 게 아니라
        # 표식을 붙여 구분한다(``structured_diff`` 의 site_extra 선례와 같은 규약).
        memo_before_raw = (getattr(o, "regional_memo", None) or "").strip()
        memo_before = ledger_text(getattr(o, "regional_memo", None), "regional_memo")
        o.regional_memo = memo
        sess.add(OrderEvent(
            order_id=o.id,
            event_type=REGIONAL_MEMO_EVENT,
            payload={"memo_len": len(memo)},
            created_by_user_id=user_id,
        ))
        # 위치 근거는 체크리스트 경로의 주석과 같다(replay·rollback 시 유령 행 방지).
        memo_after_raw = (memo or "").strip()
        memo_after = ledger_text(memo, "regional_memo")
        if memo_before_raw != memo_after_raw:
            if memo_after == memo_before:
                # 절단 충돌: 원문은 달라졌는데 표시값이 같다. 그대로 두면 원장이
                # ``A → A`` 로 거짓말을 한다.
                memo_after = f"{memo_after} {CONTENT_MODIFIED_MARK}" if memo_after else CONTENT_MODIFIED_MARK
            record_field_changes(
                sess,
                [{
                    "path": "regional_memo",
                    "before": memo_before,
                    "after": memo_after,
                    "op": ("add" if memo_before is None
                           else ("clear" if memo_after is None else "set")),
                }],
                order_id=o.id,
                actor_user_id=user_id,
                change_set_id=change_set_id,
            )
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    try:
        outcome = execute_order_mutation(
            db,
            actor_user_id=user_id,
            policy_id=REGIONAL_POLICY_ID,
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
        return jsonify({"success": False, "message": str(rev), "code": rev.error_code}), rev.status_code
    except Exception as exc:  # noqa: BLE001 - 롤백 후 500
        db.rollback()
        logger.exception("[REGIONAL] 메모 업데이트 오류 order=%s", order_id)
        return jsonify({"success": False, "message": f"오류 발생: {str(exc)}"}), 500

    memo_context = order_audit_context(order)
    log_access(
        describe_field_change(
            order_id=order_id, field="regional_memo", before=previous_memo, after=memo,
            has_before=True, **memo_context,
        ),
        session["user_id"],
        action="ORDER_MEMO_UPDATED", target_type="order", target_id=order_id,
        detail={
            "field": "regional_memo",
            # 원문 전량은 담지 않는다 — 메모는 길이 제한만 있는 자유 텍스트라
            # 감사 원장이 본문 저장소가 되면 안 된다(요약으로 무엇이 바뀌었는지만 남긴다).
            "before": previous_memo[:_MEMO_AUDIT_MAX],
            "after": memo[:_MEMO_AUDIT_MAX],
            "before_len": len(previous_memo),
            "after_len": len(memo),
            "change_set": change_set_id,
            **memo_context,
        },
    )
    resp = jsonify({
        "success": True,
        "message": "메모가 저장되었습니다.",
        "mutation_receipt": outcome.read_receipt_id,
    })
    for header, hvalue in outcome.headers.items():
        resp.headers[header] = hvalue
    return resp


__all__ = [
    "REGIONAL_ALLOWED_FIELDS",
    "REGIONAL_POLICY_ID",
    "update_regional_memo_response",
    "update_regional_status_response",
]

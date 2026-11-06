"""정산 차감 넣기 · 취소 쓰기(설계서 FCOMM-01 §10.2~10.5 · 검수 원장 A12 · A17).

차감은 ``structured_data.settlement.deductions[]`` 한 곳에만 쌓는다(D13). 두 쓰기 모두 주문 저장의
표준 길(:func:`foms.services.orders.revision.execute_order_mutation`)을 탄다 — 첫 조회부터 행을
``FOR UPDATE`` 로 잠그고(:func:`lock_order_row`), 잠근 뒤 다시 읽은 structured_data 를 깊은 복사해 고친
다음 다시 대입 · ``flag_modified`` 하고, 엔진이 ``mutation_version`` 을 1 올린다. 예전 넣기 길은 잠금 없이
읽은 dict 를 통째로 되써서 겹친 저장(다른 차감 · CS 의 주문 저장)이 사라졌다(A12).

If-Match 는 보내면 확인하고, 안 보내면 요구하지 않는다(완료 화면 · 정산 실무 탭 · 태블릿 시트가 지금 안 보낸다).

차감은 지우지 않는다. 취소는 ``voided_at`` · ``voided_by`` · ``voided_by_name`` · ``void_reason`` 을 붙이고,
읽는 곳은 모두 :mod:`foms.services.settlement_deductions` 의 유효 판정으로 거른다. 커밋은 부르는 쪽.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
from typing import Any, Mapping, Optional

from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_kst
from foms.services.erp_display import _ensure_dict
from foms.services.erp_policy import ORDER_SETTLEMENT_ALERT_TARGET_STATUSES
from foms.services.orders.revision import execute_order_mutation, lock_order_row
from foms.services.sales_commission.calc import COMPLETED_STAGES
from foms.services.settlement_deductions import settlement_valid_deductions
from models import Order, OrderEvent, SecurityLog, User

#: 비용 청구 귀속 대상(계획서 2026-03-02 §3.1). ``foms.api.cs.dashboard`` 가 같은 이름으로 다시 내보낸다.
SETTLEMENT_DEPARTMENTS = ("SALES", "DRAWING", "PRODUCTION", "CONSTRUCTION", "CUSTOMER")
#: 넣기 · 취소의 REV-00 receipt 정책 id(라우트 manifest 와 같은 이름).
ISSUE_POLICY_ID = "FINANCE_MUTATION"
VOID_POLICY_ID = "SALES_COMMISSION_WRITE"
VOID_EVENT_TYPE = "SETTLEMENT_DEDUCTION_VOIDED"
VOID_REASON_MAX = 500
_SALES = "SALES"


class DeductionError(Exception):
    """화면에 그대로 보일 수 있는 거부 이유. ``status`` 는 HTTP 코드."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


# --------------------------------------------------------------------------
# 공통
# --------------------------------------------------------------------------
def deduction_allowed_for_order(order: Any) -> bool:
    """차감을 넣을 수 있는 주문인지 — 완료·AS 글자(예전 규칙) 또는 메인 단계 CS · COMPLETED(J1).

    공용 상수 ``TARGET_STATUSES`` 는 정산 모집단 여러 곳이 같이 쓰므로 넓히지 않고 여기서만 더한다(§10.4).
    """
    if getattr(order, "status", None) in ORDER_SETTLEMENT_ALERT_TARGET_STATUSES:
        return True
    return str(getattr(order, "erp_stage_code", None) or "").strip().upper() in COMPLETED_STAGES


def _lock_active_order(db, order_id: int) -> Optional[Order]:
    """첫 조회부터 행 잠금 → 지워졌거나 초안이면 None(잠금은 트랜잭션 끝까지 남는다)."""
    order = lock_order_row(db, order_id)
    if order is None:
        return None
    active = db.query(Order.id).filter(Order.id == order_id, Order.active_filter()).first()
    return order if active is not None else None


def _expected_versions(order_id: int, if_match: Any) -> Optional[dict[int, int]]:
    """If-Match 가 숫자면 그 버전을 요구하고, 비었거나 숫자가 아니면 요구하지 않는다."""
    text = str(if_match or "").strip().strip('"')
    return {order_id: int(text)} if text.isdigit() else None


def _hashes(policy_id: str, order_id: int, payload: Mapping[str, Any]) -> tuple[str, str]:
    scope = hashlib.sha256(f"{policy_id}:{order_id}".encode("utf-8")).hexdigest()
    body = json.dumps(dict(payload), sort_keys=True, ensure_ascii=False, default=str)
    return scope, hashlib.sha256(body.encode("utf-8")).hexdigest()


def _settlement_of(sd: dict) -> dict:
    settlement = sd.get("settlement")
    if not isinstance(settlement, dict):
        settlement = {"status": "PENDING", "base_cost": None, "deductions": [], "final_cost": None}
    if not isinstance(settlement.get("deductions"), list):
        settlement["deductions"] = []
    return settlement


def _refresh_totals(settlement: dict) -> None:
    """상태 · 최종 비용을 유효한 차감만으로 다시 맞춘다(취소한 차감은 빠진다)."""
    valid = settlement_valid_deductions(settlement)
    settlement["status"] = "ISSUE_RAISED" if valid else "PENDING"
    base = settlement.get("base_cost")
    if isinstance(base, (int, float)) and not isinstance(base, bool):
        settlement["final_cost"] = base + sum(
            d["amount"] for d in valid if isinstance(d.get("amount"), (int, float)))


def _write_structured(order: Order, sd: dict) -> None:
    order.structured_data = sd
    flag_modified(order, "structured_data")


def _resulting_version(outcome: Any, order_id: int) -> Optional[int]:
    for res in (outcome.body or {}).get("resources") or []:
        if res.get("order_id") == order_id:
            return res.get("resulting_version")
    return None


# --------------------------------------------------------------------------
# 넣기
# --------------------------------------------------------------------------
def _clean_issue_fields(db, data: Mapping[str, Any]) -> dict[str, Any]:
    """요청 본문 검사 → ``{department, amount(음수), reason, charge_to_user_id, charge_to_name}``."""
    department = str(data.get("department") or "").strip().upper()
    if department not in SETTLEMENT_DEPARTMENTS:
        raise DeductionError("귀속 대상이 올바르지 않습니다. (SALES, DRAWING, PRODUCTION, CONSTRUCTION, CUSTOMER)")
    raw_amount = data.get("amount")
    if raw_amount is None:
        raise DeductionError("청구 금액을 입력해주세요.")
    try:
        amount = int(raw_amount)
    except (TypeError, ValueError):
        raise DeductionError("청구 금액을 숫자로 입력해주세요.") from None
    amount = -abs(amount)
    reason = str(data.get("reason") or "").strip()
    if not reason:
        raise DeductionError("사유를 입력해주세요.")

    charge_to_user_id, charge_to_name = None, None
    raw_charge = data.get("charge_to_user_id")
    if raw_charge not in (None, "") and department != "CUSTOMER":
        try:
            uid = int(raw_charge)
        except (TypeError, ValueError):
            raise DeductionError("귀속 인원이 올바르지 않습니다.") from None
        charge_user = db.query(User).filter(User.id == uid, User.is_active.is_(True)).first()
        if charge_user is None:
            raise DeductionError("해당 귀속 인원을 찾을 수 없거나 비활성입니다.")
        if (charge_user.team or "").strip().upper() != department:
            raise DeductionError("선택한 인원이 해당 부서 소속이 아닙니다.")
        charge_to_user_id = uid
        charge_to_name = str(charge_user.name) if charge_user.name is not None else None
    if department == _SALES and charge_to_user_id is None:
        raise DeductionError("영업 귀속 차감은 사람을 골라야 해요.")
    return {"department": department, "amount": amount, "reason": reason,
            "charge_to_user_id": charge_to_user_id, "charge_to_name": charge_to_name}


def _new_deduction_id(order_id: int, existing: list) -> str:
    """``DED-<주문>-<밀리초>``. 같은 밀리초에 이미 있으면 1씩 올린다(잠금 아래라 연달아 와도 안 겹친다)."""
    taken = {str(d.get("id")) for d in existing if isinstance(d, dict)}
    stamp = int(datetime.datetime.now().timestamp() * 1000)
    while f"DED-{order_id}-{stamp}" in taken:
        stamp += 1
    return f"DED-{order_id}-{stamp}"


def issue_deduction(db, *, order_id: int, actor: Any, data: Mapping[str, Any],
                    if_match: Any = None) -> dict[str, Any]:
    """차감 한 건을 넣는다 → ``{deduction, settlement, mutation_version}``. 커밋은 부르는 쪽.

    Raises:
        DeductionError: 403(시공팀) · 404(주문 없음) · 400(단계 · 입력).
        RevisionError: If-Match 불일치(409) 등 엔진 거부.
    """
    if actor is not None and getattr(actor, "team", None) == "CONSTRUCTION":
        raise DeductionError("시공팀은 비용 청구를 등록할 수 없습니다.", 403)
    order = _lock_active_order(db, order_id)
    if order is None:
        raise DeductionError("주문을 찾을 수 없습니다.", 404)
    if not deduction_allowed_for_order(order):
        raise DeductionError("완료·AS 건에만 비용 청구를 등록할 수 있습니다.")
    fields = _clean_issue_fields(db, data)
    actor_id = getattr(actor, "id", None)
    created_by = actor.name if actor is not None else "Unknown"
    captured: dict[str, Any] = {}

    def _mutate(sess, locked):
        target = locked[0]
        sd = copy.deepcopy(_ensure_dict(target.structured_data))
        settlement = _settlement_of(sd)
        item = {"id": _new_deduction_id(order_id, settlement["deductions"]),
                "department": fields["department"], "amount": fields["amount"], "reason": fields["reason"],
                "created_at": datetime.datetime.now().isoformat(), "created_by": created_by}
        for key in ("charge_to_user_id", "charge_to_name"):
            if fields[key] is not None:
                item[key] = fields[key]
        settlement["deductions"].append(item)
        _refresh_totals(settlement)
        sd["settlement"] = settlement
        _write_structured(target, sd)
        payload = {k: item[k] for k in ("department", "amount", "reason", "created_by")}
        payload["deduction_id"] = item["id"]
        payload.update({k: item[k] for k in ("charge_to_user_id", "charge_to_name") if k in item})
        sess.add(OrderEvent(order_id=order_id, event_type="SETTLEMENT_ISSUE_RAISED",
                            payload=payload, created_by_user_id=actor_id))
        captured.update(deduction=copy.deepcopy(item), settlement=copy.deepcopy(settlement))
        return {target.id: [f"ORDER_DETAIL:{target.id}", "ORDERS_INDEX"]}

    scope_hash, request_hash = _hashes(ISSUE_POLICY_ID, order_id, fields)
    outcome = execute_order_mutation(
        db, actor_user_id=actor_id, policy_id=ISSUE_POLICY_ID, order_ids=[order_id],
        expected_versions=_expected_versions(order_id, if_match),
        scope_hash=scope_hash, request_hash=request_hash, mutation=_mutate,
    )
    item = captured["deduction"]
    log_msg = f"주문 #{order_id} 비용 청구: {item['department']}"
    if item.get("charge_to_name"):
        log_msg += f" {item['charge_to_name']}({item['charge_to_user_id']})"
    log_msg += f" {item['amount']}원 - {item['reason'][:50]}"
    db.add(SecurityLog(user_id=actor_id, message=log_msg))
    return {"deduction": item, "settlement": captured["settlement"],
            "mutation_version": _resulting_version(outcome, order_id)}


# --------------------------------------------------------------------------
# 취소
# --------------------------------------------------------------------------
def _clean_void_reason(reason: Any) -> str:
    text = reason.strip() if isinstance(reason, str) else ""
    if not text:
        raise DeductionError("취소 사유를 적어 주세요.")
    if len(text) > VOID_REASON_MAX:
        raise DeductionError(f"취소 사유는 {VOID_REASON_MAX}자까지 적을 수 있어요.")
    return text


def _pick_for_void(settlement: Any, deduction_id: str) -> dict:
    """취소할 차감 — 같은 id 중 아직 유효한 첫 건. 없으면 404, 모두 취소됐으면 409."""
    entries = settlement.get("deductions") if isinstance(settlement, dict) else None
    matches = [d for d in entries or [] if isinstance(d, dict) and str(d.get("id")) == deduction_id]
    if not matches:
        raise DeductionError("차감 기록을 찾을 수 없어요.", 404)
    for entry in matches:
        if not entry.get("voided_at"):
            return entry
    raise DeductionError("이미 취소한 차감이에요.", 409)


def void_deduction(db, *, order_id: int, deduction_id: str, actor: Any, reason: Any,
                   if_match: Any = None) -> dict[str, Any]:
    """차감 한 건에 취소 표시를 붙인다(지우지 않는다) → ``{deduction, settlement, mutation_version}``.

    Raises:
        DeductionError: 400(사유) · 404(주문 · 차감 없음) · 409(이미 취소).
        RevisionError: If-Match 불일치(409) 등 엔진 거부.
    """
    reason_text = _clean_void_reason(reason)
    deduction_id = str(deduction_id or "").strip()
    order = _lock_active_order(db, order_id)
    if order is None:
        raise DeductionError("주문을 찾을 수 없습니다.", 404)
    _pick_for_void(_ensure_dict(order.structured_data).get("settlement"), deduction_id)
    actor_id = getattr(actor, "id", None)
    actor_name = str(actor.name) if actor is not None and actor.name is not None else "Unknown"
    captured: dict[str, Any] = {}

    def _mutate(sess, locked):
        target = locked[0]
        sd = copy.deepcopy(_ensure_dict(target.structured_data))
        settlement = _settlement_of(sd)
        entry = _pick_for_void(settlement, deduction_id)
        entry.update(voided_at=now_kst().isoformat(), voided_by=actor_id,
                     voided_by_name=actor_name, void_reason=reason_text)
        _refresh_totals(settlement)
        sd["settlement"] = settlement
        _write_structured(target, sd)
        payload = {"deduction_id": deduction_id, "amount": entry.get("amount"),
                   "department": entry.get("department"), "reason": reason_text}
        if entry.get("charge_to_user_id") is not None:
            payload["charge_to_user_id"] = entry.get("charge_to_user_id")
        sess.add(OrderEvent(order_id=order_id, event_type=VOID_EVENT_TYPE,
                            payload=payload, created_by_user_id=actor_id))
        captured.update(deduction=copy.deepcopy(entry), settlement=copy.deepcopy(settlement))
        return {target.id: [f"ORDER_DETAIL:{target.id}", "ORDERS_INDEX"]}

    scope_hash, request_hash = _hashes(VOID_POLICY_ID, order_id,
                                       {"deduction_id": deduction_id, "reason": reason_text})
    outcome = execute_order_mutation(
        db, actor_user_id=actor_id, policy_id=VOID_POLICY_ID, order_ids=[order_id],
        expected_versions=_expected_versions(order_id, if_match),
        scope_hash=scope_hash, request_hash=request_hash, mutation=_mutate,
    )
    entry = captured["deduction"]
    log_msg = f"주문 #{order_id} 차감 취소: {entry.get('department')}"
    if entry.get("charge_to_name"):
        log_msg += f" {entry['charge_to_name']}({entry.get('charge_to_user_id')})"
    log_msg += f" {entry.get('amount')}원 - {reason_text[:50]}"
    db.add(SecurityLog(user_id=actor_id, message=log_msg))
    return {"deduction": entry, "settlement": captured["settlement"],
            "mutation_version": _resulting_version(outcome, order_id)}


__all__ = [
    "DeductionError",
    "ISSUE_POLICY_ID",
    "SETTLEMENT_DEPARTMENTS",
    "VOID_EVENT_TYPE",
    "VOID_POLICY_ID",
    "deduction_allowed_for_order",
    "issue_deduction",
    "void_deduction",
]

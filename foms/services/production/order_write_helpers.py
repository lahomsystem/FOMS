"""생산 주문 쓰기 API 공통 조각 — 영수증 열쇠 · 보류 게이트 · 승인 게이트 · 검수까지 게이트 · 관리자 뚫기 · 회차 · 이벤트 보강.

``foms/api/production/orders.py`` 에 있던 함수를 이름 · 뜻 그대로 옮겼다(설계서 2026-11-23 §4-14 — 제작 완료 본문을
``complete_order`` 서비스로 옮기면서 그 본문이 쓰는 조각을 API 밖으로). 옛 API 모듈은 같은 이름으로 다시 내보낸다(제작 시작 ·
재제작 · 제작 취소 · 완료 취소 · 공정 · 보류가 같이 쓴다). 글 · 응답 꼴은 한 글자도 안 바꿨다.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from flask import jsonify
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.erp_policy_quests import check_quest_approvals_complete
from foms.services.orders.order_transition_service import StageConflictError
from foms.services.production.part_progress import complete_block_body
from models import OrderEvent, OrderMutationReceipt, ProductionRun

#: 보류 이력(hold_history) 캡 — 완료 후에도 보존되는 해제된 보류 기록(최근 20건 유지).
PRODUCTION_HOLD_HISTORY_CAP = 20


def _append_hold_history(production: dict[str, Any], released_by: str | None) -> None:
    """보류 해제 직전, active hold 를 hold_history 에 보존한다(완료 후 이력 소실 방지).

    보류 해제 2경로(hold API 직접 해제 · 전이 게이트 release)가 공유한다. 호출 시점의
    ``production['hold']`` 가 active 면 ``{reason, at(보류 시작), released_at(now),
    released_by}`` 를 ``production['hold_history']`` 리스트에 append 하고 최근
    ``PRODUCTION_HOLD_HISTORY_CAP`` 건만 유지한다. active 가 아니면 아무것도 하지
    않는다(빈 해제·중복 append 방지). 호출부가 이 함수 뒤에 hold 를 초기화한다.

    :param production: ``sd['production']`` dict(호출부의 deepcopy 작업 사본 내부 참조).
    :param released_by: 해제자 이름(``user.name`` 또는 None).
    """
    hold = production.get("hold")
    if not (isinstance(hold, dict) and hold.get("active")):
        return
    history = production.get("hold_history")
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "reason": hold.get("reason") or "",
            "at": hold.get("at"),
            "released_at": now_utc_naive().isoformat(),
            "released_by": released_by,
        }
    )
    if len(history) > PRODUCTION_HOLD_HISTORY_CAP:
        history = history[-PRODUCTION_HOLD_HISTORY_CAP:]
    production["hold_history"] = history


def _scope_hash(command_id: str, order_id: int) -> str:
    """전이 scope 의 sha256 hex(receipt 저장용)."""
    return hashlib.sha256(f"{command_id}:{order_id}".encode("utf-8")).hexdigest()


def _request_hash(body: dict[str, Any]) -> str:
    """요청 payload 의 sha256 hex(same-key/different-hash 감지용)."""
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _idempotency_receipt_exists(db: Any, actor_user_id: Any, policy_id: str, idem_key: str | None) -> bool:
    """(actor, policy, key) receipt 존재 여부. 존재하면 이 요청은 replay(전제 게이트 skip).

    same-key transport 재시도는 첫 전이로 stage 가 이미 advance 됐어도 stage 게이트가 아니라
    전이 엔진의 idempotency replay 로 저장된 성공을 돌려줘야 한다(§E2E "same key replay 200").
    """
    if not idem_key or actor_user_id is None:
        return False
    return (
        db.query(OrderMutationReceipt.read_receipt_id)
        .filter(
            OrderMutationReceipt.actor_user_id == actor_user_id,
            OrderMutationReceipt.policy_id == policy_id,
            OrderMutationReceipt.idempotency_key == idem_key,
        )
        .first()
        is not None
    )


def _hold_active(sd: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
    """(hold active 여부, hold dict). production.hold.active 판정."""
    production = sd.get("production")
    hold = production.get("hold") if isinstance(production, dict) else None
    if isinstance(hold, dict):
        return bool(hold.get("active")), hold
    return False, None


def _hold_block_response(sd: dict[str, Any], release_hold: bool):
    """보류 중(active)이고 release_hold 아니면 409 HOLD_ACTIVE 튜플, 아니면 None(read-only)."""
    active, hold = _hold_active(sd)
    if not active or release_hold:
        return None
    message = "보류 중인 주문입니다."
    reason = hold.get("reason")
    if reason:
        message += f" (사유: {reason})"
    return jsonify({"success": False, "code": "HOLD_ACTIVE", "message": message, "hold": hold}), 409


def _stage_quest_block(sd: dict[str, Any], stage_code: str, stage_label: str, *, require_quest: bool = False):
    """현재 stage quest 가 존재하고 미완이면 409 QUEST_INCOMPLETE, 아니면 None.

    quest 자체가 없으면(레거시/backfill 미완) 기본(``require_quest=False``)은 게이트하지 않는다
    (lock-out 방지) — 존재하는 stage quest 의 필수 승인이 완료돼야만 전이한다.
    ``require_quest=True`` 면 quest 없음도 409 로 거부한다(code 는 소비자 호환을 위해
    ``QUEST_INCOMPLETE`` 그대로, 구분은 ``reason: "QUEST_MISSING"``). 이때 missing_teams 는
    정책 템플릿의 필수 팀(CONFIRM 이면 CS·SALES)이다. 화면 승인 버튼(합성 quest)이 quest 를
    만들고 전이까지 하므로 막다른 길이 아니다(2026-09-20 F2).
    """
    quests = sd.get("quests")
    has_stage_quest = isinstance(quests, list) and any(
        isinstance(q, dict) and q.get("stage") in (stage_code, stage_label) for q in quests
    )
    if not has_stage_quest:
        if not require_quest:
            return None
        _complete, missing = check_quest_approvals_complete(sd, stage_code)
        return (
            jsonify({
                "success": False, "code": "QUEST_INCOMPLETE", "reason": "QUEST_MISSING",
                "message": f"{stage_label} 승인이 먼저 필요합니다.", "missing_teams": missing,
            }),
            409,
        )
    for stage in (stage_code, stage_label):
        complete, _missing = check_quest_approvals_complete(sd, stage)
        if complete:
            return None
    _complete, missing = check_quest_approvals_complete(sd, stage_code)
    return (
        jsonify({
            "success": False, "code": "QUEST_INCOMPLETE",
            "message": "필수 승인이 완료되지 않아 전이할 수 없습니다.", "missing_teams": missing,
        }),
        409,
    )


def _steps_incomplete_block(sd: dict[str, Any], marks: list[Any]):
    """검수까지(공정 4칸 · 카드를 쓴 주문은 네 파트 실제 완료) 안 끝났으면 409 STEPS_INCOMPLETE 튜플, 끝났으면 None.

    판정 · 글은 :func:`complete_block_body` 한 곳(작업 시트 단추 · 일반 단계 쓰기와 같은 함수, §4-3).
    """
    body = complete_block_body(sd, marks)
    return None if body is None else (jsonify(body), 409)


def _punch_or_return(blocked, code: str, override, punched: list):
    """업무 게이트 판정을 관리자 강제 진행과 합친다.

    막히지 않았으면 None. 막혔는데 override 가 없으면 거부 응답을 그대로 돌려주고,
    override 가 있으면 건너뛴 게이트 코드를 ``punched`` 에 적고 None 을 돌려준다.
    """
    if blocked is None:
        return None
    if override is None:
        return blocked
    punched.append(code)
    return None


def _transition_error_response(exc: Exception):
    """전이 엔진/REV helper 예외를 route JSON 오류로 매핑(stage 불일치는 INVALID_STAGE)."""
    code = "INVALID_STAGE" if isinstance(exc, StageConflictError) else getattr(exc, "error_code", "TRANSITION_ERROR")
    status = getattr(exc, "status_code", 409)
    return jsonify({"success": False, "code": code, "message": str(exc)}), status


def _is_rework_completion(sd: dict[str, Any]) -> bool:
    """production.rework.active 판정(완료 시 active 해제하고 재제작 표식을 남기기 위함)."""
    production = sd.get("production") if isinstance(sd.get("production"), dict) else None
    rework = production.get("rework") if isinstance(production, dict) else None
    return bool(isinstance(rework, dict) and rework.get("active"))


def _release_hold_in_sd(sd: dict[str, Any], db: Any, order_id: int, user_id: Any, via: str,
                        released_by: str | None = None) -> None:
    """same-tx 보류 해제 + PRODUCTION_HOLD_TOGGLED 이벤트(전이 후 side-effect).

    초기화 직전 active hold 를 :func:`_append_hold_history` 로 보존한다 — 완료 후에도 해제
    사유가 남아야 한다(전이 게이트 release 경로와 hold API 직접 해제가 공유하는 계약).
    """
    production = sd.get("production")
    if not isinstance(production, dict):
        production = {}
        sd["production"] = production
    _append_hold_history(production, released_by)
    production["hold"] = {"active": False, "reason": "", "at": None, "by_name": None}
    db.add(OrderEvent(
        order_id=order_id, event_type="PRODUCTION_HOLD_TOGGLED",
        payload={"active": False, "reason": "", "via": via,
                 "domain": "PRODUCTION_DOMAIN", "action": "PRODUCTION_HOLD_TOGGLED"},
        created_by_user_id=user_id,
    ))


def _current_production_run(db: Any, order_id: int) -> ProductionRun | None:
    """해당 주문의 current production run(없으면 None). start/cancel 게이트·종결이 공유."""
    return (
        db.query(ProductionRun)
        .filter(ProductionRun.order_id == order_id, ProductionRun.is_current.is_(True))
        .first()
    )


def _close_current_production_run(db: Any, order_id: int) -> None:
    """current IN_PROGRESS run 을 COMPLETED + is_current=False 로 종결(없으면 no-op)."""
    run = _current_production_run(db, order_id)
    if run is None:
        return
    run.status = "COMPLETED"
    run.is_current = False


def _merge_event_payload(db: Any, event_id: Any, extra: dict[str, Any]) -> None:
    """전이가 만든 OrderEvent payload 에 legacy 표시 키를 덧씌운다(없는 event 는 no-op).

    :param db: DB 세션.
    :param event_id: 전이 결과 ``result.event_id`` (replay 면 None).
    :param extra: payload 에 병합할 키(같은 키는 덮어쓴다).
    """
    if not event_id:
        return
    event = db.get(OrderEvent, event_id)
    if event is None:
        return
    payload = dict(event.payload or {})
    payload.update(extra)
    event.payload = payload
    flag_modified(event, "payload")


def _enrich_production_completed_event(db: Any, event_id: Any, is_rework: bool) -> None:
    """전이가 만든 PRODUCTION_COMPLETED 이벤트 payload 에 legacy 표시 키·rework 표식을 보강한다."""
    extra: dict[str, Any] = {
        "domain": "PRODUCTION_DOMAIN", "action": "PRODUCTION_COMPLETED",
        "target": "workflow.stage", "before": "PRODUCTION", "after": "CONSTRUCTION",
        "change_method": "API", "source_screen": "erp_production_dashboard",
        "reason": "제작 완료 (시공 대기)",
    }
    if is_rework:
        extra["rework"] = True
    _merge_event_payload(db, event_id, extra)

"""
ERP 주문 생산(제작) API. (Phase 4-5f)
erp.py에서 분리: production/start, production/complete, production/steps.
"""

import copy
import datetime
import hashlib
import json
import uuid
from foms.services.datetime_kst import now_utc_naive
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, jsonify, request, session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import get_user_by_id, log_access, login_required
from foms.services.audit_message_display import describe_order_action
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.erp_permissions import erp_edit_required  # noqa: F401  # AUTH-01(P0-9): start/complete/rework 는 _production_steps_edit_required 로 전환됐으나 namespace surface 계약이 재노출을 요구해 유지
from db import get_db
from models import Order, OrderEvent, OrderMutationReceipt, ProductionRun
from foms.services.erp_display import _ensure_dict
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.order_transition_service import (
    COMMAND_REGISTRY,
    StageConflictError,
    TransitionCommand,
    TransitionError,
    transition_order,
)
from foms.services.orders.revision import (
    IDEMPOTENCY_REPLAY_WINDOW,
    READ_RECEIPT_TTL,
    RevisionError,
    execute_order_mutation,
)
from foms.services.orders.state_axes import AXIS_MAIN, read_logistics
from foms.services.orders.order_mutation_policy import (
    POLICY_REGISTRY,
    evaluate_policy,
    team_has_capability,
)
from foms.services.orders.erp_policy_quests import check_quest_approvals_complete

erp_orders_production_bp = Blueprint("erp_orders_production", __name__, url_prefix="/api/orders")


# --- 생산 공정 스텝 권한/스키마 (erp_permissions 통합 후보) --------------------------
# 아래 _can_edit_production_steps / _production_steps_edit_required 는
# erp_permissions.erp_construction_edit_required 스타일을 모듈 로컬로 복제한 것이다.
# 생산 공정 스텝 체크는 ADMIN 또는 team∈(CS,SALES,PRODUCTION) 에게 허용한다.
# 안정화되면 erp_permissions.py 의 can_edit_* / *_edit_required 계열로 승격(통합) 검토.
_PRODUCTION_STEPS_EDIT_TEAMS = ("CS", "SALES", "PRODUCTION")

# 생산 공정 기본 5단계(cut/edge/paint/assemble/inspect). 최초 접근 시 서버가 생성한다.
_PRODUCTION_STEP_DEFS: tuple[tuple[str, str], ...] = (
    ("cut", "재단"),
    ("edge", "엣지"),
    ("paint", "도장"),
    ("assemble", "조립"),
    ("inspect", "검수"),
)
_PRODUCTION_STEP_KEYS = frozenset(k for k, _ in _PRODUCTION_STEP_DEFS)

# 생산 불량 보고 사유 화이트리스트(시트 칩과 1:1)과 이력 캡(최근 20건 유지).
_PRODUCTION_DEFECT_REASONS = ("자재 불량", "가공 오류", "파손", "기타")
_PRODUCTION_DEFECTS_CAP = 20

# 보류 이력(hold_history) 캡 — 완료 후에도 보존되는 해제된 보류 기록(최근 20건 유지).
_PRODUCTION_HOLD_HISTORY_CAP = 20


def _can_edit_production_steps(user: Any) -> bool:
    """생산 공정 스텝 편집 가능 여부(ADMIN 또는 CS/SALES/PRODUCTION 팀)."""
    if not user:
        return False
    if user.role == "ADMIN":
        return True
    return team_has_capability(getattr(user, "team", None), _PRODUCTION_STEPS_EDIT_TEAMS)


def _production_steps_edit_required(f: Callable[..., Any]) -> Callable[..., Any]:
    """생산 공정 스텝 write 권한 데코레이터(모듈 로컬; erp_permissions 통합 후보)."""

    @wraps(f)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        user = get_user_by_id(session.get("user_id"))
        if not user:
            return jsonify({"success": False, "error": "로그인이 필요합니다."}), 401
        if _can_edit_production_steps(user):
            return f(*args, **kwargs)
        return (
            jsonify(
                {
                    "success": False,
                    "error": "공정 스텝 수정 권한이 없습니다. (관리자, 라홈팀, 영업팀 또는 생산팀만 가능)",
                }
            ),
            403,
        )

    return wrapped


def _ensure_production_steps(sd: dict[str, Any]) -> list[dict[str, Any]]:
    """sd['production']['steps'] 를 보장한다(없으면 기본 5단계 미체크로 생성) 후 반환.

    :param sd: 수정 대상 structured_data (deepcopy 된 사본이어야 한다).
    :return: 공정 스텝 리스트(sd 내부 참조와 동일 객체).
    """
    production = sd.get("production")
    if not isinstance(production, dict):
        production = {}
        sd["production"] = production
    steps = production.get("steps")
    if not isinstance(steps, list) or not steps:
        steps = [
            {"key": key, "label": label, "done": False, "at": None, "by_name": None}
            for key, label in _PRODUCTION_STEP_DEFS
        ]
        production["steps"] = steps
    return steps


def _append_hold_history(production: dict[str, Any], released_by: str | None) -> None:
    """보류 해제 직전, active hold 를 hold_history 에 보존한다(완료 후 이력 소실 방지).

    보류 해제 2경로(hold API 직접 해제 · 전이 게이트 release)가 공유한다. 호출 시점의
    ``production['hold']`` 가 active 면 ``{reason, at(보류 시작), released_at(now),
    released_by}`` 를 ``production['hold_history']`` 리스트에 append 하고 최근
    ``_PRODUCTION_HOLD_HISTORY_CAP`` 건만 유지한다. active 가 아니면 아무것도 하지
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
    if len(history) > _PRODUCTION_HOLD_HISTORY_CAP:
        history = history[-_PRODUCTION_HOLD_HISTORY_CAP:]
    production["hold_history"] = history


def _apply_production_hold_gate(
    sd: dict[str, Any],
    *,
    release_hold: bool,
    via: str,
    order_id: int,
    user_id: int | None,
    released_by: str | None,
    db: Any,
) -> tuple[Any, int] | None:
    """생산 전이(start/complete/rework) 전 보류 게이트. 세 엔드포인트가 공유한다.

    ``sd['production']['hold']['active']`` 가 truthy 면 주문이 보류 중이다:
      - ``release_hold`` 가 True 가 아니면 409 HOLD_ACTIVE 응답 튜플을 반환한다
        (호출부가 즉시 return — 전이 미진행, sd 불변).
      - ``release_hold`` 가 True 면 같은 sd 안에서 hold 를 해제(active=False, hold API
        해제 형과 동일)하고 ``PRODUCTION_HOLD_TOGGLED``(via) OrderEvent 를 큐잉한 뒤
        None 을 반환한다(전이 진행).
    보류가 없으면(또는 active 아님) 아무것도 하지 않고 None 을 반환한다 —
    ``release_hold`` 가 True 여도 무해하며 정상 전이한다.

    sd 는 호출부의 작업 dict(전이 흐름이 이후 ``copy.deepcopy(sd)`` 로 저장)이며,
    여기서의 hold 갱신은 그 deepcopy 에 포함되어 함께 커밋된다.

    :param sd: 수정 대상 structured_data(전이 흐름의 작업 dict).
    :param release_hold: body ``release_hold`` 플래그(True 여야 해제).
    :param via: 이벤트 payload ``via`` 값("release_on_start"|"release_on_complete"|"release_on_rework").
    :param order_id: 대상 주문 id(OrderEvent 기록용).
    :param user_id: 해제자 user id(OrderEvent created_by).
    :param released_by: 해제자 이름(hold_history 보존용, ``user.name`` 또는 None).
    :param db: DB 세션(OrderEvent add).
    :return: 409 응답 튜플(보류·미해제) 또는 None(전이 진행).
    """
    production = sd.get("production")
    hold = production.get("hold") if isinstance(production, dict) else None
    if not (isinstance(hold, dict) and hold.get("active")):
        return None  # 보류 없음 → 정상 전이.

    if not release_hold:
        message = "보류 중인 주문입니다."
        reason = hold.get("reason")
        if reason:
            message += f" (사유: {reason})"
        return (
            jsonify(
                {"success": False, "code": "HOLD_ACTIVE", "message": message, "hold": hold}
            ),
            409,
        )

    # 해제 후 전이 — 직전 active hold 를 이력에 보존한 뒤(소실 방지) hold 초기화 + 토글 이벤트 기록.
    _append_hold_history(production, released_by)
    production["hold"] = {"active": False, "reason": "", "at": None, "by_name": None}
    db.add(
        OrderEvent(
            order_id=order_id,
            event_type="PRODUCTION_HOLD_TOGGLED",
            payload={
                "active": False,
                "reason": "",
                "via": via,
                "domain": "PRODUCTION_DOMAIN",
                "action": "PRODUCTION_HOLD_TOGGLED",
            },
            created_by_user_id=user_id,
        )
    )
    return None


# --- STATE-PROD-01: 생산 start/complete 전이 배선 ---------------------------------
# 상태 전이(CONFIRM→PRODUCTION→CONSTRUCTION)는 order_transition_service(STATE-CORE-00)
# 엔진을 **단일 경로**로 경유한다: expected-from·actual-before row lock·mutation_version++·
# idempotency receipt·legacy OrderEvent parity·tx내 outbox 를 원자 보장한다. 아래 두 command
# 를 registry 에 additive 로 등록한다(엔진 파일은 import 만 — 무편집). 전이 후 same-tx 로
# history·보류 해제·production run 정합을 반영해 357d8803 드리프트 가드(hold/steps/rework)를
# non-atomic 잔존 없이 흡수한다.
_POLICY_PRODUCTION_START = "STATE_PRODUCTION_START"
_POLICY_PRODUCTION_COMPLETE = "STATE_PRODUCTION_COMPLETE"

# 되돌리기 2종(제작 취소·완료 취소)도 같은 엔진 경유 — 후진 전이라 stage 게이트만 앞세우고
# 보류 게이트는 걸지 않는다(보류는 전진만 막는다). 직접 order.status/workflow.stage 대입을
# 신설하지 않으므로 STATE-GUARD-01 EXTERNAL 잔여가 늘지 않는다.
_POLICY_PRODUCTION_CANCEL = "STATE_PRODUCTION_CANCEL"
_POLICY_PRODUCTION_UNCOMPLETE = "STATE_PRODUCTION_UNCOMPLETE"

# --- STATE-PROD-ACTIONS-01: step/defect(version++ mutation)·ACK(Order 불변 receipt) ---
# 아래는 REV-00 receipt idempotency scope 식별자(free-form string)일 뿐이다. AUTH 게이트는
# order_mutation_policy PRODUCTION_EDIT 를 그대로 재사용하며(이 파일에서 재분류 없음), 여기
# 문자열은 POLICY_REGISTRY 와 무관하다(transition 의 STATE_PRODUCTION_* 와 동일 관례).
_POLICY_PRODUCTION_STEP = "PRODUCTION_STEP_CHECK"
_POLICY_PRODUCTION_DEFECT = "PRODUCTION_DEFECT_REPORT"
_POLICY_PRODUCTION_ACK = "PRODUCTION_CHANGE_ACK"

for _command in (
    TransitionCommand(
        command_id="PRODUCTION_START", policy_id=_POLICY_PRODUCTION_START,
        axis=AXIS_MAIN, from_values=("CONFIRM",), to_values=("PRODUCTION",),
        event_type="PRODUCTION_STARTED", effect_type="STAGE_NOTIFICATION",
    ),
    TransitionCommand(
        command_id="PRODUCTION_COMPLETE", policy_id=_POLICY_PRODUCTION_COMPLETE,
        axis=AXIS_MAIN, from_values=("PRODUCTION",), to_values=("CONSTRUCTION",),
        event_type="PRODUCTION_COMPLETED", effect_type="STAGE_NOTIFICATION",
    ),
    TransitionCommand(
        command_id="PRODUCTION_CANCEL", policy_id=_POLICY_PRODUCTION_CANCEL,
        axis=AXIS_MAIN, from_values=("PRODUCTION",), to_values=("CONFIRM",),
        event_type="PRODUCTION_CANCELLED", effect_type="STAGE_NOTIFICATION",
    ),
    TransitionCommand(
        command_id="PRODUCTION_UNCOMPLETE", policy_id=_POLICY_PRODUCTION_UNCOMPLETE,
        axis=AXIS_MAIN, from_values=("CONSTRUCTION",), to_values=("PRODUCTION",),
        event_type="PRODUCTION_COMPLETE_REVERTED", effect_type="STAGE_NOTIFICATION",
    ),
):
    COMMAND_REGISTRY.setdefault(_command.command_id, _command)
del _command


def _idempotency_key(body: dict[str, Any]) -> str | None:
    """요청 idempotency key(헤더 우선, body fallback, ≤64자). 없으면 None(중복제거 안 함)."""
    key = request.headers.get("Idempotency-Key") or body.get("idempotency_key")
    key = str(key).strip() if key is not None else ""
    return key[:64] if key else None


def _scope_hash(command_id: str, order_id: int) -> str:
    """전이 scope 의 sha256 hex(receipt 저장용)."""
    return hashlib.sha256(f"{command_id}:{order_id}".encode("utf-8")).hexdigest()


def _request_hash(body: dict[str, Any]) -> str:
    """요청 payload 의 sha256 hex(same-key/different-hash 감지용)."""
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _record_immutable_ack_receipt(
    db: Any, actor_user_id: Any, order_id: int, idem_key: str,
    body: dict[str, Any], response_body: dict[str, Any],
) -> None:
    """Order 불변 ack 의 idempotency receipt 1건을 기록한다(mutation_version bump 없음).

    execute_order_mutation 은 version 을 무조건 bump 하므로 ack(Order 불변)에는 쓸 수 없다.
    대신 REV-00 receipt 만 receipt-only 경로로 남겨 same-token 재요청을 replay(event 0)로
    수렴시킨다. resulting_versions 는 빈 dict(변경 order 없음)로 둔다.

    (actor, PRODUCTION_CHANGE_ACK, key) unique 제약이 same-token 동시 요청을 막는다 — 두
    번째 insert 는 flush 에서 IntegrityError 를 던져 호출부가 rollback→replay 하게 한다.

    :param db: business 트랜잭션 세션(호출부가 commit 소유).
    :param actor_user_id: 요청 actor(receipt 소유자·idempotency scope).
    :param order_id: 대상 주문 id(scope_hash 구성).
    :param idem_key: idempotency key(≤64자, None 아님 — 호출부가 존재 확인 후 전달).
    :param body: 요청 payload(request_hash 계산).
    :param response_body: replay 시 돌려줄 저장 응답 body.
    """
    now = now_utc_naive()
    db.add(
        OrderMutationReceipt(
            read_receipt_id=str(uuid.uuid4()),
            actor_user_id=actor_user_id,
            policy_id=_POLICY_PRODUCTION_ACK,
            idempotency_key=idem_key,
            scope_hash=_scope_hash("PRODUCTION_CHANGE_ACK", order_id),
            request_hash=_request_hash(body),
            response_status=200,
            response_body=response_body,
            resulting_versions={},  # Order 불변 — bump 없음.
            read_expires_at=now + READ_RECEIPT_TTL,
            expires_at=now + IDEMPOTENCY_REPLAY_WINDOW,
        )
    )
    db.flush()


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


def _stage_quest_block(sd: dict[str, Any], stage_code: str, stage_label: str):
    """현재 stage quest 가 존재하고 미완이면 409 QUEST_INCOMPLETE, 아니면 None.

    quest 자체가 없으면(레거시/backfill 미완) 게이트하지 않는다(lock-out 방지) — 존재하는
    stage quest 의 필수 승인이 완료돼야만 전이한다.
    """
    quests = sd.get("quests")
    if not isinstance(quests, list) or not quests:
        return None
    if not any(isinstance(q, dict) and q.get("stage") in (stage_code, stage_label) for q in quests):
        return None
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


def _mint_current_production_run(db: Any, order_id: int, sd: dict[str, Any]) -> None:
    """current IN_PROGRESS production run 이 없으면 발급(있으면 멱등 skip). flat steps/defects 복제."""
    exists = (
        db.query(ProductionRun.id)
        .filter(ProductionRun.order_id == order_id, ProductionRun.is_current.is_(True))
        .first()
    )
    if exists is not None:
        return
    production = sd.get("production") if isinstance(sd.get("production"), dict) else {}
    steps = production.get("steps") if isinstance(production.get("steps"), list) else []
    defects = production.get("defects") if isinstance(production.get("defects"), list) else []
    db.add(ProductionRun(
        order_id=order_id, status="IN_PROGRESS", started_at=now_utc_naive(),
        steps=copy.deepcopy(steps), defects=copy.deepcopy(defects), is_current=True,
    ))


def _close_current_production_run(db: Any, order_id: int) -> None:
    """current IN_PROGRESS run 을 COMPLETED + is_current=False 로 종결(없으면 no-op)."""
    run = (
        db.query(ProductionRun)
        .filter(ProductionRun.order_id == order_id, ProductionRun.is_current.is_(True))
        .first()
    )
    if run is None:
        return
    run.status = "COMPLETED"
    run.is_current = False


def _append_stage_history(sd: dict[str, Any], stage: str, note: str, user: Any) -> None:
    """workflow.history 에 단계 이력 1건 append + stage_updated_by 갱신."""
    wf = sd.setdefault("workflow", {})
    wf["stage_updated_by"] = user.name if user else "Unknown"
    updated_at = wf.get("stage_updated_at") or now_utc_naive().isoformat()
    history = wf.get("history") or []
    history.append({"stage": stage, "updated_at": updated_at,
                    "updated_by": wf["stage_updated_by"], "note": note})
    wf["history"] = history


def _audit_production(
    order: Order,
    action: str,
    user_id: Any,
    note: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """생산 행위 1건을 구조화 감사로 남긴다(문장은 표시 SSOT 가 만든다).

    라우트가 뒤에서 ``db.commit()`` 하므로 같은 트랜잭션에 싣는다(``auto_commit=False``).

    :param order: 대상 :class:`~models.Order`.
    :param action: 행위 코드(``PRODUCTION_STARTED`` 등).
    :param user_id: 행위자 user id.
    :param note: 문장 뒤에 붙일 짧은 부연(재제작 사유 등).
    :param extra: ``detail`` 에 추가로 담을 구조화 값.
    """
    context = order_audit_context(order)
    log_access(
        describe_order_action(order_id=order.id, action=action, note=note, **context),
        user_id,
        auto_commit=False,
        action=action, target_type="order", target_id=int(order.id),
        detail={**(extra or {}), **context},
    )


def _apply_start_side_effects(db: Any, order: Order, user: Any, user_id: Any,
                              release_hold: bool, hold_was_active: bool) -> None:
    """PRODUCTION_START 전이 후 same-tx side-effect: history·보류해제·run 발급·감사 기록."""
    sd = copy.deepcopy(_ensure_dict(order.structured_data))
    _append_stage_history(sd, "PRODUCTION", "제작 시작", user)
    if release_hold and hold_was_active:
        _release_hold_in_sd(sd, db, order.id, user_id, "release_on_start",
                            user.name if user else None)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    sync_erp_flat_columns(order, sd)
    _mint_current_production_run(db, order.id, sd)
    _audit_production(order, "PRODUCTION_STARTED", user_id,
                      extra={"hold_released": bool(release_hold and hold_was_active)})


def _apply_complete_side_effects(db: Any, order: Order, user: Any, user_id: Any, release_hold: bool,
                                 hold_was_active: bool, is_rework: bool, event_id: Any) -> None:
    """PRODUCTION_COMPLETE 전이 후 same-tx side-effect: history·rework 해제·보류해제·event 보강·run 종결."""
    sd = copy.deepcopy(_ensure_dict(order.structured_data))
    note = "제작 완료 (재제작)" if is_rework else "제작 완료 (시공/출고 대기)"
    _append_stage_history(sd, "CONSTRUCTION", note, user)
    if is_rework:
        production = sd.get("production")
        rework = production.get("rework") if isinstance(production, dict) else None
        if isinstance(rework, dict):
            rework["active"] = False  # count·reason·at·by_name 은 보존, active 만 해제.
            # completed_at 은 uncomplete(완료 취소)가 "이 완료가 재제작 완료였는지" 판정하는
            # 근거 — 존재하면 uncomplete 가 rework 를 active=True 로 복원한다.
            rework["completed_at"] = now_utc_naive().isoformat()
    if release_hold and hold_was_active:
        _release_hold_in_sd(sd, db, order.id, user_id, "release_on_complete",
                            user.name if user else None)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    sync_erp_flat_columns(order, sd)
    _enrich_production_completed_event(db, event_id, is_rework)
    _close_current_production_run(db, order.id)
    _audit_production(order, "PRODUCTION_COMPLETED", user_id,
                      extra={"is_rework": bool(is_rework), "new_stage": "CONSTRUCTION"})


def _apply_cancel_side_effects(db: Any, order: Order, user: Any, user_id: Any,
                               reason: str, event_id: Any) -> None:
    """PRODUCTION_CANCEL 전이 후 same-tx side-effect: history·진행 플래그 정리·event 보강.

    깨끗한 되돌림(F-1b): ``rework.active`` 해제(count·reason·at 보존)와 active hold 해제
    (:func:`_append_hold_history` 로 이력 보존)를 수행하고, 정리 여부를 전이 event payload 에
    ``rework_cleared``/``hold_released`` 로 남긴다.
    """
    sd = copy.deepcopy(_ensure_dict(order.structured_data))
    note = "제작 취소 (제작대기 복귀)"
    if reason:
        note += f" — {reason}"
    _append_stage_history(sd, "CONFIRM", note, user)

    production = sd.get("production")
    rework_cleared = False
    hold_released = False
    if isinstance(production, dict):
        rework = production.get("rework")
        if isinstance(rework, dict):
            rework_cleared = bool(rework.get("active"))
            rework["active"] = False  # count·reason·at 보존
        hold = production.get("hold")
        if isinstance(hold, dict) and hold.get("active"):
            _append_hold_history(production, user.name if user else None)
            production["hold"] = {"active": False, "reason": "", "at": None, "by_name": None}
            hold_released = True

    order.structured_data = sd
    flag_modified(order, "structured_data")
    sync_erp_flat_columns(order, sd)
    _merge_event_payload(db, event_id, {
        "domain": "PRODUCTION_DOMAIN", "action": "PRODUCTION_CANCELLED",
        "reason": reason, "rework_cleared": rework_cleared, "hold_released": hold_released,
    })
    # production run 은 건드리지 않는다 — 재시작 시 _mint_current_production_run 이 기존 current
    # run 을 그대로 재사용(멱등)하므로 중복 발급이 없고, 취소된 run 을 COMPLETED 로 종결하는
    # 의미 왜곡도 피한다(rework 경로와 동일 관례).
    _audit_production(order, "PRODUCTION_START_CANCELED", user_id,
                      extra={"reason": reason or None, "rework_cleared": rework_cleared,
                             "hold_released": hold_released})


def _apply_uncomplete_side_effects(db: Any, order: Order, user: Any, user_id: Any,
                                   event_id: Any) -> None:
    """PRODUCTION_UNCOMPLETE 전이 후 same-tx side-effect: history·재제작 복원·event 보강.

    직전 완료가 재제작 완료였으면(``rework.completed_at`` 존재 + ``active`` False) rework 를
    다시 활성으로 복원하고 완료 시각 표식을 제거한다(count 불변). production run 은 rework
    경로와 동일하게 건드리지 않는다(재완료 시 종결 호출이 no-op 로 수렴).
    """
    sd = copy.deepcopy(_ensure_dict(order.structured_data))
    _append_stage_history(sd, "PRODUCTION", "완료 취소 (제작중 복귀)", user)

    production = sd.get("production") if isinstance(sd.get("production"), dict) else None
    rework = production.get("rework") if isinstance(production, dict) else None
    rework_restored = False
    if isinstance(rework, dict) and rework.get("completed_at") and not rework.get("active"):
        rework["active"] = True
        rework.pop("completed_at", None)
        rework_restored = True

    order.structured_data = sd
    flag_modified(order, "structured_data")
    sync_erp_flat_columns(order, sd)
    _merge_event_payload(db, event_id, {
        "domain": "PRODUCTION_DOMAIN", "action": "PRODUCTION_COMPLETE_REVERTED",
        "rework_restored": rework_restored,
    })
    _audit_production(order, "PRODUCTION_COMPLETE_CANCELED", user_id,
                      extra={"rework_restored": rework_restored})


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


@erp_orders_production_bp.route("/<int:order_id>/production/start", methods=["POST"])
@login_required
@_production_steps_edit_required
def api_production_start(order_id):
    """제작 시작 (고객컨펌/CONFIRM → PRODUCTION), transition_order(PRODUCTION_START) 경유.

    5단계 하드 게이트를 순서대로 검사한다: 존재(404) → team 권한(데코레이터 403) → 제작대기
    stage(INVALID_STAGE 409) → 보류(HOLD_ACTIVE 409, release_hold 예외) → 현재 stage quest
    완료(QUEST_INCOMPLETE 409). same-key(idempotency) 재요청은 전이/side-effect 없이 저장된
    성공을 replay 한다. 전이 후 same-tx 로 history·보류해제·current IN_PROGRESS run 을 반영한다.
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        body = request.get_json(silent=True) or {}
        release_hold = body.get("release_hold") is True
        idem_key = _idempotency_key(body)
        user_id = session.get("user_id")
        user = get_user_by_id(user_id)
        sd = _ensure_dict(order.structured_data)
        hold_was_active = _hold_active(sd)[0]

        # replay(같은 key 저장 receipt 존재) 가 아니면 전제 게이트를 검사한다.
        if not _idempotency_receipt_exists(db, user_id, _POLICY_PRODUCTION_START, idem_key):
            if order.erp_stage_code not in ("고객컨펌", "CONFIRM"):
                return jsonify({"success": False, "code": "INVALID_STAGE",
                                "message": "제작대기 상태에서만 제작을 시작할 수 있습니다."}), 409
            blocked = _hold_block_response(sd, release_hold)
            if blocked is not None:
                return blocked
            blocked = _stage_quest_block(sd, "CONFIRM", "고객컨펌")
            if blocked is not None:
                return blocked

        try:
            result = transition_order(
                db, command_id="PRODUCTION_START", order_id=order_id,
                actor_user_id=user_id, expected_from="CONFIRM", target_value="PRODUCTION",
                scope_hash=_scope_hash("PRODUCTION_START", order_id),
                request_hash=_request_hash(body), idempotency_key=idem_key,
            )
        except (TransitionError, RevisionError) as exc:
            db.rollback()
            return _transition_error_response(exc)

        if not result.replayed:
            _apply_start_side_effects(db, order, user, user_id, release_hold, hold_was_active)
        db.commit()
        return jsonify({"success": True, "message": "제작이 시작되었습니다.", "new_status": "PRODUCTION"})
    except Exception as exc:  # noqa: BLE001 - 최종 방어(구체 전이 예외는 위에서 매핑)
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/production/complete", methods=["POST"])
@login_required
@_production_steps_edit_required
def api_production_complete(order_id):
    """제작 완료 (제작중/PRODUCTION → CONSTRUCTION), transition_order(PRODUCTION_COMPLETE) 경유.

    5단계 하드 게이트: 존재(404) → team 권한(데코레이터 403) → 제작중 stage(INVALID_STAGE 409)
    → 보류(HOLD_ACTIVE 409, release_hold 예외) → 현재 stage quest 완료(QUEST_INCOMPLETE 409).
    same-key 재요청은 전이/side-effect 없이 replay. 전이 후 same-tx 로 history·재제작 표식 해제·
    보류해제·PRODUCTION_COMPLETED event 보강·current run 종결(COMPLETED)을 반영한다. 5-step
    process/defect 는 완료의 hard gate 가 아니다(§341).
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        body = request.get_json(silent=True) or {}
        release_hold = body.get("release_hold") is True
        idem_key = _idempotency_key(body)
        user_id = session.get("user_id")
        user = get_user_by_id(user_id)
        sd = _ensure_dict(order.structured_data)
        hold_was_active = _hold_active(sd)[0]
        is_rework = _is_rework_completion(sd)

        if not _idempotency_receipt_exists(db, user_id, _POLICY_PRODUCTION_COMPLETE, idem_key):
            if order.erp_stage_code not in ("생산", "PRODUCTION"):
                return jsonify({"success": False, "code": "INVALID_STAGE",
                                "message": "제작중 상태에서만 제작을 완료할 수 있습니다."}), 409
            blocked = _hold_block_response(sd, release_hold)
            if blocked is not None:
                return blocked
            blocked = _stage_quest_block(sd, "PRODUCTION", "생산")
            if blocked is not None:
                return blocked

        try:
            result = transition_order(
                db, command_id="PRODUCTION_COMPLETE", order_id=order_id,
                actor_user_id=user_id, expected_from="PRODUCTION", target_value="CONSTRUCTION",
                scope_hash=_scope_hash("PRODUCTION_COMPLETE", order_id),
                request_hash=_request_hash(body), idempotency_key=idem_key,
            )
        except (TransitionError, RevisionError) as exc:
            db.rollback()
            return _transition_error_response(exc)

        if not result.replayed:
            _apply_complete_side_effects(
                db, order, user, user_id, release_hold, hold_was_active, is_rework, result.event_id
            )
        db.commit()
        return jsonify({
            "success": True,
            "message": "제작이 완료되었습니다. (시공 대기 상태로 변경)",
            "new_status": "CONSTRUCTION",
        })
    except Exception as exc:  # noqa: BLE001 - 최종 방어(구체 전이 예외는 위에서 매핑)
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/production/rework", methods=["POST"])
@login_required
@_production_steps_edit_required
def api_production_rework(order_id: int):
    """수정 제작 시작 (제작완료 → PRODUCTION 되돌림).

    제작완료(시공/CONSTRUCTION) 상태의 주문을 다시 제작중(PRODUCTION)으로 되돌린다.
    재제작 회차(count)를 누적하고 ``sd['production']['rework']`` 에 활성 표식을 남긴다
    (완료 시 ``api_production_complete`` 가 active=False 로 해제하며 count 는 보존).
    가드는 start/complete 와 동일 순서: 404 → INVALID_STAGE(제작완료가 아니면 409) →
    보류 게이트(HOLD_ACTIVE / release_hold, via="release_on_rework").

    :param order_id: 대상 주문 id.
    :param reason: (body) 수정 제작 사유(선택, trim). 빈 값 허용.
    :param release_hold: (body) 보류 해제 후 진행 여부(선택, bool).
    :return: ``{success, message, new_status}`` 또는 오류 JSON(에러 키 = message).
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        # 전이 전제조건: 제작완료(시공/CONSTRUCTION) 에서만 수정 제작 허용. 레거시 한글 값 포함.
        if order.erp_stage_code not in ("시공", "CONSTRUCTION"):
            return (
                jsonify(
                    {
                        "success": False,
                        "code": "INVALID_STAGE",
                        "message": "제작완료 상태에서만 수정 제작을 시작할 수 있습니다.",
                    }
                ),
                409,
            )

        body = request.get_json(silent=True) or {}
        release_hold = body.get("release_hold") is True
        reason_raw = body.get("reason")
        reason = reason_raw.strip() if isinstance(reason_raw, str) else ""

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)

        hold_gate = _apply_production_hold_gate(
            sd,
            release_hold=release_hold,
            via="release_on_rework",
            order_id=order_id,
            user_id=user_id,
            released_by=user.name if user else None,
            db=db,
        )
        if hold_gate is not None:
            return hold_gate

        wf = sd.get("workflow") or {}
        wf["stage"] = "PRODUCTION"
        wf["stage_updated_at"] = now_utc_naive().isoformat()
        wf["stage_updated_by"] = user.name if user else "Unknown"

        note = "수정 제작 시작"
        if reason:
            note += f" — {reason}"
        hist = wf.get("history") or []
        hist.append(
            {
                "stage": "PRODUCTION",
                "updated_at": wf["stage_updated_at"],
                "updated_by": wf["stage_updated_by"],
                "note": note,
            }
        )
        wf["history"] = hist
        sd["workflow"] = wf

        production = sd.get("production")
        if not isinstance(production, dict):
            production = {}
            sd["production"] = production
        prev_rework = production.get("rework")
        prev_count = prev_rework.get("count") if isinstance(prev_rework, dict) else 0
        count = (prev_count or 0) + 1
        production["rework"] = {
            "active": True,
            "reason": reason,
            "count": count,
            "at": now_utc_naive().isoformat(),
            "by_name": user.name if user else None,
        }

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = "PRODUCTION"
        sync_erp_flat_columns(order, sd)

        db.add(
            OrderEvent(
                order_id=order_id,
                event_type="PRODUCTION_REWORK_STARTED",
                payload={
                    "reason": reason,
                    "count": count,
                    "domain": "PRODUCTION_DOMAIN",
                    "action": "PRODUCTION_REWORK_STARTED",
                },
                created_by_user_id=user_id,
            )
        )
        _audit_production(order, "PRODUCTION_REWORK_STARTED", user_id,
                          note=reason or None, extra={"reason": reason or None, "count": count})
        db.commit()
        return jsonify(
            {"success": True, "message": "수정 제작을 시작했습니다.", "new_status": "PRODUCTION"}
        )
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/production/cancel", methods=["POST"])
@login_required
@_production_steps_edit_required
def api_production_cancel(order_id: int):
    """제작 취소 (제작중 → 제작대기/CONFIRM 되돌림), transition_order(PRODUCTION_CANCEL) 경유.

    제작중(생산/PRODUCTION) 상태의 주문을 제작대기(CONFIRM)로 되돌린다. 후진 전이이므로
    **보류 게이트를 적용하지 않는다** — 보류는 전진(시작·완료·수정 제작)만 막는 배지이며,
    되돌리기는 보류가 걸린 채로도 허용한다(단, 아래처럼 정리한다). 가드는 404 →
    INVALID_STAGE(제작중이 아니면 409) 순서. 상태 변이는 start/complete 와 같은 canonical
    엔진 경유라 mutation_version++·idempotency receipt·legacy OrderEvent·tx내 outbox 가
    원자 보장되며, 전이 후 same-tx 로 history·플래그 정리·SecurityLog 를 반영한다.

    **깨끗한 되돌림(F-1)**: 취소는 진행 자체를 되돌리므로 진행 플래그를 정리한다(이력 보존).
    ``sd['production']`` 이 dict 면 (1) ``rework`` dict 의 ``active`` 를 False 로(count·reason·at
    보존), (2) ``hold`` 가 active 면 ``_append_hold_history`` 로 이력에 보존한 뒤 hold 초기화.
    이렇게 하면 제작대기로 복귀한 카드/시트에 재제작·보류 배지가 잔존하지 않는다.
    (완료 취소 ``uncomplete`` 는 제작중 복귀라 rework 를 **복원**하므로 여기와 반대다.)

    :param order_id: 대상 주문 id.
    :param reason: (body) 취소 사유(선택, trim). 빈 값 허용.
    :return: ``{success, message, new_status}`` 또는 오류 JSON(에러 키 = message).
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        body = request.get_json(silent=True) or {}
        reason_raw = body.get("reason")
        reason = reason_raw.strip() if isinstance(reason_raw, str) else ""
        idem_key = _idempotency_key(body)
        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        # replay(같은 key 저장 receipt 존재) 가 아니면 전제 게이트를 검사한다.
        # 전이 전제조건: 제작중(생산/PRODUCTION) 에서만 취소 허용. 레거시 한글 값 포함.
        if not _idempotency_receipt_exists(db, user_id, _POLICY_PRODUCTION_CANCEL, idem_key):
            if order.erp_stage_code not in ("생산", "PRODUCTION"):
                return jsonify({"success": False, "code": "INVALID_STAGE",
                                "message": "제작중 상태에서만 제작을 취소할 수 있습니다."}), 409

        try:
            result = transition_order(
                db, command_id="PRODUCTION_CANCEL", order_id=order_id,
                actor_user_id=user_id, expected_from="PRODUCTION", target_value="CONFIRM",
                scope_hash=_scope_hash("PRODUCTION_CANCEL", order_id),
                request_hash=_request_hash(body), idempotency_key=idem_key,
                reason=reason or None,
            )
        except (TransitionError, RevisionError) as exc:
            db.rollback()
            return _transition_error_response(exc)

        if not result.replayed:
            _apply_cancel_side_effects(db, order, user, user_id, reason, result.event_id)
        db.commit()
        return jsonify({
            "success": True,
            "message": "제작을 취소했습니다. (제작대기 복귀)",
            "new_status": "CONFIRM",
        })
    except Exception as exc:  # noqa: BLE001 - 최종 방어(구체 전이 예외는 위에서 매핑)
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/production/uncomplete", methods=["POST"])
@login_required
@_production_steps_edit_required
def api_production_uncomplete(order_id: int):
    """완료 취소 (제작완료 → 제작중/PRODUCTION 되돌림), transition_order(PRODUCTION_UNCOMPLETE) 경유.

    제작완료(시공/CONSTRUCTION) 상태의 주문을 다시 제작중(PRODUCTION)으로 되돌린다.
    후진 전이이므로 **보류 게이트를 적용하지 않는다**(cancel 참조 — 보류는 유지된다).
    가드는 404 → INVALID_STAGE(제작완료가 아니면 409) 순서. 상태 변이는 canonical 엔진
    경유이며, 전이 후 same-tx 로 history·재제작 복원·run 재발급·SecurityLog 를 반영한다.

    **재제작 복원**: 직전 완료가 재제작 완료였다면(``rework`` dict 에 ``completed_at`` 가 있고
    ``active`` 가 False) 완료를 되돌리며 rework 를 ``active=True`` 로 복원하고 ``completed_at``
    키를 제거한다(회차 count 는 불변). 재제작 완료가 아니었으면 rework 는 건드리지 않는다.

    :param order_id: 대상 주문 id.
    :return: ``{success, message, new_status}`` 또는 오류 JSON(에러 키 = message).
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        body = request.get_json(silent=True) or {}
        idem_key = _idempotency_key(body)
        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        # 전이 전제조건: 제작완료(시공/CONSTRUCTION) 에서만 완료 취소 허용. 레거시 한글 값 포함.
        if not _idempotency_receipt_exists(db, user_id, _POLICY_PRODUCTION_UNCOMPLETE, idem_key):
            if order.erp_stage_code not in ("시공", "CONSTRUCTION"):
                return jsonify({"success": False, "code": "INVALID_STAGE",
                                "message": "제작완료 상태에서만 완료 취소할 수 있습니다."}), 409

        try:
            result = transition_order(
                db, command_id="PRODUCTION_UNCOMPLETE", order_id=order_id,
                actor_user_id=user_id, expected_from="CONSTRUCTION", target_value="PRODUCTION",
                scope_hash=_scope_hash("PRODUCTION_UNCOMPLETE", order_id),
                request_hash=_request_hash(body), idempotency_key=idem_key,
            )
        except (TransitionError, RevisionError) as exc:
            db.rollback()
            return _transition_error_response(exc)

        if not result.replayed:
            _apply_uncomplete_side_effects(db, order, user, user_id, result.event_id)
        db.commit()
        return jsonify({
            "success": True,
            "message": "완료를 취소했습니다. (제작중 복귀)",
            "new_status": "PRODUCTION",
        })
    except Exception as exc:  # noqa: BLE001 - 최종 방어(구체 전이 예외는 위에서 매핑)
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/production/change-ack", methods=["POST"])
@login_required
@_production_steps_edit_required
def api_production_change_ack(order_id: int):
    """생산 변경 확인(ack). 카드/시트 변경 스트립·묘비 [확인] 버튼이 호출한다.

    **Order 불변**(structured_data·상태·mutation_version 무변경) — ``PRODUCTION_CHANGE_ACK``
    OrderEvent 1건과 (idempotency key 가 있으면) REV-00 receipt 1건만 기록한다. 이 ack 시각이
    변경 감지 윈도를 리셋하므로 이후 대시보드 재조회 시 해당 주문의 변경 스트립이 사라진다.
    **삭제(취소)된 주문에도 허용**한다 — 묘비 카드 확인용이라 존재 여부만 확인한다.

    **idempotent**: body/헤더 idempotency key 를 주면 same-token 재요청은 event/receipt 를
    재기록하지 않고 저장 응답을 replay 한다(event 0). key 가 없으면 dedupe 하지 않는다(레거시
    묘비 재확인·매 요청 기록 — 기존 동작 보존).

    권한: 생산 공정 스텝과 동일 게이트(ADMIN 또는 CS/SALES/**PRODUCTION** 팀). ack 는
    "생산 인원 개인별" 설계라 생산팀 계정이 반드시 눌러야 하므로 erp_edit(ADMIN/CS/SALES
    전용)이 아닌 스텝 게이트를 재사용한다.

    :param order_id: 대상 주문 id.
    :return: ``{success, data:{order_id}}`` 또는 오류 JSON.
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if order is None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        body = request.get_json(silent=True) or {}
        idem_key = _idempotency_key(body)
        user_id = session.get("user_id")
        response_body = {"success": True, "data": {"order_id": order_id}}

        # idempotent: 같은 token 재요청은 event/receipt 재기록 없이 저장 응답을 replay 한다.
        if _idempotency_receipt_exists(db, user_id, _POLICY_PRODUCTION_ACK, idem_key):
            return jsonify(response_body)

        payload = {"source": "tablet_kanban"}
        if order.deleted_at is not None:
            # 묘비 확인: 이 삭제 시점을 마커로 고정한다(시계 비교 없이 동등성으로 판정).
            # 복구 후 재삭제되면 deleted_at 값이 달라져 묘비가 다시 나타난다(의도된 동작).
            payload["deleted_at"] = str(order.deleted_at)
        db.add(
            OrderEvent(
                order_id=order_id,
                event_type="PRODUCTION_CHANGE_ACK",
                payload=payload,
                created_by_user_id=user_id,
            )
        )

        # Order 는 건드리지 않는다(version bump 없음) — receipt 만 same-token idempotency 를 건다.
        if idem_key is not None:
            try:
                _record_immutable_ack_receipt(db, user_id, order_id, idem_key, body, response_body)
            except IntegrityError:
                db.rollback()  # 동시 same-token → event/receipt 0, replay 로 수렴.
                return jsonify(response_body)
        _audit_production(order, "PRODUCTION_CHANGE_ACKNOWLEDGED", user_id,
                          extra={"source": "tablet_kanban"})
        db.commit()
        return jsonify(response_body)
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/production/steps", methods=["GET"])
@login_required
def api_production_steps_get(order_id: int):
    """생산 공정 스텝 조회(시트 lazy 로드용).

    sd['production']['steps'] 가 없으면 기본 5단계를 메모리에서 파생만 하고 저장하지
    않는다(쓰기는 POST 소관). 읽기는 대시보드 열람과 동일하게 @login_required 만 요구
    — 편집 불가 팀도 진행 현황은 볼 수 있어야 한다.
    """
    db = get_db()
    order = db.get(Order, order_id)
    if not order or order.status == "DELETED" or order.deleted_at is not None:
        return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

    sd = _ensure_dict(order.structured_data)
    production = sd.get("production") if isinstance(sd.get("production"), dict) else {}
    steps = production.get("steps")
    if not isinstance(steps, list) or not steps:
        steps = [
            {"key": key, "label": label, "done": False, "at": None, "by_name": None}
            for key, label in _PRODUCTION_STEP_DEFS
        ]
    done_count = sum(1 for s in steps if isinstance(s, dict) and s.get("done"))
    defects = production.get("defects") if isinstance(production.get("defects"), list) else []
    latest_defect = defects[-1] if defects else None
    return jsonify(
        {
            "success": True,
            "data": {
                "steps": steps,
                "done_count": done_count,
                "total": len(steps),
                "latest_defect": latest_defect,
            },
        }
    )


@erp_orders_production_bp.route("/<int:order_id>/production/steps", methods=["POST"])
@login_required
@_production_steps_edit_required
def api_production_steps(order_id: int):
    """생산 공정 스텝 체크 토글. body {key, done(bool)[, idempotency_key]}.

    최초 접근 시 기본 5단계(cut/edge/paint/assemble/inspect)를 생성한 뒤 해당 key의
    done 상태를 반영한다(체크 시 at=UTC iso, by_name 기록). 스텝 변경은
    execute_order_mutation(REV-00) 경유로 Order.mutation_version++ 와 PRODUCTION_STEP_CHECKED
    OrderEvent 를 한 트랜잭션에 원자 기록한다(JSONB 는 deepcopy+flag_modified). idempotency
    key 를 주면 same-token 재요청은 replay(중복 bump/event 0)한다 — 없으면 dedupe 안 함.
    """
    db = get_db()
    try:
        payload = request.get_json(silent=True) or {}
        key = payload.get("key")
        done = payload.get("done")
        if key not in _PRODUCTION_STEP_KEYS or not isinstance(done, bool):
            return jsonify({"success": False, "error": "key 또는 done 값이 올바르지 않습니다."}), 400

        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

        user = get_user_by_id(session.get("user_id"))
        user_id = session.get("user_id")
        captured: dict[str, Any] = {}

        def _mutate(sess: Any, orders: list[Order]) -> dict[int, list[str]]:
            o = orders[0]
            sd = copy.deepcopy(_ensure_dict(o.structured_data))
            steps = _ensure_production_steps(sd)
            # key 는 _PRODUCTION_STEP_KEYS 로 검증됐고 _ensure_production_steps 가 5단계를
            # 항상 보장하므로 target 은 반드시 존재한다.
            target = next(s for s in steps if s.get("key") == key)
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            target["done"] = done
            target["at"] = now_iso if done else None
            target["by_name"] = (user.name if user else None) if done else None
            o.structured_data = sd
            flag_modified(o, "structured_data")
            sess.add(
                OrderEvent(
                    order_id=o.id,
                    event_type="PRODUCTION_STEP_CHECKED",
                    payload={
                        "key": key,
                        "done": done,
                        "domain": "PRODUCTION_DOMAIN",
                        "action": "PRODUCTION_STEP_CHECKED",
                    },
                    created_by_user_id=user_id,
                )
            )
            captured["steps"] = steps
            return {o.id: []}

        try:
            execute_order_mutation(
                db,
                actor_user_id=user_id,
                policy_id=_POLICY_PRODUCTION_STEP,
                order_ids=[order_id],
                scope_hash=_scope_hash("PRODUCTION_STEP", order_id),
                request_hash=_request_hash(payload),
                mutation=_mutate,
                idempotency_key=_idempotency_key(payload),
            )
        except RevisionError as exc:
            db.rollback()
            return jsonify({"success": False, "error": str(exc), "code": exc.error_code}), exc.status_code

        _audit_production(order, "PRODUCTION_STEP_CHECKED", user_id,
                          note=f"{key}: {'완료' if done else '해제'}",
                          extra={"step": key, "done": bool(done)})
        db.commit()
        steps = captured["steps"]
        done_count = sum(1 for s in steps if s.get("done"))
        return jsonify(
            {"success": True, "data": {"steps": steps, "done_count": done_count, "total": len(steps)}}
        )
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/production/defect", methods=["POST"])
@login_required
@_production_steps_edit_required
def api_production_defect(order_id: int):
    """생산 불량 보고. body {reason}.

    reason 은 화이트리스트(_PRODUCTION_DEFECT_REASONS)로 검증한다. 통과 시
    sd['production']['defects'] 에 {reason, at(UTC iso), by_name} 를 append 하고
    최근 _PRODUCTION_DEFECTS_CAP(20)건만 유지한다. defect 보고는 execute_order_mutation(REV-00)
    경유로 Order.mutation_version++ 와 PRODUCTION_DEFECT_REPORTED OrderEvent 를 한 트랜잭션에
    원자 기록한다(JSONB 는 deepcopy+flag_modified). idempotency key 를 주면 same-token 재요청은
    replay(중복 bump/event 0)한다 — 없으면 dedupe 안 함.

    :param order_id: 대상 주문 id.
    :return: {success, data:{defects, latest, total}} 또는 오류 JSON.
    """
    db = get_db()
    try:
        payload = request.get_json(silent=True) or {}
        reason = payload.get("reason")
        if reason not in _PRODUCTION_DEFECT_REASONS:
            return jsonify({"success": False, "error": "불량 사유 값이 올바르지 않습니다."}), 400

        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

        user = get_user_by_id(session.get("user_id"))
        user_id = session.get("user_id")
        captured: dict[str, Any] = {}

        def _mutate(sess: Any, orders: list[Order]) -> dict[int, list[str]]:
            o = orders[0]
            sd = copy.deepcopy(_ensure_dict(o.structured_data))
            production = sd.get("production")
            if not isinstance(production, dict):
                production = {}
                sd["production"] = production
            defects = production.get("defects")
            if not isinstance(defects, list):
                defects = []
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            entry = {"reason": reason, "at": now_iso, "by_name": (user.name if user else None)}
            defects.append(entry)
            if len(defects) > _PRODUCTION_DEFECTS_CAP:
                defects = defects[-_PRODUCTION_DEFECTS_CAP:]
            production["defects"] = defects
            o.structured_data = sd
            flag_modified(o, "structured_data")
            sess.add(
                OrderEvent(
                    order_id=o.id,
                    event_type="PRODUCTION_DEFECT_REPORTED",
                    payload={
                        "reason": reason,
                        "domain": "PRODUCTION_DOMAIN",
                        "action": "PRODUCTION_DEFECT_REPORTED",
                    },
                    created_by_user_id=user_id,
                )
            )
            captured["defects"] = defects
            captured["entry"] = entry
            return {o.id: []}

        try:
            execute_order_mutation(
                db,
                actor_user_id=user_id,
                policy_id=_POLICY_PRODUCTION_DEFECT,
                order_ids=[order_id],
                scope_hash=_scope_hash("PRODUCTION_DEFECT", order_id),
                request_hash=_request_hash(payload),
                mutation=_mutate,
                idempotency_key=_idempotency_key(payload),
            )
        except RevisionError as exc:
            db.rollback()
            return jsonify({"success": False, "error": str(exc), "code": exc.error_code}), exc.status_code

        _audit_production(order, "PRODUCTION_DEFECT_REPORTED", user_id,
                          note=reason, extra={"reason": reason})
        db.commit()
        defects = captured["defects"]
        return jsonify(
            {"success": True, "data": {"defects": defects, "latest": captured["entry"], "total": len(defects)}}
        )
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500


def _mirror_workflow_hold_to_production(order: Order, active: bool, reason: str, user: Any) -> dict[str, Any]:
    """전이기(transitional) dual-write: canonical ``workflow.hold`` 를 legacy ``production.hold`` 배지로 미러.

    HOLD_ORDER/RELEASE_HOLD 전이는 canonical ``workflow.hold`` 축을 소유하지만, STATE-PROD-01
    게이트(:func:`_hold_active` 가 ``production.hold.active`` 를 읽음)와 생산 칸반 배지가 아직
    ``production.hold`` 를 읽는다. 따라서 전이 직후 **같은 tx** 에서 ``production.hold`` 를
    canonical 상태로 동기화해 게이트·배지를 무회귀로 보존한다. ``at`` 은 canonical
    ``workflow.hold.held_at`` 을 그대로 재사용해 두 저장소의 시각을 일치시킨다.

    ponytail: transitional mirror. 완전 통합(``production.hold`` → read-only projection, 게이트
    reader 를 ``workflow.hold`` 로 이관, backfill 마이그레이션)은 후속 packet(SSOT §350) 소관이며
    그때 이 미러를 제거한다. 영구 해법으로 위장하지 말 것.

    :param order: 전이가 ``workflow.hold`` 를 이미 쓴 주문(같은 tx, uncommitted).
    :param active: True 면 보류 활성(HELD), False 면 해제(NONE).
    :param reason: 보류 사유(active 일 때만 의미).
    :param user: 요청 actor(``by_name`` 표기용).
    :return: 미러된 ``production.hold`` dict(응답 body 용).
    """
    sd = copy.deepcopy(_ensure_dict(order.structured_data))
    workflow = sd.get("workflow") if isinstance(sd.get("workflow"), dict) else {}
    wf_hold = workflow.get("hold") if isinstance(workflow.get("hold"), dict) else {}
    production = sd.get("production")
    if not isinstance(production, dict):
        production = {}
        sd["production"] = production
    hold = {
        "active": active,
        "reason": reason if active else "",
        "at": wf_hold.get("held_at") if active else None,
        "by_name": (user.name if user else None) if active else None,
    }
    # 해제 미러 시 초기화 직전 active hold 를 이력에 보존한다(완료 후 사유 소실 방지).
    if not active:
        _append_hold_history(production, user.name if user else None)
    production["hold"] = hold
    order.structured_data = sd
    flag_modified(order, "structured_data")
    return hold


@erp_orders_production_bp.route("/<int:order_id>/production/hold", methods=["POST"])
@login_required
@_production_steps_edit_required
def api_production_hold(order_id: int):
    """생산 보류 토글 — canonical HOLD_ORDER/RELEASE_HOLD 전이(STATE-OVERLAY-01).

    body ``{active(bool), reason(str, optional), idempotency_key(optional)}``. active=True 는
    ``HOLD_ORDER``(NONE→HELD), active=False 는 ``RELEASE_HOLD``(HELD→NONE) 전이를
    :func:`transition_order` 로 실행한다 — canonical ``workflow.hold`` 축 소유 + mutation_version++
    + idempotency receipt + legacy ``OrderEvent``(ORDER_HELD/ORDER_HOLD_RELEASED) + 같은 tx
    outbox(HOLD_NOTIFICATION)를 원자 기록한다. 보류는 overlay 라 **main stage
    (erp_stage_code/workflow.stage)는 불변**이며, legacy ``order.status`` 는 projection 규칙
    (ON_HOLD>logistics>main)상 HELD 동안 ``ON_HOLD`` 로 파생된다.

    전이 후 같은 tx 에서 ``production.hold`` 배지를 canonical 상태로 미러한다(전이기 dual-write,
    :func:`_mirror_workflow_hold_to_production`). 해제(active=False) 미러 시에는 초기화 직전의
    active hold 를 ``production.hold_history`` 에 보존한다(완료 후 이력 소실 방지,
    :func:`_append_hold_history` — 전이 게이트 release 경로와 같은 헬퍼). 권한은 생산 팀
    (PRODUCTION_EDIT: ADMIN 또는 CS/SALES/PRODUCTION). 이미 보류/해제 상태에서 같은 방향을 다시
    호출하면 전이 엔진이 409 로 거부한다(상태 불변). same idempotency_key 재요청은 전이 1회 후
    저장된 응답을 replay 한다.

    :param order_id: 대상 주문 id.
    :return: ``{success, data:{hold}}`` 또는 오류 JSON.
    """
    db = get_db()
    try:
        payload = request.get_json(silent=True) or {}
        active = payload.get("active")
        if not isinstance(active, bool):
            return jsonify({"success": False, "error": "active 값(bool)이 올바르지 않습니다."}), 400
        reason_raw = payload.get("reason")
        reason = reason_raw.strip() if isinstance(reason_raw, str) else ""

        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)
        command_id = "HOLD_ORDER" if active else "RELEASE_HOLD"
        try:
            result = transition_order(
                db, command_id=command_id, order_id=order_id,
                actor_user_id=user_id,
                expected_from="NONE" if active else "HELD",
                target_value="HELD" if active else "NONE",
                scope_hash=_scope_hash(command_id, order_id),
                request_hash=_request_hash(payload),
                idempotency_key=_idempotency_key(payload),
                reason=reason if active else None,
            )
        except (TransitionError, RevisionError) as exc:
            db.rollback()
            return _transition_error_response(exc)

        if result.replayed:
            hold = _hold_active(_ensure_dict(order.structured_data))[1] or {
                "active": active, "reason": reason if active else "", "at": None, "by_name": None,
            }
        else:
            hold = _mirror_workflow_hold_to_production(order, active, reason, user)
        _audit_production(
            order,
            "PRODUCTION_HOLD_SET" if active else "PRODUCTION_HOLD_RELEASED",
            user_id, note=reason or None, extra={"active": bool(active), "reason": reason or None},
        )
        db.commit()
        return jsonify({"success": True, "data": {"hold": hold}})
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500


@erp_orders_production_bp.route("/<int:order_id>/logistics", methods=["POST"])
@login_required
def api_set_logistics_status(order_id: int):
    """물류 상태 전이 — canonical SET_LOGISTICS_STATUS(STATE-OVERLAY-01).

    body ``{status, idempotency_key(optional)}``. ``shipment.logistics_status`` overlay 축을
    :func:`transition_order` 로 전이한다(enum NONE|MEASURED|REGIONAL_MEASURED|SCHEDULED|
    SHIPPED_PENDING). overlay 라 **main stage 불변**이며 mutation_version++·idempotency receipt·
    legacy ``OrderEvent``(LOGISTICS_STATUS_CHANGED)·같은 tx outbox(LOGISTICS_NOTIFICATION)를
    원자 기록한다. 현재 값을 expected-from 으로 읽어 낙관적으로 전이한다(동시 변경 시 409).

    권한은 출고/물류 팀(SHIPMENT_EDIT: ADMIN/MANAGER 또는 STAFF+CS/SALES/SHIPMENT)을 policy
    SSOT 로 인라인 판정한다(TESTING 에서도 강제). generic status write 는 이 엔드포인트가 아니라
    STATE-LEGACY-01 소관이며, 여기선 typed 물류 enum 만 받는다(enum 밖이면 전이 엔진이 거부).

    :param order_id: 대상 주문 id.
    :return: ``{success, data:{logistics_status}}`` 또는 오류 JSON.
    """
    db = get_db()
    try:
        payload = request.get_json(silent=True) or {}
        target = payload.get("status")
        if not isinstance(target, str) or not target.strip():
            return jsonify({"success": False, "error": "status 값이 올바르지 않습니다."}), 400
        target = target.strip()

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)
        decision = evaluate_policy(POLICY_REGISTRY["SHIPMENT_EDIT"], user)
        if not decision.allowed:
            return jsonify({"success": False, "code": decision.code, "message": decision.reason}), decision.status

        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

        try:
            transition_order(
                db, command_id="SET_LOGISTICS_STATUS", order_id=order_id,
                actor_user_id=user_id,
                expected_from=read_logistics(order),
                target_value=target,
                scope_hash=_scope_hash("SET_LOGISTICS_STATUS", order_id),
                request_hash=_request_hash(payload),
                idempotency_key=_idempotency_key(payload),
            )
        except (TransitionError, RevisionError) as exc:
            db.rollback()
            return _transition_error_response(exc)

        _audit_production(order, "LOGISTICS_STATUS_CHANGED", user_id, note=target,
                          extra={"logistics_status": target})
        db.commit()
        return jsonify({"success": True, "data": {"logistics_status": target}})
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500

"""생산 제작 완료 한 곳 — [제작 완료] 본문 · 공장마다 제작 완료(설계서 2026-11-23 §4-3 · §4-4 · §4-14 · §7, 3단계 ⑥).

``POST /api/orders/<id>/production/complete``(``foms/api/production/orders.py``)의 본문을 그대로 옮겼고, 새
``POST /api/orders/<id>/production/factory-done``(``foms/api/production/factory_done.py``)이 같은 길을 쓴다 — API 가 API 를
부르지 않게(레이어) 서비스 한 곳에 둔다. 옛 API 모듈은 이 헬퍼들을 같은 이름으로 다시 내보낸다(다른 생산 API 가 같이 쓴다).

**공장마다 제작 완료**(섞인 주문 = 2공장 장이 있는 주문만, §4-14):

* 표지 ``structured_data.production.factory_done = {"2": {keys, at, by_name, by_user_id}}`` — 서버만 쓴다(폼 저장 · 주문 만들기 ·
  초안 자동 저장이 못 바꾼다). '살아 있음' 판정은 :func:`foms.services.orders.drawing_factory.factory_done_entry` 한 곳(그 공장
  지금 장 key ⊆ 저장 keys — 새 판 도면이 오면 저절로 풀림).
* 공장 완료(``done=True``): 생산 단계 · 보류 아님 · 그 공장 장이 네 파트 모두 완료(:func:`complete_state` ``factory=``) → 다른 있는
  공장이 모두 살아 있으면 **마지막** = 지금 제작 완료 길 그대로(남은 단계 게이트 · 전이 · 곁일이 남은 표지를 같은 deepcopy 에 씀) →
  시공 대기. 마지막이 아니면 표지만(``execute_order_mutation`` 버전 +1, 이벤트 ``PRODUCTION_FACTORY_COMPLETED``, 단계 그대로).
* 공장 완료 취소(``done=False``): 생산 단계에서 그 공장 표지만 지운다(``PRODUCTION_FACTORY_UNCOMPLETED``).
* 옛 [제작 완료](``production/complete``)는 섞인 주문에서 남은 공장을 한꺼번에 완료로 읽는다(주문 전체 판정을 통과해야 한다).
* 완료 취소(시공 대기 → 생산)는 누른 사람 공장 표지만(관리자는 고른 공장, 기본 둘 다), 재제작 · 제작 취소는 표지를 모두 지운다.

한 공장 주문은 표지를 쓰지 않는다 — 지금 길 그대로다.
"""

from __future__ import annotations

import copy
import datetime
from typing import Any, Callable, Iterable, Optional

from flask import jsonify
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_display import _ensure_dict
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.admin_override import (
    GATE_STEPS_INCOMPLETE,
    admin_override_error,
    log_admin_override_denied,
    record_admin_override_event,
    resolve_admin_override,
)
from foms.services.orders.drawing_factory import (
    FACTORY_DONE_KEY,
    current_factories,
    factory_done_entry,
    has_second_factory,
    present_factories,
)
from foms.services.orders.order_transition_service import TransitionError, transition_order
from foms.services.orders.revision import RevisionError, lock_order_row
from foms.services.orders.state_axes import read_main_stage
from foms.services.production.factory_constants import FACTORIES
from foms.services.production.factory_marks import clear_factory_marks, done_table
from foms.services.production.order_write_helpers import (
    _close_current_production_run,
    _enrich_production_completed_event,
    _hold_active,
    _hold_block_response,
    _idempotency_receipt_exists,
    _is_rework_completion,
    _punch_or_return,
    _release_hold_in_sd,
    _revising_block_response,
    _request_hash,
    _scope_hash,
    _stage_quest_block,
    _steps_incomplete_block,
    _transition_error_response,
)
from foms.services.production.part_access import account_production_factory, is_part_admin
from foms.services.production.part_mark_gates import DRAWING_REVISING
from foms.services.production.part_marks_query import order_marks
from foms.services.production.start_run import append_stage_history
from models import Order

#: 감사 한 줄을 쓰는 함수 ``(order, action, user_id, *, note=None, extra=None)`` — API 층 ``_audit_production``.
AuditFn = Callable[..., None]
POLICY_PRODUCTION_COMPLETE = "STATE_PRODUCTION_COMPLETE"
#: 공장 완료 · 완료 취소(마지막이 아닐 때)의 영수증 정책 칸 — 단계를 안 옮기는 주문 쓰기.
POLICY_FACTORY_DONE = "PRODUCTION_FACTORY_DONE"
FACTORY_COMPLETED_EVENT = "PRODUCTION_FACTORY_COMPLETED"
FACTORY_UNCOMPLETED_EVENT = "PRODUCTION_FACTORY_UNCOMPLETED"
COMPLETE_ROUTE = "erp_orders_production.api_production_complete"


def _apply_complete_side_effects(db: Any, order: Order, user: Any, user_id: Any, release_hold: bool,
                                 hold_was_active: bool, is_rework: bool, event_id: Any, *, audit: AuditFn) -> None:
    """PRODUCTION_COMPLETE 전이 후 same-tx side-effect: history·rework 해제·보류해제·event 보강·run 종결.

    섞인 주문(2공장, 설계서 2026-11-23 §4-14)은 아직 살아 있지 않은 공장 완료 표지를 누른 사람 이름으로 같은 deepcopy 에 쓴다
    (:func:`mark_remaining_factories` — 옛 [제작 완료] · 마지막 공장 완료 모두, 버전 +1 한 번). 한 공장 주문은 아무것도 안 쓴다.
    ``audit`` = 감사 한 줄을 쓰는 함수(API 층 ``_audit_production`` — 서비스가 웹 층을 부르지 않게 넘겨받는다).
    """
    sd = copy.deepcopy(_ensure_dict(order.structured_data))
    note = "제작 완료 (재제작)" if is_rework else "제작 완료 (시공/출고 대기)"
    append_stage_history(sd, "CONSTRUCTION", note, user)
    mark_remaining_factories(sd, user)
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
    audit(order, "PRODUCTION_COMPLETED", user_id,
                      extra={"is_rework": bool(is_rework), "new_stage": "CONSTRUCTION"})


# --------------------------------------------------------------------------- #
# 공장 완료 표지(§4-14) — 쓰기 · 지우기
# --------------------------------------------------------------------------- #
def factory_keys(sd: Any, factory: int) -> list[str]:
    """그 공장의 지금 확정 도면 key(도면 번호 순)."""
    return [entry["key"] for entry, f in current_factories(sd) if f == factory]


def write_factory_done(sd: dict[str, Any], factory: int, user: Any, *, at_iso: Optional[str] = None) -> dict[str, Any]:
    """표지 하나를 ``sd``(부르는 쪽 deepcopy)에 쓴다 — 그때 그 공장 지금 장 key · 때 · 누른 사람(이름 스냅샷 · id)."""
    entry = {"keys": factory_keys(sd, factory), "at": at_iso or datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "by_name": getattr(user, "name", None) or getattr(user, "username", None),
             "by_user_id": getattr(user, "id", None)}
    table = done_table(sd)
    table[str(factory)] = entry
    production = sd.get("production") if isinstance(sd.get("production"), dict) else {}
    production[FACTORY_DONE_KEY] = table
    sd["production"] = production
    return entry


def mark_remaining_factories(sd: dict[str, Any], user: Any) -> list[int]:
    """섞인 주문의 아직 살아 있지 않은 공장 표지를 모두 쓴다(옛 [제작 완료] · 마지막 공장 완료 — 같은 deepcopy). 한 공장 주문은 0.

    Returns:
        쓴 공장 번호들.
    """
    if not has_second_factory(sd):
        return []
    at_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    wrote = [f for f in present_factories(sd) if factory_done_entry(sd, f) is None]
    for factory in wrote:
        write_factory_done(sd, factory, user, at_iso=at_iso)
    return wrote


#: 옛 이름(공장 완료 본문이 읽는다) — 표 사본은 아래층 한 곳(:mod:`foms.services.production.factory_marks`).
_done_table = done_table


def uncomplete_factories(user: Any, sd: Any, requested: Any) -> Optional[tuple[int, ...]]:
    """완료 취소(시공 대기 → 생산)가 지울 표지 — 섞인 주문만(한 공장 주문은 None = 표지 없음).

    관리자는 고른 공장(몸 ``factories`` — 1 · 2 목록, 안 보내거나 틀리면 둘 다 — §19 여섯째 추천 기본), 그 밖은 누른 사람 공장만.
    """
    if not has_second_factory(sd):
        return None
    if is_part_admin(user):
        picked = tuple(f for f in FACTORIES if isinstance(requested, list) and f in requested)
        return picked or FACTORIES
    return (account_production_factory(user) or FACTORIES[0],)


def reopen_after_uncomplete(user: Any, sd: dict[str, Any], requested: Any) -> list[int]:
    """완료 취소(시공 대기 → 생산)가 공장 표지를 지운다 — 다시 열린 공장이 하나도 없으면 주문에 있는 공장을 모두 연다.

    누른 사람 공장(관리자는 고른 공장)만 지우는 게 기본이다(§19 여섯째). 그 공장 장이 주문에 없으면(예: 장이 모두 2공장인데 1공장
    계정이 누름) 아무것도 안 지워져 생산으로 돌아왔는데 모든 공장이 '완료'인 막다른 길이 된다 — 그때만 있는 공장 표지를 모두 지운다.

    Args:
        user: 누른 사람. sd: 부르는 쪽 deepcopy(제자리). requested: 몸 ``factories``(관리자만 뜻 있음).

    Returns:
        지운 공장 번호들(한 공장 주문은 빈 목록).
    """
    picked = uncomplete_factories(user, sd, requested)
    if picked is None:
        return []
    removed = clear_factory_marks(sd, picked)
    present = present_factories(sd)
    if present and all(factory_done_entry(sd, f) is not None for f in present):
        removed += [f for f in clear_factory_marks(sd, present) if f not in removed]
    return removed


# --------------------------------------------------------------------------- #
# [제작 완료] 본문(orders.api_production_complete 에서 옮김)
# --------------------------------------------------------------------------- #
def complete_production(db: Any, order_id: int, user: Any, user_id: Any, body: dict[str, Any], idem_key: Optional[str],
                        *, audit: AuditFn, route: str = COMPLETE_ROUTE) -> Any:
    """제작 완료 (제작중/PRODUCTION → CONSTRUCTION), transition_order(PRODUCTION_COMPLETE) 경유 — 응답 튜플을 돌려준다.

    게이트 순서 · 글 · 응답 꼴은 옮기기 전 ``api_production_complete`` 그대로: 존재(404) → 제작중 stage(INVALID_STAGE 409) →
    보류(HOLD_ACTIVE 409, release_hold 예외) → 도면 고치는 중(DRAWING_REVISING 409 — 사장님 2026-11-25 "제작 완료도 막기", 보류와
    같은 자리 · 같은 꼴 · 관리자 뚫기도 같다) → 현재 stage quest 완료(QUEST_INCOMPLETE 409) → **검수까지 끝남**(STEPS_INCOMPLETE
    409 — 판정 = :func:`complete_block_body` 한 곳, 카드를 쓴 주문은 표시 줄로). ADMIN ``admin_override``(사유)로 게이트 뚫기.
    same-key 재요청은 전이/side-effect 없이 replay. 섞인 주문은 남은 공장 표지를 누른 사람 이름으로 모두 쓴다(곁일).
    """
    try:
        # 첫 조회부터 행 잠금 — 카드 쓰기(같은 행을 잠근다)와 줄 세워 표시 줄 판정이 낡지 않게(§4-3).
        order = lock_order_row(db, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없어요."}), 404
        release_hold = body.get("release_hold") is True
        err = admin_override_error(user, body)
        if err is not None:
            log_admin_override_denied(db, order_id=order_id, gate=err[0].get_json().get("code"), route=route, user=user)
            return err
        override = resolve_admin_override(user, body)
        punched: list = []
        sd = _ensure_dict(order.structured_data)
        hold_was_active = _hold_active(sd)[0]
        is_rework = _is_rework_completion(sd)
        from_stage = read_main_stage(order)
        if not _idempotency_receipt_exists(db, user_id, POLICY_PRODUCTION_COMPLETE, idem_key):
            blocked = _complete_gates(db, order, sd, release_hold, override, punched)
            if blocked is not None:
                return blocked
        try:
            result = _transition_complete(db, order_id, user_id, from_stage, body, idem_key, override)
        except (TransitionError, RevisionError) as exc:
            db.rollback()
            return _transition_error_response(exc)
        if not result.replayed:
            _apply_complete_side_effects(db, order, user, user_id, release_hold, hold_was_active, is_rework,
                                         result.event_id, audit=audit)
        if override is not None and punched:
            record_admin_override_event(db, order, override=override, gates=punched, route=route, axis="MAIN",
                                        from_value=from_stage, to_value="CONSTRUCTION")
        db.commit()
        return jsonify({"success": True, "message": "제작이 완료됐어요. (시공 대기로 바뀜)", "new_status": "CONSTRUCTION"})
    except Exception as exc:  # noqa: BLE001 - 최종 방어(구체 전이 예외는 위에서 매핑)
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


def _complete_gates(db: Any, order: Order, sd: dict[str, Any], release_hold: bool, override: Any, punched: list) -> Any:
    """[제작 완료] 업무 게이트 다섯(단계 · 보류 · 도면 고치는 중 · 승인 · 검수까지) — 막히면 응답 튜플, 지나면 None(관리자 뚫기는
    ``punched`` 에). 도면 고치는 중은 보류 바로 뒤(도면 한 장 누름 ``order_gate`` 와 같은 차례) — ``release_hold`` 여도 막히면 보류를
    풀지 않는다(아무것도 안 씀)."""
    if order.erp_stage_code not in ("생산", "PRODUCTION"):
        if override is None:
            return jsonify({"success": False, "code": "INVALID_STAGE",
                            "message": "제작 중일 때만 제작을 완료할 수 있어요."}), 409
        punched.append("INVALID_STAGE")
    blocked = _punch_or_return(_hold_block_response(sd, release_hold), "HOLD_ACTIVE", override, punched)
    if blocked is not None:
        return blocked
    blocked = _punch_or_return(_revising_block_response(sd), DRAWING_REVISING, override, punched)
    if blocked is not None:
        return blocked
    blocked = _punch_or_return(_stage_quest_block(sd, "PRODUCTION", "생산"), "QUEST_INCOMPLETE", override, punched)
    if blocked is not None:
        return blocked
    marks = order_marks(db, order.id)  # 카드를 쓴 주문은 표시 줄로(§4-3, +1)
    return _punch_or_return(_steps_incomplete_block(sd, marks), GATE_STEPS_INCOMPLETE, override, punched)


def _transition_complete(db: Any, order_id: int, user_id: Any, from_stage: Any, body: dict[str, Any],
                         idem_key: Optional[str], override: Any) -> Any:
    """전이 엔진 한 번(PRODUCTION_COMPLETE) — 잠금 아래 expected_from 재확인 · 버전 +1 · 영수증 · 이벤트."""
    return transition_order(
        db, command_id="PRODUCTION_COMPLETE", order_id=order_id,
        actor_user_id=user_id, expected_from=from_stage, target_value="CONSTRUCTION",
        scope_hash=_scope_hash("PRODUCTION_COMPLETE", order_id),
        request_hash=_request_hash(body), idempotency_key=idem_key,
        emergency_override=bool(override),
        reason=(override.reason if override is not None else None),
    )

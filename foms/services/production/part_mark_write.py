"""생산 파트 표시 쓰기 몸통 — 한 장 · 재단 일괄 기본(설계서 §15.4 · 2026-11-23 §4-5 ~ §4-8).

API(``foms/api/production/part_marks.py``)는 로그인 · 파트 문 · 몸 읽기 · tx 만 하고 여기를 부른다(500줄 래칫).

한 장 순서(한 tx): 주문 행 잠금(``FOR UPDATE`` — 같은 주문 표시 쓰기 · 공정 칸 API · 제작 완료를 줄 세운다) → 살아 있는 ERP
주문 · 생산 단계(아니면 409 ``NOT_IN_PRODUCTION``) → 지금 확정 도면 안의 key(아니면 409 ``DRAWING_NOT_CURRENT``) → 그 주문
**네 파트** 표시 줄 읽기(쿼리 1 — 검수 순서 · 손 체크 판정 · 완료 물음이 같은 줄을 쓴다) → 전이 표
(:mod:`~foms.services.production.part_mark_rules`) · 막는 까닭(:mod:`~foms.services.production.part_mark_gates`) → 줄 쓰기 +
이벤트 ``PRODUCTION_PART_MARKED`` → 주문 쓰기 한 번(누른 파트 공정 칸 동기화 + 첫 카드면 제작 시작) → 감사 한 줄.

표시는 주문 JSON 밖 표라 표시만으로는 주문 ``mutation_version`` 을 올리지 않는다. 공정 칸이 바뀌거나 제작이 시작될 때만
``execute_order_mutation`` 한 번으로 쓰고 버전이 1 오른다(일괄은 바뀐 주문을 모아 한 번).
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy import insert, update
from sqlalchemy.orm.attributes import flag_modified

from foms.services.audit_message_display import action_label, describe_order_action
from foms.services.datetime_kst import now_utc_naive
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.drawing_fix import complete_blocked, factory_complete_blocked
from foms.services.orders.revision import execute_order_mutation, lock_order_row
from foms.services.orders.state_axes import read_main_stage
from foms.services.orders.drawing_factory import factory_done_entry, has_second_factory, present_factories, sheet_factory
from foms.services.production.factory_home import factory_ready
from foms.services.production.factory_scope import factory_gate
from foms.services.production.part_access import is_part_admin
from foms.services.production.part_constants import (
    BASIC_ALLOWED_PART,
    MARK_STATE_DONE,
    MARK_STATE_NONE,
    PART_INSPECT,
    PRODUCTION_PART_LABELS,
)
from foms.services.production.part_mark_decide import decide_mark
from foms.services.production.part_mark_gates import Gate, hand_step_gate, inspect_gate, order_gate
from foms.services.production.part_mark_notes import actor_name, event_payload, mark_note
from foms.services.production.part_mark_rules import (
    ACTION_BASIC,
    ACTION_CHECK,
    ACTION_JOIN,
    ACTION_TAKE,
    ACTION_TAKEOVER,
    DECISION_APPLY,
    DECISION_CONFLICT,
    DECISION_FORBIDDEN,
    DECISION_INVALID,
    DECISION_SAME,
    SEEN_BY_UNSET,
    TARGET_GONE,
    MarkDecision,
    MarkSnapshot,
    mark_payload,
    next_mark_values,
    target_gone_message,
)
from foms.services.production.part_marks_query import order_marks, orders_with_current_run
from foms.services.production.part_progress import complete_state
from foms.services.production.part_steps_sync import (
    apply_part_step_changes,
    plan_part_step_changes,
    step_change_body,
    step_event_rows,
)
from foms.services.production.start_run import (
    CARD_START_NOTE,
    PRODUCTION_START_POLICY_ID,
    VIA_PART_MARKS,
    card_start_audit_values,
    new_run_values,
    record_start_in_sd,
    started_event_values,
)
from foms.services.production.write_access import can_write_production
from models import Order, OrderEvent, ProductionPartMark, ProductionRun, SecurityLog, User

PART_MARK_EVENT = "PRODUCTION_PART_MARKED"
#: 공정 칸 동기화의 정책 id — 지금 공정 API(``POST …/production/steps``)와 같다(설계서 §15.5).
STEP_SYNC_POLICY_ID = "PRODUCTION_STEP_CHECK"
#: 첫 카드로 제작이 시작되는 누름(§4-8 — 작업 시작 · 기본 · 담당 바꾸기 · 일괄 기본 + 같이 작업 · PC [완료 처리], multi-holder §5).
STARTING_ACTIONS: tuple[str, ...] = (ACTION_TAKE, ACTION_BASIC, ACTION_TAKEOVER, ACTION_JOIN, ACTION_CHECK)
NOT_CURRENT_MESSAGE = "도면이 바뀌었어요. [다시 받기]를 눌러 주세요."
NOT_IN_PRODUCTION_MESSAGE = "생산 단계 주문이 아니에요. [다시 받기]를 눌러 주세요."
NOT_FOUND_MESSAGE = "주문을 찾을 수 없어요."


class MarkRefusal(Exception):
    """요청을 거절하는 까닭(상태 · 코드 · 글 · 자료) — API 가 응답으로 바꾼다."""

    def __init__(self, status: int, code: str, message: str, extra: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}

    @classmethod
    def from_gate(cls, gate: Gate, extra: Optional[dict[str, Any]] = None) -> "MarkRefusal":
        """막는 까닭(:class:`Gate`) → 거절."""
        return cls(gate.status, gate.code, gate.message, {**gate.extra, **(extra or {})})


@dataclass(frozen=True)
class MarkRequest:
    """한 장 누름 — 주문 · 장 · 파트 · 누름 · 본 상태 · 본 담당(안 보냈으면 :data:`SEEN_BY_UNSET`) · 본 내 몫 · 대상."""

    order_id: int
    key: str
    part: str
    action: str
    seen: str
    seen_by: Any = SEEN_BY_UNSET
    seen_me: Optional[str] = None
    target_uid: Optional[int] = None


@dataclass(frozen=True)
class MarkWrite:
    """쓸 표시 한 장 — 새 칸 값 · 이벤트 한 줄 · 바뀌기 전 모습(``row_id`` 가 없으면 새 줄)."""

    row_id: Optional[int]
    values: dict[str, Any]
    event: dict[str, Any]
    before: MarkSnapshot

    @property
    def view(self) -> Any:
        """응답 자료용 줄 모습(``mark_payload`` 가 읽는다)."""
        return SimpleNamespace(**self.values)


def check_order(order: Optional[Order]) -> Order:
    """잠근 주문이 살아 있는 ERP 주문이고 생산 단계인지(아니면 404 · 409)."""
    if order is None or order.status == "DELETED" or order.deleted_at is not None or not order.is_erp_order:
        raise MarkRefusal(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
    if read_main_stage(order) != "PRODUCTION":
        raise MarkRefusal(409, "NOT_IN_PRODUCTION", NOT_IN_PRODUCTION_MESSAGE)
    return order


def current_entry(order: Order, key: str) -> dict[str, Any]:
    """지금 확정 도면 안의 그 장(없으면 409 — 교체된 옛 key 거나 빠진 장)."""
    entry = next((e for e in resolve_final_drawing_files(order.structured_data) if e["key"] == key), None)
    if entry is None:
        raise MarkRefusal(409, "DRAWING_NOT_CURRENT", NOT_CURRENT_MESSAGE)
    return entry


def plan_write(order: Order, entry: dict[str, Any], row: Optional[ProductionPartMark], *, part: str, target: str,
               user: Any, action: str, override: bool, decision: Optional[MarkDecision] = None,
               now: Optional[datetime.datetime] = None) -> MarkWrite:
    """표시 한 장의 새 값과 이벤트 ``PRODUCTION_PART_MARKED`` 를 만든다(쓰지는 않는다). ``decision`` = 판정의 새 목록 · 대상
    (없으면 풀어 쓰기 · 일괄 기본 — :func:`~foms.services.production.part_mark_rules.default_crew`)."""
    now = now or now_utc_naive()
    before = MarkSnapshot.from_row(row)
    values = next_mark_values(row, order_id=int(order.id), drawing_key=entry["key"], part=part,
                              sheet_id=entry.get("sheet_id"), target=target, actor_id=user.id,
                              actor_name=actor_name(user), now=now, action=action, decision=decision)
    event = {"order_id": int(order.id), "event_type": PART_MARK_EVENT, "created_by_user_id": user.id, "created_at": now,
             "payload": event_payload(entry, before, part=part, target=target, user=user, action=action,
                                      override=override, decision=decision, crew_after=values["holders"])}
    return MarkWrite(row.id if row is not None else None, values, event, before)


def flush_writes(db: Any, writes: list[MarkWrite]) -> None:
    """표시 줄 · 이벤트를 **표마다 한 번에** 쓴다 — 장이 5장이든 50장이든 문 수가 같다(쿼리 수 계약).

    두 표 모두 테이블 버전 카운터 대상(``VERSIONED_TABLES``) 밖이라 세션 훅을 거치지 않아도 신호가 빠지지 않는다.
    """
    inserts = [w.values for w in writes if w.row_id is None]
    updates = [{"id": w.row_id, **w.values} for w in writes if w.row_id is not None]
    if inserts:
        db.execute(insert(ProductionPartMark), inserts)
    if updates:
        db.execute(update(ProductionPartMark), updates)
    if writes:
        db.execute(insert(OrderEvent), [w.event for w in writes])


def write_audit(db: Any, user: Any, note: str, detail: dict[str, Any], order: Optional[Order] = None,
                order_count: int = 0) -> None:
    """감사 1행 — 요청 하나에 한 줄(같은 tx, '생산 파트 체크'). 일괄이 여러 주문이면 주문 수를 적는다."""
    if order is not None:
        context = order_audit_context(order)
        message = describe_order_action(order_id=order.id, action=PART_MARK_EVENT, note=note, **context)
        target_id: Optional[int] = int(order.id)
    else:
        context, target_id = {}, None
        message = f"주문 {order_count}건 — {action_label(PART_MARK_EVENT)}: {note}"
    db.add(SecurityLog(user_id=user.id, action=PART_MARK_EVENT, target_type="order", target_id=target_id,
                       message=message, detail={**detail, **context}))


def after_views(rows: list[Any], writes: list[MarkWrite]) -> dict[int, list[Any]]:
    """주문 → 이번 쓰기를 반영한 표시 줄 모습(읽은 줄 위에 새 값을 덮는다 — 다시 읽지 않는다)."""
    views: dict[tuple[int, str, str], Any] = {
        (int(r.order_id), str(r.drawing_key), str(r.part)): r for r in rows}
    for w in writes:
        views[(int(w.values["order_id"]), str(w.values["drawing_key"]), str(w.values["part"]))] = w.view
    out: dict[int, list[Any]] = {}
    for (order_id, _key, _part), view in views.items():
        out.setdefault(order_id, []).append(view)
    return out


def step_note(changes: list[dict[str, Any]]) -> str:
    """감사 글 꼬리 — " · 공정 재단 켬"(바뀐 칸이 없으면 빈 글)."""
    words = [f"{PRODUCTION_PART_LABELS.get(c['key'], c['key'])} {'켬' if c['done'] else '끔'}" for c in changes]
    return f" · 공정 {', '.join(words)}" if words else ""


def apply_order_changes(db: Any, orders: list[Order], marks: dict[int, list[Any]], user: Any, *,
                        parts: tuple[str, ...], starting: set[int],
                        cleared: tuple[str, ...] = ()) -> tuple[list[dict[str, Any]], list[int]]:
    """표시가 바뀐 주문들의 주문 쓰기 — 누른 파트 공정 칸 동기화(§15.5, 카드를 쓴 파트만) + 첫 카드 제작 시작(§4-8).

    바꿀 칸도 시작할 주문도 없으면 쿼리 0 · 버전 그대로. 있으면 ``execute_order_mutation`` **한 번**(주문마다 버전 +1 한 번) —
    제작이 시작되는 주문이 있으면 정책 ``STATE_PRODUCTION_START``, 없으면 공정 API 와 같은 ``PRODUCTION_STEP_CHECK``.

    Args:
        db: 세션(같은 tx — 주문들은 이미 잠겨 있다).
        orders: 표시가 바뀐 주문.
        marks: 주문 → 이번 쓰기를 반영한 표시 줄 모습.
        user: 누른 사람(켜면 칸 ``by_name`` = 그 파트에서 마지막으로 끝낸 사람).
        parts: 동기화할 파트(누른 파트).
        starting: 제작을 시작할 주문 id(잠금 아래에서 회차가 없음을 확인한 것).
        cleared: 완료 줄이 미정이 된 파트(:func:`~foms.services.production.part_steps_sync.part_steps_after`).

    Returns:
        (바뀐 공정 칸 ``[{order_id, key, done}]``, 제작이 시작된 주문 id).
    """
    changed = sorted({int(o.id) for o in orders if int(o.id) in starting
                      or plan_part_step_changes(o.structured_data, marks.get(int(o.id), []), parts, cleared)})
    if not changed:
        return [], []
    out: list[dict[str, Any]] = []
    started: list[int] = []

    def _mutate(sess: Any, locked: list[Order]) -> dict[int, list[str]]:
        at_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        events: list[dict[str, Any]] = []
        runs: list[dict[str, Any]] = []
        audits: list[dict[str, Any]] = []
        for order in locked:
            oid = int(order.id)
            sd = copy.deepcopy(order.structured_data if isinstance(order.structured_data, dict) else {})
            changes = plan_part_step_changes(sd, marks.get(oid, []), parts, cleared)
            apply_part_step_changes(sd, changes, at_iso=at_iso)
            events += step_event_rows(oid, changes, actor_user_id=user.id, actor_name=actor_name(user))
            out.extend(step_change_body(oid, c) for c in changes)
            if oid in starting:  # 잠금 아래에서 회차가 없음을 이미 확인했다(겹쳐도 부분 유일 색인이 막는다)
                record_start_in_sd(order, sd, user, note=CARD_START_NOTE)
                runs.append(new_run_values(oid, sd))
                events.append(started_event_values(oid, user.id, via=VIA_PART_MARKS))
                audits.append(card_start_audit_values(order, user))
                started.append(oid)
            else:
                order.structured_data = sd
                flag_modified(order, "structured_data")
        for table, rows in ((ProductionRun, runs), (OrderEvent, events), (SecurityLog, audits)):
            if rows:  # 표마다 INSERT 한 번(주문 수와 무관)
                sess.execute(insert(table), rows)
        return {int(o.id): ["ORDERS_INDEX", f"ORDER_DETAIL:{o.id}"] for o in locked}

    policy = PRODUCTION_START_POLICY_ID if starting else STEP_SYNC_POLICY_ID
    scope = hashlib.sha256(f"{policy}:part_marks:{changed}".encode("utf-8")).hexdigest()
    body = json.dumps({"orders": changed, "user": user.id, "start": sorted(starting)}, sort_keys=True)
    execute_order_mutation(db, actor_user_id=user.id, policy_id=policy, order_ids=changed, scope_hash=scope,
                           request_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(), mutation=_mutate)
    return out, started


def mark_body(row: Any, order_id: int, key: str, part: str) -> dict[str, Any]:
    """응답 표시 한 장(``mark_payload`` + 자리)."""
    return {**mark_payload(row), "order_id": order_id, "drawing_key": key, "part": part}


def _hold_active(sd: Any) -> bool:
    production = sd.get("production") if isinstance(sd, dict) else None
    hold = production.get("hold") if isinstance(production, dict) else None
    return bool(isinstance(hold, dict) and hold.get("active"))


def _complete_blocked(sd: Any) -> bool:
    """제작 완료가 막힌 주문 — 보류 · 도면 고치는 중(사장님 2026-11-25 "제작 완료도 막기", 제작 완료 API 와 같은 판정).

    도면 고치는 중 = 주문 통째 또는 막힌 도면이 하나라도(2026-11-25 설계서 §4-3 — [제작 완료] 와 같은 판정).
    """
    return _hold_active(sd) or complete_blocked(sd)


def _factory_complete_blocked(sd: Any, entry: dict[str, Any]) -> bool:
    """그 장 공장의 [N공장 완료]가 막힌 주문 — 보류 · 그 공장에 막힌 도면 · 마지막 공장이면 [제작 완료] 판정(공장 완료 API 와 같다)."""
    factory = sheet_factory(sd, entry)
    final = all(factory_done_entry(sd, f) is not None for f in present_factories(sd) if f != factory)
    return _hold_active(sd) or factory_complete_blocked(sd, factory, final=final)


def order_ready(order: Order, views: list[Any], user: Any, req: MarkRequest, target: Optional[str]) -> Optional[dict]:
    """검수 카드를 완료한 뒤 "제작 완료할까요?"를 물을지(§4-4 한 공장 주문) — 쿼리 0(읽은 줄 · 잠근 주문).

    검수 완료 쓰기 · 완료 판정 참 · 생산 단계 · 보류 · 도면 고치는 중 아님 · 누른 사람이 생산 쓰기 가능일 때만 ``{order_id}``.
    """
    if req.part != PART_INSPECT or target != MARK_STATE_DONE:
        return None
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    if read_main_stage(order) != "PRODUCTION" or _complete_blocked(sd) or not can_write_production(user):
        return None
    if has_second_factory(sd):  # 섞인 주문은 공장마다 묻는다(factory_ready, 2026-11-23 §4-4 · §4-14)
        return None
    return {"order_id": int(order.id)} if complete_state(sd, views)["ready"] else None


def _factory_ready(order: Order, entry: dict[str, Any], views: list[Any], user: Any, req: MarkRequest,
                   target: Optional[str]) -> Optional[dict]:
    """섞인 주문의 "2공장 제작 완료할까요?"(:func:`~foms.services.production.factory_home.factory_ready`) — 쿼리 0."""
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    return factory_ready(sd, entry, views, user, order_id=int(order.id), part=req.part, target=target,
                         stage=read_main_stage(order), hold=_factory_complete_blocked(sd, entry))  # 보류 · 도면 고치는 중이면 묻지 않는다


def _note(req: MarkRequest, write: MarkWrite, decision: MarkDecision, user: Any) -> str:
    """감사 글(:func:`~foms.services.production.part_mark_notes.mark_note`) — 덮어쓰기 꼬리는 관리자 "(관리자 덮어쓰기)",
    대신(반장, 2026-11-23 §4-12 · 승인 때 고친 것 5)은 "(대신 처리)"."""
    return mark_note(req.part, decision.action or req.action, write.before, decision.target, write.values["holders"],
                     user=user, override=decision.override, admin_tail=is_part_admin(user), decision=decision)


def _refusal(db: Any, decision: MarkDecision, server_mark: dict[str, Any]) -> MarkRefusal:
    """판정 거절 → 응답 거절. 고른 사람이 빠졌으면(``TARGET_GONE``) 그 이름을 사용자 표에서 한 번 읽는다(거절 길만 +1)."""
    if decision.kind == DECISION_CONFLICT:
        return MarkRefusal(409, "MARK_CONFLICT", decision.message, server_mark)
    if decision.kind == DECISION_FORBIDDEN:
        return MarkRefusal(403, decision.code, decision.message)
    message = decision.message
    if decision.code == TARGET_GONE and decision.target_uid is not None:
        gone = db.get(User, decision.target_uid)
        message = target_gone_message(actor_name(gone) or "") if gone is not None else message
    return MarkRefusal(decision.status, decision.code, message, server_mark)


def _decide(db: Any, req: MarkRequest, order: Order, entry: dict[str, Any], rows: list[Any], row: Any, user: Any,
            admin: bool, now: datetime.datetime) -> MarkDecision:
    """전이 표 + 막는 까닭(§4-6 · multi-holder §7-3) — apply · same(멱등) 결정을 돌려주고, 막히면 :class:`MarkRefusal` 로 거절한다.

    순서: 잘못된 짝(400) → 멱등(막힘 안 봄) → 넘김(take → join · join → take) → 남의 공장 장(403 ``OTHER_FACTORY``) → 보류 ·
    도면 고치는 중 · 손 체크 칸(409) → 경합(409, ``JOIN_DONE`` · ``TARGET_GONE``) · 권한(403) · 새 거절 → 검수 순서(409).
    막는 까닭은 넘김 뒤 누름으로 본다(넘어온 join 도 take 와 같은 막힘). 경합 · 막힘 응답에는 서버의 지금 표시(``mark``)를 싣는다.
    """
    sd = order.structured_data
    decision = decide_mark(MarkSnapshot.from_row(row), action=req.action, seen=req.seen, actor_id=user.id, admin=admin,
                           seen_by=req.seen_by, seen_me=req.seen_me, target_uid=req.target_uid,
                           actor_name=actor_name(user), now=now, label=PRODUCTION_PART_LABELS[req.part])
    if decision.kind == DECISION_INVALID:
        raise MarkRefusal(400, "BAD_REQUEST", decision.message)
    if decision.kind == DECISION_SAME:
        return decision  # 같은 사람 · 같은 결과(멱등) — 막힘을 보지 않고 그대로 성공
    action = decision.action or req.action
    server_mark = {"mark": mark_body(row, req.order_id, req.key, req.part)}
    gate = (factory_gate(user, sd, entry, action=action, row=row) or order_gate(sd, action, entry)
            or hand_step_gate(sd, rows, req.part))
    if gate is not None:
        raise MarkRefusal.from_gate(gate, server_mark)
    if decision.kind != DECISION_APPLY:
        raise _refusal(db, decision, server_mark)
    gate = inspect_gate(sd, rows, req.key, req.part, action, undo_basic=req.seen == "basic")
    if gate is not None:
        raise MarkRefusal.from_gate(gate, server_mark)
    return decision


def mark_one(db: Any, user: Any, admin: bool, req: MarkRequest) -> dict[str, Any]:
    """잠금 → 주문 · 도면 검사 → 전이 표 · 막는 까닭 → 쓰기 → 주문 쓰기 → 감사. 커밋 전 응답 자료를 돌려준다.

    Returns:
        ``{mark, order_step, changed, run_started, order_ready, factory_ready, joined_late, notice, proxied}`` — 바뀐 게
        없으면(멱등) ``changed`` False. 섞인 주문(2공장)은 ``order_ready`` 대신 ``factory_ready``(그 장 공장의 마지막 검수 장일 때 —
        줄이 DONE 이 된 누름만, 검수 1/2 완료면 안 묻는다). ``joined_late`` · ``notice`` = 늦은 [작업 시작]이 같이 작업으로 넘어감(Q16
        "{이름}이 먼저 시작했어요."), ``proxied`` = PC [완료 처리]가 대신 완료로 감(판결 2).
    """
    order = check_order(lock_order_row(db, req.order_id))
    entry = current_entry(order, req.key)
    rows = order_marks(db, req.order_id)  # 네 파트 한 번(검수 순서 · 손 체크 · 완료 물음 — 쿼리 수는 그대로 1)
    row = next((r for r in rows if r.drawing_key == req.key and r.part == req.part), None)
    now = now_utc_naive()
    decision = _decide(db, req, order, entry, rows, row, user, admin, now)
    extra = {"joined_late": decision.joined_late, "notice": decision.notice or None, "proxied": decision.proxied}
    if decision.kind != DECISION_APPLY:
        return {"mark": mark_body(row, req.order_id, req.key, req.part), "order_step": None, "changed": False,
                "run_started": False, "order_ready": order_ready(order, rows, user, req, decision.target),
                "factory_ready": _factory_ready(order, entry, rows, user, req, decision.target), **extra}
    action = decision.action or req.action
    write = plan_write(order, entry, row, part=req.part, target=decision.target, user=user, action=action,
                       override=decision.override, decision=decision, now=now)
    flush_writes(db, [write])
    starting = set()
    if action in STARTING_ACTIONS and decision.target != MARK_STATE_NONE:
        starting = {req.order_id} - orders_with_current_run(db, [req.order_id])  # 잠금 아래 — 회차 찾기 +1
    views = after_views(rows, [write])
    cleared = (req.part,) if write.before.state == MARK_STATE_DONE and decision.target == MARK_STATE_NONE else ()  # 바로 완료 취소
    steps, started = apply_order_changes(db, [order], views, user, parts=(req.part,), starting=starting, cleared=cleared)
    write_audit(db, user, _note(req, write, decision, user) + step_note(steps) + (" · 제작 시작" if started else ""),
                {"key": req.key, "part": req.part, "action": action, "from": write.before.state,
                 "to": decision.target, "override": decision.override, "order_steps": steps,
                 "run_started": bool(started), "joined_late": decision.joined_late}, order=order)
    return {"mark": mark_body(write.view, req.order_id, req.key, req.part), "order_step": steps[0] if steps else None,
            "changed": True, "run_started": bool(started),
            "order_ready": order_ready(order, views.get(req.order_id, []), user, req, decision.target),
            "factory_ready": _factory_ready(order, entry, views.get(req.order_id, []), user, req, decision.target), **extra}


def lock_orders(db: Any, order_ids: list[int]) -> dict[int, Order]:
    """주문들을 id 순으로 한 번에 잠근다(교착 없는 순서 — ``execute_order_mutation`` 과 같은 규칙)."""
    rows = (db.query(Order).filter(Order.id.in_(sorted(set(order_ids)))).order_by(Order.id.asc())
            .populate_existing().with_for_update().all())
    return {int(o.id): o for o in rows}


def _bulk_one(user: Any, admin: bool, order: Optional[Order], key: str, row: Any,
              cut_rows: list[Any]) -> Optional[MarkWrite]:
    """일괄의 장 하나 — 한 장 쓰기와 같은 검사(남의 공장 · 보류 · 도면 고치는 중 · 손 체크 포함). → 쓸 것(이미 내가 기본이면 None).

    Raises:
        MarkRefusal: 이 장만 건너뛸 까닭(``reason`` = 코드).
    """
    order = check_order(order)
    entry = current_entry(order, key)
    decision = decide_mark(MarkSnapshot.from_row(row), action=ACTION_BASIC, seen="none", actor_id=user.id, admin=admin,
                           actor_name=actor_name(user))
    if decision.kind not in (DECISION_APPLY, DECISION_CONFLICT):
        return None
    gate = (factory_gate(user, order.structured_data, entry, action=ACTION_BASIC)
            or order_gate(order.structured_data, ACTION_BASIC, entry)
            or hand_step_gate(order.structured_data, cut_rows, BASIC_ALLOWED_PART))
    if gate is not None:
        raise MarkRefusal.from_gate(gate)
    if decision.kind == DECISION_CONFLICT:
        raise MarkRefusal(409, "MARK_CONFLICT", decision.message)
    return plan_write(order, entry, row, part=BASIC_ALLOWED_PART, target=decision.target, user=user,
                      action=ACTION_BASIC, override=False, decision=decision)


def bulk_basic(db: Any, user: Any, admin: bool, pairs: list[tuple[int, str]]) -> dict[str, Any]:
    """보낸 목록만 기본으로(일부 성공). 주문 잠금 · 표시 줄 읽기 · 회차 찾기 · 감사는 요청마다 한 번씩(장 수와 무관)."""
    orders = lock_orders(db, [oid for oid, _ in pairs])
    rows = (db.query(ProductionPartMark)
            .filter(ProductionPartMark.order_id.in_(sorted(orders)), ProductionPartMark.part == BASIC_ALLOWED_PART)
            .all()) if orders else []
    marks = {(int(m.order_id), str(m.drawing_key)): m for m in rows}
    by_order = after_views(rows, [])
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    writes: list[MarkWrite] = []
    changed: dict[int, list[str]] = {}
    for order_id, key in pairs:
        row = marks.get((order_id, key))
        try:
            write = _bulk_one(user, admin, orders.get(order_id), key, row, by_order.get(order_id, []))
        except MarkRefusal as refusal:
            skipped.append({"order_id": order_id, "drawing_key": key, "reason": refusal.code, "error": refusal.message,
                            "mark": mark_body(row, order_id, key, BASIC_ALLOWED_PART)})
            continue
        if write is not None:
            writes.append(write)
            changed.setdefault(order_id, []).append(key)
        view = write.view if write is not None else row
        applied.append({**mark_body(view, order_id, key, BASIC_ALLOWED_PART), "changed": write is not None})
    if not writes:
        return {"applied": applied, "skipped": skipped, "order_steps": [], "run_started": []}
    flush_writes(db, writes)
    starting = set(changed) - orders_with_current_run(db, list(changed))
    steps, started = apply_order_changes(db, [orders[oid] for oid in changed], after_views(rows, writes), user,
                                         parts=(BASIC_ALLOWED_PART,), starting=starting)
    only = orders[next(iter(changed))] if len(changed) == 1 else None
    start_tail = f" · 제작 시작 {len(started)}건" if started else ""
    write_audit(db, user, f"재단 기본 {len(writes)}장" + step_note(steps) + start_tail,
                {"part": BASIC_ALLOWED_PART, "to": "BASIC", "bulk": True, "order_steps": steps, "run_started": started,
                 "orders": [{"order_id": oid, "keys": keys} for oid, keys in changed.items()]},
                order=only, order_count=len(changed))
    return {"applied": applied, "skipped": skipped, "order_steps": steps, "run_started": started}

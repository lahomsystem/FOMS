"""생산 파트 표시 쓰기 API — 도면 카드의 맡기 · 기본 · 완료 · 되돌리기(설계서 §15.4, P15-4).

* ``POST /api/production/part-marks`` — 한 장. 몸 ``{order_id, drawing_key, part, action, seen}``.
* ``POST /api/production/part-marks/basic`` — 재단 [남은 N장 모두 기본]. 몸 ``{part:'cut', seen:'none', items:[{order_id,
  drawing_key}…]}``(최대 200). **화면이 보낸 목록만** 바꾼다(서버가 '남은 전부'를 고르지 않는다) · 일부 성공.

순서(한 tx): 로그인 → 파트 문(:mod:`foms.services.production.part_access`) → 주문 행 잠금(``FOR UPDATE`` — 같은 주문 표시
쓰기를 줄 세운다, 주문 행은 바꾸지 않는다) → 살아 있는 ERP 주문 · 단계 생산(아니면 409 ``NOT_IN_PRODUCTION``) → 지금 확정
도면 안의 key(아니면 409 ``DRAWING_NOT_CURRENT``) → 표시 줄 읽기 → 전이 표(:mod:`foms.services.production.part_mark_rules`)
→ 줄 쓰기 + 이벤트 ``PRODUCTION_PART_MARKED`` → 공정 칸 동기화(§15.5, P15-6) → 감사 "생산 파트 체크" → commit.

표시는 주문 JSON 밖 표(``production_part_marks``)라 표시만으로는 주문 ``mutation_version`` 을 올리지 않는다(편집 화면 ·
마법사 · 도면 전달의 If-Match 를 깨지 않는다). 동기화가 공정 칸을 **바꿀 때만** ``execute_order_mutation`` 한 번으로
칸 · 이벤트 ``PRODUCTION_STEP_CHECKED``(``via: 'part_marks'``)를 쓰고 버전이 1 오른다(일괄은 바뀐 주문만 모아 한 번). CSRF · 정책 가드는 다른 생산 API 와 같이 before_request(매니페스트 두 곳)가 건다.
API 층은 웹 층을 부르지 않는다(레이어 래칫) — 로그인은 ``g.current_user``, 감사는 ``SecurityLog`` 를 같은 세션에 싣는다.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy import insert, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from foms.services.audit_message_display import action_label, describe_order_action
from foms.services.datetime_kst import now_utc_naive
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.revision import RevisionError, execute_order_mutation, lock_order_row
from foms.services.orders.state_axes import read_main_stage
from foms.services.production.part_access import VIEW_ADMIN, VIEW_PART, part_account_part, part_view_mode
from foms.services.production.part_constants import BASIC_ALLOWED_PART, PRODUCTION_PART_KEYS, PRODUCTION_PART_LABELS
from foms.services.production.part_mark_rules import (
    ACTION_BASIC,
    DECISION_APPLY,
    DECISION_CONFLICT,
    DECISION_INVALID,
    MARK_ACTIONS,
    SEEN_VALUES,
    STALE_MESSAGE,
    MarkSnapshot,
    decide_mark,
    mark_payload,
    next_mark_values,
)
from foms.services.production.part_steps_sync import (
    apply_part_step_changes,
    plan_part_step_changes,
    step_change_body,
    step_event_rows,
)
from models import Order, OrderEvent, ProductionPartMark, SecurityLog

production_part_marks_bp = Blueprint("production_part_marks", __name__, url_prefix="/api/production")

PART_MARK_EVENT = "PRODUCTION_PART_MARKED"
#: 공정 칸 동기화의 정책 id — 지금 공정 API(``POST …/production/steps``)와 같다(설계서 §15.5).
STEP_SYNC_POLICY_ID = "PRODUCTION_STEP_CHECK"
#: 일괄 기본 한 번의 장 수 상한(화면 한 장 카드 캡과 같다).
BULK_MAX_ITEMS = 200
_SAVE_FAILED = "저장하지 못했어요. 잠시 뒤 다시 해 주세요."
_NOT_CURRENT = "도면이 바뀌었어요. 다시 받아 주세요."
_NOT_IN_PRODUCTION = "생산 단계 주문이 아니에요. 다시 받아 주세요."
_NOT_FOUND = "주문을 찾을 수 없어요."


class _Refusal(Exception):
    """요청을 거절하는 까닭(상태 · 코드 · 글 · 자료) — 핸들러가 응답으로 바꾼다."""

    def __init__(self, status: int, code: str, message: str, extra: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}


@dataclass(frozen=True)
class _Write:
    """쓸 표시 한 장 — 새 칸 값 · 이벤트 한 줄 · 바뀌기 전 상태(``row_id`` 가 없으면 새 줄)."""

    row_id: Optional[int]
    values: dict[str, Any]
    event: dict[str, Any]
    before: str

    @property
    def view(self) -> Any:
        """응답 자료용 줄 모습(``mark_payload`` 가 읽는다)."""
        return SimpleNamespace(**self.values)


def _ok(data: dict[str, Any]):
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response, 200


def _fail(refusal: _Refusal):
    body = {"success": False, "data": {"code": refusal.code, **refusal.extra}, "error": refusal.message}
    return jsonify(body), refusal.status


def _int_id(value: Any) -> int:
    """양의 정수 id(불린 · 글은 거절)."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise _Refusal(400, "BAD_REQUEST", "주문 번호가 올바르지 않아요.")
    return value


def _drawing_key(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text or len(text) > 500:
        raise _Refusal(400, "BAD_REQUEST", "도면 장이 올바르지 않아요.")
    return text


def _choice(value: Any, allowed: tuple[str, ...], label: str) -> str:
    text = value.strip().lower() if isinstance(value, str) else ""
    if text not in allowed:
        raise _Refusal(400, "BAD_REQUEST", f"{label} 값이 올바르지 않아요.")
    return text


def _actor() -> Any:
    """로그인한 사람(``_set_current_user`` 가 비활성 · 끊긴 세션은 이미 비웠다)."""
    user = getattr(g, "current_user", None)
    if user is None:
        raise _Refusal(401, "AUTH_REQUIRED", "로그인이 필요해요.")
    return user


def _gate_part(user: Any, part: str) -> bool:
    """파트 문(D53 · D55). 통과하면 관리자 여부를 돌려준다.

    Raises:
        _Refusal: 파트 없는 계정 403 ``PART_REQUIRED`` · 남의 파트 403 ``PART_FORBIDDEN``.
    """
    mode = part_view_mode(user)
    if mode == VIEW_ADMIN:
        return True
    if mode != VIEW_PART:
        raise _Refusal(403, "PART_REQUIRED", "생산 파트가 정해진 계정만 체크할 수 있어요.")
    if part_account_part(user) != part:
        raise _Refusal(403, "PART_FORBIDDEN", "자기 파트만 체크할 수 있어요.")
    return False


def _check_order(order: Optional[Order]) -> Order:
    """잠근 주문이 살아 있는 ERP 주문이고 생산 단계인지."""
    if order is None or order.status == "DELETED" or order.deleted_at is not None or not order.is_erp_order:
        raise _Refusal(404, "NOT_FOUND", _NOT_FOUND)
    if read_main_stage(order) != "PRODUCTION":
        raise _Refusal(409, "NOT_IN_PRODUCTION", _NOT_IN_PRODUCTION)
    return order


def _current_entry(order: Order, key: str) -> dict[str, Any]:
    """지금 확정 도면 안의 그 장(없으면 409 — 교체된 옛 key 거나 빠진 장)."""
    entry = next((e for e in resolve_final_drawing_files(order.structured_data) if e["key"] == key), None)
    if entry is None:
        raise _Refusal(409, "DRAWING_NOT_CURRENT", _NOT_CURRENT)
    return entry


def _state_words(part: str, state: str) -> str:
    """감사 글의 상태 낱말 — 안 봄(재단) · 안 고름 · 작업 필요 · 기본 · <파트> 끝."""
    label = PRODUCTION_PART_LABELS.get(part, part)
    return {"NEED": "작업 필요", "BASIC": "기본", "DONE": f"{label} 끝"}.get(
        state, "안 봄" if part == BASIC_ALLOWED_PART else "안 고름")


def _plan_write(order: Order, entry: dict[str, Any], row: Optional[ProductionPartMark], *, part: str, target: str,
                user: Any, action: str, override: bool) -> _Write:
    """표시 한 장의 새 값과 이벤트 ``PRODUCTION_PART_MARKED``(payload key · part · from · to)를 만든다(쓰지는 않는다)."""
    now = now_utc_naive()
    before = MarkSnapshot.from_row(row).state
    values = next_mark_values(row, order_id=int(order.id), drawing_key=entry["key"], part=part,
                              sheet_id=entry.get("sheet_id"), target=target, actor_id=user.id,
                              actor_name=user.name or user.username, now=now)
    event = {"order_id": int(order.id), "event_type": PART_MARK_EVENT, "created_by_user_id": user.id, "created_at": now,
             "payload": {"key": entry["key"], "part": part, "from": before, "to": target, "action": action,
                         "override": override, "sheet_id": entry.get("sheet_id"), "domain": "PRODUCTION_DOMAIN"}}
    return _Write(row.id if row is not None else None, values, event, before)


def _flush_writes(db: Any, writes: list[_Write]) -> None:
    """표시 줄 · 이벤트를 **표마다 한 번에** 쓴다 — 장이 5장이든 50장이든 문 수가 같다(쿼리 수 계약).

    ORM 한 줄씩 flush 는 SQLite 레인에서 줄마다 INSERT 를 따로 낸다(RETURNING 순서 보장 때문). 두 표 모두
    테이블 버전 카운터 대상(``VERSIONED_TABLES``) 밖이라 세션 훅을 거치지 않아도 신호가 빠지지 않는다.
    """
    inserts = [w.values for w in writes if w.row_id is None]
    updates = [{"id": w.row_id, **w.values} for w in writes if w.row_id is not None]
    if inserts:
        db.execute(insert(ProductionPartMark), inserts)
    if updates:
        db.execute(update(ProductionPartMark), updates)
    if writes:
        db.execute(insert(OrderEvent), [w.event for w in writes])


def _audit(db: Any, user: Any, note: str, detail: dict[str, Any], order: Optional[Order] = None,
           order_count: int = 0) -> None:
    """감사 1행 — 요청 하나에 한 줄(같은 tx, '생산 파트 체크'). 문장은 표시 SSOT(``audit_message_display``)가 만든다.

    주문 하나면 그 주문 표기(``주문 #12 (홍길동) — 생산 파트 체크: …``), 일괄이 여러 주문에 걸치면 주문 수를 적고
    바뀐 주문 · 장 목록은 ``detail`` 에 싣는다(선례: 네이버 일괄 발송처리 감사). 주문마다의 이력은 이벤트가 맡는다.
    """
    if order is not None:
        context = order_audit_context(order)
        message = describe_order_action(order_id=order.id, action=PART_MARK_EVENT, note=note, **context)
        target_id: Optional[int] = int(order.id)
    else:
        context, target_id = {}, None
        message = f"주문 {order_count}건 — {action_label(PART_MARK_EVENT)}: {note}"
    db.add(SecurityLog(user_id=user.id, action=PART_MARK_EVENT, target_type="order", target_id=target_id,
                       message=message, detail={**detail, **context}))


def _after_views(rows: list[Any], writes: list[_Write]) -> dict[int, list[Any]]:
    """주문 → 이번 쓰기를 반영한 표시 줄 모습(읽은 줄 위에 새 값을 덮는다 — 다시 읽지 않는다)."""
    views: dict[tuple[int, str, str], Any] = {
        (int(r.order_id), str(r.drawing_key), str(r.part)): r for r in rows}
    for w in writes:
        views[(int(w.values["order_id"]), str(w.values["drawing_key"]), str(w.values["part"]))] = w.view
    out: dict[int, list[Any]] = {}
    for (order_id, _key, _part), view in views.items():
        out.setdefault(order_id, []).append(view)
    return out


def _step_note(changes: list[dict[str, Any]]) -> str:
    """감사 글 꼬리 — " · 공정 재단 켬"(바뀐 칸이 없으면 빈 글)."""
    words = [f"{PRODUCTION_PART_LABELS.get(c['key'], c['key'])} {'켬' if c['done'] else '끔'}" for c in changes]
    return f" · 공정 {', '.join(words)}" if words else ""


def _sync_order_steps(db: Any, orders: list[Order], marks: dict[int, list[Any]], user: Any) -> list[dict[str, Any]]:
    """표시가 바뀐 주문들의 지금 공정 칸(``structured_data.production.steps``)을 맞춘다(설계서 §15.5).

    한 주문 · 한 파트의 지금 확정 도면 모든 장이 끝이면 그 공정 칸을 켜고, 아니면 끈다(카드로 일한 파트만 — 넘겨받는
    표시 줄은 그 파트 것뿐이다). 바꿀 칸이 있는 주문만 모아 ``execute_order_mutation`` 을 **한 번** 부른다 — 칸이
    안 바뀌면 쿼리 0 · 주문 ``mutation_version`` 그대로.

    Args:
        db: 세션(같은 tx — 주문들은 이미 잠겨 있다).
        orders: 표시가 바뀐 주문.
        marks: 주문 → 이번 쓰기를 반영한 그 파트 표시 줄 모습.
        user: 누른 사람(켜면 칸 ``by_name`` = 그 파트에서 마지막으로 끝낸 사람).

    Returns:
        바뀐 공정 칸 목록 ``[{order_id, key, done}]``.
    """
    changed = [int(o.id) for o in orders if plan_part_step_changes(o.structured_data, marks.get(int(o.id), []))]
    if not changed:
        return []
    out: list[dict[str, Any]] = []

    def _mutate(sess: Any, locked: list[Order]) -> dict[int, list[str]]:
        at_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        events: list[dict[str, Any]] = []
        for order in locked:
            sd = copy.deepcopy(order.structured_data if isinstance(order.structured_data, dict) else {})
            changes = plan_part_step_changes(sd, marks.get(int(order.id), []))
            apply_part_step_changes(sd, changes, at_iso=at_iso)
            order.structured_data = sd
            flag_modified(order, "structured_data")
            events += step_event_rows(order.id, changes, actor_user_id=user.id)
            out.extend(step_change_body(order.id, c) for c in changes)
        if events:
            sess.execute(insert(OrderEvent), events)
        return {int(o.id): ["ORDERS_INDEX", f"ORDER_DETAIL:{o.id}"] for o in locked}

    scope = hashlib.sha256(f"{STEP_SYNC_POLICY_ID}:part_marks:{changed}".encode("utf-8")).hexdigest()
    body = json.dumps({"orders": changed, "user": user.id}, sort_keys=True)
    execute_order_mutation(db, actor_user_id=user.id, policy_id=STEP_SYNC_POLICY_ID, order_ids=changed,
                           scope_hash=scope, request_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
                           mutation=_mutate)
    return out


def _mark_body(row: Any, order_id: int, key: str, part: str) -> dict[str, Any]:
    return {**mark_payload(row), "order_id": order_id, "drawing_key": key, "part": part}


def _parse_one(body: dict[str, Any]) -> tuple[int, str, str, str, str]:
    return (_int_id(body.get("order_id")), _drawing_key(body.get("drawing_key")),
            _choice(body.get("part"), PRODUCTION_PART_KEYS, "파트"), _choice(body.get("action"), MARK_ACTIONS, "누름"),
            _choice(body.get("seen"), SEEN_VALUES, "본 상태"))


def _mark_one(db: Any, user: Any, admin: bool, parsed: tuple[int, str, str, str, str]) -> dict[str, Any]:
    """잠금 → 주문 · 도면 검사 → 전이 표 → 쓰기. 커밋 전 응답 자료를 돌려준다(바뀐 게 없으면 ``changed`` False)."""
    order_id, key, part, action, seen = parsed
    order = _check_order(lock_order_row(db, order_id))
    entry = _current_entry(order, key)
    # 그 주문 · 그 파트 줄을 한 번에 읽는다(누른 장 + 동기화가 볼 나머지 장 — 쿼리 수는 그대로 1).
    rows = (db.query(ProductionPartMark)
            .filter(ProductionPartMark.order_id == order_id, ProductionPartMark.part == part)
            .all())
    row = next((r for r in rows if r.drawing_key == key), None)
    decision = decide_mark(MarkSnapshot.from_row(row), action=action, seen=seen, actor_id=user.id, admin=admin)
    if decision.kind == DECISION_INVALID:
        raise _Refusal(400, "BAD_REQUEST", decision.message)
    if decision.kind == DECISION_CONFLICT:
        raise _Refusal(409, "MARK_CONFLICT", decision.message, {"mark": _mark_body(row, order_id, key, part)})
    if decision.kind != DECISION_APPLY:  # 같은 사람 · 같은 결과(멱등) — 쓰지 않는다
        return {"mark": _mark_body(row, order_id, key, part), "order_step": None, "changed": False}
    write = _plan_write(order, entry, row, part=part, target=decision.target, user=user, action=action,
                        override=decision.override)
    note = f"{PRODUCTION_PART_LABELS[part]} {_state_words(part, write.before)} → {_state_words(part, decision.target)}"
    _flush_writes(db, [write])
    steps = _sync_order_steps(db, [order], _after_views(rows, [write]), user)
    _audit(db, user, note + (" (관리자 덮어쓰기)" if decision.override else "") + _step_note(steps),
           {"key": key, "part": part, "from": write.before, "to": decision.target, "override": decision.override,
            "order_steps": steps}, order=order)
    return {"mark": _mark_body(write.view, order_id, key, part), "order_step": steps[0] if steps else None,
            "changed": True}


def _run(handler: Any) -> Any:
    """핸들러 하나를 한 tx 로 돌리고 응답으로 바꾼다(거절 · 동시 첫 표시 · DB 오류는 되감고 해요체 한 문장)."""
    db = get_db()
    try:
        data = handler(db)
        db.commit()
    except _Refusal as refusal:
        db.rollback()
        return _fail(refusal)
    except RevisionError as exc:  # 공정 칸 동기화의 주문 쓰기 길 — 이미 잠근 주문이라 드물다
        db.rollback()
        return _fail(_Refusal(exc.status_code, exc.error_code or "SAVE_FAILED", _SAVE_FAILED))
    except IntegrityError:  # 같은 장 · 파트 첫 표시가 동시에 두 번(잠금 없는 레인) — 나중 것은 낡은 화면이다
        db.rollback()
        return _fail(_Refusal(409, "MARK_CONFLICT", STALE_MESSAGE))
    except SQLAlchemyError:
        db.rollback()
        return _fail(_Refusal(500, "SAVE_FAILED", _SAVE_FAILED))
    return _ok(data)


@production_part_marks_bp.route("/part-marks", methods=["POST"])
def api_part_mark():
    """도면 한 장 · 내 파트 표시 하나를 바꾼다(맡기 · 기본 · 완료 · 되돌리기). 같은 사람이 같은 결과를 다시 보내면 200."""

    def _handle(db: Any) -> dict[str, Any]:
        user = _actor()
        parsed = _parse_one(request.get_json(silent=True) or {})
        admin = _gate_part(user, parsed[2])
        if parsed[3] == ACTION_BASIC and parsed[2] != BASIC_ALLOWED_PART:
            raise _Refusal(400, "BASIC_CUT_ONLY", "'기본'은 재단에만 있어요.")
        return _mark_one(db, user, admin, parsed)

    return _run(_handle)


def _parse_bulk(body: dict[str, Any]) -> tuple[str, list[tuple[int, str]]]:
    """일괄 몸 → (파트, 보낸 순서의 (주문, 장) 목록 · 겹침 제거)."""
    part = _choice(body.get("part"), PRODUCTION_PART_KEYS, "파트")
    if _choice(body.get("seen"), SEEN_VALUES, "본 상태") != "none":
        raise _Refusal(400, "BAD_REQUEST", "안 본 도면만 한 번에 기본으로 할 수 있어요.")
    items = body.get("items")
    if not isinstance(items, list) or not items:
        raise _Refusal(400, "BAD_REQUEST", "기본으로 할 도면을 골라 주세요.")
    if len(items) > BULK_MAX_ITEMS:
        raise _Refusal(400, "TOO_MANY", f"한 번에 {BULK_MAX_ITEMS}장까지만 할 수 있어요.")
    pairs: list[tuple[int, str]] = []
    for item in items:
        item = item if isinstance(item, dict) else {}
        pair = (_int_id(item.get("order_id")), _drawing_key(item.get("drawing_key")))
        if pair not in pairs:
            pairs.append(pair)
    return part, pairs


def _lock_orders(db: Any, order_ids: list[int]) -> dict[int, Order]:
    """주문들을 id 순으로 한 번에 잠근다(교착 없는 순서 — ``execute_order_mutation`` 과 같은 규칙)."""
    rows = (db.query(Order).filter(Order.id.in_(sorted(set(order_ids)))).order_by(Order.id.asc())
            .populate_existing().with_for_update().all())
    return {int(o.id): o for o in rows}


def _bulk_one(user: Any, admin: bool, order: Optional[Order], key: str, row: Any) -> Optional[_Write]:
    """일괄의 장 하나 — 한 장 쓰기와 같은 검사. → 쓸 것(이미 내가 기본이면 None).

    Raises:
        _Refusal: 이 장만 건너뛸 까닭(``reason`` = 코드).
    """
    order = _check_order(order)
    entry = _current_entry(order, key)
    decision = decide_mark(MarkSnapshot.from_row(row), action=ACTION_BASIC, seen="none", actor_id=user.id, admin=admin)
    if decision.kind == DECISION_CONFLICT:
        raise _Refusal(409, "MARK_CONFLICT", decision.message)
    if decision.kind != DECISION_APPLY:
        return None
    return _plan_write(order, entry, row, part=BASIC_ALLOWED_PART, target=decision.target, user=user,
                       action=ACTION_BASIC, override=False)


def _bulk_basic(db: Any, user: Any, admin: bool, pairs: list[tuple[int, str]]) -> dict[str, Any]:
    """보낸 목록만 기본으로(일부 성공). 주문 잠금 · 표시 줄 읽기 · 감사는 요청마다 한 번씩(장 수와 무관)."""
    orders = _lock_orders(db, [oid for oid, _ in pairs])
    rows = (db.query(ProductionPartMark)
            .filter(ProductionPartMark.order_id.in_(sorted(orders)), ProductionPartMark.part == BASIC_ALLOWED_PART)
            .all()) if orders else []
    marks = {(int(m.order_id), str(m.drawing_key)): m for m in rows}
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    writes: list[_Write] = []
    changed: dict[int, list[str]] = {}
    for order_id, key in pairs:
        row = marks.get((order_id, key))
        try:
            write = _bulk_one(user, admin, orders.get(order_id), key, row)
        except _Refusal as refusal:
            skipped.append({"order_id": order_id, "drawing_key": key, "reason": refusal.code, "error": refusal.message,
                            "mark": _mark_body(row, order_id, key, BASIC_ALLOWED_PART)})
            continue
        if write is not None:
            writes.append(write)
            changed.setdefault(order_id, []).append(key)
        view = write.view if write is not None else row
        applied.append({**_mark_body(view, order_id, key, BASIC_ALLOWED_PART), "changed": write is not None})
    if not writes:
        return {"applied": applied, "skipped": skipped, "order_steps": []}
    _flush_writes(db, writes)
    steps = _sync_order_steps(db, [orders[oid] for oid in changed], _after_views(rows, writes), user)
    only = orders[next(iter(changed))] if len(changed) == 1 else None
    _audit(db, user, f"재단 기본 {len(writes)}장" + _step_note(steps),
           {"part": BASIC_ALLOWED_PART, "to": "BASIC", "bulk": True, "order_steps": steps,
            "orders": [{"order_id": oid, "keys": keys} for oid, keys in changed.items()]},
           order=only, order_count=len(changed))
    return {"applied": applied, "skipped": skipped, "order_steps": steps}


@production_part_marks_bp.route("/part-marks/basic", methods=["POST"])
def api_part_marks_basic():
    """재단 [남은 N장 모두 기본] — 화면이 보낸 목록만 기본으로. 맞는 장만 바꾸고 나머지는 ``skipped`` 로(전부 실패해도 200)."""

    def _handle(db: Any) -> dict[str, Any]:
        user = _actor()
        part, pairs = _parse_bulk(request.get_json(silent=True) or {})
        admin = _gate_part(user, part)
        if part != BASIC_ALLOWED_PART:
            raise _Refusal(400, "BASIC_CUT_ONLY", "'기본'은 재단에만 있어요.")
        return _bulk_basic(db, user, admin, pairs)

    return _run(_handle)

"""도면 장의 공장 지정 · 바꾸기 API(설계서 2026-11-23 §4-13 · §5-1 · §6-3 · §7, 3단계 ③).

``POST /api/orders/<id>/drawing/sheet-factory`` 몸 ``{items: [{sheet_id?, key?, factory: 1|2}], idempotency_key?}``
(장 하나 또는 여럿 — 하나라도 막히면 모두 안 바꾼다, 같은 값이면 안 쓴다). 응답 ``{success, data: {factory_by_sheet,
factory_by_key, changed}, error}`` — 두 표는 2공장인 장만 열쇠로 든다(없는 열쇠 = 1공장).

* 누가: 도면팀 누구나 + 관리자(앞문 정책 ``DRAWING_TEAM`` + 처리기 술어
  :func:`~foms.services.orders.erp_policy_permissions.can_set_sheet_factory` — 생산팀 MANAGER 는 앞문을 지나도 여기서 403
  ``FACTORY_DRAWING_ONLY``). 그 주문 도면 담당이 아니어도, 담당이 없는 주문도 된다.
* 언제: 아무도 맡거나 완료하지 않은 장만 옮긴다(생산으로 내려온 뒤에도). 시공 대기 이후 409 ``ORDER_DONE``. 판정 · 글은
  :mod:`foms.services.orders.drawing_factory`.
* 한 tx(REV-00 :func:`execute_order_mutation` — 행 잠금 · If-Match · 버전 +1 · 멱등): 잠금 1 + 표시 줄 1(생산 단계 옮김만) + 쓰기 +
  이벤트 ``DRAWING_SHEET_FACTORY_CHANGED`` 1 + 감사 1. 막히면 되감고 감사에 거절 한 줄만.
* 응답 ``data.mutation_version`` = 이 요청 뒤 주문 버전(읽기 전용) — 같은 화면이 들고 있는 If-Match 값을 맞춘다(3단계 ④ 검토).
* 확인 창(§4-13 표 둘째 줄): 몸에 ``confirmed: false`` 를 실으면, 생산 단계에서 지금 확정 도면 장을 옮기는데 일이 시작 안 된 경우
  409 ``CONFIRM_REQUIRED`` 로 돌려보낸다(쓰기 0 · 거절 감사 없음) — 화면이 확인 창을 띄운 뒤 ``confirmed: true`` 로 다시 보낸다.
  화면이 연 때 값으로 "생산에 내려간 장"을 가르지 않게 서버가 정한다. ``confirmed`` 가 없으면 묻지 않는다(그대로 옮김).
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
from typing import Any

from flask import Blueprint, g, jsonify, request
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from foms.services.audit_message_display import describe_order_action
from foms.services.common.dashboard_cache import (
    DASHBOARD_FAMILY_DRAWING,
    DASHBOARD_FAMILY_PRODUCTION,
    invalidate_order_dashboard_families,
)
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.drawing_factory import (
    FORBIDDEN_MESSAGE,
    SHEET_FACTORY_EVENT,
    SHEET_FACTORY_REFUSED,
    SheetFactoryRefusal,
    apply_factory_changes,
    change_note,
    change_rows,
    factory_by_key,
    factory_by_sheet,
    plan_factory_changes,
)
from foms.services.orders.erp_policy_permissions import can_set_sheet_factory
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.orders.revision import RevisionError, execute_order_mutation
from foms.services.orders.stage_override import STAGE_FORWARD_RANK
from foms.services.orders.state_axes import read_main_stage
from foms.services.production.factory_constants import FACTORIES
from foms.services.production.part_marks_query import order_marks
from models import Order, OrderEvent, SecurityLog

logger = logging.getLogger(__name__)

#: 앞문 정책(매니페스트) — 팀 DRAWING + 관리자.
SHEET_FACTORY_POLICY_ID = "DRAWING_TEAM"
#: 멱등 영수증 칸(같은 key 를 다른 도면 일과 섞지 않게 따로 둔다).
SHEET_FACTORY_MUTATION_ID = "DRAWING_SHEET_FACTORY"
MAX_ITEMS = 100
_SAVE_FAILED = "저장하지 못했어요. 잠시 뒤 다시 해 주세요."
#: 확인 창이 필요하다(쓰기 0) — 화면은 이 글 대신 확인 창을 띄운다. API 만 부르는 쪽이 읽을 글.
CONFIRM_REQUIRED = "CONFIRM_REQUIRED"
_CONFIRM_MESSAGE = "생산에 이미 내려간 도면이에요. 옮기면 1공장 · 2공장 화면에 '바뀜'으로 알려요."

erp_orders_sheet_factory_bp = Blueprint('erp_orders_sheet_factory', __name__, url_prefix='/api/orders')


class _Unchanged(Exception):
    """바꿀 것이 없다(모두 같은 값) — 되감고 200(쓰기 · 이벤트 · 버전 0)."""

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__("unchanged")
        self.data = data


def _fail(refusal: SheetFactoryRefusal):
    return jsonify({"success": False, "data": {"code": refusal.code, **refusal.extra}, "error": refusal.message}), refusal.status


def _items(payload: Any) -> list[dict[str, Any]]:
    """몸의 ``items`` — 1 ~ 100줄, 줄마다 ``sheet_id`` 또는 ``key`` 와 ``factory`` 1 · 2(모양이 틀리면 400)."""
    rows = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ITEMS:
        raise SheetFactoryRefusal(400, "BAD_REQUEST", "지정할 도면이 올바르지 않아요.")
    out = []
    for row in rows:
        factory = row.get("factory") if isinstance(row, dict) else None
        if isinstance(factory, bool) or factory not in FACTORIES:
            raise SheetFactoryRefusal(400, "BAD_REQUEST", "공장 값이 올바르지 않아요.")
        sheet_id, key = row.get("sheet_id"), row.get("key")
        if not any(isinstance(v, str) and v.strip() for v in (sheet_id, key)):
            raise SheetFactoryRefusal(400, "BAD_REQUEST", "지정할 도면이 올바르지 않아요.")
        out.append({"sheet_id": sheet_id if isinstance(sheet_id, str) else None,
                    "key": key[:500] if isinstance(key, str) else None, "factory": factory})
    return out


def _hashes(order_id: int, items: list[dict[str, Any]]) -> tuple[str, str]:
    scope = hashlib.sha256(f"{SHEET_FACTORY_MUTATION_ID}:{order_id}".encode()).hexdigest()
    body = json.dumps(items, sort_keys=True, ensure_ascii=False)
    return scope, hashlib.sha256(body.encode()).hexdigest()


def _actor_name(user: Any) -> str:
    return getattr(user, "name", None) or getattr(user, "username", None) or ""


def _audit(db: Any, user: Any, order: Any, action: str, note: str, detail: dict[str, Any]) -> None:
    """감사 1행(같은 tx) — "주문 #4182 (구슬기) — 도면 공장 지정: 도면 2/3 1공장 → 2공장"."""
    context = order_audit_context(order)
    db.add(SecurityLog(user_id=user.id, action=action, target_type="order", target_id=int(order.id),
                       message=describe_order_action(order_id=order.id, action=action, note=note, **context),
                       detail={**detail, **context}))


def _refusal_audit(db: Any, user: Any, order_id: int, refusal: SheetFactoryRefusal) -> None:
    """막힌 옮김 · 권한 거절은 감사에 거절 한 줄만(§11) — 본 tx 는 이미 되감았다."""
    order = db.get(Order, order_id)
    if order is None:
        return
    try:
        _audit(db, user, order, SHEET_FACTORY_REFUSED, refusal.message, {"code": refusal.code, "reason": refusal.message})
        db.commit()
    except Exception:  # noqa: BLE001 - 거절 기록 실패가 거절 응답을 바꾸면 안 된다(로그는 남긴다)
        db.rollback()
        logger.warning("[SHEET_FACTORY] refusal audit failed order=%s", order_id, exc_info=True)


def _needs_confirm(stage: Any, changes: list[Any]) -> bool:
    """생산 단계에서 지금 확정 도면 장(``keys`` 있음)을 옮기는지 — 확인 창 대상(§4-13 표 둘째 줄)."""
    return STAGE_FORWARD_RANK.get(str(stage or "")) == STAGE_FORWARD_RANK["PRODUCTION"] and any(c.keys for c in changes)


def _mutation(user: Any, items: list[dict[str, Any]], captured: dict[str, Any], *, ask_confirm: bool = False):
    """잠근 주문 위에서 계획 → 쓰기 → 이벤트 · 감사(막히면 :class:`SheetFactoryRefusal`, 같은 값이면 :class:`_Unchanged`).

    ``ask_confirm`` 이면 막힘 판정을 다 지난 뒤 확인 창 대상인지 보고 409 ``CONFIRM_REQUIRED``(쓰기 0).
    """

    def _mutate(sess: Any, locked: list[Order]) -> dict[int, list[str]]:
        order = locked[0]
        if order.status == "DELETED" or order.deleted_at is not None or not order.is_erp_order:
            raise SheetFactoryRefusal(404, "NOT_FOUND", "주문을 찾을 수 없어요.")
        sd = copy.deepcopy(order.structured_data if isinstance(order.structured_data, dict) else {})
        stage = read_main_stage(order)
        changes = plan_factory_changes(sd, items, stage=stage, load_marks=lambda: order_marks(sess, order.id))
        if not changes:
            raise _Unchanged({"factory_by_sheet": factory_by_sheet(sd), "factory_by_key": factory_by_key(sd), "changed": [],
                              "mutation_version": int(order.mutation_version or 0)})
        if ask_confirm and _needs_confirm(stage, changes):
            raise SheetFactoryRefusal(409, CONFIRM_REQUIRED, _CONFIRM_MESSAGE)
        rows = change_rows(sd, changes)
        apply_factory_changes(sd, changes, by_name=_actor_name(user), at_iso=now_utc_naive().isoformat())
        order.structured_data = sd
        flag_modified(order, "structured_data")
        sess.add(OrderEvent(order_id=order.id, event_type=SHEET_FACTORY_EVENT, created_by_user_id=user.id,
                            payload={"changes": rows, "by_name": _actor_name(user), "stage": stage}))
        _audit(sess, user, order, SHEET_FACTORY_EVENT, change_note(rows), {"changes": rows})
        captured["data"] = {"factory_by_sheet": factory_by_sheet(sd), "factory_by_key": factory_by_key(sd), "changed": rows}
        return {order.id: [f"ORDER_DETAIL:{order.id}", "ORDERS_INDEX"]}

    return _mutate


@erp_orders_sheet_factory_bp.route('/<int:order_id>/drawing/sheet-factory', methods=['POST'])
def api_order_sheet_factory(order_id: int):
    """도면 장의 공장을 지정 · 바꾼다. 하나라도 막히면 아무것도 바꾸지 않는다."""
    user = getattr(g, "current_user", None)  # before_request(_set_current_user) — 비활성 · 끊긴 세션은 이미 비웠다
    if user is None:
        return jsonify({"success": False, "data": {"code": "AUTH_REQUIRED"}, "error": "다시 로그인해 주세요."}), 401
    db = get_db()
    if not can_set_sheet_factory(user) or not evaluate_policy(POLICY_REGISTRY[SHEET_FACTORY_POLICY_ID], user).allowed:
        refusal = SheetFactoryRefusal(403, "FACTORY_DRAWING_ONLY", FORBIDDEN_MESSAGE)
        _refusal_audit(db, user, order_id, refusal)
        return _fail(refusal)
    payload = request.get_json(silent=True) or {}
    try:
        items = _items(payload)
    except SheetFactoryRefusal as refusal:
        return _fail(refusal)
    ask_confirm = payload.get("confirmed") is False if isinstance(payload, dict) else False
    if_match = (request.headers.get("If-Match") or "").strip().strip('"')
    idem = (str(payload.get("idempotency_key") or "").strip() or (request.headers.get("Idempotency-Key") or "").strip())[:64]
    scope_hash, request_hash = _hashes(order_id, items)
    captured: dict[str, Any] = {}
    try:
        execute_order_mutation(
            db, actor_user_id=user.id, policy_id=SHEET_FACTORY_MUTATION_ID, order_ids=[order_id],
            expected_versions={order_id: int(if_match)} if if_match.isdigit() else None, idempotency_key=idem or None,
            scope_hash=scope_hash, request_hash=request_hash, mutation=_mutation(user, items, captured, ask_confirm=ask_confirm),
        )
        db.commit()
    except _Unchanged as same:
        db.rollback()
        return jsonify({"success": True, "data": same.data, "error": None})
    except SheetFactoryRefusal as refusal:
        db.rollback()
        if refusal.status == 409 and refusal.code != CONFIRM_REQUIRED:  # 확인 물음은 거절이 아니다
            _refusal_audit(db, user, order_id, refusal)
        return _fail(refusal)
    except RevisionError as rev:  # 주문 없음 404 · If-Match 어긋남 409 · 멱등 key 어긋남
        db.rollback()
        message = "주문을 찾을 수 없어요." if rev.status_code == 404 else _SAVE_FAILED
        return _fail(SheetFactoryRefusal(rev.status_code, rev.error_code or "SAVE_FAILED", message))
    except Exception as exc:  # noqa: BLE001 - 되감고 500(해요체 한 문장)
        db.rollback()
        logger.exception("[SHEET_FACTORY] order %s: %s", order_id, exc)
        return _fail(SheetFactoryRefusal(500, "SAVE_FAILED", _SAVE_FAILED))

    order = db.get(Order, order_id)
    if order is not None:
        invalidate_order_dashboard_families(order, extra=(DASHBOARD_FAMILY_DRAWING, DASHBOARD_FAMILY_PRODUCTION))
    data = captured.get("data")
    if data is None and order is not None:  # 같은 멱등 key 다시 보냄 — 저장한 뒤 모습을 읽어 준다(쓰기 0)
        sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        data = {"factory_by_sheet": factory_by_sheet(sd), "factory_by_key": factory_by_key(sd), "changed": []}
    if data is not None and order is not None:
        data["mutation_version"] = int(order.mutation_version or 0)  # 같은 화면의 If-Match 값을 맞춘다
    return jsonify({"success": True, "data": data or {}, "error": None})

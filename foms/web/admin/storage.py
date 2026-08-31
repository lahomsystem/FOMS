"""수납장 대시보드 Blueprint (canonical; SFC-B11B). Phase 2-2 app.py 슬림다운.

STORAGE-WRITER-01: 대시보드 인라인 편집은 generic field adapter(임의 필드 강제) 대신
typed field adapter(:func:`update_storage_field_response`)로 저장한다. cabinet 상태는
enum·Production/Shipment 정책, 배송비는 정수·Finance 정책으로 in-handler enforce 하고,
REV-00 :func:`execute_order_mutation` 으로 If-Match·version bump·receipt·OrderEvent 를 한
transaction 에 묶는다. main/logistics/settlement 축은 건드리지 않는다.
"""
import hashlib
import json
import uuid
from typing import Any, Optional

from flask import Blueprint, render_template, request, session, current_app, jsonify
from sqlalchemy import or_, func, String
from sqlalchemy.orm import Session
from db import get_db
from models import Order, OrderEvent
from foms.web.auth import login_required, role_required, log_access, get_user_by_id
from foms.services.audit_message_display import describe_order_action
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.status_constants import CABINET_STATUS, STATUS
from foms.services.orders.order_field_change_writer import record_field_changes
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy, Decision
from foms.services.orders.revision import RevisionError, execute_order_mutation

storage_dashboard_bp = Blueprint('storage_dashboard', __name__)

#: typed adapter 가 쓰는 유일한 두 필드(generic coercion 금지). OrderEvent.event_type·receipt
#: policy_id 가 이 command 문자열을 공유한다.
STORAGE_CABINET_COMMAND = "CABINET_STATUS_CHANGED"
STORAGE_SHIPPING_COMMAND = "SHIPPING_FEE_CHANGED"
_STORAGE_TYPED_FIELDS = ("cabinet_status", "shipping_fee")
_VALID_CABINET_STATUSES = frozenset(CABINET_STATUS.keys())


@storage_dashboard_bp.route('/storage_dashboard')
@login_required
def storage_dashboard():
    """수납장 대시보드"""
    db = get_db()
    search_query = request.args.get('search_query', '').strip()

    base_query = db.query(Order).filter(
        Order.is_cabinet == True,
        Order.active_filter()
    )

    if search_query:
        search_term = f"%{search_query}%"
        id_conditions = []
        try:
            search_id = int(search_query)
            id_conditions.append(Order.id == search_id)
        except ValueError:
            id_conditions.append(func.cast(Order.id, String).ilike(search_term))  # perf-ok: bounded id search admin/cold path

        base_query = base_query.filter(
            or_(
                Order.customer_name.ilike(search_term),  # perf-ok: ix_orders_customer_name_trgm
                Order.phone.ilike(search_term),  # perf-ok: ix_orders_phone_trgm
                Order.address.ilike(search_term),  # perf-ok: ix_orders_address_trgm
                Order.product.ilike(search_term),  # perf-ok: ix_orders_product_trgm
                Order.notes.ilike(search_term),  # perf-ok: ix_orders_structured_data_text_trgm
                *id_conditions
            )
        )

    all_cabinet_orders = base_query.order_by(Order.id.desc()).all()

    # 카테고리 분류: 접수(RECEIVED), 제작중(IN_PRODUCTION), 발송(SHIPPED)
    received_orders = [o for o in all_cabinet_orders if (o.cabinet_status or 'RECEIVED') == 'RECEIVED']
    in_production_orders = [o for o in all_cabinet_orders if o.cabinet_status == 'IN_PRODUCTION']
    shipped_orders = [o for o in all_cabinet_orders if o.cabinet_status == 'SHIPPED']

    return render_template('admin/storage_dashboard.html',
                           received_orders=received_orders,
                           in_production_orders=in_production_orders,
                           shipped_orders=shipped_orders,
                           search_query=search_query,
                           CABINET_STATUS=CABINET_STATUS,
                           STATUS=STATUS)



# --------------------------------------------------------------------------- #
# typed field adapter (STORAGE-WRITER-01) — generic coercion 제거
# --------------------------------------------------------------------------- #
def _json_error(message: str, status: int, code: str = "") -> Any:
    """canonical ``{success,data,error}`` 실패 응답을 만든다."""
    return jsonify({
        "success": False, "data": None,
        "error": message, "message": message, "code": code,
    }), status


def _coerce_shipping_fee(value: Any) -> Optional[int]:
    """배송비를 비음수 정수로 강제한다(재정의 없이 원값 저장; [[shipping_price_grand_total]]).

    Args:
        value: 요청 payload 의 배송비(int/float/정수문자열 허용).

    Returns:
        비음수 정수, 또는 정수로 안전 해석 불가 시 ``None``(호출자가 422 처리).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value >= 0 else None
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if cleaned.isdigit():
            return int(cleaned)
    return None


def _authorize_storage_field(field: str, user: Any) -> Decision:
    """typed field 별 §2.1 정책 판정(in-handler).

    cabinet_status 는 Production 또는 Shipment 정책(CS/SALES/PRODUCTION/SHIPMENT +
    ADMIN/MANAGER), shipping_fee 는 Finance 정책(CS/SALES + ADMIN/MANAGER). VIEWER deny.

    Args:
        field: ``"cabinet_status"`` 또는 ``"shipping_fee"``.
        user: 현재 사용자(``None`` 이면 미인증).

    Returns:
        :class:`Decision` (거부 시 status/code/reason 동봉).
    """
    if field == "cabinet_status":
        prod = evaluate_policy(POLICY_REGISTRY["PRODUCTION_EDIT"], user)
        if prod.allowed:
            return prod
        return evaluate_policy(POLICY_REGISTRY["SHIPMENT_EDIT"], user)
    return evaluate_policy(POLICY_REGISTRY["FINANCE_MUTATION"], user)


def _validate_storage_value(field: str, value: Any) -> tuple[Any, Optional[tuple]]:
    """typed 값 검증. 반환 ``(typed_value, error)``; error 가 not None 이면 거부(422)."""
    if field == "cabinet_status":
        if value in _VALID_CABINET_STATUSES:
            return value, None
        return None, (f"유효하지 않은 수납장 상태입니다: {value}", 422, "INVALID_CABINET_STATUS")
    fee = _coerce_shipping_fee(value)
    if fee is None:
        return None, ("배송비는 0 이상의 정수만 가능합니다.", 422, "INVALID_SHIPPING_FEE")
    return fee, None


def _storage_hashes(order_id: int, field: str, value: Any) -> tuple[str, str]:
    """``(scope_hash, request_hash)`` — receipt 저장·same-key/different-hash 감지용 sha256."""
    scope = hashlib.sha256(f"STORAGE:{order_id}:{field}".encode()).hexdigest()
    payload = json.dumps({"field": field, "value": value}, sort_keys=True, ensure_ascii=False)
    return scope, hashlib.sha256(payload.encode()).hexdigest()


def _storage_ledger_text(value: Any) -> Optional[str]:
    """원장에 실을 문자열 표현(빈값은 ``None`` 으로 접는다).

    ``cabinet_status`` 는 ``None``/``''`` 이 모두 "값 없음"이라 둘을 같은 뜻으로 접어야
    빈값→빈값이 가짜 변경으로 남지 않는다. ``shipping_fee`` 의 ``0`` 은 **빈값이 아니다**
    (무료 배송이라는 값) — 그래서 문자열로 만든 뒤에 판정한다.

    Args:
        value: 컬럼 값(``str``/``int``/``None``).

    Returns:
        문자열, 또는 빈값이면 ``None``.
    """
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    return text or None


def _storage_ledger_op(before: Any, after: Any) -> str:
    """원장 op 판정 — ``add``(빈값→값) · ``clear``(값→빈값) · ``set``."""
    before_text = _storage_ledger_text(before)
    after_text = _storage_ledger_text(after)
    if before_text is None:
        return "add"
    if after_text is None:
        return "clear"
    return "set"


def _parse_if_match(order_id: int) -> tuple[Optional[dict], Optional[Any]]:
    """optional ``If-Match``(mutation_version) → expected_versions. 형식오류는 ``(None, 400)``."""
    raw = (request.headers.get("If-Match") or "").strip().strip('"')
    if not raw:
        return None, None
    try:
        return {order_id: int(raw)}, None
    except ValueError:
        return None, _json_error("If-Match 형식이 올바르지 않습니다.", 400, "BAD_IF_MATCH")


def _commit_storage_field(
    db: Session, order_id: int, field: str, typed_value: Any,
    expected_versions: Optional[dict], idempotency_key: Optional[str],
) -> Any:
    """REV-00 one-tx: FOR UPDATE + If-Match + version bump + receipt + OrderEvent.

    typed scalar 컬럼(cabinet_status/shipping_fee)만 setattr 한다 — structured_data(JSONB)·
    main/logistics/settlement 축은 건드리지 않는다.
    """
    user_id = session.get("user_id")
    command = STORAGE_CABINET_COMMAND if field == "cabinet_status" else STORAGE_SHIPPING_COMMAND
    scope_hash, request_hash = _storage_hashes(order_id, field, typed_value)
    # AUDIT-GAP-01: 이전값은 row lock 아래에서만 읽을 수 있다(밖에서 다시 읽으면 그 사이의
    # 동시 쓰기를 놓친다). OrderEvent 에만 있던 값을 감사 헤더·변경 원장까지 끌어올린다 —
    # 배송비는 돈이라 before 가 없으면 분쟁에서 따질 근거가 없다.
    # 원장 판정은 ``_mutate`` 안에서 끝나므로 밖으로 들고 나오는 것은 감사 헤더에 실을
    # 이전값 하나뿐이다(replay 로 ``_mutate`` 가 안 돌면 ``None`` 으로 남는다).
    captured: dict[str, Any] = {"before": None}
    # AUDIT-GAP-01: 감사 헤더 ``detail['change_set']`` 과 원장 행을 잇는 열쇠(아래 참조).
    storage_change_set = str(uuid.uuid4())

    def _mutate(sess: Session, orders: list) -> dict:
        o = orders[0]
        old_value = getattr(o, field)
        captured["before"] = old_value
        changed = old_value != typed_value
        setattr(o, field, typed_value)
        sess.add(OrderEvent(
            order_id=o.id, event_type=command,
            payload={"field": field, "from": old_value, "to": typed_value},
            created_by_user_id=user_id,
        ))
        # AUDIT-GAP-01: 원장 쓰기는 컬럼 write 와 **운명을 같이해야** 하므로 ``_mutate`` 안에
        # 둔다. ``execute_order_mutation`` 이 반환한 뒤(바깥)에 쓰면 두 경로가 어긋난다:
        # ① 같은 Idempotency-Key replay 는 ``mutation`` 을 아예 실행하지 않고 저장된 응답을
        # 반환하고, ② receipt insert 의 IntegrityError backstop 은 ``mutation`` 을 **이미
        # 실행한 뒤** ``session.rollback()`` 하고 replay 를 반환한다(``revision.py`` 의
        # ``session.add(receipt)`` → ``flush()`` except 블록). ②에서는 컬럼이 롤백됐는데
        # 바깥 쓰기만 살아남아 **컬럼은 안 바뀌었는데 원장 행만 남는** 유령 행이 된다.
        # 안에서 쓰면 FOR UPDATE 락 안·같은 tx 라 rollback 이 원장 행도 함께 지운다.
        #
        # 평면 컬럼이라 점 없는 컬럼명을 원장 path 로 쓴다(ORDER-FLAG-01 확정 규약).
        # 무변경 저장은 행을 만들지 않는다.
        if changed:
            record_field_changes(
                sess,
                [{
                    "path": field,
                    "before": _storage_ledger_text(old_value),
                    "after": _storage_ledger_text(typed_value),
                    "op": _storage_ledger_op(old_value, typed_value),
                }],
                order_id=int(o.id), actor_user_id=user_id,
                change_set_id=storage_change_set,
            )
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    try:
        outcome = execute_order_mutation(
            db, actor_user_id=user_id, policy_id=command, order_ids=[order_id],
            expected_versions=expected_versions, idempotency_key=idempotency_key,
            scope_hash=scope_hash, request_hash=request_hash, mutation=_mutate,
        )
        order = db.get(Order, order_id)
        storage_context = order_audit_context(order)
        before_value = captured["before"]
        # AUDIT-GAP-01: 조인 키는 행 수와 **무관하게 항상** 넣는다 — 감사 화면에서 원장으로
        # 넘어가는 길을 늘 열어두기 위해서다. 헤더만 있고 행이 0인 상태는 결함이 아니라
        # "저장은 했는데 바뀐 값이 없다"는 정상 상태다(``edit.py``·``regional.py`` 와 같은 규약).
        storage_detail: dict[str, Any] = {
            "field": field, "before": before_value, "after": typed_value,
            "change_set": storage_change_set, **storage_context,
        }
        log_access(
            describe_order_action(order_id=order_id, action="STORAGE_SETTING_UPDATED",
                                  note=field, **storage_context),
            user_id,
            auto_commit=False,
            action="STORAGE_SETTING_UPDATED", target_type="order", target_id=int(order_id),
            detail=storage_detail,
        )
        db.commit()
    except RevisionError as rev:
        db.rollback()
        return _json_error(str(rev), rev.status_code, rev.error_code)
    except Exception as exc:  # noqa: BLE001 - 롤백 후 500 반환
        db.rollback()
        current_app.logger.error("[STORAGE] typed field 저장 실패: %s", exc, exc_info=True)
        return _json_error(f"오류 발생: {exc}", 500, "STORAGE_WRITE_FAILED")

    resp = jsonify({
        "success": True, "error": None,
        "data": {"normalized_value": typed_value, "mutation_receipt": outcome.read_receipt_id},
    })
    for header, value in outcome.headers.items():
        resp.headers[header] = value
    return resp


def update_storage_field_response(order_id: int) -> Any:
    """수납장 대시보드 typed field(cabinet_status·shipping_fee)를 저장한다 (STORAGE-WRITER-01).

    generic coercion 없이 두 typed 필드만 허용하고, in-handler 정책(cabinet=Production/
    Shipment, shipping_fee=Finance)으로 권한을 enforce 한 뒤 REV-00 경유로 저장한다.

    Args:
        order_id: URL 경로의 대상 주문 ID.

    Returns:
        성공 시 ``{success, data:{normalized_value, mutation_receipt}}`` + no-store,
        실패 시 canonical 오류(400/403/404/409/422/500).
    """
    db: Session = get_db()
    data = request.get_json(silent=True) or {}
    field = data.get("field")
    if field not in _STORAGE_TYPED_FIELDS:
        return _json_error(f"허용되지 않은 필드입니다: {field}", 400, "FIELD_NOT_ALLOWED")

    decision = _authorize_storage_field(field, get_user_by_id(session.get("user_id")))
    if not decision.allowed:
        return _json_error(decision.reason, decision.status, decision.code)

    typed_value, err = _validate_storage_value(field, data.get("value"))
    if err:
        return _json_error(*err)

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return _json_error("유효하지 않은 주문입니다.", 404, "ORDER_NOT_FOUND")

    expected_versions, if_match_err = _parse_if_match(order_id)
    if if_match_err:
        return if_match_err
    idempotency_key = (request.headers.get("Idempotency-Key") or "").strip() or None

    return _commit_storage_field(db, order_id, field, typed_value, expected_versions, idempotency_key)


@storage_dashboard_bp.route('/api/storage_dashboard/order/<int:order_id>/field', methods=['POST'])
@login_required
def update_storage_field(order_id: int):
    """수납장 typed field 저장 route. 권한은 handler in-handler 정책이 enforce 한다."""
    return update_storage_field_response(order_id)

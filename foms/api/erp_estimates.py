"""견적서/계약서 API Blueprint (ERP-ESTIMATE-01).

엔드포인트:
  POST   /api/orders/<order_id>/estimates        — 견적서 생성
  GET    /api/orders/<order_id>/estimates        — 주문별 견적서 목록
  GET    /api/estimates/<estimate_id>            — 견적서 상세 조회
  PUT    /api/estimates/<estimate_id>            — 견적서 수정
  DELETE /api/estimates/<estimate_id>            — 견적서 삭제(draft) / 취소(issued)
  GET    /api/orders/<order_id>/estimate-preview — 주문 데이터에서 견적서 미리보기 데이터 추출

견적서(OrderEstimate)는 **부모 Order 에 종속된 child** 다. 따라서 create/update/
draft-delete/issued-cancel 는 부모 Order 의 mutation 으로 취급해 REV-00
:func:`execute_order_mutation` 경유로 **Order If-Match + mutation_version bump +
idempotency receipt + OrderEvent parity 를 한 transaction** 에 원자화한다. parent scope:
mutation 은 언제나 estimate.order_id(진짜 부모)만 잠그며 payload 로 다른 order 로 재부모화
할 수 없다(cross-order 거부). 권한은 §2.1 canonical 정책 ``ERP_EDIT`` (STAFF+CS/SALES 또는
ADMIN/MANAGER; VIEWER deny) 로 route 레벨에서도 enforce 한다(AUTH-01 before_request 가드가
꺼진 컨텍스트 대비). issued estimate 는 **hard-delete 금지**(soft cancel 만), draft-delete 는
draft 상태에서만.

**경계**: WDC estimate(WDC-AUTH-01 소관)와 혼합하지 않는다 — order estimate 전용.
"""
import hashlib
import json
import logging
from typing import Any, Callable, Optional, Tuple

from flask import Blueprint, request, jsonify, session

from db import get_db
from models import Order, OrderEstimate, OrderEvent
from foms.web.auth import login_required, get_user_by_id, log_access
from foms.services.audit_message_display import describe_order_action
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.estimate_defaults import (
    ESTIMATE_LEGAL_NOTICE,
    resolve_estimate_company_info,
    resolve_estimate_payment_info,
)
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.orders.revision import RevisionError, execute_order_mutation
from foms.services.estimate_service import (
    create_estimate,
    update_estimate,
    extract_estimate_data_from_order,
    is_factory2_order,
)

logger = logging.getLogger(__name__)

erp_estimates_bp = Blueprint('erp_estimates', __name__, url_prefix='/api')

#: §2.1 canonical AUTH 정책(route manifest 가 같은 policy_id 로 매핑).
ESTIMATE_POLICY_ID = "ERP_EDIT"

#: REV-00 receipt/idempotency scope 를 구분하는 command 식별자(POLICY_REGISTRY 아님 —
#: OrderEvent.event_type 와 함께 receipt policy_id 로 저장한다).
CMD_ESTIMATE_CREATE = "ESTIMATE_CREATE"
CMD_ESTIMATE_UPDATE = "ESTIMATE_UPDATE"
CMD_ESTIMATE_DELETE = "ESTIMATE_DELETE"   # draft hard-delete
CMD_ESTIMATE_CANCEL = "ESTIMATE_CANCEL"   # issued soft-cancel

EVENT_ESTIMATE_CREATED = "ESTIMATE_CREATED"
EVENT_ESTIMATE_UPDATED = "ESTIMATE_UPDATED"
EVENT_ESTIMATE_DELETED = "ESTIMATE_DELETED"
EVENT_ESTIMATE_CANCELLED = "ESTIMATE_CANCELLED"


def _is_factory2(order: Order) -> bool:
    """주문 structured_data.flags.factory2 여부."""
    return is_factory2_order(order.structured_data or {})


def _company_info_for_order(order: Order) -> dict:
    """주문 structured_data.flags.factory2에 따라 공급자 정보를 선택한다."""
    return resolve_estimate_company_info(_is_factory2(order))


def _payment_info_for_order(order: Order) -> dict:
    """주문 structured_data.flags.factory2에 따라 결제정보를 선택한다."""
    return resolve_estimate_payment_info(_is_factory2(order))


def _estimate_info_variants() -> dict:
    """견적 프리뷰 UI에서 2공장 체크 토글 시 클라이언트가 즉시 전환할 수 있도록 변형 목록."""
    return {
        'company_info': {
            'default': resolve_estimate_company_info(False),
            'factory2': resolve_estimate_company_info(True),
        },
        'payment_info': {
            'default': resolve_estimate_payment_info(False),
            'factory2': resolve_estimate_payment_info(True),
        },
    }


def _deny_if_not_erp_edit() -> Optional[Any]:
    """route 레벨 §2.1 권한 게이트(ERP_EDIT). 거부면 JSON 응답, 허용이면 None.

    AUTH-01 before_request 가드가 비활성(TESTING 등)인 컨텍스트에서도 VIEWER/타팀을 항상
    403 으로 막기 위해 route 안에서 직접 enforce 한다(call-log 준용).
    """
    user = get_user_by_id(session.get('user_id'))
    decision = evaluate_policy(POLICY_REGISTRY[ESTIMATE_POLICY_ID], user)
    if decision.allowed:
        return None
    return jsonify({
        'success': False,
        'data': None,
        'error': decision.reason,
        'message': decision.reason,
        'code': decision.code,
    }), decision.status


def _run_estimate_mutation(
    db,
    order_id: int,
    *,
    policy_id: str,
    response_status: int,
    scope_extra: str,
    request_payload: dict,
    mutate: Callable,
    audit_action: Optional[str] = None,
    audit_note: Optional[str] = None,
    audit_extra: Optional[dict] = None,
) -> Tuple[Optional[Any], Optional[Any]]:
    """estimate CRUD 를 REV-00 one-tx 로 감싼다. ``(outcome, error_response)`` 반환.

    error_response 가 not None 이면 outcome 은 None 이고 호출자는 그 응답을 그대로 반환한다.
    order_id 는 **언제나 estimate 의 진짜 부모**여야 한다(parent scope; payload 로 다른
    order 를 넘기지 않는다). optional 헤더 ``If-Match``(Order.mutation_version 낙관 잠금)·
    ``Idempotency-Key``(재요청 replay) 를 파싱한다.
    """
    if_match_raw = (request.headers.get('If-Match') or '').strip().strip('"')
    expected_versions: Optional[dict] = None
    if if_match_raw:
        try:
            expected_versions = {order_id: int(if_match_raw)}
        except ValueError:
            return None, (jsonify({'success': False, 'error': 'If-Match 형식이 올바르지 않습니다.'}), 400)
    idempotency_key = (request.headers.get('Idempotency-Key') or '').strip() or None

    user_id = session.get('user_id')
    scope_hash = hashlib.sha256(f"{policy_id}:{order_id}:{scope_extra}".encode()).hexdigest()
    request_hash = hashlib.sha256(
        json.dumps(request_payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()

    try:
        outcome = execute_order_mutation(
            db,
            actor_user_id=user_id,
            policy_id=policy_id,
            order_ids=[order_id],
            expected_versions=expected_versions,
            idempotency_key=idempotency_key,
            scope_hash=scope_hash,
            request_hash=request_hash,
            mutation=mutate,
            response_status=response_status,
        )
        if audit_action:
            order = db.get(Order, order_id)
            context = order_audit_context(order)
            log_access(
                describe_order_action(order_id=order_id, action=audit_action,
                                      note=audit_note, **context),
                user_id,
                auto_commit=False,
                action=audit_action, target_type="order", target_id=int(order_id),
                detail={**(audit_extra or {}), **context},
            )
        db.commit()
        return outcome, None
    except RevisionError as rev:
        db.rollback()
        return None, (jsonify({'success': False, 'error': str(rev), 'code': rev.error_code}), rev.status_code)
    except Exception:
        db.rollback()
        logger.exception("견적서 mutation 실패: order_id=%s policy=%s", order_id, policy_id)
        return None, (jsonify({'success': False, 'error': '견적서 처리 중 오류가 발생했습니다.'}), 500)


def _attach_headers(resp, outcome) -> None:
    """REV-00 no-store 헤더를 응답에 전달한다."""
    for header, value in outcome.headers.items():
        resp.headers[header] = value


@erp_estimates_bp.route('/orders/<int:order_id>/estimate-preview', methods=['GET'])
@login_required
def get_estimate_preview(order_id: int):
    """주문의 structured_data에서 견적서 프리뷰 데이터를 추출한다."""
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return jsonify({'success': False, 'error': '주문을 찾을 수 없습니다.'}), 404

    try:
        data = extract_estimate_data_from_order(order)
    except Exception:
        logger.exception("견적서 프리뷰 추출 실패: order_id=%d", order_id)
        return jsonify({'success': False, 'error': '견적서 데이터를 불러오는 중 오류가 발생했습니다.'}), 500

    variants = _estimate_info_variants()
    data['company_info'] = _company_info_for_order(order)
    data['payment_info'] = _payment_info_for_order(order)
    data['company_info_variants'] = variants['company_info']
    data['payment_info_variants'] = variants['payment_info']
    data['legal_notice'] = ESTIMATE_LEGAL_NOTICE

    return jsonify({'success': True, 'data': data})


@erp_estimates_bp.route('/orders/<int:order_id>/estimates', methods=['POST'])
@login_required
def create_order_estimate(order_id: int):
    """주문에 대한 견적서를 생성한다(REV-00 one-tx · parent scope · ERP_EDIT)."""
    db = get_db()
    deny = _deny_if_not_erp_edit()
    if deny:
        return deny

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return jsonify({'success': False, 'error': '주문을 찾을 수 없습니다.'}), 404

    payload = request.get_json(silent=True) or {}
    override_data = payload.get('override_data')
    user_id = session.get('user_id')
    captured: dict = {}

    def _mutate(sess, orders):
        o = orders[0]
        estimate = create_estimate(sess, o, override_data=override_data, created_by_user_id=user_id)
        sess.add(OrderEvent(
            order_id=o.id,
            event_type=EVENT_ESTIMATE_CREATED,
            payload={'estimate_number': estimate.estimate_number, 'total_amount': estimate.total_amount},
            created_by_user_id=user_id,
        ))
        captured['data'] = estimate.to_dict()  # flush 후 확정된 값(commit 후 재조회 회피)
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    outcome, err = _run_estimate_mutation(
        db, order_id,
        policy_id=CMD_ESTIMATE_CREATE,
        response_status=201,
        scope_extra='create',
        audit_action='ORDER_ESTIMATE_CREATED',
        request_payload={'override_data': override_data},
        mutate=_mutate,
    )
    if err:
        return err

    if outcome.replayed:  # 같은 Idempotency-Key 재요청: business write 미수행.
        data = {'mutation_receipt': outcome.read_receipt_id, 'replayed': True}
    else:
        data = captured['data']
        data['mutation_receipt'] = outcome.read_receipt_id
    resp = jsonify({'success': True, 'data': data})
    _attach_headers(resp, outcome)
    return resp, 201


@erp_estimates_bp.route('/orders/<int:order_id>/estimates', methods=['GET'])
@login_required
def list_order_estimates(order_id: int):
    """주문에 연결된 견적서 목록을 조회한다."""
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return jsonify({'success': False, 'error': '주문을 찾을 수 없습니다.'}), 404

    estimates = (
        db.query(OrderEstimate)
        .filter(OrderEstimate.order_id == order_id)
        .order_by(OrderEstimate.created_at.desc())
        .all()
    )

    variants = _estimate_info_variants()
    return jsonify({
        'success': True,
        'data': [e.to_dict() for e in estimates],
        'company_info': _company_info_for_order(order),
        'payment_info': _payment_info_for_order(order),
        'company_info_variants': variants['company_info'],
        'payment_info_variants': variants['payment_info'],
        'legal_notice': ESTIMATE_LEGAL_NOTICE,
    })


@erp_estimates_bp.route('/estimates/<int:estimate_id>', methods=['GET'])
@login_required
def get_estimate(estimate_id: int):
    """견적서 단건 상세 조회."""
    db = get_db()
    estimate = db.query(OrderEstimate).filter(OrderEstimate.id == estimate_id).first()
    if not estimate:
        return jsonify({'success': False, 'error': '견적서를 찾을 수 없습니다.'}), 404

    order = db.query(Order).filter(Order.id == estimate.order_id).first()
    stored_payment = estimate.payment_info if isinstance(estimate.payment_info, dict) else None
    payment_info = stored_payment or (_payment_info_for_order(order) if order else resolve_estimate_payment_info(False))
    variants = _estimate_info_variants()

    return jsonify({
        'success': True,
        'data': estimate.to_dict(),
        'company_info': _company_info_for_order(order) if order else resolve_estimate_company_info(False),
        'payment_info': payment_info,
        'company_info_variants': variants['company_info'],
        'payment_info_variants': variants['payment_info'],
        'legal_notice': ESTIMATE_LEGAL_NOTICE,
    })


@erp_estimates_bp.route('/estimates/<int:estimate_id>', methods=['PUT'])
@login_required
def update_estimate_api(estimate_id: int):
    """견적서 수정(REV-00 one-tx · parent scope · ERP_EDIT). DRAFT/ISSUED 상태에서만 가능."""
    db = get_db()
    deny = _deny_if_not_erp_edit()
    if deny:
        return deny

    estimate = db.query(OrderEstimate).filter(OrderEstimate.id == estimate_id).first()
    if not estimate:
        return jsonify({'success': False, 'error': '견적서를 찾을 수 없습니다.'}), 404

    if estimate.status not in ('DRAFT', 'ISSUED'):
        return jsonify({'success': False, 'error': f'현재 상태({estimate.status})에서는 수정할 수 없습니다.'}), 400

    payload = request.get_json(silent=True) or {}
    order_id = estimate.order_id  # parent scope: 진짜 부모만 잠근다(payload order_id 무시)
    captured: dict = {}

    def _mutate(sess, orders):
        o = orders[0]
        update_estimate(sess, estimate, payload)  # allowed_fields 만 반영(order_id 재부모화 불가)
        sess.add(OrderEvent(
            order_id=o.id,
            event_type=EVENT_ESTIMATE_UPDATED,
            payload={'estimate_id': estimate_id, 'estimate_number': estimate.estimate_number},
            created_by_user_id=session.get('user_id'),
        ))
        captured['data'] = estimate.to_dict()
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    outcome, err = _run_estimate_mutation(
        db, order_id,
        policy_id=CMD_ESTIMATE_UPDATE,
        audit_action='ORDER_ESTIMATE_UPDATED',
        audit_extra={'estimate_id': estimate_id},
        response_status=200,
        scope_extra=f'update:{estimate_id}',
        request_payload=payload,
        mutate=_mutate,
    )
    if err:
        return err

    if outcome.replayed:
        data = {'mutation_receipt': outcome.read_receipt_id, 'replayed': True}
    else:
        data = captured['data']
        data['mutation_receipt'] = outcome.read_receipt_id
    resp = jsonify({'success': True, 'data': data})
    _attach_headers(resp, outcome)
    return resp


@erp_estimates_bp.route('/estimates/<int:estimate_id>', methods=['DELETE'])
@login_required
def delete_estimate(estimate_id: int):
    """견적서 삭제(REV-00 one-tx · parent scope · ERP_EDIT).

    DRAFT 는 물리 삭제(hard-delete), 그 외(ISSUED 등)는 CANCELLED 로 soft-cancel 한다 —
    issued estimate 는 hard-delete 하지 않는다.
    """
    db = get_db()
    deny = _deny_if_not_erp_edit()
    if deny:
        return deny

    estimate = db.query(OrderEstimate).filter(OrderEstimate.id == estimate_id).first()
    if not estimate:
        return jsonify({'success': False, 'error': '견적서를 찾을 수 없습니다.'}), 404

    order_id = estimate.order_id  # parent scope
    is_draft = estimate.status == 'DRAFT'
    estimate_number = estimate.estimate_number
    command = CMD_ESTIMATE_DELETE if is_draft else CMD_ESTIMATE_CANCEL
    event_type = EVENT_ESTIMATE_DELETED if is_draft else EVENT_ESTIMATE_CANCELLED
    user_id = session.get('user_id')

    def _mutate(sess, orders):
        o = orders[0]
        if is_draft:
            sess.delete(estimate)   # draft 만 물리 삭제
        else:
            estimate.status = 'CANCELLED'  # issued 등은 soft-cancel(보존)
        sess.add(OrderEvent(
            order_id=o.id,
            event_type=event_type,
            payload={'estimate_id': estimate_id, 'estimate_number': estimate_number},
            created_by_user_id=user_id,
        ))
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    outcome, err = _run_estimate_mutation(
        db, order_id,
        policy_id=command,
        audit_action='ORDER_ESTIMATE_DELETED',
        audit_note=estimate_number,
        audit_extra={'estimate_id': estimate_id, 'soft_cancel': not is_draft},
        response_status=200,
        scope_extra=f'delete:{estimate_id}',
        request_payload={'estimate_id': estimate_id, 'status': estimate.status},
        mutate=_mutate,
    )
    if err:
        return err

    message = '견적서가 삭제되었습니다.' if is_draft else '견적서가 취소되었습니다.'
    resp = jsonify({
        'success': True,
        'message': message,
        'data': {'cancelled': not is_draft, 'mutation_receipt': outcome.read_receipt_id},
    })
    _attach_headers(resp, outcome)
    return resp

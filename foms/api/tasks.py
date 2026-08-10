"""주문 팔로업(Task) API (TASK-01).

팔로업 :class:`~models.OrderTask` 은 **부모 Order 에 종속된 child** 다. create/update/
cancel 은 부모 Order 의 mutation 으로 취급해 REV-00 :func:`execute_order_mutation` 경유로
**Order If-Match + mutation_version bump + idempotency receipt + OrderEvent parity 를 한
transaction** 에 원자화하고, task 자신의 ``version`` 도 함께 증가시킨다. parent scope:
mutation 은 언제나 URL 의 부모 Order 만 잠그며 다른 order 로 재부모화/조회할 수 없다
(cross-order 는 404).

권한은 §2.1 canonical 정책 ``ERP_EDIT`` (STAFF+CS/SALES 또는 ADMIN/MANAGER; VIEWER·타팀
STAFF deny = **any-STAFF 금지**) 로 route 레벨에서도 enforce 한다(AUTH-01 before_request
가드가 꺼진 컨텍스트 대비). owner_team 은 canonical 팀 enum(:data:`TEAMS`, MEASURE→SALES
정규화)만 허용하고 owner_user_id 는 활성 User 만 받는다. manual task 는 **arbitrary meta 를
저장하지 않는다**(meta 는 auto task 전용). DELETE 는 **hard-delete 금지** — status=CANCELLED
soft-cancel + OrderEvent(TASK_CANCELLED) 로 취소 이력을 보존한다.
"""
import hashlib
import json
import logging
import uuid
from typing import Any, Callable, Optional, Tuple

from flask import Blueprint, request, jsonify, session

from db import get_db
from models import Order, OrderEvent, OrderTask, User
from foms.web.auth import TEAMS, get_user_by_id, log_access, login_required
from foms.services.audit_message_display import describe_order_action
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.datetime_kst import format_datetime_kst, now_utc_naive
from foms.services.orders.order_mutation_policy import (
    POLICY_REGISTRY,
    evaluate_policy,
    normalize_team,
)
from foms.services.orders.revision import RevisionError, execute_order_mutation

logger = logging.getLogger(__name__)

tasks_bp = Blueprint('tasks', __name__, url_prefix='/api')

#: §2.1 canonical AUTH 정책(route manifest 가 같은 policy_id 로 매핑).
TASK_POLICY_ID = "ERP_EDIT"

#: REV-00 receipt/idempotency scope 를 구분하는 command 식별자(OrderEvent.event_type 와
#: 함께 receipt policy_id 로 저장한다).
CMD_TASK_CREATE = "TASK_CREATE"
CMD_TASK_UPDATE = "TASK_UPDATE"
CMD_TASK_CANCEL = "TASK_CANCEL"

EVENT_TASK_CREATED = "TASK_CREATED"
EVENT_TASK_UPDATED = "TASK_UPDATED"
EVENT_TASK_CANCELLED = "TASK_CANCELLED"

#: canonical 팀 enum(auth 사용자관리·audit 과 동일 SSOT). MEASURE 는 여기 없고
#: normalize_team 이 SALES 로 매핑한다.
CANONICAL_TEAMS = frozenset(TEAMS.keys())
#: manual create/update 가 설정할 수 있는 status(CANCELLED 는 cancel route 전용).
ASSIGNABLE_STATUSES = frozenset({"OPEN", "IN_PROGRESS", "DONE"})


def _deny_if_not_task_editor() -> Optional[Any]:
    """route 레벨 §2.1 권한 게이트(ERP_EDIT). 거부면 JSON 응답, 허용이면 None."""
    user = get_user_by_id(session.get('user_id'))
    decision = evaluate_policy(POLICY_REGISTRY[TASK_POLICY_ID], user)
    if decision.allowed:
        return None
    return jsonify({
        'success': False,
        'data': None,
        'error': decision.reason,
        'message': decision.reason,
        'code': decision.code,
    }), decision.status


def _validate_owner_team(raw: Any) -> Tuple[Optional[str], Optional[str]]:
    """owner_team 을 canonical enum 으로 정규화한다. ``(team_or_None, error_or_None)``.

    빈 값/None 은 미배정(None)으로 허용. 그 외는 :func:`normalize_team` (trim·upper·
    MEASURE→SALES) 후 canonical enum 에 없으면 error.
    """
    if raw in (None, ""):
        return None, None
    team = normalize_team(raw)
    if team not in CANONICAL_TEAMS:
        return None, f"owner_team '{raw}' 은(는) 허용된 팀이 아닙니다."
    return team, None


def _validate_owner_user(db, raw: Any) -> Tuple[Optional[int], Optional[str]]:
    """owner_user_id 를 활성 User 로만 허용한다. ``(uid_or_None, error_or_None)``."""
    if raw in (None, ""):
        return None, None
    try:
        uid = int(raw)
    except (TypeError, ValueError):
        return None, "owner_user_id 형식이 올바르지 않습니다."
    user = db.query(User).filter(User.id == uid, User.is_active.is_(True)).first()
    if user is None:
        return None, "owner_user_id 에 해당하는 활성 사용자가 없습니다."
    return uid, None


def _validate_status(raw: Any, *, default: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """status 를 ASSIGNABLE_STATUSES 로만 허용한다. ``(status_or_None, error_or_None)``."""
    if raw in (None, ""):
        return default, None
    status = str(raw).strip().upper()
    if status not in ASSIGNABLE_STATUSES:
        return None, f"status '{raw}' 은(는) 허용되지 않습니다."
    return status, None


def _reject_meta(payload: dict) -> Optional[Any]:
    """manual task 는 client meta(arbitrary) 를 저장하지 않는다 — 전송 시 400."""
    if payload.get('meta'):
        return jsonify({
            'success': False,
            'error': 'manual task 는 meta 를 설정할 수 없습니다.',
        }), 400
    return None


def _run_task_mutation(
    db,
    order_id: int,
    *,
    policy_id: str,
    scope_extra: str,
    request_payload: dict,
    mutate: Callable,
    audit_action: Optional[str] = None,
    audit_note: Optional[str] = None,
    audit_extra: Optional[dict] = None,
) -> Tuple[Optional[Any], Optional[Any]]:
    """task CRUD 를 REV-00 one-tx 로 감싼다. ``(outcome, error_response)`` 반환.

    order_id 는 **언제나 task 의 진짜 부모**여야 한다(parent scope). optional 헤더
    ``If-Match``(Order.mutation_version 낙관 잠금)·``Idempotency-Key``(재요청 replay)
    를 파싱한다.

    :param audit_action: 감사 원장에 남길 행위 코드(``ORDER_TASK_CREATED`` 등).
        ``None`` 이면 기록하지 않는다. replay 요청은 business write 가 없으므로 기록도 없다.
    :param audit_note: 감사 문장 뒤에 붙일 부연(업무 제목).
    :param audit_extra: ``detail`` 에 추가로 담을 구조화 값.
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
        )
        if audit_action and not outcome.replayed:
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
        logger.exception("task mutation 실패: order_id=%s policy=%s", order_id, policy_id)
        return None, (jsonify({'success': False, 'error': 'Task 처리 중 오류가 발생했습니다.'}), 500)


def _attach_headers(resp, outcome) -> None:
    """REV-00 no-store 헤더를 응답에 전달한다."""
    for header, value in outcome.headers.items():
        resp.headers[header] = value


@tasks_bp.route('/orders/<int:order_id>/tasks', methods=['GET'])
@login_required
def api_order_tasks_list(order_id):
    """주문 팔로업(Task) 목록(parent scope)."""
    try:
        db = get_db()
        order = db.query(Order.id).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        rows = (
            db.query(OrderTask)
            .filter(OrderTask.order_id == order_id)
            .order_by(OrderTask.updated_at.desc())
            .limit(200)
            .all()
        )
        tasks = [{
            'id': t.id,
            'order_id': t.order_id,
            'title': t.title,
            'status': t.status,
            'owner_team': t.owner_team,
            'owner_user_id': t.owner_user_id,
            'due_date': t.due_date,
            'meta': t.meta,
            'version': t.version,
            'provenance': t.provenance,
            'created_at': format_datetime_kst(t.created_at) if t.created_at else None,
            'updated_at': format_datetime_kst(t.updated_at) if t.updated_at else None,
        } for t in rows]
        return jsonify({'success': True, 'tasks': tasks})
    except Exception as e:
        db = get_db()
        db.rollback()
        logger.exception("task list 실패: order_id=%s", order_id)
        return jsonify({'success': False, 'message': str(e)}), 500


@tasks_bp.route('/orders/<int:order_id>/tasks', methods=['POST'])
@login_required
def api_order_tasks_create(order_id):
    """주문 팔로업(Task) 생성(REV-00 one-tx · parent scope · ERP_EDIT)."""
    db = get_db()
    deny = _deny_if_not_task_editor()
    if deny:
        return deny

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

    payload = request.get_json(silent=True) or {}
    meta_err = _reject_meta(payload)
    if meta_err:
        return meta_err

    title = (payload.get('title') or '').strip()
    if not title:
        return jsonify({'success': False, 'message': 'title이 필요합니다.'}), 400

    status, err = _validate_status(payload.get('status'), default='OPEN')
    if err:
        return jsonify({'success': False, 'message': err}), 400
    owner_team, err = _validate_owner_team(payload.get('owner_team'))
    if err:
        return jsonify({'success': False, 'message': err}), 400
    owner_user_id, err = _validate_owner_user(db, payload.get('owner_user_id'))
    if err:
        return jsonify({'success': False, 'message': err}), 400
    due_date = (payload.get('due_date') or None)

    captured: dict = {}

    def _mutate(sess, orders):
        o = orders[0]
        now = now_utc_naive()
        task = OrderTask(
            order_id=o.id,
            title=title,
            status=status,
            owner_team=owner_team,
            owner_user_id=owner_user_id,
            due_date=due_date,
            meta=None,                       # manual task: arbitrary meta 없음
            task_uuid=str(uuid.uuid4()),     # DB-global 안정 identity
            version=1,                       # optimistic task version 시작
            provenance='MANUAL',
            created_at=now,
            updated_at=now,
        )
        sess.add(task)
        sess.flush()                         # task.id 확정
        sess.add(OrderEvent(
            order_id=o.id,
            event_type=EVENT_TASK_CREATED,
            payload={'task_id': task.id, 'title': title, 'status': status},
            created_by_user_id=session.get('user_id'),
        ))
        captured['task_id'] = task.id
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    outcome, err = _run_task_mutation(
        db, order_id,
        policy_id=CMD_TASK_CREATE,
        scope_extra='create',
        audit_action='ORDER_TASK_CREATED', audit_note=title,
        audit_extra={'title': title, 'status': status, 'owner_team': owner_team},
        request_payload={'title': title, 'status': status, 'owner_team': owner_team,
                         'owner_user_id': owner_user_id, 'due_date': due_date},
        mutate=_mutate,
    )
    if err:
        return err

    if outcome.replayed:  # 같은 Idempotency-Key 재요청: business write 미수행.
        resp = jsonify({'success': True, 'replayed': True, 'mutation_receipt': outcome.read_receipt_id})
    else:
        resp = jsonify({'success': True, 'task_id': captured['task_id'],
                        'mutation_receipt': outcome.read_receipt_id})
    _attach_headers(resp, outcome)
    return resp


@tasks_bp.route('/orders/<int:order_id>/tasks/<int:task_id>', methods=['PUT'])
@login_required
def api_order_tasks_update(order_id, task_id):
    """주문 팔로업(Task) 수정(REV-00 one-tx · parent scope · ERP_EDIT)."""
    db = get_db()
    deny = _deny_if_not_task_editor()
    if deny:
        return deny

    # parent scope: 진짜 부모 order 로만 조회(cross-order 는 404).
    task = db.query(OrderTask).filter(OrderTask.id == task_id, OrderTask.order_id == order_id).first()
    if not task:
        return jsonify({'success': False, 'message': 'Task를 찾을 수 없습니다.'}), 404
    if task.status == 'CANCELLED':
        return jsonify({'success': False, 'message': '취소된 Task는 수정할 수 없습니다.'}), 400

    payload = request.get_json(silent=True) or {}
    meta_err = _reject_meta(payload)
    if meta_err:
        return meta_err

    updates: dict = {}
    if 'title' in payload:
        title = (payload.get('title') or '').strip()
        if not title:
            return jsonify({'success': False, 'message': 'title은 비울 수 없습니다.'}), 400
        updates['title'] = title
    if 'status' in payload:
        status, err = _validate_status(payload.get('status'), default=task.status)
        if err:
            return jsonify({'success': False, 'message': err}), 400
        updates['status'] = status
    if 'owner_team' in payload:
        owner_team, err = _validate_owner_team(payload.get('owner_team'))
        if err:
            return jsonify({'success': False, 'message': err}), 400
        updates['owner_team'] = owner_team
    if 'owner_user_id' in payload:
        owner_user_id, err = _validate_owner_user(db, payload.get('owner_user_id'))
        if err:
            return jsonify({'success': False, 'message': err}), 400
        updates['owner_user_id'] = owner_user_id
    if 'due_date' in payload:
        updates['due_date'] = payload.get('due_date') or None

    def _mutate(sess, orders):
        o = orders[0]
        for field, value in updates.items():
            setattr(task, field, value)
        task.version = (task.version or 0) + 1
        task.updated_at = now_utc_naive()
        sess.add(OrderEvent(
            order_id=o.id,
            event_type=EVENT_TASK_UPDATED,
            payload={'task_id': task_id, 'fields': sorted(updates.keys())},
            created_by_user_id=session.get('user_id'),
        ))
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    outcome, err = _run_task_mutation(
        db, order_id,
        policy_id=CMD_TASK_UPDATE,
        scope_extra=f'update:{task_id}',
        audit_action='ORDER_TASK_UPDATED', audit_note=task.title,
        audit_extra={'task_id': task_id, 'fields': sorted(updates.keys())},
        request_payload={'task_id': task_id, **updates},
        mutate=_mutate,
    )
    if err:
        return err

    resp = jsonify({'success': True, 'mutation_receipt': outcome.read_receipt_id})
    _attach_headers(resp, outcome)
    return resp


@tasks_bp.route('/orders/<int:order_id>/tasks/<int:task_id>', methods=['DELETE'])
@login_required
def api_order_tasks_delete(order_id, task_id):
    """주문 팔로업(Task) 취소(REV-00 one-tx · parent scope · ERP_EDIT).

    **hard-delete 금지** — status=CANCELLED soft-cancel + OrderEvent(TASK_CANCELLED) 로
    취소 이력을 보존한다(row 유지).
    """
    db = get_db()
    deny = _deny_if_not_task_editor()
    if deny:
        return deny

    task = db.query(OrderTask).filter(OrderTask.id == task_id, OrderTask.order_id == order_id).first()
    if not task:
        return jsonify({'success': False, 'message': 'Task를 찾을 수 없습니다.'}), 404
    if task.status == 'CANCELLED':  # 이미 취소됨 — idempotent no-op(추가 이벤트 없음)
        return jsonify({'success': True, 'already_cancelled': True})

    def _mutate(sess, orders):
        o = orders[0]
        task.status = 'CANCELLED'  # soft-cancel(보존)
        task.version = (task.version or 0) + 1
        task.updated_at = now_utc_naive()
        sess.add(OrderEvent(
            order_id=o.id,
            event_type=EVENT_TASK_CANCELLED,
            payload={'task_id': task_id, 'title': task.title},
            created_by_user_id=session.get('user_id'),
        ))
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    outcome, err = _run_task_mutation(
        db, order_id,
        policy_id=CMD_TASK_CANCEL,
        scope_extra=f'cancel:{task_id}',
        audit_action='ORDER_TASK_DELETED', audit_note=task.title,
        audit_extra={'task_id': task_id},
        request_payload={'task_id': task_id},
        mutate=_mutate,
    )
    if err:
        return err

    resp = jsonify({'success': True, 'cancelled': True, 'mutation_receipt': outcome.read_receipt_id})
    _attach_headers(resp, outcome)
    return resp

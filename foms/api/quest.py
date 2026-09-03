"""
Quest API (단계별 퀘스트 시스템).
GET/POST /api/orders/<id>/quest, POST /approve, PUT /status
"""

import datetime
import hashlib
import json
from foms.services.error_logging import log_handled_exception
from flask import Blueprint, request, jsonify, session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, User, OrderEvent
from foms.web.auth import log_access, login_required, role_required
from foms.services.audit_message_display import describe_order_action
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.erp_policy_constants import DEFAULT_OWNER_TEAM_BY_STAGE
from foms.services.orders.order_mutation_policy import normalize_team, team_has_capability
from foms.services.erp_policy import (
    get_stage,
    STAGE_LABELS,
    STAGE_NAME_TO_CODE,
    get_quest_template_for_stage,
    create_quest_from_template,
    check_quest_approvals_complete,
    get_next_stage_for_completed_quest,
)
from foms.services.orders.order_transition_service import TransitionError
from foms.services.orders.quest_transition_service import (
    advance_stage_on_quest_completion,
)
from foms.services.orders.revision import RevisionError


quest_bp = Blueprint('quest', __name__, url_prefix='/api')



def _audit_quest(order, action, user_id, note=None, extra=None) -> None:
    """퀘스트 행위 1건을 구조화 감사로 남긴다(문장은 표시 SSOT 가 만든다).

    라우트가 뒤에서 ``db.commit()`` 하므로 같은 트랜잭션에 싣는다(``auto_commit=False``).

    :param order: 대상 :class:`~models.Order`.
    :param action: 행위 코드(``QUEST_CREATED`` 등).
    :param user_id: 행위자 user id.
    :param note: 문장 뒤에 붙일 짧은 부연(단계·팀·상태).
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


@quest_bp.route('/orders/<int:order_id>/quest', methods=['GET'])
@login_required
def api_order_quest_get(order_id):
    """현재 단계의 Quest 조회"""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        sd = order.structured_data or {}
        current_stage_code = get_stage(sd)  # 영문 코드 (예: 'RECEIVED')

        if not current_stage_code:
            return jsonify({'success': True, 'quest': None, 'stage': None})

        # 도면 단계는 퀘스트 승인 흐름을 사용하지 않음 (도면 전달/수령 확정 흐름으로 관리)
        if current_stage_code == 'DRAWING':
            return jsonify({
                'success': True,
                'quest': None,
                'stage': current_stage_code,
                'stage_label': STAGE_LABELS.get(current_stage_code, current_stage_code),
                'message': '도면 단계 퀘스트는 비활성화되었습니다.'
            })

        # 영문 코드를 한글 단계명으로 변환 (quest의 stage는 한글 단계명으로 저장될 수 있음)
        CODE_TO_STAGE_NAME = {v: k for k, v in STAGE_NAME_TO_CODE.items()}
        current_stage_name = CODE_TO_STAGE_NAME.get(current_stage_code, current_stage_code)

        # 현재 단계의 quest 찾기 (한글 단계명 또는 영문 코드 모두 확인)
        quests = sd.get("quests") or []
        current_quest = None
        for q in quests:
            if isinstance(q, dict):
                quest_stage = q.get("stage")
                if quest_stage == current_stage_name or quest_stage == current_stage_code:
                    current_quest = q
                    break

        # quest가 없으면 템플릿에서 표시용으로 합성만 한다 (비영속).
        # GET은 순수 read — 저장/생성은 기존 mutation(POST/PUT) 경로에서만 수행한다.
        if not current_quest:
            quest_tpl = get_quest_template_for_stage(current_stage_code)
            if quest_tpl:
                owner_person = session.get('username') or ''
                current_quest = create_quest_from_template(current_stage_code, owner_person, sd)

        return jsonify({
            'success': True,
            'quest': current_quest,
            'stage': current_stage_code,
            'stage_label': STAGE_LABELS.get(current_stage_code, current_stage_code),
        })
    except Exception as e:
        log_handled_exception()
        return jsonify({'success': False, 'message': str(e)}), 500


@quest_bp.route('/orders/<int:order_id>/quest', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_order_quest_create(order_id):
    """Quest 생성 (현재 단계 기준)"""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        payload = request.get_json(silent=True) or {}
        stage = payload.get('stage') or get_stage(order.structured_data or {})

        if not stage:
            return jsonify({'success': False, 'message': '단계가 지정되지 않았습니다.'}), 400

        # 도면 단계는 퀘스트 생성 비활성화
        stage_code = STAGE_NAME_TO_CODE.get(stage, stage)
        if stage_code == 'DRAWING':
            return jsonify({'success': False, 'message': '도면 단계 퀘스트는 비활성화되었습니다.'}), 400

        # 이미 해당 단계의 quest가 있는지 확인
        sd = order.structured_data or {}
        if not sd.get("quests"):
            sd["quests"] = []

        existing = None
        for q in sd["quests"]:
            if isinstance(q, dict) and q.get("stage") == stage:
                existing = q
                break

        if existing:
            return jsonify({'success': False, 'message': '이미 해당 단계의 Quest가 존재합니다.'}), 400

        # Quest 생성
        owner_person = payload.get('owner_person') or session.get('username') or ''
        new_quest = create_quest_from_template(stage, owner_person, sd)

        if not new_quest:
            return jsonify({'success': False, 'message': 'Quest 템플릿을 찾을 수 없습니다.'}), 400

        sd["quests"].append(new_quest)
        order.structured_data = sd
        order.updated_at = datetime.datetime.now()
        _audit_quest(order, "QUEST_CREATED", session.get('user_id'), note=stage,
                     extra={"stage": stage, "owner": owner_person})
        db.commit()
        # Tier A(broad): quest 생성/전환은 stage 전환을 유발해 탭 간 이동이 일어남.
        from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches

        invalidate_all_dashboard_slice_caches()

        return jsonify({'success': True, 'quest': new_quest})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            log_handled_exception("quest rollback")
        log_handled_exception()
        return jsonify({'success': False, 'message': str(e)}), 500


# DRAWING/CONFIRM 은 전용 command(도면 전달·고객 컨펌)로만 진행 — 단독 quest 승인 거부.
_COMMAND_REQUIRED_STAGES = frozenset({"DRAWING", "CONFIRM"})

#: 전이 receipt scope 구성용 command 식별자(라우트 단일 진입점 — 실제 stage command 는
#: quest_transition_service 의 _STAGE_ADVANCE 가 고른다).
_QUEST_APPROVE_COMMAND = "QUEST_APPROVE"


def _idempotency_key(body):
    """요청 idempotency key(헤더 우선, body fallback, ≤64자). 없으면 None(중복제거 안 함).

    Args:
        body: 요청 JSON dict.

    Returns:
        idempotency key 문자열 또는 None.
    """
    key = request.headers.get("Idempotency-Key") or (body or {}).get("idempotency_key")
    key = str(key).strip() if key is not None else ""
    return key[:64] if key else None


def _scope_hash(command_id: str, order_id: int) -> str:
    """전이 scope 의 sha256 hex(receipt 저장용).

    Args:
        command_id: 전이 scope 식별자.
        order_id: 대상 주문 id.

    Returns:
        sha256 hex 문자열.
    """
    return hashlib.sha256(f"{command_id}:{order_id}".encode("utf-8")).hexdigest()


def _request_hash(body) -> str:
    """요청 payload 의 sha256 hex(same-key/different-hash 감지용).

    Args:
        body: 요청 JSON dict.

    Returns:
        sha256 hex 문자열.
    """
    canonical = json.dumps(body or {}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _transition_error_response(exc):
    """전이 엔진/REV helper 예외를 route JSON 오류로 매핑한다.

    Args:
        exc: TransitionError/RevisionError 계열 예외.

    Returns:
        (flask response, status code) 튜플.
    """
    code = getattr(exc, "error_code", "TRANSITION_ERROR")
    status = getattr(exc, "status_code", 409)
    return jsonify({"success": False, "code": code, "message": str(exc)}), status


def _int_or_none(value):
    """int 변환 실패 시 None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _required_teams_for_stage(current_quest, stage_code):
    """현 단계의 dynamic 필수 승인 팀(정규화). quest.required_approvals 우선, 없으면 기본 owner team.

    Args:
        current_quest: 현재 단계 quest dict (QUEST-BACKFILL 정규화된 required_approvals).
        stage_code: 현재 단계 영문 코드.

    Returns:
        정규화된 팀 코드 목록.
    """
    raw = current_quest.get("required_approvals") if isinstance(current_quest, dict) else None
    teams = [normalize_team(t) for t in (raw or []) if t]
    if not teams:
        default = DEFAULT_OWNER_TEAM_BY_STAGE.get(stage_code)
        if default:
            teams = [normalize_team(default)]
    return [t for t in teams if t]


def _authorize_quest_approve(
    db, user, order, stage_code, current_quest, *, emergency_override, override_reason
):
    """quest approve 권한 게이트 (AUTH-QUEST-01). 권한만 판정 — 상태 전이·기록은 하지 않는다.

    §5.2: actor team = 현 단계 필수 승인 팀; 시공은 ASSIGNMENT-00 user-ID row 기반;
    관리자 override 는 사유 필수(감사). DRAWING/CONFIRM 의 command-required 거부는 caller 가
    앞단에서 처리한다.

    Args:
        db: DB 세션(construction assignment 조회용).
        user: 승인 주체(role/team/id).
        order: 대상 주문.
        stage_code: 현재 단계 영문 코드.
        current_quest: 현재 단계 quest(required_approvals dynamic 팀 근거).
        emergency_override: 관리자 오버라이드 요청 여부.
        override_reason: 오버라이드 사유(오버라이드 시 필수).

    Returns:
        (allowed, status, message) 튜플. 허용이면 ``(True, 200, "")``.
    """
    role = (getattr(user, "role", None) or "").strip().upper()
    actor_team = normalize_team(getattr(user, "team", None))

    # 관리자 오버라이드: 사유 필수(감사). role/team 불일치를 override_reason 으로만 뚫는다.
    if emergency_override:
        if role not in ("ADMIN", "MANAGER"):
            return (False, 403, "긴급 오버라이드는 관리자만 가능합니다.")
        if not override_reason:
            return (False, 422, "오버라이드 승인은 사유(override_reason)가 필수입니다.")
        return (True, 200, "")

    # ADMIN 정상 command 통과(§2.1 role bypass).
    if role == "ADMIN":
        return (True, 200, "")

    # 시공: ASSIGNMENT-00 user-ID row 기반(JSONB 이름 미사용).
    if stage_code == "CONSTRUCTION":
        from foms.services.orders.assignment import active_assignee_ids

        assigned = active_assignee_ids(db, order.id, "CONSTRUCTION")
        if assigned:
            uid = _int_or_none(getattr(user, "id", None))
            if uid is not None and uid in assigned:
                return (True, 200, "")
            return (False, 403, "이 주문에 배정된 시공 담당자만 승인할 수 있습니다.")
        # 배정 0(backfill 미완) → 팀 capability 폴백(lock-out 방지).
        if team_has_capability(actor_team, ("CS", "SALES", "CONSTRUCTION")):
            return (True, 200, "")
        return (False, 403, "시공 승인 권한이 없는 팀입니다.")

    # 일반: actor team = 현 단계 필수 승인 팀(dynamic).
    required_teams = _required_teams_for_stage(current_quest, stage_code)
    if required_teams and team_has_capability(actor_team, required_teams):
        return (True, 200, "")
    return (False, 403, "현재 단계 승인 권한이 없는 팀입니다. (오버라이드가 필요합니다.)")


@quest_bp.route('/orders/<int:order_id>/quest/approve', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_order_quest_approve(order_id):
    """팀별/담당자 Quest 승인 (권한 게이트 + 승인 기록). 상태 전이는 STATE-QUEST-01 하류."""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        payload = request.get_json(silent=True) or {}
        team = (payload.get('team') or '').strip()
        emergency_override = payload.get('emergency_override', False)
        override_reason = payload.get('override_reason', '').strip()

        user_id = session.get('user_id')
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401

        role = (user.role or '').strip().upper()
        actor_team = normalize_team(user.team)

        sd = order.structured_data or {}
        current_stage_code = get_stage(sd)

        if not current_stage_code:
            return jsonify({'success': False, 'message': '현재 단계가 없습니다.'}), 400

        # DRAWING/CONFIRM 단독 승인은 전용 command(도면 전달·고객 컨펌)로만 — command-required 거부.
        if current_stage_code in _COMMAND_REQUIRED_STAGES:
            return jsonify({
                'success': False,
                'code': 'COMMAND_REQUIRED',
                'message': (
                    f'{STAGE_LABELS.get(current_stage_code, current_stage_code)} 단계는 '
                    f'단독 퀘스트 승인이 아니라 전용 command로 진행해야 합니다.'
                ),
            }), 409

        CODE_TO_STAGE_NAME = {v: k for k, v in STAGE_NAME_TO_CODE.items()}
        current_stage_name = CODE_TO_STAGE_NAME.get(current_stage_code, current_stage_code)

        quests = sd.get("quests") or []
        current_quest = None
        quest_index = -1
        for i, q in enumerate(quests):
            if isinstance(q, dict):
                quest_stage = q.get("stage")
                if quest_stage == current_stage_name or quest_stage == current_stage_code:
                    current_quest = q
                    quest_index = i
                    break

        if not current_quest:
            owner_person = session.get('username') or ''
            current_quest = create_quest_from_template(current_stage_name, owner_person, sd)
            if not current_quest:
                return jsonify({'success': False, 'message': 'Quest 템플릿을 찾을 수 없습니다.'}), 400
            if not sd.get("quests"):
                sd["quests"] = []
            sd["quests"].append(current_quest)
            quest_index = len(sd["quests"]) - 1

        # ── 권한 게이트 (AUTH-QUEST-01): 권한만 판정. 상태 전이·기록은 하지 않는다. ──
        allowed, deny_status, deny_msg = _authorize_quest_approve(
            db, user, order, current_stage_code, current_quest,
            emergency_override=emergency_override, override_reason=override_reason,
        )
        if not allowed:
            return jsonify({'success': False, 'message': deny_msg}), deny_status

        username = session.get('username') or ''
        now = datetime.datetime.now()

        # 승인 슬롯 팀: 기본은 actor 자기 팀(스푸핑 방지). ADMIN/오버라이드는 payload team 허용.
        effective_team = (team or actor_team) if (role == 'ADMIN' or emergency_override) else actor_team

        approval_mode = current_quest.get("approval_mode", "team")

        if approval_mode == "assignee":
            domain = None
            if current_stage_code in ('MEASURE', 'CONFIRM'):
                domain = 'SALES_DOMAIN'
            elif current_stage_code == 'DRAWING':
                domain = 'DRAWING_DOMAIN'

            if "assignee_approval" not in current_quest:
                current_quest["assignee_approval"] = {}

            current_quest["assignee_approval"] = {
                "approved": True,
                "approved_by": user_id,
                "approved_by_name": username,
                "approved_at": now.isoformat(),
            }
            current_quest["updated_at"] = now.isoformat()
            if current_quest.get("status") == "OPEN":
                current_quest["status"] = "IN_PROGRESS"

            is_complete = True
            missing_teams = []

            quest_event_payload = {
                'domain': domain or f'{current_stage_code}_DOMAIN',
                'action': 'QUEST_ASSIGNEE_APPROVED',
                'target': 'quest.assignee_approval',
                'before': 'not_approved',
                'after': 'approved',
                'change_method': 'API',
                'source_screen': 'erp_dashboard',
                'reason': f'{current_stage_name} 담당자 승인 완료',
                'is_override': emergency_override,
                'override_reason': override_reason if emergency_override else None,
            }
            quest_approval_event = OrderEvent(
                order_id=order.id,
                event_type='QUEST_APPROVAL_CHANGED',
                payload=quest_event_payload,
                created_by_user_id=user_id
            )
            db.add(quest_approval_event)

        else:
            if not effective_team:
                return jsonify({'success': False, 'message': '팀이 지정되지 않았습니다.'}), 400

            if not current_quest.get("team_approvals"):
                current_quest["team_approvals"] = {}

            current_quest["team_approvals"][effective_team] = {
                "approved": True,
                "approved_by": user_id,
                "approved_by_name": username,
                "approved_at": now.isoformat(),
            }
            current_quest["updated_at"] = now.isoformat()
            if current_quest.get("status") == "OPEN":
                current_quest["status"] = "IN_PROGRESS"

            is_complete, missing_teams = check_quest_approvals_complete(sd, current_stage_name)

            quest_event_payload = {
                'domain': f'{current_stage_code}_DOMAIN',
                'action': 'QUEST_APPROVAL_CHANGED',
                'target': f'quest.team_approvals.{effective_team}',
                'before': 'not_approved',
                'after': 'approved',
                'change_method': 'API',
                'source_screen': 'erp_dashboard',
                'reason': f'{effective_team} 팀 승인 완료',
                'is_override': emergency_override,
                'override_reason': override_reason if emergency_override else None,
            }
            quest_approval_event = OrderEvent(
                order_id=order.id,
                event_type='QUEST_APPROVAL_CHANGED',
                payload=quest_event_payload,
                created_by_user_id=user_id
            )
            db.add(quest_approval_event)

        sd["quests"][quest_index] = current_quest

        # 승인 완료 시 quest 를 COMPLETED 로 마킹한다(승인 bookkeeping).
        if is_complete:
            current_quest["status"] = "COMPLETED"
            current_quest["completed_at"] = now.isoformat()
            sd["quests"][quest_index] = current_quest

        order.structured_data = sd
        flag_modified(order, "structured_data")
        order.updated_at = now
        sync_erp_flat_columns(order, sd)
        _audit_quest(order, "QUEST_APPROVED", user_id, note=team, extra={"team": team})

        # 최종 승인 → stage 전이(STATE-QUEST-01). 라우트는 stage 를 직접 쓰지 않고 정본 서비스에
        # 위임한다. 승인 기록을 먼저 order 에 반영해 두어야 전이 엔진의 structured_data 스냅샷에
        # 승인이 포함된다(승인·전이가 한 tx·한 commit 에 원자적으로 남는다).
        # RECEIVED→MEASURE, MEASURE→DRAWING 만 advance 하고 그 밖의 stage 는 None(no-op).
        auto_transitioned = False
        transition_result = None
        if is_complete:
            try:
                transition_result = advance_stage_on_quest_completion(
                    db,
                    order_id=order.id,
                    actor_user_id=user_id,
                    scope_hash=_scope_hash(_QUEST_APPROVE_COMMAND, order.id),
                    request_hash=_request_hash(payload),
                    idempotency_key=_idempotency_key(payload),
                    reason=f'{current_stage_name} 최종 승인',
                    source_screen='erp_dashboard',
                    now=now,
                )
            except (TransitionError, RevisionError) as exc:
                db.rollback()
                return _transition_error_response(exc)
            auto_transitioned = transition_result is not None and not transition_result.replayed

        db.commit()
        # quest 승인 기록은 배지/카운트에 반영되므로 대시보드 슬라이스 캐시를 무효화한다.
        from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches

        invalidate_all_dashboard_slice_caches()

        next_stage_for_response = None
        if is_complete:
            CODE_TO_STAGE_NAME = {v: k for k, v in STAGE_NAME_TO_CODE.items()}
            if transition_result is not None:
                # 전이가 실제로 일어났으면 엔진이 쓴 현재 stage 가 정답(추정값 금지).
                next_stage_code = order.erp_stage_code
            else:
                next_stage_code = get_next_stage_for_completed_quest(current_stage_name)
            if next_stage_code:
                next_stage_for_response = CODE_TO_STAGE_NAME.get(next_stage_code, next_stage_code)

        return jsonify({
            'success': True,
            'quest': current_quest,
            'all_approved': is_complete,
            'missing_teams': missing_teams,
            'auto_transitioned': auto_transitioned,
            'next_stage': next_stage_for_response,
        })
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            log_handled_exception("quest rollback")
        log_handled_exception()
        return jsonify({'success': False, 'message': str(e)}), 500


@quest_bp.route('/orders/<int:order_id>/quest/status', methods=['PUT'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_order_quest_update_status(order_id):
    """Quest 상태 수동 업데이트 (OPEN, IN_PROGRESS, COMPLETED)"""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        payload = request.get_json(silent=True) or {}
        status = payload.get('status')
        owner_person = payload.get('owner_person')

        if status not in ['OPEN', 'IN_PROGRESS', 'COMPLETED']:
            return jsonify({'success': False, 'message': '유효하지 않은 상태입니다.'}), 400

        sd = order.structured_data or {}
        current_stage = get_stage(sd)

        if not current_stage:
            return jsonify({'success': False, 'message': '현재 단계가 없습니다.'}), 400

        quests = sd.get("quests") or []
        quest_index = -1
        for i, q in enumerate(quests):
            if isinstance(q, dict) and q.get("stage") == current_stage:
                quest_index = i
                break

        if quest_index == -1:
            return jsonify({'success': False, 'message': 'Quest를 찾을 수 없습니다.'}), 404

        now = datetime.datetime.now()
        quests[quest_index]["status"] = status
        quests[quest_index]["updated_at"] = now.isoformat()

        if owner_person:
            quests[quest_index]["owner_person"] = owner_person

        if status == "COMPLETED" and not quests[quest_index].get("completed_at"):
            quests[quest_index]["completed_at"] = now.isoformat()

        sd["quests"] = quests
        order.structured_data = sd
        order.updated_at = now
        _audit_quest(order, "QUEST_STATUS_CHANGED", session.get('user_id'), note=status,
                     extra={"status": status})
        db.commit()
        # Tier A(broad): quest 상태 변경은 stage 전환으로 이어질 수 있어 탭 간 이동 발생.
        from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches

        invalidate_all_dashboard_slice_caches()

        return jsonify({'success': True, 'quest': quests[quest_index]})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            log_handled_exception("quest rollback")
        log_handled_exception()
        return jsonify({'success': False, 'message': str(e)}), 500

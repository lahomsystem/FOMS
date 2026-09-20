"""
Quest API (단계별 퀘스트 시스템).
GET/POST /api/orders/<id>/quest, POST /approve, PUT /status
"""

import copy
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
from foms.services.orders.order_mutation_policy import normalize_team
from foms.services.orders.quest_approve_authz import (
    approval_slot_team as _approval_slot_team,
    authorize_quest_approve as _authorize_quest_approve,
    find_stage_quest as _find_stage_quest,
    required_teams_for_stage as _required_teams_for_stage,
)
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
    find_stage_quest_for_approve,
    stage_advance_target,
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

        # 이미 해당 단계의 quest가 있는지 확인 — quest.stage 는 한글명('실측')으로도, 코드('MEASURE')로도
        # 저장돼 있어 별칭 두 가지를 모두 본다(정확 일치만 보면 한글 저장형이 있는데 하나 더 만든다).
        sd = copy.deepcopy(order.structured_data or {})
        if not sd.get("quests"):
            sd["quests"] = []

        CODE_TO_STAGE_NAME = {v: k for k, v in STAGE_NAME_TO_CODE.items()}
        stage_name = CODE_TO_STAGE_NAME.get(stage_code, stage_code)
        existing, _existing_index = _find_stage_quest(sd, stage_name, stage_code)

        if existing:
            return jsonify({'success': False, 'message': '이미 해당 단계의 Quest가 존재합니다.'}), 400

        # Quest 생성
        owner_person = payload.get('owner_person') or session.get('username') or ''
        new_quest = create_quest_from_template(stage, owner_person, sd)

        if not new_quest:
            return jsonify({'success': False, 'message': 'Quest 템플릿을 찾을 수 없습니다.'}), 400

        sd["quests"].append(new_quest)
        # 프로젝트 규약(deepcopy → 수정 → 재대입 → flag_modified)을 따른다. 예전 버그는 로드된 dict 를
        # 제자리에서 고쳐 같은 객체를 재대입해 dirty 가 안 잡힌 것.
        order.structured_data = sd
        flag_modified(order, "structured_data")
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


# 전용 command 로만 진행하는 stage — 단독 quest 승인 거부(409). DRAWING 은 도면 전달·수령확정이
# 실제 전용 경로다. CONFIRM 은 2026-07-26 가드가 들어올 때 짝이 될 ``CUSTOMER_CONFIRM`` command
# 가 끝내 안 들어와 "승인도 못 하고 생산으로도 못 가는" 막다른 골목이었다(운영 #5193) —
# 2026-09-17 부터 CONFIRM 최종 승인은 quest 종결 + ``blueprint.customer_confirmed`` 기록 뒤
# 서비스(quest_transition_service ``CUSTOMER_CONFIRM``)로 CONFIRM→PRODUCTION 을 **전이한다**.
_COMMAND_REQUIRED_STAGES = frozenset({"DRAWING"})

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


def _already_transitioned_into(sd, current_stage_code: str) -> bool:
    """종결(COMPLETED)된 quest 중 다음 단계가 ``current_stage_code`` 인 것이 있는가.

    있으면 이 단계는 그 quest 의 최종 승인으로 이미 들어온 것이고, 현 단계 quest 가 없는
    상태에서 팀 없이 온 승인 요청은 전이 직후의 재요청이다.
    """
    quests = sd.get('quests')
    if not isinstance(quests, list):
        return False
    for quest in quests:
        if not isinstance(quest, dict):
            continue
        if str(quest.get('status', 'OPEN')).upper() != 'COMPLETED':
            continue
        raw = quest.get('stage')
        code = STAGE_NAME_TO_CODE.get(raw, raw)
        if stage_advance_target(code) == current_stage_code:
            return True
    return False


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

        # DRAWING 단독 승인은 전용 경로(도면 전달·수령확정)로만 — command-required 거부.
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

        # 같은 단계 quest 가 여럿이면 표시 SSOT 와 같은 규칙(활성 최신 → 완료 최신)으로 고른다.
        current_quest, quest_index = find_stage_quest_for_approve(sd, current_stage_name, current_stage_code)

        if not current_quest:
            # 전이 직후의 stale 재요청(연타·같은 키·옛 화면) 방어. 예: 고객 컨펌 최종 승인으로
            # stage 가 PRODUCTION 이 된 뒤 같은 버튼이 다시 오면 현 단계 quest 가 없어
            # 템플릿으로 PRODUCTION quest 를 만들고 무관한 팀 승인을 남겨 제작 완료 게이트를
            # 잠갔다(2026-09-20 CEO 판정 P1). 팀을 명시하지 않은 요청이고, 이미 종결된 quest 의
            # 다음 단계가 지금 단계면 그 요청은 이미 처리된 것이다.
            if not team and _already_transitioned_into(sd, current_stage_code):
                return jsonify({
                    'success': False,
                    'code': 'ALREADY_TRANSITIONED',
                    'message': (
                        f'이미 {STAGE_LABELS.get(current_stage_code, current_stage_code)} '
                        f'단계로 넘어간 주문입니다. 화면을 새로고침하세요.'
                    ),
                }), 409
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

        # ── 재전이: 강제 단계 변경(regress)으로 되돌아온 뒤 완료 quest 가 그대로 남아 있으면
        # 승인 기록(assignee_approval·team_approvals·completed_at)은 손대지 않고 전이만 다시 건다.
        # 예전엔 이 경로가 승인 기록을 actor 로 덮어쓰고 가짜 QUEST_APPROVAL_CHANGED 를 남겼다
        # (2026-09-20 스테이징 #4382). 다음 단계가 없는 COMPLETED(PRODUCTION/CS 등)는 대상이 아니다.
        # 활성 quest 가 있으면 그 quest 를 잡아 정상 승인 경로를 탄다(2026-09-20 리뷰 P2).
        is_retransition = (
            str(current_quest.get('status', 'OPEN')).upper() == 'COMPLETED'
            and stage_advance_target(current_stage_code) is not None
        )
        if is_retransition:
            _audit_quest(order, 'QUEST_APPROVED', user_id, note='재전이',
                         extra={'team': team, 'retransition': True})
            try:
                transition_result = advance_stage_on_quest_completion(
                    db,
                    order_id=order.id,
                    actor_user_id=user_id,
                    scope_hash=_scope_hash(_QUEST_APPROVE_COMMAND, order.id),
                    request_hash=_request_hash(payload),
                    idempotency_key=_idempotency_key(payload),
                    reason=f'{current_stage_name} 재전이(완료 quest, 강제 단계 변경 뒤)',
                    source_screen='erp_dashboard',
                    now=now,
                )
            except (TransitionError, RevisionError) as exc:
                db.rollback()
                return _transition_error_response(exc)
            db.commit()
            from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches

            invalidate_all_dashboard_slice_caches()
            next_code = order.erp_stage_code
            return jsonify({
                'success': True,
                'quest': current_quest,
                'all_approved': True,
                'missing_teams': [],
                'auto_transitioned': transition_result is not None and not transition_result.replayed,
                'retransitioned': True,
                'next_stage': CODE_TO_STAGE_NAME.get(next_code, next_code),
            })

        # 승인 슬롯 팀: actor 의 소속 팀이 아니라 **필수 팀 중 actor 가 자격을 갖는 팀**이다.
        # 완료 판정(check_quest_approvals_complete)이 필수 팀 이름으로 정확 일치만 보기 때문에,
        # 경리팀(ACCOUNTING)이 CS 필수 quest 를 승인하면 슬롯 키는 CS 여야 그 칸이 채워진다.
        # 실제로 누른 팀은 아래 슬롯 값의 by_team 에 원문 그대로 남긴다.
        effective_team = _approval_slot_team(
            db, user, order, current_stage_code, current_quest,
            payload_team=team, emergency_override=emergency_override,
        ) or actor_team

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
                # 슬롯 키는 필수 팀이라 실제로 누른 팀이 지워진다 — 정규화 전 원문을 남긴다.
                "by_team": (user.team or "").strip().upper(),
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

        # 고객컨펌 최종 승인 = 고객 컨펌 완료 사실. quest 종결과 같은 tx 로 blueprint 에 남긴다
        # (도면 revision 감사가 ``blueprint.customer_confirmed`` 를 고객확인 축으로 읽는다).
        if is_complete and current_stage_code == 'CONFIRM':
            blueprint = sd.get("blueprint")
            if not isinstance(blueprint, dict):
                blueprint = {}
            blueprint["customer_confirmed"] = True
            blueprint["confirmed_at"] = now.isoformat()
            blueprint["confirmed_by"] = username
            sd["blueprint"] = blueprint

        order.structured_data = sd
        flag_modified(order, "structured_data")
        order.updated_at = now
        sync_erp_flat_columns(order, sd)
        _audit_quest(order, "QUEST_APPROVED", user_id, note=team, extra={"team": team})

        # 최종 승인 → stage 전이(STATE-QUEST-01). 라우트는 stage 를 직접 쓰지 않고 정본 서비스에
        # 위임한다. 승인 기록을 먼저 order 에 반영해 두어야 전이 엔진의 structured_data 스냅샷에
        # 승인이 포함된다(승인·전이가 한 tx·한 commit 에 원자적으로 남는다).
        # RECEIVED→MEASURE, MEASURE→DRAWING, CONFIRM→PRODUCTION 만 advance 하고 그 밖의 stage 는
        # None(no-op).
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
            'retransitioned': False,
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
        reason = str(payload.get('reason') or '').strip()

        if status not in ['OPEN', 'IN_PROGRESS', 'COMPLETED']:
            return jsonify({'success': False, 'message': '유효하지 않은 상태입니다.'}), 400

        user_id = session.get('user_id')
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401

        # 수동 COMPLETED 는 승인 없이 단계 게이트를 여는 행위라 관리자만, 사유 필수.
        if status == 'COMPLETED':
            role = (user.role or '').strip().upper()
            if role not in ('ADMIN', 'MANAGER'):
                return jsonify({
                    'success': False,
                    'code': 'ROLE_REQUIRED',
                    'message': '퀘스트 수동 완료는 관리자만 할 수 있습니다.',
                }), 403
            if not reason:
                return jsonify({
                    'success': False,
                    'code': 'REASON_REQUIRED',
                    'message': '사유를 입력하세요.',
                }), 400

        sd = copy.deepcopy(order.structured_data or {})
        current_stage_code = get_stage(sd)

        if not current_stage_code:
            return jsonify({'success': False, 'message': '현재 단계가 없습니다.'}), 400

        # quest.stage 는 한글명 또는 코드 — approve 라우트와 같은 별칭 매칭(정확 일치만 보면
        # '고객컨펌' 저장형을 stage CONFIRM 에서 못 찾아 404 였다).
        CODE_TO_STAGE_NAME = {v: k for k, v in STAGE_NAME_TO_CODE.items()}
        current_stage_name = CODE_TO_STAGE_NAME.get(current_stage_code, current_stage_code)
        quest, quest_index = _find_stage_quest(sd, current_stage_name, current_stage_code)

        if not quest:
            return jsonify({'success': False, 'message': 'Quest를 찾을 수 없습니다.'}), 404

        now = datetime.datetime.now()
        new_q = dict(quest)
        new_q["status"] = status
        new_q["updated_at"] = now.isoformat()

        if owner_person:
            new_q["owner_person"] = owner_person

        if status == "COMPLETED":
            if not new_q.get("completed_at"):
                new_q["completed_at"] = now.isoformat()
            new_q["manual_status"] = {
                "status": status, "by": user_id, "at": now.isoformat(), "reason": reason,
            }

        quests = list(sd.get("quests") or [])
        quests[quest_index] = new_q
        sd["quests"] = quests
        order.structured_data = sd
        flag_modified(order, "structured_data")
        order.updated_at = now
        _audit_quest(order, "QUEST_STATUS_CHANGED", user_id, note=status,
                     extra={"status": status, "reason": reason})
        db.commit()
        # Tier A(broad): quest 상태 변경은 stage 전환으로 이어질 수 있어 탭 간 이동 발생.
        from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches

        invalidate_all_dashboard_slice_caches()

        return jsonify({'success': True, 'quest': new_q})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            log_handled_exception("quest rollback")
        log_handled_exception()
        return jsonify({'success': False, 'message': str(e)}), 500

"""
Quest API (단계별 퀘스트 시스템).
GET/POST /api/orders/<id>/quest, POST /approve, PUT /status
"""

import datetime
from flask import Blueprint, request, jsonify, session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, User, OrderEvent
from apps.auth import login_required, role_required
from apps.erp import can_edit_erp
from services.erp_policy import (
    get_stage,
    STAGE_LABELS,
    STAGE_NAME_TO_CODE,
    get_quest_template_for_stage,
    create_quest_from_template,
    check_quest_approvals_complete,
    get_next_stage_for_completed_quest,
    get_required_approval_teams_for_stage,
    can_modify_domain,
    get_assignee_ids,
)


quest_bp = Blueprint('quest', __name__, url_prefix='/api')


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

        # quest가 없으면 템플릿에서 생성하고 DB에 저장 (한글 단계명으로 생성)
        if not current_quest:
            quest_tpl = get_quest_template_for_stage(current_stage_code)
            if quest_tpl:
                owner_person = session.get('username') or ''
                current_quest = create_quest_from_template(current_stage_code, owner_person, sd)
                if current_quest:
                    if not sd.get("quests"):
                        sd["quests"] = []
                    sd["quests"].append(current_quest)
                    order.structured_data = sd
                    order.updated_at = datetime.datetime.now()
                    db.commit()

        return jsonify({
            'success': True,
            'quest': current_quest,
            'stage': current_stage_code,
            'stage_label': STAGE_LABELS.get(current_stage_code, current_stage_code),
        })
    except Exception as e:
        import traceback
        print(f"Quest 조회 오류: {e}")
        print(traceback.format_exc())
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
        db.commit()

        return jsonify({'success': True, 'quest': new_quest})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            pass
        import traceback
        print(f"Quest 생성 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@quest_bp.route('/orders/<int:order_id>/quest/approve', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_order_quest_approve(order_id):
    """팀별/담당자 Quest 승인 및 자동 단계 전환"""
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

        # ERP Beta 주문 기본 승인 권한
        if getattr(order, 'is_erp_beta', False) and not can_edit_erp(user):
            sd_tmp = order.structured_data or {}
            stage_tmp = get_stage(sd_tmp)
            domain_tmp = None
            if stage_tmp in ('MEASURE', 'CONFIRM'):
                domain_tmp = 'SALES_DOMAIN'
            elif stage_tmp == 'DRAWING':
                domain_tmp = 'DRAWING_DOMAIN'

            can_assignee_override = False
            if domain_tmp:
                can_assignee_override = can_modify_domain(user, order, domain_tmp, emergency_override, override_reason)

                if (not can_assignee_override) and domain_tmp == 'SALES_DOMAIN':
                    allowed_ids = get_assignee_ids(order, domain_tmp)
                    if not allowed_ids:
                        manager_names = set()
                        parties_tmp = (sd_tmp.get('parties') or {}) if isinstance(sd_tmp, dict) else {}
                        manager_name_sd = ((parties_tmp.get('manager') or {}).get('name') or '').strip()
                        if manager_name_sd:
                            manager_names.add(manager_name_sd.lower())
                        manager_name_col = (order.manager_name or '').strip()
                        if manager_name_col:
                            manager_names.add(manager_name_col.lower())
                        user_name = (user.name or '').strip().lower()
                        user_username = (user.username or '').strip().lower()
                        if user_name in manager_names or user_username in manager_names:
                            can_assignee_override = True

            if not can_assignee_override:
                return jsonify({
                    'success': False,
                    'message': 'ERP Beta 수정 권한이 없습니다. (관리자, 라홈팀, 하우드팀, 영업팀 또는 지정 담당자만 가능)'
                }), 403

        sd = order.structured_data or {}
        current_stage_code = get_stage(sd)

        if not current_stage_code:
            return jsonify({'success': False, 'message': '현재 단계가 없습니다.'}), 400

        # 도면 단계는 퀘스트 승인 자체를 허용하지 않음
        if current_stage_code == 'DRAWING':
            return jsonify({
                'success': False,
                'message': '도면 단계 퀘스트 승인은 비활성화되었습니다. 도면 전달/수령 확정으로 진행해주세요.'
            }), 400

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

        username = session.get('username') or ''
        now = datetime.datetime.now()

        approval_mode = current_quest.get("approval_mode", "team")

        if approval_mode == "assignee":
            domain = None
            if current_stage_code in ('MEASURE', 'CONFIRM'):
                domain = 'SALES_DOMAIN'
            elif current_stage_code == 'DRAWING':
                domain = 'DRAWING_DOMAIN'

            if domain:
                can_modify = can_modify_domain(user, order, domain, emergency_override, override_reason)

                if (not can_modify) and domain == 'SALES_DOMAIN':
                    allowed_ids = get_assignee_ids(order, domain)
                    if not allowed_ids:
                        manager_names = set()
                        parties = (sd.get('parties') or {}) if isinstance(sd, dict) else {}
                        manager_name_sd = ((parties.get('manager') or {}).get('name') or '').strip()
                        if manager_name_sd:
                            manager_names.add(manager_name_sd.lower())
                        manager_name_col = (order.manager_name or '').strip()
                        if manager_name_col:
                            manager_names.add(manager_name_col.lower())
                        owner_person = (current_quest.get('owner_person') or '').strip()
                        if owner_person:
                            manager_names.add(owner_person.lower())
                        user_name = (user.name or '').strip().lower()
                        user_username = (user.username or '').strip().lower()
                        if user_name in manager_names or user_username in manager_names:
                            can_modify = True

                if not can_modify:
                    msg = f'{current_stage_name} 단계는 지정 담당자만 승인할 수 있습니다.'
                    if user.role == 'MANAGER':
                        msg += ' (긴급 오버라이드가 필요합니다.)'
                    return jsonify({'success': False, 'message': msg}), 403

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
            if not team:
                return jsonify({'success': False, 'message': '팀이 지정되지 않았습니다.'}), 400

            if not current_quest.get("team_approvals"):
                current_quest["team_approvals"] = {}

            current_quest["team_approvals"][team] = {
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
                'target': f'quest.team_approvals.{team}',
                'before': 'not_approved',
                'after': 'approved',
                'change_method': 'API',
                'source_screen': 'erp_dashboard',
                'reason': f'{team} 팀 승인 완료',
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

        auto_transitioned = False
        if is_complete:
            current_quest["status"] = "COMPLETED"
            current_quest["completed_at"] = now.isoformat()
            sd["quests"][quest_index] = current_quest

            if current_stage_code != 'CONFIRM':
                next_stage_code = get_next_stage_for_completed_quest(current_stage_name)
                if next_stage_code:
                    CODE_TO_STAGE_NAME = {v: k for k, v in STAGE_NAME_TO_CODE.items()}
                    next_stage_name = CODE_TO_STAGE_NAME.get(next_stage_code, next_stage_code)

                    workflow = sd.get("workflow") or {}
                    old_stage = workflow.get("stage")
                    workflow["stage"] = next_stage_code
                    workflow["stage_updated_at"] = now.isoformat()
                    sd["workflow"] = workflow

                    next_quest = create_quest_from_template(next_stage_name, username, sd)
                    if next_quest:
                        if not sd.get("quests"):
                            sd["quests"] = []
                        sd["quests"].append(next_quest)

                    ev = OrderEvent(
                        order_id=order.id,
                        event_type='STAGE_AUTO_TRANSITIONED',
                        payload={
                            'from': old_stage,
                            'to': next_stage_code,
                            'reason': 'quest_approvals_complete',
                            'approved_teams': get_required_approval_teams_for_stage(current_stage_name),
                        },
                        created_by_user_id=user_id
                    )
                    db.add(ev)
                    auto_transitioned = True

        order.structured_data = sd
        flag_modified(order, "structured_data")
        order.updated_at = now
        db.commit()

        next_stage_for_response = None
        if is_complete:
            next_stage_code = get_next_stage_for_completed_quest(current_stage_name)
            if next_stage_code:
                CODE_TO_STAGE_NAME = {v: k for k, v in STAGE_NAME_TO_CODE.items()}
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
            pass
        import traceback
        print(f"Quest 승인 오류: {e}")
        print(traceback.format_exc())
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
        db.commit()

        return jsonify({'success': True, 'quest': quests[quest_index]})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            pass
        import traceback
        print(f"Quest 상태 업데이트 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

"""
ERP 주문 도면 담당자 지정/확정 API. (Phase 4-5e)
erp.py에서 분리: assign-draftsman, batch-assign-draftsman, confirm-drawing-receipt.
"""
import copy
from datetime import datetime

from flask import Blueprint, request, jsonify, session

from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, User, OrderAttachment, OrderEvent, SecurityLog
from apps.auth import login_required, get_user_by_id
from services.erp_permissions import erp_edit_required
from apps.erp import _ensure_dict
from services.erp_policy import can_modify_domain, get_assignee_ids
from services.storage import get_storage

erp_orders_draftsman_bp = Blueprint(
    'erp_orders_draftsman',
    __name__,
    url_prefix='/api/orders',
)


@erp_orders_draftsman_bp.route('/batch-assign-draftsman', methods=['POST'])
@login_required
def api_orders_batch_assign_draftsman():
    """여러 주문에 도면 담당자 일괄 지정"""
    db = None
    try:
        data = request.get_json() or {}
        order_ids = data.get('order_ids', [])
        user_ids = data.get('user_ids', [])
        emergency_override = data.get('emergency_override', False)
        override_reason = str(data.get('override_reason', '') or '').strip()

        if not order_ids:
            return jsonify({'success': False, 'message': '주문을 선택해주세요.'}), 400
        if not user_ids:
            return jsonify({'success': False, 'message': '담당자를 선택해주세요.'}), 400

        db = get_db()

        user_id = session.get('user_id')
        current_user = get_user_by_id(user_id)
        if not current_user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401

        team_code = (current_user.team or '').strip()
        if current_user.role != 'ADMIN' and team_code != 'DRAWING':
            return jsonify({'success': False, 'message': '도면 담당자 지정 권한이 없습니다. (관리자/도면팀만 가능)'}), 403

        assigned_users = db.query(User).filter(User.id.in_(user_ids), User.is_active == True).all()
        non_drawing = [u for u in assigned_users if (u.team or '').strip() != 'DRAWING']
        if non_drawing:
            names = ', '.join([u.name for u in non_drawing])
            return jsonify({
                'success': False,
                'message': f'도면 담당자는 도면팀 소속만 지정할 수 있습니다. (도면팀이 아닌 사용자: {names})'
            }), 400
        if len(assigned_users) != len(user_ids):
            return jsonify({'success': False, 'message': '일부 사용자를 찾을 수 없거나 비활성 계정입니다.'}), 400

        assignee_list = [{'id': u.id, 'name': u.name, 'team': u.team} for u in assigned_users]
        assignee_names = ", ".join([u.name for u in assigned_users])

        orders = db.query(Order).filter(Order.id.in_(order_ids)).all()
        if len(orders) != len(order_ids):
            return jsonify({'success': False, 'message': '일부 주문을 찾을 수 없습니다.'}), 400

        success_count = 0
        failed_orders = []

        for order in orders:
            try:
                s_data: dict = _ensure_dict(order.structured_data)

                if 'assignments' not in s_data:
                    s_data['assignments'] = {}
                s_data['assignments']['drawing_assignee_user_ids'] = user_ids

                s_data['drawing_assignees'] = assignee_list

                shipment: dict = s_data.get('shipment') or {}
                shipment['drawing_managers'] = [u.name for u in assigned_users]
                s_data['shipment'] = shipment

                wf: dict = s_data.get('workflow') or {}
                hist: list = wf.get('history') or []
                hist.append({
                    'stage': wf.get('stage', 'DRAWING'),
                    'updated_at': datetime.now().isoformat(),
                    'updated_by': current_user.name if current_user else 'Unknown',
                    'note': f'도면 담당자 일괄 지정: {assignee_names}'
                })
                wf['history'] = hist
                s_data['workflow'] = wf

                order.structured_data = copy.deepcopy(s_data)
                flag_modified(order, "structured_data")

                event_payload = {
                    'domain': 'DRAWING_DOMAIN',
                    'action': 'DRAWING_ASSIGNEE_SET',
                    'target': 'assignments.drawing_assignee_user_ids',
                    'after': assignee_names,
                    'after_ids': user_ids,
                    'assignee_names': [u.name for u in assigned_users],
                    'assignee_user_ids': user_ids,
                    'change_method': 'BATCH_API',
                    'source_screen': 'drawing_workbench_dashboard',
                    'reason': '도면 담당자 일괄 지정',
                }
                drawing_event = OrderEvent(
                    order_id=order.id,
                    event_type='DRAWING_ASSIGNEE_SET',
                    payload=event_payload,
                    created_by_user_id=user_id
                )
                db.add(drawing_event)
                success_count += 1

            except Exception as e:
                failed_orders.append(f"#{order.id}: {str(e)}")
                continue

        db.commit()

        message = f'{success_count}건의 주문에 담당자가 지정되었습니다: {assignee_names}'
        if failed_orders:
            message += f' (실패: {len(failed_orders)}건)'

        return jsonify({
            'success': True,
            'message': message,
            'success_count': success_count,
            'failed_count': len(failed_orders),
            'failed_orders': failed_orders
        })

    except Exception as e:
        if db:
            db.rollback()
        import traceback
        print(f"Batch Assign Draftsman Error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_draftsman_bp.route('/<int:order_id>/assign-draftsman', methods=['POST'])
@login_required
def api_order_assign_draftsman(order_id):
    """도면 담당자 지정 (다수 가능)"""
    try:
        data = request.get_json() or {}
        user_ids = data.get('user_ids', [])
        emergency_override = data.get('emergency_override', False)
        override_reason = str(data.get('override_reason', '') or '').strip()

        if not user_ids:
            return jsonify({'success': False, 'message': '담당자를 선택해주세요.'}), 400

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        user_id = session.get('user_id')
        current_user = get_user_by_id(user_id)
        if not current_user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401

        team_code = (current_user.team or '').strip()
        can_assign_drawing_assignee = (
            current_user.role == 'ADMIN'
            or team_code == 'DRAWING'
            or can_modify_domain(current_user, order, 'DRAWING_DOMAIN', emergency_override, override_reason)
        )
        if not can_assign_drawing_assignee:
            msg = '도면 담당자 지정 권한이 없습니다. (관리자/도면팀/지정 도면담당자만 가능)'
            if current_user.role == 'MANAGER':
                msg += ' (긴급 오버라이드가 필요합니다.)'
            return jsonify({'success': False, 'message': msg}), 403

        assigned_users = db.query(User).filter(User.id.in_(user_ids), User.is_active == True).all()
        non_drawing = [u for u in assigned_users if (u.team or '').strip() != 'DRAWING']
        if non_drawing:
            names = ', '.join([u.name for u in non_drawing])
            return jsonify({
                'success': False,
                'message': f'도면 담당자는 도면팀 소속만 지정할 수 있습니다. (도면팀이 아닌 사용자: {names})'
            }), 400
        if len(assigned_users) != len(user_ids):
            return jsonify({'success': False, 'message': '일부 사용자를 찾을 수 없거나 비활성 계정입니다.'}), 400

        assignee_list = [{'id': u.id, 'name': u.name, 'team': u.team} for u in assigned_users]

        s_data: dict = _ensure_dict(order.structured_data)

        old_assignees = s_data.get('drawing_assignees', [])
        old_names = [a.get('name', '') for a in old_assignees if isinstance(a, dict)]
        
        assignments_dict = s_data.get('assignments', {})
        old_ids = assignments_dict.get('drawing_assignee_user_ids', []) if isinstance(assignments_dict, dict) else []

        if not isinstance(s_data.get('assignments'), dict):
            s_data['assignments'] = {}
        s_data['assignments']['drawing_assignee_user_ids'] = user_ids

        s_data['drawing_assignees'] = assignee_list

        shipment: dict = s_data.get('shipment', {})
        if not isinstance(shipment, dict):
            shipment = {}
        shipment['drawing_managers'] = [u.name for u in assigned_users]
        s_data['shipment'] = shipment

        wf: dict = s_data.get('workflow') or {}
        hist: list = wf.get('history') or []
        names = ", ".join([u.name for u in assigned_users])
        hist.append({
            'stage': wf.get('stage', 'DRAWING'),
            'updated_at': datetime.now().isoformat(),
            'updated_by': current_user.name if current_user else 'Unknown',
            'note': f'도면 담당자 지정: {names}'
        })
        wf['history'] = hist
        s_data['workflow'] = wf

        order.structured_data = copy.deepcopy(s_data)
        flag_modified(order, "structured_data")

        event_payload = {
            'domain': 'DRAWING_DOMAIN',
            'action': 'DRAWING_ASSIGNEE_SET',
            'target': 'assignments.drawing_assignee_user_ids',
            'before': ', '.join(old_names) if old_names else 'None',
            'after': names,
            'before_ids': old_ids,
            'after_ids': user_ids,
            'assignee_names': [u.name for u in assigned_users],
            'assignee_user_ids': user_ids,
            'change_method': 'API',
            'source_screen': 'erp_drawing_dashboard',
            'reason': '도면 담당자 지정',
            'is_override': emergency_override,
            'override_reason': override_reason if emergency_override else None,
        }
        drawing_event = OrderEvent(
            order_id=order_id,
            event_type='DRAWING_ASSIGNEE_SET',
            payload=event_payload,
            created_by_user_id=user_id
        )
        db.add(drawing_event)
        db.commit()

        return jsonify({'success': True, 'message': f'도면 담당자가 지정되었습니다: {names}'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_draftsman_bp.route('/<int:order_id>/confirm-drawing-receipt', methods=['POST'])
@login_required
@erp_edit_required
def api_order_confirm_drawing_receipt(order_id):
    """도면 수령 확인 (영업/담당자) -> 다음 단계(고객컨펌 등)로 자동 이동"""
    db = None
    try:
        data = request.get_json(silent=True) or {}
        emergency_override = data.get('emergency_override', False)
        override_reason = str(data.get('override_reason', '') or '').strip()

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        s_data: dict = _ensure_dict(order.structured_data)

        current_user = get_user_by_id(session.get('user_id'))
        if not current_user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401

        can_confirm_receipt = can_modify_domain(
            current_user, order, 'SALES_DOMAIN', emergency_override, override_reason
        )

        if not can_confirm_receipt:
            sales_assignee_ids = get_assignee_ids(order, 'SALES_DOMAIN')
            if not sales_assignee_ids:
                manager_names = set()
                parties = (s_data.get('parties') or {}) if isinstance(s_data, dict) else {}
                manager_name_sd = ((parties.get('manager') or {}).get('name') or '').strip()
                if manager_name_sd:
                    manager_names.add(manager_name_sd.lower())

                manager_name_col = (order.manager_name or '').strip()
                if manager_name_col:
                    manager_names.add(manager_name_col.lower())

                wf_tmp = (s_data.get('workflow') or {}) if isinstance(s_data, dict) else {}
                current_quest = (wf_tmp.get('current_quest') or {})
                owner_person = (current_quest.get('owner_person') or '').strip()
                if owner_person:
                    manager_names.add(owner_person.lower())

                user_name = (current_user.name or '').strip().lower()
                user_username = (current_user.username or '').strip().lower()
                if user_name in manager_names or user_username in manager_names:
                    can_confirm_receipt = True

        if not can_confirm_receipt:
            msg = '도면 수령 확인은 지정된 영업 담당자만 가능합니다.'
            if current_user.role == 'MANAGER':
                msg += ' (긴급 오버라이드가 필요합니다.)'
            return jsonify({'success': False, 'message': msg}), 403

        old_drawing_status = s_data.get('drawing_status', 'UNKNOWN')
        s_data['drawing_status'] = 'CONFIRMED'
        s_data['drawing_confirmed_at'] = datetime.now().isoformat()
        s_data['drawing_confirmed_by'] = current_user.name

        next_stage = 'CONFIRM'

        wf: dict = s_data.get('workflow') or {}
        old_stage = wf.get('stage', 'DRAWING')
        wf['stage'] = next_stage
        wf['stage_updated_at'] = datetime.now().isoformat()
        wf['stage_updated_by'] = current_user.name

        hist: list = wf.get('history') or []
        hist.append({
            'stage': next_stage,
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': '도면 수령 확인 및 단계 이동'
        })
        wf['history'] = hist
        s_data['workflow'] = wf

        order.structured_data = copy.deepcopy(s_data)
        flag_modified(order, "structured_data")
        order.status = next_stage

        event_payload = {
            'domain': 'SALES_DOMAIN',
            'action': 'DRAWING_STATUS_CHANGED',
            'target': 'drawing_status',
            'before': old_drawing_status,
            'after': 'CONFIRMED',
            'change_method': 'API',
            'source_screen': 'erp_drawing_dashboard',
            'reason': '도면 수령 확인',
            'is_override': emergency_override,
            'override_reason': override_reason if emergency_override else None,
        }
        drawing_confirm_event = OrderEvent(
            order_id=order_id,
            event_type='DRAWING_STATUS_CHANGED',
            payload=event_payload,
            created_by_user_id=current_user.id
        )
        db.add(drawing_confirm_event)

        db.add(SecurityLog(user_id=current_user.id, message=f"주문 #{order_id} 도면 확정 및 단계 이동 ({old_stage} -> {next_stage})"))

        db.commit()

        # ── 구 버전 도면 파일 R2 정리 ────────────────────────────────────────────
        # drawing_current_files 에 있는 키만 최종본으로 인정하고,
        # 이전 TRANSFER/REPLACE 히스토리에서 현재 최종본에 없는 파일들을 삭제한다.
        try:
            current_file_keys = set()
            for f in (s_data.get('drawing_current_files') or []):
                if isinstance(f, dict):
                    k = (f.get('key') or '').strip()
                    if k:
                        current_file_keys.add(k)

            # 모든 TRANSFER 히스토리 항목에서 파일 키 수집
            old_keys_to_delete = set()
            for h in (s_data.get('drawing_transfer_history') or []):
                if not isinstance(h, dict):
                    continue
                # TRANSFER 이력의 files 와 previous_current_files 모두 검사
                for field in ('files', 'previous_current_files'):
                    for f in (h.get(field) or []):
                        if isinstance(f, dict):
                            k = (f.get('key') or '').strip()
                            if k and k not in current_file_keys:
                                old_keys_to_delete.add(k)

            if old_keys_to_delete:
                storage = get_storage()
                rows = db.query(OrderAttachment).filter(
                    OrderAttachment.order_id == order_id,
                    OrderAttachment.storage_key.in_(list(old_keys_to_delete))
                ).all()
                deleted_row_keys = set()
                for row in rows:
                    try:
                        if row.storage_key:
                            storage.delete_file(row.storage_key)
                            deleted_row_keys.add(row.storage_key)
                        if row.thumbnail_key:
                            storage.delete_file(row.thumbnail_key)
                    except Exception:
                        pass
                    db.delete(row)
                for key in old_keys_to_delete:
                    if key not in deleted_row_keys:
                        try:
                            storage.delete_file(key)
                        except Exception:
                            pass
                # ← DB 레코드 삭제 반드시 커밋 (없으면 빈 카드가 목록에 남음)
                db.commit()
        except Exception as cleanup_err:
            import traceback
            print(f"[WARN] 수령 확정 구 버전 파일 정리 중 오류 (주문 #{order_id}): {cleanup_err}")
            print(traceback.format_exc())
            # 파일 정리 실패는 치명적 오류가 아니므로 계속 진행

        return jsonify({'success': True, 'message': '도면이 확정되었습니다. 다음 단계로 이동합니다.', 'new_stage': next_stage})

    except Exception as e:
        if db is not None:
            db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

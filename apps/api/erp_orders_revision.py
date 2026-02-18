"""
ERP 주문 도면 수정 요청/체크 API. (Phase 4-5d, 4-5h)
erp.py에서 분리: request-revision, request-revision-check, drawing/request-revision, drawing/complete-revision.
"""
import copy
import datetime

from flask import Blueprint, request, jsonify, session

from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, Notification, SecurityLog
from apps.auth import login_required, get_user_by_id
from apps.erp import erp_edit_required, _ensure_dict, _can_modify_sales_domain
from services.erp_policy import can_modify_domain

erp_orders_revision_bp = Blueprint(
    'erp_orders_revision',
    __name__,
    url_prefix='/api/orders',
)


@erp_orders_revision_bp.route('/<int:order_id>/request-revision', methods=['POST'])
@login_required
@erp_edit_required
def api_order_request_revision(order_id):
    """도면 수정 요청 (영업/담당자)

    Phase 2 개선:
    - target_drawing_keys (배열): 다중 도면 수정 요청 지원
    - target_drawing_key (단일): 호환성 유지
    """
    try:
        from datetime import datetime
        data = request.get_json() or {}
        note = data.get('note', '')
        files = data.get('files', []) if isinstance(data.get('files', []), list) else []
        target_drawing_key = (data.get('target_drawing_key') or '').strip()
        target_drawing_keys = data.get('target_drawing_keys') or []

        if target_drawing_key and target_drawing_key not in target_drawing_keys:
            target_drawing_keys = [target_drawing_key]
        elif not target_drawing_keys:
            target_drawing_keys = []

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        s_data = dict(order.structured_data or {})
        current_files = list(s_data.get('drawing_current_files', []) or [])

        current_user = get_user_by_id(session.get('user_id'))
        if not current_user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401
        if not _can_modify_sales_domain(current_user, order, s_data, False, None):
            msg = '도면 수정 요청 권한이 없습니다. (지정된 주문 담당자만 가능)'
            if current_user.role == 'MANAGER':
                msg += ' (긴급 오버라이드가 필요합니다.)'
            return jsonify({'success': False, 'message': msg}), 403

        target_drawing_numbers = []
        if current_files:
            if not target_drawing_keys and len(current_files) > 1:
                return jsonify({'success': False, 'message': '수정 요청할 도면 번호를 선택해주세요.'}), 400

            if target_drawing_keys:
                for target_key in target_drawing_keys:
                    found = False
                    for idx, f in enumerate(current_files):
                        if ((f or {}).get('key') or '').strip() == target_key:
                            target_drawing_numbers.append(idx + 1)
                            found = True
                            break
                    if not found:
                        return jsonify({'success': False, 'message': f'선택한 수정 대상 도면을 찾을 수 없습니다: {target_key}'}), 400
            elif len(current_files) == 1:
                only_key = ((current_files[0] or {}).get('key') or '').strip()
                if only_key:
                    target_drawing_keys = [only_key]
                    target_drawing_numbers = [1]

        if s_data.get('drawing_status') not in ['TRANSFERRED', 'CONFIRMED']:
            return jsonify({'success': False, 'message': '도면 전달(확정 대기) 상태에서만 수정 요청 가능합니다.'}), 400

        s_data['drawing_status'] = 'RETURNED'

        history = list(s_data.get('drawing_transfer_history', []))
        history.append({
            'action': 'REQUEST_REVISION',
            'by_user_id': session.get('user_id'),
            'by_user_name': current_user.name,
            'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'note': note,
            'files': files,
            'files_count': len(files),
            'target_drawing_keys': target_drawing_keys if target_drawing_keys else None,
            'target_drawing_numbers': target_drawing_numbers if target_drawing_numbers else None,
            'target_drawing_key': target_drawing_keys[0] if len(target_drawing_keys) == 1 else None,
            'target_drawing_number': target_drawing_numbers[0] if len(target_drawing_numbers) == 1 else None,
        })
        s_data['drawing_transfer_history'] = history

        order.structured_data = s_data

        msg = f"주문 #{order_id} 도면 수정 요청이 접수되었습니다."
        if target_drawing_numbers:
            if len(target_drawing_numbers) == 1:
                msg += f" 대상: {target_drawing_numbers[0]}번 도면."
            else:
                msg += f" 대상: {', '.join(map(str, target_drawing_numbers))}번 도면 ({len(target_drawing_numbers)}건)."
        msg += f" 메모: {note}"
        if files:
            msg += f" (첨부 {len(files)}건)"
        db.add(Notification(
            order_id=order_id,
            notification_type='DRAWING_REVISION',
            target_team='DRAWING',
            title='도면 수정 요청',
            message=msg,
            created_by_user_id=session.get('user_id'),
            created_by_name=current_user.name
        ))
        db.add(SecurityLog(user_id=session.get('user_id'), message=f"주문 #{order_id} 도면 수정 요청"))
        db.commit()

        return jsonify({'success': True, 'message': '도면 수정 요청이 전송되었습니다.'})
    except Exception as e:
        db.rollback()
        import traceback
        print(f"Request Revision Error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_revision_bp.route('/<int:order_id>/request-revision-check', methods=['POST'])
@login_required
def api_order_request_revision_check(order_id):
    """도면 수정요청 반영 체크 토글 (요청사항 탭 체크리스트 저장)"""
    db = None
    try:
        data = request.get_json(silent=True) or {}
        request_at = str(data.get('request_at') or '').strip()
        by_user_id_raw = data.get('by_user_id')
        checked = bool(data.get('checked'))

        if not request_at:
            return jsonify({'success': False, 'message': '요청 식별값(request_at)이 필요합니다.'}), 400

        by_user_id = None
        try:
            if by_user_id_raw not in (None, ''):
                by_user_id = int(by_user_id_raw)
        except (TypeError, ValueError):
            by_user_id = None

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        s_data = _ensure_dict(order.structured_data)
        current_user = get_user_by_id(session.get('user_id'))
        if not current_user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401

        can_toggle = (
            current_user.role == 'ADMIN'
            or can_modify_domain(current_user, order, 'DRAWING_DOMAIN', False, None)
            or _can_modify_sales_domain(current_user, order, s_data, False, None)
        )
        if not can_toggle:
            return jsonify({'success': False, 'message': '권한이 없습니다. (지정 담당자 또는 관리자만 가능)'}), 403

        history = list(s_data.get('drawing_transfer_history', []) or [])
        if not history:
            return jsonify({'success': False, 'message': '도면 창구 이력이 없습니다.'}), 404

        matched_idx = -1
        for i in range(len(history) - 1, -1, -1):
            h = history[i]
            if not isinstance(h, dict):
                continue
            if (h.get('action') or '') != 'REQUEST_REVISION':
                continue
            at_val = str(h.get('at') or h.get('transferred_at') or '').strip()
            if at_val != request_at:
                continue
            if by_user_id is not None:
                try:
                    h_uid = int(h.get('by_user_id'))
                except (TypeError, ValueError):
                    h_uid = None
                if h_uid != by_user_id:
                    continue
            matched_idx = i
            break

        if matched_idx < 0:
            return jsonify({'success': False, 'message': '해당 수정 요청을 찾을 수 없습니다.'}), 404

        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        target = dict(history[matched_idx] or {})
        target['review_check'] = {
            'checked': checked,
            'checked_at': now_str if checked else None,
            'checked_by_user_id': session.get('user_id') if checked else None,
            'checked_by_name': (current_user.name if current_user else '') if checked else None,
        }
        history[matched_idx] = target
        s_data['drawing_transfer_history'] = history

        order.structured_data = copy.deepcopy(s_data)
        flag_modified(order, 'structured_data')

        db.add(SecurityLog(
            user_id=session.get('user_id'),
            message=f"주문 #{order_id} 도면 수정요청 반영 체크 {'완료' if checked else '해제'}"
        ))
        db.commit()

        return jsonify({
            'success': True,
            'message': '요청 반영 체크가 저장되었습니다.' if checked else '요청 반영 체크가 해제되었습니다.'
        })
    except Exception as e:
        if db is not None:
            db.rollback()
        import traceback
        print(f"Request Revision Check Error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_revision_bp.route('/<int:order_id>/drawing/request-revision', methods=['POST'])
@login_required
@erp_edit_required
def api_drawing_request_revision(order_id):
    """도면 수정 요청 (고객 컨펌 또는 생산 단계에서) - Blueprint V3: blueprint.revisions 구조"""
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        data = request.get_json() or {}
        feedback = data.get('feedback', '')
        requested_by = data.get('requested_by', 'customer')

        user_id = session.get('user_id')
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)
        blueprint = sd.get('blueprint') or {}
        revisions = blueprint.get('revisions') or []

        revision_entry = {
            'id': len(revisions) + 1,
            'requested_at': datetime.datetime.now().isoformat(),
            'requested_by': requested_by,
            'requester_name': user.name if user else 'Unknown',
            'feedback': feedback,
            'status': 'PENDING',
            'revised_at': None,
            'revised_by': None
        }
        revisions.append(revision_entry)
        blueprint['revisions'] = revisions
        blueprint['revision_count'] = len(revisions)
        blueprint['has_pending_revision'] = True
        sd['blueprint'] = blueprint

        wf = sd.get('workflow') or {}
        hist = wf.get('history') or []
        requester_labels = {'customer': '고객', 'production': '생산팀'}
        hist.append({
            'stage': wf.get('stage', 'CONFIRM'),
            'updated_at': datetime.datetime.now().isoformat(),
            'updated_by': user.name if user else 'Unknown',
            'note': f'도면 수정 요청 ({requester_labels.get(requested_by, requested_by)}): {feedback}'
        })
        wf['history'] = hist
        sd['workflow'] = wf

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 도면 수정 요청: {feedback[:50]}..."))
        db.commit()

        return jsonify({
            'success': True,
            'message': '도면 수정 요청이 등록되었습니다. 도면팀에서 확인 후 수정됩니다.',
            'revision_id': revision_entry['id']
        })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_revision_bp.route('/<int:order_id>/drawing/complete-revision', methods=['POST'])
@login_required
@erp_edit_required
def api_drawing_complete_revision(order_id):
    """도면 수정 완료 (도면팀에서 수정 후)"""
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        data = request.get_json() or {}
        revision_id = data.get('revision_id')
        revision_note = data.get('note', '')

        user_id = session.get('user_id')
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)
        blueprint = sd.get('blueprint') or {}
        revisions = blueprint.get('revisions') or []

        for rev in revisions:
            if isinstance(rev, dict) and (rev.get('id') == revision_id or revision_id is None):
                if rev.get('status') == 'PENDING':
                    rev['status'] = 'COMPLETED'
                    rev['revised_at'] = datetime.datetime.now().isoformat()
                    rev['revised_by'] = user.name if user else 'Unknown'
                    rev['revision_note'] = revision_note
                    break

        pending_count = sum(1 for r in revisions if isinstance(r, dict) and r.get('status') == 'PENDING')
        blueprint['has_pending_revision'] = pending_count > 0
        blueprint['revisions'] = revisions
        sd['blueprint'] = blueprint

        wf = sd.get('workflow') or {}
        hist = wf.get('history') or []
        hist.append({
            'stage': wf.get('stage', 'DRAWING'),
            'updated_at': datetime.datetime.now().isoformat(),
            'updated_by': user.name if user else 'Unknown',
            'note': f'도면 수정 완료: {revision_note}'
        })
        wf['history'] = hist
        sd['workflow'] = wf

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 도면 수정 완료"))
        db.commit()

        return jsonify({
            'success': True,
            'message': '도면 수정이 완료되었습니다.',
            'pending_revisions': pending_count
        })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

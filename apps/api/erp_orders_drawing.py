"""
ERP 주문 도면 전달/취소/창구 업로드 API. (Phase 4-5b, 4-5c)
erp.py에서 분리: transfer-drawing, cancel-transfer, drawing-gateway-upload.
"""
import json
from datetime import datetime

from flask import Blueprint, request, jsonify, session

from db import get_db
from models import Order, OrderAttachment, Notification, SecurityLog
from apps.auth import login_required, get_user_by_id
from apps.api.notifications import (
    resolve_notification_recipient_user_ids,
    invalidate_badge_cache_for_user_ids,
)
from services.erp_permissions import erp_edit_required
from services.erp_policy import can_modify_domain, get_assignee_ids
from services.realtime_notifications import emit_erp_notification_to_users
from services.storage import get_storage

erp_orders_drawing_bp = Blueprint(
    'erp_orders_drawing',
    __name__,
    url_prefix='/api/orders',
)


@erp_orders_drawing_bp.route('/<int:order_id>/transfer-drawing', methods=['POST'])
@login_required
def api_order_transfer_drawing(order_id):
    """도면 전달 처리 (단계 변경 없이 전달 정보만 기록)"""
    db = None
    try:
        data = request.get_json() or {}
        note = data.get('note', '')
        is_retransfer = bool(data.get('is_retransfer'))
        replace_target_key = (data.get('replace_target_key') or '').strip()
        replace_target_keys = data.get('replace_target_keys') or []
        mode = (data.get('mode') or '').upper()
        emergency_override = bool(data.get('emergency_override'))
        override_reason = (data.get('override_reason') or '').strip()

        if mode == 'REPLACE_ALL':
            pass
        elif replace_target_key and replace_target_key not in replace_target_keys:
            replace_target_keys = [replace_target_key]
        elif not replace_target_keys:
            replace_target_keys = []

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        s_data = {}
        if order.structured_data:
            if isinstance(order.structured_data, dict):
                s_data = dict(order.structured_data)
            elif isinstance(order.structured_data, str):
                try:
                    s_data = json.loads(order.structured_data)
                except Exception:
                    s_data = {}

        current_user = get_user_by_id(session.get('user_id'))
        user_id = session.get('user_id')
        draw_assignee_ids = get_assignee_ids(order, 'DRAWING_DOMAIN')
        if not draw_assignee_ids:
            return jsonify({'success': False, 'message': '도면 담당자가 지정되지 않아 전달할 수 없습니다. 먼저 담당자를 지정해주세요.'}), 400

        if not current_user:
            return jsonify({'success': False, 'message': '사용자 정보를 찾을 수 없습니다.'}), 401
        can_transfer = can_modify_domain(current_user, order, 'DRAWING_DOMAIN', emergency_override, override_reason)
        if not can_transfer:
            msg = '도면 전달 권한이 없습니다. (지정된 도면 담당자만 가능)'
            if current_user.role == 'MANAGER':
                msg += ' (긴급 오버라이드가 필요합니다.)'
            return jsonify({'success': False, 'message': msg}), 403

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        user_name = current_user.name if current_user else 'Unknown'

        raw_new_files = data.get('files', [])
        new_files = []
        if isinstance(raw_new_files, list):
            for f in raw_new_files:
                if not isinstance(f, dict):
                    continue
                key = (f.get('key') or '').strip()
                if not key:
                    continue
                filename = (f.get('filename') or key.rsplit('/', 1)[-1]).strip()
                new_files.append({
                    'key': key,
                    'filename': filename,
                    'view_url': f"/api/files/view/{key}",
                    'download_url': f"/api/files/download/{key}",
                })

        old_files = list(s_data.get('drawing_current_files', []) or [])
        updated_files = list(old_files)
        replaced_target_numbers = []

        if is_retransfer and not new_files:
            return jsonify({'success': False, 'message': '수정본 재전송 시 도면 파일 업로드가 필요합니다.'}), 400

        if new_files:
            if mode == 'REPLACE_ALL':
                storage = get_storage()
                for idx, old_file in enumerate(old_files):
                    old_key = ((old_file or {}).get('key') or '').strip()
                    if old_key:
                        replaced_target_numbers.append(idx + 1)
                        try:
                            storage.delete_file(old_key)
                        except Exception:
                            pass
                        rows = db.query(OrderAttachment).filter(
                            OrderAttachment.order_id == order_id,
                            OrderAttachment.storage_key == old_key
                        ).all()
                        for row in rows:
                            try:
                                if row.thumbnail_key:
                                    storage.delete_file(row.thumbnail_key)
                            except Exception:
                                pass
                            db.delete(row)
                updated_files = list(new_files)
            elif replace_target_keys:
                indices_to_replace = []
                for target_key in replace_target_keys:
                    for i, f in enumerate(old_files):
                        if ((f or {}).get('key') or '').strip() == target_key:
                            indices_to_replace.append((i, target_key))
                            break
                if len(indices_to_replace) != len(replace_target_keys):
                    return jsonify({'success': False, 'message': '일부 교체 대상 도면을 찾을 수 없습니다. 목록을 새로고침 후 다시 시도해주세요.'}), 400
                indices_to_replace.sort(key=lambda x: x[0], reverse=True)
                storage = get_storage()
                for idx, target_key in indices_to_replace:
                    replaced_target_numbers.append(idx + 1)
                    target_item = old_files[idx] if idx < len(old_files) else {}
                    target_file_key = (target_item.get('key') or '').strip()
                    if target_file_key:
                        try:
                            storage.delete_file(target_file_key)
                        except Exception:
                            pass
                        rows = db.query(OrderAttachment).filter(
                            OrderAttachment.order_id == order_id,
                            OrderAttachment.storage_key == target_file_key
                        ).all()
                        for row in rows:
                            try:
                                if row.thumbnail_key:
                                    storage.delete_file(row.thumbnail_key)
                            except Exception:
                                pass
                            db.delete(row)
                    updated_files.pop(idx)
                first_index = min([x[0] for x in indices_to_replace])
                for offset, nf in enumerate(new_files):
                    updated_files.insert(first_index + offset, nf)
                replaced_target_numbers.sort()
            else:
                if is_retransfer and len(old_files) > 1:
                    return jsonify({'success': False, 'message': '수정본 재전송 시 교체할 도면 번호를 선택해주세요.'}), 400
                updated_files = list(old_files) + list(new_files)

            s_data['drawing_current_files'] = updated_files
            new_keys = [((f or {}).get('key') or '').strip() for f in new_files]
            new_keys = [k for k in new_keys if k]
            if new_keys:
                db.query(OrderAttachment).filter(
                    OrderAttachment.order_id == order_id,
                    OrderAttachment.storage_key.in_(new_keys)
                ).update(
                    {OrderAttachment.category: 'drawing'},
                    synchronize_session=False
                )

        transfer_info = {
            'action': 'TRANSFER',
            'transferred_at': now_str,
            'by_user_id': user_id,
            'by_user_name': user_name,
            'note': note,
            'files_count': len(new_files),
            'files': new_files,
            'mode': mode if mode else ('REPLACE' if replace_target_keys else 'APPEND'),
            'replace_target_keys': replace_target_keys if replace_target_keys else None,
            'replace_target_numbers': replaced_target_numbers if replaced_target_numbers else None,
            'replace_target_key': replace_target_keys[0] if len(replace_target_keys) == 1 else None,
            'replace_target_number': replaced_target_numbers[0] if len(replaced_target_numbers) == 1 else None,
        }

        if 'drawing_transfer_history' not in s_data:
            s_data['drawing_transfer_history'] = []
        history = list(s_data['drawing_transfer_history'])
        history.append(transfer_info)
        s_data['drawing_transfer_history'] = history
        s_data['drawing_status'] = 'TRANSFERRED'
        s_data['drawing_transferred'] = True
        s_data['last_drawing_transfer'] = transfer_info
        order.structured_data = s_data

        manager_name = (((s_data.get('parties') or {}).get('manager') or {}).get('name') or '').strip()
        customer_name = (((s_data.get('parties') or {}).get('customer') or {}).get('name') or '').strip()
        target_team = None
        target_manager_name = None
        notification_message = f"주문 #{order_id}"
        if customer_name:
            notification_message += f" ({customer_name})"
        notification_message += f" 도면이 준비되었습니다."
        if note:
            notification_message += f" 메모: {note}"
        if '라홈' in manager_name:
            target_team = 'CS'
        elif '하우드' in manager_name:
            target_team = 'HAUDD'
        else:
            target_team = 'SALES'
            target_manager_name = manager_name if manager_name else None

        new_notification = Notification(
            order_id=order_id,
            notification_type='DRAWING_TRANSFERRED',
            target_team=target_team,
            target_manager_name=target_manager_name,
            title='도면 전달됨',
            message=notification_message,
            created_by_user_id=user_id,
            created_by_name=user_name,
            is_read=False
        )
        db.add(new_notification)
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 도면 전달 완료: {note}"))
        db.commit()

        recipient_user_ids = resolve_notification_recipient_user_ids(
            db,
            target_team=target_team,
            target_manager_name=target_manager_name,
            include_admin=True,
        )
        invalidate_badge_cache_for_user_ids(recipient_user_ids)
        emit_erp_notification_to_users(
            recipient_user_ids,
            {
                'notification_id': new_notification.id,
                'order_id': order_id,
                'notification_type': 'DRAWING_TRANSFERRED',
                'title': new_notification.title,
                'message': new_notification.message,
            },
        )

        target_info = "라홈팀" if target_team == 'CS' else (
            "하우드팀" if target_team == 'HAUDD' else (
                f"영업팀 - {target_manager_name}" if target_manager_name else "영업팀"
            )
        )
        return jsonify({
            'success': True,
            'message': f'도면이 전달되었습니다. [{target_info}]에 알림이 전송되었습니다. (확정 대기 상태)',
            'info': '담당자가 수령 확인을 하면 다음 단계로 진행됩니다.'
        })
    except Exception as e:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500


@erp_orders_drawing_bp.route('/<int:order_id>/cancel-transfer', methods=['POST'])
@login_required
def api_order_cancel_transfer(order_id):
    """도면 전달 취소 (도면팀/관리자)"""
    db = None
    try:
        data = request.get_json(silent=True) or {}
        note = data.get('note', '')

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        s_data = dict(order.structured_data or {})
        current_user = get_user_by_id(session.get('user_id'))
        if not current_user:
            return jsonify({'success': False, 'message': '사용자 정보를 찾을 수 없습니다.'}), 401

        can_cancel = False
        if current_user.role == 'ADMIN':
            can_cancel = True
        elif can_modify_domain(current_user, order, 'DRAWING_DOMAIN', False, None):
            can_cancel = True
        else:
            latest_transfer = None
            for h in reversed(list(s_data.get('drawing_transfer_history', []) or [])):
                if isinstance(h, dict) and h.get('action') == 'TRANSFER':
                    latest_transfer = h
                    break
            if latest_transfer:
                try:
                    can_cancel = int(latest_transfer.get('by_user_id')) == int(current_user.id)
                except Exception:
                    can_cancel = False

        if not can_cancel:
            return jsonify({'success': False, 'message': '권한이 없습니다. (관리자/지정 도면담당/마지막 전달 실행자만 가능)'}), 403

        if s_data.get('drawing_status') != 'TRANSFERRED':
            return jsonify({'success': False, 'message': '확정 대기(\'TRANSFERRED\') 상태에서만 취소할 수 있습니다.'}), 400

        current_files = list(s_data.get('drawing_current_files', []) or [])
        current_keys = []
        for f in current_files:
            if isinstance(f, dict):
                k = (f.get('key') or '').strip()
                if k:
                    current_keys.append(k)

        deleted_files_count = 0
        if current_keys:
            storage = get_storage()
            rows = db.query(OrderAttachment).filter(
                OrderAttachment.order_id == order_id,
                OrderAttachment.storage_key.in_(current_keys)
            ).all()
            deleted_row_keys = set()
            for row in rows:
                try:
                    if row.storage_key:
                        if storage.delete_file(row.storage_key):
                            deleted_files_count += 1
                        deleted_row_keys.add(row.storage_key)
                    if row.thumbnail_key:
                        storage.delete_file(row.thumbnail_key)
                except Exception:
                    pass
                db.delete(row)
            for key in current_keys:
                if key in deleted_row_keys:
                    continue
                try:
                    if storage.delete_file(key):
                        deleted_files_count += 1
                except Exception:
                    pass

        s_data['drawing_status'] = 'PENDING'
        s_data['drawing_transferred'] = False
        s_data['drawing_current_files'] = []
        s_data['last_drawing_transfer'] = None
        history = list(s_data.get('drawing_transfer_history', []))
        removed_transfer = False
        current_key_set = set(current_keys)
        for idx in range(len(history) - 1, -1, -1):
            h = history[idx]
            if not isinstance(h, dict) or h.get('action') != 'TRANSFER':
                continue
            transfer_files = h.get('files') if isinstance(h.get('files'), list) else []
            transfer_keys = set()
            for tf in transfer_files:
                if isinstance(tf, dict):
                    k = (tf.get('key') or '').strip()
                    if k:
                        transfer_keys.add(k)
            if (not current_key_set) or (transfer_keys & current_key_set):
                history.pop(idx)
                removed_transfer = True
                break
        if (not removed_transfer) and history:
            for idx in range(len(history) - 1, -1, -1):
                h = history[idx]
                if isinstance(h, dict) and h.get('action') == 'TRANSFER':
                    history.pop(idx)
                    removed_transfer = True
                    break
        s_data['drawing_transfer_history'] = history
        order.structured_data = s_data
        db.add(SecurityLog(
            user_id=session.get('user_id'),
            message=f"주문 #{order_id} 도면 전달 취소 (파일 {deleted_files_count}개 삭제, 히스토리 정리: {'Y' if removed_transfer else 'N'})"
        ))
        db.commit()
        return jsonify({
            'success': True,
            'message': f'도면 전달이 취소되었습니다. (작업중 상태로 복귀, 전달 파일 {deleted_files_count}개 삭제)'
        })
    except Exception as e:
        if db is not None:
            db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_drawing_bp.route('/<int:order_id>/drawing-gateway-upload', methods=['POST'])
@login_required
@erp_edit_required
def api_drawing_gateway_upload(order_id):
    """도면 창구(수정요청) 파일 업로드 - 히스토리 표시용 파일만 저장."""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '파일이 없습니다.'}), 400
        file = request.files['file']
        if not file or not file.filename:
            return jsonify({'success': False, 'message': '파일명이 없습니다.'}), 400

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        storage = get_storage()
        folder = f"orders/{order_id}/drawing_gateway/revisions"
        result = storage.upload_file(file, file.filename, folder)
        if not result.get('success'):
            return jsonify({'success': False, 'message': '파일 업로드 실패'}), 500

        key = result.get('key')
        filename = file.filename
        file_type = storage._get_file_type(filename) if hasattr(storage, '_get_file_type') else 'file'
        if file_type not in ('image', 'video'):
            file_type = 'file'

        return jsonify({
            'success': True,
            'file': {
                'key': key,
                'filename': filename,
                'file_type': file_type,
                'view_url': f"/api/files/view/{key}",
                'download_url': f"/api/files/download/{key}",
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

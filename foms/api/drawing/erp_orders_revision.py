"""
ERP 주문 도면 수정 요청/체크 API. (Phase 4-5d, 4-5h)
erp.py에서 분리: request-revision, request-revision-check, cancel-revision-request, ack-order-change.
"""
import copy
import datetime
import logging

from flask import Blueprint, request, jsonify, session

from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, OrderAttachment, Notification, SecurityLog
from foms.web.auth import login_required, get_user_by_id
from foms.services.datetime_kst import now_utc_naive
from foms.services.storage import get_storage
from foms.api.notifications import (
    resolve_notification_recipient_user_ids,
    invalidate_badge_cache_for_user_ids,
)
from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.erp_permissions import erp_edit_required
from foms.services.erp_display import _can_modify_sales_domain, _ensure_dict
from foms.services.erp_policy import is_drawing_workbench_participant

logger = logging.getLogger(__name__)
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
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        s_data = copy.deepcopy(order.structured_data or {})
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
            'at': now_utc_naive().strftime('%Y-%m-%d %H:%M:%S'),
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
        flag_modified(order, 'structured_data')

        msg = f"주문 #{order_id} 도면 수정 요청이 접수되었습니다."
        if target_drawing_numbers:
            if len(target_drawing_numbers) == 1:
                msg += f" 대상: {target_drawing_numbers[0]}번 도면."
            else:
                msg += f" 대상: {', '.join(map(str, target_drawing_numbers))}번 도면 ({len(target_drawing_numbers)}건)."
        msg += f" 메모: {note}"
        if files:
            msg += f" (첨부 {len(files)}건)"
        new_notification = Notification(
            order_id=order_id,
            notification_type='DRAWING_REVISION',
            target_team='DRAWING',
            title='도면 수정 요청',
            message=msg,
            created_by_user_id=session.get('user_id'),
            created_by_name=current_user.name
        )
        db.add(new_notification)
        db.flush()
        # 같은 트랜잭션에서 수신자 state + 'created' 이벤트 생성(상태 없는 고아 알림 방지).
        fan_out_new_notification(db, new_notification, actor_user_id=session.get('user_id'))
        prod_notif = None
        prod_notif_created = False
        try:
            from foms.services.notifications.production_change import apply_production_change_alert
            prod_notif, prod_notif_created = apply_production_change_alert(
                db, order, "drawing", "도면 수정요청",
                actor_user_id=session.get('user_id'), actor_name=current_user.name,
            )
        except Exception as e:
            logger.warning("production change alert (revision) failed: %s", e, exc_info=True)
        db.add(SecurityLog(user_id=session.get('user_id'), message=f"주문 #{order_id} 도면 수정 요청"))
        db.commit()

        # 커밋 후 Web Push enqueue(P1 유형: DRAWING_REVISION).
        from foms.services.notifications.push_sender import enqueue_push_for_notification
        enqueue_push_for_notification(new_notification.id, db=db)

        recipient_user_ids = resolve_notification_recipient_user_ids(
            db,
            target_team='DRAWING',
            target_manager_name=None,
            include_admin=True,
        )
        invalidate_badge_cache_for_user_ids(recipient_user_ids)
        emit_erp_notification_to_users(
            recipient_user_ids,
            {
                'notification_id': new_notification.id,
                'order_id': order_id,
                'notification_type': 'DRAWING_REVISION',
                'title': new_notification.title,
                'message': new_notification.message,
            },
        )

        try:
            from foms.services.notifications.production_change import finalize_production_change_alert
            finalize_production_change_alert(db, prod_notif, created_new=prod_notif_created)
        except Exception as e:
            logger.warning("production change finalize (revision) failed: %s", e, exc_info=True)

        return jsonify({'success': True, 'message': '도면 수정 요청이 전송되었습니다.'})
    except Exception as e:
        db.rollback()
        logger.exception("Request Revision Error: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500


def _revision_reference_keys(files) -> set:
    """수정요청 이력 항목의 files에서 참고 파일 storage_key 집합을 추출.

    Args:
        files: REQUEST_REVISION 이력의 files 값(dict 리스트, 이번 요청 신규 업로드분).
    Returns:
        공백 제거된 storage_key 문자열 집합(빈 값 제외).
    """
    keys = set()
    for f in (files or []):
        if isinstance(f, dict):
            k = (f.get('key') or '').strip()
            if k:
                keys.add(k)
    return keys


def _delete_revision_reference_files(db, order_id: int, keys: set) -> int:
    """수정요청에서 새로 올린 참고 파일만 스토리지+DB에서 삭제.

    도면 원본(drawing_current_files)이나 타 이력 파일은 대상이 아니다.

    Args:
        db: SQLAlchemy 세션.
        order_id: 주문 ID.
        keys: 삭제 대상 storage_key 집합(이번 요청 신규 업로드분).
    Returns:
        실제로 삭제된 파일 수.
    """
    if not keys:
        return 0
    storage = get_storage()
    rows = db.query(OrderAttachment).filter(
        OrderAttachment.order_id == order_id,
        OrderAttachment.storage_key.in_(list(keys)),
    ).all()
    deleted = 0
    handled = set()
    for row in rows:
        try:
            if row.storage_key:
                if storage.delete_file(row.storage_key):
                    deleted += 1
                handled.add(row.storage_key)
            if row.thumbnail_key:
                storage.delete_file(row.thumbnail_key)
        except Exception:
            logger.warning("cancel-revision: file delete failed key=%s", row.storage_key, exc_info=True)
        db.delete(row)
    for key in keys:
        if key in handled:
            continue
        try:
            if storage.delete_file(key):
                deleted += 1
        except Exception:
            logger.warning("cancel-revision: orphan key delete failed key=%s", key, exc_info=True)
    return deleted


def _resolve_revision_restore_status(history: list) -> str:
    """수정요청 취소 후 복원할 drawing_status 결정.

    REQUEST_REVISION 제거 후 남은 이력을 역순 스캔해 최신 TRANSFER면
    'TRANSFERRED', 최신 CONFIRM_RECEIPT면 'CONFIRMED'로 복원한다. 수정요청은
    TRANSFERRED/CONFIRMED 상태에서만 생성되므로 이론상 항상 매칭되며, 방어적
    기본값은 'TRANSFERRED'.

    Args:
        history: REQUEST_REVISION 제거 후의 drawing_transfer_history 리스트.
    Returns:
        복원 대상 drawing_status 문자열.
    """
    for h in reversed(history):
        if not isinstance(h, dict):
            continue
        action = h.get('action')
        if action == 'TRANSFER':
            return 'TRANSFERRED'
        if action == 'CONFIRM_RECEIPT':
            return 'CONFIRMED'
    return 'TRANSFERRED'


@erp_orders_revision_bp.route('/<int:order_id>/cancel-revision-request', methods=['POST'])
@login_required
def api_order_cancel_revision_request(order_id):
    """도면 수정요청 취소 (영업측/관리자)

    영업팀이 접수한 도면 수정요청을 철회하고, 그 요청에서 새로 올린 참고
    파일만 삭제한 뒤 이전 상태(TRANSFERRED 또는 CONFIRMED)로 복원한다.
    도면 원본(drawing_current_files)과 타 이력 파일은 건드리지 않는다.
    권한은 전달취소(도면팀)와 대칭으로 영업측+관리자(도면팀 제외) 전용.

    Args:
        order_id: 주문 ID(URL 경로).
    Returns:
        JSON 응답 {success, message}.
    """
    db = None
    try:
        db = get_db()
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        s_data = copy.deepcopy(order.structured_data or {})
        current_user = get_user_by_id(session.get('user_id'))
        if not current_user:
            return jsonify({'success': False, 'message': '사용자 정보를 찾을 수 없습니다.'}), 401

        is_admin = current_user.role == 'ADMIN'
        is_drawing_team = (getattr(current_user, 'team', None) or '').strip() == 'DRAWING'
        can_sales = _can_modify_sales_domain(current_user, order, s_data, False, None)
        if not (is_admin or (can_sales and not is_drawing_team)):
            return jsonify({
                'success': False,
                'message': '수정요청 취소 권한이 없습니다. (지정된 주문 담당자/관리자만 가능)'
            }), 403

        if s_data.get('drawing_status') != 'RETURNED':
            return jsonify({'success': False, 'message': '수정 요청 상태에서만 취소할 수 있습니다.'}), 400

        history = list(s_data.get('drawing_transfer_history', []) or [])
        target_idx = None
        for idx in range(len(history) - 1, -1, -1):
            h = history[idx]
            if isinstance(h, dict) and h.get('action') == 'REQUEST_REVISION':
                target_idx = idx
                break
        if target_idx is None:
            return jsonify({'success': False, 'message': '취소할 수정 요청 이력을 찾을 수 없습니다.'}), 404

        deleted_count = _delete_revision_reference_files(
            db, order_id, _revision_reference_keys((history[target_idx] or {}).get('files'))
        )
        history.pop(target_idx)
        restore_status = _resolve_revision_restore_status(history)

        s_data['drawing_status'] = restore_status
        s_data['drawing_transfer_history'] = history
        order.structured_data = s_data
        flag_modified(order, 'structured_data')
        db.add(SecurityLog(
            user_id=session.get('user_id'),
            message=(
                f"주문 #{order_id} 도면 수정요청 취소 → {restore_status} 복귀 "
                f"(참고파일 {deleted_count}개 삭제)"
            )
        ))

        # 수정요청취소 알림 → 도면팀. 실패해도 취소는 진행(로그만).
        cancel_notif = None
        try:
            _cust = (((s_data.get('parties') or {}).get('customer') or {}).get('name') or '').strip()
            _msg = f"주문 #{order_id}" + (f" ({_cust})" if _cust else "") + " 도면 수정요청이 취소되었습니다."
            cancel_notif = Notification(
                order_id=order_id,
                notification_type='DRAWING_REVISION_CANCELLED',
                target_team='DRAWING',
                title='도면 수정요청 취소',
                message=_msg,
                created_by_user_id=session.get('user_id'),
                created_by_name=current_user.name,
                is_read=False,
            )
            db.add(cancel_notif)
            db.flush()
            fan_out_new_notification(db, cancel_notif, actor_user_id=session.get('user_id'))
        except Exception as _notif_err:
            cancel_notif = None
            logger.warning("cancel-revision notification build failed: %s", _notif_err, exc_info=True)

        db.commit()

        # 도메인-스코프: stage 무변경(drawing_status 복원만) → 도면·주문 목록만 무효화.
        from foms.services.common.dashboard_cache import (
            DASHBOARD_FAMILY_DRAWING,
            DASHBOARD_FAMILY_ORDERS,
            invalidate_dashboard_families,
        )

        invalidate_dashboard_families(DASHBOARD_FAMILY_DRAWING, DASHBOARD_FAMILY_ORDERS)

        # 커밋 후: push/badge/realtime(수정요청 알림 finalize 미러). 실패해도 취소 결과 불침해.
        if cancel_notif is not None:
            try:
                from foms.services.notifications.push_sender import enqueue_push_for_notification
                enqueue_push_for_notification(cancel_notif.id, db=db)
                _rids = resolve_notification_recipient_user_ids(
                    db, target_team='DRAWING', target_manager_name=None, include_admin=True,
                )
                invalidate_badge_cache_for_user_ids(_rids)
                emit_erp_notification_to_users(_rids, {
                    'notification_id': cancel_notif.id, 'order_id': order_id,
                    'notification_type': 'DRAWING_REVISION_CANCELLED',
                    'title': cancel_notif.title, 'message': cancel_notif.message,
                })
            except Exception as _fin_err:
                logger.warning("cancel-revision notification finalize failed: %s", _fin_err, exc_info=True)

        status_label = '확정 완료' if restore_status == 'CONFIRMED' else '확정 대기'
        return jsonify({
            'success': True,
            'message': f'수정 요청이 취소되었습니다. ({status_label} 상태로 복귀)'
        })
    except Exception as e:
        if db is not None:
            db.rollback()
        logger.exception("Cancel Revision Request Error: %s", e)
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
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        s_data = _ensure_dict(order.structured_data)
        current_user = get_user_by_id(session.get('user_id'))
        if not current_user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401

        if not is_drawing_workbench_participant(current_user, order):
            return jsonify({'success': False, 'message': '권한이 없습니다. (도면 담당자 또는 도면팀만 가능)'}), 403

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

        now_str = now_utc_naive().strftime('%Y-%m-%d %H:%M:%S')

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
        logger.exception("Request Revision Check Error: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_revision_bp.route('/<int:order_id>/drawing/ack-order-change', methods=['POST'])
@login_required
def api_ack_drawing_order_change(order_id):
    """도면 작업실 — ERP 주문 변경 배지/배너 확인(ack)."""
    from foms.services.notifications.drawing_order_change import ack_drawing_order_change

    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        current_user = get_user_by_id(session.get('user_id'))
        if not current_user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401
        if not is_drawing_workbench_participant(current_user, order) and current_user.role != 'ADMIN':
            return jsonify({'success': False, 'message': '도면 작업 참여자만 확인할 수 있습니다.'}), 403

        changed = ack_drawing_order_change(
            db,
            order,
            actor_user_id=session.get('user_id'),
            actor_name=current_user.name or '',
        )
        if changed:
            db.commit()
            from foms.services.common.dashboard_cache import (
                DASHBOARD_FAMILY_DRAWING,
                invalidate_dashboard_families,
            )
            invalidate_dashboard_families(DASHBOARD_FAMILY_DRAWING)
        else:
            db.rollback()
        return jsonify({'success': True, 'acked': bool(changed)})
    except Exception as e:
        db.rollback()
        logger.exception("ack drawing order-change failed: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500

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
from models import Order, Notification, SecurityLog
from foms.web.auth import login_required, get_user_by_id, log_access
from foms.services.audit_message_display import describe_order_action
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.datetime_kst import format_datetime_kst, now_utc_naive
from foms.api.notifications import (
    resolve_notification_recipient_user_ids,
    invalidate_badge_cache_for_user_ids,
)
from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.erp_permissions import erp_edit_required
from foms.services.erp_display import _can_modify_sales_domain, _ensure_dict
from foms.services.erp_policy import is_drawing_workbench_participant
from foms.services.orders.drawing_gate_followups import (
    invalidate_after_drawing_revision,
    invalidate_customer_confirmation,
    restore_customer_confirmation,
)
from foms.services.orders.drawing_revision_files import MAX_REVISION_FILES, normalize_revision_files
from foms.services.orders.revision import execute_single_order_write, lock_order_row

logger = logging.getLogger(__name__)
erp_orders_revision_bp = Blueprint(
    'erp_orders_revision',
    __name__,
    url_prefix='/api/orders',
)

# REV-00 receipt scope 용 정책 id. 세 라우트 모두 첫 조회를 lock_order_row 로 잠그고,
# 구조화 쓰기는 execute_single_order_write 콜백 안에서 한다(버전 +1, 2a-1②).
DRAWING_REVISION_REQUEST_POLICY_ID = 'DRAWING_REVISION_REQUEST'
DRAWING_REVISION_CANCEL_POLICY_ID = 'DRAWING_REVISION_CANCEL'
DRAWING_REVISION_CHECK_POLICY_ID = 'DRAWING_REVISION_CHECK'
DRAWING_ORDER_CHANGE_ACK_POLICY_ID = 'DRAWING_ORDER_CHANGE_ACK'

#: 수정요청 취소 이유(선택 본문 필드) 최대 길이.
REVISION_CANCEL_REASON_MAX = 200


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
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            data = {}
        note = data.get('note', '')
        # 참고 파일 입력 계약(M5): 키가 없거나 null 이면 빈 목록(태블릿 도면 검토 화면은
        # {note, target_drawing_keys} 만 보낸다). 키가 있는데 목록이 아니거나 이 주문
        # drawing_gateway/ 정본 key 가 아닌 항목이 하나라도 있으면 조용히 버리지 않고 400.
        raw_files = data.get('files')
        files = []
        if raw_files is not None:
            files, rejects = normalize_revision_files(order_id, raw_files)
            if rejects:
                too_many = isinstance(raw_files, list) and len(raw_files) > MAX_REVISION_FILES
                return jsonify({
                    'success': False,
                    'code': 'INVALID_REVISION_FILE',
                    'message': (f'참고 파일은 {MAX_REVISION_FILES}개까지 올릴 수 있습니다.' if too_many
                                else '참고 파일 경로가 올바르지 않습니다. 파일을 다시 올려 주세요.'),
                    'error': 'INVALID_REVISION_FILE',
                }), 400
        target_drawing_key = (data.get('target_drawing_key') or '').strip()
        target_drawing_keys = data.get('target_drawing_keys') or []

        if target_drawing_key and target_drawing_key not in target_drawing_keys:
            target_drawing_keys = [target_drawing_key]
        elif not target_drawing_keys:
            target_drawing_keys = []

        db = get_db()
        order = lock_order_row(db, order_id)
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
        invalidate_customer_confirmation(s_data, history[-1])  # M16(2a-2)
        s_data['drawing_transfer_history'] = history

        def _write_revision_request(locked):
            locked.structured_data = s_data
            flag_modified(locked, 'structured_data')

        execute_single_order_write(
            db, order_id=order_id, actor_user_id=current_user.id,
            policy_id=DRAWING_REVISION_REQUEST_POLICY_ID, payload=data,
            write=_write_revision_request,
        )

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
        invalidate_after_drawing_revision(order)  # 2a-2: CONFIRM·생산 패널이 게이트와 같은 답
        emit_erp_notification_to_users(
            recipient_user_ids,
            {
                'notification_id': new_notification.id,
                'order_id': order_id,
                'notification_type': 'DRAWING_REVISION',
                'title': new_notification.title,
                'message': new_notification.message,
                'created_by_name': current_user.name,
                # ACTION-REQUIRED 등급: 도면팀 화면에 확인을 눌러야 닫히는 창을 띄운다.
                # 등급 판정은 서버가 한다(프런트는 이 키만 본다). 긴급 호출(P0, urgent)과 달리
                # 전체화면 빨강이 아니라 중앙 확인창이다 — 2026-09-11 알림 개편.
                'interrupt': True,
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

    영업팀이 접수한 도면 수정요청을 철회하고 이전 상태(TRANSFERRED 또는 CONFIRMED)로
    복원한다. 열린 요청을 세는 소비자들이 바뀌지 않게 REQUEST_REVISION 항목은 이력에서
    빼되, 이력 끝에 ``REVISION_CANCELLED``(원래 요청 전체 복사·취소자·시각·이유)를 붙여
    "이 단계에서 수정요청이 있었다"가 남게 한다(M2). **파일은 지우지 않는다** — 예전에는
    참고 파일을 커밋 전에 R2 에서 지워 커밋이 실패하면 파일만 사라졌다.
    도면팀이 '반영 완료'를 누르고 작업 중이어도 취소할 수 있다(Q3 추천안 — 기록·알림으로 남김).
    권한은 전달취소(도면팀)와 대칭으로 영업측+관리자(도면팀 제외) 전용.
    본문은 선택 ``{reason}`` 이고 본문·Content-Type 이 없어도 된다(지금 화면 두 곳).

    Args:
        order_id: 주문 ID(URL 경로).
    Returns:
        JSON 응답 {success, message}.
    """
    db = None
    try:
        body = request.get_json(silent=True) or {}
        reason_raw = body.get('reason') if isinstance(body, dict) else None
        reason = (reason_raw.strip() if isinstance(reason_raw, str) else '')[:REVISION_CANCEL_REASON_MAX]
        db = get_db()
        order = lock_order_row(db, order_id)
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

        cancelled_request = copy.deepcopy(history.pop(target_idx))
        restore_status = _resolve_revision_restore_status(history)
        history.append({
            'action': 'REVISION_CANCELLED',
            'at': now_utc_naive().strftime('%Y-%m-%d %H:%M:%S'),
            'by_user_id': session.get('user_id'),
            'by_user_name': current_user.name,
            'reason': reason,
            'request': cancelled_request,
        })

        s_data['drawing_status'] = restore_status
        s_data['drawing_transfer_history'] = history
        restore_customer_confirmation(s_data, cancelled_request, history)  # M16(2a-2)

        def _write_revision_cancel(locked):
            locked.structured_data = s_data
            flag_modified(locked, 'structured_data')

        execute_single_order_write(
            db, order_id=order_id, actor_user_id=current_user.id,
            policy_id=DRAWING_REVISION_CANCEL_POLICY_ID,
            payload={'target_idx': target_idx, 'reason': reason}, write=_write_revision_cancel,
        )
        db.add(SecurityLog(
            user_id=session.get('user_id'),
            message=f"주문 #{order_id} 도면 수정요청 취소 → {restore_status} 복귀",
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
        invalidate_after_drawing_revision(order)  # 2a-2: CONFIRM·생산 패널이 게이트와 같은 답

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
                    'created_by_name': current_user.name,
                    # NOTICE 등급: 작업을 멈출 일은 아니지만 종 배지로만 두면 놓친다.
                    # 화면 오른쪽 아래 쪽지로 남고, 닫으면 읽음 처리된다(확인창과 달리 ack 없음).
                    'notice': True,
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
        order = lock_order_row(db, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        s_data = copy.deepcopy(_ensure_dict(order.structured_data))
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

        def _write_revision_check(locked):
            locked.structured_data = s_data
            flag_modified(locked, 'structured_data')

        execute_single_order_write(
            db, order_id=order_id, actor_user_id=current_user.id,
            policy_id=DRAWING_REVISION_CHECK_POLICY_ID, payload=data,
            write=_write_revision_check,
        )

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
    """도면 작업실 — ERP 주문 변경 배지/배너 확인(ack).

    도면 축(``drawing_transfer_history`` acked·pending 플래그) 쓰기라 다른 도면 라우트처럼
    첫 조회부터 행 잠금, 쓰기는 REV-00 엔진 콜백 안에서 한다(버전 +1). 바꿀 것이 없으면
    쓰지도 버전을 올리지도 않는다(리뷰 P3 — 예전엔 잠금 없이 읽고 통째로 되써 동시 수정요청을
    지웠고, 그 전에 연 폼이 409 를 받지 않았다).
    """
    from foms.services.notifications.drawing_order_change import (
        ack_drawing_order_change,
        order_change_ack_needed,
    )

    db = get_db()
    try:
        order = lock_order_row(db, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        current_user = get_user_by_id(session.get('user_id'))
        if not current_user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401
        if not is_drawing_workbench_participant(current_user, order) and current_user.role != 'ADMIN':
            return jsonify({'success': False, 'message': '도면 작업 참여자만 확인할 수 있습니다.'}), 403

        changed = False
        if order_change_ack_needed(order.structured_data):
            acked = {}

            def _write_ack(locked):
                acked['changed'] = ack_drawing_order_change(
                    db,
                    locked,
                    actor_user_id=session.get('user_id'),
                    actor_name=current_user.name or '',
                )

            execute_single_order_write(
                db, order_id=order_id, actor_user_id=current_user.id,
                policy_id=DRAWING_ORDER_CHANGE_ACK_POLICY_ID, payload={}, write=_write_ack,
            )
            changed = bool(acked.get('changed'))
        # 모바일 리본 한 줄이 '확인함 · 누가 언제'로 바뀌려면 이 두 값이 필요하다.
        # commit 뒤에는 속성이 만료되므로 커밋 전에 읽는다.
        acked_at_text = ''
        sd_after = order.structured_data if isinstance(order.structured_data, dict) else {}
        for entry in reversed(list(sd_after.get('drawing_transfer_history') or [])):
            if not isinstance(entry, dict):
                continue
            if entry.get('action') == 'ERP_ORDER_CHANGED' and entry.get('acked_at'):
                acked_at_text = format_datetime_kst(entry.get('acked_at'), '%m-%d %H:%M') or ''
                break
        if changed:
            ack_context = order_audit_context(order)
            log_access(
                describe_order_action(order_id=order_id, action="DRAWING_CHANGE_ACKNOWLEDGED",
                                      **ack_context),
                session.get('user_id'),
                auto_commit=False,
                action="DRAWING_CHANGE_ACKNOWLEDGED", target_type="order",
                target_id=int(order_id), detail=ack_context,
            )
            db.commit()
            from foms.services.common.dashboard_cache import (
                DASHBOARD_FAMILY_DRAWING,
                invalidate_dashboard_families,
            )
            invalidate_dashboard_families(DASHBOARD_FAMILY_DRAWING)
        else:
            db.rollback()
        return jsonify({
            'success': True,
            'acked': bool(changed),
            'acked_by_name': current_user.name or '',
            'acked_at': acked_at_text,
        })
    except Exception as e:
        db.rollback()
        logger.exception("ack drawing order-change failed: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500

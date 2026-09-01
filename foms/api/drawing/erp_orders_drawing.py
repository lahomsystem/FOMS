"""
ERP 주문 도면 전달/취소/창구 업로드 API. (Phase 4-5b, 4-5c)
erp.py에서 분리: transfer-drawing, cancel-transfer, drawing-gateway-upload.
"""
import copy
import json
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify, session
from sqlalchemy.orm.attributes import flag_modified

logger = logging.getLogger(__name__)

from db import get_db
from models import Order, OrderAttachment, Notification, OrderEvent
from foms.web.auth import login_required, get_user_by_id, log_access
from foms.services.audit_message_display import describe_order_action
from foms.services.common.table_version_counter import mark_tables_dirty
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.datetime_kst import now_utc_naive
from foms.api.notifications import (
    resolve_notification_recipient_user_ids,
    invalidate_badge_cache_for_user_ids,
)
from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.erp_permissions import erp_edit_required
from foms.services.erp_policy import (
    can_modify_domain,
    get_assignee_ids,
    has_pending_unchecked_drawing_revision_requests,
)
from foms.services.orders.drawing_transfer import (
    materialize_pending_snapshot,
    materialize_transfer_attachments,
)
from foms.services.sidefx_outbox import enqueue_side_effect
from foms.services.storage import get_storage
from foms.api.files import build_file_view_url, build_file_download_url

erp_orders_drawing_bp = Blueprint(
    'erp_orders_drawing',
    __name__,
    url_prefix='/api/orders',
)


def perform_drawing_transfer(
    db, order, order_id, current_user, user_id, *,
    note='', mode='', files=None, is_retransfer=False,
    replace_target_key='', replace_target_keys=None,
    emergency_override=False, override_reason='',
):
    """도면 전달 핵심 처리 — ``transfer-drawing`` 및 작업실 ``transfer-pending`` 공용.

    drawing_current_files 갱신·drawing_status='TRANSFERRED'·전달 히스토리 append·담당자
    알림(fan_out+push+realtime)·SecurityLog·대시보드 캐시 무효화를 한 트랜잭션으로 수행하고
    커밋한다. 호출측이 ``order``/``current_user``/``user_id`` 를 이미 로드해 전달한다.

    :param files: [{key, filename}] (이미 R2에 업로드된 참조). None/[] 이면 파일 미갱신.
    :returns: ``(payload_dict, http_status)``. 성공 시 ``payload['success']=True`` (200),
        검증 실패 시 해당 오류 payload 와 상태코드. 예외는 발생시키지 않고 호출측
        ``try/except`` 가 롤백한다.
    """
    note = note or ''
    mode = (mode or '').upper()
    is_retransfer = bool(is_retransfer)
    replace_target_key = (replace_target_key or '').strip()
    replace_target_keys = list(replace_target_keys or [])
    emergency_override = bool(emergency_override)
    override_reason = (override_reason or '').strip()

    if mode == 'REPLACE_ALL':
        pass
    elif replace_target_key and replace_target_key not in replace_target_keys:
        replace_target_keys = [replace_target_key]
    elif not replace_target_keys:
        replace_target_keys = []

    s_data = {}
    if order.structured_data:
        if isinstance(order.structured_data, dict):
            s_data = copy.deepcopy(order.structured_data)
        elif isinstance(order.structured_data, str):
            try:
                s_data = json.loads(order.structured_data)
            except Exception:
                s_data = {}

    draw_assignee_ids = get_assignee_ids(order, 'DRAWING_DOMAIN')
    if not draw_assignee_ids:
        return {'success': False, 'message': '도면 담당자가 지정되지 않아 전달할 수 없습니다. 먼저 담당자를 지정해주세요.'}, 400

    if not current_user:
        return {'success': False, 'message': '사용자 정보를 찾을 수 없습니다.'}, 401
    try:
        actor_uid = int(current_user.id)
    except (TypeError, ValueError):
        actor_uid = None
    # explicit assignment 만 쓰기 허용 — 도면팀 소속(team-only write)만으로는 전달 불가.
    # (지정 담당자 · 관리자 · 사유 있는 매니저 긴급 오버라이드만.)
    if current_user.role == 'ADMIN':
        can_do_transfer = True
    elif current_user.role == 'MANAGER' and emergency_override and override_reason:
        can_do_transfer = True
    else:
        can_do_transfer = actor_uid is not None and actor_uid in draw_assignee_ids
    if not can_do_transfer:
        msg = '도면 전달 권한이 없습니다. (지정된 도면 담당자 또는 관리자만 가능)'
        if current_user.role == 'MANAGER':
            msg += ' (긴급 시 사유와 함께 오버라이드를 사용하세요.)'
        return {'success': False, 'message': msg}, 403

    drawing_status = ((s_data.get('drawing') or {}).get('status') or s_data.get('drawing_status') or 'PENDING').upper()
    if not is_retransfer:
        is_retransfer = drawing_status == 'RETURNED'
    if (
        drawing_status == 'RETURNED'
        and has_pending_unchecked_drawing_revision_requests(s_data)
        and not (current_user.role == 'MANAGER' and emergency_override and override_reason)
    ):
        return {
            'success': False,
            'message': '수정 요청이 모두 "반영 완료"로 처리된 뒤에 수정본을 전달할 수 있습니다.',
        }, 400

    now_str = now_utc_naive().strftime('%Y-%m-%d %H:%M:%S')
    user_name = current_user.name if current_user else 'Unknown'

    # WIZ-TRANSFER helper 로 전달 소스 조립(인라인 재구현 금지). 도면 key 경로만 통과시켜
    # 실측/일반 첨부 유출을 차단한다(drawing_current_files leak 함정 SSOT).
    new_files = materialize_transfer_attachments(order_id, files or [])

    old_files = list(s_data.get('drawing_current_files', []) or [])
    updated_files = list(old_files)
    replaced_target_numbers = []

    if is_retransfer and not new_files:
        return {'success': False, 'message': '수정본 재전송 시 도면 파일 업로드가 필요합니다.'}, 400

    if new_files:
        if mode == 'REPLACE_ALL':
            # 기존 파일은 타임라인 히스토리에서 계속 참조되므로 R2에서 삭제하지 않음.
            # drawing_current_files 만 새 파일로 교체한다.
            for idx, old_file in enumerate(old_files):
                replaced_target_numbers.append(idx + 1)
            updated_files = list(new_files)
        elif replace_target_keys:
            indices_to_replace = []
            for target_key in replace_target_keys:
                for i, f in enumerate(old_files):
                    if ((f or {}).get('key') or '').strip() == target_key:
                        indices_to_replace.append((i, target_key))
                        break
            if len(indices_to_replace) != len(replace_target_keys):
                return {'success': False, 'message': '일부 교체 대상 도면을 찾을 수 없습니다. 목록을 새로고침 후 다시 시도해주세요.'}, 400
            indices_to_replace.sort(key=lambda x: x[0], reverse=True)
            for idx, target_key in indices_to_replace:
                replaced_target_numbers.append(idx + 1)
                # 교체 대상 파일도 히스토리 참조를 위해 R2에서 삭제하지 않음.
                updated_files.pop(idx)
            first_index = min([x[0] for x in indices_to_replace])
            for offset, nf in enumerate(new_files):
                updated_files.insert(first_index + offset, nf)
            replaced_target_numbers.sort()
        else:
            if is_retransfer and len(old_files) > 1:
                return {'success': False, 'message': '수정본 재전송 시 교체할 도면 번호를 선택해주세요.'}, 400
            if is_retransfer:
                # 수정 재전달 APPEND는 단일 도면일 때 교체로 처리 (이전본 누적 방지)
                updated_files = list(new_files)
            else:
                updated_files = list(old_files) + list(new_files)

        s_data['drawing_current_files'] = updated_files
        new_keys = [((f or {}).get('key') or '').strip() for f in new_files]
        new_keys = [k for k in new_keys if k]
        if new_keys:
            # HB-S1: query-level update() 는 ORM 세션 훅이 못 본다 — 커밋 시점
            # 테이블 버전 카운터 증가 대상으로 직접 등재한다.
            mark_tables_dirty(db, 'order_attachments')
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
        'previous_current_files': old_files,  # 취소 시 복원용
        'mode': (
            'REPLACE'
            if is_retransfer and not replace_target_keys and (mode or 'APPEND').upper() == 'APPEND' and len(old_files) <= 1
            else (mode if mode else ('REPLACE' if replace_target_keys else 'APPEND'))
        ),
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
    flag_modified(order, 'structured_data')

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
    db.flush()
    # 같은 트랜잭션에서 수신자 state + 'created' 이벤트 생성(상태 없는 고아 알림 방지).
    fan_out_new_notification(db, new_notification, actor_user_id=user_id)
    prod_notif = None
    prod_notif_created = False
    try:
        from foms.services.notifications.production_change import apply_production_change_alert
        prod_notif, prod_notif_created = apply_production_change_alert(
            db, order, "drawing", "도면 재전달",
            actor_user_id=user_id, actor_name=user_name,
        )
    except Exception as e:
        logger.warning("production change alert (transfer) failed: %s", e, exc_info=True)
    context = order_audit_context(order)
    log_access(
        describe_order_action(order_id=order_id, action="DRAWING_DELIVERED", note=note or None, **context),
        user_id,
        auto_commit=False,
        action="DRAWING_DELIVERED", target_type="order", target_id=int(order_id),
        detail={"note": note or None, "target_team": target_team,
                "target_manager_name": target_manager_name, **context},
        db=db,  # 호출자 소유 세션 — get_db() 를 부르면 teardown 이 호출자 인스턴스를 detach 한다.
    )
    db.commit()
    # 도메인-스코프: 도면 전달 완료는 workflow.stage를 바꾸지 않고 drawing_status만
    # 변경 → 도면 대시보드/워크벤치와 주문 목록만 무효화(생산 read-model은 도면
    # 상태를 읽지 않음).
    from foms.services.common.dashboard_cache import (
        DASHBOARD_FAMILY_DRAWING,
        DASHBOARD_FAMILY_ORDERS,
        invalidate_dashboard_families,
    )

    invalidate_dashboard_families(DASHBOARD_FAMILY_DRAWING, DASHBOARD_FAMILY_ORDERS)

    # 커밋 후 Web Push enqueue(P1 유형: DRAWING_TRANSFERRED).
    from foms.services.notifications.push_sender import enqueue_push_for_notification
    enqueue_push_for_notification(new_notification.id, db=db)

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

    try:
        from foms.services.notifications.production_change import finalize_production_change_alert
        finalize_production_change_alert(db, prod_notif, created_new=prod_notif_created)
    except Exception as e:
        logger.warning("production change finalize (transfer) failed: %s", e, exc_info=True)

    target_info = "라홈팀" if target_team == 'CS' else (
        "하우드팀" if target_team == 'HAUDD' else (
            f"영업팀 - {target_manager_name}" if target_manager_name else "영업팀"
        )
    )
    return {
        'success': True,
        'message': f'도면이 전달되었습니다. [{target_info}]에 알림이 전송되었습니다. (확정 대기 상태)',
        'info': '담당자가 수령 확인을 하면 다음 단계로 진행됩니다.'
    }, 200


@erp_orders_drawing_bp.route('/<int:order_id>/transfer-drawing', methods=['POST'])
@login_required
def api_order_transfer_drawing(order_id):
    """도면 전달 처리 (단계 변경 없이 전달 정보만 기록)"""
    db = None
    try:
        data = request.get_json() or {}
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        current_user = get_user_by_id(session.get('user_id'))

        # 도면 마법사 [저장]본(pending) 병합 — 재업로드 없이 저장된 대기 도면을 함께 전달.
        # pending_sheet_ids 가 오면 해당 대기 시트의 {key, filename} 을 파일 목록에 병합하고,
        # 전달 성공 후 그 sheet_id 들만 스냅샷 저장 + pending 제거(없으면 기존 동작 100% 불변).
        from foms.api.drawing.wizard import snapshot_and_clear_pending
        pending_sheet_ids = [str(x) for x in (data.get('pending_sheet_ids') or []) if str(x)]
        manual_files = list(data.get('files') or [])
        pending_files = []
        if pending_sheet_ids:
            wanted = set(pending_sheet_ids)
            pending_files = [
                {'key': p['key'], 'filename': p['filename']}
                for p in materialize_pending_snapshot(order)
                if p['sheet_id'] in wanted
            ]
        # 저장된 대기 도면(primary)을 앞에, 직접 올린 파일(supplementary)을 뒤에 둔다.
        files = pending_files + manual_files

        payload, status = perform_drawing_transfer(
            db, order, order_id, current_user, session.get('user_id'),
            note=data.get('note', ''),
            mode=data.get('mode') or '',
            files=files,
            is_retransfer=bool(data.get('is_retransfer')),
            replace_target_key=data.get('replace_target_key') or '',
            replace_target_keys=data.get('replace_target_keys') or [],
            emergency_override=bool(data.get('emergency_override')),
            override_reason=data.get('override_reason') or '',
        )
        if payload.get('success') and pending_sheet_ids:
            snapshot_and_clear_pending(db, order, order_id, current_user, sheet_ids=pending_sheet_ids)
        return jsonify(payload), status
    except Exception as e:
        if db is not None:
            try:
                db.rollback()
            except Exception as rb_err:
                logger.warning("transfer-drawing: rollback failed: %s", rb_err, exc_info=True)
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500


@erp_orders_drawing_bp.route('/<int:order_id>/cancel-transfer', methods=['POST'])
@login_required
def api_order_cancel_transfer(order_id):
    """도면 전달 취소 (도면팀/관리자)
    수정 요청 후 재전달한 경우, 이번 전달에서 '새로 올린 파일'만 삭제하고
    이전 상태(RETURNED 또는 PENDING)로 복원한다.
    """
    db = None
    try:
        data = request.get_json(silent=True) or {}

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        s_data = copy.deepcopy(order.structured_data or {})
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
            return jsonify({'success': False, 'message': "확정 대기('TRANSFERRED') 상태에서만 취소할 수 있습니다."}), 400

        history = list(s_data.get('drawing_transfer_history', []))
        current_files = list(s_data.get('drawing_current_files', []) or [])

        # ── 1. 취소할 최신 TRANSFER 이력 탐색 ──────────────────────────────────
        latest_transfer_idx = None
        latest_transfer_entry = None
        for idx in range(len(history) - 1, -1, -1):
            h = history[idx]
            if isinstance(h, dict) and h.get('action') == 'TRANSFER':
                latest_transfer_idx = idx
                latest_transfer_entry = h
                break

        # ── 2. 이번 전달에서 새로 올린 파일 키 목록 파악 ──────────────────────
        # transfer_info['files'] = 이번 전달에서 올린 신규 파일만 기록됨
        newly_uploaded_keys = set()
        transfer_mode = 'APPEND'
        if latest_transfer_entry:
            transfer_mode = (latest_transfer_entry.get('mode') or 'APPEND').upper()
            for tf in (latest_transfer_entry.get('files') or []):
                if isinstance(tf, dict):
                    k = (tf.get('key') or '').strip()
                    if k:
                        newly_uploaded_keys.add(k)

        # ── 3. 삭제 대상 결정 ──────────────────────────────────────────────────
        # 이번 전달에서 새로 올린 파일(newly_uploaded_keys)만 회수 대상.
        # 기존 파일들은 1차 전달 이력 등 타임라인에서 계속 참조되므로 절대 삭제 금지.
        # OrderAttachment DB row 는 이 트랜잭션에서 제거하고, 실제 R2 blob 삭제는
        # STORAGE_DELETE outbox 로 예약한다(동기 R2 삭제 금지 — 아래 6.5 참조).
        keys_to_delete = newly_uploaded_keys
        storage_keys_for_outbox = set()  # 삭제 예약할 R2 object key(원본 + 썸네일)
        if keys_to_delete:
            rows = db.query(OrderAttachment).filter(
                OrderAttachment.order_id == order_id,
                OrderAttachment.storage_key.in_(list(keys_to_delete))
            ).all()
            handled = set()
            for row in rows:
                if row.storage_key:
                    storage_keys_for_outbox.add(row.storage_key)
                    handled.add(row.storage_key)
                if row.thumbnail_key:
                    storage_keys_for_outbox.add(row.thumbnail_key)
                db.delete(row)
            for key in keys_to_delete:
                if key not in handled:
                    storage_keys_for_outbox.add(key)
        deleted_files_count = len(keys_to_delete)

        # ── 4. drawing_current_files 복원 ──────────────────────────────────────
        # transfer_info에 저장된 previous_current_files로 정확히 복원.
        # (이전 버전 호환: 없으면 APPEND 모드에서는 새 파일만 제거하는 방식으로 폴백)
        if latest_transfer_entry and isinstance(latest_transfer_entry.get('previous_current_files'), list):
            restored_files = list(latest_transfer_entry['previous_current_files'])
        elif transfer_mode == 'APPEND':
            restored_files = [
                f for f in current_files
                if isinstance(f, dict) and (f.get('key') or '').strip() not in newly_uploaded_keys
            ]
        else:
            restored_files = []

        # ── 5. 히스토리에서 최신 TRANSFER 제거 ──────────────────────────────────
        removed_transfer = False
        if latest_transfer_idx is not None:
            history.pop(latest_transfer_idx)
            removed_transfer = True

        # ── 6. 이전 상태로 복원 ──────────────────────────────────────────────────
        # 히스토리에서 마지막 액션이 REQUEST_REVISION이면 RETURNED, 아니면 PENDING
        restore_status = 'PENDING'
        for h in reversed(history):
            if not isinstance(h, dict):
                continue
            prev_action = h.get('action')
            if prev_action == 'REQUEST_REVISION':
                restore_status = 'RETURNED'
                break
            elif prev_action == 'TRANSFER':
                restore_status = 'PENDING'
                break

        s_data['drawing_status'] = restore_status
        s_data['drawing_transferred'] = False
        s_data['drawing_current_files'] = restored_files
        s_data['last_drawing_transfer'] = None
        s_data['drawing_transfer_history'] = history
        order.structured_data = s_data
        flag_modified(order, 'structured_data')
        cancel_context = order_audit_context(order)
        log_access(
            describe_order_action(
                order_id=order_id, action="DRAWING_DELIVERY_CANCELED",
                note=f"{restore_status} 복귀", **cancel_context,
            ),
            session.get('user_id'),
            auto_commit=False,
            action="DRAWING_DELIVERY_CANCELED", target_type="order", target_id=int(order_id),
            detail={"restore_status": restore_status,
                    "deleted_files": deleted_files_count,
                    "restored_files": len(restored_files),
                    "history_cleaned": bool(removed_transfer), **cancel_context},
        )

        # ── 6.5 회수 파일 R2 blob 삭제를 STORAGE_DELETE outbox 로 예약 ────────────
        # 동기 R2 삭제 금지 — sidefx worker/handler 가 소비한다(이 핸들러는 enqueue 만).
        # ORDER_EVENT 를 source 로 두어 one-of FK 매트릭스를 만족하고, business tx 가
        # rollback 되면 event·outbox 도 함께 rollback 된다(원자성).
        if storage_keys_for_outbox:
            cancel_event = OrderEvent(
                order_id=order_id,
                event_type='DRAWING_TRANSFER_CANCELLED',
                payload={
                    'action': 'CANCEL_TRANSFER',
                    'restore_status': restore_status,
                    'deleted_keys': sorted(storage_keys_for_outbox),
                },
                created_by_user_id=session.get('user_id'),
            )
            db.add(cancel_event)
            db.flush()
            order.mutation_version = (order.mutation_version or 0) + 1
            for object_key in sorted(storage_keys_for_outbox):
                enqueue_side_effect(
                    db,
                    source_domain='ORDER_EVENT',
                    source_id=cancel_event.id,
                    effect_type='STORAGE_DELETE',
                    payload={'object_key': object_key, 'order_id': order_id},
                    dedupe_key=f'drawing_cancel:{order_id}:{object_key}',
                )

        # 전달취소 알림 → 영업(전달 알림과 동일 매니저 라우팅). 실패해도 취소는 진행(로그만).
        cancel_notif = None
        cancel_target_team = None
        cancel_target_manager = None
        try:
            _mgr = (((s_data.get('parties') or {}).get('manager') or {}).get('name') or '').strip()
            _cust = (((s_data.get('parties') or {}).get('customer') or {}).get('name') or '').strip()
            if '라홈' in _mgr:
                cancel_target_team = 'CS'
            elif '하우드' in _mgr:
                cancel_target_team = 'HAUDD'
            else:
                cancel_target_team = 'SALES'
                cancel_target_manager = _mgr or None
            _msg = f"주문 #{order_id}" + (f" ({_cust})" if _cust else "") + " 도면 전달이 취소되었습니다."
            cancel_notif = Notification(
                order_id=order_id,
                notification_type='DRAWING_TRANSFER_CANCELLED',
                target_team=cancel_target_team,
                target_manager_name=cancel_target_manager,
                title='도면 전달 취소',
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
            logger.warning("cancel-transfer notification build failed: %s", _notif_err, exc_info=True)

        db.commit()
        # 도메인-스코프: 도면 전달 취소도 stage 무변경(drawing_status 복원만)
        # → 도면·주문 목록만 무효화.
        from foms.services.common.dashboard_cache import (
            DASHBOARD_FAMILY_DRAWING,
            DASHBOARD_FAMILY_ORDERS,
            invalidate_dashboard_families,
        )

        invalidate_dashboard_families(DASHBOARD_FAMILY_DRAWING, DASHBOARD_FAMILY_ORDERS)

        # 커밋 후: push/badge/realtime(전달 알림 finalize 미러). 실패해도 취소 결과 불침해.
        if cancel_notif is not None:
            try:
                from foms.services.notifications.push_sender import enqueue_push_for_notification
                enqueue_push_for_notification(cancel_notif.id, db=db)
                _rids = resolve_notification_recipient_user_ids(
                    db, target_team=cancel_target_team,
                    target_manager_name=cancel_target_manager, include_admin=True,
                )
                invalidate_badge_cache_for_user_ids(_rids)
                emit_erp_notification_to_users(_rids, {
                    'notification_id': cancel_notif.id, 'order_id': order_id,
                    'notification_type': 'DRAWING_TRANSFER_CANCELLED',
                    'title': cancel_notif.title, 'message': cancel_notif.message,
                })
            except Exception as _fin_err:
                logger.warning("cancel-transfer notification finalize failed: %s", _fin_err, exc_info=True)

        status_label = '수정 요청 상태' if restore_status == 'RETURNED' else '작업중 상태'
        return jsonify({
            'success': True,
            'message': f'도면 전달이 취소되었습니다. ({status_label}로 복귀, 신규 업로드 파일 {deleted_files_count}개 삭제)'
        })
    except Exception as e:
        if db is not None:
            db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


def _audit_drawing_gateway_upload(order, filename: str, key: str) -> None:
    """도면 창구 파일 업로드 1건을 구조화 감사로 남긴다.

    이 경로는 업무 트랜잭션이 없으므로(파일만 R2 로 올리고 메타를 돌려준다) 감사 기록은
    자기 커밋으로 남긴다.

    :param order: 대상 :class:`~models.Order`.
    :param filename: 업로드된 원본 파일명.
    :param key: R2 storage key.
    """
    context = order_audit_context(order)
    log_access(
        describe_order_action(
            order_id=order.id, action="DRAWING_GATEWAY_FILE_UPLOADED",
            note=filename, **context,
        ),
        session.get('user_id'),
        action="DRAWING_GATEWAY_FILE_UPLOADED", target_type="order", target_id=int(order.id),
        detail={"filename": filename, "storage_key": key, **context},
    )


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
        file_type = storage.get_file_type(filename)
        if file_type not in ('image', 'video'):
            file_type = 'file'

        _audit_drawing_gateway_upload(order, filename, key)

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


@erp_orders_drawing_bp.route('/<int:order_id>/drawing-gateway/complete', methods=['POST'])
@login_required
@erp_edit_required
def api_drawing_gateway_complete(order_id):
    """Phase D: Direct R2 업로드 완료 후 파일 메타 반환 (히스토리 표시용)."""
    try:
        data = request.get_json(silent=True) or {}
        key = data.get('key')
        filename = data.get('filename')
        if not key or not filename:
            return jsonify({'success': False, 'message': 'key, filename 필수가 필요합니다.'}), 400

        expected = f"orders/{order_id}/drawing_gateway"
        if expected not in key or '..' in key:
            return jsonify({'success': False, 'message': '유효하지 않은 key 경로입니다.'}), 400

        storage = get_storage()
        if not storage.object_exists(key):
            return jsonify({'success': False, 'message': '업로드된 파일을 찾을 수 없습니다. 먼저 PUT으로 업로드하세요.'}), 404

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        file_type = storage.get_file_type(filename)
        if file_type not in ('image', 'video'):
            file_type = 'file'

        _audit_drawing_gateway_upload(order, filename, key)

        return jsonify({
            'success': True,
            'file': {
                'key': key,
                'filename': filename,
                'file_type': file_type,
                'view_url': build_file_view_url(key),
                'download_url': build_file_download_url(key),
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

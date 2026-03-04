"""
ERP 알림 API: 목록/배지/읽음 처리.
erp.py에서 분리 (Phase 4-1).
"""
import json
import os
import time
import datetime as dt_mod
from urllib.parse import quote

from flask import Blueprint, request, jsonify, session
from sqlalchemy import or_, func

from db import get_db
from models import Order, Notification, User
from apps.auth import login_required

notifications_bp = Blueprint(
    'notifications',
    __name__,
    url_prefix='/erp/api',
)

_NOTIFICATION_DEBUG = os.environ.get('ERP_BETA_DEBUG', '').lower() in ('1', 'true', 'yes', 'on')

# 배지 카운트 캐시: user_id -> (count, expiry_unix_ts). DB 부하 감소용.
_badge_cache = {}
BADGE_CACHE_TTL_SECONDS = 30


def _invalidate_badge_cache(user_id):
    """사용자별 배지 캐시 무효화 (읽음 처리 시 호출)."""
    if user_id is not None:
        _badge_cache.pop(user_id, None)


def invalidate_badge_cache_for_user_ids(user_ids):
    """여러 사용자의 배지 캐시를 한 번에 무효화."""
    if not user_ids:
        return
    for uid in user_ids:
        try:
            _invalidate_badge_cache(int(uid))
        except (TypeError, ValueError):
            continue


def resolve_notification_recipient_user_ids(
    db, target_type=None, target_team=None, target_manager_name=None,
    target_user_ids=None, include_admin=True
):
    """알림 타겟 기준으로 수신 사용자 ID 집합을 계산.
    
    target_type:
      ALL  → 전체 활성 사용자
      TEAM → target_team 기준
      USER → target_user_ids 직접 지정
      ORDER/None → 기존 방식 (target_team/target_manager_name)
    """
    ttype = (target_type or '').strip().upper()

    if ttype == 'ALL':
        rows = db.query(User.id).all()
        return {int(r[0]) for r in rows}

    if ttype == 'USER' and target_user_ids:
        out = set()
        for uid in target_user_ids:
            try:
                out.add(int(uid))
            except (TypeError, ValueError):
                continue
        return out

    team = (target_team or '').strip().upper()
    manager_name = (target_manager_name or '').strip()

    conditions = []
    if team:
        conditions.append(func.upper(User.team) == team)
    if manager_name:
        conditions.append(User.name == manager_name)
    if include_admin:
        conditions.append(User.role == 'ADMIN')

    if not conditions:
        return set()

    rows = db.query(User.id).filter(or_(*conditions)).all()
    return {int(r[0]) for r in rows}


def _build_user_notification_filter(user, user_id):
    """비관리자 사용자의 알림 필터 조건 목록을 반환. ADMIN이면 None (전체 접근)."""
    if user.role == 'ADMIN':
        return None
    conditions = []
    user_team = user.team.upper() if user.team else None
    user_name = user.name.strip() if user.name else None
    if user_team:
        conditions.append(Notification.target_team == user_team)
    if user_name:
        conditions.append(Notification.target_manager_name == user_name)
    conditions.append(Notification.target_user_id == user_id)
    conditions.append(Notification.target_type == 'ALL')
    return conditions


def _ensure_dict(data):
    """JSONB 필드가 문자열로 오인될 경우를 대비해 딕셔너리로 변환."""
    if not data:
        return {}
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except Exception:
            return {}
    return {}


def _parse_history_time(value):
    """도면 히스토리 문자열 시각을 datetime으로 파싱."""
    if not value:
        return None
    try:
        return dt_mod.datetime.strptime(str(value), '%Y-%m-%d %H:%M:%S')
    except Exception:
        return None


def _build_drawing_event_key(idx, event):
    """도면 이벤트 고유 키 생성."""
    action = str((event or {}).get('action') or '')
    at = str((event or {}).get('at') or (event or {}).get('transferred_at') or '')
    by_user_id = str((event or {}).get('by_user_id') or '')
    return f"{idx}:{action}:{at}:{by_user_id}"


def _resolve_notification_deep_link(notification, order_structured_data):
    """알림 -> 도면 작업실 상세 딥링크 정보(event_id/target_no/tab) 계산."""
    n_type = str(getattr(notification, 'notification_type', '') or '').upper()
    oid = getattr(notification, 'order_id', None)

    if n_type not in ('DRAWING_TRANSFERRED', 'DRAWING_REVISION') or not oid:
        return {
            'deep_tab': None,
            'deep_event_id': None,
            'deep_target_no': None,
            'deep_link_url': None,
        }

    target_action = 'TRANSFER' if n_type == 'DRAWING_TRANSFERRED' else 'REQUEST_REVISION'
    target_tab = 'timeline' if n_type == 'DRAWING_TRANSFERRED' else 'requests'
    history = list(((order_structured_data or {}).get('drawing_transfer_history', []) or []))
    if not history:
        return {
            'deep_tab': target_tab,
            'deep_event_id': None,
            'deep_target_no': None,
            'deep_link_url': f"/erp/drawing-workbench/{oid}?tab={target_tab}",
        }

    created_at = getattr(notification, 'created_at', None)
    matched = None
    matched_idx = -1
    best_score = None

    for idx, h in enumerate(history):
        if not isinstance(h, dict):
            continue
        if str(h.get('action') or '') != target_action:
            continue
        h_dt = _parse_history_time(h.get('at') or h.get('transferred_at'))
        if created_at and h_dt:
            score = abs((created_at - h_dt).total_seconds())
        else:
            score = float('inf')
        if best_score is None or score < best_score:
            best_score = score
            matched = h
            matched_idx = idx

    if matched is None:
        for idx in range(len(history) - 1, -1, -1):
            h = history[idx]
            if isinstance(h, dict) and str(h.get('action') or '') == target_action:
                matched = h
                matched_idx = idx
                break

    deep_event_id = _build_drawing_event_key(matched_idx, matched) if matched is not None and matched_idx >= 0 else None
    deep_target_no = None
    if isinstance(matched, dict):
        try:
            deep_target_no = int(matched.get('target_drawing_number') or matched.get('replace_target_number') or 0) or None
        except (TypeError, ValueError):
            deep_target_no = None

    query_parts = [f"tab={target_tab}"]
    if deep_event_id:
        query_parts.append(f"event_id={quote(str(deep_event_id), safe='')}")
    if deep_target_no:
        query_parts.append(f"target_no={deep_target_no}")
    deep_link_url = f"/erp/drawing-workbench/{oid}?{'&'.join(query_parts)}"
    return {
        'deep_tab': target_tab,
        'deep_event_id': deep_event_id,
        'deep_target_no': deep_target_no,
        'deep_link_url': deep_link_url,
    }


@notifications_bp.route('/notifications', methods=['GET'])
@login_required
def api_notifications_list():
    """현재 사용자의 알림 목록 조회. unread_only, limit 쿼리 지원."""
    try:
        db = get_db()
        user_id = session.get('user_id')
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return jsonify({'success': False, 'message': '사용자 정보를 찾을 수 없습니다.'}), 404

        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        limit = int(request.args.get('limit', 20))

        query = db.query(Notification)
        conds = _build_user_notification_filter(user, user_id)

        if conds is not None:
            if not conds:
                return jsonify({'success': True, 'notifications': [], 'unread_count': 0})
            query = query.filter(or_(*conds))

        if unread_only:
            query = query.filter(Notification.is_read == False)

        query = query.order_by(Notification.created_at.desc()).limit(limit)
        notifications = query.all()

        unread_query = db.query(Notification).filter(Notification.is_read == False)
        if conds is not None and conds:
            unread_query = unread_query.filter(or_(*conds))
        unread_count = unread_query.count()

        order_ids = list({int(n.order_id) for n in notifications if n.order_id is not None})
        order_map = {}
        if order_ids:
            order_rows = db.query(Order.id, Order.structured_data).filter(Order.id.in_(order_ids)).all()
            for oid, sd in order_rows:
                order_map[int(oid)] = _ensure_dict(sd)

        notif_payloads = []
        for n in notifications:
            row = n.to_dict()
            sd = order_map.get(n.order_id, {}) if n.order_id else {}
            deep = _resolve_notification_deep_link(n, sd)
            row.update(deep)
            notif_payloads.append(row)

        return jsonify({
            'success': True,
            'notifications': notif_payloads,
            'unread_count': unread_count,
        })
    except Exception as e:
        import traceback
        print(f"Notification List Error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@notifications_bp.route('/notifications/badge', methods=['GET'])
@login_required
def api_notifications_badge():
    """알림 배지 카운트 조회 (읽지 않은 알림 수). 사용자별 30초 캐시로 DB 부하 완화."""
    try:
        user_id = session.get('user_id')
        if user_id is None:
            return jsonify({'success': True, 'count': 0})

        now_ts = time.time()
        cached = _badge_cache.get(user_id)
        if cached is not None and cached[1] > now_ts:
            return jsonify({'success': True, 'count': cached[0]})

        db = get_db()
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({'success': True, 'count': 0})

        query = db.query(Notification).filter(Notification.is_read == False)
        conds = _build_user_notification_filter(user, user_id)

        if conds is not None:
            if not conds:
                count = 0
                _badge_cache[user_id] = (count, now_ts + BADGE_CACHE_TTL_SECONDS)
                return jsonify({'success': True, 'count': count})
            query = query.filter(or_(*conds))

        count = query.count()
        _badge_cache[user_id] = (count, now_ts + BADGE_CACHE_TTL_SECONDS)
        return jsonify({'success': True, 'count': count})
    except Exception:
        return jsonify({'success': True, 'count': 0})


@notifications_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def api_notification_mark_read(notification_id):
    """알림 읽음 처리."""
    try:
        db = get_db()
        user_id = session.get('user_id')

        notification = db.query(Notification).filter(Notification.id == notification_id).first()
        if not notification:
            return jsonify({'success': False, 'message': '알림을 찾을 수 없습니다.'}), 404

        notification.is_read = True
        notification.read_at = dt_mod.datetime.now()
        notification.read_by_user_id = user_id

        db.commit()
        _invalidate_badge_cache(user_id)
        return jsonify({'success': True, 'message': '알림을 읽음 처리했습니다.'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@notifications_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def api_notifications_mark_all_read():
    """모든 알림 읽음 처리."""
    try:
        db = get_db()
        user_id = session.get('user_id')
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return jsonify({'success': False, 'message': '사용자 정보를 찾을 수 없습니다.'}), 404

        query = db.query(Notification).filter(Notification.is_read == False)
        conds = _build_user_notification_filter(user, user_id)

        if conds is not None and conds:
            query = query.filter(or_(*conds))

        now = dt_mod.datetime.now()
        updated = query.update({
            Notification.is_read: True,
            Notification.read_at: now,
            Notification.read_by_user_id: user_id,
        }, synchronize_session='fetch')

        db.commit()
        _invalidate_badge_cache(user_id)
        return jsonify({'success': True, 'message': f'{updated}개 알림을 읽음 처리했습니다.', 'count': updated})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@notifications_bp.route('/notifications/delete-all', methods=['POST'])
@login_required
def api_notifications_delete_all():
    """현재 사용자 기준으로 보이는 알림 전체 삭제 (목록과 동일 필터)."""
    try:
        db = get_db()
        user_id = session.get('user_id')
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return jsonify({'success': False, 'message': '사용자 정보를 찾을 수 없습니다.'}), 404

        query = db.query(Notification)
        conds = _build_user_notification_filter(user, user_id)

        if conds is not None and conds:
            query = query.filter(or_(*conds))
        elif conds is not None:
            return jsonify({'success': True, 'message': '삭제할 알림이 없습니다.', 'count': 0})

        deleted = query.delete(synchronize_session='fetch')
        db.commit()
        _invalidate_badge_cache(user_id)
        return jsonify({'success': True, 'message': f'{deleted}개 알림을 삭제했습니다.', 'count': deleted})
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'message': str(e)}), 500


# ─────────────────────────────────────────────────
# 사용자 목록 (동료 호출 대상 선택용)
# ─────────────────────────────────────────────────

@notifications_bp.route('/users/list', methods=['GET'])
@login_required
def api_users_list_for_mention():
    """동료 호출 대상 선택용 사용자 목록."""
    try:
        db = get_db()
        users = db.query(User.id, User.name, User.team, User.role).order_by(User.name).all()
        return jsonify({
            'success': True,
            'users': [
                {'id': u.id, 'name': u.name, 'team': u.team, 'role': u.role}
                for u in users
            ],
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ─────────────────────────────────────────────────
# 발송 API
# ─────────────────────────────────────────────────

@notifications_bp.route('/notifications/send', methods=['POST'])
@login_required
def api_notifications_send():
    """관리자/매니저 전용 — 공지/알림 발송.
    
    target_type:
      ALL  → 전체 사용자에게 레코드 복제
      TEAM → 특정 팀 대상 사용자에게 레코드 복제
      USER → target_user_ids 목록에 레코드 복제
    """
    try:
        db = get_db()
        user_id = session.get('user_id')
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.role not in ('ADMIN', 'MANAGER'):
            return jsonify({'success': False, 'message': '권한이 없습니다.'}), 403

        data = request.get_json(silent=True) or {}
        title = (data.get('title') or '').strip()
        message = (data.get('message') or '').strip()
        is_urgent = bool(data.get('is_urgent'))
        target_type = (data.get('target_type') or 'ALL').strip().upper()
        target_team_val = (data.get('target_team') or '').strip().upper() or None
        target_user_ids_raw = data.get('target_user_ids') or []
        order_id_val = data.get('order_id')

        if not title:
            return jsonify({'success': False, 'message': '제목을 입력해주세요.'}), 400
        if target_type not in ('ALL', 'TEAM', 'USER'):
            return jsonify({'success': False, 'message': '대상 유형이 올바르지 않습니다.'}), 400
        if target_type == 'TEAM' and not target_team_val:
            return jsonify({'success': False, 'message': '팀을 선택해주세요.'}), 400
        if target_type == 'USER' and not target_user_ids_raw:
            return jsonify({'success': False, 'message': '사용자를 선택해주세요.'}), 400

        ntype = 'URGENT_ANNOUNCEMENT' if is_urgent else 'ANNOUNCEMENT'

        recipient_ids = resolve_notification_recipient_user_ids(
            db,
            target_type=target_type,
            target_team=target_team_val,
            target_user_ids=target_user_ids_raw,
            include_admin=True,
        )
        if not recipient_ids:
            return jsonify({'success': False, 'message': '수신 대상자가 없습니다.'}), 400

        # 전체/팀/개인 발송 시 수신자별 레코드 생성. 각 레코드는 해당 수신자 전용이므로
        # target_type 을 'USER' 로 저장해, 브리핑 보드 등에서 target_user_id 로 1건만 조회되게 함.
        stored_target_type = 'USER' if target_type in ('ALL', 'TEAM', 'USER') else target_type
        for uid in recipient_ids:
            notif = Notification(
                order_id=int(order_id_val) if order_id_val else None,
                notification_type=ntype,
                target_type=stored_target_type,
                target_team=target_team_val,
                target_user_id=uid,
                is_urgent=is_urgent,
                title=title,
                message=message or None,
                created_by_user_id=user_id,
                created_by_name=str(user.name or ''),
                is_read=False,
            )
            db.add(notif)

        db.flush()
        db.commit()

        invalidate_badge_cache_for_user_ids(recipient_ids)

        from services.realtime_notifications import emit_erp_notification_to_users
        payload = {
            'title': title,
            'message': message,
            'urgent': is_urgent,
            'notification_type': ntype,
            'order_id': int(order_id_val) if order_id_val else None,
            'created_by_name': str(user.name or ''),
        }
        realtime_sent = emit_erp_notification_to_users(list(recipient_ids), payload)

        msg = f'{len(recipient_ids)}명에게 알림을 발송했습니다.'
        if realtime_sent < len(recipient_ids) and len(recipient_ids) > 0:
            msg += f' (실시간 전송: {realtime_sent}명 — 일부는 새로고침 시 확인)'

        return jsonify({
            'success': True,
            'message': msg,
            'sent_count': len(recipient_ids),
            'realtime_sent': realtime_sent,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'message': str(e)}), 500


@notifications_bp.route('/orders/<int:order_id>/urgent-mention', methods=['POST'])
@login_required
def api_order_urgent_mention(order_id):
    """주문 상세에서 특정 동료를 긴급 호출(멘션).
    
    Body: { target_user_id: int, message: str (선택) }
    """
    try:
        db = get_db()
        sender_id = session.get('user_id')
        sender = db.query(User).filter(User.id == sender_id).first()
        if not sender:
            return jsonify({'success': False, 'message': '사용자 정보를 찾을 수 없습니다.'}), 404

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        data = request.get_json(silent=True) or {}
        target_uid_raw = data.get('target_user_id')
        if not target_uid_raw:
            return jsonify({'success': False, 'message': '호출 대상을 선택해주세요.'}), 400

        try:
            target_uid = int(target_uid_raw)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': '올바르지 않은 사용자입니다.'}), 400

        target_user = db.query(User).filter(User.id == target_uid).first()
        if not target_user:
            return jsonify({'success': False, 'message': '대상 사용자를 찾을 수 없습니다.'}), 404

        msg = (data.get('message') or '').strip()
        customer = order.customer_name or f'#{order_id}'
        title = f'[긴급 멘션] {sender.name}님이 #{order_id} {customer} 주문에서 호출했습니다'

        notif = Notification(
            order_id=order_id,
            notification_type='URGENT_MENTION',
            target_type='USER',
            target_user_id=target_uid,
            is_urgent=True,
            title=title,
            message=msg or None,
            created_by_user_id=sender_id,
            created_by_name=str(sender.name or ''),
            is_read=False,
        )
        db.add(notif)
        db.commit()

        invalidate_badge_cache_for_user_ids([target_uid])

        from services.realtime_notifications import emit_erp_notification_to_users
        payload = {
            'title': title,
            'message': msg or '',
            'urgent': True,
            'notification_type': 'URGENT_MENTION',
            'order_id': order_id,
            'created_by_name': str(sender.name or ''),
        }
        emit_erp_notification_to_users([target_uid], payload)

        return jsonify({
            'success': True,
            'message': f'{target_user.name}님에게 긴급 멘션을 보냈습니다.',
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'message': str(e)}), 500

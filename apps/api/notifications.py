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
from sqlalchemy import or_

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
    if n_type not in ('DRAWING_TRANSFERRED', 'DRAWING_REVISION'):
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
            'deep_link_url': f"/erp/drawing-workbench/{notification.order_id}?tab={target_tab}",
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
    deep_link_url = f"/erp/drawing-workbench/{notification.order_id}?{'&'.join(query_parts)}"
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
        user_team = user.team.upper() if user.team else None
        user_name = user.name.strip() if user.name else None

        if _NOTIFICATION_DEBUG:
            print(f"[DEBUG] Notification Check - User: '{user_name}', Team: '{user_team}'")

        if user.role != 'ADMIN':
            conditions = []
            if user_team:
                conditions.append(Notification.target_team == user_team)
            if user_name:
                conditions.append(Notification.target_manager_name == user_name)
            if conditions:
                query = query.filter(or_(*conditions))
            else:
                return jsonify({'success': True, 'notifications': [], 'unread_count': 0})

        if unread_only:
            query = query.filter(Notification.is_read == False)

        query = query.order_by(Notification.created_at.desc()).limit(limit)
        notifications = query.all()

        unread_query = db.query(Notification).filter(Notification.is_read == False)
        if user.role != 'ADMIN':
            conditions = []
            if user_team:
                conditions.append(Notification.target_team == user_team)
            if user_name:
                conditions.append(Notification.target_manager_name == user_name)
            if conditions:
                unread_query = unread_query.filter(or_(*conditions))
        unread_count = unread_query.count()

        order_ids = list({int(n.order_id) for n in notifications if getattr(n, 'order_id', None)})
        order_map = {}
        if order_ids:
            order_rows = db.query(Order.id, Order.structured_data).filter(Order.id.in_(order_ids)).all()
            for oid, sd in order_rows:
                order_map[int(oid)] = _ensure_dict(sd)

        notif_payloads = []
        for n in notifications:
            row = n.to_dict()
            deep = _resolve_notification_deep_link(n, order_map.get(int(n.order_id), {}))
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

        user_team = user.team.upper() if user.team else None
        user_name = user.name

        query = db.query(Notification).filter(Notification.is_read == False)

        if user.role != 'ADMIN':
            conditions = []
            if user_team:
                conditions.append(Notification.target_team == user_team)
            if user_name:
                conditions.append(Notification.target_manager_name == user_name)
            if conditions:
                query = query.filter(or_(*conditions))
            else:
                count = 0
                _badge_cache[user_id] = (count, now_ts + BADGE_CACHE_TTL_SECONDS)
                return jsonify({'success': True, 'count': count})

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

        user_team = user.team.upper() if user.team else None
        user_name = user.name

        query = db.query(Notification).filter(Notification.is_read == False)

        if user.role != 'ADMIN':
            conditions = []
            if user_team:
                conditions.append(Notification.target_team == user_team)
            if user_name:
                conditions.append(Notification.target_manager_name == user_name)
            if conditions:
                query = query.filter(or_(*conditions))

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

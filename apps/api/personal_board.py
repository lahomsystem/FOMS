"""
개인 맞춤형 브리핑 보드 API.
계획서: docs/plans/2026-03-02-personal-briefing-board-plan.md
- GET /api/personal-board/summary: 내 업무 스트림, 공지, 알림/채팅 수, 최근 작업 등 통합 요약.
"""
import datetime

from flask import Blueprint, jsonify, session
from sqlalchemy import or_, func, and_

from db import get_db
from models import (
    Order,
    User,
    Notification,
    OrderEvent,
    OrderTask,
    ChatRoomMember,
    ChatMessage,
)
from apps.auth import login_required
from services.erp_policy import DEFAULT_OWNER_TEAM_BY_STAGE, STAGE_LABELS

personal_board_bp = Blueprint(
    'personal_board',
    __name__,
    url_prefix='/api/personal-board',
)

# 단계별 딥링크 URL 매핑 (해당 단계의 전용 대시보드로 직접 이동)
STAGE_DASHBOARD_URL = {
    "RECEIVED":     "/erp/dashboard",
    "HAPPYCALL":    "/erp/dashboard",
    "MEASURE":      "/erp/measurement",
    "DRAWING":      "/erp/drawing-workbench",
    "CONFIRM":      "/erp/dashboard",
    "PRODUCTION":   "/erp/production/dashboard",
    "CONSTRUCTION": "/erp/construction/dashboard",
    "CS":           "/erp/dashboard",
    "COMPLETED":    "/erp/completion",
    "AS":           "/erp/as",
    "AS_RECEIVED":  "/erp/as",
    "AS_COMPLETED": "/erp/as",
}


def _display_customer_name(customer_name, structured_data, order_id):
    """브리핑 보드 표시용 고객명. ERP Beta 플레이스홀더('ERP Beta') 대신 structured_data 또는 주문번호 사용."""
    if isinstance(structured_data, dict):
        parties = structured_data.get('parties') or {}
        name = (parties.get('customer') or {}).get('name')
        if name and str(name).strip():
            return str(name).strip()
    raw = (customer_name or '').strip()
    if raw.upper() in ('ERP BETA', 'ERP_BETA'):
        return f'#{order_id}'
    return customer_name or f'#{order_id}'


def _order_card(order_id, customer_name, status, structured_data):
    """주문 한 건을 위젯에서 표시할 카드 딕셔너리로 변환."""
    from services.erp_display import _erp_get_stage
    from services.erp_policy import STAGE_NAME_TO_CODE
    
    sd = structured_data or {}
    stage = status or ''
    if str(stage).lower() == 'erpbeta':
        stage = _erp_get_stage(None, sd) or '주문접수'

    stage_code = STAGE_NAME_TO_CODE.get(stage, stage)
    stage_label = STAGE_LABELS.get(stage_code, stage)
    
    is_urgent = bool((sd.get('flags') or {}).get('urgent'))
    stage_dashboard = STAGE_DASHBOARD_URL.get(stage_code, '/erp/dashboard')
    display_name = _display_customer_name(customer_name, sd, order_id)
    # 클릭 시 해당 주문 건으로 이동 (브리핑 보드 리다이렉트 정확도)
    deep_url = f'/edit/{order_id}?open=erp-beta'

    return {
        'order_id': order_id,
        'customer_name': display_name,
        'status': stage_code,
        'stage_label': stage_label,
        'is_urgent': is_urgent,
        'deep_url': deep_url,
        'stage_dashboard': stage_dashboard,
    }


def _work_stream_counts(db, user_team):
    """내 팀 소유 단계별 주문 건수. N+1 없이 한 번에 집계."""
    if not user_team:
        return {}
    team_upper = (user_team or '').strip().upper()
    stages_for_team = [s for s, t in DEFAULT_OWNER_TEAM_BY_STAGE.items() if (t or '').upper() == team_upper]
    if not stages_for_team:
        return {}
    rows = (
        db.query(Order.status, func.count(Order.id))
        .filter(Order.status.in_(stages_for_team))
        .filter(Order.status != 'DELETED')
        .group_by(Order.status)
        .all()
    )
    result = {}
    for s, c in rows:
        label = STAGE_LABELS.get(str(s), str(s))
        result[label] = int(c or 0)
    return result


def _announcements_count(db):
    """공지사항(ANNOUNCEMENT) 최근 건수."""
    try:
        q = db.query(func.count(Notification.id)).filter(
            Notification.notification_type == 'ANNOUNCEMENT'
        )
        return int(q.scalar() or 0)
    except Exception:
        return 0


def _unread_notifications_count(db, user, user_id):
    """현재 사용자 대상 미읽음 알림 수."""
    if not user:
        return 0
    q = db.query(Notification).filter(Notification.is_read == False)
    if user.role == 'ADMIN':
        return q.count()
    conditions = []
    if user.team:
        conditions.append(Notification.target_team == (user.team or '').strip().upper())
    if user.name:
        conditions.append(Notification.target_manager_name == (user.name or '').strip())
    conditions.append(Notification.target_user_id == user_id)
    conditions.append(Notification.target_type == 'ALL')
    if not conditions:
        return 0
    q = q.filter(or_(*conditions))
    return q.count()


def _unread_chats_count(db, user_id):
    """미읽음 메시지가 있는 채팅방 수."""
    try:
        sub = (
            db.query(ChatMessage.room_id)
            .join(
                ChatRoomMember,
                and_(
                    ChatRoomMember.room_id == ChatMessage.room_id,
                    ChatRoomMember.user_id == user_id,
                ),
            )
            .filter(
                or_(
                    ChatRoomMember.last_read_at.is_(None),
                    ChatMessage.created_at > ChatRoomMember.last_read_at,
                )
            )
            .distinct()
        )
        return len(sub.all())
    except Exception:
        return 0


def _recent_work(db, user_id, limit=5):
    """내가 최근 작업한 주문 카드 목록 (고객명+단계+딥링크 포함)."""
    try:
        rows = (
            db.query(OrderEvent.order_id)
            .filter(OrderEvent.created_by_user_id == user_id)
            .order_by(OrderEvent.created_at.desc())
            .limit(limit * 3)  # 중복 제거 후 limit 맞추기 위해 넉넉하게
            .all()
        )
        # 중복 order_id 제거 (최근 순 유지)
        seen = set()
        order_ids = []
        for (oid,) in rows:
            if oid not in seen:
                seen.add(oid)
                order_ids.append(oid)
            if len(order_ids) >= limit:
                break

        if not order_ids:
            return []

        orders = (
            db.query(Order.id, Order.customer_name, Order.status, Order.structured_data)
            .filter(Order.id.in_(order_ids))
            .all()
        )
        order_map = {o[0]: o for o in orders}
        result = []
        for oid in order_ids:
            if oid in order_map:
                _, cname, status, sd = order_map[oid]
                result.append(_order_card(oid, cname, status, sd))
        return result
    except Exception:
        return []


def _stalled_count(db, user_team, days=3):
    """3일 이상 이벤트 변경 없는 내 팀 소유 주문 건수."""
    if not user_team:
        return 0
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
        subq = (
            db.query(OrderEvent.order_id, func.max(OrderEvent.created_at).label('last_at'))
            .group_by(OrderEvent.order_id)
            .subquery()
        )
        stalled_order_ids = [r[0] for r in db.query(subq.c.order_id).filter(subq.c.last_at < cutoff).all()]
        if not stalled_order_ids:
            return 0
        stages = [s for s, t in DEFAULT_OWNER_TEAM_BY_STAGE.items() if (t or '').upper() == (user_team or '').strip().upper()]
        if not stages:
            return 0
        return (
            db.query(Order.id)
            .filter(Order.id.in_(stalled_order_ids))
            .filter(Order.status.in_(stages))
            .filter(Order.status != 'DELETED')
            .count()
        )
    except Exception:
        return 0


def _pending_quest_and_task(db, user_id, user_team):
    """OPEN Task 건수."""
    task_count = (
        db.query(OrderTask.id)
        .filter(OrderTask.status == 'OPEN')
        .filter(OrderTask.owner_user_id == user_id)
        .count()
    )
    return 0, task_count


def _settlement_alerts_count(db, user_id):
    """나에게 귀속된 비용 차감 건수."""
    try:
        from apps.api.erp_orders_completion import TARGET_STATUSES
        orders = (
            db.query(Order.id, Order.structured_data)
            .filter(Order.deleted_at.is_(None), Order.status.in_(TARGET_STATUSES))
            .limit(500)
            .all()
        )
        count = 0
        for _oid, sd in orders:
            if not isinstance(sd, dict):
                continue
            settlement = sd.get('settlement') or {}
            deductions = settlement.get('deductions') or []
            for d in deductions:
                if isinstance(d, dict) and d.get('charge_to_user_id') == user_id:
                    count += 1
                    break
        return count
    except Exception:
        return 0


def _urgent_notifications(db, user, user_id, limit=10):
    """미읽음 긴급 알림 목록 (브리핑 보드 상단 배너용).
    전체 공지는 수신자별 레코드(target_type='USER', target_user_id=uid)로 저장되므로
    비관리자는 target_user_id == user_id 로 자기 1건만 조회. 관리자/기존 데이터는
    동일 공지(title+message+created_at) 중복 제거로 1건만 노출.
    """
    try:
        q = db.query(Notification).filter(
            Notification.is_urgent == True,
            Notification.is_read == False,
        )
        if user.role != 'ADMIN':
            conditions = []
            if user.team:
                conditions.append(Notification.target_team == (user.team or '').strip().upper())
            if user.name:
                conditions.append(Notification.target_manager_name == (user.name or '').strip())
            conditions.append(Notification.target_user_id == user_id)
            conditions.append(Notification.target_type == 'ALL')
            q = q.filter(or_(*conditions))
        rows = q.order_by(Notification.created_at.desc()).limit(limit * 3).all()
        # 동일 공지 중복 제거: (title, message, created_at) 기준으로 첫 건만 사용
        seen = set()
        out = []
        for n in rows:
            key = (n.title or '', n.message or '', n.created_at.strftime('%Y-%m-%d %H:%M:%S') if n.created_at else '')
            if key in seen:
                continue
            seen.add(key)
            out.append({
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'order_id': n.order_id,
                'notification_type': n.notification_type,
                'created_by_name': n.created_by_name,
                'created_at': n.created_at.strftime('%Y-%m-%d %H:%M:%S') if n.created_at else None,
            })
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


def _schedule_today_tomorrow(db, user_id, user_team):
    """오늘/내일 실측·시공 일정 카드 (고객명+단계+딥링크 포함)."""
    today_s = datetime.date.today().strftime('%Y-%m-%d')
    tomorrow_s = (datetime.date.today() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    out_today = []
    out_tomorrow = []
    type_label = {'measurement': '실측', 'construction': '시공'}
    type_url = {'measurement': '/erp/measurement', 'construction': '/erp/construction/dashboard'}
    try:
        orders = (
            db.query(Order.id, Order.customer_name, Order.status, Order.structured_data)
            .filter(Order.deleted_at.is_(None))
            .order_by(Order.id.desc())
            .limit(300)
            .all()
        )
        for oid, cname, status, sd in orders:
            if not isinstance(sd, dict):
                continue
            
            stage = status or ''
            if str(stage).lower() == 'erpbeta':
                from services.erp_display import _erp_get_stage
                stage = _erp_get_stage(None, sd) or '주문접수'
            
            from services.erp_policy import STAGE_NAME_TO_CODE, STAGE_LABELS
            stage_code = STAGE_NAME_TO_CODE.get(stage, stage)
            stage_label = STAGE_LABELS.get(stage_code, stage)

            sched = sd.get('schedule') or {}
            for stype in ('measurement', 'construction'):
                date_val = (sched.get(stype) or {}).get('date') or ''
                time_val = (sched.get(stype) or {}).get('time') or ''
                
                # 클릭 시 해당 주문 건으로 이동 (내일 일정 '이새롬' 등 → 해당 탭의 해당 주문)
                order_detail_url = f'/edit/{oid}?open=erp-beta'

                display_name = _display_customer_name(cname, sd, oid)
                if date_val == today_s:
                    out_today.append({
                        'order_id': oid,
                        'customer_name': display_name,
                        'type': stype,
                        'type_label': type_label[stype],
                        'date': date_val,
                        'time': time_val,
                        'status': stage_code,
                        'stage_label': stage_label,
                        'is_urgent': bool((sd.get('flags') or {}).get('urgent')),
                        'deep_url': order_detail_url,
                    })
                elif date_val == tomorrow_s:
                    out_tomorrow.append({
                        'order_id': oid,
                        'customer_name': display_name,
                        'type': stype,
                        'type_label': type_label[stype],
                        'date': date_val,
                        'time': time_val,
                        'status': stage_code,
                        'stage_label': stage_label,
                        'is_urgent': bool((sd.get('flags') or {}).get('urgent')),
                        'deep_url': order_detail_url,
                    })
        return out_today[:20], out_tomorrow[:20]
    except Exception:
        return [], []


@personal_board_bp.route('/summary', methods=['GET'])
@login_required
def api_summary():
    """브리핑 보드 통합 요약. 배치 쿼리로 N+1 방지."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401

    try:
        db = get_db()
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 404

        work_stream = _work_stream_counts(db, user.team)
        announcements_count = _announcements_count(db)
        noti_count = _unread_notifications_count(db, user, user_id)
        unread_chats = _unread_chats_count(db, user_id)
        recent_work = _recent_work(db, user_id)
        stalled_count = _stalled_count(db, user.team)
        pending_quest, pending_task = _pending_quest_and_task(db, user_id, user.team)
        settlement_alerts = _settlement_alerts_count(db, user_id)
        schedule_today, schedule_tomorrow = _schedule_today_tomorrow(db, user_id, user.team)
        urgent_notifications = _urgent_notifications(db, user, user_id)

        return jsonify({
            'success': True,
            'work_stream': work_stream,
            'announcements_count': announcements_count,
            'urgent_inbox': {'notifications': noti_count, 'unread_chats': unread_chats},
            'stalled_count': stalled_count,
            'recent_work': recent_work,
            'schedule_today': schedule_today,
            'schedule_tomorrow': schedule_tomorrow,
            'settlement_alerts': settlement_alerts,
            'pending_quest_count': pending_quest,
            'pending_task_count': pending_task,
            'urgent_notifications': urgent_notifications,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

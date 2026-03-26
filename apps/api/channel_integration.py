"""
채널톡 연동 API Blueprint.
수동 푸쉬, 웹훅 수신 등 채널톡 양방향 통신을 담당.
"""

import copy
import datetime
import logging
import os
import traceback

from flask import Blueprint, request, jsonify
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, OrderAttachment
from apps.auth import login_required, role_required
from services.storage import get_storage
from services.channel_client import is_configured, send_group_message
from services.channel_delivery import get_delivery_metrics, get_queue_backlog, check_legacy_only_success_after_cutover
from services.jobs.queue import get_rq_queue

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 4000

channel_integration_bp = Blueprint('channel_integration', __name__, url_prefix='/api/channel')

_MIME_MAP = {
    'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
    'gif': 'image/gif', 'webp': 'image/webp',
    'mp4': 'video/mp4', 'mov': 'video/quicktime', 'avi': 'video/avi',
    'mkv': 'video/x-matroska', 'webm': 'video/webm',
}


def _infer_mime(filename: str, file_type: str) -> str:
    """
    첨부파일 MIME 타입 추론.

    Args:
        filename: 파일명 (확장자 포함)
        file_type: OrderAttachment.file_type ('image' 또는 'video')

    Returns:
        MIME 타입 문자열
    """
    if filename and '.' in filename:
        ext = filename.rsplit('.', 1)[-1].lower()
        if ext in _MIME_MAP:
            return _MIME_MAP[ext]
    return 'video/mp4' if file_type == 'video' else 'image/jpeg'


@channel_integration_bp.route('/push-manual', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_channel_push_manual():
    """
    ERP Beta 수동 채널톡 푸쉬.

    사용자가 변환된 텍스트 + 현재 주문의 전체 첨부파일(이미지+동영상)을
    채널톡 그룹으로 즉시 전송합니다.

    Request JSON:
        order_id (int): 주문 ID
        text (str): 전송할 텍스트 (변환된 내용)

    Returns:
        {success: bool, files_count: int, error: str}
    """
    db = get_db()
    try:
        payload = request.get_json(silent=True) or {}
        order_id = payload.get('order_id')
        text = (payload.get('text') or '').strip()

        if not order_id:
            return jsonify({'success': False, 'message': 'order_id가 없습니다.'}), 400
        if not text:
            return jsonify({'success': False, 'message': '전송할 텍스트가 없습니다. 변환 버튼을 먼저 누르거나 내용을 입력해주세요.'}), 400
        if len(text) > _MAX_TEXT_LENGTH:
            return jsonify({'success': False, 'message': f'텍스트가 너무 깁니다 (최대 {_MAX_TEXT_LENGTH}자).'}), 400

        if not is_configured():
            msg = '채널톡 환경변수(CHANNEL_APP_SECRET, CHANNEL_ID)가 서버에 설정되지 않았습니다.'
            return jsonify({'success': False, 'message': msg, 'error': msg}), 503

        group_id = os.environ.get('CHANNEL_GROUP_MEASUREMENT', '')
        if not group_id:
            msg = 'CHANNEL_GROUP_MEASUREMENT 환경변수가 설정되지 않았습니다.'
            return jsonify({'success': False, 'message': msg, 'error': msg}), 503

        order = db.query(Order).filter(Order.id == int(order_id), Order.active_filter()).first()
        if not order:
            return jsonify({'success': False, 'message': f'주문 #{order_id}을 찾을 수 없습니다.'}), 404

        # 이전 푸쉬 이력 확인 → 재전송이면 [수정] prefix 추가
        # message_id 유무와 무관하게 pushed=True 플래그로 재전송 여부 판단
        sd = copy.deepcopy(order.structured_data or {})
        prev_push = sd.get('channeltalk_push') or {}
        if prev_push.get('pushed'):
            text = f"[수정]\n{text}"

        # 현재 주문의 전체 첨부파일 (이미지 + 동영상, 업로드 순서대로)
        attachments = (
            db.query(OrderAttachment)
            .filter(OrderAttachment.order_id == order.id)
            .order_by(OrderAttachment.id.asc())
            .all()
        )

        storage = get_storage()
        files = []
        for att in attachments:
            if not att.storage_key:
                continue
            url = storage.get_download_url(att.storage_key, expires_in=3600)
            if url:
                files.append({
                    'fileName': att.filename or 'file',
                    'url': url,
                    'mime': _infer_mime(att.filename or '', att.file_type or 'image'),
                })

        result = send_group_message(
            group_id=group_id,
            plain_text=text,
            files=files,
            raise_on_error=True,
        )

        # 전송 성공 후 push 이력을 structured_data에 저장
        msg_id = result.get('message_id')
        if not msg_id:
            logger.warning("[채널톡 수동푸쉬] 전송 성공이나 message_id 미수신 (order_id=%s)", order_id)
        sd['channeltalk_push'] = {
            'pushed': True,
            'message_id': msg_id,
            'group_id': group_id,
            'sent_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'is_modified': bool(prev_push.get('pushed')),
        }
        order.structured_data = sd
        flag_modified(order, 'structured_data')
        db.commit()

        return jsonify({'success': True, 'files_count': len(files)})

    except RuntimeError as e:
        # 채널톡 API 레벨 오류 (토큰 발급 실패, API 거부 등)
        err_msg = str(e)
        logger.error("[채널톡 수동푸쉬] RuntimeError: %s", err_msg)
        return jsonify({'success': False, 'message': f'채널톡 API 오류: {err_msg}', 'error': err_msg}), 502

    except Exception as e:
        err_msg = str(e)
        logger.error("[채널톡 수동푸쉬] 예외: %s\n%s", err_msg, traceback.format_exc())
        return jsonify({'success': False, 'message': f'서버 오류: {err_msg}', 'error': err_msg}), 500

@channel_integration_bp.route('/health', methods=['GET'])
def api_channel_health():
    """
    ChannelTalk 연동 상태 헬스체크 및 readiness 판단. (CT-00-03)
    반환 상태: ready, degraded, fail
    """
    db = get_db()
    
    # 1. 환경변수 체크
    has_app_secret = bool(os.environ.get('CHANNEL_APP_SECRET'))
    has_channel_id = bool(os.environ.get('CHANNEL_ID'))
    has_signing_key = bool(os.environ.get('CHANNEL_SIGNING_KEY'))
    has_foms_base_url = bool(os.environ.get('FOMS_BASE_URL'))
    
    # 2. Feature Flags
    flags = {
        'push': os.environ.get('CHANNEL_PUSH_ENABLED', 'false').lower() == 'true',
        'command': os.environ.get('CHANNEL_COMMAND_ENABLED', 'false').lower() == 'true',
        'wam': os.environ.get('CHANNEL_WAM_ENABLED', 'false').lower() == 'true',
        'webhook': os.environ.get('CHANNEL_WEBHOOK_ENABLED', 'false').lower() == 'true',
        'inbound_create': os.environ.get('CHANNEL_INBOUND_CREATE_ENABLED', 'false').lower() == 'true',
        'write_action': os.environ.get('CHANNEL_WRITE_ACTION_ENABLED', 'false').lower() == 'true',
    }
    
    # 3. Queue / Worker 상태
    redis_url = os.environ.get('REDIS_URL')
    q = get_rq_queue()
    queue_state = 'reachable' if q else ('disabled' if not redis_url else 'unreachable')
    rq_worker_count = len(q.registry.get_worker_ids()) if q else 0
    
    # backlog / drift
    backlog_count = get_queue_backlog(db)
    legacy_success_drift = check_legacy_only_success_after_cutover(db)
    
    # metrics
    metrics = get_delivery_metrics(db)
    
    # 4. 의존 행렬 위반 점검
    flag_violations = []
    if flags['inbound_create'] and not flags['webhook']:
        flag_violations.append('INBOUND_CREATE_REQUIRES_WEBHOOK')
    if flags['write_action'] and not (flags['command'] or flags['wam']):
        flag_violations.append('WRITE_ACTION_REQUIRES_COMMAND_OR_WAM')
        
    # Readiness 판정
    # fail-closed 조건
    if not has_foms_base_url:
        readiness = 'fail'
    elif (flags['push'] or flags['webhook']) and rq_worker_count < 1:
        readiness = 'fail'
    elif flag_violations:
        readiness = 'fail'
    elif legacy_success_drift > 0:
        readiness = 'degraded'
    else:
        readiness = 'ready'
        
    return jsonify({
        'readiness': readiness,
        'environment': {
            'CHANNEL_APP_SECRET': has_app_secret,
            'CHANNEL_ID': has_channel_id,
            'CHANNEL_SIGNING_KEY': has_signing_key,
            'FOMS_BASE_URL': has_foms_base_url,
        },
        'flags': flags,
        'flag_violations': flag_violations,
        'queue': {
            'state': queue_state,
            'worker_count': rq_worker_count,
            'backlog_count': backlog_count,
        },
        'metrics': metrics,
        'security': {
            'signature_verification': True,  # 향후 CT-C-01 적용 시 실제 상태 연동
            'replay_window_seconds': int(os.environ.get('CHANNEL_REPLAY_WINDOW_SECONDS', 300))
        },
        'legacy_only_success_after_cutover': legacy_success_drift,
    }), 200 if readiness != 'fail' else 503

@channel_integration_bp.route('/admin/delivery-status', methods=['GET'])
@login_required
@role_required(['ADMIN', 'MANAGER'])
def api_channel_admin_delivery_status():
    """
    운영 조회용 Admin API (최근 실패 내역, backlog 확인)
    """
    db = get_db()
    
    try:
        from models import ChannelDeliveryLog
        limit = request.args.get('limit', 50, type=int)
        
        logs = db.query(ChannelDeliveryLog)\
            .order_by(ChannelDeliveryLog.id.desc())\
            .limit(limit)\
            .all()
            
        result = []
        for log in logs:
            result.append({
                'id': log.id,
                'event_key': log.event_key,
                'source_type': log.source_type,
                'source_id': log.source_id,
                'status': log.status,
                'retry_count': log.retry_count,
                'last_error': log.last_error,
                'created_at': log.created_at.isoformat() if log.created_at else None,
            })
            
        return jsonify({
            'success': True,
            'metrics': get_delivery_metrics(db),
            'backlog_count': get_queue_backlog(db),
            'recent_logs': result
        })
    except Exception as e:
        logger.error("[ChannelAdmin] delivery_status 오류: %s", str(e), exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


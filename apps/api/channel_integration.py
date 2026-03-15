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

"""채팅 유틸: 파일 검증, 썸네일 생성."""
import os
from concurrent.futures import ThreadPoolExecutor
from constants import CHAT_ALLOWED_EXTENSIONS
from services.storage import get_storage
from db import db_session
from models import ChatAttachment
from apps.api.files import build_file_view_url

_thumb_workers = int(os.environ.get('CHAT_THUMBNAIL_WORKERS', '2') or 2)
_thumb_workers = max(1, min(_thumb_workers, 4))
chat_thumbnail_executor = ThreadPoolExecutor(max_workers=_thumb_workers)


def allowed_chat_file(filename):
    """채팅용 파일 확장자 검증"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in CHAT_ALLOWED_EXTENSIONS


def get_chat_file_max_size(filename):
    """채팅 파일 타입별 최대 크기 제한 (바이트)"""
    if '.' not in filename:
        return 10 * 1024 * 1024  # 기본 10MB
    ext = filename.rsplit('.', 1)[1].lower()
    image_exts = ['jpg', 'jpeg', 'png', 'gif', 'webp']
    video_exts = ['mp4', 'mov', 'avi', 'mkv', 'webm']
    if ext in image_exts:
        return 10 * 1024 * 1024  # 10MB
    if ext in video_exts:
        return 500 * 1024 * 1024  # 500MB
    return 50 * 1024 * 1024  # 50MB


def _generate_chat_thumbnail_background(storage_key: str):
    """storage_key 기준으로 썸네일 생성 후 ChatAttachment.thumbnail_url 업데이트"""
    if not storage_key:
        return
    try:
        storage = get_storage()
        result = storage.generate_thumbnail_from_storage_key(storage_key)
        if not result.get('success'):
            return
        thumbnail_key = result.get('thumbnail_key')
        if not thumbnail_key:
            return
        attachment_db = db_session()
        try:
            attachment = attachment_db.query(ChatAttachment).filter(
                ChatAttachment.storage_key == storage_key
            ).order_by(ChatAttachment.id.desc()).first()
            if attachment and not attachment.thumbnail_url:
                attachment.thumbnail_url = build_file_view_url(thumbnail_key)
                attachment_db.commit()
        finally:
            attachment_db.close()
            db_session.remove()
    except Exception as e:
        print(f"[ChatThumbnail] background generation error: {e}")


def schedule_chat_thumbnail_generation(storage_key: str):
    """채팅 썸네일 비동기 작업 큐잉"""
    if not storage_key:
        return
    try:
        chat_thumbnail_executor.submit(_generate_chat_thumbnail_background, storage_key)
    except Exception as e:
        print(f"[ChatThumbnail] schedule error: {e}")

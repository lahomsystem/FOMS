"""파일 확장자 검증 유틸 (app.py에서 분리)."""
from constants import ALLOWED_EXTENSIONS, ERP_MEDIA_ALLOWED_EXTENSIONS


def allowed_file(filename):
    """엑셀 업로드 확장자 검증."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_erp_media_file(filename):
    """ERP 첨부(사진/동영상) 확장자 검증."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ERP_MEDIA_ALLOWED_EXTENSIONS

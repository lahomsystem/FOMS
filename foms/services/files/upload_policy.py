"""Upload extension allowlists and direct-upload Content-Type policy."""

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

# 채팅 파일 업로드용 확장자
CHAT_ALLOWED_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'gif', 'webp',
    'mp4', 'mov', 'avi', 'mkv', 'webm',
    'pdf', 'doc', 'docx', 'xlsx', 'xls', 'txt', 'zip', 'rar'
}

ERP_MEDIA_ALLOWED_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'gif', 'webp',
    'mp4', 'mov', 'avi', 'mkv', 'webm',
}

# Phase D: Direct upload 세션 발급 시 허용 Content-Type (보안)
DIRECT_UPLOAD_ALLOWED_CONTENT_TYPES = frozenset({
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
    'video/mp4', 'video/quicktime', 'video/x-msvideo',
    'video/x-matroska', 'video/webm',
    'application/pdf', 'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel', 'text/plain',
    'application/zip', 'application/x-rar-compressed',
    'application/octet-stream',
})

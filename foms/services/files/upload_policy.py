"""Upload extension allowlists and direct-upload Content-Type policy."""

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

# heic/heif = 아이폰 원본 — 받은 뒤 서버가 JPEG 로 바꾼다(SPEC 2026-11-04-heic-to-jpeg).
ERP_MEDIA_ALLOWED_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif',
    'mp4', 'mov', 'avi', 'mkv', 'webm',
}

# Phase D: Direct upload 세션 발급 시 허용 Content-Type (보안)
DIRECT_UPLOAD_ALLOWED_CONTENT_TYPES = frozenset({
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
    'image/heic', 'image/heif',
    'video/mp4', 'video/quicktime', 'video/x-msvideo',
    'video/x-matroska', 'video/webm',
    'application/pdf', 'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel', 'text/plain',
    'application/zip', 'application/x-rar-compressed',
    'application/octet-stream',
})

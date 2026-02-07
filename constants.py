
# Constants for the application

# Order status constants
STATUS = {
    'RECEIVED': '접수',
    'MEASURED': '실측',
    'REGIONAL_MEASURED': '지방실측',
    'SCHEDULED': '설치 예정',
    'SHIPPED_PENDING': '상차 예정',
    'COMPLETED': '완료',
    'AS_RECEIVED': 'AS 접수',
    'AS_COMPLETED': 'AS 완료',
    'ON_HOLD': '보류',
    'DELETED': '삭제됨'
}

# 수납장 상태 매핑
CABINET_STATUS = {
    'RECEIVED': '접수',
    'IN_PRODUCTION': '제작중',
    'SHIPPED': '발송'
}

# 일괄 작업용 상태 목록 (삭제 제외)
BULK_ACTION_STATUS = {k: v for k, v in STATUS.items() if k != 'DELETED'}

# 업로드 경로 설정
UPLOAD_FOLDER = 'static/uploads'
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

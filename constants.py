
# Constants for the application

# Order status constants (Blueprint V3 기준: A→B→C→D→E→F→G→H)
STATUS = {
    # 메인 프로세스 단계
    'RECEIVED': '접수',           # A. 주문접수
    'HAPPYCALL': '해피콜',        # B. 해피콜
    'MEASURE': '실측',            # C. 실측 (영업 방문 또는 고객 셀프)
    'DRAWING': '도면',            # D. 도면 작성
    'CONFIRM': '고객컨펌',        # E. 고객 컨펌
    'PRODUCTION': '생산',         # F. 생산
    'CONSTRUCTION': '시공',       # G. 시공
    'CS': 'CS',                   # H. CS 접수 및 처리 (신규)
    'COMPLETED': '완료',          # 최종 완료
    
    # AS 서브프로세스
    'AS': 'AS처리',              # CS 단계에서 AS 필요 시
    
    # 레거시 호환 (기존 시스템)
    'MEASURED': '실측완료',
    'REGIONAL_MEASURED': '지방실측',
    'SCHEDULED': '설치예정',
    'SHIPPED_PENDING': '상차예정',
    'AS_RECEIVED': 'AS접수',
    'AS_COMPLETED': 'AS완료',
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

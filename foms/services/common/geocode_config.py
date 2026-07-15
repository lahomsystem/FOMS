# 지도 시스템 설정 (canonical; legacy `map_config.py` 대체)
KAKAO_REST_API_KEY = "6b616f811df2a8aeb3ab12ee71152952"

# Kakao Maps JavaScript SDK 앱 키 (클라이언트 노출용 · 도메인 제한 공개 키).
# 실측 "오늘 동선" 스트립이 실지도 위 방문 순서를 그릴 때 사용한다. REST 키와 별개이며
# 뷰가 템플릿 마운트에 data-kakao-js-key 로 주입한다(하드코딩 SSOT = 이 상수).
KAKAO_JS_API_KEY = "28bd94a6ae70d28d1b9226bd4b88e595"

# 기본 설정
DEFAULT_CENTER = [37.5665, 126.9780]  # 서울 중심좌표
MAX_RETRIES = 3                        # API 재시도 횟수
DELAY_BETWEEN_REQUESTS = 0.1           # API 요청 간격 (초)

# 좌표 검증 범위 (한국)
MIN_LAT, MAX_LAT = 33.0, 39.0         # 위도 범위
MIN_LNG, MAX_LNG = 124.0, 132.0       # 경도 범위

# 카카오 API 설정
KAKAO_REST_API_KEY = "6b616f811df2a8aeb3ab12ee71152952"  # 문서에서 제공된 API 키

# 기본 설정
DEFAULT_CENTER = [37.5665, 126.9780]  # 서울 중심좌표
MAX_RETRIES = 3                        # API 재시도 횟수
DELAY_BETWEEN_REQUESTS = 0.1           # API 요청 간격 (초)

# 좌표 검증 범위 (한국)
MIN_LAT, MAX_LAT = 33.0, 39.0         # 위도 범위
MIN_LNG, MAX_LNG = 124.0, 132.0       # 경도 범위 
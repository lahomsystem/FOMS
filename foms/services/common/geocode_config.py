# 지도 시스템 설정 (canonical; legacy `map_config.py` 대체)
import os

# Kakao REST secret 은 env-only (SECRET-01 / P0-2). 하드코딩 금지 · 외부 rotate.
# 미설정 시 상수는 None 이고, 지오코딩 기능 사용 시점에 require_kakao_rest_key() 가
# 명확히 실패한다(기능별 fail-fast — 앱 부팅은 막지 않음).
KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY")


def require_kakao_rest_key() -> str:
    """설정된 Kakao REST 키를 반환하고, 없으면 명확히 실패한다.

    :return: `KAKAO_REST_API_KEY` env 값.
    :raises RuntimeError: env 미설정 시(지오코딩 기능 fail-fast).
    """
    key = os.environ.get("KAKAO_REST_API_KEY")
    if not key:
        raise RuntimeError(
            "KAKAO_REST_API_KEY 환경변수가 설정되지 않았습니다. "
            "지오코딩/주소 검색 기능은 이 키가 필요합니다(하드코딩 금지)."
        )
    return key


def kakao_rest_headers() -> dict:
    """Kakao REST API 호출용 Authorization 헤더를 반환(요청 시점 fail-fast)."""
    return {"Authorization": f"KakaoAK {require_kakao_rest_key()}"}

# Kakao Maps JavaScript SDK 앱 키 (클라이언트 노출용 · 도메인 제한 공개 키).
# 지도 보기(map_view)·AS/출고 일정 지도가 실지도를 그릴 때 사용한다. REST 키와 별개이며
# 뷰가 템플릿 마운트에 data-kakao-js-key 로 주입한다(하드코딩 SSOT = 이 상수).
KAKAO_JS_API_KEY = "28bd94a6ae70d28d1b9226bd4b88e595"

# 기본 설정
DEFAULT_CENTER = [37.5665, 126.9780]  # 서울 중심좌표
MAX_RETRIES = 3                        # API 재시도 횟수
DELAY_BETWEEN_REQUESTS = 0.1           # API 요청 간격 (초)

# 좌표 검증 범위 (한국)
MIN_LAT, MAX_LAT = 33.0, 39.0         # 위도 범위
MIN_LNG, MAX_LNG = 124.0, 132.0       # 경도 범위

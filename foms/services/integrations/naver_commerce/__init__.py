"""네이버 커머스API(스마트스토어) 연동 (NAVER-INGEST-01).

**호출 위치 제약(설계가 아니라 인프라 제약이다)**: 커머스API센터 애플리케이션은 호출 IP를
최대 3개까지 허용하고, Railway static outbound IP도 서비스당 3개다. 정확히 3=3이라 여유가
없다. 따라서 이 패키지의 HTTP는 **WORKER 서비스에서만** 나가야 한다. web 프로세스에서
부르면 등록되지 않은 IP라 차단된다 — web의 "지금 수집"은 rq enqueue만 한다.
"""

from foms.services.integrations.naver_commerce.client import (  # noqa: F401
    NaverCommerceAuthError,
    NaverCommerceClient,
    NaverCommerceConfigError,
    NaverCommerceError,
    NaverCommerceHTTPError,
    build_signature,
    iter_time_windows,
)

__all__ = [
    "NaverCommerceClient",
    "NaverCommerceError",
    "NaverCommerceConfigError",
    "NaverCommerceAuthError",
    "NaverCommerceHTTPError",
    "build_signature",
    "iter_time_windows",
]

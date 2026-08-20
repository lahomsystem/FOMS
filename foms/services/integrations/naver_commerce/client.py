"""네이버 커머스API 클라이언트 — 토큰 캐시·변경분 조회·상세 배치 조회 (NAVER-INGEST-01 §3.2/§3.3).

이 모듈은 **읽기 전용**이다. 발주확인·발송처리 같은 역방향 쓰기는 v1 비목표다.

설계 근거(2026-08-13 실 API 호출로 확인한 사실만 반영):

* 토큰 서명은 bcrypt이고 **``client_secret`` 자체가 salt**다
  (``base64(bcrypt.hashpw(f"{client_id}_{timestamp_ms}", client_secret))``).
  그래서 시크릿은 반드시 ``$2`` 로 시작하는 bcrypt salt 문자열이다 — 아니면 발급이 실패한다.
* 토큰 ``expires_in`` 실측 10799초(3시간). 매 호출 재발급은 낭비이자 rate limit 소모라
  캐시하고 만료 5분 전에만 갱신한다.
* 변경분 조회 구간 상한은 24시간이다. 워터마크가 그보다 뒤처지면 하루씩 나눠 순회해야 한다.
* ``last-changed-statuses`` 는 **상태 변경 이벤트 전부**를 준다(3일에 163건). 신규 주문만
  뽑는 필터는 호출자(수집 파이프라인) 몫이며 여기서는 원본을 그대로 돌려준다.

**HTTP 전송은 주입 가능**하다(``transport``). 테스트는 네트워크 없이 스텁을 넣어 돌린다.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional, Protocol, Sequence

import bcrypt

logger = logging.getLogger(__name__)

BASE_URL = "https://api.commerce.naver.com/external"
KST = timezone(timedelta(hours=9))

#: 변경분 조회 구간 상한. API 제약은 24시간이지만 경계에서 400을 맞지 않도록 1분 여유를 둔다
#: (2026-08-13 실호출은 23h59m 구간으로 성공했다).
MAX_WINDOW = timedelta(hours=23, minutes=59)

#: 상세 조회 1회 배치 크기. 네이버 문서 상한(300)보다 보수적으로 잡아 타임아웃 위험을 줄인다.
DETAIL_BATCH_SIZE = 100

#: 만료 이 시간 전이면 토큰을 새로 받는다(경계에서 401 맞지 않게).
TOKEN_REFRESH_MARGIN_SECONDS = 300

#: 재시도 대상 HTTP 상태. 429=rate limit, 5xx=서버측 일시 오류.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 3
#: 지수 백오프 기본 간격(초). 재시도 n회차 대기 = BACKOFF_BASE * 2**(n-1).
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_CAP_SECONDS = 30.0


class NaverCommerceError(Exception):
    """네이버 커머스API 연동 실패의 최상위 예외."""


class NaverCommerceConfigError(NaverCommerceError):
    """자격증명 미설정·형식 오류 — 재시도해도 소용없는 설정 문제."""


class NaverCommerceAuthError(NaverCommerceError):
    """토큰 발급 실패 또는 갱신 후에도 401."""


class NaverCommerceHTTPError(NaverCommerceError):
    """재시도를 소진했거나 재시도 대상이 아닌 HTTP 오류."""

    def __init__(self, status: int, body: str, *, url: str = "") -> None:
        super().__init__(f"HTTP {status} {url}: {body[:300]}")
        self.status = status
        self.body = body
        self.url = url


class TokenCache(Protocol):
    """토큰 저장소 인터페이스(Redis / 프로세스 메모리 공용)."""

    def get(self, key: str) -> Optional[str]:
        ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        ...


class MemoryTokenCache:
    """프로세스 메모리 토큰 캐시.

    Redis가 없거나 죽었을 때의 폴백이다. replica마다 따로 발급받게 되지만 토큰 발급은
    idempotent라 기능상 문제가 없다 — Redis 장애가 수집 전체를 멈추게 두지 않는 쪽이 낫다.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float]] = {}

    def get(self, key: str) -> Optional[str]:
        """만료되지 않은 값만 돌려준다(만료분은 즉시 버린다)."""
        hit = self._store.get(key)
        if not hit:
            return None
        value, expires_at = hit
        if expires_at <= time.time():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """TTL과 함께 저장한다."""
        self._store[key] = (value, time.time() + max(1, ttl_seconds))


class RedisTokenCache:
    """Redis 토큰 캐시(replica 공용). 모든 오류는 삼키고 캐시 미스로 취급한다.

    스토어 의존 경로의 fail-open 규율이다 — Redis가 죽었다고 주문 수집이 멈추면 안 된다.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self, key: str) -> Optional[str]:
        """캐시 조회. Redis 오류는 미스로 강등한다."""
        try:
            raw = self._client.get(key)
        except Exception as exc:  # noqa: BLE001 - fail-open (로그는 남긴다)
            logger.warning("[NAVER] token cache get 실패(메모리 폴백): %s", exc)
            return None
        if raw is None:
            return None
        return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """캐시 저장. Redis 오류는 무시한다(다음 호출이 재발급하면 그만)."""
        try:
            self._client.setex(key, max(1, ttl_seconds), value)
        except Exception as exc:  # noqa: BLE001 - fail-open
            logger.warning("[NAVER] token cache set 실패(무시): %s", exc)


def default_token_cache() -> TokenCache:
    """REDIS_URL이 있으면 Redis 캐시, 없거나 연결 실패면 메모리 캐시를 준다."""
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return MemoryTokenCache()
    try:
        from redis import Redis

        return RedisTokenCache(Redis.from_url(redis_url, socket_timeout=2))
    except Exception as exc:  # noqa: BLE001 - fail-open
        logger.warning("[NAVER] Redis 토큰 캐시 초기화 실패(메모리 폴백): %s", exc)
        return MemoryTokenCache()


def build_signature(client_id: str, client_secret: str, timestamp_ms: int) -> str:
    """커머스API 전자서명을 만든다.

    ``client_secret`` 이 bcrypt **salt** 로 쓰인다(일반적인 HMAC 서명과 다른 부분이라
    틀리기 쉽다). PowerShell 큰따옴표가 ``$2a`` 를 변수로 치환해 시크릿이 깨지는 사고가
    실제로 있었으므로, salt 형식이 아니면 여기서 명확히 실패시킨다.

    Args:
        client_id: 커머스API센터 애플리케이션 ID.
        client_secret: 애플리케이션 시크릿(bcrypt salt, ``$2`` 로 시작).
        timestamp_ms: 서명 시각(epoch 밀리초). 토큰 요청의 ``timestamp`` 와 같아야 한다.

    Returns:
        base64 인코딩된 서명 문자열.

    Raises:
        NaverCommerceConfigError: 시크릿이 bcrypt salt 형식이 아닐 때.
    """
    if not client_id or not client_secret:
        raise NaverCommerceConfigError(
            "NAVER_COMMERCE_CLIENT_ID / NAVER_COMMERCE_CLIENT_SECRET 가 설정되지 않았다."
        )
    if not client_secret.startswith("$2"):
        raise NaverCommerceConfigError(
            "시크릿 형식 오류: bcrypt salt($2a$04$... 형식)여야 한다. "
            f"받은 값 길이={len(client_secret)}. "
            "PowerShell 큰따옴표는 $2a 를 변수로 치환하므로 작은따옴표를 써야 한다."
        )
    hashed = bcrypt.hashpw(f"{client_id}_{timestamp_ms}".encode("utf-8"),
                           client_secret.encode("utf-8"))
    return base64.b64encode(hashed).decode("utf-8")


def iter_time_windows(start: datetime, end: datetime,
                      max_window: timedelta = MAX_WINDOW) -> Iterator[tuple[datetime, datetime]]:
    """``[start, end]`` 를 API 구간 상한 이하 조각으로 잘라 순서대로 내놓는다.

    워터마크가 24시간보다 뒤처졌을 때(장기 중단 후 재가동) 한 번에 조회하면 400이 난다.
    조각은 앞에서부터 만들며, 마지막 조각의 끝은 항상 ``end`` 다.

    Args:
        start: 구간 시작(포함).
        end: 구간 끝(포함).
        max_window: 조각 하나의 최대 길이.

    Yields:
        ``(구간시작, 구간끝)`` 튜플. ``start >= end`` 면 아무것도 내놓지 않는다.
    """
    if start >= end:
        return
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + max_window, end)
        yield (cursor, chunk_end)
        cursor = chunk_end


def _format_ts(value: datetime) -> str:
    """API가 받는 밀리초 정밀도 ISO-8601(타임존 포함) 문자열로 만든다."""
    aware = value if value.tzinfo else value.replace(tzinfo=KST)
    return aware.astimezone(KST).isoformat(timespec="milliseconds")


class NaverCommerceClient:
    """커머스API 읽기 클라이언트(토큰 캐시 + 재시도 내장).

    WORKER 프로세스에서만 인스턴스화한다(§3.1 IP 제약). 스레드 안전성은 보장하지 않으며,
    폴링 루프 한 개가 한 인스턴스를 쓰는 사용을 전제한다.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        *,
        base_url: str = BASE_URL,
        token_cache: Optional[TokenCache] = None,
        transport: Optional[Any] = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleep: Any = time.sleep,
    ) -> None:
        """자격증명은 인자 우선, 없으면 환경변수에서 읽는다(저장소에 두지 않는다).

        Args:
            client_id: 미지정 시 ``NAVER_COMMERCE_CLIENT_ID``.
            client_secret: 미지정 시 ``NAVER_COMMERCE_CLIENT_SECRET``.
            base_url: API 베이스(테스트 스텁용으로만 바꾼다).
            token_cache: 토큰 저장소. 기본은 Redis(없으면 메모리).
            transport: ``request(method, url, **kwargs)`` 를 가진 객체(기본 ``requests.Session``).
            timeout: 요청 타임아웃(초).
            max_retries: 재시도 횟수(첫 시도 제외).
            sleep: 백오프 대기 함수(테스트 주입용).
        """
        self.client_id = client_id if client_id is not None else os.environ.get("NAVER_COMMERCE_CLIENT_ID", "")
        self._client_secret = (
            client_secret if client_secret is not None
            else os.environ.get("NAVER_COMMERCE_CLIENT_SECRET", "")
        )
        self.base_url = base_url.rstrip("/")
        self._cache = token_cache if token_cache is not None else default_token_cache()
        self._transport = transport
        self._timeout = timeout
        self._max_retries = max_retries
        self._sleep = sleep

    # -- 토큰 ------------------------------------------------------------- #

    @property
    def _cache_key(self) -> str:
        """client_id를 해시해 캐시 키를 만든다(원문을 Redis에 남기지 않는다)."""
        digest = hashlib.sha256(self.client_id.encode("utf-8")).hexdigest()[:16]
        return f"foms:naver_commerce:token:{digest}"

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        """유효한 액세스 토큰을 준다(캐시 히트면 발급하지 않는다).

        Args:
            force_refresh: True면 캐시를 무시하고 재발급한다(401 복구 경로).

        Returns:
            Bearer 토큰 문자열.

        Raises:
            NaverCommerceAuthError: 발급 응답에 ``access_token`` 이 없을 때.
            NaverCommerceConfigError: 자격증명 미설정·형식 오류.
        """
        if not force_refresh:
            cached = self._cache.get(self._cache_key)
            if cached:
                return cached
        token, expires_in = self._issue_token()
        ttl = max(60, int(expires_in) - TOKEN_REFRESH_MARGIN_SECONDS)
        self._cache.set(self._cache_key, token, ttl)
        return token

    def _issue_token(self) -> tuple[str, int]:
        """토큰 발급 호출. ``(토큰, expires_in)`` 을 돌려준다."""
        timestamp_ms = int(time.time() * 1000)
        form = {
            "client_id": self.client_id,
            "timestamp": timestamp_ms,
            "client_secret_sign": build_signature(self.client_id, self._client_secret, timestamp_ms),
            "grant_type": "client_credentials",
            "type": "SELF",
        }
        payload = self._request(
            "POST", "/v1/oauth2/token",
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            authenticated=False,
        )
        token = payload.get("access_token")
        if not token:
            raise NaverCommerceAuthError(
                f"토큰 발급 응답에 access_token 이 없다: {json.dumps(payload, ensure_ascii=False)[:300]}"
            )
        return str(token), int(payload.get("expires_in") or 3600)

    # -- 조회 ------------------------------------------------------------- #

    def get_last_changed_statuses(self, start: datetime, end: datetime) -> list[dict]:
        """한 구간의 상태 변경 이벤트를 그대로 돌려준다(필터 없음).

        구간이 API 상한을 넘으면 :func:`iter_time_windows` 로 잘라 순회한 뒤 이어 붙인다.

        Args:
            start: 구간 시작(naive면 KST로 간주).
            end: 구간 끝.

        Returns:
            ``lastChangeStatuses`` 항목 리스트(원본 dict). 각 항목에 ``productOrderId`` 가 있다.
        """
        collected: list[dict] = []
        for window_start, window_end in iter_time_windows(start, end):
            payload = self._request(
                "GET", "/v1/pay-order/seller/product-orders/last-changed-statuses",
                params={
                    "lastChangedFrom": _format_ts(window_start),
                    "lastChangedTo": _format_ts(window_end),
                },
            )
            chunk = ((payload.get("data") or {}).get("lastChangeStatuses")) or []
            logger.info("[NAVER] 변경분 %s ~ %s: %d건",
                        _format_ts(window_start), _format_ts(window_end), len(chunk))
            collected.extend(chunk)
        return collected

    def get_product_orders(self, product_order_ids: Sequence[str]) -> list[dict]:
        """상품주문 상세를 배치로 조회한다(배치 크기 초과분은 나눠 호출).

        Args:
            product_order_ids: ``productOrderId`` 목록. 빈 목록이면 호출하지 않는다.

        Returns:
            상세 dict 리스트(원본 그대로 — 매핑은 호출자 몫).
        """
        ids = [str(x) for x in product_order_ids if x]
        if not ids:
            return []
        details: list[dict] = []
        for offset in range(0, len(ids), DETAIL_BATCH_SIZE):
            batch = ids[offset:offset + DETAIL_BATCH_SIZE]
            payload = self._request(
                "POST", "/v1/pay-order/seller/product-orders/query",
                json_body={"productOrderIds": batch},
                headers={"Content-Type": "application/json"},
            )
            details.extend(payload.get("data") or [])
        return details

    # -- 쓰기 (T16-G) — WORKER 에서만 호출된다 -------------------------------- #

    def confirm_place_orders(self, product_order_ids: Sequence[str]) -> dict:
        """발주확인 처리 — ``placeOrderStatus`` 를 확인 완료로 올린다.

        결제완료 뒤 판매자가 "이 주문 받았다"를 네이버에 알리는 단계다. 이걸 안 하면 발송
        단계로 넘어가지 않는다.

        Args:
            product_order_ids: 발주확인할 ``productOrderId`` 목록.

        Returns:
            응답 payload(원본). 실패는 :class:`NaverCommerceHTTPError` 로 던진다.

        Raises:
            ValueError: 상품주문번호가 비었을 때(빈 요청으로 API 를 때리지 않는다).
        """
        ids = [str(x) for x in product_order_ids if x]
        if not ids:
            raise ValueError("발주확인할 상품주문번호가 없습니다.")
        return self._request(
            "POST", "/v1/pay-order/seller/product-orders/confirm",
            json_body={"productOrderIds": ids},
            headers={"Content-Type": "application/json"},
        )

    def dispatch_product_orders(self, dispatches: Sequence[dict]) -> dict:
        """발송처리 — 배송 시작을 네이버에 기록한다.

        가구는 자사 배송·시공이라 택배사·송장번호가 없다. 그 경우 배송방법은
        ``DIRECT_DELIVERY``(직접 전달)를 쓴다 — 구매자 배송추적은 없고, 자동 구매확정
        기준이 택배와 달라 **정산 시점이 달라진다**(운영 반영 전 실건 1회로 확인할 것).

        Args:
            dispatches: ``{"productOrderId", "deliveryMethod", "dispatchDate", ...}`` 목록.
                ``dispatchDate`` 는 ISO8601(밀리초 + 타임존) 이어야 한다.

        Returns:
            응답 payload(원본).

        Raises:
            ValueError: 목록이 비었거나 필수 키가 없을 때.
        """
        rows = [row for row in (dispatches or []) if isinstance(row, dict)]
        if not rows:
            raise ValueError("발송처리할 항목이 없습니다.")
        for row in rows:
            if not str(row.get("productOrderId") or "").strip():
                raise ValueError("발송처리 항목에 상품주문번호가 없습니다.")
            if not str(row.get("deliveryMethod") or "").strip():
                raise ValueError("발송처리 항목에 배송방법이 없습니다.")
        return self._request(
            "POST", "/v1/pay-order/seller/product-orders/dispatch",
            json_body={"dispatchProductOrders": rows},
            headers={"Content-Type": "application/json"},
        )

    # -- HTTP ------------------------------------------------------------- #

    def _session(self) -> Any:
        """전송 객체를 준다(주입된 것이 있으면 그것, 없으면 requests 세션)."""
        if self._transport is None:
            import requests

            self._transport = requests.Session()
        return self._transport

    def _request(self, method: str, path: str, *, params: Optional[dict] = None,
                 data: Optional[dict] = None, json_body: Optional[dict] = None,
                 headers: Optional[dict] = None, authenticated: bool = True) -> dict:
        """재시도·토큰 갱신을 포함한 단일 API 호출. 파싱된 JSON dict를 돌려준다.

        429/5xx·네트워크 오류는 지수 백오프로 재시도하고, 401은 토큰을 강제 재발급해
        **한 번만** 다시 시도한다(무한 재발급 루프 방지).

        Raises:
            NaverCommerceHTTPError: 재시도 소진 또는 재시도 대상이 아닌 오류 응답.
            NaverCommerceAuthError: 토큰 재발급 후에도 401.
        """
        url = f"{self.base_url}{path}"
        request_headers = dict(headers or {})
        token_retried = False
        attempt = 0

        while True:
            if authenticated:
                request_headers["Authorization"] = f"Bearer {self.get_access_token()}"
            try:
                response = self._session().request(
                    method, url, params=params, data=data, json=json_body,
                    headers=request_headers, timeout=self._timeout,
                )
            except Exception as exc:  # noqa: BLE001 - 네트워크 계층 예외는 재시도 대상
                if attempt >= self._max_retries:
                    raise NaverCommerceError(f"{method} {url} 네트워크 실패: {exc}") from exc
                attempt += 1
                self._backoff(attempt, reason=str(exc))
                continue

            status = int(getattr(response, "status_code", 0))
            if 200 <= status < 300:
                return self._parse_json(response, url)

            body = self._body_text(response)
            if status == 401 and authenticated and not token_retried:
                token_retried = True
                logger.info("[NAVER] 401 — 토큰 강제 재발급 후 1회 재시도")
                self.get_access_token(force_refresh=True)
                continue
            if status in RETRYABLE_STATUS and attempt < self._max_retries:
                attempt += 1
                self._backoff(attempt, reason=f"HTTP {status}")
                continue
            if status == 401:
                raise NaverCommerceAuthError(f"{method} {url} 인증 실패(401): {body[:300]}")
            raise NaverCommerceHTTPError(status, body, url=url)

    def _backoff(self, attempt: int, *, reason: str) -> None:
        """지수 백오프 대기(상한 있음). 재시도 사유를 남긴다."""
        delay = min(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), BACKOFF_CAP_SECONDS)
        logger.warning("[NAVER] 재시도 %d회차 %.1fs 대기 (%s)", attempt, delay, reason)
        self._sleep(delay)

    @staticmethod
    def _parse_json(response: Any, url: str) -> dict:
        """2xx 응답 본문을 dict로 판다. 본문이 dict가 아니면 오류로 올린다."""
        try:
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - 본문 파싱 실패는 그대로 실패다
            raise NaverCommerceError(f"{url} 응답 JSON 파싱 실패: {exc}") from exc
        if not isinstance(payload, dict):
            raise NaverCommerceError(f"{url} 응답이 dict 가 아니다: {type(payload).__name__}")
        return payload

    @staticmethod
    def _body_text(response: Any) -> str:
        """오류 응답 본문을 문자열로 뽑는다(없으면 빈 문자열)."""
        try:
            return str(getattr(response, "text", "") or "")
        except Exception as exc:  # noqa: BLE001 - 진단 문자열 추출 실패가 오류 보고를 막지 않게
            logger.warning("[NAVER] 오류 본문 추출 실패(무시): %s", exc, exc_info=True)
            return ""


__all__ = [
    "BASE_URL",
    "KST",
    "MAX_WINDOW",
    "DETAIL_BATCH_SIZE",
    "NaverCommerceClient",
    "NaverCommerceError",
    "NaverCommerceConfigError",
    "NaverCommerceAuthError",
    "NaverCommerceHTTPError",
    "MemoryTokenCache",
    "RedisTokenCache",
    "default_token_cache",
    "build_signature",
    "iter_time_windows",
]

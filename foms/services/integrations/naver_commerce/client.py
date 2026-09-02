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
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterator, Optional, Protocol, Sequence

import bcrypt

from foms.services.integrations.naver_commerce.settle_enums import (
    PERIOD_TYPES,
    SETTLE_DECISION_TYPES,
    SETTLE_TYPES,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.commerce.naver.com/external"
KST = timezone(timedelta(hours=9))

#: 변경분 조회 구간 상한. API 제약은 24시간이지만 경계에서 400을 맞지 않도록 1분 여유를 둔다
#: (2026-08-13 실호출은 23h59m 구간으로 성공했다).
MAX_WINDOW = timedelta(hours=23, minutes=59)

#: 상세 조회 1회 배치 크기. 네이버 문서 상한(300)보다 보수적으로 잡아 타임아웃 위험을 줄인다.
DETAIL_BATCH_SIZE = 100

#: 변경분 조회 1회 응답 상한. 문서(2026-09-01)상 기본·상한 모두 300 이고, 300 을 넘겨 보내도
#: 300 으로 캡된다. 명시해서 보내는 이유는 기본값이 바뀌어도 우리 페이징 계산이 안 흔들리게.
LAST_CHANGED_LIMIT = 300

#: 한 시간창에서 이어받기(more)를 돌 최대 쪽수. 300 * 50 = 15,000건/창 — 하루치로 넉넉하다.
#: 상한이 필요한 이유는 서버가 진척 없는 ``more`` 를 계속 돌려줄 때 무한 루프가 되지 않게.
LAST_CHANGED_MAX_PAGES = 50

#: 만료 이 시간 전이면 토큰을 새로 받는다(경계에서 401 맞지 않게).
TOKEN_REFRESH_MARGIN_SECONDS = 300

#: 재시도 대상 HTTP 상태. 429=rate limit, 5xx=서버측 일시 오류.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

#: 커머스API 호출 한도 응답 헤더(2026-08-31 조사). 게이트웨이가 매 응답에 실어 준다.
#: 한도는 **앱당·API당 초당 호출수**(Token Bucket)이고, 자사 스토어 애플리케이션은 전 API
#: 2 RPS 고정이다. 넘으면 429 로 **처리되지 않고** 실패한다.
#:
#: 이 헤더를 로그로 남기는 이유: 일괄 발송처리처럼 호출이 연달아 나가는 경로에서 "한도에
#: 얼마나 붙어 있었나"를 사후에 알 창이 여기밖에 없다. 429 를 맞고 나서야 아는 것과
#: 여유가 줄어드는 것을 미리 보는 것은 다르다.
RATE_LIMIT_REPLENISH_HEADER = "GNCP-GW-RateLimit-Replenish-Rate"
RATE_LIMIT_REMAINING_HEADER = "GNCP-GW-RateLimit-Remaining"
RATE_LIMIT_BURST_HEADER = "GNCP-GW-RateLimit-Burst-Capacity"

#: 남은 호출이 이 값 이하로 떨어지면 경고로 올린다(0 = 다음 호출이 429).
RATE_LIMIT_WARN_REMAINING = 1

#: 시간당 호출 할당(Quota) 응답 헤더. 자사 스토어 앱은 원칙적으로 Quota 미적용이지만,
#: 토큰 발급 규격을 어기면 **벌칙성 제한**이 걸리면서 이 헤더와 429 ``GW.QUOTA_LIMIT`` 가
#: 같이 온다(커머스API Discussions #3709/#3751 실증, 2026-09-02 조사).
#: 정산 순회처럼 호출이 길게 이어지는 경로는 이 헤더가 보이면 그 자리에서 멈춰야 한다 —
#: 벌칙 구간을 끝까지 태우면 다음 정상 주기까지 통째로 막힌다.
QUOTA_LIMIT_HEADER = "gncp-gw-quota-limit"

#: 정산 조회 페이지 크기 상한(문서 5종 공통: "페이지 크기(1000 이하)").
SETTLE_MAX_PAGE_SIZE = 1000

#: 건별 정산·수수료 상세 조회의 기본 기간 기준 — 정산 예정일.
DEFAULT_SETTLE_PERIOD_TYPE = "SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE"

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


def _header_text(response: Any, name: str) -> Optional[str]:
    """응답 헤더 하나를 문자열로 읽는다 — 없으면 ``None``.

    대소문자를 가리지 않는다. ``requests`` 의 헤더는 대소문자 무시 매핑이지만 주입 전송
    (테스트·다른 구현)은 보통 그냥 dict 라, 정확한 철자에만 걸리면 이 조회가 조용히
    빈 값이 된다.

    Args:
        response: 전송 계층 응답 객체(``headers`` 속성이 없으면 ``None``).
        name: 헤더 이름.

    Returns:
        헤더 값 문자열(앞뒤 공백 제거) 또는 ``None``.
    """
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = None
    getter = getattr(headers, "get", None)
    if callable(getter):
        value = getter(name)
    if value is None:
        lowered = name.lower()
        items = getattr(headers, "items", None)
        if callable(items):
            for key, candidate in items():
                if str(key).lower() == lowered:
                    value = candidate
                    break
    if value is None:
        return None
    return str(value).strip()


def _header_int(response: Any, name: str) -> Optional[int]:
    """응답 헤더 하나를 정수로 읽는다 — 없거나 숫자가 아니면 ``None``.

    Args:
        response: 전송 계층 응답 객체.
        name: 헤더 이름.

    Returns:
        정수 값 또는 ``None``.
    """
    value = _header_text(response, name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
        #: 마지막 응답의 시간당 할당 헤더(``gncp-gw-quota-limit``). **관측 전용**이다 —
        #: 값이 있으면 벌칙성 제한이 걸린 것이라 순회 호출자(정산 동기화)가 그 자리에서
        #: 멈추고 워터마크를 전진시키지 않는다. 헤더가 없는 응답이면 ``None`` 으로 돌아간다.
        self.last_quota_limit_header: Optional[str] = None

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

        구간이 API 상한을 넘으면 :func:`iter_time_windows` 로 잘라 순회하고, 한 창의
        응답이 상한(300건)을 넘어 ``data.more`` 가 오면 그 창 안에서 **이어받는다**.

        이어받기를 하지 않으면 300건을 넘는 창에서 나머지가 **조용히 사라진다** — 5분 주기
        정상 스윕에서는 드물지만 하루 창을 훑는 백필에서는 확실히 걸린다. 문서(2026-09-01)
        규정: ``more.moreFrom`` 을 다음 요청의 시작 일시로, ``more.moreSequence`` 를 같은
        일시 안의 구분자로 보낸다.

        Args:
            start: 구간 시작(naive면 KST로 간주).
            end: 구간 끝.

        Returns:
            ``lastChangeStatuses`` 항목 리스트(원본 dict). 각 항목에 ``productOrderId`` 가 있다.
        """
        collected: list[dict] = []
        for window_start, window_end in iter_time_windows(start, end):
            collected.extend(self._changed_window(window_start, window_end))
        return collected

    def _changed_window(self, window_start: datetime, window_end: datetime) -> list[dict]:
        """한 시간창을 ``more`` 이어받기까지 포함해 끝까지 읽는다.

        Args:
            window_start: 창 시작.
            window_end: 창 끝(이어받는 동안 고정된다 — 끝을 옮기면 범위가 새로 열린다).

        Returns:
            그 창의 변경 이벤트 전부(쪽수 상한에 걸리면 거기까지 + 경고 로그).
        """
        rows: list[dict] = []
        params: dict[str, Any] = {
            "lastChangedFrom": _format_ts(window_start),
            "lastChangedTo": _format_ts(window_end),
            "limitCount": LAST_CHANGED_LIMIT,
        }
        for page in range(1, LAST_CHANGED_MAX_PAGES + 1):
            payload = self._request(
                "GET", "/v1/pay-order/seller/product-orders/last-changed-statuses",
                params=params,
            )
            data = payload.get("data") or {}
            chunk = data.get("lastChangeStatuses") or []
            rows.extend(chunk)
            logger.info("[NAVER] 변경분 %s ~ %s (%d쪽): %d건",
                        _format_ts(window_start), _format_ts(window_end), page, len(chunk))
            more = data.get("more") or {}
            more_from = (more or {}).get("moreFrom")
            if not more_from:
                break
            if not chunk:
                # 진척 없는 이어받기 — 같은 요청을 무한히 반복하지 않는다.
                logger.warning("[NAVER] more 가 왔는데 항목이 0건이라 이어받기를 멈춘다(%s)", more_from)
                break
            params = dict(params)
            params["lastChangedFrom"] = str(more_from)
            more_sequence = (more or {}).get("moreSequence")
            if more_sequence is not None:
                params["moreSequence"] = str(more_sequence)
            else:
                params.pop("moreSequence", None)
        else:
            # for-else: 상한까지 돌고도 more 가 남았다. 잘렸다는 사실을 조용히 넘기지 않는다.
            logger.warning("[NAVER] 변경분 이어받기 쪽수 상한(%d) 도달 — %s ~ %s 구간 일부만 읽었다",
                           LAST_CHANGED_MAX_PAGES, _format_ts(window_start), _format_ts(window_end))
        return rows

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

    def request_cancel_product_order(self, product_order_id: str, *, reason: str,
                                     detail: Optional[str] = None,
                                     quantity: Optional[int] = None) -> dict:
        """판매자 직접취소 — 상품주문 **1건**을 취소 요청한다.

        발주확인·발송처리와 달리 배치가 없다(문서 "취소 요청": 1건의 상품 주문을 취소
        요청합니다). 집 단위 처리는 호출자가 돌면서 한다.

        Args:
            product_order_id: 취소할 ``productOrderId``.
            reason: 클레임 요청 사유 코드(``SOLD_OUT`` 등 — 목록은
                :data:`fulfillment.CANCEL_REASONS`).
            detail: 취소 상세 사유(500자 제한). 없으면 보내지 않는다.
            quantity: 취소 수량. 없으면 전체 수량 취소다(네이버 기본값).

        Returns:
            응답 payload(원본). 건별 성공/실패는 ``data.successProductOrderIds`` 와
            ``data.failProductOrderInfos`` 로 온다.

        Raises:
            ValueError: 상품주문번호나 사유가 비었을 때(빈 요청으로 API 를 때리지 않는다).
        """
        pid = str(product_order_id or "").strip()
        if not pid:
            raise ValueError("취소할 상품주문번호가 없습니다.")
        if not str(reason or "").strip():
            raise ValueError("취소 사유가 없습니다.")
        body: dict[str, Any] = {"cancelReason": str(reason).strip()}
        if detail:
            body["cancelDetailedReason"] = str(detail)[:500]
        if quantity is not None:
            body["cancelQuantity"] = int(quantity)
        return self._request(
            "POST", f"/v1/pay-order/seller/product-orders/{pid}/claim/cancel/request",
            json_body=body,
            headers={"Content-Type": "application/json"},
            # **불가역 클레임 호출은 재시도하지 않는다**(2026-09-02). 커머스API 문서가
            # 재호출 전 상태 재확인을 요구하는데 우리는 다시 읽지 않는다 — 맹목 재전송은
            # 중복 클레임이고, 타임아웃은 "안 나갔다"가 아니다.
            retry=False,
        )

    def approve_cancel_product_order(self, product_order_id: str) -> dict:
        """판매자 취소 **승인** — 구매자가 낸 취소 요청을 승인한다 (T9-G1).

        **환불이 확정된다. 되돌리는 엔드포인트가 없다.**

        **규격 출처**: 커머스API센터 공개 문서(2026-09-01 원문 확인) —
        ``apicenter.commerce.naver.com/llms/`` 의
        ``post-v1-pay-order-seller-product-orders-productOrderId-claim-cancel-approve.md``
        와 ``wiki-주문-주문-상태-변경-흐름도.md``. 로그인·JS 없이 열리는 갈래다.

        **body 를 보내지 않는다.** 문서의 요청 파라미터 표는 Path 의 ``productOrderId``
        하나뿐이고 요청 본문 절이 아예 없다("요청은 path의 productOrderId만으로 동작하며
        별도 본문이 필요 없고"). :meth:`approve_return_product_order` 와 같은 모양이다.
        2026-08-27 원장의 ``approvalData`` 근거는 폐기됐다 — 없는 필드를 지어내
        불가역 API 에 보내지 않는다.

        **출발 상태**: 흐름도 분기 C 가 ``CANCEL_REQUEST``(발주확인 후 취소요청)에서
        ``approveCancelApplication`` → 환불처리 → ``CANCEL_DONE`` 을 적고, 분기 B 가
        환불처리 불가로 ``CANCELING`` 에 머문 건도 같은 호출로 재판정한다고 적는다.
        그 밖의 상태는 400 이다 — 상태를 먼저 읽고 건다.

        **취소 거부 전용 endpoint 는 없다 — 그러나 거부 경로 자체는 있다**(2026-09-02
        정정). 옛 도스트링은 "취소 철회는 구매자만 한다"고 적었는데 **사실이 아니다.**
        공식 FAQ 원문(Discussion #2823, author ``commerce-api-naver``):

            취소 요청 거부는 단독으로 진행할 수 없으며 요청된 주문건(상품주문번호)을
            **발송 처리함으로서 취소 요청을 거부하는 방법만 가능**합니다.

        같은 취지가 #923 에도 있다 — "발송 처리 API 로 호출하게 될 경우 구매자 취소 요청
        거부 + 발송 처리가 동시에 진행됩니다". #1321 이 "발송 처리(**취소 철회**)"를 한
        묶음으로 적는 이유가 이것이다.

        **우리는 그 경로를 열지 않는다.** 물건이 이미 나간 건에만 성립하는데,
        :func:`fulfillment._claim_guard` 가 ``CANCEL_REQUEST`` 집의 발송처리를 막기
        때문이다(불가역 오발송 차단이 우선). 즉 **없어서 안 하는 게 아니라 막아서 안
        한다** — 담당자는 판매자센터로 간다. 열려면 그 가드부터 설계해야 한다.

        **이미 승인된 건·취소 요청이 없는 건은 처리되지 않는다** — 예외가 아니라
        ``data.failProductOrderInfos`` 로 온다. 응답이 접수·반품 승인과 **동형**이라
        호출자가 ``_split_result`` 를 그대로 쓴다.

        Args:
            product_order_id: 승인할 ``productOrderId``.

        Returns:
            응답 payload(원본). 건별 성공/실패는 ``data.successProductOrderIds`` 와
            ``data.failProductOrderInfos`` 로 온다.

        Raises:
            ValueError: 상품주문번호가 비었을 때(빈 요청으로 불가역 API 를 때리지 않는다).
        """
        pid = str(product_order_id or "").strip()
        if not pid:
            raise ValueError("승인할 상품주문번호가 없습니다.")
        return self._request(
            "POST", f"/v1/pay-order/seller/product-orders/{pid}/claim/cancel/approve",
            # **불가역 클레임 호출은 재시도하지 않는다**(2026-09-02). 커머스API 문서가
            # 재호출 전 상태 재확인을 요구하는데 우리는 다시 읽지 않는다 — 맹목 재전송은
            # 중복 클레임이고, 타임아웃은 "안 나갔다"가 아니다.
            retry=False,
        )

    def request_return_product_order(self, product_order_id: str, *, reason: str,
                                     collect_method: str,
                                     detail: Optional[str] = None,
                                     quantity: Optional[int] = None) -> dict:
        """판매자 반품 접수 — 상품주문 **1건**의 반품을 요청한다 (T8-S1).

        취소와 **같은 모양**이다: 배치가 없어 집 단위 처리는 호출자가 돌면서 하고,
        응답도 ``successProductOrderIds``/``failProductOrderInfos`` 로 온다.

        **취소와 다른 점 둘.** ① 사유 코드 목록이 취소와 다르다
        (:data:`fulfillment.RETURN_REASONS`). ② ``collectDeliveryMethod`` 가 있다 —
        실물 회수가 있어서가 아니다(시공 전 발송이라 고객 집에 간 물건 자체가 없고,
        반품은 주문(금액)만 움직인다). ``RETURN_INDIVIDUAL`` 만 쓰는 이유는 오발송을
        막기 위해서다: 다른 값을 보내면 **API 값이 무시되고 상품에 설정된 택배사가
        부르지도 않은 자동 수거를 고객 집으로 보낸다** — 되돌릴 수 없다. 그래서
        호출자가 화이트리스트로 미리 막는다.

        Args:
            product_order_id: 반품할 ``productOrderId``.
            reason: 반품 사유 코드(목록은 :data:`fulfillment.RETURN_REASONS`).
            collect_method: 회수 방법 코드. 실질적으로 ``RETURN_INDIVIDUAL`` 하나다.
            detail: 반품 상세 사유(500자 제한). 없으면 보내지 않는다.
            quantity: 반품 수량. 없으면 전체 수량이다(네이버 기본값).

        Returns:
            응답 payload(원본). 건별 성공/실패는 ``data.successProductOrderIds`` 와
            ``data.failProductOrderInfos`` 로 온다.

        Raises:
            ValueError: 상품주문번호·사유·회수방법 중 하나라도 비었을 때
                (빈 요청으로 불가역 API 를 때리지 않는다).
        """
        pid = str(product_order_id or "").strip()
        if not pid:
            raise ValueError("반품할 상품주문번호가 없습니다.")
        if not str(reason or "").strip():
            raise ValueError("반품 사유가 없습니다.")
        if not str(collect_method or "").strip():
            # 비워 보내면 네이버가 상품 기본 택배사로 수거를 보낼 수 있다 — 막는다.
            raise ValueError("회수 방법이 없습니다.")
        body: dict[str, Any] = {
            "returnReason": str(reason).strip(),
            "collectDeliveryMethod": str(collect_method).strip(),
        }
        if detail:
            body["returnDetailedReason"] = str(detail)[:500]
        if quantity is not None:
            body["returnQuantity"] = int(quantity)
        return self._request(
            "POST", f"/v1/pay-order/seller/product-orders/{pid}/claim/return/request",
            json_body=body,
            headers={"Content-Type": "application/json"},
            # **불가역 클레임 호출은 재시도하지 않는다**(2026-09-02). 커머스API 문서가
            # 재호출 전 상태 재확인을 요구하는데 우리는 다시 읽지 않는다 — 맹목 재전송은
            # 중복 클레임이고, 타임아웃은 "안 나갔다"가 아니다.
            retry=False,
        )

    def approve_return_product_order(self, product_order_id: str) -> dict:
        """판매자 반품 **승인** — 상품주문 1건의 반품 요청을 승인한다 (T8-S2).

        **환불이 확정된다. 되돌리는 엔드포인트가 없다.**

        **body 를 보내지 않는다.** 공식 문서(커머스API v2.86.0, 2026-08-31 원문 확인)의
        Request 항목은 Path 파라미터 ``productOrderId`` 하나뿐이고, curl 예시에도
        ``Content-Type`` 도 ``-d`` 도 없다. 2026-08-27 원장이 "빈 body 는 400 이고
        ``approvalData`` 를 넣어야 200"이라고 적었으나 그 출처(#3693)는 **취소** 승인
        문서였고 해당 문장이 없다 — 근거 폐기. 없는 필드를 지어내 보내지 않는다.

        응답은 접수·취소와 **동형**이라 호출자가 ``_split_result`` 를 그대로 쓴다.

        Args:
            product_order_id: 승인할 ``productOrderId``.

        Returns:
            응답 payload(원본). 건별 성공/실패는 ``data.successProductOrderIds`` 와
            ``data.failProductOrderInfos`` 로 온다.

        Raises:
            ValueError: 상품주문번호가 비었을 때(빈 요청으로 불가역 API 를 때리지 않는다).
        """
        pid = str(product_order_id or "").strip()
        if not pid:
            raise ValueError("승인할 상품주문번호가 없습니다.")
        return self._request(
            "POST", f"/v1/pay-order/seller/product-orders/{pid}/claim/return/approve",
            # **불가역 클레임 호출은 재시도하지 않는다**(2026-09-02). 커머스API 문서가
            # 재호출 전 상태 재확인을 요구하는데 우리는 다시 읽지 않는다 — 맹목 재전송은
            # 중복 클레임이고, 타임아웃은 "안 나갔다"가 아니다.
            retry=False,
        )

    def reject_return_product_order(self, product_order_id: str, *, reason: str) -> dict:
        """판매자 반품 **거부(철회)** — 고객이 낸 반품 요청을 되돌려보낸다 (T8-S3).

        **규격 출처**: 커머스API센터 공개 문서(2026-09-01 원문 확인) —
        ``apicenter.commerce.naver.com/llms/`` 의
        ``post-v1-pay-order-seller-product-orders-productOrderId-claim-return-reject.md``.
        로그인·JS 없이 열리는 ``llms.txt`` 갈래다. 화면이 막혔다고 규격을 지어내던
        자리를 이 문서가 닫았다(``approvalData`` 사고와 같은 자리).

        **body 는 ``rejectReturnReason`` 한 필드다**(string, **필수**). 문서의 요청 본문
        표에 그 한 줄만 있고 curl 예시에 ``Content-Type: application/json`` 과 ``-d`` 가
        있다. 승인(:meth:`approve_return_product_order`)이 "본문이 필요 없고"인 것과 갈린다.

        **문장은 구매자에게 간다** — 문서가 "구매자 알림과 사후 분쟁 대응의 근거"라고
        적는다. 그래서 호출자가 보낸 원문을 상태와 감사 로그 양쪽에 남긴다.

        **되돌리는 엔드포인트는 없다.** 거부 뒤 클레임 상태는 ``RETURN_REJECT`` 가 되고
        상품주문상태는 클레임 직전(``DELIVERING``/``DELIVERED``)으로 복귀한다. 환불은
        발생하지 않으며 **구매자가 다시 반품을 신청할 수 있다**(이력은 ``completedClaims``
        에 쌓인다).

        **보류 건·반품완료 건은 처리되지 않는다** — 예외가 아니라
        ``data.failProductOrderInfos`` 로 온다. 응답이 접수·승인과 **동형**이라 호출자가
        ``_split_result`` 를 그대로 쓴다.

        Args:
            product_order_id: 거부할 ``productOrderId``.
            reason: 구매자에게 **그대로 전달되는** 거부 사유 문장.

        Returns:
            응답 payload(원본). 건별 성공/실패는 ``data.successProductOrderIds`` 와
            ``data.failProductOrderInfos`` 로 온다.

        Raises:
            ValueError: 상품주문번호나 사유 문장이 비었을 때. 빈 요청으로 불가역 API 를
                때리지 않는다 — 문서도 **사유 누락을 400** 으로 적는다.
        """
        pid = str(product_order_id or "").strip()
        if not pid:
            raise ValueError("거부할 상품주문번호가 없습니다.")
        text = str(reason or "").strip()
        if not text:
            raise ValueError("거부 사유 문장이 없습니다.")
        return self._request(
            "POST", f"/v1/pay-order/seller/product-orders/{pid}/claim/return/reject",
            json_body={"rejectReturnReason": text},
            headers={"Content-Type": "application/json"},
            # **불가역 클레임 호출은 재시도하지 않는다**(2026-09-02). 커머스API 문서가
            # 재호출 전 상태 재확인을 요구하는데 우리는 다시 읽지 않는다 — 맹목 재전송은
            # 중복 클레임이고, 타임아웃은 "안 나갔다"가 아니다.
            retry=False,
        )

    # -- 정산(pay-settle) --------------------------------------------------- #
    #
    # 정산 5종은 **읽기 전용 GET** 이고 :meth:`_request` 를 그대로 쓴다. 새 토큰 경로를
    # 만들지 않는 이유: 토큰 발급 규격을 어긴 앱은 발급이 시간당 1회로 묶이고 그 벌칙이
    # 정산 API 429 로 번진다(커머스API Discussions #3751/#3709). 이미 규격을 지키는 이
    # 클라이언트에 얹는 것이 곧 대응책이다.
    #
    # 페이지 순회는 호출자(정산 동기화) 몫이다 — 한 쪽만 돌려주고 ``pagination`` 을 원본
    # 그대로 넘긴다. 응답 금액도 손대지 않는다(재계산 금지).

    def get_settle_daily(self, start_date: date, end_date: date, *, page: int = 1,
                         page_size: int = SETTLE_MAX_PAGE_SIZE) -> dict:
        """일별 정산 내역 한 쪽을 조회한다(``GET /v1/pay-settle/settle/daily``).

        네 파라미터(startDate·endDate·pageNumber·pageSize)가 모두 필수인 엔드포인트다.

        Args:
            start_date: 조회 시작일.
            end_date: 조회 종료일.
            page: 페이지 번호(1부터).
            page_size: 페이지 크기(1~1000).

        Returns:
            ``{"elements": [...], "pagination": {...}}`` 파싱 결과 원본.

        Raises:
            ValueError: 날짜 타입·페이지 범위가 규격을 벗어날 때.
        """
        params: dict[str, Any] = {
            "startDate": self._settle_date(start_date, "start_date"),
            "endDate": self._settle_date(end_date, "end_date"),
        }
        params.update(self._settle_page_params(page, page_size))
        return self._request("GET", "/v1/pay-settle/settle/daily", params=params)

    def get_settle_cases(self, search_date: date, *,
                         period_type: str = DEFAULT_SETTLE_PERIOD_TYPE,
                         settle_type: Optional[str] = None,
                         settle_decision_type: Optional[str] = None,
                         order_id: Optional[str] = None,
                         product_order_id: Optional[str] = None,
                         page: int = 1,
                         page_size: int = SETTLE_MAX_PAGE_SIZE) -> dict:
        """건별 정산 내역 한 쪽을 조회한다(``GET /v1/pay-settle/settle/case``).

        **기간 조회를 지원하지 않는다** — 하루(``searchDate``)씩 호출한다(Discussion #3709).
        ``settle_decision_type`` 은 ``period_type`` 이 결제일 기준일 때만 뜻이 있다.

        Args:
            search_date: 조회일(하루).
            period_type: 기간 기준 enum. ``None`` 이면 파라미터를 보내지 않는다.
            settle_type: 정산 구분 필터(선택).
            settle_decision_type: 결제일 구분 필터(선택).
            order_id: 주문 번호 필터(선택).
            product_order_id: 상품 주문 번호 필터(선택).
            page: 페이지 번호(1부터).
            page_size: 페이지 크기(1~1000).

        Returns:
            ``{"elements": [...], "pagination": {...}}`` 파싱 결과 원본.

        Raises:
            ValueError: 날짜 타입·페이지 범위·enum 값이 규격을 벗어날 때.
        """
        params = self._settle_case_params(
            search_date, period_type=period_type, settle_type=settle_type,
            settle_decision_type=settle_decision_type, order_id=order_id,
            product_order_id=product_order_id, page=page, page_size=page_size,
        )
        return self._request("GET", "/v1/pay-settle/settle/case", params=params)

    def get_settle_commission_details(self, search_date: date, *,
                                      period_type: str = DEFAULT_SETTLE_PERIOD_TYPE,
                                      settle_type: Optional[str] = None,
                                      settle_decision_type: Optional[str] = None,
                                      order_id: Optional[str] = None,
                                      product_order_id: Optional[str] = None,
                                      page: int = 1,
                                      page_size: int = SETTLE_MAX_PAGE_SIZE) -> dict:
        """수수료 상세 내역 한 쪽을 조회한다(``GET /v1/pay-settle/settle/commission-details``).

        파라미터는 건별 정산과 같다. 같은 상품 주문이 ``commissionType`` 별로 여러 줄로
        쪼개져 오므로 분개 키는 ``(productOrderId, commissionType)`` 조합이다.

        Args:
            search_date: 조회일(하루).
            period_type: 기간 기준 enum. ``None`` 이면 파라미터를 보내지 않는다.
            settle_type: 정산 구분 필터(선택).
            settle_decision_type: 결제일 구분 필터(선택).
            order_id: 주문 번호 필터(선택).
            product_order_id: 상품 주문 번호 필터(선택).
            page: 페이지 번호(1부터).
            page_size: 페이지 크기(1~1000).

        Returns:
            ``{"elements": [...], "pagination": {...}}`` 파싱 결과 원본.

        Raises:
            ValueError: 날짜 타입·페이지 범위·enum 값이 규격을 벗어날 때.
        """
        params = self._settle_case_params(
            search_date, period_type=period_type, settle_type=settle_type,
            settle_decision_type=settle_decision_type, order_id=order_id,
            product_order_id=product_order_id, page=page, page_size=page_size,
        )
        return self._request("GET", "/v1/pay-settle/settle/commission-details", params=params)

    def get_vat_daily(self, start_date: date, end_date: date, *, page: int = 1,
                      page_size: int = SETTLE_MAX_PAGE_SIZE) -> dict:
        """일별 부가세 내역 한 쪽을 조회한다(``GET /v1/pay-settle/vat/daily``).

        **전월 말일까지만 조회된다** — 당월 구간을 넣으면 400 이다. 구간 판단은 호출자
        (정산 동기화)가 하고 여기서는 받은 구간을 그대로 보낸다.

        Args:
            start_date: 조회 시작일.
            end_date: 조회 종료일.
            page: 페이지 번호(1부터).
            page_size: 페이지 크기(1~1000).

        Returns:
            ``{"elements": [...], "pagination": {...}}`` 파싱 결과 원본.

        Raises:
            ValueError: 날짜 타입·페이지 범위가 규격을 벗어날 때.
        """
        params: dict[str, Any] = {
            "startDate": self._settle_date(start_date, "start_date"),
            "endDate": self._settle_date(end_date, "end_date"),
        }
        params.update(self._settle_page_params(page, page_size))
        return self._request("GET", "/v1/pay-settle/vat/daily", params=params)

    def get_vat_cases(self, start_date: date, end_date: date, *, page: int = 1,
                      page_size: int = SETTLE_MAX_PAGE_SIZE) -> dict:
        """건별 부가세 내역 한 쪽을 조회한다(``GET /v1/pay-settle/vat/case``).

        일별 부가세와 같은 기간 제약(전월 말일까지)을 받는다.

        Args:
            start_date: 조회 시작일.
            end_date: 조회 종료일.
            page: 페이지 번호(1부터).
            page_size: 페이지 크기(1~1000).

        Returns:
            ``{"elements": [...], "pagination": {...}}`` 파싱 결과 원본.

        Raises:
            ValueError: 날짜 타입·페이지 범위가 규격을 벗어날 때.
        """
        params: dict[str, Any] = {
            "startDate": self._settle_date(start_date, "start_date"),
            "endDate": self._settle_date(end_date, "end_date"),
        }
        params.update(self._settle_page_params(page, page_size))
        return self._request("GET", "/v1/pay-settle/vat/case", params=params)

    def _settle_case_params(self, search_date: date, *, period_type: Optional[str],
                            settle_type: Optional[str], settle_decision_type: Optional[str],
                            order_id: Optional[str], product_order_id: Optional[str],
                            page: int, page_size: int) -> dict:
        """건별 정산·수수료 상세 공용 파라미터를 만든다 — ``None`` 은 **보내지 않는다**.

        빈 필터를 실어 보내면 400 이 나므로 값이 없는 파라미터는 키째로 뺀다.

        Args:
            search_date: 조회일.
            period_type: 기간 기준 enum(``None`` 이면 생략).
            settle_type: 정산 구분 enum(``None`` 이면 생략).
            settle_decision_type: 결제일 구분 enum(``None`` 이면 생략).
            order_id: 주문 번호(``None``·공백이면 생략).
            product_order_id: 상품 주문 번호(``None``·공백이면 생략).
            page: 페이지 번호.
            page_size: 페이지 크기.

        Returns:
            쿼리 파라미터 dict.
        """
        optional = {
            "periodType": self._settle_enum(period_type, PERIOD_TYPES, "period_type"),
            "settleType": self._settle_enum(settle_type, SETTLE_TYPES, "settle_type"),
            "settleDecisionType": self._settle_enum(
                settle_decision_type, SETTLE_DECISION_TYPES, "settle_decision_type"),
            "orderId": self._settle_text(order_id),
            "productOrderId": self._settle_text(product_order_id),
        }
        params: dict[str, Any] = {"searchDate": self._settle_date(search_date, "search_date")}
        params.update({key: value for key, value in optional.items() if value is not None})
        params.update(self._settle_page_params(page, page_size))
        return params

    @staticmethod
    def _settle_page_params(page: int, page_size: int) -> dict:
        """페이지 파라미터를 검증해 만든다(문서 규격: 번호 1 이상, 크기 1~1000).

        Args:
            page: 페이지 번호.
            page_size: 페이지 크기.

        Returns:
            ``{"pageNumber": ..., "pageSize": ...}``.

        Raises:
            ValueError: 규격 밖일 때 — 400 을 맞기 전에 여기서 멈춘다.
        """
        try:
            page_no = int(page)
            size = int(page_size)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"페이지 파라미터는 정수여야 합니다(page={page!r}, page_size={page_size!r})."
            ) from exc
        if page_no < 1:
            raise ValueError(f"페이지 번호는 1 이상이어야 합니다(받은 값: {page_no}).")
        if not 1 <= size <= SETTLE_MAX_PAGE_SIZE:
            raise ValueError(
                f"페이지 크기는 1~{SETTLE_MAX_PAGE_SIZE} 여야 합니다(받은 값: {size})."
            )
        return {"pageNumber": page_no, "pageSize": size}

    @staticmethod
    def _settle_enum(value: Optional[str], allowed: dict, field: str) -> Optional[str]:
        """enum 파라미터를 허용 집합으로 검증한다 — ``None``·공백이면 ``None``(생략).

        문서에 없는 값을 보내면 400 이다. 스냅샷에서 처음 본 코드를 그대로 요청에 싣지
        않도록, 보내는 값은 공식 범례(``settle_enums``)로만 받는다.

        Args:
            value: 요청에 실을 코드.
            allowed: 허용 코드 카탈로그(코드→라벨).
            field: 오류 문구에 쓸 파라미터 이름.

        Returns:
            검증된 코드 또는 ``None``.

        Raises:
            ValueError: 허용 집합 밖의 코드일 때.
        """
        if value is None:
            return None
        code = str(value).strip()
        if not code:
            return None
        if code not in allowed:
            raise ValueError(
                f"{field} 값이 규격 밖입니다: {code!r}. 허용값: {', '.join(sorted(allowed))}"
            )
        return code

    @staticmethod
    def _settle_date(value: date, field: str) -> str:
        """조회 날짜를 ``yyyy-MM-dd`` 문자열로 만든다(KST 날짜 그대로).

        Args:
            value: ``datetime.date``(``datetime`` 이면 날짜 부분만 쓴다).
            field: 오류 문구에 쓸 파라미터 이름.

        Returns:
            ISO 날짜 문자열.

        Raises:
            ValueError: date 가 아닐 때 — 문자열을 그대로 넘겨 조용히 400 을 맞지 않게.
        """
        if isinstance(value, datetime):
            value = value.date()
        if not isinstance(value, date):
            raise ValueError(
                f"{field} 는 datetime.date 여야 합니다(받은 값: {type(value).__name__})."
            )
        return value.isoformat()

    @staticmethod
    def _settle_text(value: Optional[str]) -> Optional[str]:
        """선택 문자열 파라미터를 정리한다 — 공백뿐이면 ``None``(빈 필터를 안 보낸다).

        Args:
            value: 원본 값.

        Returns:
            공백 제거 문자열 또는 ``None``.
        """
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    # -- HTTP ------------------------------------------------------------- #

    def _session(self) -> Any:
        """전송 객체를 준다(주입된 것이 있으면 그것, 없으면 requests 세션)."""
        if self._transport is None:
            import requests

            self._transport = requests.Session()
        return self._transport

    def _request(self, method: str, path: str, *, params: Optional[dict] = None,
                 data: Optional[dict] = None, json_body: Optional[dict] = None,
                 headers: Optional[dict] = None, authenticated: bool = True,
                 retry: bool = True) -> dict:
        """재시도·토큰 갱신을 포함한 단일 API 호출. 파싱된 JSON dict를 돌려준다.

        429/5xx·네트워크 오류는 지수 백오프로 재시도하고, 401은 토큰을 강제 재발급해
        **한 번만** 다시 시도한다(무한 재발급 루프 방지).

        ``retry=False`` 는 **불가역 클레임 호출** 전용이다(2026-09-02). 커머스API
        문서가 재호출 전에 상태 재확인을 요구한다 — 취소 요청 문서 원문:
        "500은 일시 장애로 보고 traceId 기반 재시도와 **동일 사유 재호출 시 중복
        클레임 방지를 위해 상품 주문 상세 조회로 현재 클레임 상태를 먼저 확인**합니다."
        그런데 우리는 상태를 다시 읽지 않으므로, 맹목 재전송은 **중복 클레임**을 만든다.
        더 나쁜 갈래는 타임아웃이다 — 네이버가 이미 처리했는데 응답만 못 받은 경우다.
        401 토큰 재발급 1회는 재시도가 아니라 **같은 호출의 인증 복구**라 그대로 둔다
        (요청이 서버에 닿지 않았다).

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
                # 불가역 호출은 여기서 멈춘다 — 타임아웃은 "안 나갔다"가 아니다.
                if not retry or attempt >= self._max_retries:
                    raise NaverCommerceError(f"{method} {url} 네트워크 실패: {exc}") from exc
                attempt += 1
                self._backoff(attempt, reason=str(exc))
                continue

            status = int(getattr(response, "status_code", 0))
            # 관측 전용 1줄 — 재시도·백오프 동작은 바뀌지 않는다(성공·오류 응답 공통).
            self.last_quota_limit_header = _header_text(response, QUOTA_LIMIT_HEADER)
            self._log_rate_limit(response, method=method, path=path, status=status)
            if 200 <= status < 300:
                return self._parse_json(response, url)

            body = self._body_text(response)
            if status == 401 and authenticated and not token_retried:
                token_retried = True
                logger.info("[NAVER] 401 — 토큰 강제 재발급 후 1회 재시도")
                self.get_access_token(force_refresh=True)
                continue
            if retry and status in RETRYABLE_STATUS and attempt < self._max_retries:
                attempt += 1
                self._backoff(attempt, reason=f"HTTP {status}")
                continue
            if status == 401:
                raise NaverCommerceAuthError(f"{method} {url} 인증 실패(401): {body[:300]}")
            raise NaverCommerceHTTPError(status, body, url=url)

    def _log_rate_limit(self, response: Any, *, method: str, path: str,
                        status: int) -> None:
        """호출 한도 응답 헤더를 로그에 남긴다 — **관측 전용**(호출 동작은 바뀌지 않는다).

        헤더가 없으면 아무것도 남기지 않는다. 커머스API 밖(토큰 발급 등)이나 테스트용
        전송처럼 헤더를 안 싣는 응답에서 매 호출 잡음을 만들지 않기 위해서다.

        Args:
            response: 전송 계층 응답 객체.
            method: HTTP 메서드(로그 식별용).
            path: 호출 경로(로그 식별용).
            status: 응답 상태 코드 — 429 는 남은 값과 무관하게 경고로 남긴다.

        Returns:
            None. 헤더 추출이 실패해도 예외를 올리지 않는다(진단 로그가 본 호출을 막으면
            안 된다 — 실패 사실 자체는 debug 로 남긴다).
        """
        try:
            remaining = _header_int(response, RATE_LIMIT_REMAINING_HEADER)
            replenish = _header_int(response, RATE_LIMIT_REPLENISH_HEADER)
            burst = _header_int(response, RATE_LIMIT_BURST_HEADER)
        except Exception as exc:  # noqa: BLE001 - 진단 실패가 API 호출을 깨지 않게
            logger.debug("[NAVER] 한도 헤더 추출 실패(무시): %s", exc, exc_info=True)
            return
        if remaining is None and replenish is None and burst is None:
            return
        line = ("[NAVER] 호출 한도 %s %s status=%d 남음=%s 초당배정=%s 버스트=%s")
        args = (method, path, status,
                "?" if remaining is None else remaining,
                "?" if replenish is None else replenish,
                "?" if burst is None else burst)
        if status == 429 or (remaining is not None and remaining <= RATE_LIMIT_WARN_REMAINING):
            logger.warning(line, *args)
        else:
            logger.debug(line, *args)

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
    "QUOTA_LIMIT_HEADER",
    "SETTLE_MAX_PAGE_SIZE",
    "DEFAULT_SETTLE_PERIOD_TYPE",
    "DETAIL_BATCH_SIZE",
    "LAST_CHANGED_LIMIT",
    "LAST_CHANGED_MAX_PAGES",
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

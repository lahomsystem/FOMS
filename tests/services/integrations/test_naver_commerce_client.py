"""NAVER-INGEST-01 T3: 네이버 커머스API 클라이언트 계약 테스트.

네트워크를 타지 않는다 — 전송(transport)과 대기(sleep)를 주입해 서명·토큰 캐시·구간 분할·
배치·재시도 경로를 결정적으로 고정한다. 실 API 호출 검증은 T1(WORKER static IP) 몫이다.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta

import bcrypt
import pytest

from foms.services.integrations.naver_commerce.client import (
    DETAIL_BATCH_SIZE,
    KST,
    LAST_CHANGED_MAX_PAGES,
    MemoryTokenCache,
    NaverCommerceAuthError,
    NaverCommerceClient,
    NaverCommerceConfigError,
    NaverCommerceError,
    NaverCommerceHTTPError,
    build_signature,
    iter_time_windows,
)

CLIENT_ID = "test-client-id"
SECRET = bcrypt.gensalt(rounds=4).decode("utf-8")  # 실 시크릿과 같은 bcrypt salt 형식
TOKEN_PATH = "/v1/oauth2/token"
CHANGED_PATH = "/v1/pay-order/seller/product-orders/last-changed-statuses"
QUERY_PATH = "/v1/pay-order/seller/product-orders/query"


class FakeResponse:
    """requests.Response 최소 계약(status_code / json() / text)만 흉내낸다."""

    def __init__(self, status_code: int, payload=None, text: str = "", raise_on_json: bool = False,
                 headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload
        self.text = text or ""
        self._raise_on_json = raise_on_json
        # 실 게이트웨이는 매 응답에 호출 한도 헤더를 싣는다. 기본은 빈 dict —
        # 헤더 없는 응답에서도 클라이언트가 죽지 않는 것이 계약이다.
        self.headers = dict(headers or {})

    def json(self):
        if self._raise_on_json:
            raise ValueError("not json")
        return self._payload


class FakeTransport:
    """경로별 응답 큐. 큐가 비면 마지막 응답을 반복한다."""

    def __init__(self, routes: dict[str, list[FakeResponse]]):
        self._routes = {path: list(responses) for path, responses in routes.items()}
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        for path, queue in self._routes.items():
            if url.endswith(path):
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f"테스트에 없는 경로 호출: {url}")

    def calls_to(self, path: str) -> list[tuple[str, str, dict]]:
        return [call for call in self.calls if call[1].endswith(path)]


def token_response(expires_in: int = 10799) -> FakeResponse:
    return FakeResponse(200, {"access_token": "tok-abc", "expires_in": expires_in})


def make_client(routes: dict[str, list[FakeResponse]], **kwargs) -> tuple[NaverCommerceClient, FakeTransport, list]:
    """전송·캐시·sleep 을 모두 주입한 클라이언트를 만든다(네트워크·실대기 없음)."""
    transport = FakeTransport(routes)
    slept: list[float] = []
    client = NaverCommerceClient(
        CLIENT_ID, SECRET,
        transport=transport,
        token_cache=kwargs.pop("token_cache", MemoryTokenCache()),
        sleep=slept.append,
        **kwargs,
    )
    return client, transport, slept


# --------------------------------------------------------------------------- #
# 서명
# --------------------------------------------------------------------------- #

def test_signature_is_base64_bcrypt_with_secret_as_salt():
    """서명은 base64(bcrypt(f"{id}_{ts}", salt=client_secret)) 여야 한다."""
    timestamp_ms = 1_700_000_000_000
    sign = build_signature(CLIENT_ID, SECRET, timestamp_ms)
    hashed = base64.b64decode(sign)
    assert bcrypt.checkpw(f"{CLIENT_ID}_{timestamp_ms}".encode("utf-8"), hashed)


def test_signature_changes_with_timestamp():
    """같은 자격증명이라도 timestamp 가 다르면 서명이 달라야 한다(리플레이 방지)."""
    assert build_signature(CLIENT_ID, SECRET, 1) != build_signature(CLIENT_ID, SECRET, 2)


def test_signature_rejects_non_bcrypt_secret():
    """PowerShell 큰따옴표로 깨진 시크릿($2a 치환)은 조용히 실패하지 않고 즉시 막는다."""
    with pytest.raises(NaverCommerceConfigError) as exc:
        build_signature(CLIENT_ID, "plain-secret", 1)
    assert "bcrypt salt" in str(exc.value)


def test_signature_rejects_missing_credentials():
    """자격증명 미설정은 재시도 대상이 아닌 설정 오류로 구분된다."""
    with pytest.raises(NaverCommerceConfigError):
        build_signature("", "", 1)


# --------------------------------------------------------------------------- #
# 토큰 캐시
# --------------------------------------------------------------------------- #

def test_token_is_cached_across_calls():
    """캐시 히트면 토큰을 다시 발급하지 않는다(3시간짜리 토큰을 매번 받지 않는다)."""
    client, transport, _ = make_client({TOKEN_PATH: [token_response()]})
    assert client.get_access_token() == "tok-abc"
    assert client.get_access_token() == "tok-abc"
    assert len(transport.calls_to(TOKEN_PATH)) == 1


def test_force_refresh_reissues_token():
    """force_refresh 는 캐시를 무시하고 재발급한다(401 복구 경로가 이걸 쓴다)."""
    client, transport, _ = make_client({TOKEN_PATH: [token_response()]})
    client.get_access_token()
    client.get_access_token(force_refresh=True)
    assert len(transport.calls_to(TOKEN_PATH)) == 2


def test_token_cache_ttl_shrinks_by_refresh_margin():
    """캐시 TTL 은 만료 5분 전으로 당겨져야 한다(경계에서 401 맞지 않게)."""
    stored: dict[str, int] = {}

    class RecordingCache(MemoryTokenCache):
        def set(self, key, value, ttl_seconds):
            stored[key] = ttl_seconds
            super().set(key, value, ttl_seconds)

    client, _, _ = make_client({TOKEN_PATH: [token_response(expires_in=10799)]},
                               token_cache=RecordingCache())
    client.get_access_token()
    assert list(stored.values()) == [10799 - 300]


def test_expired_memory_cache_entry_is_reissued():
    """만료된 캐시 항목은 미스로 취급되어 재발급된다."""
    cache = MemoryTokenCache()
    client, transport, _ = make_client({TOKEN_PATH: [token_response(expires_in=61)]},
                                       token_cache=cache)
    client.get_access_token()
    # 저장된 항목을 과거로 만료시킨다(시간 흐름 대신 상태를 직접 조작).
    key = next(iter(cache._store))
    value, _ = cache._store[key]
    cache._store[key] = (value, 0.0)
    client.get_access_token()
    assert len(transport.calls_to(TOKEN_PATH)) == 2


def test_token_response_without_access_token_raises_auth_error():
    """발급 응답에 토큰이 없으면 인증 오류로 구분한다(HTTP 200 이어도)."""
    client, _, _ = make_client({TOKEN_PATH: [FakeResponse(200, {"expires_in": 10})]})
    with pytest.raises(NaverCommerceAuthError):
        client.get_access_token()


# --------------------------------------------------------------------------- #
# 구간 분할 (24h 상한)
# --------------------------------------------------------------------------- #

def test_windows_split_long_range_and_end_exactly_at_end():
    """72시간 구간은 24시간 조각 3개가 되고 마지막 조각 끝은 정확히 end 다."""
    start = datetime(2026, 8, 10, 0, 0, tzinfo=KST)
    end = start + timedelta(hours=72)
    windows = list(iter_time_windows(start, end, max_window=timedelta(hours=24)))
    assert len(windows) == 3
    assert windows[0][0] == start
    assert windows[-1][1] == end
    # 조각이 끊김 없이 이어져야 한다(구멍 = 주문 유실).
    assert all(windows[i][1] == windows[i + 1][0] for i in range(len(windows) - 1))


def test_window_shorter_than_limit_stays_single():
    """상한보다 짧은 구간은 나누지 않는다."""
    start = datetime(2026, 8, 10, 0, 0, tzinfo=KST)
    windows = list(iter_time_windows(start, start + timedelta(hours=3)))
    assert windows == [(start, start + timedelta(hours=3))]


def test_empty_or_reversed_range_yields_nothing():
    """start >= end 면 호출하지 않는다(워터마크가 미래일 때 무의미한 호출 방지)."""
    now = datetime(2026, 8, 10, 0, 0, tzinfo=KST)
    assert list(iter_time_windows(now, now)) == []
    assert list(iter_time_windows(now, now - timedelta(hours=1))) == []


def test_last_changed_statuses_iterates_windows_and_concatenates():
    """구간이 상한을 넘으면 여러 번 호출하고 결과를 이어 붙인다."""
    routes = {
        TOKEN_PATH: [token_response()],
        CHANGED_PATH: [
            FakeResponse(200, {"data": {"lastChangeStatuses": [{"productOrderId": "A"}]}}),
            FakeResponse(200, {"data": {"lastChangeStatuses": [{"productOrderId": "B"}]}}),
        ],
    }
    client, transport, _ = make_client(routes)
    start = datetime(2026, 8, 10, 0, 0, tzinfo=KST)
    result = client.get_last_changed_statuses(start, start + timedelta(hours=30))
    assert [row["productOrderId"] for row in result] == ["A", "B"]
    assert len(transport.calls_to(CHANGED_PATH)) == 2


def test_last_changed_sends_millisecond_iso_timestamps():
    """API 가 받는 밀리초 정밀도 ISO 문자열로 보내야 한다."""
    routes = {
        TOKEN_PATH: [token_response()],
        CHANGED_PATH: [FakeResponse(200, {"data": {"lastChangeStatuses": []}})],
    }
    client, transport, _ = make_client(routes)
    start = datetime(2026, 8, 10, 1, 2, 3, tzinfo=KST)
    client.get_last_changed_statuses(start, start + timedelta(hours=1))
    params = transport.calls_to(CHANGED_PATH)[0][2]["params"]
    assert params["lastChangedFrom"] == "2026-08-10T01:02:03.000+09:00"
    assert params["lastChangedTo"] == "2026-08-10T02:02:03.000+09:00"


# --------------------------------------------------------------------------- #
# 상세 배치 조회
# --------------------------------------------------------------------------- #

def test_product_orders_are_requested_in_batches():
    """배치 상한을 넘는 id 목록은 나눠 호출하고 결과를 합친다."""
    ids = [f"PO{i}" for i in range(DETAIL_BATCH_SIZE * 2 + 5)]
    routes = {
        TOKEN_PATH: [token_response()],
        QUERY_PATH: [FakeResponse(200, {"data": [{"productOrderId": "x"}]})],
    }
    client, transport, _ = make_client(routes)
    details = client.get_product_orders(ids)
    calls = transport.calls_to(QUERY_PATH)
    assert len(calls) == 3
    assert len(calls[0][2]["json"]["productOrderIds"]) == DETAIL_BATCH_SIZE
    assert len(calls[-1][2]["json"]["productOrderIds"]) == 5
    assert len(details) == 3


def test_empty_id_list_skips_http_entirely():
    """빈 목록이면 호출하지 않는다(폴링 대부분이 이 경로다 — rate limit 절약)."""
    client, transport, _ = make_client({TOKEN_PATH: [token_response()]})
    assert client.get_product_orders([]) == []
    assert transport.calls == []


# --------------------------------------------------------------------------- #
# 재시도 / 오류 분류
# --------------------------------------------------------------------------- #

def test_server_error_is_retried_then_succeeds():
    """5xx 는 백오프 후 재시도하고, 성공하면 정상 반환한다."""
    routes = {
        TOKEN_PATH: [token_response()],
        CHANGED_PATH: [
            FakeResponse(500, text="boom"),
            FakeResponse(200, {"data": {"lastChangeStatuses": []}}),
        ],
    }
    client, transport, slept = make_client(routes)
    start = datetime(2026, 8, 10, 0, 0, tzinfo=KST)
    assert client.get_last_changed_statuses(start, start + timedelta(hours=1)) == []
    assert len(transport.calls_to(CHANGED_PATH)) == 2
    assert slept == [1.0]


def test_rate_limit_backoff_is_exponential_and_then_raises():
    """429 는 재시도 대상이며 대기가 지수적으로 늘고, 소진되면 HTTP 오류로 올린다."""
    routes = {
        TOKEN_PATH: [token_response()],
        CHANGED_PATH: [FakeResponse(429, text="too many")],
    }
    client, transport, slept = make_client(routes, max_retries=3)
    start = datetime(2026, 8, 10, 0, 0, tzinfo=KST)
    with pytest.raises(NaverCommerceHTTPError) as exc:
        client.get_last_changed_statuses(start, start + timedelta(hours=1))
    assert exc.value.status == 429
    assert slept == [1.0, 2.0, 4.0]
    assert len(transport.calls_to(CHANGED_PATH)) == 4  # 첫 시도 + 3회 재시도


def test_client_error_is_not_retried():
    """4xx(400 등)는 재시도해도 소용없으므로 즉시 실패한다."""
    routes = {
        TOKEN_PATH: [token_response()],
        CHANGED_PATH: [FakeResponse(400, text="bad window")],
    }
    client, transport, slept = make_client(routes)
    start = datetime(2026, 8, 10, 0, 0, tzinfo=KST)
    with pytest.raises(NaverCommerceHTTPError) as exc:
        client.get_last_changed_statuses(start, start + timedelta(hours=1))
    assert exc.value.status == 400
    assert slept == []
    assert len(transport.calls_to(CHANGED_PATH)) == 1


def test_unauthorized_refreshes_token_once_then_succeeds():
    """401 은 토큰 강제 재발급 후 1회만 재시도한다."""
    routes = {
        TOKEN_PATH: [token_response()],
        CHANGED_PATH: [
            FakeResponse(401, text="expired"),
            FakeResponse(200, {"data": {"lastChangeStatuses": []}}),
        ],
    }
    client, transport, _ = make_client(routes)
    start = datetime(2026, 8, 10, 0, 0, tzinfo=KST)
    assert client.get_last_changed_statuses(start, start + timedelta(hours=1)) == []
    assert len(transport.calls_to(TOKEN_PATH)) == 2  # 최초 + 강제 재발급
    assert len(transport.calls_to(CHANGED_PATH)) == 2


def test_persistent_unauthorized_raises_auth_error_without_loop():
    """재발급 후에도 401 이면 무한 재발급 대신 인증 오류로 끝낸다."""
    routes = {
        TOKEN_PATH: [token_response()],
        CHANGED_PATH: [FakeResponse(401, text="denied")],
    }
    client, transport, _ = make_client(routes)
    start = datetime(2026, 8, 10, 0, 0, tzinfo=KST)
    with pytest.raises(NaverCommerceAuthError):
        client.get_last_changed_statuses(start, start + timedelta(hours=1))
    assert len(transport.calls_to(TOKEN_PATH)) == 2


def test_network_exception_is_retried_then_raises():
    """네트워크 예외도 재시도 대상이고, 소진되면 연동 오류로 올린다."""

    class ExplodingTransport:
        def __init__(self):
            self.count = 0

        def request(self, method, url, **kwargs):
            if url.endswith(TOKEN_PATH):
                return token_response()
            self.count += 1
            raise ConnectionError("connection reset")

    transport = ExplodingTransport()
    slept: list[float] = []
    client = NaverCommerceClient(CLIENT_ID, SECRET, transport=transport,
                                 token_cache=MemoryTokenCache(), sleep=slept.append,
                                 max_retries=2)
    start = datetime(2026, 8, 10, 0, 0, tzinfo=KST)
    with pytest.raises(NaverCommerceError):
        client.get_last_changed_statuses(start, start + timedelta(hours=1))
    assert transport.count == 3  # 첫 시도 + 2회 재시도
    assert slept == [1.0, 2.0]


def test_unparseable_body_raises_integration_error():
    """2xx 인데 JSON 이 아니면 조용히 빈 결과로 넘기지 않고 실패시킨다."""
    routes = {
        TOKEN_PATH: [token_response()],
        CHANGED_PATH: [FakeResponse(200, raise_on_json=True)],
    }
    client, _, _ = make_client(routes)
    start = datetime(2026, 8, 10, 0, 0, tzinfo=KST)
    with pytest.raises(NaverCommerceError):
        client.get_last_changed_statuses(start, start + timedelta(hours=1))


# --------------------------------------------------------------------------- #
# Redis 캐시 fail-open
# --------------------------------------------------------------------------- #

def test_redis_cache_failure_falls_back_to_reissue():
    """Redis 가 죽어도 수집이 멈추면 안 된다 — 캐시 미스로 강등하고 계속 간다."""
    from foms.services.integrations.naver_commerce.client import RedisTokenCache

    class DeadRedis:
        def get(self, key):
            raise RuntimeError("redis down")

        def setex(self, key, ttl, value):
            raise RuntimeError("redis down")

    client, transport, _ = make_client({TOKEN_PATH: [token_response()]},
                                       token_cache=RedisTokenCache(DeadRedis()))
    assert client.get_access_token() == "tok-abc"
    assert client.get_access_token() == "tok-abc"
    assert len(transport.calls_to(TOKEN_PATH)) == 2  # 캐시가 죽어 매번 재발급하지만 동작은 유지


# --------------------------------------------------------------------------- #
# 호출 한도 헤더 관측 (2026-08-31) — 일괄 발송처리 대비
# --------------------------------------------------------------------------- #

def test_rate_limit_headers_are_logged_when_present(caplog):
    """여유가 남아 있으면 debug 로 남긴다 — 매 호출 경고를 만들지 않는다."""
    headers = {"GNCP-GW-RateLimit-Remaining": "2",
               "GNCP-GW-RateLimit-Replenish-Rate": "2",
               "GNCP-GW-RateLimit-Burst-Capacity": "4"}
    client, _, _ = make_client({
        TOKEN_PATH: [token_response()],
        QUERY_PATH: [FakeResponse(200, {"data": []}, headers=headers)],
    })
    with caplog.at_level(logging.DEBUG,
                         logger="foms.services.integrations.naver_commerce.client"):
        client.get_product_orders(["1"])
    line = next(r for r in caplog.records if "호출 한도" in r.getMessage())
    assert line.levelno == logging.DEBUG
    assert "남음=2" in line.getMessage()
    assert "초당배정=2" in line.getMessage()
    assert "버스트=4" in line.getMessage()


def test_rate_limit_headers_warn_when_budget_nearly_gone(caplog):
    """남은 호출이 바닥이면 경고다 — 다음 호출이 429 로 **처리 없이** 실패한다."""
    client, _, _ = make_client({
        TOKEN_PATH: [token_response()],
        QUERY_PATH: [FakeResponse(200, {"data": []},
                                  headers={"GNCP-GW-RateLimit-Remaining": "0"})],
    })
    with caplog.at_level(logging.DEBUG,
                         logger="foms.services.integrations.naver_commerce.client"):
        client.get_product_orders(["1"])
    line = next(r for r in caplog.records if "호출 한도" in r.getMessage())
    assert line.levelno == logging.WARNING


def test_rate_limit_header_lookup_is_case_insensitive(caplog):
    """주입 전송은 보통 그냥 dict 다 — 철자 대소문자로 로그가 조용히 비면 안 된다."""
    client, _, _ = make_client({
        TOKEN_PATH: [token_response()],
        QUERY_PATH: [FakeResponse(200, {"data": []},
                                  headers={"gncp-gw-ratelimit-remaining": "7"})],
    })
    with caplog.at_level(logging.DEBUG,
                         logger="foms.services.integrations.naver_commerce.client"):
        client.get_product_orders(["1"])
    assert any("남음=7" in r.getMessage() for r in caplog.records)


def test_no_rate_limit_headers_logs_nothing(caplog):
    """헤더가 없으면 한 줄도 남기지 않는다(토큰 발급 등 매 호출 잡음 방지)."""
    client, _, _ = make_client({
        TOKEN_PATH: [token_response()],
        QUERY_PATH: [FakeResponse(200, {"data": []})],
    })
    with caplog.at_level(logging.DEBUG,
                         logger="foms.services.integrations.naver_commerce.client"):
        client.get_product_orders(["1"])
    assert not [r for r in caplog.records if "호출 한도" in r.getMessage()]


# --------------------------------------------------------------------------- #
# 변경분 이어받기(more) — NAVER-INGEST-BACKFILL T1
# --------------------------------------------------------------------------- #

def test_last_changed_follows_more_within_one_window():
    """한 창의 응답이 상한을 넘으면 more 로 이어받아 전부 모은다."""
    routes = {
        TOKEN_PATH: [token_response()],
        CHANGED_PATH: [
            FakeResponse(200, {"data": {
                "lastChangeStatuses": [{"productOrderId": "A"}],
                "more": {"moreFrom": "2026-08-10T05:00:00.000+09:00", "moreSequence": "7"},
            }}),
            FakeResponse(200, {"data": {"lastChangeStatuses": [{"productOrderId": "B"}]}}),
        ],
    }
    client, transport, _ = make_client(routes)
    start = datetime(2026, 8, 10, 0, 0, tzinfo=KST)
    result = client.get_last_changed_statuses(start, start + timedelta(hours=6))
    assert [row["productOrderId"] for row in result] == ["A", "B"]
    calls = transport.calls_to(CHANGED_PATH)
    assert len(calls) == 2
    first, second = calls[0][2]["params"], calls[1][2]["params"]
    assert first["limitCount"] == 300
    assert "moreSequence" not in first
    # 이어받기는 moreFrom 을 그대로 시작 일시로 쓰고 moreSequence 를 함께 보낸다.
    assert second["lastChangedFrom"] == "2026-08-10T05:00:00.000+09:00"
    assert second["moreSequence"] == "7"
    # 창 끝은 고정이다 — 옮기면 범위가 새로 열린다.
    assert second["lastChangedTo"] == first["lastChangedTo"]


def test_last_changed_more_without_sequence_omits_param():
    """moreSequence 가 없으면 파라미터를 보내지 않는다(임의값 금지 — 문서 경고)."""
    routes = {
        TOKEN_PATH: [token_response()],
        CHANGED_PATH: [
            FakeResponse(200, {"data": {
                "lastChangeStatuses": [{"productOrderId": "A"}],
                "more": {"moreFrom": "2026-08-10T05:00:00.000+09:00"},
            }}),
            FakeResponse(200, {"data": {"lastChangeStatuses": []}}),
        ],
    }
    client, transport, _ = make_client(routes)
    start = datetime(2026, 8, 10, 0, 0, tzinfo=KST)
    client.get_last_changed_statuses(start, start + timedelta(hours=6))
    second = transport.calls_to(CHANGED_PATH)[1][2]["params"]
    assert "moreSequence" not in second


def test_last_changed_more_page_limit_stops_loop():
    """서버가 more 를 끝없이 돌려줘도 쪽수 상한에서 멈춘다(무한 루프 금지)."""
    routes = {
        TOKEN_PATH: [token_response()],
        CHANGED_PATH: [FakeResponse(200, {"data": {
            "lastChangeStatuses": [{"productOrderId": "A"}],
            "more": {"moreFrom": "2026-08-10T05:00:00.000+09:00", "moreSequence": "1"},
        }})],
    }
    client, transport, _ = make_client(routes)
    start = datetime(2026, 8, 10, 0, 0, tzinfo=KST)
    result = client.get_last_changed_statuses(start, start + timedelta(hours=6))
    assert len(transport.calls_to(CHANGED_PATH)) == LAST_CHANGED_MAX_PAGES
    assert len(result) == LAST_CHANGED_MAX_PAGES


def test_last_changed_more_without_rows_stops_loop():
    """항목 0건인데 more 만 오면 진척이 없다 — 같은 요청을 반복하지 않는다."""
    routes = {
        TOKEN_PATH: [token_response()],
        CHANGED_PATH: [FakeResponse(200, {"data": {
            "lastChangeStatuses": [],
            "more": {"moreFrom": "2026-08-10T05:00:00.000+09:00"},
        }})],
    }
    client, transport, _ = make_client(routes)
    start = datetime(2026, 8, 10, 0, 0, tzinfo=KST)
    assert client.get_last_changed_statuses(start, start + timedelta(hours=6)) == []
    assert len(transport.calls_to(CHANGED_PATH)) == 1

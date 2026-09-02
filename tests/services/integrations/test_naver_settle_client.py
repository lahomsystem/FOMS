"""NAVER-SETTLE-01 §2: 정산 조회 클라이언트 + enum 카탈로그 계약 테스트.

네트워크를 타지 않는다 — 전송(transport)·대기(sleep)를 주입해 경로·파라미터·검증 실패를
결정적으로 고정한다. 여기서 지키는 계약 4가지:

* **경로·파라미터**: 5개 메서드가 문서(``docs/research/2026-09-02-naver-settlement/raw``)의
  경로와 파라미터 이름(camelCase)으로 나간다.
* **빈 필터 금지**: ``None``·공백 파라미터는 키째로 빠진다(빈 값을 보내면 400).
* **규격 선검증**: page_size 상한(1000)·enum 허용 집합을 클라이언트가 먼저 막는다.
  보내는 enum 은 공식 범례로만 받는다 — 스냅샷 관측값을 실으면 400 이다.
* **quota 헤더 관측**: ``gncp-gw-quota-limit`` 가 오면 속성에만 담는다. 재시도·백오프
  동작은 바뀌지 않는다(중단 판단은 순회 호출자 몫).
"""

from __future__ import annotations

from datetime import date, datetime

import bcrypt
import pytest

from foms.services.integrations.naver_commerce import settle_enums
from foms.services.integrations.naver_commerce.client import (
    DEFAULT_SETTLE_PERIOD_TYPE,
    QUOTA_LIMIT_HEADER,
    SETTLE_MAX_PAGE_SIZE,
    MemoryTokenCache,
    NaverCommerceClient,
    NaverCommerceHTTPError,
)

CLIENT_ID = "test-client-id"
SECRET = bcrypt.gensalt(rounds=4).decode("utf-8")  # 실 시크릿과 같은 bcrypt salt 형식
TOKEN_PATH = "/v1/oauth2/token"

SETTLE_DAILY_PATH = "/v1/pay-settle/settle/daily"
SETTLE_CASE_PATH = "/v1/pay-settle/settle/case"
COMMISSION_PATH = "/v1/pay-settle/settle/commission-details"
VAT_DAILY_PATH = "/v1/pay-settle/vat/daily"
VAT_CASE_PATH = "/v1/pay-settle/vat/case"

ALL_SETTLE_PATHS = (SETTLE_DAILY_PATH, SETTLE_CASE_PATH, COMMISSION_PATH,
                    VAT_DAILY_PATH, VAT_CASE_PATH)

PAGE_PAYLOAD = {"elements": [], "pagination": {"page": 1, "size": 1000,
                                               "totalPages": 1, "totalElements": 0}}


class FakeResponse:
    """requests.Response 최소 계약(status_code / json() / text / headers)만 흉내낸다."""

    def __init__(self, status_code: int, payload=None, text: str = "",
                 headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload
        self.text = text or ""
        self.headers = dict(headers or {})

    def json(self):
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


def token_response() -> FakeResponse:
    return FakeResponse(200, {"access_token": "tok-abc", "expires_in": 10799})


def make_client(routes: dict[str, list[FakeResponse]] | None = None,
                **kwargs) -> tuple[NaverCommerceClient, FakeTransport]:
    """전송·캐시·sleep 을 모두 주입한 클라이언트를 만든다(네트워크·실대기 없음)."""
    full = {TOKEN_PATH: [token_response()]}
    if routes:
        full.update(routes)
    else:
        for path in ALL_SETTLE_PATHS:
            full[path] = [FakeResponse(200, PAGE_PAYLOAD)]
    transport = FakeTransport(full)
    client = NaverCommerceClient(
        CLIENT_ID, SECRET,
        transport=transport,
        token_cache=MemoryTokenCache(),
        sleep=lambda _seconds: None,
        **kwargs,
    )
    return client, transport


def sent_params(transport: FakeTransport, path: str) -> dict:
    """그 경로로 **실제 나간** 쿼리 파라미터를 돌려준다(호출 1회 전제)."""
    calls = transport.calls_to(path)
    assert len(calls) == 1, f"{path} 호출 횟수={len(calls)}"
    method, _url, kwargs = calls[0]
    assert method == "GET", f"정산 조회는 GET 이어야 한다(받은 값: {method})"
    return kwargs["params"]


# --------------------------------------------------------------------------- #
# 경로·파라미터
# --------------------------------------------------------------------------- #

def test_settle_daily_sends_range_and_page_params():
    """일별 정산: startDate·endDate·pageNumber·pageSize 4종이 그대로 나간다."""
    client, transport = make_client()
    payload = client.get_settle_daily(date(2026, 8, 1), date(2026, 8, 31), page=2, page_size=500)

    assert payload == PAGE_PAYLOAD  # 응답은 파싱만 하고 손대지 않는다
    assert sent_params(transport, SETTLE_DAILY_PATH) == {
        "startDate": "2026-08-01",
        "endDate": "2026-08-31",
        "pageNumber": 2,
        "pageSize": 500,
    }


def test_settle_cases_defaults_to_expect_date_period_and_max_page_size():
    """건별 정산 기본값: 정산 예정일 기준 + 1쪽 + 1000건(하루 단위 searchDate)."""
    client, transport = make_client()
    client.get_settle_cases(date(2026, 8, 20))

    assert sent_params(transport, SETTLE_CASE_PATH) == {
        "searchDate": "2026-08-20",
        "periodType": DEFAULT_SETTLE_PERIOD_TYPE,
        "pageNumber": 1,
        "pageSize": SETTLE_MAX_PAGE_SIZE,
    }
    assert DEFAULT_SETTLE_PERIOD_TYPE in settle_enums.PERIOD_TYPES


def test_settle_cases_sends_every_optional_filter_when_given():
    """선택 필터를 다 주면 문서 파라미터 이름(camelCase) 그대로 나간다."""
    client, transport = make_client()
    client.get_settle_cases(
        date(2026, 8, 20),
        period_type="SETTLE_CASEBYCASE_PAY_DATE",
        settle_type="NORMAL_SETTLE_ORIGINAL",
        settle_decision_type="SETTLED",
        order_id="2026082012345",
        product_order_id="2026082012345678",
        page=3,
        page_size=10,
    )

    assert sent_params(transport, SETTLE_CASE_PATH) == {
        "searchDate": "2026-08-20",
        "periodType": "SETTLE_CASEBYCASE_PAY_DATE",
        "settleType": "NORMAL_SETTLE_ORIGINAL",
        "settleDecisionType": "SETTLED",
        "orderId": "2026082012345",
        "productOrderId": "2026082012345678",
        "pageNumber": 3,
        "pageSize": 10,
    }


def test_commission_details_uses_its_own_path_with_same_params():
    """수수료 상세는 경로만 다르고 파라미터 규격은 건별 정산과 같다."""
    client, transport = make_client()
    client.get_settle_commission_details(date(2026, 8, 20), settle_type="QUICK_SETTLE_ORIGINAL")

    assert sent_params(transport, COMMISSION_PATH) == {
        "searchDate": "2026-08-20",
        "periodType": DEFAULT_SETTLE_PERIOD_TYPE,
        "settleType": "QUICK_SETTLE_ORIGINAL",
        "pageNumber": 1,
        "pageSize": SETTLE_MAX_PAGE_SIZE,
    }
    assert not transport.calls_to(SETTLE_CASE_PATH)  # 경로가 섞이지 않는다


def test_vat_daily_and_vat_case_send_range_params():
    """부가세 2종은 구간(startDate·endDate) 조회다 — 경로가 서로 다르다."""
    client, transport = make_client()
    client.get_vat_daily(date(2026, 7, 1), date(2026, 7, 31))
    client.get_vat_cases(date(2026, 7, 1), date(2026, 7, 31), page=2, page_size=200)

    assert sent_params(transport, VAT_DAILY_PATH) == {
        "startDate": "2026-07-01",
        "endDate": "2026-07-31",
        "pageNumber": 1,
        "pageSize": SETTLE_MAX_PAGE_SIZE,
    }
    assert sent_params(transport, VAT_CASE_PATH) == {
        "startDate": "2026-07-01",
        "endDate": "2026-07-31",
        "pageNumber": 2,
        "pageSize": 200,
    }


def test_datetime_argument_is_reduced_to_date_string():
    """datetime 을 넘겨도 날짜(yyyy-MM-dd)만 나간다(시각이 붙으면 400)."""
    client, transport = make_client()
    client.get_settle_daily(datetime(2026, 8, 1, 13, 45), datetime(2026, 8, 2, 0, 5))

    params = sent_params(transport, SETTLE_DAILY_PATH)
    assert params["startDate"] == "2026-08-01"
    assert params["endDate"] == "2026-08-02"


# --------------------------------------------------------------------------- #
# None·공백 파라미터는 아예 보내지 않는다
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("method_name", ["get_settle_cases", "get_settle_commission_details"])
def test_none_optional_params_are_omitted_entirely(method_name):
    """``None`` 선택 필터는 키째로 빠진다 — 빈 값을 실어 보내면 400 이다."""
    client, transport = make_client()
    path = SETTLE_CASE_PATH if method_name == "get_settle_cases" else COMMISSION_PATH
    getattr(client, method_name)(
        date(2026, 8, 20),
        settle_type=None, settle_decision_type=None,
        order_id=None, product_order_id=None,
    )

    params = sent_params(transport, path)
    for key in ("settleType", "settleDecisionType", "orderId", "productOrderId"):
        assert key not in params


def test_blank_text_filters_are_omitted_too():
    """공백뿐인 주문번호 필터도 보내지 않는다(빈 문자열 필터 = 400)."""
    client, transport = make_client()
    client.get_settle_cases(date(2026, 8, 20), order_id="   ", product_order_id="")

    params = sent_params(transport, SETTLE_CASE_PATH)
    assert "orderId" not in params
    assert "productOrderId" not in params


def test_none_period_type_omits_the_parameter():
    """periodType 을 명시적으로 비우면 파라미터를 보내지 않는다(API 기본값에 맡긴다)."""
    client, transport = make_client()
    client.get_settle_cases(date(2026, 8, 20), period_type=None)

    assert "periodType" not in sent_params(transport, SETTLE_CASE_PATH)


# --------------------------------------------------------------------------- #
# 규격 선검증 (호출 전에 막는다)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("bad_size", [1001, 5000, 0, -1])
def test_page_size_out_of_range_raises_value_error(bad_size):
    """페이지 크기 규격(1~1000) 밖이면 호출 전에 ValueError 다."""
    client, transport = make_client()
    with pytest.raises(ValueError) as exc:
        client.get_settle_daily(date(2026, 8, 1), date(2026, 8, 2), page_size=bad_size)

    assert "1~1000" in str(exc.value)
    assert not transport.calls_to(SETTLE_DAILY_PATH)  # 네트워크로 나가지 않았다


def test_page_number_below_one_raises_value_error():
    """페이지 번호는 1부터다(0쪽 요청은 400)."""
    client, _ = make_client()
    with pytest.raises(ValueError):
        client.get_vat_daily(date(2026, 7, 1), date(2026, 7, 31), page=0)


@pytest.mark.parametrize(("kwargs", "needle"), [
    ({"period_type": "SETTLE_SCHEDULE_DATE"}, "period_type"),
    ({"settle_type": "NORMAL_SETTLE"}, "settle_type"),
    ({"settle_decision_type": "DONE"}, "settle_decision_type"),
])
def test_invalid_enum_raises_value_error_before_call(kwargs, needle):
    """문서에 없는 enum 은 보내지 않는다 — 관측값을 그대로 실으면 400 이다."""
    client, transport = make_client()
    with pytest.raises(ValueError) as exc:
        client.get_settle_cases(date(2026, 8, 20), **kwargs)

    assert needle in str(exc.value)
    assert not transport.calls_to(SETTLE_CASE_PATH)


def test_non_date_argument_raises_value_error():
    """날짜 자리에 문자열을 넣으면 조용히 나가지 않고 즉시 막는다."""
    client, _ = make_client()
    with pytest.raises(ValueError) as exc:
        client.get_settle_cases("2026-08-20")  # type: ignore[arg-type]
    assert "date" in str(exc.value)


# --------------------------------------------------------------------------- #
# quota 헤더 관측 (읽기 전용)
# --------------------------------------------------------------------------- #

def test_quota_limit_header_is_captured_on_success():
    """성공 응답에 quota 헤더가 오면 속성에 담긴다(순회 중단 판단 근거)."""
    client, _ = make_client({
        SETTLE_CASE_PATH: [FakeResponse(200, PAGE_PAYLOAD, headers={QUOTA_LIMIT_HEADER: "5"})],
    })
    assert client.last_quota_limit_header is None

    client.get_settle_cases(date(2026, 8, 20))
    assert client.last_quota_limit_header == "5"


def test_quota_limit_header_is_captured_case_insensitively_on_error():
    """오류 응답에서도 담는다. 헤더 철자 대소문자는 가리지 않는다(주입 전송은 그냥 dict)."""
    client, _ = make_client({
        SETTLE_DAILY_PATH: [FakeResponse(400, {}, text="bad request",
                                         headers={"GNCP-GW-Quota-Limit": "5"})],
    })
    with pytest.raises(NaverCommerceHTTPError):
        client.get_settle_daily(date(2026, 8, 1), date(2026, 8, 2))

    assert client.last_quota_limit_header == "5"


def test_quota_limit_header_resets_when_absent():
    """헤더 없는 응답이면 ``None`` 으로 돌아간다(옛 값이 남아 오판하지 않게)."""
    client, _ = make_client({
        SETTLE_CASE_PATH: [FakeResponse(200, PAGE_PAYLOAD, headers={QUOTA_LIMIT_HEADER: "5"})],
        VAT_DAILY_PATH: [FakeResponse(200, PAGE_PAYLOAD)],
    })
    client.get_settle_cases(date(2026, 8, 20))
    assert client.last_quota_limit_header == "5"

    client.get_vat_daily(date(2026, 7, 1), date(2026, 7, 31))
    assert client.last_quota_limit_header is None


def test_quota_header_does_not_change_retry_behaviour():
    """헤더 관측은 **읽기 전용**이다 — 429 재시도 횟수는 그대로다(중단은 호출자 몫)."""
    responses = [FakeResponse(429, {}, text="quota", headers={QUOTA_LIMIT_HEADER: "5"})]
    client, transport = make_client({SETTLE_CASE_PATH: responses}, max_retries=2)
    with pytest.raises(NaverCommerceHTTPError):
        client.get_settle_cases(date(2026, 8, 20))

    assert len(transport.calls_to(SETTLE_CASE_PATH)) == 3  # 첫 시도 + 재시도 2회
    assert client.last_quota_limit_header == "5"


# --------------------------------------------------------------------------- #
# enum 카탈로그 (원문 전량 전사)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(("mapping", "expected"), [
    (settle_enums.PERIOD_TYPES, 5),
    (settle_enums.SETTLE_DECISION_TYPES, 3),
    (settle_enums.SETTLE_TYPES, 7),
    (settle_enums.PRODUCT_ORDER_TYPES, 27),
    (settle_enums.COMMISSION_TYPES, 14),
    (settle_enums.PAY_MEANS_TYPES, 16),
    (settle_enums.SETTLE_METHOD_TYPES, 2),
    (settle_enums.VAT_DETAIL_TYPES, 11),
    (settle_enums.VAT_STATUSES, 4),
])
def test_enum_catalog_counts_match_the_docs(mapping, expected):
    """문서 원문의 값 개수와 정확히 같아야 한다(누락 = 화면에 코드가 그대로 뜬다)."""
    assert len(mapping) == expected


def test_bank_types_cover_the_full_document_list():
    """은행 목록은 60종 이상(원문 64종)이고 저축은행·증권사까지 포함한다."""
    assert len(settle_enums.BANK_TYPES) >= 60
    for code in ("KB", "SHINHAN", "KEB_HANA", "TOSS", "KKOBANK", "POST",
                 "WELCOME_BANK", "KIWOOM_IVST_SEC", "KSFC"):
        assert code in settle_enums.BANK_TYPES, code


@pytest.mark.parametrize(("mapping", "code", "expected"), [
    (settle_enums.SETTLE_TYPES, "NORMAL_SETTLE_ORIGINAL", "일반 정산"),
    (settle_enums.SETTLE_TYPES, "QUANTITY_CANCEL_RESTORE", "수량 취소 정산(환급)"),
    (settle_enums.PERIOD_TYPES, "SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE", "정산 예정일"),
    (settle_enums.PRODUCT_ORDER_TYPES, "PROD_ORDER", "상품 주문"),
    (settle_enums.PRODUCT_ORDER_TYPES, "DELIVERY", "배송비"),
    (settle_enums.COMMISSION_TYPES, "PAY_COMMISSION", "Npay 수수료"),
    (settle_enums.COMMISSION_TYPES, "PLATFORM_COMMISSION", "판매 수수료"),
    (settle_enums.PAY_MEANS_TYPES, "PAYMEANS_TYPE_CCARD", "신용카드"),
    (settle_enums.SETTLE_METHOD_TYPES, "CHARGE_AMT", "충전금"),
    (settle_enums.BANK_TYPES, "KB", "KB국민은행"),
    (settle_enums.VAT_DETAIL_TYPES, "VOUCH_DETAIL_PAYMENT_SETL", "결제 대금 정산"),
    (settle_enums.VAT_STATUSES, "VOUCH_PUBLICATION", "원주문 매출"),
])
def test_sampled_labels_match_the_document_wording(mapping, code, expected):
    """라벨은 원문 표기 그대로다 — 판매자센터와 낱말이 달라지면 대조가 안 된다."""
    assert mapping[code] == expected


def test_negative_settle_types_are_a_subset_of_settle_types():
    """차감/환급 집합은 정산 구분 카탈로그 안에 있어야 한다(오타 방지)."""
    assert settle_enums.NEGATIVE_SETTLE_TYPES <= set(settle_enums.SETTLE_TYPES)
    assert settle_enums.NEGATIVE_SETTLE_TYPES == {
        "NORMAL_SETTLE_AFTER_CANCEL",
        "NORMAL_SETTLE_BEFORE_CANCEL",
        "QUICK_SETTLE_CANCEL",
        "QUANTITY_CANCEL_RESTORE",
    }
    # 원거래는 들어가면 안 된다(부호 반전 대상이 아니다).
    assert "NORMAL_SETTLE_ORIGINAL" not in settle_enums.NEGATIVE_SETTLE_TYPES


def test_label_falls_back_to_the_code_for_unknown_values():
    """모르는 코드는 코드 그대로 — 네이버가 값을 늘려도 화면이 빈칸이 되지 않는다."""
    assert settle_enums.label(settle_enums.SETTLE_TYPES, "NORMAL_SETTLE_ORIGINAL") == "일반 정산"
    assert settle_enums.label(settle_enums.SETTLE_TYPES, "BRAND_NEW_CODE") == "BRAND_NEW_CODE"
    assert settle_enums.label(settle_enums.SETTLE_TYPES, None) == ""
    assert settle_enums.label(settle_enums.SETTLE_TYPES, "") == ""

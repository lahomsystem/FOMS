"""변환기 실패 사유 분류 계약 (GEO-FAILKIND-01).

운영 사고(2026-09-01): 실측 지도 "주소오류" 배지가 붙은 11건의 주소가 전부 무죄였다.
같은 코드·같은 운영 키로 다시 변환하니 11/11 성공했고, outbox 행에는
``attempts=1 · last_error=NULL · DONE`` 만 남아 사유를 알 수 없었다. 원인은
:class:`FOMSAddressConverter` 가 키 부재·타임아웃·429·HTTP 비200 을 전부
``except Exception`` 으로 삼켜 "주소를 찾을 수 없음"과 같은 실패로 강등한 것이다.

이 계약은 **다시 부르면 될 실패**(transient)와 **주소를 고쳐야 하는 실패**(permanent)가
갈라지는지 본다. 기존 :mod:`tests.domains.test_address_query` 는 전처리 문자열 동일성만
보기 때문에 이 축을 전혀 잡지 못한다.

모든 케이스는 음성 대조군을 동반한다 — 양성(일시 오류)만 확인하면 "전부 transient" 로
퇴화한 구현도 통과하기 때문이다.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest
import requests

from foms.services.common import address_converter as ac
from foms.services.common.address_converter import (
    FAILURE_PERMANENT,
    FAILURE_TRANSIENT,
    FOMSAddressConverter,
)


class _FakeResponse:
    """카카오 응답 대역(상태코드 + JSON 본문)."""

    def __init__(self, status_code: int, payload: Optional[dict] = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self) -> dict:
        return self._payload


def _documents(lat: float = 37.5, lng: float = 127.0) -> dict:
    """address·keyword 양쪽 파서가 읽을 수 있는 성공 응답 1건.

    keyword API 는 문서 최상위의 ``x``/``y`` 를 읽는다 — 그 키가 없으면 파싱 예외가 나서
    실패 종류가 transient 로 뒤집힌다(대역이 실제 응답 모양을 벗어나면 안 되는 이유).
    """
    return {
        "documents": [
            {
                "y": str(lat),
                "x": str(lng),
                "address": {
                    "y": str(lat),
                    "x": str(lng),
                    "region_1depth_name": "서울",
                    "region_2depth_name": "강남구",
                    "region_3depth_name": "역삼동",
                }
            }
        ]
    }


@pytest.fixture
def converter(monkeypatch: pytest.MonkeyPatch) -> FOMSAddressConverter:
    """학습·고급처리 의존을 걷어낸 변환기(외부 호출 축만 검사).

    프로세스 전역 캐시를 매 케이스마다 비운다 — 앞 케이스의 실패가 600초 TTL 로
    남아 다음 케이스의 API 호출을 건너뛰면 판정이 뒤집힌다.
    """
    FOMSAddressConverter.clear_geocode_cache()
    inst = FOMSAddressConverter.__new__(FOMSAddressConverter)
    inst.base_url = "https://dapi.kakao.com/v2/local/search/address.json"
    inst.keyword_url = "https://dapi.kakao.com/v2/local/search/keyword.json"

    class _NoLearning:
        def suggest_correction(self, address: str) -> None:
            return None

    class _NoProcessor:
        def process_address(self, address: str) -> str:
            return address

        def extract_address_components(self, address: str) -> dict:
            return {"city": None, "district": None, "dong": None}

    inst.learning_system = _NoLearning()
    inst.advanced_processor = _NoProcessor()
    inst.ai_enabled = False
    monkeypatch.setattr(ac, "kakao_rest_headers", lambda: {"Authorization": "KakaoAK test"})
    monkeypatch.setattr(ac.time, "sleep", lambda *_a, **_k: None)
    yield inst
    FOMSAddressConverter.clear_geocode_cache()


def _patch_get(monkeypatch: pytest.MonkeyPatch, handler: Any) -> list[str]:
    """``requests.get`` 을 대역으로 바꾸고 호출된 URL 목록을 돌려준다."""
    calls: list[str] = []

    def _fake_get(url: str, **kwargs: Any):
        calls.append(url)
        return handler(url, **kwargs)

    monkeypatch.setattr(ac.requests, "get", _fake_get)
    return calls


def test_timeout_is_transient(converter: FOMSAddressConverter,
                              monkeypatch: pytest.MonkeyPatch) -> None:
    """타임아웃은 일시 오류다(주소는 판정된 적이 없다)."""
    def _boom(url: str, **kwargs: Any):
        raise requests.exceptions.Timeout("read timeout")

    _patch_get(monkeypatch, _boom)
    lat, lng, _status, kind = converter.convert_address_with_reason("서울 강남구 테헤란로 1")
    assert (lat, lng) == (None, None)
    assert kind == FAILURE_TRANSIENT


def test_address_not_found_is_permanent(converter: FOMSAddressConverter,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """음성 대조군: 200 + 문서 0건은 주소 오류다(일시 오류로 뭉뚱그리지 않는다)."""
    _patch_get(monkeypatch, lambda url, **kw: _FakeResponse(200, {"documents": []}))
    lat, lng, _status, kind = converter.convert_address_with_reason("없는주소 999-999")
    assert (lat, lng) == (None, None)
    assert kind == FAILURE_PERMANENT


@pytest.mark.parametrize("status_code", [401, 403, 429, 500, 502, 503])
def test_non_200_status_codes_are_transient(converter: FOMSAddressConverter,
                                            monkeypatch: pytest.MonkeyPatch,
                                            status_code: int) -> None:
    """인증·쿼터·서버 오류는 전부 일시 오류다."""
    _patch_get(monkeypatch, lambda url, **kw: _FakeResponse(status_code))
    _lat, _lng, _status, kind = converter.convert_address_with_reason("서울 강남구 테헤란로 1")
    assert kind == FAILURE_TRANSIENT


def test_bad_request_is_permanent(converter: FOMSAddressConverter,
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """음성 대조군: 400 은 같은 질의로 다시 불러도 같은 답이라 permanent 다."""
    _patch_get(monkeypatch, lambda url, **kw: _FakeResponse(400))
    _lat, _lng, _status, kind = converter.convert_address_with_reason("서울 강남구 테헤란로 1")
    assert kind == FAILURE_PERMANENT


def test_success_reports_no_failure_kind(converter: FOMSAddressConverter,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """음성 대조군: 성공은 실패 사유가 없다."""
    _patch_get(monkeypatch, lambda url, **kw: _FakeResponse(200, _documents()))
    lat, lng, _status, kind = converter.convert_address_with_reason("서울 강남구 테헤란로 1")
    assert (lat, lng) == (37.5, 127.0)
    assert kind is None


def test_missing_api_key_is_transient(converter: FOMSAddressConverter,
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """키 부재(RuntimeError)는 일시 오류다 — 주소 탓으로 돌리면 안 된다."""
    def _no_key():
        raise RuntimeError("KAKAO_REST_API_KEY 환경변수가 설정되지 않았습니다.")

    monkeypatch.setattr(ac, "kakao_rest_headers", _no_key)
    _patch_get(monkeypatch, lambda url, **kw: _FakeResponse(200, _documents()))
    _lat, _lng, _status, kind = converter.convert_address_with_reason("서울 강남구 테헤란로 1")
    assert kind == FAILURE_TRANSIENT


def test_coordinates_outside_korea_are_permanent(converter: FOMSAddressConverter,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """음성 대조군: bbox 밖 좌표는 우리가 거부한 것이므로 permanent."""
    _patch_get(monkeypatch, lambda url, **kw: _FakeResponse(200, _documents(lat=48.8, lng=2.3)))
    _lat, _lng, _status, kind = converter.convert_address_with_reason("Paris")
    assert kind == FAILURE_PERMANENT


def test_transient_on_first_strategy_does_not_hide_later_success(
        converter: FOMSAddressConverter, monkeypatch: pytest.MonkeyPatch) -> None:
    """일시 오류를 겪어도 뒤 전략이 성공하면 성공이 이긴다."""
    state = {"n": 0}

    def _handler(url: str, **kwargs: Any):
        state["n"] += 1
        if state["n"] == 1:
            raise requests.exceptions.ConnectionError("boom")
        return _FakeResponse(200, _documents())

    _patch_get(monkeypatch, _handler)
    lat, lng, _status, kind = converter.convert_address_with_reason("서울 강남구 테헤란로 1 101동 202호")
    assert (lat, lng) == (37.5, 127.0)
    assert kind is None


def test_any_transient_wins_over_permanent_when_all_fail(
        converter: FOMSAddressConverter, monkeypatch: pytest.MonkeyPatch) -> None:
    """전략 중 하나라도 일시 오류였고 끝내 실패했으면 결과는 transient 다.

    그 주소는 아직 "찾을 수 없다"는 답을 온전히 받은 적이 없다 — permanent 로 굳히면
    사람이 멀쩡한 주소를 고치러 가게 된다(이번 사고의 사용자 경험).
    """
    state = {"n": 0}

    def _handler(url: str, **kwargs: Any):
        state["n"] += 1
        if state["n"] == 1:
            return _FakeResponse(429)
        return _FakeResponse(200, {"documents": []})

    _patch_get(monkeypatch, _handler)
    _lat, _lng, _status, kind = converter.convert_address_with_reason("서울 강남구 테헤란로 1 101동 202호")
    assert kind == FAILURE_TRANSIENT


def test_transient_failure_is_not_cached(converter: FOMSAddressConverter,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """일시 오류는 실패 캐시에 남지 않는다 — 회복된 뒤 곧바로 다시 부를 수 있어야 한다."""
    state = {"fail": True}

    def _handler(url: str, **kwargs: Any):
        if state["fail"]:
            raise requests.exceptions.Timeout("read timeout")
        return _FakeResponse(200, _documents())

    _patch_get(monkeypatch, _handler)
    _lat, _lng, _status, kind = converter.convert_address_with_reason("서울 강남구 테헤란로 1")
    assert kind == FAILURE_TRANSIENT

    state["fail"] = False
    lat, lng, _status2, kind2 = converter.convert_address_with_reason("서울 강남구 테헤란로 1")
    assert (lat, lng) == (37.5, 127.0), "일시 오류가 캐시에 남아 재시도를 삼켰다"
    assert kind2 is None


def test_permanent_failure_is_cached(converter: FOMSAddressConverter,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """음성 대조군: 주소 오류는 기존대로 캐시된다(같은 주소 반복 호출 억제)."""
    calls = _patch_get(monkeypatch, lambda url, **kw: _FakeResponse(200, {"documents": []}))
    converter.convert_address_with_reason("없는주소 999-999")
    first_round = len(calls)
    assert first_round > 0
    converter.convert_address_with_reason("없는주소 999-999")
    assert len(calls) == first_round, "permanent 실패가 캐시되지 않아 API 를 다시 불렀다"


def test_legacy_return_shapes_unchanged(converter: FOMSAddressConverter,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """기존 호출자 계약 유지: convert_address 3-튜플, analyze_address 4-튜플."""
    _patch_get(monkeypatch, lambda url, **kw: _FakeResponse(200, _documents()))
    assert len(converter.convert_address("서울 강남구 테헤란로 1")) == 3
    FOMSAddressConverter.clear_geocode_cache()
    assert len(converter.analyze_address("서울 강남구 테헤란로 1")) == 4

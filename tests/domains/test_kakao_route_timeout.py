"""카카오 길찾기는 무한 대기하지 않는다.

예전에는 ``calculate_route(timeout=None)`` 이 requests 에 timeout 을 넘기지 않았다. 웹 요청
(``/api/calculate_route``·시공 근처 추천)이 DB 연결을 쥔 채 카카오 응답을 끝없이 기다릴 수
있었다(2026-10-01 전체 성능 검사). 생략·None 은 기본 상한, 명시 값은 그대로 쓴다.
"""

from __future__ import annotations

import pytest
import requests

from foms.services.common import address_converter as ac


class _Resp:
    status_code = 200

    @staticmethod
    def json():
        return {"routes": [{"summary": {"distance": 1000, "duration": 120, "fare": {}},
                            "sections": []}]}


@pytest.fixture
def captured(monkeypatch):
    calls: list[dict] = []

    def _fake_get(url, **kwargs):
        calls.append(kwargs)
        return _Resp()

    monkeypatch.setattr(ac.requests, "get", _fake_get)
    monkeypatch.setattr(ac, "kakao_rest_headers", lambda: {"Authorization": "KakaoAK test"})
    return calls


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, ac.DEFAULT_ROUTE_TIMEOUT_SECONDS),
        ({"timeout": None}, ac.DEFAULT_ROUTE_TIMEOUT_SECONDS),
        ({"timeout": 3.0}, 3.0),
    ],
    ids=["omitted", "explicit-none", "explicit-value"],
)
def test_route_request_always_has_a_timeout(captured, kwargs, expected):
    converter = ac.FOMSAddressConverter()

    converter.calculate_route(37.5, 127.0, 37.6, 127.1, **kwargs)

    assert captured[-1]["timeout"] == expected
    assert 0 < ac.DEFAULT_ROUTE_TIMEOUT_SECONDS <= 30


def test_route_timeout_becomes_error_result_not_exception(monkeypatch):
    """상한에 걸리면 예외 대신 error 결과 — 호출자(근처 추천)는 직선거리로 물러난다."""

    def _timeout(url, **kwargs):
        raise requests.Timeout("slow kakao")

    monkeypatch.setattr(ac.requests, "get", _timeout)
    monkeypatch.setattr(ac, "kakao_rest_headers", lambda: {"Authorization": "KakaoAK test"})

    result = ac.FOMSAddressConverter().calculate_route(37.5, 127.0, 37.6, 127.1)

    assert result["status"] == "error"

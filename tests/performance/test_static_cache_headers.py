"""정적 자원 캐시 헤더 가드 (성능 회귀 방지).

배경: 서비스워커 + WhiteNoise가 css/js를 모두 no-cache로 두면 브라우저가 매
네비게이션마다 ~수십 개 css/js를 재검증(304)한다 → 적은 web 워커(운영 2 vCPU)에서
정적 요청 폭주 → 탭전환 지연(운영 실측 2~5초 들쭉날쭉).

수정: `_versioned_static_cache_middleware`가 버전(?v=)이 붙은 css/js에 한해 단기
max-age를 부여(버전 URL은 배포 시 바뀌므로 안전). 미버전(@import)·sw.js·manifest는
no-cache 유지(신선도/SW 컨트롤러 보호).

이 테스트는 그 동작을 고정해 회귀를 막는다. 정책: docs/guides/PERFORMANCE_GUARDRAILS.md
"""
from __future__ import annotations


def _cc(client, path: str) -> tuple[int, str]:
    resp = client.get(path)
    return resp.status_code, (resp.headers.get("Cache-Control") or "")


def test_versioned_css_gets_maxage(client) -> None:
    """?v= 가 붙은 css는 max-age 캐시(매 네비 재검증 폭주 제거)."""
    status, cc = _cc(client, "/static/css/foundation/erp-pro.css?v=test")
    assert status == 200, f"versioned css not served: {status}"
    assert "max-age" in cc, f"versioned css must be cacheable, got Cache-Control={cc!r}"
    assert "no-cache" not in cc


def test_versioned_js_gets_maxage(client) -> None:
    """?v= 가 붙은 js도 max-age 캐시."""
    status, cc = _cc(client, "/static/js/orders/erp-order-shared.js?v=test")
    assert status == 200, f"versioned js not served: {status}"
    assert "max-age" in cc, f"versioned js must be cacheable, got Cache-Control={cc!r}"


def test_unversioned_css_stays_no_cache(client) -> None:
    """버전 없는 css(@import sub-file 등)는 no-cache 유지 — 배포 신선도 보호."""
    _, cc = _cc(client, "/static/css/foundation/erp-pro.css")
    assert cc == "no-cache", f"unversioned css must revalidate, got {cc!r}"


def test_service_worker_stays_no_cache(client) -> None:
    """sw.js 컨트롤러는 항상 재검증(no-cache) — 캐시되면 SW 업데이트가 막힌다."""
    status, cc = _cc(client, "/static/sw.js")
    assert status == 200
    assert "no-cache" in cc, f"sw.js must be no-cache, got {cc!r}"

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

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ERP_PRO_CSS = ROOT / "static" / "css" / "foundation" / "erp-pro.css"
LAYOUT_HEAD = ROOT / "templates" / "partials" / "shared" / "layout_head.html"
A2HS_JS = ROOT / "static" / "js" / "foms" / "a2hs-prompt.js"
LAYOUT_SCRIPTS = ROOT / "templates" / "partials" / "shared" / "layout_scripts.html"
FOMS_P2_BUNDLE = ROOT / "templates" / "partials" / "shared" / "foms_p2_surface_bundle.html"

# @import url("...css") 또는 @import url("...css?v=..."); 그룹1=경로, 그룹2=쿼리(있으면).
_IMPORT_RE = re.compile(r"""@import\s+url\(\s*["']([^"'?]+\.css)(\?[^"']*)?["']\s*\)""", re.I)


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


def test_erp_pro_css_imports_are_all_versioned() -> None:
    """erp-pro.css의 모든 @import 자식은 ?v= 를 가져야 한다(Wave 4-B).

    미버전 @import는 운영에서 Cache-Control: no-cache라 매 full page load마다 재검증
    왕복(한국↔SG)을 만든다. ?v= 가 붙어야 app_factory 미들웨어가 max-age로 재작성한다.
    이 계약은 무버전 @import 재유입을 막는다(첫 로딩 지연 회귀 방지).
    """
    text = ERP_PRO_CSS.read_text(encoding="utf-8")
    imports = _IMPORT_RE.findall(text)
    assert imports, "erp-pro.css에서 @import를 못 찾음 — 정규식/파일 구조 확인"
    unversioned = [path for (path, query) in imports if not (query and "v=" in query)]
    assert not unversioned, (
        "erp-pro.css에 미버전 @import가 있다(no-cache 재검증 왕복=첫 로딩 지연).\n"
        "해결: 각 @import URL에 ?v=YYYYMMDD 부여(자식 편집 시 값 상향).\n"
        + "\n".join(f"  - {p}" for p in unversioned)
    )


def test_layout_head_has_cdn_preconnect() -> None:
    """CDN 3 origin preconnect로 콜드 TLS 왕복 선점(첫 로딩 지연 축소, Wave 4-B)."""
    head = LAYOUT_HEAD.read_text(encoding="utf-8")
    for origin in (
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com",
        "https://cdn.socket.io",
    ):
        assert re.search(
            r"""<link\b[^>]*\brel\s*=\s*["']preconnect["'][^>]*\bhref\s*=\s*["']"""
            + re.escape(origin)
            + r"""["']""",
            head,
            re.I,
        ), f"preconnect link 누락: {origin}"


def test_service_worker_registration_is_global_not_shell_gated() -> None:
    """SW 등록은 전 페이지(데스크톱 포함) — mobile-shell DOM 게이트 제거 정책 고정(Wave 4-B).

    데스크톱 full page load에서도 sw.js staticCacheFirst의 css/js 재검증 흡수를 받으려면
    등록 함수가 [data-erp-mobile-shell] 존재 여부로 조기 return하면 안 되고, 스크립트가
    전역(layout_scripts.html)에서 로드돼야 한다. A2HS 설치 배너 노출은 maybePrompt 내부의
    shell 게이트로 모바일 한정 유지(동작 무변경).
    """
    a2hs = A2HS_JS.read_text(encoding="utf-8")
    reg_start = a2hs.index("function registerPwaServiceWorker")
    reg_end = a2hs.index("}", a2hs.index("navigator.serviceWorker.register", reg_start))
    reg_body = a2hs[reg_start:reg_end]
    assert "data-erp-mobile-shell" not in reg_body, (
        "registerPwaServiceWorker가 여전히 mobile-shell 게이트로 막혀 있다 "
        "— 데스크톱 SW가 등록되지 않는다."
    )
    # A2HS 배너 게이트는 유지(모바일 한정 노출).
    assert 'querySelector("[data-erp-mobile-shell]")' in a2hs

    # 전역 로드: layout_scripts.html이 defer로 로드하고, 모바일 P2 번들에서는 승격 제거.
    scripts = LAYOUT_SCRIPTS.read_text(encoding="utf-8")
    assert re.search(
        r"""<script\b[^>]*a2hs-prompt\.js[^>]*\bdefer\b""", scripts, re.I | re.S
    ), "layout_scripts.html이 a2hs-prompt.js를 defer로 전역 로드하지 않는다"
    bundle = FOMS_P2_BUNDLE.read_text(encoding="utf-8")
    assert not re.search(
        r"""<script\b[^>]*a2hs-prompt\.js""", bundle, re.I | re.S
    ), "a2hs-prompt.js가 전역 승격 후에도 P2 번들에 <script>로 남아 중복 로드된다"

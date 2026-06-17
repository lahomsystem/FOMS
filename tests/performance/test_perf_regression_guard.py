"""성능 회귀 원천 차단 가드 (pre_push_smoke 게이트).

목적: 코드/기능 추가가 서버·페이지를 느리게 만드는 회귀를 머지 전에 자동 차단한다.
이 테스트는 과거 실제 장애(2026-06 견적서 배포로 모든 ERP 탭 로딩 저하, 서비스워커
networkFirst 무timeout으로 탭 무한 스피너)에서 도출됐다.
배경/정책: docs/guides/PERFORMANCE_GUARDRAILS.md

가드 항목:
  G1) 템플릿에 렌더 차단(동기) `<script src>` 신규 추가 금지 → defer/async/module 사용.
  G2) 외부 CDN 동기 `<script>` 신규 추가 금지(네트워크 stall = 렌더 차단).
  G3) 서비스워커의 network-first 류 fetch는 timeout + 캐시 폴백 필수.

신규 동기 스크립트가 정말 불가피하면 (1) 가능한 한 defer/async/lazy로 바꾸고,
(2) 그래도 동기여야 하면 아래 ALLOWLIST에 사유와 함께 추가한다.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates"
SW_FILE = ROOT / "static" / "sw.js"

# 동기 `<script src>` 태그 매칭(다중 라인 허용).
_SCRIPT_TAG = re.compile(r"<script\b[^>]*?\bsrc\s*=\s*(['\"])(.*?)\1[^>]*?>", re.I | re.S)
_FILENAME = re.compile(r"filename\s*=\s*['\"]([^'\"]+)['\"]")
_URLFOR_ENDPOINT = re.compile(r"url_for\(\s*['\"]([^'\"]+)['\"]")


def _is_render_blocking(tag: str) -> bool:
    """defer/async/type=module 이 없으면 렌더 차단(동기)."""
    if re.search(r"\bdefer\b", tag):
        return False
    if re.search(r"\basync\b", tag):
        return False
    if re.search(r"type\s*=\s*['\"]module['\"]", tag):
        return False
    return True


def _script_key(tag: str, src: str) -> str:
    """스크립트를 안정 키로 정규화(파일명/CDN 마지막 세그먼트/엔드포인트)."""
    src = src.strip()
    if src.startswith("http://") or src.startswith("https://"):
        last = src.split("?")[0].rstrip("/").split("/")[-1]
        return "cdn:" + last
    fn = _FILENAME.search(tag)
    if fn:
        return fn.group(1).split("?")[0].split("/")[-1]
    ep = _URLFOR_ENDPOINT.search(tag)
    if ep and "filename" not in tag:
        return "endpoint:" + ep.group(1)
    # 정적 경로 직접 지정 등
    return src.split("?")[0].split("/")[-1]


def _collect_sync_scripts() -> dict[str, list[str]]:
    """현재 템플릿의 동기 스크립트 → {key: [상대경로...]} ."""
    found: dict[str, list[str]] = {}
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in _SCRIPT_TAG.finditer(text):
            tag = m.group(0)
            if not _is_render_blocking(tag):
                continue
            key = _script_key(tag, m.group(2))
            found.setdefault(key, []).append(str(path.relative_to(ROOT)).replace("\\", "/"))
    return found


# --- 승인된 동기 스크립트 baseline (2026-06-16 기준) ---------------------------
# 신규 항목 추가는 "defer/async/lazy로 불가능함"을 확인한 경우에만, 사유를 남길 것.
# 코어 라이브러리/레이아웃 부트스트랩 등 파싱 시점 전역 의존이 있는 것만 동기 허용.
SYNC_SCRIPT_ALLOWLIST: frozenset[str] = frozenset({
    # 외부 코어 라이브러리(레이아웃/지도/실시간) — 인라인 코드가 파싱시점 의존
    "cdn:bootstrap.bundle.min.js",
    "cdn:flatpickr",
    "cdn:ko.js",
    "cdn:leaflet.js",
    "cdn:socket.io.min.js",
    # 라우트로 서빙되는 채팅 스크립트
    "endpoint:channel_chat_pages.chat_scripts_js",
    # 로컬 공용/코어 (전역 함수 정의·파싱시점 의존)
    "attachment-preview-zoom.js",
    "column-resizer.js",
    "common_utils.js",
    "composition.js",
    "dashboard-columns.js",
    "dashboard.js",
    "drawing-handoff.js",
    "erp-order-shared.js",
    "estimate-lifecycle.js",
    "image-export.js",
    "layout-sync-wiring.js",
    "manual-rows.js",
    "mobile.js",
    "order-detail-fragment.js",
    "photo-capture.js",
    "pricing-core.js",
    "primary-form.js",
    "rum-baseline.js",
    "script.js",
    "shared.js",
    "spec-width-eval.js",
    "theme.js",
    "unsaved-exit-guard.js",
    "upload-progress.js",
    "visual-viewport.js",
})

# 외부 CDN 동기 허용(네트워크 stall 위험을 알고도 코어라 유지). 신규 CDN 동기 금지.
CDN_SYNC_ALLOWLIST: frozenset[str] = frozenset({
    "cdn:bootstrap.bundle.min.js",
    "cdn:flatpickr",
    "cdn:ko.js",
    "cdn:leaflet.js",
    "cdn:socket.io.min.js",
})


def test_no_new_render_blocking_scripts() -> None:
    """G1: 템플릿에 baseline 밖 렌더 차단 스크립트가 추가되면 실패."""
    sync = _collect_sync_scripts()
    violations = {k: v for k, v in sync.items() if k not in SYNC_SCRIPT_ALLOWLIST}
    assert not violations, (
        "렌더 차단(동기) <script src> 신규 추가 감지 — 서버 응답이 빨라도 탭 로딩이 느려진다.\n"
        "해결: defer/async 부여 또는 사용 시점 lazy 로드. 정말 동기여야 하면 "
        "tests/performance/test_perf_regression_guard.py 의 SYNC_SCRIPT_ALLOWLIST에 사유와 함께 추가.\n"
        "정책: docs/guides/PERFORMANCE_GUARDRAILS.md\n"
        + "\n".join(f"  - {k}  ({', '.join(sorted(set(v)))})" for k, v in sorted(violations.items()))
    )


def test_no_new_external_cdn_sync_scripts() -> None:
    """G2: 외부 CDN 동기 스크립트 신규 추가 금지(네트워크 stall=렌더 차단)."""
    sync = _collect_sync_scripts()
    cdn = {k: v for k, v in sync.items() if k.startswith("cdn:")}
    violations = {k: v for k, v in cdn.items() if k not in CDN_SYNC_ALLOWLIST}
    assert not violations, (
        "외부 CDN 동기 <script> 신규 추가 감지 — CDN 지연 시 페이지 전체가 멈춘다.\n"
        "해결: defer 부여, 또는 사용 시점 동적 로드(html2canvas의 _ensureHtml2canvas 패턴), "
        "또는 self-host. 정책: docs/guides/PERFORMANCE_GUARDRAILS.md\n"
        + "\n".join(f"  - {k}  ({', '.join(sorted(set(v)))})" for k, v in sorted(violations.items()))
    )


def test_service_worker_networkfirst_has_timeout() -> None:
    """G3: 서비스워커 network-first에 timeout 가드가 있어야 한다(무한 스피너 방지)."""
    if not SW_FILE.exists():
        return  # SW 미존재 환경은 스킵
    sw = SW_FILE.read_text(encoding="utf-8", errors="ignore")
    if "networkFirst" not in sw:
        return  # network-first 전략 미사용이면 무관
    assert "NETWORK_FIRST_TIMEOUT_MS" in sw and "setTimeout" in sw, (
        "서비스워커가 networkFirst를 쓰는데 timeout 가드(NETWORK_FIRST_TIMEOUT_MS)가 없다.\n"
        "network fetch가 지연되면 respondWith가 미해결되어 탭 로딩 스피너가 무한 회전한다.\n"
        "해결: network fetch를 timeout과 경주시켜 느리면 캐시본으로 폴백. "
        "정책: docs/guides/PERFORMANCE_GUARDRAILS.md"
    )

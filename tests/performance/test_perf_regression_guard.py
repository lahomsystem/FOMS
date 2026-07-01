"""성능 회귀 원천 차단 가드 (pre_push_smoke 게이트).

목적: 코드/기능 추가가 서버·페이지를 느리게 만드는 회귀를 머지 전에 자동 차단한다.
이 테스트는 과거 실제 장애(2026-06 견적서 배포로 모든 ERP 탭 로딩 저하, 서비스워커
networkFirst 무timeout으로 탭 무한 스피너)에서 도출됐다.
배경/정책: docs/guides/PERFORMANCE_GUARDRAILS.md

가드 항목:
  G1) 템플릿에 렌더 차단(동기) `<script src>` 신규 추가 금지 → defer/async/module 사용.
  G2) 외부 CDN 동기 `<script>` 신규 추가 금지(네트워크 stall = 렌더 차단).
  G3) 서비스워커의 network-first 류 fetch는 timeout + 캐시 폴백 필수.
  G4) ERP shell fragment 안에서 재실행되는 JS의 전역 listener 중복 바인딩 금지.

신규 동기 스크립트가 정말 불가피하면 (1) 가능한 한 defer/async/lazy로 바꾸고,
(2) 그래도 동기여야 하면 아래 ALLOWLIST에 사유와 함께 추가한다.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates"
SW_FILE = ROOT / "static" / "sw.js"
PERF_SCAN = ROOT / "tools" / "perf" / "perf_scan.py"

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
# FOUC 방지: paint 전 data-theme/data-bs-theme 부트스트랩 — defer 불가.
SYNC_SCRIPT_ALLOWLIST: frozenset[str] = frozenset()

# 외부 CDN 동기 허용(네트워크 stall 위험을 알고도 코어라 유지). 신규 CDN 동기 금지.
CDN_SYNC_ALLOWLIST: frozenset[str] = frozenset()

# Existing replayed shell scripts that predate the singleton-listener guard.
# Keep the expected count fixed: a new global listener in one of these files must
# either refactor to a singleton guard or intentionally update this baseline.
FRAGMENT_REPLAYED_GLOBAL_LISTENER_BASELINE: dict[str, int] = {
    "js/foms/a2hs-prompt.js": 1,
    "js/foms/alpine-store.js": 2,
    "js/foms/bottom-nav-shell.js": 4,
    "js/foms/haptic.js": 1,
    "js/foms/kv-copy.js": 1,
    "js/foms/lightbox.js": 1,
    "js/foms/mobile-queue-focus.js": 1,
    "js/foms/mobile-queue-scroll.js": 1,
    "js/foms/search.js": 2,
    "js/foms/swipe-actions.js": 1,
    "js/foms/sync.js": 2,
    "js/runtime/erp-mobile-shell.js": 2,
}


def _load_perf_scan_module():
    spec = importlib.util.spec_from_file_location("foms_perf_scan", PERF_SCAN)
    assert spec and spec.loader, f"cannot import {PERF_SCAN}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


def test_service_worker_does_not_force_static_no_cache_fetches() -> None:
    """Static assets must not be force-revalidated by SW fetch options."""
    sw = SW_FILE.read_text(encoding="utf-8", errors="ignore")
    assert "fetch(request, { cache:" not in sw
    assert "staticCacheFirst(req, STATIC_CACHE)" in sw


def test_fragment_replayed_global_listeners_are_guarded_or_frozen() -> None:
    """G4: fragment-replayed JS must not accumulate global listeners on tab swaps."""
    perf_scan = _load_perf_scan_module()
    replayed = perf_scan._collect_fragment_replayed_js_paths()
    assert "js/foms/erp-attachment-preview-open.js" in replayed

    violations: list[str] = []
    for js_rel in sorted(replayed):
        if js_rel.startswith("js/vendor/"):
            continue
        path = ROOT / "static" / js_rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        listener_count = len(perf_scan._GLOBAL_REPLAYED_EVENT_RE.findall(text))
        if listener_count == 0 or perf_scan._has_global_init_guard(text):
            continue
        expected = FRAGMENT_REPLAYED_GLOBAL_LISTENER_BASELINE.get(js_rel)
        if expected != listener_count:
            violations.append(f"{js_rel}: expected={expected} actual={listener_count}")

    assert not violations, (
        "fragment swap에서 재실행되는 JS에 singleton guard 없는 전역 listener가 추가됐다.\n"
        "해결: window.__*_BOUND 같은 단일 초기화 가드를 추가하거나, 기존 debt면 "
        "FRAGMENT_REPLAYED_GLOBAL_LISTENER_BASELINE에 사유와 함께 고정.\n"
        + "\n".join(f"  - {v}" for v in violations)
    )

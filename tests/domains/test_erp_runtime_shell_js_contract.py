"""EPT-B6: static checks for `static/js/runtime/erp-shell.js` (no JS runtime in CI)."""

from __future__ import annotations

from pathlib import Path

import pytest

from foms.services.common import erp_navigation_contract as enc

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_SHELL = _REPO_ROOT / "static" / "js" / "runtime" / "erp-shell.js"
_LAYOUT_SCRIPTS = _REPO_ROOT / "templates" / "partials" / "shared" / "layout_scripts.html"
_SERVICE_WORKER = _REPO_ROOT / "static" / "sw.js"


@pytest.fixture(scope="module")
def runtime_shell_src() -> str:
    assert _RUNTIME_SHELL.is_file(), f"missing {_RUNTIME_SHELL}"
    return _RUNTIME_SHELL.read_text(encoding="utf-8")


def test_runtime_shell_lists_match_python_fragment_ready(runtime_shell_src: str) -> None:
    """Client FRAGMENT_READY_PATHS array must match enc.ERP_FRAGMENT_READY_PATHS order and values."""
    for path in enc.ERP_FRAGMENT_READY_PATHS:
        assert f"'{path}'" in runtime_shell_src, path


def test_runtime_shell_subordinate_fragment_patterns(runtime_shell_src: str) -> None:
    """B6: subordinate shell-swap allowlist (B5 server contract) present."""
    assert "isSubordinateShellFragmentPath" in runtime_shell_src
    assert "/erp/shipment-settings" in runtime_shell_src
    assert "/erp/drawing-workbench/" in runtime_shell_src or "drawing-workbench" in runtime_shell_src
    assert r"^\/edit\/\d+$" not in runtime_shell_src


def test_runtime_shell_excludes_map_view_prefetch(runtime_shell_src: str) -> None:
    """map_view is full-document-only; must not appear as a prefetch/swap target."""
    assert "map_view" not in runtime_shell_src


def test_runtime_shell_prefetch_warm_nav_hooks(runtime_shell_src: str) -> None:
    """B6: idle stagger, hover delegation, LRU cache, popstate restore."""
    assert "scheduleIdlePrimaryPrefetch" in runtime_shell_src
    assert "prefetchShellFragment" in runtime_shell_src
    assert "fragmentHtmlCache" in runtime_shell_src or "cachePut" in runtime_shell_src
    assert "popstate" in runtime_shell_src
    assert "fromPopState" in runtime_shell_src
    assert "scrollMemory" in runtime_shell_src


def test_runtime_shell_no_fragment_cache_mechanism_present(runtime_shell_src: str) -> None:
    """warm-cache 강제 우회 메커니즘은 유지(현재 대상 경로는 없음 — 실측은 FRESH_TTL 로 이동).

    실측은 fragment 안에 마크업만 남아(스크립트는 measurement-entry.js 가 load-once) warm-cache 가
    안전해졌다. 날짜 민감성은 NO_FRAGMENT_CACHE 가 아니라 FRESH_TTL(60s, 하트비트 50s 선행)+focus 재수혈로 커버.
    """
    assert "NO_FRAGMENT_CACHE_PATHS" in runtime_shell_src
    assert "isFragmentCacheable" in runtime_shell_src
    assert "window.FOMS_ERP_SHELL.isFragmentCacheable" in runtime_shell_src


def test_runtime_shell_measurement_uses_fresh_ttl_not_no_cache(runtime_shell_src: str) -> None:
    """실측은 date-sensitive → NO_CACHE(매 스왑 refetch, 5.8s) 대신 FRESH_TTL(짧은 warm + 재검증)."""
    fresh_block = runtime_shell_src.split("FRESH_TTL_PATHS")[1].split("]")[0]
    assert "'/erp/measurement'" in fresh_block, "measurement 는 FRESH_TTL_PATHS 에 있어야 함"
    no_cache_block = runtime_shell_src.split("NO_FRAGMENT_CACHE_PATHS")[1].split("]")[0]
    assert "'/erp/measurement'" not in no_cache_block, "measurement 는 더 이상 NO_FRAGMENT_CACHE_PATHS 가 아님"


def test_runtime_shell_dashboard_fresh_ttl_and_focus_revalidate(runtime_shell_src: str) -> None:
    """Wave 4-A: home is mutation-sensitive → warm TTL + stale-while-refresh on focus/bfcache.

    복귀(visibilitychange/pageshow)는 캐시를 **삭제**하지 않고 force prefetch 로 **재수혈**한다 —
    삭제하면 복귀 직후 첫 클릭이 싱가포르 왕복을 그대로 맞기 때문. FRESH_TTL 은 60s(하트비트 50s 선행).
    """
    assert "FRESH_TTL_PATHS" in runtime_shell_src
    assert "'/erp/dashboard'" in runtime_shell_src
    assert "cacheTtlForKey" in runtime_shell_src
    assert "visibilitychange" in runtime_shell_src
    assert "e.persisted" in runtime_shell_src
    # A2: 복귀 경로는 삭제(invalidate)가 아니라 재수혈(refresh) 함수를 쓴다.
    #     (핸들러 등록부만 검사 — 주석 언급이 아니라 실제 addEventListener 블록.)
    assert "refreshFreshTtlSurfaces" in runtime_shell_src, "복귀 재수혈 함수 존재"
    vis_block = runtime_shell_src.split("addEventListener('visibilitychange'")[1].split("});")[0]
    assert "refreshFreshTtlSurfaces" in vis_block, "visibilitychange 는 refresh(재수혈)를 호출"
    assert "invalidateFreshTtlSurfaces" not in vis_block, "visibilitychange 에서 invalidate 금지"
    pageshow_block = runtime_shell_src.split("addEventListener('pageshow'")[1].split("});")[0]
    assert "refreshFreshTtlSurfaces" in pageshow_block, "pageshow(persisted) 도 refresh"
    assert "invalidateFreshTtlSurfaces" not in pageshow_block, "pageshow 에서 invalidate 금지"
    # FRESH_TTL 60s 상향(하트비트 선행으로 사실상 영구 웜).
    assert "var FRESH_TTL_MS = 60 * 1000;" in runtime_shell_src, "FRESH_TTL 은 60s"


def test_runtime_shell_heartbeat_reprefetch(runtime_shell_src: str) -> None:
    """Wave 4-A A1: 하트비트가 캐시 만료 전에 재프리페치해 warm 캐시 약효를 유지한다.

    fresh 는 FRESH_TTL(60s) 앞선 50s, primary 는 CACHE_TTL(5분=300s) 앞선 240s 주기로,
    visible + 최근 활동일 때만 돈다(방치 탭 자동 정지). prefetch 는 force 옵션으로 warm-hit 를 덮어쓴다.
    """
    # 상수 존재 + 관계(하트비트가 각 TTL 보다 앞선다).
    assert "HEARTBEAT_PRIMARY_MS = 240 * 1000" in runtime_shell_src
    assert "HEARTBEAT_FRESH_MS = 50 * 1000" in runtime_shell_src
    assert "HEARTBEAT_IDLE_CUTOFF_MS" in runtime_shell_src
    assert "FRESH_TTL_MS = 60 * 1000" in runtime_shell_src
    assert 50 * 1000 < 60 * 1000, "HEARTBEAT_FRESH_MS < FRESH_TTL_MS"
    assert 240 * 1000 < 5 * 60 * 1000, "HEARTBEAT_PRIMARY_MS < CACHE_TTL_MS"
    # visible + activity 게이트.
    assert "document.visibilityState === 'visible'" in runtime_shell_src
    assert "HEARTBEAT_IDLE_CUTOFF_MS" in runtime_shell_src.split("heartbeatActive")[1]
    assert "lastActivityTs" in runtime_shell_src
    # 활동 추적 리스너(가벼운 것들).
    for evt in ("pointerdown", "keydown", "wheel", "touchstart"):
        assert evt in runtime_shell_src, evt
    # 주기 타이머 2개(setInterval).
    assert runtime_shell_src.count("setInterval") >= 2, "primary+fresh 하트비트 타이머 2개"
    # prefetch force 옵션.
    assert "function prefetchShellFragment(url, opts)" in runtime_shell_src
    assert "opts && opts.force" in runtime_shell_src
    assert "{ force: true }" in runtime_shell_src


def test_runtime_shell_fragment_loading_overlay(runtime_shell_src: str) -> None:
    """UX: network fragment fetch shows loading overlay (not for cache-only swap)."""
    assert "setShellFragmentLoading" in runtime_shell_src
    assert "beginShellNavigationPending" in runtime_shell_src
    assert "foms-erp-shell-loading-overlay" in runtime_shell_src
    assert "window.FOMS_ERP_SHELL.beginShellNavigationPending" in runtime_shell_src


def test_runtime_shell_push_state_before_fragment_scripts(runtime_shell_src: str) -> None:
    """Inline page scripts read window.location.search; history must update before activateScripts."""
    navigate_fn = runtime_shell_src.split("function navigateByShell(url, opts)")[1]
    fetch_branch = navigate_fn.split("return fetchFragment(canonical)")[1].split(".catch(function ()")[0]
    assert "commitShellHistory(finalUrl)" in fetch_branch
    assert fetch_branch.index("commitShellHistory(finalUrl)") < fetch_branch.index("applyFragmentToMain")
    cache_branch = navigate_fn.split("if (!opts.bypassCache && isFragmentCacheable")[1].split("setShellFragmentLoading(true)")[0]
    assert "commitShellHistory(canonical)" in cache_branch
    assert cache_branch.index("commitShellHistory(canonical)") < cache_branch.index("applyFragmentToMain")


def test_runtime_shell_uses_final_fetch_url_for_redirected_fragments(runtime_shell_src: str) -> None:
    """Dashboard search can 302 to history; shell state must follow the final canonical URL."""
    assert "canonicalFromFetchResponse" in runtime_shell_src
    assert "X-FOMS-Canonical-URL" in runtime_shell_src
    assert "r.url" in runtime_shell_src
    assert "finalUrl.pathname + finalUrl.search + finalUrl.hash" in runtime_shell_src
    assert "unsafe redirected fragment url" in runtime_shell_src


def test_runtime_shell_script_url_is_versioned_for_service_worker_cache() -> None:
    """ERP shell must cache-bust old SW Cache API entries after fragment-script fixes."""
    layout_src = _LAYOUT_SCRIPTS.read_text(encoding="utf-8")
    assert "js/runtime/erp-shell.js') }}?v=" in layout_src
    assert "js/runtime/upload-progress.js') }}?v=" in layout_src


def test_service_worker_cache_version_purges_stale_erp_shell() -> None:
    """SW cache namespace bump removes old unversioned erp-shell.js entries on activate."""
    sw_src = _SERVICE_WORKER.read_text(encoding="utf-8")
    assert 'CACHE_VERSION = "foms-p2-v7"' in sw_src

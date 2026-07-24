"""SHELL-01: static/simulation checks for erp-shell.js rapid A→B nav race guard.

CI has no JS runtime, so these are static-source contracts (same style as
test_erp_runtime_shell_js_contract.py). They pin the invariants that make a late
response from a superseded navigation commit 0 (the newer surface B is preserved):

  * every real navigation bumps a generation token and aborts the previous nav's
    in-flight fetch (AbortController),
  * the abort signal is threaded to fetch() via a one-shot channel that prefetch/
    heartbeat callers do not inherit,
  * every history/DOM/loading mutation is gated on isCurrent() (own generation is
    still the newest) — cache-hit, network, and the catch-fallback paths alike,
  * a superseded nav never falls back to a hard page load (that would clobber B),
  * the guard adds no new listener, so fragment re-exec stays idempotent (G4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_SHELL = _REPO_ROOT / "static" / "js" / "runtime" / "erp-shell.js"


@pytest.fixture(scope="module")
def runtime_shell_src() -> str:
    assert _RUNTIME_SHELL.is_file(), f"missing {_RUNTIME_SHELL}"
    return _RUNTIME_SHELL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def navigate_body(runtime_shell_src: str) -> str:
    """navigateByShell body up to the next top-level function."""
    return runtime_shell_src.split("function navigateByShell(url, opts)")[1].split(
        "\n  /**"
    )[0]


def test_generation_token_present(runtime_shell_src: str, navigate_body: str) -> None:
    """A monotonic generation is bumped once per navigation and captured per-call."""
    assert "var navGeneration = 0;" in runtime_shell_src
    assert "var myGeneration = ++navGeneration;" in navigate_body
    assert "function isCurrent()" in navigate_body
    assert "return myGeneration === navGeneration;" in navigate_body


def test_abort_controller_present(runtime_shell_src: str, navigate_body: str) -> None:
    """Each nav aborts the previous nav's in-flight fetch (feature-detected)."""
    assert "var navAbortController = null;" in runtime_shell_src
    assert "navAbortController.abort();" in navigate_body
    assert "typeof AbortController !== 'undefined'" in navigate_body
    assert "var mySignal = navAbortController ? navAbortController.signal : null;" in navigate_body


def test_abort_signal_threaded_to_fetch_via_oneshot_channel(runtime_shell_src: str) -> None:
    """The signal reaches fetch() through a one-shot channel consumed in fetchFragment.

    prefetch/heartbeat call fetchFragment without setting navFetchSignal, so they must
    NOT inherit a nav's abort lifecycle. navigateByShell sets it immediately before its
    own fetch; fetchFragment reads+clears it at the top (same synchronous tick).
    """
    assert "var navFetchSignal = null;" in runtime_shell_src
    fetch_block = runtime_shell_src.split("function fetchFragment(canonical)")[1].split(
        "function navigateByShell"
    )[0]
    assert "var navSignal = navFetchSignal;" in fetch_block
    assert "navFetchSignal = null;" in fetch_block
    assert "signal: navSignal || undefined," in fetch_block
    # consume happens before the inflight-dedup early return (no leak to next caller).
    assert fetch_block.index("navFetchSignal = null;") < fetch_block.index("if (inflightFetches[key])")
    # nav sets the channel right before its own fetch.
    nav_net = runtime_shell_src.split("setShellFragmentLoading(true);\n    navFetchSignal = mySignal;")
    assert len(nav_net) == 2, "navigateByShell must set navFetchSignal = mySignal before fetchFragment"
    # prefetch never sets the channel.
    prefetch_block = runtime_shell_src.split("function prefetchShellFragment(url, opts)")[1].split(
        "function scheduleIdlePrimaryPrefetch"
    )[0]
    assert "navFetchSignal" not in prefetch_block


def test_cache_hit_commit_is_generation_gated(navigate_body: str) -> None:
    """Cache-hit swap re-checks generation after (async) style preload before committing."""
    cache_branch = navigate_body.split("var cached = cacheGet(destKey);")[1].split(
        "setShellFragmentLoading(true);"
    )[0]
    assert "if (!isCurrent())" in cache_branch, "cache-hit commit must be gated"
    assert cache_branch.index("if (!isCurrent())") < cache_branch.index("commitShellHistory(canonical)")
    assert cache_branch.index("if (!isCurrent())") < cache_branch.index("applyFragmentToMain")


def test_network_commit_is_generation_gated(navigate_body: str) -> None:
    """Late network response is dropped (commit 0) unless still the newest nav.

    Gate appears twice: an early-out on response arrival, and again after style
    preload immediately before history+DOM commit.
    """
    net_branch = navigate_body.split("return fetchFragment(canonical)")[1].split(
        ".catch(function ()"
    )[0]
    assert net_branch.count("if (!isCurrent())") >= 2, "gate on arrival and before commit"
    assert net_branch.index("if (!isCurrent())") < net_branch.index("commitShellHistory(finalUrl)")
    assert net_branch.index("commitShellHistory(finalUrl)") < net_branch.index("applyFragmentToMain")


def test_superseded_nav_does_not_hard_navigate(navigate_body: str) -> None:
    """A superseded/aborted nav must NOT fall back to a hard page load (would clobber B)."""
    catch_block = navigate_body.split(".catch(function ()")[1].split(".then(function ()")[0]
    assert "if (!isCurrent())" in catch_block
    assert catch_block.index("if (!isCurrent())") < catch_block.index("window.location.href"), (
        "the !isCurrent() early-return must precede the hard-nav fallback"
    )
    # the trailing loading-cleanup .then is likewise gated so a stale nav can't
    # hide an overlay the newer nav is showing.
    tail_then = navigate_body.split(".catch(function ()")[1].split(".then(function ()")[1]
    assert "if (!isCurrent())" in tail_then


def test_guard_adds_no_listener_stays_idempotent(navigate_body: str) -> None:
    """G4: the commit guard only *tightens* commits; it registers no new listener."""
    assert "addEventListener" not in navigate_body

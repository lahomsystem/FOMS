"""엔트리 체인(실측·주문 대시보드)은 번들을 한꺼번에 넣고 순서대로 실행한다 (원장 P2-4 ①).

왜: 예전에는 파일 하나의 onload 를 기다린 뒤 다음 파일을 넣어 왕복이 파일 수만큼 줄을 섰다
(스테이징 콜드 실측 12개 약 1.3초, 대시보드 9개 약 1.0초). 동적 script 를 async=false 로 넣으면
다운로드는 병렬이고 실행은 넣은 순서대로다(HTML 표준의 "넣은 순서대로 실행" 목록).

문자열 존재가 아니라 동작을 본다: 가짜 DOM 에서 엔트리를 node 로 돌려
  - 첫 onload 전에 CHAIN 전부가 들어갔는지(병렬), 전부 async=false 인지, 넣은 순서가 CHAIN 순서인지
  - 뒤에서부터 끝나도 마지막 파일이 끝나기 전에는 완료 표식이 서지 않는지
  - 탭 스왑·조각 재실행 때 다시 넣지 않는지(기존 singleton 동작)
  - 받는 중 스왑해도 겹쳐 넣지 않는지, 하나가 실패한 뒤 재시도는 실패한 파일만 다시 넣는지
음성 대조군: 같은 검사기로 옛 순차 루프·async=true·재사용 가드 제거본을 돌려 각각 잡히는지 본다.

출고(shipment-entry.js)는 아직 순차다: 엔트리 핀을 올리려면 출고 scripts 파샬을 고쳐야 하는데 그 파샬은
<script src> 2개라 perf_scan fragment-multi-script 가 막는다(구조 부채, 원장 P2-4 남은 일).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node 없음")

SWAP = "foms:erp-shell-fragment-swapped"

# name: (경로, 완료 표식, 진행 중 Promise, 조각 안에서 재실행되는가)
ENTRIES = {
    "measurement": (
        "static/js/measurement/measurement-entry.js",
        "__fomsMeasurementBundleLoaded",
        "__fomsMeasurementBundlePromise",
        True,
    ),
    "dashboard": (
        "static/js/orders/erp-dashboard-entry.js",
        "__fomsErpDashboardBundleLoaded",
        "__fomsErpDashboardBundlePromise",
        False,
    ),
}

# 가짜 DOM: head.appendChild 로 들어온 script 를 기록하고, onload/onerror 는 드라이버가 직접 부른다.
HARNESS = r"""
process.on('unhandledRejection', function () {});
const out = { log: [] };
const inserted = [];
const listeners = {};
const head = {
  appendChild(el) { el.parentNode = head; inserted.push(el); return el; },
  removeChild(el) { el.parentNode = null; return el; },
};
global.window = global;
global.document = {
  readyState: 'interactive',
  head: head,
  createElement() { return { tagName: 'SCRIPT', async: true, src: '', onload: null, onerror: null, parentNode: null }; },
  querySelector() { return {}; },
  getElementById() { return {}; },
  addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
};
global.console = { error() {}, log() {}, warn() {} };
const tick = () => new Promise((r) => setTimeout(r, 0));
const runEntry = () => { (0, eval)(SRC); };
const swap = () => { (listeners[SWAP] || []).slice().forEach((fn) => fn()); };
"""

DRIVERS = {
    # 정상 경로: 병렬 삽입 → 뒤에서부터 완료 → 스왑·재실행
    "happy": r"""
(async () => {
  runEntry();
  out.before_any_load = inserted.length;
  out.async_flags = inserted.map((s) => s.async);
  out.srcs = inserted.map((s) => s.src);
  const n = inserted.length;
  for (let i = n - 1; i >= 1; i--) { inserted[i].onload(); }
  await tick();
  out.flag_before_first_done = !!window[FLAG];
  inserted[0].onload();
  await tick();
  out.flag_after_all = !!window[FLAG];
  out.promise_after_all = window[PROMISE] === null || window[PROMISE] === undefined;
  swap(); await tick();
  out.after_swap = inserted.length;
  runEntry(); await tick();
  out.after_replay = inserted.length;
  out.swap_listeners = (listeners[SWAP] || []).length;
  process.stdout.write(JSON.stringify(out));
})();
""",
    # 받는 중 스왑 → 겹쳐 넣지 않는다. 하나 실패 → 재시도는 실패한 파일만.
    "fail_retry": r"""
(async () => {
  runEntry();
  const n = inserted.length;
  swap(); await tick();
  out.inflight_swap = inserted.length - n;
  const failed = inserted[1] || inserted[0];
  for (let i = 0; i < n; i++) { if (inserted[i] !== failed) inserted[i].onload(); }
  failed.onerror();
  await tick();
  out.flag_after_fail = !!window[FLAG];
  out.failed_detached = failed.parentNode === null;
  swap(); await tick();
  const again = inserted.slice(n);
  out.retry_srcs = again.map((s) => s.src);
  out.failed_src = failed.src;
  again.forEach((s) => s.onload());
  await tick();
  out.flag_after_retry = !!window[FLAG];
  process.stdout.write(JSON.stringify(out));
})();
""",
}


def _run(source: str, flag: str, promise: str, scenario: str) -> dict:
    script = (
        f"const SRC = {json.dumps(source)};\nconst FLAG = {json.dumps(flag)};\n"
        f"const PROMISE = {json.dumps(promise)};\nconst SWAP = {json.dumps(SWAP)};\n"
        + HARNESS
        + DRIVERS[scenario]
    )
    proc = subprocess.run(
        [NODE, "-"], input=script, capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=str(ROOT)
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def _chain_paths(source: str) -> list[str]:
    block = source[source.index("var CHAIN = [") : source.index("];", source.index("var CHAIN = ["))]
    return [m.split("?")[0] for m in re.findall(r"'(/static/[^']+)'", block)]


def _problems(name: str, source: str) -> list[str]:
    """정상 경로 + 실패 재시도 두 시나리오에서 어긋난 점을 모두 모은다(빈 목록 = 계약 충족)."""
    _path, flag, promise, replayed = ENTRIES[name]
    chain = _chain_paths(source)
    probs: list[str] = []

    h = _run(source, flag, promise, "happy")
    if h["before_any_load"] != len(chain):
        probs.append(f"parallel: 첫 onload 전 삽입 {h['before_any_load']}/{len(chain)}")
    if any(flag_ is not False for flag_ in h["async_flags"]):
        probs.append(f"async=false 아님: {h['async_flags']}")
    if [s.split("?")[0] for s in h["srcs"]] != chain[: len(h["srcs"])]:
        probs.append("order: 넣은 순서가 CHAIN 순서와 다르다")
    if h["flag_before_first_done"]:
        probs.append("done-early: 첫 파일이 끝나기 전에 완료 표식이 섰다")
    if not h["flag_after_all"] or not h["promise_after_all"]:
        probs.append("done-missing: 전부 끝났는데 완료 표식/Promise 정리가 안 됐다")
    if h["after_swap"] != h["before_any_load"] or h["after_replay"] != h["before_any_load"]:
        probs.append(f"reload: 스왑·재실행 뒤 다시 넣었다({h['after_swap']}, {h['after_replay']})")
    if replayed and h["swap_listeners"] != 1:
        probs.append(f"listener: 재실행 뒤 스왑 리스너 {h['swap_listeners']}개(G4)")

    f = _run(source, flag, promise, "fail_retry")
    if f["inflight_swap"] != 0:
        probs.append(f"inflight: 받는 중 스왑에 {f['inflight_swap']}개를 겹쳐 넣었다")
    if f["flag_after_fail"]:
        probs.append("fail-flag: 실패했는데 완료 표식이 섰다")
    if f["retry_srcs"] != [f["failed_src"]]:
        probs.append(f"retry: 실패한 파일만 다시 넣어야 하는데 {len(f['retry_srcs'])}개를 넣었다")
    if not f["flag_after_retry"]:
        probs.append("retry-done: 재시도 뒤 완료 표식이 없다")
    return probs


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _mutate(source: str, old: str, new: str) -> str:
    assert source.count(old) == 1, f"음성 대조군 변형 지점이 없다: {old[:60]!r}"
    return source.replace(old, new)


@pytest.mark.parametrize("name", sorted(ENTRIES))
def test_entry_chain_loads_in_parallel_and_executes_in_order(name: str) -> None:
    source = _read(ENTRIES[name][0])
    assert _problems(name, source) == []


@pytest.mark.parametrize("name", sorted(ENTRIES))
def test_negative_control_sequential_loop_is_caught(name: str) -> None:
    """옛 순차 루프(파일마다 await)로 되돌리면 병렬 검사에 걸린다."""
    source = _mutate(
        _read(ENTRIES[name][0]),
        "Promise.all(CHAIN.map(loadScript)).then(function () {",
        "(async function () { for (var i = 0; i < CHAIN.length; i++) { await loadScript(CHAIN[i]); } })()"
        ".then(function () {",
    )
    probs = _problems(name, source)
    assert any(p.startswith("parallel:") for p in probs), probs


@pytest.mark.parametrize("name", sorted(ENTRIES))
def test_negative_control_async_true_is_caught(name: str) -> None:
    """async=true 로 넣으면 받는 대로 실행돼 순서가 깨진다 — 검사에 걸린다."""
    source = _mutate(_read(ENTRIES[name][0]), "s.async = false;", "s.async = true;")
    probs = _problems(name, source)
    assert any(p.startswith("async=false") for p in probs), probs


@pytest.mark.parametrize("name", sorted(ENTRIES))
def test_negative_control_reinsert_on_retry_is_caught(name: str) -> None:
    """파일별 재사용 가드를 빼면 재시도 때 이미 실행된 파일까지 다시 넣는다 — 검사에 걸린다."""
    source = _mutate(
        _read(ENTRIES[name][0]),
        "    if (loads[src]) {\n      return loads[src];\n    }\n",
        "",
    )
    probs = _problems(name, source)
    assert any(p.startswith("retry:") for p in probs), probs

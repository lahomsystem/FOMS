"""도면 마법사 — 확대해도 또렷하게(zoom-sharp.js, node 로 돌린다).

사용자 지시(2026-10-28): '150% 키우면 흐린거 고쳐'. 배율은 .dws-stage 의 CSS transform 이라 Konva 캔버스가
처음 잡은 devicePixelRatio 해상도 그대로 늘어나 흐려졌다(병렬 조사 총괄 판정 2번). 배율이 바뀌고 0.15초 쉬면 레이어 캔버스
pixelRatio 를 devicePixelRatio × 배율(0.25 단위로 올림, 한도 3, 100% 이하는 그대로)로 바꾸고 바로 다시 그린다.
모니터를 옮겨 devicePixelRatio 가 바뀌어도 다시 맞춘다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS_DIR = ROOT / "static/js/drawing"
JS = (JS_DIR / "wizard.js").read_text(encoding="utf-8")
TPL = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")

RUNNER = r"""
const file = process.argv[1];
let timers = [];
const mqs = [];
global.setTimeout = (fn, ms) => { timers.push({ fn, ms }); return timers.length; };
global.clearTimeout = (id) => { if (id && timers[id - 1]) { timers[id - 1].fn = null; } };
global.window = { devicePixelRatio: 1, matchMedia(q) {
  const mq = { q, fns: [], addEventListener(t, f) { this.fns.push(f); }, removeEventListener(t, f) { this.fns = this.fns.filter(x => x !== f); } };
  mqs.push(mq); return mq; } };
require(file);
const Z = window.FomsZoomSharp;
function canvas() { return { pr: 1, sets: 0, getPixelRatio() { return this.pr; }, setPixelRatio(v) { this.pr = v; this.sets++; } }; }
const layer = { cv: canvas(), draws: 0, getCanvas() { return this.cv; }, draw() { this.draws++; } };
const stage = { bufferCanvas: canvas(), getLayers() { return [layer]; } };
function flush() {
  const live = timers.filter(t => t.fn), waits = live.map(t => t.ms);
  timers = []; live.forEach(t => t.fn());
  return { pr: layer.cv.pr, sets: layer.cv.sets, draws: layer.draws, buffer: stage.bufferCanvas.pr, waits };
}
const h = Z.attach(stage), out = {};
h.zoom(0.6); out.under = flush();
h.zoom(1.2); h.zoom(1.5); h.zoom(2); out.burst = flush();
h.zoom(4); out.cap = flush();
h.zoom(1); out.back = flush();
window.devicePixelRatio = 2; mqs[0].fns.slice().forEach(f => f());
out.dpr = Object.assign(flush(), { queries: mqs.map(m => m.q), left: mqs[0].fns.length, watching: mqs[1].fns.length });
out.target = [[1.1, 1], [0.5, 2], [1, 3.5], [2, 3.5], [1.5, 1.25], [null, null], [2, 0]].map(a => Z.target(a[0], a[1]));
out.consts = [Z.CAP, Z.WAIT];
process.stdout.write(JSON.stringify(out));
"""


def _node() -> str:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


def _run() -> dict:
    proc = subprocess.run([_node(), "-e", RUNNER, str(JS_DIR / "zoom-sharp.js")], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_node_check_zoom_sharp():
    proc = subprocess.run([_node(), "--check", str(JS_DIR / "zoom-sharp.js")], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr


def test_resolution_follows_zoom_after_a_pause_and_gives_memory_back():
    out = _run()
    assert out["consts"] == [3, 150]
    assert out["under"] == {"pr": 1, "sets": 0, "draws": 0, "buffer": 1, "waits": [150]}   # 100% 이하는 그대로 — 다시 그리지 않는다
    assert out["burst"] == {"pr": 2, "sets": 1, "draws": 1, "buffer": 2, "waits": [150]}   # 120 · 150 · 200% 를 빠르게 돌려도 한 번만
    assert out["cap"]["pr"] == 3 and out["cap"]["buffer"] == 3                            # 400% 도 한도 3(캔버스 약 55MB)
    assert out["back"]["pr"] == 1 and out["back"]["draws"] == 3                           # 100% 로 돌아오면 메모리를 돌려준다


def test_monitor_change_reapplies_with_the_new_device_pixel_ratio():
    out = _run()["dpr"]
    assert out["pr"] == 2 and out["buffer"] == 2 and out["draws"] == 4                    # 같은 100% 라도 새 화면 해상도로 다시 그린다
    assert out["queries"] == ["(resolution: 1dppx)", "(resolution: 2dppx)"]
    assert out["left"] == 0 and out["watching"] == 1                                       # 옛 조건은 풀고 새 값으로 다시 건다


def test_target_rounds_up_caps_and_never_goes_below_the_screen():
    assert _run()["target"] == [1.25, 2, 3.5, 3.5, 2, 1, 2]


def test_wizard_wires_zoom_sharp_into_stage_and_set_zoom():
    create = JS[JS.index("  function createKonva() {"):JS.index("    transformer = new Konva.Transformer({")]
    assert "if (window.FomsZoomSharp) { zoomSharp = window.FomsZoomSharp.attach(konvaStage); zoomSharp.zoom(zoom); }" in create
    set_zoom = JS[JS.index("  function setZoom(z) {"):JS.index("  function openLogoPopup() {")]
    assert set_zoom.rstrip().endswith("if (zoomSharp) { zoomSharp.zoom(z); }\n  }")         # 휠 · 핀치 · 단축키 · V2 배율 고르기 모두 여기로 온다
    konva = TPL.index("vendor/konva.min.js')")
    sharp = TPL.index("js/drawing/zoom-sharp.js') }}?v=20261028a")
    assert konva < TPL.index("js/drawing/image-smooth.js')") < sharp < TPL.index("js/drawing/wizard.js') }}?v=20261029b")

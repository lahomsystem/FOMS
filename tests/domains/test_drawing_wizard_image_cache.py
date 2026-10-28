"""도면 마법사 — 그림 노드 이미지 캐시(wizard.js buildImage, node 로 돌린다).

스테이징 실화면(2026-10-29): 같은 그림이 한 시트에 둘(Ctrl+J 제자리 복제 사본 — 같은 key)이면 처음 열 때 한 칸이 빈 틀로 남았다.
캐시는 key 하나에 HTMLImageElement 하나를 두는데, 로드 전 두 번째 노드가 img.onload 를 덮어써 첫 노드는 끝내 그림을 못 받았다
(다른 편집으로 다시 그리기 전까지). 내보내기 PNG 도 지금 Konva 화면을 찍는다.
같은 날: 그림이 뜨기 전에 잰 예전 양식 기준을 V2 가 계속 기억해 열 때마다 % · 배치가 달랐다 → 그림이 다 뜨면 한 번 다시 그린다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIZARD = ROOT / "static/js/drawing/wizard.js"

RUNNER = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
const start = src.indexOf('var _annoImgCache = {};'), end = src.indexOf('function flippedImageSource', start);
if (start < 0 || end < 0) { throw new Error('buildImage 를 못 찾음'); }
global.window = {};
class KImage { constructor(a) { this.attrs = a; this.img = a.image; } image(v) { if (v === undefined) { return this.img; } this.img = v; } }
global.Konva = { Image: KImage };
class FakeImage {
  constructor() { this.complete = false; this.naturalWidth = 0; this.handlers = []; this.onload = null; }
  addEventListener(type, fn, opts) { if (type === 'load') { this.handlers.push({ fn, once: !!(opts && opts.once) }); } }
  done() { this.complete = true; this.naturalWidth = 640; const hs = this.handlers; this.handlers = hs.filter(h => !h.once); hs.forEach(h => h.fn()); if (this.onload) { this.onload(); } }
}
global.Image = FakeImage;
const num = (v, d) => (typeof v === 'number' ? v : (d || 0)), tagNode = () => {}, viewUrl = k => '/view/' + k;
const flippedImageSource = img => img, konvaLayer = { batchDraw() {} }, canSave = true;
const emitted = [], emitCore = name => emitted.push(name);
let timers = [];   // 가짜 시계 — 그림이 다 뜬 뒤 한 번만 다시 그리는지(묶기 0.15초)
const setTimeout = (fn, ms) => { timers.push(fn); return timers.length; }, clearTimeout = id => { timers[id - 1] = null; };
const flush = () => { const ts = timers; timers = []; ts.forEach(fn => fn && fn()); };
const api = eval(src.slice(start, end) + '; ({ buildImage, cache: _annoImgCache })');
const obj = id => ({ id, type: 'image', key: 'orders/1/a.png', x: 0, y: 0, w: 100, h: 80 });
const a = api.buildImage(obj('a')), b = api.buildImage(obj('b'));
const img = api.cache['orders/1/a.png'];
img.done();
const other = api.buildImage(Object.assign(obj('d'), { key: 'orders/1/b.png' }));
api.cache['orders/1/b.png'].done();
const renders = emitted.length;   // 아직 묶는 중
flush();
const c = api.buildImage(obj('c'));   // 로드 뒤 다시 그리기 — 캐시에서 바로
process.stdout.write(JSON.stringify({ a: !!a.image(), b: !!b.image(), c: !!c.image(), d: !!other.image(), one: Object.keys(api.cache).length,
  left: img.handlers.length, renders: [renders, emitted.filter(n => n === 'render').length] }));
"""


def _node() -> str:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


def test_two_nodes_of_the_same_picture_both_get_the_image_when_it_loads():
    proc = subprocess.run([_node(), "-e", RUNNER, str(WIZARD)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["a"] and out["b"], out          # 앞 칸(a)이 빈 틀로 남지 않는다
    assert out["c"] and out["d"] and out["one"] == 2, out   # key 마다 이미지 하나 · 로드 뒤 새 노드는 캐시에서 바로
    assert out["left"] == 0, out               # 한 번 쓴 로드 손잡이는 남기지 않는다(지운 노드를 붙잡지 않게)


def test_pictures_finishing_loading_redraw_v2_once():
    """그림이 다 뜨면 V2 를 한 번 다시 그린다(render) — 치수 글자 높이 · 예전 양식 기준(% 의 분모)은 그림이 떠야 재는데,
    첫 계산이 그림 전이라 열 때마다 미리보기 · % 가 달랐다(스테이징 4465 같은 시트 두 번 열기: 기준 높이 110 ↔ 150)."""
    proc = subprocess.run([_node(), "-e", RUNNER, str(WIZARD)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["renders"] == [0, 1], out       # 그림 둘이 떠도 묶어서 한 번

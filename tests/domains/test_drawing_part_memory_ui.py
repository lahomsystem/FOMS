"""도면 마법사 그림 종류 기억 — 브라우저 모듈(part-memory.js) 계약 · wizard.js 연결 시험.

설계 정본: docs/plans/2026-10-26-drawing-part-memory-spec.md
- 특징은 float16 little-endian base64(2,048자)로 보낸다 — 파이썬이 같은 값으로 읽는다.
- 이름표 목록: 사람 이름표가 이기고 그다음은 나중 것. 바뀐 줄만 보내고, 실패하면 다음 동기화 때 다시.
- follow 는 갈림 · 꺼짐이면 null, spread 는 사람 이름표 · 잠금 · 주방 짝 · 같은 종류 · 다른 폴더 그림을 묻지 않는다.
- V1 · V2 가 같은 엔진(wizard.js)을 쓰므로 연결은 엔진에 있다.
"""

import base64
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static/js/drawing/part-memory.js"
WIZ = ROOT / "static/js/drawing/wizard.js"

RUNNER = r"""
const timers = [];
global.setTimeout = (fn, ms) => { timers.push(fn); return timers.length; };
global.clearTimeout = () => {};
global.window = { btoa: (s) => Buffer.from(s, 'binary').toString('base64') };
require(process.argv[1]);
const M = window.FomsPartMemory, vec = Float32Array.from(JSON.parse(process.argv[2]));
const settle = () => new Promise((r) => setImmediate(r));
async function tick() { for (let k = 0; k < 4; k++) { while (timers.length) { timers.shift()(); } await settle(); } }
const calls = []; let answer = (path, body) => ({ saved: body.items ? body.items.length : 0, missing: [] }); let fail = false;
const fetch = (url, opts) => { const body = JSON.parse(opts.body); calls.push({ url, body });
  if (fail) { return Promise.resolve({ status: 500, data: { success: false } }); }
  return Promise.resolve({ status: 200, data: { success: true, data: answer(url, body) } }); };
const K = (n) => 'orders/7/drawing_wizard/assets/' + n + '.png';
const img = (id, key, label, src, extra) => Object.assign({ id, type: 'image', key, part: { label, src } }, extra || {});
const sheet = { id: 's1', objects: [img('o-1', K('a'), '정면·내부', 'ai')] };
const out = {};
(async () => {
  out.b64 = M.f16b64(vec);
  out.heads = [M.memHead('h1'), M.memHead('h1.m'), M.memHead('h1234567890123456789')];
  out.isMem = [M.isMem({ src: 'ai', head: 'h1.m' }), M.isMem({ src: 'user', head: 'h1.m' }), M.isMem({ src: 'ai', head: 'h1' })];
  out.map = M.labelMap([
    { objects: [img('a', K('x'), '사진', 'user'), img('b', K('y'), '정면·내부', 'ai')] },
    { objects: [img('c', K('x'), '그림 아님', 'ai'), img('d', K('y'), '정면·도어', 'ai'), img('e', K('z'), '사진', 'user')] },
  ]);
  const pair = { objects: [img('p1', K('p1'), '정면·내부', 'ai'), img('p2', K('p2'), '정면·도어', 'ai'), img('p3', K('p3'), '서랍 단면', 'ai')] };
  out.partner = [M.partnerOf(pair, pair.objects[1], '정면·도어'), M.partnerOf(pair, pair.objects[1], '서랍 단면')];

  // 꺼져 있으면 아무것도 보내지 않는다
  M.init({ base: '/api/orders/7', orderId: 7, fetch, policy: {}, sheets: () => [sheet] });
  M.remember(sheet.objects[0], { feat: vec, fv: 'f1-dv2s-8b1f', ai: '정면·내부', conf: 0.4, head: 'h1' });
  out.offFollow = await M.follow(sheet.objects[0], { feat: vec, fv: 'f1-dv2s-8b1f' });
  await tick(); out.offCalls = calls.length;

  M.init({ base: '/api/orders/7', orderId: 7, fetch, policy: { store: true, follow: true, spread: true }, sheets: () => [sheet] });
  sheet.objects[0].part.head = 'h1.m';
  M.remember(sheet.objects[0], { feat: vec, fv: 'f1-dv2s-8b1f', ai: '정면·내부', conf: 0.4, head: 'h1.m' });
  await tick();
  out.first = calls.slice();
  calls.length = 0;
  M.labelsChanged(); await tick(); out.unchanged = calls.length;           // 이미 보낸 이름표는 다시 안 보낸다
  sheet.objects[0].part = { label: '정면·도어', src: 'user' };
  sheet.objects.push(img('o-out', 'orders/8/drawing_wizard/assets/q.png', '사진', 'user'));   // 다른 주문 폴더는 안 보낸다
  fail = true; M.labelsChanged(); await tick(); out.failed = calls.map((c) => c.body);
  fail = false; calls.length = 0; M.labelsChanged(); await tick(); out.retried = calls.map((c) => c.body);

  answer = () => ({ enabled: true, items: { 'o-9': { label: '정면·도어', sim: 0.99, n: 1, scope: 'other', conflict: false } } });
  out.follow = await M.follow({ id: 'o-9', key: K('n') }, { feat: vec, fv: 'f1-dv2s-8b1f', ai: '정면·내부', conf: 0.5 });
  answer = () => ({ enabled: true, items: { 'o-9': { label: null, sim: 0.97, n: 2, conflict: true } } });
  out.conflict = await M.follow({ id: 'o-9', key: K('n') }, { feat: vec, fv: 'f1-dv2s-8b1f' });

  calls.length = 0;
  answer = () => ({ enabled: true, ids: [{ id: 'b2', sim: 0.99 }] });
  const sp = { objects: [img('a1', K('a1'), '정면·도어', 'user'), img('b2', K('b2'), '정면·내부', 'ai'),
    img('c3', K('c3'), '정면·내부', 'user'), img('d4', K('d4'), '정면·내부', 'ai', { locked: true }),
    img('e5', K('e5'), '정면·도어', 'ai'), img('f6', 'orders/9/drawing_wizard/assets/f.png', '정면·내부', 'ai'),
    img('g7', K('g7'), '서랍 단면', 'ai')] };
  out.spread = await M.spread(sp, sp.objects[0], '정면·도어');
  out.spreadBody = calls.length ? calls[calls.length - 1].body : null;
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""


def _node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    return node


@pytest.fixture(scope="module")
def run():
    vec = np.random.default_rng(3).standard_normal(768).astype(np.float32)
    vec /= np.linalg.norm(vec)
    proc = subprocess.run([_node(), "-e", RUNNER, str(JS), json.dumps(vec.tolist())],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return vec, json.loads(proc.stdout)


def test_feature_is_float16_base64_that_python_reads_back(run):
    vec, out = run
    assert len(out["b64"]) == 2048
    back = np.frombuffer(base64.b64decode(out["b64"]), dtype="<f2").astype(np.float32)
    assert np.allclose(back, vec.astype(np.float16).astype(np.float32), atol=1e-6)
    assert float(back @ vec) > 0.9999


def test_heads_memory_marks_label_map_and_partner(run):
    _, out = run
    assert out["heads"] == ["h1.m", "h1.m", "h1234567890123.m"]
    assert out["isMem"] == [True, False, False]
    k = "orders/7/drawing_wizard/assets/"
    assert out["map"] == {k + "x.png": {"label": "사진", "src": "user"},        # 사람 이름표가 나중 AI 를 이긴다
                          k + "y.png": {"label": "정면·도어", "src": "ai"},     # 같은 출처면 나중 것
                          k + "z.png": {"label": "사진", "src": "user"}}
    assert out["partner"] == ["p1", None]   # 같은 보기 딱 둘 → 짝, 내부/도어가 아니면 짝 없음


def test_sync_sends_features_once_then_only_changed_labels_and_retries_failures(run):
    _, out = run
    assert out["offCalls"] == 0 and out["offFollow"] is None
    assert len(out["first"]) == 1 and out["first"][0]["url"] == "/api/orders/7/drawing-wizard/part-memory"
    item = out["first"][0]["body"]["items"][0]
    assert item["key"] == "orders/7/drawing_wizard/assets/a.png" and len(item["f"]) == 2048
    assert (item["fv"], item["label"], item["src"], item["head"], item["ai"]) == ("f1-dv2s-8b1f", "정면·내부", "ai", "h1", "정면·내부")
    assert out["unchanged"] == 0
    changed = {"items": [{"key": "orders/7/drawing_wizard/assets/a.png", "label": "정면·도어", "src": "user"}]}
    assert out["failed"] == [changed] and out["retried"] == [changed]   # 실패한 줄은 다음 동기화 때 다시


def test_follow_and_spread_requests(run):
    _, out = run
    assert out["follow"] == {"label": "정면·도어", "sim": 0.99, "n": 1, "scope": "other", "conflict": False}
    assert out["conflict"] is None
    assert out["spread"] == [{"id": "b2", "sim": 0.99}]
    body = out["spreadBody"]
    assert body["mode"] == "spread" and body["label"] == "정면·도어"
    # 사람 이름표(c3) · 잠금(d4) · 같은 종류(e5) · 다른 주문 폴더(f6) 는 빼고, 같은 보기가 여럿이라 짝 빼기는 없다
    assert [i["id"] for i in body["items"]] == ["b2", "g7"]


def test_engine_wiring_is_shared_by_v1_and_v2():
    src = WIZ.read_text(encoding="utf-8")
    assert "ai.classify(img).then(function (res) { return memoryFollow(id, res); }).then(function (res) {" in src
    assert "window.FomsPartMemory.remember(o, res);" in src
    assert "o.part.src === 'ai' && !isMemPart(o.part)" in src                     # 짝 규칙은 기억 이름표를 안 바꾼다
    assert "emitCore('labels', { id: id, by: 'user' });\n    memoryAfterUserLabel(o, label);" in src
    assert src.count("memoryLabelsChanged();") >= 5                               # 여러 장 고름 · 되돌리기 · 다시 하기 · 저장 · 같이 고치기
    assert "recordUndo();\n      changed.forEach(function (x) {" in src           # 같이 고치기는 되돌리기 한 번
    ai = (ROOT / "static/js/drawing/part-ai.js").read_text(encoding="utf-8")
    assert "feat: feat, fv: FEAT_VERSION" in ai
    shell = (ROOT / "static/js/drawing/v2-shell.js").read_text(encoding="utf-8")
    assert "core.setPartLabel(id, label)" in shell                                # V2 도 같은 고르기 길을 탄다

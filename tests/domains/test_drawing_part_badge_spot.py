"""도면 마법사 그림 이름 딱지 자리 · 분류 차례 계약 테스트(사용성 재평가 2026-10-25 QA1·QA3).

- 딱지 자리(part-badge-spot.js place)는 순수 계산이라 node 로 돌린다: 그림 틀 위 바깥이 기본, 머리칸·글자 객체·
  다른 그림의 잉크·먼저 놓은 딱지·시트 밖을 덜 가리는 곳으로, 그림 폭보다 긴 글은 짧은 글로.
- 마지막 실화면 확인(V1): 그림 사이 틈이 딱지보다 좁으면 틀에 걸쳐 제 그림 위쪽 빈 곳을 쓴다(윗그림 '60' 을 덮지 않게),
  선보다 글자(숫자) 덮기를 무겁게, 사진 딱지는 제 사진 위도 된다, 줌 100% 아래에서는 딱지도 80% 까지 준다.
- 잉크 지도(inkFromPixels·inkCover)는 합성 픽셀로 잰다 — 글자 지도(t)는 길게 이어진 선을 뺀 나머지.
- 분류(part-ai.js classify)는 한 장씩 차례로, 사이사이 화면을 그리게(그림 틀) 돈다 — 쉬지 않고 이어 돌면
  진행 칩 'n/N' 이 한 번도 안 그려졌다. 실행기·캐시·fetch 를 흉내 내 겹쳐 돌지 않는지 본다.
"""

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPOT_JS = ROOT / "static/js/drawing/part-badge-spot.js"
AI_JS = ROOT / "static/js/drawing/part-ai.js"


def _node():
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


def _run(script, *args):
    proc = subprocess.run([_node(), "-e", script, *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_spot_and_ai_node_check_and_size():
    for path in (SPOT_JS, AI_JS):
        proc = subprocess.run([_node(), "--check", str(path)], capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr
        assert len(path.read_text(encoding="utf-8").splitlines()) < 300   # 새 JS 300줄 래칫


PLACE_RUNNER = r"""
global.window = {};
require(process.argv[1]);
const S = window.FomsPartBadgeSpot, job = JSON.parse(process.argv[2]);
const grid = (g) => g && { w: g.w, h: g.h, v: g.cells.flat() };
const out = {};
for (const [name, c] of Object.entries(job)) {
  const pics = c.pics.map(p => ({ id: p.id, r: p.r, ink: grid(p.ink) }));
  const items = c.pics.filter(p => !p.nobadge).map(p => ({ id: p.id, fw: 125, sw: 70, bh: 21, g: 6 }));
  out[name] = S.place(pics, items, c.blocks || [], { w: 1478, h: 1040 });
}
process.stdout.write(JSON.stringify(out));
"""

HEADER = {"x": 48, "y": 43, "w": 650, "h": 52}   # 머리칸(도면팀·생산팀 두 줄) — 그림 칸은 그 아래 8px(103)부터


def _pic(i, x, y, w, h, ink=None, **kw):
    return {"id": i, "r": {"x": x, "y": y, "w": w, "h": h}, "ink": ink, **kw}


def _ink(w, h, fn):
    return {"w": w, "h": h, "cells": [[1 if fn(i, j) else 0 for i in range(w)] for j in range(h)]}


def test_badge_goes_outside_above_and_dodges_header_text_ink_and_other_badges():
    """QA1·QA3: 딱지가 그림 안 맨 위 치수('950'·'(100)')·자리표 '[SR]'를 가리고 딱지끼리 겹치던 것."""
    top_left_inked = _ink(8, 6, lambda i, j: i < 4 and j < 2)          # 왼쪽 위에 치수 글자가 몰린 그림
    bottom_left_inked = _ink(8, 4, lambda i, j: j == 3 and i < 4)     # 아래 왼쪽에 치수가 있는 윗줄 그림
    job = {
        "free": {"pics": [_pic("a", 100, 300, 400, 300)]},
        "underHeader": {"pics": [_pic("b", 100, 103, 400, 300, top_left_inked)], "blocks": [HEADER]},
        "textAbove": {"pics": [_pic("d", 100, 300, 400, 300)], "blocks": [{"x": 90, "y": 270, "w": 60, "h": 30}]},
        "sheetTop": {"pics": [_pic("e", 100, 5, 400, 300, _ink(8, 6, lambda i, j: False))]},
        "narrow": {"pics": [_pic("f", 100, 700, 90, 100)]},
        "inkAbove": {"pics": [_pic("g1", 100, 300, 400, 200, bottom_left_inked), _pic("g2", 100, 516, 400, 200)]},
        "stacked": {"pics": [_pic("c1", 100, 300, 300, 200), _pic("c2", 110, 310, 300, 200)]},
        "noBadgeStillContent": {"pics": [_pic("w", 100, 250, 400, 40, nobadge=True),
                                         _pic("h", 100, 300, 400, 300, _ink(8, 6, lambda i, j: False))]},
    }
    res = _run(PLACE_RUNNER, SPOT_JS, json.dumps(job))
    full = {"w": 125, "h": 21, "short": False}
    assert res["free"]["a"] == {"x": 106, "y": 277, **full}               # 그림 틀 바로 위 바깥, 왼쪽 끝 맞춤
    assert res["underHeader"]["b"] == {"x": 369, "y": 109, **full}        # 위는 머리칸 글자 → 빈 오른쪽 위 모서리 안
    assert res["textAbove"]["d"] == {"x": 369, "y": 277, **full}          # 위 왼쪽 글자 객체([SR]) → 위 오른쪽 끝
    assert res["sheetTop"]["e"] == {"x": 106, "y": 11, **full}            # 시트 밖으로는 안 나간다
    assert res["narrow"]["f"] == {"x": 106, "y": 677, "w": 70, "h": 21, "short": True}   # 그림 폭보다 긴 글 → 짧은 글
    assert res["inkAbove"]["g2"]["x"] == 369 and res["inkAbove"]["g2"]["y"] == 493       # 윗그림 치수 없는 쪽
    c1, c2 = res["stacked"]["c1"], res["stacked"]["c2"]
    assert not (c1["x"] < c2["x"] + c2["w"] and c2["x"] < c1["x"] + c1["w"] and
                c1["y"] < c2["y"] + c2["h"] and c2["y"] < c1["y"] + c1["h"])                # 딱지끼리 겹치지 않음
    assert "w" not in res["noBadgeStillContent"]                          # 알아보는 중인 그림은 딱지가 없다
    # 그래도 그 그림(w)은 안 가리고 제 그림 위쪽 빈 곳에 틀을 걸쳐(딱지 60% 가 안) — w 아래 끝 290 보다 아래
    assert res["noBadgeStillContent"]["h"] == {"x": 106, "y": 292, **full}


CROWD_RUNNER = r"""
global.window = {};
require(process.argv[1]);
const S = window.FomsPartBadgeSpot;
const pics = [], items = [];
for (let row = 0; row < 3; row++) for (let col = 0; col < 5; col++) {
  const id = 'p' + row + col;
  pics.push({ id, r: { x: 60 + col * 186, y: 120 + row * 136, w: 170, h: 120 }, ink: null });
  items.push({ id, fw: 125, sw: 70, bh: 21, g: 6 });
}
const a = S.place(pics, items, [], { w: 1478, h: 1040 }), b = S.place(pics, items, [], { w: 1478, h: 1040 });
const r = Object.values(a);
let hits = 0;
for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++) {
  if (r[i].x < r[j].x + r[j].w && r[j].x < r[i].x + r[i].w && r[i].y < r[j].y + r[j].h && r[j].y < r[i].y + r[i].h) hits++;
}
process.stdout.write(JSON.stringify({ n: r.length, hits, same: JSON.stringify(a) === JSON.stringify(b) }));
"""


def test_crowded_sheet_badges_never_overlap_and_are_deterministic():
    """QA3 Q61: 작은 그림이 빽빽하면 딱지끼리 겹쳤다 — 15장 격자에서 겹침 0, 같은 입력이면 같은 자리."""
    assert _run(CROWD_RUNNER, SPOT_JS) == {"n": 15, "hits": 0, "same": True}


INK_RUNNER = r"""
global.window = {};
require(process.argv[1]);
const S = window.FomsPartBadgeSpot;
const w = 8, h = 8, px = new Uint8ClampedArray(w * h * 4).fill(255);
const put = (x, y, v, a) => { const k = (y * w + x) * 4; px[k] = px[k + 1] = px[k + 2] = v; px[k + 3] = a; };
put(1, 1, 0, 255);      // 검은 점 → 왼쪽 위 칸 가득
put(6, 1, 240, 255);    // 아주 옅은 회색 → 조금
put(1, 6, 0, 0);        // 투명한 검정 → 바탕(흰색)
put(6, 6, 200, 255);    // 회색 → 반쯤
const g = S.inkFromPixels(px, w, h);
const pic = { r: { x: 0, y: 0, w: 80, h: 80 }, ink: { w: 2, h: 2, v: [1, 0, 0, 0.5] } };
process.stdout.write(JSON.stringify({
  g: { w: g.w, h: g.h, v: g.v.map(v => Math.round(v * 1000) / 1000) },
  all: S.inkCover(pic, 0, 0, 80, 80), mid: S.inkCover(pic, 20, 20, 60, 60),
  none: S.inkCover({ r: pic.r, ink: null }, 10, 10, 30, 20), bad: S.inkFromPixels(px, 9, 9),
}));
"""


def test_ink_grid_takes_darkest_point_per_cell_and_cover_weights_area():
    res = _run(INK_RUNNER, SPOT_JS)
    assert res["g"] == {"w": 2, "h": 2, "v": [1, 0.176, 0, 0.647]}      # 칸마다 가장 진한 점, 밝기 170 이하 = 1
    assert res["all"] == 1 * 40 * 40 + 0.5 * 40 * 40
    assert res["mid"] == 20 * 20 + 0.5 * 20 * 20                           # 칸과 겹친 넓이만큼
    assert res["none"] == 20 * 10                                          # 잉크 지도 없음 = 가득 찬 것으로
    assert res["bad"] is None                                              # 픽셀 수가 모자라면 모름


V1_RUNNER = r"""
global.window = {};
require(process.argv[1]);
const S = window.FomsPartBadgeSpot, B = { w: 1478, h: 1040 }, out = {};
const grid = (w, h, fv, ft) => { const v = [], t = []; for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) { v.push(fv(i, j)); t.push(ft(i, j)); } return { w, h, v, t }; };
const itm = (id, extra) => Object.assign({ id, fw: 113, sw: 65, bh: 20, g: 6 }, extra || {});
// 도면 8(1920·100%): 윗그림 아래 왼쪽에 '60', 그림 사이 틈 16px(딱지 20px), 아랫그림 위 왼쪽은 비고 오른쪽은 치수선
const up = grid(16, 24, (i, j) => (j === 23 && i < 3 ? 1 : 0), (i, j) => (j === 23 && i < 3 ? 1 : 0));
const lo = grid(16, 24, (i, j) => (j === 0 && i >= 4 ? 0.6 : (j === 1 && i < 6 ? 1 : 0)), (i, j) => (j === 1 && i < 6 ? 1 : 0));
out.gap = S.place([{ id: 'u', r: { x: 51, y: 103, w: 527, h: 223 }, ink: up }, { id: 'l', r: { x: 51, y: 342, w: 511, h: 287 }, ink: lo }],
  [itm('u'), itm('l')], [{ x: 48, y: 43, w: 650, h: 52 }], B);
// 글자(왼쪽 위 '9 5 0' 덩어리) 대 선(가운데~오른쪽 긴 치수선) — 위는 양식 칸, 아래 안쪽은 글자 줄
const W = 64, H = 48, px = new Uint8ClampedArray(W * H * 4).fill(255);
const dot = (x, y) => { const k = (y * W + x) * 4; px[k] = px[k + 1] = px[k + 2] = 0; };
for (let n = 0; n < 3; n++) for (let y = 1; y <= 4; y++) for (let x = 2 + n * 5; x <= 4 + n * 5; x++) dot(x, y);
for (let x = 22; x < 64; x++) dot(x, 2);
for (let n = 0; n < 10; n++) for (let y = 44; y <= 47; y++) for (let x = 2 + n * 6; x <= 4 + n * 6; x++) dot(x, y);
out.textVsLine = S.place([{ id: 'p', r: { x: 100, y: 300, w: 400, h: 300 }, ink: S.inkFromPixels(px, W, H) }], [itm('p')],
  [{ x: 0, y: 200, w: 1478, h: 100 }], B);
// 글자 지도: 가로 긴 선(y=1) · 세로 긴 선(x=30) · 3×3 덩어리 하나
const W2 = 32, px2 = new Uint8ClampedArray(W2 * W2 * 4).fill(255);
const dot2 = (x, y) => { const k = (y * W2 + x) * 4; px2[k] = px2[k + 1] = px2[k + 2] = 0; };
for (let x = 0; x < 32; x++) dot2(x, 1);
for (let y = 0; y < 32; y++) dot2(30, y);
for (let y = 16; y <= 18; y++) for (let x = 8; x <= 10; x++) dot2(x, y);
const g2 = S.inkFromPixels(px2, W2, W2);
out.t = { row0: [g2.v.slice(0, 8), g2.t.slice(0, 8)], col7: [[0, 1, 2, 3, 4, 5, 6, 7].map(j => g2.v[j * 8 + 7]), [0, 1, 2, 3, 4, 5, 6, 7].map(j => g2.t[j * 8 + 7])],
  blob: [g2.v[4 * 8 + 2], g2.t[4 * 8 + 2]], sum: g2.t.reduce((a, b) => a + b, 0) };
out.scale = [2, 1, 0.9, 0.8, 0.74, 0.5, 0, NaN, undefined].map(S.badgeScale);
// 사진 딱지: 위 도면 아래 왼쪽에 글자, 틈 16px — 사진 딱지는 제 사진 위에 앉아도 된다(긴 글 그대로)
const dw = grid(8, 4, (i, j) => (j === 3 && i < 4 ? 1 : 0), (i, j) => (j === 3 && i < 4 ? 1 : 0));
const pics = [{ id: 'dw', r: { x: 100, y: 300, w: 400, h: 200 }, ink: dw }, { id: 'ph', r: { x: 100, y: 516, w: 200, h: 260 }, ink: grid(8, 8, () => 1, () => 1) }];
out.photo = S.place(pics, [itm('ph', { photo: true, fw: 86, sw: 38 })], [], B).ph;
out.notPhoto = S.place(pics, [itm('ph', { fw: 86, sw: 38 })], [], B).ph;
process.stdout.write(JSON.stringify(out));
"""


def test_badge_straddles_own_top_prefers_lines_over_digits_and_photo_may_cover_itself():
    """마지막 실화면 확인(V1): 틈(16px)보다 큰 딱지가 윗그림 아래 '60' 을 덮고, 맞춤 74% 에서 '650'·'950 45' 를 덮었다."""
    res = _run(V1_RUNNER, SPOT_JS)
    gap = res["gap"]
    assert gap["l"] == {"x": 57, "y": 328, "w": 113, "h": 20, "short": False}   # 틀에 걸침 — 윗그림 아래 끝(326) 아래, 제 그림 빈 위쪽
    assert gap["u"]["y"] == 95                                            # 머리칸(~95) 바로 밑에 걸침 — 머리칸 글자도 맨 위 치수도 안 덮음
    # 왼쪽 위 숫자 덩어리 대신 오른쪽 치수선 위로(앞 후보인 왼쪽이 싸도 글자 덮기가 훨씬 무겁다)
    assert res["textVsLine"]["p"] == {"x": 429, "y": 306, "w": 65, "h": 20, "short": True}
    t = res["t"]
    assert t["row0"] == [[1] * 8, [0] * 8]                                # 가로 긴 선 — 잉크는 있지만 글자는 아님
    assert t["col7"] == [[1] * 8, [0] * 8]                                # 세로 긴 선도 같다
    assert t["blob"] == [1, 1] and t["sum"] == 1                          # 작은 덩어리만 글자로 남는다
    # 딱지 화면 배율: 100% 이상 1, 아래는 줌을 따라 80% 까지(wizard.css clamp(0.8, 줌, 1) 와 같은 식) · 이상한 값은 1
    assert res["scale"] == [1, 1, 0.9, 0.8, 0.8, 0.8, 1, 1, 1]
    assert res["photo"] == {"x": 106, "y": 502, "w": 86, "h": 20, "short": False}   # 도면 글자(아래 끝 500) 안 덮고 사진 위 긴 글
    assert res["notPhoto"]["short"] is True and res["notPhoto"]["y"] >= 500        # 사진이 아니면 덜 덮으려 짧은 글


AI_RUNNER = r"""
const job = JSON.parse(process.argv[2]);
let active = 0, overlap = false, frames = 0, runs = 0;
global.document = {
  currentScript: null, hidden: false, head: { appendChild() {} },
  createElement: () => ({ width: 0, height: 0, getContext: () => ({ fillRect() {}, drawImage() {},
    getImageData: (x, y, w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }) }) }),
};
const head = { labels: ['정면·내부', '정면·도어'], W: [new Array(768).fill(0), new Array(768).fill(0)], b: [2, 0],
  threshold: 0.5, version: 'h1' };
const sess = { inputNames: ['pixel_values'], run: async () => {
  runs += 1; active += 1; if (active > 1) { overlap = true; }
  await new Promise(r => setTimeout(r, 5));   // 실행기가 도는 동안
  active -= 1;
  return { last_hidden_state: { dims: [1, 2, 384], data: new Float32Array(768).fill(0.1) } };
} };
const store = job.cached ? { match: async () => ({ arrayBuffer: async () => new ArrayBuffer(4) }), put: async () => {} }
  : { match: async () => undefined, put: async () => {} };
global.window = {
  requestAnimationFrame: (f) => { frames += 1; setTimeout(f, 1); },
  caches: { open: async () => store },
  ort: { InferenceSession: { create: async () => sess }, Tensor: function () {}, env: { wasm: {} } },
};
let fetches = 0;
global.fetch = async () => { fetches += 1; if (job.offline) { throw new Error('offline'); }
  return { ok: true, json: async () => head, arrayBuffer: async () => new ArrayBuffer(4), clone() { return this; } }; };
require(process.argv[1]);
const AI = window.FomsPartAI, img = { naturalWidth: 10, naturalHeight: 10 };
(async () => {
  const cached = await AI.cached();
  const res = await Promise.all([AI.classify(img), AI.classify(img), AI.classify(img)]);
  delete window.caches;
  const noStore = await AI.cached();
  const first = fetches, ran = runs, again = await AI.classify(img);   // 실패 뒤 새로 맡긴 그림은 다시 준비해 본다
  process.stdout.write(JSON.stringify({ cached, noStore, labels: res.map(r => r && r.label), overlap, runs: ran, frames,
    fetches: [first, fetches], again: again && again.label }));
})();
"""


def test_classify_runs_one_at_a_time_with_a_frame_between_and_reports_cache():
    """QA1·QA3: 진행 칩 'n/N' 이 한 번도 안 보였다 — 분류가 쉬지 않고 이어 돌아 화면을 그릴 틈이 없었다."""
    res = _run(AI_RUNNER, AI_JS, json.dumps({"cached": True}))
    assert res["labels"] == ["정면·내부"] * 3
    assert res["overlap"] is False and res["runs"] == 3                 # 앞 장이 끝난 뒤에 다음 장
    assert res["frames"] >= 3                                            # 장마다 그림 틀 한 번(진행 칩이 그려질 틈)
    assert res["cached"] is True and res["noStore"] is False
    assert _run(AI_RUNNER, AI_JS, json.dumps({"cached": False}))["cached"] is False
    off = _run(AI_RUNNER, AI_JS, json.dumps({"cached": True, "offline": True}))
    assert off["labels"] == [None, None, None] and off["runs"] == 0      # 받기 실패 — 함께 맡긴 그림은 같이 손으로
    # 세 장이 준비 한 번(분류기 1번 — 모델은 캐시)을 같이 기다린다 · 다음에 맡긴 그림 때 한 번 더(캐시를 지워 모델·분류기 2번)
    assert off["fetches"] == [1, 3] and off["again"] is None


WIZARD_JS = ROOT / "static/js/drawing/wizard.js"

PROGRESS_RUNNER = r"""
// wizard.js 의 partCheckModel · partProgress 원문을 흉내 낸 앱 위에서 돌린다(진행 칩에 넘기는 장수·글 갈래)
const job = JSON.parse(process.argv[2]);
const calls = [];
global.window = { FomsPartBadges: { progress: (d, t, o) => calls.push([d, t, o.loading]) } };
if (job.ai) { window.FomsPartAI = { warm: () => new Promise(() => {}), cached: () => Promise.resolve(job.cached) }; }
var partBusy = { done: 0, total: 0, held: 0 }, partModelReady = false, partWarmAsked = false, partModelCached = null, partModelAsked = false;
eval(process.argv[1]);
const tick = () => new Promise(r => setTimeout(r, 0));
(async () => {
  for (const step of job.steps) {
    if (step === 'tick') { await tick(); continue; }
    if (step === 'open') { partCheckModel(); continue; }   // 페이지를 열 때(initPartBadges) 미리 묻기
    partProgress(step[0], step[1], step[2]);
  }
  process.stdout.write(JSON.stringify({ calls, busy: partBusy }));
})();
"""


def _progress(job):
    js = WIZARD_JS.read_text(encoding="utf-8")
    src = "\n".join(js[js.index("  function " + n + "("):].split("\n  }\n", 1)[0] + "\n  }" for n in ("partCheckModel", "partProgress"))
    return _run(PROGRESS_RUNNER, src, json.dumps(job))


def test_progress_counts_whole_batch_up_front_and_waits_for_model_answer():
    """V3: 20장을 한꺼번에 올리면 칩 분모가 0/1 → 1/1 → 0/14 → 3/19 로 뛰고 19 까지만 보였다(올림이 끝나는 대로 셌다).
    V1: 모델이 있는지 답이 오기 전에 '알아보는 중' 을 띄웠다가 0.1초 뒤 '모델 받는 중' 으로 바꿨다 → 답 전에는 장수만(null)."""
    starts = [[1, 0]] * 19
    res = _progress({"ai": True, "cached": False,
                     "steps": [[20, 0, True], [-1, 0, True]] + starts + ["tick"] + [[0, 1]] * 19})
    calls = res["calls"]
    assert calls[0] == [0, 20, None] and calls[1] == [0, 19, None]     # 처음부터 묶음 장수 · 못 올린 1장은 뺌 · 답 전엔 글 없음
    assert all(c[:2] == [0, 19] for c in calls[2:21])                   # 분류 시작은 미리 센 데서 꺼낸다(분모가 안 뛴다)
    assert calls[21] == [0, 19, True]                                    # 답: 모델 없음 → '모델 받는 중'
    assert calls[-1] == [19, 19, True] and res["busy"] == {"done": 0, "total": 0, "held": 0}
    # 모델을 받아 둔 브라우저는 답이 오면 '알아보는 중'(false) · 한 장만 올리면 예전처럼 시작할 때 센다
    one = _progress({"ai": True, "cached": True, "steps": ["open", "tick", [1, 0], [0, 1]]})["calls"]
    assert one == [[0, 0, False], [0, 1, False], [1, 1, False]]
    # 분류 스크립트가 없으면 미리 세지 않는다(칩이 0/N 에 멈추지 않게)
    assert _progress({"ai": False, "steps": [[5, 0, True], [-1, 0, True]]})["calls"] == []

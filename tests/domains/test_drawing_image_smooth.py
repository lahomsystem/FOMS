"""도면 마법사 — 줄여 그린 그림 고운 필터(image-smooth.js, node 로 돌린다).

사용자 보고(2026-10-28): '컴퍼넌트를 줄이면 화질이 떨어진다'. 병렬 조사(화면 · 내보내기 · 원본 · 브라우저 실험) 총괄 판정:
원본 그림은 줄이지 않는다(여백 자르기뿐) — Konva.Image 가 그릴 때마다 원본을 drawImage 로 줄이면서 캔버스 기본
imageSmoothingQuality 'low' 를 써서, GPU 캔버스의 Chromium 은 33% 밑에서 치수선 · 빗금 · 숫자가 깨진다. Chrome · Edge 에서만
그림을 그리는 동안 'high' 로 바꾸고 되돌린다(Safari/iPad · Firefox 는 없거나 너무 느려 그대로). node.image() 는 원본 그대로.
같은 날 다시 보고('위자드에 들어가서 줄이거나 늘이면 화질이 매우 저하' — 끊긴 치수선): 'high' 가 안 먹는 캔버스(그래픽 카드 없이 그리는
Chrome · Safari · Firefox)도 곱게, 반씩 줄인 사다리에서 그릴 크기 이상인 가장 작은 칸으로 그린다(마지막 줄임 2배 안).
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
const [file, ua] = process.argv.slice(1, 3);
const drawn = [], made = [];
global.document = { createElement: () => { const c = { width: 0, height: 0 };
  c.getContext = () => ({ drawImage: (src, x, y, w, h) => made.push([src.naturalWidth || src.width, w, h]) }); return c; } };
global.window = { navigator: { userAgent: ua }, Konva: { Image: { prototype: {
  _sceneFunc(ctx) {
    if (this.id === 'boom') { throw new Error('boom'); }
    const im = this.attrs.image;
    drawn.push([this.id, im.naturalWidth || im.width, ctx && ctx._context ? ctx._context.imageSmoothingQuality : null]);
  } } } } };
require(file);
const S = window.FomsImageSmooth, img = { naturalWidth: 1696, naturalHeight: 1223 };   // 주문 4385 주 그림 원본
const mk = (id, w, h) => ({ id, attrs: { image: img }, width: () => w, height: () => h });
const ctx = k => ({ _context: { imageSmoothingQuality: 'low', getTransform: () => ({ a: k, b: 0, c: 0, d: k }) } });
const shapes = [mk('fit', 715, 515), mk('small', 300, 216), mk('zoom', 715, 515), mk('fit2', 715, 515), mk('none', 715, 515)];
const raws = [ctx(1), ctx(1), ctx(2.25), ctx(1), null];
shapes.forEach((sh, i) => S.sceneFunc(raws[i], sh));
const boom = mk('boom', 300, 216), braw = ctx(1);
try { S.sceneFunc(braw, boom); } catch (e) { /* 그리다 깨져도 원본 · 필터는 되돌린다 */ }
process.stdout.write(JSON.stringify({ enabled: S.enabled, drawn, made, restored: shapes.concat([boom]).every(sh => sh.attrs.image === img),
  after: raws.slice(0, 4).map(r => r._context.imageSmoothingQuality).concat([braw._context.imageSmoothingQuality]), step: S.STEP }));
"""

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
EDGE = CHROME + " Edg/141.0"
SAFARI = "Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
IOS_CHROME = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/141.0 Mobile/15E148 Safari/604.1"
FIREFOX = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0"
# 그릴 크기(기기 픽셀)마다 고르는 사다리 칸 — 원본 1696 · 1/2 848 · 1/4 424
SIZES = [["fit", 848], ["small", 424], ["zoom", 1696], ["fit2", 848], ["none", 1696]]


def _node() -> str:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


def _run(ua: str) -> dict:
    proc = subprocess.run([_node(), "-e", RUNNER, str(JS_DIR / "image-smooth.js"), ua], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_node_check_image_smooth():
    proc = subprocess.run([_node(), "--check", str(JS_DIR / "image-smooth.js")], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr


def test_big_reductions_draw_from_the_half_size_ladder_in_every_browser():
    """같은 날 다시 보고(끊긴 치수선): 'high' 가 안 먹는 캔버스(그래픽 카드 없이 · Safari · Firefox)도 곱게 —
    반씩 줄인 사다리를 필요할 때만 만들고, 그릴 기기 픽셀 크기 이상인 칸 가운데 가장 작은 것으로 그린다(마지막 줄임 2배 안)."""
    for ua in (CHROME, EDGE, SAFARI, IOS_CHROME, FIREFOX):
        out = _run(ua)
        assert [[d[0], d[1]] for d in out["drawn"]] == SIZES, (ua, out)
        assert out["made"] == [[1696, 848, 612], [848, 424, 306]], out      # 두 칸만, 한 번씩(다시 그려도 새로 안 만든다)
        assert out["restored"] is True and out["step"] == 2                # node.image() 는 원본 그대로(깨져도)


def test_chrome_and_edge_also_draw_with_high_quality_and_restore():
    for ua in (CHROME, EDGE):
        out = _run(ua)
        assert out["enabled"] is True, ua
        assert [d[2] for d in out["drawn"]] == ["high", "high", "high", "high", None], out
        assert out["after"] == ["low"] * 5                                  # 그 그림을 그린 뒤 원래 값으로(다른 노드 · 선 · 글자는 그대로)


def test_safari_ipad_ios_chrome_and_firefox_keep_low_but_still_use_the_ladder():
    for ua in (SAFARI, IOS_CHROME, FIREFOX):
        out = _run(ua)
        assert out["enabled"] is False, ua
        assert [d[2] for d in out["drawn"]][:4] == ["low"] * 4 and out["after"] == ["low"] * 5, ua   # WebKit 'high' 는 그림 한 장 100ms 넘게


def test_image_nodes_use_the_smooth_scene_and_keep_the_original_source():
    build = JS[JS.index("  function buildImage(o) {"):JS.index("  function flippedImageSource(img, o) {")]
    assert "if (window.FomsImageSmooth) { node.sceneFunc(window.FomsImageSmooth.sceneFunc); }" in build
    assert build.count("node.image(flippedImageSource(") == 2              # 원본(또는 뒤집은 원본) 그대로 — 글자 높이 · 빗금 · 딱지가 읽는다
    konva = TPL.index("vendor/konva.min.js')")
    smooth = TPL.index("js/drawing/image-smooth.js') }}?v=20261028b")
    assert konva < smooth < TPL.index("js/drawing/wizard.js') }}?v=20261029a")

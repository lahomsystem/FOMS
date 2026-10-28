"""도면 마법사 — 줄여 그린 그림 고운 필터(image-smooth.js, node 로 돌린다).

사용자 보고(2026-10-28): '컴퍼넌트를 줄이면 화질이 떨어진다'. 병렬 조사(화면 · 내보내기 · 원본 · 브라우저 실험) 총괄 판정:
원본 그림은 줄이지 않는다(여백 자르기뿐) — Konva.Image 가 그릴 때마다 원본을 drawImage 로 줄이면서 캔버스 기본
imageSmoothingQuality 'low' 를 써서, GPU 캔버스의 Chromium 은 33% 밑에서 치수선 · 빗금 · 숫자가 깨진다. Chrome · Edge 에서만
그림을 그리는 동안 'high' 로 바꾸고 되돌린다(Safari/iPad · Firefox 는 없거나 너무 느려 그대로). node.image() 는 원본 그대로.
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
const seen = [];
global.window = { navigator: { userAgent: ua }, Konva: { Image: { prototype: {
  _sceneFunc(ctx) { seen.push([this.id, ctx && ctx._context ? ctx._context.imageSmoothingQuality : null]); } } } } };
require(file);
const S = window.FomsImageSmooth, raw = { imageSmoothingQuality: 'low' };
S.sceneFunc({ _context: raw }, { id: 'n1' });
S.sceneFunc(null, { id: 'n2' });               // 컨텍스트가 없어도(내보내기 준비 중) 그리기는 그대로 넘긴다
process.stdout.write(JSON.stringify({ enabled: S.enabled, seen, after: raw.imageSmoothingQuality }));
"""

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
EDGE = CHROME + " Edg/141.0"
SAFARI = "Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
IOS_CHROME = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/141.0 Mobile/15E148 Safari/604.1"
FIREFOX = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0"


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


def test_chrome_and_edge_draw_with_high_quality_and_restore():
    for ua in (CHROME, EDGE):
        out = _run(ua)
        assert out["enabled"] is True, ua
        assert out["seen"] == [["n1", "high"], ["n2", None]], out
        assert out["after"] == "low"                 # 그 그림을 그린 뒤 원래 값으로(다른 노드 · 선 · 글자는 그대로)


def test_safari_ipad_ios_chrome_and_firefox_are_left_alone():
    for ua in (SAFARI, IOS_CHROME, FIREFOX):
        out = _run(ua)
        assert out["enabled"] is False, ua
        assert out["seen"][0] == ["n1", "low"] and out["after"] == "low", ua   # WebKit 'high' 는 그림 한 장 100ms 넘게 — 바꾸지 않는다


def test_image_nodes_use_the_smooth_scene_and_keep_the_original_source():
    build = JS[JS.index("  function buildImage(o) {"):JS.index("  function flippedImageSource(img, o) {")]
    assert "if (window.FomsImageSmooth) { node.sceneFunc(window.FomsImageSmooth.sceneFunc); }" in build
    assert build.count("node.image(flippedImageSource(") == 2              # 원본(또는 뒤집은 원본) 그대로 — 글자 높이 · 빗금 · 딱지가 읽는다
    konva = TPL.index("vendor/konva.min.js')")
    smooth = TPL.index("js/drawing/image-smooth.js') }}?v=20261028a")
    assert konva < smooth < TPL.index("js/drawing/wizard.js') }}?v=20261028c")

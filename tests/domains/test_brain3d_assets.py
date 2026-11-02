"""'뇌 보기' 파일 규칙(설계서 7.6 '기술' · 사장님 D100 — three.js 0.187.0 반입 허락 · AGENTS.md 프런트 규칙).

- three.js 세 파일: SHA-256 이 NOTICE 에 적은 값과 같다 · MIT. three.module.js · three.core.js 는 배포 바이트 그대로이고,
  OrbitControls.js 는 import 한 줄만 고쳤다(``'three'`` → ``'./three.module.js'`` — import map 없이 같은 인스턴스).
- 탭을 열 때만 import() — 어떤 템플릿도 <script> · <link> 로 싣지 않고, 화면 파일 가운데 brain3d-tab.js 만 부른다.
- 그리기 파일은 classic 스크립트(import · export 구문 없음 — 정적 JS 구문 시험이 클래식으로 읽는다)이고 인라인 스타일을 만지지
  않는다 — 이름표 자리는 SVG transform 속성(setAttribute). 이웃 지도 · 뇌 보기 새 파이썬 파일은 500줄 이하.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "static/vendor/three-0.187.0"
DIGESTS = {
    "three.module.js": "104f56145899722094556490d787aae0617cc2fc3382f31df02d724ea1aee341",
    "three.core.js": "613e370f76638fdef83926642bf256dc9615684922de1ce1f63a8583e5d78578",
    "OrbitControls.js": "a747d56dd959510407777f1800792b2b52c0a435980fd6e40caf303d8a674b9e",
}
ORBIT_ORIGINAL = "e7fca2fe9e7670a828af9b28084669a5909445b7f36f1f26cee9bf8f2961c32c"
RENDER = ("brain3d-layout.js", "brain3d-shell.js", "brain3d-nodes.js", "brain3d-labels.js", "brain3d-scene.js")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_vendored_three_files_match_the_recorded_sha256_and_mit():
    notice = _text(ROOT / "static/vendor/three-NOTICE.txt")
    assert sorted(p.name for p in VENDOR.iterdir()) == sorted(DIGESTS)
    for name, digest in DIGESTS.items():
        data = (VENDOR / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, name
        assert digest in notice and f"static/vendor/three-0.187.0/{name}" in notice
        assert b"\r\n" not in data[:200_000]  # 줄 끝을 바꾸면 받은 바이트가 아니다
    assert ORBIT_ORIGINAL in notice and notice.count("MIT") >= 4 and "Copyright © 2010-2026 three.js authors" in notice
    assert "static/vendor/three-0.187.0/*.js -text" in _text(ROOT / ".gitattributes")
    core = (VENDOR / "three.core.js").read_bytes()
    assert b"const REVISION = '187';" in core and b"SPDX-License-Identifier: MIT" in core[:200]


def test_only_the_orbit_controls_import_line_was_changed():
    orbit = _text(VENDOR / "OrbitControls.js")
    sources = re.findall(r"^\} from '([^']+)';", orbit, flags=re.M) + re.findall(r"^import .* from '([^']+)';", orbit,
                                                                                  flags=re.M)
    assert sources == ["./three.module.js"]  # 'three' 맨 이름이 남지 않았다
    assert orbit.splitlines()[11] == "} from './three.module.js';"
    module = _text(VENDOR / "three.module.js")
    assert set(re.findall(r"from '([^']+)';", module)) == {"./three.core.js"}  # 같은 폴더 하나만 읽는다


def test_three_loads_only_through_import_when_the_tab_opens():
    tags = [t for p in ROOT.joinpath("templates").rglob("*.html") for t in re.findall(r"<(?:script|link)[^>]*>", _text(p))]
    assert not [t for t in tags if "three" in t]
    partial = _text(ROOT / "templates/brain/partials/card_brain3d.html")
    assert "url_for('static', filename='vendor/three-0.187.0/three.module.js')" in partial
    assert "url_for('static', filename='vendor/three-0.187.0/OrbitControls.js')" in partial
    tab = _text(ROOT / "static/js/brain/brain3d-tab.js")
    assert "import(root.getAttribute('data-three-url'))" in tab and "import(root.getAttribute('data-orbit-url'))" in tab
    assert "button.addEventListener('shown.bs.tab', open)" in tab and "button.addEventListener('hidden.bs.tab', close)" in tab
    scene = _text(ROOT / "static/js/brain/brain3d-scene.js")
    assert "failIfMajorPerformanceCaveat: true" in scene and "renderer.dispose()" in scene
    assert "renderer.forceContextLoss()" in scene and "setAnimationLoop(null)" in scene
    code = {p.name: [line for line in _text(p).splitlines() if not line.strip().startswith(("*", "//", "/**"))]
            for p in ROOT.joinpath("static/js").rglob("*.js")}
    assert [name for name, lines in code.items() if any("three-0.187.0" in line for line in lines)] == []  # 주소는 data-*


def test_render_files_are_classic_scripts_without_inline_style():
    for name in RENDER + ("brain3d-core.js", "brain3d-tab.js"):
        js = _text(ROOT / "static/js/brain" / name)
        assert not re.search(r"^\s*(import|export)\s", js, flags=re.M), name  # 클래식 — import() 로만 읽힌다
        for banned in (".style", "innerHTML", "insertAdjacentHTML", "cssText", "setProperty("):
            assert banned not in js, (name, banned)
    labels = _text(ROOT / "static/js/brain/brain3d-labels.js")
    assert "setAttribute('transform', 'translate(" in labels and "textContent = item.name" in labels
    assert "prefers-reduced-motion: reduce" in _text(ROOT / "static/js/brain/brain3d-tab.js")
    tab = _text(ROOT / "static/js/brain/brain3d-tab.js")
    assert "WEBGL_debug_renderer_info" in tab and "core.canShow3d(" in tab and "core.isSoftwareRenderer(" in tab


def test_new_python_files_stay_under_five_hundred_lines():
    for rel in ("foms/services/brain/around.py", "foms/services/brain/external.py", "foms/services/brain/quality.py",
                "foms/services/brain/read.py", "foms/services/brain/card.py", "foms/services/brain/apply.py",
                "foms/api/brain.py", "foms/web/brain.py"):
        assert len(_text(ROOT / rel).splitlines()) <= 500, rel

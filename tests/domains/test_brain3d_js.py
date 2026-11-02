"""'뇌 보기' · '이웃 지도' 순수 함수 node 시험(설계서 7.5 화면 9 · 7.6) — three.js · DOM 없이.

- 같은 키 → 같은 자리(따로 띄운 node 두 번도 같은 수) · 부위 표(7.6 — 에이전트 일은 이마엽 D100, 관찰은 층과 무관하게 해마).
- 소프트웨어 그리기 판별(SwiftShader · llvmpipe · Microsoft Basic Render · 'Software') · 휴대폰 · WebGL 없음 → 탭 숨김.
- 색(은퇴 회색 > 낡음 주황 > 유형 색) · 밝기(쓰인 횟수 log) · 바탕 점 풀기.
- 이웃 지도 요소 · 종류 칩 · 켜진 종류 바꾸기 · 고른 항목과 이어진 키 · 목록 차례 · 물음 글.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from foms.services.brain.browse import type_map_data

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static/js/brain"
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")


def _node(expr: str, data: object = None):
    script = (f"const core = require({json.dumps(str(JS / 'brain3d-core.js'))});"
              f"const layout = require({json.dumps(str(JS / 'brain3d-layout.js'))});"
              f"const g = require({json.dumps(str(JS / 'brain-graph-view.js'))});"
              f"const data = {json.dumps(data, ensure_ascii=False)};"
              f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60,
                         check=True).stdout
    return json.loads(out)


@NODE
def test_same_key_gives_the_same_position_across_runs():
    expr = "data.map(k => layout.positionFor({key: k, type: 'price_rule', layer: 'common'}))"
    keys = ["common/shipping", "common/install", "cs/answer/03"]
    first, second = _node(expr, keys), _node(expr, keys)
    assert first == second  # 따로 띄운 node 두 번 — 해시 · 씨앗 난수라 물리 배치 흔들림이 없다
    assert first[0] != first[1]
    again = _node("[layout.positionFor({key: 'common/shipping', type: 'price_rule'}),"
                  " layout.positionFor({key: 'common/shipping', type: 'price_rule'})]")
    assert again[0] == again[1] == first[0]
    packed = _node("Array.from(layout.layoutAll(data.map(k => ({key: k, type: 'price_rule'}))))", keys)
    assert [round(x, 4) for x in packed[:3]] == [round(x, 4) for x in first[0]]


@NODE
def test_regions_follow_the_spec_table():
    got = _node("[['brand','common'],['spec','common'],['price_rule','common'],['owner_decision','common'],"
                "['conflict','cs'],['question','drawing'],['template','cs'],['image_read_rule','cs'],"
                "['bom_rule','drawing'],['case','drawing'],['photo_observation','cs'],['nope','production'],"
                "['nope','cs'],['nope','']].map(p => core.regionOf(p[0], p[1]))")
    assert got == ["base", "base", "frontal", "frontal", "frontal", "frontal", "temporal", "temporal", "occipital",
                   "hippo", "hippo", "motor", "temporal", "base"]
    # 부위 자리 — 이마엽은 앞(z > 0), 뒤통수엽은 뒤, 해마 · 바탕은 안쪽(겉 반지름 안)
    spots = _node("['price_rule','drawing_rule','template','case','spec'].map(t => Array.from({length: 40}, (_, i) =>"
                  " layout.positionFor({key: t + '/' + i, type: t})))")
    frontal, occipital, temporal, hippo, base = spots
    assert all(p[2] > 0.25 for p in frontal) and all(p[2] < -0.45 for p in occipital)
    assert all(abs(p[0]) > 0.45 for p in temporal)  # 옆쪽
    assert all(abs(p[0]) < 0.45 and p[1] < 0.15 for p in hippo)
    assert all(abs(p[0]) <= 0.37 and abs(p[2]) <= 0.56 for p in base)
    # 가운데 뭉침 줄이기 — 바탕 점의 한가운데(바탕 반지름 30% 안)에는 거의 없다
    centre = [p for p in base if (p[0] / 0.36) ** 2 + ((p[1] + 0.06) / 0.25) ** 2 + ((p[2] - 0.03) / 0.52) ** 2 < 0.09]
    assert len(centre) <= 2


@NODE
def test_software_renderer_and_phone_hide_the_tab():
    names = ["ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)",
             "llvmpipe (LLVM 15.0.7, 256 bits)", "Microsoft Basic Render Driver", "Software Rasterizer",
             "Mesa OffScreen", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)",
             "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)", "Apple M2", ""]
    assert _node("data.map(core.isSoftwareRenderer)", names) == [True] * 5 + [False] * 4
    cases = [{"width": 1600, "webgl": True, "renderer": names[5], "hover": True},
             {"width": 390, "webgl": True, "renderer": names[5]},
             {"width": 1024, "coarse": True, "hover": False, "webgl": True, "renderer": names[5]},
             {"width": 1600, "webgl": False, "renderer": ""},
             {"width": 1600, "webgl": True, "renderer": names[0], "hover": True}]
    assert _node("data.map(core.canShow3d)", cases) == [
        {"show": True, "reason": None}, {"show": False, "reason": "phone"}, {"show": False, "reason": "phone"},
        {"show": False, "reason": "no_webgl"}, {"show": False, "reason": "software"}]


@NODE
def test_colours_brightness_and_point_decoding():
    display = type_map_data({})["display"]
    got = _node("[core.pointColor('product_line', 0, data), core.pointColor('product_line', core.FLAG_STALE, data),"
                " core.pointColor('product_line', core.FLAG_RETIRED | core.FLAG_STALE, data),"
                " core.hexRgb('#1d4ed8'), core.glow(0, 0, 0), core.glow(9, 9, 0), core.glow(9, 9, core.FLAG_RETIRED),"
                " core.flagsOf({status: 'draft', stale: true}), core.linkColor('applies_to', data)]", display)
    base = got[3]
    assert got[0] == [pytest.approx(c + (1 - c) * 0.42) for c in base]  # 화면 표 유형 색을 밝힌 것(같은 계열)
    assert got[1] == [pytest.approx(x) for x in (0xFB / 255, 0x92 / 255, 0x3C / 255)]  # 낡음 주황
    assert got[2] == [pytest.approx(x) for x in (0x9C / 255, 0xA3 / 255, 0xAF / 255)]  # 은퇴가 낡음보다 먼저
    assert got[4] == 0 and got[5] == 1 and got[6] == pytest.approx(0.1) and got[7] == 5
    assert len(got[8]) == 3
    rows = _node("core.decodePoints(data)", {"types": ["spec", "case"], "rows": [["a/1", 1, 4, 3], ["b", 9, 0, 0]]})
    assert rows == [{"key": "a/1", "type": "case", "flags": 4, "usage": 3}, {"key": "b", "type": "", "flags": 0, "usage": 0}]


@NODE
def test_neighbour_map_elements_chips_and_selection():
    display = type_map_data({})["display"]
    data = {"display": display, "around": {
        "start": {"key": "common/door", "name": "문짝", "type": "product_line", "status": "active"},
        "items": [{"key": "common/slide", "name": "미닫이", "type": "product_line", "status": "retired", "depth": 2,
                   "via": ["requires"]},
                  {"key": "common/fit", "name": "맞춤", "type": "build_rule", "status": "draft", "stale": True,
                   "depth": 1, "via": ["applies_to"]}],
        "edges": [{"kind": "applies_to", "from": "common/fit", "to": "common/door"},
                  {"kind": "requires", "from": "common/fit", "to": "common/slide"}]}}
    els = _node("g.aroundElements(data.around, data.display)", data)
    nodes = {e["data"]["id"]: e for e in els if e["group"] == "nodes"}
    edges = [e["data"] for e in els if e["group"] == "edges"]
    assert nodes["common/door"]["classes"] == "is-start" and nodes["common/door"]["data"]["color"] == "#1d4ed8"
    assert nodes["common/fit"]["classes"] == "is-depth1 is-draft is-stale"
    assert nodes["common/slide"]["classes"] == "is-depth2 is-retired"
    assert edges[0] == {"id": "applies_to:common/fit>common/door", "source": "common/fit", "target": "common/door",
                        "kind": "applies_to", "color": "#2563eb", "label": "적용"}
    order = ["applies_to", "requires", "excludes"]
    chips = _node("[g.chipModel({requires: 1, applies_to: 3}, data, [], data.order),"
                  " g.chipModel({requires: 1, applies_to: 3}, data, ['requires'], data.order)]", {**display, "order": order})
    assert [(c["kind"], c["count"], c["on"]) for c in chips[0]] == [("applies_to", 3, True), ("requires", 1, True)]
    assert [(c["kind"], c["on"]) for c in chips[1]] == [("applies_to", False), ("requires", True)]
    toggles = _node("[g.toggleKind([], 'requires', data), g.toggleKind(['applies_to'], 'requires', data),"
                    " g.toggleKind(['requires'], 'requires', data), g.toggleKind(['applies_to'], 'applies_to', data)]",
                    ["applies_to", "requires", "excludes"])
    assert toggles == [["applies_to", "excludes"], ["applies_to", "requires"], ["requires"], ["applies_to"]]
    assert _node("g.toggleKind(['applies_to', 'requires'], 'excludes', data)", ["applies_to", "requires", "excludes"]) == []
    assert _node("g.related(data.around.edges, 'common/fit')", data) == ["common/door", "common/fit", "common/slide"]
    assert _node("g.related(data.around.edges, 'common/slide')", data) == ["common/fit", "common/slide"]
    assert [r["key"] for r in _node("g.listRows(data.around)", data)] == ["common/fit", "common/slide"]
    assert _node("[g.aroundParams({key: 'calc:a b', depth: 2, kinds: ['requires', 'applies_to'], limit: 60}),"
                 " g.aroundParams({key: 'common/door', depth: 5})]") == [
        "key=calc%3Aa%20b&kinds=requires,applies_to&depth=2&limit=60", "key=common%2Fdoor&depth=1"]

"""'회사 지식' 화면 스크립트 — node --check(파일 스물) + 순수 함수 node 시험(static/js/brain/brain-view.js).

유형 → 색 · 상태 모양 · 표 물음 글 · 쪽 안내 · 항목 주소 · 판 수 글 · 유형 지도 요소(묶음 줄이기 · 같은 두 끝 선 합치기 ·
파이썬 :func:`foms.services.brain.browse.compress_types` 와 같은 줄이기). 그림 요소는 서버 :func:`type_map_data` 자료로 만든다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from foms.services.brain.browse import type_map_data
from foms.services.brain.constants import ALLOWED_LINKS, LINK_KINDS

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "static/js/brain/brain-view.js"
SCRIPTS = sorted((ROOT / "static/js/brain").glob("*.js"))
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")


def _node(expr: str, data: object = None):
    script = (f"const v = require({json.dumps(str(VIEW))});"
              f"const data = {json.dumps(data, ensure_ascii=False)};"
              f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60,
                         check=True).stdout
    return json.loads(out)


@NODE
def test_node_check_passes_for_every_brain_script():
    assert len(SCRIPTS) == 24  # 읽기 여섯(⑤-2) + 제안함 · 다시 확인 · 카드 제안 다섯(⑤-3) + 이웃 지도 · 뇌 보기 아홉(⑤-4)
    # + 물어보기 셋(⑤-5) + '확인할 것' 네 묶음 하나(설계서 7.9)
    for path in SCRIPTS:
        subprocess.run(["node", "--check", str(path)], check=True, capture_output=True, timeout=60)


@NODE
def test_type_colour_state_shapes_and_badges():
    display = type_map_data({})["display"]
    got = _node("[v.typeInfo(data, 'product_line'), v.typeInfo(data, 'nope'),"
                " v.stateClasses({status:'draft', stale:true}), v.stateClasses({status:'retired'}),"
                " v.stateClasses({status:'active'}),"
                " v.badges({status:'retired', confidence:'observed', stale:true, needs_check:true}, data)]", display)
    assert got[0] == {"label": "제품 라인", "color": "#1d4ed8", "icon": "fa-couch"}
    assert got[1] == {"label": "nope", "color": "#475569", "icon": "fa-circle"}
    assert got[2] == ["brain-state--draft", "brain-state--stale"]
    assert got[3] == ["brain-state--retired"] and got[4] == []
    assert got[5] == [{"text": "은퇴", "cls": "brain-badge--retired"}, {"text": "관찰", "cls": "brain-badge--observed"},
                      {"text": "낡음", "cls": "brain-badge--stale"}, {"text": "확인 필요", "cls": "brain-badge--check"}]


@NODE
def test_table_params_pager_item_href_and_counts_text():
    display = type_map_data({})["display"]
    got = _node("[v.tableParams({sort:'checked', type:'build_rule', layer:'', check:'stale', page:3}),"
                " v.tableParams({type:'spec', page:1}), v.pager(2, 3, 45, 20), v.pager(1, 1, 0, 20),"
                " v.itemHref('/brain/items/', 'calc:a b/문짝'), v.countsText({update:1, create:3}, data)]", display)
    assert got[0] == "type=build_rule&check=stale&sort=checked&page=3"  # 정한 차례 · 빈 값 빠짐
    assert got[1] == "type=spec"
    assert got[2] == {"hasPrev": True, "hasNext": True, "text": "21–40 / 모두 45개 (2/3쪽)"}
    assert got[3] == {"hasPrev": False, "hasNext": False, "text": "항목이 없습니다"}
    assert got[4] == "/brain/items/calc%3Aa%20b/%EB%AC%B8%EC%A7%9D"
    assert got[5] == "새로 만듦 3 · 고침 1"


@NODE
def test_map_elements_compress_whole_groups_and_merge_parallel_lines():
    data = type_map_data({"product_line": 4, "build_rule": 2})
    els = _node("v.mapElements(data, data.display)", data)
    nodes = {e["data"]["id"]: e for e in els if e["group"] == "nodes"}
    edges = {e["data"]["id"]: e["data"] for e in els if e["group"] == "edges"}
    groups = [n for n in nodes.values() if n["data"].get("kind") == "group"]
    assert len(groups) == 7  # + 바깥 사본(7.8 다음 6)
    types = [n for n in nodes.values() if n["data"].get("kind") == "type"]
    assert len(types) == 31 and all(n["data"]["parent"] in nodes for n in types)  # 유형 24 + 바깥 자리 7
    assert nodes["t:product_line"]["data"]["label"] == "제품 라인\n4개" and nodes["t:product_line"]["data"]["color"] == "#1d4ed8"
    assert "is-empty" in nodes["t:spec"]["classes"] and "is-external" in nodes["t:ext_calculator"]["classes"]
    assert all(e["source"] in nodes and e["target"] in nodes for e in edges.values())
    # 관찰 전체 → 정체 항목 묶음 셋(54 짝이 선 3개로) · 공통 바탕 전체 → 기준 답 문구
    assert {k for k in edges if k.startswith("e:g:observation>")} == {
        "e:g:observation>g:common", "e:g:observation>g:cs", "e:g:observation>g:drawing"}
    assert edges["e:g:common>t:template"]["kinds"] == ["copy_in"]
    # 같은 두 끝의 선은 하나로(필요 · 제외)
    assert edges["e:t:build_rule>t:product_line"]["kinds"] == ["applies_to", "requires", "excludes"]
    assert edges["e:t:build_rule>t:product_line"]["label"] == "적용 · 필요 · 제외"
    assert edges["e:t:product_line>g:external"]["kinds"] == ["value_from"]
    kinds = {k for e in edges.values() for k in e["kinds"]}
    # 짝 있는 종류는 모두 그림에(원인 · 고침은 판 3) — 같은 유형끼리(broader)는 자기 자신 선뿐이라 범례에만
    assert kinds == {k for k in LINK_KINDS if ALLOWED_LINKS[k][0]} - {"broader"}
    assert len(edges) < 75  # 실뭉치 막기 — 짝 그대로면 290 개가 넘는다(7.8 링크 일곱 뒤)


@NODE
def test_js_and_python_compress_the_same_way():
    data = type_map_data({})
    for link in data["links"]:
        if not link["pairs"]:
            continue
        starts = list(dict.fromkeys(p[0] for p in link["pairs"]))
        js = _node("v.compressEnds(data.starts, data.groups)", {"starts": starts, "groups": data["groups"]})
        py = [("g:" + e["group"]) if "group" in e else ("t:" + e["type"]) for e in link["from"]]
        assert sorted(js) == sorted(py), link["kind"]


@NODE
def test_map_style_is_plain_data_with_the_page_font():
    style = _node("v.mapStyle('Malgun Gothic')")
    selectors = [s["selector"] for s in style]
    assert "node.brain-map-type" in selectors and "node.brain-map-group" in selectors and "edge.is-lit" in selectors
    node = next(s for s in style if s["selector"] == "node.brain-map-type")["style"]
    assert node["font-family"] == "Malgun Gothic" and node["background-color"] == "data(color)"

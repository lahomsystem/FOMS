"""도면 마법사 그림 종류 자동 분류·자동 배치 계약 테스트.

설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md (§3.1 이름표 · §3.2 자동 배치)
- 서버 검증(_PART_LABELS) · 마법사(PART_LABELS) · 브라우저 AI(KEY_LABELS) 의 닫힌 목록이 같아야 한다.
- 분류기 가중치(part-head.json)는 브라우저가 그대로 읽는 꼴이어야 한다.
- 자동 배치(part-layout.js + part-pack.js)는 순수 계산이라 node 로 돌려 결정성·칸·자재표 자리·겹침·짝 순서·
  같은 배율·확대 상한·글자 크기(너무 작음) 판정을 본다. 치수 글자 재기(part-textsize.js)도 node 로 합성 그림을 잰다.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from foms.api.drawing import wizard as wizard_api

ROOT = Path(__file__).resolve().parents[2]
JS = {
    "part_ai": ROOT / "static/js/drawing/part-ai.js",
    "part_arrange": ROOT / "static/js/drawing/part-arrange.js",
    "part_layout": ROOT / "static/js/drawing/part-layout.js",
    "part_pack": ROOT / "static/js/drawing/part-pack.js",
    "part_pair": ROOT / "static/js/drawing/part-pair.js",
    "part_split": ROOT / "static/js/drawing/part-split.js",
    "part_textsize": ROOT / "static/js/drawing/part-textsize.js",
    "wizard": ROOT / "static/js/drawing/wizard.js",
}
HEAD = ROOT / "static/js/drawing/part-head.json"
TEMPLATE = ROOT / "templates/drawing/wizard.html"


def _node():
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


@pytest.mark.parametrize("name", sorted(JS))
def test_node_check(name):
    proc = subprocess.run([_node(), "--check", str(JS[name])], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr


def _js_list(path, var_name):
    text = path.read_text(encoding="utf-8")
    m = re.search(var_name + r"\s*=\s*\[([^\]]*)\]", text)
    assert m, f"{var_name} not found in {path.name}"
    return re.findall(r"'([^']+)'", m.group(1))


def test_part_labels_match_server_and_browser():
    server = list(wizard_api._PART_LABELS)
    wizard_labels = _js_list(JS["wizard"], "var PART_LABELS")
    ai_labels = _js_list(JS["part_ai"], "var LABELS")
    assert wizard_labels == server
    # 브라우저 AI 는 '미분류'를 따로 붙인다(LABELS + UNSURE = 숫자키 1~9, 0)
    assert ai_labels + ["미분류"] == server


def test_head_json_shape_matches_browser_contract():
    head = json.loads(HEAD.read_text(encoding="utf-8"))
    assert set(head["labels"]) <= set(wizard_api._PART_LABELS) - {"미분류"}
    assert len(head["W"]) == len(head["labels"]) == len(head["b"])
    assert all(len(row) == 768 for row in head["W"])
    assert re.fullmatch(r"[A-Za-z0-9._-]{1,16}", head["version"])
    assert 0 < head["threshold"] < 1
    assert head["model"]["url"].startswith("https://huggingface.co/onnx-community/dinov2-small/resolve/")


def test_template_loads_part_scripts_deferred_with_pin():
    html = TEMPLATE.read_text(encoding="utf-8")
    for name in ("part-ai.js", "part-pack.js", "part-layout.js", "part-split.js", "part-textsize.js", "part-arrange.js",
                 "part-pair.js"):
        tag = re.search(r'<script src="[^"]*' + re.escape(name) + r'[^"]*"[^>]*>', html)
        assert tag, name
        assert "?v=" in tag.group(0) and " defer" in tag.group(0)
    assert 'data-head-url="' in html
    # part-layout.js 는 part-pack.js 를 쓰고, wizard.js 는 셋 다 쓴다(defer 는 적힌 순서대로 돈다)
    pos = {n: html.index("js/drawing/" + n) for n in ("part-pack.js", "part-layout.js", "part-split.js", "part-textsize.js",
                                                       "part-arrange.js", "wizard.js")}
    assert pos["part-pack.js"] < pos["part-layout.js"] < pos["part-split.js"] < pos["wizard.js"]   # 나누기 계획은 배치 계산을 쓴다
    assert pos["part-textsize.js"] < pos["wizard.js"] and pos["part-arrange.js"] < pos["wizard.js"]


# 자동 배치(part-layout.js · part-pack.js · part-textsize.js · part-arrange.js) 시험은
# test_drawing_part_layout_contract.py 에 있다(이 파일이 500줄 래칫을 넘지 않게).


PAIR_RUNNER = r"""
global.window = {};
require(process.argv[1]);
const P = window.FomsPartPair, job = JSON.parse(process.argv[2]);
const out = {};
for (const [name, items] of Object.entries(job.cases)) {
  out[name] = Object.fromEntries(P.pairLabels(items, 0.5).map(r => [r.id, r.label]));
}
out.kitchen = job.names.map(P.isKitchen);
out.hatch = P.hatchFromPixels(Buffer.from(job.rgba, 'base64'), job.w, job.h);
process.stdout.write(JSON.stringify(out));
"""


def test_kitchen_pair_rule_and_hatch_formula():
    """주방 짝 규칙(설계서 §3.1) — 같은 보기 딱 두 장이면 빗금 많은 쪽이 내부, 차이 0.05 미만·세 장이면 모델 짐작 그대로."""
    import base64

    from PIL import Image, ImageDraw

    def it(i, ai, conf, hatch, label=None):
        return {"id": i, "ai": ai, "conf": conf, "hatch": hatch, "label": label or (ai if conf >= 0.5 else "미분류")}

    img = Image.new("RGB", (60, 40), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([2, 2, 57, 37], outline=(0, 0, 0))
    for x in range(6, 56, 6):
        draw.line([(x, 4), (x - 4, 36)], fill=(180, 180, 180))
    gray = img.convert("L")
    px = list(gray.getdata())
    ink = sum(1 for v in px if v < 230)
    py_hatch = sum(1 for v in px if 150 <= v <= 215) / max(1, ink)   # 1단계 실험 all_label.hatch 와 같은 식

    job = {
        "cases": {
            "swap": [it("a", "정면·도어", 0.9, 0.42), it("b", "정면·도어", 0.8, 0.10), it("p", "사진", 0.9, None)],
            "close": [it("a", "정면·도어", 0.9, 0.30), it("b", "정면·내부", 0.7, 0.27)],
            "three": [it("a", "입체·도어", 0.9, 0.5, label="입체·내부"), it("b", "입체·도어", 0.9, 0.1),
                      it("c", "입체·내부", 0.4, 0.3)],
            "unsure": [it("a", "입체·내부", 0.3, 0.05), it("b", "입체·도어", 0.45, 0.6), it("f", "정면·내부", 0.9, 0.2)],
        },
        "names": ["주방 하부장", "아일랜드 식탁", "양문형 냉장고장", "몰딩 여닫이 붙박이장"],
        "rgba": base64.b64encode(img.convert("RGBA").tobytes()).decode(), "w": 60, "h": 40,
    }
    proc = subprocess.run([_node(), "-e", PAIR_RUNNER, str(JS["part_pair"]), json.dumps(job)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    res = json.loads(proc.stdout)
    assert res["swap"] == {"a": "정면·내부", "b": "정면·도어", "p": "사진"}
    assert res["close"] == {"a": "정면·도어", "b": "정면·내부"}                      # 차이 0.03 — 그대로
    assert res["three"] == {"a": "입체·도어", "b": "입체·도어", "c": "미분류"}        # 짝이 깨지면 모델 짐작으로
    assert res["unsure"] == {"a": "입체·도어", "b": "입체·내부", "f": "정면·내부"}    # 확신이 낮아도 짝이면 정함
    assert res["kitchen"] == [True, True, False, False]
    assert abs(res["hatch"] - py_hatch) < 0.02
    # 학습 이름표 화면(이름 딱지·Enter 맞음·여러 장 숫자키·짝 풀림 안내)은 test_drawing_part_badges.py — 500줄 래칫


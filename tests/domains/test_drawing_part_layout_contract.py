"""도면 마법사 자동 배치 계약 테스트(사용성 평가 2026-10-25 막힘-1·큼-5·큼-6·큼-8).

설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.2
- 자동 배치(part-layout.js + part-pack.js)는 순수 계산이라 node 로 돌려 결정성 · 놓는 칸(테두리 안·머리칸 아래·아래 표 위)
  · 자재표 자리 · 장애물 · 겹침 · 짝 순서(내부 왼쪽) · 같은 배율 · 확대 상한 · 글자 크기(너무 작음) 판정을 본다.
- 치수 글자 재기(part-textsize.js)는 합성 그림으로, 시트 도우미(part-arrange.js)는 자재표 자리·순서·층·선택 창 글을 본다.
- wizard.js 연결(고른 파일 순서 · 글자 재기 · 늦게 온 이름 · 자리 기록 · 되돌리기 한 번)은 원문 계약으로 본다.
(test_drawing_part_ai_contract.py 가 500줄 래칫을 넘지 않게 따로 둔다.)
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JS = {
    "part_arrange": ROOT / "static/js/drawing/part-arrange.js",
    "part_layout": ROOT / "static/js/drawing/part-layout.js",
    "part_pack": ROOT / "static/js/drawing/part-pack.js",
    "part_textsize": ROOT / "static/js/drawing/part-textsize.js",
    "wizard": ROOT / "static/js/drawing/wizard.js",
}


def _node():
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


def _node_json(runner, scripts, payload):
    """node 러너에 자료는 표준 입력으로 넘긴다(Windows 명령줄 길이 한도를 넘지 않게)."""
    proc = subprocess.run([_node(), "-e", runner] + [str(s) for s in scripts], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _fn_body(src, name):
    start = src.index("function " + name + "(")
    return src[start:src.index("\n  }\n", start)]


@pytest.mark.parametrize("name", ["part_arrange", "part_layout", "part_pack", "part_textsize"])
def test_part_layout_scripts_stay_under_ratchet(name):
    assert len(JS[name].read_text(encoding="utf-8").splitlines()) < 300   # 새 JS 300줄 래칫


LAYOUT_RUNNER = r"""
global.window = {};
require(process.argv[1]);
require(process.argv[2]);
const job = JSON.parse(require('fs').readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(job.map(j => window.FomsPartLayout.arrange(j.items, j.area, j.obstacles, j.opts))));
"""

# 실제 시트 좌표: 테두리 안쪽 8px(43+8 ~ 1437−8) · 머리칸 바닥 95 + 8 · 아래 표 899 − 12
AREA = {"x0": 51, "y0": 103, "x1": 1429, "y1": 887}
# 새 시트 자리표 다섯 개(x 628~1380, y 120, 두 줄 50) → 자재표 자리 x 620~1429, y 103 ~ max(170+50, 120+9×25)+8 = 353
RESERVE = {"x": 620, "y": 103, "w": 809, "h": 250}
OBSTACLES = [{"x": 1366, "y": 32, "w": 82, "h": 65}, {"x": 52, "y": 760, "w": 140, "h": 60}]   # 쪽번호 칸 · 손으로 쓴 글자


def _arrange_many(jobs):
    return _node_json(LAYOUT_RUNNER, [JS["part_pack"], JS["part_layout"]], jobs)


def _job(items, area=AREA, obstacles=OBSTACLES, reserve=RESERVE):
    return {"items": items, "area": area, "obstacles": obstacles, "opts": {"reserve": reserve}}


def _overlap(a, b):
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]


def _sheet_items():
    """견본 도면(모듈 3짝 + 입체 + 평면 + 서랍 + 사진 + 작은 원본)과 같은 크기·글자 높이. 파일 순서는 일부러 섞어 둠."""
    def it(i, nw, nh, label, order, tx):
        return {"id": i, "nw": nw, "nh": nh, "label": label, "order": order, "tx": tx}
    return [
        it("m1-door", 370, 598, "정면·도어", 0, 26),     # 도어를 먼저 골라도 내부가 왼쪽
        it("m1-in", 370, 598, "정면·내부", 1, 26),
        it("m2-in", 232, 580, "정면·내부", 2, 27),
        it("m2-door", 232, 580, "부품 상세", 3, 27),     # AI 가 도어를 부품으로 틀림 — 크기가 정면과 같아 짝
        it("m3-in", 292, 598, "미분류", 4, 27),          # 한쪽이 미분류여도 크기가 같으면 짝
        it("m3-door", 292, 598, "정면·도어", 5, 27),
        it("iso", 1222, 652, "입체·도어", 6, 25),
        it("plan", 1004, 832, "평면·상판", 7, 26),
        it("drawer", 401, 336, "서랍 단면", 8, 22),
        it("photo", 390, 520, "사진", 9, 13),
        it("low", 207, 139, "미분류", 10, 29),          # 작은 원본 — 확대는 1.25배까지
    ]


def test_layout_stays_in_area_off_reserve_and_obstacles_without_overlap():
    items = _sheet_items()
    res = _arrange_many([_job(items)])[0]
    placed = {p["id"]: p for p in res["placed"]}
    assert set(placed) == {it["id"] for it in items}
    for p in placed.values():
        assert AREA["x0"] <= p["x"] and p["x"] + p["w"] <= AREA["x1"], p          # 테두리 안쪽 8px
        assert AREA["y0"] <= p["y"] and p["y"] + p["h"] <= AREA["y1"], p          # 머리칸 아래 · 아래 표 위
        assert not _overlap(p, RESERVE), p                                         # 자재표가 자랄 자리는 비움
        assert not any(_overlap(p, o) for o in OBSTACLES), p
    rects = list(placed.values())
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert not _overlap(a, b), (a, b)
    assert res["crowded"] is False and res["minText"] >= 8
    # '부품 상세'로 짐작했지만 정면·내부와 크기가 같아 짝의 도어 자리에 놓은 그림은 guess 로 알린다(미분류 짝은 딱지가 이미 '?')
    assert res["guess"] == {"m2-door": "정면·도어"}


def test_layout_pairs_interior_left_same_scale_and_upscale_cap():
    items = _sheet_items()
    by = {it["id"]: it for it in items}
    res = _arrange_many([_job(items)])[0]
    placed = {p["id"]: p for p in res["placed"]}
    for left, right in (("m1-in", "m1-door"), ("m2-in", "m2-door"), ("m3-in", "m3-door")):
        a, b = placed[left], placed[right]
        assert a["x"] < b["x"] and 0 <= b["x"] - (a["x"] + a["w"]) <= 20, (left, a, b)   # 내부 왼쪽 · 도어 바로 오른쪽
        assert a["y"] + a["h"] == b["y"] + b["h"], (left, a, b)                            # 같은 줄(바닥 맞춤)
    scales = [placed[i]["w"] / by[i]["nw"] for i in ("m1-in", "m1-door", "m2-in", "m2-door", "m3-in", "m3-door")]
    assert max(scales) / min(scales) <= 1.03, scales                                       # 모듈 그림은 같은 배율
    for p in placed.values():
        assert p["h"] / by[p["id"]]["nh"] <= 1.25 + 0.01, p                               # 그림마다 확대는 1.25배까지
        if by[p["id"]]["label"] != "사진":
            assert by[p["id"]]["tx"] * p["h"] / by[p["id"]]["nh"] >= 8 - 0.05, p          # 치수 글자 8px 이상


def test_layout_is_deterministic_and_follows_given_order():
    items = _sheet_items()
    shuffled = items[5:] + items[:5]                       # 넘겨준 목록 순서가 달라도 order 가 같으면 같은 답
    a, b, c = _arrange_many([_job(items), _job(items), _job(shuffled)])
    assert a == b == c
    order = [p["id"] for p in a["placed"]]
    assert order.index("m1-in") < order.index("m2-in") < order.index("m3-in")   # 모듈은 고른 순서대로


def _pairs(n, tx):
    out = []
    for i in range(n):
        out.append({"id": f"in{i}", "nw": 370, "nh": 598, "label": "정면·내부", "order": 2 * i, "tx": tx})
        out.append({"id": f"dr{i}", "nw": 370, "nh": 598, "label": "정면·도어", "order": 2 * i + 1, "tx": tx})
    return out


def test_layout_flags_crowded_by_text_size():
    few, many = _arrange_many([_job(_pairs(4, 26)), _job(_pairs(16, 26))])
    assert few["crowded"] is False and few["minText"] >= 8
    assert many["crowded"] is True and many["minText"] < 8                     # 글자가 8px 밑 → 묻기(나누기 계획은 part-split.js)
    assert len(many["placed"]) == 32                                           # '그래도 이 시트에' 용 배치는 다 들어감
    for i, a in enumerate(many["placed"]):
        for b in many["placed"][i + 1:]:
            assert not _overlap(a, b)


def _it(i, nw, nh, label, order, tx):
    return {"id": i, "nw": nw, "nh": nh, "label": label, "order": order, "tx": tx}


def _row_scale(p, it):
    return p["h"] / it["nh"]


def test_layout_keeps_iso_pair_together_and_fills_space():
    """실화면 QA1(같은 8장): 입체·내부와 입체·도어(둘 다 1222×652)는 한 묶음 — 같은 배율로 나란히, 내부 왼쪽.
    QA3 실험1(10장): 큰 그림(모듈) 높이 295 → 360 이상, 가장 큰 빈 칸이 크게 남지 않는다."""
    qa1 = [_it("door", 1104, 654, "정면·도어", 0, 26.2), _it("in", 1104, 654, "정면·내부", 1, 26.2),
           _it("iso-in", 1222, 652, "입체·내부", 2, 26), _it("iso-door", 1222, 652, "입체·도어", 3, 24.4),
           _it("plan", 1004, 832, "평면·상판", 4, 26.4), _it("top", 820, 718, "평면·상판", 5, 28.7),
           _it("drawer", 401, 336, "서랍 단면", 6, 22), _it("photo", 390, 520, "사진", 7, 21)]
    exp1 = [_it("m1-in", 370, 598, "정면·내부", 0, 27), _it("m1-door", 370, 598, "정면·도어", 1, 27),
            _it("m2-in", 232, 580, "정면·내부", 2, 27), _it("m2-door", 232, 580, "부품 상세", 3, 27),
            _it("m4-in", 292, 598, "정면·내부", 4, 27), _it("m4-door", 292, 598, "정면·도어", 5, 27),
            _it("iso", 1222, 652, "미분류", 6, 24.4), _it("plan", 1004, 832, "평면·상판", 7, 26.4),
            _it("drawer", 401, 336, "서랍 단면", 8, 22), _it("photo", 390, 520, "사진", 9, 21)]
    seed = [{"x": 1366, "y": 32, "w": 82, "h": 65}]
    a, b = _arrange_many([_job(qa1, obstacles=seed), _job(exp1, obstacles=seed)])
    pa, by = {p["id"]: p for p in a["placed"]}, {it["id"]: it for it in qa1}
    for left, right in (("in", "door"), ("iso-in", "iso-door")):
        x, y = pa[left], pa[right]
        assert x["x"] < y["x"] and 0 <= y["x"] - (x["x"] + x["w"]) <= 20 and x["y"] + x["h"] == y["y"] + y["h"], (x, y)
        assert abs(_row_scale(x, by[left]) - _row_scale(y, by[right])) < 0.01, (x, y)
    assert a["crowded"] is False and a["minText"] >= 8
    pb = {p["id"]: p for p in b["placed"]}
    assert b["crowded"] is False and min(pb[i]["h"] for i in ("m1-in", "m4-in")) >= 360, b
    assert sum(p["w"] * p["h"] for p in b["placed"]) / ((1378 * 784) - 809 * 250) > 0.55   # 채운 넓이(자재표 자리 뺀 칸)


def test_layout_spills_tail_modules_into_free_space_at_same_scale():
    """실화면 QA1: 주방 앞모습 2장 + 붙박이장 앞모습 2장 — 줄에 다 안 들어가는 뒤쪽 모듈은 같은 배율로 자재표 왼쪽 빈 칸에.
    예전에는 한 줄에 모두 넣느라 글자가 6px 로 작아져 나누기 창이 떴다."""
    items = [_it("k-in", 1022, 1033, "정면·내부", 0, 31), _it("k-door", 1020, 1033, "정면·도어", 1, 31),
             _it("w-door", 1104, 654, "정면·도어", 2, 26.2), _it("w-in", 1440, 610, "정면·내부", 3, 23.4)]
    res = _arrange_many([_job(items, obstacles=[{"x": 1366, "y": 32, "w": 82, "h": 65}])])[0]
    assert res["crowded"] is False and res["minText"] >= 8, res
    by, pl = {it["id"]: it for it in items}, {p["id"]: p for p in res["placed"]}
    scales = [_row_scale(pl[i], by[i]) for i in by]
    assert max(scales) / min(scales) <= 1.03, scales                          # 모듈은 모두 같은 배율 그대로
    for p in pl.values():
        assert not _overlap(p, RESERVE), p


def test_layout_unknown_photo_not_bigger_than_rows():
    """실화면 QA1(분류 35초 늦춤): 이름 없이 놓을 때 방 사진(미분류)이 가장 큰 자리(512×384)를 차지했다 —
    종류를 모르는 그림은 줄 배율보다 크게 놓지 않는다(치수 글자는 지킨다)."""
    items = [_it("in", 1134, 876, "미분류", 0, 32.6), _it("door", 1026, 974, "미분류", 1, 26.9),
             _it("photo", 552, 414, "미분류", 2, 12)]
    res = _arrange_many([_job(items, obstacles=[{"x": 1366, "y": 32, "w": 82, "h": 65}])])[0]
    by, pl = {it["id"]: it for it in items}, {p["id"]: p for p in res["placed"]}
    assert res["crowded"] is False
    assert pl["photo"]["w"] * pl["photo"]["h"] < min(pl["in"]["w"] * pl["in"]["h"], pl["door"]["w"] * pl["door"]["h"])
    assert _row_scale(pl["photo"], by["photo"]) <= max(res["scale"], 8 / 12) + 0.01


def test_layout_aims_rest_text_above_floor_without_shrinking_modules():
    """실화면 V3: 모듈을 키운 두 번째 고침 뒤 평면·입체가 하한 8px 쪽으로 몰렸다(실험2 입체 짝 8.0 · 실험3 s16-door 8.4).
    남은 칸 그림은 먼저 치수 글자 9.5px 로 놓아 보고, 점수도 가장 작은 글자를 본다 — 모듈 크기는 거의 그대로."""
    seed = [{"x": 1366, "y": 32, "w": 82, "h": 65}]
    exp2 = [_it("m1-in", 370, 598, "정면·내부", 0, 27), _it("m1-door", 370, 598, "정면·도어", 1, 27),
            _it("m2-in", 232, 580, "정면·내부", 2, 27), _it("m2-door", 232, 580, "부품 상세", 3, 27),
            _it("m3-in", 234, 580, "정면·내부", 4, 27), _it("m3-door", 234, 580, "부품 상세", 5, 27),
            _it("m4-in", 292, 598, "정면·내부", 6, 27), _it("m4-door", 292, 598, "정면·도어", 7, 27),
            _it("iso-in", 1222, 652, "입체·내부", 8, 24.4), _it("iso-door", 1222, 652, "미분류", 9, 24.4),
            _it("plan", 1004, 832, "평면·상판", 10, 26.4), _it("drawer12", 401, 336, "서랍 단면", 11, 22),
            _it("drawer13", 598, 300, "서랍 단면", 12, 26), _it("photo", 390, 520, "사진", 13, 21)]
    exp3 = [_it("m1-in", 335, 536, "미분류", 0, 24), _it("m2-in", 207, 525, "정면·내부", 1, 23),
            _it("m3-in", 210, 525, "정면·내부", 2, 23), _it("m4-in", 207, 525, "정면·내부", 3, 29),
            _it("s16-door", 1392, 826, "입체·도어", 4, 24.4), _it("low", 207, 142, "미분류", 5, 29),
            _it("wideplan", 1079, 290, "평면·상판", 6, 16.2), _it("photo", 344, 458, "사진", 7, 10)]
    a, b = _arrange_many([_job(exp2, obstacles=seed), _job(exp3, obstacles=seed)])
    for res in (a, b):
        assert res["crowded"] is False and res["minText"] >= 9.5 - 0.05, res["minText"]   # 예전 8.0 · 8.4
        assert res["photo"] >= 120                                                         # 현장 사진 높이 하한
    pa, pb = {p["id"]: p for p in a["placed"]}, {p["id"]: p for p in b["placed"]}
    assert 27 * pa["m1-in"]["h"] / 598 >= 11                                    # 실험2 모듈 글자 12.1 → 11.2
    assert min(pb[i]["h"] for i in ("m2-in", "m3-in", "m4-in")) >= 345          # 실험3 모듈은 그대로(350, 글자 15px)


def test_layout_without_text_size_falls_back_to_row_height():
    few, many = _arrange_many([_job(_pairs(2, 0)), _job(_pairs(60, 0))])      # 글자 높이를 못 잰 그림만
    assert few["crowded"] is False and few["minText"] is None
    assert many["crowded"] is True and many["mainH"] < 150


TEXTSIZE_RUNNER = r"""
global.window = {};
require(process.argv[1]);
const job = JSON.parse(require('fs').readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(job.map(j => window.FomsPartTextSize.fromPixels(Buffer.from(j.rgba, 'base64'), j.w, j.h, j.scale))));
"""


def test_textsize_reads_digit_height_on_shrunken_drawing():
    """치수 글자 높이 = 숫자 꼴 덩어리 높이의 중앙값(원본 픽셀). 긴 변 800 으로 줄여 재도 원본 높이로 돌려준다."""
    import base64

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1600, 900), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 1579, 879], outline="black", width=3)                 # 큰 테두리(글자 아님)
    for k in range(6):
        d.line([(60, 128 + k * 130), (1500, 128 + k * 130)], fill="black", width=2)   # 치수선(글자 아님)
    for row in range(5):
        for j in range(12):
            x, y = 90 + j * 110, 150 + row * 130
            if j % 2:
                d.rectangle([x, y, x + 3, y + 25], fill="black")              # '1' 꼴: 높이 26
            else:
                d.ellipse([x, y, x + 13, y + 25], outline="black", width=3)   # '0' 꼴: 높이 26
    small = img.resize((800, 450), Image.BOX)
    blank = Image.new("RGB", (400, 300), "white")
    job = [{"rgba": base64.b64encode(im.convert("RGBA").tobytes()).decode(), "w": im.width, "h": im.height, "scale": sc}
           for im, sc in ((img, 1), (small, 0.5), (blank, 1))]
    full, shrunk, none = _node_json(TEXTSIZE_RUNNER, [JS["part_textsize"]], job)
    assert abs(full - 26) <= 1 and abs(shrunk - 26) <= 3, (full, shrunk)
    assert none == 0                                                           # 숫자 꼴이 없으면 모름


ARRANGE_RUNNER = r"""
global.window = {};
require(process.argv[1]);
const A = window.FomsPartArrange, job = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const ids = list => list.map(o => o.id);
process.stdout.write(JSON.stringify({
  zone: job.zones.map(z => A.bomZone(z, job.area)),
  bom: job.texts.map(A.isBomText),
  order: A.order(job.images, job.seq),
  reorder: ids(A.reorder(job.objects, job.placed)),
  sigSame: A.signature(job.objects) === A.signature(JSON.parse(JSON.stringify(job.objects))),
  sigMoved: A.signature(job.objects) === A.signature(job.objects.map(o => Object.assign({}, o, o.id === 'i1' ? { x: o.x + 1 } : {}))),
  lines: [A.crowdedLines(4.7, job.split, { room: 8 }), A.crowdedLines(null, null, { room: 0 }),
    A.crowdedLines(5.2, { sheets: [['a']], ok: false, counts: [{ n: 1 }] }, { room: 4 }),
    A.crowdedLines(5.2, Object.assign({}, job.split, { ok: false }), { room: 2 })],
  seeds: A.seedRects([{ x: 628, y: 120, text: '[SR]\n' }, { x: 1308, y: 120, text: '[마이다]\n' }], 20),
  notes: [A.skippedNote(0, 0), A.skippedNote(1, 0), A.skippedNote(2, 1)],
  guess: [A.guessNote([]), A.guessNote(['정면·도어']), A.guessNote(['정면·도어', '입체·도어'])],
  v3: [A.crowdedLines(4.7, job.split, { room: 8, skipped: 2 }), A.crowdedLines(9.4, job.split, { room: 8, photo: 84.6, photoMin: 120 }),
    A.crowdedLines(null, null, { room: 0, skipped: 1 })],
  kept: [A.keptText({ crowded: false }), A.keptText({ crowded: true, minText: 5.4 }), A.keptText({ crowded: true, minText: null }),
    A.keptText({ crowded: true, why: 'photo', photo: 86, minText: 12.1 })],
}));
"""


def test_arrange_helpers_reserve_order_layers_and_dialog_text():
    seed = [{"x": 628 + 170 * i, "y": 120, "w": 40, "h": 50, "line": 25} for i in range(5)]
    long_bom = seed[:2] + [{"x": 968, "y": 120, "w": 140, "h": 400, "line": 25}]
    moved = [{"x": 300, "y": 600, "w": 60, "h": 50, "line": 25}]
    job = {
        "area": AREA,
        "zones": [seed, long_bom, moved, []],
        "texts": ["[SR]\n", "  [마이다]\n466*235=3", "메모", "", "SR 110"],
        # a 는 전부터 있던 그림, b·c·d 는 같이 올린 묶음(업로드가 끝난 순서 b → c → d, 고른 순서 c → d → b)
        "images": [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}],
        "seq": {"b": [1, 2], "c": [1, 0], "d": [1, 1]},
        "objects": [{"id": "t1", "type": "text"}, {"id": "i1", "type": "image", "x": 5, "y": 5, "w": 9, "h": 9},
                    {"id": "p1", "type": "pen"}, {"id": "i2", "type": "image", "x": 50, "y": 5, "w": 9, "h": 9},
                    {"id": "t2", "type": "text"}],
        "placed": ["i2", "i1"],
        # 실화면 QA3 20장: 이 시트 9장(모듈 5묶음) · 옮길 11장(정면 1 · 입체 5 · 평면 2 · 서랍 2 · 사진 1)
        "split": {"sheets": [["k"] * 9, ["m"] * 8, ["n"] * 3], "ok": True, "counts": [
            {"n": 9, "front": 5, "iso": 0, "other": 0, "plan": 0, "small": 0, "photo": 0},
            {"n": 8, "front": 1, "iso": 3, "other": 0, "plan": 1, "small": 2, "photo": 1},
            {"n": 3, "front": 0, "iso": 2, "other": 0, "plan": 1, "small": 0, "photo": 0}]},
    }
    res = _node_json(ARRANGE_RUNNER, [JS["part_arrange"]], job)
    assert res["zone"][0] == RESERVE                                            # 머리 아래 ~ 머리글 줄 + 9줄
    assert res["zone"][1] == {"x": 620, "y": 103, "w": 809, "h": 578 - 103}     # 친 자재표 바닥 + 2줄
    assert res["zone"][2] == {"x": 292, "y": 592, "w": 1429 - 292, "h": 833 - 592}   # 아래로 옮긴 자재표 — 그 자리부터
    assert res["zone"][3] is None
    assert res["bom"] == [True, True, False, False, False]
    assert res["order"] == {"a": 0, "c": 1, "d": 2, "b": 3}                     # 묶음 안은 고른 파일 순서
    assert res["reorder"] == ["i2", "p1", "i1", "t2", "t1"]                     # 그림은 놓은 순서, 그림 아래 글자는 맨 위
    assert res["sigSame"] is True and res["sigMoved"] is False
    crowded, full, big, short = res["lines"]
    # 실화면 QA3: '모듈'은 정면 묶음만 세고 입체 그림은 따로, 필요한 시트 수를 먼저 알린다(나눈 뒤 또 창이 뜨지 않게)
    assert crowded == [
        "이 시트에 다 넣으면 치수 글자가 4px 로 작아져요.",
        "시트 3장으로 나누면 치수 글자를 모두 8px 이상으로 놓을 수 있어요.",
        "이 시트에 9장을 두고 새 시트 2장에 11장을 옮겨요 — 모듈 1개 · 입체 그림 5장 · 평면 2장 · 서랍·부품 2장 · 사진 1장.",
        "나누면 시트마다 다시 배치해요. 이 시트에서 Ctrl+Z 한 번이면 새 시트와 옮긴 그림까지 처음대로 돌아와요.",
    ]
    assert full == ["이 시트에 다 넣으면 그림이 아주 작게 놓여요.",
                    "시트가 10장이라 더 나눌 수 없어요 — [그래도 이 시트에]로 작게 놓거나 시트를 정리해 주세요."]
    assert big[1] == "한 묶음만으로도 글자가 작아지는 큰 그림이에요 — [그래도 이 시트에]로 놓아 주세요."
    assert short[1] == "시트 3장으로 나눠도 일부 그림은 글자가 8px 보다 작아요 — 시트는 10장까지예요."
    assert res["seeds"][0] == {"x": 628, "y": 120, "w": 75, "h": 50, "line": 25}   # 새 시트 자리표 두 줄 높이
    assert res["notes"] == ["", " · 돌리거나 잠근 그림 1장은 그대로 두었어요",
                            " · 돌리거나 잠근 그림 2장은 그대로 두었어요 — 테두리 밖 1장을 골라 두었어요"]
    # 부품으로 짐작했지만 크기가 같아 도어 자리에 놓은 그림 — 숫자키로 굳히게 이끈다(실화면 QA3 '도어?' 확인)
    assert res["guess"] == ["", " · 크기가 같아 도어 자리에 놓은 그림 1장 — 맞으면 골라서 숫자키 2",
                            " · 크기가 같아 짝 자리에 놓은 그림 2장 — 종류를 확인해 주세요"]
    # 실화면 V3: 창 글에 돌리거나 잠가 그대로 둘 그림 수를 적고(마지막 Ctrl+Z 안내 바로 앞), 글자는 되는데 사진만 작아지면 사진으로 말한다
    skipped, photo, none_room = res["v3"]
    assert skipped[:3] == crowded[:3] and skipped[3] == "돌리거나 잠근 그림 2장은 그대로 둬요." and skipped[4] == crowded[3]
    assert photo[0] == "이 시트에 다 넣으면 현장 사진이 높이 84px 로 작아져요."
    assert photo[1] == "시트 3장으로 나누면 현장 사진도 높이 120px 이상으로 놓을 수 있어요." and len(photo) == 4
    assert none_room == full + ["돌리거나 잠근 그림 1장은 그대로 둬요."]
    assert res["kept"] == ["종류에 맞춰 배치했습니다 (되돌리기 Ctrl+Z)", "그림을 작게 놓았어요 — 가장 작은 글자 5px (되돌리기 Ctrl+Z)",
                           "그림을 작게 놓았어요 (되돌리기 Ctrl+Z)", "현장 사진을 작게 놓았어요 — 높이 86px (되돌리기 Ctrl+Z)"]


ASK_RUNNER = r"""
global.window = {};
const made = [];
function node(tag) {
  const n = { tag, children: [], attrs: {}, listeners: {}, className: '', textContent: '', focused: false };
  n.appendChild = c => { n.children.push(c); c.parentNode = n; return c; };
  n.removeChild = c => { n.children.splice(n.children.indexOf(c), 1); c.parentNode = null; };
  n.setAttribute = (k, v) => { n.attrs[k] = v; };
  n.addEventListener = (t, f) => { (n.listeners[t] = n.listeners[t] || []).push(f); };
  n.querySelector = sel => n.children.filter(c => sel === 'button' ? c.tag === 'button' : (' ' + c.className + ' ').indexOf(' ' + sel.slice(1) + ' ') >= 0)[0] || null;
  n.focus = () => { n.focused = true; };
  made.push(n);
  return n;
}
const root = node('div');
global.document = { createElement: node, getElementById: () => root, body: root };
require(process.argv[1]);
window.FomsPartArrange.ask({ title: 't', lines: ['a'], buttons: [{ id: null, label: '나중에 (겹친 채 두기)' },
  { id: 'keep', label: '그래도 이 시트에' }, { id: 'split', label: '시트 3장으로 나누기', primary: true }] }).then(v => {
  process.stdout.write(JSON.stringify({ picked: v }));
});
const actions = made.filter(n => n.className === 'dws-dialog-actions')[0];
process.stderr.write('');
global.ORDER = actions.children.map(b => [b.textContent, b.className, b.focused]);
process.stdout.write(JSON.stringify({ order: global.ORDER }) + '\n');
actions.children[1].listeners.click[0]();
"""


def test_crowded_dialog_stacks_buttons_with_primary_first():
    """실화면 V3(V60-20imgs-dialog.png): 단추 셋이 한 줄에 안 들어가 1920 화면에서도 주 단추만 둘째 줄로 떨어졌다 —
    세로로 쌓고 주 단추를 맨 위·'나중에'를 맨 아래(읽는 순서·Tab 순서도 같게)에, 첫 초점도 주 단추."""
    proc = subprocess.run([_node(), "-e", ASK_RUNNER, str(JS["part_arrange"])], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    first, second = proc.stdout.strip().splitlines()
    order = json.loads(first)["order"]
    assert [o[0] for o in order] == ["시트 3장으로 나누기", "그래도 이 시트에", "나중에 (겹친 채 두기)"]
    assert order[0][1] == "dws-btn dws-btn-primary" and order[0][2] is True
    assert json.loads(second) == {"picked": "keep"}                            # 단추 자리가 바뀌어도 고른 값은 그 단추 것
    css = (ROOT / "static/css/contexts/drawing/wizard.css").read_text(encoding="utf-8")
    rule = re.search(r"\.dws-arrange-dialog \.dws-dialog-actions \{([^}]*)\}", css).group(1)
    assert "flex-direction: column" in rule and "align-items: stretch" in rule


def test_wizard_wires_auto_arrange_order_text_size_late_names_and_record():
    js = JS["wizard"].read_text(encoding="utf-8")
    place = _fn_body(js, "placeImageFromKey")
    assert "partUploadSeq[o.id] = [batch.no," in place and "partTextOf(o, img)" in place
    # 같이 올린 여러 장은 되돌리기 한 번에(실화면 QA3: 고르기 뒤 Ctrl+Z 가 마지막 한 장만 지웠다)
    assert "recordBatchUndo(batch)" in place and "recordUndo()" not in place
    assert "x0: PART_FRAME.x0 + 8, y0: headBottom + 8, x1: PART_FRAME.x1 - 8, y1: partTableTop(s) - 12" in _fn_body(js, "partArea")
    plan = _fn_body(js, "partArrangePlan")
    assert "A.bomZone(boms, area)" in plan and "A.order(imgs, partUploadSeq)" in plan and "partItem(o, order)" in plan
    assert "skipped += 1" in plan and "outside.push(o.id)" in plan                  # 돌리거나 잠근 그림은 알리고 밖이면 골라 보여 줌
    assert "tx: partTextOf(o)" in _fn_body(js, "partItem")
    assert "var PART_FRAME = { x0: 43, x1: 1437, headBottom: 95, pageBox: { x: 1374, y: 40, w: 66, h: 49 } };" in js
    auto = _fn_body(js, "autoArrangeImages")
    assert "askCrowdedArrange(s, res, batch, plan)" in auto and "{ reserve: plan.reserve }" in auto
    assert "lateMsg || partArrangedText(batch)" in auto                              # 이름 없이 놓으면 '크기대로 놓았어요'
    assert "'종류를 아직 몰라 크기대로 놓았어요 — 종류가 오면 다시 놓을게요'" in _fn_body(js, "partArrangedText")
    # 30초가 지나 이름 없이 놓으려는데 글자가 작으면 묻지 않고 늦은 이름을 기다린다(이름 없는 배치로 창을 띄우지 않음)
    assert auto.index("if (!res.crowded)") < auto.index("batch.late > 0") < auto.index("askCrowdedArrange(")
    assert "batch.waiting = window.FomsPartArrange.signature(s.objects)" in auto
    apply_ = _fn_body(js, "applyPartArrangement")
    assert apply_.count("recordUndo()") == 1                                   # Ctrl+Z 한 번이면 배치 전으로
    assert "partPlace(s, res)" in apply_ and "skippedNote(plan.skipped, out.length)" in apply_
    assert "deselect()" in apply_ and "FomsPartBadges.refresh()" in apply_
    place_all = _fn_body(js, "partPlace")
    assert "arr: [p.x, p.y, p.w, p.h]" in place_all and "FomsPartArrange.reorder(s.objects" in place_all
    ask = _fn_body(js, "askCrowdedArrange")
    assert "'그래도 이 시트에'" in ask and "'나중에 (겹친 채 두기)'" in ask and "splitPartSheets(s, batch)" in ask
    assert "pick" not in ask and "Ctrl+X" not in ask                                # 잘라 붙이기 안내 대신 마법사가 직접 옮긴다
    split = _fn_body(js, "splitPartSheets")
    assert split.count("recordUndo()") == 1 and "partSplitLinks.push({ snap: snap" in split
    assert "uniqueSheetName(s.name)" in split and "form.checks = base.checks" in split
    assert "partSplitUndone();" in _fn_body(js, "undo")                         # 원래 시트 Ctrl+Z 한 번에 새 시트까지
    undone = _fn_body(js, "partSplitUndone")
    assert "redoStack.length = 0" in undone and "delete sheetHistories[sh.id]" in undone
    assert "sheetHistories[sh.id] = { undo: [], redo: [] }" in undone
    classify = _fn_body(js, "classifyPlacedImage")
    assert "partProgress(1, 0)" in classify and "partProgress(0, 1)" in classify and "latePartName(batch)" in classify
    late = _fn_body(js, "latePartName")
    assert "'종류가 늦게 와서 다시 배치했어요 · 되돌리기 Ctrl+Z'" in late and "signature(s.objects) === ref" in late
    assert "var s = currentSheet(), ref = batch.arranged || batch.waiting;" in late             # 안 건드렸을 때만 다시 배치
    assert "'종류가 늦게 왔어요 — 위의 [자동 배치]로 다시 정리할 수 있어요'" in late             # 건드렸으면 알리기만
    progress = _fn_body(js, "partProgress")
    assert "B.progress(partBusy.done, partBusy.total, { loading: !partModelReady" in progress   # 모델을 받는 동안만 '모델 받는 중'
    assert "out.arr = p.arr.map(" in _fn_body(js, "sanitizePart")             # 저장해도 자동 배치 자리가 남는다

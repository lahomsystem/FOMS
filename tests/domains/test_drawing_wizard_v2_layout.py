"""도면 마법사 V2 — 칸 묶기 · 칸 배치 계산(순수 계산, node 로 돌린다).

설계서: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §2 · §4
- 칸은 저장하지 않고 객체에서 읽는다: 그림 이름표 · 자재표 머리글 · 특이 사항/강조 문구 id 앞머리.
- 틀 두 가지(위 띠형 · 왼쪽 기둥형)를 모두 계산하고 점수가 높은 쪽(사람이 고른 틀이 있으면 그것).
- 같은 칸 그림은 같은 배율 · 확대 1.25배 상한 · 고정 그림은 옮기지 않음 · % 는 지금 양식(V1 자동 배치) 대비.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS_DIR = ROOT / "static/js/drawing"
MODULES = ["v2-slots.js", "v2-pack.js", "v2-layout.js", "v2-plan.js"]


def _node() -> str:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


RUNNER = r"""
global.window = {};
const fs = require('fs');
const [dir, layoutFile] = process.argv.slice(1, 3);
for (const f of ['part-pack.js', 'part-layout.js', 'v2-slots.js', 'v2-pack.js', 'v2-layout.js', 'v2-plan.js']) { require(dir + '/' + f); }
const S = window.FomsV2Slots, L = window.FomsV2Layout, P = window.FomsV2Plan, K = window.FomsV2Pack;
const out = {};
const img = (id, label, x, y, w, h, extra) => Object.assign({ id, type: 'image', key: id + '.png', x, y, w, h, natural_w: w, natural_h: h,
  part: label ? { label, src: 'ai', conf: 0.9 } : undefined }, extra || {});
const txt = (id, text, x, y, w, size) => ({ id, type: 'text', x, y, w, text, size: size || 20 });
"""


def _run(body: str) -> dict:
    script = RUNNER + body + "\nprocess.stdout.write(JSON.stringify(out));"
    proc = subprocess.run([_node(), "-e", script, str(JS_DIR)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_node_check_v2_modules():
    for name in MODULES + ["v2-paper.js", "v2-notes.js", "v2-left.js", "v2-right.js", "v2-chrome.js", "v2-shell.js",
                           "wizard-ui-switch.js"]:
        proc = subprocess.run([_node(), "--check", str(JS_DIR / name)], capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, (name, proc.stderr)


def test_group_reads_slots_from_labels_bom_and_id_prefixes():
    out = _run(r"""
const objs = [img('p', '사진', 0, 0, 900, 1200), img('a', '정면·내부', 0, 0, 1200, 740), img('b', '입체·도어', 0, 0, 1100, 980),
  img('d', '서랍 단면', 0, 0, 600, 450), img('f', '평면·상판', 0, 0, 800, 300), img('u', '미분류', 0, 0, 500, 500, { part: { label: '미분류', src: 'ai', ai: '부품 상세', conf: 0.3 } }),
  img('x', '그림 아님', 0, 0, 300, 300), txt('b1', '[SR]\n60*2440=2', 0, 0, 80), txt('n-1', '좌벽 스라 맞춤', 0, 0, 110),
  txt('nc-2', '뒷벽 띄움', 0, 0, 90), txt('st-1', '비규격', 0, 0, 70, 24), txt('t', '메모', 0, 0, 40),
  { id: 'r', type: 'rect', x: 0, y: 0, w: 10, h: 10 }];
const g = S.group(objs, {});
out.on = { photo: g.photo.map(o => o.id), main: g.main.map(o => o.id), detail: g.detail.map(o => o.id), plan: g.plan.map(o => o.id),
  unsorted: g.unsorted.map(o => o.id), bom: g.bom.map(o => o.id), notes: g.notes.map(o => o.id), stamp: g.stamp && g.stamp.id,
  free: g.free.map(o => o.id) };
const g2 = S.group(objs, { lowToUnsorted: false, kitchen: true });
out.off = { detail: g2.detail.map(o => o.id), unsorted: g2.unsorted.map(o => o.id), main: g2.main.map(o => o.id), iso: g2.iso.map(o => o.id) };
out.kinds = [S.detectKind('하부장 주방 ㄱ자'), S.detectKind('양문형 냉장고장'), S.detectKind('몰딩 여닫이'), S.detectKind('')];
out.noteKinds = [S.noteKind({ id: 'n-1' }), S.noteKind({ id: 'nc-2' })];
out.box = S.textBox({ x: 5, y: 6, w: 1, text: '[SR]\n', size: 20 });
""")
    assert out["on"] == {"photo": ["p"], "main": ["a", "b"], "detail": ["d"], "plan": ["f"], "unsorted": ["u", "x"],
                         "bom": ["b1"], "notes": ["n-1", "nc-2"], "stamp": "st-1", "free": ["t", "r"]}
    # 확신이 낮으면 미분류로를 끄면 AI 짐작 칸으로 · 주방이면 입체는 따로
    assert out["off"] == {"detail": ["d", "u"], "unsorted": ["x"], "main": ["a"], "iso": ["b"]}
    assert out["kinds"] == ["kitchen", "fridge", "closet", "closet"]
    assert out["noteKinds"] == ["make", "site"]
    assert out["box"]["h"] == 50 and out["box"]["w"] > 20     # 줄 2 × 20 × 1.25 · 새 자리표(폭 1)는 어림


def test_fixed_images_are_locked_rotated_or_moved_from_arr():
    out = _run(r"""
const moved = img('m', '정면·도어', 120, 100, 300, 200, { part: { label: '정면·도어', src: 'ai', arr: [100, 100, 300, 200] } });
const kept = img('k', '정면·내부', 100, 100, 300, 200, { part: { label: '정면·내부', src: 'ai', arr: [100, 100, 300, 200] } });
const g = S.group([moved, kept, img('l', '사진', 0, 0, 10, 10, { locked: true }), img('r', '사진', 0, 0, 10, 10, { rotation: 90 })], {});
out.fixed = Object.keys(g.fixed).sort();
out.off = Object.keys(S.group([moved, kept], { lockMoved: false }).fixed);
""")
    assert out["fixed"] == ["l", "m", "r"]
    assert out["off"] == []


INPUT = r"""
const input = {
  base: { in1: { w: 480, h: 300 }, door1: { w: 430, h: 390 }, dr1: { w: 230, h: 170 } },
  photo: [{ id: 'ph', nw: 900, nh: 1200, tx: 0 }],
  detail: [{ id: 'dr1', nw: 600, nh: 450, tx: 0 }], plan: [], unsorted: [],
  units: [{ slot: 'main', members: [{ id: 'in1', nw: 1200, nh: 740, tx: 0 }] }, { slot: 'main', members: [{ id: 'door1', nw: 1100, nh: 980, tx: 0 }] }],
  bom: [{ id: 'b1', w: 70, h: 125 }, { id: 'b2', w: 90, h: 175 }],
  notes: [{ id: 'n-1', w: 110, h: 21 }], stamp: { id: 'st-1', w: 90, h: 30 }
};
"""


def test_compute_two_templates_inside_area_and_picks_higher_score():
    out = _run(INPUT + r"""
const res = L.compute(input, {});
const A = L.AREA;
out.best = res.best;
out.scores = { band: res.band.score, column: res.column.score };
out.inside = ['band', 'column'].every(k => res[k].moves.every(m => m.x >= A.x0 - 1 && m.y >= A.y0 - 1 && m.x + m.w <= A.x1 + 1 && m.y + m.h <= A.y1 + 1));
const ids = r => r.moves.map(m => m.id).sort();
out.allPlaced = ['band', 'column'].every(k => JSON.stringify(ids(res[k])) === JSON.stringify(['b1', 'b2', 'door1', 'dr1', 'in1', 'n-1', 'ph', 'st-1']));
// 겹침 없음(사진 · 그림 · 자재표 · 특이 · 강조)
const over = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
out.overlap = ['band', 'column'].map(k => { const m = res[k].moves; let n = 0; for (let i = 0; i < m.length; i++) for (let j = i + 1; j < m.length; j++) if (over(m[i], m[j])) n++; return n; });
// 같은 칸 같은 배율: 큰 그림 두 장의 배율(높이/원본)이 같다
const by = id => res.band.moves.find(m => m.id === id);
out.sameScale = Math.abs(by('in1').h / 740 - by('door1').h / 980) < 0.01;
out.stampRight = by('st-1').x + by('st-1').w + L.STAMP_PAD === A.x1;
out.pref = L.compute(input, { prefer: 'column' }).best;
out.pctMain = res.band.mainPct > 0 && Math.abs(res.band.pct.in1 - by('in1').h / 300) < 1e-9;
out.pctBase = res.band.pctBase;
""")
    assert out["best"] == ("column" if out["scores"]["column"] > out["scores"]["band"] + 0.005 else "band")
    assert out["inside"] and out["allPlaced"]
    assert out["overlap"] == [0, 0]
    assert out["sameScale"] and out["stampRight"]
    assert out["pref"] == "column"                      # 사람이 고른 틀이 먼저
    assert out["pctMain"] and out["pctBase"] == "v1"   # % = V1 자동 배치 높이 대비


def test_same_scale_off_makes_equal_heights_and_upscale_is_capped():
    out = _run(r"""
const units = [{ slot: 'main', members: [{ id: 'a', nw: 200, nh: 100 }] }, { slot: 'main', members: [{ id: 'b', nw: 100, nh: 50 }] }];
const on = L.compute({ units, photo: [], detail: [], plan: [], unsorted: [], bom: [], notes: [] }, {}).band;
const off = L.compute({ units, photo: [], detail: [], plan: [], unsorted: [], bom: [], notes: [] }, { sameScale: false }).band;
const h = (r, id) => r.moves.find(m => m.id === id).h;
out.on = [h(on, 'a'), h(on, 'b')];
out.off = [h(off, 'a'), h(off, 'b')];
""")
    assert out["on"] == [125, 63] or out["on"] == [125, 62]   # 원본의 1.25배까지만 · 같은 배율(높이 비 2:1)
    assert out["off"][0] == out["off"][1]                     # 같은 높이


def test_crowded_when_smaller_than_80_percent_or_text_under_8px():
    out = _run(r"""
const many = [];
for (let i = 0; i < 9; i++) { many.push({ slot: 'main', members: [{ id: 'm' + i, nw: 1400, nh: 900, tx: 14 }] }); }
const base = {};
many.forEach(u => { base[u.members[0].id] = { w: 600, h: 400 }; });
const r = L.compute({ units: many, photo: [], detail: [], plan: [], unsorted: [], bom: [], notes: [], base }, {});
out.crowded = r[r.best].crowded;
out.minPct = r[r.best].minPct;
const ok = L.compute({ units: many.slice(0, 1), photo: [], detail: [], plan: [], unsorted: [], bom: [], notes: [], base }, {});
out.okCrowded = ok[ok.best].crowded;
""")
    assert out["crowded"] is True and out["minPct"] < 0.8
    assert out["okCrowded"] is False


def test_plan_apply_moves_objects_sets_arr_and_carries_followers():
    out = _run(r"""
const sheet = { id: 's1', form: {}, objects: [
  img('a', '정면·내부', 300, 300, 400, 250, { natural_w: 1200, natural_h: 750, part: { label: '정면·내부', src: 'ai', arr: [300, 300, 400, 250] } }),
  img('n', '정면·도어', 900, 300, 300, 300, { natural_w: 900, natural_h: 900 }),
  txt('memo', '600', 450, 400, 30),
  { id: 'ln', type: 'line', points: [320, 320, 380, 380] },
  txt('far', '멀리', 50, 820, 40),
  txt('b1', '[SR]\n60*2440=2', 600, 120, 80) ] };
const ctx = { items: imgs => imgs.map((o, i) => ({ id: o.id, nw: o.natural_w, nh: o.natural_h, tx: 0, order: i, label: o.part.label })),
  baseline: () => ({}), productText: '몰딩 여닫이', settings: {} };
const plan = P.build(sheet, ctx);
const res = plan.out[plan.out.best];
const before = { memo: { x: 450, y: 400 }, a: { x: 300, y: 300, w: 400, h: 250 } };
P.apply(sheet, res, { template: plan.out.best });
const o = id => sheet.objects.find(x => x.id === id);
const a = o('a');
out.arr = a.part.arr;
out.rect = [a.x, a.y, a.w, a.h];
// 메모는 그림 안 같은 비율 자리로 따라간다
const fx = (450 - 300) / 400, fy = (400 - 300) / 250;
out.memo = [o('memo').x, o('memo').y];
out.memoWant = [Math.round(a.x + fx * a.w), Math.round(a.y + fy * a.h)];
out.line = o('ln').points;
out.lineWant = [320, 320, 380, 380].map((v, i) => Math.round(i % 2 ? a.y + (v - 300) * a.h / 250 : a.x + (v - 300) * a.w / 400));
out.far = [o('far').x, o('far').y];
out.layout = sheet.form.v2_layout;
out.newHasArr = !!(o('n').part && o('n').part.arr);
out.bomMoved = o('b1').y !== 120;
""")
    assert out["arr"] == out["rect"]
    assert out["memo"] == out["memoWant"] and out["line"] == out["lineWant"]
    assert out["far"] == [50, 820]                  # 그림 밖 글자는 그대로
    assert out["layout"] in ("band", "column")
    assert out["newHasArr"] and out["bomMoved"]


def test_split_groups_keeps_pairs_and_moves_about_half():
    out = _run(r"""
const plan = { input: { units: [
  { slot: 'main', members: [{ id: 'i1', nw: 1000, nh: 700 }, { id: 'd1', nw: 1000, nh: 700 }] },
  { slot: 'main', members: [{ id: 'i2', nw: 1000, nh: 700 }, { id: 'd2', nw: 1000, nh: 700 }] },
  { slot: 'main', members: [{ id: 'k', nw: 900, nh: 900 }] }], detail: [{ id: 's', nw: 300, nh: 200 }], plan: [] } };
out.g = P.splitGroups(plan);
out.none = P.splitGroups({ input: { units: [{ slot: 'main', members: [{ id: 'x', nw: 1, nh: 1 }] }], detail: [], plan: [] } });
""")
    moved = out["g"][0]
    assert ("i2" in moved) == ("d2" in moved) and ("i1" in moved) == ("d1" in moved)   # 짝은 가르지 않는다
    assert "i1" not in moved and moved                                               # 첫 묶음은 남는다
    assert out["none"] is None


def test_unsorted_row_does_not_shrink_big_pictures():
    out = _run(INPUT + r"""
const base = L.compute(input, { prefer: 'band' }).band;
const withU = L.compute(Object.assign({}, input, { unsorted: [{ id: 'u1', nw: 600, nh: 450 }] }), { prefer: 'band' }).band;
const h = (r, id) => r.moves.find(m => m.id === id).h;
out.main = [h(base, 'in1'), h(withU, 'in1')];
const u = withU.moves.find(m => m.id === 'u1');
out.uBottom = u.y + u.h;
out.uH = u.h;
out.slot = withU.slots.find(s => s.key === 'unsorted');
""")
    assert out["main"][1] >= 0.75 * out["main"][0]       # 예전엔 미분류 한 장에 큰 그림이 반으로 줄었다
    assert out["uBottom"] <= 848 and out["slot"]["w"] <= 1374
    assert out["slot"]["w"] <= 200 or out["uH"] <= 170 - 24     # 오른쪽 좁은 기둥 또는 맨 아래 낮은 줄


def test_ai_slot_guess_places_unsure_pictures_and_titles_follow_contents():
    """세부 확신이 낮아 미분류여도 칸 확신(form.v2_ai)이 있으면 그 칸 — 이름표는 미분류 그대로(사람 확인). 칸 이름은 든 그림 종류."""
    out = _run(r"""
const u = (id, ai, conf) => img(id, null, 0, 0, 600, 500, { part: { label: '미분류', src: 'ai', ai, conf } });
const objs = [img('c1', '입체·내부', 0, 0, 1700, 1200), u('cc', '정면·도어', 0.36), u('w1', '입체·내부', 0.36),
  u('dd', '정면·도어', 0.3), u('xx', '부품 상세', 0.2), img('t1', '평면·상판', 0, 0, 1300, 1000),
  img('d1', '서랍 단면', 0, 0, 500, 400), img('d2', '부품 상세', 0, 0, 400, 240),
  img('me', null, 0, 0, 600, 500, { part: { label: '미분류', src: 'user', ai: '정면·도어', conf: 0.3 } })];
const text = 'cc=f68 w1=f76 dd=d55 me=f90 gone=i70 bad=z50';
const guess = S.parseGuess(text);
const g = S.group(objs, { guess });
const ids = k => g[k].map(o => o.id);
out.guessKeys = Object.keys(guess).sort();
out.main = ids('main'); out.detail = ids('detail'); out.unsorted = ids('unsorted');
out.labels = [g.labels.cc, g.labels.w1, g.lay.cc, g.lay.w1, g.lay.dd];
out.guessed = Object.keys(g.guess).sort();
out.titles = [S.title('main', g, false), S.title('detail', g, false), S.title('plan', g, false), S.title('unsorted', g, false)];
const empty = S.group([], {});
out.empty = [S.title('main', empty, false), S.title('main', empty, true), S.title('iso', empty, true), S.title('detail', empty, false)];
const k = S.group(objs, { guess, kitchen: true });
out.kitchen = [k.main.map(o => o.id), k.iso.map(o => o.id), S.title('main', k, true), S.title('iso', k, true)];
out.off = S.group(objs, { guess, lowToUnsorted: false }).labels.cc;
out.fmt = S.formatGuess(guess, objs);
const many = {}; for (let i = 0; i < 80; i++) { many['o-' + i + 'abcdef'] = { fam: 'f', conf: 0.6 }; }
const manyObjs = Object.keys(many).map(id => img(id, null, 0, 0, 10, 10));
out.capLen = S.formatGuess(many, manyObjs).length;
""")
    assert out["guessKeys"] == ["cc", "dd", "gone", "me", "w1"]          # 모르는 칸 글자(z)는 버린다
    assert out["main"] == ["c1", "cc", "w1"] and "dd" in out["detail"]
    assert out["unsorted"] == ["xx", "me"]                              # 짐작 없음 · 사람이 미분류로 고름 = 미분류 칸
    assert out["labels"] == ["미분류", "미분류", "정면·도어", "정면·내부", "부품 상세"]   # 첫 짐작이 다른 칸이면 대표 이름표
    assert out["guessed"] == ["cc", "dd", "w1"]
    assert out["titles"] == ["정면 · 입체", "서랍 단면 · 부품 상세", "평면 · 상판", "기타 그림"]   # 제품 이름이 아니다
    assert out["empty"] == ["큰 그림", "정면", "입체", "상세"]
    assert out["kitchen"] == [["cc", "w1"], ["c1"], "정면", "입체"]
    assert out["off"] == "정면·도어"                                   # 미분류 끄기 = AI 첫 짐작 그대로
    assert out["fmt"] == "cc=f68 w1=f76 dd=d55 me=f90"                 # 시트에 없는 그림은 뺀다
    assert 0 < out["capLen"] <= 500                                    # 폼 한 칸 한도

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
MODULES = ["v2-slots.js", "v2-pack.js", "v2-hero.js", "v2-fill.js", "v2-layout.js", "v2-plan.js"]


def _node() -> str:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


RUNNER = r"""
global.window = {};
const fs = require('fs');
const [dir, layoutFile] = process.argv.slice(1, 3);
for (const f of ['part-pack.js', 'part-layout.js', 'v2-slots.js', 'v2-pack.js', 'v2-hero.js', 'v2-fill.js', 'v2-layout.js', 'v2-plan.js']) { require(dir + '/' + f); }
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
    for name in MODULES + ["v2-paper.js", "v2-notes.js", "v2-text.js", "v2-left.js", "v2-right.js", "v2-chrome.js", "v2-shell.js",
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


def test_click_jitter_does_not_pin_but_real_drag_does():
    """Konva 는 3px 부터 끌기로 친다 — 1px 로 재던 때는 그림을 누르다 손이 조금 밀려도 고정이 되어 다시 배치가 건너뛰었다."""
    out = _run(r"""
const mk = (id, dx) => img(id, '정면·내부', 100 + dx, 100, 300, 200, { part: { label: '정면·내부', src: 'ai', arr: [100, 100, 300, 200] } });
const g = S.group([mk('j3', 3), mk('j6', 6), mk('m7', 7), mk('m40', 40)], {});
out.fixed = Object.keys(g.fixed).sort();
out.tol = S.MOVE_TOL;
""")
    assert out["tol"] == 6 and out["fixed"] == ["m40", "m7"]


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
const off = L.compute({ units, photo: [], detail: [], plan: [], unsorted: [], bom: [], notes: [] }, { sameScale: false, hero: false }).band;
const offHero = L.compute({ units, photo: [], detail: [], plan: [], unsorted: [], bom: [], notes: [] }, { sameScale: false }).band;
const h = (r, id) => r.moves.find(m => m.id === id).h;
out.on = [h(on, 'a'), h(on, 'b')];
out.off = [h(off, 'a'), h(off, 'b')];
out.offHero = [h(offHero, 'a'), h(offHero, 'b'), offHero.hero];
""")
    assert out["on"] == [125, 63] or out["on"] == [125, 62]   # 원본의 1.25배까지만 · 같은 배율(높이 비 2:1)
    assert out["off"][0] == out["off"][1]                     # 같은 높이
    # 주 그림 크게(기본)는 따로 켜고 끈다 — 같은 높이로 맞춘 칸에서도 주 그림만 제 상한(원본 1.25배)까지 커진다
    assert out["offHero"][:2] == [125, out["off"][1]] and out["offHero"][2] == ["a"]


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


# ---- 다시 배치 · 장애물 (스테이징 주문 4385, 2026-10-27) ------------------------------------------------
# 고정 그림(손으로 옮김 · 잠금 · 돌림 · 사본)을 배치 입력에서 빼기만 하고 그 자리를 비우지 않아, 다시 놓은 그림이 그 위에 겹쳤다.
ARRANGE = r"""
const ctxOf = settings => ({ items: imgs => imgs.map((o, i) => ({ id: o.id, nw: o.natural_w || o.w, nh: o.natural_h || o.h, tx: 0, order: i,
  label: (o.part && o.part.label) || '미분류' })), baseline: () => ({}), productText: '몰딩 화장대 여닫이', settings: settings || {} });
function arrange(sheet, settings) {   // v2-shell.js arrange 와 같은 길(코어 부수 효과 빼고)
  const plan = P.build(sheet, ctxOf(settings));
  let key = plan.pick || plan.out.best, res = key ? plan.out[key] : null;
  if (!res && key !== plan.out.best) { key = plan.out.best; res = key ? plan.out[key] : null; }
  if (!res) { return { ok: false, plan }; }
  P.apply(sheet, res, { template: key });
  return { ok: true, plan, res, key };
}
function box(o) {   // 돌린 그림을 감싼 상자 — Konva offset 0 이라 (x, y)가 축
  const r = (o.rotation || 0) * Math.PI / 180, c = Math.cos(r), s = Math.sin(r);
  const xs = [0, o.w * c, -o.h * s, o.w * c - o.h * s].map(v => o.x + v), ys = [0, o.w * s, o.h * c, o.w * s + o.h * c].map(v => o.y + v);
  const x0 = Math.min(...xs), y0 = Math.min(...ys);
  return { x: x0, y: y0, w: Math.max(...xs) - x0, h: Math.max(...ys) - y0 };
}
const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
function overlaps(sheet) {
  const b = sheet.objects.filter(o => o.type === 'image').map(o => Object.assign(box(o), { id: o.id })), n = [];
  for (let i = 0; i < b.length; i++) { for (let j = i + 1; j < b.length; j++) { if (hit(b[i], b[j])) { n.push(b[i].id + '/' + b[j].id); } } }
  return n;
}
function upload(id, label, nw, nh, k, part) {   // wizard.js placeImageFromKey: 폭 900 까지 · 가운데에서 24px 씩 어긋나게
  const w = Math.min(900, nw), h = Math.round(w * nh / nw);
  return img(id, label, Math.round((1478 - w) / 2) + 24 * k, Math.round(70 + (730 - h) / 2) + 24 * k, w, h,
    Object.assign({ natural_w: nw, natural_h: nh }, part ? { part } : {}));
}
function sheet4385() {
  const u = (ai, conf) => ({ label: '미분류', src: 'ai', ai, conf });
  return { id: 's1', form: { v2_ai: 'cc=f68 w1=f76', v2_pick: 'column' }, objects: [
    upload('c1', '입체·내부', 1700, 1200, 0), upload('cc', null, 1500, 1100, 1, u('정면·도어', 0.36)),
    upload('w1', null, 1400, 1000, 2, u('입체·내부', 0.36)), upload('d1', '서랍 단면', 500, 400, 3),
    upload('d2', '서랍 단면', 450, 380, 4), upload('d3', '부품 상세', 400, 240, 5), upload('t1', '평면·상판', 1300, 1000, 6),
    upload('xx', null, 600, 1400, 7, u('부품 상세', 0.2))] };
}
const find = (sh, id) => sh.objects.find(o => o.id === id);
const rect = o => [o.x, o.y, o.w, o.h, o.rotation || 0];
"""


def test_pinned_pictures_are_obstacles_when_rearranging():
    out = _run(ARRANGE + r"""
const laid = sheet4385();
out.first = arrange(laid).ok && overlaps(laid).length === 0;
const cases = {
  drag: sh => { const o = find(sh, 'd1'); o.x += 40; o.y += 10; sh.objects = sh.objects.filter(x => x.id !== 'c1'); return 'd1'; },
  resize: sh => { const o = find(sh, 't1'); o.w = Math.round(o.w * 1.6); o.h = Math.round(o.h * 1.6); return 't1'; },
  lock: sh => { find(sh, 'c1').locked = true; sh.objects.push(upload('n1', '정면·내부', 1200, 900, 0)); return 'c1'; },
  rotate: sh => { find(sh, 'w1').rotation = 90; return 'w1'; },
  copy: sh => { const c = JSON.parse(JSON.stringify(find(sh, 'd2'))); c.id = 'cp'; c.x += 10; c.y += 10; sh.objects.push(c); return 'cp'; },
  trim: sh => { const o = find(sh, 'c1'); o.natural_h = 900; o.h = Math.round(o.w * 900 / o.natural_w); sh.objects.push(upload('n2', '서랍 단면', 520, 400, 0)); return 'c1'; }
};
out.cases = {};
Object.keys(cases).forEach(name => {
  const sh = JSON.parse(JSON.stringify(laid)), pin = cases[name](sh), before = rect(find(sh, pin));
  const r = arrange(sh);
  out.cases[name] = { ok: r.ok, kept: JSON.stringify(rect(find(sh, pin))) === JSON.stringify(before), overlaps: overlaps(sh),
    obstacles: (r.plan.input.obstacles || []).length };
});
""")
    assert out["first"]
    for name, case in out["cases"].items():
        assert case["ok"] and case["overlaps"] == [], (name, case)      # 예전: 여섯 경우 모두 고정 그림 위에 겹쳤다
        assert case["kept"] and case["obstacles"] >= 1, (name, case)    # 고정 그림은 그대로 · 장애물로 들어간다


def test_locked_bom_and_stamp_texts_are_obstacles():
    out = _run(ARRANGE + r"""
const sh = { id: 's', form: {}, objects: [
  img('a', '정면·내부', 300, 300, 600, 400, { natural_w: 1200, natural_h: 800 }),
  img('b', '서랍 단면', 300, 300, 300, 240, { natural_w: 500, natural_h: 400 }),
  img('p', '평면·상판', 300, 300, 400, 300, { natural_w: 1300, natural_h: 1000 }),
  Object.assign(txt('b1', '[SR]\n60*2440=2\n60*2440=2\n60*2440=2', 60, 60, 120), { locked: true }),
  Object.assign(txt('st-1', '비규격', 700, 400, 80, 24), { locked: true })] };
const r = arrange(sh);
out.ok = r.ok;
out.hits = [];
sh.objects.filter(o => o.type === 'image').forEach(i => ['b1', 'st-1'].forEach(id => { if (hit(i, S.textBox(find(sh, id)))) { out.hits.push(i.id + '/' + id); } }));
out.textsKept = [find(sh, 'b1').x, find(sh, 'b1').y, find(sh, 'st-1').x, find(sh, 'st-1').y];
""")
    assert out["ok"] and out["hits"] == []
    assert out["textsKept"] == [60, 60, 700, 400]     # 잠긴 글자는 그 자리 그대로


def test_compute_without_obstacles_is_unchanged_and_rec_is_best_score():
    out = _run(INPUT + r"""
const a = L.compute(input, {}), b = L.compute(Object.assign({}, input, { obstacles: [] }), {});
out.same = JSON.stringify(a) === JSON.stringify(b);
out.rec = a.rec;
out.recWant = a.column.score > a.band.score + 0.005 ? 'column' : 'band';
const other = out.recWant === 'band' ? 'column' : 'band', picked = L.compute(input, { prefer: other });
out.picked = [picked.best, picked.rec];
out.other = other;
""")
    assert out["same"]
    assert out["rec"] == out["recWant"]
    assert out["picked"] == [out["other"], out["recWant"]]   # 고른 틀을 붙여도 '추천'은 점수가 높은 틀


def test_seeded_pin_then_delete_or_add_never_overlaps():
    out = _run(ARRANGE + r"""
let seed = 4242;
const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
const ri = (a, b) => Math.floor(a + rnd() * (b - a + 1));
const LABELS = ['정면·내부', '정면·도어', '입체·내부', '입체·도어', '평면·상판', '서랍 단면', '부품 상세', '사진', null];
let uid = 0;
const pic = () => upload('o' + (uid++), LABELS[ri(0, LABELS.length - 1)], ri(250, 2000), ri(200, 1500), 0);
out.runs = 0; out.overlapRuns = 0; out.failed = 0;
for (let n = 0; n < 60; n++) {
  const sh = { id: 's', form: rnd() < 0.3 ? { v2_pick: rnd() < 0.5 ? 'band' : 'column' } : {}, objects: Array.from({ length: ri(3, 9) }, pic) };
  if (!arrange(sh).ok) { continue; }
  const imgs = sh.objects.filter(o => o.type === 'image'), t = imgs[ri(0, imgs.length - 1)], act = ri(0, 4);
  if (act === 0) { t.x += ri(3, 300) * (rnd() < 0.5 ? 1 : -1); t.y += ri(3, 200) * (rnd() < 0.5 ? 1 : -1); }
  if (act === 1) { const k = 0.6 + rnd() * 1.2; t.w = Math.round(t.w * k); t.h = Math.round(t.h * k); }
  if (act === 2) { t.locked = true; }
  if (act === 3) { t.rotation = 90; }
  if (act === 4) { const c = JSON.parse(JSON.stringify(t)); c.id = 'o' + (uid++); c.x += 10; c.y += 10; sh.objects.push(c); }
  if (rnd() < 0.5 && imgs.length > 2) { const d = imgs.find(o => o !== t); sh.objects = sh.objects.filter(o => o !== d); } else { sh.objects.push(pic()); }
  const r = arrange(sh);
  out.runs++;
  if (!r.ok) { out.failed++; continue; }
  if (overlaps(sh).length) { out.overlapRuns++; }
}
""")
    assert out["runs"] >= 50
    assert out["overlapRuns"] == 0 and out["failed"] == 0      # 예전(고친 앞): 겹친 다시 배치가 대부분이었다


def test_pinned_picture_does_not_shrink_the_rest_much():
    """고정 그림 하나가 생겨도 나머지 그림은 고정 없이 놓은 것과 비슷한 크기 — 틀 전체를 빈 사각형 하나 안으로 옮기지 않고,
    종이 칸 그대로에서 큰 그림 칸만 고정 그림을 비켜 간다(v2-pack room). 비율 = 같은 시트를 고정 없이 놓았을 때 대비 한 변."""
    out = _run(ARRANGE + r"""
let seed = 4242;
const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
const ri = (a, b) => Math.floor(a + rnd() * (b - a + 1));
const LABELS = ['정면·내부', '정면·도어', '입체·내부', '입체·도어', '평면·상판', '서랍 단면', '부품 상세', '사진'];
let uid = 0;
const pic = () => upload('o' + (uid++), LABELS[ri(0, LABELS.length - 1)], ri(250, 2000), ri(200, 1500), 0);
const area = sh => { const m = {}; sh.objects.filter(o => o.type === 'image').forEach(o => { m[o.id] = o.w * o.h; }); return m; };
function ratio(free, sh, pin) {
  const A = area(free), B = area(sh), rs = Object.keys(B).filter(id => id !== pin && A[id] > 0).map(id => Math.sqrt(B[id] / A[id]));
  return rs.reduce((s, v) => s + v, 0) / rs.length;
}
const rs = [];
out.overlapRuns = 0;
for (let n = 0; n < 60; n++) {
  const sh = { id: 's', form: {}, objects: Array.from({ length: ri(3, 9) }, pic) };
  if (!arrange(sh).ok) { continue; }
  const imgs = sh.objects.filter(o => o.type === 'image'), t = imgs[ri(0, imgs.length - 1)], free = JSON.parse(JSON.stringify(sh));
  t.x += ri(20, 160) * (rnd() < 0.5 ? 1 : -1); t.y += ri(20, 120) * (rnd() < 0.5 ? 1 : -1);
  const extra = pic(); sh.objects.push(extra); free.objects.push(JSON.parse(JSON.stringify(extra)));
  if (!arrange(free).ok || !arrange(sh).ok) { continue; }
  if (overlaps(sh).length) { out.overlapRuns++; }
  rs.push(ratio(free, sh, t.id));
}
rs.sort((a, b) => a - b);
out.n = rs.length; out.median = rs[Math.floor(rs.length / 2)]; out.p10 = rs[Math.floor(rs.length / 10)];
const laid = sheet4385(); arrange(laid);
const sh = JSON.parse(JSON.stringify(laid)), free = JSON.parse(JSON.stringify(laid));
find(sh, 'c1').locked = true;
[sh, free].forEach(s => s.objects.push(upload('nn', '서랍 단면', 520, 400, 0)));
arrange(free); arrange(sh);
out.lock = ratio(free, sh, 'c1');
""")
    assert out["n"] >= 50 and out["overlapRuns"] == 0
    # 예전(2026-10-27): 중앙값 0.88 · 열에 하나는 0.64배 밑. 2026-10-29 주 그림 크게 틀 견주기 뒤 하위 10% 0.74 → 0.69 — 같은 시트로
    # 견주면 60장 모두 그대로였고(고정 · 고정 없음 크기 1.000), 처음 놓은 자리가 바뀌어 옮긴 그림 자리가 달라진 표본 차이다.
    # 같은 날 띠형 위 띠 빈자리 채우기 뒤 0.67: 같은 시트 60장에서 고정 있는 쪽 빈칸 평균 29.3 → 27.3% · 가장 작은 그림 25.4 → 26.2%
    # (뚜렷이 나아짐 12 · 나빠짐 2) — 틀이 띠형으로 바뀐 몇 장에서 그림 크기 비율만 내려갔다.
    assert out["median"] >= 0.93 and out["p10"] >= 0.66, out
    assert out["lock"] >= 0.9, out                               # 스테이징 4385: 큰 그림 하나를 잠그면 나머지가 0.75배였다


def test_slot_heads_keep_minimum_width_so_neighbours_do_not_collide():
    out = _run(r"""
const units = [{ slot: 'main', members: [{ id: 'm1', nw: 1600, nh: 1100 }] }, { slot: 'main', members: [{ id: 'm2', nw: 1400, nh: 1000 }] }];
const sets = [
  { photo: [{ id: 'ph', nw: 900, nh: 1200 }], detail: [{ id: 'd1', nw: 300, nh: 500 }], plan: [{ id: 't1', nw: 400, nh: 900 }] },
  { photo: [{ id: 'ph', nw: 600, nh: 1400 }], detail: [{ id: 'd1', nw: 500, nh: 400 }, { id: 'd2', nw: 260, nh: 600 }], plan: [] },
  { photo: [], detail: [{ id: 'd1', nw: 200, nh: 700 }], plan: [{ id: 't1', nw: 1300, nh: 1000 }] }];
const H = 132, row = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + 24 && b.y < a.y + 24;
out.min = L.HEAD_MIN_W;
out.collide = [];
sets.forEach((s, si) => {
  ['band', 'column'].forEach(t => {
    const r = L.compute(Object.assign({ units, unsorted: [], bom: [{ id: 'b1', w: 70, h: 125 }], notes: [{ id: 'n-1', w: 110, h: 21 }], stamp: null }, s), { prefer: t })[t];
    if (!r) { return; }
    const heads = r.slots.map(x => ({ key: x.key, x: x.x, y: x.y, w: Math.max(x.w, x.key === 'notes' ? 300 : H) }));   // v2-paper 머리 폭
    for (let i = 0; i < heads.length; i++) { for (let j = i + 1; j < heads.length; j++) { if (row(heads[i], heads[j])) { out.collide.push(si + t + ':' + heads[i].key + '/' + heads[j].key); } } }
  });
});
""")
    assert out["min"] == 132
    assert out["collide"] == []      # 예전: 좁은 칸 머리(132px)가 옆 칸 머리 위로 뻗었다


def test_plan_diff_counts_changed_pictures_only():
    out = _run(ARRANGE + r"""
const sh = sheet4385(), r = arrange(sh);
out.after = P.diff(sh, r.res, r.key);
find(sh, 'd1').x += 30;
out.moved = P.diff(sh, r.res, r.key);
find(sh, 'd1').x -= 30;
out.other = P.diff(sh, r.res, r.key === 'band' ? 'column' : 'band').any;
""")
    assert out["after"] == {"n": 0, "any": False}     # 붙인 그대로면 바뀐 것 없음 — 되돌리기 사본을 남기지 않는다
    assert out["moved"] == {"n": 1, "any": True}
    assert out["other"] is True                       # 놓인 틀 이름이 바뀌어도 바뀐 것

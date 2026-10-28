"""도면 마법사 V2 — 빈자리 채우기(v2-fill.js · v2-layout 점수 빈자리 벌점, node 로 돌린다).

사용자 보고(2026-10-28, 스테이징 주문 4385 '사진·상세를 왼쪽에' + 고르게): '여전히 공간을 비 효율적으로 써 — 예시 처럼 공간을 꽉 채워
사용 하도록 해(비율이 아주 이상하지만 않게)' · '강조 문구를 넣으면 아래 전체 공백이 생겨'. 큰 그림 칸(정면 둘 · 입체)이 높이에 막혀
폭 826 중 636만 쓰고 강조 문구 밑 오른쪽 190px 기둥이 통째로 비었고, 평면은 왼쪽 기둥에 끼어 상세가 62%로 작아졌다.
- 평면 · 상세를 큰 그림 칸이 남긴 빈 사각형으로 옮긴 틀도 재고, 점수에 가장 큰 빈 사각형 벌점 · 사진 최소 높이 벌점을 더한다.
- 옮긴 칸은 큰 그림보다 큰 배율로 놓지 않는다 · 겹침 없음 · 종이 칸 안.
"""
from __future__ import annotations

from tests.domains.test_drawing_wizard_v2_layout import ARRANGE, _run

# 스테이징 주문 4385 배치 입력(2026-10-28 읽기 전용으로 뜬 값 — 크기 · 지금 양식 기준만, id 는 바꿈)
INPUT_4385 = r"""
const IN = {"photo":[{"id":"ph","nw":1920,"nh":1441,"tx":0}],"detail":[{"id":"d1","nw":490,"nh":403,"tx":0},{"id":"d2","nw":512,"nh":371,"tx":0},
 {"id":"d3","nw":436,"nh":237,"tx":0}],"plan":[{"id":"p1","nw":629,"nh":799,"tx":0},{"id":"p2","nw":1335,"nh":1065,"tx":0}],"unsorted":[],
 "units":[{"slot":"main","members":[{"id":"m1","nw":1067,"nh":1049,"tx":0}]},{"slot":"main","members":[{"id":"m2","nw":1049,"nh":1049,"tx":0}]},
 {"slot":"main","members":[{"id":"m3","nw":1696,"nh":1223,"tx":0}]}],"bom":[{"id":"b1","w":97,"h":50},{"id":"b2","w":34,"h":50},
 {"id":"b3","w":70,"h":50},{"id":"b4","w":52,"h":50},{"id":"b5","w":72,"h":50}],"notes":[{"id":"n-1","w":51,"h":21}],"stamp":{"id":"st-1","w":72,"h":30},
 "base":{"m1":{"w":451,"h":443},"m2":{"w":443,"h":443},"m3":{"w":308,"h":222},"p1":{"w":218,"h":277},"p2":{"w":278,"h":222},"d1":{"w":162,"h":133},
 "d2":{"w":184,"h":133},"d3":{"w":184,"h":100},"ph":{"w":160,"h":120}}};
const copy = () => JSON.parse(JSON.stringify(IN));
const A = L.AREA, F = window.FomsV2Fill;
const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
function clashes(r) {
  const n = [];
  r.moves.forEach((a, i) => r.moves.slice(i + 1).forEach(b => { if (hit(a, b)) { n.push(a.id + '/' + b.id); } }));
  return n;
}
const inside = r => r.moves.every(m => m.x >= A.x0 && m.y >= A.y0 && m.x + m.w <= A.x1 + 1 && m.y + m.h <= A.y1 + 1);
function without(fn) { window.FomsV2Fill = undefined; try { return fn(); } finally { window.FomsV2Fill = F; } }   // 대조군: 빈자리 채우기 전
"""


def test_4385_column_moves_plan_into_the_empty_strip_and_everything_grows():
    out = _run(INPUT_4385 + r"""
const o = { prefer: 'column', hero: false };
const now = L.compute(copy(), o).column, old = without(() => L.compute(copy(), o).column);
out.old = { fill: old.fillKeys || null, blank: F.blank(old, A, []), min: old.minPct };
out.now = { fill: now.fillKeys, blank: now.blank, min: now.minPct, main: now.mainPct, clashes: clashes(now), inside: inside(now) };
const sc = id => { const m = now.moves.find(x => x.id === id), it = [].concat(IN.plan, IN.detail).concat(...IN.units.map(u => u.members)).find(x => x.id === id); return m.h / it.nh; };
out.cap = ['p1', 'p2'].every(id => sc(id) <= sc('m1') * 1.01);   // 옮긴 평면은 큰 그림보다 큰 배율로 놓지 않는다(픽셀 반올림만큼)
out.photoH = now.moves.find(m => m.id === 'ph').h;
const plan = now.slots.find(s => s.key === 'plan'), main = now.slots.find(s => s.key === 'main');
out.planRight = plan.x >= main.x + 300;                            // 평면 칸은 큰 그림 칸 오른쪽 빈자리(왼쪽 기둥이 아니다)
""")
    assert out["old"]["fill"] is None and out["old"]["blank"] >= 0.12, out    # 예전: 강조 문구 밑 오른쪽 기둥이 통째로 비었다
    assert out["now"]["fill"] == ["plan"] and out["now"]["blank"] < 0.07, out
    assert out["now"]["min"] >= out["old"]["min"] + 0.05, out                # 가장 작은 그림 62% → 69%
    assert out["now"]["clashes"] == [] and out["now"]["inside"] and out["cap"] and out["planRight"], out
    assert out["photoH"] >= 200, out                                           # 사진은 읽을 만큼(사진 최소 높이 벌점)


def test_stamp_does_not_leave_a_blank_column_under_it():
    """'강조 문구를 넣으면 아래 전체 공백이 생겨' — 강조 문구가 있든 없든 가장 큰 빈 사각형이 종이 칸의 7% 밑."""
    out = _run(INPUT_4385 + r"""
out.cases = [true, false].map(stamp => {
  const inp = copy(); if (!stamp) { inp.stamp = null; }
  const r = L.compute(inp, { prefer: 'column', hero: false }).column;
  return { stamp, blank: r.blank, clashes: clashes(r).length };
});
""")
    for c in out["cases"]:
        assert c["blank"] < 0.07 and c["clashes"] == 0, c


def test_random_sheets_fill_without_overlap_and_never_bigger_than_the_main_pictures():
    """무작위 시트 60장(고르게 · 두 틀): 빈자리로 옮긴 칸이 있어도 그림 · 글자끼리 겹치지 않고 종이 칸 안, 옮긴 칸은 큰 그림 배율 이하."""
    out = _run(INPUT_4385 + r"""
let seed = 2810;
const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
const ri = (a, b) => Math.floor(a + rnd() * (b - a + 1));
const items = (p, n) => Array.from({ length: n }, (_, i) => ({ id: p + i, nw: ri(300, 1900), nh: ri(240, 1400), tx: 0 }));
out.used = 0; out.bad = [];
for (let n = 0; n < 60; n++) {
  const inp = { photo: rnd() < 0.7 ? items('ph', 1) : [], detail: items('d', ri(0, 3)), plan: items('p', ri(0, 2)), unsorted: items('u', ri(0, 1)),
    units: items('m', ri(1, 3)).map(m => ({ slot: 'main', members: [m] })), bom: rnd() < 0.6 ? [{ id: 'b1', w: 90, h: 50 }, { id: 'b2', w: 60, h: 50 }] : [],
    notes: rnd() < 0.5 ? [{ id: 'n-1', w: 120, h: 21 }] : [], stamp: rnd() < 0.4 ? { id: 'st-1', w: 72, h: 30 } : null, base: {} };
  const out2 = L.compute(inp, { hero: false });
  ['band', 'column'].forEach(k => {
    const r = out2[k];
    if (!r) { return; }
    const nat = {}; [].concat(inp.photo, inp.detail, inp.plan, inp.unsorted).concat(...inp.units.map(u => u.members)).forEach(x => { nat[x.id] = x; });
    const t = id => { const m = r.moves.find(x => x.id === id); return m.h / nat[id].nh; };
    const main = Math.min(...inp.units.map(u => t(u.members[0].id)));
    const moved = (r.fillKeys || []).flatMap(key => inp[key].map(x => x.id));
    if (moved.length) { out.used++; }
    if (clashes(r).length || !inside(r) || moved.some(id => t(id) > main * 1.01)) { out.bad.push([n, k, clashes(r), inside(r)]); }
  });
}
""")
    assert out["bad"] == [], out["bad"][:5]
    assert out["used"] >= 10, out        # 빈자리 채우기가 실제로 쓰인다(무작위 시트의 상당수)


def test_blank_counts_obstacles_and_photo_floor_penalty():
    out = _run(INPUT_4385 + r"""
const res = { moves: [{ id: 'a', x: 53, y: 53, w: 687, h: 795 }], slots: [] }, area = { x0: 53, y0: 53, x1: 1427, y1: 848 };
out.open = F.blank(res, area, []);
out.covered = F.blank(res, area, [{ x: 760, y: 53, w: 667, h: 795 }]);   // 고정 그림이 남은 반을 차지 — 빈자리가 아니다
const inp = { byId: { ph: { slot: 'photo' } }, full: area, obstacles: [] };
out.small = F.penalty({ moves: [{ id: 'ph', x: 53, y: 53, w: 160, h: 120 }], slots: [] }, inp);
out.big = F.penalty({ moves: [{ id: 'ph', x: 53, y: 53, w: 320, h: 240 }], slots: [] }, inp);
out.consts = [F.BLANK_W, F.PHOTO_H];
""")
    assert 0.45 < out["open"] < 0.52 and out["covered"] < 0.02, out
    assert out["small"] - out["big"] > 0.15, out        # 사진 120px 은 200px 보다 0.2 더 깎인다(같은 빈자리면)
    assert out["consts"] == [1, 200]


def test_plan_reuses_layout_result_for_the_same_input():
    """화면은 고르기 · 확대마다 다시 그린다 — 배치 입력이 같으면 틀 계산(0.1초 넘게)을 다시 하지 않는다."""
    out = _run(ARRANGE + r"""
let calls = 0;
const real = L.compute;
L.compute = function (i, o) { calls++; return real(i, o); };
const sh = sheet4385();
const a = P.build(sh, ctxOf()), b = P.build(sh, ctxOf());
out.same = a.out === b.out;
out.calls = calls;
sh.objects.find(o => o.id === 'd1').natural_w = 640;   // 입력(원본 크기)이 바뀌면 다시 잰다
P.build(sh, ctxOf());
out.after = calls;
L.compute = real;
""")
    assert out == {"same": True, "calls": 1, "after": 2}, out


def test_band_fills_the_empty_space_under_materials_and_notes_in_the_top_band():
    """사용자 질문 창 답(2026-10-29 '띠형 빈칸도 고치고 올려'): 띠형을 고르면 위 띠의 자재표 · 특이 사항 칸이 사진 · 평면보다 낮아
    그 밑이 통째로 비었다(스테이징 4385 띠형 빈칸 17%). 띠형은 옮긴 칸(상세 · 평면)을 종이 칸 전체 빈자리에서 찾는다 — 위 띠
    자재 · 특이 밑으로 들어가고 글자(자재 · 특이 · 강조)와 겹치지 않는다."""
    out = _run(INPUT_4385 + r"""
const o = { prefer: 'band', hero: false };
const now = L.compute(copy(), o).band, none = without(() => L.compute(copy(), o).band);
const isText = m => /^(b\d|n-|st-)/.test(m.id), pics = now.moves.filter(m => !isText(m)), texts = now.moves.filter(isText);
out.now = { fill: now.fillKeys || null, blank: F.blank(now, A, []), photo: (now.moves.find(m => m.id === 'ph') || {}).h, inside: inside(now),
  top: ['d1', 'd2', 'd3', 'p1', 'p2'].filter(id => { const m = now.moves.find(x => x.id === id); return m && m.y + m.h <= now.big.y; }),
  textClash: texts.reduce((n, t) => n + pics.filter(p => hit(t, p)).length, 0), clashes: clashes(now) };
out.none = { blank: F.blank(none, A, []), photo: (none.moves.find(m => m.id === 'ph') || {}).h };
""")
    n, z = out["now"], out["none"]
    assert n["fill"] and set(n["top"]) >= {"d1", "d2", "d3"}, n          # 상세가 위 띠(큰 그림 칸 위)로
    assert n["blank"] < 0.06 and n["blank"] < z["blank"] - 0.05, (n, z)  # 빈칸이 크게 준다
    assert n["photo"] >= 300, n                                          # 위 띠가 넉넉해져 사진도 커진다
    assert n["textClash"] == 0 and n["clashes"] == [] and n["inside"], n

"""도면 마법사 V2 — 주 그림 크게(bento · v2-hero.js, node 로 돌린다).

설계서: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §4
사용자 요청(2026-10-28, 스테이징 주문 4385): 메인 컴퍼넌트를 크게(bento grid) — 같은 배율 한 줄은 폭에 막혀 주 그림이 501×362,
칸 아래 150px 이 비었다. 큰 그림 칸에서 원본 넓이가 두드러지게 큰 그림을 크게, 나머지는 남은 자리에 같은 배율로(겹침 없음).
나머지는 치수 글자 8px · 지금 양식 대비 60% 밑으로 줄이지 않는다. 틀 고르기 · 위 띠는 그대로.
"""
from __future__ import annotations

from tests.domains.test_drawing_wizard_v2_layout import ARRANGE, INPUT, _run


HERO = r"""
// 스테이징 주문 4385 꼴(2026-10-28 사용자 보고): 큰 그림 칸에 주 그림(입체 1696×1223)과 칸 짐작 둘(약 1060×1050),
// 위 띠에 사진 · 상세 셋 · 평면, 기타 1. 같은 배율 한 줄은 폭에 막혀 주 그림이 501×362 · 칸 아래 150px 이 비었다.
function heroSheet() {
  const u = (ai) => ({ label: '미분류', src: 'ai', ai, conf: 0.36 });
  return { id: 's1', form: { v2_ai: 'g1=f71 g2=i81' }, objects: [
    upload('ph', '사진', 1920, 1441, 0), upload('d1', '서랍 단면', 490, 403, 1), upload('d2', '서랍 단면', 512, 371, 2),
    upload('d3', '부품 상세', 436, 237, 3), upload('p1', '평면·상판', 1335, 1065, 4), upload('g1', null, 1067, 1049, 5, u('정면·도어')),
    upload('hero', '입체·내부', 1696, 1223, 6), upload('g2', null, 1049, 1049, 7, u('입체·내부')),
    upload('u1', null, 629, 799, 8, u('평면·상판'))] };
}
const rectOf = o => [o.x, o.y, o.w, o.h].join(',');
"""


def test_main_picture_grows_bento_style_and_the_rest_fits_beside_it():
    """사용자 보고(2026-10-28): 메인 컴퍼넌트를 크게(bento grid) — 큰 그림 칸에서 원본 넓이가 두드러지게 큰 그림을 크게,
    나머지는 남은 자리에 같은 배율로. 위 띠 · 틀 고르기는 그대로, 겹침 없음."""
    out = _run(ARRANGE + HERO + r"""
const on = heroSheet(), off = heroSheet(), a = arrange(on), b = arrange(off, { hero: false });
const sc = (sh, id) => find(sh, id).h / find(sh, id).natural_h;
out.hero = a.res.hero || null;
out.offHero = b.res.hero || null;
out.grow = find(on, 'hero').h / find(off, 'hero').h;
out.overlaps = [overlaps(on), overlaps(off)];
out.restSame = Math.abs(sc(on, 'g1') - sc(on, 'g2')) < 0.01;
out.ratio = sc(on, 'g1') / sc(on, 'hero');
out.inside = on.objects.every(o => o.x >= 52 && o.y >= 52 && o.x + o.w <= 1428 && o.y + o.h <= 849);
out.mainPct = Math.abs(a.res.mainPct - sc(on, 'hero')) < 0.01;
const slot = a.res.slots.find(s => s.key === 'main');
out.slot = ['g1', 'hero', 'g2'].every(id => { const o = find(on, id);
  return o.x >= slot.x && o.x + o.w <= slot.x + slot.w + 1 && o.y >= slot.y + 24 && o.y + o.h <= slot.y + slot.h + 1; });
out.band = ['ph', 'd1', 'd2', 'd3', 'p1', 'u1'].every(id => rectOf(find(on, id)) === rectOf(find(off, id)));
out.key = [a.key, b.key];
""")
    assert out["hero"] == ["hero"] and out["offHero"] is None
    assert out["grow"] >= 1.3, out                 # 4385: 501×362 → 715×515(1.42배)
    assert out["overlaps"] == [[], []]
    assert out["restSame"] and out["ratio"] >= 0.5, out   # 나머지는 같은 배율 · 주 그림의 절반 이상
    assert out["inside"] and out["mainPct"] and out["slot"]
    assert out["band"] and out["key"][0] == out["key"][1]  # 큰 그림 칸만 바뀐다


def test_main_picture_stays_same_scale_when_sizes_are_close_or_floors_hold_the_rest():
    out = _run(INPUT + r"""
out.close = L.compute(input, {}).band.hero || null;                  // 원본 넓이 차이 1.21배 — 하나만 키우지 않는다
const units = [{ slot: 'main', members: [{ id: 'a', nw: 1067, nh: 1049, tx: 0 }] }, { slot: 'main', members: [{ id: 'h', nw: 1696, nh: 1223, tx: 0 }] },
  { slot: 'main', members: [{ id: 'b', nw: 1049, nh: 1049, tx: 0 }] }];
const plain = { units, photo: [], detail: [], plan: [], unsorted: [], bom: [], notes: [] };
const free = L.compute(plain, {}).band, keep = L.compute(plain, { hero: false }).band;
const h = (r, id) => r.moves.find(m => m.id === id).h;
out.free = [free.hero, h(free, 'h') / h(keep, 'h'), h(free, 'a') / h(keep, 'a')];
// 지금 양식 대비 60% 밑으로 줄이지 않는다(기준 높이 550 → 330 까지)
const based = L.compute(Object.assign({}, plain, { base: { a: { w: 560, h: 550 }, b: { w: 550, h: 550 }, h: { w: 700, h: 500 } } }), {}).band;
out.based = [based.hero || null, h(based, 'a'), h(based, 'b')];
// 치수 글자가 이미 8px 밑이면 지금보다 더 줄이지 않는다
const tiny = L.compute(Object.assign({}, plain, { units: units.map(u => ({ slot: 'main', members: u.members.map(m => Object.assign({}, m, { tx: 20 })) })) }), {}).band;
const tinyKeep = L.compute(Object.assign({}, plain, { units: units.map(u => ({ slot: 'main', members: u.members.map(m => Object.assign({}, m, { tx: 20 })) })) }), { hero: false }).band;
out.tiny = [h(tiny, 'a') >= h(tinyKeep, 'a') || 20 * h(tiny, 'a') / 1049 >= 8, h(tiny, 'b') >= h(tinyKeep, 'b') || 20 * h(tiny, 'b') / 1049 >= 8];
""")
    assert out["close"] is None
    assert out["free"][0] == ["h"] and out["free"][1] >= 1.15 and out["free"][2] < 1
    assert out["based"][0] == ["h"] and min(out["based"][1:]) >= 330, out
    assert out["tiny"] == [True, True]


def test_kitchen_iso_picture_alone_in_its_slot_sits_beside_the_front_slot():
    """주방은 큰 그림이 A 정면 · C 입체 두 칸 — 입체 한 장이 두드러지게 크면 입체 칸을 왼쪽에 크게, 정면 칸은 오른쪽에(칸 머리는 칸마다)."""
    out = _run(r"""
const units = [{ slot: 'main', members: [{ id: 'f1', nw: 1200, nh: 700 }] }, { slot: 'main', members: [{ id: 'f2', nw: 1100, nh: 700 }] },
  { slot: 'iso', members: [{ id: 'i1', nw: 1800, nh: 1300 }] }];
const inp = { units, photo: [], detail: [], plan: [], unsorted: [], bom: [], notes: [] };
const r = L.compute(inp, {}).band, k = L.compute(inp, { hero: false }).band;
const m = id => r.moves.find(x => x.id === id), s = key => r.slots.find(x => x.key === key);
out.hero = r.hero || null;
out.grow = m('i1').h / k.moves.find(x => x.id === 'i1').h;
out.heads = ['main', 'iso'].map(key => !!s(key));
out.isoHead = m('i1').y >= s('iso').y + 24;
out.frontHead = ['f1', 'f2'].every(id => m(id).y >= s('main').y + 24 && m(id).x >= s('main').x);
const ov = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
out.slotOverlap = ov(s('main'), s('iso'));
""")
    assert out["hero"] == ["i1"] and out["grow"] >= 1.15, out
    assert out["heads"] == [True, True] and out["isoHead"] and out["frontHead"]
    assert out["slotOverlap"] is False


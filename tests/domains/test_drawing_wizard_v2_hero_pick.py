"""도면 마법사 V2 — 주 그림 크게 틀 견주기(v2-hero heroPick, node 로 돌린다).

설계서: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §4
조사(2026-10-29, 사용자 '다른 주문도 배치 살펴보기'): 스테이징 주문 4385 · 4465 를 그림 빼고 더해 66가지로 실화면에서 다시 배치해 봤다
(저장 요청은 모두 막음). 고르게는 괜찮았고, 주 그림 크게에서 두 가지가 나왔다.
- 고른 틀 하나만 키워 큰 그림 칸 모양이 주 그림과 안 맞으면 오른쪽 기둥이 통째로 비었다(빈칸 16~21%).
  → 옮긴 칸 묶음마다 점수 높은 틀 몇 개에서도 키워 보고, 사진 · 가장 작은 그림을 크게 줄이지 않는 나은 모습을 고른다.
- 띠형에서 키우면 위 띠가 낮아 사진이 114px · 치수 글자가 4px 이 됐다. → 키운 모습이 치수 글자 8px 를 못 지키는데 고르게는 지키면 키우지 않는다.
"""
from __future__ import annotations

from tests.domains.test_drawing_wizard_v2_layout import _run

# 배치 입력(2026-10-29 스테이징에서 읽기 전용으로 뜬 값 — 그림 원본 크기 · 치수 글자 높이 tx · 지금 양식 기준 · 글자 칸 크기만, id 는 바꿈)
FIXTURES = r"""
// 4385: 사진 1 · 상세 3 · 평면 2(탑뷰 포함) · 정면 2 · 입체 1(주 그림) · 자재 5열 · 특이 1 · 강조 문구
const IN_4385 = {"photo":[{"id":"ph","nw":1920,"nh":1441,"tx":12}],"detail":[{"id":"d1","nw":490,"nh":403,"tx":35},{"id":"d2","nw":512,"nh":371,"tx":36},
 {"id":"d3","nw":436,"nh":237,"tx":0}],"plan":[{"id":"p1","nw":629,"nh":799,"tx":35},{"id":"p2","nw":1335,"nh":1065,"tx":35}],"unsorted":[],
 "units":[{"slot":"main","members":[{"id":"f1","nw":1067,"nh":1049,"tx":34.7}]},{"slot":"main","members":[{"id":"f2","nw":1049,"nh":1049,"tx":35.4}]},
 {"slot":"main","members":[{"id":"iso","nw":1696,"nh":1223,"tx":33.9}]}],"bom":[{"id":"b1","w":97,"h":50},{"id":"b2","w":34,"h":50},{"id":"b3","w":70,"h":50},
 {"id":"b4","w":52,"h":50},{"id":"b5","w":72,"h":50}],"notes":[{"id":"n-1","w":51,"h":21}],"stamp":{"id":"st-1","w":72,"h":30},
 "base":{"f1":{"w":364,"h":358},"f2":{"w":358,"h":358},"iso":{"w":476,"h":343},"p1":{"w":176,"h":224},"p2":{"w":364,"h":290},"d1":{"w":134,"h":110},
 "d2":{"w":148,"h":107},"d3":{"w":197,"h":107},"ph":{"w":167,"h":125}},"obstacles":[]};
// 4465 + 사진 하나 더: 세로 사진 2 · 상세 3 · 평면 2 · 기타 1 · 정면 1 · 입체 1(주 그림) · 자재 5열(큰 글씨)
const IN_4465 = {"photo":[{"id":"ph1","nw":1576,"nh":2100,"tx":13.1},{"id":"ph2","nw":1576,"nh":2100,"tx":13.1}],"detail":[{"id":"d1","nw":512,"nh":371,"tx":36},
 {"id":"d2","nw":436,"nh":237,"tx":0},{"id":"d3","nw":490,"nh":403,"tx":35}],"plan":[{"id":"p1","nw":1335,"nh":1065,"tx":35},{"id":"p2","nw":629,"nh":799,"tx":35}],
 "unsorted":[{"id":"u1","nw":1067,"nh":1049,"tx":34.7}],"units":[{"slot":"main","members":[{"id":"f1","nw":1049,"nh":1049,"tx":35.4}]},
 {"slot":"main","members":[{"id":"iso","nw":1696,"nh":1223,"tx":33.9}]}],"bom":[{"id":"b1","w":62,"h":80},{"id":"b2","w":60,"h":80},{"id":"b3","w":117,"h":80},
 {"id":"b4","w":127,"h":80},{"id":"b5","w":54,"h":40}],"notes":[],"stamp":null,"base":{"f1":{"w":366,"h":366},"u1":{"w":373,"h":366},"iso":{"w":476,"h":343},
 "p1":{"w":364,"h":290},"p2":{"w":180,"h":229},"d1":{"w":152,"h":110},"d2":{"w":202,"h":110},"d3":{"w":134,"h":110},"ph1":{"w":96,"h":128},"ph2":{"w":96,"h":128}},
 "obstacles":[]};
const copy = x => JSON.parse(JSON.stringify(x));
const A = L.AREA, F = window.FomsV2Fill, H = window.FomsV2Hero, choose = H.choose;
const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
const clashes = r => { const n = []; r.moves.forEach((a, i) => r.moves.slice(i + 1).forEach(b => { if (hit(a, b)) { n.push(a.id + '/' + b.id); } })); return n; };
const inside = r => r.moves.every(m => m.x >= A.x0 && m.y >= A.y0 && m.x + m.w <= A.x1 + 1 && m.y + m.h <= A.y1 + 1);
const photoH = (r, ids) => Math.min(...r.moves.filter(m => ids.includes(m.id)).map(m => m.h));
// 대조군: 견줄 틀을 비우면 고른 틀 하나만 키운다(고치기 전 모습)
function alone(fn) { H.choose = (p, f, inp, o, kit) => choose(p, f, inp, o, Object.assign({}, kit, { cands: {} })); try { return fn(); } finally { H.choose = choose; } }
const nums = r => ({ hero: r.hero || null, blank: F.blank(r, A, []), min: r.minPct, main: r.mainPct, text: r.minText, fill: r.fillKeys || null });
"""


def test_4385_main_picture_no_longer_leaves_the_right_strip_empty():
    """4385 기둥형 · 주 그림 크게: 고른 틀 하나만 키우면 입체 아래 정면 둘 · 오른쪽 250px 기둥이 비었다(빈칸 16%).
    상세를 옮긴 틀에서 키우면 입체가 왼쪽에 크게 · 정면 둘이 오른쪽에 · 상세는 입체 아래 빈자리로 — 빈칸이 반으로, 주 그림은 더 크게."""
    out = _run(FIXTURES + r"""
const o = { prefer: 'column', hero: true };
const before = alone(() => L.compute(copy(IN_4385), o).column), now = L.compute(copy(IN_4385), o).column;
out.before = nums(before);
out.now = Object.assign(nums(now), { clashes: clashes(now), inside: inside(now), photo: photoH(now, ['ph']),
  small: Math.max(...['d1', 'd2', 'd3', 'p1', 'p2'].map(id => now.pct[id])) });
""")
    b, n = out["before"], out["now"]
    assert b["hero"] == ["iso"] and b["blank"] >= 0.15, b                  # 대조군: 오른쪽 기둥이 통째로 비었다
    assert n["hero"] == ["iso"] and n["fill"] == ["detail"], n             # 상세를 옮긴 틀에서 키웠다
    assert n["blank"] < 0.10 and n["main"] > b["main"] * 1.2, (b, n)      # 빈칸 16% → 8% · 주 그림 123% → 157%
    assert n["text"] >= 8 and n["photo"] >= 200, n                         # 치수 글자 8px · 사진 200px 는 지킨다
    assert n["min"] >= b["min"] - 0.1 and n["small"] <= n["main"], n       # 가장 작은 그림은 크게 줄지 않고 상세 · 평면이 주 그림보다 크지 않다
    assert n["clashes"] == [] and n["inside"]


def test_4465_band_does_not_grow_the_main_picture_when_dimension_text_would_go_under_8px():
    """4465 + 사진 2장 · 띠형 · 주 그림 크게: 위 띠가 낮아져 사진이 110px · 치수 글자가 8px 밑이 됐다.
    고르게 모습은 치수 글자를 지키므로 키우지 않는다 — 두 스타일 미리보기도 '같아요'(키운 모습을 보이지 않는다). 막대는 남는다."""
    out = _run(FIXTURES + r"""
const hero = L.compute(copy(IN_4465), { prefer: 'band', hero: true }).band, even = L.compute(copy(IN_4465), { prefer: 'band', hero: false }).band;
out.hero = Object.assign(nums(hero), { photo: photoH(hero, ['ph1', 'ph2']), alt: hero.alt ? hero.alt.style : null, size: !!hero.size });
out.even = { alt: even.alt ? even.alt.style : null, same: JSON.stringify(even.moves) === JSON.stringify(hero.moves) };
""")
    h, e = out["hero"], out["even"]
    assert h["hero"] is None and h["text"] >= 8 and h["photo"] >= 200, h   # 사진 110px · 글자 8px 밑 대신 고르게 모습
    assert h["alt"] is None and e["alt"] is None and e["same"], (h, e)     # 미리보기 = 실제(두 스타일이 같다)
    assert h["size"], h                                                    # 막대로는 여전히 키울 수 있다(사람이 고른 크기)


def test_style_previews_match_what_the_other_style_actually_places_after_picking_a_new_frame():
    """틀을 견줘 바꿔도 미리보기 = 실제: 주 그림 크게의 '고르게' 미리보기는 고르게 결과, 고르게의 '주 그림 크게' 미리보기는 키운 결과."""
    out = _run(FIXTURES + r"""
const a = L.compute(copy(IN_4385), { prefer: 'column', hero: true }).column, b = L.compute(copy(IN_4385), { prefer: 'column', hero: false }).column;
const norm = sl => JSON.stringify(sl.slice().sort((x, y) => (x.key + x.x + ',' + x.y).localeCompare(y.key + y.x + ',' + y.y)));
out.heroAlt = a.alt && a.alt.style === 'even' && norm(a.alt.slots) === norm(b.slots);
out.evenAlt = b.alt && b.alt.style === 'hero' && Math.abs(b.alt.mainPct - a.mainPct) < 1e-9 && norm(b.alt.slots) === norm(a.slots);
out.sizes = [a.size && a.size.pct, b.size && b.size.max === a.size.max];
""")
    assert out["heroAlt"] and out["evenAlt"], out
    assert out["sizes"][0] and out["sizes"][1], out

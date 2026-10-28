"""도면 마법사 V2 — 종이 위 · 전달 도면에 찍히는 글(node, 가짜 코어 · 가짜 DOM).

설계서: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §3
도면팀원 눈 평가(2026-10-27) '전달 도면에 찍히는 글이 어색하다' · '겹친 그림 · 안 읽히는 치수를 종이 위에서 짚어 주지 않는다':
1) 종류 모르는 그림 칸 머리 'D 기타 그림'이 내보낸 PNG 에 찍혔다 → PNG 층(#dws-v2-slots)엔 없고 화면 층(#dws-v2-badges)에 주황 '종류 확인'.
2) 칸 글자를 큰 그림부터 붙여 종이 위 읽는 순서가 B → A → D 로 뒤섞였다 → 칸으로 정리한 시트는 왼쪽 위부터 읽는 순서
   (왼쪽 카드도 같은 글자). 정리 전 시트는 예전 순서 그대로.
3) 자재 칸 배율 자리의 눌리지 않는 '직접 입력' 표시를 뺐다.
4) 'A 정면 · 입체 1500'의 1500 = 아래 띠 현장규격 → '현장규격 1500 · 색상 화이트'.
5) 서로 겹친 그림 · 치수 글자 8px 밑 그림에 주황 테두리 + 딱지(화면에만, 자동 배치 모드 · 칸으로 정리한 시트).
실제 v2-*.js 를 싣는다. 가짜 DOM 은 어떤 id 든 만들어 준다 — 다른 화면 조각이 늘어도 이 시험이 깨지지 않게.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS_DIR = ROOT / "static/js/drawing"
TPL = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")

RUNNER = r"""
const dir = process.argv[1];
let now = 0, tid = 0, timers = [];
global.window = {
  setTimeout: (fn, ms) => { const id = ++tid; timers.push({ id, fn, at: now + (ms || 0) }); return id; },
  clearTimeout: id => { timers = timers.filter(t => t.id !== id); },
  localStorage: { getItem: () => null, setItem: () => {} }
};
function tick(ms) {
  const end = now + ms;
  for (;;) {
    timers.sort((a, b) => a.at - b.at || a.id - b.id);
    const t = timers[0];
    if (!t || t.at > end) { break; }
    timers.shift(); now = t.at; t.fn();
  }
  now = end;
}
function mkEl(tag) {
  const e = { tagName: String(tag || 'div').toUpperCase(), children: [], style: {}, attrs: {}, handlers: {}, hidden: false,
    disabled: false, className: '', title: '', type: '', value: '', _text: '' };
  Object.defineProperty(e, 'textContent', {
    get() { return e._text + e.children.map(c => c.textContent).join(''); },
    set(v) { e._text = String(v == null ? '' : v); e.children = []; } });
  e.appendChild = c => { e.children.push(c); c.parentNode = e; return c; };
  e.insertBefore = (c, ref) => { const i = e.children.indexOf(ref); if (i < 0) { e.children.push(c); } else { e.children.splice(i, 0, c); } c.parentNode = e; return c; };
  e.removeChild = c => { e.children = e.children.filter(x => x !== c); return c; };
  e.remove = () => { if (e.parentNode) { e.parentNode.removeChild(e); } };
  e.addEventListener = (n, fn) => { (e.handlers[n] = e.handlers[n] || []).push(fn); };
  e.removeEventListener = () => {};
  e.setAttribute = (k, v) => { e.attrs[k] = String(v); };
  e.getAttribute = k => (k in e.attrs ? e.attrs[k] : null);
  e.removeAttribute = k => { delete e.attrs[k]; };
  const cls = new Set();
  e.classList = { add: (...c) => c.forEach(x => cls.add(x)), remove: (...c) => c.forEach(x => cls.delete(x)),
    toggle: (c, on) => { if (on === undefined ? !cls.has(c) : on) { cls.add(c); } else { cls.delete(c); } }, contains: c => cls.has(c) };
  e.querySelector = () => null;
  e.querySelectorAll = () => [];
  e.contains = n => { for (let p = n; p; p = p.parentNode) { if (p === e) { return true; } } return false; };
  e.closest = () => null; e.focus = () => {}; e.blur = () => {}; e.scrollIntoView = () => {};
  e.getBoundingClientRect = () => ({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 });
  e.click = () => (e.handlers.click || []).forEach(fn => fn({ stopPropagation() {}, preventDefault() {} }));
  return e;
}
const dom = {};
function byId(id) { if (!dom[id]) { dom[id] = mkEl('div'); dom[id].id = id; } return dom[id]; }
global.document = { readyState: 'complete', activeElement: null, getElementById: byId, querySelectorAll: () => [],
  querySelector: () => null, createElement: mkEl, addEventListener: () => {} };
// ---- 가짜 코어: wizard.js 사건 순서 · 치수 글자 높이(원본 px)는 TX 로 준다 ----
const handlers = {}, undo = [], state = { sheets: [] }, TX = {};
let cur = 0;
function emit(name, data) { (handlers[name] || []).slice().forEach(fn => fn(data)); }
const core = {
  ui: 'v2', on: (n, fn) => { (handlers[n] = handlers[n] || []).push(fn); },
  state: () => state, sheet: () => state.sheets[cur] || null, canSave: () => true,
  recordUndo: () => { undo.push(JSON.stringify(state.sheets[cur])); },
  markDirty: () => emit('change'), redraw: () => emit('render'),
  select: () => {}, toast: () => {}, editing: () => false, dragging: () => false,
  items: imgs => imgs.map((o, i) => ({ id: o.id, nw: o.natural_w || o.w, nh: o.natural_h || o.h, order: i, tx: TX[o.id] || 0,
    label: (o.part && o.part.label) || '미분류' })),
  baseline: () => ({}), productText: () => '몰딩 화장대 여닫이',
  products: () => [], photos: () => [], photoVisible: () => true, importPhoto: () => Promise.resolve(false), threshold: () => 0.5,
  fitCell: () => {}, hatch: () => null, viewUrl: () => '', setTool: () => {}, setPartLabel: () => {}
};
window.FomsWizardCore = core;
for (const f of ['part-pack.js', 'part-layout.js', 'v2-slots.js', 'v2-pack.js', 'v2-hero.js', 'v2-fill.js', 'v2-layout.js', 'v2-plan.js', 'v2-paper.js',
  'v2-left.js', 'v2-shell.js']) { require(dir + '/' + f); }
const V2 = window.FomsV2, S = window.FomsV2Slots;
const img = (id, label, w, h, extra) => Object.assign({ id, type: 'image', key: id + '.png', x: 500, y: 300, w: Math.min(900, w),
  h: Math.round(Math.min(900, w) * h / w), natural_w: w, natural_h: h, rotation: 0, part: { label, src: 'ai', conf: 0.8 } }, extra || {});
function sheet4385(form) {   // 주문 4385 꼴: 큰 그림 3(칸 짐작 2) · 상세 3 · 평면 1 · 종류 모름 1 · 자재표 1열
  return { id: 's1', name: '몰딩 화장대 여닫이', form: Object.assign({ v2_ai: 'g1=f71 g2=i81', site_spec: '1500', color: '화이트' }, form || {}),
    objects: [
      img('g1', '미분류', 1600, 1100, { part: { label: '미분류', src: 'ai', ai: '정면·도어', conf: 0.36 } }),
      img('g2', '미분류', 1700, 1150, { part: { label: '미분류', src: 'ai', ai: '입체·내부', conf: 0.36 } }),
      img('i1', '입체·내부', 1700, 1150), img('d1', '부품 상세', 700, 420), img('d2', '서랍 단면', 600, 500),
      img('d3', '서랍 단면', 650, 480), img('p1', '평면·상판', 1500, 700),
      img('u1', '미분류', 500, 900, { part: { label: '미분류', src: 'ai', ai: '부품 상세', conf: 0.49 } }),
      { id: 'b1', type: 'text', x: 60, y: 60, w: 80, text: '[SR]\n60*2440=2', size: 20 }] };
}
function laid(form) {   // 같이 올린 묶음이 끝남 → 칸 배치(자동 배치 모드)
  state.sheets = [sheet4385(form)]; cur = 0;
  emit('batch', { ids: state.sheets[0].objects.filter(o => o.type === 'image').map(o => o.id), sheetId: 's1' });
  tick(200);
  return core.sheet();
}
const obj = id => core.sheet().objects.find(o => o.id === id);
const find = (n, re) => { if (re.test(n.className || '')) { return n; } for (const c of n.children || []) { const r = find(c, re); if (r) { return r; } } return null; };
function heads(layer) {   // 칸 머리 → { badge, name, meta, x, y, w, check }
  return dom[layer].children.filter(n => /(^|\s)dws-v2-head(\s|$)/.test(n.className)).map(n => {
    const part = re => { const c = n.children.find(x => re.test(x.className)); return c ? c.textContent : ''; };
    return { badge: part(/head-badge/), name: part(/head-name/), meta: part(/head-meta/), x: parseInt(n.style.left, 10),
      y: parseInt(n.style.top, 10), w: parseInt(n.style.width, 10), check: /dws-v2-head-check/.test(n.className) };
  });
}
function cards() {   // 왼쪽 칸 카드 → { 칸: 딱지 글자 }
  const res = {};
  dom['dws-v2-cards'].children.forEach(c => { const b = find(c, /dws-v2-card-badge/); res[c.getAttribute('data-slot')] = b ? b.textContent : ''; });
  return res;
}
const out = {};
"""


def _node() -> str:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


def _run(body: str) -> dict:
    script = RUNNER + body + "\nprocess.stdout.write(JSON.stringify(out));"
    proc = subprocess.run([_node(), "-e", script, str(JS_DIR)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_read_order_cuts_rows_then_columns_and_letters_skip_unsorted_when_laid():
    out = _run(r"""
const B = (key, x, y, w, h) => ({ key, box: { x, y, w, h } });
// 왼쪽 기둥형: 상세(위) · 평면(아래, 7px 더 왼쪽) — 기둥 안에서 위부터, 그다음 오른쪽 큰 그림
out.column = S.readOrder([B('main', 400, 200, 1000, 640), B('plan', 53, 560, 300, 280), B('detail', 60, 53, 290, 480)]);
out.band = S.readOrder([B('main', 53, 300, 1374, 540), B('plan', 600, 53, 300, 200), B('detail', 300, 53, 280, 220)]);
out.row = S.readOrder([B('b', 500, 90, 100, 300), B('a', 100, 0, 100, 100)]);          // 위아래가 겹치면 같은 줄 → 왼쪽부터
out.stack = S.readOrder([B('low', 0, 200, 300, 100), B('high', 400, 0, 100, 150)]);    // 안 겹치면 위부터(왼쪽에 있어도)
out.tangled = S.readOrder([B('q', 50, 50, 200, 200), B('p', 0, 0, 200, 200), B('r', 100, 100, 200, 200)]);   // 못 자르면 위 → 왼쪽
const objs = [img('m', '정면·내부', 1200, 800, { x: 400, y: 300, w: 900, h: 600 }), img('d', '서랍 단면', 600, 400, { x: 60, y: 60, w: 300, h: 200 }),
  img('t', '평면·상판', 900, 300, { x: 60, y: 600, w: 300, h: 100 }),
  img('u', null, 300, 300, { x: 1300, y: 60, w: 100, h: 100, part: { label: '미분류', src: 'ai' } }),
  img('pin', '부품 상세', 400, 300, { x: 1300, y: 900, w: 60, h: 40, locked: true })];   // 잠근 상세 — 칸 상자에서 뺀다
const g = S.group(objs, {});
out.unlaid = S.letters(g, false);
out.unlaidFalse = S.letters(g, false, false);
out.laid = S.letters(g, false, true);
out.box = S.slotBox(g, 'detail');
out.allPinned = S.slotBox(S.group([objs[4]], {}), 'detail');
out.empty = S.slotBox(g, 'iso');
""")
    assert out["column"] == ["detail", "plan", "main"]
    assert out["band"] == ["detail", "plan", "main"]
    assert out["row"] == ["a", "b"] and out["stack"] == ["high", "low"] and out["tangled"] == ["p", "q", "r"]
    # 정리 전 = 예전 순서(큰 그림 A · 상세 B · 평면 C · 기타 D) — 세 번째 인자를 안 주면 그대로
    assert out["unlaid"] == out["unlaidFalse"] == {"main": "A", "detail": "B", "plan": "C", "unsorted": "D"}
    # 칸으로 정리한 시트 = 왼쪽 위부터 읽는 순서 · 종류 모르는 그림은 글자 없음(머리가 화면에만)
    assert out["laid"] == {"detail": "A", "plan": "B", "main": "C"}
    assert out["box"] == {"x": 60, "y": 60, "w": 300, "h": 200}            # 잠근 그림은 칸 상자에서 빠진다
    assert out["allPinned"] == {"x": 1300, "y": 900, "w": 60, "h": 40}     # 다 고정이면 그대로
    assert out["empty"] is None


def test_laid_sheet_paper_heads_and_left_cards_use_reading_order_letters():
    out = _run(r"""
[['column', {}], ['band', {}], ['kitchen', { v2_kind: 'kitchen' }]].forEach(([name, extra]) => {
  const sh = laid(Object.assign({ v2_pick: name === 'column' ? 'column' : 'band' }, extra));
  const hs = heads('dws-v2-slots'), letters = V2.plan().letters, paper = {}, g = V2.plan().g;
  hs.forEach(h => { if (/^[A-G]$/.test(h.badge)) { paper[h.badge] = h; } });
  const left = k => { const loose = g[k].filter(o => !g.fixed[o.id]); return Math.round(Math.min(...(loose.length ? loose : g[k]).map(o => o.x))); };
  const byKey = {};
  Object.keys(letters).forEach(k => { byKey[k] = !!paper[letters[k]] && paper[letters[k]].x === left(k); });
  out[name] = { layout: sh.form.v2_layout, letters, headAtSlot: byKey, cards: cards(), slotsText: dom['dws-v2-slots'].textContent,
    check: heads('dws-v2-badges'), paperLetters: Object.keys(paper).sort(),
    pills: dom['dws-v2-badges'].children.filter(n => /dws-v2-pill /.test(n.className)).map(n => n.textContent),
    mainMeta: (hs.find(h => h.badge === letters.main) || {}).meta };
});
""")
    for name in ("column", "band", "kitchen"):
        case = out[name]
        assert case["layout"] == ("column" if name == "column" else "band"), (name, case["layout"])
        # 2026-10-28 빈자리 채우기(v2-fill): 평면(왼쪽 기둥형) · 상세와 평면(위 띠형)이 큰 그림 칸 빈자리로 가 읽는 순서가 바뀐다.
        # 주방: 정면 줄 옆 빈자리에 평면, 그 아래 입체 줄. 10-29 띠형은 위 띠 자재 · 특이 밑 빈자리도 찾아 상세가 입체보다 위(C)로.
        want = {"column": {"detail": "A", "main": "B", "plan": "C"}, "band": {"main": "A", "plan": "B", "detail": "C"},
                "kitchen": {"main": "A", "plan": "B", "detail": "C", "iso": "D"}}[name]
        # 예전: 큰 그림 A · 상세 B · 평면 C · 기타 D — 틀에 따라 종이 위 순서가 B → A → D, 그 밑 C 로 뒤섞였다
        assert case["letters"] == want, (name, case["letters"])
        assert all(case["headAtSlot"].values()), (name, case["headAtSlot"])     # 글자 딱지 = 그 칸 머리
        assert case["paperLetters"] == sorted(want.values()), name
        assert {k: case["cards"][k] for k in want} == want, (name, case["cards"])  # 왼쪽 카드도 같은 글자
        # 종류 모르는 그림 칸 머리는 PNG 층에 없고, 화면 층에만 주황 '? 종류 확인 1장'
        assert "기타 그림" not in case["slotsText"] and "종류 확인" not in case["slotsText"], name
        assert [(h["badge"], h["name"], h["meta"], h["check"]) for h in case["check"]] == [("?", "종류 확인", "1장", True)], name
        assert "직접 입력" not in case["pills"], name                              # 자재 칸엔 배율 표시가 없다
    assert out["column"]["mainMeta"] == "현장규격 1500 · 색상 화이트"            # 예전 '1500 · 화이트' — 무슨 숫자인지 몰랐다
    assert out["kitchen"]["mainMeta"] == ""                                       # 주방은 곁글 없음(예전 그대로)


def test_unlaid_sheet_keeps_old_letters_and_draws_no_heads_or_marks():
    out = _run(r"""
V2.setMode('free', true);                        // 자유 배치 모드 — 칸으로 정리하지 않는다
state.sheets = [sheet4385({})]; cur = 0;
TX.p1 = 10;
V2.refresh(); tick(200);
out.layout = core.sheet().form.v2_layout || '';
out.letters = V2.plan().letters;
out.cards = cards();
out.slots = dom['dws-v2-slots'].children.length;
out.badges = dom['dws-v2-badges'].children.length;
""")
    assert out["layout"] == ""
    assert out["letters"] == {"main": "A", "detail": "B", "plan": "C", "unsorted": "D"}   # 지금 순서 그대로
    assert {k: out["cards"][k] for k in ("main", "detail", "plan")} == {"main": "A", "detail": "B", "plan": "C"}
    assert out["slots"] == 0 and out["badges"] == 0      # 정리 전에는 머리 · 표시를 그리지 않는다


def test_overlapping_and_small_text_pictures_get_orange_marks_only_on_screen_in_auto_mode():
    out = _run(r"""
TX.p1 = 10; TX.i1 = 400; TX.u1 = 1;              // 평면은 치수 글자가 작고 · 큰 그림은 크고 · 종류 모르는 그림은 따지지 않는다
const sh = laid({ v2_pick: 'band' });
const d2 = obj('d2'), d3 = obj('d3');
core.recordUndo(); d2.x = d3.x; d2.y = d3.y; core.markDirty(); tick(200);   // 상세 한 장을 옆 그림 위로 끌어 놓음(= 고정)
const kids = dom['dws-v2-badges'].children;
out.problems = window.FomsV2Paper.problems ? window.FomsV2Paper.problems(sh, V2.plan()) : {};
const imgs = sh.objects.filter(o => o.type === 'image'), over = new Set();
const ov = (a, b) => Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) > 2 && Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) > 2;
imgs.forEach(a => imgs.forEach(b => { if (a !== b && ov(a, b)) { over.add(a.id); } }));
out.overlapIds = Array.from(over).sort();
out.warns = kids.filter(n => n.className === 'dws-v2-warn').length;
out.tags = kids.filter(n => n.className === 'dws-v2-warn-tag').map(n => [n.textContent, parseInt(n.style.left, 10), parseInt(n.style.top, 10)]);
out.d2 = [d2.x, d2.y];
out.p1px = Math.floor(10 * obj('p1').h / 700);
out.fixed = Object.keys(V2.plan().g.fixed);
out.slotsText = dom['dws-v2-slots'].textContent;
V2.setMode('free', true); tick(200);             // 자유 배치 모드에선 표시하지 않는다
out.freeMarks = dom['dws-v2-badges'].children.filter(n => /dws-v2-(warn|pin)/.test(n.className)).length;
out.freeCheck = heads('dws-v2-badges').length;   // 종류 확인 머리는 그대로(칸으로 정리한 시트)
""")
    flagged = sorted(k for k, v in out["problems"].items() if "그림 겹침" in v)
    assert "d2" in flagged and "d3" in flagged and flagged == out["overlapIds"]
    assert out["problems"]["p1"] == ["글자 작음 %dpx" % max(1, out["p1px"])] and out["p1px"] < 8
    assert "글자 작음" not in " ".join(out["problems"].get("i1", [])) and "u1" not in out["problems"]
    assert out["warns"] == len(out["problems"]) == len(out["tags"])
    d2_tag = [t for t in out["tags"] if t[0] == " · ".join(out["problems"]["d2"])]
    assert out["fixed"] == ["d2"] and [out["d2"][0] + 4, out["d2"][1] + 4 + 24] in [t[1:] for t in d2_tag]   # '고정' 표시 아래 줄
    for word in ("그림 겹침", "글자 작음", "고정"):
        assert word not in out["slotsText"], word        # PNG 층에는 찍히지 않는다
    assert out["freeMarks"] == 0 and out["freeCheck"] == 1


def test_screen_layer_hides_on_export_and_assets_are_pinned():
    form = (ROOT / "templates/drawing/partials/wizard_v2_form.html").read_text(encoding="utf-8")
    assert '<div class="dws-v2-badges dws-ui" id="dws-v2-badges"' in TPL          # 화면 층 = .dws-ui
    assert '<div class="dws-v2-slots" id="dws-v2-slots"' in form                   # PNG 층 = .dws-ui 아님
    wizard_css = (ROOT / "static/css/contexts/drawing/wizard.css").read_text(encoding="utf-8")
    assert ".dws-exporting .dws-ui { display: none !important; }" in wizard_css
    css = (ROOT / "static/css/contexts/drawing/wizard-v2.css").read_text(encoding="utf-8")
    for rule in (".dws-v2-head-check {", ".dws-v2-warn {", ".dws-v2-warn-tag {"):
        assert rule in css, rule
    paper = (JS_DIR / "v2-paper.js").read_text(encoding="utf-8")
    assert "text: '직접 입력'" not in paper and "name: '기타 그림'" not in paper
    assert "into = key === 'unsorted' ? badges : layer" in paper
    assert "js/drawing/v2-paper.js') }}?v=20261028a" in TPL
    assert "js/drawing/v2-slots.js') }}?v=20261028c" in TPL   # 10-28 겹친 고정 그림 풀기 · 글자 고정(v2_pin)
    assert "css/contexts/drawing/wizard-v2.css') }}?v=20261028b" in TPL   # 10-28 알림 띠 탭 줄 · 내 문구 단추


def test_band_page_number_shows_sheet_position_instead_of_dash():
    """아래 띠 '장 - / 1' → '1 / 1'(운영 점검 2026-10-27). 도면 번호가 '-'(제품 1개 주문 규칙)나 빈칸이면 몇 번째 시트인지
    보인다 — 화면 · PNG 글만이고 저장 값 · V1 · 파일 이름 규칙은 그대로. 번호가 매겨진 시트가 있으면(여러 제품) 손대지 않는다."""
    src = (JS_DIR / "wizard.js").read_text(encoding="utf-8")
    assert "if (k === 'page_no' && UI === 'v2') { el.textContent = v2PageText(el.textContent); }" in src
    fn = re.search(r"  function v2PageText\(text\) \{\n.*?\n  \}\n", src, re.S)
    assert fn
    script = "let state, current;\n" + fn.group(0) + r"""
const cases = [[['-'], 0, '-'], [['-', '-'], 1, '-'], [[''], 0, ''], [['1', '2', '-'], 2, '-'], [['-'], 0, '3'], [['-'], 0, 'A']];
process.stdout.write(JSON.stringify(cases.map(([nos, at, text]) => {
  state = { sheets: nos.map(p => ({ form: { page_no: p } })) }; current = at; return v2PageText(text);
})));
"""
    proc = subprocess.run([_node(), "-e", script], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == ["1", "2", "1", "-", "3", "A"]
    assert "else \"-\"" in (ROOT / "foms/services/drawing_wizard_defaults.py").read_text(encoding="utf-8")   # 저장 규칙은 그대로

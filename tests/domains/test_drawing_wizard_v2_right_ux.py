"""도면 마법사 V2 — 오른쪽 칸 · 앱바 · 알림 띠 · 도구 사용성(도면팀원 눈 평가 2026-10-27 후속).

설계서: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §1 · §4 · §6
1) 틀 이름을 쉬운 말로('사진·상세를 위에' · '사진·상세를 왼쪽에' · '지금 쓰는 틀' · '틀 고르기'), '추천'은 늘 붙고
   고른 틀이 추천과 다르면 [추천 틀로 돌아가기] — 고른 틀만 풀고 다시 놓는다(고정 그림은 그대로).
2) '컴퓨터가 본 것' · 켜고 끄기는 '자세히 ▸'로 접는다(처음엔 접힘 · 이 브라우저에 기억 · 저장소가 막혀도 돈다).
3) 자동 배치 모드에도 도구가 보이고, 그림 밖 메모 · 선 · 도형은 다시 배치의 장애물이다(그림 안 치수 메모는 그림을 따라간다).
4) 알림 띠는 종이를 내려도 위에 붙어 있다(sticky).
5) 알림 글은 '오른쪽 [고정 풀고 모두 다시]'를 가리키지 않는다 — ⋯ 메뉴에도 같은 항목(1280 밑 창은 오른쪽 칸이 숨는다).
6) V2 앱바에 늘 보이는 [예전 화면](data-dws-ui-switch="v1").
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]
JS_DIR = ROOT / "static/js/drawing"
TPL = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
RIGHT = (ROOT / "templates/drawing/partials/wizard_v2_right.html").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/contexts/drawing/wizard-v2.css").read_text(encoding="utf-8")

# ---- 순수 계산(배치 계획) ----------------------------------------------------------------------------
PLAN = r"""
global.window = {};
const dir = process.argv[1];
for (const f of ['part-pack.js', 'part-layout.js', 'v2-slots.js', 'v2-pack.js', 'v2-hero.js', 'v2-layout.js', 'v2-plan.js']) { require(dir + '/' + f); }
const S = window.FomsV2Slots, P = window.FomsV2Plan;
const out = {};
const ctx = { items: imgs => imgs.map((o, i) => ({ id: o.id, nw: o.natural_w || o.w, nh: o.natural_h || o.h, tx: 0, order: i,
  label: (o.part && o.part.label) || '미분류' })), baseline: () => ({}), productText: '몰딩 화장대 여닫이', settings: {} };
function arrange(sheet) {   // v2-shell.js arrange 와 같은 길(코어 부수 효과 빼고)
  const plan = P.build(sheet, ctx), key = plan.pick || plan.out.best, res = key ? plan.out[key] : null;
  if (res) { P.apply(sheet, res, { template: key }); }
  return { ok: !!res, plan, key };
}
const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
function upload(id, label, nw, nh, k, part) {   // wizard.js placeImageFromKey: 폭 900 까지 · 가운데에서 24px 씩 어긋나게
  const w = Math.min(900, nw), h = Math.round(w * nh / nw);
  return { id, type: 'image', key: id + '.png', x: Math.round((1478 - w) / 2) + 24 * k, y: Math.round(70 + (730 - h) / 2) + 24 * k, w, h,
    natural_w: nw, natural_h: nh, rotation: 0, part: part || { label, src: 'ai', conf: 0.8 } };
}
function sheet() {
  return { id: 's1', form: {}, objects: [upload('c1', '입체·내부', 1700, 1200, 0), upload('f1', '정면·내부', 1500, 1100, 1),
    upload('d1', '서랍 단면', 500, 400, 2), upload('d2', '부품 상세', 450, 380, 3), upload('t1', '평면·상판', 1300, 1000, 4)] };
}
const find = (sh, id) => sh.objects.find(o => o.id === id);
const memosHit = sh => { const n = []; sh.objects.filter(o => o.type === 'image').forEach(i => sh.objects.filter(o => /^(t-|a-)/.test(o.id))
  .forEach(m => { if (hit(i, P.stayBox(m))) { n.push(i.id + '/' + m.id); } })); return n; };
"""

# ---- 화면 배선(가짜 DOM · 가짜 코어 · 실제 v2-*.js) ---------------------------------------------------
UI = r"""
const dir = process.argv[1], PRE = JSON.parse(process.argv[2] || '{}');
let now = 0, tid = 0, timers = [];
const store = Object.assign({}, PRE.store || {});
global.window = {
  setTimeout: (fn, ms) => { const id = ++tid; timers.push({ id, fn, at: now + (ms || 0) }); return id; },
  clearTimeout: id => { timers = timers.filter(t => t.id !== id); },
  localStorage: { getItem: k => { if (PRE.blocked) { throw new Error('SecurityError'); } return k in store ? store[k] : null; },
    setItem: (k, v) => { if (PRE.blocked) { throw new Error('SecurityError'); } store[k] = String(v); } }
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
  const e = { tagName: String(tag || 'div').toUpperCase(), children: [], style: {}, attrs: {}, handlers: {}, hidden: false, disabled: false,
    className: '', title: '', type: '', _text: '' };
  Object.defineProperty(e, 'textContent', {
    get() { return e._text + e.children.map(c => c.textContent).join(''); },
    set(v) { e._text = String(v == null ? '' : v); e.children = []; } });
  e.appendChild = c => { e.children.push(c); c.parentNode = e; return c; };
  e.addEventListener = (n, fn) => { (e.handlers[n] = e.handlers[n] || []).push(fn); };
  e.click = () => (e.handlers.click || []).forEach(fn => fn({ stopPropagation() {}, preventDefault() {} }));
  e.setAttribute = (k, v) => { e.attrs[k] = String(v); };
  e.getAttribute = k => (k in e.attrs ? e.attrs[k] : null);
  const cls = new Set();
  e.classList = { add: (...c) => c.forEach(x => cls.add(x)), remove: (...c) => c.forEach(x => cls.delete(x)),
    toggle: (c, on) => { if (on === undefined ? !cls.has(c) : on) { cls.add(c); } else { cls.delete(c); } }, contains: c => cls.has(c) };
  e.querySelector = () => null;
  e.querySelectorAll = () => [];
  return e;
}
const dom = {}, menuUnpin = mkEl('button');
menuUnpin.hidden = true;
['dws-root', 'dws-v2-slots', 'dws-v2-badges', 'dws-v2-summary', 'dws-v2-templates', 'dws-v2-seen', 'dws-v2-toggles',
 'dws-v2-relayout', 'dws-v2-rearrange', 'dws-v2-unpin', 'dws-v2-detail-toggle', 'dws-v2-detail'].forEach(id => { dom[id] = mkEl('div'); dom[id].id = id; });
dom['dws-v2-detail'].hidden = true;
global.document = { readyState: 'complete', getElementById: id => dom[id] || null, querySelectorAll: () => [],
  querySelector: q => (q === '[data-v2-for="dws-v2-unpin"]' ? menuUnpin : null), createElement: mkEl, addEventListener: () => {} };
const handlers = {}, toasts = [], undo = [], state = { sheets: [] };
function emit(name, data) { (handlers[name] || []).slice().forEach(fn => fn(data)); }
const core = {
  ui: 'v2', on: (n, fn) => { (handlers[n] = handlers[n] || []).push(fn); },
  state: () => state, sheet: () => state.sheets[0] || null, canSave: () => true,
  recordUndo: () => { undo.push(JSON.stringify(state.sheets[0])); },
  undo: () => { const s = undo.pop(); if (s) { state.sheets[0] = JSON.parse(s); emit('render'); } },
  markDirty: () => emit('change'), redraw: () => emit('render'), select: () => {}, toast: m => toasts.push(m), editing: () => false, dragging: () => false,
  items: imgs => imgs.map((o, i) => ({ id: o.id, nw: o.natural_w || o.w, nh: o.natural_h || o.h, order: i, tx: 0,
    label: (o.part && o.part.label) || '미분류' })),
  baseline: () => ({}), productText: () => '몰딩 화장대 여닫이', photos: () => [], photoVisible: () => true,
  importPhoto: () => Promise.resolve(false), threshold: () => 0.5, fitCell: () => {}, hatch: () => null, viewUrl: () => '', setTool: () => {}
};
window.FomsWizardCore = core;
for (const f of ['part-pack.js', 'part-layout.js', 'v2-slots.js', 'v2-pack.js', 'v2-hero.js', 'v2-layout.js', 'v2-plan.js', 'v2-paper.js',
  'v2-right.js', 'v2-chrome.js', 'v2-shell.js']) { require(dir + '/' + f); }
const V2 = window.FomsV2;
const img = (id, label, nw, nh, k) => ({ id, type: 'image', key: id + '.png', x: 300 + 24 * k, y: 120 + 24 * k, w: Math.min(900, nw),
  h: Math.round(Math.min(900, nw) * nh / nw), natural_w: nw, natural_h: nh, rotation: 0, part: { label, src: 'ai', conf: 0.8 } });
function laid() {
  state.sheets = [{ id: 's1', name: '붙박이장', form: {}, objects: [img('c1', '입체·내부', 1700, 1200, 0), img('f1', '정면·내부', 1500, 1100, 1),
    img('d1', '서랍 단면', 500, 400, 2), img('d2', '부품 상세', 450, 380, 3), img('t1', '평면·상판', 1300, 1000, 4)] }];
  emit('batch', { ids: state.sheets[0].objects.map(o => o.id), sheetId: 's1' });
  tick(100);
  return core.sheet();
}
const cards = () => dom['dws-v2-templates'].children.filter(n => n.className === 'dws-v2-tpl');
const backLink = () => dom['dws-v2-templates'].children.find(n => /dws-v2-tpl-back/.test(n.className)) || null;
const out = {};
"""


def _node() -> str:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


def _run(head: str, body: str, pre: dict | None = None) -> dict:
    script = head + body + "\nprocess.stdout.write(JSON.stringify(out));"
    proc = subprocess.run([_node(), "-e", script, str(JS_DIR), json.dumps(pre or {})], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_free_memo_outside_pictures_is_an_obstacle_and_dimension_memo_still_follows():
    out = _run(PLAN, r"""
const base = sheet(), p0 = P.build(base, ctx), r0 = p0.out[p0.out.best];
const big = r0.moves.filter(m => find(base, m.id)).sort((a, b) => b.w * b.h - a.w * a.h)[0];   // 메모 없이 놓으면 가장 큰 그림 자리
const sh = JSON.parse(JSON.stringify(base));
sh.objects.push({ id: 't-memo', type: 'text', x: Math.round(big.x + big.w / 2 - 60), y: Math.round(big.y + big.h / 2 - 15), w: 120,
  text: '현장 기둥 주의', size: 24 });
sh.objects.push({ id: 'a-arrow', type: 'arrow', x: 0, y: 0, points: [big.x + 20, big.y + 20, big.x + 160, big.y + 70] });
out.wouldHit = hit(big, P.stayBox(find(sh, 't-memo')));   // 대조군: 장애물이 아니면 그 그림이 메모 위에 놓인다
const r1 = arrange(sh);
out.first = { ok: r1.ok, stay: r1.plan.stay, hits: memosHit(sh), memo: [find(sh, 't-memo').x, find(sh, 't-memo').y] };
// 놓인 그림(배치 자리 그대로) 안 치수 메모는 그림을 따라간다 — 장애물이 아니다
const host = sh.objects.filter(o => o.type === 'image').sort((a, b) => b.w * b.h - a.w * a.h)[0];
sh.objects.push({ id: 'dim', type: 'text', x: host.x + Math.round(host.w * 0.4), y: host.y + Math.round(host.h * 0.4), w: 40, text: '1200', size: 16 });
const rel = () => { const h = find(sh, host.id), d = find(sh, 'dim'); return [Math.round((d.x - h.x) / h.w * 100), Math.round((d.y - h.y) / h.h * 100)]; };
const relBefore = rel(), hostBefore = [host.x, host.y, host.w, host.h];
sh.form.v2_pick = r1.key === 'band' ? 'column' : 'band';
const r2 = arrange(sh), h2 = find(sh, host.id);
out.follow = { ok: r2.ok, stay: r2.plan.stay, relBefore, relAfter: rel(), hostMoved: JSON.stringify([h2.x, h2.y, h2.w, h2.h]) !== JSON.stringify(hostBefore),
  hits: memosHit(sh) };
// 잠긴 도형은 그림 안이어도 남는다(장애물) · 종이 칸 밖(아래 띠)은 세지 않는다
const h3 = find(sh, host.id);
sh.objects.push({ id: 'r-lock', type: 'rect', x: h3.x + 10, y: h3.y + 10, w: 40, h: 30, locked: true });
sh.objects.push({ id: 't-strip', type: 'text', x: 600, y: 920, w: 80, text: '아래 띠 메모', size: 18 });
out.stayMore = P.build(sh, ctx).stay;
""")
    assert out["wouldHit"], "대조군 — 메모를 가장 큰 그림 자리에 두었다"
    assert out["first"]["ok"] and out["first"]["stay"] == 2 and out["first"]["hits"] == []   # 예전엔 그림이 메모 · 화살표 위에 놓였다
    follow = out["follow"]
    assert follow["ok"] and follow["hostMoved"] and follow["stay"] == 2 and follow["hits"] == []
    assert all(abs(a - b) <= 2 for a, b in zip(follow["relBefore"], follow["relAfter"])), follow   # 치수 메모는 그림 안 같은 자리
    assert out["stayMore"] == 3


def test_template_names_recommendation_and_back_to_recommended_keeps_pins():
    out = _run(UI, r"""
laid();
out.names = cards().map(c => c.textContent);
out.backAtFirst = !!backLink();
const c1 = core.sheet().objects.find(o => o.id === 'c1');
core.recordUndo(); c1.x += 40; c1.y += 12; core.markDirty();   // 손으로 옮김 = 고정(장애물 — 추천은 고정 그림까지 넣고 잰다)
tick(100);
const rec = V2.plan().out.rec, other = rec === 'band' ? 'column' : 'band', idx = { band: 0, column: 1 };
cards()[idx[other]].click();                       // 추천이 아닌 틀을 고른다
tick(100);
out.picked = [core.sheet().form.v2_pick, core.sheet().form.v2_layout];
out.namesPicked = cards().map(c => c.textContent);
const pinned = [c1.x, c1.y, c1.w, c1.h], depth = undo.length;
const back = backLink();
out.backTitle = back ? back.title : '';
toasts.length = 0;
back.click();
tick(100);
const c1b = core.sheet().objects.find(o => o.id === 'c1');
out.after = [core.sheet().form.v2_pick, core.sheet().form.v2_layout === rec, JSON.stringify([c1b.x, c1b.y, c1b.w, c1b.h]) === JSON.stringify(pinned)];
out.undoAdded = undo.length - depth;
out.toast = toasts.slice(-1)[0] || '';
out.backGone = !backLink();
""")
    band, column = out["names"]
    assert "사진·상세를 위에" in band and "사진·상세를 왼쪽에" in column
    assert all("띠형" not in n and "기둥형" not in n and "선택됨" not in n and "(고름)" not in n for n in out["names"])
    assert any("지금 쓰는 틀 · 추천" in n for n in out["names"]) and not out["backAtFirst"]   # 추천 틀을 쓰는 중 — 돌아갈 곳 없음
    assert out["picked"][0] == out["picked"][1] and out["picked"][0] in ("band", "column")
    assert sum("지금 쓰는 틀" in n for n in out["namesPicked"]) == 1 and sum("추천" in n for n in out["namesPicked"]) == 1
    assert "추천 틀(" in out["backTitle"] and "고정된 그림은 그 자리에" in out["backTitle"]
    assert out["after"] == ["", True, True], "고른 틀만 풀고 추천 틀로 — 고정 그림은 그대로"
    assert out["undoAdded"] == 1 and "추천 틀(사진·상세를" in out["toast"] and "Ctrl+Z" in out["toast"]
    assert "고정된 그림 1장" in out["toast"] and out["backGone"]


def test_details_fold_by_default_remember_and_survive_blocked_storage():
    body = r"""
laid();
const btn = dom['dws-v2-detail-toggle'], box = dom['dws-v2-detail'];
out.start = [box.hidden, btn.textContent, btn.getAttribute('aria-expanded'), dom['dws-v2-seen'].children.length];
btn.click();
out.opened = [box.hidden, btn.textContent, btn.getAttribute('aria-expanded'), dom['dws-v2-seen'].children.length > 0];
out.saved = (() => { try { return window.localStorage.getItem('foms.dws.v2.detail'); } catch (e) { return 'blocked'; } })();
"""
    fresh = _run(UI, body)
    assert fresh["start"] == [True, "자세히 ▸", "false", 0]          # 처음엔 접힘 — 접힌 동안 '컴퓨터가 본 것'은 그리지 않는다
    assert fresh["opened"] == [False, "자세히 ▾", "true", True] and fresh["saved"] == "1"
    remembered = _run(UI, body, {"store": {"foms.dws.v2.detail": "1"}})
    assert remembered["start"][:3] == [False, "자세히 ▾", "true"] and remembered["start"][3] > 0
    blocked = _run(UI, body, {"blocked": True})                    # 사생활 보호 모드 · 막힌 저장소 — 접힘으로 시작하고 눌러도 돈다
    assert blocked["start"][:3] == [True, "자세히 ▸", "false"] and blocked["opened"][:3] == [False, "자세히 ▾", "true"]


def test_unpin_shows_with_pins_in_foot_and_more_menu_and_toasts_do_not_point_right():
    out = _run(UI, r"""
laid();
out.menuAtFirst = [menuUnpin.hidden, dom['dws-v2-unpin'].hidden];
const c1 = core.sheet().objects.find(o => o.id === 'c1');
core.recordUndo(); c1.x += 40; c1.y += 12; core.markDirty();
toasts.length = 0;
dom['dws-v2-relayout'].click();
tick(100);
out.menuPinned = [menuUnpin.hidden, menuUnpin.textContent, dom['dws-v2-unpin'].hidden];
out.toast = toasts.slice(-1)[0] || '';
const C = window.FomsV2Chrome, plan = { g: { fixed: { a: 1, b: 1 } }, stay: 0, pick: '', out: { best: 'band' } };
out.fail = C.arrangeText('button', null, plan);
out.failMemo = C.arrangeText('batch', null, { g: { fixed: {} }, stay: 3, out: { best: 'band' } });
out.memo = C.arrangeText('button', { n: 2, any: true }, { g: { fixed: {} }, stay: 3, out: { best: 'band' } });
out.unpick = C.arrangeText('unpick', { n: 4, any: true }, { g: { fixed: {} }, stay: 0, pick: '', out: { best: 'band' } });
out.same = C.arrangeText('button', { n: 0, any: false }, { g: { fixed: {} }, stay: 0, pick: 'column', out: { best: 'column' } });
""")
    assert out["menuAtFirst"] == [True, True]
    assert out["menuPinned"][0] is False and "고정 풀고 모두 다시 (고정 1장)" == out["menuPinned"][1] and out["menuPinned"][2] is False
    for text in (out["toast"], out["fail"]):
        assert "[고정 풀고 모두 다시]" in text and "오른쪽" not in text, text
    assert "그림 밖 메모 3개가 자리를 차지해요" in out["failMemo"] and "그림 밖 메모 3개는 비켜 놓았어요" in out["memo"]
    assert out["unpick"].startswith("추천 틀(사진·상세를 위에)로 다시 놓았어요")
    assert "고른 틀: 사진·상세를 왼쪽에" in out["same"]
    for name in ("v2-right.js", "v2-chrome.js"):
        src = (JS_DIR / name).read_text(encoding="utf-8")
        assert "'위 띠형'" not in src and "'왼쪽 기둥형'" not in src and "오른쪽 [고정" not in src, name   # 화면 글(따옴표 글자)


def test_templates_css_tools_sticky_banner_and_pins():
    right = RIGHT.replace("\r\n", "\n")
    assert '<h3 class="dws-v2-section-title">틀 고르기</h3>' in right and "틀 후보" not in right
    toggle = right.index('id="dws-v2-detail-toggle"')
    detail = right.index('<div class="dws-v2-detail" id="dws-v2-detail" hidden>')
    assert toggle < detail < right.index('id="dws-v2-seen"') < right.index('id="dws-v2-toggles"') < right.index('class="dws-v2-right-foot"')
    assert 'aria-expanded="false"' in right and ">자세히 ▸</button>" in right and "style=" not in right
    v2_block = TPL[TPL.index("{% if wizard_ui == 'v2' %}\n        {# V2: K2"):TPL.index('id="dws-btn-room-push"')]
    assert ('<button type="button" class="dws-btn dws-v2-uiback" data-dws-ui-switch="v1" '
            'title="예전 화면(V1)으로 돌아가요 · 고치던 것은 저장돼요">예전 화면</button>') in v2_block
    assert '<button type="button" class="dws-menu-item" data-v2-for="dws-v2-unpin" hidden>고정 풀고 모두 다시</button>' in v2_block
    assert "css/contexts/drawing/wizard-v2.css') }}?v=20261027e" in TPL
    for asset in ("js/drawing/v2-plan.js", "js/drawing/v2-right.js", "js/drawing/v2-chrome.js", "js/drawing/v2-shell.js"):   # 10-28 주 그림 크게
        assert f"{asset}') }}}}?v=20261028a" in TPL, asset
    assert ".dws-v2-auto .dws-appbar-center .dws-seg" not in CSS                       # 자동 배치에도 도구가 보인다
    assert ".dws-v2.dws-v2-auto #dws-btn-preset { display: none !important; }" in CSS
    banner = CSS[CSS.index(".dws-v2-banner {"):CSS.index(".dws-v2-banner[hidden]")]
    assert "position: sticky;" in banner and "top: 8px;" in banner
    assert ".dws-v2 #dws-v2-more-menu .dws-menu-item[hidden] { display: none; }" in CSS
    narrow = CSS[CSS.index("@media (min-width: 1180px) and (max-width: 1279px) {"):]
    assert ".dws-v2-mode { padding-left: 10px; padding-right: 10px; }" in narrow[:300]
    assert re.search(r"\.dws-v2-detail\[hidden\] \{ display: none; \}", CSS)


def _login(client, username):
    user = User(username=username, password=generate_password_hash("x"), role="ADMIN", team="DRAWING", name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


def test_old_screen_button_only_on_v2_page(client):
    _login(client, "v2right_a")
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="오른쪽", phone="010-1111-2222", address="대구",
                  product="붙박이장", status="DRAWING", manager_name="영업", is_erp_order=True,
                  structured_data={"parties": {"customer": {"name": "오른쪽"}}})
    db_session.add(order)
    db_session.commit()
    v2 = client.get(f"/erp/drawing-workbench/{order.id}/wizard?ui=v2").get_data(as_text=True)
    v1 = client.get(f"/erp/drawing-workbench/{order.id}/wizard?ui=v1").get_data(as_text=True)
    assert v2.count('data-dws-ui-switch="v1"') == 2 and 'class="dws-btn dws-v2-uiback"' in v2   # 앱바 단추 + ⋯ 메뉴
    assert 'data-v2-for="dws-v2-unpin"' in v2 and 'id="dws-v2-detail-toggle"' in v2
    assert "dws-v2-uiback" not in v1 and 'data-dws-ui-switch="v1"' not in v1


def test_main_picture_toggle_is_listed_and_on_by_default():
    """주 그림 크게(bento — 사용자 요청 2026-10-28)는 켜고 끄기 다섯째(기본 켬) — 끄면 예전처럼 큰 그림 칸이 같은 배율 한 줄."""
    right = (JS_DIR / "v2-right.js").read_text(encoding="utf-8")
    assert "['sameScale', '같은 칸은 같은 배율'], ['hero', '주 그림 크게'], ['lockMoved', '손으로 옮긴 그림은 고정']" in right
    assert "켜고 끄기 5" in right
    shell = (JS_DIR / "v2-shell.js").read_text(encoding="utf-8")
    assert "lockMoved: true, hero: true }" in shell
    plan = (JS_DIR / "v2-plan.js").read_text(encoding="utf-8")
    assert "hero: s.hero !== false" in plan and "hero: set.hero" in plan


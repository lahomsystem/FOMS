// ERP 대시보드 [도면 전달] 창(erp-dashboard-drawing-fix.js + 공용 조각)과 태블릿 갤러리 '시트 전달'(tablet-drawing-gallery.js)을
// 작은 가짜 화면에서 실제로 돌린다(node — tests/domains/test_drawing_fix_other_paths.py). 설계서 2026-11-25 D2 · 지휘 L · M.
// argv: [2]=drawing-fix-send.js [3]=drawing-fix-picks.js [4]=erp-dashboard-drawing-fix.js [5]=tablet-drawing-gallery.js [6]=시나리오
// 시나리오: dash_hotfix · dash_plain · tablet_no_memo · tablet_send · tablet_refused
'use strict';
const fs = require('fs');
const [sendSrc, picksSrc, dashSrc, tabletSrc, scenario] = process.argv.slice(2).map((a, i) => (i < 4 ? fs.readFileSync(a, 'utf8') : a));

function el(tag, extra) {
  const node = Object.assign({ tagName: tag, className: '', hidden: false, disabled: false, value: '', id: '', type: '',
    children: [], listeners: {}, attrs: {}, style: {},
    appendChild(c) { node.children.push(c); return c; },
    setAttribute(k, v) { node.attrs[k] = String(v); },
    getAttribute(k) { return k in node.attrs ? node.attrs[k] : null; },
    hasAttribute(k) { return k in node.attrs; },
    addEventListener(n, fn) { (node.listeners[n] = node.listeners[n] || []).push(fn); },
    click() { if (!node.disabled) { (node.listeners.click || []).forEach((fn) => fn({ target: node })); } },
    focus() { node.focused = true; }, remove() {}, closest() { return null; },
    classList: { toggle() {}, contains() { return false; }, add() {}, remove() {} },
    querySelector() { return null; }, querySelectorAll() { return []; } }, extra || {});
  Object.defineProperty(node, 'textContent', { get() { return node._t || ''; }, set(v) { node._t = v; if (v === '') { node.children = []; } } });
  if (tag === 'dialog') {
    node.showModal = () => { out.dialogs.push(1); setTimeout(() => node.children[2].children[1].click(), 0); };
    node.close = () => (node.listeners.close || []).forEach((fn) => fn());
  }
  return node;
}

const out = { calls: [], dialogs: [], confirms: [], alerts: [] };
const byId = {};
const listeners = {};
let r1Hotfix = scenario !== 'dash_plain';
global.window = global;
global.document = { readyState: 'complete', body: el('body'),
  getElementById: (id) => byId[id] || null,
  createElement: (t) => el(t),
  querySelector: (sel) => (sel === '[data-foms-drawing-fix-box]' ? byId.__fixBox || null : null),
  querySelectorAll: () => [],
  addEventListener(n, fn) { (listeners[n] = listeners[n] || []).push(fn); } };
global.localStorage = { getItem: () => null, setItem() {} };
global.matchMedia = () => ({ matches: false, addEventListener() {} });
global.getComputedStyle = () => ({ getPropertyValue: () => '' });
global.confirm = (t) => { out.confirms.push(t); return true; };
global.alert = (t) => { out.alerts.push(t); };
global.location = { reload() { out.reloaded = true; } };
const posts = scenario === 'tablet_refused'
  ? [{ success: false, error: '공장 수정 요청을 [반영 완료]나 [요청 반려]로 처리한 뒤에 보낼 수 있어요.', data: { code: 'FACTORY_REQUEST_OPEN' } }]
  : [{ success: false, error: 'w', data: { code: 'WORKED_DRAWING', warnings: [{ ident: 'sheet:s1', text: '도면 2는 …', line: '' }] } }, { success: true }];
global.fetch = (url, opts) => {
  const method = (opts && opts.method) || 'GET';
  out.calls.push({ method, url, body: opts && opts.body ? JSON.parse(opts.body) : null });
  if (method === 'GET' && url.indexOf('?') < 0) {   // R1 — 창을 열 때 단계 · 지금 도면
    return Promise.resolve({ json: () => Promise.resolve({ success: true, data: { hotfix: r1Hotfix,
      drawings: [{ key: 'k/d1.png' }, { key: 'k/d2.png' }] } }) });
  }
  if (method === 'GET') {
    return Promise.resolve({ json: () => Promise.resolve({ success: true, data: { plan: { changed_line: '바뀐 도면: 도면 2 (고침)', warnings: [] } } }) });
  }
  return Promise.resolve({ status: 200, json: () => Promise.resolve(posts.shift() || { success: true }) });
};
const tick = (ms) => new Promise((r) => setTimeout(r, ms || 260));

eval(sendSrc);   // eslint-disable-line no-eval — 시험 전용: 실제 파일을 그대로 돌린다
eval(picksSrc);  // eslint-disable-line no-eval

(async () => {
  if (scenario.indexOf('dash') === 0) {
    const rows = el('div');
    const picks = el('div', { hidden: true, querySelector: (s) => (s === '[data-dfx-pick-rows]' ? rows : null) });
    const only = [el('span', { hidden: true }), el('div', { hidden: true })];
    const parts = { '[data-dfx-dash-changed]': el('div', { hidden: true }), '[data-dfx-dash-picks]': picks,
      '[data-dfx-dash-picks] [data-dfx-pick-rows]': rows, '[data-dfx-dash-note-error]': el('div', { hidden: true }) };
    byId.erpDrawingTransferModal = el('div', { querySelector: (s) => parts[s] || null,
      querySelectorAll: (s) => (s === '[data-dfx-dash-only]' ? only : []) });
    byId['drawing-transfer-files'] = el('input', { id: 'drawing-transfer-files', files: [] });
    byId['drawing-transfer-note'] = el('textarea', { id: 'drawing-transfer-note' });
    byId['drawing-transfer-replace-wrap'] = el('div');
    eval(dashSrc);   // eslint-disable-line no-eval
    const D = window.FomsDashboardFix;
    const opened = await D.open(77, true);
    const files = [{ name: 'a.pdf', size: 1, lastModified: 1 }, { name: 'b.pdf', size: 2, lastModified: 1 }];
    byId['drawing-transfer-files'].files = files;
    (listeners.change || []).forEach((fn) => fn({ target: byId['drawing-transfer-files'] }));
    out.opened = opened;
    out.active = D.active(77);
    out.onlyShown = only.map((e) => !e.hidden);
    out.replaceHidden = byId['drawing-transfer-replace-wrap'].style.display === 'none';
    out.picksShown = !picks.hidden;
    out.noteCheck = D.active() ? D.check('') : '';
    out.noteErrorShown = !parts['[data-dfx-dash-note-error]'].hidden;
    if (D.active()) {
      rows.children[0].children[1].children[0].click();   // a → 도면 1
      out.secondRowFirstOff = rows.children[1].children[1].children[0].disabled;   // b 줄 도면 1 꺼짐
      out.pickCheck = D.check('메모');
      rows.children[1].children[1].children[2].click();   // b → 새 도면
      out.readyCheck = D.check('메모');
      out.attached = D.attach([{ key: 'u/a', filename: 'a.pdf' }, { key: 'u/b', filename: 'b.pdf' }], files);
      await tick();
      out.changed = parts['[data-dfx-dash-changed]'].textContent;
      out.confirm = await D.confirmSend();
    }
  } else {
    const box = el('div');
    const note = el('textarea', { value: scenario === 'tablet_no_memo' ? '  ' : '문짝 손잡이 위치' });
    const err = el('div', { hidden: true });
    const msg = el('div', { hidden: true });
    box.querySelector = (s) => ({ '[data-foms-drawing-fix-note]': note, '[data-foms-drawing-fix-error]': err,
      '[data-foms-drawing-fix-msg]': msg })[s] || null;
    byId.__fixBox = box;
    eval(tabletSrc);   // eslint-disable-line no-eval
    const btn = el('button', { attrs: { 'data-order-id': '77', 'data-foms-drawing-fix': '', 'data-foms-fix-sheets': 's1,s2' } });
    btn.closest = (s) => (s === '[data-foms-drawing-transfer]' ? btn : null);
    (listeners.click || []).forEach((fn) => fn({ target: btn, preventDefault() {}, stopPropagation() {} }));
    await tick(120);
    out.errorShown = !err.hidden;
    out.message = msg.hidden ? '' : msg.textContent;
    out.focused = !!note.focused;
  }
  await tick(50);
  process.stdout.write(JSON.stringify(out));
})();

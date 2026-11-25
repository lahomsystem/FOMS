// workbench-transfer-fix.js 를 작은 가짜 작업실 전달 창에서 실제로 돌린다(node — tests/domains/test_drawing_fix_send_js.py).
// 시나리오(argv[3]): remove · same · reopen. 출력(stdout JSON): 단계마다 고르기 줄 모습 · 미리 보기 질의 · 붙인 replace_of.
'use strict';
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const scenario = process.argv[3];
const picksSrc = fs.readFileSync(process.argv[4], 'utf8');   // 공용 고르기 조각(drawing-fix-picks.js)

function el(tag, extra) {
  const node = Object.assign({
    tagName: tag, className: '', textContent: '', hidden: false, disabled: false, type: '', id: '', value: '',
    children: [], listeners: {}, attrs: {},
    appendChild(child) { node.children.push(child); return child; },
    setAttribute(k, v) { node.attrs[k] = v; },
    addEventListener(name, fn) { (node.listeners[name] = node.listeners[name] || []).push(fn); },
    click() { if (!node.disabled) { (node.listeners.click || []).forEach((fn) => fn({ target: node })); } },
    classList: { toggle() {}, contains() { return false; } },
    closest() { return null; },
  }, extra || {});
  Object.defineProperty(node, 'textContent', {
    get() { return node._text || ''; },
    set(v) { node._text = v; if (v === '') { node.children = []; } },
  });
  return node;
}

const rows = el('div');
const picksWrap = el('div', { querySelector: (sel) => (sel === '[data-dfx-pick-rows]' ? rows : null) });
const changed = el('div');
const noteErr = el('div');
const modal = el('div', {
  id: 'dwTransferModal',
  querySelector: (sel) => ({ '[data-dfx-changed]': changed, '[data-dfx-picks]': picksWrap, '[data-dfx-note-error]': noteErr })[sel] || null,
});
let cfg = { order_id: 77, drawing_status: 'CONFIRMED', drawing_files: [
  { key: 'k/d1.png', sheet_id: 's1' }, { key: 'k/d2.png', sheet_id: 's2' }, { key: 'k/d3.png' }] };
const configEl = el('script');
Object.defineProperty(configEl, 'textContent', { get() { return JSON.stringify(cfg); } });
const fileInput = el('input', { id: 'dw-transfer-files', files: [] });
const modeEl = el('select', { id: 'dw-transfer-mode', value: 'APPEND' });
const noteEl = el('textarea', { id: 'dw-transfer-note', value: '' });
const byId = { dwTransferModal: modal, 'erp-drawing-workbench-config': configEl, 'dw-transfer-files': fileInput,
  'dw-transfer-mode': modeEl, 'dw-transfer-note': noteEl };
const docListeners = {};
let pendingChecked = [];
global.window = global;
global.document = {
  getElementById: (id) => byId[id] || null,
  querySelectorAll: (sel) => (sel.indexOf('dw-pending-checkbox') >= 0 ? pendingChecked.map((v) => ({ value: v })) : []),
  createElement: (tag) => el(tag),
  addEventListener(name, fn, capture) { (docListeners[name] = docListeners[name] || []).push({ fn, capture: !!capture }); },
};
function fire(name, target) { (docListeners[name] || []).forEach((l) => l.fn({ target })); }
const previews = [];
global.FomsFixSend = {
  NOTE_MSG: '공장에 남길 메모를 적어 주세요.', PICK_MSG: '바꿀 도면을 골라 주세요.', HOTFIX_TEXT: 'H',
  preview: (id, plan) => { previews.push(plan); return Promise.resolve({ changed_line: 'L' }); },
  setChanged: () => {},
  gate: (id, plan, text) => Promise.resolve({ ok: true, ack: { idents: [], orderMade: false }, plan, text: text({ changed_line: 'L' }) }),
  post: () => Promise.resolve({ success: true }),
};

eval(picksSrc);   // eslint-disable-line no-eval — 시험 전용: 실제 파일을 그대로 돌린다
eval(src);   // eslint-disable-line no-eval

function file(name) { return { name, size: name.length * 10, lastModified: 1 }; }
function view() {
  return rows.children.map((row) => ({
    name: row.children[0].textContent,
    chips: row.children[1].children.map((b) => b.textContent + (b.className.indexOf('is-on') >= 0 ? '*' : '') + (b.disabled ? '(off)' : '')),
  }));
}
function chip(rowIndex, label) {
  rows.children[rowIndex].children[1].children.find((b) => b.textContent === label).click();
}
const out = { steps: [] };
const tick = () => new Promise((r) => setTimeout(r, 260));
const W = window.FomsWorkbenchFix;

(async () => {
  fire('show.bs.modal', modal);
  fileInput.files = [file('a.pdf'), file('b.pdf'), file('c.pdf')];
  fire('change', fileInput);
  if (scenario === 'remove') {
    chip(0, '도면 1');
    chip(1, '도면 2');
    chip(2, '새 도면');
    out.steps.push({ at: 'picked', view: view() });
    // 미리 보기 [x] — removeFileFromPreview 는 change 를 안 낸다: 붙잡는 단계 click 만 온다
    const xBtn = el('button', { closest: (sel) => (sel.indexOf('#dw-transfer-preview') === 0 ? {} : null) });
    fire('click', xBtn);
    fileInput.files = [fileInput.files[0], fileInput.files[2]];
    await tick();
    out.steps.push({ at: 'removed', view: view(), check: W.check('메모') });
    out.attached = W.attachPicks([{ key: 'u/a', filename: 'a.pdf' }, { key: 'u/c', filename: 'c.pdf' }], fileInput.files);
    out.lastPreview = previews[previews.length - 1];
    out.confirm = await W.confirmSend();
  } else if (scenario === 'same') {
    chip(0, '도면 1');
    pendingChecked = ['s2'];   // 전달 대기 시트 s2 의 새 판이 도면 2 를 바꾼다
    fire('change', { id: 'x', classList: { contains: (c) => c === 'dw-pending-checkbox' } });
    out.steps.push({ at: 'one_picked', view: view() });
    chip(1, '도면 1');   // 꺼진 단추 — 눌러도 안 바뀐다(가짜 DOM 도 disabled 면 click 을 안 낸다)
    out.steps.push({ at: 'second_tried', check: W.check('메모') });
  } else if (scenario === 'reopen') {
    chip(0, '도면 1');
    chip(1, '도면 2');
    chip(2, '도면 3');
    out.steps.push({ at: 'picked', check: W.check('메모') });
    fire('show.bs.modal', modal);
    out.steps.push({ at: 'reopened', view: view(), check: W.check('메모') });
    chip(0, '도면 1'); chip(1, '도면 2'); chip(2, '도면 3');
    cfg = Object.assign({}, cfg, { order_id: 78 });   // ERP 셸에서 다른 주문 상세로
    out.steps.push({ at: 'other_order', check: W.check('메모'), noteCheck: W.check('  ') });
  }
  await tick();
  process.stdout.write(JSON.stringify(out));
})();

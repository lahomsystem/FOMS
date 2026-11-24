// wizard-factory.js 를 작은 가짜 화면에서 돌려 공장 줄 접기 · [공장 지정] 펼침 단추를 본다
// (node 로 실행 — tests/domains/test_drawing_wizard_factory_fold.py).
// 입력(stdin JSON): {by_sheet: {id: 2}, can_set: bool, clicks: n, side: bool}
// 출력(stdout JSON): {fold, row, steps:[{expanded, hidden}], core_calls:[이름], side_first}
'use strict';
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));

function el(tag) {
  const handlers = {};
  const attrs = {};
  const node = {
    tagName: String(tag || 'div').toUpperCase(), children: [], parentNode: null, hidden: false, disabled: false,
    className: '', id: '', textContent: '', type: '',
    classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } },
    setAttribute(name, value) { attrs[name] = String(value); },
    getAttribute(name) { return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null; },
    addEventListener(name, fn) { (handlers[name] = handlers[name] || []).push(fn); },
    fire(name) { (handlers[name] || []).forEach((fn) => fn({ target: node, preventDefault() {}, stopPropagation() {} })); },
    appendChild(child) { child.parentNode = node; node.children.push(child); return child; },
    insertBefore(child, ref) {
      child.parentNode = node;
      const i = ref ? node.children.indexOf(ref) : -1;
      if (i < 0) node.children.push(child); else node.children.splice(i, 0, child);
      return child;
    },
    get firstChild() { return node.children[0] || null; },
    get nextSibling() {
      const sib = node.parentNode ? node.parentNode.children : [];
      return sib[sib.indexOf(node) + 1] || null;
    },
    querySelectorAll(sel) {
      const out = [];
      const want = sel === '[data-fac]' ? (n) => n.getAttribute('data-fac') !== null : () => false;
      (function walk(n) { n.children.forEach((c) => { if (want(c)) out.push(c); walk(c); }); })(node);
      return out;
    },
    querySelector(sel) { return node.querySelectorAll(sel)[0] || null; },
    focus() {},
  };
  return node;
}

const body = el('body');
const tabrow = body.appendChild(el('div'));
tabrow.className = 'dws-tabrow';
const side = el('div');
side.id = 'dws-v2-tabstatus';
const v2btn = side.appendChild(el('button'));
v2btn.className = 'dws-ui-switch-btn';
if (input.side !== false) tabrow.appendChild(side);
body.appendChild(el('div')).className = 'dws-body';

const cfgEl = el('script');
cfgEl.textContent = JSON.stringify({ factory: { can_set: input.can_set !== false, by_sheet: input.by_sheet || {} } });
const calls = [];
const handlers = {};
const sheet = { id: 'sheet-a', name: '침대 수납장' };
const core = {
  orderId: 7,
  on(name, fn) { (handlers[name] = handlers[name] || []).push(fn); },
  tabbar() { return el('div'); },
  state() { calls.push('state'); return { sheets: [sheet] }; },
  sheet() { return sheet; },
  hydrated() { return true; },
};
['markDirty', 'save', 'saveAll', 'queueSheets', 'recordUndo', 'renderForm', 'toast'].forEach((name) => {
  core[name] = function () { calls.push(name); return Promise.resolve(true); };
});

global.window = { FomsWizardCore: core, FomsSheetFactory: {} };
global.document = {
  readyState: 'complete',
  getElementById(id) {
    if (id === 'drawing-wizard-config') return cfgEl;
    if (id === 'dws-v2-tabstatus') return input.side !== false ? side : null;
    return null;
  },
  querySelector(sel) { return sel === '.dws-tabrow' ? tabrow : null; },
  createElement(tag) { return el(tag); },
  addEventListener() {},
};
global.localStorage = { setItem() { calls.push('localStorage'); }, getItem() { calls.push('localStorage'); return null; } };
global.sessionStorage = global.localStorage;

new Function(src)();   // eslint-disable-line no-new-func

const row = body.children.find((c) => c.id === 'dsf-toolrow') || null;
const fold = side.children.find((c) => c.id === 'dsf-fold') || null;
const steps = [];
const snap = () => steps.push({ expanded: fold ? fold.getAttribute('aria-expanded') : null, hidden: row ? row.hidden : null });
snap();
for (let i = 0; i < (input.clicks || 0); i += 1) { if (fold) fold.fire('click'); snap(); }
process.stdout.write(JSON.stringify({
  fold: fold && { text: fold.textContent, type: fold.type, controls: fold.getAttribute('aria-controls'), className: fold.className },
  row: row && { className: row.className, next_to_tabrow: tabrow.nextSibling === row },
  side_first: side.children[0] === fold,
  side_count: side.children.length,
  steps,
  core_calls: calls.filter((name) => name !== 'state'),
}));

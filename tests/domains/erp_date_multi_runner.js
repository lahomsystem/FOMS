// static/js/orders/erp-date-multi.js 를 작은 가짜 화면 · 가짜 flatpickr(erp_date_multi_fakes.js)에서 돌려 본 것을 적는다
// (node 로 실행 — tests/domains/test_erp_date_multi_mobile.py).
// 입력(argv[2]): erp-date-multi.js 경로, 출력(stdout JSON): {phone:{...}, pc:{...}}
'use strict';
const fs = require('fs');
const path = require('path');
const fakes = require(path.join(__dirname, 'erp_date_multi_fakes.js'));

const SRC = fs.readFileSync(process.argv[2], 'utf8');
const { makeDom, SHARED_DEFAULT_IGNORED } = fakes;
const load = (dom) => fakes.load(dom, SRC);

function field(dom, parent, labelText, attrs, forId) {
  const box = dom.doc.createElement('div');
  const label = dom.doc.createElement('label');
  label.textContent = labelText;
  if (forId) label.setAttribute('for', forId);
  box.appendChild(label);
  const inner = dom.doc.createElement('div');
  const input = dom.doc.createElement('input');
  Object.keys(attrs).forEach((k) => (k === 'value' ? (input.value = attrs[k]) : input.setAttribute(k, attrs[k])));
  inner.appendChild(input);
  box.appendChild(inner);
  if (parent) parent.appendChild(box);
  return { box, label, input };
}

function labelledText(dom, view) {
  return (view.getAttribute('aria-labelledby') || '').split(' ').map((id) => {
    const el = dom.doc.body.querySelectorAll('#' + id)[0];
    return el ? el.textContent : '?';
  }).join(' | ');
}

function phone() {
  const dom = makeDom();
  const form = dom.doc.createElement('div');
  form.className = 'erp-order-mobile-form';
  dom.doc.body.appendChild(form);
  const main = field(dom, form, '시공일', { id: 'c', class: 'foms-input foms-tabular', placeholder: '2026-03-13', value: '2026-12-03, 2026-12-04' }, 'c');
  const win = load(dom);
  const log = [];
  main.input.addEventListener('change', () => log.push('change:' + main.input.value));
  main.input.addEventListener('input', () => log.push('input:' + main.input.value));
  // 인라인 저장(inline-edit.js)이 듣는 두 신호 — 칸 focus · #erp-items focusin(버블)
  main.input.addEventListener('focus', () => { main.input.inlinePrev = main.input.value; });
  form.addEventListener('focusin', (ev) => { if (ev.target === main.input) log.push('focusin'); });
  let extraReady = 0;
  const fp = win.ErpDateMulti.attach(main.input, {
    onReady: () => { extraReady += 1; },
    onChange: () => log.push('hook:' + main.input.value),
  });
  const view = main.input._erpDateView;
  const out = {};
  out.init = {
    readonly: main.input.readOnly === true, src: main.input.classList.contains('erp-fp-src'),
    viewNext: main.box.children[1].children[1] === view, view: view.textContent, cls: view.className,
    role: view.getAttribute('role'), tabIndex: view.tabIndex, expanded: view.getAttribute('aria-expanded'),
    name: labelledText(dom, view), dataErp: Object.keys(view.attrs).filter((k) => k.indexOf('data-') === 0),
    allowInput: fp.config.allowInput, positionFn: typeof fp.config.position === 'function',
    ignored: fp.config.ignoredFocusElements !== SHARED_DEFAULT_IGNORED && fp.config.ignoredFocusElements[0] === view,
    sharedIgnoredEmpty: SHARED_DEFAULT_IGNORED.length === 0, extraReady,
    sheet: fp.calendarContainer.classList.contains('erp-fp-sheet'), yearReadonly: fp.currentYearElement.readOnly === true,
    clearBtn: !!fp.calendarContainer.querySelector('.erp-fp-clear-btn'), done: fp.calendarContainer.querySelector('.erp-fp-done-btn').textContent.trim(),
  };
  // 문서에 붙기 전에 만든 항목 칸(빈 값)
  const row = field(dom, null, '항목 실측일', { class: 'foms-input foms-tabular erp-item-date-multiple', 'data-erp': 'measurement_date', placeholder: '여러 날짜 가능', value: '' });
  const itemFp = win.ErpDateMulti.attach(row.input);
  form.appendChild(row.box);
  const iv = row.input._erpDateView;
  out.item = { phone: !!iv, allowInput: itemFp.config.allowInput, view: iv.textContent, empty: iv.classList.contains('is-empty'),
    name: labelledText(dom, iv), placeholderHidden: iv.querySelector('.erp-fp-placeholder').getAttribute('aria-hidden') };
  // 다른 창의 '여러 날짜면 두 칸 위아래로 쌓기'(erpNewItemRow — 묶음이 change · input 때 칸 value 에 ',' 가 있는지 본다)가
  // 숨은 입력 칸 · 보기 칸 방식에서도 도는지: 달력이 change 를 내고 value 는 저장 값 그대로 읽힌다.
  const stack = [];
  row.box.addEventListener('change', () => stack.push(String(row.input.value || '').includes(',')));
  itemFp.pick('2026-12-01');
  itemFp.pick('2026-12-02');
  out.item.viewTwo = iv.textContent;
  itemFp.clear();
  out.item.stack = stack;
  // 밖에서 value 쓰기(서버 값 채우기 · 작성 중 복원)
  main.input.value = '2026-12-07';
  out.externalView = view.textContent;
  // 보기 칸 누르기 → 열림 · 인라인 '바꾸기 전 값' · 판에 가리면 칸을 올림
  view.rect = { top: 700, bottom: 746, height: 46 };
  fp.calendarContainer.rect = { top: 844, bottom: 1281, height: 437 };
  view.fire('click');
  out.open = { isOpen: fp.isOpen, expanded: view.getAttribute('aria-expanded'), inlinePrev: main.input.inlinePrev,
    focusin: log.indexOf('focusin') >= 0, active: dom.doc.activeElement === view ? 'view' : dom.doc.activeElement.tagName,
    scrolled: view.scrolled.slice(), sheetVar: view.style.props['--erp-fp-sheet-h'], positioned: fp.positioned };
  log.length = 0;
  fp.pick('2026-12-15');
  out.pick = { value: main.input.value, view: view.textContent, log: log.slice() };
  log.length = 0;
  fp.calendarContainer.querySelector('.erp-fp-clear-btn').fire('click');
  out.clear = { value: main.input.value, view: view.textContent, empty: view.classList.contains('is-empty'),
    args: fp.clearArgs, open: fp.isOpen, log: log.slice() };
  dom.doc.activeElement = dom.doc.body;
  fp.calendarContainer.querySelector('.erp-fp-done-btn').fire('click');
  out.done = { open: fp.isOpen, expanded: view.getAttribute('aria-expanded'), focusView: dom.doc.activeElement === view };
  // 키보드: Enter 로 열기 → 날짜 칸 포커스 → 고르기(칸이 새로 그려져도 포커스 유지) → 보기 칸 Escape
  fp.setDate(['2026-12-12']);
  view.fire('keydown', { key: 'Enter' });
  const a1 = dom.doc.activeElement;
  out.kbd = { open: fp.isOpen, focusDay: a1.iso || a1.tagName };
  fp.calendarContainer.fire('keydown', { key: 'ArrowRight' });
  fp.pick('2026-12-13');
  const a2 = dom.doc.activeElement;
  out.kbd.afterPick = { value: main.input.value, focusDay: a2.iso || a2.tagName, connected: a2.isConnected };
  fp.close();
  out.kbd.closedFocusView = dom.doc.activeElement === view;
  view.fire('keydown', { key: ' ' });
  view.fire('keydown', { key: 'Escape' });
  out.kbd.spaceOpenEscapeClose = !fp.isOpen;
  // 손가락으로 고르면 포커스를 만들지 않는다
  view.fire('click');
  fp.calendarContainer.fire('pointerdown');
  dom.doc.activeElement = dom.doc.body;
  fp.pick('2026-12-20');
  out.touchPickActive = dom.doc.activeElement.tagName;
  fp.close();
  // 가로 폰(높이 360): 판이 화면을 거의 덮으면 칸을 올리지 않는다(올릴 자리가 없다)
  win.innerHeight = 360;
  view.scrolled = [];
  view.rect = { top: 254, bottom: 300, height: 46 };
  fp.calendarContainer.rect = { top: 17, bottom: 360, height: 343 };
  view.fire('click');
  out.landscapeScrolled = view.scrolled.length;
  fp.close();
  win.innerHeight = 844;
  // 이미 판 위에 보이는 칸은 그대로
  view.scrolled = [];
  view.rect = { top: 200, bottom: 246, height: 46 };
  fp.calendarContainer.rect = { top: 407, bottom: 844, height: 437 };
  view.fire('click');
  out.visibleScrolled = view.scrolled.length;
  fp.close();
  // 잠긴 칸은 안 열린다
  main.input.disabled = true;
  view.fire('click');
  out.disabledOpens = fp.isOpen;
  // for= 이름 누르기
  main.input.disabled = false;
  main.label.fire('click');
  out.labelOpens = fp.isOpen;
  return out;
}

function pc() {
  const dom = makeDom();
  const form = dom.doc.createElement('div');
  form.className = 'pc-form';
  dom.doc.body.appendChild(form);
  const main = field(dom, form, '시공일', { id: 'c', class: 'form-control form-control-sm', value: '2026-12-03' }, 'c');
  const win = load(dom);
  const fp = win.ErpDateMulti.attach(main.input, {});
  main.input.value = '2026-12-20, 2026-12-21';   // 손으로 친 값
  return {
    allowInput: fp.config.allowInput, readonly: main.input.readOnly === true, view: !!main.input._erpDateView,
    src: main.input.classList.contains('erp-fp-src'), positionFn: typeof fp.config.position === 'function',
    sheet: fp.calendarContainer.classList.contains('erp-fp-sheet'), clearBtn: !!fp.calendarContainer.querySelector('.erp-fp-clear-btn'),
    done: !!fp.calendarContainer.querySelector('.erp-fp-done-btn'), yearReadonly: fp.currentYearElement.readOnly === true,
    ignoredShared: fp.config.ignoredFocusElements === SHARED_DEFAULT_IGNORED, typed: main.input.value,
    again: win.ErpDateMulti.attach(main.input) === fp,
  };
}

process.stdout.write(JSON.stringify({ phone: phone(), pc: pc() }));

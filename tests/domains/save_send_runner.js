// save-send.js 를 작은 가짜 화면에서 돌려 보낸 요청을 적는다(node 로 실행 — tests/domains/test_drawing_wizard_save_send.py).
// 입력(stdin JSON): {kind, sheets:[id], current:id, pending:[id], send, push,
//   sent:{id: 전달본 지문|null}(전달본 있는 시트), sigs:{id: 지금 지문}, pendingSigs:{id: 대기함 지문}, empty:[빈 시트 id],
//   queueFail:bool, hotfix:bool(생산·시공 단계), note:'전달 메모', warnings:[보내기 전 확인 글](있으면 확인 창 → ack)}
// 출력(stdout JSON): {calls:[{url, method, body}], toasts:[...]}
'use strict';
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));

function el(extra) {
  const handlers = {};
  const node = Object.assign({
    hidden: true, checked: false, disabled: false, textContent: '', type: '',
    classList: { toggle() {}, add() {}, remove() {} },
    addEventListener(name, fn) { (handlers[name] = handlers[name] || []).push(fn); },
    fire(name, ev) { (handlers[name] || []).forEach((fn) => fn(ev || { target: node, preventDefault() {}, stopPropagation() {} })); },
    getAttribute() { return null; },
    focus() {},
    closest() { return node; },
  }, extra || {});
  return node;
}

const parts = {
  '[data-savesend="send"]': el({ type: 'checkbox' }),
  '[data-savesend="push"]': el({ type: 'checkbox' }),
  '[data-savesend-row="push"]': el(),
  '[data-savesend-lock]': el(),
  '[data-savesend-go]': el(),
  '[data-savesend-cancel]': el(),
  '[data-savesend-remember]': el({ type: 'checkbox' }),
};
if (input.hotfix) {   // 생산·시공 단계 템플릿만 그리는 칸(설계서 2026-11-25 D2)
  parts['[data-savesend-fix]'] = el();
  parts['[data-savesend-note]'] = el({ value: input.note || '' });
  parts['[data-savesend-note-error]'] = el();
  parts['[data-savesend-changed]'] = el();
}
const pop = el({ querySelector: (sel) => parts[sel] || null });
const byId = {
  'dws-root': el({ getAttribute: (name) => (name === 'data-order-id' ? '77' : null) }),
  'dws-savesend': pop,
  'dws-savesend-head': el(),
  'drawing-wizard-config': el({ textContent: JSON.stringify({ save_send: { user_id: 1, can_transfer: true, hotfix_stage: !!input.hotfix, is_partner: false } }) }),
};

const calls = [];
const toasts = [];
const store = {};
global.document = { getElementById: (id) => byId[id] || null, addEventListener() {} };
global.window = global;
global.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; }, removeItem: (k) => { delete store[k]; } };
global.confirm = () => true;
const sheets = input.sheets.map((id) => ({ id, objects: (input.empty || []).indexOf(id) >= 0 ? [] : [{ id: 'o-' + id }] }));
global.FomsWizardCore = {
  canSave: () => true,
  hydrated: () => true,
  state: () => ({ sheets }),
  sheet: () => sheets.find((s) => s.id === input.current),
  save: () => Promise.resolve(true),
  saveAll: () => Promise.resolve({ ok: sheets.length, fail: [], total: sheets.length }),
  pushRoom: () => { calls.push({ url: 'pushRoom', method: 'CALL', body: null }); return Promise.resolve(true); },
  queueSheets: (ids) => {
    calls.push({ url: 'queueSheets', method: 'CALL', body: ids });
    return Promise.resolve(input.queueFail ? { ok: 0, fail: ids, total: ids.length } : { ok: ids.length, fail: [], total: ids.length });
  },
  refreshPending: () => {},
  toast: (msg) => { toasts.push(msg); },
};
if (input.hotfix) {
  global.FomsFixSend = {
    preview: () => Promise.resolve({ changed_line: '바뀐 도면: 도면 1 (고침)', warnings: input.warnings || [] }),
    setChanged: () => {},
    gate: (id, opts, text) => Promise.resolve(opts).then((o) => {
      calls.push({ url: 'gate', method: 'CALL', body: o });
      return { ok: true, ack: (input.warnings || []).length > 0 };
    }),
    post: (url, body) => { calls.push({ url, method: 'POST', body }); return Promise.resolve({ success: true }); },
  };
}
global.FomsSaveStatus = {
  sheetSig: (s) => ((input.sigs || {})[s.id] || ''),
  tagSig: (x) => (x ? 'v2:' + x : ''),
};
global.fetch = (url, opts) => {
  const method = (opts && opts.method) || 'GET';
  calls.push({ url, method, body: opts && opts.body ? JSON.parse(opts.body) : null });
  let data = { success: true, message: 'ok' };
  if (method === 'GET' && /\/drawing-wizard\/pending$/.test(url)) {
    const sent = input.sent || {};
    data = { success: true, data: {
      pending: input.pending.map((id) => ({ sheet_id: id, key: 'k-' + id, sig: (input.pendingSigs || {})[id] || undefined })),
      current: Object.keys(sent).map((id) => ({ sheet_id: id, sig: sent[id] })),
    } };
  }
  return Promise.resolve({ status: 200, json: () => Promise.resolve(data) });
};

eval(src);   // eslint-disable-line no-eval — 시험 전용: 실제 파일을 그대로 돌린다

window.FomsSaveSend.open(input.kind);
parts['[data-savesend="send"]'].checked = !!input.send;
parts['[data-savesend="push"]'].checked = !!input.push;
parts['[data-savesend="send"]'].fire('change');
parts['[data-savesend-go]'].fire('click');
setTimeout(() => {
  const errEl = parts['[data-savesend-note-error]'];
  process.stdout.write(JSON.stringify({ calls, toasts, noteError: errEl ? !errEl.hidden : null, open: !pop.hidden }));
}, 50);

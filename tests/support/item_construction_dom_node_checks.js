// 제품마다 시공 끝(2단계) 화면 JS — 작은 가짜 DOM 위에서 동작을 잰다(tests/domains/test_item_construction_screens.py 가 부른다).
// 1) erp-item-construction-done.js: 셸 조각 교체(foms:main-content-swapped) 뒤 새 #erp-items(주문 B)에 글이 붙고
//    옛 지켜보기는 끊긴다 · 두 번 실려도 클릭 위임은 하나.
// 2) foms-visit-items.js: 체크 0개 = 단추 끔 · 못 읽음 + 나눠 시공 줄 = [다시 읽기] + 끔 · 몸에 done_item_uids · visit_date.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..', '..');
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8');

// ── 가짜 DOM: 태그 · .class · [attr] · [attr="v"] 묶음 선택자만(조합자 없음) ──
function parseSel(sel) {
  const m = { tag: null, classes: [], attrs: [] };
  const re = /^([a-z]+)|\.([\w-]+)|\[([\w-]+)(?:="([^"]*)")?\]/g;
  let x;
  while ((x = re.exec(sel))) {
    if (x[1]) m.tag = x[1];
    else if (x[2]) m.classes.push(x[2]);
    else m.attrs.push([x[3], x[4]]);
  }
  return m;
}
function matches(node, sel) {
  if (sel.startsWith('#')) {
    const [id, rest] = [sel.slice(1).split('[')[0], sel.includes('[') ? sel.slice(sel.indexOf('[')) : ''];
    return node.attrs.id === id && (!rest || matches(node, rest));
  }
  const m = parseSel(sel);
  if (m.tag && node.tag !== m.tag) return false;
  const cls = String(node.className || '').split(/\s+/);
  if (m.classes.some((c) => !cls.includes(c))) return false;
  return m.attrs.every(([k, v]) => k in node.attrs && (v === undefined || node.attrs[k] === v));
}
function walk(node, out) {
  node.children.forEach((c) => { out.push(c); walk(c, out); });
  return out;
}
function el(tag) {
  const node = {
    tag, attrs: {}, children: [], className: '', parentNode: null, listeners: {},
    textContent: '', checked: false, value: '', type: '', disabled: false,
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    hasAttribute(k) { return k in this.attrs; },
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
    insertBefore(c, ref) {
      c.parentNode = this;
      const i = ref ? this.children.indexOf(ref) : -1;
      if (i < 0) this.children.push(c); else this.children.splice(i, 0, c);
      return c;
    },
    removeChild(c) { this.children.splice(this.children.indexOf(c), 1); c.parentNode = null; return c; },
    get firstElementChild() { return this.children[0] || null; },
    get nextSibling() {
      const p = this.parentNode;
      return p ? (p.children[p.children.indexOf(this) + 1] || null) : null;
    },
    matches(sel) { return matches(this, sel); },
    closest(sel) { let n = this; while (n) { if (n.matches && n.matches(sel)) return n; n = n.parentNode; } return null; },
    querySelector(sel) { return walk(this, []).find((n) => matches(n, sel)) || null; },
    querySelectorAll(sel) { return walk(this, []).filter((n) => matches(n, sel)); },
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
  };
  return node;
}

function makeContext() {
  const body = el('body');
  const docListeners = {};
  const observers = [];
  class FakeObserver {
    constructor(cb) { this.cb = cb; this.disconnected = false; observers.push(this); }
    observe(target) { this.target = target; }
    disconnect() { this.disconnected = true; }
  }
  const document = {
    readyState: 'complete', body,
    createElement: el,
    querySelector: (sel) => body.querySelector(sel),
    addEventListener(t, f) { (docListeners[t] = docListeners[t] || []).push(f); },
  };
  const ctx = { document, MutationObserver: FakeObserver, console, Promise, setTimeout, JSON, String, Array, Number };
  ctx.window = ctx;
  return { ctx: vm.createContext(ctx), body, docListeners, observers };
}

function orderHost(orderId, uid, canUndo) {
  const host = el('div');
  host.setAttribute('id', 'erp-items');
  host.setAttribute('data-item-construction-done', JSON.stringify({
    order_id: orderId, can_undo: canUndo, records: [{ uid, name: '부엌가구', label: '11/5 시공 끝' }],
  }));
  const row = el('div');
  row.className = 'border rounded p-2 mb-2 erp-item-row';
  row.setAttribute('data-item-uid', uid);
  row.appendChild(el('div'));  // 머리 줄
  row.appendChild(el('div'));  // 칸들
  host.appendChild(row);
  return { host, row };
}

// ── 1) 조각 교체 ──
(function swapRestartsOnNewHost() {
  const { ctx, body, docListeners, observers } = makeContext();
  const a = orderHost(11, 'uid-a', true);
  body.appendChild(a.host);
  const src = read('static/js/orders/erp-item-construction-done.js');
  vm.runInContext(src, ctx);
  assert.ok(a.row.querySelector('.erp-item-done-line'), 'A 줄에 글이 붙는다');
  assert.ok(a.row.querySelector('[data-erp-item-done-undo]'), 'A 는 되돌리기 단추가 있다');
  assert.strictEqual(observers.length, 1);

  body.removeChild(a.host);  // 셸이 주문 B 조각으로 바꿈
  const b = orderHost(22, 'uid-b', false);
  body.appendChild(b.host);
  vm.runInContext(src, ctx);  // 로더가 같은 src 를 다시 돌려도(돌리지 않는 게 보통) 위임은 하나
  assert.strictEqual((docListeners.click || []).length, 1, '클릭 위임은 한 번만');
  (docListeners['foms:main-content-swapped'] || []).forEach((f) => f());
  assert.ok(b.row.querySelector('.erp-item-done-line'), '교체 뒤 B 줄에 글이 붙는다');
  assert.ok(!b.row.querySelector('[data-erp-item-done-undo]'), 'B 는 권한 없음 — 단추 없음');
  assert.ok(observers.slice(0, -1).every((o) => o.disconnected), '옛 지켜보기는 끊는다');
  assert.strictEqual(observers[observers.length - 1].target, b.host);
  assert.ok(/REASON_MAX = 200;/.test(src), '되돌리기 사유 200자');
})();

// ── 2) 완료 창 체크 목록 ──
async function visitItemsChecks() {
  const { ctx, body } = makeContext();
  let reply = { success: true, data: { split: true, items: [
    { ref: 'uid-a', name: '부엌가구', last_date: '2026-11-05', last_label: '11/5', precheck: true },
    { ref: 'uid-b', name: '화장대', last_date: '2026-11-17', last_label: '11/17', precheck: false },
  ] } };
  ctx.fetch = async () => ({ json: async () => { if (reply === 'boom') throw new Error('x'); return reply; } });
  vm.runInContext(read('static/js/construction/foms-visit-items.js'), ctx);
  const api = ctx.window.FomsVisitItems;
  const row = el('tr');
  row.setAttribute('data-order-id', '7');
  row.setAttribute('data-visit-date', '2026-11-05');
  body.appendChild(row);
  const host = el('div');
  const anchor = el('p');
  host.appendChild(anchor);
  body.appendChild(host);
  let changes = 0;
  await api.mount(host, () => anchor, 7, () => true, () => { changes += 1; });
  assert.ok(changes >= 1);
  assert.strictEqual(api.buttonLabel(host, '시공 완료'), '오늘 시공 끝 — 남은 제품 1개');
  assert.ok(api.leavesRemaining(host) && !api.blocked(host));
  const body1 = api.extendBody(host, 7, { completion_note: '' });
  assert.deepStrictEqual(JSON.parse(JSON.stringify(body1)),
    { completion_note: '', done_item_uids: ['uid-a'], visit_date: '2026-11-05' });
  host.querySelectorAll('input[data-foms-visit-item]').forEach((b) => { b.checked = false; });
  assert.ok(api.blocked(host), '하나도 안 고르면 단추 끔');
  host.querySelectorAll('input[data-foms-visit-item]').forEach((b) => { b.checked = true; });
  assert.strictEqual(api.buttonLabel(host, '시공 완료'), '시공 완료');
  assert.ok(!api.leavesRemaining(host));

  reply = 'boom';  // 나눠 시공 줄인데 못 읽음 → [다시 읽기] + 끔
  await api.mount(host, () => anchor, 7, () => true, () => {});
  assert.ok(host.querySelector('[data-foms-visit-items-failed]') && api.blocked(host));
  assert.strictEqual(api.selected(host), null);
  reply = { success: true, data: { split: true, items: [{ ref: 'uid-b', name: '화장대', precheck: true }] } };
  const retry = host.querySelector('.foms-visit-items__retry');
  retry.listeners.click[0]({ preventDefault() {} });
  await new Promise((r) => setTimeout(r, 0));
  assert.ok(!host.querySelector('[data-foms-visit-items-failed]') && !api.blocked(host), '다시 읽으면 목록');

  reply = 'boom';  // 나눠 시공인지 모르는 줄(data-visit-date 없음)은 못 읽어도 그대로
  const plain = el('div');
  body.appendChild(plain);
  await api.mount(plain, () => null, 8, () => true, () => {});
  assert.strictEqual(plain.querySelector('[data-foms-visit-items]'), null);
  assert.ok(!api.blocked(plain));
  const body2 = api.extendBody(plain, 8, { completion_note: 'x' });
  assert.deepStrictEqual(JSON.parse(JSON.stringify(body2)), { completion_note: 'x' }, '나눠 시공 아님 — 몸 그대로');

  reply = { success: true, data: { split: false, items: [] } };  // 나눠 시공 아님
  await api.mount(plain, () => null, 7, () => true, () => {});
  assert.strictEqual(plain.querySelector('[data-foms-visit-items]'), null);
}

visitItemsChecks().then(() => { console.log('ITEM_DONE_DOM_OK'); }, (err) => { console.error(err); process.exit(1); });

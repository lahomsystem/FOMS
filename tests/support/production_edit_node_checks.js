// PC [고치기] 켠 시각(foms-production-edit.js) — 위 탭을 바꿔(셸 조각 교체) 새 단추가 온 뒤 첫 누름이 앞날 값을 심던 것(2026-11-22).
// tests/domains/test_production_pc_viewer.py 가 부른다. 가짜 시계(Date.now)와 단추 둘(처음 화면 · 교체로 온 화면)만 쓴다.
// 1) 처음 화면: 서버 시각 1000 · 열고 5초 뒤 누름 → 1005.
// 2) 30초 뒤 셸 교체로 새 단추(서버 시각 1030)가 오고 2초 뒤 누름 → 1032(옛 코드는 문서를 연 때부터 세어 1062 = 앞날).
// 3) 교체 신호 없이 끼워진 단추(적어 둔 때 없음) → 서버 시각 그대로(앞날이 되지 않는다).
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..', '..');
let clock = 1000 * 1000; // ms
const docListeners = {};
let buttons = [];
let cookie = '';
function button(now) {
  return {
    attrs: { 'data-foms-prod-edit': 'on', 'data-foms-prod-edit-now': String(now) }, disabled: false,
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    closest(sel) { return sel === '[data-foms-prod-edit]' ? this : null; },
  };
}
const FakeDate = { now: () => clock };
const ctx = {
  console, WeakMap, Math, parseInt, isNaN, String, Array,
  Date: FakeDate,
  location: { protocol: 'http:', reload() {} },
  document: {
    querySelectorAll: () => buttons.slice(),
    addEventListener(t, f) { (docListeners[t] = docListeners[t] || []).push(f); },
    set cookie(v) { cookie = v; },
    get cookie() { return cookie; },
  },
};
ctx.window = ctx;
vm.createContext(ctx);
const fire = (type, target) => (docListeners[type] || []).forEach((f) => f({ type, target, preventDefault() {} }));
const issued = () => Number((cookie.match(/^foms_prod_edit=(\d+)/) || [])[1]);

buttons = [button(1000)];
vm.runInContext(fs.readFileSync(path.join(root, 'static/js/production/foms-production-edit.js'), 'utf8'), ctx);
clock += 5000;
fire('click', buttons[0]);
assert.strictEqual(issued(), 1005, '처음 화면 = 서버 시각 + 흐른 시간');

clock += 25000; // 연 지 30초
buttons = [button(1030)]; // 셸 교체로 온 새 단추(그 조각을 그린 서버 시각)
fire('foms:erp-shell-fragment-swapped');
clock += 2000;
fire('click', buttons[0]);
assert.strictEqual(issued(), 1032, `교체로 온 단추는 그 단추가 온 때부터 센다(옛 코드 1062): ${cookie}`);

const stray = button(1100); // 교체 신호 없이 끼워진 단추
clock += 9000;
fire('click', stray);
assert.strictEqual(issued(), 1100, '적어 둔 때가 없으면 흐른 시간 0');
// 다시 실행돼도(셸 교체로 스크립트가 또 돈다) 리스너는 한 번
vm.runInContext(fs.readFileSync(path.join(root, 'static/js/production/foms-production-edit.js'), 'utf8'), ctx);
assert.strictEqual(docListeners.click.length, 1);
console.log('OK');

// 도면 작업실 요청사항 칸 공장 요청 [반영 완료] · [요청 반려] — 서버가 그린 진짜 칸(argv[2]) 위에서 workbench-factory-request.js 를 Node 로
// 돌린다(D4). tests/domains/test_drawing_request_js.py 가 부른다. want = argv[3] {posts: [서버 답…]}. 결과는 stdout JSON.
// <dialog> 는 가짜(showModal · close). 가짜 DOM = production_fake_dom.js.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { fakeDom } = require('./production_fake_dom.js');

const root = path.resolve(__dirname, '..', '..');
const html = fs.readFileSync(process.argv[2], 'utf8');
const want = JSON.parse(process.argv[3]);
const D = fakeDom();
const body = D.parse(html);
const calls = [];
const posts = (want.posts || []).slice();
let reloads = 0;
function makeEl(tag) {
  const node = D.makeEl(tag);
  if (tag === 'dialog') {
    node.showModal = () => { node.setAttribute('open', ''); };
    node.close = () => { node.removeAttribute('open'); D.dispatch(node, 'close'); };
    node.remove = () => { if (node.parentNode) { node.parentNode.removeChild(node); } };
  }
  return node;
}
const document = {
  body,
  querySelector: (s) => body.querySelector(s), querySelectorAll: (s) => body.querySelectorAll(s),
  createElement: (t) => makeEl(t.toLowerCase()),
  addEventListener: (t, f) => { (D.docListeners[t] = D.docListeners[t] || []).push(f); },
};
const ctx = {
  console, JSON, Promise, Object, Array, String, Number, Boolean, Error, setTimeout, document,
  location: { reload: () => { reloads += 1; } },
  fetch: (url, opts) => {
    calls.push({ url, method: opts.method, body: JSON.parse(opts.body) });
    const next = posts.shift();
    if (next === 'offline') { return Promise.reject(new TypeError('Failed to fetch')); }
    return Promise.resolve({ json: () => Promise.resolve(next || { success: true, data: {} }) });
  },
};
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(root, 'static/js/drawing/workbench-factory-request.js'), 'utf8'), ctx);

const click = (el) => D.dispatch(el, 'click');
const tick = () => new Promise((r) => setTimeout(r, 0));
const dialog = () => body.querySelector('dialog');
const out = {};

(async () => {
  click(body.querySelector('[data-dfr-act="check"]'));          // [반영 완료] — 서버 거절
  await tick(); await tick();
  const err = body.querySelector('[data-dfr-error]');
  out.checkError = err.hidden ? '' : err.textContent;
  click(body.querySelector('[data-dfr-act="reject"]'));
  const d = dialog();
  out.dialogOpen = !!d && d.hasAttribute('open');
  out.dialogText = d.querySelector('.dfx-dialog__head').textContent + '|' + d.querySelector('.dwp-dialog__text').textContent;
  out.buttons = d.querySelector('.dfx-dialog__foot').children.map((b) => b.textContent);
  const go = d.querySelector('.dwp-btn--stop');
  d.querySelector('textarea').value = '  ';
  click(go);
  await tick();
  out.emptyNote = d.querySelector('[role="alert"]').textContent;
  d.querySelector('textarea').value = '실';
  D.dispatch(d.querySelector('textarea'), 'input');            // 적기 시작하면 빨간 글이 바로 지워진다
  out.afterTyping = d.querySelector('[role="alert"]').hidden ? '' : d.querySelector('[role="alert"]').textContent;
  out.callsAfterEmpty = calls.filter((c) => /\/reject$/.test(c.url)).length;
  d.querySelector('textarea').value = '실측과 같아요';
  click(go);                                                    // 서버 거절 → 창 안 글
  await tick(); await tick();
  out.rejectError = d.querySelector('[role="alert"]').textContent;
  out.reenabled = !go.disabled;
  click(go);                                                    // 다시 — 됨 → 다시 읽기
  await tick(); await tick();
  out.reloadsAfterReject = reloads;
  click(body.querySelector('[data-dfr-act="check"]'));          // [반영 완료] 다시 — 됨 → 다시 읽기
  await tick(); await tick();
  out.reloads = reloads;
  out.calls = calls;
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });

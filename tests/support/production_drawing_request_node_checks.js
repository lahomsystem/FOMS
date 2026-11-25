// 생산 도면 판 [도면 수정 요청] 창 — 서버가 그린 진짜 판(argv[2]) 위에서 foms-production-drawing-request.js 를 Node 로 돌린다(D4).
// tests/domains/test_drawing_request_js.py 가 부른다. want = argv[3] {oid, card_no, posts: [서버 답…], uploads: [서버 답…]}.
// 고르기 · 사유 · 사진 · 보내기 · 같은 몸 = 같은 열쇠 · 보낸 뒤 카드 '도면 고치는 중' · 실패 글을 차례로 본다. 결과는 stdout JSON.
// 가짜 DOM = production_fake_dom.js. 카드 다시 그리기(FomsPartsCards.render)는 부른 카드만 적는 가짜.
'use strict';
const assert = require('assert');
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
const rendered = [];
const posts = (want.posts || []).slice();
const uploads = (want.uploads || []).slice();
let uuid = 0;
const document = {
  body,
  querySelector: (s) => body.querySelector(s), querySelectorAll: (s) => body.querySelectorAll(s),
  createElement: (t) => D.makeEl(t.toLowerCase()),
  addEventListener() {}, contains: (n) => body.contains(n),
};
function FormData() { this.parts = []; }
FormData.prototype.append = function (k, v, name) { this.parts.push([k, name || '']); };
const ctx = {
  console, JSON, Promise, Date, Math, Object, Array, String, Number, Boolean, Error, setTimeout, document, FormData,
  crypto: { randomUUID: () => 'key-' + (++uuid) },
  URL: { createObjectURL: (f) => 'blob:' + f.name },
  fetch: (url, opts) => {
    const isPhoto = /\/photo$/.test(url);
    calls.push({ url, method: opts.method, headers: opts.headers || {}, body: isPhoto ? opts.body.parts : JSON.parse(opts.body) });
    const next = isPhoto ? uploads.shift() : posts.shift();
    if (next === 'offline') { return Promise.reject(new TypeError('Failed to fetch')); }
    if (next === '413') { return Promise.resolve({ status: 413, json: () => Promise.reject(new SyntaxError('not json')) }); }
    return Promise.resolve({ status: 200, json: () => Promise.resolve(next || { success: true, data: {} }) });
  },
  FomsPartsCards: { render: (card) => rendered.push(card.getAttribute('data-key')) },
};
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(root, 'static/js/production/foms-production-drawing-request.js'), 'utf8'), ctx);

const modal = body.querySelector('[data-pp-rq]');
const homeRoot = body.querySelector('[data-foms-prod-home]');
const q = (s) => modal.querySelector(s);
const cards = () => body.querySelectorAll('[data-pp-card][data-order-id="' + want.oid + '"]');
const card = cards().find((c) => c.getAttribute('data-no') === String(want.card_no));
const click = (el) => D.dispatch(el, 'click');
const tick = () => new Promise((r) => setTimeout(r, 0));
const picks = () => q('[data-pp-rq-picks]').children.map((b) => [b.textContent, b.getAttribute('aria-pressed')]);
const err = () => (q('[data-pp-rq-err]').hidden ? '' : q('[data-pp-rq-err]').textContent);
const send = () => click(q('[data-pp-rq-send]'));
const out = {};

(async () => {
  assert.ok(modal.hidden, '창은 처음에 닫혀 있다');
  click(card.querySelector('[data-pp-req]'));
  out.opened = !modal.hidden;
  out.who = q('[data-pp-rq-who]').textContent;
  out.picks = picks();
  q('[data-pp-rq-note]').value = '   ';
  send();
  out.noNote = err();
  click(q('[data-pp-rq-picks]').children.find((b) => b.getAttribute('aria-pressed') === 'true'));
  q('[data-pp-rq-note]').value = '측판 길이가 실측과 달라요';
  send();
  out.noPick = err();
  out.callsBeforePick = calls.length;
  const first = q('[data-pp-rq-picks]').children[0];
  click(first);
  window_onFiles([{ name: 'a.jpg' }, { name: 'b.jpg' }, { name: 'c.jpg' }, { name: 'd.jpg' }]);
  out.tooMany = err();
  window_onFiles([{ name: 'huge.jpg' }]);   // 몸 상한 413(success 칸 없는 답)
  await tick(); await tick(); await tick();
  out.tooBig = err();
  out.thumbsAfterBig = q('[data-pp-rq-thumbs]').children.length;
  window_onFiles([{ name: 'a.jpg' }, { name: 'b.jpg' }]);
  out.sendDisabledWhileUploading = q('[data-pp-rq-send]').disabled;
  await tick(); await tick(); await tick();
  out.thumbs = q('[data-pp-rq-thumbs]').children.length;
  out.uploadCalls = calls.filter((c) => /\/photo$/.test(c.url)).map((c) => c.url).slice(1);
  send();                                   // 첫 보냄 — 서버 403
  await tick(); await tick();
  out.refused = err();
  out.stillOpen = !modal.hidden;
  send();                                   // 같은 몸 = 같은 열쇠
  await tick(); await tick();
  out.offline = err();
  q('[data-pp-rq-note]').value = '측판 길이가 실측과 달라요(고침)';
  send();                                   // 몸이 바뀜 = 새 열쇠 → 성공
  await tick(); await tick();
  const sendCalls = calls.filter((c) => /drawing-request$/.test(c.url));
  out.keys = sendCalls.map((c) => c.headers['Idempotency-Key']);
  out.lastBody = sendCalls[sendCalls.length - 1].body;
  out.closed = modal.hidden;
  out.status = homeRoot.querySelector('[data-foms-home-status]').textContent;
  out.blocked = cards().filter((c) => c.getAttribute('data-pp-block') === 'revise').map((c) => c.getAttribute('data-no'));
  out.blockWhy = cards().map((c) => c.getAttribute('data-pp-block-why')).filter(Boolean);
  out.hiddenReq = cards().filter((c) => c.querySelector('[data-pp-req]') && c.querySelector('[data-pp-req]').hidden).map((c) => c.getAttribute('data-no'));
  out.rendered = rendered;
  out.optsLeft = cards().map((c) => { const b = c.querySelector('[data-pp-req]'); return b ? [c.getAttribute('data-no'), JSON.parse(b.getAttribute('data-pp-req-opts')).map((o) => o.no)] : null; }).filter(Boolean);
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });

function window_onFiles(files) { ctx.FomsPartRequest.onFiles(files); }

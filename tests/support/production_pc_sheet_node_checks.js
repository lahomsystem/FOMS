// PC 공정 칸 → 도면 목록 창 — 서버가 그린 진짜 PC 첫 화면(argv[2]) 위에서 sheet-parts.js · pc-sheet.js · pc-sheet-write.js 를 Node 로
// 돌린다(설계서 2026-11-25 multi-holder §8-2 24 · 41 ~ 45 · 판결 2). tests/domains/test_production_multi_holder_screens.py 가 부른다.
// want = argv[3] {oid, sheets: {파트: 서버 part-sheet 자료}, history: [서버 바뀐 기록], posts: [POST 마다 서버 답], key_need, key_done,
//                 key_mine, log_only: [기록](있으면 그 목록만 renderLog 로 그려 돌려준다)}. 결과는 stdout JSON.
// GET 은 진짜 서버 응답(파이썬이 받아 넘긴 것)을 그대로 돌려주고, POST 는 몸만 적고 want.posts 를 차례로 돌려준다
// (파이썬이 그 몸을 진짜 서버에 다시 보내 결과를 본다).
// 가짜 DOM = production_fake_dom.js(태그 · .class · #id · [attr] 묶음 + 쉼표 목록만 — 조합자는 첫 마디만 본다).
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { fakeDom } = require('./production_fake_dom.js');

const root = path.resolve(__dirname, '..', '..');
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8');
const html = fs.readFileSync(process.argv[2], 'utf8');
const want = JSON.parse(process.argv[3]);
const D = fakeDom();
const body = D.parse(html);
const posts = [];
const gets = [];
const replies = (want.posts || []).slice(); // POST 마다 차례로 돌려줄 서버 답(없으면 빈 성공)
function textNode(t) { return { tag: null, children: [], parentNode: null, textContent: String(t) }; }
// 만든 요소의 textContent = 글 마디 하나(진짜 DOM 처럼 — 뒤에 자식을 더해도 글이 남는다: 상태 칸 글 + <small>)
function made(node) {
  Object.defineProperty(node, 'textContent', {
    get() { return this.children.map((c) => c.textContent).join(''); },
    set(v) { this.children = []; if (String(v)) { this.appendChild(textNode(v)); } },
  });
  return node;
}
const document = {
  body,
  querySelector: (s) => body.querySelector(s), querySelectorAll: (s) => body.querySelectorAll(s),
  createElement: (t) => made(D.makeEl(t.toLowerCase())),
  createTextNode: (t) => textNode(t),
  addEventListener: (t, f) => { (D.docListeners[t] = D.docListeners[t] || []).push(f); },
  contains: (n) => body.contains(n),
  dispatchEvent: () => true,
};
function reply(data) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
}
const ctx = {
  console, JSON, Promise, Object, Array, String, Number, Boolean, Error, Date, Math, RegExp, setTimeout, clearTimeout, document,
  CustomEvent: function CustomEvent(t, o) { this.type = t; this.detail = (o || {}).detail; },
  location: { reload() {}, href: 'http://127.0.0.1/erp/production/home' },
  fetch: (url, opts) => {
    const method = (opts && opts.method) || 'GET';
    if (method === 'POST') {
      posts.push({ url, body: JSON.parse(opts.body) });
      return reply(replies.length ? replies.shift() : { success: true, data: {} });
    }
    gets.push(url);
    const u = new URL(url, 'http://127.0.0.1');
    if (u.pathname === '/api/production/part-history') { return reply({ success: true, data: { items: want.history || [] } }); }
    const part = u.searchParams.get('part');
    return reply({ success: true, data: want.sheets[part] });
  },
};
ctx.window = ctx;
vm.createContext(ctx);
['static/js/production/foms-production-sheet-parts.js', 'static/js/production/foms-production-pc-sheet.js',
  'static/js/production/foms-production-pc-sheet-write.js'].forEach((rel) => vm.runInContext(read(rel), ctx, { filename: rel }));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const click = (el) => D.dispatch(el, 'click');
const box = body.querySelector('[data-foms-pc-sheet-box]');
const q = (sel) => box.querySelector(sel);
const out = {};

function rowOf(oid) { return body.querySelectorAll('[data-foms-home-dayrow]').find((n) => n.getAttribute('data-foms-home-dayrow') === String(oid)); }
function cell(oid, part) { return rowOf(oid).querySelector(`[data-foms-pc-sheet="${part}"]`); }
function rows() {
  return q('[data-foms-pc-sheet-rows]').children.map((li) => {
    const meta = li.querySelector('.fpc-sheet__meta');
    const st = li.querySelector('.fpc-sheet__st');
    const small = st.querySelector('small');
    const btn = li.querySelector('[data-foms-pc-sheet-act]');
    return { key: li.getAttribute('data-key'), lines: meta ? meta.children.map((n) => n.textContent) : [],
      word: st.children.filter((c) => !c.tag).map((c) => c.textContent).join(''),
      note: small ? small.textContent : null, button: btn ? btn.textContent : null, act: btn ? btn.getAttribute('data-foms-pc-sheet-act') : null };
  });
}
function tools() { return q('[data-foms-pc-sheet-tools]').children.map((b) => b.textContent); }
function rowButton(key) {
  return q('[data-foms-pc-sheet-rows]').children.find((li) => li.getAttribute('data-key') === key).querySelector('[data-foms-pc-sheet-act]');
}
function close() { click(box.querySelector('.fpc-sheet__x')); }

(async () => {
  if (want.log_only) { // 바뀐 기록 낱말만 — 작업 시트 · PC 창이 같이 쓰는 renderLog
    const list = document.createElement('ul');
    ctx.window.FomsSheetParts.renderLog(list, want.log_only, want.keys || []);
    out.log = list.children.map((li) => li.textContent);
    process.stdout.write(JSON.stringify(out));
    return;
  }
  // 1) 재단 칸을 누르면 창 — 줄 글은 서버가 준 사람마다 조각 그대로, 단추는 [완료 처리] · [완료 취소]
  click(cell(want.oid, 'cut'));
  await sleep(30);
  out.title = q('[data-foms-pc-sheet-title]').textContent;
  out.rows = rows();
  out.tools = tools();
  out.log = q('[data-foms-pc-sheet-log]').children.map((li) => li.textContent);
  // 2) 1/2 완료 장 [완료 처리] = POST 한 번(action check) — 옛 맡기 → 완료 두 요청 없음
  const before = posts.length;
  click(rowButton(want.key_need));
  await sleep(30);
  out.checkPosts = posts.slice(before);
  // 3) 완료한 장 [완료 취소] = undo 한 번(되돌린 뒤 작업하는 사람이 나 하나가 아니면 시작 취소는 안 보냄)
  const mid = posts.length;
  click(rowButton(want.key_done));
  await sleep(30);
  out.undoPosts = posts.slice(mid);
  // 4) 내가 빈 장을 [완료 처리]한 장(undo_releases) [완료 취소] = undo → 되돌린 뒤 작업하는 사람이 나 하나면 시작 취소까지
  const mine = posts.length;
  click(rowButton(want.key_mine));
  await sleep(30);
  out.minePosts = posts.slice(mine);
  close();
  await sleep(5);
  out.closed = box.hidden;
  // 5) 아무도 안 시작한 파트 = 창 머리 [모두 완료 처리] → 작업 시트와 같은 확인 창 글 그대로
  click(cell(want.oid, 'assemble'));
  await sleep(30);
  out.allTools = tools();
  const all = q('[data-foms-pc-sheet-tools]').children[0];
  click(all);
  await sleep(30);
  const confirm = body.querySelector('[data-foms-sheet-confirm]');
  out.confirmTitle = confirm.querySelector('[data-foms-sheet-confirm-title]').textContent;
  out.confirmYes = confirm.querySelector('[data-foms-sheet-confirm-yes]').textContent.trim();
  out.confirmOpen = !confirm.hidden;
  await sleep(450); // 연 뒤 0.4초 안 누름은 버린다(sheet-parts OPEN_GUARD_MS)
  confirm.querySelector('[data-foms-sheet-confirm-no].foms-btn').click();
  await sleep(5);
  out.confirmClosed = confirm.hidden;
  out.postsAfterCancel = posts.length;
  close();
  await sleep(5);
  // 6) 손으로 통째 체크한 파트 = 창 머리 [모두 완료 취소]
  click(cell(want.oid, 'edge'));
  await sleep(30);
  out.handTools = tools();
  out.handRows = rows();
  out.gets = gets.length;
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });

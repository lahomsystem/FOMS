// drawing-fix-send.js 를 작은 가짜 화면에서 실제로 돌린다(node — tests/domains/test_drawing_fix_send_js.py).
// 입력(stdin JSON): {action: 'gate'|'post', plan: R1 plan | null(못 받음), confirm: bool, answers: [창 답 true/false…],
//   posts: [서버 답…], body: 보낼 본문}
// 출력(stdout JSON): {result, calls:[{method, url, body}], dialogs:[창 글], confirms:[확인 글]}
'use strict';
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));

const calls = [];
const dialogs = [];
const confirms = [];
const answers = (input.answers || []).slice();
const posts = (input.posts || []).slice();

function el(tag) {
  const node = {
    tagName: tag, className: '', textContent: '', id: '', type: '', children: [], listeners: {}, attrs: {},
    appendChild(child) { node.children.push(child); return child; },
    setAttribute(k, v) { node.attrs[k] = v; },
    addEventListener(name, fn) { (node.listeners[name] = node.listeners[name] || []).push(fn); },
    fire(name) { (node.listeners[name] || []).forEach((fn) => fn({ target: node })); },
    focus() {},
    remove() {},
    text() { return [node.textContent].concat(node.children.map((c) => c.text())).filter(Boolean).join('\n'); },
  };
  if (tag === 'dialog') {
    node.showModal = () => {
      dialogs.push(node.text());
      const yes = answers.length ? answers.shift() : true;
      const foot = node.children[2];
      setTimeout(() => foot.children[yes ? 1 : 0].fire('click'), 0);
    };
    node.close = () => node.fire('close');
  }
  return node;
}

global.window = global;
global.document = { createElement: el, body: el('body') };
global.confirm = (text) => { confirms.push(text); return input.confirm !== false; };
global.fetch = (url, opts) => {
  const method = (opts && opts.method) || 'GET';
  calls.push({ method, url, body: opts && opts.body ? JSON.parse(opts.body) : null });
  if (method === 'GET') {
    if (input.plan === null) { return Promise.reject(new TypeError('Failed to fetch')); }
    return Promise.resolve({ json: () => Promise.resolve({ success: true, data: { plan: input.plan } }) });
  }
  const data = posts.length ? posts.shift() : { success: true };
  return Promise.resolve({ status: 200, json: () => Promise.resolve(data) });
};

eval(src);   // eslint-disable-line no-eval — 시험 전용: 실제 파일을 그대로 돌린다

const F = window.FomsFixSend;
const run = input.action === 'gate'
  ? F.gate(77, { sheets: ['s-1'] }, (plan) => [plan.changed_line, F.HOTFIX_TEXT].filter(Boolean).join('\n\n'))
  : F.post('/api/orders/77/transfer-drawing', input.body || {});
run.then((result) => {
  process.stdout.write(JSON.stringify({ result, calls, dialogs, confirms }));
});

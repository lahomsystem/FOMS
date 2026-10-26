"""도면 마법사 알림(토스트) 쌓기 계약 — 2026-10-25 실화면 QA(보통) · 리드 메모.

- 알림이 4초 이상 남게 되자 연달아 뜬 알림이 한꺼번에 쌓였다: Enter 로 5장 확인 → 같은 '확인했어요' 5개,
  [일괄 저장] 5장 → '1/5 처리 중'…'5/5' 와 마무리까지 6개.
  → 같은 글은 '(5)'로 합치고, key 가 같은 진행 알림은 하나를 고쳐 쓰고, 한 번에 3개까지만.
- 규칙 창(<dialog> showModal)이 열린 채 뜬 알림이 흐린 바탕 밑에 깔렸다 → 모달 창 안 알림 자리에 띄운다.

동작은 wizard-toast.js 와 wizard.js 의 실제 toast()·errorToast() 본문을 node 로 돌려 본다(가짜 DOM).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TPL = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
JS = (ROOT / "static/js/drawing/wizard.js").read_text(encoding="utf-8")
STACK = ROOT / "static/js/drawing/wizard-toast.js"

_FN_DECL = chr(10) + "  function "


def _fn_slice(src: str, decl: str) -> str:
    start = src.index(decl)
    nxt = src.find(_FN_DECL, start + len(decl))
    return src[start:] if nxt < 0 else src[start:nxt]


def _node():
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


# ---- 문자열 계약 ---------------------------------------------------------------

def test_stack_script_loads_before_wizard():
    tag = re.search(r'<script src="[^"]*wizard-toast\.js[^"]*"[^>]*>', TPL)
    assert tag and "?v=" in tag.group(0) and " defer" in tag.group(0)
    assert TPL.index("js/drawing/wizard-toast.js") < TPL.index("js/drawing/wizard.js')")


def test_stack_js_syntax_and_size():
    proc = subprocess.run([_node(), "--check", str(STACK)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert len(STACK.read_text(encoding="utf-8").splitlines()) < 300   # 새 JS 300줄 래칫


def test_wizard_toast_uses_stack():
    toast = _fn_slice(JS, "function toast(msg, opts) {")
    # 고쳐 쓰기(같은 글·같은 key)를 먼저 보고, 없을 때만 새로 만든다 — 오류 알림도 같은 길
    assert toast.index("T.reuse(msg, opts, ms)") < toast.index("if (opts.error) { return errorToast(msg, opts.retry); }")
    assert "T.add(els.toastHost, t, msg, opts, ms)" in toast
    err = _fn_slice(JS, "function errorToast(msg, retry) {")
    assert "T.add(els.toastHost, t, msg, { error: true, retry: retry }, 0)" in err
    assert "T.remove(t)" in err   # × 로 닫으면 쌓기 목록에서도 뺀다


def test_batch_progress_rewrites_one_toast():
    each = _fn_slice(JS, "function eachSheetToBlob(handler, label) {")
    assert "' 처리 중…', { key: 'sheet-batch' })" in each
    assert "window.FomsWizardToast.drop('sheet-batch')" in each   # 마무리 알림 전에 진행 알림을 닫는다


# ---- 동작(node) ----------------------------------------------------------------

RUNNER = r"""
const fs = require('fs');
const [stackPath, fnPath] = process.argv.slice(1);

// --- 가짜 시계 ---
let now = 0, tid = 0;
const timers = new Map();
global.setTimeout = (fn, ms) => { tid += 1; timers.set(tid, { at: now + (ms || 0), fn }); return tid; };
global.clearTimeout = (id) => { timers.delete(id); };
function tick(ms) {
  const end = now + ms;
  for (;;) {
    let best = null;
    timers.forEach((t, id) => { if (t.at <= end && (!best || t.at < best[1].at)) { best = [id, t]; } });
    if (!best) { break; }
    timers.delete(best[0]); now = best[1].at; best[1].fn();
  }
  now = end;
}

// --- 가짜 DOM ---
function el(tag) {
  const on = {};
  const node = {
    tagName: String(tag).toUpperCase(), children: [], parentNode: null, attrs: {}, cls: new Set(), _text: '', open: false,
    get className() { return Array.from(node.cls).join(' '); },
    set className(v) { node.cls = new Set(String(v).split(/\s+/).filter(Boolean)); },
    classList: { add: (c) => node.cls.add(c), remove: (c) => node.cls.delete(c), contains: (c) => node.cls.has(c) },
    get textContent() { return node._text + node.children.map((c) => c.textContent).join(''); },
    set textContent(v) { node.children.forEach((c) => { c.parentNode = null; }); node.children = []; node._text = String(v); },
    get firstChild() { return node.children[0] || null; },
    appendChild(c) { if (c.parentNode) { c.parentNode.removeChild(c); } c.parentNode = node; node.children.push(c); return c; },
    removeChild(c) { const i = node.children.indexOf(c); if (i >= 0) { node.children.splice(i, 1); c.parentNode = null; } return c; },
    setAttribute(k, v) { node.attrs[k] = String(v); },
    getAttribute(k) { return k in node.attrs ? node.attrs[k] : null; },
    addEventListener(t, fn) { (on[t] = on[t] || []).push(fn); },
    fire(t) { (on[t] || []).forEach((fn) => fn({ type: t })); },
    click() { node.fire('click'); },
    matches(sel) { return sel === ':modal' ? node.open : false; },
    querySelector(sel) {
      const want = sel.replace(/^\./, '');
      const walk = (n) => { for (const c of n.children) { if (c.cls.has(want)) { return c; } const r = walk(c); if (r) { return r; } } return null; };
      return walk(node);
    },
  };
  return node;
}
const dialogs = [];
global.document = {
  createElement: el,
  querySelectorAll: (sel) => (sel === 'dialog[open]' ? dialogs.filter((d) => d.open) : []),
};
global.window = { requestAnimationFrame: (fn) => fn(), FomsWizardChrome: { toastMs: () => 4000 } };
global.requestAnimationFrame = window.requestAnimationFrame;
require(stackPath);
const T = window.FomsWizardToast;

// wizard.js 의 실제 toast()·errorToast() 본문
const els = { toastHost: el('div') };
const src = fs.readFileSync(fnPath, 'utf8');
const api = new Function('els', 'window', 'document', 'requestAnimationFrame', src + '; return { toast: toast };')(
  els, window, document, window.requestAnimationFrame);
const toast = api.toast;
const host = els.toastHost;
const texts = (h) => h.children.map((c) => c.textContent);   // 오류 알림은 글 + '다시 시도' + '×'
const out = {};

// 순수
out.label = [T.label('a', 1), T.label('a', 5)];
const L = [
  { key: '', text: 'x', error: false, retry: false, seq: 3 },
  { key: 'k', text: 'p', error: false, retry: false, seq: 1 },
  { key: '', text: 'e', error: true, retry: true, seq: 2 },
];
out.find = [
  T.findIndex(L, 'x', {}), T.findIndex(L, 'zz', { key: 'k' }), T.findIndex(L, 'p', {}),
  T.findIndex(L, 'x', { error: true }), T.findIndex(L, 'e', { error: true, retry: () => 0 }), T.findIndex(L, 'e', { error: true }),
];
out.evict = T.evictList(L, 3).map((e) => e.text);
out.evictErr = T.evictList([{ error: true, seq: 5, text: 'b' }, { error: true, seq: 4, text: 'a' }, { error: true, seq: 6, text: 'c' }], 3).map((e) => e.text);
out.evictRoom = T.evictList(L.slice(0, 1), 3).length;

// 1) Enter 로 5장 확인 — 같은 글은 하나로, 횟수만
for (let i = 0; i < 5; i++) { if (i) { tick(300); } toast('확인했어요 — 다음 학습에 씁니다'); }
out.enter = texts(host);
tick(3999);
out.enterAlive = host.children.length;     // 마지막 확인에서 4초 안이면 그대로
tick(2);
out.enterGoneLive = T.count();
tick(240);
out.enterGoneDom = host.children.length;

// 2) 일괄 저장 5장 — 진행 알림 하나를 고쳐 쓰고, 끝나면 닫고 마무리 하나
for (let i = 1; i <= 5; i++) { toast('일괄 저장 ' + i + '/5 처리 중…', { key: 'sheet-batch' }); tick(500); }
out.progress = texts(host);
T.drop('sheet-batch');
toast('시트 5장을 모두 전달 대기함에 넣었어요');
tick(240);
out.batchDone = texts(host);
tick(5000);

// 3) 서로 다른 글 5개 — 3개까지만(오래된 것부터 닫힘)
['가', '나', '다', '라', '마'].forEach((t) => toast(t));
out.cap = texts(host);
tick(5000);

// 4) 오류 알림: 같은 글은 하나로 '(2)', × 로 닫으면 목록에서도 빠져 다음 같은 오류는 새로
let retried = 0;
const retry = () => { retried += 1; };
toast('저장 실패 — 서버 오류', { error: true, retry });
toast('저장 실패 — 서버 오류', { error: true, retry });
out.errMerged = texts(host);
const errEl = host.children[0];
errEl.querySelector('dws-toast-close').click();
out.errClosedLive = T.count();
tick(240);
toast('저장 실패 — 서버 오류', { error: true, retry });
out.errAgain = texts(host);
host.children[0].querySelector('dws-toast-retry').click();
out.retried = retried;
tick(240);
out.afterRetryDom = host.children.length;

// 5) 진행(일반) 자리에 같은 key 오류가 오면 진행 알림은 바로 닫히고 오류 하나
toast('일괄 저장 2/5 처리 중…', { key: 'sheet-batch' });
toast('일괄 저장 실패', { error: true, retry, key: 'sheet-batch' });
out.keyToError = texts(host);
host.children[0].querySelector('dws-toast-close').click();
tick(240);

// 6) 오류 알림 3개가 떠 있을 때 일반 알림 — 오래된 오류부터(일반 알림이 없을 때만)
toast('오류 A', { error: true }); toast('오류 B', { error: true }); toast('오류 C', { error: true });
toast('알림 D');
out.errEvict = texts(host);
host.children.slice().forEach((c) => { const x = c.querySelector('dws-toast-close'); if (x) { x.click(); } });
tick(5000);

// 7) 모달 창이 열려 있으면 그 창 위 자리로(떠 있던 알림도 함께), 창이 닫히면 원래 자리로
toast('먼저 뜬 알림');
const dlg = el('dialog'); dlg.open = true; dialogs.push(dlg);
toast('다른 사람이 먼저 규칙을 고쳤습니다.');
const mh = dlg.querySelector('dws-toast-host-modal');
out.modal = { inDialog: mh ? texts(mh) : null, home: texts(host), live: mh ? mh.getAttribute('aria-live') : null };
toast('다른 사람이 먼저 규칙을 고쳤습니다.');
out.modalMerged = texts(mh);
dlg.open = false; dlg.fire('close');
out.afterClose = { inDialog: texts(mh), home: texts(host) };

process.stdout.write(JSON.stringify(out));
"""


def _run(tmp_path):
    fns = tmp_path / "toast_fns.js"
    fns.write_text(_fn_slice(JS, "function toast(msg, opts) {") + "\n" + _fn_slice(JS, "function errorToast(msg, retry) {"),
                   encoding="utf-8")
    proc = subprocess.run([_node(), "-e", RUNNER, str(STACK), str(fns)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_pure_rules(tmp_path):
    res = _run(tmp_path)
    assert res["label"] == ["a", "a (5)"]
    # 같은 글(키 없음) · 같은 key · key 알림과는 글이 같아도 안 합침 · 종류(일반/오류)·다시 시도 유무가 달라도 안 합침
    assert res["find"] == [0, 1, -1, -1, 2, -1]
    assert res["evict"] == ["p"]            # 상한을 넘으면 마지막으로 고친 때가 가장 이른 일반 알림부터
    assert res["evictErr"] == ["a"]         # 일반 알림이 없으면 오래된 오류
    assert res["evictRoom"] == 0


def test_same_text_merges_with_count_and_restarts_timer(tmp_path):
    res = _run(tmp_path)
    assert res["enter"] == ["확인했어요 — 다음 학습에 씁니다 (5)"]
    assert res["enterAlive"] == 1 and res["enterGoneLive"] == 0 and res["enterGoneDom"] == 0


def test_batch_progress_is_one_toast_then_final(tmp_path):
    res = _run(tmp_path)
    assert res["progress"] == ["일괄 저장 5/5 처리 중…"]
    assert res["batchDone"] == ["시트 5장을 모두 전달 대기함에 넣었어요"]


def test_at_most_three_visible(tmp_path):
    res = _run(tmp_path)
    assert res["cap"] == ["다", "라", "마"]


def test_error_toasts_merge_close_and_retry(tmp_path):
    res = _run(tmp_path)
    assert res["errMerged"] == ["저장 실패 — 서버 오류 (2)다시 시도×"]
    assert res["errClosedLive"] == 0
    assert res["errAgain"] == ["저장 실패 — 서버 오류다시 시도×"]   # 닫힌 알림에 합쳐지지 않고 새로
    assert res["retried"] == 1 and res["afterRetryDom"] == 0
    assert res["keyToError"] == ["일괄 저장 실패다시 시도×"]
    assert res["errEvict"] == ["오류 B×", "오류 C×", "알림 D"]


def test_toasts_rise_above_open_modal_and_return_on_close(tmp_path):
    res = _run(tmp_path)
    m = res["modal"]
    assert m["inDialog"] == ["먼저 뜬 알림", "다른 사람이 먼저 규칙을 고쳤습니다."] and m["home"] == []
    assert m["live"] == "polite"
    assert res["modalMerged"] == ["먼저 뜬 알림", "다른 사람이 먼저 규칙을 고쳤습니다. (2)"]
    assert res["afterClose"] == {"inDialog": [], "home": ["먼저 뜬 알림", "다른 사람이 먼저 규칙을 고쳤습니다. (2)"]}

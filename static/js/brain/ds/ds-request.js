/**
 * 문장으로 고치기 묶음 화면(/brain/requests/<번호> — 설계서 docs/specs/2026-11-18-brain-sentence-change_SPEC.md 4절 · D246) —
 * templates/brain/ds/request.html 의 [data-ds-req]. 화면은 서버가 그리고, 이 스크립트는 누름만 받는다:
 * - [빼기] [data-ds-req-skip] — 줄을 뺄 줄로 표시(다시 누르면 되살림 · aria-pressed). 모두 빼면 [이대로 고치기]가 잠긴다.
 * - [이대로 고치기] — POST …/apply {skip: [뺀 줄 번호]}.
 * - [버리기] · [이 묶음 되돌리기] — 한 번 누르면 무엇이 되는지 한 줄 + 확인 단추가 열리고(판 · 기록의 층 되돌리기와 같은 버릇),
 *   확인을 눌러야 POST …/discard · …/revert.
 * - 물음 [답하기] — POST …/answer {text}(다시 분석 — 10 ~ 30초, 단추를 잠근다).
 * 성공하면 이 화면을 다시 읽어 보고를 그린다. 실패는 서버가 준 말을 한 줄로. 분석 중 묶음이면 몇 초 뒤 다시 읽는다.
 * 보내는 동안 다른 단추는 모두 잠근다(두 번 눌러도 한 번만). fetch 는 brain-dom.js 한 곳 · 글은 textContent 만.
 */
(function (root) {
  'use strict';

  /** 뺀 줄 번호(오름차순 수). */
  function skipList(buttons) {
    return buttons.filter(function (b) { return b.getAttribute('aria-pressed') === 'true'; })
      .map(function (b) { return Number(b.getAttribute('data-ds-req-skip')); })
      .sort(function (a, b) { return a - b; });
  }

  var api = { skipList: skipList };
  root.FOMS_DS_REQUEST = api;
  if (typeof module === 'object' && module.exports) module.exports = api;

  var dom = root.FOMS_BRAIN_DOM;
  var doc = root.document;
  var box = doc && doc.querySelector('[data-ds-req]');
  if (!dom || !box || root.__FOMS_DS_REQ_BOUND) return;
  root.__FOMS_DS_REQ_BOUND = true;

  var status = box.querySelector('[data-ds-req-act-status]');
  var applyButton = box.querySelector('[data-ds-req-apply]');
  var skips = Array.prototype.slice.call(box.querySelectorAll('[data-ds-req-skip]'));
  var answerForm = box.querySelector('[data-ds-req-answer-form]');
  var answerInput = box.querySelector('[data-ds-req-answer]');
  var busy = false;
  var WAITS = { apply: '고치는 중이에요…', discard: '버리는 중이에요…', revert: '되돌리는 중이에요…',
                answer: '다시 분석 중이에요 — 10 ~ 30초 걸려요. 이 화면에 그대로 있어 주세요.' };

  function allControls() {
    return Array.prototype.slice.call(box.querySelectorAll('button, [data-ds-req-answer]'));
  }

  /** 보내는 동안 모든 단추 · 칸을 잠그고, 끝나면(실패) 앞 상태로 되돌린다. */
  function lock(on) {
    busy = on;
    box.setAttribute('aria-busy', on ? 'true' : 'false');
    allControls().forEach(function (node) {
      if (on) {
        node.setAttribute('data-ds-req-was', node.disabled ? '1' : '0');
        node.disabled = true;
      } else {
        node.disabled = node.getAttribute('data-ds-req-was') === '1';
        node.removeAttribute('data-ds-req-was');
      }
    });
  }

  async function send(act, body) {
    if (busy) return;
    var url = box.getAttribute('data-' + act + '-url');
    lock(true);
    dom.setStatus(status, WAITS[act]);
    var res = await dom.postJson(url, body || {});
    if (!res.ok) {
      lock(false);
      syncApply();
      dom.setStatus(status, res.error, 'error');
      return;
    }
    dom.setStatus(status, '마쳤어요 — 화면을 새로 읽어요.');
    root.location.reload();
  }

  /** 모두 뺐으면 [이대로 고치기]를 잠근다. */
  function syncApply() {
    if (!applyButton || busy) return;
    var none = skips.length > 0 && skipList(skips).length === skips.length;
    applyButton.disabled = none;
    if (none) dom.setStatus(status, '모든 줄을 뺐어요 — 고칠 줄을 하나 이상 남겨 주세요.');
    else if (status && !status.classList.contains('is-error')) dom.setStatus(status, '');
  }

  function toggleSkip(button) {
    var on = button.getAttribute('aria-pressed') !== 'true';
    var line = button.closest('[data-ds-req-line]');
    button.setAttribute('aria-pressed', on ? 'true' : 'false');
    var text = button.querySelector('[data-ds-req-skip-text]');
    if (text) text.textContent = on ? '되살리기' : '빼기';
    button.setAttribute('aria-label', line.getAttribute('data-ds-req-line') + '번 줄 ' + (on ? '되살리기' : '빼기'));
    line.classList.toggle('is-skipped', on);
    var note = line.querySelector('[data-ds-req-skipped]');
    if (note) note.hidden = !on;
    syncApply();
  }

  function openConfirm(wrap, open) {
    var ask = wrap.querySelector('[data-ds-req-ask]');
    var sure = wrap.querySelector('[data-ds-req-sure]');
    ask.hidden = open;
    sure.hidden = !open;
    if (open) wrap.querySelector('[data-ds-req-do]').focus();
    else ask.focus();
  }

  box.addEventListener('click', function (event) {
    var target = event.target;
    if (!target || !target.closest || busy) return;
    var skip = target.closest('[data-ds-req-skip]');
    if (skip) { toggleSkip(skip); return; }
    if (target.closest('[data-ds-req-apply]')) { send('apply', { skip: skipList(skips) }); return; }
    var wrap = target.closest('[data-ds-req-confirm]');
    if (wrap && target.closest('[data-ds-req-ask]')) { openConfirm(wrap, true); return; }
    if (wrap && target.closest('[data-ds-req-no]')) { openConfirm(wrap, false); return; }
    var go = target.closest('[data-ds-req-do]');
    if (go) send(go.getAttribute('data-ds-req-do'));
  });

  if (answerForm) {
    answerForm.addEventListener('submit', function (event) {
      event.preventDefault();
      var text = String(answerInput ? answerInput.value : '').trim();
      if (!text) {
        dom.setStatus(status, '답을 적어 주세요.', 'error');
        return;
      }
      send('answer', { text: text });
    });
  }

  if (box.getAttribute('data-ds-req-status-code') === 'analyzing') {
    root.setTimeout(function () { root.location.reload(); }, 5000);  // 다른 창에서 분석 중 — 끝나면 보고가 그려진다
  }
})(typeof window !== 'undefined' ? window : globalThis);

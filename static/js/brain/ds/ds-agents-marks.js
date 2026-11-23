/**
 * AI 직원 'AI 시험' 칸의 사장님 채점(설계서 docs/specs/2026-11-23-brain-learning-upgrade_SPEC.md 4.1) — partials/agents_evals.html 의
 * [data-ds-evals-marks](ADMIN 에게만 있다).
 *
 * - ds-agents.js 가 직원을 그릴 때마다 내는 document 'ds:agents-detail' 이벤트({key})를 듣는다. 상담 AI(cs)면 GET data-marks-url
 *   로 오늘 채점할 차례를 읽어 한 줄에 손님 글 · 직원 답 · AI 초안(넘긴 차례는 넘긴 까닭 한 문장)과 단추 둘을 그린다. 다른 직원이면
 *   자리를 숨긴다.
 * - 초안: [보내도 돼요] [안 돼요] — '안 돼요'면 까닭 하나(서버가 준 fail_kinds — 사실이 틀림 · 없는 약속 · 말투)를 고른다.
 *   넘김: [넘기는 게 맞아요] [답했어야 해요]. 고르면 POST data-marks-url {mark, answer, fail_kind?} → 그 줄을 걷고 한 줄 수를 고친다.
 * - 채점하는 AI 의 판정은 받지도 그리지도 않는다(사장님이 모르고 채점한다).
 * - 이 조각은 본문 안이라 brain-dom.js 보다 먼저 실릴 수 있다 — 듣개만 바로 걸고 그리기는 이벤트 때 window.FOMS_BRAIN_DOM 을 쓴다.
 * fetch 는 brain-dom.js 한 곳(try/catch · success 확인) · 글은 textContent 만 · 듣개는 한 번만(window.__FOMS_DS_EVAL_MARKS_BOUND).
 */
(function () {
  'use strict';

  if (window.__FOMS_DS_EVAL_MARKS_BOUND) return;
  window.__FOMS_DS_EVAL_MARKS_BOUND = true;

  /** 갈래마다 단추 둘 — 앞은 '된다'(초록), 뒤는 '안 된다'(빨강). */
  var CHOICES = {
    draft: [{ answer: 'ok', label: '보내도 돼요', cls: 'f-btn-success' },
            { answer: 'bad', label: '안 돼요', cls: 'f-btn-danger' }],
    handoff: [{ answer: 'handoff_right', label: '넘기는 게 맞아요', cls: 'f-btn-success' },
              { answer: 'should_answer', label: '답했어야 해요', cls: 'f-btn-danger' }]
  };
  var state = { key: '', kinds: [], busy: false, done: 0, left: 0, seq: 0 };

  function dom() { return window.FOMS_BRAIN_DOM; }
  function root() { return document.querySelector('[data-ds-evals-marks]'); }
  function part(name) {
    var box = root();
    return box ? box.querySelector('[data-ds-evals-marks-' + name + ']') : null;
  }

  /** 한 줄 수 — 오류 글이 오면 그 글(빨강), 아니면 오늘 한 수 · 남은 줄 수. */
  function paintCount(errorText) {
    var node = part('count');
    var list = part('list');
    if (!node || !list) return;
    var shown = list.children.length;
    var text = errorText || (state.left <= 0 ? '오늘 채점 ' + state.done + '개를 다 했어요.'
      : shown ? 'AI 초안을 손님에게 보내도 될지 골라 주세요 · 오늘 ' + state.done + '개 했어요 · ' + shown + '개 남았어요'
        : '오늘 ' + state.done + '개 했어요 · 지금은 채점할 차례가 없어요.');
    node.textContent = text;
    node.classList.toggle('is-error', Boolean(errorText));
    list.hidden = !shown;
  }

  /** 단추 하나. */
  function button(label, cls, onClick) {
    var node = dom().el('button', { cls: 'f-btn' + (cls ? ' ' + cls : ''), text: label, attrs: { type: 'button' } });
    node.addEventListener('click', onClick);
    return node;
  }

  /** 이름 · 글 한 덩어리(글은 줄바꿈 그대로). */
  function block(label, text) {
    var el = dom().el;
    return el('div', { cls: 'f-col', children: [
      el('span', { cls: 'f-small f-muted', text: label }),
      el('p', { cls: 'f-quote fb-evals-mark-text', text: text })] });
  }

  function setDisabled(li, disabled) {
    Array.prototype.slice.call(li.querySelectorAll('button')).forEach(function (node) { node.disabled = disabled; });
  }

  /** 줄을 걷는다(남은 줄이 없으면 수 줄만). */
  function drop(li) {
    if (li.parentNode) li.parentNode.removeChild(li);
  }

  /** 채점 하나 보내기 — 되면 줄을 걷고 수를 고친다. 이미 채점했거나 없는 차례면 줄을 걷고 · 오늘 다 했으면 모두 걷는다. */
  async function send(li, item, answer, failKind) {
    var box = root();
    if (!box || state.busy) return;
    state.busy = true;
    setDisabled(li, true);
    var body = { mark: item.id, answer: answer };
    if (failKind) body.fail_kind = failKind;
    var res = await dom().postJson(box.getAttribute('data-marks-url'), body);
    state.busy = false;
    if (!res.ok) {
      var code = res.data && res.data.code;
      if (code === 'EVAL_MARK_LIMIT') {
        state.left = 0;
        dom().clear(part('list'));
      } else if (code === 'EVAL_MARK_GONE') {
        drop(li);
      } else {
        setDisabled(li, false);
      }
      paintCount(res.error || '저장하지 못했어요.');
      return;
    }
    state.done = res.data.graded_today;
    state.left = res.data.left;
    drop(li);
    if (state.left <= 0) dom().clear(part('list'));
    paintCount();
  }

  /** '안 돼요' — 단추 자리를 까닭 고르기로 바꾼다(하나만 고른다). */
  function askReason(li, item) {
    var acts = li.querySelector('[data-ds-evals-mark-acts]');
    dom().clear(acts);
    acts.appendChild(dom().el('span', { cls: 'f-small', text: '무엇이 안 되나요?' }));
    state.kinds.forEach(function (kind) {
      acts.appendChild(button(kind.label, '', function () { send(li, item, 'bad', kind.code); }));
    });
    var first = acts.querySelector('button');
    if (first) first.focus();
  }

  /** 단추 둘(갈래에 맞게). */
  function choices(li, item) {
    var acts = dom().el('div', { cls: 'fb-evals-mark-acts', attrs: { 'data-ds-evals-mark-acts': '' } });
    (CHOICES[item.kind] || []).forEach(function (choice) {
      acts.appendChild(button(choice.label, choice.cls, function () {
        if (choice.answer === 'bad') askReason(li, item);
        else send(li, item, choice.answer, null);
      }));
    });
    return acts;
  }

  /** 채점할 줄 하나 — 손님 글 · 직원 답 · AI 초안(또는 넘김 한 문장) · 단추. */
  function row(item) {
    var li = dom().el('li', { cls: 'f-col fb-evals-mark', attrs: { 'data-ds-evals-mark': String(item.id) } });
    li.appendChild(block('손님 글', item.question));
    li.appendChild(block('직원 답', item.staff_reply));
    li.appendChild(block('AI 초안', item.kind === 'handoff' ? item.handoff : item.draft));
    li.appendChild(choices(li, item));
    return li;
  }

  /** GET data-marks-url → 줄 · 수를 새로 그린다(늦게 온 앞 답은 버린다). */
  async function load() {
    var box = root();
    if (!box) return;
    state.seq += 1;
    var mine = state.seq;
    var res = await dom().getJson(box.getAttribute('data-marks-url'));
    if (mine !== state.seq || state.key !== 'cs') return;
    var list = part('list');
    dom().clear(list);
    box.hidden = false;
    if (!res.ok || !res.data) {
      paintCount(res.error || '채점할 차례를 읽지 못했어요.');
      return;
    }
    state.kinds = res.data.fail_kinds || [];
    state.done = res.data.graded_today || 0;
    state.left = res.data.left || 0;
    (res.data.items || []).forEach(function (item) { list.appendChild(row(item)); });
    paintCount();
  }

  document.addEventListener('ds:agents-detail', function (event) {
    var detail = event.detail || {};
    state.key = detail.key || '';
    var box = root();
    if (!box || !dom()) return;
    if (state.key === 'cs') {
      load();
      return;
    }
    state.seq += 1;  // 읽는 중이던 답은 버린다
    box.hidden = true;
  });
})();

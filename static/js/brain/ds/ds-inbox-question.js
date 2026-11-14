/**
 * 새 승인 대기 화면 — ③ 사장님이 정해 주실 것 질문 카드(설계서 2026-11-14-foms-graft 5.4 · 옛 brain-inbox-question.js 와 같은
 * 흐름 — D152). 엇갈림 · 질문 제안 하나를 "어느 쪽이 맞아요?" 로 묻고, 답마다 있는 동작만 쓴다(새 쓰기 길 없음):
 *  - 회사 지식이 맞아요 = 그 제안을 'knowledge_right' 까닭으로 닫는다(바깥 글은 고칠 일로 남음).
 *  - 바깥 글이 맞아요 = 다루는 지식 글을 적은 글로 고치는 제안 → 바로 승인 → 질문 제안을 'outside_right' 로 닫는다.
 *  - 둘 다 맞아요 = 경우를 적은 한 줄을 지식 글 끝에 덧붙이는 제안 → 바로 승인 → 'both_right' 로 닫는다.
 * 결정한 사람 · 등급 B 확인은 서버가 다시 본다. PC · 폰 모두 같은 카드(폰에서도 정한다). '나중에'는 data-ds-act="later".
 * 글은 textContent 만 · 인라인 스타일 없음.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var kit = window.FOMS_DS_INBOX_KIT;
  if (!dom || !kit) return;
  var el = dom.el;
  var CODES = { knowledge: 'knowledge_right', 'outside-save': 'outside_right', 'both-save': 'both_right' };
  var SAID = { knowledge: '회사 지식이 맞아요', 'outside-save': '바깥 글이 맞아요', 'both-save': '둘 다 맞아요' };

  function answerButton(text, answer, cls) {
    var b = kit.button(text, null, cls || '');
    b.setAttribute('data-ds-answer', answer);
    return b;
  }

  function side(head, text) {
    return el('div', { cls: 'f-col f-gap4', children: [el('span', { cls: 'f-h6', text: head }),
                                                       el('p', { cls: 'f-quote', text: text || '' })] });
  }

  function editor(kind, about) {
    var box = el('div', { cls: 'f-col fb-edit', attrs: { 'data-ds-answer-box': kind } });
    box.hidden = true;
    var outside = kind === 'outside';
    var input = el(outside ? 'textarea' : 'input', { cls: 'f-input', attrs: {
      'data-ds-answer-text': kind, rows: outside ? 3 : null, type: outside ? null : 'text', maxlength: outside ? null : 200,
      'aria-label': outside ? '새 회사 지식 글' : '어떤 경우인지 한 줄' } });
    input.value = outside ? about.text : '';
    box.appendChild(el('label', { cls: 'f-field', children: [el('span', { cls: 'f-label', text: outside
      ? '새 글 — AI · 직원이 이 글로 안내해요' : '어떤 경우에 어느 쪽인지 한 줄 — 지식 글 끝에 붙어요' }), input] }));
    box.appendChild(el('div', { cls: 'f-actions', children: [
      answerButton(outside ? '이 글로 바꾸기' : '덧붙이기', kind + '-save', 'f-btn-primary')] }));
    return box;
  }

  /** 질문 카드 하나 — li(data-card-id · data-change-id 는 ds-inbox-act.js 가 찾는 꼴 그대로). */
  function build(card) {
    var view = card.main;
    var about = (view.about || [])[0] || null;
    var li = el('li', { cls: 'f-card f-card-compact f-col fb-icard', attrs: { 'data-card-id': card.id } });
    var box = el('div', { cls: 'f-col fb-prop', attrs: { 'data-change-id': view.id } });
    var title = card.title || card.name || '';
    box.appendChild(el('span', { cls: 'f-strong', text: title }));
    box.appendChild(el('p', { cls: 'f-h6', text: '어느 쪽이 맞아요?' }));
    if (view.sentence && view.sentence.indexOf(title.replace(/…$/, '')) !== 0) box.appendChild(side('바깥 글', view.sentence));
    if (about) box.appendChild(side('회사 지식 「' + about.title + '」', about.text));
    var bar = el('div', { cls: 'f-actions' });
    bar.appendChild(answerButton('회사 지식이 맞아요 (바깥 글은 고칠 일로)', 'knowledge'));
    if (about) {
      bar.appendChild(answerButton('바깥 글이 맞아요 (지식 고치기)', 'outside'));
      bar.appendChild(answerButton('둘 다 맞아요 (경우 적기)', 'both'));
    }
    bar.appendChild(kit.button('나중에', 'later', 'f-btn-minimal', 'time'));
    box.appendChild(bar);
    if (about) {
      box.appendChild(editor('outside', about));
      box.appendChild(editor('both', about));
    } else {
      box.appendChild(el('p', { cls: 'f-help', text: '다루는 지식을 못 찾아 「회사 지식이 맞아요」만 고를 수 있어요.' }));
    }
    box.appendChild(kit.statusLine());
    li.appendChild(box);
    return li;
  }

  function newText(kind, box, about) {
    var input = box.querySelector('[data-ds-answer-text="' + (kind === 'outside-save' ? 'outside' : 'both') + '"]');
    var value = input ? input.value.trim() : '';
    if (!value) return '';
    return kind === 'outside-save' ? value : about.text.replace(/\s+$/, '') + '\n' + value;
  }

  function lock(box, on) {
    Array.prototype.slice.call(box.querySelectorAll('[data-ds-answer]')).forEach(function (b) { b.disabled = on; });
  }

  function fail(box, status, text) {
    lock(box, false);
    dom.setStatus(status, text || '하지 못했어요 — 다시 눌러 주세요.', 'error');
  }

  /** 고칠 글이 있으면 고침 제안 → 승인. 실패 글(없으면 빈 글)을 돌려준다. */
  async function rewrite(kind, box, about, urls) {
    var text = about ? newText(kind, box, about) : '';
    if (!text || text === about.text) return '바뀐 글이 없어요 — 글을 적어 주세요.';
    var made = await dom.postJson(urls.proposals, { action: 'propose_edit', key: about.key, base_version: about.version,
                                                    after: { text: text }, reason: '사장님 답 — ' + SAID[kind] });
    if (!made.ok) return made.error;
    var applied = await dom.postJson(urls.proposals + '/' + made.data.change_id + '/apply',
                                     { base_version: about.version, view_ms: 0, confirm: { field: 'text', value: text } });
    return applied.ok ? '' : applied.error;
  }

  /** 답 하나 — 고칠 글이 있으면 고침 제안 → 승인, 그다음 질문 제안을 그 답의 까닭으로 닫는다. */
  async function answer(button, deps) {
    var box = button.closest('[data-change-id]');
    var view = box && deps.findView(box.getAttribute('data-change-id'));
    if (!view) return;
    var kind = button.getAttribute('data-ds-answer');
    var status = box.querySelector('[data-ds-prop-status]');
    if (kind === 'outside' || kind === 'both') {
      Array.prototype.slice.call(box.querySelectorAll('[data-ds-answer-box]')).forEach(function (b) {
        b.hidden = b.getAttribute('data-ds-answer-box') !== kind;
      });
      return;
    }
    lock(box, true);
    if (kind !== 'knowledge') {
      dom.setStatus(status, '회사 지식을 고치는 중…');
      var problem = await rewrite(kind, box, (view.about || [])[0], deps.urls);
      if (problem) { fail(box, status, problem); return; }
    }
    var closed = await dom.postJson(deps.urls.proposals + '/' + view.id + '/reject', { code: CODES[kind], view_ms: 0 });
    if (!closed.ok) { fail(box, status, closed.error); return; }
    await deps.reload();
    deps.done('정했어요 — ' + SAID[kind] + '.');
  }

  window.FOMS_DS_INBOX_QUESTION = { build: build, answer: answer };
})();

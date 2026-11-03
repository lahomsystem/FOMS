/**
 * '확인할 것' ③ 사장님이 정해 주실 것 — 질문 카드(HAUD master brain 설계서 7.9 단계 4 · D152). 엇갈림 · 질문 제안 하나를
 * "어느 쪽이 맞아요?" 로 묻고, 답마다 있는 동작만 쓴다(새 쓰기 길 없음):
 *  - 회사 지식이 맞아요 = 그 제안을 '회사 지식이 맞음 — 바깥 글 고칠 일' 까닭으로 닫는다(고칠 일로 남음).
 *  - 바깥 글이 맞아요 = 다루는 지식 글을 사장님이 적은 글로 고치는 제안 → 바로 승인 → 그 제안을 닫는다.
 *  - 둘 다 맞아요 = 경우를 적은 한 줄을 지식 글 끝에 덧붙이는 제안 → 바로 승인 → 그 제안을 닫는다.
 * 글은 textContent 만 · 인라인 스타일 없음. '나중에'는 brain-inbox.js 의 data-brain-act="later" 그대로.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  if (!dom) return;
  var el = dom.el;
  var CODES = { knowledge: 'knowledge_right', 'outside-save': 'outside_right', 'both-save': 'both_right' };
  var SAID = { knowledge: '회사 지식이 맞아요', 'outside-save': '바깥 글이 맞아요', 'both-save': '둘 다 맞아요' };

  function button(text, answer, primary) {
    return el('button', { cls: 'brain-btn' + (primary ? ' brain-btn--primary' : ''), text: text,
                          attrs: { type: 'button', 'data-brain-answer': answer } });
  }

  function side(head, text) {
    return el('p', { cls: 'brain-prop__fact', children: [el('strong', { text: head + ' · ' }),
                                                        el('span', { text: '“' + (text || '') + '”' })] });
  }

  function editor(kind, about) {
    var box = el('div', { cls: 'brain-prop__edit', attrs: { 'data-brain-answer-box': kind } });
    box.hidden = true;
    var outside = kind === 'outside';
    var input = el(outside ? 'textarea' : 'input', { cls: 'form-control form-control-sm', attrs: {
      'data-brain-answer-text': kind, rows: outside ? 3 : null, type: outside ? null : 'text', maxlength: outside ? null : 200,
      'aria-label': outside ? '새 회사 지식 글' : '어떤 경우인지 한 줄' } });
    input.value = outside ? about.text : '';
    box.appendChild(el('label', { cls: 'brain-propose__field', children: [el('span', { text: outside
      ? '새 글 — AI · 직원이 이 글로 안내해요'
      : '어떤 경우에 어느 쪽인지 한 줄 — 지식 글 끝에 붙어요' }), input] }));
    box.appendChild(button(outside ? '이 글로 바꾸기' : '덧붙이기', kind + '-save', true));
    return box;
  }

  /** 질문 카드 하나 — li(카드 id · 제안 id 는 brain-inbox.js 가 찾는 꼴 그대로). */
  function build(card) {
    var view = card.main;
    var about = (view.about || [])[0] || null;
    var li = el('li', { cls: 'brain-icard brain-type--' + card.type, attrs: { 'data-card-id': card.id } });
    var box = el('div', { cls: 'brain-prop', attrs: { 'data-change-id': view.id } });
    var title = card.title || card.name || '';
    box.appendChild(el('p', { cls: 'brain-icard__name', text: title }));
    box.appendChild(el('p', { cls: 'brain-prop__meaning', text: '어느 쪽이 맞아요?' }));
    if (view.sentence && view.sentence.indexOf(title.replace(/…$/, '')) !== 0) box.appendChild(side('바깥 글', view.sentence));
    if (about) box.appendChild(side('회사 지식 「' + about.title + '」', about.text));
    var bar = el('div', { cls: 'brain-prop__actions' });
    bar.appendChild(button('회사 지식이 맞아요 (바깥 글은 고칠 일로)', 'knowledge'));
    if (about) {
      bar.appendChild(button('바깥 글이 맞아요 (지식 고치기)', 'outside'));
      bar.appendChild(button('둘 다 맞아요 (경우 적기)', 'both'));
    }
    bar.appendChild(el('button', { cls: 'brain-btn', text: '나중에', attrs: { type: 'button', 'data-brain-act': 'later' } }));
    box.appendChild(bar);
    if (about) {
      box.appendChild(editor('outside', about));
      box.appendChild(editor('both', about));
    } else {
      box.appendChild(el('p', { cls: 'brain-empty', text: '다루는 지식을 못 찾아 「회사 지식이 맞아요」만 고를 수 있어요.' }));
    }
    box.appendChild(el('p', { cls: 'brain-status-line', attrs: { 'data-brain-prop-status': '1', role: 'status',
                                                                'aria-live': 'polite' } }));
    li.appendChild(box);
    return li;
  }

  function newText(kind, box, about) {
    var input = box.querySelector('[data-brain-answer-text="' + (kind === 'outside-save' ? 'outside' : 'both') + '"]');
    var value = input ? input.value.trim() : '';
    if (!value) return '';
    return kind === 'outside-save' ? value : about.text.replace(/\s+$/, '') + '\n' + value;
  }

  function fail(box, status, text) {
    box.querySelectorAll('[data-brain-answer]').forEach(function (b) { b.disabled = false; });
    dom.setStatus(status, text || '하지 못했어요 — 다시 눌러 주세요.', 'error');
  }

  /** 답 하나 — 고칠 글이 있으면 고침 제안 → 승인, 그다음 질문 제안을 그 답의 까닭으로 닫는다. */
  async function answer(button, deps) {
    var box = button.closest('[data-change-id]');
    var view = box && deps.findView(box.getAttribute('data-change-id'));
    if (!view) return;
    var kind = button.getAttribute('data-brain-answer');
    var status = box.querySelector('[data-brain-prop-status]');
    if (kind === 'outside' || kind === 'both') {
      box.querySelectorAll('[data-brain-answer-box]').forEach(function (b) {
        b.hidden = b.getAttribute('data-brain-answer-box') !== kind;
      });
      return;
    }
    var about = (view.about || [])[0];
    box.querySelectorAll('[data-brain-answer]').forEach(function (b) { b.disabled = true; });
    if (kind !== 'knowledge') {
      var text = about ? newText(kind, box, about) : '';
      if (!text || text === about.text) {
        fail(box, status, '바뀐 글이 없어요 — 글을 적어 주세요.');
        return;
      }
      dom.setStatus(status, '회사 지식을 고치는 중…');
      var made = await dom.postJson(deps.urls.proposals, { action: 'propose_edit', key: about.key,
        base_version: about.version, after: { text: text }, reason: '사장님 답 — ' + SAID[kind] });
      var applied = made.ok && await dom.postJson(deps.urls.proposals + '/' + made.data.change_id + '/apply',
        { base_version: about.version, view_ms: 0, confirm: { field: 'text', value: text } });
      if (!made.ok || !applied.ok) {
        fail(box, status, made.ok ? applied.error : made.error);
        return;
      }
    }
    var closed = await dom.postJson(deps.urls.proposals + '/' + view.id + '/reject', { code: CODES[kind], view_ms: 0 });
    if (!closed.ok) {
      fail(box, status, closed.error);
      return;
    }
    await deps.reload();
    deps.done('정했어요 — ' + SAID[kind] + '.');
  }

  window.FOMS_BRAIN_INBOX_QUESTION = { build: build, answer: answer, codes: Object.keys(CODES).map(function (k) {
    return CODES[k];
  }) };
})();

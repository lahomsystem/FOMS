/**
 * '승인 대기' ③ 사장님이 정해 주실 것 — 질문 카드(HAUD master brain 설계서 7.9 단계 4 · D152). 엇갈림 · 질문 제안 하나를
 * "어느 쪽이 맞아요?" 로 묻는다. 답은 **한 번에 저장**(설계서 2026-11-26 온톨로지 잇기 3.2 — POST …/proposals/<id>/answer
 * 한 번. 서버가 고침 제안 · 반영 · 카드 닫기 · 사장님 글 남기기를 한 트랜잭션에서 한다):
 *  - 회사 지식이 맞아요 = code 'knowledge_right'(글 없음).
 *  - 바깥 글이 맞아요 = code 'outside_right' + 사장님이 적은 글(새 지식 글 전체).
 *  - 둘 다 맞아요 = code 'both_right' + 경우를 적은 한 줄(서버가 지식 글 끝에 붙인다).
 * 결정 시간(view_ms)은 카드를 보인 때부터 잰다. 금액 알림(saved 거짓)이면 그 한 줄을 보이고 같은 글로 다시 누르면 저장한다.
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
    var box = el('div', { cls: 'brain-prop', attrs: { 'data-change-id': view.id,
                                                      'data-shown-at': Math.round(window.performance.now()) } });
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

  /** 사장님이 적은 글(앞뒤 빈칸 뺌) — 서버에 보내는 글. */
  function typedText(kind, box) {
    var input = box.querySelector('[data-brain-answer-text="' + (kind === 'outside-save' ? 'outside' : 'both') + '"]');
    return input ? input.value.trim() : '';
  }

  /** 저장하면 들어갈 지식 글(서버와 같은 셈 — 바뀐 글 없음 확인용). */
  function newText(kind, box, about) {
    var value = typedText(kind, box);
    if (!value) return '';
    return kind === 'outside-save' ? value : about.text.replace(/\s+$/, '') + '\n' + value;
  }

  function fail(box, status, text) {
    box.querySelectorAll('[data-brain-answer]').forEach(function (b) { b.disabled = false; });
    dom.setStatus(status, text || '하지 못했어요 — 다시 눌러 주세요.', 'error');
  }

  /** 답 하나 — 서버 동작 하나(answer_question)로 한 번에 저장한다. */
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
    var body = { code: CODES[kind],
                 view_ms: Math.max(0, Math.round(window.performance.now() - Number(box.getAttribute('data-shown-at') || 0))) };
    if (kind !== 'knowledge') {
      var text = about ? newText(kind, box, about) : '';
      if (!text || text === about.text) {
        fail(box, status, '바뀐 글이 없어요 — 글을 적어 주세요.');
        return;
      }
      body.text = typedText(kind, box);
      body.base_version = about.version;
      if (box.getAttribute('data-brain-money-ok') === body.text) body.money_ok = true;  // 금액 알림을 본 뒤 같은 글로 다시
      dom.setStatus(status, '회사 지식을 고치는 중…');
    }
    var saved = await dom.postJson(deps.urls.proposals + '/' + view.id + '/answer', body);
    if (!saved.ok) {
      fail(box, status, saved.error);
      return;
    }
    if (saved.data && saved.data.saved === false) {  // 금액 알림 — 아무것도 저장하지 않았다. 같은 글로 다시 누르면 저장
      box.setAttribute('data-brain-money-ok', body.text || '');
      box.querySelectorAll('[data-brain-answer]').forEach(function (b) { b.disabled = false; });
      dom.setStatus(status, saved.data.message);
      return;
    }
    await deps.reload();
    deps.done('정했어요 — ' + SAID[kind] + '.');
  }

  window.FOMS_BRAIN_INBOX_QUESTION = { build: build, answer: answer, codes: Object.keys(CODES).map(function (k) {
    return CODES[k];
  }) };
})();

/**
 * 새 승인 대기 화면 — ③ 사장님이 정해 주실 것 질문 카드(설계서 2026-11-14-foms-graft 5.4 · 옛 brain-inbox-question.js 와 같은
 * 흐름 — D152). 엇갈림 · 질문 제안 하나를 "어느 쪽이 맞아요?" 로 묻는다. 답은 **한 번에 저장**(설계서 2026-11-26 온톨로지 잇기
 * 3.2 — POST …/proposals/<id>/answer 한 번. 서버가 고침 제안 · 반영 · 카드 닫기 · 사장님 글 남기기를 한 트랜잭션에서 한다):
 *  - 회사 지식이 맞아요 = code 'knowledge_right'(글 없음).
 *  - 바깥 글이 맞아요 = code 'outside_right' + 적은 글(새 지식 글 전체). 칸에는 바깥 글이 미리 들어간다(ds-inbox-view.js
 *    outsideDraft — 지금 글을 품으면 바깥 글 그대로, 아니면 어긋난 문장을 빼고 붙임).
 *  - 둘 다 맞아요 = code 'both_right' + 적은 한 줄(서버가 지식 글 끝에 붙인다).
 * 두 칸 아래에는 저장 전에 '바뀌는 곳'(빠지는 글 · 들어가는 글 — ds-inbox-view.js textDiff)을 보인다(설계서 2026-11-23 5.1).
 * 결정 시간(view_ms)은 카드를 보인 때부터 누를 때까지 잰다. 서버가 금액 알림(saved 거짓 · 견적 계산기가 원본인 지식에 금액을 적음)을
 * 돌려주면 그 한 줄을 보이고, 같은 글로 한 번 더 누르면 money_ok 를 실어 저장한다.
 * 결정한 사람 · 등급 B 확인은 서버가 다시 본다. PC · 폰 모두 같은 카드(폰에서도 정한다). '나중에'는 data-ds-act="later".
 * 답한 바로 뒤 ds-inbox-undo.js 가 [되돌리기]를 보인다(닫은 질문 번호 + 서버가 돌려준 고침 번호를 넘긴다).
 * 글은 textContent 만 · 인라인 스타일 없음.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var kit = window.FOMS_DS_INBOX_KIT;
  var iv = window.FOMS_DS_INBOX_VIEW;
  if (!dom || !kit || !iv) return;
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

  var PART = { same: 'span', del: 'del', add: 'ins' };

  /**
   * 바뀌는 곳(설계서 2026-11-23 5.1) — 저장하면 들어갈 글(newText 와 같은 셈)을 지금 지식 글과 견줘, 빠지는 글은 빨강 + 가운데
   * 줄 · 들어가는 글은 초록 + 밑줄로 보인다(색을 못 가려도 읽히게). 바뀌는 것이 없으면 한 줄만.
   */
  function showChange(kind, box, about) {
    var out = box.querySelector('[data-ds-answer-change="' + kind + '"]');
    if (!out || !about) return;
    var after = newText(kind + '-save', box, about);
    out.textContent = '';
    if (!after || after === about.text) {
      out.appendChild(el('p', { cls: 'f-help', text: '아직 바뀌는 곳이 없어요.' }));
      return;
    }
    var line = el('p', { cls: 'fb-change__text' });
    iv.textDiff(about.text, after).forEach(function (part) {
      line.appendChild(el(PART[part.kind], { cls: 'fb-change__' + part.kind, text: part.text }));
    });
    out.appendChild(el('span', { cls: 'f-label', text: '바뀌는 곳 — 빨간 줄 그은 글은 빠지고, 초록 밑줄 글이 들어가요' }));
    out.appendChild(line);
  }

  function editor(kind, about, sentence) {
    var box = el('div', { cls: 'f-col fb-edit', attrs: { 'data-ds-answer-box': kind } });
    box.hidden = true;
    var outside = kind === 'outside';
    var input = el(outside ? 'textarea' : 'input', { cls: 'f-input', attrs: {
      'data-ds-answer-text': kind, rows: outside ? 3 : null, type: outside ? null : 'text', maxlength: outside ? null : 200,
      'aria-label': outside ? '새 회사 지식 글' : '어떤 경우인지 한 줄' } });
    var draft = outside ? iv.outsideDraft(sentence, about.text) : { text: '', mixed: false };
    input.value = draft.text;
    box.appendChild(el('label', { cls: 'f-field', children: [el('span', { cls: 'f-label', text: outside
      ? '새 글 — AI · 직원이 이 글로 안내해요' : '손님에게 안내할 문장으로 적어요 — 지식 글 끝에 붙어요' }), input] }));
    if (draft.mixed) box.appendChild(el('p', { cls: 'f-help', text: '지금 글 뒤에 바깥 글을 붙였어요 — 틀린 옛 문장은 지워 주세요.' }));
    box.appendChild(el('div', { cls: 'f-col f-gap4 fb-change', attrs: { 'data-ds-answer-change': kind, 'aria-live': 'polite' } }));
    box.appendChild(el('div', { cls: 'f-actions', children: [
      answerButton(outside ? '이 글로 바꾸기' : '덧붙이기', kind + '-save', 'f-btn-primary')] }));
    showChange(kind, box, about);
    var timer = 0;
    input.addEventListener('input', function () {  // 적는 동안 잠깐 멈출 때마다 다시 그린다
      window.clearTimeout(timer);
      timer = window.setTimeout(function () { showChange(kind, box, about); }, 150);
    });
    return box;
  }

  /** 질문 카드 하나 — li(data-card-id · data-change-id 는 ds-inbox-act.js 가 찾는 꼴 그대로). */
  function build(card) {
    var view = card.main;
    var about = (view.about || [])[0] || null;
    var li = el('li', { cls: 'f-card f-card-compact f-col fb-icard', attrs: { 'data-card-id': card.id } });
    var box = el('div', { cls: 'f-col fb-prop', attrs: { 'data-change-id': view.id,
                                                         'data-shown-at': Math.round(window.performance.now()) } });
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
      box.appendChild(editor('outside', about, view.sentence));
      box.appendChild(editor('both', about));
    } else {
      box.appendChild(el('p', { cls: 'f-help', text: '다루는 지식을 못 찾아 「회사 지식이 맞아요」만 고를 수 있어요.' }));
    }
    box.appendChild(kit.statusLine());
    li.appendChild(box);
    return li;
  }

  /** 사장님이 적은 글(앞뒤 빈칸 뺌) — 서버에 보내는 글. */
  function typedText(kind, box) {
    var input = box.querySelector('[data-ds-answer-text="' + (kind === 'outside-save' ? 'outside' : 'both') + '"]');
    return input ? input.value.trim() : '';
  }

  /** 저장하면 들어갈 지식 글(서버와 같은 셈 — 바뀌는 곳 · 바뀐 글 없음 확인용). */
  function newText(kind, box, about) {
    var value = typedText(kind, box);
    if (!value) return '';
    return kind === 'outside-save' ? value : about.text.replace(/\s+$/, '') + '\n' + value;
  }

  function viewMs(box) {
    return Math.max(0, Math.round(window.performance.now() - Number(box.getAttribute('data-shown-at') || 0)));
  }

  function lock(box, on) {
    Array.prototype.slice.call(box.querySelectorAll('[data-ds-answer]')).forEach(function (b) { b.disabled = on; });
  }

  function fail(box, status, text) {
    lock(box, false);
    dom.setStatus(status, text || '하지 못했어요 — 다시 눌러 주세요.', 'error');
  }

  /** 보낼 본문 — 고칠 글이 있는 답은 적은 글 · 다루는 지식 판. {problem: 실패 글(없으면 빈 글), body}. */
  function answerBody(kind, box, about) {
    var body = { code: CODES[kind], view_ms: viewMs(box) };
    if (kind === 'knowledge') return { problem: '', body: body };
    var after = about ? newText(kind, box, about) : '';
    if (!after || after === about.text) return { problem: '바뀐 글이 없어요 — 글을 적어 주세요.' };
    body.text = typedText(kind, box);
    body.base_version = about.version;
    if (box.getAttribute('data-ds-money-ok') === body.text) body.money_ok = true;  // 금액 알림을 본 뒤 같은 글로 다시 누름
    return { problem: '', body: body };
  }

  /** 답 하나 — 서버 동작 하나(answer_question)로 한 번에 저장한다. */
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
      showChange(kind, box, (view.about || [])[0]);
      return;
    }
    lock(box, true);
    var made = answerBody(kind, box, (view.about || [])[0]);
    if (made.problem) { fail(box, status, made.problem); return; }
    if (kind !== 'knowledge') dom.setStatus(status, '회사 지식을 고치는 중…');
    var res = await dom.postJson(deps.urls.proposals + '/' + view.id + '/answer', made.body);
    if (!res.ok) { fail(box, status, res.error); return; }
    if (res.data && res.data.saved === false) {  // 금액 알림 — 아무것도 저장하지 않았다. 같은 글로 다시 누르면 저장
      box.setAttribute('data-ds-money-ok', made.body.text || '');
      lock(box, false);
      dom.setStatus(status, res.data.message);
      return;
    }
    var title = box.querySelector('.f-strong');
    await deps.reload();
    deps.done('정했어요 — ' + SAID[kind] + '.');
    if (window.FOMS_DS_INBOX_UNDO) {
      window.FOMS_DS_INBOX_UNDO.offer({ id: view.id, edit: (res.data && res.data.edit) || null, title: title ? title.textContent : '' });
    }
  }

  window.FOMS_DS_INBOX_QUESTION = { build: build, answer: answer };
})();

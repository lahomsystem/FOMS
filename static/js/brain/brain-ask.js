/**
 * 회사 지식 물어보기 화면(HAUD master brain 설계서 10절 · D88 · ⑤-5) — [data-brain-ask](회사 지식 '물어보기' 탭 · /brain/ask).
 *
 * - 첫 값: GET /api/brain/chat/state(물을 수 있나 · 남은 질문 수). 묻기: POST /api/brain/chat/ask {question} — 서버가 가림 →
 *   보기 범위 안 찾기 → 두뇌 → 근거 확인을 하고 답 · 근거 칩 · 확신을 준다. 새 답이 맨 위.
 * - 피드백: 도움 됨 · 안 됨 · 틀림(+ 고칠 말) = POST /api/brain/chat/questions/<번호>/feedback. 틀림이면 근거 항목에 신고가 붙고,
 *   카드를 열 수 있는 사람에게는 '고칠 말 제안(항목 카드)' 링크(이름 있는 액션 propose_edit — 챗봇은 지식을 쓰지 않는다).
 * - fetch 는 brain-dom.js requestJson 한 곳(try/catch + data.success 확인 · CSRF 는 공용 부트스트랩). 글은 textContent 만.
 */
(function () {
  'use strict';

  if (window.__FOMS_BRAIN_ASK_BOUND) return;
  var root = document.querySelector('[data-brain-ask]');
  if (!root) return;
  window.__FOMS_BRAIN_ASK_BOUND = true;

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_ASK_VIEW;
  var display = dom.safeJsonParse(root.getAttribute('data-display'), {});
  var urls = { state: root.getAttribute('data-state-url'), ask: root.getAttribute('data-ask-url'),
               feedback: root.getAttribute('data-feedback-url'), items: root.getAttribute('data-item-base') };
  var form = root.querySelector('[data-brain-ask-form]');
  var input = root.querySelector('[data-brain-ask-input]');
  var submit = root.querySelector('[data-brain-ask-submit]');
  var status = root.querySelector('[data-brain-ask-status]');
  var stateLine = root.querySelector('[data-brain-ask-state]');
  var left = root.querySelector('[data-brain-ask-left]');
  var log = root.querySelector('[data-brain-ask-log]');
  var loaded = false;
  var busy = false;

  function setAsking(on) {
    busy = on;
    if (submit) submit.disabled = on;
  }

  async function loadState() {
    loaded = true;
    var res = await dom.getJson(urls.state);
    if (!res.ok) {
      dom.setStatus(stateLine, res.error, 'error');
      return;
    }
    root.dispatchEvent(new CustomEvent('brain:ask-state', { detail: res.data }));
    dom.setStatus(stateLine, view.stateText(res.data));
    if (left) left.textContent = view.leftText(res.data.left_today);
    if (submit) submit.disabled = !res.data.can_ask;
  }

  function chipNode(c) {
    var node = dom.el(c.href ? 'a' : 'span', { cls: 'brain-chip brain-type--' + c.type,
                                               attrs: { href: c.href, title: c.meta || null } });
    node.appendChild(dom.icon(((display.types || {})[c.type] || {}).icon || 'fa-circle'));
    node.appendChild(document.createTextNode(c.name));
    if (c.meta) node.appendChild(dom.el('span', { cls: 'brain-ask__chip-date', text: ' · ' + c.meta }));
    return dom.el('li', { children: [node] });
  }

  function feedbackBar(data, v) {
    var bar = dom.el('div', { cls: 'brain-ask__feedback', attrs: { 'data-question': data.id } });
    v.feedback.forEach(function (f) {
      bar.appendChild(dom.el('button', { cls: 'brain-btn', text: f.label, attrs: { type: 'button', 'data-feedback': f.value } }));
    });
    var fix = dom.el('div', { cls: 'brain-ask__fix', attrs: { hidden: 'hidden', 'data-fix': '1' } });
    var label = 'brain-ask-fix-' + data.id;
    fix.appendChild(dom.el('label', { text: '무엇이 틀렸나요?', attrs: { for: label } }));
    fix.appendChild(dom.el('textarea', { cls: 'brain-ask__input', attrs: { id: label, maxlength: '500', rows: '2', 'data-fix-note': '1' } }));
    fix.appendChild(dom.el('button', { cls: 'brain-btn brain-btn--primary', text: '틀림 보내기',
                                       attrs: { type: 'button', 'data-fix-send': '1' } }));
    if (v.fixLink) {
      fix.appendChild(dom.el('a', { cls: 'brain-btn', text: '지식 고치기', attrs: { href: v.fixLink } }));
    }
    bar.appendChild(fix);
    bar.appendChild(dom.el('p', { cls: 'brain-status-line', attrs: { 'data-feedback-status': '1', role: 'status' } }));
    return bar;
  }

  function renderTurn(question, data) {
    var v = view.answerView(data, display, urls.items);
    var li = dom.el('li', { cls: 'brain-ask__turn ' + v.cls, attrs: { 'data-question-id': data.id } });
    li.appendChild(dom.el('p', { cls: 'brain-ask__q', text: '물음: ' + question }));
    var answer = dom.el('p', { cls: 'brain-ask__a' });
    if (v.badge) answer.appendChild(dom.el('span', { cls: 'brain-ask__badge', text: v.badge }));
    answer.appendChild(document.createTextNode(v.text));
    li.appendChild(answer);
    if (v.confidence) li.appendChild(dom.el('p', { cls: 'brain-ask__meta', text: v.confidence }));
    if (v.chips.length) {
      li.appendChild(dom.el('p', { cls: 'brain-ask__meta', text: '근거' }));
      li.appendChild(dom.el('ul', { cls: 'brain-ask__chips', children: v.chips.map(chipNode) }));
    }
    if (v.checks) li.appendChild(dom.el('p', { cls: 'brain-ask__checks', text: v.checks }));
    li.appendChild(feedbackBar(data, v));
    return li;
  }

  async function ask(question) {
    if (busy) return;
    setAsking(true);
    dom.setStatus(status, '찾아서 답하는 중…');
    var res = await dom.postJson(urls.ask, { question: question });
    setAsking(false);
    if (!res.ok) {
      dom.setStatus(status, res.error, 'error');
      return;
    }
    dom.setStatus(status, '');
    if (left) left.textContent = view.leftText(res.data.left_today);
    log.insertBefore(renderTurn(question, res.data), log.firstChild);
    if (input) input.value = '';
  }

  async function sendFeedback(bar, choice, note) {
    var body = view.feedbackBody(choice, note);
    var line = bar.querySelector('[data-feedback-status]');
    if (!body) return;
    dom.setStatus(line, '보내는 중…');
    var res = await dom.postJson(view.feedbackUrl(urls.feedback, bar.getAttribute('data-question')), body);
    if (!res.ok) {
      dom.setStatus(line, res.error, 'error');
      return;
    }
    bar.querySelectorAll('[data-feedback]').forEach(function (b) {
      b.classList.toggle('is-on', b.getAttribute('data-feedback') === choice);
    });
    dom.setStatus(line, choice === 'wrong'
      ? (res.data.raised && res.data.raised.length ? '고마워요 — 여러 사람이 틀렸다고 해 승인자에게 올렸어요.'
                                                   : '고마워요 — 틀림 신고를 남겼어요.')
      : '고마워요 — 기록했어요.');
  }

  if (form) {
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      var text = String(input ? input.value : '').trim();
      if (!text) {
        dom.setStatus(status, '물을 말을 적어 주세요.', 'error');
        return;
      }
      ask(text);
    });
  }

  if (log) {
    log.addEventListener('click', function (event) {
      var bar = event.target.closest('[data-question]');
      if (!bar || !log.contains(bar)) return;
      var pick = event.target.closest('[data-feedback]');
      var fix = bar.querySelector('[data-fix]');
      if (pick) {
        var choice = pick.getAttribute('data-feedback');
        if (choice === 'wrong') {
          fix.hidden = false;
          var note = fix.querySelector('[data-fix-note]');
          if (note) note.focus();
          return;
        }
        if (fix) fix.hidden = true;
        sendFeedback(bar, choice, '');
        return;
      }
      if (event.target.closest('[data-fix-send]')) {
        sendFeedback(bar, 'wrong', (fix.querySelector('[data-fix-note]') || {}).value || '');
      }
    });
  }

  var page = document.querySelector('[data-brain-page]');
  if (page && root.closest('#brain-tab-ask')) {
    page.addEventListener('brain:tab', function (event) {
      if (event.detail.tab === 'ask' && !loaded) loadState();
    });
  } else {
    document.addEventListener('DOMContentLoaded', loadState);
  }
})();

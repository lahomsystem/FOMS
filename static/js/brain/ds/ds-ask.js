/**
 * 새 물어보기 화면(판 ⑨ — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 3.7 · 5.4 · 5.5) — templates/brain/ds/ask.html 의 [data-ds-ask].
 *
 * - 첫 값: GET /api/brain/chat/state(물을 수 있나 · 남은 수 — ADMIN 은 설정 · 빈 지식, 'ds:ask-state' 로 ds-ask-admin.js 에 넘긴다) ·
 *   GET /api/brain/chat/history(내가 물은 것 — 오늘 · 지난 7일, 왼쪽 길잡이).
 * - 묻기: POST /api/brain/chat/ask {question} — 서버가 가림 → (erp_read 켬이면 주문 읽기) → 찾기 → 두뇌 → 코드 확인 → 기록.
 *   물음(서버가 준 가린 글 · 가린 갈래 · 수) · 답 카드를 아래에 잇고, 답에 erp 칸이 있으면 오른쪽 '이 답이 읽은 것'을 채운다.
 *   옆 창은 늘 그 자리에 있고 읽은 것이 없으면 빈 안내(점검 w2-16 — 가운데 폭이 흔들리지 않게). 답을 받으면 내 질문 목록을 다시 읽는다.
 * - 피드백: 도움 됨 · 도움 안 됨 · 틀림(+ 고칠 말) = POST /api/brain/chat/questions/<번호>/feedback(옛 화면과 같은 본문 · 같은 글).
 * - 왼쪽 줄을 누르면: 이 화면에서 물은 것이면 그 답으로, 아니면 그 질문의 물음 · 답을 다시 보인다(ds-ask-past.js — 다시 묻지
 *   않고 하루 수도 안 줄어든다). 주소 ?question=<번호>(팀 묻기 알림이 여는 곳)도 같은 길. 모름 답의 [○○팀에 묻기]도 ds-ask-past.js.
 * fetch 는 brain-dom.js 한 곳 · 글은 textContent 만 · 전역 듣개는 한 번만(window.__FOMS_DS_ASK_BOUND).
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_ASK_VIEW;
  var dv = window.FOMS_DS_ASK_VIEW;
  var turn = window.FOMS_DS_ASK_TURN;
  var past = window.FOMS_DS_ASK_PAST;
  var root = document.querySelector('[data-ds-ask]');
  if (!root || !dom || !view || !dv || !turn || !past || window.__FOMS_DS_ASK_BOUND) return;
  window.__FOMS_DS_ASK_BOUND = true;

  var display = dom.safeJsonParse(root.getAttribute('data-display'), {});
  var urls = { state: root.getAttribute('data-state-url'), ask: root.getAttribute('data-ask-url'),
               history: root.getAttribute('data-history-url'), feedback: root.getAttribute('data-feedback-url'),
               question: root.getAttribute('data-question-url'), team: root.getAttribute('data-team-url'),
               items: root.getAttribute('data-item-base') };
  var me = root.getAttribute('data-me') || '';
  var q = function (sel, base) { return (base || root).querySelector(sel); };
  var form = q('[data-ds-ask-form]');
  var input = q('[data-ds-ask-input]');
  var submit = q('[data-ds-ask-submit]');
  var status = q('[data-ds-ask-status]');
  var stateLine = q('[data-ds-ask-state]');
  var left = q('[data-ds-ask-left]');
  var log = q('[data-ds-ask-log]');
  var side = document.querySelector('[data-ds-ask-side]');
  var aside = document.querySelector('[data-ds-ask-aside]');
  var readBody = aside && q('[data-ds-ask-read]', aside);
  var readEmpty = readBody ? readBody.textContent.trim() : '';
  var reads = {};
  var busy = false;

  async function loadState() {
    var res = await dom.getJson(urls.state);
    if (!res.ok) {
      dom.setStatus(stateLine, res.error, 'error');
      return;
    }
    root.dispatchEvent(new CustomEvent('ds:ask-state', { detail: res.data }));
    dom.setStatus(stateLine, view.stateText(res.data));
    if (left) left.textContent = view.leftText(res.data.left_today);
    if (submit) submit.disabled = !res.data.can_ask;
  }

  function historyButton(item, full) {
    var btn = dom.el('button', { cls: 'f-nav-item fb-ask-item', attrs: { type: 'button', 'data-ds-ask-pick': item.id,
                                                                         title: [item.text, item.when].filter(Boolean).join(' · ') } });
    if (full) {
      btn.appendChild(dom.el('span', { cls: 'f-col f-gap4 f-grow', children: [
        dom.el('span', { cls: 'f-ellipsis', text: item.text }),
        dom.el('span', { cls: 'f-row-nw f-small', children: [turn.icon(item.icon), document.createTextNode(item.sub)] })] }));
    } else {
      btn.appendChild(turn.icon('chat', 'f-i-muted'));
      btn.appendChild(dom.el('span', { cls: 'f-ellipsis f-grow', text: item.text }));
    }
    return btn;
  }

  function renderHistory(data) {
    if (!side) return;
    var lists = dv.historyLists(data);
    [['[data-ds-ask-today]', lists.today, true], ['[data-ds-ask-week]', lists.week, false]].forEach(function (part) {
      var box = q(part[0], side);
      dom.clear(box);
      part[1].forEach(function (item) { box.appendChild(historyButton(item, part[2])); });
    });
    q('[data-ds-ask-today-count]', side).textContent = String(lists.count);
    dom.setStatus(q('[data-ds-ask-history-status]', side), lists.empty ? '아직 물은 것이 없어요.' : '');
    select(log.getAttribute('data-ds-ask-current'));
  }

  /** 내 질문 목록을 읽는다 — 돌려주는 값은 history data(못 읽으면 null). */
  async function loadHistory() {
    if (!urls.history) return null;
    var res = await dom.getJson(urls.history);
    if (!res.ok) {
      if (side) dom.setStatus(q('[data-ds-ask-history-status]', side), res.error, 'error');
      return null;
    }
    renderHistory(res.data);
    return res.data;
  }

  function select(id) {
    log.setAttribute('data-ds-ask-current', id || '');
    if (!side) return;
    side.querySelectorAll('[data-ds-ask-pick]').forEach(function (btn) {
      var on = !!id && btn.getAttribute('data-ds-ask-pick') === String(id);
      btn.classList.toggle('is-selected', on);
      if (on) btn.setAttribute('aria-current', 'true'); else btn.removeAttribute('aria-current');
    });
  }

  /** 옆 창 — 그 답이 주문을 읽었으면 채우고, 아니면 빈 안내(옆 창은 늘 그 자리 — 숨기지 않는다). */
  function showRead(id) {
    if (!readBody) return;
    var rv = id ? reads[id] : null;
    if (rv) {
      turn.fillRead(readBody, rv);
      return;
    }
    dom.clear(readBody);
    readBody.appendChild(dom.el('p', { cls: 'f-small f-muted', text: readEmpty }));
  }

  /** 지난 질문 하나를 다시 보인다(다시 묻지 않는다) — 이미 화면에 있으면 그리로. */
  async function openPast(id) {
    var card = log.querySelector('[data-question="' + id + '"]');
    select(id);
    showRead(id);
    if (card) {
      if (card.scrollIntoView) card.scrollIntoView({ block: 'nearest' });
      return;
    }
    dom.setStatus(status, '지난 질문을 불러오는 중…');
    var res = await past.load(urls.question, id);
    if (!res.ok) {
      dom.setStatus(status, res.error, 'error');
      return;
    }
    dom.setStatus(status, '');
    past.nodes(res.data, { display: display, items: urls.items, me: me }).forEach(function (node) { log.appendChild(node); });
    card = log.querySelector('[data-question="' + id + '"]');
    if (card && card.scrollIntoView) card.scrollIntoView({ block: 'nearest' });
  }

  async function ask(question) {
    if (busy) return;
    busy = true;
    if (submit) submit.disabled = true;
    dom.setStatus(status, '찾아서 답하는 중…');
    var started = window.performance ? window.performance.now() : Date.now();
    var res = await dom.postJson(urls.ask, { question: question });
    var elapsed = (window.performance ? window.performance.now() : Date.now()) - started;
    busy = false;
    if (submit) submit.disabled = false;
    if (!res.ok) {
      dom.setStatus(status, res.error, 'error');
      return;
    }
    var data = res.data;
    dom.setStatus(status, '');
    if (left) left.textContent = view.leftText(data.left_today);
    var qNode = turn.questionNode(data.question || question, dv.askedLine(me, dv.clockOf(), data.masked_count), data.masked);
    qNode.setAttribute('data-question-of', data.id);
    var card = turn.answerNode(data, { display: display, items: urls.items, elapsed: elapsed });
    log.appendChild(qNode);
    log.appendChild(card);
    reads[data.id] = dv.readView(data.erp);
    showRead(data.id);
    if (input) input.value = '';
    if (card.scrollIntoView) card.scrollIntoView({ block: 'nearest' });
    log.setAttribute('data-ds-ask-current', data.id);
    await loadHistory();
  }

  async function sendFeedback(card, choice, note) {
    var body = view.feedbackBody(choice, note);
    var line = q('[data-feedback-status]', card);
    if (!body) return;
    dom.setStatus(line, '보내는 중…');
    var res = await dom.postJson(view.feedbackUrl(urls.feedback, card.getAttribute('data-question')), body);
    if (!res.ok) {
      dom.setStatus(line, res.error, 'error');
      return;
    }
    card.querySelectorAll('[data-feedback]').forEach(function (b) {
      var on = b.getAttribute('data-feedback') === choice;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    dom.setStatus(line, choice === 'wrong'
      ? (res.data.raised && res.data.raised.length ? '고마워요 — 여러 사람이 틀렸다고 해 승인자에게 올렸어요.'
                                                   : '고마워요 — 틀림 신고를 남겼어요.')
      : '고마워요 — 기록했어요.');
  }

  function onLogClick(event) {
    var card = event.target.closest('[data-question]');
    if (!card || !log.contains(card)) return;
    var fix = q('[data-fix]', card);
    var pick = event.target.closest('[data-feedback]');
    if (pick) {
      var choice = pick.getAttribute('data-feedback');
      if (choice === 'wrong') {
        fix.hidden = false;
        q('[data-fix-note]', fix).focus();
        return;
      }
      fix.hidden = true;
      sendFeedback(card, choice, '');
      return;
    }
    var send = event.target.closest('[data-ds-ask-team-send]');
    if (send) {
      past.sendTeam(urls.team, card, send);
      return;
    }
    if (event.target.closest('[data-fix-send]')) {
      sendFeedback(card, 'wrong', (q('[data-fix-note]', fix) || {}).value || '');
      return;
    }
    if (event.target.closest('a, button, textarea')) return;
    var id = card.getAttribute('data-question');
    select(id);
    showRead(id);
  }

  function onSideClick(event) {
    var pick = event.target.closest('[data-ds-ask-pick]');
    if (pick) {
      openPast(pick.getAttribute('data-ds-ask-pick'));
      return;
    }
    if (event.target.closest('[data-ds-ask-new]')) {
      select(null);
      showRead(null);
      dom.setStatus(status, '');
      if (input) {
        input.value = '';
        input.focus();
      }
    }
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
  log.addEventListener('click', onLogClick);
  if (side) side.addEventListener('click', onSideClick);

  function start() {
    loadState();
    loadHistory();
    showRead(null);
    var asked = past.questionFromQuery(window.location.search);
    if (asked) openPast(asked);  // 팀 묻기 알림이 여는 질문
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();

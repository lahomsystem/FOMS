/**
 * 승인 대기 'AI 할 일 제안' 칸(T8 · 판 ⑥ · ⑫ — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 3.5 · 3.6 · 5.5) —
 * templates/brain/ds/partials/inbox_erp_section.html.
 *
 * - 읽기 GET /api/erp-actions/inbox 한 번 → PC 카드(셋까지 + 'n개 더 보기') · 왼쪽 AI 직원 수 · 폰 카드(폰 목록 맨 앞).
 *   수는 window.FOMS_DS_INBOX.setCount('actions', n) 으로 승인 대기 바탕(ds-inbox.js)에 알린다(숫자 띠 · '모두' · 위 줄).
 * - [자세히] · 폰 카드 제목 → GET /proposals/<번호> → 옆 창(FOMS_DS_INBOX.openAside). 주소 ?proposal=<번호> 면 처음부터 연다,
 *   ?agent=<직원> 이면 그 직원 제안만.
 * - [승인] → (카드에서 누르면 자세히를 먼저 읽어 기준 판 · 넣을 값 · 사유 · 손님 알림톡 줄을 본다 — 하나라도 있으면 옆 창)
 *   POST /approve. 409 ACTION_BASE_CHANGED 면 새 카드로
 *   옆 창을 다시 그리고 "제안 뒤 주문이 바뀌었어요 — 다시 봐 주세요". 실행 실패(200 · success 거짓)는 그 말 + 카드 [다시].
 * - [거절] → 까닭 칩 한 번 · [나중에] → POST /snooze.
 * 승인 대기 바탕보다 먼저 실리므로(문서 차례) 'ds:inbox-ready' 뒤에 시작한다. 요청은 brain-dom.js 한 곳 · 글은 textContent 만 ·
 * 전역 듣개는 한 번만(window.__FOMS_DS_INBOX_ERP_BOUND).
 */
(function () {
  'use strict';

  var section = document.querySelector('[data-erp-section]');
  if (!section || window.__FOMS_DS_INBOX_ERP_BOUND) return;
  window.__FOMS_DS_INBOX_ERP_BOUND = true;

  var FIRST = 3;
  var AGENT_ORDER = ['cs', 'schedule', 'ops'];
  var NOTICE_FIRST = '손님에게 알림톡이 나가요 — 확인한 뒤 승인해 주세요.';
  var api = section.getAttribute('data-erp-api') || '/api/erp-actions';
  var q = function (sel) { return section.querySelector(sel); };
  var parts = { status: q('[data-erp-status]'), cards: q('[data-erp-cards]'), count: q('[data-erp-count]'),
                moreRow: q('[data-erp-more-row]'), rest: q('[data-erp-rest]'), moreText: q('[data-erp-more-text]') };
  var state = { data: null, expanded: false, agent: fromQuery('agent', /^(cs|schedule|ops)$/), start: fromQuery('proposal', /^\d+$/),
                detail: null, shownAt: 0, busy: false, started: false };
  var card = window.FOMS_DS_INBOX_ERP_CARD;
  var aside = window.FOMS_DS_INBOX_ERP_ASIDE;

  function fromQuery(name, pattern) {
    var m = new RegExp('[?&]' + name + '=([^&]*)').exec(window.location.search || '');
    var value = m ? decodeURIComponent(m[1]) : '';
    return pattern.test(value) ? value : '';
  }

  function dom() { return window.FOMS_BRAIN_DOM; }
  function inbox() { return window.FOMS_DS_INBOX || null; }
  function isPhone() { return inbox() ? inbox().isPhone() : window.matchMedia('(max-width: 640px)').matches; }

  function ctx() {
    return { rejectCodes: (state.data && state.data.reject_codes) || [], today: card.todayText(), phone: isPhone(),
             selected: state.detail ? state.detail.id : null };
  }

  /** 알림 — PC 는 이 칸의 알림 줄, 폰은 승인 대기 알림 줄(이 칸은 폰에서 숨는다). */
  function say(text, kind) {
    var target = isPhone() ? document.querySelector('[data-ds-inbox-status]') : parts.status;
    dom().setStatus(target || parts.status, text, kind);
  }

  function awake() {
    return ((state.data && state.data.cards) || []).filter(function (c) { return !c.snoozed; });
  }

  function restLine(shown, all) {
    var left = {};
    all.slice(shown.length).forEach(function (c) { left[c.agent] = (left[c.agent] || 0) + 1; });
    var names = {};
    all.forEach(function (c) { names[c.agent] = c.agent_label; });
    var bits = AGENT_ORDER.filter(function (k) { return left[k]; }).map(function (k) { return names[k] + ' ' + left[k]; });
    return all.length + '개 중 ' + shown.length + '개 · 남은 것 ' + bits.join(' · ');
  }

  function renderPc(all) {
    var list = state.agent ? all.filter(function (c) { return c.agent === state.agent; }) : all;
    var shown = state.expanded ? list : list.slice(0, FIRST);
    dom().clear(parts.cards);
    if (!list.length) parts.cards.appendChild(dom().el('li', { cls: 'f-small f-muted fb-erp-empty', text: '결정할 AI 할 일 제안이 없어요.' }));
    shown.forEach(function (c) { parts.cards.appendChild(card.pcCard(c, ctx())); });
    parts.moreRow.hidden = shown.length >= list.length;
    parts.rest.textContent = parts.moreRow.hidden ? '' : restLine(shown, list);
    parts.moreText.textContent = (list.length - shown.length) + '개 더 보기';
    parts.count.textContent = String(list.length);
  }

  function renderNav() {
    var by = (state.data && state.data.counts && state.data.counts.by_agent) || {};
    Array.prototype.slice.call(document.querySelectorAll('[data-erp-agent-nav]')).forEach(function (item) {
      var key = item.getAttribute('data-erp-agent-nav');
      var n = item.querySelector('[data-erp-agent-count]');
      if (n) n.textContent = String(by[key] || 0);
      item.classList.toggle('fb-nav-item--muted', !by[key]);
      item.classList.toggle('is-selected', state.agent === key);
      if (state.agent === key) item.setAttribute('aria-current', 'page'); else item.removeAttribute('aria-current');
    });
    var all = document.querySelector('[data-ds-nav="inbox"]');
    if (all && state.agent) { all.classList.remove('is-selected'); all.removeAttribute('aria-current'); }
  }

  /** 폰 카드 — 승인 대기 폰 목록 맨 앞(바탕은 제 카드만 지우고 다시 넣는다). */
  function renderPhone(all) {
    var list = document.querySelector('[data-ds-phone-list]');
    if (!list) return;
    Array.prototype.slice.call(list.querySelectorAll('[data-ds-inbox-erp-card]')).forEach(function (n) { list.removeChild(n); });
    var anchor = list.firstChild;
    all.forEach(function (c) { list.insertBefore(card.phoneCard(c, ctx()), anchor); });
  }

  function render() {
    var all = awake();
    renderPc(all);
    renderNav();
    renderPhone(all);
    if (inbox()) inbox().setCount('actions', (state.data && state.data.counts && state.data.counts.total) || all.length);
  }

  async function load() {
    var res = await dom().getJson(api + '/inbox');
    if (!res.ok) { say(res.error, 'error'); return false; }
    state.data = res.data;
    render();
    return true;
  }

  function showDetail(detail, message, kind) {
    state.detail = detail;
    state.shownAt = window.performance.now();
    var node = aside.build(detail, ctx());
    if (inbox()) inbox().openAside(node);
    if (message) dom().setStatus(node.querySelector('[data-erp-card-status]'), message, kind);
    renderPc(awake());
    return node;
  }

  async function openDetail(id, message) {
    var res = await dom().getJson(api + '/proposals/' + encodeURIComponent(id));
    if (!res.ok) { say(res.error, 'error'); return null; }
    var node = showDetail(res.data, message);
    var focus = node.querySelector('[data-erp-act="close"]');
    if (focus && !message) focus.focus();
    return res.data;
  }

  function closeAside() {
    state.detail = null;
    if (inbox()) inbox().closeAside();
    renderPc(awake());
  }

  function viewMs() {
    return state.shownAt ? Math.round(window.performance.now() - state.shownAt) : null;
  }

  /** 결과 — 성공 · 실행 실패 · 기준 판 바뀜(새 카드) · 막힘 · 이미 처리됨. 목록은 다시 읽는다. */
  async function settle(res, where) {
    var data = res.data || {};
    if (res.ok) {
      closeAside();
      say(data.message || '승인했어요 — 실행됐어요.');
    } else if (res.status === 409 && data.code === 'ACTION_BASE_CHANGED' && data.card) {
      showDetail(data.card, card.BASE_CHANGED, 'error');
    } else if (where) {
      dom().setStatus(where, (data && data.reason) || res.error, 'error');
    } else {
      say(res.error, 'error');
    }
    await load();
  }

  async function approve(detail, node, withEdits) {
    var body = { base_version: detail.base_version, view_ms: viewMs() };
    if (node) {
      var form = node.querySelector('[data-erp-form]');
      if (withEdits || (form && !form.hidden)) body.edits = aside.edits(node, detail);
      var r = aside.reason(node);
      if (r.asked) { body.reason_code = r.code; body.reason_note = r.note || null; }
    }
    return dom().postJson(api + '/proposals/' + detail.id + '/approve', body);
  }

  /** 카드의 [승인](PC · 폰) — 자세히를 읽어 기준 판을 얻고, 넣을 값 · 사유가 필요하면 옆 창(칸을 펼쳐), 카드에 안 보이는
   *  손님 알림톡이 같이 나가면 옆 창(그 줄을 본 뒤 승인)을 연다. 알림톡을 쓸 수 없는 상태면 줄이 없어 지금처럼 바로 승인. */
  async function approveCard(id, line) {
    var res = await dom().getJson(api + '/proposals/' + encodeURIComponent(id));
    if (!res.ok) { dom().setStatus(line, res.error, 'error'); return; }
    var detail = res.data;
    var needs = aside.missing(detail) || !!(detail.change_reason && detail.change_reason.required);
    if (needs || aside.notice(detail)) {
      var node = showDetail(detail, needs ? '값을 고른 뒤 승인해 주세요.' : NOTICE_FIRST);
      if (needs) aside.showForm(node);
      return;
    }
    dom().setStatus(line, '승인하는 중…');
    await settle(await approve(detail, null, false), line);
  }

  async function post(id, verb, body, line) {
    var res = await dom().postJson(api + '/proposals/' + encodeURIComponent(id) + '/' + verb, body);
    if (!res.ok) { dom().setStatus(line, res.error, 'error'); if (res.status === 409 || res.status === 404) await load(); return; }
    if (state.detail && String(state.detail.id) === String(id)) closeAside();
    say(verb === 'reject' ? '거절했어요 — 같은 제안은 다시 오지 않아요.' : '나중에 볼게요 — 내일 아침에 다시 보여요.');
    await load();
  }

  function owner(button) {
    var inAside = button.closest('[data-erp-aside]');
    var host = inAside || button.closest('[data-erp-card]');
    var id = inAside ? inAside.getAttribute('data-erp-aside') : (host && host.getAttribute('data-erp-card'));
    return { id: id, aside: inAside, line: host ? host.querySelector('[data-erp-card-status]') : parts.status };
  }

  async function onAct(button) {
    var act = button.getAttribute('data-erp-act');
    var who = owner(button);
    if (act === 'more') { state.expanded = true; renderPc(awake()); return; }
    if (act === 'close') { closeAside(); return; }
    if (act === 'open') { await openDetail(who.id); return; }
    if (act === 'reject-open') {
      var box = button.closest('[data-erp-card]').querySelector('[data-erp-reject-box]');
      if (box) box.hidden = !box.hidden;
      return;
    }
    if (act === 'edit' && who.aside) { aside.showForm(who.aside); aside.refresh(who.aside, state.detail); return; }
    if (state.busy || !who.id) return;
    state.busy = true;
    try {
      if (act === 'reject') await post(who.id, 'reject', { code: button.getAttribute('data-erp-code'), view_ms: viewMs() }, who.line);
      else if (act === 'snooze') await post(who.id, 'snooze', {}, who.line);
      else if ((act === 'approve' || act === 'approve-edit') && who.aside && state.detail) {
        dom().setStatus(who.line, '승인하는 중…');
        await settle(await approve(state.detail, who.aside, act === 'approve-edit'), who.line);
      } else if (act === 'approve') await approveCard(who.id, who.line);
    } finally {
      state.busy = false;
    }
  }

  function onNav(link, event) {
    event.preventDefault();
    var key = link.getAttribute('data-erp-agent-nav');
    state.agent = state.agent === key ? '' : key;
    state.expanded = false;
    render();
  }

  function bind() {
    document.addEventListener('click', function (event) {
      var t = event.target;
      if (!t || !t.closest) return;
      var nav = t.closest('[data-erp-agent-nav]');
      if (nav && state.data && !isPhone()) { onNav(nav, event); return; }
      if (t.closest('[data-ds-nav="inbox"]') && state.agent) { state.agent = ''; render(); }
      var button = t.closest('[data-erp-act]');
      if (button && !button.disabled && button.closest('[data-erp-section], [data-erp-aside], [data-ds-inbox-erp-card]')) onAct(button);
    });
    var refreshForm = function (event) {
      var node = event.target && event.target.closest ? event.target.closest('[data-erp-aside]') : null;
      if (node && state.detail) aside.refresh(node, state.detail);
    };
    document.addEventListener('input', refreshForm);
    document.addEventListener('change', refreshForm);
    document.addEventListener('keydown', function (event) {  // Esc 는 바탕이 옆 창을 닫는다 — 고른 카드 표시만 지운다
      if (event.key === 'Escape' && state.detail) { state.detail = null; renderPc(awake()); }
    });
    window.matchMedia('(max-width: 640px)').addEventListener('change', function () { if (state.data) render(); });
  }

  async function start() {
    if (state.started || !dom() || !card || !aside) return;
    state.started = true;
    bind();
    if (await load() && state.start) await openDetail(state.start);
  }

  var root = document.querySelector('[data-ds-inbox]');
  if (root && root.getAttribute('data-ds-inbox-ready') === '1') start();
  else {
    if (root) root.addEventListener('ds:inbox-ready', start, { once: true });
    document.addEventListener('DOMContentLoaded', start, { once: true });
  }
})();

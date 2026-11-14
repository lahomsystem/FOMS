/**
 * AI 직원 'AI 시험' 칸(판 ⑪ — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 3.15 · D209) — partials/agents_evals.html 의 [data-ds-evals].
 *
 * - ds-agents.js 가 직원을 그릴 때마다 내는 document 'ds:agents-detail' 이벤트({key, data})를 듣는다. 상담 AI(cs)면 data.evals 로
 *   줄 셋(막대 <progress> · 결과 글 · 꼬리표) · 마지막 시험 줄을 그리고, 틀린 차례(번호 · 까닭)는 T10 의 '최근 실패' 목록 끝에
 *   붙인다. 다른 직원이면 안내 한 줄.
 * - ADMIN(data-run-url 이 있을 때만): 머리 단추 자리([data-ds-agents-actions])에 [시험 다시 돌리기] — 도는 중 · 막힘이면 꺼짐.
 *   누르면 POST data-run-url → 다시 읽기. 도는 중일 때만 GET data-detail-url 을 15초마다(화면이 보일 때만 · 다른 직원으로 가거나
 *   화면을 떠나면 멈춤 · 세 번 잇달아 못 읽으면 멈춤). 돈 상한 · 묶음 크기 칸은 POST data-settings-url → 다시 읽기.
 * - 이 조각은 본문 안이라 brain-dom.js 보다 먼저 실릴 수 있다 — 듣개만 바로 걸고 그리기는 이벤트 때 window.FOMS_BRAIN_DOM 을 쓴다.
 * fetch 는 brain-dom.js 한 곳 · 글은 textContent 만 · 듣개는 한 번만(window.__FOMS_DS_EVALS_BOUND).
 */
(function () {
  'use strict';

  if (window.__FOMS_DS_EVALS_BOUND) return;
  window.__FOMS_DS_EVALS_BOUND = true;

  var POLL_MS = 15000;
  var MAX_FAILS = 3;
  var FIELDS = ['past_size', 'risk_size', 'past_target_pct'];
  var state = { key: '', evals: null, timer: 0, busy: false, fails: 0 };

  function dom() { return window.FOMS_BRAIN_DOM; }
  function root() { return document.querySelector('[data-ds-evals]'); }
  function part(name) {
    var box = root();
    return box ? box.querySelector('[data-ds-evals-' + name + ']') : null;
  }

  /** 아이콘(장식). */
  function icon(cls, extra) {
    return dom().el('span', { cls: 'f-i ' + cls + (extra ? ' ' + extra : ''), attrs: { 'aria-hidden': 'true' } });
  }

  /** 알림 줄 — 오류면 빨강. */
  function note(text, isError) {
    var node = part('note');
    if (!node) return;
    node.textContent = text || '';
    node.hidden = !text;
    node.classList.toggle('is-error', Boolean(isError));
  }

  function stopPoll() {
    if (state.timer) window.clearTimeout(state.timer);
    state.timer = 0;
  }

  /** 도는 중이고 · 상담 AI 를 보고 · 화면이 보일 때만 다음 읽기를 건다. */
  function schedulePoll() {
    stopPoll();
    if (!state.evals || !state.evals.running || state.key !== 'cs' || state.fails >= MAX_FAILS) return;
    if (document.visibilityState === 'hidden') return;
    state.timer = window.setTimeout(refresh, POLL_MS);
  }

  /** GET data-detail-url → evals 만 다시 그린다. */
  async function refresh() {
    state.timer = 0;
    var box = root();
    if (!box || state.key !== 'cs') return;
    var res = await dom().getJson(box.getAttribute('data-detail-url'));
    if (state.key !== 'cs') return;
    if (res.ok && res.data && res.data.evals) {
      state.fails = 0;
      draw(res.data.evals);
      return;
    }
    state.fails += 1;
    note(res.error || '읽지 못했어요.', true);
    schedulePoll();
  }

  /** 줄 하나 — 이름 · 막대 · 결과 글 · 꼬리표. */
  function row(item) {
    var el = dom().el;
    var tone = item.verdict.tone;
    return el('div', { cls: 'fb-evals-row', attrs: { 'data-ds-evals-row': item.key }, children: [
      el('span', { cls: 'f-strong', text: item.label }),
      el('progress', { cls: 'fb-evals-bar is-' + tone,
                       attrs: { max: '100', value: String(item.pct === null ? 0 : item.pct), 'aria-label': item.label } }),
      el('span', { cls: 'f-small', text: item.text }),
      el('span', { cls: 'f-tag f-tag-minimal f-tag-' + tone + ' fb-evals-tag', text: item.verdict.text })] });
  }

  /** 마지막 시험 줄 — 도는 중이면 진행, 아니면 때 · 상태(까닭) · 모델 · (ADMIN 만) 쓴 돈. */
  function lastLine(last, running) {
    var box = part('last');
    if (!box) return;
    dom().clear(box);
    if (!last) {
      box.hidden = true;
      return;
    }
    var parts = running ? ['도는 중이에요', last.progress]
      : ['마지막 시험 ' + (last.at || ''), last.status_label + (last.reason ? '(' + last.reason + ')' : '')];
    if (last.model) parts.push(last.model);
    if (last.cost) parts.push('쓴 돈 ' + last.cost);
    box.appendChild(icon(running ? 'i-refresh' : 'i-time'));
    box.appendChild(dom().el('span', { text: parts.join(' · ') }));
    box.hidden = false;
  }

  /** 틀린 차례를 '최근 실패' 목록(T10) 끝에 — 앞에 붙인 것은 걷고 새로. */
  function failures(items) {
    var list = document.querySelector('[data-ds-agents-failures]');
    if (!list) return;
    Array.prototype.slice.call(list.querySelectorAll('[data-ds-evals-failure]')).forEach(function (li) {
      list.removeChild(li);
    });
    if (items.length && !list.querySelector('.i-cross')) dom().clear(list);  // '실패가 없어요' 한 줄을 걷는다
    if (!items.length && !list.firstChild) {
      list.appendChild(dom().el('li', { cls: 'f-small f-muted', text: '지난 2주 실패가 없어요.' }));
    }
    items.forEach(function (item) {
      var li = dom().el('li', { cls: 'f-row-nw', attrs: { 'data-ds-evals-failure': item.code } });
      li.appendChild(icon('i-cross', 'f-i-danger'));
      li.appendChild(dom().el('span', { text: item.label }));
      li.appendChild(dom().el('span', { cls: 'f-small f-muted', text: item.reason }));
      list.appendChild(li);
    });
  }

  /** 설정 칸(ADMIN) — 고치는 중이 아니면 저장된 값으로 채운다. */
  function fillForm(settings) {
    var form = part('form');
    if (!form) return;
    form.hidden = !settings;
    if (!settings || form.contains(document.activeElement)) return;
    form.elements.cap_usd.value = String(settings.cap_usd);
    FIELDS.forEach(function (name) { form.elements[name].value = String(settings[name]); });
  }

  /** [시험 다시 돌리기] — ADMIN 이고 상담 AI 일 때만 보인다. 도는 중 · 막힘 · 보내는 중이면 꺼짐. */
  function paint() {
    var box = root();
    var holder = document.querySelector('[data-ds-agents-actions]');
    if (!box || !holder || !box.getAttribute('data-run-url')) return;
    var button = holder.querySelector('[data-ds-evals-run]');
    if (!button) {
      button = dom().el('button', { cls: 'f-btn f-btn-primary', attrs: { type: 'button', 'data-ds-evals-run': '' } });
      button.appendChild(icon('i-play'));
      button.appendChild(dom().el('span', { attrs: { 'data-ds-evals-run-label': '' } }));
      button.addEventListener('click', run);
      holder.appendChild(button);
    }
    var evals = state.evals;
    var running = Boolean(evals && evals.running);
    button.hidden = state.key !== 'cs' || !evals || !evals.can_run;
    button.disabled = running || state.busy || Boolean(evals && evals.blocked);
    button.querySelector('[data-ds-evals-run-label]').textContent = running ? '도는 중이에요…' : '시험 다시 돌리기';
  }

  /** 상담 AI 의 evals 로 칸 전체를 그린다. */
  function draw(evals) {
    state.evals = evals;
    var rows = part('rows');
    dom().clear(rows);
    (evals.rows || []).forEach(function (item) { rows.appendChild(row(item)); });
    rows.hidden = false;
    lastLine(evals.last, evals.running);
    failures(evals.failures || []);
    note(evals.blocked ? evals.blocked.message : '');
    fillForm(evals.settings || null);
    paint();
    schedulePoll();
  }

  /** 다른 직원 — 상담 AI 말고는 아직 시험 묶음이 없다. */
  function other() {
    state.evals = null;
    stopPoll();
    var rows = part('rows');
    dom().clear(rows);
    rows.hidden = true;
    part('last').hidden = true;
    fillForm(null);
    note('이 직원은 아직 시험 묶음이 없어요.');
    paint();
  }

  async function run() {
    var box = root();
    if (!box || state.busy) return;
    state.busy = true;
    paint();
    var res = await dom().postJson(box.getAttribute('data-run-url'), {});
    state.busy = false;
    if (!res.ok) {
      note(res.error || '돌리지 못했어요.', true);
      paint();
      return;
    }
    state.fails = 0;
    await refresh();
  }

  async function save(event) {
    event.preventDefault();
    var box = root();
    var form = part('form');
    if (!box || !form || state.busy) return;
    var body = { cap_usd: form.elements.cap_usd.value.trim() };
    FIELDS.forEach(function (name) { body[name] = Number(form.elements[name].value || 0); });
    state.busy = true;
    var res = await dom().postJson(box.getAttribute('data-settings-url'), body);
    state.busy = false;
    if (!res.ok) {
      note(res.error || '저장하지 못했어요.', true);
      return;
    }
    if (document.activeElement && form.contains(document.activeElement)) document.activeElement.blur();
    await refresh();
    if (!(state.evals && state.evals.blocked)) note('시험 설정을 저장했어요.');
  }

  var form = part('form');
  if (form) form.addEventListener('submit', save);
  document.addEventListener('ds:agents-detail', function (event) {
    var detail = event.detail || {};
    state.key = detail.key || '';
    state.fails = 0;
    stopPoll();
    if (!root() || !dom()) return;
    if (state.key === 'cs' && detail.data && detail.data.evals) draw(detail.data.evals);
    else other();
  });
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') stopPoll();
    else schedulePoll();
  });
  window.addEventListener('pagehide', stopPoll);
})();

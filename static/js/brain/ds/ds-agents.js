/**
 * AI 직원 화면(판 ⑪ — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 3.10) — templates/brain/ds/agents.html 의 [data-ds-agents].
 *
 * - 첫 값 GET /api/ai-staff(직원 다섯 · 상태 꼬리표) → 왼쪽 목록. 고른 직원(주소 ?agent= · 없으면 첫 직원)은
 *   GET /api/ai-staff/<열쇠> 로 읽어 가운데 · 오른쪽을 그린다. 고른 것은 주소(?tab=agents&agent=)에 남긴다.
 * - 수준 고치기(ADMIN 만 — data-levels-url 이 있을 때): 할 일 표의 고르기를 바꾸면 POST /api/ai-staff/levels
 *   {"levels": {"<직원>": {"<할 일>": n}}} → 목록 · 자세히를 다시 읽는다. 실패하면 알림 줄에 서버가 정한 말.
 * - 다 그리면 document 에 'ds:agents-detail' 이벤트({key, data}) — 'AI 시험' 칸(T16)이 듣는다.
 * fetch 는 brain-dom.js 한 곳 · 글은 textContent 만 · 듣개는 한 번만(window.__FOMS_DS_AGENTS_BOUND).
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var kit = window.FOMS_DS_AGENTS_KIT;
  var root = document.querySelector('[data-ds-agents]');
  if (!root || !dom || !kit || window.__FOMS_DS_AGENTS_BOUND) return;
  window.__FOMS_DS_AGENTS_BOUND = true;

  var listUrl = root.getAttribute('data-list-url') || '/api/ai-staff';
  var levelsUrl = root.getAttribute('data-levels-url') || '';
  var pageUrl = root.getAttribute('data-page-url') || '/brain';
  var status = root.querySelector('[data-ds-agents-status]');
  var side = document.querySelector('[data-ds-agents-side]');
  var nav = side && side.querySelector('[data-ds-agents-nav]');
  var heading = side && side.querySelector('[data-ds-agents-heading]');
  var aside = document.querySelector('[data-ds-agents-aside]');
  var refs = {
    name: root.querySelector('[data-ds-agents-name]'), tags: root.querySelector('[data-ds-agents-tags]'),
    about: root.querySelector('[data-ds-agents-about]'), readsNote: root.querySelector('[data-ds-agents-reads-note]'),
    reads: root.querySelector('[data-ds-agents-reads]'), tools: root.querySelector('[data-ds-agents-tools]'),
    duties: root.querySelector('[data-ds-agents-duties]'), failures: root.querySelector('[data-ds-agents-failures]'),
    usage: root.querySelector('[data-ds-agents-usage]')
  };
  var runRefs = aside ? {
    list: aside.querySelector('[data-ds-agents-trace]'), sum: aside.querySelector('[data-ds-agents-run-sum]'),
    text: aside.querySelector('[data-ds-agents-run-text]'), title: aside.querySelector('[data-ds-agents-run-title]'),
    foot: aside.querySelector('[data-ds-agents-foot]')
  } : null;
  var state = { agents: [], current: '', seq: 0, saving: false };

  function href(key) {
    return pageUrl + '?tab=agents&agent=' + encodeURIComponent(key);
  }

  function drawNav() {
    if (!nav) return;
    dom.clear(nav);
    state.agents.forEach(function (agent) {
      nav.appendChild(kit.navItem(agent, agent.key === state.current, href(agent.key)));
    });
    if (heading) heading.textContent = 'AI 직원 ' + state.agents.length;
  }

  /** 목록 읽기 — 못 읽으면 거짓(알림 줄에 까닭). */
  async function loadList() {
    var res = await dom.getJson(listUrl);
    if (!res.ok) {
      dom.setStatus(status, res.error || '읽지 못했어요.', 'error');
      return false;
    }
    state.agents = res.data.agents || [];
    drawNav();
    return true;
  }

  function draw(data) {
    kit.head(refs, data);
    refs.readsNote.textContent = data.reads_note || '';
    kit.reads(refs.reads, refs.tools, data);
    kit.duties(refs.duties, data.duties || []);
    kit.failures(refs.failures, data.failures || []);
    kit.usage(refs.usage, data.usage || {});
    if (runRefs) kit.trace(runRefs, data.run, data.foot);
    document.dispatchEvent(new CustomEvent('ds:agents-detail', { detail: { key: data.key, data: data } }));
  }

  /** 직원 하나 열기 — 늦게 온 옛 답은 버린다. */
  async function open(key) {
    state.current = key;
    drawNav();
    if (window.history && window.history.replaceState) window.history.replaceState(null, '', href(key));
    var mine = ++state.seq;
    dom.setStatus(status, '불러오는 중이에요…');
    var res = await dom.getJson(listUrl + '/' + encodeURIComponent(key));
    if (mine !== state.seq) return false;
    if (!res.ok) {
      dom.setStatus(status, res.error || '읽지 못했어요.', 'error');
      return false;
    }
    dom.setStatus(status, '');
    draw(res.data);
    return true;
  }

  /** 수준 하나 저장(ADMIN 만) → 목록 · 자세히 다시 읽기. */
  async function saveLevel(select) {
    if (!levelsUrl || state.saving) return;
    var body = { levels: {} };
    body.levels[state.current] = {};
    body.levels[state.current][select.getAttribute('data-ds-agents-level')] = Number(select.value);
    state.saving = true;
    select.disabled = true;
    dom.setStatus(status, '저장하는 중이에요…');
    var res = await dom.postJson(levelsUrl, body);
    state.saving = false;
    select.disabled = false;
    if (!res.ok) {
      await open(state.current);
      dom.setStatus(status, res.error || '저장하지 못했어요.', 'error');
      return;
    }
    await loadList();
    if (await open(state.current)) dom.setStatus(status, '수준을 저장했어요.');
  }

  if (nav) {
    nav.addEventListener('click', function (event) {
      var link = event.target.closest('[data-ds-agent]');
      if (!link || event.metaKey || event.ctrlKey || event.shiftKey) return;
      event.preventDefault();
      open(link.getAttribute('data-ds-agent'));
    });
  }
  if (refs.duties) {
    refs.duties.addEventListener('change', function (event) {
      var select = event.target.closest('[data-ds-agents-level]');
      if (select) saveLevel(select);
    });
  }

  (async function boot() {
    if (!(await loadList()) || !state.agents.length) return;
    var start = root.getAttribute('data-start') || '';
    var known = state.agents.some(function (agent) { return agent.key === start; });
    await open(known ? start : state.agents[0].key);
  })();
})();

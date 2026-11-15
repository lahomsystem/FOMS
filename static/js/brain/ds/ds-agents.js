/**
 * AI 직원 화면(판 ⑪ — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 3.10) — templates/brain/ds/agents.html 의 [data-ds-agents].
 *
 * - 첫 값 GET /api/ai-staff(직원 다섯 · 상태 꼬리표) → 왼쪽 목록. 고른 직원(주소 ?agent= · 없으면 첫 직원)은
 *   GET /api/ai-staff/<열쇠> 로 읽어 가운데 · 오른쪽을 그린다. 고른 것은 주소(?tab=agents&agent=)에 남긴다.
 * - 수준 고치기(ADMIN 만 — data-levels-url 이 있을 때): 할 일 표의 고르기를 바꾸면 POST /api/ai-staff/levels
 *   {"levels": {"<직원>": {"<할 일>": n}}} → 목록 · 자세히를 다시 읽는다. 실패하면 알림 줄에 서버가 정한 말.
 *   바꾼 줄에는 '저장했어요 · [되돌리기]' 한 줄(확인 창 없이 바로 저장되므로 — 점검 2차 의견). 되돌리기는 앞 값을 같은 길로 저장.
 * - 지시문 보기(ADMIN 만 — data-prompt-url 이 있을 때, D233): GET /api/ai-staff/<열쇠>/instructions → 읽기만 하는 창(<dialog>).
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
  var promptUrl = root.getAttribute('data-prompt-url') || '';
  var promptBox = root.querySelector('[data-ds-agents-prompt]');
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
    foot: aside.querySelector('[data-ds-agents-foot]'), who: aside.querySelector('[data-ds-agents-run-who]')
  } : null;
  var state = { agents: [], current: '', seq: 0, saving: false, levels: {}, saved: null };

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

  /** 바꾼 줄의 '저장했어요 · [되돌리기]'(되돌린 뒤에는 '되돌렸어요'만) — 그 직원 그 할 일 줄에만. */
  function drawSaved() {
    var saved = state.saved;
    if (!saved || saved.agent !== state.current || !refs.duties) return;
    var row = refs.duties.querySelector('[data-ds-agents-duty="' + saved.duty + '"]');
    var cell = row && row.children[0];  // 이름 칸 아래 — 수준 칸 폭을 흔들지 않는다
    if (!cell) return;
    var line = dom.el('div', { cls: 'f-small f-muted fb-agents-saved', attrs: { role: 'status' },
                               children: [dom.el('span', { text: saved.undone ? '되돌렸어요' : '저장했어요' })] });
    if (!saved.undone) {
      line.appendChild(dom.el('span', { text: '·', attrs: { 'aria-hidden': 'true' } }));
      line.appendChild(dom.el('button', { cls: 'f-btn f-btn-minimal f-btn-small', text: '되돌리기',
                                          attrs: { type: 'button', 'data-ds-agents-undo': '' } }));
    }
    cell.appendChild(line);
  }

  function draw(data) {
    kit.head(refs, data);
    refs.readsNote.textContent = data.reads_note || '';
    kit.reads(refs.reads, refs.tools, data);
    kit.duties(refs.duties, data.duties || []);
    state.levels = {};
    (data.duties || []).forEach(function (row) { state.levels[row.key] = row.level; });
    drawSaved();
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

  /** 수준 하나 저장(ADMIN 만) → 목록 · 자세히 다시 읽기 → 바꾼 줄에 '저장했어요 · 되돌리기'. undo 면 앞 값으로 되돌린 것. */
  async function saveLevel(duty, value, control, undo) {
    if (!levelsUrl || state.saving) return;
    var body = { levels: {} };
    var agent = state.current;
    var before = state.levels[duty];
    body.levels[agent] = {};
    body.levels[agent][duty] = value;
    state.saving = true;
    if (control) control.disabled = true;
    dom.setStatus(status, '저장하는 중이에요…');
    var res = await dom.postJson(levelsUrl, body);
    state.saving = false;
    if (control) control.disabled = false;
    if (!res.ok) {
      await open(agent);
      dom.setStatus(status, res.error || '저장하지 못했어요.', 'error');
      return;
    }
    state.saved = undo ? { agent: agent, duty: duty, undone: true }
      : { agent: agent, duty: duty, from: before, undone: false };
    await loadList();
    await open(agent);
  }

  /** 지시문 보기 — 읽기만 하는 창. 못 읽으면 알림 줄에 서버가 정한 말. */
  async function showPrompt() {
    if (!promptUrl || !promptBox) return;
    var res = await dom.getJson(promptUrl.replace('__KEY__', encodeURIComponent(state.current)));
    if (!res.ok || !res.data) {
      dom.setStatus(status, res.error || '지시문을 읽지 못했어요.', 'error');
      return;
    }
    promptBox.querySelector('[data-ds-agents-prompt-title]').textContent = res.data.label + ' 지시문';
    promptBox.querySelector('[data-ds-agents-prompt-note]').textContent = res.data.note || '';
    var body = promptBox.querySelector('[data-ds-agents-prompt-body]');
    dom.clear(body);
    (res.data.sections || []).forEach(function (part) {
      body.appendChild(dom.el('h2', { cls: 'f-h6', text: part.title }));
      body.appendChild(dom.el('pre', { cls: 'fb-agents-prompt__text', text: part.text }));
    });
    if (typeof promptBox.showModal === 'function') promptBox.showModal();
    else promptBox.setAttribute('open', '');
  }

  if (nav) {
    nav.addEventListener('click', function (event) {
      var link = event.target.closest('[data-ds-agent]');
      if (!link || event.metaKey || event.ctrlKey || event.shiftKey) return;
      event.preventDefault();
      state.saved = null;
      open(link.getAttribute('data-ds-agent'));
    });
  }
  if (refs.duties) {
    refs.duties.addEventListener('change', function (event) {
      var select = event.target.closest('[data-ds-agents-level]');
      if (select) saveLevel(select.getAttribute('data-ds-agents-level'), Number(select.value), select, false);
    });
    refs.duties.addEventListener('click', function (event) {
      var undo = event.target.closest('[data-ds-agents-undo]');
      var saved = state.saved;
      if (!undo || !saved || saved.undone || saved.from === null || saved.from === undefined) return;
      saveLevel(saved.duty, saved.from, undo, true);
    });
  }
  var promptOpen = root.querySelector('[data-ds-agents-prompt-open]');
  if (promptOpen) promptOpen.addEventListener('click', showPrompt);
  if (promptBox) {
    promptBox.querySelector('[data-ds-agents-prompt-close]').addEventListener('click', function () {
      if (typeof promptBox.close === 'function') promptBox.close();
      else promptBox.removeAttribute('open');
    });
  }

  (async function boot() {
    if (!(await loadList()) || !state.agents.length) return;
    var start = root.getAttribute('data-start') || '';
    var known = state.agents.some(function (agent) { return agent.key === start; });
    await open(known ? start : state.agents[0].key);
  })();
})();

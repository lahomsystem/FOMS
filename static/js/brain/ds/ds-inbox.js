/**
 * 새 승인 대기 화면 바탕(설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 5.3 · 5.4 · 5.5 · 판 ⑥ · ⑫) — templates/brain/ds/inbox.html.
 *
 * - 읽기 GET /api/brain/inbox 한 번 → 왼쪽 길잡이 수(묶음 ① ~ ⑥ · 나중에 볼 것 — 0 은 흐리게) · 숫자 띠 · 묶음 줄 · 카드.
 *   다시 확인 · 판 보기에서도 길잡이 수를 채운다(지식 칸을 여는 사람만 — data-inbox-url 이 있을 때).
 * - PC: 첫 화면은 묶음마다 한 줄(제목 · 수 · 설명 · 첫 장 · 어림 · 열기) + 빈 묶음 한 줄 + 등급 A 모두 승인. 묶음을 열면 그
 *   묶음 카드만(표 묶음은 표 한 장 · ③ 은 질문 카드), 연 묶음은 주소(?tab=inbox&bin=)에 남는다(F07). '나중에'로 접은 카드는
 *   '나중에 볼 것'(이 탭에서만 기억 — 서버 쓰기 없음).
 * - 폰(640px 아래): ds-inbox-phone.js — 폭이 바뀌면 다시 그린다.
 * - T8(AI 할 일 제안)과의 약속: window.FOMS_DS_INBOX = { setCount(kind, n), openAside(node), closeAside(), isPhone() }
 *   (kind 'knowledge' · 'actions' — 숫자 띠와 '모두' 수를 다시 센다) · 준비되면 뿌리 [data-ds-inbox] 에 'ds:inbox-ready'
 *   (bubbles · 늦게 실린 스크립트는 data-ds-inbox-ready="1" 을 본다) · 옆 창 [data-ds-inbox-aside] · 폰 목록 [data-ds-phone-list].
 * 글은 textContent 만 · 요청은 brain-dom.js 한 곳 · 전역 듣개는 한 번만(window.__FOMS_DS_INBOX_BOUND).
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var review = window.FOMS_BRAIN_REVIEW;
  var iv = window.FOMS_DS_INBOX_VIEW;
  var kit = window.FOMS_DS_INBOX_KIT;
  if (!dom || !review || !iv || !kit || window.__FOMS_DS_INBOX_BOUND) return;
  var c = kit.ctx();
  if (!c) return;
  window.__FOMS_DS_INBOX_BOUND = true;

  var root = c.root;
  var shell = root.closest('[data-ds-shell]') || document.body;
  var cardKit = window.FOMS_DS_INBOX_CARD;
  var tableKit = window.FOMS_DS_INBOX_TABLE;
  var questionKit = window.FOMS_DS_INBOX_QUESTION;
  var phoneKit = window.FOMS_DS_INBOX_PHONE;
  var phoneQuery = window.matchMedia('(max-width: 640px)');
  var q = function (sel) { return root.querySelector(sel); };
  var parts = { status: q('[data-ds-inbox-status]'), bins: q('[data-ds-inbox-bins]'), open: q('[data-ds-inbox-open]'),
                cards: q('[data-ds-inbox-cards]'), laterBox: q('[data-ds-inbox-later-box]'), later: q('[data-ds-inbox-later]'),
                laterTitle: q('[data-ds-inbox-later-title]'), title: q('[data-ds-inbox-title]'), count: q('[data-ds-inbox-know-count]'),
                sub: q('[data-ds-inbox-sub]'), back: q('[data-ds-inbox-back]'), bulk: q('[data-ds-inbox-bulk]'),
                bulkText: q('[data-ds-inbox-bulk-text]'), ai: q('[data-ds-inbox-ai]'), erp: q('[data-ds-inbox-erp]') };
  var data = null;
  var counts = { knowledge: Number(root.getAttribute('data-knowledge-count')) || 0, actions: 0 };  // 서버가 센 수로 시작
  var actionsKnown = false;
  var openBin = c.view === 'inbox' && window.location ? iv.fromQuery(window.location.search) : '';
  var laterKey = 'foms-ds-inbox-later:' + (shell.getAttribute('data-ds-uid') || 'anon');
  var deferred = readDeferred();

  function readDeferred() {
    var out = {};
    try {
      JSON.parse(window.sessionStorage.getItem(laterKey) || '[]').forEach(function (id) { out[id] = true; });
    } catch (e) {
      return {};  // 저장 막힘 = 이 화면에서만 기억
    }
    return out;
  }

  function saveDeferred() {
    try {
      window.sessionStorage.setItem(laterKey, JSON.stringify(Object.keys(deferred)));
    } catch (e) {
      return;  // 저장 막힘 — 이 화면에서는 그대로 접혀 있다
    }
  }

  function isPhone() {
    return phoneQuery.matches;
  }

  function allCards() {
    return (data && data.cards) || [];
  }

  function findView(changeId) {
    var id = Number(changeId);
    var cards = allCards();
    for (var i = 0; i < cards.length; i += 1) {
      var views = [cards[i].main].concat(cards[i].attached);
      for (var j = 0; j < views.length; j += 1) if (views[j].id === id) return views[j];
    }
    return null;
  }

  function status(text, kind) {
    dom.setStatus(parts.status, text, kind);
  }

  function setText(sel, text) {
    var node = document.querySelector(sel);
    if (node) node.textContent = String(text);
  }

  /** 숫자 띠 · 위 줄 수 — AI 할 일 제안 수는 T8 이 알려 준 뒤에만 보인다. */
  function refreshCounts() {
    var totals = iv.stripTotals(allCards(), counts.actions);
    var today = counts.knowledge + totals.actions;
    setText('[data-ds-inbox-stat="today"]', today);
    setText('[data-ds-inbox-stat="knowledge"]', counts.knowledge);
    setText('[data-ds-inbox-stat="actions"]', totals.actions);
    if (data || !c.urls.inbox) setText('[data-ds-inbox-stat="minutes"]', totals.minutes);  // 카드를 읽은 뒤에만
    var box = document.querySelector('[data-ds-inbox-stat-box="actions"]');
    if (box) box.hidden = !actionsKnown;
    var shellKit = window.FOMS_DS_SHELL;
    if (shellKit && (actionsKnown || !shell.hasAttribute('data-badge-url'))) shellKit.setCount(today);
  }

  function setCount(kind, n) {
    if (kind !== 'knowledge' && kind !== 'actions') return;
    counts[kind] = Math.max(0, Math.floor(Number(n) || 0));
    if (kind === 'actions') actionsKnown = true;
    refreshCounts();
  }

  /** 왼쪽 길잡이 — 묶음 수(0 은 흐리게) · 나중에 볼 것 수 · 지금 보는 줄 표시. */
  function refreshNav(all) {
    var n = iv.counts(all);
    n[iv.LATER] = all.filter(function (card) { return deferred[card.id]; }).length;
    Array.prototype.slice.call(document.querySelectorAll('[data-ds-inbox-bin-nav]')).forEach(function (item) {
      var key = item.getAttribute('data-ds-inbox-bin-nav');
      var count = item.querySelector('[data-ds-inbox-bin-count]');
      if (count) { count.textContent = String(n[key] || 0); count.hidden = false; }
      item.classList.toggle('fb-nav-item--muted', !n[key]);
    });
    if (c.view !== 'inbox') return;
    var selected = openBin ? document.querySelector('[data-ds-inbox-bin-nav="' + openBin + '"]')
      : document.querySelector('[data-ds-nav="inbox"]');
    Array.prototype.slice.call(document.querySelectorAll('[data-ds-inbox-bin-nav], [data-ds-nav="inbox"]')).forEach(function (item) {
      item.classList.toggle('is-selected', item === selected);
      if (item === selected) item.setAttribute('aria-current', 'page'); else item.removeAttribute('aria-current');
    });
  }

  function binRow(row) {
    var head = dom.el('span', { cls: 'f-row f-gap4', children: [dom.el('span', { cls: 'f-strong', text: row.title }),
                                                                 dom.el('span', { cls: 'f-count', text: row.n })] });
    var peek = dom.el('span', { cls: 'f-row-nw f-small', children: [kit.icon('document', 'f-i-muted'),
                                                                   dom.el('span', { cls: 'f-ellipsis', text: row.peek })] });
    var open = kit.button('열기', null, 'f-btn-small f-btn-primary');
    open.setAttribute('data-ds-bin-open', row.key);
    return dom.el('li', { cls: 'fb-bin', attrs: { 'data-bin': row.key }, children: [
      dom.el('div', { cls: 'f-col f-gap4 fb-bin__text', children: [head, dom.el('span', { cls: 'f-small f-muted', text: row.line }), peek] }),
      dom.el('div', { cls: 'f-row', children: [dom.el('span', { cls: 'f-small f-muted f-num', text: '약 ' + row.mins + '분' }), open] })] });
  }

  /** 첫 화면 — 묶음 줄 + 빈 묶음 한 줄(카드가 0 이면 '승인 대기가 없어요.' 한 줄만 — F27). */
  function renderOverview(all) {
    dom.clear(parts.bins);
    if (!all.length) {
      parts.bins.appendChild(dom.el('li', { cls: 'f-empty fb-bin-empty', text: '승인 대기가 없어요.' }));
      return;
    }
    iv.binRows(all, c.display).forEach(function (row) { parts.bins.appendChild(binRow(row)); });
    var none = iv.emptyLine(all);
    if (none) parts.bins.appendChild(dom.el('li', { cls: 'f-small f-muted fb-bin fb-bin--none', text: none }));
  }

  /** 연 묶음(또는 나중에 볼 것)의 카드 — 표 묶음은 PC 에서 표 한 장, ③ 은 질문 카드. */
  function renderOpen(all) {
    dom.clear(parts.cards);
    dom.clear(parts.later);
    var later = openBin === iv.LATER;
    var cards = later ? all.filter(function (card) { return deferred[card.id]; }) : iv.inBin(all, openBin);
    if (c.wideBins.indexOf(openBin) >= 0 && tableKit) {
      tableKit.render(parts.cards, cards, openBin);
      parts.laterBox.hidden = true;
      return;
    }
    var folded = 0;
    cards.forEach(function (card) {
      var node = iv.binOf(card) === 'decide' && questionKit ? questionKit.build(card) : cardKit.build(card, c);
      if (later || deferred[card.id]) {  // 이미 접은 카드에는 '나중에'가 할 일이 없다
        Array.prototype.slice.call(node.querySelectorAll('[data-ds-act="later"]')).forEach(function (b) { b.hidden = true; });
      }
      if (!later && deferred[card.id]) { parts.later.appendChild(node); folded += 1; } else { parts.cards.appendChild(node); }
    });
    parts.laterBox.hidden = !folded;
    parts.laterTitle.textContent = '나중에 볼 것 ' + folded + '개';
  }

  function renderPc(all) {
    if (openBin && !(openBin === iv.LATER ? all.some(function (card) { return deferred[card.id]; }) : iv.inBin(all, openBin).length)) {
      openBin = '';  // 없거나 빈 묶음이면 목록(F07)
    }
    var bin = iv.find(openBin);
    if (parts.erp) parts.erp.hidden = !!openBin;  // 묶음을 열면 그 묶음 카드만
    parts.title.textContent = openBin ? (bin ? bin.title : '나중에 볼 것') : '지식 고침';
    parts.count.textContent = String(openBin ? (openBin === iv.LATER ? all.filter(function (x) { return deferred[x.id]; }).length
      : iv.inBin(all, openBin).length) : all.length);
    parts.sub.hidden = parts.bins.hidden = !!openBin;
    parts.back.hidden = parts.open.hidden = !openBin;
    if (openBin) renderOpen(all); else renderOverview(all);
    var ids = iv.bulkScope(all, openBin, c.wideBins, deferred, review);
    parts.bulk.hidden = ids.length < 2;
    parts.bulkText.textContent = '등급 A ' + ids.length + '개 모두 승인';
    var waiting = (data && data.counts && data.counts.ai_waiting) || 0;
    parts.ai.hidden = !waiting;  // AI 제안 주 상한 — 자리를 기다리는 AI 제안이 있을 때만
    parts.ai.textContent = waiting ? review.aiLine(data) : '';
    window.history.replaceState(null, '', iv.addressFor(c.urls.page, openBin));
  }

  function render() {
    var all = allCards();
    if (data) counts.knowledge = all.length;
    refreshNav(all);
    refreshCounts();
    if (c.view !== 'inbox' || !parts.bins) return;
    root.classList.toggle('is-phone', isPhone());
    if (isPhone()) {
      if (phoneKit) phoneKit.render(iv.phoneSplit(all, deferred, review), c);
    } else {
      renderPc(all);
    }
  }

  async function load() {
    if (c.view === 'inbox') status('불러오는 중…');
    var res = await dom.getJson(c.urls.inbox);
    if (!res.ok) {
      status(res.error, 'error');
      return;
    }
    data = res.data;
    status('');
    render();
  }

  function defer(cardId) {
    deferred[cardId] = true;
    saveDeferred();
    render();
  }

  var act = window.FOMS_DS_INBOX_ACT ? window.FOMS_DS_INBOX_ACT.create({ urls: c.urls, root: root, findView: findView,
                                                                        reload: load, defer: defer, status: status }) : null;

  function openAside(node) {
    var aside = document.querySelector('[data-ds-inbox-aside]');
    if (!aside) return null;
    dom.clear(aside);
    if (node) aside.appendChild(node);
    aside.hidden = false;
    return aside;
  }

  function closeAside() {
    var aside = document.querySelector('[data-ds-inbox-aside]');
    if (!aside) return;
    aside.hidden = true;
    dom.clear(aside);
  }

  /** 길잡이 · 묶음 열기 · 돌아가기 — 승인 대기 보기에서는 다시 읽지 않고 그 자리에서 바꾼다. */
  function onNav(target, event) {
    var link = target.closest('[data-ds-inbox-bin-nav], [data-ds-nav="inbox"], [data-ds-bin-open], [data-ds-inbox-back]');
    if (!link || c.view !== 'inbox' || !data || isPhone()) return false;
    if (event && event.preventDefault) event.preventDefault();
    openBin = link.getAttribute('data-ds-inbox-bin-nav') || link.getAttribute('data-ds-bin-open') || '';
    render();
    return true;
  }

  function mine(node) {
    return !!node.closest('[data-ds-inbox-know], [data-ds-inbox-own], [data-ds-phone-pc-list]');
  }

  shell.addEventListener('click', function (event) {
    var target = event.target;
    if (!target || !target.closest || onNav(target, event)) return;
    var answer = target.closest('[data-ds-answer]');
    if (answer && mine(answer) && questionKit) {
      questionKit.answer(answer, { urls: c.urls, findView: findView, reload: load, done: function (t) { status(t); } });
      return;
    }
    var tableApply = target.closest('[data-ds-table-apply]');
    if (tableApply && act) { act.applyTable(tableApply); return; }
    var bulk = target.closest('[data-ds-inbox-bulk]');
    if (bulk && act) { act.bulk(bulk, iv.bulkScope(allCards(), openBin, c.wideBins, deferred, review)); return; }
    var button = target.closest('[data-ds-act]');
    if (button && mine(button) && act) { act.onAct(button); return; }
    if (phoneKit && c.view === 'inbox') phoneKit.onClick(target);
  });

  phoneQuery.addEventListener('change', function () { if (data) render(); });
  document.addEventListener('keydown', function (event) {
    var aside = document.querySelector('[data-ds-inbox-aside]');
    if (event.key === 'Escape' && aside && !aside.hidden) closeAside();
  });

  window.FOMS_DS_INBOX = { setCount: setCount, openAside: openAside, closeAside: closeAside, isPhone: isPhone };
  if (phoneKit) phoneKit.watch();
  if (c.urls.inbox) load(); else refreshCounts();
  root.setAttribute('data-ds-inbox-ready', '1');
  root.dispatchEvent(new CustomEvent('ds:inbox-ready', { bubbles: true, detail: { view: c.view } }));
})();

/* 생산 파트 도면 카드 — 확인 창 글 · 창 그리기(설계서 §15.6 '확인 창' 표 9줄 + 2026-11-23 §8-1 · §9 창 글). 쓰기 없음(fetch 0).
 * 쓰기(요청 · 응답 처리)는 foms-production-parts.js 의 send() 하나 — 이 파일은 글을 짓고 창(#foms-part-confirm-modal)을 그린다.
 * 2026-11-25 multi-holder §8-2: [작업 시작] · [시작 취소] · '작업 중' · '완료'로 낱말을 바꿨다. 여러 명이 같이 작업하는 창 글([같이 작업] ·
 *   [담당 바꾸기] 사람 고르기 · 반장 고르기 [{이름} 시작 취소] · 남은 사람이 있는 [완료])은 foms-production-parts-crew.js 가 먼저 짓는다(plan).
 *   이름 줄("이시영 · 김재단 외 1")은 서버가 준 글(카드 data-pp-crew · 응답 mark.crew)만 쓴다. 그 밖 창 글:
 *   시작 취소 · 담당 바꾸기(시작한 때 한 줄) · 관리자 고르기 · 첫 카드 한 줄(제작 시작) ·
 *   진 경합 · 거절(창 안 빨간 글 + 계획 줄을 서버 모습으로 + [닫기] 하나, .pp-modal.is-lost) · "제작 완료할까요?"(검수 마지막 장).
 * 창이 열린 동안: 판(창의 형제)은 inert, Tab 은 창 안에서만 돈다, 닫으면 연 단추로(다시 그려졌으면 같은 카드의 같은 단추로) 초점.
 * 이어 뜨는 창(제작 완료할까요?)은 내용이 바뀐 뒤 0.8초 동안 실행 단추가 aria-disabled(장갑 손 두 번 누름 막기, §4-4). */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  var modal = root && root.querySelector('[data-pp-modal]');
  var board = window.FomsPartsBoard;
  if (!root || !board || !modal) { return; }
  var bound = window.__FOMS_PROD_PARTS_BOUND = window.__FOMS_PROD_PARTS_BOUND || {};
  if (bound.modal === root) { return; }
  bound.modal = root;

  var cfg = board.cfg || {};
  var LABEL = cfg.label || '';
  var IS_CUT = cfg.part === 'cut';
  var NAME = cfg.me || '';
  var LOCK_MS = 800;
  var claim = window.FomsPartsClaim || {};
  function q(sel) { return modal.querySelector(sel); }
  function attr(card, name) { return card.getAttribute(name) || ''; }
  function josa(name) { return claim.josa ? claim.josa(name, '가', '이') : name; }
  function crewOf(card) { var c = window.FomsPartsCrew; return (c && card && c.of(card)) || {}; }
  function who(card) { return crewOf(card).who || attr(card, 'data-picked-name'); }
  // 문장 속 이름 + 이/가 — 같이 작업하는 줄은 서버가 준 완성 조각("이시영 · 김재단 외 2명이"), 사람 없는 옛 줄만 한 이름에 토씨
  function subj(card) { var name = attr(card, 'data-picked-name'); return crewOf(card).who_subj || (name ? josa(name) : ''); }
  function toward(name) {
    var code = name.charCodeAt(name.length - 1) - 0xAC00;
    var fin = code >= 0 && code < 11172 ? code % 28 : -1;
    return name + (fin === 0 || fin === 8 ? '로' : '으로');
  }

  // ── 누름 문구(설계서 §15.6 확인 창 표 9줄 + multi-holder §8-2 1 · 2 · 32 · 33) — 여러 명 창은 crew.plan 이 먼저 ──
  function plan(action, card) {
    var crew = window.FomsPartsCrew;
    var many = crew && card ? crew.plan(action, card) : null;
    if (many) { return many; }
    if (action === 'take') {
      return { title: LABEL + ' 작업을 시작할까요?', line: (IS_CUT ? '안 봄 ' : '') + '→ 작업 필요 · ' + NAME, run: '작업 시작', tone: 'need' };
    }
    if (action === 'basic') { return { title: '기본으로 할까요?', line: '안 봄 → 기본 · ' + NAME, run: '기본으로', tone: 'basic' }; }
    if (action === 'done') {
      return { title: LABEL + ' 완료로 바꿀까요?', line: '작업 필요 → ' + LABEL + ' 완료 · ' + NAME, run: LABEL + ' 완료', tone: 'done' };
    }
    if (action === 'release' || action === 'takeover' || action === 'held') { return newPlan(action, card); }
    if (card && attr(card, 'data-state') === 'basic') { return { title: '안 봄으로 되돌릴까요?', line: '기본 → 안 봄', run: '되돌리기', tone: 'unbasic' }; }
    return { title: '작업 필요로 되돌릴까요?', line: LABEL + ' 완료 → 작업 필요 · ' + NAME, run: '되돌리기', tone: 'need' };
  }
  function bulkPlan(cards) {
    return { title: cards.length + '장을 기본으로 할까요?', line: '안 봄 → 기본 · ' + NAME, run: cards.length + '장 기본으로', tone: 'basic' };
  }
  // ── 새 누름 문구(§9 — 미정 · 작업 중 · 시작 취소 · 담당 바꾸기, multi-holder §8-2 4 · 5 · 12 · 13) ──
  function heldSince(card, subject, iso) {
    var holder = subject || (card ? subj(card) : '');
    var at = claim.sinceAt ? claim.sinceAt(iso || (card ? attr(card, 'data-picked-at') : '')) : '';
    return holder ? holder + ' ' + (at ? at + '부터 ' : '') + '작업 중인 도면이에요.' : '';
  }
  function newPlan(action, card) {
    var holder = who(card) || '다른 사람';
    var mine = attr(card, 'data-picked-me') === '1';
    if (action === 'release') {
      return mine ? { title: '시작을 취소할까요?', line: '담당 ' + NAME + ' → 미정', run: '시작 취소', tone: 'release' }
        : { title: holder + ' 작업 시작을 취소할까요?', line: '담당 ' + holder + ' → 미정', run: '시작 취소', tone: 'release', note: heldSince(card) };
    }
    if (action === 'takeover') {
      return { title: '담당을 ' + holder + '에서 ' + toward(NAME) + ' 바꿀까요?', line: '담당 ' + holder + ' → 담당 ' + NAME,
        run: '담당 바꾸기', tone: 'taken',
        note: heldSince(card) + (attr(card, 'data-picked-name') ? ' 바꾸기 전에 ' + holder + '에게 말해 주세요.' : '') };
    }
    return { title: holder + ' 작업 중인 도면이에요', line: holder + ' 작업 중', run: '', tone: 'taken', note: heldSince(card),
      choices: [['takeover', '담당 바꾸기', 'taken'], ['done', '대신 완료', 'done'], ['release', '시작 취소', 'release']] };
  }
  // 관리자 · 대신(파트 없는 생산팀, 2026-11-23 §4-12)이 남이 작업 중이거나 완료한 장을 누를 때 한 줄 더(D55, §8-2 14 · 34)
  function ownerNote(card) {
    if ((cfg.mode !== 'admin' && cfg.mode !== 'sub') || !card) { return ''; }
    var st = attr(card, 'data-state');
    var picked = subj(card);
    var name = attr(card, 'data-done-name');
    var done = (st === 'done' && crewOf(card).done_subj) || (name ? josa(name) : '');
    if (st === 'need' && picked && attr(card, 'data-picked-me') !== '1') { return picked + ' 작업 중인 도면이에요'; }
    if ((st === 'done' || st === 'basic') && done && attr(card, 'data-done-me') !== '1') {
      return done + (st === 'basic' ? ' 기본으로 한 도면이에요' : ' 완료한 도면이에요');
    }
    return '';
  }
  function firstLine(action, cards) {
    var first = cards.some(function (c) { return attr(c, 'data-pp-first') === '1'; });
    return first && (action === 'take' || action === 'basic' || action === 'bulk') ? '이 집 첫 도면이라 제작 시작도 같이 돼요.' : '';
  }

  // ── 창 그리기 ──
  var opened = null; // {opener, key, act, siblings}
  function setText(sel, text) { var n = q(sel); n.textContent = text || ''; n.hidden = !text; }
  // 아래 단추 줄의 실행 단추 — 고르기 칸의 단추(관리자 고르기도 data-pp-modal-run)를 잘못 집지 않게 아래 줄에서만 찾는다
  function runBtn() { return q('.foms-prod-change-modal__foot [data-pp-modal-run]'); }
  // 고르기 — 관리자 고르기([action, 글, 색, 고른 사람 id, 다음 창]) 또는 [담당 바꾸기] 사람 고르기(people — 누르면 고름만, 실행은 아래 단추)
  function renderChoices(choices, people) {
    var box = q('[data-pp-modal-choices]');
    var list = people || choices || [];
    box.textContent = '';
    box.className = 'pp-mchoices' + (people ? ' pp-mchoices--who' : list.length === 4 ? ' pp-mchoices--two' : ''); // 넷 = 2 × 2
    box.setAttribute('aria-label', people ? '누구와 바꿀지' : '고르기');
    list.forEach(function (c) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'foms-prod-change-modal__btn pp-mbtn ' + (people ? 'pp-mwho' : 'pp-mgo pp-mgo--' + c[2]);
      if (people) { b.setAttribute('data-pp-who', String(c.uid)); b.setAttribute('data-pp-line', c.line); b.setAttribute('aria-pressed', 'false'); }
      else { b.setAttribute(c[4] ? 'data-pp-next' : 'data-pp-modal-run', ''); b.setAttribute('data-pp-choice', c[0]); }
      if (!people && c[3] != null) { b.setAttribute('data-pp-target', String(c[3])); }
      b.textContent = people ? c.text : c[1];
      box.appendChild(b);
    });
    box.hidden = !list.length;
  }
  // [담당 바꾸기] 사람 고르기 — 고른 칸만 켜고 계획 줄을 "담당 이시영 · 김재단 → 담당 이시영 · 박재단"으로, 실행 단추를 연다
  function pick(btn) {
    [].slice.call(modal.querySelectorAll('[data-pp-who]')).forEach(function (b) {
      b.classList.toggle('is-on', b === btn);
      b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
    });
    var label = modal.querySelector('.foms-prod-change-modal__alert-label');
    if (label) { label.textContent = btn.getAttribute('data-pp-line') || ''; }
    runBtn().removeAttribute('aria-disabled');
  }
  function fill(p, items, body) {
    modal.classList.remove('is-lost');
    q('[data-pp-modal-title]').textContent = p.title;
    q('[data-pp-modal-count]').textContent = items.length ? items.length + '장' : '';
    setText('[data-pp-modal-note]', p.note);
    setText('[data-pp-modal-body]', body);
    q('[data-pp-modal-err]').hidden = true;
    var list = q('[data-pp-modal-list]');
    list.textContent = '';
    items.forEach(function (li) { list.appendChild(li); });
    list.hidden = !items.length; // 제작 완료 물음처럼 목록이 없으면 빈 줄을 안 남긴다
    var run = runBtn();
    run.className = 'foms-prod-change-modal__btn pp-mbtn pp-mgo pp-mgo--' + p.tone;
    run.textContent = p.run || '';
    run.hidden = !p.run;
    if (p.locked) { run.setAttribute('aria-disabled', 'true'); } else { run.removeAttribute('aria-disabled'); }
    q('[data-pp-modal-close]').textContent = p.closeText || (p.run ? '취소' : '닫기');
    renderChoices(p.choices, p.who);
    modal.classList.toggle('is-many', items.length > 1);
  }
  function setInert(on) {
    if (on) {
      opened.siblings = [].slice.call(modal.parentNode.children).filter(function (n) { return n !== modal && !n.inert; });
      opened.siblings.forEach(function (n) { n.inert = true; });
    } else if (opened && opened.siblings) {
      opened.siblings.forEach(function (n) { n.inert = false; });
    }
  }
  function open(p, items, opener, card) {
    if (!opened) {
      opened = { opener: opener, key: card ? [attr(card, 'data-order-id'), attr(card, 'data-key')] : null,
        act: opener && opener.getAttribute('data-pp-act') };
      setInert(true);
    }
    fill(p, items, p.body);
    modal.hidden = false;
    modal.classList.add('is-open');
    q('[data-pp-modal-close]').focus();
  }
  // 보이는 칸인지 — 문서에 있어도 숨었으면(카드가 칸 단추로 숨음 · hidden · 보이는 크기 0) 초점을 주지 않는다
  function shown(n) { return !!n && document.contains(n) && n.offsetParent !== null && !n.closest('[hidden]'); }
  function refocus() {
    var o = opened;
    if (!o) { return; }
    var cards = window.FomsPartsCards;
    var card = o.key && cards ? cards.find(o.key[0], o.key[1])[0] : null;
    var pick = [o.opener, card && card.querySelector('[data-pp-act="' + o.act + '"]'), card && card.querySelector('[data-pp-actbox] button'),
      card && card.querySelector('.pp-sheetlink'), root.querySelector('.fph-parts:not([hidden]) [data-pp-view].is-on')];
    var next = pick.filter(shown)[0]; // 다 숨었으면 늘 보이는 판 머리 거르개(고른 칸)
    if (next && typeof next.focus === 'function') { next.focus(); }
  }
  function close() {
    modal.classList.remove('is-open', 'is-lost');
    modal.hidden = true;
    setInert(false);
    refocus();
    opened = null;
  }
  function busy(on, runText) {
    var run = runBtn();
    run.disabled = on;
    q('[data-pp-modal-close]').disabled = on;
    [].slice.call(modal.querySelectorAll('[data-pp-choice]')).forEach(function (b) { b.disabled = on; });
    run.textContent = on ? '저장하는 중…' : runText;
  }
  function error(text) { var err = q('[data-pp-modal-err]'); err.textContent = text; err.hidden = false; }
  // 진 경합 · 거절: 빨간 글(서버 글) + 계획 줄을 서버 모습으로("지금: 박엣지 작업 중") + [닫기] 하나
  function lost(text, nowLine) {
    modal.classList.add('is-lost');
    error(text);
    var alertBox = modal.querySelector('.foms-prod-change-modal__alert');
    if (alertBox && nowLine) {
      alertBox.className = 'foms-prod-change-modal__alert pp-al--now';
      alertBox.textContent = '';
      var label = document.createElement('span');
      label.className = 'foms-prod-change-modal__alert-label';
      label.textContent = nowLine;
      alertBox.appendChild(label);
    }
    runBtn().hidden = true;
    renderChoices(null);
    setText('[data-pp-modal-body]', '');
    q('[data-pp-modal-close]').textContent = '닫기';
    q('[data-pp-modal-close]').focus();
  }
  function nowLine(mark) {
    if (!mark) { return ''; }
    var cr = mark.crew || {};
    if (mark.state === 'need') { return '지금: ' + (cr.who || mark.picked_by_name || '다른 사람') + ' 작업 중'; }
    var done = cr.done || mark.done_by_name;
    if (mark.state === 'done') { return '지금: ' + LABEL + ' 완료' + (done ? ' · ' + done : ''); }
    if (mark.state === 'basic') { return '지금: 기본' + (mark.done_by_name ? ' · ' + mark.done_by_name : ''); }
    return '지금: 담당 미정';
  }
  // 검수 마지막 장 완료 뒤 같은 창이 이어서 묻는다(§4-4) — 실행 단추 0.8초 잠금, 초점은 [나중에].
  // 섞인 주문(2공장)은 sheets 자리에 서버가 준 factory_ready({label, message}) — "2공장 제작 완료할까요?" · [2공장 제작 완료]
  function complete(card, sheets, pending) {
    var who = ((card.querySelector('.fph-dr__nm b') || {}).textContent || '') + ' #' + attr(card, 'data-order-id');
    var fac = sheets && typeof sheets === 'object' ? sheets : null;
    fill({ title: (fac ? fac.label + ' ' : '') + '제작 완료할까요?', run: pending.run, tone: 'done', closeText: '나중에' }, [],
      who + ' · ' + (fac ? fac.message : '도면 ' + sheets + '장이 모두 완료됐어요. 제작 완료하면 시공 대기로 넘어가요.'));
    var run = runBtn();
    run.setAttribute('aria-disabled', 'true');
    pending.locked = true;
    window.setTimeout(function () { pending.locked = false; run.removeAttribute('aria-disabled'); }, LOCK_MS);
    q('[data-pp-modal-close]').focus();
  }
  // Tab 은 창 안에서만(초점 가두기)
  modal.addEventListener('keydown', function (e) {
    if (e.key !== 'Tab' || modal.hidden) { return; }
    var list = [].slice.call(modal.querySelectorAll('button, a[href]')).filter(function (n) { return !n.hidden && !n.disabled && n.offsetParent !== null; });
    if (!list.length) { return; }
    var first = list[0];
    var last = list[list.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  window.FomsPartsModal = { plan: plan, bulkPlan: bulkPlan, ownerNote: ownerNote, firstLine: firstLine, open: open, close: close,
    busy: busy, error: error, lost: lost, nowLine: nowLine, complete: complete, pick: pick, heldSince: heldSince, toward: toward };
})();

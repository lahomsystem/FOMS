/* 생산 파트 도면 카드 — 확인 창 글 · 창 그리기(설계서 §15.6 '확인 창' 표 9줄 + 2026-11-23 §8-1 · §9 창 글). 쓰기 없음(fetch 0).
 * 쓰기(요청 · 응답 처리)는 foms-production-parts.js 의 send() 하나 — 이 파일은 글을 짓고 창(#foms-part-confirm-modal)을 그린다.
 * 지금 누름(맡기 · 기본 · 완료 · 되돌리기 · 모두 기본)의 창 글은 한 글자도 안 바꿨다(승인 때 고친 것 1). 새 창 글:
 *   맡기 취소 · 담당 바꾸기(맡은 때 한 줄) · 관리자 고르기 셋([담당 바꾸기][대신 완료][맡기 취소]) · 첫 카드 한 줄(제작 시작) ·
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
  var VERB = cfg.verb || LABEL;
  var IS_CUT = cfg.part === 'cut';
  var NAME = cfg.me || '';
  var LOCK_MS = 800;
  var claim = window.FomsPartsClaim || {};
  function q(sel) { return modal.querySelector(sel); }
  function attr(card, name) { return card.getAttribute(name) || ''; }
  function josa(name) { return claim.josa ? claim.josa(name, '가', '이') : name; }
  function toward(name) {
    var code = name.charCodeAt(name.length - 1) - 0xAC00;
    var fin = code >= 0 && code < 11172 ? code % 28 : -1;
    return name + (fin === 0 || fin === 8 ? '로' : '으로');
  }

  // ── 지금 누름 문구(설계서 §15.6 확인 창 표 9줄 — 그대로) ──
  function plan(action, card) {
    if (action === 'take') {
      return { title: IS_CUT ? '내가 자를까요?' : '내가 ' + VERB + '할까요?', line: (IS_CUT ? '안 봄 ' : '') + '→ 작업 필요 · ' + NAME,
        run: '내가 ' + VERB, tone: 'need' };
    }
    if (action === 'basic') { return { title: '기본으로 할까요?', line: '안 봄 → 기본 · ' + NAME, run: '기본으로', tone: 'basic' }; }
    if (action === 'done') {
      return { title: LABEL + ' 끝으로 바꿀까요?', line: '작업 필요 → ' + LABEL + ' 끝 · ' + NAME, run: LABEL + ' 완료', tone: 'done' };
    }
    if (action === 'release' || action === 'takeover' || action === 'held') { return newPlan(action, card); }
    if (card && attr(card, 'data-state') === 'basic') { return { title: '안 봄으로 되돌릴까요?', line: '기본 → 안 봄', run: '되돌리기', tone: 'unbasic' }; }
    return { title: '작업 필요로 되돌릴까요?', line: LABEL + ' 끝 → 작업 필요 · ' + NAME, run: '되돌리기', tone: 'need' };
  }
  function bulkPlan(cards) {
    return { title: cards.length + '장을 기본으로 할까요?', line: '안 봄 → 기본 · ' + NAME, run: cards.length + '장 기본으로', tone: 'basic' };
  }
  // ── 새 누름 문구(§9 — 미정 · 담당 · 맡기 취소 · 담당 바꾸기) ──
  function heldSince(card) {
    var holder = attr(card, 'data-picked-name');
    var at = claim.sinceAt ? claim.sinceAt(attr(card, 'data-picked-at')) : '';
    return holder ? josa(holder) + ' ' + (at ? at + '부터 ' : '') + '맡은 도면이에요.' : '';
  }
  function newPlan(action, card) {
    var holder = attr(card, 'data-picked-name') || '다른 사람';
    var mine = attr(card, 'data-picked-me') === '1';
    if (action === 'release') {
      return mine ? { title: '맡기를 취소할까요?', line: '담당 ' + NAME + ' → 미정', run: '맡기 취소', tone: 'release' }
        : { title: holder + ' 담당을 취소할까요?', line: '담당 ' + holder + ' → 미정', run: '맡기 취소', tone: 'release', note: heldSince(card) };
    }
    if (action === 'takeover') {
      return { title: '담당을 ' + holder + '에서 ' + toward(NAME) + ' 바꿀까요?', line: '담당 ' + holder + ' → 담당 ' + NAME,
        run: '담당 바꾸기', tone: 'taken',
        note: heldSince(card) + (attr(card, 'data-picked-name') ? ' 바꾸기 전에 ' + holder + '에게 말해 주세요.' : '') };
    }
    return { title: holder + ' 담당 도면이에요', line: '담당 ' + holder, run: '', tone: 'taken', note: heldSince(card),
      choices: [['takeover', '담당 바꾸기', 'taken'], ['done', '대신 완료', 'done'], ['release', '맡기 취소', 'release']] };
  }
  // 관리자가 남이 맡거나 끝낸 장을 누를 때 한 줄 더(D55 — 지금 글)
  function ownerNote(card) {
    if (cfg.mode !== 'admin' || !card) { return ''; }
    var st = attr(card, 'data-state');
    var picked = attr(card, 'data-picked-name');
    var done = attr(card, 'data-done-name');
    if (st === 'need' && picked && attr(card, 'data-picked-me') !== '1') { return josa(picked) + ' 맡은 도면이에요'; }
    if ((st === 'done' || st === 'basic') && done && attr(card, 'data-done-me') !== '1') {
      return josa(done) + (st === 'basic' ? ' 기본으로 한 도면이에요' : ' 끝낸 도면이에요');
    }
    return '';
  }
  function firstLine(action, cards) {
    var first = cards.some(function (c) { return attr(c, 'data-pp-first') === '1'; });
    return first && (action === 'take' || action === 'basic' || action === 'bulk') ? '이 집 첫 카드라 제작 시작도 같이 돼요.' : '';
  }

  // ── 창 그리기 ──
  var opened = null; // {opener, key, act, siblings}
  function setText(sel, text) { var n = q(sel); n.textContent = text || ''; n.hidden = !text; }
  function runBtn() { return q('[data-pp-modal-run]'); }
  function renderChoices(choices) {
    var box = q('[data-pp-modal-choices]');
    box.textContent = '';
    (choices || []).forEach(function (c) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'foms-prod-change-modal__btn pp-mbtn pp-mgo pp-mgo--' + c[2];
      b.setAttribute('data-pp-modal-run', '');
      b.setAttribute('data-pp-choice', c[0]);
      b.textContent = c[1];
      box.appendChild(b);
    });
    box.hidden = !(choices && choices.length);
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
    var run = runBtn();
    run.className = 'foms-prod-change-modal__btn pp-mbtn pp-mgo pp-mgo--' + p.tone;
    run.textContent = p.run || '';
    run.hidden = !p.run;
    run.removeAttribute('aria-disabled');
    q('[data-pp-modal-close]').textContent = p.closeText || (p.run ? '취소' : '닫기');
    renderChoices(p.choices);
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
  function refocus() {
    var o = opened;
    if (!o) { return; }
    if (o.opener && document.contains(o.opener) && typeof o.opener.focus === 'function') { o.opener.focus(); return; }
    var cards = window.FomsPartsCards;
    var card = o.key && cards ? cards.find(o.key[0], o.key[1])[0] : null;
    var next = card && (card.querySelector('[data-pp-act="' + o.act + '"]') || card.querySelector('[data-pp-actbox] button, .pp-sheetlink'));
    if (next) { next.focus(); }
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
  // 진 경합 · 거절: 빨간 글(서버 글) + 계획 줄을 서버 모습으로("지금: 담당 박엣지") + [닫기] 하나
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
    if (mark.state === 'need') { return '지금: 담당 ' + (mark.picked_by_name || '다른 사람'); }
    if (mark.state === 'done') { return '지금: ' + LABEL + ' 완료' + (mark.done_by_name ? ' · ' + mark.done_by_name : ''); }
    if (mark.state === 'basic') { return '지금: 기본' + (mark.done_by_name ? ' · ' + mark.done_by_name : ''); }
    return '지금: 담당 미정';
  }
  // 검수 마지막 장 완료 뒤 같은 창이 이어서 묻는다(§4-4) — 실행 단추 0.8초 잠금, 초점은 [나중에]
  function complete(card, sheets, pending) {
    var who = ((card.querySelector('.fph-dr__nm b') || {}).textContent || '') + ' #' + attr(card, 'data-order-id');
    fill({ title: '제작 완료할까요?', run: '제작 완료', tone: 'done', closeText: '나중에' }, [],
      who + ' · 도면 ' + sheets + '장이 모두 완료됐어요. 제작 완료하면 시공 대기로 넘어가요.');
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
    busy: busy, error: error, lost: lost, nowLine: nowLine, complete: complete };
})();

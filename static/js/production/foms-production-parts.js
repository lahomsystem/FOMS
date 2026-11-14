/* 생산 파트 도면 카드 — 카드 고치기 + 쓰는 쪽. 설계서 §15.6 '확인 창'(D53 · D54) · §15.4 API, P15-5 · P15-7.
 * 카드 · 칸 숫자 고치기(applyMark)는 window.FomsPartsCards 하나로 내보내 30초 받아 오기(foms-production-parts-sync.js)와 같이 쓴다.
 * 쓰기(맡기 · 기본 · 모두 기본 · 완료 · 되돌리기)는 확인 창(#foms-part-confirm-modal)이 있는 사람(D55)에게만 묶이고, 요청은 창의
 * 실행 단추에서만 나간다. 성공 · 409 면 그 카드와 칸 숫자만 그 자리에서 고친다(다시 읽기 없음). 일괄 기본은 화면의 안 본 장만.
 * 보기 쪽(칸 단추 · 크게 보기)은 foms-production-parts-viewer.js(window.FomsPartsBoard). 실패 글은 설계서 §8 한 가지. */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  var board = window.FomsPartsBoard;
  var modal = root && root.querySelector('[data-pp-modal]');
  if (!root || !board) { return; }
  var bound = window.__FOMS_PROD_PARTS_BOUND = window.__FOMS_PROD_PARTS_BOUND || {};
  if (bound.write === root || board.root !== root) { return; } // 셸 조각 교체로 다시 돌면 새 화면에만 한 번 묶는다
  bound.write = root;

  var cfg = board.cfg || {};
  var OFFLINE = '연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.';
  var LABEL = cfg.label || '';
  var VERB = cfg.verb || LABEL;
  var IS_CUT = cfg.part === 'cut';
  var MINE = cfg.mode === 'part';
  var NAME = cfg.me || '';
  var WRITABLE = !!(modal && cfg.writable); // 읽기 전용(D55) = 배지만, 단추 없음
  var pending = null;
  function toArr(list) { return [].slice.call(list || []); }
  function q(sel) { return modal.querySelector(sel); }
  function attr(card, name) { return card.getAttribute(name) || ''; }
  function josa(name) {
    var code = name.charCodeAt(name.length - 1) - 0xAC00;
    return name + (code >= 0 && code < 11172 && code % 28 === 0 ? '가' : '이');
  }
  function setStatus(text, bad) {
    var box = root.querySelector('[data-foms-home-status]');
    if (box) { box.textContent = text || ''; box.classList.toggle('is-bad', !!bad); }
  }
  function el(tag, cls, text, act) {
    var node = document.createElement(tag);
    node.className = cls || '';
    node.textContent = text || '';
    if (act) { node.type = 'button'; node.setAttribute('data-pp-act', act); }
    return node;
  }

  // ── 문구(설계서 §15.6 확인 창 표 9줄) ──
  function plan(action, card) {
    if (action === 'take') {
      return { title: IS_CUT ? '내가 자를까요?' : '내가 ' + VERB + '할까요?', line: (IS_CUT ? '안 봄 ' : '') + '→ 작업 필요 · ' + NAME,
        run: '내가 ' + VERB, tone: 'need' };
    }
    if (action === 'basic') { return { title: '기본으로 할까요?', line: '안 봄 → 기본 · ' + NAME, run: '기본으로', tone: 'basic' }; }
    if (action === 'done') {
      return { title: LABEL + ' 끝으로 바꿀까요?', line: '작업 필요 → ' + LABEL + ' 끝 · ' + NAME, run: LABEL + ' 완료', tone: 'done' };
    }
    if (card && attr(card, 'data-state') === 'basic') { return { title: '안 봄으로 되돌릴까요?', line: '기본 → 안 봄', run: '되돌리기', tone: 'unbasic' }; }
    return { title: '작업 필요로 되돌릴까요?', line: LABEL + ' 끝 → 작업 필요 · ' + NAME, run: '되돌리기', tone: 'need' };
  }
  // 관리자가 남이 맡거나 끝낸 장을 누를 때 한 줄 더(D55)
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

  // ── 확인 창 ──
  function listItem(card, line, tone) {
    var li = el('li', 'foms-prod-change-modal__item pp-mitem');
    var pic = el('div', 'pp-mimg');
    var img = card.querySelector('.pp-thumb');
    pic.appendChild(img && !img.hidden ? Object.assign(img.cloneNode(false), { loading: 'eager', decoding: 'sync' }) : img ? el('span', 'pp-broken', '그림을 못 불러왔어요') : el('b', '', (card.querySelector('.pp-file b') || {}).textContent || '파일'));
    var body = el('div', 'foms-prod-change-modal__item-body');
    var head = el('div', 'foms-prod-change-modal__item-head');
    var who = el('span', 'foms-prod-change-modal__item-customer', ((card.querySelector('.fph-dr__nm b') || {}).textContent || '') + ' ');
    who.appendChild(el('small', '', '#' + attr(card, 'data-order-id')));
    head.appendChild(who);
    head.appendChild(el('span', 'foms-prod-change-modal__item-id', '도면 ' + attr(card, 'data-no') + '/' + attr(card, 'data-of')));
    body.appendChild(head);
    body.appendChild(el('span', 'foms-prod-change-modal__alert-detail', (card.querySelector('.pp-item') || {}).textContent || ''));
    var alert = el('div', 'foms-prod-change-modal__alert pp-al--' + tone);
    alert.appendChild(el('span', 'foms-prod-change-modal__alert-label', line));
    body.appendChild(alert);
    li.appendChild(pic);
    li.appendChild(body);
    return li;
  }
  function openModal(action, cards, opener) {
    if (!cards.length) { return; }
    var p = action === 'bulk' ? { title: cards.length + '장을 기본으로 할까요?', line: '안 봄 → 기본 · ' + NAME,
      run: cards.length + '장 기본으로', tone: 'basic' } : plan(action, cards[0]);
    pending = { action: action, cards: cards, opener: opener, busy: false, run: p.run };
    q('[data-pp-modal-title]').textContent = p.title;
    q('[data-pp-modal-count]').textContent = cards.length + '장';
    var note = action === 'bulk' ? '' : ownerNote(cards[0]);
    q('[data-pp-modal-note]').textContent = note;
    q('[data-pp-modal-note]').hidden = !note;
    q('[data-pp-modal-err]').hidden = true;
    var list = q('[data-pp-modal-list]');
    list.textContent = '';
    cards.forEach(function (card) { list.appendChild(listItem(card, p.line, p.tone)); });
    var run = q('[data-pp-modal-run]');
    run.className = 'foms-prod-change-modal__btn pp-mbtn pp-mgo pp-mgo--' + p.tone;
    run.textContent = p.run;
    modal.classList.toggle('is-many', cards.length > 1);
    modal.hidden = false;
    modal.classList.add('is-open');
    q('[data-pp-modal-close]').focus();
  }
  function closeModal() {
    if (!pending || pending.busy) { return; }
    var opener = pending.opener;
    pending = null;
    modal.classList.remove('is-open');
    modal.hidden = true;
    if (opener && typeof opener.focus === 'function' && document.contains(opener)) { opener.focus(); }
  }
  function setBusy(busy) {
    pending.busy = busy;
    var run = q('[data-pp-modal-run]');
    run.disabled = busy;
    q('[data-pp-modal-close]').disabled = busy;
    run.textContent = busy ? '저장하는 중…' : pending.run;
  }
  function showError(text) { var err = q('[data-pp-modal-err]'); err.textContent = text; err.hidden = false; }

  // ── 카드 · 칸 숫자 고치기(그 자리에서) ──
  function membership(card) {
    var st = attr(card, 'data-state');
    return { need: attr(card, 'data-in-need') === '1' ? 1 : 0, done: attr(card, 'data-in-done') === '1' ? 1 : 0,
      unseen: st === 'none' ? 1 : 0 };
  }
  function bumpCounts(pane, before, after) {
    ['need', 'done', 'unseen'].forEach(function (k) {
      var delta = after[k] - before[k];
      if (!delta) { return; }
      toArr(pane.querySelectorAll('[data-pp-count="' + k + '"]')).forEach(function (n) {
        n.textContent = String(Math.max(0, Number(n.textContent || 0) + delta));
      });
    });
    var unseen = pane.querySelector('[data-pp-act="bulk"] [data-pp-count="unseen"]');
    var left = unseen ? Number(unseen.textContent || 0) : 0;
    var text = pane.querySelector('[data-pp-unseen-text]');
    if (text) {
      text.textContent = left ? '안 본 도면 ' : '안 본 도면 없어요';
      if (left) { text.appendChild(el('b', '', String(left))); text.appendChild(document.createTextNode('장')); }
    }
    var bulk = pane.querySelector('[data-pp-act="bulk"]');
    if (bulk) { bulk.hidden = !left; }
  }
  function renderAct(card) {
    var box = card.querySelector('[data-pp-actbox]');
    var st = attr(card, 'data-state');
    var picked = attr(card, 'data-picked-name');
    var done = attr(card, 'data-done-name');
    box.textContent = '';
    if (st === 'none') {
      if (!WRITABLE) { return; }
      var two = IS_CUT ? el('div', 'pp-two') : box;
      if (IS_CUT) { two.appendChild(el('button', 'foms-prod-home__btn pp-pick-basic', '기본', 'basic')); box.appendChild(two); }
      two.appendChild(el('button', 'foms-prod-home__btn ' + (IS_CUT ? 'foms-prod-home__btn--pri' : 'pp-act'), '내가 ' + VERB, 'take'));
      return;
    }
    if (st === 'need') {
      if (MINE && attr(card, 'data-picked-me') !== '1') { box.appendChild(el('span', 'fph-wi pp-act pp-st-taken', (picked || '다른 사람') + ' 맡음')); return; }
      box.appendChild(el('span', 'fph-wi pp-act pp-st-need' + (WRITABLE ? ' pp-not-need' : ''), '작업 필요' + (picked ? ' · ' + picked : '')));
      if (WRITABLE) { box.appendChild(el('button', 'fph-qr__done pp-act pp-fin pp-only-need', LABEL + ' 완료', 'done')); }
      return;
    }
    var word = (st === 'done' ? LABEL + ' 끝' : '기본') + (done ? ' · ' + done : '');
    var canUndo = WRITABLE && (!MINE || attr(card, 'data-done-me') === '1');
    box.appendChild(el('span', 'fph-wi pp-act pp-st-' + st + (canUndo ? ' pp-not-done' : ''), word));
    if (!canUndo) { return; }
    var row = el('div', 'fph-wi pp-act pp-undo-row pp-st-' + st + ' pp-only-done');
    row.appendChild(el('span', '', word));
    row.appendChild(el('button', 'foms-prod-home__btn pp-undo', '되돌리기', 'undo'));
    box.appendChild(row);
  }
  function applyMark(card, mark) {
    if (!card || !mark) { return; }
    var pane = board.paneOf(card);
    var before = membership(card);
    var me = String(cfg.me_id);
    var st = mark.state || 'none';
    var pickedMe = mark.picked_by_user_id != null && String(mark.picked_by_user_id) === me;
    var doneMe = mark.done_by_user_id != null && String(mark.done_by_user_id) === me;
    var finished = st === 'done' || st === 'basic';
    var inNeed = st === 'need' && (pickedMe || !MINE);
    card.setAttribute('data-state', st);
    card.setAttribute('data-picked-me', pickedMe ? '1' : '0');
    card.setAttribute('data-done-me', doneMe ? '1' : '0');
    card.setAttribute('data-picked-name', mark.picked_by_name || '');
    card.setAttribute('data-done-name', mark.done_by_name || '');
    card.setAttribute('data-in-need', inNeed ? '1' : '0');
    card.setAttribute('data-in-done', finished && (doneMe || !MINE) ? '1' : '0');
    card.classList.toggle('is-mine', inNeed);
    card.classList.toggle('is-done', finished);
    card.classList.toggle('is-other', st === 'need' && !inNeed);
    renderAct(card);
    bumpCounts(pane, before, membership(card));
    board.applyView(pane);
    document.dispatchEvent(new CustomEvent('foms:part-card-updated', { detail: { key: attr(card, 'data-key') } }));
  }
  function findCard(orderId, key) {
    return toArr(root.querySelectorAll('[data-pp-card]')).filter(function (c) {
      return attr(c, 'data-order-id') === String(orderId) && attr(c, 'data-key') === key;
    });
  }

  // ── 쓰기 — 확인 창의 실행 단추에서만 부른다 ──
  function post(url, body) {
    var opts = { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    var offline = { ok: false, kind: 'network', status: 0, data: {}, message: OFFLINE };
    var call = window.fomsMutationFetch || function (u, o) {
      return fetch(u, o).then(function (res) {
        return res.json().then(function (d) { return { ok: res.ok, status: res.status, data: d || {}, message: (d && d.error) || '' }; });
      });
    };
    try { return call(url, opts).catch(function () { return offline; }); } catch (e) { return Promise.resolve(offline); }
  }
  function requestFor(p) {
    if (p.action === 'bulk') {
      return { url: '/api/production/part-marks/basic', body: { part: cfg.part, seen: 'none', items: p.cards.map(function (c) {
        return { order_id: Number(attr(c, 'data-order-id')), drawing_key: attr(c, 'data-key') };
      }) } };
    }
    var card = p.cards[0];
    return { url: '/api/production/part-marks', body: { order_id: Number(attr(card, 'data-order-id')), drawing_key: attr(card, 'data-key'),
      part: cfg.part, action: p.action, seen: attr(card, 'data-state') } };
  }
  function bulkDone(data) {
    var changed = 0;
    (data.applied || []).forEach(function (m) {
      if (m.changed) { changed += 1; }
      findCard(m.order_id, m.drawing_key).forEach(function (c) { applyMark(c, m); });
    });
    var skipped = data.skipped || [];
    skipped.forEach(function (s) { findCard(s.order_id, s.drawing_key).forEach(function (c) { applyMark(c, s.mark); }); });
    var text = changed + '장 기본으로 했어요';
    if (skipped.length === 1) { text += ' · 1장은 ' + (skipped[0].error || '그사이 다른 사람이 바꿨어요'); }
    if (skipped.length > 1) { text += ' · ' + skipped.length + '장은 그사이 다른 사람이 바꿨어요'; }
    return { text: text, bad: skipped.length > 0 };
  }
  function handle(p, result) {
    var body = result.data || {};
    var data = body.data || {};
    if (result.ok && body.success === true) {
      var done = p.action === 'bulk' ? bulkDone(data) : { text: '저장했어요', bad: false };
      if (p.action !== 'bulk') { p.cards.forEach(function (c) { applyMark(c, data.mark); }); }
      setBusy(false);
      closeModal();
      setStatus(done.text, done.bad);
      return;
    }
    setBusy(false);
    if (result.status === 0 || result.kind === 'network' || result.kind === 'timeout') { showError(OFFLINE); return; }
    if (result.status === 409) {
      if (data.code === 'MARK_CONFLICT' && data.mark && p.action !== 'bulk') { applyMark(p.cards[0], data.mark); }
      closeModal();
      setStatus(body.error || result.message, true);
      return;
    }
    showError(body.error || result.message || OFFLINE);
  }
  function send() {
    if (!pending || pending.busy) { return; }
    var p = pending;
    var req = requestFor(p);
    setBusy(true);
    post(req.url, req.body).then(function (result) { handle(p, result || {}); });
  }

  // 받아 오기가 쓴다: 고치기 · 카드 찾기 · 이 카드가 내 확인 창에 있거나 저장 중인지(그러면 건너뛴다)
  window.FomsPartsCards = { apply: applyMark, find: findCard, held: function (card) { return !!pending && pending.cards.indexOf(card) >= 0; } };
  if (!modal) { return; } // 읽기 전용 — 누름 · 쓰기를 묶지 않는다
  root.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || typeof t.closest !== 'function') { return; }
    if (t === modal) { closeModal(); return; }
    if (t.closest('[data-pp-modal-close]')) { closeModal(); return; }
    if (t.closest('[data-pp-modal-run]')) { send(); return; }
    var btn = t.closest('[data-pp-act]');
    if (!btn) { return; }
    var action = btn.getAttribute('data-pp-act');
    var pane = board.paneOf(btn);
    if (action === 'bulk') {
      openModal('bulk', board.cardsOf(pane).filter(function (c) { return attr(c, 'data-state') === 'none'; }), btn);
      return;
    }
    openModal(action, [btn.closest('[data-pp-card]')], btn);
  });
  window.FomsPartsCards.onEscape = function () { if (pending && !modal.hidden) { closeModal(); } }; // Esc 는 viewer 의 문서 리스너 한 번이 부른다
})();

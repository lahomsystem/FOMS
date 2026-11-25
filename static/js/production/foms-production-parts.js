/* 생산 파트 도면 카드 — 카드 고치기 + 쓰는 쪽. 설계서 §15.6 '확인 창'(D53 · D54) · §15.4 API, P15-5 · P15-7, 2026-11-23 §4-4 · §4-5 · §8-1.
 * 카드 · 칸 숫자 고치기(applyMark)는 window.FomsPartsCards 하나로 내보내 30초 받아 오기(foms-production-parts-sync.js)와 같이 쓴다.
 * 쓰기(작업 시작 · 같이 작업 · 기본 · 모두 기본 · 완료 · 되돌리기 · 시작 취소 · 남의 시작 취소 · 담당 바꾸기 · 제작 완료 — 2026-11-25
 * multi-holder §7-1: 몸에 본 내 몫 seen_me · 고른 사람 target_user_id)는 확인 창(#foms-part-confirm-modal)이 있는 사람(D55)
 * 에게만 묶이고, 요청은 창의 실행 단추(관리자 고르기 셋 포함)에서만 나간다. 성공이면 그 카드와 칸 숫자만 그 자리에서 고친다(다시 읽기
 * 없음). 경합 · 거절(409 · 403)은 창 안에 서버 글 + 서버 모습(.is-lost, [닫기] 하나). 검수 마지막 장이면 같은 창이 "제작 완료할까요?".
 * 창 글 · 창 그리기는 foms-production-parts-modal.js(FomsPartsModal), 새 카드 칸(손 체크 · 막힘 · 내 작업 한 층 · 꼬리)은
 * foms-production-parts-claim.js(FomsPartsClaim), 여러 명 칸(작업 필요 · 완료 · [같이 작업] · 이름 줄 · 넘김 말풍선)은
 * foms-production-parts-crew.js(FomsPartsCrew), 보기 쪽은 foms-production-parts-viewer.js(FomsPartsBoard). */
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
  var IS_CUT = cfg.part === 'cut';
  var MINE = cfg.mode === 'part';
  var WRITABLE = !!(modal && cfg.writable); // 읽기 전용(D55) = 배지만, 단추 없음
  var claim = window.FomsPartsClaim || {};
  var crew = window.FomsPartsCrew || {};
  var M = window.FomsPartsModal || {};
  var pending = null;
  function toArr(list) { return [].slice.call(list || []); }
  function attr(card, name) { return card.getAttribute(name) || ''; }
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

  // ── 확인 창 목록 줄(카드 그림 · 이름 · 도면 n/m · 품목 · 바뀔 상태 한 줄) ──
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
    var p = action === 'bulk' ? M.bulkPlan(cards) : M.plan(action, cards[0]);
    var note = action === 'bulk' || p.note ? (p.note || '') : M.ownerNote(cards[0]);
    p.note = note;
    p.body = M.firstLine(action, cards);
    pending = { action: action === 'held' ? '' : action, cards: cards, busy: false, run: p.run, locked: !!p.locked, target: p.target };
    M.open(p, cards.map(function (card) { return listItem(card, p.line, p.tone); }), opener, cards[0]);
  }
  function closeModal() {
    if (!pending || pending.busy) { return; }
    pending = null;
    M.close();
  }
  function setBusy(busy) {
    pending.busy = busy;
    M.busy(busy, pending.run);
  }

  // ── 카드 · 칸 숫자 고치기(그 자리에서) ──
  // unseen = [남은 N장 모두 기본] 숫자(막힌 안 본 장은 뺀다 — 창 목록 bulkCards 와 같은 기준), look = '안 본 도면 N장' 글(모두)
  function bulkable(card) { return attr(card, 'data-state') === 'none' && !attr(card, 'data-pp-block'); }
  function membership(card) {
    var st = attr(card, 'data-state');
    return { need: attr(card, 'data-in-need') === '1' ? 1 : 0, done: attr(card, 'data-in-done') === '1' ? 1 : 0,
      unseen: bulkable(card) ? 1 : 0, look: st === 'none' ? 1 : 0 };
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
      var look = Math.max(0, Number(text.getAttribute('data-pp-unseen-text') || 0) + after.look - before.look);
      text.setAttribute('data-pp-unseen-text', String(look));
      text.textContent = look ? '안 본 도면 ' : '안 본 도면 없어요';
      if (look) { text.appendChild(el('b', '', String(look))); text.appendChild(document.createTextNode('장')); }
    }
    var bulk = pane.querySelector('[data-pp-act="bulk"]');
    if (bulk) { bulk.hidden = !left; }
  }
  // 카드 단추 칸 — 템플릿(home_parts.html pp_act)과 같은 규칙. 새 칸(손 체크 · 막힘 · 내 작업 한 층)은 claim, 작업 필요 · 완료 칸은
  // crew(여러 명 — 이름 줄은 서버 글)가 먼저 그린다. 여기는 안 봄 칸([기본][작업 시작] — 네 파트 같은 글, multi-holder §8-2 1)만.
  function renderAct(card) {
    var box = card.querySelector('[data-pp-actbox]');
    var opts = { writable: WRITABLE, mine: MINE, label: cfg.label || '' };
    toArr(box.children).forEach(function (n) { if (!n.classList.contains('pp-why')) { box.removeChild(n); } });
    if (claim.renderTag) { claim.renderTag(card, WRITABLE); }
    if (claim.special && claim.special(card, box, opts)) { return; }
    if (crew.render && crew.render(card, box, opts)) { return; }
    if (attr(card, 'data-state') !== 'none' || !WRITABLE) { return; }
    var two = IS_CUT ? el('div', 'pp-two') : box;
    if (IS_CUT) { two.appendChild(el('button', 'foms-prod-home__btn pp-pick-basic', '기본', 'basic')); box.appendChild(two); }
    two.appendChild(el('button', 'foms-prod-home__btn ' + (IS_CUT ? 'foms-prod-home__btn--pri' : 'pp-act'), '작업 시작', 'take'));
  }
  // 받은 표시 → 카드. 내 몫(작업 중 · 완료)은 서버가 준 mark.crew.me — 내 몫만 완료("재단 1/2 완료")는 파트 계정 '완료' 칸(Q12)
  function applyMark(card, mark) {
    if (!card || !mark) { return; }
    var pane = board.paneOf(card);
    var before = membership(card);
    var me = String(cfg.me_id);
    var st = mark.state || 'none';
    var cr = crew.setAttrs ? crew.setAttrs(card, mark) : {};
    var share = cr.me || 'none';
    var pickedMe = share === 'held';
    var doneMe = share === 'done' || (!cr.n && mark.done_by_user_id != null && String(mark.done_by_user_id) === me);
    var finished = st === 'done' || st === 'basic';
    var inNeed = st === 'need' && (pickedMe || !MINE);
    card.setAttribute('data-state', st);
    card.setAttribute('data-picked-me', pickedMe ? '1' : '0');
    card.setAttribute('data-done-me', doneMe ? '1' : '0');
    card.setAttribute('data-picked-name', mark.picked_by_name || '');
    card.setAttribute('data-done-name', mark.done_by_name || '');
    card.setAttribute('data-in-need', inNeed ? '1' : '0');
    card.setAttribute('data-in-done', (finished && (doneMe || !MINE)) || (st === 'need' && share === 'done') ? '1' : '0'); // 반장 자기 몫 완료도
    if (claim.setMarkAttrs) { claim.setMarkAttrs(card, mark); }
    card.classList.toggle('is-mine', inNeed);
    card.classList.toggle('is-done', finished);
    card.classList.toggle('is-other', st === 'need' && MINE && share === 'none');
    renderAct(card);
    bumpCounts(pane, before, membership(card));
    board.applyView(pane);
    document.dispatchEvent(new CustomEvent('foms:part-card-updated', { detail: { key: attr(card, 'data-key') } }));
  }
  function findCard(orderId, key) {
    return toArr(root.querySelectorAll('[data-pp-card]')).filter(function (c) {
      return attr(c, 'data-order-id') === String(orderId) && (key == null || attr(c, 'data-key') === key);
    });
  }
  // 주문 막힘 칸(서버 sync_blocks — 보류 · 도면 고치는 중 · 생산 단계 아님, 글은 서버 글) → 카드 단추 칸 · 칸 숫자. 받아 오기 · 제작 완료 응답(C06 · C09)
  var BLOCK_ATTR = { kind: 'data-pp-block', text: 'data-pp-block-text', why: 'data-pp-block-why', code: 'data-pp-block-code' };
  var STOP_CODES = ['HOLD_ACTIVE', 'DRAWING_REVISING', 'NOT_IN_PRODUCTION']; // 이 거절이면 그 주문 카드를 바로 다시 받는다
  function setBlock(card, b) {
    var keys = Object.keys(BLOCK_ATTR);
    if (keys.every(function (k) { return k === 'code' || attr(card, BLOCK_ATTR[k]) === ((b && b[k]) || ''); })) { return; }
    var before = membership(card);
    keys.forEach(function (k) { if (b && b[k]) { card.setAttribute(BLOCK_ATTR[k], b[k]); } else { card.removeAttribute(BLOCK_ATTR[k]); } });
    var req = card.querySelector('[data-pp-req]'); // [도면 수정 요청] — 고치는 중 · 생산 단계 아님이면 숨김(판이 그릴 때와 같은 규칙)
    if (req) { req.hidden = !!b && (b.kind === 'revise' || b.code === 'NOT_IN_PRODUCTION'); }
    renderAct(card);
    bumpCounts(board.paneOf(card), before, membership(card));
  }

  // ── 쓰기 — 확인 창의 실행 단추에서만 부른다 ──
  function post(url, body) {
    var opts = { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    var offline = { ok: false, kind: 'network', status: 0, data: {}, message: OFFLINE };
    var call = window.fomsMutationFetch || function (u, o) {
      return fetch(u, o).then(function (res) {
        return res.json().then(function (d) { return { ok: res.ok, status: res.status, data: d || {}, message: (d && (d.error || d.message)) || '' }; });
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
    var base = '/api/orders/' + encodeURIComponent(attr(card, 'data-order-id'));
    if (p.action === 'complete') { return { url: base + '/production/complete', body: {} }; }
    if (p.action === 'factory') { return { url: base + '/production/factory-done', body: { factory: p.factory, done: true } }; } // 2공장(§4-14)
    var body = { order_id: Number(attr(card, 'data-order-id')), drawing_key: attr(card, 'data-key'), part: cfg.part, action: p.action,
      seen: attr(card, 'data-state'), seen_me: (crew.of ? crew.of(card).me : '') || 'none' }; // 본 내 몫까지 견준다(multi-holder §7-1)
    if (body.seen === 'need') { body.seen_by = attr(card, 'data-picked-id') ? Number(attr(card, 'data-picked-id')) : null; } // 본 담당까지 견준다(§4-5)
    if (p.target != null) { body.target_user_id = p.target; } // 담당 바꾸기 · 시작 취소 대상
    return { url: '/api/production/part-marks', body: body };
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
  function started(data) { // 첫 카드 = 제작 시작(§4-8) — 그 집 카드의 첫 카드 표지를 뗀다
    var ids = Array.isArray(data.run_started) ? data.run_started : (data.run_started && data.mark ? [data.mark.order_id] : []);
    ids.forEach(function (id) { findCard(id).forEach(function (c) { c.removeAttribute('data-pp-first'); }); });
    return ids.length ? ' · 제작 시작도 같이 됐어요' : '';
  }
  function handle(p, result) {
    var body = result.data || {};
    var data = body.data || {};
    var asks = p.action === 'complete' || p.action === 'factory'; // 제작 완료 물음의 실행(카드 쓰기가 아님)
    if (result.ok && body.success === true) {
      var finished = p.action === 'complete' || (p.action === 'factory' && data.final);
      var done = p.action === 'bulk' ? bulkDone(data) : { text: finished ? '제작 완료했어요 — 시공 대기로 넘어갔어요'
        : p.action === 'factory' ? p.run + '했어요' : '저장했어요', bad: false };
      if (finished) { findCard(attr(p.cards[0], 'data-order-id')).forEach(function (c) { setBlock(c, cfg.done_block); }); } // [되돌리기] 대신 '제작 완료'(C09)
      if (p.action !== 'bulk' && !asks) { p.cards.forEach(function (c) { applyMark(c, data.mark); }); }
      done.text += asks ? '' : started(data);
      setBusy(false);
      var fac = data.factory_ready;
      // 검수 마지막 장 → 같은 창에서 "제작 완료할까요?"(섞인 주문은 공장마다). 시작 취소로 남은 사람이 모두 완료돼 저절로 완료된
      // 누름도 그 누른 사람에게 묻는다(multi-holder §5 풀이 Q6 — 서버가 줄이 DONE 이 된 누름에만 준다)
      if ((data.order_ready || fac) && p.action !== 'bulk') {
        p.action = fac ? 'factory' : 'complete';
        p.factory = fac ? fac.factory : null;
        p.run = fac ? fac.label + ' 제작 완료' : '제작 완료';
        if (fac) { M.complete(p.cards[0], fac, p); } else { M.complete(p.cards[0], findCard(attr(p.cards[0], 'data-order-id')).length || attr(p.cards[0], 'data-of'), p); }
        setStatus(done.text, false);
        return;
      }
      closeModal();
      setStatus(done.text, done.bad);
      if (data.notice && crew.notice) { crew.notice(p.cards[0], data.notice); } // 거의 같이 [작업 시작] — 서버 글 그대로(Q16)
      return;
    }
    setBusy(false);
    if (result.status === 0 || result.kind === 'network' || result.kind === 'timeout') { M.error(OFFLINE); return; }
    var text = body.error || body.message || result.message || OFFLINE;
    if (result.status === 409 || result.status === 403) {
      if (data.mark && p.action !== 'bulk' && !asks) { applyMark(p.cards[0], data.mark); }
      if (STOP_CODES.indexOf(data.code) >= 0 && bound.syncTick) { bound.syncTick(); } // 그 주문 카드를 모두 막힘 칸으로(C06)
      M.lost(text, M.nowLine(data.mark));
      return;
    }
    M.error(text);
  }
  function send() {
    if (!pending || pending.busy || pending.locked || !pending.action) { return; }
    var p = pending;
    var req = requestFor(p);
    setBusy(true);
    post(req.url, req.body).then(function (result) { handle(p, result || {}); });
  }

  // 받아 오기가 쓴다: 고치기 · 카드 찾기 · 이 카드가 내 확인 창에 있거나 저장 중 · 말풍선이 열린 카드인지(그러면 건너뛴다) · 다시 그리기 · 막힘 칸
  window.FomsPartsCards = { apply: applyMark, find: findCard, held: function (card) {
    return (!!pending && pending.cards.indexOf(card) >= 0) || !!(claim.busy && claim.busy(card));
  }, render: renderAct, block: setBlock };
  if (!modal) { return; } // 읽기 전용 — 누름 · 쓰기를 묶지 않는다
  root.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || typeof t.closest !== 'function') { return; }
    if (t === modal) { closeModal(); return; }
    if (t.closest('[data-pp-modal-close]')) { closeModal(); return; }
    var choice = t.closest('[data-pp-choice]'); // 관리자 고르기 — 누른 것이 곧 실행(같은 실행 길), [담당 바꾸기 ›]는 다음 창
    if (choice && pending && !pending.busy && choice.hasAttribute('data-pp-next')) { openModal(choice.getAttribute('data-pp-choice'), pending.cards, choice); return; }
    if (choice && pending && !pending.busy) {
      pending.action = choice.getAttribute('data-pp-choice');
      pending.run = choice.textContent;
      pending.target = choice.hasAttribute('data-pp-target') ? Number(choice.getAttribute('data-pp-target')) : null;
    }
    var who = t.closest('[data-pp-who]'); // [담당 바꾸기] 누구와 — 고르면 실행 단추가 열린다
    if (who && pending && !pending.busy) { pending.target = Number(who.getAttribute('data-pp-who')); pending.locked = false; M.pick(who); return; }
    if (t.closest('[data-pp-modal-run]')) { send(); return; }
    var btn = t.closest('[data-pp-act]');
    if (!btn || modal.contains(btn)) { return; }
    var action = btn.getAttribute('data-pp-act');
    var pane = board.paneOf(btn);
    if (action === 'bulk') {
      openModal('bulk', board.cardsOf(pane).filter(bulkable), btn);
      return;
    }
    openModal(action === 'held' && MINE ? 'takeover' : action, [btn.closest('[data-pp-card]')], btn);
  });
  window.FomsPartsCards.onEscape = function () { if (pending && !modal.hidden) { closeModal(); } }; // Esc 는 viewer 의 문서 리스너 한 번이 부른다
})();

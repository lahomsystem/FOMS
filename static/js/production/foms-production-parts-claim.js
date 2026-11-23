/* 생산 파트 도면 카드 — 맡기 고침의 카드 칸(설계서 2026-11-23 §4-5 · §4-6 · §4-9 · §4-11 · §8-1, 승인 때 고친 것 1).
 * 쓰기 없음(fetch 0) — 카드 단추 그리기(foms-production-parts.js 의 renderAct)가 새 칸을 여기서 받아 그린다:
 *   손 체크 칸(카드 안 쓴 파트 · "재단 완료 · 박반장" + "작업 시트") · 막힌 칸(보류 · 도면 고치는 중 · 검수 전) · 내 담당 한 층
 *   [맡기 취소][<파트> 완료] · 남이 맡은 칸(누르면 [담당 바꾸기] 창, 둘째 줄 어제부터 · 바뀜) · 다른 파트 줄 끝 "내 담당" 꼬리.
 * 막힌 칸 = button aria-disabled — 누르면 카드 키를 안 바꾸는 말풍선(.pp-why)에 서버가 그린 까닭 글. 검수 판은 30초 받아 오기로
 * 같은 장 재단 · 엣지 · 조립이 완료되면 저절로 열린다(recheck — 다른 파트 한 줄 낱말로). 아침 칩("어제부터 내 담당 2장")의 작은 창.
 * "어제부터" · "바뀜 14:20" 은 서버 KST 오늘(cfg.today)과 서버 시각으로만 센다(기기 시계 날짜를 믿지 않는다).
 * 셸 조각 교체로 다시 실행된다: 화면(root) 리스너는 화면마다 한 번(window.__FOMS_PROD_PARTS_BOUND.claim). */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  var board = window.FomsPartsBoard;
  if (!root || !board) { return; }
  var bound = window.__FOMS_PROD_PARTS_BOUND = window.__FOMS_PROD_PARTS_BOUND || {};
  if (bound.claim === root || board.root !== root) { return; }
  bound.claim = root;

  var cfg = board.cfg || {};
  var TODAY = String(cfg.today || '');
  var PRE_PARTS = ['cut', 'edge', 'assemble'];
  function attr(card, name) { return card.getAttribute(name) || ''; }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text) { node.textContent = text; }
    return node;
  }
  function josa(name, a, b) {
    var code = name.charCodeAt(name.length - 1) - 0xAC00;
    return name + (code >= 0 && code < 11172 && code % 28 === 0 ? a : b);
  }

  // ── 날짜 · 시각(서버 값만) ──
  function dayNum(key) { var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(key || ''); return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) / 864e5 : null; }
  function kst(iso) { var t = Date.parse(iso || ''); return isNaN(t) ? null : new Date(t + 9 * 36e5); }
  function md(d) { return (d.getUTCMonth() + 1) + '/' + d.getUTCDate(); }
  function hm(d) { return ('0' + d.getUTCHours()).slice(-2) + ':' + ('0' + d.getUTCMinutes()).slice(-2); }
  function sinceText(pickedDay) {
    var d = dayNum(pickedDay);
    var t = dayNum(TODAY);
    if (d === null || t === null || d >= t) { return ''; }
    if (t - d === 1) { return '어제부터'; }
    var m = /^\d{4}-(\d{2})-(\d{2})$/.exec(pickedDay);
    return Number(m[1]) + '/' + Number(m[2]) + '부터';
  }
  function handedText(from, at) {
    if (!from) { return ''; }
    var d = kst(at);
    var head = from + '에서 바뀜';
    if (!d) { return head; }
    var gap = dayNum(TODAY) - Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) / 864e5;
    return gap <= 0 ? head + ' ' + hm(d) : gap === 1 ? head + ' · 어제' : head + ' · ' + md(d);
  }
  function sinceAt(iso) { var d = kst(iso); return d ? md(d) + ' ' + hm(d) : ''; }
  function heldNote(card) {
    if (attr(card, 'data-state') !== 'need') { return ''; }
    return handedText(attr(card, 'data-handed-from'), attr(card, 'data-handed-at')) || sinceText(attr(card, 'data-picked-day'));
  }

  // ── 막힘: 주문 전체(보류 · 도면 고치는 중) 또는 검수 전(같은 장 앞 파트 미완료) ──
  function preLeft(card) {
    if (cfg.part !== 'inspect') { return []; }
    var hands = ' ' + attr(card, 'data-pp-hands') + ' ';
    return PRE_PARTS.filter(function (p) {
      var span = card.querySelector('[data-pp-other="' + p + '"]');
      var done = hands.indexOf(' ' + p + ' ') >= 0 || (span && (span.classList.contains('pp-w-done') || span.classList.contains('pp-w-basic')));
      return !done;
    }).map(function (p) {
      var span = card.querySelector('[data-pp-other="' + p + '"] i');
      return span ? span.textContent : p;
    });
  }
  function block(card) {
    if (attr(card, 'data-pp-block')) {
      return { kind: attr(card, 'data-pp-block'), text: attr(card, 'data-pp-block-text'), why: attr(card, 'data-pp-block-why') };
    }
    var left = preLeft(card);
    if (!left.length) { return null; }
    var text = left.join(' · ') + ' 미완료';
    var why = text === attr(card, 'data-pp-pre') ? attr(card, 'data-pp-pre-why')
      : '아직 검수할 수 없어요. ' + josa(left.join(' · '), '가', '이') + ' 미완료예요. 완료되면 검수할 수 있어요.';
    return { kind: 'pre', text: text, why: why };
  }
  function whyId(card) { return 'pp-why-' + attr(card, 'data-order-id') + '-' + attr(card, 'data-no'); }
  function chip(card, cls, why) {
    var btn = el('button', 'fph-wi pp-act ' + cls);
    btn.type = 'button';
    btn.setAttribute('aria-disabled', 'true');
    btn.setAttribute('aria-describedby', whyId(card));
    btn.setAttribute('data-pp-why', why || '');
    return btn;
  }
  function blockChip(card, b) { var btn = chip(card, 'pp-st-' + b.kind, b.why); btn.textContent = b.text; return btn; }
  function held(card, head, cls) {
    var btn = el('button', 'fph-wi pp-act ' + cls + ' pp-held');
    btn.type = 'button';
    btn.setAttribute('data-pp-act', 'held');
    var note = heldNote(card);
    btn.setAttribute('aria-label', head + (note ? ' · ' + note : ''));
    var who = el('span', 'pp-held__who');
    who.appendChild(el('b', '', head));
    if (note) { who.appendChild(el('small', '', note)); }
    btn.appendChild(who);
    var go = el('span', 'pp-held__go', '›');
    go.setAttribute('aria-hidden', 'true');
    btn.appendChild(go);
    return btn;
  }
  function actBtn(cls, text, act) { var b = el('button', cls, text); b.type = 'button'; b.setAttribute('data-pp-act', act); return b; }

  // renderAct(parts.js)가 먼저 부른다 — 새 칸이면 그려 넣고 true(지금 칸은 parts.js 가 지금 글 그대로 그린다)
  function special(card, box, c) {
    var st = attr(card, 'data-state');
    if (st === 'hand') {
      var hand = chip(card, 'pp-st-done pp-hand', attr(card, 'data-pp-hand-why'));
      hand.appendChild(el('span', '', attr(card, 'data-pp-hand')));
      hand.appendChild(el('small', '', '작업 시트'));
      box.appendChild(hand);
      return true;
    }
    if (!c.writable || (st !== 'none' && st !== 'need')) { return false; }
    var b = block(card);
    if (st === 'none') { if (b) { box.appendChild(blockChip(card, b)); } return !!b; }
    if (attr(card, 'data-picked-me') === '1') {
      var two = el('div', 'pp-two is-mine');
      two.appendChild(actBtn('foms-prod-home__btn pp-release', '맡기 취소', 'release'));
      two.appendChild(b ? blockChip(card, b) : actBtn('fph-qr__done pp-act pp-fin is-pair', c.label + ' 완료', 'done'));
      box.appendChild(two);
      return true;
    }
    if (c.mine && b) { box.appendChild(blockChip(card, b)); return true; }
    return false;
  }

  // 다른 파트 줄 끝 "내 담당 · 어제부터 · 박엣지에서 바뀜"(내 담당 장만, 줄을 안 넘기고 끝부터 말줄임 — 다 푼 글은 aria-label)
  function renderTag(card, writable) {
    var line = card.querySelector('.pp-by');
    if (!line) { return; }
    var old = line.querySelector('[data-pp-tag]');
    if (old) { line.removeChild(old); }
    var mine = writable && attr(card, 'data-state') === 'need' && attr(card, 'data-picked-me') === '1';
    line.classList.toggle('has-tag', mine);
    if (!mine) { return; }
    var from = attr(card, 'data-handed-from');
    var since = from ? '' : sinceText(attr(card, 'data-picked-day'));
    var tag = el('span', 'pp-tag', '내 담당');
    tag.setAttribute('data-pp-tag', '');
    tag.setAttribute('aria-label', ['내 담당', since, handedText(from, attr(card, 'data-handed-at'))].filter(Boolean).join(' · '));
    if (since) { tag.appendChild(document.createTextNode(' · ')); tag.appendChild(el('span', 'is-old', since)); }
    if (from) { tag.appendChild(document.createTextNode(' · ')); tag.appendChild(el('span', 'is-chg', from + '에서 바뀜')); }
    line.appendChild(tag);
  }
  // 받은 표시(쓰기 응답 · 30초 받아 오기) → 3판 칸 data-*
  function setMarkAttrs(card, mark) {
    card.setAttribute('data-picked-id', mark.picked_by_user_id != null ? String(mark.picked_by_user_id) : '');
    card.setAttribute('data-picked-day', mark.picked_day || '');
    card.setAttribute('data-picked-at', mark.picked_at || '');
    card.setAttribute('data-handed-from', mark.handed_from_name || '');
    card.setAttribute('data-handed-at', mark.handed_at || '');
  }

  // ── 까닭 말풍선 ──
  var openWhy = null;
  var whyTimer = 0;
  var WHY_MS = 6000; // 말풍선은 6초 뒤 저절로 닫힌다(열린 채 두면 받아 오기가 그 카드를 계속 건너뛴다)
  function hideWhy() {
    window.clearTimeout(whyTimer);
    if (!openWhy) { return; }
    openWhy.hidden = true;
    openWhy.textContent = '';
    openWhy = null;
  }
  function showWhy(btn) {
    var card = btn.closest('[data-pp-card]');
    var bubble = card && card.querySelector('.pp-why');
    if (!bubble) { return; }
    if (openWhy === bubble) { hideWhy(); return; }
    hideWhy();
    bubble.textContent = btn.getAttribute('data-pp-why') || '';
    bubble.hidden = !bubble.textContent;
    openWhy = bubble.hidden ? null : bubble;
    if (openWhy) { whyTimer = window.setTimeout(hideWhy, WHY_MS); }
  }
  // 받아 오기는 말풍선이 열린 카드를 건너뛴다(누른 칸이 사라지지 않게)
  function busy(card) { return !!openWhy && card.contains(openWhy); }

  // ── 아침 칩 ──
  function setChip(open) {
    var chipBtn = root.querySelector('[data-pp-mchip]');
    var pop = root.querySelector('[data-pp-mpop]');
    if (!chipBtn || !pop) { return; }
    pop.hidden = !open;
    chipBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  root.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || typeof t.closest !== 'function') { return; }
    var why = t.closest('[data-pp-why]');
    if (why) { showWhy(why); return; }
    if (t.closest('[data-pp-mchip]')) { var pop = root.querySelector('[data-pp-mpop]'); setChip(!!pop && pop.hidden); return; }
    if (!t.closest('[data-pp-mpop]')) { setChip(false); }
    if (!t.closest('.pp-why')) { hideWhy(); }
  });
  root.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') { return; }
    hideWhy();
    var pop = root.querySelector('[data-pp-mpop]');
    if (pop && !pop.hidden) { setChip(false); var c = root.querySelector('[data-pp-mchip]'); if (c) { c.focus(); } }
  });

  // 검수 판: 다른 파트 낱말이 바뀐 카드의 막힘을 다시 본다(앞 파트가 다 완료되면 저절로 열림)
  function recheck(card) {
    var cards = window.FomsPartsCards;
    if (cfg.part === 'inspect' && cards && cards.render) { cards.render(card); }
  }

  window.FomsPartsClaim = { special: special, held: held, renderTag: renderTag, setMarkAttrs: setMarkAttrs, busy: busy,
    recheck: recheck, heldNote: heldNote, sinceAt: sinceAt, hideWhy: hideWhy, josa: josa };
})();

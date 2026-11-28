/* 생산 새 흐름 — 위 탭 숫자 · 담으면 판에서 빼기 · '내 공정' 띠 거르기 · 받아 오기 뒤 다시 받기(설계서 2026-11-28-production-my-steps-flow
 * §3-1 · §3-2 · §3-4 · §3-6, 사장님 답 2 · 19 · 24 · 31). 태블릿 문 안(템플릿 flow)에서만 싣는다 — PC · 폰은 이 파일이 없다.
 *   위 탭 숫자: 서버가 None 으로 그린 탭(남은 공정 · 바뀐 것 · 찾기 — 숨긴 숫자 칸)은 GET ?view=counts 한 번으로 채운다.
 *   날짜 판(파트 계정): [<파트> 시작] · [같이 작업] 등으로 내 카드가 되면 판에서 빼고 '전체 도면' 칸 숫자 −1 · '내 공정 N' +1, 알림 뒤에
 *     " · 내 공정에 담았어요"(parts.js 가 bound.flowWrote 의 돌려준 글을 붙인다). 반장 · 관리자 판은 아무 카드도 안 빠진다(숫자만 다시 받기).
 *   '내 공정' · '작업 중': 내 쓰기가 성공하면 그 화면을 다시 받아 바꿔 끼운다(오늘 끝낸 것 · 띠 숫자 · 묶음 · 탭 숫자 = 서버 글 그대로) —
 *     창 · 크게 보기가 열린 동안은 닫힐 때까지 미룬다. '내 공정' 띠 줄은 화면 거르기(카드 data-day, 요청 없음).
 *   30초 받아 오기(parts-sync.js 의 bound.flowSynced · flowOrphan): "내 것이 됐다 / 아니게 됐다"면 날짜 탭은 그 날 장(?view=day)을,
 *     '내 공정'은 화면을 다시 받는다. '작업 중'은 카드가 바뀌면 화면을 다시 받는다(사람 묶음 · 미정 숫자).
 *   파트가 섞인 화면('작업 중' 전체 · 여러 파트 계정 '내 공정')은 창 글 · 다시 그린 단추 글의 파트 이름을 카드 data-part-label 로 고쳐 끼운다
 *     (창 · 칸 JS 가 판 파트 이름을 상수로 쥐고 있어서 — 쓰기 요청의 part 는 parts.js 가 카드 data-part 로 보낸다).
 * 셸 조각 교체로 다시 실행된다 — 화면마다 한 번(window.__FOMS_PROD_PARTS_BOUND.flow). */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  if (!root) { return; }
  var bound = window.__FOMS_PROD_PARTS_BOUND = window.__FOMS_PROD_PARTS_BOUND || {};
  if (bound.flow === root) { return; }
  bound.flow = root;

  var TAB = root.getAttribute('data-foms-home-tab') || 'date';
  var board = window.FomsPartsBoard && window.FomsPartsBoard.root === root ? window.FomsPartsBoard : null;
  var cfg = (board && board.cfg) || {};
  var FLOW = (cfg.flow && cfg.flow.tab) || '';
  var MINE = cfg.mode === 'part';
  var HEAD = cfg.label || '';
  var SAID = ' · 내 공정에 담았어요'; // 사장님 답 31 "재단 시작했어요 · 내 공정에 담았어요"
  var WAIT_MS = 400;
  function toArr(list) { return [].slice.call(list || []); }
  function attr(n, k) { return (n && n.getAttribute(k)) || ''; }
  function q(sel) { return root.querySelector(sel); }
  function http(url, accept) {
    try {
      return fetch(url, { method: 'GET', credentials: 'same-origin', cache: 'no-store', headers: { Accept: accept, 'X-Requested-With': 'XMLHttpRequest' } })
        .catch(function () { return null; });
    } catch (e) { return Promise.resolve(null); }
  }
  function pageUrl(extra) {
    var u = new URL(window.location.href);
    Object.keys(extra || {}).forEach(function (k) { u.searchParams.set(k, extra[k]); });
    return u.toString();
  }

  // ── 위 탭 숫자(내 공정 N · 작업 중 N) ──
  function countEl(key) { return q('[data-flow-count="' + key + '"]'); }
  function setCount(key, n) {
    var s = countEl(key);
    if (!s || typeof n !== 'number' || n < 0) { return; }
    s.textContent = String(n);
    s.hidden = false;
  }
  function bump(key, d) { var s = countEl(key); if (s && !s.hidden) { setCount(key, Math.max(0, Number(s.textContent || 0) + d)); } }
  function recount(all) { // 숫자만 받는 길 — all 이면 보이는 숫자도 새로(반장 판 쓰기 · 받아 오기로 다시 받은 날 장 뒤)
    var keys = toArr(root.querySelectorAll('[data-flow-count]')).filter(function (s) { return all || s.hidden; });
    if (!keys.length) { return; }
    http(pageUrl({ view: 'counts' }), 'application/json').then(function (res) { return res && res.ok ? res.json() : null; })
      .then(function (body) {
        var c = body && body.success === true && body.data ? body.data.counts : null;
        if (c && document.contains(root)) { keys.forEach(function (s) { setCount(attr(s, 'data-flow-count'), c[attr(s, 'data-flow-count')]); }); }
      }).catch(function () { /* 못 받으면 그대로 — 다음에 화면을 받으면 맞는다 */ });
  }

  // ── 열린 창 · 크게 보기가 닫힐 때까지 미루기(다시 받은 화면이 창이 붙든 카드를 바꾸지 않게) ──
  function busy() {
    var modal = q('[data-pp-modal]');
    var viewer = q('[data-pp-viewer]');
    return !!((modal && !modal.hidden) || (viewer && !viewer.hidden));
  }
  function whenFree(fn) { if (busy()) { window.setTimeout(function () { whenFree(fn); }, WAIT_MS); } else { fn(); } }
  function parse(html) { var tpl = document.createElement('template'); tpl.innerHTML = html; return tpl.content; }

  // ── 다시 받기는 한 번에 하나 — 받는 중에 또 부르면 끝난 뒤 한 번 더(받아 오기 한 번에 여러 카드가 바뀌어도 받기 한 번) ──
  function single(load) {
    var st = { on: false, again: false };
    function run() {
      if (st.on) { st.again = true; return; }
      st.on = true;
      load().catch(function () { /* 못 받으면 그대로 — 다음에 화면을 받으면 맞는다 */ }).then(function () {
        st.on = false;
        if (st.again) { st.again = false; run(); }
      });
    }
    return run;
  }
  // ── '내 공정' · '작업 중' 화면 다시 받기(같은 주소) ──
  var reloadScreen = single(function () {
    return http(window.location.href, 'text/html').then(function (res) { return res && res.ok ? res.text() : null; }).then(function (html) {
      if (html) { whenFree(function () { swapScreen(parse(html)); }); }
    });
  });
  function swapScreen(doc) {
    var cur = q('[data-flow-screen]');
    var fresh = doc.querySelector('[data-flow-screen]');
    if (!cur || !fresh || !document.contains(root)) { return; }
    var day = picked;
    cur.parentNode.replaceChild(fresh, cur);
    toArr(doc.querySelectorAll('[data-flow-count]')).forEach(function (s) { if (!s.hidden) { setCount(attr(s, 'data-flow-count'), Number(s.textContent)); } });
    if (day !== 'all') { filterDay(q('[data-flow-day="' + day + '"]') ? day : 'all'); }
  }

  // ── 날짜 탭: 고른 날 장 다시 받기(?view=day — 날 고르기와 같은 길). 받아 둔 다른 날 장은 버린다(누르면 새로 받는다) ──
  var reloadDay = single(function () {
    var btn = q('[data-foms-home-daybtn].is-on');
    var key = attr(btn, 'data-foms-home-daybtn');
    if (!key) { return Promise.resolve(); }
    return http(pageUrl({ day: key, view: 'day' }), 'text/html').then(function (res) {
      return res && res.ok && res.headers.get('X-FOMS-HOME-DAY') === key ? res.text() : null;
    }).then(function (html) {
      if (!html) { return; }
      whenFree(function () {
        var fresh = parse(html).querySelector('[data-foms-home-daypane]');
        var cur = toArr(root.querySelectorAll('[data-foms-home-daypane]')).filter(function (p) { return attr(p, 'data-foms-home-daypane') === key; })[0];
        if (!fresh || !cur) { return; }
        toArr(root.querySelectorAll('[data-foms-home-daypane]')).forEach(function (p) { if (p !== cur) { p.parentNode.removeChild(p); } });
        cur.parentNode.replaceChild(fresh, cur);
        recount(true);
      });
    });
  });

  // ── 날짜 판(파트 계정): 내 카드가 되면 판에서 뺀다 ──
  function mineNow(card) { return attr(card, 'data-state') === 'need' && attr(card, 'data-picked-me') === '1'; }
  function leave(card) {
    var pane = board.paneOf(card);
    var all = pane && pane.querySelector('[data-pp-count="all"]');
    if (all) { all.textContent = String(Math.max(0, Number(all.textContent || 0) - 1)); }
    if (card.parentNode) { card.parentNode.removeChild(card); }
    if (pane) { board.applyView(pane); } // 판이 비면 빈 화면 글
    bump('mine', 1);
  }
  // parts.js 가 쓰기 성공 뒤(카드 고치기 다음) 부른다 — 알림 뒤에 붙일 글을 돌려준다
  bound.flowWrote = function (action, cards, data) {
    if (bound.flow !== root) { return ''; }
    if (TAB === 'mine' || TAB === 'crew') { reloadScreen(); return ''; }
    if (FLOW === 'crew') { recount(true); return ''; } // 반장 · 관리자 날짜 · 도면 카드 판 — 카드는 그대로, '작업 중 N'만 새로
    if (FLOW !== 'mine' || !MINE || !board) { return ''; }
    var moved = (cards || []).filter(function (c) { return document.contains(c) && mineNow(c); });
    moved.forEach(leave);
    return moved.length ? SAID : '';
  };

  // ── 30초 받아 오기 뒤 ──
  function myPart(part) {
    var scr = q('[data-flow-screen="mine"]');
    var list = scr ? attr(scr, 'data-flow-parts').split(' ') : [cfg.part];
    return list.indexOf(part) >= 0;
  }
  bound.flowSynced = function (card, mark) {
    if (bound.flow !== root) { return; }
    if (TAB === 'crew') { reloadScreen(); return; }
    var me = (mark.crew || {}).me || 'none';
    if (TAB === 'mine') {
      var done = !!card.closest('[data-flow-done]');
      if (done ? me !== 'done' : !mineNow(card)) { reloadScreen(); }
      return;
    }
    if (FLOW === 'mine' && MINE && mineNow(card)) { reloadDay(); } // 반장이 담당을 나에게 줌
  };
  bound.flowOrphan = function (mark) { // 화면에 그 장 카드가 없는 표시 줄
    if (bound.flow !== root || !myPart(mark.part)) { return; }
    var me = (mark.crew || {}).me || 'none';
    if (mark.drawing_key === '@order' && (mark.state || 'none') === 'none') { return; } // 도면이 온 뒤 남은 주문 카드 미정 줄 — 조용히 버린다
    var other = toArr(root.querySelectorAll('[data-pp-elsewhere]')).some(function (c) {
      return attr(c, 'data-order-id') === String(mark.order_id) && attr(c, 'data-key') === mark.drawing_key;
    });
    if (other) { return; }
    if (TAB === 'mine' && me === 'held') { reloadScreen(); } // 반장이 나에게 준 장(화면에 없던 장)
    if (TAB !== 'mine' && FLOW === 'mine' && MINE && me !== 'held') { reloadDay(); } // 내 것이 아니게 됨(남에게 넘김) · 끝낸 장이 판으로 돌아옴
  };

  // ── '내 공정' 띠 거르기(화면만) ──
  var picked = 'all';
  function shownIn(box) { return toArr(box.querySelectorAll('[data-pp-card]')).filter(function (c) { return !c.classList.contains('fpf-off'); }).length; }
  function filterDay(key) {
    var scr = q('[data-flow-screen="mine"]');
    if (!scr) { return; }
    picked = key || 'all';
    toArr(scr.querySelectorAll('[data-flow-day]')).forEach(function (b) {
      var on = attr(b, 'data-flow-day') === picked;
      b.classList.toggle('is-on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    toArr(scr.querySelectorAll('[data-pp-card]')).forEach(function (c) { c.classList.toggle('fpf-off', picked !== 'all' && attr(c, 'data-day') !== picked); });
    toArr(scr.querySelectorAll('[data-flow-group="order"], [data-flow-group="day"]')).forEach(function (g) { g.hidden = !shownIn(g); });
    var done = scr.querySelector('[data-flow-done]');
    var doneN = scr.querySelector('[data-flow-done-n]');
    if (done && doneN) { doneN.textContent = String(shownIn(done)); }
    var empty = scr.querySelector('[data-flow-empty]');
    var active = toArr(scr.querySelectorAll('[data-flow-group="day"]')).some(function (g) { return !g.hidden; });
    if (empty) { empty.hidden = active; }
  }
  root.addEventListener('click', function (e) {
    var t = e.target;
    var row = t && typeof t.closest === 'function' ? t.closest('[data-flow-day]') : null;
    if (row) { filterDay(attr(row, 'data-flow-day')); }
  });

  // ── 파트가 섞인 화면: 창 글 · 다시 그린 단추 글의 파트 이름을 카드 파트로(판 파트 이름이 상수로 박힌 글만 바꾼다) ──
  function relabel(text, label) {
    if (!text || !label || !HEAD || label === HEAD) { return text; }
    return String(text).replace(new RegExp('(^|[\\s\\[(→·])' + HEAD + '(?=[\\s\\u00a0]|$)', 'g'), '$1' + label);
  }
  function relabelTree(node, label) {
    toArr(node.children).filter(function (n) { return n.nodeType === 1; }).forEach(function (n) {
      if (toArr(n.children).some(function (k) { return k.nodeType === 1; })) { relabelTree(n, label); } else { n.textContent = relabel(n.textContent, label); }
    });
  }
  function labelOf(part) { return attr(q('[data-pp-card][data-part="' + part + '"]'), 'data-part-label'); }
  var M = window.FomsPartsModal;
  var C = window.FomsPartsCrew;
  if ((TAB === 'mine' || TAB === 'crew') && board && M && C && !M.flowWrapped) {
    M.flowWrapped = true;
    var plan = M.plan;
    var nowLine = M.nowLine;
    var render = C.render;
    M.plan = function (action, card) {
      var p = plan(action, card);
      var label = card ? attr(card, 'data-part-label') : '';
      if (p && label) { ['title', 'line', 'run', 'note'].forEach(function (k) { if (typeof p[k] === 'string') { p[k] = relabel(p[k], label); } }); }
      return p;
    };
    M.nowLine = function (mark) { return relabel(nowLine(mark), mark ? labelOf(mark.part) : ''); };
    C.render = function (card, box, o) {
      var drawn = render(card, box, o);
      var label = attr(card, 'data-part-label');
      if (label && label !== HEAD) { relabelTree(box, label); }
      return drawn;
    };
  }

  recount(false); // 숫자 없이 그린 탭(남은 공정 · 바뀐 것 · 찾기)
})();

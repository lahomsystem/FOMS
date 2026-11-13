/* 생산 파트 도면 카드 — 보는 쪽(쓰기 없음). 설계서 §15.6 칸 단추 · '크게 보기'(시안 f63), P15-5.
 * 읽기 전용 직원도 싣는다(D55): 칸 단추 셋(보이기/숨기기만, 새 요청 없음) · 크게 보기(원본 한 장 · 같은 주문 장끼리 ◀ ▶ ·
 * 그림을 한 번 더 누르면 GlobalImageViewer 손가락 확대) · 그림을 못 받으면(원본 없음 404) 깨진 그림 대신 글 · '도면 카드' 탭의 날 주소.
 * 크게 보기의 큰 단추는 카드 단추를 대신 누른다(같은 확인 창 — 쓰기는 foms-production-parts.js 몫, 이 파일엔 fetch 없음).
 * 설정은 data-foms-parts-config(safeJsonParse). 전역 리스너는 window.__FOMS_PROD_PARTS_BOUND.viewer 로 한 번만. */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  var holder = root && root.querySelector('[data-foms-parts-config]');
  if (!root || !holder) { return; }
  var bound = window.__FOMS_PROD_PARTS_BOUND = window.__FOMS_PROD_PARTS_BOUND || {};
  if (bound.viewer) { return; }
  bound.viewer = true;

  function safeJsonParse(value, fallback) {
    try {
      var text = String(value || '').trim();
      return text ? JSON.parse(text) : fallback;
    } catch (e) {
      return fallback;
    }
  }
  function toArr(list) { return [].slice.call(list || []); }

  var cfg = safeJsonParse(holder.getAttribute('data-foms-parts-config'), {}) || {};
  var EMPTY_TEXT = { need: '작업 필요 도면이 없어요.', done: '완료한 도면이 없어요.' };
  var BROKEN_TEXT = '그림을 못 불러왔어요';

  // ── 그림을 못 받을 때: 그림을 숨기고 그 자리에 글(카드 · 크게 보기 같은 글, 인라인 오류 속성 없음) ──
  function markBroken(img) {
    var box = img && img.parentNode;
    if (!box || !img.getAttribute('src')) { return; }
    img.hidden = true;
    box.classList.add('is-broken');
    if (box.querySelector('.pp-broken')) { return; }
    var note = document.createElement('span');
    note.className = 'pp-broken';
    note.textContent = BROKEN_TEXT;
    box.appendChild(note);
  }
  function clearBroken(img) {
    var box = img && img.parentNode;
    if (!box) { return; }
    box.classList.remove('is-broken');
    var note = box.querySelector('.pp-broken');
    if (note) { box.removeChild(note); }
    img.hidden = false;
  }

  // ── 칸 단추 셋: 전체 도면 · 작업 필요 · 완료(보이기/숨기기만) ──
  function paneOf(el) { return el && el.closest('[data-pp-pane]'); }
  function cardsOf(pane) { return toArr(pane.querySelectorAll('[data-pp-card]')); }
  function inView(card, view) {
    if (view === 'need') { return card.getAttribute('data-in-need') === '1'; }
    if (view === 'done') { return card.getAttribute('data-in-done') === '1'; }
    return true;
  }
  function applyView(pane, view) {
    if (!pane) { return; }
    view = view || pane.getAttribute('data-pp-on') || 'all';
    pane.setAttribute('data-pp-on', view);
    toArr(pane.querySelectorAll('[data-pp-view]')).forEach(function (tab) {
      var on = tab.getAttribute('data-pp-view') === view;
      tab.classList.toggle('is-on', on);
      tab.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    var grid = pane.querySelector('[data-pp-grid]');
    if (grid) {
      grid.classList.toggle('is-need', view === 'need');
      grid.classList.toggle('is-done', view === 'done');
    }
    var shown = 0;
    cardsOf(pane).forEach(function (card) {
      var ok = inView(card, view);
      card.hidden = !ok;
      if (ok) { shown += 1; }
    });
    var empty = pane.querySelector('[data-pp-empty]');
    if (empty) {
      if (!empty.hasAttribute('data-pp-empty-all')) { empty.setAttribute('data-pp-empty-all', empty.textContent); }
      empty.textContent = EMPTY_TEXT[view] || empty.getAttribute('data-pp-empty-all');
      empty.hidden = shown > 0;
    }
  }

  // ── 크게 보기 ──
  var viewer = root.querySelector('[data-pp-viewer]');
  var vImg = viewer && viewer.querySelector('[data-pp-v-img]');
  var state = { list: [], index: 0, opener: null };
  function cardText(card, sel) {
    var el = card.querySelector(sel);
    return el ? el.textContent.replace(/\s+/g, ' ').trim() : '';
  }
  function orderCards(card) {
    var oid = card.getAttribute('data-order-id');
    return cardsOf(paneOf(card)).filter(function (c) { return c.getAttribute('data-order-id') === oid; })
      .sort(function (a, b) { return Number(a.getAttribute('data-no')) - Number(b.getAttribute('data-no')); });
  }
  function fillActions(card) {
    var box = viewer.querySelector('[data-pp-v-act]');
    box.textContent = '';
    var buttons = toArr(card.querySelectorAll('[data-pp-actbox] [data-pp-act]'));
    var badge = card.querySelector('[data-pp-actbox] .fph-wi:not(.pp-only-need):not(.pp-only-done)');
    (buttons.length ? buttons : (badge ? [badge] : [])).forEach(function (el) {
      var copy = el.cloneNode(true);
      copy.classList.remove('pp-only-need', 'pp-only-done', 'pp-not-need', 'pp-not-done', 'pp-act');
      if (copy.hasAttribute('data-pp-act')) {
        copy.setAttribute('data-pp-proxy', copy.getAttribute('data-pp-act'));
        copy.removeAttribute('data-pp-act');
      }
      box.appendChild(copy);
    });
  }
  function render() {
    var card = state.list[state.index];
    if (!card || !viewer) { return; }
    var head = paneOf(card).querySelector('.pp-head .fph-pane__h');
    var day = head && head.firstChild ? head.firstChild.textContent.trim() : '';
    viewer.querySelector('[data-pp-v-title]').textContent = cardText(card, '.fph-dr__nm');
    viewer.querySelector('[data-pp-v-sub]').textContent = cardText(card, '.pp-item') + (day ? ' · ' + day + ' 시공' : '');
    viewer.querySelector('[data-pp-v-page]').textContent = card.getAttribute('data-no') + ' / ' + card.getAttribute('data-of');
    var by = viewer.querySelector('[data-pp-v-by]');
    var src = card.querySelector('.pp-by');
    by.textContent = '';
    toArr(src ? src.childNodes : []).forEach(function (n) { by.appendChild(n.cloneNode(true)); });
    var isImage = !!card.querySelector('[data-pp-open]');
    clearBroken(vImg);
    vImg.hidden = !isImage;
    if (isImage) { vImg.src = card.getAttribute('data-view-url') || ''; }
    viewer.querySelector('[data-pp-v-zoom]').setAttribute('aria-label', isImage ? '손가락으로 크게 보기' : '파일 열기');
    toArr(viewer.querySelectorAll('[data-pp-v-step]')).forEach(function (btn) {
      var next = state.index + Number(btn.getAttribute('data-pp-v-step'));
      btn.disabled = next < 0 || next >= state.list.length;
    });
    fillActions(card);
  }
  function openViewer(card, opener) {
    if (!viewer) { return; }
    state.list = orderCards(card);
    state.index = Math.max(0, state.list.indexOf(card));
    state.opener = opener || null;
    viewer.hidden = false;
    render();
    var close = viewer.querySelector('[data-pp-v-close]');
    if (close) { close.focus(); }
  }
  function closeViewer() {
    if (!viewer || viewer.hidden) { return; }
    viewer.hidden = true;
    vImg.removeAttribute('src');
    if (state.opener && typeof state.opener.focus === 'function') { state.opener.focus(); }
  }
  function zoom() {
    var card = state.list[state.index];
    if (!card) { return; }
    if (!card.querySelector('[data-pp-open]')) {
      window.open(card.getAttribute('data-view-url') || '', '_blank', 'noopener');
      return;
    }
    var files = state.list.filter(function (c) { return !!c.querySelector('[data-pp-open]'); });
    var gv = window.GlobalImageViewer;
    if (!gv || typeof gv.open !== 'function') { return; }
    gv.open(files.map(function (c) {
      return { key: c.getAttribute('data-key'), view_url: c.getAttribute('data-view-url'),
        filename: cardText(c, '.fph-dr__nm') + ' ' + c.getAttribute('data-no') + '/' + c.getAttribute('data-of') };
    }), Math.max(0, files.indexOf(card)));
  }
  function proxy(btn) {
    var card = state.list[state.index];
    var real = card && card.querySelector('[data-pp-actbox] [data-pp-act="' + btn.getAttribute('data-pp-proxy') + '"]');
    if (real) { real.click(); }
  }

  // ── '도면 카드' 탭(관리자 · 읽기 전용): 날을 바꿔도 주소에 탭 · 파트를 남긴다(날 고르기는 foms-production-home.js) ──
  function keepPartsTabUrl(dayBtn) {
    if (root.getAttribute('data-foms-home-tab') !== 'parts') { return; }
    var url = window.location.pathname + '?tab=parts&part=' + encodeURIComponent(cfg.part || 'cut') +
      '&day=' + encodeURIComponent(dayBtn.getAttribute('data-foms-home-daybtn') || '');
    try { window.history.replaceState(window.history.state, '', url); } catch (e) { /* 주소를 못 바꿔도 화면은 그대로 */ }
    var reload = root.querySelector('[data-foms-home-reload]');
    if (reload) { reload.setAttribute('href', url); }
  }

  root.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || typeof t.closest !== 'function') { return; }
    var tab = t.closest('[data-pp-view]');
    if (tab) { applyView(paneOf(tab), tab.getAttribute('data-pp-view')); return; }
    var open = t.closest('[data-pp-open]');
    if (open) { openViewer(open.closest('[data-pp-card]'), open); return; }
    var dayBtn = t.closest('[data-foms-home-daybtn]');
    if (dayBtn) { keepPartsTabUrl(dayBtn); return; }
    if (!viewer || viewer.hidden || !viewer.contains(t)) { return; }
    var step = t.closest('[data-pp-v-step]');
    if (step && !step.disabled) { state.index += Number(step.getAttribute('data-pp-v-step')); render(); return; }
    if (t.closest('[data-pp-v-close]')) { closeViewer(); return; }
    if (t.closest('[data-pp-v-zoom]')) { zoom(); return; }
    var px = t.closest('[data-pp-proxy]');
    if (px) { proxy(px); }
  });
  document.addEventListener('keydown', function (e) {
    var modal = root.querySelector('[data-pp-modal]');
    if (e.key === 'Escape' && (!modal || modal.hidden)) { closeViewer(); }
  });
  // 카드 작은 그림 · 크게 보기 원본을 못 받으면 글(카드는 그대로 쓸 수 있다). error 는 거품이 안 올라 잡기 단계로 받는다.
  root.addEventListener('error', function (e) {
    var img = e.target;
    if (img && img.tagName === 'IMG' && (img.classList.contains('pp-thumb') || img === vImg)) { markBroken(img); }
  }, true);
  // defer 라 이 파일보다 먼저 실패한 그림(첫 화면 장)은 error 를 놓친다 — 끝난 채 크기 0 인 그림을 한 번 훑는다.
  toArr(root.querySelectorAll('img.pp-thumb')).forEach(function (img) {
    if (img.complete && img.naturalWidth === 0) { markBroken(img); }
  });
  // 쓰기 쪽이 카드를 고치면 열린 크게 보기도 같은 상태로
  document.addEventListener('foms:part-card-updated', function () { if (viewer && !viewer.hidden) { render(); } });

  window.FomsPartsBoard = { cfg: cfg, applyView: applyView, paneOf: paneOf, cardsOf: cardsOf, closeViewer: closeViewer };
})();

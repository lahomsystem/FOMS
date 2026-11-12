/**
 * 태블릿 가로 출고 탭 위 줄 — 날짜 버튼 띠 넘기기 · 돋보기 검색칸 · [더보기 ▾] 여닫기
 * (설계서 docs/specs/2026-11-09-tablet-production-ui_SPEC.md §14.10 P14-8 · 시안 안 28).
 * - 날짜 버튼은 <a href="?date=…"> 라 누르면 셸(erp-shell.js 의 a[href] 가로채기)이 조각만 바꿔 연다 — 여기선 손대지 않는다.
 * - [◀] [▶] = 띠(data-ship-days-track)를 7개만큼 민다. 새로 읽지 않는다. 손가락 밀기는 CSS scroll-snap.
 * - 처음 열 때(셸 조각이 바뀐 뒤도) 고른 날이 든 7개 묶음이 보이게 띠를 맞춘다.
 * - 아래로 펼치는 작은 창 둘([data-ship-pop]: 돋보기 검색칸 · 더보기) = is-open 을 붙였다 뗀다. 하나를 열면 다른 하나는 닫고,
 *   밖을 누르거나 Esc 면 닫는다. 검색칸을 열면 커서를 둔다. 더보기 안 남은 자수 · 이미지 저장을 누르면 닫는다.
 * 실리는 곳 = shipment-entry.js CHAIN(문서 위임 싱글턴).
 */
(function () {
  'use strict';
  if (window.__FOMS_SHIP_DATEBAR_BOUND) return;
  window.__FOMS_SHIP_DATEBAR_BOUND = true;

  var PAGE = 7;
  var TOGGLE = '[data-ship-more-toggle], [data-ship-search-toggle]';

  function step(track) {
    var a = track.querySelector('.foms-ship-day');
    if (!a) return 0;
    var gap = parseFloat(window.getComputedStyle(track).columnGap) || 0;
    return a.getBoundingClientRect().width + gap;
  }

  function syncNav(track) {
    var box = track.closest('.foms-ship-days');
    if (!box) return;
    var max = track.scrollWidth - track.clientWidth - 1;
    var prev = box.querySelector('[data-ship-days-nav="-1"]');
    var next = box.querySelector('[data-ship-days-nav="1"]');
    if (prev) prev.disabled = track.scrollLeft <= 1;
    if (next) next.disabled = track.scrollLeft >= max;
  }

  function showSelected(track) {
    var days = track.querySelectorAll('.foms-ship-day');
    var idx = 0;
    for (var i = 0; i < days.length; i++) {
      if (days[i].classList.contains('is-selected')) { idx = i; break; }
    }
    var first = days[Math.floor(idx / PAGE) * PAGE];
    track.scrollLeft = first ? first.offsetLeft - days[0].offsetLeft : 0;
    syncNav(track);
  }

  function setPop(wrap, open) {
    wrap.classList.toggle('is-open', open);
    var btn = wrap.querySelector(TOGGLE);
    if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    var q = open && wrap.querySelector('.foms-ship-pcbar__filter-q');
    if (q) q.focus();
  }

  function closePops(except) {
    var all = document.querySelectorAll('[data-ship-pop].is-open');
    for (var i = 0; i < all.length; i++) if (all[i] !== except) setPop(all[i], false);
  }

  document.addEventListener('click', function (ev) {
    var t = ev.target;
    if (!t || !t.closest) return;
    var nav = t.closest('[data-ship-days-nav]');
    if (nav) {
      var track = nav.closest('.foms-ship-days').querySelector('[data-ship-days-track]');
      var dir = Number(nav.getAttribute('data-ship-days-nav')) || 1;
      if (track) track.scrollBy({ left: dir * step(track) * PAGE, behavior: 'smooth' });
      return;
    }
    var wrap = t.closest('[data-ship-pop]');
    if (wrap && t.closest(TOGGLE)) {
      closePops(wrap);
      setPop(wrap, !wrap.classList.contains('is-open'));
      return;
    }
    if (wrap && t.closest('[data-ship-cap-toggle], .js-shipment-export-trigger')) {
      setPop(wrap, false);
      return;
    }
    if (!wrap) closePops(null);
  });

  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Escape') return;
    var open = document.querySelector('[data-ship-pop].is-open');
    if (!open) return;
    setPop(open, false);
    var btn = open.querySelector(TOGGLE);
    if (btn) btn.focus();
  });

  // scroll 은 거품이 일지 않아 capture 로 받는다(띠는 조각이 바뀔 때마다 새로 생긴다).
  document.addEventListener('scroll', function (ev) {
    var t = ev.target;
    if (t && t.hasAttribute && t.hasAttribute('data-ship-days-track')) syncNav(t);
  }, true);

  function eachTrack(fn) {
    var tracks = document.querySelectorAll('[data-ship-days-track]');
    for (var i = 0; i < tracks.length; i++) fn(tracks[i]);
  }
  function sync() { eachTrack(showSelected); }
  document.addEventListener('foms:erp-shell-fragment-swapped', sync);
  document.addEventListener('foms:main-content-swapped', sync);
  window.addEventListener('resize', function () { eachTrack(syncNav); });
  sync();
})();

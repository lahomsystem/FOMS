/**
 * FOMS 공지 사진 — 썸네일 줄 + 가운데 사진 창(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §8).
 * 본사 공지 창 · /notices · 협력사 공지 창 · /partner/notices · 관리자 쓰기 화면 휴대폰 미리보기가 같이 쓴다.
 *
 * - 썸네일 줄: [data-foms-notice-images] 안의 [data-foms-notice-thumb] 단추. 서버가 그린 줄은 data-images(JSON
 *   [{url, thumb_url, name}])로, 스크립트가 그린 줄은 FomsNoticeGallery.render(상자, 사진들)로 사진 목록을 갖는다.
 * - 사진 창: 썸네일을 누르면 가운데 흰 카드로 크게. 바깥은 흐림 + 어둡게. 여러 장이면 좌우 단추 · 화살표 키 · 밀기로 넘긴다.
 *   닫기 = X · 바깥 누르기 · Esc. 닫으면 누른 썸네일로 초점을 돌려준다(공지 창은 그대로 남는다).
 * - 공지 창(확인을 눌러야 닫히는 창)과 같이 뜬다: 공지 창은 document 잡기 단계에서 초점 · Esc 를 가둔다. 사진 창은 그보다
 *   먼저 도는 window 잡기 단계에서 keydown · focusin 을 받아 처리하고 더 내려보내지 않는다(사진 창 안 초점은 사진 창이 가둔다).
 *   공지 창 스크립트도 열린 사진 창(.foms-notice-gallery:not([hidden]))을 "더 위 창"으로 보고 가두기를 쉰다.
 *   z-index 105460: 공지 창(105450) 위 · 도면 확인창(105500) · 긴급 창(106000) 아래 — 그 창들이 열려 있으면 사진 창은 키를 놓아 준다.
 */
(function () {
  'use strict';

  if (window.FomsNoticeGallery) return; // 한 화면에 두 번 실려도(협력사 공지 목록 + 공지 창) 한 벌만 돈다

  var HIGHER = '#foms-urgent-alert, .foms-drawing-alert:not([hidden])';
  var SWIPE_MIN = 40;
  var shell = null;
  var parts = {};
  var items = [];
  var index = 0;
  var trigger = null;
  var touch = null;

  function safeJsonParse(val, fb) {
    try {
      var text = String(val || '').trim();
      return text ? JSON.parse(text) : fb;
    } catch (err) {
      return fb;
    }
  }

  // 같은 사이트 주소만(자바스크립트 주소 · 남의 사이트 그림을 넣지 않는다).
  function sameSite(url) {
    return typeof url === 'string' && /^\/(?!\/)/.test(url);
  }

  function clean(list) {
    return (Array.isArray(list) ? list : []).filter(function (item) {
      return item && sameSite(item.url) && (!item.thumb_url || sameSite(item.thumb_url));
    });
  }

  function el(tag, className, attrs) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    Object.keys(attrs || {}).forEach(function (name) { node.setAttribute(name, attrs[name]); });
    return node;
  }

  function icon(name) {
    return el('i', 'fas ' + name, { 'aria-hidden': 'true' });
  }

  // ---- 썸네일 줄 ----
  function render(box, list) {
    if (!box) return;
    var photos = clean(list);
    box.__fomsImages = photos;
    while (box.firstChild) box.removeChild(box.firstChild);
    photos.forEach(function (photo, i) {
      var button = el('button', 'foms-notice-thumb', {
        type: 'button', 'data-foms-notice-thumb': '', 'data-index': String(i),
        'aria-label': '사진 ' + (i + 1) + ' / ' + photos.length + ' 크게 보기'
      });
      var img = el('img', 'foms-notice-thumb__img', { alt: '', loading: 'lazy', decoding: 'async' });
      img.src = photo.thumb_url || photo.url;
      button.appendChild(img);
      box.appendChild(button);
    });
    box.hidden = !photos.length;
  }

  function photosOf(box) {
    if (!box) return [];
    if (!box.__fomsImages) box.__fomsImages = clean(safeJsonParse(box.getAttribute('data-images'), []));
    return box.__fomsImages;
  }

  // ---- 사진 창 ----
  function build() {
    if (shell) return;
    shell = el('div', 'foms-notice-gallery', {
      'data-foms-notice-gallery': '', role: 'dialog', 'aria-modal': 'true', 'aria-label': '사진 크게 보기'
    });
    shell.hidden = true;
    var backdrop = el('div', 'foms-notice-gallery__backdrop', { 'data-gallery-close': '' });
    var card = el('div', 'foms-notice-gallery__card');
    var head = el('div', 'foms-notice-gallery__head');
    parts.count = el('span', 'foms-notice-gallery__count');
    parts.name = el('span', 'foms-notice-gallery__name');
    parts.close = el('button', 'foms-notice-gallery__close', { type: 'button', 'aria-label': '닫기', 'data-gallery-close': '' });
    parts.close.appendChild(icon('fa-xmark'));
    head.appendChild(parts.count);
    head.appendChild(parts.name);
    head.appendChild(parts.close);
    parts.stage = el('div', 'foms-notice-gallery__stage');
    parts.img = el('img', 'foms-notice-gallery__img', { alt: '', draggable: 'false' });
    parts.prev = el('button', 'foms-notice-gallery__nav foms-notice-gallery__nav--prev', { type: 'button', 'aria-label': '앞 사진' });
    parts.prev.appendChild(icon('fa-chevron-left'));
    parts.next = el('button', 'foms-notice-gallery__nav foms-notice-gallery__nav--next', { type: 'button', 'aria-label': '다음 사진' });
    parts.next.appendChild(icon('fa-chevron-right'));
    parts.stage.appendChild(parts.img);
    parts.stage.appendChild(parts.prev);
    parts.stage.appendChild(parts.next);
    card.appendChild(head);
    card.appendChild(parts.stage);
    shell.appendChild(backdrop);
    shell.appendChild(card);
    document.body.appendChild(shell);

    shell.addEventListener('click', function (ev) {
      if (ev.target.closest('[data-gallery-close]')) close();
    });
    parts.prev.addEventListener('click', function () { show(index - 1); });
    parts.next.addEventListener('click', function () { show(index + 1); });
    parts.stage.addEventListener('touchstart', function (ev) {
      var t = ev.touches && ev.touches[0];
      touch = t ? { x: t.clientX, y: t.clientY } : null;
    }, { passive: true });
    parts.stage.addEventListener('touchend', function (ev) {
      var t = ev.changedTouches && ev.changedTouches[0];
      if (!touch || !t) return;
      var dx = t.clientX - touch.x;
      var dy = t.clientY - touch.y;
      touch = null;
      if (Math.abs(dx) >= SWIPE_MIN && Math.abs(dx) > Math.abs(dy)) show(index + (dx < 0 ? 1 : -1));
    }, { passive: true });
  }

  function show(i) {
    if (!items.length) return;
    index = Math.max(0, Math.min(i, items.length - 1));
    var photo = items[index];
    var full = photo.url;
    parts.img.classList.add('is-loading');
    parts.img.src = photo.thumb_url || full;
    parts.img.alt = photo.name || ('사진 ' + (index + 1));
    var loader = new Image();
    loader.onload = function () {
      if (items[index] === photo) { parts.img.src = full; parts.img.classList.remove('is-loading'); }
    };
    loader.onerror = function () { parts.img.classList.remove('is-loading'); };
    loader.src = full;
    parts.count.textContent = items.length > 1 ? (index + 1) + ' / ' + items.length : '';
    parts.name.textContent = photo.name || '';
    parts.prev.hidden = items.length < 2;
    parts.next.hidden = items.length < 2;
    parts.prev.disabled = index === 0;
    parts.next.disabled = index === items.length - 1;
  }

  function isOpen() { return !!(shell && !shell.hidden); }
  function higherOpen() { return !!document.querySelector(HIGHER); }

  function focusables() {
    return [parts.close, parts.prev, parts.next].filter(function (b) { return !b.hidden && !b.disabled; });
  }

  function open(list, start, from) {
    var photos = clean(list);
    if (!photos.length) return;
    build();
    items = photos;
    trigger = from || document.activeElement;
    shell.hidden = false;
    document.documentElement.classList.add('foms-notice-gallery-open');
    show(Number(start) || 0);
    parts.close.focus();
  }

  function close() {
    if (!isOpen()) return;
    shell.hidden = true;
    document.documentElement.classList.remove('foms-notice-gallery-open');
    parts.img.removeAttribute('src');
    items = [];
    var back = trigger;
    trigger = null;
    if (back && back.isConnected && typeof back.focus === 'function') back.focus();
  }

  // window 잡기 단계 — 공지 창(document 잡기 단계)의 초점 가두기 · Esc 무시보다 먼저 받는다.
  function onKeyDown(ev) {
    if (!isOpen() || higherOpen()) return;
    ev.stopPropagation(); // 사진 창이 맨 위 — 아래 공지 창 가두기로 키를 내려보내지 않는다
    if (ev.key === 'Escape' || ev.key === 'Esc') { ev.preventDefault(); close(); return; }
    if (ev.key === 'ArrowLeft') { ev.preventDefault(); show(index - 1); return; }
    if (ev.key === 'ArrowRight') { ev.preventDefault(); show(index + 1); return; }
    if (ev.key === 'Tab') {
      ev.preventDefault();
      var list = focusables();
      var at = list.indexOf(document.activeElement);
      var next = ev.shiftKey ? (at <= 0 ? list.length - 1 : at - 1) : (at + 1) % list.length;
      if (list[next]) list[next].focus();
    }
  }

  function onFocusIn(ev) {
    if (!isOpen() || higherOpen()) return;
    ev.stopPropagation();
    if (!shell.contains(ev.target)) parts.close.focus();
  }

  window.addEventListener('keydown', onKeyDown, true);
  window.addEventListener('focusin', onFocusIn, true);

  document.addEventListener('click', function (ev) {
    var thumb = ev.target.closest && ev.target.closest('[data-foms-notice-thumb]');
    if (!thumb) return;
    var box = thumb.closest('[data-foms-notice-images]');
    ev.preventDefault();
    open(photosOf(box), Number(thumb.getAttribute('data-index')) || 0, thumb);
  });

  window.FomsNoticeGallery = { render: render, open: open, close: close, isOpen: isOpen };
})();

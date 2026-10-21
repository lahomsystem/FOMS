/**
 * PARTNER-FOMS 5-2: 사진 칸 — 우리 품목 사진 칸과 같은 모양(즉시 추가 · Ctrl+V · 끌어놓기, 휴대폰 찍기 · 앨범).
 *
 * - 고른 사진은 보내기(품목 저장) 전까지 브라우저에만 둔다 — 새 주문은 주문이 생겨야 올릴 곳이 생긴다.
 *   칸마다 파일 목록을 zone._ppFiles 에 두고, 미리보기 · 빼기 · 옮기기를 그린다.
 * - 공통 실측 사진(common)은 사진마다 "제품 연결"로 제품 칸(item)에 옮기고, 제품 사진은 "공통으로"로 되돌린다.
 *   초안 도면(draft)은 제품에 붙이지 않는다(서버가 제품에는 실측 사진만 받는다).
 * - 붙여넣기는 커서가 있는 칸 → 그 제품 카드 → (넓은 화면) 보이는 제품 → 공통 실측 사진 순으로 받는다.
 * - partner-items.js 는 PartnerPhotos.files(제품 칸), partner-portal.js 는 PartnerPhotos.commonJobs() 로 올릴 목록을 읽는다.
 * 설계서: docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.4 · §17
 */
(function () {
  'use strict';

  var MAX_FILES = 50;
  var WIDE = window.matchMedia('(min-width: 992px)');

  function filesOf(zone) {
    if (!zone._ppFiles) zone._ppFiles = [];
    return zone._ppFiles;
  }

  function zoneOf(root, kind) {
    return root ? root.querySelector('[data-pp-photo-zone="' + kind + '"]') : null;
  }

  function accepts(zone, file) {
    var input = zone.querySelector('[data-pp-photo-input]');
    var rules = String((input && input.accept) || '').split(',').map(function (r) { return r.trim().toLowerCase(); });
    var type = String(file.type || '').toLowerCase();
    var name = String(file.name || '').toLowerCase();
    return rules.some(function (rule) {
      if (rule.slice(-2) === '/*') return type.indexOf(rule.slice(0, -1)) === 0;
      return rule.charAt(0) === '.' && name.slice(-rule.length) === rule;
    });
  }

  function add(zone, files) {
    if (!zone) return;
    var list = filesOf(zone);
    Array.prototype.forEach.call(files || [], function (f) {
      if (list.length < MAX_FILES && accepts(zone, f)) list.push(f);
    });
    render(zone);
  }

  function cards() {
    return Array.prototype.slice.call(document.querySelectorAll('[data-pp-items] .pp-item'));
  }

  function cardName(card, i) {
    var input = card.querySelector('[data-k="product_name"]');
    return (i + 1) + '. ' + ((input && input.value.trim()) || '미입력');
  }

  function button(cls, attr, index, icon, title) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-sm ' + cls;
    btn.setAttribute(attr, String(index));
    btn.title = title;
    btn.setAttribute('aria-label', title);
    btn.innerHTML = '<i class="fas ' + icon + '"></i>';
    return btn;
  }

  /** "제품 연결" 목록 — 열 때마다 지금 제품 이름 · 수로 다시 채운다. */
  function fillLinks(select) {
    select.length = 0;
    select.add(new Option('제품 연결', ''));
    cards().forEach(function (card, i) { select.add(new Option(cardName(card, i), String(i))); });
  }

  function linkSelect(index) {
    var select = document.createElement('select');
    select.className = 'form-select form-select-sm pp-tile__link';
    select.setAttribute('data-pp-photo-link', String(index));
    select.setAttribute('aria-label', '제품 연결');
    fillLinks(select);
    return select;
  }

  function tile(zone, file, index) {
    var kind = zone.getAttribute('data-pp-photo-zone');
    var el = document.createElement('div');
    el.className = 'pp-tile border rounded bg-white p-1 d-flex align-items-center gap-1';
    var media;
    if (String(file.type).indexOf('image/') === 0) {
      media = document.createElement('img');
      media.className = 'pp-tile__thumb';
      media.alt = file.name;
      media.src = URL.createObjectURL(file);
      zone._ppUrls.push(media.src);
    } else {
      media = document.createElement('span');
      media.className = 'pp-tile__thumb pp-tile__thumb--file';
      media.innerHTML = '<i class="fas ' + (String(file.type).indexOf('video/') === 0 ? 'fa-video' : 'fa-file-alt') + '"></i>';
    }
    var name = document.createElement('div');
    name.className = 'small text-truncate flex-grow-1 pp-tile__name';
    name.title = file.name;
    name.textContent = file.name;
    el.appendChild(media);
    el.appendChild(name);
    if (kind === 'common' && cards().length) el.appendChild(linkSelect(index));
    if (kind === 'item' && zoneOf(document, 'common')) {
      el.appendChild(button('btn-outline-secondary', 'data-pp-photo-unlink', index, 'fa-unlink', '공통으로 이동'));
    }
    el.appendChild(button('btn-outline-danger', 'data-pp-photo-remove', index, 'fa-times', '빼기'));
    return el;
  }

  function render(zone) {
    var list = filesOf(zone);
    var gallery = zone.querySelector('[data-pp-photo-gallery]');
    (zone._ppUrls || []).forEach(function (u) { URL.revokeObjectURL(u); });
    zone._ppUrls = [];
    gallery.innerHTML = '';
    list.forEach(function (f, i) { gallery.appendChild(tile(zone, f, i)); });
    var empty = zone.querySelector('[data-pp-photo-empty]');
    if (empty) empty.hidden = list.length > 0;
    var count = zone.querySelector('[data-pp-photo-count]');
    if (count) count.textContent = list.length ? list.length + '개' : '';
  }

  function move(from, to, index) {
    if (!from || !to) return;
    var file = filesOf(from).splice(index, 1)[0];
    if (file) filesOf(to).push(file);
    render(from);
    render(to);
  }

  /** 붙여넣을 칸: 커서가 있는 칸 → 그 제품 카드 → (넓은 화면) 보이는 제품 → 공통 실측 사진. */
  function pasteTarget(target) {
    var zone = target.closest && target.closest('[data-pp-photo-zone]');
    if (zone) return zone;
    var card = target.closest && target.closest('.pp-item');
    if (card) return zoneOf(card, 'item');
    if (WIDE.matches) {
      var shown = cards().filter(function (c) { return !c.classList.contains('erp-item-row--md-hidden'); });
      if (shown.length === 1 && zoneOf(shown[0], 'item')) return zoneOf(shown[0], 'item');
    }
    return zoneOf(document, 'common');
  }

  function hasFiles(ev) {
    var types = ev.dataTransfer && ev.dataTransfer.types;
    return !!types && Array.prototype.indexOf.call(types, 'Files') !== -1;
  }

  function bind() {
    document.addEventListener('click', function (ev) {
      var zone = ev.target.closest('[data-pp-photo-zone]');
      if (!zone) return;
      var hit = function (attr) { return ev.target.closest('[' + attr + ']'); };
      var at = function (el, attr) { return parseInt(el.getAttribute(attr), 10); };
      var el;
      if (hit('data-pp-photo-pick')) zone.querySelector('[data-pp-photo-input]').click();
      else if (hit('data-pp-photo-shoot')) zone.querySelector('[data-pp-photo-camera]').click();
      else if ((el = hit('data-pp-photo-remove'))) { filesOf(zone).splice(at(el, 'data-pp-photo-remove'), 1); render(zone); }
      else if ((el = hit('data-pp-photo-unlink'))) move(zone, zoneOf(document, 'common'), at(el, 'data-pp-photo-unlink'));
    });
    // 제품 카드를 빼면 그 카드에 고른 사진은 공통 실측 사진으로 돌린다(partner-items.js 가 카드를 지우기 전에).
    document.addEventListener('click', function (ev) {
      var card = ev.target.closest('[data-pp-remove-item]') && ev.target.closest('.pp-item');
      var zone = card && zoneOf(card, 'item');
      var common = zoneOf(document, 'common');
      if (!zone || !common || !filesOf(zone).length || cards().length <= 1) return;
      filesOf(zone).splice(0).forEach(function (f) { filesOf(common).push(f); });
      render(common);
    }, true);
    document.addEventListener('change', function (ev) {
      var zone = ev.target.closest('[data-pp-photo-zone]');
      if (!zone) return;
      if (ev.target.matches('[data-pp-photo-input], [data-pp-photo-camera]')) {
        add(zone, ev.target.files);
        ev.target.value = '';
      } else if (ev.target.matches('[data-pp-photo-link]') && ev.target.value !== '') {
        move(zone, zoneOf(cards()[parseInt(ev.target.value, 10)], 'item'), parseInt(ev.target.getAttribute('data-pp-photo-link'), 10));
      }
    });
    document.addEventListener('paste', function (ev) {
      var files = ev.clipboardData && ev.clipboardData.files;
      if (!files || !files.length) return;
      var zone = pasteTarget(ev.target);
      if (!zone) return;
      ev.preventDefault();
      add(zone, files);
    });
    // 칸 밖에 떨어뜨린 파일을 브라우저가 열어 버리면(쓰던 주문이 사라진다) 막는다.
    ['dragover', 'drop'].forEach(function (type) {
      document.addEventListener(type, function (ev) {
        if (!hasFiles(ev)) return;
        ev.preventDefault();
        var zone = ev.target.closest('[data-pp-photo-zone]');
        Array.prototype.forEach.call(document.querySelectorAll('.pp-drop--over'), function (z) {
          if (z !== zone || type === 'drop') z.classList.remove('pp-drop--over');
        });
        if (!zone) return;
        if (type === 'dragover') zone.classList.add('pp-drop--over');
        else add(zone, ev.dataTransfer.files);
      });
    });
    document.addEventListener('focusin', function (ev) {
      if (ev.target.matches && ev.target.matches('[data-pp-photo-link]')) fillLinks(ev.target);
    });
  }

  window.PartnerPhotos = {
    files: function (zone) { return zone ? filesOf(zone).slice() : []; },
    /** 공통 칸 올릴 목록: [[파일, 'photo'|'draft'], …]. */
    commonJobs: function () {
      var jobs = [];
      [['common', 'photo'], ['draft', 'draft']].forEach(function (pair) {
        var zone = zoneOf(document, pair[0]);
        if (zone) filesOf(zone).forEach(function (f) { jobs.push([f, pair[1]]); });
      });
      return jobs;
    }
  };

  document.addEventListener('DOMContentLoaded', bind);
})();

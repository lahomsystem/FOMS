/**
 * PARTNER-FOMS 3-1: 제품 항목 왼쪽 목록 · 오른쪽 상세 — 우리 주문 화면(erp-items-master-detail.js)과 같은 모양.
 *
 * - 넓은 화면(992px 이상)에서만 한 항목씩 보인다. 좁은 화면은 지금처럼 카드를 차례로 모두 보인다.
 * - 목록 · 검색 · 이전/다음 · Ctrl+↑↓ · 전체 항목 요약. 카드는 서버가 그리거나 partner-items.js 가 더한다.
 * - 같은 CSS(erp-items-master-detail.css)를 쓰려고 우리 클래스(item-rail · rail-item · erp-item-row--md-hidden)를 단다.
 * 설계서: docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.3 · §12
 */
(function () {
  'use strict';

  var WIDE = window.matchMedia('(min-width: 992px)');

  function text(card, selector) {
    var el = card.querySelector(selector);
    return el ? String(el.value || '').trim() : '';
  }

  function firstSpec(card) {
    var row = card.querySelector('.pp-spec');
    if (!row) return '';
    return ['spec_width', 'spec_depth', 'spec_height']
      .map(function (key) { return text(row, '[data-s="' + key + '"]'); })
      .filter(Boolean).join('×');
  }

  function Rail(shell) {
    this.shell = shell;
    this.items = shell.querySelector('[data-pp-items]');
    this.list = shell.querySelector('[data-pp-rail-list]');
    this.search = shell.querySelector('[data-pp-rail-search]');
    this.selected = 0;
  }

  Rail.prototype.cards = function () {
    return Array.prototype.slice.call(this.items.querySelectorAll('.pp-item'));
  };

  Rail.prototype.select = function (index) {
    var cards = this.cards();
    this.selected = Math.max(0, Math.min(index, cards.length - 1));
    this.render();
  };

  Rail.prototype.render = function () {
    var cards = this.cards();
    var wide = WIDE.matches;
    var q = this.search ? this.search.value.trim().toLowerCase() : '';
    var self = this;
    if (this.selected >= cards.length) this.selected = Math.max(0, cards.length - 1);
    this.list.innerHTML = '';
    cards.forEach(function (card, i) {
      card.classList.toggle('erp-item-row--md-hidden', wide && i !== self.selected);
      var name = text(card, '[data-k="product_name"]');
      var el = document.createElement('div');
      el.className = 'rail-item' + (i === self.selected ? ' is-selected' : '')
        + (q && name.toLowerCase().indexOf(q) === -1 ? ' is-filtered-out' : '') + (name ? '' : ' rail-item--ghost');
      el.setAttribute('role', 'option');
      el.setAttribute('aria-selected', i === self.selected ? 'true' : 'false');
      el.innerHTML = '<span class="rail-item__index"></span><div class="rail-item__main">'
        + '<span class="rail-item__name"></span><span class="rail-item__spec"></span></div>';
      el.querySelector('.rail-item__index').textContent = String(i + 1);
      el.querySelector('.rail-item__name').textContent = name || '미입력';
      el.querySelector('.rail-item__spec').textContent = firstSpec(card);
      el.addEventListener('click', function () { self.select(i); });
      self.list.appendChild(el);
    });
    this.setText('[data-pp-rail-count]', String(cards.length));
    this.setText('[data-pp-rail-pos]', cards.length ? (this.selected + 1) + ' / ' + cards.length : '0 / 0');
  };

  Rail.prototype.setText = function (selector, value) {
    var el = this.shell.querySelector(selector);
    if (el) el.textContent = value;
  };

  Rail.prototype.summary = function () {
    var lines = this.cards().map(function (card, i) {
      var spec = Array.prototype.map.call(card.querySelectorAll('.pp-spec'), function (row) {
        return ['spec_width', 'spec_depth', 'spec_height']
          .map(function (key) { return text(row, '[data-s="' + key + '"]') || '-'; }).join(' × ');
      }).join(' / ');
      return (i + 1) + '. ' + (text(card, '[data-k="product_name"]') || '미입력') + (spec ? '  ' + spec : '');
    });
    window.alert(lines.join('\n') || '제품 항목이 없습니다.');
  };

  Rail.prototype.bind = function () {
    var self = this;
    this.items.addEventListener('pp:items-changed', function (ev) {
      var added = ev.detail && ev.detail.added;
      if (added) self.selected = self.cards().indexOf(added);
      self.render();
    });
    this.items.addEventListener('input', function (ev) {
      if (ev.target.matches('[data-k="product_name"], [data-s]')) self.render();
    });
    if (this.search) this.search.addEventListener('input', function () { self.render(); });
    this.shell.addEventListener('click', function (ev) {
      if (ev.target.closest('[data-pp-rail-prev]')) self.select(self.selected - 1);
      if (ev.target.closest('[data-pp-rail-next]')) self.select(self.selected + 1);
      if (ev.target.closest('[data-pp-rail-summary]')) self.summary();
    });
    document.addEventListener('keydown', function (ev) {
      if (!WIDE.matches || !ev.ctrlKey || (ev.key !== 'ArrowUp' && ev.key !== 'ArrowDown')) return;
      ev.preventDefault();
      self.select(self.selected + (ev.key === 'ArrowUp' ? -1 : 1));
    });
    WIDE.addEventListener('change', function () { self.render(); });
    this.render();
  };

  document.addEventListener('DOMContentLoaded', function () {
    var shell = document.querySelector('[data-pp-items-md]');
    if (shell && shell.querySelector('[data-pp-items]')) new Rail(shell).bind();
  });
})();

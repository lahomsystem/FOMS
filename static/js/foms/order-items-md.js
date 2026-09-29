/**
 * 주문 상세 펼침의 "제품 여러 건" 목록+상세(Master-Detail) — erporder 와 같은 모양.
 * 주문·생산·시공 대시보드가 같이 쓴다. 왼쪽 목록에서 고른 제품 카드만 오른쪽에 보인다.
 *
 * - render(items, cards): cards[i] 는 호출 쪽이 그린 i번째 제품 카드 HTML. 2건 이상일 때만 부른다.
 * - nav(idx, total): 카드 머리에 넣는 ‹ n / N › 버튼.
 * - 클릭은 문서 한 곳에서 받는다(프래그먼트 교체로 스크립트가 다시 돌아도 한 번만 건다).
 */
(function () {
  'use strict';

  function esc(v) {
    return String(v == null ? '' : v)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function text(v) {
    return v === null || v === undefined ? '' : String(v).trim();
  }

  function specOf(item) {
    let w = text(item.spec_width);
    let d = text(item.spec_depth);
    let h = text(item.spec_height);
    if (!w && !d && !h && item.spec) {
      const parts = String(item.spec).split(/[xX*×]/).map(function (s) { return s.trim(); });
      w = parts[0] || ''; d = parts[1] || ''; h = parts[2] || '';
    }
    return [w, d, h].filter(function (s) { return s && s !== '-'; }).join('×');
  }

  function priceNum(item) {
    const n = Number(String(item.price == null ? '' : item.price).replace(/[^0-9.-]/g, ''));
    return Number.isFinite(n) && n > 0 ? n : 0;
  }

  function priceText(item) {
    const raw = item.price;
    if (raw == null || raw === '') return '-';
    const n = Number(raw);
    return n ? n.toLocaleString('ko-KR') + '원' : String(raw);
  }

  function nav(idx, total) {
    return '<div class="od-item-nav">'
      + '<button type="button" class="btn btn-sm btn-outline-secondary" data-od-nav="-1"' + (idx === 0 ? ' disabled' : '') + ' aria-label="이전 제품"><i class="fas fa-chevron-left"></i></button>'
      + '<span class="od-item-nav__pos">' + (idx + 1) + ' / ' + total + '</span>'
      + '<button type="button" class="btn btn-sm btn-outline-secondary" data-od-nav="1"' + (idx === total - 1 ? ' disabled' : '') + ' aria-label="다음 제품"><i class="fas fa-chevron-right"></i></button>'
      + '</div>';
  }

  function render(items, cards) {
    let sum = 0;
    const rail = items.map(function (item, idx) {
      sum += priceNum(item);
      const name = esc(text(item.product_name || item.name) || '-');
      // 둘째 줄: 규격이 있으면 규격, 없으면(네이버 주문 등) 옵션 요약
      const sub = specOf(item) || text(item.option_detail || item.options);
      const on = idx === 0;
      return '<button type="button" class="rail-item' + (on ? ' is-selected' : '') + '" role="option" aria-selected="' + on + '" data-od-rail-index="' + idx + '" title="' + name + '">'
        + '<span class="rail-item__index">' + (idx + 1) + '</span>'
        + '<span class="rail-item__main"><span class="rail-item__name">' + name + '</span>'
        + (sub ? '<span class="rail-item__spec">' + esc(sub) + '</span>' : '')
        + '</span>'
        + '<span class="rail-item__price">' + esc(priceText(item)) + '</span>'
        + '</button>';
    }).join('');
    const detail = cards.map(function (html, idx) {
      return '<div data-od-card-index="' + idx + '"' + (idx > 0 ? ' class="d-none"' : '') + '>' + html + '</div>';
    }).join('');
    return '<div class="dw-items-md" data-od-items-md data-od-current="0">'
      + '<aside class="item-rail" aria-label="제품 항목 목록">'
      + '<div class="item-rail__head"><span class="item-rail__title">제품 <span class="item-rail__count">' + items.length + '</span></span></div>'
      + '<div class="item-rail__list" role="listbox">' + rail + '</div>'
      + '<div class="item-rail__foot"><span>항목 합계</span><strong>' + (sum > 0 ? sum.toLocaleString('ko-KR') + '원' : '-') + '</strong></div>'
      + '</aside>'
      + '<div class="dw-item-detail">' + detail + '</div>'
      + '</div>';
  }

  function select(md, idx) {
    const cards = md.querySelectorAll('[data-od-card-index]');
    if (idx < 0 || idx >= cards.length) return;
    md.dataset.odCurrent = String(idx);
    cards.forEach(function (card) {
      card.classList.toggle('d-none', Number(card.dataset.odCardIndex) !== idx);
    });
    md.querySelectorAll('[data-od-rail-index]').forEach(function (btn) {
      const on = Number(btn.dataset.odRailIndex) === idx;
      btn.classList.toggle('is-selected', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
  }

  if (!window.__fomsOrderItemsMdBound) {
    window.__fomsOrderItemsMdBound = true;
    document.addEventListener('click', function (ev) {
      const t = ev.target;
      if (!t || typeof t.closest !== 'function') return;
      const md = t.closest('[data-od-items-md]');
      if (!md) return;
      const railBtn = t.closest('[data-od-rail-index]');
      if (railBtn) { select(md, Number(railBtn.dataset.odRailIndex)); return; }
      const navBtn = t.closest('[data-od-nav]');
      if (navBtn) select(md, Number(md.dataset.odCurrent || 0) + Number(navBtn.dataset.odNav));
    });
  }

  window.FomsOrderItemsMD = { render: render, nav: nav };
})();

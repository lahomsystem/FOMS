/**
 * 정산 대시보드 · 탭 "제품별" — 분류 안 된 품목(데이터 품질) · 검산 줄.
 *
 * 둘 다 구간 기준 값(`coverage`·`unmapped_top`·`allocation_check`)을 읽는다. 품목명은 자유 입력
 * 원문이라 textContent 로만 넣는다(innerHTML 미사용).
 */
(function () {
  'use strict';

  var P = window.FomsSettleProducts = window.FomsSettleProducts || {};

  function tds(tr, values) { values.forEach(function (v) { tr.appendChild(P.el('td', null, v)); }); return tr; }

  /* ═══════════════ 분류 안 된 품목 · 검산 ═══════════════ */

  P.renderUnmapped = function (ctx, model) {
    var els = ctx.els, data = model.data, cov = data.coverage || {};
    var items = P.num(cov.items_total), other = P.num(cov.items_other), share = P.num(cov.revenue_other_share);
    if (els.coverage) {
      P.clear(els.coverage);
      [['s-pr-dbox--warn', '기타로 간 품목', P.cnt(other), '개', ['전체 품목 ' + P.cnt(items) + '개 중 ', { b: P.pctTxt(other, items) }]],
        ['', '기타 매출 비중', (share * 100).toFixed(1), '%', ['배분 후 출고가 기준']],
        ['', '분류된 품목', P.pctTxt(items - other, items), '', ['규칙에 걸린 품목 몫 — 높을수록 이 탭을 믿을 수 있습니다']],
      ].forEach(function (x) {
        var box = P.el('div', 's-pr-dbox' + (x[0] ? ' ' + x[0] : ''));
        box.appendChild(P.el('div', 's-pr-dbox-label', x[1]));
        var v = P.el('div', 's-pr-dbox-val', x[2]);
        if (x[3]) v.appendChild(P.el('i', null, x[3]));
        box.appendChild(v);
        box.appendChild(P.rich(P.el('div', 's-pr-dbox-sub'), x[4]));
        els.coverage.appendChild(box);
      });
    }
    if (els.unmapped) {
      P.clear(els.unmapped);
      var list = (data.unmapped_top || []).filter(function (r) { return r && r.length; });
      var thead = P.el('thead'), hr = P.el('tr'), tb = P.el('tbody');
      ['품목명(원문)', '건수', '품목가 합(할인 전)', '1건 평균'].forEach(function (t) { hr.appendChild(P.el('th', null, t)); });
      thead.appendChild(hr);
      els.unmapped.appendChild(thead);
      if (!list.length) {
        var td0 = P.el('td', null, '이 기간에 분류 안 된 품목이 없습니다.');
        td0.colSpan = 4;
        tb.appendChild(P.el('tr')).appendChild(td0);
      }
      var maxN = Math.max.apply(null, list.map(function (r) { return P.num(r[1]); }).concat([1]));
      list.forEach(function (r) {
        var tr = P.el('tr'), tdc = P.el('td'), wrap = P.el('span', 's-pr-uq-cnt'), bar = P.el('i', 's-pr-uq-bar');
        tr.appendChild(P.el('td', 's-pr-uq-name', String(r[0])));
        bar.style.setProperty('--s-pr-w', Math.max(2, P.num(r[1]) / maxN * 64) + 'px');
        wrap.appendChild(bar);
        wrap.appendChild(P.el('span', null, P.cnt(r[1]) + '건'));
        tdc.appendChild(wrap);
        tr.appendChild(tdc);
        tds(tr, [r.length > 2 ? P.wonU(r[2]) : '-', r.length > 2 && P.num(r[1]) ? P.wonU(P.num(r[2]) / P.num(r[1])) : '-']);
        tb.appendChild(tr);
      });
      els.unmapped.appendChild(tb);
    }
    if (els.alloc) {
      var a = data.allocation_check || {};
      P.clear(els.alloc);
      [['검산 · 주문 ', { b: P.cnt(a.orders) + '건' }], ['출고가 합 ', { b: P.wonU(a.sum_shipping) }],
        ['할인 전 품목가 합 ', { b: P.wonU(a.sum_raw_items) }],
        ['배분 비율 ', { b: P.pctTxt(P.num(a.sum_shipping), P.num(a.sum_raw_items)) }, ' — 품목가 1원이 매출 이만큼으로 잡힙니다'],
      ].forEach(function (parts) { els.alloc.appendChild(P.rich(P.el('span'), parts)); });
    }
  };

  P.quality = true;
  if (typeof P.mountAll === 'function') P.mountAll();
})();

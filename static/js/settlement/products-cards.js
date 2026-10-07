/**
 * 정산 대시보드 · 탭 "제품별" — KPI 4장 · 제품군별 매출 · 채널별 제품 구성.
 *
 * 전부 구간 합계(`period` → products-core.js buildModel 의 agg/tot)만 읽는다. 막대 폭·색은 CSS
 * 사용자 속성(`--s-pr-w`·`--s-pr-pct`·`--s-pr-c`·`--s-pr-inner`)으로 넣는다(인라인 style 금지 규칙) —
 * 퍼센트 폭이라 숨은 pane 에서 그려도 폭 0 함정을 타지 않는다.
 */
(function () {
  'use strict';

  var P = window.FomsSettleProducts = window.FomsSettleProducts || {};
  var SORT_LABEL = { expected: '예상', actual: '실제', orders: '건수' };

  function sortVal(a, k) { return k === 'orders' ? a.expected_orders : a[k]; }

  /** 제품 칸(순위 대상)과 제품 아닌 칸(아래 '분류 밖' 묶음)을 정렬 기준으로 나눠 돌려준다. */
  P.orderedFamilies = function (model, sort) {
    var agg = model.agg;
    var main = model.famOrder.filter(function (c) { return !P.NON_PRODUCT[c]; });
    var rest = model.famOrder.filter(function (c) { return P.NON_PRODUCT[c]; });
    function by(a, b) { return sortVal(agg[b], sort) - sortVal(agg[a], sort) || agg[b].expected - agg[a].expected; }
    main.sort(by);
    rest.sort(by);
    return { main: main, rest: rest };
  };

  /* ═══════════════ KPI ═══════════════ */

  P.renderKpis = function (ctx, model) {
    var host = ctx.els.kpis;
    if (!host) return;
    P.clear(host);
    var agg = model.agg, tot = model.tot, label = model.famLabel;
    var basis = tot.actual > 0 ? 'actual' : 'expected';
    var ranked = model.famOrder.filter(function (c) { return !P.NON_PRODUCT[c]; })
      .sort(function (a, b) { return agg[b][basis] - agg[a][basis]; });
    var first = ranked[0], second = ranked[1];
    var hasFirst = first && agg[first][basis] > 0;
    var rate = P.pct(tot.actual, tot.expected);
    var specs = [
      { cls: 's-pr-kpi--plan', label: '예상 매출', chip: '시공일 기준', value: P.won(tot.expected), unit: '원',
        sub: ['품목 ', { b: P.cnt(tot.expected_items) + '개' }, ' · 할인 전 품목가 ' + P.wonU(tot.expected_raw)] },
      { cls: 's-pr-kpi--real', label: '실제 매출', chip: '시공완료', value: P.won(tot.actual), unit: '원',
        sub: ['품목 ', { b: P.cnt(tot.actual_items) + '개' }, ' · 완료 · AS접수 · AS완료'] },
      { cls: 's-pr-kpi--rate', label: '달성률', chip: '실제 ÷ 예상',
        value: tot.expected ? rate.toFixed(1) : '-', unit: tot.expected ? '%' : '', meter: rate,
        sub: ['남은 예상 ', { b: P.wonU(tot.expected - tot.actual) }] },
      { cls: 's-pr-kpi--top', label: '1위 제품군', chip: basis === 'actual' ? '실제 매출 비중' : '예상 매출 비중',
        name: hasFirst ? label[first] : '-',
        share: hasFirst ? P.pctTxt(agg[first][basis], tot[basis]) : '',
        sub: !hasFirst ? ['이 기간에는 매출이 없습니다'] : [{ b: P.wonU(agg[first][basis]) },
          second && agg[second][basis] > 0
            ? ' · 2위 ' + label[second] + ' ' + P.pctTxt(agg[second][basis], tot[basis]) : ''] },
    ];
    specs.forEach(function (s) {
      var card = P.el('div', 's-pr-kpi ' + s.cls);
      var lab = P.el('div', 's-pr-kpi-label', s.label);
      lab.appendChild(P.el('span', 's-pr-chip-rule', s.chip));
      card.appendChild(lab);
      var v;
      if (s.name != null) {
        v = P.el('div', 's-pr-kpi-value s-pr-kpi-value--name', s.name);
        if (s.share) v.appendChild(P.el('em', null, s.share));
        v.title = s.name;
      } else {
        v = P.el('div', 's-pr-kpi-value', s.value);
        if (s.unit) v.appendChild(P.el('i', null, s.unit));
      }
      card.appendChild(v);
      if (s.meter != null) {
        var m = P.el('div', 's-pr-meter'), f = P.el('span');
        f.style.setProperty('--s-pr-pct', Math.max(0, Math.min(100, s.meter)) + '%');
        m.appendChild(f);
        card.appendChild(m);
      }
      card.appendChild(P.rich(P.el('div', 's-pr-kpi-sub'), s.sub));
      host.appendChild(card);
    });
  };

  /* ═══════════════ 제품군별 매출 ═══════════════ */

  function detail(model, c, a) {
    var box = P.el('div', 's-pr-detail');
    box.appendChild(P.el('h4', null, '이 제품군으로 묶인 대표 품목명'));
    var chips = P.el('div', 's-pr-chips');
    var names = model.topNames[c] || [];
    if (!names.length) chips.appendChild(P.el('span', null, '이 기간에 대표 품목명 자료가 없습니다.'));
    names.forEach(function (n) {
      var ch = P.el('span', 's-pr-chip', String(n[0]));
      ch.appendChild(P.el('i', null, '×' + P.cnt(n[1])));
      chips.appendChild(ch);
    });
    box.appendChild(chips);
    var raw = P.el('div', 's-pr-raw');
    raw.appendChild(P.rich(P.el('span'), ['할인 전 품목가 합(예상) ', { b: P.wonU(a.expected_raw) },
      ' → 배분 후 ', { b: P.wonU(a.expected) }, ' (' + P.pctTxt(a.expected, a.expected_raw) + ')']));
    raw.appendChild(P.rich(P.el('span'), ['할인 전 품목가 합(실제) ', { b: P.wonU(a.actual_raw) },
      ' → 배분 후 ', { b: P.wonU(a.actual) }, ' (' + P.pctTxt(a.actual, a.actual_raw) + ')']));
    box.appendChild(raw);
    return box;
  }

  function cell(cls, text, dataLabel) {
    var d = P.el('div', cls, text);
    if (dataLabel) d.setAttribute('data-l', dataLabel);
    return d;
  }

  P.renderFamilies = function (ctx, model) {
    var host = ctx.els.families;
    if (!host) return;
    P.clear(host);
    var st = ctx.state, agg = model.agg, tot = model.tot, label = model.famLabel;
    var any = model.famOrder.some(function (c) { return agg[c].expected > 0 || agg[c].actual > 0; });
    if (!any) {
      host.appendChild(P.el('div', 's-empty', '이 기간에는 시공일이 잡힌 주문이 없습니다.'));
      return;
    }
    var head = P.el('div', 's-pr-row s-pr-row--head');
    ['제품군', '예상 · 실제', '실제', '예상', '달성률', '비중', '주문 · 품목(예상)'].forEach(function (t) {
      head.appendChild(P.el('span', null, t));
    });
    host.appendChild(head);
    var groups = P.orderedFamilies(model, st.sort);
    var max = 0;
    model.famOrder.forEach(function (c) { max = Math.max(max, agg[c].expected, agg[c].actual); });
    var shareTot = st.sort === 'orders' ? tot.expected_orders : tot[st.sort];
    var rank = 0;

    function row(c, muted) {
      var a = agg[c];
      if (!(a.expected > 0 || a.actual > 0 || a.expected_orders > 0)) return;
      var open = !!st.open[c];
      var r = P.el('div', 's-pr-row' + (muted ? ' s-pr-row--muted' : '') + (open ? ' s-pr-row--open' : ''));
      var nameCell = P.el('div', 's-pr-c-name');
      var btn = P.el('button', 's-pr-name');
      btn.type = 'button';
      btn.setAttribute('data-products-fam', c);
      btn.setAttribute('aria-expanded', String(open));
      btn.title = label[c] + ' — 대표 품목명 보기';
      btn.appendChild(P.el('i', 's-pr-rank', muted ? '' : String(++rank)));
      btn.appendChild(P.el('span', null, label[c]));
      nameCell.appendChild(btn);
      r.appendChild(nameCell);

      var barCell = P.el('div', 's-pr-c-bar');
      var track = P.el('div', 's-pr-track');
      track.tabIndex = 0;
      track.setAttribute('aria-label', label[c] + ' 예상 ' + P.wonU(a.expected) + ', 실제 ' + P.wonU(a.actual));
      var be = P.el('i', 's-pr-exp');
      be.style.setProperty('--s-pr-w', (max ? a.expected / max * 100 : 0) + '%');
      var ba = P.el('i', 's-pr-act');
      ba.style.setProperty('--s-pr-w', (max ? a.actual / max * 100 : 0) + '%');
      track.appendChild(be);
      track.appendChild(ba);
      barCell.appendChild(track);
      r.appendChild(barCell);
      P.bindTip(ctx, track, function () {
        return [label[c], [
          { c: 'var(--s-plan-edge)', l: '예상', v: P.wonU(a.expected) },
          { c: 'var(--s-accent)', l: '실제', v: P.wonU(a.actual) },
          { l: '달성률', v: P.pctTxt(a.actual, a.expected) },
          { l: '할인 전 품목가(예상)', v: P.wonU(a.expected_raw) },
          { l: '주문 · 품목(예상)', v: P.cnt(a.expected_orders) + '건 · ' + P.cnt(a.expected_items) + '개' },
          { l: '주문 · 품목(실제)', v: P.cnt(a.actual_orders) + '건 · ' + P.cnt(a.actual_items) + '개' },
        ]];
      });
      r.appendChild(cell('s-pr-c-act', P.wonU(a.actual)));
      r.appendChild(cell('s-pr-c-exp', P.wonU(a.expected), '예상'));
      var cr = cell('s-pr-c-rate', null, '달성률');
      cr.appendChild(P.el('b', null, P.pctTxt(a.actual, a.expected, 0)));
      r.appendChild(cr);
      r.appendChild(cell('s-pr-c-share', P.pctTxt(sortVal(a, st.sort), shareTot), SORT_LABEL[st.sort] + ' 비중'));
      var cc = cell('s-pr-c-cnt', null, '주문 · 품목');
      P.rich(cc, [{ b: P.cnt(a.expected_orders) + '건' }, ' · ' + P.cnt(a.expected_items) + '개']);
      r.appendChild(cc);
      host.appendChild(r);
      if (open) host.appendChild(detail(model, c, a));
    }

    groups.main.forEach(function (c) { row(c, false); });
    if (groups.rest.some(function (c) { return agg[c].expected > 0 || agg[c].actual > 0; })) {
      var g = P.el('div', 's-pr-group', '제품 아님 · 분류 밖');
      g.appendChild(P.el('span', null, '순위·1위에서 뺍니다 — 부대비용과 정리할 데이터'));
      host.appendChild(g);
      groups.rest.forEach(function (c) { row(c, true); });
    }
    var tr = P.el('div', 's-pr-row s-pr-row--total');
    tr.appendChild(cell('s-pr-c-name', '합계'));
    tr.appendChild(cell('s-pr-c-bar'));
    tr.appendChild(cell('s-pr-c-act', P.wonU(tot.actual)));
    tr.appendChild(cell('s-pr-c-exp', P.wonU(tot.expected), '예상'));
    var trr = cell('s-pr-c-rate', null, '달성률');
    trr.appendChild(P.el('b', null, P.pctTxt(tot.actual, tot.expected, 0)));
    tr.appendChild(trr);
    tr.appendChild(cell('s-pr-c-share', '100%', '비중'));
    tr.appendChild(cell('s-pr-c-cnt', P.cnt(tot.expected_items) + '개', '품목'));
    host.appendChild(tr);
  };

  /* ═══════════════ 채널별 제품 구성(라홈 안 네이버 = shop in shop) ═══════════════ */

  function naverPct(p) { return p < 1 ? '1% 미만' : Math.round(p) + '%'; }

  function seg(cls, text, pctVal, color) {
    var s = P.el('div', cls, text);
    s.style.setProperty('--s-pr-pct', pctVal + '%');
    if (color) s.style.setProperty('--s-pr-c', color);
    return s;
  }

  function chBar(ctx, a, m) {
    var bar = P.el('div', 's-pr-chbar' + (m === 'expected' ? ' s-pr-chbar--plan' : ''));
    var total = a.general[m] + a.lahom[m];
    if (!(total > 0)) return bar;
    var gP = P.pct(a.general[m], total), lP = P.pct(a.lahom[m], total);
    var nv = Math.min(a.naver[m], a.lahom[m]);
    var word = m === 'actual' ? '실제' : '예상';
    if (gP > 0) {
      var g = seg('s-pr-chseg', gP >= 26 ? '일반 ' + Math.round(gP) + '%' : gP >= 9 ? Math.round(gP) + '%' : '',
        gP, 'var(--s-pr-general)');
      P.bindTip(ctx, g, function () {
        return ['일반 · ' + word, [{ c: 'var(--s-pr-general)', l: '매출', v: P.wonU(a.general[m]) },
          { l: '비중', v: gP.toFixed(1) + '%' }]];
      });
      bar.appendChild(g);
    }
    if (lP > 0) {
      var l = seg('s-pr-chseg', null, lP, 'var(--s-pr-lahom)');
      var ownTxt = lP >= 30 ? '라홈 ' + Math.round(lP) + '%' : lP >= 10 ? Math.round(lP) + '%' : '';
      if (nv > 0) {
        var inner = P.pct(nv, a.lahom[m]), barP = lP * inner / 100;
        l.classList.add('s-pr-chseg--host');
        var own = P.el('span', 's-pr-chseg-own', ownTxt);
        var nav = P.el('span', 's-pr-chseg-inner',
          barP >= 18 ? '네이버 (' + naverPct(barP) + ')' : barP >= 7 ? '(' + naverPct(barP) + ')' : '');
        nav.style.setProperty('--s-pr-inner', inner + '%');
        if (!nav.textContent && own.textContent) own.textContent += ' (네이버 ' + naverPct(barP) + ')';
        nav.addEventListener('pointermove', function (e) {
          e.stopPropagation();
          P.showTip(ctx, e.clientX, e.clientY, '라홈 중 네이버 · ' + word, [
            { c: 'var(--s-pr-naver)', l: '매출', v: P.wonU(nv) },
            { l: '라홈 중', v: inner.toFixed(1) + '%' }, { l: '전체 중', v: barP.toFixed(1) + '%' }]);
        });
        l.appendChild(own);
        l.appendChild(nav);
      } else {
        l.textContent = ownTxt;
      }
      P.bindTip(ctx, l, function () {
        return ['라홈 · ' + word, [{ c: 'var(--s-pr-lahom)', l: '매출', v: P.wonU(a.lahom[m]) },
          { l: '비중', v: lP.toFixed(1) + '%' },
          nv > 0 ? { c: 'var(--s-pr-naver)', l: '그중 네이버', v: P.wonU(nv) } : null]];
      });
      bar.appendChild(l);
    }
    return bar;
  }

  P.renderChannels = function (ctx, model) {
    var host = ctx.els.channels;
    if (!host) return;
    P.clear(host);
    var m = ctx.state.chM, tot = model.tot, agg = model.agg;
    if (!(tot[m] > 0)) {
      host.appendChild(P.el('div', 's-empty', '이 기간에는 ' + (m === 'expected' ? '예상' : '실제') + ' 매출이 없습니다.'
        + (m === 'expected' ? '' : ' 위에서 \'예상\'을 눌러 보세요.')));
      return;
    }
    var line = P.el('div', 's-pr-chline s-pr-chline--total');
    line.appendChild(P.el('b', null, '전체'));
    line.appendChild(chBar(ctx, tot, m));
    line.appendChild(P.el('span', null, P.wonU(tot[m])));
    host.appendChild(line);
    var g = P.orderedFamilies(model, ctx.state.sort);
    g.main.concat(g.rest).forEach(function (c) {
      var a = agg[c];
      if (!(a[m] > 0)) return;
      var ln = P.el('div', 's-pr-chline');
      var b = P.el('b', P.NON_PRODUCT[c] ? 's-pr-muted' : null, model.famLabel[c]);
      b.title = model.famLabel[c];
      ln.appendChild(b);
      ln.appendChild(chBar(ctx, a, m));
      ln.appendChild(P.el('span', null, P.won(a[m])));
      host.appendChild(ln);
    });
  };

  P.cards = true;
  if (typeof P.mountAll === 'function') P.mountAll();
})();

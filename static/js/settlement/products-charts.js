/**
 * 정산 대시보드 · 탭 "제품별" — 시리즈 · 월별 추이.
 *
 * 시리즈는 구간 합계(`period`)를, 월별 추이만 `trend`(기간 끝 달로 끝나는 12개월)를 읽고 `selected_months` 를 칠해 강조한다.
 * 추이 SVG 는 호스트 폭으로 viewBox 를 잡고 CSS 가 100% 로 늘린다 — 숨은 pane 에서 그려 폭이 0 이면
 * 300 폭으로 그려 비율만 조금 다르고, 탭이 열리거나 폭이 바뀌면 진입점이 다시 그린다.
 */
(function () {
  'use strict';

  var P = window.FomsSettleProducts = window.FomsSettleProducts || {};
  var NS = 'http://www.w3.org/2000/svg';

  /* 칩에 쓰는 짧은 제품 이름("여닫이 붙박이장(기본)" → "여닫이"). 없는 코드는 API 라벨 그대로. */
  var FAM_SHORT = { SWING: '여닫이', NOMOLD_SWING: '무몰딩 여닫이', MOLD_SWING: '몰딩 여닫이', SLIDING: '슬라이딩',
    KITCHEN: '부엌가구', REFRIG: '냉장고장', REFRIG_REFORM: '냉장고장 리폼', TV_WALL: 'TV월플렉스', HOMECAFE: '홈카페장',
    SHOE: '신발장', HANGER: '시스템행거', STORAGE: '수납장', DOOR: '도어', EXTRA: '부대비용', PLACEHOLDER: '미입력', OTHER: '기타' };

  function word(m) { return m === 'actual' ? '실제' : '예상'; }
  function sw(color) { var s = P.el('i', 's-pr-sw'); s.style.setProperty('--s-pr-c', color); return s; }
  function tds(tr, values) { values.forEach(function (v) { tr.appendChild(P.el('td', null, v)); }); return tr; }

  /* ═══════════════ 시리즈 ═══════════════ */

  function serGroupsOf(model, a, m) {
    var out = {};
    model.serGroups.forEach(function (g) { out[g.key] = 0; });
    Object.keys(a.series).forEach(function (k) { out[model.serGroupOf(k)] += P.num(a.series[k][m]); });
    return out;
  }

  function serBar(ctx, model, vals, total, m, title) {
    var bar = P.el('div', 's-pr-chbar' + (m === 'expected' ? ' s-pr-chbar--plan' : ''));
    if (!(total > 0)) return bar;
    model.serGroups.forEach(function (g) {
      var v = vals[g.key];
      if (!(v > 0)) return;
      var p = P.pct(v, total);
      var s = P.el('div', 's-pr-chseg' + (g.dark ? ' s-pr-chseg--dark' : ''),
        p >= 22 ? g.label + ' ' + Math.round(p) + '%' : p >= 9 ? Math.round(p) + '%' : '');
      s.style.setProperty('--s-pr-pct', p + '%');
      s.style.setProperty('--s-pr-c', g.color);
      P.bindTip(ctx, s, function () {
        return [title + ' · ' + g.label, [{ c: g.color, l: word(m), v: P.wonU(v) }, { l: '비중', v: p.toFixed(1) + '%' }]];
      });
      bar.appendChild(s);
    });
    return bar;
  }

  P.renderSeries = function (ctx, model) {
    var els = ctx.els, m = ctx.state.seM, agg = model.agg, groups = model.serGroups;
    if (!els.seriesList || !els.seriesTable) return;
    P.clear(els.seriesLegend);
    groups.forEach(function (g) {
      var s = P.el('span', 's-lg');
      s.appendChild(sw(g.color));
      s.appendChild(document.createTextNode(g.label));
      if (els.seriesLegend) els.seriesLegend.appendChild(s);
    });
    P.clear(els.seriesList);
    P.clear(els.seriesTable);
    var fams = model.famOrder.filter(function (c) { return agg[c].hasSeries; });
    var sumE = {}, sumA = {}, detailE = {}, detailA = {};
    groups.forEach(function (g) { sumE[g.key] = 0; sumA[g.key] = 0; });
    fams.forEach(function (c) {
      var e = serGroupsOf(model, agg[c], 'expected'), a = serGroupsOf(model, agg[c], 'actual');
      groups.forEach(function (g) { sumE[g.key] += e[g.key]; sumA[g.key] += a[g.key]; });
      Object.keys(agg[c].series).forEach(function (k) {
        if (model.serGroupOf(k) !== '__other') return;
        detailE[k] = (detailE[k] || 0) + agg[c].series[k].expected;
        detailA[k] = (detailA[k] || 0) + agg[c].series[k].actual;
      });
    });
    var sums = m === 'actual' ? sumA : sumE, total = 0;
    Object.keys(sums).forEach(function (k) { total += sums[k]; });
    if (els.seriesSub) {
      els.seriesSub.textContent = '도어 라인별 · 시리즈 정보가 있는 '
        + fams.filter(function (c) { return agg[c][m] > 0; }).length + '개 제품군';
    }
    if (!(total > 0)) {
      els.seriesList.appendChild(P.el('div', 's-empty', '이 기간에는 시리즈별 ' + word(m) + ' 매출이 없습니다.'));
      return;
    }
    var line = P.el('div', 's-pr-chline s-pr-chline--total');
    line.appendChild(P.el('b', null, '전체'));
    line.appendChild(serBar(ctx, model, sums, total, m, '전체'));
    line.appendChild(P.el('span', null, P.wonU(total)));
    els.seriesList.appendChild(line);
    fams.slice().sort(function (a, b) { return agg[b][m] - agg[a][m]; }).forEach(function (c) {
      var v = serGroupsOf(model, agg[c], m), t = 0;
      Object.keys(v).forEach(function (k) { t += v[k]; });
      if (!(t > 0)) return;
      var ln = P.el('div', 's-pr-chline');
      var b = P.el('b', null, model.famLabel[c]);
      b.title = model.famLabel[c];
      ln.appendChild(b);
      ln.appendChild(serBar(ctx, model, v, t, m, model.famLabel[c]));
      ln.appendChild(P.el('span', null, P.won(t)));
      els.seriesList.appendChild(ln);
    });

    // 표: 시리즈 · 실제 · 예상 · 수량 · 비중. 시리즈마다 바로 아래 "시리즈 제품 N개" 칩 줄(사용자 요청 2026-10-07).
    var totA = 0, totE = 0;
    groups.forEach(function (g) { totA += sumA[g.key]; totE += sumE[g.key]; });
    var itemKey = m === 'actual' ? 'actual_items' : 'expected_items';
    function qtyOf(keys) {
      var n = 0;
      fams.forEach(function (c) { keys.forEach(function (k) { n += P.num((agg[c].series[k] || {})[itemKey]); }); });
      return n;
    }
    function chipsRow(k) {
      var list = [];
      fams.forEach(function (c) { var n = P.num((agg[c].series[k] || {})[itemKey]); if (n > 0) list.push([c, n]); });
      if (!list.length) return null;
      list.sort(function (a, b) { return b[1] - a[1]; });
      var tr = P.el('tr', 's-pr-dt-chips'), td = P.el('td');
      td.colSpan = 5;
      list.forEach(function (x) {
        var chip = P.el('span', 's-pr-sechip', model.serLabel[k] + ' ' + (FAM_SHORT[x[0]] || model.famLabel[x[0]] || x[0]));
        chip.appendChild(P.el('b', null, x[1].toLocaleString('ko-KR') + '개'));
        td.appendChild(chip);
      });
      tr.appendChild(td);
      return tr;
    }
    var memberKeys = {};
    Object.keys(model.serLabel).forEach(function (k) {
      var g = model.serGroupOf(k);
      (memberKeys[g] = memberKeys[g] || []).push(k);
    });
    var thead = P.el('thead'), hr = P.el('tr');
    ['시리즈', '실제', '예상', '수량(' + word(m) + ')', word(m) + ' 비중'].forEach(function (t) { hr.appendChild(P.el('th', null, t)); });
    thead.appendChild(hr);
    els.seriesTable.appendChild(thead);
    var tb = P.el('tbody'), share = m === 'actual' ? totA : totE;
    groups.forEach(function (g) {
      var tr = P.el('tr'), td = P.el('td');
      td.appendChild(sw(g.color));
      td.appendChild(document.createTextNode(g.label));
      tr.appendChild(td);
      tds(tr, [P.won(sumA[g.key]), P.won(sumE[g.key]), qtyOf(memberKeys[g.key] || []).toLocaleString('ko-KR') + '개',
        P.pctTxt(m === 'actual' ? sumA[g.key] : sumE[g.key], share)]);
      tb.appendChild(tr);
      // 기본(시리즈 없음)은 칩을 달지 않는다 — 제품군 전체 목록이 되어 위 제품군 카드와 겹친다.
      if (g.key !== '__other' && g.key !== 'BASIC') { var cr = chipsRow(g.key); if (cr) tb.appendChild(cr); }
      if (g.key !== '__other') return;
      Object.keys(detailE).sort(function (a, b) { return detailE[b] - detailE[a]; }).forEach(function (k) {
        // 이 기간에 매출도 수량도 없는 시리즈는 줄을 내지 않는다(0 줄이 길게 쌓여 읽기를 막는다).
        if (!(detailE[k] > 0) && !((detailA[k] || 0) > 0) && qtyOf([k]) === 0) return;
        tb.appendChild(tds(P.el('tr', 's-pr-dt-sub'), [model.serLabel[k], P.won(detailA[k] || 0), P.won(detailE[k]),
          qtyOf([k]).toLocaleString('ko-KR') + '개', P.pctTxt(m === 'actual' ? detailA[k] || 0 : detailE[k], share)]));
        var cr2 = chipsRow(k);
        if (cr2) tb.appendChild(cr2);
      });
    });
    els.seriesTable.appendChild(tb);
  };

  /* ═══════════════ 월별 추이(소형 다중) ═══════════════ */

  function niceMax(v) {
    if (v <= 0) return 1;
    var p = Math.pow(10, Math.floor(Math.log10(v))), x = v / p;
    return (x <= 1 ? 1 : x <= 2 ? 2 : x <= 2.5 ? 2.5 : x <= 5 ? 5 : 10) * p;
  }

  function drawMini(ctx, host, p, max, sel, mode, nowMonth) {
    var W = Math.max(240, host.clientWidth || 300), H = 150;
    var padL = 38, padR = 4, padT = 8, padB = 20, plotW = W - padL - padR, plotH = H - padT - padB;
    var n = Math.max(1, p.series.length), slot = plotW / n;
    var pw = Math.max(4, Math.min(28, slot * 0.64)), rw = mode === 'both' ? Math.max(2, pw * 0.5) : pw;
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.setAttribute('width', W);
    svg.setAttribute('height', H);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', p.label + ' 월별 예상·실제 매출');
    function add(tag, at, txt) {
      var x = document.createElementNS(NS, tag);
      Object.keys(at).forEach(function (k) { x.setAttribute(k, at[k]); });
      if (txt != null) x.textContent = txt;
      svg.appendChild(x);
      return x;
    }
    p.series.forEach(function (s, i) {
      if (sel.indexOf(s.m) >= 0) add('rect', { x: padL + slot * i, y: padT - 4, width: slot, height: plotH + 4, class: 's-pr-sel-band' });
    });
    [0, 0.5, 1].forEach(function (f) {
      var y = padT + plotH - plotH * f;
      add('line', { x1: padL, x2: W - padR, y1: y, y2: y, class: f ? 's-pr-gl' : 's-pr-bl' });
      if (f) add('text', { x: padL - 6, y: y + 4, 'text-anchor': 'end', class: 's-pr-ax' }, P.tick(max * f));
    });
    var every = slot < 26 ? 2 : 1;
    p.series.forEach(function (s, i) {
      var cx = padL + slot * i + slot / 2;
      var he = Math.min(plotH, plotH * s.e / max), ha = Math.min(plotH, plotH * s.a / max);
      if (mode !== 'actual' && s.e > 0) add('rect', { x: cx - pw / 2, y: padT + plotH - he, width: pw, height: he, rx: Math.min(3, pw / 2), class: 's-pr-bar-plan' });
      if (mode !== 'expected' && s.a > 0) add('rect', { x: cx - rw / 2, y: padT + plotH - ha, width: rw, height: ha, rx: Math.min(2.5, rw / 2), class: 's-pr-bar-real' });
      if (i % every === 0 || s.m === nowMonth) {
        add('text', { x: cx, y: H - 5, 'text-anchor': 'middle',
          class: 's-pr-ax' + (s.m === nowMonth ? ' s-pr-ax--now' : sel.indexOf(s.m) >= 0 ? ' s-pr-ax--sel' : '') }, (+s.m.slice(5, 7)) + '월');
      }
      var hit = add('rect', { x: cx - slot / 2, y: padT, width: slot, height: plotH, class: 's-pr-hit', tabindex: 0 });
      hit.setAttribute('aria-label', P.monthKo(s.m, true) + ' 예상 ' + P.wonU(s.e) + ', 실제 ' + P.wonU(s.a));
      P.bindTip(ctx, hit, function () {
        return [p.label + ' · ' + P.monthKo(s.m, true) + (s.m === nowMonth ? ' (진행 중)' : ''), [
          { c: 'var(--s-plan-edge)', l: '예상', v: P.wonU(s.e) }, { c: 'var(--s-accent)', l: '실제', v: P.wonU(s.a) },
          { l: '달성률', v: P.pctTxt(s.a, s.e) }]];
      });
    });
    host.appendChild(svg);
  }

  P.renderTrend = function (ctx, model) {
    var els = ctx.els, st = ctx.state, agg = model.agg, months = model.months, sel = model.selected;
    if (!els.trend) return;
    P.clear(els.trend);
    P.clear(els.trendNote);
    var products = model.famOrder.filter(function (c) { return !P.NON_PRODUCT[c]; });
    var top = products.filter(function (c) { return agg[c].expected > 0; })
      .sort(function (a, b) { return agg[b].expected - agg[a].expected; }).slice(0, 5);
    if (!top.length) top = products.slice(0, 5);
    var restCodes = model.famOrder.filter(function (c) { return top.indexOf(c) < 0; });
    var panels = top.map(function (c) { return { label: model.famLabel[c], codes: [c] }; });
    panels.push({ label: '나머지 ' + restCodes.length + '개 제품군', codes: restCodes, rest: true });
    var mode = st.trM, nowMonth = model.today.slice(0, 7);
    if (!months.length) {
      els.trend.appendChild(P.el('div', 's-empty', '월별 추이 자료가 없습니다.'));
      return;
    }
    panels.forEach(function (p) {
      p.series = months.map(function (m) {
        var e = 0, a = 0, mo = model.byMonth[m] || {};
        p.codes.forEach(function (c) { var x = mo[c]; if (x) { e += P.num(x.expected); a += P.num(x.actual); } });
        return { m: m, e: e, a: a };
      });
      p.max = Math.max.apply(null, p.series.map(function (s) {
        return mode === 'actual' ? s.a : mode === 'expected' ? s.e : Math.max(s.e, s.a);
      }).concat([1]));
      p.selE = 0; p.selA = 0;
      p.series.forEach(function (s) { if (sel.indexOf(s.m) >= 0) { p.selE += s.e; p.selA += s.a; } });
    });
    // 공통 눈금은 상위 5개 칸으로만 정한다 — '나머지'는 여러 제품군의 합이라 늘 커서 같이 재면 다 납작해진다.
    var shared = niceMax(Math.max.apply(null, panels.filter(function (p) { return !p.rest; })
      .map(function (p) { return p.max; }).concat([1])));
    panels.forEach(function (p) {
      var box = P.el('div', 's-pr-tm'), head = P.el('div', 's-pr-tm-head');
      var b = P.el('b', null, p.label);
      b.title = p.rest ? p.codes.map(function (c) { return model.famLabel[c]; }).join(', ') : p.label;
      if (p.rest && !st.trFree) head.appendChild(P.el('span', 's-pr-tm-own', '눈금 따로'));
      head.appendChild(b);
      head.appendChild(P.rich(P.el('span', 's-pr-tm-meta'), mode === 'expected' ? ['예상 ', { strong: P.won(p.selE) }]
        : ['실제 ', { strong: P.won(p.selA) }, mode === 'both' ? ' / 예상 ' + P.won(p.selE) : '']));
      box.appendChild(head);
      var host = P.el('div', 's-pr-tm-chart');
      box.appendChild(host);
      els.trend.appendChild(box);
      drawMini(ctx, host, p, st.trFree || p.rest ? niceMax(p.max) : shared, sel, mode, nowMonth);
    });
    if (els.trendSub) {
      els.trendSub.textContent = '고른 기간 예상 매출 상위 5개 제품군 + 나머지 · '
        + P.monthKo(months[0], true) + ' ~ ' + P.monthKo(months[months.length - 1], true);
    }
    var note = st.trFree
      ? ['칸마다 세로 눈금이 다릅니다 — ', { b: '모양(오르내림)' }, '을 비교할 때 쓰고, 크기는 칸끼리 비교하지 마세요.']
      : ['상위 5개 칸은 ', { b: '같은 세로 눈금' }, '이라 막대 높이를 바로 비교할 수 있습니다. 나머지 칸만 합계가 커서 눈금이 따로입니다.'];
    note.push(' 파란 칠 = 기간 바에서 고른 달.');
    if (months.indexOf(nowMonth) >= 0) {
      note.push(' ' + P.monthKo(nowMonth) + '은 진행 중이라 실제가 ' + (+model.today.slice(8, 10)) + '일까지만 들어 있습니다.');
    }
    if (months[months.length - 1] > nowMonth) note.push(' 이후 달은 시공일이 잡힌 만큼만 예상이 있습니다.');
    P.rich(els.trendNote, note);
  };

  P.charts = true;
  if (typeof P.mountAll === 'function') P.mountAll();
})();

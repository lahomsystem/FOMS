/**
 * 정산 대시보드 · 탭 "제품별" — 공용 조각(표기 · DOM · 툴팁 · 응답 → 화면 모델).
 *
 * 이 탭의 스크립트는 5개로 나뉜다(파일당 300줄 래칫 — tests/harness/test_file_size_ratchet.py):
 *   products-core.js   표기 · DOM · 툴팁 · 모델(이 파일)
 *   products-cards.js  KPI · 제품군별 매출 · 채널별 제품 구성
 *   products-charts.js 시리즈 · 월별 추이
 *   products-quality.js 분류 안 된 품목 · 검산
 *   products.js        마운트 · 조회 · 상태 · 조작(진입점)
 * 서로는 전역 이름공간 `window.FomsSettleProducts` 하나로만 만난다. 프래그먼트 스왑 때 셸이
 * `<script src>` 를 다시 실행해도 같은 함수를 다시 대입할 뿐이라 누적되는 것이 없다. 로드 순서가
 * 흔들려도 되게, 각 조각은 끝에서 `P.mountAll` 이 있으면 부른다(진입점이 조각이 다 왔는지 본다).
 *
 * 데이터 문자열(제품군·품목 이름)은 전부 textContent 로 넣는다(innerHTML 미사용).
 */
(function () {
  'use strict';

  var P = window.FomsSettleProducts = window.FomsSettleProducts || {};

  /* 제품이 아닌 칸 — 순위·1위·추이 상위에서 빼고 '분류 밖' 묶음으로 내린다. */
  P.NON_PRODUCT = { EXTRA: 1, PLACEHOLDER: 1, OTHER: 1 };
  /* 시리즈 색 — 매출 상위 5개 시리즈에 순서대로(dataviz 검증 통과 순서). 기타 · 기본은 회색 계열. */
  var SERIES_COLORS = ['#4a3aa7', '#eda100', '#1baf7a', '#e34948', '#8a3b6b'];
  var DARK_INK = { '#eda100': 1, '#1baf7a': 1 };
  var SERIES_OTHER_COLOR = '#8a94a3';
  var SERIES_BASIC_COLOR = '#d3d9e2';
  var COUNT_KEYS = ['expected', 'actual', 'expected_items', 'actual_items',
    'expected_orders', 'actual_orders', 'expected_raw', 'actual_raw'];
  var CHANNEL_KEYS = ['general', 'lahom', 'naver'];

  /* ═══════════════ 표기 ═══════════════ */

  function num(v) { v = +v; return isFinite(v) ? v : 0; }
  function fmtMan(m) {
    m = Math.round(m);
    if (m === 0) return '0';
    var neg = m < 0 ? '−' : '';
    m = Math.abs(m);
    if (m >= 10000) {
      var e = Math.floor(m / 10000), r = m % 10000;
      return neg + (r ? e + '억 ' + r.toLocaleString('ko-KR') + '만' : e + '억');
    }
    return neg + m.toLocaleString('ko-KR') + '만';
  }
  P.num = num;
  P.won = function (w) { return fmtMan(num(w) / 10000); };
  P.wonU = function (w) { return P.won(w) + '원'; };
  P.tick = function (w) {
    var m = w / 10000;
    if (m === 0) return '0';
    if (m >= 10000) { var e = m / 10000; return (Number.isInteger(e) ? e : e.toFixed(1)) + '억'; }
    return Math.round(m).toLocaleString('ko-KR') + '만';
  };
  P.cnt = function (n) { return Math.round(num(n)).toLocaleString('ko-KR'); };
  P.pct = function (a, b) { return b > 0 ? a / b * 100 : 0; };
  P.pctTxt = function (a, b, d) { return b > 0 ? P.pct(a, b).toFixed(d == null ? 1 : d) + '%' : '-'; };
  P.monthKo = function (m, withYear) {
    return (withYear ? m.slice(0, 4) + '년 ' : '') + (+m.slice(5, 7)) + '월';
  };
  /** 서울 기준 오늘(YYYY-MM-DD). 진행 중인 달 표기에만 쓴다. */
  P.kstToday = function () {
    return new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);
  };

  /* ═══════════════ DOM ═══════════════ */

  P.el = function (tag, cls, text) {
    var x = document.createElement(tag);
    if (cls) x.className = cls;
    if (text != null) x.textContent = text;
    return x;
  };
  P.clear = function (node) { if (node) node.textContent = ''; };
  /**
   * 굵은 글씨가 섞인 문장을 노드로 짓는다. parts 의 문자열은 그대로, `{b: '...'}` 는 <b>,
   * `{cls, t}` 는 그 클래스의 <span> 이다 — 데이터가 섞이는 문장에서 innerHTML 을 쓰지 않으려고.
   */
  P.rich = function (node, parts) {
    parts.forEach(function (p) {
      if (p == null || p === '') return;
      if (typeof p === 'string') node.appendChild(document.createTextNode(p));
      else if (p.b != null) node.appendChild(P.el('b', null, p.b));
      else if (p.strong != null) node.appendChild(P.el('strong', null, p.strong));
      else node.appendChild(P.el('span', p.cls || null, p.t));
    });
    return node;
  };
  /** 세그먼트 버튼의 aria-pressed 를 현재 값에 맞춘다. */
  P.syncPressed = function (root, attr, value) {
    root.querySelectorAll('[' + attr + ']').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute(attr) === value));
    });
  };

  /* ═══════════════ 툴팁(탭 전용 한 벌, 좌표는 CSS 변수) ═══════════════ */

  P.showTip = function (ctx, x, y, title, rows) {
    var tt = ctx.els.tt;
    if (!tt) return;
    tt.textContent = '';
    tt.appendChild(P.el('div', 's-tt-title', title));
    rows.forEach(function (r) {
      if (!r) return;
      var row = P.el('div', 's-tt-row');
      var key = P.el('i', 's-tt-key');
      if (r.c) key.style.setProperty('--s-key-color', r.c);
      row.appendChild(key);
      row.appendChild(P.el('span', 's-tt-lbl', r.l));
      row.appendChild(P.el('span', 's-tt-val', r.v));
      tt.appendChild(row);
    });
    tt.classList.add('s-on');
    var w = tt.offsetWidth, h = tt.offsetHeight;
    var vw = document.documentElement.clientWidth, vh = window.innerHeight;
    var left = x + 14;
    if (left + w > vw - 8) left = Math.max(8, x - w - 14);
    var top = y + 14;
    if (top + h > vh - 8) top = Math.max(8, y - h - 14);
    tt.style.setProperty('--s-tt-x', left + 'px');
    tt.style.setProperty('--s-tt-y', top + 'px');
  };
  P.hideTip = function (ctx) { if (ctx.els.tt) ctx.els.tt.classList.remove('s-on'); };
  /** 노드 하나에 툴팁을 단다. fn() 은 [제목, 줄 배열] 을 돌려준다(그릴 때 값을 읽는다). */
  P.bindTip = function (ctx, node, fn) {
    node.addEventListener('pointermove', function (e) {
      var a = fn();
      P.showTip(ctx, e.clientX, e.clientY, a[0], a[1]);
    });
    node.addEventListener('pointerleave', function () { P.hideTip(ctx); });
    node.addEventListener('focus', function () {
      var r = node.getBoundingClientRect(), a = fn();
      P.showTip(ctx, r.left + r.width / 2, r.top + r.height / 2, a[0], a[1]);
    });
    node.addEventListener('blur', function () { P.hideTip(ctx); });
  };

  /* ═══════════════ 응답 → 화면 모델 ═══════════════ */

  function blank() {
    var t = { series: {}, hasSeries: false };
    COUNT_KEYS.forEach(function (k) { t[k] = 0; });
    CHANNEL_KEYS.forEach(function (c) { t[c] = { expected: 0, actual: 0 }; });
    return t;
  }
  /** 제품군 칸 하나(FAMILY_ENTRY)를 누적한다. 빠진 키·이상한 값은 0 으로 읽는다. */
  function addInto(t, e) {
    if (!e) return;
    COUNT_KEYS.forEach(function (k) { t[k] += num(e[k]); });
    CHANNEL_KEYS.forEach(function (c) {
      var s = e[c] || {};
      t[c].expected += num(s.expected);
      t[c].actual += num(s.actual);
    });
    var s = e.series;
    if (!s || typeof s !== 'object') return;
    Object.keys(s).forEach(function (k) {
      var src = s[k] || {};
      var dst = t.series[k] || (t.series[k] = { expected: 0, actual: 0, expected_items: 0, actual_items: 0 });
      dst.expected += num(src.expected);
      dst.actual += num(src.actual);
      dst.expected_items += num(src.expected_items);
      dst.actual_items += num(src.actual_items);
      t.hasSeries = true;
    });
  }

  /**
   * API data → 카드들이 읽는 모델. 구간 합계(`period`)는 서버가 이미 정확한 날짜 범위로
   * 모았으므로 여기서는 다시 더하지 않고 제품군 칸을 정규화만 한다(합계 줄만 더한다).
   * 제품군 · 시리즈 사전은 API 순서가 SSOT 이고, 사전에 없는 코드가 와도 코드 이름으로 받는다.
   */
  P.buildModel = function (data) {
    var famLabel = {}, famOrder = [], serLabel = {}, serOrder = [];
    var period = data.period || {};
    (data.families || []).forEach(function (f) {
      if (f && f.code && !famLabel[f.code]) { famLabel[f.code] = f.label || f.code; famOrder.push(f.code); }
    });
    Object.keys(period).forEach(function (c) {
      if (!famLabel[c]) { famLabel[c] = c; famOrder.push(c); }
    });
    (data.series || []).forEach(function (s) {
      if (s && s.code && !serLabel[s.code]) { serLabel[s.code] = s.label || s.code; serOrder.push(s.code); }
    });

    var agg = {}, tot = blank();
    famOrder.forEach(function (c) {
      agg[c] = blank();
      addInto(agg[c], period[c]);
      addInto(tot, period[c]);
    });

    // 시리즈 색은 이 기간 예상 매출 상위 5개(기본 제외)에 붙인다.
    var serAll = {};
    famOrder.forEach(function (c) {
      Object.keys(agg[c].series).forEach(function (k) {
        serAll[k] = (serAll[k] || 0) + agg[c].series[k].expected;
        if (!serLabel[k]) { serLabel[k] = k; serOrder.push(k); }
      });
    });
    var serTop = Object.keys(serAll)
      .filter(function (k) { return k !== 'BASIC' && serAll[k] > 0; })
      .sort(function (a, b) { return serAll[b] - serAll[a]; })
      .slice(0, SERIES_COLORS.length);
    var serGroups = serTop.map(function (k, i) {
      return { key: k, label: serLabel[k], color: SERIES_COLORS[i], dark: !!DARK_INK[SERIES_COLORS[i]] };
    });
    var hasOther = Object.keys(serAll).some(function (k) {
      return k !== 'BASIC' && serTop.indexOf(k) < 0;
    });
    if (hasOther) serGroups.push({ key: '__other', label: '기타 시리즈', color: SERIES_OTHER_COLOR, dark: false });
    serGroups.push({ key: 'BASIC', label: serLabel.BASIC || '기본', color: SERIES_BASIC_COLOR, dark: true });

    var trend = data.trend || {};
    return {
      data: data,
      range: data.range || {},
      famOrder: famOrder,
      famLabel: famLabel,
      serLabel: serLabel,
      serOrder: serOrder,
      agg: agg,
      tot: tot,
      serGroups: serGroups,
      serGroupOf: function (k) { return k === 'BASIC' ? 'BASIC' : serTop.indexOf(k) >= 0 ? k : '__other'; },
      months: (trend.months || []).slice().sort(),
      byMonth: trend.by_month || {},
      selected: data.selected_months || [],
      topNames: data.top_names || {},
      today: P.kstToday(),
    };
  };

  P.core = true;
  if (typeof P.mountAll === 'function') P.mountAll();
})();

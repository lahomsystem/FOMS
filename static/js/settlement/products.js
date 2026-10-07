/**
 * 정산 대시보드 · 탭 "제품별"(제품군 · 시리즈별 매출) — 진입점: 마운트 · 조회 · 상태 · 조작.
 *
 * **데이터 소스는 `GET /api/settlement/products` 하나다**(루트 `data-products-url`). 응답 data 의
 * 최상위 키: range · families · series · period(구간 합계) · trend(12개월) · selected_months ·
 * top_names · unmapped_top · coverage · allocation_check. KPI·제품군·채널·시리즈·분류 안 된 품목
 * 카드는 period 를, 월별 추이는 trend 를 읽는다. 렌더는 products-core/-cards/-charts/-quality.js 가 맡는다.
 *
 * **공통 기간**: dashboard.js 가 셸 루트에 적는 `data-settlement-date-range="YYYY-MM-DD..YYYY-MM-DD"`
 * 를 조회 구간으로 쓰고 MutationObserver 로 따라간다(operations.js · channel.js 와 같은 방식 — 새
 * 이벤트를 만들지 않는다). 첫 조회는 탭이 처음 열릴 때다(`data-settlement-active-tab` 관찰) —
 * 요약 탭만 보고 나가는 사용자에게 품목 전량 집계 왕복을 물리지 않는다.
 *
 * **상태 4종**: 불러오는 중 · 실패(재시도) · 권한 없음(403) · 빈 기간 — 서로 다른 노드·문구다.
 * 셸 루트의 로딩/실패 노드는 요약·분석 집계 전용이라 이 탭은 자기 노드(`data-products-*`)를 쓴다.
 *
 * **프래그먼트 재실행 규율(perf G4)**: document 리스너는 `window.__FOMS_SETTLEMENT_PRODUCTS_BOUND`
 * 싱글톤 뒤에서 1회만, 마운트는 루트의 `data-settlement-products-mounted` 표식으로 루트당 1회,
 * mountAll() 은 스크립트 재실행과 swap 이벤트 양쪽에서 부르고 떨어져 나간 루트의 옵저버를 정리한다.
 */
(function () {
  'use strict';

  var P = window.FomsSettleProducts = window.FomsSettleProducts || {};
  var ROOT_SELECTOR = '[data-foms-settlement-products]';
  var PRODUCTS_FALLBACK = '/api/settlement/products';
  var PRODUCTS_TAB = 'products';
  var RANGE_RE = /^(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})$/;
  var RESIZE_DEBOUNCE_MS = 150;

  /** 렌더 조각 4개가 다 실렸는지 — 스왑 재실행 순서가 흔들려도 덜 실린 채 마운트하지 않는다. */
  function partsReady() { return !!(P.core && P.cards && P.charts && P.quality); }

  function toggle(node, hide) { if (node) node.classList.toggle('s-hidden', !!hide); }

  function showState(ctx, kind, detail) {
    toggle(ctx.els.loading, kind !== 'loading');
    toggle(ctx.els.error, kind !== 'error');
    toggle(ctx.els.denied, kind !== 'denied');
    toggle(ctx.els.grid, kind !== 'ready');
    if (kind === 'error' && ctx.els.errorDetail && detail) ctx.els.errorDetail.textContent = detail;
    if (kind !== 'ready') P.hideTip(ctx);
  }

  /* ═══════════════ 조회 ═══════════════ */

  function shellOf(ctx) { return ctx.root.closest('[data-settlement-active-tab]'); }

  /** 셸 공통 기간. 셸 밖 단독 렌더면 null — 서버 기본(이번 달 KST)으로 본다. */
  function shellRange(ctx) {
    var shell = shellOf(ctx);
    var m = RANGE_RE.exec((shell && shell.getAttribute('data-settlement-date-range')) || '');
    return m ? { from: m[1], to: m[2] } : null;
  }

  function buildUrl(ctx) {
    var base = ctx.root.getAttribute('data-products-url') || PRODUCTS_FALLBACK;
    var range = shellRange(ctx);
    if (!range) return base;
    return base + (base.indexOf('?') === -1 ? '?' : '&')
      + 'date_from=' + encodeURIComponent(range.from) + '&date_to=' + encodeURIComponent(range.to);
  }

  function failureReason(res, body) {
    if (body && body.error) return String(body.error);
    if (res && !res.ok) return '서버 응답 오류 (HTTP ' + res.status + ')';
    return '응답 형식이 올바르지 않습니다. 잠시 뒤 다시 시도하세요.';
  }

  async function load(ctx) {
    var state = ctx.state;
    var seq = ++state.seq;
    showState(ctx, 'loading');
    try {
      var res = await fetch(buildUrl(ctx), { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      var body = null;
      try { body = await res.json(); } catch (parseError) { body = null; }
      if (seq !== state.seq) return;   // 늦게 온 응답이 최신 기간 화면을 덮지 않게 한다
      if (res.status === 403) {
        showState(ctx, 'denied');
        return;
      }
      if (!res.ok || !body || body.success !== true || !body.data) {
        showState(ctx, 'error', failureReason(res, body));
        return;
      }
      state.model = P.buildModel(body.data);
      showState(ctx, 'ready');
      renderAll(ctx);
    } catch (err) {
      if (seq !== state.seq) return;
      showState(ctx, 'error', '정산 서버에 연결하지 못했습니다. 네트워크를 확인한 뒤 다시 시도하세요.');
    }
  }

  /* ═══════════════ 렌더 ═══════════════ */

  function renderRange(ctx, model) {
    var node = ctx.els.range;
    if (!node) return;
    P.clear(node);
    var r = model.range, from = r.date_from || '', to = r.date_to || '';
    var parts = ['조회 기간 ', { b: from === to ? from : from + ' ~ ' + to }, ' · 시공일 기준'];
    if (from && from <= model.today && model.today <= to) {
      parts.push(' · ', { cls: 's-pr-partial', t: '오늘(' + model.today + ')이 든 기간 — 실제 매출은 오늘까지 완료된 주문만' });
    }
    P.rich(node, parts);
  }

  function renderAll(ctx) {
    var model = ctx.state.model, st = ctx.state;
    if (!model) return;
    P.syncPressed(ctx.root, 'data-products-sort', st.sort);
    P.syncPressed(ctx.root, 'data-products-ch', st.chM);
    P.syncPressed(ctx.root, 'data-products-se', st.seM);
    P.syncPressed(ctx.root, 'data-products-tr', st.trM);
    if (ctx.els.trScale) ctx.els.trScale.setAttribute('aria-pressed', String(st.trFree));
    toggle(ctx.els.empty, model.tot.expected > 0 || model.tot.actual > 0);
    renderRange(ctx, model);
    P.renderKpis(ctx, model);
    P.renderFamilies(ctx, model);
    P.renderChannels(ctx, model);
    P.renderSeries(ctx, model);
    P.renderTrend(ctx, model);
    P.renderUnmapped(ctx, model);
  }

  /* ═══════════════ 조작(루트 위임 한 곳) ═══════════════ */

  var SEGMENTS = [
    ['data-products-sort', 'sort'], ['data-products-ch', 'chM'],
    ['data-products-se', 'seM'], ['data-products-tr', 'trM'],
  ];

  function bindControls(ctx) {
    ctx.root.addEventListener('click', function (e) {
      var target = e.target;
      if (!target || !target.closest) return;
      if (target.closest('[data-products-retry]')) {
        load(ctx);
        return;
      }
      var fam = target.closest('[data-products-fam]');
      if (fam && ctx.root.contains(fam)) {
        var code = fam.getAttribute('data-products-fam');
        ctx.state.open[code] = !ctx.state.open[code];
        renderAll(ctx);
        return;
      }
      if (target.closest('[data-products-trscale]')) {
        ctx.state.trFree = !ctx.state.trFree;
        renderAll(ctx);
        return;
      }
      for (var i = 0; i < SEGMENTS.length; i += 1) {
        var btn = target.closest('[' + SEGMENTS[i][0] + ']');
        if (btn && ctx.root.contains(btn)) {
          ctx.state[SEGMENTS[i][1]] = btn.getAttribute(SEGMENTS[i][0]);
          renderAll(ctx);
          return;
        }
      }
    });
  }

  /* ═══════════════ 탭 활성화 · 기간 · 폭 관찰 ═══════════════ */

  function ensureLoaded(ctx) {
    if (ctx.state.loaded) return;
    ctx.state.loaded = true;
    load(ctx);
  }

  function watchShell(ctx) {
    var shell = shellOf(ctx);
    if (!shell || typeof MutationObserver !== 'function') {
      ensureLoaded(ctx);   // 셸 밖 단독 렌더 — 관찰할 대상이 없으니 바로 연다
      return;
    }
    if (shell.getAttribute('data-settlement-active-tab') === PRODUCTS_TAB) ensureLoaded(ctx);
    ctx.observer = new MutationObserver(function () {
      if (shell.getAttribute('data-settlement-active-tab') !== PRODUCTS_TAB) {
        P.hideTip(ctx);
        return;
      }
      ensureLoaded(ctx);
      renderAll(ctx);   // 숨은 pane 에서 그린 추이 SVG 를 보이는 폭으로 다시 그린다
    });
    ctx.observer.observe(shell, { attributes: true, attributeFilter: ['data-settlement-active-tab'] });
    // 공통 기간이 바뀌면 이미 연 탭만 다시 읽는다. 아직 안 연 탭은 열 때 새 기간으로 읽힌다.
    ctx.rangeObserver = new MutationObserver(function () {
      if (ctx.state.loaded) load(ctx);
    });
    ctx.rangeObserver.observe(shell, { attributes: true, attributeFilter: ['data-settlement-date-range'] });
  }

  /** 추이 칸 폭이 바뀌면 다시 그린다. 루트별 ResizeObserver 라 루트와 함께 태어나고 죽는다. */
  function watchResize(ctx) {
    if (typeof ResizeObserver !== 'function' || !ctx.els.trend) return;
    var lastWidth = 0;
    ctx.resizeObserver = new ResizeObserver(function () {
      var width = ctx.els.trend.clientWidth;
      if (!width || width === lastWidth) return;
      lastWidth = width;
      window.clearTimeout(ctx.resizeTimer);
      ctx.resizeTimer = window.setTimeout(function () {
        if (ctx.root.isConnected && ctx.state.model) P.renderTrend(ctx, ctx.state.model);
      }, RESIZE_DEBOUNCE_MS);
    });
    ctx.resizeObserver.observe(ctx.els.trend);
  }

  /* ═══════════════ 마운트 ═══════════════ */

  var mounts = [];

  function collectEls(root) {
    var q = function (sel) { return root.querySelector(sel); };
    return {
      loading: q('[data-products-loading]'),
      error: q('[data-products-error]'),
      errorDetail: q('[data-products-error-detail]'),
      denied: q('[data-products-denied]'),
      grid: q('[data-products-grid]'),
      empty: q('[data-products-empty]'),
      range: q('[data-products-range]'),
      kpis: q('[data-products-kpis]'),
      families: q('[data-products-families]'),
      channels: q('[data-products-channels]'),
      seriesSub: q('[data-products-series-sub]'),
      seriesLegend: q('[data-products-series-legend]'),
      seriesList: q('[data-products-series]'),
      seriesTable: q('[data-products-series-table]'),
      trend: q('[data-products-trend]'),
      trendSub: q('[data-products-trend-sub]'),
      trendNote: q('[data-products-trend-note]'),
      trScale: q('[data-products-trscale]'),
      coverage: q('[data-products-coverage]'),
      unmapped: q('[data-products-unmapped]'),
      alloc: q('[data-products-alloc]'),
      tt: q('[data-products-tt]'),
    };
  }

  function mount(root) {
    if (!root || root.dataset.settlementProductsMounted === '1') return;
    root.dataset.settlementProductsMounted = '1';
    var ctx = {
      root: root,
      els: collectEls(root),
      observer: null,
      rangeObserver: null,
      resizeObserver: null,
      resizeTimer: null,
      state: {
        sort: 'expected', chM: 'actual', seM: 'actual', trM: 'both', trFree: false,
        open: {}, model: null, seq: 0, loaded: false,
      },
    };
    mounts.push(ctx);
    bindControls(ctx);
    watchShell(ctx);
    watchResize(ctx);
  }

  function mountAll() {
    if (!partsReady()) return;
    // 떨어져 나간 루트는 정리한다 — 스왑으로 사라진 화면의 옵저버·타이머를 남기지 않는다.
    mounts = mounts.filter(function (ctx) {
      if (ctx.root.isConnected) return true;
      if (ctx.observer) ctx.observer.disconnect();
      if (ctx.rangeObserver) ctx.rangeObserver.disconnect();
      if (ctx.resizeObserver) ctx.resizeObserver.disconnect();
      window.clearTimeout(ctx.resizeTimer);
      return false;
    });
    document.querySelectorAll(ROOT_SELECTOR).forEach(mount);
  }
  P.mountAll = mountAll;

  // 전역(document) 리스너는 싱글톤 뒤에서 1회만 — 프래그먼트 재실행 때 중복 누적 금지(perf G4).
  // 리스너는 P.mountAll 을 늦게 읽는다 — 재실행으로 바뀐 최신 함수를 부른다.
  if (!window.__FOMS_SETTLEMENT_PRODUCTS_BOUND) {
    window.__FOMS_SETTLEMENT_PRODUCTS_BOUND = true;
    var onSwap = function () { if (typeof P.mountAll === 'function') P.mountAll(); };
    document.addEventListener('foms:main-content-swapped', onSwap);
    document.addEventListener('foms:erp-shell-fragment-swapped', onSwap);
    document.addEventListener('DOMContentLoaded', onSwap);
  }

  // defer 로 실린 첫 로드와, 셸이 <script src> 를 재실행하는 스왑 경로를 **둘 다** 덮는다.
  mountAll();
})();

/**
 * 정산 대시보드 · 탭 "영업 수수료" — 진입점(마운트 · 조회 · 위 줄 조작) (FCOMM-01 §2.1 · 플랜 T6).
 *
 * 회계팀 흐름(설계서 §2.1): 프리랜서와 달(기본 지난달 — 서버 `default_month`)을 고르면 엑셀과 같은 순서의
 * 표가 뜨고, 시공비 칸에 바로 넣는다. 기준 전환 "실측일" 은 앞으로 들어올 돈을 미리 보는 읽기 전용 표다.
 *
 * - 첫 조회는 **탭이 열릴 때**다. 셸은 탭 전환 이벤트를 쏘지 않으므로 CSS 가 이미 쓰는 루트 속성
 *   `data-settlement-active-tab` 을 관찰한다(channel.js 와 같은 방식 — 새 신호를 만들지 않는다).
 * - 셸의 기간 바(`data-settlement-date-range`)는 따르지 않는다 — 수수료는 달 하나 단위라 위 줄의 달 칸이
 *   그 일을 하고, 이 탭에서는 기간 바를 CSS 로 감춘다.
 * - 리스너는 전부 이 탭 루트 안 위임이다. 전역 리스너는 스왑 재마운트용 3개를 싱글톤 뒤에서 한 번만 단다.
 */
(function () {
  'use strict';

  var C = window.FomsSettleCommission = window.FomsSettleCommission || {};

  var ROOT_SELECTOR = '[data-foms-settlement-commission]';
  var COMMISSION_TAB = 'commission';
  var NO_FREELANCER = '켜진 프리랜서가 없어요. 오른쪽 위 "요율 · 시작 달 설정"에서 먼저 추가해 주세요.';
  var EMPTY_TEXT = {
    completion: '이 달까지 시공 완료된 주문이 없어요.',
    measurement: '이 달에 실측한 주문이 없어요.',
  };

  var mounts = C.mounts = C.mounts || [];

  /** 조각 4개가 다 실렸는지 — 스왑 재실행 순서가 흔들려도 덜 실린 채 마운트하지 않는다. */
  function partsReady() { return !!(C.core && C.table && C.edit && C.deduct); }

  function collectEls(root) {
    var q = function (sel) { return root.querySelector(sel); };
    return {
      user: q('[data-settlement-cm-user]'),
      month: q('[data-settlement-cm-month]'),
      basis: Array.prototype.slice.call(root.querySelectorAll('[data-settlement-cm-basis]')),
      forecastNote: q('[data-settlement-cm-forecast-note]'),
      dateHead: q('[data-settlement-cm-date-head]'),
      near: q('[data-settlement-cm-near]'),
      nearText: q('[data-settlement-cm-near-text]'),
      nearList: q('[data-settlement-cm-near-list]'),
      msg: q('[data-settlement-cm-msg]'),
      loading: q('[data-settlement-cm-loading]'),
      empty: q('[data-settlement-cm-empty]'),
      gridwrap: q('[data-settlement-cm-gridwrap]'),
      total: q('[data-settlement-cm-total]'),
      rows: q('[data-settlement-cm-rows]'),
      dialog: q('[data-settlement-cm-dialog]'),
    };
  }

  /** 상태 3종 — 불러오는 중 · 빈/실패 안내 · 표. 셋 중 하나만 보인다. */
  function showState(ctx, kind, text) {
    C.hide(ctx.els.loading, kind !== 'loading');
    C.hide(ctx.els.empty, kind !== 'empty');
    C.hide(ctx.els.gridwrap, kind !== 'table');
    if (kind === 'empty') ctx.els.empty.textContent = text || '';
  }

  function syncControls(ctx) {
    var s = ctx.state;
    ctx.els.basis.forEach(function (btn) {
      btn.setAttribute('aria-pressed', String(btn.getAttribute('data-settlement-cm-basis') === s.basis));
    });
    C.hide(ctx.els.forecastNote, s.basis !== 'measurement');
    if (ctx.els.dateHead) ctx.els.dateHead.textContent = s.basis === 'measurement' ? '실측일' : '시공일';
    if (ctx.els.month && s.month) ctx.els.month.value = s.month;
    if (ctx.els.user && s.userId) ctx.els.user.value = String(s.userId);
  }

  function fillFreelancers(ctx) {
    var select = ctx.els.user;
    select.textContent = '';
    ctx.state.freelancers.forEach(function (f) {
      var opt = C.el('option', '', f.match_name);
      opt.value = String(f.user_id);
      select.appendChild(opt);
    });
  }

  /** 표 조회 — 늦게 온 옛 응답은 버린다(seq). 다시 읽을 때는 표를 감추지 않는다(깜빡임 없음). */
  C.load = async function (ctx) {
    var s = ctx.state;
    if (!s.userId || !C.monthOk(s.month)) return;
    var seq = ++s.seq;
    if (!s.rows.length) showState(ctx, 'loading');
    var query = new URLSearchParams({ user_id: String(s.userId), month: s.month, basis: s.basis });
    try {
      var body = await C.request('GET', ctx.urls.rows + '?' + query.toString());
      if (seq !== s.seq) return;
      var data = body.data || {};
      s.rows = Array.isArray(data.rows) ? data.rows : [];
      Object.keys(ctx.queue).forEach(function (key) { if (!ctx.queue[key].pending) delete ctx.queue[key]; });
      C.renderNear(ctx, data.near_misses);
      if (!s.rows.length) {
        ctx.els.rows.textContent = '';
        showState(ctx, 'empty', EMPTY_TEXT[s.basis]);
        return;
      }
      C.renderRows(ctx);
      showState(ctx, 'table');
    } catch (err) {
      if (seq !== s.seq) return;
      s.rows = [];
      C.renderNear(ctx, []);
      showState(ctx, 'empty', err.message);
    }
  };

  async function start(ctx) {
    showState(ctx, 'loading');
    try {
      var body = await C.request('GET', ctx.urls.freelancers);
      var data = body.data || {};
      ctx.state.freelancers = Array.isArray(data.freelancers) ? data.freelancers : [];
      if (!ctx.state.month) ctx.state.month = data.default_month || '';
      fillFreelancers(ctx);
      if (!ctx.state.freelancers.length) {
        showState(ctx, 'empty', NO_FREELANCER);
        return;
      }
      ctx.state.userId = String(ctx.state.freelancers[0].user_id);
      syncControls(ctx);
      C.load(ctx);
    } catch (err) {
      ctx.state.loaded = false;   // 다음에 탭을 열 때 다시 시도한다
      showState(ctx, 'empty', err.message);
    }
  }

  function ensureLoaded(ctx) {
    if (ctx.state.loaded) return;
    ctx.state.loaded = true;
    start(ctx);
  }

  function reload(ctx) {
    ctx.state.rows = [];
    C.notice(ctx, '', false);
    syncControls(ctx);
    C.load(ctx);
  }

  function bindControls(ctx) {
    var els = ctx.els;
    els.user.addEventListener('change', function () {
      ctx.state.userId = els.user.value;
      reload(ctx);
    });
    els.month.addEventListener('change', function () {
      if (!C.monthOk(els.month.value)) return;
      ctx.state.month = els.month.value;
      reload(ctx);
    });
    ctx.root.addEventListener('click', function (e) {
      var btn = e.target.closest && e.target.closest('[data-settlement-cm-basis]');
      if (!btn || !ctx.root.contains(btn)) return;
      var basis = btn.getAttribute('data-settlement-cm-basis');
      if (basis === ctx.state.basis) return;
      ctx.state.basis = basis;
      reload(ctx);
    });
    C.bindEdit(ctx);
    C.bindDeduct(ctx);
  }

  function watchTabActivation(ctx) {
    var shell = ctx.root.closest('[data-settlement-active-tab]');
    if (!shell || typeof MutationObserver !== 'function') {
      ensureLoaded(ctx);
      return;
    }
    if (shell.getAttribute('data-settlement-active-tab') === COMMISSION_TAB) ensureLoaded(ctx);
    ctx.observer = new MutationObserver(function () {
      if (shell.getAttribute('data-settlement-active-tab') === COMMISSION_TAB) ensureLoaded(ctx);
    });
    ctx.observer.observe(shell, { attributes: true, attributeFilter: ['data-settlement-active-tab'] });
  }

  function mount(root) {
    if (!root || root.dataset.settlementCmMounted === '1') return;
    root.dataset.settlementCmMounted = '1';
    var ctx = {
      root: root,
      els: collectEls(root),
      urls: {
        freelancers: root.getAttribute('data-settlement-cm-freelancers-api'),
        rows: root.getAttribute('data-settlement-cm-rows-api'),
        input: root.getAttribute('data-settlement-cm-input-api'),
        order: root.getAttribute('data-settlement-cm-order-api'),
      },
      observer: null,
      queue: {},
      state: {
        freelancers: [], userId: null, month: '', basis: 'completion', rows: [], seq: 0,
        loaded: false, dedOrderId: null, dedBusy: false,
      },
    };
    if (!ctx.els.user || !ctx.els.month || !ctx.els.rows) return;
    mounts.push(ctx);
    bindControls(ctx);
    syncControls(ctx);
    watchTabActivation(ctx);
  }

  function mountAll() {
    if (!partsReady()) return;
    // 떨어져 나간 루트는 정리한다 — 스왑으로 사라진 화면의 옵저버를 남기지 않는다.
    for (var i = mounts.length - 1; i >= 0; i -= 1) {
      if (mounts[i].root.isConnected) continue;
      if (mounts[i].observer) mounts[i].observer.disconnect();
      mounts.splice(i, 1);
    }
    document.querySelectorAll(ROOT_SELECTOR).forEach(mount);
  }
  C.mountAll = mountAll;

  // 전역(document) 리스너는 싱글톤 뒤에서 1회만 — 프래그먼트 재실행 때 중복 누적 금지(perf G4).
  if (!window.__FOMS_SETTLEMENT_COMMISSION_BOUND) {
    window.__FOMS_SETTLEMENT_COMMISSION_BOUND = true;
    var onSwap = function () { if (typeof C.mountAll === 'function') C.mountAll(); };
    document.addEventListener('foms:main-content-swapped', onSwap);
    document.addEventListener('foms:erp-shell-fragment-swapped', onSwap);
    document.addEventListener('DOMContentLoaded', onSwap);
  }

  // defer 로 실린 첫 로드와, 셸이 <script src> 를 재실행하는 스왑 경로를 **둘 다** 덮는다.
  mountAll();
})();

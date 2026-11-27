/* 생산 파트 도면 카드 — 내 쓰기 뒤 위 탭 숫자 · 다른 탭 사본을 바로 맞춘다(사장님 2026-11-27 "작업 시작하면 내 공정에 바로바로 반영").
 * 늦던 까닭 둘: (1) 위 탭 '남은 공정 N' · '바뀐 것 N'은 서버가 화면을 그릴 때만 적는다 — 카드 쓰기 응답 · 30초 받아 오기는 카드와
 *   판 칸 숫자(data-pp-count)만 고쳐, 화면을 다시 받을 때까지 옛 숫자였다. (2) 셸이 받아 둔 탭 사본(erp-shell.js 생산 첫 화면 60초 캐시)을
 *   그대로 끼워, 1분 안에 갔던 '남은 공정' 탭을 다시 누르면 쓰기 전 줄이 나왔다.
 * 그래서: 카드가 바뀌면(내 쓰기 · 받아 오기, foms:part-card-updated) 또는 내 쓰기가 성공하면(foms:prod-parts-written — parts.js) 위 탭
 *   주소 · 지금 주소의 셸 사본을 버린다(요청 0 — 다음 누름이 새로 받는다). 주문 칸이 바뀐 내 쓰기(첫 카드 = 제작 시작 · 시작 취소로
 *   그 제작 시작이 되돌려짐(run_cancelled, 11-27 — 제작 대기로) · 공정 칸이 켜지고 꺼짐 · 제작 완료)만 숫자 받기 한 번(GET ?view=counts — 화면 그리기 없이 숫자만, 쓰기 길에는 쿼리를 더하지 않는다).
 * 셸 조각 교체로 다시 실행된다 — 문서 리스너는 한 번(.freshOnce), 지금 화면 함수(.freshApi)를 부른다. */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  if (!root) { return; }
  var bound = window.__FOMS_PROD_PARTS_BOUND = window.__FOMS_PROD_PARTS_BOUND || {};
  if (bound.fresh === root) { return; }
  bound.fresh = root;

  var COUNTS_URL = '/erp/production/home?view=counts';
  var ORDER_ACTIONS = ['complete', 'factory']; // 제작 완료 · 공장 제작 완료 — 주문 단계가 바뀐다
  function toArr(list) { return [].slice.call(list || []); }
  function tabs() { return toArr(root.querySelectorAll('.foms-prod-home__navtab[href]')); }
  function tabOf(a) {
    try { return new URL(a.href, window.location.origin).searchParams.get('tab') || 'date'; } catch (e) { return ''; }
  }

  // 위 탭 주소 · 지금 주소의 셸 사본을 버린다(셸이 없으면 아무것도 안 함 — 온전한 문서는 누르면 새로 받는다)
  function forget() {
    var shell = window.FOMS_ERP_SHELL;
    if (!shell || typeof shell.invalidateFragmentCache !== 'function') { return; }
    shell.invalidateFragmentCache(window.location.href);
    tabs().forEach(function (a) { shell.invalidateFragmentCache(a.href); });
  }
  function some(v) { return Array.isArray(v) ? v.length > 0 : !!v; }
  // 주문 칸이 바뀐 쓰기인가 — 첫 카드 제작 시작(run_started) · 그 시작 되돌림(run_cancelled) · 공정 칸 켜짐/꺼짐(order_step · order_steps) · 제작 완료
  function orderLevel(action, data) {
    if (ORDER_ACTIONS.indexOf(action) >= 0) { return true; }
    return some(data.run_started) || some(data.run_cancelled) || some(data.order_step) || some(data.order_steps);
  }
  function setCount(tab, n, hot) {
    tabs().forEach(function (a) {
      var small = tabOf(a) === tab ? a.querySelector('small') : null;
      if (!small || typeof n !== 'number') { return; }
      small.textContent = String(n);
      if (hot) { small.classList.toggle('is-hot', n > 0); } // '바뀐 것'만 숫자가 있으면 빨간 점(home_body.html 과 같은 규칙)
    });
  }
  function recount() {
    try {
      fetch(COUNTS_URL, { method: 'GET', credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } })
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (body) {
          var c = body && body.success === true && body.data ? body.data.counts : null;
          if (!c || !document.contains(root)) { return; }
          setCount('steps', c.making, false);
          setCount('changes', c.changed, true);
        })
        .catch(function () { /* 못 받으면 숫자는 그대로 — 다음에 화면을 받으면 맞는다 */ });
    } catch (e) { /* fetch 가 없으면 그대로 */ }
  }

  bound.freshApi = {
    updated: function () { if (document.contains(root)) { forget(); } },
    written: function (detail) {
      if (!document.contains(root)) { return; }
      forget();
      // '남은 공정' 탭이 없는 화면(파트 계정 — D50)은 바뀔 숫자가 없어 받지 않는다('바뀐 것'은 카드 쓰기로 안 바뀐다)
      var steps = tabs().some(function (a) { return tabOf(a) === 'steps'; });
      if (steps && orderLevel(detail.action || '', detail.data || {})) { recount(); }
    },
  };
  if (!bound.freshOnce) {
    bound.freshOnce = true;
    document.addEventListener('foms:part-card-updated', function () { bound.freshApi.updated(); });
    document.addEventListener('foms:prod-parts-written', function (e) { bound.freshApi.written((e && e.detail) || {}); });
  }
})();

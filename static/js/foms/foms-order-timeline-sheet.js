/**
 * 주문 진행 360° 타임라인 바텀시트 (모바일 v2).
 *
 * foms-tl-trigger(큐 카드 버튼) 탭 → Bootstrap Offcanvas 바텀시트 오픈 →
 * GET /api/foms/fragment/order/<id>/timeline fragment 를 [data-foms-tl-sheet-body]
 * 에 read-only 로 주입한다. erp_mobile_notification_panel + mobile-notification.js 의
 * capture 위임 패턴을 모방하되, 알림 시트의 write/badge 로직은 없다(read-only fetch 뿐).
 *
 * foms_app_shell.html(fragment-replay entry)에서 defer 로드 — 모든 listener 는
 * document 위임 + window.__FOMS_TL_SHEET_BOUND 싱글톤(perf 가드 G4)으로 셸 fragment
 * swap 간 중복 바인딩을 차단한다.
 */
(function () {
  'use strict';
  if (window.__FOMS_TL_SHEET_BOUND) return;
  window.__FOMS_TL_SHEET_BOUND = true;

  var SHEET_ID = 'foms-order-timeline-sheet';
  // 동일 시트로의 중복 fetch 를 막는 module 스코프 로딩 플래그.
  var loading = false;

  function hasOffcanvas() {
    return !!(window.bootstrap && window.bootstrap.Offcanvas);
  }

  function loadingHtml() {
    return '<div class="foms-tl-sheet__loading" data-foms-tl-sheet-loading>불러오는 중...</div>';
  }

  function openSheet(id) {
    if (!hasOffcanvas()) return;
    var sheet = document.getElementById(SHEET_ID);
    if (!sheet) return;
    window.bootstrap.Offcanvas.getOrCreateInstance(sheet).show();
    loadTimeline(id);
  }

  function loadTimeline(id) {
    var body = document.querySelector('[data-foms-tl-sheet-body]');
    if (!body) return;
    if (loading) return;
    loading = true;
    body.innerHTML = loadingHtml();

    fetch('/api/foms/fragment/order/' + encodeURIComponent(id) + '/timeline', {
      headers: { 'Accept': 'text/html' },
      credentials: 'same-origin'
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.text();
      })
      .then(function (html) {
        body.innerHTML = html;
      })
      .catch(function (err) {
        console.error('order timeline load error:', err);
        body.innerHTML = '<div class="foms-tl-sheet__error">'
          + '<i class="fas fa-exclamation-circle" aria-hidden="true"></i> 타임라인을 불러오지 못했습니다.</div>';
      })
      .finally(function () { loading = false; });
  }

  // ---- 트리거(큐 카드 버튼) — capture 위임 -----------------------------------
  // 카드 네비/erp-shell 의 capture nav listener 보다 먼저 가로채 시트만 연다
  // (mobile-notification.js 의 capture 위임 패턴과 동일).
  document.addEventListener('click', function (e) {
    if (!e.target || !e.target.closest) return;
    var trigger = e.target.closest('[data-foms-tl-open]');
    if (!trigger) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    var id = trigger.getAttribute('data-foms-tl-open');
    if (id == null || id === '') return;
    openSheet(id);
  }, true);

  // ---- 주입된 fragment(persona_order360) 아코디언 토글 — 일반 bubble --------
  // v2 셸엔 foms-mobile-v3.js 가 없어 data-tl-toggle 가 죽으므로 여기서 위임한다.
  // 시트 내부 토글은 nav 가 아니므로 stopImmediatePropagation 은 하지 않는다.
  document.addEventListener('click', function (e) {
    if (!e.target || !e.target.closest) return;
    var toggle = e.target.closest('[data-tl-toggle]');
    if (!toggle) return;
    e.preventDefault();
    var card = toggle.closest('.fos-tl-card');
    if (card) card.classList.toggle('is-open');
  });
})();

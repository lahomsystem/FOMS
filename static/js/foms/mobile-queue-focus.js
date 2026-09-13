/**
 * Scroll/highlight queue cards when landing with ?focus_order= (search, briefing).
 */
(function () {
  'use strict';

  if (window.__FOMS_MOBILE_QUEUE_FOCUS_BOUND) return;
  window.__FOMS_MOBILE_QUEUE_FOCUS_BOUND = true;

  function focusQueueOrderCard() {
    var params = new URLSearchParams(window.location.search || '');
    var focusOrder = (params.get('focus_order') || '').trim();
    if (!focusOrder) {
      return;
    }

    var selectors = [
      '.foms-queue-card-v2[data-order-id="' + focusOrder + '"]',
      '.queue-card[data-order-id="' + focusOrder + '"]',
      '.foms-drawing-queue-card[data-order-id="' + focusOrder + '"]',
      '.erp-drawing-mobile-card[data-order-id="' + focusOrder + '"]',
      '.erp-measurement-mobile-card[data-measurement-mobile-order-id="' + focusOrder + '"]',
      '.erp-history-mobile-card[data-order-id="' + focusOrder + '"]',
      '.erp-pro-order-card[data-order-id="' + focusOrder + '"]',
      'tr[data-order-id="' + focusOrder + '"]',
      '.erp-main-row[data-order-id="' + focusOrder + '"]',
    ];

    // 선택자 우선순위는 그대로 두고(모바일에서는 큐 카드가 1순위가 맞다),
    // 보이는 후보를 우선 채택한다. 데스크톱 응답에도 모바일 큐 카드가 항상 렌더되지만
    // 광폭(>=992)에서는 display:none 이라(foms-mobile-v2-surfaces-hide.css:23-31)
    // 그 카드를 집으면 scrollIntoView 가 무동작이 되고 데스크톱 표 행 강조가 사라진다.
    // 가시 필터는 순위를 뒤집지 않고 비가시 후보만 건너뛴다.
    var card = null;
    var fallback = null;
    for (var i = 0; i < selectors.length; i += 1) {
      var candidate = document.querySelector(selectors[i]);
      if (!candidate) {
        continue;
      }
      if (!fallback) {
        fallback = candidate;
      }
      // offsetParent === null 은 display:none(조상 포함) 판정. 이 후보들은
      // position:fixed 가 아니라(CSS 전수 확인) fixed 예외에 걸리지 않는다.
      if (candidate.offsetParent !== null) {
        card = candidate;
        break;
      }
    }
    if (!card) {
      card = fallback;
    }
    if (!card) {
      return;
    }

    window.requestAnimationFrame(function () {
      card.scrollIntoView({ behavior: 'smooth', block: 'center' });
      card.classList.add('is-focused', 'table-info');
      window.setTimeout(function () {
        card.classList.remove('is-focused', 'table-info');
      }, 2600);
    });
  }

  function init() {
    window.setTimeout(focusQueueOrderCard, 320);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  document.addEventListener('foms:main-content-swapped', init);
})();

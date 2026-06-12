/**
 * Scroll/highlight queue cards when landing with ?focus_order= (search, briefing).
 */
(function () {
  'use strict';

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

    var card = null;
    for (var i = 0; i < selectors.length; i += 1) {
      card = document.querySelector(selectors[i]);
      if (card) {
        break;
      }
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

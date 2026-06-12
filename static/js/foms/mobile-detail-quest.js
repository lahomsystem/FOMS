/**
 * Mobile order detail — deep-link scroll to quest approval section.
 */
(function () {
  'use strict';

  function scrollToQuestAnchor() {
    if (window.location.hash !== '#foms-detail-quest') {
      return;
    }
    var el = document.getElementById('foms-detail-quest');
    if (!el) {
      return;
    }
    try {
      el.focus({ preventScroll: true });
    } catch (e) {
      /* focus optional */
    }
    el.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scrollToQuestAnchor);
  } else {
    scrollToQuestAnchor();
  }
})();

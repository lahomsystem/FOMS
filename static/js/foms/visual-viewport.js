/**
 * P0-06: Expose keyboard overlap height for sticky footers (Visual Viewport API).
 */
(function () {
  'use strict';

  var root = document.documentElement;
  var vv = window.visualViewport;

  function syncKeyboardInset() {
    if (!vv) {
      root.style.setProperty('--foms-keyboard-h', '0px');
      return;
    }
    var offset = Math.max(0, Math.round(window.innerHeight - vv.height - vv.offsetTop));
    root.style.setProperty('--foms-keyboard-h', offset + 'px');
  }

  if (!vv) {
    return;
  }

  vv.addEventListener('resize', syncKeyboardInset);
  vv.addEventListener('scroll', syncKeyboardInset);
  window.addEventListener('resize', syncKeyboardInset);
  syncKeyboardInset();
})();

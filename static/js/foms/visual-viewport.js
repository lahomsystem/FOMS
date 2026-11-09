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
    // 화면 크기 배율이 붙으면 innerHeight · vv 는 보이는 px, CSS 변수는 배율 전 px 다.
    var uz = window.fomsUiZoom ? window.fomsUiZoom() : 1;
    root.style.setProperty('--foms-keyboard-h', Math.round(offset / uz) + 'px');
  }

  if (!vv) {
    return;
  }

  vv.addEventListener('resize', syncKeyboardInset);
  vv.addEventListener('scroll', syncKeyboardInset);
  window.addEventListener('resize', syncKeyboardInset);
  syncKeyboardInset();
})();

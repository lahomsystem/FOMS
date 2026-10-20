/* PARTNER-FOMS 4-1: 협력사 휴대폰 틀 — 아래 시트 여닫기(우리 foms-reason-sheet 모양).
   [data-pp-sheet-open="시트 id"] 로 열고 [data-pp-sheet-close] · 바깥 · Esc 로 닫는다.
   우리 메뉴 서랍(Bootstrap offcanvas)은 Bootstrap JS 를 싣지 않는 협력사 화면에서 쓰지 않는다.
   설계서 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §16 */
(function () {
  'use strict';

  var opener = null;

  function open(sheet, trigger) {
    opener = trigger || null;
    sheet.hidden = false;
    document.body.classList.add('pp-sheet-open');
    var focusable = sheet.querySelector('button, a, input, textarea');
    if (focusable) focusable.focus();
  }

  function close(sheet) {
    sheet.hidden = true;
    document.body.classList.remove('pp-sheet-open');
    if (opener) opener.focus();
    opener = null;
  }

  document.addEventListener('click', function (ev) {
    var trigger = ev.target.closest('[data-pp-sheet-open]');
    if (trigger) {
      var sheet = document.getElementById(trigger.getAttribute('data-pp-sheet-open'));
      if (sheet) open(sheet, trigger);
      return;
    }
    var closer = ev.target.closest('[data-pp-sheet-close]');
    if (closer) close(closer.closest('[data-pp-sheet]'));
  });

  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Escape') return;
    var sheet = document.querySelector('[data-pp-sheet]:not([hidden])');
    if (sheet) close(sheet);
  });

  window.PartnerShell = { open: open, close: close };
})();

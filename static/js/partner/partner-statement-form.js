/**
 * 거래명세서 양식(templates/partner_statement/form.html) — "인쇄 · PDF 저장" 단추만. 설계서 2026-11-03-partner-statement §5.6 · §5.8.
 */
(function () {
  'use strict';
  document.addEventListener('click', function (ev) {
    if (ev.target.closest && ev.target.closest('[data-psf-print]')) window.print();
  });
})();

/**
 * 도면 마법사 — V1(예전 화면) · V2(칸 자동 배치 화면) 고르기. 이 브라우저에 기억한다(쿠키 dws_ui, 1년).
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §6
 * - 단추 data-dws-ui-switch="v2"|"v1" 를 누르면 고치던 것을 자동 저장(PUT, 전달 대기함에는 넣지 않음)한 뒤
 *   쿠키를 바꾸고 같은 주문을 다시 연다(주소의 ?ui= 는 뗀다 — 다음부터 쿠키로 연다).
 * - 저장을 못 했으면 묻는다(저장 안 된 내용은 이 브라우저 비상 백업에 남는다 — 다시 열면 복원 띠).
 * - 계정마다 기억하려면 DB 칸이 필요하다 — 이번에는 브라우저마다.
 *
 * window.FomsWizardUiSwitch = { go(ui), current() }
 */
(function () {
  'use strict';
  if (window.FomsWizardUiSwitch) { return; }

  var COOKIE = 'dws_ui', MAX_AGE = 60 * 60 * 24 * 365, PATH = '/erp/drawing-workbench';

  function current() {
    var root = document.getElementById('dws-root');
    return (root && root.getAttribute('data-ui')) === 'v2' ? 'v2' : 'v1';
  }

  function remember(ui) {
    document.cookie = COOKIE + '=' + ui + '; Max-Age=' + MAX_AGE + '; Path=' + PATH + '; SameSite=Lax';
  }

  function go(ui) {
    if ((ui !== 'v1' && ui !== 'v2') || ui === current()) { return; }
    var core = window.FomsWizardCore, wait = Promise.resolve(true);
    if (core && core.canSave() && core.hydrated() && core.isDirty()) {
      wait = core.save({ auto: true }).then(function (ok) { return ok !== false; }, function () { return false; });
    }
    wait.then(function (ok) {
      if (!ok && core && core.isDirty() &&
        !window.confirm('고친 내용을 아직 저장하지 못했어요. 그래도 화면을 바꿀까요?\n(저장 안 된 내용은 이 브라우저에 남아서 다시 열면 복원할 수 있어요)')) {
        return;
      }
      remember(ui);
      window.location.replace(window.location.pathname);
    });
  }

  function init() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-dws-ui-switch]'), function (btn) {
      btn.addEventListener('click', function () { go(btn.getAttribute('data-dws-ui-switch')); });
    });
  }

  window.FomsWizardUiSwitch = { go: go, current: current };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();

/**
 * 도면 마법사 — 장의 공장(설계서 docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md §8-5 첫 두 줄).
 *
 * 마법사 엔진(window.FomsWizardCore)에 붙어 화면만 돕는다(wizard-as.js 꼴). 값은 페이지 설정 factory 에서 읽는다
 * (서버가 그린 값 — 불러오기 요청을 더하지 않는다). 지키는 일은 서버가 한다.
 *
 * - 탭: 2공장 시트만 이름 앞에 "2공장" 표시(1공장은 표시 없음 = 지금 모습). 누구에게나.
 * - 탭 줄 바로 아래 시트 도구 줄: "공장 지정 [1공장 | 2공장]" + "고르면 바로 저장돼요. [저장]을 안 눌러도 돼요." — 도면팀 누구나 · 관리자만.
 *   고르면 지금 시트를 API 로 바로 저장한다. 생산에 내려간 시트는 확인 창을 먼저, 막히면 서버 글 그대로 창에.
 * - 서버가 모르는 새 시트(자동 저장 전)는 한 번 자동 저장한 뒤 다시 보낸다.
 */
(function () {
  'use strict';
  if (window.__DWS_FACTORY_BOUND) return;
  window.__DWS_FACTORY_BOUND = true;

  var cfg = {};
  try {
    cfg = JSON.parse((document.getElementById('drawing-wizard-config') || {}).textContent || '{}');
  } catch (e) { cfg = {}; }
  var fac = cfg && cfg.factory;
  if (!fac) return;
  var bySheet = fac.by_sheet || {};
  var confirmIds = {};
  (fac.confirm_sheet_ids || []).forEach(function (id) { confirmIds[String(id)] = true; });
  var core = null;
  var bar = null;
  var busy = false;

  function SF() { return window.FomsSheetFactory; }
  function factoryOf(sheet) { return sheet && Number(bySheet[String(sheet.id)]) === 2 ? 2 : 1; }

  function decorateTabs() {
    var tabbar = core.tabbar && core.tabbar();
    if (!tabbar) return;
    var sheets = core.state().sheets || [];
    Array.prototype.forEach.call(tabbar.querySelectorAll('.dws-tab'), function (tab, i) {
      var mark = tab.querySelector('.dws-tab-fac');
      var two = factoryOf(sheets[i]) === 2;
      tab.classList.toggle('dws-tab-has-fac', two);
      if (two && !mark) {
        mark = document.createElement('span');
        mark.className = 'dws-tab-fac';
        mark.textContent = '2공장';
        tab.insertBefore(mark, tab.firstChild);
      } else if (!two && mark) {
        mark.parentNode.removeChild(mark);
      }
    });
  }

  function syncBar() {
    if (!bar) return;
    var sheet = core.sheet && core.sheet();
    var now = factoryOf(sheet);
    Array.prototype.forEach.call(bar.querySelectorAll('[data-fac]'), function (btn) {
      btn.setAttribute('aria-pressed', Number(btn.getAttribute('data-fac')) === now ? 'true' : 'false');
      btn.disabled = !sheet || busy;
    });
    bar.setAttribute('aria-busy', busy ? 'true' : 'false');
  }

  function render() { decorateTabs(); syncBar(); }

  function buildBar() {
    var tabrow = document.querySelector('.dws-tabrow');
    if (!fac.can_set || !tabrow) return;
    var row = document.createElement('div');
    row.className = 'dsf-toolrow dws-ui';
    bar = document.createElement('div');
    bar.className = 'dsf-bar';
    var name = document.createElement('span');
    name.className = 'dsf-bar__label';
    name.id = 'dsf-bar-label';
    name.textContent = '공장 지정';
    var group = document.createElement('div');
    group.className = 'dsf-sel';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-labelledby', 'dsf-bar-label');
    [1, 2].forEach(function (f) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'dsf-sel__b is-' + f;
      btn.setAttribute('data-fac', String(f));
      btn.setAttribute('aria-pressed', 'false');
      btn.textContent = f + '공장';
      btn.addEventListener('click', function () { choose(f); });
      group.appendChild(btn);
    });
    var hint = document.createElement('span');
    hint.className = 'dsf-bar__hint';
    hint.textContent = '고르면 바로 저장돼요. [저장]을 안 눌러도 돼요.';
    bar.appendChild(name);
    bar.appendChild(group);
    bar.appendChild(hint);
    row.appendChild(bar);
    // 탭 줄 바로 아래 '시트 도구 줄'(설계서 §8-5 · 목업 3판) — 탭 줄 자리를 빼앗지 않게 따로 둔다(V2 알림 띠 · 시트 10장).
    tabrow.parentNode.insertBefore(row, tabrow.nextSibling);
  }

  function refocus(to) {
    var btn = bar && bar.querySelector('[data-fac="' + to + '"]');
    if (btn && btn.focus) btn.focus();   // 기다리는 동안 단추가 잠겨 초점이 빠졌다 — 누른 단추로 돌려놓는다
  }

  function choose(to) {
    var sheet = core.sheet && core.sheet();
    if (!sheet || busy || !SF() || factoryOf(sheet) === to) return;
    var sid = String(sheet.id);
    var go = function () { send(sid, to, false); };
    if (confirmIds[sid]) {
      SF().confirmMove({ to: to, sub: sheet.name || '', onGo: go, anchor: bar });
    } else {
      go();
    }
  }

  function setBusy(on) { busy = on; syncBar(); }

  function send(sid, to, retried) {
    setBusy(true);
    SF().post(core.orderId, [{ sheet_id: sid, factory: to }]).then(function (res) {
      if (res.ok) {
        setBusy(false);
        bySheet = res.data.factory_by_sheet || {};
        render();
        refocus(to);
        core.toast(SF().label(to) + '으로 지정했어요.');
        return;
      }
      // 아직 자동 저장 전인 새 시트 — 서버가 모르는 시트라 한 번 자동 저장한 뒤 다시 보낸다.
      if (!retried && res.code === 'DRAWING_NOT_CURRENT' && String(res.data.sheet_id || '') === sid && core.save) {
        return core.save({ auto: true }).then(function (saved) {
          if (saved) { send(sid, to, true); return; }
          setBusy(false);
          refocus(to);
          SF().showBlocked({ to: to, message: res.message, anchor: bar });
        });
      }
      setBusy(false);
      render();
      refocus(to);
      SF().showBlocked({ to: to, message: res.message, anchor: bar });
    });
  }

  function init() {
    core = window.FomsWizardCore;
    if (!core || typeof core.on !== 'function') return;
    buildBar();
    core.on('sheet', render);
    core.on('loaded', render);
    if (core.hydrated && core.hydrated()) render();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();

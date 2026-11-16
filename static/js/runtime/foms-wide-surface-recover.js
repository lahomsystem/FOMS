/* 넓은 창 표면 되돌리기 — 폰에서 뺀 표면을 창이 넓어지면 다시 받는다(2026-11-16).

   서버는 폰(foms_ptr=coarse + foms_vw=narrow)에 태블릿 가로 화면 · 모바일 셸이 끄는 PC 표면을 빼고
   [data-foms-wide-surface-omitted] 표식만 남긴다(foms/services/feature_flags.py
   wants_wide_viewport_surfaces, 표식 templates/partials/shared/wide_surface_omitted_marker.html —
   이 파일은 그 표식 옆에서만 실린다). 창 폭은 바뀐다 — 폴더블을 펼치거나 화면 분할을 넓히거나 작은
   태블릿을 세로에서 가로로 돌리면 992 이상이 된다. 그때 표식이 남아 있으면 지금 화면을 다시 받는다
   (쿠키는 이미 wide/tall 로 바뀌어 서버가 표면을 다시 그린다).

   static/js/runtime/erp-shell.js 의 recoverOmittedMobileSurface(넓은 창 → 좁은 창)와 반대 방향 짝이고
   같은 모양이다: 셸 다시 받기 1회 → 그래도 표식이 남으면 전체 새로고침 1회(sessionStorage 표식, 60초)
   → 그래도 남으면 경고만 남기고 멈춘다(쿠키가 저장되지 않는 환경 등). 셸 API 는 window.FOMS_ERP_SHELL
   로만 쓴다(그 파일은 건드리지 않는다).

   판정 식 = 서버의 narrow 와 같은 식 `(min-width: 992px)`(foms-viewport-hint-boot.js 가 쿠키를 쓰는 식).
   한 번만 묶는다(셸 스왑으로 다시 실행돼도 리스너가 쌓이지 않게 — 퍼포먼스 가드 G4). */
(function () {
  'use strict';
  if (window.__FOMS_WIDE_SURFACE_RECOVER_BOUND) return;
  window.__FOMS_WIDE_SURFACE_RECOVER_BOUND = true;
  if (!window.matchMedia) return;

  var WIDE_MQ = '(min-width: 992px)';
  var OMITTED_SELECTOR = '[data-foms-wide-surface-omitted]';
  var RELOAD_GUARD_KEY = 'foms_wide_surface_reload';
  var RELOAD_GUARD_MS = 60 * 1000;
  var wideMql = window.matchMedia(WIDE_MQ);
  /** 셸 다시 받기를 이미 한 주소(캐시 키). 표면이 돌아오면 비운다. */
  var refetchKey = null;
  /** 셸 다시 받기를 보내고 스왑을 기다리는 중 — 그 사이 다른 호출이 새로고침으로 넘어가지 않게. */
  var awaitingSwap = false;
  var storageWarned = false;

  /**
   * 새로고침 되풀이 표식 저장소. 실패하면 undefined(1회 경고) — 호출자는 새로고침을 하지 않는다.
   * @param {'get'|'set'|'remove'} op
   * @param {string} [value]
   */
  function reloadGuard(op, value) {
    try {
      var store = window.sessionStorage;
      if (op === 'get') return store.getItem(RELOAD_GUARD_KEY);
      if (op === 'set') {
        store.setItem(RELOAD_GUARD_KEY, value);
        return value;
      }
      store.removeItem(RELOAD_GUARD_KEY);
      return null;
    } catch (e) {
      if (!storageWarned) {
        storageWarned = true;
        console.warn('[foms-wide-surface-recover] sessionStorage 사용 불가 — 새로고침 되돌림을 하지 않는다:', e);
      }
      return undefined;
    }
  }

  function reloadedRecently(guard, key) {
    if (!guard) return false;
    var cut = guard.lastIndexOf('|');
    return guard.slice(0, cut) === key && Date.now() - Number(guard.slice(cut + 1)) < RELOAD_GUARD_MS;
  }

  function shellApi() {
    var shell = window.FOMS_ERP_SHELL;
    if (!shell || typeof shell.navigateByShell !== 'function' || typeof shell.isShellFragmentSwapUrl !== 'function') {
      return null;
    }
    return shell;
  }

  function recover() {
    if (awaitingSwap) return;
    var shell = shellApi();
    var here = window.location.href;
    var key = shell && typeof shell.getCacheKey === 'function' ? shell.getCacheKey(here) : here;
    if (!wideMql.matches || !document.querySelector(OMITTED_SELECTOR)) {
      // 표면이 필요 없거나 이미 그려져 있다 = 되돌림 불필요·성공 → 되풀이 표식 정리.
      refetchKey = null;
      if (reloadGuard('get')) reloadGuard('remove');
      return;
    }
    // 창 여러 개가 쿠키 하나를 나눠 쓴다 — 다시 받기 직전에 이 창의 폭 구간으로 맞춘다.
    if (typeof window.__fomsViewportHintSync === 'function') {
      window.__fomsViewportHintSync();
    }
    if (shell && refetchKey !== key && shell.isShellFragmentSwapUrl(here) && document.getElementById('main-content')) {
      refetchKey = key;
      awaitingSwap = true;
      if (typeof shell.invalidateFragmentCache === 'function') shell.invalidateFragmentCache(here);
      shell.navigateByShell(here, { bypassCache: true, replaceHistory: true });
      return;
    }
    var guard = reloadGuard('get');
    if (guard === undefined) return;
    if (reloadedRecently(guard, key)) {
      console.warn('[foms-wide-surface-recover] 새로고침 뒤에도 넓은 창 표면이 빠져 있다(쿠키 저장 실패?) — 되풀이하지 않는다:', key);
      return;
    }
    if (reloadGuard('set', key + '|' + Date.now()) === undefined) return;
    window.location.reload();
  }

  function onWideChange() {
    awaitingSwap = false;
    if (wideMql.matches) {
      // 좁을 때 받아 둔 warm 캐시에는 넓은 창 표면이 빠져 있다 — 통째로 버린다.
      var shell = shellApi();
      if (shell && typeof shell.invalidateFragmentCache === 'function') shell.invalidateFragmentCache();
    }
    // 부트의 foms_vw 쿠키 갱신(먼저 등록된 리스너)이 끝난 뒤에 돈다.
    window.setTimeout(recover, 0);
  }

  if (wideMql.addEventListener) {
    wideMql.addEventListener('change', onWideChange);
  } else if (wideMql.addListener) {
    wideMql.addListener(onWideChange);
  }
  document.addEventListener('foms:erp-shell-fragment-swapped', function () {
    awaitingSwap = false;
    recover();
  });
  window.addEventListener('pageshow', function (e) {
    if (e && e.persisted) recover();
  });
  // 첫 실행: 전체 문서면 defer 스크립트가 다 돈 뒤(뒤에 실리는 erp-shell.js 가 FOMS_ERP_SHELL 을 내놓은 뒤 —
  // DOMContentLoaded, 이미 지났으면 load), 셸 스왑으로 들어왔으면(문서 complete) 바로. 두 번 불려도 awaitingSwap ·
  // 표식 검사로 한 번만 받는다. 좁은 창 쿠키가 낡았는데 지금 창이 넓을 수 있다(창 여러 개 · 닫힌 동안 펼침).
  if (document.readyState === 'complete') {
    recover();
  } else {
    document.addEventListener('DOMContentLoaded', recover);
    window.addEventListener('load', recover);
  }
})();

/**
 * Tablet-landscape global rail active-state sync (T2, 2026-07-12 목업 v5 정합).
 *
 * The global 72px rail (templates/partials/shared/foms_tablet_rail.html) lives in
 * layout_nav.html — OUTSIDE #main-content — so the ERP shell fast-tab swap
 * (static/js/runtime/erp-shell.js, which replaces only #main-content.innerHTML) never
 * re-renders it. Without this the rail's server-rendered .is-active highlight goes
 * stale after an in-place fragment navigation. This script re-derives the active item
 * from location.pathname on every fragment swap + popstate, applying the SAME
 * longest-segment-prefix rule as the server resolver
 * (foms.services.foms_split_view.resolve_tablet_rail_active_id) — including the
 * calculator item, whose href is /wdcalculator, so no special-case is needed here.
 *
 * Load: layout_nav.html, right after the rail include, deferred (perf guard G1). It is
 * layout-owned (not inside #main-content), so it is evaluated once per full page load,
 * never re-run by the fragment swap; the singleton guard is belt-and-braces (perf
 * guard G4). No inline styles, no jQuery.
 */
(function () {
  'use strict';

  if (window.__FOMS_TABLET_RAIL_NAV_BOUND) {
    return;
  }

  var rail = document.querySelector('.foms-tablet-rail');
  if (!rail) {
    // No rail on this page (non-cohort / non-/erp / non-calculator). The rail is
    // layout-owned and can never appear via a fragment swap, so skip listener
    // registration entirely (no-op).
    return;
  }

  window.__FOMS_TABLET_RAIL_NAV_BOUND = true;

  // 위 메뉴 묶음(점검 2차 w4-02) — 키 낮은 화면 · 화면 크기 110% 이상에서는 이 안에서만 굴린다.
  var menu = rail.querySelector('.foms-tablet-rail__menu');

  /**
   * 강조 칸(.is-active)이 굴림 영역(위 메뉴 묶음) 밖에 숨어 있으면 그 칸이 막 다 보이도록 묶음만 굴린다(점검 3차, 11-15 —
   * 1176×626 · 130% 에서 시공 · 완료 · 이력 화면의 강조 칸이 묶음 아래에 숨었다). 이미 다 보이면 건드리지 않는다 · 부드러운
   * 굴림 없이 · 문서나 레일 전체는 굴리지 않는다. 보이는 크기(rect)는 화면 크기 배율이 곱해진 값이라 배율 전 크기(offsetHeight)
   * 로 나눠 굴림 값으로 바꾼다.
   */
  function revealActive() {
    if (!menu || menu.scrollHeight <= menu.clientHeight) {
      return;
    }
    var item = menu.querySelector('.foms-tablet-rail__item.is-active');
    var box = menu.getBoundingClientRect();
    if (!item || !box.height || !menu.offsetHeight) {
      return;
    }
    var scale = box.height / menu.offsetHeight;
    var at = item.getBoundingClientRect();
    if (at.top < box.top - 0.5 || at.bottom - at.top > box.height) {
      menu.scrollTop = Math.floor(menu.scrollTop + (at.top - box.top) / scale);
    } else if (at.bottom > box.bottom + 0.5) {
      menu.scrollTop = Math.ceil(menu.scrollTop + (at.bottom - box.bottom) / scale);
    }
  }

  /**
   * Strip a single trailing slash while preserving the root "/".
   * @param {string} path
   * @returns {string}
   */
  function normalizePath(path) {
    if (!path) {
      return '';
    }
    return path.length > 1 ? path.replace(/\/+$/, '') : path;
  }

  /**
   * True when `current` equals `base` or extends it on a segment boundary, so
   * "/erp/ashley" does NOT match the "/erp/as" prefix (server parity).
   * @param {string} current
   * @param {string} base
   * @returns {boolean}
   */
  function isSegmentPrefix(current, base) {
    return current === base || current.indexOf(base + '/') === 0;
  }

  /** Re-apply .is-active + aria-current="page" to the rail item matching the path. */
  function syncActive() {
    var current = normalizePath(window.location.pathname);
    var items = rail.querySelectorAll('.foms-tablet-rail__item');
    var best = null;
    var bestLen = -1;
    var i;
    var item;
    var base;
    for (i = 0; i < items.length; i += 1) {
      // Anchor .pathname resolves the href to its absolute path (segment SSOT parity).
      // data-foms-rail-match(생산 칸, D19) = 서버 판정과 같은 접두어 — href 가 첫 화면이어도 보드에서 강조.
      base = normalizePath(items[i].getAttribute('data-foms-rail-match') || items[i].pathname || '');
      if (base && isSegmentPrefix(current, base) && base.length > bestLen) {
        bestLen = base.length;
        best = items[i];
      }
    }
    for (i = 0; i < items.length; i += 1) {
      item = items[i];
      if (item === best) {
        item.classList.add('is-active');
        item.setAttribute('aria-current', 'page');
      } else {
        item.classList.remove('is-active');
        item.removeAttribute('aria-current');
      }
    }
    revealActive();
  }

  document.addEventListener('foms:erp-shell-fragment-swapped', syncActive);
  window.addEventListener('popstate', syncActive);

  // 처음 그릴 때(서버가 강조한 칸) · 묶음 높이가 바뀔 때(회사 지식 칸이 나타남 · 화면 크기 손잡이 · 화면 돌림) 다시 본다.
  revealActive();
  if (menu && window.ResizeObserver) {
    new window.ResizeObserver(revealActive).observe(menu);
  }
})();

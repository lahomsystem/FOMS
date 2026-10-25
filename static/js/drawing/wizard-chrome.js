/**
 * 도면 마법사 — 앱바 '도구 ▾' 묶음 · 떠 있는 막대 자리 · 알림 시간.
 *
 * 2026-10-25 사용성 평가 큼-1·큼-4·보통-6 몫.
 * - 도구 ▾: 좁은 폭(CSS 가 폭을 정한다)에서 [자동 채움]·[자동 배치]·[자재표 계산](더 좁으면 표 글자 단추도)을
 *   메뉴 하나로 묶는다. 메뉴 항목은 원래 단추를 눌러 주기만 해서 단추 id·처리·잠금·시험이 그대로 산다.
 * - 떠 있는 막대(그림 미니 막대·정렬 막대·글 편집 막대): 화면 끝이 아니라 '보이는 캔버스'
 *   (열린 계산 칸·제품 드로어가 덮은 몫을 뺀 칸) 안에만 놓는다. 자리가 모자라면 막대가 두 줄로 접힌다.
 * - 알림: 최소 4초, 긴 글은 글자 수만큼 더 오래(최대 12초). 오류 알림은 지금처럼 닫을 때까지 남는다.
 *   (같은 글 합치기·3개 상한·모달 창 위 띄우기는 wizard-toast.js, 앱바 메뉴 Esc·자리·도구 이름은 wizard-appbar.js)
 *
 * window.FomsWizardChrome = {
 *   initToolsMenu(opts), syncToolsMenu(menu),
 *   toastMs(msg), shrinkBounds(base, covers), placeBar(anchor, bar, bounds, lift),
 *   visibleCanvas(canvas, covers), placeFloating(el, anchor, lift, canvas, covers), watchLayout(fn, canvas, covers)
 * }
 */
(function () {
  'use strict';
  if (window.FomsWizardChrome) { return; }

  var EDGE = 8;          // 막대와 보이는 캔버스 가장자리 사이(px)
  var MIN_BAR_W = 160;   // 막대 폭을 이보다 좁게 접지는 않는다

  /* ---- 알림 시간 ------------------------------------------------------- */

  /** 알림이 떠 있을 시간(ms) — 최소 4초, 25자를 넘으면 한 글자에 0.08초씩 더, 최대 12초. */
  function toastMs(msg) {
    var n = String(msg == null ? '' : msg).length;
    return Math.max(4000, Math.min(12000, 2000 + n * 80));
  }

  /* ---- 떠 있는 막대 자리 ------------------------------------------------ */

  /** 보이는 사각형 — base 에서, 왼쪽 끝을 덮는 것(드로어)과 오른쪽 끝을 덮는 것(계산 칸)만큼 줄인다.
      가운데만 덮는 것은 무시한다. 모든 사각형은 화면 좌표 {left, top, right, bottom}. */
  function shrinkBounds(base, covers) {
    var b = { left: base.left, top: base.top, right: base.right, bottom: base.bottom };
    (covers || []).forEach(function (c) {
      if (!c || c.right - c.left <= 0 || c.bottom - c.top <= 0) { return; }
      if (c.right <= b.left || c.left >= b.right || c.bottom <= b.top || c.top >= b.bottom) { return; }   // 안 겹친다
      if (c.left <= b.left) { b.left = Math.min(b.right, c.right); }          // 왼쪽을 덮는다(제품 드로어)
      else if (c.right >= b.right) { b.right = Math.max(b.left, c.left); }    // 오른쪽을 덮는다(계산 칸)
    });
    return b;
  }

  /** 막대 왼쪽 위 자리. 그림 위(회전 손잡이 여유 lift 만큼 더 위)를 먼저 보고, 모자라면 그림 아래,
      둘 다 모자라면 보이는 칸 안으로 당긴다. 가로는 보이는 칸 왼쪽~오른쪽 안(가장자리 8px)에 둔다.
      anchor {left, top, bottom} · bar {w, h} · bounds {left, top, right, bottom} → {left, top} */
  function placeBar(anchor, bar, bounds, lift) {
    var minL = bounds.left + EDGE, maxL = bounds.right - bar.w - EDGE;
    var left = Math.max(minL, Math.min(anchor.left, maxL));
    var minT = bounds.top + EDGE, maxT = bounds.bottom - bar.h - EDGE;
    var above = anchor.top - bar.h - EDGE - (lift || 0);
    var below = anchor.bottom + EDGE;
    var top;
    if (above >= minT && above <= maxT) { top = above; }
    else if (below >= minT && below <= maxT) { top = below; }
    else { top = Math.max(minT, Math.min(above, maxT)); }
    return { left: Math.round(left), top: Math.round(top) };
  }

  function rectOf(el) {
    if (!el || el.hidden || typeof el.getBoundingClientRect !== 'function') { return null; }
    var r = el.getBoundingClientRect();
    return { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
  }

  /** 캔버스 칸의 그림 보이는 안쪽(스크롤 막대 뺌) 화면 사각형. */
  function innerRectOf(el) {
    var r = rectOf(el);
    if (!r) { return null; }
    var left = r.left + (el.clientLeft || 0), top = r.top + (el.clientTop || 0);
    return { left: left, top: top, right: left + (el.clientWidth || r.right - r.left), bottom: top + (el.clientHeight || r.bottom - r.top) };
  }

  /** 보이는 캔버스(화면 좌표) — 캔버스 칸(스크롤 막대 뺌)을 창 안으로 자르고, 열린 계산 칸·드로어가 덮은 몫을 뺀다. */
  function visibleCanvas(canvas, covers) {
    var vw = window.innerWidth, vh = window.innerHeight;
    var base = innerRectOf(canvas) || { left: 0, top: 0, right: vw, bottom: vh };
    base = { left: Math.max(0, base.left), top: Math.max(0, base.top), right: Math.min(vw, base.right), bottom: Math.min(vh, base.bottom) };
    return shrinkBounds(base, (covers || []).map(rectOf));
  }

  /** 떠 있는 막대 하나를 보이는 캔버스 안에 놓는다. 폭 상한을 먼저 걸어 모자라면 두 줄로 접힌 뒤 크기를 잰다. */
  function placeFloating(el, anchor, lift, canvas, covers) {
    if (!el) { return; }
    var b = visibleCanvas(canvas, covers);
    el.style.maxWidth = Math.max(MIN_BAR_W, Math.floor(b.right - b.left - EDGE * 2)) + 'px';
    el.style.left = Math.round(b.left) + 'px';   // 재기 전에 왼쪽 끝으로 — 화면 오른쪽 끝에 둔 채 재면 폭이 눌린 채로 잰다
    var pos = placeBar(anchor, { w: el.offsetWidth, h: el.offsetHeight }, b, lift);
    el.style.left = pos.left + 'px';
    el.style.top = pos.top + 'px';
  }

  /** 캔버스 크기가 바뀌거나(계산 칸 열고 닫기·제품 목록 접기) 덮는 칸이 열리고 닫히면 fn 을 다시 부른다. */
  function watchLayout(fn, canvas, covers) {
    if (typeof fn !== 'function') { return; }
    if (canvas && window.ResizeObserver) { new window.ResizeObserver(function () { fn(); }).observe(canvas); }
    if (!window.MutationObserver) { return; }
    (covers || []).forEach(function (el) {
      if (el) { new window.MutationObserver(function () { fn(); }).observe(el, { attributes: true, attributeFilter: ['hidden'] }); }
    });
  }

  /* ---- 앱바 '도구 ▾' ------------------------------------------------------ */

  function eachItem(menu, fn) {
    Array.prototype.forEach.call(menu.querySelectorAll('[data-tools-for]'), fn);
  }
  function targetOf(item) { return document.getElementById(item.getAttribute('data-tools-for')); }

  /** 메뉴를 열기 전에 항목을 원래 단추 상태에 맞춘다 — 없거나 숨은 단추의 항목은 숨기고, 잠긴 단추의 항목은 잠그고,
      계산 칸처럼 여닫는 단추는 지금 열렸는지(aria-expanded)를 항목의 aria-pressed 로 옮긴다. */
  function syncToolsMenu(menu) {
    if (!menu) { return; }
    eachItem(menu, function (item) {
      var target = targetOf(item);
      item.hidden = !target || !!target.hidden;
      item.disabled = !!target && (!!target.disabled || target.classList.contains('dws-disabled'));
      var open = target ? target.getAttribute('aria-expanded') : null;
      if (open != null) { item.setAttribute('aria-pressed', open === 'true' ? 'true' : 'false'); }
    });
  }

  /** 앱바 '도구 ▾' 연결. opts: { toggleMenu(menu), closeMenus() } — 마법사의 메뉴 열고 닫기를 그대로 쓴다. */
  function initToolsMenu(opts) {
    var btn = document.getElementById('dws-btn-tools');
    var menu = document.getElementById('dws-tools-menu');
    if (!btn || !menu || !opts || typeof opts.toggleMenu !== 'function') { return false; }
    btn.addEventListener('click', function (e) {
      if (e && e.stopPropagation) { e.stopPropagation(); }   // 다른 앱바 메뉴처럼 — 문서 클릭 닫기와 겹치지 않게
      if (menu.hidden) { syncToolsMenu(menu); }
      opts.toggleMenu(menu);
      btn.setAttribute('aria-expanded', String(!menu.hidden));
    });
    eachItem(menu, function (item) {
      item.addEventListener('click', function () {
        if (typeof opts.closeMenus === 'function') { opts.closeMenus(); }
        btn.setAttribute('aria-expanded', 'false');
        if (typeof btn.focus === 'function') { btn.focus(); }   // 닫힌 메뉴에 초점이 남지 않게(대화 상자를 여는 단추는 그쪽이 초점을 가져간다)
        var target = targetOf(item);
        if (target && !target.disabled) { target.click(); }   // 원래 단추의 처리(잠금·계산 칸 aria-expanded 포함)를 그대로
      });
    });
    if (window.MutationObserver) {   // 바깥 클릭·다른 메뉴로 닫혀도 aria-expanded 를 맞춘다
      new window.MutationObserver(function () { btn.setAttribute('aria-expanded', String(!menu.hidden)); })
        .observe(menu, { attributes: true, attributeFilter: ['hidden'] });
    }
    return true;
  }

  window.FomsWizardChrome = {
    initToolsMenu: initToolsMenu,
    syncToolsMenu: syncToolsMenu,
    toastMs: toastMs,
    shrinkBounds: shrinkBounds,
    placeBar: placeBar,
    visibleCanvas: visibleCanvas,
    placeFloating: placeFloating,
    watchLayout: watchLayout
  };
})();

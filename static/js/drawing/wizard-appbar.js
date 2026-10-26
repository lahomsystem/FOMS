/**
 * 도면 마법사 — 앱바 메뉴 Esc 닫기 · 옆으로 미는 줄의 메뉴 자리 · 도구 이름 맞춤.
 *
 * 2026-10-25 실화면 QA(작음) 몫.
 * - 앱바 메뉴(도구 ▾·프리셋·도형·내보내기, 편집 막대의 프리셋)가 Esc 로 닫히지 않았다(도움말에는 'Esc … 창 닫기').
 *   → 열린 메뉴를 Esc 로 닫고 초점을 그 단추로 돌린다. 같은 Esc 로 그림 선택까지 풀리지는 않는다.
 * - 옆으로 미는 줄(≤1179px)의 메뉴는 앱바 스크롤에 잘리지 않게 fixed 라 CSS 만으로는 화면 오른쪽 끝(right: 8px)에
 *   열렸다(1024 에서 '도구' 단추와 430px 떨어짐). → 열 때 단추 왼쪽에 맞추고, 화면 밖으로 나갈 때만 오른쪽 끝에 붙인다.
 * - 도구 이름(선택·텍스트·도형·펜·지우개·이미지)을 2399px 이하에서 폭 단계로 미리 숨기니 1920 에서도 그림만 남았다.
 *   → 앱바에 실제로 남는 자리를 재서 다 / 자주 쓰는 '선택'·'텍스트'만 / 그림만 중 처음 맞는 것을 고른다(wizard.css
 *   data-seg-names). '그림 종류 알아보는 중' 같은 칩이 생겨 자리가 줄면 다시 잰다.
 *
 * 2026-10-25 마지막 실화면 확인(V1 보통): 진행 칩·저장 칩 글이 바뀔 때마다 가운데 도구 묶음이 옆으로 크게 밀렸다
 * (1920 에서 진행 칩이 뜨면 [자동 채움] 658→490, 첫 편집 780→690, 탭 바꿈 44px).
 * - 상태 칩 자리 폭은 wizard.css 가 늘 잡아 둔다('알아보는 중' 칩은 앱바 아래에 떠서 보인다).
 * - 여기서는 제목 칸 상한을 글 폭으로 정한다(--dws-left-w, fitLeft) — 남는 자리는 제목 칸이 아니라 도구 묶음 뒤에
 *   남아서, 가운데 도구 묶음이 오른쪽 묶음 폭을 따라 움직이지 않는다.
 * - 이름을 다시 펴는 쪽은 여유(HYST)가 있어야 편다 — 경계 폭에서 이름이 폈다 접혔다 하지 않게(되돌림 문턱).
 *
 * window.FomsWizardAppbar = { init(opts), menuLeft(btnLeft, menuW, vw), placeMenu(menu),
 *                             closeMenuByEsc(e, menus, closeMenus), fitSegNames(bar), fitLeft(bar) }
 */
(function () {
  'use strict';
  if (window.FomsWizardAppbar) { return; }

  var EDGE = 8;   // 메뉴와 화면 가장자리 사이(px)
  var BAR_MENUS = ['dws-tools-menu', 'dws-preset-menu', 'dws-shape-menu', 'dws-export-menu'];
  var ESC_MENUS = BAR_MENUS.concat(['dws-mt-preset-menu']);   // Esc 는 편집 막대의 프리셋 메뉴도 닫는다
  var OVER_MENU = 'dialog[open], #dws-help:not([hidden]), #dws-lightbox:not([hidden])';   // 이것이 떠 있으면 Esc 는 그쪽 몫
  var NAME_STEPS = ['all', 'two', 'none'];   // 이름 다 · 자주 쓰는 '선택'·'텍스트'만 · 그림만
  var SUB_KEEP = 72;                         // 고객명은 이만큼(다섯 글자쯤)은 남긴다
  var TITLE_MIN = 76;                        // 제목 칸 최소 폭(wizard.css .dws-appbar-titlewrap min-width)
  var HYST = 16;                             // 이름을 다시 펼 때는 이만큼(px) 더 남아야 편다

  /* ---- 메뉴 자리 -------------------------------------------------------- */

  /** 메뉴를 여는 단추 — 메뉴와 같은 .dws-dropdown 안의 첫 단추. */
  function menuToggle(menu) {
    var box = menu && menu.parentNode;
    return box && typeof box.querySelector === 'function' ? box.querySelector('button') : null;
  }

  /** fixed 메뉴의 왼쪽 자리 — 단추 왼쪽에 맞추고, 화면 밖으로 나갈 때만 오른쪽 끝(8px 안)으로 당긴다. */
  function menuLeft(btnLeft, menuW, vw) {
    return Math.round(Math.max(EDGE, Math.min(btnLeft, vw - menuW - EDGE)));
  }

  /** 열린 메뉴를 그 단추 아래에 놓는다(fixed 일 때만 — 넓은 화면의 absolute 메뉴는 CSS 그대로).
      닫히거나 넓은 화면으로 바뀌면 손댄 자리를 지운다. */
  function placeMenu(menu) {
    if (!menu || !menu.style) { return; }
    menu.style.left = '';
    menu.style.right = '';
    var btn = menuToggle(menu);
    if (menu.hidden || !btn || window.getComputedStyle(menu).position !== 'fixed') { return; }
    menu.style.left = menuLeft(btn.getBoundingClientRect().left, menu.offsetWidth, window.innerWidth) + 'px';
    menu.style.right = 'auto';
  }

  /* ---- Esc ------------------------------------------------------------- */

  function isTyping(el) {
    return !!(el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName || '')));
  }

  /** Esc — 열린 메뉴를 닫고 초점을 그 단추로 돌린다. 마법사의 Esc(그림 선택 풀기)까지 가지 않게 여기서 멈춘다.
      글 편집 중(편집 막대의 프리셋 메뉴)이면 초점은 편집 칸에 그대로 둔다. 메뉴를 닫았으면 true. */
  function closeMenuByEsc(e, menus, closeMenus) {
    if (!e || (e.key !== 'Escape' && e.key !== 'Esc')) { return false; }
    var open = null;
    menus.forEach(function (m) { if (!open && m && !m.hidden) { open = m; } });
    if (!open) { return false; }
    e.preventDefault();
    if (e.stopPropagation) { e.stopPropagation(); }
    var btn = menuToggle(open);
    var typing = isTyping(document.activeElement);
    closeMenus();
    if (btn && !typing && typeof btn.focus === 'function') { btn.focus(); }
    return true;
  }

  /* ---- 도구 이름 -------------------------------------------------------- */

  /** 글 전체 폭 — 말줄임으로 잘렸으면 scrollWidth, 아니면 글자 범위(Range) 폭(칸 폭이 아니라 글 폭). */
  function textWidth(el) {
    if (!el) { return 0; }
    var w = el.scrollWidth > el.clientWidth + 1 ? el.scrollWidth : 0;
    if (typeof document.createRange === 'function') {
      var rg = document.createRange();
      rg.selectNodeContents(el);
      w = Math.max(w, rg.getBoundingClientRect().width);
    }
    return w;
  }

  /** 오른쪽 묶음 앞에 남는 빈 자리(px) — 묶음은 오른쪽 끝에 붙으므로 처음 보이는 단추 왼쪽 끝 − 묶음 왼쪽 끝. */
  function spareRoom(right) {
    var kids = right.children || [];
    var left = right.getBoundingClientRect().left;
    for (var i = 0; i < kids.length; i++) {
      var r = kids[i].getBoundingClientRect();
      if (r.width > 0) { return r.left - left; }
    }
    return 0;
  }

  /** 지금 앱바가 한 줄에 들어가는가 — 오른쪽 묶음이 앱바 밖으로 밀리지 않고, 주문 번호가 다 보이고, 고객명 몫이 남는다.
      margin 이 있으면 그만큼 더 남아야 한다(이름을 다시 펼 때의 여유) — 남는 몫 = 제목 칸이 더 줄 수 있는 폭(긴 고객명은
      다섯 글자 몫까지 줄어든다) + 오른쪽 묶음 앞 빈 자리. */
  function appbarFits(bar, margin) {
    var wrap = bar.querySelector('.dws-appbar-titlewrap');
    var right = bar.querySelector('.dws-appbar-right');
    if (!wrap || !right) { return true; }
    var pad = parseFloat(window.getComputedStyle(bar).paddingRight) || 0;
    if (right.getBoundingClientRect().right > bar.getBoundingClientRect().right - pad + 1) { return false; }
    var need = Math.max(textWidth(bar.querySelector('.dws-appbar-title')),
      Math.min(textWidth(bar.querySelector('.dws-appbar-sub')), SUB_KEEP));
    var titleRoom = wrap.clientWidth + 0.5 - need;
    if (titleRoom < 0) { return false; }
    return !(margin > 0) || titleRoom + spareRoom(right) >= margin;
  }

  /** 제목 칸 상한 — [나가기] + 틈 + 주문 번호·고객명 중 긴 글 폭을 앱바 --dws-left-w 로 남긴다(wizard.css 앱바 격자의
      왼쪽 열 상한). 자리가 넉넉해도 제목 칸은 글 폭까지만 넓어지고 남는 자리는 도구 묶음 뒤로 가서, 오른쪽 묶음 폭이
      바뀌어도 가운데 도구 묶음이 따라 움직이지 않는다. 잰 폭(px)을 돌려준다(못 재면 0 — 속성을 건드리지 않는다). */
  function fitLeft(bar) {
    var left = bar && bar.querySelector('.dws-appbar-left');
    var wrap = bar && bar.querySelector('.dws-appbar-titlewrap');
    if (!left || !wrap || !bar.style || typeof bar.style.setProperty !== 'function') { return 0; }
    var text = Math.max(textWidth(bar.querySelector('.dws-appbar-title')), textWidth(bar.querySelector('.dws-appbar-sub')));
    var w = Math.ceil(wrap.getBoundingClientRect().left - left.getBoundingClientRect().left + Math.max(text, TITLE_MIN) + 1);
    bar.style.setProperty('--dws-left-w', w + 'px');
    return w;
  }

  /** 도구 이름을 보일 만큼만 — 다 → '선택'·'텍스트'만 → 그림만 순서로 대 보고 처음 맞는 것을 앱바 data-seg-names 로
      남긴다. 지금보다 이름을 더 펴는 단계는 HYST 만큼 더 남아야 고른다(접는 쪽은 바로 — 단추가 화면 밖으로 밀리면 안 된다).
      옆으로 미는 줄(좁은 폭, grid 아님)은 그림만이라 속성을 지운다(CSS 폭 단계가 숨긴다). 고른 단계를 돌려준다. */
  function fitSegNames(bar) {
    if (!bar) { return ''; }
    if (window.getComputedStyle(bar).display !== 'grid') {
      bar.removeAttribute('data-seg-names');
      if (bar.style && typeof bar.style.removeProperty === 'function') { bar.style.removeProperty('--dws-left-w'); }
      return '';
    }
    fitLeft(bar);
    var now = NAME_STEPS.indexOf(bar.getAttribute('data-seg-names'));   // 지금 단계(-1 = 처음 재는 것)
    for (var i = 0; i < NAME_STEPS.length; i++) {
      bar.setAttribute('data-seg-names', NAME_STEPS[i]);
      if (i === NAME_STEPS.length - 1 || appbarFits(bar, now >= 0 && i < now ? HYST : 0)) { return NAME_STEPS[i]; }
    }
    return '';
  }

  /* ---- 연결 ------------------------------------------------------------- */

  var ready = false;

  /** 앱바 연결 — 메뉴 Esc 닫기·fixed 메뉴 자리·도구 이름 맞춤. opts: { closeMenus() }(마법사의 메뉴 닫기). 한 번만 건다. */
  function init(opts) {
    if (ready || typeof document.addEventListener !== 'function') { return false; }
    ready = true;
    var closeMenus = opts && typeof opts.closeMenus === 'function' ? opts.closeMenus : function () {};
    var bar = document.querySelector('.dws-appbar');
    var escMenus = ESC_MENUS.map(function (id) { return document.getElementById(id); }).filter(Boolean);
    var barMenus = BAR_MENUS.map(function (id) { return document.getElementById(id); }).filter(Boolean);
    document.addEventListener('keydown', function (e) {   // 잡는 단계(capture) — 마법사 Esc 처리보다 먼저
      if ((e.key === 'Escape' || e.key === 'Esc') && !document.querySelector(OVER_MENU)) { closeMenuByEsc(e, escMenus, closeMenus); }
    }, true);
    if (window.MutationObserver) {   // 메뉴가 열리고 닫힐 때(누가 열었든) 자리를 잡고 지운다
      barMenus.forEach(function (m) {
        new window.MutationObserver(function () { placeMenu(m); }).observe(m, { attributes: true, attributeFilter: ['hidden'] });
      });
    }
    function placeOpen() { barMenus.forEach(function (m) { if (!m.hidden) { placeMenu(m); } }); }
    if (bar) { bar.addEventListener('scroll', placeOpen); }   // 줄을 옆으로 밀면 메뉴도 단추를 따라간다
    var queued = false;
    function later() {   // 다음 그림 때 한 번만(크기 감시 콜백 안에서 크기를 바꾸면 감시가 맴돈다)
      if (queued) { return; }
      queued = true;
      window.requestAnimationFrame(function () { queued = false; placeOpen(); fitSegNames(bar); });
    }
    window.addEventListener('resize', later);
    if (bar) {
      fitSegNames(bar);
      var right = bar.querySelector('.dws-appbar-right');   // 오른쪽 열 폭이 바뀌면(창 폭·제목·넘침) 다시 잰다 — 상태 칩 글은 폭을 안 바꾼다
      if (right && window.ResizeObserver) { new window.ResizeObserver(later).observe(right); }
      var wrap = bar.querySelector('.dws-appbar-titlewrap');   // 불러오기 뒤 고객명이 바뀌면 남길 몫도 바뀐다
      if (wrap && window.MutationObserver) { new window.MutationObserver(later).observe(wrap, { childList: true, characterData: true, subtree: true }); }
      if (document.fonts && document.fonts.ready) { document.fonts.ready.then(later); }
    }
    return true;
  }

  window.FomsWizardAppbar = {
    init: init,
    menuLeft: menuLeft,
    placeMenu: placeMenu,
    closeMenuByEsc: closeMenuByEsc,
    fitSegNames: fitSegNames,
    fitLeft: fitLeft
  };
})();

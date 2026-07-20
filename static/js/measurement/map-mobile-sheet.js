/*
 * FOMS 실측 동선 지도(map_view) — 모바일 바텀시트 · 상세 풀시트 컨트롤러.
 *
 * 담당 범위(스킨 레이어):
 *  - 주문 목록 패널(.map-right-panel)을 peek/half/full 3-스냅 바텀시트로 운전
 *  - 주문 상세 패널(#order-detail-panel)을 풀시트 오버레이로 승격/복귀
 *  - 뒤로가기·ESC·백드롭 닫기, 배경 스크롤 잠금, 포커스 이동
 *
 * 엔진 READ-ONLY 원칙: 카카오 지도와 map_view.html 인라인 전역
 * (selectOrder / loadOrderDetail / closeOrderDetail / openAddressEdit /
 *  openMapManagerEdit)의 시그니처·동작은 건드리지 않는다. 이 모듈은
 * loadOrderDetail·closeOrderDetail 을 "감싸서" 시트 승격만 얹는다.
 *
 * 게이트 문자열은 SSOT(static/css/foundation/foms-shell.css:11 / map-mobile.css)와
 * 바이트 동일해야 한다 — CSS/JS 판정이 어긋나면 승격만 되고 스타일이 없는
 * 반쪽 상태가 된다.
 *
 * 로드: <script defer> (가드 G1). 전역 리스너는 __FOMS_MAP_MOBILE_BOUND 싱글톤(G4).
 */
(function () {
  'use strict';

  if (window.__FOMS_MAP_MOBILE_BOUND) return;

  var GATE = '(max-width: 991.98px), ((min-width: 992px) and (pointer: coarse) and (orientation: portrait))';
  var SNAP_KEY = 'fomsMapSheetSnap';
  var SNAPS = ['peek', 'half', 'full'];
  // map-mobile.css 의 --fmm-peek / --fmm-half 와 동일 값(둘 중 하나만 바꾸면 흡착이 어긋난다).
  var PEEK_PX = 64;
  var HALF_RATIO = 0.52;
  var FLICK_VELOCITY = 0.5;  // px/ms — 이보다 빠르면 방향 다음 스냅으로 던진다
  var DRAG_THRESHOLD = 8;    // px — 목록 스크롤과 시트 드래그를 가르는 최소 이동량
  var TAP_SLOP = 10;         // px — 지도 탭 vs 팬 판정
  var TAP_MS = 400;

  var panel = document.querySelector('.map-right-panel');
  var header = panel && panel.querySelector('.order-list-header');
  var listContent = document.getElementById('order-list-content');
  var detailPanel = document.getElementById('order-detail-panel');
  var mapLeft = document.querySelector('.map-left');
  if (!panel || !header || !listContent || !detailPanel) return;

  window.__FOMS_MAP_MOBILE_BOUND = true;

  var mq = window.matchMedia(GATE);
  var mobileOn = false;
  var snap = 'half';
  var drag = null;
  var suppressClick = false;
  var detailHome = null;
  var backdrop = null;
  var historyPushed = false;

  // ── 스냅 ────────────────────────────────────────────────────────────
  function sheetHeight() {
    return panel.offsetHeight || 0;
  }

  /** 스냅별 translateY(px). CSS 의 calc 와 같은 식을 JS 좌표로 환산한다. */
  function snapY(name) {
    var h = sheetHeight();
    if (name === 'full') return 0;
    if (name === 'half') return Math.max(0, h - Math.round(window.innerHeight * HALF_RATIO));
    return Math.max(0, h - PEEK_PX);
  }

  function nearestSnap(y) {
    var best = SNAPS[0];
    var bestDist = Infinity;
    for (var i = 0; i < SNAPS.length; i++) {
      var d = Math.abs(y - snapY(SNAPS[i]));
      if (d < bestDist) { bestDist = d; best = SNAPS[i]; }
    }
    return best;
  }

  function setSnap(name, persist) {
    if (SNAPS.indexOf(name) < 0) return;
    snap = name;
    panel.classList.remove('fmm-dragging');
    panel.style.removeProperty('--fmm-drag-y');
    for (var i = 0; i < SNAPS.length; i++) {
      panel.classList.toggle('fmm-snap-' + SNAPS[i], SNAPS[i] === name);
    }
    header.setAttribute('aria-expanded', name === 'peek' ? 'false' : 'true');
    if (persist === false) return;
    try {
      window.localStorage.setItem(SNAP_KEY, name);
    } catch (err) {
      console.debug('[map-mobile] 스냅 저장 불가(프라이빗 모드 등)', err);
    }
  }

  function storedSnap() {
    var saved = null;
    try {
      saved = window.localStorage.getItem(SNAP_KEY);
    } catch (err) {
      console.debug('[map-mobile] 스냅 복원 불가', err);
    }
    return SNAPS.indexOf(saved) >= 0 ? saved : 'half';
  }

  function cycleSnap() {
    setSnap(snap === 'peek' ? 'half' : (snap === 'half' ? 'full' : 'peek'));
  }

  // ── 드래그(헤더 상시 · 목록은 최상단에서 아래로 끌 때만) ──────────────
  function dragStart(e, fromContent) {
    if (!mobileOn || drag) return;
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    drag = {
      id: e.pointerId,
      startY: e.clientY,
      lastY: e.clientY,
      lastT: Date.now(),
      velocity: 0,
      base: snapY(snap),
      active: !fromContent
    };
  }

  function dragMove(e) {
    if (!drag || e.pointerId !== drag.id) return;
    var dy = e.clientY - drag.startY;
    if (!drag.active) {
      // 목록에서 시작한 제스처: 스크롤 최상단 + 아래 방향일 때만 시트를 잡는다.
      if (dy > DRAG_THRESHOLD && listContent.scrollTop <= 0) drag.active = true;
      else if (Math.abs(dy) > DRAG_THRESHOLD) { drag = null; return; }
      else return;
    }
    var now = Date.now();
    if (now > drag.lastT) drag.velocity = (e.clientY - drag.lastY) / (now - drag.lastT);
    drag.lastY = e.clientY;
    drag.lastT = now;
    var y = Math.min(snapY('peek'), Math.max(0, drag.base + dy));
    panel.classList.add('fmm-dragging');
    // 드래그 좌표만 인라인 커스텀 프로퍼티(정적 스타일은 전부 map-mobile.css 소유).
    panel.style.setProperty('--fmm-drag-y', y + 'px');
    if (e.cancelable) e.preventDefault();
  }

  function dragEnd(e) {
    if (!drag || (e && e.pointerId !== drag.id)) return;
    var moved = Math.abs(drag.lastY - drag.startY);
    var wasActive = drag.active && moved > 0;
    var velocity = drag.velocity;
    var y = drag.base + (drag.lastY - drag.startY);
    drag = null;
    if (!wasActive) return;
    suppressClick = moved > 6;
    if (Math.abs(velocity) > FLICK_VELOCITY) {
      var idx = SNAPS.indexOf(snap);
      setSnap(velocity < 0
        ? SNAPS[Math.min(SNAPS.length - 1, idx + 1)]
        : SNAPS[Math.max(0, idx - 1)]);
      return;
    }
    setSnap(nearestSnap(y));
  }

  // ── 주문 상세 풀시트 ────────────────────────────────────────────────
  function isDetailVisible() {
    return detailPanel.style.display !== 'none' && detailPanel.style.display !== '';
  }

  function isDetailPromoted() {
    return detailPanel.classList.contains('fmm-detail-sheet');
  }

  function focusDetailClose() {
    var btn = detailPanel.querySelector('.order-detail-header button');
    if (btn) btn.focus();
  }

  function ensureBackdrop() {
    if (backdrop) return backdrop;
    backdrop = document.createElement('div');
    backdrop.className = 'fmm-detail-backdrop';
    backdrop.addEventListener('click', function () {
      if (typeof window.closeOrderDetail === 'function') window.closeOrderDetail();
    });
    return backdrop;
  }

  function promoteDetail() {
    if (!mobileOn) return;
    if (isDetailPromoted()) { focusDetailClose(); return; }
    detailHome = detailPanel.parentNode;
    document.body.appendChild(ensureBackdrop());
    // 시트의 transform 이 fixed 자식의 컨테이닝 블록이 되므로 body 직속으로 옮긴다.
    document.body.appendChild(detailPanel);
    detailPanel.classList.add('fmm-detail-sheet');
    detailPanel.setAttribute('role', 'dialog');
    detailPanel.setAttribute('aria-modal', 'true');
    detailPanel.setAttribute('aria-label', '주문 상세 정보');
    document.body.classList.add('foms-map-detail-open');
    if (!historyPushed) {
      try {
        window.history.pushState({ fomsMapDetail: 1 }, '');
        historyPushed = true;
      } catch (err) {
        console.debug('[map-mobile] pushState 실패 — 뒤로가기 닫힘 비활성', err);
      }
    }
    focusDetailClose();
  }

  /** DOM 원복만 수행(히스토리 처리는 closeOrderDetail 래퍼가 소유). */
  function demoteDetail() {
    if (!isDetailPromoted()) return;
    detailPanel.classList.remove('fmm-detail-sheet');
    detailPanel.removeAttribute('role');
    detailPanel.removeAttribute('aria-modal');
    detailPanel.removeAttribute('aria-label');
    document.body.classList.remove('foms-map-detail-open');
    if (backdrop && backdrop.parentNode) backdrop.parentNode.removeChild(backdrop);
    if (detailHome) detailHome.appendChild(detailPanel);
  }

  // ── 기존 전역 감싸기(시그니처·동작 무변경 + 시트 승격만 추가) ─────────
  var origLoadDetail = window.loadOrderDetail;
  if (typeof origLoadDetail === 'function') {
    window.loadOrderDetail = function () {
      var result = origLoadDetail.apply(this, arguments);
      if (mobileOn) promoteDetail();
      return result;
    };
  }

  var origCloseDetail = window.closeOrderDetail;
  if (typeof origCloseDetail === 'function') {
    window.closeOrderDetail = function () {
      var result = origCloseDetail.apply(this, arguments);
      demoteDetail();
      if (historyPushed) {
        historyPushed = false;
        try {
          window.history.back();
        } catch (err) {
          console.debug('[map-mobile] history.back 실패', err);
        }
      }
      return result;
    };
  }

  // ── 게이트 동기화 ───────────────────────────────────────────────────
  function syncGate() {
    var on = mq.matches;
    if (on === mobileOn) return;
    mobileOn = on;
    if (on) {
      header.setAttribute('role', 'button');
      header.setAttribute('tabindex', '0');
      setSnap(storedSnap(), false);
      if (isDetailVisible()) promoteDetail();
      return;
    }
    // PC 폭으로 이탈: 승격 해제 → 기존 인라인 패널로 자연 복귀
    demoteDetail();
    historyPushed = false;
    panel.classList.remove('fmm-snap-peek', 'fmm-snap-half', 'fmm-snap-full', 'fmm-dragging');
    panel.style.removeProperty('--fmm-drag-y');
    header.removeAttribute('role');
    header.removeAttribute('tabindex');
    header.removeAttribute('aria-expanded');
  }

  // ── 배선 ────────────────────────────────────────────────────────────
  header.addEventListener('pointerdown', function (e) { dragStart(e, false); });
  listContent.addEventListener('pointerdown', function (e) { dragStart(e, true); });
  document.addEventListener('pointermove', dragMove, { passive: false });
  document.addEventListener('pointerup', dragEnd);
  document.addEventListener('pointercancel', dragEnd);

  header.addEventListener('click', function () {
    if (!mobileOn) return;
    if (suppressClick) { suppressClick = false; return; }
    cycleSnap();
  });

  header.addEventListener('keydown', function (e) {
    if (!mobileOn) return;
    if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
    e.preventDefault();
    cycleSnap();
  });

  // 지도 빈 공간 탭 → peek 로 축소(팬/줌 제스처는 이동량·시간으로 배제).
  if (mapLeft) {
    var mapTap = null;
    mapLeft.addEventListener('pointerdown', function (e) {
      mapTap = { x: e.clientX, y: e.clientY, t: Date.now() };
    });
    mapLeft.addEventListener('pointerup', function (e) {
      var start = mapTap;
      mapTap = null;
      if (!mobileOn || !start) return;
      if (Date.now() - start.t > TAP_MS) return;
      if (Math.abs(e.clientX - start.x) > TAP_SLOP || Math.abs(e.clientY - start.y) > TAP_SLOP) return;
      if (e.target.closest('.foms-kmap-popup, .foms-kmap-routecalc, .foms-kmap-pill, button, a, input, select')) return;
      if (snap !== 'peek') setSnap('peek');
    });
  }

  document.addEventListener('keydown', function (e) {
    if (!mobileOn || e.key !== 'Escape') return;
    if (isDetailPromoted() && typeof window.closeOrderDetail === 'function') {
      window.closeOrderDetail();
    }
  });

  window.addEventListener('popstate', function () {
    if (!historyPushed) return;
    historyPushed = false;  // 래퍼의 history.back() 재진입 가드
    if (isDetailPromoted() && typeof window.closeOrderDetail === 'function') {
      window.closeOrderDetail();
    }
  });

  if (typeof mq.addEventListener === 'function') mq.addEventListener('change', syncGate);
  else if (typeof mq.addListener === 'function') mq.addListener(syncGate);

  syncGate();

  /**
   * 전역 계약: 마커 팝업의 [주문 상세 보기]가 이 훅을 우선 사용한다.
   * (훅이 없으면 map-view-kakao.js 가 기존 selectOrder 직접 호출로 폴백)
   */
  window.FomsMapMobileSheet = {
    isMobile: function () { return mobileOn; },
    setSnap: setSnap,
    openDetail: function (orderId) {
      if (typeof window.selectOrder === 'function') window.selectOrder(Number(orderId));
      if (mobileOn) setSnap('full');
    },
    /** QA 진단 훅(read-only): 헤드리스 검증이 IIFE 내부 상태를 볼 수 있게 노출. */
    _debug: function () {
      return {
        mobile: mobileOn,
        snap: snap,
        snapY: { peek: snapY('peek'), half: snapY('half'), full: 0 },
        sheetHeight: sheetHeight(),
        detailVisible: isDetailVisible(),
        detailPromoted: isDetailPromoted(),
        detailParent: detailPanel.parentNode ? detailPanel.parentNode.className || detailPanel.parentNode.tagName : null,
        historyPushed: historyPushed
      };
    }
  };
})();

/* =============================================================
   AS 대시보드 PC 12열 컬럼 폭 조절
   계약 출처: static/js/shipment/dashboard-columns.js (출고 대시보드, 2026-03 GDM
   colgroup+schema+resize 재작성). DOM 계약(colgroup col[data-col-key] +
   thead th[data-col-key] > .col-resize-handle + table-layout:fixed)을 그대로 따른다.

   출고판과 다른 점 하나 — 기본 폭을 JS 스키마가 들고 있지 않다.
   기본값은 CSS(`#as-dashboard-table col[data-col-key]`)가 소유하고 JS 는 사용자가
   조정한 폭만 인라인으로 덮는다. 덕분에 (1) 기본 폭이 CSS/JS 두 곳에서 갈릴 일이 없고
   (2) JS 가 안 돌아도 열 폭이 살아 있으며(table-layout:fixed + col 폭 미지정 = 12등분 붕괴 회피)
   (3) 초기화 = 인라인 제거로 끝난다.

   최소 폭만 JS 가 갖는다 — <col> 에는 min-width 가 먹지 않아 드래그 하한을 CSS 로 표현할
   방법이 없다. 주소 260/내용 240 하한은 2026-07-28 붕괴(주소 1글자 세로 흐름) 재발 방지선이다.
   ============================================================= */

(function () {
  'use strict';

  var TABLE_ID = 'as-dashboard-table';
  var STORAGE_KEY = 'foms.asDashboard.columnWidths.v1';
  var RESET_BTN_ID = 'as-btn-reset-column-widths';
  var DESKTOP_MIN_WIDTH = 768; // PC 테이블 표시 경계(.d-none.d-md-block)와 동일

  /** 열별 드래그 하한(px). 키는 col[data-col-key] 와 1:1. */
  var MIN_WIDTHS = {
    order: 56,
    received: 88,
    visit: 150,
    completed: 150,
    manager: 64,
    workers: 150,
    customer: 96,
    address: 180,
    attach: 48,
    blueprint: 44,
    content: 200,
    status: 76
  };

  /**
   * 저장된 폭 읽기. 손상/차단(사파리 프라이빗 등) 시 빈 객체.
   * @returns {Object<string, number>}
   */
  function loadSavedWidths() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      return (parsed && typeof parsed === 'object') ? parsed : {};
    } catch (e) { return {}; }
  }

  function saveWidths(widths) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(widths)); } catch (e) {}
  }

  function isDesktop() {
    return window.innerWidth >= DESKTOP_MIN_WIDTH;
  }

  function getCols(table) {
    return table.querySelectorAll('colgroup col[data-col-key]');
  }

  /** 저장분만 인라인으로 덮는다(미저장 열은 CSS 기본폭 유지). */
  function applySavedWidths(table, saved) {
    getCols(table).forEach(function (col) {
      var w = saved[col.dataset.colKey];
      if (typeof w === 'number' && w > 0) col.style.width = w + 'px';
    });
  }

  /** 현재 실렌더 폭 전량 수집 — 한 열을 옮기면 이웃 폭도 재계산되므로 통째로 저장한다. */
  function collectWidths(table) {
    var widths = {};
    getCols(table).forEach(function (col) {
      var w = Math.round(col.getBoundingClientRect().width);
      if (w > 0) widths[col.dataset.colKey] = w;
    });
    return widths;
  }

  /**
   * 핸들 드래그 1회 처리.
   *
   * pointer 이벤트를 쓰는 이유: mouse/touch 두 벌을 붙이지 않아도 되고, setPointerCapture 로
   * 커서가 표를 벗어나도 드래그가 끊기지 않는다(mousemove 판은 창 밖에서 놓치면 고착된다).
   * @param {PointerEvent} e
   * @param {HTMLTableElement} table
   */
  function onHandlePointerDown(e, table) {
    if (!isDesktop() || e.button !== 0) return;
    var th = e.currentTarget.closest('th[data-col-key]');
    if (!th) return;
    var key = th.dataset.colKey;
    var col = table.querySelector('colgroup col[data-col-key="' + key + '"]');
    if (!col) return;

    e.preventDefault();
    e.stopPropagation();

    var min = MIN_WIDTHS[key] || 48;
    var startX = e.clientX;
    var startWidth = col.getBoundingClientRect().width;
    var handle = e.currentTarget;

    table.classList.add('col-resizing');
    document.body.classList.add('col-resizing-active');
    try { handle.setPointerCapture(e.pointerId); } catch (err) {}

    function onMove(ev) {
      col.style.width = Math.max(min, startWidth + (ev.clientX - startX)) + 'px';
    }

    function onUp() {
      handle.removeEventListener('pointermove', onMove);
      handle.removeEventListener('pointerup', onUp);
      handle.removeEventListener('pointercancel', onUp);
      table.classList.remove('col-resizing');
      document.body.classList.remove('col-resizing-active');
      saveWidths(collectWidths(table));
    }

    handle.addEventListener('pointermove', onMove);
    handle.addEventListener('pointerup', onUp);
    handle.addEventListener('pointercancel', onUp);
  }

  /** 테이블 노드 단위 중복 바인딩 가드(프래그먼트 스왑 시엔 새 노드라 자연 초기화). */
  function bindHandles(table) {
    if (table.dataset.asResizeBound === '1') return;
    table.dataset.asResizeBound = '1';
    table.querySelectorAll('thead th[data-col-key] .col-resize-handle').forEach(function (h) {
      h.addEventListener('pointerdown', function (e) { onHandlePointerDown(e, table); });
    });
  }

  function init() {
    var table = document.getElementById(TABLE_ID);
    if (!table) return;
    if (isDesktop()) {
      applySavedWidths(table, loadSavedWidths());
      bindHandles(table);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // 프래그먼트 스왑마다 이 파일이 재실행되므로 document 위임은 1회만(perf 가드 G4).
  if (!window.__FOMS_AS_COLUMNS_BOUND) {
    window.__FOMS_AS_COLUMNS_BOUND = true;
    document.addEventListener('foms:erp-shell-fragment-swapped', init);
    // 초기화 = 저장분 삭제 + 인라인 제거 → CSS 기본폭 복귀(위 파일 주석 참조).
    document.addEventListener('click', function (e) {
      var btn = e.target.closest && e.target.closest('#' + RESET_BTN_ID);
      if (!btn) return;
      try { localStorage.removeItem(STORAGE_KEY); } catch (err) {}
      var table = document.getElementById(TABLE_ID);
      if (table) getCols(table).forEach(function (col) { col.style.width = ''; });
    });
  }
})();

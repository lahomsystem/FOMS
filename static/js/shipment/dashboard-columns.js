/* =============================================================
   출고 대시보드 컬럼 리사이즈 JS
   파일: static/js/shipment-dashboard-columns.js
   생성: 2026-03-10 (GDM colgroup+schema+resize 재작성)

   원칙:
   - 컬럼 폭의 진실 원천은 colgroup 하나
   - 이 파일은 table/colgroup/th 만 제어
   - 편집 입력 시스템(시공시간/도면담당자/시공자)과 완전 분리
   ============================================================= */

(function () {
  'use strict';

  // ── 1. 컬럼 스키마 ────────────────────────────────────────────
  var SHIPMENT_COLUMN_SCHEMA = {
    detail:               { defaultWidth: 60,  minWidth: 48,  resizable: true },
    customer:             { defaultWidth: 90,  minWidth: 80,  resizable: true },
    orderer:              { defaultWidth: 90,  minWidth: 80,  resizable: true },
    product:              { defaultWidth: 100, minWidth: 60,  resizable: true },
    spec:                 { defaultWidth: 84,  minWidth: 70,  resizable: true },
    address:              { defaultWidth: 320, minWidth: 180, resizable: true, flexible: true },
    construction_time:    { defaultWidth: 150, minWidth: 140, resizable: true },
    drawing_managers:     { defaultWidth: 170, minWidth: 150, resizable: true },
    construction_workers: { defaultWidth: 170, minWidth: 150, resizable: true },
    vehicle:              { defaultWidth: 110, minWidth: 80,  resizable: true },
    trip:                 { defaultWidth: 120, minWidth: 80,  resizable: true },
    manager:              { defaultWidth: 95,  minWidth: 95,  resizable: true }
  };

  var STORAGE_KEY = 'foms.shipmentDashboard.columnWidths.v2';
  var TABLE_ID    = 'shipment-dashboard-table';

  // ── 2. localStorage 저장/복원 ─────────────────────────────────
  function loadSavedWidths() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      return (parsed && typeof parsed === 'object') ? parsed : {};
    } catch (e) { return {}; }
  }

  function saveWidths(widths) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(widths));
    } catch (e) {}
  }

  function clearSavedWidths() {
    try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
  }

  // ── 3. colgroup col 요소에 폭 적용 ───────────────────────────
  function applyWidthsToCols(table, savedWidths) {
    var cols = table.querySelectorAll('colgroup col[data-col-key]');
    cols.forEach(function (col) {
      var key    = col.dataset.colKey;
      var schema = SHIPMENT_COLUMN_SCHEMA[key];
      if (!schema) return;
      var w = (savedWidths[key] !== undefined) ? savedWidths[key] : schema.defaultWidth;
      col.style.width = w + 'px';
    });
  }

  // ── 4. 현재 col 폭 수집 ──────────────────────────────────────
  function collectCurrentWidths(table) {
    var widths = {};
    var cols = table.querySelectorAll('colgroup col[data-col-key]');
    cols.forEach(function (col) {
      var key = col.dataset.colKey;
      var w   = parseInt(col.style.width, 10);
      if (!isNaN(w)) widths[key] = w;
    });
    return widths;
  }

  // ── 5. 드래그 리사이즈 이벤트 ────────────────────────────────
  function bindResizeHandles(table) {
    // 같은 테이블 노드에 중복 바인딩 방지(스왑 시엔 새 테이블 노드라 dataset 자연 초기화).
    if (table.dataset.shipResizeBound === '1') return;
    table.dataset.shipResizeBound = '1';
    var handles = table.querySelectorAll('thead th[data-col-key] .col-resize-handle');
    handles.forEach(function (handle) {
      handle.addEventListener('mousedown', function (e) {
        onHandleMouseDown(e, table);
      });
    });
  }

  function onHandleMouseDown(e, table) {
    // 모바일/터치 환경 무시
    if (window.innerWidth <= 992) return;

    e.preventDefault();
    e.stopPropagation();

    var th     = e.currentTarget.closest('th');
    var colKey = th.dataset.colKey;
    var schema = SHIPMENT_COLUMN_SCHEMA[colKey];
    if (!schema || !schema.resizable) return;

    var col = table.querySelector('colgroup col[data-col-key="' + colKey + '"]');
    if (!col) return;

    var startX     = e.clientX;
    var startWidth = col.offsetWidth || schema.defaultWidth;

    table.classList.add('col-resizing');
    document.body.classList.add('col-resizing-active');

    function onMouseMove(ev) {
      var dx       = ev.clientX - startX;
      var newWidth = Math.max(schema.minWidth, startWidth + dx);
      col.style.width = newWidth + 'px';
    }

    function onMouseUp() {
      table.classList.remove('col-resizing');
      document.body.classList.remove('col-resizing-active');
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);

      // 전체 컬럼 폭 수집 후 저장
      saveWidths(collectCurrentWidths(table));
    }

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }

  // ── 6. 컬럼 폭 초기화 버튼 ──────────────────────────────────
  function bindResetButton(table) {
    var btn = document.getElementById('btn-reset-column-widths');
    if (!btn || btn.dataset.fomsShipResetBound === '1') return;
    btn.dataset.fomsShipResetBound = '1';
    btn.addEventListener('click', function () {
      clearSavedWidths();
      applyWidthsToCols(table, {});
    });
  }

  // ── 7. 초기화 진입점 ─────────────────────────────────────────
  function init() {
    var table = document.getElementById(TABLE_ID);
    if (!table) return;

    // 모바일에서는 저장된 폭 복원 무시 (프리셋 기본값만 사용)
    var isMobile    = window.innerWidth <= 992;
    var savedWidths = isMobile ? {} : loadSavedWidths();

    applyWidthsToCols(table, savedWidths);

    if (!isMobile) {
      bindResizeHandles(table);
    }

    bindResetButton(table);
  }

  // entry 동적 로드 대응 readyState 분기 + fragment 스왑 재초기화(모듈은 1회 로드).
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  if (!window.__FOMS_SHIP_COLUMNS_BOUND) {
    window.__FOMS_SHIP_COLUMNS_BOUND = true;
    document.addEventListener('foms:erp-shell-fragment-swapped', init);
  }

})();

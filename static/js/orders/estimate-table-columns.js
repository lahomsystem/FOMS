/* =============================================================
   견적서(계약서) 계약 내용 테이블 — 컬럼 폭 조절
   원칙: colgroup col[data-col-key] = 폭의 단일 진실 원천
   저장: localStorage (출고/실측 대시보드와 동일 패턴)
   ============================================================= */

(function () {
  'use strict';

  var TABLE_ID = 'erp-estimate-items-table';
  var STORAGE_KEY = 'foms.estimatePane.columnWidths.v1';
  var DESKTOP_BREAKPOINT = 992;

  /** @type {Record<string, {defaultWidth: number, minWidth: number, resizable?: boolean}>} */
  var ESTIMATE_COLUMN_SCHEMA = {
    name:   { defaultWidth: 110, minWidth: 72,  resizable: true },
    spec:   { defaultWidth: 168, minWidth: 80,  resizable: true },
    color:  { defaultWidth: 210, minWidth: 96,  resizable: true },
    qty:    { defaultWidth: 32,  minWidth: 28,  resizable: true },
    amount: { defaultWidth: 96,  minWidth: 80,  resizable: true }
  };

  /**
   * localStorage에서 저장된 컬럼 폭 객체를 반환한다.
   * @returns {Record<string, number>}
   */
  function loadSavedWidths() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (e) {
      return {};
    }
  }

  /**
   * 컬럼 폭 객체를 localStorage에 저장한다.
   * @param {Record<string, number>} widths
   */
  function saveWidths(widths) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(widths));
    } catch (e) {
      console.error('[estimate-table-columns] 컬럼 폭 저장 실패', e);
    }
  }

  function clearSavedWidths() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {
      console.error('[estimate-table-columns] 컬럼 폭 초기화 실패', e);
    }
  }

  var _viewportTimer = null;
  var _handlesBound = false;
  var _resetBound = false;

  function canUseDesktopResize() {
    return window.innerWidth > DESKTOP_BREAKPOINT;
  }

  function scheduleViewportSync() {
    if (_viewportTimer) window.clearTimeout(_viewportTimer);
    _viewportTimer = window.setTimeout(function () {
      initEstimateTableColumns(true);
    }, 150);
  }

  /**
   * 단일 컬럼 폭을 스키마 minWidth 이상으로 적용한다.
   * @param {HTMLTableElement} table
   * @param {string} colKey
   * @param {number} widthPx
   */
  function setColumnWidth(table, colKey, widthPx) {
    var schema = ESTIMATE_COLUMN_SCHEMA[colKey];
    if (!schema) return;

    var nextWidth = Math.max(schema.minWidth, Math.round(Number(widthPx) || schema.defaultWidth));
    var col = table.querySelector('colgroup col[data-col-key="' + colKey + '"]');
    if (!col) return;
    col.style.width = nextWidth + 'px';
  }

  /**
   * colgroup에 스키마/저장값 기준 폭을 적용한다.
   * @param {HTMLTableElement} table
   * @param {Record<string, number>} savedWidths
   */
  function applyWidthsToCols(table, savedWidths) {
    Object.keys(ESTIMATE_COLUMN_SCHEMA).forEach(function (key) {
      var schema = ESTIMATE_COLUMN_SCHEMA[key];
      var nextWidth = savedWidths && savedWidths[key] !== undefined
        ? savedWidths[key]
        : schema.defaultWidth;
      setColumnWidth(table, key, nextWidth);
    });
  }

  /**
   * 현재 colgroup col 요소의 px 폭을 수집한다.
   * @param {HTMLTableElement} table
   * @returns {Record<string, number>}
   */
  function collectCurrentWidths(table) {
    var widths = {};
    table.querySelectorAll('colgroup col[data-col-key]').forEach(function (col) {
      var key = col.dataset.colKey;
      var w = parseInt(col.style.width, 10);
      if (!isNaN(w)) widths[key] = w;
    });
    return widths;
  }

  /**
   * thead th 리사이즈 핸들에 mousedown 바인딩.
   * @param {HTMLTableElement} table
   */
  function bindResizeHandles(table) {
    if (_handlesBound) return;
    table.querySelectorAll('thead th[data-col-key] .erp-est-col-resize-handle').forEach(function (handle) {
      handle.addEventListener('mousedown', function (e) {
        onHandleMouseDown(e, table);
      });
    });
    _handlesBound = true;
  }

  /**
   * @param {MouseEvent} e
   * @param {HTMLTableElement} table
   */
  function onHandleMouseDown(e, table) {
    if (window.innerWidth <= DESKTOP_BREAKPOINT) return;

    e.preventDefault();
    e.stopPropagation();

    var th = e.currentTarget.closest('th');
    if (!th) return;

    var colKey = th.dataset.colKey;
    var schema = ESTIMATE_COLUMN_SCHEMA[colKey];
    if (!schema || schema.resizable === false) return;

    var col = table.querySelector('colgroup col[data-col-key="' + colKey + '"]');
    if (!col) return;

    var startX = e.clientX;
    var startWidth = col.offsetWidth || schema.defaultWidth;

    table.classList.add('erp-est-col-resizing');
    document.body.classList.add('erp-est-col-resizing-active');

    function onMouseMove(ev) {
      var dx = ev.clientX - startX;
      setColumnWidth(table, colKey, startWidth + dx);
    }

    function onMouseUp() {
      table.classList.remove('erp-est-col-resizing');
      document.body.classList.remove('erp-est-col-resizing-active');
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      saveWidths(collectCurrentWidths(table));
    }

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }

  /**
   * 컬럼 폭 초기화 버튼 바인딩.
   * @param {HTMLTableElement} table
   */
  function bindResetButton(table) {
    if (_resetBound) return;
    var btn = document.getElementById('btn-est-reset-column-widths');
    if (!btn) return;
    btn.addEventListener('click', function () {
      clearSavedWidths();
      applyWidthsToCols(table, {});
    });
    _resetBound = true;
  }

  /**
   * 견적서 계약 내용 테이블 컬럼 리사이저 초기화.
   * @param {boolean} [fromViewport]
   * @returns {boolean}
   */
  function initEstimateTableColumns(fromViewport) {
    var table = document.getElementById(TABLE_ID);
    if (!table) return false;

    var isDesktop = canUseDesktopResize();
    var savedWidths = isDesktop ? loadSavedWidths() : {};

    applyWidthsToCols(table, savedWidths);

    if (isDesktop) {
      bindResizeHandles(table);
    }

    if (!fromViewport) {
      bindResetButton(table);
      window.addEventListener('resize', scheduleViewportSync);
    }

    return true;
  }

  window.initEstimateTableColumns = initEstimateTableColumns;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initEstimateTableColumns);
  } else {
    initEstimateTableColumns();
  }
})();

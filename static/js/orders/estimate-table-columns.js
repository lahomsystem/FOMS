/* =============================================================
   견적서(계약서) 계약 내용 테이블 — 컬럼 폭 조절
   엔진: static/js/runtime/column-resizer.js (colResizable vanilla fork)
   모드: fit — 인접 컬럼 경계 이동, 테이블 폭 합 유지
   저장: localStorage (출고/실측과 동일 키 패턴)
   ============================================================= */

(function () {
  'use strict';

  var TABLE_ID = 'erp-estimate-items-table';
  var STORAGE_KEY = 'foms.estimatePane.columnWidths.v1';
  var RESIZER_SESSION_KEY = TABLE_ID;
  var DESKTOP_BREAKPOINT = 992;
  var DESKTOP_POINTER_QUERY = '(hover: hover) and (pointer: fine)';

  var ESTIMATE_COLUMN_SCHEMA = {
    name:   { defaultWidth: 110, minWidth: 72 },
    spec:   { defaultWidth: 168, minWidth: 80 },
    color:  { defaultWidth: 210, minWidth: 96 },
    qty:    { defaultWidth: 32,  minWidth: 28 },
    amount: { defaultWidth: 96,  minWidth: 80 }
  };

  var viewportTimer = null;
  var lastViewportMode = null;
  var desktopResizer = null;
  var desktopResizeListener = null;
  var isDesktopResizeListenerAttached = false;
  var resetBound = false;

  function getTable() {
    return document.getElementById(TABLE_ID);
  }

  function isEstimateDocumentVisible() {
    var doc = document.getElementById('est-document');
    return !!(doc && !doc.classList.contains('erp-est-hidden'));
  }

  function canUseDesktopResize() {
    if (window.innerWidth <= DESKTOP_BREAKPOINT) return false;
    if (typeof window.matchMedia !== 'function') return true;
    return window.matchMedia(DESKTOP_POINTER_QUERY).matches;
  }

  function getColumnElements(table, colKey) {
    return {
      col: table.querySelector('colgroup col[data-col-key="' + colKey + '"]'),
      th: table.querySelector('thead th[data-col-key="' + colKey + '"]')
    };
  }

  function getColumnWidth(colEl, thEl) {
    var styleWidth = colEl ? parseFloat(colEl.style.width) : NaN;
    if (!isNaN(styleWidth)) return styleWidth;

    var target = thEl || colEl;
    return target ? target.getBoundingClientRect().width : NaN;
  }

  function setColumnWidth(table, colKey, widthPx) {
    var schema = ESTIMATE_COLUMN_SCHEMA[colKey];
    if (!schema) return;

    var nextWidth = Math.max(schema.minWidth, Math.round(widthPx));
    var columnEls = getColumnElements(table, colKey);
    if (!columnEls.col || !columnEls.th) return;

    var widthText = nextWidth + 'px';
    columnEls.col.style.width = widthText;
    columnEls.th.style.width = widthText;
    columnEls.th.style.minWidth = widthText;
    columnEls.th.style.maxWidth = widthText;
  }

  function applyWidthsToCols(table, widths) {
    Object.keys(ESTIMATE_COLUMN_SCHEMA).forEach(function (key) {
      var schema = ESTIMATE_COLUMN_SCHEMA[key];
      var nextWidth = widths && widths[key] !== undefined ? widths[key] : schema.defaultWidth;
      setColumnWidth(table, key, nextWidth);
    });
  }

  function collectCurrentWidths(table) {
    var result = {};
    Object.keys(ESTIMATE_COLUMN_SCHEMA).forEach(function (key) {
      var columnEls = getColumnElements(table, key);
      var width = getColumnWidth(columnEls.col, columnEls.th);
      if (!isNaN(width)) result[key] = Math.round(width);
    });
    return result;
  }

  function applySchemaMinimums(table) {
    Object.keys(ESTIMATE_COLUMN_SCHEMA).forEach(function (key) {
      var schema = ESTIMATE_COLUMN_SCHEMA[key];
      var columnEls = getColumnElements(table, key);
      var currentWidth = getColumnWidth(columnEls.col, columnEls.th);
      if (!isNaN(currentWidth) && currentWidth < schema.minWidth) {
        setColumnWidth(table, key, schema.minWidth);
      }
    });
  }

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

  function clearLibrarySessionStore() {
    try {
      sessionStorage.removeItem(RESIZER_SESSION_KEY);
    } catch (e) {}
  }

  function normalizeTableInlineWidths(table) {
    table.style.width = '';
    table.style.minWidth = '';
  }

  function getResizerConstructor() {
    if (!window.ColumnResizer) return null;
    return window.ColumnResizer.default || window.ColumnResizer;
  }

  function getGripContainer(table) {
    var prev = table.previousElementSibling;
    return prev && prev.classList && prev.classList.contains('grip-container') ? prev : null;
  }

  function destroyDesktopResizer(table) {
    if (desktopResizer && typeof desktopResizer.destroy === 'function') {
      desktopResizer.destroy();
    }
    desktopResizer = null;
    desktopResizeListener = null;
    isDesktopResizeListenerAttached = false;

    if (table) {
      var gripContainer = getGripContainer(table);
      if (gripContainer && gripContainer.parentNode) {
        gripContainer.parentNode.removeChild(gripContainer);
      }
    }
  }

  function syncDesktopGripPositions() {
    if (!desktopResizer || typeof desktopResizer.onResize !== 'function') return;
    desktopResizer.onResize();
  }

  function attachDesktopResizeListener() {
    if (!desktopResizeListener || isDesktopResizeListenerAttached) return;
    window.addEventListener('resize', desktopResizeListener);
    isDesktopResizeListenerAttached = true;
  }

  function detachDesktopResizeListener() {
    if (!desktopResizeListener || !isDesktopResizeListenerAttached) return;
    window.removeEventListener('resize', desktopResizeListener);
    isDesktopResizeListenerAttached = false;
  }

  function initDesktopResizer(table) {
    if (desktopResizer) return;

    var ResizerCtor = getResizerConstructor();
    if (!ResizerCtor) {
      console.warn('[estimate-table-columns] ColumnResizer unavailable — fallback static widths only');
      return;
    }

    if (table.clientWidth <= 0) return;

    clearLibrarySessionStore();
    desktopResizer = new ResizerCtor(table, {
      resizeMode: 'fit',
      liveDrag: true,
      minWidth: 28,
      headerOnly: true,
      removePadding: false,
      serialize: false,
      draggingClass: 'erp-est-col-resizer-active',
      gripInnerHtml: '<div class="erp-est-col-resizer-grip"></div>',
      onResize: function () {
        applySchemaMinimums(table);
        saveWidths(collectCurrentWidths(table));
      }
    });

    desktopResizeListener = typeof desktopResizer.onResize === 'function' ? desktopResizer.onResize : null;
    isDesktopResizeListenerAttached = !!desktopResizeListener;

    applySchemaMinimums(table);
    saveWidths(collectCurrentWidths(table));
  }

  function applyDesktopState(table) {
    normalizeTableInlineWidths(table);
    applyWidthsToCols(table, loadSavedWidths());
    applySchemaMinimums(table);
    initDesktopResizer(table);
    attachDesktopResizeListener();
    syncDesktopGripPositions();
  }

  function applyStaticTableState(table) {
    destroyDesktopResizer(table);
    detachDesktopResizeListener();
    normalizeTableInlineWidths(table);
    applyWidthsToCols(table, loadSavedWidths());
    applySchemaMinimums(table);
  }

  function bindResetButton(table) {
    if (resetBound) return;
    var btn = document.getElementById('btn-est-reset-column-widths');
    if (!btn) return;

    btn.addEventListener('click', function () {
      clearSavedWidths();
      normalizeTableInlineWidths(table);
      applyWidthsToCols(table, {});
      applySchemaMinimums(table);
      saveWidths(collectCurrentWidths(table));
      syncDesktopGripPositions();
    });
    resetBound = true;
  }

  function syncViewportState(force) {
    var table = getTable();
    if (!table || !isEstimateDocumentVisible()) return false;

    var nextMode = canUseDesktopResize() ? 'desktop' : 'static';
    if (!force && nextMode === lastViewportMode) {
      syncDesktopGripPositions();
      return true;
    }

    lastViewportMode = nextMode;
    if (nextMode === 'desktop') {
      applyDesktopState(table);
      return true;
    }

    applyStaticTableState(table);
    return true;
  }

  function initEstimateTableColumns(force) {
    var table = getTable();
    if (!table) return false;

    bindResetButton(table);
    if (!isEstimateDocumentVisible()) return false;
    return syncViewportState(!!force);
  }

  function refreshEstimateTableColumns() {
    var table = getTable();
    if (!table || !isEstimateDocumentVisible()) return false;

    destroyDesktopResizer(table);
    lastViewportMode = null;
    return syncViewportState(true);
  }

  function scheduleEstimateColumnRefresh() {
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () {
        refreshEstimateTableColumns();
      });
    });
  }

  function setExportMode(isExporting) {
    var table = getTable();
    if (!table) return;

    table.classList.toggle('erp-est-exporting', !!isExporting);
    var gripContainer = getGripContainer(table);
    if (gripContainer) {
      gripContainer.classList.toggle('erp-est-exporting', !!isExporting);
    }
  }

  window.initEstimateTableColumns = initEstimateTableColumns;
  window.refreshEstimateTableColumns = refreshEstimateTableColumns;
  window.scheduleEstimateColumnRefresh = scheduleEstimateColumnRefresh;
  window.setEstimateTableExportMode = setExportMode;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      initEstimateTableColumns(true);
    });
  } else {
    initEstimateTableColumns(true);
  }

  window.addEventListener('resize', function () {
    clearTimeout(viewportTimer);
    viewportTimer = window.setTimeout(function () {
      if (!isEstimateDocumentVisible()) return;
      refreshEstimateTableColumns();
    }, 150);
  });
})();

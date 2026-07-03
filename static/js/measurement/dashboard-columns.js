(function () {
  'use strict';

  var TABLE_ID = 'measurement-dashboard-table';
  var DESKTOP_BREAKPOINT = 992;
  var DESKTOP_POINTER_QUERY = '(hover: hover) and (pointer: fine)';
  var DESKTOP_STORAGE_KEY = 'foms.measurementDashboard.columnWidths.v2';
  var RESIZER_SESSION_KEY = TABLE_ID;

  var viewportTimer = null;
  var lastViewportMode = null;
  var desktopResizer = null;
  var desktopResizeListener = null;
  var isDesktopResizeListenerAttached = false;
  var resizerTable = null;

  var MEASUREMENT_COLUMN_SCHEMA = {
    detail:           { defaultWidth: 70,  minWidth: 56 },
    customer:         { defaultWidth: 120, minWidth: 96 },
    orderer:          { defaultWidth: 110, minWidth: 90 },
    address:          { defaultWidth: 190, minWidth: 150 },
    phone:            { defaultWidth: 130, minWidth: 110 },
    measurement_date: { defaultWidth: 100, minWidth: 90 },
    meas_time:        { defaultWidth: 110, minWidth: 90 },
    product:          { defaultWidth: 190, minWidth: 150 },
    manager:          { defaultWidth: 200, minWidth: 150 }
  };

  function getTable() {
    return document.getElementById(TABLE_ID);
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

    var target = colEl || thEl;
    return target ? target.getBoundingClientRect().width : NaN;
  }

  function setColumnWidth(table, colKey, widthPx) {
    var schema = MEASUREMENT_COLUMN_SCHEMA[colKey];
    if (!schema) return;

    var nextWidth = Math.max(schema.minWidth, Math.round(widthPx));
    var columnEls = getColumnElements(table, colKey);
    if (!columnEls.col || !columnEls.th) return;

    columnEls.col.style.width = nextWidth + 'px';
    columnEls.th.style.width = nextWidth + 'px';
    columnEls.th.style.minWidth = nextWidth + 'px';
    columnEls.th.style.maxWidth = nextWidth + 'px';
  }

  function applyWidthsToCols(table, widths) {
    Object.keys(MEASUREMENT_COLUMN_SCHEMA).forEach(function (key) {
      var schema = MEASUREMENT_COLUMN_SCHEMA[key];
      var nextWidth = widths && widths[key] !== undefined ? widths[key] : schema.defaultWidth;
      setColumnWidth(table, key, nextWidth);
    });
  }

  function collectCurrentWidths(table) {
    var widths = {};

    Object.keys(MEASUREMENT_COLUMN_SCHEMA).forEach(function (key) {
      var columnEls = getColumnElements(table, key);
      var width = getColumnWidth(columnEls.col, columnEls.th);
      if (!isNaN(width)) {
        widths[key] = Math.round(width);
      }
    });

    return widths;
  }

  function applySchemaMinimums(table) {
    Object.keys(MEASUREMENT_COLUMN_SCHEMA).forEach(function (key) {
      var schema = MEASUREMENT_COLUMN_SCHEMA[key];
      var columnEls = getColumnElements(table, key);
      var currentWidth = getColumnWidth(columnEls.col, columnEls.th);
      if (!isNaN(currentWidth) && currentWidth < schema.minWidth) {
        setColumnWidth(table, key, schema.minWidth);
      }
    });
  }

  function loadDesktopWidths() {
    try {
      var raw = localStorage.getItem(DESKTOP_STORAGE_KEY);
      if (!raw) return {};

      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (error) {
      return {};
    }
  }

  function saveDesktopWidths(widths) {
    try {
      localStorage.setItem(DESKTOP_STORAGE_KEY, JSON.stringify(widths));
    } catch (error) {}
  }

  function clearDesktopWidths() {
    try {
      localStorage.removeItem(DESKTOP_STORAGE_KEY);
    } catch (error) {}
  }

  function clearLibrarySessionStore() {
    try {
      sessionStorage.removeItem(RESIZER_SESSION_KEY);
    } catch (error) {}
  }

  function normalizeTableInlineWidths(table) {
    table.style.width = '';
    table.style.minWidth = '';
  }

  function getResizerConstructor() {
    if (!window.ColumnResizer) return null;
    return window.ColumnResizer.default || window.ColumnResizer;
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

  /**
   * fragment 스왑으로 테이블 DOM 이 교체되면 옛 ColumnResizer 는 detached 테이블을 참조한다.
   * 모듈 var(desktopResizer)는 load-once 라 리셋되지 않으므로, 새 테이블 init 전에 명시적으로 정리한다.
   * vendor(column-resizer.js)는 생성자에서 window resize 에 인스턴스별 onResize 를 등록하고 destroy() 로도
   * 이를 해제하지 않는다. onResize 는 인스턴스 안정 프로퍼티이므로 removeEventListener 로 직접 해제한다.
   */
  function destroyDesktopResizer() {
    detachDesktopResizeListener();
    if (desktopResizer) {
      if (typeof desktopResizer.onResize === 'function') {
        window.removeEventListener('resize', desktopResizer.onResize);
      }
      if (typeof desktopResizer.destroy === 'function') {
        try { desktopResizer.destroy(); } catch (error) {}
      }
    }
    desktopResizer = null;
    desktopResizeListener = null;
    resizerTable = null;
  }

  function initDesktopResizer(table) {
    // 같은 테이블에 이미 붙어 있으면 재생성하지 않음(동일 DOM 재init 멱등).
    if (desktopResizer && resizerTable === table) return;
    // 다른(옛) 테이블에 붙어 있던 인스턴스는 grip DOM·전역 리스너까지 정리 후 새로 생성.
    if (desktopResizer) destroyDesktopResizer();

    var ResizerCtor = getResizerConstructor();
    if (!ResizerCtor) return;

    clearLibrarySessionStore();
    desktopResizer = new ResizerCtor(table, {
      resizeMode: 'overflow',
      liveDrag: true,
      minWidth: 56,
      headerOnly: true,
      removePadding: false,
      serialize: false,
      draggingClass: 'measurement-col-resizer-active',
      gripInnerHtml: '<div class="measurement-col-resizer-grip"></div>',
      onResize: function () {
        applySchemaMinimums(table);
        saveDesktopWidths(collectCurrentWidths(table));
      }
    });
    resizerTable = table;

    desktopResizeListener = typeof desktopResizer.onResize === 'function' ? desktopResizer.onResize : null;
    isDesktopResizeListenerAttached = !!desktopResizeListener;

    applySchemaMinimums(table);
    saveDesktopWidths(collectCurrentWidths(table));
  }

  function applyDesktopState(table) {
    normalizeTableInlineWidths(table);
    applyWidthsToCols(table, loadDesktopWidths());
    initDesktopResizer(table);
    attachDesktopResizeListener();
    syncDesktopGripPositions();
  }

  function applyStaticTableState(table) {
    // 정적/모바일 모드: 리사이저를 완전히 정리(grip DOM + 전역 리스너)해 옛 테이블 잔여 참조를 제거.
    destroyDesktopResizer();
    normalizeTableInlineWidths(table);
    applyWidthsToCols(table, loadDesktopWidths());
    applySchemaMinimums(table);
  }

  function bindResetButton(table) {
    var button = document.getElementById('btn-reset-measurement-column-widths');
    if (!button || button.dataset.bound === '1') return;

    button.dataset.bound = '1';
    button.addEventListener('click', function () {
      clearDesktopWidths();
      normalizeTableInlineWidths(table);
      applyWidthsToCols(table, {});
      applySchemaMinimums(table);
      saveDesktopWidths(collectCurrentWidths(table));
      syncDesktopGripPositions();
    });
  }

  function syncViewportState(force) {
    var table = getTable();
    if (!table) return;

    var nextMode = canUseDesktopResize() ? 'desktop' : 'static';
    if (!force && nextMode === lastViewportMode) return;

    lastViewportMode = nextMode;
    if (nextMode === 'desktop') {
      applyDesktopState(table);
      return;
    }

    applyStaticTableState(table);
  }

  function onViewportResize() {
    clearTimeout(viewportTimer);
    viewportTimer = window.setTimeout(function () {
      syncViewportState(false);
    }, 120);
  }

  function init() {
    var table = getTable();
    if (!table) {
      // 새 fragment 에 표가 없거나(권한/비활성) 옛 표가 사라진 경우 잔여 리사이저 정리.
      if (desktopResizer) destroyDesktopResizer();
      return;
    }

    // 스왑으로 표가 교체됐다면(옛 인스턴스가 다른 표에 묶여 있으면) mode 재판정 전에 강제 재적용.
    if (desktopResizer && resizerTable !== table) {
      lastViewportMode = null;
    }

    bindResetButton(table);
    syncViewportState(true);
  }

  // 창 resize debounce 리스너는 전역이라 1회만 등록(스왑마다 누적 방지). 내부에서 현재 표를 조회.
  if (!window.__FOMS_MEAS_COLUMNS_RESIZE_BOUND) {
    window.__FOMS_MEAS_COLUMNS_RESIZE_BOUND = true;
    window.addEventListener('resize', onViewportResize);
  }

  // entry 동적 로드 대응 readyState 분기 + fragment 스왑 재초기화(리사이저 생명주기는 init 이 관리).
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  if (!window.__FOMS_MEAS_COLUMNS_BOUND) {
    window.__FOMS_MEAS_COLUMNS_BOUND = true;
    document.addEventListener('foms:erp-shell-fragment-swapped', init);
  }
})();

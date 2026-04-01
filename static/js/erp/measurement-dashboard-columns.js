(function () {
  'use strict';

  var TABLE_ID = 'measurement-dashboard-table';
  var STORAGE_KEY = 'foms.measurementDashboard.columnWidths.v1';
  var DESKTOP_BREAKPOINT = 992;
  var resizeState = null;
  var lastDesktopState = null;
  var viewportTimer = null;

  var MEASUREMENT_COLUMN_SCHEMA = {
    detail:           { defaultWidth: 70,  minWidth: 56,  resizable: true },
    customer:         { defaultWidth: 120, minWidth: 96,  resizable: true },
    orderer:          { defaultWidth: 110, minWidth: 90,  resizable: true },
    address:          { defaultWidth: 190, minWidth: 150, resizable: true },
    phone:            { defaultWidth: 130, minWidth: 110, resizable: true },
    measurement_date: { defaultWidth: 100, minWidth: 90,  resizable: true },
    meas_time:        { defaultWidth: 110, minWidth: 90,  resizable: true },
    product:          { defaultWidth: 190, minWidth: 150, resizable: true },
    manager:          { defaultWidth: 200, minWidth: 150, resizable: true }
  };

  function getTable() {
    return document.getElementById(TABLE_ID);
  }

  function isDesktopViewport() {
    return window.innerWidth > DESKTOP_BREAKPOINT;
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
    } catch (e) {}
  }

  function clearSavedWidths() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {}
  }

  function getColumnElements(table, colKey) {
    return {
      col: table.querySelector('colgroup col[data-col-key="' + colKey + '"]'),
      th: table.querySelector('thead th[data-col-key="' + colKey + '"]')
    };
  }

  function setColumnWidth(table, colKey, widthPx) {
    var schema = MEASUREMENT_COLUMN_SCHEMA[colKey];
    if (!schema) return;

    var nextWidth = Math.max(schema.minWidth, Math.round(widthPx));
    var columnEls = getColumnElements(table, colKey);
    if (!columnEls.col) return;

    columnEls.col.style.width = nextWidth + 'px';
    if (columnEls.th) {
      columnEls.th.style.width = nextWidth + 'px';
      columnEls.th.style.minWidth = nextWidth + 'px';
      columnEls.th.style.maxWidth = nextWidth + 'px';
    }
  }

  function applyWidthsToCols(table, savedWidths) {
    var cols = table.querySelectorAll('colgroup col[data-col-key]');
    cols.forEach(function (col) {
      var key = col.dataset.colKey;
      var schema = MEASUREMENT_COLUMN_SCHEMA[key];
      if (!schema) return;

      var width = savedWidths[key] !== undefined ? savedWidths[key] : schema.defaultWidth;
      setColumnWidth(table, key, width);
    });
  }

  function collectCurrentWidths(table) {
    var widths = {};
    var cols = table.querySelectorAll('colgroup col[data-col-key]');

    cols.forEach(function (col) {
      var key = col.dataset.colKey;
      var width = parseInt(col.style.width, 10);
      if (!isNaN(width)) {
        widths[key] = width;
      }
    });

    return widths;
  }

  function cleanupResize() {
    if (!resizeState) return;

    resizeState.table.classList.remove('col-resizing');
    document.body.classList.remove('col-resizing-active');
    document.removeEventListener('pointermove', onPointerMove);
    document.removeEventListener('pointerup', onPointerUpOrCancel);
    document.removeEventListener('pointercancel', onPointerUpOrCancel);
    resizeState = null;
  }

  function onPointerMove(event) {
    if (!resizeState) return;

    var dx = event.clientX - resizeState.startX;
    setColumnWidth(resizeState.table, resizeState.colKey, resizeState.startWidth + dx);
  }

  function onPointerUpOrCancel() {
    if (!resizeState) return;

    saveWidths(collectCurrentWidths(resizeState.table));
    cleanupResize();
  }

  function startResize(event, table) {
    if (!isDesktopViewport()) return;
    if (event.pointerType === 'mouse' && event.button !== 0) return;

    var handle = event.currentTarget;
    var th = handle.closest('th[data-col-key]');
    if (!th) return;

    var colKey = th.dataset.colKey;
    var schema = MEASUREMENT_COLUMN_SCHEMA[colKey];
    if (!schema || !schema.resizable) return;

    var columnEls = getColumnElements(table, colKey);
    if (!columnEls.col) return;

    event.preventDefault();
    event.stopPropagation();

    resizeState = {
      table: table,
      colKey: colKey,
      startX: event.clientX,
      startWidth: columnEls.col.offsetWidth || schema.defaultWidth
    };

    table.classList.add('col-resizing');
    document.body.classList.add('col-resizing-active');
    document.addEventListener('pointermove', onPointerMove);
    document.addEventListener('pointerup', onPointerUpOrCancel);
    document.addEventListener('pointercancel', onPointerUpOrCancel);
  }

  function bindResizeHandles(table) {
    var handles = table.querySelectorAll('thead th[data-col-key] .col-resize-handle');

    handles.forEach(function (handle) {
      if (handle.dataset.bound === '1') return;
      handle.dataset.bound = '1';

      handle.addEventListener('pointerdown', function (event) {
        startResize(event, table);
      });

      handle.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopPropagation();
      });

      handle.addEventListener('dblclick', function (event) {
        event.preventDefault();
        event.stopPropagation();

        var th = handle.closest('th[data-col-key]');
        if (!th) return;

        var colKey = th.dataset.colKey;
        var schema = MEASUREMENT_COLUMN_SCHEMA[colKey];
        if (!schema) return;

        setColumnWidth(table, colKey, schema.defaultWidth);
        saveWidths(collectCurrentWidths(table));
      });
    });
  }

  function bindResetButton(table) {
    var button = document.getElementById('btn-reset-measurement-column-widths');
    if (!button || button.dataset.bound === '1') return;

    button.dataset.bound = '1';
    button.addEventListener('click', function () {
      clearSavedWidths();
      applyWidthsToCols(table, {});
    });
  }

  function syncViewportState() {
    var table = getTable();
    if (!table) return;

    var isDesktop = isDesktopViewport();
    if (isDesktop === lastDesktopState) return;

    lastDesktopState = isDesktop;
    if (!isDesktop) {
      cleanupResize();
    }

    applyWidthsToCols(table, isDesktop ? loadSavedWidths() : {});
  }

  function init() {
    var table = getTable();
    if (!table) return;

    lastDesktopState = isDesktopViewport();
    applyWidthsToCols(table, lastDesktopState ? loadSavedWidths() : {});
    bindResizeHandles(table);
    bindResetButton(table);

    window.addEventListener('resize', function () {
      clearTimeout(viewportTimer);
      viewportTimer = window.setTimeout(syncViewportState, 120);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

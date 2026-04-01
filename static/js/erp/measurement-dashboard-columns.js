(function () {
  'use strict';

  var TABLE_ID = 'measurement-dashboard-table';
  var DESKTOP_BREAKPOINT = 992;
  var DESKTOP_POINTER_QUERY = '(hover: hover) and (pointer: fine)';
  var DESKTOP_STORAGE_KEY = 'foms.measurementDashboard.columnWidths.v2';
  var MOBILE_PRESET_STORAGE_KEY = 'foms.measurementDashboard.mobilePreset.v1';
  var DEFAULT_MOBILE_PRESET = 'default';
  var RESIZER_SESSION_KEY = TABLE_ID;

  var viewportTimer = null;
  var lastViewportMode = null;
  var desktopResizer = null;
  var desktopResizeListener = null;
  var isDesktopResizeListenerAttached = false;

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

  function getSchemaDefaultWidths() {
    var widths = {};
    Object.keys(MEASUREMENT_COLUMN_SCHEMA).forEach(function (key) {
      widths[key] = MEASUREMENT_COLUMN_SCHEMA[key].defaultWidth;
    });
    return widths;
  }

  function createMobilePreset(overrides) {
    var widths = getSchemaDefaultWidths();
    Object.keys(overrides || {}).forEach(function (key) {
      if (MEASUREMENT_COLUMN_SCHEMA[key]) {
        widths[key] = overrides[key];
      }
    });
    return widths;
  }

  var MOBILE_PRESETS = {
    compact: createMobilePreset({
      detail: 60,
      customer: 104,
      orderer: 96,
      address: 164,
      phone: 120,
      measurement_date: 92,
      meas_time: 92,
      product: 166,
      manager: 170
    }),
    default: getSchemaDefaultWidths(),
    wide: createMobilePreset({
      customer: 124,
      orderer: 116,
      address: 228,
      phone: 136,
      measurement_date: 104,
      meas_time: 116,
      product: 240,
      manager: 214
    })
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

  function loadMobilePreset() {
    try {
      var presetKey = localStorage.getItem(MOBILE_PRESET_STORAGE_KEY);
      return MOBILE_PRESETS[presetKey] ? presetKey : DEFAULT_MOBILE_PRESET;
    } catch (error) {
      return DEFAULT_MOBILE_PRESET;
    }
  }

  function saveMobilePreset(presetKey) {
    try {
      localStorage.setItem(MOBILE_PRESET_STORAGE_KEY, presetKey);
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

  function initDesktopResizer(table) {
    if (desktopResizer) return;

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
    updateMobilePresetButtons(loadMobilePreset());
  }

  function applyMobilePresetWidths(table, presetKey) {
    detachDesktopResizeListener();
    normalizeTableInlineWidths(table);
    applyWidthsToCols(table, MOBILE_PRESETS[presetKey] || MOBILE_PRESETS[DEFAULT_MOBILE_PRESET]);
    updateMobilePresetButtons(presetKey);
  }

  function setMobilePreset(table, presetKey) {
    var nextPreset = MOBILE_PRESETS[presetKey] ? presetKey : DEFAULT_MOBILE_PRESET;
    saveMobilePreset(nextPreset);
    applyMobilePresetWidths(table, nextPreset);
  }

  function updateMobilePresetButtons(activePreset) {
    var buttons = document.querySelectorAll('[data-measurement-mobile-preset]');
    buttons.forEach(function (button) {
      var isActive = button.dataset.measurementMobilePreset === activePreset;
      button.classList.toggle('is-active', isActive);
      button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
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

  function bindMobilePresetButtons(table) {
    var buttons = document.querySelectorAll('[data-measurement-mobile-preset]');
    buttons.forEach(function (button) {
      if (button.dataset.bound === '1') return;

      button.dataset.bound = '1';
      button.addEventListener('click', function () {
        setMobilePreset(table, button.dataset.measurementMobilePreset);
      });
    });
  }

  function syncViewportState(force) {
    var table = getTable();
    if (!table) return;

    var nextMode = canUseDesktopResize() ? 'desktop' : 'mobile';
    if (!force && nextMode === lastViewportMode) return;

    lastViewportMode = nextMode;
    if (nextMode === 'desktop') {
      applyDesktopState(table);
      return;
    }

    applyMobilePresetWidths(table, loadMobilePreset());
  }

  function init() {
    var table = getTable();
    if (!table) return;

    bindResetButton(table);
    bindMobilePresetButtons(table);
    syncViewportState(true);

    window.addEventListener('resize', function () {
      clearTimeout(viewportTimer);
      viewportTimer = window.setTimeout(function () {
        syncViewportState(false);
      }, 120);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

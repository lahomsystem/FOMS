/* ============================================================================
 * 도면 마법사 (Drawing Wizard) — 프론트 에디터
 *
 * 독립 페이지 에디터. 스테이지(논리 1478x1040) 위에 양식 폼 + 자유 객체(텍스트/
 * 이미지)를 배치하고, 상태를 structured_data['drawing_wizard']에 저장한다.
 * 내보내기는 html2canvas(scale=2)로 PNG 생성 → 다운로드 또는 기존 전달 API 재사용.
 *
 * 밴드: config/api → state/history → form render → objects → toolbar →
 *       save/load → export/transfer → init
 * ========================================================================== */
(function () {
  'use strict';

  if (window.__DWS_BOUND) { return; }
  window.__DWS_BOUND = true;

  /* ========================================================================
   * [1] config / api
   * ====================================================================== */
  var root = document.getElementById('dws-root');
  if (!root) { return; }

  var ORDER_ID = parseInt(root.getAttribute('data-order-id'), 10) || 0;
  var CONFIG = {};
  try {
    var cfgEl = document.getElementById('drawing-wizard-config');
    CONFIG = cfgEl ? (JSON.parse(cfgEl.textContent || '{}') || {}) : {};
  } catch (e) {
    console.warn('[dws] config parse 실패', e);
    CONFIG = {};
  }

  var API_BASE = '/api/orders/' + ORDER_ID;
  var HTML2CANVAS_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
  var STAGE_W = 1478;
  var STAGE_H = 1040;
  var ALLOWED_SIZES = [14, 17, 20, 24, 28];
  var CHECK_KEYS = ['d_site', 'd_double', 'd_order', 'p_prod', 'p_glass', 'p_light', 'p_handle', 'p_etc'];
  var PRESETS = { SR: '[SR]', EP: '[EP]', DOOR: '[DOOR]', ROD: '[옷봉]' };
  var _html2canvasPromise = null;

  /**
   * fetch → {status, data} 로 정규화. 파싱 실패도 안전 폴백.
   * @param {string} url
   * @param {Object} [opts]
   * @returns {Promise<{status:number, data:Object}>}
   */
  function jsonFetch(url, opts) {
    opts = opts || {};
    opts.credentials = 'same-origin';
    return fetch(url, opts).then(function (resp) {
      return resp.json().then(
        function (data) { return { status: resp.status, data: data || {} }; },
        function () { return { status: resp.status, data: { success: false, message: '응답을 해석할 수 없습니다.' } }; }
      );
    });
  }

  /** html2canvas lazy-load (image-export.js 패턴 복제, perf guard G2). */
  function ensureHtml2canvas() {
    if (typeof window.html2canvas === 'function') { return Promise.resolve(); }
    if (_html2canvasPromise) { return _html2canvasPromise; }
    _html2canvasPromise = new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = HTML2CANVAS_SRC;
      s.async = true;
      s.onload = function () {
        if (typeof window.html2canvas === 'function') { resolve(); }
        else { _html2canvasPromise = null; reject(new Error('html2canvas loaded but global missing')); }
      };
      s.onerror = function () { _html2canvasPromise = null; reject(new Error('html2canvas load failed')); };
      document.head.appendChild(s);
    });
    return _html2canvasPromise;
  }

  function viewUrl(key) { return API_BASE + '/drawing-wizard/asset-raw?key=' + encodeURIComponent(key); }
  function rid(prefix) { return prefix + Math.random().toString(36).slice(2, 8) + Date.now().toString(36).slice(-3); }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function num(v, def) { return (typeof v === 'number' && isFinite(v)) ? v : (def || 0); }

  /* ========================================================================
   * [2] state / history
   * ====================================================================== */
  var state = { v: 1, sheets: [] };
  var current = 0;
  var dirty = false;
  var baseUpdatedAt = null;
  var canSave = !!CONFIG.can_save;
  var defaults = {};
  var customerName = '';
  var selected = null;
  var zoom = 1;
  var imageRatioLock = true;
  var undoStack = [];
  var redoStack = [];
  var lastArrowUndoTs = 0;

  function currentSheet() { return state.sheets[current]; }
  function cloneSheet(s) { return JSON.parse(JSON.stringify(s)); }
  function findObj(id) {
    var objs = currentSheet().objects || [];
    for (var i = 0; i < objs.length; i++) { if (objs[i].id === id) { return objs[i]; } }
    return null;
  }

  function newSheet(name, d) { return { id: rid('s-'), name: name, form: cloneForm(d), objects: [] }; }

  function cloneForm(d) {
    d = d || {};
    var f = {};
    Object.keys(d).forEach(function (k) { if (k !== 'checks') { f[k] = (d[k] == null) ? '' : String(d[k]); } });
    var ck = d.checks || {};
    f.checks = {};
    CHECK_KEYS.forEach(function (k) { f.checks[k] = !!ck[k]; });
    return f;
  }

  function recordUndo() {
    undoStack.push(cloneSheet(currentSheet()));
    if (undoStack.length > 50) { undoStack.shift(); }
    redoStack.length = 0;
  }

  function undo() {
    if (!undoStack.length) { return; }
    redoStack.push(cloneSheet(currentSheet()));
    state.sheets[current] = undoStack.pop();
    deselect();
    renderForm();
    renderObjects();
    markDirty();
  }

  function redo() {
    if (!redoStack.length) { return; }
    undoStack.push(cloneSheet(currentSheet()));
    state.sheets[current] = redoStack.pop();
    deselect();
    renderForm();
    renderObjects();
    markDirty();
  }

  function markDirty() { dirty = true; updateSaveState(); }

  /* ========================================================================
   * [3] form render
   * ====================================================================== */
  var els = {};

  function cacheDom() {
    els.customer = document.getElementById('dws-customer');
    els.readonlyBanner = document.getElementById('dws-readonly-banner');
    els.tabbar = document.getElementById('dws-tabbar');
    els.canvas = document.getElementById('dws-canvas');
    els.wrap = document.getElementById('dws-stage-wrap');
    els.stage = document.getElementById('dws-stage');
    els.form = document.getElementById('dws-form');
    els.objects = document.getElementById('dws-objects');
    els.logoCell = document.getElementById('dws-logo-cell');
    els.logoImg = document.getElementById('dws-logo-img');
    els.logoHint = document.getElementById('dws-logo-hint');
    els.logoPopup = document.getElementById('dws-logo-popup');
    els.saveBtn = document.getElementById('dws-btn-save');
    els.zoomRange = document.getElementById('dws-zoom-range');
    els.zoomLabel = document.getElementById('dws-zoom-label');
    els.fileInput = document.getElementById('dws-file-input');
    els.presetMenu = document.getElementById('dws-preset-menu');
    els.exportMenu = document.getElementById('dws-export-menu');
    els.mt = document.getElementById('dws-minitoolbar');
    els.mtText = document.getElementById('dws-mt-text');
    els.mtImage = document.getElementById('dws-mt-image');
    els.mtSize = document.getElementById('dws-mt-size');
    els.mtBold = document.getElementById('dws-mt-bold');
    els.mtAlign = document.getElementById('dws-mt-align');
    els.mtRatio = document.getElementById('dws-mt-ratio');
    els.transferDialog = document.getElementById('dws-transfer-dialog');
    els.transferNote = document.getElementById('dws-transfer-note');
    els.transferMode = document.getElementById('dws-transfer-mode');
    els.transferSubmit = document.getElementById('dws-transfer-submit');
    els.toastHost = document.getElementById('dws-toast-host');
    els.mobileNotice = document.getElementById('dws-mobile-notice');
  }

  function formCells() { return Array.prototype.slice.call(els.form.querySelectorAll('[data-dws-form-key]')); }
  function checkEls() { return Array.prototype.slice.call(els.form.querySelectorAll('[data-dws-check]')); }

  function renderForm() {
    var form = currentSheet().form || {};
    formCells().forEach(function (el) {
      var k = el.getAttribute('data-dws-form-key');
      el.textContent = (form[k] != null) ? String(form[k]) : '';
    });
    renderChecks();
    renderLogo(form.logo);
  }

  function renderChecks() {
    var checks = (currentSheet().form || {}).checks || {};
    checkEls().forEach(function (el) {
      var k = el.getAttribute('data-dws-check');
      var on = !!checks[k];
      el.textContent = on ? '✓' : '';
      el.classList.toggle('dws-check-on', on);
    });
  }

  function renderLogo(logo) {
    if (logo === 'haud') {
      els.logoImg.src = '/static/images/haud-logo.png';
      els.logoImg.hidden = false; els.logoHint.hidden = true;
    } else if (logo === 'lahom') {
      els.logoImg.src = '/static/images/lahom-logo.png';
      els.logoImg.hidden = false; els.logoHint.hidden = true;
    } else {
      els.logoImg.hidden = true; els.logoImg.removeAttribute('src');
      els.logoHint.hidden = !canSave;
    }
  }

  function syncEditable(el) {
    var k = el.getAttribute('data-dws-form-key');
    if (!k) { return; }
    currentSheet().form[k] = el.textContent;
    markDirty();
  }

  function toggleCheck(key) {
    if (!canSave) { return; }
    recordUndo();
    var checks = currentSheet().form.checks || (currentSheet().form.checks = {});
    checks[key] = !checks[key];
    renderChecks();
    markDirty();
  }

  /** 편집 리스너 배선(저장 권한 있을 때만). */
  function wireFormEditing() {
    if (!canSave) { return; }
    if (els.form.getAttribute('data-dws-wired') === '1') { return; }
    els.form.setAttribute('data-dws-wired', '1');
    formCells().forEach(function (el) {
      el.setAttribute('contenteditable', 'plaintext-only');
      el.addEventListener('focus', function () { el._dwsPushed = false; });
      el.addEventListener('input', function () {
        if (!el._dwsPushed) { recordUndo(); el._dwsPushed = true; }
        syncEditable(el);
      });
    });
    checkEls().forEach(function (el) {
      el.addEventListener('click', function () { toggleCheck(el.getAttribute('data-dws-check')); });
    });
    els.logoCell.addEventListener('click', function (e) { e.stopPropagation(); openLogoPopup(); });
  }

  /* ========================================================================
   * [4] objects render / interactions
   * ====================================================================== */
  function objEl(id) { return els.objects.querySelector('[data-obj-id="' + id + '"]'); }

  function renderObjects() {
    els.objects.innerHTML = '';
    (currentSheet().objects || []).forEach(function (o) {
      els.objects.appendChild(o.type === 'text' ? buildTextEl(o) : buildImageEl(o));
    });
    applySelectionStyles();
  }

  function appendHandles(el, isImage) {
    ['nw', 'ne', 'sw', 'se'].forEach(function (pos) {
      var h = document.createElement('div');
      h.className = 'dws-handle dws-handle-' + pos + ' dws-ui';
      if (pos === 'se') { h.className += ' dws-resize-handle'; }
      el.appendChild(h);
    });
  }

  function buildTextEl(o) {
    var el = document.createElement('div');
    el.className = 'dws-obj dws-obj-text';
    el.setAttribute('data-obj-id', o.id);
    el.style.left = o.x + 'px';
    el.style.top = o.y + 'px';
    el.style.width = o.w + 'px';
    el.style.fontSize = o.size + 'px';
    el.style.color = o.color;
    el.style.fontWeight = o.bold ? '700' : '400';
    el.style.textAlign = o.align;
    el.style.zIndex = '20';
    el.textContent = o.text;
    appendHandles(el, false);
    if (canSave) {
      makeDraggable(el, o);
      wireResize(el, o);
      el.addEventListener('dblclick', function (e) { e.stopPropagation(); startEditText(o.id, false); });
    }
    return el;
  }

  function buildImageEl(o) {
    var el = document.createElement('div');
    el.className = 'dws-obj dws-obj-image';
    el.setAttribute('data-obj-id', o.id);
    el.style.left = o.x + 'px';
    el.style.top = o.y + 'px';
    el.style.width = o.w + 'px';
    el.style.height = o.h + 'px';
    el.style.zIndex = '10';
    var img = document.createElement('img');
    img.src = viewUrl(o.key);
    img.alt = '';
    img.draggable = false;
    el.appendChild(img);
    appendHandles(el, true);
    if (canSave) { makeDraggable(el, o); wireResize(el, o); }
    return el;
  }

  function positionObjEl(o) {
    var el = objEl(o.id);
    if (!el) { return; }
    el.style.left = o.x + 'px';
    el.style.top = o.y + 'px';
    el.style.width = o.w + 'px';
    if (o.type === 'image') { el.style.height = o.h + 'px'; }
  }

  function makeDraggable(el, o) {
    el.addEventListener('pointerdown', function (e) {
      if (e.target && e.target.classList && e.target.classList.contains('dws-resize-handle')) { return; }
      if (el.classList.contains('dws-editing')) { return; }
      if (e.button !== 0) { return; }
      selectObject(o.id);
      var sx = e.clientX, sy = e.clientY, ox = o.x, oy = o.y, moved = false;
      try { el.setPointerCapture(e.pointerId); } catch (_) { /* noop */ }
      function mv(ev) {
        var dx = (ev.clientX - sx) / zoom, dy = (ev.clientY - sy) / zoom;
        if (!moved && (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5)) { recordUndo(); moved = true; }
        if (!moved) { return; }
        o.x = Math.round(ox + dx);
        o.y = Math.round(oy + dy);
        el.style.left = o.x + 'px';
        el.style.top = o.y + 'px';
        positionMiniToolbar(o.id);
      }
      function up() {
        el.removeEventListener('pointermove', mv);
        el.removeEventListener('pointerup', up);
        try { el.releasePointerCapture(e.pointerId); } catch (_) { /* noop */ }
        if (moved) { markDirty(); }
      }
      el.addEventListener('pointermove', mv);
      el.addEventListener('pointerup', up);
    });
  }

  function wireResize(el, o) {
    var h = el.querySelector('.dws-resize-handle');
    if (!h) { return; }
    var isText = (o.type === 'text');
    h.addEventListener('pointerdown', function (e) {
      e.stopPropagation();
      if (e.button !== 0) { return; }
      selectObject(o.id);
      var sx = e.clientX, sy = e.clientY, ow = o.w, oh = o.h, aspect = ow / (oh || 1), moved = false;
      try { h.setPointerCapture(e.pointerId); } catch (_) { /* noop */ }
      function mv(ev) {
        if (!moved) { recordUndo(); moved = true; }
        var dx = (ev.clientX - sx) / zoom, dy = (ev.clientY - sy) / zoom;
        if (isText) {
          var tw = Math.max(40, Math.round(ow + dx));
          o.w = tw;
          el.style.width = tw + 'px';
          positionMiniToolbar(o.id);
          return;
        }
        var lock = ev.shiftKey ? !imageRatioLock : imageRatioLock;
        var w = Math.max(20, Math.round(ow + dx));
        var hgt = lock ? Math.max(20, Math.round(w / aspect)) : Math.max(20, Math.round(oh + dy));
        o.w = w; o.h = hgt;
        el.style.width = w + 'px';
        el.style.height = hgt + 'px';
        positionMiniToolbar(o.id);
      }
      function up() {
        h.removeEventListener('pointermove', mv);
        h.removeEventListener('pointerup', up);
        try { h.releasePointerCapture(e.pointerId); } catch (_) { /* noop */ }
        if (moved) { markDirty(); }
      }
      h.addEventListener('pointermove', mv);
      h.addEventListener('pointerup', up);
    });
  }

  function selectObject(id) {
    selected = id;
    applySelectionStyles();
    showMiniToolbar(id);
  }

  function deselect() {
    selected = null;
    applySelectionStyles();
    hideMiniToolbar();
    hideLogoPopup();
  }

  function applySelectionStyles() {
    Array.prototype.forEach.call(els.objects.querySelectorAll('.dws-obj'), function (el) {
      el.classList.toggle('dws-selected', el.getAttribute('data-obj-id') === selected);
    });
  }

  function deleteSelected() {
    if (!canSave || !selected) { return; }
    recordUndo();
    var objs = currentSheet().objects;
    var i = -1;
    objs.some(function (o, idx) { if (o.id === selected) { i = idx; return true; } return false; });
    if (i >= 0) { objs.splice(i, 1); }
    deselect();
    markDirty();
    renderObjects();
  }

  function addTextObject(x, y) {
    if (!canSave) { return; }
    recordUndo();
    var o = {
      id: rid('o-'), type: 'text', x: Math.round(x), y: Math.round(y), w: 220,
      text: '', size: 20, color: '#000000', bold: false, align: 'left'
    };
    currentSheet().objects.push(o);
    markDirty();
    renderObjects();
    selectObject(o.id);
    startEditText(o.id, true);
  }

  function addPreset(kind) {
    if (!canSave) { return; }
    var label = PRESETS[kind];
    if (!label) { return; }
    recordUndo();
    var n = currentSheet().objects.length;
    var o = {
      id: rid('o-'), type: 'text', x: 340 + (n % 3) * 30, y: 95 + (n % 6) * 46, w: 220,
      text: label + '\n', size: 20, color: '#000000', bold: true, align: 'left'
    };
    currentSheet().objects.push(o);
    markDirty();
    renderObjects();
    selectObject(o.id);
    startEditText(o.id, true);
  }

  function startEditText(id, skipUndo) {
    if (!canSave) { return; }
    var o = findObj(id), el = objEl(id);
    if (!o || !el) { return; }
    if (!skipUndo) { recordUndo(); }
    el.setAttribute('contenteditable', 'plaintext-only');
    el.classList.add('dws-editing');
    el.focus();
    var range = document.createRange();
    range.selectNodeContents(el);
    range.collapse(false);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    el.addEventListener('blur', function onBlur() {
      el.removeEventListener('blur', onBlur);
      el.removeAttribute('contenteditable');
      el.classList.remove('dws-editing');
      o.text = el.textContent;
      if (String(o.text).trim() === '') {
        var objs = currentSheet().objects, i = -1;
        objs.some(function (x2, idx) { if (x2.id === o.id) { i = idx; return true; } return false; });
        if (i >= 0) { objs.splice(i, 1); }
        if (selected === o.id) { deselect(); }
        renderObjects();
      } else {
        markDirty();
      }
    });
  }

  function uploadAsset(file) {
    var fd = new FormData();
    fd.append('file', file, file.name || ('paste-' + Date.now() + '.png'));
    return jsonFetch(API_BASE + '/drawing-wizard/asset', { method: 'POST', body: fd });
  }

  function addImageFromFile(file) {
    if (!canSave || !file) { return; }
    uploadAsset(file).then(function (r) {
      if (r.status !== 200 || !r.data || !r.data.success || !r.data.data) {
        toast((r.data && r.data.message) || '이미지 업로드 실패');
        return;
      }
      var key = r.data.data.key;
      var url = viewUrl(key);
      var img = new Image();
      img.onload = function () {
        var nw = img.naturalWidth || 900, nh = img.naturalHeight || 600;
        var w = Math.min(900, nw);
        var h = Math.round(w * nh / nw) || Math.round(w * 0.66);
        recordUndo();
        var o = {
          id: rid('o-'), type: 'image',
          x: Math.round((STAGE_W - w) / 2),
          y: Math.round(70 + (730 - h) / 2),
          w: w, h: h, key: key, natural_w: nw, natural_h: nh
        };
        if (o.y < 70) { o.y = 70; }
        currentSheet().objects.push(o);
        markDirty();
        renderObjects();
        selectObject(o.id);
      };
      img.onerror = function () { toast('이미지를 불러오지 못했습니다.'); };
      img.src = url;
    }).catch(function (err) { console.warn('[dws] asset upload', err); toast('이미지 업로드 오류'); });
  }

  /* ========================================================================
   * [5] toolbar (앱바 · 미니툴바 · 탭 · 줌 · 로고팝업 · 메뉴)
   * ====================================================================== */
  function showMiniToolbar(id) {
    if (!canSave) { hideMiniToolbar(); return; }
    var o = findObj(id);
    if (!o) { hideMiniToolbar(); return; }
    els.mtText.hidden = (o.type !== 'text');
    els.mtImage.hidden = (o.type !== 'image');
    els.mt.hidden = false;
    if (o.type === 'text') { syncTextToolbar(o); } else { syncImageToolbar(o); }
    positionMiniToolbar(id);
  }

  function hideMiniToolbar() { els.mt.hidden = true; }

  function positionMiniToolbar(id) {
    if (els.mt.hidden) { return; }
    var el = objEl(id);
    if (!el) { return; }
    var rect = el.getBoundingClientRect();
    var top = rect.top - els.mt.offsetHeight - 8;
    if (top < 8) { top = rect.bottom + 8; }
    var left = clamp(rect.left, 8, window.innerWidth - els.mt.offsetWidth - 8);
    els.mt.style.left = left + 'px';
    els.mt.style.top = top + 'px';
  }

  function syncTextToolbar(o) {
    els.mtSize.value = String(o.size);
    Array.prototype.forEach.call(els.mtText.querySelectorAll('.dws-swatch'), function (sw) {
      sw.classList.toggle('dws-active', sw.getAttribute('data-color').toLowerCase() === String(o.color).toLowerCase());
    });
    els.mtBold.classList.toggle('dws-active', !!o.bold);
    els.mtAlign.textContent = (o.align === 'center') ? '중' : '좌';
    els.mtAlign.classList.toggle('dws-active', o.align === 'center');
  }

  function syncImageToolbar() {
    els.mtRatio.textContent = '비율고정: ' + (imageRatioLock ? '켬' : '끔');
  }

  function updateSelectedText(patch) {
    var o = findObj(selected);
    if (!o || o.type !== 'text') { return; }
    recordUndo();
    Object.keys(patch).forEach(function (k) { o[k] = patch[k]; });
    renderObjects();
    markDirty();
    selectObject(o.id);
  }

  function renderTabs() {
    els.tabbar.innerHTML = '';
    state.sheets.forEach(function (s, i) {
      var tab = document.createElement('button');
      tab.type = 'button';
      tab.className = 'dws-tab' + (i === current ? ' dws-tab-active' : '');
      var label = document.createElement('span');
      label.textContent = s.name;
      tab.appendChild(label);
      tab.addEventListener('click', function () { switchSheet(i); });
      if (canSave) {
        tab.addEventListener('dblclick', function (e) { e.preventDefault(); renameSheet(i); });
        var x = document.createElement('span');
        x.className = 'dws-tab-x';
        x.textContent = '×';
        x.title = '삭제';
        x.addEventListener('click', function (e) { e.stopPropagation(); deleteSheet(i); });
        tab.appendChild(x);
      }
      els.tabbar.appendChild(tab);
    });
    if (canSave && state.sheets.length < 10) {
      var add = document.createElement('button');
      add.type = 'button';
      add.className = 'dws-tab-add';
      add.textContent = '+ 시트';
      add.addEventListener('click', addSheet);
      els.tabbar.appendChild(add);
    }
  }

  function switchSheet(i) {
    if (i === current || i < 0 || i >= state.sheets.length) { return; }
    if (document.activeElement && document.activeElement.blur) { document.activeElement.blur(); }
    current = i;
    deselect();
    undoStack.length = 0;
    redoStack.length = 0;
    renderTabs();
    renderForm();
    renderObjects();
  }

  function addSheet() {
    if (!canSave) { return; }
    if (state.sheets.length >= 10) { toast('시트는 최대 10장까지 만들 수 있습니다.'); return; }
    state.sheets.push(newSheet('도면 ' + (state.sheets.length + 1), defaults));
    current = state.sheets.length - 1;
    undoStack.length = 0;
    redoStack.length = 0;
    deselect();
    markDirty();
    renderTabs();
    renderForm();
    renderObjects();
  }

  function renameSheet(i) {
    if (!canSave) { return; }
    var name = prompt('시트 이름', state.sheets[i].name);
    if (name == null) { return; }
    name = name.trim().slice(0, 50);
    if (!name) { return; }
    state.sheets[i].name = name;
    markDirty();
    renderTabs();
  }

  function deleteSheet(i) {
    if (!canSave) { return; }
    if (state.sheets.length <= 1) { toast('최소 1개의 시트가 필요합니다.'); return; }
    if (!confirm('시트 "' + state.sheets[i].name + '"를 삭제할까요?')) { return; }
    state.sheets.splice(i, 1);
    if (current >= state.sheets.length) { current = state.sheets.length - 1; }
    else if (i < current) { current -= 1; }
    undoStack.length = 0;
    redoStack.length = 0;
    deselect();
    markDirty();
    renderTabs();
    renderForm();
    renderObjects();
  }

  function fitZoom() {
    var avail = els.canvas.clientWidth - 48;
    var z = Math.min(1, avail / STAGE_W);
    if (!isFinite(z) || z <= 0) { z = 1; }
    setZoom(z);
  }

  function setZoom(z) {
    zoom = z;
    els.stage.style.setProperty('--dws-zoom', String(z));
    els.wrap.style.width = (STAGE_W * z) + 'px';
    els.wrap.style.height = (STAGE_H * z) + 'px';
    var pct = Math.round(z * 100);
    els.zoomRange.value = String(clamp(pct, 50, 150));
    els.zoomLabel.textContent = pct + '%';
    if (selected) { positionMiniToolbar(selected); }
  }

  function openLogoPopup() {
    if (!canSave) { return; }
    var rect = els.logoCell.getBoundingClientRect();
    els.logoPopup.hidden = false;
    els.logoPopup.style.left = clamp(rect.left, 8, window.innerWidth - 140) + 'px';
    els.logoPopup.style.top = clamp(rect.top, 8, window.innerHeight - 140) + 'px';
  }

  function hideLogoPopup() { if (els.logoPopup) { els.logoPopup.hidden = true; } }

  function setLogo(v) {
    if (!canSave) { return; }
    recordUndo();
    currentSheet().form.logo = v;
    renderLogo(v);
    markDirty();
  }

  function toggleMenu(menu) {
    var willShow = menu.hidden;
    closeMenus();
    menu.hidden = !willShow;
  }

  function closeMenus() {
    if (els.presetMenu) { els.presetMenu.hidden = true; }
    if (els.exportMenu) { els.exportMenu.hidden = true; }
  }

  function toast(msg) {
    var t = document.createElement('div');
    t.className = 'dws-toast';
    t.textContent = String(msg || '');
    els.toastHost.appendChild(t);
    requestAnimationFrame(function () { t.classList.add('dws-toast-show'); });
    setTimeout(function () {
      t.classList.remove('dws-toast-show');
      setTimeout(function () { if (t.parentNode) { t.parentNode.removeChild(t); } }, 240);
    }, 2600);
  }

  function updateSaveState() {
    if (!els.saveBtn) { return; }
    els.saveBtn.classList.toggle('dws-dirty', !!dirty);
    els.saveBtn.textContent = dirty ? '저장 *' : '저장';
  }

  function applyPermissions() {
    Array.prototype.forEach.call(document.querySelectorAll('.dws-edit-ctl'), function (el) {
      if (canSave) { el.classList.remove('dws-disabled'); if ('disabled' in el) { el.disabled = false; } }
      else { el.classList.add('dws-disabled'); if ('disabled' in el) { el.disabled = true; } }
    });
    if (els.fileInput) { els.fileInput.disabled = !canSave; }
    els.readonlyBanner.hidden = canSave;
  }

  /* ========================================================================
   * [6] save / load
   * ====================================================================== */
  function serializeObj(o) {
    if (o.type === 'image') {
      return {
        id: o.id, type: 'image',
        x: clamp(Math.round(o.x), -2000, 4000),
        y: clamp(Math.round(o.y), -2000, 4000),
        w: clamp(Math.round(o.w), 1, 3000),
        h: clamp(Math.round(o.h), 1, 3000),
        key: o.key, natural_w: num(o.natural_w, 0), natural_h: num(o.natural_h, 0)
      };
    }
    return {
      id: o.id, type: 'text',
      x: clamp(Math.round(o.x), -2000, 4000),
      y: clamp(Math.round(o.y), -2000, 4000),
      w: clamp(Math.round(o.w), 1, 3000),
      text: String(o.text || ''),
      size: (ALLOWED_SIZES.indexOf(o.size) >= 0) ? o.size : 20,
      color: /^#[0-9a-fA-F]{6}$/.test(o.color) ? o.color : '#000000',
      bold: !!o.bold,
      align: (o.align === 'center') ? 'center' : 'left'
    };
  }

  function serializeForm(f) {
    f = f || {};
    var o = {};
    Object.keys(f).forEach(function (k) { if (k !== 'checks') { o[k] = (f[k] == null) ? '' : String(f[k]); } });
    o.checks = {};
    var ck = f.checks || {};
    Object.keys(ck).forEach(function (k) { o.checks[k] = !!ck[k]; });
    return o;
  }

  function serializeState() {
    return {
      v: 1,
      sheets: state.sheets.map(function (s) {
        return { id: s.id, name: s.name, form: serializeForm(s.form), objects: (s.objects || []).map(serializeObj) };
      })
    };
  }

  function mergeFormDefaults(saved) {
    var base = {};
    var d = defaults || {};
    Object.keys(d).forEach(function (k) { if (k !== 'checks') { base[k] = d[k]; } });
    saved = saved || {};
    Object.keys(saved).forEach(function (k) { if (k !== 'checks') { base[k] = saved[k]; } });
    var checks = {}, dk = d.checks || {}, sk = saved.checks || {};
    CHECK_KEYS.forEach(function (k) { checks[k] = (k in sk) ? !!sk[k] : !!dk[k]; });
    base.checks = checks;
    return base;
  }

  function normalizeObj(o) {
    if (o.type === 'image') {
      return {
        id: o.id || rid('o-'), type: 'image',
        x: num(o.x), y: num(o.y), w: num(o.w, 200), h: num(o.h, 150),
        key: o.key || '', natural_w: num(o.natural_w, 0), natural_h: num(o.natural_h, 0)
      };
    }
    return {
      id: o.id || rid('o-'), type: 'text',
      x: num(o.x), y: num(o.y), w: num(o.w, 220),
      text: String(o.text || ''),
      size: (ALLOWED_SIZES.indexOf(o.size) >= 0) ? o.size : 20,
      color: /^#[0-9a-fA-F]{6}$/.test(o.color) ? o.color : '#000000',
      bold: !!o.bold,
      align: (o.align === 'center') ? 'center' : 'left'
    };
  }

  function normalizeState(st) {
    var sheets = ((st && st.sheets) || []).map(function (s) {
      return {
        id: s.id || rid('s-'),
        name: s.name || '도면',
        form: serializeForm(mergeFormDefaults(s.form)),
        objects: (s.objects || [])
          .filter(function (o) { return o && (o.type === 'text' || o.type === 'image'); })
          .map(normalizeObj)
      };
    });
    if (!sheets.length) { sheets = [newSheet('도면 1', defaults)]; }
    return { v: 1, sheets: sheets };
  }

  function load() {
    jsonFetch(API_BASE + '/drawing-wizard', { headers: { 'Accept': 'application/json' } }).then(function (r) {
      if (r.status !== 200 || !r.data || !r.data.success || !r.data.data) {
        toast((r.data && r.data.message) || '불러오기에 실패했습니다.');
        return;
      }
      var d = r.data.data;
      canSave = !!d.can_save;
      defaults = d.defaults || {};
      customerName = d.customer_name || customerName;
      els.customer.textContent = '(' + customerName + ')';
      if (d.state && d.state.sheets && d.state.sheets.length) {
        state = normalizeState(d.state);
        baseUpdatedAt = d.state.updated_at || null;
      } else {
        state = { v: 1, sheets: [newSheet('도면 1', defaults)] };
        baseUpdatedAt = null;
      }
      current = 0;
      undoStack.length = 0;
      redoStack.length = 0;
      dirty = false;
      selected = null;
      applyPermissions();
      wireFormEditing();
      renderTabs();
      renderForm();
      renderObjects();
      updateSaveState();
      fitZoom();
    }, function (err) { console.warn('[dws] load', err); toast('불러오기 오류'); });
  }

  function handleConflict(cdata) {
    var name = (cdata && cdata.server_updated_by_name) || '다른 사용자';
    var ok = confirm(
      '다른 사용자(' + name + ')가 먼저 저장했습니다.\n\n' +
      '[확인] 서버 버전을 다시 불러옵니다.\n' +
      '[취소] 내 버전을 유지합니다(다시 저장하면 서버 내용을 덮어씁니다).'
    );
    if (ok) {
      load();
    } else {
      baseUpdatedAt = (cdata && cdata.server_updated_at) || baseUpdatedAt;
      toast('내 버전을 유지합니다. 다시 저장하면 덮어씁니다.');
    }
  }

  function save() {
    if (!canSave) { return; }
    if (document.activeElement && document.activeElement.blur) { document.activeElement.blur(); }
    var body = { state: serializeState(), base_updated_at: baseUpdatedAt };
    els.saveBtn.disabled = true;
    jsonFetch(API_BASE + '/drawing-wizard', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    }).then(function (r) {
      els.saveBtn.disabled = false;
      if (r.status === 200 && r.data && r.data.success) {
        baseUpdatedAt = (r.data.data && r.data.data.updated_at) || baseUpdatedAt;
        dirty = false;
        updateSaveState();
        toast('저장됨');
      } else if (r.status === 409) {
        handleConflict(r.data);
      } else {
        toast((r.data && r.data.message) || ('저장 실패 (' + r.status + ')'));
      }
    }, function (err) {
      els.saveBtn.disabled = false;
      console.warn('[dws] save', err);
      toast('저장 오류');
    });
  }

  /* ========================================================================
   * [7] export / transfer
   * ====================================================================== */
  function exportFilename() {
    var safe = function (s) { return String(s || '').replace(/[\\/:*?"<>|\n\r]/g, '_').trim() || '무제'; };
    return '도면_' + safe(customerName) + '_' + ORDER_ID + '_' + safe(currentSheet().name) + '.png';
  }

  /** 내보내기 준비(선택 해제 + chrome 숨김 + 줌 1.0) → html2canvas → 원복. */
  function withExportMode() {
    if (document.activeElement && document.activeElement.blur) { document.activeElement.blur(); }
    var prevZoom = zoom;
    deselect();
    root.classList.add('dws-exporting');
    setZoom(1);
    return ensureHtml2canvas().then(function () {
      return window.html2canvas(els.stage, { scale: 2, backgroundColor: '#ffffff', useCORS: true, logging: false });
    }).then(function (canvas) {
      root.classList.remove('dws-exporting');
      setZoom(prevZoom);
      return canvas;
    }).catch(function (err) {
      root.classList.remove('dws-exporting');
      setZoom(prevZoom);
      throw err;
    });
  }

  function exportPng() {
    closeMenus();
    withExportMode().then(function (cv) {
      cv.toBlob(function (blob) {
        if (!blob) { toast('PNG 생성에 실패했습니다.'); return; }
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = exportFilename();
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
        toast('PNG를 저장했습니다.');
      }, 'image/png');
    }).catch(function (err) {
      console.warn('[dws] export png', err);
      toast('내보내기 실패: ' + ((err && err.message) || '알 수 없는 오류'));
    });
  }

  function openTransferDialog() {
    if (!canSave) { return; }
    closeMenus();
    if (els.transferDialog.showModal) {
      try { els.transferDialog.showModal(); } catch (_) { els.transferDialog.setAttribute('open', ''); }
    } else {
      els.transferDialog.setAttribute('open', '');
    }
  }

  function closeTransferDialog() {
    if (els.transferDialog.close) {
      try { els.transferDialog.close(); } catch (_) { els.transferDialog.removeAttribute('open'); }
    } else {
      els.transferDialog.removeAttribute('open');
    }
  }

  function doTransfer() {
    if (!canSave) { return; }
    var note = els.transferNote.value || '';
    var mode = els.transferMode.value || 'APPEND';
    els.transferSubmit.disabled = true;
    withExportMode().then(function (cv) {
      cv.toBlob(function (blob) {
        if (!blob) { els.transferSubmit.disabled = false; toast('PNG 생성 실패'); return; }
        var fd = new FormData();
        fd.append('file', blob, exportFilename());
        jsonFetch(API_BASE + '/drawing-gateway-upload', { method: 'POST', body: fd }).then(function (up) {
          if (up.status !== 200 || !up.data || !up.data.success || !up.data.file) {
            els.transferSubmit.disabled = false;
            toast((up.data && up.data.message) || '업로드 실패');
            return;
          }
          var f = up.data.file;
          jsonFetch(API_BASE + '/transfer-drawing', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ note: note, mode: mode, files: [{ key: f.key, filename: f.filename }] })
          }).then(function (tr) {
            els.transferSubmit.disabled = false;
            if (tr.status === 200 && tr.data && tr.data.success) {
              toast(tr.data.message || '도면이 전달되었습니다.');
              closeTransferDialog();
            } else {
              toast((tr.data && tr.data.message) || '전달 실패');
            }
          }, function (err) { els.transferSubmit.disabled = false; console.warn('[dws] transfer', err); toast('전달 오류'); });
        }, function (err) { els.transferSubmit.disabled = false; console.warn('[dws] upload', err); toast('업로드 오류'); });
      }, 'image/png');
    }).catch(function (err) {
      els.transferSubmit.disabled = false;
      console.warn('[dws] export(transfer)', err);
      toast('내보내기 실패: ' + ((err && err.message) || ''));
    });
  }

  /* ========================================================================
   * [8] init (전역 배선)
   * ====================================================================== */
  function isMobile() {
    try { return window.matchMedia('(pointer: coarse)').matches && window.innerWidth < 900; }
    catch (_) { return false; }
  }

  function insertPlainText(text) {
    text = String(text || '');
    if (document.queryCommandSupported && document.queryCommandSupported('insertText')) {
      document.execCommand('insertText', false, text);
      return;
    }
    var sel = window.getSelection();
    if (!sel.rangeCount) { return; }
    var range = sel.getRangeAt(0);
    range.deleteContents();
    var node = document.createTextNode(text);
    range.insertNode(node);
    range.setStartAfter(node);
    range.collapse(true);
    sel.removeAllRanges();
    sel.addRange(range);
  }

  function wireStatic() {
    // 앱바 편집 버튼
    document.getElementById('dws-btn-autofill').addEventListener('click', autofill);
    document.getElementById('dws-btn-add-text').addEventListener('click', function () {
      addTextObject((STAGE_W - 220) / 2, 340);
    });
    document.getElementById('dws-btn-undo').addEventListener('click', undo);
    document.getElementById('dws-btn-redo').addEventListener('click', redo);
    els.saveBtn.addEventListener('click', save);

    // 프리셋 메뉴
    var presetBtn = document.getElementById('dws-btn-preset');
    presetBtn.addEventListener('click', function (e) { e.stopPropagation(); toggleMenu(els.presetMenu); });
    Array.prototype.forEach.call(els.presetMenu.querySelectorAll('[data-preset]'), function (b) {
      b.addEventListener('click', function () { closeMenus(); addPreset(b.getAttribute('data-preset')); });
    });

    // 이미지 파일 선택
    els.fileInput.addEventListener('change', function () {
      var file = els.fileInput.files && els.fileInput.files[0];
      if (file) { addImageFromFile(file); }
      els.fileInput.value = '';
    });

    // 줌
    document.getElementById('dws-btn-zoom-fit').addEventListener('click', fitZoom);
    els.zoomRange.addEventListener('input', function () { setZoom((parseInt(els.zoomRange.value, 10) || 100) / 100); });

    // 내보내기 메뉴
    var exportBtn = document.getElementById('dws-btn-export');
    exportBtn.addEventListener('click', function (e) { e.stopPropagation(); toggleMenu(els.exportMenu); });
    document.getElementById('dws-btn-export-png').addEventListener('click', exportPng);
    document.getElementById('dws-btn-export-transfer').addEventListener('click', openTransferDialog);

    // 미니 툴바 — 텍스트
    els.mtSize.addEventListener('change', function () { updateSelectedText({ size: parseInt(els.mtSize.value, 10) }); });
    Array.prototype.forEach.call(els.mtText.querySelectorAll('.dws-swatch'), function (sw) {
      sw.addEventListener('click', function () { updateSelectedText({ color: sw.getAttribute('data-color') }); });
    });
    els.mtBold.addEventListener('click', function () {
      var o = findObj(selected); if (o && o.type === 'text') { updateSelectedText({ bold: !o.bold }); }
    });
    els.mtAlign.addEventListener('click', function () {
      var o = findObj(selected); if (o && o.type === 'text') { updateSelectedText({ align: o.align === 'center' ? 'left' : 'center' }); }
    });
    document.getElementById('dws-mt-del-text').addEventListener('click', deleteSelected);

    // 미니 툴바 — 이미지
    els.mtRatio.addEventListener('click', function () { imageRatioLock = !imageRatioLock; syncImageToolbar(); });
    document.getElementById('dws-mt-del-image').addEventListener('click', deleteSelected);

    // 로고 팝업
    Array.prototype.forEach.call(els.logoPopup.querySelectorAll('[data-logo]'), function (b) {
      b.addEventListener('click', function (e) { e.stopPropagation(); setLogo(b.getAttribute('data-logo')); hideLogoPopup(); });
    });

    // 전달 다이얼로그
    document.getElementById('dws-transfer-cancel').addEventListener('click', closeTransferDialog);
    els.transferSubmit.addEventListener('click', doTransfer);

    // 스테이지: 빈 곳 더블클릭 = 텍스트 생성, 빈 곳 클릭 = 선택 해제
    els.stage.addEventListener('dblclick', function (e) {
      if (!canSave || e.target !== els.stage) { return; }
      var rect = els.stage.getBoundingClientRect();
      addTextObject((e.clientX - rect.left) / zoom, (e.clientY - rect.top) / zoom);
    });
    els.stage.addEventListener('pointerdown', function (e) { if (e.target === els.stage) { deselect(); } });

    // 문서 레벨: 메뉴/팝업 바깥 클릭 닫기
    document.addEventListener('click', function (e) {
      if (!e.target.closest('.dws-dropdown')) { closeMenus(); }
      if (!e.target.closest('#dws-logo-popup') && !e.target.closest('#dws-logo-cell')) { hideLogoPopup(); }
    });

    // 문서 레벨 붙여넣기: 편집 중이면 plain text, 아니면 클립보드 이미지 업로드
    document.addEventListener('paste', function (e) {
      if (!canSave) { return; }
      var ae = document.activeElement;
      var cd = e.clipboardData || window.clipboardData;
      if (!cd) { return; }
      if (ae && ae.isContentEditable) {
        e.preventDefault();
        insertPlainText(cd.getData('text/plain'));
        if (ae.getAttribute && ae.getAttribute('data-dws-form-key')) {
          if (!ae._dwsPushed) { recordUndo(); ae._dwsPushed = true; }
          syncEditable(ae);
        }
        return;
      }
      var items = cd.items || [];
      for (var i = 0; i < items.length; i++) {
        if (items[i].type && items[i].type.indexOf('image') === 0) {
          var blob = items[i].getAsFile();
          if (blob) { e.preventDefault(); addImageFromFile(blob); return; }
        }
      }
    });

    // 키보드: 저장 / undo·redo / 삭제 / 화살표 이동
    document.addEventListener('keydown', function (e) {
      var meta = e.ctrlKey || e.metaKey;
      if (meta && (e.key === 's' || e.key === 'S')) { e.preventDefault(); save(); return; }
      var ae = document.activeElement;
      if (ae && ae.isContentEditable) { return; }
      if (meta && (e.key === 'z' || e.key === 'Z')) { e.preventDefault(); if (e.shiftKey) { redo(); } else { undo(); } return; }
      if (meta && (e.key === 'y' || e.key === 'Y')) { e.preventDefault(); redo(); return; }
      if (!selected) { return; }
      if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); deleteSelected(); return; }
      var step = e.shiftKey ? 10 : 1, dx = 0, dy = 0;
      if (e.key === 'ArrowLeft') { dx = -step; }
      else if (e.key === 'ArrowRight') { dx = step; }
      else if (e.key === 'ArrowUp') { dy = -step; }
      else if (e.key === 'ArrowDown') { dy = step; }
      else { return; }
      e.preventDefault();
      var o = findObj(selected);
      if (!o) { return; }
      var now = Date.now();
      if (now - lastArrowUndoTs > 500) { recordUndo(); }
      lastArrowUndoTs = now;
      o.x += dx; o.y += dy;
      positionObjEl(o);
      markDirty();
      positionMiniToolbar(selected);
    });

    // 스크롤/리사이즈 시 미니툴바 위치 갱신
    els.canvas.addEventListener('scroll', function () { if (selected) { positionMiniToolbar(selected); } });
    window.addEventListener('resize', function () { if (selected) { positionMiniToolbar(selected); } });

    // 미저장 이탈 가드
    window.addEventListener('beforeunload', function (e) {
      if (dirty) { e.preventDefault(); e.returnValue = ''; return ''; }
    });
  }

  function autofill() {
    if (!canSave) { return; }
    if (!confirm('현재 폼 값을 주문 데이터로 덮어씁니다. 계속할까요?')) { return; }
    recordUndo();
    var form = currentSheet().form;
    var d = defaults || {};
    Object.keys(d).forEach(function (k) { if (k !== 'checks') { form[k] = (d[k] == null) ? '' : String(d[k]); } });
    renderForm();
    markDirty();
    toast('자동 채움 완료');
  }

  function init() {
    cacheDom();
    if (isMobile()) {
      els.mobileNotice.hidden = false;
      return;
    }
    wireStatic();
    load();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();

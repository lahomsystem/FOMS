/* ============================================================================
 * 도면 마법사 (Drawing Wizard) — 프론트 에디터 (v2 Konva 주석 엔진)
 *
 * 독립 페이지 에디터. 스테이지(논리 1478x1040) 위에 양식 폼(DOM) + 자유 주석
 * 레이어(Konva Stage)를 배치하고, 상태를 structured_data['drawing_wizard']에 저장한다.
 * 주석은 텍스트/이미지/사각형/원/화살표/선 6종을 지원하며 선택·이동·리사이즈·회전이
 * 가능하다. 내보내기는 폼(html2canvas scale=2) + Konva(toCanvas pixelRatio=2)를 오프스크린
 * 캔버스에 합성해 PNG 생성 → 다운로드 또는 기존 전달 API 재사용.
 *
 * 밴드: config/api → state/history → form render → anno(Konva) → toolbar →
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
  var ALLOWED_STROKES = [1, 2, 3];
  var SHAPE_TYPES = ['rect', 'ellipse', 'arrow', 'line'];
  var CHECK_KEYS = ['d_site', 'd_double', 'd_order', 'p_prod', 'p_glass', 'p_light', 'p_handle', 'p_etc'];
  var PRESETS = { SR: '[SR]', EP: '[EP]', DOOR: '[DOOR]', ROD: '[옷봉]' };
  var ANNO_FONT = '"Malgun Gothic","맑은 고딕","Dotum","돋움",sans-serif';
  var _html2canvasPromise = null;

  /* 하단 표 지오메트리(§6 v3) — 외곽 고정, 내부 경계는 form.layout 로 승격.
     cols = A/B 열 내부 x 경계 8개[c1..c8], addr = 주소라벨 경계, rows = 내부 y 경계 3개[r1..r3]. */
  var TBL_X0 = 40, TBL_X1 = 1440, TBL_Y0 = 899, TBL_Y1 = 1000;
  var COL_MIN_GAP = 24, ROW_MIN_GAP = 18;
  var TOP_MIN = 120, TOP_MAX = 940;   // 하단 표 상단선(top) 이동 범위(헤더 아래 ~ r1-18 위)
  var LAYOUT_DEFAULT = { cols: [123, 211, 310, 399, 728, 820, 1227, 1330], addr: 89, rows: [924, 949, 974], top: 899 };
  var CELL_FONT_DEFAULT = 16, CELL_FONT_MIN = 12, CELL_FONT_MAX = 24;
  /* 경계 드래그 정의: col 8 + addr 1 + row 3 + top 1 = 13. span = 히트존 세로/가로 범위. */
  var DIVIDERS = [
    { kind: 'col', idx: 0, span: 'ab' }, { kind: 'col', idx: 1, span: 'ab' },
    { kind: 'col', idx: 2, span: 'full' }, { kind: 'col', idx: 3, span: 'full' },
    { kind: 'col', idx: 4, span: 'full' }, { kind: 'col', idx: 5, span: 'full' },
    { kind: 'col', idx: 6, span: 'full' }, { kind: 'col', idx: 7, span: 'ab' },
    { kind: 'addr' },
    { kind: 'row', idx: 0, span: 'full' }, { kind: 'row', idx: 1, span: 'full' },
    { kind: 'row', idx: 2, span: 'partial' },
    { kind: 'top' }
  ];

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

  /* 주석 필드 정규화 헬퍼(직렬화·역직렬화·노드 생성 공용) */
  function sizeOrDefault(s) { return (ALLOWED_SIZES.indexOf(s) >= 0) ? s : 20; }
  function colorOrDefault(c) { return /^#[0-9a-fA-F]{6}$/.test(c) ? c : '#000000'; }
  function strokeOrDefault(s) { return (ALLOWED_STROKES.indexOf(s) >= 0) ? s : 2; }
  function clampCoord(v) { return clamp(Math.round(num(v)), -2000, 4000); }
  function clampDim(v) { return clamp(Math.round(num(v, 1)), 1, 3000); }
  function normalizeRotation(r) { r = Math.round(num(r, 0)); return ((r % 360) + 360) % 360; }
  function normalizePoints(pts) {
    var out = [];
    var src = Array.isArray(pts) ? pts : [];
    for (var i = 0; i < 4; i++) { out.push(clamp(Math.round(num(src[i])), -2000, 4000)); }
    return out;
  }
  function isShapeType(t) { return SHAPE_TYPES.indexOf(t) >= 0; }
  function isFiniteNum(v) { return typeof v === 'number' && isFinite(v); }

  /** 경계 배열 검증: 길이 정확 + 각 항목 숫자 + 최소간격 오름차순 + 외곽 여유. */
  function validBounds(arr, len, lo, hi, gap) {
    if (!Array.isArray(arr) || arr.length !== len) { return false; }
    var prev = lo;
    for (var i = 0; i < len; i++) {
      if (!isFiniteNum(arr[i]) || arr[i] < prev + gap) { return false; }
      prev = arr[i];
    }
    return prev <= hi - gap;
  }

  /** form.layout → 검증·폴백된 {cols[8], addr, rows[3]}. 이상치는 v3 기본값으로. */
  function sanitizeLayout(raw) {
    var out = { cols: LAYOUT_DEFAULT.cols.slice(), addr: LAYOUT_DEFAULT.addr, rows: LAYOUT_DEFAULT.rows.slice(), top: LAYOUT_DEFAULT.top };
    if (raw && typeof raw === 'object') {
      if (validBounds(raw.cols, 8, TBL_X0, TBL_X1, COL_MIN_GAP)) { out.cols = raw.cols.map(function (v) { return Math.round(v); }); }
      var a = raw.addr;
      if (isFiniteNum(a) && a >= TBL_X0 + COL_MIN_GAP && a <= out.cols[2] - COL_MIN_GAP) { out.addr = Math.round(a); }
      var t = raw.top;   // top 먼저(절대범위 120~940). top↔rows 최소간격은 rows 하한=top 으로 강제.
      if (isFiniteNum(t) && t >= TOP_MIN && t <= TOP_MAX) { out.top = Math.round(t); }
      // rows 는 표 상단선(top) 아래에서만 유효 — 하한을 top 으로 두어 상단선 이동과 정합(레거시=899).
      if (validBounds(raw.rows, 3, out.top, TBL_Y1, ROW_MIN_GAP)) { out.rows = raw.rows.map(function (v) { return Math.round(v); }); }
    }
    // 불변식 강제: top+18 ≤ rows[0] (기본 rows 로 폴백 시 top 이 과도하면 끌어내림).
    if (out.top > out.rows[0] - ROW_MIN_GAP) { out.top = out.rows[0] - ROW_MIN_GAP; }
    return out;
  }

  /** form.cell_font → 12~24 정수(이상치는 16). */
  function sanitizeCellFont(v) {
    if (!isFiniteNum(v)) { return CELL_FONT_DEFAULT; }
    return clamp(Math.round(v), CELL_FONT_MIN, CELL_FONT_MAX);
  }

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
  var selected = null;                 // 선택된 주석 객체 id (Konva 노드와 동기)
  var zoom = 1;
  var imageRatioLock = true;
  var undoStack = [];
  var redoStack = [];
  var lastArrowUndoTs = 0;

  /* Konva 런타임 상태 */
  var konvaStage = null;
  var konvaLayer = null;
  var transformer = null;
  var nodeById = {};                   // objId → Konva 노드
  var annoMode = 'select';             // 'select'|'text'|'rect'|'ellipse'|'arrow'|'line'
  var lastStrokeColor = '#000000';     // 다음 도형 기본 선 색
  var lastStrokeWidth = 2;             // 다음 도형 기본 선 굵기
  var editingTextarea = null;          // 활성 텍스트 오버레이(있으면 편집 중; contenteditable div)
  var editCtx = null;                  // 리치 편집 컨텍스트 {id, area, isNew, size, align}
  var commitActiveEdit = null;         // 활성 편집 즉시 커밋 훅(stage down/save/export 공용)
  var suppressLogoHideUntil = 0;       // 로고 셀 열림 제스처의 같은 native click 억제 창(ms 타임스탬프)
  var textJustOpenedUntil = 0;         // 새 텍스트 오버레이 보호창 — 직후 stage down의 handler-blur 방지
  var lastDownTs = -1000;              // stage mousedown 이중발화 dedupe: 직전 처리 down의 timeStamp
  var lastDownX = -9999;               // 직전 처리 down의 clientX
  var lastDownY = -9999;               // 직전 처리 down의 clientY

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
    Object.keys(d).forEach(function (k) {
      if (k === 'checks' || k === 'layout' || k === 'cell_font') { return; }
      f[k] = (d[k] == null) ? '' : String(d[k]);
    });
    var ck = d.checks || {};
    f.checks = {};
    CHECK_KEYS.forEach(function (k) { f.checks[k] = !!ck[k]; });
    f.layout = sanitizeLayout(d.layout);
    f.cell_font = sanitizeCellFont(d.cell_font);
    return f;
  }

  function pushUndoSnapshot(snap) {
    undoStack.push(snap);
    if (undoStack.length > 50) { undoStack.shift(); }
    redoStack.length = 0;
  }

  function recordUndo() { pushUndoSnapshot(cloneSheet(currentSheet())); }

  function undo() {
    if (!undoStack.length) { return; }
    redoStack.push(cloneSheet(currentSheet()));
    state.sheets[current] = undoStack.pop();
    deselect();
    renderForm();
    rebuildAnno();
    markDirty();
  }

  function redo() {
    if (!redoStack.length) { return; }
    undoStack.push(cloneSheet(currentSheet()));
    state.sheets[current] = redoStack.pop();
    deselect();
    renderForm();
    rebuildAnno();
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
    els.anno = document.getElementById('dws-anno');
    els.logoCell = document.getElementById('dws-logo-cell');
    els.logoImg = document.getElementById('dws-logo-img');
    els.logoPopup = document.getElementById('dws-logo-popup');
    els.saveBtn = document.getElementById('dws-btn-save');
    els.zoomRange = document.getElementById('dws-zoom-range');
    els.zoomLabel = document.getElementById('dws-zoom-label');
    els.fileInput = document.getElementById('dws-file-input');
    els.presetMenu = document.getElementById('dws-preset-menu');
    els.shapeMenu = document.getElementById('dws-shape-menu');
    els.exportMenu = document.getElementById('dws-export-menu');
    els.mt = document.getElementById('dws-minitoolbar');
    els.mtText = document.getElementById('dws-mt-text');
    els.mtImage = document.getElementById('dws-mt-image');
    els.mtShape = document.getElementById('dws-mt-shape');
    els.mtSize = document.getElementById('dws-mt-size');
    els.mtBold = document.getElementById('dws-mt-bold');
    els.mtAlign = document.getElementById('dws-mt-align');
    els.mtRatio = document.getElementById('dws-mt-ratio');
    els.mtStroke = document.getElementById('dws-mt-stroke');
    els.transferDialog = document.getElementById('dws-transfer-dialog');
    els.transferNote = document.getElementById('dws-transfer-note');
    els.transferMode = document.getElementById('dws-transfer-mode');
    els.transferSubmit = document.getElementById('dws-transfer-submit');
    els.toastHost = document.getElementById('dws-toast-host');
    els.mobileNotice = document.getElementById('dws-mobile-notice');
    els.modeHint = document.getElementById('dws-mode-hint');
    els.fontDecBtn = document.getElementById('dws-btn-font-dec');
    els.fontIncBtn = document.getElementById('dws-btn-font-inc');
    els.dividers = document.getElementById('dws-dividers');
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
    applyFormLayout(currentSheet());
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
    // 라홈만 라홈 로고, 그 외 전부('haud'/'none'/빈값/기타)는 하우드 로고
    // (하위호환: 기존 저장 'none'도 하우드로 렌더).
    var src = (logo === 'lahom') ? '/static/images/lahom-logo.png' : '/static/images/haud-logo.png';
    els.logoImg.src = src;
    els.logoImg.hidden = false;
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

  /** 편집 리스너 배선(저장 권한 있을 때만). 캔버스가 위에 있어 폼 클릭은 passthrough로 전달됨. */
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

  /* ---- 표 레이아웃 렌더 엔진 (CSS 고정 → JS 주도, 단일 소스=state) -------- */
  /** 표 셀·그리드라인 DOM 참조를 1회 캐시(정적 DOM, 시트 전환 시 재사용). */
  function cacheLayoutEls() {
    var f = els.form;
    function g(cls) { return f.querySelector('.' + cls); }
    els.lay = {
      aL1: g('dws-c-a-l1'), aL2: g('dws-c-a-l2'), aL3: g('dws-c-a-l3'), aL4: g('dws-c-a-l4'),
      aProduct: g('dws-c-a-product'), aL5: g('dws-c-a-l5'), aSite: g('dws-c-a-sitespec'),
      aL6: g('dws-c-a-l6'), aSales: g('dws-c-a-sales'),
      bCdate: g('dws-c-b-cdate'), bCname: g('dws-c-b-cname'), bPhone: g('dws-c-b-phone'),
      bL1: g('dws-c-b-l1'), bColor: g('dws-c-b-color'), bL2: g('dws-c-b-l2'),
      bW300: g('dws-c-b-w300'), bL3: g('dws-c-b-l3'), bMphone: g('dws-c-b-mphone'),
      addrLabel: g('dws-c-cd-addrlabel'), addr: g('dws-c-cd-addr'),
      handleLabel: g('dws-c-c-handlelabel'), handle: g('dws-c-c-handle'),
      drawerLabel: g('dws-c-d-drawerlabel'), drawer: g('dws-c-d-drawer'),
      etcLabel: g('dws-c-cd-etclabel'), misc: g('dws-c-cd-misc'), logo: g('dws-c-cd-logo'),
      topFrame: g('dws-table-frame'),
      hAb: g('dws-hline-ab'), hBc: g('dws-hline-bc'), hCd: g('dws-hline-cd'),
      vC1: g('dws-v-123'), vC2: g('dws-v-211'), vC3: g('dws-v-310'), vC4: g('dws-v-399'),
      vC5: g('dws-v-728'), vC6: g('dws-v-820'), vC7: g('dws-v-1227'), vC8: g('dws-v-1330'),
      vAddr: g('dws-v-89'),
      cells: f.querySelectorAll('.dws-cell')
    };
  }

  function setBox(el, left, top, width, height) {
    if (!el) { return; }
    el.style.left = left + 'px'; el.style.top = top + 'px';
    el.style.width = width + 'px'; el.style.height = height + 'px';
  }
  function setHLine(el, left, top, width) {
    if (!el) { return; }
    el.style.left = left + 'px'; el.style.top = top + 'px';
    el.style.width = width + 'px'; el.style.height = '1px';
  }
  function setVLine(el, left, top, height) {
    if (!el) { return; }
    el.style.left = left + 'px'; el.style.top = top + 'px';
    el.style.width = '1px'; el.style.height = height + 'px';
  }

  /** 시트 layout+cell_font → 셀/그리드라인/폰트 style 직접 세팅 + 히트존 재배치. */
  function applyFormLayout(sheet) {
    if (!els.lay) { return; }
    var form = (sheet || currentSheet()).form || {};
    var L = sanitizeLayout(form.layout);
    var font = sanitizeCellFont(form.cell_font);
    var c = L.cols, addr = L.addr, r = L.rows, top = L.top;
    var X0 = TBL_X0, X1 = TBL_X1, Y1 = TBL_Y1;
    var aTop = top, aH = r[0] - top;
    var bTop = r[0], bH = r[1] - r[0];
    var cdTop = r[1], cdH = Y1 - r[1];
    var cTop = r[1], cH = r[2] - r[1];
    var dTop = r[2], dH = Y1 - r[2];
    var q = els.lay;
    // A행 (라벨/값 9칸)
    setBox(q.aL1, X0, aTop, c[0] - X0, aH); setBox(q.aL2, c[0], aTop, c[1] - c[0], aH);
    setBox(q.aL3, c[1], aTop, c[2] - c[1], aH); setBox(q.aL4, c[2], aTop, c[3] - c[2], aH);
    setBox(q.aProduct, c[3], aTop, c[4] - c[3], aH); setBox(q.aL5, c[4], aTop, c[5] - c[4], aH);
    setBox(q.aSite, c[5], aTop, c[6] - c[5], aH); setBox(q.aL6, c[6], aTop, c[7] - c[6], aH);
    setBox(q.aSales, c[7], aTop, X1 - c[7], aH);
    // B행
    setBox(q.bCdate, X0, bTop, c[0] - X0, bH); setBox(q.bCname, c[0], bTop, c[1] - c[0], bH);
    setBox(q.bPhone, c[1], bTop, c[2] - c[1], bH); setBox(q.bL1, c[2], bTop, c[3] - c[2], bH);
    setBox(q.bColor, c[3], bTop, c[4] - c[3], bH); setBox(q.bL2, c[4], bTop, c[5] - c[4], bH);
    setBox(q.bW300, c[5], bTop, c[6] - c[5], bH); setBox(q.bL3, c[6], bTop, c[7] - c[6], bH);
    setBox(q.bMphone, c[7], bTop, X1 - c[7], bH);
    // C/D행 (주소/기타/로고는 C+D 병합, 손잡이·서랍은 각 행)
    setBox(q.addrLabel, X0, cdTop, addr - X0, cdH); setBox(q.addr, addr, cdTop, c[2] - addr, cdH);
    setBox(q.handleLabel, c[2], cTop, c[3] - c[2], cH); setBox(q.handle, c[3], cTop, c[4] - c[3], cH);
    setBox(q.drawerLabel, c[2], dTop, c[3] - c[2], dH); setBox(q.drawer, c[3], dTop, c[4] - c[3], dH);
    setBox(q.etcLabel, c[4], cdTop, c[5] - c[4], cdH); setBox(q.misc, c[5], cdTop, c[6] - c[5], cdH);
    setBox(q.logo, c[6], cdTop, X1 - c[6], cdH);
    // 표 상단 프레임(top 이동 반영 — 좌/우/폭은 CSS 유지, y만 갱신)
    if (q.topFrame) { q.topFrame.style.top = top + 'px'; }
    // 그리드 라인
    setHLine(q.hAb, X0, r[0], X1 - X0); setHLine(q.hBc, X0, r[1], X1 - X0);
    setHLine(q.hCd, c[2], r[2], c[4] - c[2]);
    setVLine(q.vC1, c[0], top, r[1] - top); setVLine(q.vC2, c[1], top, r[1] - top);
    setVLine(q.vC3, c[2], top, Y1 - top); setVLine(q.vC4, c[3], top, Y1 - top);
    setVLine(q.vC5, c[4], top, Y1 - top); setVLine(q.vC6, c[5], top, Y1 - top);
    setVLine(q.vC7, c[6], top, Y1 - top); setVLine(q.vC8, c[7], top, r[1] - top);
    setVLine(q.vAddr, addr, r[1], Y1 - r[1]);
    // 폰트(표 셀 전체 동일)
    if (q.cells) { Array.prototype.forEach.call(q.cells, function (el) { el.style.fontSize = font + 'px'; }); }
    if (els.fontDecBtn) { els.fontDecBtn.title = '표 글자 작게 (현재 ' + font + 'px)'; }
    if (els.fontIncBtn) { els.fontIncBtn.title = '표 글자 크게 (현재 ' + font + 'px)'; }
    positionDividers(L);
  }

  /* ---- 경계선 드래그(열/행 폭 조절) --------------------------------------- */
  function positionDividers(L) {
    if (!els.divEls) { return; }
    L = L || sanitizeLayout(currentSheet().form.layout);
    var c = L.cols, addr = L.addr, r = L.rows, r2 = r[1], topY = L.top;
    els.divEls.forEach(function (item) {
      var d = item.meta, el = item.el;
      if (d.kind === 'col') {
        el.style.left = (c[d.idx] - 3.5) + 'px'; el.style.top = topY + 'px';
        el.style.width = '7px'; el.style.height = ((d.span === 'ab') ? (r2 - topY) : (TBL_Y1 - topY)) + 'px';
      } else if (d.kind === 'addr') {
        el.style.left = (addr - 3.5) + 'px'; el.style.top = r2 + 'px';
        el.style.width = '7px'; el.style.height = (TBL_Y1 - r2) + 'px';
      } else if (d.kind === 'top') {
        el.style.left = TBL_X0 + 'px'; el.style.top = (topY - 3.5) + 'px';
        el.style.width = (TBL_X1 - TBL_X0) + 'px'; el.style.height = '7px';
      } else {
        var partial = (d.span === 'partial');
        el.style.left = (partial ? c[2] : TBL_X0) + 'px'; el.style.top = (r[d.idx] - 3.5) + 'px';
        el.style.width = (partial ? (c[4] - c[2]) : (TBL_X1 - TBL_X0)) + 'px'; el.style.height = '7px';
      }
    });
  }

  function dividerLogical(evt) {
    var rect = els.dividers.getBoundingClientRect();
    return { x: (evt.clientX - rect.left) / zoom, y: (evt.clientY - rect.top) / zoom };
  }

  /** 경계 이동을 제약(이웃·외곽 최소간격) 안에서 layout에 반영. logical={x}|{y}. */
  function commitDividerMove(d, logical) {
    var lay = currentSheet().form.layout;
    if (!lay || !lay.cols) { lay = currentSheet().form.layout = sanitizeLayout(lay); }
    if (!isFiniteNum(lay.top)) { lay.top = LAYOUT_DEFAULT.top; }   // 구 저장분(top 없음) 방어
    var G = COL_MIN_GAP, GR = ROW_MIN_GAP;
    if (d.kind === 'col') {
      var i = d.idx;
      var lo = (i === 0 ? TBL_X0 : lay.cols[i - 1]) + G;
      var hi = (i === 7 ? TBL_X1 : lay.cols[i + 1]) - G;
      if (i === 2) { lo = Math.max(lo, lay.addr + G); }   // c3 은 addr 오른쪽 유지
      lay.cols[i] = Math.round(clamp(logical.x, lo, hi));
    } else if (d.kind === 'addr') {
      lay.addr = Math.round(clamp(logical.x, TBL_X0 + G, lay.cols[2] - G));
    } else if (d.kind === 'top') {
      lay.top = Math.round(clamp(logical.y, TOP_MIN, lay.rows[0] - GR));   // 위=120, 아래=r1-18
    } else {
      var j = d.idx;
      var loR = (j === 0 ? lay.top : lay.rows[j - 1]) + GR;   // r1 상한은 top 아래로만
      var hiR = (j === 2 ? TBL_Y1 : lay.rows[j + 1]) - GR;
      lay.rows[j] = Math.round(clamp(logical.y, loR, hiR));
    }
  }

  function resetDivider(d) {
    recordUndo();
    if (d.kind === 'col') { commitDividerMove(d, { x: LAYOUT_DEFAULT.cols[d.idx] }); }
    else if (d.kind === 'addr') { commitDividerMove(d, { x: LAYOUT_DEFAULT.addr }); }
    else if (d.kind === 'top') { commitDividerMove(d, { y: LAYOUT_DEFAULT.top }); }
    else { commitDividerMove(d, { y: LAYOUT_DEFAULT.rows[d.idx] }); }
    markDirty();
    applyFormLayout(currentSheet());
  }

  function wireDivider(el, meta) {
    var drag = null, rafPending = false, pendingLogical = null;
    el.addEventListener('pointerdown', function (e) {
      if (!canSave || annoMode !== 'select') { return; }
      var now = Date.now();
      if (now - (el.__dwsTapTs || 0) < 320) {   // 두 번째 탭 = 초기화(dblclick 합성 억제와 무관)
        el.__dwsTapTs = 0; e.preventDefault(); e.stopPropagation();
        resetDivider(meta); return;
      }
      el.__dwsTapTs = now;
      e.preventDefault(); e.stopPropagation();
      try { el.setPointerCapture(e.pointerId); } catch (_) { /* noop */ }
      drag = { snap: cloneSheet(currentSheet()), moved: false, pid: e.pointerId };
    });
    el.addEventListener('pointermove', function (e) {
      if (!drag || e.pointerId !== drag.pid) { return; }
      e.preventDefault();
      pendingLogical = dividerLogical(e);
      drag.moved = true;
      if (!rafPending) {
        rafPending = true;
        requestAnimationFrame(function () {
          rafPending = false;
          if (!drag || !pendingLogical) { return; }
          commitDividerMove(meta, pendingLogical);
          applyFormLayout(currentSheet());
        });
      }
    });
    function finish() {
      if (!drag) { return; }
      try { el.releasePointerCapture(drag.pid); } catch (_) { /* noop */ }
      var moved = drag.moved, snap = drag.snap, last = pendingLogical;
      drag = null; pendingLogical = null;
      if (moved) {
        if (last) { commitDividerMove(meta, last); }   // 마지막 프레임(rAF 미발화분) 확정
        el.__dwsTapTs = 0; pushUndoSnapshot(snap); markDirty(); applyFormLayout(currentSheet());
      }
    }
    el.addEventListener('pointerup', finish);
    el.addEventListener('pointercancel', function () {
      if (!drag) { return; }
      try { el.releasePointerCapture(drag.pid); } catch (_) { /* noop */ }
      var moved = drag.moved, snap = drag.snap;
      drag = null; pendingLogical = null;
      if (moved) { state.sheets[current] = snap; applyFormLayout(currentSheet()); }   // 취소 = 드래그 시작 상태 복원
    });
  }

  function buildDividers() {
    if (!els.dividers) { return; }
    els.divEls = [];
    DIVIDERS.forEach(function (meta) {
      var el = document.createElement('div');
      var horizontal = (meta.kind === 'row' || meta.kind === 'top');   // 가로선=행/상단선(row-resize 커서)
      el.className = 'dws-divider dws-divider-' + (horizontal ? 'row' : 'col');
      if (meta.kind === 'top') { el.title = '드래그: 표 상단선 이동 · 더블클릭: 초기화'; }
      else if (meta.kind === 'row') { el.title = '드래그: 행 높이 조절 · 더블클릭: 초기화'; }
      else { el.title = '드래그: 열 너비 조절 · 더블클릭: 초기화'; }
      wireDivider(el, meta);
      els.dividers.appendChild(el);
      els.divEls.push({ el: el, meta: meta });
    });
  }

  /** 편집 불가·비select 모드에서 히트존 비활성(도형 드로잉·셀 편집 방해 금지). */
  function updateDividerState() {
    if (root) { root.classList.toggle('dws-dividers-off', (!canSave || annoMode !== 'select')); }
  }

  function bumpCellFont(delta) {
    if (!canSave) { return; }
    var form = currentSheet().form;
    var cur = sanitizeCellFont(form.cell_font);
    var next = clamp(cur + delta, CELL_FONT_MIN, CELL_FONT_MAX);
    if (next === cur) { return; }
    recordUndo();
    form.cell_font = next;
    markDirty();
    applyFormLayout(currentSheet());
  }

  /* ========================================================================
   * [4] anno layer (Konva Stage) — 렌더 / 상호작용 / 그리기 / 편집
   * ====================================================================== */

  /** Konva Stage/Layer/Transformer 생성 + 스테이지 레벨 이벤트 배선. */
  function createKonva() {
    konvaStage = new Konva.Stage({ container: els.anno, width: STAGE_W, height: STAGE_H });
    konvaLayer = new Konva.Layer();
    konvaStage.add(konvaLayer);

    transformer = new Konva.Transformer({
      rotateEnabled: true,
      keepRatio: false,
      enabledAnchors: ['top-left', 'top-right', 'bottom-left', 'bottom-right'],
      anchorSize: 10,
      anchorStroke: '#1c62d6',
      anchorFill: '#ffffff',
      borderStroke: '#1c62d6',
      borderStrokeWidth: 1.5,
      rotateAnchorOffset: 24,
      rotationSnaps: [0, 45, 90, 135, 180, 225, 270, 315],
      rotationSnapTolerance: 6,
      ignoreStroke: true
    });
    konvaLayer.add(transformer);

    konvaStage.on('mousedown', onStageMouseDown);
    konvaStage.on('dblclick', onStageDblClick);
  }

  /** 네이티브 이벤트 → 스테이지 논리 좌표(줌 역보정). */
  function pointerLogical(evt) {
    var rect = els.anno.getBoundingClientRect();
    return { x: (evt.clientX - rect.left) / zoom, y: (evt.clientY - rect.top) / zoom };
  }

  /* ---- 텍스트 스타일 런(글자 단위 색상/굵기) 공용 헬퍼 --------------------
     스키마: text 객체의 optional runs = [{t, c '#rrggbb', b bool}]. 개행은 t 안의
     '\n'. text(플레인 합본)=join(runs.t), color/bold=첫 런 값으로 항상 동기(SSOT).
     runs 없는 객체 = 기존 단색 Konva.Text 경로(무변경). ------------------------ */
  var MAX_TEXT_RUNS = 60;
  var _measureCanvas = null;

  /** raw runs → 검증·병합된 [{t,c,b}] 또는 null(런 없음/단일 스타일=단색 경로). */
  function sanitizeRuns(rawRuns) {
    if (!Array.isArray(rawRuns) || !rawRuns.length || rawRuns.length > MAX_TEXT_RUNS) { return null; }
    var out = [];
    for (var i = 0; i < rawRuns.length; i++) {
      var r = rawRuns[i];
      if (!r || typeof r.t !== 'string' || r.t === '') { continue; }
      var c = colorOrDefault(r.c), b = !!r.b;
      var last = out[out.length - 1];
      if (last && last.c === c && last.b === b) { last.t += r.t; }
      else { out.push({ t: r.t, c: c, b: b }); }
    }
    if (out.length <= 1) { return null; }   // 0/1 런 = 단색 경로(상태 비대 방지)
    var first = out[0];
    var allSame = out.every(function (x) { return x.c === first.c && x.b === first.b; });
    return allSame ? null : out;
  }

  /** runs 불변식 강제: text=join(t), color/bold=첫 런. 무효 런은 제거(단색 폴백). */
  function syncTextFromRuns(o) {
    var runs = sanitizeRuns(o.runs);
    if (!runs) { delete o.runs; return; }
    o.runs = runs;
    o.text = runs.map(function (r) { return r.t; }).join('');
    o.color = runs[0].c;
    o.bold = !!runs[0].b;
  }

  /** canvas 2d measureText 로 런 폭 계산(Konva 내부와 동일 엔진 → 렌더 정합). */
  function measureRunWidth(text, size, bold) {
    if (!_measureCanvas) { _measureCanvas = document.createElement('canvas'); }
    var ctx = _measureCanvas.getContext('2d');
    ctx.font = (bold ? 'bold ' : '') + size + 'px ' + ANNO_FONT;
    return ctx.measureText(String(text)).width;
  }

  /** runs → 줄 시퀀스[[{t,c,b}...], ...] ('\n' 기준 분할, 개행 문자는 제거). */
  function runsToLines(runs) {
    var lines = [[]];
    runs.forEach(function (r) {
      var parts = String(r.t).split('\n');
      for (var i = 0; i < parts.length; i++) {
        if (i > 0) { lines.push([]); }
        if (parts[i] !== '') { lines[lines.length - 1].push({ t: parts[i], c: r.c, b: r.b }); }
      }
    });
    return lines;
  }

  /* ---- 노드 빌더 ---------------------------------------------------------- */
  function buildNode(o) {
    switch (o.type) {
      case 'text': return buildText(o);
      case 'image': return buildImage(o);
      case 'rect': return buildRect(o);
      case 'ellipse': return buildEllipse(o);
      case 'arrow': return buildArrow(o);
      case 'line': return buildLine(o);
      default: return null;
    }
  }

  function tagNode(node, o) {
    node.setAttr('annoType', o.type);
    node.setAttr('objId', o.id);
    wireNode(node);
    return node;
  }

  function buildText(o) {
    if (o.runs && o.runs.length) { return buildRichText(o); }
    var node = new Konva.Text({
      x: num(o.x), y: num(o.y), width: num(o.w, 220), text: String(o.text || ''),
      fontSize: sizeOrDefault(o.size), fill: colorOrDefault(o.color), fontFamily: ANNO_FONT,
      fontStyle: o.bold ? 'bold' : 'normal', align: (o.align === 'center') ? 'center' : 'left',
      lineHeight: 1.25, rotation: num(o.rotation), wrap: 'word', name: 'anno', draggable: canSave
    });
    tagNode(node, o);
    node.on('dblclick', function (e) { e.cancelBubble = true; if (canSave) { startEditText(node, false); } });
    return node;
  }

  /** 런 텍스트 = Konva.Group + 줄/런별 Text 조각(글자 단위 색상/굵기). wrap 미지원(명시 개행만). */
  function buildRichText(o) {
    var size = sizeOrDefault(o.size);
    var lineHeight = size * 1.25;
    var align = (o.align === 'center') ? 'center' : 'left';
    var lines = runsToLines(o.runs);
    var lineWidths = lines.map(function (segs) {
      var w = 0;
      segs.forEach(function (s) { w += measureRunWidth(s.t, size, s.b); });
      return w;
    });
    var groupWidth = Math.max.apply(null, lineWidths.concat([1]));
    var group = new Konva.Group({
      x: num(o.x), y: num(o.y), rotation: num(o.rotation), name: 'anno', draggable: canSave
    });
    lines.forEach(function (segs, li) {
      var xOff = (align === 'center') ? (groupWidth - lineWidths[li]) / 2 : 0;
      var cursorX = xOff;
      segs.forEach(function (s) {
        group.add(new Konva.Text({
          x: cursorX, y: li * lineHeight, text: s.t, fontSize: size,
          fill: colorOrDefault(s.c), fontFamily: ANNO_FONT,
          fontStyle: s.b ? 'bold' : 'normal', lineHeight: 1.25
        }));
        cursorX += measureRunWidth(s.t, size, s.b);
      });
    });
    group.setAttr('richWidth', Math.round(groupWidth));
    tagNode(group, o);
    group.on('dblclick', function (e) { e.cancelBubble = true; if (canSave) { startEditText(group, false); } });
    return group;
  }

  function buildImage(o) {
    var node = new Konva.Image({
      x: num(o.x), y: num(o.y), width: num(o.w, 200), height: num(o.h, 150),
      rotation: num(o.rotation), image: undefined, name: 'anno', draggable: canSave
    });
    tagNode(node, o);
    if (o.key) {
      var img = new Image();
      img.onload = function () { node.image(img); konvaLayer.batchDraw(); };
      img.onerror = function () { /* 로드 실패 시 빈 프레임 유지 */ };
      img.src = viewUrl(o.key);
    }
    return node;
  }

  function buildRect(o) {
    var node = new Konva.Rect({
      x: num(o.x), y: num(o.y), width: num(o.w, 80), height: num(o.h, 60),
      stroke: colorOrDefault(o.stroke), strokeWidth: strokeOrDefault(o.strokeWidth),
      rotation: num(o.rotation), fill: 'rgba(0,0,0,0.001)', hitStrokeWidth: 12,
      name: 'anno', draggable: canSave
    });
    return tagNode(node, o);
  }

  function buildEllipse(o) {
    var rx = num(o.w, 80) / 2, ry = num(o.h, 60) / 2;
    var node = new Konva.Ellipse({
      x: num(o.x) + rx, y: num(o.y) + ry, radiusX: Math.max(1, rx), radiusY: Math.max(1, ry),
      stroke: colorOrDefault(o.stroke), strokeWidth: strokeOrDefault(o.strokeWidth),
      rotation: num(o.rotation), fill: 'rgba(0,0,0,0.001)', hitStrokeWidth: 12,
      name: 'anno', draggable: canSave
    });
    return tagNode(node, o);
  }

  function buildArrow(o) {
    var pts = normalizePoints(o.points);
    var node = new Konva.Arrow({
      points: pts, stroke: colorOrDefault(o.stroke), strokeWidth: strokeOrDefault(o.strokeWidth),
      fill: colorOrDefault(o.stroke), pointerLength: 12, pointerWidth: 12,
      rotation: num(o.rotation), hitStrokeWidth: 12, name: 'anno', draggable: canSave
    });
    return tagNode(node, o);
  }

  function buildLine(o) {
    var pts = normalizePoints(o.points);
    var node = new Konva.Line({
      points: pts, stroke: colorOrDefault(o.stroke), strokeWidth: strokeOrDefault(o.strokeWidth),
      lineCap: 'round', lineJoin: 'round', rotation: num(o.rotation), hitStrokeWidth: 12,
      name: 'anno', draggable: canSave
    });
    return tagNode(node, o);
  }

  /** 선택/드래그/변형 이벤트 공통 배선. */
  function wireNode(node) {
    if (!canSave) { return; }
    node.on('mousedown', function (e) {
      if (annoMode !== 'select') { return; }   // 그리기 모드면 스테이지 핸들러가 처리
      e.cancelBubble = true;
      selectById(node.getAttr('objId'));
    });
    node.on('dragstart', function () {
      if (annoMode !== 'select') { node.stopDrag(); return; }
      recordUndo();
    });
    node.on('dragmove', function () { positionMiniToolbar(); });
    node.on('dragend', function () { commitNode(node); });
    node.on('transformstart', function () { recordUndo(); });
    node.on('transform', function () { applyLiveTransform(node); positionMiniToolbar(); });
    node.on('transformend', function () { commitNode(node); });
  }

  /** 변형 중 scale → 실제 치수로 정규화(폰트/선굵기 왜곡 방지). */
  function applyLiveTransform(node) {
    var t = node.getAttr('annoType');
    if (t === 'text') {
      if (node.getClassName() === 'Group') { return; }   // 런 텍스트: 회전만(리사이즈 앵커 비활성)
      node.width(Math.max(30, node.width() * node.scaleX()));
      node.scaleX(1); node.scaleY(1);
    } else if (t === 'ellipse') {
      node.radiusX(Math.max(4, node.radiusX() * node.scaleX()));
      node.radiusY(Math.max(4, node.radiusY() * node.scaleY()));
      node.scaleX(1); node.scaleY(1);
    } else if (t === 'rect' || t === 'image') {
      node.width(Math.max(8, node.width() * node.scaleX()));
      node.height(Math.max(8, node.height() * node.scaleY()));
      node.scaleX(1); node.scaleY(1);
    }
    /* arrow/line: scale/회전은 commit 시 절대 points로 baking */
  }

  /** 노드 → state 객체 역직렬화(드래그/변형 확정 시). */
  function commitNode(node) {
    var o = findObj(node.getAttr('objId'));
    if (!o) { return; }
    var t = node.getAttr('annoType');
    if (t === 'text') {
      o.x = Math.round(node.x()); o.y = Math.round(node.y());
      o.rotation = normalizeRotation(node.rotation());
      // 런 텍스트(Group)는 렌더 결과 폭을 w 로 저장(렌더는 무시), 단색은 Konva.Text 폭.
      o.w = (node.getClassName() === 'Group')
        ? Math.round(node.getAttr('richWidth') || o.w || 220)
        : Math.round(node.width());
    } else if (t === 'image' || t === 'rect') {
      o.x = Math.round(node.x()); o.y = Math.round(node.y());
      o.w = Math.round(node.width()); o.h = Math.round(node.height());
      o.rotation = normalizeRotation(node.rotation());
    } else if (t === 'ellipse') {
      var rx = node.radiusX(), ry = node.radiusY();
      o.x = Math.round(node.x() - rx); o.y = Math.round(node.y() - ry);
      o.w = Math.round(rx * 2); o.h = Math.round(ry * 2);
      o.rotation = normalizeRotation(node.rotation());
    } else if (t === 'arrow' || t === 'line') {
      var tr = node.getAbsoluteTransform();
      var p = node.points();
      var a = tr.point({ x: p[0], y: p[1] });
      var b = tr.point({ x: p[2], y: p[3] });
      node.points([a.x, a.y, b.x, b.y]);
      node.position({ x: 0, y: 0 }); node.rotation(0); node.scale({ x: 1, y: 1 });
      o.points = [Math.round(a.x), Math.round(a.y), Math.round(b.x), Math.round(b.y)];
      o.rotation = 0;
    }
    markDirty();
    konvaLayer.batchDraw();
    positionMiniToolbar();
  }

  /** state.objects → Konva 노드 전체 재구성. */
  function rebuildAnno() {
    if (!konvaLayer) { return; }
    transformer.nodes([]);
    konvaLayer.find('.anno').forEach(function (n) { n.destroy(); });
    nodeById = {};
    (currentSheet().objects || []).forEach(function (o) {
      var node = buildNode(o);
      if (node) { konvaLayer.add(node); nodeById[o.id] = node; }
    });
    konvaLayer.find('.anno').forEach(function (n) { n.draggable(canSave && annoMode === 'select'); });
    transformer.moveToTop();
    konvaLayer.batchDraw();
    if (selected && nodeById[selected]) { selectNode(nodeById[selected]); }
    else if (selected) { deselect(); }
  }

  /* ---- 선택 / 미니툴바 ---------------------------------------------------- */
  function selectById(id) { var node = nodeById[id]; if (node) { selectNode(node); } else { deselect(); } }

  function selectNode(node) {
    if (!node) { deselect(); return; }
    selected = node.getAttr('objId');
    var t = node.getAttr('annoType');
    var o = findObj(selected);
    var isRich = (t === 'text' && o && o.runs && o.runs.length);
    transformer.keepRatio(t === 'image' ? imageRatioLock : false);
    // 런 텍스트는 이동·회전만(리사이즈 앵커 비활성) — 단색 텍스트/도형은 코너 앵커 유지.
    transformer.enabledAnchors(isRich ? [] : ['top-left', 'top-right', 'bottom-left', 'bottom-right']);
    transformer.nodes([node]);
    transformer.moveToTop();
    showMiniToolbar(node);
    konvaLayer.batchDraw();
  }

  function deselect() {
    selected = null;
    if (transformer) { transformer.nodes([]); }
    hideMiniToolbar();
    hideLogoPopup();
    if (konvaLayer) { konvaLayer.batchDraw(); }
  }

  function showMiniToolbar(node) {
    if (!canSave || !node) { hideMiniToolbar(); return; }
    var t = node.getAttr('annoType');
    var o = findObj(node.getAttr('objId'));
    if (!o) { hideMiniToolbar(); return; }
    els.mtText.hidden = (t !== 'text');
    els.mtImage.hidden = (t !== 'image');
    els.mtShape.hidden = !isShapeType(t);
    els.mt.hidden = false;
    if (t === 'text') { syncTextToolbar(o); }
    else if (t === 'image') { syncImageToolbar(); }
    else { syncShapeToolbar(o); }
    positionMiniToolbar();
  }

  function hideMiniToolbar() { els.mt.hidden = true; }

  function positionMiniToolbar() {
    if (editCtx) { positionEditToolbar(); return; }   // 편집 중이면 오버레이 위 고정 담당
    if (els.mt.hidden || !selected) { return; }
    var node = nodeById[selected];
    if (!node) { return; }
    var box = node.getClientRect();
    var annoRect = els.anno.getBoundingClientRect();
    var screenTop = annoRect.top + box.y * zoom;
    var screenBottom = screenTop + box.height * zoom;
    var screenLeft = annoRect.left + box.x * zoom;
    var top = screenTop - els.mt.offsetHeight - 8;
    if (top < 8) { top = screenBottom + 8; }
    var left = clamp(screenLeft, 8, window.innerWidth - els.mt.offsetWidth - 8);
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

  function syncShapeToolbar(o) {
    Array.prototype.forEach.call(els.mtShape.querySelectorAll('.dws-swatch'), function (sw) {
      sw.classList.toggle('dws-active', sw.getAttribute('data-shape-color').toLowerCase() === String(o.stroke).toLowerCase());
    });
    els.mtStroke.value = String(strokeOrDefault(o.strokeWidth));
  }

  function updateSelectedText(patch) {
    var o = findObj(selected);
    if (!o || o.type !== 'text') { return; }
    recordUndo();
    Object.keys(patch).forEach(function (k) { o[k] = patch[k]; });
    // 선택-모드에서 단색 색/굵기 적용 = 박스 전체 통일 → 런 평탄화(부분 색은 편집모드에서).
    if (('color' in patch) || ('bold' in patch)) { delete o.runs; }
    markDirty();
    rebuildAnno();
    selectById(o.id);
  }

  function updateSelectedShape(patch) {
    var o = findObj(selected);
    if (!o || !isShapeType(o.type)) { return; }
    recordUndo();
    Object.keys(patch).forEach(function (k) { o[k] = patch[k]; });
    if ('stroke' in patch) { lastStrokeColor = patch.stroke; }
    if ('strokeWidth' in patch) { lastStrokeWidth = patch.strokeWidth; }
    markDirty();
    rebuildAnno();
    selectById(o.id);
  }

  /* ---- 삭제 / 이동 -------------------------------------------------------- */
  function removeObject(id) {
    var objs = currentSheet().objects, i = -1;
    objs.some(function (o, idx) { if (o.id === id) { i = idx; return true; } return false; });
    if (i >= 0) { objs.splice(i, 1); }
    rebuildAnno();
  }

  function deleteSelected() {
    if (!canSave || !selected) { return; }
    recordUndo();
    var id = selected;
    deselect();
    removeObject(id);
    markDirty();
  }

  function moveObjectBy(o, dx, dy) {
    if (o.type === 'arrow' || o.type === 'line') {
      o.points = [o.points[0] + dx, o.points[1] + dy, o.points[2] + dx, o.points[3] + dy];
    } else {
      o.x += dx; o.y += dy;
    }
    var node = nodeById[o.id];
    if (!node) { return; }
    if (o.type === 'arrow' || o.type === 'line') { node.points(o.points.slice()); }
    else if (o.type === 'ellipse') { node.x(node.x() + dx); node.y(node.y() + dy); }
    else { node.x(o.x); node.y(o.y); }
    konvaLayer.batchDraw();
  }

  /* ---- 그리기 모드 -------------------------------------------------------- */
  /** 세그먼트 컨트롤 active 동기화: annoMode → 세그 버튼(.dws-seg-active). 이미지 버튼은 모드 아님. */
  function syncSegActive() {
    var activeId = null;
    if (annoMode === 'select') { activeId = 'dws-btn-select'; }
    else if (annoMode === 'text') { activeId = 'dws-btn-add-text'; }
    else if (isShapeType(annoMode)) { activeId = 'dws-btn-shape'; }
    ['dws-btn-select', 'dws-btn-add-text', 'dws-btn-shape'].forEach(function (id) {
      var b = document.getElementById(id);
      if (b) { b.classList.toggle('dws-seg-active', id === activeId); }
    });
  }

  function setAnnoMode(mode) {
    annoMode = mode;
    if (mode !== 'select') { deselect(); }
    if (els.anno) { els.anno.classList.toggle('dws-drawing', mode !== 'select'); }
    if (konvaLayer) {
      konvaLayer.find('.anno').forEach(function (n) { n.draggable(canSave && mode === 'select'); });
    }
    updateModeHint(mode);
    syncSegActive();
    updateDividerState();
  }

  /** 모드 무장 시 캔버스 상단 중앙 힌트 pill 표시/문구 갱신(select면 숨김). */
  function updateModeHint(mode) {
    if (!els.modeHint) { return; }
    var msg = '';
    if (mode === 'text') { msg = '텍스트: 넣을 위치를 클릭 · Esc 취소'; }
    else if (isShapeType(mode)) { msg = '도형: 드래그해서 그리기 · Esc 취소'; }
    if (msg) {
      els.modeHint.textContent = msg;
      els.modeHint.classList.add('dws-mode-hint-show');
    } else {
      els.modeHint.classList.remove('dws-mode-hint-show');
    }
  }

  function onStageMouseDown(e) {
    if (!canSave) { return; }
    /* 같은 물리 클릭의 stage 'mousedown' 이중발화 dedupe(플랫폼별 pointer/mouse
       이중 매핑 방어): 50ms·2px 내 중복 down은 같은 제스처로 보고 무시한다. */
    var devt = e.evt || {};
    var downTs = num(devt.timeStamp);
    var downX = num(devt.clientX);
    var downY = num(devt.clientY);
    if (Math.abs(downTs - lastDownTs) < 50 && Math.abs(downX - lastDownX) < 2 && Math.abs(downY - lastDownY) < 2) { return; }
    lastDownTs = downTs; lastDownX = downX; lastDownY = downY;
    if (editingTextarea) {
      if (Date.now() < textJustOpenedUntil) { return; }   // 방금 연 오버레이 보호(커밋 없이 무시, 2중 방어)
      if (commitActiveEdit) { commitActiveEdit(); }        // 편집 중 바깥 클릭 = 동기 커밋(editingTextarea=null)
      if (annoMode === 'select') { return; }  // select 모드면 커밋만(같은 클릭으로 다음 액션 없음)
      // 텍스트/도형 모드면 아래로 계속 진행 — 같은 클릭이 다음 액션을 시작(좌표는 blur 후에도 유효)
    }
    if (annoMode === 'text') {
      /* [근본 수정] mousedown 브라우저 기본동작(비포커스 대상 클릭 → 기존 포커스 해제)이
         핸들러에서 연 textarea를 즉시 blur→빈 텍스트 삭제한다(실마우스에서만 재현,
         합성 이벤트는 기본동작 미실행). preventDefault로 포커스 이동을 차단한다. */
      if (devt.preventDefault) { devt.preventDefault(); }
      var pt = pointerLogical(devt);
      setAnnoMode('select');
      createTextAt(pt.x, pt.y);
      return;
    }
    if (isShapeType(annoMode)) {
      if (devt.preventDefault) { devt.preventDefault(); }  // 드로잉 제스처 중 네이티브 선택/드래그 기본동작 차단
      startDrawShape(e);
      return;
    }
    /* select 모드 빈 영역 */
    if (e.target !== konvaStage) { return; }
    if (devt.ctrlKey || devt.metaKey) {
      if (devt.preventDefault) { devt.preventDefault(); }  // Ctrl+클릭 텍스트 생성도 동일 보호
      var cp = pointerLogical(devt);
      createTextAt(cp.x, cp.y);
      return;
    }
    deselect();
    passthroughToForm(e.evt);
  }

  function onStageDblClick(e) {
    if (!canSave || annoMode !== 'select') { return; }
    if (e.target !== konvaStage) { return; }
    var evt = e.evt;
    els.anno.style.pointerEvents = 'none';
    var under = document.elementFromPoint(evt.clientX, evt.clientY);
    els.anno.style.pointerEvents = '';
    if (under && els.form.contains(under)) {
      var cell = under.closest('[data-dws-form-key]');
      if (cell) { cell.focus(); }
    }
    /* 빈 영역 더블클릭은 무동작 — 텍스트 생성 경로는 [텍스트] 버튼 + Ctrl+클릭으로 통일 */
  }

  /** 캔버스 빈 영역 클릭을 아래 폼 요소로 투과(폼 셀 편집·체크박스·로고 공존). */
  function passthroughToForm(evt) {
    els.anno.style.pointerEvents = 'none';
    var under = document.elementFromPoint(evt.clientX, evt.clientY);
    var range = document.caretRangeFromPoint ? document.caretRangeFromPoint(evt.clientX, evt.clientY) : null;
    els.anno.style.pointerEvents = '';
    if (!under || !els.form.contains(under)) { return; }
    var cell = under.closest('[data-dws-form-key]');
    if (cell) {
      cell.focus();
      if (range && cell.contains(range.startContainer)) {
        try { var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range); } catch (_) { /* noop */ }
      }
      return;
    }
    var interactive = under.closest('[data-dws-check]') || under.closest('#dws-logo-cell');
    if (interactive) {
      // 로고 셀 열림 제스처: 같은 제스처의 native click(target=캔버스)이 도큐먼트
      // 핸들러의 로고 hide 분기를 타서 팝업이 즉시 닫히는 것을 막는다(450ms 창).
      if (interactive.id === 'dws-logo-cell') { suppressLogoHideUntil = Date.now() + 450; }
      interactive.dispatchEvent(new MouseEvent('click', {
        bubbles: true, cancelable: true, view: window, clientX: evt.clientX, clientY: evt.clientY
      }));
    }
  }

  function startDrawShape(e) {
    var start = pointerLogical(e.evt);
    var mode = annoMode;
    var draft;
    var attrs = { stroke: lastStrokeColor, strokeWidth: lastStrokeWidth, name: 'anno-draft', listening: false };
    if (mode === 'rect') {
      draft = new Konva.Rect({ x: start.x, y: start.y, width: 1, height: 1, fill: 'rgba(0,0,0,0.001)', stroke: attrs.stroke, strokeWidth: attrs.strokeWidth, name: 'anno-draft', listening: false });
    } else if (mode === 'ellipse') {
      draft = new Konva.Ellipse({ x: start.x, y: start.y, radiusX: 1, radiusY: 1, fill: 'rgba(0,0,0,0.001)', stroke: attrs.stroke, strokeWidth: attrs.strokeWidth, name: 'anno-draft', listening: false });
    } else if (mode === 'arrow') {
      draft = new Konva.Arrow({ points: [start.x, start.y, start.x, start.y], stroke: attrs.stroke, strokeWidth: attrs.strokeWidth, fill: attrs.stroke, pointerLength: 12, pointerWidth: 12, name: 'anno-draft', listening: false });
    } else {
      draft = new Konva.Line({ points: [start.x, start.y, start.x, start.y], stroke: attrs.stroke, strokeWidth: attrs.strokeWidth, lineCap: 'round', name: 'anno-draft', listening: false });
    }
    konvaLayer.add(draft);
    transformer.moveToTop();

    // window 레벨 네이티브 리스너: 포인터가 캔버스를 벗어났다 놓아도 그리기가 확정된다.
    function move(nativeEvt) {
      var p = pointerLogical(nativeEvt);
      if (mode === 'rect' || mode === 'ellipse') {
        var x = Math.min(start.x, p.x), y = Math.min(start.y, p.y);
        var w = Math.abs(p.x - start.x), h = Math.abs(p.y - start.y);
        if (mode === 'rect') { draft.setAttrs({ x: x, y: y, width: Math.max(1, w), height: Math.max(1, h) }); }
        else { draft.setAttrs({ x: x + w / 2, y: y + h / 2, radiusX: Math.max(1, w / 2), radiusY: Math.max(1, h / 2) }); }
      } else {
        draft.points([start.x, start.y, p.x, p.y]);
      }
      konvaLayer.batchDraw();
    }
    function up(nativeEvt) {
      window.removeEventListener('mousemove', move, true);
      window.removeEventListener('mouseup', up, true);
      finishDrawShape(draft, mode, start, pointerLogical(nativeEvt));
    }
    window.addEventListener('mousemove', move, true);
    window.addEventListener('mouseup', up, true);
  }

  function finishDrawShape(draft, mode, start, end) {
    draft.destroy();
    setAnnoMode('select');
    var w = Math.abs(end.x - start.x), h = Math.abs(end.y - start.y);
    var dist = Math.sqrt(Math.pow(end.x - start.x, 2) + Math.pow(end.y - start.y, 2));
    var tooSmall = (mode === 'rect' || mode === 'ellipse') ? (w < 8 && h < 8) : (dist < 8);
    if (tooSmall) { konvaLayer.batchDraw(); return; }
    recordUndo();
    var o;
    if (mode === 'rect' || mode === 'ellipse') {
      o = {
        id: rid('o-'), type: mode, x: Math.round(Math.min(start.x, end.x)), y: Math.round(Math.min(start.y, end.y)),
        w: Math.round(w), h: Math.round(h), stroke: lastStrokeColor, strokeWidth: lastStrokeWidth, rotation: 0
      };
    } else {
      o = {
        id: rid('o-'), type: mode,
        points: [Math.round(start.x), Math.round(start.y), Math.round(end.x), Math.round(end.y)],
        stroke: lastStrokeColor, strokeWidth: lastStrokeWidth, rotation: 0
      };
    }
    currentSheet().objects.push(o);
    markDirty();
    rebuildAnno();
    selectById(o.id);
  }

  /* ---- 텍스트 생성 / 인라인 편집 ------------------------------------------ */
  function createTextAt(x, y) {
    if (!canSave) { return; }
    recordUndo();
    var o = {
      id: rid('o-'), type: 'text', x: Math.round(x), y: Math.round(y), w: 220,
      text: '', size: 20, color: '#000000', bold: false, align: 'left', rotation: 0
    };
    currentSheet().objects.push(o);
    markDirty();
    rebuildAnno();
    selectById(o.id);
    startEditText(nodeById[o.id], true);
  }

  function addPreset(kind) {
    if (!canSave) { return; }
    var label = PRESETS[kind];
    if (!label) { return; }
    recordUndo();
    var n = currentSheet().objects.length;
    var o = {
      id: rid('o-'), type: 'text', x: 340 + (n % 3) * 30, y: 95 + (n % 6) * 46, w: 220,
      text: label + '\n', size: 20, color: '#000000', bold: true, align: 'left', rotation: 0
    };
    currentSheet().objects.push(o);
    markDirty();
    rebuildAnno();
    selectById(o.id);
    startEditText(nodeById[o.id], true);
  }

  /* ---- 리치 편집: DOM ↔ 런 변환 헬퍼 ------------------------------------- */
  /** computed color 문자열('rgb(r,g,b)') → '#rrggbb'. 파싱 실패 시 검정. */
  function rgbToHex(rgb) {
    var m = /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i.exec(String(rgb || ''));
    if (!m) { return '#000000'; }
    function h(n) { var s = clamp(parseInt(n, 10) || 0, 0, 255).toString(16); return s.length === 1 ? '0' + s : s; }
    return '#' + h(m[1]) + h(m[2]) + h(m[3]);
  }
  /** computed fontWeight('700'/'bold'/…) → bold 여부(≥600). */
  function isBoldWeight(w) {
    if (w === 'bold' || w === 'bolder') { return true; }
    var n = parseInt(w, 10);
    return isFinite(n) && n >= 600;
  }

  /** contenteditable DOM → raw 런 배열([{t,c,b}]). <br>/블록(div/p) 경계는 '\n'. */
  function extractRuns(rootEl) {
    var raw = [];
    function lastChar() {
      for (var i = raw.length - 1; i >= 0; i--) { if (raw[i].t.length) { return raw[i].t.charAt(raw[i].t.length - 1); } }
      return '';
    }
    function nl() {
      var last = raw[raw.length - 1];   // 개행 스타일 = 직전 런(스타일 감지에 중립)
      raw.push({ t: '\n', c: last ? last.c : '#000000', b: last ? last.b : false });
    }
    function emit(text, styleEl) {
      if (!text) { return; }
      var cs = window.getComputedStyle(styleEl);
      raw.push({ t: text, c: rgbToHex(cs.color), b: isBoldWeight(cs.fontWeight) });
    }
    function walk(node, styleEl) {
      for (var child = node.firstChild; child; child = child.nextSibling) {
        if (child.nodeType === 3) {
          emit(child.nodeValue, styleEl);
        } else if (child.nodeType === 1) {
          var tag = child.tagName;
          if (tag === 'BR') {
            if (child.nextSibling) { nl(); }   // 블록 끝의 filler <br> 은 무시(중복 개행 방지)
          } else if (tag === 'DIV' || tag === 'P') {
            if (raw.length && lastChar() !== '\n') { nl(); }
            walk(child, child);
          } else {
            walk(child, child);   // span/b/font 등 인라인: 스타일은 자기 요소에서
          }
        }
      }
    }
    walk(rootEl, rootEl);
    return raw;
  }

  /** raw 런에서 첫 유효(개행 제외) 런 — 단색 폴백 시 색/굵기 근거. */
  function firstStyleRun(raw) {
    for (var i = 0; i < raw.length; i++) {
      if (String(raw[i].t).replace(/\n/g, '') !== '') { return raw[i]; }
    }
    return null;
  }

  /** 오버레이 초기 콘텐츠 주입: runs → span 시퀀스, 없으면 플레인. textContent 만(XSS 안전). */
  function fillOverlay(area, o) {
    area.textContent = '';
    if (o.runs && o.runs.length) {
      o.runs.forEach(function (r) {
        var parts = String(r.t).split('\n');
        for (var i = 0; i < parts.length; i++) {
          if (i > 0) { area.appendChild(document.createElement('br')); }
          if (parts[i] !== '') {
            var span = document.createElement('span');
            span.style.color = colorOrDefault(r.c);
            span.style.fontWeight = r.b ? '700' : '400';
            span.textContent = parts[i];   // 사용자 문자열은 textContent 로만 삽입
            area.appendChild(span);
          }
        }
      });
    } else {
      var lines = String(o.text || '').split('\n');
      for (var j = 0; j < lines.length; j++) {
        if (j > 0) { area.appendChild(document.createElement('br')); }
        if (lines[j] !== '') { area.appendChild(document.createTextNode(lines[j])); }
      }
    }
  }

  /* ---- 리치 편집: 선택/스타일 적용 --------------------------------------- */
  function selectAllIn(area) {
    var range = document.createRange();
    range.selectNodeContents(area);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }
  /** 오버레이 내부에 비collapsed 선택이 있으면 true(부분 적용 대상). */
  function selectionInside(area) {
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) { return false; }
    return area.contains(sel.anchorNode) && area.contains(sel.focusNode);
  }
  function applyEditStyle(cmd, value) {
    if (!editCtx) { return; }
    var area = editCtx.area;
    area.focus();
    try { document.execCommand('styleWithCSS', false, true); } catch (_) { /* noop */ }
    if (!selectionInside(area)) { selectAllIn(area); }   // collapsed/외부 = 전체 적용
    try { document.execCommand(cmd, false, value); } catch (_) { /* noop */ }
  }
  function applyEditColor(color) { applyEditStyle('foreColor', color); syncEditToolbar(); }
  function applyEditBold() { applyEditStyle('bold', null); syncEditToolbar(); }
  function setEditFontSize(size) {
    if (!editCtx) { return; }
    editCtx.size = sizeOrDefault(size);
    editCtx.area.style.fontSize = (editCtx.size * zoom) + 'px';
    editCtx.area.focus();
    positionEditToolbar();
  }
  function setEditAlign(align) {
    if (!editCtx) { return; }
    editCtx.align = (align === 'center') ? 'center' : 'left';
    editCtx.area.style.textAlign = editCtx.align;
    editCtx.area.focus();
    syncEditToolbar();
  }

  /* ---- 리치 편집: 편집 중 미니바(오버레이 위 고정, 삭제 버튼 숨김) -------- */
  function showEditToolbar() {
    els.mtText.hidden = false;
    els.mtImage.hidden = true;
    els.mtShape.hidden = true;
    els.mt.hidden = false;
    els.mt.classList.add('dws-mt-editing');   // CSS: 편집 중 삭제 버튼 숨김
    syncEditToolbar();
    positionEditToolbar();
  }
  function hideEditToolbar() {
    els.mt.classList.remove('dws-mt-editing');
    els.mt.hidden = true;
  }
  function positionEditToolbar() {
    if (!editCtx) { return; }
    var r = editCtx.area.getBoundingClientRect();
    var top = r.top - els.mt.offsetHeight - 8;
    if (top < 8) { top = r.bottom + 8; }
    var left = clamp(r.left, 8, window.innerWidth - els.mt.offsetWidth - 8);
    els.mt.style.left = left + 'px';
    els.mt.style.top = top + 'px';
  }
  function syncEditToolbar() {
    if (!editCtx) { return; }
    els.mtSize.value = String(editCtx.size);
    els.mtAlign.textContent = (editCtx.align === 'center') ? '중' : '좌';
    els.mtAlign.classList.toggle('dws-active', editCtx.align === 'center');
    // 편집 중 스와치/굵기 활성표시는 caret 스타일로 정확 판별이 어려워 중립(비활성)로 둔다.
    Array.prototype.forEach.call(els.mtText.querySelectorAll('.dws-swatch'), function (sw) { sw.classList.remove('dws-active'); });
    els.mtBold.classList.remove('dws-active');
  }

  /** contenteditable 오버레이 인라인 편집 → blur/Esc 커밋. 커밋 시 DOM→런 추출. */
  function startEditText(node, isNew) {
    if (!canSave || !node) { return; }
    if (commitActiveEdit) { commitActiveEdit(); }
    var o = findObj(node.getAttr('objId'));
    if (!o) { return; }
    if (!isNew) { recordUndo(); }

    transformer.nodes([]);
    hideMiniToolbar();
    node.hide();
    konvaLayer.batchDraw();

    var annoRect = els.anno.getBoundingClientRect();
    var pos = node.absolutePosition();
    var size = sizeOrDefault(o.size);
    var align = (o.align === 'center') ? 'center' : 'left';
    var area = document.createElement('div');
    area.className = 'dws-text-overlay';
    area.setAttribute('contenteditable', 'true');
    area.setAttribute('spellcheck', 'false');
    area.style.left = (annoRect.left + pos.x * zoom) + 'px';
    area.style.top = (annoRect.top + pos.y * zoom) + 'px';
    area.style.minWidth = Math.max(40, num(o.w, 40) * zoom) + 'px';
    area.style.fontSize = (size * zoom) + 'px';
    area.style.fontFamily = ANNO_FONT;
    area.style.fontWeight = o.bold ? '700' : '400';
    area.style.color = colorOrDefault(o.color);
    area.style.textAlign = align;
    fillOverlay(area, o);
    document.body.appendChild(area);
    editingTextarea = area;
    editCtx = { id: o.id, area: area, isNew: !!isNew, size: size, align: align };
    textJustOpenedUntil = Date.now() + 450;   // 보호창: 직후 stage down의 handler-blur 방지(2중 방어)

    try { document.execCommand('styleWithCSS', false, true); } catch (_) { /* noop */ }
    showEditToolbar();
    area.focus();
    selectAllIn(area);

    var done = false;
    function commit() {
      if (done) { return; }
      done = true;
      var ctxSize = editCtx ? editCtx.size : size;
      var ctxAlign = editCtx ? editCtx.align : align;
      editingTextarea = null;
      editCtx = null;
      commitActiveEdit = null;
      hideEditToolbar();
      var raw = extractRuns(area);
      if (area.parentNode) { area.parentNode.removeChild(area); }
      var cur = findObj(o.id);
      if (!cur) { node.destroy(); konvaLayer.batchDraw(); return; }
      var text = raw.map(function (r) { return r.t; }).join('');
      if (text.trim() === '') {
        var wasSelected = (selected === o.id);
        removeObject(o.id);
        if (wasSelected) { deselect(); }
        markDirty();
        return;
      }
      cur.size = ctxSize;
      cur.align = ctxAlign;
      var runs = sanitizeRuns(raw);
      if (runs) {
        cur.runs = runs;
        cur.text = runs.map(function (r) { return r.t; }).join('');
        cur.color = runs[0].c; cur.bold = !!runs[0].b;
      } else {
        delete cur.runs;
        cur.text = text;
        var fv = firstStyleRun(raw);
        if (fv) { cur.color = fv.c; cur.bold = fv.b; }
      }
      markDirty();
      rebuildAnno();
      if (selected === o.id) { selectById(o.id); }
      else { konvaLayer.batchDraw(); }
    }
    commitActiveEdit = commit;

    area.addEventListener('blur', function (e) {
      // 미니바(크기 select 등)로 포커스 이동 = 편집 유지(커밋 아님). 그 외 바깥 = 커밋.
      if (e.relatedTarget && els.mt && els.mt.contains(e.relatedTarget)) { return; }
      commit();
    });
    area.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { e.preventDefault(); commit(); return; }
      /* Enter = 줄바꿈(contenteditable 기본). 커밋은 blur/Esc. */
    });
    area.addEventListener('input', function () { positionEditToolbar(); });
  }

  /* ---- 이미지 업로드 / 생성 ----------------------------------------------- */
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
          w: w, h: h, key: key, natural_w: nw, natural_h: nh, rotation: 0
        };
        if (o.y < 70) { o.y = 70; }
        currentSheet().objects.push(o);
        markDirty();
        rebuildAnno();
        selectById(o.id);
      };
      img.onerror = function () { toast('이미지를 불러오지 못했습니다.'); };
      img.src = url;
    }).catch(function (err) { console.warn('[dws] asset upload', err); toast('이미지 업로드 오류'); });
  }

  /* ========================================================================
   * [5] toolbar (앱바 · 미니툴바 · 탭 · 줌 · 로고팝업 · 메뉴)
   * ====================================================================== */
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
    setAnnoMode('select');
    current = i;
    deselect();
    undoStack.length = 0;
    redoStack.length = 0;
    renderTabs();
    renderForm();
    rebuildAnno();
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
    rebuildAnno();
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
    rebuildAnno();
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
    positionMiniToolbar();
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
    if (els.shapeMenu) { els.shapeMenu.hidden = true; }
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
    updateDividerState();
  }

  /* ========================================================================
   * [6] save / load
   * ====================================================================== */
  function serializeObj(o) {
    var rot = normalizeRotation(o.rotation);
    if (o.type === 'image') {
      return {
        id: o.id, type: 'image',
        x: clampCoord(o.x), y: clampCoord(o.y), w: clampDim(o.w), h: clampDim(o.h),
        key: o.key, natural_w: num(o.natural_w, 0), natural_h: num(o.natural_h, 0), rotation: rot
      };
    }
    if (o.type === 'rect' || o.type === 'ellipse') {
      return {
        id: o.id, type: o.type,
        x: clampCoord(o.x), y: clampCoord(o.y), w: clampDim(o.w), h: clampDim(o.h),
        stroke: colorOrDefault(o.stroke), strokeWidth: strokeOrDefault(o.strokeWidth), rotation: rot
      };
    }
    if (o.type === 'arrow' || o.type === 'line') {
      return {
        id: o.id, type: o.type, points: normalizePoints(o.points),
        stroke: colorOrDefault(o.stroke), strokeWidth: strokeOrDefault(o.strokeWidth), rotation: rot
      };
    }
    if (o.type === 'text') {
      var txt = {
        id: o.id, type: 'text',
        x: clampCoord(o.x), y: clampCoord(o.y), w: clampDim(o.w),
        text: String(o.text || ''), size: sizeOrDefault(o.size),
        color: colorOrDefault(o.color), bold: !!o.bold,
        align: (o.align === 'center') ? 'center' : 'left', rotation: rot
      };
      var runs = sanitizeRuns(o.runs);
      if (runs) {
        txt.runs = runs;
        txt.text = runs.map(function (r) { return r.t; }).join('');   // 서버 계약: join(t)==text
        txt.color = runs[0].c; txt.bold = !!runs[0].b;
      }
      return txt;
    }
    return null;
  }

  function serializeForm(f) {
    f = f || {};
    var o = {};
    Object.keys(f).forEach(function (k) {
      if (k === 'checks' || k === 'layout' || k === 'cell_font') { return; }
      o[k] = (f[k] == null) ? '' : String(f[k]);
    });
    o.checks = {};
    var ck = f.checks || {};
    Object.keys(ck).forEach(function (k) { o.checks[k] = !!ck[k]; });
    o.layout = sanitizeLayout(f.layout);
    o.cell_font = sanitizeCellFont(f.cell_font);
    return o;
  }

  function serializeState() {
    return {
      v: 1,
      sheets: state.sheets.map(function (s) {
        return {
          id: s.id, name: s.name, form: serializeForm(s.form),
          objects: (s.objects || []).map(serializeObj).filter(function (o) { return !!o; })
        };
      })
    };
  }

  function mergeFormDefaults(saved) {
    var base = {};
    var d = defaults || {};
    Object.keys(d).forEach(function (k) { if (k !== 'checks') { base[k] = d[k]; } });
    saved = saved || {};
    Object.keys(saved).forEach(function (k) { if (k !== 'checks' && k !== 'layout' && k !== 'cell_font') { base[k] = saved[k]; } });
    var checks = {}, dk = d.checks || {}, sk = saved.checks || {};
    CHECK_KEYS.forEach(function (k) { checks[k] = (k in sk) ? !!sk[k] : !!dk[k]; });
    base.checks = checks;
    base.layout = sanitizeLayout(saved.layout);
    base.cell_font = sanitizeCellFont(saved.cell_font);
    return base;
  }

  /** 저장 상태 → 런타임 객체. v1(text/image, rotation 없음)은 기본값 보충해 무손실 로드. */
  function normalizeObj(o) {
    var rot = num(o.rotation);
    if (o.type === 'image') {
      return {
        id: o.id || rid('o-'), type: 'image',
        x: num(o.x), y: num(o.y), w: num(o.w, 200), h: num(o.h, 150),
        key: o.key || '', natural_w: num(o.natural_w, 0), natural_h: num(o.natural_h, 0), rotation: rot
      };
    }
    if (o.type === 'rect' || o.type === 'ellipse') {
      return {
        id: o.id || rid('o-'), type: o.type,
        x: num(o.x), y: num(o.y), w: num(o.w, 80), h: num(o.h, 60),
        stroke: colorOrDefault(o.stroke), strokeWidth: strokeOrDefault(o.strokeWidth), rotation: rot
      };
    }
    if (o.type === 'arrow' || o.type === 'line') {
      return {
        id: o.id || rid('o-'), type: o.type, points: normalizePoints(o.points),
        stroke: colorOrDefault(o.stroke), strokeWidth: strokeOrDefault(o.strokeWidth), rotation: rot
      };
    }
    var text = {
      id: o.id || rid('o-'), type: 'text',
      x: num(o.x), y: num(o.y), w: num(o.w, 220),
      text: String(o.text || ''), size: sizeOrDefault(o.size), color: colorOrDefault(o.color),
      bold: !!o.bold, align: (o.align === 'center') ? 'center' : 'left', rotation: rot
    };
    if (o.runs) { text.runs = o.runs; syncTextFromRuns(text); }   // 런 있으면 불변식 동기(text/color/bold)
    return text;
  }

  function normalizeState(st) {
    var sheets = ((st && st.sheets) || []).map(function (s) {
      return {
        id: s.id || rid('s-'),
        name: s.name || '도면',
        form: serializeForm(mergeFormDefaults(s.form)),
        objects: (s.objects || [])
          .filter(function (o) { return o && ['text', 'image', 'rect', 'ellipse', 'arrow', 'line'].indexOf(o.type) >= 0; })
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
      setAnnoMode('select');
      applyPermissions();
      wireFormEditing();
      renderTabs();
      renderForm();
      rebuildAnno();
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
    if (commitActiveEdit) { commitActiveEdit(); }
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

  /**
   * 내보내기 합성(§3.5): 폼(html2canvas scale=2) + Konva(toCanvas pixelRatio=2)를
   * 오프스크린 2956x2080 캔버스에 순서대로 draw → 합성 canvas 반환.
   */
  function withExportMode() {
    if (commitActiveEdit) { commitActiveEdit(); }
    if (document.activeElement && document.activeElement.blur) { document.activeElement.blur(); }
    var prevZoom = zoom;
    deselect();
    root.classList.add('dws-exporting');
    setZoom(1);
    els.anno.style.visibility = 'hidden';
    function restore() {
      els.anno.style.visibility = '';
      root.classList.remove('dws-exporting');
      setZoom(prevZoom);
    }
    return ensureHtml2canvas().then(function () {
      return window.html2canvas(els.stage, { scale: 2, backgroundColor: '#ffffff', useCORS: true, logging: false });
    }).then(function (formCanvas) {
      var out = document.createElement('canvas');
      out.width = STAGE_W * 2;
      out.height = STAGE_H * 2;
      var ctx = out.getContext('2d');
      ctx.drawImage(formCanvas, 0, 0, out.width, out.height);
      var annoCanvas = konvaStage.toCanvas({ pixelRatio: 2 });
      ctx.drawImage(annoCanvas, 0, 0, out.width, out.height);
      restore();
      return out;
    }).catch(function (err) {
      restore();
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
    document.getElementById('dws-btn-select').addEventListener('click', function () {
      setAnnoMode('select');
    });
    document.getElementById('dws-btn-add-text').addEventListener('click', function () {
      setAnnoMode(annoMode === 'text' ? 'select' : 'text');
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

    // 도형 메뉴 → 그리기 모드 진입
    var shapeBtn = document.getElementById('dws-btn-shape');
    shapeBtn.addEventListener('click', function (e) { e.stopPropagation(); toggleMenu(els.shapeMenu); });
    Array.prototype.forEach.call(els.shapeMenu.querySelectorAll('[data-shape]'), function (b) {
      b.addEventListener('click', function () { closeMenus(); setAnnoMode(b.getAttribute('data-shape')); });
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

    // 표 글자 크기(A− / A+)
    if (els.fontDecBtn) { els.fontDecBtn.addEventListener('click', function () { bumpCellFont(-1); }); }
    if (els.fontIncBtn) { els.fontIncBtn.addEventListener('click', function () { bumpCellFont(1); }); }

    // 내보내기 메뉴
    var exportBtn = document.getElementById('dws-btn-export');
    exportBtn.addEventListener('click', function (e) { e.stopPropagation(); toggleMenu(els.exportMenu); });
    document.getElementById('dws-btn-export-png').addEventListener('click', exportPng);
    document.getElementById('dws-btn-export-transfer').addEventListener('click', openTransferDialog);

    // 미니 툴바 — 텍스트 (편집 중이면 선택범위/전체에 실시간 적용, 아니면 선택 객체 통일)
    // 편집 중 미니바 버튼 클릭이 오버레이 포커스/선택을 뺏지 않도록 mousedown 기본동작 차단
    // (크기 select 는 드롭다운을 열어야 하므로 예외 — blur relatedTarget 로 커밋만 억제).
    els.mt.addEventListener('mousedown', function (e) {
      if (!editCtx) { return; }
      if (e.target === els.mtSize || els.mtSize.contains(e.target)) { return; }
      e.preventDefault();
    });
    els.mtSize.addEventListener('change', function () {
      var size = parseInt(els.mtSize.value, 10);
      if (editCtx) { setEditFontSize(size); } else { updateSelectedText({ size: size }); }
    });
    Array.prototype.forEach.call(els.mtText.querySelectorAll('.dws-swatch'), function (sw) {
      sw.addEventListener('click', function () {
        var color = sw.getAttribute('data-color');
        if (editCtx) { applyEditColor(color); } else { updateSelectedText({ color: color }); }
      });
    });
    els.mtBold.addEventListener('click', function () {
      if (editCtx) { applyEditBold(); return; }
      var o = findObj(selected); if (o && o.type === 'text') { updateSelectedText({ bold: !o.bold }); }
    });
    els.mtAlign.addEventListener('click', function () {
      if (editCtx) { setEditAlign(editCtx.align === 'center' ? 'left' : 'center'); return; }
      var o = findObj(selected); if (o && o.type === 'text') { updateSelectedText({ align: o.align === 'center' ? 'left' : 'center' }); }
    });
    document.getElementById('dws-mt-del-text').addEventListener('click', deleteSelected);

    // 미니 툴바 — 이미지
    els.mtRatio.addEventListener('click', function () {
      imageRatioLock = !imageRatioLock;
      if (transformer && selected && nodeById[selected] && nodeById[selected].getAttr('annoType') === 'image') {
        transformer.keepRatio(imageRatioLock);
        konvaLayer.batchDraw();
      }
      syncImageToolbar();
    });
    document.getElementById('dws-mt-del-image').addEventListener('click', deleteSelected);

    // 미니 툴바 — 도형
    Array.prototype.forEach.call(els.mtShape.querySelectorAll('.dws-swatch'), function (sw) {
      sw.addEventListener('click', function () { updateSelectedShape({ stroke: sw.getAttribute('data-shape-color') }); });
    });
    els.mtStroke.addEventListener('change', function () { updateSelectedShape({ strokeWidth: parseInt(els.mtStroke.value, 10) }); });
    document.getElementById('dws-mt-del-shape').addEventListener('click', deleteSelected);

    // 로고 팝업
    Array.prototype.forEach.call(els.logoPopup.querySelectorAll('[data-logo]'), function (b) {
      b.addEventListener('click', function (e) { e.stopPropagation(); setLogo(b.getAttribute('data-logo')); hideLogoPopup(); });
    });

    // 전달 다이얼로그
    document.getElementById('dws-transfer-cancel').addEventListener('click', closeTransferDialog);
    els.transferSubmit.addEventListener('click', doTransfer);

    // 문서 레벨: 메뉴/팝업 바깥 클릭 닫기
    document.addEventListener('click', function (e) {
      if (!e.target.closest('.dws-dropdown')) { closeMenus(); }
      if (Date.now() < suppressLogoHideUntil) {
        /* 로고 셀 열림 제스처의 같은 native click만 무시(이후 바깥 클릭은 정상 닫힘) */
      } else if (!e.target.closest('#dws-logo-popup') && !e.target.closest('#dws-logo-cell')) {
        hideLogoPopup();
      }
    });

    // 문서 레벨 붙여넣기: 폼 셀 편집 중이면 plain text, 텍스트 편집 중이면 기본, 아니면 클립보드 이미지 업로드
    document.addEventListener('paste', function (e) {
      if (!canSave) { return; }
      var ae = document.activeElement;
      if (ae && (ae.tagName === 'TEXTAREA' || ae.tagName === 'INPUT')) { return; }
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

    // 키보드: 저장 / undo·redo / 삭제 / 화살표 이동 / Esc
    document.addEventListener('keydown', function (e) {
      var ae = document.activeElement;
      var editing = !!(ae && (ae.isContentEditable || ae.tagName === 'TEXTAREA' || ae.tagName === 'INPUT' || ae.tagName === 'SELECT'));
      var meta = e.ctrlKey || e.metaKey;
      if (meta && (e.key === 's' || e.key === 'S')) { e.preventDefault(); save(); return; }
      if (editing) { return; }
      if (e.key === 'Escape') {
        if (annoMode !== 'select') { setAnnoMode('select'); } else { deselect(); }
        return;
      }
      /* 'T' 단축키(수정자 없음, 한글 자판은 code 기준): 텍스트 모드 무장.
         Ctrl+T는 Chrome 예약 단축키라 웹페이지가 가로챌 수 없어 무수정자 T로 대체. */
      if (canSave && !meta && !e.altKey && (e.key === 't' || e.key === 'T' || e.code === 'KeyT')) {
        e.preventDefault();
        setAnnoMode('text');
        return;
      }
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
      moveObjectBy(o, dx, dy);
      markDirty();
      positionMiniToolbar();
    });

    // 스크롤/리사이즈 시 미니툴바 위치 갱신
    els.canvas.addEventListener('scroll', function () { positionMiniToolbar(); });
    window.addEventListener('resize', function () { positionMiniToolbar(); });

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
    if (typeof window.Konva === 'undefined') {
      console.error('[dws] Konva 라이브러리를 불러오지 못했습니다.');
      if (els.toastHost) { toast('주석 엔진(Konva)을 불러오지 못했습니다. 새로고침해 주세요.'); }
      return;
    }
    createKonva();
    cacheLayoutEls();
    buildDividers();
    wireStatic();
    load();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();

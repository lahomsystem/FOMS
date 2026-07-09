/* ============================================================================
 * 도면 마법사 (Drawing Wizard) — 프론트 에디터 (v2 Konva 주석 엔진)
 *
 * 독립 페이지 에디터. 스테이지(논리 1478x1040) 위에 양식 폼(DOM) + 자유 주석
 * 레이어(Konva Stage)를 배치하고, 상태를 structured_data['drawing_wizard']에 저장한다.
 * 주석은 텍스트/이미지/사각형/원/화살표/선 6종을 지원하며 선택·이동·리사이즈·회전이
 * 가능하다. 내보내기는 폼(html2canvas scale=2) + Konva(toCanvas pixelRatio=2)를 오프스크린
 * 캔버스에 합성해 PNG 생성 → 다운로드. 저장 시 PNG는 '전달 대기함'에 보관되며(도면 탭 저장
 * 아님), 담당자 전달은 도면 작업실의 일괄 전송이 담당한다.
 *
 * 밴드: config/api → state/history → form render → anno(Konva) → toolbar →
 *       save/load → export/version → init
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
  /* 프리핸드 펜(손그림) — 팔레트 굵기 후보 + 허용 범위, 스트로크 좌표 상한(백엔드 _PEN_MAX_POINTS 정합). */
  var PEN_WIDTHS = [2, 4, 7];
  var PEN_WIDTH_DEFAULT = 4, PEN_MIN_WIDTH = 1, PEN_MAX_WIDTH = 20;
  var PEN_MAX_COORDS = 400;            // 스트로크 좌표(x,y 쌍) 상한 = 200점(64KB·200객체 보호)
  var PEN_MIN_STEP_SQ = 4;             // 점 단순화: 직전 점과 논리거리² < 4(=2px) 이면 skip
  var PEN_TENSION = 0.4;               // Konva.Line 곡선 장력(손그림 부드럽게)
  /* 형광펜(highlighter) — 펜 인프라 확장: 반투명(opacity) + 굵은 폭 + 형광 색. 굵기는 백엔드
     펜 상한(1~20) 이내로 유지한다(초과분은 penWidthOrDefault 가 클램프). */
  var HI_WIDTH_DEFAULT = 16;           // 형광펜 기본 굵기(px) — 펜 상한 20 이내
  var HI_COLOR_DEFAULT = '#ffd400';    // 형광펜 기본 색(노랑)
  var HI_OPACITY = 0.35;               // 형광펜 반투명도(0<x≤1)
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
  /* select 모드 미니툴바·이동에서 pen 을 line 처럼 다루기 위한 판별(그리기 세그/힌트에는 미포함). */
  function isStrokeType(t) { return isShapeType(t) || t === 'pen'; }

  /** 펜 굵기 정규화: 1~20 정수(이상치는 기본 4). 팔레트 2/4/7·도형 편집 1~3 모두 포용. */
  function penWidthOrDefault(w) { return clamp(Math.round(num(w, PEN_WIDTH_DEFAULT)), PEN_MIN_WIDTH, PEN_MAX_WIDTH); }

  /** 펜 불투명도 정규화: 반투명(0<x<1)이면 소수 3자리로 보존, 아니면 null(불투명=필드 생략).
      형광펜은 HI_OPACITY(0.35)로 저장되고 일반 펜은 필드 없음(=1, 하위호환). */
  function penOpacityOrNull(v) {
    if (typeof v === 'number' && isFinite(v) && v > 0 && v < 1) { return Math.round(v * 1000) / 1000; }
    return null;
  }

  /** 펜 획 좌표 정규화: 짝수 길이(불완전 trailing 제거) + 각 좌표 반올림·클램프 + 상한 절단. */
  function normalizePenPoints(pts) {
    var src = Array.isArray(pts) ? pts : [];
    var n = src.length - (src.length % 2);
    if (n > PEN_MAX_COORDS) { n = PEN_MAX_COORDS; }
    var out = [];
    for (var i = 0; i < n; i++) { out.push(clamp(Math.round(num(src[i])), -2000, 4000)); }
    return out;
  }

  /** points(x,y 쌍 나열)를 dx/dy 만큼 평행이동한 새 배열(가변 길이 — pen/arrow/line 공용). */
  function shiftPoints(points, dx, dy) {
    var out = [];
    var src = Array.isArray(points) ? points : [];
    for (var i = 0; i + 1 < src.length; i += 2) { out.push(src[i] + dx, src[i + 1] + dy); }
    return out;
  }

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
  var userPresets = [];                // 도면팀 공유 사용자 프리셋 [{label,text}] (전역 SystemSetting)
  var defaults = {};
  var products = [];                   // 주문 제품 리스트 [{index,name,spec,price}] (좌측 패널 소스)
  var measurePhotos = [];              // 실측 사진 [{key,filename,item_index,thumb_url}] (사이드 참조 소스)
  var customerName = '';
  var selected = null;                 // 주 선택(primary) 주석 객체 id — 단일 선택 경로 호환용(selectedIds 의 마지막)
  var selectedIds = [];                // 다중 선택 id 배열(SSOT). 단일=길이1, 없음=길이0, 그룹=길이≥2
  var zoom = 1;
  var imageRatioLock = true;
  var undoStack = [];
  var redoStack = [];
  var lastArrowUndoTs = 0;

  /* 저장 조율 상태 (자동 저장 · 저장+전달 원클릭 공용) */
  var saveInFlight = false;            // 저장 요청 진행 중(중복 저장·자동 저장 억제)
  var dragActive = false;             // 노드 드래그/변형·경계선 드래그 진행 중(자동 저장 억제)
  var AUTOSAVE_INTERVAL_MS = 45000;   // 자동 저장 주기(45초)
  var autosaveTimer = null;           // setInterval 핸들(단일)
  var autoConflictWarned = false;     // 자동 저장 409 경고 1회성 플래그(성공 시 해제)

  /* Konva 런타임 상태 */
  var konvaStage = null;
  var konvaLayer = null;
  var transformer = null;
  var nodeById = {};                   // objId → Konva 노드
  var annoMode = 'select';             // 'select'|'text'|'rect'|'ellipse'|'arrow'|'line'|'pen'|'eraser'
  var lastStrokeColor = '#000000';     // 다음 도형 기본 선 색
  var lastStrokeWidth = 2;             // 다음 도형 기본 선 굵기
  var penColor = '#e11d1d';            // 펜 색(종이 마크업 관례상 빨강 기본)
  var penWidth = PEN_WIDTH_DEFAULT;    // 펜 굵기(px)
  var penMode = 'pen';                 // 펜 팔레트 서브모드 'pen'|'hi'(형광펜) — 색/굵기/반투명 분기
  var hiColor = HI_COLOR_DEFAULT;      // 형광펜 색
  var hiWidth = HI_WIDTH_DEFAULT;      // 형광펜 굵기(px)
  var isDrawingPen = false;            // 프리핸드/지우개 포인터 스트로크 진행 중(터치 팬/핀치 억제 = 팜 리젝션)
  var lastPointerType = 'mouse';       // 최근 스테이지 pointerdown 입력 종류(pen/mouse/touch) — 손가락 드래그 차단용
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
    var cs = currentSheet();
    if (!cs) { return null; }
    var objs = cs.objects || [];
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
    els.products = document.getElementById('dws-products');
    els.productList = document.getElementById('dws-product-list');
    els.productToggle = document.getElementById('dws-products-toggle');
    els.photos = document.getElementById('dws-photos');
    els.photosTitle = document.getElementById('dws-photos-title');
    els.photosToggle = document.getElementById('dws-photos-toggle');
    els.photoGrid = document.getElementById('dws-photo-grid');
    els.pending = document.getElementById('dws-pending');
    els.pendingTitle = document.getElementById('dws-pending-title');
    els.pendingToggle = document.getElementById('dws-pending-toggle');
    els.pendingGrid = document.getElementById('dws-pending-grid');
    els.delSavedBtn = document.getElementById('dws-btn-delete-saved');
    els.lightbox = document.getElementById('dws-lightbox');
    els.lightboxImg = document.getElementById('dws-lightbox-img');
    els.lightboxClose = document.getElementById('dws-lightbox-close');
    els.tabbar = document.getElementById('dws-tabbar');
    els.canvas = document.getElementById('dws-canvas');
    els.empty = document.getElementById('dws-empty');
    els.emptyAdd = document.getElementById('dws-empty-add');
    els.wrap = document.getElementById('dws-stage-wrap');
    els.stage = document.getElementById('dws-stage');
    els.form = document.getElementById('dws-form');
    els.anno = document.getElementById('dws-anno');
    els.logoCell = document.getElementById('dws-logo-cell');
    els.logoImg = document.getElementById('dws-logo-img');
    els.logoPopup = document.getElementById('dws-logo-popup');
    els.saveBtn = document.getElementById('dws-btn-save');
    els.saveAllBtn = document.getElementById('dws-btn-save-all');
    els.zoomRange = document.getElementById('dws-zoom-range');
    els.zoomLabel = document.getElementById('dws-zoom-label');
    els.fileInput = document.getElementById('dws-file-input');
    els.presetMenu = document.getElementById('dws-preset-menu');
    els.shapeMenu = document.getElementById('dws-shape-menu');
    els.exportMenu = document.getElementById('dws-export-menu');
    els.mt = document.getElementById('dws-minitoolbar');
    els.mtText = document.getElementById('dws-mt-text');
    els.mtPresetBtn = document.getElementById('dws-mt-preset-btn');
    els.mtPresetMenu = document.getElementById('dws-mt-preset-menu');
    els.mtImage = document.getElementById('dws-mt-image');
    els.mtShape = document.getElementById('dws-mt-shape');
    els.mtSize = document.getElementById('dws-mt-size');
    els.mtBold = document.getElementById('dws-mt-bold');
    els.mtAlign = document.getElementById('dws-mt-align');
    els.mtRatio = document.getElementById('dws-mt-ratio');
    els.mtStroke = document.getElementById('dws-mt-stroke');
    els.versionDialog = document.getElementById('dws-version-dialog');
    els.versionList = document.getElementById('dws-version-list');
    els.toastHost = document.getElementById('dws-toast-host');
    els.mobileNotice = document.getElementById('dws-mobile-notice');
    els.modeHint = document.getElementById('dws-mode-hint');
    els.penPalette = document.getElementById('dws-pen-palette');
    els.fontDecBtn = document.getElementById('dws-btn-font-dec');
    els.fontIncBtn = document.getElementById('dws-btn-font-inc');
    els.tableResetBtn = document.getElementById('dws-btn-table-reset');
    els.dividers = document.getElementById('dws-dividers');
    els.alignToolbar = document.getElementById('dws-aligntoolbar');
  }

  function formCells() { return Array.prototype.slice.call(els.form.querySelectorAll('[data-dws-form-key]')); }
  function checkEls() { return Array.prototype.slice.call(els.form.querySelectorAll('[data-dws-check]')); }

  function renderForm() {
    var cs = currentSheet();
    if (!cs) { return; }   // 시트 0개(빈 상태): 빈 안내 오버레이는 renderTabs 가 표시
    var form = cs.form || {};
    formCells().forEach(function (el) {
      var k = el.getAttribute('data-dws-form-key');
      el.textContent = (form[k] != null) ? String(form[k]) : '';
    });
    renderChecks();
    renderLogo(form.logo);
    applyFormLayout(cs);
  }

  function renderChecks() {
    var cs = currentSheet();
    if (!cs) { return; }
    var checks = (cs.form || {}).checks || {};
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
    var cs = currentSheet();
    if (!cs) { return; }
    cs.form[k] = el.textContent;
    markDirty();
  }

  function toggleCheck(key) {
    if (!canSave || !currentSheet()) { return; }
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
    var s = sheet || currentSheet();
    if (!s) { return; }
    var form = s.form || {};
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
    var cs = currentSheet();
    if (!cs) { return; }
    L = L || sanitizeLayout(cs.form.layout);
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
      if (!canSave || annoMode !== 'select' || !currentSheet()) { return; }
      var now = Date.now();
      if (now - (el.__dwsTapTs || 0) < 320) {   // 두 번째 탭 = 초기화(dblclick 합성 억제와 무관)
        el.__dwsTapTs = 0; e.preventDefault(); e.stopPropagation();
        resetDivider(meta); return;
      }
      el.__dwsTapTs = now;
      e.preventDefault(); e.stopPropagation();
      try { el.setPointerCapture(e.pointerId); } catch (_) { /* noop */ }
      drag = { snap: cloneSheet(currentSheet()), moved: false, pid: e.pointerId };
      dragActive = true;
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
      drag = null; pendingLogical = null; dragActive = false;
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
      drag = null; pendingLogical = null; dragActive = false;
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
    if (!canSave || !currentSheet()) { return; }
    var form = currentSheet().form;
    var cur = sanitizeCellFont(form.cell_font);
    var next = clamp(cur + delta, CELL_FONT_MIN, CELL_FONT_MAX);
    if (next === cur) { return; }
    recordUndo();
    form.cell_font = next;
    markDirty();
    applyFormLayout(currentSheet());
  }

  /** 현재 시트의 표 칸 폭·행 높이·상단선·글자 크기를 기본값으로 되돌린다(원상 복구). */
  function resetTableLayout() {
    if (!canSave || !currentSheet()) { return; }
    recordUndo();
    var form = currentSheet().form;
    form.layout = {
      cols: LAYOUT_DEFAULT.cols.slice(), addr: LAYOUT_DEFAULT.addr,
      rows: LAYOUT_DEFAULT.rows.slice(), top: LAYOUT_DEFAULT.top
    };
    form.cell_font = CELL_FONT_DEFAULT;
    markDirty();
    applyFormLayout(currentSheet());   // positionDividers 포함(내부 마지막 호출)
    toast('표 칸 크기를 기본값으로 되돌렸습니다.');
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
    konvaStage.on('pointerdown', onStagePointerDown);   // 펜슬/마우스 프리핸드 + 입력종류 추적(팜 리젝션)
    konvaStage.on('dblclick', onStageDblClick);
    wireTransformerGroup();
  }

  /** 다중 선택(그룹) 이동/변형 배선 — 단일 선택은 노드별 핸들러(wireNode) 소관.
     shouldOverdrawWholeArea(true) 로 그룹 bbox 영역 드래그=전체 함께 이동, 코너 앵커=그룹 리사이즈/회전.
     각 핸들러는 isMultiSelect() 게이트로 단일 선택 경로(노드 핸들러)와 이중 처리를 회피한다. */
  function wireTransformerGroup() {
    transformer.on('dragstart', function () {
      if (!isMultiSelect()) { return; }
      if (lastPointerType === 'touch') { transformer.stopDrag(); return; }   // 손가락 그룹 드래그 금지(팜 리젝션)
      dragActive = true; recordUndo();
    });
    transformer.on('dragmove', function () { if (!isMultiSelect()) { return; } positionAlignToolbar(); });
    transformer.on('dragend', function () {
      if (!isMultiSelect()) { return; }
      dragActive = false;
      selectedNodes().forEach(commitNode);   // commitNode 내부 markDirty
      transformer.forceUpdate();             // arrow/line commit 이 노드 내부(points/position) 재설정 → 박스 재계산
      positionAlignToolbar();
    });
    transformer.on('transformstart', function () { if (!isMultiSelect()) { return; } dragActive = true; recordUndo(); });
    transformer.on('transform', function () { if (!isMultiSelect()) { return; } positionAlignToolbar(); });
    transformer.on('transformend', function () {
      if (!isMultiSelect()) { return; }
      dragActive = false;
      selectedNodes().forEach(commitNode);   // commitNode 가 residual scale 를 치수로 baking
      rebuildAnno();   // state 기준 재구성(런텍스트 스냅 정리) + 다중 선택 복원
    });
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
      case 'pen': return buildPen(o);
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

  /** 프리핸드 펜 획 — 가변 points Konva.Line(tension 곡선). arrow/line 과 동일한 이동/변형 경로.
      optional opacity(형광펜=0.35)면 반투명 + multiply 합성으로 겹침을 자연스럽게 한다. */
  function buildPen(o) {
    var pts = normalizePenPoints(o.points);
    var sw = penWidthOrDefault(o.strokeWidth);
    var node = new Konva.Line({
      points: pts, stroke: colorOrDefault(o.stroke), strokeWidth: sw,
      tension: PEN_TENSION, lineCap: 'round', lineJoin: 'round', rotation: num(o.rotation),
      hitStrokeWidth: Math.max(12, sw), name: 'anno', draggable: canSave
    });
    var op = penOpacityOrNull(o.opacity);
    if (op != null) { node.opacity(op); node.globalCompositeOperation('multiply'); }
    return tagNode(node, o);
  }

  /** 선택/드래그/변형 이벤트 공통 배선. */
  function wireNode(node) {
    if (!canSave) { return; }
    node.on('mousedown', function (e) {
      if (annoMode !== 'select') { return; }   // 그리기 모드면 스테이지 핸들러가 처리
      e.cancelBubble = true;
      var id = node.getAttr('objId');
      var devt = e.evt || {};
      // Shift/Ctrl/Cmd+클릭 = 선택 토글(추가/제거), 일반 클릭 = 단일 선택.
      if (devt.shiftKey || devt.ctrlKey || devt.metaKey) { toggleInSelection(id); }
      else { selectSingle(id); }
    });
    // 아래 드래그/변형 핸들러는 단일 선택 전용 — 다중(그룹)은 transformer 레벨 핸들러가 처리.
    node.on('dragstart', function () {
      if (annoMode !== 'select') { node.stopDrag(); return; }
      if (lastPointerType === 'touch') { node.stopDrag(); return; }   // 손가락 드래그 금지(팜 리젝션 — 손가락=이동/핀치 전용)
      if (isMultiSelect()) { return; }
      dragActive = true;
      recordUndo();
    });
    node.on('dragmove', function () { if (isMultiSelect()) { return; } positionMiniToolbar(); });
    node.on('dragend', function () { if (isMultiSelect()) { return; } dragActive = false; commitNode(node); });
    node.on('transformstart', function () { if (isMultiSelect()) { return; } dragActive = true; recordUndo(); });
    node.on('transform', function () { if (isMultiSelect()) { return; } applyLiveTransform(node); positionMiniToolbar(); });
    node.on('transformend', function () { if (isMultiSelect()) { return; } dragActive = false; commitNode(node); });
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
    // 그룹 변형은 노드에 residual scale 를 남긴다(단일 경로는 transform 중 이미 folding됨=no-op).
    // 치수 읽기 전에 scale 을 실제 width/height/radius 로 baking 한다.
    applyLiveTransform(node);
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
    } else if (t === 'pen') {
      // 가변 points 전체를 절대 변환으로 baking(드래그/리사이즈/회전 확정) → position/scale/rotation 리셋.
      var trp = node.getAbsoluteTransform();
      var pp = node.points();
      var baked = [];
      for (var i = 0; i + 1 < pp.length; i += 2) {
        var qq = trp.point({ x: pp[i], y: pp[i + 1] });
        baked.push(qq.x, qq.y);
      }
      node.points(baked.slice());
      node.position({ x: 0, y: 0 }); node.rotation(0); node.scale({ x: 1, y: 1 });
      o.points = baked.map(function (v) { return Math.round(v); });
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
    var cs = currentSheet();
    if (!cs) { konvaLayer.batchDraw(); return; }   // 빈 상태: 주석 없음
    (cs.objects || []).forEach(function (o) {
      var node = buildNode(o);
      if (node) { konvaLayer.add(node); nodeById[o.id] = node; }
    });
    konvaLayer.find('.anno').forEach(function (n) { n.draggable(canSave && annoMode === 'select'); });
    transformer.moveToTop();
    konvaLayer.batchDraw();
    // 다중 선택 복원: 아직 존재하는 노드만 유지, 하나라도 남으면 applySelection, 전부 사라졌으면 해제.
    var restored = selectedIds.filter(function (id) { return !!nodeById[id]; });
    if (restored.length) { selectedIds = restored; applySelection(); }
    else if (selectedIds.length) { deselect(); }
  }

  /* ---- 선택 / 미니툴바 ----------------------------------------------------
     selectedIds(배열)가 SSOT. selected(단일 id)는 primary=마지막 선택으로 파생(단일 경로 호환).
     applySelection() 이 transformer 노드/앵커/그룹드래그 + 미니툴바/정렬툴바 노출을 일괄 동기. */
  function isMultiSelect() { return selectedIds.length > 1; }

  function selectedNodes() {
    var out = [];
    for (var i = 0; i < selectedIds.length; i++) {
      var n = nodeById[selectedIds[i]];
      if (n) { out.push(n); }
    }
    return out;
  }

  function selectSingle(id) {
    if (!nodeById[id]) { deselect(); return; }
    selectedIds = [id];
    applySelection();
  }

  function toggleInSelection(id) {
    if (!nodeById[id]) { return; }
    var i = selectedIds.indexOf(id);
    if (i === -1) { selectedIds = selectedIds.concat([id]); }
    else { selectedIds = selectedIds.slice(0, i).concat(selectedIds.slice(i + 1)); }
    applySelection();
  }

  /* 단일 선택 공개 진입점(기존 호출부 호환): 항상 단일 선택으로 설정. */
  function selectById(id) { selectSingle(id); }
  function selectNode(node) { if (node) { selectSingle(node.getAttr('objId')); } else { deselect(); } }

  /** selectedIds → transformer/툴바 동기(단일=미니툴바, 다중=정렬툴바+그룹드래그). */
  function applySelection() {
    var nodes = selectedNodes();
    if (nodes.length !== selectedIds.length) {
      // 사라진 노드 정리(rebuild 등)
      selectedIds = nodes.map(function (n) { return n.getAttr('objId'); });
    }
    selected = selectedIds.length ? selectedIds[selectedIds.length - 1] : null;
    if (!transformer) { return; }
    if (!nodes.length) {
      transformer.shouldOverdrawWholeArea(false);
      transformer.nodes([]);
      hideMiniToolbar();
      hideAlignToolbar();
      hideLogoPopup();
      if (konvaLayer) { konvaLayer.batchDraw(); }
      return;
    }
    if (nodes.length === 1) {
      var node = nodes[0];
      var t = node.getAttr('annoType');
      var o = findObj(node.getAttr('objId'));
      var isRich = (t === 'text' && o && o.runs && o.runs.length);
      transformer.shouldOverdrawWholeArea(false);
      transformer.keepRatio(t === 'image' ? imageRatioLock : false);
      // 런 텍스트는 이동·회전만(리사이즈 앵커 비활성) — 단색 텍스트/도형은 코너 앵커 유지.
      transformer.enabledAnchors(isRich ? [] : ['top-left', 'top-right', 'bottom-left', 'bottom-right']);
      transformer.nodes([node]);
      transformer.moveToTop();
      hideAlignToolbar();
      showMiniToolbar(node);
    } else {
      // 다중: 그룹 bbox 영역 드래그=함께 이동, 코너 앵커=그룹 리사이즈/회전.
      // (런 텍스트 포함 시 리사이즈는 richWidth 로 되돌아감 — 이동/정렬은 정상. 문서화된 한계.)
      transformer.shouldOverdrawWholeArea(true);
      transformer.keepRatio(false);
      transformer.enabledAnchors(['top-left', 'top-right', 'bottom-left', 'bottom-right']);
      transformer.nodes(nodes);
      transformer.moveToTop();
      hideMiniToolbar();
      showAlignToolbar();
    }
    konvaLayer.batchDraw();
  }

  function deselect() {
    selectedIds = [];
    selected = null;
    if (transformer) { transformer.shouldOverdrawWholeArea(false); transformer.nodes([]); }
    hideMiniToolbar();
    hideAlignToolbar();
    hideLogoPopup();
    if (konvaLayer) { konvaLayer.batchDraw(); }
  }

  /* ---- 정렬 툴바(다중 선택 ≥2 시 노출) ------------------------------------
     선택 객체들의 axis-aligned bbox 기준으로 각 객체 x/y(또는 arrow/line points)를 이동.
     회전 객체는 노드 getClientRect bbox 근사로 정렬(브리프 허용). state 갱신 후 rebuild 로 동기. */
  function showAlignToolbar() { if (!canSave || !els.alignToolbar) { return; } els.alignToolbar.hidden = false; positionAlignToolbar(); }
  function hideAlignToolbar() { if (els.alignToolbar) { els.alignToolbar.hidden = true; } }

  function positionAlignToolbar() {
    if (!els.alignToolbar || els.alignToolbar.hidden || selectedIds.length < 2) { return; }
    var nodes = selectedNodes();
    if (!nodes.length) { return; }
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nodes.forEach(function (n) {
      var b = n.getClientRect();
      if (b.x < minX) { minX = b.x; }
      if (b.y < minY) { minY = b.y; }
      if (b.x + b.width > maxX) { maxX = b.x + b.width; }
      if (b.y + b.height > maxY) { maxY = b.y + b.height; }
    });
    var annoRect = els.anno.getBoundingClientRect();
    var screenTop = annoRect.top + minY * zoom;
    var screenBottom = annoRect.top + maxY * zoom;
    var screenLeft = annoRect.left + minX * zoom;
    var ROTATER_CLEARANCE = 34;   // 회전 핸들 위로 띄워 앵커를 가리지 않게
    var top = screenTop - els.alignToolbar.offsetHeight - 8 - ROTATER_CLEARANCE;
    if (top < 8) { top = screenBottom + 8; }
    var left = clamp(screenLeft, 8, window.innerWidth - els.alignToolbar.offsetWidth - 8);
    els.alignToolbar.style.left = left + 'px';
    els.alignToolbar.style.top = top + 'px';
  }

  /** 객체 좌표를 dx/dy 만큼 평행이동(state SSOT). arrow/line 은 points, 그 외는 x/y. */
  function shiftObjectState(o, dx, dy) {
    if (dx === 0 && dy === 0) { return; }
    if (o.type === 'arrow' || o.type === 'line' || o.type === 'pen') {
      o.points = shiftPoints(o.points, dx, dy);
    } else {
      o.x = num(o.x) + dx; o.y = num(o.y) + dy;
    }
  }

  function alignSelected(kind) {
    if (kind === 'hdistribute') { distributeSelected('h'); return; }
    if (kind === 'vdistribute') { distributeSelected('v'); return; }
    if (!canSave || selectedIds.length < 2) { return; }
    var items = [];
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    selectedIds.forEach(function (id) {
      var n = nodeById[id], o = findObj(id);
      if (!n || !o) { return; }
      var r = n.getClientRect();   // 논리 좌표 bbox(회전 포함 근사)
      items.push({ o: o, r: r });
      if (r.x < minX) { minX = r.x; }
      if (r.y < minY) { minY = r.y; }
      if (r.x + r.width > maxX) { maxX = r.x + r.width; }
      if (r.y + r.height > maxY) { maxY = r.y + r.height; }
    });
    if (items.length < 2) { return; }
    var cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
    recordUndo();
    items.forEach(function (it) {
      var r = it.r, dx = 0, dy = 0;
      switch (kind) {
        case 'left': dx = minX - r.x; break;
        case 'hcenter': dx = (cx - r.width / 2) - r.x; break;
        case 'right': dx = (maxX - r.width) - r.x; break;
        case 'top': dy = minY - r.y; break;
        case 'vcenter': dy = (cy - r.height / 2) - r.y; break;
        case 'bottom': dy = (maxY - r.height) - r.y; break;
        default: return;
      }
      shiftObjectState(it.o, Math.round(dx), Math.round(dy));
    });
    markDirty();
    rebuildAnno();   // state 기준 재구성 + 다중 선택 복원(applySelection)
  }

  /** 선택 객체의 인접 간격을 균등 분배(양끝 고정). axis='h'(가로)|'v'(세로). 3개 이상 필요. */
  function distributeSelected(axis) {
    if (!canSave) { return; }
    if (selectedIds.length < 3) {
      if (selectedIds.length === 2) { toast('간격을 맞추려면 3개 이상 선택하세요'); }
      return;
    }
    var horiz = (axis === 'h');
    var items = [];
    selectedIds.forEach(function (id) {
      var n = nodeById[id], o = findObj(id);
      if (!n || !o) { return; }
      items.push({ o: o, r: n.getClientRect() });   // 정렬과 동일 기준(회전 근사 bbox)
    });
    if (items.length < 3) { return; }
    // 위치(가로=x, 세로=y) 오름차순 정렬 → 양끝 고정
    items.sort(function (a, b) { return horiz ? (a.r.x - b.r.x) : (a.r.y - b.r.y); });
    var first = items[0].r, last = items[items.length - 1].r;
    var sumSize = 0;
    items.forEach(function (it) { sumSize += horiz ? it.r.width : it.r.height; });
    var span = horiz ? ((last.x + last.width) - first.x) : ((last.y + last.height) - first.y);
    var gap = (span - sumSize) / (items.length - 1);   // 인접 가장자리-가장자리 균등 간격(음수=겹침 허용)
    var cursor = horiz ? first.x : first.y;
    recordUndo();
    items.forEach(function (it) {
      var r = it.r, size = horiz ? r.width : r.height;
      if (horiz) { shiftObjectState(it.o, Math.round(cursor - r.x), 0); }
      else { shiftObjectState(it.o, 0, Math.round(cursor - r.y)); }
      cursor += size + gap;
    });
    markDirty();
    rebuildAnno();   // state 기준 재구성 + 다중 선택 복원(applySelection)
  }

  function showMiniToolbar(node) {
    if (!canSave || !node) { hideMiniToolbar(); return; }
    var t = node.getAttr('annoType');
    var o = findObj(node.getAttr('objId'));
    if (!o) { hideMiniToolbar(); return; }
    els.mtText.hidden = (t !== 'text');
    els.mtImage.hidden = (t !== 'image');
    els.mtShape.hidden = !isStrokeType(t);   // pen 도 line 처럼 색/굵기/삭제 툴 노출
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
    // 미니바를 회전 핸들(박스 상단 위 ~24px + 핸들 반경) 위로 띄워 회전 앵커를 가리지 않게 한다.
    var ROTATER_CLEARANCE = 34;
    var top = screenTop - els.mt.offsetHeight - 8 - ROTATER_CLEARANCE;
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
    if (!o || !isStrokeType(o.type)) { return; }
    recordUndo();
    Object.keys(patch).forEach(function (k) { o[k] = patch[k]; });
    // 도형 기본값은 도형에서만 계승(pen 편집이 다음 도형 색/굵기로 새지 않게).
    if (isShapeType(o.type)) {
      if ('stroke' in patch) { lastStrokeColor = patch.stroke; }
      if ('strokeWidth' in patch) { lastStrokeWidth = patch.strokeWidth; }
    }
    markDirty();
    rebuildAnno();
    selectById(o.id);
  }

  /* ---- 삭제 / 이동 -------------------------------------------------------- */
  function spliceObject(id) {
    var objs = currentSheet().objects, i = -1;
    objs.some(function (o, idx) { if (o.id === id) { i = idx; return true; } return false; });
    if (i >= 0) { objs.splice(i, 1); }
  }

  function removeObject(id) { spliceObject(id); rebuildAnno(); }

  /** 선택 전체 삭제(단일·다중 공용) — recordUndo 1회로 묶고 rebuild 1회. */
  function deleteSelected() {
    if (!canSave || !selectedIds.length) { return; }
    recordUndo();
    var ids = selectedIds.slice();
    deselect();
    ids.forEach(spliceObject);
    rebuildAnno();
    markDirty();
  }

  function moveObjectBy(o, dx, dy) {
    var isPoints = (o.type === 'arrow' || o.type === 'line' || o.type === 'pen');
    if (isPoints) {
      o.points = shiftPoints(o.points, dx, dy);
    } else {
      o.x += dx; o.y += dy;
    }
    var node = nodeById[o.id];
    if (!node) { return; }
    if (isPoints) { node.points(o.points.slice()); }
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
    else if (annoMode === 'pen') { activeId = 'dws-btn-pen'; }
    else if (annoMode === 'eraser') { activeId = 'dws-btn-eraser'; }
    else if (isShapeType(annoMode)) { activeId = 'dws-btn-shape'; }
    ['dws-btn-select', 'dws-btn-add-text', 'dws-btn-pen', 'dws-btn-eraser', 'dws-btn-shape'].forEach(function (id) {
      var b = document.getElementById(id);
      if (b) { b.classList.toggle('dws-seg-active', id === activeId); }
    });
  }

  function setAnnoMode(mode) {
    annoMode = mode;
    if (mode !== 'select') { deselect(); }
    if (els.anno) {
      els.anno.classList.toggle('dws-drawing', mode !== 'select');
      els.anno.classList.toggle('dws-erasing', mode === 'eraser');
    }
    if (konvaLayer) {
      konvaLayer.find('.anno').forEach(function (n) { n.draggable(canSave && mode === 'select'); });
    }
    if (els.penPalette) {
      els.penPalette.hidden = (mode !== 'pen');
      if (mode === 'pen') { syncPenPalette(); }
    }
    updateModeHint(mode);
    syncSegActive();
    updateDividerState();
  }

  /* ---- 펜 팔레트(색·굵기·형광펜 토글) — 펜 모드일 때만 노출 ---------------- */
  function setPenMode(mode) { penMode = (mode === 'hi') ? 'hi' : 'pen'; syncPenPalette(); updateModeHint(annoMode); }
  function setPenColor(c) { penColor = colorOrDefault(c); syncPenPalette(); }
  function setPenWidth(w) { penWidth = penWidthOrDefault(w); syncPenPalette(); }
  function setHiColor(c) { hiColor = colorOrDefault(c); syncPenPalette(); }
  function setHiWidth(w) { hiWidth = penWidthOrDefault(w); syncPenPalette(); }

  /** 팔레트 버튼 active 표시를 현재 penMode/penColor·penWidth/hiColor·hiWidth 로 동기.
      penMode 에 따라 일반 펜(.dws-pen-only) ↔ 형광펜(.dws-hi-only) 컨트롤을 CSS 로 전환한다. */
  function syncPenPalette() {
    if (!els.penPalette) { return; }
    var hi = (penMode === 'hi');
    els.penPalette.classList.toggle('dws-pen-hi', hi);
    Array.prototype.forEach.call(els.penPalette.querySelectorAll('[data-pen-mode]'), function (b) {
      b.classList.toggle('dws-active', b.getAttribute('data-pen-mode') === penMode);
    });
    Array.prototype.forEach.call(els.penPalette.querySelectorAll('[data-pen-color]'), function (b) {
      b.classList.toggle('dws-active', b.getAttribute('data-pen-color').toLowerCase() === String(penColor).toLowerCase());
    });
    Array.prototype.forEach.call(els.penPalette.querySelectorAll('[data-pen-width]'), function (b) {
      b.classList.toggle('dws-active', (parseInt(b.getAttribute('data-pen-width'), 10) || 0) === penWidth);
    });
    Array.prototype.forEach.call(els.penPalette.querySelectorAll('[data-hi-color]'), function (b) {
      b.classList.toggle('dws-active', b.getAttribute('data-hi-color').toLowerCase() === String(hiColor).toLowerCase());
    });
    Array.prototype.forEach.call(els.penPalette.querySelectorAll('[data-hi-width]'), function (b) {
      b.classList.toggle('dws-active', (parseInt(b.getAttribute('data-hi-width'), 10) || 0) === hiWidth);
    });
  }

  /** 모드 무장 시 캔버스 상단 중앙 힌트 pill 표시/문구 갱신(select면 숨김). */
  function updateModeHint(mode) {
    if (!els.modeHint) { return; }
    var msg = '';
    if (mode === 'text') { msg = '텍스트: 넣을 위치를 클릭 · Esc 취소'; }
    else if (mode === 'pen') {
      msg = (penMode === 'hi')
        ? '형광펜: 펜슬·마우스로 반투명 강조 · 손가락으로 이동/확대 · Esc 종료'
        : '펜: 펜슬·마우스로 필기 · 손가락으로 이동/확대 · Esc 종료';
    }
    else if (mode === 'eraser') { msg = '지우개: 펜슬·마우스로 획 위를 문질러 삭제 · 손가락으로 이동/확대 · Esc 종료'; }
    else if (isShapeType(mode)) { msg = '도형: 드래그해서 그리기 · Esc 취소'; }
    if (msg) {
      els.modeHint.textContent = msg;
      els.modeHint.classList.add('dws-mode-hint-show');
    } else {
      els.modeHint.classList.remove('dws-mode-hint-show');
    }
  }

  function onStageMouseDown(e) {
    if (!canSave || !currentSheet()) { return; }
    // 펜/지우개는 pointer 핸들러(onStagePointerDown) 전담 — mousedown 은 no-op(러버밴드·선택 이중발동 차단).
    if (annoMode === 'pen' || annoMode === 'eraser') { return; }
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
    if (e.target !== konvaStage) { return; }   // 다중 선택 bbox(transformer overdraw)는 여기 도달 X
    if (devt.ctrlKey || devt.metaKey) {
      if (devt.preventDefault) { devt.preventDefault(); }  // Ctrl+클릭 텍스트 생성도 동일 보호
      var cp = pointerLogical(devt);
      createTextAt(cp.x, cp.y);
      return;
    }
    // 빈 영역: 드래그=러버밴드 다중 선택 / 순수 클릭=선택 해제 + 폼 투과(이동 임계 4px로 판별).
    startMarqueeSelect(e);
  }

  /** 빈 캔버스 드래그=러버밴드 박스로 교차 객체 다중 선택. 순수 클릭(이동<4px)=기존 해제+폼 투과.
     Shift/Ctrl/Cmd 드래그는 기존 선택에 합집합으로 추가. */
  function startMarqueeSelect(e) {
    var devt = e.evt;
    var startLogical = pointerLogical(devt);
    var startX = num(devt.clientX), startY = num(devt.clientY);
    var additive = !!(devt.shiftKey || devt.ctrlKey || devt.metaKey);
    var moved = false;
    var rect = null;
    function ensureRect() {
      if (rect) { return; }
      rect = new Konva.Rect({
        x: startLogical.x, y: startLogical.y, width: 0, height: 0,
        fill: 'rgba(28,98,214,0.08)', stroke: '#1c62d6', strokeWidth: 1,
        dash: [4, 3], name: 'anno-marquee', listening: false
      });
      konvaLayer.add(rect);
      transformer.moveToTop();
    }
    function move(nativeEvt) {
      if (!moved) {
        if (Math.abs(num(nativeEvt.clientX) - startX) < 4 && Math.abs(num(nativeEvt.clientY) - startY) < 4) { return; }
        moved = true;
        if (devt.preventDefault) { devt.preventDefault(); }   // 네이티브 텍스트 선택 억제
        ensureRect();
      }
      if (nativeEvt.preventDefault) { nativeEvt.preventDefault(); }
      var p = pointerLogical(nativeEvt);
      var x = Math.min(startLogical.x, p.x), y = Math.min(startLogical.y, p.y);
      var w = Math.abs(p.x - startLogical.x), h = Math.abs(p.y - startLogical.y);
      rect.setAttrs({ x: x, y: y, width: w, height: h });
      konvaLayer.batchDraw();
    }
    function up(nativeEvt) {
      window.removeEventListener('mousemove', move, true);
      window.removeEventListener('mouseup', up, true);
      if (!moved) {
        // 순수 클릭: 기존 동작(선택 해제 + 폼 투과)
        deselect();
        passthroughToForm(nativeEvt);
        return;
      }
      var box = { x: rect.x(), y: rect.y(), w: rect.width(), h: rect.height() };
      rect.destroy();
      rect = null;
      konvaLayer.batchDraw();
      var hits = marqueeHits(box);
      if (additive) {
        var merged = selectedIds.slice();
        hits.forEach(function (id) { if (merged.indexOf(id) === -1) { merged.push(id); } });
        selectedIds = merged;
      } else {
        selectedIds = hits;
      }
      applySelection();
    }
    window.addEventListener('mousemove', move, true);
    window.addEventListener('mouseup', up, true);
  }

  /** 러버밴드 박스(논리 좌표)와 AABB 교차하는 객체 id 목록. */
  function marqueeHits(box) {
    var out = [];
    var objs = (currentSheet() && currentSheet().objects) || [];
    objs.forEach(function (o) {
      var n = nodeById[o.id];
      if (!n) { return; }
      var r = n.getClientRect();
      if (r.x < box.x + box.w && r.x + r.width > box.x && r.y < box.y + box.h && r.y + r.height > box.y) {
        out.push(o.id);
      }
    });
    return out;
  }

  function onStageDblClick(e) {
    if (!canSave || annoMode !== 'select' || !currentSheet()) { return; }
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
    if (!currentSheet()) { konvaLayer.batchDraw(); return; }
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

  /* ---- 프리핸드 펜(포인터 이벤트 + 팜 리젝션) -----------------------------
     펜 모드 + pointerType 'pen'|'mouse' → 스트로크. 'touch'(손가락) → 미그리기(팜 리젝션).
     입력 종류는 모든 모드에서 추적(lastPointerType) — 손가락 드래그(객체 이동) 차단에 사용. */
  function onStagePointerDown(e) {
    var devt = e.evt || {};
    lastPointerType = devt.pointerType || 'mouse';
    var pt = devt.pointerType;
    if (annoMode === 'eraser') {                    // 지우개: 펜슬·마우스로 획 위를 지나며 통째 삭제
      if (!canSave || !currentSheet()) { return; }
      if (pt && pt !== 'pen' && pt !== 'mouse') { return; }   // 손가락(touch) → 안 지움(네비/팜 리젝션)
      if (isDrawingPen) { return; }                 // 이미 포인터 스트로크 진행 중(멀티포인터 방어)
      startEraseStroke(devt);
      return;
    }
    if (annoMode !== 'pen') { return; }            // 펜 모드에서만 pointer 그리기 활성(select/도형은 mouse 경로)
    if (!canSave || !currentSheet()) { return; }
    if (pt && pt !== 'pen' && pt !== 'mouse') { return; }   // 손가락(touch) → 안 그림
    if (isDrawingPen) { return; }                  // 이미 스트로크 진행 중(멀티포인터 방어)
    startPenStroke(devt);
  }

  /** 시트에 pen 객체 1건 push(가변 points). 200개 캡 도달 시 skip(저장 400 예방).
      penMode='hi'(형광펜)면 형광 색·굵기 + 반투명(opacity) 필드를 부여한다. */
  function commitPenObject(points) {
    var cs = currentSheet();
    if (!cs) { return null; }
    var pts = normalizePenPoints(points);
    if (pts.length < 4) { return null; }
    if ((cs.objects || []).length >= 200) { toast('한 시트의 객체가 200개를 넘어 더 그릴 수 없습니다.'); return null; }
    var hi = (penMode === 'hi');
    var o = {
      id: rid('o-'), type: 'pen', points: pts,
      stroke: hi ? hiColor : penColor, strokeWidth: hi ? hiWidth : penWidth, rotation: 0
    };
    if (hi) { o.opacity = HI_OPACITY; }
    cs.objects.push(o);
    return o;
  }

  /** 프리핸드 스트로크 시작 — 라이브 프리뷰 draft + window pointer 리스너로 점 누적/커밋. */
  function startPenStroke(devt) {
    if (devt.preventDefault) { devt.preventDefault(); }   // 브라우저 기본(스크롤·선택) 억제
    var p = pointerLogical(devt);
    var pts = [p.x, p.y];
    var lastPt = p;
    var pointerId = devt.pointerId;
    var recorded = false;   // undo 는 실제 점 추가 시 1회만(단순 탭은 스택 오염 방지)
    var committed = false;
    var hi = (penMode === 'hi');   // 형광펜: 반투명 굵은 획(라이브 프리뷰도 동일하게 반영)
    var draft = new Konva.Line({
      points: pts.slice(), stroke: hi ? hiColor : penColor, strokeWidth: hi ? hiWidth : penWidth,
      tension: PEN_TENSION, lineCap: 'round', lineJoin: 'round', name: 'anno-draft', listening: false
    });
    if (hi) { draft.opacity(HI_OPACITY); draft.globalCompositeOperation('multiply'); }
    konvaLayer.add(draft);
    transformer.moveToTop();
    isDrawingPen = true;

    function samePointer(nativeEvt) {
      return pointerId == null || nativeEvt.pointerId == null || nativeEvt.pointerId === pointerId;
    }
    function move(nativeEvt) {
      if (!samePointer(nativeEvt)) { return; }   // 다른 포인터(팜 등) 무시
      if (nativeEvt.preventDefault) { nativeEvt.preventDefault(); }
      var q = pointerLogical(nativeEvt);
      var dx = q.x - lastPt.x, dy = q.y - lastPt.y;
      if (dx * dx + dy * dy < PEN_MIN_STEP_SQ) { return; }   // 점 단순화(2px 미만 skip)
      if (!recorded) { recordUndo(); recorded = true; }
      pts.push(q.x, q.y);
      lastPt = q;
      draft.points(pts.slice());
      konvaLayer.batchDraw();
      if (pts.length >= PEN_MAX_COORDS) {
        // 상한 도달 → 현재까지 커밋하고 같은 지점부터 새 스트로크로 이어간다(64KB·200객체 보호).
        var mid = commitPenObject(pts);
        if (mid) {
          committed = true;
          var mn = buildNode(mid);
          if (mn) { mn.draggable(false); konvaLayer.add(mn); nodeById[mid.id] = mn; }
          transformer.moveToTop();
        }
        pts = [q.x, q.y];
        draft.points(pts.slice());
      }
    }
    function up(nativeEvt) {
      if (nativeEvt.type !== 'pointercancel' && !samePointer(nativeEvt)) { return; }
      window.removeEventListener('pointermove', move, true);
      window.removeEventListener('pointerup', up, true);
      window.removeEventListener('pointercancel', up, true);
      isDrawingPen = false;
      draft.destroy();
      if (pts.length >= 4 && commitPenObject(pts)) { committed = true; }
      if (committed) { markDirty(); rebuildAnno(); }   // 펜 모드 유지(선택 안 함=연속 필기), draggable=false 재적용
      else { konvaLayer.batchDraw(); }
    }
    window.addEventListener('pointermove', move, true);
    window.addEventListener('pointerup', up, true);
    window.addEventListener('pointercancel', up, true);
  }

  /* ---- 지우개(획 삭제, GoodNotes식 스트로크 지우개) -----------------------
     지우개 모드 + pointerType 'pen'|'mouse' 로 pointerdown~move 하며 포인터 아래에 걸리는
     주석 객체(.anno 노드)를 통째로 삭제한다. 손가락(touch)은 지우지 않고 팬/핀치 네비 유지.
     한 제스처(down~up) 당 recordUndo 1회로 묶고, 실제 삭제가 있으면 markDirty+rebuildAnno. */

  /** getIntersection 결과(리치 텍스트는 Group 내부 조각) → objId 를 가진 .anno 조상 노드. */
  function annoNodeFromHit(hit) {
    var n = hit;
    while (n && n !== konvaLayer) {
      if (typeof n.name === 'function' && n.name() === 'anno' && n.getAttr('objId')) { return n; }
      n = n.getParent();
    }
    return null;
  }

  /** 지우개 스트로크 — 포인터 아래 주석 노드를 즉시 제거(진행형)하고, 제스처 종료 시 state 정리. */
  function startEraseStroke(devt) {
    if (devt.preventDefault) { devt.preventDefault(); }
    var pointerId = devt.pointerId;
    var recorded = false;   // 첫 삭제 시 1회만 undo 스냅샷(빈 제스처는 스택 오염 방지)
    var erased = false;
    isDrawingPen = true;    // 팜 리젝션 재사용: 제스처 중 손가락 네비/핀치 억제

    function eraseAt(nativeEvt) {
      var hit = konvaStage.getIntersection(pointerLogical(nativeEvt));
      if (!hit) { return; }
      var node = annoNodeFromHit(hit);
      if (!node) { return; }
      var id = node.getAttr('objId');
      if (!id) { return; }
      if (!recorded) { recordUndo(); recorded = true; }   // 첫 삭제 직전 스냅샷(제스처당 1회 undo)
      spliceObject(id);
      node.destroy();
      delete nodeById[id];
      erased = true;
      konvaLayer.batchDraw();   // 아래 겹친 획이 다음 판정에서 드러나도록 즉시 반영
    }
    function samePointer(nativeEvt) {
      return pointerId == null || nativeEvt.pointerId == null || nativeEvt.pointerId === pointerId;
    }
    function move(nativeEvt) {
      if (!samePointer(nativeEvt)) { return; }
      if (nativeEvt.preventDefault) { nativeEvt.preventDefault(); }
      eraseAt(nativeEvt);
    }
    function up(nativeEvt) {
      if (nativeEvt.type !== 'pointercancel' && !samePointer(nativeEvt)) { return; }
      window.removeEventListener('pointermove', move, true);
      window.removeEventListener('pointerup', up, true);
      window.removeEventListener('pointercancel', up, true);
      isDrawingPen = false;
      if (erased) { markDirty(); rebuildAnno(); }   // 지우개 모드 유지(연속 삭제), 선택 복원 없음
      else { konvaLayer.batchDraw(); }
    }
    eraseAt(devt);   // pointerdown 지점 즉시 판정(탭으로도 삭제)
    window.addEventListener('pointermove', move, true);
    window.addEventListener('pointerup', up, true);
    window.addEventListener('pointercancel', up, true);
  }

  /* ---- 텍스트 생성 / 인라인 편집 ------------------------------------------ */
  function createTextAt(x, y) {
    if (!canSave || !currentSheet()) { return; }
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

  /** 프리셋 텍스트를 새 텍스트 객체로 캔버스에 삽입하고 편집 모드 진입(플레인 문자열). */
  function insertPresetText(text, bold) {
    if (!canSave || !currentSheet()) { toast('제품을 선택해 도면을 먼저 시작하세요.'); return; }
    recordUndo();
    var n = currentSheet().objects.length;
    var o = {
      id: rid('o-'), type: 'text', x: 340 + (n % 3) * 30, y: 95 + (n % 6) * 46, w: 220,
      text: String(text || ''), size: 20, color: '#000000', bold: !!bold, align: 'left', rotation: 0
    };
    currentSheet().objects.push(o);
    markDirty();
    rebuildAnno();
    selectById(o.id);
    startEditText(nodeById[o.id], true);
  }

  function addPreset(kind) {
    var label = PRESETS[kind];
    if (!label) { return; }
    insertPresetText(label + '\n', true);
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
    if (els.mtPresetMenu) { els.mtPresetMenu.hidden = true; }
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

  /** 업로드된 에셋 key 를 이미지 객체로 배치한다(원본 natural 비율·undo·dirty).
      pos(논리 좌표 {x,y}) 가 주어지면 이미지 중심이 그 지점에 오도록, 없으면 캔버스 중앙에 배치.
      이미지 업로드(파일/붙여넣기/드롭)와 실측 사진 삽입(import-attachment)의 공용 삽입 파이프라인. */
  function placeImageFromKey(key, pos) {
    if (!canSave || !key || !currentSheet()) { return; }
    var img = new Image();
    img.onload = function () {
      if (!currentSheet()) { return; }   // 비동기 로드 사이 빈 상태 방어
      var nw = img.naturalWidth || 900, nh = img.naturalHeight || 600;
      var w = Math.min(900, nw);
      var h = Math.round(w * nh / nw) || Math.round(w * 0.66);
      recordUndo();
      var x, y;
      if (pos && isFinite(pos.x) && isFinite(pos.y)) {
        // 드롭 지점에 이미지 중심을 두고 스테이지 범위로 클램프(y 하한 70 = 헤더 영역 보호).
        x = clamp(Math.round(pos.x - w / 2), 0, Math.max(0, STAGE_W - w));
        y = clamp(Math.round(pos.y - h / 2), 70, Math.max(70, STAGE_H - h));
      } else {
        x = Math.round((STAGE_W - w) / 2);
        y = Math.round(70 + (730 - h) / 2);
        if (y < 70) { y = 70; }
      }
      var o = {
        id: rid('o-'), type: 'image',
        x: x, y: y,
        w: w, h: h, key: key, natural_w: nw, natural_h: nh, rotation: 0
      };
      currentSheet().objects.push(o);
      markDirty();
      rebuildAnno();
      selectById(o.id);
    };
    img.onerror = function () { toast('이미지를 불러오지 못했습니다.'); };
    img.src = viewUrl(key);
  }

  function addImageFromFile(file, pos) {
    if (!canSave || !file) { return; }
    if (!currentSheet()) { toast('제품을 선택해 도면을 먼저 시작하세요.'); return; }
    uploadAsset(file).then(function (r) {
      if (r.status !== 200 || !r.data || !r.data.success || !r.data.data) {
        toast((r.data && r.data.message) || '이미지 업로드 실패');
        return;
      }
      placeImageFromKey(r.data.data.key, pos);
    }).catch(function (err) { console.warn('[dws] asset upload', err); toast('이미지 업로드 오류'); });
  }

  /** 드롭 화면좌표(clientX/Y)를 스테이지 논리좌표로 역산한다.
      anno 컨테이너 rect + `zoom` 스케일 기준(positionMiniToolbar 의 정매핑
      screen = annoRect + logical*zoom 의 역). 매핑 불가(사이즈 0 등) 시 null → 중앙 폴백. */
  function dropLogicalPos(e) {
    if (!els.anno) { return null; }
    var r = els.anno.getBoundingClientRect();
    if (!r.width || !r.height || !zoom) { return null; }
    var x = (e.clientX - r.left) / zoom;
    var y = (e.clientY - r.top) / zoom;
    if (!isFinite(x) || !isFinite(y)) { return null; }
    return { x: clamp(x, 0, STAGE_W), y: clamp(y, 0, STAGE_H) };
  }

  /** 캔버스 뷰포트에 이미지 파일 드래그앤드롭 배선(HTML5 DnD, 툴바 [이미지]·Ctrl+V 와 동일 파이프라인).
      드롭 지점 논리좌표로 배치하며, 여러 파일은 소폭 cascade 로 겹침을 피한다.
      dragover 는 반드시 preventDefault 해야 drop 이 발화한다. */
  function bindCanvasDnd() {
    var zone = els.canvas;
    if (!zone) { return; }
    var depth = 0;   // dragenter/leave 균형 카운터(자식 경계 진입에도 하이라이트 유지)
    function isFileDrag(e) {
      var t = e.dataTransfer && e.dataTransfer.types;
      if (!t) { return false; }
      for (var i = 0; i < t.length; i++) { if (t[i] === 'Files') { return true; } }
      return false;
    }
    function show(on) { zone.classList.toggle('dws-dropzone-active', !!on); }
    zone.addEventListener('dragenter', function (e) {
      if (!isFileDrag(e)) { return; }
      e.preventDefault();
      depth++;
      show(true);
    });
    zone.addEventListener('dragover', function (e) {
      if (!isFileDrag(e)) { return; }
      e.preventDefault();   // 없으면 drop 이 발화하지 않음
      if (e.dataTransfer) { e.dataTransfer.dropEffect = 'copy'; }
      show(true);
    });
    zone.addEventListener('dragleave', function () {
      if (depth === 0) { return; }   // depth>0 = 파일 드래그 진행 중(dragenter 에서만 증가)
      depth--;
      if (depth === 0) { show(false); }
    });
    zone.addEventListener('drop', function (e) {
      if (!isFileDrag(e)) { return; }
      e.preventDefault();   // 브라우저의 파일 네비게이션 차단
      depth = 0;
      show(false);
      var files = (e.dataTransfer && e.dataTransfer.files) ? e.dataTransfer.files : [];
      var base = dropLogicalPos(e);   // null 이면 중앙 폴백
      var placed = 0, skipped = 0;
      for (var i = 0; i < files.length; i++) {
        var f = files[i];
        if (!f || !f.type || f.type.indexOf('image/') !== 0) { skipped++; continue; }
        var pos = null;
        if (base) { var off = placed * 24; pos = { x: base.x + off, y: base.y + off }; }
        addImageFromFile(f, pos);
        placed++;
      }
      if (placed === 0 && skipped > 0) { toast('이미지 파일만 캔버스에 추가할 수 있습니다.'); }
    });
  }

  /* ========================================================================
   * [5] toolbar (제품 리스트 · 앱바 · 미니툴바 · 탭 · 줌 · 로고팝업 · 메뉴)
   * ====================================================================== */

  /** 주문 제품 리스트를 좌측 패널에 렌더한다(번호·이름·규격·금액). textContent 만(XSS 안전). */
  function renderProducts() {
    if (!els.productList) { return; }
    els.productList.textContent = '';
    if (!products.length) {
      var empty = document.createElement('div');
      empty.className = 'dws-product-empty';
      empty.textContent = '제품 없음';
      els.productList.appendChild(empty);
      return;
    }
    products.forEach(function (p) {
      var row = document.createElement('button');
      row.type = 'button';
      row.className = 'dws-product';
      row.setAttribute('data-product-index', String(p.index));
      var num = document.createElement('span');
      num.className = 'dws-product-num';
      num.textContent = String(p.index + 1);
      row.appendChild(num);
      var body = document.createElement('span');
      body.className = 'dws-product-body';
      var name = document.createElement('span');
      name.className = 'dws-product-name';
      name.textContent = p.name || ('제품 ' + (p.index + 1));
      body.appendChild(name);
      if (p.spec) {
        var spec = document.createElement('span');
        spec.className = 'dws-product-spec';
        spec.textContent = p.spec;
        body.appendChild(spec);
      }
      if (isFiniteNum(p.price)) {
        var price = document.createElement('span');
        price.className = 'dws-product-price';
        price.textContent = p.price.toLocaleString('ko-KR') + '원';
        body.appendChild(price);
      }
      row.appendChild(body);
      row.addEventListener('click', function () { onProductClick(p.index); });
      els.productList.appendChild(row);
    });
    syncProductActive();
  }

  /** 현재 시트의 product_index 에 해당하는 제품 행만 활성 하이라이트한다.
      활성 제품이 바뀌면 실측 사진 정렬(현재 제품 우선)도 함께 갱신한다. */
  function syncProductActive() {
    if (els.productList) {
      var cs = currentSheet();
      var activeIdx = (cs && isFiniteNum(cs.product_index)) ? cs.product_index : -1;
      Array.prototype.forEach.call(els.productList.querySelectorAll('.dws-product'), function (el) {
        var i = parseInt(el.getAttribute('data-product-index'), 10);
        el.classList.toggle('dws-product-active', i === activeIdx);
      });
    }
    renderPhotos();
  }

  /** 제품 클릭 → 그 제품 전용 도면 시트로 전환(없으면 defaults 로드 후 생성). */
  function onProductClick(idx) {
    if (!canSave) { toast('열람 전용 — 도면 담당자·도면팀 또는 관리자만 편집할 수 있습니다.'); return; }
    var cs = currentSheet();
    if (cs && cs.product_index === idx) { return; }   // 이미 그 제품 시트면 no-op
    for (var i = 0; i < state.sheets.length; i++) {
      if (state.sheets[i].product_index === idx) { switchSheet(i); return; }
    }
    if (state.sheets.length >= 10) { toast('시트는 최대 10장까지 만들 수 있습니다.'); return; }
    var prod = products[idx] || {};
    var name = String(prod.name || ('제품 ' + (idx + 1))).slice(0, 50);
    jsonFetch(API_BASE + '/drawing-wizard?item=' + idx, { headers: { 'Accept': 'application/json' } }).then(function (r) {
      var d = (r.status === 200 && r.data && r.data.success && r.data.data && r.data.data.defaults)
        ? r.data.data.defaults : defaults;
      var sheet = newSheet(name, d);
      sheet.product_index = idx;
      state.sheets.push(sheet);
      current = state.sheets.length - 1;
      undoStack.length = 0;
      redoStack.length = 0;
      deselect();
      setAnnoMode('select');
      markDirty();
      renderTabs();
      renderForm();
      rebuildAnno();
      syncProductActive();
    }, function (err) { console.warn('[dws] product defaults', err); toast('제품 기본값을 불러오지 못했습니다.'); });
  }

  /** 좌측 제품 패널 접기/펼치기 토글. */
  function toggleProducts() {
    if (!els.products) { return; }
    var collapsed = els.products.classList.toggle('dws-products-collapsed');
    if (els.productToggle) {
      els.productToggle.textContent = collapsed ? '▸' : '◂';
      els.productToggle.title = collapsed ? '제품 목록 펼치기' : '제품 목록 접기';
      els.productToggle.setAttribute('aria-label', els.productToggle.title);
    }
  }

  /** 실측 사진이 현재 제품 시트(activeIdx)에 표시 대상인지 판정.
      제품 시트면 그 제품(item_index===activeIdx) + 공통(null/음수)만 true. */
  function photoVisibleFor(photo, activeIdx) {
    if (activeIdx < 0) { return true; }   // 제품 시트 아님 → 전체 표시
    var ii = photo.item_index;
    return ii === activeIdx || ii == null || (isFiniteNum(ii) && ii < 0);
  }

  /** 실측 사진 썸네일 그리드를 렌더한다. 현재 시트가 제품 시트면 그 제품에 연결된 사진 +
      공통 사진만 표시하고(다른 제품 사진 숨김), 매칭 사진을 상단 우선 정렬한다. 제품 시트가
      아니면 전체 표시. 제목 카운트는 필터 후 개수. 라벨/alt/title 은 textContent·alt 로만(XSS 안전). */
  function renderPhotos() {
    if (!els.photos || !els.photoGrid) { return; }
    var cs = currentSheet();
    var activeIdx = (cs && isFiniteNum(cs.product_index)) ? cs.product_index : -1;
    var visible = measurePhotos.filter(function (p) { return photoVisibleFor(p, activeIdx); });
    els.photos.hidden = !visible.length;
    if (els.photosTitle) { els.photosTitle.textContent = '실측 사진 ' + visible.length; }
    els.photoGrid.textContent = '';
    if (!visible.length) { return; }
    var ordered = visible.slice();
    if (activeIdx >= 0) {
      // 안정 정렬(Array.sort ES2019+): 현재 제품 사진을 앞으로, 그 외는 원래 순서 보존.
      ordered.sort(function (a, b) {
        return ((a.item_index === activeIdx) ? 0 : 1) - ((b.item_index === activeIdx) ? 0 : 1);
      });
    }
    ordered.forEach(function (photo) {
      var cell = document.createElement('button');
      cell.type = 'button';
      cell.className = 'dws-photo';
      cell.title = photo.filename || '실측 사진';
      if (activeIdx >= 0 && photo.item_index === activeIdx) { cell.classList.add('dws-photo-match'); }
      var img = document.createElement('img');
      img.className = 'dws-photo-img';
      img.loading = 'lazy';
      img.alt = photo.filename || '실측 사진';
      img.src = photo.thumb_url || '';
      cell.appendChild(img);
      cell.addEventListener('click', function () { onPhotoClick(photo, cell); });
      els.photoGrid.appendChild(cell);
    });
  }

  /** 실측 사진 썸네일 클릭 → import-attachment 로 에셋 복사 후 캔버스에 삽입(로딩 표시). */
  function onPhotoClick(photo, cell) {
    if (!canSave) { toast('열람 전용 — 도면 담당자·도면팀 또는 관리자만 편집할 수 있습니다.'); return; }
    if (!currentSheet()) { toast('제품을 선택해 도면을 먼저 시작하세요.'); return; }
    if (!photo || !photo.key || cell.classList.contains('dws-photo-loading')) { return; }
    cell.classList.add('dws-photo-loading');
    jsonFetch(API_BASE + '/drawing-wizard/import-attachment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({ key: photo.key })
    }).then(function (r) {
      cell.classList.remove('dws-photo-loading');
      if (r.status !== 200 || !r.data || !r.data.success || !r.data.data || !r.data.data.key) {
        toast((r.data && r.data.message) || '실측 사진을 삽입하지 못했습니다.');
        return;
      }
      placeImageFromKey(r.data.data.key);
    }, function (err) {
      cell.classList.remove('dws-photo-loading');
      console.warn('[dws] import-attachment', err);
      toast('실측 사진 삽입 오류');
    });
  }

  /** 실측 사진 섹션 접기/펼치기 토글. */
  function togglePhotos() {
    if (!els.photos) { return; }
    var collapsed = els.photos.classList.toggle('dws-photos-collapsed');
    if (els.photosToggle) {
      els.photosToggle.textContent = collapsed ? '▸' : '▾';
      els.photosToggle.title = collapsed ? '실측 사진 펼치기' : '실측 사진 접기';
      els.photosToggle.setAttribute('aria-label', els.photosToggle.title);
    }
  }

  /* 현재 전달 대기함에 저장된 시트 id 집합(renderPending 이 재구성) — 캔버스 삭제버튼 가시성 판정용. */
  var pendingSheetIds = new Set();

  /* ---- 저장된 도면(전달 대기) 사이드 미리보기 -------------------------------
   * pending 목록(GET /drawing-wizard/pending)을 읽어 aside 에 썸네일 그리드로 렌더한다.
   * 항목 클릭 → 원본(asset-raw) 라이트박스 확대. 표시 전용(structured_data 쓰기 없음).
   * 로드 시 1회 + 매 save()/saveAll() 성공 직후 refreshPending() 으로 갱신한다.
   * ------------------------------------------------------------------------ */

  /** 전달 대기 도면 목록을 서버에서 다시 읽어 패널을 렌더한다(try/catch + success 검증). */
  function refreshPending() {
    if (!els.pending || !els.pendingGrid) { return; }
    jsonFetch(API_BASE + '/drawing-wizard/pending', { headers: { 'Accept': 'application/json' } }).then(function (r) {
      var list = (r.status === 200 && r.data && r.data.success && r.data.data && Array.isArray(r.data.data.pending))
        ? r.data.data.pending : [];
      renderPending(list);
    }, function (err) {
      console.warn('[dws] pending', err);
      renderPending([]);
    });
  }

  /** 저장된 도면 썸네일 그리드를 렌더한다(항목 없으면 패널 숨김). 각 항목 = asset-raw 썸네일(lazy)
      + 시트명 + 저장시각. 라벨/alt 는 textContent·alt 로만 삽입한다(XSS 안전, innerHTML 금지). */
  function renderPending(list) {
    if (!els.pending || !els.pendingGrid) { return; }
    var items = Array.isArray(list) ? list : [];
    els.pending.hidden = !items.length;
    if (els.pendingTitle) { els.pendingTitle.textContent = '저장된 도면 ' + items.length; }
    els.pendingGrid.textContent = '';
    pendingSheetIds = new Set();
    items.forEach(function (it) {
      if (!it || !it.key) { return; }
      if (it.sheet_id) { pendingSheetIds.add(it.sheet_id); }
      var name = String(it.sheet_name || it.filename || '도면');
      var cell = document.createElement('button');
      cell.type = 'button';
      cell.className = 'dws-pending-item';
      cell.title = name + (it.at ? (' · ' + it.at) : '');
      var img = document.createElement('img');
      img.className = 'dws-pending-thumb';
      img.loading = 'lazy';
      img.alt = name;
      img.src = viewUrl(it.key);
      var nameEl = document.createElement('span');
      nameEl.className = 'dws-pending-name';
      nameEl.textContent = name;
      var atEl = document.createElement('span');
      atEl.className = 'dws-pending-at';
      atEl.textContent = it.at || '';
      // 저장분 삭제 미니 × (셀은 <button>이므로 버튼 중첩 금지 → span + stopPropagation)
      var del = document.createElement('span');
      del.className = 'dws-pending-del';
      del.textContent = '×';
      del.title = '삭제';
      del.addEventListener('click', function (e) {
        e.stopPropagation();
        if (!confirm('저장된 도면을 삭제할까요? 되돌릴 수 없습니다.')) { return; }
        deletePending(it.sheet_id);
      });
      cell.appendChild(img);
      cell.appendChild(nameEl);
      cell.appendChild(atEl);
      cell.appendChild(del);
      cell.addEventListener('click', function () { openLightbox(it.key, name); });
      els.pendingGrid.appendChild(cell);
    });
    updateDeleteSavedBtn();
  }

  /** 전달 대기 도면 1건을 서버에서 삭제한다(DELETE). 성공 시 목록 재조회로 UI 동기화. */
  function deletePending(sheetId) {
    if (!sheetId) { return; }
    jsonFetch(API_BASE + '/drawing-wizard/pending/' + encodeURIComponent(sheetId), { method: 'DELETE' }).then(function (r) {
      if (r.status === 200 && r.data && r.data.success) {
        toast('저장된 도면을 삭제했습니다.');
        refreshPending();          // renderPending 재실행 → pendingSheetIds/버튼 가시성 갱신
      } else {
        toast((r.data && r.data.message) || '삭제하지 못했습니다.');
      }
    }, function () { toast('삭제 중 오류가 발생했습니다.'); });
  }

  /** 캔버스 우측상단 '저장분 삭제' 버튼 가시성 — 현재 시트에 저장분 있고 저장 권한일 때만 노출. */
  function updateDeleteSavedBtn() {
    if (!els.delSavedBtn) { return; }
    var cs = currentSheet();
    var show = !!(canSave && cs && cs.id && pendingSheetIds && pendingSheetIds.has(cs.id));
    els.delSavedBtn.hidden = !show;
  }

  /** 저장된 도면 섹션 접기/펼치기 토글. */
  function togglePending() {
    if (!els.pending) { return; }
    var collapsed = els.pending.classList.toggle('dws-pending-collapsed');
    if (els.pendingToggle) {
      els.pendingToggle.textContent = collapsed ? '▸' : '▾';
      els.pendingToggle.title = collapsed ? '저장된 도면 펼치기' : '저장된 도면 접기';
      els.pendingToggle.setAttribute('aria-label', els.pendingToggle.title);
    }
  }

  /** 저장된 도면 원본(asset-raw)을 라이트박스로 확대한다. */
  function openLightbox(key, alt) {
    if (!els.lightbox || !els.lightboxImg || !key) { return; }
    els.lightboxImg.src = viewUrl(key);
    els.lightboxImg.alt = String(alt || '저장된 도면 미리보기');
    els.lightbox.hidden = false;
  }

  /** 라이트박스를 닫고 src 를 비운다(대용량 원본 즉시 해제). */
  function closeLightbox() {
    if (!els.lightbox) { return; }
    els.lightbox.hidden = true;
    if (els.lightboxImg) { els.lightboxImg.removeAttribute('src'); }
  }

  /** 시트 0개면 빈 안내 오버레이 표시(제품 클릭·+시트로 첫 시트 생성 유도), ≥1이면 숨김.
      모든 상태 변경 렌더 경로(load·제품클릭·addSheet·switchSheet·복제·삭제·복원)가 renderTabs 를
      거치므로 여기서 단일 갱신한다. */
  function updateEmptyOverlay() {
    if (!els.empty) { return; }
    els.empty.hidden = (state.sheets.length > 0);
  }

  function renderTabs() {
    updateEmptyOverlay();
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
        var dup = document.createElement('span');
        dup.className = 'dws-tab-dup';
        dup.textContent = '⧉';
        dup.title = '시트 복제';
        dup.addEventListener('click', function (e) { e.stopPropagation(); duplicateSheet(i); });
        tab.appendChild(dup);
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
    syncProductActive();
    updateDeleteSavedBtn();
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
    syncProductActive();
  }

  /**
   * 시트 i 를 깊은 복제해 바로 뒤에 삽입·전환한다.
   * - attachment_id 삭제: 복제본 저장이 원본 도면 탭 첨부를 교체하는 사고를 차단(핵심).
   * - product_index 삭제: 제품 매핑 혼동 방지.
   * - 객체 id 재발급: state 내 id 중복 방지.
   * @param {number} i 복제할 시트 인덱스
   */
  function duplicateSheet(i) {
    if (!canSave) { return; }
    if (state.sheets.length >= 10) { toast('시트는 최대 10장까지 만들 수 있습니다.'); return; }
    var src = state.sheets[i];
    if (!src) { return; }
    var copy = JSON.parse(JSON.stringify(src));
    copy.id = rid('s-');
    copy.name = String(src.name || '도면').slice(0, 47) + ' 복사';   // ' 복사'(3자) 포함 최대 50자
    delete copy.attachment_id;
    delete copy.product_index;
    (copy.objects || []).forEach(function (o) { o.id = rid('o-'); });
    state.sheets.splice(i + 1, 0, copy);
    current = i + 1;
    undoStack.length = 0;
    redoStack.length = 0;
    deselect();
    markDirty();
    renderTabs();
    renderForm();
    rebuildAnno();
    syncProductActive();
    toast('시트를 복제했습니다.');
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
    syncProductActive();
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
    els.zoomRange.value = String(clamp(pct, 50, 250));
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
    if (!canSave || !currentSheet()) { return; }
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
    if (els.mtPresetMenu) { els.mtPresetMenu.hidden = true; }
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

  /* ---- 프리셋 메뉴: 기본 4개(코드 상수) + 사용자 프리셋(전역) 동적 렌더 ---- */
  var PRESETS_ENDPOINT = '/api/orders/drawing-wizard/presets';

  /** 프리셋 메뉴를 재구성한다. 기본 프리셋은 삭제 불가, 사용자 프리셋만 ×·저장 노출.
      모든 라벨/본문은 textContent 로만 삽입한다(XSS 안전, innerHTML 금지). */
  function renderPresetMenu() {
    var menu = els.presetMenu;
    if (!menu) { return; }
    menu.textContent = '';

    Object.keys(PRESETS).forEach(function (kind) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'dws-menu-item';
      b.setAttribute('data-preset', kind);
      b.textContent = PRESETS[kind];
      b.addEventListener('click', function () { closeMenus(); addPreset(kind); });
      menu.appendChild(b);
    });

    userPresets.forEach(function (p, idx) {
      var row = document.createElement('div');
      row.className = 'dws-preset-row';
      var ins = document.createElement('button');
      ins.type = 'button';
      ins.className = 'dws-menu-item dws-preset-ins';
      ins.textContent = p.label || p.text;
      ins.title = p.text;
      ins.addEventListener('click', function () { closeMenus(); insertPresetText(p.text, false); });
      row.appendChild(ins);
      if (canSave) {
        var del = document.createElement('button');
        del.type = 'button';
        del.className = 'dws-preset-del';
        del.title = '삭제';
        del.setAttribute('aria-label', '프리셋 삭제');
        del.textContent = '×';
        del.addEventListener('click', function (e) { e.stopPropagation(); deleteUserPreset(idx); });
        row.appendChild(del);
      }
      menu.appendChild(row);
    });

    if (canSave) {
      var sep = document.createElement('div');
      sep.className = 'dws-preset-sep';
      menu.appendChild(sep);
      var addBtn = document.createElement('button');
      addBtn.type = 'button';
      addBtn.className = 'dws-menu-item dws-preset-add';
      addBtn.textContent = '+ 현재 텍스트를 프리셋으로 저장';
      addBtn.addEventListener('click', function () { closeMenus(); saveCurrentAsPreset(); });
      menu.appendChild(addBtn);
    }
  }

  /** 전역 프리셋 목록을 로드해 메뉴를 갱신한다(실패 시 기본 프리셋만). */
  function loadUserPresets() {
    jsonFetch(PRESETS_ENDPOINT, { headers: { 'Accept': 'application/json' } }).then(function (r) {
      if (r.status === 200 && r.data && r.data.success && r.data.data) {
        userPresets = r.data.data.presets || [];
      } else {
        userPresets = [];
      }
      renderPresetMenu();
    });
  }

  /** 프리셋 목록을 서버에 저장(POST)하고 성공 시 메뉴 갱신 + 토스트. */
  function persistUserPresets(list, okMsg) {
    jsonFetch(PRESETS_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({ presets: list })
    }).then(function (r) {
      if (r.status !== 200 || !r.data || !r.data.success) {
        toast((r.data && r.data.message) || '프리셋 저장에 실패했습니다.');
        return;
      }
      userPresets = (r.data.data && r.data.data.presets) || [];
      renderPresetMenu();
      toast(okMsg);
    });
  }

  /** 선택된 텍스트(없으면 prompt)를 라벨과 함께 새 프리셋으로 저장. */
  function saveCurrentAsPreset() {
    if (!canSave) { return; }
    var text = '';
    var o = findObj(selected);
    if (o && o.type === 'text' && String(o.text || '').trim()) {
      text = String(o.text).trim();
    } else {
      text = String(window.prompt('프리셋으로 저장할 텍스트를 입력하세요.') || '').trim();
    }
    if (!text) { return; }
    var defaultLabel = text.split('\n')[0].slice(0, 20);
    var label = String(window.prompt('프리셋 이름(라벨)을 입력하세요.', defaultLabel) || '').trim();
    if (!label) { label = defaultLabel; }
    persistUserPresets(userPresets.concat([{ label: label, text: text }]), '프리셋을 저장했습니다.');
  }

  /** 인덱스의 사용자 프리셋을 제외하고 저장(삭제). */
  function deleteUserPreset(idx) {
    if (!canSave) { return; }
    persistUserPresets(userPresets.filter(function (_, i) { return i !== idx; }), '프리셋을 삭제했습니다.');
  }

  /* ---- 텍스트 편집 미니바 프리셋 드롭다운(편집 중 커서 위치에 즉시 삽입) --------
     앱바 프리셋(새 텍스트 객체 생성)과 별개로, 편집 중 오버레이 커서에 텍스트만 삽입한다.
     선택 유지: 미니바 mousedown 이 preventDefault 되어(els.mt 핸들러) 오버레이 포커스가
     유지되므로 execCommand('insertText') 가 캐럿 위치에 정확히 삽입된다. */

  /** 편집 오버레이 커서 위치에 프리셋 텍스트 삽입(편집 유지 — blur/커밋 없음). */
  function insertPresetIntoEdit(text) {
    if (!editCtx || !editCtx.area) { return; }
    editCtx.area.focus();
    insertPlainText(String(text || ''));   // textContent 경로만(XSS 안전), execCommand insertText
    positionEditToolbar();
  }

  /** 편집 미니바 프리셋 메뉴 재구성: 기본 4개(코드 상수) + 사용자 프리셋(전역). 삽입 전용.
      라벨/본문은 textContent 로만 삽입(XSS 안전, innerHTML 금지). */
  function renderEditPresetMenu() {
    var menu = els.mtPresetMenu;
    if (!menu) { return; }
    menu.textContent = '';
    Object.keys(PRESETS).forEach(function (kind) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'dws-menu-item';
      b.textContent = PRESETS[kind];
      b.addEventListener('click', function (e) { e.stopPropagation(); insertPresetIntoEdit(PRESETS[kind]); closeMenus(); });
      menu.appendChild(b);
    });
    userPresets.forEach(function (p) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'dws-menu-item dws-preset-ins';
      b.textContent = p.label || p.text;
      b.title = p.text;
      b.addEventListener('click', function (e) { e.stopPropagation(); insertPresetIntoEdit(p.text); closeMenus(); });
      menu.appendChild(b);
    });
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
    if (o.type === 'pen') {
      var penPts = normalizePenPoints(o.points);
      if (penPts.length < 4) { return null; }   // 점 부족 획은 저장에서 제외(서버 400 예방)
      var pen = {
        id: o.id, type: 'pen', points: penPts,
        stroke: colorOrDefault(o.stroke), strokeWidth: penWidthOrDefault(o.strokeWidth), rotation: rot
      };
      var penOp = penOpacityOrNull(o.opacity);   // 형광펜 반투명 보존(불투명이면 필드 생략)
      if (penOp != null) { pen.opacity = penOp; }
      return pen;
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

  /** 시트 1장 → 직렬화 객체(저장·버전 스냅샷 공용). */
  function serializeSheet(s) {
    var out = {
      id: s.id, name: s.name, form: serializeForm(s.form),
      objects: (s.objects || []).map(serializeObj).filter(function (o) { return !!o; })
    };
    // 제품별 시트 승격 값(서버가 그대로 보존): 인덱스·도면탭 첨부 식별자.
    if (isFiniteNum(s.product_index) && s.product_index >= 0 && s.product_index <= 199) {
      out.product_index = Math.round(s.product_index);
    }
    if (isFiniteNum(s.attachment_id) && s.attachment_id >= 0) {
      out.attachment_id = Math.round(s.attachment_id);
    }
    return out;
  }

  function serializeState() {
    return { v: 1, sheets: state.sheets.map(serializeSheet) };
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
    if (o.type === 'pen') {
      var pen = {
        id: o.id || rid('o-'), type: 'pen', points: normalizePenPoints(o.points),
        stroke: colorOrDefault(o.stroke), strokeWidth: penWidthOrDefault(o.strokeWidth), rotation: rot
      };
      var penOp = penOpacityOrNull(o.opacity);   // 형광펜 반투명 로드 보존(누락=불투명)
      if (penOp != null) { pen.opacity = penOp; }
      return pen;
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
      var sheet = {
        id: s.id || rid('s-'),
        name: s.name || '도면',
        form: serializeForm(mergeFormDefaults(s.form)),
        objects: (s.objects || [])
          .filter(function (o) { return o && ['text', 'image', 'rect', 'ellipse', 'arrow', 'line', 'pen'].indexOf(o.type) >= 0; })
          .map(normalizeObj)
      };
      if (isFiniteNum(s.product_index)) { sheet.product_index = Math.round(s.product_index); }
      if (isFiniteNum(s.attachment_id)) { sheet.attachment_id = Math.round(s.attachment_id); }
      return sheet;
    });
    // 빈 배열은 그대로 반환 — 기본 시트 자동 생성 없음(제품 클릭/+시트로만 생성).
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
      products = d.products || [];
      measurePhotos = d.measure_photos || [];
      customerName = d.customer_name || customerName;
      els.customer.textContent = '(' + customerName + ')';
      if (d.state && d.state.sheets && d.state.sheets.length) {
        state = normalizeState(d.state);
        baseUpdatedAt = d.state.updated_at || null;
      } else {
        // 저장된 도면 없음 → 빈 상태(기본 시트 자동 생성 안 함). 제품 클릭/+시트로만 시트 생성.
        state = { v: 1, sheets: [] };
        baseUpdatedAt = null;
      }
      current = 0;
      undoStack.length = 0;
      redoStack.length = 0;
      dirty = false;
      // 저장 시트라도 지정 도면담당자의 영문명이 있으면 DREW를 그 값으로 동기화(담당자 기준 SSOT).
      if (d.drew_assignee_en) {
        var changed = false;
        state.sheets.forEach(function (s) {
          if (s.form && s.form.drew !== d.drew_assignee_en) { s.form.drew = d.drew_assignee_en; changed = true; }
        });
        if (changed) { dirty = true; }   // 값이 실제로 바뀌면 저장 유도(dirty 표시)
      }
      // 제품별 시트의 페이지 번호가 비어있으면(과거 저장분) 제품 번호(1-base)로 자동 채움.
      // 사용자가 이미 값을 넣었으면 유지.
      (function () {
        var numbered = false;
        state.sheets.forEach(function (s) {
          if (!s.form || !isFiniteNum(s.product_index)) { return; }
          var cur = String(s.form.page_no == null ? '' : s.form.page_no).trim();
          if (cur === '' || cur === '-') { s.form.page_no = String(s.product_index + 1); numbered = true; }
        });
        if (numbered) { dirty = true; }
      })();
      selectedIds = [];
      selected = null;
      setAnnoMode('select');
      applyPermissions();
      wireFormEditing();
      renderProducts();
      renderTabs();
      renderForm();
      rebuildAnno();
      updateSaveState();
      fitZoom();
      refreshPending();   // 저장된 도면(전달 대기) 미리보기 패널 초기 로드
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

  /**
   * 상태를 서버에 저장한다. Promise<boolean> 반환(true = 상태 PUT 성공).
   * @param {Object} [opts]
   * @param {boolean} [opts.auto] 자동 저장(주기 타이머)일 때 true. 이 경우
   *   (a) PNG 도면 탭 갱신 생략(수동 저장 전용), (b) 409 시 confirm 대신 1회성 경고
   *   토스트 + dirty 유지, (c) 성공 토스트 없음(저장 버튼 dirty 해제로 충분).
   * @returns {Promise<boolean>}
   */
  function save(opts) {
    opts = opts || {};
    var auto = opts.auto === true;
    if (!canSave || saveInFlight) { return Promise.resolve(false); }
    if (!state.sheets.length) {
      if (!auto) { toast('저장할 도면이 없습니다. 제품을 선택해 도면을 먼저 만드세요.'); }
      return Promise.resolve(false);
    }
    if (!auto) {
      // 수동 저장만 활성 편집을 커밋·blur(자동 저장은 폼 셀 포커스/캐럿을 방해하지 않음).
      if (commitActiveEdit) { commitActiveEdit(); }
      if (document.activeElement && document.activeElement.blur) { document.activeElement.blur(); }
    }
    saveInFlight = true;
    var sheet = currentSheet();   // 저장 시점 시트 참조(비동기 PNG 단계 동안 고정)
    var body = { state: serializeState(), base_updated_at: baseUpdatedAt };
    els.saveBtn.disabled = true;
    return jsonFetch(API_BASE + '/drawing-wizard', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    }).then(function (r) {
      if (r.status === 200 && r.data && r.data.success) {
        baseUpdatedAt = (r.data.data && r.data.data.updated_at) || baseUpdatedAt;
        dirty = false;
        autoConflictWarned = false;   // 저장 성공 → 다음 충돌 시 다시 1회 경고 허용
        updateSaveState();
        if (auto) {
          els.saveBtn.disabled = false;
          saveInFlight = false;
          return true;   // 자동 저장: PNG 도면 탭 갱신 생략, 조용히 성공
        }
        // 수동 저장: 상태 확정 후 PNG 를 도면 탭에 반영(버튼 재활성·토스트는 내부에서).
        return saveSheetPng(sheet).then(function () {
          saveInFlight = false;
          refreshPending();   // 전달 대기함에 새 시트 반영 → 미리보기 패널 갱신
          return true;
        });
      }
      els.saveBtn.disabled = false;
      saveInFlight = false;
      if (r.status === 409) {
        if (auto) {
          if (!autoConflictWarned) {
            autoConflictWarned = true;
            toast('자동 저장 충돌 — 다른 사용자가 저장했습니다. 수동 저장으로 확인하세요.');
          }
          // dirty 유지(이미 true) — 수동 저장으로 충돌을 확인하도록 둔다.
        } else {
          handleConflict(r.data);
        }
      } else {
        toast((r.data && r.data.message) || ('저장 실패 (' + r.status + ')'));
      }
      return false;
    }, function (err) {
      els.saveBtn.disabled = false;
      saveInFlight = false;
      console.warn('[dws] save', err);
      if (!auto) { toast('저장 오류'); }
      return false;
    });
  }

  /** 자동 저장 틱: 안전 조건을 모두 만족할 때만 조용히 저장(수동 저장 동작 불변). */
  function tickAutosave() {
    if (!dirty || !canSave || saveInFlight) { return; }
    if (!state.sheets.length) { return; }          // 빈 상태(시트 0개)는 저장 대상 없음
    if (editingTextarea || editCtx) { return; }   // 주석 텍스트 편집 중이면 보류
    if (annoMode !== 'select') { return; }         // 그리기/도형 모드면 보류
    if (dragActive) { return; }                    // 드래그·변형 진행 중이면 보류
    save({ auto: true });
  }

  /** 합성 canvas → PNG blob(Promise). 실패 시 reject. */
  function canvasToPngBlob(cv) {
    return new Promise(function (resolve, reject) {
      cv.toBlob(function (blob) {
        if (blob) { resolve(blob); } else { reject(new Error('PNG 생성 실패')); }
      }, 'image/png');
    });
  }

  /** PNG blob 을 '전달 대기함'(sheet-png)에 POST. 성공 시 true, 실패 시 throw(집계·재시도 판단은 호출측). */
  function postSheetPngBlob(blob, sheet) {
    var fd = new FormData();
    fd.append('file', blob, sheetPngFilename(sheet));
    fd.append('sheet_id', String((sheet && sheet.id) || ''));
    fd.append('sheet_name', String((sheet && sheet.name) || ''));
    return jsonFetch(API_BASE + '/drawing-wizard/sheet-png', { method: 'POST', body: fd }).then(function (r) {
      if (r.status === 200 && r.data && r.data.success && r.data.data) { return true; }
      console.warn('[dws] sheet-png', r.status, r.data);
      throw new Error('sheet-png 저장 실패');
    });
  }

  /**
   * 현재 DOM 이 반영하는 시트를 PNG 로 합성해 '전달 대기함'(structured_data.drawing_wizard.pending)에
   * 보관한다(주문 '도면' 탭 저장 아님 — 담당자 전달은 도면 작업실의 일괄 전송이 담당).
   * 같은 시트(sheet_id) 재저장 시 서버가 구 PNG를 교체한다. 추가 PUT은 하지 않는다(단일·일괄 저장 공용).
   * @param {Object} sheet 저장 시점의 시트(비동기 동안 참조 고정)
   * @returns {Promise<true>} 실패 시 reject
   */
  function pushSheetPng(sheet) {
    return withExportMode().then(canvasToPngBlob).then(function (blob) {
      return postSheetPngBlob(blob, sheet);
    });
  }

  function saveSheetPng(sheet) {
    return pushSheetPng(sheet).then(function () {
      els.saveBtn.disabled = false;
      toast('저장됨 · 전달 대기함에 보관');
    }, function (err) {
      els.saveBtn.disabled = false;
      console.warn('[dws] sheet-png export', err);
      toast('저장됨 (도면 이미지 저장 실패)');
    });
  }

  var IMG_SETTLE_MS = 4000;

  /** 현재 시트의 Konva 이미지 노드가 모두 로드될 때까지(또는 timeout) 대기한다.
      시트 전환 직후 이미지가 아직 로드 중이면 합성 PNG 가 빈 프레임이 되므로 배치 렌더 정합용. */
  function waitForSheetImages(timeoutMs) {
    return new Promise(function (resolve) {
      if (!konvaLayer) { resolve(); return; }
      var imgNodes = [];
      konvaLayer.find('.anno').forEach(function (n) {
        if (n.getAttr('annoType') === 'image') { imgNodes.push(n); }
      });
      if (!imgNodes.length) { resolve(); return; }
      var deadline = Date.now() + (timeoutMs || IMG_SETTLE_MS);
      (function poll() {
        var pending = imgNodes.some(function (n) { return !n.image(); });
        if (!pending || Date.now() >= deadline) { resolve(); return; }
        setTimeout(poll, 60);
      })();
    });
  }

  /**
   * 모든 시트를 순차로 PNG blob 으로 렌더하며 handler(blob, sheet, i)를 호출한다.
   * 각 시트: switchSheet → 이미지 로드 대기 → withExportMode → PNG blob → handler(Promise 가능).
   * 개별 시트 실패는 스킵·집계(전체 중단 없음). 원 시트 복귀는 호출측 책임.
   * @param {function} handler (blob, sheet, index) → Promise|void
   * @param {string} label 진행 토스트 접두어("일괄 저장" 등)
   * @returns {Promise<{ok:number, fail:string[], total:number}>}
   */
  function eachSheetToBlob(handler, label) {
    var total = state.sheets.length;
    var okCount = 0;
    var failNames = [];
    var chain = Promise.resolve();
    state.sheets.forEach(function (s, i) {
      chain = chain.then(function () {
        toast(label + ' ' + (i + 1) + '/' + total + ' 처리 중…');
        switchSheet(i);
        return waitForSheetImages(IMG_SETTLE_MS)
          .then(withExportMode)
          .then(canvasToPngBlob)
          .then(function (blob) { return handler(blob, state.sheets[i], i); })
          .then(function () { okCount += 1; }, function (err) {
            console.warn('[dws] eachSheetToBlob', i, err);
            failNames.push((state.sheets[i] && state.sheets[i].name) || ('시트 ' + (i + 1)));
          });
      });
    });
    return chain.then(function () { return { ok: okCount, fail: failNames, total: total }; });
  }

  /**
   * 일괄 저장(X-1): state 전체 PUT 1회 → 모든 시트를 순차로 PNG 합성해 전달 대기함에 보관.
   * PUT 은 1회만(무한루프 금지). 개별 시트 PNG 실패는 스킵·집계. 완료 후 원 시트 복귀.
   */
  function saveAll() {
    if (!canSave || saveInFlight) { return; }
    if (!state.sheets.length) {
      toast('저장할 도면이 없습니다. 제품을 선택해 도면을 먼저 만드세요.');
      return;
    }
    if (commitActiveEdit) { commitActiveEdit(); }
    if (document.activeElement && document.activeElement.blur) { document.activeElement.blur(); }
    saveInFlight = true;
    var origIdx = current;
    els.saveBtn.disabled = true;
    if (els.saveAllBtn) { els.saveAllBtn.disabled = true; }
    var body = { state: serializeState(), base_updated_at: baseUpdatedAt };
    jsonFetch(API_BASE + '/drawing-wizard', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    }).then(function (r) {
      if (!(r.status === 200 && r.data && r.data.success)) {
        finishSaveAll();
        if (r.status === 409) { handleConflict(r.data); }
        else { toast((r.data && r.data.message) || ('저장 실패 (' + r.status + ')')); }
        return;
      }
      baseUpdatedAt = (r.data.data && r.data.data.updated_at) || baseUpdatedAt;
      dirty = false;
      autoConflictWarned = false;
      updateSaveState();
      return eachSheetToBlob(postSheetPngBlob, '일괄 저장').then(function (res) {
        switchSheet(origIdx);
        finishSaveAll();
        refreshPending();   // 전달 대기함에 저장된 시트들 반영 → 미리보기 패널 갱신
        if (res.fail.length) {
          toast('일괄 저장 완료 · ' + res.ok + '/' + res.total + ' 성공, ' + res.fail.length + '건 실패');
        } else {
          toast('일괄 저장 완료 · ' + res.total + '개 시트를 전달 대기함에 보관');
        }
      });
    }, function (err) {
      finishSaveAll();
      console.warn('[dws] save-all', err);
      toast('저장 오류');
    });
  }

  function finishSaveAll() {
    saveInFlight = false;
    els.saveBtn.disabled = false;
    if (els.saveAllBtn) { els.saveAllBtn.disabled = false; }
  }

  /* ========================================================================
   * [7] export / transfer
   * ====================================================================== */
  function sheetPngFilename(sheet) {
    var safe = function (s) { return String(s || '').replace(/[\\/:*?"<>|\n\r]/g, '_').trim() || '무제'; };
    return '도면_' + safe(customerName) + '_' + ORDER_ID + '_' + safe((sheet || {}).name) + '.png';
  }
  function exportFilename() { return sheetPngFilename(currentSheet()); }

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
    if (!state.sheets.length) { toast('내보낼 도면이 없습니다.'); return; }
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

  /** 파일/폴더명 안전화: `/\:*?"<>|` 및 제어문자 제거·trim, 빈 값은 '무제'. */
  function fsSafe(s) {
    return String(s == null ? '' : s).replace(/[\\/:*?"<>|\n\r\t]/g, '').trim() || '무제';
  }

  /** 오늘 날짜 MMDD(예: 7월 8일 → "0708"). 폴더명 접두에 사용. */
  function todayMMDD() {
    var d = new Date();
    return ('0' + (d.getMonth() + 1)).slice(-2) + ('0' + d.getDate()).slice(-2);
  }

  /** 일괄 내보내기 파일명: `고객이름도면번호.png`(붙여쓰기, 도면번호=page_no, 없으면 순번+1).
      .png 확장자 필수 — 없으면 Windows 가 PNG 로 인식 못 함(탐색기는 알려진 확장자를 기본 숨김). */
  function exportSheetFilename(sheet, i) {
    var form = (sheet && sheet.form) || {};
    var pageNo = String(form.page_no == null ? '' : form.page_no).trim();
    if (!pageNo) { pageNo = String(i + 1); }
    return fsSafe(customerName) + fsSafe(pageNo) + '.png';
  }

  /** 일괄 내보내기 폴더명: `MMDD 고객이름`(오늘 날짜 + 1칸 공백 + 고객이름). */
  function exportFolderName() {
    return todayMMDD() + ' ' + fsSafe(customerName);
  }

  /**
   * 일괄 내보내기(X-3): 모든 시트 PNG 를 로컬 폴더에 저장.
   * File System Access API(showDirectoryPicker) 지원 시 `MMDD 고객이름` 서브폴더에 저장, 미지원이면 개별 다운로드.
   * showDirectoryPicker 는 사용자 제스처(버튼 클릭) 안에서 직접 호출해야 하므로 클릭 핸들러에서 진입한다.
   */
  function exportAll() {
    closeMenus();
    if (!state.sheets.length) { toast('내보낼 도면이 없습니다.'); return; }
    if (typeof window.showDirectoryPicker === 'function') {
      exportAllToDirectory();
    } else {
      exportAllFallbackDownloads();
    }
  }

  /** 폴더 선택 → `MMDD 고객이름` 서브폴더 생성 → 각 시트 PNG 를 파일로 write. */
  function exportAllToDirectory() {
    var origIdx = current;
    var folderName = exportFolderName();
    // showDirectoryPicker 는 제스처 직후 동기 호출(이 함수는 클릭 핸들러 콜스택 내에서 즉시 진입).
    // id: 같은 id 로 재호출 시 브라우저가 마지막 선택 폴더를 기억(두 번째부터 그 위치에서 열림).
    // startIn: 시작 위치를 문서로 유도 — 드라이브 루트/시스템 폴더 선택(브라우저 차단)을 줄인다.
    window.showDirectoryPicker({ mode: 'readwrite', id: 'dwsExport', startIn: 'documents' }).then(function (dirHandle) {
      return dirHandle.getDirectoryHandle(folderName, { create: true });
    }).then(function (custDir) {
      return eachSheetToBlob(function (blob, sheet, i) {
        return custDir.getFileHandle(exportSheetFilename(sheet, i), { create: true })
          .then(function (fh) { return fh.createWritable(); })
          .then(function (writable) {
            return Promise.resolve(writable.write(blob)).then(function () { return writable.close(); });
          });
      }, '일괄 내보내기').then(function (res) {
        switchSheet(origIdx);
        if (res.fail.length) {
          toast('일괄 내보내기 완료 · ' + res.ok + '/' + res.total + ' 성공, ' + res.fail.length + '건 실패');
        } else {
          toast('일괄 내보내기 완료 · "' + folderName + '" 폴더에 ' + res.total + '개 저장');
        }
      });
    }).catch(function (err) {
      if (err && err.name === 'AbortError') {
        // 폴더 선택 취소 또는 브라우저의 특수 폴더 차단(드라이브 루트·Windows·홈 루트·바탕화면·
        // OneDrive·다운로드) → showDirectoryPicker 는 둘 다 AbortError 로 오므로 안내 토스트로 통일.
        toast('폴더 선택이 취소되었거나 차단되었습니다. 바탕화면·OneDrive·시스템 폴더는 브라우저가 막습니다 — C:\\도면 같은 일반 폴더를 만들어 지정하세요.');
        return;
      }
      switchSheet(origIdx);
      console.warn('[dws] export-all', err);
      toast('일괄 내보내기 실패: ' + ((err && err.message) || '알 수 없는 오류'));
    });
  }

  /** 미지원 브라우저 폴백: 각 시트 PNG 를 같은 파일명 규칙으로 개별 다운로드(폴더 없음). */
  function exportAllFallbackDownloads() {
    toast('이 브라우저는 폴더 저장을 지원하지 않습니다 — 개별 다운로드로 진행합니다.');
    var origIdx = current;
    eachSheetToBlob(function (blob, sheet, i) {
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = exportSheetFilename(sheet, i);
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
    }, '개별 다운로드').then(function (res) {
      switchSheet(origIdx);
      toast('개별 다운로드 완료 · ' + res.ok + '/' + res.total + '개');
    });
  }

  /* ========================================================================
   * [7b] version history (이전 버전 복원 · 전달 시점 스냅샷은 작업실 일괄 전송이 기록)
   * ====================================================================== */

  function openVersionDialog() {
    closeMenus();
    renderVersionList([{ __loading: true }]);
    if (els.versionDialog.showModal) {
      try { els.versionDialog.showModal(); } catch (_) { els.versionDialog.setAttribute('open', ''); }
    } else {
      els.versionDialog.setAttribute('open', '');
    }
    jsonFetch(API_BASE + '/drawing-wizard/versions', { headers: { 'Accept': 'application/json' } })
      .then(function (r) {
        if (r.status !== 200 || !r.data || !r.data.success || !r.data.data) {
          renderVersionList([]); toast((r.data && r.data.message) || '버전 목록을 불러오지 못했습니다.'); return;
        }
        renderVersionList(r.data.data.versions || []);
      }, function (err) { console.warn('[dws] versions', err); renderVersionList([]); toast('버전 목록 오류'); });
  }

  function closeVersionDialog() {
    if (els.versionDialog.close) {
      try { els.versionDialog.close(); } catch (_) { els.versionDialog.removeAttribute('open'); }
    } else {
      els.versionDialog.removeAttribute('open');
    }
  }

  /** 버전 목록 렌더(최신 우선). 라벨/시각/작성자는 textContent 로만 삽입(XSS 안전). */
  function renderVersionList(versions) {
    var list = els.versionList;
    if (!list) { return; }
    list.textContent = '';
    if (versions.length === 1 && versions[0] && versions[0].__loading) {
      var loading = document.createElement('p');
      loading.className = 'dws-version-empty';
      loading.textContent = '불러오는 중…';
      list.appendChild(loading);
      return;
    }
    if (!versions.length) {
      var empty = document.createElement('p');
      empty.className = 'dws-version-empty';
      empty.textContent = '아직 저장된 버전이 없습니다. 도면을 전달하면 버전이 기록됩니다.';
      list.appendChild(empty);
      return;
    }
    versions.slice().reverse().forEach(function (p) {
      if (!p || !p.key) { return; }
      var row = document.createElement('div');
      row.className = 'dws-version-row';
      var meta = document.createElement('div');
      meta.className = 'dws-version-meta';
      var title = document.createElement('div');
      title.className = 'dws-version-title';
      title.textContent = 'v' + (p.v || '?') + ' · ' + (p.sheet_name || '도면');
      var sub = document.createElement('div');
      sub.className = 'dws-version-sub';
      sub.textContent = (p.at || '') + (p.by_name ? (' · ' + p.by_name) : '');
      meta.appendChild(title);
      meta.appendChild(sub);
      row.appendChild(meta);
      if (canSave) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'dws-btn dws-version-restore';
        btn.textContent = '새 시트로 복원';
        btn.addEventListener('click', function () { restoreVersion(p); });
        row.appendChild(btn);
      }
      list.appendChild(row);
    });
  }

  /** 버전 스냅샷 내용을 새 시트로 복원(id 재발급·attachment_id/product_index 제거·전환·dirty). */
  function restoreVersion(p) {
    if (!canSave) { return; }
    if (state.sheets.length >= 10) { toast('시트는 최대 10장까지 만들 수 있습니다.'); return; }
    jsonFetch(API_BASE + '/drawing-wizard/version-content?key=' + encodeURIComponent(p.key),
      { headers: { 'Accept': 'application/json' } })
      .then(function (r) {
        if (r.status !== 200 || !r.data || !r.data.success || !r.data.data || !r.data.data.sheet) {
          toast((r.data && r.data.message) || '버전 내용을 불러오지 못했습니다.'); return;
        }
        if (state.sheets.length >= 10) { toast('시트는 최대 10장까지 만들 수 있습니다.'); return; }
        var norm = normalizeState({ v: 1, sheets: [r.data.data.sheet] });
        var sheet = norm.sheets[0];
        sheet.id = rid('s-');
        sheet.name = (String(p.sheet_name || sheet.name || '도면')).slice(0, 40) + ' (v' + (p.v || '?') + ' 복원)';
        delete sheet.attachment_id;
        delete sheet.product_index;
        (sheet.objects || []).forEach(function (o) { o.id = rid('o-'); });
        state.sheets.push(sheet);
        current = state.sheets.length - 1;
        undoStack.length = 0;
        redoStack.length = 0;
        deselect();
        markDirty();
        renderTabs();
        renderForm();
        rebuildAnno();
        syncProductActive();
        closeVersionDialog();
        toast('v' + (p.v || '?') + ' 을(를) 새 시트로 복원했습니다.');
      }, function (err) { console.warn('[dws] version-content', err); toast('버전 복원 오류'); });
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
    els.saveBtn.addEventListener('click', function () { save(); });
    if (els.saveAllBtn) { els.saveAllBtn.addEventListener('click', saveAll); }

    // 빈 상태 오버레이 — "빈 시트 추가"(제품 없는 주문 대비). addSheet 는 defaults 로 시트 생성.
    if (els.emptyAdd) { els.emptyAdd.addEventListener('click', function () { addSheet(); }); }

    // 좌측 제품 리스트 패널 접기/펼치기
    if (els.productToggle) { els.productToggle.addEventListener('click', toggleProducts); }
    // 실측 사진 섹션 접기/펼치기
    if (els.photosToggle) { els.photosToggle.addEventListener('click', togglePhotos); }
    // 저장된 도면(전달 대기) 섹션 접기/펼치기 + 썸네일 라이트박스 닫기(닫기 버튼·배경 클릭)
    if (els.pendingToggle) { els.pendingToggle.addEventListener('click', togglePending); }
    // 캔버스 우측상단 '저장분 삭제' — 현재 시트의 전달 대기 도면 삭제(가시성은 updateDeleteSavedBtn 관리)
    if (els.delSavedBtn) {
      els.delSavedBtn.addEventListener('click', function () {
        var cs = currentSheet();
        if (!cs) { return; }
        if (!confirm('저장된 도면을 삭제할까요? 되돌릴 수 없습니다.')) { return; }
        deletePending(cs.id);
      });
    }
    if (els.lightboxClose) { els.lightboxClose.addEventListener('click', closeLightbox); }
    if (els.lightbox) {
      els.lightbox.addEventListener('click', function (e) { if (e.target === els.lightbox) { closeLightbox(); } });
    }

    // 프리셋 메뉴 (기본 4개 + 사용자 프리셋 동적 렌더; 항목 배선은 renderPresetMenu 내부)
    var presetBtn = document.getElementById('dws-btn-preset');
    presetBtn.addEventListener('click', function (e) { e.stopPropagation(); toggleMenu(els.presetMenu); });
    renderPresetMenu();

    // 도형 메뉴 → 그리기 모드 진입
    var shapeBtn = document.getElementById('dws-btn-shape');
    shapeBtn.addEventListener('click', function (e) { e.stopPropagation(); toggleMenu(els.shapeMenu); });
    Array.prototype.forEach.call(els.shapeMenu.querySelectorAll('[data-shape]'), function (b) {
      b.addEventListener('click', function () { closeMenus(); setAnnoMode(b.getAttribute('data-shape')); });
    });

    // 펜(프리핸드) 도구 + 팔레트(펜/형광펜 토글·색·굵기) — 토글 진입, 팔레트는 펜 모드일 때만 노출.
    var penBtn = document.getElementById('dws-btn-pen');
    if (penBtn) { penBtn.addEventListener('click', function () { closeMenus(); setAnnoMode(annoMode === 'pen' ? 'select' : 'pen'); }); }
    if (els.penPalette) {
      Array.prototype.forEach.call(els.penPalette.querySelectorAll('[data-pen-mode]'), function (b) {
        b.addEventListener('click', function () { setPenMode(b.getAttribute('data-pen-mode')); });
      });
      Array.prototype.forEach.call(els.penPalette.querySelectorAll('[data-pen-color]'), function (b) {
        b.addEventListener('click', function () { setPenColor(b.getAttribute('data-pen-color')); });
      });
      Array.prototype.forEach.call(els.penPalette.querySelectorAll('[data-pen-width]'), function (b) {
        b.addEventListener('click', function () { setPenWidth(parseInt(b.getAttribute('data-pen-width'), 10)); });
      });
      Array.prototype.forEach.call(els.penPalette.querySelectorAll('[data-hi-color]'), function (b) {
        b.addEventListener('click', function () { setHiColor(b.getAttribute('data-hi-color')); });
      });
      Array.prototype.forEach.call(els.penPalette.querySelectorAll('[data-hi-width]'), function (b) {
        b.addEventListener('click', function () { setHiWidth(parseInt(b.getAttribute('data-hi-width'), 10)); });
      });
    }

    // 지우개 도구 — 토글 진입(획/주석 통째 삭제). 팔레트·미니툴바 없음(세그 active 로 표시).
    var eraserBtn = document.getElementById('dws-btn-eraser');
    if (eraserBtn) { eraserBtn.addEventListener('click', function () { closeMenus(); setAnnoMode(annoMode === 'eraser' ? 'select' : 'eraser'); }); }

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
    if (els.tableResetBtn) { els.tableResetBtn.addEventListener('click', resetTableLayout); }

    // 내보내기 메뉴
    var exportBtn = document.getElementById('dws-btn-export');
    exportBtn.addEventListener('click', function (e) { e.stopPropagation(); toggleMenu(els.exportMenu); });
    document.getElementById('dws-btn-export-png').addEventListener('click', exportPng);
    var exportAllBtn = document.getElementById('dws-btn-export-all');
    if (exportAllBtn) { exportAllBtn.addEventListener('click', exportAll); }
    document.getElementById('dws-btn-version-history').addEventListener('click', openVersionDialog);

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

    // 미니 툴바 — 텍스트 편집 중 프리셋 삽입 드롭다운(편집 중에만 노출: CSS .dws-mt-editing)
    // 미니바 mousedown 이 preventDefault(위 els.mt 핸들러) → 버튼/항목 클릭에도 오버레이 포커스 유지.
    if (els.mtPresetBtn && els.mtPresetMenu) {
      els.mtPresetBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        var willShow = els.mtPresetMenu.hidden;
        closeMenus();
        if (willShow) { renderEditPresetMenu(); els.mtPresetMenu.hidden = false; }
      });
    }

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

    // 정렬 툴바(다중 선택) — 6종 정렬 버튼
    if (els.alignToolbar) {
      Array.prototype.forEach.call(els.alignToolbar.querySelectorAll('[data-align]'), function (b) {
        b.addEventListener('click', function () { alignSelected(b.getAttribute('data-align')); });
      });
    }

    // 로고 팝업
    Array.prototype.forEach.call(els.logoPopup.querySelectorAll('[data-logo]'), function (b) {
      b.addEventListener('click', function (e) { e.stopPropagation(); setLogo(b.getAttribute('data-logo')); hideLogoPopup(); });
    });

    // 버전 이력 다이얼로그
    document.getElementById('dws-version-close').addEventListener('click', closeVersionDialog);

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
      // 라이트박스 열림 시: ESC 로 닫고 다른 단축키는 모달 우선으로 무시.
      if (els.lightbox && !els.lightbox.hidden) {
        if (e.key === 'Escape') { e.preventDefault(); closeLightbox(); }
        return;
      }
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
      if (!selectedIds.length) { return; }
      if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); deleteSelected(); return; }
      var step = e.shiftKey ? 10 : 1, dx = 0, dy = 0;
      if (e.key === 'ArrowLeft') { dx = -step; }
      else if (e.key === 'ArrowRight') { dx = step; }
      else if (e.key === 'ArrowUp') { dy = -step; }
      else if (e.key === 'ArrowDown') { dy = step; }
      else { return; }
      e.preventDefault();
      var now = Date.now();
      if (now - lastArrowUndoTs > 500) { recordUndo(); }
      lastArrowUndoTs = now;
      // 단일·다중 공용: 선택 전체를 같은 델타로 이동.
      selectedIds.forEach(function (id) { var o = findObj(id); if (o) { moveObjectBy(o, dx, dy); } });
      markDirty();
      if (isMultiSelect() && transformer) { transformer.forceUpdate(); }
      positionMiniToolbar();
      positionAlignToolbar();
    });

    // 스크롤/리사이즈 시 미니툴바/정렬툴바 위치 갱신
    els.canvas.addEventListener('scroll', function () { positionMiniToolbar(); positionAlignToolbar(); });
    window.addEventListener('resize', function () { positionMiniToolbar(); positionAlignToolbar(); });

    /* Space+드래그 캔버스 팬(포토샵 hand tool 감각) — els.canvas 스크롤 뷰포트 조작.
       Space 를 홀드한 동안만 드래그가 팬으로 소비된다. capture 단계 mousedown 으로
       Konva 컨테이너(선택/러버밴드/객체드래그)보다 먼저 가로채고, Space 홀드가 아니면
       아무것도 안 하므로 기존 마퀴/객체드래그/텍스트생성(Ctrl/Cmd+클릭)과 무충돌.
       폼 셀/텍스트 편집 중 Space 는 절대 가로채지 않는다(정상 입력). */
    (function wirePan() {
      var panning = false;
      var spaceHeld = false;
      var startX = 0, startY = 0, startScrollLeft = 0, startScrollTop = 0;
      function isSpaceKey(e) { return e.code === 'Space' || e.key === ' ' || e.key === 'Spacebar'; }
      function onPanMove(e) {
        if (!panning) { return; }
        // 드래그 방향으로 내용이 따라오는 hand tool 감각(범위 밖이면 브라우저가 clamp).
        els.canvas.scrollLeft = startScrollLeft - (e.clientX - startX);
        els.canvas.scrollTop = startScrollTop - (e.clientY - startY);
        e.preventDefault();
      }
      function onPanUp() {
        if (!panning) { return; }
        panning = false;
        window.removeEventListener('mousemove', onPanMove, true);
        window.removeEventListener('mouseup', onPanUp, true);
        els.canvas.classList.remove('dws-panning');
      }
      // capture=true 필수: 버블 단계면 Konva 가 이미 처리해 stopPropagation 이 무효.
      els.canvas.addEventListener('mousedown', function (e) {
        if (!spaceHeld) { return; }           // Space 홀드 없으면 기존 선택/러버밴드/객체드래그 그대로
        e.preventDefault();                   // 텍스트 선택 억제
        e.stopPropagation();                  // Konva 로 전파 차단(선택/러버밴드/객체드래그 미발동)
        panning = true;
        startX = e.clientX; startY = e.clientY;
        startScrollLeft = els.canvas.scrollLeft; startScrollTop = els.canvas.scrollTop;
        els.canvas.classList.add('dws-panning');
        window.addEventListener('mousemove', onPanMove, true);
        window.addEventListener('mouseup', onPanUp, true);
      }, true);

      // Space 홀드 동안 grab 커서(팬 준비). 편집 중이면 폼 입력이 정상 통과하도록 무시.
      window.addEventListener('keydown', function (e) {
        if (!isSpaceKey(e)) { return; }
        var ae = document.activeElement;
        var editing = !!(ae && (ae.isContentEditable || ae.tagName === 'TEXTAREA' || ae.tagName === 'INPUT' || ae.tagName === 'SELECT'));
        if (editing) { return; }              // 폼 셀/텍스트 편집 중 Space 는 정상 입력(가로채지 않음)
        spaceHeld = true;
        e.preventDefault();                   // 페이지 스크롤/포커스 버튼 트리거 방지
        els.canvas.classList.add('dws-pan-ready');
      });
      window.addEventListener('keyup', function (e) {
        if (!isSpaceKey(e)) { return; }
        spaceHeld = false;
        els.canvas.classList.remove('dws-pan-ready');
        onPanUp();                            // 진행 중 팬 종료
      });
      // 창 blur 시 spaceHeld·커서 잔류 방지(Space 뗀 이벤트를 놓친 경우 대비).
      window.addEventListener('blur', function () {
        spaceHeld = false;
        els.canvas.classList.remove('dws-pan-ready');
        onPanUp();
      });
    })();

    /* Alt+휠 = 도면 확대/축소. 일반 휠(Alt 없음)은 기존 스크롤 그대로 관여 안 함.
       커서 아래 논리점을 고정해(포토샵 감각) 줌 전후 scrollLeft/Top 을 보정한다.
       setZoom 이 슬라이더(#dws-zoom-range)·라벨을 자동 갱신하므로 별도 DOM 갱신 불필요.
       __DWS_BOUND 스코프라 1회만 바인딩(idempotent). */
    els.canvas.addEventListener('wheel', function (e) {
      if (!e.altKey) { return; }              // 일반 휠 = 기존 스크롤(관여 안 함)
      e.preventDefault();
      var rect = els.canvas.getBoundingClientRect();
      var px = e.clientX - rect.left, py = e.clientY - rect.top;   // 뷰포트 내 커서 좌표
      var focalLogicalX = (els.canvas.scrollLeft + px) / zoom;     // 커서 아래 논리점(줌 무관)
      var focalLogicalY = (els.canvas.scrollTop + py) / zoom;
      var step = 0.1;                                              // 휠 1노치 = 10%p
      var nz = clamp(zoom + (e.deltaY < 0 ? step : -step), 0.5, 2.5);
      if (nz === zoom) { return; }            // clamp 경계 도달 → 변화 없음
      setZoom(nz);
      // 커서 아래 논리점이 화면상 같은 위치에 남도록 스크롤 보정(범위 밖은 브라우저 clamp).
      els.canvas.scrollLeft = focalLogicalX * nz - px;
      els.canvas.scrollTop = focalLogicalY * nz - py;
    }, { passive: false });

    /* 손가락 네비게이션(태블릿) — 1지 드래그=팬, 2지=핀치 확대(중점 고정).
       touch-action:none 이라 네이티브 스크롤/줌은 꺼져 있고 여기서 전량 구현한다.
       Apple Pencil(touchType 'stylus')은 그리기(pointer 'pen') 담당이라 제외하고,
       펜슬 필기 중(isDrawingPen)에는 팬/핀치를 억제한다(팜 리젝션). capture+stopPropagation
       으로 Konva 가 손가락 터치를 받지 않게 해 객체 조작·탭을 차단한다. */
    (function wireTouchNav() {
      if (!els.canvas) { return; }
      var mode = 0;               // 0=없음, 1=팬, 2=핀치
      var startX = 0, startY = 0, startScrollLeft = 0, startScrollTop = 0;
      var startDist = 1, startZoom = 1, focalLogicalX = 0, focalLogicalY = 0;

      function fingerList(touchList) {
        var out = [];
        for (var i = 0; i < touchList.length; i++) {
          if (touchList[i].touchType === 'stylus') { continue; }   // 펜슬 → 그리기 담당(제외)
          out.push(touchList[i]);
        }
        return out;
      }
      function dist(a, b) { var dx = a.clientX - b.clientX, dy = a.clientY - b.clientY; return Math.sqrt(dx * dx + dy * dy); }
      function midpoint(a, b) { return { x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2 }; }

      function initGesture(fingers) {
        var rect = els.canvas.getBoundingClientRect();
        startScrollLeft = els.canvas.scrollLeft; startScrollTop = els.canvas.scrollTop;
        if (fingers.length >= 2) {
          mode = 2;
          startDist = dist(fingers[0], fingers[1]) || 1;
          startZoom = zoom;
          var m = midpoint(fingers[0], fingers[1]);
          focalLogicalX = (startScrollLeft + (m.x - rect.left)) / zoom;
          focalLogicalY = (startScrollTop + (m.y - rect.top)) / zoom;
        } else {
          mode = 1;
          startX = fingers[0].clientX; startY = fingers[0].clientY;
        }
      }
      function onMove(e) {
        if (mode === 0) { return; }
        var fingers = fingerList(e.touches);
        if (!fingers.length) { return; }
        // 손가락 수 변화(2↔1) → baseline 재설정(급점프 방지).
        if ((mode === 2 && fingers.length < 2) || (mode === 1 && fingers.length >= 2)) { initGesture(fingers); }
        if (e.cancelable) { e.preventDefault(); }
        e.stopPropagation();
        if (mode === 2 && fingers.length >= 2) {
          var rect = els.canvas.getBoundingClientRect();
          var d = dist(fingers[0], fingers[1]) || 1;
          var nz = clamp(startZoom * (d / startDist), 0.5, 2.5);
          setZoom(nz);
          var m = midpoint(fingers[0], fingers[1]);
          els.canvas.scrollLeft = focalLogicalX * nz - (m.x - rect.left);
          els.canvas.scrollTop = focalLogicalY * nz - (m.y - rect.top);
        } else {
          els.canvas.scrollLeft = startScrollLeft - (fingers[0].clientX - startX);
          els.canvas.scrollTop = startScrollTop - (fingers[0].clientY - startY);
        }
      }
      function onEnd(e) {
        var fingers = fingerList(e.touches);
        if (!fingers.length) {
          mode = 0;
          window.removeEventListener('touchmove', onMove, true);
          window.removeEventListener('touchend', onEnd, true);
          window.removeEventListener('touchcancel', onEnd, true);
        } else {
          initGesture(fingers);   // 남은 손가락으로 재설정(2→1 전환 이어가기)
        }
      }
      els.canvas.addEventListener('touchstart', function (e) {
        if (isDrawingPen) { return; }            // 펜슬 필기 중 → 팜 리젝션(팬/핀치 억제)
        var fingers = fingerList(e.touches);
        if (!fingers.length) { return; }         // 펜슬 단독 터치 → 그리기 담당(관여 안 함)
        e.stopPropagation();                     // Konva 로 손가락 터치 전파 차단(객체 조작·탭 방지)
        if (e.cancelable) { e.preventDefault(); }
        initGesture(fingers);
        window.addEventListener('touchmove', onMove, { capture: true, passive: false });
        window.addEventListener('touchend', onEnd, true);
        window.addEventListener('touchcancel', onEnd, true);
      }, { capture: true, passive: false });
    })();

    // 캔버스 이미지 파일 드래그앤드롭(드롭 지점 배치). 빈 시트 오버레이 위 드롭도 안내 토스트.
    bindCanvasDnd();

    // 미저장 이탈 가드
    window.addEventListener('beforeunload', function (e) {
      if (dirty) { e.preventDefault(); e.returnValue = ''; return ''; }
    });
  }

  function autofill() {
    if (!canSave || !currentSheet()) { return; }
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
    // 모바일/태블릿도 편집 허용(펜슬 프리핸드 + 두 손가락 팬/핀치). 기존 "데스크톱
    // 전용" 전체화면 차단(dws-mobile-notice)은 폐지 — 종이 수기 마크업의 태블릿 DX가
    // 본 기능의 목적이다. 작은 화면 크롬 밀집은 확대/팬으로 흡수(반응형 셸 정돈은 후속).
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
    loadUserPresets();
    // 자동 저장 타이머(단일). 실제 저장 여부는 tickAutosave 내부 게이트가 판단(canSave 포함).
    if (!autosaveTimer) { autosaveTimer = setInterval(tickAutosave, AUTOSAVE_INTERVAL_MS); }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();

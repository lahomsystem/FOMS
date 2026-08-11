/**
 * 관리자 감사 표 컬럼 폭 조절 (AUDIT-LOG P4 후속).
 *
 * 감사 화면은 한 행에 시간·행위·대상·문장·JSON이 함께 들어가서 기본 폭으로는 시간이 세 줄로
 * 접히고 문장 칸이 좁다. 사람마다 보는 축이 달라(어떤 날은 문장, 어떤 날은 JSON) 고정 폭으로는
 * 답이 없으므로 **헤더 경계를 끌어 폭을 조절**하고 그 폭을 브라우저에 기억시킨다.
 *
 * 표에 ``data-foms-resizable-table`` 을 달면 자동 적용된다(opt-in). 저장 키는 그 값이다.
 * 마우스가 있는 넓은 화면에서만 켠다 — 터치·좁은 화면에서는 손잡이가 오히려 방해다.
 *
 * 구현은 기존 대시보드(출고·실측·AS)와 같은 ColumnResizer 런타임을 재사용한다.
 */
(function () {
  'use strict';

  var TABLE_SELECTOR = 'table[data-foms-resizable-table]';
  var DESKTOP_MIN_WIDTH = 992;
  var POINTER_QUERY = '(hover: hover) and (pointer: fine)';
  var STORAGE_PREFIX = 'foms.auditTable.columnWidths.';
  var MIN_COLUMN_WIDTH = 60;

  var instances = [];
  var resizeTimer = null;

  /**
   * 폭 조절을 켤 화면인지 판정한다(마우스 있는 넓은 화면만).
   * @returns {boolean}
   */
  function canResize() {
    if (window.innerWidth < DESKTOP_MIN_WIDTH) return false;
    if (typeof window.matchMedia !== 'function') return true;
    return window.matchMedia(POINTER_QUERY).matches;
  }

  /**
   * 표의 저장 키.
   * @param {HTMLTableElement} table 대상 표.
   * @returns {string}
   */
  function storageKey(table) {
    return STORAGE_PREFIX + (table.getAttribute('data-foms-resizable-table') || 'default');
  }

  /**
   * 저장해 둔 폭 배열을 읽는다. 값이 깨졌으면 무시하고 기본 폭을 쓴다.
   * @param {HTMLTableElement} table 대상 표.
   * @param {number} columnCount 헤더 칸 수.
   * @returns {number[]|null} 픽셀 폭 배열. 없거나 칸 수가 다르면 ``null``.
   */
  function readWidths(table, columnCount) {
    try {
      var raw = window.localStorage.getItem(storageKey(table));
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (!Array.isArray(parsed) || parsed.length !== columnCount) return null;
      var valid = parsed.every(function (value) {
        return typeof value === 'number' && isFinite(value) && value >= MIN_COLUMN_WIDTH;
      });
      return valid ? parsed : null;
    } catch (error) {
      return null;  // 저장소 차단(사생활 보호 모드)·손상 값 — 기본 폭으로 진행한다.
    }
  }

  /**
   * 현재 폭을 저장한다(실패는 조용히 넘긴다 — 표시 기능이 저장 때문에 죽으면 안 된다).
   * @param {HTMLTableElement} table 대상 표.
   */
  function saveWidths(table) {
    try {
      var widths = Array.prototype.map.call(
        table.querySelectorAll('thead tr:first-child > th'),
        function (th) { return Math.round(th.getBoundingClientRect().width); }
      );
      window.localStorage.setItem(storageKey(table), JSON.stringify(widths));
    } catch (error) {
      /* 저장 실패는 무시 — 이번 세션에서만 폭이 유지된다. */
    }
  }

  /**
   * ColumnResizer 생성자를 얻는다.
   *
   * 런타임은 UMD 번들이라 ``window.ColumnResizer`` 가 **네임스페이스 객체**(``{default: …}``)로
   * 잡힐 수 있다 — 기존 대시보드 래퍼들과 같은 fallback 을 쓴다.
   * @returns {Function|null} 생성자. 런타임이 없으면 ``null``.
   */
  function getResizerCtor() {
    if (!window.ColumnResizer) return null;
    return window.ColumnResizer.default || window.ColumnResizer;
  }

  /**
   * 표 1개에 폭 조절을 붙인다.
   * @param {HTMLTableElement} table 대상 표.
   */
  function attach(table) {
    var Resizer = getResizerCtor();
    if (typeof Resizer !== 'function') return;
    if (!table.id) table.id = 'audit-table-' + instances.length;

    var headers = table.querySelectorAll('thead tr:first-child > th');
    if (!headers.length) return;

    var options = {
      resizeMode: 'fit',
      liveDrag: true,
      minWidth: MIN_COLUMN_WIDTH,
      headerOnly: false,
      partialRefresh: true,
      serialize: false,        // 저장은 이 모듈이 localStorage 로 한다(세션 넘어 유지).
      onResize: function () { saveWidths(table); }
    };

    var stored = readWidths(table, headers.length);
    if (stored) options.widths = stored;

    instances.push(new Resizer(table, options));
    table.classList.add('foms-audit-table--resizable');
  }

  /**
   * 화면 폭이 바뀌면 다시 판정한다(태블릿 가로/세로 전환).
   */
  function onViewportChange() {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(function () {
      if (!instances.length && canResize()) init();
    }, 200);
  }

  /**
   * opt-in 표 전부에 적용한다.
   */
  function init() {
    if (!canResize()) return;
    Array.prototype.forEach.call(document.querySelectorAll(TABLE_SELECTOR), attach);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  window.addEventListener('resize', onViewportChange);
})();

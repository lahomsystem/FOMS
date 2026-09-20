/**
 * 공용 사유 입력 바텀시트 컨트롤러(C-D1·C-D2).
 *
 * window.prompt 를 쓰던 모바일 액션(수정 제작·제작 취소·시공 불가)이 전부 이 시트
 * 하나를 쓴다. 마크업은 templates/partials/shared/foms_reason_sheet.html 이고
 * 스타일은 static/css/components/foms-reason-sheet.css 다(인라인 style 금지).
 *
 * 공개 API:
 *   window.FomsReasonSheet.open({
 *     title,        // 시트 제목(문자열)
 *     actionLabel,  // 확인 버튼 글자(문자열, 기본 '확인')
 *     reasons,      // [{code, label}] 라디오 목록. null/빈 배열이면 사유 선택 없음
 *     detailLabel,  // 상세 textarea 라벨(문자열)
 *     onSubmit(reason, detail)  // 확인 시 호출. reason 은 선택 없음이면 ''
 *   })
 *   window.FomsReasonSheet.close()
 *
 * document 위임 + window.__FOMS_REASON_SHEET_BOUND 싱글턴이라 셸 프래그먼트가
 * 재실행돼도 리스너가 누적되지 않는다.
 */
(function () {
  'use strict';

  if (window.__FOMS_REASON_SHEET_BOUND) {
    return;
  }
  window.__FOMS_REASON_SHEET_BOUND = true;

  var SHEET_SEL = '[data-foms-reason-sheet]';
  var state = {
    reasons: [],
    selected: '',
    onSubmit: null
  };

  function getSheet() {
    return document.querySelector(SHEET_SEL);
  }

  function setError(sheet, msg) {
    var el = sheet && sheet.querySelector('[data-foms-reason-error]');
    if (!el) {
      return;
    }
    if (msg) {
      el.textContent = msg;
      el.hidden = false;
    } else {
      el.textContent = '';
      el.hidden = true;
    }
  }

  function setText(sheet, selector, value) {
    var el = sheet.querySelector(selector);
    if (el && value) {
      el.textContent = value;
    }
  }

  // 사유 라디오 목록을 다시 그린다(옵션이 없으면 칸 자체를 숨긴다).
  function renderReasons(sheet, reasons) {
    var box = sheet.querySelector('[data-foms-reason-list]');
    if (!box) {
      return;
    }
    var legend = box.querySelector('.foms-reason-sheet__legend');
    while (box.lastChild && box.lastChild !== legend) {
      box.removeChild(box.lastChild);
    }
    if (!reasons.length) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    reasons.forEach(function (item, idx) {
      var label = document.createElement('label');
      label.className = 'foms-reason-sheet__option';
      if (idx === 0) {
        label.classList.add('is-selected');
      }
      var input = document.createElement('input');
      input.type = 'radio';
      input.name = 'foms-reason-sheet-reason';
      input.value = item.code;
      input.setAttribute('data-foms-reason-option', item.code);
      if (idx === 0) {
        input.checked = true;
      }
      var span = document.createElement('span');
      span.textContent = item.label;
      label.appendChild(input);
      label.appendChild(span);
      box.appendChild(label);
    });
  }

  function syncSelection(sheet) {
    var options = sheet.querySelectorAll('[data-foms-reason-option]');
    Array.prototype.forEach.call(options, function (input) {
      var label = input.parentNode;
      if (label && label.classList) {
        label.classList.toggle('is-selected', !!input.checked);
      }
      if (input.checked) {
        state.selected = input.value;
      }
    });
  }

  function close() {
    var sheet = getSheet();
    state.onSubmit = null;
    if (!sheet) {
      return;
    }
    sheet.hidden = true;
    sheet.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('foms-reason-sheet-open');
  }

  function open(opts) {
    var sheet = getSheet();
    if (!sheet) {
      return;
    }
    var options = opts || {};
    state.reasons = Array.isArray(options.reasons) ? options.reasons : [];
    state.selected = state.reasons.length ? state.reasons[0].code : '';
    state.onSubmit = typeof options.onSubmit === 'function' ? options.onSubmit : null;

    setText(sheet, '[data-foms-reason-title]', options.title || '사유 입력');
    setText(sheet, '[data-foms-reason-detail-label]', options.detailLabel || '상세 사유 (선택)');
    setText(sheet, '[data-foms-reason-submit]', options.actionLabel || '확인');
    renderReasons(sheet, state.reasons);

    var detail = sheet.querySelector('[data-foms-reason-detail]');
    if (detail) {
      detail.value = '';
    }
    setError(sheet, '');

    sheet.hidden = false;
    sheet.setAttribute('aria-hidden', 'false');
    document.body.classList.add('foms-reason-sheet-open');
    var first = sheet.querySelector('[data-foms-reason-option]');
    if (first && first.focus) {
      try { first.focus(); } catch (_) { /* 포커스 실패는 무시 */ }
    }
  }

  function submit(sheet) {
    if (state.reasons.length && !state.selected) {
      setError(sheet, '사유를 먼저 선택하세요.');
      return;
    }
    var detailEl = sheet.querySelector('[data-foms-reason-detail]');
    var detail = detailEl ? (detailEl.value || '').trim() : '';
    var handler = state.onSubmit;
    var reason = state.reasons.length ? state.selected : '';
    close();
    if (handler) {
      handler(reason, detail);
    }
  }

  document.addEventListener('click', function (ev) {
    if (!ev.target || !ev.target.closest) {
      return;
    }
    if (ev.target.closest('[data-foms-reason-close]')) {
      ev.preventDefault();
      close();
      return;
    }
    var sheet = ev.target.closest(SHEET_SEL);
    if (!sheet) {
      return;
    }
    if (ev.target.closest('[data-foms-reason-submit]')) {
      ev.preventDefault();
      submit(sheet);
    }
  });

  document.addEventListener('change', function (ev) {
    var input = ev.target && ev.target.closest ? ev.target.closest('[data-foms-reason-option]') : null;
    if (!input) {
      return;
    }
    var sheet = input.closest(SHEET_SEL);
    if (sheet) {
      syncSelection(sheet);
      setError(sheet, '');
    }
  });

  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Escape') {
      return;
    }
    var sheet = getSheet();
    if (sheet && !sheet.hidden) {
      close();
    }
  });

  window.FomsReasonSheet = { open: open, close: close };
})();

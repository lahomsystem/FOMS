/**
 * 여러 날짜 달력(flatpickr mode 'multiple') — 주문 화면의 주 실측일 · 시공일과 항목 실측일 · 시공일이 같이 쓴다.
 *
 * PC(옛 폼 erp_order_tab.html): 전과 같다 — 칸 아래 달력 · 손으로 치기(allowInput) · 아래 [확인].
 * 폰(모바일 폼 .erp-order-mobile-form — 폰 · 세로 태블릿에서 남는 표면):
 *   - 칸을 누르면 자판 없이 화면 아래에서 달력이 올라온다. 입력 칸은 숨기고 같은 자리에 보기 칸을 둔다
 *     (입력 칸은 한 줄이라 반폭 시공일 칸에서 '2026-12-03, 2026-12-04' 가 잘렸다 — 보기 칸은 같은 글을 줄바꿈한다).
 *   - 날짜 칸 · 앞뒤 달 · [확인]은 손가락 크기(44px 이상), [지우기]로 고른 날짜를 모두 비운다.
 * 저장 값은 원래 입력 칸의 value("YYYY-MM-DD, YYYY-MM-DD") 그대로다. 보기 칸에는 data-erp 를 붙이지 않는다
 * (erpCollectStructured 가 행의 [data-erp] 를 모은다). 모양은 static/css/orders/erp-date-multi.css.
 */
(function () {
  'use strict';
  if (window.ErpDateMulti) return;

  var INPUT_VALUE = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');

  /** 모바일 폼 칸인가. 항목 행은 문서에 붙기 전에 달력을 붙이므로(erpNewItemRow) 그때는 문서에 모바일 폼이 있는지로 본다
   *  — erpNewItemRow 가 모바일 칸 모양을 고르는 erpIsMobileFormContext 와 같은 판정. */
  function isPhoneForm(input) {
    if (input.isConnected) return !!input.closest('.erp-order-mobile-form');
    return !!document.querySelector('.erp-order-mobile-form');
  }

  function hookList(first, second) {
    return [].concat(first || [], second || []);
  }

  function noPosition() {
    // 폰 달력 자리는 CSS(.erp-fp-sheet — 화면 아래)가 정한다. flatpickr 가 칸 옆 좌표를 넣지 않게 비워 둔다.
  }

  /** 달력 아래 줄: [확인](PC · 폰) — 폰은 왼쪽에 [지우기]도. 여러 날짜 달력은 날짜를 눌러도 저절로 닫히지 않는다. */
  function addBar(fp, phone) {
    var cal = fp.calendarContainer;
    if (!cal || cal.querySelector('.erp-fp-done-bar')) return;
    var bar = document.createElement('div');
    bar.className = 'erp-fp-done-bar';
    if (phone) {
      var clearBtn = document.createElement('button');
      clearBtn.type = 'button';
      clearBtn.className = 'erp-fp-clear-btn';
      clearBtn.textContent = '지우기';
      // 보던 달은 그대로 두고(toInitial=false) 고른 날짜만 비운다 — change 이벤트가 나가 자동 저장이 잡는다.
      clearBtn.addEventListener('click', function () { fp.clear(true, false); });
      bar.appendChild(clearBtn);
    }
    var doneBtn = document.createElement('button');
    doneBtn.type = 'button';
    doneBtn.className = 'erp-fp-done-btn';
    doneBtn.innerHTML = '<i class="fas fa-check"></i> 확인';
    doneBtn.addEventListener('click', function () { fp.close(); });
    bar.appendChild(doneBtn);
    cal.appendChild(bar);
  }

  /** 폰: 입력 칸 대신 보이는 보기 칸. 값은 늘 입력 칸 value 를 그대로 비춘다. */
  function mountView(input) {
    var view = document.createElement('div');
    view.className = input.className.split(/\s+/).filter(function (c) { return /^foms-/.test(c); })
      .concat('erp-fp-view').join(' ');
    view.setAttribute('role', 'button');
    view.tabIndex = 0;
    // 글은 저장 값 그대로("2026-11-26, 2026-12-01"). 날짜 하나는 한 덩어리(.erp-fp-date — 줄을 안 꺾음)라
    // 칸이 좁으면 ', ' 뒤에서만 다음 줄로 간다('2026-11-' / '30' 처럼 날짜 가운데서 꺾이지 않게).
    function render() {
      var value = String(INPUT_VALUE.get.call(input) || '').trim();
      view.textContent = '';
      view.classList.toggle('is-empty', !value);
      if (!value) {
        view.textContent = input.getAttribute('placeholder') || '';
        return;
      }
      var parts = value.split(', ');
      parts.forEach(function (part, i) {
        if (i) view.appendChild(document.createTextNode(' '));
        var span = document.createElement('span');
        span.className = 'erp-fp-date';
        // 쉼표도 날짜 덩어리에 붙인다 — 줄 맨 앞에 쉼표만 홀로 내려가지 않게. 칸 글은 저장 값과 같다.
        span.textContent = i < parts.length - 1 ? part + ',' : part;
        view.appendChild(span);
      });
    }
    // 이 칸 값을 쓰는 곳이 여럿이다(달력 · 서버 값 채우기 erpLoadStructured · 작성 중 복원 erp-order-autosave).
    // 어디서 value 를 써도 보기 칸이 따라오게 이 칸의 value 쓰기에 다시 그리기를 잇는다(읽기 · 쓰기 자체는 원래 그대로).
    Object.defineProperty(input, 'value', {
      configurable: true,
      get: function () { return INPUT_VALUE.get.call(this); },
      set: function (next) { INPUT_VALUE.set.call(this, next); render(); }
    });
    function openPicker() {
      if (input._flatpickr) input._flatpickr.open();
    }
    view.addEventListener('click', openPicker);
    view.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        openPicker();
      }
    });
    input.classList.add('erp-fp-src');
    input.insertAdjacentElement('afterend', view);
    input._erpDateView = view;
    render();
    return view;
  }

  /** 폰: 달력이 올라오면 그 칸이 달력에 가리지 않게 칸을 달력 위로 올린다(고르는 동안 칸 글이 바로 바뀌는 게 보이게). */
  function keepViewAboveSheet(_dates, _str, fp) {
    var view = fp.input && fp.input._erpDateView;
    if (!view || !fp.isOpen) return;
    // 판은 올라오는 중(transform)이라 top 을 바로 읽으면 아래로 치우친다 — 화면 아래에 붙으니 높이로 자리를 센다.
    var sheetTop = window.innerHeight - fp.calendarContainer.getBoundingClientRect().height;
    var overlap = view.getBoundingClientRect().bottom + 12 - sheetTop;
    if (overlap > 0) window.scrollBy(0, overlap);
  }

  /**
   * 여러 날짜 달력을 칸에 붙인다. 이미 붙어 있거나 flatpickr 가 없으면 아무것도 안 한다.
   *
   * @param {HTMLInputElement} input 달력을 붙일 입력 칸(저장 값이 들어 있는 칸).
   * @param {Object} [extra] 더할 flatpickr 옵션(onReady · onOpen 같은 훅은 이 파일 훅 뒤에 이어 부른다).
   * @returns {Object|undefined} flatpickr 인스턴스.
   */
  function attach(input, extra) {
    if (!input || typeof window.flatpickr !== 'function') return undefined;
    if (input._flatpickr) return input._flatpickr;
    var ex = extra || {};
    var phone = isPhoneForm(input);
    var opts = Object.assign({}, ex, {
      mode: 'multiple',
      dateFormat: 'Y-m-d',
      locale: 'ko',
      // 손으로 치기는 PC 만. 폰은 입력 칸을 숨기고 보기 칸을 눌러 달력만 연다(자판이 안 올라온다).
      allowInput: !phone,
      onReady: hookList(function (_d, _s, fp) {
        addBar(fp, phone);
        if (phone) fp.calendarContainer.classList.add('erp-fp-sheet');
      }, ex.onReady)
    });
    if (phone) {
      var view = mountView(input);
      opts.position = noPosition;
      // 보기 칸을 눌러도 '달력 밖을 눌렀다'로 닫지 않는다(인스턴스마다 새 배열 — flatpickr 기본 배열은 모두가 같이 쓴다).
      opts.ignoredFocusElements = [view];
      opts.onOpen = hookList(ex.onOpen, keepViewAboveSheet);
      // 날짜를 더하면 칸이 줄바꿈으로 길어진다 — 그때도 칸 아래 끝이 판에 안 덮이게.
      opts.onChange = hookList(ex.onChange, keepViewAboveSheet);
    }
    return window.flatpickr(input, opts);
  }

  window.ErpDateMulti = { attach: attach };
})();

/**
 * 여러 날짜 달력(flatpickr mode 'multiple') — 주문 화면의 주 실측일 · 시공일과 항목 실측일 · 시공일이 같이 쓴다.
 *
 * PC(옛 폼 erp_order_tab.html): 전과 같다 — 칸 아래 달력 · 손으로 치기(allowInput) · 아래 [확인].
 * 폰(모바일 폼 .erp-order-mobile-form — 폰 · 세로 태블릿에서 남는 표면):
 *   - 칸을 누르면 자판 없이 화면 아래에서 달력이 올라온다. 입력 칸은 숨기고 같은 자리에 보기 칸을 둔다
 *     (입력 칸은 한 줄이라 반폭 시공일 칸에서 '2026-12-03, 2026-12-04' 가 잘렸다 — 보기 칸은 같은 글을 줄바꿈한다).
 *   - 날짜 칸 · 앞뒤 달 · [확인]은 손가락 크기(44px 이상), [지우기]로 고른 날짜를 모두 비운다. 해 칸은 읽기만(자판 없음).
 *   - 보기 칸 이름은 그 칸의 label 글. Enter · Space 로 열면 달력 날짜로 포커스가 가고(화살표 이동),
 *     [확인] · Escape 로 닫으면 보기 칸으로 돌아온다.
 * 저장 값은 원래 입력 칸의 value("YYYY-MM-DD, YYYY-MM-DD") 그대로다. 보기 칸에는 data-erp 를 붙이지 않는다
 * (erpCollectStructured 가 행의 [data-erp] 를 모은다). 모양은 static/css/orders/erp-date-multi.css.
 * node 시험: tests/domains/erp_date_multi_runner.js.
 */
(function () {
  'use strict';
  if (window.ErpDateMulti) return;

  var INPUT_VALUE = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
  var GAP = 12;
  var DAY = '.flatpickr-day:not(.prevMonthDay):not(.nextMonthDay)';
  var seq = 0;

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

  /** 칸 이름 label: for= 로 이어진 것, 없으면 칸을 감싼 줄(두 겹까지)의 첫 label(항목 칸은 for 가 없다). */
  function findLabel(input) {
    if (input.id && input.isConnected) {
      var byFor = document.querySelector('label[for="' + input.id + '"]');
      if (byFor) return byFor;
    }
    var box = input.parentElement;
    for (var depth = 0; box && depth < 2; depth += 1, box = box.parentElement) {
      var label = box.querySelector('label');
      if (label) return label;
    }
    return null;
  }

  /** 열린 달력의 날짜 칸에 포커스(고른 날 → 오늘 → 그 달 첫날) — 그다음 화살표 · Enter · Escape 는 flatpickr 가 받는다. */
  function focusDay(fp) {
    var cal = fp.calendarContainer;
    var day = cal.querySelector(DAY + '.selected') || cal.querySelector(DAY + '.today') || cal.querySelector(DAY);
    if (day) day.focus();
  }

  /** 키보드로 날짜를 고르면 flatpickr 가 날짜 칸을 새로 그려(buildDays) 포커스가 사라진다 — 다음 화살표 · Escape 가 안 먹던 것.
   *  키보드로 움직이던 때만 방금 고른 날짜 칸에 포커스를 되돌린다(손가락으로 누를 때는 회색 포커스 표시를 만들지 않는다). */
  function keepKeyboardFocus(fp) {
    var cal = fp.calendarContainer;
    if (!fp._erpByKeyboard || !fp.isOpen || cal.contains(document.activeElement)) return;
    var picked = fp.latestSelectedDateObj && fp.latestSelectedDateObj.getTime();
    var days = cal.querySelectorAll(DAY);
    for (var i = 0; i < days.length; i += 1) {
      if (days[i].dateObj && days[i].dateObj.getTime() === picked) {
        days[i].focus();
        return;
      }
    }
    focusDay(fp);
  }

  /** 폰: 입력 칸 대신 보이는 보기 칸. 값은 늘 입력 칸 value 를 그대로 비춘다. */
  function mountView(input) {
    seq += 1;
    var view = document.createElement('div');
    view.className = input.className.split(/\s+/).filter(function (c) { return /^foms-/.test(c); })
      .concat('erp-fp-view').join(' ');
    view.setAttribute('role', 'button');
    view.setAttribute('aria-expanded', 'false');
    view.tabIndex = 0;
    var valueEl = document.createElement('span');
    valueEl.id = 'erp-fp-value-' + seq;
    // 빈 칸의 자리 글은 보이기만 한다 — 화면 읽기는 값으로 읽지 않는다.
    var holder = document.createElement('span');
    holder.className = 'erp-fp-placeholder';
    holder.setAttribute('aria-hidden', 'true');
    view.appendChild(valueEl);
    view.appendChild(holder);
    var label = findLabel(input);
    if (label) {
      if (!label.id) label.id = 'erp-fp-label-' + seq;
      view.setAttribute('aria-labelledby', label.id + ' ' + valueEl.id);
    }
    // 글은 저장 값 그대로("2026-11-26, 2026-12-01"). 날짜 하나(쉼표 포함)는 한 덩어리(.erp-fp-date — 줄을 안 꺾음)라
    // 칸이 좁으면 ', ' 뒤에서만 다음 줄로 간다('2026-11-' / '30' · 줄 맨 앞 쉼표처럼 꺾이지 않게).
    function render() {
      var value = String(INPUT_VALUE.get.call(input) || '').trim();
      valueEl.textContent = '';
      holder.textContent = value ? '' : (input.getAttribute('placeholder') || '');
      view.classList.toggle('is-empty', !value);
      if (!value) return;
      var parts = value.split(', ');
      parts.forEach(function (part, i) {
        if (i) valueEl.appendChild(document.createTextNode(' '));
        var span = document.createElement('span');
        span.className = 'erp-fp-date';
        span.textContent = i < parts.length - 1 ? part + ',' : part;
        valueEl.appendChild(span);
      });
    }
    // 이 칸 값을 쓰는 곳이 여럿이다(달력 · 서버 값 채우기 erpLoadStructured · 작성 중 복원 erp-order-autosave).
    // 어디서 value 를 써도 보기 칸이 따라오게 이 칸의 value 쓰기에 다시 그리기를 잇는다(읽기 · 쓰기 자체는 원래 그대로).
    Object.defineProperty(input, 'value', {
      configurable: true,
      get: function () { return INPUT_VALUE.get.call(this); },
      set: function (next) { INPUT_VALUE.set.call(this, next); render(); }
    });
    function openPicker(byKeyboard) {
      var fp = input._flatpickr;
      if (!fp) return;
      fp.open();
      if (byKeyboard && fp.isOpen) focusDay(fp);
    }
    view.addEventListener('click', function () { openPicker(false); });
    view.addEventListener('keydown', function (e) {
      var fp = input._flatpickr;
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        openPicker(true);
      } else if (fp && fp.isOpen && e.key === 'Escape') {
        e.preventDefault();
        fp.close();
      } else if (fp && fp.isOpen && e.key.indexOf('Arrow') === 0) {
        e.preventDefault();
        focusDay(fp);
      }
    });
    // for= 로 이어진 이름을 누르면 PC 처럼 달력이 열린다(숨은 입력 칸은 포커스를 못 받는다).
    if (label && label.htmlFor && label.htmlFor === input.id) {
      label.addEventListener('click', function (e) {
        e.preventDefault();
        openPicker(false);
      });
    }
    input.classList.add('erp-fp-src');
    input.insertAdjacentElement('afterend', view);
    input._erpDateView = view;
    render();
    return view;
  }

  /** 폰: 달력이 올라오면 그 칸이 판에 가리지 않게 칸을 판 위로 올린다(고르는 동안 칸 글이 바로 바뀌는 게 보이게).
   *  안쪽이 따로 스크롤되는 곳(태블릿 옆 시트 · 분할 칸)도 있어 scrollIntoView 에 맡기고, 판 높이만큼을 칸의
   *  scroll-margin-bottom(CSS --erp-fp-sheet-h)으로 준다. 판이 화면을 거의 덮으면(가로 폰) 올릴 자리가 없어 그대로 둔다. */
  function keepViewAboveSheet(fp) {
    var view = fp.input && fp.input._erpDateView;
    if (!view || !fp.isOpen) return;
    // 판은 올라오는 중(transform)이라 top 을 바로 읽으면 아래로 치우친다 — 화면 아래에 붙으니 높이로 자리를 센다.
    var sheetH = fp.calendarContainer.getBoundingClientRect().height;
    var sheetTop = window.innerHeight - sheetH;
    var rect = view.getBoundingClientRect();
    if (rect.bottom + GAP <= sheetTop || sheetTop - GAP < rect.height) return;
    // rect 는 화면 크기 배율(html zoom)이 붙은 값, CSS 값은 배율 전 값.
    var zoom = typeof window.fomsUiZoom === 'function' ? Number(window.fomsUiZoom()) || 1 : 1;
    view.style.setProperty('--erp-fp-sheet-h', Math.ceil(sheetH / zoom) + 'px');
    view.scrollIntoView({ block: 'nearest' });
  }

  function onSheetOpen(_dates, _str, fp) {
    var input = fp.input;
    input._erpDateView.setAttribute('aria-expanded', 'true');
    // 인라인 저장(static/js/foms/inline-edit.js)은 칸이 포커스를 받을 때 '바꾸기 전 값'을 적는다(칸 focus · #erp-items focusin).
    // 폰의 입력 칸은 숨어 포커스를 못 받는다 — 달력이 열리는 때를 같은 신호로 알린다(포커스는 옮기지 않는다: 자판 없음).
    input.dispatchEvent(new FocusEvent('focus'));
    input.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
    keepViewAboveSheet(fp);
  }

  function onSheetClose(_dates, _str, fp) {
    var view = fp.input._erpDateView;
    view.setAttribute('aria-expanded', 'false');
    // [확인] · Escape 로 닫으면 포커스를 보기 칸으로 돌린다. 다른 칸을 눌러 닫힌 때는 그 칸에 둔다.
    var active = document.activeElement;
    if (!active || active === document.body || active === view || fp.calendarContainer.contains(active)) {
      view.focus({ preventScroll: true });
    }
  }

  /**
   * 여러 날짜 달력을 칸에 붙인다. 이미 붙어 있거나 flatpickr 가 없으면 아무것도 안 한다.
   *
   * @param {HTMLInputElement} input 달력을 붙일 입력 칸(저장 값이 들어 있는 칸).
   * @param {Object} [extra] 더할 flatpickr 옵션(onReady · onOpen 같은 훅은 이 파일 훅과 함께 부른다).
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
        if (!phone) return;
        fp.calendarContainer.classList.add('erp-fp-sheet');
        fp.calendarContainer.addEventListener('keydown', function () { fp._erpByKeyboard = true; }, true);
        fp.calendarContainer.addEventListener('pointerdown', function () { fp._erpByKeyboard = false; }, true);
        // 해 칸은 숫자 입력이라 누르면 자판이 뜬다 — 폰은 읽기만(해는 앞뒤 달 단추로 넘어간다).
        if (fp.currentYearElement) fp.currentYearElement.readOnly = true;
      }, ex.onReady)
    });
    if (phone) {
      var view = mountView(input);
      opts.position = noPosition;
      // 보기 칸을 눌러도 '달력 밖을 눌렀다'로 닫지 않는다(인스턴스마다 새 배열 — flatpickr 기본 배열은 모두가 같이 쓴다).
      opts.ignoredFocusElements = [view];
      opts.onOpen = hookList(ex.onOpen, onSheetOpen);
      opts.onClose = hookList(ex.onClose, onSheetClose);
      // 날짜를 더하면 칸이 줄바꿈으로 길어진다 — 그때도 칸 아래 끝이 판에 안 덮이게.
      opts.onChange = hookList(ex.onChange, function (_d, _s, fp) {
        keepKeyboardFocus(fp);
        keepViewAboveSheet(fp);
      });
    }
    return window.flatpickr(input, opts);
  }

  window.ErpDateMulti = { attach: attach };
})();
